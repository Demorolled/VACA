#!/usr/bin/env python3
"""Build a no-Drive variant of the round-6 Colab notebook.

The round-6 Step-4 cell mounts Google Drive when USE_DRIVE=True, which pops an
interactive OAuth dialog — a hard blocker for headless automation. This script
rewrites the config cell to USE_DRIVE = False so Step 4 goes straight to the
file-upload / /content fallback path.
"""
import json
import sys

SRC = "training/cloud/colab/train_round6_bible_10h_q4.ipynb"
DST = "training/cloud/colab/train_round6_bible_10h_q4_nodrive.ipynb"

nb = json.load(open(SRC))
edited = 0
for c in nb["cells"]:
    if c["cell_type"] != "code":
        continue
    src = "".join(c["source"])
    if "USE_DRIVE" in src and "ZIP_NAME" not in src and "EPOCHS" in src:
        new_src = src.replace("USE_DRIVE = True", "USE_DRIVE = False")
        assert new_src != src, "USE_DRIVE line not found in config cell"
        # keep source as a list of lines for compatibility
        c["source"] = new_src.splitlines(keepends=True)
        edited += 1
        print("editing config cell: USE_DRIVE = True -> False")

# Also drop the Drive-mount mention from Step-4 markdown (cosmetic, optional)
for c in nb["cells"]:
    if c["cell_type"] == "markdown":
        src = "".join(c["source"])
        if "Drive" in src and "upload" in src and "Step 4" in src:
            c["source"] = src.replace(
                "on Drive (mounts it if needed) or asks", "or asks"
            ).splitlines(keepends=True)

if edited != 1:
    print(f"ERROR: expected exactly 1 config-cell edit, got {edited}")
    sys.exit(1)

json.dump(nb, open(DST, "w"), indent=1)
print(f"wrote {DST}")
