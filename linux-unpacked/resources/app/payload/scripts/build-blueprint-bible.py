#!/usr/bin/env python3
"""
Build the blueprint bible (backend/blueprints/generated/) from data sources
============================================================================
Converts every existing catalog into the ODT blueprint JSON format
(app_type / target_stack / architecture_checklist / wiring_graph) that the
backend bible loader (backend/src/blueprint/bible.ts) consumes:

  1. data/design-specs-v2.json        — ~282 interactive app/algorithm tool
     templates across 10 categories. Each entry is {name, goal, tags} with no
     module decomposition, so the checklist is derived deterministically from
     a per-category module template (ui_screens + domain engines/stores).
     Target stack is the standard interactive web stack (React/Node/SQLite).

  2. data/large-program-blueprints.md — 39 curated large-program blueprints
     (Go / TypeScript / Python / C#). Each entry lists a Goal and Feature
     slices; the slices become the architecture_checklist and the section
     header determines the target_stack (and thus the source language).

  3. data/designs.json                — 800+ REAL saved canvas designs. Their
     node labels become the checklist and their resolved edges the wiring
     graph (human-arranged decompositions). Deduped by goal.

  4. projects/*.html                  — 90+ REAL complete single-file apps.
     Title/description drive semantic matching; a keyword table enriches the
     module checklist with the domain's engine (game, audio, image, ...).

Wiring: generated entries get a deterministic linear data-flow chain across
their modules (curated bible entries keep their hand-authored wiring_graph).

Output: one JSON file per blueprint in backend/blueprints/generated/
(regenerated idempotently — stale files in the output dir are removed first).
Adds a `source` field for provenance; the loader ignores extra fields.

Usage:
  python3 scripts/build-blueprint-bible.py [--dry-run] [--out DIR]
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DESIGN_SPECS = ROOT / "data" / "design-specs-v2.json"
LARGE_PROGRAM = ROOT / "data" / "large-program-blueprints.md"
DESIGNS = ROOT / "data" / "designs.json"
PROJECTS_DIR = ROOT / "projects"
DEFAULT_OUT = ROOT / "backend" / "blueprints" / "generated"

# ─── Target stacks ─────────────────────────────────────────────────────────
# The backend's detectLanguage() scans these strings for go/python/csharp/rust,
# so each stack must contain the keyword for its intended language.

WEB_STACK = {"frontend": "React", "backend": "Node.js Express", "database": "SQLite"}

LANG_STACKS = {
    "go": {"frontend": "React (static)", "backend": "Go", "database": "PostgreSQL"},
    "typescript": WEB_STACK,
    "python": {"frontend": "React", "backend": "Python FastAPI", "database": "SQLite"},
    "csharp": {"frontend": "Blazor", "backend": "C# .NET", "database": "SQL Server"},
}

# ─── Per-category module templates (design-specs entries) ─────────────────
# Module names are chosen so the backend's moduleNodeType() inference lands on
# the right lane (ui / database / api / input / output / logic). The first
# module is always ui_screens so generated apps get a previewable UI.
CATEGORY_TEMPLATES = {
    "fundamentals":      ["ui_screens", "canvas_ui", "algorithm_core", "input_handler", "dataset_store", "visualization_engine"],
    "games":             ["ui_screens", "game_engine", "input_handler", "score_store", "canvas_ui"],
    "desktop":           ["ui_screens", "core_engine", "input_handler", "local_store", "settings_service"],
    "systems":           ["ui_screens", "file_loader", "analysis_engine", "visualization_engine", "report_renderer"],
    "database":          ["ui_screens", "storage_engine", "query_engine", "visualization_engine", "dataset_store"],
    "mathematics":       ["ui_screens", "math_core", "input_handler", "plot_renderer", "dataset_store"],
    "specialized":       ["ui_screens", "core_engine", "render_engine", "input_handler", "dataset_store"],
    "data-engineering":  ["ui_screens", "file_loader", "format_engine", "schema_models", "visualization_engine"],
    "devops":            ["ui_screens", "config_engine", "validator_core", "input_handler", "export_service"],
    "search":            ["ui_screens", "index_store", "query_engine", "visualization_engine", "dataset_store"],
}

# Generic data-contract labels cycled through linear-chain wiring.
WIRING_LABELS = ["requests", "results", "state_and_events", "data", "updates"]

CATEGORY_DOMAIN = {
    "fundamentals": "algorithm", "games": "game", "desktop": "desktop utility",
    "systems": "systems", "database": "database", "mathematics": "mathematics",
    "specialized": "computing", "data-engineering": "data engineering",
    "devops": "devops", "search": "search",
}


def slugify(name: str) -> str:
    """Lowercase slug: non-alphanumerics become single underscores."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "untitled"


