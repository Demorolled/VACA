#!/usr/bin/env python3
"""
index-library-to-rag.py — embed the VACA knowledge library into the RAG store.

Reads every PatternEntry in backend/knowledge/patterns.json (the "main library")
and the micro-app ideas DB (data/micro-app-ideas.json) and:
  1. chunks + embeds each design's code (title + description + code) into the
     existing FAISS vector store from llm-training-app/rag_pipeline.py,
  2. emits a RAG-augmented training sheet (training/dataset/rag-library.jsonl).

Degrades gracefully when sentence-transformers / faiss are missing.

Usage:
  python3 scripts/index-library-to-rag.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "llm-training-app"))

PATTERNS = ROOT / "backend" / "knowledge" / "patterns.json"
IDEAS = ROOT / "data" / "micro-app-ideas.json"
OUT = ROOT / "training" / "dataset" / "rag-library.jsonl"


def pattern_bundle(p: dict) -> str:
    """Render one library pattern as indexable text."""
    return (
        f"Pattern: {p.get('title', '')}\n"
        f"Node type: {p.get('nodeType', '')}  Language: {p.get('language', '')}\n"
        f"Description: {p.get('description', '')}\n"
        f"Tags: {', '.join(p.get('tags', []))}\n"
        f"Code:\n{p.get('code', '')}"
    )


def idea_bundle(idea: dict) -> str:
    files = "".join(
        f"// FILE: {f.get('path', '')}\n{f.get('content', '')}\n\n"
        for f in idea.get("files", [])
    )
    lesson = idea.get("lesson") or idea.get("design") or ""
    return f"App purpose: {idea.get('purpose', '')}\nDesign/Lesson: {lesson}\n\n{files}"


def main() -> int:
    try:
        from llm_training_app_rag import RAGPipeline  # noqa
    except Exception:
        pass
    # Import the real pipeline via module path.
    try:
        from rag_pipeline import RAGPipeline
    except Exception as e:
        print(f"ℹ️  RAG deps unavailable ({e}) — skipping indexing.")
        return 0

    bundles = []
    if PATTERNS.exists():
        for p in json.loads(PATTERNS.read_text(encoding="utf-8")):
            bundles.append((pattern_bundle(p), p.get("title", p.get("id", "pattern"))))
    if IDEAS.exists():
        for idea in json.loads(IDEAS.read_text(encoding="utf-8")):
            bundles.append((idea_bundle(idea), idea.get("purpose", "idea")))

    if not bundles:
        print("No library/idea content to index.")
        return 0

    rag = RAGPipeline()
    total = 0
    rows = []
    for text, src in bundles:
        n = rag.index_text(text, source=src, source_id=src)
        total += n
        # Build a RAG-augmented row for the sheet.
        content, _ = rag.build_rag_context(text, k=5, max_chars=1024)
        rows.append({
            "instruction": f"Write a {src} implementation.",
            "input": "",
            "output": text,
            "rag_context": content,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"✅ Indexed {len(bundles)} library items → {total} passages into RAG store")
    print(f"📝 RAG-augmented training sheet → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())