#!/usr/bin/env python3
"""engine3d.py — minimal software 3D pipeline for Crystal Chess 3D.

Pure pygame (no numpy/OpenGL): a small vector/matrix-free renderer that
projects 3D polygons through an orbiting perspective camera and draws them
back-to-front (painter's algorithm) with flat directional shading.

Public API (contract for chess3d.py):
    Vec3(x, y, z)                     — 3D point, ops: + - * dot cross len norm
    Camera(yaw, pitch, dist, w, h)    — orbit camera around target
        .project(v) -> (sx, sy)|None  — world point to screen pixel
        .ray_plane(sx, sy, plane_y) -> (x, z)|None  — floor point under a pixel
        .orbit(dyaw, dpitch)          — rotate view
        .zoom(d)                      — change distance
    Poly(verts, color)                — 3D polygon (verts are Vec3)
        .shade(factor) -> Poly        — recolored copy
    Mesh(polys)                       — collection of polys
        .draw(surface, camera, center)  — draw at world position `center`
    render(surface, camera, entries)  — draw a list of (mesh, center) pairs

World convention: +y up, board floor at y=0, a8 near (0, 0), +x to the right
(increasing file), +z away from the camera's default view (increasing rank).
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import pygame

# ── Vector ───────────────────────────────────────────────────────────────────

class Vec3:
    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: "Vec3") -> "Vec3":
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s: float) -> "Vec3":
        return Vec3(self.x * s, self.y * s, self.z * s)

    __rmul__ = __mul__

    def dot(self, o: "Vec3") -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o: "Vec3") -> "Vec3":
        return Vec3(
            self.y * o.z - self.z * o.y,
            self.z * o.x - self.x * o.z,
            self.x * o.y - self.y * o.x,
        )

    def len(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def norm(self) -> "Vec3":
        d = self.len()
        if d < 1e-9:
            return Vec3(0, 1, 0)
        return Vec3(self.x / d, self.y / d, self.z / d)

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Vec3):
            return NotImplemented
        return (abs(self.x - o.x) < 1e-9 and abs(self.y - o.y) < 1e-9
                and abs(self.z - o.z) < 1e-9)

    def __hash__(self) -> int:  # allow use in sets/dicts
        return hash((round(self.x, 6), round(self.y, 6), round(self.z, 6)))

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"Vec3({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"


# ── Camera ───────────────────────────────────────────────────────────────────

NEAR = 0.2


class Camera:
    """Orbiting perspective camera looking at a fixed target."""

    def __init__(self, yaw: float = 0.0, pitch: float = 0.55, dist: float = 14.0,
                 w: int = 900, h: int = 700, target: Optional[Vec3] = None,
                 fov: float = 52.0):
        self.yaw = yaw
        self.pitch = max(0.08, min(1.35, pitch))   # never go below the board
        self.dist = max(4.0, dist)
        self.w, self.h = w, h
        self.fov = fov
        self.target = target if target is not None else Vec3(3.5, 0.0, 3.5)
        self._update()

    def _update(self) -> None:
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        # eye orbits the target on a sphere of radius dist
        eye = self.target + Vec3(cp * sy, sp, cp * cy) * self.dist
        forward = (self.target - eye).norm()
        right = forward.cross(Vec3(0, 1, 0)).norm()
        upv = right.cross(forward).norm()
        self.eye, self.forward, self.right, self.upv = eye, forward, right, upv
        self.fl = (self.h / 2.0) / math.tan(math.radians(self.fov) / 2.0)

    # ── view transforms ────────────────────────────────────────────────────

    def _to_camera(self, p: Vec3) -> Vec3:
        d = p - self.eye
        return Vec3(d.dot(self.right), d.dot(self.upv), d.dot(self.forward))

    def project(self, v: Vec3) -> Optional[Tuple[float, float]]:
        """World point -> screen pixel, or None if behind the camera."""
        p = self._to_camera(v)
        if p.z <= NEAR:
            return None
        sx = self.w / 2.0 + p.x * self.fl / p.z
        sy = self.h / 2.0 - p.y * self.fl / p.z
        return sx, sy

    def ray_plane(self, sx: float, sy: float, plane_y: float = 0.0) -> Optional[Tuple[float, float]]:
        """World-floor (x, z) under a screen pixel, or None when the ray is
        parallel to the plane (shouldn't happen — pitch is clamped)."""
        # direction in camera space through the pixel
        dx = (sx - self.w / 2.0) / self.fl
        dy = (self.h / 2.0 - sy) / self.fl
        dir_c = Vec3(dx, dy, 1.0).norm()
        # to world space
        dir_w = self.right * dir_c.x + self.upv * dir_c.y + self.forward * dir_c.z
        if abs(dir_w.y) < 1e-9:
            return None
        t = (plane_y - self.eye.y) / dir_w.y
        if t < 0:
            return None
        hit = self.eye + dir_w * t
        return hit.x, hit.z

    # ── controls ───────────────────────────────────────────────────────────

    def orbit(self, dyaw: float, dpitch: float) -> None:
        self.yaw += dyaw
        self.pitch = max(0.08, min(1.35, self.pitch + dpitch))
        self._update()

    def zoom(self, d: float) -> None:
        self.dist = max(4.0, min(26.0, self.dist + d))
        self._update()

    def resize(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self._update()


# ── Polygon / mesh ───────────────────────────────────────────────────────────

Color = Tuple[int, int, int]

LIGHT_DIR = Vec3(-0.5, 1.0, -0.35).norm()  # fixed directional light


class Poly:
    __slots__ = ("verts", "color")

    def __init__(self, verts: Sequence[Vec3], color: Color):
        self.verts = list(verts)
        self.color = color

    def _normal(self, center: Vec3) -> Vec3:
        a, b, c = (self.verts[0] + center, self.verts[1] + center,
                   self.verts[2] + center)
        return (b - a).cross(c - a).norm()

    def shade(self, factor: float) -> "Poly":
        r = min(255, int(self.color[0] * factor))
        g = min(255, int(self.color[1] * factor))
        b = min(255, int(self.color[2] * factor))
        return Poly(self.verts, (r, g, b))


class Mesh:
    __slots__ = ("polys",)

    def __init__(self, polys: Sequence[Poly]):
        self.polys = list(polys)

    def draw(self, surface: pygame.Surface, camera: Camera, center: Vec3) -> None:
        """Project + cull + shade + sort + fill. `center` translates the mesh
        (piece meshes sit on y=0 at their base, so passing a square center
        stands them on that square; pass an animated offset for lifts)."""
        queue: List[Tuple[float, Color, List[Tuple[float, float]]]] = []
        for poly in self.polys:
            normal = poly._normal(center)
            # backface cull: face is visible when it points toward the camera
            to_eye = camera.eye - (poly.verts[0] + center)
            if normal.dot(to_eye) <= 0:
                continue
            light = max(0.25, normal.dot(LIGHT_DIR))
            col = poly.shade(0.72 + 0.42 * light).color
            screen: List[Tuple[float, float]] = []
            view_z = 0.0
            ok = True
            for v in poly.verts:
                p = camera.project(v + center)
                if p is None:
                    ok = False
                    break
                screen.append(p)
                view_z += camera._to_camera(v + center).z
            if not ok or len(screen) < 3:
                continue
            queue.append((view_z / len(screen), col, screen))
        # far -> near (painter's algorithm)
        for _, col, screen in sorted(queue, key=lambda q: -q[0]):
            if len(screen) >= 3:
                pygame.draw.polygon(surface, col, screen)


def render(surface: pygame.Surface, camera: Camera,
           entries: Sequence[Tuple[Mesh, Vec3]]) -> None:
    """Draw a list of (mesh, center) pairs. Order in the list is the render
    order — put the board first, highlights next, pieces last for correctness
    (each mesh still depth-sorts its own polys internally)."""
    for mesh, center in entries:
        mesh.draw(surface, camera, center)
