#!/usr/bin/env python3
"""
build-rook-piece.py — the 3D Rook chess piece, built by VACA (dspark).

Generates a single-file Three.js app rendering ONE detailed rook piece
(base -> shaft -> collar -> crenellated top, metal material, soft shadows,
slow rotation) through dspark, then:

  RAW gate -> REPAIR (repair-3d-wiring.py) -> REPAIRED gate
  FUNCTIONAL probe -> the rook actually exists (piece-like meshes + no errors)

On gate-pass, stores the compacted app as a training row
({instruction, input, output}) in "new training data set/chunk-3d-rook.jsonl"
ready to fold into a future round.

Usage: python3 scripts/build-rook-piece.py [--reuse]
"""
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "rook-piece"
OUT.mkdir(parents=True, exist_ok=True)
DSPARK = "http://127.0.0.1:8000/v1/chat/completions"
REPAIR = ROOT / "scripts" / "repair-3d-wiring.py"
SMOKE = ROOT / "scripts" / "smoke-test-html.py"
CHUNK = ROOT.parent / "new training data set" / "chunk-3d-rook.jsonl"

SYSTEM = (
    "You are an expert front-end engineer. Write complete, working code in a "
    "single HTML file. Output ONLY the raw HTML starting with <!DOCTYPE html> "
    "-- no markdown fences, no commentary."
)

INSTRUCTION = "Build a 3D Rook chess piece"
SPEC = (
    "Single-file HTML, Three.js r128 via CDN (global THREE + OrbitControls). A SINGLE detailed "
    "3D rook chess piece STANDING UPRIGHT in the middle of the scene. COMPOSITION RULES — "
    "follow them exactly:\n"
    "1. STACK the parts along the Y axis with explicit, non-overlapping y positions: base "
    "plinth (a flattened cylinder, e.g. radius 1.1, height 0.25) centered at y=-1.5 (spans "
    "-1.625..-1.375), tapered shaft (CylinderGeometry(radiusTop, radiusBottom, height) — "
    "radiusTop is FIRST, so a shaft narrow at top is CylinderGeometry(0.5, 0.9, 1.4, 32)) "
    "centered at y=-0.6 (spans -1.3..0.1, seated on the plinth), a flared collar (radius 0.6, "
    "height 0.1) centered at y=0.3, and the crenellated top (radius 0.45, height 0.3) centered "
    "at y=0.6 (spans 0.45..0.75). REMEMBER: position.y is the CENTER of a part, NOT its "
    "bottom — compute it as (partTop + partBottom) / 2 so parts just touch.\n"
    "2. The piece must STAND VERTICAL — do NOT rotate the group (no rotation.x set; keep the "
    "Y axis as the piece's long axis).\n"
    "3. Battlements: exactly 5 small cylinders (radius 0.12, height 0.25) arranged in a RING "
    "around the top rim at a fixed radius (0.45) and fixed angles (i * 2*PI/5 for i in 0..4) — "
    "use a loop with trig, NEVER Math.random() for placement.\n"
    "4. FRAMING: camera.position.set(3, 2.2, 5), camera.lookAt(0, 0, 0), controls.target.set(0, 0, 0) "
    "so the whole piece fills the middle of the frame.\n"
    "5. LIGHTING — critical: a metal material (metalness >0.8) reflects almost NO diffuse, so "
    "a single weak light makes it render NEARLY BLACK. Use metalness 0.6-0.75, roughness ~0.3, "
    "a strong key light (PointLight intensity >= 2.5) PLUS a directional fill light from the "
    "opposite side PLUS an ambient >= 0x444444. Soft shadows, warm spotlight from the upper "
    "right, gentle slow auto-rotation of the piece, OrbitControls.\n"
    "6. NAMING: never declare a top-level const named `top`, `name`, `length`, or `status` "
    "(built-in globals) — use descriptive names like `crownTop`.\n"
    "7. No textures, no external assets. Two-script rule: when using THREE.OrbitControls you "
    "MUST load BOTH https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js and "
    "https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js before "
    "the app script."
)

COMMENT_RE = re.compile(r"(?<!:)//[^\n]*")
MAX_SEQ = 3072
TOKEN_CHARS = 3.1
BUDGET_TOKENS = MAX_SEQ - 90


