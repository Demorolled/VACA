#!/usr/bin/env python3
"""
Build the Round-19 Kaggle notebook — Qwen2.5-Coder-14B CONTINUATION round.
============================================================================
    Dataset A: <user>/round19-corpus   (~1,900 rows capped for the 10h weekly quota:
                                        ALL code rows kept — R16 611 + ladder 155 +
                                        new verified captures + repair-pairs 9 ≈ 875,
                                        emotion fills the remaining ~1,025)
    Dataset B: <user>/vaca-r18-adapter  (the R18 trained LoRA — chained resume;
                                        requires training/cloud/out/round18/adapter)
    Kernel   : <user>/vaca-qlora-round19 (single-GPU T4, RESUMES the R18 LoRA)
    Trainer  : training/cloud/train_round1.py (verbatim, via %%writefile)

Round-19 config (continuation — mirrors R15→R16 chaining):
  1 epoch · batch 2 × grad-accum 4 (effective 8) · seq 3072 · LR 3e-5 (gentle)
  ≈ ~6-6.5 h on 1× T4 (14B) — comfortably under the 10h weekly quota.

  WHY resume: R19 continues the 14B chain from the R18 LoRA, teaching the new
  multi-file repair-pairs + captures without forgetting R18's knowledge, at a
  gentle LR 3e-5 single epoch so the run stays under the 10h Kaggle cap.

Usage:
  python3 scripts/build-r18-corpus.py                 # first: build the corpus
  python3 scripts/build-round19-kaggle-notebook.py    # then: build the notebook
  bash scripts/kaggle-setup-round19.sh                # push adapter + dataset + kernel
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()

DATASET_SLUG = "round19-corpus"
ADAPTER_SLUG = "vaca-r18-adapter"
KERNEL_SLUG = "vaca-qlora-round19"
NB_NAME = "train_r19_coder14_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-round19.json"
TITLE = "VACA QLoRA Round19"

_m = KAGGLE_DIR.parent / "round19.meta.json"
N_ROWS = json.loads(_m.read_text()).get("total_rows", 2000) if _m.exists() else 2000

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
    SEQ = 3072
    EST = "~6-6.5 h"
    SUBTITLE_NOTE = (
        f"R16 clean-code 611 + ladder-r1 155 + round7-emotion 1010 + verified 115 "
        f"+ repair-pairs 9 (incl. 3 multi-file); RESUMES the R18 LoRA, LR 3e-5, 1 ep, "
        f"batch 2 × accum 4, seq {SEQ}, single-GPU"
    )
    SUBTITLE = f"{N_ROWS} rows — {SUBTITLE_NOTE}"

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
        "# ── Dataset A: round-18 mixed corpus (code + emotion + repair pairs) ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round19-train.jsonl'",
        "assert ds.exists(), 'round19-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'rows (trainer splits 10% val internally)')",
        "",
        "# ── Dataset B: the R18 trained LoRA (chained resume) ──",
        "adapter_src = find_input('" + ADAPTER_SLUG + "')",
        "raw = pathlib.Path('/kaggle/working/adapters_raw')",
        "extract_all(adapter_src, raw)",
        "cand = None",
        "for p in raw.rglob('adapter_config.json'):",
        "    cand = p.parent",
        "    break",
        "assert cand is not None, 'adapter_config.json not found under ' + str(raw)",
        "adapter_dir = pathlib.Path('/kaggle/working/adapters/r18')",
        "adapter_dir.mkdir(parents=True, exist_ok=True)",
        "for f in cand.iterdir():",
        "    if f.is_file():",
        "        shutil.copy(f, adapter_dir / f.name)",
        "print('✅ R18 adapter ready:', adapter_dir)",
    ])

    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-19 config (resumes from the R18 LoRA — same chaining as R16←R15) ──",
        "EPOCHS = 1",
        "BATCH = 2                 # per-device batch (T4 16GB, seq " + str(SEQ) + ", 14B 4-bit)",
        "GRAD_ACCUM = 4            # effective batch = 2 × 4 = 8",
        "LR = 3e-5                 # gentle continuation (10h quota cap) — learn today's patterns without forgetting",
        "MODEL = 'BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored'",
        "ADAPTER = '/kaggle/working/adapters/r18'",
        "SEQ = " + str(SEQ),
        "# ── Launch ──",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "assert (pathlib.Path(ADAPTER) / 'adapter_model.safetensors').exists(), 'R18 adapter missing'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 19 | base={MODEL} | resume={ADAPTER} | LR {LR:.1e} | EPOCHS={EPOCHS} | batch {BATCH} × accum {GRAD_ACCUM} | seq {SEQ} | --no-gguf (merged 16-bit)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round19-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '19',",
        "       '--load-adapter', ADAPTER,",
        "       '--lr', str(LR), '--epochs', str(EPOCHS),",
        "       '--batch-size', str(BATCH),",
        "       '--grad-accum', str(GRAD_ACCUM),",
        "       '--model-name', MODEL,",
        "       '--no-gguf',",
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
        "# ── SANITY: the saved round-18 adapter must contain real training deltas ──",
        "saved = pathlib.Path('/kaggle/working/out/adapter_round19/adapter_model.safetensors')",
        "assert saved.exists(), f'❌ adapter missing: {saved}'",
        "sz = saved.stat().st_size",
        "print(f'✅ Round-18 adapter present: {sz/1e6:.1f} MB (nonzero = weights written)')",
        "assert sz > 1_000_000, '❌ adapter implausibly small — training may not have applied!'",
        "print('✅ SANITY OK — deploy via scripts/download-round19-merged.py + deploy-round19.sh')",
    ])

    # Trainer cell — verbatim copy of train_round1.py via %%writefile
    trainer_cell = code("""
%%writefile train_round1.py
""" + SCRIPT.rstrip() + """
""")

    cells = [
        md(f"# 🧠 VACA Round-19 — Qwen2.5-Coder-14B continuation (resumes R18)\n\n"
           f"{SUBTITLE}\n\n"
           f"**Corpus: {N_ROWS} rows** = the R18 corpus PLUS the new multi-file "
           f"captures and the 9 teacher repair-pairs (incl. 3 multi-file). **Resumes the "
           f"R18 LoRA** (chained like R16←R15) at LR 3e-5 so the model learns the "
           f"new patterns without forgetting. Single-GPU (no torchrun). "
           f"Estimated {EST} on 1× T4."),
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
