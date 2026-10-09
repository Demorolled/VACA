#!/usr/bin/env python3
"""
Build the REAL round-13 merged model locally (no Kaggle re-run).

The round-13 kernel trained correctly (78 rows, 3 epochs, accum 4 = ~51
optimizer steps) and its save-bug fix worked: the round adapter (sha
5565c096...) is genuinely different from R12's (b8df227c...). BUT its merged
export (out/model.safetensors) is still NF4-quantized (merge_and_unload on the
4-bit QLoRA left absmax/quant_state tensors), so convert_hf_to_gguf refuses it.

Recovery — exact algebra, reusing the REAL R12 fp16 merged shards (which were
themselves validated as base + R12 LoRA to bf16 precision):
    merged_R13 = merged_R12 + (B13@A13 - B12@A12) * (alpha/r)

All adapters are r=8 / alpha=16 / rslora=False on the same base
(Orion-zhen/Qwen2.5-7B-Instruct-Uncensored), so the LoRA delta chain adds
directly: merged_R12 == base + R12_BA*scale, and we patch with the R13-R12
delta.

The round13/merged dir is built fresh: copy the R12 fp16 shards + index, then
patch each shard IN PLACE at its existing data offsets (same dtype/shape ->
identical file layout, low RAM).

Steps: 0) sanity: R12 merged == base + R12_BA*scale (guards the chain base)
       1) copy round12/merged shards + index -> round13/merged (drop the
          quantized single-shard model.safetensors)
       2) patch round13/merged shards with (B13@A13 - B12@A12) * scale
       3) validate: patched == merged_R12 + R13_BA*scale
"""
import gc
import json
import shutil
import struct
from pathlib import Path

import torch

ROOT = Path("/home/final-flash1/Desktop/visual-ai-architect")
MERGED_R12 = ROOT / "training/cloud/out/round12/merged"
MERGE_OUT = ROOT / "training/cloud/out/round13/merged"
ADAPTER_R12 = ROOT / "training/cloud/out/round12/adapter/adapter_model.safetensors"
ADAPTER_R13 = ROOT / "training/cloud/out/round13/adapter/adapter_model.safetensors"

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


def patch_merged_shard(shard_name: str, r12: dict, r13: dict) -> int:
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
        if akey not in r13 or f"base_model.model.{core}.lora_B.weight" not in r13:
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
            new = (old + lora_delta(r13, mk) - lora_delta(r12, mk)).to(
                torch.bfloat16
            ).contiguous()
            f.seek(data_off + start)
            f.write(new.view(torch.int16).numpy().tobytes())
        patched += 1
        del old, new
    gc.collect()
    return patched


def main() -> None:
    assert ADAPTER_R12.exists(), f"R12 adapter missing: {ADAPTER_R12}"
    assert ADAPTER_R13.exists(), f"R13 adapter missing: {ADAPTER_R13}"
    assert (MERGED_R12 / "model.safetensors.index.json").exists(), "R12 merged missing"

    r12 = load_sf(ADAPTER_R12)
    r13 = load_sf(ADAPTER_R13)
    assert set(r12) == set(r13), "R12/R13 adapter key sets differ!"
    assert len(r13) == 392, f"expected 392 LoRA tensors, got {len(r13)}"

    c12 = json.load(open(ROOT / "training/cloud/out/round12/adapter/adapter_config.json"))
    c13 = json.load(open(ROOT / "training/cloud/out/round13/adapter/adapter_config.json"))
    for c in (c12, c13):
        assert c["lora_alpha"] == 16 and c["r"] == 8 and not c.get("use_rslora"), c
    print(f"✅ both adapters r={R} alpha={ALPHA} rslora=False -> scale={SCALE}")
    print(f"   R12 trained: b8df227c… (expect) | R13 trained: 5565c096… (expect)")

    # 0) sanity: R12 merged must equal base + R12 LoRA (it was built that way)
    err_r12 = validate(MERGED_R12, r12, _base_snap(), "R12 merged (base + R12 LoRA)")
    assert err_r12 < 5e-3, f"R12 merged validation failed: {err_r12}"

    # 1) build round13/merged from the real R12 fp16 shards
    MERGE_OUT.mkdir(parents=True, exist_ok=True)
    for f in MERGE_OUT.glob("*"):
        if f.is_file() and f.name != "model.safetensors.index.json":
            f.unlink()  # drop the quantized single-shard download
    index = json.load(open(MERGED_R12 / "model.safetensors.index.json"))
    shards = sorted(set(index["weight_map"].values()))
    for shard in shards:
        shutil.copy2(MERGED_R12 / shard, MERGE_OUT / shard)
    shutil.copy2(MERGED_R12 / "model.safetensors.index.json", MERGE_OUT / "model.safetensors.index.json")
    print(f"✅ copied {len(shards)} R12 fp16 shards + index -> round13/merged (quantized model.safetensors dropped)")

    # 2) patch with (B13@A13 - B12@A12) * scale
    total = 0
    for shard in shards:
        n = patch_merged_shard(shard, r12, r13)
        total += n
        print(f"   patched {shard}: {n} modules")
    print(f"✅ patched {total} LoRA module weights across {len(shards)} shards")

    # 3) validate the result = merged_R12 + R13 LoRA delta
    err_after = validate(MERGE_OUT, r13, MERGED_R12, "after patch (R13 math)")
    assert err_after < 5e-3, f"post-validation failed: {err_after}"
    print("\n✅ R13 merged model built and validated: merged_R12 + R13 trained LoRA")


def _base_snap() -> Path:
    from huggingface_hub import snapshot_download  # noqa: F401
    import glob as _glob
    snaps = _glob.glob(
        str(Path.home() / ".cache/huggingface/hub/models--Orion-zhen--Qwen2.5-7B-Instruct-Uncensored/snapshots/*")
    )
    assert snaps, "base model snapshot not cached"
    return Path(snaps[0])


if __name__ == "__main__":
    main()
