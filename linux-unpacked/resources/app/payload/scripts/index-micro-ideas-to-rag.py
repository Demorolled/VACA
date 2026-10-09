#!/usr/bin/env python3
"""
index-micro-ideas-to-rag.py — turn the verified micro-app builds into RAG
training material.

For every stored idea in data/micro-app-ideas.json it:
  1. chunks + embeds the WINNING code (purpose + lesson + files) into the
     existing RAG vector store (llm-training-app/rag_pipeline.py, FAISS),
  2. emits a RAG-augmented training sheet (training/dataset/
     rag-micro-app-ideas.jsonl) — each row is the idea text prefixed with its
     top retrieved context, ready for RAG-style training
     (augment_training_text_with_rag).

Runs fine when sentence-transformers / faiss are NOT installed: it reports
"RAG deps unavailable" and exits 0 so callers (the backend endpoint) can treat
it as a soft no-op.

Usage:
  python3 scripts/index-micro-ideas-to-rag.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "llm-training-app"))

IDEAS = ROOT / "data" / "micro-app-ideas.json"
OUT = ROOT / "training" / "dataset" / "rag-micro-app-ideas.jsonl"


def idea_bundle(idea: dict) -> str:
    """Render one idea (purpose + lesson + files) as a single text block."""
    files = "".join(
        f"// FILE: {f.get('path', '')}\n{f.get('content', '')}\n\n"
        for f in idea.get("files", [])
    )
    lesson = idea.get("lesson") or idea.get("design") or ""
    return f"App purpose: {idea.get('purpose', '')}\nDesign/Lesson: {lesson}\n\n{files}"


def main() -> int:
    if not IDEAS.exists():
        print(json.dumps({"ok": False, "error": "no ideas db at data/micro-app-ideas.json"}))
        return 1

    ideas = json.loads(IDEAS.read_text(encoding="utf-8")) if IDEAS.exists() else []
    if not ideas:
        print(json.dumps({"ok": False, "error": "no stored ideas to index"}))
        return 0

    try:
        from rag_pipeline import RAGPipeline
    except Exception as e:  # sentence-transformers / faiss missing
        print(json.dumps({"ok": False, "error": f"RAG deps unavailable: {e}"}))
        return 0

    rag = RAGPipeline()
    indexed = 0
    rows = []
    for idea in ideas:
        text = idea_bundle(idea)
        if len(text.strip()) < 20:
            continue
        rag.index_text(
            text,
            source=idea.get("purpose", "untitled"),
            source_id=idea.get("id", ""),
        )
        indexed += 1
        try:
            ctx, _ = rag.build_rag_context(text, k=3, max_chars=1200)
        except Exception:
            ctx = ""
        rows.append({
            "text": (f"<RAG_CONTEXT>\n{ctx}\n</RAG_CONTEXT>\n\n{text}" if ctx else text),
            "title": f"RAG micro-app idea — {idea.get('purpose', '')}",
            "language": "mixed",
            "tags": ["micro-app-idea", "rag", "self-improve", *(idea.get("focus") or [])],
            "nodeType": "micro_app_idea",
            "source": "micro-app-rag",
            "timestamp": idea.get("createdAt", ""),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n" if rows else "",
        encoding="utf-8",
    )

    n_vectors = rag.vector_store.index.ntotal if rag.vector_store.index else 0
    print(json.dumps({
        "ok": True,
        "indexed": indexed,
        "stored_ideas": len(ideas),
        "vectors": n_vectors,
        "sheet": str(OUT),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())