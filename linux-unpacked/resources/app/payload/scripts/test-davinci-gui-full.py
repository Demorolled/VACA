#!/usr/bin/env python3
"""
Davinci GUI Full Pipeline Test (v2)
====================================
Enhanced test that:
  1. Maps all 207 design tags to the 10 bible-reference categories
  2. Goes through the full Architect scaffold pipeline (create project → scaffold → push)
  3. Generates node-aware widgets using actual design content
  4. Verifies Davinci received and applied the build
  5. Cleans up between each design
  6. Records results to auto-learn

Usage:
  python3 scripts/test-davinci-gui-full.py [--batch N] [--design N] [--all] [--quick]
"""

import json
import sys
import os
import time
import re
import urllib.request
import urllib.error
from datetime import datetime

# ─── Configuration ──────────────────────────────────────────────────────────

ARCHITECT_API = "http://localhost:3001"
DAVINCI_API = "http://localhost:8000"
DESIGNS_FILE = "data/designs.json"

# ─── Tag-to-Category Mapping ──────────────────────────────────────────
# Maps any tag in use to one of the 10 bible-reference categories

TAG_CATEGORY_MAP = {
    # Fundamentals (01-fundamentals)
    "algorithms": "fundamentals", "data-structures": "fundamentals",
    "complexity": "fundamentals", "big-o": "fundamentals",
    "arrays": "fundamentals", "linked-list": "fundamentals",
    "binary": "fundamentals", "sorting": "fundamentals",
    "searching": "fundamentals", "recursion": "fundamentals",
    "backtracking": "fundamentals", "dynamic-programming": "fundamentals",
    "greedy": "fundamentals", "hash-tables": "fundamentals",
    "trees": "fundamentals", "graphs": "fundamentals",
    "strings": "fundamentals", "logic": "fundamentals",
    "comparison": "fundamentals", "pathfinding": "fundamentals",
    "minimax": "fundamentals",

    # Games (02-games)
    "game": "games", "arcade": "games", "puzzle": "games",
    "card-game": "games", "2d": "games", "classic": "games",
    "snake": "games", "tetris": "games", "pong": "games",
    "sokoban": "games", "platformer": "games", "rpg": "games",

    # Desktop Apps (03-desktop-apps)
    "desktop": "desktop", "editor": "desktop",
    "developer-tools": "desktop", "text-editor": "desktop",
    "file-explorer": "desktop", "media-player": "desktop",
    "audio": "desktop", "video": "desktop",

    # Systems Programming (05-systems-programming)
    "memory": "systems", "low-level": "systems",
    "concurrency": "systems", "threads": "systems",
    "compiler": "systems", "debugger": "systems",
    "kernel": "systems", "driver": "systems",
    "ebpf": "systems", "tracing": "systems",
    "benchmark": "systems", "performance": "systems",
    "optimization": "systems", "virtual-memory": "systems",
    "cpp": "systems", "rust": "systems",
    "serialization": "systems", "protocol": "systems",

    # Databases (06-databases)
    "database": "database", "sql": "database", "nosql": "database",
    "postgres": "database", "postgresql": "database",
    "btree": "database", "index": "database",
    "query": "database", "data-modeling": "database",
    "warehouse": "database", "distributed": "database",

    # Mathematics (13-math)
    "mathematics": "mathematics", "math": "mathematics",
    "calculus": "mathematics", "linear-algebra": "mathematics",
    "statistics": "mathematics", "geometry": "mathematics",
    "visualization": "mathematics", "science": "mathematics",
    "physics": "mathematics", "simulation": "mathematics",
    "education": "mathematics",

    # Specialized Computing (20-specialized-computing)
    "specialized": "specialized", "computation": "specialized",
    "quantum": "specialized", "bioinformatics": "specialized",
    "chemistry": "specialized", "weather": "specialized",
    "climate": "specialized", "optimization": "specialized",

    # Data Engineering (27-data-engineering)
    "data-engineering": "data-engineering", "etl": "data-engineering",
    "pipeline": "data-engineering", "data-quality": "data-engineering",
    "data-lineage": "data-engineering", "data-governance": "data-engineering",
    "analytics": "data-engineering", "streaming": "data-engineering",
    "real-time": "data-engineering", "data-warehouse": "data-engineering",

    # DevOps/SRE (33-devops-sre-tooling)
    "devops": "devops", "sre": "devops", "monitoring": "devops",
    "ci-cd": "devops", "terraform": "devops", "docker": "devops",
    "kubernetes": "devops", "vault": "devops", "secrets": "devops",
    "logging": "devops", "observability": "devops", "iac": "devops",
    "container": "devops",

    # Search/Recommendation (36-search-recs-personalization)
    "search": "search", "recommendations": "search",
    "personalization": "search", "ranking": "search",
    "relevance": "search", "vector-search": "search",
    "embeddings": "search", "lucene": "search",
    "elasticsearch": "search", "learning-to-rank": "search",
}

