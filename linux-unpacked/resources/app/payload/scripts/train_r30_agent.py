#!/usr/bin/env python3
"""
train_r30_agent.py — VACA R30 QLoRA on the AGENT (3× RTX 3060 12GB)
=====================================================================
FRESH QLoRA round (no continuation adapter) on the puzzle-game corpus —
the 2,133 rows the Puzzle-RAG trainer generated: SFT node picks,
completion (cloze) fills, and tune-up optimizations.

Engine: BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored (already in the
agent's HF cache — HF_HUB_OFFLINE=1), 4-bit QLoRA r8/α16, LR 5e-5, fp16,
seq 1024, batch 1 × accum 4, gradient checkpointing, masked chat-template
labels, explicit pyarrow Features.

GPU layout: the SINGLE 14B model is 4-bit sharded across all 3× 12 GB
cards (device_map="auto", ~11 GB budget per card). A full per-GPU replica
OOMs (weights ≈ 9.5 GB + the lm_head fp32 cast ≈ 2.9 GB > 12 GB), so we
use one sharded model spanning the 3 cards — the SAME memory the inference
server used — and Trainer auto-switches to model-parallel mode.

Run on the agent (single process — Trainer handles the sharded model):
  source /home/llmlab/vaca-train-venv/bin/activate
  HF_HUB_OFFLINE=1 python3 -u /home/llmlab/vaca-r30/scripts/train_r30_agent.py

Input : /home/llmlab/vaca-r30/training/{train,val}.jsonl
Output: /home/llmlab/vaca-r30/output/round30/{final/, checkpoint-*/, resume.json, progress.json}
"""
import json
import os
import re
import sys
import time
import traceback
from collections.abc import Mapping
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

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

# ── paths / constants ────────────────────────────────────────────────────
# R31: fresh shrink corpus lives under ~/vaca-r31 (synced from the local
# puzzle-rag-trainer corpus builder) — NOT vaca-r30, which still holds the
# pre-fix R30 dataset.  Training must read the pick-dominant rows.
ROOT = Path("/home/llmlab/vaca-r31")
TRAIN_JSONL = ROOT / "training" / "train.jsonl"
VAL_JSONL = ROOT / "training" / "val.jsonl"
OUT_DIR = ROOT / "output" / "round31"
RESUME_JSON = OUT_DIR / "resume.json"
PROGRESS = OUT_DIR / "progress.json"

MODEL_NAME = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
SYSTEM_PROMPT = (
    "You are a Visual AI Architect assistant specializing in GUI development. "
    "You build complete web applications, explain UI patterns, generate code, "
    "and help with frontend development."
)
MAX_SEQ = 1024
EPOCHS = 2
SESS_BUDGET_H = 20.0  # generous ceiling; epochs bind first
LOCAL_RANK = int(os.environ.get("LOCAL_RANK", "0"))
WORLD_SIZE = int(os.environ.get("WORLD_SIZE", "1"))

def phase(msg):
    print(f"[r{LOCAL_RANK}] PHASE {msg}", flush=True)

def heartbeat(**kw):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **kw}
    PROGRESS.write_text(json.dumps(data))
    if LOCAL_RANK == 0:
        print("HEARTBEAT " + json.dumps(data), flush=True)

class HeartbeatCallback(TrainerCallback):
    def __init__(self, every=5):
        self.every = every
        self.t0 = None
        self.last_step = 0
        self.s_per_step = None

    def on_train_begin(self, args, state, control, **kw):
        self.t0 = time.time()

    def on_log(self, args, state, control, logs=None, **kw):
        if state.global_step % self.every == 0:
            if self.t0 is None:
                self.t0 = time.time()
            dt = time.time() - self.t0
            if state.global_step > self.last_step:
                self.s_per_step = dt / max(state.global_step, 1)
                self.last_step = state.global_step
            heartbeat(step=state.global_step, status="training",
                      loss=round(logs["loss"], 4) if logs and logs.get("loss") is not None else None,
                      epoch=round(state.epoch, 3) if state.epoch is not None else None,
                      gpus=torch.cuda.device_count(),
                      s_per_step=round(self.s_per_step, 3) if self.s_per_step else None,
                      seg_h=round((time.time() - self.t0) / 3600, 3))

