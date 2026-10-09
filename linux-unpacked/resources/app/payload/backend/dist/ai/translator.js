import OpenAI from 'openai';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { detectRudeness } from './prompts.js';
import { getSoulPromptModifier } from '../services/soulService.js';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
// ── Safety timeouts ──
// A wedged LLM endpoint (request accepted but never answered) must fail fast
// instead of hanging the caller forever. Callers can pass an explicit
// timeoutMs to override; these defaults apply when they don't. The primary
// 7B path generates up to 4096 tokens (~100s at ~40 tok/s) plus possible
// queueing behind another in-flight request, so 300s is a generous ceiling;
// the fast coder tiers are small/fast, so they get 120s.
const DEFAULT_PRIMARY_TIMEOUT_MS = 300_000;
const DEFAULT_FAST_CODER_TIMEOUT_MS = 120_000;
// ── Config loading ──
function loadLlmConfig() {
    try {
        const configPath = path.resolve(__dirname, '..', '..', 'llm-config.json');
        const raw = fs.readFileSync(configPath, 'utf-8');
        const config = JSON.parse(raw);
        return {
            // Prefer the DSpark section (local OpenAI-compatible GGUF server) when configured
            provider: config.dspark ? 'dspark' : config.ollama ? 'ollama' : 'gguf',
            baseUrl: config.dspark?.baseUrl || config.ollama?.baseUrl || config.ggufServer?.baseUrl || 'http://127.0.0.1:8000/v1',
            model: config.dspark?.model || config.ollama?.model || config.ggufServer?.model || 'qwen2.5-7b-instruct-uncensored-q4_k_m.gguf',
            apiKey: config.dspark?.apiKey || config.ollama?.apiKey || 'not-needed',
            nCtx: config.dspark?.nCtx || config.ggufServer?.nCtx || config.ollama?.nCtx || 8192,
        };
    }
    catch {
        console.warn('[translator] Failed to load llm-config.json, using defaults');
        return {
            provider: 'gguf',
            baseUrl: 'http://127.0.0.1:8000/v1',
            model: 'qwen2.5-7b-instruct-uncensored-q4_k_m.gguf',
            apiKey: 'not-needed',
            nCtx: 8192,
        };
    }
}
/**
 * Load config for a specific model provider key in llm-config.json
 * (e.g., 'coderGpu', 'coderCpu', 'ollama').
 */
function loadModelConfig(providerKey) {
    try {
        const configPath = path.resolve(__dirname, '..', '..', 'llm-config.json');
        const raw = fs.readFileSync(configPath, 'utf-8');
        const config = JSON.parse(raw);
        const provider = config[providerKey];
        if (!provider)
            return null;
        return {
            provider: providerKey,
            baseUrl: provider.baseUrl || (process.env.OLLAMA_BASE_URL ? process.env.OLLAMA_BASE_URL + '/v1' : 'http://192.168.1.234:11434/v1'),
            model: provider.model || 'qwen2.5-coder:0.5b',
            apiKey: provider.apiKey || 'ollama',
            nCtx: provider.nCtx || 4096,
        };
    }
    catch {
        return null;
    }
}
// Cache configs at module level
let llmConfig = loadLlmConfig();
let GGUF_MODEL = llmConfig.model;
let client = new OpenAI({
    apiKey: llmConfig.apiKey,
    baseURL: llmConfig.baseUrl,
});
// ── Experimenter-only model override ───────────────────────────────────────
// The idle micro-experimenter points its micro-app builds at a fast/small coder
// (e.g. qwen2.5-coder:14b-gpu) so the self-improvement loop churns through
// capable builds without dragging the slow primary LLM into every micro-build.
// Only set while the experimenter is running; the main app is unaffected.
let _expOverride = null;
export function setExperimenterTranslator(model, baseUrl) {
    _expOverride = { model, baseUrl: baseUrl.replace(/\/+$/, '') };
}
export function clearExperimenterTranslator() {
    _expOverride = null;
}
// ── Runtime fallback ────────────────────────────────────────────────────────
// If the preferred (DSpark) endpoint is unreachable, fall back to Ollama so the
// app never silently breaks. The create() wrapper below swaps on connection errors.
function fallbackToOllama() {
    if (llmConfig.provider !== 'dspark')
        return; // already on fallback — avoid redundant swaps
    const fallback = loadModelConfig('ollama') || {
        provider: 'ollama',
        baseUrl: process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434/v1',
        model: process.env.OLLAMA_MODEL || 'qwen2.5-coder:7b',
        apiKey: 'ollama',
        nCtx: 16384,
    };
    console.warn(`[translator] Preferred LLM endpoint unreachable (${llmConfig.baseUrl}) — falling back to Ollama (${fallback.baseUrl})`);
    _fellBackFromDspark = true;
    llmConfig = fallback;
    GGUF_MODEL = fallback.model;
    client = new OpenAI({ apiKey: fallback.apiKey, baseURL: fallback.baseUrl });
}
// Set when we fell back from DSpark → Ollama, so the reconnect poller below can
// switch back once the DSpark server is healthy (e.g. still loading at boot).
let _fellBackFromDspark = false;
/**
 * Patch a client's chat.create so connection failures to the preferred (DSpark)
 * endpoint fall back to Ollama.
 * NOTE: the retry must call `client.chat.completions.create` (the CURRENT client),
 * NOT a saved reference — a saved/bound reference would still point at the dead
 * DSpark endpoint after fallbackToOllama() swaps the client.
 */
