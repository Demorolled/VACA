#!/usr/bin/env python3
"""
Build the GUI-design fine-tune dataset from the projects/ HTML corpus.
=====================================================================
Implements the DATASET side of the GUI-design training plan (GUI.odt):
"curate component pairs + inject design tokens + strict tokenization".

The corpus: visual-ai-architect/projects/*.html — 96 single-file, self-contained
apps (inline <style> + <script>, vanilla JS, no build step). Every project
yields TWO rows so each fits the QLoRA context budget (2048 tokens ≈ 8KB):

  1. DESIGN row     — instruction asks for the UI; `input` is a deterministic
                      DESIGN-TOKENS block (theme, palette, fonts, spacing,
                      layout, components, behavior, custom props) extracted
                      from the project's own CSS; `output` is the complete
                      HTML document up to the inline <script> — the JS belongs
                      to the behavior row, so cutting at the <script> boundary
                      keeps the design row a valid, complete document
                      (with a `script omitted` marker).
  2. BEHAVIOR row   — instruction asks for the app's inline <script>;
                      `input` is the same token block; `output` is the
                      extracted JavaScript (so the logic tail that HTML
                      truncation would lose is trained separately).

The token block teaches the model the plan's core skill: producing code from
a strict design-token spec instead of free-form prompts. Zero LLM calls —
extraction is deterministic regex/statistics over the project source.

Row schema (engine-compatible): {instruction, input, output, source}
  source: "gui:design:projects/<file>.html" | "gui:behavior:projects/<file>.html"

Usage:
  python3 scripts/build-gui-design-dataset.py                # full build
  python3 scripts/build-gui-design-dataset.py --dry-run      # stats only
  python3 scripts/build-gui-design-dataset.py --max-rows 5   # smoke test
  python3 scripts/build-gui-design-dataset.py --no-behavior  # design rows only

Output: training/dataset/gui-design.jsonl  (the launcher's default dataset).
Bounding-box / screenshot annotation is a future multimodal extension — this
corpus is text-only HTML, so tokens are the coupling mechanism for now.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(ROOT, 'projects')
OUT = os.path.join(ROOT, 'training', 'dataset', 'gui-design.jsonl')

DEFAULT_MAX_OUTPUT_CHARS = 7000   # fits ~1.8k tokens at ~4 chars/token (seq 2048)
DEFAULT_MAX_JS_CHARS = 6000
DEFAULT_MIN_OUTPUT_CHARS = 300

# ─── CSS / HTML extraction regexes ─────────────────────────────────────────

HEX_RE = re.compile(r'#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b')
RGB_RE = re.compile(r'rgba?\([^)]*\)')
HSL_RE = re.compile(r'hsla?\([^)]*\)')
FONT_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)")
RADIUS_RE = re.compile(r'border-radius\s*:\s*([^;}\n]+)')
SPACING_RE = re.compile(r'(?:gap|padding|margin)\s*:\s*([^;}\n]+)')
PROP_RE = re.compile(r'(--[a-zA-Z0-9-]+)\s*:\s*([^;}\n]+)')
SCRIPT_RE = re.compile(r'<script[^>]*>(.*?)</script>', re.S | re.I)
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.S | re.I)
H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S | re.I)
SUB_RE = re.compile(r'<p[^>]*class="[^"]*sub[^"]*"[^>]*>(.*?)</p>', re.S | re.I)

COMPONENT_PATTERNS = [
    ('navbar', r'\b(?:nav|navbar|menu-bar|toolbar)\b'),
    ('header', r'<header\b'),
    ('footer', r'<footer\b'),
    ('sidebar', r'\bsidebar\b'),
    ('cards', r'\bcard\b'),
    ('buttons', r'<button\b'),
    ('inputs', r'<input\b'),
    ('selects', r'<select\b'),
    ('textarea', r'<textarea\b'),
    ('form', r'<form\b'),
    ('table', r'<table\b'),
    ('modal', r'\bmodal\b'),
    ('tabs', r'\btabs?\b|\btab-'),
    ('accordion', r'\baccordion\b'),
    ('toast', r'\btoast\b'),
    ('sliders', r'<input[^>]*type=["\']?range'),
    ('canvas', r'<canvas\b'),
    ('svg', r'<svg\b'),
    ('charts', r'\bchart\b'),
    ('badge', r'\bbadge\b'),
    ('toggle', r'\btoggle\b|\bswitch\b'),
    ('avatar', r'\bavatar\b'),
    ('progress', r'\bprogress\b|\bprogress-bar\b'),
    ('tooltip', r'\btooltip\b'),
    ('breadcrumb', r'\bbreadcrumb\b'),
    ('carousel', r'\bcarousel\b|\bslider\b'),
    ('timeline', r'\btimeline\b'),
    ('stat', r'\bstat\b'),
    ('icon', r'\bicon\b'),
]

LAYOUT_FLAGS = [
    ('flex', r'display\s*:\s*flex'),
    ('grid', r'display\s*:\s*grid'),
    ('responsive', r'@media'),
    ('sticky', r'position\s*:\s*(?:sticky|fixed)'),
    ('centered', r'justify-content\s*:\s*center'),
    ('max-width', r'max-width\s*:\s*\d'),
]

FEATURE_PATTERNS = [
    ('live preview', r'\bpreview\b'),
    ('export', r'\bexport\b|\bdownload\b|\bsave\b'),
    ('localStorage', r'\blocalStorage\b'),
    ('drag & drop', r'\bdrag|draggable\b'),
    ('keyboard', r'addEventListener\([\'"]key'),
    ('clipboard', r'\bclipboard\b'),
    ('fetch/API', r'\bfetch\s*\('),
    ('WebSocket', r'\bWebSocket\b'),
    ('timer', r'\bsetInterval\b|\bsetTimeout\b'),
    ('animation', r'\brequestAnimationFrame\b|\b@keyframes\b|\banimation\b'),
    ('audio', r'<audio\b|\bAudio\s*\('),
    ('video', r'<video\b'),
    ('canvas drawing', r'\.getContext\s*\('),
    ('file input', r'type=["\']?file'),
    ('search', r'\bsearch\b|\bfilter\b'),
    ('chart rendering', r'\bnew\s+(?:Chart|plotly|d3)\b'),
]

def parse_color(c: str):
    """Return (r, g, b) 0..1 floats for #hex or rgb()/hsl() strings, else None."""
    c = c.strip().lower()
    if c.startswith('#'):
        h = c.lstrip('#')
        if len(h) in (3, 4):
            h = ''.join(ch * 2 for ch in h[:3])
        if len(h) >= 6:
            try:
                return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
            except ValueError:
                return None
        return None
    m = re.match(r'rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)', c)
    if m:
        return tuple(min(1.0, float(g) / 255) for g in m.groups())
    return None