def ids_of(x):
    """Shape-proof: return a flat list of token ints no matter what apply_chat_template returns.

    Recent transformers (>= 5.0) return a `BatchEncoding` — a `UserDict`-based Mapping, NOT a
    `dict` subclass — when tokenize=True (default return_dict=True). Iterating one yields its
    KEYS ("input_ids", "attention_mask", ...), and `list(x)` / `int('input_ids')` crashes the
    Dataset build. Use collections.abc.Mapping so both plain dicts and BatchEncoding are
    unwrapped to their "input_ids" list; also handle `.ids` objects, tensors, and nesting.
    """
    if x is None:
        return []
    if hasattr(x, "ids"):
        x = x.ids
    if not isinstance(x, Mapping) and hasattr(x, "input_ids"):
        x = x.input_ids
    if isinstance(x, Mapping):
        ids = x.get("input_ids")
        if ids is None:
            ids = x.get("inputIds")
        if ids is None:
            for v in x.values():
                ids = v
                break
        x = ids if ids is not None else []
    if hasattr(x, "tolist"):                  # tensor / numpy array at top level
        x = x.tolist()
    if isinstance(x, (int,)):
        return [x]
    if isinstance(x, str):                    # single string token? coerce
        return [int(x)] if x.lstrip("-").isdigit() else []
    out = []
    for item in x:
        if hasattr(item, "tolist"):          # tensor / numpy scalar-array
            item = item.tolist()
        if isinstance(item, (list, tuple)) or isinstance(item, Mapping):  # nested → recurse
            out.extend(ids_of(item))
        else:
            out.append(int(item))
    return out

