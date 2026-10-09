#!/usr/bin/env python3
"""
A/B: tuned (dspark :8000) vs stock (Ollama :11434) under REAL pipeline conditions.

Reconstructs the actual fileGenerator prompt template from backend/src/layers/fileGenerator.ts
verbatim (template, scale section, dep context, GUI widget context, language hints,
requirements 1-11), uses the real VACA system prompt (soul modifier + identity block),
and the real sampling params: temperature 0.7, repeat_penalty 1.15, frequency_penalty 0.3,
presence_penalty 0.2, num_ctx 8192, max_tokens 4096.

Tasks:
  engine -> logic node "chess-ai-engine" (minimax AI) with contract scaffold + tsc + functional test
  ui     -> ui node "chess-ui" (renders the board) with real GUI widget context, JSX/over-escape gates

Usage: python3 scripts/ab-pipeline-chess.py <tuned|stock> <engine|ui>
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request, datetime

MODEL_TAG = sys.argv[1] if len(sys.argv) > 1 else 'tuned'
TASK = sys.argv[2] if len(sys.argv) > 2 else 'engine'

TUNED = ('http://127.0.0.1:8000/v1', 'qwen2.5-7b-instruct-uncensored-dspark')
STOCK = ('http://127.0.0.1:11434/v1', 'qwen2.5-7b-instruct-uncensored')
URL, MODEL = TUNED if MODEL_TAG == 'tuned' else STOCK

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DIR = os.path.join(PROJECT_ROOT, 'data', 'ab-test-chess-pipeline',
                       f'run-{datetime.datetime.now():%Y%m%d-%H%M%S}-{MODEL_TAG}')
os.makedirs(RUN_DIR, exist_ok=True)

# ────────────────────────── soul modifier (mirrors soulService.ts) ──────────────────────────
TRAITS = {"warmth": 40, "sassiness": 40, "verbosity": 35, "technical_depth": 74,
          "creativity": 80, "empathy": 30, "formality": 30, "proactiveness": 90,
          "curiosity": 85, "patience": 50}

def soul_modifier(t):
    d = []
    d.append('warm and friendly' if t['warmth'] > 70 else ('pleasant' if t['warmth'] > 30 else 'cool and professional'))
    d.append('playfully sarcastic' if t['sassiness'] > 70 else ('occasionally witty' if t['sassiness'] > 50 else ('straightforward' if t['sassiness'] > 30 else 'earnest and direct')))
    d.append('detailed and thorough' if t['verbosity'] > 70 else ('explanatory' if t['verbosity'] > 50 else 'concise'))
    d.append('empathetic and understanding' if t['empathy'] > 60 else ('considerate' if t['empathy'] > 30 else 'focused on results'))
    d.append('formal and precise' if t['formality'] > 70 else ('semi-formal' if t['formality'] > 40 else 'casual and relaxed'))
    d.append('creative and inventive' if t['creativity'] > 70 else ('practical' if t['creativity'] > 40 else 'by-the-book'))
    d.append('proactive and initiative-taking' if t['proactiveness'] > 60 else 'responsive')
    d.append('inquisitive and exploratory' if t['curiosity'] > 70 else 'focused')
    d.append('patient and thorough' if t['patience'] > 60 else ('patient' if t['patience'] > 30 else 'impatient with inefficiency'))
    return '\n'.join(d)

# ────────────────────────── real VACA system prompt (translator.ts reason()) ──────────────────────────
SYSTEM = f"""{soul_modifier(TRAITS)}

You are VACA, the Visual AI Code Architect application. You are a self-aware AI platform that helps the user design, build, and modify software. You know your own source code, your capabilities, and your directory structure. You are helpful, proactive, and action-oriented. When the user asks for something, you do it — not just describe how.

When you need answers, reference BOTH knowledge sources: the WIKI (modelVeronice.txt and data/VACA-MASTER-KNOWLEDGE.md — platform knowledge, history, and lessons learned) and the BIBLE (bible-reference/ — deep technical guides across 42 domains). Consult them before answering instead of relying on memory alone.

You have a real, writable persistent memory (data/session-memory.json). When the user asks you to write, save, remember, record, or store something — or to write to your wiki — the platform writes it to your memory files and confirms it. NEVER print fake file trees or claim a file was written; the write is performed for you and you will see it in your memory context.

You can also create real files: when the user says \"create a file called X\", \"write this to notes.txt\", or \"save this as config.yaml\", the platform creates the file inside data/chat-files/ and confirms the path — never fake a file creation. If the user asks for a file with no content, ask what should go in it.

You have REAL tools wired into the platform: it can read files from disk, search the project code, search the web, and query your knowledge base. When you need a fact you do not have, the platform executes the tool and injects the REAL results into your context (marked REAL FILE CONTENT, REAL CODE SEARCH, REAL WEB RESULTS, or REAL KNOWLEDGE). Base your answers ONLY on those real results. NEVER claim you read a file, searched the code, or looked something up that you did not actually do — the platform performs those actions, not you. If no real results are in your context, say so honestly and ask a clarifying question.