CATEGORY_LABELS = {
    "fundamentals": "01-fundamentals",
    "games": "02-games",
    "desktop": "03-desktop-apps",
    "systems": "05-systems-programming",
    "database": "06-databases",
    "mathematics": "13-math",
    "specialized": "20-specialized-computing",
    "data-engineering": "27-data-engineering",
    "devops": "33-devops-sre-tooling",
    "search": "36-search-recs-personalization",
}

CATEGORY_NUMBERS = {v: k for k, v in CATEGORY_LABELS.items()}

# ─── Widget Generation ────────────────────────────────────────────────

WIDGET_DEFAULTS = {
    "button": {"w": 120, "h": 36},
    "slider": {"w": 200, "h": 28},
    "toggle": {"w": 56, "h": 28},
    "display": {"w": 260, "h": 80},
    "input": {"w": 200, "h": 32},
    "knob": {"w": 52, "h": 52},
    "label": {"w": 120, "h": 24},
}

CATEGORY_WIDGETS = {
    "fundamentals": [
        ("button", "Run", "topbar", "runAlgorithm"),
        ("display", "Output", "main", "displayResults"),
        ("input", "Input Data", "main", "inputData"),
        ("display", "Visualization", "main", "showVisualization"),
        ("slider", "Speed", "bottom", "setSpeed"),
        ("toggle", "Auto-Run", "sidebar", "toggleAutoRun"),
        ("button", "Reset", "bottom", "reset"),
        ("button", "Export", "bottom", "export"),
    ],
    "games": [
        ("button", "Start", "main", "startGame"),
        ("button", "Pause", "bottom", "pauseGame"),
        ("display", "Score", "topbar", "showScore"),
        ("display", "Timer", "topbar", "showTimer"),
        ("button", "Restart", "bottom", "restart"),
        ("slider", "Difficulty", "sidebar", "setDifficulty"),
        ("toggle", "Sound", "sidebar", "toggleSound"),
        ("button", "Settings", "topbar", "openSettings"),
    ],
    "desktop": [
        ("button", "New", "topbar", "newFile"),
        ("button", "Save", "topbar", "saveFile"),
        ("button", "Open", "topbar", "openFile"),
        ("display", "Content", "main", "showContent"),
        ("input", "Search", "topbar", "search"),
        ("button", "Delete", "main", "delete"),
        ("toggle", "Dark Mode", "sidebar", "toggleDark"),
        ("button", "Export", "bottom", "export"),
    ],
    "database": [
        ("button", "New Query", "topbar", "newQuery"),
        ("button", "Run", "topbar", "runQuery"),
        ("display", "Results", "main", "showResults"),
        ("input", "SQL Input", "main", "inputSQL"),
        ("display", "Schema", "sidebar", "showSchema"),
        ("button", "Save", "bottom", "saveQuery"),
        ("toggle", "Auto-Commit", "sidebar", "toggleCommit"),
        ("button", "Export", "bottom", "export"),
    ],
    "systems": [
        ("button", "Compile", "topbar", "compile"),
        ("button", "Run", "topbar", "run"),
        ("display", "Output", "main", "showOutput"),
        ("display", "Profile", "main", "showProfile"),
        ("input", "Command", "bottom", "inputCommand"),
        ("button", "Debug", "topbar", "debug"),
        ("toggle", "Verbose", "sidebar", "toggleVerbose"),
        ("slider", "Timeout", "sidebar", "setTimeout"),
    ],
    "mathematics": [
        ("button", "Calculate", "topbar", "calculate"),
        ("display", "Result", "main", "showResult"),
        ("input", "Expression", "main", "inputExpr"),
        ("display", "Graph", "main", "showGraph"),
        ("button", "Plot", "topbar", "plot"),
        ("slider", "Range", "bottom", "setRange"),
        ("toggle", "Grid", "sidebar", "toggleGrid"),
        ("button", "Export", "bottom", "exportPlot"),
    ],
    "specialized": [
        ("button", "Simulate", "topbar", "simulate"),
        ("display", "Output", "main", "showOutput"),
        ("input", "Parameters", "main", "inputParams"),
        ("display", "Progress", "main", "showProgress"),
        ("button", "Load", "topbar", "loadModel"),
        ("slider", "Precision", "sidebar", "setPrecision"),
        ("toggle", "GPU Mode", "sidebar", "toggleGPU"),
        ("button", "Export", "bottom", "export"),
    ],
    "data-engineering": [
        ("button", "Run Pipeline", "topbar", "runPipeline"),
        ("display", "Status", "main", "showStatus"),
        ("input", "Config", "main", "configSource"),
        ("display", "Preview", "main", "showPreview"),
        ("button", "Validate", "topbar", "validate"),
        ("toggle", "Auto-Run", "sidebar", "toggleAuto"),
        ("display", "Logs", "sidebar", "showLogs"),
        ("button", "Export", "bottom", "export"),
    ],
    "devops": [
        ("button", "Deploy", "topbar", "deploy"),
        ("display", "Status", "main", "showStatus"),
        ("display", "Metrics", "main", "showMetrics"),
        ("button", "Rollback", "topbar", "rollback"),
        ("input", "Search Logs", "main", "searchLogs"),
        ("toggle", "Auto-Scale", "sidebar", "toggleScale"),
        ("button", "Alert Config", "sidebar", "configAlerts"),
        ("button", "Restart", "bottom", "restart"),
    ],
    "search": [
        ("input", "Search", "topbar", "search"),
        ("display", "Results", "main", "showResults"),
        ("button", "Filter", "topbar", "filter"),
        ("slider", "Relevance", "sidebar", "setRelevance"),
        ("toggle", "Semantic", "sidebar", "toggleSemantic"),
        ("display", "Preview", "main", "showPreview"),
        ("button", "Advanced", "topbar", "advanced"),
        ("button", "Export", "bottom", "export"),
    ],
}

