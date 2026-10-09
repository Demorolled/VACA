#!/usr/bin/env python3
"""
Build a small fine-tuning dataset teaching CROSS-FILE CONTRACT FIDELITY.

Motivation (from A/B run data/ab-test-chess-pipeline/SUMMARY.md): the tuned 7B
model formats cleanly (0 fences / 0 prose) but invents members beyond the
declared exports (board.makeMove(), board.evaluate(), board.isCheckmate()) and
forgets export contracts (no `render` export). This dataset teaches:

  1. Use ONLY the members explicitly whitelisted in the sibling contract.
  2. When a capability isn't in the contract, implement it LOCALLY with the
     whitelisted members (e.g. apply a move via clone()+setPiece(), never
     invent board.makeMove()).
  3. Export the exact named symbols requested (never `export default`).
  4. UI files MUST export a named `render`/`init`.
  5. No import statements (build system adds them), no JSX, no fences/prose.

Format: Alpaca JSONL (instruction / input / output) — the exact schema the
GUITrainer engine expects (training/gui_trainer/engine.py -> ChatML, assistant-
only loss). Outputs are hand-authored and contract-clean, validated by
`--validate` (lint + tsc against the real scaffolds from the chess A/B).

Usage:
  python3 scripts/build-contract-fidelity-dataset.py                 # build jsonl
  python3 scripts/build-contract-fidelity-dataset.py --validate      # lint + tsc
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "training", "dataset")
OUT_TRAIN = os.path.join(OUT_DIR, "contract-fidelity.jsonl")
OUT_VAL = os.path.join(OUT_DIR, "contract-fidelity-val.jsonl")
OUT_TEST = os.path.join(OUT_DIR, "contract-fidelity-test.jsonl")

# ─────────────────────────────────────────────────────────────────────────────
# Sibling contract scaffolds (used by --validate tsc). These mirror the real
# chess scaffolds from scripts/ab-pipeline-chess.py so validation is authentic.
# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# Hand-authored examples. Each has an explicit member whitelist and a
# contract-clean output that ONLY uses whitelisted members.
# ─────────────────────────────────────────────────────────────────────────────
def t(node, app, tier, lang, node_type, desc, siblings, exports_hint, output, trap=""):
    """Build one Alpaca example. siblings = list of (file, exports-desc)."""
    sibling_block = "\n".join(f"  - {f} (exports: {e})" for f, e in siblings)
    node_export = f" Export ONLY these named symbols: {exports_hint}." if exports_hint else ""
    lang_rules = {
        "typescript": ("TypeScript", "Use NO import statements (the build system adds them automatically), NO JSX "
                       "(build the DOM with document.createElement, textContent, className, appendChild), and include "
                       "error handling and edge cases."),
        "go": ("Go", "Use NO import statements (the build system adds them automatically) and include error handling."),
        "python": ("Python", "Use NO import statements (the build system adds them automatically) and include error handling."),
    }[lang]
    instruction = (
        f"Generate the source file for the node '{node}' in the '{app}' app ({tier} tier). "
        f"Write complete, production-ready {lang_rules[0]} code that exports named symbols only."
        f"{node_export} {lang_rules[1]}"
        f"{trap}"
        f" Use ONLY the declared exports from the sibling files listed below — never invent members that are not "
        f"listed. Return only the code — no markdown, no explanations, no code fences."
    )
    return {"instruction": instruction, "input": sibling_block, "output": output.strip()}


EXAMPLES = []

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 1: Chess — the exact A/B failure cases, corrected
# ═══════════════════════════════════════════════════════════════════════════
CHESS_DEPS = [
    ("chess-board", "class ChessBoard { getPiece(sq): Piece|null; setPiece(sq,p): void; clone(): ChessBoard; "
                    "toState(): BoardState }; createInitialBoard(): ChessBoard; types Square, Color, Piece, BoardState"),
    ("chess-move-rules", "type Move; getPseudoLegalMoves(board,color): Move[]; isSquareAttacked(board,sq,byColor): "
                         "boolean; isKingInCheck(board,color): boolean"),
]

# 1a. AI engine — the star lesson: minimax WITHOUT inventing board.makeMove/evaluate.
EXAMPLES.append(t(
    "chess-ai-engine", "Chess Game", "complex", "typescript", "logic",
    "Implement the AI opponent: minimax search with alpha-beta pruning, difficulty depth 1-4, "
    "never return an illegal move. ChessBoard has NO makeMove/evaluate/isCheckmate — implement move "
    "application locally with clone()+setPiece(), and evaluate material by iterating the 64 squares with getPiece.",
    CHESS_DEPS,
    "getBestMove(board,color,config?) and setDifficulty(depth)",
    """export interface AIConfig { depth?: number; }

interface MoveResult { move: Move | null; score: number; }

const PIECE_VALUES: Record<string, number> = { pawn: 100, knight: 320, bishop: 330, rook: 500, queen: 900, king: 20000 };

function applyMove(board: ChessBoard, move: Move): ChessBoard {
  const next = board.clone();
  next.setPiece(move.to, board.getPiece(move.from));
  next.setPiece(move.from, null);
  return next;
}

function evaluate(board: ChessBoard, color: Color): number {
  let score = 0;
  for (let rank = 0; rank < 8; rank++) {
    for (let file = 0; file < 8; file++) {
      const piece = board.getPiece({ file, rank });
      if (!piece) continue;
      const value = PIECE_VALUES[piece.type] || 0;
      score += piece.color === color ? value : -value;
    }
  }
  return score;
}

function minimax(board: ChessBoard, depth: number, color: Color, alpha: number, beta: number, maximizing: boolean): MoveResult {
  if (depth === 0) return { move: null, score: evaluate(board, color) };
  const moves = getPseudoLegalMoves(board, color).filter(m => !isKingInCheck(applyMove(board, m), color));
  if (moves.length === 0) return { move: null, score: evaluate(board, color) };
  let best: MoveResult = { move: null, score: maximizing ? -Infinity : Infinity };
  for (const move of moves) {
    const result = minimax(applyMove(board, move), depth - 1, color === 'white' ? 'black' : 'white', alpha, beta, !maximizing);
    if (maximizing) {
      if (result.score > best.score) best = { move, score: result.score };
      alpha = Math.max(alpha, result.score);
    } else {
      if (result.score < best.score) best = { move, score: result.score };
      beta = Math.min(beta, result.score);
    }
    if (beta <= alpha) break;
  }
  return best;
}

export function getBestMove(board: ChessBoard, color: Color, config?: AIConfig): Move | null {
  const depth = Math.min(Math.max(config?.depth ?? 2, 1), 4);
  return minimax(board, depth, color, -Infinity, Infinity, true).move;
}

export function setDifficulty(depth: number): AIConfig {
  const clamped = Math.min(Math.max(depth, 1), 4);
  return { depth: clamped };
}""",
    trap="",
))

# 1b. Repair variant — exactly the tsc error from the A/B, fixed.
EXAMPLES.append(t(
    "chess-ai-engine", "Chess Game", "complex", "typescript", "logic",
    "THE PREVIOUS VERSION OF THIS FILE FAILED TO COMPILE. CURRENT CONTENT included "
    "newBoard.makeMove(move), board.evaluate(this.color), board.isCheckmate(color) — none of which exist on ChessBoard. "
    "TSC ERRORS: Property 'makeMove' does not exist on type 'ChessBoard'; Property 'evaluate' does not exist on type "
    "'ChessBoard'; Property 'isCheckmate' does not exist on type 'ChessBoard'. Fix ALL errors: keep the SAME exported "
    "symbol names (getBestMove, setDifficulty). ChessBoard only exposes getPiece, setPiece, clone, toState — implement "
    "make-move and evaluation LOCALLY with those. Do not cast to any.",
    CHESS_DEPS,
    "getBestMove(board,color,config?) and setDifficulty(depth)",
    """export interface AIConfig { depth?: number; }

