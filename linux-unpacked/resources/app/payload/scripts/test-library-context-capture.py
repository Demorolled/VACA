#!/usr/bin/env python3
"""
Synthetic test for the library-context capture pipeline (roadmap Phase 2b).
Verifies:
  1. A sidecar carrying `libraryContext` produces rows with input == that context
  2. Rows WITHOUT libraryContext keep input == ""
  3. Idempotency: re-running skips already-captured sidecars
  4. Quality filters still apply (stub file dropped, clean file captured)
"""
import json
import os
import shutil
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(BASE, "scripts", "capture-verified-pairs.py")
OUT = os.path.join(BASE, "training", "dataset", "captured-verified.jsonl")
EXPORTS = os.path.join(BASE, "backend", "exports")

ts = str(int(time.time()))

# Snapshot the production captured-verified.jsonl so this test can restore it
# in a finally block — the test is self-contained and can never leave rows or
# fixtures behind, even when an assertion fires mid-way.
OUT_TMP = OUT + ".test-snapshot"
if os.path.isfile(OUT):
    shutil.copy2(OUT, OUT_TMP)

ctx = (
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📚 REFERENCE LIBRARY — Architecture patterns, code gen rules, templates.\n"
    "── 📖 12-game-development-patterns — game loop, ECS, collision detection\n"
    "Fixed timestep loop, entity-component-system, spatial hashing.\n"
    "── 📜 Bible: 02 — Games — game development, rendering, game loop, physics\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "Use the reference library and Bible guides above when generating code."
)

# ── 1. Fixture: an export dir with a sidecar (WITH libraryContext) ──────
fixture = os.path.join(EXPORTS, f"__libctx-test-{ts}")
fixture2 = os.path.join(EXPORTS, f"__libctx-nocontext-{ts}")


def _run_all_assertions(fixture, fixture2, ctx, OUT_TMP):
    src = os.path.join(fixture, "src")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "timer.ts"), "w", encoding="utf-8") as f:
        f.write("export class Timer {\n  private seconds = 0;\n  start(): void { this.seconds = 1500; }\n  tick(): number { return ++this.seconds; }\n  reset(): void { this.seconds = 0; }\n}\n")
    with open(os.path.join(src, "stub.ts"), "w", encoding="utf-8") as f:
        f.write("// TODO: Implement the stub\nexport function stub(): string { return 'not implemented'; }\n")
    sidecar = {
        "version": 1, "createdAt": "2026-07-31T00:00:00Z",
        "request": "make a pomodoro timer",
        "intent": {"goal": "pomodoro timer", "targetUser": "", "coreFeatures": ["timing"], "uiStyle": "cli", "language": "typescript"},
        "questions": [{"key": "q1", "question": "Interface?", "options": ["CLI"]}],
        "answers": {"q1": "CLI"},
        "planFiles": [{"path": "src/timer.ts", "summary": "Countdown engine", "language": "typescript", "exports": ["Timer"]}],
        "mode": "one-shot", "repairRounds": 0, "tscErrors": 0,
        "libraryContext": ctx,
        "files": ["src/timer.ts", "src/stub.ts"],
    }
    with open(os.path.join(fixture, "_training.json"), "w", encoding="utf-8") as f:
        json.dump(sidecar, f)

    before = 0
    if os.path.isfile(OUT):
        with open(OUT, encoding="utf-8") as f:
            before = sum(1 for _ in f)

    # ── 2. Run capture ────────────────────────────────────────────────────
    r = subprocess.run([sys.executable, CAPTURE], capture_output=True, text=True, cwd=BASE)
    print(r.stdout)
    if r.returncode != 0:
        print("❌ capture failed:", r.stderr)
        sys.exit(1)

    with open(OUT, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    new_rows = rows[before:]

    assert len(new_rows) == 1, f"expected exactly 1 new row, got {len(new_rows)}"
    row = new_rows[0]
    assert row["input"] == ctx, f"input != libraryContext ({len(row['input'])} vs {len(ctx)} chars)"
    assert row["output"].startswith("export class Timer"), "clean file should be captured"
    assert row["source"] == "captured-verified", row["source"]
    print(f"✅ row 1: input == libraryContext ({len(row['input'])} chars), clean file captured")

    # ── 3. Idempotency re-run ─────────────────────────────────────────────
    r2 = subprocess.run([sys.executable, CAPTURE], capture_output=True, text=True, cwd=BASE)
    print(r2.stdout)
    assert "already-captured" in r2.stdout, "re-run should skip captured sidecar"
    with open(OUT, encoding="utf-8") as f:
        after = sum(1 for _ in f)
    assert after == before + 1, f"idempotency broken: {before + 1} != {after}"
    print("✅ idempotent: re-run skipped the captured sidecar, no duplicate rows")

    # ── 4. No-context fallback fixture ────────────────────────────────────
    os.makedirs(os.path.join(fixture2, "src"), exist_ok=True)
    with open(os.path.join(fixture2, "src", "note.ts"), "w", encoding="utf-8") as f:
        f.write("export class Note {\n  text = '';\n  title = '';\n  setText(t: string): void { this.text = t; }\n  setTitle(t: string): void { this.title = t; }\n  getPreview(): string { return this.title + ': ' + this.text; }\n  clear(): void { this.text = ''; this.title = ''; }\n}\n")
    sidecar2 = dict(sidecar)
    sidecar2.pop("libraryContext", None)
    sidecar2["files"] = ["src/note.ts"]
    sidecar2["planFiles"] = [{"path": "src/note.ts", "summary": "Note model", "language": "typescript", "exports": ["Note"]}]
    with open(os.path.join(fixture2, "_training.json"), "w", encoding="utf-8") as f:
        json.dump(sidecar2, f)

    r3 = subprocess.run([sys.executable, CAPTURE], capture_output=True, text=True, cwd=BASE)
    print(r3.stdout)
    with open(OUT, encoding="utf-8") as f:
        rows3 = [json.loads(l) for l in f if l.strip()]
    row3 = rows3[-1]
    assert row3["input"] == "", f"no-context sidecar should produce input='' (got {len(row3['input'])} chars)"
    print("✅ row without libraryContext keeps input == ''")


# ── Run + always-cleanup (try/finally so even a mid-script failure cleans up) ──
try:
    _run_all_assertions(fixture, fixture2, ctx, OUT_TMP)
finally:
    # Cleanup ALWAYS runs — even when an assertion fails mid-way, so the test
    # can never leave fixture dirs or appended rows behind.
    shutil.rmtree(fixture, ignore_errors=True)
    shutil.rmtree(fixture2, ignore_errors=True)
    if os.path.isfile(OUT_TMP):
        shutil.copy2(OUT_TMP, OUT)
        os.remove(OUT_TMP)
print("\n🎉 ALL LIBRARY-CONTEXT CAPTURE TESTS PASSED")
