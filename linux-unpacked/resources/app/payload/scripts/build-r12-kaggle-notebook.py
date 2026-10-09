#!/usr/bin/env python3
"""
Build the Round-12 defects Kaggle notebook — 3D probe-failure fix round.
============================================================================
    Dataset A : <user>/round12-defects      (defect-fix rows + 3D re-exposure
                                             + round-11 retention slice)
    Dataset B : <user>/vaca-r11-adapter     (the REAL round-11 trained LoRA —
                                             e3b7e7cc, chained from adapter_trained)
    Kernel    : <user>/vaca-qlora-round12   (single-GPU T4, no torchrun)
    Trainer   : training/cloud/train_round1.py   (verbatim, via %%writefile —
                                             with the R11 save-bug fix: trained
                                             LoRA is promoted from resume/ and
                                             the merged model comes from
                                             merge_and_unload, plus a sha sanity
                                             check that training actually applied)

Round-12 config (stronger dose than R11's 26 steps):
  3 epochs · grad-accum 4 · seq 3072 · LR 5e-5 → 67 train rows ⇒ ~51 optimizer
  steps (~2× R11) ≈ 45 min on 1× T4.

Usage:
  python3 scripts/combine-defects-r12.py                 # first: build the dataset
  python3 scripts/build-r12-kaggle-notebook.py
  python3 scripts/validate-cloud-notebooks.py            # compile-check all cells
  bash scripts/kaggle-setup-round12.sh                   # push datasets + kernel
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
KAGGLE_DIR = ROOT / "training" / "cloud" / "kaggle"

DATASET_SLUG = "round12-defects"
ADAPTER_SLUG = "vaca-r11-adapter"
KERNEL_SLUG = "vaca-qlora-round12"
NB_NAME = "train_r12_defects_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-round12.json"
DS_META_NAME = "round12-defects-dataset-metadata.json"
ADAPTER_META_NAME = "r11-adapter-dataset-metadata.json"
TITLE = "VACA QLoRA Round12"
SUBTITLE = ("Round 12 defects (3D probe-failure fix; resume from the REAL R11 "
            "LoRA; LR 5e-5; 3 ep; accum 4; seq 3072; single-GPU; merged 16-bit)")

_m = KAGGLE_DIR.parent / "round12-defects.meta.json"
N_ROWS = json.loads(_m.read_text()).get("total_rows", 74) if _m.exists() else 74

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
        "# ── Dataset A: round-12 defect-fix training rows ──",
        "data_src = find_input('" + DATASET_SLUG + "')",
        "data_dst = pathlib.Path('/kaggle/working/dataset')",
        "extract_all(data_src, data_dst)",
        "ds = data_dst / 'round12-defects-train.jsonl'",
        "assert ds.exists(), 'round12-defects-train.jsonl missing after copy!'",
        "n_rows = sum(1 for _ in open(ds, encoding='utf-8'))",
        "print('✅ Data ready:', ds.name, '|', n_rows, 'rows (trainer splits 10% val internally)')",
        "",
        "# ── Dataset B: the REAL round-11 LoRA (adapter_trained = e3b7e7cc) ──",
        "adapter_src = find_input('" + ADAPTER_SLUG + "')",
        "raw = pathlib.Path('/kaggle/working/adapters_raw')",
        "extract_all(adapter_src, raw)",
        "cand = None",
        "for p in raw.rglob('adapter_config.json'):",
        "    cand = p.parent",
        "    break",
        "assert cand is not None, 'adapter_config.json not found under ' + str(raw)",
        "adapter_dir = pathlib.Path('/kaggle/working/adapters/r11')",
        "adapter_dir.mkdir(parents=True, exist_ok=True)",
        "for f in cand.iterdir():",
        "    if f.is_file():",
        "        shutil.copy(f, adapter_dir / f.name)",
        "print('✅ R11 adapter ready:', adapter_dir)",
        "print('   (resuming from the genuinely-trained R11 LoRA e3b7e7cc)')",
    ])

    # ─── Step 3b: run cell — plain single-GPU python, resume R11 ────────
    run_cell = jn([
        "import os, subprocess, sys, torch",
        "# ── Round-12 defect-round config (resumes from the REAL R11 LoRA) ──",
        "EPOCHS = 3",
        "GRAD_ACCUM = 4           # 2x R11's optimizer-step count (54 vs 26)",
        "LR = 5e-5                # gentle continuation — defect-fix round",
        "ADAPTER = '/kaggle/working/adapters/r11'",
        "# ── Launch ──",
        "assert torch.cuda.is_available(), 'No usable GPU detected — enable GPU in the notebook settings (CPU-only session)!'",
        "os.environ.setdefault('CUDA_VISIBLE_DEVICES', '0')",
        "print(f'⚙️  Round 12 | LR {LR:.1e} | EPOCHS={EPOCHS} | grad-accum {GRAD_ACCUM} | resume={ADAPTER} | --no-gguf (merged 16-bit)')",
        "cmd = [sys.executable, 'train_round1.py',",
        "       '--dataset', '/kaggle/working/dataset/round12-defects-train.jsonl',",
        "       '--out-dir', '/kaggle/working/out',",
        "       '--rounds', '1', '--start-round', '12',",
        "       '--lr', str(LR), '--epochs', str(EPOCHS),",
        "       '--grad-accum', str(GRAD_ACCUM),",
        "       '--load-adapter', ADAPTER,",
        "       '--no-gguf',",
        "       '--max-seq-length', '3072']",
        "print('RUN:', ' '.join(cmd))",
        "subprocess.run(cmd, check=True)",
    ])

    # ─── Step 4: outputs + SANITY (saved adapter must differ from loaded) ──
    out_cell = jn([
        "!ls -lh /kaggle/working/out/",
        "import pathlib, hashlib",
        "print('\\n✅ Done. Download /kaggle/working/out/results.zip (adapter) + the merged *.safetensors files from the Output tab.')",
        "print('Adapter dirs:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('adapter*')) if pathlib.Path('/kaggle/working/out').exists() else [])",
        "print('Merged safetensors:', sorted(p.name for p in pathlib.Path('/kaggle/working/out').glob('*.safetensors')) if pathlib.Path('/kaggle/working/out').exists() else [])",
        "",
        "# ── SANITY: the saved round adapter MUST differ from the loaded R11 LoRA ──",
        "def _sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()",
        "saved = pathlib.Path('/kaggle/working/out/adapter_round12/adapter_model.safetensors')",
        "loaded = pathlib.Path('/kaggle/working/adapters/r11/adapter_model.safetensors')",
        "if saved.exists() and loaded.exists():",
        "    sa, lb = _sha(saved), _sha(loaded)",
        "    if sa == lb:",
        "        print('❌❌ SANITY FAIL: round-12 adapter == loaded R11 adapter — training did NOT apply! Do not deploy.'); raise SystemExit(1)",
        "    print('✅ SANITY OK: round-12 adapter differs from loaded R11 adapter (training applied).')",
        "else:",
        "    print('⚠️  sanity check skipped (missing adapter files).')",
    ])

    cells = [
        md(jn([
            "# 🧠 Round 12 — 3D Defect-Fix, RESUMING from the REAL R11 LoRA",
            "",
            "Fine-tunes **Orion-zhen/Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) ",
            "**resuming from the genuinely-trained round-11 LoRA** (`e3b7e7cc` — staged "
            "locally as `training/cloud/out/round11/adapter_trained/`, uploaded as "
            "dataset B). This round teaches the model to **not repeat the R11 3D probe "
            "failures**: every error class observed in the browser-gated probe becomes "
            "a render-verified *fix* row.",
            "",
            "| Source | Rows | Why |",
            "|---|---|---|",
            f"| `chunk-3d-defects.jsonl` | 18 | fresh defect-fix rows (8 verified fixed apps + 10 recipes) |",
            f"| `chunk-3d.jsonl` | 22 | 3D apps re-exposed with a REAL dose (R11 saw only 26 tiny steps) |",
            f"| `round11-mixa-train.jsonl` | 34 | retention slice (anti-regression) |",
            f"**Total** | **{N_ROWS}** | ~51 optimizer steps ≈ 50 min @ seq 3072 on 1× T4 |",
            "",
            "**Defect classes targeted:** OrbitControls CDN wiring (7/8 probe apps), "
            "hallucinated APIs (`THREE.OrbitPath`, `THREE.OctaveNoise`), removed "
            "`THREE.Geometry`/`Face3`, null tooltip element, `const` reassignment, "
            "duplicate identifiers, dead-particle deref, unbound `this.animate` in rAF, "
            "broken external texture URLs → procedural `CanvasTexture`.",
            "",
            "**Round 12** (LR 5e-5), **3 epochs, grad-accum 4** (≈2× R11's optimizer "
            "steps), seq 3072, LoRA r8/α16. **`--no-gguf`** — merged 16-bit safetensors "
            "export; q4_k_m rebuilt locally (proven path).",
            "",
            "**Save-bug fix (round-11 lesson):** the trainer now promotes the trained "
            "LoRA from unsloth's `resume/` subdir, merges via `merge_and_unload()` on "
            "the live model, and prints a **sha sanity check** that the saved adapter "
            "differs from the loaded one — the round-11 kernel silently shipped the "
            "pre-training adapter; that cannot happen here silently.",
            "",
            "**Output:** `/kaggle/working/out/` → `results.zip` (adapter_round12/) + "
            "`model-0000{1-4}-of-00004.safetensors` + config. Download from the **Output** tab.",
            "",
            "**After download (back on the local machine):**",
            "```",
            "python3 scripts/download-round12-merged.py",
            "bash scripts/deploy-round12.sh                  # convert→q4_k_m, deploy, drop R11",
            "```",
            "",
            "**Steps:** ▶ Step 1 install → ▶ Step 2 copy inputs → ▶ Step 3 train → "
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
           f"**Dataset A** `{DATASET_SLUG}` (defect-fix rows) and **Dataset B** "
           f"`{ADAPTER_SLUG}` (the REAL round-11 LoRA — chaining base) are attached "
           "to this kernel. Copy both into `/kaggle/working/`."),
        code(step2),
        md("## Step 3 — Train (Round 12, resume from R11)\n"
           "**Step 3a** writes the trainer script (with the round-11 save-bug fix). "
           "**Step 3b** runs plain single-GPU `python train_round1.py` with "
           "`--load-adapter <R11 LoRA>`, 3 epochs, grad-accum 4 and `--no-gguf`."),
        code("%%writefile train_round1.py\n" + SCRIPT),
        code(run_cell),
        md("## Step 4 — Show outputs + sanity check\n"
           "List the training artifacts and verify the saved round-12 adapter differs "
           "from the loaded R11 LoRA (guards against the round-11 save bug)."),
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
    print(f"[round12-defects] wrote {KAGGLE_DIR / NB_NAME}")
    print(f"[round12-defects] wrote {KAGGLE_DIR / KERNEL_META_NAME} (N_ROWS={N_ROWS})")


if __name__ == "__main__":
    build()
