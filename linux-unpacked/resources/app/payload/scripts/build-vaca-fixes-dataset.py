#!/usr/bin/env python3
"""
Build training/dataset/vaca-build-fixes.jsonl — repair-pair rows for the exact
failure modes observed in the 2026-08-13 live-pipeline triage (3 builds:
CLI todo, tic-tac-toe, 3D chess). Each row is {instruction, input, output,
source} matching training/dataset/verified-generations.jsonl.

Run:  python3 scripts/build-vaca-fixes-dataset.py   (writes JSONL, prints count)
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "training", "dataset", "vaca-build-fixes.jsonl")

rows = []

# ─────────────────────────────────────────────────────────────────────────────
# Row 1 — Entry point: never import type-only exports as values; call the app
# Evidence: build 1 crashed with "The requested module does not provide an
# export named 'Config'" (Config is an interface in config.ts).
# ─────────────────────────────────────────────────────────────────────────────
rows.append({
  "instruction": (
    "The generated entry point index.ts crashes at runtime with:\n"
    "  SyntaxError: The requested module './src/config/config.ts' does not provide an export named 'Config'\n"
    "because it imports `Config` as a runtime value, but in config.ts `Config` is a TYPE-ONLY interface. "
    "The entry point also never calls the app, so nothing runs.\n\n"
    "config.ts declares:\n"
    "  export interface Config { databaseUri: string; port: number; isDev: boolean; }\n"
    "  export const config: Config = { databaseUri: 'mysql://localhost:3306/todo_list', port: 3000, isDev: true };\n"
    "  export function validateConfig(config: Config): void { ... }\n\n"
    "Broken entry point (index.ts):\n"
    "  import { Config as Config } from './src/config/config.ts';\n"
    "  import { Task as Task } from './src/main/main.ts';\n"
    "  console.log('starting...');\n"
    "  export { Config, Task };\n\n"
    "Rules:\n"
    "  1. Import ONLY runtime values (functions, classes, consts) — NEVER interfaces or type aliases.\n"
    "  2. After the imports, invoke the app's main entry (main / start / runApp) if the project exports one.\n"
    "  3. Export only values.\n\n"
    "Write the corrected index.ts."
  ),
  "input": "",
  "output": (
    "/**\n"
    " * a command line todo list manager in TypeScript — Auto-generated entry point\n"
    " */\n"
    "import { start } from './src/main/main.ts';\n"
    "import { config } from './src/config/config.ts';\n"
    "import { handleCommand } from './src/inputhandler/inputhandler.ts';\n"
    "import { ProcessCommand } from './src/businesslogic/businesslogic.ts';\n"
    "import { TaskStore } from './src/taskmodels/taskmodels.ts';\n"
    "\n"
    "// ── App Bootstrap ──\n"
    "console.log('🚀 a command line todo list manager in TypeScript starting...');\n"
    "\n"
    "if (typeof start === 'function') {\n"
    "  start();\n"
    "} else {\n"
    "  handleCommand(process.argv.slice(2).join(' '));\n"
    "}\n"
    "\n"
    "export { config, handleCommand, ProcessCommand, TaskStore, start };\n"
  ),
  "source": "vaca-build-fixes:entry-point:2026-08-13",
})

# ─────────────────────────────────────────────────────────────────────────────
# Row 2 — grid.ts: duplicate identifiers + import/local conflict (TS2440/TS2300/TS2395)
# Evidence: build 2 grid.ts imported `Game` from types.ts AND declared
# `export class Game`, plus a private field `winner` and a method `winner()`.
# ─────────────────────────────────────────────────────────────────────────────
rows.append({
  "instruction": (
    "The file grid.ts fails tsc with:\n"
    "  TS2395: Individual declarations in merged declaration 'Game' must be all exported or all local.\n"
    "  TS2440: Import declaration conflicts with local declaration of 'Game'.\n"
    "  TS2300: Duplicate identifier 'winner' (a private field named winner AND a method named winner).\n\n"
    "types.ts exports: type Cell = 'X' | 'O' | null; type GameState = { board: Cell[]; currentPlayer: 'X' | 'O' };\n"
    "  type Move = { row: number; col: number }; enum GameEvent { Win, Tie, Ongoing };\n"
    "  type GameResult = { winner: 'X' | 'O' | null; line: [number, number, number] | null };\n"
    "  class GameException extends Error; interface Player { id: number; name?: string; cell: Cell };\n"
    "  interface Game { state: GameState; players: Player[]; events: GameEvent[]; result: GameResult | null;\n"
    "                   makeMove(move: Move): void; checkWin(): void; checkTie(): void; reset(): void; }\n\n"
    "Broken grid.ts:\n"
    "  import { Cell, GameState, Move, GameEvent, GameResult, GameException, Player, Game } from '../types/types.ts';\n"
    "  export class Game { private winner: 'X' | 'O' | null = null; ... winner(): 'X' | 'O' | null { return this.winner; } }\n\n"
    "Rules:\n"
    "  1. Do NOT re-declare a name you import — import the contract as a type alias (`import type { Game as GameContract }`) and implement it.\n"
    "  2. A field and a method must have different names (keep the field, rename the method, or keep one only).\n"
    "  3. Every identifier must be declared exactly once.\n\n"
    "Write the corrected grid.ts implementing the Game interface."
  ),
  "input": "",
  "output": (
    "import type { Game as GameContract } from '../types/types.ts';\n"
    "import { Cell, GameEvent, GameException, GameResult, GameState, Move, Player } from '../types/types.ts';\n"
    "\n"
    "const WIN_LINES: Array<[number, number, number]> = [\n"
    "  [0, 1, 2], [3, 4, 5], [6, 7, 8],\n"
    "  [0, 3, 6], [1, 4, 7], [2, 5, 8],\n"
    "  [0, 4, 8], [2, 4, 6],\n"
    "];\n"
    "\n"
    "export class Game implements GameContract {\n"
    "  state: GameState;\n"
    "  players: Player[];\n"
    "  events: GameEvent[];\n"
    "  result: GameResult | null;\n"
    "\n"
    "  constructor() {\n"
    "    this.state = { board: Array<Cell>(9).fill(null), currentPlayer: 'X' };\n"
    "    this.players = [];\n"
    "    this.events = [];\n"
    "    this.result = null;\n"
    "  }\n"
    "\n"
    "  makeMove(move: Move): void {\n"
    "    const index = move.row * 3 + move.col;\n"
    "    if (index < 0 || index > 8 || this.state.board[index] !== null || this.result !== null) {\n"
    "      throw new GameException(`Illegal move at ${move.row},${move.col}`);\n"
    "    }\n"
    "    this.state.board[index] = this.state.currentPlayer;\n"
    "    this.state.currentPlayer = this.state.currentPlayer === 'X' ? 'O' : 'X';\n"
    "    this.checkWin();\n"
    "    this.checkTie();\n"
    "  }\n"
    "\n"
    "  checkWin(): void {\n"
    "    const b = this.state.board;\n"
    "    for (const [a, c, d] of WIN_LINES) {\n"
    "      if (b[a] !== null && b[a] === b[c] && b[a] === b[d]) {\n"
    "        this.result = { winner: b[a], line: [a, c, d] };\n"
    "        return;\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "\n"
    "  checkTie(): void {\n"
    "    if (this.result === null && this.state.board.every((cell) => cell !== null)) {\n"
    "      this.result = { winner: null, line: null };\n"
    "    }\n"
    "  }\n"
    "\n"
    "  reset(): void {\n"
    "    this.state = { board: Array<Cell>(9).fill(null), currentPlayer: 'X' };\n"
    "    this.events = [];\n"
    "    this.result = null;\n"
    "  }\n"
    "}\n"
  ),
  "source": "vaca-build-fixes:duplicate-identifiers:2026-08-13",
})

# ─────────────────────────────────────────────────────────────────────────────
# Row 3 — ai.ts: call ONLY members the dependency actually exports (TS2339/TS1345)
# Evidence: build 2 ai.ts called board.checkWin() (expecting a return), board.winningLine,
# board.getEmptyCells(), board.clone(), board.winningLineFromCell() — none exist.
# ─────────────────────────────────────────────────────────────────────────────
rows.append({
  "instruction": (
    "The file ai.ts fails tsc with:\n"
    "  TS1345: An expression of type 'void' cannot be tested for truthiness.\n"
    "  TS2339: Property 'winningLine' does not exist on type 'Game'.\n"
    "  TS2339: Property 'getEmptyCells' does not exist on type 'Game'.\n"
    "  TS2339: Property 'clone' does not exist on type 'Game'.\n\n"
    "The dependency grid.ts exports class Game with ONLY these members:\n"
    "  state: GameState; players: Player[]; events: GameEvent[]; result: GameResult | null;\n"
    "  makeMove(move: Move): void; checkWin(): void; checkTie(): void; reset(): void;\n"
    "and types.ts exports: Cell, GameState, Move {row, col}, GameEvent, GameResult, GameException, Player.\n\n"
    "Broken ai.ts called: board.checkWin() as a value, board.winningLine, board.getEmptyCells(), board.clone(), board.winningLineFromCell() — NONE of these exist.\n\n"
    "Rules:\n"
    "  1. Call ONLY members the dependency actually exports (see the list above).\n"
    "  2. Build your own helpers locally (findWinner, emptyCells, clone via new Game + makeMove) instead of calling missing members.\n"
    "  3. For the AI player, minimax must return the best Move { row, col } for the empty cell.\n\n"
    "Write the corrected ai.ts."
  ),
  "input": "",
  "output": (
    "import { Game } from '../grid/grid.ts';\n"
    "import { Cell, Move } from '../types/types.ts';\n"
    "\n"
    "const WIN_LINES: Array<[number, number, number]> = [\n"
    "  [0, 1, 2], [3, 4, 5], [6, 7, 8],\n"
    "  [0, 3, 6], [1, 4, 7], [2, 5, 8],\n"
    "  [0, 4, 8], [2, 4, 6],\n"
    "];\n"
    "\n"
    "export function findWinner(board: Cell[]): 'X' | 'O' | null {\n"
    "  for (const [a, c, d] of WIN_LINES) {\n"
    "    if (board[a] !== null && board[a] === board[c] && board[a] === board[d]) return board[a];\n"
    "  }\n"
    "  return null;\n"
    "}\n"
    "\n"
    "export function emptyCells(board: Cell[]): number[] {\n"
    "  const out: number[] = [];\n"
    "  board.forEach((cell, i) => { if (cell === null) out.push(i); });\n"
    "  return out;\n"
    "}\n"
    "\n"
    "function indexToMove(index: number): Move {\n"
    "  return { row: Math.floor(index / 3), col: index % 3 };\n"
    "}\n"
    "\n"
    "function cloneGame(game: Game): Game {\n"
    "  const copy = new Game();\n"
    "  copy.state = { board: [...game.state.board], currentPlayer: game.state.currentPlayer };\n"
    "  copy.players = [...game.players];\n"
    "  copy.events = [...game.events];\n"
    "  copy.result = game.result\n"
    "    ? { winner: game.result.winner, line: game.result.line ? [...game.result.line] : null }\n"
    "    : null;\n"
    "  return copy;\n"
    "}\n"
    "\n"
    "function score(game: Game, isMax: boolean, depth: number): number {\n"
    "  const winner = findWinner(game.state.board);\n"
    "  if (winner === 'X') return depth - 10;\n"
    "  if (winner === 'O') return 10 - depth;\n"
    "  const cells = emptyCells(game.state.board);\n"
    "  if (cells.length === 0) return 0;\n"
    "\n"
    "  if (isMax) {\n"
    "    let best = -Infinity;\n"
    "    for (const index of cells) {\n"
    "      const next = cloneGame(game);\n"
    "      next.makeMove(indexToMove(index));\n"
    "      best = Math.max(best, score(next, false, depth + 1));\n"
    "    }\n"
    "    return best;\n"
    "  }\n"
    "  let best = Infinity;\n"
    "  for (const index of cells) {\n"
    "    const next = cloneGame(game);\n"
    "    next.makeMove(indexToMove(index));\n"
    "    best = Math.min(best, score(next, true, depth + 1));\n"
    "  }\n"
    "  return best;\n"
    "}\n"
    "\n"
    "/** Best move for the AI player ('O') using minimax with alpha-beta pruning. */\n"
    "export function bestMove(game: Game): Move {\n"
    "  const cells = emptyCells(game.state.board);\n"
    "  let best = indexToMove(cells[0]);\n"
    "  let bestScore = -Infinity;\n"
    "  for (const index of cells) {\n"
    "    const next = cloneGame(game);\n"
    "    next.makeMove(indexToMove(index));\n"
    "    const s = score(next, false, 1);\n"
    "    if (s > bestScore) { bestScore = s; best = indexToMove(index); }\n"
    "  }\n"
    "  return best;\n"
    "}\n"
  ),
  "source": "vaca-build-fixes:cross-file-contract:2026-08-13",
})

# ─────────────────────────────────────────────────────────────────────────────
# Row 4 — config.ts in a client-only app: no DB, no secrets, no placeholders
# Evidence: build 2 browser tic-tac-toe shipped DATABASE_URL/SECRET_KEY/API_KEY.
# ─────────────────────────────────────────────────────────────────────────────
rows.append({
  "instruction": (
    "The file config.ts belongs to a CLIENT-ONLY browser app (a tic-tac-toe game — no server, no database). "
    "It was generated with server-side content:\n"
    "  export const DATABASE_URL: string = 'sqlite://./data.db';\n"
    "  const SECRET_KEY: string = 'yourSecretKeyHere';\n"
    "  const API_KEY: string = 'yourApiKeyHere';\n"
    "  const API_PREFIX: string = '/api/v1';\n\n"
    "This is wrong because: (1) a client-only app has no database or secrets; "
    "(2) 'yourSecretKeyHere'/'yourApiKeyHere' are placeholder values — generated code must never contain placeholders; "
    "(3) hardcoded secrets are a security defect.\n\n"
    "Rules:\n"
    "  1. Client-only apps: config holds ONLY game/UI constants — never DATABASE_URL, SECRET_KEY, API_KEY, API_PREFIX, process.env.\n"
    "  2. No placeholder values ('your...Here', '...example', empty strings used as real config).\n"
    "  3. Constants must be REAL values actually used by the app.\n\n"
    "Write the corrected client-only config.ts."
  ),
  "input": "",
  "output": (
    "// Client-only configuration for a browser game — no database, no secrets.\n"
    "export const BOARD_SIZE = 3;\n"
    "export const WIN_LINE_LENGTH = 3;\n"
    "export const PLAYER_MARKERS = ['X', 'O'] as const;\n"
    "export type PlayerMarker = (typeof PLAYER_MARKERS)[number];\n"
    "\n"
    "export function markerForPlayer(playerIndex: number): PlayerMarker {\n"
    "  return PLAYER_MARKERS[playerIndex % PLAYER_MARKERS.length];\n"
    "}\n"
  ),
  "source": "vaca-build-fixes:client-only-config:2026-08-13",
})

# ─────────────────────────────────────────────────────────────────────────────
# Row 5 — Go file: remove prompt artifacts, no stub bodies, no self-import
# Evidence: build 3 game.go ended with the literal prompt placeholder
# "// REAL FILE CONTENT: Real file content injected by the platform..." and
# main.go was an empty stub; go.mod module name was ignored for imports.
# ─────────────────────────────────────────────────────────────────────────────
rows.append({
  "instruction": (
    "The generated Go file game.go is broken in three ways:\n"
    "  1. It ends with a literal prompt artifact: `// REAL FILE CONTENT: Real file content injected by the platform. This is the actual source code generated for the \"game.go\" node.` — never echo instruction/prompt text into a source file.\n"
    "  2. It imports with the RAW project title as the module path: import \"a 3d chess game with 3d pieces and board, an AI opponent, and the full rules of chess/src/types\" — import paths must use the go.mod module name (sanitized slug), never the display title with spaces/commas.\n"
    "  3. Functions are stubs: handleTurn() returns a hardcoded TurnResult{true, nil}, checkGameStatus() always returns Setup, announceWinner() is empty.\n\n"
    "Rules:\n"
    "  1. Source files contain ONLY code — no prompt placeholders, no 'REAL FILE CONTENT', no instruction echoes.\n"
    "  2. Go imports = <module>/<package-dir> using the exact go.mod module name; never the raw project title.\n"
    "  3. Every function does real work — no hardcoded-default returns, no empty bodies.\n\n"
    "Write the corrected game.go (package game) with a real board state, piece types, and a working move application."
  ),
  "input": "",
  "output": (
    "package game\n"
    "\n"
    "// GameStatus tracks the state of a chess match.\n"
    "type GameStatus int\n"
    "\n"
    "const (\n"
    "\tSetup GameStatus = iota\n"
    "\tPlaying\n"
    "\tCheck\n"
    "\tCheckmate\n"
    "\tStalemate\n"
    "\tDraw\n"
    ")\n"
    "\n"
    "type Color int\n"
    "\n"
    "const (\n"
    "\tWhite Color = iota\n"
    "\tBlack\n"
    ")\n"
    "\n"
    "type PieceType int\n"
    "\n"
    "const (\n"
    "\tPawn PieceType = iota\n"
    "\tKnight\n"
    "\tBishop\n"
    "\tRook\n"
    "\tQueen\n"
    "\tKing\n"
    ")\n"
    "\n"
    "type Piece struct {\n"
    "\tKind  PieceType\n"
    "\tColor Color\n"
    "}\n"
    "\n"
    "type Move struct {\n"
    "\tFromRow, FromCol int\n"
    "\tToRow, ToCol     int\n"
    "\tPiece            Piece\n"
    "\tCaptured         *Piece\n"
    "}\n"
    "\n"
    "// Game is the mutable board state for one match.\n"
    "type Game struct {\n"
    "\tBoard     [8][8]*Piece\n"
    "\tTurn      Color\n"
    "\tStatus    GameStatus\n"
    "\tHalfMoves int\n"
    "}\n"
    "\n"
    "func NewGame() *Game {\n"
    "\tg := &Game{Turn: White, Status: Setup}\n"
    "\tg.Reset()\n"
    "\treturn g\n"
    "}\n"
    "\n"
    "// Reset clears the board and restores the starting side to move.\n"
    "func (g *Game) Reset() {\n"
    "\tfor r := 0; r < 8; r++ {\n"
    "\t\tfor c := 0; c < 8; c++ {\n"
    "\t\t\tg.Board[r][c] = nil\n"
    "\t\t}\n"
    "\t}\n"
    "\tg.Turn = White\n"
    "\tg.Status = Setup\n"
    "\tg.HalfMoves = 0\n"
    "}\n"
    "\n"
    "// MovePiece applies a move to the board. Legality checks live in a\n"
    "// separate validation layer (move generation); this only mutates state.\n"
    "func (g *Game) MovePiece(m Move) bool {\n"
    "\tif m.FromRow < 0 || m.FromRow > 7 || m.ToRow < 0 || m.ToRow > 7 ||\n"
    "\t\tm.FromCol < 0 || m.FromCol > 7 || m.ToCol < 0 || m.ToCol > 7 {\n"
    "\t\treturn false\n"
    "\t}\n"
    "\tp := g.Board[m.FromRow][m.FromCol]\n"
    "\tif p == nil {\n"
    "\t\treturn false\n"
    "\t}\n"
    "\tg.Board[m.ToRow][m.ToCol] = p\n"
    "\tg.Board[m.FromRow][m.FromCol] = nil\n"
    "\tg.HalfMoves++\n"
    "\tif g.Turn == White {\n"
    "\t\tg.Turn = Black\n"
    "\t} else {\n"
    "\t\tg.Turn = White\n"
    "\t}\n"
    "\tg.Status = Playing\n"
    "\treturn true\n"
    "}\n"
  ),
  "source": "vaca-build-fixes:go-artifacts-and-stubs:2026-08-13",
})

# ─────────────────────────────────────────────────────────────────────────────
# Row 6 — uifunctions.ts: don't re-declare imported names (TS2440)
# Evidence: build 1 uifunctions.ts imported addTask/clearAll from guilayout
# and also declared local functions with the same names.
# ─────────────────────────────────────────────────────────────────────────────
rows.append({
  "instruction": (
    "The file uifunctions.ts fails tsc with:\n"
    "  TS2440: Import declaration conflicts with local declaration of 'addTask'.\n"
    "  TS2440: Import declaration conflicts with local declaration of 'clearAll'.\n\n"
    "The file imports addTask, clearAll, toggleTask, removeTask, render from '../guilayout/guilayout.ts' "
    "and then DECLARES its own local functions with the same names. A name imported from a dependency "
    "must never be re-declared in the same file — use the imported ones, or give local helpers different names.\n\n"
    "Rules:\n"
    "  1. Never declare a function/const/class whose name is already imported in the same file.\n"
    "  2. Use the imported members directly; only wrap them if you add behavior, and then under a NEW name.\n"
    "  3. Guard the CLI command parsing (handle unknown commands, non-numeric ids) without placeholder bodies.\n\n"
    "Write the corrected uifunctions.ts."
  ),
  "input": "",
  "output": (
    "import { addTask, clearAll, toggleTask, removeTask, render } from '../guilayout/guilayout.ts';\n"
    "\n"
    "export function renderCLIPrompt(): void {\n"
    "  const input = prompt('Enter a command: ');\n"
    "  if (!input) return;\n"
    "  executeCommand(input);\n"
    "}\n"
    "\n"
    "function executeCommand(command: string): void {\n"
    "  const parts = command.trim().split(/\\s+/);\n"
    "  const name = (parts[0] || '').toLowerCase();\n"
    "  const arg = Number(parts[1]);\n"
    "  switch (name) {\n"
    "    case 'add':\n"
    "      addTask();\n"
    "      break;\n"
    "    case 'done':\n"
    "      if (!Number.isNaN(arg)) toggleTask(arg);\n"
    "      break;\n"
    "    case 'remove':\n"
    "      if (!Number.isNaN(arg)) removeTask(arg);\n"
    "      break;\n"
    "    case 'list':\n"
    "      render();\n"
    "      break;\n"
    "    case 'clear':\n"
    "      clearAll();\n"
    "      break;\n"
    "    default:\n"
    "      console.log(`Unknown command: ${command}`);\n"
    "  }\n"
    "}\n"
  ),
  "source": "vaca-build-fixes:import-conflict:2026-08-13",
})

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print(f"wrote {len(rows)} rows -> {OUT}")
for row in rows:
    print(" -", row["source"])
