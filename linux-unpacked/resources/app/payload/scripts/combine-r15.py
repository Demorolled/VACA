#!/usr/bin/env python3
"""
combine-r15.py — R15 Kaggle dataset (GUI/vision breadth round)
=============================================================
Round 15 = GUI + 3D breadth: the R14 GUI battery's own verified apps become
generation-framed rows (the model's passing GUI output, plus QA rules for the
GUI defect classes it still shows), alongside the R14-probe defect rules and
the single-piece rook/chess rows.

  new training data set/chunk-gui-verified.jsonl   N rows (NEW signal: R14's
                                                          passing GUI apps +
                                                          QA GUI rules)
  new training data set/chunk-3d-r14probe.jsonl     7 rows (NEW: 3 RAW-pass
                                                          3D apps + 4 QA rules)
  new training data set/chunk-3d-rook.jsonl         2 rows (NEW: rook QA rules)
  new training data set/chunk-3d-chess.jsonl        2 rows (NEW: chess QA rules)
  new training data set/chunk-3d-genfix.jsonl      20 rows (RE-EXPOSURE)
  new training data set/chunk-3d-random.jsonl      22 rows (RE-EXPOSURE)
  new training data set/chunk-3d-defects.jsonl     18 rows (RE-EXPOSURE)
  new training data set/chunk-3d.jsonl             22 rows (RE-EXPOSURE)
  training/cloud/round14-genfix-train.jsonl      ~18 rows (RETENTION slice)

The re-exposure sources are intentionally EXEMPT from the trained-union dedupe
(deliberate repeat of already-trained content — repetition is the point after
R13 showed no transfer).

Config for the R15 kernel (chained from the R14 adapter):
  3 epochs · grad-accum 4 · seq 3072 · LR 5e-5 · resume vaca-r14-adapter
  ~N train rows → ~N steps ≈ ~45–60 min on 1× T4.

Seq-3072 budget guard: identical to combine-r14.py — every row is trimmed so
the full VERIFIED app output survives.

Outputs (deterministic, seed 42, 90/10):
  training/cloud/round15-gui-all.jsonl / -train.jsonl / -val.jsonl
  training/cloud/round15-gui.meta.json
  training/cloud/round15-gui.zip   (Kaggle upload bundle)

Usage: python3 scripts/combine-r15.py
"""
import hashlib
import json
import random
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud"
SEED = 42
RETENTION_N = 18

# New-signal sources (deduped against the trained union).
SOURCES = [
    (ROOT.parent / "new training data set" / "chunk-gui-verified.jsonl", "round15:gui-verified"),
    (ROOT.parent / "new training data set" / "chunk-3d-r14probe.jsonl", "round15:r14probe"),
    (ROOT.parent / "new training data set" / "chunk-3d-rook.jsonl", "round15:rook"),
    (ROOT.parent / "new training data set" / "chunk-3d-chess.jsonl", "round15:chess"),
]
# Re-exposure sources (EXEMPT from dedupe — deliberate repeat).
REEXPOSURE = [
    (ROOT.parent / "new training data set" / "chunk-3d-genfix.jsonl", "round15:genfix-reexposure"),
    (ROOT.parent / "new training data set" / "chunk-3d-random.jsonl", "round15:random-reexposure"),
    (ROOT.parent / "new training data set" / "chunk-3d-defects.jsonl", "round15:defects-reexposure"),
    (ROOT.parent / "new training data set" / "chunk-3d.jsonl", "round15:3d-reexposure"),
]
RETENTION = (OUT / "round14-genfix-train.jsonl", "round15:retention-r14")

# Everything already trained (now incl. the R14 mix).
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
    OUT / "round12-defects-all.jsonl",
    OUT / "round13-random-all.jsonl",
    OUT / "round14-genfix-all.jsonl",
]

# ─── Seq-3072 budget guard (kernel max_seq_length, must match the notebook) ─
MAX_SEQ = 3072
TOKEN_CHARS = 3.1
BUDGET_TOKENS = MAX_SEQ - 90


