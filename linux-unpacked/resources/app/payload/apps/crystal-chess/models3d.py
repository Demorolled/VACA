#!/usr/bin/env python3
"""models3d.py — 3D meshes for Crystal Chess 3D.

Board, pieces and highlights are built from simple primitives (boxes,
tapered prisms, discs) stacked to make the classic silhouettes. Side faces
alternate light/mid/dark crystal tones around each shape so the pieces read
as faceted cut glass.

World convention (matches engine3d.py): +y up, floor at y=0, one board square
= SQ (1.0) world units. Engine board coords map directly: a8 is (r=0, c=0) at
world (0, 0); +x is increasing file, +z is increasing rank.

Public API (contract for chess3d.py):
    SQ = 1.0
    square_center(r, c) -> Vec3          engine coords -> world position
    world_to_square(x, z) -> (r, c)|None
    build_board() -> Mesh                64 two-tone squares + frame + base
    build_piece(piece, side) -> Mesh     'KQRNBP' x 'wb' — base on y=0
    build_highlight(kind) -> Mesh        'dot'|'ring'|'select'|'last'|'check'
    WHITE_CRYSTAL / BLACK_CRYSTAL        material palettes (light/mid/dark)
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from engine3d import Mesh, Poly, Vec3

SQ = 1.0

# ── Crystal materials ─────────────────────────────────────────────────────────
# (light, mid, dark) face tones — alternated around a shape for the facet look.

WHITE_CRYSTAL = {
    "light": (246, 250, 255), "mid": (192, 220, 248), "dark": (122, 160, 202),
}
BLACK_CRYSTAL = {
    "light": (152, 122, 240), "mid": (94, 68, 170), "dark": (42, 28, 86),
}

BOARD_LIGHT = (234, 244, 255)
BOARD_DARK = (64, 74, 152)
FRAME = (74, 92, 168)
BASE = (16, 22, 44)

HIGHLIGHT = {
    "dot": (255, 255, 255),
    "ring": (255, 255, 255),
    "select": (0, 205, 255),
    "last": (255, 214, 130),
    "check": (255, 70, 70),
}


# ── Primitives ────────────────────────────────────────────────────────────────

Facet = Tuple[int, int, int]  # (light, mid, dark)


def _facet(f: Facet, i: int) -> Tuple[int, int, int]:
    return f[i % 3]


def _quad(a: Vec3, b: Vec3, c: Vec3, d: Vec3, color: Tuple[int, int, int]) -> Poly:
    return Poly([a, b, c, d], color)


def _box(cx: float, cz: float, w: float, d: float, y0: float, y1: float,
         facet: Facet, top: bool = True, start: int = 0) -> List[Poly]:
    """Axis-aligned box from y0 to y1; sides alternate facet tones, top is
    light. All faces wind OUTWARD (+normal away from the box) so backface
    culling in engine3d keeps them. No bottom face (never visible from above)."""
    hw, hd = w / 2.0, d / 2.0
    x0, x1 = cx - hw, cx + hw
    z0, z1 = cz - hd, cz + hd
    p: List[Poly] = [
        _quad(Vec3(x0, y0, z1), Vec3(x1, y0, z1), Vec3(x1, y1, z1), Vec3(x0, y1, z1), _facet(facet, 0 + start)),  # +z
        _quad(Vec3(x1, y0, z1), Vec3(x1, y0, z0), Vec3(x1, y1, z0), Vec3(x1, y1, z1), _facet(facet, 1 + start)),  # +x
        _quad(Vec3(x1, y0, z0), Vec3(x0, y0, z0), Vec3(x0, y1, z0), Vec3(x1, y1, z0), _facet(facet, 2 + start)),  # -z
        _quad(Vec3(x0, y0, z0), Vec3(x0, y0, z1), Vec3(x0, y1, z1), Vec3(x0, y1, z0), _facet(facet, 3 + start)),  # -x
    ]
    if top:
        p.append(_quad(Vec3(x0, y1, z1), Vec3(x1, y1, z1), Vec3(x1, y1, z0), Vec3(x0, y1, z0), facet[0]))
    return p


def _prism(n: int, r0: float, r1: float, y0: float, y1: float,
           facet: Facet, top: bool = True,
           cx: float = 0.0, cz: float = 0.0, start: int = 0) -> List[Poly]:
    """Tapered N-gon prism (cylinder approx) from y0 to y1, radius r0->r1.
    Sides wind outward; the top cap faces +y."""
    p: List[Poly] = []
    for i in range(n):
        a0 = 2.0 * math.pi * i / n
        a1 = 2.0 * math.pi * (i + 1) / n
        x0a, z0a = cx + r0 * math.cos(a0), cz + r0 * math.sin(a0)
        x0b, z0b = cx + r0 * math.cos(a1), cz + r0 * math.sin(a1)
        x1a, z1a = cx + r1 * math.cos(a0), cz + r1 * math.sin(a0)
        x1b, z1b = cx + r1 * math.cos(a1), cz + r1 * math.sin(a1)
        p.append(_quad(Vec3(x0a, y0, z0a), Vec3(x1a, y1, z1a),
                       Vec3(x1b, y1, z1b), Vec3(x0b, y0, z0b), _facet(facet, i + start)))
    if top:
        pts = [Vec3(cx + r1 * math.cos(2 * math.pi * i / n), y1,
                    cz + r1 * math.sin(2 * math.pi * i / n)) for i in range(n - 1, -1, -1)]
        p.append(Poly(pts, facet[0]))
    return p


def _disc(n: int, r: float, y: float, color: Tuple[int, int, int],
          cx: float = 0.0, cz: float = 0.0) -> Poly:
    """Flat N-gon facing +y (reversed winding)."""
    pts = [Vec3(cx + r * math.cos(2 * math.pi * i / n), y,
                cz + r * math.sin(2 * math.pi * i / n)) for i in range(n - 1, -1, -1)]
    return Poly(pts, color)


# ── Square mapping ────────────────────────────────────────────────────────────

def square_center(r: int, c: int) -> Vec3:
    """Engine coords (a8 = r0,c0) -> world center of the square."""
    return Vec3(c + SQ / 2.0, 0.0, r + SQ / 2.0)


def world_to_square(x: float, z: float) -> Optional[Tuple[int, int]]:
    """World floor point -> engine square, or None if outside the board."""
    c, r = int(math.floor(x)), int(math.floor(z))
    if 0 <= r <= 7 and 0 <= c <= 7:
        return r, c
    return None


# ── Board ─────────────────────────────────────────────────────────────────────

def build_board() -> Mesh:
    """Two-tone crystal squares on a raised frame over a dark base slab."""
    polys: List[Poly] = []
    # base slab (top at y=0 — the squares sit on it)
    slab = (BASE, BASE, BASE)
    polys += _box(4.0, 4.0, 9.2, 9.2, -0.24, 0.0, slab, top=False)
    # perimeter frame, slightly proud of the squares
    frame = (FRAME, FRAME, FRAME)
    polys += _box(4.0, -0.28, 8.56, 0.56, 0.0, 0.14, frame)
    polys += _box(4.0, 8.28, 8.56, 0.56, 0.0, 0.14, frame, start=1)
    polys += _box(-0.28, 4.0, 0.56, 8.56, 0.0, 0.14, frame, start=2)
    polys += _box(8.28, 4.0, 0.56, 8.56, 0.0, 0.14, frame, start=3)
    # 64 squares (wound so the normal faces +y — the camera is above the board)
    for r in range(8):
        for c in range(8):
            col = BOARD_LIGHT if (r + c) % 2 == 0 else BOARD_DARK
            polys.append(Poly([
                Vec3(c, 0.0, r), Vec3(c, 0.0, r + 1),
                Vec3(c + 1, 0.0, r + 1), Vec3(c + 1, 0.0, r),
            ], col))
    return Mesh(polys)


# ── Pieces ────────────────────────────────────────────────────────────────────

def build_piece(piece: str, side: str) -> Mesh:
    """Build a 3D piece mesh standing on y=0, fitting inside one square."""
    pal = WHITE_CRYSTAL if side == "w" else BLACK_CRYSTAL
    facet: Facet = (pal["light"], pal["mid"], pal["dark"])
    p: List[Poly] = []

    def box(cx, cz, w, d, y0, y1, f=None, top=True, start=0):
        p.extend(_box(cx, cz, w, d, y0, y1, f or facet, top, start))

    def prism(n, r0, r1, y0, y1, f=None, top=True, cx=0.0, cz=0.0, start=0):
        p.extend(_prism(n, r0, r1, y0, y1, f or facet, top, cx, cz, start))

    if piece == "P":
        box(0, 0, 0.52, 0.52, 0.0, 0.16)                       # base
        prism(8, 0.21, 0.15, 0.16, 0.44, start=1)              # stem
        prism(8, 0.13, 0.16, 0.44, 0.52, top=False, start=2)   # collar
        prism(8, 0.17, 0.13, 0.52, 0.6, start=3)               # head
        box(0, 0, 0.12, 0.12, 0.6, 0.64, f=(facet[0], facet[0], facet[0]))  # knob
        p.append(_disc(8, 0.1, 0.64, facet[0]))

    elif piece == "R":
        box(0, 0, 0.64, 0.64, 0.0, 0.16)                       # base
        prism(8, 0.29, 0.3, 0.16, 0.58, start=1)               # body
        p.append(_disc(8, 0.3, 0.58, facet[0]))
        for k, (ox, oz) in enumerate(((-0.22, -0.22), (0.22, -0.22),
                                      (-0.22, 0.22), (0.22, 0.22))):
            box(ox, oz, 0.16, 0.16, 0.58, 0.72, start=k)       # crenellations
        p.append(_disc(8, 0.12, 0.72, facet[1]))

    elif piece == "N":
        box(0, 0, 0.58, 0.58, 0.0, 0.15)                       # base
        prism(8, 0.26, 0.28, 0.15, 0.42, start=1)              # body
        prism(6, 0.22, 0.2, 0.42, 0.56, start=2, cz=0.06)      # chest, leaning fwd
        prism(6, 0.2, 0.17, 0.56, 0.74, start=3, cz=0.12)      # head
        box(0, 0.3, 0.15, 0.16, 0.6, 0.7, f=(facet[2], facet[2], facet[2]))  # muzzle
        box(-0.12, 0.1, 0.1, 0.2, 0.7, 0.84)                   # ear
        p.append(_disc(6, 0.1, 0.84, facet[1]))

    elif piece == "B":
        box(0, 0, 0.56, 0.56, 0.0, 0.14)                       # base
        prism(8, 0.2, 0.17, 0.14, 0.5, start=1)                # stem
        prism(8, 0.12, 0.14, 0.5, 0.6, start=2)                # collar
        prism(8, 0.16, 0.03, 0.6, 0.82, start=3)               # mitre cone
        box(0, 0, 0.1, 0.1, 0.82, 0.88)                        # finial

    elif piece == "Q":
        box(0, 0, 0.58, 0.58, 0.0, 0.16)                       # base
        prism(8, 0.23, 0.16, 0.16, 0.68, start=1)              # stem
        p.append(_disc(8, 0.16, 0.68, facet[0]))
        for i in range(6):                                     # crown spikes
            a = 2 * math.pi * i / 6
            prism(6, 0.045, 0.045, 0.68, 0.8, top=False,
                  cx=0.14 * math.cos(a), cz=0.14 * math.sin(a), start=i)
        prism(6, 0.11, 0.06, 0.8, 0.92, start=2)               # orb
        p.append(_disc(6, 0.06, 0.92, facet[0]))

    elif piece == "K":
        box(0, 0, 0.58, 0.58, 0.0, 0.16)                       # base
        prism(8, 0.23, 0.17, 0.16, 0.66, start=1)              # stem
        box(0, 0, 0.12, 0.12, 0.66, 0.98, f=(facet[0], facet[0], facet[0]))  # cross vertical
        box(0, 0, 0.36, 0.12, 0.78, 0.9, f=(facet[0], facet[0], facet[0]))   # cross horizontal
        p.append(_disc(8, 0.1, 0.98, facet[1]))

    else:
        raise ValueError(f"unknown piece type: {piece!r}")

    return Mesh(p)


# ── Highlights ────────────────────────────────────────────────────────────────

def build_highlight(kind: str) -> Mesh:
    """3D overlay meshes (flat, slightly above the board floor)."""
    col = HIGHLIGHT.get(kind)
    if col is None:
        raise ValueError(f"unknown highlight kind: {kind!r}")
    p: List[Poly] = []
    if kind == "dot":
        p.append(_disc(8, 0.17, 0.02, col))
    elif kind == "ring":
        n = 10
        for i in range(n):
            a0 = 2 * math.pi * i / n
            a1 = 2 * math.pi * (i + 1) / n
            p.append(_quad(
                Vec3(0.33 * math.cos(a0), 0.02, 0.33 * math.sin(a0)),
                Vec3(0.46 * math.cos(a0), 0.02, 0.46 * math.sin(a0)),
                Vec3(0.46 * math.cos(a1), 0.02, 0.46 * math.sin(a1)),
                Vec3(0.33 * math.cos(a1), 0.02, 0.33 * math.sin(a1)),
                col,
            ))
    else:  # select / last / check — square overlay (facing +y)
        p.append(Poly([
            Vec3(0.03, 0.015, 0.03), Vec3(0.97, 0.015, 0.03),
            Vec3(0.97, 0.015, 0.97), Vec3(0.03, 0.015, 0.97),
        ][::-1], col))
    return Mesh(p)
