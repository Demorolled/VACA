#!/usr/bin/env python3
"""
Launch the 4-bit QLoRA fine-tune on the merged campaign50 dataset
=================================================================
- Dual GPU (DDP — recommended, 2x 12GB RTX 3060):
      torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-campaign50.py
  torchrun assigns one GPU per rank — do NOT set CUDA_VISIBLE_DEVICES here.
  Note: dspark must be stopped first (it uses BOTH GPUs):
      bash scripts/start-dspark.sh --stop
- Single GPU (fallback):
      VACA_TRAIN_GPU=1 python3 scripts/launch-qlora-campaign50.py
  (defaults to GPU 1 so dspark can stay on GPU 0)

- Base: Orion-zhen/Qwen2.5-7B-Instruct-Uncensored (matches the q4_k_m GGUF
  dspark serves) — 4-bit NF4 load + LoRA adapters + adamw_8bit = QLoRA
- Dataset: training/dataset/train.jsonl (merged: 3,262 examples incl. all
  215 campaign50-corrected per-node files + 3 captured-verified rows)
- 1 LR-decay round (2e-4) — run round 1 only, then stop and export
- Outputs to training/gui_trainer/models/ so the trainer web UI lists them,
  with GGUF export at q4_k_m
"""

import os, sys

# Under torchrun (DDP), torch manages per-rank GPU visibility. Only set
# CUDA_VISIBLE_DEVICES when running directly (single-GPU fallback).
if os.environ.get("LOCAL_RANK") is None and os.environ.get("RANK") is None:
    os.environ["CUDA_VISIBLE_DEVICES"] = os.environ.get("VACA_TRAIN_GPU", "1")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from training.gui_trainer.engine import GUITrainer  # noqa: E402

MODELS_DIR = os.path.join(BASE, "training", "gui_trainer", "models")


def main():
    rank = int(os.environ.get("LOCAL_RANK", 0))
    trainer = GUITrainer(str(MODELS_DIR))
    trainer.update_config(
        model_name="Orion-zhen/Qwen2.5-7B-Instruct-Uncensored",
        quantization="4bit",
        gguf_quantization="q4_k_m",
        max_rounds=1,
        num_epochs=2,
        max_seq_length=2048,
        batch_size=1,
        gradient_accumulation=8,
        learning_rate=2e-4,
        lora_r=8,
        lora_alpha=16,
        lora_dropout=0.05,
    )
    dataset = os.path.join(BASE, "training", "dataset", "train.jsonl")
    if rank == 0:
        print(f"[launch] DDP world_size={os.environ.get('WORLD_SIZE', 1)} "
              f"gpu={os.environ.get('CUDA_VISIBLE_DEVICES', '?')}", flush=True)
        print(f"[launch] Base model: {trainer.config['model_name']} (4-bit QLoRA)", flush=True)
        print(f"[launch] Dataset: {dataset}", flush=True)
        print(f"[launch] Outputs: {MODELS_DIR}", flush=True)

    ok = trainer.train(dataset_paths=[dataset])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
