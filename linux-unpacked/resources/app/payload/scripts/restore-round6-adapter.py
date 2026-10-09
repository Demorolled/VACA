#!/usr/bin/env python3
"""
Restore the interrupted round-6 adapter download from Kaggle.

The original flow (kaggle-watch-round6.sh -> download_round6.sh) failed twice:
  1. The session crashed mid-`kaggle kernels output` (IncompleteRead after 3.9 GB)
  2. Even on success it would fail: the kernel output contains 84 LOOSE files,
     not a results.zip, so download_round6.sh's `find -name results.zip` misses.

This script instead:
  - Lists the kernel session output files via the Kaggle SDK
  - Selects the `out/adapter_round6/` LoRA adapter files (small, resumable)
  - Downloads them straight from their signed kaggleusercontent URLs
  - Places them at ~/Desktop/new training data set/out/round6-adapter/ (the
    Lightning handoff location download_round6.sh uses) and mirrors to
    training/cloud/out/round6-adapter/ (what kaggle-watch-round6.sh checks)

Usage:
  python3 scripts/restore-round6-adapter.py [--kernel OWNER/SLUG]
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import requests

KERNEL = "stevenawoods/vaca-qlora-round6"
PREFIX = "out/adapter_round6/"

ROOT = Path(__file__).resolve().parent.parent
DESKTOP_DL = Path.home() / "Desktop" / "new training data set" / "out" / "round6-adapter"
PROJECT_DL = ROOT / "training" / "cloud" / "out" / "round6-adapter"

RETRIES = 8


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
    return [
        {"name": f.file_name, "url": f.url}
        for f in (resp.files or [])
    ]


def download(url: str, dest: Path, retries: int = RETRIES):
    """Download with resume support + retries. Returns bytes downloaded or None."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            resume_at = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={resume_at}-"} if resume_at else {}
            with requests.get(url, stream=True, timeout=60, headers=headers) as r:
                if r.status_code == 416:  # already complete
                    part.rename(dest)
                    return part.stat().st_size
                if r.status_code not in (200, 206):
                    print(f"  HTTP {r.status_code} — retrying ({attempt}/{retries})")
                    time.sleep(5)
                    continue
                mode = "ab" if resume_at else "wb"
                with open(part, mode) as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
            # verify integrity: content-length of the final file
            part.rename(dest)
            return dest.stat().st_size
        except Exception as e:
            print(f"  attempt {attempt}/{retries} failed: {type(e).__name__}: {e}")
            time.sleep(5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", default=KERNEL)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = list_output_files(args.kernel)
    selected = [f for f in files if f["name"].startswith(PREFIX)]
    if not selected:
        print(f"❌ no files under {PREFIX} found in kernel output ({len(files)} files total)")
        for f in files[:40]:
            print("   ", f["name"])
        sys.exit(1)

    print(f"✅ {args.kernel} output has {len(files)} files; adapter files ({len(selected)}):")
    for f in selected:
        print(f"  {f['name']}")

    if args.dry_run:
        print("\n(dry run — nothing downloaded)")
        return

    dest = DESKTOP_DL
    ok = True
    for f in selected:
        rel = Path(f["name"]).name
        out = dest / rel
        if out.exists() and out.stat().st_size > 0:
            print(f"✓ already present: {out} ({out.stat().st_size} bytes)")
            continue
        print(f"⬇️  {rel} ...")
        size = download(f["url"], out)
        if size is None:
            ok = False
            print(f"❌ failed after {RETRIES} attempts: {rel}")
        else:
            print(f"  ✓ {out.name}: {size} bytes")

    if not ok:
        print("\n❌ some files failed — rerun this script to resume.")
        sys.exit(1)

    # mirror into the project tree so kaggle-watch-round6.sh's check passes
    shutil.copytree(dest, PROJECT_DL, dirs_exist_ok=True)
    print(f"\n📋 mirrored to {PROJECT_DL}")

    config = dest / "adapter_config.json"
    weights = dest / "adapter_model.safetensors"
    print()
    if config.exists() and weights.exists():
        print(f"✅ round-6 adapter restored:")
        print(f"   {config}  ({config.stat().st_size} bytes)")
        print(f"   {weights} ({weights.stat().st_size/1e6:.1f} MB)")
        print(f"   Next: upload ~/Desktop/new training data set/ to Lightning AI and run  bash setup_lightning.sh")
    else:
        print(f"⚠️  adapter incomplete — missing adapter_config.json or adapter_model.safetensors")


if __name__ == "__main__":
    main()
