#!/usr/bin/env python3
"""
build-multifile-repair-pairs.py — fold IMPORT-BASED multi-file blueprint
repair examples into repair-pairs.jsonl.

WHY: the single-file-mode heritage (training outputs without imports, prompt
rule "DO NOT include import statements — the build adds them") taught the model
to write multi-file modules as if state were implicitly shared — the scope-leak
(TS2304/TS2451 `task`/`state` referenced as implicit globals across modules)
and invented-member (TS2339 `Task.push`) failure classes on blueprint builds.
When the repair loop DOES converge, the files come back with the correct
multi-file style: explicit sibling imports + member-whitelisted usage. Those
converged files are the training signal the corpus was missing.

This script pulls the LATEST verified blueprint capture for a goal's modules
from verified-generations.jsonl (the capture is already tsc-gated) and appends
the import-based files as repair-pair rows with a REPAIR directive that names
the failure class. Idempotent: (instruction, output) keys already present are
skipped.

Row format (mirrors build-repair-pairs.py):
  instruction: the original per-file generation instruction + the failure
               class the repair fixed + a repair directive.
  input:       ''
  output:      the converged file content.
  source:      'multi-file-repair:<goal>:<date>:<file>'
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPTURE_FILE = ROOT / "training" / "dataset" / "verified-generations.jsonl"
OUT_FILE = ROOT / "training" / "dataset" / "repair-pairs.jsonl"

# Goal → the module files whose converged form demonstrates the multi-file
# import style. Only files that carry sibling imports are folded (a file that
# converged to a self-contained no-import body teaches the OLD single-file
# habit, not the fix).
GOALS = {
    "a todo list app with tasks, due dates, and projects": {
        "goal_label": "todo_list",
        "import_files": ["input-handler.ts", "data-store.ts", "task-store.ts"],
    },
}

REPAIR_NOTE = (
    "\n\n⚠️ THE PREVIOUS VERSION OF THIS FILE FAILED TO COMPILE with the "
    "multi-file scope-leak / invented-member classes: it referenced state "
    "(`task`, `state`) as if it were a shared global and called members on "
    "guessed shapes. The corrected file below shows the FIX: import sibling "
    "modules explicitly and call ONLY the members they export. In multi-file "
    "apps there are NO implicit globals — every cross-module value is a "
    "function parameter, a return value, or an import."
)


def load_jsonl(path):
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def existing_keys(path):
    return {(r.get("instruction", ""), r.get("output", "")) for r in load_jsonl(path)}


def main():
    existing = existing_keys(OUT_FILE)
    captured = load_jsonl(CAPTURE_FILE)
    added = 0
    for goal, cfg in GOALS.items():
        want = set(cfg["import_files"])
        rows = [r for r in captured if goal in (r.get("instruction") or "") and (r.get("source") or "").startswith("blueprint-verified")]
        if not rows:
            print(f"[skip] no verified capture rows for goal: {goal}")
            continue
        # The last capture of each wanted file wins.
        by_file = {}
        for r in rows:
            for name in want:
                if f"Generate the COMPLETE file '{name}'" in (r.get("instruction") or ""):
                    by_file[name] = r
        for name in want:
            r = by_file.get(name)
            if not r:
                print(f"[skip] no capture for {name}")
                continue
            output = r.get("output") or ""
            if "import " not in output:
                print(f"[skip] {name} converged without imports — not a multi-file-style example")
                continue
            instruction = r.get("instruction", "") + REPAIR_NOTE
            source = f"multi-file-repair:{cfg['goal_label']}:{date.today().isoformat()}:{name}"
            if (instruction, output) in existing:
                print(f"[dup]  {name}")
                continue
            with OUT_FILE.open("a") as fh:
                fh.write(json.dumps({"instruction": instruction, "input": "", "output": output, "source": source}) + "\n")
            existing.add((instruction, output))
            added += 1
            print(f"[add]  {name} ({len(output)} chars) -> repair-pairs.jsonl")
    print(f"done: {added} row(s) added")


if __name__ == "__main__":
    sys.exit(main())