def est_tokens(text: str) -> int:
    return int(len(text) // TOKEN_CHARS) + 1


def fit_row(r: dict) -> dict:
    """Trim so instruction+input+output fit MAX_SEQ tokens.

    Trim order (least critical first): input tail, then instruction tail.
    Never touches the output (the verified app) except as a last resort for
    retention rows whose output alone exceeds the budget.
    """
    out = r.get("output", "")
    out_t = est_tokens(out)
    ins_full = r.get("instruction", "")
    inp_full = r.get("input", "") or ""

    def fits(ins, inp):
        return out_t + est_tokens(ins) + est_tokens(inp) <= BUDGET_TOKENS

    if fits(ins_full, inp_full):
        return r

    for frac in (0.75, 0.50, 0.25, 0.0):
        if fits(ins_full, inp_full[: int(len(inp_full) * frac)]):
            r["input"] = inp_full[: int(len(inp_full) * frac)]
            return r

    for frac in (0.75, 0.50, 0.25, 0.0):
        if fits(ins_full[: int(len(ins_full) * frac)], ""):
            r["instruction"] = ins_full[: int(len(ins_full) * frac)]
            r["input"] = ""
            return r

    if r.get("source", "") == "round15:retention-r14" and out_t > BUDGET_TOKENS:
        keep = max(0, int(BUDGET_TOKENS * TOKEN_CHARS))
        r["output"] = out[:keep]
    return r


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
    print("[round15-gui] trained union:")
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

    # 1) NEW signal — GUI verified + r14probe + rook + chess (deduped)
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

    # 2) Re-exposure — whole 3D corpus (deliberate repeat)
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

    # 3) Retention slice of the R14 mix
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

    # ─── Seq-3072 budget guard ─────────────────────────────────────────────
    trimmed = 0
    over_budget = []
    for r in merged:
        before = est_tokens(r.get("output", "")) + est_tokens(r.get("instruction", "")) + est_tokens(r.get("input", "") or "")
        fit_row(r)
        after = est_tokens(r.get("output", "")) + est_tokens(r.get("instruction", "")) + est_tokens(r.get("input", "") or "")
        if after > BUDGET_TOKENS:
            print(f"  ⚠️  row still over budget after trim ({after} tok, src={r.get('source')}):"
                  f" {r.get('instruction','')[:50]}")
            over_budget.append({"instruction": r.get("instruction", "")[:80],
                                "est_tokens": int(after), "source": r.get("source")})
        elif after < before:
            trimmed += 1
    print(f"[round15-gui] budget guard: {trimmed}/{len(merged)} rows input-trimmed to fit seq {MAX_SEQ}")
    if over_budget:
        print(f"  ⚠️  {len(over_budget)} row(s) have outputs > seq budget — the kernel will truncate"
              f" their tails at {MAX_SEQ} tokens (re-exposure/retention apps already trained).")

    print(f"\n[round15-gui] merged: {len(merged)} rows")
    rng = random.Random(SEED)
    rng.shuffle(merged)
    n_val = max(1, round(len(merged) * 0.10))
    val, train = merged[:n_val], merged[n_val:]

    out_all = OUT / "round15-gui-all.jsonl"
    out_train = OUT / "round15-gui-train.jsonl"
    out_val = OUT / "round15-gui-val.jsonl"
    out_meta = OUT / "round15-gui.meta.json"
    out_zip = OUT / "round15-gui.zip"

    for path, rows in [(out_all, merged), (out_train, train), (out_val, val)]:
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    steps = (len(train) // 4) * 3
    meta = {
        "generated": "2026-08-11",
        "round": 15,
        "mix": "gui-vision",
        "total_rows": len(merged),
        "by_source": dict(src_counts),
        "split": {"train": len(train), "val": len(val), "seed": SEED},
        "seq_budget": {"max_seq": MAX_SEQ, "rows_input_trimmed": trimmed,
                        "rows_output_truncated_by_kernel": len(over_budget),
                        "rows": over_budget},
        "kernel_config": {
            "epochs": 3, "grad_accum": 4, "seq": 3072, "lr": 5e-5,
            "optimizer_steps": steps,
            "resume_from": "vaca-r14-adapter (R14 trained LoRA, chained)",
        },
        "projected_t4_time": f"~{steps * 45 / 60:.1f} h ({steps} steps @ ~45 s/step)",
        "note": "chunk-gui-verified is the fresh GUI signal (R14's own passing "
                "GUI apps + GUI QA rules); r14probe/rook/chess are the fresh 3D "
                "rules; re-exposure of the whole 3D corpus is deliberate "
                "repetition; retention is an R14 slice.",
    }
    (OUT / "round15-gui.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out_train, arcname=out_train.name)
    print(f"[round15-gui] wrote {out_all.name} ({out_all.stat().st_size} B), train {len(train)} / val {len(val)}")
    print(f"[round15-gui] meta + zip: {out_meta.name}, {out_zip.name}")
    print(f"[round15-gui] kernel: {steps} optimizer steps ≈ {steps * 45 / 60:.0f} min @ seq 3072 on T4")


if __name__ == "__main__":
    main()
