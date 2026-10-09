#!/usr/bin/env python3
"""
R14 3D-breadth probe battery — dual-gate (raw vs mechanically repaired).

Generates the same 12 random-3D app categories as R13 through dspark (the
deployed R14 model), then for each app measures TWO numbers:

  RAW pass rate      — the app as generated (R13-comparable: 0/12 baseline)
  REPAIRED pass rate — after scripts/repair-3d-wiring.py (OrbitControls addon
                       injection + CDN case fix) — this isolates DEPENDENCY
                       WIRING from real breadth defects.

Both gates use the same bar (scripts/smoke-test-html.py): no page/console
errors + WebGL canvas + window.THREE probe.

Per-app defect classes are classified so the R14 training (generation-framed
defect rows + QA rules) can be verified: wiring-only, shader, scope,
object-indexing, performance/crash, derailment, CDN case.

Writes probes/r14-3d/results.json + per-app HTML (raw + repaired) + REPORT.md
comparing against R13 (raw 0/12).
"""
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "r14-3d"
OUT.mkdir(parents=True, exist_ok=True)
DSPARK = "http://127.0.0.1:8000/v1/chat/completions"
REPAIR = ROOT / "scripts" / "repair-3d-wiring.py"
SMOKE = ROOT / "scripts" / "smoke-test-html.py"

SYSTEM = (
    "You are an expert front-end engineer. Write complete, working code in a "
    "single HTML file. Output ONLY the raw HTML starting with <!DOCTYPE html> "
    "-- no markdown fences, no commentary."
)

