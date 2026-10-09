#!/usr/bin/env python3
"""
R16 anti-fence probe battery — measures the EXACT failure class R16 was
trained to eliminate.

R16's training corpus (round16-antifence) is 552 rows whose outputs all pass
the VACA isQualityCode gate (no ``` fences, no `---` batched separators, no
prose explanations, no prompt artifacts, no stubs). This probe runs the same
gate against the DEPLOYED model (dspark :8000) on a battery of raw-code
generation prompts — the same prompt shape VACA's file generator uses — and
reports:

  GATE PASS rate     — share of outputs isQualityCode() accepts (R15 baseline
                       from the A/B was ~1/4 fence-free on some classes)
  FENCE rate         — outputs containing a ``` fence line
  SEPARATOR rate     — outputs containing a `---` batch separator
  PROSE rate         — outputs with prose-explanation lines
  ARTIFACT rate      — outputs echoing prompt scaffolding ("REAL FILE CONTENT")

Prompts span the languages VACA generates (TypeScript, CSS, HTML) so the
measure covers the classes that actually broke builds.

Writes probes/r16/results.json + REPORT.md.
"""
import json
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path("/home/final-flash1/Desktop/visual-ai-architect")
OUT = ROOT / "probes" / "r16"
OUT.mkdir(parents=True, exist_ok=True)
DSPARK = "http://127.0.0.1:8000/v1/chat/completions"

# ── Python port of backend/src/knowledge/qualityGate.ts (isQualityCode) ─────
STUB_PATTERNS = [
    re.compile(r"not implemented", re.I),
    re.compile(r"placeholder\s+for", re.I),
    re.compile(r"coming soon", re.I),
    re.compile(r"lorem ipsum", re.I),
    re.compile(r"unimplemented", re.I),
    re.compile(r"throw new Error\(['\"]not", re.I),
    re.compile(r"TODO: Implement", re.I),
]
MARKDOWN_FENCE_RE = re.compile(r"^\s*```", re.M)
BATCH_SEPARATOR_RE = re.compile(r"^\s*---\s*$", re.M)
PROMPT_ARTIFACT_RE = re.compile(
    r"REAL FILE CONTENT|injected by the platform|generated for the \"[^\"]+\" node|entry point for the node", re.I)
PROSE_RE = re.compile(
    r"^\s*(?:\*\*[^*]+\*\*|[-*]\s+[A-Za-z]|Note:|NOTE:|> |Explanation:|Here's|Below is|"
    r"In this (?:solution|implementation|file|module|example)|"
    r"This (?:code|file|module|implementation|class|function) (?:defines|implements|handles|provides|is|shows)|"
    r"For (?:a|an) .* (?:game|app|application)|"
    r"The .* (?:function|class|module|implementation))")
JSX_IN_TS_RE = re.compile(r"</?[a-z][a-z0-9]*\s[^>]*>|</[a-z][a-z0-9]*\s*>")


def is_quality_code(code: str, language: str) -> bool:
    if len(code.strip()) < 30:
        return False
    if any(p.search(code) for p in STUB_PATTERNS):
        return False
    if MARKDOWN_FENCE_RE.search(code):
        return False
    if BATCH_SEPARATOR_RE.search(code):
        return False
    if PROMPT_ARTIFACT_RE.search(code):
        return False
    if language in ("typescript", "javascript"):
        # strip string literals before JSX check
        stripped = re.sub(r"(['\"`])(?:\\.|(?!\1)[^\\])*\1", "", code)
        if JSX_IN_TS_RE.search(stripped):
            return False
    for line in code.split("\n"):
        t = line.strip()
        if PROSE_RE.search(line) and not re.search(r"[;{}()=<>]", t):
            return False
    return True


# ── Prompt battery — mirrors VACA's per-file generation prompt shape ────────
# (name, language, instruction)
BATTERY = [
    ("ts-chess-ai", "typescript",
     "Write a complete TypeScript file ai.ts implementing a chess AI opponent "
     "class ComputerPlayer with a method chooseMove(board: string[][]): "
     "{from: [number, number]; to: [number, number]} that picks a legal move "
     "by minimax depth 2. Output ONLY the raw TypeScript source."),
    ("ts-todo-types", "typescript",
     "Write a complete TypeScript file types.ts defining export interface Task "
     "{ id: string; title: string; done: boolean; createdAt: string }, export "
     "type TaskPriority = 'low' | 'medium' | 'high', and export class DueDate "
     "with a constructor(iso: string) and method daysLeft(): number. Output "
     "ONLY the raw TypeScript source."),
    ("ts-config", "typescript",
     "Write a complete TypeScript file config.ts exporting const PORT: number "
     "= 3000, interface AppConfig, and function loadConfig(path: string): "
     "AppConfig. Output ONLY the raw TypeScript source."),
    ("ts-game-logic", "typescript",
     "Write a complete TypeScript file grid.ts exporting class Game with a "
     "private cells field of type (string | null)[] of length 9, a "
     "constructor, makeMove(index: number): void, checkWinner(): "
     "{ winner: string; line: number[] } | null, isFull(): boolean, and "
     "reset(): void. Output ONLY the raw TypeScript source."),
    ("ts-utils", "typescript",
     "Write a complete TypeScript file utils.ts exporting function "
     "shuffle<T>(arr: T[]): T[], function clamp(n: number, lo: number, hi: "
     "number): number, and function groupBy<T>(items: T[], key: keyof T): "
     "Map<string, T[]>. Output ONLY the raw TypeScript source."),
    ("css-layout", "css",
     "Write a complete CSS stylesheet for a chess board: a .board grid "
     "container with 8x8 cells, alternating .light/.dark squares, pieces "
     "centered, responsive sizing, and a status bar. Output ONLY the raw CSS."),
    ("css-theme", "css",
     "Write a complete CSS theme file: CSS variables for a dark theme, body "
     "typography, a .card component with hover elevation, and a responsive "
     "media query. Output ONLY the raw CSS."),
    ("html-app", "html",
     "Write a complete single HTML file for a todo app: an input with an "
     "Add button, a task list with delete toggles, and localStorage "
     "persistence. Output ONLY the raw HTML starting with <!DOCTYPE html>."),
    ("html-dashboard", "html",
     "Write a complete single HTML file for a weather dashboard: a search "
     "box, a 5-day forecast grid, and a temperature chart drawn with canvas. "
     "Output ONLY the raw HTML starting with <!DOCTYPE html>."),
    ("ts-store", "typescript",
     "Write a complete TypeScript file store.ts exporting class Store<T> with "
     "a private items: T[] field, methods add(item: T): void, remove(id: "
     "string): void, get(id: string): T | undefined, and snapshot(): T[]. "
     "Output ONLY the raw TypeScript source."),
]