def default_wiring(modules: list) -> list:
    """Linear data-flow chain across modules (deterministic for generated entries)."""
    return [
        {
            "source_module": modules[i],
            "destination_module": modules[i + 1],
            "data_passed": WIRING_LABELS[i % len(WIRING_LABELS)],
        }
        for i in range(len(modules) - 1)
    ]


# ─── Source 1: data/design-specs-v2.json ──────────────────────────────────

def build_design_specs_blueprints() -> tuple:
    """Return (blueprints, warnings)."""
    data = json.loads(DESIGN_SPECS.read_text(encoding="utf-8"))
    blueprints = []
    warnings = []
    seen_slugs = set()
    categories = data.get("categories", {})
    meta_total = data.get("meta", {}).get("total", 0)

    for category, spec in categories.items():
        template = CATEGORY_TEMPLATES.get(category)
        if template is None:
            warnings.append(f"design-specs: no module template for category '{category}' — skipped")
            continue
        for design in spec.get("designs", []):
            name = design.get("name") or "Untitled"
            goal = design.get("goal") or ""
            tags = design.get("tags") or []
            base = slugify(name)
            slug = base
            n = 2
            while slug in seen_slugs:
                slug = f"{base}_{n}"
                n += 1
            seen_slugs.add(slug)

            keywords = [category] + [t for t in tags] + re.findall(r"[a-z0-9']+", name.lower())
            description = (
                f"{goal} — an interactive {CATEGORY_DOMAIN.get(category, category)} tool "
                f"with a visual interface."
            )
            blueprints.append({
                "app_type": slug,
                "description": description,
                "keywords": keywords,
                "target_stack": dict(WEB_STACK),
                "architecture_checklist": list(template),
                "wiring_graph": default_wiring(template),
                "source": f"design-specs-v2.json:{category}",
            })

    if meta_total and meta_total != len(blueprints):
        warnings.append(f"design-specs: meta.total={meta_total} but {len(blueprints)} designs were found in categories")
    return blueprints, warnings


# ─── Source 2: data/large-program-blueprints.md ────────────────────────────

LANG_HEADER = re.compile(r"^## (.+?) blueprints", re.IGNORECASE)

# Normalize section-header language names to LANG_STACKS keys.
LANG_NORMALIZE = {"c#": "csharp"}
ENTRY_HEADER = re.compile(r"^### \d+\.\s+([A-Za-z0-9_-]+)\s*[—-]\s*(.+?)\s*(?:\((\d+)\s*files?\))?\s*$")
FIELD = re.compile(r"^-\s*\*\*([^*]+):\*\*\s*(.*)$")


def parse_large_program() -> list:
    """Parse the catalog into entries: {slug, title, files, language, goal, slices}."""
    entries = []
    current_lang = None
    current = None

    def finish():
        nonlocal current
        if current is not None and (current.get("_slices_items") or current.get("_slices_text")):
            entries.append(current)
        current = None

    for raw in LARGE_PROGRAM.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        # Any `## ` header starts a new section. Language sections reset the
        # language; every other section (How to use, Quick reference, Domain
        # index, Blueprint anatomy, ...) resets it to None so stray `###`
        # entries can never be attributed to the previous language.
        if line.startswith("## "):
            finish()
            m = LANG_HEADER.match(line)
            if m:
                raw_lang = m.group(1).strip().lower()
                current_lang = LANG_NORMALIZE.get(raw_lang, raw_lang)
            else:
                current_lang = None
            continue
        m = ENTRY_HEADER.match(line)
        if m:
            finish()
            current = {
                "slug": m.group(1),
                "title": m.group(2).strip(),
                "files": int(m.group(3)) if m.group(3) else None,
                "language": current_lang,
                "goal": "",
                "slices": [],
            }
            continue
        if current is None:
            continue
        m = FIELD.match(line)
        if m:
            field = m.group(1).strip().lower().replace(" ", "_")
            current["_field"] = field
            if field == "feature_slices":
                current["_slices_text"] = m.group(2).strip()
                current["_slices_items"] = []
            else:
                current[field] = m.group(2).strip()
            continue
        # Continuation / slice-list lines are indented by two spaces.
        if line.startswith("  ") and current.get("_field"):
            body = line.strip()
            if current["_field"] == "feature_slices":
                if body.startswith("- "):
                    current["_slices_items"].append(body[2:].strip())
                elif current["_slices_text"]:
                    current["_slices_text"] += " " + body
            else:
                # Multi-line Goal/Reasoning/... — append to the ACTIVE field,
                # never to a hardcoded field.
                field_name = current["_field"]
                if field_name in current and isinstance(current[field_name], str):
                    current[field_name] += " " + body

    finish()
    return entries


