#!/usr/bin/env python3
"""Build the cross-cutting COMPONENT MANIFEST from the library sheets.

A true component manifest: for every app type it lists the components
(nodes + concrete files) needed to build it, extracted deterministically
from the library sheets:

  data/library/02-app-type-templates.md      - per-app-type node graphs, file
                                               structures, languages, libraries
  data/library/01-node-architecture-reference.md - universal node types
  data/library/07-node-implementation-guide.md   - universal file skeleton

Outputs:
  data/library/43-component-manifest.md       - readable cross-cutting index
                                               (consultable by the LLM)
  data/component-manifest.json                - machine-readable for probes

Re-run after editing any library sheet:  python3 scripts/build-component-manifest.py
"""
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "data" / "library" / "02-app-type-templates.md"
NODE_REF = ROOT / "data" / "library" / "01-node-architecture-reference.md"
IMPL_GUIDE = ROOT / "data" / "library" / "07-node-implementation-guide.md"
OUT_MD = ROOT / "data" / "library" / "43-component-manifest.md"
OUT_JSON = ROOT / "data" / "component-manifest.json"

# ── Universal node types (canonical, from 01-node-architecture-reference.md) ──
NODE_TYPES = [
    {"type": "input", "purpose": "Handle user input, validate, sanitize",
     "variants": ["CLI Args", "HTTP Request", "File Input", "Form Input", "WebSocket", "Stdin"],
     "canonicalFiles": ["src/input/index.ts", "src/input/validation.ts"]},
    {"type": "logic", "purpose": "Business logic, processing, computation",
     "variants": ["Pure function", "Pipeline", "State machine"],
     "canonicalFiles": ["src/logic/index.ts"]},
    {"type": "database", "purpose": "Data persistence, storage, retrieval",
     "variants": ["SQLite (default)", "PostgreSQL", "JSON File", "In-Memory"],
     "canonicalFiles": ["src/db/schema.ts", "src/db/repository.ts", "data/app.db"]},
    {"type": "ui", "purpose": "User interface rendering",
     "variants": ["Web UI (React)", "Terminal UI (Bubble Tea)", "Desktop UI"],
     "canonicalFiles": ["src/ui/App.tsx", "src/ui/components/"]},
    {"type": "api", "purpose": "External service integration",
     "variants": ["REST", "WebSocket", "System command"],
     "canonicalFiles": ["src/api/client.ts"]},
]

# Universal project skeleton (from 07-node-implementation-guide.md §5)
UNIVERSAL_SKELETON = [
    "src/index.ts", "src/types.ts", "src/config.ts",
    "src/input/", "src/logic/", "src/db/schema.ts", "src/db/repository.ts",
    "src/ui/App.tsx", "src/ui/components/",
    "data/app.db", "package.json", "tsconfig.json", "README.md",
]

# Box labels that are VARIANTS of the box above (never standalone nodes).
VARIANT_ALIASES = {"Router"}  # API box: '│ API │' / '│ Router │'

# Node-graph box label -> node type (from the ASCII diagrams in the templates)
NODE_TYPE_MAP = {
    "Input": "input", "Collector": "input",
    "Logic": "logic", "Scanner": "logic", "Checks": "logic", "Auth": "logic",
    "Database": "database", "Library": "database", "Files": "database",
    "Output": "ui", "UI": "ui", "Web UI": "ui", "TUI": "ui", "Report": "ui",
    "Router": "api", "API": "api", "Stream Server": "api", "Stream": "api",
    # New app-type template labels (02-app-type-templates.md §7-13)
    "Chat": "logic", "Cart": "logic", "Widgets": "ui",
    "Sessions": "database", "Realtime": "api", "Payments": "api", "Data API": "api",
    "Watcher": "input", "Sync": "logic", "Index": "database", "Remote": "api",
    "Booking": "logic", "Content": "logic", "Publish": "api",
}


def strip_comment(name: str) -> str:
    """Strip trailing '# ...' comments from file-tree lines."""
    for sep in ("#", "//"):
        if sep in name:
            name = name.split(sep)[0]
    return name.strip().strip("`").strip()


