import { Router } from 'express';
import { execSync } from 'child_process';
import { readFileSync, statSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { isAboutVacaRequest } from './voice-action.js';
import { clearRolesRoleCache } from '../ai/translator.js';
import { coderTierAlive } from '../ai/translator.js';
import { askOtherLlm } from '../ai/translator.js';
// ESM: this module runs via tsx where __dirname is NOT a global. Derive it
// the same way the other route modules do (e.g. routes/soul.ts).
const __dirname = dirname(fileURLToPath(import.meta.url));
export const llmRoutes = Router();
// backend/src/routes → up 2 = backend/ (llm-config.json lives there — same
// layout translator.ts uses: backend/src/ai → up 2 = backend/).
const LLM_CONFIG_PATH = join(__dirname, '..', '..', 'llm-config.json');
/** The job roles the user can assign a provider/model to. */
export const LLM_ROLES = ['reasoning', 'codeGeneration', 'guiBuild', 'fastChat'];
/** Pretty labels + icons for each role */
const ROLE_META = {
    reasoning: { label: 'Reasoning / Chat', icon: '💬', hint: 'Chat, reasoning panel, planning, and general analysis' },
    codeGeneration: { label: 'Code Handling', icon: '🧩', hint: 'Per-file code generation & repair (delegator / fast coder chain)' },
    guiBuild: { label: 'GUI Build', icon: '🖥', hint: 'GUI builder / app blueprint & mockup synthesis' },
    fastChat: { label: 'Fast Chat', icon: '⚡', hint: 'Casual conversational replies (falls back to reasoning)' },
};
/**
 * GET /api/llm/roles
 * Returns the current role→model assignment map from llm-config.json
 * (top-level "roles"), plus role metadata and which provider keys exist.
 */
llmRoutes.get('/roles', async (_req, res) => {
    let roles = {};
    try {
        const config = JSON.parse(readFileSync(LLM_CONFIG_PATH, 'utf-8'));
        roles = config?.roles ?? {};
    }
    catch {
        // Missing/corrupt config → empty roles (defaults apply).
    }
    res.json({
        roles,
        roleMeta: ROLE_META,
        providers: LLM_ROLES.map((r) => ({ role: r, ...ROLE_META[r], active: Boolean(roles[r]) })),
    });
});
/**
 * POST /api/llm/roles
 * Persist a role→{ provider|baseUrl, model } assignment into llm-config.json's
 * top-level "roles" map, then clear the translator's role cache so the next
 * request honors it. Body: { roles: { [role]: { baseUrl, model, apiKey?, nCtx? } | providerKey } }
 */
llmRoutes.post('/roles', async (req, res) => {
    const incoming = req.body?.roles;
    if (!incoming || typeof incoming !== 'object') {
        return res.status(400).json({ error: 'roles object is required' });
    }
    const allowed = new Set(LLM_ROLES);
    const clean = {};
    for (const [role, entry] of Object.entries(incoming)) {
        if (!allowed.has(role))
            continue;
        // Accept either a provider-key string OR an inline { baseUrl, model } object.
        if (typeof entry === 'string' && entry.trim()) {
            clean[role] = entry.trim();
        }
        else if (entry && typeof entry === 'object') {
            const e = entry;
            if (e.provider && !e.baseUrl) {
                clean[role] = e.provider;
            }
            else if (e.baseUrl && e.model) {
                clean[role] = { baseUrl: e.baseUrl.replace(/\/+$/, ''), model: e.model, apiKey: e.apiKey || 'not-needed', nCtx: e.nCtx };
            }
        }
    }
    try {
        const config = JSON.parse(readFileSync(LLM_CONFIG_PATH, 'utf-8'));
        // REPLACE (not merge): the client sends the COMPLETE role map (each role
        // either assigned or absent), so merging kept stale entries alive when a
        // role was unassigned — "clear all" (roles: {}) did nothing. A client that
        // wants to preserve unlisted roles must send them explicitly.
        config.roles = clean;
        writeFileSync(LLM_CONFIG_PATH, JSON.stringify(config, null, 2) + '\n');
        // Drop the translator's cached role clients so this takes effect now.
        clearRolesRoleCache();
        res.json({ success: true, roles: config.roles });
    }
    catch (err) {
        res.status(500).json({ error: `Failed to persist roles: ${err?.message || err}` });
    }
});
/**
 * GET /api/llm/providers
 * Lists the known provider keys in llm-config.json plus a live reachability
 * check, so the role UI can offer the configured backends as assignable.
 * Returns { error: true } rather than hard-failing if the config is unreadable.
 */
llmRoutes.get('/providers', async (_req, res) => {
    let providers = {};
    try {
        providers = JSON.parse(readFileSync(LLM_CONFIG_PATH, 'utf-8')) || {};
    }
    catch {
        return res.json({ providers: [], modelProviders: [] });
    }
    const knownKeys = Object.keys(providers).filter((k) => typeof providers[k] === 'object' && providers[k] !== null);
    const details = await Promise.all(knownKeys.map(async (k) => {
        const p = providers[k];
        const baseUrl = p?.baseUrl || '';
        let alive = false;
        // coderTierAlive appends /models itself — do NOT add /v1 again (baseUrl
        // already ends in /v1, so appending /v1/models produced /v1/v1/models and
        // every provider looked offline).
        if (baseUrl)
            alive = await coderTierAlive(baseUrl, 2000).catch(() => false);
        return { key: k, baseUrl, model: p?.model || null, alive };
    }));
    res.json({ providers: details });
});
/**
 * Parse `ollama list` output into structured model data.
 *
 * Expected output format (tabular):
 * NAME    ID    SIZE    MODIFIED
 * model1  abc   4.2 GB  2 weeks ago
 */
function parseOllamaList(output) {
    const lines = output.trim().split('\n');
    if (lines.length < 2)
        return []; // Header only or empty
    const models = [];
    // Skip header line
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line)
            continue;
        // Split by 2+ spaces or tabs
        const parts = line.split(/\s{2,}|\t+/);
        if (parts.length < 3)
            continue;
        const name = parts[0].trim();
        // Try to extract quantization from name (e.g., "model:Q4_K_M")
        const quantMatch = name.match(/:([^:]+)$/);
        const quantization = quantMatch ? quantMatch[1] : 'unknown';
        // Parse size string like "4.2 GB", "842 MB"
        const sizeStr = parts[2]?.trim() || '';
        let sizeBytes = 0;
        const sizeNum = parseFloat(sizeStr);
        if (sizeStr.includes('GB'))
            sizeBytes = Math.round(sizeNum * 1e9);
        else if (sizeStr.includes('MB'))
            sizeBytes = Math.round(sizeNum * 1e6);
        else if (sizeStr.includes('KB'))
            sizeBytes = Math.round(sizeNum * 1e3);
        else if (sizeStr.includes('TB'))
            sizeBytes = Math.round(sizeNum * 1e12);
        else if (!isNaN(sizeNum))
            sizeBytes = Math.round(sizeNum);
        const modifiedAt = parts[3]?.trim() || '';
        models.push({
            name,
            size: sizeStr,
            sizeBytes,
            quantization,
            modifiedAt,
        });
    }
    return models;
}
/**
 * GET /api/llm/ollama-scan
 * Runs `ollama list` on the server and returns parsed results.
 */
