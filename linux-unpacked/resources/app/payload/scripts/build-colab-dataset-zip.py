#!/usr/bin/env python3
"""
Build training/cloud/campaign50-dataset.zip
============================================
The dataset zip the Colab notebook (colab/train_vaca_colab.ipynb) and the
Kaggle notebooks expect: train.jsonl / val.jsonl / test.jsonl at the zip ROOT
(flat layout — the notebook extracts to /content/dataset and asserts
train.jsonl exists).

Rebuild this every time the dataset is re-merged:
  python3 scripts/merge-campaign50-into-dataset.py   # updates train/val/test
  python3 scripts/build-colab-dataset-zip.py         # re-zip for upload
  python3 scripts/build-colab-dataset-zip.py --self-test
      # build, then extract to a temp dir and assert the flat layout + row
      # counts match the source files (fail loudly on any mismatch, so a bad
      # zip can never be shipped to Colab/Kaggle).
"""

import os
import sys
import tempfile
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(BASE, "training", "dataset")
OUT = os.path.join(BASE, "training", "cloud", "campaign50-dataset.zip")

FILES = ["train.jsonl", "val.jsonl", "test.jsonl"]


def count_lines(path: str) -> int:
    n = 0
    with open(path, encoding="utf-8") as f:
        for _ in f:
            n += 1
    return n


def self_test(zip_path: str = OUT) -> None:
    """Extract the zip to a temp dir; assert flat layout + counts match sources.

    Mirrors what the Colab notebook's Step 4 does: extract to a dir and require
    train.jsonl / val.jsonl / test.jsonl at the ROOT. Any missing file, extra
    top-level nesting, or row-count mismatch aborts with exit 1.
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        missing = [f for f in FILES if f not in names]
        if missing:
            raise SystemExit(
                f"❌ --self-test: zip missing {missing} at root (flat layout expected, got {names})"
            )
        with tempfile.TemporaryDirectory() as td:
            zf.extractall(td)
            total = 0
            for name in FILES:
                src = os.path.join(DS, name)
                n_zip = count_lines(os.path.join(td, name))
                n_src = count_lines(src)
                total += n_zip
                if n_zip != n_src:
                    raise SystemExit(
                        f"❌ --self-test: {name} count mismatch — zip={n_zip} source={n_src}"
                    )
                print(f"   ✓ {name}: {n_zip} rows (zip == source)")
    print(f"✅ --self-test PASS: {len(FILES)} files at root, counts match source ({total} rows total)")


def main() -> None:
    missing = [f for f in FILES if not os.path.isfile(os.path.join(DS, f))]
    if missing:
        raise SystemExit(f"❌ Missing dataset files: {missing} — run the merge first.")

    counts = {}
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in FILES:
            zf.write(os.path.join(DS, name), name)
            counts[name] = count_lines(os.path.join(DS, name))

    size_mb = os.path.getsize(OUT) / 1e6
    print(f"✅ Wrote {OUT} ({size_mb:.1f} MB)")
    for name in FILES:
        print(f"   {name}: {counts[name]} rows")
    print(f"   total: {sum(counts.values())} rows")
    print("   Upload to Colab (or Drive) → the notebook's Step 4 finds it.")

    if "--self-test" in sys.argv:
        print("\n=== self-test: extract + assert layout & counts ===")
        self_test(OUT)


if __name__ == "__main__":
    main()
