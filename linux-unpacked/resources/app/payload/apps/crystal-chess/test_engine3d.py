#!/usr/bin/env python3
"""Headless tests for engine3d.py — no display needed (dummy SDL driver)."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math

import pygame
import pytest

from engine3d import Camera, Mesh, Poly, Vec3, render


# ── Vec3 ──────────────────────────────────────────────────────────────────────

def test_vec3_ops():
    a = Vec3(1, 2, 3)
    b = Vec3(4, -1, 2)
    assert (a + b) == Vec3(5, 1, 5)
    assert (b - a) == Vec3(3, -3, -1)
    assert (a * 2) == Vec3(2, 4, 6)
    assert a.dot(b) == pytest.approx(1 * 4 + 2 * -1 + 3 * 2)
    c = Vec3(1, 0, 0).cross(Vec3(0, 1, 0))
    assert c.x == pytest.approx(0) and c.y == pytest.approx(0) and c.z == pytest.approx(1)
    assert Vec3(3, 4, 0).len() == pytest.approx(5)
    n = Vec3(0, 5, 0).norm()
    assert n.y == pytest.approx(1) and n.len() == pytest.approx(1)


# ── Camera ────────────────────────────────────────────────────────────────────

def make_cam():
    return Camera(yaw=0.0, pitch=0.6, dist=14.0, w=800, h=600)


def test_camera_project_center():
    cam = make_cam()
    # board center should project near the screen center
    p = cam.project(Vec3(3.5, 0, 3.5))
    assert p is not None
    sx, sy = p
    assert 380 <= sx <= 420
    assert 280 <= sy <= 320


def test_camera_project_behind_is_none():
    cam = make_cam()
    # a point behind the camera (opposite side of the target) is culled
    assert cam.project(cam.eye + cam.forward * -10) is None


def test_camera_ray_plane_roundtrip():
    cam = make_cam()
    # pick the screen center -> floor under it should be near board center
    hit = cam.ray_plane(400, 300)
    assert hit is not None
    x, z = hit
    assert 2.5 <= x <= 4.5 and 2.5 <= z <= 4.5


def test_camera_ray_plane_off_board():
    cam = make_cam()
    hit = cam.ray_plane(10, 10)  # top-left corner of the window
    assert hit is not None  # a floor point exists; may be off the board


def test_camera_orbit_and_zoom_clamp():
    cam = make_cam()
    cam.orbit(0.5, 0.1)
    assert cam.yaw == pytest.approx(0.5)
    assert cam.pitch == pytest.approx(0.7)
    cam.orbit(0, 5.0)          # pitch clamps high
    assert cam.pitch <= 1.35
    cam.orbit(0, -9.0)         # and low
    assert cam.pitch >= 0.08
    cam.zoom(-50)              # dist clamps
    assert cam.dist >= 4.0
    cam.zoom(100)
    assert cam.dist <= 26.0


def test_camera_resize_updates_projection():
    cam = make_cam()
    cam.resize(1200, 900)
    p = cam.project(Vec3(3.5, 0, 3.5))
    assert p is not None
    assert 580 <= p[0] <= 620 and 430 <= p[1] <= 470


# ── Rendering ─────────────────────────────────────────────────────────────────

def _surface(w=200, h=200):
    return pygame.Surface((w, h))


def test_mesh_draw_paints_pixels():
    surf = _surface()
    # a front-facing quad high above the floor, straight ahead of the camera
    mesh = Mesh([Poly([
        Vec3(-0.5, 1, -1), Vec3(0.5, 1, -1),
        Vec3(0.5, 1, -3), Vec3(-0.5, 1, -3),
    ], (200, 30, 30))])
    cam = Camera(yaw=0, pitch=0.3, dist=6, w=200, h=200)
    mesh.draw(surf, cam, Vec3(3.5, 0, 3.5))
    # something red should be visible
    colors = [surf.get_at((x, y))[:3] for x in range(0, 200, 4) for y in range(0, 200, 4)]
    assert any(c[0] > 150 and c[1] < 90 for c in colors)


def test_mesh_draw_backface_culled():
    surf = _surface()
    # a quad facing DOWN (away from the camera above it) draws nothing
    mesh = Mesh([Poly([
        Vec3(-0.5, 0, -0.5), Vec3(0.5, 0, -0.5),
        Vec3(0.5, 0, 0.5), Vec3(-0.5, 0, 0.5),
    ], (30, 200, 30))])
    cam = Camera(yaw=0, pitch=0.6, dist=6, w=200, h=200)
    mesh.draw(surf, cam, Vec3(3.5, 0, 3.5))
    colors = [surf.get_at((x, y))[:3] for x in range(0, 200, 4) for y in range(0, 200, 4)]
    assert not any(c[1] > 150 and c[0] < 90 for c in colors)


def test_render_multiple_meshes_no_error():
    surf = _surface()
    cam = Camera(yaw=0.3, pitch=0.5, dist=10, w=200, h=200)
    meshes = [
        Mesh([Poly([Vec3(-1, 0, -1), Vec3(1, 0, -1), Vec3(1, 0, 1), Vec3(-1, 0, 1)], (50, 50, 200))]),
        Mesh([Poly([Vec3(-0.3, 0.5, -0.3), Vec3(0.3, 0.5, -0.3),
                    Vec3(0.3, 0.5, 0.3), Vec3(-0.3, 0.5, 0.3)], (200, 200, 50))]),
    ]
    render(surf, cam, [(meshes[0], Vec3(3.5, 0, 3.5)), (meshes[1], Vec3(3.5, 0, 3.5))])
    assert True  # no exception = render pipeline healthy