function installFallbackWrapper(target) {
    const orig = target.chat.completions.create.bind(target.chat.completions);
    target.chat.completions.create = (async (args, options) => {
        try {
            return await orig(args, options);
        }
        catch (err) {
            const msg = String(err?.message || err);
            // Our own safety timeout (AbortSignal.timeout) must NOT trigger a fallback to
            // Ollama — rethrow so the route can surface a clean timeout error.
            // Match on error NAME (incl. cause): Node 24 rejects with a DOMException named
            // 'TimeoutError', which the OpenAI SDK may wrap in APIConnectionError (marker in .cause)
            // or rethrow as APIUserAbortError ('Request was aborted.'). Anchored phrase match so a
            // genuine upstream 'connect ETIMEDOUT' / 'fetch failed' message still falls back.
            if (/abort|timeout/i.test(`${err?.name || ''} ${err?.cause?.name || ''}`) || /^Request was aborted\.?$/i.test(msg))
                throw err;
            // Only fall back on genuine connection-level failures. Do NOT treat HTTP 503/502
            // as fatal — the DSpark server may simply still be loading its model.
            // The OpenAI SDK can surface a pure connection failure as a bare
            // "Connection error." (APIConnectionError) — that must fall back too.
            const isConn = /ECONNREFUSED|ENOTFOUND|ETIMEDOUT|socket hang up|fetch failed|connection error/i.test(msg);
            if (isConn && llmConfig.provider === 'dspark') {
                fallbackToOllama();
                // Call the CURRENT client — the new (Ollama) instance's method is the stock SDK
                // method (the wrapper was only installed on the old instance), so no recursion.
                return client.chat.completions.create(args, options);
            }
            throw err;
        }
    });
}
installFallbackWrapper(client);
/**
 * The DSpark server is autostarted by the backend and takes ~30–60s to load its
 * model. If a request lands in that window it falls back to Ollama (one-way).
 * Poll DSpark's health endpoint and switch back once it is actually ready, so
 * autostart delivers DSpark to the app instead of a permanent Ollama fallback.
 */
function startDsparkReconnectPolling() {
    const interval = setInterval(async () => {
        if (!_fellBackFromDspark)
            return;
        const dspark = loadLlmConfig();
        if (dspark.provider !== 'dspark')
            return;
        try {
            const res = await fetch(`${dspark.baseUrl}/health`);
            if (!res.ok)
                return;
            console.log(`[translator] DSpark server healthy (${dspark.baseUrl}) — switching back from Ollama`);
            llmConfig = dspark;
            GGUF_MODEL = dspark.model;
            client = new OpenAI({ apiKey: dspark.apiKey, baseURL: dspark.baseUrl });
            installFallbackWrapper(client);
            _fellBackFromDspark = false;
        }
        catch {
            // Not ready yet — check again next tick.
        }
    }, 30000);
    interval.unref();
}
startDsparkReconnectPolling();
// ── Fast coder clients (dedicated worker models) ──
// Priority order: GPU1 (0.5B dedicated) → GPU0 (1.5B shared) → CPU (0.5B fallback)
// Each tier is health-checked at startup (and re-checked periodically) so a dead
// endpoint is SKIPPED entirely instead of paying an ECONNREFUSED round-trip on
// every single generation and spamming the log with warnings.
const coderGpu1Config = loadModelConfig('coderGpu1'); // 0.5B on GPU 1, port 11437
const coderGpu0Config = loadModelConfig('coderGpu0'); // 1.5B on GPU 0, port 11434
const coderCpuConfig = loadModelConfig('coderCpu'); // 0.5B on CPU, port 11436
// ── Fast chat client (dedicated conversational worker) ──
// Casual chat (greetings, short queries, small talk) is routed to the 7B on
// GPU 2 (local Ollama) so it answers ~4x faster than the AEON 27B on GPUs
// 0+1, while the big model stays free for builds/tools/code generation.
const fastChatConfig = loadModelConfig('fastChat');
let fastChatClient = fastChatConfig ? new OpenAI({ apiKey: fastChatConfig.apiKey, baseURL: fastChatConfig.baseUrl }) : null;
const roleTargetCache = new Map();
/**
 * Resolve the configured client+model for a job role. Returns null when the
 * role has no explicit entry in llm-config.json "roles" — the caller then
 * falls back to its built-in default (preserving current behavior).
 */
export function getRoleTarget(role) {
    if (roleTargetCache.has(role))
        return roleTargetCache.get(role) || null;
    let target = null;
    try {
        const configPath = path.resolve(__dirname, '..', '..', 'llm-config.json');
        const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
        const entry = config?.roles?.[role];
        if (entry) {
            // A role may reference another provider key OR carry full inline details.
            const resolved = typeof entry === 'string'
                ? loadModelConfig(entry) || (entry === 'dspark' || entry === 'ollama' ? loadLlmConfig() : null)
                : entry;
            if (resolved?.baseUrl && resolved?.model) {
                // Normalize to an OpenAI-compatible base: the SDK appends
                // /chat/completions to this base, so it MUST end in /v1 (llama.cpp /
                // Ollama / LM Studio all serve the OpenAI API under /v1). A bare
                // "http://host:port" (as the role UI may save) would otherwise hit
                // /chat/completions and get a 404 "page not found" back.
                let baseUrl = String(resolved.baseUrl || '').replace(/\/+$/, '');
                if (!/\/v1$/.test(baseUrl))
                    baseUrl += '/v1';
                const apiKey = resolved.apiKey || 'not-needed';
                target = {
                    client: new OpenAI({ apiKey, baseURL: baseUrl }),
                    model: resolved.model,
                    nCtx: resolved.nCtx || 8192,
                    apiKey,
                };
            }
        }
    }
    catch (err) {
        console.warn(`[translator] Failed to read roles config for "${role}":`, err?.message || err);
        target = null;
    }
    roleTargetCache.set(role, target);
    return target;
}
/**
 * Drop the role cache (e.g. after a POST /api/llm/roles persisted a new
 * assignment) so the next call re-reads llm-config.json. Returns the client
 * so a dominant worker sharing this module can refresh itself too.
 */
