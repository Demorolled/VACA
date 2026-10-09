#!/usr/bin/env python3
"""
Build training/dataset/self-contained-corrected.jsonl
======================================================
Anti-delegation corrected examples for the VACA training set.

WHY THIS FILE EXISTS
--------------------
The A/B harness (scripts/ab-test-tuned-vs-stock.py) showed the round-1 tuned
model reliably emits a sibling-module import + `export default` (a thin
delegating facade) even under an explicit "NO imports / named exports only"
instruction. Root cause: ~60% of campaign50-corrected.jsonl rows THEMSELVES
contain a substantive sibling import and/or `export default` — the model was
trained on examples of the exact behavior we want to kill.

CONTENTS
--------
1. HAND-WRITTEN SEEDS — 5 tsc-clean, fully self-contained Countdown Timer
   node rewrites (countdown-engine, timer-input, state-store, alarm-handler,
   timer-ui): zero imports, named exports only, no JSX, browser-native
   `number` timers, real error handling.
2. MECHANICAL SWEEP — every other flagged campaign50 row is transformed:
     a. unused substantive imports  → removed (binding never referenced)
     b. side-effect imports         → removed (fully self-contained)
     c. used substantive imports    → best-effort INLINE of the sibling
        declaration from backend/exports/campaign50/<app>/src/<sibling>.ts
        (exports stripped to locals, depth-1)
     d. `export default Name;`      → `export` on the Name declaration
     e. `export default class/fn N` → `export class/fn N`
     f. NodeJS.Timeout              → number (browser target)
   Each transformed row is re-validated with the TIGHTENED A/B gate
   (analyze + tsc_check). ONLY rows that pass are written. Rows that cannot
   be mechanically fixed are reported in training/dataset/sweep-report.json
   as needs-hand-write, so the bad signal is never shipped.

Rows land in the train split as a priority source via
scripts/merge-campaign50-into-dataset.py (SELF_CONTAINED), ahead of
captured/vaca/existing on dedupe collisions.

Usage:
  python3 scripts/build-self-contained-corrected.py
      # build seeds + sweep, write passing rows. The FULL A/B gate
      # (analyze + tsc_check) runs on EVERY deduped row (seeds AND swept)
      # BY DEFAULT before writing, and hard-fails (exit 1, no file written)
      # if any row fails to compile — so no uncertified output can ship.
  python3 scripts/build-self-contained-corrected.py --no-validate-tsc
      # opt OUT of the build-time gate for fast iterations during hand-write
      # batches (only the regex validate_output runs on the seeds). Use the
      # acceptance loop below before merging.
  python3 scripts/build-self-contained-corrected.py --validate-tsc
      # still accepted for backward compatibility; it is the default now.

Acceptance loop (after any hand-write batch):
  python3 scripts/build-self-contained-corrected.py   # gate is default-on
  python3 scripts/merge-campaign50-into-dataset.py     # re-merge
"""

import importlib.util
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "training", "dataset", "self-contained-corrected.jsonl")
CAMPAIGN = os.path.join(BASE, "training", "dataset", "campaign50-corrected.jsonl")
SWEEP_REPORT = os.path.join(BASE, "training", "dataset", "sweep-report.json")
REF_ROOT = os.path.join(BASE, "backend", "exports", "campaign50")

# ── Load the A/B harness (reuse its gate: analyze + tsc_check) ──────────
_spec = importlib.util.spec_from_file_location(
    "ab", os.path.join(BASE, "scripts", "ab-test-tuned-vs-stock.py")
)
ab = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ab)

# ── Hand-written seed instruction (mirrors the tightened A/B INSTRUCTION) ──
INSTRUCTION = (
    "Generate the source file for the node '{node}' in the 'Countdown Timer' app "
    "(simple tier). Write complete, production-ready TypeScript code that is FULLY "
    "SELF-CONTAINED: implement the entire '{node}' logic inline in this file. "
    "STRICT RULES: (1) NO import statements of any kind - especially NO "
    "sibling-module imports like `import {{ TimerService }} from "
    "'../timer-service/timer-service.ts'`; the build system injects siblings, so "
    "do NOT delegate to or reference other modules. (2) NO `export default` - use "
    "named exports only (`export class`, `export function`, `export const`). "
    "(3) NO JSX - build the DOM with document.createElement. (4) Include real "
    "error handling and edge cases (negative/zero durations, double start/stop, "
    "completing at zero). Return only the code - no markdown, no explanations, "
    "no code fences."
)

