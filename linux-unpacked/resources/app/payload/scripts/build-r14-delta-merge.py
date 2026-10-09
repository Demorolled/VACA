#!/usr/bin/env python3
"""
Build the REAL round-14 merged model locally (no Kaggle re-run).

The round-14 kernel trains correctly (90 rows, 3 epochs, accum 4 = ~60
optimizer steps) and its save-bug fix will hold (adapter_round14 differs from
R13's). BUT its merged export (out/model.safetensors) is still NF4-quantized
(merge_and_unload on the 4-bit QLoRA leaves absmax/quant_state tensors), so
convert_hf_to_gguf refuses it.

Recovery — exact algebra, reusing the REAL R13 fp16 merged shards (which were
themselves validated as merged_R12 + R13 LoRA to bf16 precision):
    merged_R14 = merged_R13 + (B14@A14 - B13@A13) * (alpha/r)

All adapters are r=8 / alpha=16 / rslora=False on the same base
(Orion-zhen/Qwen2.5-7B-Instruct-Uncensored), so the LoRA delta chain adds
directly.

The round14/merged dir is built fresh: copy the R13 fp16 shards + index, then
patch each shard IN PLACE at its existing data offsets.

Steps: 0) sanity: R13 merged == merged_R12 + R13_BA*scale (guards the chain)
       1) copy round13/merged shards + index -> round14/merged (drop the
          quantized single-shard model.safetensors)
       2) patch round14/merged shards with (B14@A14 - B13@A13) * scale
       3) validate: patched == merged_R13 + R14_BA*scale
"""
import gc
import json
import shutil
import struct
from pathlib import Path

import torch

ROOT = Path("/home/final-flash1/Desktop/visual-ai-architect")
MERGED_R13 = ROOT / "training/cloud/out/round13/merged"
MERGE_OUT = ROOT / "training/cloud/out/round14/merged"
ADAPTER_R13 = ROOT / "training/cloud/out/round13/adapter/adapter_model.safetensors"
ADAPTER_R14 = ROOT / "training/cloud/out/round14/adapter/adapter_model.safetensors"

ALPHA, R = 16, 8
SCALE = ALPHA / R

SAMPLE_MODULES = [
    "model.layers.0.self_attn.q_proj.weight",
    "model.layers.5.mlp.gate_proj.weight",
    "model.layers.20.self_attn.v_proj.weight",
]


def load_sf(path: Path) -> dict:
    from safetensors.torch import load_file
    return load_file(str(path))


def weight_map(base_dir: Path, key: str) -> str:
    idx = json.load(open(base_dir / "model.safetensors.index.json"))
    return idx["weight_map"][key]


def get_tensor_f32(sf_dir: Path, key: str) -> torch.Tensor:
    from safetensors import safe_open
    shard = weight_map(sf_dir, key)
    with safe_open(sf_dir / shard, framework="pt") as f:
        return f.get_tensor(key).float()


def lora_delta(ad: dict, module_key: str) -> torch.Tensor:
    core = module_key[: -len(".weight")]
    A = ad[f"base_model.model.{core}.lora_A.weight"].float()
    B = ad[f"base_model.model.{core}.lora_B.weight"].float()
    return (B @ A) * SCALE  # (out, in)


def validate(merged_dir: Path, adapter: dict, base_dir: Path, label: str) -> float:
    maxerr = 0.0
    for mk in SAMPLE_MODULES:
        base = get_tensor_f32(base_dir, mk)
        merged = get_tensor_f32(merged_dir, mk)
        exp = base + lora_delta(adapter, mk)
        err = (exp - merged).abs().max().item()
        maxerr = max(maxerr, err)
        print(f"   {mk}: max|(base + BA*{SCALE}) - merged| = {err:.6f}")
    print(f"   [{label}] max error over samples = {maxerr:.6f}")
    return maxerr


