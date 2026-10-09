#!/usr/bin/env python3
"""Crystal Chess — a standalone desktop chess game, not a web app.

Board and pieces are rendered as faceted CRYSTAL GLASS: vertical gradient
bodies, cut-glass facet lines, specular highlights and a frosted-ice board.

Modes: Human vs Human, Human vs AI (default — you play White, AI plays
Black), AI vs AI. Full rules (castling, en passant, promotion,
check/checkmate/stalemate + draw rules) come from the pure engine.py,
which has no rendering dependency.

Controls:
  mouse            click to select / click legal target to move (or drag)
  R                new game          U    undo
  F                flip board       M    cycle mode (HvH / HvAI / AIvAI)
  H                hint (AI's move)   +/- adjust AI depth    ESC deselect

Launch flags:
  python3 crystal_chess.py               Human vs AI (basic, depth 1)
  python3 crystal_chess.py --depth 2     casual AI
  python3 crystal_chess.py --depth 4     stronger AI
  python3 crystal_chess.py --aivai       watch AI vs AI
  python3 crystal_chess.py --delay 3     AI waits 3s between moves (default)
"""

import copy
import os
import random
import threading
import sys

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame

from engine import ChessGame, best_move, SIDE_NAMES

# ── Geometry ────────────────────────────────────────────────────────────
SQUARE = 82
BOARD_PX = SQUARE * 8
BOARD_X = 28
BOARD_Y = 56
WIN_W = BOARD_X * 2 + BOARD_PX + 300
WIN_H = BOARD_Y + BOARD_PX + 40
PANEL_X = BOARD_X + BOARD_PX + 26

# ── Palette ─────────────────────────────────────────────────────────────
BG = (9, 12, 24)
FRAME_DARK = (18, 24, 46)
FRAME_LIGHT = (40, 52, 96)
TEXT = (225, 233, 250)
TEXT_DIM = (150, 162, 195)
ACCENT = (110, 210, 255)

LIGHT_SQ_TOP = (238, 248, 255)
LIGHT_SQ_BOT = (176, 206, 238)
DARK_SQ_TOP = (96, 108, 190)
DARK_SQ_BOT = (40, 48, 106)

LAST_MOVE = (255, 214, 130, 52)
SELECTED = (0, 205, 255, 70)
CHECK = (255, 70, 70, 90)
DOT = (255, 255, 255, 150)
DOT_RING = (255, 255, 255, 200)

WHITE_GEM = {'top': (255, 255, 255), 'bot': (188, 222, 248),
             'facet_dark': (120, 160, 198), 'facet_light': (255, 255, 255),
             'outline': (84, 124, 168), 'glow': (255, 255, 255)}
BLACK_GEM = {'top': (150, 118, 235), 'bot': (34, 20, 66),
             'facet_dark': (20, 10, 44), 'facet_light': (148, 120, 236),
             'outline': (52, 34, 104), 'glow': (196, 164, 255)}