# (node, output) pairs — the hand-written seeds. Outputs are the positive signal.
EXAMPLES = [
    (
        "countdown-engine",
        """export type CountdownStatus = 'idle' | 'running' | 'paused' | 'finished';

export class CountdownEngine {
  private timerId: number | null = null;
  private totalSeconds = 0;
  private remainingSeconds = 0;
  private status: CountdownStatus = 'idle';
  private readonly onTick: (remaining: number) => void;
  private readonly onFinish: () => void;

  constructor(options?: { onTick?: (remaining: number) => void; onFinish?: () => void }) {
    this.onTick = options?.onTick ?? (() => undefined);
    this.onFinish = options?.onFinish ?? (() => undefined);
  }

  start(durationSeconds: number): void {
    if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
      throw new RangeError('durationSeconds must be a positive number, got ' + durationSeconds);
    }
    if (this.status === 'running') {
      throw new Error('Countdown is already running - call pause() or reset() first.');
    }
    this.totalSeconds = Math.floor(durationSeconds);
    this.remainingSeconds = this.totalSeconds;
    this.status = 'running';
    this.timerId = window.setInterval(() => this.tick(), 1000);
    this.onTick(this.remainingSeconds);
  }

  pause(): void {
    if (this.status !== 'running') {
      return;
    }
    this.clearTimer();
    this.status = 'paused';
  }

  resume(): void {
    if (this.status !== 'paused' || this.remainingSeconds <= 0) {
      return;
    }
    this.status = 'running';
    this.timerId = window.setInterval(() => this.tick(), 1000);
  }

  reset(): void {
    this.clearTimer();
    this.remainingSeconds = this.totalSeconds;
    this.status = this.totalSeconds > 0 ? 'idle' : 'finished';
  }

  getRemainingSeconds(): number {
    return this.remainingSeconds;
  }

  getStatus(): CountdownStatus {
    return this.status;
  }

  private tick(): void {
    if (this.remainingSeconds <= 0) {
      this.clearTimer();
      this.status = 'finished';
      this.onFinish();
      return;
    }
    this.remainingSeconds -= 1;
    this.onTick(this.remainingSeconds);
    if (this.remainingSeconds <= 0) {
      this.clearTimer();
      this.status = 'finished';
      this.onFinish();
    }
  }

  private clearTimer(): void {
    if (this.timerId !== null) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }
  }
}
""",
    ),
    (
        "timer-input",
        """export type TimerPreset = '1m' | '5m' | '10m' | '25m';

export const TIMER_PRESETS: ReadonlyArray<TimerPreset> = ['1m', '5m', '10m', '25m'];

export function parsePresetSeconds(preset: string): number {
  const match = /^(\\d+)m$/.exec(preset.trim().toLowerCase());
  if (!match) {
    throw new Error('Invalid timer preset "' + preset + '" - expected e.g. 1m, 5m, 10m, 25m.');
  }
  const minutes = Number(match[1]);
  if (!Number.isFinite(minutes) || minutes <= 0) {
    throw new RangeError('Preset "' + preset + '" must be a positive number of minutes.');
  }
  return minutes * 60;
}

export class TimerInput {
  private readonly input: HTMLInputElement;

  constructor(input: HTMLInputElement) {
    if (!(input instanceof HTMLInputElement)) {
      throw new TypeError('TimerInput requires an <input> element.');
    }
    this.input = input;
  }

  readSeconds(): number {
    return parsePresetSeconds(this.input.value);
  }

  validate(): void {
    parsePresetSeconds(this.input.value);
  }

  setPreset(preset: TimerPreset): void {
    parsePresetSeconds(preset);
    this.input.value = preset;
  }
}
""",
    ),
    (
        "state-store",
        """export type CountdownState = 'idle' | 'running' | 'paused' | 'finished';

export class StateStore {
  private state: CountdownState = 'idle';
  private readonly listeners = new Set<(state: CountdownState, previous: CountdownState) => void>();

  getState(): CountdownState {
    return this.state;
  }

  setState(next: CountdownState): void {
    if (!StateStore.isValid(next)) {
      throw new Error('Invalid state "' + next + '" - expected idle, running, paused or finished.');
    }
    if (next === this.state) {
      return;
    }
    const previous = this.state;
    this.state = next;
    this.listeners.forEach((listener) => listener(next, previous));
  }

  subscribe(listener: (state: CountdownState, previous: CountdownState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private static isValid(value: unknown): value is CountdownState {
    return value === 'idle' || value === 'running' || value === 'paused' || value === 'finished';
  }
}
""",
    ),
    (
        "alarm-handler",
        """export type AlarmState = 'off' | 'pinging';

export class AlarmHandler {
  private state: AlarmState = 'off';
  private timerId: number | null = null;
  private readonly onAlarm: () => void;

  constructor(options?: { onAlarm?: () => void }) {
    this.onAlarm = options?.onAlarm ?? (() => undefined);
  }

  start(countdownSeconds: number): void {
    if (this.state === 'pinging') {
      throw new Error('Alarm is already pinging - call stop() first.');
    }
    if (!Number.isFinite(countdownSeconds) || countdownSeconds <= 0) {
      throw new RangeError('countdownSeconds must be positive, got ' + countdownSeconds);
    }
    this.state = 'pinging';
    const deadline = Date.now() + countdownSeconds * 1000;
    this.timerId = window.setInterval(() => {
      const secondsLeft = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      if (secondsLeft <= 0) {
        this.clearTimer();
        this.state = 'off';
        this.onAlarm();
      }
    }, 200);
  }

  stop(): void {
    this.clearTimer();
    this.state = 'off';
  }

  getState(): AlarmState {
    return this.state;
  }

  private clearTimer(): void {
    if (this.timerId !== null) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }
  }
}
""",
    ),
    (
        "timer-ui",
        """export interface TimerUICallbacks {
  onStart: (seconds: number) => void;
  onPause: () => void;
  onReset: () => void;
}

export interface TimerUIOptions extends TimerUICallbacks {
  readSeconds?: () => number;
}

export class TimerUI {
  private readonly container: HTMLElement;
  private readonly callbacks: TimerUICallbacks;
  private readonly readSeconds: () => number;
  private readonly display: HTMLElement;
  private readonly startButton: HTMLButtonElement;
  private readonly pauseButton: HTMLButtonElement;
  private readonly resetButton: HTMLButtonElement;
  private readonly errorSlot: HTMLElement;

  constructor(container: HTMLElement, options: TimerUIOptions) {
    if (!container) {
      throw new TypeError('TimerUI requires a container element.');
    }
    this.container = container;
    this.callbacks = options;
    this.readSeconds = options.readSeconds ?? (() => 60);

    this.display = document.createElement('div');
    this.display.className = 'timer-display';
    this.display.textContent = '00:00';

    this.errorSlot = document.createElement('div');
    this.errorSlot.className = 'timer-error';
    this.errorSlot.hidden = true;

    this.startButton = document.createElement('button');
    this.startButton.className = 'timer-start';
    this.startButton.textContent = 'Start';
    this.startButton.addEventListener('click', () => this.handleStart());

    this.pauseButton = document.createElement('button');
    this.pauseButton.className = 'timer-pause';
    this.pauseButton.textContent = 'Pause';
    this.pauseButton.addEventListener('click', () => this.callbacks.onPause());

    this.resetButton = document.createElement('button');
    this.resetButton.className = 'timer-reset';
    this.resetButton.textContent = 'Reset';
    this.resetButton.addEventListener('click', () => this.callbacks.onReset());

    container.appendChild(this.display);
    container.appendChild(this.errorSlot);
    container.appendChild(this.startButton);
    container.appendChild(this.pauseButton);
    container.appendChild(this.resetButton);
  }

  setTime(totalSeconds: number): void {
    const clamped = Math.max(0, Math.floor(totalSeconds));
    const minutes = String(Math.floor(clamped / 60)).padStart(2, '0');
    const seconds = String(clamped % 60).padStart(2, '0');
    this.display.textContent = `${minutes}:${seconds}`;
  }

  private handleStart(): void {
    try {
      const seconds = this.readSeconds();
      this.callbacks.onStart(seconds);
      this.errorSlot.hidden = true;
    } catch (err) {
      this.showError(err instanceof Error ? err.message : String(err));
    }
  }

  private showError(message: string): void {
    this.errorSlot.textContent = message;
    this.errorSlot.hidden = false;
  }
}
""",
    ),
]

