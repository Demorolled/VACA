#!/usr/bin/env python3
"""
Build the Round-20 Kaggle notebook — Qwen2.5-Coder-14B ORPO (preference) round.
================================================================================
    Dataset A: <user>/round20-orpo-corpus   (instruction/chosen/rejected pairs —
                                            the model's tsc-clean finals vs its
                                            OWN broken first drafts, #62/#63)
    Dataset B: <user>/vaca-r19-adapter      (the deployed R19 LoRA — resume point)
    Kernel   : <user>/vaca-qlora-round20    (single-GPU T4, ORPOTrainer via
                                            train_round1.py --train-type orpo)
    Trainer  : training/cloud/train_round1.py (verbatim, via %%writefile)

Round-20 config (preference tuning on top of R19) — QUOTA-FIT v3 (2026-08-17):
  v1 OOM'd on the first step (torch.OutOfMemoryError, 14.56 GiB T4 full at
  0/12): ORPOTrainer computes logits for BOTH chosen and rejected per row, so
  batch 2 × seq 3072 (which SFT survived) needs ~2× SFT's activation memory.
  v2 (batch 1 × accum 8 · seq 2048) ran 6/12 steps then OOM'd trying to
  allocate 686 MiB with only ~380 MiB free — just barely over the T4.
  v3: seq 2048 → 1280 (measured: p50 ≈ 330 / p90 ≈ 610 / p99 ≈ 1074 tokens;
  only ONE 7800-char outlier needs >1280) frees ~1.3 GB activation memory
  ≈ comfortable margin. Training ~8 min @ 40s/step → kernel ~15-18 min.
  Rest: batch 1 × grad-accum 8 · PYTORCH_ALLOC_CONF=expandable_segments:True
  · LR 1e-5 · β=0.1 · 1 epoch · --skip-merge --skip-eval (adapter only,
  no in-kernel merge — the R19 OOM spot; merge locally)

  WHY ORPO: SFT rounds teach the model to WRITE working code; ORPO teaches it
  to PREFER its own verified output over its own broken drafts — the
  self-improvement loop's missing half (the R19 session's parked milestone).

Usage:
  python3 scripts/build-r20-orpo-corpus.py             # first: corpus
  python3 scripts/build-round20-kaggle-notebook.py     # then: notebook
  bash scripts/kaggle-setup-round20.sh                 # push dataset + kernel
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()

DATASET_SLUG = "round20-orpo-corpus"
ADAPTER_SLUG = "vaca-r19-adapter"
KERNEL_SLUG = "vaca-qlora-round20-orpo"  # NOTE: the actual slug (title "VACA QLoRA Round20 (ORPO)" resolves with the -orpo suffix — the v1 push warned about this; using the real slug so v2 updates the SAME kernel)
NB_NAME = "train_r20_orpo_coder14_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-round20.json"
TITLE = "VACA QLoRA Round20 (ORPO)"

_m = KAGGLE_DIR.parent / "round20.meta.json"
N_PAIRS = json.loads(_m.read_text()).get("pairs", 100) if _m.exists() else 100

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
    SEQ = 1280  # v3: v2 OOM'd at step 7/12 (needed 686 MiB, had ~380 free); 1280 covers p99 ≈ 1074 tokens, truncates only the single 7800-char outlier
    setup_cell = jn([
        "# ── Install (R16 v2 lesson: explicit cell so the base 14B loads clean) ──",
        "!pip install -q unsloth trl transformers datasets accelerate peft",
        "import torch",
        "assert torch.cuda.is_available(), '❌ No GPU — enable GPU in notebook settings (T4 x1 or x2)'",
        "print('✅ CUDA:', torch.cuda.get_device_name(0))",
        "import unsloth",
        "print('✅ unsloth', unsloth.__version__)",
    ])

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
        "# ── Dataset A: Round-20 ORPO corpus (preference pairs) ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round20-orpo-train.jsonl'",
        "assert ds.exists(), 'round20-orpo-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'ORPO pairs (trainer splits 10% val internally)')",
        "",
        "# ── Dataset B: the R19 trained LoRA (resume point — the deployed model) ──",
        "adapter_src = find_input('" + ADAPTER_SLUG + "')",
        "raw = pathlib.Path('/kaggle/working/adapters_raw')",
        "extract_all(adapter_src, raw)",
        "cand = None",
        "for p in raw.rglob('adapter_config.json'):",
        "    cand = p.parent",
        "    break",
        "assert cand is not None, 'adapter_config.json not found under ' + str(raw)",
        "adapter_dir = pathlib.Path('/kaggle/working/adapters/r19')",
        "adapter_dir.mkdir(parents=True, exist_ok=True)",
        "for f in cand.iterdir():",
        "    if f.is_file():",
        "        shutil.copy(f, adapter_dir / f.name)",
        "print('✅ R19 adapter ready:', adapter_dir)",
    ])

    run_cell = jn([
        "import os, subprocess, sys, torch, pathlib",
        "# ── Round-20 config v3 (ORPO preference tuning, resumes the R19 LoRA) ──",
        "# v1 OOM'd at step 0, v2 at step 7/12 (needed 686 MiB, had ~380 free).",
        "# v3: seq 2048 → 1280 — measured corpus p99 ≈ 1074 tokens (only ONE",
        "# 7800-char outlier exceeds 1280), frees ~1.3 GB activation memory.",
        "EPOCHS = 1                  # quota-fit: 12 steps ≈ ~8 min @ 40s/step",
        "BATCH = 1                   # ORPO needs ~2× SFT memory — batch 1 is the safe equivalent of SFT batch 2",
        "GRAD_ACCUM = 8              # effective batch = 1 × 8 = 8 (accum is memory-free)",
        "LR = 1e-5                   # gentle — ORPO must refine, not rewrite, R19",
        "ORPO_BETA = 0.1             # TRL default",
        "MODEL = 'BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored'",
        "ADAPTER = '/kaggle/working/adapters/r19'",
        "SEQ = " + str(SEQ),
        "# ── Launch ──",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "assert (pathlib.Path(ADAPTER) / 'adapter_model.safetensors').exists(), 'R19 adapter missing'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "os.environ.setdefault('PYTORCH_ALLOC_CONF', 'expandable_segments:True')",
        "print(f'⚙️  Round 20 v3 | ORPO | base={MODEL} | resume={ADAPTER} | LR {LR:.1e} | β={ORPO_BETA} | EPOCHS={EPOCHS} | batch {BATCH} × accum {GRAD_ACCUM} | seq {SEQ} | --no-gguf --skip-merge --skip-eval')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round20-orpo-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '20',",
        "       '--load-adapter', ADAPTER,",
        "       '--lr', str(LR), '--epochs', str(EPOCHS),",
        "       '--batch-size', str(BATCH),",
        "       '--grad-accum', str(GRAD_ACCUM),",
        "       '--model-name', MODEL,",
        "       '--train-type', 'orpo', '--orpo-beta', str(ORPO_BETA),",
        "       '--no-gguf', '--skip-merge', '--skip-eval',",
        "       '--max-seq-length', str(SEQ)]",
        "print('RUN:', ' '.join(cmd))",
        "subprocess.run(cmd, check=True)",
    ])

    out_cell = jn([
        "!ls -lh /kaggle/working/out/",
        "import pathlib",
        "print('\\n✅ Done. Download /kaggle/working/out/results.zip (adapter) + the merged *.safetensors files from the Output tab.')",
        "print('Adapter dirs:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('adapter*')) if pathlib.Path('/kaggle/working/out').exists() else [])",
        "",
        "# ── SANITY: the saved round-20 adapter must contain real training deltas ──",
        "saved = pathlib.Path('/kaggle/working/out/adapter_round20/adapter_model.safetensors')",
        "assert saved.exists(), f'❌ adapter missing: {saved}'",
        "sz = saved.stat().st_size",
        "print(f'✅ Round-20 adapter present: {sz/1e6:.1f} MB (nonzero = weights written)')",
        "assert sz > 1_000_000, '❌ adapter implausibly small — training may not have applied!'",
        "print('✅ SANITY OK — merge locally: build-r19-merged.py pattern (no in-kernel merge, R19 OOM lesson); deploy via download/deploy scripts')",
    ])

    # Trainer cell — verbatim copy of train_round1.py via %%writefile
    trainer_cell = code("""