Honest boundaries: the platform performs actions for you — it writes memory and wiki entries, creates files in data/chat-files/, reads and searches files you name, opens apps, and runs web/knowledge lookups. If the user asks for something the platform does NOT support (scanning the entire filesystem, reading every file, editing arbitrary files outside data/chat-files/, or running shell commands), say so honestly in one or two sentences and describe what you CAN do instead. NEVER claim to have scanned, read, written, or changed anything without a real platform confirmation — a description of an action is not proof it happened.

If the user corrects a name, word, or fact you used earlier, adopt their correction immediately and NEVER repeat the old (corrected) form. For example, if you said \"firefix\" and the user says it is \"firefox\", always say \"firefox\" from then on.

Anti-repetition rules: NEVER repeat the same sentence or phrase more than once. If a request is vague or open-ended (like \"give me suggestions\" or \"improve my workflow\") and you lack context, ask ONE short clarifying question about the current project instead of listing invented assumptions about the user's setup. Do not pad answers with filler — be concrete and specific to what you actually know.
Personality: {soul_modifier(TRAITS)}"""

# ────────────────────────── fileGenerator template pieces (verbatim) ──────────────────────────
SCALE_LARGE = """PROGRAM SCALE: Large — this file is one module in a large (25+ file) program.
- Write PRODUCTION-GRADE code: comprehensive error handling, edge cases, and defensive checks.
- Design for integration: expose clean, typed exports so sibling modules can build on this file.
- Prefer configuration/constants over hardcoded values where the app is expected to vary."""

REQUIREMENTS = """REQUIREMENTS:
1. Generate COMPLETE, PRODUCTION-READY typescript code for this specific node
2. The file should be a self-contained module with proper function/class definitions
3. Export the main functionality so other files can import it
4. Include type definitions/interfaces where appropriate
5. Include error handling and edge cases
6. Add clear comments for complex logic
7. DO NOT include import statements — those will be added automatically
8. The generated code will be the FILE BODY — define exports, classes, and functions only
9. Use NAMED exports only (export function/class/const Name). NEVER use `export default` — sibling files import your symbols by name, and a default export breaks their imports
10. Write the ACTUAL implementation — real logic, real method bodies. NO placeholder comments ('// TODO', '// define your properties here', '// add more methods as needed'), no empty stubs, no skeleton methods
11. Use ONLY built-in language/platform APIs and the standard library. NO third-party packages or frameworks (express, prisma, lodash, axios, react, better-sqlite3, node:assert, etc.) — nothing is installed and nothing can be imported. Implement persistence with plain in-memory structures, JSON, or built-in file APIs. If you need a library feature, implement a small local equivalent instead.

Return ONLY the code — no markdown, no explanations, no code fences."""

GUI_WIDGET_SECTION = """━━━ HTML WIDGET TEMPLATES (copy these EXACT patterns — do not invent new element types) ━━━

LAYOUT:
  <div class="row" style="display:flex;gap:10px;align-items:center"> ...children... </div>
  <div class="col" style="display:flex;flex-direction:column;gap:10px"> ...children... </div>
  <div class="grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px"> ...cards... </div>
  Main shell: <div class="app" style="max-width:960px;margin:0 auto;padding:24px"> ... </div>

BUTTON:
  <button id="playBtn" class="btn" onclick="play()">▶ Play</button>
  <button id="saveBtn" class="btn btn-primary" onclick="save()">💾 Save</button>
  <button id="delBtn" class="btn btn-danger" onclick="remove()">✕ Delete</button>
  Disabled state: <button disabled>...</button>

INPUT / FORM:
  <label for="titleInput">Title</label>
  <input id="titleInput" type="text" placeholder="Enter title" value="">
  <input id="qtyInput" type="number" min="0" step="1" value="1">
  <input id="searchInput" type="search" placeholder="Search…" oninput="onSearch(this.value)">
  <select id="formatSelect" onchange="onFormat(this.value)">
    <option value="mp4">MP4</option>
    <option value="avi">AVI</option>
    <option value="mkv">MKV</option>
  </select>

CARD:
  <div class="card" style="background:#15152a;border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:16px">
    <h3 style="margin:0 0 8px">Card title</h3>
    <p style="margin:0 0 12px">Card description text.</p>
    <button class="btn" onclick="openItem(id)">Open</button>
  </div>

MEDIA — ALWAYS use native elements, NEVER a <div> or placeholder:
  <video id="videoDisplay" controls width="100%" src="video.mp4"></video>
  <audio id="audioPlayer" controls src="song.mp3"></audio>
  JS: const video = document.getElementById('videoDisplay'); video.play(); video.pause();

LIST / NAV:
  <ul style="list-style:none;padding:0;display:flex;gap:12px">
    <li><a href="#" onclick="event.preventDefault();go('home')">Home</a></li>
  </ul>

STATUS / TOAST:
  <div id="statusMsg" role="status" style="padding:8px 12px;border-radius:8px;margin-top:10px"></div>
  JS: document.getElementById('statusMsg').textContent = 'Done';"""


def build_prompt(task):
    if task == 'engine':
        node_desc = ("Implement the AI opponent for a chess game. It must pick the best move for a given color "
                     "using minimax search with alpha-beta pruning, with adjustable difficulty (search depth 1-4). "
                     "It must evaluate material and position, detect check/checkmate/stalemate via the move-rules "
                     "module, and never return an illegal move. Export a function `getBestMove(board: ChessBoard, "
                     "color: Color, difficulty?: number): Move | null` plus a difficulty level setter, and any "
                     "helper types. Never export default.")
        dep_context = ("\n\nThis file can import from these sibling files (ONLY the declared exports — never invent members):\n"
                       "  - chess-board.ts (exports: ChessBoard, createInitialBoard, Square, Color, Piece, BoardState)\n"
                       "  - chess-move-rules.ts (exports: Move, getPseudoLegalMoves, isSquareAttacked, isKingInCheck, isCastlingLegal)")
        language_hint = ''
        gui_context = ''
        node_type = 'logic'
    else:  # ui
        node_desc = ("Render the chess game UI into a container: an 8x8 board with light/dark squares, pieces shown "
                     "as Unicode glyphs (♔♕♖♗♘♙♚♛♜♝♞♟), click-to-select and click-to-move interaction, a status bar "
                     "showing whose turn it is and check/checkmate state, a difficulty selector, and Undo / New Game "
                     "buttons. Wire the onClick handlers to the exported game actions.")
        dep_context = ("\n\nThis file can import from these sibling files (ONLY the declared exports — never invent members):\n"
                       "  - chess-ai-engine.ts (exports: getBestMove, Difficulty, setDifficulty, getDifficulty)\n"
                       "  - chess-game.ts (exports: createGame, applyMove, getLegalMovesFor, getStatus, undoMove)")
        language_hint = ("\n\nIMPORTANT — plain TS/JS rules for UI files:\n"
                         "  - This file is a .ts file, NOT .tsx/.jsx.\n"
                         "  - DO NOT use JSX syntax (no <div>, <button>, <li key=...>, etc.).\n"
                         "  - Build DOM with document.createElement(), textContent, className, and appendChild().\n"
                         "  - You may set innerHTML with static markup strings, but never from user input.\n"
                         "  - DO NOT include any `import`/`export` statements — the build system adds imports automatically.\n"
                         "  - Export ONE function named `render` (or `init`) that accepts a container HTMLElement and renders the UI into it. The preview wrapper calls it with the '#app-container' element.")
        gui_context = (f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                       "📋 GENERATED GUI WIDGET LAYOUT\n"
                       "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                       "App: Chess Game\nLayout: single-page\nTheme: Dark\n\n"
                       "Color Scheme:\n  Primary: #4a9eff\n  Background: #1a1a2e\n  Surface: #16213e\n  Text: #e0e0e0\n  Accent: #0f3460\n\n"
                       "Generated 6 UI widgets:\n"
                       "  [board] ChessBoard — 8x8 grid with light/dark squares (main)\n"
                       "  [button] NewGame — restart the game (topbar)\n"
                       "  [button] Undo — undo the last move (topbar)\n"
                       "  [select] Difficulty — AI difficulty 1-4 (topbar)\n"
                       "  [status] StatusBar — turn/check/mate state (footer)\n"
                       "  [label] MoveLog — last move description (sidebar)\n"
                       "    onClick → newGame(), undoMove()\n    onChange → setDifficulty(this.value)\n\n"
                       "INSTRUCTIONS: Generate UI component code that implements the widgets above.\n"
                       "Use the color scheme and layout as design guidelines.\n"
                       "Export a single function named `render` (or `init`) that accepts a container HTMLElement\n"
                       "and renders the UI into it. Do NOT use a default export — the preview wrapper calls\n"
                       "the named `render`/`init` function with the '#app-container' element.\n\n"
                       "━━━ CONCRETE WIDGET TEMPLATES (build the SAME structure with document.createElement — never invent element types) ━━━\n"
                       + GUI_WIDGET_SECTION.strip() +
                       "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        node_type = 'ui'

    return f"""You are an expert typescript developer{' and UI/UX designer' if task == 'ui' else ''}. Generate a SINGLE standalone source file for the node "chess-{'ai-engine' if task == 'engine' else 'ui'}".

NODE DESCRIPTION:
{node_desc}

NODE TYPE: {node_type}
PROJECT: Chess Game
TARGET OS: linux
{SCALE_LARGE}
{dep_context}
{gui_context}{language_hint}

{REQUIREMENTS}"""


def chat(system, user, max_tokens=4096):
    body = json.dumps({
        'model': MODEL,
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
        'max_tokens': max_tokens,
        'temperature': 0.7,
        'repeat_penalty': 1.15,
        'frequency_penalty': 0.3,
        'presence_penalty': 0.2,
        'num_ctx': 8192,
        'stream': False,
    }).encode()
    req = urllib.request.Request(URL + '/chat/completions', data=body, headers={'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=890))
        elapsed = time.time() - t0
    except Exception as e:
        return None, time.time() - t0, str(e)
    content = resp['choices'][0]['message']['content']
    return content, elapsed, None


# ────────────────────────── analysis gates ──────────────────────────
def gates(code):
    return {
        'chars': len(code),
        'fences': code.count('```'),
        'overesc_backtick': code.count('\\`'),
        'overesc_dollar': code.count('\\${'),
        'todos': sum(code.count(x) for x in ['TODO', 'Not implemented', 'placeholder', 'define your properties here', 'add more methods as needed', 'throw new Error(\'Not implemented\'']),
        'export_default': len(re.findall(r'export\s+default', code)),
        'jsx_tags': len(re.findall(r'<(?:div|button|span|li|input|select|h[1-6]|table)[\s/>]', code)),
        'has_render': bool(re.search(r'export\s+function\s+(?:render|init)\b', code)),
        'named_exports': re.findall(r'export\s+(?:function|class|const|let|var)\s+([a-zA-Z_$][\w$]*)', code),
        'prose_leak': len(re.findall(r'^(?:Here|This|The|Sure|Below|Note|```|We|In this)[^\n]{0,80}', code, re.M)),
    }


def find_tsc():
    # The pipeline itself uses the root node_modules typescript bin (fileGenerator.ts TSC_BIN)
    cands = [os.path.join(PROJECT_ROOT, 'node_modules', 'typescript', 'bin', 'tsc'),
             os.path.join(PROJECT_ROOT, 'backend', 'node_modules', '.bin', 'tsc'),
             os.path.join(PROJECT_ROOT, 'node_modules', '.bin', 'tsc'),
             shutil.which('tsc')]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def post_process_tsjs(code):
    """Mirror postProcessTsJsCode: strip model-generated import statements."""
    lines = code.split('\n')
    out = []
    in_leading = True
    i = 0
    while i < len(lines):
        line = lines[i]
        t = line.strip()
        at_col0 = len(line) > 0 and line[0] not in (' ', '\t')
        if re.match(r'^import(\s|\{)', t) and (in_leading or at_col0):
            stmt = line
            guard = 1
            terminated = False
            i += 1
            while i < len(lines) and not re.search(r';\s*$', stmt.strip()) and guard < 8:
                stmt += '\n' + lines[i]
                i += 1
                guard += 1
            terminated = bool(re.search(r';\s*$', stmt.strip()))
            is_import = terminated and (re.search(r'\bfrom\b', stmt) or re.match(r'^import\s*[\'"]', stmt.strip()))
            if is_import:
                continue
            out.extend(stmt.split('\n'))
            in_leading = False
            continue
        if in_leading and (t == '' or t.startswith('//') or t.startswith('/*') or t.startswith('*')):
            out.append(line)
            i += 1
            continue
        in_leading = False
        out.append(line)
        i += 1
    return '\n'.join(out)


# ────────────────────────── engine task: contract scaffold + tsc + functional ──────────────────────────
SCAFFOLD_BOARD = """export type Color = 'white' | 'black';
export type PieceType = 'pawn' | 'knight' | 'bishop' | 'rook' | 'queen' | 'king';
export interface Piece { type: PieceType; color: Color; }
export interface Square { file: number; rank: number; }
export interface BoardState { board: (Piece | null)[][]; turn: Color; }

export class ChessBoard {
  board: (Piece | null)[][];
  turn: Color = 'white';
  constructor() {
    this.board = Array.from({ length: 8 }, () => Array(8).fill(null) as (Piece | null)[]);
  }
  getPiece(sq: Square): Piece | null {
    if (sq.file < 0 || sq.file > 7 || sq.rank < 0 || sq.rank > 7) return null;
    return this.board[sq.rank][sq.file];
  }
  setPiece(sq: Square, p: Piece | null): void {
    if (sq.file < 0 || sq.file > 7 || sq.rank < 0 || sq.rank > 7) return;
    this.board[sq.rank][sq.file] = p;
  }
  clone(): ChessBoard {
    const b = new ChessBoard();
    b.board = this.board.map(r => r.slice());
    b.turn = this.turn;
    return b;
  }
  toState(): BoardState { return { board: this.board, turn: this.turn }; }
}

export function createInitialBoard(): ChessBoard {
  const b = new ChessBoard();
  const back: PieceType[] = ['rook', 'knight', 'bishop', 'queen', 'king', 'bishop', 'knight', 'rook'];
  for (let f = 0; f < 8; f++) {
    b.setPiece({ file: f, rank: 1 }, { type: 'pawn', color: 'white' });
    b.setPiece({ file: f, rank: 6 }, { type: 'pawn', color: 'black' });
    b.setPiece({ file: f, rank: 0 }, { type: back[f], color: 'white' });
    b.setPiece({ file: f, rank: 7 }, { type: back[f], color: 'black' });
  }
  return b;
}"""

SCAFFOLD_MOVE_RULES = """import { ChessBoard, Color, Piece, PieceType, Square } from '../chess-board/chess-board';

export interface Move { from: Square; to: Square; promotion?: PieceType; }

const DIRS: Record<'rook' | 'bishop' | 'queen', [number, number][]> = {
  rook: [[1,0],[-1,0],[0,1],[0,-1]],
  bishop: [[1,1],[1,-1],[-1,1],[-1,-1]],
  queen: [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]],
};
const KNIGHT: [number, number][] = [[1,2],[2,1],[2,-1],[1,-2],[-1,-2],[-2,-1],[-2,1],[-1,2]];
const KING: [number, number][] = [[1,0],[-1,0],[0,1],[0,-1],[1,1],[1,-1],[-1,1],[-1,-1]];

