#!/usr/bin/env python3
"""
combine-mixa-round11.py — Mix A Kaggle dataset for the round-11 3D round
========================================================================
Mix A (user-approved 2026-08-10): fill a ~3.4 h T4 session @ seq 2048
(measured ~49.5 s/row × 2 epochs ⇒ ~127 rows):

  new training data set/chunk-3d.jsonl            22 rows  (9 verified 3D apps
                                                           + 13 focused recipes)
  training/dataset/verified-generations.jsonl     18 rows  (auto-capture loop)
  training/operator/dataset/round9-buildladder.jsonl  57 rows  (round-9 data)
  training/cloud/gui-combined-all.jsonl            30 rows  (RETENTION top-up —
                                                           already trained once;
                                                           re-exposed so the 3D
                                                           round can't regress
                                                           prior UI skills)

The gui-combined top-up is intentionally pulled FROM the trained union (it is
a retention slice, like VACA_MIX in the round-4 failures builder) — it is the
ONLY source exempted from the trained-union dedupe.

Outputs (deterministic, seed 42, 90/10):
  training/cloud/round11-mixa-all.jsonl      (merged + deduped, all rows)
  training/cloud/round11-mixa-train.jsonl    (uploaded to Kaggle)
  training/cloud/round11-mixa-val.jsonl      (offline eval only)
  training/cloud/round11-mixa.meta.json
  training/cloud/round11-mixa.zip            (Kaggle upload bundle:
                                             round11-mixa-train.jsonl +
                                             README + metadata)

Usage:
  python3 scripts/combine-mixa-round11.py
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
GUI_TOPDUP = 30  # retention rows sampled from gui-combined-all

# New-signal sources (deduped against the trained union).
SOURCES = [
    (ROOT.parent / "new training data set" / "chunk-3d.jsonl", "round11:3d"),
    (ROOT / "training" / "dataset" / "verified-generations.jsonl", "round11:verified"),
    (ROOT / "training" / "operator" / "dataset" / "round9-buildladder.jsonl", "round11:buildladder"),
]
RETENTION = (ROOT / "training" / "cloud" / "gui-combined-all.jsonl", "round11:retention-gui")

# Everything already trained — new rows matching these are excluded so the
# round trains ONLY fresh signal (plus the deliberate retention slice).
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
    print("[round11-mixa] sources:")
    trained_keys = set()
    found_union = missing_union = 0
    for path in TRAINED_UNION:
        if path.exists():
            trained_keys |= {row_key(r) for r in load(path)}
            found_union += 1
        else:
            missing_union += 1
            print(f"  ⚠️  trained-union file NOT on disk (skipped): {path.name}")
    print(f"  trained union: {len(trained_keys)} rows from {found_union} files"
          f" ({missing_union} listed union files absent locally — their rows are NOT excluded)")

    merged = []
    seen = set()
    src_counts = Counter()
    for path, tag in SOURCES:
        rows = load(path)
        added = 0
        for r in rows:
            k = row_key(r)
            if k in seen or k in trained_keys:
                continue
            seen.add(k)
            r["source"] = tag  # authoritative round-11 tag (overwrites stale provenance)
            merged.append(r)
            added += 1
        src_counts[path.name] = added
        print(f"  {path.name}: {len(rows)} rows → {added} new (deduped)")

    # Retention top-up: sampled deterministically, EXEMPT from dedupe.
    ret_path, ret_tag = RETENTION
    ret_rows = load(ret_path)
    rng = random.Random(SEED + 1)
    rng.shuffle(ret_rows)
    top = 0
    for r in ret_rows[:GUI_TOPDUP]:
        k = row_key(r)
        if k in seen:
            continue
        seen.add(k)
        r["source"] = ret_tag
        merged.append(r)
        top += 1
    src_counts[ret_path.name] = top
    print(f"  {ret_path.name}: {top} retention rows (re-exposure top-up)")

    print(f"\n[round11-mixa] merged: {len(merged)} rows")
    rng = random.Random(SEED)
    rng.shuffle(merged)
    n_val = max(1, round(len(merged) * 0.10))
    val, train = merged[:n_val], merged[n_val:]

    out_all = OUT / "round11-mixa-all.jsonl"
    out_train = OUT / "round11-mixa-train.jsonl"
    out_val = OUT / "round11-mixa-val.jsonl"
    out_meta = OUT / "round11-mixa.meta.json"
    out_zip = OUT / "round11-mixa.zip"

    for path, rows in [(out_all, merged), (out_train, train), (out_val, val)]:
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    meta = {
        "generated": "2026-08-10",
        "round": 11,
        "mix": "A",
        "total_rows": len(merged),
        "by_source": dict(src_counts),
        "split": {"train": len(train), "val": len(val), "seed": SEED},
        "projected_t4_time": {
            "seq_2048_2ep": f"~{len(merged) * 2 * 49.5 / 3600:.1f} h",
            "per_row_anchor": "49.5 s/row @ seq 2048 (measured round-6 Kaggle T4)",
        },
        "note": "gui-combined top-up is a deliberate retention re-exposure (exempt from dedupe).",
    }
    out_meta.write_text(json.dumps(meta, indent=2))

    # ─── Upload bundle (zip) ───────────────────────────────────────────────
    tmp = OUT / "_round11_mixa_stage"
    tmp.mkdir(exist_ok=True)
    shutil.copy(out_train, tmp / "round11-mixa-train.jsonl")
    (tmp / "README.md").write_text(
        "# Round-11 Mix A — 3D GUI + verified + buildladder + retention top-up\n\n"
        f"Train rows: {len(train)} (90/10 split, val kept offline).\n"
        "Config: QLoRA 4-bit Qwen2.5-7B-Instruct-Uncensored · seq 2048 · 2 epochs · "
        "LR 5e-5 continuation from the R10 adapter · batch 1 · grad-accum 8 · "
        "--no-gguf (merged 16-bit safetensors; GGUF converted locally).\n"
        f"Projected: ~{len(merged) * 2 * 49.5 / 3600:.1f} h on 1× T4.\n",
        encoding="utf-8",
    )
    ds_meta = OUT / "kaggle" / "round11-mixa-dataset-metadata.json"
    if ds_meta.exists():
        shutil.copy(ds_meta, tmp / "dataset-metadata.json")
    out_zip.unlink(missing_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(tmp.iterdir()):
            z.write(f, f.name)
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n[round11-mixa] wrote:")
    for p in (out_all, out_train, out_val, out_meta, out_zip):
        print(f"  {p} ({p.stat().st_size if p.exists() else 'n/a'} B)")
    print(f"  → upload bundle: {out_zip}")


if __name__ == "__main__":
    main()
