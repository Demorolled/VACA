#!/usr/bin/env python3
"""
train_r23_kaggle.py — VACA R23 QLoRA on Kaggle (14B, combined RAG corpus)
==========================================================================
Runs the PROVEN R22 recipe (BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored,
4-bit QLoRA r8/α16, LR 5e-5, bf16, grad checkpointing, seq 1280, epochs 2)
on the combined 1,565-row RAG corpus, on Kaggle's T4 x2.

NOTES
  - Model is NOT gated → no HF token needed; ~29GB download on first run
    (Kaggle needs Internet ON).
  - logging_strategy="steps" is set EXPLICITLY: with gradient accumulation,
    transformers 4.57's default silently suppresses loss printing (verified).
  - Writes /kaggle/working/round23-kaggle/progress.json every 5 steps + a
    HEARTBEAT stdout line so the remote monitor can track progress.
  - Saves the LoRA adapter to /kaggle/working/round23-kaggle/final/ — merge
    into the base + GGUF export happen back on the agent afterwards.

Input : /kaggle/input/vaca-rag-training-all/{train,val}.jsonl
Output: /kaggle/working/round23-kaggle/{progress.json, final/, checkpoint-*/}
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

# Kaggle's default image has no bitsandbytes (verified: ImportError on the 4-bit
# load). Install it BEFORE anything imports transformers — it's imported lazily
# by from_pretrained, so a top-of-script install is sufficient.
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "bitsandbytes"], check=False)

# Expandable CUDA segments — prevents the OOM during quantized model load
# on 2×T4 (14.56 GiB each). The 14B Q4 peaks at ~14.66 GiB during load;
# fragmentation alone wastes ~200 MiB; this eliminates it.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainerCallback,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

MODEL_NAME = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
SYSTEM_PROMPT = (
    "You are a Visual AI Architect assistant specializing in GUI development. "
    "You build complete web applications, explain UI patterns, generate code, "
    "and help with frontend development."
)
DATA_DIR = Path("/kaggle/input/vaca-rag-training-all")
# Auto-discover the dataset mount: Kaggle's API push doesn't reliably attach
# dataset_sources on the first run, and the mount can be NESTED — this account's
# datasets mount as /kaggle/input/datasets/<owner>/<slug>/ (verified live), not
# the standard /kaggle/input/<slug>/. Fall back to a RECURSIVE scan for any dir
# that actually contains train.jsonl (same pattern as the working R19 notebook).
if not DATA_DIR.exists():
    _found = []
    if Path("/kaggle/input").exists():
        for d in Path("/kaggle/input").rglob("*"):
            if d.is_dir() and (d / "train.jsonl").exists():
                _found.append(d)
    if _found:
        DATA_DIR = _found[0]
        print(f"  auto-discovered dataset at: {DATA_DIR}", flush=True)
OUT_DIR = Path("/kaggle/working/round23-kaggle")
PROGRESS = OUT_DIR / "progress.json"
MAX_SEQ = 1280


def heartbeat(**kw):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **kw}
    PROGRESS.write_text(json.dumps(data))
    print("HEARTBEAT " + json.dumps(data), flush=True)


class HeartbeatCallback(TrainerCallback):
    def __init__(self, every=5):
        self.every = every

    def on_log(self, args, state, control, logs=None, **kwargs):
        if state.global_step % self.every == 0:
            heartbeat(step=state.global_step, max_steps=state.max_steps,
                      loss=logs.get("loss") if logs else None,
                      epoch=round(state.epoch, 3) if state.epoch is not None else None)


def main():
    print("=" * 60)
    print("  VACA R23 — 14B QLoRA on Kaggle (combined RAG corpus)")
    print(f"  model : {MODEL_NAME}")
    print(f"  data  : {DATA_DIR}")
    gpus = torch.cuda.device_count()
    for i in range(gpus):
        print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
    print("=" * 60)
    heartbeat(status="starting")

    train_path = DATA_DIR / "train.jsonl"
    val_path = DATA_DIR / "val.jsonl"
    if not train_path.exists():
        print(f"❌ {train_path} not found — is the dataset attached?", file=sys.stderr)
        # Diagnostic dump so a rerun tells us exactly what Kaggle mounted.
        inp = Path("/kaggle/input")
        if inp.exists():
            print("  /kaggle/input contents:", file=sys.stderr)
            for d in sorted(inp.iterdir()):
                files = [f.name for f in d.iterdir()][:10] if d.is_dir() else []
                print(f"    {d.name}/ → {files}", file=sys.stderr)
        else:
            print("  /kaggle/input does NOT exist — no datasets attached.", file=sys.stderr)
        sys.exit(1)

    # ─── 4-bit QLoRA, split across the 2 T4s ───────────────────────────────
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("Loading 14B (4-bit) split across GPUs…")
    heartbeat(status="loading_model")
    # The loading pipeline keeps raw shards + quantized copies in memory
    # simultaneously, peaking at ~2× the final weight size (~14 GiB on GPU1).
    # BitsAndBytes ignores max_memory during tensor materialization, so the
    # only reliable way to prevent OOM is offload_folder (disk overflow).
    # max_memory with CPU included helps accelerate route overflow to RAM first.
    os.makedirs("/tmp/offload", exist_ok=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb,
        device_map="auto",
        max_memory={0: "10GB", 1: "10GB", "cpu": "12GB"},
        offload_folder="/tmp/offload",
        offload_state_dict=True,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    ))
    model.gradient_checkpointing_enable()
    t, total = model.get_nb_trainable_parameters()
    print(f"Trainable: {t:,} / {total:,} ({100 * t / total:.2f}%)")

    # ─── Dataset: instruction/input/output → chat template, prompt masked ──
    records = []
    for line in train_path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        instruction = rec.get("instruction", "")
        inp = rec.get("input", "") or ""
        output = rec.get("output", "")
        if not output or len(output.strip()) < 10:
            continue
        user_text = f"{instruction}\n\n{inp}".strip() if inp else instruction
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": output.strip()},
        ]
        prompt_ids = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
        full_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
        full_ids = full_ids[:MAX_SEQ]
        labels = [-100] * min(len(prompt_ids), len(full_ids)) + \
                 full_ids[min(len(prompt_ids), len(full_ids)):]
        records.append({"input_ids": full_ids, "labels": labels})
    if not records:
        print("❌ no valid rows", file=sys.stderr)
        sys.exit(1)

    from datasets import Dataset as HFDataset
    pad = tokenizer.pad_token_id or tokenizer.eos_token_id or 0
    for r in records:
        n = len(r["input_ids"])
        r["attention_mask"] = [1] * n
        if n < MAX_SEQ:
            r["input_ids"] += [pad] * (MAX_SEQ - n)
            r["labels"] += [-100] * (MAX_SEQ - n)
            r["attention_mask"] += [0] * (MAX_SEQ - n)
    ds = HFDataset.from_list(records)
    print(f"rows: {len(ds)} train")
    heartbeat(status="training", step=0)

    targs = TrainingArguments(
        output_dir=str(OUT_DIR),
        num_train_epochs=2,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=5e-5,
        lr_scheduler_type="cosine",
        warmup_steps=10,
        weight_decay=0.01,
        bf16=True,
        # EXPLICIT logging_strategy — required for loss output with grad accum
        logging_strategy="steps",
        logging_steps=5,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        dataloader_num_workers=2,
        remove_unused_columns=False,
        report_to="none",
        gradient_checkpointing=True,
        seed=42,
    )
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=ds,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer, padding=True,
            max_length=MAX_SEQ, return_tensors="pt"),
        callbacks=[HeartbeatCallback(every=5)],
    )

    t0 = time.time()
    try:
        trainer.train()
    except Exception:
        traceback.print_exc()
        heartbeat(status="error")
        sys.exit(1)
    mins = (time.time() - t0) / 60
    final = OUT_DIR / "final"
    trainer.save_model(final)
    tokenizer.save_pretrained(final)
    heartbeat(status="done", elapsed_min=round(mins, 1))
    print(f"\n✅ adapter saved → {final} ({mins:.1f} min)")
    for f in sorted(OUT_DIR.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(OUT_DIR)} ({f.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
