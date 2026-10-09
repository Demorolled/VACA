#!/usr/bin/env python3
"""
Restore dataset_meta.json to the pre-merge state (reverses a validation-only
merge run of scripts/merge-campaign50-into-dataset.py).

The merge script only backs up train/val/test (not the meta), so after a
validation run the meta can disagree with the restored files. This recomputes
the totals FROM the on-disk files and drops the merged_priority_sources entry
+ captured-verified.jsonl source marker added by that run.
"""
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(BASE, "training", "dataset")
META = os.path.join(DS, "dataset_meta.json")


def count(path):
    with open(path, encoding="utf-8") as f:
        return sum(1 for _ in f)


def main():
    n_train = count(os.path.join(DS, "train.jsonl"))
    n_val = count(os.path.join(DS, "val.jsonl"))
    n_test = count(os.path.join(DS, "test.jsonl"))
    with open(META, encoding="utf-8") as f:
        meta = json.load(f)
    meta["total_examples"] = n_train + n_val + n_test
    meta["train_examples"] = n_train
    meta["val_examples"] = n_val
    meta["test_examples"] = n_test
    meta.pop("merged_priority_sources", None)
    srcs = meta.get("sources", [])
    if "captured-verified.jsonl" in srcs:
        srcs.remove("captured-verified.jsonl")
    meta["sources"] = srcs
    with open(META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"✅ meta restored: total={meta['total_examples']} train={n_train} val={n_val} test={n_test} "
          f"(priority_sources={meta.get('merged_priority_sources', 'absent')}, captured-src={'in' if 'captured-verified.jsonl' in srcs else 'out'})")


if __name__ == "__main__":
    main()
