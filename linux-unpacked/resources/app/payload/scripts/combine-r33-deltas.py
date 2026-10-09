#!/usr/bin/env python3
"""
combine-r33-deltas.py — LoRA DELTA AVERAGING of the two R33 half-adapters
==========================================================================
The R33 corpus was split into two DISJOINT halves trained in PARALLEL:
  local  : 1,500 most-valuable rows -> agent 3x3060 (train_r33_agent.py)
          adapter at /home/llmlab/vaca-r33/output/round33/final
  kaggle : overflow rows (~2,345)  -> Kaggle T4 (train_r33_kaggle.py)
          adapter harvested to training/cloud/kaggle-r33-output/.../final

Both halves are FRESH QLoRA r8/α16 on the SAME base
(BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored) — but with independent
random LoRA-A initializations, so you CANNOT average their matrices
elementwise. The correct combine is DELTA averaging:

    W_combined = W_base + (Δ_local + Δ_kaggle) / 2

PEFT 0.20 implements exactly this via add_weighted_adapter() with
combination_type="linear" (it stacks the two decompositions so the merged
product reproduces the weighted sum of deltas), then merge_and_unload()
into a clean fp16 checkpoint on CPU — same proven merge path as r31.

Steps:
  1. sanity: both adapters same r/alpha/base
  2. load base fp16 on CPU (~29GB), attach adapter A as "local"
  3. load adapter B as "kaggle", weighted-combine [0.5, 0.5]
  4. merge_and_unload -> clean fp16 -> save to round33-out/merged
  5. GGUF: convert Q8_0 -> quantize Q4_K_M (same deploy chain as R17-R31)
Output layout (mirrors round31):
  training/cloud/out/round33/merged/            fp16 safetensors
  training/cloud/out/round33/gguf/vaca-r33.Q4_K_M.gguf
Usage ON THE AGENT (after BOTH halves finish + kaggle adapter harvested):
  /home/llmlab/vaca-train-venv/bin/python scripts/combine-r33-deltas.py
  ... --merge-only   (skip GGUF export)
"""
import argparse
import gc
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
ROUND33 = ROOT / "training/cloud/out/round33"
ADAPTER_LOCAL = Path("/home/llmlab/vaca-r33/output/round33/final")
# Kaggle adapter: harvested by kaggle-mon-r33.sh; final/ extracted there.
ADAPTER_KAGGLE = ROOT / "training/cloud/kaggle-r33-output/final"
MERGE_OUT = ROUND33 / "merged"
GGUF_OUT = ROUND33 / "gguf"
BASE_MODEL = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
ALPHA, R = 16, 8
WEIGHTS = [0.5, 0.5]


def sanity() -> None:
    for label, p in (("local", ADAPTER_LOCAL), ("kaggle", ADAPTER_KAGGLE)):
        if not (p / "adapter_model.safetensors").exists():
            print(f"❌ No {label} adapter at {p} — training must have finished.")
            sys.exit(1)
        c = json.load(open(p / "adapter_config.json"))
        assert c["lora_alpha"] == ALPHA and c["r"] == R, (label, c)
        base = c["base_model_name_or_path"]
        assert base == BASE_MODEL or BASE_MODEL in base, (label, base)
        print(f"✅ {label} adapter: r={c['r']} alpha={c['lora_alpha']} "
              f"(peft {c.get('peft_version')}) on {base}")


def build_combined() -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"⬇️  Loading base {BASE_MODEL} fp16 on CPU (~29GB RAM)...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.float16, device_map=None,
        low_cpu_mem_usage=True,
    )
    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    print("  Attaching local adapter as 'local'...")
    model = PeftModel.from_pretrained(model, str(ADAPTER_LOCAL), adapter_name="local")
    print("  Loading kaggle adapter as 'kaggle'...")
    model.load_adapter(str(ADAPTER_KAGGLE), adapter_name="kaggle")
    model.set_adapter(["local", "kaggle"])
    print(f"  Weighted delta combination (linear, weights={WEIGHTS})...")
    model.add_weighted_adapter(
        adapters=["local", "kaggle"],
        weights=WEIGHTS,
        combination_type="linear",
        adapter_name="r33-combined",
    )
    model.set_adapter("r33-combined")
    print("  Merging on CPU (14B fp16, ~10-20 min)...")
    model = model.merge_and_unload()   # clean fp16, no NF4 tensors
    print("  ✅ Combined merge complete")
    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving fp16 safetensors -> {MERGE_OUT.name}/")
    model.save_pretrained(str(MERGE_OUT), safe_serialization=True)
    tok.save_pretrained(str(MERGE_OUT))
    del model, tok
    gc.collect()
    print("✅ combined + tokenizer saved")


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
    print(f"✅ combined is a real 16-bit checkpoint ({total/1e9:.1f}GB, no quantized tensors)")


def export_gguf() -> None:
    GGUF_OUT.mkdir(parents=True, exist_ok=True)
    convert = Path.home() / ".unsloth/llama.cpp/convert_hf_to_gguf.py"
    quantize = Path.home() / ".unsloth/llama.cpp/llama-quantize"
    assert convert.exists(), f"missing {convert}"
    assert quantize.exists(), f"missing {quantize}"
    q8 = GGUF_OUT / "vaca-r33.Q8_0.gguf"
    q4 = GGUF_OUT / "vaca-r33.Q4_K_M.gguf"
    print("  llama.cpp: converting merged fp16 -> Q8_0 (CPU, ~10-15 min)...")
    subprocess.run([sys.executable, str(convert), str(MERGE_OUT),
                    "--outfile", str(q8), "--outtype", "q8_0"], check=True)
    print("  llama.cpp: quantizing Q8_0 -> Q4_K_M...")
    subprocess.run([str(quantize), str(q8), str(q4), "q4_k_m", "--allow-requantize"],
                   check=True)
    for f in (q8, q4):
        print(f"  📦 {f.name}: {f.stat().st_size/1e9:.2f} GB")
    assert q4.stat().st_size > 8e9, f"Q4 GGUF only {q4.stat().st_size} bytes — refusing partial export"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()
    sanity()
    build_combined()
    validate()
    if not args.merge_only:
        export_gguf()
    print("✅ R33 combine done — merged fp16 at", MERGE_OUT)


if __name__ == "__main__":
    main()
