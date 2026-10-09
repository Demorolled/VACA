#!/usr/bin/env python3
"""
build-r16-antifence-corpus.py — R16 clean-corpus builder
========================================================
Round 15 (the DEPLOYED model) resumed from the R14 adapter, whose training
lineage (rounds 10-14, all run on Kaggle) contains rows whose OUTPUT is the
markdown-fenced / batched / prose-wrapped chat format ("# ===== index.html ====="
plus ``` fences). Those rows taught the model to emit fences + multi-file
batches into what should be raw source files — the exact failure signature in
input.ts / cheese.ts / todo-app/.

R16 is the remediation round: EVERY row is passed through the same poison gate
the VACA app now uses (markdown fences, `---` separators, prompt artifacts,
prose explanations, stubs), and only CLEAN rows are kept. The clean rows from
rounds 10-14 become NEW signal (their fence-free form was never trained), the
clean verified-generations.jsonl (tsc-gated) is added, and round-15's own clean
rows are re-exposed as retention. Resuming from the R15 adapter, this teaches
"raw code only" without retraining on any poisoned content.

Outputs (deterministic, seed 42, 90/10):
  training/cloud/round16-antifence-all.jsonl / -train.jsonl / -val.jsonl
  training/cloud/round16-antifence.meta.json
  training/cloud/round16-antifence.zip   (Kaggle upload bundle)

Usage: python3 scripts/build-r16-antifence-corpus.py
"""
import hashlib
import json
import random
import re
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud"
SEED = 42

# ─── The poison gate (mirror of backend qualityGate.ts isQualityCode) ───────
FENCE_RE = re.compile(r"^\s*```", re.M)
SEP_RE = re.compile(r"^\s*---\s*$", re.M)
ARTIFACT_RE = re.compile(
    r"REAL FILE CONTENT|injected by the platform|generated for the \"[^\"]+\" node|entry point for the node", re.I
)
PROSE_RE = re.compile(
    r"^\s*(?:\*\*[^*]+\*\*|[-*]\s+[A-Za-z]|Note:|NOTE:|> |Explanation:|Here.s|Below is|"
    r"In this (?:solution|implementation|file|module|example)|"
    r"This (?:code|file|module|implementation|class|function) (?:defines|implements|handles|provides|is|shows)|"
    r"For (?:a|an) .* (?:game|app|application)|The .* (?:function|class|module|implementation))"
)
STUB_RE = re.compile(
    r"not implemented|placeholder\s+for|coming soon|lorem ipsum|unimplemented|throw new Error\(['\"]not|TODO: Implement", re.I
)
MIN_OUTPUT_CHARS = 30


def gate(text: str) -> str | None:
    """Return the reason the OUTPUT is poisoned, or None if clean."""
    if len(text.strip()) < MIN_OUTPUT_CHARS:
        return "too-short"
    if FENCE_RE.search(text):
        return "markdown-fence"
    if SEP_RE.search(text):
        return "separator"
    if ARTIFACT_RE.search(text):
        return "prompt-artifact"
    if STUB_RE.search(text):
        return "stub"
    for line in text.split("\n"):
        t = line.strip()
        if PROSE_RE.search(line) and not re.search(r"[;{}()=<>]", t):
            return "prose"
    return None


# Sources: every round-10-15 dataset + the tsc-gated verified captures.
# tag -> (path, re-expose?)
#
# CRITICAL semantics for R16: rounds 10-14 were trained in their FENCED form.
# Their CLEAN (unfenced) form was NEVER trained — so every row that passes the
# gate is NEW signal, and must NOT be deduped against the trained union (which
# only contains the poisoned versions). Dedupe is in-corpus only (a row can't
# appear twice in R16). Round-15 rows were already trained clean — re-expose.
SOURCES = [
    # Round 10 (GUI) + round 11 (mix-a): the heavily-fenced rounds.
    (OUT / "gui-combined-all.jsonl", "r16:gui-r10-clean", False),
    (OUT / "round11-mixa-all.jsonl", "r16:r11-clean", False),
    (OUT / "round12-defects-all.jsonl", "r16:r12-clean", False),
    (OUT / "round13-random-all.jsonl", "r16:r13-clean", False),
    (OUT / "round14-genfix-all.jsonl", "r16:r14-clean", False),
    # Round 15 was already clean — re-expose as retention so the model keeps
    # the GUI/3D breadth it just learned.
    (OUT / "round15-gui-all.jsonl", "r16:r15-retention", True),
    # The tsc-gated verified path — the only capture that was always clean.
    (ROOT / "training" / "dataset" / "verified-generations.jsonl", "r16:verified", False),
    # Curated repair-pair rows (built from the actual triage failures).
    (ROOT / "training" / "dataset" / "vaca-build-fixes.jsonl", "r16:build-fixes", False),
]

# Seq budget guard (kernel max_seq_length, must match the R15 notebook config).
MAX_SEQ = 3072
TOKEN_CHARS = 3.1
BUDGET_TOKENS = MAX_SEQ - 90