# ── Sweep helpers ────────────────────────────────────────────────────────

IMPORT_LINE_RE = re.compile(r"^\s*import\b.*$", re.M)
SIDE_EFFECT_IMPORT_RE = re.compile(r"^\s*import\s+['\"]", re.M)
SUBSTANTIVE_IMPORT_RE = re.compile(
    r"^\s*import\s+([^'\";]+?)\s+from\s+['\"]([^'\"]+)['\"]", re.M
)
EXPORT_DEFAULT_LINE_RE = re.compile(r"^\s*export\s+default\s+(\w+)\s*;\s*$", re.M)
EXPORT_DEFAULT_INLINE_RE = re.compile(
    r"^\s*export\s+default\s+(class|function|abstract\s+class|interface)\s+(\w+)", re.M
)
EXPORT_DEFAULT_ANON_RE = re.compile(
    r"^\s*export\s+default\s+(?:abstract\s+)?(class|function)\s*[({]", re.M
)
EXPORT_DECL_RE = re.compile(
    r"^\s*export\s+(?:(abstract\s+)?(class|function|const|let|var|interface|type|enum|namespace))\s+(\w+)",
    re.M,
)
EXPORT_NAMED_BLOCK_RE = re.compile(r"^\s*export\s*\{.*?\}\s*;", re.M | re.S)
EXPORT_STAR_RE = re.compile(r"^\s*export\s+\*\s+from\s+.*$", re.M)
NODEJS_RE = re.compile(r"\bNodeJS\.(\w+)")

