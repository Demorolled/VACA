#!/usr/bin/env python3
"""
build-r37-merged.py — unified merge: R33 base + R34b + R35 + R36 adapters
=========================================================================
All three adapters were trained on the SAME base:
  /home/llmlab/Desktop/visual-ai-architect/training/cloud/out/round33/merged

So they compose additively (peft weighted sum of deltas, one merge pass):

  unified = R33_merged + ΔR34b(gen) + ΔR35(comprehension v1) + ΔR36(comprehension v2)

The result is a single clean fp16 checkpoint that carries the R34b entry-point
generation skill AND both comprehension breadths — deployable as one model.

Usage (ON THE AGENT, venv python):
  /home/llmlab/vaca-train-venv/bin/python scripts/build-r37-merged.py \
      /home/llmlab/vaca-r36/output/round36/checkpoint-300
"""
import gc
import json
import sys
from pathlib import Path

ROOT = Path("/home/llmlab/Desktop/visual-ai-architect")
BASE = ROOT / "training/cloud/out/round33/merged"
MERGE_OUT = ROOT / "training/cloud/out/unified/merged"
ADAPTERS = [
    ("r34b", Path("/home/llmlab/vaca-r34/output/round34b/final")),
    ("r35", Path("/home/llmlab/vaca-r35/output/round35/checkpoint-400")),
    ("r36", None),  # filled from argv
]
ALPHA, R = 16, 8


def sanity(r36_path: Path) -> None:
    for name, path in ADAPTERS:
        if path is None:
            path = r36_path
        if not (path / "adapter_model.safetensors").exists():
            print(f"❌ no adapter at {path}")
            sys.exit(1)
        c = json.load(open(path / "adapter_config.json"))
        assert c["lora_alpha"] == ALPHA and c["r"] == R, (name, c)
        base = Path(c["base_model_name_or_path"])
        assert base == BASE, f"{name} base {base} != {BASE}"
        print(f"✅ {name}: r={c['r']} alpha={c['lora_alpha']} on {base}")
    if not (BASE / "config.json").exists():
        print(f"❌ base not found: {BASE}")
        sys.exit(1)
    print(f"✅ base {BASE}")


def build_merged(r36_path: Path) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print("⬇️  Loading base fp16 on CPU (~29GB RAM)...")
    model = AutoModelForCausalLM.from_pretrained(
        str(BASE), torch_dtype=torch.float16, device_map=None,
        low_cpu_mem_usage=True, trust_remote_code=True,
    )
    tok = AutoTokenizer.from_pretrained(str(BASE), trust_remote_code=True)

    first = True
    for name, path in ADAPTERS:
        if path is None:
            path = r36_path
        print(f"  attaching {name} ({path.name})...")
        if first:
            model = PeftModel.from_pretrained(model, str(path), adapter_name=name)
            first = False
        else:
            model.load_adapter(str(path), adapter_name=name)

    names = [n for n, _ in ADAPTERS]
    print(f"  merging {names} in one pass (14B fp16 CPU, ~15-25 min)...")
    model = model.merge_and_unload(adapter_names=names)
    print("  ✅ merge complete")

    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving fp16 safetensors -> {MERGE_OUT.name}/")
    model.save_pretrained(str(MERGE_OUT), safe_serialization=True)
    tok.save_pretrained(str(MERGE_OUT))
    del model, tok
    gc.collect()
    print("✅ unified fp16 + tokenizer saved")


def validate() -> None:
    from safetensors import safe_open
    st_files = sorted(MERGE_OUT.glob("*.safetensors"))
    assert st_files, f"no safetensors written to {MERGE_OUT}"
    total = sum(f.stat().st_size for f in st_files)
    assert total > 20e9, f"merged size {total/1e9:.1f}GB — too small for fp16 14B"
    for f in st_files:
        with safe_open(str(f), framework="pt") as sf:
            bad = [k for k in sf.keys() if ".absmax" in k or "quant_state" in k]
            assert not bad, f"{f.name} still quantized: {bad[:3]}"
    cfg = json.load(open(MERGE_OUT / "config.json"))
    assert "quantization_config" not in cfg, "config still has quantization_config!"
    print(f"✅ real 16-bit checkpoint ({total/1e9:.1f}GB, no quantized tensors)")


def main() -> None:
    r36 = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not r36:
        print("usage: build-r37-merged.py <r36-adapter-dir>")
        sys.exit(1)
    sanity(r36)
    build_merged(r36)
    validate()
    print("\n✅ UNIFIED model built — merged fp16 at", MERGE_OUT)


if __name__ == "__main__":
    main()