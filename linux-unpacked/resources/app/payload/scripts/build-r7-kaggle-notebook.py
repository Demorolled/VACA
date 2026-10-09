#!/usr/bin/env python3
"""
Build the ROUND-7 Kaggle notebook — Gemma-4-emotion-distillation QLoRA.

Teacher            : dna5rm/gemma4:12b-8k (Google Gemma 4 12B via Ollama)
Dataset            : round7-emotion.jsonl  (~1.1k rows: emotion/reasoning
                     distillate + round-6 retention mix, instruction/input/output)
Config             : LR 5e-5 (later ladder round — gentle on top of round-6
                     skills) · 2 epochs · max_seq_length 2048 · LoRA
                     r8/alpha16/d0.05 · batch 1 · grad-accum 8 · GGUF q4_k_m
Output             : /kaggle/working/out/ -> adapter_round7/ + tuned GGUF
                     + results.zip

Kaggle adaptations (same hard lessons as rounds 4-6):
  - Plain single-GPU `python train_round1.py` — NO torchrun DDP (Kaggle
    reports 2 T4s but grants 1 usable GPU -> rank 1 'invalid device ordinal').
  - Pin CUDA_VISIBLE_DEVICES=0 so unsloth fast-attention stays on one device.
  - Dataset arrives as a Kaggle input (/kaggle/input/round7-emotion), copied
    to /kaggle/working/dataset — no upload prompt, no Drive.

Usage:
  python3 scripts/build-r7-kaggle-notebook.py            # write notebook+metadata
  python3 scripts/validate-cloud-notebooks.py            # compile-check all cells

Push (after building):
  bash scripts/kaggle-setup-r7.sh                        # dataset + kernel push
  (then set Settings -> Accelerator GPU T4 x2 + Internet ON in the web UI)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"
DATASET_SLUG = "round7-emotion"
KERNEL_SLUG = "vaca-qlora-round7"
NB_NAME = "train_round7_kaggle.ipynb"
META_NAME = "kernel-metadata-round7.json"
DS_META_NAME = "round7-dataset-metadata.json"
TITLE = "VACA QLoRA Round7 (Gemma-4 Emotion Distill)"

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
        "ds = dst / 'round7-emotion.jsonl'",
        "assert ds.exists(), 'round7-emotion.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Dataset ready:', ds.name, '|', n_rows, 'rows')",
    ])

    # ─── Step 3b: run cell — plain single-GPU python, round 7 ──────────
    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-7 config (Gemma-4 emotion distillation round) ──",
        "EPOCHS = 2          # 2 ≈ 4-5 h on 1×T4 at ~1.1k rows",
        "LR = 5e-5           # later ladder round — gentle on top of round-6 skills",
        "# ── Launch ──",
        "# torchrun DDP is UNRELIABLE here (Kaggle reports 2 T4s but grants 1",
        "# usable GPU → rank 1 'invalid device ordinal'; 3 failures 2026-08-01).",
        "# Always plain single-GPU python.",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 7 | LR {LR:.1e} | EPOCHS={EPOCHS} | plain single-GPU (no torchrun)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round7-emotion.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '7',",
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
            "# 🧠 Round-7 Gemma-4 Emotion Distillation — Q4 QLoRA (Kaggle Edition)",
            "",
            "Fine-tunes **Orion-zhen/Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) on the ",
            "round-7 emotion-distillation dataset — ~1.1k rows distilled from **Google ",
            "Gemma 4 12B** (`dna5rm/gemma4:12b-8k`) covering the full emotional register ",            "(banter/roast, empathy-first, mood mirroring & decay, joy, personality, ",
            "identity rules, technical reasoning) + round-6 retention rows so codegen ",
            "does not regress. **Round 7** (LR 5e-5 — gentle continuation), 2 epochs, ",
            "seq len 2048, LoRA r8/α16, GGUF q4_k_m export. ",
            "**Plain single-GPU python — no torchrun** (DDP is unreliable on this ",
            "Kaggle account: only 1 GPU is truly granted to the training subprocess).",
            "",
            "**Kaggle free:** 1× T4 usable, ~4-5 h projected (well under the 12 h cap).",
            "",
            "**Output:** `/kaggle/working/out/results.zip` (adapter_round7/ + tuned ",
            "GGUF ~4.4 GB). Download from the **Output** tab (top-right).",
            "",
            "**After download (back on the local machine):**",
            "```",
            "scripts/deploy-tuned-dspark.sh --now     # replace the live :8000 model",
            "python3 scripts/verify-blueprint-emotion.py   # emotion + fidelity re-check",
            "```",
            "",
            "**Steps:** ▶ Step 1 install → ▶ Step 2 copy inputs → ▶ Step 3 train → ",
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
        md("## Step 3 — Train (round 7)\n"
           "**Step 3a** writes the trainer script. **Step 3b** runs plain "
           "single-GPU `python train_round1.py` (no torchrun — DDP is unreliable "
           "on this account). Round 7, LR 5e-5, 2 epochs."),
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
        "subtitle": ("Round 7 (Gemma-4 emotion distill, LR 5e-5) · single-GPU (no torchrun) · "
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
        "title": "Round 7 Gemma-4 Emotion Distillation Dataset",
        "subtitle": "Gemma-4 emotion distillation dataset (1,276 rows, 7 registers)",
        "licenses": [{"name": "other"}],
    }

    (KAGGLE_DIR / NB_NAME).write_text(json.dumps(nb, indent=1))
    (KAGGLE_DIR / META_NAME).write_text(json.dumps(meta, indent=2))
    (KAGGLE_DIR / DS_META_NAME).write_text(json.dumps(ds_meta, indent=2))
    print(f"✅ Wrote {NB_NAME} ({len(cells)} cells) + {META_NAME} + {DS_META_NAME}")


if __name__ == "__main__":
    build()