SEED_NODES = {node for node, _ in EXAMPLES}


def node_app_from_instruction(instruction: str):
    node = re.search(r"node '([^']+)'", instruction)
    app = re.search(r"in the '([^']+)' app", instruction)
    return (node.group(1) if node else None, app.group(1) if app else None)


def pascal_node(node: str) -> str:
    """'category-filter' -> 'CategoryFilter' (for naming anonymous default exports)."""
    return "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", node) if part)


def parse_import_bindings(line: str):
    """Return (bindings:list[str], side_effect:bool) for one import line."""
    m = SUBSTANTIVE_IMPORT_RE.search(line)
    if not m:
        return [], bool(SIDE_EFFECT_IMPORT_RE.search(line))
    clause = m.group(1).strip()
    bindings = []
    if clause.startswith("{"):
        inner = clause[1 : clause.rfind("}")] if "}" in clause else clause
        for part in inner.split(","):
            part = part.strip()
            if not part:
                continue
            if " as " in part:
                part = part.split(" as ")[-1].strip()
            bindings.append(part)
    elif clause.startswith("*"):
        ns = re.search(r"\*\s*as\s+(\w+)", clause)
        if ns:
            bindings.append(ns.group(1))
    else:
        bindings.append(clause.split(",")[0].strip())
    return bindings, False