def patch_merged_shard(shard_name: str, r13: dict, r14: dict) -> int:
    path = MERGE_OUT / shard_name
    with open(path, "rb") as f:
        hlen = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(hlen))
    data_off = 8 + hlen
    patched = 0
    tensor_entries = {k: v for k, v in header.items() if k != "metadata"}
    for mk, info in tensor_entries.items():
        if not mk.endswith(".weight"):
            continue
        core = mk[: -len(".weight")]
        akey = f"base_model.model.{core}.lora_A.weight"
        if akey not in r14 or f"base_model.model.{core}.lora_B.weight" not in r14:
            continue
        assert info["dtype"] == "BF16", f"{mk} dtype {info['dtype']} unexpected"
        shape = info["shape"]
        start, end = info["data_offsets"]
        nbytes = end - start
        with open(path, "r+b") as f:
            f.seek(data_off + start)
            old = (
                torch.frombuffer(f.read(nbytes), dtype=torch.bfloat16)
                .view(shape)
                .float()
            )
            new = (old + lora_delta(r14, mk) - lora_delta(r13, mk)).to(
                torch.bfloat16
            ).contiguous()
            f.seek(data_off + start)
            f.write(new.view(torch.int16).numpy().tobytes())
        patched += 1
        del old, new
    gc.collect()
    return patched


def main() -> None:
    assert ADAPTER_R13.exists(), f"R13 adapter missing: {ADAPTER_R13}"
    assert ADAPTER_R14.exists(), f"R14 adapter missing: {ADAPTER_R14} — download first"
    assert (MERGED_R13 / "model.safetensors.index.json").exists(), "R13 merged missing — deploy R13 first"

    r13 = load_sf(ADAPTER_R13)
    r14 = load_sf(ADAPTER_R14)
    assert set(r13) == set(r14), "R13/R14 adapter key sets differ!"
    assert len(r14) == 392, f"expected 392 LoRA tensors, got {len(r14)}"

    c13 = json.load(open(ROOT / "training/cloud/out/round13/adapter/adapter_config.json"))
    c14 = json.load(open(ROOT / "training/cloud/out/round14/adapter/adapter_config.json"))
    for c in (c13, c14):
        assert c["lora_alpha"] == 16 and c["r"] == 8 and not c.get("use_rslora"), c
    print(f"✅ both adapters r={R} alpha={ALPHA} rslora=False -> scale={SCALE}")

    # 0) sanity: R13 merged must equal merged_R12 + R13 LoRA (it was built that way)
    err_r13 = validate(MERGED_R13, r13, ROOT / "training/cloud/out/round12/merged", "R13 merged (merged_R12 + R13 LoRA)")
    assert err_r13 < 5e-3, f"R13 merged validation failed: {err_r13}"

    # 1) build round14/merged from the real R13 fp16 shards
    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    for f in MERGE_OUT.glob("*"):
        if f.is_file() and f.name != "model.safetensors.index.json":
            f.unlink()  # drop the quantized single-shard download
    index = json.load(open(MERGED_R13 / "model.safetensors.index.json"))
    shards = sorted(set(index["weight_map"].values()))
    for shard in shards:
        shutil.copy2(MERGED_R13 / shard, MERGE_OUT / shard)
    shutil.copy2(MERGED_R13 / "model.safetensors.index.json", MERGE_OUT / "model.safetensors.index.json")
    # config files come from R13's merged (same base model) — the merge cleanup
    # wipes them, so copy BEFORE patching and never delete them.
    for f in ("config.json", "generation_config.json", "tokenizer.json",
              "tokenizer_config.json", "chat_template.jinja", "README.md"):
        src = MERGED_R13 / f
        if src.exists() and not (MERGE_OUT / f).exists():
            shutil.copy2(src, MERGE_OUT / f)
    print(f"✅ copied {len(shards)} R13 fp16 shards + index + config -> round14/merged")

    # 2) patch with (B14@A14 - B13@A13) * scale
    total = 0
    for shard in shards:
        n = patch_merged_shard(shard, r13, r14)
        total += n
        print(f"   patched {shard}: {n} modules")
    print(f"✅ patched {total} LoRA module weights across {len(shards)} shards")

    # 3) validate the result = merged_R13 + R14 LoRA delta
    err_after = validate(MERGE_OUT, r14, MERGED_R13, "after patch (R14 math)")
    assert err_after < 5e-3, f"post-validation failed: {err_after}"
    print("\n✅ R14 merged model built and validated: merged_R13 + R14 trained LoRA")
    print("   Next: bash scripts/deploy-round14.sh (convert -> q4_k_m -> dspark)")


if __name__ == "__main__":
    main()
