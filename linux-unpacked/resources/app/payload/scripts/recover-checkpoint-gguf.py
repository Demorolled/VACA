#!/usr/bin/env python3
"""
Recover the trained LoRA adapter from checkpoint-340 and export to GGUF
=======================================================================
Training completed all 340 steps but crashed at the FINAL checkpoint save
(PicklingError on trl SFTConfig) — so no GGUF was ever exported. The fully
trained adapter survived in training/gui_trainer/models/checkpoint-340/.

This script:
  1. Loads the base model (Orion-zhen/Qwen2.5-7B-Instruct-Uncensored) in FP16
     (NOT 4-bit — exporting from a bitsandbytes 4-bit base raises
     NotImplementedError: Quant method is not yet supported: 'bitsandbytes')
  2. Attaches the trained LoRA adapter from checkpoint-340 (Unsloth's
     documented "pass the adapter dir" pattern, with a base+PeftModel fallback)
  3. Merges the LoRA into the base, then exports q4_k_m GGUF into
     training/gui_trainer/models/ (same dir the deploy watcher + web UI expect)

Usage:
  python3 scripts/recover-checkpoint-gguf.py [checkpoint_dir] [out_dir]
"""

import os, sys, time
from pathlib import Path

# ─── CUDA Library Path Fix (mirrors engine.py) ─────────────────────────
_user_lib = os.path.expanduser('~/.local/lib')
_ld_path = os.environ.get('LD_LIBRARY_PATH', '')
if _user_lib not in _ld_path:
    os.environ['LD_LIBRARY_PATH'] = _user_lib + ':' + _ld_path if _ld_path else _user_lib

BASE = Path(__file__).parent.parent
DEFAULT_CKPT = BASE / 'training' / 'gui_trainer' / 'models' / 'checkpoint-340'
DEFAULT_OUT = BASE / 'training' / 'gui_trainer' / 'models'

BASE_MODEL = 'Orion-zhen/Qwen2.5-7B-Instruct-Uncensored'
MAX_SEQ_LEN = 512
# Quant override: GGUF_QUANT=q4_0 (or q8_0/q5_k_m/...) — default q4_k_m.
GGUF_QUANT = os.environ.get('GGUF_QUANT', 'q4_k_m')


def log(msg: str):
    print(f'[recover] {msg}', flush=True)


def main():
    ckpt = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CKPT
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT

    log(f'checkpoint : {ckpt}')
    log(f'output dir : {out_dir}')
    assert (ckpt / 'adapter_model.safetensors').exists(), \
        f'adapter not found in {ckpt}'
    out_dir.mkdir(parents=True, exist_ok=True)

    import torch
    from unsloth import FastLanguageModel
    from peft import PeftModel

    load_kw = dict(
        max_seq_length=MAX_SEQ_LEN,
        dtype=torch.float16,          # fp16 — avoids bitsandbytes in export
        load_in_4bit=False,
        device_map='auto',            # spread across both GPUs
        token=os.environ.get('HF_TOKEN', None),
    )

    # ── Path 1: Unsloth's documented "pass the adapter dir" pattern ──
    method = 'unsloth-direct'
    model = tokenizer = None
    try:
        log(f'path-1: from_pretrained(adapter dir {ckpt}) ...')
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(ckpt), **load_kw)
    except Exception as e:
        log(f'path-1 failed: {type(e).__name__}: {e}')
        model = tokenizer = None

    # ── Path 2: load base, then wrap with PeftModel ──
    if model is None or not isinstance(model, PeftModel):
        method = 'base+peft-wrap'
        log(f'path-2: loading base {BASE_MODEL} fp16 ...')
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=BASE_MODEL, **load_kw)
        log(f'path-2: wrapping adapter from {ckpt} ...')
        model = PeftModel.from_pretrained(model, str(ckpt))
        log(f'path-2: active_adapter={getattr(model, "active_adapter", "?")}')

    log(f'loaded via {method}; type={type(model).__name__} '
        f'is_peft={isinstance(model, PeftModel)} '
        f'active_adapter={getattr(model, "active_adapter", None)}')

    # Sanity: adapter must be attached before we merge/export.
    if not isinstance(model, PeftModel):
        log('❌ model is NOT a PeftModel — refusing to export an untuned base!')
        sys.exit(2)

    # ── Merge LoRA into the base (fp16) ──
    log('merging LoRA into base (fp16)...')
    model = model.merge_and_unload()
    log(f'merged → type={type(model).__name__}')

    # ── Export ──
    log(f'exporting GGUF ({GGUF_QUANT})... this takes several minutes')
    t0 = time.time()
    model.save_pretrained_gguf(
        str(out_dir),
        tokenizer,
        quantization_method=GGUF_QUANT,
    )
    log(f'GGUF export complete in {time.time()-t0:.0f}s')

    # Unsloth's save_pretrained_gguf writes into a '<out_dir>_gguf' sibling dir.
    gguf_dir = out_dir.parent / (out_dir.name + '_gguf')
    candidates = list(out_dir.glob('*.gguf')) + list(gguf_dir.glob('*.gguf'))
    ggs = sorted(f for f in candidates if f.stat().st_size > 0)
    if not ggs:
        log('❌ no .gguf produced!')
        sys.exit(1)
    for f in ggs:
        log(f'📦 {f.name}: {f.stat().st_size/1e9:.2f} GB')
    # Unsloth leaves a ~4.4GB f16 intermediate next to the q4_k_m output;
    # reclaim the disk (only the q4_k_m is deployed). Guard: never delete the
    # final artifact if the target quant ever becomes f16.
    if GGUF_QUANT != 'f16' and gguf_dir.exists():
        for f in gguf_dir.glob('*F16*.gguf'):
            log(f'🧹 removing f16 intermediate: {f.name}')
            f.unlink(missing_ok=True)
    log('✅ done')


if __name__ == '__main__':
    main()
