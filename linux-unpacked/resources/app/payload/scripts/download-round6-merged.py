#!/usr/bin/env python3
"""
Download the round-6 merged model + F16 GGUF from the Kaggle kernel output.

The kernel (stevenawoods/vaca-qlora-round6) crashed after training in the
GGUF-export cell, but its output contains the fully-trained artifacts:
  - out/model-0000X-of-00004.safetensors  (merged base+LoRA, fp16, ~15.2 GB)
  - out/model.safetensors.index.json, config.json, tokenizer*, chat_template
  - Qwen2.5-7B-Instruct-Uncensored.F16.gguf  (~5.35 GB)

Unlike `kaggle kernels output` (no resume; the original crash point), this
downloads each file straight from its signed kaggleusercontent URL with
Range-based resume + retries, so a blip never restarts from zero.

Placement:
  training/cloud/out/round6-merged/  <- shards + index/config/tokenizer
  training/cloud/out/round6-gguf/    <- F16 GGUF

Usage:
  python3 scripts/download-round6-merged.py            # foreground
  nohup python3 scripts/download-round6-merged.py > data/download-round6-merged.log 2>&1 &
"""

import os
import sys
import time
from pathlib import Path

import requests

KERNEL = "stevenawoods/vaca-qlora-round6"

ROOT = Path(__file__).resolve().parent.parent
MERGED_DIR = ROOT / "training" / "cloud" / "out" / "round6-merged"
GGUF_DIR = ROOT / "training" / "cloud" / "out" / "round6-gguf"

MERGE_FILES = [
    "out/model-00001-of-00004.safetensors",
    "out/model-00002-of-00004.safetensors",
    "out/model-00003-of-00004.safetensors",
    "out/model-00004-of-00004.safetensors",
    "out/model.safetensors.index.json",
    "out/config.json",
    "out/generation_config.json",
    "out/tokenizer.json",
    "out/tokenizer_config.json",
    "out/chat_template.jinja",
    "out/README.md",
]
GGUF_FILES = [
    "Qwen2.5-7B-Instruct-Uncensored.F16.gguf",
]

RETRIES = 10
TIMEOUT = 120


def list_output_files(kernel: str):
    from kaggle.api.kaggle_api_extended import KaggleApi
    from kagglesdk.kernels.types import kernels_api_service as t

    api = KaggleApi()
    api.authenticate()
    client = api.build_kaggle_client()
    svc = client.kernels.kernels_api_client
    req = t.ApiListKernelSessionOutputRequest()
    owner, slug = kernel.split("/", 1)
    req.user_name = owner
    req.kernel_slug = slug
    req.page_size = 500
    resp = svc.list_kernel_session_output(req)
    return {f.file_name: f.url for f in (resp.files or [])}


def expected_size(url: str) -> int:
    """Return total file size via a 1-byte Range probe (Content-Range header)."""
    r = requests.get(url, headers={"Range": "bytes=0-0"}, timeout=TIMEOUT, allow_redirects=True)
    cr = r.headers.get("content-range") or r.headers.get("Content-Range")
    if cr:
        return int(cr.split("/")[1])
    cl = r.headers.get("content-length")
    return int(cl) if cl else 0


def download(url: str, dest: Path, total: int):
    """Download with Range-resume + retries. Returns True on full success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, RETRIES + 1):
        try:
            done = part.stat().st_size if part.exists() else 0
            if done >= total > 0:
                part.rename(dest)
                return True
            headers = {"Range": f"bytes={done}-"} if done else {}
            with requests.get(url, stream=True, timeout=TIMEOUT, headers=headers) as r:
                if r.status_code == 416:  # range not satisfiable -> already complete
                    part.rename(dest)
                    return True
                if r.status_code not in (200, 206):
                    print(f"    HTTP {r.status_code} — retry {attempt}/{RETRIES}")
                    time.sleep(8)
                    continue
                mode = "ab" if done else "wb"
                with open(part, mode) as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                size = part.stat().st_size
                if total > 0 and size >= total:
                    part.rename(dest)
                    return True
        except Exception as e:
            print(f"    {type(e).__name__}: {e} — retry {attempt}/{RETRIES}")
            time.sleep(8)
    return False


def main():
    if len(sys.argv) > 1:
        which = sys.argv[1]  # "merged" | "gguf" | "all"
    else:
        which = "all"

    files = list_output_files(KERNEL)
    print(f"[dl] {KERNEL}: {len(files)} output files; plan = {which}", flush=True)

    jobs = []
    if which in ("all", "merged"):
        jobs += [(MERGE_FILES, MERGED_DIR)]
    if which in ("all", "gguf"):
        jobs += [(GGUF_FILES, GGUF_DIR)]

    failures = []
    for names, out_dir in jobs:
        for name in names:
            if name not in files:
                print(f"[dl] ⚠️  missing in output: {name}", flush=True)
                failures.append(name)
                continue
            url = files[name]
            dest = out_dir / Path(name).name
            if dest.exists() and dest.stat().st_size > 0:
                total = expected_size(url)
                if total and dest.stat().st_size >= total:
                    print(f"[dl] ✓ already complete: {dest} ({dest.stat().st_size/1e9:.2f} GB)", flush=True)
                    continue
            total = expected_size(url)
            print(f"[dl] ⬇️  {dest.name} ({total/1e9:.2f} GB) -> {out_dir.name}/", flush=True)
            t0 = time.time()
            ok = download(url, dest, total)
            if ok:
                got = dest.stat().st_size
                print(f"[dl] ✓ {dest.name}: {got/1e9:.2f} GB in {time.time()-t0:.0f}s"
                      + (f"  (expected {total/1e9:.2f} GB)" if total else ""), flush=True)
            else:
                print(f"[dl] ❌ failed after {RETRIES} attempts: {name}", flush=True)
                failures.append(name)

    print()
    if failures:
        print(f"[dl] ❌ DONE with {len(failures)} failures: {failures}", flush=True)
        print("[dl] rerun this script to resume (range-resume preserves completed bytes)", flush=True)
        sys.exit(1)
    print("[dl] ✅ ALL round-6 merged model + GGUF files downloaded.", flush=True)
    for d in (MERGED_DIR, GGUF_DIR):
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    print(f"[dl]   {f.name}: {f.stat().st_size/1e9:.2f} GB", flush=True)


if __name__ == "__main__":
    main()
