/**
 * Tests for the server-side reaction toggle (backend/src/routes/reactions.ts).
 * The toggle semantics moved from the client's localStorage into the backend
 * so counts stay consistent across devices — these tests lock that behavior.
 */
import { describe, it, expect } from 'vitest';
import { applyReaction, REACTIONS } from './reactions';
const alice = 'user-alice';
const bob = 'user-bob';
describe('applyReaction', () => {
    it('adds a reaction for a user', () => {
        const s = applyReaction(undefined, alice, '👍');
        expect(s.counts).toEqual({ '👍': 1 });
        expect(s.users[alice]).toBe('👍');
    });
    it('un-reacts when the user clicks their active emoji again', () => {
        let s = applyReaction(undefined, alice, '👍');
        s = applyReaction(s, alice, '👍');
        expect(s.counts).toEqual({});
        expect(s.users[alice]).toBeUndefined();
    });
    it('switches reactions instead of stacking them', () => {
        let s = applyReaction(undefined, alice, '👍');
        s = applyReaction(s, alice, '🚀');
        expect(s.counts).toEqual({ '🚀': 1 });
        expect(s.counts['👍']).toBeUndefined();
        expect(s.users[alice]).toBe('🚀');
    });
    it('counts multiple users on the same emoji', () => {
        let s = applyReaction(undefined, alice, '😂');
        s = applyReaction(s, bob, '😂');
        expect(s.counts).toEqual({ '😂': 2 });
        expect(s.users[alice]).toBe('😂');
        expect(s.users[bob]).toBe('😂');
    });
    it('decrements only the un-reacting user', () => {
        let s = applyReaction(undefined, alice, '😂');
        s = applyReaction(s, bob, '😂');
        s = applyReaction(s, alice, '😂'); // alice un-reacts
        expect(s.counts).toEqual({ '😂': 1 });
        expect(s.users[alice]).toBeUndefined();
        expect(s.users[bob]).toBe('😂');
    });
    it('does not mutate the input state', () => {
        const input = applyReaction(undefined, alice, '👍');
        const before = JSON.stringify(input);
        applyReaction(input, bob, '👍');
        expect(JSON.stringify(input)).toBe(before);
    });
    it('validates against the known reaction set', () => {
        expect(REACTIONS).toContain('👍');
        expect(REACTIONS).toContain('❤️');
        expect(REACTIONS).toContain('🤩');
        expect(REACTIONS).toHaveLength(7);
    });
});
