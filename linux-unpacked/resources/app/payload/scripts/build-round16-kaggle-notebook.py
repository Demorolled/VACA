#!/usr/bin/env python3
"""
Build the Round-16 Kaggle notebook — Anti-Fence Clean round.
============================================================
    Dataset A : <user>/round16-antifence   (clean-only corpus: rounds 10-15
                                           re-filtered through the VACA
                                           isQualityCode gate + verified
                                           generations; 552 train rows)
    Dataset B : <user>/vaca-r15-adapter    (the R15 trained LoRA — chained;
                                           requires the R15 adapter on disk
                                           at training/cloud/out/round15/adapter)
    Kernel    : <user>/vaca-qlora-round16  (single-GPU T4, no torchrun)
    Trainer   : training/cloud/train_round1.py (verbatim, via %%writefile)

Round-16 config:
  3 epochs · grad-accum 4 · seq 3072 · LR 5e-5 → 414 optimizer steps
  ≈ ~5.2 h on 1× T4 (clean corpus is bigger than R15's 108 rows).

  WHY: rounds 10-14 (the deployed R15 model's lineage) contained training rows
  whose OUTPUT was markdown-fenced/batched chat format. R16 retrains ONLY on
  rows whose output passes the poison gate, so the model re-learns raw-code
  output. Every row in this corpus is fence-free by construction.

Usage:
  python3 scripts/build-r16-antifence-corpus.py   # first: build the dataset
  python3 scripts/build-round16-kaggle-notebook.py
  python3 scripts/validate-cloud-notebooks.py     # compile-check all cells
  bash scripts/kaggle-setup-round16.sh            # push datasets + kernel
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"

DATASET_SLUG = "round16-antifence"
ADAPTER_SLUG = "vaca-r15-adapter"
KERNEL_SLUG = "vaca-qlora-round16"
NB_NAME = "train_r16_antifence_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-round16.json"
TITLE = "VACA QLoRA Round16"
SUBTITLE = ("Round 16 anti-fence clean round (all rows pass the isQualityCode gate; "
            "resume from R15 LoRA; LR 5e-5; 3 ep; accum 4; seq 3072; single-GPU)")

_m = KAGGLE_DIR.parent / "round16-antifence.meta.json"
N_ROWS = json.loads(_m.read_text()).get("total_rows", 600) if _m.exists() else 600

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
        "# ── Dataset A: round-16 clean-only anti-fence corpus ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round16-antifence-train.jsonl'",
        "assert ds.exists(), 'round16-antifence-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'rows (trainer splits 10% val internally)')\n",
        "# ── Dataset B: the R15 trained LoRA (chained) ──",
        "adapter_src = find_input('" + ADAPTER_SLUG + "')",
        "raw = pathlib.Path('/kaggle/working/adapters_raw')",
        "extract_all(adapter_src, raw)",
        "cand = None",
        "for p in raw.rglob('adapter_config.json'):",
        "    cand = p.parent",
        "    break",
        "assert cand is not None, 'adapter_config.json not found under ' + str(raw)",
        "adapter_dir = pathlib.Path('/kaggle/working/adapters/r15')",
        "adapter_dir.mkdir(parents=True, exist_ok=True)",
        "for f in cand.iterdir():",
        "    if f.is_file():",
        "        shutil.copy(f, adapter_dir / f.name)",
        "print('✅ R15 adapter ready:', adapter_dir)",
    ])

    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-16 anti-fence config (resumes from the R15 LoRA) ──",
        "EPOCHS = 3",
        "GRAD_ACCUM = 4",
        "LR = 5e-5                # gentle continuation — clean-corpus remediation",
        "ADAPTER = '/kaggle/working/adapters/r15'",
        "# ── Launch ──",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 16 | LR {LR:.1e} | EPOCHS={EPOCHS} | grad-accum {GRAD_ACCUM} | resume={ADAPTER} | --no-gguf (merged 16-bit)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round16-antifence-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '16',",
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
        "",
        "# ── SANITY: the saved round-16 adapter MUST differ from the loaded R15 LoRA ──",
        "def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()",
        "saved = pathlib.Path('/kaggle/working/out/adapter_round16/adapter_model.safetensors')",
        "loaded = pathlib.Path('/kaggle/working/adapters/r15/adapter_model.safetensors')",
        "if saved.exists() and loaded.exists():",
        "    sa, lb = _sha(saved), _sha(loaded)",
        "    if sa == lb:",
        "        print('❌❌ SANITY FAIL: round-16 adapter == loaded R15 adapter — training did NOT apply! Do not deploy.'); raise SystemExit(1)",
        "    print('✅ SANITY OK: round-16 adapter differs from loaded R15 adapter (training applied).')",
        "else:",
        "    print('⚠️  sanity check skipped (missing adapter files).')",
    ])

    cells = [
        md(jn([
            "# 🧠 Round 16 — Anti-Fence Clean Corpus (REMEDIATION), RESUMING from the R15 LoRA",
            "",
            "Fine-tunes **Orion-zhen/Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) **resuming from the ",
            "round-15 trained LoRA** (uploaded as dataset B). **Why:** rounds 10-14 (the deployed R15 ",
            "model's lineage, all run on Kaggle) contained training rows whose OUTPUT was the ",
            "markdown-fenced / batched chat format — the exact failure signature seen in VACA's generated ",
            "source files (`input.ts`, `cheese.ts`, `todo-app/`). Round 16 retrains **only on rows whose ",
            "output passes the same poison gate the VACA app uses** (`isQualityCode`): no ``` fences, no ",
            "`---` separators, no prompt artifacts, no prose explanations, no stub bodies.",
            "",
            "| Source | Rows kept | Why |",
            "|---|---|---|",
            f"| R10 GUI corpus (fence-filtered) | 469 | NEW signal — clean form never trained |",
            f"| R11 mix-a (fence-filtered) | 40 | NEW signal |",
            f"| R12 defects (fence-filtered) | 21 | NEW signal |",
            f"| R13 random (fence-filtered) | 22 | NEW signal |",
            f"| R14 genfix (fence-filtered) | 20 | NEW signal |",
            f"| R15 GUI (retention) | 24 | re-exposure (already trained clean) |",
            f"| verified-generations (tsc-gated) | 12 | always-clean capture path |",
            f"| vaca-build-fixes (curated) | 5 | repair-pair rows from triage failures |",
            f"**Total** | **{N_ROWS}** | ~414 optimizer steps ≈ ~5.2 h @ seq 3072 on 1× T4 |",
            "",
            "**Poison rejected by the gate:** 147 fence rows, 199 prose rows, 1 separator row.",
            "",
            "**Round 16** (LR 5e-5), **3 epochs, grad-accum 4**, seq 3072, LoRA r8/α16. ",
            "**`--no-gguf`** — merged 16-bit safetensors export; q4_k_m rebuilt locally.",
            "",
            "**Save-bug guard (round-11 lesson):** the trainer promotes the trained LoRA from unsloth's ",
            "`resume/` subdir, merges via `merge_and_unload()` on the live model, and runs a **sha sanity ",
            "check** that the saved adapter differs from the loaded one — a silently-untrained kernel fails loudly.",
            "",
            "**Output:** `/kaggle/working/out/` → `results.zip` (adapter_round16/) + `model.safetensors` + config. ",
            "Download from the **Output** tab.",
        ])),
        md("## 1. Install dependencies\n"
           "~2–3 min. Internet is enabled for this kernel (needed for pip + Hugging Face)."),
        code(jn([
            "!pip install -q unsloth trl transformers datasets accelerate",
            "import torch",
            "print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE', '| count:', torch.cuda.device_count())",
            "assert torch.cuda.is_available(), 'No GPU detected — enable GPU in the notebook settings!'",
            "print('✅ GPU ready — plain single-GPU run (no torchrun).')",
        ])),
        md("## 2. Load the trainer script"),
        code("%%writefile train_round1.py\n" + SCRIPT),
        md("## 3. Attach datasets (A: round16-antifence, B: vaca-r15-adapter)"),
        code(step2),
        md("## 4. Train (single GPU, resumes R15 → R16)"),
        code(run_cell),
        md("## 5. Verify output"),
        code(out_cell),
    ]

    nb = {
        "cells": cells,
        "metadata": NB_METADATA,
        "nbformat": 4,
        "nbformat_minor": 0,
    }
    (KAGGLE_DIR / NB_NAME).write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print(f"✅ Wrote {KAGGLE_DIR / NB_NAME} (round 16, {N_ROWS} rows → ~414 steps ≈ ~5.2 h on T4)")


if __name__ == "__main__":
    build()
