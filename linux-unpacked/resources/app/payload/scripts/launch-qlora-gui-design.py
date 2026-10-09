#!/usr/bin/env python3
"""
Launch the GUI-design QLoRA fine-tune round (strategy: GUI.odt).
================================================================
Implements the fine-tuning side of the GUI-design training plan:

  * SFT on a component/GUI-design dataset (default training/dataset/gui-design.jsonl,
    {instruction, input, output} JSONL — same schema the engine already eats).
  * QLoRA 4-bit on Qwen2.5-7B-Instruct-Uncensored via the proven GUITrainer
    engine (training/gui_trainer/engine.py). Target modules are ALREADY every
    linear layer the plan calls for (q/k/v/o_proj + gate/up/down_proj) — the
    engine's hard-coded get_peft_model list.
  * Context: default 2048 (proven on 2x RTX 3060 12GB, ~40 s/it per round-5).
    The plan says >=8192; that is available via --seq 8192 but at ~4x the
    memory/time per step — 12GB per card is the constraint, so default stays
    2048 and --seq is the override.
  * Retention mix (anti-regression): passed to the engine as the
    mix_paths/mix_ratio config keys — load_datasets samples
    training/dataset/round8-code.jsonl down to GUI_MIX_RATIO (default 0.15)
    of its rows (deterministic) and appends them to the GUI rows, so the
    GUI round can't regress prior code capability. Disable with --no-mix.
  * GGUF q4_k_m export is automatic (engine), landing in training/gui_trainer/models/.

NOT run automatically — training pins both GPUs for hours. Launch when ready:

  bash scripts/start-dspark.sh --stop          # free the GPUs
  python3 scripts/launch-qlora-gui-design.py                 # default dataset
  python3 scripts/launch-qlora-gui-design.py /path/to/gui.jsonl --seq 4096
  torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-gui-design.py

Dataset format (the plan's "component pairs", schemas compatible with the engine):
  {"instruction": "Build a modern auth screen...", "input": "", "output": "<html>...", "source": "curriculum:GUI:..."}
  Rows whose output is < 10 chars are dropped by the engine.
  DPO (chosen/rejected triplets) is a LATER round — this launcher is SFT-only.
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

DEFAULT_DATASET = os.path.join(BASE, 'training', 'dataset', 'gui-design.jsonl')
RETENTION_DATASET = os.path.join(BASE, 'training', 'dataset', 'round8-code.jsonl')
MODELS_DIR = os.path.join(BASE, 'training', 'gui_trainer', 'models')


def count_rows(path: str) -> int:
    """Fast line count for a JSONL file (used by --dry-run, no deps needed)."""
    if not os.path.exists(path):
        return 0
    with open(path, encoding='utf-8') as f:
        return sum(1 for line in f if line.strip())


def main():
    ap = argparse.ArgumentParser(description='Launch the GUI-design QLoRA round (SFT).')
    ap.add_argument('dataset', nargs='?', default=os.environ.get('GUI_DATASET', DEFAULT_DATASET),
                    help='GUI-design dataset (JSONL, {instruction,input,output}); '
                         'default: $GUI_DATASET or training/dataset/gui-design.jsonl')
    ap.add_argument('--seq', type=int, default=2048, help='max_seq_length (plan says >=8192; '
                    '2x12GB proven at 2048 — raise at your own step-time risk)')
    ap.add_argument('--no-mix', action='store_true', help='skip the round8-code retention mix')
    ap.add_argument('--mix-ratio', type=float, default=float(os.environ.get('GUI_MIX_RATIO', '0.15')),
                    help='fraction of round8-code.jsonl rows to retain (default 0.15)')
    ap.add_argument('--dry-run', action='store_true', help='validate config + datasets, do NOT train')
    args = ap.parse_args()

    if not (0.0 <= args.mix_ratio <= 1.0):
        print(f'[launch] ❌ --mix-ratio must be in [0, 1], got {args.mix_ratio!r}')
        sys.exit(1)

    if not os.path.exists(args.dataset):
        print(f'[launch] ❌ GUI dataset missing: {args.dataset}')
        print('[launch]   Create a JSONL of {instruction, input, output} rows — e.g. from the')
        print('[launch]   projects/ corpus (component pairs) or curriculum/out/dataset/*.jsonl,')
        print('[launch]   then re-run. See the GUI.odt plan (component pairs, design tokens,')
        print('[launch]   optional bounding-box annotation).')
        sys.exit(1)

    n_rows = count_rows(args.dataset)
    print(f'[launch] GUI dataset: {args.dataset} ({n_rows} row(s))')

    mix_paths = [] if args.no_mix else [RETENTION_DATASET]
    if mix_paths:
        if not os.path.exists(RETENTION_DATASET):
            print(f'[launch] ⚠️  retention dataset missing ({RETENTION_DATASET}) — mixing disabled')
            mix_paths = []
        else:
            n_ret = count_rows(RETENTION_DATASET)
            keep = max(1, int(round(n_ret * args.mix_ratio)))
            print(f'[launch] retention mix: {RETENTION_DATASET} → up to {keep} of {n_ret} rows '
                  f'({args.mix_ratio:.0%}) via engine mix_paths/mix_ratio')
    else:
        print('[launch] retention mix disabled (--no-mix)')

    print('[launch] GUI-DESIGN ROUND | base=Qwen2.5-7B-Instruct-Uncensored | QLoRA 4bit | '
          f'seq={args.seq} | lora_r=8 | epochs=2')
    print('[launch] Target modules: q/k/v/o_proj + gate/up/down_proj (engine default — '
          'every linear layer, per the plan)')
    print(f'[launch] Outputs: {MODELS_DIR} (GGUF q4_k_m export automatic)')
    print('[launch] Post-round: re-deploy via scripts/deploy-tuned-dspark.sh, then re-run '
          '`eval` to measure the GUI delta; DPO (taste) is a later round.')

    if args.dry_run:
        print('[launch] --dry-run: config validated, training NOT started')
        sys.exit(0)

    # Lazy import: torch/trl/unsloth are only needed to actually train, so
    # --help / --dry-run / the missing-dataset error work in any environment.
    from training.gui_trainer.engine import GUITrainer  # noqa: E402
    trainer = GUITrainer(str(MODELS_DIR))
    trainer.update_config(
        model_name='Orion-zhen/Qwen2.5-7B-Instruct-Uncensored',
        quantization='4bit',
        gguf_quantization='q4_k_m',
        max_rounds=1,
        num_epochs=2,
        max_seq_length=args.seq,
        batch_size=1,
        gradient_accumulation=8,
        learning_rate=2e-4,
        lora_r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        mix_paths=mix_paths,
        mix_ratio=args.mix_ratio,
    )
    ok = trainer.train(dataset_paths=[args.dataset])
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
