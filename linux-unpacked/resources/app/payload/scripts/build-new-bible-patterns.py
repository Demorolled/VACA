#!/usr/bin/env python3
"""
Build the NEW bible-pattern training set for VACA (round-7 prep):
  1. Complete web-app patterns from training/gui_trainer/datasets/gui-combined.jsonl
     (690 rows; the ONLY source of genuinely-new complete implementations — the
     bible-reference md files are signature stubs, verified: 0 real impls).
     Each kept row gets a 2nd phrasing via verb-synonym (same canonical output,
     EXACTLY the round-6 "2 phrasings per chunk" convention).
  2. knowledge/patterns.json rows (TypeScript/Python/Go idiom + code patterns).
  3. Flaw-fix rows from the LLM analysis (see ANALYSIS.md):
       - alias normalization (got app_type → canonical)
       - blueprint JSON discipline (never raw C#/prose)
       - code-quality lessons as correct TypeScript (validate-first, no
         innerHTML, no stubs, errors-as-values, no eval, strict types, no N+1)
       - canonical blueprint wiring shapes per app family
  4. Hard dedupe against EVERY existing dataset on (instruction, output) AND
     output code-hash → zero repeats with all prior creations.

Chunk math (H200, seq 2048, Q4 QLoRA 7B):
    T4 anchor 5.3–8.0 s/row → H200 ≈ 8–12× faster ≈ 0.5–1.0 s/row.
    2h chunk = 7,200 s → ~3,600–7,200 rows per chunk at 2 epochs.
    Our set (~1,000 rows × 2 epochs ≈ 25–40 min) fits in ONE 2h budget; the
    trainer hard-stops at --max-minutes 120 per chunk with resumable adapters.

Output → ~/Desktop/new training data set/
            bible-patterns-new.jsonl   (all new rows)
            chunk-1.jsonl … chunk-N.jsonl
            stats.json
            ANALYSIS.md
            README.md
            train_chunk.py
            run_all_chunks.sh

Run:  python3 scripts/build-new-bible-patterns.py
"""
import hashlib
import json
import os
import random
import re
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS_DIR = os.path.join(ROOT, 'training', 'dataset')
GUI_DIR = os.path.join(ROOT, 'training', 'gui_trainer', 'datasets')
FIDELITY = os.path.join(ROOT, 'data', 'blueprint-fidelity-validation.json')
OUT_DIR = os.path.expanduser('~/Desktop/new training data set')

random.seed(42)


# ─── helpers ────────────────────────────────────────────────────────────────

def code_hash(code):
    return hashlib.sha1(re.sub(r'\s+', ' ', code).strip().encode()).hexdigest()


def load_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def collect_existing():
    """All (instruction, output) pairs + output code-hashes from every existing
    dataset → the new set must not collide with any of them."""
    pairs, hashes = set(), set()
    for fn in sorted(os.listdir(DS_DIR)):
        if not fn.endswith('.jsonl') or 'backup' in fn:
            continue
        for r in load_jsonl(os.path.join(DS_DIR, fn)):
            instr, out = r.get('instruction', ''), r.get('output', '')
            if instr and out:
                pairs.add((instr, out))
                hashes.add(code_hash(out))
    return pairs, hashes


# ─── source 1: gui-combined complete apps ───────────────────────────────────

VERB_SYNONYMS = [
    ('Build ', 'Create a complete '),
    ('Build ', 'Make a fully working '),
    ('Implement ', 'Write the code for '),
    ('Implement ', 'Create the '),
    ('Explain ', 'Describe how to build '),
    ('Explain ', 'Walk through the '),
    ('Style ', 'Design the styling for '),
    ('Write ', 'Create '),
]


