#!/usr/bin/env python3
"""
Build the REAL round-15 merged model locally (no Kaggle re-run).

The round-15 kernel trains correctly (GUI+3D rows, 3 epochs, accum 4) and its
save-bug fix holds (adapter_round15 differs from R14's). BUT its merged export
(out/model.safetensors) is still NF4-quantized (merge_and_unload on the 4-bit
QLoRA leaves absmax/quant_state tensors), so convert_hf_to_gguf refuses it.

Recovery — exact algebra, reusing the REAL R14 fp16 merged shards (which were
themselves validated as merged_R13 + R14 LoRA to bf16 precision):
    merged_R15 = merged_R14 + (B15@A15 - B14@A14) * (alpha/r)

All adapters are r=8 / alpha=16 / rslora=False on the same base
(Orion-zhen/Qwen2.5-7B-Instruct-Uncensored), so the LoRA delta chain adds
directly.

Steps: 0) sanity: R14 merged == merged_R13 + R14_BA*scale (guards the chain)
       1) copy round14/merged shards + index -> round15/merged (drop the
          quantized single-shard model.safetensors)
       2) patch round15/merged shards with (B15@A15 - B14@A14) * scale
       3) validate: patched == merged_R14 + R15_BA*scale
"""
import gc
import json
import shutil
import struct
from pathlib import Path

import torch

ROOT = Path("/home/final-flash1/Desktop/visual-ai-architect")
MERGED_R14 = ROOT / "training/cloud/out/round14/merged"
MERGE_OUT = ROOT / "training/cloud/out/round15/merged"
ADAPTER_R14 = ROOT / "training/cloud/out/round14/adapter/adapter_model.safetensors"
ADAPTER_R15 = ROOT / "training/cloud/out/round15/adapter/adapter_model.safetensors"

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


def patch_merged_shard(shard_name: str, r14: dict, r15: dict) -> int:
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
        if akey not in r15 or f"base_model.model.{core}.lora_B.weight" not in r15:
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
            new = (old + lora_delta(r15, mk) - lora_delta(r14, mk)).to(
                torch.bfloat16
            ).contiguous()
            f.seek(data_off + start)
            f.write(new.view(torch.int16).numpy().tobytes())
        patched += 1
        del old, new
    gc.collect()
    return patched


def main() -> None:
    assert ADAPTER_R14.exists(), f"R14 adapter missing: {ADAPTER_R14}"
    assert ADAPTER_R15.exists(), f"R15 adapter missing: {ADAPTER_R15} — download first"
    assert (MERGED_R14 / "model.safetensors.index.json").exists(), "R14 merged missing — deploy R14 first"

    r14 = load_sf(ADAPTER_R14)
    r15 = load_sf(ADAPTER_R15)
    assert set(r14) == set(r15), "R14/R15 adapter key sets differ!"
    assert len(r15) == 392, f"expected 392 LoRA tensors, got {len(r15)}"

    c14 = json.load(open(ROOT / "training/cloud/out/round14/adapter/adapter_config.json"))
    c15 = json.load(open(ROOT / "training/cloud/out/round15/adapter/adapter_config.json"))
    for c in (c14, c15):
        assert c["lora_alpha"] == 16 and c["r"] == 8 and not c.get("use_rslora"), c
    print(f"✅ both adapters r={R} alpha={ALPHA} rslora=False -> scale={SCALE}")

    # 0) sanity: R14 merged must equal merged_R13 + R14 LoRA (it was built that way)
    err_r14 = validate(MERGED_R14, r14, ROOT / "training/cloud/out/round13/merged", "R14 merged (merged_R13 + R14 LoRA)")
    assert err_r14 < 5e-3, f"R14 merged validation failed: {err_r14}"

    # 1) build round15/merged from the real R14 fp16 shards
    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    for f in MERGE_OUT.glob("*"):
        if f.is_file() and f.name != "model.safetensors.index.json":
            f.unlink()  # drop the quantized single-shard download
    index = json.load(open(MERGED_R14 / "model.safetensors.index.json"))
    shards = sorted(set(index["weight_map"].values()))
    for shard in shards:
        shutil.copy2(MERGED_R14 / shard, MERGE_OUT / shard)
    shutil.copy2(MERGED_R14 / "model.safetensors.index.json", MERGE_OUT / "model.safetensors.index.json")
    for f in ("config.json", "generation_config.json", "tokenizer.json",
              "tokenizer_config.json", "chat_template.jinja", "README.md"):
        src = MERGED_R14 / f
        if src.exists() and not (MERGE_OUT / f).exists():
            shutil.copy2(src, MERGE_OUT / f)
    print(f"✅ copied {len(shards)} R14 fp16 shards + index + config -> round15/merged")

    # 2) patch with (B15@A15 - B14@A14) * scale
    total = 0
    for shard in shards:
        n = patch_merged_shard(shard, r14, r15)
        total += n
        print(f"   patched {shard}: {n} modules")
    print(f"✅ patched {total} LoRA module weights across {len(shards)} shards")

    # 3) validate the result = merged_R14 + R15 LoRA delta
    err_after = validate(MERGE_OUT, r15, MERGED_R14, "after patch (R15 math)")
    assert err_after < 5e-3, f"post-validation failed: {err_after}"
    print("\n✅ R15 merged model built and validated: merged_R14 + R15 trained LoRA")
    print("   Next: bash scripts/deploy-round15.sh (convert -> q4_k_m -> dspark)")


if __name__ == "__main__":
    main()
