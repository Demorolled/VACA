#!/usr/bin/env python3
"""Crystal Chess 3D — scene assembly + main loop for the 3D rebuild.

Uses engine.py (rules + AI), engine3d.py (3D pipeline) and models3d.py (meshes).
Engine board a8=(0,0) -> world (0,0). Pieces sit on y=0 via square_center.

Controls mirror the 2D version: R new game, U undo, F flip, M cycle mode,
H hint, +/- depth, ESC deselect, click/drag, right-drag orbit, scroll zoom.
"""

import copy
import math
import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame

from engine import ChessGame, best_move, SIDE_NAMES

# Jarvis voice: announce moves aloud using Jarvis's own TTS (best-effort —
# if the helper can't load or TTS is disabled, the game runs silently).
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import jarvis_voice as _voice
except Exception:
    _voice = None
from engine3d import Camera, Vec3, render
from models3d import (
    SQ, square_center, world_to_square,
    build_board, build_piece, build_highlight,
)

WIN_W, WIN_H = 1100, 800
BG = (9, 12, 24)
TEXT = (225, 233, 250)
TEXT_DIM = (150, 162, 195)
ACCENT = (110, 210, 255)
FRAME = (40, 52, 96)

ANIM_MS = 250
LIFT_H = 0.6
CAPTURE_FADE_MS = 200


class Anim:
    def __init__(self, start, end, piece_mesh, captured_mesh=None):
        self.start = start  # Vec3
        self.end = end
        self.piece_mesh = piece_mesh
        self.captured_mesh = captured_mesh
        self.captured_pos = None
        self.t0 = time.time() * 1000
        self.done = False

    def progress(self) -> float:
        return min(1.0, (time.time()*1000 - self.t0) / ANIM_MS)

    def pos(self) -> Vec3:
        p = self.progress()
        # ease in-out
        e = p * p * (3 - 2*p)
        base = Vec3(
            self.start.x + (self.end.x - self.start.x) * e,
            0,
            self.start.z + (self.end.z - self.start.z) * e,
        )
        # lift arc: quadratic bezier height
        h = 4 * LIFT_H * p * (1 - p)
        base.y = h
        return base

    def is_done(self) -> bool:
        return self.progress() >= 1.0


