#!/usr/bin/env python3
"""
R13 3D-breadth probe battery.

Generates the 12 RANDOM-3D app categories (the ones chunk-3d-random.jsonl
teaches — city, galaxy, ocean, DNA, lava lamp, snow globe, molecule, voxel
castle, butterfly swarm, donut, shooting stars, audio visualizer) through
dspark (the deployed R13 model), using prompts that mirror the round-13
training rows, then runs the established render gate
(scripts/smoke-test-html.py) on each: console/page errors, WebGL canvas,
THREE probe, screenshot.

Same gate as the R11 probe (window.THREE !== undefined) for a fair
comparison: the model's generated apps will NOT set the training-only
window.__vaca3d markers, so requiring them would be unfair.

Writes probes/r13-3d/results.json + per-app HTML and screenshots, plus
REPORT.md comparing against the R11 baseline (raw 0/8, 3/8 after the
mechanical OrbitControls fix).
"""
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "r13-3d"
OUT.mkdir(parents=True, exist_ok=True)
DSPARK = "http://127.0.0.1:8000/v1/chat/completions"

SYSTEM = (
    "You are an expert front-end engineer. Write complete, working code in a "
    "single HTML file. Output ONLY the raw HTML starting with <!DOCTYPE html> "
    "-- no markdown fences, no commentary."
)

# (name, instruction, detailed spec) — mirrors chunk-3d-random.jsonl rows
BATTERY = [
    ("city-skyline",
     "Build a 3D night city skyline",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A sprawling night city with hundreds of buildings of random heights, "
     "lit window lights, roads, fog, and a Randomize City button that "
     "regenerates the skyline. Moonlight with shadows. OrbitControls, resize."),
    ("galaxy-spiral",
     "Build a 3D spiral galaxy",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A spiral galaxy made of thousands of glowing particles with warm core "
     "to cool-blue edges, a bright core sphere, and a Regenerate button that "
     "rebuilds the galaxy with a different arm count. Slow rotation."),
    ("ocean-waves",
     "Build a 3D ocean with animated waves",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A large ocean plane with animated vertex waves, a few bobbing buoys, "
     "sunlight with shadows, and a wireframe toggle button."),
    ("dna-helix",
     "Build a 3D DNA double helix",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A rotating DNA double helix with two colored strands of beads and "
     "connecting rungs, pulsing subtly. Nice lighting with shadows."),
    ("lava-lamp",
     "Build a 3D lava lamp",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A glass lava lamp with a dark base, glowing warm blobs that rise, fall "
     "and morph inside the glass, and a soft glow light."),
    ("snow-globe",
     "Build a 3D snow globe",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A glass dome on a wooden base with a tiny house and tree inside, falling "
     "snow particles, and a Shake button that spins the snow."),
    ("molecule-viewer",
     "Build a 3D molecule viewer",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A ball-and-stick molecule viewer with element-colored atoms and bonds, "
     "a Cycle button that switches between Water, Methane and Benzene, and a "
     "caption showing the current molecule."),
    ("voxel-castle",
     "Build a 3D voxel castle",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A voxel castle built from cubes: outer walls with a gate, corner towers, "
     "battlements, a keep, roofs and a flag. A New Castle button regenerates "
     "it with a different layout. Ground, fog, sun shadows."),
    ("butterfly-swarm",
     "Build a 3D butterfly swarm",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A meadow with dozens of colorful butterflies flapping their wings while "
     "wandering on gentle paths, a Respawn button that rebuilds the swarm, "
     "soft sunlight and fog."),
    ("donut-shop",
     "Build a 3D donut showcase",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A glossy glazed donut with colorful sprinkles on a ceramic plate under a "
     "warm spotlight, floating and slowly spinning. A New Glaze button cycles "
     "the glaze color."),
    ("shooting-stars",
     "Build a 3D shooting star field",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A night sky with a dense starfield and comets that streak across the "
     "sky leaving fading trails, launching automatically and on a button."),
    ("audio-visualizer",
     "Build a 3D music visualizer",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A reactive 3D visualizer: a row of bars that pulse to a synthetic beat "
     "(no audio file needed) with a hue gradient, a reflective floor, and a "
     "Play/Pause button."),
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
            print("  generating...")
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

    # ── comparison report vs the R11 probe baseline ──────────────────────
    r11 = ROOT / "probes" / "r11-3d" / "results-repaired.json"
    r11_note = ""
    if r11.exists():
        try:
            r11r = json.loads(r11.read_text())
            r11_pass = sum(1 for x in r11r if x.get("pass"))
            r11_note = f"R11 baseline (same gate): {r11_pass}/{len(r11r)} after mechanical fix (raw 0/8)."
        except Exception:
            r11_note = "R11 baseline: 3/8 after mechanical OrbitControls fix (raw 0/8)."
    else:
        r11_note = "R11 baseline: 3/8 after mechanical OrbitControls fix (raw 0/8)."

    md = [
        "# R13 Random-3D Breadth Probe",
        "",
        f"**Generated through dspark serving R13 — {npass}/{len(results)} apps pass the render gate.**",
        f"({r11_note})",
        "",
        "| App | Result | Errors | WebGL | Notes |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        errs = len(r.get("consoleErrors", []) + r.get("pageErrors", []))
        first = (r.get("pageErrors") or r.get("consoleErrors") or [""])[0][:60]
        md.append(f"| {r['name']} | {'✅' if r['pass'] else '❌'} | {errs} | "
                  f"{r.get('canvas', {}).get('webgl')} | {first} |")
    md += [
        "",
        f"Run: `python3 scripts/probe-r13-3d.py` — apps in `probes/r13-3d/`, "
        "screenshots `*-shot.png`, `results.json`.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nwrote {OUT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