# Piece silhouettes as normalized polygons (0..1 box) — faceted gem shapes.
PIECE_SHAPES = {
    'P': [  # pawn: base slab + tapered column + orb head
        [(0.30, 0.90), (0.70, 0.90), (0.72, 0.78), (0.66, 0.66), (0.60, 0.42),
         (0.52, 0.30), (0.48, 0.30), (0.40, 0.42), (0.34, 0.66), (0.28, 0.78)],
    ],
    'R': [  # rook: base + cylinder + crenellations
        [(0.24, 0.92), (0.76, 0.92), (0.78, 0.34), (0.82, 0.30), (0.82, 0.20),
         (0.72, 0.20), (0.72, 0.27), (0.62, 0.27), (0.62, 0.20), (0.52, 0.20),
         (0.52, 0.27), (0.48, 0.27), (0.48, 0.20), (0.38, 0.20), (0.38, 0.27),
         (0.28, 0.27), (0.28, 0.20), (0.18, 0.20), (0.18, 0.30), (0.22, 0.34)],
    ],
    'N': [  # knight: stylized horse head
        [(0.26, 0.94), (0.74, 0.94), (0.78, 0.80), (0.92, 0.64), (0.86, 0.52),
         (0.64, 0.46), (0.58, 0.24), (0.50, 0.34), (0.42, 0.24), (0.36, 0.46),
         (0.18, 0.52), (0.12, 0.62), (0.16, 0.74), (0.22, 0.84)],
    ],
    'B': [  # bishop: base + mitre with slit
        [(0.28, 0.92), (0.72, 0.92), (0.70, 0.74), (0.62, 0.66), (0.62, 0.44),
         (0.54, 0.30), (0.50, 0.16), (0.46, 0.30), (0.38, 0.44), (0.38, 0.66),
         (0.30, 0.74)],
    ],
    'Q': [  # queen: collared base + 5-point crown
        [(0.24, 0.92), (0.76, 0.92), (0.78, 0.72), (0.66, 0.72), (0.62, 0.52),
         (0.56, 0.34), (0.50, 0.16), (0.44, 0.34), (0.38, 0.52), (0.34, 0.72),
         (0.22, 0.72)],
    ],
    'K': [  # king: taller crown + cross
        [(0.24, 0.92), (0.76, 0.92), (0.78, 0.70), (0.66, 0.70), (0.62, 0.48),
         (0.54, 0.30), (0.50, 0.10), (0.46, 0.30), (0.38, 0.48), (0.34, 0.70),
         (0.22, 0.70)],
    ],
}
# Facet lines per piece (normalized segments) to sell the "cut glass" look.
PIECE_FACETS = {
    'P': [((0.28, 0.90), (0.34, 0.62)), ((0.72, 0.90), (0.66, 0.62)),
          ((0.40, 0.48), (0.52, 0.32))],
    'R': [((0.24, 0.86), (0.76, 0.86)), ((0.22, 0.60), (0.78, 0.60)),
          ((0.26, 0.42), (0.74, 0.42))],
    'N': [((0.26, 0.90), (0.40, 0.60)), ((0.74, 0.90), (0.60, 0.56)),
          ((0.18, 0.58), (0.50, 0.40)), ((0.82, 0.60), (0.62, 0.44))],
    'B': [((0.28, 0.88), (0.72, 0.88)), ((0.30, 0.66), (0.70, 0.66)),
          ((0.50, 0.18), (0.50, 0.78))],
    'Q': [((0.24, 0.88), (0.76, 0.88)), ((0.30, 0.64), (0.70, 0.64)),
          ((0.44, 0.36), (0.56, 0.36)), ((0.40, 0.52), (0.60, 0.52))],
    'K': [((0.24, 0.88), (0.76, 0.88)), ((0.30, 0.62), (0.70, 0.62)),
          ((0.44, 0.32), (0.56, 0.32)), ((0.50, 0.12), (0.50, 0.70))],
}


