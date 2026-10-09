#!/usr/bin/env python3
"""
Round-28: QLoRA the 14B on the compiled VACA corpus + distilled 27B pairs.

Follows the proven R25 local pattern (LoraConfig r=8, 3 epochs, 4-bit) but:
  - base = BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored (already cached)
  - runs on ALL 3 GPUs via FSDP (ZeRO-3) so the 14B QLoRA fits and trains
    ~2-3x faster than a single card.
  - data = round28-train.jsonl (R21-25 catch-up + distilled 27B behavior)

Run:
  source ~/.unsloth/studio/unsloth_studio/bin/activate   # or use uv python
  python3 scripts/train_r28_14b.py
"""
import json
import os
import time
import torch
from pathlib import Path

# Fragmentation fix (the OOM error's own advice): lets PyTorch reuse freed
# blocks across the layer-split, critical for a 14B on 3x12 GB cards.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
DATA = ROOT / "training/cloud/round28-train.jsonl"
OUT = ROOT / "training/cloud/out/round28-14b"
MODEL = "/home/llmlab/.cache/huggingface/hub/models--BlossomsAI--Qwen2.5-Coder-14B-Instruct-Uncensored/snapshots/dc337087cc41582701a55f55528cb7f5d0e767de"


class JsonlDataset(Dataset):
    def __init__(self, path, tokenizer, max_len=1024):
        rows = [json.loads(l) for l in open(path) if l.strip()]
        self.examples = []
        for r in rows:
            text = f"User: {r['instruction']}\n"
            if r.get("input"):
                text += f"{r['input']}\n"
            text += f"Assistant: {r['output']}"
            # No padding here — dynamic padding in the collator (batch=1 means
            # each row runs at its own length; a fixed 1024 pad wasted ~5x
            # compute on the median 183-token row). Truncate long rows only.
            enc = tokenizer(text, truncation=True, max_length=max_len,
                            return_tensors="pt")
            self.examples.append({k: v.squeeze(0) for k, v in enc.items()})

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, i):
        return self.examples[i]


def collate_pad_to_longest(batch, pad_token_id):
    """Pad a batch to its own longest sequence (dynamic padding)."""
    max_len = max(len(b["input_ids"]) for b in batch)
    input_ids, attention_mask, labels = [], [], []
    for b in batch:
        pad = max_len - len(b["input_ids"])
        ids = torch.cat([b["input_ids"], torch.full((pad,), pad_token_id, dtype=torch.long)])
        mask = torch.cat([b["attention_mask"], torch.zeros(pad, dtype=torch.long)])
        lab = ids.clone()
        lab[b["attention_mask"] == 0] = -100  # don't learn to predict padding
        input_ids.append(ids)
        attention_mask.append(mask)
        labels.append(lab)
    return {
        "input_ids": torch.stack(input_ids),
        "attention_mask": torch.stack(attention_mask),
        "labels": torch.stack(labels),
    }


def main():
    n_gpus = torch.cuda.device_count()
    print(f"GPUs: {n_gpus}x {torch.cuda.get_device_name(0)}", flush=True)
    print(f"Loading {MODEL}...", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.pad_token = tok.eos_token

    from transformers import BitsAndBytesConfig
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        ),
        use_cache=False,
        device_map="auto",  # layer-split across all 3 GPUs (proven R25 pattern)
    )
    lora = LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    )
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, lora)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)", flush=True)

    ds = JsonlDataset(DATA, tok)
    split = int(len(ds) * 0.95)
    train_ds, val_ds = torch.utils.data.random_split(ds, [split, len(ds) - split])
    print(f"Train: {len(train_ds)} | Val: {len(val_ds)}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    collate = lambda batch: collate_pad_to_longest(batch, tok.pad_token_id)
    args = TrainingArguments(
        output_dir=str(OUT),
        num_train_epochs=1,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        fp16=True,
        optim="paged_adamw_8bit",
        logging_steps=10,
        eval_strategy="no",
        save_strategy="steps",
        save_steps=200,
        save_total_limit=3,
        report_to="none",
        seed=3407,
        gradient_checkpointing=True,
    )
    trainer = Trainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
                      data_collator=collate)
    t0 = time.time()
    trainer.train()
    h = (time.time() - t0) / 3600

    final = OUT / "final"
    final.mkdir(exist_ok=True)
    model.save_pretrained(str(final))
    tok.save_pretrained(str(final))
    json.dump({
        "round": "R28-14b-distill",
        "rows": len(ds),
        "epochs": 3,
        "elapsed_h": round(h, 2),
        "gpus": n_gpus,
    }, open(final / "meta.json", "w"), indent=2)
    print(f"Done in {h:.1f}h -> {final}", flush=True)


if __name__ == "__main__":
    main()
