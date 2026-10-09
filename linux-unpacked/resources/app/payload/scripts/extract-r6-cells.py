#!/usr/bin/env python3
"""Extract key cells from the round-6 Colab notebook for exact reference."""
import json

NB = "training/cloud/colab/train_round6_bible_10h_q4.ipynb"
nb = json.load(open(NB))

for i, c in enumerate(nb["cells"]):
    src = "".join(c["source"])
    if c["cell_type"] != "code":
        continue
    tag = ""
    if "USE_DRIVE" in src and "MODE" in src and "ZIP_NAME" not in src:
        tag = "CONFIG"
    elif "ZIP_NAME" in src:
        tag = "STEP4"
    elif "--dataset" in src and "train_round1.py" in src and "!" in src:
        tag = "STEP7"
    if tag:
        print(f"\n{'=' * 70}\n[{tag}] cell #{i}\n{'=' * 70}")
        print(src)
