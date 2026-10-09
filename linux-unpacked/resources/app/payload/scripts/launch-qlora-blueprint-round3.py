#!/usr/bin/env python3
"""
Launch the 4-bit QLoRA round-3 fine-tune on the BLUEPRINT-JSON dataset.
=======================================================================
Trains the model to map any natural-language app request to a perfectly
structured JSON blueprint (the engine's strict Blueprint contract) — the
behavior side of the Hybrid Strategy.

- Dataset: training/dataset/blueprint-pairs.jsonl (999 prompt→blueprint-JSON
  pairs built by scripts/build-blueprint-finetune-dataset.py)
- Mixed with a seeded sample of the existing train.jsonl so code-generation
  skills are not forgotten (same pattern as round 2).
- 1 LR-decay round (2e-4), 2 epochs.
- Outputs to training/gui_trainer/models/ (GGUF export at q4_k_m automatic).

Usage:
  # Dual GPU (recommended, 2x 12GB RTX 3060); dspark must be stopped first:
  bash scripts/start-dspark.sh --stop
  torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-blueprint-round3.py
  # Single GPU (fallback; dspark can stay on GPU 0):
  VACA_TRAIN_GPU=1 python3 scripts/launch-qlora-blueprint-round3.py
  # Mix control: VACA_MIX=0 (pure blueprint), VACA_MIX=300 (default)
"""
import json
import os
import random
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from training.gui_trainer.engine import GUITrainer  # noqa: E402

BLUEPRINT_TRAIN = os.path.join(BASE, "training", "dataset", "blueprint-pairs.jsonl")
EXISTING_TRAIN = os.path.join(BASE, "training", "dataset", "train.jsonl")
MIXED_OUT = os.path.join(BASE, "training", "dataset", "round3-mixed.jsonl")
MODELS_DIR = os.path.join(BASE, "training", "gui_trainer", "models")


def build_mixed_dataset(mix_n: int) -> str:
    """Blueprint examples + a seeded random sample of existing train examples.

    The 10% internal val split (load_gui_dataset, seed 42) then draws from
    both sources, so the model keeps its code-generation behavior while
    learning blueprint-JSON shape fidelity.
    """
    if not os.path.exists(BLUEPRINT_TRAIN):
        print(f"[launch] ❌ Blueprint dataset missing: {BLUEPRINT_TRAIN}")
        print("[launch]    Run first: python3 scripts/build-blueprint-finetune-dataset.py")
        sys.exit(1)

    with open(BLUEPRINT_TRAIN, encoding="utf-8") as f:
        bp = [json.loads(l) for l in f if l.strip()]

    mixed = list(bp)
    if os.path.exists(EXISTING_TRAIN) and mix_n > 0:
        with open(EXISTING_TRAIN, encoding="utf-8") as f:
            existing = [json.loads(l) for l in f if l.strip()]
        rng = random.Random(42)
        sample = rng.sample(existing, min(mix_n, len(existing)))
        mixed.extend(sample)
        print(f"[launch] Mixed: {len(bp)} blueprint + {len(sample)} existing = {len(mixed)}")
    else:
        print(f"[launch] ⚠️  train.jsonl missing or VACA_MIX=0 — pure blueprint round ({len(mixed)})")

    with open(MIXED_OUT, "w", encoding="utf-8") as f:
        for rec in mixed:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[launch] -> {MIXED_OUT}")
    return MIXED_OUT


def main():
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
    print("[launch] ROUND 3: BLUEPRINT-JSON FIDELITY | base=Qwen2.5-7B-Instruct-Uncensored | QLoRA 4bit")
    print(f"[launch] Dataset: {dataset}")
    print(f"[launch] Outputs: {MODELS_DIR}")

    ok = trainer.train(dataset_paths=[dataset])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
