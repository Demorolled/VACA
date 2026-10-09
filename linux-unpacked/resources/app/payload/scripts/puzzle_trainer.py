#!/usr/bin/env python3
"""
puzzle_trainer.py — VACA Puzzle-RAG Trainer (trains the Qwen 14B by playing)
============================================================================
Turns the VACA exports library into a puzzle game that TRAINS the served 14B:

  1. CHUNK  : parse every exports/<app>/index.html into semantic NODES
              (each JS function, each CSS rule, the HTML layout block) and
              classify each node's PURPOSE (Database / UI-render / Game-logic /
              Event-handler / State / Styling / Layout / Input / Output / Util).
  2. FAKE   : for every puzzle, build 2 fake nodes:
                (a) a subtle MUTATION of the correct chunk (swapped comparison,
                    off-by-one bound, wrong API, inverted boolean) and
                (b) a REAL same-purpose chunk taken from a DIFFERENT app.
  3. RAG    : retrieve same-purpose reference chunks from OTHER apps in the
              library and inject them as reference context (mirrors VACA's
              libraryContext) — the model plays in retrieval-augmented mode.
  4. PLAY   : show the app goal + node purpose + reference + 3 nodes A/B/C.
              The model replies "NODE: X".  Correct = +REWARD.correct,
              wrong = REWARD.wrong.  Completing every node of an app ends the
              puzzle -> +REWARD.puzzle_complete.  Beating the previous best
              round time -> +REWARD.speed_bonus.
  5. LEARN  : every episode is logged to episodes.jsonl and baked into
              reward-scored training rows:
                * train-puzzle-rNN.jsonl   (SFT)  — goal+purpose+reference
                                                    -> the CORRECT chunk code
                * dpo-puzzle-rNN.jsonl     (DPO)  — from WRONG picks:
                                                    chosen=correct, rejected=what
                                                    the model actually chose
              -> feeds the next QLoRA round exactly like your R-round pipeline.

Usage:
  python3 scripts/puzzle_trainer.py --rounds 3 --llm-url http://127.0.0.1:8002
  python3 scripts/puzzle_trainer.py --self-test          # no LLM, verify puzzles
  python3 scripts/puzzle_trainer.py --status-port 8300   # live watch page

Everything is stdlib-only (urllib for the OpenAI-compatible call).
"""
import argparse
import json
import random
import re
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────
EXPORTS_DIR = Path(__file__).resolve().parent.parent / "backend" / "exports"
OUT_DIR = Path(__file__).resolve().parent.parent / "training" / "cloud" / "puzzle-r30"

# ⚠ OUT_DIR is a mutable module global — main() sets it from --out-dir so two
#   trainer sessions (R20 + R28) can run in parallel without sharing files.

DEFAULT_LLM_URL = "http://127.0.0.1:8002/v1/chat/completions"
DEFAULT_MODEL = "qwen2.5-coder-14b-uncensored-dspark"
# Semantic RAG: reference chunks are ranked by embedding similarity to the app
# request using the Ollama embed model (nomic-embed-text).  --embed-url should
# point at the same Ollama as --llm-url; empty disables it (keyword ranking).
EMBED_MODEL = "nomic-embed-text"
EMBED_URL = ""          # set by main() from --embed-url
EMBED_BATCH = 64
EMBED_TIMEOUT = 30

REWARDS = {
    "correct": 10,
    "wrong": -5,
    "puzzle_complete": 50,
    "speed_bonus": 25,
    "optimize": 15,        # tune-up produced a valid, leaner node
    "optimize_bad": -10,   # tune-up broke the node (invalid / lost behavior)
    "optimize_keep": 0,    # refused to attempt (KEEP) — no free lunch
    "rebuild_ok": 100,     # whole-app REBUILD from memory matched the design
    "rebuild_bad": -30,    # rebuilt app lost structure / didn't match
}

REBUILD_SIM_OK = 0.60      # similarity floor for a whole-app rebuild (+100)
REBUILD_MAX_NODES = 3      # only small apps get a REBUILD finale (token budget)
REBUILD_MAX_CHARS = 2400   # assembled-app cap: keeps the SFT row under MAX_SEQ

NODE_PURPOSES = [
    ("database", [
        "localstorage", "indexeddb", "fetch(", "axios", "sql", "insert", "select ",
        "query", "save(", "load(", "store", "api/", "json.parse", "json.stringify",
        "sessionstorage", "database", "db.", "endpoint", "request("]),
    ("ui-render", [
        "render", "createelement", "innerhtml", "appendchild", "draw", "paint",
        "template", "textcontent", "createtextnode", "display", "updatelist",
        "populate", "buildui"]),
    ("game-logic", [
        "board", "move", "turn", "score", "game", "tick", "collision", "player",
        "piece", "level", "enemy", "roll", "dice", "guess", "win", "lose",
        "checkers", "chess", "grid", "spawn", "velocity"]),
    ("event-handler", [
        "addeventlistener", "onclick", "onchange", "oninput", "onkeydown",
        "onkeyup", "onsubmit", "handle", "click", "keydown", "submit", "mousedown",
        "mouseup", "change", "input"]),
    ("state", [
        "state", "usestate", "reducer", "setstate", "state =", "let ", "var ",
        "store", "dispatch", "currentstate", "history", "undo", "redo"]),
    ("styling", [
        "background", "color:", "display:flex", "margin", "padding", "border",
        "font-", "width:", "height:", "position:", "border-radius", "box-shadow",
        "z-index", "cursor:", "align-items", "justify-content"]),
    ("layout", [
        "<div", "<section", "<header", "<nav", "<main", "<footer", "id=", "class=",
        "<canvas", "<table", "<form", "<button", "<input", "<ul", "<ol", "<li"]),
    ("input", [
        "prompt(", "readline", "process.argv", "args[", "getvalue", ".value",
        "stdin", "getinput", "parameters", "argv"]),
    ("output", [
        "print(", "console.log", "return", "stdout", "write(", "log(",
        "displayresult", "showresult", "output"]),
    ("utility", [
        "function ", "helper", "util", "format", "parse", "convert", "validate",
        "random", "math.", "sort", "filter", "map(", "reduce", "reverse",
        "tostring", "trim", "split("]),
    ("animations", [
        "@keyframes", "animation", "transition", "transform", "translate",
        "rotate(", "scale(", "requestanimationframe", "ease-in", "ease-out",
        "ease-in-out", "cubic-bezier", "steps(", "0%{", "100%{"]),
    ("canvas-rendering", [
        "getcontext", "ctx.", "fillstyle", "strokestyle", "beginpath",
        "fillrect", "drawimage", "createlineargradient", "requestanimationframe",
        "canvas.width", "canvas.height", "clearrect", "arc(", "2d"]),
]

PURPOSE_LABELS = {
    "database": "Database node",
    "ui-render": "UI render node",
    "game-logic": "Game logic node",
    "event-handler": "Event handler node",
    "state": "State management node",
    "styling": "Styling node",
    "layout": "Layout node",
    "input": "Input node",
    "output": "Output node",
    "utility": "Utility node",
    "animations": "Animation node",
    "canvas-rendering": "Canvas rendering node",
}

MAX_CHUNK = 1600          # trim chunks above this (chars) so prompts stay sane
MIN_CHUNK = 30            # drop trivial chunks

# Serve-time fake quality (Fix: near-duplicate fakes are unanswerable).
# chunk_similarity(correct, fake) above this cap means the two are practically
# identical (one hex digit, one declaration) — a coin flip, not a puzzle.
# The cap applies ONLY at serve time in the game below the extreme tier;
# corpus builder + eval keep uncapped near-dupe fakes as fine-grained
# discrimination TRAINING rows.
FAKE_SIM_CAP = 0.90
FAKE_SIM_TRIES = 8        # retries to find an acceptable mutation fake
FAKE_SIM_SAMPLE = 20      # rejection-sample window for cross-app fakes

# Tiny-chunk merging (Fix: 50-160 char CSS rules give nothing to discriminate).
# Consecutive same-purpose chunks below MERGE_TINY chars are combined into one
# real section (~MERGE_TARGET chars) so picks have actual context.  Big chunks
# are left untouched.
MERGE_TINY = 220          # chunks shorter than this are merge candidates
MERGE_TARGET = 400        # keep merging until the section is about this size
MERGE_MAX = 900           # never merge past this combined size

# ── Game rules ──────────────────────────────────────────────────────────────
# GAME_RULES.md is the single source of truth for how the game is played
# (stages, reply formats, scoring, fakes).  It lives next to the standalone
# app; the trainer loads it once and injects a compact summary into every
# system prompt so the model always knows what the game is and does.
# The rules file ships with the standalone app (puzzle-rag-trainer/) but the
# repo copy of this script lives one level up — try both.
RULES_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "GAME_RULES.md",
    Path(__file__).resolve().parent.parent / "puzzle-rag-trainer" / "GAME_RULES.md",
]
RULES_TEXT = ""
_RULES_SUMMARY = ""


def load_rules():
    """Read GAME_RULES.md into RULES_TEXT and build a compact summary for the
    system prompt (the full file is too long for MAX_SEQ=1024 training rows)."""
    global RULES_TEXT, _RULES_SUMMARY
    for cand in RULES_CANDIDATES:
        try:
            if cand.exists():
                RULES_TEXT = cand.read_text(encoding="utf-8", errors="ignore").strip()
                break
        except Exception:
            continue
    if not RULES_TEXT:
        RULES_TEXT = ""
    if RULES_TEXT:
        _RULES_SUMMARY = (
            "GAME RULES (read the full GAME_RULES.md for details):\n"
            "1) OBSERVE: the whole app is shown once — acknowledge with OK.\n"
            "2) SLICE: the app is divided into sections (nodes).\n"
            "3) PICK: for a section you get THREE candidate chunks; exactly ONE "
            "is correct for that purpose in THIS app, the other two are fakes "
            "(buggy mutations or code from a different app). Reply: NODE: X\n"
            "4) RECREATE: after a correct pick, write back the missing code. "
            "Reply: NODE: X then CODE: <the missing code>.\n"
            "5) OPTIMIZE: final test — rewrite the solved node to be smaller, "
            "faster, more efficient (same behavior, same identifiers). "
            "Reply: OPTIMIZE: <the improved code>\n"
        )
    return _RULES_SUMMARY


load_rules()

SYS_PROMPT = (
    "You are a Visual AI Architect puzzle player. You are constructing a web "
    "app one section at a time.\n\n"
    + (_RULES_SUMMARY if _RULES_SUMMARY else (
        "You are given an app goal, a node purpose, reference patterns, and "
        "THREE candidate code nodes. Exactly ONE is the correct implementation "
        "for that purpose in THIS app; the other two are fakes (buggy "
        "mutations or code from a different app). Reply with only the line: "
        "NODE: X  where X is A, B, or C."))
)

OPTIMIZER_SYS = (
    "You are a code performance coach inside a puzzle game. You are given ONE "
    "correct node from an app under construction. You MUST rewrite it to be "
    "BOTH faster AND smaller — each improvement is rewarded separately, so "
    "achieving both pays double.  Faster = fewer expensive operations (hoist "
    "repeated DOM lookups out of loops, fuse loops, cut redundant work).  "
    "Smaller = fewer characters (drop boilerplate, minify CSS, tighten names "
    "without renaming public identifiers).  Keep its exact behavior and every "
    "public identifier (function names, DOM ids, class names, event targets, "
    "API endpoints).  Keeping the code as-is is NOT allowed — always output a "
    "rewritten version. Reply with exactly:"
    "\nOPTIMIZE: <the improved code>"
    "\nDo NOT change behavior, do NOT rename identifiers, and keep the code "
    "complete and runnable (CSS may be minified; JS must keep its logic)."
)


# ─────────────────────────────────────────────────────────────────────────────
#  Chunker — split an app build into semantic nodes
# ─────────────────────────────────────────────────────────────────────────────
def match_brace(s: str, open_idx: int) -> int:
    """Index of the matching close brace for s[open_idx] == '{'."""
    depth = 0
    for j in range(open_idx, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def split_js(code: str):
    """Split JS source into top-level chunks (functions, const-arrow fns, setup)."""
    chunks = []
    pat = re.compile(
        r"(?:function\s+\w+\s*\([^)]*\)|"
        r"const\s+\w+\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>)",
        re.M,
    )
    spans = []
    for m in pat.finditer(code):
        brace = code.find("{", m.start())
        if brace == -1:
            continue
        end = match_brace(code, brace)
        if end == -1:
            continue
        spans.append((m.start(), end + 1))
    # fold overlapping spans (a const arrow inside another fn is caught once)
    spans.sort()
    merged = []
    for st, en in spans:
        if merged and st < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], en))
        else:
            merged.append((st, en))
    taken = [False] * len(code)
    for st, en in merged:
        chunk = code[st:en].strip()
        if len(chunk) >= MIN_CHUNK:
            chunks.append(chunk)
        for i in range(st, en):
            taken[i] = True
    # leftover top-level code (state declarations, init calls) -> setup node
    leftover = "".join(c for i, c in enumerate(code) if not taken[i]).strip()
    if len(leftover) >= MIN_CHUNK:
        chunks.append(leftover)
    return chunks


def split_css(code: str):
    """Split CSS into per-rule chunks (selector + declaration block)."""
    chunks = []
    i = 0
    while True:
        brace = code.find("{", i)
        if brace == -1:
            break
        end = match_brace(code, brace)
        if end == -1:
            break
        selector = code[i:brace].strip()
        body = code[brace + 1:end].strip()
        i = end + 1
        if selector and body:
            chunks.append(f"{selector} {{\n{body}\n}}")
    return chunks


def split_html(code: str):
    """HTML layout chunk(s): top-level body elements with ids/classes, or the
    whole body if it is small. Returns list of markup strings."""
    body = re.search(r"<body[^>]*>(.*?)</body>", code, re.S | re.I)
    html = body.group(1) if body else code
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"\n\s*\n+", "\n", html).strip()
    if not html:
        return []
    if len(html) <= MAX_CHUNK:
        return [html]
    # large body: split on top-level block elements
    parts = re.split(r"(?=<\s*(?:div|section|header|nav|main|footer|form|table|ul|ol)\b)",
                     html, flags=re.I)
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) >= MIN_CHUNK]
    return parts or [html[:MAX_CHUNK]]


CSS_ONLY_PURPOSES = {"styling", "animations"}   # a CSS rule can never be game-logic
JS_SAFE_PURPOSES = set(k for k, _ in NODE_PURPOSES) - {"styling", "layout"}
HTML_SAFE_PURPOSES = {"layout", "ui-render", "event-handler", "input"}


def classify_purpose(text: str, scope=None):
    """Return (purpose_key, score) for the best matching node purpose.
    scope: optional set of allowed purpose keys — the chunker restricts CSS
    rules to styling/animations so a selector like `.game-container .score`
    can never be labeled game-logic (the model would rightly refuse to call
    CSS game logic)."""
    low = text.lower()
    best, best_score = None, 0
    for key, kws in NODE_PURPOSES:
        if scope is not None and key not in scope:
            continue
        score = sum(1 for kw in kws if kw in low)
        if score > best_score:
            best, best_score = key, score
    return best, best_score


def chunk_app(export_dir: Path):
    """Return list of dicts {text, purpose, purpose_score} for one export.
    Purpose is keyword-classified with a type-based default (js->utility,
    css->styling, html->layout) so no node is dropped.  Each language is
    classified against a scope it can plausibly be (CSS can't be game-logic,
    HTML can't be database state, etc.)."""
    index = export_dir / "index.html"
    if not index.exists():
        return []
    code = index.read_text(encoding="utf-8", errors="ignore")
    nodes = []
    style_m = re.search(r"<style[^>]*>(.*?)</style>", code, re.S | re.I)
    if style_m:
        for c in split_css(style_m.group(1)):
            p, s = classify_purpose(c, scope=CSS_ONLY_PURPOSES)
            if p is None:
                p, s = "styling", 0
            nodes.append({"text": c[:MAX_CHUNK], "purpose": p, "score": s})
    for script_m in re.finditer(r"<script([^>]*)>(.*?)</script>", code, re.S | re.I):
        attrs, js = script_m.group(1), script_m.group(2)
        # skip external src-only scripts (no inline body)
        if re.search(r"\bsrc=", attrs, re.I) or not js.strip():
            continue
        for c in split_js(js):
            p, s = classify_purpose(c, scope=JS_SAFE_PURPOSES)
            if p is None:
                p, s = "utility", 0
            nodes.append({"text": c[:MAX_CHUNK], "purpose": p, "score": s})
    for c in split_html(code):
        p, s = classify_purpose(c, scope=HTML_SAFE_PURPOSES)
        if p is None:
            p, s = "layout", 0
        nodes.append({"text": c[:MAX_CHUNK], "purpose": p, "score": s})
    return nodes


def merge_tiny_chunks(nodes):
    """Combine consecutive tiny same-purpose chunks (the 50-160 char CSS rules)
    into one real section with actual context to discriminate.  Big chunks are
    left untouched; runs of tiny chunks merge until ~MERGE_TARGET chars."""
    out = []
    bucket = []            # texts being accumulated
    bucket_purpose = None
    bucket_len = 0
    bucket_score = 0

    def flush():
        nonlocal bucket, bucket_purpose, bucket_len, bucket_score
        if bucket:
            out.append({
                "text": "\n\n".join(bucket)[:MAX_CHUNK],
                "purpose": bucket_purpose,
                "score": bucket_score,
            })
        bucket, bucket_purpose, bucket_len, bucket_score = [], None, 0, 0

    for node in nodes:
        t, p = node["text"], node["purpose"]
        tiny = len(t) < MERGE_TINY
        if tiny and bucket_purpose == p and bucket_len + len(t) <= MERGE_MAX:
            bucket.append(t)
            bucket_len += len(t)
            bucket_score = max(bucket_score, node.get("score", 0))
            continue
        if bucket and (p != bucket_purpose or not tiny or bucket_len >= MERGE_TARGET):
            flush()
        if tiny:
            bucket = [t]
            bucket_purpose = p
            bucket_len = len(t)
            bucket_score = node.get("score", 0)
        else:
            flush()
            out.append(node)
    flush()
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Fake generator — mutations + cross-app chunks
# ─────────────────────────────────────────────────────────────────────────────
def _op_swap(src, a, b):
    """Swap operator a -> b once, guarded so we never turn `<=` into `=<`
    or break `=>` arrows or `==` comparisons."""
    out, i = [], 0
    while i < len(src):
        if src.startswith(a, i):
            before = src[i - 1] if i > 0 else ""
            after = src[i + len(a)] if i + len(a) < len(src) else ""
            guarded = (after in "=" or (a in "><=" and before == "=")
                       or (a == "=" and (after in "=>" or before in "!<>")))
            if not guarded:
                out.append(b)
                i += len(a)
                continue
        out.append(src[i])
        i += 1
    return "".join(out)


# Subtle one-token mutations: off-by-one bounds, wrong array index, loose
# equality, wrong initializer, flipped logic op.  These read as *plausible*
# and are what the extreme tier is built from.
_SM_MUTATIONS = [
    (" < ", " <= ", "subtle: off-by-one lower"),
    (" <= ", " < ", "subtle: off-by-one upper"),
    (" > ", " >= ", "subtle: off-by-one upper (rev)"),
    (" >= ", " > ", "subtle: off-by-one lower (rev)"),
    (" + 1", "", "subtle: dropped increment"),
    (" - 1", "", "subtle: dropped decrement"),
    (" === ", " == ", "subtle: loose equality"),
    (" && ", " || ", "subtle: AND→OR"),
    (" || ", " && ", "subtle: OR→AND"),
]


def subtle_mutation(code: str, rng: random.Random):
    """Return code with ONE subtle single-token break (off-by-one, wrong
    index, loose equality, wrong init, etc.).  Returns code unchanged if no
    subtle family matches — caller decides if that's acceptable."""
    s = code
    for a, b, _tag in _SM_MUTATIONS:
        if a in s:
            return _op_swap(s, a, b)
    # wrong array index / counter arithmetic
    m = re.search(r"\b(\w+)\[(i|j|k|n)\s*\+\s*1\]", s)
    if m:
        return s.replace(m.group(0), f"{m.group(1)}[{m.group(2)}]", 1)
    m = re.search(r"\b(\w+)\[(i|j|k|n)\]", s)
    if m:
        return s.replace(m.group(0), f"{m.group(1)}[{m.group(2)} + 1]", 1)
    m = re.search(r"\[0\]", s)
    if m:
        return s.replace(m.group(0), "[1]", 1)
    m = re.search(r"\[1\]", s)
    if m:
        return s.replace(m.group(0), "[0]", 1)
    # wrong initializer / counter start
    m = re.search(r"\b(let|const|var)\s+(\w+)\s*=\s*(0|1)", s)
    if m:
        return s.replace(m.group(0),
                         f"{m.group(1)} {m.group(2)} = {'1' if m.group(3) == '0' else '0'}", 1)
    m = re.search(r"(Math\.(?:floor|ceil|max|min|round))\(", s)
    if m:
        flip = {"Math.floor": "Math.ceil", "Math.ceil": "Math.floor",
                "Math.max": "Math.min", "Math.min": "Math.max",
                "Math.round": "Math.floor"}
        return s.replace(m.group(1), flip[m.group(1)], 1)
    # subtle CSS value flips
    for a, b in [("repeat(3", "repeat(2"), ("repeat(4", "repeat(3"),
                 ("repeat(2", "repeat(3"), ("100%", "50%")]:
        if a in s:
            return s.replace(a, b, 1)
    # subtle HTML: disable an interactive element / swap input type
    if re.search(r"<button", s, re.I):
        return re.sub(r"<button([^>]*?)(/?)>", r"<button\1 disabled\2>", s, count=1, flags=re.I)
    m = re.search(r'type="(button|submit|text|number)"', s)
    if m:
        flip = {"button": "submit", "submit": "button", "text": "number", "number": "text"}
        return s.replace(m.group(0), f'type="{flip[m.group(1)]}"', 1)
    return code


