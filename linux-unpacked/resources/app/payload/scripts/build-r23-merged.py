#!/usr/bin/env python3
"""
build-r23-merged.py — merge the round-23 LoRA into the fresh 14B base (agent).

Straight clone of the PROVEN R21/R22 pattern (build-r21-merged.py): the R23
adapter is a LoRA on the FRESH base (BlossomsAI/Qwen2.5-Coder-14B-Instruct-
Uncensored, r=8/alpha=16), so

    merged_R23 = base + B23@A23 * (alpha/r)

  1. Explicit max_memory for ALL THREE RTX 3060s (device_map="auto" alone
     shoves modules to CPU/disk, which bitsandbytes 4-bit refuses).
  2. unsloth_generic_save_pretrained_merged(save_method="merged_16bit"),
     NOT merge_and_unload() + save_pretrained() — the latter keeps NF4
     quantized tensors in the output AND materializes the whole fp16 model
     in VRAM (28GB for a 14B) -> OOM.

After:  convert + quantize with the llama.cpp toolchain
        (~/.unsloth/llama.cpp/convert_hf_to_gguf.py + llama-quantize).

Usage (ON THE AGENT, after R23 training finishes):
  llm-training-app/.venv/bin/python scripts/build-r23-merged.py
"""
import gc
import hashlib
import sys
from pathlib import Path

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
ROUND23 = ROOT / "training/cloud/out/round23"
ADAPTER = ROUND23 / "final"          # trainer.save_model() target
MERGE_OUT = ROUND23 / "merged"

BASE_MODEL = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
ALPHA, R = 16, 8
SCALE = ALPHA / R

MAX_SEQ = 3072
MAX_MEMORY = {0: "11GB", 1: "11GB", 2: "11GB"}  # all three RTX 3060 12GB


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sanity() -> None:
    if not (ADAPTER / "adapter_model.safetensors").exists():
        print(f"❌ No round-23 adapter — run the R23 training round first")
        sys.exit(1)
    import json
    c = json.load(open(ADAPTER / "adapter_config.json"))
    assert c["lora_alpha"] == 16 and c["r"] == 8, c
    assert c["base_model_name_or_path"] == BASE_MODEL, c["base_model_name_or_path"]
    print(f"✅ R23 adapter: r={c['r']} alpha={c['lora_alpha']} scale={SCALE} on {BASE_MODEL}")


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

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Trainable after attach: {trainable:,}")

    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving merged 16-bit safetensors -> {MERGE_OUT.name}/")
    # PROVEN R16-R22 path: merged_16bit via the unsloth PEFT-aware save.
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
    gc.collect()
    torch.cuda.empty_cache()


def validate() -> None:
    from safetensors import safe_open

    st_files = sorted(MERGE_OUT.glob("*.safetensors"))
    assert st_files, f"no safetensors written to {MERGE_OUT}"
    total = sum(f.stat().st_size for f in st_files)
    # 14B fp16 ≈ 28GB. If it's ~9GB (the 4-bit size) the merge stayed quantized.
    assert total > 20e9, (
        f"merged size {total/1e9:.1f}GB — too small for a 16-bit 14B merge; "
        "still quantized!"
    )
    for f in st_files:
        with safe_open(str(f), framework="pt") as sf:
            bad = [k for k in sf.keys() if ".absmax" in k or "quant_state" in k]
            assert not bad, f"{f.name} still contains quantized tensors: {bad[:3]}"
    import json
    cfg = json.load(open(MERGE_OUT / "config.json"))
    assert "quantization_config" not in cfg, "merged config still has quantization_config!"
    print(f"✅ merged is a real 16-bit checkpoint ({total/1e9:.1f}GB, no quantized tensors)")


def main() -> None:
    sanity()
    build_merged()
    validate()
    print(f"\n✅ R23 merge complete → {MERGE_OUT}")
    print("   Next: convert + quantize:\n"
          "   python3 ~/.unsloth/llama.cpp/convert_hf_to_gguf.py "
          f"{MERGE_OUT} --outfile {ROUND23 / 'gguf' / 'vaca-r23.Q8_0.gguf'} --outtype q8_0\n"
          f"   ~/.unsloth/llama.cpp/llama-quantize "
          f"{ROUND23 / 'gguf' / 'vaca-r23.Q8_0.gguf'} "
          f"{ROUND23 / 'gguf' / 'vaca-r23.Q4_K_M.gguf'} q4_k_m --allow-requantize")


if __name__ == "__main__":
    main()
