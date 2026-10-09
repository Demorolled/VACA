import { Router } from 'express';
import { exec, spawn } from 'child_process';
import { promisify } from 'util';
import { AITranslator } from '../ai/translator.js';
import { openApplication, openUrl, hasTool } from '../services/desktopActions.js';
const execAsync = promisify(exec);
export const desktopRoutes = Router();
const translator = new AITranslator();
// ─── Execute a desktop action ────────────────────────────────────────────
async function executeAction(action) {
    try {
        switch (action.action) {
            // ── Open Application ──
            case 'open_app': {
                const { app, args } = action.params;
                const opened = await openApplication(app, args || []);
                return {
                    success: opened.success,
                    result: opened.result,
                    spoken: action.spoken || `I've opened ${app} for you.`,
                };
            }
            // ── Run Shell Command ──
            case 'run_command': {
                const cmd = action.params.command;
                const { stdout, stderr } = await execAsync(cmd, { timeout: 15000 });
                const output = stdout.trim() || stderr.trim() || 'Command completed.';
                return {
                    success: true,
                    result: output,
                    spoken: action.spoken || 'Command executed successfully.',
                };
            }
            // ── Search Web ──
            case 'search_web': {
                const query = encodeURIComponent(action.params.query);
                const url = `https://www.google.com/search?q=${query}`;
                spawn('google-chrome', [url], { detached: true, stdio: 'ignore' }).unref();
                return {
                    success: true,
                    result: `Searching for: ${action.params.query}`,
                    spoken: action.spoken || `I searched for ${action.params.query} on the web.`,
                };
            }
            // ── Open URL ──
            case 'open_url': {
                const opened = await openUrl(action.params.url);
                return {
                    success: opened.success,
                    result: opened.result,
                    spoken: action.spoken || `I've opened that URL for you.`,
                };
            }
            // ── System Info ──
            case 'get_info': {
                const infoType = action.params.info.toLowerCase();
                let cmd = '';
                if (infoType.includes('time') || infoType.includes('date')) {
                    cmd = 'date "+%A, %B %d, %Y at %I:%M %p"';
                }
                else if (infoType.includes('system') || infoType.includes('os')) {
                    cmd = 'uname -a';
                }
                else if (infoType.includes('uptime')) {
                    cmd = 'uptime -p';
                }
                else if (infoType.includes('memory') || infoType.includes('ram')) {
                    cmd = "free -h | grep Mem | awk '{print $3 \" used out of \" $2}'";
                }
                else if (infoType.includes('disk') || infoType.includes('storage')) {
                    cmd = "df -h / | tail -1 | awk '{print $3 \" used out of \" $2 \" on \" $6}'";
                }
                else if (infoType.includes('ip') || infoType.includes('network')) {
                    cmd = "hostname -I 2>/dev/null | awk '{print $1}'";
                }
                else {
                    cmd = 'uname -a';
                }
                const { stdout } = await execAsync(cmd);
                const info = stdout.trim() || 'No information available.';
                return {
                    success: true,
                    result: info,
                    spoken: action.spoken || info,
                };
            }
            // ── Type Text ──
            case 'type_text': {
                const text = action.params.text;
                if (hasTool('ydotool')) {
                    const escapedText = text.replace(/"/g, '\\"');
                    await execAsync(`ydotool type "${escapedText}"`, { timeout: 5000 });
                    return {
                        success: true,
                        result: `Typed: ${text.substring(0, 50)}${text.length > 50 ? '...' : ''}`,
                        spoken: action.spoken || 'I typed that for you.',
                    };
                }
                if (hasTool('wtype')) {
                    const escapedText = text.replace(/"/g, '\\"');
                    await execAsync(`wtype "${escapedText}"`, { timeout: 5000 });
                    return {
                        success: true,
                        result: `Typed: ${text.substring(0, 50)}${text.length > 50 ? '...' : ''}`,
                        spoken: action.spoken || 'I typed that for you.',
                    };
                }
                if (hasTool('wl-copy')) {
                    await execAsync(`echo "${text.replace(/"/g, '\\"')}" | wl-copy`, { timeout: 5000 });
                    return {
                        success: true,
                        result: `Copied to clipboard: ${text.substring(0, 50)}`,
                        spoken: "I copied that to your clipboard since I can't type directly.",
                    };
                }
                return {
                    success: false,
                    result: 'No typing tool available (install ydotool or wtype)',
                    spoken: "I need ydotool installed to type on your desktop.",
                };
            }
            // ── Mouse Move ──
            case 'mouse_move': {
                if (hasTool('ydotool')) {
                    await execAsync(`ydotool mouse move ${action.params.x} ${action.params.y}`, { timeout: 5000 });
                    return { success: true, result: `Mouse moved to (${action.params.x}, ${action.params.y})`, spoken: action.spoken };
                }
                return { success: false, result: 'ydotool not installed', spoken: "I need ydotool to control the mouse." };
            }
            // ── Mouse Click ──
            case 'mouse_click': {
                if (hasTool('ydotool')) {
                    const btn = action.params.button === 'right' ? '3' : '1';
                    await execAsync(`ydotool click ${btn}`, { timeout: 5000 });
                    return { success: true, result: `${action.params.button || 'left'} click`, spoken: action.spoken };
                }
                return { success: false, result: 'ydotool not installed', spoken: "I need ydotool to click." };
            }
            // ── Press Key ──
            case 'press_key': {
                if (hasTool('ydotool')) {
                    await execAsync(`ydotool key ${action.params.key}`, { timeout: 5000 });
                    return { success: true, result: `Pressed ${action.params.key}`, spoken: action.spoken };
                }
                return { success: false, result: 'ydotool not installed', spoken: "I need ydotool to press keys." };
            }
            // ── Screenshot ──
            case 'screenshot': {
                const screenshotPath = `/tmp/veronica-screenshot-${Date.now()}.png`;
                if (hasTool('grim')) {
                    await execAsync(`grim "${screenshotPath}"`, { timeout: 10000 });
                    return { success: true, result: 'Screenshot taken', spoken: 'I took a screenshot. It\'s saved on the desktop.' };
                }
                if (hasTool('gnome-screenshot')) {
                    await execAsync(`gnome-screenshot -f "${screenshotPath}"`, { timeout: 10000 });
                    return { success: true, result: 'Screenshot taken', spoken: 'I took a screenshot.' };
                }
                return { success: false, result: 'No screenshot tool available', spoken: "I don't have a screenshot tool installed." };
            }
            // ── Say ──
            case 'say': {
                return {
                    success: true,
                    result: action.params.message,
                    spoken: action.params.message,
                };
            }
            // ── None ──
            case 'none': {
                return {
                    success: true,
                    result: 'No action needed.',
                    spoken: action.spoken,
                };
            }
            default:
                return { success: false, result: 'Unknown action', spoken: "I don't know how to do that yet." };
        }
    }
    catch (err) {
        return {
            success: false,
            result: err.message || 'Execution failed',
            spoken: `I had trouble with that. ${err.message || ''}`,
        };
    }
}
// ─── LLM interprets command → structured action ──────────────────────────
const COMMAND_SYSTEM_PROMPT = `You are Veronica, a desktop voice assistant. Interpret the user's spoken command and respond with ONLY a JSON object.

Available actions and their params:
1. {"action":"open_app","params":{"app":"app_name","args":[]},"spoken":"What you'll say"}
   - Apps: browser/chrome, firefox, terminal, file manager/files/nautilus, editor/vscode, calculator, settings, text editor
2. {"action":"run_command","params":{"command":"shell command"},"spoken":"response"}
   - For running terminal commands, scripts, or operations
3. {"action":"search_web","params":{"query":"search text"},"spoken":"response"}
   - Search the internet
4. {"action":"open_url","params":{"url":"full url"},"spoken":"response"}
   - Open a specific URL
5. {"action":"get_info","params":{"info":"time|date|system|uptime|memory|disk|ip"},"spoken":"response"}
   - Get system information
6. {"action":"type_text","params":{"text":"text to type"},"spoken":"response"}
   - Type text on the desktop
7. {"action":"mouse_move","params":{"x":0,"y":0},"spoken":"response"}
   - Move mouse to coordinates
8. {"action":"mouse_click","params":{"button":"left|right"},"spoken":"response"}
   - Click mouse button
9. {"action":"press_key","params":{"key":"key_combination"},"spoken":"response"}
   - Press keyboard shortcut (e.g., "ctrl+alt+t" for terminal)
10. {"action":"screenshot","spoken":"response"}
    - Take a screenshot
11. {"action":"say","params":{"message":"message"},"spoken":"message"}
    - Just speak a response without any action
12. {"action":"none","spoken":"response"}
    - If the command doesn't require any desktop action

Rules:
- Be helpful, concise, and slightly witty as Veronica
- Execute the user's request directly — don't ask for permission
- For general conversation or questions, use "say" action
- For greetings, use "say" with a friendly response
- ALWAYS respond with valid JSON only, no other text
- The "spoken" field is what Veronica will say out loud - make it natural and conversational`;
async function interpretCommand(text) {
    try {
        const response = await translator.reason(text, COMMAND_SYSTEM_PROMPT, { maxTokens: 512 });
        const jsonMatch = response.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
            return JSON.parse(jsonMatch[0]);
        }
    }
    catch { }
    return {
        action: 'say',
        params: { message: text },
        spoken: `I heard you say "${text}". I'm not sure what to do with that.`,
    };
}
// ─── Routes ───────────────────────────────────────────────────────────────
/**
 * POST /api/desktop/command
 * Execute a natural language desktop command via Veronica
 */
desktopRoutes.post('/command', async (req, res) => {
    try {
        const { command, voice_mode } = req.body;
        if (!command || typeof command !== 'string') {
            return res.status(400).json({ error: 'Command text is required' });
        }
        const action = await interpretCommand(command);
        const result = await executeAction(action);
        res.json({
            success: result.success,
            command,
            action: action.action,
            result: result.result,
            spoken: result.spoken,
            voice_mode: !!voice_mode,
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error.message || 'Desktop command failed',
            spoken: "Sorry, I had trouble with that command.",
        });
    }
});
/**
 * GET /api/desktop/status
 * Check what desktop control tools are available
 */
desktopRoutes.get('/status', (_req, res) => {
    const tools = {
        xdg_open: hasTool('xdg-open'),
        google_chrome: hasTool('google-chrome'),
        firefox: hasTool('firefox'),
        gnome_terminal: hasTool('gnome-terminal'),
        nautilus: hasTool('nautilus'),
        ydotool: hasTool('ydotool'),
        wtype: hasTool('wtype'),
        wl_copy: hasTool('wl-copy'),
        grim: hasTool('grim'),
        gnome_screenshot: hasTool('gnome-screenshot'),
        python3: hasTool('python3'),
    };
    res.json({
        success: true,
        display_server: process.env.XDG_SESSION_TYPE || 'unknown',
        tools,
        available_count: Object.values(tools).filter(Boolean).length,
    });
});
/**
 * POST /api/desktop/run
 * Directly run a shell command (for power users)
 */
desktopRoutes.post('/run', async (req, res) => {
    try {
        const { command } = req.body;
        if (!command || typeof command !== 'string') {
            return res.status(400).json({ error: 'Command is required' });
        }
        const { stdout, stderr } = await execAsync(command, { timeout: 30000 });
        res.json({
            success: true,
            stdout: stdout.trim(),
            stderr: stderr.trim(),
        });
    }
    catch (error) {
        res.status(500).json({
            success: false,
            error: error.message,
        });
    }
});
