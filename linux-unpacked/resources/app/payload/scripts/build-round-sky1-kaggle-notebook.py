#!/usr/bin/env python3
"""
build-round-sky1-kaggle-notebook.py — Sky-T1 SFT round notebook + kernel metadata.
================================================================================
Follows the PROVEN R28 pattern (train_r28_kaggle.kernel) but for SFT of the
Sky-T1 reasoning corpus on Qwen2.5-Coder-14B-Instruct-Uncensored.

  Dataset : <user>/vaca-sky1-sft-corpus   (train.jsonl / val.jsonl — the
                                          converted Sky-T1 reasoning rows)
  Kernel  : <user>/vaca-qlora-round-sky1  (14B SFT, ORPO-free; adapter-only save
                                          so no 16-bit in-kernel merge → the
                                          R19 OOM spot is avoided)

Config (mirrors R28's single-16GB-GPU reality):
  QLoRA 4-bit, r8/α16, seq 2048 (Sky-T1 traces), batch 1 × accum 4,
  LR 5e-5, fp16 (T4/P100 lack bf16), grad checkpointing, epochs 1.

Usage:
  python3 scripts/build-sky1-sft-corpus.py                # 1st: corpus
  python3 scripts/build-round-sky1-kaggle-notebook.py     # then: notebook
  bash scripts/kaggle-setup-sky1.sh                       # push dataset + kernel
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE_DIR = ROOT / "kaggle_kernel"
CORPUS_DIR = ROOT / "training" / "cloud" / "sky1"

DATASET_SLUG = "vaca-sky1-sft-corpus"
KERNEL_SLUG = "vaca-qlora-round-sky1"
NB_NAME = "train_sky1_kaggle.ipynb"
KERNEL_META_NAME = "kernel-metadata-sky1.json"
TITLE = "VACA QLoRA Round Sky1"

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


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [], "source": src.splitlines(keepends=True)}


def build():
    n_train = sum(1 for _ in open(CORPUS_DIR / "train.jsonl") if _.strip()) if (CORPUS_DIR / "train.jsonl").exists() else 0
    cells = [
        md(
            f"""# 🧠 VACA Sky-T1 round — 14B SFT (reasoning traces)

**{n_train} train rows** = converted Sky-T1_data_17k reasoning rows
(`{{instruction, input, output}}`, thinking trace kept in output — seq 2048).
Trains Qwen2.5-Coder-**14B**-Instruct-Uncensored so the next VACA round reasons
before it writes code.

Proven R23/R28 single-16GB-GPU recipe: QLoRA 4-bit r8/α16, seq **2048**,
epochs 1, batch 1×accum 4, LR 5e-5, **fp16** (T4 lacks bf16), grad
checkpointing, adapter-only save (no in-kernel 16-bit merge)."""
        ),
        code("!nvidia-smi"),
        code(
            """# ── Install (PINNED combo — verified working for QLoRA, fixes both failure modes):
#    transformers too new (base image) → unsloth 'auto_docstring' NameError;
#    newest unsloth+transformers → Triton 'cpu tensor' OOM on one T4.
#    The working trio: transformers==5.5.0, unsloth==2026.8.19, unsloth_zoo==2026.8.13
#    (unsloth GH #9650 — same stack trains 27B QLoRA cleanly). ──
import sys, subprocess
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q',
                 'transformers==5.5.0', 'unsloth==2026.8.19', 'unsloth_zoo==2026.8.13',
                 'trl', 'datasets', 'accelerate', 'peft', 'bitsandbytes'], check=True)
import torch
assert torch.cuda.is_available(), '❌ No GPU — set Accelerator to a GPU in kernel settings'
print('✅ CUDA:', torch.cuda.device_count(), 'x', torch.cuda.get_device_name(0))
print('   bf16 supported?', torch.cuda.is_bf16_supported(), '(expect False on T4/P100)')
import unsloth, transformers
print('✅ unsloth', unsloth.__version__, '| transformers', transformers.__version__)"""
        ),
        code(
            """# ── Dataset: prefer the mount, else pull from Kaggle (Internet is ON) ──