def luminance(c: str) -> float:
    """Relative luminance (0=black, 1=white) of a color string; 0.5 on parse fail."""
    rgb = parse_color(c)
    if not rgb:
        return 0.5
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_neutral(c: str) -> bool:
    """Near-black / near-white colors don't carry design identity."""
    lum = luminance(c)
    return lum < 0.08 or lum > 0.92


def strip_tags(s: str) -> str:
    return re.sub(r'<[^>]+>', '', s or '').strip()


def extract_design_tokens(html: str, title: str) -> str:
    """Deterministic design-token block: what the model must reproduce."""
    style_section = ''
    ms = re.search(r'<style[^>]*>(.*?)</style>', html, re.S | re.I)
    if ms:
        style_section = ms.group(1)
    css = style_section + ' ' + html  # inline styles count too

    # Colors — frequency-ranked; skip near-black/white neutrals for the palette.
    colors = []
    for m in HEX_RE.findall(css):
        colors.append(m.lower())
    for m in RGB_RE.findall(css):
        colors.append(m.strip().lower())
    for m in HSL_RE.findall(css):
        colors.append(m.strip().lower())
    counts = Counter(colors)
    # Palette: non-neutral colors, deduped by base rgb (alpha variants of the
    # same accent collapse into one entry) and frequency-ranked.
    seen_rgb = set()
    palette = []
    for c, _ in counts.most_common(20):
        if is_neutral(c):
            continue
        rgb = parse_color(c)
        key = rgb[:3] if rgb else c
        if key in seen_rgb:
            continue
        seen_rgb.add(key)
        palette.append(c)
        if len(palette) >= 5:
            break
    # Theme: prefer the body/html background declaration, falling back to the
    # most frequent hex color (a text color like #ccc must not flip a dark app).
    # The background value may be a shorthand (gradient, url, multiple tokens) —
    # extract the FIRST hex/rgb token from it rather than luminance()ing the
    # whole string (which would parse-fail and report a wrong 'light').
    theme = 'light'
    bg_m = re.search(r'(?:body|html)[^{]*\{[^}]*?background(?:-color)?\s*:\s*([^;}\n]+)', css, re.I)
    if bg_m:
        bg_tokens = HEX_RE.findall(bg_m.group(1)) + RGB_RE.findall(bg_m.group(1))
        if bg_tokens:
            theme = 'dark' if luminance(bg_tokens[0]) < 0.5 else 'light'
    if bg_m is None or not (HEX_RE.search(bg_m.group(1)) or RGB_RE.search(bg_m.group(1))):
        for c, _ in counts.most_common():
            if c.startswith('#'):
                theme = 'dark' if luminance(c) < 0.5 else 'light'
                break

    # Fonts (skip identity-less values and dupes; strip quotes per component so
    # 'Segoe UI',Arial becomes Segoe UI, Arial — no stray quotes in the token).
    skip_fonts = {'inherit', 'initial', 'unset', 'revert'}
    fonts = []
    for f in FONT_RE.findall(css):
        names = [n.strip().strip('\'"') for n in re.split(r'\s*,\s*', f) if n.strip()]
        for name in names:
            if name and name.lower() not in skip_fonts and name not in fonts:
                fonts.append(name)
    fonts = fonts[:3]

    # Spacing: radius values + gap/padding values; 4px-scale verdict.
    radii = []
    for r in RADIUS_RE.findall(css):
        radii.append(r.strip().strip('\'"'))
    spacing_vals = []
    for s in SPACING_RE.findall(css):
        for part in s.split():
            m = re.match(r'^(\d+(?:\.\d+)?)(px|rem|em)?$', part)
            if m:
                spacing_vals.append(float(m.group(1)))
    # all() on an empty list is True — only claim a scale when spacing was found.
    scale = '4px unit' if spacing_vals and all(v % 4 == 0 for v in spacing_vals) else (
        'mixed' if spacing_vals else 'none')

    # Layout flags.
    layout = [name for name, pat in LAYOUT_FLAGS if re.search(pat, css)]

    # Components + behaviors.
    components = [name for name, pat in COMPONENT_PATTERNS if re.search(pat, html, re.I)]
    behaviors = [name for name, pat in FEATURE_PATTERNS if re.search(pat, html, re.I)]

    # CSS custom properties.
    props = [f'{k}: {v.strip()}' for k, v in PROP_RE.findall(style_section)][:6]

    lines = ['━━━ DESIGN TOKENS (MANDATORY) ━━━', f'app: {title}']
    if palette:
        lines.append('palette: ' + ' · '.join(palette))
    lines.append(f'theme: {theme}')
    if fonts:
        lines.append('fonts: ' + ' · '.join(fonts))
    lines.append(f'spacing: {scale}' + (f' · radii {", ".join(radii[:4])}' if radii else ''))
    if layout:
        lines.append('layout: ' + ', '.join(layout))
    if components:
        lines.append('components: ' + ', '.join(components))
    if behaviors:
        lines.append('behavior: ' + ', '.join(behaviors))
    if props:
        lines.append('custom-props: ' + '; '.join(props))
    return '\n'.join(lines)