def est_tokens(text: str) -> int:
    return int(len(text) // TOKEN_CHARS) + 1


def fit_row(r: dict) -> dict:
    """Trim so instruction+input+output fit MAX_SEQ tokens (never the output)."""
    out = r.get("output", "")
    out_t = est_tokens(out)

    def fits(ins, inp):
        return out_t + est_tokens(ins) + est_tokens(inp) <= BUDGET_TOKENS

    if fits(r.get("instruction", ""), r.get("input", "") or ""):
        return r
    for frac in (0.75, 0.50, 0.25, 0.0):
        if fits(r.get("instruction", ""), (r.get("input", "") or "")[: int(len(r.get("input", "") or "") * frac)]):
            r["input"] = (r.get("input", "") or "")[: int(len(r.get("input", "") or "") * frac)]
            return r
    for frac in (0.75, 0.50, 0.25, 0.0):
        if fits(r.get("instruction", "")[: int(len(r.get("instruction", "")) * frac)], ""):
            r["instruction"] = r.get("instruction", "")[: int(len(r.get("instruction", "")) * frac)]
            r["input"] = ""
            return r
    return r


def row_key(r: dict) -> str:
    return hashlib.md5(
        f"{r.get('instruction', '')}|{r.get('input', '')}|{r.get('output', '')}".encode()
    ).hexdigest()


def load(path: Path):
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def main():
    print("[r16-antifence] NO trained-union dedupe — rounds 10-14 were trained in "
          "fenced form only; their clean form is NEW signal. Dedupe is in-corpus.")
    merged = []
    seen = set()
    src_counts = Counter()
    gate_counts = Counter()
    per_source = {}

    for path, tag, re_expose in SOURCES:
        rows = load(path)
        kept = dropped = 0
        dropped_reasons = Counter()
        for r in rows:
            out = r.get("output", "")
            why = gate(out)
            if why:
                dropped += 1
                dropped_reasons[why] += 1
                continue
            k = row_key(r)
            # In-corpus dedupe only: R16 must not repeat a row within itself.
            if k in seen:
                dropped += 1
                dropped_reasons["duplicate"] += 1
                continue
            seen.add(k)
            r["source"] = tag
            merged.append(r)
            kept += 1
        src_counts[path.name] = kept
        per_source[path.name] = {"total": len(rows), "kept": kept, "dropped": dropped, "reasons": dict(dropped_reasons)}
        print(f"  {path.name}: {len(rows)} rows → kept {kept}, dropped {dropped} {dict(dropped_reasons)}")
        gate_counts.update(dropped_reasons)

    print(f"\n[r16-antifence] total poison rejected across corpus: {dict(gate_counts)}")
    print(f"[r16-antifence] merged: {len(merged)} CLEAN rows")

    # Seq budget guard
    trimmed = 0
    for r in merged:
        before = est_tokens(r.get("output", "")) + est_tokens(r.get("instruction", "")) + est_tokens(r.get("input", "") or "")
        fit_row(r)
        after = est_tokens(r.get("output", "")) + est_tokens(r.get("instruction", "")) + est_tokens(r.get("input", "") or "")
        if after < before:
            trimmed += 1
    print(f"[r16-antifence] budget guard: {trimmed}/{len(merged)} rows input-trimmed to fit seq {MAX_SEQ}")

    rng = random.Random(SEED)
    rng.shuffle(merged)
    n_val = max(1, round(len(merged) * 0.10))
    val, train = merged[:n_val], merged[n_val:]

    out_all = OUT / "round16-antifence-all.jsonl"
    out_train = OUT / "round16-antifence-train.jsonl"
    out_val = OUT / "round16-antifence-val.jsonl"
    out_meta = OUT / "round16-antifence.meta.json"
    out_zip = OUT / "round16-antifence.zip"
    for path, rows in [(out_all, merged), (out_train, train), (out_val, val)]:
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    steps = (len(train) // 4) * 3
    meta = {
        "generated": "2026-08-13",
        "round": 16,
        "mix": "antifence-clean",
        "purpose": "REMEDIATION: clean-only corpus (no markdown fences / separators / prose / stubs in output). "
                   "Rounds 10-14 (R15's lineage) trained on fenced chat-format output; R16 re-teaches raw-code output.",
        "total_rows": len(merged),
        "by_source": dict(src_counts),
        "per_source": per_source,
        "poison_rejected": dict(gate_counts),
        "split": {"train": len(train), "val": len(val), "seed": SEED},
        "seq_budget": {"max_seq": MAX_SEQ, "rows_input_trimmed": trimmed},
        "kernel_config": {
            "epochs": 3, "grad_accum": 4, "seq": 3072, "lr": 5e-5,
            "optimizer_steps": steps,
            "resume_from": "vaca-r15-adapter (R15 trained LoRA, chained)",
        },
        "projected_t4_time": f"~{steps * 45 / 60:.1f} h ({steps} steps @ ~45 s/step)",
        "note": "Every row's output passed the VACA isQualityCode gate. Clean rows from R10-R14 are NEW signal "
                "(fence-free form never trained); R15 rows are retention re-exposure; verified-generations is the "
                "always-clean tsc-gated capture.",
    }
    (OUT / "round16-antifence.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out_train, arcname=out_train.name)
    print(f"[r16-antifence] wrote {out_all.name} ({out_all.stat().st_size} B), train {len(train)} / val {len(val)}")
    print(f"[r16-antifence] meta + zip: {out_meta.name}, {out_zip.name}")
    print(f"[r16-antifence] kernel: {steps} optimizer steps ≈ {steps * 45 / 60:.0f} min @ seq 3072 on T4")


if __name__ == "__main__":
    main()
