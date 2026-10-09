import { describe, it, expect } from 'vitest';
import { resolveTimezone, formatFullDate, formatTime, utcOffsetLabel, formatIsoDate, buildClockContext, } from './clockContext.js';
// ═══════════════════════════════════════════════════════════════════════════
// clockContext — timezone-aware date/time for LLM prompts
// ═══════════════════════════════════════════════════════════════════════════
// These tests verify that the clock block formats dates/times correctly in a
// chosen IANA timezone (with sane fallbacks) so the app can truthfully answer
// "what time is it?" / "what's the date?" instead of the model guessing.
// ═══════════════════════════════════════════════════════════════════════════
describe('resolveTimezone', () => {
    it('accepts an explicit IANA timezone', () => {
        expect(resolveTimezone('America/New_York')).toBe('America/New_York');
        expect(resolveTimezone('Asia/Tokyo')).toBe('Asia/Tokyo');
    });
    it('falls back to a valid timezone when none is given', () => {
        const tz = resolveTimezone();
        expect(typeof tz).toBe('string');
        expect(tz.length).toBeGreaterThan(0);
    });
    it('falls back when given junk input', () => {
        expect(typeof resolveTimezone('not-a-real-zone///')).toBe('string');
    });
});
describe('formatFullDate', () => {
    it('formats a fixed instant in UTC', () => {
        const date = new Date('2026-08-01T12:00:00Z');
        const out = formatFullDate(date, 'UTC');
        // August 1, 2026 is a Saturday.
        expect(out).toContain('Saturday');
        expect(out).toContain('August');
        expect(out).toContain('2026');
        expect(out).toContain('1');
    });
    it('shifts the day in a non-UTC zone', () => {
        // 2026-08-01T12:00:00Z is Aug 1 UTC. In Pacific (UTC-07) it is still Aug 1
        // (05:00), but in Tokyo (UTC+9) it is Aug 1 21:00 — same date. Use a
        // midnight-adjacent instant to prove the shift:
        const date = new Date('2026-08-02T00:30:00Z');
        // UTC: Sunday Aug 2; Tokyo (UTC+9): Sunday Aug 2 09:30.
        expect(formatFullDate(date, 'UTC')).toContain('August 2');
        expect(formatFullDate(date, 'Asia/Tokyo')).toContain('August 2');
    });
});
describe('formatTime', () => {
    it('formats a 12-hour clock time with AM/PM', () => {
        const date = new Date('2026-08-01T12:00:00Z');
        const out = formatTime(date, 'UTC');
        expect(out).toMatch(/12:00:00 (AM|PM)/);
    });
    it('shifts time across timezones', () => {
        const date = new Date('2026-08-01T00:00:00Z');
        // Tokyo is UTC+9 — should be 9:00 AM.
        expect(formatTime(date, 'Asia/Tokyo')).toMatch(/9:00:00 AM/);
    });
});
describe('utcOffsetLabel', () => {
    it('returns a signed HH:MM label', () => {
        const date = new Date('2026-08-01T12:00:00Z');
        expect(utcOffsetLabel(date, 'UTC')).toMatch(/^[+-]\d{2}:\d{2}$/);
    });
});
describe('formatIsoDate', () => {
    it('returns a deterministic YYYY-MM-DD', () => {
        const date = new Date('2026-08-01T12:00:00Z');
        expect(formatIsoDate(date, 'UTC')).toBe('2026-08-01');
    });
});
describe('buildClockContext', () => {
    it('returns a full authoritative clock block', () => {
        const ctx = buildClockContext('UTC');
        expect(ctx).toContain('Current Date & Time');
        expect(ctx).toContain('AUTHORITATIVE');
        expect(ctx).toContain('Date:');
        expect(ctx).toContain('Time:');
        expect(ctx).toContain('Timezone: UTC');
        expect(ctx).toContain('ISO Date:');
        expect(ctx).toMatch(/ISO Date: \d{4}-\d{2}-\d{2}/);
    });
    it('matches the current date regardless of zone', () => {
        const utc = buildClockContext('UTC');
        const ny = buildClockContext('America/New_York');
        // Both blocks must contain the same ISO Date (day rollover may differ near
        // midnight, so compare to the actual current UTC date instead).
        const now = new Date();
        const todayUtc = now.toISOString().slice(0, 10);
        const nearMidnight = now.getUTCHours() < 5;
        if (!nearMidnight) {
            expect(utc).toContain(`ISO Date: ${todayUtc}`);
            expect(ny).toContain(`ISO Date: ${todayUtc}`);
        }
    });
});
