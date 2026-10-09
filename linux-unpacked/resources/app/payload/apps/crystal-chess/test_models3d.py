#!/usr/bin/env python3
"""Headless tests for models3d.py — geometry + a full-scene render smoke test."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from engine3d import Camera, Mesh, Vec3, render
from models3d import (
    SQ, build_board, build_highlight, build_piece, square_center, world_to_square,
)

PIECES = "KQRNBP"
SIDES = "wb"


# ── Square mapping ────────────────────────────────────────────────────────────

def test_square_center_corners():
    assert square_center(0, 0) == Vec3(0.5, 0, 0.5)      # a8
    assert square_center(7, 7) == Vec3(7.5, 0, 7.5)      # h1
    assert square_center(7, 0) == Vec3(0.5, 0, 7.5)      # a1
    assert square_center(0, 7) == Vec3(7.5, 0, 0.5)      # h8


def test_world_to_square_roundtrip():
    for r in range(8):
        for c in range(8):
            center = square_center(r, c)
            assert world_to_square(center.x, center.z) == (r, c)


def test_world_to_square_off_board():
    assert world_to_square(-0.5, 3.5) is None
    assert world_to_square(3.5, 8.5) is None
    assert world_to_square(3.5, -1.0) is None


# ── Board ─────────────────────────────────────────────────────────────────────

def test_board_has_64_squares_plus_frame():
    board = build_board()
    assert len(board.polys) >= 64 + 5   # 64 squares + 4 frame boxes + base


def test_board_squares_on_floor():
    board = build_board()
    flat = [p for p in board.polys
            if all(abs(v.y) < 1e-6 for v in p.verts) and len(p.verts) == 4]
    assert len(flat) == 64


def test_board_square_colors_two_tone():
    board = build_board()
    colors = {p.color for p in board.polys if len(p.verts) == 4 and all(abs(v.y) < 1e-6 for v in p.verts)}
    assert len(colors) == 2


# ── Pieces ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("piece", PIECES)
@pytest.mark.parametrize("side", SIDES)
def test_piece_mesh_valid(piece, side):
    mesh = build_piece(piece, side)
    assert len(mesh.polys) >= 10, f"{piece}{side} too sparse"
    for poly in mesh.polys:
        for v in poly.verts:
            # base on the floor, within one square, sane height
            assert v.y >= -1e-6
            assert v.y <= 1.3
            assert -0.6 <= v.x <= 0.6 and -0.6 <= v.z <= 0.6


def test_piece_sides_have_distinct_palettes():
    white = build_piece("P", "w")
    black = build_piece("P", "b")
    w_colors = {p.color for p in white.polys}
    b_colors = {p.color for p in black.polys}
    assert w_colors != b_colors
    # white pawns are icy/bright, black are purple — check lightness
    w_avg = sum(sum(c) for c in w_colors) / len(w_colors)
    b_avg = sum(sum(c) for c in b_colors) / len(b_colors)
    assert w_avg > b_avg


def test_all_pieces_build_without_error():
    for piece in PIECES:
        for side in SIDES:
            mesh = build_piece(piece, side)
            assert len(mesh.polys) > 0


# ── Highlights ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["dot", "ring", "select", "last", "check"])
def test_highlight_kinds(kind):
    mesh = build_highlight(kind)
    assert len(mesh.polys) >= 1
    for poly in mesh.polys:
        for v in poly.verts:
            assert 0.0 <= v.y <= 0.05     # just above the floor


def test_unknown_highlight_raises():
    with pytest.raises(ValueError):
        build_highlight("nope")


# ── Full scene render (integration) ──────────────────────────────────────────

def test_full_scene_renders():
    """Board + full starting position + highlights render through the camera."""
    surf = pygame.Surface((640, 480))
    cam = Camera(yaw=-0.35, pitch=0.6, dist=13.5, w=640, h=480)

    entries = [(build_board(), Vec3(0, 0, 0))]
    back = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
    for r, rank in enumerate(back.split("/")):
        c = 0
        for ch in rank:
            if ch.isdigit():
                c += int(ch)
                continue
            piece = ch.upper()
            side = "w" if ch.isupper() else "b"
            entries.append((build_piece(piece, side), square_center(r, c)))
            c += 1
    entries.append((build_highlight("select"), square_center(4, 4)))
    entries.append((build_highlight("dot"), square_center(3, 3)))
    entries.append((build_highlight("check"), square_center(0, 4)))

    render(surf, cam, entries)
    colors = [surf.get_at((x, y))[:3] for x in range(0, 640, 8) for y in range(0, 480, 8)]
    lit = [c for c in colors if sum(c) > 40]
    # a rich scene: roughly a quarter of the window is drawn (board + pieces),
    # with both red-ish and blue-ish pixels (warm highlights + crystal blues)
    assert len(lit) > 900
    assert sum(c[0] for c in lit) > 0 and sum(c[2] for c in lit) > 0
