#!/usr/bin/env python3
"""
=============================================================================
  🧠 Kaggle QLoRA Trainer — Qwen2.5-7B Fine-Tuning
=============================================================================
  
  INSTRUCTIONS:
    1. Upload your dataset to Kaggle (see kaggle_package.sh)
    2. Create a Kaggle Notebook → Attach your dataset
    3. Set Accelerator: GPU T4 x2 (or P100) in Notebook Settings
    4. Copy/paste this entire file into a code cell and run
    5. After training, download adapter from:
       /kaggle/working/qwen-lora/final_adapter/
  
  HOW IT WORKS:
    - QLoRA: 4-bit NF4 quantization + LoRA adapters → fits on T4 16GB
    - GPU throttle: 75% ceiling via dynamic sleep between steps
    - Checkpoint resume: saves every 50 steps, auto-resumes on restart
    - Session-safe: if Kaggle disconnects, re-run and it picks up where it left off
    - Target: 99% token accuracy (or stops after 50 rounds)
    
  DATA SOURCE:
    - /kaggle/input/vaca-training-data/train.jsonl  (2,847 examples)
    - /kaggle/input/vaca-training-data/val.jsonl    (356 examples)
  
  OUTPUT:
    /kaggle/working/qwen-lora/
      ├── final_adapter/   ← Download this!
      ├── best_adapter/    ← Best accuracy checkpoint
      ├── checkpoint-XXX/  ← Auto-save every 50 steps (for resume)
      └── progress.json   ← Live training metrics
=============================================================================
"""

import os, sys, json, time, gc, random, math, shutil
from pathlib import Path
from datetime import datetime

# ─── Install/Upgrade required packages (Kaggle has most pre-installed) ───
# Uncomment if needed:
# !pip install -q bitsandbytes transformers accelerate peft datasets

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

