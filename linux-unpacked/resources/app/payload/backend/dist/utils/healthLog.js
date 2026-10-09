// ─── Periodic resource logging decision (leak watchdog) ─────────────────
// The backend samples memory every 30s. The console stays QUIET while memory
// is normal: the periodic [Health] line only prints when there is actually
// something to look at — RSS crossed the interest threshold (500MB), a
// sustained rise (>10%) while already elevated, a low-frequency heartbeat
// while elevated (one line per HEALTH_HEARTBEAT_MS so slow leaks don't go
// silent), or the return below the band. The >1.5GB critical warning is
// unchanged. Extracted to its own module so unit tests do not import the
// whole Express app.
export const HEALTH_RSS_INTEREST_MB = 500;
export const HEALTH_RSS_CRITICAL_MB = 1500;
export const HEALTH_RISE_FRACTION = 0.10;
export const HEALTH_HEARTBEAT_MS = 5 * 60 * 1000; // one line per 5 min while elevated
/**
 * Decide whether the periodic [Health] line should print for this sample.
 * Pure function — unit-tested in src/utils/healthLog.test.ts.
 *
 * @param rssBytes          current RSS
 * @param prevRssBytes      last sampled RSS (0 on first sample)
 * @param elevated          whether the previous sample was already above interest
 * @param lastElevatedLogMs timestamp of the last [Health] line printed while
 *                          elevated (0 if none)
 * @param nowMs             current epoch ms (injectable for tests)
 * @returns [shouldLog, nowElevated, nowLastElevatedLogMs]
 */
export function shouldLogHealth(rssBytes, prevRssBytes, elevated, lastElevatedLogMs = 0, nowMs = Date.now()) {
    const above = rssBytes > HEALTH_RSS_INTEREST_MB * 1024 * 1024;
    // Log on: entering the elevated band, sustained rise while elevated,
    // leaving the elevated band, or a heartbeat while staying elevated so a
    // slow leak (520→540→560MB, never >10% per step) stays visible.
    const entered = !elevated && above;
    const rose = elevated && prevRssBytes > 0 && rssBytes > prevRssBytes * (1 + HEALTH_RISE_FRACTION);
    const fellBack = elevated && !above;
    const heartbeat = above && nowMs - lastElevatedLogMs >= HEALTH_HEARTBEAT_MS;
    const shouldLog = entered || rose || fellBack || heartbeat;
    return [shouldLog, above, shouldLog && above ? nowMs : lastElevatedLogMs];
}
