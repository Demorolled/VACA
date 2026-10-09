#!/usr/bin/env python3
"""
Build the VACA knowledge dataset and merge it into the training split
=======================================================================
Converts the merged VACA knowledge base (data/VACA-MASTER-KNOWLEDGE.md) plus
the wiki (modelVeronice.txt), the reference library (data/library/*.md), the
build-knowledge doc, the design manifesto, and knowledge/patterns.json into
{instruction, input, output, source} JSONL examples — the same format as the
existing training dataset.

Sources and their example styles (matching the existing dataset):
  - modelVeronice.txt sections        → "Explain 'NN. TITLE' in the Visual AI Architect platform."
  - VACA-MASTER-KNOWLEDGE.md parts    → "Explain 'Part X — Title' from the VACA Complete Knowledge Base."
  - data/library/*.md                 → "Explain <doc title>"
  - data/build-knowledge.md           → "Explain Build Knowledge Base — Automated App Generation Patterns"
  - data/design-manifesto.md          → "Explain 🎨 Visual AI Architect — Design Manifesto"
  - knowledge/patterns.json           → per-pattern "Explain the <name> pattern from the VACA knowledge store."

Merge policy (mirrors scripts/merge-campaign50-into-dataset.py):
  - Pool = existing train + val + test + new knowledge examples
  - Dedupe on (instruction, input, output); new examples win on collision
  - New knowledge examples are guaranteed into train (they teach the current
    system state); existing pool fills train to 80%, remainder split 50/50
    into val/test
  - Backs up the 4 files to training/dataset/backup-<timestamp>/
  - Overwrites train.jsonl / val.jsonl / test.jsonl, updates dataset_meta.json
  - Also writes the raw new examples to training/dataset/vaca-knowledge.jsonl

Usage:
  python3 scripts/build-vaca-knowledge-dataset.py [--dry-run] [--no-merge]
"""

import json, os, random, re, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DS_DIR = ROOT / "training" / "dataset"
WIKI = ROOT / "modelVeronice.txt"
MASTER = DATA_DIR / "VACA-MASTER-KNOWLEDGE.md"
LIBRARY = DATA_DIR / "library"
BUILD_KNOWLEDGE = DATA_DIR / "build-knowledge.md"
MANIFESTO = DATA_DIR / "design-manifesto.md"
LARGE_PROGRAM = DATA_DIR / "large-program-architecture.md"
BLUEPRINTS = DATA_DIR / "large-program-blueprints.md"
CODE_LESSONS = DATA_DIR / "code-lessons.md"
CODE_LESSONS_DIR = DATA_DIR / "code-lessons"
PATTERNS = ROOT / "knowledge" / "patterns.json"
NEW_OUT = DS_DIR / "vaca-knowledge.jsonl"

# Priority sources — same list as scripts/merge-campaign50-into-dataset.py.
# These examples teach the fixed import/export/no-JSX contract, counter the
# delegation habit, and teach library-conditioned generation, so they are
# ALWAYS guaranteed into the train split — no matter which merge script runs
# last. Without this, running this knowledge rebuild after the campaign merge
# would re-shuffle verified/captured rows into val/test and silently dilute
# the "verified code stays in train" guarantee.
PRIORITY_FILES = [
    DS_DIR / "campaign50-corrected.jsonl",
    DS_DIR / "self-contained-corrected.jsonl",
    DS_DIR / "captured-verified.jsonl",
    DS_DIR / "verified-generations.jsonl",
    # Curated large-program architecture blueprints — hand-authored ground truth
    # for 25+ file decomposition. Guaranteed into train so the fine-tune learns
    # to plan big programs regardless of which merge script runs last.
    DS_DIR / "large-program-examples.jsonl",
    # Curated code-lessons — hand-authored ground truth for robust code: validate
    # input first, errors are values, XSS-safe DOM, parameterized SQL, no stubs,
    # secrets from config, transactions/no N+1, safe concurrency. Guaranteed into
    # train so the fine-tune learns code-quality behavior regardless of merge order.
    DS_DIR / "code-lessons-examples.jsonl",
    # Curated per-file generation lessons — hand-authored ground truth for writing
    # one file from a blueprint plan entry (exports = the only public API, uses =
    # the only imports, one responsibility). Guaranteed into train so the model
    # learns the per-file contract that keeps 30+ file programs compilable.
    DS_DIR / "file-generation-examples.jsonl",
]

