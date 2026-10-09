#!/usr/bin/env python3
"""
build-r34-merged.py — merge the R34 correction adapter into a clean fp16 checkpoint
====================================================================================
R34 is a LoRA trained on TOP OF THE R33 MERGED MODEL (not the HF base) — the
correction round for R33's known weakness (entry-point src/main.ts that imports a
sibling module), deliberately preserving R33 knowledge:

    merged_R34 = R33_merged + B@A * (alpha/r)     (telescoping chain: base → R33 → R34)

The base is read from the adapter's own adapter_config.json
(base_model_name_or_path = .../out/round33/merged), so this script works even if
the chain shifts again.

Same proven CPU merge path as R33 (combine-r33-deltas.py): load base fp16 on CPU
(~29GB RAM; this box has 60GB), attach the adapter, merge_and_unload() -> clean
fp16 (no NF4/quantized tensors), save to out/round34/merged. GGUF convert + deploy
happen separately AFTER the eval passes (eval-r34-accuracy.py).

Usage (ON THE AGENT, venv python):
  /home/llmlab/vaca-train-venv/bin/python scripts/build-r34-merged.py
"""
import gc
import json
import sys
from pathlib import Path

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
ROUND34 = ROOT / "training/cloud/out/round34"
ADAPTER = Path("/home/llmlab/vaca-r34/output/round34/final")
MERGE_OUT = ROUND34 / "merged"
ALPHA, R = 16, 8


def sanity() -> Path:
    if not (ADAPTER / "adapter_model.safetensors").exists():
        print(f"❌ No R34 adapter at {ADAPTER} — training must have finished.")
        sys.exit(1)
    c = json.load(open(ADAPTER / "adapter_config.json"))
    assert c["lora_alpha"] == ALPHA and c["r"] == R, c
    base = Path(c["base_model_name_or_path"])
    if not (base / "config.json").exists():
        print(f"❌ Adapter base not found: {base}")
        sys.exit(1)
    print(f"✅ R34 adapter: r={c['r']} alpha={c['lora_alpha']} "
          f"(peft {c.get('peft_version')}) on {base}")
    return base


def build_merged(base: Path) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"⬇️  Loading base {base} fp16 on CPU (~29GB RAM)...")
    model = AutoModelForCausalLM.from_pretrained(
        str(base), torch_dtype=torch.float16, device_map=None,
        low_cpu_mem_usage=True, trust_remote_code=True,
    )
    tok = AutoTokenizer.from_pretrained(str(base), trust_remote_code=True)
    print("  Attaching R34 adapter...")
    model = PeftModel.from_pretrained(model, str(ADAPTER))
    print("  Merging on CPU (14B fp16, ~10-20 min)...")
    model = model.merge_and_unload()   # clean fp16, no NF4 tensors
    print("  ✅ Merge complete")
    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving fp16 safetensors -> {MERGE_OUT.name}/")
    model.save_pretrained(str(MERGE_OUT), safe_serialization=True)
    tok.save_pretrained(str(MERGE_OUT))
    del model, tok
    gc.collect()
    print("✅ R34 merged + tokenizer saved")


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


def main() -> None:
    base = sanity()
    build_merged(base)
    validate()
    print("\n✅ R34 merged model built — merged fp16 at", MERGE_OUT)
    print("   Next: eval-r34-accuracy.py <merged> --temperature 0.2 (target 95%)")


if __name__ == "__main__":
    main()