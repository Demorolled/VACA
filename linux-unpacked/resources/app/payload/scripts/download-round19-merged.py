#!/usr/bin/env python3
"""
Download the round-19 trained adapter + merged witness from the Kaggle kernel.

Kernel: stevenawoods/vaca-qlora-round19 (Qwen2.5-Coder-14B-Instruct-Uncensored,
resumes the R18 LoRA — chained continuation). --no-gguf output:
  out/adapter_round19/     (the new LoRA — the REAL trained weights)
  out/model.safetensors    (kernel merged export — NF4 witness only; the real
                            deployable merged model is built locally by
                            scripts/build-r19-merged.py, which loads the base
                            + adapter_round19 and does save_pretrained_merged
                            with merged_16bit)

Placement:
  training/cloud/out/round19/adapter/   <- adapter_round19 (for future rounds)
  training/cloud/out/round19/merged/    <- kernel merged export (witness only)

After download, build + deploy:
  python3 scripts/build-r19-merged.py    # real fp16 merged from base + adapter
  bash scripts/deploy-round19.sh         # convert -> q4_k_m GGUF, deploy to
                                         # dspark :8000, back up the R18 Q4 first

Usage:
  python3 scripts/download-round19-merged.py [adapter|merged|all]
"""

import sys
from pathlib import Path

import requests

KERNEL = "stevenawoods/vaca-qlora-round19"

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "out" / "round19"
ADAPTER_DIR = OUT / "adapter"
MERGED_DIR = OUT / "merged"

ADAPTER_FILES = [
    "out/adapter_round19/adapter_config.json",
    "out/adapter_round19/adapter_model.safetensors",
    "out/adapter_round19/chat_template.jinja",
    "out/adapter_round19/tokenizer.json",
    "out/adapter_round19/tokenizer_config.json",
    "out/adapter_round19/README.md",
]

MERGED_FILES = [
    "out/model.safetensors",
    "out/config.json",
    "out/generation_config.json",
    "out/tokenizer.json",
    "out/tokenizer_config.json",
]


def fetch(url: str, dest: Path, label: str):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  ⏭️  already on disk ({dest.stat().st_size/1e6:.1f} MB): {dest.name}")
        return
    print(f"  ⬇️  {label}: {url.split('?')[0][-70:]}")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    print(f"     ✓ {dest.stat().st_size/1e6:.1f} MB -> {dest}")


def download(mode: str):
    print(f"=== Round-19 download ({mode}) ===")
    files = []
    if mode in ("adapter", "all"):
        files += ADAPTER_FILES
    if mode in ("merged", "all"):
        files += MERGED_FILES
    if not files:
        print("usage: download-round19-merged.py [adapter|merged|all]")
        sys.exit(1)

    for rel in files:
        dest = ADAPTER_DIR / Path(rel).name if rel.startswith("out/adapter") else MERGED_DIR / Path(rel).name
        url = f"https://www.kaggleusercontent.com/kernels/output/{KERNEL}/{rel}"
        try:
            fetch(url, dest, rel)
        except Exception as e:
            print(f"  ⚠️  {rel}: {e} — kernel may still be running (wait, then re-run)")

    print(f"\n  Adapter: {ADAPTER_DIR}")
    print(f"  Merged witness: {MERGED_DIR}")
    print("  Next: python3 scripts/build-r19-merged.py && bash scripts/deploy-round19.sh")


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else "all")