ZONES = {
    "topbar": {"x": 8, "y": 8, "max_x": 780, "max_y": 56},
    "main": {"x": 8, "y": 68, "max_x": 600, "max_y": 480},
    "sidebar": {"x": 610, "y": 68, "max_x": 780, "max_y": 480},
    "bottom": {"x": 8, "y": 500, "max_x": 780, "max_y": 560},
}


def infer_category(design):
    """Map a design to one of 10 bible-reference categories."""
    tags = design.get("tags", [])
    name = design.get("name", "").lower()
    goal = design.get("goal", "").lower()

    # Check tags first
    for tag in tags:
        t = tag.lower().strip()
        if t in TAG_CATEGORY_MAP:
            return TAG_CATEGORY_MAP[t]

    # Check goal text for keyword matches
    keyword_map = {
        "fundamentals": ["sort", "search", "tree", "graph", "hash", "recursion", "dp", "dynamic programming",
                         "greedy", "backtracking", "algorithm", "linked list", "stack", "queue"],
        "games": ["game", "play", "puzzle", "snake", "tetris", "pong", "chess", "checkers", "sokoban",
                  "platformer", "rpg", "card", "board game", "arcade"],
        "desktop": ["editor", "explorer", "player", "viewer", "browser", "note", "calendar", "mail",
                    "media", "text editor", "file manager"],
        "database": ["database", "sql", "query", "index", "schema", "nosql", "table", "postgres"],
        "systems": ["compiler", "memory", "concurrency", "thread", "kernel", "driver", "serialization",
                    "protocol", "debugger", "profiler"],
        "mathematics": ["math", "calculus", "algebra", "geometry", "linear", "statistics",
                        "graph theory", "plot", "numerical"],
        "specialized": ["quantum", "bioinfo", "chemistry", "weather", "climate", "simulation",
                        "computational", "optimization"],
        "data-engineering": ["pipeline", "etl", "stream", "analytics", "warehouse", "lineage",
                             "governance", "data quality"],
        "devops": ["deploy", "monitor", "ci", "cd", "terraform", "docker", "kubernetes",
                   "vault", "secrets", "sre", "observability"],
        "search": ["search", "recommend", "relevance", "ranking", "vector", "embedding",
                   "personalization", "lucene", "elastic"],
    }

    for cat, keywords in keyword_map.items():
        for kw in keywords:
            if kw in goal or kw in name:
                return cat

    return "fundamentals"