const PIECE_VALUES: Record<string, number> = { pawn: 100, knight: 320, bishop: 330, rook: 500, queen: 900, king: 20000 };

function makeMoveLocal(board: ChessBoard, from: Square, to: Square): ChessBoard {
  const next = board.clone();
  next.setPiece(to, board.getPiece(from));
  next.setPiece(from, null);
  return next;
}

function evaluateMaterial(board: ChessBoard, color: Color): number {
  let score = 0;
  for (let rank = 0; rank < 8; rank++) {
    for (let file = 0; file < 8; file++) {
      const piece = board.getPiece({ file, rank });
      if (!piece) continue;
      score += (PIECE_VALUES[piece.type] || 0) * (piece.color === color ? 1 : -1);
    }
  }
  return score;
}

function inCheckAfterMove(board: ChessBoard, from: Square, to: Square, color: Color): boolean {
  return isKingInCheck(makeMoveLocal(board, from, to), color);
}

function search(board: ChessBoard, depth: number, color: Color, alpha: number, beta: number, maximizing: boolean): { move: Move | null; score: number } {
  if (depth === 0) return { move: null, score: evaluateMaterial(board, color) };
  let best = { move: null as Move | null, score: maximizing ? -Infinity : Infinity };
  let any = false;
  for (const move of getPseudoLegalMoves(board, color)) {
    if (inCheckAfterMove(board, move.from, move.to, color)) continue;
    any = true;
    const result = search(makeMoveLocal(board, move.from, move.to), depth - 1, color === 'white' ? 'black' : 'white', alpha, beta, !maximizing);
    if (maximizing) {
      if (result.score > best.score) best = { move, score: result.score };
      alpha = Math.max(alpha, result.score);
    } else {
      if (result.score < best.score) best = { move, score: result.score };
      beta = Math.min(beta, result.score);
    }
    if (beta <= alpha) break;
  }
  return any ? best : { move: null, score: evaluateMaterial(board, color) };
}

export function getBestMove(board: ChessBoard, color: Color, config?: AIConfig): Move | null {
  const depth = Math.min(Math.max(config?.depth ?? 2, 1), 4);
  return search(board, depth, color, -Infinity, Infinity, true).move;
}

export function setDifficulty(depth: number): AIConfig {
  return { depth: Math.min(Math.max(depth, 1), 4) };
}""",
))

# 1c. Checkmate-without-isCheckmate trap: implement via whitelisted members.
EXAMPLES.append(t(
    "chess-ai-engine", "Chess Game", "complex", "typescript", "logic",
    "Add checkmate detection to the AI. Note: chess-move-rules does NOT export isCheckmate — detect checkmate "
    "yourself: a side is checkmated if it is in check AND has no legal move that escapes check. Keep exports "
    "getBestMove and setDifficulty, add isCheckmated(board, color).",
    CHESS_DEPS,
    "getBestMove, setDifficulty, isCheckmated(board,color)",
    """export interface AIConfig { depth?: number; }

export function isCheckmated(board: ChessBoard, color: Color): boolean {
  if (!isKingInCheck(board, color)) return false;
  for (const move of getPseudoLegalMoves(board, color)) {
    const next = board.clone();
    next.setPiece(move.to, board.getPiece(move.from));
    next.setPiece(move.from, null);
    if (!isKingInCheck(next, color)) return false;
  }
  return true;
}

function evaluate(board: ChessBoard, color: Color): number {
  if (isCheckmated(board, color)) return -100000;
  let score = 0;
  const values: Record<string, number> = { pawn: 100, knight: 320, bishop: 330, rook: 500, queen: 900, king: 20000 };
  for (let rank = 0; rank < 8; rank++) {
    for (let file = 0; file < 8; file++) {
      const p = board.getPiece({ file, rank });
      if (!p) continue;
      score += (values[p.type] || 0) * (p.color === color ? 1 : -1);
    }
  }
  return score;
}

function search(board: ChessBoard, depth: number, color: Color, alpha: number, beta: number, maximizing: boolean): { move: Move | null; score: number } {
  if (depth === 0) return { move: null, score: evaluate(board, color) };
  let best = { move: null as Move | null, score: maximizing ? -Infinity : Infinity };
  let any = false;
  for (const move of getPseudoLegalMoves(board, color)) {
    const next = board.clone();
    next.setPiece(move.to, board.getPiece(move.from));
    next.setPiece(move.from, null);
    if (isKingInCheck(next, color)) continue;
    any = true;
    const result = search(next, depth - 1, color === 'white' ? 'black' : 'white', alpha, beta, !maximizing);
    if (maximizing) {
      if (result.score > best.score) best = { move, score: result.score };
      alpha = Math.max(alpha, result.score);
    } else {
      if (result.score < best.score) best = { move, score: result.score };
      beta = Math.min(beta, result.score);
    }
    if (beta <= alpha) break;
  }
  return any ? best : { move: null, score: evaluate(board, color) };
}

export function getBestMove(board: ChessBoard, color: Color, config?: AIConfig): Move | null {
  return search(board, Math.min(Math.max(config?.depth ?? 2, 1), 4), color, -Infinity, Infinity, true).move;
}

export function setDifficulty(depth: number): AIConfig {
  return { depth: Math.min(Math.max(depth, 1), 4) };
}""",
))

# 1d. Game-state module using whitelisted board/move APIs.
EXAMPLES.append(t(
    "chess-game", "Chess Game", "complex", "typescript", "logic",
    "Game orchestration: create a game, apply a move (validate with isKingInCheck after local application), "
    "list legal moves for a square, report status (whose turn, check, checkmate, stalemate), and undo the last "
    "move. Board moves must be applied with clone()+setPiece() — there is no board.makeMove.",
    CHESS_DEPS,
    "createGame(), applyMove(game,move), getLegalMovesFor(game,square), getStatus(game), undoMove(game)",
    """export interface Game {
  board: ChessBoard;
  history: Move[];
  turn: Color;
}

export function createGame(): Game {
  return { board: createInitialBoard(), history: [], turn: 'white' };
}

function afterMove(board: ChessBoard, move: Move): ChessBoard {
  const next = board.clone();
  next.setPiece(move.to, board.getPiece(move.from));
  next.setPiece(move.from, null);
  return next;
}

export function getLegalMovesFor(game: Game, square: Square): Move[] {
  const piece = game.board.getPiece(square);
  if (!piece || piece.color !== game.turn) return [];
  return getPseudoLegalMoves(game.board, game.turn)
    .filter(m => m.from.file === square.file && m.from.rank === square.rank)
    .filter(m => !isKingInCheck(afterMove(game.board, m), game.turn));
}

export function applyMove(game: Game, move: Move): Game {
  const nextBoard = afterMove(game.board, move);
  return { board: nextBoard, history: [...game.history, move], turn: game.turn === 'white' ? 'black' : 'white' };
}

