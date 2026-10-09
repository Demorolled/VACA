#!/usr/bin/env python3
"""
Build the Google Colab notebook for the 4-round QLoRA fine-tune.

Colab free tier gives 1× T4 (16 GB) + internet. The trainer (train_round1.py)
already supports plain single-GPU mode (no torchrun), so this is a drop-in:

  rounds 1-2   fresh from base model     LR 2e-4 → 1e-4
  rounds 3-4   resumes a rounds-1-2 adapter  LR 5e-5 → 2.5e-5

Variants (default MODE in the Step 3 config cell):
  python3 scripts/build-colab-notebook.py                  → train_vaca_colab.ipynb          (MODE = "rounds12")
  python3 scripts/build-colab-notebook.py --mode round2    → train_vaca_colab_round2.ipynb  (MODE = "round2")
  python3 scripts/build-colab-notebook.py --mode rounds34  → train_vaca_colab_rounds34.ipynb (MODE = "rounds34")

The notebook is fully self-contained: it embeds the trainer via %%writefile,
acquires the dataset zip (2 MB) from Drive or a file-upload fallback, optionally
acquires a previous results.zip for resume mode, runs training, and zips/copies
the outputs for download.

NOTE on free-tier timing: 1× T4 is roughly half the throughput of Kaggle's 2× T4,
so a 2-round run (~8-12 h on Kaggle) will take ~16-24 h here. Colab free sessions
cap at ~12 h and can be reclaimed — the safe pattern is ONE round per session
(set ROUNDS below to 1), or Colab Pro for longer sessions.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "training" / "cloud" / "train_round1.py").read_text()
COL_DIR = ROOT / "training" / "cloud" / "colab"


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [],
            "source": src.splitlines(keepends=True)}


def build(mode: str = "rounds12", out_name: str = "train_vaca_colab.ipynb"):
    cells = [
        md(
            "## 🏆 VACA QLoRA Trainer — Colab Edition\n"
            "\n"
            "Fine-tunes **Qwen2.5-7B-Instruct-Uncensored** (4-bit QLoRA) on the VACA "
            "campaign-50 dataset — **4 rounds total**: LR `2e-4 → 1e-4 → 5e-5 → 2.5e-5` "
            "(one round per halving), 2 epochs each, seq len 2048, LoRA `r8/α16/d0.05`, "
            "GGUF `q4_k_m` export — identical config to the local engine.\n"
            "\n"
            "**Runtime:** Runtime → Change runtime type → **T4 GPU** (free tier).\n"
            "\n"
            "**What you need:**\n"
            "- `campaign50-dataset.zip` (**2 MB** — the notebook finds it on Drive or asks "
            "you to upload it)\n"
            "- *only for rounds 3-4:* `results.zip` from a completed rounds-1-2 run "
            "(adapter resume)\n"
            "\n"
            "**Timing (honest):** 1× T4 ≈ half the throughput of Kaggle's 2× T4. A "
            "2-round run ≈ **16-24 h** — that can exceed Colab's free ~12 h session cap. "
            "If you're on free tier, set `ROUNDS = 1` in the config cell and run one "
            "round per session (each round saves its own adapter, so you can resume).\n"
            "\n"
            "**Output:** `/content/out/results.zip` — per-round adapters + tuned GGUF "
            "(~4.4 GB). Downloaded from the files panel or copied to your Drive.\n"
            "\n"
            "**Steps:** ▶ Step 1 GPU check → ▶ Step 2 install → ▶ Step 3 config → "
            "▶ Step 4 dataset → ▶ Step 5 adapter (resume modes) → ▶ Step 6 trainer → "
            "▶ Step 7 train → ▶ Step 8 outputs."
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
           "~2-3 min. Colab has internet (unlike the Kaggle API-push runs), so pip + the "
           "Hugging Face model download just work."),
        code(
            "!python --version\n"
            "!pip install -q unsloth trl transformers datasets accelerate\n"
            "import torch, unsloth, trl\n"
            "print('✅ deps installed | Python', __import__('sys').version.split()[0], '| unsloth', unsloth.__version__, '| trl', trl.__version__)\n"
            # NB: double quotes on purpose — a \' inside the single-quoted print would
            # collapse to a raw apostrophe when this literal is evaluated, breaking the cell.
            "print(\"(If unsloth fails to import, Colab's Python may be too new — switch the runtime to Python 3.12.)\")\n"
        ),
        md("## Step 3 — Configuration\n"
           "Pick which rounds to run:\n"
           "- `rounds12` → train rounds 1-2 fresh from the base model (LR 2e-4 → 1e-4)\n"
           "- `round2`   → resume at round 2 only (LR 1e-4) from a rounds-1 adapter\n"
           "- `rounds34` → resume rounds 3-4 from a completed rounds-1-2 adapter (LR 5e-5 → 2.5e-5)\n"
           f"This notebook was built with **`MODE = \"{mode}\"`** as the default — "
           "edit the config cell below if you need a different mode."),
        code(
            "# ══════════════════════════════════════════════════════════════\n"
            "#  EDIT THIS CELL\n"
            "#  MODE:\n"
            "#    \"rounds12\"  → train rounds 1-2 fresh from base model (LR 2e-4 → 1e-4)\n"
            "#    \"round2\"    → resume at round 2 only (LR 1e-4) from a rounds-1 adapter\n"
            "#    \"rounds34\"  → resume rounds 3-4 from a rounds-1-2 adapter (LR 5e-5 → 2.5e-5)\n"
            "#  ROUNDS:\n"
            "#    Number of rounds in THIS session. Free tier → set 1 and run one per session.\n"
            "#  USE_DRIVE:\n"
            "#    Look for the dataset zip (+ results.zip) on Google Drive first.\n"
            "# ══════════════════════════════════════════════════════════════\n"
            f"MODE = \"{mode}\"      # \"rounds12\" | \"round2\" | \"rounds34\"\n"
            "ROUNDS = 2             # 2 on Pro, 1 on free tier\n"
            "USE_DRIVE = True       # False → always use the upload prompt\n"
            "\n"
            "assert MODE in (\"rounds12\", \"round2\", \"rounds34\"), f\"Unknown MODE: {MODE}\"\n"
            "if MODE == \"rounds12\":\n"
            "    START_ROUND, FIRST_LR, LOAD_ARG = 1, \"2e-4\", \"\"\n"
            "elif MODE == \"round2\":\n"
            "    START_ROUND, FIRST_LR, LOAD_ARG = 2, \"1e-4\", \"--load-adapter /content/adapter\"\n"
            "else:\n"
            "    START_ROUND, FIRST_LR, LOAD_ARG = 3, \"5e-5\", \"--load-adapter /content/adapter\"\n"
            "print(f\"⚙️  MODE={MODE} → rounds {START_ROUND}-{START_ROUND + ROUNDS - 1} | first LR {FIRST_LR} | load: {LOAD_ARG or '(fresh)'}\")\n"
        ),
        md("## Step 4 — Dataset\n"
           "Finds `campaign50-dataset.zip` on Drive (mounts it if needed) or asks you to "
           "upload the **2 MB** zip. Extracts to `/content/dataset/`."),
        code(
            "import pathlib, zipfile\n"
            "\n"
            "DST = pathlib.Path('/content/dataset'); DST.mkdir(exist_ok=True)\n"
            "ZIP_NAME = 'campaign50-dataset.zip'\n"
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
            "candidates = [pathlib.Path('/content') / ZIP_NAME]\n"
            "if DRIVE is not None:\n"
            "    candidates = list(DRIVE.rglob(ZIP_NAME)) + candidates\n"
            "found = next((p for p in candidates if p.exists()), None)\n"
            "\n"
            "if found is None:\n"
            "    print(f'⬆️  Upload {ZIP_NAME} (2 MB) using the file picker that appears…')\n"
            "    from google.colab import files\n"
            "    up = files.upload()\n"
            "    if ZIP_NAME not in up:\n"
            "        raise SystemExit(f'Expected {ZIP_NAME}, got: {list(up)}')\n"
            "    (pathlib.Path('/content') / ZIP_NAME).write_bytes(up[ZIP_NAME])\n"
            "    found = pathlib.Path('/content') / ZIP_NAME\n"
            "\n"
            "print('📦 Using dataset zip:', found)\n"
            "with zipfile.ZipFile(found) as z:\n"
            "    z.extractall(DST)\n"
            "ds_files = sorted(p.name for p in DST.glob('*.jsonl'))\n"
            "print('Dataset files:', ds_files)\n"
            "assert (DST / 'train.jsonl').exists(), 'train.jsonl missing after extraction!'\n"
            "print('✅ Dataset ready')\n"
        ),
        md("## Step 5 — Adapter (resume modes only)\n"
           "For `MODE = \"round2\"` or `\"rounds34\"`: finds `results.zip` from a "
           "previous run on Drive or asks you to upload it, then extracts the last-round "
           "adapter. **Skipped for `rounds12`.**\n"
           "\n"
           "⚠️ **Killed session?** `results.zip` is only written when a run finishes. If "
           "a free-tier session dies mid-run, download the small `adapter_roundN/` dir "
           "from the files panel (left, `/content/out/`), zip **the folder itself** (so "
           "the `adapter_round1/` name is preserved), and upload that — Step 5 finds any "
           "zip containing an `adapter_config.json`. For `round2` mode you need the "
           "**round-1** adapter; for `rounds34` the round-2 one."),
        code(
            "import pathlib, zipfile, shutil\n"
            "\n"
            "if MODE in ('round2', 'rounds34'):\n"
            "    AD_ZIP = 'results.zip'   # from a completed previous run\n"
            "    SRC = pathlib.Path('/content/adapter-src'); SRC.mkdir(exist_ok=True)\n"
            "    candidates = [pathlib.Path('/content') / AD_ZIP]\n"
            "    if DRIVE is not None:\n"
            "        candidates = list(DRIVE.rglob(AD_ZIP)) + candidates\n"
            "    found = next((p for p in candidates if p.exists()), None)\n"
            "    if found is None:\n"
            "        print(f'⬆️  Upload {AD_ZIP} from the previous run (file picker appears)…')\n"
            "        from google.colab import files\n"
            "        up = files.upload()\n"
            "        if AD_ZIP not in up:\n"
            "            raise SystemExit(f'Expected {AD_ZIP}, got: {list(up)}')\n"
            "        (pathlib.Path('/content') / AD_ZIP).write_bytes(up[AD_ZIP])\n"
            "        found = pathlib.Path('/content') / AD_ZIP\n"
            "    print('🔁 Using adapter zip:', found)\n"
            "    with zipfile.ZipFile(found) as z:\n"
            "        z.extractall(SRC)\n"
            "    # MODE-aware adapter selection (recursive discovery — handles\n"
            "    #  top-level, nested PEFT multi-adapter saves, and flat zips):\n"
            "    #  round2   → needs the ROUND-1 adapter (adapter_round1/).\n"
            "    #  rounds34 → needs the LAST-round adapter (adapter/ is a copy of\n"
            "    #             it; else highest adapter_roundN).\n"
            "    #  (Assumes the uploaded zip is the artifact the mode needs — if the\n"
            "    #   zip only contains a round-2 adapter, round2 mode will use it.)\n"
            "    _dirs, _seen = [], set()\n"
            "    for _cfg in SRC.rglob('adapter_config.json'):\n"
            "        _d = _cfg.parent\n"
            "        if _d.name in ('default', 'resume') and _d.parent != SRC:\n"
            "            _d = _d.parent  # unwrap PEFT per-adapter subfolder\n"
            "        if _d not in _seen:\n"
            "            _seen.add(_d); _dirs.append(_d)\n"
            "    round_dirs = sorted([d for d in _dirs if d.name.startswith('adapter_round')],\n"
            "                       key=lambda p: int(p.name.replace('adapter_round', '')))\n"
            "    target = None\n"
            "    if MODE == 'round2':\n"
            "        target = next((d for d in _dirs if d.name == 'adapter_round1'), None)\n"
            "        if target is None and round_dirs:\n"
            "            target = round_dirs[0]  # lowest available round\n"
            "        if target is None and _dirs:\n"
            "            target = _dirs[0]\n"
            "    else:\n"
            "        target = next((d for d in _dirs if d.name == 'adapter'), None)\n"
            "        if target is None and round_dirs:\n"
            "            target = round_dirs[-1]  # highest available round\n"
            "        if target is None and _dirs:\n"
            "            target = _dirs[0]\n"
            "    assert target is not None, 'No adapter_config.json found in the zip!'\n"
            "    # PEFT multi-adapter saves nest adapters under default/ and resume/.\n"
            "    # Promote the innermost ACTIVE adapter (prefer resume/) to the top\n"
            "    # level so the trainer's load_adapter finds adapter_config.json.\n"
            "    # (Only adapter weights are needed — the trainer loads the tokenizer\n"
            "    #  from the base model, so tokenizer files are intentionally not copied.)\n"
            "    if (target / 'resume' / 'adapter_config.json').exists():\n"
            "        target = target / 'resume'\n"
            "    elif (target / 'default' / 'adapter_config.json').exists():\n"
            "        target = target / 'default'\n"
            "    shutil.copytree(target, '/content/adapter', dirs_exist_ok=True)\n"
            "    print('✅ Resume adapter →', target, '→ /content/adapter')\n"
            "else:\n"
            "    print('(rounds12 — no resume adapter needed)')\n"
        ),
        md("## Step 6 — Trainer script\n"
           "Writes the self-contained trainer (`train_round1.py`) — same code used on "
           "Kaggle/local. Runs fine on a single GPU (no torchrun)."),
        code("%%writefile train_round1.py\n" + SCRIPT),        md("## Step 7 — Train\n"
           "Runs the rounds selected in Step 3 on the T4 (see the printed `⚙️` line). "
           "Each round saves its own adapter; the last one is exported to GGUF `q4_k_m` "
           "and everything is zipped to `results.zip`. **Watch for the 12 h free-session "
           "cap** — if you're on free tier with ROUNDS=2 and the session is killed, "
           "re-run with `ROUNDS = 1` + the right MODE: `round2` resumes a killed round-2 "
           "run, `rounds34` starts round 3 from a completed rounds-1-2 adapter."),
        code(
            "# Runs the trainer with the rounds/config selected in the 'EDIT THIS\n"
            "# CELL' step above. A shell `!`-cell cannot interpolate the Python\n"
            "# variables, so the command is built and executed here (subprocess).\n"
            "import subprocess\n"
            "\n"
            "cmd = [\n"
            "    \"train_round1.py\",\n"
            "    \"--dataset\",\n"
            "    \"/content/dataset/train.jsonl\",\n"
            "    \"--out-dir\",\n"
            "    \"/content/out\",\n"
            "    \"--rounds\",\n"
            "    str(ROUNDS),\n"
            "    \"--lr\",\n"
            "    str(FIRST_LR),\n"
            "    \"--start-round\",\n"
            "    str(START_ROUND),\n"
            "    \"--epochs\",\n"
            "    \"2\",\n"
            "    \"--max-seq-length\",\n"
            "    \"2048\",\n"
            "]\n"
            "\n"
            "# --load-adapter continuation arg ('' when starting fresh)\n"
            "cmd += LOAD_ARG.split()\n"
            "print(\"\u25b6  \" + \" \".join(cmd))\n"
            "subprocess.run(cmd, check=True)\n"
        ),
        md("## Step 8 — Outputs\n"
           "Shows the outputs, zips anything missing, and copies the whole `out/` folder "
           "to Drive if mounted. Download `results.zip` from the left files panel."),
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
            "    dest = DRIVE / 'VACA-training-out'\n"
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
    out = COL_DIR / out_name
    out.write_text(json.dumps(nb, indent=1))
    print(f"✅ Wrote {out} ({len(cells)} cells, MODE={mode})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Build the VACA Colab notebook (pick the default MODE variant).")
    ap.add_argument("--mode", choices=("rounds12", "round2", "rounds34"),
                    default="rounds12",
                    help="default MODE in the Step 3 config cell")
    ap.add_argument("--out", default=None,
                    help="output filename (default: per-mode variant, e.g. "
                         "train_vaca_colab_round2.ipynb / "
                         "train_vaca_colab_rounds34.ipynb; plain "
                         "train_vaca_colab.ipynb for --mode rounds12)")
    args = ap.parse_args()
    if args.out is None:
        # Variant filename per mode so --mode round2 / rounds34 never clobber
        # the canonical rounds12-default notebook.
        args.out = ("train_vaca_colab.ipynb" if args.mode == "rounds12"
                    else f"train_vaca_colab_{args.mode}.ipynb")
    build(mode=args.mode, out_name=args.out)
