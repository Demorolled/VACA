#!/usr/bin/env python3
"""
build-r29-kaggle-notebook.py — R29 14B continue-training notebook for Kaggle
================================================================================
    Dataset A: <user>/vaca-r29-corpus    (train/val.jsonl + corpus.json marker)
    Dataset B: <user>/vaca-r29-start     (R28 adapter pack + start.json)
    Dataset C: <user>/vaca-r29-resume    (placeholder first; the monitor versions
                                         it with in-training snapshots between
                                         segments so a re-push resumes exactly)
    Kernel   : <user>/vaca-qlora-round29-r28-continue-26h

Trainer: scripts/train_r29_kaggle.py (verbatim, continuation + 26h budget +
11.3h session cap + resume + crash-safe checkpoints — the proven R22/R23 single
16GB GPU engine from train_r28_kaggle.py).

Usage:
  python3 scripts/build-r29-kaggle-notebook.py
Output:
  kaggle_kernel/train_r29_kaggle.ipynb
  kaggle_kernel/kernel-metadata-r29.json
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE_DIR = ROOT / "kaggle_kernel"
SCRIPT = (ROOT / "scripts" / "train_r29_kaggle.py").read_text()

DATASET_CORPUS = "vaca-r29-corpus"
DATASET_START = "vaca-r29-start"
DATASET_RESUME = "vaca-r29-resume"
KERNEL_SLUG = "vaca-qlora-r29-r28-continue-26h"   # MUST match the title slug, or re-pushes 409
NB_NAME = "train_r29_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-r29.json"
TITLE = "VACA QLoRA R29 (R28 continue, 26h)"

NB_METADATA = {
    "kaggle": {
        # SINGLE 16 GB GPU — CLI can't request T4x2; P100/T4 both fp16-safe.
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


def md(src): return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src): return {"cell_type": "code", "execution_count": None,
                       "metadata": {}, "outputs": [], "source": src.splitlines(keepends=True)}


def build():
    intro = md(
        "# 🧠 VACA Round-29 — 14B QLoRA CONTINUE on Kaggle (26h budget)\n\n"
        "**Continues the CURRENT VACA 14B** — the R28 adapter is loaded on top of "
        "`BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored` and trained onward for a "
        "**total of 26 training hours** across session segments (the monitor re-pushes "
        "this kernel after each ≤11.3h segment; `vaca-r29-resume` carries the state).\n\n"
        "Corpus: **every pool R28 never saw** — Sky-T1 reasoning (4,750), "
        "kaggle-combined/R23/R24 leftovers, GUI, library-distilled, rag, operator, … "
        "(see `corpus.json`; deduped vs R28).\n\n"
        "Proven R22/R23 engine: QLoRA 4-bit r8/α16, LR 5e-5, **fp16** (P100/T4 lack "
        "bf16), seq 1280, batch 1×accum 4, grad checkpointing, `offload_folder` "
        "(defeats the R26 load-spike OOM), masked chat-template labels. Adapter-only "
        "save; 16-bit merge + GGUF happen back on the agent."
    )
    env = code("!nvidia-smi")
    setup = code("\n".join([
        "# ── Install + GPU assert (base 14B loads clean after this cell) ──",
        "!pip install -q -U bitsandbytes",
        "import torch",
        "assert torch.cuda.is_available(), '❌ No GPU — set Accelerator to GPU T4'",
        "print('✅ CUDA:', torch.cuda.device_count(), 'x', torch.cuda.get_device_name(0))",
        "print('   bf16 supported?', torch.cuda.is_bf16_supported(), '(expect False on P100/T4 -> fp16 QLoRA)')",
    ]))
    trainer_cell = code("%%writefile train_r29_kaggle.py\n" + SCRIPT.rstrip() + "\n")
    run_cell = code("\n".join([
        "import os, sys, subprocess, torch",
        "os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')",
        "os.environ.setdefault('PYTORCH_ALLOC_CONF', 'expandable_segments:True')",
        "assert torch.cuda.is_available(), 'No GPU detected'",
        "print('⚙️  Running train_r29_kaggle.py — discovers corpus/start/resume under /kaggle/input')",
        "subprocess.run([sys.executable, 'train_r29_kaggle.py'], check=True)",
    ]))
    out_cell = code("\n".join([
        "import json, pathlib",
        "out = pathlib.Path('/kaggle/working/round29-kaggle')",
        "final = out / 'final'",
        "assert (final / 'adapter_config.json').exists(), '❌ adapter missing'",
        "sz = (final / 'adapter_model.safetensors').stat().st_size",
        "print(f'✅ R29 adapter: {sz/1e6:.1f} MB')",
        "rj = json.loads((out / 'resume.json').read_text()) if (out / 'resume.json').exists() else {}",
        "print('📊 resume.json:', {k: v for k, v in rj.items()})",
        "print('→ download /kaggle/working/round29-kaggle (final/ + checkpoint-*/ + resume.json)')",
    ]))

    nb = {"cells": [intro, env, setup, trainer_cell, run_cell, out_cell],
          "metadata": NB_METADATA, "nbformat": 4, "nbformat_minor": 5}
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
        "dataset_sources": ["__USERNAME__/" + DATASET_CORPUS,
                            "__USERNAME__/" + DATASET_START,
                            "__USERNAME__/" + DATASET_RESUME],
        "kernel_sources": [],
        "model_sources": [],
    }
    (KAGGLE_DIR / KERNEL_META_NAME).write_text(json.dumps(meta, indent=2))
    print(f"✅ Wrote {KAGGLE_DIR / KERNEL_META_NAME}")


if __name__ == "__main__":
    build()