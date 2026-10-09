#!/usr/bin/env python3
"""
run-orpo-seed.py — seed the ORPO self-learning loop with real write cycles.

Runs plan-code → write-code cycles for a batch of requests (4 very-simple, then
4 medium) so the harness snapshots FIRST DRAFTS (snapshotFirstDrafts, #62) and
captures verified finals. After this completes:

    python3 scripts/build-orpo-pairs.py      # → training/dataset/orpo-pairs.jsonl

Each write also logs tscErrors + tscClasses (telemetry, #61) so the convergence
rate of the batch is visible.

Usage:
  python3 scripts/run-orpo-seed.py            # both batches (default)
  python3 scripts/run-orpo-seed.py --simple   # very-simple batch only
  python3 scripts/run-orpo-seed.py --medium   # medium batch only
  python3 scripts/run-orpo-seed.py --medium2  # second medium batch (5 builds)
  python3 scripts/run-orpo-seed.py --medium3  # third medium batch (5 builds)
  python3 scripts/run-orpo-seed.py --medium4  # fourth medium batch (5 builds)
  python3 scripts/run-orpo-seed.py --medium5  # fifth medium batch (5 builds)
  python3 scripts/run-orpo-seed.py --tmux     # re-exec inside a named tmux session
"""
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

BASE = "http://127.0.0.1:3001"
LOG = "/tmp/orpo-seed.log"

SIMPLE = [
    "a todo list CLI app in TypeScript with add, list, and done commands",
    "a calculator app in TypeScript that does add, subtract, multiply, and divide",
    "a temperature converter app in TypeScript (Celsius and Fahrenheit)",
    "a password generator app in TypeScript that makes random 12-character passwords",
]

MEDIUM = [
    "a note-taking app in TypeScript: store notes in a JSON file, list/add/edit/delete, with a simple web UI",
    "a habit tracker app in TypeScript: track daily habits, mark them done, show streaks, persist to local storage",
    "a quiz app in TypeScript: multiple-choice questions with scoring and a results screen",
    "a URL shortener app: an Express API that maps short codes to URLs and serves a redirect endpoint",
]

MEDIUM2 = [
    "a kanban task board CLI app in TypeScript: columns (todo/doing/done), move tasks between columns, persist to a JSON file",
    "a markdown blog generator in TypeScript: read .md files from a folder and emit static HTML pages with an index",
    "a pomodoro timer app in TypeScript: 25-minute work / 5-minute break cycles with a session history log",
    "an expense tracker app in TypeScript: add expenses with category and amount, show monthly totals and a category breakdown",
    "a flashcard study app in TypeScript: decks of cards, quiz yourself, track correct/incorrect per review session",
]

MEDIUM3 = [
    "a music playlist manager app in TypeScript: create playlists, add/remove songs, shuffle a playlist, persist to a JSON file",
    "a budget splitter app in TypeScript: split an expense among friends and show who owes whom what amount",
    "a contact book app in TypeScript: add/search contacts by name or tag, edit and delete, persist to a JSON file",
    "a tic-tac-toe game app in TypeScript: two-player turns, win/tie detection, and a board display",
    "a log analyzer app in TypeScript: parse log lines with levels, count per level, and report the top modules by error count",
]

MEDIUM4 = [
    "a recipe manager app in TypeScript: add recipes with ingredients, scale servings, search recipes by ingredient, persist to a JSON file",
    "a banking ledger app in TypeScript: accounts with deposits and withdrawals, show balance and transaction history",
    "a text stats tool app in TypeScript: count words, characters, sentences and show the most frequent words in a text",
    "an event countdown planner app in TypeScript: schedule events with dates, show days-until and list upcoming events",
    "a password strength checker app in TypeScript: score passwords, flag weak patterns like repeats and short length",
]

MEDIUM5 = [
    "a text adventure game app in TypeScript: rooms with descriptions, items to take, move and look commands",
    "a meeting scheduler app in TypeScript: schedule meetings with start/end times and detect overlapping conflicts",
    "a stock portfolio tracker app in TypeScript: holdings with buy/sell transactions and computed profit/loss",
    "a voting poll app in TypeScript: create polls with options, cast votes, and show results with percentages",
    "a file organizer app in TypeScript: sort files into folders by extension with a dry-run preview",
]


def api(method, path, body, timeout=300):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def run_cycle(i, n, request):
    log(f"── {i}/{n} ── {request[:70]}")
    stp, pland = api("POST", "/api/reason/plan-code", {"request": request, "scale": "small"}, timeout=300)
    plan = (pland.get("plan") or {}) if isinstance(pland, dict) else {}
    pfiles = plan.get("files") or plan.get("contractFiles") or []
    if stp != 200 or not pfiles:
        log(f"  plan failed (status={stp}) — skipping")
        return
    answers = {}
    for qi, q in enumerate((plan.get("questions") or [])[:3]):
        key = q.get("key") if isinstance(q, dict) else f"q{qi + 1}"
        opts = q.get("options") if isinstance(q, dict) else None
        answers[key] = opts[0] if opts else "yes"
    log(f"  plan: {len(pfiles)} file(s), {len(plan.get('questions') or [])} question(s) — writing…")
    stw, wd = api("POST", "/api/reason/write-code",
                  {"request": request, "plan": plan, "answers": answers,
                   "libraryMode": "hybrid", "scale": "small"}, timeout=900)
    success = stw == 200 and isinstance(wd, dict) and wd.get("success")
    files = (wd or {}).get("files") or []
    classes = (wd or {}).get("tscClasses") or {}
    classes_s = f" classes={json.dumps(classes)}" if classes else ""
    log(f"write {i}/{n}: status={stw} success={success} tscErrors={(wd or {}).get('tscErrors')}"
        f" files={len(files)} mode={(wd or {}).get('mode')}{classes_s}")
    time.sleep(3)


def main():
    if "--tmux" in sys.argv:
        import os
        args = [a for a in sys.argv if a != "--tmux"]
        name = "orpo-seed"
        import subprocess
        subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
        cmd = f"{sys.executable} {os.path.abspath(__file__)} " + " ".join(args)
        subprocess.run(["tmux", "new-session", "-d", "-s", name,
                        f"{cmd} > {LOG} 2>&1; echo EXIT=$? >> {LOG}"])
        print(f"launched in tmux:{name} — tail -f {LOG}")
        return 0

    batches = []
    flags = ("--simple", "--medium", "--medium2", "--medium3", "--medium4", "--medium5")
    explicit = any(a in sys.argv for a in flags)
    if "--simple" in sys.argv or (not explicit and not any(a in sys.argv for a in ("--medium", "--medium2", "--medium3", "--medium4", "--medium5"))):
        batches.append(("VERY-SIMPLE", SIMPLE))
    if "--medium" in sys.argv or (not explicit and "--simple" not in sys.argv):
        batches.append(("MEDIUM", MEDIUM))
    if "--medium2" in sys.argv:
        batches.append(("MEDIUM-B", MEDIUM2))
    if "--medium3" in sys.argv:
        batches.append(("MEDIUM-C", MEDIUM3))
    if "--medium4" in sys.argv:
        batches.append(("MEDIUM-D", MEDIUM4))
    if "--medium5" in sys.argv:
        batches.append(("MEDIUM-E", MEDIUM5))

    total = sum(len(b) for _, b in batches)
    i = 0
    for label, reqs in batches:
        log(f"═══ BATCH: {label} ({len(reqs)}) ═══")
        for r in reqs:
            i += 1
            run_cycle(i, total, r)
    log(f"DONE — {total} writes. Next: python3 scripts/build-orpo-pairs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
