# Crystal Chess ♟️💎

A **standalone desktop chess game** — no browser, no web stack. Built with
Python + pygame, with the board and pieces rendered as *faceted crystal glass*:
vertical gradient bodies, cut-glass facet lines, specular highlights and a
frosted-ice board.

## Quick start

```bash
pip install pygame          # if not already installed
python3 crystal_chess.py            # Human vs AI (you are White)
```

Requires Python 3.9+ (tested on 3.13 with pygame 2.6.1).

## Launch flags

| Flag | Effect |
|------|--------|
| *(none)* | Human vs AI — you play White, AI plays Black |
| `--depth N` | AI strength 1–4 (`1` = basic, `4` = strongest) |
| `--aivai` | Start in AI-vs-AI mode (watch them play) |
| `--delay S` | AI waits `S` seconds between moves (default `3`) |

Example: `python3 crystal_chess.py --aivai --depth 2 --delay 2`

## Game modes

| Key | Mode |
|-----|------|
| `M` | Cycle: **Human vs Human** → **Human vs AI** → **AI vs AI** |

## Controls

| Input | Action |
|-------|--------|
| Click piece → click target | Move (or click & drag) |
| `R` | New game |
| `U` | Undo (undoes 2 plies in AI-vs-AI) |
| `F` | Flip board |
| `H` | Hint (AI's suggested move) |
| `+` / `-` | Raise / lower AI depth (1–4) |
| `Esc` | Deselect |

## Rules support (engine.py)

- Full legal move generation — all piece types, no pseudo-legal shortcuts
- Castling (both sides, rights tracked & revoked correctly)
- En passant (including the ep-square edge cases)
- Promotion (auto-picker: Q/R/B/N — click or `Q`/`R`/`B`/`N`)
- Check / checkmate / stalemate detection
- Draws: threefold repetition, 50-move rule, insufficient material
- **SAN** (Standard Algebraic Notation) computed and stored per move, shown in
  the move list panel

## AI

`best_move(game, depth)` — negamax with alpha-beta pruning + a material/mobility
evaluator. Depth 2 is the default (snappy on any machine); depth 4 is a strong
club player. Moves run on a background thread so the UI never blocks.

## Files

| File | Purpose |
|------|---------|
| `engine.py` | Pure chess rules + AI — zero rendering dependencies, unit-tested |
| `crystal_chess.py` | pygame UI: crystal rendering, interaction, modes, move list |
| `test_rules.py` | 21 unit tests (castling, en passant, pins, draws, AI sanity) |
| `smoke_ui.py` | Headless boot test — plays a full AI-vs-AI game, saves `shots/smoke.png` |

## Headless test / smoke

```bash
python3 test_rules.py                      # 21/21 unit tests
SDL_VIDEODRIVER=dummy python3 smoke_ui.py  # AI-vs-AI game + screenshot
```

## Why standalone?

The user asked for a *standalone, non-browser* build. pygame + a pure-Python
engine keeps it fully offline, self-contained, and runnable with a single
command — no Node, no server, no SQLite, no network.
