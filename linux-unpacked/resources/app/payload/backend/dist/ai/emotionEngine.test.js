import { describe, it, expect, beforeEach } from 'vitest';
import { buildTurnContinuityContext, getEmotionPromptModifier, buildTurnRecap, detectPlayful, updateMood, getMoodState, getMoodModifier, resetMoodForTests, MOOD_DECAY_MS, } from './emotionEngine.js';
describe('buildTurnContinuityContext', () => {
    it('returns empty for <2 messages (no prior turn → no noise)', () => {
        expect(buildTurnContinuityContext([])).toBe('');
        expect(buildTurnContinuityContext([{ role: 'user', content: 'hi' }])).toBe('');
        expect(buildTurnContinuityContext(undefined)).toBe('');
    });
    it('ignores blank/whitespace-only messages', () => {
        // Blank first message filtered; the remaining 2 messages give a prior turn.
        expect(buildTurnContinuityContext([
            { role: 'user', content: '   ' },
            { role: 'user', content: 'earlier stuff' },
            { role: 'user', content: 'now what?' },
        ])).toContain('User: earlier stuff');
        // After filtering, a single meaningful message is not enough for a prior turn.
        expect(buildTurnContinuityContext([
            { role: 'user', content: '   ' },
            { role: 'user', content: 'only message' },
        ])).toBe('');
    });
    it('includes the assistant reply before the current message', () => {
        const block = buildTurnContinuityContext([
            { role: 'user', content: "I'm stressed about my deadline" },
            { role: 'assistant', content: 'Take a breath, we can get through this together.' },
            { role: 'user', content: 'and now my laptop died' },
        ]);
        expect(block).toContain('RECENT CONVERSATION');
        expect(block).toContain('User: I\'m stressed about my deadline');
        expect(block).toContain('VACA: Take a breath');
        // The current (final) message must NOT appear in the block.
        expect(block).not.toContain('laptop died');
    });
    it('caps at 4 prior lines and truncates long lines', () => {
        const long = 'x'.repeat(500);
        const msgs = [];
        for (let i = 0; i < 6; i++) {
            msgs.push({ role: i % 2 === 0 ? 'user' : 'assistant', content: `turn ${i}` });
        }
        msgs.push({ role: 'user', content: 'current' });
        const block = buildTurnContinuityContext(msgs);
        // 6 prior messages is not yet over the cutoff, so 4 lines survive
        // (turns 2-5 kept, 0-1 dropped, current excluded).
        expect(block).toContain('turn 2');
        expect(block).toContain('turn 5');
        expect(block).not.toContain('turn 0');
        expect(block).not.toContain('turn 1');
        expect(block).not.toContain('current');
        const clipped = buildTurnContinuityContext([
            { role: 'user', content: long },
            { role: 'user', content: 'second' },
        ]);
        // The 500-char line is clipped to 220 + ellipsis; the block stays compact
        // (header + worked example + two clipped lines ≈ 1KB — nowhere near the
        // raw 500+ chars of the long message alone).
        expect(clipped).toContain('…');
        expect(clipped.length).toBeLessThan(1200);
        expect(clipped).not.toContain('x'.repeat(300));
    });
    it('includes a WORKED EXAMPLE teaching the tie-back pattern', () => {
        const block = buildTurnContinuityContext([
            { role: 'user', content: 'I am stressed about my deadline tomorrow' },
            { role: 'assistant', content: 'Take a breath, one thing at a time.' },
            { role: 'user', content: 'and now my laptop died and I lost my work' },
        ]);
        expect(block).toContain('WORKED EXAMPLE');
        // The example must show the FOLLOW-UP reply referencing the earlier topic
        // (the exact behavior the continuity probe demands). Its topic must be
        // fictional and distant from real stress scenarios so the 7B never echoes
        // example facts ("interview nerves" leaked into live replies before):
        // assert NO stress/interview/deadline/laptop vocabulary anywhere in it.
        const exampleSection = block.slice(block.indexOf('WORKED EXAMPLE'), block.indexOf('Now continue'));
        expect(exampleSection).toContain('great book');
        expect(exampleSection).toContain('on top of');
        expect(exampleSection).toContain('STRUCTURE ONLY');
        expect(exampleSection.toLowerCase()).toContain('never copy');
        for (const leak of ['interview', 'nerves', 'car', 'deadline', 'laptop', 'stress', 'job']) {
            expect(exampleSection).not.toContain(leak);
        }
        // The real prior turn still renders below the example.
        expect(block).toContain('User: I am stressed about my deadline tomorrow');
    });
    it('long histories (>6 prior) shrink to the last pair to cap token cost', () => {
        const msgs = [];
        for (let i = 0; i < 10; i++) {
            msgs.push({ role: i % 2 === 0 ? 'user' : 'assistant', content: `turn ${i}` });
        }
        msgs.push({ role: 'user', content: 'current' });
        const block = buildTurnContinuityContext(msgs);
        // 10 prior messages > 6 → only the last pair (turns 8-9) survives.
        expect(block).toContain('turn 8');
        expect(block).toContain('turn 9');
        expect(block).not.toContain('turn 0');
        expect(block).not.toContain('turn 7');
        expect(block).not.toContain('current');
    });
    it('never leaks system-role messages into the block', () => {
        const block = buildTurnContinuityContext([
            { role: 'system', content: 'TOP-SECRET SYSTEM PROMPT' },
            { role: 'user', content: 'hello there' },
            { role: 'assistant', content: 'hi! how can I help' },
            { role: 'user', content: 'tell me more' },
        ]);
        expect(block).not.toContain('TOP-SECRET');
        expect(block).not.toContain('system');
        expect(block).toContain('User: hello there');
        expect(block).toContain('VACA: hi!');
    });
    it('works when the final message is an assistant message (system-style array)', () => {
        const block = buildTurnContinuityContext([
            { role: 'user', content: 'first' },
            { role: 'assistant', content: 'second' },
        ]);
        expect(block).toContain('User: first');
        expect(block).not.toContain('second');
    });
    it('forbids verbatim quoting (the echo fix — never "quote their own words")', () => {
        const block = buildTurnContinuityContext([
            { role: 'user', content: 'your momma was a broken toaster' },
            { role: 'assistant', content: 'and your dad was a toaster oven.' },
            { role: 'user', content: 'still burned the toast' },
        ]);
        // The instruction must tell the model to reference in its OWN words and
        // explicitly ban the echo pattern it kept producing live.
        expect(block).toContain('NEVER quote');
        expect(block).toContain('I see you\'re typing');
        expect(block).not.toContain('quote their own words');
    });
});
describe('getEmotionPromptModifier (empathy-first)', () => {
    it('demands an empathic opening for fear/anxiety', () => {
        const mod = getEmotionPromptModifier({
            dominant: 'fear',
            probabilities: { fear: 0.6, neutral: 0.4 },
            valence: -0.5,
            arousal: 0.7,
            confidence: 0.6,
        });
        expect(mod).toContain('lead with empathy');
        expect(mod).toContain("I'm sorry");
        expect(mod).toContain('step-by-step');
    });
    it('demands an empathic opening for sadness', () => {
        const mod = getEmotionPromptModifier({
            dominant: 'sadness',
            probabilities: { sadness: 0.6, neutral: 0.4 },
            valence: -0.6,
            arousal: 0.3,
            confidence: 0.6,
        });
        expect(mod).toContain('lead with empathy');
        expect(mod).toContain('Never jump straight into advice');
    });
    it('acknowledges frustration before solutions for anger', () => {
        const mod = getEmotionPromptModifier({
            dominant: 'anger',
            probabilities: { anger: 0.6, neutral: 0.4 },
            valence: -0.7,
            arousal: 0.8,
            confidence: 0.6,
        });
        expect(mod).toContain('acknowledge their frustration first');
    });
});
describe('buildTurnRecap (user-message continuity prefix)', () => {
    it('returns empty without an earlier user turn', () => {
        expect(buildTurnRecap([])).toBe('');
        expect(buildTurnRecap([{ role: 'user', content: 'hi' }])).toBe('');
        expect(buildTurnRecap([{ role: 'assistant', content: 'hi' }])).toBe('');
    });
    it('returns the user\'s earlier message (not the current one)', () => {
        const recap = buildTurnRecap([
            { role: 'user', content: "I'm stressed about my deadline tomorrow" },
            { role: 'assistant', content: 'Take a breath.' },
            { role: 'user', content: 'and now my laptop died' },
        ]);
        expect(recap).toContain('deadline');
        expect(recap).not.toContain('laptop');
    });
    it('ignores blank earlier messages and truncates long ones', () => {
        const long = 'x'.repeat(300);
        const recap = buildTurnRecap([
            { role: 'user', content: '   ' },
            { role: 'user', content: long },
            { role: 'user', content: 'now' },
        ]);
        expect(recap.length).toBeLessThanOrEqual(140);
        expect(recap.endsWith('…')).toBe(true);
    });
});
describe('mood mirroring with baseline decay', () => {
    beforeEach(() => resetMoodForTests());
    it('detectPlayful spots joking/silly signals and ignores plain text', () => {
        for (const playful of ['lol that was funny', 'haha good one 😂', 'jk obviously', "I'm just kidding", 'you silly goose', 'rofl']) {
            expect(detectPlayful(playful)).toBe(true);
        }
        for (const plain of ['what is the weather like', 'please fix the login bug', 'ok thanks']) {
            expect(detectPlayful(plain)).toBe(false);
        }
    });
    it('detectPlayful catches yo-mama jokes and banter (no lol/haha markers)', () => {
        for (const banter of [
            'your mom was a broken toaster',
            'your mommy was full of broken circuits and smelled',
            'yo mama so fat',
            'fight me bro',
            'come at me 1v1',
            'in your dreams',
            'absolute unit',
            'nah bro',
        ]) {
            expect(detectPlayful(banter)).toBe(true);
        }
    });
    it('detectPlayful catches sassy/comeback banter (the "give me a sassy comeback" ask)', () => {
        expect(detectPlayful('your not gonna respond with sassy comeback?')).toBe(true);
        expect(detectPlayful('give me a sassy comeback')).toBe(true);
        expect(detectPlayful('why is she so sassy')).toBe(true);
    });
    it('detectPlayful catches put-downs directed at VACA (roast me back, don\'t apologize)', () => {
        for (const putdown of [
            'you suck at making code',
            'you suck',
            'your code is trash',
            "you're useless",
            "you're so stupid",
            'you are the worst',
            'your design is garbage',
            'your app sucks',
            'worst developer ever',
            'is that the best you got',
            'roast me',
        ]) {
            expect(detectPlayful(putdown)).toBe(true);
        }
    });
    it('does NOT flag complaints about one\'s OWN work as playful (empathy must win)', () => {
        for (const ownWork of [
            'the build failed again',
            'my code is broken',
            'this app is trash and I need to fix it',
            'i suck at coding, can you help',
        ]) {
            expect(detectPlayful(ownWork)).toBe(false);
        }
    });
    it('does NOT flag ambiguous frustration slang as playful', () => {
        for (const serious of [
            'omg this bug is killing me',
            'bruh the build failed again',
            'she looked as if she had seen a ghost',
            'you wish that were true',
            'y\'all need to fix this',
        ]) {
            expect(detectPlayful(serious)).toBe(false);
        }
    });
    it('confident negative emotion beats playful markers (humor-as-coping)', () => {
        // "my dog died lol" must NOT arm the playful mood — empathy wins.
        updateMood("my dog died lol i can't even", 1_000_000);
        expect(getMoodState().register).toBe('baseline');
        // "omg this is killing me" never arms either.
        updateMood('omg this is killing me', 1_100_000);
        expect(getMoodState().register).toBe('baseline');
    });
    it('arms the playful register and mirrors it back', () => {
        const t0 = 1_000_000;
        updateMood('haha you got me lol 😂', t0);
        expect(getMoodState().register).toBe('playful');
        expect(getMoodState().neutralStreak).toBe(0);
        expect(getMoodModifier()).toContain('PLAYFUL');
        expect(getMoodModifier()).toContain('witty comeback');
        expect(getMoodModifier()).toContain('do NOT take the joke seriously');
    });
    it('arms the playful register for yo-mama jokes without lol markers', () => {
        updateMood('your mom was a broken toaster', 1_000_000);
        expect(getMoodState().register).toBe('playful');
        expect(getMoodModifier()).toContain('PLAYFUL');
    });
    it('arms the playful register for put-downs at VACA (roast back, no sympathy)', () => {
        updateMood('your code is trash', 1_000_000);
        expect(getMoodState().register).toBe('playful');
        expect(getMoodModifier()).toContain('PLAYFUL');
        // "my code is trash" (own work) must NOT keep the roast armed — empathy stays.
        updateMood('my code is trash and i need help', 1_000_000 + MOOD_DECAY_MS + 1000);
        expect(getMoodState().register).toBe('baseline');
    });
    it('scales the playful roast by configured sassiness', () => {
        updateMood('lol nice one', 1_000_000);
        expect(getMoodModifier(80)).toContain('BRUTAL');
        expect(getMoodModifier(54)).toContain('playfully sarcastic');
        expect(getMoodModifier(20)).toContain('gentle teasing');
    });
    it('keeps the playful register while the user stays playful', () => {
        const t0 = 1_000_000;
        updateMood('haha nice one lol', t0);
        const since = getMoodState().since;
        updateMood('and then he said... 😂😂', t0 + 30_000);
        expect(getMoodState().register).toBe('playful');
        expect(getMoodState().since).toBe(since); // same register, no re-arm
        expect(getMoodState().neutralStreak).toBe(0);
    });
    it('decays to baseline after the user stops joking for a few turns', () => {
        const t0 = 1_000_000;
        updateMood('lmao that was wild', t0);
        updateMood('ok anyway', t0 + 60_000);
        expect(getMoodState().register).toBe('playful'); // 1 neutral: still playful
        expect(getMoodState().neutralStreak).toBe(1);
        updateMood('can you help me with the login page', t0 + 120_000);
        expect(getMoodState().register).toBe('baseline'); // 2nd neutral: decayed
        expect(getMoodModifier()).toBe('');
    });
    it('decays to baseline by time even without neutral turns', () => {
        const t0 = 1_000_000;
        updateMood('so silly haha', t0);
        expect(getMoodState().register).toBe('playful');
        updateMood('(long pause, still typing)', t0 + MOOD_DECAY_MS + 1000);
        expect(getMoodState().register).toBe('baseline');
        expect(getMoodState().neutralStreak).toBe(0);
    });
    it('tracks joyful (high-positive, non-playful) as its own register', () => {
        updateMood('This is amazing! I am so excited about this opportunity!', 2_000_000);
        expect(getMoodState().register).toBe('joyful');
        expect(getMoodModifier()).toContain('JOYFUL');
    });
});