import glob, os, shutil, sys
import pathlib
DATA_DIR = pathlib.Path('/kaggle/input/vaca-sky1-sft-corpus')
data_roots = sorted(glob.glob(str(DATA_DIR / '*')))
print('data candidates:', data_roots)
if not data_roots:
    print('ℹ️  Dataset not mounted — pulling via kagglehub...')
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'kagglehub'], check=True)
    import kagglehub
    p = kagglehub.dataset_download('stevenawoods/vaca-sky1-sft-corpus')
    DATA_DIR = pathlib.Path(p)
    data_roots = sorted(glob.glob(str(DATA_DIR / '*')))
    print('ℹ️  pulled dataset to', DATA_DIR, 'files:', data_roots)
assert data_roots, '❌ No dataset files found anywhere'
import json
# NOTE: write to /kaggle/working — the dataset dir is read-only!
ENV_PATH = pathlib.Path('/kaggle/working/kernel-env.json')
with open(ENV_PATH, 'w') as _f:
    json.dump({'data_dir': str(DATA_DIR)}, _f)
print('✅ dataset ready →', DATA_DIR)
"""
        ),
        code(
            """%%writefile train_sky1_kaggle.py
#!/usr/bin/env python3
\"\"\"train_sky1_kaggle.py — VACA Sky-T1 SFT on Kaggle (14B).\"\"\"
import glob, os, sys, subprocess
import torch
from pathlib import Path

os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')
os.environ.setdefault('PYTORCH_ALLOC_CONF', 'expandable_segments:True')

# ── Locate dataset (mounted or pulled — the env file tells us where) ──
env_f = Path('/kaggle/working/kernel-env.json')
if env_f.exists():
    import json as _json
    root = Path(_json.load(open(env_f))['data_dir'])
else:
    root = Path('/kaggle/input/vaca-sky1-sft-corpus')
train_f = sorted(root.glob('**/train.jsonl'))
if not train_f:
    print('❌ train.jsonl not found under', root)
    sys.exit(1)
train_path, = train_f
print('📄 train:', train_path)

BASE = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
SEQ = 2048   # Sky-T1 traces are long (~median 3k tok); 2048 caps cleanly on a T4
EPOCHS = 1
BATCH = 1
GRAD_ACCUM = 4
LR = 5e-5
OUT = Path('/kaggle/working/sky1-kaggle')

def dep_root(p):
    import site
    return site.getsitepackages()[0] if site else None

# ── Build model ──
print('⬇️  Loading base', BASE, '(4-bit QLoRA, spread across all GPUs)...')
from unsloth import FastLanguageModel
import torch
_n_gpu = torch.cuda.device_count()
_model_kwargs = {}
if _n_gpu > 1:
    # Split across the T4s so activations never spill to CPU (the Triton
    # 'cpu tensor' OOM). 11GB per card keeps ~1GB headroom on 12/16GB.
    _model_kwargs['device_map'] = 'auto'
    _model_kwargs['max_memory'] = {i: '11GB' for i in range(_n_gpu)}
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=BASE,
    max_seq_length=SEQ,
    load_in_4bit=True,
    dtype=None,            # fp16 auto (T4)
    **_model_kwargs,
)
model = FastLanguageModel.get_peft_model(
    model, r=8, lora_alpha=16,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0, bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42, use_rslora=False, loftq_config=None,
)

print('⚙️  Tokenizing dataset (assistant-only labels) ...')
sys.path.insert(0, str(Path('/kaggle/working')))

# ── Use VACA's loader logic directly (tokenize here so T4 stays for training) ──
import json
from datasets import load_dataset as hf_load
raw = hf_load('json', data_files=str(train_path), split='train')

SYSTEM = "You are VACA's code architect. Think step by step, then give a working, small, fast, reusable solution."

messages_full, labels0 = [], []
max_seq = SEQ