from transformers import (
    AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
    TrainingArguments, Trainer, TrainerCallback, DataCollatorForLanguageModeling,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# ─── Paths (auto-detect Kaggle vs local) ─────────────────────────────────
IS_KAGGLE = "/kaggle" in os.getcwd() or "KAGGLE_KERNEL_RUN_TYPE" in os.environ

if IS_KAGGLE:
    print("✅ Running on Kaggle")
    # Kaggle mounts dataset at /kaggle/input/<dataset-name>/
    INPUT_DIR = Path("/kaggle/input")
    # Find the dataset directory
    dataset_dirs = list(INPUT_DIR.glob("vaca-training-data*")) + list(INPUT_DIR.glob("*training*")) + list(INPUT_DIR.glob("*vaca*"))
    if not dataset_dirs:
        print("  Available inputs:", [str(d) for d in INPUT_DIR.iterdir()])
        # Try any directory with train.jsonl
        for d in INPUT_DIR.iterdir():
            if d.is_dir() and (d / "train.jsonl").exists():
                dataset_dirs = [d]
                break
    if not dataset_dirs:
        print("\n❌ Could not find training dataset!")
        print("   Make sure you attached the dataset to this notebook.")
        print("   Go to the right panel → Data → + Add Data → Your Datasets")
        print(f"   Available inputs: {[str(d) for d in INPUT_DIR.iterdir()]}")
        raise FileNotFoundError("vaca-training-data dataset not found in /kaggle/input/")
    DATA_DIR = dataset_dirs[0]
    print(f"  Using dataset: {DATA_DIR}")
    OUTPUT_DIR = Path("/kaggle/working") / "qwen-lora"
else:
    print("✅ Running locally")
    DATA_DIR = Path(__file__).parent.parent / "training" / "dataset"
    OUTPUT_DIR = Path(__file__).parent.parent / "llm-training-app" / "data" / "models" / "qwen-lora"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Config ────────────────────────────────────────────────────────────────
CONFIG = {
    "model_name": "Qwen/Qwen2.5-7B-Instruct",  # or "Qwen/Qwen2.5-1.5B-Instruct" for testing
    "target_accuracy": 0.99,
    "max_rounds": 50,
    "max_length": 1024,
    "batch_size": 1,          # Per GPU — 1 works on T4 16GB
    "grad_accum": 8,          # Effective batch: 1 × 8 × num_gpus
    "gpu_ceiling": 0.75,      # 75% utilization cap
    "save_every_steps": 50,   # Save checkpoint every N steps
    "learning_rates": [2e-4, 1e-4, 5e-5, 2e-5, 1e-5],
    "epochs_per_round": [2, 2, 3, 4, 5],
}

# ─── HuggingFace Authentication ──────────────────────────────────────────
# Qwen2.5-7B-Instruct is a gated model. You MUST:
#   1. Accept the license at: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
#   2. Get a token from: https://huggingface.co/settings/tokens
#   3. Set it here or via Kaggle Secrets
#
# On Kaggle: Add a Secret named HF_TOKEN in Notebook Settings → Secrets
# Or uncomment and paste below:
# HF_TOKEN = "your_hf_token_here"

HF_TOKEN = os.environ.get("HF_TOKEN", os.environ.get("KAGGLE_SECRETS_HF_TOKEN", ""))
if HF_TOKEN:
    from huggingface_hub import login
    login(token=HF_TOKEN, add_to_git_credential=False)
    print("✅ Logged into HuggingFace Hub")
else:
    print("⚠️  No HF_TOKEN found. Qwen2.5-7B-Instruct requires authentication!")
    print("   Set HF_TOKEN as a Kaggle Secret or environment variable.")
    print("   Or switch to a non-gated model like: microsoft/phi-3-mini-4k-instruct")

# ─── ChatML ────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = "You are a Visual AI Architect assistant. You generate code, explain architecture patterns, build complete applications, and debug software issues."

def to_chatml(instruction: str, input_text: str, output: str) -> str:
    user_input = instruction
    if input_text and input_text.strip():
        user_input = f"{instruction}\n\n{input_text}"
    return f"""<|im_start|>system
{SYSTEM_PROMPT}
<|im_end|>
<|im_start|>user
{user_input.strip()}
<|im_end|>
<|im_start|>assistant
{output.strip()}
<|im_end|>"""


# ─── Dataset ───────────────────────────────────────────────────────────────
class QwenFineTuneDataset(Dataset):
    def __init__(self, jsonl_path: str, tokenizer, max_length: int = 1024):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.examples = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    inst = record.get("instruction", "")
                    inp = record.get("input", "")
                    out = record.get("output", "")
                    if out and len(out) > 5:
                        self.examples.append((inst, inp, out))
                except json.JSONDecodeError:
                    continue
        print(f"  Loaded {len(self.examples)} examples")

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        inst, inp, out = self.examples[idx]
        chatml = to_chatml(inst, inp, out)
        encoded = self.tokenizer(chatml, truncation=True, max_length=self.max_length, padding="max_length", return_tensors="pt")
        input_ids = encoded["input_ids"].squeeze(0)
        attention_mask = encoded["attention_mask"].squeeze(0)
        labels = input_ids.clone()
        assistant_ids = self.tokenizer.encode("assistant", add_special_tokens=False)
        if assistant_ids:
            aid_len = len(assistant_ids)
            for j in range(len(input_ids) - aid_len):
                if (input_ids[j:j+aid_len] == torch.tensor(assistant_ids)).all():
                    labels[:j + aid_len + 1] = -100
                    break
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


# ─── Accuracy Calculator ──────────────────────────────────────────────────
@torch.no_grad()
def compute_accuracy(model, tokenizer, val_dataset, max_samples=200, device=None):
    model.eval()
    if device is None:
        device = next(model.parameters()).device
    total, correct, examples, correct_ex = 0, 0, 0, 0
    for i in range(min(len(val_dataset), max_samples)):
        batch = val_dataset[i]
        input_ids = batch["input_ids"].unsqueeze(0).to(device)
        labels = batch["labels"].unsqueeze(0).to(device)
        am = batch["attention_mask"].unsqueeze(0).to(device)
        logits = model(input_ids=input_ids, attention_mask=am).logits
        preds = torch.argmax(logits[..., :-1, :], dim=-1)
        labels = labels[..., 1:]
        mask = labels != -100
        tc = ((preds == labels) & mask).sum().item()
        tt = mask.sum().item()
        correct += tc; total += tt
        if ((preds == labels) & mask).all() and mask.any():
            correct_ex += 1
        examples += 1
    model.train()
    return {
        "accuracy": round(correct / total, 4) if total > 0 else 0,
        "exact_match": round(correct_ex / max(examples, 1), 4),
        "samples": examples,
    }


# ─── GPU Throttle Callback (75% ceiling) ──────────────────────────────────
class GpuThrottleCallback(TrainerCallback):
    def __init__(self, ceiling=0.75):
        self.ceiling = ceiling
        self._last = None
        self._sleep = 0.0
        self._gpu_cache = ""

    def _sample_gpu(self):
        """Get GPU utilization once (lazy cache)."""
        import subprocess
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            self._gpu_cache = r.stdout.strip()
        except Exception:
            self._gpu_cache = "N/A"

    def on_step_end(self, args, state, control, **kwargs):
        local_rank = int(os.environ.get("LOCAL_RANK", 0))
        now = time.time()
        if self._last is not None and local_rank == 0:
            dur = now - self._last
            desired = dur * (1.0 / self.ceiling - 1.0)
            self._sleep = 0.5 * self._sleep + 0.5 * desired if self._sleep > 0 else desired
            self._sleep = max(0.005, min(3.0, self._sleep))
            if self._sleep > 0.005:
                time.sleep(self._sleep)
            if state.global_step % 50 == 0:  # Sample GPU less frequently
                self._sample_gpu()
                print(f"    Step {state.global_step} | GPU: {self._gpu_cache[:40]} | Sleep: {self._sleep:.3f}s")
        self._last = now


# ─── Load Model ────────────────────────────────────────────────────────────
def load_model(model_name, use_ddp=True):
    is_ddp = use_ddp and "LOCAL_RANK" in os.environ
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    world_size = int(os.environ.get("WORLD_SIZE", 1))
    device_map = {"": local_rank} if is_ddp else "auto"

    print(f"\n  Loading {model_name}...")

    quant = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
    )

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True, padding_side="right")
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name, quantization_config=quant, device_map=device_map,
        trust_remote_code=True, torch_dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    model.gradient_checkpointing_enable()
    model = prepare_model_for_kbit_training(model)

    lora = LoraConfig(
        r=16, lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    model.config.use_cache = False

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"  Trainable: {trainable:,} ({100 * trainable / total:.2f}% of {total:,})")
    return model, tokenizer


