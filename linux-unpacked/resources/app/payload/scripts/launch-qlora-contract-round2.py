#!/usr/bin/env python3
"""
Launch the 4-bit QLoRA round-2 fine-tune on the CONTRACT-FIDELITY dataset
=========================================================================
Target failure mode (from data/ab-test-chess-pipeline/SUMMARY.md): the round-1
tuned model formats cleanly but invents members beyond declared exports
(board.makeMove(), board.evaluate(), board.isCheckmate()) and forgets export
contracts (no `render` export). This round teaches contract discipline.

- Dataset: training/dataset/contract-fidelity.jsonl (hand-authored, member
  whitelists + only-whitelisted outputs; see scripts/build-contract-fidelity-dataset.py)
- Mixed with a seeded sample of the existing train.jsonl so formatting rules
  learned in round 1 are NOT forgotten (catastrophic forgetting guard).
  Set VACA_MIX=0 to disable mixing (pure contract round).
- Base: Orion-zhen/Qwen2.5-7B-Instruct-Uncensored (matches the q4_k_m GGUF
  dspark serves) — 4-bit NF4 load + LoRA adapters + adamw_8bit = QLoRA
- 1 LR-decay round (2e-4), 2 epochs — small focused dataset, single pass
- Outputs to training/gui_trainer/models/ (GGUF export at q4_k_m automatic)

Usage:
  # Dual GPU (recommended, 2x 12GB RTX 3060); dspark must be stopped first:
  bash scripts/start-dspark.sh --stop
  torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-contract-round2.py
  # Single GPU (fallback; dspark can stay on GPU 0):
  VACA_TRAIN_GPU=1 python3 scripts/launch-qlora-contract-round2.py
  # Mix control: VACA_MIX=0 (pure contract), VACA_MIX=300 (default) existing examples
"""
import json
import os
import random
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from training.gui_trainer.engine import GUITrainer  # noqa: E402

MODELS_DIR = os.path.join(BASE, "training", "gui_trainer", "models")
CONTRACT_TRAIN = os.path.join(BASE, "training", "dataset", "contract-fidelity.jsonl")
EXISTING_TRAIN = os.path.join(BASE, "training", "dataset", "train.jsonl")
MIXED_OUT = os.path.join(BASE, "training", "dataset", "round2-mixed.jsonl")


def build_mixed_dataset(mix_n: int) -> str:
    """Contract examples + a seeded random sample of existing train examples.

    The 10% internal val split (load_gui_dataset, seed 42) then draws from both
    pools. Mixing prevents the small contract set from erasing the round-1
    formatting behavior (fences/prose discipline) that we want to KEEP.
    """
    if not os.path.exists(CONTRACT_TRAIN):
        print(f"[launch] ❌ Contract dataset missing: {CONTRACT_TRAIN}")
        print(f"[launch]    Run first: python3 scripts/build-contract-fidelity-dataset.py")
        sys.exit(1)
    with open(CONTRACT_TRAIN) as f:
        contract = [json.loads(l) for l in f if l.strip()]
    if mix_n <= 0:
        print(f"[launch] Pure contract round: {len(contract)} examples (VACA_MIX=0)")
        return CONTRACT_TRAIN
    if not os.path.exists(EXISTING_TRAIN):
        print(f"[launch] ⚠️  Existing train.jsonl missing ({EXISTING_TRAIN}) — falling back to pure contract round")
        return CONTRACT_TRAIN
    with open(EXISTING_TRAIN) as f:
        existing = [json.loads(l) for l in f if l.strip()]
    random.seed(42)
    sample = random.sample(existing, min(mix_n, len(existing)))
    mixed = contract + sample
    random.shuffle(mixed)
    with open(MIXED_OUT, "w") as f:
        for rec in mixed:
            f.write(json.dumps(rec) + "\n")
    print(f"[launch] Mixed dataset: {len(contract)} contract + {len(sample)} existing = {len(mixed)} -> {MIXED_OUT}")
    return MIXED_OUT


def main():
    rank = int(os.environ.get("LOCAL_RANK", 0))
    # Default mixing keeps formatting retention; VACA_MIX=0 for a pure contract round.
    mix_n = int(os.environ.get("VACA_MIX", "300"))
    dataset = build_mixed_dataset(mix_n)

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
    if rank == 0:
        print(f"[launch] ROUND 2: CONTRACT FIDELITY | base=Qwen2.5-7B-Instruct-Uncensored | QLoRA 4bit")
        print(f"[launch] Dataset: {dataset}")
        print(f"[launch] Outputs: {MODELS_DIR}")

    ok = trainer.train(dataset_paths=[dataset])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
