#!/usr/bin/env python3
"""
Build the ROUND-6 Kaggle notebook — port of the Colab round-6 Bible + Error-Fix
QLoRA trainer (train_round6_bible_10h_q4_nodrive.ipynb).

Same training as the Colab plan:
  Base          : Orion-zhen/Qwen2.5-7B-Instruct-Uncensored (4-bit NF4 QLoRA)
  Dataset       : round6-bible-10h.jsonl (2,941 rows, instruction/input/output)
  Config        : LR 2e-4 · 2 epochs · max_seq_length 2048 · LoRA r8/alpha16/d0.05
                  batch 1 · grad-accum 8 · adamw_8bit · GGUF q4_k_m export
  Output        : /kaggle/working/out/  -> adapter_round6/ + tuned GGUF + results.zip

Kaggle adaptations (HARD LESSON 2026-08-01, same as the VACA kernels):
  - Plain single-GPU `python train_round1.py` — NO torchrun DDP (Kaggle reports
    2 T4s but grants only 1 usable GPU -> rank 1 dies 'invalid device ordinal').
  - Pin CUDA_VISIBLE_DEVICES=0 so unsloth fast-attention stays on one device.
  - Dataset arrives as a Kaggle input (/kaggle/input/round6-bible-10h), copied
    to /kaggle/working/dataset — no upload prompt, no Drive.
  - Kaggle auto-zips /kaggle/working into kernel-output.zip at the end; the
    trainer ALSO writes /kaggle/working/out/results.zip for easy download.

Usage:
  python3 scripts/build-r6-kaggle-notebook.py            # write notebook+metadata
  python3 scripts/validate-cloud-notebooks.py            # compile-check all cells

Push (after building):
  bash scripts/kaggle-setup-r6.sh                        # dataset + kernel push
  (then set Settings -> Accelerator GPU T4 x2 + Internet ON in the web UI)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"
DATASET_SLUG = "round6-bible-10h"
KERNEL_SLUG = "vaca-qlora-round6"
NB_NAME = "train_round6_kaggle.ipynb"
META_NAME = "kernel-metadata-round6.json"
DS_META_NAME = "round6-dataset-metadata.json"
TITLE = "VACA QLoRA Round6"

NL = "\n"


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}


def jn(lines):
    return NL.join(lines)


NB_METADATA = {
    # Canonical Kaggle metadata block — the server only honors GPU/internet
    # when these exact fields are present (accelerator is the UI value).
    "kaggle": {
        "accelerator": "NvidiaTeslaT4",
        "dataSources": [],
        "isInternetEnabled": True,
        "language": "python",
        "sourceType": "notebook",
        "isGpuEnabled": True,
    },
    "kernelspec": {"name": "python3", "display_name": "Python 3"},
    "language_info": {"name": "python"},
}


def build():
    # ─── Step 2: locate + copy the attached dataset input ───────────────
    # Kaggle's mount path varies by layout: legacy `/kaggle/input/<slug>` vs
    # the newer nested `/kaggle/input/datasets/<user>/<slug>`. Locate it by
    # globbing /kaggle/input for the slug dir, then for the jsonl itself.
    step2 = jn([
        "import pathlib, shutil",
        "slug_dirs = [p for p in pathlib.Path('/kaggle/input').rglob('*" + DATASET_SLUG + "*') if p.is_dir()]",
        "src = slug_dirs[0] if slug_dirs else None",
        "print('Dataset dirs found:', [str(p) for p in slug_dirs])",
        "if src is None:",
        "    raise SystemExit('Dataset not attached! Click +Add Input → Data → " + DATASET_SLUG + "')",
        "print('Attached inputs:', sorted(p.name for p in src.iterdir()))",
        "dst = pathlib.Path('/kaggle/working/dataset')",
        "dst.mkdir(exist_ok=True)",
        "zips = list(src.glob('*.zip'))",
        "if zips:",
        "    import zipfile",
        "    with zipfile.ZipFile(zips[0]) as z:",
        "        z.extractall(dst)",
        "elif list(src.glob('*.jsonl')):",
        "    for f in src.glob('*.jsonl'):",
        "        shutil.copy(f, dst / f.name)",
        "else:",
        "    raise SystemExit('No .zip or .jsonl found in the attached dataset!')",
        "ds = dst / 'round6-bible-10h.jsonl'",
        "assert ds.exists(), 'round6-bible-10h.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Dataset ready:', ds.name, '|', n_rows, 'rows')",
    ])

    # ─── Step 3b: run cell — plain single-GPU python, round 6 ──────────
    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-6 config (matches the Colab plan) ──",
        "EPOCHS = 2          # 2 ≈ 10.9 h on 1×T4 · 1 = short",
        "LR = 2e-4           # round-6 config (single round @ 2e-4)",
        "# ── Launch ──",
        "# torchrun DDP is UNRELIABLE here (Kaggle reports 2 T4s but grants 1",
        "# usable GPU → rank 1 'invalid device ordinal'; 3 failures 2026-08-01).",
        "# Always plain single-GPU python.",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 6 | LR {LR:.1e} | EPOCHS={EPOCHS} | plain single-GPU (no torchrun)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round6-bible-10h.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '6',",
        "       '--lr', str(LR), '--epochs', str(EPOCHS),",
        "       '--max-seq-length', '2048']",
        "print('RUN:', ' '.join(cmd))",
        "subprocess.run(cmd, check=True)",
    ])

    # ─── Step 4: outputs cell ───────────────────────────────────────────
    out_cell = jn([
        "!ls -lh /kaggle/working/out/",
        "import pathlib",
        "print('\\n✅ Done. Download /kaggle/working/out/results.zip from the Output tab.')",
        "print('Adapter dirs:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('adapter*')) if pathlib.Path('/kaggle/working/out').exists() else [])",
    ])

    cells = [
        md(jn([
            "# 🏆 Round-6 Bible + Error-Fix Q4 QLoRA Trainer — Kaggle Edition",
            "",
            "Fine-tunes **Orion-zhen/Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) on the "
            "round-6 Bible + error-fix dataset — **round 6** (LR 2e-4), 2 epochs, "
            "seq len 2048, LoRA r8/α16, GGUF q4_k_m export. "
            "**Plain single-GPU python — no torchrun** (DDP is unreliable on this "
            "Kaggle account: only 1 GPU is truly granted to the training subprocess).",
            "",
            "**Kaggle free:** 1× T4 usable, ~10.9 h projected, under the 12 h/run cap.",
            "",
            "**Output:** `/kaggle/working/out/results.zip` (adapter_round6/ + tuned "
            "GGUF ~4.4 GB). Download from the **Output** tab (top-right).",
            "",
            "**Steps:** ▶ Step 1 install → ▶ Step 2 copy inputs → ▶ Step 3 train → "
            "▶ Step 4 show outputs.",
        ])),
        md("## Step 1 — Install dependencies\n"
           "~2–3 min. Internet is enabled for this kernel (needed for pip + Hugging Face)."),
        code(jn([
            "!pip install -q unsloth trl transformers datasets accelerate",
            "import torch",
            "print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE', '| count:', torch.cuda.device_count())",
            "assert torch.cuda.is_available(), 'No GPU detected — enable GPU in the notebook settings!'",
            "print('✅ GPU ready — plain single-GPU run (no torchrun).')",
        ])),
        md("## Step 2 — Copy the attached dataset\n"
           f"The `{DATASET_SLUG}` input is attached to this kernel. Copy it into "
           f"`/kaggle/working/dataset/`."),
        code(step2),
        md("## Step 3 — Train (round 6)\n"
           "**Step 3a** writes the trainer script. **Step 3b** runs plain "
           "single-GPU `python train_round1.py` (no torchrun — DDP is unreliable "
           "on this account). Round 6, LR 2e-4, 2 epochs — same config as the "
           "Colab plan."),
        code("%%writefile train_round1.py\n" + SCRIPT),
        code(run_cell),
        md("## Step 4 — Show outputs\n"
           "After training, `results.zip` is in `/kaggle/working/out/`. "
           "Open the **Output** tab (top right) to download it."),
        code(out_cell),
    ]

    nb = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": NB_METADATA,
        "cells": cells,
    }

    meta = {
        "id": f"__USERNAME__/{KERNEL_SLUG}",
        "title": TITLE,
        "subtitle": ("Round 6 (fresh, LR 2e-4) · single-GPU (no torchrun) · "
                     "Qwen2.5-7B-Instruct-Uncensored · GGUF q4_k_m"),
        "code_file": NB_NAME,
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "language": "python",
        "kernel_type": "notebook",
        "dataset_sources": [f"__USERNAME__/{DATASET_SLUG}"],
        "competition_sources": [],
        "kernel_sources": [],
    }

    ds_meta = {
        "id": f"__USERNAME__/{DATASET_SLUG}",
        "title": "Round 6 Bible + Error-Fix Dataset",
        "subtitle": "round6-bible-10h.jsonl — 2,941 rows (Bible + error-fix QLoRA data)",
        "licenses": [{"name": "other"}],
    }

    (KAGGLE_DIR / NB_NAME).write_text(json.dumps(nb, indent=1))
    (KAGGLE_DIR / META_NAME).write_text(json.dumps(meta, indent=2))
    (KAGGLE_DIR / DS_META_NAME).write_text(json.dumps(ds_meta, indent=2))
    print(f"✅ Wrote {NB_NAME} ({len(cells)} cells) + {META_NAME} + {DS_META_NAME}")


if __name__ == "__main__":
    build()