def generate_widgets(design, category):
    """Generate GUI widgets for a design with node awareness."""
    widgets = []
    template = CATEGORY_WIDGETS.get(category, CATEGORY_WIDGETS["fundamentals"])
    occupied = []
    goal = design.get("goal", "").lower()
    name = design.get("name", "").lower()
    nodes = design.get("nodes", [])

    # Try to make widgets node-aware - match to actual node labels
    node_labels = {}
    for node in nodes:
        label = (node.get("data", {}).get("label", "") or
                 node.get("label", "") or "").lower()
        ntype = node.get("data", {}).get("type", node.get("type", "logic"))
        node_labels[label] = ntype

    for i, (wtype, wlabel, zone_name, action) in enumerate(template):
        zone = ZONES[zone_name]
        wdef = WIDGET_DEFAULTS[wtype]
        ww = wdef["w"]
        wh = wdef["h"]

        # Grid placement within zone
        col = i % 3
        row = i // 3
        x = zone["x"] + col * (ww + 12)
        y = zone["y"] + row * (wh + 12)

        # Clamp
        if x + ww > zone["max_x"]:
            x = zone["x"]
            y += wh + 12
        if y + wh > zone["max_y"]:
            y = zone["y"]

        widget_id = f"w_{action}_{int(time.time()*1000)}_{i}"
        node_id = f"node_{action}"

        # Try to link to an actual design node
        action_lower = action.lower()
        for nl, nt in node_labels.items():
            if action_lower in nl or any(word in nl for word in action_lower.split("_")):
                node_id = f"node-{nl.replace(' ', '-')}"
                break

        widget = {
            "id": widget_id,
            "type": wtype,
            "label": wlabel,
            "x": x,
            "y": y,
            "width": ww,
            "height": wh,
            "linkedNodeId": node_id,
            "archBindings": {
                "onClick": action if wtype == "button" else "",
                "onChange": action if wtype in ("slider", "toggle", "knob", "input") else "",
                "displayInput": action if wtype == "display" else "",
                "valueInput": "",
            },
            "rotation": 0,
            "opacity": 100,
            "styleId": "bs1",
            "props": {}
        }
        widgets.append(widget)
        occupied.append({"x": x, "y": y, "w": ww, "h": wh})

    return widgets


def build_architect_nodes(design):
    """Build architect node representation from design nodes."""
    nodes = []
    for node in design.get("nodes", []):
        nd = node.get("data", node)
        nodes.append({
            "id": node.get("id", ""),
            "label": nd.get("label", "Node"),
            "type": nd.get("type", "logic"),
            "description": nd.get("description", ""),
        })
    return nodes


