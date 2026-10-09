#!/usr/bin/env python3
"""Patch the round-6 notebook builder wording: honest held-out count + timing."""
import io

path = 'scripts/build-colab-round6-notebook.py'
src = open(path, encoding='utf-8').read()

# 1. honest caveat: 28 never-seen -> 12 truly held-out
old1 = (
    '"**Honest caveat:** 33 of the 61 validation prompts are intentionally "\n'
    '"in-train now, so exact-match on those is not a generalization signal — "\n'
    '"watch the **known** gate (valid library key) and the 28 never-seen "\n'
    '"prompts for the real measure."),'
)
new1 = (
    '"**Honest caveat:** 33 of the 61 validation prompts are intentionally "\n'
    '"in-train now, so exact-match on those is not a generalization signal. "\n'
    'Only **12 of 61** prompts are truly held-out (no instruction anywhere in "\n'
    'the dataset — the rest are error-fixes or round-4 inheritance). Watch the "\n'
    '"**known** gate (valid library key) and those 12 for the real measure."),'
)
assert old1 in src, 'caveat block not found'
src = src.replace(old1, new1)

# 2. timing claim in the intro markdown: "2 epochs ≈ 10.9 h on T4 — sized to fill"
old2 = '"for 2,941 rows: **2 epochs ≈ 10.9 h on T4** — "\n            "sized to fill a ~11 h session. Step 4 prints the exact projection "'
new2 = '"for 2,941 rows: **2 epochs ≈ 10.9 h on T4** (range "\n            "8.7–13.1 h @ 5.3–8.0 s/row) — sized to fill a ~11 h session. Step 4 "\n            "prints the exact projection "'
assert old2 in src, 'timing intro not found'
src = src.replace(old2, new2)

# 3. Step 3 markdown: hedge on 2 epochs
old3 = '"Set `EPOCHS` and the session budget. Defaults: **2 epochs** (≈10.9 h "\n           "on T4 for the 2,941-row round-6 set) — this dataset is sized to FILL "\n           "an 11 h session. If your session has less time left, drop to 1; the "\n           "error-fix rows get at least one full pass either way. "\n           "**Don\\'t raise above 3** — round-4 showed 3 epochs on a small set "\n           "already caused app_type vocabulary drift."),'
new3 = '"Set `EPOCHS` and the session budget. Defaults: **2 epochs** (≈10.9 h "\n           "on T4 for the 2,941-row round-6 set; honest range 8.7–13.1 h). If the "\n           "Step-4 projection exceeds ~90% of the session, drop to 1 — the "\n           "error-fix rows get at least one full pass either way. "\n           "**Don\\'t raise above 3** — round-4 showed 3 epochs on a small set "\n           "already caused app_type vocabulary drift."),'
assert old3 in src, 'step 3 block not found'
src = src.replace(old3, new3)

# 4. Step 3 code comment: EPOCHS=2 fills ~11h -> hedge
old4 = 'EPOCHS = 2          # 1 = short · 2 = default (fills ~11 h) · 3 = max, drift risk'
new4 = 'EPOCHS = 2          # 1 = short · 2 = default (~10.9 h mid) · 3 = max, drift risk'
assert old4 in src, 'epochs comment not found'
src = src.replace(old4, new4)

# 5. Step 4 per_row_s: make the T4 constant match the runbook midpoint (6.65)
old5 = "per_row_s = 6.5 if 'T4' in gpu else (3.8 if 'L4' in gpu else (2.2 if 'A100' in gpu or 'H100' in gpu else 6.5))"
new5 = "per_row_s = 6.65 if 'T4' in gpu else (3.8 if 'L4' in gpu else (2.2 if 'A100' in gpu or 'H100' in gpu else 6.65))"
assert old5 in src, 'per_row_s not found'
src = src.replace(old5, new5)

open(path, 'w', encoding='utf-8').write(src)
print('patched all 5 blocks')