llmRoutes.get('/ollama-scan', async (_req, res) => {
    try {
        const stdout = execSync('ollama list', {
            encoding: 'utf-8',
            timeout: 10000,
            maxBuffer: 10 * 1024 * 1024,
        });
        const models = parseOllamaList(stdout);
        res.json({
            success: true,
            models,
            count: models.length,
            raw: stdout,
        });
    }
    catch (err) {
        // ollama not installed or not running
        res.status(200).json({
            success: false,
            models: [],
            count: 0,
            error: err.message?.includes('not found')
                ? 'Ollama is not installed or not in PATH'
                : err.message?.includes('timed out')
                    ? 'Ollama list timed out — is the service running?'
                    : `Ollama scan failed: ${err.message}`,
        });
    }
});
/**
 * GET /api/llm/ollama-scan/raw
 * Returns the raw output of `ollama list` for debugging.
 */
llmRoutes.get('/ollama-scan/raw', async (_req, res) => {
    try {
        const stdout = execSync('ollama list', {
            encoding: 'utf-8',
            timeout: 10000,
            maxBuffer: 10 * 1024 * 1024,
        });
        res.type('text/plain').send(stdout);
    }
    catch (err) {
        res.status(500).send(`Error: ${err.message}`);
    }
});
// ─── LLM Proxy Endpoints ──────────────────────────────────────────────────
// These proxy LLM requests through the backend to avoid CORS issues
// when the frontend (localhost:5173) needs to talk to the LLM (localhost:11434).
/**
 * GET /api/llm/proxy/models
 * Proxies a request to the LLM provider's /v1/models endpoint.
 * Query params: url (optional, defaults to Ollama)
 */