def slugify(s: str) -> str:
    """kebab-case slug for matching app dir names (e.g. 'Countdown Timer' -> 'countdown-timer')."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def find_sibling_file(app: str, import_spec: str):
    """Resolve a relative import like ../x/x.ts against the app's node tree."""
    # import_spec is relative to the importing node's dir (e.g. ../task-store/task-store.ts)
    # We can't know the importing node's exact dir from the instruction alone, so we search
    # the app tree for a file matching the import's basename.
    if not app:
        return None
    target = os.path.basename(import_spec)
    base = os.path.join(REF_ROOT, slugify(app))
    if not os.path.isdir(base):
        # try a fuzzy match on the app dir
        cands = [d for d in os.listdir(REF_ROOT) if slugify(app) in slugify(d)]
        base = os.path.join(REF_ROOT, cands[0]) if cands else None
    if not base or not os.path.isdir(base):
        return None
    matches = []
    for dirpath, _, files in os.walk(base):
        if target in files:
            matches.append(os.path.join(dirpath, target))
    if len(matches) == 1:
        return matches[0]
    # prefer the sibling whose dir name matches the import's parent dir
    parent = os.path.basename(os.path.dirname(import_spec))
    for m in matches:
        if os.path.basename(os.path.dirname(m)) == parent:
            return m
    return matches[0] if matches else None


def strip_imports(code: str):
    """Remove all import lines. Return (code, removed:list[str])."""
    removed = []
    lines = code.split("\n")
    kept = []
    for line in lines:
        if re.match(r"^\s*import\b", line):
            removed.append(line.strip())
        else:
            kept.append(line)
    return "\n".join(kept), removed


def convert_default_exports(code: str, fallback_name: str = "DefaultExport"):
    """Convert export default -> named export. Return (code, actions:list[str])."""
    actions = []
    # collect trailing default names BEFORE mutating the source
    trailing = [m.group(1) for m in EXPORT_DEFAULT_LINE_RE.finditer(code)]

    # inline forms: export default class Name { / export default function Name(
    def _inline(m):
        kw = " ".join(m.group(1).split())  # normalize 'abstract  class'
        actions.append(f"default inline -> export {kw} {m.group(2)}")
        return f"export {kw} {m.group(2)}"

    code, n = EXPORT_DEFAULT_INLINE_RE.subn(_inline, code)
    if n:
        actions.append(f"({n} inline defaults converted)")

    # trailing forms: export default Name;  ->  drop the line, export the declaration
    code, n = EXPORT_DEFAULT_LINE_RE.subn("", code)
    if n:
        for name in trailing:
            code, n2 = exportify_declaration(code, name)
            if n2:
                actions.append(f"default {name} -> named export on declaration")
            else:
                actions.append(f"default {name}: declaration not found (anonymous?)")

    # anonymous forms (export default class { ... }) — name them from the node name
    def _name_anon(m):
        kw = m.group(1)
        actions.append(f"anon default {kw} -> export {kw} {fallback_name}")
        return f"export {kw} {fallback_name}"

    code, n = EXPORT_DEFAULT_ANON_RE.subn(_name_anon, code)
    if n:
        actions.append(f"({n} anonymous defaults named from node)")
    return code, actions


def exportify_declaration(code: str, name: str):
    """Ensure the declaration of `name` carries `export` (for default->named)."""
    pat = re.compile(
        r"^(\s*)((?:abstract\s+)?(?:class|function|const|let|var|interface|type|enum))\s+"
        + re.escape(name)
        + r"\b",
        re.M,
    )
    code, n = pat.subn(lambda m: f"{m.group(1)}export {m.group(2)} {name}", code, count=1)
    return code, n


def fix_nodejs(code: str):
    """Replace NodeJS.* with browser-native types. Return (code, n_replaced)."""
    def _repl(m):
        return "number" if m.group(1) == "Timeout" else m.group(0)

    code, n = NODEJS_RE.subn(_repl, code)
    return code, n


