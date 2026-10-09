#!/usr/bin/env python3
"""
distill-vaca.py — build the VACA file-recreation corpus (the "collected rows").
================================================================================
This is the producer half of the acceptance eval. It mines the repo's own
tsc-clean builds into a scored task file, so a model can be asked to recreate a
VACA file and graded on whether it PARSES and EXPORTS what the task declared.

One role (matching scripts/eval_acceptance.py):
  * completion — given a file's spec (path, summary, app plan, expected exports),
    output the file content. Scored by --role completion.

Where the rows come from
------------------------
Every export under backend/exports/<slug>/ was written by VACA itself and carries
a sidecar `_training.json` holding the plan:

    planFiles = [ {path, summary, language, exports:[...]}, ... ]
    files     = [ "<same paths>", ... ]   # paths only; content is on disk
    request   = the user's original build request

So each (planFile, on-disk file) pair is one collected row: a real spec plus the
real file that satisfies it. The file content is the GOLD.

Gold-authored targets
---------------------
By default the gold is the real file, verbatim. With `--teacher NAME=MODEL` the
gold is RE-AUTHORED by a stronger model (any OpenAI-compatible endpoint), which
is what "gold-authored targets" means for the distilled reasoning adapter. A
teacher call that fails falls back to the real file, so the corpus is never
empty on a flaky endpoint.

Held-out eval tasks
-------------------
The corpus keeps a deterministic 7-task HELD-OUT slice (ids written to
meta.json, never a teacher target the model could have memorised) for
scripts/eval_adapters.py, the older gold-similarity gate.

Outputs (under --out, default corpora/vaca/):
  tasks.txt      one line per task, the file eval_acceptance.py scores
  gold.jsonl     the same tasks + the gold file content
  meta.json      counts, held-out ids, source digest, format version

Usage:
  python3 scripts/distill-vaca.py                             # local build
  python3 scripts/distill-vaca.py --max-tasks 197 --held-out 7
  python3 scripts/distill-vaca.py --teacher g14=qwen2.5-coder:14b \
      --api http://192.168.1.234:11434/v1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # visual-ai-architect/
DEFAULT_EXPORTS = ROOT / "backend" / "exports"
DEFAULT_OUT = ROOT / "corpora" / "vaca"

CODE_EXTS = {"ts", "tsx", "js", "jsx", "mjs", "cjs"}
# Files the completion gate can actually type-check + export-check.
MAX_GOLD_BYTES = 64 * 1024              # skip monsters; a task must be answerable
FORMAT_VERSION = 1

# Local artifacts that may contain what the adapter trained on. The Training-Studio
# "sheets" are the model's OWN build outputs, so they are the strongest local leak
# signal. This is a PROXY: the adapter's actual training set lives on the agent box,
# so a clean pass here is necessary but not sufficient for true unseen-ness.
DEFAULT_LEAK_SOURCES = [
    ROOT / "llm-training-app" / "data" / "uploads",
    ROOT / "kaggle_upload" / "train.jsonl",
    ROOT / "kaggle_upload" / "val.jsonl",
    ROOT / "training" / "selfplay" / "corpus",
    ROOT / "training" / "unlearn" / "data",
]
LEAK_LINE_MIN = 20          # ignore trivial lines (braces, imports' tails) when hashing

# Same prefix eval_acceptance.py puts in front of every completion task line.
COMPLETION_PREFIX = "Recreate this file. Output the file content only.\n\n"


def _walk_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_strings(v)


def _sig_lines(text: str):
    """The significant lines of a blob: trimmed, long enough to be evidence, and
    not pure punctuation. Hashing these is how we detect reused code."""
    for raw in (text or "").splitlines():
        s = raw.strip()
        if len(s) < LEAK_LINE_MIN:
            continue
        if all(c in "}{)(;,.[]<>=" for c in s):
            continue
        yield s


def _hash(line: str) -> bytes:
    return hashlib.blake2b(line.encode("utf-8", "replace"), digest_size=8).digest()


def build_leak_index(sources) -> set:
    files = []
    for src in sources:
        p = Path(src).expanduser()
        if p.is_dir():
            files.extend(sorted(p.rglob("*.jsonl")))
        elif p.is_file():
            files.append(p)
    seen_lines = set()
    n_files = 0
    for fp in files:
        try:
            with fp.open(errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line[0] not in '{"[':
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    for s in _walk_strings(obj):
                        for ln in _sig_lines(s):
                            seen_lines.add(_hash(ln))
            n_files += 1
        except OSError:
            continue
    print(f"[distill] leak index: {len(seen_lines)} unique lines from {n_files} files")
    return seen_lines


def leak_fraction(gold: str, index: set) -> float:
    lines = list(_sig_lines(gold))
    if not lines or not index:
        return 0.0
    hit = sum(1 for ln in lines if _hash(ln) in index)
    return hit / len(lines)


def ext_of(path: str) -> str:
    m = re.search(r"\.([A-Za-z0-9]+)$", path or "")
    return m.group(1).lower() if m else ""


def slug_id(slug: str, path: str) -> str:
    """id= is [A-Za-z0-9_.-]+ in eval_acceptance.parse_task — build one safely."""
    raw = f"{slug}__{path}"
    return re.sub(r"[^A-Za-z0-9_.-]", "-", raw)


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_GOLD_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def iter_tasks(exports_dir: Path):
    """Yield one task dict per (planFile, on-disk file) with a real gold body."""
    for sidecar in sorted(exports_dir.glob("*/_training.json")):
        slug = sidecar.parent.name
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        plan = meta.get("planFiles") or []
        request = str(meta.get("request") or "").strip()
        # app plan = every path this app planned, for sibling coverage.
        plan_paths = [str(p.get("path") or "") for p in plan if p.get("path")]
        for p in plan:
            path = str(p.get("path") or "").strip()
            if not path:
                continue
            ext = ext_of(path)
            if ext not in CODE_EXTS:
                continue
            body = read_text(sidecar.parent / path)
            if not body or not body.strip():
                continue
            exports = [str(e) for e in (p.get("exports") or []) if e]
            yield {
                "id": slug_id(slug, path),
                "slug": slug,
                "file": path,
                "lang": "typescript" if ext in {"ts", "tsx"} else ext,
                "ext": ext,
                "exports": exports,
                "summary": str(p.get("summary") or "").strip(),
                "request": request,
                "app_plan": plan_paths,
                "gold": body,
            }


def dedup(tasks):
    """Collapse the same module shape copied across many builds.

    Keyed on (basename, exports signature, language): `src/notes.ts` exporting the
    same four functions from eight note-taking builds is ONE task, not eight.
    """
    seen = {}
    for t in tasks:
        base = t["file"].split("/")[-1]
        key = (base, tuple(sorted(t["exports"])), t["lang"])
        seen.setdefault(key, t)
    return list(seen.values())


def reserve_ids(tasks, held_out: int):
    """Deterministic evenly-spaced 7-task held-out slice from the sorted corpus."""
    ordered = sorted(tasks, key=lambda t: t["id"])
    n = len(ordered)
    if held_out <= 0 or n <= held_out:
        return [] , ordered
    idxs = [round(i * (n - 1) / (held_out - 1)) for i in range(held_out)] if held_out > 1 else [0]
    held = {idxs[i] for i in range(len(idxs))}
    held_ids = [ordered[i]["id"] for i in sorted(held)]
    return held_ids, ordered


def sample(tasks, max_tasks: int):
    """Evenly-spaced deterministic subsample down to max_tasks."""
    ordered = sorted(tasks, key=lambda t: t["id"])
    if max_tasks <= 0 or len(ordered) <= max_tasks:
        return ordered
    idxs = [round(i * (len(ordered) - 1) / (max_tasks - 1)) for i in range(max_tasks)]
    return [ordered[i] for i in sorted(set(idxs))]


def render_line(t: dict) -> str:
    """One task line. Order is chosen so every eval_acceptance regex terminates on
    a `|` and the plan never swallows the exports:

        id=.. file=.. lang=.. | app plan: .. | expected exports: .. | task: ..
    """
    parts = [f"id={t['id']} file={t['file']} lang={t['lang']}"]
    if t.get("app_plan"):
        parts.append("app plan: " + ", ".join(t["app_plan"]))
    if t.get("exports"):
        parts.append("expected exports: " + ", ".join(t["exports"]))
    desc = t.get("request") or "a VACA app"
    if t.get("summary"):
        desc = f"{desc} :: {t['summary']}"
    parts.append("task: " + desc)
    return " | ".join(parts)


def ask_teacher(api: str, model: str, prompt: str, max_tokens: int = 1200,
                timeout: int = 600) -> str | None:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(api.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read())
        return (j["choices"][0]["message"]["content"] or "").strip() or None
    except Exception as e:  # noqa: BLE001
        print(f"[distill] teacher failed for one row: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", default=str(DEFAULT_EXPORTS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--max-tasks", type=int, default=197,
                    help="cap the corpus (0 = keep all). 197 matches the upstream corpus.")
    ap.add_argument("--held-out", type=int, default=7)
    ap.add_argument("--teacher", default=None, metavar="NAME=MODEL",
                    help="re-author gold with a stronger model (OpenAI-compatible).")
    ap.add_argument("--api", default="http://192.168.1.234:11434/v1")
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--decontaminate", action="store_true",
                    help="drop tasks whose gold overlaps local training artifacts.")
    ap.add_argument("--decon", action="append", default=None, metavar="PATH",
                    help="extra jsonl file/dir to index for leakage (repeatable).")
    ap.add_argument("--leak-threshold", type=float, default=0.2,
                    help="drop a task when this fraction of its lines are seen (default 0.2: "
                         "conservative — 0.1 drops 39%% of shapes, 0.3 drops 15%%, 0.5 drops 10%%).")
    args = ap.parse_args()

    exports_dir = Path(args.exports).expanduser()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not exports_dir.is_dir():
        print(f"[distill] ABORT: no exports dir {exports_dir}", file=sys.stderr)
        return 1

    raw = list(iter_tasks(exports_dir))
    tasks = dedup(raw)
    print(f"[distill] {len(raw)} file rows from {exports_dir} → {len(tasks)} unique module shapes")

    leak_report = {}
    if args.decontaminate:
        sources = list(args.decon) if args.decon else [str(p) for p in DEFAULT_LEAK_SOURCES]
        index = build_leak_index(sources)
        keep, drop = [], []
        for t in tasks:
            fr = leak_fraction(t["gold"], index)
            (drop if fr >= args.leak_threshold else keep).append((fr, t))
        drop.sort(key=lambda x: -x[0])
        leak_report = {t["id"]: round(fr, 3) for fr, t in drop}
        print(f"[distill] decontaminate: dropped {len(drop)}/{len(tasks)} "
              f"(overlap >= {args.leak_threshold}), kept {len(keep)}")
        tasks = [t for _, t in keep]

    tasks = sample(tasks, args.max_tasks)
    held_ids, ordered = reserve_ids(tasks, args.held_out)  # ordered==sorted tasks
    print(f"[distill] corpus: {len(tasks)} tasks, {len(held_ids)} held-out ({len(raw)} raw)")

    teacher_name, teacher_model = (None, None)
    if args.teacher:
        if "=" not in args.teacher:
            print("[distill] ABORT: --teacher needs NAME=MODEL", file=sys.stderr)
            return 1
        teacher_name, teacher_model = args.teacher.split("=", 1)

    t0 = time.time()
    gold_rows = []
    for i, t in enumerate(ordered):
        gold = t["gold"]
        if teacher_model:
            prompt = COMPLETION_PREFIX + render_line(t)[:3000]
            out = ask_teacher(args.api, teacher_model, prompt, args.max_tokens)
            if out:
                gold = out
        gold_rows.append({
            "id": t["id"], "file": t["file"], "lang": t["lang"], "ext": t["ext"],
            "expected_exports": t["exports"], "app_plan": t["app_plan"],
            "summary": t["summary"], "request": t["request"], "slug": t["slug"],
            "held_out": t["id"] in held_ids,
            "gold": gold,
        })
        if (i + 1) % 25 == 0:
            print(f"[distill]   {i + 1}/{len(ordered)} ({time.time() - t0:.0f}s)")

    tasks_path = out_dir / "tasks.txt"
    with tasks_path.open("w", encoding="utf-8") as f:
        for t in ordered:
            f.write(render_line(t) + "\n")
    gold_path = out_dir / "gold.jsonl"
    with gold_path.open("w", encoding="utf-8") as f:
        for r in gold_rows:
            f.write(json.dumps(r) + "\n")

    digest = hashlib.sha256(tasks_path.read_bytes()).hexdigest()[:16]
    if leak_report:
        (out_dir / "leak_report.json").write_text(
            json.dumps(leak_report, indent=2) + "\n", encoding="utf-8")

    meta = {
        "version": FORMAT_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "exports_dir": str(exports_dir),
        "rows_raw": len(raw),
        "n_tasks": len(tasks),
        "held_out_ids": held_ids,
        "decontaminated": bool(args.decontaminate),
        "leak_threshold": args.leak_threshold,
        "n_dropped_leak": len(leak_report),
        "teacher": teacher_name,
        "teacher_model": teacher_model,
        "tasks_sha256_16": digest,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"[distill] wrote {tasks_path} ({len(tasks)} lines), {gold_path}, meta.json")
    print(f"[distill] held-out: {', '.join(held_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
