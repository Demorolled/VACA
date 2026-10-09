#!/usr/bin/env python3
"""
Build the Blueprint fine-tuning dataset (Hybrid Strategy — prong 1: behavior).
============================================================================
Trains the LLM to map ANY natural-language app request to a perfectly
structured JSON blueprint that matches the engine's strict contract:

    Blueprint { app_type, description, keywords, target_stack
                {frontend, backend, database}, architecture_checklist[],
                wiring_graph[{source_module, destination_module, data_passed}] }

This is the dataset side of the hybrid strategy:
  * Fine-tuning hardwires the JSON output shape (never raw prose, always valid
    blueprint JSON) — behavior lives in weights.
  * The bible (bible-reference/, data/code-bible/) stays external for RAG —
    knowledge is injected at prompt time, not baked in.

Sources:
  * backend/blueprints/*.json + generated/*.json  — 1,228 canonical blueprints
  * data/designs.json                              — 811 REAL user prompts

Output (Alpaca JSONL, one record per line — the exact format GUITrainer
load_gui_dataset() reads):
    {"instruction": "<user request>", "input": "", "output": "<blueprint JSON>"}

Also emits train/val/test splits + a validation report.

Retention report:
  --report      build, then compute retention metrics and write them to the
                datasheet (training/datasheets/blueprint-finetune.md) + JSON.
  --report-only report-only mode: read the existing dataset and refresh the
                datasheet WITHOUT rebuilding.

Usage:
  python3 scripts/build-blueprint-finetune-dataset.py [--target 1000] [--seed 42]
  python3 scripts/build-blueprint-finetune-dataset.py --report-only
"""
import argparse
import datetime
import glob
import importlib.util
import json
import os
import random
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLUEPRINT_DIRS = [
    os.path.join(BASE, 'backend', 'blueprints', '*.json'),
    os.path.join(BASE, 'backend', 'blueprints', 'generated', '*.json'),
]
DESIGNS_FILE = os.path.join(BASE, 'data', 'designs.json')
OUT_DIR = os.path.join(BASE, 'training', 'dataset')
DATASHEET_DIR = os.path.join(BASE, 'training', 'datasheets')

CONTRACT_KEYS = ('app_type', 'description', 'keywords', 'target_stack', 'architecture_checklist', 'wiring_graph')

# Natural phrasing templates for synthetic prompts (no design matched).
# {name} / {desc} / {kw} are filled from the blueprint itself.
PHRASINGS = [
    'Build me an app for {desc}',
    'I want a {name} app. {desc}',
    'Create an application: {desc}',
    'I need a tool that {desc}',
    'Make me a {name} — {desc}',
    'Can you build an app to {desc}',
    'Design a {name} app where {desc}',
    'Build a {name} with features for {kw}',
    'I\'m looking for a {name}. {desc}',
    'Help me build {desc}',
]

# Short purpose variants appended when a design has no purpose text.
PURPOSE_HINTS = ['with a clean UI and persistent storage', 'with search and a dashboard',
                 'with real-time updates', 'that is fast and responsive', 'with data persistence',
                 'with authentication and roles', 'with import/export', 'with charts and reports']


def norm(s: str) -> str:
    """Lowercase, strip non-alnum to compare app_type/design names loosely."""
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def load_blueprints():
    """Load every blueprint file; returns {exact app_type: blueprint}.
    Keyed by the EXACT app_type (not normalized) so near-duplicate names like
    'connect_4'/'connect4' and 'tictactoe'/'tic_tac_toe' are NOT collapsed —
    every blueprint on disk must be represented in the dataset."""
    bps = {}
    for pat in BLUEPRINT_DIRS:
        for path in glob.glob(pat):
            try:
                with open(path, encoding='utf-8') as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(raw, dict) or not isinstance(raw.get('app_type'), str):
                continue
            if not all(isinstance(raw.get(k), (str, list, dict)) for k in CONTRACT_KEYS):
                continue
            bps[raw['app_type'].strip()] = raw
    return bps


