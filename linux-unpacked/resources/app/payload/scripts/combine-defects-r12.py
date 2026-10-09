#!/usr/bin/env python3
"""
combine-defects-r12.py — R12 defect-round Kaggle dataset
=========================================================
Round 12 = DEFECT-FIX round (the R11 3D probe failures, packaged as
chunk-3d-defects.jsonl) plus deliberate re-exposure of the 3D apps and a
retention slice of round 11's mix so prior skills cannot regress.

  new training data set/chunk-3d-defects.jsonl   18 rows  (NEW signal — deduped)
  new training data set/chunk-3d.jsonl           22 rows  (RE-EXPOSURE: seen only
                                                           in R11's tiny 26-step
                                                           dose; re-trained with a
                                                           real dose now)
  training/cloud/round11-mixa-train.jsonl        40 rows  (RETENTION slice of the
                                                           R11 mix, re-exposed)

The two re-exposure sources are intentionally EXEMPT from the trained-union
dedupe (they are already-trained content that the round deliberately repeats).

Config for the R12 kernel (stronger dose than R11):
  3 epochs · grad-accum 4 · seq 3072 · LR 5e-5 · resume from the REAL R11 LoRA
  (adapter_trained = e3b7e7cc, chained as dataset B `vaca-r11-adapter`).
  72 train rows → 18 steps/epoch → 54 optimizer steps (~2x R11's 26) ≈ 45 min.

Seq-3072 budget guard (reviewer fix): every row is trimmed to fit the kernel's
max_seq_length so the VERIFIED app output is never truncated mid-HTML. Trim
order: input tail first (spec/guidance is the least critical part), and only
for RETENTION rows (already-trained content) the output tail as a last resort.
Defect + 3D re-exposure outputs are always kept whole (they fit after input
trim: max defect row 2097 tok, max 3D row 3384 tok).

Outputs (deterministic, seed 42, 90/10):
  training/cloud/round12-defects-all.jsonl / -train.jsonl / -val.jsonl
  training/cloud/round12-defects.meta.json
  training/cloud/round12-defects.zip   (Kaggle upload bundle)

Usage: python3 scripts/combine-defects-r12.py
"""
import hashlib
import json
import random
import shutil
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud"
SEED = 42
RETENTION_N = 40

# ─── Seq-3072 budget guard ─────────────────────────────────────────────────
# Kernel max_seq_length (must match build-r12-kaggle-notebook.py). Reserve
# ~90 tokens for the chat-template wrapper. ~3.1 chars/token is conservative
# for code-heavy rows (measured 2.9-3.3 on this dataset), so we over-estimate
# token counts slightly — safe direction.
MAX_SEQ = 3072
TOKEN_CHARS = 3.1
BUDGET_TOKENS = MAX_SEQ - 90