MAX_OUTPUT_CHARS = 4000  # keep examples compact enough for seq-512 training


def clean(text: str) -> str:
    """Normalize whitespace, strip separator decorations."""
    text = re.sub(r"[─═╔╗╚╝║]+\s*", "", text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    # drop pure separator lines
    lines = [ln for ln in lines if not re.fullmatch(r"[=\-─]{8,}", ln.strip())]
    return "\n".join(lines).strip()


def chunk(text: str, limit: int = MAX_OUTPUT_CHARS):
    """Yield text in chunks no larger than limit (at paragraph boundaries)."""
    if len(text) <= limit:
        yield text
        return
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if len(cur) + len(para) + 2 > limit and cur:
            parts.append(cur)
            cur = para
        else:
            cur = (cur + "\n\n" + para) if cur else para
    if cur:
        parts.append(cur)
    yield from parts


def make(instruction: str, output: str, source: str):
    return {"instruction": instruction, "input": "", "output": output, "source": source}


# ─── 1. Wiki sections ────────────────────────────────────────────────────────
def parse_wiki() -> list:
    """Extract 'NN. TITLE' sections from modelVeronice.txt."""
    out = []
    if not WIKI.exists():
        return out
    text = WIKI.read_text(encoding="utf-8", errors="replace")
    # Wiki structure: every section is "==== / NN. TITLE / ==== / <body>".
    # Splitting on ==== therefore isolates each TITLE in its own block and
    # puts the <body> in the NEXT block. So: title blocks match the
    # numbered-title regex; the body is the immediately following block.
    blocks = re.split(r"\n={20,}\n", text)
    for i, b in enumerate(blocks):
        lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue
        title = lines[0]
        if not re.match(r"^\d{1,2}\.\s+\S", title):
            continue
        body_lines = list(lines[1:])
        if i + 1 < len(blocks):  # body block follows the closing ====
            nxt = [ln.strip() for ln in blocks[i + 1].splitlines() if ln.strip()]
            # guard: never consume the next section's TITLE as this body
            if nxt and not re.match(r"^\d{1,2}\.\s+\S", nxt[0]):
                body_lines += nxt
        body = clean("\n".join(body_lines))
        if len(body) < 60:
            continue
        for pi, part in enumerate(chunk(body)):
            instr = f"Explain '{title}' in the Visual AI Architect platform."
            if pi:
                instr = f"Explain '{title}' (part {pi + 1}) in the Visual AI Architect platform."
            out.append(make(instr, part, f"modelVeronice.txt → {title}"))
    return out


# ─── 2. Master knowledge doc ─────────────────────────────────────────────────
def parse_master() -> list:
    """Extract '## Part X' sections; use '###' subsections when present."""
    out = []
    if not MASTER.exists():
        return out
    text = MASTER.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"\n(?=## Part )", text)
    for p in parts:
        m = re.match(r"## (Part \w+ — [^\n]+)", p)
        if not m:
            continue
        part_title = m.group(1).strip()
        # If the part has ### subsections, emit one example per subsection
        subs = re.split(r"\n(?=### )", p)
        if len(subs) > 1:
            for s in subs:
                sm = re.match(r"### ([^\n]+)", s)
                if not sm:
                    continue
                sub_title = sm.group(1).strip()
                body = clean(s.split("\n", 1)[1] if "\n" in s else "")
                if len(body) < 60:
                    continue
                instr = (f"Explain '{sub_title}' from the VACA Complete Knowledge Base "
                         f"(section {part_title}).")
                out.append(make(instr, body, f"VACA-MASTER-KNOWLEDGE.md → {part_title} / {sub_title}"))
        else:
            body = clean(p.split("\n", 1)[1] if "\n" in p else "")
            if len(body) < 60:
                continue
            out.append(make(f"Explain '{part_title}' from the VACA Complete Knowledge Base.",
                            body, f"VACA-MASTER-KNOWLEDGE.md → {part_title}"))
    return out


