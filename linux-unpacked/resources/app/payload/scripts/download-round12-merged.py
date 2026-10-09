#!/usr/bin/env python3
"""
Download the round-12 trained model + adapter from the Kaggle kernel output.

The round-12 kernel (stevenawoods/vaca-qlora-round12) trains round-12 defects
resuming from the REAL R11 LoRA (vaca-r11-adapter dataset) and runs with
--no-gguf, so its output is:
  out/adapter_round12/     (the new LoRA — resume point for any later round)
  out/model-0000{1-4}.safetensors + index + config/tokenizer   (merged 16-bit)

Downloads with Range-resume + retries straight from signed kaggleusercontent
URLs (the `kaggle kernels output` zip stream dies with IncompleteRead on files
this large).

Placement:
  training/cloud/out/round12/adapter/   <- adapter_round12 (for chained rounds)
  training/cloud/out/round12/merged/    <- merged safetensors + config/tokenizer

After download, deploy:
  bash scripts/deploy-round12.sh        # convert -> q4_k_m GGUF, deploy to
                                        # dspark :8000, then drop the old R11
                                        # (guarded by the model-backups/ snapshot)

Usage:
  python3 scripts/download-round12-merged.py [adapter|merged|all]
"""

import os
import sys
import time
from pathlib import Path

import requests

KERNEL = "stevenawoods/vaca-qlora-round12"

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "training" / "cloud" / "out" / "round12"
ADAPTER_DIR = OUT / "adapter"
MERGED_DIR = OUT / "merged"

ADAPTER_FILES = [
    "out/adapter_round12/adapter_config.json",
    "out/adapter_round12/adapter_model.safetensors",
    "out/adapter_round12/chat_template.jinja",
    "out/adapter_round12/tokenizer.json",
    "out/adapter_round12/tokenizer_config.json",
    "out/adapter_round12/README.md",
]

MERGED_FILES = [
    "out/model.safetensors",   # R12 save_pretrained wrote a SINGLE shard (no index)
    "out/config.json",
    "out/generation_config.json",
    "out/tokenizer.json",
    "out/tokenizer_config.json",
    "out/chat_template.jinja",
    "out/README.md",
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
    """Total file size via a 1-byte Range probe (Content-Range header)."""
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
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    files = list_output_files(KERNEL)
    print(f"[dl] {KERNEL}: {len(files)} output files; plan = {which}", flush=True)

    jobs = []
    if which in ("all", "adapter"):
        jobs += [(ADAPTER_FILES, ADAPTER_DIR)]
    if which in ("all", "merged"):
        jobs += [(MERGED_FILES, MERGED_DIR)]

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
                print(f"[dl] ❌ {dest.name} failed after {RETRIES} attempts", flush=True)
                failures.append(name)

    if failures:
        print(f"[dl] ❌ {len(failures)} file(s) failed: {failures}", flush=True)
        print("[dl] Rerun to resume — Range-resume makes this safe.", flush=True)
        sys.exit(1)
    print("[dl] ✅ ALL round-12 artifacts downloaded", flush=True)


if __name__ == "__main__":
    main()
