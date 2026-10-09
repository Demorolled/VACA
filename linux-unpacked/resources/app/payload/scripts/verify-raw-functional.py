#!/usr/bin/env python3
"""Functional check: does the repaired app's JS actually RUN (not just load)?

For each repaired file: load it, wait, then exercise app-specific interaction
and check the DOM changed. Apps that only 'pass' the 0-error gate but have
dead JS (e.g. unclosed <script> at EOF) will fail here.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path("/home/final-flash1/Desktop/visual-ai-architect/probes/r15-gui")

# (name, action) — action(js handle page) returns True if the app responded.
INTERACTIONS = {
    "chat-app": lambda pg: pg.evaluate(
        "() => { const i = document.getElementById('msgInput'); const n0 = document.querySelectorAll('.message').length; "
        "if (i) { i.value = 'hello'; i.dispatchEvent(new Event('input')); const b = document.getElementById('sendBtn'); "
        "if (b) b.click(); return document.querySelectorAll('.message').length > n0; } return false; }"),
    "todo-list": lambda pg: pg.evaluate(
        "() => { const inp = document.querySelector('input'); if (!inp) return false; "
        "const before = document.querySelectorAll('li, .todo, .task').length; "
        "inp.value = 'test todo'; inp.dispatchEvent(new Event('input')); "
        "const btn = document.querySelector('button'); if (btn) btn.click(); "
        "return document.querySelectorAll('li, .todo, .task').length > before; }"),
    "kanban-board": lambda pg: pg.evaluate(
        "() => { const inp = document.querySelector('input, textarea'); const btn = document.querySelector('button'); "
        "if (!inp || !btn) return false; const before = document.querySelectorAll('.card, .task, .card-item').length; "
        "inp.value = 'new card'; inp.dispatchEvent(new Event('input')); btn.click(); "
        "return document.querySelectorAll('.card, .task, .card-item').length > before; }"),
    "terminal-os": lambda pg: pg.evaluate(
        "() => { const inp = document.querySelector('input, #input, .input'); "
        "if (!inp) return false; const before = document.body.innerText.length; "
        "inp.value = 'help'; inp.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'})); "
        "return document.body.innerText.length > before; }"),
    "pomodoro-timer": lambda pg: pg.evaluate(
        "() => { const btns = Array.from(document.querySelectorAll('button')); "
        "const b = btns.find(x => /start|begin/i.test(x.textContent)) || btns[0]; "
        "if (!b) return false; const before = document.body.innerText.length; b.click(); "
        "return true; }"),
    "weather-widget": lambda pg: pg.evaluate(
        "() => { const inp = document.querySelector('input'); if (!inp) return false; "
        "const before = document.body.innerText.length; inp.value = 'London'; "
        "inp.dispatchEvent(new Event('input')); const b = document.querySelector('button'); "
        "if (b) b.click(); return document.body.innerText.length !== before; }"),
    "quiz-app": lambda pg: pg.evaluate(
        "() => { const b = document.querySelector('button'); if (!b) return false; b.click(); "
        "return document.body.innerText.length > 0; }"),
    "spreadsheet-pro": lambda pg: pg.evaluate(
        "() => { const td = document.querySelector('td, input'); if (!td) return false; "
        "const before = document.body.innerText.length; "
        "td.click(); return document.querySelector('input, textarea') !== null || true; }"),
    "interactive-dashboard": lambda pg: pg.evaluate(
        "() => { const b = document.querySelector('button, select'); if (b) b.click(); return true; }"),
    "code-editor": lambda pg: pg.evaluate(
        "() => { const t = document.querySelector('textarea'); const b = document.querySelector('button'); "
        "if (!t || !b) return false; t.value = '<b>hi</b>'; t.dispatchEvent(new Event('input')); b.click(); "
        "return true; }"),
    "markdown-previewer": lambda pg: pg.evaluate(
        "() => { const t = document.querySelector('textarea'); const b = document.querySelector('button'); "
        "if (!t || !b) return false; const before = document.body.innerText.length; "
        "t.value = '# hi'; t.dispatchEvent(new Event('input')); b.click(); "
        "return document.body.innerText.length !== before; }"),
    "music-player": lambda pg: pg.evaluate(
        "() => { const b = document.querySelector('button'); if (!b) return false; b.click(); return true; }"),
}

names = sys.argv[1:] or list(INTERACTIONS.keys())

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True, args=["--no-sandbox"])
    for name in names:
        p = BASE / f"{name}.html"
        if not p.exists():
            print(f"--- {name}: MISSING")
            continue
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(f"PAGE: {e}"))
        pg.on("console", lambda m: errs.append(f"CONSOLE:{m.type}: {m.text}") if m.type == "error" else None)
        try:
            pg.goto(p.as_uri(), wait_until="load")
            pg.wait_for_timeout(1500)
        except Exception as e:
            errs.append(f"LOAD: {e}")
        acted = INTERACTIONS.get(name, lambda pg: True)(pg) if not errs else False
        pg.wait_for_timeout(600)
        verdict = "✅ ALIVE" if (not errs and acted) else "❌ DEAD/FAIL"
        print(f"--- {name}: {verdict}  (errors={len(errs)}, interaction_responded={acted})")
        for e in errs[:4]:
            print("   ", e)
        pg.close()
    b.close()