def parse_node_graph(fence: str):
    """Extract node labels from an ASCII box diagram (│ Text │ segments)."""
    labels: list[str] = []
    for line in fence.splitlines():
        for m in re.finditer(r"\u2502([^\u2502]*)\u2502", line):
            text = m.group(1).strip()
            if not text or text == "..." or text == "-----":
                continue
            name = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()  # drop (variant)
            if not name or name.startswith("("):
                continue
            # A box's second line can carry a non-parenthetical variant label
            # (e.g. the API box shows 'API' then 'Router' on the next line) —
            # those are variants of the box above, not separate nodes.
            if name in VARIANT_ALIASES:
                continue
            if name not in labels:
                labels.append(name)
    nodes = []
    for name in labels:
        ntype = NODE_TYPE_MAP.get(name, "custom")
        nodes.append({"name": name, "type": ntype})
    return nodes


def parse_file_tree(fence: str):
    """Parse a 'Generated File Structure' tree into concrete file paths."""
    paths: list[str] = []
    stack: list[str] = []
    for line in fence.splitlines():
        if "\u2500\u2500" not in line:
            continue
        idx = line.find("\u251c\u2500\u2500")
        if idx == -1:
            idx = line.find("\u2514\u2500\u2500")
        if idx == -1:
            continue
        depth = idx // 4
        name = strip_comment(line[idx + 3:])
        if not name:
            continue
        # 'X or Y' alternatives (e.g. 'main.go / main.ts', 'pkg/ or src/') are
        # SIBLINGS — each starts from the SAME parent (reviewer fix: the first
        # pass nested 'src/' under 'pkg/' -> 'pkg/src/'). Children of this line
        # attach under the LAST directory sibling, which is how the tree
        # continuation reads.
        names = [n.strip() for n in re.split(r"\s+or\s+|\s+/\s+", name) if n.strip()]
        parent = stack[:depth]
        last_dir = None
        for n in names:
            is_dir = n.endswith("/")
            n = n.rstrip("/")
            full = "/".join(parent + [n]) if parent else n
            if is_dir:
                last_dir = full
                if full + "/" not in paths:
                    paths.append(full + "/")
            else:
                if full not in paths:
                    paths.append(full)
        if last_dir:
            stack = parent + [last_dir.split("/")[-1]]
    return paths


