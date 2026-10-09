#!/usr/bin/env python3
"""
Train the Gemma 4 12B Unified (abliterated, uncensored) on the distilled 27B
rows. Uses an isolated venv (.venv-gemma) with transformers 5.16.1, because
the main unsloth stack (transformers 4.57) cannot load the `gemma4_unified`
architecture. 4-bit QLoRA on all 3 GPUs via device_map="auto".

Data: training/cloud/round28-distill-27b.jsonl
      (rows: instruction / input / output, tag r28:distill-27b)
      pure-text so we train the text path only.

Usage (ON THE AGENT):
  # smoke run: 8 rows, 4 steps — verify load + loss moves
  ./.venv-gemma/bin/python scripts/train_gemma4_12b.py --smoke

  # full run: all 132 distilled rows, 2 epochs, seq 1536
  ./.venv-gemma/bin/python scripts/train_gemma4_12b.py
"""
import argparse
import json
import os
import time
import torch
from pathlib import Path

os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    Trainer,
    default_data_collator,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
DATA = ROOT / "training/cloud/round28-distill-27b.jsonl"
OUT = ROOT / "training/cloud/out/gemma4-12b-distill"
MODEL = "/home/llmlab/Desktop/gemma4"

SYSTEM_PROMPT = (
    "You are VACA, the Video App Creation Assistant: an expert full-stack "
    "engineer and web/app builder. You produce complete, working, "
    "self-contained code. Follow the user's spec exactly."
)


def ids_of(ids):
    """Coerce apply_chat_template output to a plain list of int token ids."""
    if isinstance(ids, list):
        return ids
    if hasattr(ids, "ids"):  # tokenizers.Encoding
        return ids.ids
    try:
        return ids["input_ids"]  # BatchEncoding / dict-like (tf 5.x)
    except (KeyError, TypeError):
        return list(ids)


class ChatDataset(Dataset):
    """Build chat-formatted rows with assistant-only label masking.

    Pre-pads everything to max_len so the default collator (stacking) works —
    transformers 5.x DataCollatorForSeq2Seq chokes on plain dicts via
    tokenizer.pad.
    """

    def __init__(self, path, tokenizer, max_len=1536, limit=None):
        rows = [json.loads(l) for l in open(path) if l.strip()]
        if limit:
            rows = rows[:limit]
        self.examples = []
        pad = tokenizer.pad_token_id or tokenizer.eos_token_id or 0
        for r in rows:
            user_text = f"{r['instruction']}\n\n{r['input']}".strip() if r.get("input") else r["instruction"]
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ]
            prompt_ids = ids_of(tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True,
                truncation=True, max_length=max_len))
            full_ids = ids_of(tokenizer.apply_chat_template(
                messages + [{"role": "assistant", "content": r["output"].strip()}],
                tokenize=True, add_generation_prompt=False,
                truncation=True, max_length=max_len))
            n = len(full_ids)
            m = min(len(prompt_ids), n)  # mask system+user, keep assistant
            input_ids = full_ids + [pad] * (max_len - n)
            labels = ([-100] * m) + full_ids[m:] + ([-100] * (max_len - n))
            attention_mask = [1] * n + [0] * (max_len - n)
            self.examples.append({
                "input_ids": input_ids,
                "labels": labels,
                "attention_mask": attention_mask,
            })

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, i):
        e = self.examples[i].copy()
        e["labels"] = e["labels"]

        return e


def discover_targets(model):
    """Return the text-backbone attention+MLP proj module names for LoRA."""
    want = {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}
    mods = set()
    for name, m in model.named_modules():
        base = name.rsplit(".", 1)[-1]
        if base in want:
            mods.add(base)
    return sorted(mods)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="8 rows, 4 steps, seq 512 — verify it trains")
    ap.add_argument("--seq", type=int, default=1536)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--rows", type=int, default=None, help="cap #rows (for tests)")
    args = ap.parse_args()

    n_gpus = torch.cuda.device_count()
    print(f"GPUs: {n_gpus}x {torch.cuda.get_device_name(0)}", flush=True)

    max_len = args.seq
    row_limit = args.rows
    if args.smoke:
        max_len = 512
        row_limit = row_limit or 8

    print(f"Loading {MODEL} (4-bit QLoRA)...", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True, local_files_only=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    quant_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        quantization_config=quant_cfg,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    model.config.use_cache = False  # unified arch: no use_cache load kwarg
    targets = discover_targets(model)
    print(f"LoRA targets: {targets}", flush=True)
    lora = LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=targets,
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    ds = ChatDataset(DATA, tok, max_len=max_len, limit=row_limit)
    print(f"Dataset: {len(ds)} rows (max_len={max_len})", flush=True)

    if args.smoke:
        out_dir = ROOT / "training/cloud/out/gemma4-smoke"
    else:
        out_dir = OUT

    out_dir.mkdir(parents=True, exist_ok=True)
    steps = 4 if args.smoke else -1  # -1 = train for num_train_epochs
    train_args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        max_steps=steps,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=10 if args.smoke else 40,
        fp16=True,
        logging_strategy="steps" if args.smoke else "steps",
        logging_steps=1 if args.smoke else 10,
        save_strategy="epoch",
        save_total_limit=2,
        report_to="none",
        seed=3407,
        gradient_checkpointing=True,
        dataloader_num_workers=2,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=ds,
        data_collator=default_data_collator,
    )

    t0 = time.time()
    trainer.train()
    h = (time.time() - t0) / 3600

    final = out_dir / "final"
    final.mkdir(exist_ok=True)
    model.save_pretrained(str(final))
    tok.save_pretrained(str(final))
    json.dump({
        "model": "gemma4-12b-unified-abliterated",
        "round": "gemma4-distill-27b",
        "rows": len(ds),
        "epochs": args.epochs,
        "smoke": args.smoke,
        "elapsed_h": round(h, 2),
        "gpus": n_gpus,
    }, open(final / "meta.json", "w"), indent=2)
    print(f"Done in {h:.1f}h -> {final}", flush=True)


if __name__ == "__main__":
    main()