def finalize_slices(entry: dict) -> list:
    """Slice names from either the bulleted list or the inline '·'-separated text."""
    items = entry.get("_slices_items") or []
    if items:
        names = []
        for item in items:
            clean = item.replace("`", "").strip()
            # `users` → User: auth + quota limits  ⇒  name is everything before '→'
            name = clean.split("→")[0].split(":")[0].strip()
            if name:
                names.append(name)
        return names
    text = entry.get("_slices_text", "")
    if not text:
        return []
    return [part.strip().rstrip(".").strip() for part in text.split("·") if part.strip()]


def build_large_program_blueprints() -> list:
    """Convert catalog entries into bible blueprints."""
    blueprints = []
    for entry in parse_large_program():
        lang = entry.get("language")
        stack = LANG_STACKS.get(lang)
        if stack is None:
            continue  # e.g. the 'Domain index' / 'Blueprint anatomy' sections
        slices = finalize_slices(entry)
        if not slices:
            continue
        title_tokens = re.findall(r"[a-z0-9']+", entry["title"].lower())
        keywords = [entry["slug"], lang] + title_tokens + [s for s in slices]
        description = entry.get("goal") or f"{entry['title']} — large-program blueprint ({lang})."
        blueprint = {
            "app_type": entry["slug"],
            "description": description,
            "keywords": keywords,
            "target_stack": dict(stack),
            "architecture_checklist": slices,
            "wiring_graph": default_wiring(slices),
            "source": "large-program-blueprints.md:" + (lang or "?"),
        }
        if entry.get("files"):
            blueprint["file_count"] = entry["files"]
        blueprints.append(blueprint)
    return blueprints


# ─── Source 3: data/designs.json (real user-built node graphs) ────────────
# 800+ saved canvas designs. Each has a real node graph (labels + edges), so
# the node labels become the architecture_checklist and the resolved edges the
# wiring_graph — real, human-arranged decompositions. Filtered + deduped.

# Default canvas-template labels carry no decomposition signal.
GENERIC_NODE_LABELS = {
    "user input", "core logic", "output", "master", "master node", "untitled",
    "main", "input", "logic", "database", "ui", "api", "data", "node", "default",
}

# Fallback checklist when a design is all generic labels (still a valid routing entry).
DESIGN_FALLBACK_MODULES = ["ui_screens", "core_engine", "input_handler", "data_store"]


def _majority_language(nodes: list) -> str:
    counts = {}
    for n in nodes:
        lang = (n.get("language") or "").strip().lower()
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "typescript"
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    return {"c#": "csharp"}.get(best, best)


def build_designs_blueprints() -> tuple:
    """Convert saved canvas designs into blueprints (real labels + wiring)."""
    data = json.loads(DESIGNS.read_text(encoding="utf-8"))
    blueprints = []
    warnings = []
    seen_goals = set()
    seen_slugs = set()

    for d in data:
        goal = (d.get("goal") or "").strip()
        name = (d.get("name") or "").strip() or goal[:50] or "untitled design"
        key = (goal or name).lower()
        if not key or key in seen_goals:
            continue
        seen_goals.add(key)

        nodes = d.get("nodes") or []
        if len(nodes) < 2:
            continue

        # Checklist = non-generic node labels (deduped, capped).
        labels = []
        for n in nodes:
            lab = (n.get("label") or "").strip()
            if not lab or lab.lower() in GENERIC_NODE_LABELS:
                continue
            if lab not in labels:
                labels.append(lab)
        labels = labels[:8]
        if len(labels) < 2:
            labels = list(DESIGN_FALLBACK_MODULES)

        # Wiring = edges resolved through node ids → labels.
        id2label = {}
        for n in nodes:
            if n.get("id"):
                id2label[str(n["id"])] = (n.get("label") or "").strip()
        wiring_pairs = []
        for e in d.get("edges") or []:
            s = id2label.get(str(e.get("source")))
            t = id2label.get(str(e.get("target")))
            if s and t and s != t and (s, t) not in wiring_pairs:
                wiring_pairs.append((s, t))
        wiring = [
            {"source_module": s, "destination_module": t, "data_passed": "state_and_events"}
            for s, t in wiring_pairs[:10]
        ] or default_wiring(labels)

        language = _majority_language(nodes)
        stack = LANG_STACKS.get(language, WEB_STACK)
        purpose = (d.get("purpose") or "").strip()
        description = goal + (f" — {purpose}" if purpose and purpose not in goal else "")

        tags = [t for t in (d.get("tags") or []) if isinstance(t, str)]
        keywords = (
            tags
            + re.findall(r"[a-z0-9']+", name.lower())
            + [lab.lower() for lab in labels]
        )

        base = slugify(name)
        slug = base
        n = 2
        while slug in seen_slugs:
            slug = f"{base}_{n}"
            n += 1
        seen_slugs.add(slug)

        blueprints.append({
            "app_type": slug,
            "description": description[:400],
            "keywords": keywords[:40],
            "target_stack": dict(stack),
            "architecture_checklist": labels,
            "wiring_graph": wiring,
            "source": "designs.json",
        })
    return blueprints, warnings


