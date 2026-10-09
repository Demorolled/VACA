#!/usr/bin/env python3
"""
Launch the 3D-rendering QLoRA fine-tune round (strategy: data/library/44).
================================================================================
Teaches the tuned Qwen2.5 to generate STUNNING single-file 3D GUI apps
(Three.js r128 via CDN, real 3D scenes, animated chess, particles).

  * SFT on the 3D chunk: new training data set/chunk-3d.jsonl — nine verified
    full 3D apps (every one renders green under scripts/smoke-test-html.py):
    chess (rules + minimax AI), solar system, product showcase, Rubik's cube,
    maze explorer, particle fireworks, terrain viewer, torus knot, 3D bar
    chart; plus 13 focused recipe rows distilled from the same apps. With
    seq 3072 the compact full-app rows (1.8k–2.7k tokens) are seen complete;
    only 3d-chess (~7.7k) truncates, like larger rows across the corpus.
  * QLoRA 4-bit on Qwen2.5-7B-Instruct-Uncensored via the proven GUITrainer
    engine (training/gui_trainer/engine.py), GGUF q4_k_m export automatic.
  * Retention mix (anti-regression): chunk-1.jsonl (the 2D corpus) sampled at
    GUI_MIX_RATIO (default 0.15) so the round can't regress the 2D/UI quality
    built in earlier rounds. The 3D rows are 25% of the chunk, the 2D mix
    keeps the rest of the corpus alive.
  * Post-round: re-deploy via scripts/deploy-tuned-dspark.sh (the deploy
    watcher picks the q4_k_m export up automatically), then run the 3D probe
    set (scripts/test-one-shot.py "a 3d chess game ...") and check the new
    renderSmoke field in the response.

NOT run automatically — training pins both GPUs for hours. Launch when ready:

  bash scripts/start-dspark.sh --stop          # free the GPUs
  python3 scripts/launch-qlora-3d-round.py --dry-run
  python3 scripts/launch-qlora-3d-round.py
  torchrun --standalone --nproc_per_node=2 scripts/launch-qlora-3d-round.py
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

DEFAULT_DATASET = os.path.abspath(os.path.join(BASE, '..', 'new training data set', 'chunk-3d.jsonl'))
RETENTION_DATASET = os.path.abspath(os.path.join(BASE, '..', 'new training data set', 'chunk-1.jsonl'))
MODELS_DIR = os.path.join(BASE, 'training', 'gui_trainer', 'models')


def count_rows(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, encoding='utf-8') as f:
        return sum(1 for line in f if line.strip())


def main():
    ap = argparse.ArgumentParser(description='Launch the 3D-rendering QLoRA round (SFT).')
    ap.add_argument('dataset', nargs='?', default=os.environ.get('D3D_DATASET', DEFAULT_DATASET),
                    help='3D dataset (JSONL, {instruction,input,output}); default: new training data set/chunk-3d.jsonl')
    ap.add_argument('--seq', type=int, default=3072, help='max_seq_length (3072 fits the compact 3D full-app rows; '
                    'focused rows fit, raise at your own step-time risk)')
    ap.add_argument('--no-mix', action='store_true', help='skip the chunk-1 2D retention mix')
    ap.add_argument('--mix-ratio', type=float, default=float(os.environ.get('D3D_MIX_RATIO', '0.15')),
                    help='fraction of chunk-1.jsonl rows to retain (default 0.15)')
    ap.add_argument('--dry-run', action='store_true', help='validate config + datasets, do NOT train')
    args = ap.parse_args()

    if not (0.0 <= args.mix_ratio <= 1.0):
        print(f'[launch] ❌ --mix-ratio must be in [0, 1], got {args.mix_ratio!r}')
        sys.exit(1)

    if not os.path.exists(args.dataset):
        print(f'[launch] ❌ 3D dataset missing: {args.dataset}')
        print('[launch]   Build it with: python3 "new training data set/build-3d-chunk.py"')
        sys.exit(1)

    n_rows = count_rows(args.dataset)
    print(f'[launch] 3D dataset: {args.dataset} ({n_rows} row(s))')

    mix_paths = [] if args.no_mix else [RETENTION_DATASET]
    if mix_paths:
        if not os.path.exists(RETENTION_DATASET):
            print(f'[launch] ⚠️  retention dataset missing ({RETENTION_DATASET}) — mixing disabled')
            mix_paths = []
        else:
            n_ret = count_rows(RETENTION_DATASET)
            keep = max(1, int(round(n_ret * args.mix_ratio)))
            print(f'[launch] retention mix: chunk-1.jsonl → up to {keep} of {n_ret} rows '
                  f'({args.mix_ratio:.0%}) via engine mix_paths/mix_ratio')
    else:
        print('[launch] retention mix disabled (--no-mix)')

    print('[launch] 3D-ROUND | base=Qwen2.5-7B-Instruct-Uncensored | QLoRA 4bit | '
          f'seq={args.seq} | lora_r=8 | epochs=2')
    print(f'[launch] Outputs: {MODELS_DIR} (GGUF q4_k_m export automatic)')
    print('[launch] Post-round: deploy-tuned-dspark.sh (auto) → probe 3D requests and read '
          'renderSmoke in test-one-shot.py output → measure the delta vs the 3D baseline.')
    print('[launch] Gate: data/library/44-threejs-scene-recipes.md is already injected into '
          'every generation prompt — the round cements those recipes in the weights.')

    if args.dry_run:
        print('[launch] --dry-run: config validated, training NOT started')
        sys.exit(0)

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
