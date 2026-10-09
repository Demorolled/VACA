#!/usr/bin/env node
/**
 * A/B test: base Qwen2.5-7B-Instruct-Uncensored (ollama) vs the deployed R15
 * fine-tune (dspark :8000) on identical codegen prompts.
 *
 * Scores each output for: markdown fences, prose explanations, stub markers,
 * and whether it compiles under `tsc --strict --noEmit`.
 *
 * Usage: node scripts/ab-model-quality.mjs
 */
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { execSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';

const PROMPTS = [
  {
    id: 'p1-strict-single-file',
    prompt: `Generate a SINGLE standalone TypeScript file for node "todo-store.ts". NODE DESCRIPTION: in-memory todo item store with add, list, complete operations. NODE TYPE: logic. Write COMPLETE, PRODUCTION-READY code. Export the main functionality using NAMED exports only. Return ONLY the code — no markdown, no explanations, no code fences.`,
  },
  {
    id: 'p2-weak-prompt',
    prompt: `Write a TypeScript file for a config module for a browser tic-tac-toe game. Include any configuration values the game needs.`,
  },
  {
    id: 'p3-multi-export',
    prompt: `Generate a SINGLE standalone TypeScript file for node "chess-board.ts". NODE DESCRIPTION: 8x8 chess board, legal move generation for all pieces, check detection. NODE TYPE: logic. Write COMPLETE, PRODUCTION-READY code with NAMED exports only. Return ONLY the code — no markdown, no explanations, no code fences.`,
  },
  {
    id: 'p4-cli-entry',
    prompt: `Generate a SINGLE standalone TypeScript file for node "main.ts". NODE DESCRIPTION: entry point that parses CLI args and runs a todo app loop. NODE TYPE: logic. Write COMPLETE, PRODUCTION-READY code with NAMED exports only. Return ONLY the code — no markdown, no explanations, no code fences.`,
  },
];

const FENCE_RE = /^\s*```/m;
const PROSE_RE = /In this solution|This code defines|Here's|Below is|Explanation:|Here is the|Sure, here/;
const STUB_RE = /not implemented|TODO:?\s*implement|coming soon|placeholder for|REAL FILE CONTENT/;

function askOllama(prompt) {
  const body = JSON.stringify({ model: 'qwen2.5-7b-instruct-uncensored', prompt, stream: false, options: { temperature: 0.2, num_predict: 700 } });
  const out = execSync(`curl -s -m 180 http://127.0.0.1:11434/api/generate -H 'Content-Type: application/json' -d '${body.replace(/'/g, "'\\''")}'`, { encoding: 'utf-8' });
  return JSON.parse(out).response || '';
}

function askDspark(prompt) {
  const body = JSON.stringify({ model: 'qwen2.5-7b-instruct-uncensored-dspark', messages: [{ role: 'user', content: prompt }], max_tokens: 700, temperature: 0.2 });
  const out = execSync(`curl -s -m 180 http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' -d '${body.replace(/'/g, "'\\''")}'`, { encoding: 'utf-8' });
  return JSON.parse(out).choices[0].message.content || '';
}

function compileCheck(code, id) {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'ab-quality-'));
  try {
    writeFileSync(path.join(dir, 'file.ts'), code, 'utf-8');
    writeFileSync(path.join(dir, 'package.json'), JSON.stringify({ type: 'module' }), 'utf-8');
    try {
      execSync(`cd ${dir} && npx --yes -p typescript@5.4 tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution bundler --skipLibCheck --allowImportingTsExtensions file.ts 2>&1`, { encoding: 'utf-8', stdio: 'pipe' });
      return { compiles: true, errors: 0 };
    } catch (e) {
      const errs = String(e.stderr || e.stdout || '');
      return { compiles: false, errors: (errs.match(/error TS\d+/g) || []).length, sample: errs.split('\n').slice(0, 3).join(' | ') };
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function score(code, id) {
  const c = compileCheck(code, id);
  return {
    fences: FENCE_RE.test(code),
    prose: PROSE_RE.test(code),
    stubs: STUB_RE.test(code),
    chars: code.length,
    ...c,
  };
}

console.log(`A/B: base (ollama qwen2.5-7b-instruct-uncensored) vs deployed R15 fine-tune (dspark :8000)\n`);
const results = [];
for (const { id, prompt } of PROMPTS) {
  console.log(`── ${id} ──`);
  const base = askOllama(prompt);
  const ft = askDspark(prompt);
  const sb = score(base, id);
  const sf = score(ft, id);
  results.push({ id, base: sb, ft: sf });
  console.log(`  base   : fences=${sb.fences} prose=${sb.prose} stubs=${sb.stubs} compiles=${sb.compiles} (${sb.errors} errs) chars=${sb.chars}`);
  console.log(`  R15-ft : fences=${sf.fences} prose=${sf.prose} stubs=${sf.stubs} compiles=${sf.compiles} (${sf.errors} errs) chars=${sf.chars}`);
  if (!sf.compiles && sf.errors > 0 && sf.sample) console.log(`           err sample: ${sf.sample.slice(0, 150)}`);
  if (!sb.compiles && sb.errors > 0 && sb.sample) console.log(`           base err sample: ${sb.sample.slice(0, 150)}`);
}

console.log(`\n=== SUMMARY (fewer flags = better) ===`);
console.log(`prompt            base[fen/prose/stub/compile]   R15[fen/prose/stub/compile]`);
for (const r of results) {
  const f = (s) => `${s.fences ? 'Y' : '-'}/${s.prose ? 'Y' : '-'}/${s.stubs ? 'Y' : '-'}/${s.compiles ? 'OK' : 'FAIL'}`;
  console.log(`${r.id.padEnd(18)} ${f(r.base).padEnd(30)} ${f(r.ft)}`);
}
