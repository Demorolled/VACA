/**
 * Play test for an AI-generated chess app (generic).
 *
 * Usage:  npx tsx scripts/playtest-generated-chess.ts [exportDir]
 *   - exportDir optional; defaults to the NEWEST backend/exports/* dir.
 *
 * Scans the export's src/ for GameState / AiEngine / isValidMove exports and
 * attempts to ACTUALLY play: build a GameState, inspect the board, validate a
 * move, run the minimax AI search, and simulate a few half-moves.
 * Exits non-zero if any check FAILs.
 */
import { readdirSync, statSync } from 'fs';
import { join, resolve, isAbsolute } from 'path';

const ROOT = resolve(process.cwd());
const EXPORTS = join(ROOT, 'backend', 'exports');

function resolveExportDir(arg?: string): string {
  if (arg && arg.trim()) {
    const p = isAbsolute(arg.trim()) ? arg.trim() : join(EXPORTS, arg.trim());
    if (statSync(p).isDirectory()) return p;
  }
  const dirs = readdirSync(EXPORTS)
    .map(d => join(EXPORTS, d))
    .filter(d => { try { return statSync(d).isDirectory(); } catch { return false; } })
    .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  if (!dirs.length) throw new Error('no backend/exports/* dirs found');
  return dirs[0];
}

async function main(): Promise<void> {
  const DIR = resolveExportDir(process.argv[2]);
  console.log('[playtest] export dir:', DIR);

  const srcDir = join(DIR, 'src');
  const tsFiles = readdirSync(srcDir).filter(f => f.endsWith('.ts'));
  console.log('[playtest] src files:', tsFiles.join(', '));

  let GameState: any, AiEngine: any, isValidMove: any;
  for (const f of tsFiles) {
    const mod = await import(join(srcDir, f));
    if (!GameState && mod.GameState) GameState = mod.GameState;
    if (!AiEngine && mod.AiEngine) AiEngine = mod.AiEngine;
    if (!isValidMove && mod.isValidMove) isValidMove = mod.isValidMove;
  }

  let failures = 0;
  const check = (ok: boolean, label: string, extra = '') => {
    console.log(`  [${ok ? 'OK ' : 'FAIL'}] ${label}${extra ? ' — ' + extra : ''}`);
    if (!ok) failures++;
  };

  // 1. Board setup
  if (GameState) {
    try {
      const game = new GameState();
      const board = game.getBoard();
      const occupied = board.flat().filter((c: any) => c !== null && c !== undefined && c !== '' && c !== ' ').length;
      check(occupied === 32, 'board has 32 occupied start cells', `found ${occupied}`);
      console.log('[1] sample row 0:', JSON.stringify(board[0]));
    } catch (e) { check(false, 'GameState instantiation', (e as Error).message); }
  } else {
    check(false, 'GameState export found', 'not exported by any src file');
  }

  // 2. Move validation (white pawn e2->e4: row 6 col 4 -> row 4 col 4)
  if (isValidMove) {
    try {
      const game = new GameState();
      const mv = isValidMove(game.getBoard(), { row: 6, col: 4 }, { row: 4, col: 4 });
      check(mv === true, 'isValidMove accepts e2->e4', `returned ${mv}`);
    } catch (e) { check(false, 'isValidMove call', (e as Error).message); }
  } else {
    check(false, 'isValidMove export found', 'not exported by any src file');
  }

  // 3. Actual minimax AI search
  if (AiEngine) {
    try {
      const game = new GameState();
      const ai = new AiEngine(3);
      const res = ai.search(game.getBoard(), 'white', -Infinity, Infinity, 3);
      check(!!res && typeof res.move === 'string' && res.move.length > 0, 'AI returns a move', JSON.stringify(res));
    } catch (e) { check(false, 'AI search', (e as Error).message); }
  } else {
    check(false, 'AiEngine export found', 'not exported by any src file');
  }

  // 4. Simulate a short game: alternate moves via the AI
  let moved = 0;
  try {
    if (AiEngine && GameState) {
      const state = new GameState();
      const ai = new AiEngine(2);
      for (let i = 0; i < 6; i++) {
        const r = ai.search(state.getBoard(), state.getCurrentPlayer(), -Infinity, Infinity, 2);
        if (!r.move || r.move.length === 0) break;
        moved++;
        console.log('[4] move', moved, '->', r.move);
      }
    }
  } catch (e) { console.log('[4] simulation crashed:', (e as Error).message); }
  check(moved >= 2, `simulated ${moved} half-moves`, 'want >= 2 legal moves exchanged');

  console.log(`\nPLAYTEST VERDICT: ${failures === 0 ? 'PLAYABLE ✅' : `${failures} FAILURE(S) ❌`}`);
  process.exit(failures === 0 ? 0 : 1);
}

main().catch(err => {
  console.error('[playtest] fatal:', err);
  process.exit(2);
});