llmRoutes.get('/proxy/models', async (req, res) => {
    const targetUrl = req.query.url || 'http://192.168.1.234:11434/v1/models';
    try {
        const response = await fetch(targetUrl, {
            signal: AbortSignal.timeout(10000),
            headers: { 'Accept': 'application/json' },
        });
        const data = await response.json();
        res.json(data);
    }
    catch (err) {
        res.status(502).json({
            error: `LLM proxy request failed: ${err.message}`,
            data: [],
        });
    }
});
/**
 * Read a short intro from VACA_Speech.txt to use as a canned response
 * when the user asks about VACA, avoiding LLM hallucination.
 */
function _getVacaIntro() {
    try {
        const homeDir = process.env.HOME || '/home/final-flash1';
        const speechPath = join(homeDir, 'Desktop', 'VACA_Speech.txt');
        const content = readFileSync(speechPath, 'utf-8');
        // Extract just the introduction section (first ~800 chars)
        const introMatch = content.match(/SECTION 1: INTRODUCTION[\s\S]*?(?=SECTION 2:|$)/);
        if (introMatch) {
            // Clean up: remove box-drawing, = lines, normalize
            let intro = introMatch[0]
                .replace(/[\u{2500}-\u{259F}]/gu, '')
                .replace(/^[=\-]{2,}\n?/gm, '')
                .replace(/\n{3,}/g, '\n\n')
                .trim();
            // Truncate to reasonable length
            intro = intro.length > 1500 ? intro.slice(0, 1500) + '...' : intro;
            return intro;
        }
    }
    catch { }
    return 'VACA is the AI Code Architect platform (assistant: Veronica). I am an AI-powered software development platform that builds complete applications from visual flowcharts. I use a custom-built recurrent neural network called Venorica to learn from code patterns and generate better code with every project.';
}
/**
 * POST /api/llm/proxy/chat
 * Proxies a chat completion request to the LLM provider.
 * Intercepts "about VACA" queries to prevent LLM hallucination of fictional personas.
 * Body: { url?, model, messages, max_tokens?, stream?, ... }
 */
llmRoutes.post('/proxy/chat', async (req, res) => {
    const { url, model, messages, ...rest } = req.body;
    if (!messages || !model) {
        return res.status(400).json({ error: 'model and messages are required' });
    }
    // Check if the last user message is asking about VACA
    // (uses the shared detection function from voice-action.ts)
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUserMsg && isAboutVacaRequest(lastUserMsg.content || '')) {
        // Return a pre-defined response about VACA instead of proxying to the LLM
        console.log('[LLM Proxy] Intercepted "about VACA" query — returning canned response instead of proxying to LLM');
        res.json({
            id: 'chatcmpl-vaca-intro',
            object: 'chat.completion',
            created: Math.floor(Date.now() / 1000),
            model: model,
            choices: [{
                    index: 0,
                    message: {
                        role: 'assistant',
                        content: _getVacaIntro(),
                    },
                    finish_reason: 'stop',
                }],
            usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
        });
        return;
    }
    const targetUrl = url || 'http://192.168.1.234:11434/v1/chat/completions';
    try {
        const response = await fetch(targetUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify({ model, messages, ...rest }),
            signal: AbortSignal.timeout(60000),
        });
        const data = await response.json();
        res.json(data);
    }
    catch (err) {
        res.status(502).json({
            error: `LLM proxy chat request failed: ${err.message}`,
        });
    }
});
/**
 * POST /api/llm/relay
 * Relay a mid-build question from one band LLM to the OTHER LLM. This is the
 * "phone line" between the two voices: the asker's question is sent to the
 * answering role's configured client+model (with the band-chart relay system
 * prompt, so it knows it is answering a fellow band member mid-build), and the
 * reply is returned so the asker's chunk can incorporate it.
 * Body: { question, fromRole?, toRole?, context?, maxTokens? }
 *   - question  (required) the direct question one LLM asks the other
 *   - fromRole  which role is asking (default 'codeGeneration' — the writer)
 *   - toRole    which role should answer (default 'reasoning' — the 2nd voice)
 *   - context   optional work-so-far summary / file contents to ground the answer
 */
llmRoutes.post('/relay', async (req, res) => {
    const { question, fromRole, toRole, context, maxTokens } = req.body ?? {};
    if (!question || typeof question !== 'string') {
        return res.status(400).json({ error: 'question (string) is required' });
    }
    try {
        const answer = await askOtherLlm(String(question), {
            toRole: toRole || undefined,
            fromRole: fromRole || undefined,
            context: typeof context === 'string' ? context : undefined,
            maxTokens: typeof maxTokens === 'number' ? maxTokens : undefined,
        });
        res.json({ answer, toRole: toRole ?? 'reasoning', fromRole: fromRole ?? 'codeGeneration' });
    }
    catch (err) {
        res.status(502).json({
            error: `LLM relay failed: ${err.message}`,
        });
    }
});
/**
 * POST /api/llm/proxy/scan-provider
 * Pings a specific provider URL to check if it's reachable.
 * Body: { url }
 */