def build_ids(rec):
    from transformers import AutoTokenizer  # noqa
    out_map = {"role": "assistant", "content": rec["output"].strip()}
    user_text = rec["instruction"].strip()
    if rec.get("input") and rec["input"].strip() and rec["input"] != "Auto-learned conversation":
        user_text = f"{rec['instruction']}\\n\\n{rec['input']}"
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_text},
        out_map,
    ]
    prompt_ids = tokenizer.apply_chat_template(msgs[:-1], tokenize=True, add_generation_prompt=True)
    full_ids = tokenizer.apply_chat_template(msgs, tokenize=True, add_generation_prompt=False)
    if len(full_ids) > max_seq:
        full_ids = full_ids[:max_seq]
    labels = [-100] * min(len(prompt_ids), len(full_ids)) + full_ids[min(len(prompt_ids), len(full_ids)):]
    full_ids = (full_ids + [tokenizer.pad_token_id or tokenizer.eos_token_id] * max_seq)[:max_seq]
    labels = (labels + [-100] * max_seq)[:max_seq]
    return {
        "input_ids": full_ids, "attention_mask": [1] * len(full_ids), "labels": labels,
    }

from datasets import Dataset as HFDataset
recs = [build_ids(r) for r in raw]
ds = HFDataset.from_list(recs).train_test_split(test_size=0.1, seed=42)
print('✅ train rows:', len(ds['train']), 'val rows:', len(ds['test']))

# ── SFT trainer ──
from trl import SFTConfig, SFTTrainer
print('🏋️  SFTTrainer ...')
try:
    from trl import SFTConfig as _C
    sft_args = _C(
        output_dir=str(OUT), per_device_train_batch_size=BATCH,
        gradient_accumulation_steps=GRAD_ACCUM, num_train_epochs=EPOCHS,
        learning_rate=LR, warmup_ratio=0.05, logging_steps=5,
        save_strategy="no", report_to=[],
        fp16=True, bf16=False,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_seq_length=SEQ, packing=False,
        dataset_text_field=None,
    )
except Exception as e:
    print('SFTConfig failed, falling back to TrainingArguments:', e)
    from transformers import TrainingArguments
    from trl import SFTTrainer as _S
    sft_args = TrainingArguments(
        output_dir=str(OUT), per_device_train_batch_size=BATCH,
        gradient_accumulation_steps=GRAD_ACCUM, num_train_epochs=EPOCHS,
        learning_rate=LR, warmup_ratio=0.05, logging_steps=5,
        save_strategy="no", report_to=[], fp16=True, bf16=False,
    )

trainer = SFTTrainer(
    model=model, tokenizer=tokenizer, args=sft_args,
    train_dataset=ds['train'], eval_dataset=ds['test'],
    max_seq_length=SEQ,
)
trainer.train()

# ── Save adapter ONLY (no 16-bit merge on T4 — the R19 OOM spot) ──
final = OUT / 'final'
model.save_pretrained(str(final))
tokenizer.save_pretrained(str(final))
print('✅ adapter saved →', final)
print('   download /kaggle/working/sky1-kaggle (final/ = LoRA)')"""
        ),
        code(
            """# ── Runner: script was just written to /kaggle/working by the cell above ──
import os, sys, subprocess
os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')
os.environ.setdefault('PYTORCH_ALLOC_CONF', 'expandable_segments:True')
assert os.path.exists('/kaggle/working/train_sky1_kaggle.py'), '❌ train_sky1_kaggle.py missing — writefile cell ran after this?'
subprocess.run([sys.executable, '/kaggle/working/train_sky1_kaggle.py'], cwd='/kaggle/working', check=True)"""
        ),
        code(
            """import pathlib
out = pathlib.Path('/kaggle/working/sky1-kaggle')
final = out / 'final'
assert (final / 'adapter_config.json').exists(), '❌ adapter missing'
sz = (final / 'adapter_model.safetensors').stat().st_size
print(f'✅ Sky-T1 adapter: {sz/1e6:.1f} MB')
print('→ download /kaggle/working/sky1-kaggle (final/ = LoRA; merge locally)')"""
        ),
    ]

    nb = {
        "metadata": NB_METADATA,
        "nbformat": 4, "nbformat_minor": 0,
        "cells": cells,
    }
    out_nb = KAGGLE_DIR / NB_NAME
    KAGGLE_DIR.mkdir(parents=True, exist_ok=True)
    out_nb.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print(f"📝 notebook → {out_nb}")

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
    meta_p = KAGGLE_DIR / KERNEL_META_NAME
    meta_p.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"📝 kernel metadata → {meta_p}")
    print("→ bash scripts/kaggle-setup-sky1.sh  (push dataset + kernel)")


if __name__ == "__main__":
    build()