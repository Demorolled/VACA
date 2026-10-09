#!/usr/bin/env python3
"""
playtest-chess.py — functional playtest of the VACA chess demo.

The render gate (smoke-test-html.py) only proves the page has no errors and a
WebGL canvas — it cannot prove the GAME works. This script plays the game in
headless Chrome and verifies real game mechanics:

  * page loads clean (no console/page errors)
  * a board + pieces exist
  * BLACK pieces exist (a chess game needs two sides)
  * clicking a piece then a destination actually MOVES it
  * moveHistory / turn / check state changes
  * the board does NOT continuously spin (a static board is expected)

Writes probes/chess-demo/playtest.json + screenshot.
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

CHROME = "/usr/bin/google-chrome"
OUT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect/probes/chess-demo")
PATH = OUT / "chess-repaired.html"

PROBE_JS = """() => {
  const canvas = document.querySelector('canvas');
  return {
    canvas: !!canvas,
    three: typeof THREE !== 'undefined',
    piecesVar: typeof pieces !== 'undefined' ? Object.keys(pieces).length : -1,
    blackPieces: (typeof pieces !== 'undefined')
      ? Object.values(pieces).filter(p => p && p.isBlack).length : -1,
    state: (typeof state !== 'undefined')
      ? { turn: state.turn, moveHistoryLen: (state.moveHistory||[]).length,
          check: state.check, enPassant: state.enPassantTarget } : null,
    boardRotY: (typeof board !== 'undefined') ? board.rotation.y : null,
    hasMoveFn: typeof move === 'function',
    hasClickHandler: (typeof raycaster !== 'undefined') && (typeof pointer !== 'undefined'),
    hintText: document.getElementById('hint') ? document.getElementById('hint').textContent : null,
  };
}"""


def main() -> None:
    results = {"checks": {}, "errors": [], "console": []}
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME, headless=True,
            args=["--no-sandbox", "--disable-gpu-sandbox", "--use-gl=swiftshader",
                  "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1280, "height": 800})
        page_errors, console_msgs = [], []
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.on("console", lambda m: console_msgs.append(f"{m.type}: {m.text[:140]}"))
        pg.goto("file://" + str(PATH), wait_until="load", timeout=30000)
        pg.wait_for_timeout(7000)  # let CDN + init settle
        results["console"] = console_msgs[:8]
        results["errors"] = page_errors[:8]

        base = pg.evaluate(PROBE_JS)
        results["checks"]["load"] = {
            "clean": (not page_errors) and not [c for c in console_msgs if "error" in c.lower()],
            "canvas": base["canvas"], "three": base["three"],
        }
        results["checks"]["initial"] = base

        # Board rotation check: sample rotation.y over 3s
        r0 = base["boardRotY"]
        pg.wait_for_timeout(3000)
        r1 = pg.evaluate("() => (typeof board !== 'undefined') ? board.rotation.y : null")
        results["checks"]["spins"] = {
            "r0": r0, "r1": r1, "spinning": (r1 is not None and r0 is not None and abs(r1 - r0) > 0.001),
        }

        # Hint button
        pg.click("#hintBtn")
        pg.wait_for_timeout(300)
        hint = pg.evaluate("() => document.getElementById('hint').textContent")
        results["checks"]["hint"] = hint or ""

        # Try to PLAY: click board center, then elsewhere — does anything move?
        before = pg.evaluate("() => (typeof state !== 'undefined') ? state.moveHistory.length : -1")
        pg.mouse.click(640, 400)
        pg.mouse.click(700, 420)
        pg.mouse.click(580, 380)
        pg.wait_for_timeout(1500)
        after = pg.evaluate("() => (typeof state !== 'undefined') ? state.moveHistory.length : -1")
        pieces_after = pg.evaluate(
            "() => (typeof pieces !== 'undefined') ? JSON.stringify(Object.keys(pieces).sort()) : '[]'")
        results["checks"]["click_moves_piece"] = {
            "moveHistory_before": before, "moveHistory_after": after,
            "changed": before != after,
        }
        pg.screenshot(path=str(OUT / "playtest-shot.png"))

        b.close()

    # ── Verdict ──
    c = results["checks"]
    verdicts = []
    if c["load"]["clean"] and c["load"]["canvas"]:
        verdicts.append("renders clean")
    else:
        verdicts.append("rendering problems")
    if c["initial"]["blackPieces"] > 0:
        verdicts.append("has black pieces")
    else:
        verdicts.append("NO black pieces")
    if c["spins"]["spinning"]:
        verdicts.append("board SPINS continuously (bug)")
    else:
        verdicts.append("board static")
    if c["click_moves_piece"]["changed"]:
        verdicts.append("clicks move pieces")
    else:
        verdicts.append("clicks do NOTHING")
    if c["initial"]["hasMoveFn"]:
        verdicts.append("move() exists")
    else:
        verdicts.append("no move() function")
    results["verdict"] = "; ".join(verdicts)

    (OUT / "playtest.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps({"checks": {k: v for k, v in results["checks"].items()},
                      "verdict": results["verdict"], "errors": results["errors"][:4]}, indent=1))


if __name__ == "__main__":
    main()
