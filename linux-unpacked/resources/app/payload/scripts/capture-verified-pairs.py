#!/usr/bin/env python3
"""
Capture verified exports → training pairs (roadmap Phase 2)
=============================================================
Every write-code / interactive generation drops a `_training.json` sidecar next
to its export dir (request + intent + questions/answers + plan). This script is
the GATE: it only converts exports that compile cleanly (tsc --noEmit with zero
errors) into training rows, so the dataset learns from WORKING code — exactly
the format the model needs to learn both understanding and generation.

Per-file rows (mirrors campaign50-corrected.jsonl):
  {"instruction": ..., "input": <library context>, "output": <file code>, "source": "captured-verified"}
The instruction embeds the request + intent + the user's answers + the planned
file list (so cross-file import targets are known) and asks for THAT file. When
the sidecar carries a `libraryContext` (the reference-library block the write
prompt actually retrieved for this request), it goes into the row's `input`
field — the trainer concatenates `instruction\n\n<input>` into the user message,
so the LoRA learns to generate code conditioned on the retrieved library.

Quality filters (mirror export-corrected-builds-to-training.py):
  - Only .ts/.tsx files can be tsc-gated — HTML/CSS/JS exports are skipped
  - Skip non-source files (README, package.json, tsconfig, *.md, *.html)
  - Skip stubs (not implemented / placeholder / TODO: Implement ...)
  - Skip JSX-in-.ts and markdown-prose lines (the TS1005 / TS1434 failure modes)
  - Skip tiny files (< 80 chars)

Idempotent: a sidecar with a `capturedAt` timestamp is skipped on re-runs.

Usage:
  python3 scripts/capture-verified-pairs.py             # scan + capture
  python3 scripts/capture-verified-pairs.py --dry-run   # report only, no writes
"""

import collections
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORTS = os.path.join(BASE, "backend", "exports")
OUT = os.path.join(BASE, "training", "dataset", "captured-verified.jsonl")
TSC = os.path.join(BASE, "node_modules", ".bin", "tsc")
SIDECAR = "_training.json"

STUB_PATTERNS = [
    r"\bnot implemented\b", r"placeholder\s+for\b", r"\bcoming soon\b",
    r"\blorem ipsum\b", r"\bunimplemented\b",
    r"throw new Error\(['\"]not", r"TODO:\s*Implement",
]

# JSX-in-ts: opening tags with attributes (<div className="x">) and closing tags
# (</div>) — NOT generics like Promise<Foo> (no whitespace after the tag name).
JSX_RE = re.compile(r"</?[a-z][a-z0-9]*\s[^>]*>|</[a-z][a-z0-9]*\s*>")

# Prose lines that break tsc (TS1434/TS1435) — markdown bullets, bold, notes
PROSE_RE = re.compile(r"^\s*(?:\*\*[^*]+\*\*|[-*]\s+[A-Za-z]|Note:|NOTE:|> |Explanation:|Here's|Below is|The .* (?:function|class|module))")

SKIP_RE = re.compile(r"(README|\.gitignore|package\.json|tsconfig|\.md$|\.html$|__init__\.py$|_training\.json$)")


def is_safe_rel(f: str) -> bool:
    """Reject absolute paths and anything that escapes the export dir (../x)."""
    return bool(f) and not os.path.isabs(f) and ".." not in f.split("/")


def core_features_list(v):
    """Accept an array OR a comma string (direct API callers may send the latter)."""
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return v if isinstance(v, list) else []


def is_stub(code: str) -> bool:
    return any(re.search(p, code, re.I) for p in STUB_PATTERNS)


def has_jsx_in_ts(code: str) -> bool:
    stripped = re.sub(r"(['\"`])(?:\\.|(?!\1)[^\\])*\1", "", code)
    return bool(JSX_RE.search(stripped))


def has_prose(code: str) -> bool:
    for line in code.split("\n"):
        t = line.strip()
        if not t:
            continue
        if PROSE_RE.match(line) and not re.search(r"[;{}()=<>]", t):
            return True
    return False


def tsc_check(export_dir: str, ts_files: list) -> list:
    """Return tsc error lines; [] = clean; None = could not verify (skip)."""
    if not ts_files:
        return []
    if not os.path.isfile(TSC):
        return None
    cmd = [TSC, "--noEmit", "--target", "ES2020", "--module", "ESNext",
           "--moduleResolution", "bundler", "--skipLibCheck"] + \
          [os.path.join(export_dir, f) for f in ts_files]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except Exception:
        return None
    return [ln for ln in r.stdout.splitlines() if "error TS" in ln]


