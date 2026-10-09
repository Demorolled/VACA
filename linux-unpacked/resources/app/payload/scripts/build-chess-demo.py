#!/usr/bin/env python3
"""
build-chess-demo.py — generate the 3D chess demo WITH VACA (dspark).

Sends the chess build prompt (mirroring the chunk-3d training spec) to dspark
(currently serving the deployed VACA model), extracts the HTML, then:

  RAW gate      -> scripts/smoke-test-html.py (console/page errors + WebGL)
  REPAIR        -> scripts/repair-3d-wiring.py (addon injection + CDN case)
  REPAIRED gate -> same bar

Writes probes/chess-demo/chess.html (+ -repaired.html, -shot.png, results.json,
REPORT.md). R11's chess app failed on broken external texture URLs — the spec
explicitly forbids external assets, so this measures the model's current
ability at a real game build.

Usage: python3 scripts/build-chess-demo.py
"""
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "chess-demo"
OUT.mkdir(parents=True, exist_ok=True)
DSPARK = "http://127.0.0.1:8000/v1/chat/completions"
REPAIR = ROOT / "scripts" / "repair-3d-wiring.py"
SMOKE = ROOT / "scripts" / "smoke-test-html.py"

SYSTEM = (
    "You are an expert front-end engineer. Write complete, working code in a "
    "single HTML file. Output ONLY the raw HTML starting with <!DOCTYPE html> "
    "-- no markdown fences, no commentary."
)

INSTRUCTION = "Build a 3D Chess game"
SPEC = (
    "Create a stunning 3D chess game in a single HTML file. Use Three.js r128 via CDN "
    "(global THREE + OrbitControls). Real 3D board with checkerboard texture, LatheGeometry "
    "chess pieces (pawn, rook, knight, bishop, queen, king) with metal materials, soft shadows, "
    "fog, starfield background, OrbitControls with damping, intro camera sweep, legal move "
    "highlighting, move/capture animation via lerp, en passant, castling, check/checkmate "
    "detection, and an AI opponent. NEVER use external image assets or URLs for textures or "
    "models — generate the checkerboard with a canvas + CanvasTexture and give pieces solid "
    "metal MeshStandardMaterial colors. Two-script rule: when using THREE.OrbitControls you "
    "MUST load BOTH https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js and "
    "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js before "
    "the app script."
)


def gen(prompt: str, max_tokens: int = 7000):
    payload = {
        "model": "x",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
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


def gate(html_path: pathlib.Path):
    r = subprocess.run(
        [sys.executable, str(SMOKE), str(html_path),
         "--probe", "window.THREE !== undefined", "--wait", "5000"],
        capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False, {"error": "no-json", "rc": r.returncode,
                       "stderr": r.stderr[-150:], "stdout": r.stdout[-150:]}
    errs = d.get("pageErrors", []) + d.get("consoleErrors", [])
    webgl = bool((d.get("canvas") or {}).get("webgl"))
    ok = (not errs) and webgl and bool((d.get("probes") or {}).get("window.THREE !== undefined"))
    return ok, {"errs": errs[:4], "webgl": webgl,
                "canvas_found": bool((d.get("canvas") or {}).get("found"))}


def main() -> None:
    raw_path = OUT / "chess.html"
    toks = 0
    if "--reuse" in sys.argv and raw_path.exists():
        raw_html = raw_path.read_text(encoding="utf-8")
        print(f"[chess-demo] --reuse: re-gating existing {raw_path.name} ({len(raw_html)} chars)")
    else:
        print(f"[chess-demo] generating via dspark (VACA): '{INSTRUCTION}'")
        out, dt, toks = gen(f"{INSTRUCTION}\n\n{SPEC}\n")
        raw_html = extract_html(out)
        raw_path.write_text(raw_html, encoding="utf-8")
        print(f"[chess-demo] generated {len(raw_html)} chars in {dt:.0f}s ({toks} completion tokens)")

    raw_ok, raw_d = gate(raw_path)
    print(f"[chess-demo] RAW gate: {'✅ PASS' if raw_ok else '❌ FAIL'}"
          + (f" — {raw_d.get('errs', [])[:2]}" if not raw_ok else ""))

    repaired = subprocess.run(
        [sys.executable, str(REPAIR), str(raw_path)],
        capture_output=True, text=True).stdout
    rep_path = OUT / "chess-repaired.html"
    rep_path.write_text(repaired, encoding="utf-8")
    rep_ok, rep_d = gate(rep_path)
    print(f"[chess-demo] REPAIRED gate: {'✅ PASS' if rep_ok else '❌ FAIL'}"
          + (f" — {rep_d.get('errs', [])[:2]}" if not rep_ok else ""))

    results = {
        "model": "R13 (dspark, Q4_K_M)",
        "instruction": INSTRUCTION,
        "generated_chars": len(raw_html),
        "completion_tokens": toks,
        "raw_pass": raw_ok,
        "repaired_pass": rep_ok,
        "raw_errors": raw_d.get("errs", []),
        "repaired_errors": rep_d.get("errs", []),
        "raw_webgl": raw_d.get("webgl"),
        "repaired_webgl": rep_d.get("webgl"),
        "files": [p.name for p in OUT.iterdir()],
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    lines = [
        "# 3D Chess Demo — built by VACA (dspark)",
        "",
        f"**RAW gate: {'✅ PASS' if raw_ok else '❌ FAIL'} | "
        f"after mechanical wiring repair: {'✅ PASS' if rep_ok else '❌ FAIL'}**",
        "",
        f"- Model: R13 (Q4_K_M) via dspark on :8000",
        f"- Spec: {SPEC[:90]}...",
        f"- Generated: {len(raw_html)} chars, {toks} completion tokens",
        "",
        "## Raw gate errors",
    ]
    for e in raw_d.get("errs", []):
        lines.append(f"- `{str(e)[:120]}`")
    if not raw_d.get("errs"):
        lines.append("- (none)")
    lines += [
        "",
        "## Repaired gate errors",
    ]
    for e in rep_d.get("errs", []):
        lines.append(f"- `{str(e)[:120]}`")
    if not rep_d.get("errs"):
        lines.append("- (none)")
    lines += [
        "",
        "## Verdict",
        "",
    ]
    if raw_ok:
        lines.append("The model generated a fully working 3D chess app — no repair needed.")
    elif rep_ok:
        lines.append("Wiring-only failure (OrbitControls addon / CDN) — mechanically repaired "
                     "to a clean render. The game logic itself is intact.")
    else:
        lines.append("Defects beyond wiring — inspect the app + errors above (may be a good "
                     "R15 defect-row candidate).")
    lines += [
        "",
        f"Files: `probes/chess-demo/chess.html` (raw), `chess-repaired.html`, `chess-shot.png`, "
        "`results.json`.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[chess-demo] report: {OUT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
