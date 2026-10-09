#!/usr/bin/env python3
"""
Build the self-contained Colab/Kaggle notebook for the cloud QLoRA trainer.
The notebook embeds training/cloud/train_round1.py via a %%writefile cell so the
user uploads a SINGLE .ipynb file (plus the dataset zip).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
OUT = ROOT / "training" / "cloud" / "train_round1.ipynb"


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}


cells = [
    md(
        "# ☁️ VACA QLoRA Round-1 Trainer (GPU Cloud)\n"
        "\n"
        "Fine-tunes **Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) on the VACA "
        "campaign-50 dataset — round 1, LR 2e-4, 2 epochs, seq len 2048, LoRA r8/α16, "
        "GGUF q4_k_m export.\n"
        "\n"
        "**Works on:** Google Colab (T4 free), Kaggle, Lightning AI, RunPod, Vast.ai, Modal.\n"
        "\n"
        "**You need:** the `campaign50-dataset.zip` (train/val/test jsonl) in your "
        "browser downloads. Upload it in Step 2.\n"
        "\n"
        "**Run time:** ~4–6 h on a T4/P100, ~1–2 h on an A100/L40S.\n"
        "\n"
        "---\n"
        "\n"
        "**Steps:** ▶ Run Step 1 (install) → ▶ Run Step 2 (upload dataset zip) "
        "→ ▶ Run Step 3 (train) → ▶ Run Step 4 (download `results.zip`).\n"
        "\n"
        "**Output:** `results.zip` contains `adapter/` (~80 MB) + the tuned "
        "`Qwen2.5-7B-Instruct-Uncensored-Q4_K_M.gguf` (~4.4 GB)."
    ),
    md("## Step 1 — Install dependencies\n"
       "Run this once. ~2–3 min. Colab free (T4, 16 GB) is enough for this config."),
    code(
        "!pip install -q unsloth trl transformers datasets accelerate\n"
        "import torch\n"
        "print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE')\n"
        "assert torch.cuda.is_available(), 'No GPU detected — change runtime type to GPU!'"
    ),
    md("## Step 2 — Upload the dataset zip\n"
       "Click the folder icon → upload → pick `campaign50-dataset.zip`, **then** run this cell. "
       "It extracts `train.jsonl`, `val.jsonl`, `test.jsonl` into `./dataset/`."),
    code(
        "from google.colab import files\n"
        "import zipfile, pathlib\n"
        "uploaded = files.upload()          # pick campaign50-dataset.zip\n"
        "zip_path = next(iter(uploaded))\n"
        "pathlib.Path('dataset').mkdir(exist_ok=True)\n"
        "with zipfile.ZipFile(zip_path) as z:\n"
        "    z.extractall('dataset')\n"
        "print(sorted(p.name for p in pathlib.Path('dataset').glob('*.jsonl')))"
    ),
    md("## Step 3 — Train (round 1)\n"
       "**Step 3a** writes the trainer script to disk. **Step 3b** runs it. "
       "Defaults match the local run: `--rounds 1 --lr 2e-4 --epochs 2 --max-seq-length 2048`. "
       "To run more rounds, change `--rounds` (e.g. `--rounds 3` → 2e-4 → 1e-4 → 5e-5)."),
    code("%%writefile train_round1.py\n" + SCRIPT),
    code(
        "!python train_round1.py --dataset dataset/train.jsonl --out-dir out --rounds 1"
    ),
    md("## Step 4 — Download results\n"
       "Downloads `results.zip` (adapter + GGUF). On free tiers the GGUF (~4.4 GB) "
       "downloads via the browser — keep the tab open."),
    code(
        "from google.colab import files\n"
        "files.download('out/results.zip')\n"
        "print('✅ Downloaded. adapter/ = LoRA (~80 MB), *.gguf = tuned model (~4.4 GB)')"
    ),
]

nb = {
    "nbformat": 4,
    "nbformat_minor": 0,
    "metadata": {
        "colab": {"provenance": []},
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
    },
    "cells": cells,
}

OUT.write_text(json.dumps(nb, indent=1))
print(f"✅ Wrote {OUT} ({len(cells)} cells)")
