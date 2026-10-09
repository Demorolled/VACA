#!/usr/bin/env python3
"""
build-repair-pairs.py — turn teacher-fixed sessions into REPAIR-PAIR training
rows (same {instruction, input, output, source} JSONL format as
verified-generations.jsonl).

WHY: the teacher loop (data/teacher/sessions/*.fixed.json + the /tmp fixed
files saved when patching) produced CORRECTED code for files the 14B got wrong.
Each fixed file is a supervised repair example: the model saw its own broken
output and learned the corrected pattern. Feeding those pairs back is how the
finetune learns the failure classes (scope leakage, DOM-string props,
self-recursion, truncation) instead of repeating them.

Row format (mirrors verified-generation rows):
  instruction: the same generation instruction the model saw, PLUS the errors
               that were found and a REPAIR directive.
  input:       ''
  output:      the teacher-fixed code.
  source:      'teacher-repair:seq-N:app-name'

Dedupe: (instruction, output) pairs already present are skipped, so re-runs
never duplicate rows.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = ROOT / "data" / "teacher" / "sessions"
OUT_FILE = ROOT / "training" / "dataset" / "repair-pairs.jsonl"

# Files the teacher patched that have NO .fixed.json dump (patched in /tmp):
# seq 8 = checkers, seq 9 = password generator. Map: fileName -> /tmp path.
TMP_FIXES = {
    8: {
        "render-view.ts": Path("/tmp/checkers-render-view-fixed.ts"),
        "game-controller.ts": Path("/tmp/checkers-game-controller-fixed.ts"),
    },
    9: {
        "user-interface.ts": Path("/tmp/pg-user-interface-fixed.ts"),
    },
}


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
    keys = set()
    for r in load_jsonl(path):
        keys.add((r.get("instruction", ""), r.get("output", "")))
    return keys


def instruction_for(project, file_name, node_label, errors):
    goal = project.get("name", "Untitled")
    master = None
    for n in project.get("nodes", []):
        if n.get("type") == "master":
            master = n.get("data", {})
    purpose = (master or {}).get("appPurpose", "")
    target_os = project.get("targetOS", "linux")
    planned = [f.get("fileName") for f in project.get("files", []) if f.get("fileName", "").endswith(".ts")]
    error_block = "\n".join(f"  - {e}" for e in errors[:12]) if errors else "  - (runtime failure — code compiled but crashed)"

    lines = [
        f"Project goal: {goal}",
        purpose and f"Project purpose: {purpose}",
        f"Target OS: {target_os}",
        "",
        "PLANNED FILES:",
        *[f"  - {p} (typescript)" for p in planned],
        "",
        f"Generate the COMPLETE file '{file_name}' for the multi-file app above.",
        node_label and f"Node: {node_label}",
        "Language: typescript",
        "",
        "Your previous version of this file FAILED verification with these errors:",
        error_block,
        "",
        "REPAIR the file: fix every error above so the file compiles cleanly and runs. "
        "Keep the same public API (exports) and the same overall structure — only fix what is broken. "
        "Return only the code, no markdown, no explanations.",
    ]
    return "\n".join(l for l in lines if l)


def emit(rows, key_set, project, file_name, node_label, errors, fixed_code, source_tag):
    instr = instruction_for(project, file_name, node_label, errors)
    if (instr, fixed_code) in key_set:
        return 0
    rows.append({
        "instruction": instr,
        "input": "",
        "output": fixed_code,
        "source": source_tag,
    })
    key_set.add((instr, fixed_code))
    return 1


def main():
    sessions = {r.get("seq"): r for r in load_jsonl(SESSIONS_DIR.parent / "sessions.jsonl")}
    existing = existing_keys(OUT_FILE)
    rows = []
    count = 0

    # ── 1. Sessions with .fixed.json dumps (seq 11 calculator, 12 stopwatch, 13 tip calc) ──
    for seq in [11, 12, 13]:
        fixed_path = SESSIONS_DIR / f"{seq}.fixed.json"
        orig_path = SESSIONS_DIR / f"{seq}.json"
        if not fixed_path.exists() or not orig_path.exists():
            continue
        fixed = json.loads(fixed_path.read_text())
        orig = json.loads(orig_path.read_text())
        project = fixed.get("project") or {}
        session = sessions.get(seq, {})
        errors_by_file = session.get("fileErrors", {}) or {}

        fixed_files = {f.get("fileName"): f for f in fixed.get("files", [])}
        orig_files = {f.get("fileName"): f for f in orig.get("files", [])}
        for name, ff in fixed_files.items():
            if not name.endswith(".ts"):
                continue
            of = orig_files.get(name)
            # Only emit rows for files the teacher actually changed.
            if of and of.get("code") == ff.get("code"):
                continue
            if not ff.get("code") or len(ff["code"]) < 80:
                continue
            errors = errors_by_file.get(name) or []
            if seq in TMP_FIXES:
                continue  # handled below with the real fixed file
            count += emit(
                rows, existing, project, name, ff.get("nodeLabel", ""), errors,
                ff["code"], f"teacher-repair:seq-{seq}:{project.get('name', 'app')}",
            )

    # ── 2. Sessions patched in /tmp (seq 8 checkers, seq 9 password gen) ──
    for seq, fixes in TMP_FIXES.items():
        orig_path = SESSIONS_DIR / f"{seq}.json"
        if not orig_path.exists():
            continue
        orig = json.loads(orig_path.read_text())
        project = orig.get("project") or {}
        session = sessions.get(seq, {})
        errors_by_file = session.get("fileErrors", {}) or {}
        node_by_file = {f.get("fileName"): f.get("nodeLabel", "") for f in orig.get("files", [])}
        for name, tmp_path in fixes.items():
            if not tmp_path.exists():
                print(f"  !! missing fixed file for seq {seq}: {name}")
                continue
            fixed_code = tmp_path.read_text()
            if len(fixed_code) < 80:
                continue
            count += emit(
                rows, existing, project, name, node_by_file.get(name, ""),
                errors_by_file.get(name) or [], fixed_code,
                f"teacher-repair:seq-{seq}:{project.get('name', 'app')}",
            )

    if rows:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUT_FILE.open("a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    print(f"repair-pairs: +{len(rows)} new rows (total in file: {len(existing) + len(rows)})")
    print(f"file: {OUT_FILE}")
    for r in rows:
        print(f"  - {r['source']}: {r['output'][:60]!r}...")


if __name__ == "__main__":
    main()
