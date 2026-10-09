/**
 * Idle Monitor
 * ============
 * Tracks "when did the user last touch the app" so background services (the
 * idle micro-app experimenter) can run without competing for the LLM while the
 * user is actively building.
 *
 * Activity is stamped by:
 *   - an Express middleware (registered in index.ts) for any request that
 *     isn't a health probe or a static asset fetch
 *   - the WebSocket layer (registered in index.ts): socket connect / message /
 *     disconnect all count as activity.
 *
 * Uses monotonic timing internally; exposes `lastActivityAt` as an ISO string
 * for status reporting. Starts quiet and never spawns timers on its own — the
 * callers (experimenter service) drive the polling via `isIdle()`.
 */
const IDLE_DEFAULT_MS = 60_000;
/** Request paths that should NOT count as user activity (health + static noise). */
const ACTIVITY_IGNORE = (() => {
    const exact = new Set(['/health', '/api/health']);
    const isIgnored = (p) => {
        if (exact.has(p))
            return true;
        // Static-file GETs (frontend assets, exported apps) churn constantly and
        // are never "user thinking time" — ignore asset extensions.
        if (/\.(js|css|png|jpe?g|gif|svg|woff2?|ttf|ico|map|html)$/i.test(p))
            return true;
        return false;
    };
    return isIgnored;
})();
class IdleMonitor {
    _lastActivityMs = Date.now();
    _signal = 'startup';
    _monotonicStart = getMonotonicMs();
    /** Record that real user/socket activity just happened. */
    noteActivity(signal = 'http') {
        this._lastActivityMs = Date.now();
        this._signal = signal;
    }
    /**
     * True when the app has seen no user activity for at least `idleMs`
     * (defaults to IDLE_DEFAULT_MS). Safe even if nothing has ever been tracked.
     */
    isIdle(idleMs = IDLE_DEFAULT_MS) {
        return Date.now() - this._lastActivityMs >= idleMs;
    }
    /** Milliseconds since the app last saw user activity (− below zero when active). */
    idleSinceMs(idleMs = IDLE_DEFAULT_MS) {
        return Date.now() - this._lastActivityMs - idleMs;
    }
    get lastActivityAt() {
        return new Date(this._lastActivityMs).toISOString();
    }
    get lastSignal() {
        return this._signal;
    }
    get uptimeMs() {
        return getMonotonicMs() - this._monotonicStart;
    }
}
function getMonotonicMs() {
    // process.uptime() is monotonic (unaffected by wall-clock changes); convert
    // to ms. Guard for environments where it is unavailable.
    return typeof process?.uptime === 'function' ? process.uptime() * 1000 : Date.now();
}
/** Whether the ignore-list should suppress an HTTP request path. */
export function shouldCountRequestAsActivity(method, pathname) {
    // Anything non-GET is a user action (POST/PUT/PATCH/DELETE).
    if (method !== 'GET')
        return true;
    return !ACTIVITY_IGNORE(pathname);
}
// ─── Optional state persistence (best-effort) ────────────────────────────
// Not strictly needed — activity is ephemeral — but keeping it lets a restart
// remain conservative (idle timeout re-arms immediately).
export const idleMonitor = new IdleMonitor();