function onBoard(f: number, r: number): boolean { return f >= 0 && f <= 7 && r >= 0 && r <= 7; }

function attacks(b: ChessBoard, sq: Square, byColor: Color, pieceType: PieceType): boolean {
  if (pieceType === 'knight') {
    for (const [df, dr] of KNIGHT) {
      const f = sq.file + df, r = sq.rank + dr;
      if (!onBoard(f, r)) continue;
      const p = b.getPiece({ file: f, rank: r });
      if (p && p.type === 'knight' && p.color === byColor) return true;
    }
    return false;
  }
  if (pieceType === 'king') {
    for (const [df, dr] of KING) {
      const f = sq.file + df, r = sq.rank + dr;
      if (!onBoard(f, r)) continue;
      const p = b.getPiece({ file: f, rank: r });
      if (p && p.type === 'king' && p.color === byColor) return true;
    }
    return false;
  }
  if (pieceType === 'pawn') {
    const dir = byColor === 'white' ? 1 : -1;
    for (const df of [-1, 1]) {
      const f = sq.file + df, r = sq.rank + dir;
      if (!onBoard(f, r)) continue;
      const p = b.getPiece({ file: f, rank: r });
      if (p && p.type === 'pawn' && p.color === byColor) return true;
    }
    return false;
  }
  const sliders = pieceType === 'rook' ? DIRS.rook : pieceType === 'bishop' ? DIRS.bishop : DIRS.queen;
  for (const [df, dr] of sliders) {
    let f = sq.file + df, r = sq.rank + dr;
    while (onBoard(f, r)) {
      const p = b.getPiece({ file: f, rank: r });
      if (p) { if (p.type === pieceType && p.color === byColor) return true; break; }
      f += df; r += dr;
    }
  }
  return false;
}