llmRoutes.post('/proxy/scan-provider', async (req, res) => {
    const { url } = req.body;
    if (!url) {
        return res.status(400).json({ error: 'url is required' });
    }
    const start = performance.now();
    try {
        const response = await fetch(url, {
            signal: AbortSignal.timeout(5000),
            headers: { 'Accept': 'application/json' },
        });
        const ms = Math.round(performance.now() - start);
        if (response.ok) {
            let firstModel = null;
            try {
                const data = await response.json();
                if (data?.data?.length > 0 && data.data[0]?.id) {
                    firstModel = data.data[0].id;
                }
            }
            catch { }
            res.json({ reachable: true, latencyMs: ms, firstModel });
        }
        else if (response.status === 401 || response.status === 403) {
            res.json({ reachable: true, latencyMs: ms, error: 'Auth required' });
        }
        else if (response.status === 404) {
            res.json({ reachable: true, latencyMs: ms, error: 'Non-standard API' });
        }
        else {
            res.json({ reachable: false, latencyMs: null, error: `HTTP ${response.status}` });
        }
    }
    catch (err) {
        res.json({ reachable: false, latencyMs: null, error: err.message || 'No response' });
    }
});
/**
 * True if the DSpark launcher's pid file references a live process.
 * Used to distinguish "server is still loading its model" (pid alive, port
 * not bound yet) from "server is fully down".
 */
function isDSparkPidAlive() {
    try {
        const pidFile = join(__dirname, '..', '..', '..', 'scripts', 'dspark.pid');
        const pid = parseInt(readFileSync(pidFile, 'utf-8').trim(), 10);
        if (!Number.isFinite(pid) || pid <= 0)
            return false;
        process.kill(pid, 0); // signal 0 = existence/permission check
        return true;
    }
    catch (err) {
        // EPERM means the process exists but we lack permission — still alive.
        return err?.code === 'EPERM';
    }
}
/**
 * Read DSPARK_TARGET (scripts/dspark-target.env) + stat the GGUF to expose
 * the deployed model's real file facts — so the LLM can answer truthfully
 * about its own size instead of guessing.
 */
function _getDSparkModelFileFacts() {
    try {
        const envPath = join(__dirname, '..', '..', '..', 'scripts', 'dspark-target.env');
        const env = readFileSync(envPath, 'utf-8');
        const m = env.match(/DSPARK_TARGET=([^\s]+)/);
        if (!m)
            return { modelFile: null, modelFileSizeGb: null, modelFileSizeMiB: null };
        const target = m[1].trim();
        const modelFile = target.split('/').pop() || target;
        try {
            const stat = statSync(target);
            const bytes = stat.size;
            return {
                modelFile,
                modelFileSizeGb: Math.round((bytes / 1073741824) * 100) / 100,
                modelFileSizeMiB: Math.round(bytes / 1048576),
            };
        }
        catch {
            return { modelFile, modelFileSizeGb: null, modelFileSizeMiB: null };
        }
    }
    catch {
        return { modelFile: null, modelFileSizeGb: null, modelFileSizeMiB: null };
    }
}
/**
 * GPU VRAM in use by this machine's dspark process (via nvidia-smi compute
 * apps filtered by python3 + llama), plus the GPU inventory. Graceful nulls.
 */
function _getGpuFacts() {
    try {
        const out = execSync('nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader,nounits', { encoding: 'utf-8', timeout: 8000 });
        const lines = out.trim().split('\n').filter(Boolean);
        let used = 0, total = 0;
        const gpus = lines.map(l => {
            const [idx, name, usedS, totalS] = l.split(',').map(s => s.trim());
            used += parseInt(usedS, 10) || 0;
            total += parseInt(totalS, 10) || 0;
            return { index: idx, name };
        });
        return {
            vramUsedMiB: used || null,
            vramTotalMiB: total || null,
            gpus: gpus.length ? gpus : null,
        };
    }
    catch {
        return { vramUsedMiB: null, vramTotalMiB: null, gpus: null };
    }
}
/**
 * GET /api/llm/dspark-status
 * Live status of the DSpark GGUF server (OpenAI-compatible, port 8000):
 *   running  — /v1/health responded OK (includes draft_mode + model)
 *   loading  — pid file alive but health not responding (model still loading)
 *   offline  — nothing on the port and no live pid
 * Includes the deployed model's file facts + GPU VRAM (truthful self-knowledge
 * for the LLM's system prompt).
 */
