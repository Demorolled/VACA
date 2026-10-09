#!/usr/bin/env python3
"""
build-r23-bible-code.py — R23 bible-code segment
=================================================
Mines the code knowledge from bible-reference/ (the 965 markdown guides) into
instruction/output training rows: each substantial code block becomes a
"write the {lang} implementation following the {level} bible pattern" row.

Quality controls:
  - code fences only (```lang ... ```), lang tag required
  - output passes the VACA poison gate (no fences/separators/stubs/prose)
  - dedupe by (level, content) hash and against the hand-authored R23 rows
  - cap per level (max 3) and total (--max-rows) to keep the round fast
  - never emits a row for a block that is mostly non-code (junk ratio)

Outputs:
  training/cloud/round23-bible-code.jsonl   (this segment)

Usage:
  python3 scripts/build-r23-bible-code.py [--max-rows 400]
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIBLE = ROOT / "bible-reference"
OUT = ROOT / "training" / "cloud" / "round23-bible-code.jsonl"
R23_SEED = ROOT / "training" / "cloud" / "round23-reasoning-all.jsonl"

FENCE_RE = re.compile(r"^```", re.M)
STUB_RE = re.compile(
    r"not implemented|placeholder|coming soon|lorem ipsum|unimplemented|"
    r"TODO: Implement|FIXME|\bpass\s*#\s*(TODO|not)|throw new Error\(['\"]not", re.I
)
JUNK_LINE_RE = re.compile(r"^\s*(?:#+\s|[-*]\s|>|```|$)")
MIN_BLOCK_CHARS = 160
MAX_PER_LEVEL = 3


def fence_blocks(text: str):
    """Yield (lang, code) for each ```lang fence pair."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*```([a-zA-Z0-9+#-]*)", lines[i])
        if m:
            lang = m.group(1).strip()
            j = i + 1
            buf = []
            while j < len(lines) and not re.match(r"^\s*```", lines[j]):
                buf.append(lines[j])
                j += 1
            if j < len(lines):
                yield lang, "\n".join(buf)
                i = j + 1
                continue
        i += 1


def gate(code: str) -> bool:
    if len(code.strip()) < MIN_BLOCK_CHARS:
        return False
    if STUB_RE.search(code):
        return False
    lines = code.split("\n")
    if not lines:
        return False
    # Junk-ratio: if more than a third of lines look like prose/markdown, skip.
    prose = sum(1 for l in lines if JUNK_LINE_RE.match(l) and not re.search(r"[;{}()=<>]", l))
    return prose / len(lines) < 0.34


def topic_of(content: str) -> str:
    for line in content.split("\n"):
        t = line.strip().lstrip("#").strip()
        if t and len(t) > 6 and not t.startswith("```"):
            return t[:90]
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=400)
    args = ap.parse_args()

    # Existing hand-authored R23 keys to dedupe against.
    seen = set()
    if R23_SEED.exists():
        for line in R23_SEED.open():
            try:
                r = json.loads(line)
                seen.add(hashlib.sha1((r.get("instruction", "") + r.get("output", "")).encode()).hexdigest())
            except json.JSONDecodeError:
                pass

    rows = []
    levels = sorted([d for d in BIBLE.iterdir() if d.is_dir()])
    for level in levels:
        name = level.name
        count = 0
        for f in sorted(level.glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            topic = topic_of(content) or name
            for lang, code in fence_blocks(content):
                if not lang or not gate(code):
                    continue
                lang_clean = lang.split("+")[0].strip()
                instruction = (
                    f"Write the {lang_clean} implementation following the "
                    f"bible-reference '{name}' pattern ({topic})."
                )
                key = hashlib.sha1((instruction + code).encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "category": "code",
                    "instruction": instruction,
                    "input": "",
                    "output": code.strip(),
                    "source": f"bible:{name}/{f.name}",
                })
                count += 1
                if count >= MAX_PER_LEVEL:
                    break
            if count >= MAX_PER_LEVEL:
                break

    rows = rows[: args.max_rows]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    print(f"✅ bible-code segment: {len(rows)} rows → {OUT}")
    print("   by level:", dict(Counter(r["source"].split(":")[1].split("/")[0] for r in rows).most_common(10)))


if __name__ == "__main__":
    main()
