#!/usr/bin/env python3
"""
Build the Round-11 Mix A Kaggle notebook — 3D GUI + catch-up, resuming R10.
============================================================================
Same flow as build-round10-kaggle-notebook.py:

    Dataset A : <user>/round11-mixa        (Mix A train rows — 3D + verified
                                           + buildladder + gui retention top-up)
    Dataset B : <user>/vaca-r10-adapter    (copy of the LIVE deployed R10 LoRA)
    Kernel    : <user>/vaca-qlora-round11  (single-GPU T4, no torchrun)
    Trainer   : training/cloud/train_round1.py   (verbatim, via %%writefile)

Mix A (built by scripts/combine-mixa-round11.py, user-approved 2026-08-10):
  - chunk-3d.jsonl                22 rows  (9 verified 3D apps + 13 recipes)
  - verified-generations.jsonl    18 rows
  - round9-buildladder.jsonl      57 rows
  - gui-combined-all.jsonl        30 rows  (retention top-up, exempt from dedupe)
  ≈ 127 rows ≈ 3.4 h @ seq 2048 on 1× T4 (measured 49.5 s/row).

Resume-from-live: the kernel loads the base model, then --load-adapter the R10
LoRA (the trainable form of the model dspark currently serves), then trains
round 11. The local R10 GGUF stays untouched and connected to the VACA app.

--no-gguf: the GGUF q4_k_m export step has crashed on Kaggle twice (rounds 6
and 9), so this round saves the MERGED 16-BIT SAFETENSORS instead and we
convert to q4_k_m locally (the proven round-9 recovery path).

Kaggle adaptations (hard lessons from rounds 4-10):
  - Plain single-GPU `python train_round1.py` — NO torchrun DDP (Kaggle
    grants only 1 usable T4 to the training subprocess).
  - CUDA_VISIBLE_DEVICES pinned inside the trainer (single-GPU path).
  - Both datasets arrive as /kaggle/input/<slug>; copied to /kaggle/working.

Usage:
  python3 scripts/combine-mixa-round11.py              # first: build the dataset
  python3 scripts/build-round11-mixa-kaggle-notebook.py
  python3 scripts/validate-cloud-notebooks.py          # compile-check all cells
  bash scripts/kaggle-setup-round11-mixa.sh            # push datasets + kernel

After training completes:
  python3 scripts/download-round10-merged.py  (reuse: adapter + merged safetensors)
  bash scripts/deploy-round11.sh              (convert->q4_k_m, deploy, drop R10)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"

DATASET_SLUG = "round11-mixa"
ADAPTER_SLUG = "vaca-r10-adapter"
KERNEL_SLUG = "vaca-qlora-round11"
NB_NAME = "train_round11_mixa_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-round11.json"
DS_META_NAME = "round11-mixa-dataset-metadata.json"
ADAPTER_META_NAME = "r10-adapter-dataset-metadata.json"
TITLE = "VACA QLoRA Round11"
SUBTITLE = ("Round 11 Mix A (3D GUI + verified + buildladder; resume from live "
            "R10 adapter; LR 5e-5; seq 2048; single-GPU; merged 16-bit export)")

# Row count filled from the combine meta (fall back to the projected ~127).
_m = KAGGLE_DIR.parent / "round11-mixa.meta.json"
N_ROWS = json.loads(_m.read_text()).get("total_rows", 127) if _m.exists() else 127

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
        "# ── Dataset A: round-11 Mix A training rows ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round11-mixa-train.jsonl'",
        "assert ds.exists(), 'round11-mixa-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'rows (trainer splits 10% val internally)')",
        "",
        "# ── Dataset B: the live R10 LoRA (trainable copy of the deployed model) ──",
        "adapter_src = find_input('" + ADAPTER_SLUG + "')",
        "raw = pathlib.Path('/kaggle/working/adapters_raw')",
        "extract_all(adapter_src, raw)",
        "cand = None",
        "for p in raw.rglob('adapter_config.json'):",
        "    cand = p.parent",
        "    break",
        "assert cand is not None, 'adapter_config.json not found under ' + str(raw)",
        "adapter_dir = pathlib.Path('/kaggle/working/adapters/r10')",
        "adapter_dir.mkdir(parents=True, exist_ok=True)",
        "for f in cand.iterdir():",
        "    if f.is_file():",
        "        shutil.copy(f, adapter_dir / f.name)",
        "print('✅ R10 adapter ready:', adapter_dir)",
        "print('   (resuming training from the model currently live on :8000)')",
    ])

    # ─── Step 3b: run cell — plain single-GPU python, resume R10 ────────
    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-11 Mix A config (resumes from the live R10) ──",
        "EPOCHS = 2",
        "LR = 5e-5           # gentle continuation — new domains (3D), low LR",
        "ADAPTER = '/kaggle/working/adapters/r10'",
        "# ── Launch ──",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 11 | LR {LR:.1e} | EPOCHS={EPOCHS} | resume={ADAPTER} | --no-gguf (merged 16-bit)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round11-mixa-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '11',",
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
            "# 🧠 Round 11 — Mix A: 3D GUI capability, RESUMING from the live R10 model",
            "",
            "Fine-tunes **Orion-zhen/Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) **resuming ",
            "from the R10 LoRA that is currently deployed and serving the VACA app** "
            "(`--load-adapter`). This round teaches the model to write **stunning 3D apps** — ",
            "the 9 render-verified Three.js examples (chess with AI, solar system, product ",
            "showcase, Rubik's cube, maze explorer, fireworks, terrain, torus knot, 3D bar ",
            "chart) plus their 13 focused recipe rows, alongside verified + round-9 catch-up ",
            "and a gui-combined retention slice so prior 2D skills cannot regress.",
            "",
            "| Source | Rows | Why |",
            "|---|---|---|",
            f"| `chunk-3d.jsonl` | 22 | verified 3D apps + recipes (render-gated) |",
            f"| `verified-generations.jsonl` | 18 | auto-capture loop output |",
            f"| `round9-buildladder.jsonl` | 57 | round-9 operator data |",
            f"| `gui-combined-all.jsonl` | 30 | RETENTION top-up (anti-regression) |",
            f"**Total** | **{N_ROWS}** | ≈ 3.4 h @ seq 2048 on 1× T4 |",
            "",
            "**Round 11** (LR 5e-5 — gentle continuation), 2 epochs, seq len 2048, LoRA ",
            "r8/α16. **`--no-gguf`** — the GGUF q4_k_m export has crashed on Kaggle twice ",
            "(rounds 6 & 9), so this run saves the **merged 16-bit safetensors** + adapter ",
            "and finishes cleanly; the q4_k_m GGUF is rebuilt locally (proven path).",
            "",
            "**Kaggle free:** 1× T4 usable, ~3.4 h projected (well under the 12 h cap).",
            "",
            "**Output:** `/kaggle/working/out/` → `results.zip` (adapter_round11/) + ",
            "`model-0000{1-4}-of-00004.safetensors` + config. Download from the **Output** tab.",
            "",
            "**After download (back on the local machine):**",
            "```",
            "python3 scripts/download-round10-merged.py     # reuse: adapter + merged safetensors",
            "bash scripts/deploy-round11.sh                  # convert→q4_k_m, deploy, drop R10",
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
           f"`{ADAPTER_SLUG}` (the live R10 LoRA — trainable copy of the deployed model) "
           "are attached to this kernel. Copy both into `/kaggle/working/`."),
        code(step2),
        md("## Step 3 — Train (Round 11, resume from R10)\n"
           "**Step 3a** writes the trainer script. **Step 3b** runs plain single-GPU "
           "`python train_round1.py` with `--load-adapter <R10 LoRA>` and `--no-gguf` "
           "(no torchrun — DDP is unreliable on this account)."),
        code("%%writefile train_round1.py\n" + SCRIPT),
        code(run_cell),
        md("## Step 4 — Show outputs\n"
           "List the training artifacts in `/kaggle/working/out/` so they can be downloaded "
           "from the Output tab."),
        code(out_cell),
    ]

    nb = {
        "metadata": NB_METADATA,
        "nbformat": 4,
        "nbformat_minor": 4,
        "cells": cells,
    }
    (KAGGLE_DIR / NB_NAME).write_text(json.dumps(nb, indent=1))

    kernel_meta = {
        "id": "__USERNAME__/" + KERNEL_SLUG,
        "title": TITLE,
        "subtitle": SUBTITLE,
        "code_file": NB_NAME,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "competition_sources": [],
        "dataset_sources": [
            "__USERNAME__/" + DATASET_SLUG,
            "__USERNAME__/" + ADAPTER_SLUG,
        ],
    }
    (KAGGLE_DIR / KERNEL_META_NAME).write_text(json.dumps(kernel_meta, indent=2))
    print(f"[round11-mixa] wrote {KAGGLE_DIR / NB_NAME}")
    print(f"[round11-mixa] wrote {KAGGLE_DIR / KERNEL_META_NAME} (N_ROWS={N_ROWS})")


if __name__ == "__main__":
    build()
