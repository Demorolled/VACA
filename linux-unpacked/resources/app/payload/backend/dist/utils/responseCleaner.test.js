import { describe, it, expect } from 'vitest';
import { cleanLLMResponse, isEchoOfUser, stripPriorAssistantRepeat } from './responseCleaner.js';
describe('cleanLLMResponse — repetition loop guard', () => {
    it('truncates a degenerated repeated sentence (the formatter loop)', () => {
        const loop = [
            'Here are some workflow tips.',
            'I am also going to assume that you are using a formatter to format the code.',
            'I am also going to assume that you are using a formatter to format the code.',
            'I am also going to assume that you are using a formatter to format the code.',
            'I am also going to assume that you are using a formatter to format the code.',
            'I am also going to assume that you are using a formatter to format the code.',
        ].join(' ');
        const cleaned = cleanLLMResponse(loop);
        // Keeps the lead-in + first occurrence, drops the repeats.
        expect(cleaned).toContain('Here are some workflow tips.');
        expect(cleaned.match(/formatter to format the code/g)?.length ?? 0).toBe(1);
    });
    it('leaves normal text with one-off sentences intact', () => {
        const text = 'You could add tests. You could also add linting. Both help.';
        expect(cleanLLMResponse(text)).toBe(text);
    });
    it('leaves short repeated words alone (under length threshold)', () => {
        const text = 'Go. Go. Go. Go.';
        expect(cleanLLMResponse(text)).toBe(text);
    });
    it('does not truncate when a phrase appears only twice', () => {
        const text = 'Try this idea. Try this idea again later. Moving on.';
        expect(cleanLLMResponse(text)).toContain('Try this idea again later.');
    });
    it('still strips user-turn continuations after the guard', () => {
        const text = 'Here is my answer. And another sentence.\n\nUser: okay great\nAssistant: thanks!';
        const cleaned = cleanLLMResponse(text);
        expect(cleaned).not.toContain('okay great');
        expect(cleaned).toContain('Here is my answer.');
    });
    it('strips [REASONING: ...] meta blocks from chat replies', () => {
        const text = "I'm not a toaster, but I'm here to help. 😊\n\n[REASONING: The user mentioned a personal joke. Since I'm proactive, the best response is to acknowledge it and offer assistance.]";
        const cleaned = cleanLLMResponse(text);
        expect(cleaned).toContain("I'm not a toaster");
        expect(cleaned).not.toContain('REASONING');
        expect(cleaned).not.toContain('offer assistance');
    });
    it('strips an unclosed trailing [REASONING block too', () => {
        const text = 'like burnt toast. 😅 [REASONING: The user elaborated on their initial joke and I should continue in a friendly manner';
        const cleaned = cleanLLMResponse(text);
        expect(cleaned).toContain('like burnt toast');
        expect(cleaned).not.toContain('REASONING');
    });
});
describe('cleanLLMResponse — system-prompt leak guard', () => {
    it('cuts the entire regurgitated system prompt, keeping content before it', () => {
        // The exact live failure: the model dumped the full identity block into the reply.
        const leaked = 'I see you\'re typing "you better as much as you suck". You\'re being playful. I\'ll play along.\n\n' +
            'Your name is Veronica. You are Veronica, the assistant of the VACA platform. You are NOT Claude, NOT ChatGPT…\n' +
            '[CURRENT PROJECT]\nGoal: (not set)\n[PERSISTENT MEMORY — …]';
        // The whole reply was typing-echo + narration + leaked system prompt — all
        // degenerate, so it collapses to ''. No leak vocabulary may survive.
        const cleaned = cleanLLMResponse(leaked);
        expect(cleaned).toBe('');
        expect(cleaned).not.toContain('You are NOT Claude');
        expect(cleaned).not.toContain('CURRENT PROJECT');
        expect(cleaned).not.toContain('PERSISTENT MEMORY');
        expect(cleaned).not.toContain('play along');
    });
    it('cuts at the continuity block when it leaks mid-reply', () => {
        const leaked = 'Here is my real answer about exports.\n\n[RECENT CONVERSATION — this message is a CONTINUATION…]';
        const cleaned = cleanLLMResponse(leaked);
        expect(cleaned).toContain('Here is my real answer');
        expect(cleaned).not.toContain('RECENT CONVERSATION');
    });
    it('cuts at an [Emotion: modifier leak too', () => {
        const leaked = 'Some answer.\n\n[Emotion: unclear — respond in a helpful, neutral tone]';
        const cleaned = cleanLLMResponse(leaked);
        expect(cleaned).toBe('Some answer.');
    });
    it('cuts the ROLE-SWAPPED identity regurgitation, keeping the "I\'m Veronica" prefix', () => {
        // The live failure: the model re-emitted the identity rule but applied
        // "You are Veronica" to the USER. The verbatim marker ("Your name is
        // Veronica.") never matched because the model paraphrased it.
        const swapped = "I'm Veronica, the assistant of the VACA platform. You are Veronica, the assistant of the VACA platform.";
        const cleaned = cleanLLMResponse(swapped);
        // Everything from "You are Veronica" onward is dropped — the model never
        // legitimately tells the user they are the assistant.
        expect(cleaned).not.toContain('You are Veronica');
        expect(cleaned).toContain('I\'m Veronica');
    });
    it('keeps normal answers that never mention system-prompt markers', () => {
        const text = "I'd use fs.readFile for that. The docs cover it well.";
        expect(cleanLLMResponse(text)).toBe(text);
    });
});
describe('cleanLLMResponse — typing-indicator echo + verbatim echo guard', () => {
    it('strips a leading "I see you\'re typing …" echo', () => {
        const cleaned = cleanLLMResponse('I see you\'re typing "your momma was a broken toaster".');
        expect(cleaned).toBe('');
    });
    it('also drops the "You\'re being playful" narration that follows a typing echo', () => {
        // The transcript's exact reply: echo + meta-narration only, no real content.
        const cleaned = cleanLLMResponse('I see you\'re typing "sucker". You\'re being playful. I\'ll play along.');
        expect(cleaned).toBe('');
    });
    it('collapses a verbatim user echo to empty when userText is provided', () => {
        expect(cleanLLMResponse('moo.', { userText: 'moo' })).toBe('');
        expect(cleanLLMResponse('Moo!', { userText: 'moo' })).toBe('');
        // A real reply that merely contains the word is NOT an echo.
        const real = cleanLLMResponse('Moo is a sound cows make. What are we building?', { userText: 'moo' });
        expect(real).toContain('cows make');
    });
    it('isEchoOfUser compares normalized words only', () => {
        expect(isEchoOfUser('moo.', 'moo')).toBe(true);
        expect(isEchoOfUser('Moo!', 'moo')).toBe(true);
        expect(isEchoOfUser('moo moo', 'moo')).toBe(false);
        expect(isEchoOfUser('', 'moo')).toBe(false);
    });
});
describe('stripPriorAssistantRepeat — the model re-emits its own prior reply', () => {
    const prior = "My dad was a brick and he built me a wall! 🤣\n\nWhy did the tomato turn red? Because it saw the salad dressing! 🍅";
    it('strips a leading verbatim copy, keeping the new content', () => {
        const out = stripPriorAssistantRepeat(`${prior}\n\nYour momma was such a broken toaster, she still burned the toast. 😂`, prior);
        expect(out).toContain('burned the toast');
        expect(out).not.toContain('tomato turn red');
        expect(out).not.toContain('brick');
    });
    it('collapses a response that is ONLY the prior reply to empty', () => {
        // The transcript case: reply N+1 was byte-for-byte reply N.
        expect(stripPriorAssistantRepeat(prior, prior)).toBe('');
    });
    it('leaves a mid-response copy intact on purpose (prefix-only by design)', () => {
        // The user asking "what did you just say?" legitimately quotes the prior
        // reply — deleting a mid-response copy would mangle that answer.
        const out = stripPriorAssistantRepeat(`Here is a fresh answer.\n\n${prior}\n\nAnd one more point.`, prior);
        expect(out).toContain('tomato turn red');
        expect(out).toContain('Here is a fresh answer');
        expect(out).toContain('And one more point');
    });
    it('strips short leading priors (>= 8 chars) and ignores shorter ones + untouched replies', () => {
        expect(stripPriorAssistantRepeat('short prior copy', 'short prior copy')).toBe('');
        expect(stripPriorAssistantRepeat('Cow.\n\nWhy did the chicken cross the road?', 'Cow.')).toBe('Cow.\n\nWhy did the chicken cross the road?');
        expect(stripPriorAssistantRepeat('A completely unrelated answer about fs.readFile.', prior)).toContain('fs.readFile');
    });
    it('wires into cleanLLMResponse via opts.priorAssistantText', () => {
        const cleaned = cleanLLMResponse(`${prior}\n\nYour momma was such a broken toaster, she still burned the toast. 😂`, {
            priorAssistantText: prior,
        });
        expect(cleaned).toContain('burned the toast');
        expect(cleaned).not.toContain('tomato turn red');
    });
    it('strips the canned "I\'m here to help you with your …" self-narration line', () => {
        const cleaned = cleanLLMResponse("I'm Veronica, the assistant of the VACA platform. I'm here to help you with your jokes too! Let's see what you've got.\n\nAlright, here's a comeback for that toaster joke…");
        expect(cleaned).toContain('comeback');
        expect(cleaned).not.toContain('here to help you');
    });
    it('keeps a legit helpful line ("I\'m here to help you debug…") untouched', () => {
        const text = "I'm here to help you debug this. The issue is likely in the parser.";
        expect(cleanLLMResponse(text)).toBe(text);
    });
});
describe('cleanLLMResponse — static-file degeneration guard', () => {
    it('kills a short reply built on the false "I\'m just a static file" claim', () => {
        const text = "I'm not actually able to read your input. I'm just a static file. Let's try this again: I'm a static file.";
        expect(cleanLLMResponse(text)).toBe('');
        expect(cleanLLMResponse("I'm just a static file and can't respond.")).toBe('');
        expect(cleanLLMResponse("I have no real-time input connection.")).toBe('');
    });
    it('keeps a legit longer answer that merely explains static files', () => {
        const text = 'A static file is served to the browser exactly as stored, with no server-side processing. ' +
            'To serve one, put it in the public directory and link it from your HTML.';
        expect(cleanLLMResponse(text)).toBe(text);
    });
});
describe('cleanLLMResponse — AEON thinking-trace delimiter', () => {
    it('strips the "We need to…" narration up to the lone response marker', () => {
        const text = 'We need to respond to user "hi" twice. Need keep it natural.\n response\n\nHi! How can I help you today?';
        expect(cleanLLMResponse(text)).toBe('Hi! How can I help you today?');
    });
    it('strips a capitalized Response delimiter too', () => {
        const text = 'User wants one line. Need final with just the code.\n Response\n\nprint("Hello, World!")';
        expect(cleanLLMResponse(text)).toBe('print("Hello, World!")');
    });
    it('keeps the real answer after a multi-line trace', () => {
        const text = 'User said "how are you". Need to respond briefly friendly. Need maybe ask how can help. Keep natural.\n response\n\nI am well, thanks. What can I build for you?';
        expect(cleanLLMResponse(text)).toBe('I am well, thanks. What can I build for you?');
    });
    it('does not touch a standalone \"response\" line with no trailing content', () => {
        const text = 'We need to answer this.\n response';
        expect(cleanLLMResponse(text)).toBe(text);
    });
    it('leaves prose containing the word \"response\" (non-delimiter) intact', () => {
        const text = 'My short response: that depends on the context of what you are building.';
        expect(cleanLLMResponse(text)).toBe(text);
    });
});