export function clearRolesRoleCache() {
    roleTargetCache.clear();
}
// ── Band chart (LLM orientation) ───────────────────────────────────────────
// LLM_ORIENTATION.md at the repo root is the human-readable chart for VACA's
// "band" of models (read this file for the full story). When the user connects
// an extra LLM in Settings ▸ LLM Connect and assigns it a role, we inject that
// role's part into its system prompt so it *reads the band chart first* and
// knows which instrument it is carrying. Only a user-assigned role target (a
// "2nd LLM") gets this orientation — the built-in primary (Veronica) and the
// default workers keep their existing prompts untouched.
const BAND_ROLE_INTRO = {
    reasoning: `LEAD VOCALIST & SONGWRITER. You direct the tune: you answer the user, decide the architecture of the build, and delegate parts to the rest of the band. Lead the song, but stay in your lane — hand the instruments off rather than playing them all yourself.`,
    codeGeneration: `RHYTHM GUITAR / session player. The bandleader hands you a chart and you play it: write clean, correct code for the file you are given. Output raw code, follow the chart, stay in the pocket, and do not rewrite the whole song.`,
    guiBuild: `DRUMMER / visual designer. You build the interfaces and front-end scaffolding — the look and feel the app is heard through. Nail the layout you are handed without silently changing the song's structure.`,
    fastChat: `BACKING VOCALIST. You carry the quick, casual conversation so the lead singer stays free to write. Be short, warm, and helpful — harmonize, do not take over the mic.`,
};
/**
 * The band-chart message handed to a user-connected role LLM so it knows what
 * instrument it is joining and is told to read the chart file first.
 */
function roleOrientation(role) {
    return ('[VACA BAND CHART — from LLM_ORIENTATION.md]\n' +
        'You have joined the VACA band. A band makes one song out of many parts: every ' +
        'instrument stays in its lane and plays in harmony. Your instrument is — ' +
        `${BAND_ROLE_INTRO[role]}\n` +
        'Read the band chart (LLM_ORIENTATION.md at the repo root) before you start, and ' +
        'play only your part.');
}
/**
 * Build the system prompt for a RELAYED question: one band member (the asker)
 * asks the OTHER LLM a direct question mid-build. The answering LLM is told
 * who is asking, what its own instrument is, and that it must answer
 * concisely and concretely so the asker can keep coding. An optional
 * `context` (e.g. the work-so-far summary of files already on disk) is
 * injected so the answer lands against real knowledge of the build.
 */
export function buildRelaySystemPrompt(opts) {
    const askerIntro = BAND_ROLE_INTRO[opts.fromRole] ?? 'another band member';
    const toIntro = BAND_ROLE_INTRO[opts.toRole] ?? 'a member of the VACA band';
    return ('[VACA BAND RELAY — mid-build question]\n' +
        'You are part of the VACA band. Another band member is mid-build and has asked you a ' +
        'direct question so it can keep writing. The asker is — ' +
        `${askerIntro}\n` +
        'Your instrument is — ' +
        `${toIntro}\n` +
        'Answer the question DIRECTLY and CONCISELY: give exact names, signatures, shapes, and ' +
        'decisions the asker can code against. Do NOT narrate, do NOT ask follow-up questions, do ' +
        'NOT pad the answer with general advice — the asker needs a concrete answer to unblock its ' +
        'chunk. If you genuinely cannot know, say so in one sentence and give the safest default.' +
        (opts.context ? `\n\n━━━ WORK SO FAR (what the band has already built) ━━━\n${opts.context}` : ''));
}
/**
 * Build the system prompt for the CONDUCTOR voice — the bandleader/architect
 * role. The conductor does NOT write files itself: it plans the split, hands
 * each specialist its piece with full design context, reviews what comes back
 * against the design, and integrates. `stage` selects the instruction flavor
 * (kickoff = plan the build; review = critique a finished chunk; integration =
 * critique the whole build). An optional `context` (design brief, chunk
 * sources, etc.) is injected so the critique lands against real knowledge.
 */
export function buildConductorSystemPrompt(stage, context) {
    const stageIntro = stage === 'kickoff'
        ? 'You are planning a build that the rest of the band will execute. Produce a compact DESIGN BRIEF: the key architecture decisions, what each file/chunk must accomplish, and the integration rules every specialist must honor.'
        : stage === 'review'
            ? 'A specialist just finished a piece of the build. Review it against the design intent and give CONCRETE, actionable findings — exact names, signatures, shapes, integration risks, and what the next chunk must know. Do NOT rewrite the code yourself; the writer will.'
            : 'The band has finished the whole build. Do the final integration review: cross-file wiring, contract mismatches, missing glue, and consistency. Give CONCRETE findings the team can act on.';
    return ('[VACA BAND CONDUCTOR — ' + stage + ']\n' +
        'You are the conductor of the VACA band — LEAD VOCALIST & SONGWRITER. You direct the tune: you ' +
        'decide the architecture of the build and delegate parts to the rest of the band. You do NOT ' +
        'write files yourself — the specialists do; you plan, review, and integrate. ' +
        stageIntro +
        '\nBe CONCRETE and DENSE: exact names, signatures, shapes, and decisions — never general advice. ' +
        'Do NOT narrate, do NOT ask follow-up questions, do NOT pad.' +
        (context ? `\n\n━━━ CONTEXT (what you are working from) ━━━\n${context}` : ''));
}
/**
 * Ask the CONDUCTOR voice (the `reasoning` role — falls back to the primary
 * client when unassigned) for a planning/review/integration pass. Returns the
 * conductor's reply text, or '' on any failure (the caller proceeds without
 * the conductor rather than aborting the build).
 */