# ─── 3. Markdown knowledge dirs (library, per-language code lessons) ─────────
def parse_markdown_dir(directory: Path, source_tag: str) -> list:
    """Parse every *.md in a directory: H1 title → chunked Explain examples."""
    out = []
    if not directory.is_dir():
        return out
    for f in sorted(directory.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^#\s+([^\n]+)", text)
        title = m.group(1).strip() if m else f.stem.replace("-", " ").title()
        body = clean(text)
        if len(body) < 60:
            continue
        for i, part in enumerate(chunk(body)):
            instr = f"Explain {title}"
            if i:
                instr = f"Explain {title} (part {i + 1})"
            out.append(make(instr, part, f"{source_tag}/{f.name}"))
    return out


def parse_library() -> list:
    return parse_markdown_dir(LIBRARY, "library")


# ─── 4. Build knowledge + manifesto ──────────────────────────────────────────
def parse_code_lessons() -> list:
    return parse_markdown_dir(CODE_LESSONS_DIR, "data/code-lessons")


def parse_single(f: Path, title: str, tag: str) -> list:
    out = []
    if not f.exists():
        return out
    body = clean(f.read_text(encoding="utf-8", errors="replace"))
    if len(body) < 60:
        return out
    for i, part in enumerate(chunk(body)):
        instr = f"Explain {title}"
        if i:
            instr = f"Explain {title} (part {i + 1})"
        out.append(make(instr, part, tag))
    return out


# ─── 5. Patterns store ───────────────────────────────────────────────────────
def parse_patterns(limit: int = 120) -> list:
    out = []
    if not PATTERNS.exists():
        return out
    try:
        data = json.loads(PATTERNS.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return out
    items = data if isinstance(data, list) else data.get("patterns", [])
    if isinstance(data, dict) and not items:
        items = list(data.values())
    for it in items[:limit]:
        if not isinstance(it, dict):
            continue
        name = it.get("name") or it.get("title") or it.get("id") or "pattern"
        desc = it.get("description") or it.get("summary") or ""
        code = it.get("code") or it.get("template") or ""
        parts = [p for p in (desc, code) if p]
        if not parts:
            continue
        body = clean("\n\n".join(parts))
        if len(body) < 60:
            continue
        out.append(make(f"Explain the '{name}' pattern from the VACA knowledge store.",
                        body, "knowledge/patterns.json"))
    return out


def main():
    dry_run = "--dry-run" in sys.argv
    no_merge = "--no-merge" in sys.argv

    print("=== VACA Knowledge Dataset Builder ===")
    new = []
    new += parse_wiki()
    new += parse_master()
    new += parse_library()
    new += parse_single(BUILD_KNOWLEDGE, "Build Knowledge Base — Automated App Generation Patterns",
                        "data/build-knowledge.md")
    new += parse_single(MANIFESTO, "🎨 Visual AI Architect — Design Manifesto",
                        "data/design-manifesto.md")
    new += parse_single(LARGE_PROGRAM, "Large-Program Architecture — Scaling Multi-File Generation",
                        "data/large-program-architecture.md")
    new += parse_single(BLUEPRINTS, "Large-Program Blueprints — Searchable Catalog of 23 App Architectures",
                        "data/large-program-blueprints.md")
    new += parse_single(CODE_LESSONS, "Code Lessons — Writing Robust, Production-Grade Code",
                        "data/code-lessons.md")
    new += parse_code_lessons()
    new += parse_patterns()

    # Dedupe new examples
    seen, deduped = set(), []
    for ex in new:
        key = (ex["instruction"], ex["output"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ex)
    new = deduped

    print(f"  New knowledge examples: {len(new)}")
    by_src = {}
    for ex in new:
        src = ex["source"].split(" →")[0]
        by_src[src] = by_src.get(src, 0) + 1
    for src, n in sorted(by_src.items()):
        print(f"    {n:>4}  {src}")

    # A true dry run must touch nothing: print the plan, skip the write too.
    # (--no-merge still writes the raw vaca-knowledge.jsonl — that's its
    # documented purpose: produce the file, just don't merge it downstream.)
    if dry_run:
        print(f"  (dry run — would write {NEW_OUT.relative_to(ROOT)} with {len(new)} examples; nothing written)")
        print("  (no merge — stopped)")
        return

    DS_DIR.mkdir(parents=True, exist_ok=True)
    NEW_OUT.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in new) + "\n",
        encoding="utf-8")
    print(f"  Wrote {NEW_OUT.relative_to(ROOT)}")

    if no_merge:
        print("  (no merge — stopped)")
        return

    # ─── Merge into train/val/test ─────────────────────────────────────────
    existing = []
    for name in ("train", "val", "test"):
        f = DS_DIR / f"{name}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    existing.append(json.loads(line))
    print(f"  Existing pool: {len(existing)} examples")

    # Priority sources (campaign / self-contained / captured / verified) are
    # extracted from the pool BEFORE shuffling so they stay guaranteed in train.
    # Same key as merge-campaign50-into-dataset.py: (instruction, input, output).
    def pkey(r):
        return (r.get("instruction", ""), r.get("input", ""), r.get("output", ""))

    priority_keys = set()
    for pf in PRIORITY_FILES:
        if not pf.exists():
            continue
        for line in pf.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                priority_keys.add(pkey(rec))
            except Exception:
                continue
    priority = [e for e in existing if pkey(e) in priority_keys]
    existing = [e for e in existing if pkey(e) not in priority_keys]
    if priority:
        print(f"  Priority sources preserved: {len(priority)} examples (campaign/self-contained/captured/verified)")

    # Dedupe pool against new examples (new wins)
    new_keys = {(e["instruction"], e["output"]) for e in new}
    existing = [e for e in existing if (e["instruction"], e["output"]) not in new_keys]
    print(f"  After dedupe vs new: {len(existing)} existing retained")

    # Sort by a stable key BEFORE the seeded shuffle — same fix as
    # merge-campaign50-into-dataset.py. The pool is re-read from the previous
    # run's (already shuffled) train/val/test files, so a seeded shuffle alone
    # applies its position permutation to a different input order each run →
    # the split drifts and fine-tune runs aren't comparable. Sorting first
    # makes the pre-shuffle order canonical.
    existing.sort(key=pkey)

    rng = random.Random(20260731)
    rng.shuffle(existing)

    total = len(new) + len(priority) + len(existing)
    train_target = int(total * 0.8)
    train = list(new) + list(priority) + existing[: max(0, train_target - len(new) - len(priority))]
    rest = existing[max(0, train_target - len(new) - len(priority)):]
    half = len(rest) // 2
    val, test = rest[:half], rest[half:]

    print(f"  train={len(train)} val={len(val)} test={len(test)}")

    # Backup
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = DS_DIR / f"backup-{ts}"
    backup.mkdir(parents=True, exist_ok=True)
    for name in ("train", "val", "test"):
        f = DS_DIR / f"{name}.jsonl"
        if f.exists():
            shutil.copy2(f, backup / f"{name}.jsonl")
    print(f"  Backed up to {backup.relative_to(ROOT)}")

    for name, rows in (("train", train), ("val", val), ("test", test)):
        (DS_DIR / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8")

    # Update dataset_meta.json
    meta_path = DS_DIR / "dataset_meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta.update({
        "total_examples": len(train) + len(val) + len(test),
        "train_examples": len(train),
        "val_examples": len(val),
        "test_examples": len(test),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "new_knowledge_examples": len(new),
    })
    tag = "vaca-knowledge.jsonl (knowledge base merge)"
    srcs = meta.get("sources", [])
    if tag not in srcs:
        srcs = srcs + [tag]
    meta["sources"] = srcs
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  Updated {meta_path.relative_to(ROOT)}")

    print("=== DONE ===")


if __name__ == "__main__":
    main()
