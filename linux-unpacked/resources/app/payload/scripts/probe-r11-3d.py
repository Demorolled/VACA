#!/usr/bin/env python3
"""
R11 3D-ability probe battery.

Generates 8 Three.js single-file HTML apps through dspark (the deployed R11
model) using prompts that mirror the round-11 training data (instruction +
detailed input spec), then runs the established render gate
(scripts/smoke-test-html.py) on each: console/page errors, WebGL canvas,
fallback banner, THREE probe, screenshot.

Writes probes/r11-3d/results.json + per-app HTML and screenshots.
"""
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "r11-3d"
OUT.mkdir(parents=True, exist_ok=True)
DSPARK = "http://127.0.0.1:8000/v1/chat/completions"

SYSTEM = (
    "You are an expert front-end engineer. Write complete, working code in a "
    "single HTML file. Output ONLY the raw HTML starting with <!DOCTYPE html> "
    "-- no markdown fences, no commentary."
)

# (name, instruction, detailed spec) — mirrors chunk-3d.jsonl rows
BATTERY = [
    ("solar-system",
     "Build a 3D Solar System",
     "Create a stunning 3D solar system in a single HTML file. Use Three.js r128 "
     "via CDN (global THREE + OrbitControls). Sun in the center with glowing "
     "material, 8 planets orbiting at different radii and speeds, Saturn with "
     "rings, starfield background, labels. Auto-rotate camera slowly. Clean UI."),
    ("chess",
     "Build a 3D Chess game",
     "Create a stunning 3D chess game in a single HTML file. Use Three.js r128 "
     "via CDN (global THREE + OrbitControls). Real 3D board with checkerboard "
     "texture, all 32 pieces as 3D shapes, click-to-select and move with legal "
     "square highlighting, turn indicator, orbit camera."),
    ("maze-explorer",
     "Build a 3D Maze Explorer",
     "Create a 3D first-person maze explorer in a single HTML file. Use Three.js "
     "r128 via CDN (global THREE). Procedural maze of walls with different "
     "colors, WASD movement with collision, mouse-look, minimap overlay, timer "
     "and a goal marker."),
    ("terrain-viewer",
     "Build a 3D Terrain Viewer",
     "Create an interactive 3D terrain viewer in a single HTML file. Use "
     "Three.js r128 via CDN (global THREE + OrbitControls). Heightmap-generated "
     "rolling hills with gradient coloring by elevation, animated clouds, "
     "roughness slider that regenerates the terrain, FPS counter."),
    ("fireworks",
     "Build 3D Particle Fireworks",
     "Create a 3D fireworks show in a single HTML file. Use Three.js r128 via "
     "CDN (global THREE). Rockets launch from the ground and burst into "
     "hundreds of colored particles that fade and fall with gravity, multiple "
     "colors, launch button and auto-loop."),
    ("product-showcase",
     "Build a 3D Product Showcase",
     "Create a 3D product showcase in a single HTML file. Use Three.js r128 via "
     "CDN (global THREE + OrbitControls). Three product objects (bottle, sphere, "
     "cube) on a rotating pedestal with studio lighting, buttons to switch "
     "products, smooth transitions, elegant dark UI."),
    ("bar-chart",
     "Build a 3D Bar Chart",
     "Create an animated 3D bar chart in a single HTML file. Use Three.js r128 "
     "via CDN (global THREE + OrbitControls). 12 months of data as 3D bars with "
     "gradient colors, hover tooltip with value, axis labels, newData button "
     "that regenerates the chart."),
    ("rubiks-cube",
     "Build a 3D Rubik's Cube",
     "Create an interactive 3D Rubik's cube in a single HTML file. Use Three.js "
     "r128 via CDN (global THREE + OrbitControls). 3x3x3 cube of 26 cubies with "
     "colored stickers, click or keyboard to rotate layers with smooth "
     "animation, shuffle and reset buttons, move counter."),
]


def gen(prompt: str):
    payload = {
        "model": "x",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4000,
        "temperature": 0.7,
        "stream": False,
    }
    req = urllib.request.Request(
        DSPARK, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    out = d["choices"][0]["message"]["content"]
    return out, time.time() - t0, d.get("usage", {}).get("completion_tokens", 0)


def extract_html(out: str) -> str:
    m = re.search(r"<!DOCTYPE html>.*", out, re.S)
    if m:
        return m.group(0)
    i = out.find("<html")
    return out[i:] if i >= 0 else ""


def main() -> None:
    results = []
    for name, instruction, spec in BATTERY:
        print(f"\n=== {name} ===")
        html_path = OUT / f"{name}.html"
        if not html_path.exists():
            prompt = f"{instruction}\n\n{spec}\n"
            print(f"  generating...")
            out, dt, toks = gen(prompt)
            html = extract_html(out)
            if not html:
                results.append({"name": name, "pass": False,
                                "error": "no HTML in model output",
                                "gen_s": round(dt), "tokens": toks})
                print(f"  NO HTML ({dt:.0f}s, {toks} tok)")
                continue
            html_path.write_text(html)
            print(f"  generated {toks} tokens in {dt:.0f}s -> {len(html)} chars")
        else:
            print("  (reusing existing file)")

        shot = OUT / f"{name}-shot.png"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "smoke-test-html.py"),
             str(html_path), "--probe", "window.THREE !== undefined",
             "--out", str(shot)],
            capture_output=True, text=True, timeout=240)
        try:
            res = json.loads(proc.stdout)  # stdout is pure JSON
        except Exception:
            res = {"error": proc.stdout[:200] + proc.stderr[:200]}
        res["name"] = name
        res["pass"] = proc.returncode == 0
        results.append(res)
        print(f"  render: {'PASS' if res['pass'] else 'FAIL'} "
              f"(errs={len(res.get('consoleErrors', []) + res.get('pageErrors', []))}, "
              f"webgl={res.get('canvas', {}).get('webgl')})")

    (OUT / "results.json").write_text(
        json.dumps(results, indent=2))
    npass = sum(1 for r in results if r.get("pass"))
    print(f"\n{'='*60}\nBATTERY RESULT: {npass}/{len(results)} PASS")
    for r in results:
        print(f"  {'✅' if r['pass'] else '❌'} {r['name']}")


if __name__ == "__main__":
    main()