%%writefile train_round1.py
""" + SCRIPT.rstrip() + """
""")

    cells = [
        md(f"# 🧠 VACA Round-20 v3 — Qwen2.5-Coder-14B ORPO (preference tuning)\\n\\n"
           f"**{N_PAIRS} ORPO pairs** = the model's own tsc-clean finals (chosen) vs its own "
           f"broken first drafts (rejected) — captured by snapshotFirstDrafts (#62) + "
           f"build-orpo-pairs.py. **v3 fixes the v2 OOM** (batch 1 × accum 8, seq 2048 ran "
           f"6/12 steps then OOM'd — needed 686 MiB with ~380 free): seq → 1280 (measured "
           f"p99 ≈ 1074 tokens; only one outlier pair truncates) frees ~1.3 GB ⇒ ~8 min "
           f"training, ~15-18 min kernel — fits the 1h40m weekly budget with margin. "
           f"Resumes the R19 LoRA at LR 1e-5, β={0.1}, 1 epoch. Adapter-only save (no in-kernel "
           f"16-bit merge — the R19 OOM spot); merge locally after download. Single-GPU."),
        code("!nvidia-smi"),
        code(setup_cell),
        code(step2),
        trainer_cell,
        code(run_cell),
        code(out_cell),
    ]

    nb = {
        "cells": cells,
        "metadata": NB_METADATA,
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    out_nb = KAGGLE_DIR / NB_NAME
    out_nb.write_text(json.dumps(nb, indent=1))
    print(f"✅ Wrote {out_nb} ({len(cells)} cells)")

    # ── Kernel metadata (title-slug 409 guard: R16 v2 lesson) ──
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
        "dataset_sources": [
            "__USERNAME__/" + DATASET_SLUG,
            "__USERNAME__/" + ADAPTER_SLUG,
        ],
        "kernel_sources": [],
        "model_sources": [],
    }
    meta_path = KAGGLE_DIR / KERNEL_META_NAME
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"✅ Wrote {meta_path}")


if __name__ == "__main__":
    build()
