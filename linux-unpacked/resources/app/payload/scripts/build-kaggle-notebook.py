#!/usr/bin/env python3
"""
Build the KAGGLE notebooks for the 4-round QLoRA fine-tune.

HARD LESSON (2026-08-01): torchrun DDP is UNRELIABLE on this Kaggle account.
The node reports 2 T4s at the driver level (torch.cuda.device_count()==2), but
the session only GRANTS 1 usable GPU to the training subprocess — so torchrun
rank 1 dies with 'invalid device ordinal' during model load. This failed
identically across THREE launch strategies (hardcoded torchrun, count-based
adaptive, probe-based adaptive), so ALL kernels now run plain single-GPU python
(train_round1.py supports it) — no torchrun, no GPU probe.

Kaggle caps a single run at 12 h. On 1× T4 each round is ~6-10 h, so each run
trains exactly ONE round (ROUNDS=1) and the 4 rounds are chained across FOUR
runs, each resuming the previous round's adapter:

  mode     round  LR      resume from         kernel slug
  rounds12 r1     2e-4    (fresh)             vaca-qlora-rounds-1-2
  round2   r2     1e-4    round-1 adapter     vaca-qlora-rounds-1-2
  rounds34 r3     5e-5    round-2 adapter     vaca-qlora-rounds-3-4
  round4   r4     2.5e-5  round-3 adapter     vaca-qlora-rounds-3-4

Resume modes need the `vaca-rounds12-adapter` dataset attached — it must be
re-versioned with the LATEST completed adapter before each resume run
(scripts/kaggle-watch-adapter.sh prepares the local zip after every run).

Usage:
  python3 scripts/build-kaggle-notebook.py                # build all 4 modes
  bash scripts/kaggle-setup.sh --kernel round2            # push a specific mode
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"
DATASET_SLUG = "vaca-campaign50-dataset"
ADAPTER_SLUG = "vaca-rounds12-adapter"

# One mode per round. round2 reuses the rounds-1-2 kernel slug (same version
# family), round4 reuses rounds-3-4 — so the chain/status scripts' kernel refs
# stay valid. The title must slugify EXACTLY to `slug` (Kaggle derives the
# kernel slug from the title), hence shared titles within each pair.
MODES = {
    "rounds12": dict(
        start_round=1, first_lr="2e-4", resume=False, next_kernel="round2",
        slug="vaca-qlora-rounds-1-2", title="VACA QLoRA Rounds 1-2",
        nb="train_rounds12_kaggle.ipynb", meta="kernel-metadata-rounds12.json",
        subtitle=("Round 1 of 4 (fresh, LR 2e-4) · single-GPU (no torchrun) · "
                  "Qwen2.5-7B-Instruct-Uncensored · GGUF q4_k_m"),
    ),
    "round2": dict(
        start_round=2, first_lr="1e-4", resume=True, next_kernel="rounds34",
        slug="vaca-qlora-rounds-1-2", title="VACA QLoRA Rounds 1-2",
        nb="train_round2_kaggle.ipynb", meta="kernel-metadata-round2.json",
        subtitle=("Round 2 of 4 (resumes round-1 adapter, LR 1e-4) · single-GPU "
                  "(no torchrun) · Qwen2.5-7B-Instruct-Uncensored · GGUF q4_k_m"),
    ),
    "rounds34": dict(
        start_round=3, first_lr="5e-5", resume=True, next_kernel="round4",
        slug="vaca-qlora-rounds-3-4", title="VACA QLoRA Rounds 3-4",
        nb="train_rounds34_kaggle.ipynb", meta="kernel-metadata-rounds34.json",
        subtitle=("Round 3 of 4 (resumes round-2 adapter, LR 5e-5) · single-GPU "
                  "(no torchrun) · Qwen2.5-7B-Instruct-Uncensored · GGUF q4_k_m"),
    ),
    "round4": dict(
        start_round=4, first_lr="2.5e-5", resume=True, next_kernel="",
        slug="vaca-qlora-rounds-3-4", title="VACA QLoRA Rounds 3-4",
        nb="train_round4_kaggle.ipynb", meta="kernel-metadata-round4.json",
        subtitle=("Round 4 of 4 (resumes round-3 adapter, LR 2.5e-5) · single-GPU "
                  "(no torchrun) · Qwen2.5-7B-Instruct-Uncensored · GGUF q4_k_m"),
    ),
}


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}


NB_METADATA = {
    # Canonical Kaggle metadata block — the server only honors GPU/internet
    # when these exact fields are present (accelerator is the UI value).
    "kaggle": {
        # API machine_shape values per official kaggle-cli docs: NvidiaTeslaT4,
        # NvidiaTeslaP100, Tpu1VmV38 (GPU_T4_X2 is a web-UI label, not the API
        # enum — the server silently ran CPU on it).
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


def build_kernel(mode: str):
    """mode: 'rounds12' (fresh r1) | 'round2' (resume r2) |
             'rounds34' (resume r3) | 'round4' (resume r4)."""
    m = MODES[mode]
    start_round, first_lr, resume = m["start_round"], m["first_lr"], m["resume"]
    slug, title, subtitle = m["slug"], m["title"], m["subtitle"]
    nb_name, meta_name = m["nb"], m["meta"]

    # ─── Step 2: unzip attached inputs ───────────────────────────────────
    step2 = (
        "import zipfile, pathlib, shutil\n"
        "src = pathlib.Path('/kaggle/input/" + DATASET_SLUG + "')\n"
        "print('Attached inputs:', [p.name for p in src.iterdir()] if src.exists() else 'NONE — attach the dataset first!')\n"
        "assert src.exists(), 'Dataset not attached! Click +Add Input → Data → " + DATASET_SLUG + "'\n"
        "dst = pathlib.Path('/kaggle/working/dataset')\n"
        "dst.mkdir(exist_ok=True)\n"
        "zips = list(src.glob('*.zip'))\n"
        "if zips:\n"
        "    with zipfile.ZipFile(zips[0]) as z:\n"
        "        z.extractall(dst)\n"
        "elif list(src.glob('*.jsonl')):\n"
        "    for f in src.glob('*.jsonl'):\n"
        "        shutil.copy(f, dst / f.name)\n"
        "else:\n"
        "    raise SystemExit('No .zip or .jsonl found in the attached dataset!')\n"
        "print(sorted(p.name for p in dst.glob('*.jsonl')))\n"
    )
    if resume:
        step2 += (
            "\n"
            "# ── Resume adapter from the previous round ──\n"
            "ad = pathlib.Path('/kaggle/input/" + ADAPTER_SLUG + "')\n"
            "print('Adapter inputs:', [p.name for p in ad.iterdir()] if ad.exists() else 'NONE — attach vaca-rounds12-adapter!')\n"
            "assert ad.exists(), 'Adapter dataset not attached! (Add Input → Data → " + ADAPTER_SLUG + ")'\n"
            "ad_dst = pathlib.Path('/kaggle/working/adapter')\n"
            "ad_dst.mkdir(exist_ok=True)\n"
            "ad_zips = list(ad.glob('*.zip'))\n"
            "if ad_zips:\n"
            "    with zipfile.ZipFile(ad_zips[0]) as z:\n"
            "        z.extractall(ad_dst)\n"
            "elif (ad / 'adapter_config.json').exists():\n"
            "    shutil.copytree(ad, ad_dst, dirs_exist_ok=True)\n"
            "else:\n"
            "    raise SystemExit('No adapter.zip or adapter_config.json found!')\n"
            "print('Adapter files:', sorted(p.name for p in ad_dst.iterdir()))\n"
        )

    # ─── Step 3b: run cell (always plain single-GPU python, ROUNDS=1) ─────
    # torchrun DDP is UNRELIABLE here (verified 2026-08-01 across hardcoded,
    # count-based, and probe-based launches — rank 1 always died with
    # 'invalid device ordinal'). Never torchrun. ROUNDS=1 keeps each run under
    # Kaggle's 12 h cap (~6-10 h/round on 1× T4).
    run_cell = (
        "import os, subprocess, sys, torch\n"
        "# ── ROUNDS in THIS run ──\n"
        "# Kaggle caps runs at 12 h. 1 round ≈ 6-10 h on 1×T4, so ROUNDS=1 is\n"
        "# the safe default (2 rounds ≈ 16-24 h would hit the cap). Each round\n"
        "# saves its own adapter — resume the next round via the matching mode.\n"
        "ROUNDS = 1\n"
        "# ── Launch ──\n"
        "# torchrun DDP is UNRELIABLE here (Kaggle reports 2 T4s but grants 1\n"
        "# usable GPU → rank 1 'invalid device ordinal'; 3 failures 2026-08-01).\n"
        "# Always plain single-GPU python.\n"
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'\n"
        "# Kaggle reports 2 T4s but grants only 1 — pin to GPU 0 so unsloth's\n"
        "# fast attention doesn't scatter Q/K/V onto cuda:1 (device-mismatch\n"
        "# crash, verified 2026-08-01). train_round1.py does the same itself.\n"
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')\n"
        f"print('⚙️  Round {start_round} of 4 (LR {first_lr}) — plain single-GPU, ROUNDS=' + str(ROUNDS))\n"
        "base = ['train_round1.py', '--dataset', '/kaggle/working/dataset/train.jsonl',\n"
        "        '--out-dir', '/kaggle/working/out', '--rounds', str(ROUNDS),\n"
        f"        '--lr', '{first_lr}', '--start-round', '{start_round}',\n"
        "        '--epochs', '2', '--max-seq-length', '2048']\n"
        + ("base += ['--load-adapter', '/kaggle/working/adapter']\n" if resume else "")
        + "cmd = [sys.executable] + base\n"
        "print('RUN:', ' '.join(cmd))\n"
        "subprocess.run(cmd, check=True)\n"
    )

    cells = [
        md(
            f"# 🏆 VACA QLoRA Trainer — Round {start_round} of 4 (Kaggle)\n"
            "\n"
            f"Fine-tunes **Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) on the VACA "
            f"campaign-50 dataset — **round {start_round} of 4** (LR {first_lr}), "
            f"2 epochs, seq len 2048, LoRA r8/α16, GGUF q4_k_m export. "
            f"**Plain single-GPU python — no torchrun** (DDP is unreliable on this "
            f"Kaggle account: only 1 GPU is truly granted to the training subprocess).\n"
            "\n"
            "**Kaggle free:** 1× T4 usable, 12 h/run cap — one round ≈ 6–10 h, "
            "safely under the cap (ROUNDS=1).\n"
            "\n"
            f"{'**This kernel trains round 1 from the base model.**' if not resume else '**This kernel resumes round ' + str(start_round) + ' from the previous round\'s adapter** (attached `' + ADAPTER_SLUG + '`).'}\n"
            "\n"
            "**Output:** `/kaggle/working/out/results.zip` (this round's adapter + "
            "tuned GGUF ~4.4 GB). Download from the **Output** tab (top-right).\n"
            "\n"
            "**Steps:** ▶ Step 1 install → ▶ Step 2 unzip inputs → ▶ Step 3 train → "
            "▶ Step 4 show outputs."
        ),
        md("## Step 1 — Install dependencies\n"
           "~2–3 min. Internet is enabled for this kernel (needed for pip + Hugging Face)."),
        code(
            "!pip install -q unsloth trl transformers datasets accelerate\n"
            "import torch\n"
            "print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE', '| count:', torch.cuda.device_count())\n"
            "assert torch.cuda.is_available(), 'No GPU detected — enable GPU in the notebook settings!'\n"
            "print('✅ GPU ready — plain single-GPU run (no torchrun).')\n"
        ),
        md(f"## Step 2 — Unzip the attached inputs\n"
           f"The `{DATASET_SLUG}` input is attached to this kernel. "
           f"{'The `' + ADAPTER_SLUG + '` adapter input is attached too.' if resume else 'Extract it into `/kaggle/working/dataset/`.'}"),
        code(step2),
        md(f"## Step 3 — Train (round {start_round} of 4)\n"
           f"**Step 3a** writes the trainer script. **Step 3b** runs plain "
           f"single-GPU `python train_round1.py` (no torchrun — DDP is unreliable "
           f"on this account), **ROUNDS=1** to stay under the 12 h cap. "
           f"Round {start_round}, LR {first_lr}."
           + (f" After this completes, resume round {start_round + 1} by pushing "
              f"the next mode (--kernel {m['next_kernel']})."
              if m["next_kernel"] else "")),
        code("%%writefile train_round1.py\n" + SCRIPT),
        code(run_cell),
        md("## Step 4 — Show outputs\n"
           "After training, `results.zip` is in `/kaggle/working/out/`. "
           "Open the **Output** tab (top right) to download it."),
        code(
            "!ls -lh /kaggle/working/out/\n"
            "print('\\n✅ Done. Download /kaggle/working/out/results.zip from the Output tab.')\n"
            "print('Adapter dirs:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('adapter*')) if pathlib.Path('/kaggle/working/out').exists() else [])\n"
        ),
    ]

    nb = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": NB_METADATA,
        "cells": cells,
    }

    dataset_sources = [f"__USERNAME__/{DATASET_SLUG}"]
    if resume:
        dataset_sources.append(f"__USERNAME__/{ADAPTER_SLUG}")

    meta = {
        "id": f"__USERNAME__/{slug}",
        "title": title,
        "subtitle": subtitle,
        "code_file": nb_name,
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "machine_shape": "NvidiaTeslaT4",
        "language": "python",
        "kernel_type": "notebook",
        "dataset_sources": dataset_sources,
        "competition_sources": [],
        "kernel_sources": [],
    }

    (KAGGLE_DIR / nb_name).write_text(json.dumps(nb, indent=1))
    (KAGGLE_DIR / meta_name).write_text(json.dumps(meta, indent=2))
    print(f"✅ Wrote {nb_name} ({len(cells)} cells) + {meta_name} (round {start_round}, LR {first_lr})")


if __name__ == "__main__":
    for mode in MODES:
        build_kernel(mode)
    print("✅ All 4 kernel modes built.")