def gui_rows(existing_pairs, existing_hashes):
    rows = []
    seen = set()
    for r in load_jsonl(os.path.join(GUI_DIR, 'gui-combined.jsonl')):
        instr = str(r.get('instruction') or '').strip()
        out = str(r.get('output') or '')
        if len(out) < 100 or not instr:
            continue
        k = (instr, out)
        h = code_hash(out)
        if k in existing_pairs or k in seen or h in existing_hashes:
            continue
        seen.add(k)
        rows.append({'instruction': instr, 'input': str(r.get('input') or ''),
                     'output': out, 'source': 'gui-combined'})
        # 2nd phrasing (round-6 convention: same canonical output, new prompt)
        alt = instr
        for prefix, repl in VERB_SYNONYMS:
            if instr.startswith(prefix):
                alt = repl + instr[len(prefix):]
                # fix double determiners ("a a", "an a")
                alt = re.sub(r'\b(a|an) a\b', r'\1', alt)
                break
        if alt and alt != instr:
            k2 = (alt, out)
            if k2 not in existing_pairs and k2 not in seen and code_hash(out) not in existing_hashes:
                seen.add(k2)
                rows.append({'instruction': alt, 'input': str(r.get('input') or ''),
                             'output': out, 'source': 'gui-combined-phrasing'})
    return rows


# ─── source 2: patterns.json ────────────────────────────────────────────────

def patterns_rows(existing_pairs, existing_hashes):
    rows = []
    seen = set()
    pats = json.load(open(os.path.join(ROOT, 'knowledge', 'patterns.json')))
    for p in pats:
        code = str(p.get('code') or '')
        if len(code) < 150:
            continue
        title = p.get('title') or 'pattern'
        lang = p.get('language') or 'typescript'
        instr = f'Write a {lang} module that implements the pattern "{title}". Implement {title}.'
        k = (instr, code)
        h = code_hash(code)
        if k in existing_pairs or k in seen or h in existing_hashes:
            continue
        seen.add(k)
        rows.append({'instruction': instr, 'input': '', 'output': code,
                     'source': 'patterns-json'})
    return rows


# ─── source 3: flaw-fix rows ────────────────────────────────────────────────

