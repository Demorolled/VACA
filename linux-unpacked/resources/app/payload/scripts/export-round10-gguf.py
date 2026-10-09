#!/usr/bin/env python3
"""
Export the round-10 merged safetensors -> q4_k_m GGUF via unsloth
==================================================================
The round-10 Kaggle kernel ran with --no-gguf and output an already-merged
16-bit model (out/model-0000{1-4}.safetensors + config/tokenizer). The raw
llama.cpp convert_hf_to_gguf.py path fails against transformers 4.57 (the
tokenizer_config carries a Qwen2.5-VL style `extra_special_tokens` list that
breaks `_set_model_specific_special_tokens`), so we reuse the proven unsloth
export path (same env that successfully exported round 6 on this machine).

Usage:
  python3 scripts/export-round10-gguf.py [quant]
  GGUF_QUANT=q8_0 python3 scripts/export-round10-gguf.py
"""

import os
import sys
import time
from pathlib import Path

# ─── CUDA Library Path Fix (mirrors engine.py / recover-checkpoint-gguf.py) ──
_user_lib = os.path.expanduser("~/.local/lib")
_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
if _user_lib not in _ld_path:
    os.environ["LD_LIBRARY_PATH"] = _user_lib + ":" + _ld_path if _ld_path else _user_lib

BASE = Path(__file__).resolve().parent.parent
MERGED = BASE / "training" / "cloud" / "out" / "round10" / "merged"
OUT = BASE / "training" / "cloud" / "out" / "round10"
GGUF_QUANT = os.environ.get("GGUF_QUANT", sys.argv[1] if len(sys.argv) > 1 else "q4_k_m")


def log(msg: str):
    print(f"[export-r10] {msg}", flush=True)


def main():
    import torch
    from unsloth import FastLanguageModel

    assert (MERGED / "config.json").exists(), f"missing {MERGED}/config.json"
    assert list(MERGED.glob("model-*.safetensors")), f"no safetensors in {MERGED}"
    OUT.mkdir(parents=True, exist_ok=True)

    log(f"loading merged model {MERGED} (fp16, no 4-bit)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(MERGED),
        max_seq_length=512,
        dtype=torch.float16,
        load_in_4bit=False,
        device_map="auto",
        token=os.environ.get("HF_TOKEN", None),
    )
    log(f"loaded type={type(model).__name__}")

    log(f"exporting GGUF ({GGUF_QUANT}) — this takes several minutes...")
    t0 = time.time()
    model.save_pretrained_gguf(str(OUT), tokenizer, quantization_method=GGUF_QUANT)
    log(f"GGUF export complete in {time.time() - t0:.0f}s")

    # Unsloth writes into a '<model_dir>_gguf' sibling dir (named after the
    # model dir, e.g. 'merged_gguf'). Search OUT, '<OUT>_gguf' and any
    # '*_gguf' sibling of OUT to be robust to the naming.
    gguf_dirs = [OUT, OUT.parent / (OUT.name + "_gguf")]
    gguf_dirs += [p for p in OUT.parent.glob("*_gguf") if p not in gguf_dirs]
    candidates = [f for d in gguf_dirs for f in d.glob("*.gguf")]
    ggs = sorted(f for f in candidates if f.is_file() and f.stat().st_size > 0)
    if not ggs:
        log("❌ no .gguf produced!")
        sys.exit(1)
    for f in ggs:
        log(f"📦 {f.name}: {f.stat().st_size / 1e9:.2f} GB")
    if GGUF_QUANT != "f16":
        for d in gguf_dirs:
            for f in d.glob("*F16*.gguf"):
                log(f"🧹 removing f16 intermediate: {f.name}")
                f.unlink(missing_ok=True)
    log("✅ done")


if __name__ == "__main__":
    main()