llmRoutes.get('/dspark-status', async (_req, res) => {
    const port = process.env.DSPARK_PORT || '8000';
    const healthUrl = `http://127.0.0.1:${port}/v1/health`;
    const start = performance.now();
    const fileFacts = _getDSparkModelFileFacts();
    const gpuFacts = _getGpuFacts();
    try {
        const response = await fetch(healthUrl, { signal: AbortSignal.timeout(5000) });
        if (response.ok) {
            const data = await response.json();
            const latencyMs = Math.round(performance.now() - start);
            const stats = data?.stats ?? {};
            res.json({
                running: true,
                loading: false,
                draftMode: data?.draft_mode ?? null,
                model: data?.model ?? null,
                speculativeDecoding: !!data?.speculative_decoding,
                tokensPerSec: stats.tokens_per_sec ?? null,
                avgLatencyMs: stats.avg_latency_ms ?? null,
                totalCompletionTokens: stats.total_completion_tokens ?? 0,
                totalRequests: stats.requests ?? 0,
                latencyMs,
                port,
                ...fileFacts,
                ...gpuFacts,
            });
            return;
        }
    }
    catch {
        // fall through to pid check below
    }
    // Health not responding — is the process still loading its model?
    const pidAlive = isDSparkPidAlive();
    res.json({
        running: false,
        loading: pidAlive,
        draftMode: null,
        model: null,
        speculativeDecoding: false,
        latencyMs: null,
        port,
        ...fileFacts,
        ...gpuFacts,
        hint: pidAlive
            ? 'DSpark is starting — the model takes ~30–60s to load'
            : 'DSpark is not running (it autostarts with the backend)',
    });
});
/**
 * GET /api/llm/dspark-benchmark
 * Serves the tuned-vs-stock benchmark report written by scripts/benchmark-dspark.py
 * (data/benchmark-dspark.json): tuned tok/s, stock control tok/s, and the
 * draft-mode verification verdict for the tuned GGUF.
 * Returns { exists: false } when no benchmark has run yet.
 */
llmRoutes.get('/dspark-benchmark', async (_req, res) => {
    const reportPath = join(__dirname, '..', '..', '..', 'data', 'benchmark-dspark.json');
    try {
        const raw = JSON.parse(readFileSync(reportPath, 'utf-8'));
        const steps = raw?.steps ?? {};
        const tuned = steps.tuned_benchmark ?? {};
        const stock = steps.stock_benchmark ?? {};
        const draft = steps.draft_mode ?? {};
        res.json({
            exists: true,
            timestamp: raw?.timestamp ?? null,
            steps: {
                beforeDeployHistorical: steps.before_deploy_historical ?? null,
                tunedTps: tuned.client_tps_mean ?? null,
                tunedServerTps: tuned.health_stats?.tokens_per_sec ?? null,
                stockTps: stock.client_tps_mean ?? null,
                stockServerTps: stock.health_stats?.tokens_per_sec ?? null,
                stockError: stock.error ?? null,
                draftOk: draft.ok ?? null,
                draftMode: draft.health?.draft_mode ?? null,
                draftSpeculative: draft.health?.speculative_decoding ?? null,
                draftTps: draft.generation?.client_tps_mean ?? null,
                finalModel: steps.final_health?.model ?? null,
            },
        });
    }
    catch {
        res.json({ exists: false });
    }
});
/**
 * POST /api/llm/proxy/verify-model
 * Verifies a model by sending a tiny chat completion.
 * Body: { url, model }
 */
llmRoutes.post('/proxy/verify-model', async (req, res) => {
    const { url, model } = req.body;
    if (!url || !model) {
        return res.status(400).json({ error: 'url and model are required' });
    }
    const chatUrl = url.replace(/\/+$/, '') + '/v1/chat/completions';
    const start = performance.now();
    try {
        const response = await fetch(chatUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model,
                messages: [{ role: 'user', content: 'OK' }],
                max_tokens: 2,
                stream: false,
            }),
            signal: AbortSignal.timeout(10000),
        });
        const ms = Math.round(performance.now() - start);
        if (response.ok) {
            res.json({ success: true, latencyMs: ms });
        }
        else {
            const body = await response.text().catch(() => '');
            res.json({ success: false, latencyMs: ms, error: `HTTP ${response.status}: ${body.slice(0, 200)}` });
        }
    }
    catch (err) {
        res.json({ success: false, latencyMs: null, error: err.message || 'Connection failed' });
    }
});