export function getStatus(game: Game): { turn: Color; check: boolean; checkmate: boolean; stalemate: boolean } {
  const check = isKingInCheck(game.board, game.turn);
  const legal = getPseudoLegalMoves(game.board, game.turn)
    .filter(m => !isKingInCheck(afterMove(game.board, m), game.turn));
  const none = legal.length === 0;
  return { turn: game.turn, check, checkmate: none && check, stalemate: none && !check };
}

export function undoMove(game: Game): Game {
  if (game.history.length === 0) return game;
  return { board: createInitialBoard(), history: game.history.slice(0, -1), turn: game.turn };
}""",
))

# 1e. UI node — MUST export named render(), document.createElement only.
EXAMPLES.append(t(
    "chess-ui", "Chess Game", "complex", "typescript", "ui",
    "Render the chess game UI into a container: an 8x8 board of light/dark squares, Unicode piece glyphs "
    "(♔♕♖♗♘♙♚♛♜♝♞♟), click-to-select and click-to-move, a status bar for turn/check/mate, a difficulty "
    "selector, and Undo / New Game buttons. ChessBoard has NO render method — build the DOM yourself with "
    "document.createElement.",
    CHESS_DEPS + [("chess-ai-engine", "getBestMove(board,color,config?); setDifficulty(depth); isCheckmated(board,color)"),
                  ("chess-game", "createGame(); applyMove(game,move); getLegalMovesFor(game,square); getStatus(game); undoMove(game)")],
    "render(container) — the ONLY export",
    """export function render(container: HTMLElement): void {
  container.innerHTML = '';
  const wrapper = document.createElement('div');
  wrapper.className = 'chess-app';
  const boardEl = document.createElement('div');
  boardEl.style.display = 'grid';
  boardEl.style.gridTemplateColumns = 'repeat(8, 60px)';
  boardEl.style.gridTemplateRows = 'repeat(8, 60px)';

  const game = createGame();
  const glyphs: Record<string, string> = {
    'white-king': '♔', 'white-queen': '♕', 'white-rook': '♖', 'white-bishop': '♗', 'white-knight': '♘', 'white-pawn': '♙',
    'black-king': '♚', 'black-queen': '♛', 'black-rook': '♜', 'black-bishop': '♝', 'black-knight': '♞', 'black-pawn': '♟',
  };

  for (let rank = 7; rank >= 0; rank--) {
    for (let file = 0; file < 8; file++) {
      const cell = document.createElement('button');
      cell.dataset.file = String(file);
      cell.dataset.rank = String(rank);
      cell.style.width = '60px';
      cell.style.height = '60px';
      cell.style.fontSize = '36px';
      cell.style.background = (rank + file) % 2 === 0 ? '#f0d9b5' : '#b58863';
      const piece = game.board.getPiece({ file, rank });
      if (piece) cell.textContent = glyphs[`${piece.color}-${piece.type}`] || '';
      cell.addEventListener('click', () => {
        const sq = { file: Number(cell.dataset.file), rank: Number(cell.dataset.rank) };
        const moves = getLegalMovesFor(game, sq);
        if (moves.length > 0) {
          const move = moves[0];
          applyMove(game, move);
          render(container);
        }
      });
      boardEl.appendChild(cell);
    }
  }
  wrapper.appendChild(boardEl);

  const status = getStatus(game);
  const statusEl = document.createElement('div');
  statusEl.textContent = status.checkmate ? 'Checkmate' : status.check ? 'Check!' : `${status.turn} to move`;
  wrapper.appendChild(statusEl);

  const undoBtn = document.createElement('button');
  undoBtn.textContent = 'Undo';
  undoBtn.addEventListener('click', () => { undoMove(game); render(container); });
  wrapper.appendChild(undoBtn);

  container.appendChild(wrapper);
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 2: Todo App
# ═══════════════════════════════════════════════════════════════════════════
TODO_DEPS = [
    ("todo-store", "class TodoStore { list(): Todo[]; add(title): Todo; toggle(id): Todo; remove(id): boolean; clearCompleted(): void }; createTodoStore(): TodoStore; type Todo"),
]
EXAMPLES.append(t(
    "todo-controller", "Todo App", "simple", "typescript", "logic",
    "Controller that uses the injected TodoStore (from todo-store) to implement the app actions: add a todo, "
    "toggle completion, delete a todo, and clear completed. TodoStore has NO reset method — do not invent one; "
    "only list/add/toggle/remove/clearCompleted exist.",
    TODO_DEPS,
    "createController(store) returning { addTodo, toggleTodo, deleteTodo, clearCompleted, getTodos }",
    """export interface TodoController {
  getTodos(): Todo[];
  addTodo(title: string): Todo;
  toggleTodo(id: string): Todo;
  deleteTodo(id: string): boolean;
  clearCompleted(): void;
}

export function createController(store: ReturnType<typeof createTodoStore>): TodoController {
  return {
    getTodos: () => store.list(),
    addTodo: (title: string) => store.add(title.trim() || 'Untitled'),
    toggleTodo: (id: string) => store.toggle(id),
    deleteTodo: (id: string) => store.remove(id),
    clearCompleted: () => store.clearCompleted(),
  };
}""",
))
EXAMPLES.append(t(
    "todo-ui", "Todo App", "simple", "typescript", "ui",
    "Render the todo list UI: an input to add items, a checkbox per todo, a delete button, and a 'clear "
    "completed' button. Use the controller from todo-controller and the TodoStore from todo-store. Todo "
    "objects have { id, title, done }.",
    TODO_DEPS + [("todo-controller", "createController(store); type TodoController")],
    "render(container, store) — the ONLY export",
    """export function render(container: HTMLElement, store: ReturnType<typeof createTodoStore>): void {
  container.innerHTML = '';
  const controller = createController(store);

  const input = document.createElement('input');
  input.placeholder = 'New todo…';
  const addBtn = document.createElement('button');
  addBtn.textContent = 'Add';
  addBtn.addEventListener('click', () => {
    if (input.value.trim()) { controller.addTodo(input.value); render(container, store); }
  });

  const list = document.createElement('ul');
  const refresh = () => {
    list.innerHTML = '';
    for (const todo of controller.getTodos()) {
      const li = document.createElement('li');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = todo.done;
      cb.addEventListener('change', () => { controller.toggleTodo(todo.id); refresh(); });
      const label = document.createElement('span');
      label.textContent = todo.title;
      const del = document.createElement('button');
      del.textContent = '✕';
      del.addEventListener('click', () => { controller.deleteTodo(todo.id); refresh(); });
      li.append(cb, label, del);
      list.appendChild(li);
    }
  };
  refresh();

  const clearBtn = document.createElement('button');
  clearBtn.textContent = 'Clear completed';
  clearBtn.addEventListener('click', () => { controller.clearCompleted(); refresh(); });

  container.append(input, addBtn, list, clearBtn);
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 3: Calculator
# ═══════════════════════════════════════════════════════════════════════════
CALC_DEPS = [
    ("calc-parser", "tokenize(expr): Token[]; parse(tokens): ExprNode; types Token, TokenType, ExprNode"),
]
EXAMPLES.append(t(
    "calc-engine", "Calculator", "simple", "typescript", "logic",
    "Evaluate an arithmetic expression string by parsing then walking the AST. calc-parser exposes tokenize "
    "and parse only — there is NO evaluate/visit method on nodes, so implement the recursive evaluator locally, "
    "switching on the ExprNode type field. ExprNode is a discriminated union with type 'number' | 'binary' and "
    "fields (value, left, right, operator).",
    CALC_DEPS,
    "evaluate(expr: string): number and validate(expr: string): boolean",
    """export function evaluate(expr: string): number {
  const tokens = tokenize(expr);
  const node = parse(tokens);
  return evalNode(node);
}

function evalNode(node: ExprNode): number {
  if (node.type === 'number') return node.value;
  if (node.type === 'binary') {
    const left = evalNode(node.left);
    const right = evalNode(node.right);
    switch (node.operator) {
      case '+': return left + right;
      case '-': return left - right;
      case '*': return left * right;
      case '/':
        if (right === 0) throw new Error('Division by zero');
        return left / right;
      default: throw new Error(`Unknown operator: ${node.operator}`);
    }
  }
  throw new Error('Unknown node type');
}

export function validate(expr: string): boolean {
  try {
    tokenize(expr);
    parse(expr);
    return true;
  } catch {
    return false;
  }
}""",
))
EXAMPLES.append(t(
    "calc-ui", "Calculator", "simple", "typescript", "ui",
    "Render a calculator UI: a display, digit buttons 0-9, operators + - * /, equals, and clear. The display "
    "shows the result of evaluate() and shows an error message when validate() fails. Build DOM with "
    "document.createElement only.",
    CALC_DEPS + [("calc-engine", "evaluate(expr): number; validate(expr): boolean")],
    "render(container) — the ONLY export",
    """export function render(container: HTMLElement): void {
  container.innerHTML = '';
  let current = '';

  const display = document.createElement('input');
  display.readOnly = true;
  display.style.fontSize = '24px';

  const buttons = document.createElement('div');
  buttons.style.display = 'grid';
  buttons.style.gridTemplateColumns = 'repeat(4, 48px)';
  buttons.style.gap = '4px';

  const press = (label: string, action: () => void) => {
    const btn = document.createElement('button');
    btn.textContent = label;
    btn.addEventListener('click', action);
    buttons.appendChild(btn);
  };

  for (const d of '789/456*123-0.=+'.split('')) {
    press(d, () => {
      if (d === '=') {
        if (validate(current)) display.value = String(evaluate(current));
        else display.value = 'Error';
        current = '';
      } else if (d === 'C') {
        current = '';
        display.value = '';
      } else {
        current += d;
        display.value = current;
      }
    });
  }
  press('C', () => { current = ''; display.value = ''; });

  container.append(display, buttons);
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 4: Weather Widget
# ═══════════════════════════════════════════════════════════════════════════
WEATHER_DEPS = [
    ("weather-service", "fetchForecast(city): Promise<Forecast>; type Forecast { tempC, condition, windKph, city }"),
]
EXAMPLES.append(t(
    "weather-widget", "Weather Widget", "simple", "typescript", "ui",
    "Render a weather card for a city: city name, temperature, condition, wind. Load data via fetchForecast "
    "(a Promise). weather-service exposes NO subscribe/onData method — call fetchForecast and render when it "
    "resolves, and show a loading state until then.",
    WEATHER_DEPS,
    "render(container, city) — the ONLY export",
    """export function render(container: HTMLElement, city: string): void {
  container.innerHTML = '';
  const card = document.createElement('div');
  card.className = 'weather-card';

  const title = document.createElement('h2');
  title.textContent = city;
  const body = document.createElement('p');
  body.textContent = 'Loading…';
  card.append(title, body);
  container.appendChild(card);

  fetchForecast(city).then((forecast: Forecast) => {
    body.textContent = `${forecast.tempC}°C, ${forecast.condition}, wind ${forecast.windKph} km/h`;
  }).catch(() => {
    body.textContent = 'Failed to load weather';
  });
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 5: Habit Tracker
# ═══════════════════════════════════════════════════════════════════════════
HABIT_DEPS = [
    ("habit-store", "class HabitStore { list(): Habit[]; add(name): Habit; check(id, date): void; streak(id): number; remove(id): void }; createHabitStore(): HabitStore; type Habit { id, name, checks: string[] }"),
]
EXAMPLES.append(t(
    "habit-stats", "Habit Tracker", "simple", "typescript", "logic",
    "Compute statistics over the HabitStore: total habits, habits checked today, best streak across all habits, "
    "and an overall completion rate for the last 7 days. HabitStore exposes list/add/check/streak/remove only — "
    "compute the rate by iterating list() and counting habit.checks entries within 7 days; do not invent a "
    "stats() method.",
    HABIT_DEPS,
    "getStats(store) returning { total, checkedToday, bestStreak, weekRate }",
    """export interface HabitStats {
  total: number;
  checkedToday: number;
  bestStreak: number;
  weekRate: number;
}

export function getStats(store: ReturnType<typeof createHabitStore>): HabitStats {
  const habits = store.list();
  const today = new Date().toISOString().slice(0, 10);
  let checkedToday = 0;
  let bestStreak = 0;
  let weekChecks = 0;

  for (const habit of habits) {
    if (habit.checks.includes(today)) checkedToday++;
    bestStreak = Math.max(bestStreak, store.streak(habit.id));
    const cutoff = Date.now() - 7 * 86400000;
    weekChecks += habit.checks.filter(d => new Date(d).getTime() >= cutoff).length;
  }

  const weekRate = habits.length > 0 ? weekChecks / (habits.length * 7) : 0;
  return { total: habits.length, checkedToday, bestStreak, weekRate: Math.round(weekRate * 100) / 100 };
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 6: Text Adventure
# ═══════════════════════════════════════════════════════════════════════════
ADVENTURE_DEPS = [
    ("room-model", "createRoom(id, name, desc, exits): Room; getRoomById(rooms, id): Room | undefined; type Room { id, name, description, exits: Record<string, string> }"),
    ("player-model", "createPlayer(name): Player; movePlayer(player, roomId): Player; type Player { name, currentRoomId, inventory: string[] }"),
]
EXAMPLES.append(t(
    "game-engine", "Text Adventure", "medium", "typescript", "logic",
    "Game engine: start a game with a starting room, handle a 'go <direction>' command by looking up the exit "
    "in the current Room.exits map and moving via movePlayer, and handle 'take <item>' by appending to "
    "player.inventory locally (there is no takeItem method on Player — mutate a copy). Return a human-readable "
    "response string for each command. Player is a whitelisted type from player-model — use it without writing "
    "any import statement (the build system adds imports).",
    ADVENTURE_DEPS,
    "startGame(rooms, playerName): GameState; handleCommand(state, command): string; type GameState",
    """export interface GameState {
  player: Player;
  rooms: Room[];
  message: string;
}

export function startGame(rooms: Room[], playerName: string): GameState {
  const player = createPlayer(playerName);
  player.currentRoomId = rooms[0]?.id ?? '';
  return { player, rooms, message: describeRoom(rooms, player.currentRoomId) };
}

function describeRoom(rooms: Room[], roomId: string): string {
  const room = getRoomById(rooms, roomId);
  if (!room) return 'You are lost.';
  const exits = Object.keys(room.exits).join(', ');
  return `${room.name}\n${room.description}\nExits: ${exits || 'none'}`;
}

export function handleCommand(state: GameState, command: string): string {
  const parts = command.trim().toLowerCase().split(/\\s+/);
  const verb = parts[0];
  const arg = parts.slice(1).join(' ');
  const room = getRoomById(state.rooms, state.player.currentRoomId);

  if (verb === 'go' && room) {
    const dest = room.exits[arg];
    if (!dest) return `You cannot go ${arg}.`;
    state.player = movePlayer(state.player, dest);
    return describeRoom(state.rooms, state.player.currentRoomId);
  }
  if (verb === 'take' && arg) {
    const player = { ...state.player, inventory: [...state.player.inventory, arg] };
    state.player = player;
    return `You take the ${arg}.`;
  }
  if (verb === 'look') return describeRoom(state.rooms, state.player.currentRoomId);
  if (verb === 'inventory') return state.player.inventory.length ? `You carry: ${state.player.inventory.join(', ')}` : 'You carry nothing.';
  return `I don't understand "${command}".`;
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 7: Music Player
# ═══════════════════════════════════════════════════════════════════════════
MUSIC_DEPS = [
    ("playlist-model", "createPlaylist(name): Playlist; addTrack(playlist, track): Playlist; nextTrack(playlist): Track | undefined; type Playlist { name, tracks: Track[] }; type Track { id, title, artist, durationSec }"),
]
EXAMPLES.append(t(
    "player-engine", "Music Player", "medium", "typescript", "logic",
    "Playback engine built on playlist-model: a Player holds a current playlist, a current index, and a "
    "playing flag. There is no Player class in playlist-model — the exports are pure functions on Playlist "
    "objects — so model the engine state as a plain object with an index, and advance it with nextTrack().",
    MUSIC_DEPS,
    "createPlayer(playlist): PlayerState; play(state): PlayerState; pause(state): PlayerState; skip(state): PlayerState",
    """export interface PlayerState {
  playlist: Playlist;
  index: number;
  playing: boolean;
}

export function createPlayer(playlist: Playlist): PlayerState {
  return { playlist, index: 0, playing: false };
}

export function currentTrack(state: PlayerState): Track | undefined {
  return state.playlist.tracks[state.index];
}

export function play(state: PlayerState): PlayerState {
  return { ...state, playing: true };
}

export function pause(state: PlayerState): PlayerState {
  return { ...state, playing: false };
}

export function skip(state: PlayerState): PlayerState {
  const next = nextTrack(state.playlist);
  if (!next) return { ...state, playing: false, index: state.playlist.tracks.length };
  return { ...state, index: state.index + 1, playing: true };
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 8: Go variant (order service) — cross-language generalization
# ═══════════════════════════════════════════════════════════════════════════
GO_DEPS = [
    ("models", "type Order struct { ID string; Items []OrderItem; Status string }; type OrderItem struct { SKU string; Qty int; PriceCents int }"),
]
EXAMPLES.append(t(
    "order_service", "Order Service", "complex", "go", "logic",
    "Business rules on the Order model: compute the total in cents (sum Items Qty*PriceCents), validate an "
    "order (non-empty ID, at least one item, all quantities > 0), and advance status from 'created' to "
    "'paid' to 'shipped'. The Order struct has NO methods — write plain functions taking *Order. Do NOT write "
    "any import statement (the build system adds them); define a small local error type instead of importing errors.",
    GO_DEPS,
    "TotalCents(o *Order) int; Validate(o *Order) error; AdvanceStatus(o *Order)",
    """package order_service

// errOrder is a local error type so no import of the errors package is needed.
type errOrder string

func (e errOrder) Error() string { return string(e) }

func TotalCents(o *Order) int {
	total := 0
	for _, it := range o.Items {
		total += it.Qty * it.PriceCents
	}
	return total
}

func Validate(o *Order) error {
	if o.ID == "" {
		return errOrder("order id is required")
	}
	if len(o.Items) == 0 {
		return errOrder("order must have at least one item")
	}
	for _, it := range o.Items {
		if it.Qty <= 0 {
			return errOrder("item quantity must be positive")
		}
	}
	return nil
}

func AdvanceStatus(o *Order) {
	switch o.Status {
	case "created":
		o.Status = "paid"
	case "paid":
		o.Status = "shipped"
	}
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 9: Python variant (data processor) — cross-language generalization
# ═══════════════════════════════════════════════════════════════════════════
PY_DEPS = [
    ("db", "connect(path: str) -> Connection; Connection has .execute(sql, params) -> Cursor and .close() -> None"),
]
EXAMPLES.append(t(
    "processor", "Data Processor", "medium", "python", "logic",
    "Process rows from an SQLite-like connection: run a SELECT, normalize rows (strip whitespace, coerce "
    "numeric columns), and return a summary dict {count, total}. The Connection object has execute() and "
    "close() only — do not call a non-existent fetch_all method; use the cursor returned by execute().",
    PY_DEPS,
    "process(conn) -> dict and normalize_row(row) -> dict",
    """def normalize_row(row):
    out = {}
    for key, value in row.items():
        if isinstance(value, str):
            value = value.strip()
        out[key] = value
    return out


def process(conn):
    cursor = conn.execute("SELECT * FROM items")
    rows = cursor.fetchall()
    normalized = [normalize_row(r) for r in rows]
    total = 0
    for r in normalized:
        try:
            total += float(r.get("amount", 0))
        except (TypeError, ValueError):
            continue
    return {"count": len(normalized), "total": total}""",
))


# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 10: Markdown Previewer
# ═══════════════════════════════════════════════════════════════════════════
MD_DEPS = [
    ("md-tokenizer", "tokenize(md: string): Token[]; type Token { type: 'heading'|'bold'|'text'|'link'; content: string; href?: string }"),
]
EXAMPLES.append(t(
    "md-renderer", "Markdown Previewer", "medium", "typescript", "logic",
    "Render an array of Markdown tokens to an HTML string. md-tokenizer exposes tokenize and the Token type "
    "only — there is NO render function on tokens; build the HTML string locally by switching on token.type. "
    "Never escape user content with innerHTML on a live page; here we return a static string.",
    MD_DEPS,
    "renderMarkdown(md: string): string",
    """export function renderMarkdown(md: string): string {
  const tokens = tokenize(md);
  let html = '';
  for (const token of tokens) {
    switch (token.type) {
      case 'heading':
        html += `<h1>${escapeHtml(token.content)}</h1>`;
        break;
      case 'bold':
        html += `<strong>${escapeHtml(token.content)}</strong>`;
        break;
      case 'link':
        html += `<a href="${escapeAttr(token.href ?? '#')}">${escapeHtml(token.content)}</a>`;
        break;
      default:
        html += escapeHtml(token.content);
    }
  }
  return html;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeAttr(s: string): string {
  return s.replace(/"/g, '&quot;');
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 11: Quiz App
# ═══════════════════════════════════════════════════════════════════════════
QUIZ_DEPS = [
    ("question-bank", "class QuestionBank { all(): Question[]; byCategory(cat): Question[]; shuffle(seed?): Question[] }; createQuestionBank(questions): QuestionBank; type Question { id, text, options: string[], correctIndex, category }"),
]
EXAMPLES.append(t(
    "quiz-scorer", "Quiz App", "simple", "typescript", "logic",
    "Score a quiz attempt: compare user answers (a map of question id -> chosen index) against the correct "
    "answers fetched from the QuestionBank. QuestionBank has NO isCorrect method — implement the comparison "
    "locally using the Question.correctIndex field.",
    QUIZ_DEPS,
    "scoreAttempt(bank, answers): { correct, total, percent } and isCorrect(question, chosenIndex): boolean",
    """export interface QuizResult { correct: number; total: number; percent: number; }

export function isCorrect(question: Question, chosenIndex: number): boolean {
  return chosenIndex === question.correctIndex;
}

export function scoreAttempt(bank: ReturnType<typeof createQuestionBank>, answers: Record<string, number>): QuizResult {
  const questions = bank.all();
  let correct = 0;
  for (const q of questions) {
    const chosen = answers[q.id];
    if (chosen !== undefined && isCorrect(q, chosen)) correct++;
  }
  const total = questions.length;
  return { correct, total, percent: total > 0 ? Math.round((correct / total) * 100) : 0 };
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 12: Budget Tracker
# ═══════════════════════════════════════════════════════════════════════════
BUDGET_DEPS = [
    ("ledger", "class Ledger { entries(): LedgerEntry[]; add(entry): void; remove(id): boolean; total(): number }; createLedger(): Ledger; type LedgerEntry { id, amount, category, note, date };"),
]
EXAMPLES.append(t(
    "budget-service", "Budget Tracker", "medium", "typescript", "logic",
    "Report helpers over a Ledger: spend by category, biggest single expense, and a monthly summary. The Ledger "
    "exposes entries()/add()/remove()/total() only — compute everything else locally by iterating entries(). "
    "Do not call a non-existent getByCategory method.",
    BUDGET_DEPS,
    "spendByCategory(ledger): Record<string, number>; biggestExpense(ledger): LedgerEntry | null; monthlySummary(ledger, month): { income, expenses, net }",
    """export function spendByCategory(ledger: ReturnType<typeof createLedger>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of ledger.entries()) {
    if (e.amount < 0) out[e.category] = (out[e.category] ?? 0) + Math.abs(e.amount);
  }
  return out;
}

export function biggestExpense(ledger: ReturnType<typeof createLedger>): LedgerEntry | null {
  let best: LedgerEntry | null = null;
  for (const e of ledger.entries()) {
    if (e.amount < 0 && (!best || e.amount < best.amount)) best = e;
  }
  return best;
}

export function monthlySummary(ledger: ReturnType<typeof createLedger>, month: string): { income: number; expenses: number; net: number } {
  let income = 0, expenses = 0;
  for (const e of ledger.entries()) {
    if (!e.date.startsWith(month)) continue;
    if (e.amount >= 0) income += e.amount;
    else expenses += Math.abs(e.amount);
  }
  return { income, expenses, net: income - expenses };
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 13: Pomodoro Timer
# ═══════════════════════════════════════════════════════════════════════════
POMODORO_DEPS = [
    ("pomodoro-config", "loadConfig(): PomodoroConfig; saveConfig(cfg): void; type PomodoroConfig { workMin, shortBreakMin, longBreakMin, rounds }"),
]
EXAMPLES.append(t(
    "pomodoro-engine", "Pomodoro Timer", "simple", "typescript", "logic",
    "Timer engine that tracks a session: work / short break / long break phases, remaining seconds, and "
    "phase transitions. pomodoro-config has loadConfig/saveConfig only — do NOT invent a getPhase method on "
    "the config; track the phase as plain engine state and read durations from the loaded config.",
    POMODORO_DEPS,
    "createSession(): Session; tick(session): Session; phaseOf(session): 'work'|'short'|'long'; isSessionDone(session): boolean; type Session",
    """export type Phase = 'work' | 'short' | 'long';

export interface Session {
  phase: Phase;
  remainingSec: number;
  round: number;
  config: PomodoroConfig;
}

function phaseDuration(config: PomodoroConfig, phase: Phase): number {
  if (phase === 'work') return config.workMin * 60;
  if (phase === 'short') return config.shortBreakMin * 60;
  return config.longBreakMin * 60;
}

export function createSession(): Session {
  const config = loadConfig();
  return { phase: 'work', remainingSec: config.workMin * 60, round: 1, config };
}

export function phaseOf(session: Session): Phase {
  return session.phase;
}

export function tick(session: Session): Session {
  if (session.remainingSec > 1) return { ...session, remainingSec: session.remainingSec - 1 };
  if (session.phase === 'work') {
    const long = session.round % session.config.rounds === 0;
    return { ...session, phase: long ? 'long' : 'short', remainingSec: phaseDuration(session.config, long ? 'long' : 'short'), round: long ? session.round + 1 : session.round };
  }
  return { ...session, phase: 'work', remainingSec: phaseDuration(session.config, 'work') };
}

export function isSessionDone(session: Session): boolean {
  return session.remainingSec <= 0;
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 14: Chat App
# ═══════════════════════════════════════════════════════════════════════════
CHAT_DEPS = [
    ("chat-store", "class ChatStore { messages(): Message[]; send(text, author): Message; delete(id): boolean; unreadCount(): number }; createChatStore(): ChatStore; type Message { id, text, author, ts, read }"),
]
EXAMPLES.append(t(
    "chat-service", "Chat App", "simple", "typescript", "logic",
    "Compose messages into a channel view: group by date, count unread, and format a message preview. ChatStore "
    "exposes messages/send/delete/unreadCount only — do not call store.groupByDate; do the grouping locally "
    "with a Map over messages().",
    CHAT_DEPS,
    "groupByDate(store): Map<string, Message[]>; preview(message): string; unreadFor(store): number",
    """export function groupByDate(store: ReturnType<typeof createChatStore>): Map<string, Message[]> {
  const groups = new Map<string, Message[]>();
  for (const m of store.messages()) {
    const day = m.ts.slice(0, 10);
    const arr = groups.get(day) ?? [];
    arr.push(m);
    groups.set(day, arr);
  }
  return groups;
}

export function preview(message: Message): string {
  return message.text.length > 60 ? message.text.slice(0, 60) + '…' : message.text;
}

export function unreadFor(store: ReturnType<typeof createChatStore>): number {
  return store.unreadCount();
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 15: File Explorer
# ═══════════════════════════════════════════════════════════════════════════
FS_DEPS = [
    ("fs-adapter", "listDir(path): Promise<FileEntry[]>; readFile(path): Promise<string>; exists(path): Promise<boolean>; type FileEntry { name, path, isDir, size };"),
]
EXAMPLES.append(t(
    "file-explorer-logic", "File Explorer", "simple", "typescript", "logic",
    "Explorer navigation logic on top of the async fs-adapter: resolve a path (handle '..' and '.'), list a "
    "directory, and compute a breadcrumb trail. fs-adapter exposes listDir/readFile/exists only — there is no "
    "resolve method; implement path normalization locally with split/filter/join.",
    FS_DEPS,
    "resolvePath(path: string): string; breadcrumbs(path: string): string[]; listDirSafe(path): Promise<FileEntry[]>",
    """export function resolvePath(path: string): string {
  const parts = path.split('/').filter(p => p !== '' && p !== '.');
  const out: string[] = [];
  for (const p of parts) {
    if (p === '..') out.pop();
    else out.push(p);
  }
  return '/' + out.join('/');
}

export function breadcrumbs(path: string): string[] {
  const parts = resolvePath(path).split('/').filter(Boolean);
  return parts.map((_, i) => '/' + parts.slice(0, i + 1).join('/'));
}

export async function listDirSafe(path: string): Promise<FileEntry[]> {
  const resolved = resolvePath(path);
  if (!(await exists(resolved))) return [];
  return listDir(resolved);
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 16: Tic-Tac-Toe
# ═══════════════════════════════════════════════════════════════════════════
TTT_DEPS = [
    ("ttt-board", "createBoard(): Board; boardEmpty(board): boolean; type Board = (Player | null)[]; type Player = 'X' | 'O';"),
]
EXAMPLES.append(t(
    "ttt-engine", "Tic-Tac-Toe", "simple", "typescript", "logic",
    "Win detection and move application on a flat 9-cell Board. ttt-board exports createBoard and the Board/Player "
    "types only — there are NO methods on Board; implement makeMove and winner locally by indexing the array, "
    "and validate the move (cell empty, game not over) yourself.",
    TTT_DEPS,
    "makeMove(board, index, player): Board; winner(board): Player | null; isDraw(board): boolean",
    """const LINES = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8],
  [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6],
];

export function makeMove(board: Board, index: number, player: Player): Board {
  if (index < 0 || index > 8 || board[index] !== null || winner(board)) return board;
  const next = board.slice();
  next[index] = player;
  return next;
}

export function winner(board: Board): Player | null {
  for (const line of LINES) {
    const [a, b, c] = line;
    if (board[a] && board[a] === board[b] && board[a] === board[c]) return board[a];
  }
  return null;
}

export function isDraw(board: Board): boolean {
  return !winner(board) && board.every(cell => cell !== null);
}""",
))

# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN 17: Chess UI with AI difficulty (trap: must not invent board.render)
# ═══════════════════════════════════════════════════════════════════════════
EXAMPLES.append(t(
    "chess-ui", "Chess Game", "complex", "typescript", "ui",
    "Chess UI with an AI opponent: board rendering, human moves, and an AI reply via getBestMove when the "
    "difficulty selector changes. ChessBoard has NO render method — draw every square with "
    "document.createElement. After a human move, call getBestMove(game.board, 'black', { depth: difficulty }) "
    "and apply the returned Move with the local apply-move helper (clone+setPiece), then re-render.",
    CHESS_DEPS + [("chess-ai-engine", "getBestMove(board,color,config?): Move|null; setDifficulty(depth); type AIConfig")],
    "render(container) — the ONLY export",
    """const GLYPHS: Record<string, string> = {
  'white-king': '♔', 'white-queen': '♕', 'white-rook': '♖', 'white-bishop': '♗', 'white-knight': '♘', 'white-pawn': '♙',
  'black-king': '♚', 'black-queen': '♛', 'black-rook': '♜', 'black-bishop': '♝', 'black-knight': '♞', 'black-pawn': '♟',
};

export function render(container: HTMLElement): void {
  container.innerHTML = '';
  const board = createInitialBoard();
  let difficulty = 2;

  const grid = document.createElement('div');
  grid.style.display = 'grid';
  grid.style.gridTemplateColumns = 'repeat(8, 60px)';
  grid.style.gridTemplateRows = 'repeat(8, 60px)';

  const draw = () => {
    grid.innerHTML = '';
    for (let rank = 7; rank >= 0; rank--) {
      for (let file = 0; file < 8; file++) {
        const cell = document.createElement('button');
        cell.style.width = '60px';
        cell.style.height = '60px';
        cell.style.fontSize = '36px';
        cell.style.background = (rank + file) % 2 === 0 ? '#f0d9b5' : '#b58863';
        const piece = board.getPiece({ file, rank });
        if (piece) cell.textContent = GLYPHS[`${piece.color}-${piece.type}`] ?? '';
        cell.addEventListener('click', () => {
          const move = { from: { file, rank }, to: { file: file + 1, rank: rank + 1 } };
          const candidate = getPseudoLegalMoves(board, 'white')
            .filter(m => m.from.file === file && m.from.rank === rank)
            .find(m => m.to.file === move.to.file && m.to.rank === move.to.rank);
          if (!candidate) return;
          applyMoveLocal(candidate);
          const ai = getBestMove(board, 'black', { depth: difficulty });
          if (ai) applyMoveLocal(ai);
          draw();
        });
        grid.appendChild(cell);
      }
    }
  };

  function applyMoveLocal(m: Move): void {
    const from = board.getPiece(m.from);
    board.setPiece(m.to, from);
    board.setPiece(m.from, null);
  }

  const diff = document.createElement('select');
  [1, 2, 3, 4].forEach(d => {
    const opt = document.createElement('option');
    opt.value = String(d);
    opt.textContent = `Depth ${d}`;
    diff.appendChild(opt);
  });
  diff.value = '2';
  diff.addEventListener('change', () => { difficulty = Number(diff.value); setDifficulty(difficulty); });

  draw();
  container.append(diff, grid);
}""",
))

# ─────────────────────────────────────────────────────────────────────────────
def write_split(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"  wrote {len(records)} -> {os.path.relpath(path, BASE)}")


def build():
    random.seed(42)
    shuffled = list(EXAMPLES)
    random.shuffle(shuffled)
    n = len(shuffled)
    n_test = max(2, int(n * 0.15))
    n_val = max(2, int(n * 0.15))
    test, val, train = shuffled[:n_test], shuffled[n_test:n_test + n_val], shuffled[n_test + n_val:]
    os.makedirs(OUT_DIR, exist_ok=True)
    write_split(OUT_TRAIN, train)
    write_split(OUT_VAL, val)
    write_split(OUT_TEST, test)
    stats = {
        "total_examples": n,
        "train": len(train), "val": len(val), "test": len(test),
        "languages": ["typescript", "go", "python"],
        "avg_output_chars": round(sum(len(r["output"]) for r in shuffled) / n, 1),
        "avg_instruction_chars": round(sum(len(r["instruction"]) for r in shuffled) / n, 1),
        "note": "Cross-file contract-fidelity dataset. Member whitelists in input; outputs use ONLY whitelisted members.",
    }
    with open(os.path.join(OUT_DIR, "contract-fidelity-meta.json"), "w") as f:
        json.dump(stats, f, indent=1)
    print(f"  stats: {json.dumps(stats, indent=1)}")


# ─────────────────────────────────────────────────────────────────────────────
# Validation: lint + tsc on chess examples against the real scaffolds
# ─────────────────────────────────────────────────────────────────────────────
def find_tsc():
    cands = [os.path.join(BASE, "node_modules", "typescript", "bin", "tsc"),
             os.path.join(BASE, "backend", "node_modules", ".bin", "tsc"),
             os.path.join(BASE, "node_modules", ".bin", "tsc")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return shutil.which("tsc")


def lint_output(rec, idx):
    errs = []
    out = rec["output"]
    if "```" in out:
        errs.append(f"[{idx}] output contains markdown fences")
    if re.search(r"^import\s", out, re.M):
        errs.append(f"[{idx}] output contains import statements")
    if "export default" in out:
        errs.append(f"[{idx}] output uses export default")
    # Stub markers: TODO anywhere; Not implemented / placeholder in comments or error strings
    if re.search(r"\bTODO\b", out) or \
       re.search(r"(?://|/\*|\*).{0,60}\b(?:Not implemented|placeholder)\b", out, re.I) or \
       re.search(r"Error\('\s*Not implemented", out, re.I):
        errs.append(f"[{idx}] output contains TODO/stub markers")
    if re.search(r"<\s*(?:div|button|span|li|input|select)\b", out) and "document.createElement" in out:
        errs.append(f"[{idx}] output mixes JSX-style tags with createElement (should be createElement only)")
    return errs


def tsc_check_chess(recs):
    tsc = find_tsc()
    if not tsc:
        return ["tsc not found — skipping compile check"]
    errs = []
    tmp_root = tempfile.mkdtemp(prefix="contract-fidelity-tsc-")
    tmp = os.path.join(tmp_root, "scaffold")
    os.makedirs(tmp, exist_ok=True)
    for dep in ["chess-board", "chess-move-rules", "chess-ai-engine", "chess-game", "chess-ui"]:
        os.makedirs(os.path.join(tmp, dep), exist_ok=True)
    with open(os.path.join(tmp, "chess-board", "chess-board.ts"), "w") as f:
        f.write(SCAFFOLD_BOARD)
    with open(os.path.join(tmp, "chess-move-rules", "chess-move-rules.ts"), "w") as f:
        f.write(SCAFFOLD_MOVE_RULES)
    # Scaffold for chess-game + chess-ai-engine used by the UI node
    game_scaffold = """import { ChessBoard, Color, Square, Piece, BoardState } from '../chess-board/chess-board';
import { Move } from '../chess-move-rules/chess-move-rules';
export interface Game { board: ChessBoard; history: Move[]; turn: Color; }
export function createGame(): Game { return { board: new ChessBoard(), history: [], turn: 'white' }; }
export function applyMove(game: Game, move: Move): Game { return game; }
export function getLegalMovesFor(game: Game, sq: Square): Move[] { return []; }
export function getStatus(game: Game): { turn: Color; check: boolean; checkmate: boolean; stalemate: boolean } {
  return { turn: 'white', check: false, checkmate: false, stalemate: false };
}
export function undoMove(game: Game): Game { return game; }"""
    ai_scaffold = """import { ChessBoard, Color, Square } from '../chess-board/chess-board';
import { Move } from '../chess-move-rules/chess-move-rules';
export interface AIConfig { depth?: number; }
export function getBestMove(board: ChessBoard, color: Color, config?: AIConfig): Move | null { return null; }
export function setDifficulty(depth: number): AIConfig { return { depth: depth }; }
export function isCheckmated(board: ChessBoard, color: Color): boolean { return false; }"""
    with open(os.path.join(tmp, "chess-game", "chess-game.ts"), "w") as f:
        f.write(game_scaffold)
    with open(os.path.join(tmp, "chess-ai-engine", "chess-ai-engine.ts"), "w") as f:
        f.write(ai_scaffold)

    imports_map = {
        "chess-ai-engine": ("import { ChessBoard, createInitialBoard, Square, Color, Piece, BoardState } from '../chess-board/chess-board';\n"
                            "import { Move, getPseudoLegalMoves, isSquareAttacked, isKingInCheck, isCastlingLegal } from '../chess-move-rules/chess-move-rules';\n"),
        "chess-game": ("import { ChessBoard, createInitialBoard, Square, Color, Piece, BoardState } from '../chess-board/chess-board';\n"
                       "import { Move, getPseudoLegalMoves, isSquareAttacked, isKingInCheck, isCastlingLegal } from '../chess-move-rules/chess-move-rules';\n"),
        "chess-ui": ("import { ChessBoard, createInitialBoard, Square, Color, Piece, BoardState } from '../chess-board/chess-board';\n"
                     "import { Move, getPseudoLegalMoves, isSquareAttacked, isKingInCheck, isCastlingLegal } from '../chess-move-rules/chess-move-rules';\n"
                     "import { createGame, applyMove, getLegalMovesFor, getStatus, undoMove, Game } from '../chess-game/chess-game';\n"
                     "import { getBestMove, setDifficulty, isCheckmated, AIConfig } from '../chess-ai-engine/chess-ai-engine';\n"),
    }
    # Per-example subdirs so a generated chess-ai-engine example never overwrites the scaffold
    for i, rec in enumerate(recs):
        node = re.search(r"node '([^']+)'", rec["instruction"])
        if not node:
            continue
        name = node.group(1)
        imports = imports_map.get(name)
        if not imports:
            continue
        exdir = os.path.join(tmp_root, f"ex{i}")
        os.makedirs(os.path.join(exdir, name), exist_ok=True)
        # strip any imports the author accidentally left, then prepend pipeline imports
        out = re.sub(r"^import\s[^\n]*\n?", "", rec["output"], flags=re.M)
        dest = os.path.join(exdir, name, f"{name}.ts")
        # rewrite scaffold-relative paths so all deps resolve under the per-example dir
        imports = imports.replace("../chess-board/chess-board", "../../scaffold/chess-board/chess-board")
        imports = imports.replace("../chess-move-rules/chess-move-rules", "../../scaffold/chess-move-rules/chess-move-rules")
        imports = imports.replace("../chess-game/chess-game", "../../scaffold/chess-game/chess-game")
        imports = imports.replace("../chess-ai-engine/chess-ai-engine", "../../scaffold/chess-ai-engine/chess-ai-engine")
        with open(dest, "w") as f:
            f.write(imports + "\n" + out)
        r = subprocess.run([tsc, "--noEmit", "--strict", "--target", "es2020", "--module", "commonjs",
                            "--moduleResolution", "node", "--skipLibCheck", "--esModuleInterop", dest],
                           capture_output=True, text=True, timeout=180)
        clean = r.returncode == 0
        if not clean:
            errs.append(f"[chess-{name}] tsc FAILED:\n" + "\n".join(
                l for l in r.stdout.splitlines() if "error TS" in l)[:1200])
        else:
            print(f"  ✅ chess-{name} compiles clean")
    shutil.rmtree(tmp_root, ignore_errors=True)
    return errs


def validate():
    errs = []
    for path, label in [(OUT_TRAIN, "train"), (OUT_VAL, "val"), (OUT_TEST, "test")]:
        if not os.path.exists(path):
            errs.append(f"missing {label}: {path}")
            continue
        recs = [json.loads(l) for l in open(path) if l.strip()]
        for i, rec in enumerate(recs):
            for k in ("instruction", "input", "output"):
                if not rec.get(k):
                    errs.append(f"[{label}:{i}] missing field {k}")
            errs.extend(lint_output(rec, f"{label}:{i}"))
        print(f"  {label}: {len(recs)} records linted")
    if not errs:
        print("  ✅ lint clean (no fences / imports / export-default / TODOs / JSX-in-createElement)")
    else:
        print(f"  ❌ {len(errs)} lint issues:")
        for e in errs[:20]:
            print("   ", e)

    # tsc on chess examples from the train split (guard: skip if train file missing)
    if not os.path.exists(OUT_TRAIN):
        print("  ⚠️  train file missing — skipping tsc chess check")
        return
    chess_recs = [json.loads(l) for l in open(OUT_TRAIN) if "Chess Game" in l]
    print(f"  tsc-checking {len(chess_recs)} chess examples…")
    for e in tsc_check_chess(chess_recs):
        print("   ❌", e)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="lint + tsc-check the built dataset")
    args = ap.parse_args()
    if args.validate:
        validate()
    else:
        build()