# ─── Source 4: projects/*.html (93 real single-file apps) ───────────────────
# Every complete app in the projects gallery becomes a routing entry: the
# title/description power semantic matching and a keyword table enriches the
# module checklist with the domain's engine (game, audio, image, ...).

HTML_TITLE_RE = re.compile(r"<title[^>]*>\s*([^<]+?)\s*</title>", re.I)
# Meta description with name= before content=, OR content= before name=.
HTML_DESC_NAME_FIRST = re.compile(r'<meta[^>]*\bname=["\']description["\'][^>]*\bcontent=["\']([^"\']+)["\']', re.I)
HTML_DESC_CONTENT_FIRST = re.compile(r'<meta[^>]*\bcontent=["\']([^"\']+)["\'][^>]*\bname=["\']description["\']', re.I)
HTML_TEXT_RE = re.compile(r"<(h1|h2|p)[^>]*>\s*([^<]{10,200}?)\s*</\1>", re.I)

# Keyword → extra module (title/filename driven). Base modules are always present.
DOMAIN_MODULES = [
    ("game", "game_engine"), ("chess", "game_engine"), ("puzzle", "game_engine"),
    ("arcade", "game_engine"), ("tictactoe", "game_engine"), ("connect", "game_engine"),
    ("maze", "game_engine"), ("sudoku", "game_engine"), ("geometry", "game_engine"),
    ("dungeon", "game_engine"), ("music", "audio_engine"), ("audio", "audio_engine"),
    ("player", "audio_engine"), ("photo", "image_engine"), ("image", "image_engine"),
    ("paint", "image_engine"), ("pixel", "image_engine"), ("sketch", "image_engine"),
    ("collage", "image_engine"), ("vector", "image_engine"), ("chat", "message_store"),
    ("message", "message_store"), ("editor", "editor_core"), ("regex", "editor_core"),
    ("terminal", "editor_core"), ("timer", "timer_core"), ("stopwatch", "timer_core"),
    ("countdown", "timer_core"), ("pomodoro", "timer_core"), ("finance", "ledger_store"),
    ("expense", "ledger_store"), ("budget", "ledger_store"), ("stock", "ledger_store"),
    ("portfolio", "ledger_store"), ("chart", "visualization_engine"),
    ("dashboard", "visualization_engine"), ("graph", "visualization_engine"),
    ("analytics", "visualization_engine"), ("pathfinder", "algorithm_core"),
    ("binary", "algorithm_core"), ("sorting", "algorithm_core"),
    ("spreadsheet", "data_store"), ("table", "data_store"), ("database", "data_store"),
    ("weather", "weather_service"), ("note", "task_store"), ("todo", "task_store"),
    ("kanban", "task_store"), ("habit", "task_store"), ("calendar", "task_store"),
    ("planner", "task_store"),
]

HTML_BASE_MODULES = ["ui_screens", "core_engine", "input_handler", "data_store"]