def flaw_rows(existing_pairs, existing_hashes):
    rows = []
    seen = set()

    def add(instruction, output, source):
        k = (instruction, output)
        h = code_hash(output)
        if k in existing_pairs or k in seen or h in existing_hashes:
            return
        seen.add(k)
        rows.append({'instruction': instruction, 'input': '', 'output': output,
                     'source': source})

    fid = json.load(open(FIDELITY, encoding='utf-8')) if os.path.exists(FIDELITY) else {'cases': []}

    # alias normalization: got → canonical app_type
    done = set()
    for case in fid.get('cases', []):
        got, exp = case.get('got_app_type'), case.get('expected_app_type')
        if not got or not exp or got == exp:
            continue
        if not case.get('checks', {}).get('known') and (got, exp) not in done:
            done.add((got, exp))
            add(f'What is the canonical library app_type for this project? The name "{got}" is not a valid blueprint key.',
                json.dumps({'app_type': exp}, indent=2), 'flaw-alias')
            add(f'The blueprint library key for this app is "{exp}", not "{got}". Confirm the correct app_type.',
                json.dumps({'app_type': exp}, indent=2), 'flaw-alias')

    # blueprint JSON discipline (parse-fail cases)
    for case in fid.get('cases', []):
        if case.get('checks', {}).get('parse'):
            continue
        exp = case.get('expected_app_type')
        if not exp:
            continue
        add(case['instruction'] + ' Return only the blueprint JSON.',
            json.dumps({'app_type': exp}, indent=2), 'flaw-blueprint-json')
        add(f'The blueprint for "{exp}" must be emitted as JSON with the app_type field — never as raw source code or prose.',
            json.dumps({'app_type': exp}, indent=2), 'flaw-blueprint-json')

    # code-quality lessons → correct TypeScript
    LESSONS = [
        ('validate-first', 'Write a TypeScript module that validates all external input before using it — check type, shape, and ranges, and return a clear error on failure. Implement validateInput.',
         '''export interface FieldRule<T> {
  validate(value: unknown): { ok: true; value: T } | { ok: false; error: string };
}

export const requiredString: FieldRule<string> = {
  validate(value: unknown) {
    if (typeof value !== 'string' || value.trim().length === 0) {
      return { ok: false, error: 'expected a non-empty string' };
    }
    return { ok: true, value: value.trim() };
  },
};

export const nonNegativeNumber: FieldRule<number> = {
  validate(value: unknown) {
    if (typeof value !== 'number' || Number.isNaN(value) || value < 0) {
      return { ok: false, error: 'expected a non-negative number' };
    }
    return { ok: true, value };
  },
};

export function validateAll<T extends Record<string, unknown>>(
  rules: { [K in keyof T]: FieldRule<T[K]> },
  raw: Record<string, unknown>,
): { ok: true; value: T } | { ok: false; errors: string[] } {
  const errors: string[] = [];
  const out = {} as T;
  for (const key of Object.keys(rules) as (keyof T)[]) {
    const r = rules[key].validate(raw[String(key)]);
    if (!r.ok) errors.push(`${String(key)}: ${r.error}`);
    else out[key] = r.value;
  }
  return errors.length ? { ok: false, errors } : { ok: true, value: out };
}'''),
        ('no-innerhtml', 'Write a TypeScript module that renders user-controlled text into the DOM safely — never with innerHTML. Implement safeTextRenderer.',
         '''export function safeText(container: HTMLElement, text: string): void {
  container.textContent = text; // textContent never parses HTML — XSS-safe
}

export function safeList(container: HTMLElement, items: string[]): void {
  const ul = document.createElement('ul');
  for (const item of items) {
    const li = document.createElement('li');
    li.textContent = item; // user content is data, never markup
    ul.appendChild(li);
  }
  container.replaceChildren(ul);
}

// NEVER: container.innerHTML = userInput
export const neverInnerHTML = 'use createElement + textContent for user data';'''),
        ('no-stubs', 'Write a TypeScript module with complete real implementations — no TODO, no stubs, no placeholders. Implement fileSizeFormatter.',
         '''export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'] as const;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}'''),
        ('errors-as-values', 'Write a TypeScript module that returns errors as values instead of throwing for expected conditions. Implement safeJsonParser.',
         '''export type Result<T> = { ok: true; value: T } | { ok: false; error: string };

export function parseJsonSafe<T = unknown>(text: string): Result<T> {
  if (typeof text !== 'string' || text.trim() === '') {
    return { ok: false, error: 'empty input' };
  }
  try {
    const value = JSON.parse(text) as T;
    return { ok: true, value };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'invalid JSON' };
  }
}

export function safeDivide(a: number, b: number): Result<number> {
  if (b === 0) return { ok: false, error: 'division by zero' };
  return { ok: true, value: a / b };
}'''),
        ('no-eval', 'Write a TypeScript module that evaluates arithmetic expressions safely without eval() or the Function constructor. Implement safeExpressionEvaluator.',
         r'''export function evaluate(expr: string): number | null {
  const src = expr.replace(/\s+/g, '');
  const tokens = src.match(/\d+(?:\.\d+)?|[+\-*/]/g);
  if (!tokens || tokens.join('') !== src) return null; // reject anything else

  const vals: number[] = [];
  const ops: string[] = [];
  const prec: Record<string, number> = { '+': 1, '-': 1, '*': 2, '/': 2 };

  const apply = (): void => {
    const op = ops.pop() as string;
    const b = vals.pop() as number;
    const a = vals.pop() as number;
    if (op === '+') vals.push(a + b);
    else if (op === '-') vals.push(a - b);
    else if (op === '*') vals.push(a * b);
    else if (op === '/') {
      if (b === 0) throw new RangeError('division by zero');
      vals.push(a / b);
    }
  };

  try {
    for (const tok of tokens) {
      if ('+-*/'.includes(tok)) {
        while (ops.length && prec[ops[ops.length - 1]] >= prec[tok]) apply();
        ops.push(tok);
      } else {
        vals.push(Number(tok));
      }
    }
    while (ops.length) apply();
    const result = vals[0];
    return Number.isFinite(result) ? result : null;
  } catch {
    return null; // division by zero or malformed input → null, never a throw
  }
}'''),
        ('typed-never-any', 'Write a TypeScript module with strict types everywhere — no any, no implicit any, nullable access with ?. and ??. Implement typedUserStore.',
         '''export interface User {
  readonly id: string;
  readonly name: string;
  email: string | null;
}

export class UserStore {
  private readonly byId = new Map<string, User>();

  add(user: User): void {
    this.byId.set(user.id, user);
  }

  find(id: string): User | undefined {
    return this.byId.get(id); // undefined, not null — use ?. / ?? at call site
  }

  displayName(id: string): string {
    const user = this.find(id);
    return user?.name ?? 'Unknown user';
  }

  contact(id: string): string {
    const user = this.find(id);
    return user?.email ?? 'no email on file';
  }
}'''),
        ('no-n-plus-one', 'Write a TypeScript module that loads parent records and their children in one pass — never a query per row. Implement batchCommentsLoader.',
         '''export interface Post { id: number; title: string }
export interface Comment { id: number; postId: number; body: string }

export interface PostsWithComments {
  post: Post;
  comments: Comment[];
}

export function groupCommentsByPost(posts: Post[], comments: Comment[]): PostsWithComments[] {
  const byPost = new Map<number, Comment[]>();
  for (const c of comments) {
    const list = byPost.get(c.postId) ?? [];
    list.push(c);
    byPost.set(c.postId, list);
  }
  // one pass over posts, one pass over comments — O(n + m), no N+1
  return posts.map((post) => ({
    post,
    comments: byPost.get(post.id) ?? [],
  }));
}'''),
        ('concurrency-safe', 'Write a TypeScript module that coordinates concurrent work safely — bounded parallelism, all errors handled, no fire-and-forget. Implement taskPool.',
         '''export interface TaskResult<T> {
  ok: true; value: T;
} | {
  ok: false; error: string;
}

export async function runPool<T>(tasks: Array<() => Promise<T>>, concurrency = 4): Promise<TaskResult<T>[]> {
  const results: TaskResult<T>[] = new Array(tasks.length);
  let next = 0;
  const worker = async (): Promise<void> => {
    while (true) {
      const i = next;
      next += 1;
      if (i >= tasks.length) return;
      try {
        results[i] = { ok: true, value: await tasks[i]() };
      } catch (err) {
        results[i] = { ok: false, error: err instanceof Error ? err.message : String(err) };
      }
    }
  };
  const workers = Array.from({ length: Math.min(concurrency, tasks.length) }, () => worker());
  await Promise.all(workers); // every worker always resolves — nothing is fire-and-forget
  return results;
}'''),
        ('parameterized-sql', 'Write a TypeScript module that queries a database with parameterized statements — never string-concatenated SQL. Implement safeQuery.',
         '''export interface DbRow { [column: string]: string | number | null }

export interface QueryClient {
  query(sql: string, params: unknown[]): Promise<DbRow[]>;
}

export class UserRepository {
  constructor(private readonly db: QueryClient) {}

  findByEmail(email: string): Promise<DbRow[]> {
    // NEVER: `SELECT * FROM users WHERE email = '${email}'`
    return this.db.query('SELECT * FROM users WHERE email = $1 LIMIT 1', [email]);
  }

  search(term: string, limit: number): Promise<DbRow[]> {
    return this.db.query(
      'SELECT * FROM users WHERE name ILIKE $1 ORDER BY id LIMIT $2',
      [`%${term}%`, limit],
    );
  }
}'''),
    ]
    for name, instr, code in LESSONS:
        add(instr, code, 'flaw-' + name)

    # canonical blueprint wiring shapes per app family
    FAMILY_SHAPES = [
        ('interactive dashboard', 'analytics-dashboard',
         ['Data Source', 'Aggregation Engine', 'Chart Renderer', 'Filter Bar', 'Dashboard Layout']),
        ('real-time visualization lab', 'realtime-lab',
         ['Config Input', 'Orchestrator', 'State Store', 'Analysis Engine', 'Ops Dashboard']),
        ('puzzle game', 'puzzle-game',
         ['Game Controller', 'Game Engine', 'Game State', 'AI Opponent', 'Render View']),
        ('data pipeline tool', 'data-pipeline-tool',
         ['Pipeline Config', 'Data Processor', 'Data Store', 'Orchestrator', 'Pipeline Dashboard']),
        ('math explorer', 'math-explorer',
         ['Math Input', 'Math Engine', 'Data Storage', 'Analysis Module', 'Visualization']),
        ('search engine explorer', 'search-explorer',
         ['Query Input', 'Search Engine', 'Index & Data', 'Evaluation Module', 'Results Display']),
        ('content management system', 'cms',
         ['Article Models', 'Content Store', 'Editorial Workflow', 'Comment Service', 'Publishing Controls']),
        ('auth gate', 'auth-gate',
         ['Login Form', 'Session Store', 'Auth Guard', 'User Profile', 'Audit Log']),
    ]
    for name, at, modules in FAMILY_SHAPES:
        wiring = [{'source_module': modules[i], 'destination_module': modules[i + 1],
                   'data_passed': 'results'} for i in range(len(modules) - 1)]
        blueprint = json.dumps({
            'app_type': at,
            'description': f'{name} with real-time visualization and analysis',
            'keywords': [at] + modules,
            'architecture_checklist': modules,
            'wiring_graph': wiring,
        }, indent=2)
        add(f'Generate the canonical blueprint wiring graph for a {name}.', blueprint, 'flaw-family-shape')

    return rows


