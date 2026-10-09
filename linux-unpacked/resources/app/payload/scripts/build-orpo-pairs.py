#!/usr/bin/env python3
"""
build-orpo-pairs.py — build ORPO preference pairs from first-draft snapshots.

The write paths now snapshot every .ts/.tsx file's FIRST draft into
`backend/exports/<slug>/_first-drafts/<path>` BEFORE the tsc gate + repair loop
mutates it. The final file ships tsc-clean; the snapshot is the model's own
BROKEN first attempt. That is a genuine (chosen, rejected) preference pair from
the model's own work — the data an ORPO/DPO round needs:

    instruction: per-file generation instruction (from the sidecar)
    chosen:      final file content (tsc-clean — the survivor)
    rejected:    first-draft snapshot (the model's original, usually broken)

Only pairs where the draft DIFFERS from the final are emitted (a file that
passed first try has no rejected side — the pair is trivially identical and
teaches nothing). Pairs where the final file does NOT re-run tsc-clean are
skipped (the "chosen" side must be verified, mirroring the capture gate).

Usage:
  python3 scripts/build-orpo-pairs.py            # scan exports, write pairs
  python3 scripts/build-orpo-pairs.py --dry-run  # report only
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "backend" / "exports"
TSC = ROOT / "node_modules" / ".bin" / "tsc"
SIDECAR = "_training.json"
DRAFTS = "_first-drafts"
OUT = ROOT / "training" / "dataset" / "orpo-pairs.jsonl"

STUB_RE = re.compile(
    r"\bnot implemented\b|placeholder\s+for\b|\bcoming soon\b|\blorem ipsum\b|"
    r"TODO:\s*Implement|throw new Error\(['\"]not"
)


def per_file_instruction(sidecar, fpath):
    req = sidecar.get("request") or "(no request)"
    plan = sidecar.get("planFiles") or []
    plan_block = "\n".join(
        f"  - {p.get('path')} ({p.get('language') or '?'})" for p in plan
    ) if plan else "(no plan)"
    lang = next((p.get("language") for p in plan if p.get("path") == fpath), "typescript")
    return (
        f"Project goal: {req}\n"
        f"PLANNED FILES:\n{plan_block}\n"
        f"Generate the COMPLETE file '{fpath}' for the multi-file app above.\n"
        f"Language: {lang}"
    )


def run_tsc(export_dir, ts_files):
    abs_paths = [str(export_dir / f) for f in ts_files]
    if not abs_paths:
        return True
    p = subprocess.run(
        [str(TSC), "--noEmit", "--target", "ES2020", "--module", "ESNext",
         "--moduleResolution", "bundler", "--esModuleInterop", "--skipLibCheck",
         *abs_paths],
        capture_output=True, text=True, timeout=180,
    )
    errs = [l for l in (p.stderr or "").splitlines() if "error TS" in l and "TS5112" not in l]
    return len(errs) == 0


def main():
    dry = "--dry-run" in sys.argv
    if not EXPORTS.is_dir():
        print(f"❌ no exports dir at {EXPORTS}")
        return 1

    rows = []
    seen = {r["source"] for r in _load(OUT)}
    n_exports = n_pairs = n_skipped = 0

    for d in sorted(EXPORTS.iterdir()):
        sidecar_path = d / SIDECAR
        drafts = d / DRAFTS
        if not d.is_dir() or not sidecar_path.exists() or not drafts.is_dir():
            continue
        n_exports += 1
        try:
            sc = json.loads(sidecar_path.read_text())
        except Exception:
            continue
        final_files = [f for f in (sc.get("files") or []) if f.endswith((".ts", ".tsx")) and not STUB_RE.search(f)]
        if not final_files:
            continue
        # The chosen side must be verified clean (mirror the capture gate).
        if not run_tsc(d, final_files):
            n_skipped += 1
            continue
        for fpath in final_files:
            draft = drafts / fpath
            final = d / fpath
            if not draft.is_file() or not final.is_file():
                continue
            rejected = draft.read_text(errors="replace")
            chosen = final.read_text(errors="replace")
            if rejected == chosen:
                continue  # passed first try — no rejected side, nothing to learn
            if len(chosen) < 80 or len(rejected) < 80:
                continue
            row = {
                "instruction": per_file_instruction(sc, fpath),
                "chosen": chosen,
                "rejected": rejected,
                "source": f"orpo:{d.name}:{fpath}",
            }
            if row["source"] not in seen:
                rows.append(row)
                seen.add(row["source"])
            n_pairs += 1

    if dry:
        print(f"[dry-run] exports_with_drafts={n_exports} pairs={n_pairs} "
              f"skipped(unclean-final)={n_skipped} new_rows={len(rows)}")
        return 0

    if rows:
        with open(OUT, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"✅ orpo-pairs: {len(rows)} new pairs → {OUT.name} "
          f"(total {len(_load(OUT))}); skipped {n_skipped} export(s) with unclean finals")
    return 0


def _load(p: Path):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


if __name__ == "__main__":
    sys.exit(main())
