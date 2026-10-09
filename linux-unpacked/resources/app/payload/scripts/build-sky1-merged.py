#!/usr/bin/env python3
"""
build-sky1-merged.py — merge the Kaggle Sky-T1 LoRA into the 14B base + GGUF.
====================================================================================
The Sky1 kernel (vaca-qlora-round-sky1) trains a LoRA (r=8/alpha=16) on the
fresh base (BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored) and saves the
adapter-only to /kaggle/working/sky1-kaggle/final. kaggle-mon-sky1.sh auto-
downloads it to ROOT/training/cloud/kaggle-sky1-output/sky1-kaggle/final/.

This script (copy of the PROVEN build-r28-merged.py path):
  1. sanity-checks the adapter (r/alpha/base must match).
  2. Merges it into the fresh base across ALL THREE RTX 3060s using unsloth's
     unsloth_generic_save_pretrained_merged(save_method="merged_16bit") —
     NOT merge_and_unload()+save_pretrained() (which keeps NF4 tensors and
     OOMs). Same path as R23/R28.
  3. Validates the merge is a real 16-bit checkpoint (no quantized tensors).
  4. Exports to GGUF (default q4_k_m, matching your deployed Qwen Q4_K_M),
     via unsloth save_pretrained_gguf, falling back to the llama.cpp toolchain.

Output layout (mirrors R28):
  training/cloud/kaggle-sky1-output/sky1-kaggle/merged/   <- fp16 safetensors
  training/cloud/kaggle-sky1-output/sky1-kaggle/gguf/vaca-sky1.Q4_K_M.gguf

Usage ON THE AGENT (after kaggle-mon-sky1.sh prints "ADAPTER READY"):
  llm-training-app/.venv/bin/python scripts/build-sky1-merged.py
  GGUF_QUANT=q8_0 llm-training-app/.venv/bin/python scripts/build-sky1-merged.py
  scripts/build-sky1-merged.py --merge-only          # skip GGUF
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
SKY1 = ROOT / "training/cloud/kaggle-sky1-output" / "sky1-kaggle"
ADAPTER = SKY1 / "final"          # monitor download target (adapter + safetensors)
MERGE_OUT = SKY1 / "merged"
GGUF_OUT = SKY1 / "gguf"

BASE_MODEL = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
ALPHA, R = 16, 8
SCALE = ALPHA / R
MAX_SEQ = 3072
MAX_MEMORY = {0: "11GB", 1: "11GB", 2: "11GB"}  # all three RTX 3060 12GB

# ─── CUDA Library Path Fix (mirrors engine.py / recover-checkpoint-gguf.py) ──
_user_lib = os.path.expanduser("~/.local/lib")
_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
if _user_lib not in _ld_path:
    os.environ["LD_LIBRARY_PATH"] = _user_lib + ":" + _ld_path if _ld_path else _user_lib


def sanity() -> None:
    if not (ADAPTER / "adapter_model.safetensors").exists():
        print(
            f"❌ No Sky1 adapter at {ADAPTER} — kaggle-mon-sky1.sh must report "
            "'ADAPTER READY' first."
        )
        sys.exit(1)
    c = json.load(open(ADAPTER / "adapter_config.json"))
    assert c["lora_alpha"] == ALPHA and c["r"] == R, c
    assert c["base_model_name_or_path"] == BASE_MODEL, c["base_model_name_or_path"]
    print(f"✅ Sky1 adapter: r={c['r']} alpha={c['lora_alpha']} scale={SCALE} on {BASE_MODEL}")


def build_merged() -> None:
    import torch
    from unsloth import FastLanguageModel

    print(f"⬇️  Loading base {BASE_MODEL} (4-bit QLoRA, split across 3×3060)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ,
        dtype=None,
        load_in_4bit=True,
        device_map="auto",
        max_memory=MAX_MEMORY,
    )

    from peft import PeftModel
    model = PeftModel.from_pretrained(model, str(ADAPTER))
    print("  ✅ Adapter attached")

    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving merged 16-bit safetensors -> {MERGE_OUT.name}/")
    from unsloth.save import unsloth_generic_save_pretrained_merged
    unsloth_generic_save_pretrained_merged(
        model,
        save_directory=str(MERGE_OUT),
        tokenizer=tokenizer,
        save_method="merged_16bit",
    )
    tokenizer.save_pretrained(str(MERGE_OUT))
    print("✅ merged + tokenizer saved")
    del model
    gc()


def gc():
    import gc as _gc
    import torch
    _gc.collect()
    torch.cuda.empty_cache()


def validate() -> None:
    from safetensors import safe_open

    st_files = sorted(MERGE_OUT.glob("*.safetensors"))
    assert st_files, f"no safetensors written to {MERGE_OUT}"
    total = sum(f.stat().st_size for f in st_files)
    assert total > 20e9, (
        f"merged size {total/1e9:.1f}GB — too small for a 16-bit 14B merge; "
        "still quantized!"
    )
    for f in st_files:
        with safe_open(str(f), framework="pt") as sf:
            bad = [k for k in sf.keys() if ".absmax" in k or "quant_state" in k]
            assert not bad, f"{f.name} still contains quantized tensors: {bad[:3]}"
    cfg = json.load(open(MERGE_OUT / "config.json"))
    assert "quantization_config" not in cfg, "merged config still has quantization_config!"
    print(f"✅ merged is a real 16-bit checkpoint ({total/1e9:.1f}GB, no quantized tensors)")


def export_gguf() -> None:
    GGUF_OUT.mkdir(parents=True, exist_ok=True)
    quant = os.environ.get("GGUF_QUANT", "q4_k_m")

    # Path A (preferred): unsloth export (proven for rounds 6/10 on this box).
    try:
        import torch
        from unsloth import FastLanguageModel

        print(f"  loading merged model {MERGE_OUT} (fp16, no 4-bit)...")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(MERGE_OUT),
            max_seq_length=512,
            dtype=torch.float16,
            load_in_4bit=False,
            device_map="auto",
        )
        print(f"  exporting GGUF ({quant})...")
        model.save_pretrained_gguf(str(GGUF_OUT), tokenizer, quantization_method=quant)
        print("✅ unsloth GGUF export complete")
        del model
        gc()
        _collect_gguf()
        return
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"  ⚠️ unsloth GGUF path failed ({e}); falling back to llama.cpp toolchain")

    # Path B: llama.cpp convert + quantize.
    convert = Path.home() / ".unsloth/llama.cpp/convert_hf_to_gguf.py"
    quantize = Path.home() / ".unsloth/llama.cpp/llama-quantize"
    assert convert.exists(), f"missing {convert}"
    assert quantize.exists(), f"missing {quantize}"

    f16 = GGUF_OUT / "vaca-sky1.Q8_0.gguf"
    print(f"  llama.cpp: converting {MERGE_OUT.name} -> f16 GGUF...")
    subprocess.run(
        [sys.executable, str(convert), str(MERGE_OUT), "--outfile", str(f16), "--outtype", "q8_0"],
        check=True,
    )
    print(f"  llama.cpp: quantizing -> {quant}...")
    target = GGUF_OUT / f"vaca-sky1.{quant}.gguf"
    subprocess.run(
        [str(quantize), str(f16), str(target), quant, "--allow-requantize"],
        check=True,
    )
    _collect_gguf()


def _collect_gguf() -> None:
    ggs = sorted(f for f in GGUF_OUT.glob("*.gguf") if f.is_file() and f.stat().st_size > 0)
    if not ggs:
        print("  ❌ no .gguf produced!")
        sys.exit(1)
    for f in ggs:
        print(f"  📦 {f.name}: {f.stat().st_size/1e9:.2f} GB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-only", action="store_true", help="merge fp16; skip GGUF export")
    args = ap.parse_args()

    sanity()
    build_merged()
    validate()
    print(f"✅ Sky1 merge complete → {MERGE_OUT}")
    if args.merge_only:
        print("   (--merge-only: skipped GGUF export)")
        return
    export_gguf()


if __name__ == "__main__":
    main()