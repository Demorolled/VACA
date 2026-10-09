#!/usr/bin/env python3
"""Crystal Chess — pure rules engine (no pygame dependency).

Implements full standard chess: legal move generation for every piece,
castling (with all rights/attacks-through-square checks), en passant,
pawn promotion, check / checkmate / stalemate detection, and the draw rules
(fifty-move, threefold repetition, insufficient material).

The AI is a minimax search with alpha-beta pruning, capture-ordered moves and
piece-square evaluation tables. Depth is configurable (default 2 + capture
extension, which plays a reasonable club-level game instantly; 3 is stronger).

Board convention:
  board[r][c] is None or a tuple ('w'|'b', 'KQRNBP'). a8 is (0,0).
  Moves are (from_r, from_c, to_r, to_c, promotion) with promotion in 'QRNB'
  (empty string = none).
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

Piece = Tuple[str, str]          # ('w', 'K') etc.
Move = Tuple[int, int, int, int, str]
Board = List[List[Optional[Piece]]]

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

PIECE_ORDER = {'K': 0, 'Q': 1, 'R': 2, 'B': 3, 'N': 4, 'P': 5}
PIECE_NAMES = {'K': 'King', 'Q': 'Queen', 'R': 'Rook', 'B': 'Bishop',
               'N': 'Knight', 'P': 'Pawn'}
SIDE_NAMES = {'w': 'White', 'b': 'Black'}

# Material values + piece-square tables (white perspective; mirrored for black).
VALUES = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 0}

PST = {
    'P': [
        0, 0, 0, 0, 0, 0, 0, 0,
        50, 50, 50, 50, 50, 50, 50, 50,
        10, 10, 20, 30, 30, 20, 10, 10,
        5, 5, 10, 25, 25, 10, 5, 5,
        0, 0, 0, 20, 20, 0, 0, 0,
        5, -5, -10, 0, 0, -10, -5, 5,
        5, 10, 10, -20, -20, 10, 10, 5,
        0, 0, 0, 0, 0, 0, 0, 0,
    ],
    'N': [
        -50, -40, -30, -30, -30, -30, -40, -50,
        -40, -20, 0, 0, 0, 0, -20, -40,
        -30, 0, 10, 15, 15, 10, 0, -30,
        -30, 5, 15, 20, 20, 15, 5, -30,
        -30, 0, 15, 20, 20, 15, 0, -30,
        -30, 5, 10, 15, 15, 10, 5, -30,
        -40, -20, 0, 5, 5, 0, -20, -40,
        -50, -40, -30, -30, -30, -30, -40, -50,
    ],
    'B': [
        -20, -10, -10, -10, -10, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 10, 10, 5, 0, -10,
        -10, 5, 5, 10, 10, 5, 5, -10,
        -10, 0, 10, 10, 10, 10, 0, -10,
        -10, 10, 10, 10, 10, 10, 10, -10,
        -10, 5, 0, 0, 0, 0, 5, -10,
        -20, -10, -10, -10, -10, -10, -10, -20,
    ],
    'R': [
        0, 0, 0, 0, 0, 0, 0, 0,
        5, 10, 10, 10, 10, 10, 10, 5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        -5, 0, 0, 0, 0, 0, 0, -5,
        0, 0, 0, 5, 5, 0, 0, 0,
    ],
    'Q': [
        -20, -10, -10, -5, -5, -10, -10, -20,
        -10, 0, 0, 0, 0, 0, 0, -10,
        -10, 0, 5, 5, 5, 5, 0, -10,
        -5, 0, 5, 5, 5, 5, 0, -5,
        0, 0, 5, 5, 5, 5, 0, -5,
        -10, 5, 5, 5, 5, 5, 0, -10,
        -10, 0, 5, 0, 0, 0, 0, -10,
        -20, -10, -10, -5, -5, -10, -10, -20,
    ],
    'K': [
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -30, -40, -40, -50, -50, -40, -40, -30,
        -20, -30, -30, -40, -40, -30, -30, -20,
        -10, -20, -20, -20, -20, -20, -20, -10,
        20, 20, 0, 0, 0, 0, 20, 20,
        20, 30, 10, 0, 0, 10, 30, 20,
    ],
}

# Endgame king tables (used when few pieces remain).
PST_KING_END = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10, 0, 0, -10, -20, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 30, 40, 40, 30, -10, -30,
    -30, -10, 20, 30, 30, 20, -10, -30,
    -30, -30, 0, 0, 0, 0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
]


def mirror_sq(sq: int) -> int:
    return (7 - sq // 8) * 8 + (sq % 8)


def board_to_sq(r: int, c: int) -> int:
    return r * 8 + c


def sq_to_board(sq: int) -> Tuple[int, int]:
    return sq // 8, sq % 8


def make_start_board() -> Board:
    rows = START_FEN.split(' ')[0].split('/')
    board: Board = [[None] * 8 for _ in range(8)]
    for r, fen_row in enumerate(rows):
        c = 0
        for ch in fen_row:
            if ch.isdigit():
                c += int(ch)
            else:
                color = 'w' if ch.isupper() else 'b'
                board[r][c] = (color, ch.upper())
                c += 1
    return board


class ChessGame:
    """Full chess state with legal-move generation and draw detection."""

    def __init__(self, fen: str = START_FEN) -> None:
        parts = fen.split(' ')
        self.board = make_start_board()
        if fen != START_FEN and parts[0]:
            self.board = self._board_from_fen(parts[0])
        self.turn = parts[1] if len(parts) > 1 else 'w'
        self.castle = {'K': 'K' in (parts[2] if len(parts) > 2 else 'KQkq'),
                       'Q': 'Q' in (parts[2] if len(parts) > 2 else 'KQkq'),
                       'k': 'k' in (parts[2] if len(parts) > 2 else 'KQkq'),
                       'q': 'q' in (parts[2] if len(parts) > 2 else 'KQkq')}
        self.ep = None          # en-passant target square (r, c) or None
        self.halfmove = 0       # fifty-move clock
        self.fullmove = 1
        self.history: List[dict] = []          # undo stack
        self.position_counts = {}              # threefold repetition
        self.key = self._position_key()
        self.position_counts[self.key] = 1

    @staticmethod
    def _board_from_fen(placement: str) -> Board:
        board: Board = [[None] * 8 for _ in range(8)]
        for r, fen_row in enumerate(placement.split('/')):
            c = 0
            for ch in fen_row:
                if ch.isdigit():
                    c += int(ch)
                else:
                    color = 'w' if ch.isupper() else 'b'
                    board[r][c] = (color, ch.upper())
                    c += 1
        return board

    def _position_key(self) -> str:
        rows = []
        for r in range(8):
            row = ''
            empty = 0
            for c in range(8):
                p = self.board[r][c]
                if p is None:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    color, kind = p
                    ch = kind if color == 'w' else kind.lower()
                    row += ch
            if empty:
                row += str(empty)
            rows.append(row)
        castle = ''.join(k for k in 'KQkq' if self.castle.get(k))
        ep = f'{self.ep[0]},{self.ep[1]}' if self.ep else '-'
        return f"{'/'.join(rows)} {self.turn} {castle} {ep}"

    # ── helpers ──────────────────────────────────────────────────────────
    def piece_at(self, r: int, c: int) -> Optional[Piece]:
        if 0 <= r < 8 and 0 <= c < 8:
            return self.board[r][c]
        return None

    def king_square(self, color: str) -> Tuple[int, int]:
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p and p == (color, 'K'):
                    return (r, c)
        return (-1, -1)  # unreachable in a legal game

    def is_attacked(self, r: int, c: int, by_color: str) -> bool:
        """Is square (r,c) attacked by any piece of `by_color`?"""
        # Pawns
        pr = r + (1 if by_color == 'w' else -1)
        for pc in (c - 1, c + 1):
            if 0 <= pr < 8 and 0 <= pc < 8:
                if self.board[pr][pc] == (by_color, 'P'):
                    return True
        # Knights
        for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                       (1, -2), (1, 2), (2, -1), (2, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] == (by_color, 'N'):
                return True
        # King
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] == (by_color, 'K'):
                    return True
        # Sliding pieces
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                p = self.board[nr][nc]
                if p:
                    if p == (by_color, 'R') or p == (by_color, 'Q'):
                        return True
                    break
                nr += dr
                nc += dc
        for dr, dc in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                p = self.board[nr][nc]
                if p:
                    if p == (by_color, 'B') or p == (by_color, 'Q'):
                        return True
                    break
                nr += dr
                nc += dc
        return False

    def in_check(self, color: Optional[str] = None) -> bool:
        color = color or self.turn
        kr, kc = self.king_square(color)
        if kr < 0:
            return False
        return self.is_attacked(kr, kc, 'w' if color == 'b' else 'b')

    # ── legal move generation ────────────────────────────────────────────
    def pseudo_legal_moves(self, color: Optional[str] = None) -> List[Move]:
        color = color or self.turn
        moves: List[Move] = []
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if not p or p[0] != color:
                    continue
                kind = p[1]
                if kind == 'P':
                    self._pawn_moves(r, c, color, moves)
                elif kind == 'N':
                    for dr, dc in ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
                                   (1, -2), (1, 2), (2, -1), (2, 1)):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < 8 and 0 <= nc < 8:
                            t = self.board[nr][nc]
                            if t is None or t[0] != color:
                                moves.append((r, c, nr, nc, ''))
                elif kind in ('B', 'R', 'Q'):
                    dirs = []
                    if kind in ('B', 'Q'):
                        dirs += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
                    if kind in ('R', 'Q'):
                        dirs += [(-1, 0), (1, 0), (0, -1), (0, 1)]
                    for dr, dc in dirs:
                        nr, nc = r + dr, c + dc
                        while 0 <= nr < 8 and 0 <= nc < 8:
                            t = self.board[nr][nc]
                            if t is None:
                                moves.append((r, c, nr, nc, ''))
                            else:
                                if t[0] != color:
                                    moves.append((r, c, nr, nc, ''))
                                break
                            nr += dr
                            nc += dc
                elif kind == 'K':
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            if dr == 0 and dc == 0:
                                continue
                            nr, nc = r + dr, c + dc
                            if 0 <= nr < 8 and 0 <= nc < 8:
                                t = self.board[nr][nc]
                                if t is None or t[0] != color:
                                    moves.append((r, c, nr, nc, ''))
                    self._castle_moves(r, c, color, moves)
        return moves

    def _pawn_moves(self, r: int, c: int, color: str, moves: List[Move]) -> None:
        direction = -1 if color == 'w' else 1
        start_row = 6 if color == 'w' else 1
        promo_row = 0 if color == 'w' else 7
        nr = r + direction
        # forward
        if 0 <= nr < 8 and self.board[nr][c] is None:
            if nr == promo_row:
                for promo in 'QRNB':
                    moves.append((r, c, nr, c, promo))
            else:
                moves.append((r, c, nr, c, ''))
                if r == start_row and self.board[r + 2 * direction][c] is None:
                    moves.append((r, c, r + 2 * direction, c, ''))
        # captures + en passant
        for dc in (-1, 1):
            nc = c + dc
            if not (0 <= nc < 8):
                continue
            if 0 <= nr < 8:
                t = self.board[nr][nc]
                if t and t[0] != color:
                    if nr == promo_row:
                        for promo in 'QRNB':
                            moves.append((r, c, nr, nc, promo))
                    else:
                        moves.append((r, c, nr, nc, ''))
                elif t is None and self.ep == (nr, nc):
                    moves.append((r, c, nr, nc, ''))

    def _castle_moves(self, r: int, c: int, color: str, moves: List[Move]) -> None:
        if self.in_check(color):
            return
        enemy = 'b' if color == 'w' else 'w'
        row = 7 if color == 'w' else 0
        if r != row or c != 4:
            return
        # kingside
        if self.castle.get('K' if color == 'w' else 'k') and \
                self.board[row][5] is None and self.board[row][6] is None and \
                self.board[row][7] == (color, 'R') and \
                not self.is_attacked(row, 5, enemy) and \
                not self.is_attacked(row, 6, enemy):
            moves.append((r, c, row, 6, ''))
        # queenside
        if self.castle.get('Q' if color == 'w' else 'q') and \
                self.board[row][3] is None and self.board[row][2] is None and \
                self.board[row][1] is None and \
                self.board[row][0] == (color, 'R') and \
                not self.is_attacked(row, 3, enemy) and \
                not self.is_attacked(row, 2, enemy):
            moves.append((r, c, row, 2, ''))

    def legal_moves(self, color: Optional[str] = None) -> List[Move]:
        color = color or self.turn
        moves = []
        for m in self.pseudo_legal_moves(color):
            if self._is_legal(m, color):
                moves.append(m)
        return moves

    def _is_legal(self, m: Move, color: str) -> bool:
        fr, fc, tr, tc, promo = m
        captured = self.board[tr][tc]
        ep_captured = None
        if self.board[fr][fc] and self.board[fr][fc][1] == 'P' and \
                (tr, tc) == self.ep and captured is None:
            ep_captured = self.board[fr][tc]
        self.board[tr][tc] = self.board[fr][fc]
        self.board[fr][fc] = None
        if ep_captured:
            self.board[fr][tc] = None
        # castling: move the rook too
        moved = self.board[tr][tc]
        moved_rook = False
        if moved and moved[1] == 'K' and abs(tc - fc) == 2:
            row = tr
            if tc == 6:
                self.board[row][5], self.board[row][7] = self.board[row][7], None
            else:
                self.board[row][3], self.board[row][0] = self.board[row][0], None
            moved_rook = True
        in_check = self.in_check(color)
        # restore
        self.board[fr][fc] = self.board[tr][tc]
        self.board[tr][tc] = captured
        if ep_captured:
            self.board[fr][tc] = ep_captured
        if moved_rook:
            row = tr
            if tc == 6:
                self.board[row][7], self.board[row][5] = self.board[row][5], None
            else:
                self.board[row][0], self.board[row][3] = self.board[row][3], None
        return not in_check

    # ── making moves ─────────────────────────────────────────────────────
    def make_move(self, m: Move) -> bool:
        """Apply a move. Returns False if it wasn't legal."""
        fr, fc, tr, tc, promo = m
        piece = self.board[fr][fc]
        if not piece or piece[0] != self.turn:
            return False
        legal = self.legal_moves()
        if m not in legal and (not promo or (fr, fc, tr, tc, '') not in legal):
            return False
        captured = self.board[tr][tc]
        ep_captured = None
        if piece[1] == 'P' and (tr, tc) == self.ep and captured is None:
            ep_captured = self.board[fr][tc]

        entry = {
            'fr': fr, 'fc': fc, 'tr': tr, 'tc': tc, 'promo': promo,
            'piece': piece, 'captured': captured, 'ep': self.ep,
            'castle': dict(self.castle), 'halfmove': self.halfmove,
            'ep_captured': ep_captured,
            'san': self.san(m),  # computed pre-move (board still shows the piece)
        }

        # Update castle rights when king/rook moves or rook is captured.
        if piece[1] == 'K':
            if self.turn == 'w':
                self.castle['K'] = self.castle['Q'] = False
            else:
                self.castle['k'] = self.castle['q'] = False
        for r, k in ((7, 'K'), (7, 'Q')):
            if (fr, fc) == (r, 0):
                self.castle[k] = False
            if (fr, fc) == (r, 7):
                self.castle['K' if r == 7 else 'k'] = False
        if (tr, tc) == (7, 0):
            self.castle['Q'] = False
        if (tr, tc) == (7, 7):
            self.castle['K'] = False
        if (tr, tc) == (0, 0):
            self.castle['q'] = False
        if (tr, tc) == (0, 7):
            self.castle['k'] = False

        # Move the piece (with promotion).
        self.board[fr][fc] = None
        self.board[tr][tc] = (piece[0], promo or piece[1])
        if ep_captured:
            self.board[fr][tc] = None
        # Castling: move the rook.
        if piece[1] == 'K' and abs(tc - fc) == 2:
            row = tr
            if tc == 6:
                self.board[row][5] = self.board[row][7]
                self.board[row][7] = None
            else:
                self.board[row][3] = self.board[row][0]
                self.board[row][0] = None

        # En-passant target: a double pawn push sets it.
        self.ep = None
        if piece[1] == 'P' and abs(tr - fr) == 2:
            self.ep = ((fr + tr) // 2, fc)

        # Halfmove clock.
        if piece[1] == 'P' or captured or ep_captured:
            self.halfmove = 0
        else:
            self.halfmove += 1

        self.turn = 'b' if self.turn == 'w' else 'w'
        self.history.append(entry)
        self.key = self._position_key()
        self.position_counts[self.key] = self.position_counts.get(self.key, 0) + 1
        return True

    def undo(self) -> bool:
        if not self.history:
            return False
        e = self.history.pop()
        self.turn = 'b' if self.turn == 'w' else 'w'
        self.board[e['fr']][e['fc']] = e['piece']
        self.board[e['tr']][e['tc']] = e['captured']
        if e['ep_captured']:
            self.board[e['fr']][e['tc']] = e['ep_captured']
        # un-castle
        if e['piece'][1] == 'K' and abs(e['tc'] - e['fc']) == 2:
            row = e['tr']
            if e['tc'] == 6:
                self.board[row][7] = self.board[row][5]
                self.board[row][5] = None
            else:
                self.board[row][0] = self.board[row][3]
                self.board[row][3] = None
        self.ep = e['ep']
        self.castle = e['castle']
        self.halfmove = e['halfmove']
        self.key = self._position_key()
        cnt = self.position_counts.get(self.key, 1) - 1
        if cnt <= 0:
            self.position_counts.pop(self.key, None)
        else:
            self.position_counts[self.key] = cnt
        return True

    # ── game state ───────────────────────────────────────────────────────
    def result(self) -> Tuple[str, str]:
        """Return ('ongoing'|'checkmate'|'stalemate'|'draw', detail)."""
        if not self.legal_moves():
            if self.in_check():
                return 'checkmate', SIDE_NAMES[self.turn]
            return 'stalemate', 'Stalemate'
        if self.halfmove >= 100:
            return 'draw', 'Fifty-move rule'
        if self.is_repetition():
            return 'draw', 'Threefold repetition'
        if self.insufficient_material():
            return 'draw', 'Insufficient material'
        return 'ongoing', ''

    def is_repetition(self) -> bool:
        return self.position_counts.get(self.key, 0) >= 3

    def insufficient_material(self) -> bool:
        pieces = []
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p and p[1] != 'K':
                    pieces.append(p)
        if not pieces:
            return True
        if len(pieces) == 1:
            # K vs K + one MINOR piece (B or N) is a draw; K vs K + R/Q/P is
            # not (a lone rook can mate; a lone pawn can promote).
            return pieces[0][1] in ('B', 'N')
        if len(pieces) == 2:
            # K+B vs K or K+N vs K (kinds are already only B/N here since a
            # rook+minor would be > 2 distinct winners)
            kinds = [p[1] for p in pieces]
            if all(k in ('B', 'N') for k in kinds):
                return True
        # K+B vs K+B with bishops on same color
        if len(pieces) == 2 and all(p[1] == 'B' for p in pieces):
            color_bishops = [p[0] for p in pieces]
            if color_bishops[0] == color_bishops[1]:
                return True
        return False

    def material_count(self) -> int:
        total = 0
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p and p[1] != 'K':
                    total += VALUES[p[1]]
        return total

    # ── SAN-ish notation for the move list ───────────────────────────────
    def san(self, m: Move) -> str:
        fr, fc, tr, tc, promo = m
        piece = self.board[fr][fc]
        kind = piece[1]
        capture = self.board[tr][tc] is not None or \
            (kind == 'P' and (tr, tc) == self.ep)
        if kind == 'K' and abs(tc - fc) == 2:
            return 'O-O' if tc == 6 else 'O-O-O'
        base = '' if kind == 'P' else kind
        if kind == 'P' and capture:
            base = chr(ord('a') + fc)
        suffix = 'x' if capture else ''
        target = f"{chr(ord('a') + tc)}{8 - tr}"
        promo_s = f'={promo}' if promo else ''
        return f"{base}{suffix}{target}{promo_s}"


# ── AI ────────────────────────────────────────────────────────────────────

def evaluate(game: ChessGame, color: str) -> int:
    """Static evaluation from `color`'s perspective (centipawns)."""
    score = 0
    endgame = game.material_count() <= 2600
    for r in range(8):
        for c in range(8):
            p = game.board[r][c]
            if not p:
                continue
            pcolor, kind = p
            sq = board_to_sq(r, c)
            val = VALUES[kind]
            if kind == 'K':
                table = PST_KING_END if endgame else PST['K']
                psq = table[sq if pcolor == 'w' else mirror_sq(sq)]
            else:
                psq = PST[kind][sq if pcolor == 'w' else mirror_sq(sq)]
            sign = 1 if pcolor == color else -1
            score += sign * (val + psq)
    return score


def _order_moves(game: ChessGame, moves: List[Move]) -> List[Move]:
    def key(m: Move) -> int:
        _, _, tr, tc, promo = m
        target = game.board[tr][tc]
        if promo == 'Q':
            return 100000
        if target:
            v = VALUES[target[1]] * 10 - VALUES.get(game.board[m[0]][m[1]][1] if game.board[m[0]][m[1]] else '', 0)
            return 10000 + v
        return 0
    return sorted(moves, key=key, reverse=True)


def _minimax(game: ChessGame, depth: int, alpha: int, beta: int,
             maximizing: bool) -> int:
    result = game.result()
    if result[0] == 'checkmate':
        return -1000000 - depth if maximizing else 1000000 + depth
    if result[0] != 'ongoing':
        return 0
    if depth == 0:
        return evaluate(game, 'w' if maximizing else 'b')
    moves = _order_moves(game, game.legal_moves())
    if maximizing:
        best = -10 ** 9
        for m in moves:
            game.make_move(m)
            best = max(best, _minimax(game, depth - 1, alpha, beta, False))
            game.undo()
            alpha = max(alpha, best)
            if beta <= alpha:
                break
        return best
    else:
        best = 10 ** 9
        for m in moves:
            game.make_move(m)
            best = min(best, _minimax(game, depth - 1, alpha, beta, True))
            game.undo()
            beta = min(beta, best)
            if beta <= alpha:
                break
        return best


def best_move(game: ChessGame, depth: int = 2, rng: Optional[random.Random] = None) -> Optional[Move]:
    """Best move for the side to move; None when no legal moves."""
    moves = game.legal_moves()
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]
    rng = rng or random
    maximizing = game.turn == 'w'
    scored = []
    ordered = _order_moves(game, moves)
    for m in ordered:
        game.make_move(m)
        v = _minimax(game, depth - 1, -10 ** 9, 10 ** 9, not maximizing)
        game.undo()
        scored.append((v, m))
    # Stability: among equal scores, prefer a random one (less repetitive play).
    scored.sort(key=lambda x: -x[0])
    top = scored[0][0]
    bests = [m for v, m in scored if v >= top - 30]
    return rng.choice(bests)