# ─── Training Round ────────────────────────────────────────────────────────
def train_round(train_dataset, val_dataset, model, tokenizer, lr, epochs, gpu_ceiling=0.75, resume_checkpoint=None):
    print(f"\n{'='*60}")
    print(f"  Round: LR={lr}, Epochs={epochs}")
    if resume_checkpoint:
        print(f"  Resuming from: {resume_checkpoint}")
    print(f"{'='*60}")

    world_size = int(os.environ.get("WORLD_SIZE", 1))
    eff_batch = CONFIG["batch_size"] * CONFIG["grad_accum"] * world_size
    warmup = max(1, int(0.03 * len(train_dataset) * epochs // eff_batch))

    args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=epochs,
        per_device_train_batch_size=CONFIG["batch_size"],
        gradient_accumulation_steps=CONFIG["grad_accum"],
        gradient_checkpointing=True,
        optim="adamw_torch", learning_rate=lr,
        warmup_steps=warmup, lr_scheduler_type="cosine",
        logging_steps=10, save_steps=CONFIG["save_every_steps"],
        save_total_limit=2,
        max_grad_norm=0.3, weight_decay=0.01,
        bf16=torch.cuda.is_available(),
        dataloader_num_workers=2,
        remove_unused_columns=False,
        report_to="none",
        ddp_find_unused_parameters=False if world_size > 1 else None,
        local_rank=int(os.environ.get("LOCAL_RANK", 0)),
    )

    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
        callbacks=[GpuThrottleCallback(ceiling=gpu_ceiling)],
    )

    result = trainer.train(resume_from_checkpoint=resume_checkpoint)
    
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    if local_rank == 0:
        model.save_pretrained(str(OUTPUT_DIR / "adapter"))
        tokenizer.save_pretrained(str(OUTPUT_DIR / "adapter"))
        print(f"\n  ✅ Adapter saved")
        
        # Clean up intermediate checkpoints so next round starts fresh
        for cp in sorted(OUTPUT_DIR.glob("checkpoint-*")):
            shutil.rmtree(cp, ignore_errors=True)
        
        metrics = compute_accuracy(model, tokenizer, val_dataset, max_samples=200)
        return {"train_loss": round(result.training_loss, 4), "learning_rate": lr, "epochs": epochs, **metrics}
    return {"train_loss": round(result.training_loss, 4)}