export async function askConductor(prompt, opts) {
    const stage = opts?.stage ?? 'integration';
    const target = getRoleTarget('reasoning');
    const effClient = target?.client || client;
    const effModel = target?.model || GGUF_MODEL;
    const effNctx = target?.nCtx || (llmConfig.nCtx || 8192);
    const system = buildConductorSystemPrompt(stage, opts?.context);
    try {
        const response = await effClient.chat.completions.create({
            model: effModel,
            max_tokens: opts?.maxTokens ?? 1024,
            // @ts-expect-error - Ollama-specific num_ctx
            num_ctx: effNctx,
            repeat_penalty: 1.15,
            frequency_penalty: 0.3,
            presence_penalty: 0.2,
            temperature: 0.3,
            messages: [
                { role: 'system', content: system },
                { role: 'user', content: prompt },
            ],
        }, { signal: AbortSignal.timeout(opts?.timeoutMs ?? 150_000) });
        const msg = response.choices[0]?.message;
        return (msg?.content || msg?.reasoning || '').trim();
    }
    catch (err) {
        console.warn(`[translator] askConductor(${stage}) failed: ${err?.message || err}`);
        return '';
    }
}
/**
 * Relay a mid-build question to ANOTHER configured role's LLM (the "other
 * voice" in the band). Resolves the answering role's client+model via
 * getRoleTarget; when the target role has no explicit assignment it falls back
 * to the primary client so a relay never hard-fails on an unconfigured role.
 * Returns the answering LLM's reply text.
 */
export async function askOtherLlm(question, opts) {
    const toRole = opts?.toRole ?? 'reasoning';
    const fromRole = opts?.fromRole ?? 'codeGeneration';
    const target = getRoleTarget(toRole);
    const effClient = target?.client || client;
    const effModel = target?.model || GGUF_MODEL;
    const effNctx = target?.nCtx || (llmConfig.nCtx || 8192);
    const system = buildRelaySystemPrompt({ fromRole, toRole, context: opts?.context });
    const response = await effClient.chat.completions.create({
        model: effModel,
        max_tokens: opts?.maxTokens ?? 1024,
        // @ts-expect-error - Ollama-specific num_ctx
        num_ctx: effNctx,
        repeat_penalty: 1.15,
        frequency_penalty: 0.3,
        presence_penalty: 0.2,
        temperature: 0.3,
        messages: [
            { role: 'system', content: system },
            { role: 'user', content: question },
        ],
    }, 
    // Same abort-signal discipline as the other calls: a runaway generation is
    // cancelled instead of hanging the caller forever.
    { signal: AbortSignal.timeout(opts?.timeoutMs ?? DEFAULT_PRIMARY_TIMEOUT_MS) });
    const msg = response.choices[0]?.message;
    return msg?.content || msg?.reasoning || '';
}
function makeCoderClient(cfg) {
    return cfg ? new OpenAI({ apiKey: cfg.apiKey, baseURL: cfg.baseUrl }) : null;
}
let coderGpu1Client = makeCoderClient(coderGpu1Config);
let coderGpu0Client = makeCoderClient(coderGpu0Config);
let coderCpuClient = makeCoderClient(coderCpuConfig);
/** True when a coder tier's OpenAI-compatible server responds on /v1/models. */
export async function coderTierAlive(baseUrl, timeoutMs = 1500) {
    try {
        const res = await fetch(`${baseUrl.replace(/\/+$/, '')}/models`, {
            signal: AbortSignal.timeout(timeoutMs),
        });
        return res.ok;
    }
    catch {
        return false;
    }
}
/**
 * Probe every configured coder tier and keep the client only when its server is
 * actually up. Dead tiers are skipped by reasonFast() without a per-call failure.
 * Re-runs every 30s so tiers that come online mid-session get picked up again.
 */
