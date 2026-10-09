#!/usr/bin/env python3
"""
build-r38-merged.py — deploy merge: UNIFIED base + R38 adapter → fp16
=========================================================================
R38 was trained FROM the unified base (out/unified/merged = deployed
vaca-r36), so the deployable next model is a single PEFT merge:

    r38-merged = unified_merged + ΔR38(gen: purpose / gap / code)

Result: a clean fp16 checkpoint deployable as one model (vaca-r38),
following the same pattern as build-r37-merged.py.

Usage (ON THE AGENT, venv python):
  /home/llmlab/vaca-train-venv/bin/python scripts/build-r38-merged.py
"""
import json
import sys
from pathlib import Path

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
BASE = ROOT / "training/cloud/out/unified/merged"
MERGE_OUT = ROOT / "training/cloud/out/unified/r38-merged"
ADAPTER = Path("/home/llmlab/vaca-r38/output/round38/final")
ALPHA, R = 16, 8


def main() -> None:
    if (ADAPTER / "adapter_model.safetensors").exists():
        c = json.load(open(ADAPTER / "adapter_config.json"))
        assert c["lora_alpha"] == ALPHA and c["r"] == R, (c["lora_alpha"], c["r"])
        base = Path(c["base_model_name_or_path"])
        assert base == BASE, f"adapter base {base} != {BASE}"
        print(f"✅ adapter {ADAPTER.name}: r={c['r']} alpha={c['lora_alpha']} on {base}")
    else:
        print(f"❌ no adapter at {ADAPTER}")
        sys.exit(1)
    if not (BASE / "config.json").exists():
        print(f"❌ base not found: {BASE}")
        sys.exit(1)
    print(f"✅ base {BASE}")
    if MERGE_OUT.exists() and any(MERGE_OUT.iterdir()):
        print(f"❌ output already exists: {MERGE_OUT} — refusing to clobber")
        sys.exit(1)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print("⬇️  Loading base fp16 on CPU (~29GB RAM)...")
    model = AutoModelForCausalLM.from_pretrained(
        str(BASE), torch_dtype=torch.float16, device_map=None,
        low_cpu_mem_usage=True, trust_remote_code=True,
    )
    tok = AutoTokenizer.from_pretrained(str(BASE), trust_remote_code=True)

    print(f"  attaching r38 ({ADAPTER.name})...")
    model = PeftModel.from_pretrained(model, str(ADAPTER))
    print("  merging 14B fp16 on CPU (~15-25 min)...")
    model = model.merge_and_unload()
    print("  ✅ merge complete — saving fp16...")
    model.save_pretrained(str(MERGE_OUT))
    try:
        tok.save_pretrained(str(MERGE_OUT))
    except Exception as e:
        print(f"  ⚠ tokenizer save: {e}")
    size = sum(f.stat().st_size for f in MERGE_OUT.rglob("*") if f.is_file())
    print(f"✅ r38-merged saved to {MERGE_OUT} ({size / 1e9:.1f} GB)")


if __name__ == "__main__":
    main()