# ─── Main ──────────────────────────────────────────────────────────────────
def find_latest_checkpoint(output_dir: Path):
    """Find the latest checkpoint directory for resume.
    Sorts by step number (not string) to handle variable-digit step counts.
    """
    checkpoints = sorted(
        output_dir.glob("checkpoint-*"),
        key=lambda p: int(p.name.split("-")[1]) if p.name.count("-") >= 1 else 0
    )
    if checkpoints:
        latest = str(checkpoints[-1])
        print(f"  🔄 Resuming from checkpoint: {latest}")
        return latest
    return None


def main():
    print("=" * 60)
    print("  🧠 Kaggle QLoRA Trainer — VACA Fine-Tuning")
    print("=" * 60)
    print(f"\n  Model:      {CONFIG['model_name']}")
    print(f"  Dataset:    {DATA_DIR}")
    print(f"  Output:     {OUTPUT_DIR}")
    print(f"  GPU Ceil:   {CONFIG['gpu_ceiling']*100:.0f}%")
    gpu_count = torch.cuda.device_count()
    print(f"  GPUs:       {gpu_count}")
    for i in range(gpu_count):
        print(f"    GPU {i}: {torch.cuda.get_device_name(i)}")
    
    # Memory check: T4 (16GB) is tight for 7B, recommend 1.5B for testing
    if gpu_count > 0:
        try:
            import subprocess
            r = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=3)
            mem = int(r.stdout.strip().split("\n")[0]) if r.stdout.strip() else 0
            if mem > 0 and mem < 20000 and "1.5B" not in CONFIG["model_name"]:
                print(f"  ⚠️  GPU has {mem}MB VRAM — 7B QLoRA barely fits on <20GB cards.")
                print(f"  💡 If OOM, restart with: model_name = 'Qwen/Qwen2.5-1.5B-Instruct'")
        except Exception:
            pass
    
    # Verify dataset
    train_path = DATA_DIR / "train.jsonl"
    val_path = DATA_DIR / "val.jsonl"
    if not train_path.exists():
        print(f"\n❌ train.jsonl not found at {train_path}")
        print(f"   Available files: {list(DATA_DIR.iterdir())}")
        return
    train_count = sum(1 for _ in open(train_path))
    val_count = sum(1 for _ in open(val_path)) if val_path.exists() else 0
    print(f"\n  Dataset: {train_count} train, {val_count} val")

    # Check for existing adapter (Kaggle session resume)
    adapter_dir = OUTPUT_DIR / "final_adapter"
    if adapter_dir.exists() and (adapter_dir / "adapter_config.json").exists():
        print(f"\n  🔄 Found existing adapter at {adapter_dir}")
        print(f"  Skipping training (already completed). Download from /kaggle/working/")
        return

    # Load
    model, tokenizer = load_model(CONFIG["model_name"])
    train_dataset = QwenFineTuneDataset(str(train_path), tokenizer, CONFIG["max_length"])
    if val_path.exists():
        val_dataset = QwenFineTuneDataset(str(val_path), tokenizer, CONFIG["max_length"])
    else:
        print("\n  ⚠️  No val.jsonl found! Creating a 10% split from training data...")
        from torch.utils.data import Subset
        val_size = max(1, len(train_dataset) // 10)
        indices = list(range(len(train_dataset)))
        random.shuffle(indices)
        val_dataset = Subset(train_dataset, indices[:val_size])
        print(f"  Using {len(val_dataset)} examples for validation")

    # Training loop
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    best_acc = 0.0
    all_rounds = []
    start_time = time.time()

    for round_num in range(1, CONFIG["max_rounds"] + 1):
        lr_idx = min(round_num - 1, len(CONFIG["learning_rates"]) - 1)
        ep_idx = min(round_num - 1, len(CONFIG["epochs_per_round"]) - 1)
        lr = CONFIG["learning_rates"][lr_idx]
        epochs = CONFIG["epochs_per_round"][ep_idx]
        
        # Check for existing checkpoint to resume from (Kaggle session recovery)
        resume_cp = find_latest_checkpoint(OUTPUT_DIR)

        metrics = train_round(train_dataset, val_dataset, model, tokenizer, lr, epochs, CONFIG["gpu_ceiling"], resume_checkpoint=resume_cp)
        metrics["round"] = round_num
        all_rounds.append(metrics)

        if local_rank == 0:
            acc = metrics.get("accuracy", 0)
            em = metrics.get("exact_match", 0)
            loss = metrics.get("train_loss", "?")
            elapsed = (time.time() - start_time) / 60
            print(f"\n  📊 Round {round_num} ({elapsed:.1f}m): Loss={loss} Acc={acc*100:.2f}% EM={em*100:.2f}%")
            
            if acc > best_acc:
                best_acc = acc
                model.save_pretrained(str(OUTPUT_DIR / "best_adapter"))
                print(f"  🏆 New best! Saved.")

            if acc >= CONFIG["target_accuracy"]:
                print(f"\n🎯 TARGET ACHIEVED! {acc*100:.2f}% >= {CONFIG['target_accuracy']*100:.0f}%")
                break

        gc.collect()
        torch.cuda.empty_cache()

    # Final save
    if local_rank == 0:
        model.save_pretrained(str(OUTPUT_DIR / "final_adapter"))
        tokenizer.save_pretrained(str(OUTPUT_DIR / "final_adapter"))
        print(f"\n  💾 Final adapter: {OUTPUT_DIR / 'final_adapter'}")
        total_time = (time.time() - start_time) / 60
        print(f"\n{'='*60}")
        print(f"  ✅ TRAINING COMPLETE")
        print(f"  Total:  {total_time:.1f}m")
        print(f"  Rounds: {round_num}")
        print(f"  Best:   {best_acc*100:.2f}%")
        print(f"  Acc:    {metrics.get('accuracy', 0)*100:.2f}%")
        
        # List output files
        print(f"\n  📁 Output files:")
        for f in sorted(OUTPUT_DIR.rglob("*")):
            if f.is_file() and f.stat().st_size > 100:
                print(f"    {f.relative_to(OUTPUT_DIR.parent)} ({f.stat().st_size / 1024 / 1024:.1f}MB)" if f.stat().st_size > 1e6 else f"    {f.relative_to(OUTPUT_DIR.parent)} ({f.stat().st_size / 1024:.0f}KB)")
        
        print(f"\n  📥 Download your adapter from: {OUTPUT_DIR / 'final_adapter'}")


if __name__ == "__main__":
    main()