def write_resume(seg_h=None, steps_total=None, gpu=None, s_per_step=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "round": 30,
        "host": "agent-3060x3",
        "elapsed_h": round(seg_h, 3) if seg_h else 0.0,
        "steps_total": int(steps_total or 0),
        "gpu": gpu,
        "s_per_step": round(s_per_step, 3) if s_per_step else None,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    RESUME_JSON.write_text(json.dumps(data, indent=1))
    return data

def main():
    phase("=" * 60)
    phase(f"VACA R30 — 14B QLoRA on agent 3×3060 — rank {LOCAL_RANK}/{WORLD_SIZE}")
    phase(f"model : {MODEL_NAME}")
    try:
        import transformers as _tf
        phase(f"transformers {_tf.__version__}")
    except Exception:
        pass
    gpus = torch.cuda.device_count()
    for i in range(gpus):
        phase(f"GPU {i}: {torch.cuda.get_device_name(i)}")

    if not TRAIN_JSONL.exists():
        phase(f"❌ missing {TRAIN_JSONL}")
        sys.exit(1)

    heartbeat(status="loading_model")

    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    phase("Loading 14B (4-bit) with explicit 3-GPU split…")
    os.makedirs("/tmp/offload", exist_ok=True)
    # Single 4-bit copy split ACROSS all 3 cards with a deterministic layer map
    # (device_map="auto" ignored max_memory here: it packed 40 modules onto one
    # card and OOM'd on the lm_head fp32 cast + CE logits). 48-layer Qwen 14B:
    #   GPU 0: embed + layers 0-15
    #   GPU 1: layers 16-31
    #   GPU 2: layers 32-47 + norm + lm_head (head fp32 ≈3.1GB on a light card)
    # Weights ≈2.5-3 GB per GPU as 4-bit; even after peft's fp32 casts each card
    # stays ~5-6 GB used, leaving plenty of room for CE logits + activations.
    n_gpus = torch.cuda.device_count()
    assert n_gpus == 3, f"expected 3 GPUs, got {n_gpus}"
    from transformers import AutoConfig
    cfg = AutoConfig.from_pretrained(MODEL_NAME, trust_remote_code=True)
    n_layers = cfg.num_hidden_layers  # 48 for Qwen2.5-Coder-14B
    per = n_layers // n_gpus
    device_map = {"model.embed_tokens": 0}
    device_map.update({f"model.layers.{i}": 0 for i in range(0, per)})        # layers  0-15
    device_map.update({f"model.layers.{i}": 1 for i in range(per, 2 * per)})  # layers 16-31
    device_map.update({f"model.layers.{i}": 2 for i in range(2 * per, n_layers)})  # 32-47
    device_map["model.norm"] = 2
    device_map["lm_head"] = 2
    phase(f"layer map: {per} layers per GPU ({n_layers} total), head on GPU 2")
    max_mem = {i: "11000MiB" for i in range(n_gpus)}
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, quantization_config=bnb, device_map=device_map, max_memory=max_mem,
        offload_folder="/tmp/offload", offload_state_dict=False,
        low_cpu_mem_usage=True,
        trust_remote_code=True, torch_dtype=torch.float16,
    )
    torch.cuda.empty_cache()
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    ))
    model.gradient_checkpointing_enable()
    t, total = model.get_nb_trainable_parameters()
    phase(f"Trainable: {t:,} / {total:,} ({100 * t / total:.2f}%)")
    torch.cuda.empty_cache()
    heartbeat(status="adapter_attached")

    # ── Dataset (masked chat template — R28/R29-proven, shape-proof ids) ──
    records = []
    for line in TRAIN_JSONL.open(encoding="utf-8"):
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
        if not output or not output.strip():
            continue
        out = output.strip()
        # Pick rows legitimately answer "NODE: A" (7 chars) — the guard below
        # must NOT drop them or the corpus's discrimination half silently
        # vanishes (R30's run only trained ~2k of its 4.9k rows for this
        # reason).  Drop only empty/garbage outputs, and keep anything that is
        # at least a few chars OR a well-formed short answer (single letter or
        # NODE: X).
        _short_ok = len(out) >= 3 and (
            len(out) >= 10
            or re.fullmatch(r"(?:NODE\s*[:=]\s*)?[ABC]", out, re.I)
        )
        if not _short_ok:
            continue
        user_text = f"{instruction}\n\n{inp}".strip() if inp else instruction
        # Rows may carry their own system prompt (pick rows send the game's
        # SYS_PROMPT so training matches the eval's scored prompt).
        sys_prompt = rec.get("system") or SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": output.strip()},
        ]
        prompt_ids = ids_of(tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True))
        full_ids = ids_of(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False))
        full_ids = full_ids[:MAX_SEQ]
        m = min(len(prompt_ids), len(full_ids))
        records.append({"input_ids": full_ids,
                        "labels": [-100] * m + full_ids[m:]})
    if not records:
        phase("❌ no valid rows")
        sys.exit(1)

    from datasets import Dataset as HFDataset, Features, Sequence, Value
    pad = tokenizer.pad_token_id or tokenizer.eos_token_id or 0
    for r in records:
        n = len(r["input_ids"])
        r["attention_mask"] = [1] * n
        if n < MAX_SEQ:
            r["input_ids"] += [pad] * (MAX_SEQ - n)
            r["labels"] += [-100] * (MAX_SEQ - n)
            r["attention_mask"] += [0] * (MAX_SEQ - n)
    feats = Features({
        "input_ids": Sequence(Value("int32")),
        "labels": Sequence(Value("int32")),
        "attention_mask": Sequence(Value("int32")),
    })
    records = [
        {k: ids_of(rec[k]) for k in ("input_ids", "labels", "attention_mask")}
        for rec in records
    ]
    ds = HFDataset.from_list(records, features=feats)
    phase(f"rows: {len(ds)} train")
    heartbeat(status="dataset-built")

    targs = TrainingArguments(
        output_dir=str(OUT_DIR),
        num_train_epochs=EPOCHS,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=5e-5,
        lr_scheduler_type="cosine",
        warmup_steps=10,
        weight_decay=0.01,
        bf16=False, fp16=True,
        logging_strategy="steps", logging_steps=5,
        save_strategy="steps", save_steps=25, save_total_limit=3,
        dataloader_num_workers=0,
        dataloader_pin_memory=False,
        remove_unused_columns=False,
        report_to="none",
        gradient_checkpointing=True,
        seed=42,
        ddp_find_unused_parameters=False,
    )
    cb_heart = HeartbeatCallback(every=5)
    phase(f"trainer-init (rows={len(ds)}, world={WORLD_SIZE})")
    trainer = Trainer(
        model=model, args=targs, train_dataset=ds,
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True,
                                             max_length=MAX_SEQ, return_tensors="pt"),
        callbacks=[cb_heart],
    )

    t0 = time.time()
    try:
        phase("train-start")
        trainer.train()
    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)
        try:
            (OUT_DIR / "crash.log").write_text(tb)
        except Exception:
            pass
        try:
            trainer.save_model(OUT_DIR / "crash-save")
            write_resume(seg_h=(time.time() - t0) / 3600,
                         steps_total=trainer.state.global_step if trainer.state else 0,
                         gpu=torch.cuda.get_device_name(LOCAL_RANK) if torch.cuda.is_available() else "CPU",
                         s_per_step=cb_heart.s_per_step)
        except Exception:
            pass
        heartbeat(status="error", phase="train")
        sys.exit(1)

    seg_h = (time.time() - t0) / 3600
    final = OUT_DIR / "final"
    trainer.save_model(final)
    try:
        tokenizer.save_pretrained(final)
    except Exception:
        pass
    resume = write_resume(seg_h=seg_h, steps_total=trainer.state.global_step,
                          gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
                          s_per_step=cb_heart.s_per_step)
    heartbeat(status="session_done", elapsed_h=resume["elapsed_h"], seg_h=round(seg_h, 3))
    print(f"\n✅ round done: {seg_h:.2f}h, {trainer.state.global_step} steps, loss "
          f"{trainer.state.log_history[-1].get('loss') if trainer.state.log_history else '?'}")
    for f in sorted(OUT_DIR.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(OUT_DIR)} ({f.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()