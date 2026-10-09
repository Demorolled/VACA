#!/usr/bin/env python3
"""
Launch Round-4: focused QLoRA fine-tune on the blueprint-fidelity failures.
===========================================================================
Re-trains the model on the 25 prompts it failed in the round-3 validation
(data/blueprint-fidelity-validation.json), each paired with its CANONICAL
blueprint JSON. See scripts/build-round4-failures-dataset.py for the dataset.

- Dataset: training/dataset/round4-failures.jsonl (auto-built on launch)
- Optional retention mix: VACA_MIX=300 samples rows from round3-mixed.jsonl
  so the focused round does not forget other knowledge (default 0 = pure failures)
- 1 LR round (2e-4), 3 epochs — small set, so keep the round short
- Outputs to training/gui_trainer/models/ (GGUF export at q4_k_m automatic)

Usage:
  bash scripts/start-dspark.sh --stop
  python3 scripts/build-round4-failures-dataset.py            # build dataset only
  VACA_MIX=300 torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-round4-failures.py
  VACA_MIX=0 torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-round4-failures.py
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from training.gui_trainer.engine import GUITrainer  # noqa: E402

FAILURES_DATASET = os.path.join(BASE, 'training', 'dataset', 'round4-failures.jsonl')
MODELS_DIR = os.path.join(BASE, 'training', 'gui_trainer', 'models')


def main():
    # Rebuild the dataset from the latest validation report (env VACA_MIX flows
    # through to the build script for the optional retention mix).
    build = os.path.join(BASE, 'scripts', 'build-round4-failures-dataset.py')
    subprocess.run([sys.executable, build], check=True, env=os.environ.copy())

    if not os.path.exists(FAILURES_DATASET):
        print('[launch] ❌ no failure dataset — run validation first '
              '(python3 scripts/validate-blueprint-fidelity.py --all)')
        sys.exit(1)

    # The retention mix (VACA_MIX) is folded into round4-failures.jsonl by the
    # build script — nothing extra to add here.
    dataset_paths = [FAILURES_DATASET]

    trainer = GUITrainer(str(MODELS_DIR))
    trainer.update_config(
        model_name="Orion-zhen/Qwen2.5-7B-Instruct-Uncensored",
        quantization="4bit",
        gguf_quantization="q4_k_m",
        max_rounds=1,
        num_epochs=3,
        max_seq_length=2048,
        batch_size=1,
        gradient_accumulation=8,
        learning_rate=2e-4,
        lora_r=8,
        lora_alpha=16,
        lora_dropout=0.05,
    )
    print('[launch] ROUND 4: FOCUSED FAILURE RE-TRAIN | base=Qwen2.5-7B-Instruct-Uncensored | QLoRA 4bit')
    print(f'[launch] Dataset: {dataset_paths[0]} (VACA_MIX={os.environ.get("VACA_MIX", "0")})')
    print(f'[launch] Outputs: {MODELS_DIR}')

    ok = trainer.train(dataset_paths=dataset_paths)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
