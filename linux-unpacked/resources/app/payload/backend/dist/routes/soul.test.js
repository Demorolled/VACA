import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { DEFAULT_SOUL } from './soul';
const __dirname = dirname(fileURLToPath(import.meta.url));
// Same resolution as soul.ts getSoulPath(): backend/src/routes -> repo root
const SOUL_PATH = resolve(__dirname, '..', '..', '..', 'data', 'soul.json');
// Guards the 2025 "Veronica identity + no company references" decision.
// If soul.json is edited so the name drifts from Veronica — or a 3rd-party
// company brand (Claude, OpenAI, Gemini, …) creeps into the identity or any
// other field — these tests fail and force a conscious decision.
const FORBIDDEN_TOKENS = [
    'claude',
    'anthropic',
    'openai',
    'chatgpt',
    'gpt-',
    'gemini',
    'grok',
    'copilot',
    'azure',
    'openrouter',
    'microsoft',
    'deepseek',
    'google',
    'xai',
    'together',
];
function loadSoulFile() {
    expect(existsSync(SOUL_PATH), `soul.json missing at ${SOUL_PATH}`).toBe(true);
    return JSON.parse(readFileSync(SOUL_PATH, 'utf-8'));
}
describe('soul.json identity (Veronica, company-free)', () => {
    const soul = loadSoulFile();
    it('identity.name is exactly "Veronica"', () => {
        expect(soul.identity?.name).toBe('Veronica');
    });
    it('the name is anchored in role and description', () => {
        const text = `${soul.identity?.role} ${soul.identity?.description}`;
        expect(text.toLowerCase()).toContain('veronica');
    });
    it('has no forbidden company tokens anywhere in the file', () => {
        const haystack = JSON.stringify(soul).toLowerCase();
        for (const token of FORBIDDEN_TOKENS) {
            expect(haystack.includes(token), `company token '${token}' found in soul.json`).toBe(false);
        }
    });
});
describe('DEFAULT_SOUL fallback (served if soul.json is missing)', () => {
    it('fallback name is "Veronica"', () => {
        expect(DEFAULT_SOUL.identity.name).toBe('Veronica');
    });
    it('fallback has no forbidden company tokens', () => {
        const haystack = JSON.stringify(DEFAULT_SOUL).toLowerCase();
        for (const token of FORBIDDEN_TOKENS) {
            expect(haystack.includes(token), `company token '${token}' found in DEFAULT_SOUL`).toBe(false);
        }
    });
});