def mutate(code: str, rng: random.Random, subtle=False):
    """Return a subtly-broken variant of code.  subtle=True uses ONLY the
    single-token mutation families (extreme tier); otherwise the full set
    including crude structural breaks for the easier tiers."""
    s = code
    if subtle:
        return subtle_mutation(s, rng)
    for a, b in [("red", "black"), ("black", "red"), ("true", "false"),
                 ("max", "min"), ("min", "max")]:
        if re.search(rf"\b{a}\b", s):
            return re.sub(rf"\b{a}\b", b, s)
    for a, b in [("===", "!=="), ("!==", "==="), (" < ", " > "), (" > ", " < "),
                 ("+=", "-="), ("-=", "+=")]:
        if a in s:
            return _op_swap(s, a, b)
    for a, b in [("getElementById", "getElementsByClassName"),
                 ("innerHTML", "textContent"), ("appendChild", "insertBefore"),
                 ("querySelector", "getElementById")]:
        if a in s:
            return s.replace(a, b, 1)
    if "return " in s:
        return s.replace("return ", "// return ", 1)
    # ── CSS: drop a declaration / change a value ──
    if ":" in s and ";" in s:
        for a, b in [("display: flex", "display: block"),
                     ("display:flex", "display:block"),
                     ("background: #", "background: #111"),
                     ("border-radius: 50%", "border-radius: 0%"),
                     ("position: absolute", "position: static")]:
            if a in s:
                return s.replace(a, b, 1)
        lines = s.splitlines()
        decls = [i for i, l in enumerate(lines) if ":" in l and l.strip().endswith(";")]
        if decls:
            i = rng.choice(decls)
            # DELETE the declaration entirely — never prefix with a marker
            # comment.  Markers like "/* removed */" taught the model (via the
            # cloze rows' ⟦MISSING CODE⟧) to associate removal markers with
            # "the node to complete" and biased picks toward such fakes.
            del lines[i]
            return "\n".join(lines)
    # ── HTML: change id / drop an attribute / swap text ──
    m = re.search(r'id="([^"]+)"', s)
    if m:
        return s.replace(m.group(0), f'id="{m.group(1)}-x"', 1)
    if ">" in s and "<" in s:
        return re.sub(r"<([a-z]+)", r"<\1 data-x", s, count=1)
    return s


def explain_fake(correct: str, fake: str, kind: str, purpose: str,
                 letter: str = "") -> str:
    """A one-line COACHED reason why `fake` is the wrong node for this app.
    Used to synthesize reason-then-choose rows whose justification is grounded
    in the REAL difference (not the model's rationalization)."""
    purpose_label = PURPOSE_LABELS.get(purpose, f"{purpose} node")
    who = f"Node {letter}" if letter else "It"
    if kind == "FAKE-XAPP":
        # cross-app fake: real code from a DIFFERENT app of the same purpose
        # — it doesn't match this app's identifiers / goal
        ids_correct = set(re.findall(r"\b[a-zA-Z_$][\w$]*\b", correct))
        ids_fake = set(re.findall(r"\b[a-zA-Z_$][\w$]*\b", fake))
        foreign = sorted(ids_fake - ids_correct)
        sig = " ".join(foreign[:6]) if foreign else ""
        if sig:
            return (f"{who} is real code from a DIFFERENT app — its identifiers "
                    f"({sig}) never appear in this app's {purpose_label}, so it "
                    f"cannot be the one this app uses")
        return (f"{who} is real code from a DIFFERENT app — it implements a "
                f"{purpose_label} that this app's goal does not ask for")
    # FAKE-MUT: find the concrete edit the mutation made
    import difflib
    sm = difflib.SequenceMatcher(None, correct.split(), fake.split())
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old = " ".join(correct.split()[i1:i2])
        new = " ".join(fake.split()[j1:j2])
        if tag == "replace" and old and new:
            return (f"{who} is a broken edit of the real node: it changes "
                    f"`{old[:60]}` into `{new[:60]}`, which corrupts the "
                    f"{purpose_label}")
        if tag == "delete" and old:
            return (f"{who} is a broken edit of the real node: it DELETES "
                    f"`{old[:60]}`, which the {purpose_label} needs")
        if tag == "insert" and new:
            return (f"{who} is a broken edit of the real node: it inserts "
                    f"`{new[:60]}`, which does not belong in the "
                    f"{purpose_label}")
    return f"{who} is a subtly-broken copy of the real {purpose_label}"


def build_reason_prompt(puzzle):
    """Plain-text prompt for a reason-then-choose row: the full pick prompt
    (goal + purpose + 3 candidates) plus the request to justify the choice.
    Shared by the live Stage 4.5 call and the banked training rows so the
    trained format matches the played format."""
    parts = [
        f"APP GOAL: {puzzle['request']}",
        f"NODE PURPOSE: {puzzle['purpose_label']}",
        "",
        "CANDIDATE NODES — exactly ONE is correct for this purpose in THIS app:",
    ]
    for n in puzzle["nodes"]:
        parts.append(f"NODE {n['letter']}:\n```\n{n['text']}\n```")
    parts.append(
        "Explain concisely which node is correct and WHY the other two "
        "candidates are wrong (name the concrete code difference that gives "
        "it away). Reply with exactly:\nNODE: X\nREASON: <one or two sentences>")
    return "\n\n".join(parts)