def parse_templates(text: str):
    """Parse 02-app-type-templates.md into per-app-type component records."""
    app_types = []
    quick_ref = {}   # appType -> (nodeCount, languages, database, interface)
    selection = {}   # keyword -> template
    hybrids = []

    # Quick Reference table
    for m in re.finditer(r"\|\s*\*\*([^*]+)\*\*\s*\|\s*([\d\-]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\s*\|", text):
        quick_ref[m.group(1).strip()] = [g.strip() for g in m.groups()[1:]]

    # Selection guide + hybrids
    def norm_template(s: str) -> list[str]:
        """Normalize a 'Use Template' value to candidate type names, e.g.
        'System Tool' -> ['System Tool'], 'Game Template' -> ['Game'],
        'Data Processor / CLI Tool' -> ['Data Processor', 'CLI Tool']."""
        cleaned = s.replace(" Template", "").strip()
        return [p.strip() for p in re.split(r"\s*/\s*", cleaned) if p.strip()]

    # Tolerate both '## Template Selection Guide' and a numbered variant
    # ('## 11. Template Selection Guide') — a plain split() would silently
    # return the whole document if the heading is ever renumbered.
    sel_block = re.split(r"^##\s*\d*\.?\s*Template Selection Guide", text, flags=re.M)[-1]
    for m in re.finditer(r"\|\s*\"([^\"]+)\"\s*\|\s*([^|]+)\s*\|", sel_block):
        selection[m.group(1).strip()] = m.group(2).strip()
    for m in re.finditer(r"^([A-Za-z+ -]+) = ([A-Za-z+ -]+)$", sel_block, re.M):
        hybrids.append("%s = %s" % (m.group(1).strip(), m.group(2).strip()))

    # Per-template sections: ## N. <Name> Template (title may carry a
    # parenthetical, e.g. 'Desktop App Template (Web-based UI)').
    sections = re.split(r"^## \d+\. (.+)$", text, flags=re.M)
    # sections[0] is the prelude; then pairs of (title, body)
    for i in range(1, len(sections), 2):
        title = re.sub(r"\s*\(.*\)$", "", sections[i].strip())
        title = title.replace(" Template", "").strip()
        if title not in quick_ref:
            continue  # 'Template Selection Guide' etc.
        body = sections[i + 1]
        rec = {"appType": title, "nodes": [], "files": [], "languages": [],
               "libraries": [], "database": "", "interface": "", "bestFor": ""}
        bf = re.search(r"Best for:\s*([^\n]+)", body)
        if bf:
            rec["bestFor"] = bf.group(1).strip()
        # Languages section — capture the VALUE after the bold label
        # (e.g. "**Primary:** Go ..." -> "Go"), filtered to a known
        # vocabulary so prose words ("For", "single binary") never leak in.
        KNOWN_LANGS = {"Go", "TypeScript", "Python", "React", "Node.js", "Electron",
                       "Vite", "Capacitor", "Express", "FastAPI", "SQLite",
                       "PostgreSQL", "Rust", "C", "C++", "Java", "Kotlin", "Swift",
                       "Bash", "SQL", "JavaScript"}
        lang_sec = body.split("### Recommended Languages")[-1].split("###")[0]
        # '**Label:** value' — the label class must exclude ':' or it greedily
        # eats the colon inside the bold (\*\*Primary:\*\*) and the pattern
        # can never align (this silently fell back to the quick-ref language
        # cell for every template before CHANGE 49 fixed it).
        for m in re.finditer(r"-\s*\*\*[^*:]+:\*\*\s*([^\n(]+)", lang_sec):
            for tok in re.split(r"[,+/]|\s+or\s+", m.group(1).strip()):
                tok = tok.strip().rstrip(".")
                if tok in KNOWN_LANGS and tok not in rec["languages"]:
                    rec["languages"].append(tok)
        # Libraries section
        lib_sec = body.split("### Key Libraries")[-1].split("###")[0]
        for m in re.finditer(r"`([^`]+)`", lib_sec):
            lib = m.group(1).strip()
            if lib not in rec["libraries"]:
                rec["libraries"].append(lib)
        # First code fence = node diagram; second = file structure
        fences = re.findall(r"```\n(.*?)```", body, re.S)
        if fences:
            rec["nodes"] = parse_node_graph(fences[0])
            if len(fences) > 1:
                rec["files"] = parse_file_tree(fences[1])
        qr = quick_ref.get(title)
        if qr:
            rec["nodeCount"] = qr[0]
            rec["languages"] = rec["languages"] or [qr[1]]
            rec["database"] = qr[2]
            rec["interface"] = qr[3]
        rec["selectionKeywords"] = [k for k, v in selection.items() if title in norm_template(v)]
        app_types.append(rec)

    # Quick-ref-only types (no full template section): Data Processor, Game
    for extra, node_count in (("Data Processor", "3-4"), ("Game", "5-8")):
        if not any(a["appType"] == extra for a in app_types):
            qr = quick_ref.get(extra)
            app_types.append({
                "appType": extra, "nodes": [], "files": [],
                "languages": [p.strip() for p in qr[1].split("/")] if qr else [],
                "libraries": [], "database": qr[2] if qr else "",
                "interface": qr[3] if qr else "",
                "bestFor": "Quick-reference only (no full template section in "
                           "02-app-type-templates.md — consult the matching "
                           "bible-reference/ level for component details)",
                "nodeCount": node_count,
                "selectionKeywords": [k for k, v in selection.items() if extra in norm_template(v)],
            })
    return app_types, quick_ref, selection, hybrids


