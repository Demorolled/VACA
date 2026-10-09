/**
 * System Monitor Route — System Awareness Daemon API
 * ====================================================
 *
 * Receives periodic system state reports from the `system_monitor.py` daemon
 * and makes them available to the Veronica terminal (and all connected clients
 * via Socket.IO broadcast).
 *
 * Endpoints:
 *   POST /api/system-monitor/report  — Daemon posts system state
 *   GET  /api/system-monitor/status  — Get latest system snapshot
 *   GET  /api/system-monitor/context — Get system context formatted for LLM prompt
 *   POST /api/system-monitor/start   — Launch the daemon from the backend
 *   POST /api/system-monitor/stop    — Stop the daemon
 *   GET  /api/system-monitor/daemon  — Check daemon status
 */
import { Router } from 'express';
import { spawn, execSync, execFile } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import { getIO } from '../socket/socketManager.js';
import { describeImage } from '../ai/vision.js';
// ─── In-Memory State ───────────────────────────────────────────────────────
let currentState = null;
let lastSeen = 0;
const DAEMON_SCRIPT = join(import.meta.dirname, '..', '..', 'system-agent', 'system_monitor.py');
const PID_FILE = join(import.meta.dirname, '..', '..', 'system-agent', '.system_monitor.pid');
// ─── Helpers ───────────────────────────────────────────────────────────────
function formatProcessList(procs, limit = 8) {
    return procs.slice(0, limit).map(p => `  - ${p.name} (PID ${p.pid}): ${p.cpu_percent}% CPU, ${p.memory_percent}% RAM`).join('\n');
}
function formatProcessLine(proc) {
    return `${proc.name} (${proc.cpu_percent}% CPU, ${proc.memory_percent}% RAM)`;
}
function isDaemonRunning() {
    if (!existsSync(PID_FILE))
        return false;
    try {
        const pid = parseInt(readFileSync(PID_FILE, 'utf-8').trim(), 10);
        execSync(`kill -0 ${pid}`, { stdio: 'ignore' });
        return true;
    }
    catch {
        return false;
    }
}
function getStaleSeconds() {
    if (!lastSeen)
        return -1;
    return Math.floor((Date.now() - lastSeen) / 1000);
}
// ─── LLM-Ready Context Formatter ───────────────────────────────────────────
/**
 * Generate a formatted string suitable for injection into an LLM system prompt.
 * This is the "awareness" data that makes the terminal AI "see" what the user
 * is running.
 */
export function getSystemContextForLLM() {
    if (!currentState) {
        return '';
    }
    const s = currentState;
    const isStale = getStaleSeconds() > 30;
    let context = `── System Awareness ──\n`;
    context += `Active Window: ${s.active_window}\n`;
    context += `Processes Running: ${s.process_count}\n`;
    context += `System Load: ${s.load.cpu_percent}% CPU | ${s.load.ram_percent}% RAM | ${s.load.disk_percent}% Disk\n`;
    context += `Uptime: ${s.load.uptime_hours}h\n\n`;
    context += `Top CPU Processes:\n`;
    context += formatProcessList(s.top_cpu, 8);
    context += `\n\n`;
    context += `Top Memory Processes:\n`;
    context += formatProcessList(s.top_memory, 5);
    context += `\n\n`;
    // Window-specific hints
    if (s.active_window_basename && s.active_window_basename !== '(unknown)') {
        context += `The user is currently focused on: **${s.active_window_basename}**\n`;
    }
    if (isStale) {
        context += `\n⚠️ System data is ${getStaleSeconds()}s stale — the monitor daemon may not be running.\n`;
    }
    context += `── End System Awareness ──`;
    return context;
}
// ─── Routes ────────────────────────────────────────────────────────────────
export const systemMonitorRoutes = Router();
/**
 * POST /api/system-monitor/report
 * Receives system state from the Python daemon.
 */
systemMonitorRoutes.post('/report', (req, res) => {
    const state = req.body;
    // Validate required fields
    if (!state || !state.timestamp || !state.load) {
        res.status(400).json({ success: false, error: 'Invalid system state payload' });
        return;
    }
    currentState = state;
    lastSeen = Date.now();
    // Broadcast to all Socket.IO clients
    const io = getIO();
    if (io) {
        io.emit('system_state', state);
    }
    res.json({ success: true, stale_seconds: 0 });
});
/**
 * GET /api/system-monitor/status
 * Returns the latest system state snapshot.
 */
