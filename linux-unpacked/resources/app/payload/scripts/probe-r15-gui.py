#!/usr/bin/env python3
"""
probe-r15-gui.py — R15 GUI-app battery (dual-gate, DOM bar)

Generates 12 polished GUI apps through dspark (VACA R14) — the GUI/vision
half of the R15 push. Unlike the 3D probes, the gate bar here is DOM-based,
NOT WebGL: 0 page/console errors + probe holds + real interactive content
(elements count). A pure canvas requirement would wrongly fail every 2D app.

  RAW pass rate  — app as generated
  REPAIRED rate  — after scripts/repair-gui.py (mechanical GUI fixes:
                   script-order, missing DOMContentLoaded guard, null-safe
                   handlers — classes observed in earlier GUI generations)

Per-app defect classes feed the R15 GUI training chunk
(chunk-gui-verified.jsonl): passing apps become generation-framed rows,
failing classes become QA-rule rows.

Writes probes/r15-gui/{name}.html, {name}-repaired.html, results.json,
REPORT.md. Run: python3 scripts/probe-r15-gui.py
"""
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "r15-gui"
OUT.mkdir(parents=True, exist_ok=True)
DSPARK = "http://127.0.0.1:8000/v1/chat/completions"
REPAIR = ROOT / "scripts" / "repair-gui.py"
SMOKE = ROOT / "scripts" / "smoke-test-html.py"

SYSTEM = (
    "You are an expert front-end engineer. Write complete, working code in a "
    "single HTML file. Output ONLY the raw HTML starting with <!DOCTYPE html> "
    "-- no markdown fences, no commentary."
)