def build_manifest():
    templates_text = TEMPLATES.read_text()
    app_types, quick_ref, selection, hybrids = parse_templates(templates_text)

    manifest = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceSheets": ["02-app-type-templates.md", "01-node-architecture-reference.md",
                         "07-node-implementation-guide.md"],
        "nodeTypes": NODE_TYPES,
        "universalSkeleton": UNIVERSAL_SKELETON,
        "appTypes": app_types,
        "selectionGuide": selection,
        "hybrids": hybrids,
    }
    OUT_JSON.write_text(json.dumps(manifest, indent=1), "utf-8")

    # ── Readable markdown ──
    md = []
    md.append("# \U0001f4cb Component Manifest \u2014 cross-cutting index")
    md.append("")
    md.append("> Every component (nodes + files) needed per app type. Generated by")
    md.append("> `scripts/build-component-manifest.py` from the library sheets:")
    md.append("> `02-app-type-templates.md` + `01-node-architecture-reference.md` +")
    md.append("> `07-node-implementation-guide.md`. Regenerate after editing any sheet.")
    md.append("")
    md.append("## 1. Universal Node Types (every program is built from these)")
    md.append("")
    md.append("| Node | Purpose | Variants | Canonical files |")
    md.append("|---|---|---|---|")
    for nt in NODE_TYPES:
        md.append("| `%s` | %s | %s | `%s` |" % (
            nt["type"], nt["purpose"], ", ".join(nt["variants"]),
            "`, `".join(nt["canonicalFiles"])))
    md.append("")
    md.append("## 2. Universal Project Skeleton (files every generated project needs)")
    md.append("")
    md.append("```")
    for p in UNIVERSAL_SKELETON:
        md.append(p)
    md.append("```")
    md.append("")
    md.append("## 3. Per-App-Type Component Matrix")
    md.append("")
    md.append("| App type | Nodes | Files | Languages | Database | Interface |")
    md.append("|---|---|---|---|---|---|")
    for a in app_types:
        md.append("| **%s** | %d | %d | %s | %s | %s |" % (
            a["appType"], len(a["nodes"]), len(a["files"]),
            ", ".join(a["languages"][:2]) or "-", a["database"] or "-", a["interface"] or "-"))
    md.append("")
    md.append("## 4. Per-App-Type Component Lists (nodes + files)")
    md.append("")
    for a in app_types:
        md.append("### %s" % a["appType"])
        if a.get("bestFor"):
            md.append("Best for: %s" % a["bestFor"])
        if a.get("nodeCount"):
            md.append("Node count: %s" % a["nodeCount"])
        md.append("")
        md.append("**Nodes:**")
        if a["nodes"]:
            for n in a["nodes"]:
                md.append("- `%s` (%s)" % (n["name"], n["type"]))
        else:
            md.append("- (no template node graph \u2014 see bible-reference/ level for this app type)")
        md.append("")
        md.append("**Files:**")
        if a["files"]:
            md.append("```")
            for f in a["files"]:
                md.append(f)
            md.append("```")
        else:
            md.append("- (no template file structure \u2014 use the universal skeleton above)")
        md.append("")
        md.append("**Languages:** %s" % (", ".join(a["languages"]) or "-"))
        md.append("**Database:** %s | **Interface:** %s" % (a["database"] or "-", a["interface"] or "-"))
        if a["libraries"]:
            md.append("**Key libraries:** %s" % ", ".join(a["libraries"]))
        if a["selectionKeywords"]:
            md.append("**Selection keywords:** %s" % ", ".join('"%s"' % k for k in a["selectionKeywords"]))
        md.append("")
    md.append("## 5. Template Selection Guide")
    md.append("")
    md.append("| User says | Use template |")
    md.append("|---|---|")
    for k, v in selection.items():
        md.append("| \"%s\" | %s |" % (k, v))
    md.append("")
    md.append("## 6. Hybrid Templates")
    md.append("")
    for h in hybrids:
        md.append("- %s" % h)
    md.append("")
    md.append("*For deep technical implementation details per app type, consult the "
              "matching bible-reference/ level via MASTER-INDEX.txt*")
    OUT_MD.write_text("\n".join(md) + "\n", "utf-8")

    # ── Summary ──
    print("wrote:", OUT_JSON.relative_to(ROOT), "(%d app types)" % len(app_types))
    print("wrote:", OUT_MD.relative_to(ROOT), "(%d lines)" % (len(md) + 1))
    for a in app_types:
        print("  %-16s nodes=%d files=%d langs=%s" % (
            a["appType"], len(a["nodes"]), len(a["files"]),
            ", ".join(a["languages"][:2]) or "-"))
    return manifest


if __name__ == "__main__":
    build_manifest()