def make_piece_surface(palette: dict, kind: str, size: int) -> pygame.Surface:
    """Render one crystal piece (gradient body + facets + specular) to an
    SRCALPHA surface so it can be cached and blitted every frame."""
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pts = [(int(x * size), int(y * size)) for x, y in PIECE_SHAPES[kind][0]]

    # Gradient body: fill the polygon with a vertical gradient via
    # BLEND_RGBA_MIN over a per-row gradient surface.
    grad = pygame.Surface((size, size), pygame.SRCALPHA)
    top, bot = palette['top'], palette['bot']
    for y in range(size):
        t = y / max(1, size - 1)
        col = (int(top[0] + (bot[0] - top[0]) * t),
               int(top[1] + (bot[1] - top[1]) * t),
               int(top[2] + (bot[2] - top[2]) * t), 255)
        pygame.draw.line(grad, col, (0, y), (size, y))
    poly = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.polygon(poly, (255, 255, 255, 255), pts)
    grad.blit(poly, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(grad, (0, 0))

    # Facet lines (cut-glass bevels).
    for (x1, y1), (x2, y2) in PIECE_FACETS.get(kind, []):
        pygame.draw.line(surf, palette['facet_dark'],
                         (int(x1 * size), int(y1 * size)),
                         (int(x2 * size), int(y2 * size)), max(1, size // 60))
    # Left facet highlight (light catching the glass).
    pygame.draw.line(surf, palette['facet_light'],
                     (int(0.24 * size), int(0.9 * size)),
                     (int(0.38 * size), int(0.30 * size)), max(1, size // 70))

    # Specular highlight (small glossy orb, top-left).
    glow = pygame.Surface((size, size), pygame.SRCALPHA)
    hx, hy, hr = int(0.36 * size), int(0.28 * size), max(3, int(0.13 * size))
    for i in range(hr, 0, -1):
        a = int(120 * (1 - i / hr))
        pygame.draw.circle(glow, (*palette['glow'], a), (hx, hy), i)
    surf.blit(glow, (0, 0))

    # Outline (sharp crystal edge).
    pygame.draw.polygon(surf, palette['outline'], pts, max(1, size // 60))
    return surf


class GameUI:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption('Crystal Chess')
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 26)
        self.font_sm = pygame.font.Font(None, 21)
        self.font_title = pygame.font.Font(None, 34)

        self.game = ChessGame()
        self.flipped = False
        self.selected = None          # (r, c)
        self.legal: dict = {}          # (r, c) -> move
        self.last_move = None          # (fr, fc, tr, tc)
        self.mode = 1                 # 0 HvH, 1 HvAI, 2 AIvAI
        self.ai_depth = 1             # basic by default (--depth to raise)
        self.ai_move_delay = 3.0      # seconds the AI waits after a move
        self.ai_thinking = False
        self.pending_ai = None
        self._ai_last_move_ms = 0     # pacing clock (pygame ticks)
        self.promotion_pending = None  # (from, targets)
        self.drag = None               # (r, c, mouse offset)
        self.status_msg = ''
        self.hint = None               # suggested move
        self.time = 0.0

        self._piece_cache: dict = {}
        self._button_rects: dict = {}
        self.prepare_prompts()

    # ── helpers ──────────────────────────────────────────────────────────
    def prepare_prompts(self) -> None:
        pass

    def piece_surface(self, color: str, kind: str, size: int = None) -> pygame.Surface:
        size = size or int(SQUARE * 0.82)
        key = (color, kind, size)
        if key not in self._piece_cache:
            self._piece_cache[key] = make_piece_surface(
                WHITE_GEM if color == 'w' else BLACK_GEM, kind, size)
        return self._piece_cache[key]

    def sq_rect(self, r: int, c: int) -> pygame.Rect:
        if self.flipped:
            rr, cc = 7 - r, 7 - c
        else:
            rr, cc = r, c
        return pygame.Rect(BOARD_X + cc * SQUARE, BOARD_Y + rr * SQUARE,
                           SQUARE, SQUARE)

    def board_sq_from_pixel(self, x: int, y: int):
        if not (BOARD_X <= x < BOARD_X + BOARD_PX and BOARD_Y <= y < BOARD_Y + BOARD_PX):
            return None
        cc = (x - BOARD_X) // SQUARE
        rr = (y - BOARD_Y) // SQUARE
        r, c = rr, cc
        if self.flipped:
            r, c = 7 - rr, 7 - cc
        if 0 <= r < 8 and 0 <= c < 8:
            return (r, c)
        return None

    def mode_label(self) -> str:
        return ['Human vs Human', 'Human vs AI', 'AI vs AI'][self.mode]

    # ── rendering ────────────────────────────────────────────────────────
    def draw_gradient_rect(self, rect: pygame.Rect, top, bot) -> None:
        for y in range(rect.top, rect.bottom):
            t = (y - rect.top) / max(1, rect.height - 1)
            col = (int(top[0] + (bot[0] - top[0]) * t),
                   int(top[1] + (bot[1] - top[1]) * t),
                   int(top[2] + (bot[2] - top[2]) * t))
            pygame.draw.line(self.screen, col, (rect.left, y), (rect.right - 1, y))

    def draw_board(self) -> None:
        # frame
        frame = pygame.Rect(BOARD_X - 10, BOARD_Y - 10, BOARD_PX + 20, BOARD_PX + 20)
        self.draw_gradient_rect(frame, FRAME_LIGHT, FRAME_DARK)
        pygame.draw.rect(self.screen, (8, 10, 20), frame, 2, border_radius=8)
        # squares (frosted glass)
        for r in range(8):
            for c in range(8):
                rect = self.sq_rect(r, c)
                if (r + c) % 2 == 0:
                    self.draw_gradient_rect(rect, LIGHT_SQ_TOP, LIGHT_SQ_BOT)
                else:
                    self.draw_gradient_rect(rect, DARK_SQ_TOP, DARK_SQ_BOT)
                # frosted inner sheen
                pygame.draw.rect(self.screen, (255, 255, 255, 0), rect, 1)
        # coordinates
        for i in range(8):
            r, c = (0, i) if not self.flipped else (7, i)
            label = chr(ord('a') + (i if not self.flipped else 7 - i))
            file_rect = self.sq_rect(0, i)
            rank_rect = self.sq_rect(i, 0)
            col = (30, 38, 80)
            if (0 + (i if not self.flipped else 7 - i)) % 2 == 1:
                col = (215, 232, 250)
            self.screen.blit(self.font_sm.render(label, True, col),
                             (file_rect.left + 4, file_rect.bottom - 18))
            self.screen.blit(self.font_sm.render(str(8 - r), True, col),
                             (rank_rect.right - 16, rank_rect.top + 2))

    def overlay_square(self, r: int, c: int, color) -> None:
        rect = self.sq_rect(r, c)
        ov = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
        ov.fill(color)
        self.screen.blit(ov, rect.topleft)

    def draw_pieces(self, mouse_pos=None) -> None:
        for r in range(8):
            for c in range(8):
                p = self.game.board[r][c]
                if not p:
                    continue
                if self.drag and self.drag[0] == (r, c):
                    continue  # drawn under the cursor below
                self.blit_piece(r, c, p)
        if self.drag and self.drag[0]:
            p = self.game.board[self.drag[0][0]][self.drag[0][1]]
            if p:
                x, y = mouse_pos
                surf = self.piece_surface(p[0], p[1])
                self.screen.blit(surf, (x - surf.get_width() // 2,
                                        y - surf.get_height() // 2))

    def blit_piece(self, r: int, c: int, p, size=None) -> None:
        rect = self.sq_rect(r, c)
        surf = self.piece_surface(p[0], p[1], size)
        self.screen.blit(surf, (rect.centerx - surf.get_width() // 2,
                                rect.centery - surf.get_height() // 2))

    def draw_panel(self) -> None:
        x = PANEL_X
        title = self.font_title.render('CRYSTAL CHESS', True, ACCENT)
        self.screen.blit(title, (x, 14))
        sub = self.font_sm.render('standalone · crystal glass', True, TEXT_DIM)
        self.screen.blit(sub, (x + 2, 48))

        # status
        status, detail = self.game.result()
        if status == 'checkmate':
            txt = f'Checkmate — {detail} wins'
        elif status == 'stalemate':
            txt = 'Stalemate — draw'
        elif status == 'draw':
            txt = f'Draw ({detail})'
        else:
            txt = f"{SIDE_NAMES[self.game.turn]} to move"
            if self.game.in_check():
                txt += ' — CHECK'
        col = (255, 120, 120) if status in ('checkmate',) or (self.game.in_check() and status == 'ongoing') else TEXT
        self.screen.blit(self.font.render(txt, True, col), (x, 84))
        if self.status_msg:
            self.screen.blit(self.font_sm.render(self.status_msg, True, TEXT_DIM), (x, 112))
        self.screen.blit(self.font_sm.render(f'Mode: {self.mode_label()}  (M)', True, TEXT_DIM), (x, 140))
        self.screen.blit(self.font_sm.render(f'AI depth: {self.ai_depth}  (+/-)', True, TEXT_DIM), (x, 164))
        self.screen.blit(self.font_sm.render(f'AI thinking…', True, ACCENT) if self.ai_thinking
                         else self.font_sm.render('', True, TEXT_DIM), (x, 186))

        # captured trays
        self.draw_captured(x, 210)

        # buttons
        self._button_rects = {}
        y = 470
        for label, key in (('New game  (R)', 'new'), ('Undo  (U)', 'undo'),
                           ('Flip board  (F)', 'flip'), ('Hint  (H)', 'hint')):
            rect = pygame.Rect(x, y, 268, 34)
            self.draw_gradient_rect(rect, (44, 58, 104), (30, 40, 76))
            pygame.draw.rect(self.screen, (70, 92, 150), rect, 1, border_radius=6)
            self.screen.blit(self.font_sm.render(label, True, TEXT),
                             (rect.left + 10, rect.top + 7))
            self._button_rects[key] = rect
            y += 42

        # move list
        mlist = pygame.Rect(x, y + 6, 268, WIN_H - y - 46)
        pygame.draw.rect(self.screen, (12, 16, 32), mlist, border_radius=6)
        pygame.draw.rect(self.screen, (34, 44, 82), mlist, 1, border_radius=6)
        head = self.font_sm.render('MOVES', True, TEXT_DIM)
        self.screen.blit(head, (mlist.left + 8, mlist.top + 6))
        rows = [f'{i}. {e["san"]}' for i, e in enumerate(self.game.history, 1)]
        vis = rows[-14:]
        start_y = mlist.top + 30
        for idx, row in enumerate(vis):
            col = TEXT if idx == len(vis) - 1 else TEXT_DIM
            self.screen.blit(self.font_sm.render(row, True, col),
                             (mlist.left + 12, start_y + idx * 20))

    def draw_captured(self, x: int, y: int) -> None:
        whites = [p[1] for p in self.captured_for('b')]
        blacks = [p[1] for p in self.captured_for('w')]
        label = self.font_sm.render('Captured', True, TEXT_DIM)
        self.screen.blit(label, (x, y))
        for i, kind in enumerate(whites[:8]):
            surf = self.piece_surface('w', kind, 26)
            self.screen.blit(surf, (x + i * 28, y + 20))
        for i, kind in enumerate(blacks[:8]):
            surf = self.piece_surface('b', kind, 26)
            self.screen.blit(surf, (x + 10 + i * 28, y + 48))

    def captured_for(self, color: str):
        out = []
        for e in self.game.history:
            if e['captured'] and e['captured'][0] == color:
                out.append(e['captured'])
        return out

    def draw(self, mouse_pos=None) -> None:
        self.screen.fill(BG)
        self.draw_board()
        # overlays
        if self.last_move:
            fr, fc, tr, tc = self.last_move
            self.overlay_square(fr, fc, LAST_MOVE)
            self.overlay_square(tr, tc, LAST_MOVE)
        if self.selected:
            self.overlay_square(*self.selected, SELECTED)
        for (r, c) in self.legal:
            if self.game.board[r][c]:
                rect = self.sq_rect(r, c)
                pygame.draw.circle(self.screen, DOT_RING, rect.center, 16, 3)
            else:
                rect = self.sq_rect(r, c)
                pygame.draw.circle(self.screen, DOT, rect.center, 7)
        if self.game.in_check():
            kr, kc = self.game.king_square(self.game.turn)
            if kr >= 0:
                pulse = 60 + int(50 * (0.5 + 0.5 * ((self.time * 3) % 1)))
                self.overlay_square(kr, kc, (*CHECK[:3], min(120, pulse)))
        if self.hint:
            fr, fc, tr, tc, _ = self.hint
            rect = self.sq_rect(tr, tc)
            pygame.draw.circle(self.screen, (110, 210, 255), rect.center, 18, 3)
        self.draw_pieces(mouse_pos)
        self.draw_panel()
        if self.promotion_pending:
            self.draw_promotion()
        pygame.display.flip()

    def draw_promotion(self) -> None:
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((5, 7, 16, 190))
        self.screen.blit(overlay, (0, 0))
        msg = self.font.render('Promote to:', True, TEXT)
        self.screen.blit(msg, (WIN_W // 2 - 70, WIN_H // 2 - 90))
        _, targets = self.promotion_pending
        color = self.game.turn
        for i, kind in enumerate('QRNB'):
            rect = pygame.Rect(WIN_W // 2 - 170 + i * 90, WIN_H // 2 - 40, 80, 80)
            pygame.draw.rect(self.screen, (30, 40, 76), rect, border_radius=8)
            pygame.draw.rect(self.screen, ACCENT, rect, 2, border_radius=8)
            surf = self.piece_surface(color, kind)
            self.screen.blit(surf, (rect.centerx - surf.get_width() // 2,
                                    rect.centery - surf.get_height() // 2))
            self._promo_rects = getattr(self, '_promo_rects', {})
            self._promo_rects[kind] = rect
        pygame.display.flip()

    # ── interaction ──────────────────────────────────────────────────────
    def select(self, sq) -> None:
        r, c = sq
        p = self.game.board[r][c]
        if p and p[0] == self.game.turn:
            self.selected = (r, c)
            self.legal = {(m[2], m[3]): m for m in self.game.legal_moves()
                          if m[0] == r and m[1] == c}
        else:
            self.selected = None
            self.legal = {}

    def try_move(self, m) -> bool:
        fr, fc, tr, tc, promo = m
        # Promotion requires a picker when a pawn reaches the last rank.
        need_promo = self.game.board[fr][fc] and \
            self.game.board[fr][fc][1] == 'P' and (tr == 0 or tr == 7)
        if need_promo and not promo:
            legal_promos = [x for x in 'QRNB'
                            if self.game._is_legal((fr, fc, tr, tc, x), self.game.turn)]
            if legal_promos:
                self.promotion_pending = ((fr, fc, tr, tc), legal_promos)
                return True
        if self.game.make_move(m):
            self.after_move(fr, fc, tr, tc)
            return True
        return False

    def after_move(self, fr, fc, tr, tc) -> None:
        self.last_move = (fr, fc, tr, tc)
        self.selected = None
        self.legal = {}
        self.hint = None
        self.status_msg = ''
        self._ai_last_move_ms = pygame.time.get_ticks()
        self.dump_state()

    def dump_state(self) -> None:
        """Write exact game state to a JSON file (used by external
        monitors/tests to read move count, result and material without
        touching the running process)."""
        try:
            import json as _json
            status, detail = self.game.result()
            with open('/tmp/crystal-chess-state.json', 'w') as f:
                _json.dump({
                    'ply': len(self.game.history),
                    'moves': [e.get('san') for e in self.game.history],
                    'result': status,
                    'detail': detail,
                    'turn': self.game.turn,
                    'material_diff': self.game.material_count(),
                }, f)
        except Exception:
            pass  # monitoring is best-effort; never break gameplay

    def apply_pending_ai(self) -> None:
        if self.pending_ai is not None:
            m = self.pending_ai
            self.pending_ai = None
            self.ai_thinking = False
            if m:
                self.try_move(m)

    def maybe_ai(self) -> None:
        """Start AI thinking when it is the AI's turn.

        Mode 0 (HvH): never. Mode 1 (HvAI): the AI plays black while the
        human is white. Mode 2 (AIvAI): the AI plays both sides.
        """
        status = self.game.result()[0]
        if status != 'ongoing' or self.ai_thinking or self.promotion_pending:
            return
        if self.mode == 0:
            return
        if self.mode == 1 and self.game.turn != 'b':
            return
        # Pacing: the AI waits ai_move_delay seconds after the last move
        # (either side) before starting to think, so games feel human.
        if self.ai_move_delay > 0:
            if (pygame.time.get_ticks() - self._ai_last_move_ms) < \
                    self.ai_move_delay * 1000:
                return
        self.ai_thinking = True
        depth = self.ai_depth

        def think():
            # Work on a private copy — the main thread may mutate self.game
            # (AIvAI applies the opponent's move while this search runs).
            m = best_move(copy.deepcopy(self.game), depth)
            self.pending_ai = m
            self.ai_thinking = False

        threading.Thread(target=think, daemon=True).start()

    def new_game(self) -> None:
        self.game = ChessGame()
        self.selected = None
        self.legal = {}
        self.last_move = None
        self.hint = None
        self.status_msg = ''
        self.promotion_pending = None
        self._ai_last_move_ms = 0     # fresh 3s pacing on every new game

    def undo(self) -> None:
        if self.promotion_pending:
            self.promotion_pending = None
            return
        self.game.undo()
        if self.mode == 2 and self.pending_ai is None and not self.ai_thinking:
            # AIvAI: only pair-undo when both plies are already on the board
            # (an in-flight AI move hasn't been applied yet — don't eat a
            # move that doesn't exist).
            self.game.undo()
        self.selected = None
        self.legal = {}
        self.hint = None

    # ── main loop ────────────────────────────────────────────────────────
    def run(self) -> None:
        self.maybe_ai()
        while True:
            self.time = pygame.time.get_ticks() / 1000.0
            for event in pygame.event.get():
                self.handle(event)
            self.apply_pending_ai()
            self.maybe_ai()
            self.draw(pygame.mouse.get_pos())
            self.clock.tick(60)

    def handle(self, event) -> None:
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit(0)
        if self.promotion_pending:
            self.handle_promotion(event)
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self.new_game()
            elif event.key == pygame.K_u:
                self.undo()
            elif event.key == pygame.K_f:
                self.flipped = not self.flipped
            elif event.key == pygame.K_m:
                self.mode = (self.mode + 1) % 3
                self.new_game()
            elif event.key == pygame.K_h:
                if self.game.result()[0] == 'ongoing':
                    self.hint = best_move(self.game, self.ai_depth)
            elif event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                self.ai_depth = min(4, self.ai_depth + 1)
            elif event.key == pygame.K_MINUS:
                self.ai_depth = max(1, self.ai_depth - 1)
            elif event.key == pygame.K_ESCAPE:
                self.selected = None
                self.legal = {}
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            sq = self.board_sq_from_pixel(*event.pos)
            if sq:
                if sq in self.legal:
                    self.try_move(self.legal[sq])
                else:
                    self.select(sq)
                    if self.selected:
                        self.drag = (self.selected, event.pos)
            else:
                self.selected = None
                self.legal = {}
            for key, rect in self._button_rects.items():
                if rect.collidepoint(event.pos):
                    {'new': self.new_game, 'undo': self.undo,
                     'flip': lambda: setattr(self, 'flipped', not self.flipped),
                     'hint': lambda: setattr(self, 'hint',
                                             best_move(self.game, self.ai_depth)
                                             if self.game.result()[0] == 'ongoing' else None)}[key]()
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drag:
                sq = self.board_sq_from_pixel(*event.pos)
                if sq and sq in self.legal:
                    self.try_move(self.legal[sq])
                self.drag = None

    def handle_promotion(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                self.choose_promo('Q')
            elif event.key == pygame.K_r:
                self.choose_promo('R')
            elif event.key == pygame.K_b:
                self.choose_promo('B')
            elif event.key == pygame.K_n:
                self.choose_promo('N')
            elif event.key == pygame.K_ESCAPE:
                self.promotion_pending = None
        elif event.type == pygame.MOUSEBUTTONDOWN:
            for kind, rect in getattr(self, '_promo_rects', {}).items():
                if rect.collidepoint(event.pos):
                    self.choose_promo(kind)

    def choose_promo(self, kind: str) -> None:
        if not self.promotion_pending:
            return
        (fr, fc, tr, tc), _ = self.promotion_pending
        self.promotion_pending = None
        if self.game.make_move((fr, fc, tr, tc, kind)):
            self.after_move(fr, fc, tr, tc)


if __name__ == '__main__':
    ui = GameUI()
    # Launch flags:
    #   --aivai      start in AI-vs-AI mode (default: Human vs AI)
    #   --depth N    AI strength 1-4 (1 = basic, 4 = strongest)
    #   --delay S    seconds the AI waits between moves (default 3.0)
    args = [a for a in sys.argv[1:]]
    if '--aivai' in args:
        ui.mode = 2
    if '--depth' in args:
        try:
            ui.ai_depth = max(1, min(4, int(args[args.index('--depth') + 1])))
        except (ValueError, IndexError):
            pass
    if '--delay' in args:
        try:
            ui.ai_move_delay = max(0.0, float(args[args.index('--delay') + 1]))
        except (ValueError, IndexError):
            pass
    ui.run()