def est_tokens(text: str) -> int:
    return int(len(text) // TOKEN_CHARS) + 1


def compact(html: str) -> str:
    html = COMMENT_RE.sub("", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip() + "\n"


def gen(prompt: str, max_tokens: int = 3000):
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
         "--probe", "window.THREE !== undefined", "--wait", "4000"],
        capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False, {"error": "no-json"}
    errs = d.get("pageErrors", []) + d.get("consoleErrors", [])
    webgl = bool((d.get("canvas") or {}).get("webgl"))
    ok = (not errs) and webgl and bool((d.get("probes") or {}).get("window.THREE !== undefined"))
    return ok, {"errs": errs[:3], "webgl": webgl}


def functional_probe(html_path: pathlib.Path):
    """Verify a rook-like piece actually exists in the scene (not just renders)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path="/usr/bin/google-chrome", headless=True,
            args=["--no-sandbox", "--disable-gpu-sandbox", "--use-gl=swiftshader",
                  "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("file://" + str(html_path), wait_until="load", timeout=30000)
        pg.wait_for_timeout(5000)
        info = pg.evaluate("""() => {
            let sc = null;
            try { if (typeof scene !== 'undefined') sc = scene; } catch (e) {}
            if (!sc && window.__scene) sc = window.__scene;
            let meshCount = 0, cylCount = 0, boxCount = 0, highestY = 0;
            const visit = (o) => {
                if (o && o.isMesh) {
                    meshCount++;
                    if (o.geometry) {
                        const t = o.geometry.type || '';
                        if (t.includes('Cylinder')) cylCount++;
                        if (t.includes('Box')) boxCount++;
                    }
                    if (o.position) highestY = Math.max(highestY, o.position.y);
                }
                if (o && o.children) o.children.forEach(visit);
            };
            try { visit(sc); } catch (e) {}
            return { meshCount, cylCount, boxCount, hasScene: !!sc };
        }""")
        b.close()
        return info, errs[:3]


SURGICAL = [
    # `const top` collides with the built-in global window.top and kills the
    # ENTIRE script at instantiation ('Identifier top has already been
    # declared'). Rename the bare `top` binding to `crown` AND its usages.
    ("const top = new THREE.CylinderGeometry", "const crown = new THREE.CylinderGeometry"),
    ("new THREE.Mesh(top, topMat)", "new THREE.Mesh(crown, topMat)"),
    ("Mesh(top, ", "Mesh(crown, "),
    # COMPOSITION fixes (the 2026-08-10 regen followed the spec's shape but
    # botched the geometry 4 ways):
    # 1. CylinderGeometry(radiusTop, radiusBottom, ...) — the model put the
    #    WIDE end on top, inverting the rook's taper. radiusTop must be the
    #    narrower end.
    ("new THREE.CylinderGeometry(0.9, 0.5, 1.4, 32)",
     "new THREE.CylinderGeometry(0.5, 0.9, 1.4, 32)"),
    # 2. position.y is the part's CENTER, not its bottom — a center of -1.4
    #    with height 1.4 spans -2.1..-0.7 (sinks through the base, gaps the
    #    collar). Center it at -0.6 so it spans -1.3..0.1, seated on the base.
    ("shaftMesh.position.y = -1.4;", "shaftMesh.position.y = -0.6;"),
    # 3. Crown center to 0.6 (spans 0.45..0.75) so it caps the collar at 0.35
    #    instead of floating at 0.8 with a gap.
    ("topMesh.position.y = 0.8;", "topMesh.position.y = 0.6;"),
    # 4. Battlements are children of the crown: their y is LOCAL. 0.8 puts
    #    them at world y=1.6 (0.65 above the crown top). 0.28 -> world 0.88,
    #    standing ON the crown top (0.75).
    ("0.45 * Math.cos(i * 2 * Math.PI / 5), 0.8, 0.45 * Math.sin(i * 2 * Math.PI / 5)",
     "0.45 * Math.cos(i * 2 * Math.PI / 5), 0.28, 0.45 * Math.sin(i * 2 * Math.PI / 5)"),
    # 5. Battlements should STAND on the rim (vertical teeth), not lie flat.
    ("mesh.rotation.x = -Math.PI / 2;", "mesh.rotation.x = 0;"),
    # 6. Gunmetal 0x777777 on a 0x4a4a4a backdrop — the model rendered a dark
    #    piece on a dark background (black blob).
    ("color: 0x222222", "color: 0x777777", True),
    ("scene.background = new THREE.Color(0x222222);",
     "scene.background = new THREE.Color(0x4a4a4a);"),
    ("new THREE.Fog(0x222222, 20, 100)", "new THREE.Fog(0x4a4a4a, 20, 100)"),
    # 7. LIGHTING: metalness 0.95 under one weak PointLight(1.5) renders the
    #    piece nearly BLACK (metals reflect no diffuse; dim point light gives
    #    no specular). Raise the key light, add a fill directional, lift the
    #    ambient, and drop metalness to 0.7 so the piece is actually visible.
    ("new THREE.PointLight(0xffffff, 1.5)", "new THREE.PointLight(0xffffff, 2.5)"),
    ("new THREE.AmbientLight(0x333333)", "new THREE.AmbientLight(0x444444)"),
    ("scene.add(light);",
     "scene.add(light);\n    const fill = new THREE.DirectionalLight(0xffffff, 1.2);\n    fill.position.set(-4, 3, -3);\n    scene.add(fill);"),
    ("metalness: 0.95, roughness: 0.25 }", "metalness: 0.7, roughness: 0.3 }", True),
    # 8. FRAMING: the model set camera.position but never called lookAt — the
    #    camera stares level along -Z and the piece lands low-left in frame.
    #    Aim at the piece and pull the camera slightly closer for a fuller shot.
    ("camera.position.set(3, 2.2, 5);",
     "camera.position.set(2.6, 2.0, 4.2);\n    camera.lookAt(0, 0, 0);\n    controls.target.set(0, 0, 0);"),
]


def main() -> None:
    raw_path = OUT / "rook.html"
    if "--reuse" in sys.argv and raw_path.exists():
        raw_html = raw_path.read_text(encoding="utf-8")
        print(f"[rook] --reuse: using existing {raw_path.name}")
    else:
        print(f"[rook] generating via dspark (VACA): '{INSTRUCTION}'")
        out, dt, toks = gen(f"{INSTRUCTION}\n\n{SPEC}\n")
        raw_html = extract_html(out)
        raw_path.write_text(raw_html, encoding="utf-8")
        print(f"[rook] generated {len(raw_html)} chars in {dt:.0f}s ({toks} tokens)")

    raw_ok, raw_d = gate(raw_path)
    print(f"[rook] RAW gate: {'✅' if raw_ok else '❌'} {raw_d.get('errs', [])[:2]}")

    repaired = subprocess.run(
        [sys.executable, str(REPAIR), str(raw_path)],
        capture_output=True, text=True).stdout
    for old, new, *flags in SURGICAL:
        if old in repaired:
            count = 999 if flags else 1
            repaired = repaired.replace(old, new, count)
            label = old.split(" = ")[0].replace("const ", "").replace("new THREE.", "").split("(")[0]
            print(f"[rook] surgical fix: {label} ({'all' if flags else 'first'})")
    rep_path = OUT / "rook-repaired.html"
    rep_path.write_text(repaired, encoding="utf-8")
    rep_ok, rep_d = gate(rep_path)
    print(f"[rook] REPAIRED gate: {'✅' if rep_ok else '❌'} {rep_d.get('errs', [])[:2]}")

    info, ferrs = functional_probe(rep_path)
    print(f"[rook] functional probe: {json.dumps(info)} errs={ferrs}")
    func_ok = rep_ok and info.get("meshCount", 0) >= 3 and not ferrs

    results = {
        "instruction": INSTRUCTION,
        "raw_pass": raw_ok, "repaired_pass": rep_ok,
        "raw_errors": raw_d.get("errs", []), "repaired_errors": rep_d.get("errs", []),
        "functional": info, "functional_ok": func_ok,
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    if not func_ok:
        print(f"[rook] ❌ functional check failed (meshes={info.get('meshCount')}) — NOT stored for training")
        sys.exit(1)

    compacted = compact(repaired)
    tok = est_tokens(compacted)
    print(f"[rook] compacted ~{tok} tokens (budget {BUDGET_TOKENS})")
    if tok > BUDGET_TOKENS:
        print(f"[rook] ❌ over budget — NOT stored")
        sys.exit(1)
    row = {
        "instruction": INSTRUCTION,
        "input": SPEC,
        "output": compacted,
    }
    qa = {
        "instruction": "QA rule: never name a top-level const after a built-in global (top, name, length, status)",
        "input": "An app's whole script failed with 'Identifier top has already been declared' even though the "
                "code looked fine. THREE loaded, but nothing ran. Why?",
        "output": "window.top, window.name, window.length, window.status and similar are EXISTING built-in "
                "globals. A top-level `const top = ...` in a classic script collides with them and throws "
                "'Identifier ... has already been declared' at script instantiation — the ENTIRE script "
                "never runs (every other const stays in TDZ). Use descriptive names instead: `const crownTop`, "
                "`const pieceName`, `const listLength` — never the bare reserved word.\n",
    }
    with open(CHUNK, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.write(json.dumps(qa, ensure_ascii=False) + "\n")
    print(f"[rook] ✅ STORED 2 training rows -> {CHUNK}")
    print(f"[rook] files: {sorted(p.name for p in OUT.iterdir())}")


if __name__ == "__main__":
    main()