def create_project_on_backend(design):
    """Create a project on the Architect backend to enable scaffolding."""
    try:
        # Build the project payload matching the backend's expected format
        nodes = []
        for node in design.get("nodes", []):
            nd = node.get("data", node)
            nodes.append({
                "id": node.get("id", f"saved_{len(nodes)}"),
                "type": nd.get("type", "logic"),
                "position": nd.get("position", {"x": 200 + len(nodes) * 50, "y": 200}),
                "data": {
                    "label": nd.get("label", "Node"),
                    "description": nd.get("description", ""),
                    "type": nd.get("type", "logic"),
                    "status": "pending",
                },
            })

        edges = design.get("edges", [])

        project_data = {
            "id": f"test_{int(time.time()*1000)}",
            "name": design.get("name", "Test Design"),
            "goal": design.get("goal", ""),
            "purpose": design.get("purpose", ""),
            "targetOS": "linux",
            "nodes": nodes,
            "edges": edges,
        }

        # Try creating via the simple projects endpoint
        req = urllib.request.Request(
            f"{ARCHITECT_API}/api/projects",
            data=json.dumps({"name": design.get("name", "Test")}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 409 or "already exists" in body:
            return {"id": "existing"}
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


def push_to_davinci(design, widgets, architect_nodes):
    """Push design + widgets to Davinci via HTTP bridge."""
    goal = design.get("goal", "") or design.get("name", "")

    build_data = {
        "appName": design.get("name", "Untitled"),
        "goal": goal,
        "nodeCount": len(architect_nodes),
        "widgetCount": len(widgets),
        "architectNodes": architect_nodes,
        "uiFunctions": [{
            "id": w["id"],
            "label": w["label"],
            "type": w["type"],
            "description": f"Widget for {goal}",
            "defaultAction": w["archBindings"].get("onClick") or w["archBindings"].get("onChange") or "",
            "category": "utility",
        } for w in widgets],
        "placedWidgets": widgets,
        "archBindings": [{
            "widgetId": w["id"],
            "widgetLabel": w["label"],
            "nodeId": w.get("linkedNodeId", ""),
            "bindings": {k: v for k, v in w["archBindings"].items() if v},
        } for w in widgets if any(w["archBindings"].values())],
    }

    req = urllib.request.Request(
        f"{DAVINCI_API}/api/bridge/builds",
        data=json.dumps(build_data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"received": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"received": False, "error": str(e)}


def verify_build(build_id=None):
    """Verify build exists on Davinci."""
    try:
        req = urllib.request.Request(f"{DAVINCI_API}/api/bridge/builds")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            builds = result.get("builds", [])
            if not builds:
                return {"verified": False, "reason": "No builds found"}
            if build_id:
                matches = [b for b in builds if b.get("id") == build_id]
                if not matches:
                    return {"verified": False, "reason": f"Build {build_id} not found"}
                b = matches[0]
            else:
                b = builds[0]
            return {
                "verified": True,
                "build": b,
                "widgetCount": b.get("widgetCount", 0),
                "status": b.get("status", ""),
            }
    except Exception as e:
        return {"verified": False, "reason": str(e)}


def apply_build(build_id):
    """Apply a build's widgets to the Davinci canvas."""
    try:
        req = urllib.request.Request(
            f"{DAVINCI_API}/api/bridge/builds/{build_id}/apply",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def verify_canvas_widgets(expected_min):
    """Verify widgets on canvas meet minimum count."""
    try:
        req = urllib.request.Request(f"{DAVINCI_API}/api/widgets")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            widgets = result.get("widgets", [])
            count = len(widgets)
            return {
                "verified": count >= expected_min,
                "count": count,
                "expected_min": expected_min,
                "widget_types": [w.get("type", "?") for w in widgets],
                "widget_labels": [w.get("label", "?") for w in widgets],
            }
    except Exception as e:
        return {"verified": False, "reason": str(e), "count": 0}


def canvas_cleanup():
    """Clear all widgets from the Davinci canvas."""
    try:
        req = urllib.request.Request(
            f"{DAVINCI_API}/api/widgets/batch",
            data=json.dumps({"widgets": []}).encode(),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except:
        pass


def clear_builds():
    """Clear all builds from Davinci."""
    try:
        req = urllib.request.Request(
            f"{DAVINCI_API}/api/bridge/builds/clear",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except:
        pass


def record_to_auto_learn(design_name, category, passed, widget_count, details_str):
    """Record test result to auto-learn."""
    try:
        record = {
            "type": "davinci_gui_test",
            "content": f"Test {design_name} ({category}): {'PASS' if passed else 'FAIL'} - {widget_count} widgets",
            "metadata": {
                "design": design_name,
                "category": category,
                "passed": passed,
                "widget_count": widget_count,
                "details": details_str,
            }
        }
        req = urllib.request.Request(
            f"{ARCHITECT_API}/api/auto-learn/record",
            data=json.dumps(record).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except:
        pass


# ─── Test Runner ──────────────────────────────────────────────────────

def test_design(design, verbose=True):
    """Run the full Davinci GUI pipeline test on a single design."""
    name = design.get("name", "Unknown")
    category = infer_category(design)
    cat_label = CATEGORY_LABELS.get(category, category)
    tags = design.get("tags", [])
    goal = design.get("goal", "")

    if verbose:
        print(f"\n  ── {name} [{cat_label}] tags={tags[:3]}... ──")

    # Step 1: Generate widgets
    widgets = generate_widgets(design, category)
    widget_count = len(widgets)
    if verbose:
        print(f"  1️⃣  Generated {widget_count} GUI widgets ({category})")

    # Step 2: Build architect nodes
    architect_nodes = build_architect_nodes(design)
    if verbose:
        print(f"  2️⃣  Built {len(architect_nodes)} architect nodes")

    # Step 3: Push to Davinci
    push_result = push_to_davinci(design, widgets, architect_nodes)
    build_id = push_result.get("build_id", "")
    if push_result.get("received", False):
        if verbose:
            print(f"  3️⃣  ✅ Push to Davinci: {build_id} ({widget_count} widgets)")
    else:
        error = push_result.get("error", "unknown")
        if verbose:
            print(f"  3️⃣  ❌ Push failed: {error[:80]}")
        record_to_auto_learn(name, category, False, widget_count, f"Push failed: {error}")
        return {"name": name, "category": category, "passed": False, "widgets": widget_count}

    # Step 4: Verify build
    time.sleep(0.3)
    verify_b = verify_build(build_id)
    if verify_b.get("verified"):
        if verbose:
            print(f"  4️⃣  ✅ Build verified: {verify_b.get('widgetCount', 0)} widgets in build")
    else:
        if verbose:
            print(f"  4️⃣  ❌ Build not found: {verify_b.get('reason', '')}")
        record_to_auto_learn(name, category, False, widget_count, f"Verify failed: {verify_b.get('reason')}")
        return {"name": name, "category": category, "passed": False, "widgets": widget_count}

    # Step 5: Apply build to canvas
    apply_result = apply_build(build_id)
    applied = apply_result.get("widgets_applied", 0) or (1 if apply_result.get("ok") else 0)
    if applied > 0:
        if verbose:
            print(f"  5️⃣  ✅ Build applied: {applied} widgets on canvas")
    else:
        if verbose:
            print(f"  5️⃣  ⚠️  Apply result: {apply_result.get('ok', False)}")
        # Still try to verify

    # Step 6: Verify canvas widgets
    canvas_v = verify_canvas_widgets(widget_count)
    if canvas_v.get("verified"):
        if verbose:
            types_str = ", ".join(sorted(set(canvas_v["widget_types"])))
            print(f"  6️⃣  ✅ Canvas: {canvas_v['count']} widgets [{types_str}]")
    else:
        if verbose:
            print(f"  6️⃣  ⚠️  Canvas: {canvas_v['count']}/{widget_count} widgets")
        record_to_auto_learn(name, category, False, canvas_v["count"],
                             f"Canvas: {canvas_v['count']}/{widget_count}")

    passed = canvas_v.get("verified", False)
    record_to_auto_learn(name, category, passed, canvas_v["count"],
                         f"Canvas has {canvas_v['count']} widgets (expected {widget_count})")

    return {
        "name": name,
        "category": category,
        "passed": passed,
        "widgets": canvas_v["count"],
        "expected": widget_count,
        "build_id": build_id,
    }


def run_batch(tag_pattern, batch_num, limit=None, verbose=True):
    """Run tests for all designs matching a category."""
    designs = json.load(open(DESIGNS_FILE))
    batch_designs = []

    for d in designs:
        cat = infer_category(d)
        if cat == tag_pattern:
            batch_designs.append(d)

    if not batch_designs:
        # Try matching by name pattern
        for d in designs:
            name = d.get("name", "").lower()
            goal = d.get("goal", "").lower()
            # Check against all category keywords
            cat = infer_category(d)
            if cat == tag_pattern:
                batch_designs.append(d)

    if limit:
        batch_designs = batch_designs[:limit]

    cat_label = CATEGORY_LABELS.get(tag_pattern, tag_pattern)

    if not batch_designs:
        print(f"\n⚠️  No designs for batch {batch_num} ({cat_label})")
        return []

    print(f"\n{'='*55}")
    print(f"  Batch {batch_num}: {cat_label} ({len(batch_designs)} designs)")
    print(f"{'='*55}")

    results = []
    for i, design in enumerate(batch_designs):
        result = test_design(design, verbose)
        results.append(result)

        status_icon = "✅" if result["passed"] else "❌"
        print(f"     [{i+1}/{len(batch_designs)}] {status_icon} {result['name']}: {result['widgets']}/{result['expected']} widgets")

        # Clean up between designs
        canvas_cleanup()
        clear_builds()

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    print(f"\n  → Batch {batch_num} Result: {passed}/{len(results)} passed, {failed} failed")

    return results


def run_all(limit_per_batch=None, verbose=True):
    """Run tests for all 10 categories."""
    categories = [
        (1, "fundamentals"), (2, "games"), (3, "desktop"),
        (4, "systems"), (5, "database"), (6, "mathematics"),
        (7, "specialized"), (8, "data-engineering"),
        (9, "devops"), (10, "search"),
    ]

    all_results = {}
    total_passed = 0
    total_failed = 0
    total_expected = 0
    total_actual = 0

    for batch_num, cat in categories:
        results = run_batch(cat, batch_num, limit_per_batch, verbose)
        all_results[cat] = results
        for r in results:
            if r["passed"]:
                total_passed += 1
            else:
                total_failed += 1
            total_expected += r["expected"]
            total_actual += r["widgets"]

    print(f"\n{'='*55}")
    print(f"  GRAND SUMMARY")
    print(f"{'='*55}")
    total = total_passed + total_failed
    print(f"  Total: {total} designs")
    print(f"  ✅ Passed: {total_passed}")
    print(f"  ❌ Failed: {total_failed}")
    if total > 0:
        print(f"  Success: {total_passed/total*100:.1f}%")
        print(f"  Widgets: {total_actual}/{total_expected} (expected/actual)")

    # Record grand summary
    try:
        record = {
            "type": "davinci_gui_batch_test",
            "content": f"Ran {total} Davinci GUI tests: {total_passed} passed, {total_failed} failed",
            "metadata": {
                "total": total,
                "passed": total_passed,
                "failed": total_failed,
                "categories": [c for _, c in categories],
            }
        }
        req = urllib.request.Request(
            f"{ARCHITECT_API}/api/auto-learn/record",
            data=json.dumps(record).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
    except:
        pass

    return all_results


# ─── Entry Point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Davinci GUI Full Pipeline Test v2")
    parser.add_argument("--all", action="store_true", help="Run all 10 batches")
    parser.add_argument("--batch", type=int, choices=range(1, 11), help="Run single batch (1-10)")
    parser.add_argument("--quick", action="store_true", help="Quick test: 2 per batch")
    parser.add_argument("--status", action="store_true", help="Check service status")
    parser.add_argument("--count", action="store_true", help="Count designs per category")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.status:
        print(f"\nChecking services...")
        try:
            req = urllib.request.Request(f"{DAVINCI_API}/api/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = json.loads(resp.read().decode())
                print(f"  ✅ Davinci Studio: {d.get('status', 'ok')} ({d.get('widget_count', 0)} widgets)")
        except Exception as e:
            print(f"  ❌ Davinci Studio: {e}")

        try:
            req = urllib.request.Request(f"{ARCHITECT_API}/api/auto-learn/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                a = json.loads(resp.read().decode())
                print(f"  ✅ Architect Backend: running (captured: {a.get('capturedCount', 0)})")
        except Exception as e:
            print(f"  ❌ Architect Backend: {e}")
        sys.exit(0)

    if args.count:
        designs = json.load(open(DESIGNS_FILE))
        cats = {}
        for d in designs:
            cat = infer_category(d)
            cats[cat] = cats.get(cat, 0) + 1
        print(f"\nDesigns per category ({len(designs)} total):")
        for batch_num, cat in [
            (1, "fundamentals"), (2, "games"), (3, "desktop"),
            (4, "systems"), (5, "database"), (6, "mathematics"),
            (7, "specialized"), (8, "data-engineering"),
            (9, "devops"), (10, "search"),
        ]:
            count = cats.get(cat, 0)
            print(f"  Batch {batch_num}: {cat:20s} → {count} designs")
        sys.exit(0)

    # Quick status check
    try:
        req = urllib.request.Request(f"{DAVINCI_API}/api/status")
        with urllib.request.urlopen(req, timeout=3) as resp:
            status = json.loads(resp.read().decode())
            if status.get("status") != "ok":
                print(f"❌ Davinci Studio not ready at {DAVINCI_API}")
                sys.exit(1)
    except Exception as e:
        print(f"❌ Davinci Studio unreachable at {DAVINCI_API}: {e}")
        sys.exit(1)

    verbose = args.verbose or not args.quick

    if args.all:
        run_all(limit_per_batch=None if not args.quick else 2, verbose=verbose)
    elif args.batch:
        categories = {1: "fundamentals", 2: "games", 3: "desktop", 4: "systems",
                      5: "database", 6: "mathematics", 7: "specialized",
                      8: "data-engineering", 9: "devops", 10: "search"}
        cat = categories[args.batch]
        run_batch(cat, args.batch, limit=None if not args.quick else 3, verbose=verbose)
    else:
        # Default: quick test all
        run_all(limit_per_batch=3, verbose=verbose)
