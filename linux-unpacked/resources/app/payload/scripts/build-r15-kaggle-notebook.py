#!/usr/bin/env python3
"""
Build the Round-15 Kaggle notebook — GUI + 3D breadth round.
============================================================
    Dataset A : <user>/round15-gui        (R14's own passing GUI apps +
                                          GUI QA rules + r14probe/rook/chess
                                          + whole 3D re-exposure + R14
                                          retention)
    Dataset B : <user>/vaca-r14-adapter   (the R14 trained LoRA — chained)
    Kernel    : <user>/vaca-qlora-round15 (single-GPU T4, no torchrun)
    Trainer   : training/cloud/train_round1.py (verbatim, via %%writefile —
                with the save-bug fix)

Round-15 config:
  3 epochs · grad-accum 4 · seq 3072 · LR 5e-5 → ~N train rows ⇒ ~N optimizer
  steps ≈ ~50–70 min on 1× T4.

Usage:
  python3 scripts/combine-r15.py                 # first: build the dataset
  python3 scripts/build-r15-kaggle-notebook.py
  python3 scripts/validate-cloud-notebooks.py    # compile-check all cells
  bash scripts/kaggle-setup-round15.sh           # push datasets + kernel
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"

DATASET_SLUG = "round15-gui"
ADAPTER_SLUG = "vaca-r14-adapter"
KERNEL_SLUG = "vaca-qlora-round15"
NB_NAME = "train_r15_gui_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-round15.json"
TITLE = "VACA QLoRA Round15"
SUBTITLE = ("Round 15 GUI+3D breadth (R14's own passing GUI apps as generation-framed rows + "
            "GUI QA rules + 3D defect rules; resume from R14 LoRA; LR 5e-5; 3 ep; accum 4; seq 3072; single-GPU)")

_m = KAGGLE_DIR.parent / "round15-gui.meta.json"
N_ROWS = json.loads(_m.read_text()).get("total_rows", 100) if _m.exists() else 100

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
        "# ── Dataset A: round-15 GUI+3D training rows ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round15-gui-train.jsonl'",
        "assert ds.exists(), 'round15-gui-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'rows (trainer splits 10% val internally)')\n",
        "# ── Dataset B: the R14 trained LoRA (chained) ──",
        "adapter_src = find_input('" + ADAPTER_SLUG + "')",
        "raw = pathlib.Path('/kaggle/working/adapters_raw')",
        "extract_all(adapter_src, raw)",
        "cand = None",
        "for p in raw.rglob('adapter_config.json'):",
        "    cand = p.parent",
        "    break",
        "assert cand is not None, 'adapter_config.json not found under ' + str(raw)",
        "adapter_dir = pathlib.Path('/kaggle/working/adapters/r14')",
        "adapter_dir.mkdir(parents=True, exist_ok=True)",
        "for f in cand.iterdir():",
        "    if f.is_file():",
        "        shutil.copy(f, adapter_dir / f.name)",
        "print('✅ R14 adapter ready:', adapter_dir)",
    ])

    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-15 GUI+3D config (resumes from the R14 LoRA) ──",
        "EPOCHS = 3",
        "GRAD_ACCUM = 4",
        "LR = 5e-5                # gentle continuation — GUI breadth round",
        "ADAPTER = '/kaggle/working/adapters/r14'",
        "# ── Launch ──",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 15 | LR {LR:.1e} | EPOCHS={EPOCHS} | grad-accum {GRAD_ACCUM} | resume={ADAPTER} | --no-gguf (merged 16-bit)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round15-gui-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '15',",
        "       '--lr', str(LR), '--epochs', str(EPOCHS),",
        "       '--grad-accum', str(GRAD_ACCUM),",
        "       '--load-adapter', ADAPTER,",
        "       '--no-gguf',",
        "       '--max-seq-length', '3072']",
        "print('RUN:', ' '.join(cmd))",
        "subprocess.run(cmd, check=True)",
    ])

    out_cell = jn([
        "!ls -lh /kaggle/working/out/",
        "import pathlib, hashlib",
        "print('\\\\n✅ Done. Download /kaggle/working/out/results.zip (adapter) + the merged *.safetensors files from the Output tab.')",
        "print('Adapter dirs:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('adapter*')) if pathlib.Path('/kaggle/working/out').exists() else [])",
        "print('Merged safetensors:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('*.safetensors')) if pathlib.Path('/kaggle/working/out').exists() else [])",
        "",
        "# ── SANITY: the saved round adapter MUST differ from the loaded R14 LoRA ──",
        "def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()",
        "saved = pathlib.Path('/kaggle/working/out/adapter_round15/adapter_model.safetensors')",
        "loaded = pathlib.Path('/kaggle/working/adapters/r14/adapter_model.safetensors')",
        "if saved.exists() and loaded.exists():",
        "    sa, lb = _sha(saved), _sha(loaded)",
        "    if sa == lb:",
        "        print('❌❌ SANITY FAIL: round-15 adapter == loaded R14 adapter — training did NOT apply! Do not deploy.'); raise SystemExit(1)",
        "    print('✅ SANITY OK: round-15 adapter differs from loaded R14 adapter (training applied).')",
        "else:",
        "    print('⚠️  sanity check skipped (missing adapter files).')",
    ])

    cells = [
        md(jn([
            "# 🧠 Round 15 — GUI + 3D Breadth, RESUMING from the R14 LoRA",
            "",
            "Fine-tunes **Orion-zhen/Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) ",
            "**resuming from the round-14 trained LoRA** (uploaded as dataset B). Round ",
            "15 adds the FIRST GUI-app signal: the R14 GUI battery's own passing apps ",
            "(dashboard, kanban, chat, terminal, spreadsheet, ...) as generation-framed ",
            "rows, plus GUI QA rules for the classes it still shows (null DOM refs, ",
            "missing init guard, script ordering), plus the 3D defect rules from the ",
            "R14 3D probe (addon rule, scope-in-animate, hallucinated API, CDN case).",
            "",
            "| Source | Rows | Why |",
            "|---|---|---|",
            f"| `chunk-gui-verified.jsonl` | fresh | NEW signal (R14's passing GUI apps + GUI QA rules) |",
            f"| `chunk-3d-r14probe.jsonl` | 7 | NEW (3 RAW-pass 3D apps + 4 QA rules) |",
            f"| `chunk-3d-rook.jsonl` | 2 | NEW (rook QA rules) |",
            f"| `chunk-3d-chess.jsonl` | 2 | NEW (chess QA rules) |",
            f"| 3D corpus (genfix/random/defects/3d) | 82 | re-exposure (repetition) |",
            f"| `round14-genfix-train.jsonl` | ~18 | retention slice (anti-regression) |",
            f"**Total** | **{N_ROWS}** | ~{N_ROWS // 4 * 3} optimizer steps ≈ {N_ROWS // 4 * 3 * 45 / 60:.0f} min @ seq 3072 on 1× T4 |",
            "",
            "**Round 15** (LR 5e-5), **3 epochs, grad-accum 4**, seq 3072, LoRA r8/α16. ",
            "**`--no-gguf`** — merged 16-bit safetensors export; q4_k_m rebuilt locally.",
            "",
            "**Save-bug guard (round-11 lesson):** the trainer promotes the trained LoRA ",
            "from unsloth's `resume/` subdir, merges via `merge_and_unload()` on the live ",
            "model, and runs a **sha sanity check** that the saved adapter differs from the ",
            "loaded one — a silently-untrained kernel fails loudly.",
            "",
            "**Output:** `/kaggle/working/out/` → `results.zip` (adapter_round15/) + ",
            "`model.safetensors` + config. Download from the **Output** tab.",
            "",
            "**After download (back on the local machine):**",
            "```",
            "python3 scripts/download-round15-merged.py",
            "bash scripts/deploy-round15.sh                  # convert→q4_k_m, deploy, drop R14",
            "```",
            "",
            "**Steps:** ▶ Step 1 install → ▶ Step 2 copy inputs → ▶ Step 3 train → ",
            "▶ Step 4 show outputs + sanity.",
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
           f"**Dataset A** `{DATASET_SLUG}` (GUI+3D rows) and **Dataset B** "
           f"`{ADAPTER_SLUG}` (the R14 trained LoRA — chaining base) are attached "
           "to this kernel. Copy both into `/kaggle/working/`."),
        code(step2),
        md("## Step 3 — Train (Round 15, resume from R14)\n"
           "**Step 3a** writes the trainer script (with the save-bug fix). "
           "**Step 3b** runs plain single-GPU `python train_round1.py` with "
           "`--load-adapter <R14 LoRA>`, 3 epochs, grad-accum 4 and `--no-gguf`."),
        code("%%writefile train_round1.py\n" + SCRIPT),
        code(run_cell),
        md("## Step 4 — Show outputs + sanity check\n"
           "List the training artifacts and verify the saved round-15 adapter differs "
           "from the loaded R14 LoRA (guards against the round-11 save bug)."),
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
    print(f"[round15-gui] wrote {KAGGLE_DIR / NB_NAME}")
    print(f"[round15-gui] wrote {KAGGLE_DIR / KERNEL_META_NAME} (N_ROWS={N_ROWS})")


if __name__ == "__main__":
    build()