def build_instruction(sidecar: dict, f: dict) -> str:
    request = sidecar.get("request", "")
    intent = sidecar.get("intent") or {}
    answers = sidecar.get("answers") or {}
    questions = sidecar.get("questions") or []
    plan_files = sidecar.get("planFiles") or []

    lines = [f"User request: {request}"]
    iv = []
    if intent.get("goal"):
        iv.append(f"Goal: {intent['goal']}")
    if intent.get("targetUser"):
        iv.append(f"Target user: {intent['targetUser']}")
    cf = core_features_list(intent.get("coreFeatures"))
    if cf:
        iv.append(f"Core features: {', '.join(cf)}")
    if intent.get("uiStyle"):
        iv.append(f"UI style: {intent['uiStyle']}")
    if intent.get("language"):
        iv.append(f"Language: {intent['language']}")
    if iv:
        lines.append("UNDERSTOOD INTENT: " + " | ".join(iv))
    if answers:
        qmap = {q.get("key"): q.get("question") for q in questions}
        lines.append("USER ANSWERS: " + "; ".join(
            f"{qmap.get(k, k)} → {v}" for k, v in answers.items()))
    if plan_files:
        lines.append("PLANNED FILES:")
        for pf in plan_files:
            lines.append(f"  - {pf.get('path')} ({pf.get('language') or '?'}) — {pf.get('summary') or ''}")
    lines.append("")
    lines.append(f"Generate the COMPLETE file '{f.get('path')}' for the multi-file app above.")
    if f.get("summary"):
        lines.append(f"Purpose: {f['summary']}")
    lang = f.get("language") or intent.get("language") or "typescript"
    lines.append(f"Language: {lang}")
    lines.append("Write production-quality, working code. Honor the plan: you may ONLY import "
                 "members the other planned files declare (the PLANNED FILES above are the import "
                 "targets). NO JSX in .ts files. NO placeholders, NO stubs, NO TODO comments. "
                 "Return only the code — no markdown, no explanations.")
    return "\n".join(lines)


def main() -> int:
    dry = "--dry-run" in sys.argv
    if not os.path.isdir(EXPORTS):
        print("No exports dir found:", EXPORTS)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    skipped = collections.Counter()
    captured_rows = 0
    captured_exports = 0
    dry_rows = 0

    for entry in sorted(os.listdir(EXPORTS)):
        export_dir = os.path.join(EXPORTS, entry)
        sidecar_path = os.path.join(export_dir, SIDECAR)
        if not os.path.isfile(sidecar_path):
            continue  # pre-sidecar exports (or non-export dirs)
        try:
            with open(sidecar_path, encoding="utf-8") as fh:
                sidecar = json.load(fh)
        except Exception:
            skipped["unreadable-sidecar"] += 1
            continue

        if sidecar.get("capturedAt"):
            skipped["already-captured"] += 1
            continue

        files = sidecar.get("files") or []
        safe_files = [f for f in files if is_safe_rel(f)]
        if len(safe_files) != len(files):
            skipped["unsafe-path"] += len(files) - len(safe_files)
        files = safe_files
        ts_files = [f for f in files if f.endswith((".ts", ".tsx"))]
        if not ts_files:
            skipped["no-ts"] += 1
            continue

        errs = tsc_check(export_dir, ts_files)
        if errs is None:
            skipped["tsc-unavailable"] += 1
            continue
        if errs:
            # NOT marked captured — re-run after the user fixes the export re-checks it.
            skipped["tsc-failed"] += 1
            print(f"  ⚠️ {entry}: {len(errs)} tsc error(s) — skipped (fix the export, re-run to capture)")
            continue

        rows = []
        for f in files:
            if not f.endswith((".ts", ".tsx")):
                continue
            if SKIP_RE.search(f):
                skipped["non-source"] += 1
                continue
            rel = f
            path = os.path.join(export_dir, rel)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    code = fh.read()
            except Exception:
                skipped["unreadable"] += 1
                continue
            if len(code.strip()) < 80:
                skipped["tiny"] += 1
                continue
            if is_stub(code):
                skipped["stub"] += 1
                continue
            if has_jsx_in_ts(code):
                skipped["jsx-in-ts"] += 1
                continue
            if has_prose(code):
                skipped["prose"] += 1
                continue
            summary = ""
            for pf in sidecar.get("planFiles") or []:
                if pf.get("path") == f:
                    summary = pf.get("summary") or ""
                    break
            lib_ctx = sidecar.get("libraryContext")
            rows.append({
                "instruction": build_instruction(sidecar, {"path": f, "summary": summary}),
                "input": lib_ctx if isinstance(lib_ctx, str) and lib_ctx.strip() else "",
                "output": code,
                "source": "captured-verified",
            })

        if not rows:
            skipped["no-usable-files"] += 1
            continue

        if dry:
            dry_rows += len(rows)
            captured_exports += 1
            print(f"  [dry] {entry}: would capture {len(rows)} file(s)")
            continue

        with open(OUT, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        sidecar["status"] = "captured"
        sidecar["capturedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        sidecar["capturedRows"] = len(rows)
        with open(sidecar_path, "w", encoding="utf-8") as fh:
            json.dump(sidecar, fh, indent=2, ensure_ascii=False)
        captured_rows += len(rows)
        captured_exports += 1
        print(f"  ✅ {entry}: captured {len(rows)} file(s)")

    print()
    print(f"{'[dry-run] ' if dry else ''}Captured: {dry_rows if dry else captured_rows} row(s) from "
          f"{captured_exports} export(s) → {OUT}")
    print(f"   Skipped: {dict(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