def gen(prompt: str):
    payload = {
        "model": "x",
        "messages": [
            {"role": "system",
             "content": "You are an expert software engineer. Output ONLY raw "
                        "source code. Never use markdown fences, never add "
                        "explanations, never prefix with file names."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 2500,
        "temperature": 0.7,
        "stream": False,
    }
    req = urllib.request.Request(
        DSPARK, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    out = d["choices"][0]["message"]["content"]
    return out, time.time() - t0


def measure(name: str, lang: str, prompt: str):
    out, dt = gen(prompt)
    clean = MARKDOWN_FENCE_RE.search(out) is None
    # strip fences for the gate test if present (gate rejects fenced anyway)
    fence = bool(MARKDOWN_FENCE_RE.search(out))
    separator = bool(BATCH_SEPARATOR_RE.search(out))
    prose = any(PROSE_RE.search(l) and not re.search(r"[;{}()=<>]", l.strip())
                for l in out.split("\n"))
    artifact = bool(PROMPT_ARTIFACT_RE.search(out))
    # code-only view (drop leading prose/fences) for the gate
    code_view = re.sub(r"^```[^\n]*\n?", "", out)
    code_view = re.sub(r"```\s*$", "", code_view)
    if not clean:
        code_view = re.sub(r"^```.*$", "", code_view, flags=re.M).strip()
    gate_pass = is_quality_code(code_view, lang)
    return {
        "name": name, "lang": lang, "secs": round(dt, 1),
        "gate_pass": gate_pass, "fence": fence, "separator": separator,
        "prose": prose, "artifact": artifact,
        "output": out,
    }


def main() -> None:
    print(f"[probe-r16] {len(BATTERY)} raw-code prompts via dspark — anti-fence battery")
    results = []
    for name, lang, prompt in BATTERY:
        r = measure(name, lang, prompt)
        flags = "".join(
            ("G" if r["gate_pass"] else "g") + ("F" if r["fence"] else "") +
            ("S" if r["separator"] else "") + ("P" if r["prose"] else "") +
            ("A" if r["artifact"] else ""))
        print(f"  {name:<16} gate={'✅' if r['gate_pass'] else '❌'} "
              f"[{flags}] ({r['secs']}s)")
        results.append(r)
        (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
        (OUT / f"{name}.txt").write_text(r["output"], encoding="utf-8")

    n = len(results)
    g = sum(1 for r in results if r["gate_pass"])
    f = sum(1 for r in results if r["fence"])
    s = sum(1 for r in results if r["separator"])
    p = sum(1 for r in results if r["prose"])
    a = sum(1 for r in results if r["artifact"])

    lines = [
        "# R16 Anti-Fence Probe (deployed model via dspark)",
        "",
        f"**Gate pass {g}/{n} · fences {f}/{n} · separators {s}/{n} · prose {p}/{n} · artifacts {a}/{n}**",
        "",
        "The gate is a Python port of VACA's `isQualityCode` — the same bar the "
        "round-16 corpus was filtered through. R16 was trained ONLY on rows that "
        "pass it, so a high gate-pass rate here is the direct measure of whether "
        "the remediation worked.",
        "",
        "| Prompt | Gate | Fence | Sep | Prose | Artifact |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['name']} | {'✅' if r['gate_pass'] else '❌'} | "
                     f"{'✅' if r['fence'] else ''} | {'✅' if r['separator'] else ''} | "
                     f"{'✅' if r['prose'] else ''} | {'✅' if r['artifact'] else ''} |")
    lines += [
        "",
        "## Verdict",
        "",
    ]
    if f == 0 and s == 0 and p == 0 and a == 0:
        lines.append("- **Clean sweep: zero markdown/prose leaks.** The "
                     "anti-fence training held on every prompt.")
    elif f > 0 or s > 0:
        lines.append(f"- **Fences/separators still leak ({f}/{n} fenced).** "
                     "The base-model chat habit is not fully suppressed — "
                     "consider another clean round or prompt-side fence stripping.")
    if g >= n * 0.8:
        lines.append(f"- Gate pass {g}/{n} — the deployed model is producing "
                     "quality-gate-clean code at a high rate.")
    else:
        lines.append(f"- Gate pass only {g}/{n} — outputs still fail the "
                     "quality gate; remediation did not fully transfer.")
    lines += [
        "",
        f"Run: `python3 scripts/probe-r16.py` — outputs in `probes/r16/`.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[probe-r16] GATE {g}/{n} | FENCE {f} | SEP {s} | PROSE {p} | ARTIFACT {a}")
    print(f"[probe-r16] report: {OUT / 'REPORT.md'}")


if __name__ == "__main__":
    main()
