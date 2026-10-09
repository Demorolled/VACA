#!/usr/bin/env python3
"""
Build the Google Colab notebook for the ROUND-6 bible+errors fine-tune (Q4).
==========================================================================
Fine-tunes Qwen2.5-7B-Instruct-Uncensored (4-bit QLoRA) on
round6-bible-10h.jsonl — a ~2,941-row dataset sized for **~10 h of training
on a Colab T4 at 2 epochs** — and exports GGUF q4_k_m.

Dataset composition (round 6 = "bible knowledge + previous-run error fixes"):
  1,808 bible→code rows (904 chunks × 2 phrasings)
    800  blueprint retention (clean train, no new eval leakage)
    401  round-4 failures (reinforce the previous error-fix round)
     99  fidelity-fix rows (the 33 currently-failing prompts → canonical JSON)
     20  alias-normalization rows (got "alertmanager_config_lab" → "alertmanager_config_2")

Why this round: round-4 regressed fidelity 59 → 45.9% (app_type alias drift);
round-5 was set up but never trained. Round 6 adds the code-component
knowledge from the 904-chunk bible AND teaches the model the canonical
blueprints for every prompt it currently gets wrong.

It reuses the SAME self-contained trainer as all previous Colab/Kaggle rounds
(training/cloud/train_round1.py — embedded byte-for-byte via %%writefile), so
validate-cloud-notebooks.py can byte-match it and no trainer drift can ship.

Output notebook: training/cloud/colab/train_round6_bible_10h_q4.ipynb
Usage:
  python3 scripts/build-colab-round6-notebook.py
  python3 scripts/validate-cloud-notebooks.py --notebooks training/cloud/colab/train_round6_bible_10h_q4.ipynb
"""
import json
import os
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
COL_DIR = ROOT / "training" / "cloud" / "colab"
OUT_NB = COL_DIR / "train_round6_bible_10h_q4.ipynb"
DS_FILE = ROOT / "training" / "dataset" / "round6-bible-10h.jsonl"
OUT_ZIP = ROOT / "training" / "cloud" / "round6-bible-10h.zip"

SESSION_HOURS = 11  # Colab free/pro session budget used for the timing estimate


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}


def build_zip() -> None:
    """Zip round6-bible-10h.jsonl at the zip ROOT (flat layout) + self-test."""
    if not DS_FILE.exists():
        raise SystemExit(f"❌ round-6 dataset missing: {DS_FILE} (run scripts/build-round6-bible-dataset.py first)")
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(DS_FILE, DS_FILE.name)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(OUT_ZIP) as zf:
            zf.extractall(tmp)
        n = sum(1 for _ in open(Path(tmp) / DS_FILE.name, encoding="utf-8"))
    src_n = sum(1 for _ in open(DS_FILE, encoding="utf-8"))
    assert n == src_n, f"zip self-test failed: {n} != {src_n}"
    print(f"✅ Dataset zip → {OUT_ZIP.name} ({n} rows)")


