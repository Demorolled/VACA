#!/usr/bin/env python3
"""
build-r31-merged.py — merge the R31 LoRA (agent-trained) into the 14B base.
================================================================================
The R31 round trained a LoRA (r=8/alpha=16) on the FRESH base
(BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored) using vaca-train-venv
(transformers 5.16.1 / peft 0.20.0). Adapter is saved by the trainer to
/home/llmlab/vaca-r31/output/round31/final/.

This script:
  1. sanity-checks the adapter (r/alpha/base must match).
  2. Merges it into the base as a CLEAN fp16 checkpoint on CPU. The
     llm-training-app/.venv (unsloth, used for R23/R28 merges) has a broken
     torch install, and GPU merge_and_unload keeps NF4 tensors / OOMs, so we
     load the base fp16 in CPU RAM (~29GB; the agent has ~55GB free), attach
     the adapter with the SAME venv that trained it, and merge on CPU — the
     output is real fp16 with no quantized tensors.
  3. Exports the merged fp16 model to GGUF Q4_K_M via the llama.cpp toolchain
     (convert_hf_to_gguf.py --outtype q8_0, then llama-quantize q4_k_m),
     matching every deployed vaca model since R17.

Output layout:
  training/cloud/out/round31/merged/                  <- fp16 safetensors
  training/cloud/out/round31/gguf/vaca-r31.Q4_K_M.gguf

Usage ON THE AGENT (after training exits and final/ exists):
  /home/llmlab/vaca-train-venv/bin/python scripts/build-r31-merged.py
  ... --merge-only   (skip GGUF export)
"""
import argparse
import gc
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
ROUND31 = ROOT / "training/cloud/out/round31"
ADAPTER = Path("/home/llmlab/vaca-r31/output/round31/final")
MERGE_OUT = ROUND31 / "merged"
GGUF_OUT = ROUND31 / "gguf"

BASE_MODEL = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
ALPHA, R = 16, 8


def sanity() -> None:
    if not (ADAPTER / "adapter_model.safetensors").exists():
        print(f"❌ No R31 adapter at {ADAPTER} — training must have finished.")
        sys.exit(1)
    c = json.load(open(ADAPTER / "adapter_config.json"))
    assert c["lora_alpha"] == ALPHA and c["r"] == R, c
    base = c["base_model_name_or_path"]
    assert base == BASE_MODEL or BASE_MODEL in base, base
    print(f"✅ R31 adapter: r={c['r']} alpha={c['lora_alpha']} "
          f"(peft {c.get('peft_version')}) on {base}")


def build_merged() -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"⬇️  Loading base {BASE_MODEL} fp16 on CPU (~29GB RAM)...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map=None,           # stay on CPU — clean fp16, no 4-bit involved
        low_cpu_mem_usage=True,
    )
    tok = AutoTokenizer.from_pretrained(BASE_MODEL)

    model = PeftModel.from_pretrained(model, str(ADAPTER))
    print("  ✅ Adapter attached — merging on CPU (14B fp16, takes ~10-20 min)...")
    model = model.merge_and_unload()   # clean fp16 weights, no NF4/quant tensors
    print("  ✅ Merge complete")

    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving fp16 safetensors -> {MERGE_OUT.name}/")
    model.save_pretrained(str(MERGE_OUT), safe_serialization=True)
    tok.save_pretrained(str(MERGE_OUT))
    del model, tok
    gc.collect()
    print("✅ merged + tokenizer saved")


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
    convert = Path.home() / ".unsloth/llama.cpp/convert_hf_to_gguf.py"
    quantize = Path.home() / ".unsloth/llama.cpp/llama-quantize"
    assert convert.exists(), f"missing {convert}"
    assert quantize.exists(), f"missing {quantize}"

    q8 = GGUF_OUT / "vaca-r31.Q8_0.gguf"
    q4 = GGUF_OUT / "vaca-r31.Q4_K_M.gguf"
    print("  llama.cpp: converting merged fp16 -> Q8_0 (CPU, ~10-15 min)...")
    subprocess.run(
        [sys.executable, str(convert), str(MERGE_OUT),
         "--outfile", str(q8), "--outtype", "q8_0"],
        check=True,
    )
    print("  llama.cpp: quantizing Q8_0 -> Q4_K_M...")
    subprocess.run(
        [str(quantize), str(q8), str(q4), "q4_k_m", "--allow-requantize"],
        check=True,
    )
    for f in (q8, q4):
        print(f"  📦 {f.name}: {f.stat().st_size/1e9:.2f} GB")
    assert q4.stat().st_size > 8e9, f"Q4 GGUF only {q4.stat().st_size} bytes — refusing partial export"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    sanity()
    build_merged()
    validate()
    print(f"✅ R31 merge complete → {MERGE_OUT}")
    if args.merge_only:
        print("   (--merge-only: skipped GGUF export)")
        return
    export_gguf()


if __name__ == "__main__":
    main()