def extract_js(html: str) -> str:
    bodies = []
    for m in SCRIPT_RE.finditer(html):
        body = m.group(1).strip()
        if body:
            bodies.append(body)
    return '\n\n'.join(bodies)


def extract_title(html: str, filename: str) -> str:
    m = TITLE_RE.search(html)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return filename.replace('.html', '').replace('-', ' ').title()


def extract_desc(html: str) -> str:
    for m in (H1_RE.search(html), SUB_RE.search(html)):
        if m:
            t = strip_tags(m.group(1))
            if t:
                return t
    return ''


def cut_at_line_boundary(text: str, cap: int, kind: str = 'html') -> str:
    """Cut at a clean boundary <= cap so a truncated row never ends mid-token.

    Statement/block boundaries take priority over a newline: in minified code a
    newline is often just pretty-printing INSIDE a statement ("try {\n"), which
    would leave the row mid-expression. A boundary char is a complete
    statement/element regardless of WHERE it sits in the window — a cut at 30%
    is better than a raw cap cut mid-token — so only the newline fallback keeps
    a position gate (avoid stopping after just a few lines)."""
    if len(text) <= cap:
        return text, False
    # html rows: '>' closes an element; ';' / '}' cover a giant minified
    # <style> block. js rows: ';' / '}' only — a '>' in JS is a comparison
    # operator or template content, NOT a statement boundary.
    boundary_chars = ('>', ';', '}') if kind == 'html' else (';', '}')
    cut = -1
    for ch in boundary_chars:
        idx = text.rfind(ch, 0, cap)
        if idx >= 0:
            cut = idx + 1  # keep the boundary char
            break
    if cut < 0:
        # No statement boundary in the window: fall back to a complete line
        # (e.g. pretty-printed code that was never minified), else raw cap.
        nl = text.rfind('\n', 0, cap)
        if nl >= cap * 0.5:
            cut = nl
        else:
            cut = cap
    return text[:cut] + '\n<!-- [builder] truncated at boundary (original %d chars) -->' % len(text), True


