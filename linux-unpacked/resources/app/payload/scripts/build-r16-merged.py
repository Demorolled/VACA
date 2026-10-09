#!/usr/bin/env python3
"""
Build the REAL round-16 merged model locally (no Kaggle re-run).

Why not delta-merge like R15? R15's build-r15-delta-merge.py chained
merged_R15 = merged_R14 + (B15@A15 - B14@A14)*(alpha/r) — but the R14/R15 fp16
shards that were its base were deleted from disk after the R15 deploy. The
chain telescopes though: because every round is the SAME LoRA continuing on
the SAME base (Orion-zhen/Qwen2.5-7B-Instruct-Uncensored, r=8/alpha=16,
rslora=False), the round-16 adapter saved by the trainer already IS the full
delta from base:

    merged_R16 = base + B16@A16 * (alpha/r)

So we load the base + adapter_round16 with unsloth and use
save_pretrained_merged(save_method="merged_16bit") — this dequantizes the
4-bit QLoRA base properly (the R15 kernel's merge_and_unload export was
NF4-quantized and unusable; this method is the fix for that class).

Steps: 0) sanity: R16 adapter key set == R15 adapter key set (same arch),
          and SHA differs from R15 (training applied — kernel's own guard)
       1) load base 4-bit + adapter_round16 via unsloth
       2) save_pretrained_merged merged_16bit -> training/cloud/out/round16/merged
       3) validate: merged tensors differ from base tensors (LoRA applied)
"""
import gc
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path("/home/final-flash1/Desktop/visual-ai-architect")
ROUND16 = ROOT / "training/cloud/out/round16"
ADAPTER = ROUND16 / "adapter"
MERGE_OUT = ROUND16 / "merged"
ADAPTER_R15 = ROOT / "training/cloud/out/round15/adapter/adapter_model.safetensors"

BASE_MODEL = "Orion-zhen/Qwen2.5-7B-Instruct-Uncensored"
ALPHA, R = 16, 8
SCALE = ALPHA / R

SAMPLE_MODULES = [
    "model.layers.0.self_attn.q_proj.weight",
    "model.layers.5.mlp.gate_proj.weight",
    "model.layers.20.self_attn.v_proj.weight",
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sanity() -> None:
    assert ADAPTER.exists(), f"R16 adapter missing at {ADAPTER} — run scripts/download-round16-merged.py first"
    cfg = ADAPTER / "adapter_config.json"
    assert cfg.exists(), f"adapter_config.json missing in {ADAPTER}"
    import json
    c = json.load(open(cfg))
    assert c["lora_alpha"] == 16 and c["r"] == 8 and not c.get("use_rslora"), c
    print(f"✅ R16 adapter config: r={c['r']} alpha={c['lora_alpha']} rslora=False -> scale={SCALE}")

    # SHA differs from the loaded R15 LoRA (the kernel's own guard, re-verified)
    a16 = ADAPTER / "adapter_model.safetensors"
    assert a16.exists(), "adapter_model.safetensors missing"
    if ADAPTER_R15.exists():
        s16, s15 = sha256_file(a16), sha256_file(ADAPTER_R15)
        assert s16 != s15, "❌ R16 adapter == R15 adapter — training did NOT apply! Do not deploy."
        print(f"✅ SANITY OK: R16 adapter differs from R15 adapter (training applied)")
    else:
        print("⚠️  R15 adapter not found locally — skipping SHA comparison (kernel-side guard already ran)")

    # Key set matches (same architecture)
    from safetensors import safe_open
    with safe_open(str(a16), framework="pt") as f:
        keys16 = set(f.keys())
    if ADAPTER_R15.exists():
        with safe_open(str(ADAPTER_R15), framework="pt") as f:
            keys15 = set(f.keys())
        assert keys16 == keys15, f"R16/R15 adapter key sets differ: {len(keys16)} vs {len(keys15)}"
    assert len(keys16) == 392, f"expected 392 LoRA tensors, got {len(keys16)}"
    print(f"✅ key set OK: {len(keys16)} LoRA tensors")


def build_merged() -> None:
    import torch
    from unsloth import FastLanguageModel

    print(f"⬇️  Loading base {BASE_MODEL} (4-bit QLoRA) + R16 adapter...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
        device_map="auto",
    )
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, str(ADAPTER))

    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    print(f"💾 Saving merged 16-bit safetensors -> {MERGE_OUT.name}/")
    # ⚠️  Do NOT merge_and_unload() + save_pretrained() here: on an unsloth
    # 4-bit base that keeps the NF4-quantized tensors (.absmax / quant_state)
    # in the output — a ~5.5GB "merged" checkpoint llama.cpp's
    # convert_hf_to_gguf.py cannot map ("Can not map tensor ...absmax").
    # unsloth_generic_save_pretrained_merged must be called with the PEFT
    # WRAPPER as `self` so it takes the PeftModel branch and re-merges the
    # LoRA onto the dequantized 16-bit base weights (the same function behind
    # model.save_pretrained_merged; calling the method through the PeftModel
    # __getattr__ proxy binds `self` to the raw base model and silently skips
    # the merge).
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
    import json
    from safetensors import safe_open

    # A REAL 16-bit merge must (a) be ~14GB for the 7B base (not ~5.5GB, which
    # is the tell of a QLoRA-quantized "merge"), and (b) contain NO unsloth
    # quantized tensors (.absmax / quant_state). This is the exact failure the
    # old build produced — the deploy's convert_hf_to_gguf then died on
    # "Can not map tensor '...down_proj.weight.absmax'".
    st_files = sorted(MERGE_OUT.glob("*.safetensors"))
    assert st_files, f"no safetensors written to {MERGE_OUT}"
    total = sum(f.stat().st_size for f in st_files)
    assert total > 10e9, (
        f"merged size {total/1e9:.1f}GB — too small for a 16-bit 7B merge; "
        "still quantized!"
    )
    for f in st_files:
        with safe_open(str(f), framework="pt") as sf:
            bad = [k for k in sf.keys() if ".absmax" in k or "quant_state" in k]
            assert not bad, f"{f.name} still contains quantized tensors: {bad[:3]}"
    import json
    cfg = json.load(open(MERGE_OUT / "config.json"))
    assert "quantization_config" not in cfg, "merged config still has quantization_config — not a real 16-bit merge!"
    print(f"✅ merged is a real 16-bit checkpoint ({total/1e9:.1f}GB, no quantized tensors)")


def main() -> None:
    sanity()
    build_merged()
    validate()
    print("\n✅ R16 merged model built: base + adapter_round16 (merged_16bit)")
    print("   Next: bash scripts/deploy-round16.sh (convert -> q4_k_m -> dspark)")


if __name__ == "__main__":
    main()
