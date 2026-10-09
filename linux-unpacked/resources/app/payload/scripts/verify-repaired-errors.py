#!/usr/bin/env python3
"""Load repaired probe HTML files in headless Chrome and report errors."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path("/home/final-flash1/Desktop/visual-ai-architect/probes/r15-gui")

names = sys.argv[1:] or [
    "chat-app", "kanban-board", "markdown-previewer", "terminal-os",
    "todo-list", "quiz-app", "weather-widget", "interactive-dashboard",
    "spreadsheet-pro", "pomodoro-timer", "music-player", "code-editor",
]

with sync_playwright() as pw:
    b = pw.chromium.launch(
        executable_path="/usr/bin/google-chrome",
        headless=True,
        args=["--no-sandbox"],
    )
    for name in names:
        p = BASE / f"{name}-repaired.html"
        if not p.exists():
            print(f"--- {name}: MISSING repaired file")
            continue
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(f"PAGE: {e}"))
        pg.on("console", lambda m: errs.append(f"CONSOLE:{m.type}: {m.text}") if m.type == "error" else None)
        try:
            pg.goto(p.as_uri(), wait_until="load")
        except Exception as e:
            errs.append(f"LOAD: {e}")
        pg.wait_for_timeout(1200)
        n = len([e for e in errs if not e.startswith("CONSOLE:warning")])
        print(f"--- {name}: {n} errors")
        for e in errs[:6]:
            print("   ", e)
        pg.close()
    b.close()
