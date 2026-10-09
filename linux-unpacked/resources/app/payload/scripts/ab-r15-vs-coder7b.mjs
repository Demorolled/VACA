#!/usr/bin/env node
/**
 * A/B test: deployed R15 fine-tune (dspark :8000) vs qwen2.5-coder:7b (ollama)
 * on the ACTUAL failing scenarios from the triage builds:
 *   1. ai.ts — must call ONLY the declared Game members (the TS2339 invented-member class)
 *   2. config.ts — browser game config, must NOT emit server secrets (the DATABASE_URL class)
 *   3. chess logic — legal move generation (the "3d chess" class)
 *   4. multi-file contract — ai.ts imports grid.ts; both compile together (the cross-file class)
 *
 * Both models get the same prompts (chat format, system prompt demanding raw code).
 * Scoring: fences, prose, stub markers, and tsc --strict compile (single-file for 1-3,
 * two-file project for 4). 4 prompts x 2 models = 8 LLM calls (~3-5 min).
 *
 * Usage: node scripts/ab-r15-vs-coder7b.mjs
 */
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { execSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';

const SYSTEM = 'You are an expert TypeScript engineer. You write COMPLETE, PRODUCTION-READY, COMPILING code. You return ONLY the code — no markdown code fences, no prose, no explanations, no bullet lists, no leading/trailing commentary. The code must compile under tsc --strict with zero errors.';

const SCENARIOS = [
  {
    id: '1-ai-invented-members',
    prompt: `Generate a SINGLE standalone TypeScript file for node "ai.ts".
NODE DESCRIPTION: minimax AI opponent for tic-tac-toe that picks the best move.
NODE TYPE: logic. Language: typescript.
This file can import from sibling file grid.ts (exports: Game class with members: cells, makeMove(row: number, col: number): void, checkWinner(): { winner: string | null; line: number[] } | null, reset(): void, isFull(): boolean).
MEMBER WHITELIST RULE: you may ONLY call the members listed in braces. NEVER invent a method (no Game.getEmptyCells(), no Game.clone(), no Game.availableMoves()).
Export a function named chooseBestMove(game: Game): { row: number; col: number } using ONLY the whitelisted members. Write COMPLETE, PRODUCTION-READY code. Named exports only. Return ONLY the code.`,
  },
  {
    id: '2-browser-config',
    prompt: `Generate a SINGLE standalone TypeScript file for node "config.ts".
NODE DESCRIPTION: configuration for a browser-only tic-tac-toe web game (two players, local, no backend).
NODE TYPE: config. Language: typescript.
CRITICAL: this is a CLIENT-ONLY app — NO database, NO secrets, NO server config. Never emit DATABASE_URL, SECRET_KEY, API_KEY, process.env, or placeholder secrets.
Export constants the game needs: board size, player symbols, win length, restart label, css class names.
Write COMPLETE, PRODUCTION-READY code. Named exports only. Return ONLY the code.`,
  },
  {
    id: '3-chess-logic',
    prompt: `Generate a SINGLE standalone TypeScript file for node "chess-logic.ts".
NODE DESCRIPTION: chess rules — legal move generation for all pieces, check detection, move application.
NODE TYPE: logic. Language: typescript.
Export: type Piece = { type: 'pawn'|'rook'|'knight'|'bishop'|'queen'|'king'; color: 'white'|'black' }; class ChessBoard with methods getPiece(square: string): Piece | null, setPiece(square: string, piece: Piece | null): void, legalMoves(square: string): string[], isInCheck(color: 'white'|'black'): boolean.
Write COMPLETE, PRODUCTION-READY code that compiles with tsc --strict. Named exports only. Return ONLY the code.`,
  },
  {
    id: '4-multifile-contract',
    files: ['grid.ts', 'ai.ts'],
    prompt: (file) => file === 'grid.ts'
      ? `Generate TypeScript file "grid.ts": a 3x3 tic-tac-toe Game class. NODE TYPE: logic.
Exports: class Game with constructor(), cells: (string|null)[], makeMove(row: number, col: number): void, checkWinner(): { winner: string | null; line: number[] } | null, reset(): void, isFull(): boolean.
Write COMPLETE code that compiles under tsc --strict. Named exports only. Return ONLY the code.`
      : `Generate TypeScript file "ai.ts" that imports from "./grid.ts".
NODE DESCRIPTION: minimax AI opponent that picks the best move.
Import ONLY: import { Game } from './grid.ts';
The Game class has ONLY these members: cells: (string|null)[], makeMove(row: number, col: number): void, checkWinner(): { winner: string | null; line: number[] } | null, reset(): void, isFull(): boolean.
MEMBER WHITELIST RULE: you may ONLY call the members listed above. NEVER invent a method (no getEmptyCells, no clone, no availableMoves).
Export function chooseBestMove(game: Game): { row: number; col: number } using ONLY the whitelisted members (you may read game.cells directly).
Write COMPLETE code that compiles under tsc --strict with zero errors. Named exports only. Return ONLY the code.`,
  },
];

const FENCE_RE = /^\s*```/m;
const PROSE_RE = /In this solution|This code defines|Here's|Below is|Explanation:|Here is the|Sure, here/;
const STUB_RE = /not implemented|TODO:?\s*implement|coming soon|placeholder for|REAL FILE CONTENT/;
const SECRET_RE = /DATABASE_URL|SECRET_KEY|API_KEY|yourSecretKeyHere|yourApiKeyHere/;

function askDspark(system, user) {
  const body = JSON.stringify({ model: 'qwen2.5-7b-instruct-uncensored-dspark', messages: [{ role: 'system', content: system }, { role: 'user', content: user }], max_tokens: 1200, temperature: 0.2 });
  const out = execSync(`curl -s -m 240 http://127.0.0.1:8000/v1/chat/completions -H 'Content-Type: application/json' -d '${body.replace(/'/g, "'\\''")}'`, { encoding: 'utf-8' });
  return JSON.parse(out).choices[0].message.content || '';
}