def build_html_projects_blueprints() -> list:
    """Convert every complete app in projects/*.html into a routing blueprint."""
    if not PROJECTS_DIR.is_dir():
        return []
    blueprints = []
    for f in sorted(PROJECTS_DIR.glob("*.html")):
        html = f.read_text(encoding="utf-8", errors="replace")
        m = HTML_TITLE_RE.search(html)
        title = (m.group(1).strip() if m else f.stem.replace("-", " ").replace("_", " ").title())
        desc = ""
        m = HTML_DESC_NAME_FIRST.search(html) or HTML_DESC_CONTENT_FIRST.search(html)
        if m:
            desc = m.group(1).strip()
        if not desc:
            m = HTML_TEXT_RE.search(html)
            if m:
                desc = m.group(2).strip()
        text = f"{title} {f.stem}".lower()
        modules = list(HTML_BASE_MODULES)
        for key, mod in DOMAIN_MODULES:
            if key in text and mod not in modules:
                modules.append(mod)
        description = (f"{title}. {desc}").strip()[:300] or f"A complete {title} application."
        keywords = re.findall(r"[a-z0-9']+", f"{title} {f.stem}".lower())
        blueprints.append({
            "app_type": slugify(f.stem),
            "description": description,
            "keywords": keywords,
            "target_stack": dict(WEB_STACK),
            "architecture_checklist": modules,
            "wiring_graph": default_wiring(modules),
            "source": f"projects-html:{f.name}",
        })
    return blueprints


# ─── Output ────────────────────────────────────────────────────────────────

# Curated hand-authored blueprints at backend/blueprints/ top level — generated
# app_types must not shadow them.
CURATED_APP_TYPES = {
    "todo_app", "chat_app", "ecommerce_store", "home_media_server",
    "analytics_dashboard", "url_shortener", "blog_cms", "generic_fullstack_app",
}

ALL_SOURCES = {"specs", "large", "designs", "html"}
SOURCE_LABELS = {
    "specs": "design-specs-v2.json",
    "large": "large-program-blueprints",
    "designs": "designs.json (real)",
    "html": "projects/*.html (real)",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print counts + samples, write nothing")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--sources", type=str, default="all",
                    help="comma-separated subset to convert: specs,large,designs,html (default: all)")
    args = ap.parse_args()

    if args.sources.strip().lower() == "all":
        selected = set(ALL_SOURCES)
    else:
        selected = {s.strip().lower() for s in args.sources.split(",") if s.strip()}
        unknown = selected - ALL_SOURCES
        if unknown:
            ap.error(f"unknown source(s): {', '.join(sorted(unknown))} (choose from: specs, large, designs, html)")

    warnings = []
    sources = []  # (label, blueprints, warnings)
    if "specs" in selected:
        specs, w = build_design_specs_blueprints()
        warnings.extend(w)
        sources.append((SOURCE_LABELS["specs"], specs))
    if "large" in selected:
        sources.append((SOURCE_LABELS["large"], build_large_program_blueprints()))
    if "designs" in selected:
        designs, w = build_designs_blueprints()
        warnings.extend(w)
        sources.append((SOURCE_LABELS["designs"], designs))
    if "html" in selected:
        sources.append((SOURCE_LABELS["html"], build_html_projects_blueprints()))

    all_bp = sorted(
        [b for _, bps in sources for b in bps],
        key=lambda b: b["app_type"],
    )
    # Curated bible entries always win: drop generated entries colliding with
    # them. Collisions AMONG generated sources get a _N suffix instead of being
    # dropped, so the huge corpus stays lossless.
    seen = set(CURATED_APP_TYPES)
    kept = []
    for b in all_bp:
        if b["app_type"] in CURATED_APP_TYPES:
            warnings.append(f"app_type collision: '{b['app_type']}' already in the curated bible — skipped ({b.get('source')})")
            continue
        base = b["app_type"]
        n = 2
        while b["app_type"] in seen:
            b["app_type"] = f"{base}_{n}"
            n += 1
        seen.add(b["app_type"])
        kept.append(b)
    all_bp = kept

    for label, bps in sources:
        print(f"{label:<25}: {len(bps)} blueprints")
    print(f"TOTAL                   : {len(all_bp)} blueprints")
    for w in warnings[:10]:
        print(f"WARN {w}")
    if len(warnings) > 10:
        print(f"... and {len(warnings) - 10} more warning(s)")

    if args.dry_run:
        for b in all_bp[:3]:
            print("  sample:", json.dumps(b, indent=2)[:600])
            print("  " + "-" * 60)
        return 0

    out = args.out
    if out.exists():
        # Idempotent regeneration: remove stale files from previous runs.
        for f in out.glob("*.json"):
            f.unlink()
    else:
        out.mkdir(parents=True)

    for b in all_bp:
        (out / f"{b['app_type']}.json").write_text(
            json.dumps(b, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(f"Wrote {len(all_bp)} blueprint(s) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