def build_reason_messages(puzzle, reference):
    """Full messages for the live reason call.  Reference is the same RAG
    library the pick saw (or empty for the RAG-off eval form)."""
    ref_text = "\n\n".join(f"```\n{r}\n```" for r in reference)
    user = build_reason_prompt(puzzle)
    if ref_text:
        user = (f"REFERENCE (how other apps implement this node type — retrieved "
                f"from the library):\n{ref_text}\n\n{user}")
    return [{"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user}]


def play_reason(puzzle, llm_url, model, rag=True, max_retries=1):
    """Stage 4.5 — REASON: after a CORRECT pick, the model must articulate
    WHY its choice was right (a one-sentence justification naming the concrete
    difference).  Returns the model's own chosen letter + reason when it
    justifies well; when it can't (or names the wrong node), the coached
    ground-truth reason attached to the puzzle is the fallback for banking.
    """
    letter = puzzle["correct_letter"]
    reference = []
    if rag:
        reference = lib.reference_for(puzzle["purpose"], puzzle["app"], puzzle["request"])
    messages = build_reason_messages(puzzle, reference)
    t0 = time.time()
    reply = None
    for _ in range(max_retries + 1):
        try:
            reply = llm_chat(llm_url, model, messages, max_tokens=160, temperature=0.3)
        except Exception:
            reply = None
        if reply and parse_choice(reply):
            break
    chosen = parse_choice(reply or "")
    reason = ""
    if reply:
        m = re.search(r"REASON\s*[:=]\s*(.+)", reply, re.S | re.I)
        reason = (m.group(1).strip() if m else "").strip("`")
    # "Both" banking: the model's own justification is kept when it names the
    # correct node with a real reason; otherwise the coached diff-based reason
    # (puzzle['reason']) is used so the row still teaches correct reasoning.
    model_ok = bool(chosen == letter and len(reason) >= 20)
    return {"chosen": chosen, "ok": model_ok,
            "reason": reason if model_ok else puzzle["reason"],
            "reply": reply, "latency_s": round(time.time() - t0, 2)}


def chunk_similarity(a: str, b: str):
    """0..1 similarity between two code chunks — used to rank cross-app
    fakes so the most plausible (near-twin) one is offered to the LLM."""
    ta = re.findall(r"[a-z0-9_]+", a.lower())
    tb = re.findall(r"[a-z0-9_]+", b.lower())
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    inter = len(sa & sb)
    jac = inter / max(len(sa | sb), 1)
    len_sim = min(len(ta), len(tb)) / max(len(ta), len(tb), 1)
    return 0.7 * jac + 0.3 * len_sim


# ─────────────────────────────────────────────────────────────────────────────
#  VERDICT-STEP REASONING GAME (dedicated reasoning rounds)
# =============================================================================
#  Ordered, verifiable reasoning: instead of one pick over 3 candidates, the
#  game walks the model through each candidate ONE AT A TIME and forces a
#  YES/NO verdict + concrete evidence BEFORE the pick.  Every step is scored
#  against ground truth the game already knows:
#    * verdict      — the real node must be YES, fakes NO (checked exactly)
#    * evidence     — must cite a marker from the REAL diff: the mutated
#                     token/op for FAKE-MUT, or identifiers foreign to this
#                     app for FAKE-XAPP (fuzzy identifier-intersection match)
#    * finale pick  — must agree with the model's OWN verdicts
#  Rows are banked only when the whole chain is right, so the finetune learns
#  *verified* reasoning traces — not the letter-pattern-matching that made
#  the plain pick un-trainable (the C-bias).
# ─────────────────────────────────────────────────────────────────────────────

# Truthy verbatim-insertion markers that prove a copy is NOT a real app chunk.
_FAKE_COPY_MARKERS = ("// inserted into", "/* inserted into",
                      "// from another", "copied from", "stub", "todo")
# Vague evidence that adds nothing even when the verdict is right — grader
# credit requires a CONCRETE marker (diff token / foreign identifier).
_WEAK_EVIDENCE = {"looks correct", "fits the goal", "does not match",
                  "doesn't match", "different app", "another app", "not the real",
                  "matches the goal", "makes sense", "looks wrong",
                  "seems wrong", "real node", "correct node"}


def _evidence_markers(puzzle, node):
    """Ground-truth markers the model's evidence must cite for `node` to earn
    credit: for a FAKE-MUT the tokens/operators the mutation touched; for a
    FAKE-XAPP identifiers from the foreign code that don't exist in this
    app's correct chunk.  Empty for the CORRECT node (its evidence check is
    just substantive length)."""
    if node["kind"] == "CORRECT":
        return []
    correct = puzzle["correct_text"]
    text = node["text"]
    toks_c = set(re.findall(r"[a-z0-9_]+", correct.lower()))
    toks_f = set(re.findall(r"[a-z0-9_]+", text.lower()))
    if node["kind"] == "FAKE-XAPP":
        return sorted(toks_f - toks_c) or sorted(toks_c - toks_f)
    # FAKE-MUT: identifiers are near-identical — find the concrete edited
    # region (word-level diff) and return its tokens/operators.
    from difflib import SequenceMatcher
    sm = SequenceMatcher(None, correct.split(), text.split())
    out = set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old = " ".join(correct.split()[i1:i2])
        new = " ".join(text.split()[j1:j2])
        out |= set(re.findall(r"[a-z0-9_]+|[<>=!+*/%&|^~:-]{1,3}", (old + " " + new).lower()))
    if not out:  # word-level diff empty -> fall back to char-level tokens
        cc, ff = set(re.findall(r"[a-z0-9_]+|[<>=!+*/%&|^~:-]{1,3}", correct.lower())), \
                 set(re.findall(r"[a-z0-9_]+|[<>=!+*/%&|^~:-]{1,3}", text.lower()))
        out = (cc ^ ff)
    return sorted(out)


def _usable_markers(markers):
    """Drop markers too weak to serve as evidence: bare digits, hex colors,
    single letters.  A reason citing '360' or 'b' proves nothing; one citing
    'breakout' or 'lives' proves the model saw the foreign code."""
    good = []
    for m in markers:
        ml = m.lower()
        if not m or m.isdigit():
            continue
        if len(m) == 1 or (len(m) <= 4 and m.isalnum() and not m.isalpha()):
            continue
        if re.fullmatch(r"#[0-9a-f]{3,8}|[0-9a-f]{6}", ml):
            continue
        good.append(m)
    return good


def grade_verdict(puzzle, node, verdict, evidence):
    """Score ONE verdict step against ground truth.
    Returns {verdict_ok, evidence_ok, markers, weak, points}.
    points: +6 verdict right; +4 evidence cites a real diff marker (only when
    the verdict is right — a wrong-but-fluent reason earns nothing)."""
    truth = node["kind"] == "CORRECT"
    verdict_ok = bool(verdict) == truth
    ev = (evidence or "").lower()
    ev_plain = re.sub(r"[`*_\[\](){}]", " ", ev)   # strip markdown for matching
    if not verdict_ok:
        return {"verdict_ok": False, "evidence_ok": False, "markers": [],
                "weak": True, "points": -3}
    markers = _evidence_markers(puzzle, node)
    if node["kind"] == "CORRECT":
        # real node: credit any substantive evidence (~a real sentence)
        strong = len(re.findall(r"\b[a-z0-9_]{3,}\b", ev_plain)) >= 4
        evidence_ok = bool(strong and len(ev_plain) >= 30)
    else:
        markers = _usable_markers(markers)
        hits = [m for m in markers if m and m in ev_plain]
        copy_hit = any(m in ev_plain for m in _FAKE_COPY_MARKERS)
        # weak phrases only veto when NO concrete marker is cited — a reason
        # that names a real diff token ("uses `<=` not `<`") is substantive
        # even if it also says "the real node…".
        if hits:
            evidence_ok = not copy_hit
        elif copy_hit:
            evidence_ok = True
        else:
            # no marker cited: credit ONLY a quoted token/operator from the
            # code (`>=`, `isGameOver`, `score`) — never bare prose, even with
            # identifiers.  Generic "looks wrong / from another app" earns 0.
            quoted = re.findall(r"`([^`]{1,24})`|\b([<>=!+*/%&|^~]{1,3})\b", ev)
            evidence_ok = bool(quoted and not copy_hit)
        if evidence_ok:
            markers = hits
    points = 6 + (4 if evidence_ok else 0)
    return {"verdict_ok": True, "evidence_ok": evidence_ok,
            "markers": markers or [], "weak": not evidence_ok,
            "points": points}


def parse_verdict_reply(text):
    """(verdict, evidence) from a step reply.  Verdict is True=YES / False=NO;
    None when unparseable (then the caller retries the step)."""
    if not text:
        return None, None
    # verdict: the first YES/NO that comes AFTER 'VERDICT', ': YES|NO', or
    # a standalone 'YES.'/'NO.' answer (never a word like 'noise'/'yesman').
    # verdict: look for the explicit VERDICT marker first; if the model
    # answered without the word, accept a bare YES./NO. answer on a line.
    m = re.search(r"VERDICT\s*[:=-]?\s*(YES|NO)(?=\b)", text, re.I)
    if not m:
        m = re.search(r"^\s*[:=-]?\s*(YES|NO)[.\s]", text, re.I | re.M)
    if not m:
        m = re.search(r"(?:IS\s+IT\s+THE\s+REAL\s*[:=]?\s*)(YES|NO)(?=\b)", text, re.I)
    if not m:
        # conversational answer: "…is NO because…" / "I think YES, since…" —
        # take the LAST such verdict (the decision, not the analysis)
        cands = list(re.finditer(r"\b(?:is|think|answer|verdict)[^A-Za-z0-9]{1,4}(YES|NO)(?=\b)", text, re.I))
        if cands:
            m = cands[-1]
    if not m:
        return None, None
    verdict = m.group(1).upper() == "YES"
    # evidence = everything after the verdict line, minus the NODE header
    rest = text[m.end():].strip()
    for tag in ("EVIDENCE", "WHY", "REASON", "BECAUSE"):
        rest = re.sub(rf"^.*?\b{tag}\s*[:=-]?\s*", "", rest, count=1, flags=re.I)
    # cut any trailing second verdict ("…and NODE C: NO") — keep first only
    rest = re.split(r"\s+NODE\s+[ABC]\s*:", rest, maxsplit=1, flags=re.I)[0]
    rest = re.sub(r"[\s`*_]+$", "", rest)
    rest = re.sub(r"\s+", " ", rest).strip(" `-—|\n\t.")
    return verdict, rest


def build_verdict_step_prompt(puzzle, focus, reference=None):
    """One step of the walkthrough: all 3 candidates are shown (mutation
    fakes are ONLY answerable by comparing against the others — shown alone
    they are indistinguishable from the real node), and the model must
    commit a YES/NO verdict + evidence on the FOCUS candidate BEFORE the
    pick is asked anywhere."""
    parts = [f"APP GOAL: {puzzle['request']}",
             f"NODE PURPOSE: {puzzle['purpose_label']}"]
    if reference:
        ref_text = "\n\n".join(f"```\n{r}\n```" for r in reference)
        parts.append("REFERENCE (how other apps implement this node type):\n" + ref_text)
    parts.append("")
    parts.append("CANDIDATE NODES — exactly ONE is the real implementation "
                 "for this purpose in THIS app; the other two are broken:")
    for n in puzzle["nodes"]:
        parts.append(f"NODE {n['letter']}:\n```\n{n['text']}\n```")
    parts.append(
        f"Examine NODE {focus['letter']} carefully and decide: is it the real "
        f"{puzzle['purpose_label'].lower()} of THIS app, or is it broken code "
        f"(a subtly-edited copy, or code belonging to a DIFFERENT app) that "
        f"would not work here? Compare it against the other candidates and the "
        f"app goal. Reply with exactly one line:\n"
        f"NODE {focus['letter']}: VERDICT: YES|NO — EVIDENCE: <the concrete code "
        f"difference that decides it>")
    return [{"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": "\n\n".join(parts)}]


def build_finale_prompt(puzzle, reference=None):
    """Finale: after all verdicts, the model commits to the pick.  Must agree
    with its own verdicts or the round is flagged internally-inconsistent."""
    parts = [f"APP GOAL: {puzzle['request']}",
             f"NODE PURPOSE: {puzzle['purpose_label']}"]
    if reference:
        ref_text = "\n\n".join(f"```\n{r}\n```" for r in reference)
        parts.append("REFERENCE (how other apps implement this node type):\n" + ref_text)
    parts.append("")
    parts.append("CANDIDATE NODES — exactly ONE is the real implementation "
                 "for this purpose in THIS app:")
    for n in puzzle["nodes"]:
        parts.append(f"NODE {n['letter']}:\n```\n{n['text']}\n```")
    parts.append("Which node is the real implementation? Reply: NODE: X")
    return [{"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": "\n\n".join(parts)}]


RV_VERDICT = 6     # correct YES/NO per candidate
RV_EVIDENCE = 4    # evidence cites a real diff marker (on top of the verdict)
RV_FINALE = 15     # final pick right AND consistent with own verdicts
RV_INCONSISTENT = -8   # finale contradicts the model's own verdicts
RV_VERDICT_WRONG = -3  # wrong verdict (also forfeits the evidence credit)


def reason_chain_text(puzzle, verdicts, model_evidence=None):
    """Build the canonical (coached) reasoning chain for a puzzle — the
    ground-truth target the training row teaches.  Each step is one line
    naming the concrete difference, then the pick."""
    lines = []
    for n in puzzle["nodes"]:
        if n["kind"] == "CORRECT":
            lines.append(f"NODE {n['letter']}: YES — the real "
                         f"{puzzle['purpose_label'].lower()} of this app "
                         f"(matches the goal, uses this app's identifiers)")
        else:
            ev = explain_fake(puzzle["correct_text"], n["text"], n["kind"],
                              puzzle["purpose"], letter=n["letter"])
            lines.append(f"NODE {n['letter']}: NO — {ev}")
    lines.append(f"FINAL: NODE {puzzle['correct_letter']}")
    return "\n".join(lines)


def play_reason_game(puzzle, llm_url, model, rag=True, max_retries=2):
    """Play ONE puzzle as a verdict-step reasoning game.  Returns
    {steps: [{node_letter, kind, verdict, verdict_ok, evidence, evidence_ok,
              points}], pick, pick_ok, consistent, total, latency_s}.
    Every verdict is committed before any pick is asked; the finale must
    agree with the model's own YES verdict or it is flagged inconsistent."""
    reference = []
    if rag:
        try:
            reference = lib.reference_for(puzzle["purpose"], puzzle["app"],
                                          puzzle["request"])
        except Exception:
            reference = []
    t0 = time.time()
    steps = []
    total = 0
    for node in puzzle["nodes"]:
        verdict = None
        evidence = None
        reply = None
        for _ in range(max_retries + 1):
            try:
                reply = llm_chat(llm_url, model,
                                 build_verdict_step_prompt(puzzle, node, reference),
                                 max_tokens=120, temperature=0.2)
            except Exception:
                reply = None
            if reply:
                verdict, evidence = parse_verdict_reply(reply)
            if verdict is not None:
                break
        if verdict is None:   # unparseable after retries — counts as a miss
            g = {"verdict_ok": False, "evidence_ok": False, "markers": [],
                 "weak": True, "points": RV_VERDICT_WRONG}
        else:
            g = grade_verdict(puzzle, node, verdict, evidence)
        total += g["points"]
        steps.append({"node": node["letter"], "kind": node["kind"],
                      "verdict": verdict, "verdict_ok": g["verdict_ok"],
                      "evidence": evidence or "", "evidence_ok": g["evidence_ok"],
                      "points": g["points"]})
    # finale pick — must be consistent with the committed verdicts
    pick, pick_ok, consistent = None, False, True
    yes_nodes = [s["node"] for s in steps if s["verdict"] is True]
    for _ in range(max_retries + 1):
        try:
            freply = llm_chat(llm_url, model, build_finale_prompt(puzzle, reference),
                              max_tokens=40, temperature=0.1)
        except Exception:
            freply = None
        pick = parse_choice(freply or "") if freply else None
        if pick:
            break
    if pick:
        # the pick must agree with the model's own verdicts
        truth_yes = puzzle["correct_letter"]
        consistent = (yes_nodes == [truth_yes])
        pick_ok = (pick == truth_yes)
        total += RV_FINALE if (pick_ok and consistent) else (
            RV_INCONSISTENT if not consistent else 0)
    return {"steps": steps, "pick": pick, "pick_ok": pick_ok,
            "consistent": consistent, "total": total,
            "latency_s": round(time.time() - t0, 2)}


# ── Adaptive difficulty ─────────────────────────────────────────────────────
# Fakes get harder as the model proves it can handle them: recent accuracy
# drives the knob, and we make MORE of whichever fake kind (mutation vs
# cross-app) actually fools the model.
ADAPT_WINDOW = 20
ADAPT_HARD_ACC = 0.70    # recent acc >= this -> subtle mutations + near-twin
ADAPT_EASY_ACC = 0.55    # recent acc <= this -> crude mutations + random
ADAPT = {"recent": [], "acc": 0.0, "fooled_mut": 0, "fooled_xapp": 0,
         "last_knobs": None}


def adapt_update(correct):
    ADAPT["recent"].append(1 if correct else 0)
    if len(ADAPT["recent"]) > ADAPT_WINDOW:
        ADAPT["recent"] = ADAPT["recent"][-ADAPT_WINDOW:]
    ADAPT["acc"] = sum(ADAPT["recent"]) / max(len(ADAPT["recent"]), 1)


def fake_knobs(tier):
    """Return (subtle_mut, near_xapp) for this tier, adaptively.
    extreme is always hardest; easier tiers tighten as recent accuracy climbs.
    Mutation-biased by design: cross-app fakes fool the model far more than
    mutations (measured ~2.7x), so near-twin xapp actively suppresses the
    sustained high windows the gate needs. Mutations stay subtle at high acc,
    xapp never tightens past random. fooled_* counts are tracked for stats
    only, not used to tighten the game."""
    if tier == "extreme":
        return True, True
    acc = ADAPT["acc"]
    if acc >= ADAPT_HARD_ACC:
        return True, False      # subtle mutation + random xapp, never near-twin
    if acc <= ADAPT_EASY_ACC:
        return False, False
    return True, False


TIER_EASY_LOGIC = 5      # <= this many logic nodes -> easy
TIER_MED_LOGIC = 10      # <= this many logic nodes -> medium
TIER_EXT_LOGIC = 16      # <= this many logic nodes -> hard; above -> extreme
LOGIC_PURPOSES = {"ui-render", "game-logic", "database", "event-handler",
                  "state", "input", "output", "utility", "canvas-rendering"}


def app_tier(nodes, size, multi):
    """Difficulty tier from LOGIC node count (styling/layout chunks are easy
    filler and would mislabel a simple app as medium), size, and multi-file."""
    if multi:
        return "hard"
    logic = sum(1 for n in nodes if n["purpose"] in LOGIC_PURPOSES)
    if logic <= TIER_EASY_LOGIC:
        return "easy"
    if logic <= TIER_MED_LOGIC:
        return "medium"
    if logic <= TIER_EXT_LOGIC:
        return "hard"
    return "extreme"


class Library:
    """Index of all app chunks, keyed by purpose, for RAG retrieval + fakes.

    Apps are FAMILY-DEDUPED (the library is full of ~40 near-identical
    note-taking builds) and TIERED easy/medium/hard so the game can scale.
    """

    def __init__(self, exports_dir: Path, max_apps=None):
        self.apps = {}          # app_name -> {"request", "nodes", "tier", "size"}
        self.by_purpose = {}    # purpose -> [ (app_name, chunk) ]
        dirs = sorted(exports_dir.iterdir()) if exports_dir.is_dir() else []
        if max_apps:
            dirs = dirs[:max_apps]
        raw = []
        for d in dirs:
            if not d.is_dir():
                continue
            nodes = merge_tiny_chunks(chunk_app(d))
            if not nodes:
                continue
            request = ""
            explicit_tier = None
            tj = d / "_training.json"
            if tj.exists():
                try:
                    meta = json.loads(tj.read_text(encoding="utf-8", errors="ignore"))
                    request = meta.get("request", "")
                    et = meta.get("tier", "")
                    if et in ("easy", "medium", "hard", "extreme"):
                        explicit_tier = et
                except Exception:
                    pass
            index = d / "index.html"
            size = index.stat().st_size if index.exists() else 0
            multi = (d / "client").exists() or (d / "server").exists()
            tier = explicit_tier or app_tier(nodes, size, multi)
            raw.append({"name": d.name, "request": request, "nodes": nodes,
                        "tier": tier, "size": size, "multi": multi})
        # family dedupe: same request prefix (or same name prefix before '-') -> keep best
        fam = {}
        for a in raw:
            key = family_key(a["request"], a["name"])
            prev = fam.get(key)
            if prev is None or len(a["nodes"]) > len(prev["nodes"]):
                fam[key] = a
        for a in fam.values():
            self.apps[a["name"]] = {"request": a["request"], "nodes": a["nodes"],
                                     "tier": a["tier"], "size": a["size"]}
            for n in a["nodes"]:
                self.by_purpose.setdefault(n["purpose"], []).append((a["name"], n))
        self.by_purpose = {k: v for k, v in self.by_purpose.items() if v}
        self.tiers = {"easy": [], "medium": [], "hard": [], "extreme": []}
        for name, a in self.apps.items():
            self.tiers[a["tier"]].append(name)
        self._emb_cache = {}     # purpose -> (pool list, aligned vectors)
        self._query_cache = {}   # (purpose, request) -> query vector

    def tier_counts(self):
        return {t: len(v) for t, v in self.tiers.items()}

    def apps_with(self, purpose, min_nodes=4):
        """Apps that have >= min_nodes classifiable chunks of this purpose."""
        return [name for name, a in self.apps.items()
                if sum(1 for n in a["nodes"] if n["purpose"] == purpose) >= min_nodes]

    def reference_for(self, purpose, exclude_app, request, k=3, max_chars=1600):
        """RAG: top-k same-purpose chunks from OTHER apps.  With EMBED_URL set,
        ranks by embedding similarity to the target request (semantic RAG);
        otherwise falls back to keyword overlap with the request text."""
        pool = [c for app, c in self.by_purpose.get(purpose, []) if app != exclude_app]
        if not pool:
            return []
        if EMBED_URL:
            try:
                return self._semantic_refs(purpose, pool, request, k, max_chars)
            except Exception:
                pass   # fall back to keyword ranking
        words = set(re.findall(r"[a-z]{3,}", (request or "").lower()))
        pool.sort(key=lambda c: -len(words & set(re.findall(r"[a-z]{3,}", c["text"].lower()))))
        out, used = [], set()
        for c in pool:
            if c["text"] in used:
                continue
            used.add(c["text"])
            out.append(c["text"][:400])
            if len(out) >= k or sum(len(x) for x in out) >= max_chars:
                break
        return out

    def _semantic_refs(self, purpose, pool, request, k, max_chars):
        """Embedding-ranked references.  Pool vectors are cached per purpose
        (first use embeds the whole same-purpose pool once); the query vector
        is cached per unique (purpose, request) string."""
        cached = self._emb_cache.get(purpose)
        if cached is None:
            texts = [c["text"][:400] for c in pool]
            vecs = embed_texts(EMBED_URL, EMBED_MODEL, texts)
            self._emb_cache[purpose] = (list(pool), vecs)
            pool, vecs = self._emb_cache[purpose]
        else:
            pool, vecs = cached
        qkey = (purpose, request or "")
        qv = self._query_cache.get(qkey)
        if qv is None:
            qv = embed_texts(EMBED_URL, EMBED_MODEL, [(request or "")[:400]])[0]
            self._query_cache[qkey] = qv
        ranked = sorted(zip(pool, vecs), key=lambda pv: -_cosine(pv[1], qv))
        out, used = [], set()
        for c, _v in ranked:
            if c["text"] in used:
                continue
            used.add(c["text"])
            out.append(c["text"][:400])
            if len(out) >= k or sum(len(x) for x in out) >= max_chars:
                break
        return out

    def cross_app_fake(self, purpose, exclude_app, exclude_text, rng, near=False,
                       sim_cap=None):
        """A real same-purpose chunk from a different app (works there, wrong here).
        near=True ranks the pool by similarity and returns the most plausible
        (near-twin) chunk — the extreme tier's second fake.
        sim_cap: reject candidates chunk_similarity > sim_cap to the correct
        chunk (serve-time quality); falls back to the LEAST-similar pool chunk
        so the puzzle stays answerable even when the pool is full of
        boilerplate.  near=True ignores sim_cap (near-twin IS the point)."""
        pool = [c for app, c in self.by_purpose.get(purpose, [])
                if app != exclude_app and c["text"] != exclude_text]
        if not pool:
            return None
        if near or sim_cap is None:
            if near:
                pool.sort(key=lambda c: -chunk_similarity(c["text"], exclude_text))
                return pool[0]["text"]
            return rng.choice(pool)["text"]
        # rejection-sample: a plausible fake that is NOT a near-duplicate
        rng.shuffle(pool)
        for c in pool[:FAKE_SIM_SAMPLE]:
            if chunk_similarity(c["text"], exclude_text) <= sim_cap:
                return c["text"]
        # nothing distinct in the sample — the least-similar chunk is the best
        # answerable option (usually a distinctive rule vs shared boilerplate)
        pool.sort(key=lambda c: chunk_similarity(c["text"], exclude_text))
        return pool[0]["text"]

    def make_puzzle(self, app_name, node, rng, subtle_mut=False, near_xapp=False,
                    sim_cap=None):
        """Return dict: purpose label, correct chunk, 3 shuffled nodes A/B/C.
        subtle_mut: the mutation fake uses ONLY subtle single-token breaks
        (off-by-one, loose equality, flipped op).  near_xapp: the cross-app
        fake is the nearest-twin same-purpose chunk.  Both default off —
        callers pick them via fake_knobs(tier) for adaptive difficulty.
        sim_cap: reject any fake more than sim_cap similar to the correct
        chunk (serve-time quality, set by play_round below extreme tier).
        None = uncapped (corpus builder + eval keep near-dupes as training).
        Returns None when 3 distinct acceptable candidates can't be built."""
        request = self.apps[app_name]["request"]
        correct = node["text"]
        fake_a = None
        for _ in range(FAKE_SIM_TRIES):
            cand = mutate(correct, rng, subtle=subtle_mut)
            if (cand != correct and len(cand) >= MIN_CHUNK
                    and (sim_cap is None
                         or chunk_similarity(cand, correct) <= sim_cap)):
                fake_a = cand
                break
        fake_b = self.cross_app_fake(node["purpose"], app_name, correct, rng,
                                     near=near_xapp, sim_cap=sim_cap)
        candidates = [("CORRECT", correct)]
        seen = {correct}
        if fake_a:
            candidates.append(("FAKE-MUT", fake_a))
            seen.add(fake_a)
        if fake_b:
            candidates.append(("FAKE-XAPP", fake_b))
            seen.add(fake_b)
        # pad until we have 3 distinct nodes (mutations + cross-app), all
        # passing the same distinctness bar (sim_cap) as the first two
        guard = 0
        while len(candidates) < 3 and guard < 16:
            guard += 1
            cand = None
            if rng.random() < 0.6:
                cand = mutate(correct, rng, subtle=subtle_mut)
                if cand == correct or len(cand) < MIN_CHUNK or cand in seen \
                        or (sim_cap is not None
                            and chunk_similarity(cand, correct) > sim_cap):
                    cand = None
            if cand is None:
                cand = self.cross_app_fake(node["purpose"], app_name, correct, rng,
                                           near=near_xapp, sim_cap=sim_cap)
            if cand is None or cand in seen or len(cand) < MIN_CHUNK:
                continue
            candidates.append(("FAKE-MUT", cand))
            seen.add(cand)
        if len(candidates) < 3:
            return None
        rng.shuffle(candidates)
        letters = ["A", "B", "C"][:len(candidates)]
        nodes = [{"letter": L, "kind": k, "text": t} for L, (k, t) in zip(letters, candidates)]
        correct_letter = next(n["letter"] for n in nodes if n["kind"] == "CORRECT")
        # coached (ground-truth) justification: why the correct node is right,
        # and each fake wrong — generated from the REAL code difference.  Used
        # to synthesize reason rows whose reasoning is grounded in the diff
        # (not the model's rationalization).
        wrong_reasons = []
        for n in nodes:
            if n["kind"] != "CORRECT":
                wrong_reasons.append(explain_fake(
                    correct, n["text"], n["kind"], node["purpose"],
                    letter=n["letter"]))
        reason = (f"Node {correct_letter} is the real {PURPOSE_LABELS.get(node['purpose'], node['purpose'])} "
                  f"of this app; " + " ".join(wrong_reasons) if wrong_reasons
                  else f"Node {correct_letter} is the real implementation "
                       f"for this app's {PURPOSE_LABELS.get(node['purpose'], node['purpose'])}")
        return {
            "app": app_name,
            "request": request,
            "purpose": node["purpose"],
            "purpose_label": PURPOSE_LABELS.get(node["purpose"], f"{node['purpose']} node"),
            "nodes": nodes,
            "correct_letter": correct_letter,
            "correct_text": correct,
            "reason": reason,
            "reason_by_letter": {n["letter"]: explain_fake(
                correct, n["text"], n["kind"], node["purpose"], letter=n["letter"])
                for n in nodes if n["kind"] != "CORRECT"},
        }


# ─────────────────────────────────────────────────────────────────────────────
#  LLM client (OpenAI-compatible, non-streaming)
# ─────────────────────────────────────────────────────────────────────────────
def llm_chat(llm_url, model, messages, timeout=180, temperature=0.2, max_tokens=40):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        llm_url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    return data["choices"][0]["message"]["content"]


def embed_texts(url, model, texts):
    """Batch-embed texts via Ollama /api/embed.  Returns a list of vectors;
    raises on failure so the caller can fall back to keyword ranking."""
    vecs = []
    for i in range(0, len(texts), EMBED_BATCH):
        chunk = texts[i:i + EMBED_BATCH]
        req = urllib.request.Request(
            url, data=json.dumps({"model": model, "input": chunk}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        vecs.extend(data["embeddings"])
    return vecs


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / max(na * nb, 1e-12)


def build_observe_messages(request, nodes):
    """Stage 1 (OBSERVE) — show the WHOLE app once before any section is
    tested.  The model studies the complete build, then each section is
    played as its own pick/recreate/optimize puzzle."""
    parts = [
        f"APP GOAL: {request}",
        "",
        "THE COMPLETE APP (shown once — study it before the sections are tested):",
    ]
    for i, n in enumerate(nodes, 1):
        label = PURPOSE_LABELS.get(n.get("purpose"), n.get("purpose", "section"))
        parts.append(f"SECTION {i} ({label}):\n```\n{n['text']}\n```")
    parts.append("You will next be tested on each section. "
                 "Acknowledge with exactly: OK")
    user = "\n\n".join(parts)
    return [{"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user}]


def observe_app(request, nodes, llm_url, model):
    """Stage 1 — show the whole app once.  Returns {reply, latency_s}."""
    t0 = time.time()
    try:
        reply = llm_chat(llm_url, model, build_observe_messages(request, nodes),
                         max_tokens=24, temperature=0.0)
    except Exception as e:
        return {"reply": f"<observe error: {e}>", "latency_s": round(time.time() - t0, 2)}
    return {"reply": reply, "latency_s": round(time.time() - t0, 2)}


def parse_choice(text):
    """Extract the letter A/B/C from the model's reply."""
    m = re.search(r"NODE\s*[:=]\s*([ABC])", text, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"^(?:\*\*)?([ABC])(?:\*\*)?\s*$", text.strip(), re.M)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([ABC])\b", text)
    if m:
        return m.group(1).upper()
    return None


def build_messages(puzzle, reference):
    ref_text = "\n\n".join(f"```\n{r}\n```" for r in reference)
    parts = [
        f"APP GOAL: {puzzle['request']}",
        f"NODE PURPOSE: {puzzle['purpose_label']}",
        "",
        "REFERENCE (how other apps implement this node type — retrieved from the library):",
        ref_text if ref_text else "(none retrieved)",
        "",
        "CANDIDATE NODES — exactly ONE is correct for this purpose in THIS app:",
    ]
    for n in puzzle["nodes"]:
        parts.append(f"NODE {n['letter']}:\n```\n{n['text']}\n```")
    parts.append("Which node is the correct implementation? Reply: NODE: X")
    user = "\n\n".join(parts)
    return [
        {"role": "system", "content": SYS_PROMPT},
        {"role": "user", "content": user},
    ]


PICK_CAND_CAP = 800   # chars per candidate in pick rows — keeps the full
                      # prompt (goal + purpose + 3 nodes) under MAX_SEQ=1024
                      # so the trainer never truncates the answer away


def build_pick_prompt(puzzle):
    """The TRUE game prompt for a pick (discrimination) row — identical to the
    RAG-off eval prompt (build_messages with no reference), with candidates
    capped so the row fits the trainer's MAX_SEQ.  Output the model must learn:
    "NODE: X" with the correct letter."""
    parts = [
        f"APP GOAL: {puzzle['request']}",
        f"NODE PURPOSE: {puzzle['purpose_label']}",
        "",
        "REFERENCE (how other apps implement this node type — retrieved from the library):",
        "(none retrieved)",
        "",
        "CANDIDATE NODES — exactly ONE is correct for this purpose in THIS app:",
    ]
    for n in puzzle["nodes"]:
        text = n["text"]
        if len(text) > PICK_CAND_CAP:
            text = text[:PICK_CAND_CAP] + " …(truncated)"
        parts.append(f"NODE {n['letter']}:\n```\n{text}\n```")
    parts.append("Which node is the correct implementation? Reply: NODE: X")
    return "\n\n".join(parts)


def family_key(request, name):
    """Dedupe key: first ~6 words of the request, else the name stem."""
    words = re.findall(r"[a-z0-9]{3,}", (request or "").lower())
    if len(words) >= 5:
        return " ".join(words[:6])
    stem = re.sub(r"[-_][0-9]+$", "", name).lower()
    return re.sub(r"\d+", "", stem)[:40]


# ─────────────────────────────────────────────────────────────────────────────
#  Game + logging
# ─────────────────────────────────────────────────────────────────────────────
def load_rounds_file():
    p = OUT_DIR / "rounds.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"best_round_s": None, "rounds_completed": 0}


def save_rounds_file(data):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "rounds.json").write_text(json.dumps(data, indent=1))


# ─────────────────────────────────────────────────────────────────────────────
#  Spaced-replay review queue
# ─────────────────────────────────────────────────────────────────────────────
# Nodes the model answers WRONG go into a review queue.  Each item comes due
# again after a growing interval (2, 4, 8, … rounds); two consecutive correct
# replays remove it.  Persisted to OUT_DIR/review-queue.json so spacing
# survives trainer restarts.
REVIEW_START_INTERVAL = 2
REVIEW_MAX_INTERVAL = 16
REVIEWS_PER_ROUND = 2
REVIEW_MASTERY_STREAK = 2
REVIEW_QUEUE = {}   # (app, purpose) -> {"due_at": int, "interval": int, "streak": int}


def _review_key(app, text):
    return f"{app}\x00{text}"


def load_review_queue():
    """Review queue is keyed by NODE TEXT (not purpose) so apps with several
    same-purpose nodes (e.g. 4 game-logic chunks) each get their own slot
    instead of collapsing onto the first node of that purpose.  Legacy
    purpose-keyed entries from before this fix are dropped (they re-queue
    naturally on the next miss)."""
    global REVIEW_QUEUE
    REVIEW_QUEUE = {}
    try:
        p = OUT_DIR / "review-queue.json"
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            for k, v in raw.items():
                if "\x00" in k and isinstance(v, dict):
                    app, text = k.split("\x00", 1)
                    # legacy 2-part keys had no node text -> drop (re-queues later)
                    if text:
                        REVIEW_QUEUE[(app, text)] = v
    except Exception:
        pass


def save_review_queue():
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        data = {_review_key(app, p): v for (app, p), v in REVIEW_QUEUE.items()}
        (OUT_DIR / "review-queue.json").write_text(json.dumps(data, indent=1))
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Per-app curriculum (memory -> modify -> rebuild)
# ─────────────────────────────────────────────────────────────────────────────
# Each app is a mini-course: the WHOLE design is shown once (Stage 1 observe —
# the leak is the memory source), then the app keeps returning with a DIFFERENT
# chunk missing until every chunk is recreated correctly.  Once all chunks are
# mastered, a small app gets the REBUILD finale: only the goal is shown and the
# model writes the whole app from memory (scored by structure + similarity).
# Persisted to OUT_DIR/curriculum.json so mastery survives trainer restarts.
CURRICULUM = {}   # app -> {"chunks": {purpose: {"ok": bool, "seen": int}},
                  #          "observe_round": int|None, "rebuild_done": bool,
                  #          "rebuild_ok": bool, "rebuild_sim": float}


def load_curriculum():
    global CURRICULUM
    CURRICULUM = {}
    try:
        p = OUT_DIR / "curriculum.json"
        if p.exists():
            CURRICULUM = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            if not isinstance(CURRICULUM, dict):
                CURRICULUM = {}
    except Exception:
        CURRICULUM = {}


def save_curriculum():
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "curriculum.json").write_text(json.dumps(CURRICULUM, indent=1))
    except Exception:
        pass


def _cur_state(app):
    st = CURRICULUM.setdefault(app, {"chunks": {}, "observe_round": None,
                                    "rebuild_done": False, "rebuild_ok": False,
                                    "rebuild_sim": 0.0})
    st.setdefault("chunks", {})
    return st


def _chunk_key(node):
    """Curriculum chunks are keyed by NODE TEXT (not purpose) so same-purpose
    nodes each get their own mastery slot instead of collapsing onto one."""
    return node.get("text", "")


def curriculum_mark_recreated(app, text, ok, round_no):
    """Record whether a chunk was recreated correctly this round.  A chunk is
    mastered once it has been recreated OK at least once (seen counts attempts
    so replays rotate through unmastered chunks)."""
    st = _cur_state(app)
    c = st["chunks"].setdefault(text, {"ok": False, "seen": 0})
    c["seen"] += 1
    if ok:
        c["ok"] = True
    st["last_round"] = round_no
    save_curriculum()


def curriculum_mastered(app):
    """All of the app's chunks recreated correctly?"""
    nodes = lib.apps.get(app, {}).get("nodes", [])
    st = CURRICULUM.get(app, {})
    if not nodes:
        return False
    return all(st.get("chunks", {}).get(_chunk_key(n), {}).get("ok")
               for n in nodes)


def curriculum_in_progress(app):
    """App has SOME mastered chunks but not all (worth re-serving with a
    different missing chunk)."""
    nodes = lib.apps.get(app, {}).get("nodes", [])
    st = CURRICULUM.get(app, {})
    if not nodes or st.get("rebuild_done"):
        return False
    ok = sum(1 for n in nodes
             if st.get("chunks", {}).get(_chunk_key(n), {}).get("ok"))
    return 0 < ok < len(nodes)


def curriculum_unmastered(app):
    """The nodes whose chunks have NOT yet been recreated OK — the different
    missing chunk each time the app returns."""
    st = CURRICULUM.get(app, {})
    return [n for n in lib.apps[app]["nodes"]
            if not st.get("chunks", {}).get(_chunk_key(n), {}).get("ok")]


def rebuild_eligible(app):
    """Small enough that a whole-app SFT row fits the 1024-token window."""
    nodes = lib.apps.get(app, {}).get("nodes", [])
    if not nodes or len(nodes) > REBUILD_MAX_NODES:
        return False
    total = sum(len(n["text"]) for n in nodes)
    return total <= REBUILD_MAX_CHARS


def review_on_miss(app, text, now):
    """Missed a node -> (re)queue it with a growing interval.  Keyed by the
    node TEXT so each distinct chunk gets its own spaced-replay slot."""
    key = (app, text)
    it = REVIEW_QUEUE.get(key)
    if it is None:
        it = {"interval": REVIEW_START_INTERVAL, "streak": 0}
    it["interval"] = min(it.get("interval", REVIEW_START_INTERVAL) * 2, REVIEW_MAX_INTERVAL)
    it["streak"] = 0
    it["due_at"] = now + it["interval"]
    REVIEW_QUEUE[key] = it


def review_on_result(app, text, correct, now):
    """Result of a review replay.  Returns False when the node is mastered
    (2 consecutive correct replays) and should be dropped."""
    key = (app, text)
    it = REVIEW_QUEUE.get(key)
    if it is None:
        return True
    if correct:
        it["streak"] = it.get("streak", 0) + 1
        if it["streak"] >= REVIEW_MASTERY_STREAK:
            del REVIEW_QUEUE[key]
            return False
    else:
        it["streak"] = 0
    it["interval"] = min(it.get("interval", REVIEW_START_INTERVAL) * 2, REVIEW_MAX_INTERVAL)
    it["due_at"] = now + it["interval"]
    return True


def write_episode(ep):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "episodes.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ep) + "\n")


def write_training_rows(puzzle, ep):
    """Training rows for one played puzzle:

    * puzzle_sft  — generation task (goal+purpose -> correct code).  This was
      the ONLY task in the R30 corpus; it teaches generation, not selection.
    * pick_sft    — the TRUE game task: the exact RAG-off eval prompt
      (goal+purpose+candidates) -> "NODE: X" with the correct letter.  Added
      for R31 because the retention eval scores DISCRIMINATION and R30 had
      ZERO rows in this format (the measured pick regression's root cause).
    * puzzle_dpo / pick_dpo — DPO rows on wrong picks (generation form and
      pick form, each paired with its own prompt).
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sft = {
        "round": 30,
        "kind": "puzzle_sft",
        "instruction": f"Build the {puzzle['purpose_label'].lower()} for this app:\n{puzzle['request']}",
        "input": "",
        "output": puzzle["correct_text"],
        "reward": ep["reward"],
        "correct": ep["correct"],
        "app": puzzle["app"],
        "purpose": puzzle["purpose"],
    }
    with (OUT_DIR / "train-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(sft) + "\n")
    # TRUE game format — teaches the model to DISCRIMINATE (the eval task).
    pick_prompt = build_pick_prompt(puzzle)
    pick = {
        "round": 30,
        "kind": "pick_sft",
        "system": SYS_PROMPT,   # same system prompt the eval sends — so the
                                 # training prompt matches the scored prompt
        "instruction": pick_prompt,
        "input": "",
        "output": f"NODE: {puzzle['correct_letter']}",
        "reward": ep["reward"],
        "correct": ep["correct"],
        "app": puzzle["app"],
        "purpose": puzzle["purpose"],
    }
    with (OUT_DIR / "train-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(pick) + "\n")
    if not ep["correct"]:
        chosen = next((n["text"] for n in puzzle["nodes"]
                       if n["letter"] == ep["chosen"]), None)
        if chosen:
            dpo = {
                "round": 30,
                "kind": "puzzle_dpo",
                "prompt": sft["instruction"],
                "chosen": puzzle["correct_text"],
                "rejected": chosen,
                "reward": ep["reward"],
                "app": puzzle["app"],
                "purpose": puzzle["purpose"],
            }
            with (OUT_DIR / "dpo-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(dpo) + "\n")
        # pick-form DPO: teach the correct letter over the one the model chose.
        pick_dpo = {
            "round": 30,
            "kind": "pick_dpo",
            "system": SYS_PROMPT,
            "prompt": pick_prompt,
            "chosen": f"NODE: {puzzle['correct_letter']}",
            "rejected": f"NODE: {ep['chosen']}" if ep["chosen"] else "",
            "reward": ep["reward"],
            "app": puzzle["app"],
            "purpose": puzzle["purpose"],
        }
        if pick_dpo["rejected"] and pick_dpo["rejected"] != pick_dpo["chosen"]:
            with (OUT_DIR / "dpo-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(pick_dpo) + "\n")


def write_reason_rows(puzzle, rres):
    """Training rows for a Stage 4.5 REASON attempt (only banked when the
    model names the correct node AND gives a real reason):

    * reason_sft — the pick prompt plus the request to justify: ->
      "NODE: X\nREASON: <why X, naming the concrete difference>"
      Teaches the model to articulate candidate differences before/while
      choosing — the exact skill the RAG-off eval needs.
    * reason_dpo — when the model names the WRONG node but writes a reason
      anyway: pair its wrong answer against the correct one so the model
      learns that fluent justification of the wrong node loses.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "round": 30,
        "kind": "reason_sft",
        "system": SYS_PROMPT,
        "instruction": build_reason_prompt(puzzle),
        "input": "",
        "output": f"NODE: {puzzle['correct_letter']}\nREASON: {puzzle['reason']}",
        "reward": 1,
        "correct": True,
        "app": puzzle["app"],
        "purpose": puzzle["purpose"],
    }
    with (OUT_DIR / "train-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    if rres.get("chosen") and rres["chosen"] != puzzle["correct_letter"] \
            and rres.get("reason"):
        dpo = {
            "round": 30,
            "kind": "reason_dpo",
            "system": SYS_PROMPT,
            "prompt": build_reason_prompt(puzzle),
            "chosen": f"NODE: {puzzle['correct_letter']}\nREASON: {puzzle['reason']}",
            "rejected": (f"NODE: {rres['chosen']}\nREASON: {rres['reason']}"),
            "reward": -1,
            "app": puzzle["app"],
            "purpose": puzzle["purpose"],
        }
        with (OUT_DIR / "dpo-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dpo) + "\n")


def write_reason_game_rows(puzzle, res, rng):
    """Bank rows for a verdict-step REASONING round.  Two kinds:

    * reason_game_sft — a VERIFIED full chain.  Only banked when the model
      got every verdict right AND cited evidence AND picked consistently.
      The row's output is the model's own (verified) reasoning — teaching
      the *format* of step-by-step candidate elimination.
    * reason_game_dpo — when the chain was wrong/inconsistent: pair the
      coached ground-truth chain (chosen) against the model's actual chain
      (rejected).  Teaches that fluent reasoning to the WRONG answer loses.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inst = f"APP GOAL: {puzzle['request']}\nNODE PURPOSE: {puzzle['purpose_label']}"
    inst += ("\nCANDIDATE NODES — exactly ONE is real for this purpose in THIS "
             "app; decide each one in turn, then the pick:\n")
    for n in puzzle["nodes"]:
        inst += f"NODE {n['letter']}:\n```\n{n['text']}\n```\n"
    inst += ("For each node reply: NODE X: VERDICT: YES|NO — EVIDENCE: <concrete "
             "code difference>, then FINAL: NODE X.")
    chain_ok = bool(res["pick_ok"] and res["consistent"]
                    and all(s["verdict_ok"] and s["evidence_ok"]
                            for s in res["steps"]))
    if chain_ok:
        out = "\n".join(
            f"NODE {s['node']}: VERDICT: {'YES' if s['verdict'] else 'NO'} — "
            f"EVIDENCE: {s['evidence']}" for s in res["steps"])
        out += f"\nFINAL: NODE {puzzle['correct_letter']}"
        row = {"round": 30, "kind": "reason_game_sft",
               "system": SYS_PROMPT, "instruction": inst, "input": "",
               "output": out, "reward": res["total"], "correct": True,
               "app": puzzle["app"], "purpose": puzzle["purpose"]}
        with (OUT_DIR / "train-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    # DPO: always when the chain was not perfect (wrong pick / inconsistency /
    # a missed verdict).  Chosen = coached ground-truth chain.
    if not chain_ok:
        chosen_txt = reason_chain_text(puzzle, res["steps"])
        rejected_txt = "\n".join(
            f"NODE {s['node']}: VERDICT: {'YES' if s['verdict'] else 'NO'} — "
            f"EVIDENCE: {s['evidence']}" for s in res["steps"])
        if res["pick"]:
            rejected_txt += f"\nFINAL: NODE {res['pick']}"
        if rejected_txt.strip():
            dpo = {"round": 30, "kind": "reason_game_dpo",
                   "system": SYS_PROMPT, "prompt": inst,
                   "chosen": chosen_txt, "rejected": rejected_txt,
                   "reward": res["total"],
                   "app": puzzle["app"], "purpose": puzzle["purpose"]}
            with (OUT_DIR / "dpo-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(dpo) + "\n")


STATUS = {"score": 0, "correct": 0, "wrong": 0, "puzzles": 0, "round": 0,
          "tier": None, "current": None, "build": None, "ladder": [],
          "last_ep": None, "ts": None, "done": False,
          "acc": 0.0, "recent_acc": 0.0, "by_tier": {}, "by_rag": {},
          "by_mode": {}, "last_reason": None, "last_reason_game": None,
          "last_completion": None, "rounds_history": [],
          "opt": {"ok": 0, "bad": 0, "keep": 0}, "last_tuneup": None}

# Live controls — mutated by POST /api/control from the scoreboard page.
CONFIG = {"nodes_per_puzzle": 5, "difficulty": "auto", "target_rounds": 1,
          "paused": False, "stop": False,
          "observe": True,         # Stage 1: show the whole app once per round
          "reason": True,          # Stage 4.5: justify a correct pick
          "reason_chance": 50,     # classic-flow % chance a correct pick is reasoned
          "reason_game_cadence": 0,  # every N-th round is a verdict-step reasoning round (0 = off)
          "completion": True,      # Stage 4 (recreate): write back missing code
          "completion_pct": 40,    # % of each candidate chunk to remove
          "completion_chance": 50, # classic-flow % chance a solved puzzle replays
          "gate_acc": 0.0,         # accuracy gate: 0=off; else % target
          "_wake": False}          # ▶ Resume latched — breaks the round-limit idle wait

# Accuracy gate: when gate_acc > 0 AND difficulty is pinned (not "auto"), the
# round limit is ignored and the trainer plays until the rolling accuracy over
# the last GATE_WINDOW fresh (non-review) picks at that tier meets the gate,
# then it pauses so the difficulty can be promoted (gate carries up).
GATE_WINDOW = 40
GATE = {"tier": None, "target": None, "window": [], "pct": 0.0}

RECENT = []           # last 20 correctness flags (for the learning % tracker)
SESSION_USED = {}     # app_name -> set of node texts already played this epoch

# Mastery-gated progression: each tier runs learning -> speed -> promoted.
# LEARNING: solve same-tier builds until rolling accuracy >= MASTERY_PCT over
#           MASTERY_WINDOW picks (the LLM proves it understands the tier).
# SPEED   : same-tier builds under the clock; best round time tracked; once the
#           time stops improving for SPEED_PLATEAU_ROUNDS (its speed limit),
#           the tier is promoted and we move UP a difficulty tier.
MASTERY_WINDOW = 12
MASTERY_PCT = 70.0
MASTERY_RAGOFF_WINDOW = 10   # no-RAG picks needed before a tier can promote
MASTERY_RAGOFF_PCT = 60.0    # no-RAG accuracy floor — "mastered" = builds it
                             # WITHOUT the reference library
SPEED_MIN_ROUNDS = 3       # min rounds before a tier can leave speed phase
SPEED_PLATEAU_ROUNDS = 3   # consecutive non-improving rounds -> hit the limit
TIER_ORDER = ["easy", "medium", "hard", "extreme"]

PROGRESS = {
    t: {"phase": "learning", "recent": [], "mastery_pct": 0.0,
        "mastered": False, "round_times": [], "best_round_s": None,
        "plateau_rounds": 0, "speed_bonuses": 0, "promoted": False,
        "ragoff_recent": [], "ragoff_pct": 0.0}
    for t in TIER_ORDER
}


def mark_node_used(app_name, text):
    SESSION_USED.setdefault(app_name, set()).add(text)

LAST_APP = None   # app served in the previous round — rotation avoids repeats


def pick_puzzle_app(rng, tier, strict=False):
    """Pick an app with UNPLAYED nodes from the requested tier, ROTATING so
    consecutive rounds never serve the same puzzle.  In strict mode
    (mastery/speed phases) ONLY that tier's builds are offered so the LLM
    proves itself against the same tier before promotion.  When the tier's
    builds are exhausted, a fresh epoch begins with a RESHUFFLED rotation
    (not the same order), and the app played last round is skipped when any
    alternative exists.

    CURRICULUM PREFERENCE: apps already in progress (some chunks mastered, not
    all) are served FIRST, and only their UNMASTERED chunks are offered — so
    the same app returns with a DIFFERENT chunk missing each pass, cycling
    through the app until every chunk is recreated correctly."""
    global LAST_APP
    def remaining(name):
        used = SESSION_USED.get(name, set())
        return [n for n in lib.apps[name]["nodes"] if n["text"] not in used]
    def tier_apps():
        for t in (tier,) if strict else (tier, "easy", "medium", "hard", "extreme"):
            cands = [n for n in lib.tiers.get(t, [])]
            if cands:
                return cands
        return []
    def tier_pool():
        return [n for n in tier_apps() if remaining(n)]
    # 1) in-progress apps from this tier range: serve their unmastered chunks
    in_prog = [n for n in tier_apps() if curriculum_in_progress(n)]
    if in_prog:
        if LAST_APP in in_prog and len(in_prog) > 1:
            in_prog = [n for n in in_prog if n != LAST_APP]
        name = rng.choice(in_prog)
        LAST_APP = name
        nodes = curriculum_unmastered(name)
        rng.shuffle(nodes)
        return name, nodes
    pool = tier_pool()
    if not pool:
        # tier exhausted -> NEW epoch: reshuffle the rotation so the next pass
        # serves a different order (no immediate repeats of the same puzzle).
        SESSION_USED.clear()
        pool = tier_pool()
        if not pool:
            pool = [n for n in lib.apps if remaining(n)]
        rng.shuffle(pool)
    if not pool:
        return None, []
    # rotation: never serve the app from the previous round when we can avoid it
    if LAST_APP in pool and len(pool) > 1:
        pool = [n for n in pool if n != LAST_APP]
    name = rng.choice(pool)
    LAST_APP = name
    nodes = remaining(name)
    rng.shuffle(nodes)
    return name, nodes


def update_learning_stats(ep, tier):
    """Percentages: overall accuracy, recent-20 accuracy, per-tier accuracy,
    and the per-tier mastery window (rolling MASTERY_WINDOW picks)."""
    RECENT.append(ep["correct"])
    if len(RECENT) > 20:
        RECENT.pop(0)
    STATUS["acc"] = round(100 * STATUS["correct"] / max(STATUS["puzzles"], 1), 1)
    STATUS["recent_acc"] = round(100 * sum(RECENT) / len(RECENT), 1) if RECENT else 0.0
    bt = STATUS["by_tier"].setdefault(tier, {"correct": 0, "total": 0})
    bt["correct"] += int(ep["correct"])
    bt["total"] += 1
    # accuracy split by RAG on/off — proves the model can build WITHOUT
    # retrieval once it has internalized the patterns (time-trial phase).
    ragk = "on" if ep.get("rag") else "off"
    brd = STATUS.setdefault("by_rag", {})
    br = brd.setdefault(ragk, {"correct": 0, "total": 0})
    br["correct"] += int(ep["correct"])
    br["total"] += 1
    prog = PROGRESS.setdefault(tier, {"phase": "learning", "recent": []})
    if prog["phase"] == "learning":
        prog["recent"].append(ep["correct"])
        if len(prog["recent"]) > MASTERY_WINDOW:
            prog["recent"].pop(0)
        prog["mastery_pct"] = round(100 * sum(prog["recent"]) / len(prog["recent"]), 1)
        if (len(prog["recent"]) >= MASTERY_WINDOW
                and prog["mastery_pct"] >= MASTERY_PCT):
            prog["mastered"] = True
            prog["phase"] = "speed"
            prog["recent"] = []
            print(f"\n🎓 MASTERED {tier.upper()} (acc {prog['mastery_pct']}% over "
                  f"{MASTERY_WINDOW}) — entering TIME TRIALS")
            STATUS.setdefault("events", []).append(
                {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "tier": tier, "event": f"mastered (acc {prog['mastery_pct']}%)",
                 "phase": "speed"})
    # no-RAG proof tracker: time trials run WITHOUT reference (see
    # --no-rag-speed); rolling accuracy there is the true mastery gate.
    if not ep.get("rag"):
        ro = prog.setdefault("ragoff_recent", [])
        ro.append(bool(ep["correct"]))
        if len(ro) > MASTERY_RAGOFF_WINDOW:
            ro.pop(0)
        prog["ragoff_pct"] = round(100 * sum(ro) / max(len(ro), 1), 1)
    # accuracy-gate tracker (pinned-difficulty mode): fresh picks only —
    # review replays of the model's own misses must not deflate the gate.
    if CONFIG.get("gate_acc") and not ep.get("review"):
        gw = GATE["window"]
        gw.append(bool(ep["correct"]))
        if len(gw) > GATE_WINDOW:
            gw.pop(0)
        GATE["pct"] = round(100 * sum(gw) / max(len(gw), 1), 1)


def status_reset_build(app_name, tier):
    """Reset the 'app under construction' view: nodes fill in as solved."""
    STATUS["build"] = {
        "app": app_name, "tier": tier, "total": 0, "solved": 0,
        "parts": [],            # [{purpose, letter, kind, text, solved, chosen}]
        "assembled": "",        # concatenated correct chunks, in solve order
    }


def save_status():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "status.json").write_text(json.dumps(STATUS, indent=1))


def play_puzzle(puzzle, llm_url, model, rng, rag=True, max_retries=2):
    reference = []
    if rag:
        reference = lib.reference_for(puzzle["purpose"], puzzle["app"], puzzle["request"])
    messages = build_messages(puzzle, reference)
    t0 = time.time()
    reply, chosen = None, None
    for _ in range(max_retries + 1):
        reply = llm_chat(llm_url, model, messages)
        chosen = parse_choice(reply)
        if chosen:
            break
    correct = chosen == puzzle["correct_letter"]
    return {
        "chosen": chosen,
        "correct": correct,
        "reply": reply,
        "latency_s": round(time.time() - t0, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Completion (cloze) — on puzzles the LLM completed, a section of EACH
#  candidate node (correct + fakes) is removed and the LLM must BOTH choose
#  the correct node AND write back the missing code.  Teaches generation on
#  top of discrimination.  Controls on the scoreboard: on/off toggle, remove-%
#  (how much of each chunk to blank), chance-% (how often a solved puzzle is
#  replayed this way).  Rewards: choice (+10/-5) + fill bonus (+15).
# ─────────────────────────────────────────────────────────────────────────────
FILL_SIM_OK = 0.70          # fill similarity floor for the +15 fill bonus
_MISS_PLACEHOLDER = "/* ⟦MISSING CODE — write the removed code here⟧ */"


def mask_chunk(text, pct, variant=0):
    """Remove a contiguous span (~pct% of the lines) from a chunk.
    Returns (masked_text, removed_text).  The span is centered for
    variant=0; higher variants shift the hole along the chunk so a REPLAYED
    node has a DIFFERENT section removed — the model must re-derive what is
    missing instead of recognizing the same hole."""
    pct = max(5, min(95, int(pct)))
    lines = text.split("\n")
    if len(lines) < 3:
        n = max(1, int(len(text) * pct / 100))
        if variant:
            span = len(text) - n
            start = min(max(0, int(span * (variant % 7) / 7)), span) if span > 0 else 0
        else:
            start = max(0, (len(text) - n) // 2)
        removed = text[start:start + n]
        masked = text[:start] + "\n" + _MISS_PLACEHOLDER + "\n" + text[start + n:]
        return masked, removed
    n = max(1, int(len(lines) * pct / 100))
    if variant:
        # slide the window across the chunk in 7 positions (0..6 pattern)
        max_start = max(0, len(lines) - n)
        start = min(max_start, int(max_start * ((variant % 7) / 7)))
    else:
        start = max(0, (len(lines) - n) // 2)
    end = min(len(lines), start + n)
    removed = "\n".join(lines[start:end])
    masked = "\n".join(lines[:start] + [_MISS_PLACEHOLDER] + lines[end:])
    return masked, removed


def fill_similarity(a, b):
    """Whitespace-insensitive similarity of two code snippets (0..1)."""
    a = re.sub(r"\s+", " ", (a or "")).strip()
    b = re.sub(r"\s+", " ", (b or "")).strip()
    if not a or not b:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def build_completion_messages(puzzle, reference, masked_nodes):
    ref_text = "\n\n".join(f"```\n{r}\n```" for r in reference)
    parts = [
        f"APP GOAL: {puzzle['request']}",
        f"NODE PURPOSE: {puzzle['purpose_label']}",
        "",
        "REFERENCE (how other apps implement this node type — retrieved from the library):",
        ref_text if ref_text else "(none retrieved)",
        "",
        "CANDIDATE NODES — exactly ONE is correct for this purpose in THIS app.",
        "Each candidate has a section REMOVED (marked ⟦MISSING CODE⟧).",
        "",
    ]
    for n in masked_nodes:
        parts.append(f"NODE {n['letter']}:\n```\n{n['text']}\n```")
    parts.append("First choose the correct node, then write back the code that "
                 "was removed from it. Reply with exactly:\nNODE: X\nCODE:\n"
                 "<the missing code>")
    user = "\n\n".join(parts)
    return [{"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user}]


def parse_completion(text):
    """(letter, code) from a completion reply.  The letter is read only from
    the part before CODE: so code content can't confuse the choice."""
    head = re.split(r"\bCODE\s*[:=]", text or "", maxsplit=1, flags=re.I)
    letter = parse_choice(head[0]) if head else None
    code = head[1].strip() if len(head) > 1 else None
    if code:
        code = re.sub(r"^```[a-zA-Z]*\n?", "", code).strip()
        code = re.sub(r"\n?```$", "", code).strip()
    return letter, (code or None)


MASK_REPLAYS = {}   # (app, purpose) -> number of times this node was replayed


def play_completion(puzzle, llm_url, model, rng, rag=True, pct=40, max_retries=1):
    """Mask every candidate of a SOLVED puzzle, ask for NODE: X + CODE:.
    Returns {chosen, correct, written, removed, fill_sim, fill_ok, reply,
    latency_s, masked_nodes, mask_variant}.  Replays of the same node remove a
    DIFFERENT section each time (variant rotates 0,1,2,..) so the model has to
    rethink what is missing rather than memorizing the hole."""
    key = (puzzle["app"], puzzle["purpose"])
    variant = MASK_REPLAYS.get(key, 0)
    MASK_REPLAYS[key] = variant + 1
    masked_nodes, removed_by_letter = [], {}
    for n in puzzle["nodes"]:
        masked, removed = mask_chunk(n["text"], pct, variant=variant)
        masked_nodes.append({"letter": n["letter"], "kind": n["kind"],
                             "text": masked})
        removed_by_letter[n["letter"]] = removed
    reference = []
    if rag:
        reference = lib.reference_for(puzzle["purpose"], puzzle["app"], puzzle["request"])
    messages = build_completion_messages(puzzle, reference, masked_nodes)
    t0 = time.time()
    reply, chosen, code = None, None, None
    for _ in range(max_retries + 1):
        try:
            reply = llm_chat(llm_url, model, messages, max_tokens=700, temperature=0.4)
        except Exception:
            reply = None
        if not reply:
            continue
        chosen, code = parse_completion(reply)
        if chosen:
            break
    correct = chosen == puzzle["correct_letter"]
    removed = removed_by_letter.get(puzzle["correct_letter"], "")
    sim = fill_similarity(code, removed) if code else 0.0
    fill_ok = bool(correct and code and sim >= FILL_SIM_OK)
    return {"chosen": chosen, "correct": correct, "written": code,
            "removed": removed, "fill_sim": round(sim, 3), "fill_ok": fill_ok,
            "reply": reply, "latency_s": round(time.time() - t0, 2),
            "masked_nodes": masked_nodes, "mask_variant": variant}


def write_completion_rows(puzzle, ep, cres):
    """SFT row: fill the missing code (output = the removed ground-truth, with
    the masked candidates in the instruction).  DPO row on a wrong fill or a
    wrong choice."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    masked_cands = "\n\n".join(
        f"NODE {n['letter']}:\n```\n{n['text']}\n```" for n in cres["masked_nodes"])
    instr = (f"Complete the missing code (⟦MISSING CODE⟧) for the correct "
             f"{puzzle['purpose_label'].lower()} node of this app:\n"
             f"{puzzle['request']}\n\nCandidate nodes (one is correct; each has "
             f"a section removed):\n{masked_cands}\n\nWrite back the missing "
             f"code for the CORRECT node.")
    sft = {
        "round": 30, "kind": "completion_sft",
        "instruction": instr, "input": "", "output": cres["removed"],
        "reward": ep["reward"], "correct": ep["correct"],
        "fill_sim": cres["fill_sim"], "fill_ok": cres["fill_ok"],
        "app": puzzle["app"], "purpose": puzzle["purpose"],
    }
    with (OUT_DIR / "train-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(sft) + "\n")
    if not (ep["correct"] and cres["fill_ok"]):
        dpo_rejected = None
        if cres["written"] and not cres["fill_ok"] and ep["correct"]:
            dpo_rejected = cres["written"]      # bad fill — teach the right one
        elif not ep["correct"]:
            dpo_rejected = next((n["text"] for n in puzzle["nodes"]
                                 if n["letter"] == cres["chosen"]), None)
        if dpo_rejected and dpo_rejected != cres["removed"]:
            dpo = {
                "round": 30, "kind": "completion_dpo",
                "prompt": instr,
                "chosen": cres["removed"], "rejected": dpo_rejected,
                "reward": ep["reward"], "fill_sim": cres["fill_sim"],
                "app": puzzle["app"], "purpose": puzzle["purpose"],
            }
            with (OUT_DIR / "dpo-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(dpo) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
#  REBUILD — the curriculum finale: after every chunk of a small app has been
#  recreated correctly, show ONLY the goal and ask for the whole app from
#  memory.  Scored by structural integrity + similarity to the assembled
#  ground truth (+100 / -30).  Writes rebuild_sft rows (goal -> full app).
# ─────────────────────────────────────────────────────────────────────────────
def build_rebuild_messages(app_name):
    """Goal-only prompt — no observe re-show, no candidates, no reference.
    The model must write the complete app from memory."""
    request = lib.apps.get(app_name, {}).get("request", "")
    parts = [
        f"APP GOAL: {request}",
        "",
        "You studied this app's full design once and recreated every section "
        "of it. Now rebuild the COMPLETE app from memory — every section, in "
        "the right order, fully working.",
        "",
        "Reply with exactly:",
        "CODE:",
        "<the complete app>",
    ]
    user = "\n\n".join(parts)
    return [{"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user}]


def rebuild_ground_truth(app_name):
    """The correct whole app: the app's node texts in library order."""
    return "\n\n".join(n["text"] for n in lib.apps[app_name]["nodes"])


def play_rebuild(app_name, llm_url, model):
    """Stage REBUILD — write the whole app from memory.  Returns {ok, sim,
    written, reply, latency_s, reward}."""
    gt = rebuild_ground_truth(app_name)
    t0 = time.time()
    reply = llm_chat(llm_url, model, build_rebuild_messages(app_name),
                     max_tokens=1200, temperature=0.2)
    _, code = parse_completion(reply)
    sim = fill_similarity(code, gt) if code else 0.0
    ok = bool(code and structural_ok(code) and sim >= REBUILD_SIM_OK)
    reward = REWARDS["rebuild_ok"] if ok else REWARDS["rebuild_bad"]
    return {"ok": ok, "sim": round(sim, 3), "written": code, "reply": reply,
            "latency_s": round(time.time() - t0, 2), "reward": reward}


def write_rebuild_rows(app_name, rb, round_no):
    """SFT row: goal -> full app (the memory-retention target).  Only for
    eligible (small) apps so the row fits MAX_SEQ."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    request = lib.apps.get(app_name, {}).get("request", "")
    gt = rebuild_ground_truth(app_name)
    instr = (f"Rebuild this complete app from memory (you saw the full design "
             f"once):\nAPP GOAL: {request}")
    sft = {"round": 30, "kind": "rebuild_sft",
           "instruction": instr, "input": "", "output": gt,
           "reward": rb["reward"], "ok": rb["ok"], "sim": rb["sim"],
           "app": app_name, "system": SYS_PROMPT}
    with (OUT_DIR / "train-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(sft) + "\n")
    if not rb["ok"] and rb.get("written"):
        dpo = {"round": 30, "kind": "rebuild_dpo", "prompt": instr,
               "chosen": gt, "rejected": rb["written"],
               "reward": rb["reward"], "sim": rb["sim"], "app": app_name}
        with (OUT_DIR / "dpo-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dpo) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Tune-up — the LLM may rewrite a node it JUST solved correctly, chasing a
#  speed bonus.  Validated before any reward: syntax + behavior preserved +
#  provably leaner.  Invalid edits cost points and the original is kept.
# ─────────────────────────────────────────────────────────────────────────────
_NODE_OK = None   # cached shutil.which("node")


def node_bin():
    global _NODE_OK
    if _NODE_OK is None:
        import shutil
        _NODE_OK = shutil.which("node")
    return _NODE_OK


def structural_ok(code: str):
    """Balance check for JS/CSS/HTML — catches truncated or mangled output
    without node (which would reject CSS/HTML outright)."""
    for op, cl in [("{", "}"), ("(", ")"), ("[", "]")]:
        if code.count(op) != code.count(cl):
            return False
    return bool(code.strip())


def js_syntax_ok(code: str):
    """Quick syntax gate: `node --check` when available, else brace balance."""
    nb = node_bin()
    if nb:
        import subprocess, tempfile, os
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(code)
                tmp = f.name
            r = subprocess.run([nb, "--check", tmp], capture_output=True,
                               timeout=15, text=True)
            os.unlink(tmp)
            return r.returncode == 0
        except Exception:
            pass
    for op, cl in [("{", "}"), ("(", ")"), ("[", "]")]:
        if code.count(op) != code.count(cl):
            return False
    return bool(code.strip())


_JS_ID_RE = re.compile(r"(?:function\s+(\w+)|\b(?:const|let|var)\s+(\w+)|getElementById\(['\"]([^'\"]+)|querySelector(?:All)?\(['\"]([^'\"]+)|addEventListener\(['\"]([^'\"]+))")


def js_identifiers(code: str):
    """The set of behavior-carrying identifiers a node must keep: function
    names, declared vars, DOM ids, selectors, event names."""
    out = set()
    for m in _JS_ID_RE.finditer(code):
        out.add(m.group(1) or m.group(2) or m.group(3) or m.group(4) or m.group(5))
    # canvas ctx variable (from `const ctx = canvas.getContext('2d')`)
    m = re.search(r"\b(?:const|let|var)\s+(\w+)\s*=\s*\w+\.getContext\s*\(", code)
    if m:
        out.add(m.group(1))
    out.discard(None)
    return out


_SPEED_OPS = [
    (r"getElementById\s*\(", 3), (r"querySelector(?:All)?\s*\(", 3),
    (r"getElementsBy\w+\s*\(", 3),
    (r"\binnerHTML\b", 2), (r"\btextContent\b", 2),
    (r"appendChild\s*\(", 2), (r"insertBefore\s*\(", 2),
    (r"\.forEach\s*\(", 2), (r"\.map\s*\(", 2), (r"\.filter\s*\(", 2),
    (r"\.reduce\s*\(", 2), (r"\.sort\s*\(", 2),
]
# loop constructs — ops nested inside one of these are executed repeatedly,
# so they are penalized (each enclosing loop multiplies the op's cost).
_LOOP_RES = [
    re.compile(r"\bfor\s*\("), re.compile(r"\bwhile\s*\("),
    re.compile(r"\.forEach\s*\("), re.compile(r"\.map\s*\("),
    re.compile(r"\.filter\s*\("), re.compile(r"\.reduce\s*\("),
]


def speed_score(code):
    """Static proxy for how expensive the code is to run.  Each expensive op
    (DOM lookup / write / iterator) counts once for the op plus 2 extra points
    per enclosing loop — so HOISTING a lookup out of a loop lowers the score
    (that's the 'faster' improvement the OPTIMIZE stage rewards)."""
    loop_marks = [False] * len(code)
    for lre in _LOOP_RES:
        for m in lre.finditer(code):
            # mark everything after the loop's opening paren as "inside" (a
            # conservative approximation — good enough to reward hoisting)
            for i in range(m.end() - 1, len(code)):
                loop_marks[i] = True
    total = 0
    for pat, w in _SPEED_OPS:
        for m in re.finditer(pat, code):
            penalty = 2 if loop_marks[m.start()] else 0
            total += w + penalty
    return total


def validate_optimization(orig, prop):
    """(valid, smaller, faster, reason).  Behavior preserved = every identifier
    the original node exposes is still present, plus the code passes syntax.
    smaller = fewer chars; faster = fewer expensive ops (static proxy).
    A rewrite must achieve at least one to count as an optimization."""
    if not prop or len(prop.strip()) < MIN_CHUNK:
        return False, False, False, "empty or truncated"
    if not structural_ok(prop):
        return False, False, False, "unbalanced syntax (truncated?)"
    missing = js_identifiers(orig) - js_identifiers(prop)
    if missing:
        return False, False, False, f"dropped identifiers: {sorted(missing)[:4]}"
    smaller = len(prop) < 0.95 * len(orig)
    faster = speed_score(prop) < speed_score(orig)
    if not (smaller or faster):
        return False, False, False, "no improvement (not smaller and not faster)"
    return True, smaller, faster, "improved"


def parse_tuneup(text):
    """(action, code): action in {"keep", "optimize", "empty"}."""
    if not text:
        return "empty", None
    if re.search(r"\bKEEP\b", text) and "OPTIMIZE" not in text:
        return "keep", None
    m = re.search(r"OPTIMIZE\s*[:=]?\s*(?:```(?:js|javascript)?\s*)?(.*)", text, re.S)
    if not m:
        return "empty", None
    code = m.group(1).strip()
    code = re.sub(r"```\s*$", "", code).strip()
    if not code:
        return "empty", None
    return "optimize", code


def build_tuneup_messages(puzzle):
    user = (f"APP GOAL: {puzzle['request']}\n"
            f"NODE PURPOSE: {puzzle['purpose_label']}\n\n"
            f"SOLVED NODE (already correct — this is the baseline):\n"
            f"```\n{puzzle['correct_text']}\n```\n\n"
            "Rewrite it to be FASTER and SMALLER — each improvement is "
            "rewarded separately, doing both pays double.  Same behavior, "
            "same identifiers.  Reply OPTIMIZE: <the improved code>.")
    return [{"role": "system", "content": OPTIMIZER_SYS},
            {"role": "user", "content": user}]


def run_tuneup(puzzle, llm_url, model):
    """Offer the LLM a chance to optimize the node it just solved.
    Returns {action, code, valid, smaller, faster, reason, reward, latency_s}.
    Reward = REWARDS['optimize'] per achieved type (smaller AND/OR faster), so
    doing both pays DOUBLE the single-type reward."""
    t0 = time.time()
    try:
        reply = llm_chat(llm_url, model, build_tuneup_messages(puzzle),
                         max_tokens=700, temperature=0.6)
    except Exception as e:
        return {"action": "empty", "code": None, "valid": False,
                "smaller": False, "faster": False,
                "reason": f"llm error: {e}", "reward": 0, "latency_s": 0}
    action, code = parse_tuneup(reply)
    if action != "optimize":
        reward = REWARDS["optimize_keep"] if action == "keep" else 0
        return {"action": action, "code": code, "valid": False,
                "smaller": False, "faster": False,
                "reason": "kept original", "reward": reward,
                "latency_s": round(time.time() - t0, 2)}
    valid, smaller, faster, reason = validate_optimization(puzzle["correct_text"], code)
    if valid:
        reward = 0
        if smaller:
            reward += REWARDS["optimize"]      # smaller: +15
        if faster:
            reward += REWARDS["optimize"]      # faster: +15 (both = +30, double)
    else:
        reward = REWARDS["optimize_bad"] if reason != "no improvement (not smaller and not faster)" else 0
    return {"action": "optimize", "code": code[:400], "valid": valid,
            "smaller": smaller, "faster": faster, "reason": reason,
            "reward": reward, "latency_s": round(time.time() - t0, 2)}


def play_reason_round(round_no, llm_url, model, rng, rag=True, tier="easy",
                      strict_tier=False, review_nodes=None):
    """A DEDICATED reasoning round — ONE node played as a verdict-step
    walkthrough (each candidate judged YES/NO + concrete evidence, THEN the
    pick).  Returns None on failure (no chunkable app / unbuildable puzzle).
    Does NOT touch the curriculum/REVIEW_QUEUE — reasoning rounds are pure
    practice that bank verified reasoning rows."""
    if review_nodes:
        app_name = review_nodes[0]["_app"]
        node = dict(review_nodes[0]); node.pop("_app", None)
        tag = "🔁 REVIEW-REASON"
    else:
        app_name, app_nodes = pick_puzzle_app(rng, tier, strict=strict_tier)
        if not app_nodes:
            print("  ⚠️ no apps chunkable for a reasoning round", file=sys.stderr)
            return None
        node = dict(app_nodes[0])
        tag = "🧠 REASON"
    # reasoning fakes stay ANSWERABLE (same sim-cap as normal serve-time play)
    subtle_mut, near_xapp = fake_knobs(tier)
    sim_cap = None if tier == "extreme" else FAKE_SIM_CAP
    puzzle = lib.make_puzzle(app_name, node, rng,
                             subtle_mut=subtle_mut, near_xapp=near_xapp,
                             sim_cap=sim_cap)
    if puzzle is None:
        print(f"  ⚠️ couldn't build a reasoning puzzle for {app_name}",
              file=sys.stderr)
        return None
    STATUS["current"] = {"app": puzzle["app"], "purpose": puzzle["purpose_label"],
                          "tier": tier, "mode": "reason-game",
                          "node": "1/1", "reasoning": True,
                          "nodes": [{"letter": n["letter"], "kind": n["kind"],
                                      "text": n["text"][:200]} for n in puzzle["nodes"]],
                          "correct_letter": puzzle["correct_letter"]}
    save_status()
    res = play_reason_game(puzzle, llm_url, model, rag=rag)
    STATUS["score"] += res["total"]
    STATUS["puzzles"] += 1
    STATUS["by_mode"].setdefault("reason_game", {"puzzles": 0, "verdicts": 0,
                                                 "verdict_ok": 0, "ev_ok": 0,
                                                 "pick_ok": 0, "pts": 0})
    rg = STATUS["by_mode"]["reason_game"]
    rg["puzzles"] += 1
    for s in res["steps"]:
        rg["verdicts"] += 1
        rg["verdict_ok"] += int(s["verdict_ok"])
        rg["ev_ok"] += int(s["evidence_ok"])
    rg["pick_ok"] += int(res["pick_ok"])
    rg["pts"] += res["total"]
    ep = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
          "round": round_no, "tier": tier, "app": puzzle["app"],
          "purpose": puzzle["purpose"], "purpose_label": puzzle["purpose_label"],
          "reason_game": True, "rag": rag, "review": bool(review_nodes),
          "correct_letter": puzzle["correct_letter"], "chosen": res["pick"],
          "correct": res["pick_ok"], "consistent": res["consistent"],
          "steps": [{k: s[k] for k in ("node", "kind", "verdict",
                                        "verdict_ok", "evidence_ok", "points")}
                     for s in res["steps"]],
          "total": res["total"], "latency_s": res["latency_s"]}
    write_episode(ep)
    write_reason_game_rows(puzzle, res, rng)
    STATUS["last_reason_game"] = ep
    save_status()
    print(f"{tag} {round_no} — {puzzle['app']} · {puzzle['purpose_label']}")
    for s in res["steps"]:
        v = "YES" if s["verdict"] else "NO"
        if s["verdict"] is None:
            v = "?"
        print(f"    NODE {s['node']}: {v} "
              f"{'✅' if s['verdict_ok'] else '❌'}"
              f"{'🔬' if s['evidence_ok'] else ''} "
              f"{s['evidence'][:70]} ({s['points']:+d})")
    m = "✅" if (res["pick_ok"] and res["consistent"]) else \
        ("⚖️" if res["consistent"] else "❌ inconsistent")
    print(f"    FINAL: NODE {res['pick']} {m} → total {res['total']:+d} "
          f"({res['latency_s']}s)")
    return res


def play_round(round_no, llm_url, model, rng, rag=True, nodes_per_puzzle=5,
               tier="easy", strict_tier=False, tuneup_pct=0.0,
               review_nodes=None, flow="full"):
    """One puzzle = one app: play up to nodes_per_puzzle of its nodes.
    tier: 'easy' | 'medium' | 'hard' — apps are drawn from that tier.
    strict_tier: only that tier's builds (mastery/speed phases).
    review_nodes: optional list of {purpose, text, score, _app} to replay
        instead of picking a fresh app (spaced-replay review round).
    Returns dict {app, tier, solved, total, correct, wrong, score, time_s,
                  speed, per_node} where per_node is [{app, purpose, correct}]
                  for every played node."""
    rounds_file = load_rounds_file()
    if review_nodes:
        app_name = review_nodes[0]["_app"]
        app_nodes = [dict(n) for n in review_nodes]
        for n in app_nodes:
            n.pop("_app", None)
        tag = "🔁 REVIEW"
    else:
        app_name, app_nodes = pick_puzzle_app(rng, tier, strict=strict_tier)
        if not app_nodes:
            print("❌ no apps chunkable — check exports dir", file=sys.stderr)
            return None
        app_nodes = [n for n in app_nodes if n["score"] >= 2] or app_nodes
        app_nodes = app_nodes[:nodes_per_puzzle]
        for n in app_nodes:
            mark_node_used(app_name, n["text"])
        tag = "🎮 ROUND"
    STATUS["round"] = round_no
    STATUS["tier"] = tier
    status_reset_build(app_name, tier)
    STATUS["build"]["total"] = len(app_nodes)

    subtle_mut, near_xapp = fake_knobs(tier)
    # Serve-time fake quality: below extreme, fakes must be answerable
    # (not > FAKE_SIM_CAP similar to the correct chunk).  Extreme keeps
    # near-twin fakes — that's the tier's whole point.
    sim_cap = None if tier == "extreme" else FAKE_SIM_CAP
    print(f"\n{tag} {round_no} — [{'REVIEW' if review_nodes else tier.upper()}] puzzle app: {app_name} ({len(app_nodes)} nodes)")
    t0 = time.time()
    round_score = 0
    per_node = []
    # Stage 1 — OBSERVE: the WHOLE app is shown ONCE, the first time the app
    # is served — that is the memory source.  On curriculum replays (the same
    # app returns with a DIFFERENT chunk missing) observe is SKIPPED: the
    # model must hold the design in memory.  Skipped for review rounds too.
    first_pass = (app_name not in CURRICULUM
                  or CURRICULUM.get(app_name, {}).get("observe_round") is None)
    if (flow == "full" and not review_nodes
            and CONFIG.get("observe", True) and first_pass):
        st = _cur_state(app_name)
        st["observe_round"] = round_no
        save_curriculum()
        try:
            request = lib.apps.get(app_name, {}).get("request", "")
            # observe shows the FULL app (library order) — the whole design
            # the model must remember across all future chunk replays
            full_nodes = lib.apps.get(app_name, {}).get("nodes", app_nodes)
            obs = observe_app(request, full_nodes, llm_url, model)
            STATUS["last_observe"] = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                      "app": app_name, "reply": obs["reply"],
                                      "latency_s": obs["latency_s"],
                                      "curriculum": True}
            save_status()
            print(f"  👁 observe: whole app shown ({len(full_nodes)} sections) — "
                  f"{obs['reply'][:40]!r} ({obs['latency_s']}s)")
        except Exception as e:
            print(f"  ⚠️ observe failed (continuing): {e}")
    for i, node in enumerate(app_nodes, 1):
        puzzle = lib.make_puzzle(app_name, node, rng,
                                 subtle_mut=subtle_mut, near_xapp=near_xapp,
                                 sim_cap=sim_cap)
        if puzzle is None:
            print(f"  ⚠️ [{i}/{len(app_nodes)}] skipping {node['purpose']} — "
                  f"couldn't build 3 distinct candidates")
            continue
        STATUS["current"] = {
            "app": puzzle["app"], "purpose": puzzle["purpose_label"],
            "tier": tier,
            "node": f"{i}/{len(app_nodes)}", "nodes": [
                {"letter": n["letter"], "kind": n["kind"],
                 "text": n["text"][:200] + ("…" if len(n["text"]) > 200 else "")}
                for n in puzzle["nodes"]],
            "correct_letter": puzzle["correct_letter"],
        }
        save_status()
        res = play_puzzle(puzzle, llm_url, model, rng, rag=rag)
        reward = REWARDS["correct"] if res["correct"] else REWARDS["wrong"]
        round_score += reward
        STATUS["score"] += reward
        STATUS["puzzles"] += 1
        STATUS["correct"] += int(res["correct"])
        STATUS["wrong"] += int(not res["correct"])
        ep = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "round": round_no, "tier": tier,
            "app": puzzle["app"],
            "purpose": puzzle["purpose"],
            "purpose_label": puzzle["purpose_label"],
            "correct_letter": puzzle["correct_letter"],
            "chosen": res["chosen"],
            "correct": res["correct"],
            "reward": reward,
            "latency_s": res["latency_s"],
            "reply": res["reply"],
            "rag": rag,
            "review": bool(review_nodes),
        }
        write_episode(ep)
        write_training_rows(puzzle, ep)
        STATUS["last_ep"] = ep
        update_learning_stats(ep, tier)
        # adaptive difficulty: remember which fake kind fooled the model
        if not res["correct"]:
            _ck = next((n["kind"] for n in puzzle["nodes"]
                        if n["letter"] == res["chosen"]), None)
            if _ck == "FAKE-MUT":
                ADAPT["fooled_mut"] += 1
            elif _ck == "FAKE-XAPP":
                ADAPT["fooled_xapp"] += 1
        # build view: mark the correct node solved; append its code
        for n in puzzle["nodes"]:
            if n["letter"] == puzzle["correct_letter"]:
                STATUS["build"]["parts"].append({
                    "purpose": puzzle["purpose_label"], "letter": n["letter"],
                    "kind": n["kind"], "text": n["text"],
                    "solved": res["correct"], "chosen": res["chosen"],
                })
                if res["correct"]:
                    STATUS["build"]["solved"] += 1
                    STATUS["build"]["assembled"] += ("\n\n// ── " +
                        puzzle["purpose_label"].upper() + " ──\n" + n["text"])
        save_status()
        per_node.append({"app": puzzle["app"], "purpose": puzzle["purpose"],
                         "text": puzzle["correct_text"],
                         "correct": res["correct"]})
        mark = "✅" if res["correct"] else "❌"
        print(f"  {mark} [{i}/{len(app_nodes)}] {PURPOSE_LABELS.get(puzzle['purpose'], puzzle['purpose'])}: "
              f"correct={puzzle['correct_letter']} chose={res['chosen']} "
              f"reward={reward:+d} ({res['latency_s']}s)")

        # Stage 4.5 — REASON: after a correct pick the model must justify WHY
        # its choice was right.  Full flow: always on a correct pick.  Classic
        # flow: keep the old random chance.  Banked rows carry the model's own
        # reasoning when good, the coached diff-based reason otherwise — and
        # only rows naming the correct node reach training.
        reason_ok = False
        if (res["correct"] and CONFIG.get("reason")
                and (flow == "full"
                     or rng.random() * 100 < CONFIG.get("reason_chance", 50))):
            rres = play_reason(puzzle, llm_url, model, rag=rag)
            rm = STATUS.setdefault("by_mode", {}).setdefault(
                "reason",
                {"total": 0, "self_ok": 0, "coached": 0, "wrong": 0})
            rm["total"] += 1
            if rres["ok"]:
                rm["self_ok"] += 1
            elif rres["chosen"] == puzzle["correct_letter"]:
                rm["coached"] += 1      # right node, thin/absent reason -> coached
            else:
                rm["wrong"] += 1        # names a wrong node -> reason_dpo
            ep3 = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "round": round_no, "tier": tier,
                "app": puzzle["app"], "purpose": puzzle["purpose"],
                "purpose_label": puzzle["purpose_label"],
                "reason": True,
                "correct_letter": puzzle["correct_letter"],
                "chosen": rres["chosen"],
                "self_ok": rres["ok"],
                "reply": (rres["reply"] or "")[:400],
                "latency_s": rres["latency_s"],
                "rag": rag,
            }
            write_episode(ep3)
            write_reason_rows(puzzle, rres)
            STATUS["last_reason"] = ep3
            reason_ok = bool(rres["ok"])
            print(f"  🧠 reason: chose={rres['chosen']} "
                  f"{'✅ self' if rres['ok'] else '📖 coached' if rres['chosen'] == puzzle['correct_letter'] else '❌ wrong'} "
                  f"({rres['latency_s']}s)")

        # Stage 4 — RECREATE: after a correct pick, write back the missing code.
        # Full flow: always on a correct pick (deterministic chain).  Classic
        # flow: keep the old random chance.
        recreate_ok = False
        if (res["correct"] and CONFIG.get("completion")
                and (flow == "full"
                     or rng.random() * 100 < CONFIG.get("completion_chance", 50))):
            cres = play_completion(puzzle, llm_url, model, rng, rag=rag,
                                   pct=CONFIG.get("completion_pct", 40))
            creward = REWARDS["correct"] if cres["correct"] else REWARDS["wrong"]
            if cres["fill_ok"]:
                creward += REWARDS["optimize"]
            round_score += creward
            STATUS["score"] += creward
            cm = STATUS.setdefault("by_mode", {}).setdefault(
                "completion",
                {"total": 0, "choice_correct": 0, "fill_ok": 0,
                 "fill_total": 0, "sim_sum": 0.0})
            cm["total"] += 1
            cm["choice_correct"] += int(cres["correct"])
            if cres["correct"]:
                cm["fill_total"] += 1
                cm["fill_ok"] += int(cres["fill_ok"])
                cm["sim_sum"] += cres["fill_sim"]
            ep2 = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "round": round_no, "tier": tier,
                "app": puzzle["app"], "purpose": puzzle["purpose"],
                "purpose_label": puzzle["purpose_label"],
                "completion": True,
                "completion_pct": CONFIG.get("completion_pct", 40),
                "mask_variant": cres.get("mask_variant", 0),
                "correct_letter": puzzle["correct_letter"],
                "chosen": cres["chosen"], "correct": cres["correct"],
                "fill_sim": cres["fill_sim"], "fill_ok": cres["fill_ok"],
                "removed": cres["removed"], "written": cres["written"],
                "reward": creward, "latency_s": cres["latency_s"],
                "rag": rag,
            }
            write_episode(ep2)
            write_completion_rows(puzzle, ep2, cres)
            STATUS["last_completion"] = ep2
            recreate_ok = bool(cres["correct"])
            recreate_fill = bool(cres["fill_ok"])
            print(f"  🧩 recreate: chose={cres['chosen']} "
                  f"{'✅' if cres['correct'] else '❌'} "
                  f"fill {cres['fill_sim']*100:.0f}% "
                  f"{'✅' if cres['fill_ok'] else '—'} reward={creward:+d} "
                  f"({cres['latency_s']}s)")
        else:
            recreate_fill = False

        # curriculum: a chunk is mastered only when the model recreated it
        # correctly (right node chosen AND the missing code written back well)
        if flow == "full" and not review_nodes:
            chunk_ok = bool(recreate_ok and recreate_fill)
            curriculum_mark_recreated(app_name, puzzle["correct_text"], chunk_ok,
                                      round_no)

        # Stage 5 — OPTIMIZE: final test — smaller / faster / more efficient.
        # Full flow: always after a correct recreate.  Classic: after a correct
        # pick with the old random chance.
        if flow == "full":
            optimize_offer = bool(recreate_ok and tuneup_pct)
        else:
            optimize_offer = bool(res["correct"] and tuneup_pct
                                  and rng.random() < tuneup_pct)
        if optimize_offer:
            tu = run_tuneup(puzzle, llm_url, model)
            round_score += tu["reward"]
            STATUS["score"] += tu["reward"]
            opt_stats = STATUS.setdefault("opt", {"ok": 0, "bad": 0, "keep": 0})
            key = "ok" if tu["valid"] else "bad" if tu["reward"] < 0 else "keep"
            opt_stats[key] += 1
            types = (("smaller" if tu.get("smaller") else "") + " " +
                     ("faster" if tu.get("faster") else "")).strip() or "—"
            STATUS["last_tuneup"] = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "app": puzzle["app"],
                                     "purpose": puzzle["purpose_label"],
                                     "action": tu["action"],
                                     "valid": tu["valid"],
                                     "smaller": tu.get("smaller", False),
                                     "faster": tu.get("faster", False),
                                     "reason": tu["reason"],
                                     "reward": tu["reward"]}
            with (OUT_DIR / "opt-puzzle-r30.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": STATUS["last_tuneup"]["ts"],
                                    "round": round_no, "tier": tier,
                                    "app": puzzle["app"],
                                    "purpose": puzzle["purpose"],
                                    "original": puzzle["correct_text"],
                                    "optimized": tu["code"],
                                    "action": tu["action"],
                                    "valid": tu["valid"],
                                    "smaller": tu.get("smaller", False),
                                    "faster": tu.get("faster", False),
                                    "reason": tu["reason"],
                                    "reward": tu["reward"],
                                    "latency_s": tu["latency_s"]}) + "\n")
            mark = "🎛" if tu["action"] != "optimize" else "✅" if tu["valid"] else "❌"
            print(f"  {mark} optimize (final test): {tu['action']} ({tu['reward']:+d}) — "
                  f"{types} {tu['reason']} ({tu['latency_s']}s)")

    # Stage 6 — REBUILD: once EVERY chunk of a small app has been recreated
    # correctly, only the goal is shown and the model writes the whole app
    # from memory.  This is the curriculum finale — the 'able to remake the
    # apps' test.  Runs once per app (guarded by rebuild_done), RAG ON/OFF
    # follows the round (weights-only by default at eval: see retention-eval).
    cur = CURRICULUM.get(app_name, {})
    if (flow == "full" and not review_nodes and not cur.get("rebuild_done")
            and curriculum_mastered(app_name) and rebuild_eligible(app_name)):
        try:
            rb = play_rebuild(app_name, llm_url, model)
            round_score += rb["reward"]
            STATUS["score"] += rb["reward"]
            _cur_state(app_name)["rebuild_done"] = True
            _cur_state(app_name)["rebuild_ok"] = rb["ok"]
            _cur_state(app_name)["rebuild_sim"] = rb["sim"]
            save_curriculum()
            rb_ep = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "round": round_no, "tier": tier, "app": app_name,
                     "rebuild": True, "ok": rb["ok"], "sim": rb["sim"],
                     "reward": rb["reward"], "latency_s": rb["latency_s"]}
            write_episode(rb_ep)
            write_rebuild_rows(app_name, rb, round_no)
            STATUS["last_rebuild"] = rb_ep
            rbst = STATUS.setdefault("rebuild", {"ok": 0, "bad": 0})
            rbst["ok" if rb["ok"] else "bad"] += 1
            m = "✅" if rb["ok"] else "❌"
            print(f"  🏗 REBUILD from memory: {m} sim {rb['sim']*100:.0f}% "
                  f"reward={rb['reward']:+d} ({rb['latency_s']}s)")
        except Exception as e:
            print(f"  ⚠️ rebuild failed (continuing): {e}")

    round_s = round(time.time() - t0, 2)
    round_score += REWARDS["puzzle_complete"]
    STATUS["score"] += REWARDS["puzzle_complete"]
    print(f"  🧩 puzzle complete +{REWARDS['puzzle_complete']} — round time {round_s}s")

    # speed bonus vs previous best
    best = rounds_file.get("best_round_s")
    speed = 0
    if best is None or round_s < best:
        speed = REWARDS["speed_bonus"]
        rounds_file["best_round_s"] = round_s
        print(f"  ⚡ new best round time — +{speed} speed bonus")
    rounds_file["rounds_completed"] = rounds_file.get("rounds_completed", 0) + 1
    save_rounds_file(rounds_file)
    STATUS["score"] += speed
    # ladder entry (completed builds)
    STATUS["ladder"].append({"app": app_name, "tier": tier,
                              "score": round_score + speed, "time_s": round_s,
                              "solved": STATUS["build"]["solved"],
                              "total": len(app_nodes)})
    STATUS["rounds_history"].append({"round": round_no, "tier": tier,
                                     "acc": STATUS["acc"],
                                     "score": round_score + speed})
    save_status()
    print(f"  🏁 round total: {round_score + speed:+d}  |  session score: {STATUS['score']:+d}")
    return {"app": app_name, "tier": tier, "solved": STATUS["build"]["solved"],
            "total": len(app_nodes), "correct": STATUS["correct"],
            "wrong": STATUS["wrong"], "score": round_score + speed,
            "time_s": round_s, "speed": speed, "per_node": per_node}