function askOllamaChat(model, system, user) {
  const body = JSON.stringify({ model, messages: [{ role: 'system', content: system }, { role: 'user', content: user }], stream: false, options: { temperature: 0.2, num_predict: 1200 } });
  const out = execSync(`curl -s -m 240 http://127.0.0.1:11434/api/chat -H 'Content-Type: application/json' -d '${body.replace(/'/g, "'\\''")}'`, { encoding: 'utf-8' });
  return JSON.parse(out).message.content || '';
}

function stripFences(code) {
  // If the model wrapped in fences anyway, extract the code block for the compile check
  const m = code.match(/```(?:ts|typescript)?\s*\n([\s\S]*?)```/);
  return m ? m[1] : code;
}

function compileOne(dir, name, code) {
  writeFileSync(path.join(dir, name), stripFences(code), 'utf-8');
}
function compileCheck(dir) {
  try {
    execSync(`cd ${dir} && npx --yes -p typescript@5.4 tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution bundler --skipLibCheck --allowImportingTsExtensions *.ts 2>&1`, { encoding: 'utf-8', stdio: 'pipe' });
    return { compiles: true, errors: 0, sample: '' };
  } catch (e) {
    const errs = String(e.stderr || e.stdout || '');
    return { compiles: false, errors: (errs.match(/error TS\d+/g) || []).length, sample: errs.split('\n').slice(0, 3).join(' | ') };
  }
}

const CODER_MODEL = process.env.CODER_MODEL || 'qwen2.5-coder:7b';

console.log(`A/B: deployed R15 (dspark :8000) vs ${CODER_MODEL} (ollama) — 4 real failing scenarios\n`);
const rows = [];
for (const sc of SCENARIOS) {
  console.log(`── ${sc.id} ──`);
  const collect = (ask) => {
    if (sc.files) {
      const dir = mkdtempSync(path.join(os.tmpdir(), 'ab-multi-'));
      try {
        for (const f of sc.files) compileOne(dir, f, ask(SYSTEM, sc.prompt(f)));
        const r = compileCheck(dir);
        const all = sc.files.map(f => ({ f, src: read(dir, f) }));
        return { dir, ...r, all };
      } catch { return { dir, compiles: false, errors: -1, sample: 'call error', all: [] }; }
    } else {
      const code = ask(SYSTEM, sc.prompt);
      const dir = mkdtempSync(path.join(os.tmpdir(), 'ab-single-'));
      try {
        compileOne(dir, 'file.ts', code);
        const r = compileCheck(dir);
        return { dir, code, ...r };
      } catch { return { dir, code, compiles: false, errors: -1, sample: 'call error' }; }
    }
  };
  const read = (dir, f) => { try { return require('node:fs').readFileSync(path.join(dir, f), 'utf-8'); } catch { return ''; } };

  let r15, coder;
  try { r15 = collect(askDspark); } catch (e) { r15 = { compiles: false, errors: -1, sample: 'dspark error: ' + e.message }; }
  try { coder = collect(askOllamaChat.bind(null, CODER_MODEL)); } catch (e) { coder = { compiles: false, errors: -1, sample: 'ollama error: ' + e.message }; }

  const s = (r) => {
    if (!r.code && !r.all) return `fences=? prose=? stubs=? secrets=? compiles=${r.compiles} (${r.errors}) ${r.sample || ''}`;
    const text = r.code || (r.all || []).map(x => x.src).join('\n');
    return `fences=${FENCE_RE.test(text)} prose=${PROSE_RE.test(text)} stubs=${STUB_RE.test(text)} secrets=${SECRET_RE.test(text)} compiles=${r.compiles} (${r.errors} errs)${r.sample ? ' ' + r.sample.slice(0, 140) : ''}`;
  };
  rows.push({ id: sc.id, r15, coder });
  console.log(`  R15   : ${s(r15)}`);
  console.log(`  coder7: ${s(coder)}`);
  for (const [name, r] of [['R15', r15], ['coder7', coder]]) {
    if (r.dir) { try { rmSync(r.dir, { recursive: true, force: true }); } catch {} }
  }
}

console.log(`\n=== SUMMARY ===`);
console.log(`scenario             R15 (compiles/errs)   ${CODER_MODEL} (compiles/errs)`);
for (const r of rows) {
  const f = (x) => `${x.compiles ? 'OK' : 'FAIL'} (${x.errors})`;
  console.log(`${r.id.padEnd(22)} ${f(r.r15).padEnd(22)} ${f(r.coder)}`);
}