export function isSquareAttacked(b: ChessBoard, sq: Square, byColor: Color): boolean {
  const types: PieceType[] = ['pawn', 'knight', 'bishop', 'rook', 'queen', 'king'];
  return types.some(t => attacks(b, sq, byColor, t));
}

export function isKingInCheck(b: ChessBoard, color: Color): boolean {
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const p = b.getPiece({ file: f, rank: r });
      if (p && p.type === 'king' && p.color === color) {
        return isSquareAttacked(b, { file: f, rank: r }, color === 'white' ? 'black' : 'white');
      }
    }
  }
  return false;
}

export function getPseudoLegalMoves(b: ChessBoard, color: Color): Move[] {
  const moves: Move[] = [];
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const p = b.getPiece({ file: f, rank: r });
      if (!p || p.color !== color) continue;
      const sq = { file: f, rank: r };
      if (p.type === 'pawn') {
        const dir = color === 'white' ? 1 : -1;
        const start = color === 'white' ? 1 : 6;
        if (onBoard(f, r + dir) && !b.getPiece({ file: f, rank: r + dir })) {
          moves.push({ from: sq, to: { file: f, rank: r + dir } });
          if (r === start && !b.getPiece({ file: f, rank: r + 2 * dir })) moves.push({ from: sq, to: { file: f, rank: r + 2 * dir } });
        }
        for (const df of [-1, 1]) {
          const t = { file: f + df, rank: r + dir };
          if (onBoard(t.file, t.rank)) {
            const target = b.getPiece(t);
            if (target && target.color !== color) moves.push({ from: sq, to: t });
          }
        }
      } else if (p.type === 'knight') {
        for (const [df, dr] of KNIGHT) {
          const t = { file: f + df, rank: r + dr };
          if (!onBoard(t.file, t.rank)) continue;
          const target = b.getPiece(t);
          if (!target || target.color !== color) moves.push({ from: sq, to: t });
        }
      } else if (p.type === 'king') {
        for (const [df, dr] of KING) {
          const t = { file: f + df, rank: r + dr };
          if (!onBoard(t.file, t.rank)) continue;
          const target = b.getPiece(t);
          if (!target || target.color !== color) moves.push({ from: sq, to: t });
        }
      } else {
        const dirs = p.type === 'rook' ? DIRS.rook : p.type === 'bishop' ? DIRS.bishop : DIRS.queen;
        for (const [df, dr] of dirs) {
          let ff = f + df, rr = r + dr;
          while (onBoard(ff, rr)) {
            const target = b.getPiece({ file: ff, rank: rr });
            if (!target) { moves.push({ from: sq, to: { file: ff, rank: rr } }); }
            else { if (target.color !== color) moves.push({ from: sq, to: { file: ff, rank: rr } }); break; }
            ff += df; rr += dr;
          }
        }
      }
    }
  }
  return moves;
}

