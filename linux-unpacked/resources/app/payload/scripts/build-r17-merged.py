#!/usr/bin/env python3
"""
Build the REAL round-17 merged model locally (no Kaggle re-run).

Same telescoping property as R16: the round-17 adapter is a LoRA on the FRESH
base (BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored, r=8/alpha=16), so

    merged_R17 = base + B17@A17 * (alpha/r)

This follows the PROVEN R16 pattern (build-r16-merged.py) — two deviations
from the earlier R17 draft fixed here:

  1. Explicit max_memory for BOTH RTX 3060s. device_map="auto" alone on a 14B
     shoves modules to CPU/disk, which bitsandbytes 4-bit refuses
     ("Some modules are dispatched on the CPU or the disk"). A 14B 4-bit base
     needs ~9GB — fits easily across 2×12GB once the GPUs are free.
  2. unsloth_generic_save_pretrained_merged(save_method="merged_16bit"),
     NOT merge_and_unload() + save_pretrained(). The latter keeps the NF4
     quantized tensors (.absmax / quant_state) in the output AND materializes
     the whole fp16 model in VRAM (28GB for a 14B) → OOM. The unsloth merged
     save re-merges onto dequantized 16-bit weights shard-by-shard.

After:  bash scripts/deploy-round17.sh (convert -> q8_0 GGUF -> dspark)

Usage:
  python3 scripts/build-r17-merged.py
"""
import gc
import hashlib
import sys
from pathlib import Path

ROOT = Path("/home/final-flash1/Desktop/visual-ai-architect")
ROUND17 = ROOT / "training/cloud/out/round17"
ADAPTER = ROUND17 / "adapter"
MERGE_OUT = ROUND17 / "merged"

BASE_MODEL = "BlossomsAI/Qwen2.5-Coder-14B-Instruct-Uncensored"
ALPHA, R = 16, 8
SCALE = ALPHA / R

MAX_SEQ = 3072
MAX_MEMORY = {0: "11GB", 1: "11GB"}   # both RTX 3060 12GB — keep ~1GB headroom


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sanity() -> None:
    if not (ADAPTER / "adapter_model.safetensors").exists():
        print("❌ No round-17 adapter — run scripts/download-round17-merged.py first")
        sys.exit(1)
    import json
    c = json.load(open(ADAPTER / "adapter_config.json"))
    assert c["lora_alpha"] == 16 and c["r"] == 8, c
    assert c["base_model_name_or_path"] == BASE_MODEL, c["base_model_name_or_path"]
    print(f"✅ R17 adapter: r={c['r']} alpha={c['lora_alpha']} scale={SCALE} on {BASE_MODEL}")


def build_merged() -> None:
    import torch
    from unsloth import FastLanguageModel

    print(f"⬇️  Loading base {BASE_MODEL} (4-bit QLoRA, split across 2×3060)...")
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
    # PROVEN R16 path: merged_16bit via the unsloth PEFT-aware save. This
    # dequantizes the 4-bit base, applies the LoRA, and writes 16-bit shards
    # without materializing the full 28GB in VRAM at once.
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
    print("\n✅ R17 merged model built: base + adapter_round17 (merged_16bit)")
    print("   Next: bash scripts/deploy-round17.sh (convert -> q8_0 -> dspark)")


if __name__ == "__main__":
    main()
