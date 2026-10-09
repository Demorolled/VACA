/**
 * clockContext.ts — timezone-aware date/time context for LLM prompts.
 *
 * Small models hallucinate dates ("The current date is...") because they have
 * no clock. This utility produces an authoritative, correctly-formatted
 * "current date & time" block in the *user's* timezone (IANA name, e.g.
 * "America/New_York"), so the app can answer "what time is it?" / "what's the
 * date?" truthfully instead of guessing.
 */
/**
 * Resolve an IANA timezone, falling back to the server's local timezone.
 * Accepts an explicit IANA timezone (preferred — passed from the browser),
 * otherwise derives it from the runtime's resolved locale.
 */
export function resolveTimezone(timeZone) {
    if (timeZone && typeof timeZone === 'string' && timeZone.length > 0 && timeZone.length <= 64) {
        return timeZone;
    }
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    }
    catch {
        return 'UTC';
    }
}
/**
 * Format a Date in the given timezone. Returns the localized string if the
 * timezone is valid, otherwise falls back to the local timezone formatting.
 */
function formatInZone(date, timeZone, options) {
    try {
        return new Intl.DateTimeFormat('en-US', { ...options, timeZone }).format(date);
    }
    catch {
        try {
            return new Intl.DateTimeFormat('en-US', options).format(date);
        }
        catch {
            return date.toLocaleString('en-US', options);
        }
    }
}
/** Full date like "Saturday, August 1, 2026". */
export function formatFullDate(date, timeZone) {
    return formatInZone(date, timeZone, {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
}
/** 12-hour clock time like "2:35:18 PM" plus the zone abbreviation when available. */
export function formatTime(date, timeZone) {
    return formatInZone(date, timeZone, {
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
    });
}
/**
 * Human-readable UTC offset for a zone at a given instant, e.g. "-04:00".
 * Falls back to the local offset if the IANA zone is unsupported.
 */
export function utcOffsetLabel(date, timeZone) {
    try {
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone,
            timeZoneName: 'longOffset',
        }).formatToParts(date);
        const name = parts.find(p => p.type === 'timeZoneName')?.value || '';
        // Some runtimes emit "GMT-4:00" (single-digit hour) — accept 1-2 digits.
        const match = name.match(/GMT([+-]\d{1,2}:\d{2})/);
        return match ? match[1] : '';
    }
    catch {
        const local = -date.getTimezoneOffset();
        const sign = local >= 0 ? '+' : '-';
        const abs = Math.abs(local);
        const hh = String(Math.floor(abs / 60)).padStart(2, '0');
        const mm = String(abs % 60).padStart(2, '0');
        return `${sign}${hh}:${mm}`;
    }
}
/** 24-hour "YYYY-MM-DD" for logs / deterministic dates. */
export function formatIsoDate(date, timeZone) {
    try {
        const parts = new Intl.DateTimeFormat('en-CA', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            timeZone,
        }).formatToParts(date);
        const get = (t) => parts.find(p => p.type === t)?.value || '';
        return `${get('year')}-${get('month')}-${get('day')}`;
    }
    catch {
        return date.toISOString().slice(0, 10);
    }
}
/**
 * Build the authoritative clock block injected into LLM system prompts.
 *
 * Example:
 *   ── Current Date & Time ──
 *   Date: Saturday, August 1, 2026
 *   Time: 2:35:18 PM
 *   Timezone: America/New_York (UTC-04:00)
 *   ISO Date: 2026-08-01
 *   ── End Current Date & Time ──
 *
 * The block instructs the model to trust it over any memorized date.
 */
export function buildClockContext(timeZone) {
    const tz = resolveTimezone(timeZone);
    const now = new Date();
    const offset = utcOffsetLabel(now, tz);
    return [
        '── Current Date & Time (AUTHORITATIVE) ──',
        `Date: ${formatFullDate(now, tz)}`,
        `Time: ${formatTime(now, tz)}`,
        `Timezone: ${tz}${offset ? ` (UTC${offset})` : ''}`,
        `ISO Date: ${formatIsoDate(now, tz)}`,
        'Use this as the true current date and time. Never guess or use a memorized date.',
        '── End Current Date & Time ──',
    ].join('\n');
}