# ─── main ───────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    existing_pairs, existing_hashes = collect_existing()
    print('existing pairs:', len(existing_pairs))

    rows = []
    rows += gui_rows(existing_pairs, existing_hashes)
    rows += patterns_rows(existing_pairs, existing_hashes)
    rows += flaw_rows(existing_pairs, existing_hashes)

    # final internal dedupe (defensive)
    seen = set()
    kept = []
    for r in rows:
        k = (r['instruction'], r['output'])
        if k in seen:
            continue
        seen.add(k)
        kept.append(r)

    print('rows by source:', dict(Counter(r['source'] for r in kept)))
    print('TOTAL kept:', len(kept))

    with open(os.path.join(OUT_DIR, 'bible-patterns-new.jsonl'), 'w', encoding='utf-8') as f:
        for r in kept:
            f.write(json.dumps(r) + '\n')

    # chunks — split so the chained trainer exercises its resume path. Our set
    # (~1,000 rows × 2 epochs ≈ 25–40 min on H200) fits in one 2h budget, so we
    # split in half: two ~540-row chunks, each well under the 2h hard stop, with
    # chunk-2 resuming from chunk-1's adapter (run_all_chunks.sh chains them).
    half = (len(kept) + 1) // 2
    chunk_files = []
    for i, part in enumerate((kept[:half], kept[half:]), start=1):
        fn = os.path.join(OUT_DIR, f'chunk-{i}.jsonl')
        with open(fn, 'w', encoding='utf-8') as f:
            for r in part:
                f.write(json.dumps(r) + '\n')
        chunk_files.append(len(part))
    # remove stale extra chunks if a previous run wrote more
    i = len(chunk_files) + 1
    while os.path.exists(os.path.join(OUT_DIR, f'chunk-{i}.jsonl')):
        os.remove(os.path.join(OUT_DIR, f'chunk-{i}.jsonl'))
        i += 1

    stats = {
        'generated': datetime.now().isoformat(timespec='seconds'),
        'total_rows': len(kept),
        'by_source': dict(Counter(r['source'] for r in kept)),
        'chunks': len(chunk_files),
        'chunk_rows': chunk_files,
        'h200_throughput_estimate': '0.5-1.0 s/row @ seq 2048, Q4 QLoRA 7B (T4 anchor 5.3-8.0 s/row, H200 8-12x faster)',
        'rows_per_2h_chunk_at_2ep': '~3600-7200',
        'this_set_trains_in': '~25-40 min on H200 at 2 epochs (well within one 2h budget)',
        'dedupe': 'hard-deduped vs all training/dataset/*.jsonl on (instruction, output) + output code-hash',
        'note': 'bible-reference/*.md files were scaffold signature stubs (verified 0 real impls); '
                'complete new code comes from gui-combined.jsonl + patterns.json + flaw rows.',
    }
    json.dump(stats, open(os.path.join(OUT_DIR, 'stats.json'), 'w'), indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == '__main__':
    main()