def inline_sibling_exports(code: str, app: str, used_imports: list):
    """Best-effort depth-1 inline of used sibling imports.
    Returns (code, actions:list[str], ok:bool)."""
    actions = []
    out_parts = [code]
    ok = True
    for line in used_imports:
        m = SUBSTANTIVE_IMPORT_RE.search(line)
        if not m:
            continue
        bindings, _ = parse_import_bindings(line)
        import_spec = m.group(2)
        sibling = find_sibling_file(app, import_spec)
        if not sibling:
            actions.append(f"NO-REF {import_spec}")
            ok = False
            continue
        try:
            with open(sibling, encoding="utf-8") as f:
                sib_code = f.read()
        except OSError:
            actions.append(f"READ-FAIL {import_spec}")
            ok = False
            continue
        # strip sibling imports (depth-1), export keywords, default lines
        sib_code, _ = strip_imports(sib_code)
        sib_code = EXPORT_NAMED_BLOCK_RE.sub("", sib_code)
        sib_code = EXPORT_STAR_RE.sub("", sib_code)
        sib_code, _ = EXPORT_DEFAULT_LINE_RE.subn("", sib_code)
        sib_code, _ = EXPORT_DEFAULT_INLINE_RE.subn(r"\1 \2", sib_code)
        sib_code = EXPORT_DECL_RE.sub(r"\1\2 \3", sib_code)
        sib_code = sib_code.strip()
        # only inline if the binding's symbol is actually declared inside
        inline_needed = any(re.search(rf"\b{b}\b", sib_code) for b in bindings)
        if not inline_needed:
            actions.append(f"SYMBOL-NOT-FOUND {import_spec}")
            ok = False
            continue
        actions.append(f"INLINE {import_spec} [{', '.join(bindings)}]")
        out_parts.append(f"\n// ── inlined from {import_spec} (self-contained) ──")
        out_parts.append(sib_code)
    return "\n".join(out_parts), actions, ok


def gate_pass(code: str):
    """Tightened A/B gate: analyze + tsc_check."""
    a = ab.analyze(code)
    tsc = ab.tsc_check(code)
    flags = []
    if a["imports"] > 0:
        flags.append("SUBST-IMPORT")
    if a["side_effect_imports"] > 0:
        flags.append("SIDE-EFFECT-IMPORT")
    if a["default_export"]:
        flags.append("DEFAULT-EXPORT")
    if a["jsx_in_ts"]:
        flags.append("JSX")
    if a["stub"]:
        flags.append("STUB")
    if a["prose"]:
        flags.append("PROSE")
    if a["named_exports"] == 0:
        flags.append("NO-EXPORT")
    if not tsc.startswith("PASS"):
        flags.append("TSC")
    return len(flags) == 0, flags, tsc[:80]


def swept_instruction(node: str, app: str):
    return INSTRUCTION.format(node=node).replace("'Countdown Timer' app", f"'{app}' app")