# ─────────────────────────────────────────────────────────────────────────────
#  Live status page (tiny HTTP server)
# ─────────────────────────────────────────────────────────────────────────────
def control(body):
    """Apply a control command from the scoreboard; returns a human summary."""
    out = []
    if "nodes_per_puzzle" in body:
        try:
            v = max(1, min(int(body["nodes_per_puzzle"]), 24))
            CONFIG["nodes_per_puzzle"] = v
            out.append(f"nodes/puzzle={v}")
        except Exception:
            pass
    if "difficulty" in body:
        d = str(body["difficulty"]).lower()
        if d in ("auto", "easy", "medium", "hard", "extreme"):
            CONFIG["difficulty"] = d
            out.append(f"difficulty={d}")
    if "target_rounds" in body:
        try:
            v = max(1, int(body["target_rounds"]))
            CONFIG["target_rounds"] = v
            # Extending rounds means "keep going" — wake a paused/stopped session.
            CONFIG["paused"] = False
            if CONFIG.get("stop"):
                CONFIG["stop"] = False
                out.append("woke stopped session")
            out.append(f"target_rounds={v}")
        except Exception:
            pass
    if "completion" in body:
        v = bool(body["completion"])
        CONFIG["completion"] = v
        out.append(f"completion={'on' if v else 'off'}")
    if "reason_game_cadence" in body:
        try:
            v = max(0, min(int(body["reason_game_cadence"]), 50))
            CONFIG["reason_game_cadence"] = v
            out.append(f"reason-game cadence={v}")
        except Exception:
            pass
    if "completion_pct" in body:
        try:
            CONFIG["completion_pct"] = max(10, min(90, int(body["completion_pct"])))
            out.append(f"completion_pct={CONFIG['completion_pct']}")
        except Exception:
            pass
    if "completion_chance" in body:
        try:
            CONFIG["completion_chance"] = max(0, min(100, int(body["completion_chance"])))
            out.append(f"completion_chance={CONFIG['completion_chance']}")
        except Exception:
            pass
    if "gate_acc" in body:
        try:
            v = max(0.0, min(100.0, float(body["gate_acc"])))
            CONFIG["gate_acc"] = v
            out.append(f"gate_acc={v:g}{' (off)' if not v else ''}")
        except Exception:
            pass
    action = str(body.get("action", "")).lower()
    if action in ("start", "resume"):
        # Start/Resume: unpause, clear a prior Stop (restarts a stopped
        # session), and wake a session idling at the round limit.
        CONFIG["paused"] = False
        if CONFIG.get("stop"):
            CONFIG["stop"] = False
            out.append("restarted from stop")
        CONFIG["_wake"] = True
        out.append("started/resumed")
    elif action == "pause":
        CONFIG["paused"] = True
        out.append("paused")
    elif action == "stop":
        CONFIG["stop"] = True
        out.append("stopping after current node (▶ Resume restarts)")
    return "; ".join(out) or "no change"


