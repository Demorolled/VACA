#!/usr/bin/env python3
"""
Launch Round-5: full-knowledge QLoRA fine-tune on the blueprint pairs.
=====================================================================
Round-3 trained on the FULL 1,230-pair file (leaked the val/test instructions
into train), so its 59% fidelity was inflated by memorization. Round-4 trained
on the 25 failures only and drifted the app_type vocabulary (59 -> 45.9%:
11 fixed / 19 regressed). Round-5 trains on the CLEAN knowledge split:

  * blueprint-pairs-train.jsonl  (1,108 rows / 1,108 distinct app types)
  * round4-failures.jsonl        (reinforcement, ROUND5_INCLUDE_R4=1)
  * VACA_MIX=300                 (retention mix from round3-mixed.jsonl)

Eval stays genuinely held out (blueprint-pairs-test.jsonl / val.jsonl, 61 each
— never touched by this round). The engine's validation split (if used) comes
from the trainer, not from these files.

- Dataset: training/dataset/round5-blueprints.jsonl (auto-built on launch)
- 2 epochs (1,170 examples x 2 / eff-batch 16 ≈ 146 steps; seq 2048 on
  2x RTX 3060 runs ~40 s/it, so budget ~1.5-2 h wall time before GGUF export)
- Eval-ceiling note: the row-level split leaves only 15/61 test app_types
  present in train, so exact/fidelity can top out near ~25% even with a
  perfect model; the known gate (emit a valid library key) is the real
  generalization signal. Compare against round-4's 45.9% with that in mind.
- Outputs to training/gui_trainer/models/ (GGUF q4_k_m export automatic)

Usage (NOT run automatically — launch when ready):
  bash scripts/start-dspark.sh --stop
  python3 scripts/build-round5-blueprints-dataset.py      # build dataset only
  torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-round5-blueprints.py
"""
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from training.gui_trainer.engine import GUITrainer  # noqa: E402

DATASET = os.path.join(BASE, 'training', 'dataset', 'round5-blueprints.jsonl')
MODELS_DIR = os.path.join(BASE, 'training', 'gui_trainer', 'models')


def main():
    build = os.path.join(BASE, 'scripts', 'build-round5-blueprints-dataset.py')
    subprocess.run([sys.executable, build], check=True, env=os.environ.copy())

    if not os.path.exists(DATASET):
        print('[launch] ❌ round-5 dataset missing — run the build script first')
        sys.exit(1)

    with open(DATASET, encoding='utf-8') as f:
        n_rows = sum(1 for _ in f)

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
    print('[launch] ROUND 5: FULL-KNOWLEDGE BLUEPRINT RE-TRAIN | base=Qwen2.5-7B-Instruct-Uncensored | QLoRA 4bit')
    print(f'[launch] Dataset: {DATASET} ({n_rows} rows) '
          f'ROUND5_INCLUDE_R4={os.environ.get("ROUND5_INCLUDE_R4", "1")} '
          f'VACA_MIX={os.environ.get("VACA_MIX", "300")}')
    print(f'[launch] Eval (held out, untouched): blueprint-pairs-test.jsonl + val.jsonl (61 each)')
    print(f'[launch] Outputs: {MODELS_DIR}')

    ok = trainer.train(dataset_paths=[DATASET])
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