def load_designs():
    """Load data/designs.json (list of user designs with goal/name/purpose)."""
    try:
        with open(DESIGNS_FILE, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def match_design_to_blueprint(design, bps):
    """Find the canonical blueprint for a design (name/goal token overlap)."""
    name = design.get('name') or ''
    goal = design.get('goal') or ''
    tokens = set(re.findall(r'[a-z][a-z0-9]{3,}', (name + ' ' + goal).lower()))
    for key, bp in bps.items():
        at = norm(bp['app_type'])
        # exact-normalized match on design name first
        if at and at in norm(name) and len(at) >= 3:
            return bp
    for key, bp in bps.items():
        at_words = set(re.findall(r'[a-z][a-z0-9]{3,}', bp['app_type'].lower()))
        kw_words = set()
        for k in bp.get('keywords', [])[:6]:
            kw_words |= set(re.findall(r'[a-z][a-z0-9]{3,}', str(k).lower()))
        hits = len(tokens & at_words) + len(tokens & kw_words)
        if hits >= 2:
            return bp
    return None


def clean_prompt(text: str) -> str:
    """Collapse whitespace/newlines and trim the trailing sentence fragment
    users leave when they paste a node label ('with the new node I added...')."""
    t = re.sub(r'\s+', ' ', text or '').strip()
    t = re.sub(r'(,?\s*(with|and|using|that has|to have)\s+the (new|neew|added|extra).*)$', '', t, flags=re.I)
    return t[:400] or t


def build_blueprint_json(bp) -> dict:
    """Canonical strict output: exactly the 6 contract keys, verbatim.
    No truncation — the trained output must equal the blueprint the engine
    actually serves (bible.ts loadBlueprints())."""
    return {
        'app_type': bp['app_type'],
        'description': bp.get('description', ''),
        'keywords': [k for k in bp.get('keywords', []) if isinstance(k, str)],
        'target_stack': {
            'frontend': str(bp.get('target_stack', {}).get('frontend', 'React')),
            'backend': str(bp.get('target_stack', {}).get('backend', 'Node.js Express')),
            'database': str(bp.get('target_stack', {}).get('database', 'SQLite')),
        },
        'architecture_checklist': [m for m in bp.get('architecture_checklist', []) if isinstance(m, str)],
        'wiring_graph': [
            {'source_module': str(w.get('source_module', '')),
             'destination_module': str(w.get('destination_module', '')),
             'data_passed': str(w.get('data_passed', ''))}
            for w in bp.get('wiring_graph', []) if isinstance(w, dict)
        ],
    }


def readable_kw(bp) -> str:
    """Human-friendly keyword phrase for synthetic prompts: skip the app_type's
    own words so prompts never read 'Build a 2048 with features for 2048...'."""
    at_words = set(re.findall(r'[a-z][a-z0-9]{2,}', bp['app_type'].lower()))
    seen = set()
    parts = []
    for k in bp.get('keywords', []):
        if not isinstance(k, str):
            continue
        kw_words = set(re.findall(r'[a-z][a-z0-9]{2,}', k.lower()))
        if kw_words and kw_words <= at_words:
            continue  # keyword is just the app name reworded
        if k.lower() in seen:
            continue
        seen.add(k.lower())
        parts.append(k)
        if len(parts) >= 4:
            break
    return ', '.join(parts) if parts else bp['app_type'].replace('_', ' ').replace('-', ' ').strip().title()


def readable_desc(bp) -> str:
    """Trim the '— interactive … tool' boilerplate suffix so synthetic prompts
    read naturally instead of 'Make me a 2048 — 2048 sliding tile puzzle game — …'."""
    d = (bp.get('description') or f'a {bp["app_type"]} application').strip()
    d = re.sub(r'\s*[—-]\s*(interactive|a|an|the)?\s*[a-z]*\s*(tool|app|application|simulation|visualizer).*$', '', d, flags=re.I)
    return d


# ─── Retention report (--report / --report-only) ───────────────────────────

def load_bible_chunks():
    """Load {slug: chunk} from every data/code-bible/*.py module."""
    chunks = {}
    chunk_dir = os.path.join(BASE, 'data', 'code-bible')
    if not os.path.isdir(chunk_dir):
        return chunks
    for fn in sorted(os.listdir(chunk_dir)):
        if not fn.endswith('.py'):
            continue
        path = os.path.join(chunk_dir, fn)
        spec = importlib.util.spec_from_file_location(f'chunkdb_{fn[:-3]}', path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:  # noqa: BLE001 - skip broken chunk files for scoring
            continue
        for c in getattr(mod, 'CHUNKS', []):
            if isinstance(c, dict) and c.get('id'):
                chunks[c['id']] = c
    return chunks


def compute_retention(bps, designs, chunks, examples):
    """Retention across every knowledge source. examples = [(instruction, blueprint_json)]."""
    def canon(b):
        return json.dumps({k: b.get(k) for k in CONTRACT_KEYS}, ensure_ascii=False, separators=(',', ':'))

    covered = {b['app_type'] for _, b in examples}
    bp_types = len(bps)
    covered_types = len(covered & set(bps))
    total_bytes = sum(len(canon(b).encode('utf-8')) for b in bps.values())
    covered_bytes = sum(len(canon(b).encode('utf-8')) for at, b in bps.items() if at in covered)
    out_bytes = sum(len(json.dumps(b, ensure_ascii=False).encode('utf-8')) for _, b in examples)

    inst_lower = [p.lower() for p, _ in examples]
    matched_designs = 0
    for d in designs:
        g = re.sub(r'\s+', ' ', (d.get('goal') or d.get('name') or '').strip().lower())
        if not g:
            continue
        # same whitespace normalization as clean_prompt(), so multi-line design
        # goals still match their (collapsed) instructions
        if any(g[:40] in il or il[:40] in g for il in inst_lower):
            matched_designs += 1

    all_text = ' '.join(p.lower() for p, _ in examples)
    all_text += ' ' + ' '.join(b.get('app_type', '').lower() for _, b in examples)
    chunk_hits = 0
    for c in chunks.values():
        if any(re.search(re.escape(t.lower()), all_text)
               for t in c.get('tags', []) if t):
            chunk_hits += 1

    contract_ok = sum(1 for _, b in examples if all(k in b for k in CONTRACT_KEYS))

    def pct(num, den):
        # den == 0 means the source is missing/empty — report 0 (no data retained)
        # rather than a misleading 100%.
        return round(100.0 * num / den, 1) if den else 0.0

    report = {
        'generated': datetime.datetime.now().isoformat(timespec='seconds'),
        'examples': len(examples),
        'blueprints': {'total': bp_types, 'covered': covered_types,
                       'retention_pct': pct(covered_types, bp_types)},
        'blueprint_bytes': {'total': total_bytes, 'covered': covered_bytes, 'in_outputs': out_bytes,
                            'retention_pct': pct(covered_bytes, total_bytes)},
        'designs': {'total': len(designs), 'matched': matched_designs,
                    'retention_pct': pct(matched_designs, len(designs))},
        'bible_chunks': {'total': len(chunks), 'tag_hits': chunk_hits,
                         'retention_pct': pct(chunk_hits, len(chunks))},
        'contract': {'total': len(examples), 'valid': contract_ok,
                     'retention_pct': pct(contract_ok, len(examples))},
    }
    report['blended_retention_index_pct'] = round(
        0.35 * report['blueprints']['retention_pct']
        + 0.20 * report['designs']['retention_pct']
        + 0.20 * report['bible_chunks']['retention_pct']
        + 0.25 * report['contract']['retention_pct'], 1)
    return report


RETENTION_START = '<!-- RETENTION-START -->'
RETENTION_END = '<!-- RETENTION-END -->'


def render_retention_section(report):
    r = report
    return '\n'.join([
        '## 7. Retention metrics',
        '',
        f'> Auto-generated by `scripts/build-blueprint-finetune-dataset.py --report` on {r["generated"]}.',
        '',
        '| Dimension | Retention |',
        '|---|---|',
        f"| Blueprint app types | **{r['blueprints']['retention_pct']}%** ({r['blueprints']['covered']}/{r['blueprints']['total']}) |",
        f"| Blueprint content (bytes) | {r['blueprint_bytes']['retention_pct']}% ({r['blueprint_bytes']['covered']:,}/{r['blueprint_bytes']['total']:,} B) |",
        f"| Real user designs | {r['designs']['retention_pct']}% ({r['designs']['matched']}/{r['designs']['total']}) |",
        f"| Bible chunk semantic tags | {r['bible_chunks']['retention_pct']}% ({r['bible_chunks']['tag_hits']}/{r['bible_chunks']['total']}) |",
        f"| Contract-field fidelity | {r['contract']['retention_pct']}% ({r['contract']['valid']}/{r['contract']['total']}) |",
        f"| **Blended retention index** | **{r['blended_retention_index_pct']}%** |",
        '',
    ])


def update_datasheet(report):
    """Write/replace the retention section of training/datasheets/blueprint-finetune.md."""
    path = os.path.join(DATASHEET_DIR, 'blueprint-finetune.md')
    section = render_retention_section(report)
    os.makedirs(DATASHEET_DIR, exist_ok=True)
    if not os.path.exists(path):
        header = ('# Datasheet — `blueprint-pairs` (Blueprint JSON fine-tuning dataset)\n\n'
                  f'> Retention report generated {report["generated"]}.\n\n')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(header + section)
        return
    src = open(path, encoding='utf-8').read()
    if RETENTION_START in src and RETENTION_END in src:
        src = re.sub(re.escape(RETENTION_START) + r'.*?' + re.escape(RETENTION_END),
                     RETENTION_START + '\n' + section + RETENTION_END, src, flags=re.S)
    else:
        src = src.rstrip() + '\n\n---\n\n' + RETENTION_START + '\n' + section + RETENTION_END + '\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)


def save_retention_report(report, out_dir):
    """Write retention JSON, refresh the datasheet, and merge into meta.json."""
    json_path = os.path.join(out_dir, 'blueprint-pairs-retention.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    update_datasheet(report)
    meta_path = os.path.join(out_dir, 'blueprint-pairs-meta.json')
    if os.path.exists(meta_path):
        try:
            meta = json.load(open(meta_path, encoding='utf-8'))
            meta['retention'] = report
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)
        except (json.JSONDecodeError, OSError):
            pass
    print(f'[report] retention -> {json_path}')
    print(f'[report] datasheet -> {os.path.join(DATASHEET_DIR, "blueprint-finetune.md")}')
    print(f'[report] blended retention index: {report["blended_retention_index_pct"]}%')
    print(f'[report] blueprints {report["blueprints"]["covered"]}/{report["blueprints"]["total"]} '
          f'({report["blueprints"]["retention_pct"]}%) | designs {report["designs"]["retention_pct"]}% | '
          f'bible tags {report["bible_chunks"]["retention_pct"]}% | contract {report["contract"]["retention_pct"]}%')


def load_existing_examples(out_dir):
    """Read the built dataset back as [(instruction, blueprint_json)] for --report-only."""
    path = os.path.join(out_dir, 'blueprint-pairs.jsonl')
    if not os.path.exists(path):
        raise SystemExit(f'--report-only requires {path} — run the build first')
    examples = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            examples.append((r['instruction'], json.loads(r['output'])))
    return examples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', type=int, default=1000, help='target example count (default 1000)')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', default=OUT_DIR)
    report_group = ap.add_mutually_exclusive_group()
    report_group.add_argument('--report', action='store_true',
                              help='build, then compute retention metrics and write them to the datasheet')
    report_group.add_argument('--report-only', action='store_true',
                              help='skip the build; recompute retention from the existing dataset + refresh datasheet')
    args = ap.parse_args()

    random.seed(args.seed)
    bps = load_blueprints()
    designs = load_designs()

    if args.report_only:
        examples = load_existing_examples(args.out)
        chunks = load_bible_chunks()
        report = compute_retention(bps, designs, chunks, examples)
        save_retention_report(report, args.out)
        return
    print(f'[build] blueprints: {len(bps)} | designs: {len(designs)}')
    if args.target < len(bps):
        print(f'[build] ⚠ target {args.target} < {len(bps)} blueprints — coverage guarantee wins, '
              f'final count will be >= {len(bps)}')

    examples = []  # (instruction, blueprint_json)
    used_blueprints = set()

    # 1) REAL user prompts from designs.json, paired with the matched blueprint.
    for d in designs:
        prompt = clean_prompt(d.get('goal') or d.get('name') or '')
        if len(prompt) < 12:
            continue
        bp = match_design_to_blueprint(d, bps)
        if bp is None:
            continue
        key = bp['app_type']
        if key in used_blueprints and random.random() < 0.5:
            continue  # limit duplicates of the same blueprint from designs
        used_blueprints.add(key)
        examples.append((prompt, build_blueprint_json(bp)))

    print(f'[build] {len(examples)} real-prompt examples from designs')

    # 2) GUARANTEE 100% blueprint coverage: one example per untouched app type.
    pool = [bp for key, bp in bps.items() if key not in used_blueprints]
    random.shuffle(pool)
    for bp in pool:
        key = bp['app_type']
        if key in used_blueprints:
            continue
        name = bp['app_type'].replace('_', ' ').replace('-', ' ').strip().title()
        desc = readable_desc(bp)
        kw = readable_kw(bp)
        tmpl = PHRASINGS[random.randrange(len(PHRASINGS))]
        prompt = clean_prompt(tmpl.format(name=name, desc=desc, kw=kw))
        if len(prompt) < 12:
            prompt = f'Build a {name} application'
        used_blueprints.add(key)
        examples.append((prompt, build_blueprint_json(bp)))
        if len(used_blueprints) % 250 == 0:
            print(f'[build] coverage ... {len(used_blueprints)}/{len(bps)} app types')
    print(f'[build] blueprint coverage: {len(used_blueprints)}/{len(bps)} app types')

    # 3) Alternate phrasings to reach the target (duplicates of app types are fine).
    extra_bps = [bp for key, bp in bps.items()]
    i = 0
    while len(examples) < args.target and extra_bps:
        bp = extra_bps[i % len(extra_bps)]
        i += 1
        name = bp['app_type'].replace('_', ' ').replace('-', ' ').strip().title()
        desc = readable_desc(bp)
        kw = readable_kw(bp)
        tmpl = PHRASINGS[random.randrange(len(PHRASINGS))]
        prompt = clean_prompt(tmpl.format(name=name, desc=desc, kw=kw))
        if len(prompt) < 12:
            continue
        examples.append((prompt, build_blueprint_json(bp)))

    # Deduplicate identical instructions.
    seen = set()
    unique = []
    for p, b in examples:
        if p in seen:
            continue
        seen.add(p)
        unique.append((p, b))
    examples = unique

    # Trim extras to the target WITHOUT losing any app type: keep the first
    # example of every app type, then fill the remainder with duplicates.
    if len(examples) > args.target:
        by_type = {}
        rest = []
        for p, b in examples:
            at = b['app_type']
            if at not in by_type:
                by_type[at] = (p, b)
            else:
                rest.append((p, b))
        firsts = list(by_type.values())
        random.shuffle(rest)
        needed = max(0, args.target - len(firsts))
        examples = firsts + rest[:needed]
        print(f'[build] trimmed to {len(examples)} keeping all {len(by_type)} app types')
    else:
        random.shuffle(examples)

    # Post-dedup repair: re-add any app type whose only example was deduped away.
    # NOTE: this runs AFTER the trim, so the final count may exceed --target by
    # the number of repaired app types (coverage intentionally outranks count).
    covered = {b['app_type'] for _, b in examples}
    for key, bp in bps.items():
        if bp['app_type'] in covered:
            continue
        name = bp['app_type'].replace('_', ' ').replace('-', ' ').strip().title()
        examples.append((f'Build a {name} application', build_blueprint_json(bp)))
        covered.add(bp['app_type'])
    print(f'[build] final: {len(examples)} unique examples (target {args.target})')

    # 4) Validate the strict JSON contract on every output.
    contract_errors = 0
    for p, b in examples:
        missing = [k for k in CONTRACT_KEYS if k not in b]
        if missing:
            contract_errors += 1
            print(f'  ✗ {p[:60]}: missing {missing}')
        elif not isinstance(b['wiring_graph'], list) or not isinstance(b['architecture_checklist'], list):
            contract_errors += 1
            print(f'  ✗ {p[:60]}: wrong list types')
    if contract_errors:
        raise SystemExit(f'ABORTED: {contract_errors} examples violate the Blueprint contract')

    # 5) Write dataset + splits (90/5/5).
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(DATASHEET_DIR, exist_ok=True)
    all_path = os.path.join(args.out, 'blueprint-pairs.jsonl')
    with open(all_path, 'w', encoding='utf-8') as f:
        for p, b in examples:
            rec = {'instruction': p, 'input': '', 'output': json.dumps(b, ensure_ascii=False, separators=(',', ':'))}
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    n = len(examples)
    n_val = max(1, int(n * 0.05))
    n_test = max(1, int(n * 0.05))
    n_train = n - n_val - n_test
    splits = {'train': examples[:n_train], 'val': examples[n_train:n_train + n_val],
              'test': examples[n_train + n_val:]}
    for name, items in splits.items():
        pth = os.path.join(args.out, f'blueprint-pairs-{name}.jsonl')
        with open(pth, 'w', encoding='utf-8') as f:
            for p, b in items:
                rec = {'instruction': p, 'input': '', 'output': json.dumps(b, ensure_ascii=False, separators=(',', ':'))}
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    # 6) Stats + datasheet.
    cats = {}
    for p, b in examples:
        cats[b['app_type']] = cats.get(b['app_type'], 0) + 1
    avg_out = sum(len(json.dumps(b, ensure_ascii=False)) for _, b in examples) / max(1, len(examples))
    stack_counts = {}
    for _, b in examples:
        s = b['target_stack']
        key = f"{s['frontend']}/{s['backend']}/{s['database']}"
        stack_counts[key] = stack_counts.get(key, 0) + 1

    print(f'[build] splits: train={len(splits["train"])} val={len(splits["val"])} test={len(splits["test"])}')
    print(f'[build] unique app_types covered: {len(cats)} | avg output bytes: {avg_out:.0f}')
    print(f'[build] top stacks: {sorted(stack_counts.items(), key=lambda x: -x[1])[:3]}')
    print(f'[build] wrote {all_path} (+ splits)')

    meta = {
        'dataset': 'blueprint-pairs',
        'examples': n,
        'split': {k: len(v) for k, v in splits.items()},
        'unique_app_types': len(cats),
        'avg_output_bytes': round(avg_out, 1),
        'stacks': stack_counts,
        'seed': args.seed,
        'sources': {'blueprints': len(bps), 'real_designs': len(designs)},
        'contract': list(CONTRACT_KEYS),
        'format': 'Alpaca JSONL (instruction/input/output) via GUITrainer ChatML',
    }
    with open(os.path.join(args.out, 'blueprint-pairs-meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    print(f'[build] meta -> {os.path.join(args.out, "blueprint-pairs-meta.json")}')

    if args.report:
        chunks = load_bible_chunks()
        report = compute_retention(bps, designs, chunks, examples)
        save_retention_report(report, args.out)


if __name__ == '__main__':
    main()