class StatusHandler(BaseHTTPRequestHandler):
    def _send(self, ctype, body):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            payload = dict(STATUS)
            payload["config"] = dict(CONFIG)
            body = json.dumps(payload, indent=1).encode("utf-8")
            self._send("application/json", body)
        else:
            self._send("text/html; charset=utf-8", scoreboard_html().encode("utf-8"))

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8", "ignore") or "{}")
        except Exception:
            body = {}
        msg = control(body)
        resp = json.dumps({"ok": True, "msg": msg}).encode("utf-8")
        self._send("application/json", resp)

    def log_message(self, *a):
        pass


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def scoreboard_html():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    episodes = []
    p = OUT_DIR / "episodes.jsonl"
    if p.exists():
        episodes = [json.loads(l) for l in p.read_text().splitlines() if l.strip()][-12:][::-1]
    cur = STATUS.get("current") or {}
    build = STATUS.get("build") or {}
    cfg = CONFIG
    # app-canvas: node tiles filled as solved
    tiles = "".join(
        f"<div class='tile {'ok' if p.get('solved') else 'bad' if p.get('solved') is False else 'idle'}'"
        f" title='{_esc(p.get('text',''))[:300]}'>"
        f"<span class='t-letter'>{p.get('letter','')}</span>"
        f"{_esc(p.get('purpose',''))}<br>"
        f"<small>{'✅ placed' if p.get('solved') else '❌ missed' if p.get('solved') is False else '⏳'}</small>"
        f"</div>" for p in (build.get("parts") or []))
    assembled = _esc(build.get("assembled", ""))
    assembled_view = (f"<pre class='code'>{assembled}</pre>" if assembled
                      else "<p class='dim'>no nodes placed yet — solving…</p>")
    ladder_rows = "".join(
        f"<tr><td>{i}</td><td>{_esc(l['app'][:42])}</td><td>{l['tier']}</td>"
        f"<td>{l['solved']}/{l['total']}</td><td>{l['score']:+d}</td>"
        f"<td>{l['time_s']}s</td></tr>"
        for i, l in enumerate(reversed(STATUS.get("ladder", [])), 1))
    ep_rows = "".join(
        f"<tr><td>{e['ts'][11:19]}</td><td>{_esc(e['app'][:30])}</td>"
        f"<td>{_esc(e.get('purpose_label', e.get('purpose','')))}</td>"
        f"<td>{e['correct_letter']}→{e['chosen']}</td>"
        f"<td>{'✅' if e['correct'] else '❌'}</td><td>{e['reward']:+d}</td></tr>"
        for e in episodes)
    # tune-up panel: last optimization attempt + running counters
    tu = STATUS.get("last_tuneup") or {}
    o = STATUS.get("opt") or {}
    tu_line = (f"{_esc(tu.get('app','—'))} · {_esc(tu.get('purpose',''))} · "
               f"{_esc(tu.get('action',''))} → {'✅' if tu.get('valid') else '❌' if tu.get('reward', 0) < 0 else '💤'} "
               f"({_esc(tu.get('reason',''))}) {tu.get('reward', 0):+d}" if tu
               else "<span class='dim'>no tune-up offers yet — enable with --tuneup-pct (e.g. 0.3)</span>")
    # learning % trackers + mastery phase per tier
    def pct_bar(pct, color="#00d9ff"):
        return (f"<div class='bar'><div class='fill' style='width:{max(0,min(100,pct))}%"
                f";background:{color}'></div></div>")
    by_tier = STATUS.get("by_tier", {})
    phase_icon = {"learning": "🧠 learn", "speed": "⏱ speed", "promoted": "✅ done"}
    tier_color = {"easy": "#3ddc84", "medium": "#ffb454", "hard": "#ff5c5c",
                  "extreme": "#c77dff"}
    tier_parts = []
    for t in TIER_ORDER:
        if t not in by_tier and PROGRESS.get(t, {}).get("phase") == "learning":
            continue
        bt = by_tier.get(t, {"correct": 0, "total": 0})
        prog = PROGRESS.get(t, {})
        phase = prog.get("phase", "learning")
        extra = ""
        if phase == "learning" and prog.get("recent"):
            extra = f" · mastery <b>{prog.get('mastery_pct', 0.0)}%</b>/{MASTERY_PCT}%"
        elif phase == "speed":
            rop = prog.get("ragoff_pct", 0)
            extra = (f" · best <b>{prog.get('best_round_s', '—')}s</b> · "
                     f"{len(prog.get('round_times', []))} trials · "
                     f"no-RAG proof <b style='color:{'#3ddc84' if rop >= MASTERY_RAGOFF_PCT else '#ff5c5c'}'>{rop}%</b>"
                     f"/{MASTERY_RAGOFF_PCT}%")
        acc = 100 * bt["correct"] / max(bt["total"], 1)
        tier_parts.append(
            f"<div style='margin:6px 0'><b>{t}</b> "
            f"<span class='dim'>[{phase_icon.get(phase, '🧠')}]</span> "
            f"{bt['correct']}/{bt['total']} ({acc:.0f}% acc){extra}<br>"
            + pct_bar(acc, tier_color.get(t, "#00d9ff")) + "</div>")
    tier_bars = "".join(tier_parts)
    tu_panel = (f"<div class='card'><b>🎛 Tune-up (speed edits)</b> "
                f"<span class='dim'>the LLM rewrote a solved node — ✅ {o.get('ok',0)} "
                f"valid · ❌ {o.get('bad',0)} broken · 💤 {o.get('keep',0)} kept</span><br>"
                f"<span class='ok' style='font-size:12px'>{tu_line}</span></div>")
    gate_status = ""
    if cfg.get("gate_acc") and cfg.get("difficulty") != "auto":
        gp = GATE.get("pct", 0.0)
        gt = float(cfg["gate_acc"])
        gw = len(GATE.get("window", []))
        gcol = "#3ddc84" if gw and gp >= gt else "#ffb454"
        state = (f"<b style='color:{gcol}'>{gp:.0f}%</b>/{gt:g}% "
                 f"(last {gw}/{GATE_WINDOW} fresh picks @ {cfg['difficulty']})")
        gate_status = (f"<div class='card' style='border-color:#ffb454'><b>🎯 gate</b> "
                       f"<span class='dim'>plays until accuracy meets the gate, then "
                       f"pauses — raise difficulty to promote</span><br>{state}</div>")
    cm = STATUS.get("by_mode", {}).get("completion") or {}
    if cm.get("total"):
        cchoice = 100 * cm["choice_correct"] / max(cm["total"], 1)
        cfill = 100 * cm["fill_ok"] / max(cm["fill_total"], 1)
        csim = 100 * cm["sim_sum"] / max(cm["fill_total"], 1)
        comp_panel = (f"<div class='card'><b>🧩 Completion (cloze)</b> "
                      f"<span class='dim'>solved puzzles replayed with a section "
                      f"removed — choose the node AND write back the code</span><br>"
                      f"<div style='display:flex;gap:22px;flex-wrap:wrap;margin-top:8px'>"
                      f"<div><span class='big' style='font-size:24px'>{cchoice:.0f}%</span><br>"
                      f"<span class='dim'>choose correct ({cm['choice_correct']}/{cm['total']})</span></div>"
                      f"<div><span class='big' style='font-size:24px;color:#ffb454'>{cfill:.0f}%</span><br>"
                      f"<span class='dim'>fill correct ({cm['fill_ok']}/{cm['fill_total']})</span></div>"
                      f"<div class='dim' style='align-self:center'>avg fill sim "
                      f"{csim:.0f}% · remove {cfg.get('completion_pct', 40)}% · "
                      f"chance {cfg.get('completion_chance', 50)}%</div>"
                      f"</div></div>")
    else:
        comp_panel = (f"<div class='card'><b>🧩 Completion (cloze)</b> "
                      f"<span class='dim'>no completion puzzles yet — "
                      f"{'enabled, fires on solved puzzles' if cfg.get('completion') else 'disabled (turn on in controls)'}</span></div>")
    rm = STATUS.get("by_mode", {}).get("reason") or {}
    if rm.get("total"):
        rself = 100 * rm["self_ok"] / max(rm["total"], 1)
        rcoach = 100 * rm["coached"] / max(rm["total"], 1)
        reason_panel = (f"<div class='card'><b>🧠 Reasoning</b> "
                        f"<span class='dim'>after a correct pick the model must "
                        f"justify it — self-reasoned vs coached (banked rows teach "
                        f"both)</span><br>"
                        f"<div style='display:flex;gap:22px;flex-wrap:wrap;margin-top:8px'>"
                        f"<div><span class='big' style='font-size:24px'>{rself:.0f}%</span><br>"
                        f"<span class='dim'>self-reasoned ({rm['self_ok']}/{rm['total']})</span></div>"
                        f"<div><span class='big' style='font-size:24px;color:#ffb454'>{rcoach:.0f}%</span><br>"
                        f"<span class='dim'>coached ({rm['coached']}/{rm['total']})</span></div>"
                        f"<div><span class='big' style='font-size:24px;color:#ff5c5c'>"
                        f"{rm['wrong']}</span><br><span class='dim'>wrong-node → dpo</span></div>"
                        f"<div class='dim' style='align-self:center'>chance "
                        f"{cfg.get('reason_chance', 50)}% · "
                        f"{'enabled' if cfg.get('reason') else 'disabled'}</div>"
                        f"</div></div>")
    else:
        reason_panel = (f"<div class='card'><b>🧠 Reasoning</b> "
                        f"<span class='dim'>no reason stage yet — "
                        f"{'fires on solved puzzles' if cfg.get('reason') else 'disabled (turn on in controls)'}</span></div>")
    rgm = STATUS.get("by_mode", {}).get("reason_game") or {}
    cadence = int(cfg.get("reason_game_cadence", 0) or 0)
    if rgm.get("puzzles"):
        vpct = 100 * rgm["verdict_ok"] / max(rgm["verdicts"], 1)
        epct = 100 * rgm["ev_ok"] / max(rgm["verdicts"], 1)
        ppct = 100 * rgm["pick_ok"] / max(rgm["puzzles"], 1)
        rg_panel = (f"<div class='card'><b>⚖️ Verdict-step game</b> "
                    f"<span class='dim'>ordered reasoning — each candidate judged "
                    f"YES/NO + concrete evidence BEFORE the pick</span><br>"
                    f"<div style='display:flex;gap:22px;flex-wrap:wrap;margin-top:8px'>"
                    f"<div><span class='big' style='font-size:24px'>{vpct:.0f}%</span><br>"
                    f"<span class='dim'>verdicts ({rgm['verdict_ok']}/{rgm['verdicts']})</span></div>"
                    f"<div><span class='big' style='font-size:24px;color:#ffb454'>{epct:.0f}%</span><br>"
                    f"<span class='dim'>evidence ({rgm['ev_ok']}/{rgm['verdicts']})</span></div>"
                    f"<div><span class='big' style='font-size:24px;color:#3ddc84'>{ppct:.0f}%</span><br>"
                    f"<span class='dim'>puzzles ({rgm['pick_ok']}/{rgm['puzzles']})</span></div>"
                    f"<div class='dim' style='align-self:center'>pts {rgm['pts']:+d} · "
                    f"cadence {cadence or 'off'}</div></div></div>")
    else:
        rg_panel = (f"<div class='card'><b>⚖️ Verdict-step game</b> "
                    f"<span class='dim'>no rounds yet — set cadence "
                    f"{'(every N-th round, 0=off)' if not cadence else '→ every ' + str(cadence) + ' rounds'} "
                    f"in controls</span></div>")
    br = STATUS.get("by_rag") or {}
    def rag_pct(k):
        b = br.get(k) or {"correct": 0, "total": 0}
        return (b["correct"], b["total"],
                100 * b["correct"] / max(b["total"], 1))
    ro = rag_pct("on"); rf = rag_pct("off")
    rag_panel = (f"<div class='card'><b>📚 RAG vs no-RAG</b> "
                 f"<span class='dim'>time-trials drop the reference library to prove "
                 f"the model internalized the patterns</span><br>"
                 f"<div style='display:flex;gap:22px;flex-wrap:wrap;margin-top:8px'>"
                 f"<div><span class='big' style='font-size:24px'>{ro[2]:.0f}%</span><br>"
                 f"<span class='dim'>with RAG ({ro[0]}/{ro[1]})</span></div>"
                 f"<div><span class='big' style='font-size:24px;color:#ffb454'>{rf[2]:.0f}%</span><br>"
                 f"<span class='dim'>no RAG ({rf[0]}/{rf[1]})</span></div>"
                 f"<div class='dim' style='align-self:center'>{'🎓 gap ' +
                 f'{rf[2] - ro[2]:+.0f}pt' if (ro[1] and rf[1]) else 'no no-RAG picks yet'}</div>"
                 f"</div></div>")
    # ── curriculum panel: per-app chunk mastery + rebuild status ────────────
    rbst = STATUS.get("rebuild") or {"ok": 0, "bad": 0}
    last_rb = STATUS.get("last_rebuild") or {}
    cur_rows = []
    for app_name in sorted(CURRICULUM, key=lambda a: str(CURRICULUM[a].get("last_round", 0)))[-8:][::-1]:
        nodes = lib.apps.get(app_name, {}).get("nodes", [])
        st = CURRICULUM[app_name]
        if not nodes:
            continue
        ok = sum(1 for n in nodes
                 if st.get("chunks", {}).get(n["text"], {}).get("ok"))
        done = "🏗✅" if st.get("rebuild_done") and st.get("rebuild_ok") else \
               "🏗❌" if st.get("rebuild_done") else ""
        pct = int(100 * ok / len(nodes))
        short = app_name.replace("app-in-a-single-html-", "")[:24]
        cur_rows.append(
            f"<div style='display:flex;gap:10px;align-items:center;margin:4px 0'>"
            f"<span class='dim' style='width:210px;overflow:hidden;"
            f"white-space:nowrap' title='{_esc(app_name)}'>{_esc(short)}</span>"
            f"<div class='bar' style='flex:1;max-width:220px'>"
            f"<div class='fill' style='width:{pct}%;"
            f"background:{'#3ddc84' if st.get('rebuild_done') else '#ffb454'}'></div></div>"
            f"<span class='dim' style='font-size:11px'>{ok}/{len(nodes)}</span> {done}</div>")
    if cur_rows:
        cur_rows_html = "".join(cur_rows)
    else:
        cur_rows_html = ("<span class='dim'>no apps in progress yet — first "
                         "observe pass, then replays remove new chunks</span>")
    last_rb_html = (f" · last sim <b>{last_rb.get('sim', 0)*100:.0f}%</b> "
                    f"({last_rb.get('latency_s', 0)}s)" if last_rb else "")
    cur_panel = (f"<div class='card'><b>🎓 App curriculum</b> "
                 f"<span class='dim'>same app returns with a different chunk "
                 f"missing until every chunk is recreated, then rebuilt from "
                 f"memory</span><br>"
                 f"<div style='margin-top:6px'>{cur_rows_html}</div>"
                 f"<div style='margin-top:8px;font-size:12px'>🏗 rebuilds: "
                 f"<span class='ok'>✅ {rbst['ok']}</span> / "
                 f"<span class='bad'>❌ {rbst['bad']}</span>{last_rb_html}</div></div>")
    # ── library panel: rebalanced tiers after the classifier fix ────────────
    tier_counts = {}
    for an, a in lib.apps.items():
        tier_counts[a.get("tier", "easy")] = tier_counts.get(a.get("tier", "easy"), 0) + 1
    lib_tiles = "".join(
        f"<div class='tile'><span class='big' style='font-size:20px;color:{tier_color.get(t, '#00d9ff')}'>"
        f"{tier_counts.get(t, 0)}</span><br><span class='dim'>{t} apps</span></div>"
        for t in TIER_ORDER if tier_counts.get(t))
    lib_panel = (f"<div class='card'><b>🗂 Library</b> "
                 f"<span class='dim'>node puzzle source — CSS is classified as "
                 f"styling/animations only, so game-logic is always real JS</span><br>"
                 f"<div class='grid' style='margin-top:8px'>{lib_tiles}</div>"
                 f"<div style='margin-top:8px;font-size:12px' class='dim'>"
                 f"{len(lib.apps)} apps · "
                 f"{sum(len(a['nodes']) for a in lib.apps.values())} nodes</div></div>")
    hist = STATUS.get("rounds_history", [])
    spark = "".join(
        f"<div class='dot {'ok' if h['acc'] >= 60 else 'mid' if h['acc'] >= 40 else 'bad'}'"
        f" title='round {h['round']} {h['tier']} acc {h['acc']}%'></div>" for h in hist[-40:])
    cur_app = _esc(cur.get("app", "—"))
    cur_tier = _esc(STATUS.get("tier", "—"))
    cur_node = _esc(cur.get("node", "—"))
    cur_purpose = _esc(cur.get("purpose", "—"))
    solved = build.get("solved", 0)
    total = max(build.get("total", 1), 1)
    pct = int(100 * solved / total)
    if cfg.get("stop"):
        light_cls, light_txt = "light-stop", "■ STOPPED"
    elif cfg.get("paused"):
        light_cls, light_txt = "light-pause", "⏸ PAUSED"
    else:
        light_cls, light_txt = "light-run", "● RUNNING"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>🧩 VACA Puzzle-RAG Scoreboard</title>