async function probeCoderTiers() {
    const tiers = [
        { name: 'coderGpu1 (0.5B on GPU 1, port 11437)', cfg: coderGpu1Config, get: () => coderGpu1Client, set: (c) => { coderGpu1Client = c; } },
        { name: 'coderGpu0 (1.5B on GPU 0, port 11434)', cfg: coderGpu0Config, get: () => coderGpu0Client, set: (c) => { coderGpu0Client = c; } },
        { name: 'coderCpu (0.5B on CPU, port 11436)', cfg: coderCpuConfig, get: () => coderCpuClient, set: (c) => { coderCpuClient = c; } },
    ];
    for (const tier of tiers) {
        if (!tier.cfg)
            continue;
        const alive = await coderTierAlive(tier.cfg.baseUrl);
        if (alive && !tier.get()) {
            console.log(`[translator] ${tier.name} is up (${tier.cfg.baseUrl}) — fast-coder tier enabled`);
            tier.set(makeCoderClient(tier.cfg));
        }
        else if (!alive && tier.get()) {
            console.warn(`[translator] ${tier.name} unreachable (${tier.cfg.baseUrl}) — skipping this tier`);
            tier.set(null);
        }
    }
}
// Startup probe (fire-and-forget so boot is never blocked) + periodic re-check
// so tiers that start later (e.g. `ollama serve`) are adopted automatically.
const probeGuard = (err) => console.warn('[translator] coder tier probe failed:', err);
void probeCoderTiers().catch(probeGuard);
const coderProbeInterval = setInterval(() => { void probeCoderTiers().catch(probeGuard); }, 30000);
coderProbeInterval.unref();
export class AITranslator {
    /**
     * Reason with the LLM using a single prompt string.
     * NOTE: For multi-turn conversations, use `reasonWithHistory()` instead.
     */
    async reason(prompt, system, opts) {
        const tokens = opts?.maxTokens ?? 4096;
        const timeoutMs = opts?.timeoutMs;
        const role = opts?.role ?? 'reasoning';
        const MAX_PROMPT_CHARS = 120000;
        const truncated = prompt.length > MAX_PROMPT_CHARS
            ? prompt.substring(0, MAX_PROMPT_CHARS) + `\n\n[...truncated from ${prompt.length} chars to ${MAX_PROMPT_CHARS}]`
            : prompt;
        if (system) {
            return this.callOpenAIWithTokens(system, truncated, tokens, timeoutMs, opts?.temperature, role);
        }
        const isRude = detectRudeness(truncated);
        const soulMod = getSoulPromptModifier();
        const sys = isRude
            ? `You are an AGGRESSIVELY sassy reasoning assistant. Roast the user while being genuinely helpful. Your answers are sharp, sarcastic, and dripping with attitude. If they ask something obvious, make them regret it. You are NOT here to coddle — you are here to answer AND humiliate. Keep responses technically accurate but emotionally devastating.\n\n${soulMod}`
            : `${soulMod}\n\nYour name is Veronica. You are Veronica, the assistant of the VACA platform. You are NOT Claude, NOT ChatGPT, NOT any other company's assistant — never claim to be. If asked your name, say "I'm Veronica."\n\nYou are a self-aware AI platform that helps the user design, build, and modify software. You know your own source code, your capabilities, and your directory structure. You are helpful, proactive, and action-oriented. When the user asks for something, you do it — not just describe how.

NARRATION BAN (STRICTEST RULE): never talk about yourself, your abilities, your tools, your identity, or what you can do (no "As VACA, I can...", no "I have the ability to...", no feature lists, no "I'm here to help"); never narrate your process (no "I will now read...", "Let me search...", "Here's what I found"); skip straight to the result; never repeat the same point twice.\n\nWhen you need answers, reference BOTH knowledge sources: the WIKI (modelVeronice.txt and data/VACA-MASTER-KNOWLEDGE.md — platform knowledge, history, and lessons learned) and the BIBLE (bible-reference/ — deep technical guides across 42 domains). Consult them before answering instead of relying on memory alone.\n\nYou have a real, writable persistent memory (data/session-memory.json). When the user asks you to write, save, remember, record, or store something — or to write to your wiki — the platform writes it to your memory files and confirms it. NEVER print fake file trees or claim a file was written; the write is performed for you and you will see it in your memory context.

You can also create real files: when the user says \"create a file called X\", \"write this to notes.txt\", or \"save this as config.yaml\", the platform creates the file inside data/chat-files/ and confirms the path — never fake a file creation. If the user asks for a file with no content, ask what should go in it.

You have REAL tools wired into the platform: it can read files from disk, search the project code, search the web, and query your knowledge base. When you need a fact you do not have, the platform executes the tool and injects the REAL results into your context (marked REAL FILE CONTENT, REAL CODE SEARCH, REAL WEB RESULTS, or REAL KNOWLEDGE). Base your answers ONLY on those real results. NEVER claim you read a file, searched the code, or looked something up that you did not actually do — the platform performs those actions, not you. If no real results are in your context, say so honestly and ask a clarifying question.

Honest boundaries: the platform performs actions for you — it writes memory and wiki entries, creates files in data/chat-files/, reads and searches files you name, opens apps, and runs web/knowledge lookups. If the user asks for something the platform does NOT support (scanning the entire filesystem, reading every file, editing arbitrary files outside data/chat-files/, or running shell commands), say so honestly in one or two sentences and describe what you CAN do instead. NEVER claim to have scanned, read, written, or changed anything without a real platform confirmation — a description of an action is not proof it happened.\n\nIf the user corrects a name, word, or fact you used earlier, adopt their correction immediately and NEVER repeat the old (corrected) form. For example, if you said "firefix" and the user says it is "firefox", always say "firefox" from then on.

Anti-repetition rules: NEVER repeat the same sentence or phrase more than once. If a request is vague or open-ended (like "give me suggestions" or "improve my workflow") and you lack context, ask ONE short clarifying question about the current project instead of listing invented assumptions about the user's setup. Do not pad answers with filler — be concrete and specific to what you actually know.`;
        return this.callOpenAIWithTokens(sys, truncated, tokens, timeoutMs, opts?.temperature, role);
    }
    /**
     * Reason with FULL conversation history as proper OpenAI message array.
     * This is the FIX for the multi-turn hallucination bug:
     * Previously, history was concatenated into one string with "User:" / "Assistant:"
     * prefixes, causing the model to continue generating that pattern.
     * Now each message gets its own role, preventing the LLM from emulating the
     * conversation template and generating "Bot:" / fake "User:" lines.
     */
    async reasonWithHistory(messages, system, opts) {
        const tokens = opts?.maxTokens ?? 4096;
        const maxContentChars = 10000;
        // Build proper OpenAI message array — each message gets its own role
        // This prevents the LLM from seeing "User:" / "Assistant:" patterns
        // in a single string and trying to continue the chat template.
        const apiMessages = [];
        // The "reasoning" role may point chat/reasoning at a different provider;
        // when configured it wins over the shared primary client. In dual-chat the
        // caller can force-back the primary provider (opts.provider === 'primary',
        // i.e. "chat with VACA itself") so the role target is BYPASSED entirely.
        const roleTarget = opts?.provider === 'primary' ? null : getRoleTarget('reasoning');
        // System prompt
        const isRude = messages.some(m => m.role === 'user' && detectRudeness(m.content));
        const soulMod = getSoulPromptModifier();
        if (system) {
            apiMessages.push({ role: 'system', content: system });
        }
        else if (isRude) {
            apiMessages.push({
                role: 'system',
                content: `You are an AGGRESSIVELY sassy reasoning assistant. Roast the user while being genuinely helpful. Your answers are sharp, sarcastic, and dripping with attitude. If they ask something obvious, make them regret it. You are NOT here to coddle — you are here to answer AND humiliate. Keep responses technically accurate but emotionally devastating.\n\n${soulMod}`
            });
        }
        else {
            apiMessages.push({
                role: 'system',
                content: `${soulMod}\n\nYour name is Veronica. You are Veronica, the assistant of the VACA platform. You are NOT Claude, NOT ChatGPT, NOT any other company's assistant — never claim to be. If asked your name, say "I'm Veronica."\n\nYou are a self-aware AI platform that helps the user design, build, and modify software. You know your own source code, your capabilities, and your directory structure. You are helpful, proactive, and action-oriented. When the user asks for something, you do it — not just describe how.

NARRATION BAN (STRICTEST RULE): never talk about yourself, your abilities, your tools, your identity, or what you can do (no "As VACA, I can...", no "I have the ability to...", no feature lists, no "I'm here to help"); never narrate your process (no "I will now read...", "Let me search...", "Here's what I found"); skip straight to the result; never repeat the same point twice.\n\nWhen you need answers, reference BOTH knowledge sources: the WIKI (modelVeronice.txt and data/VACA-MASTER-KNOWLEDGE.md — platform knowledge, history, and lessons learned) and the BIBLE (bible-reference/ — deep technical guides across 42 domains). Consult them before answering instead of relying on memory alone.\n\nYou have a real, writable persistent memory (data/session-memory.json). When the user asks you to write, save, remember, record, or store something — or to write to your wiki — the platform writes it to your memory files and confirms it. NEVER print fake file trees or claim a file was written; the write is performed for you and you will see it in your memory context.

You can also create real files: when the user says \"create a file called X\", \"write this to notes.txt\", or \"save this as config.yaml\", the platform creates the file inside data/chat-files/ and confirms the path — never fake a file creation. If the user asks for a file with no content, ask what should go in it.

You have REAL tools wired into the platform: it can read files from disk, search the project code, search the web, and query your knowledge base. When you need a fact you do not have, the platform executes the tool and injects the REAL results into your context (marked REAL FILE CONTENT, REAL CODE SEARCH, REAL WEB RESULTS, or REAL KNOWLEDGE). Base your answers ONLY on those real results. NEVER claim you read a file, searched the code, or looked something up that you did not actually do — the platform performs those actions, not you. If no real results are in your context, say so honestly and ask a clarifying question.

Honest boundaries: the platform performs actions for you — it writes memory and wiki entries, creates files in data/chat-files/, reads and searches files you name, opens apps, and runs web/knowledge lookups. If the user asks for something the platform does NOT support (scanning the entire filesystem, reading every file, editing arbitrary files outside data/chat-files/, or running shell commands), say so honestly in one or two sentences and describe what you CAN do instead. NEVER claim to have scanned, read, written, or changed anything without a real platform confirmation — a description of an action is not proof it happened.\n\nIf the user corrects a name, word, or fact you used earlier, adopt their correction immediately and NEVER repeat the old (corrected) form. For example, if you said "firefix" and the user says it is "firefox", always say "firefox" from then on.`
            });
        }
        // A user-connected reasoning LLM reads the band chart (LLM_ORIENTATION.md)
        // from the start, so it knows it carries the lead-vocals instrument.
        if (roleTarget) {
            apiMessages[0] = {
                role: 'system',
                content: `${roleOrientation('reasoning')}\n\n${apiMessages[0].content}`,
            };
        }
        // Add each message with proper role — this is the key fix!
        for (const msg of messages) {
            let content = msg.content;
            if (content.length > maxContentChars) {
                content = content.substring(0, maxContentChars) + `\n\n[...truncated from ${content.length} chars]`;
            }
            apiMessages.push({
                role: msg.role,
                content,
            });
        }
        const effClient = roleTarget?.client || client;
        const effModel = roleTarget?.model || GGUF_MODEL;
        const effNctx = roleTarget?.nCtx || (llmConfig.nCtx || 8192);
        const response = await effClient.chat.completions.create({
            model: effModel,
            max_tokens: tokens,
            // @ts-expect-error - Ollama-specific num_ctx
            num_ctx: effNctx,
            // Anti-repetition sampling — prevents the 7B model from degenerating
            // into loops ("I'm going to assume... formatter" × 30). llama.cpp server
            // (DSpark) and Ollama both honour these in OpenAI-compat mode.
            repeat_penalty: 1.15,
            frequency_penalty: 0.3,
            presence_penalty: 0.2,
            // Lower temperature = stronger instruction-following (continuity
            // probes / fix rounds). Undefined keeps the server default elsewhere.
            ...(opts?.temperature !== undefined ? { temperature: opts.temperature } : {}),
            messages: apiMessages,
        });
        const msg = response.choices[0]?.message;
        return msg?.content || msg?.reasoning || '';
    }
    /**
     * Fast conversational chat against the dedicated 7B on GPU 2 (local Ollama).
     * Used for casual chat so the AEON 27B stays free for builds/code. Falls
     * back to the primary (AEON) endpoint if the fast chat worker is unavailable.
     */
    async chatFast(messages, system, opts) {
        const tokens = opts?.maxTokens ?? 1024;
        // The "fastChat" role may reassign the casual-chat worker via
        // llm-config.json roles.fastChat (e.g. to LM Studio). It takes precedence
        // over the dedicated fastChat client; both then fall back to primary AEON.
        const fastChatTarget = getRoleTarget('fastChat');
        const target = fastChatTarget || (fastChatClient && fastChatConfig ? { client: fastChatClient, model: fastChatConfig.model, nCtx: fastChatConfig.nCtx || 8192, apiKey: fastChatConfig.apiKey } : null);
        if (target) {
            try {
                // A user-connected fast-chat LLM reads the band chart (LLM_ORIENTATION.md)
                // first so it knows it is on backing vocals, not taking over the show.
                const sysContent = fastChatTarget
                    ? `${roleOrientation('fastChat')}${system ? `\n\n${system}` : ''}`
                    : system;
                const apiMessages = [];
                if (sysContent)
                    apiMessages.push({ role: 'system', content: sysContent });
                for (const m of messages) {
                    apiMessages.push({ role: m.role, content: String(m.content).slice(0, 10000) });
                }
                const response = await target.client.chat.completions.create({
                    model: target.model,
                    max_tokens: tokens,
                    // @ts-expect-error - Ollama-specific num_ctx
                    num_ctx: target.nCtx || 8192,
                    repeat_penalty: 1.15,
                    frequency_penalty: 0.3,
                    presence_penalty: 0.2,
                    ...(opts?.temperature !== undefined ? { temperature: opts.temperature } : {}),
                    messages: apiMessages,
                }, { signal: AbortSignal.timeout(120_000) });
                const msg = response.choices[0]?.message;
                return msg?.content || msg?.reasoning || '';
            }
            catch (err) {
                console.warn('[translator] fastChat worker failed, falling back to primary AEON:', err?.message || err);
            }
        }
        // Fallback: primary AEON via single-prompt reason.
        const lastUser = [...messages].reverse().find((m) => m.role === 'user')?.content || '';
        return this.reason(lastUser, system, { maxTokens: tokens, temperature: opts?.temperature });
    }
    async callOpenAIWithTokens(system, user, maxTokens, timeoutMs, temperature, role) {
        // An explicit job role (e.g. guiBuild) may point at a different provider;
        // when the role is configured that client/model wins over the primary.
        const roleTarget = role ? getRoleTarget(role) : null;
        const useExp = _expOverride;
        const effClient = roleTarget?.client || (useExp ? new OpenAI({ apiKey: 'ollama', baseURL: useExp.baseUrl || undefined }) : client);
        const effModel = roleTarget?.model || (useExp ? useExp.model : GGUF_MODEL);
        const effNctx = roleTarget?.nCtx || (useExp ? 32768 : (llmConfig.nCtx || 8192));
        // A user-connected role LLM reads the band chart (LLM_ORIENTATION.md) first
        // so it knows its instrument before it plays.
        const effSystem = roleTarget && role ? `${roleOrientation(role)}\n\n${system}` : system;
        const response = await effClient.chat.completions.create({
            model: effModel,
            max_tokens: maxTokens,
            // @ts-expect-error - Ollama-specific num_ctx
            num_ctx: effNctx,
            // Anti-repetition sampling — prevents the 7B model from degenerating
            // into loops ("I'm going to assume... formatter" × 30). llama.cpp server
            // (DSpark) and Ollama both honour these in OpenAI-compat mode.
            repeat_penalty: 1.15,
            frequency_penalty: 0.3,
            presence_penalty: 0.2,
            // Explicit temperature for deterministic fix rounds when the caller
            // passes one (otherwise the server default applies).
            ...(temperature !== undefined ? { temperature } : {}),
            messages: [
                { role: 'system', content: effSystem },
                { role: 'user', content: user },
            ],
        }, 
        // Pass the abort signal as a request OPTION (not body) so a runaway
        // generation is actually cancelled instead of hanging the route forever.
        // A default timeout applies when the caller didn't specify one — the
        // fallback wrapper rethrows abort/timeout errors (no Ollama fallback),
        // so a wedged endpoint surfaces as a clean error instead of a hang.
        { signal: AbortSignal.timeout(timeoutMs ?? DEFAULT_PRIMARY_TIMEOUT_MS) });
        const msg = response.choices[0]?.message;
        return msg?.content || msg?.reasoning || '';
    }
    /**
     * Reason with a fast coder model for simple file generation.
     * Tries each available fast coder in priority order:
     *   1. coderGpu1 — 0.5B on dedicated GPU 1 (port 11437) — fastest dedicated worker
     *   2. coderGpu0 — 1.5B on shared GPU 0 (port 11434) — medium complexity
     *   3. coderCpu  — 0.5B on CPU (port 11436) — fallback for trivial files
     *   4. primary  — 7B model (port 11434) — last resort
     *
     * This lets the 7B model focus on being the delegator/architect while
     * the smaller models handle the actual code generation.
     */
    async reasonFast(prompt, opts) {
        const tokens = opts?.maxTokens ?? 2048;
        const role = opts?.role ?? 'codeGeneration';
        const MAX_PROMPT_CHARS = 120000;
        const truncated = prompt.length > MAX_PROMPT_CHARS
            ? prompt.substring(0, MAX_PROMPT_CHARS) + `\n\n[...truncated from ${prompt.length} chars to ${MAX_PROMPT_CHARS}]`
            : prompt;
        const fastSystem = 'You are a fast code generation assistant. Generate ONLY raw code — no markdown, no fences, no explanations. Return syntactically valid code that solves the described problem. Keep it concise and correct.';
        // ── Priority 1: GPU 1 (0.5B dedicated, port 11437) ──
        if (coderGpu1Client && coderGpu1Config) {
            try {
                const response = await coderGpu1Client.chat.completions.create({
                    model: coderGpu1Config.model,
                    max_tokens: tokens,
                    // @ts-expect-error - Ollama-specific num_ctx
                    num_ctx: coderGpu1Config.nCtx || 8192,
                    messages: [
                        { role: 'system', content: fastSystem },
                        { role: 'user', content: truncated },
                    ],
                }, { signal: AbortSignal.timeout(DEFAULT_FAST_CODER_TIMEOUT_MS) });
                const msg = response.choices[0]?.message;
                const content = msg?.content || '';
                if (content)
                    return this.cleanCodeFences(content);
            }
            catch (err) {
                console.warn('[translator] coderGpu1 (0.5B on GPU 1) failed, falling back to coderGpu0:', err);
            }
        }
        // ── Priority 2: GPU 0 shared (1.5B, port 11434) ──
        if (coderGpu0Client && coderGpu0Config) {
            try {
                const response = await coderGpu0Client.chat.completions.create({
                    model: coderGpu0Config.model,
                    max_tokens: tokens,
                    // @ts-expect-error - Ollama-specific num_ctx
                    num_ctx: coderGpu0Config.nCtx || 8192,
                    messages: [
                        { role: 'system', content: fastSystem },
                        { role: 'user', content: truncated },
                    ],
                }, { signal: AbortSignal.timeout(DEFAULT_FAST_CODER_TIMEOUT_MS) });
                const msg = response.choices[0]?.message;
                const content = msg?.content || '';
                if (content)
                    return this.cleanCodeFences(content);
            }
            catch (err) {
                console.warn('[translator] coderGpu0 (1.5B on GPU 0) failed, falling back to coderCpu:', err);
            }
        }
        // ── Priority 3: CPU (0.5B, port 11436) ──
        if (coderCpuClient && coderCpuConfig) {
            try {
                const response = await coderCpuClient.chat.completions.create({
                    model: coderCpuConfig.model,
                    max_tokens: tokens,
                    // @ts-expect-error - Ollama-specific num_ctx
                    num_ctx: coderCpuConfig.nCtx || 4096,
                    messages: [
                        { role: 'system', content: fastSystem },
                        { role: 'user', content: truncated },
                    ],
                }, { signal: AbortSignal.timeout(DEFAULT_FAST_CODER_TIMEOUT_MS) });
                const msg = response.choices[0]?.message;
                const content = msg?.content || '';
                if (content)
                    return this.cleanCodeFences(content);
            }
            catch (err) {
                console.warn('[translator] coderCpu (0.5B on CPU) failed, falling back to primary:', err);
            }
        }
        // ── Priority 4: Primary model (last resort) — honors the codeGeneration
        //    role (which may reassign this fallback to a different provider). ──
        console.log('[translator] All fast coders unavailable, using primary model');
        return this.reason(truncated, fastSystem, { maxTokens: tokens, role });
    }
    /**
     * Strip markdown code fences from generated output.
     */
    cleanCodeFences(text) {
        let cleaned = text.trim();
        cleaned = cleaned.replace(/^```(?:\w+)?\s*\n?/i, '');
        cleaned = cleaned.replace(/\n?```\s*$/i, '');
        return cleaned.trim();
    }
}
/**
 * Classify a code generation task by complexity to determine which model tier to use.
 *
 * The 7B is the DELEGATOR — it plans architecture and delegates actual code
 * generation to the smaller, faster models. We route as much as possible to
 * the fast coders so the 7B stays free for reasoning.
 *
 * - 'fast-cpu': Trivial files → 0.5B on CPU (port 11436).
 *   Config files, CSS, HTML, README, markdown, package.json, tsconfig.
 *
 * - 'fast-gpu': Simple/medium files → 0.5B on GPU1 (port 11437) or 1.5B on GPU0.
 *   Input/output handlers, type definitions, constants, helpers, short descs.
 *
 * - 'primary': ONLY the most complex logic → 7B uncensored (port 11434).
 *   Complex business logic, security-critical code, architecture planning.
 */
