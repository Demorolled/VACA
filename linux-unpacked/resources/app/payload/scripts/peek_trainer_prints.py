#!/usr/bin/env python3
"""Show the key phases (prints, downloads, from_pretrained) of the embedded
round-6 trainer so we know what output to expect during training."""
import json

nb = json.load(open("training/cloud/colab/train_round6_bible_10h_q4_nodrive.ipynb"))
src = "".join(nb["cells"][10]["source"])
for i, line in enumerate(src.splitlines()):
    s = line.strip()
    if (
        s.startswith("print(")
        or "from_pretrained" in s
        or "save_pretrained" in s
        or "download" in s.lower()
        or "huggingface_hub" in s
        or "out_dir" in s
        or "results.zip" in s
    ):
        print(f"{i:4d}: {s[:120]}")
