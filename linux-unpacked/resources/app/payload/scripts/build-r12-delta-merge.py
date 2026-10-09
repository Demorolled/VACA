#!/usr/bin/env python3
"""
Build the REAL round-12 merged model locally (no Kaggle re-run).

The round-12 kernel trained correctly (74 rows, 3 epochs, accum 4 = 51
optimizer steps) and its save-bug fix worked: the round adapter
(out/adapter_round12/, sha b8df227c...) is genuinely different from R11's
(e3b7e7cc...). BUT its merged export (out/model.safetensors) is still
NF4-quantized (merge_and_unload on the 4-bit QLoRA left absmax/quant_state
tensors), so convert_hf_to_gguf refuses it.

Recovery — exact algebra, reusing the REAL R11 fp16 merged shards:
    merged_R12 = merged_R11 + (B12@A12 - B11@A11) * (alpha/r)

Both R11 and R12 LoRAs are r=8 / alpha=16 / rslora=False on the same base
(Orion-zhen/Qwen2.5-7B-Instruct-Uncensored), so the LoRA delta can be added
directly onto the R11-merged weights.

The round12/merged dir is built fresh: copy the real R11 fp16 shards + index,
then patch each shard IN PLACE at its existing data offsets (same dtype/shape
-> identical file layout, low RAM).

Steps: 0) sanity: R11 merged == base + R11_BA*scale (guards the base)
       1) copy round11/merged shards + index -> round12/merged (drop the
          quantized single-shard model.safetensors)
       2) patch round12/merged shards with (B12@A12 - B11@A11) * scale
       3) validate: patched == base + R12_BA*scale
"""
import gc
import json
import shutil
import struct
from pathlib import Path

import torch

ROOT = Path("/home/final-flash1/Desktop/visual-ai-architect")
BASE_SNAP = next(
    Path.home().joinpath(
        ".cache/huggingface/hub/models--Orion-zhen--Qwen2.5-7B-Instruct-Uncensored/snapshots"
    ).glob("*")
)
MERGED_R11 = ROOT / "training/cloud/out/round11/merged"
MERGE_OUT = ROOT / "training/cloud/out/round12/merged"
ADAPTER_R11 = ROOT / "training/cloud/out/round11/adapter_trained/adapter_model.safetensors"
ADAPTER_R12 = ROOT / "training/cloud/out/round12/adapter/adapter_model.safetensors"

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


def validate(merged_dir: Path, adapter: dict, label: str) -> float:
    maxerr = 0.0
    for mk in SAMPLE_MODULES:
        base = get_tensor_f32(BASE_SNAP, mk)
        merged = get_tensor_f32(merged_dir, mk)
        exp = base + lora_delta(adapter, mk)
        err = (exp - merged).abs().max().item()
        maxerr = max(maxerr, err)
        print(f"   {mk}: max|(base + BA*{SCALE}) - merged| = {err:.6f}")
    print(f"   [{label}] max error over samples = {maxerr:.6f}")
    return maxerr


def patch_merged_shard(shard_name: str, r11: dict, r12: dict) -> int:
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
        if akey not in r12 or f"base_model.model.{core}.lora_B.weight" not in r12:
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
            new = (old + lora_delta(r12, mk) - lora_delta(r11, mk)).to(
                torch.bfloat16
            ).contiguous()
            f.seek(data_off + start)
            f.write(new.view(torch.int16).numpy().tobytes())
        patched += 1
        del old, new
    gc.collect()
    return patched


def main() -> None:
    assert ADAPTER_R11.exists(), f"R11 adapter missing: {ADAPTER_R11}"
    assert ADAPTER_R12.exists(), f"R12 adapter missing: {ADAPTER_R12}"
    assert (MERGED_R11 / "model.safetensors.index.json").exists(), "R11 merged missing"

    r11 = load_sf(ADAPTER_R11)
    r12 = load_sf(ADAPTER_R12)
    assert set(r11) == set(r12), "R11/R12 adapter key sets differ!"
    assert len(r12) == 392, f"expected 392 LoRA tensors, got {len(r12)}"

    c11 = json.load(open(ROOT / "training/cloud/out/round11/adapter_trained/adapter_config.json"))
    c12 = json.load(open(ROOT / "training/cloud/out/round12/adapter/adapter_config.json"))
    for c in (c11, c12):
        assert c["lora_alpha"] == 16 and c["r"] == 8 and not c.get("use_rslora"), c
    print(f"✅ both adapters r={R} alpha={ALPHA} rslora=False -> scale={SCALE}")
    print(f"   R11 trained: e3b7e7cc… (expect) | R12 trained: b8df227c… (expect)")

    # 0) sanity: R11 merged must equal base + R11 LoRA (it was built that way)
    err_r11 = validate(MERGED_R11, r11, "R11 merged (base + R11 LoRA)")
    assert err_r11 < 5e-3, f"R11 merged validation failed: {err_r11}"

    # 1) build round12/merged from the real R11 fp16 shards
    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    for f in MERGE_OUT.glob("*"):
        if f.is_file() and f.name != "model.safetensors.index.json":
            f.unlink()  # drop the quantized single-shard download
    index = json.load(open(MERGED_R11 / "model.safetensors.index.json"))
    shards = sorted(set(index["weight_map"].values()))
    for shard in shards:
        shutil.copy2(MERGED_R11 / shard, MERGE_OUT / shard)
    shutil.copy2(MERGED_R11 / "model.safetensors.index.json", MERGE_OUT / "model.safetensors.index.json")
    print(f"✅ copied {len(shards)} R11 fp16 shards + index -> round12/merged (quantized model.safetensors dropped)")

    # 2) patch with (B12@A12 - B11@A11) * scale
    total = 0
    for shard in shards:
        n = patch_merged_shard(shard, r11, r12)
        total += n
        print(f"   patched {shard}: {n} modules")
    print(f"✅ patched {total} LoRA module weights across {len(shards)} shards")

    # 3) validate the result = base + R12 LoRA
    err_after = validate(MERGE_OUT, r12, "after patch (R12 math)")
    assert err_after < 5e-3, f"post-validation failed: {err_after}"
    print("\n✅ R12 merged model built and validated: base + R12 trained LoRA")


if __name__ == "__main__":
    main()