systemMonitorRoutes.get('/status', (_req, res) => {
    res.json({
        success: true,
        state: currentState,
        stale_seconds: getStaleSeconds(),
        daemon_running: isDaemonRunning(),
        last_seen: lastSeen ? new Date(lastSeen).toISOString() : null,
    });
});
/**
 * GET /api/system-monitor/context
 * Returns the system context formatted for LLM injection.
 */
systemMonitorRoutes.get('/context', (_req, res) => {
    const context = getSystemContextForLLM();
    res.json({
        success: true,
        context,
        available: !!currentState,
        stale_seconds: getStaleSeconds(),
    });
});
/**
 * POST /api/system-monitor/start
 * Launch the Python daemon from the backend.
 */
systemMonitorRoutes.post('/start', (_req, res) => {
    if (isDaemonRunning()) {
        res.json({ success: true, message: 'Daemon is already running', pid: parseInt(readFileSync(PID_FILE, 'utf-8').trim(), 10) });
        return;
    }
    if (!existsSync(DAEMON_SCRIPT)) {
        res.status(500).json({ success: false, error: `Daemon script not found at ${DAEMON_SCRIPT}` });
        return;
    }
    try {
        spawn('python3', [DAEMON_SCRIPT, '--daemon'], {
            detached: true,
            stdio: 'ignore',
        }).unref();
        res.json({ success: true, message: 'Daemon launched' });
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});
/**
 * POST /api/system-monitor/stop
 * Stop the running daemon.
 */
systemMonitorRoutes.post('/stop', async (_req, res) => {
    if (!isDaemonRunning()) {
        res.json({ success: true, message: 'Daemon is not running' });
        return;
    }
    try {
        execSync(`python3 ${DAEMON_SCRIPT} --stop`, { stdio: 'pipe' });
        res.json({ success: true, message: 'Daemon stopped' });
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});
/**
 * GET /api/system-monitor/daemon
 * Check daemon status.
 */
systemMonitorRoutes.get('/daemon', (_req, res) => {
    res.json({
        success: true,
        running: isDaemonRunning(),
        pid: existsSync(PID_FILE) ? parseInt(readFileSync(PID_FILE, 'utf-8').trim(), 10) : null,
    });
});
/**
 * POST /api/system-monitor/screenshot
 * Capture a screenshot via the Python daemon and return as base64.
 *
 * The daemon must be running. This uses the `mss` Python library to capture
 * the screen on both X11 and Wayland.
 *
 * Body: { resize_width?: number } (optional, max dimension for resizing)
 * Response: { success: true, image_base64: "...", width: 2560, height: 1440 }
 */
systemMonitorRoutes.post('/screenshot', async (req, res) => {
    if (!isDaemonRunning()) {
        res.status(503).json({ success: false, error: 'System monitor daemon is not running. Start it with /system start or systemctl --user start system-monitor' });
        return;
    }
    try {
        const inlineScript = `
import mss, base64

with mss.mss() as sct:
    monitor = sct.monitors[2] if len(sct.monitors) > 2 else sct.monitors[1]
    im = sct.grab(monitor)
    w, h = im.size
    png_bytes = mss.tools.to_png(im.rgb, im.size)
    b64 = base64.b64encode(png_bytes).decode('utf-8')
    print(f"{w}x{h}")
    print(b64)
`;
        execFile('python3', ['-c', inlineScript], {
            timeout: 15000,
            maxBuffer: 50 * 1024 * 1024,
        }, (err, stdout, stderr) => {
            if (err) {
                console.error('[screenshot] Capture failed:', stderr || err.message);
                res.status(500).json({ success: false, error: `Screenshot capture failed: ${err.message}` });
                return;
            }
            const lines = stdout.trim().split('\n');
            const dims = lines[0] || '2560x1440';
            const b64 = lines.slice(1).join('\n').trim();
            if (!b64) {
                res.status(500).json({ success: false, error: 'Screenshot returned empty data' });
                return;
            }
            const [widthStr, heightStr] = dims.split('x');
            const width = parseInt(widthStr, 10) || 2560;
            const height = parseInt(heightStr, 10) || 1440;
            const sizeKB = Math.round(b64.length * 0.75 / 1024);
            res.json({
                success: true,
                image_base64: b64,
                width,
                height,
                size_kb: sizeKB,
            });
        });
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});
/**
 * GET /api/system-monitor/screenshot/:filename
 * Serve a previously captured screenshot file.
 */
systemMonitorRoutes.get('/screenshot/:filename', (req, res) => {
    const { filename } = req.params;
    // Only allow PNG files for safety
    if (!filename.endsWith('.png')) {
        res.status(400).json({ success: false, error: 'Only PNG files are allowed' });
        return;
    }
    const filePath = join(DAEMON_SCRIPT.replace('system_monitor.py', ''), 'screenshots', filename);
    if (!existsSync(filePath)) {
        res.status(404).json({ success: false, error: 'Screenshot not found' });
        return;
    }
    res.sendFile(filePath);
});
/**
 * POST /api/system-monitor/screenshot/describe
 * Capture a screenshot AND describe it using a vision-capable LLM — all in one backend call.
 *
 * Eliminates the previous round-trip where the frontend received the base64 image
 * and then sent it back to the backend for vision analysis.
 *
 * Body:
 *   prompt?: string — description prompt (default: "What's shown on this screen? Describe the content briefly.")
 *   provider?: string — LLM provider (only used if apiKey provided)
 *   apiKey?: string — API key for the provider (from frontend localStorage)
 *   model?: string — model override (e.g. 'qwen2.5-7b')
 *
 * Response (success):
 *   { success: true, description: "...", model_used: "ollama" }
 *
 * Response (failure):
 *   { success: false, error: "..." }
 */
systemMonitorRoutes.post('/screenshot/describe', async (req, res) => {
    if (!isDaemonRunning()) {
        res.status(503).json({ success: false, error: 'System monitor daemon is not running' });
        return;
    }
    const userPrompt = req.body?.prompt || "What's shown on this screen? Describe the content briefly.";
    try {
        // Step 1: Capture the screenshot (with dimensions)
        const inlineScript = `
import mss, base64

with mss.mss() as sct:
    monitor = sct.monitors[2] if len(sct.monitors) > 2 else sct.monitors[1]
    im = sct.grab(monitor)
    w, h = im.size
    png_bytes = mss.tools.to_png(im.rgb, im.size)
    b64 = base64.b64encode(png_bytes).decode('utf-8')
    print(f"{w}x{h}")
    print(b64)
`;
        execFile('python3', ['-c', inlineScript], {
            timeout: 15000,
            maxBuffer: 50 * 1024 * 1024,
        }, async (err, stdout) => {
            if (err) {
                res.status(500).json({ success: false, error: 'Screenshot capture failed' });
                return;
            }
            const lines = stdout.trim().split('\n');
            const dims = lines[0] || '1920x1080';
            const b64 = lines.slice(1).join('\n').trim();
            if (!b64) {
                res.status(500).json({ success: false, error: 'Screenshot returned empty data' });
                return;
            }
            const [widthStr, heightStr] = dims.split('x');
            const width = parseInt(widthStr, 10) || 1920;
            const height = parseInt(heightStr, 10) || 1080;
            const sizeKB = Math.round(b64.length * 0.75 / 1024);
            // Step 2: Describe the image using vision LLM (backend call)
            const result = await describeImage(b64, userPrompt);
            if (result.success && result.description) {
                res.json({
                    success: true,
                    description: result.description,
                    model_used: result.model_used,
                    width,
                    height,
                });
            }
            else {
                // Vision analysis failed but we have the image — return base64 so the
                // frontend can try direct browser-to-API calls as a last resort
                res.json({
                    success: false,
                    error: result.error || 'Vision analysis failed',
                    image_base64: b64,
                    prompt: userPrompt,
                    width,
                    height,
                    size_kb: sizeKB,
                });
            }
        });
    }
    catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});