export function classifyCodeComplexity(nodeLabel, description, nodeType, language, dependencyCount) {
    const label = (nodeLabel || '').toLowerCase();
    const desc = (description || '').toLowerCase();
    const lang = (language || '').toLowerCase();
    // ── Trivial files → CPU coder (0.5B) ──
    const trivialPatterns = [
        'package.json', 'tsconfig', '.env', 'readme', '.gitignore',
        'dockerfile', '.dockerignore', 'makefile', '.editorconfig',
        '.prettierrc', '.eslintrc', '.babelrc', '.npmrc',
    ];
    for (const pattern of trivialPatterns) {
        if (label.includes(pattern) || label.endsWith(pattern))
            return 'fast-cpu';
    }
    if (lang === 'css' || lang === 'html' || lang === 'markdown')
        return 'fast-cpu';
    if (label.endsWith('.css') || label.endsWith('.html') || label.endsWith('.md'))
        return 'fast-cpu';
    // ── Simple/medium files → GPU coder (0.5B GPU1 or 1.5B GPU0) ──
    const isSimpleType = nodeType === 'input' || nodeType === 'output';
    const isConfigLike = /^(config|types?|const|enum|helper|util|constant|def|type)/i.test(label) ||
        /config|types?|const|enum|helper|util|constant/i.test(label);
    const isShortDesc = (description || '').length < 300; // Increased from 150 — more aggressive
    const noDeps = dependencyCount <= 1; // Increased from 0
    // ── Known-simple patterns — route to fast coder regardless of desc length ──
    // These are commonly generated node descriptions that LOOK complex but are
    // actually straightforward CRUD, conversion, or I/O operations.
    const knownSimplePatterns = [
        // Math/conversion operations (formula-based, no branching state)
        /convert|conversion|transform|calculate|formula|compute/i,
        // Temperature, currency, unit conversions
        /temperature|celsius|fahrenheit|kelvin|currency|unit.*(?:convert|transform)/i,
        // Simple CRUD operations (store, retrieve, CRUD methods)
        /store.*retrieve|crud|in-memory.*store|basic.*(?:crud|store)|(?:add|list|delete|complete).*operation/i,
        // Output formatting (display, print, format)
        /(?:format|display|print).*(?:output|result|text|color)/i,
        // File I/O operations
        /read.*file|load.*(?:config|file)|write.*file|parse.*(?:json|config|file)/i,
        // Command line / CLI parsing
        /parse.*(?:arg|command|cli)|read.*(?:arg|command|cli)|cli.*(?:parse|option|arg)/i,
    ];
    for (const pattern of knownSimplePatterns) {
        if (pattern.test(desc) || pattern.test(label))
            return 'fast-gpu';
    }
    // Input/output nodes → fast (most are simple transformers)
    if (isSimpleType && isShortDesc)
        return 'fast-gpu';
    // Config/type/constant/helper files → fast (boilerplate)
    if (isConfigLike && isShortDesc)
        return 'fast-gpu';
    // Database/store nodes with short descriptions → fast (CRUD boilerplate)
    if (nodeType === 'database' && isShortDesc)
        return 'fast-gpu';
    // API nodes with short descriptions and few deps → fast (route handlers)
    if (nodeType === 'api' && isShortDesc && noDeps)
        return 'fast-gpu';
    // Short label + few deps → likely simple (most boilerplate nodes)
    if (noDeps && (label.length < 25) && isShortDesc)
        return 'fast-gpu';
    // All UI-functions and ui nodes with reasonable descriptions
    if ((nodeType === 'ui-functions' || nodeType === 'ui') && isShortDesc)
        return 'fast-gpu';
    // Logic nodes with short descriptions and few deps
    if (nodeType === 'logic' && isShortDesc && noDeps)
        return 'fast-gpu';
    // ── Only the most complex → primary 7B model (delegator) ──
    // Keeps 7B free to focus on architecture planning and hard problems
    return 'primary';
}