class GameUI3D:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption('Crystal Chess 3D')
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 26)
        self.font_sm = pygame.font.Font(None, 21)
        self.font_title = pygame.font.Font(None, 34)

        self.game = ChessGame()
        self.flipped = False
        self.selected = None
        self.legal = {}  # (r,c) -> move
        self.last_move = None
        self.mode = 1  # 0 HvH, 1 HvAI, 2 AIvAI
        self.ai_depth = 2
        self.ai_move_delay = 1.2
        self.ai_thinking = False
        self.pending_ai = None
        self._ai_last_move_ms = 0
        self.promotion_pending = None  # ((fr,fc,tr,tc), [promos])
        self.hint = None
        self.captured_white = []
        self.captured_black = []
        self.status_msg = ""

        # 3D
        self.camera = Camera(yaw=0, pitch=0.6, dist=13.5, w=WIN_W, h=WIN_H)
        self.board_mesh = build_board()
        # cache piece meshes per type/side
        self.piece_meshes = {}
        for side in ("w", "b"):
            for piece in "KQRNBP":
                self.piece_meshes[(side, piece)] = build_piece(piece, side)
        # highlights
        self.hl_dot = build_highlight("dot")
        self.hl_ring = build_highlight("ring")
        self.hl_select = build_highlight("select")
        self.hl_last = build_highlight("last")
        self.hl_check = build_highlight("check")

        self.anim: Anim | None = None
        self._captured_anim = None  # for fade
        self.drag_orbit = False
        self.last_mouse = (0, 0)

    def captured_for(self, color):
        out = []
        for e in self.game.history:
            if e['captured'] and e['captured'][0] == color:
                out.append(e['captured'])
            if e.get('ep_captured') and e['ep_captured'][0] == color:
                out.append(e['ep_captured'])
        return out

    def mode_label(self):
        return ['Human vs Human', 'Human vs AI', 'AI vs AI'][self.mode]

    def is_ai_turn(self):
        if self.mode == 0:
            return False
        if self.mode == 1:
            return self.game.turn == 'b'
        return True  # AIvAI both

    def select(self, sq):
        r, c = sq
        p = self.game.board[r][c]
        if p and p[0] == self.game.turn:
            self.selected = (r, c)
            self.legal = {(m[2], m[3]): m for m in self.game.legal_moves() if m[0] == r and m[1] == c}
        else:
            self.selected = None
            self.legal = {}

    def try_move(self, move) -> bool:
        fr, fc, tr, tc, promo = move
        piece = self.game.board[fr][fc]
        need_promo = piece and piece[1] == 'P' and (tr == 0 or tr == 7)
        if need_promo and not promo:
            # auto-queen for 3D (no popup complexity in headless; still show banner)
            # Collect legal promos; if any, use Q
            legal_promos = [x for x in 'QRNB' if self.game._is_legal((fr, fc, tr, tc, x), self.game.turn)]
            if legal_promos:
                promo = 'Q'
                move = (fr, fc, tr, tc, promo)
        # capture info before make
        captured = self.game.board[tr][tc]
        ep_capt = self.game.board[fr][tc] if piece and piece[1] == 'P' and (tr, tc) == self.game.ep and captured is None else None
        is_castle = piece and piece[1] == 'K' and abs(tc - fc) == 2
        # Determine rook move for castling animation
        rook_move = None
        if is_castle:
            row = tr
            if tc == 6:
                rook_move = (row, 7, row, 5, '')
            else:
                rook_move = (row, 0, row, 3, '')
        if not self.game.make_move(move):
            return False
        self.announce_move()
        # Start animation
        start = square_center(fr, fc)
        end = square_center(tr, tc)
        mesh = self.piece_meshes.get((piece[0], promo or piece[1]), self.piece_meshes[(piece[0], piece[1])])
        self.anim = Anim(start, end, mesh)
        # Handle capture fade: store captured piece for sinking
        if captured:
            # will be drawn sinking at target square
            self._captured_anim = {"piece": captured, "pos": end, "t0": time.time()*1000}
        elif ep_capt:
            self._captured_anim = {"piece": ep_capt, "pos": square_center(fr, tc), "t0": time.time()*1000}
        else:
            self._captured_anim = None
        # For castling, animate rook separately after main anim? Simplify: move rook instantly after anim done
        self._pending_rook = rook_move
        self.last_move = (fr, fc, tr, tc)
        self.selected = None
        self.legal = {}
        self.hint = None
        self._ai_last_move_ms = pygame.time.get_ticks()
        self.dump_state()
        return True

    def announce_move(self):
        """Have Jarvis voice the move that was just played (best-effort)."""
        if _voice is None or not _voice.enabled():
            return
        try:
            mover = 'w' if self.game.turn == 'b' else 'b'   # mover = side to move next
            san = self.game.history[-1].get('san', '') if self.game.history else ''
            if san:
                _voice.say_move(SIDE_NAMES[mover], san)
        except Exception:
            pass  # voice is best-effort; never break gameplay

    def after_anim(self):
        self.anim = None
        self._captured_anim = None
        # If castling rook pending, we already moved board; nothing to animate rook separately for now
        self._pending_rook = None

    def dump_state(self):
        try:
            import json as _json
            status, detail = self.game.result()
            with open('/tmp/crystal-chess-state.json', 'w') as f:
                _json.dump({'ply': len(self.game.history), 'moves': [e.get('san') for e in self.game.history], 'result': status, 'detail': detail, 'turn': self.game.turn}, f)
        except Exception:
            pass

    def maybe_ai(self):
        if self.anim or self.promotion_pending:
            return
        status = self.game.result()[0]
        if status != 'ongoing' or self.ai_thinking:
            return
        if not self.is_ai_turn():
            return
        if (pygame.time.get_ticks() - self._ai_last_move_ms) < self.ai_move_delay * 1000:
            return
        self.ai_thinking = True
        depth = self.ai_depth
        def think():
            m = best_move(copy.deepcopy(self.game), depth)
            self.pending_ai = m
            self.ai_thinking = False
        threading.Thread(target=think, daemon=True).start()

    def apply_pending_ai(self):
        if self.pending_ai is not None:
            m = self.pending_ai
            self.pending_ai = None
            self.ai_thinking = False
            if m:
                self.try_move(m)

    def new_game(self):
        self.game = ChessGame()
        self.selected = None
        self.legal = {}
        self.last_move = None
        self.hint = None
        self.promotion_pending = None
        self.anim = None
        self._captured_anim = None
        self._ai_last_move_ms = 0
        if _voice is not None:
            try:
                _voice.speak('New game. White to move.')
            except Exception:
                pass

    def undo(self):
        if self.promotion_pending:
            self.promotion_pending = None
            return
        if self.anim:
            return
        self.game.undo()
        if self.mode == 2 and self.pending_ai is None and not self.ai_thinking:
            self.game.undo()
        self.selected = None
        self.legal = {}
        self.hint = None

    def draw(self):
        self.screen.fill(BG)
        # Build render list: board, highlights, pieces
        entries = []
        # board at 0,0,0
        entries.append((self.board_mesh, Vec3(0, 0, 0)))
        # highlights
        if self.last_move:
            fr, fc, tr, tc = self.last_move
            entries.append((self.hl_last, Vec3(fc + 0.5, 0, tr + 0.5) - Vec3(0.5, 0, 0.5) + Vec3(0,0,0)))  # placeholder, will map via square_center
            # Actually highlights are at y~0.015 local (0.5,0.5) square; we need to place at square centers
            # Simpler: use square_center for highlights too (they are centered at 0.5,0.5 local)
        # Rebuild entries with correct highlight placement
        entries = []
        entries.append((self.board_mesh, Vec3(0, 0, 0)))
        # last move squares
        if self.last_move:
            fr, fc, tr, tc = self.last_move
            entries.append((self.hl_last, square_center(fr, fc)))
            entries.append((self.hl_last, square_center(tr, tc)))
        # selected
        if self.selected:
            entries.append((self.hl_select, square_center(*self.selected)))
        # legal dots/rings
        for (r, c), mv in self.legal.items():
            target_piece = self.game.board[r][c]
            hl = self.hl_ring if target_piece else self.hl_dot
            entries.append((hl, square_center(r, c)))
        # check
        if self.game.in_check():
            kr, kc = self.game.king_square(self.game.turn)
            if kr >= 0:
                entries.append((self.hl_check, square_center(kr, kc)))
        # hint
        if self.hint:
            fr, fc, tr, tc, _ = self.hint
            entries.append((self.hl_ring, square_center(tr, tc)))
        # pieces
        # If animating, skip moving piece at source, draw it at anim pos, and optionally sinking captured
        anim_src = None
        if self.anim:
            # Find move that matches anim start/end roughly
            pass
        for r in range(8):
            for c in range(8):
                p = self.game.board[r][c]
                if not p:
                    continue
                # Don't draw moving piece at source during anim (it will be drawn via anim)
                if self.anim and r == self._anim_from()[0] and c == self._anim_from()[1] and self.anim and not self.anim.is_done():
                    # The source square now empty after make_move, so this won't trigger; handled via anim mesh
                    continue
                # Draw piece at square_center
                # But if this is the destination of animating piece, skip until anim done (anim draws it)
                if self.anim and not self.anim.is_done():
                    dst = self._anim_to()
                    if dst and r == dst[0] and c == dst[1]:
                        continue
                # captured sinking piece is separate
                entries.append((self.piece_meshes[p], square_center(r, c)))
        # anim piece
        if self.anim:
            if self.anim.is_done():
                self.after_anim()
            else:
                pos = self.anim.pos()
                entries.append((self.anim.piece_mesh, pos))
                # sinking captured
                if self._captured_anim:
                    age = time.time()*1000 - self._captured_anim["t0"]
                    if age < CAPTURE_FADE_MS:
                        # scale by shrinking? Just sink slightly
                        t = age / CAPTURE_FADE_MS
                        sink = Vec3(0, -t*0.3, 0)
                        # Use same captured mesh but slightly transparent via darker shade? Keep simple: lower y
                        cap_piece, cap_side = self._captured_anim["piece"][1], self._captured_anim["piece"][0]
                        mesh = self.piece_meshes[(cap_side, cap_piece)]
                        entries.append((mesh, self._captured_anim["pos"] + sink))

        render(self.screen, self.camera, entries)

        # HUD (2D overlay)
        title = self.font_title.render('CRYSTAL CHESS 3D', True, ACCENT)
        self.screen.blit(title, (14, 14))
        sub = self.font_sm.render(f'{self.mode_label()}  turn {SIDE_NAMES[self.game.turn]}', True, TEXT_DIM)
        self.screen.blit(sub, (14, 48))
        # last SAN
        if self.game.history:
            last_san = self.game.history[-1].get('san', '')
            self.screen.blit(self.font.render(f'Last: {last_san}', True, TEXT), (14, 72))
        if self.ai_thinking:
            self.screen.blit(self.font_sm.render('thinking…', True, ACCENT), (14, 100))
        # captured counts
        whites = len(self.captured_for('b'))
        blacks = len(self.captured_for('w'))
        self.screen.blit(self.font_sm.render(f'Captured W:{whites} B:{blacks}', True, TEXT_DIM), (14, 124))
        # result banner
        status, detail = self.game.result()
        if status != 'ongoing':
            banner = f'{status.upper()}: {detail}' if detail else status.upper()
            col = (255, 120, 120) if status == 'checkmate' else TEXT
            self.screen.blit(self.font.render(banner, True, col), (14, 150))
        # controls hint
        hint = self.font_sm.render('R new  U undo  F flip  M mode  H hint  +/- depth  ESC  drag-rotate scroll-zoom', True, TEXT_DIM)
        self.screen.blit(hint, (14, WIN_H - 24))
        # status msg
        if self.status_msg:
            self.screen.blit(self.font_sm.render(self.status_msg, True, TEXT_DIM), (14, WIN_H - 48))
        pygame.display.flip()

    def _anim_from(self):
        if self.anim and self.last_move:
            return (self.last_move[0], self.last_move[1])
        return (-1, -1)

    def _anim_to(self):
        if self.anim and self.last_move:
            return (self.last_move[2], self.last_move[3])
        return None

    def handle(self, event):
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit(0)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self.new_game()
            elif event.key == pygame.K_u:
                self.undo()
            elif event.key == pygame.K_f:
                self.camera.orbit(math.pi, 0)
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
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # left click: pick square
                if self.anim or self.promotion_pending:
                    return
                res = self.camera.ray_plane(event.pos[0], event.pos[1])
                if res:
                    sq = world_to_square(res[0], res[1])
                    if sq:
                        if sq in self.legal:
                            self.try_move(self.legal[sq])
                        else:
                            self.select(sq)
                            if not self.legal:
                                self.selected = None
                else:
                    self.selected = None
                    self.legal = {}
            elif event.button in (2, 3):
                self.drag_orbit = True
                self.last_mouse = event.pos
            elif event.button == 4:
                self.camera.zoom(-0.7)
            elif event.button == 5:
                self.camera.zoom(0.7)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button in (2, 3):
                self.drag_orbit = False
        elif event.type == pygame.MOUSEMOTION:
            if self.drag_orbit:
                dx = event.pos[0] - self.last_mouse[0]
                dy = event.pos[1] - self.last_mouse[1]
                self.camera.orbit(dx * 0.01, dy * 0.01)
                self.last_mouse = event.pos

    def run(self):
        # smoke flag
        if "--smoke" in sys.argv:
            # headless smoke: init one frame, make one legal move, undo
            self.draw()
            pygame.display.flip()
            moves = self.game.legal_moves()
            if moves:
                self.try_move(moves[0])
                # pump a few anim frames
                for _ in range(5):
                    self.draw()
                    pygame.display.flip()
                    pygame.time.wait(50)
                self.undo()
            print("smoke ok")
            return
        self._ai_last_move_ms = pygame.time.get_ticks()
        while True:
            for event in pygame.event.get():
                self.handle(event)
            self.apply_pending_ai()
            self.maybe_ai()
            self.draw()
            self.clock.tick(60)


if __name__ == '__main__':
    # Allow --depth, --delay, --aivai like crystal_chess.py for compat
    ui = GameUI3D()
    args = [a for a in sys.argv[1:]]
    if '--aivai' in args:
        ui.mode = 2
    if '--depth' in args:
        try:
            ui.ai_depth = max(1, min(4, int(args[args.index('--depth')+1])))
        except (ValueError, IndexError):
            pass
    if '--delay' in args:
        try:
            ui.ai_move_delay = max(0.0, float(args[args.index('--delay')+1]))
        except (ValueError, IndexError):
            pass
    ui.run()