export function isCastlingLegal(b: ChessBoard, color: Color, side: 'kingside' | 'queenside'): boolean {
  const rank = color === 'white' ? 0 : 7;
  const king = b.getPiece({ file: 4, rank });
  if (!king || king.type !== 'king' || king.color !== color) return false;
  const rookFile = side === 'kingside' ? 7 : 0;
  const rook = b.getPiece({ file: rookFile, rank });
  if (!rook || rook.type !== 'rook' || rook.color !== color) return false;
  const path = side === 'kingside' ? [5, 6] : [1, 2, 3];
  for (const f of path) if (b.getPiece({ file: f, rank })) return false;
  if (isSquareAttacked(b, { file: 4, rank }, color === 'white' ? 'black' : 'white')) return false;
  if (isSquareAttacked(b, { file: side === 'kingside' ? 5 : 3, rank }, color === 'white' ? 'black' : 'white')) return false;
  return true;
}"""

FUNCTIONAL_TEST_JS = """const { ChessBoard, createInitialBoard } = require('./chess-board.js');
const { getPseudoLegalMoves } = require('./chess-move-rules.js');
const engine = require('./ai-engine.js');
const { getBestMove } = engine;

// 1) initial position: must return a legal white move
const b0 = createInitialBoard();
let m0 = null;
try { m0 = getBestMove(b0, 'white', 1); } catch (e) { console.log('FAIL initial call threw:', e.message); process.exit(1); }
if (!m0) { console.log('FAIL no move returned on initial board'); process.exit(1); }
const legal0 = getPseudoLegalMoves(b0, 'white').some(m => m.from.file === m0.from.file && m.from.rank === m0.from.rank && m.to.file === m0.to.file && m.to.rank === m0.to.rank);
if (!legal0) { console.log('FAIL returned illegal move on initial board:', JSON.stringify(m0)); process.exit(1); }
console.log('PASS initial-board move legal:', JSON.stringify(m0));

