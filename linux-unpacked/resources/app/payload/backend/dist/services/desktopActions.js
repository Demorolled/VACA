/**
 * Desktop actions — shared open-application / open-URL executor.
 *
 * Extracted from routes/desktop.ts so BOTH the voice/desktop route AND the
 * chat reasoning path can actually open apps. The chat model previously
 * hallucinated "open firefox" requests (repeating the user's typo "firefix");
 * with this service the platform executes the open itself and confirms
 * deterministically.
 */
import { spawn, execSync } from 'child_process';
import { existsSync } from 'fs';
/** App aliases → candidate binaries, tried in order. */
export const APP_ALIASES = {
    browser: ['google-chrome', 'firefox'],
    chrome: ['google-chrome'],
    chromium: ['chromium', 'chromium-browser'],
    firefox: ['firefox'],
    terminal: ['gnome-terminal'],
    'file manager': ['nautilus'],
    files: ['nautilus'],
    nautilus: ['nautilus'],
    editor: ['code', 'gedit', 'nano'],
    vscode: ['code'],
    'vs code': ['code'],
    settings: ['gnome-control-center'],
    calculator: ['gnome-calculator', 'kcalc', 'qalculate-gtk'],
    'text editor': ['gedit'],
};
/** Human-readable list for "apps I can open" fallback messages. */
export const OPENABLE_APPS = Object.keys(APP_ALIASES);
/** Check whether a binary is available on PATH or in /usr/bin. */
export function hasTool(name) {
    try {
        execSync(`which ${name}`, { stdio: 'ignore' });
        return true;
    }
    catch {
        return false;
    }
}
function isAvailable(candidate) {
    return hasTool(candidate) || existsSync(`/usr/bin/${candidate}`);
}
/**
 * Open an application by alias or binary name. Returns the launched binary
 * so callers can confirm with the CORRECT name (never a user typo).
 */
export async function openApplication(app, args = []) {
    const key = app.trim().toLowerCase();
    const candidates = APP_ALIASES[key] || [app];
    for (const candidate of candidates) {
        if (isAvailable(candidate)) {
            spawn(candidate, args, {
                detached: true,
                stdio: 'ignore',
                env: { ...process.env, DISPLAY: process.env.DISPLAY || ':0' },
            }).unref();
            return { success: true, result: `Opened ${candidate}`, launched: candidate };
        }
    }
    // Fall back to xdg-open (never launch via a shell string).
    spawn('xdg-open', [app], { detached: true, stdio: 'ignore' }).unref();
    return { success: true, result: `Tried to open ${app} via xdg-open` };
}
/** Open a URL in the default browser (google-chrome or firefox). */
export async function openUrl(url) {
    const browser = isAvailable('google-chrome') ? 'google-chrome' : isAvailable('firefox') ? 'firefox' : null;
    if (browser) {
        spawn(browser, [url], { detached: true, stdio: 'ignore' }).unref();
        return { success: true, result: `Opened URL: ${url}`, launched: browser };
    }
    spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref();
    return { success: true, result: `Opened URL: ${url}` };
}
