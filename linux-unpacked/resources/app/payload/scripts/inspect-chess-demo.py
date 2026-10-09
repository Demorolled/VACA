#!/usr/bin/env python3
"""Inspect the VACA-generated chess demo: features + THREE classes used."""
import pathlib
import re

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect/probes/chess-demo")
src = (ROOT / "chess-repaired.html").read_text(encoding="utf-8", errors="replace")

print("files:", sorted(p.name for p in ROOT.iterdir()))
print("size:", len(src), "chars")

features = ["LatheGeometry", "CanvasTexture", "minimax", "enPassant", "castling",
            "checkmate", "isCheck", "queen", "knight", "Move", "animate",
            "requestAnimationFrame", "setAnimationLoop", "orbitControls",
            "OrbitControls", "THREE.Fog", "PointLight", "SpotLight", "AmbientLight"]
print("\nfeatures:")
for f in features:
    n = src.count(f)
    if n:
        print(f"  {f}: {n}")

classes = {}
for m in re.finditer(r"new THREE\.([A-Za-z]+)", src):
    classes[m.group(1)] = classes.get(m.group(1), 0) + 1
print("\nTHREE classes constructed:")
for k, v in sorted(classes.items(), key=lambda kv: -kv[1]):
    print(f"  {k}: {v}")