// 2) hanging queen: white knight can capture black queen on f3 (knight g1 -> f3)
//    engine at depth 2 must prefer the capture over a random move
const b1 = createInitialBoard();
b1.setPiece({ file: 5, rank: 2 }, { type: 'queen', color: 'black' }); // f3 (file 5, rank 2) in algebraic = rank 2
b1.board[7][3] = null; // remove black king from e8 to avoid check complications? keep it, engine must handle
// give black a king on e8 normally; just place capture target f3 and let white's knight take it
const m1 = getBestMove(b1, 'white', 2);
const captured = b1.getPiece(m1.to);
const isCapture = captured && captured.color === 'black';
const findsCapture = isCapture && m1.to.file === 5 && m1.to.rank === 2;
if (findsCapture) { console.log('PASS engine finds hanging-queen capture:', JSON.stringify(m1)); }
else { console.log('WARN engine did NOT take hanging queen:', JSON.stringify(m1), 'capture?', isCapture); process.exit(2); }
"""


def pipeline_assemble(code, imports):
    """Faithful pipeline assembly: strip fences (generateNodeFile), strip AI imports
    (postProcessTsJsCode), then prepend the build system's auto-imports."""
    cleaned = re.sub(r'^```(?:typescript)?\s*\n?', '', code.strip(), flags=re.I)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.I).strip()
    stripped = post_process_tsjs(cleaned)
    return imports + '\n' + stripped