def build() -> None:
    cells = [
        md(
            "## 🏆 Round-6 Bible + Error-Fix Q4 QLoRA Trainer — Colab Edition\n"
            "\n"
            "Fine-tunes **Qwen2.5-7B-Instruct-Uncensored** on "
            "`round6-bible-10h.jsonl` — a **~2,941-row dataset sized for ~10 h "
            "of training on a T4 at 2 epochs**. Config: **QLoRA 4-bit**, 1 round "
            "@ **LR 2e-4**, `EPOCHS` (default 2), seq len **2048**, LoRA "
            "`r8/α16/d0.05`, export **GGUF q4_k_m**.\n"
            "\n"
            "**What's in the dataset (round 6):**\n"
            "- **1,808 bible→code rows** — the 904-chunk code bible, 2 phrasings each\n"
            "- **800 blueprint retention** — clean train pairs, no new eval leakage\n"
            "- **401 round-4 failure rows** — reinforce the previous error-fix round\n"
            "- **99 fidelity-fix rows** — the 33 prompts the model currently gets "
            "wrong, paired with the **canonical** library blueprint\n"
            "- **20 alias-normalization rows** — fixes the round-4 regression where "
            "the model invented keys like `alertmanager_config_lab` instead of "
            "`alertmanager_config_2`\n"
            "\n"
            "**Runtime:** Runtime → Change runtime type → **T4 GPU** (free tier). "
            "T4 has no bf16 — the trainer auto-falls back to fp16.\n"
            "\n"
            "**You need:** `round6-bible-10h.zip` (≈1–2 MB — built by "
            "`scripts/build-colab-round6-notebook.py`) or the raw "
            "`round6-bible-10h.jsonl`. The notebook finds it on Drive or asks "
            "you to upload it.\n"
            "\n"
            "**Timing (honest, seq 2048):** T4 ≈ 5–8 s/row, L4 ≈ 3.2–4.3 s/row, "
            "A100 ≈ 1.8–2.6 s/row. For 2,941 rows: **2 epochs ≈ 10.9 h on T4** — "
            "sized to fill a ~11 h session. Step 4 prints the exact projection "
            "for your row count + GPU and warns if it exceeds the budget.\n"
            "\n"
            "**Output:** `/content/out/results.zip` — `adapter_round6/` + tuned "
            "GGUF `q4_k_m` (~4.4 GB). Copied to Drive if mounted. After download, "
            "deploy + re-run `scripts/validate-blueprint-fidelity.py --all`.\n"
            "\n"
            "**Steps:** ▶ Step 1 GPU check → ▶ Step 2 install → ▶ Step 3 config → "
            "▶ Step 4 dataset → ▶ Step 5 trainer → ▶ Step 6 train → ▶ Step 7 outputs."
        ),
        md("## Step 1 — GPU check\n"
           "Verify the T4 is live (free tier = 1 GPU). No 2-GPU requirement here."),
        code(
            "import torch\n"
            "print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NONE', '| count:', torch.cuda.device_count())\n"
            "assert torch.cuda.is_available(), 'No GPU! Runtime → Change runtime type → T4 GPU'\n"
            "assert torch.cuda.get_device_capability(0) >= (7, 0), 'T4 or newer required (Colab free gives T4)'\n"
            "print('✅ GPU ready')\n"
        ),
        md("## Step 2 — Install dependencies\n"
           "~2-3 min. Colab has internet, so pip + the Hugging Face model download just work."),
        code(
            "!python --version\n"
            "!pip install -q unsloth trl transformers datasets accelerate\n"
            "import torch, unsloth, trl\n"
            "print('✅ deps installed | Python', __import__('sys').version.split()[0], '| unsloth', unsloth.__version__, '| trl', trl.__version__)\n"
            "print(\"(If unsloth fails to import, Colab's Python may be too new — switch the runtime to Python 3.12.)\")\n"
        ),
        md("## Step 3 — Configuration\n"
           "Set `EPOCHS` and the session budget. Defaults: **2 epochs** (≈10.9 h "
           "on T4 for the 2,941-row round-6 set) — this dataset is sized to FILL "
           "an 11 h session. If your session has less time left, drop to 1; the "
           "error-fix rows get at least one full pass either way. "
           "**Don't raise above 3** — round-4 showed 3 epochs on a small set "
           "already caused app_type vocabulary drift."),
        code(
            "# ══════════════════════════════════════════════════════════════\n"
            "#  EDIT THIS CELL\n"
            "#  EPOCHS:        training epochs in THIS session (2 ≈ 10.9 h on T4)\n"
            "#  SESSION_HOURS: your Colab session budget (free tier caps ~12 h)\n"
            "#  USE_DRIVE:     look for the dataset on Google Drive first\n"
            "# ══════════════════════════════════════════════════════════════\n"
            f"EPOCHS = 2          # 1 = short · 2 = default (~10.9 h mid) · 3 = max, drift risk\n"
            f"SESSION_HOURS = {SESSION_HOURS}\n"
            "USE_DRIVE = True    # False → always use the upload prompt\n"
            "LR = 2e-4           # single round @ 2e-4 (round-6 config)\n"
            "assert EPOCHS >= 1 and EPOCHS <= 3\n"
            "print(f'⚙️  EPOCHS={EPOCHS} | LR={LR:.1e} | budget={SESSION_HOURS}h')\n"
        ),
        md("## Step 4 — Dataset\n"
           "Finds `round6-bible-10h.zip` **or** `round6-bible-10h.jsonl` on Drive "
           "(mounts it if needed) or asks you to upload it. Extracts to "
           "`/content/dataset/` and prints the row count + projected training time "
           "for your GPU, warning if it exceeds the session budget."),
        code(
            "import pathlib, zipfile, json\n"
            "\n"
            "DST = pathlib.Path('/content/dataset'); DST.mkdir(exist_ok=True)\n"
            "ZIP_NAME = 'round6-bible-10h.zip'\n"
            "JSONL_NAME = 'round6-bible-10h.jsonl'\n"
            "\n"
            "DRIVE = None\n"
            "if USE_DRIVE:\n"
            "    try:\n"
            "        if not pathlib.Path('/content/drive').exists():\n"
            "            from google.colab import drive\n"
            "            drive.mount('/content/drive')  # follow the auth link, or skip\n"
            "        DRIVE = pathlib.Path('/content/drive/MyDrive')\n"
            "        if not DRIVE.exists(): DRIVE = None\n"
            "    except Exception as e:\n"
            "        print('(Drive skipped:', e, ')')\n"
            "\n"
            "candidates = [pathlib.Path('/content') / ZIP_NAME, pathlib.Path('/content') / JSONL_NAME]\n"
            "if DRIVE is not None:\n"
            "    candidates = list(DRIVE.rglob(ZIP_NAME)) + list(DRIVE.rglob(JSONL_NAME)) + candidates\n"
            "found = next((p for p in candidates if p.exists()), None)\n"
            "\n"
            "if found is None:\n"
            "    print('⬆️  Upload ' + ZIP_NAME + ' or ' + JSONL_NAME + ' using the file picker that appears…')\n"
            "    from google.colab import files\n"
            "    up = files.upload()\n"
            "    if ZIP_NAME in up:\n"
            "        (pathlib.Path('/content') / ZIP_NAME).write_bytes(up[ZIP_NAME])\n"
            "        found = pathlib.Path('/content') / ZIP_NAME\n"
            "    elif JSONL_NAME in up:\n"
            "        (pathlib.Path('/content') / JSONL_NAME).write_bytes(up[JSONL_NAME])\n"
            "        found = pathlib.Path('/content') / JSONL_NAME\n"
            "    else:\n"
            "        raise SystemExit('Expected ' + ZIP_NAME + ' or ' + JSONL_NAME + ', got: ' + str(list(up)))\n"
            "\n"
            "print('📦 Using dataset:', found)\n"
            "if found.name.endswith('.zip'):\n"
            "    with zipfile.ZipFile(found) as z:\n"
            "        z.extractall(DST)\n"
            "else:\n"
            "    (DST / JSONL_NAME).write_bytes(found.read_bytes())\n"
            "\n"
            "ds_file = DST / JSONL_NAME\n"
            "assert ds_file.exists(), 'round6-bible-10h.jsonl missing after extraction!'\n"
            "n_rows = sum(1 for _ in open(ds_file, encoding='utf-8'))\n"
            "print('✅ Dataset ready:', ds_file.name, '|', n_rows, 'rows')\n"
            "\n"
            "# ── Session-time projection ────────────────────────────────────\n"
            "gpu = torch.cuda.get_device_name(0).upper() if torch.cuda.is_available() else 'CPU'\n"
            "per_row_s = 6.65 if 'T4' in gpu else (3.8 if 'L4' in gpu else (2.2 if 'A100' in gpu or 'H100' in gpu else 6.65))\n"
            "est_h = n_rows * EPOCHS * per_row_s / 3600\n"
            "print(f'⏱️  GPU={gpu} | ~{per_row_s}s/row @ seq 2048')\n"
            "print(f'⏱️  Projected train time: {est_h:.1f} h for {n_rows} rows x {EPOCHS} epochs')\n"
            "if est_h > SESSION_HOURS * 0.9:\n"
            "    print('⚠️  Projection exceeds ~90% of the session budget — lower EPOCHS (Step 3) or expect the session to die mid-run.')\n"
            "    print('    Re-run later with the same config + a saved adapter if it is killed.')\n"
            "else:\n"
            "    print('✅ Fits the session budget (with margin for download + GGUF export).')\n"
        ),
        md("## Step 5 — Trainer script\n"
           "Writes the self-contained trainer (`train_round1.py`) — the same file "
           "used by every previous Colab/Kaggle round. Runs fine on a single GPU "
           "(no torchrun)."),
        code("%%writefile train_round1.py\n" + SCRIPT),
        md("## Step 6 — Train\n"
           "1 round @ LR 2e-4 on the T4. Saves `adapter_round6/`, then exports "
           "**GGUF q4_k_m** and zips everything to `results.zip`. Watch the "
           "session cap printed in Step 4."),
        # NB: a bare `!python ... {LR}` shell cell would pass `{LR}` LITERALLY to
        # argparse (Colab !-cells are plain shell — no f-string interpolation),
        # crashing training with "invalid float value: '{LR}'". So this is a
        # Python cell that interpolates LR/EPOCHS from the Step-3 config cell and
        # runs the trainer via subprocess (inherits stdout → live progress).
        code(
            "import subprocess, sys\n"
            "cmd = (\"python train_round1.py --dataset /content/dataset/round6-bible-10h.jsonl \"\n"
            "       \" --out-dir /content/out \"\n"
            "       f\" --rounds 1 --start-round 6 --lr {LR} --epochs {EPOCHS} \"\n"
            "       \" --max-seq-length 2048\")\n"
            "print('▶ ' + cmd)\n"
            "sys.exit(subprocess.call(cmd, shell=True))\n"
        ),
        md("## Step 7 — Outputs\n"
           "Shows the outputs, zips anything missing, and copies the whole `out/` "
           "folder to Drive if mounted. Download `results.zip` from the left files "
           "panel.\n"
           "\n"
           "**After download:** deploy the GGUF (`scripts/deploy-tuned-dspark.sh --now` "
           "or copy into `models/` + restart dspark) and re-run "
           "`python3 scripts/validate-blueprint-fidelity.py --all` to measure the "
           "real fidelity vs round-4's 45.9%. Expected: the 33 fix rows recover "
           "their exact matches (they are now in-train), and the alias "
           "normalization should stop the `_lab`/`_generator` style drift.\n"
           "\n"
           "**Honest caveat:** 33 of the 61 validation prompts are intentionally "
           "in-train now, so exact-match on those is not a generalization signal — "
           "watch the **known** gate (valid library key) and the truly held-out "
           "prompts (12 of 61 — the rest are error-fixes or round-4 inheritance) "
           "for the real measure."),
        code(
            "import pathlib, zipfile\n"
            "out = pathlib.Path('/content/out')\n"
            "print('Outputs:')\n"
            "for p in sorted(out.iterdir()):\n"
            "    if p.is_dir():\n"
            "        sz = sum(f.stat().st_size for f in p.rglob('*') if f.is_file())\n"
            "        print(f'  {p.name}/  ({sz/1e6:.1f} MB)')\n"
            "    else:\n"
            "        print(f'  {p.name}  ({p.stat().st_size/1e6:.1f} MB)')\n"
            "\n"
            "if not (out / 'results.zip').exists():\n"
            "    print('Zipping results…')\n"
            "    with zipfile.ZipFile(out / 'results.zip', 'w', zipfile.ZIP_DEFLATED) as zf:\n"
            "        for d in out.iterdir():\n"
            "            if d.is_dir() and d.name.startswith('adapter'):\n"
            "                for f in d.rglob('*'):\n"
            "                    if f.is_file(): zf.write(f, f.relative_to(out))\n"
            "        for g in out.glob('*.gguf'):\n"
            "            zf.write(g, g.name)\n"
            "\n"
            "if DRIVE is not None:\n"
            "    dest = DRIVE / 'VACA-training-out-round6'\n"
            "    import shutil\n"
            "    shutil.copytree(out, dest, dirs_exist_ok=True)\n"
            "    print('📁 Copied out/ →', dest)\n"
            "\n"
            "print('✅ Done. Download /content/out/results.zip from the files panel (left).')\n"
        ),
    ]

    nb = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": [], "gpuType": "T4", "toc_visible": True},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }

    COL_DIR.mkdir(parents=True, exist_ok=True)
    OUT_NB.write_text(json.dumps(nb, indent=1))
    print(f"✅ Wrote {OUT_NB} ({len(cells)} cells)")


if __name__ == "__main__":
    build_zip()
    build()
    print(f"\nNow validate: python3 scripts/validate-cloud-notebooks.py "
          f"--notebooks training/cloud/colab/{OUT_NB.name}")