def sweep_campaign_rows():
    """Transform flagged campaign rows; return (passing_rows, report)."""
    if not os.path.isfile(CAMPAIGN):
        print(f"⚠️  {CAMPAIGN} missing — sweep skipped.")
        return [], []

    rows = []
    for line in open(CAMPAIGN, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    passing = []
    report = []
    skipped_seed = 0
    for r in rows:
        node, app = node_app_from_instruction(r.get("instruction", ""))
        if not node:
            continue
        if node in SEED_NODES:
            skipped_seed += 1
            continue  # hand-written seed already covers this node
        out = r.get("output", "")
        a0 = ab.analyze(out)
        needs_fix = a0["imports"] > 0 or a0["side_effect_imports"] > 0 or a0["default_export"]
        if not needs_fix:
            report.append(
                {
                    "node": node,
                    "app": app,
                    "status": "already-clean",
                    "actions": [],
                    "flags": [],
                    "tsc": "",
                }
            )
            continue

        # ── transform pipeline ──
        actions = []
        code, removed = strip_imports(out)
        body_no_imports = code  # all import lines already removed

        # classify each removed import: side-effect / unused -> dropped; used -> inline
        used_imports = []
        for imp in removed:
            bindings, is_side = parse_import_bindings(imp)
            if is_side:
                actions.append(f"strip side-effect {imp.strip()}")
            elif not bindings:
                actions.append(f"strip ambiguous {imp.strip()}")
            else:
                used = [b for b in bindings if re.search(rf"\b{b}\b", body_no_imports)]
                if used:
                    actions.append(f"used import {imp.strip()} -> inline sibling (used: {used})")
                    used_imports.append(imp)
                else:
                    actions.append(f"strip unused {imp.strip()}")

        if used_imports:
            code, actions2, _ok = inline_sibling_exports(code, app, used_imports)
        else:
            actions2 = []
        actions.extend(actions2)

        code, n_node = fix_nodejs(code)
        if n_node:
            actions.append(f"NodeJS.* -> number ({n_node})")

        # default exports -> named (anonymous defaults named from the node name)
        code, actions3 = convert_default_exports(code, fallback_name=pascal_node(node))
        actions.extend(actions3)

        passed, flags, tsc = gate_pass(code)
        if passed:
            passing.append({"input": "", "instruction": swept_instruction(node, app), "output": code})
            status = "passed"
        else:
            status = "needs-hand-write"
        report.append(
            {
                "node": node,
                "app": app,
                "status": status,
                "actions": actions,
                "flags": flags,
                "tsc": tsc,
            }
        )

    return passing, report


def validate_output(node: str, output: str) -> None:
    """Fail loudly if a hand-written example violates the contract we are teaching."""
    if re.search(r"^\s*import\b", output, re.M):
        raise SystemExit(f"❌ {node}: output contains an import - self-contained required.")
    if re.search(r"\bexport\s+default\b", output):
        raise SystemExit(f"❌ {node}: output contains export default - named exports only.")
    if re.search(r"<[A-Za-z][^>]*\s", output):  # crude JSX/open-tag-with-attrs check
        raise SystemExit(f"❌ {node}: output looks like it contains JSX.")
    if re.search(r"```|^#{1,6}\s", output, re.M):
        raise SystemExit(f"❌ {node}: output contains markdown fences/headings.")


def main() -> None:
    # 1. hand-written seeds
    seed_rows = []
    for node, output in EXAMPLES:
        validate_output(node, output)
        seed_rows.append({"input": "", "instruction": INSTRUCTION.format(node=node), "output": output})

    # 2. mechanical sweep of flagged campaign rows
    swept_rows, report = sweep_campaign_rows()

    all_rows = seed_rows + swept_rows
    # dedupe on (instruction, output) — sweep may re-produce a seed node via another app
    seen = set()
    deduped = []
    for r in all_rows:
        k = (r["instruction"], r["output"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)

    # Full A/B gate (analyze + tsc_check) runs BY DEFAULT on EVERY row
    # (incl. hand-written seeds, which otherwise only get the regex
    # validate_output) BEFORE writing — a row that fails must never ship.
    # --no-validate-tsc opts out for fast iterations during hand-write batches.
    if "--no-validate-tsc" not in sys.argv:
        failures = []
        for r in deduped:
            node = re.search(r"node '([^']+)'", r.get("instruction", ""))
            label = node.group(1) if node else "(unknown)"
            passed, flags, tsc = gate_pass(r["output"])
            if passed:
                print(f"   ✓ {label:28s} gate PASS")
            else:
                print(f"   ✗ {label:28s} flags={flags} tsc={tsc}")
                failures.append(label)
        if failures:
            raise SystemExit(
                f"❌ gate: {len(failures)} row(s) FAILED analyze + tsc_check "
                f"({failures}) — fix the outputs; nothing was written."
            )
        print(f"   ✅ gate: all {len(deduped)} rows pass analyze + tsc_check")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in deduped:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # sweep report
    if report:
        with open(SWEEP_REPORT, "w", encoding="utf-8") as f:
            json.dump({"rows": report}, f, ensure_ascii=False, indent=2)

    n_passed = sum(1 for rr in report if rr["status"] == "passed")
    n_hand = sum(1 for rr in report if rr["status"] == "needs-hand-write")
    n_clean = sum(1 for rr in report if rr["status"] == "already-clean")
    print(f"✅ Wrote {OUT}")
    print(f"   seeds: {len(seed_rows)} | swept-passed: {len(swept_rows)} | total rows: {len(deduped)}")
    print(f"   sweep report: {n_passed} passed, {n_hand} needs-hand-write, {n_clean} already-clean")
    if n_hand:
        print("   hand-write backlog (first 12):")
        for rr in [r for r in report if r["status"] == "needs-hand-write"][:12]:
            print(f"     - {rr['node']:28s} flags={rr['flags']} tsc={rr['tsc']}")
    print("   Next: python3 scripts/merge-campaign50-into-dataset.py")


if __name__ == "__main__":
    main()