def est_tokens(text: str) -> int:
    return int(len(text) // TOKEN_CHARS) + 1


def fit_row(r: dict) -> dict:
    """Trim so instruction+input+output fit MAX_SEQ tokens.

    Trim order (least critical first): input tail, then instruction tail.
    Never touches the output (the verified app) except as a last resort for
    retention rows whose output alone exceeds the budget (already-trained
    content — a truncated tail costs nothing new to learn).
    """
    out = r.get("output", "")
    out_t = est_tokens(out)
    ins_full = r.get("instruction", "")
    inp_full = r.get("input", "") or ""

    def fits(ins, inp):
        return out_t + est_tokens(ins) + est_tokens(inp) <= BUDGET_TOKENS

    if fits(ins_full, inp_full):
        return r

    # 1) Drain the input tail first (spec/guidance is the least critical).
    for frac in (0.75, 0.50, 0.25, 0.0):
        if fits(ins_full, inp_full[: int(len(inp_full) * frac)]):
            r["input"] = inp_full[: int(len(inp_full) * frac)]
            return r

    # 2) Input exhausted — now shorten the instruction tail.
    for frac in (0.75, 0.50, 0.25, 0.0):
        if fits(ins_full[: int(len(ins_full) * frac)], ""):
            r["instruction"] = ins_full[: int(len(ins_full) * frac)]
            r["input"] = ""
            return r

    # 3) Last resort — retention only: cap the output tail.
    if r.get("source", "") == "round12:retention-r11" and out_t > BUDGET_TOKENS:
        keep = max(0, int(BUDGET_TOKENS * TOKEN_CHARS))
        r["output"] = out[:keep]
    return r

# New-signal source (deduped against the trained union).
SOURCES = [
    (ROOT.parent / "new training data set" / "chunk-3d-defects.jsonl", "round12:defects"),
]
# Re-exposure sources (EXEMPT from dedupe — deliberate repeat).
REEXPOSURE = [
    (ROOT.parent / "new training data set" / "chunk-3d.jsonl", "round12:3d-reexposure"),
]
RETENTION = (OUT / "round11-mixa-train.jsonl", "round12:retention-r11")

# Everything already trained (now incl. the R11 mix).
TRAINED_UNION = [
    ROOT / "training" / "dataset" / "train.jsonl",
    ROOT / "training" / "dataset" / "val.jsonl",
    ROOT / "training" / "dataset" / "round2-mixed.jsonl",
    ROOT / "training" / "dataset" / "round3-mixed.jsonl",
    ROOT / "training" / "dataset" / "round4-failures.jsonl",
    ROOT / "training" / "dataset" / "round5-blueprints.jsonl",
    ROOT / "training" / "dataset" / "round6-bible-10h.jsonl",
    ROOT / "training" / "dataset" / "round7-emotion.jsonl",
    ROOT / "training" / "cloud" / "gui-combined-all.jsonl",
    ROOT / "training" / "cloud" / "round10-train.jsonl",
    ROOT / "training" / "cloud" / "round10-val.jsonl",
    OUT / "round11-mixa-train.jsonl",
    OUT / "round11-mixa-val.jsonl",
]


def row_key(r: dict) -> str:
    return hashlib.md5(
        f"{r.get('instruction', '')}|{r.get('input', '')}|{r.get('output', '')}".encode()
    ).hexdigest()


def load(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"❌ Dataset not found: {path}")
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  ⚠️  skip unparseable line in {path.name}")
    return rows


def main():
    print("[round12-defects] trained union:")
    trained_keys = set()
    found_union = missing_union = 0
    for path in TRAINED_UNION:
        if path.exists():
            trained_keys |= {row_key(r) for r in load(path)}
            found_union += 1
        else:
            missing_union += 1
            print(f"  ⚠️  trained-union file NOT on disk (skipped): {path.name}")
    print(f"  {len(trained_keys)} rows from {found_union} files"
          f" ({missing_union} listed files absent locally)")

    merged = []
    seen = set()
    src_counts = Counter()

    # 1) NEW signal — deduped
    for path, tag in SOURCES:
        rows = load(path)
        added = 0
        for r in rows:
            k = row_key(r)
            if k in seen or k in trained_keys:
                continue
            seen.add(k)
            r["source"] = tag
            merged.append(r)
            added += 1
        src_counts[path.name] = added
        print(f"  {path.name}: {len(rows)} rows → {added} new (deduped)")

    # 2) Re-exposure — chunk-3d (R11 saw it for 26 tiny steps; re-train fully)
    for path, tag in REEXPOSURE:
        rows = load(path)
        added = 0
        for r in rows:
            k = row_key(r)
            if k in seen:
                continue
            seen.add(k)
            r["source"] = tag
            merged.append(r)
            added += 1
        src_counts[path.name] = added
        print(f"  {path.name}: {len(rows)} rows → {added} re-exposed (exempt from dedupe)")

    # 3) Retention slice of the R11 mix
    ret_path, ret_tag = RETENTION
    ret_rows = load(ret_path)
    rng = random.Random(SEED + 2)
    rng.shuffle(ret_rows)
    top = 0
    for r in ret_rows[:RETENTION_N]:
        k = row_key(r)
        if k in seen:
            continue
        seen.add(k)
        r["source"] = ret_tag
        merged.append(r)
        top += 1
    src_counts[ret_path.name] = top
    print(f"  {ret_path.name}: {top} retention rows (re-exposure slice)")

    # ─── Seq-3072 budget guard: trim inputs so full verified outputs survive ─
    trimmed = 0
    over_budget = []
    for r in merged:
        before = est_tokens(r.get("output", "")) + est_tokens(r.get("instruction", "")) + est_tokens(r.get("input", "") or "")
        fit_row(r)
        after = est_tokens(r.get("output", "")) + est_tokens(r.get("instruction", "")) + est_tokens(r.get("input", "") or "")
        if after > MAX_SEQ - 90:
            print(f"  ⚠️  row still over budget after trim ({after} tok, src={r.get('source')}):"
                  f" {r.get('instruction','')[:50]}")
            over_budget.append({"instruction": r.get("instruction", "")[:80],
                                "est_tokens": int(after), "source": r.get("source")})
        elif after < before:
            trimmed += 1
    print(f"[round12-defects] budget guard: {trimmed}/{len(merged)} rows input-trimmed to fit seq {MAX_SEQ}")
    if over_budget:
        print(f"  ⚠️  {len(over_budget)} row(s) have outputs > seq budget — the kernel will truncate"
              f" their tails at {MAX_SEQ} tokens (all are re-exposure/retention apps already"
              f" trained at seq 2048 in R11, so this is strictly better).")

    print(f"\n[round12-defects] merged: {len(merged)} rows")
    rng = random.Random(SEED)
    rng.shuffle(merged)
    n_val = max(1, round(len(merged) * 0.10))
    val, train = merged[:n_val], merged[n_val:]

    out_all = OUT / "round12-defects-all.jsonl"
    out_train = OUT / "round12-defects-train.jsonl"
    out_val = OUT / "round12-defects-val.jsonl"
    out_meta = OUT / "round12-defects.meta.json"
    out_zip = OUT / "round12-defects.zip"

    for path, rows in [(out_all, merged), (out_train, train), (out_val, val)]:
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 54 optimizer steps = 72 rows / accum 4 × 3 epochs; ~45 s/step measured
    steps = (len(train) // 4) * 3
    meta = {
        "generated": "2026-08-10",
        "round": 12,
        "mix": "defects",
        "total_rows": len(merged),
        "by_source": dict(src_counts),
        "split": {"train": len(train), "val": len(val), "seed": SEED},
        "seq_budget": {"max_seq": MAX_SEQ, "rows_input_trimmed": trimmed,
                        "rows_output_truncated_by_kernel": len(over_budget),
                        "rows": over_budget},
        "kernel_config": {
            "epochs": 3, "grad_accum": 4, "seq": 3072, "lr": 5e-5,
            "optimizer_steps": steps,
            "resume_from": "vaca-r11-adapter (real R11 LoRA e3b7e7cc)",
        },
        "projected_t4_time": f"~{steps * 45 / 3600:.1f} h ({steps} steps @ ~45 s/step)",
        "note": "chunk-3d + round11-mixa slice are deliberate re-exposure (exempt from dedupe); "
                "chunk-3d-defects is the fresh defect-fix signal.",
    }
    out_meta.write_text(json.dumps(meta, indent=2))

    # ─── Upload bundle (zip) ───────────────────────────────────────────────
    tmp = OUT / "_round12_defects_stage"
    tmp.mkdir(exist_ok=True)
    shutil.copy(out_train, tmp / "round12-defects-train.jsonl")
    (tmp / "README.md").write_text(
        "# Round-12 Defects — 3D probe-failure fix round\n\n"
        f"Train rows: {len(train)} (90/10 split, val kept offline).\n"
        "Config: QLoRA 4-bit Qwen2.5-7B-Instruct-Uncensored · seq 2048 · 3 epochs · "
        "grad-accum 4 · LR 5e-5 continuation from the REAL R11 LoRA · "
        "--no-gguf (merged 16-bit safetensors; GGUF converted locally).\n"
        f"≈ {steps} optimizer steps ≈ ~{steps * 45 / 3600:.1f} h on 1× T4.\n",
        encoding="utf-8",
    )
    ds_meta = OUT / "kaggle" / "round12-defects-dataset-metadata.json"
    if ds_meta.exists():
        shutil.copy(ds_meta, tmp / "dataset-metadata.json")
    out_zip.unlink(missing_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(tmp.iterdir()):
            z.write(f, f.name)
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n[round12-defects] wrote:")
    for p in (out_all, out_train, out_val, out_meta, out_zip):
        print(f"  {p} ({p.stat().st_size if p.exists() else 'n/a'} B)")


if __name__ == "__main__":
    main()
