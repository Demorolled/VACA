#!/usr/bin/env python3
"""Headless smoke test for the pygame UI (no display needed).

Boots GameUI with SDL's dummy video driver, renders a frame, plays an
AI-vs-AI game through the normal UI move path, and saves a screenshot PNG
proving the crystal rendering pipeline works end to end.

Run:  SDL_VIDEODRIVER=dummy python3 smoke_ui.py
"""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame  # noqa: E402
import crystal_chess  # noqa: E402


def main() -> int:
    ui = crystal_chess.GameUI()
    ui.mode = 2  # AI vs AI
    ui.ai_depth = 1  # fast for the smoke test
    ui.ai_move_delay = 0  # no pacing — smoke test drives frames directly

    # Render the opening position.
    ui.draw()
    ui._frame_count = 0
    for _ in range(240):  # ~4s of frames, letting the AI thread run
        ui.apply_pending_ai()
        ui.maybe_ai()
        ui.draw()
        ui._frame_count = getattr(ui, '_frame_count', 0) + 1
        if ui.game.result()[0] != 'ongoing':
            break

    status = ui.game.result()
    print('frame_count:', getattr(ui, '_frame_count', 0))
    print('moves played:', len(ui.game.history))
    print('result:', status[0], '|', status[1])
    print('white king:', ui.game.king_square('w'), 'black king:', ui.game.king_square('b'))

    # Screenshot proof.
    os.makedirs('shots', exist_ok=True)
    pygame.image.save(ui.screen, 'shots/smoke.png')
    size = os.path.getsize('shots/smoke.png')
    print('screenshot: shots/smoke.png (%d bytes, %dx%d)' % (size, ui.screen.get_width(), ui.screen.get_height()))

    assert size > 20000, 'screenshot suspiciously small — rendering may be broken'
    pygame.quit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