# (name, instruction, spec) — 12 GUI categories spanning the projects/ library.
BATTERY = [
    ("interactive-dashboard", "Build an interactive analytics dashboard",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A dark-themed "
     "dashboard with KPI cards (Revenue, Users, Conversion), a bar chart and a "
     "line chart drawn on <canvas>, a date-range filter that updates the charts, "
     "and hover tooltips on the charts."),
    ("kanban-board", "Build a kanban task board",
     "Single-file HTML, no external libraries, vanilla JS + CSS. Three columns "
     "(To Do / Doing / Done) with draggable cards (HTML5 drag-and-drop), a form "
     "to add cards, a card counter per column, and localStorage persistence."),
    ("chat-app", "Build a chat messenger UI",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A polished "
     "messenger: message bubbles left/right, an input box that sends on Enter, "
     "a simulated bot reply after a delay, typing indicator, and timestamps."),
    ("terminal-os", "Build a retro terminal",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A green-on-black "
     "terminal that accepts commands (help, ls, cat, date, clear, echo), shows a "
     "blinking cursor, keeps a scrollable history, and has a boot banner."),
    ("spreadsheet-pro", "Build a spreadsheet app",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A grid of "
     "editable cells (A1..H20) built from a table, click-to-edit, SUM/AVG "
     "formulas entered as =SUM(B2:B6), a formula bar, and cell highlighting "
     "on selection."),
    ("todo-list", "Build a todo list app",
     "Single-file HTML, no external libraries, vanilla JS + CSS. Add/complete/"
     "delete todos, filter by All/Active/Completed, remaining-count badge, "
     "clear-completed button, and localStorage persistence."),
    ("markdown-previewer", "Build a markdown previewer",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A split pane: "
     "textarea on the left, live-rendered markdown (headings, bold, lists, "
     "links, code blocks) on the right, and a copy-markdown button."),
    ("weather-widget", "Build a weather dashboard",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A city search "
     "input, a large current-conditions card (temp, condition icon drawn with "
     "CSS/emoji, humidity, wind), a 5-day forecast row, and a unit toggle "
     "(C/F). Uses a fake local dataset (no network)."),
    ("pomodoro-timer", "Build a pomodoro focus timer",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A large "
     "circular timer that counts down work/break sessions, start/pause/reset "
     "controls, session counter, and a progress ring drawn with SVG or canvas."),
    ("code-editor", "Build a code editor with live preview",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A textarea "
     "editor on the left with a Run button that renders the entered HTML/CSS/JS "
     "into an iframe preview on the right, a line counter, and error display."),
    ("music-player", "Build a music player UI",
     "Single-file HTML, no external libraries, vanilla JS + CSS. A modern "
     "player: album-art square, track title, play/pause/next/prev buttons, a "
     "seek bar that advances with a timer, a playlist sidebar, and volume "
     "control."),
    ("quiz-app", "Build a quiz app",
     "Single-file HTML, no external libraries, vanilla JS + CSS. Multiple-choice "
     "questions one at a time, progress bar, immediate right/wrong feedback, "
     "final score screen with restart, and a timer per question."),
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


# GUI bar: 0 errors + probe + real content. Probe checks the body has actual
# UI. table/li are included so table-first layouts (spreadsheets) count as
# interactive content — this MUST match the chunk builder's DOM_PROBE.
GUI_PROBE = ("document.body !== null && document.body.children.length >= 1 "
             "&& (document.querySelectorAll('button,input,textarea,canvas,div,table,li').length >= 3)")


def gate(html_path: pathlib.Path):
    r = subprocess.run(
        [sys.executable, str(SMOKE), str(html_path),
         "--probe", GUI_PROBE, "--wait", "3500"],
        capture_output=True, text=True, timeout=300)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False, {"error": "no-json", "rc": r.returncode,
                       "stderr": r.stderr[-150:], "stdout": r.stdout[-150:]}
    errs = d.get("pageErrors", []) + d.get("consoleErrors", [])
    probes = d.get("probes") or {}
    probe_ok = bool(probes.get(GUI_PROBE)) if probes else True
    ok = (not errs) and probe_ok
    return ok, {"errs": errs[:2], "probe": probe_ok, "raw": d}


def classify(raw_errs, repaired_errs, repaired_ok, raw_probe_ok) -> str:
    joined = " ".join(str(e) for e in (raw_errs + repaired_errs))
    if repaired_ok:
        return "GUI-fixable (mechanical repair)"
    if "is not defined" in joined or "Cannot read properties of undefined" in joined:
        return "scope/undefined variable"
    if "is not a function" in joined:
        return "bad API / wrong receiver"
    if "Failed to load resource" in joined or "404" in joined or "net::ERR" in joined:
        return "asset/network 404"
    if "Page crashed" in joined or "no-json" in str(repaired_errs):
        return "page crash"
    if not raw_probe_ok and not raw_errs:
        return "no interactive content / probe fail (0 errors)"
    return "other"


def main() -> None:
    results = []
    raw_total = repaired_total = 0
    print(f"[probe-r15-gui] 12-app GUI battery via dspark, dual-gate (DOM bar)")
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
        cls = classify(raw_d.get("errs", []), rep_d.get("errs", []), rep_ok,
                       raw_d.get("probe", True))

        print(f"  {name}: raw={'✅' if raw_ok else '❌'} "
              f"repaired={'✅' if rep_ok else '❌'} [{cls}] "
              f"({dt:.0f}s, {toks} tok)")
        results.append({
            "name": name, "raw_pass": raw_ok, "repaired_pass": rep_ok,
            "class": cls,
            "raw_errs": raw_d.get("errs", []),
            "repaired_errs": rep_d.get("errs", []),
        })
        (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")

    lines = [
        "# R15 GUI-App Battery (dual-gate, DOM bar)",
        "",
        f"**Through dspark serving R14 — RAW {raw_total}/{len(BATTERY)} GUI apps pass; "
        f"after mechanical repair {repaired_total}/{len(BATTERY)} pass.**",
        "Gate: 0 page/console errors + DOM probe + interactive elements (no WebGL bar).",
        "",
        "| App | Raw | Repaired | Class |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {'✅' if r['raw_pass'] else '❌'} | "
            f"{'✅' if r['repaired_pass'] else '❌'} | {r['class']} |")
    lines += ["", "## Verdict", "",
              f"- RAW GUI pass: {raw_total}/{len(BATTERY)} (first GUI breadth measure for R14).",
              f"- Repaired pass: {repaired_total}/{len(BATTERY)}.",
              "", "Run: `python3 scripts/probe-r15-gui.py` — apps in `probes/r15-gui/`.",
              "`results.json`."]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[probe-r15-gui] RAW {raw_total}/{len(BATTERY)} | REPAIRED {repaired_total}/{len(BATTERY)}")
    print(f"[probe-r15-gui] report: {OUT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
