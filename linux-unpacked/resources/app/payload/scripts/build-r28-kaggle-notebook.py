#!/usr/bin/env python3
"""
build-r28-kaggle-notebook.py — R28 14B missed-corpus QLoRA notebook for Kaggle
================================================================================
    Dataset: <user>/vaca-r28-missed-corpus   (train/val.jsonl, 2,769 missed rows)
    Kernel : <user>/vaca-r28-qlora-missed-14b-t4x2
    Trainer: scripts/train_r28_kaggle.py (verbatim, single code cell — the
             proven R23 pattern: 4-bit QLoRA r8/α16, seq 1280, 2 epochs,
             batch 1 × accum 4, LR 5e-5, on ONE 16 GB GPU via device_map
             + offload_folder; FP16 because P100/T4 have no bf16).

Round-28 recipe matches the missed-corpus time estimate (~5h / 2 epochs): the
14B R20 was last trained through R18-20 (Aug 17); R21-25 generated the 2,769
rows in round25/all.jsonl it has never seen. This is JUST that missed data —
no 27B-distilled rows.

Usage (depends on build-r28-missed-corpus.py first, then):
  python3 scripts/build-r28-kaggle-notebook.py
Output:
  kaggle_kernel/train_r28_kaggle.ipynb
  kaggle_kernel/kernel-metadata-r28.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE_DIR = ROOT / "kaggle_kernel"
SCRIPT = (ROOT / "scripts" / "train_r28_kaggle.py").read_text()

DATASET_SLUG = "vaca-r28-missed-corpus"
KERNEL_SLUG = "vaca-qlora-round28-missed-corpus-14b"  # resolved from the title
NB_NAME = "train_r28_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-r28.json"
TITLE = "VACA QLoRA Round28 (Missed-Corpus 14B)"

NB_METADATA = {
    "kaggle": {
        # SINGLE 16 GB GPU — the CLI can't request "T4 x2" (NvidiaTeslaT4X2
        # isn't a valid push accelerator), so the kernel always gets one card.
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


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [], "source": src.splitlines(keepends=True)}


def build():
    intro = md(
        "# 🧠 VACA Round-28 — 14B QLoRA (missed-corpus catch-up, single 16 GB GPU)\n\n"
        "**2,769 rows** = the R21–25 VACA corpus (`round25/all.jsonl`) the R20 14B "
        "never saw. **No 27B-distilled rows** — this is pure missed-training catch-up. "
        "Proven R22/23 recipe: QLoRA r8/α16, seq 1280, 2 epochs, batch 1×accum 4, "
        "LR 5e-5, **FP16** (P100/T4 lack bf16), `device_map=auto` on ONE 16 GB GPU "
        "+ `offload_folder` (defeats the R26 load-spike OOM). "
        "Adapter-only save (no in-kernel 16-bit merge — the R19 OOM spot); merge "
        "back on the agent afterwards."
    )
    env = code(
        "!nvidia-smi"
    )
    setup = code("\n".join([
        "# ── Install (explicit cell so the base 14B loads clean) ──",
        "!pip install -q -U bitsandbytes",
        "import torch",
        "assert torch.cuda.is_available(), '❌ No GPU — set Accelerator to a GPU in kernel settings'",
        "print('✅ CUDA:', torch.cuda.device_count(), 'x', torch.cuda.get_device_name(0))",
        "print('   bf16 supported?', torch.cuda.is_bf16_supported(), '(expect False on P100/T4 -> fp16 QLoRA)')",
    ]))
    trainer_cell = code("%%writefile train_r28_kaggle.py\n" + SCRIPT.rstrip() + "\n")
    run_cell = code("\n".join([
        "import os, sys, subprocess, torch",
        "# ── Round-28 runner: the script frees VRAM via PYTORCH_ALLOC_CONF + offload_folder ──",
        "os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')",
        "os.environ.setdefault('PYTORCH_ALLOC_CONF', 'expandable_segments:True')",
        "assert torch.cuda.is_available(), 'No GPU detected'",
        "print('⚙️  Running train_r28_kaggle.py — data will be auto-discovered under /kaggle/input')",
        "subprocess.run([sys.executable, 'train_r28_kaggle.py'], check=True)",
    ]))
    out_cell = code("\n".join([
        "import pathlib",
        "out = pathlib.Path('/kaggle/working/round28-kaggle')",
        "final = out / 'final'",
        "assert (final / 'adapter_config.json').exists(), '❌ adapter missing'",
        "sz = (final / 'adapter_model.safetensors').stat().st_size",
        "print(f'✅ R28 adapter: {sz/1e6:.1f} MB')",
        "print('→ download /kaggle/working/round28-kaggle (final/ = LoRA; merge locally)')",
    ]))

    nb = {
        "cells": [intro, env, setup, trainer_cell, run_cell, out_cell],
        "metadata": NB_METADATA,
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)
    (KAGGLE_DIR / NB_NAME).write_text(json.dumps(nb, indent=1))
    print(f"✅ Wrote {KAGGLE_DIR / NB_NAME} ({len(nb['cells'])} cells)")

    meta = {
        "id": "__USERNAME__/" + KERNEL_SLUG,
        "title": TITLE,
        "code_file": NB_NAME,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "competition_sources": [],
        "dataset_sources": ["__USERNAME__/" + DATASET_SLUG],
        "kernel_sources": [],
        "model_sources": [],
    }
    (KAGGLE_DIR / KERNEL_META_NAME).write_text(json.dumps(meta, indent=2))
    print(f"✅ Wrote {KAGGLE_DIR / KERNEL_META_NAME}")


if __name__ == "__main__":
    build()