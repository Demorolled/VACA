#!/usr/bin/env python3
"""
Build the REAL round-11 merged model locally (no Kaggle re-run).

The round-11 kernel trained correctly (102 rows x 2 epochs = 26 optimizer
steps, LR 5e-5, loss 0.61 -> 0.63) but its save step wrote the pre-training
(R10) adapter as the round result. The genuinely-trained LoRA lives in the
kernel output at out/adapter_round11/resume/ (hash e3b7e7cc...).

Recovery — exact algebra, no base-model re-download:
    merged_R11 = merged_R10 + (B11@A11 - B10@A10) * (alpha/r)

Both R10 and R11 LoRAs are r=8 / alpha=16 / rslora=False on the same base
(Orion-zhen/Qwen2.5-7B-Instruct-Uncensored), so the LoRA delta can be added
directly onto the R10-merged weights.

The round11/merged safetensors shards are patched IN PLACE at their existing
data offsets (same dtype/shape -> identical file layout, low RAM).

Steps: 0) stage the trained adapter as adapter_trained/ (future chaining)
       1) validate the math: merged_R10 == base + R10_BA*scale
       2) patch round11/merged shards with the LoRA delta
       3) validate the result: patched == base + R11_BA*scale
"""
import struct, json, shutil, gc, sys
from pathlib import Path
import torch

ROOT = Path("/home/final-flash1/Desktop/visual-ai-architect")
BASE_SNAP = next(
    Path.home().joinpath(
        ".cache/huggingface/hub/models--Orion-zhen--Qwen2.5-7B-Instruct-Uncensored/snapshots"
    ).glob("*")
)
MERGED_R10 = ROOT / "training/cloud/out/round10/merged"
MERGE_OUT = ROOT / "training/cloud/out/round11/merged"
R10_ADAPTER = ROOT / "training/cloud/out/round10/adapter/adapter_model.safetensors"
KERNEL_RESUME = Path("/tmp/r11outcheck/out/adapter_round11/resume")
ADAPTER_TRAINED_DIR = ROOT / "training/cloud/out/round11/adapter_trained"
ADAPTER_TRAINED = ADAPTER_TRAINED_DIR / "adapter_model.safetensors"

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


def patch_merged_shard(shard_name: str, r10: dict, r11: dict) -> int:
    path = MERGE_OUT / shard_name
    with open(path, "rb") as f:
        hlen = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(hlen))
    data_off = 8 + hlen
    patched = 0
    # safetensors header is FLAT: one top-level key per tensor + "metadata"
    tensor_entries = {k: v for k, v in header.items() if k != "metadata"}
    for mk, info in tensor_entries.items():
        if not mk.endswith(".weight"):
            continue
        core = mk[: -len(".weight")]
        akey = f"base_model.model.{core}.lora_A.weight"
        if akey not in r11 or f"base_model.model.{core}.lora_B.weight" not in r11:
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
            new = (old + lora_delta(r11, mk) - lora_delta(r10, mk)).to(
                torch.bfloat16
            ).contiguous()
            f.seek(data_off + start)
            # numpy has no bfloat16; bf16 bit pattern == int16 view
            f.write(new.view(torch.int16).numpy().tobytes())
        patched += 1
        del old, new
    gc.collect()
    return patched


def main() -> None:
    # 0) stage the trained adapter for chaining
    if not ADAPTER_TRAINED.exists():
        assert KERNEL_RESUME.exists(), f"kernel resume dir missing: {KERNEL_RESUME}"
        ADAPTER_TRAINED_DIR.mkdir(parents=True, exist_ok=True)
        for f in KERNEL_RESUME.iterdir():
            if f.is_file():
                shutil.copy2(f, ADAPTER_TRAINED_DIR / f.name)
        print(f"✅ staged trained adapter -> {ADAPTER_TRAINED_DIR.name}/")
    else:
        print("✅ trained adapter already staged")

    r10 = load_sf(R10_ADAPTER)
    r11 = load_sf(ADAPTER_TRAINED)
    assert set(r10) == set(r11), "adapter key sets differ!"
    assert len(r10) == 392, f"expected 392 LoRA tensors, got {len(r10)}"

    # confirm R10 adapter hyperparams match the scaling assumption
    c10 = json.load(open(ROOT / "training/cloud/out/round10/adapter/adapter_config.json"))
    c11 = json.load(open(ADAPTER_TRAINED_DIR / "adapter_config.json"))
    for c in (c10, c11):
        assert c["lora_alpha"] == 16 and c["r"] == 8 and not c.get("use_rslora"), c
    print(f"✅ both adapters r={R} alpha={ALPHA} rslora=False -> scale={SCALE}")

    # confirm the shards we patch are (currently) the R10-merged bytes
    s1 = weight_map(MERGED_R10, SAMPLE_MODULES[0])
    assert (MERGE_OUT / s1).exists(), f"{s1} missing in round11/merged!"
    print(f"✅ round11/merged present ({s1} found); patching in place")

    # 1) validate the algebra on the UNPATCHED merged
    err_before = validate(MERGE_OUT, r10, "before patch (R10 math)")
    assert err_before < 5e-3, f"validation failed: {err_before}"

    # 2) patch each shard in place
    index = json.load(open(MERGE_OUT / "model.safetensors.index.json"))
    shards = sorted(set(index["weight_map"].values()))
    total = 0
    for shard in shards:
        n = patch_merged_shard(shard, r10, r11)
        total += n
        print(f"   patched {shard}: {n} modules")
    print(f"✅ patched {total} LoRA module weights across {len(shards)} shards")

    # 3) validate the result = base + trained LoRA
    err_after = validate(MERGE_OUT, r11, "after patch (R11 math)")
    assert err_after < 5e-3, f"post-validation failed: {err_after}"
    print("\n✅ R11 merged model built and validated: base + trained LoRA")


if __name__ == "__main__":
    main()
