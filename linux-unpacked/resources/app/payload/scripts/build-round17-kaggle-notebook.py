#!/usr/bin/env python3
"""
Build the Round-17 Kaggle notebook — first Qwen2.5-Coder-14B round.
====================================================================
    Dataset : <user>/round17-corpus    (2,063 rows: R16 clean-code 611 +
                                        ladder-r1 155 + round7-emotion 1275 +
                                        current verified 22; mixed code+emotion)
    Kernel  : <user>/vaca-qlora-round17 (single-GPU T4, fresh base, no resume)
    Trainer : training/cloud/train_round1.py (verbatim, via %%writefile)

Round-17 config:
  1 epoch · batch 2 × grad-accum 4 (effective 8) · seq 3072 · LR 1.5e-4
  ≈ ~258 optimizer steps ≈ ~6.5 h on 1× T4 (14B is ~2× the 7B's per-step cost;
  kept under the ~12 h Kaggle session cap).

  WHY 14B: the ladder (17 builds measured) showed the 7B's ceiling is
  reliability, not capability — same goal re-runs swing 0 → 66 errors. The
  coder-specialized uncensored 14B is ~2× the capability for the same
  unrestricted behavior, and this round is its FIRST fine-tune: it carries the
  7B's full knowledge as DATA (R16 clean-code corpus + ladder verified rows +
  the round7-emotion register that R16's code-focused corpus dropped).

Usage:
  python3 scripts/build-r17-corpus.py               # first: build the corpus
  python3 scripts/build-round17-kaggle-notebook.py
  python3 scripts/validate-cloud-notebooks.py       # compile-check all cells
  bash scripts/kaggle-setup-round17.sh              # push dataset + kernel

Fallback mode (--fallback): for a one-command restart when the full kernel
misses the 12h T4 cap. Pairs with `build-r17-corpus.py --max-rows 1500`:
seq drops to 2048 and the estimated runtime shrinks to ~4-5 h.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"

DATASET_SLUG = "round17-corpus"
KERNEL_SLUG = "vaca-qlora-round17"
NB_NAME = "train_r17_coder14_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-round17.json"
TITLE = "VACA QLoRA Round17"

_m = KAGGLE_DIR.parent / "round17.meta.json"
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


def build(fallback: bool = False):
    SEQ = 2048 if fallback else 3072
    EST = "~4-5 h" if fallback else "~6.5 h"
    if fallback:
        SUBTITLE_NOTE = (
            f"FALLBACK RESTART — trimmed corpus ({N_ROWS} rows, code preserved, "
            f"emotion trimmed) · 1 ep · batch 2 × accum 4 · seq 2048 · ~4-5 h on 1× T4"
        )
    else:
        SUBTITLE_NOTE = (
            f"R16 clean-code 611 + ladder-r1 155 + round7-emotion 1275 + verified 22; "
            f"fresh base, LR 1.5e-4, 1 ep, batch 2 × accum 4, seq 3072, single-GPU"
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
        "# ── Dataset: round-17 mixed corpus (code + emotion) ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round17-train.jsonl'",
        "assert ds.exists(), 'round17-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'rows (trainer splits 10% val internally)')",
    ])

    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-17 config: FRESH 14B coder base (no resume — new architecture) ──",
        "EPOCHS = 1",
        "BATCH = 2                 # per-device batch (T4 16GB, seq " + str(SEQ) + ", 14B 4-bit)",
        "GRAD_ACCUM = 4            # effective batch = 2 × 4 = 8",
        "LR = 1.5e-4               # fresh base, mixed corpus (R16 was 5e-5 continuation)",
        "MODEL = 'BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored'",
        "SEQ = " + str(SEQ) + ("  # FALLBACK: seq 2048 to fit the 12h T4 session cap" if fallback else ""),
        "# ── Launch ──",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 17 | base={MODEL} | LR {LR:.1e} | EPOCHS={EPOCHS} | batch {BATCH} × accum {GRAD_ACCUM} | seq {SEQ} | --no-gguf (merged 16-bit)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round17-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '17',",
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
        "import pathlib, hashlib",
        "print('\\\\n✅ Done. Download /kaggle/working/out/results.zip (adapter) + the merged *.safetensors files from the Output tab.')",
        "print('Adapter dirs:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('adapter*')) if pathlib.Path('/kaggle/working/out').exists() else [])",
        "",
        "# ── SANITY: the saved round-17 adapter must contain real training deltas ──",
        "saved = pathlib.Path('/kaggle/working/out/adapter_round17/adapter_model.safetensors')",
        "assert saved.exists(), f'❌ adapter missing: {saved}'",
        "sz = saved.stat().st_size",
        "print(f'✅ Round-17 adapter present: {sz/1e6:.1f} MB (nonzero = weights written)')",
        "assert sz > 1_000_000, '❌ adapter implausibly small — training may not have applied!'",
        "print('✅ SANITY OK — deploy via scripts/download-round17-merged.py + deploy-round17.sh')",
    ])

    # Trainer cell — verbatim copy of train_round1.py via %%writefile
    trainer_cell = code("""
%%writefile train_round1.py
""" + SCRIPT.rstrip() + """
""")

    cells = [
        md(f"# 🧠 VACA Round-17 — Qwen2.5-Coder-14B-Instruct-Uncensored\n\n"
           f"{SUBTITLE}\n\n"
           f"**Corpus: {N_ROWS} rows.** The 7B's knowledge carries over as *data* "
           f"(R16 clean-code corpus + ladder-R1 verified modules + the restored "
           f"round7-emotion register). Fresh base = no resume adapter. Single-GPU "
           f"(no torchrun). Estimated {EST} on 1× T4."),
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
        "dataset_sources": ["__USERNAME__/" + DATASET_SLUG],
        "kernel_sources": [],
        "model_sources": [],
    }
    (KAGGLE_DIR / KERNEL_META_NAME).write_text(json.dumps(meta, indent=2) + "\n")
    print(f"✅ Wrote {KAGGLE_DIR / KERNEL_META_NAME}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build R17 Kaggle notebook")
    ap.add_argument("--fallback", action="store_true",
                    help="Build the trimmed fallback notebook (seq 2048). Pair with build-r17-corpus.py --max-rows 1500.")
    args = ap.parse_args()
    build(fallback=args.fallback)
