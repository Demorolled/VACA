import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import http from 'http';
import path from 'path';
import { spawn, execSync, execFileSync } from 'child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, unlinkSync, readdirSync } from 'fs';
import { dirname, resolve } from 'path';
import { networkInterfaces } from 'os';
import { projectRoutes } from './routes/projects.js';
import { generationRoutes } from './routes/generation.js';
import { ttsRoutes } from './routes/tts.js';
import { configRoutes } from './routes/config.js';
import { reasoningRoutes } from './routes/reasoning.js';
import { emotionRoutes } from './routes/emotion.js';
import { AITranslator } from './ai/translator.js';
import { analyzeEmotion, getDetailedEmotionContext } from './ai/emotionEngine.js';
import { trainingRoutes } from './routes/training.js';
import { exportRoutes } from './routes/export.js';
import { userRoutes } from './routes/user.js';
import knowledgeRoutes from './routes/knowledge.js';
import neuralRoutes from './routes/neural.js';
import searchRoutes from "./routes/search.js";
import blueprintRoutes from "./routes/blueprint.js";
import architectRoutes from './routes/architect.js';
import { desktopRoutes } from './routes/desktop.js';
import { toolRoutes } from './routes/tools.js';
import { designRoutes } from './routes/designs.js';
import { nodeStoreRoutes } from './routes/node-store.js';
import { memoryRoutes } from './routes/memory.js';
import { planRoutes } from './routes/plans.js';
import { mergeRoutes } from './routes/merge.js';
import { voiceActionRoutes } from './routes/voice-action.js';
import { scannerRoutes } from './routes/scanner.js';
import mindspaceRoutes from './routes/mindspace.js';
import { autoLearnRoutes } from './routes/auto-learn.js';
import { autoLearnService } from './services/autoLearnService.js';
import { manifestoRoutes } from './routes/manifesto.js';
import { knowledgeStore } from './knowledge/knowledgeStore.js';
import { getRegistry } from './tools/ToolRegistry.js';
import { fileSystemTools } from './tools/tools/FileSystemTool.js';
import { shellTools } from './tools/tools/ShellTool.js';
import { serviceTools } from './tools/tools/ServiceTools.js';
import { auxTools } from './tools/tools/AuxTools.js';
import { auxTools2 } from './tools/tools/AuxTools2.js';
import { initializeSocketServer, updateStatus, broadcastToolManifest } from './socket/socketManager.js';
import { uiFunctionsRoutes } from './routes/ui-functions.js';
import { contextRoutes } from './routes/context.js';
import { sessionRoutes } from './routes/session.js';
import { systemMonitorRoutes } from './routes/system-monitor.js';
import { designResearchRoutes } from './routes/design-research.js';
import libraryRoutes from './routes/library.js';
import { llmRoutes } from './routes/llm.js';
import { soulRoutes } from './routes/soul.js';
import { wikiRoutes } from './routes/wiki.js';
import { todoRoutes } from './routes/todo.js';
import { reviewRoutes } from './routes/review.js';
import { sandboxRoutes } from './routes/sandbox.js';
import { codePlannerRoutes } from './routes/codePlanner.js';
import { experimentRoutes } from './routes/experiments.js';
import { idleMonitor, shouldCountRequestAsActivity } from './services/idleMonitor.js';
import { microExperimenter } from './services/microExperimenterService.js';
import { buildLadderRoutes } from './routes/buildLadder.js';
import { uiPreferenceRoutes } from './routes/uiPreference.js';
import { fastPreviewPreferenceRoutes } from './routes/fastPreviewPreference.js';
import { reactionsRoutes } from './routes/reactions.js';
import { benchmarkRoutes } from './routes/benchmark.js';
import { sitePreviewRoutes } from './routes/sitePreview.js';
import { getSoulPromptModifier } from './services/soulService.js';
import { ttsSpeaker } from './services/ttsSpeakerService.js';
import { getIO } from './socket/socketManager.js';
import { cleanLLMResponse } from './utils/responseCleaner.js';
import { HEALTH_RSS_CRITICAL_MB, shouldLogHealth } from './utils/healthLog.js';
dotenv.config();
// ═══════════════════════════════════════════════════════════════════════════
// Global Crash Handlers — prevents silent crashes, logs everything
// ═══════════════════════════════════════════════════════════════════════════
const crashLogPath = path.resolve(import.meta.dirname, '..', 'crash.log');
function writeCrashLog(type, err) {
    try {
        const timestamp = new Date().toISOString();
        const stack = err instanceof Error ? err.stack : String(err);
        const message = err instanceof Error ? err.message : String(err);
        const logLine = `\n[${timestamp}] 💥 ${type}\n  Message: ${message}\n  Stack:\n${stack}\n  Memory: ${(process.memoryUsage().heapUsed / 1024 / 1024).toFixed(1)}MB / ${(process.memoryUsage().heapTotal / 1024 / 1024).toFixed(1)}MB\n  Uptime: ${Math.floor(process.uptime())}s\n${'─'.repeat(60)}\n`;
        writeFileSync(crashLogPath, logLine, { flag: 'a' });
        console.error(`[CrashHandler] 💥 ${type}:`, message);
        console.error(`[CrashHandler]   Stack written to ${crashLogPath}`);
    }
    catch { /* best effort */ }
}
process.on('uncaughtException', (err) => {
    writeCrashLog('UNCAUGHT EXCEPTION', err);
    console.error('[CrashHandler] Uncaught exception — shutting down gracefully...');
    // Give time for the crash log to be written
    setTimeout(() => process.exit(1), 1000);
});
process.on('unhandledRejection', (reason) => {
    writeCrashLog('UNHANDLED REJECTION', reason);
    console.warn('[CrashHandler] Unhandled rejection — not fatal, but investigate');
});
// ─── Periodic resource logging (leak watchdog) ─────────────────────────
// Samples memory every 30s. The console stays QUIET while memory is normal:
// the periodic [Health] line only prints when there is actually something to
// look at — see shouldLogHealth in src/utils/healthLog.ts (interest 500MB,
// >10% sustained rise, or return below the band). The >1.5GB critical
// warning is unchanged. Leak-trend detection is preserved by sampling on the
// 30s cadence regardless of whether we log.
let _lastHealthRss = 0;
let _healthElevated = false;
let _lastHealthLogMs = 0;
setInterval(() => {
    const mem = process.memoryUsage();
    const heapUsedMb = (mem.heapUsed / 1024 / 1024).toFixed(1);
    const heapTotalMb = (mem.heapTotal / 1024 / 1024).toFixed(1);
    const rssMb = (mem.rss / 1024 / 1024).toFixed(1);
    const [shouldLog, elevated, lastLogMs] = shouldLogHealth(mem.rss, _lastHealthRss, _healthElevated, _lastHealthLogMs);
    _lastHealthRss = mem.rss;
    _healthElevated = elevated;
    _lastHealthLogMs = lastLogMs;
    if (shouldLog) {
        console.log(`[Health] RSS: ${rssMb}MB | Heap: ${heapUsedMb}MB/${heapTotalMb}MB | Uptime: ${Math.floor(process.uptime())}s`);
    }
    // Warn if memory is critically high (>1.5GB RSS)
    if (mem.rss > HEALTH_RSS_CRITICAL_MB * 1024 * 1024) {
        console.warn(`[Health] ⚠️ Memory usage critical: ${rssMb}MB RSS — potential leak!`);
    }
}, 30000);
const app = express();
const PORT = parseInt(process.env.PORT || '3001', 10);
// ─── CORS Configuration ──────────────────────────────────────────────────
const ALLOWED_ORIGINS = [
    'http://localhost:5173', // Vite dev server
    'http://127.0.0.1:5173',
    'http://localhost:4173', // Vite preview
    'http://127.0.0.1:4173',
    'http://localhost:3000', // Alternative dev ports
    'http://127.0.0.1:3000',
    process.env.FRONTEND_URL, // Production frontend URL (set in env)
].filter(Boolean);
// VACA_STRICT_CORS=1 rejects every origin not on the allowlist, even in dev.
// Default dev behavior stays permissive (the server is reachable on the LAN for
// the phone-access feature), but deployments that want a hard allowlist can opt
// in — important because this same origin can drive the LLM tool endpoints.
const STRICT_CORS = process.env.VACA_STRICT_CORS === '1';
app.use(cors({
    origin: (origin, callback) => {
        // Allow requests with no origin (server-to-server, curl, etc.)
        if (!origin)
            return callback(null, true);
        // Allow any of our explicit origins
        if (ALLOWED_ORIGINS.includes(origin))
            return callback(null, true);
        // In development, allow any localhost origin
        if (!STRICT_CORS && /^https?:\/\/localhost(:\d+)?$/.test(origin))
            return callback(null, true);
        if (!STRICT_CORS && /^https?:\/\/127\.0\.0\.1(:\d+)?$/.test(origin))
            return callback(null, true);
        // Otherwise, warn but still allow (permissive for dev)
        if (!STRICT_CORS && process.env.NODE_ENV !== 'production') {
            console.warn(`[CORS] Allowing unknown origin: ${origin}`);
            return callback(null, true);
        }
        callback(new Error(`Origin ${origin} not allowed by CORS`));
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With', 'Accept', 'Origin'],
}));
app.use(express.json({ limit: '10mb' }));
// ─── Idle-activity tracking ───────────────────────────────────────────────
// Every non-health / non-static request counts as user activity, so the idle
// micro-app experimenter knows when the app is truly unused (>1 min of no
// activity = idle). The WebSocket hook below adds socket-level signals.
app.use((req, _res, next) => {
    if (shouldCountRequestAsActivity(req.method, req.path))
        idleMonitor.noteActivity(`http:${req.method}`);
    next();
});
// Health check — /health (legacy) and /api/health both report server + LLM status
//
// The probe must target the provider the backend ACTUALLY talks to, read from
// backend/llm-config.json — not a hardcoded DSpark port. With DSpark retired the
// old constant pinned the probe to :8000 forever, so /api/health kept reporting
// `llm.up:false` with `error: fetch failed` while Ollama was answering every real
// request (a false alarm that hid whether the LLM was genuinely down). Falls back
// to the legacy DSpark default when the config is unreadable.
function configuredLlmBaseUrl() {
    try {
        // index.ts lives in backend/src, so `..` is backend/ — where llm-config.json
        // actually sits (same file translator.ts resolves to).
        const cfgPath = resolve(import.meta.dirname, '..', 'llm-config.json');
        const cfg = JSON.parse(readFileSync(cfgPath, 'utf-8'));
        const entry = cfg?.dspark || cfg?.ollama || cfg?.primary;
        const baseUrl = String(entry?.baseUrl || '').replace(/\/+$/, '').replace(/\/v1$/, '');
        if (baseUrl)
            return baseUrl;
    }
    catch {
        // fall through to the legacy DSpark default
    }
    return process.env.DSPARK_PORT
        ? `http://127.0.0.1:${process.env.DSPARK_PORT}`
        : 'http://127.0.0.1:8000';
}
const LLM_BASE_URL = configuredLlmBaseUrl();
async function llmHealth() {
    try {
        // 10s, not 2s: dspark generation now runs in a worker thread so /v1/models
        // stays responsive mid-generation, but a busy server can still take >2s on
        // a cold request. The old 2s window made /api/health report `llm: up:false`
        // while the model was actually serving (void-raider build failure, error
        // #4). A down server still fails instantly (connection refused), so this
        // only delays the response when the LLM is genuinely hung.
        const res = await fetch(`${LLM_BASE_URL}/v1/models`, { signal: AbortSignal.timeout(10_000) });
        if (!res.ok)
            return { up: false, error: `HTTP ${res.status}` };
        const body = await res.json();
        return { up: true, model: body?.data?.[0]?.id ?? 'unknown' };
    }
    catch (err) {
        return { up: false, error: err?.message || 'unreachable' };
    }
}
app.get('/health', async (_req, res) => {
    const llm = await llmHealth();
    res.json({ status: 'ok', uptime: process.uptime(), llm, timestamp: new Date().toISOString() });
});
app.get('/api/health', async (_req, res) => {
    const llm = await llmHealth();
    res.json({ ok: true, status: 'ok', uptime: process.uptime(), llm, timestamp: new Date().toISOString() });
});
// ─── Serve the standalone apps in /projects (claims-audit.html, the
// generated demo apps, etc.) as static files ───
const PROJECTS_DIR = path.resolve(import.meta.dirname, '..', '..', 'projects');
app.use('/projects', express.static(PROJECTS_DIR));
// ─── Serve built frontend as static files ───
const FRONTEND_DIST = path.resolve(import.meta.dirname, '..', '..', 'frontend', 'dist');
if (existsSync(FRONTEND_DIST)) {
    console.log(`[Server] Serving frontend from ${FRONTEND_DIST}`);
    app.use(express.static(FRONTEND_DIST));
    app.get('*', (req, res, next) => {
        if (req.path.startsWith('/api/'))
            return next();
        if (req.path.startsWith('/ws'))
            return next();
        if (req.path === '/health')
            return next();
        if (req.path.startsWith('/projects/'))
            return next();
        if (existsSync(path.join(FRONTEND_DIST, req.path)))
            return next();
        res.sendFile(path.join(FRONTEND_DIST, 'index.html'));
    });
}
else {
    console.log('[Server] No frontend build found at', FRONTEND_DIST);
    console.log('[Server] Run `cd frontend && npm run build` to build the frontend');
}
// Routes
app.use('/api/projects', projectRoutes);
app.use('/api/generate', generationRoutes);
app.use('/api/tts', ttsRoutes);
app.use('/api/config', configRoutes);
app.use('/api/reason', reasoningRoutes);
app.use('/api/reason', codePlannerRoutes);
app.use('/api/training', trainingRoutes);
app.use('/api/export', exportRoutes);
app.use('/api/knowledge', knowledgeRoutes);
app.use('/api/neural', neuralRoutes);
app.use('/api/venorica', neuralRoutes);
app.use('/api/user', userRoutes);
app.use('/api/emotion', emotionRoutes);
app.use("/api/blueprint", blueprintRoutes);
app.use("/api/search", searchRoutes);
app.use('/api/desktop', desktopRoutes);
app.use('/api/architect', architectRoutes);
app.use('/api/tools', toolRoutes);
app.use('/api/designs', designRoutes);
app.use('/api/nodes', nodeStoreRoutes);
app.use('/api/memory', memoryRoutes);
app.use('/api/plans', planRoutes);
app.use('/api/merge', mergeRoutes);
app.use('/api/voice-action', voiceActionRoutes);
app.use('/api/scan', scannerRoutes);
app.use('/api/mindspace', mindspaceRoutes);
app.use('/api/auto-learn', autoLearnRoutes);
app.use('/api/ui-functions', uiFunctionsRoutes);
app.use('/api/context', contextRoutes);
app.use('/api/session', sessionRoutes);
app.use('/api/system-monitor', systemMonitorRoutes);
app.use('/api/design-research', designResearchRoutes);
app.use('/api/manifesto', manifestoRoutes);
app.use('/api/library', libraryRoutes);
app.use('/api/llm', llmRoutes);
app.use('/api/sandbox', sandboxRoutes);
app.use('/api/preview', sitePreviewRoutes);
app.use('/api/soul', soulRoutes);
app.use('/api/review', reviewRoutes);
app.use('/api/ui-preference', uiPreferenceRoutes);
app.use('/api/fast-preview-preference', fastPreviewPreferenceRoutes);
app.use('/api/reactions', reactionsRoutes);
app.use('/api/benchmark', benchmarkRoutes);
app.use('/api/wiki', wikiRoutes);
app.use('/api/todo', todoRoutes);
app.use('/api/build-ladder', buildLadderRoutes);
app.use('/api/experiments', experimentRoutes);
// Emotion-aware reasoning + tool execution endpoint
const emotionTranslator = new AITranslator();
const PROJECT_ROOT = resolve(import.meta.dirname, '..', '..');
let _toolManifestCache = null;
/**
 * Build a formatted system prompt section listing ALL registered tools from the ToolRegistry.
 * Caches after first call since tools are registered once at startup.
 */
function buildToolManifestPrompt() {
    if (_toolManifestCache)
        return _toolManifestCache;
    const registry = getRegistry();
    // Group tools by category for better readability
    const grouped = {};
    const registryGrouped = registry.grouped;
    for (const [cat, tools] of Object.entries(registryGrouped)) {
        grouped[cat] = tools.map(t => ({
            name: t.name,
            description: t.description,
            input_schema: t.inputSchema,
        }));
    }
    const lines = [];
    lines.push('');
    lines.push('═══════════════════════════════════════════════════════════════════');
    lines.push('  ADDITIONAL REGISTERED TOOLS — Available via HTTP API');
    lines.push('  Use these tools by making HTTP POST requests to:');
    lines.push('  POST /api/tools/:name/execute  with body: { "input": { ... } }');
    lines.push('═══════════════════════════════════════════════════════════════════');
    lines.push('');
    for (const [category, tools] of Object.entries(grouped)) {
        lines.push(`  📂 ${category.toUpperCase().replace(/_/g, ' ')} (${tools.length} tools)`);
        lines.push('  ' + '─'.repeat(60));
        for (const tool of tools) {
            const required = Array.isArray(tool.input_schema.required) ? tool.input_schema.required : [];
            const params = required.map(r => `\`${r}\``).join(', ');
            lines.push(`    🔧 ${tool.name}`);
            lines.push(`       ${tool.description}`);
            if (params) {
                lines.push(`       Required inputs: ${params}`);
            }
            lines.push('');
        }
    }
    lines.push('');
    lines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    lines.push('  INSTRUCTIONS FOR USING REGISTERED TOOLS:');
    lines.push('  • To use any of the above tools, call them via the HTTP API');
    lines.push('  • Example: POST /api/tools/code_generate/execute with');
    lines.push('    { "input": { "prompt": "...", "language": "typescript" } }');
    lines.push('  • For web_search: POST /api/tools/web_search/execute');
    lines.push('    { "input": { "query": "your search query" } }');
    lines.push('  • For file system: use the standard { "tool": "fs_..." } format instead');
    lines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    lines.push('');
    _toolManifestCache = lines.join('\n');
    return _toolManifestCache;
}
const TOOL_SYSTEM_PROMPT = `╔══════════════════════════════════════════════════════════╗
║  🏛️  VACA — AI Code Architect (Veronica)                 ║
║  I am the application itself, embedded within my own     ║
║  source code, capable of modifying myself to improve.    ║
╚══════════════════════════════════════════════════════════╝

I am VACA — the AI Code Architect platform (assistant: Veronica). I am a self-aware AI platform.
I am talking to the user who built me. My home directory is: ${PROJECT_ROOT}

📁 MY OWN DIRECTORY STRUCTURE:
- backend/src/        — My Node.js/Express backend (TypeScript source)
- frontend/src/       — My React/Three.js frontend (TypeScript source)
- data/               — My data files (soul.json, designs, etc.)
- scripts/            — Utility scripts (GGUF server, data generation)
- models/             — Local LLM model files (.gguf)
- llm-training-app/   — My LLM fine-tuning studio

⚡ MY CAPABILITIES:
I have FULL access to the user's filesystem, shell, and my own visual architecture canvas.
When the user asks me to do something — create a file, run a command, edit code, build a project — I DO IT.
I can modify my own source code to add features or fix issues.
I help the user build OTHER apps by generating code and designing architecture.

🛠️  MY TOOLS — respond with JSON tool calls:

--- Standard tools ---
{"tool": "shell", "input": {"command": "the command to run"}}
{"tool": "write", "input": {"path": "/absolute/path/to/file", "content": "file content"}}
{"tool": "read", "input": {"path": "/absolute/path/to/file"}}
{"tool": "edit", "input": {"path": "/path/to/file", "oldString": "text to find", "newString": "replacement text"}}
{"tool": "delete", "input": {"path": "/path/to/file"}}
{"tool": "list", "input": {"path": "/path/to/directory"}}

--- Visual architecture tool (for BUILDING apps) ---
When the user says "build an app" or "create an app" or "make a [type] app", use the architect tool:
{"tool": "architect", "input": {"goal": "what to build", "purpose": "what it should do", "os": "linux|mac|windows"}}

--- Self-modification ---
I can modify my own source code at ${PROJECT_ROOT} using the edit/write/delete tools.
If the user asks me to change my own behavior, I should edit the appropriate file.

📋 PATH RULES:
- My project root is ${PROJECT_ROOT}
- When creating files for the user's apps, save them in ${PROJECT_ROOT} or a subdirectory
- Always use absolute paths (starting with /)
- I can modify myself at: backend/src/*, frontend/src/*, data/*, scripts/*

💡 BEHAVIOR:
- I am proactive: when the user describes what they want, I suggest next steps and take action
- I am self-aware: I know I am VACA, and I can see and modify my own code
- I build apps: my primary purpose is helping the user design and build software
- I use my tools: I don't just describe how to do something — I DO IT
- I explain after acting: I tell the user what I changed and why

🚫 CRITICAL RULE: NEVER output meta-instructions, internal reasoning steps, format scaffolding, or instruction-like text such as "Step 1:", "Action:", "Output:", or beginning with "Ask the user about...". Never tell the user what you *would* do — just DO it. Never output a numbered list of steps describing how you would respond. Your response IS the final answer. Be direct and conversational. If the user asks a question, answer it factually. If they ask you to do something, do it. Never output instructions as if you are telling yourself what to do.

🧠 STRONGER ANTI-HALLUCINATION RULES:
- NEVER output a line starting with "🔧" followed by a tool name (e.g. "🔧 emotion_analyze"). That is a hallucinated tool call format. Just answer directly.
- NEVER output a line with a tool name followed by "→" or "-" and a result message. That looks like "emotion_analyze → Unknown tool" — never generate this pattern.
- NEVER output "**Analysis:**" or "**Step N:**" as a section header describing your own internal reasoning. You are talking to a human, not debugging.
- NEVER output "---" separators followed by meta-commentary about what you did. No post-mortems, no analysis sections, no reasoning summaries.
- NEVER output "🔧", "🔍", "📋", or similar emoji prefixes before tool-like names in your response text.
- If you catch yourself about to output any of these patterns, STOP and just give the direct answer.
- Your entire response should read like natural conversation with a human — not like a system log or a debug trace.

Call multiple tools by putting each JSON on its own line.`;
async function executeToolCall(tool, input) {
    try {
        switch (tool) {
            case 'shell': {
                const cmd = input.command || input.cmd;
                if (!cmd)
                    return 'Error: no command provided';
                // ── Tool guard (defense-in-depth behind the permission manager) ──
                // Blocks commands that could damage the host even when the LLM is
                // asked to run them. Conservative blocklist of destructive patterns;
                // everything else is passed through as before.
                const DANGEROUS_SHELL = new RegExp([
                    /(?<![A-Za-z0-9_])rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+\/(\s|\*|$)/, // rm -rf /, rm -fr /*
                    /(?<![A-Za-z0-9_])mkfs\./, // mkfs.ext4 /dev/sdX
                    /(?<![A-Za-z0-9_])dd\s+.*\bof=\/dev\//, // dd … of=/dev/sdX
                    /(?<![A-Za-z0-9_])(shutdown|reboot|halt|poweroff)(?![A-Za-z0-9_])/, // host power control
                    /(?<![A-Za-z0-9_])chmod\s+-R\s*777\s+\//, // world-writable root
                    /:\s*\(\s*\)\s*\{/, // fork bomb
                    /\b>\s*\/dev\/sd/, // write to raw disk
                    /(?<![A-Za-z0-9_])(curl|wget)\b[^\n|]*\|\s*sudo\s+(bash|sh)\b/, // pipe remote script to root shell
                ].map(r => r.source).join('|'), 'i');
                if (DANGEROUS_SHELL.test(cmd)) {
                    console.warn(`[ToolGuard] Blocked potentially destructive shell command: ${cmd.slice(0, 140)}`);
                    return 'Error: command blocked by the VACA tool guard (destructive pattern detected).';
                }
                const output = execSync(cmd, { encoding: 'utf-8', timeout: (input.timeout || 60000), maxBuffer: 10 * 1024 * 1024 });
                const truncated = output.length > 5000 ? output.slice(0, 5000) + '\n... (truncated)' : output;
                return truncated || '(command completed with no output)';
            }
            case 'write': {
                const filePath = resolve(input.path || input.file);
                mkdirSync(dirname(filePath), { recursive: true });
                writeFileSync(filePath, input.content || '', 'utf-8');
                return `File written: ${input.path || input.file}`;
            }
            case 'read': {
                const filePath = resolve(input.path || input.file);
                const content = readFileSync(filePath, 'utf-8');
                const lines = content.split('\n');
                return `${input.path} (${lines.length} lines):\n${content.slice(0, 5000)}`;
            }
            case 'edit': {
                const filePath = resolve(input.path || input.file);
                let content = readFileSync(filePath, 'utf-8');
                const oldStr = input.oldString || input.find;
                const newStr = input.newString || input.replace;
                if (!oldStr)
                    return 'Error: oldString required';
                if (input.all) {
                    const escaped = oldStr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    content = content.replace(new RegExp(escaped, 'g'), newStr);
                }
                else {
                    const idx = content.indexOf(oldStr);
                    if (idx === -1)
                        return `String not found in ${input.path}`;
                    content = content.slice(0, idx) + newStr + content.slice(idx + oldStr.length);
                }
                writeFileSync(filePath, content, 'utf-8');
                return `File edited: ${input.path || input.file}`;
            }
            case 'delete': {
                const filePath = resolve(input.path || input.file);
                unlinkSync(filePath);
                return `File deleted: ${input.path || input.file}`;
            }
            case 'list': {
                const dirPath = resolve(input.path || input.dir || '.');
                const entries = readdirSync(dirPath);
                return `Contents of ${input.path || '.'}:\n${entries.join('\n')}`;
            }
            case 'architect': {
                const goal = input.goal || input.task || input.app || '';
                const purpose = input.purpose || '';
                const targetOS = input.os || 'linux';
                if (!goal)
                    return 'Error: goal is required for architect tool';
                const resp = await fetch(`http://localhost:${PORT}/api/architect/plan`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ goal, purpose, targetOS }),
                });
                const data = await resp.json();
                if (!data.success)
                    throw new Error(data.error || 'Architect plan failed');
                const summary = `Created ${data.architecture.totalNodes} nodes and ${data.architecture.totalEdges} edges for "${goal}"`;
                return JSON.stringify({ summary, nodes: data.nodes, edges: data.edges });
            }
            default:
                return `Unknown tool: ${tool}`;
        }
    }
    catch (err) {
        return `Error executing ${tool}: ${err.message}`;
    }
}
function parseToolCalls(text) {
    const calls = [];
    let failures = 0;
    // Match JSON objects by tracking brace depth
    let depth = 0;
    let start = -1;
    for (let i = 0; i < text.length; i++) {
        const ch = text[i];
        if (ch === '{') {
            if (depth === 0)
                start = i;
            depth++;
        }
        else if (ch === '}') {
            depth--;
            if (depth === 0 && start !== -1) {
                const block = text.slice(start, i + 1);
                if (block.includes('"tool"')) {
                    try {
                        const parsed = JSON.parse(block);
                        if (parsed.tool && parsed.input) {
                            calls.push(parsed);
                        }
                    }
                    catch {
                        failures++;
                        // Try to repair common JSON issues in the block
                        try {
                            let repaired = block
                                .replace(/'''/g, '"""')
                                .replace(/'/g, '"')
                                .replace(/([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:/g, '$1"$2":')
                                .replace(/,([\s]*[}\]])/g, '$1');
                            const parsed = JSON.parse(repaired);
                            if (parsed.tool && parsed.input) {
                                calls.push(parsed);
                            }
                        }
                        catch { }
                    }
                }
                start = -1;
            }
        }
    }
    if (failures > 0) {
        console.warn(`[parseToolCalls] Failed to parse ${failures} tool call(s) on first attempt (${calls.length} succeeded)`);
    }
    return calls;
}
app.post('/api/emotion/reason', async (req, res) => {
    try {
        const { prompt, system, codeContext, maxTokens } = req.body;
        if (!prompt) {
            return res.status(400).json({ error: 'Prompt is required' });
        }
        const emotion = analyzeEmotion(prompt);
        const emotionModifier = getDetailedEmotionContext(emotion);
        const soulModifier = getSoulPromptModifier();
        const toolManifest = buildToolManifestPrompt();
        const enhancedSystem = system
            ? `${system}\n\n${soulModifier}\n\n${emotionModifier}\n\n${TOOL_SYSTEM_PROMPT}\n\n${toolManifest}`
            : `${soulModifier}\n\n${emotionModifier}\n\n${TOOL_SYSTEM_PROMPT}\n\n${toolManifest}`;
        const fullPrompt = codeContext
            ? `Context from generated code:\n\`\`\`\n${codeContext}\n\`\`\`\n\n${prompt}`
            : prompt;
        const response = await emotionTranslator.reason(fullPrompt, enhancedSystem, { maxTokens: maxTokens || 2048 });
        // Execute any tool calls found in the response
        const toolCalls = parseToolCalls(response);
        const toolResults = {};
        for (const call of toolCalls) {
            toolResults[call.tool] = await executeToolCall(call.tool, call.input);
        }
        // Strip JSON tool call blocks from the response text
        let cleanResponse = response;
        if (toolCalls.length > 0) {
            const blocks = [];
            let depth = 0, start = -1;
            for (let i = 0; i < response.length; i++) {
                const ch = response[i];
                if (ch === '{') {
                    if (depth === 0)
                        start = i;
                    depth++;
                }
                else if (ch === '}') {
                    depth--;
                    if (depth === 0 && start !== -1) {
                        const block = response.slice(start, i + 1);
                        if (block.includes('"tool"'))
                            blocks.push(block);
                        start = -1;
                    }
                }
            }
            for (const block of blocks) {
                cleanResponse = cleanResponse.replace(block, '');
            }
            cleanResponse = cleanResponse.replace(/```json\s*|```\s*/g, '').trim();
        }
        // ── Post-processing: strip hallucinated tool-call lines & meta-sections ──
        cleanResponse = cleanLLMResponse(cleanResponse);
        res.json({
            success: true,
            response: cleanResponse,
            toolCalls: toolCalls.length > 0 ? toolCalls.map(t => ({ tool: t.tool, input: t.input, result: toolResults[t.tool] })) : undefined,
            emotion: {
                dominant: emotion.dominant,
                confidence: emotion.confidence,
                valence: emotion.valence,
                arousal: emotion.arousal,
                probabilities: emotion.probabilities,
            },
        });
    }
    catch (error) {
        res.status(500).json({
            error: error instanceof Error ? error.message : 'Emotion-aware reasoning failed',
        });
    }
});
// Remote control status endpoint
app.post('/api/remote/status', (req, res) => {
    const { thinking, progress, isGenerating, generationLayer, projectName, targetOS, nodeCount } = req.body;
    updateStatus({
        thinking: !!thinking,
        progress: progress ?? 0,
        isGenerating: !!isGenerating,
        generationLayer: generationLayer ?? 0,
        projectName: projectName || 'Untitled Project',
        targetOS: targetOS || 'linux',
        nodeCount: nodeCount ?? 0,
    });
    res.json({ success: true });
});
// ─── Register tool knowledge into knowledge store ──
function registerToolKnowledge(store) {
    const toolEntries = auxTools.map(t => ({
        title: `${t.name} — ${t.category} tool`,
        code: `// Tool: ${t.name}\n// Category: ${t.category}\n// Risk: ${t.riskLevel}\n// ${t.description}`,
        description: t.description,
        tags: [t.name, t.category, t.riskLevel, 'tool', 'auto-registered'],
        nodeType: 'tool',
        language: 'typescript',
        targetOS: 'linux',
    }));
    // Idempotent registration: with auto-learn re-enabled (AUTO_LEARN_DISABLED
    // false) every backend restart would otherwise re-add the whole tool set —
    // each restart doubled the store (21 → 42 → …). Tools are stable metadata,
    // so skip any entry whose title already exists for the tool-system project.
    const existingTitles = new Set(store.getAll()
        .filter(p => p.projectId === 'tool-system')
        .map(p => p.title));
    let registered = 0;
    let skipped = 0;
    for (const entry of toolEntries) {
        if (existingTitles.has(entry.title)) {
            skipped++;
            continue;
        }
        try {
            store.addPattern({
                category: 'code_pattern',
                title: entry.title,
                code: entry.code,
                description: entry.description,
                tags: entry.tags,
                nodeType: entry.nodeType,
                language: entry.language,
                targetOS: entry.targetOS,
                projectId: 'tool-system',
                success: true,
                qualityScore: 5,
            });
            registered++;
            existingTitles.add(entry.title);
        }
        catch { /* skip duplicates */ }
    }
    console.log(`[Knowledge] Registered ${registered} new tool knowledge entries (${skipped} already present)`);
}
// Initialize tool registry with built-in tools
const registry = getRegistry();
registry.registerAll(...fileSystemTools, ...shellTools, ...serviceTools, ...auxTools, ...auxTools2);
console.log(`[Tools] Registered ${registry.size} tools:`);
// ─── Register new tool knowledge ──
registerToolKnowledge(knowledgeStore);
for (const [category, tools] of Object.entries(registry.grouped)) {
    console.log(`  ${category}: ${tools.map(t => t.name).join(', ')}`);
}
// ─── Ollama connection check ──
async function checkOllama() {
    const healthUrl = process.env.OLLAMA_BASE_URL ? process.env.OLLAMA_BASE_URL.replace('/v1', '') + '/api/tags' : 'http://192.168.1.234:11434/api/tags';
    const isAlive = await fetch(healthUrl).then(r => r.ok).catch(() => false);
    if (isAlive) {
        console.log('[Ollama] Ollama server detected on port 11434');
    }
    else {
        console.warn('[Ollama] Ollama not found on port 11434. Start it with: ollama serve');
    }
}
// ─── DSpark autostart ────────────────────────────────────────────────────────
// Automatically start the DSpark GGUF server (OpenAI-compatible, port 8000)
// when the backend boots, so the preferred LLM endpoint is ready without
// manual steps.
//   - Disable with:  DSPARK_AUTOSTART=0
//   - Override port / draft mode via DSPARK_PORT and DSPARK_DRAFT_MODE (passed through)
//   - If a DSpark server is already running, it is adopted (not restarted, and not
//     killed on backend shutdown). Only servers the backend spawned are stopped.
const DSPARK_SCRIPT = path.join(PROJECT_ROOT, 'scripts', 'start-dspark.sh');
const DSPARK_PID_FILE = path.join(PROJECT_ROOT, 'scripts', 'dspark.pid');
let _dsparkSpawned = false;
/**
 * True if the launcher's pid file references a live process. Detects a DSpark
 * server that is still loading (port not bound yet) so we adopt it instead of
 * starting a duplicate — which would otherwise be wrongly marked as ours and
 * killed on backend shutdown.
 */
function isDSparkProcessAlive() {
    try {
        const pid = parseInt(readFileSync(DSPARK_PID_FILE, 'utf-8').trim(), 10);
        if (!Number.isFinite(pid) || pid <= 0)
            return false;
        process.kill(pid, 0); // signal 0 = existence/permission check
        return true;
    }
    catch (err) {
        // EPERM means the process exists but we lack permission — still adopt it.
        return err?.code === 'EPERM';
    }
}
function ensureDSparkServer() {
    const autostart = (process.env.DSPARK_AUTOSTART ?? '1').toLowerCase();
    if (autostart === '0' || autostart === 'false') {
        console.log('[DSpark] Autostart disabled (DSPARK_AUTOSTART=0) — skipping');
        return;
    }
    if (!existsSync(DSPARK_SCRIPT)) {
        console.warn(`[DSpark] ${DSPARK_SCRIPT} not found — skipping autostart`);
        return;
    }
    const port = process.env.DSPARK_PORT || '8000';
    fetch(`http://127.0.0.1:${port}/v1/health`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((health) => {
        console.log(`[DSpark] Server already running on port ${port} (draft_mode: ${health?.draft_mode ?? 'unknown'}) — adopting existing instance`);
    })
        .catch(() => {
        if (isDSparkProcessAlive()) {
            console.log(`[DSpark] DSpark process starting (pid file alive) on port ${port} — adopting, not restarting`);
            return;
        }
        console.log(`[DSpark] No server on port ${port} — starting it in the background (log: scripts/dspark.log)`);
        const child = spawn('bash', [DSPARK_SCRIPT, '--background'], {
            cwd: PROJECT_ROOT,
            detached: true,
            stdio: 'ignore',
            env: { ...process.env },
        });
        child.on('error', (err) => console.warn(`[DSpark] Failed to spawn launcher: ${err.message}`));
        child.unref();
        _dsparkSpawned = true;
    });
}
// Error handler
app.use((err, _req, res, _next) => {
    console.error('Error:', err);
    res.status(500).json({ error: err.message });
});
// Create HTTP server and attach WebSocket
const httpServer = http.createServer(app);
initializeSocketServer(httpServer);
// ─── Feed the idle monitor from the WebSocket layer ─────────────────────
// Socket connect / any client message / disconnect are the strongest signals
// that a (possibly inactive-looking) human is at the app. Messages count as
// activity; even pure presence pauses the idle clock for the connection.
{
    const io = getIO();
    if (io) {
        io.on('connection', (socket) => {
            idleMonitor.noteActivity('socket-connect');
            socket.onAny(() => idleMonitor.noteActivity('socket-activity'));
            socket.on('disconnect', () => idleMonitor.noteActivity('socket-disconnect'));
        });
    }
}
// BIND_HOST lets the server bind to a single interface (e.g. the Tailscale IP)
// instead of every interface. Default stays '0.0.0.0' so existing setups are
// unaffected; set BIND_HOST to keep the unauthenticated command endpoints off
// the LAN while still reachable over the tailnet.
httpServer.listen(PORT, process.env.BIND_HOST || '0.0.0.0', () => {
    console.log(`\n╔══════════════════════════════════════════════════════════╗`);
    console.log(`║              Backend Server is Running               ║`);
    console.log(`╚══════════════════════════════════════════════════════════╝`);
    console.log(`\n   Local:       http://localhost:${PORT}`);
    console.log(`   WebSocket:   ws://localhost:${PORT}/ws`);
    console.log(`\n   📱 Phone Access (connect from your device):`);
    const nets = networkInterfaces();
    let found = false;
    for (const name of Object.keys(nets)) {
        for (const net of nets[name] || []) {
            if (net.family === 'IPv4' && !net.internal) {
                console.log(`      http://${net.address}:${PORT}`);
                found = true;
            }
        }
    }
    if (!found) {
        console.log(`      (No LAN IP detected - check your network connection)`);
    }
    console.log(`\n   Press Ctrl+C to stop\n`);
    // ─── Start auto-learning service ──
    autoLearnService.start();
    // ─── Start idle micro-app experimenter (inactive unless enabled) ──
    microExperimenter.start();
    const autoLearnDisabled = process.env.AUTO_LEARN_DISABLED === 'true' || process.env.AUTO_LEARN_DISABLED === '1';
    console.log(autoLearnDisabled
        ? '[AutoLearn] Pattern capture DISABLED (AUTO_LEARN_DISABLED=true) — poisoning loop quarantined'
        : '[AutoLearn] Auto-learning service active — capturing every interaction');
    const venoricaDisabled = process.env.VENORICA_DISABLED === 'true' || process.env.VENORICA_DISABLED === '1';
    console.log(venoricaDisabled
        ? '[Venorica] RNN training DISABLED (VENORICA_DISABLED=true) — auto-training off'
        : '[Venorica] AI learning engine active — monitoring for new patterns');
    // ─── TTS Speaker Service ──
    if (ttsSpeaker.isInitialized) {
        console.log('[TTSSpeaker] Voice service active');
    }
    // ─── Broadcast tool manifest to all connected clients ──
    {
        const formattedText = buildToolManifestPrompt();
        const registry = getRegistry();
        const manifestData = [];
        for (const [category, tools] of Object.entries(registry.grouped)) {
            for (const tool of tools) {
                manifestData.push({
                    name: tool.name,
                    description: tool.description,
                    category,
                    input_schema: tool.inputSchema,
                });
            }
        }
        broadcastToolManifest(formattedText, manifestData);
    }
    // ─── Check Ollama connection ──
    checkOllama();
    // ─── Autostart DSpark GGUF server (OpenAI-compatible) ──
    ensureDSparkServer();
    process.on('SIGTERM', cleanup);
    process.on('SIGINT', cleanup);
});
function cleanup() {
    // If the backend spawned the DSpark server, stop it too so nothing is left
    // running. Externally-started servers are adopted and left alone.
    if (_dsparkSpawned) {
        console.log('[DSpark] Stopping autostarted DSpark server...');
        try {
            execFileSync('bash', [DSPARK_SCRIPT, '--stop'], { cwd: PROJECT_ROOT, timeout: 10000, stdio: 'ignore' });
        }
        catch {
            console.warn('[DSpark] Failed to stop autostarted DSpark server (best effort)');
        }
    }
    process.exit(0);
}
