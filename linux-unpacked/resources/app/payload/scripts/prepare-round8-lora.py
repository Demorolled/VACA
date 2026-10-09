#!/usr/bin/env python3
"""
=============================================================================
  ROUND-8 → q4 LoRA DATASET PREP
  =====================================================================
  Validates + dedups the distilled round-8 code-reasoning JSONL
  (build-round8-code-dataset.py output) and packages it for the local
  GUITrainer (QLoRA 4bit → q4_k_m GGUF export, same pipeline as rounds 5-7).

  The trainer (training/gui_trainer/engine.py) consumes
  {instruction, input, output} rows, requires output >= 10 chars, and builds
  chat-template records (assistant-only masking). This prep step:
    1. parses every line, drops malformed / short-output rows
    2. drops near-duplicate (instruction, output) pairs by content hash
    3. re-checks the round-8 quality gates (fluff, echo, missing code fence
       for code registers)
    4. writes a clean LoRA-ready JSONL + a metadata JSON for the training log

  Usage:
    python3 scripts/prepare-round8-lora.py                     # current file
    python3 scripts/prepare-round8-lora.py --input <path> --output <path>
    python3 scripts/prepare-round8-lora.py --min-bytes 5000000 # warn until big enough

  Idempotent — safe to re-run any time; it snapshots the current file.
=============================================================================
"""
import argparse
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(ROOT, 'training', 'dataset', 'round8-code.jsonl')
DEFAULT_OUT = os.path.join(ROOT, 'training', 'dataset', 'round8-lora-ready.jsonl')
META_OUT = os.path.join(ROOT, 'training', 'dataset', 'round8-lora-metadata.json')

CODE_FENCE = re.compile(r"```[a-zA-Z0-9+#.-]*\s*\n")
CODE_REGISTERS = {
    'codegen', 'algo', 'api', 'sql', 'shell', 'regex', 'web',
    'git', 'docker', 'test', 'security', 'data',
}
FLUFF_ANYWHERE = [
    r"i see you'?re typing", r"\[REASONING", r"chain-?of-?thought",
    r"^Bot\s*:", r"^User\s*:", r"^Assistant\s*:", r"<thinking>",
    r"</thinking>", r"\[think\]", r"\[/think\]", r"as a large language model",
]


def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def row_is_valid(row):
    """Return (ok, reason). Mirrors the trainer's minimum contract + gates."""
    instruction = (row.get('instruction') or '').strip()
    output = (row.get('output') or '').strip()
    if not instruction:
        return False, 'empty-instruction'
    if len(output) < 10:
        return False, 'short-output'
    if any(re.search(p, output, re.I) for p in FLUFF_ANYWHERE):
        return False, 'fluff'
    register = (row.get('source') or '').split(':')[1] if ':' in (row.get('source') or '') else ''
    if register in CODE_REGISTERS and not CODE_FENCE.search(output):
        return False, 'missing-code-fence'
    # verbatim echo of the instruction
    tn, i = norm(output), norm(instruction)
    if i and (tn == i or tn.startswith(i[:30]) or i.startswith(tn[:30])):
        return False, 'echo'
    return True, ''


def main():
    ap = argparse.ArgumentParser(description='Prepare round-8 distillation for q4 LoRA')
    ap.add_argument('--input', default=DEFAULT_IN)
    ap.add_argument('--output', default=DEFAULT_OUT)
    ap.add_argument('--min-bytes', type=int, default=0,
                    help='warn (non-fatal) if input is below this size')
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f'❌ input not found: {args.input}')
        print('   (the distillation build is still running — this prep is')
        print('    a snapshot; re-run it later for the full dataset)')
        sys.exit(1)

    in_bytes = os.path.getsize(args.input)
    if args.min_bytes and in_bytes < args.min_bytes:
        print(f'⚠️  input is only {in_bytes/1e6:.2f} MB — under the '
              f'{args.min_bytes/1e6:.1f} MB threshold. Consider waiting for '
              f'the build to finish, or accept a smaller round.')

    total = kept = 0
    by_register = {}
    dropped = {}
    seen = set()
    out_rows = []

    with open(args.input, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                dropped['unparseable'] = dropped.get('unparseable', 0) + 1
                continue
            ok, why = row_is_valid(row)
            if not ok:
                dropped[why] = dropped.get(why, 0) + 1
                continue
            # dedup on normalized (instruction, output) content hash
            h = hashlib.sha1(
                (norm(row.get('instruction', '')) + '||' + norm(row.get('output', ''))).encode()
            ).hexdigest()
            if h in seen:
                dropped['duplicate'] = dropped.get('duplicate', 0) + 1
                continue
            seen.add(h)
            # keep only the trainer's contract keys (drops source)
            out_rows.append({
                'instruction': row.get('instruction', ''),
                'input': row.get('input', ''),
                'output': row.get('output', ''),
            })
            reg = (row.get('source') or '').split(':')[1] if ':' in (row.get('source') or '') else 'unknown'
            by_register[reg] = by_register.get(reg, 0) + 1
            kept += 1

    with open(args.output, 'w', encoding='utf-8') as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    meta = {
        'input_file': args.input,
        'input_bytes': in_bytes,
        'output_file': args.output,
        'rows_total': total,
        'rows_kept': kept,
        'rows_dropped': total - kept,
        'dropped_breakdown': dropped,
        'bytes_written': os.path.getsize(args.output),
        'by_register': by_register,
        'format': 'instruction/input/output',
        'target': 'QLoRA 4bit -> q4_k_m GGUF (GUITrainer, Qwen2.5-7B-Instruct-Uncensored)',
        'prepared_at': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
    }
    with open(META_OUT, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    print(f'✅ LoRA-ready dataset written: {args.output}')
    print(f'   total rows: {total} | kept: {kept} | dropped: {total - kept}')
    print(f'   bytes: {meta["bytes_written"]/1e6:.2f} MB')
    print(f'   registers: {sorted(by_register)}')
    if dropped:
        print(f'   drops: {dropped}')
    print(f'   metadata: {META_OUT}')


if __name__ == '__main__':
    main()
