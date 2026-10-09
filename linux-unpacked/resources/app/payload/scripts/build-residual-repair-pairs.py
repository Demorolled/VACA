#!/usr/bin/env python3
"""
build-residual-repair-pairs.py — fold RESIDUAL-ERROR writes into repair-pairs.

WHY: the capture gate only folds tsc-CLEAN exports (capture-verified-pairs.py),
so the failure classes the model still produces — TS2304 (missing name),
TS2451 (redeclared), TS2339 (wrong member on a type) — never reach training.
The harness now fixes the mechanical classes deterministically (content-driven
import insert + local-collision dedup + phantom strip) and records the residual
class breakdown in the sidecar (`tscClasses`); the files that STILL ship with
errors are the model's own best converged attempt AFTER those repairs, and the
instruction must tell the next fine-tune WHICH classes they are so it learns
the multi-file import/shape style instead of the harness fixing it forever.

Row format (mirrors build-repair-pairs.py):
  instruction: the original per-file generation instruction + the VERBATIM
               residual tsc errors + a repair directive naming the class.
  input:       ''
  output:      the file's final (post-repair) content — the model's best
               converged attempt; the instruction carries the errors so the
               LoRA learns "these error classes -> this repair style".
  source:      'residual-repair:<slug>:<date>:<file>'

Honest tagging: rows are written to a SEPARATE file
(training/dataset/residual-repair-pairs.jsonl) so the corpus builder can weight
them below verified pairs (their output is the best ATTEMPT, not proof-clean —
tsc re-runs per file and the error classes go in the instruction; files that
re-run CLEAN are folded into the verified file instead).

Usage:
  python3 scripts/build-residual-repair-pairs.py          # scan + fold
  python3 scripts/build-residual-repair-pairs.py --dry-run
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "backend" / "exports"
TSC = ROOT / "node_modules" / ".bin" / "tsc"
SIDECAR = "_training.json"
OUT_RESIDUAL = ROOT / "training" / "dataset" / "residual-repair-pairs.jsonl"
OUT_VERIFIED = ROOT / "training" / "dataset" / "repair-pairs.jsonl"

# Same per-file instruction prefix the verified builder uses: the request +
# the planned file list + "generate THIS file".
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

REPAIR_NOTE = (
    "\n\n⚠️ YOUR PREVIOUS VERSION OF THIS FILE FAILED TO COMPILE with these "
    "errors (the classes below are the exact residual classes recorded for "
    "this write). REPAIR the file: fix EVERY error above so the file compiles "
    "cleanly and runs, keeping the same public API (exports) and overall "
    "structure — only fix what is broken. In multi-file apps: every "
    "cross-module value must be imported from the sibling that exports it "
    "(no implicit globals), and you may call ONLY the members the imported "
    "type actually declares. Return only the code, no markdown, no "
    "explanations."
)

STUB_RE = re.compile(
    r"\bnot implemented\b|placeholder\s+for\b|\bcoming soon\b|\blorem ipsum\b|"
    r"TODO:\s*Implement|throw new Error\(['\"]not"
)
TS_ERR_RE = re.compile(r"error\s+(TS\d+)")

def run_tsc_export(export_dir, ts_files):
    """Re-run tsc on the WHOLE export dir (like the real gate — cross-file
    errors like TS2451 redeclares only surface when tsc sees every file
    together). Returns (errors_by_file, class_counts)."""
    abs_paths = [str(export_dir / f) for f in ts_files]
    if not abs_paths:
        return {}, {}
    p = subprocess.run(
        [str(TSC), "--noEmit", "--target", "ES2020", "--module", "ESNext",
         "--moduleResolution", "bundler", "--esModuleInterop", "--skipLibCheck",
         *abs_paths],
        capture_output=True, text=True, timeout=180,
    )
    errs = [l for l in (p.stderr or "").splitlines() if "error TS" in l and "TS5112" not in l]
    err_by_file = {}
    classes = {}
    for e in errs:
        m = TS_ERR_RE.search(e)
        if m:
            classes[m.group(1)] = classes.get(m.group(1), 0) + 1
        rel = e.split("(", 1)[0].strip()
        try:
            rel = str(Path(rel).resolve().relative_to(export_dir.resolve()))
        except ValueError:
            rel = Path(rel).name
        err_by_file.setdefault(rel, []).append(e)
    return err_by_file, classes

def main():
    dry = "--dry-run" in sys.argv
    if not EXPORTS.is_dir():
        print(f"❌ no exports dir at {EXPORTS}")
        return 1

    residual_rows, verified_rows = [], []
    seen_residual = {r["source"] for r in _load(OUT_RESIDUAL)}
    seen_verified = {r["source"] for r in _load(OUT_VERIFIED)}
    n_sidecars = n_residual = n_verified = 0

    for d in sorted(EXPORTS.iterdir()):
        sidecar_path = d / SIDECAR
        if not d.is_dir() or not sidecar_path.exists():
            continue
        n_sidecars += 1
        try:
            sc = json.loads(sidecar_path.read_text())
        except Exception:
            continue
        # Only writes that SHIPPED with errors (the residual class).
        if not (sc.get("tscErrors") or 0) > 0:
            continue
        files = sc.get("files") or []
        if not files:
            continue
        ts_files = [f for f in files if f.endswith((".ts", ".tsx")) and not STUB_RE.search(f)]
        err_by_file, classes = run_tsc_export(d, ts_files)
        for fpath in ts_files:
            src = d / fpath
            if not src.is_file():
                continue
            content = src.read_text(errors="replace")
            if len(content) < 80:
                continue
            errs = err_by_file.get(fpath) or []
            if not errs:
                # Re-runs clean now (the deterministic fixes landed AFTER the
                # write) — fold into the VERIFIED file, not residual.
                row = {
                    "instruction": per_file_instruction(sc, fpath) + REPAIR_NOTE,
                    "input": "",
                    "output": content,
                    "source": f"residual-repair:{d.name}:{date.today().isoformat()}:{fpath}",
                }
                if row["source"] not in seen_verified:
                    verified_rows.append(row)
                    seen_verified.add(row["source"])
                n_verified += 1
                continue
            class_line = ", ".join(f"{k} ({v})" for k, v in sorted(classes.items()))
            row = {
                "instruction": (
                    per_file_instruction(sc, fpath)
                    + "\n\nYour previous version of this file FAILED verification with these errors:\n"
                    + "\n".join(f"  - {e.strip()}" for e in errs[:8])
                    + REPAIR_NOTE
                    + f"\n\nRESIDUAL ERROR CLASSES: {class_line}"
                ),
                "input": "",
                "output": content,
                "source": f"residual-repair:{d.name}:{date.today().isoformat()}:{fpath}",
            }
            if row["source"] not in seen_residual:
                residual_rows.append(row)
                seen_residual.add(row["source"])
            n_residual += 1

    if dry:
        print(f"[dry-run] sidecars={n_sidecars} residual_rows={n_residual} verified_rows={n_verified}")
        return 0

    if residual_rows:
        with open(OUT_RESIDUAL, "a", encoding="utf-8") as f:
            for r in residual_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if verified_rows:
        with open(OUT_VERIFIED, "a", encoding="utf-8") as f:
            for r in verified_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"✅ residual-repair-pairs: {len(residual_rows)} new rows → {OUT_RESIDUAL.name}")
    print(f"   re-verified-clean: {len(verified_rows)} new rows → {OUT_VERIFIED.name}")
    return 0

def _load(p: Path):
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

if __name__ == "__main__":
    sys.exit(main())
