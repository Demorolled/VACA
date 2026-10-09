#!/usr/bin/env python3
"""
Build the Round-10 Kaggle notebook — QLoRA starting FROM the deployed R9 model.
==============================================================================
Same flow as build-gui-kaggle-notebook.py:

    Dataset A : <user>/round10-untrained    (1,109 unique untrained rows)
    Dataset B : <user>/vaca-r9-adapter      (copy of the LIVE deployed R9 LoRA)
    Kernel    : <user>/vaca-qlora-round10   (single-GPU T4, no torchrun)
    Trainer   : training/cloud/train_round1.py   (verbatim, via %%writefile)

Round-10 data (everything found untrained in the repo scan, deduped against
the 8,254-row trained union):
  - bible-patterns-new.jsonl   : 573 rows  (never trained; 506 dupes dropped)
  - round8-code.jsonl          : 399 rows  (round 8 kernel never ran)
  - verified-generations.jsonl : 137 rows  (auto-capture loop output)
  Split 998 train / 111 val (seed 42) — trainer re-splits 10% internally.

Resume-from-live: the kernel loads the base model, then --load-adapter the
R9 LoRA (the trainable form of the model dspark currently serves), then trains
round 10. The local R9 GGUF stays untouched and connected to the VACA app.

--no-gguf: the GGUF q4_k_m export step has crashed on Kaggle twice (rounds 6
and 9), so this round saves the MERGED 16-BIT SAFETENSORS instead and we
convert to q4_k_m locally (the proven round-9 recovery path). The kernel
therefore ends cleanly and the output is small: adapter_round10/ + merged
safetensors, downloadable individually.

Kaggle adaptations (hard lessons from rounds 4-9):
  - Plain single-GPU `python train_round1.py` — NO torchrun DDP (Kaggle
    grants only 1 usable T4 to the training subprocess).
  - CUDA_VISIBLE_DEVICES pinned inside the trainer (single-GPU path).
  - Both datasets arrive as /kaggle/input/<slug>; copied to /kaggle/working.

Usage:
  python3 scripts/combine-untrained-round10.py     # first: build the dataset
  python3 scripts/build-round10-kaggle-notebook.py # write notebook + metadata
  python3 scripts/validate-cloud-notebooks.py      # compile-check all cells
  bash scripts/kaggle-setup-round10.sh             # push datasets + kernel

After training completes:
  python3 scripts/download-round10-merged.py       # adapter + merged safetensors
  bash scripts/deploy-round10.sh                   # convert->q4_k_m, deploy, drop R9
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"
DATASET_SLUG = "round10-untrained"
ADAPTER_SLUG = "vaca-r9-adapter"
KERNEL_SLUG = "vaca-qlora-round10"
NB_NAME = "train_round10_kaggle.ipynb"
META_NAME = "kernel-metadata-round10.json"
DS_META_NAME = "round10-dataset-metadata.json"
ADAPTER_META_NAME = "r9-adapter-dataset-metadata.json"
TITLE = "VACA QLoRA Round10"  # slugifies to vaca-qlora-round10 (matches id)
SUBTITLE = ("Round 10 (1,109 untrained rows; resume from live R9 adapter; LR 5e-5; "
            "single-GPU; merged 16-bit export, GGUF built locally)")
N_ROWS = 1109

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
    # ─── Step 2: locate + copy BOTH attached inputs ────────────────────
    step2 = jn([
        "import pathlib, shutil, zipfile",
        "def find_input(slug):",
        "    hits = [p for p in pathlib.Path('/kaggle/input').rglob('*' + slug + '*') if p.is_dir()]",
        "    print(' ', slug, '->', [str(p) for p in hits])",
        "    if not hits:",
        "        raise SystemExit('Missing input: ' + slug + ' — click +Add Input → Data')",
        "    return hits[0]",
        "def extract_all(src_dir, dst_dir):",
        "    dst_dir.mkdir(exist_ok=True)",
        "    zips = sorted(src_dir.glob('*.zip'))",
        "    if zips:",
        "        with zipfile.ZipFile(zips[0]) as z:",
        "            z.extractall(dst_dir)",
        "        print('  extracted:', zips[0].name, '->', dst_dir)",
        "        return",
        "    for f in src_dir.glob('*'):",
        "        if f.is_file():",
        "            shutil.copy(f, dst_dir / f.name)",
        "    print('  copied loose files ->', dst_dir)",
        "",
        "# ── Dataset A: round-10 training rows ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round10-train.jsonl'",
        "assert ds.exists(), 'round10-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'rows (trainer splits 10% val internally)')",
        "",
        "# ── Dataset B: the live R9 LoRA (trainable copy of the deployed model) ──",
        "adapter_src = find_input('" + ADAPTER_SLUG + "')",
        "raw = pathlib.Path('/kaggle/working/adapters_raw')",
        "extract_all(adapter_src, raw)",
        "cand = None",
        "for p in raw.rglob('adapter_config.json'):",
        "    cand = p.parent",
        "    break",
        "assert cand is not None, 'adapter_config.json not found under ' + str(raw)",
        "adapter_dir = pathlib.Path('/kaggle/working/adapters/r9')",
        "adapter_dir.mkdir(parents=True, exist_ok=True)",
        "for f in cand.iterdir():",
        "    if f.is_file():",
        "        shutil.copy(f, adapter_dir / f.name)",
        "print('✅ R9 adapter ready:', adapter_dir)",
        "print('   (resuming training from the model currently live on :8000)')",
    ])

    # ─── Step 3b: run cell — plain single-GPU python, resume R9 ────────
    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-10 config (untrained catch-up, RESUMES from live R9) ──",
        "EPOCHS = 2",
        "LR = 5e-5           # gentle continuation — new domains, low LR",
        "ADAPTER = '/kaggle/working/adapters/r9'",
        "# ── Launch ──",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 10 | LR {LR:.1e} | EPOCHS={EPOCHS} | resume={ADAPTER} | --no-gguf (merged 16-bit)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round10-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '10',",
        "       '--lr', str(LR), '--epochs', str(EPOCHS),",
        "       '--load-adapter', ADAPTER,",
        "       '--no-gguf',",
        "       '--max-seq-length', '2048']",
        "print('RUN:', ' '.join(cmd))",
        "subprocess.run(cmd, check=True)",
    ])

    # ─── Step 4: outputs cell ───────────────────────────────────────────
    out_cell = jn([
        "!ls -lh /kaggle/working/out/",
        "import pathlib",
        "print('\\n✅ Done. Download /kaggle/working/out/results.zip (adapter) + the merged *.safetensors files from the Output tab.')",
        "print('Adapter dirs:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('adapter*')) if pathlib.Path('/kaggle/working/out').exists() else [])",
        "print('Merged safetensors:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('*.safetensors')) if pathlib.Path('/kaggle/working/out').exists() else [])",
    ])

    cells = [
        md(jn([
            "# 🧠 Round 10 — Untrained-Data Catch-up, RESUMING from the live R9 model",
            "",
            "Fine-tunes **Orion-zhen/Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) **resuming from ",
            "the R9 LoRA that is currently deployed and serving the VACA app** (`--load-adapter`). ",
            f"Training rows: {N_ROWS} unique untrained rows compiled from a repo scan (deduped ",
            "against the 8,254-row trained union):",
            "",
            "| Source | Rows | Why untrained |",
            "|---|---|---|",
            f"| `bible-patterns-new.jsonl` | 573 | never trained (506 dupes dropped) |",
            f"| `round8-code.jsonl` | 399 | round-8 kernel never ran |",
            f"| `verified-generations.jsonl` | 137 | auto-capture loop output |",
            "",
            "**Round 10** (LR 5e-5 — gentle continuation), 2 epochs, seq len 2048, LoRA ",
            "r8/α16. **`--no-gguf`** — the GGUF q4_k_m export has crashed on Kaggle twice ",
            "(rounds 6 & 9), so this run saves the **merged 16-bit safetensors** + adapter ",
            "and finishes cleanly; the q4_k_m GGUF is rebuilt locally (proven path).",
            "",
            "**Kaggle free:** 1× T4 usable, ~2-3 h projected (well under the 12 h cap).",
            "",
            "**Output:** `/kaggle/working/out/` → `results.zip` (adapter_round10/) + ",
            "`model-0000{1-4}-of-00004.safetensors` + config. Download from the **Output** tab.",
            "",
            "**After download (back on the local machine):**",
            "```",
            "python3 scripts/download-round10-merged.py     # adapter + merged safetensors",
            "bash scripts/deploy-round10.sh                  # convert→q4_k_m, deploy, drop old R9",
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
        md("## Step 2 — Copy the attached inputs\n"
           f"**Dataset A** `{DATASET_SLUG}` (training rows) and **Dataset B** "
           f"`{ADAPTER_SLUG}` (the live R9 LoRA — trainable copy of the deployed model) "
           "are attached to this kernel. Copy both into `/kaggle/working/`."),
        code(step2),
        md("## Step 3 — Train (Round 10, resume from R9)\n"
           "**Step 3a** writes the trainer script. **Step 3b** runs plain single-GPU "
           "`python train_round1.py` with `--load-adapter <R9 LoRA>` and `--no-gguf` "
           "(no torchrun — DDP is unreliable on this account)."),
        code("%%writefile train_round1.py\n" + SCRIPT),
        code(run_cell),
        md("## Step 4 — Show outputs\n"
           "After training, `results.zip` (adapter) + merged `*.safetensors` are in "
           "`/kaggle/working/out/`. Open the **Output** tab (top right) to download them."),
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
        "subtitle": SUBTITLE,
        "code_file": NB_NAME,
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "language": "python",
        "kernel_type": "notebook",
        "dataset_sources": [f"__USERNAME__/{DATASET_SLUG}", f"__USERNAME__/{ADAPTER_SLUG}"],
        "competition_sources": [],
        "kernel_sources": [],
    }

    ds_meta = {
        "id": f"__USERNAME__/{DATASET_SLUG}",
        "title": "Round-10 untrained catch-up dataset",
        "subtitle": "1,109 untrained rows (bible-patterns + round8-code + verified-gen)",
        "licenses": [{"name": "other"}],
    }

    adapter_meta = {
        "id": f"__USERNAME__/{ADAPTER_SLUG}",
        "title": "VACA live R9 LoRA adapter",
        "subtitle": "adapter_round9 LoRA currently served by dspark :8000 — resume for round 10",
        "licenses": [{"name": "other"}],
    }

    (KAGGLE_DIR / NB_NAME).write_text(json.dumps(nb, indent=1))
    (KAGGLE_DIR / META_NAME).write_text(json.dumps(meta, indent=2))
    (KAGGLE_DIR / DS_META_NAME).write_text(json.dumps(ds_meta, indent=2))
    (KAGGLE_DIR / ADAPTER_META_NAME).write_text(json.dumps(adapter_meta, indent=2))
    print(f"✅ Wrote {NB_NAME} ({len(cells)} cells) + {META_NAME} + {DS_META_NAME} + {ADAPTER_META_NAME}")


if __name__ == "__main__":
    build()