SCRIPT_TAG_RE = re.compile(r'<script\b', re.I)
SCRIPT_OMITTED_MARKER = ('<!-- [builder] script omitted: the inline <script> is the '
                         'subject of the BEHAVIOR row (see DESIGN TOKENS behavior). -->')


def cut_design_output(html: str, cap: int):
    """The DESIGN row's output is the HTML document UP TO the inline <script>.

    The <script> content is the behavior row's job — embedding it here would
    either blow the token budget or force a mid-JS truncation. Cutting at the
    script tag keeps the design row a complete, valid HTML document: the model
    learns the full markup and the DESIGN-TOKENS behavior list tells it what
    the (omitted) script must implement."""
    m = SCRIPT_TAG_RE.search(html)
    if m is None:
        return cut_at_line_boundary(html, cap, kind='html')
    head = html[:m.start()]
    if len(head) <= cap:
        return head + '\n' + SCRIPT_OMITTED_MARKER, len(html) > cap
    cut, _ = cut_at_line_boundary(head, cap, kind='html')
    return cut + '\n' + SCRIPT_OMITTED_MARKER, True


SCRIPT_TAG_RE = re.compile(r'<script\b', re.I)


def cut_design_output(html: str, cap: int):
    """The DESIGN row's output is the HTML document UP TO the inline <script>.

    The <script> content is the behavior row's job — embedding it here would
    either blow the token budget or force a mid-JS truncation. Cutting at the
    script tag keeps the design row a complete, valid HTML document: the model
    learns the full markup and the DESIGN-TOKENS behavior list tells it what
    the (omitted) script must implement."""
    m = SCRIPT_TAG_RE.search(html)
    if m is None:
        return cut_at_line_boundary(html, cap, kind='html')
    head = html[:m.start()]
    if len(head) <= cap:
        return (head + '\n<!-- [builder] script omitted: the inline <script> is the '
                       'subject of the BEHAVIOR row (see DESIGN TOKENS behavior). -->',
                len(html) > cap)
    cut, _ = cut_at_line_boundary(head, cap, kind='html')
    return (cut + '\n<!-- [builder] script omitted: the inline <script> is the '
                  'subject of the BEHAVIOR row (see DESIGN TOKENS behavior). -->',
            True)


def build_design_row(filename, html, tokens, cap):
    title = extract_title(html, filename)
    desc = extract_desc(html)
    # The <h1> often echoes the <title> — don't repeat it in the instruction.
    if desc and (title.lower() in desc.lower() or desc.lower() in title.lower()):
        desc = ''
    instruction = (
        f'Build a single-file, self-contained HTML app: {title}'
        + (f' — {desc}' if desc else '')
        + '. Honor the DESIGN TOKENS below exactly: same theme, palette, '
          'fonts, spacing scale, layout structure, components and behavior. '
          'No external files and no build step: inline <style> and <script>, '
          'vanilla JavaScript, dense production-quality UI.'
    )
    output, truncated = cut_design_output(html, cap)
    return {
        'instruction': instruction,
        'input': tokens,
        'output': output,
        'source': f'gui:design:projects/{filename}',
    }, truncated