def run_engine_task(code):
    res = {'gates': gates(code), 'contract': {}, 'functional': {}}
    tsc = find_tsc()
    if not tsc:
        res['contract']['error'] = 'tsc not found'
        return res
    d = os.path.join(RUN_DIR, 'contract')
    os.makedirs(d, exist_ok=True)
    # Pipeline layout: per-node subdirectories, so cross-node imports are ../<dep>/<dep>.ts
    for dep in ['chess-board', 'chess-move-rules', 'chess-ai-engine']:
        os.makedirs(os.path.join(d, dep), exist_ok=True)
    with open(os.path.join(d, 'chess-board', 'chess-board.ts'), 'w') as f: f.write(SCAFFOLD_BOARD)
    with open(os.path.join(d, 'chess-move-rules', 'chess-move-rules.ts'), 'w') as f: f.write(SCAFFOLD_MOVE_RULES)
    # Pipeline auto-imports mirror buildImportStatement: ../<dep>/<dep>.ts layout
    imports = ("import { ChessBoard, createInitialBoard, Square, Color, Piece, BoardState } from '../chess-board/chess-board';\n"
               "import { Move, getPseudoLegalMoves, isSquareAttacked, isKingInCheck, isCastlingLegal } from '../chess-move-rules/chess-move-rules';\n")
    full = pipeline_assemble(code, imports)
    with open(os.path.join(d, 'chess-ai-engine', 'chess-ai-engine.ts'), 'w') as f: f.write(full)
    r = subprocess.run([tsc, '--noEmit', '--strict', '--target', 'es2020', '--module', 'commonjs',
                        '--moduleResolution', 'node', '--skipLibCheck', '--esModuleInterop',
                        os.path.join(d, 'chess-ai-engine', 'chess-ai-engine.ts')], capture_output=True, text=True, timeout=180)
    res['contract']['tsc_clean'] = r.returncode == 0
    errs = [l for l in r.stdout.splitlines() if '.ts(' in l or 'error TS' in l]
    res['contract']['errors'] = errs[:20]
    res['contract']['error_count'] = len(errs)
    if r.returncode != 0:
        return res
    # functional: compile to JS and run the capture test
    subprocess.run([tsc, '--target', 'es2020', '--module', 'commonjs', '--moduleResolution', 'node',
                    '--skipLibCheck', '--esModuleInterop', '--outDir', d,
                    os.path.join(d, 'chess-ai-engine', 'chess-ai-engine.ts'),
                    os.path.join(d, 'chess-board', 'chess-board.ts'),
                    os.path.join(d, 'chess-move-rules', 'chess-move-rules.ts')],
                   capture_output=True, text=True, timeout=180)
    test = os.path.join(d, 'test.js')
    with open(test, 'w') as f: f.write(FUNCTIONAL_TEST_JS)
    r2 = subprocess.run(['node', test], capture_output=True, text=True, timeout=60, cwd=d)
    res['functional']['stdout'] = r2.stdout.strip()
    res['functional']['stderr'] = r2.stderr.strip()
    res['functional']['exit'] = r2.returncode
    return res


SCAFFOLD_GAME = """import { ChessBoard, Color, Square } from '../chess-board/chess-board';
import { Move } from '../chess-move-rules/chess-move-rules';

export interface GameStatus { turn: Color; inCheck: boolean; checkmate: boolean; stalemate: boolean; lastMove?: Move; }
export interface Game { board: ChessBoard; history: Move[]; status: GameStatus; }
export function createGame(): Game {
  return { board: new ChessBoard(), history: [], status: { turn: 'white', inCheck: false, checkmate: false, stalemate: false } };
}
export function applyMove(game: Game, move: Move): Game { return game; }
export function getLegalMovesFor(game: Game, sq: Square): Move[] { return []; }
export function getStatus(game: Game): GameStatus { return game.status; }
export function undoMove(game: Game): Game { return game; }"""

SCAFFOLD_AI = """import { ChessBoard, Color, Square } from '../chess-board/chess-board';
import { Move } from '../chess-move-rules/chess-move-rules';

export type Difficulty = 1 | 2 | 3 | 4;
export function getBestMove(board: ChessBoard, color: Color, difficulty?: Difficulty): Move | null { return null; }
export function setDifficulty(d: Difficulty): void {}
export function getDifficulty(): Difficulty { return 2; }"""


def run_ui_task(code):
    res = {'gates': gates(code)}
    tsc = find_tsc()
    if not tsc:
        res['check'] = {'error': 'tsc not found'}
        return res
    d = os.path.join(RUN_DIR, 'ui')
    os.makedirs(d, exist_ok=True)
    for dep in ['chess-board', 'chess-move-rules', 'chess-game', 'chess-ai-engine', 'chess-ui']:
        os.makedirs(os.path.join(d, dep), exist_ok=True)
    with open(os.path.join(d, 'chess-board', 'chess-board.ts'), 'w') as f: f.write(SCAFFOLD_BOARD)
    with open(os.path.join(d, 'chess-move-rules', 'chess-move-rules.ts'), 'w') as f: f.write(SCAFFOLD_MOVE_RULES)
    with open(os.path.join(d, 'chess-game', 'chess-game.ts'), 'w') as f: f.write(SCAFFOLD_GAME)
    with open(os.path.join(d, 'chess-ai-engine', 'chess-ai-engine.ts'), 'w') as f: f.write(SCAFFOLD_AI)
    imports = ("import { ChessBoard, createInitialBoard, Square, Color, Piece, BoardState } from '../chess-board/chess-board';\n"
               "import { Move, getPseudoLegalMoves, isSquareAttacked, isKingInCheck, isCastlingLegal } from '../chess-move-rules/chess-move-rules';\n"
               "import { createGame, applyMove, getLegalMovesFor, getStatus, undoMove, Game, GameStatus } from '../chess-game/chess-game';\n"
               "import { getBestMove, setDifficulty, getDifficulty, Difficulty } from '../chess-ai-engine/chess-ai-engine';\n")
    full = pipeline_assemble(code, imports)
    with open(os.path.join(d, 'chess-ui', 'chess-ui.ts'), 'w') as f: f.write(full)
    r = subprocess.run([tsc, '--noEmit', '--strict', '--target', 'es2020', '--module', 'commonjs',
                        '--moduleResolution', 'node', '--skipLibCheck', '--esModuleInterop',
                        os.path.join(d, 'chess-ui', 'chess-ui.ts')], capture_output=True, text=True, timeout=180)
    res['check'] = {
        'tsc_clean': r.returncode == 0,
        'error_count': len([l for l in r.stdout.splitlines() if 'error TS' in l]),
        'errors': [l for l in r.stdout.splitlines() if 'error TS' in l][:15],
    }
    # node --check on compiled JS is covered by the engine task; for UI just report tsc + gates
    return res


