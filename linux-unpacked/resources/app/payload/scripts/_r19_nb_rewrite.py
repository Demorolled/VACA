#!/usr/bin/env python3
"""One-shot rewrite of build-round19-kaggle-notebook.py (from the R18 copy)."""
from pathlib import Path

p = Path('scripts/build-round19-kaggle-notebook.py')
s = p.read_text()

repl = [
    ("Build the Round-18 Kaggle notebook — Qwen2.5-Coder-14B CONTINUATION round.",
     "Build the Round-19 Kaggle notebook — Qwen2.5-Coder-14B CONTINUATION round."),
    ("Dataset A: <user>/round18-corpus   (2,117 rows: R16 clean-code 611 +",
     "Dataset A: <user>/round19-corpus   (~1,900 rows capped for the 10h weekly quota:"),
    ("    Dataset B: <user>/vaca-r17-adapter  (the R17 trained LoRA — chained resume;",
     "    Dataset B: <user>/vaca-r18-adapter  (the R18 trained LoRA — chained resume;"),
    ("    Kernel   : <user>/vaca-qlora-round18 (single-GPU T4, RESUMES the R18 LoRA)",
     "    Kernel   : <user>/vaca-qlora-round19 (single-GPU T4, RESUMES the R18 LoRA)"),
    ("Round-18 config (continuation — mirrors R15→R16 chaining):",
     "Round-19 config (continuation — mirrors R15→R16 chaining):"),
    ("  1 epoch · batch 2 × grad-accum 4 (effective 8) · seq 3072 · LR 5e-5 (gentle)",
     "  1 epoch · batch 2 × grad-accum 4 (effective 8) · seq 3072 · LR 3e-5 (gentle)"),
    ("  WHY resume: R17 was the 14B's first fine-tune (fresh base). R18 carries the",
     "  WHY resume: R19 continues the 14B chain from the R18 LoRA, teaching the new"),
    ("  patterns without losing R17's knowledge. Same pattern as R16 resumed R15.",
     "  multi-file repair-pairs + captures without forgetting R18's knowledge."),
    ("  python3 scripts/build-round18-kaggle-notebook.py    # then: build the notebook",
     "  python3 scripts/build-round19-kaggle-notebook.py    # then: build the notebook"),
    ("  bash scripts/kaggle-setup-round18.sh                # push adapter + dataset + kernel",
     "  bash scripts/kaggle-setup-round19.sh                # push adapter + dataset + kernel"),
    ('        f"(48 new today) + repair-pairs 6; RESUMES the R18 LoRA, LR 5e-5, 1 ep, "',
     '        f"+ repair-pairs 9 (incl. 3 multi-file); RESUMES the R18 LoRA, LR 3e-5, 1 ep, "'),
    ("        \"assert ds.exists(), 'round18-train.jsonl missing after copy!'\"",
     "        \"assert ds.exists(), 'round19-train.jsonl missing after copy!'\""),
    ("        \"# ── Dataset B: the R17 trained LoRA (chained resume) ──\"",
     "        \"# ── Dataset B: the R18 trained LoRA (chained resume) ──\""),
    ("        \"print('✅ R17 adapter ready:', adapter_dir)\"",
     "        \"print('✅ R18 adapter ready:', adapter_dir)\""),
    ("        \"# ── Round-18 config (resumes from the R18 LoRA — same chaining as R16←R15) ──\"",
     "        \"# ── Round-19 config (resumes from the R18 LoRA — same chaining as R16←R15) ──\""),
    ("        \"assert (pathlib.Path(ADAPTER) / 'adapter_model.safetensors').exists(), 'R17 adapter missing'\"",
     "        \"assert (pathlib.Path(ADAPTER) / 'adapter_model.safetensors').exists(), 'R18 adapter missing'\""),
    ("        \"print(f'⚙️  Round 18 | base={MODEL}",
     "        \"print(f'⚙️  Round 19 | base={MODEL}"),
    ("        \"print(f'✅ Round-18 adapter present: {sz/1e6:.1f} MB (nonzero = weights written)'\"",
     "        \"print(f'✅ Round-19 adapter present: {sz/1e6:.1f} MB (nonzero = weights written)'\""),
    ("        \"print('✅ SANITY OK — deploy via scripts/download-round18-merged.py + deploy-round18.sh')\"",
     "        \"print('✅ SANITY OK — deploy via scripts/download-round19-merged.py + deploy-round19.sh')\""),
    ('           f"**Corpus: {N_ROWS} rows** = the R17 corpus PLUS today\'s new verified "',
     '           f"**Corpus: {N_ROWS} rows** = the R18 corpus PLUS the new multi-file "'),
    ("  Corpus: {N_ROWS} rows** = the R17 corpus PLUS today's new verified ",
     "  Corpus: {N_ROWS} rows** = the R18 corpus PLUS the new multi-file "),
]

n = 0
for old, new in repl:
    if old in s:
        s = s.replace(old, new)
        n += 1
    else:
        print(f"NOT FOUND: {old[:70]!r}")
p.write_text(s)
print(f"applied {n}/{len(repl)}")