def build_behavior_row(filename, html, tokens, js, cap):
    title = extract_title(html, filename)
    instruction = (
        f'Write the complete inline <script> for the {title} app (a single-file '
        'HTML page). Wire every control in the DESIGN TOKENS component list and '
        'implement all behaviors listed there. Vanilla JavaScript only — no '
        'frameworks, no external files, no build step. Return ONLY the script '
        'content, no <script> tags.'
    )
    output, truncated = cut_at_line_boundary(js, cap, kind='js')
    return {
        'instruction': instruction,
        'input': tokens,
        'output': output,
        'source': f'gui:behavior:projects/{filename}',
    }, truncated


def main():
    ap = argparse.ArgumentParser(description='Build the GUI-design dataset from projects/')
    ap.add_argument('--dry-run', action='store_true', help='stats only, no write')
    ap.add_argument('--max-rows', type=int, default=0, help='hard row cap (0 = none)')
    ap.add_argument('--max-output-chars', type=int, default=DEFAULT_MAX_OUTPUT_CHARS)
    ap.add_argument('--max-js-chars', type=int, default=DEFAULT_MAX_JS_CHARS)
    ap.add_argument('--min-chars', type=int, default=DEFAULT_MIN_OUTPUT_CHARS)
    ap.add_argument('--no-behavior', action='store_true', help='design rows only')
    ap.add_argument('--out', default=OUT, help='output jsonl path')
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(PROJECTS_DIR) if f.endswith('.html'))
    if not files:
        print(f'[build-gui] ❌ no *.html found in {PROJECTS_DIR}')
        sys.exit(1)

    rows = []
    stats = {'design': 0, 'behavior': 0, 'skipped_too_small': 0, 'truncated': 0,
             'no_js': 0, 'design_over_budget': 0, 'behavior_over_budget': 0}
    lengths = []
    for filename in files:
        with open(os.path.join(PROJECTS_DIR, filename), encoding='utf-8', errors='replace') as f:
            html = f.read()
        title = extract_title(html, filename)
        tokens = extract_design_tokens(html, title)

        design_row, trunc = build_design_row(filename, html, tokens, args.max_output_chars)
        if len(design_row['output']) < args.min_chars:
            stats['skipped_too_small'] += 1
            continue
        rows.append(design_row)
        stats['design'] += 1
        if trunc:
            stats['truncated'] += 1
        if len(design_row['output']) / 4 > 2048:
            stats['design_over_budget'] += 1
        lengths.append(len(design_row['output']))

        if not args.no_behavior:
            js = extract_js(html)
            if js:
                behavior_row, trunc_js = build_behavior_row(filename, html, tokens, js, args.max_js_chars)
                if len(behavior_row['output']) >= args.min_chars:
                    rows.append(behavior_row)
                    stats['behavior'] += 1
                    if trunc_js:
                        stats['truncated'] += 1
                    if len(behavior_row['output']) / 4 > 2048:
                        stats['behavior_over_budget'] += 1
            else:
                stats['no_js'] += 1

    if args.max_rows and len(rows) > args.max_rows:
        rows = rows[:args.max_rows]

    lengths.sort()
    n = len(lengths)
    pct = lambda p: lengths[min(n - 1, int(n * p))] if n else 0
    print(f'[build-gui] projects scanned: {len(files)}')
    print(f'[build-gui] rows: {len(rows)} (design={stats["design"]}, behavior={stats["behavior"]}, '
          f'no_js={stats["no_js"]}, skipped_too_small={stats["skipped_too_small"]}, '
          f'truncated={stats["truncated"]})')
    print(f'[build-gui] output chars: min={lengths[0] if n else 0} median={pct(0.5)} '
          f'p75={pct(0.75)} max={lengths[-1] if n else 0} '
          f'(est. tokens max={lengths[-1] // 4 if n else 0})')
    if stats['design_over_budget'] or stats['behavior_over_budget']:
        print(f'[build-gui] ⚠️ rows exceeding ~2048-token budget: '
              f'design={stats["design_over_budget"]} behavior={stats["behavior_over_budget"]}')

    if args.dry_run:
        print('[build-gui] --dry-run: nothing written')
        sys.exit(0)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'[build-gui] wrote {len(rows)} row(s) → {args.out}')
    if rows:
        sample = rows[0]
        print('[build-gui] sample row:')
        print('  instruction:', sample['instruction'][:120] + '…')
        print('  input:', sample['input'].replace('\n', ' | ')[:200] + '…')
        print('  output head:', sample['output'][:80].replace('\n', '⏎'))


if __name__ == '__main__':
    main()