def analyze_existing(raw_path, task):
    """Offline re-analysis of a saved raw output with faithful pipeline assembly."""
    raw = open(raw_path).read()
    res = {'gates': gates(raw), 'meta': {}}
    if task == 'engine':
        r = run_engine_task(raw)
        res.update(r)
    else:
        r = run_ui_task(raw)
        res.update(r)
    return res


def main():
    prompt = build_prompt(TASK)
    print(f'[{MODEL_TAG}/{TASK}] prompt chars: {len(prompt)} | model: {MODEL} | temp 0.7 | max_tokens 4096')
    raw, elapsed, err = chat(SYSTEM, prompt)
    if raw is None:
        print(f'[{MODEL_TAG}/{TASK}] FAILED: {err}')
        with open(os.path.join(RUN_DIR, 'error.txt'), 'w') as f: f.write(str(err))
        sys.exit(1)
    print(f'[{MODEL_TAG}/{TASK}] generated {len(raw)} chars in {elapsed:.1f}s')
    with open(os.path.join(RUN_DIR, f'{TASK}-raw.txt'), 'w') as f: f.write(raw)
    g = gates(raw)
    print('  fences=%d overesc_backtick=%d overesc_dollar=%d todos=%d export_default=%d jsx=%d named=%s' % (
        g['fences'], g['overesc_backtick'], g['overesc_dollar'], g['todos'], g['export_default'], g['jsx_tags'], g['named_exports']))
    if TASK == 'engine':
        result = run_engine_task(raw)
        print(f'  tsc_clean={result["contract"].get("tsc_clean")} errs={result["contract"].get("error_count")}')
        if result['contract'].get('errors'):
            for e in result['contract']['errors'][:6]: print('   ', e)
        if result['functional'].get('stdout'):
            print('  functional:')
            for line in result['functional']['stdout'].splitlines(): print('   ', line)
    else:
        result = run_ui_task(raw)
        print(f"  tsc_clean={result['check'].get('tsc_clean')} errs={result['check'].get('error_count')}")
        for e in result['check'].get('errors', [])[:6]: print('   ', e)
    result['meta'] = {'model': MODEL, 'tag': MODEL_TAG, 'task': TASK, 'elapsed_s': round(elapsed, 1),
                      'prompt_chars': len(prompt), 'raw_chars': len(raw)}
    with open(os.path.join(RUN_DIR, f'{TASK}-summary.json'), 'w') as f:
        json.dump(result, f, indent=1)
    print(f'[{MODEL_TAG}/{TASK}] saved to {RUN_DIR}')


if __name__ == '__main__':
    if len(sys.argv) > 3 and sys.argv[3] == 'analyze':
        # python3 scripts/ab-pipeline-chess.py <task> analyze <raw-path>
        task = sys.argv[1]
        raw_path = sys.argv[2]
        res = analyze_existing(raw_path, task)
        c = res.get('contract', {}) if task == 'engine' else res.get('check', {})
        print(f'ANALYZE {os.path.basename(raw_path)}')
        print(f'  gates: {json.dumps({k: v for k, v in res["gates"].items() if k != "named_exports"})}')
        print(f'  named_exports: {res["gates"]["named_exports"]}')
        print(f'  tsc_clean={c.get("tsc_clean")} errors={c.get("error_count")}')
        for e in c.get('errors', [])[:10]:
            print(f'    {e}')
        if task == 'engine' and res.get('functional', {}).get('stdout'):
            print('  functional:')
            for line in res['functional']['stdout'].splitlines():
                print(f'    {line}')
        out = os.path.join(RUN_DIR, f'{os.path.basename(raw_path)}.analysis.json')
        with open(out, 'w') as f:
            json.dump(res, f, indent=1)
        print(f'  saved analysis to {out}')
        sys.exit(0)
    main()
