import { describe, it, expect } from 'vitest';
import { shouldLogHealth, HEALTH_HEARTBEAT_MS } from './healthLog.js';
const MB = 1024 * 1024;
describe('shouldLogHealth', () => {
    it('stays quiet while memory is normal and flat', () => {
        // 237MB RSS, unchanged between samples — nothing worth logging.
        const [log, elevated] = shouldLogHealth(237 * MB, 235 * MB, false);
        expect(log).toBe(false);
        expect(elevated).toBe(false);
    });
    it('stays quiet on a small normal-level rise (not >10%)', () => {
        const [log] = shouldLogHealth(250 * MB, 240 * MB, false);
        expect(log).toBe(false);
    });
    it('stays quiet on a large rise that is still well below the band', () => {
        // 150 → 180MB is +20% but trivially normal memory — no line.
        const [log, elevated] = shouldLogHealth(180 * MB, 150 * MB, false);
        expect(log).toBe(false);
        expect(elevated).toBe(false);
    });
    it('is silent on the first sample (no baseline yet)', () => {
        const [log] = shouldLogHealth(237 * MB, 0, false);
        expect(log).toBe(false);
    });
    it('logs when entering the elevated band (>500MB)', () => {
        const [log, elevated] = shouldLogHealth(510 * MB, 490 * MB, false);
        expect(log).toBe(true);
        expect(elevated).toBe(true);
    });
    it('logs on a sustained rise (>10%) while already elevated', () => {
        const [log, elevated] = shouldLogHealth(900 * MB, 800 * MB, true);
        expect(log).toBe(true);
        expect(elevated).toBe(true);
    });
    it('logs when returning below the band after being elevated', () => {
        const [log, elevated] = shouldLogHealth(450 * MB, 520 * MB, true);
        expect(log).toBe(true);
        expect(elevated).toBe(false);
    });
    it('does not log a small wobble inside the elevated band', () => {
        // Recent heartbeat already logged → a 505↔512MB wobble stays quiet.
        const now = Date.now();
        const [log, elevated] = shouldLogHealth(505 * MB, 512 * MB, true, now - 1000, now);
        expect(log).toBe(false);
        expect(elevated).toBe(true);
    });
    it('logs a heartbeat while staying elevated past the cooldown', () => {
        // Flat at 550MB, but the last elevated line was 6 minutes ago.
        const [log, elevated, lastMs] = shouldLogHealth(550 * MB, 545 * MB, true, 1000, 1000 + HEALTH_HEARTBEAT_MS + 1);
        expect(log).toBe(true);
        expect(elevated).toBe(true);
        expect(lastMs).toBe(1000 + HEALTH_HEARTBEAT_MS + 1);
    });
    it('does not heartbeat before the cooldown elapses', () => {
        // Flat elevated, last line 1 minute ago.
        const [log, , lastMs] = shouldLogHealth(550 * MB, 545 * MB, true, 1000, 1000 + 60 * 1000);
        expect(log).toBe(false);
        expect(lastMs).toBe(1000); // unchanged
    });
    it('treats exactly 500MB as below the band (strict >)', () => {
        const [log, elevated] = shouldLogHealth(500 * MB, 480 * MB, false);
        expect(log).toBe(false);
        expect(elevated).toBe(false);
    });
    it('logs when crossing up into the band from below', () => {
        // 495 → 505: crossed above; one line is worth it.
        const [log, elevated] = shouldLogHealth(505 * MB, 495 * MB, false);
        expect(log).toBe(true);
        expect(elevated).toBe(true);
    });
});