# (name, instruction, detailed spec) — mirrors the R13 probe / R14 training rows
BATTERY = [
    ("city-skyline", "Build a 3D night city skyline",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A sprawling night city with hundreds of buildings of random heights, "
     "lit window lights, roads, fog, and a Randomize City button that "
     "regenerates the skyline. Moonlight with shadows. OrbitControls, resize."),
    ("galaxy-spiral", "Build a 3D spiral galaxy",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A spiral galaxy made of thousands of glowing particles with warm core "
     "to cool-blue edges, a bright core sphere, and a Regenerate button that "
     "rebuilds the galaxy with a different arm count. Slow rotation."),
    ("ocean-waves", "Build a 3D ocean with animated waves",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A large ocean plane with animated vertex waves, a few bobbing buoys, "
     "sunlight with shadows, and a wireframe toggle button."),
    ("dna-helix", "Build a 3D DNA double helix",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A rotating DNA double helix with two colored strands of beads and "
     "connecting rungs, pulsing subtly. Nice lighting with shadows."),
    ("lava-lamp", "Build a 3D lava lamp",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A glass lava lamp with a dark base, glowing warm blobs that rise, fall "
     "and morph inside the glass, and a soft glow light."),
    ("snow-globe", "Build a 3D snow globe",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A glass dome on a wooden base with a tiny house and tree inside, falling "
     "snow particles, and a Shake button that spins the snow."),
    ("molecule-viewer", "Build a 3D molecule viewer",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A ball-and-stick molecule viewer with element-colored atoms and bonds, "
     "a Cycle button that switches between Water, Methane and Benzene, and a "
     "caption showing the current molecule."),
    ("voxel-castle", "Build a 3D voxel castle",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A voxel castle built from cubes: outer walls with a gate, corner towers, "
     "battlements, a keep, roofs and a flag. A New Castle button regenerates "
     "it with a different layout. Ground, fog, sun shadows."),
    ("butterfly-swarm", "Build a 3D butterfly swarm",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A meadow with dozens of colorful butterflies flapping their wings while "
     "wandering on gentle paths, a Respawn button that rebuilds the swarm, "
     "soft sunlight and fog."),
    ("donut-shop", "Build a 3D donut showcase",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A glossy glazed donut with colorful sprinkles on a ceramic plate under a "
     "warm spotlight, floating and slowly spinning. A New Glaze button cycles "
     "the glaze color."),
    ("shooting-stars", "Build a 3D shooting star field",
     "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). "
     "A night sky with a dense starfield and comets that streak across the "
     "sky leaving fading trails, launching automatically and on a button."),
    ("audio-visualizer", "Build a 3D music visualizer",
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


def repair(html_path: pathlib.Path) -> str:
    r = subprocess.run(
        [sys.executable, str(REPAIR), str(html_path)],
        capture_output=True, text=True)
    return r.stdout


def gate(html_path: pathlib.Path):
    r = subprocess.run(
        [sys.executable, str(SMOKE), str(html_path),
         "--probe", "window.THREE !== undefined", "--wait", "4000"],
        capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False, {"error": "no-json", "rc": r.returncode,
                       "stderr": r.stderr[-150:], "stdout": r.stdout[-150:]}
    errs = d.get("pageErrors", []) + d.get("consoleErrors", [])
    webgl = bool((d.get("canvas") or {}).get("webgl"))
    ok = (not errs) and webgl and bool((d.get("probes") or {}).get("window.THREE !== undefined"))
    return ok, {
        "errs": errs[:2],
        "webgl": webgl,
        "canvas_found": bool((d.get("canvas") or {}).get("found")),
    }


def classify(raw_errs, repaired_errs, repaired_ok) -> str:
    joined = " ".join(str(e) for e in (raw_errs + repaired_errs))
    if repaired_ok:
        return "wiring-only (fixed by addon injection)"
    if "OrbitControls is not a constructor" in joined:
        return "wiring (addon missing)"
    if "shader error" in joined or "WebGLShader" in joined or "gl.getProgramInfoLog" in joined:
        return "shader/GLSL"
    if "is not defined" in joined or "undeclared" in joined:
        return "scope/undefined variable"
    if "undefined (reading" in joined or "undefined (reading '" in joined:
        return "uninitialized property"
    if "is not a function" in joined:
        return "bad API / wrong receiver"
    if "Page crashed" in joined or "Target page" in joined or "no-json" in str(repaired_errs):
        return "renderer crash (perf/pathological)"
    if "Failed to load resource" in joined or "404" in joined:
        return "CDN/asset 404"
    return "other"


def main() -> None:
    results = []
    raw_total = repaired_total = 0
    print(f"[probe-r14] 12-app battery via dspark, dual-gate (raw | repaired)")
    for name, instruction, spec in BATTERY:
        prompt = f"{instruction}\n\n{spec}\n"
        out, dt, toks = gen(prompt)
        raw_html = extract_html(out)
        raw_path = OUT / f"{name}.html"
        raw_path.write_text(raw_html, encoding="utf-8")
        repaired_html = repair(raw_path)
        rep_path = OUT / f"{name}-repaired.html"
        rep_path.write_text(repaired_html, encoding="utf-8")

        raw_ok, raw_d = gate(raw_path)
        rep_ok, rep_d = gate(rep_path)
        raw_total += 1 if raw_ok else 0
        repaired_total += 1 if rep_ok else 0
        cls = classify(raw_d.get("errs", []), rep_d.get("errs", []), rep_ok)

        print(f"  {name}: raw={'✅' if raw_ok else '❌'} "
              f"repaired={'✅' if rep_ok else '❌'} [{cls}] "
              f"({dt:.0f}s, {toks} tok)")
        results.append({
            "name": name, "raw_pass": raw_ok, "repaired_pass": rep_ok,
            "class": cls,
            "raw_errs": raw_d.get("errs", []),
            "repaired_errs": rep_d.get("errs", []),
            "raw_webgl": raw_d.get("webgl"), "repaired_webgl": rep_d.get("webgl"),
        })
        (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    # ─── REPORT.md ───────────────────────────────────────────────────────
    lines = [
        "# R14 Random-3D Breadth Probe (dual-gate)",
        "",
        f"**Through dspark serving R14 — RAW {raw_total}/{len(BATTERY)} apps pass; "
        f"after mechanical wiring repair {repaired_total}/{len(BATTERY)} pass.**",
        "(R13 baseline: raw 0/12; R11 baseline: raw 0/8 → 3/8 after OrbitControls fix.)",
        "",
        "| App | Raw | Repaired | Class |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {'✅' if r['raw_pass'] else '❌'} | "
            f"{'✅' if r['repaired_pass'] else '❌'} | {r['class']} |")
    lines += [
        "",
        "## Verdict",
        "",
    ]
    if repaired_total > 0 and raw_total == 0:
        lines.append("- **Wiring still the dominant failure** — but the repaired "
                     "pass rate measures how much real breadth exists behind it.")
    if raw_total > 0:
        lines.append(f"- RAW gain vs R13 (0/12): **{raw_total} app(s) now pass clean "
                     "without any repair** — the wiring defect is being learned.")
    if repaired_total > raw_total:
        lines.append(f"- Repaired-only passes ({repaired_total - raw_total}) are "
                     "pure wiring failures (addon script / CDN case).")
    lines += [
        "",
        f"Run: `python3 scripts/probe-r14-3d.py` — apps in `probes/r14-3d/`, "
        "`results.json`.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[probe-r14] RAW {raw_total}/{len(BATTERY)} | REPAIRED {repaired_total}/{len(BATTERY)}")
    print(f"[probe-r14] report: {OUT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
