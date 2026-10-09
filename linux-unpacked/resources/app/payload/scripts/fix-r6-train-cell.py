#!/usr/bin/env python3
"""Fix the round-6 builder's Step-6 train cell and rebuild + validate."""
import subprocess
import sys

BUILDER = "scripts/build-colab-round6-notebook.py"

broken = (
    '        code(\n'
    '            "import subprocess, sys\\n"\n'
    '            "cmd = (\\"python train_round1.py --dataset /content/dataset/round6-bible-10h.jsonl \\\\"\\n"\n'
    '            "       \\" --out-dir /content/out \\\\"\\n"\n'
    '            "       f\\" --rounds 1 --start-round 6 --lr {LR} --epochs {EPOCHS} \\\\"\\n"\n'
    '            "       \\" --max-seq-length 2048\\")\\n"\n'
    '            "print(\'▶ \' + cmd)\\n"\n'
    '            "sys.exit(subprocess.call(cmd, shell=True))\\n"\n'
    '        ),\n'
)

fixed = (
    '        code(\n'
    '            "import subprocess, sys\\n"\n'
    '            "cmd = (\\"python train_round1.py --dataset /content/dataset/round6-bible-10h.jsonl \\"\\n"\n'
    '            "       \\" --out-dir /content/out \\"\\n"\n'
    '            "       f\\" --rounds 1 --start-round 6 --lr {LR} --epochs {EPOCHS} \\"\\n"\n'
    '            "       \\" --max-seq-length 2048\\")\\n"\n'
    '            "print(\'▶ \' + cmd)\\n"\n'
    '            "sys.exit(subprocess.call(cmd, shell=True))\\n"\n'
    '        ),\n'
)

src = open(BUILDER, encoding="utf-8").read()
if broken not in src:
    print("ERROR: broken block not found in builder — aborting")
    sys.exit(1)
src = src.replace(broken, fixed, 1)
open(BUILDER, "w", encoding="utf-8").write(src)
print("builder patched")

# rebuild both notebooks
for cmd in (
    ["python3", "scripts/build-colab-round6-notebook.py"],
    ["python3", "scripts/build-r6-nodrive-notebook.py"],
):
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip()[-400:] if r.stdout.strip() else r.stderr.strip()[-400:])
    if r.returncode != 0:
        print(f"FAILED: {cmd[1]}")
        sys.exit(1)

# validate
r = subprocess.run(
    ["python3", "scripts/validate-cloud-notebooks.py",
     "--notebooks",
     "training/cloud/colab/train_round6_bible_10h_q4.ipynb",
     "training/cloud/colab/train_round6_bible_10h_q4_nodrive.ipynb"],
    capture_output=True, text=True,
)
print(r.stdout[-800:])
print("VALIDATOR EXIT:", r.returncode)
sys.exit(r.returncode)