<style>
body{{font-family:ui-monospace,monospace;background:#0a0a14;color:#e6e6e6;margin:20px}}
h1{{color:#00d9ff;margin:0 0 4px 0}}
.sub{{color:#888;font-size:12px;margin-bottom:14px}}
.card{{background:#14141f;border:1px solid #2a2a3a;border-radius:10px;padding:16px;margin:10px 0}}
.big{{font-size:30px;color:#00d9ff;font-weight:700}}
.ok{{color:#3ddc84}} .bad{{color:#ff5c5c}} .mid{{color:#ffb454}} .dim{{color:#777}}
.grid{{display:flex;flex-wrap:wrap;gap:8px}}
.tile{{background:#0f0f1a;border:1px solid #2a2a3a;border-radius:8px;padding:8px 10px;
  min-width:110px;text-align:center;font-size:12px}}
.tile.ok{{border-color:#3ddc84;background:#0d2416}}
.tile.bad{{border-color:#ff5c5c;background:#2a0d0d}}
.tile.idle{{border-color:#555}}
.t-letter{{font-weight:700;color:#00d9ff}}
table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #2a2a3a;padding:5px 9px;text-align:left;font-size:12px}}
pre.code{{background:#0b0b14;border:1px solid #2a2a3a;border-radius:8px;padding:12px;
  max-height:260px;overflow:auto;font-size:11px;white-space:pre-wrap}}
.bar{{background:#0f0f1a;border:1px solid #2a2a3a;border-radius:6px;height:12px;overflow:hidden}}
.fill{{background:#00d9ff;height:100%;transition:width .5s}}
.twocol{{display:flex;gap:16px;flex-wrap:wrap}} .twocol>div{{flex:1;min-width:300px}}
.ctl{{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}}
.ctl label{{font-size:11px;color:#aaa;display:block;margin-bottom:4px}}
.ctl input,.ctl select{{background:#0f0f1a;border:1px solid #2a2a3a;color:#e6e6e6;
  border-radius:6px;padding:7px 9px;font-size:14px}}
.ctl button{{background:#00d9ff;color:#04141a;border:none;border-radius:6px;
  padding:8px 14px;font-size:13px;cursor:pointer}}
.ctl button.ghost{{background:#2a2a3a;color:#e6e6e6}}
.ctl button.red{{background:#ff5c5c;color:#14141f}}
.dot{{width:10px;height:10px;border-radius:50%;display:inline-block;margin:1px}}
.spark{{display:flex;flex-wrap:wrap;gap:2px;margin-top:6px}}
.msg{{color:#00d9ff;font-size:12px;min-height:16px}}
.light{{display:inline-flex;align-items:center;gap:7px;padding:4px 12px;border-radius:12px;
  font-size:11px;font-weight:700;letter-spacing:.4px}}
.light .pulse{{width:10px;height:10px;border-radius:50%}}
.light-run{{background:#0d2416;color:#3ddc84;border:1px solid #3ddc84}}
.light-run .pulse{{background:#3ddc84;box-shadow:0 0 8px #3ddc84;animation:pulse 1.4s infinite}}
.light-pause{{background:#2a200d;color:#ffb454;border:1px solid #ffb454}}
.light-pause .pulse{{background:#ffb454}}
.light-stop{{background:#2a0d0d;color:#ff5c5c;border:1px solid #ff5c5c}}
.light-stop .pulse{{background:#ff5c5c}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
</style></head><body>
<h1>🧩 VACA Puzzle-RAG Scoreboard</h1>
<div class="sub">the 14B learns by playing — node puzzles from the library · rewards, penalties, speed bonuses
<span id="state" class="light {light_cls}"><span class="pulse"></span>{light_txt}</span></div>
<div class="card" style="border-color:#00d9ff">
<b>🕹️ Controls</b> <span class="dim">— live, no restart needed</span>
<div class="ctl">
<div><label>Nodes per puzzle</label><input id="npp" type="number" min="1" max="24" value="{cfg.get('nodes_per_puzzle',5)}"></div>
<div><label>Difficulty</label>
<select id="diff"><option value="auto"{' selected' if cfg.get('difficulty')=='auto' else ''}>auto (easy→extreme)</option>
<option value="easy"{' selected' if cfg.get('difficulty')=='easy' else ''}>easy</option>
<option value="medium"{' selected' if cfg.get('difficulty')=='medium' else ''}>medium</option>
<option value="hard"{' selected' if cfg.get('difficulty')=='hard' else ''}>hard</option>
<option value="extreme"{' selected' if cfg.get('difficulty')=='extreme' else ''}>extreme (subtle fakes)</option></select></div>
<div><label>Rounds to run</label><input id="rounds" type="number" min="1" value="{cfg.get('target_rounds',1)}"></div>
<div><button onclick="ctl({{nodes_per_puzzle:+document.getElementById('npp').value}})">Apply nodes</button></div>
<div><button onclick="ctl({{difficulty:document.getElementById('diff').value}})">Set difficulty</button></div>
<div><button onclick="ctl({{target_rounds:+document.getElementById('rounds').value}})">Extend rounds</button></div>
<div><label>Completion (cloze)</label><button onclick="ctl({{completion:true}})">on</button><button onclick="ctl({{completion:false}})">off</button></div>
<div><label>🧠 Reason-game cadence (every N rounds, 0=off)</label><input id="rgc" type="number" min="0" max="50" value="{cfg.get('reason_game_cadence',0)}"><button onclick="ctl({{reason_game_cadence:+document.getElementById('rgc').value}})">Set</button></div>
<div><label>Remove %</label><input id="crm" type="number" min="10" max="90" value="{cfg.get('completion_pct',40)}"></div>
<div><label>Chance %</label><input id="cch" type="number" min="0" max="100" value="{cfg.get('completion_chance',50)}"></div>
<div><button onclick="ctl({{completion_pct:+document.getElementById('crm').value,completion_chance:+document.getElementById('cch').value}})">Apply cloze</button></div>
<div><label>Gate acc % (0=off)</label><input id="gate" type="number" min="0" max="100" step="0.1" value="{cfg.get('gate_acc',0)}"></div>
<div><button onclick="ctl({{gate_acc:+document.getElementById('gate').value}})">Set gate</button></div>
<div><button onclick="ctl({{action:'start'}})">▶ Start</button></div>
<div><button class="ghost" onclick="ctl({{action:'pause'}})">⏸ Pause</button></div>
<div><button class="ghost" onclick="ctl({{action:'resume'}})">▶ Resume</button></div>
<div><button class="red" onclick="ctl({{action:'stop'}})">⏹ Stop</button></div>
</div>
<div class="msg" id="msg"></div>
</div>
<div id="data">
<div class="card">
<span class="big">{STATUS['score']:+d}</span> session score
&nbsp;·&nbsp; ✅ <span class="ok">{STATUS['correct']}</span> / ❌ <span class="bad">{STATUS['wrong']}</span>
&nbsp;·&nbsp; {STATUS['puzzles']} puzzles · round {STATUS['round']} ({cur_tier})
</div>
{gate_status}
<div class="twocol">
<div class="card">
<b>📈 Learning progress</b>
<div style="margin-top:8px">
<div style="display:flex;gap:18px;flex-wrap:wrap">
<div><span class="big" style="font-size:26px">{STATUS['acc']}%</span><br><span class="dim">overall accuracy</span></div>
<div><span class="big" style="font-size:26px;color:#ffb454">{STATUS['recent_acc']}%</span><br><span class="dim">last 20 picks</span></div>
<div><span class="big" style="font-size:26px;color:#3ddc84">{STATUS['correct']}/{STATUS['puzzles']}</span><br><span class="dim">correct / total</span></div>
</div>
{tier_bars}
<div style="margin-top:8px"><span class="dim">accuracy by round (green ≥60% · amber 40–60% · red &lt;40%):</span>
<div class="spark">{spark or '<span class="dim">—</span>'}</div></div>
</div>
</div>
<div class="card">
<b>Building: <span class="ok">{cur_app}</span></b> <span class="dim">(node {cur_node} · {cur_purpose})</span>
<div class="bar" style="margin:8px 0"><div class="fill" style="width:{pct}%"></div></div>
<span class="dim">{solved}/{total} nodes placed ({pct}%)</span>
<div class="grid" style="margin-top:10px">{tiles}</div>
</div>
</div>
<div class="twocol">
<div class="card"><b>App under construction:</b>
{assembled_view}</div>
<div class="card"><b>🏆 Completed builds (ladder)</b>
<table><tr><th>#</th><th>app</th><th>tier</th><th>nodes</th><th>score</th><th>time</th></tr>{ladder_rows}</table></div>
</div>
<div class="twocol">
<div class="card"><b>Recent picks</b>
<table><tr><th>t</th><th>app</th><th>purpose</th><th>pick</th><th></th><th>rew</th></tr>{ep_rows}</table></div>
{tu_panel}
{reason_panel}
{rg_panel}
{comp_panel}
{cur_panel}
</div>
{rag_panel}
{lib_panel}
</div><!-- /#data -->
<script>
function ctl(body){{fetch('/api/control',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify(body)}}).then(r=>r.json()).then(d=>{{document.getElementById('msg').textContent='✔ '+d.msg;refresh();}});}}
async function refresh(){{
  try{{
    const r = await fetch('/?t=' + Date.now());
    const t = await r.text();
    const tmp = document.createElement('div');
    tmp.innerHTML = t;
    const d = tmp.querySelector('#data');
    const cur = document.getElementById('data');
    if (d && cur) cur.innerHTML = d.innerHTML;
    const st = tmp.querySelector('#state');
    const cst = document.getElementById('state');
    if (st && cst) cst.outerHTML = st.outerHTML;
  }} catch(e){{}}
}}
setInterval(refresh, 4000);
refresh();
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Entry points
# ─────────────────────────────────────────────────────────────────────────────
def main():
    global MASTERY_WINDOW, MASTERY_PCT, MASTERY_RAGOFF_WINDOW, MASTERY_RAGOFF_PCT
    global SPEED_MIN_ROUNDS, SPEED_PLATEAU_ROUNDS
    global OUT_DIR
    global EMBED_URL, EMBED_MODEL
    ap = argparse.ArgumentParser(description="VACA Puzzle-RAG Trainer")
    ap.add_argument("--rounds", type=int, default=1, help="number of puzzle rounds")
    ap.add_argument("--nodes-per-puzzle", type=int, default=5)
    ap.add_argument("--llm-url", default=DEFAULT_LLM_URL)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--embed-url", default="",
                    help="Ollama /api/embed endpoint for semantic RAG "
                         "(empty = keyword ranking only)")
    ap.add_argument("--embed-model", default=EMBED_MODEL)
    ap.add_argument("--no-rag", action="store_true", help="disable RAG reference injection")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--status-port", type=int, default=0, help="0 = no status server")
    ap.add_argument("--tuneup-pct", type=float, default=0.5,
                    help="0..1 — chance after each CORRECT pick to offer the node "
                         "back to the LLM to optimize for speed (+15 valid / -10 "
                         "broken / +2 keep).  In --flow full this is the Stage 5 "
                         "final test and runs after every correct recreate (0 disables)")
    ap.add_argument("--flow", default="full", choices=["full", "classic"],
                    help="'full' (default) = 5-stage game: OBSERVE whole app -> "
                         "slice -> PICK -> RECREATE (when correct) -> OPTIMIZE "
                         "(final test).  'classic' = old behavior (no observe, "
                         "randomized completion + tune-up)")
    ap.add_argument("--no-rag-speed", action="store_true",
                    help="run the TIME-TRIAL phase with RAG reference OFF — proves "
                         "the model can build without retrieval assistance")
    ap.add_argument("--mastery-ragoff-pct", type=float, default=MASTERY_RAGOFF_PCT,
                    help="no-RAG accuracy floor required to PROMOTE a tier "
                         "(default 60%% over the no-RAG window)")
    ap.add_argument("--mastery-ragoff-window", type=int, default=MASTERY_RAGOFF_WINDOW,
                    help="rolling picks over which no-RAG accuracy is measured")
    ap.add_argument("--max-apps", type=int, default=None, help="limit library size (test)")
    ap.add_argument("--mastery-window", type=int, default=MASTERY_WINDOW)
    ap.add_argument("--mastery-pct", type=float, default=MASTERY_PCT)
    ap.add_argument("--speed-min-rounds", type=int, default=SPEED_MIN_ROUNDS)
    ap.add_argument("--speed-plateau", type=int, default=SPEED_PLATEAU_ROUNDS)
    ap.add_argument("--out-dir", type=str, default=str(OUT_DIR),
                    help="output dir for episodes/training rows (per-session, "
                         "so parallel trainers don't collide)")
    ap.add_argument("--self-test", action="store_true", help="build puzzles, no LLM calls")
    ap.add_argument("--no-reviews", action="store_true",
                    help="disable the spaced-replay review queue")
    args = ap.parse_args()
    MASTERY_WINDOW = args.mastery_window
    MASTERY_PCT = args.mastery_pct
    MASTERY_RAGOFF_WINDOW = args.mastery_ragoff_window
    MASTERY_RAGOFF_PCT = args.mastery_ragoff_pct
    SPEED_MIN_ROUNDS = args.speed_min_rounds
    SPEED_PLATEAU_ROUNDS = args.speed_plateau
    OUT_DIR = Path(args.out_dir).resolve()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EMBED_URL = args.embed_url
    EMBED_MODEL = args.embed_model
    load_review_queue()
    load_curriculum()

    global lib
    lib = Library(EXPORTS_DIR, max_apps=args.max_apps)
    print(f"📚 library: {len(lib.apps)} apps, "
          f"{sum(len(a['nodes']) for a in lib.apps.values())} nodes "
          f"({len(lib.by_purpose)} purposes)")
    if not lib.apps:
        print(f"❌ no chunkable apps under {EXPORTS_DIR}", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)

    if args.self_test:
        ok = bad = 0
        purposes = {}
        for app_name in list(lib.apps)[:12]:
            for node in lib.apps[app_name]["nodes"][:6]:
                purposes[node["purpose"]] = purposes.get(node["purpose"], 0) + 1
                pz = lib.make_puzzle(app_name, node, rng)
                if pz is None:
                    bad += 1
                    continue
                kinds = sorted(n["kind"] for n in pz["nodes"])
                if pz["correct_letter"] and len(kinds) == 3 and kinds.count("CORRECT") == 1:
                    ok += 1
                else:
                    bad += 1
                    print("  ⚠️ weak puzzle:", app_name, node["purpose"], kinds)
        ref = lib.reference_for("game-logic", list(lib.apps)[0], "checkers game")
        print(f"🔎 self-test: {ok} solid puzzles, {bad} weak  |  "
              f"RAG sample retrieved {len(ref)} refs for game-logic")
        print(f"   purposes seen: {purposes}")
        return

    if args.status_port:
        srv = ThreadingHTTPServer(("0.0.0.0", args.status_port), StatusHandler)
        import threading
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"📺 status page: http://0.0.0.0:{args.status_port}")

    tiers = [t for t in TIER_ORDER if lib.tiers.get(t)]
    CONFIG["nodes_per_puzzle"] = args.nodes_per_puzzle
    CONFIG["target_rounds"] = args.rounds
    print(f"🎯 playing against {args.model} @ {args.llm_url} "
          f"(RAG {'ON' if not args.no_rag else 'OFF'})")
    print(f"📶 library tiers: " +
          ", ".join(f"{t}={len(lib.tiers[t])}" for t in tiers))
    print(f"🎓 mastery: ≥{MASTERY_PCT}% over {MASTERY_WINDOW} picks → time trials → "
          f"promote after {SPEED_PLATEAU_ROUNDS} plateau rounds")
    print(f"🎛 tune-up offers: {'ON' if args.tuneup_pct else 'OFF'} "
          f"(pct={args.tuneup_pct})")
    print(f"📚 RAG: {'off' if args.no_rag else 'on (speed trials: ' + 
          ('OFF' if args.no_rag_speed else 'ON') + ')'}")
    print(f"🔎 semantic RAG: {'ON (' + EMBED_MODEL + ' @ ' + EMBED_URL + ')' if EMBED_URL else 'OFF (keyword ranking)'}")
    print("🕹️ scoreboard controls: nodes-per-puzzle, difficulty, rounds, pause, stop")
    r = 0
    tier_idx = 0          # current tier position in TIER_ORDER
    try:
        while True:
            if CONFIG.get("stop"):
                # stopped — hold the session instead of ending it, so ▶ Resume
                # or Extend rounds can restart training from the scoreboard.
                if not CONFIG.get("_stop_held"):
                    CONFIG["_stop_held"] = True
                    print("\n⏹ stopped — click ▶ Resume or Extend rounds to restart training.")
                time.sleep(1)
                continue
            CONFIG["_stop_held"] = False
            if CONFIG["paused"]:
                time.sleep(1)
                continue
            r += 1
            gate_on = bool(CONFIG.get("gate_acc")) and CONFIG["difficulty"] != "auto"
            if gate_on:
                # accuracy-gate mode: no round limit — play until the rolling
                # accuracy at the pinned tier meets the gate, then pause for a
                # difficulty promotion (the gate then applies to the new tier).
                if (GATE.get("tier") != CONFIG["difficulty"]
                        or GATE.get("target") != CONFIG.get("gate_acc")):
                    GATE.update({"tier": CONFIG["difficulty"],
                                 "target": CONFIG.get("gate_acc"),
                                 "window": [], "pct": 0.0})
                if (len(GATE["window"]) >= GATE_WINDOW
                        and GATE["pct"] >= float(CONFIG["gate_acc"])):
                    print(f"\n🎯 {CONFIG['difficulty'].upper()} GATE MET — "
                          f"{GATE['pct']:.0f}% ≥ {CONFIG['gate_acc']:g}% over "
                          f"last {len(GATE['window'])} fresh picks. Paused — "
                          f"raise the difficulty or clear the gate to continue.")
                    while not CONFIG["stop"]:
                        if not CONFIG.get("gate_acc"):
                            print("   gate cleared — continuing")
                            break
                        if CONFIG["difficulty"] != GATE.get("tier"):
                            print(f"   difficulty → {CONFIG['difficulty']} — continuing")
                            break
                        if CONFIG.get("_wake"):
                            # ▶ Resume while the gate is met: re-arm the gate
                            # window (fresh picks) and keep playing.
                            CONFIG["_wake"] = False
                            GATE["window"] = []
                            GATE["pct"] = 0.0
                            print("   ▶ resumed — gate window reset, continuing")
                            break
                        if CONFIG.get("paused") and not CONFIG.get("_wake"):
                            time.sleep(1)
                            continue
                        time.sleep(1)
                    if CONFIG["stop"]:
                        break
                    continue
            elif r > CONFIG["target_rounds"]:
                # target reached — keep the scoreboard alive and WAIT for the
                # user to extend rounds from the page (resumes play).
                print(f"\n⏸ {CONFIG['target_rounds']} rounds done — extend rounds on the scoreboard to keep going.")
                if not args.status_port:
                    # No scoreboard is being served, so there is nothing to click
                    # "Extend rounds" on and idling here only deadlocks the caller:
                    # orchestrator.stage_play() runs this with subprocess.call and
                    # waits for exit, so the round would hang forever at its limit.
                    print("↩ no --status-port, so returning instead of waiting")
                    break
                while r > CONFIG["target_rounds"]:
                    if CONFIG.get("stop"):
                        # Stop while idle at the round limit: hold as paused so
                        # ▶ Resume / Extend rounds can revive this session.
                        CONFIG["stop"] = False
                        CONFIG["paused"] = True
                        print("\n⏹ stopped (idle) — click ▶ Resume or Extend rounds to continue.")
                    if CONFIG.get("paused") and not CONFIG.get("_wake"):
                        time.sleep(1)
                        continue
                    if CONFIG.get("_wake"):
                        # ▶ Resume while idle at the round limit: extend the
                        # session (10 more rounds) and keep playing.
                        CONFIG["_wake"] = False
                        CONFIG["target_rounds"] = r + 10
                        print(f"\n▶ resumed — extending to {CONFIG['target_rounds']} rounds.")
                        break
                    time.sleep(1)
            if CONFIG["difficulty"] != "auto":
                tier = CONFIG["difficulty"] if CONFIG["difficulty"] in tiers else tiers[0]
                strict_tier = True
            else:
                # mastery-gated progression: advance through the tiers
                while tier_idx < len(TIER_ORDER) and PROGRESS[TIER_ORDER[tier_idx]]["promoted"]:
                    tier_idx += 1
                if tier_idx >= len(TIER_ORDER):
                    print("\n🏆 ALL TIERS MASTERED — session complete!")
                    break
                tier = TIER_ORDER[tier_idx]
                strict_tier = True
            prog = PROGRESS.get(tier, {"phase": "learning"})
            if prog.get("phase") == "promoted":
                if CONFIG["difficulty"] == "auto":
                    tier_idx += 1
                    continue
                else:
                    prog["phase"] = "learning"
            phase_tag = {"learning": "LEARN", "speed": "SPEED"}.get(prog.get("phase"), "LEARN")
            # When difficulty is PINNED (gate mode) the no-RAG speed-trial phase
            # is skipped — the gate measures real RAG-assisted play, not the
            # no-reference proof.  Speed trials only run on the auto ladder.
            speed_phase = (prog.get("phase") == "speed"
                           and CONFIG["difficulty"] == "auto")
            rag_on = (not args.no_rag) and not (speed_phase and args.no_rag_speed)
            # ── dedicated REASONING rounds: every N-th round is a verdict-step
            # walkthrough (each candidate judged YES/NO + concrete evidence,
            # THEN the pick) — pure practice, banks verified reasoning rows.
            # cadence 0 = off; 1 = every round is a reasoning round.
            _cadence = int(CONFIG.get("reason_game_cadence", 0) or 0)
            if _cadence and r % _cadence == 0:
                rres = play_reason_round(r, args.llm_url, args.model, rng,
                                         rag=rag_on, tier=tier,
                                         strict_tier=strict_tier)
                if rres is None:
                    break
                save_status()
                continue
            # ── spaced-replay: serve due review nodes as their own round ──
            rounds_file = load_rounds_file()
            now = rounds_file.get("rounds_completed", 0)
            due = [(k, v) for k, v in REVIEW_QUEUE.items()
                   if v.get("due_at", 0) <= now]
            review_nodes = []
            for (app, text), it in sorted(due)[:REVIEWS_PER_ROUND]:
                node = next((n for n in lib.apps.get(app, {}).get("nodes", [])
                             if n.get("text") == text), None)
                if node is not None:
                    review_nodes.append(dict(node, _app=app))
            if review_nodes and not args.no_reviews:
                r_tier = lib.apps.get(review_nodes[0]["_app"], {}).get("tier", tier)
                res = play_round(r, args.llm_url, args.model, rng,
                                 rag=rag_on,
                                 nodes_per_puzzle=CONFIG["nodes_per_puzzle"],
                                 tier=r_tier, strict_tier=True,
                                 tuneup_pct=args.tuneup_pct,
                                 review_nodes=review_nodes, flow=args.flow)
                if res is None:
                    break
                for pn in res.get("per_node", []):
                    review_on_result(pn["app"], pn["text"], pn["correct"], now)
                for pn in res.get("per_node", []):
                    adapt_update(pn["correct"])
                save_review_queue()
                continue
            res = play_round(r, args.llm_url, args.model, rng,
                             rag=rag_on,
                             nodes_per_puzzle=CONFIG["nodes_per_puzzle"],
                             tier=tier, strict_tier=strict_tier,
                             tuneup_pct=args.tuneup_pct, flow=args.flow)
            if res is None:
                break
            for pn in res.get("per_node", []):
                if not pn["correct"]:
                    review_on_miss(pn["app"], pn["text"], now)
                adapt_update(pn["correct"])
            save_review_queue()
            sm, nx = fake_knobs(tier)
            if (sm, nx) != ADAPT.get("last_knobs") and ADAPT["recent"]:
                ADAPT["last_knobs"] = (sm, nx)
                print(f"  🔧 adaptive fakes: {'subtle' if sm else 'crude'} mut + "
                      f"{'near-twin' if nx else 'random'} xapp "
                      f"(recent acc {ADAPT['acc']*100:.0f}%, fooled "
                      f"{ADAPT['fooled_mut']}mut/{ADAPT['fooled_xapp']}xapp)")
            # phase machine: learning -> speed on mastery; speed -> promoted on plateau
            prog = PROGRESS.get(tier)
            if prog and prog.get("phase") == "speed":
                prog["round_times"].append(res["time_s"])
                if prog["best_round_s"] is None or res["time_s"] < prog["best_round_s"] - 0.05:
                    prog["best_round_s"] = res["time_s"]
                    prog["plateau_rounds"] = 0
                else:
                    prog["plateau_rounds"] += 1
                if res.get("speed"):
                    prog["speed_bonuses"] += 1
                if (len(prog["round_times"]) >= SPEED_MIN_ROUNDS
                        and prog["plateau_rounds"] >= SPEED_PLATEAU_ROUNDS):
                    # promotion is BLOCKED until the no-RAG proof passes:
                    # mastered = it can rebuild the tier WITHOUT the library.
                    ragoff_ok = (not args.no_rag_speed or
                                 (len(prog.get("ragoff_recent", [])) >= MASTERY_RAGOFF_WINDOW
                                  and prog.get("ragoff_pct", 0) >= MASTERY_RAGOFF_PCT))
                    if not ragoff_ok:
                        print(f"\n⛔ {tier.upper()} hit its time limit but no-RAG proof "
                              f"is {prog.get('ragoff_pct', 0)}% (need ≥{MASTERY_RAGOFF_PCT}% "
                              f"over {MASTERY_RAGOFF_WINDOW}) — running more no-RAG trials")
                        prog["plateau_rounds"] = 0
                    else:
                        prog["promoted"] = True
                        prog["phase"] = "promoted"
                        print(f"\n🚀 {tier.upper()} MASTERED — time-trial limit "
                              f"(best {prog['best_round_s']}s, {prog['plateau_rounds']} plateau) "
                              f"+ NO-RAG PROOF {prog.get('ragoff_pct', 0)}% — PROMOTING UP")
                        STATUS.setdefault("events", []).append(
                            {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "tier": tier,
                             "event": f"mastered (no-RAG {prog.get('ragoff_pct', 0)}%, "
                                       f"best {prog['best_round_s']}s)",
                             "phase": "promoted"})
                        save_status()
    except KeyboardInterrupt:
        print("\n⏹ stopped by user")
    STATUS["done"] = True
    save_status()
    print(f"\n🏆 final session score: {STATUS['score']:+d}  "
          f"({STATUS['correct']}✅/{STATUS['wrong']}❌ over {STATUS['puzzles']} puzzles, "
          f"acc {STATUS['acc']}%)")
    print(f"📦 training rows → {OUT_DIR}/train-puzzle-r30.jsonl, dpo-puzzle-r30.jsonl")
    if args.status_port:
        print(f"📺 scoreboard stays live at http://0.0.0.0:{args.status_port} (Ctrl-C to stop)")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
