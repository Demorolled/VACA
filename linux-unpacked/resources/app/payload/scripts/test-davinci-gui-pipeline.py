#!/usr/bin/env python3
"""
Davinci GUI Pipeline Test
=========================
Tests the full pipeline for each batch of designs:
  1. Reads designs from designs.json
  2. Generates appropriate GUI widgets for each design
  3. Pushes the design + widgets to Davinci Studio via HTTP bridge
  4. Verifies Davinci received the build with widgets
  5. Applies the build and verifies widgets appear on the canvas
  6. Reports pass/fail results

Usage:
  python3 scripts/test-davinci-gui-pipeline.py [--batch N] [--design N] [--all]
"""

import json
import sys
import os
import time
import urllib.request
import urllib.error
from datetime import datetime

# ─── Configuration ──────────────────────────────────────────────────────────

ARCHITECT_API = "http://localhost:3001"
DAVINCI_API = "http://localhost:8000"
DESIGNS_FILE = "data/designs.json"
DATA_DIR = "data"
BIBLE_DIR = "bible-reference/00-app-designs"

# Widget type defaults for generating GUIs
WIDGET_TYPES = {
    "button": {"width": 120, "height": 36},
    "slider": {"width": 200, "height": 28},
    "toggle": {"width": 56, "height": 28},
    "display": {"width": 260, "height": 80},
    "input": {"width": 200, "height": 32},
    "knob": {"width": 52, "height": 52},
    "label": {"width": 120, "height": 24},
}

# Layout zones
LAYOUT_ZONES = {
    "topbar": {"y_start": 8, "y_end": 56, "x_start": 8, "x_end": 780},
    "main": {"y_start": 68, "y_end": 480, "x_start": 8, "x_end": 600},
    "sidebar": {"y_start": 68, "y_end": 480, "x_start": 610, "x_end": 780},
    "bottom": {"y_start": 500, "y_end": 560, "x_start": 8, "x_end": 780},
}

# ─── Widget Generation Rules ────────────────────────────────────────────

# Based on the app category/tags, generate relevant UI widgets
CATEGORY_WIDGET_TEMPLATES = {
    "fundamentals": [
        {"type": "button", "label": "Run Analysis", "zone": "topbar", "action": "runAnalysis"},
        {"type": "button", "label": "Reset", "zone": "topbar", "action": "reset"},
        {"type": "display", "label": "Results Display", "zone": "main", "action": "showResults"},
        {"type": "input", "label": "Query Input", "zone": "main", "action": "inputQuery"},
        {"type": "button", "label": "Export Data", "zone": "bottom", "action": "exportData"},
        {"type": "display", "label": "Status Panel", "zone": "main", "action": "showStatus"},
        {"type": "slider", "label": "Speed", "zone": "bottom", "action": "setSpeed"},
        {"type": "toggle", "label": "Auto Mode", "zone": "sidebar", "action": "toggleAuto"},
    ],
    "games": [
        {"type": "button", "label": "Start Game", "zone": "main", "action": "startGame"},
        {"type": "button", "label": "Pause", "zone": "bottom", "action": "pauseGame"},
        {"type": "display", "label": "Score", "zone": "topbar", "action": "showScore"},
        {"type": "display", "label": "High Score", "zone": "topbar", "action": "showHighScore"},
        {"type": "button", "label": "Restart", "zone": "bottom", "action": "restartGame"},
        {"type": "slider", "label": "Difficulty", "zone": "sidebar", "action": "setDifficulty"},
        {"type": "toggle", "label": "Sound FX", "zone": "sidebar", "action": "toggleSound"},
        {"type": "button", "label": "Settings", "zone": "topbar", "action": "openSettings"},
    ],
    "desktop": [
        {"type": "button", "label": "New File", "zone": "topbar", "action": "newFile"},
        {"type": "button", "label": "Save", "zone": "topbar", "action": "saveFile"},
        {"type": "button", "label": "Open", "zone": "topbar", "action": "openFile"},
        {"type": "display", "label": "Content Area", "zone": "main", "action": "showContent"},
        {"type": "input", "label": "Search", "zone": "topbar", "action": "searchContent"},
        {"type": "button", "label": "Delete", "zone": "main", "action": "deleteItem"},
        {"type": "toggle", "label": "Dark Mode", "zone": "sidebar", "action": "toggleDarkMode"},
        {"type": "button", "label": "Export", "zone": "bottom", "action": "export"},
    ],
    "database": [
        {"type": "button", "label": "New Query", "zone": "topbar", "action": "newQuery"},
        {"type": "button", "label": "Run Query", "zone": "topbar", "action": "runQuery"},
        {"type": "display", "label": "Query Results", "zone": "main", "action": "showResults"},
        {"type": "input", "label": "SQL Input", "zone": "main", "action": "inputSQL"},
        {"type": "button", "label": "Save Query", "zone": "bottom", "action": "saveQuery"},
        {"type": "display", "label": "Schema Viewer", "zone": "sidebar", "action": "showSchema"},
        {"type": "toggle", "label": "Auto-Commit", "zone": "sidebar", "action": "toggleAutoCommit"},
        {"type": "button", "label": "Export Results", "zone": "bottom", "action": "exportResults"},
    ],
    "systems": [
        {"type": "button", "label": "Compile", "zone": "topbar", "action": "compile"},
        {"type": "button", "label": "Run", "zone": "topbar", "action": "run"},
        {"type": "display", "label": "Output Console", "zone": "main", "action": "showOutput"},
        {"type": "display", "label": "Memory Profile", "zone": "main", "action": "showMemory"},
        {"type": "input", "label": "Command", "zone": "bottom", "action": "inputCommand"},
        {"type": "button", "label": "Debug", "zone": "topbar", "action": "toggleDebug"},
        {"type": "toggle", "label": "Verbose", "zone": "sidebar", "action": "toggleVerbose"},
        {"type": "slider", "label": "Timeout", "zone": "sidebar", "action": "setTimeout"},
    ],
    "mathematics": [
        {"type": "button", "label": "Calculate", "zone": "topbar", "action": "calculate"},
        {"type": "display", "label": "Result Display", "zone": "main", "action": "showResult"},
        {"type": "input", "label": "Expression", "zone": "main", "action": "inputExpression"},
        {"type": "display", "label": "Graph View", "zone": "main", "action": "showGraph"},
        {"type": "button", "label": "Plot", "zone": "topbar", "action": "plot"},
        {"type": "slider", "label": "Range", "zone": "bottom", "action": "setRange"},
        {"type": "toggle", "label": "Grid Lines", "zone": "sidebar", "action": "toggleGrid"},
        {"type": "button", "label": "Export Plot", "zone": "bottom", "action": "exportPlot"},
    ],
    "specialized": [
        {"type": "button", "label": "Simulate", "zone": "topbar", "action": "simulate"},
        {"type": "display", "label": "Model Output", "zone": "main", "action": "showOutput"},
        {"type": "input", "label": "Parameters", "zone": "main", "action": "inputParams"},
        {"type": "display", "label": "Progress", "zone": "main", "action": "showProgress"},
        {"type": "button", "label": "Load Model", "zone": "topbar", "action": "loadModel"},
        {"type": "slider", "label": "Precision", "zone": "sidebar", "action": "setPrecision"},
        {"type": "toggle", "label": "GPU Mode", "zone": "sidebar", "action": "toggleGPU"},
        {"type": "button", "label": "Export Results", "zone": "bottom", "action": "exportResults"},
    ],
    "data-engineering": [
        {"type": "button", "label": "Run Pipeline", "zone": "topbar", "action": "runPipeline"},
        {"type": "display", "label": "Pipeline Status", "zone": "main", "action": "showStatus"},
        {"type": "input", "label": "Source Config", "zone": "main", "action": "configSource"},
        {"type": "display", "label": "Data Preview", "zone": "main", "action": "showPreview"},
        {"type": "button", "label": "Validate", "zone": "topbar", "action": "validate"},
        {"type": "toggle", "label": "Auto-Run", "zone": "sidebar", "action": "toggleAutoRun"},
        {"type": "button", "label": "Export", "zone": "bottom", "action": "export"},
        {"type": "display", "label": "Log Viewer", "zone": "sidebar", "action": "showLogs"},
    ],
    "devops": [
        {"type": "button", "label": "Deploy", "zone": "topbar", "action": "deploy"},
        {"type": "display", "label": "Cluster Status", "zone": "main", "action": "showStatus"},
        {"type": "display", "label": "Metrics Dashboard", "zone": "main", "action": "showMetrics"},
        {"type": "button", "label": "Rollback", "zone": "topbar", "action": "rollback"},
        {"type": "input", "label": "Search Logs", "zone": "main", "action": "searchLogs"},
        {"type": "toggle", "label": "Auto-Scale", "zone": "sidebar", "action": "toggleAutoScale"},
        {"type": "button", "label": "Alert Config", "zone": "sidebar", "action": "configAlerts"},
        {"type": "button", "label": "Restart Service", "zone": "bottom", "action": "restartService"},
    ],
    "search": [
        {"type": "input", "label": "Search Query", "zone": "topbar", "action": "search"},
        {"type": "display", "label": "Search Results", "zone": "main", "action": "showResults"},
        {"type": "button", "label": "Filter", "zone": "topbar", "action": "filter"},
        {"type": "slider", "label": "Relevance", "zone": "sidebar", "action": "setRelevance"},
        {"type": "toggle", "label": "Semantic Search", "zone": "sidebar", "action": "toggleSemantic"},
        {"type": "display", "label": "Result Preview", "zone": "main", "action": "showPreview"},
        {"type": "button", "label": "Export Results", "zone": "bottom", "action": "export"},
        {"type": "button", "label": "Advanced Filters", "zone": "topbar", "action": "advancedFilters"},
    ],
}

# ─── Helper Functions ──────────────────────────────────────────────────

def load_designs():
    """Load designs from designs.json."""
    with open(DESIGNS_FILE) as f:
        return json.load(f)


def infer_category(design):
    """Infer the app category from tags and name."""
    tags = design.get("tags", [])
    name = design.get("name", "").lower()
    goal = design.get("goal", "").lower()

    # Check tags first
    for tag in tags:
        tag_lower = tag.lower()
        if "game" in tag_lower:
            return "games"
        if "database" in tag_lower or "sql" in tag_lower:
            return "database"
        if "math" in tag_lower:
            return "mathematics"
        if "data-eng" in tag_lower or "data_eng" in tag_lower:
            return "data-engineering"
        if "devops" in tag_lower or "sre" in tag_lower:
            return "devops"
        if "search" in tag_lower or "recommend" in tag_lower:
            return "search"
        if "specialized" in tag_lower or "computing" in tag_lower:
            return "specialized"
        if "system" in tag_lower:
            return "systems"
        if "desktop" in tag_lower:
            return "desktop"
        if "fundamental" in tag_lower:
            return "fundamentals"

    # Fall back to checking the category from the bible reference path
    for key in CATEGORY_WIDGET_TEMPLATES:
        if key in name or key.replace("-", "") in name.replace(" ", ""):
            return key

    # Fall back to checking goal text
    goal_lower = goal
    search_terms = {
        "games": ["game", "play", "puzzle", "snake", "tetris", "pong", "board", "card", "sokoban", "platformer", "rpg"],
        "desktop": ["editor", "explorer", "player", "viewer", "browser", "media", "note", "calendar", "mail"],
        "database": ["data", "sql", "query", "database", "schema", "index", "table", "nosql", "postgres"],
        "systems": ["compiler", "memory", "serialization", "protocol", "embedded", "kernel", "driver"],
        "mathematics": ["math", "calculus", "algebra", "geometry", "linear", "statistics", "graph", "plot"],
        "specialized": ["quantum", "bioinformatics", "chemistry", "weather", "climate", "simulation", "optimization"],
        "data-engineering": ["pipeline", "etl", "stream", "analytics", "warehouse", "lineage", "governance"],
        "devops": ["deploy", "monitor", "ci/cd", "terraform", "docker", "kubernetes", "vault", "secrets"],
        "search": ["search", "recommend", "relevance", "ranking", "vector", "embedding", "personalization"],
    }
    for cat, terms in search_terms.items():
        for term in terms:
            if term in goal_lower or term in name:
                return cat

    return "fundamentals"


def generate_widgets(design, category=None):
    """Generate GUI widgets for a given design."""
    if category is None:
        category = infer_category(design)

    templates = CATEGORY_WIDGET_TEMPLATES.get(category, CATEGORY_WIDGET_TEMPLATES["fundamentals"])
    name = design.get("name", "App")
    goal = design.get("goal", "")

    widgets = []
    occupied_rects = []
    widget_id_counter = [0]

    for tmpl in templates:
        zone = LAYOUT_ZONES.get(tmpl["zone"], LAYOUT_ZONES["main"])
        wtype = tmpl["type"]
        wlabel = tmpl["label"]
        wdef = WIDGET_TYPES.get(wtype, WIDGET_TYPES["button"])
        ww = wdef["width"]
        wh = wdef["height"]

        # Find a non-colliding position within the zone
        x, y = find_position(zone, ww, wh, occupied_rects)

        widget_id = f"w_{widget_id_counter[0]}_{int(time.time()*1000)}"
        widget_id_counter[0] += 1

        widget = {
            "id": widget_id,
            "type": wtype,
            "label": wlabel,
            "x": x,
            "y": y,
            "width": ww,
            "height": wh,
            "linkedNodeId": f"node_{tmpl['action']}",
            "archBindings": {
                "onClick": tmpl["action"] if wtype == "button" else "",
                "onChange": tmpl["action"] if wtype in ("slider", "toggle", "knob", "input") else "",
                "displayInput": tmpl["action"] if wtype == "display" else "",
                "valueInput": "",
            },
            "rotation": 0,
            "opacity": 100,
            "styleId": "bs1",
            "props": {}
        }
        widgets.append(widget)
        occupied_rects.append({"x": x, "y": y, "w": ww, "h": wh})

    return widgets


def find_position(zone, width, height, occupied):
    """Find a non-colliding position within a layout zone."""
    margin = 10
    max_attempts = 100

    for attempt in range(max_attempts):
        # Simple grid placement: use attempt to determine row/col
        col = attempt % 3
        row = attempt // 3
        x = zone["x_start"] + col * (width + margin)
        y = zone["y_start"] + row * (height + margin)

        # Check bounds
        if x + width > zone["x_end"]:
            continue
        if y + height > zone["y_end"]:
            continue

        # Check collision
        collides = False
        for occ in occupied:
            if (x < occ["x"] + occ["w"] + margin and
                x + width + margin > occ["x"] and
                y < occ["y"] + occ["h"] + margin and
                y + height + margin > occ["y"]):
                collides = True
                break

        if not collides:
            return x, y

    # Fallback: stack at zone start
    return zone["x_start"], zone["y_start"] + (len(occupied) * (height + margin) % (zone["y_end"] - zone["y_start"]))


def build_architect_nodes(design):
    """Build architect node representation from design nodes."""
    nodes = []
    for node in design.get("nodes", []):
        nodes.append({
            "id": node.get("id", ""),
            "label": node.get("data", {}).get("label", node.get("label", "Node")),
            "type": node.get("data", {}).get("type", node.get("type", "logic")),
            "description": node.get("data", {}).get("description", ""),
        })
    return nodes


def push_build_to_davinci(design, widgets, architect_nodes):
    """Push a build + widgets to Davinci Studio via HTTP bridge."""
    build_data = {
        "appName": design.get("name", "Untitled"),
        "goal": design.get("goal", ""),
        "nodeCount": len(architect_nodes),
        "widgetCount": len(widgets),
        "architectNodes": architect_nodes,
        "uiFunctions": [{
            "id": f"uifn_{w['id']}",
            "label": w["label"],
            "type": w["type"],
            "description": f"Widget for {design.get('name', 'App')}",
            "defaultAction": w["archBindings"].get("onClick") or w["archBindings"].get("onChange") or "",
            "category": "utility",
            "linkedNodeId": w.get("linkedNodeId", ""),
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
            result = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        return {"received": False, "error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"received": False, "error": str(e)}


def verify_build_on_davinci(build_id=None):
    """Verify that a build exists on Davinci with widgets."""
    try:
        req = urllib.request.Request(f"{DAVINCI_API}/api/bridge/builds")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            builds = result.get("builds", [])
            if not builds:
                return {"verified": False, "error": "No builds found on Davinci", "builds": []}
            if build_id:
                matches = [b for b in builds if b.get("id") == build_id]
                if not matches:
                    return {"verified": False, "error": f"Build {build_id} not found", "builds": builds}
                return {"verified": True, "build": matches[0], "all_builds": builds}
            return {"verified": True, "build": builds[0], "all_builds": builds, "count": len(builds)}
    except urllib.error.HTTPError as e:
        return {"verified": False, "error": f"HTTP {e.code}: {e.read().decode()}", "builds": []}
    except Exception as e:
        return {"verified": False, "error": str(e), "builds": []}


def apply_build_on_davinci(build_id):
    """Apply a build's widgets to the Davinci canvas."""
    try:
        req = urllib.request.Request(
            f"{DAVINCI_API}/api/bridge/builds/{build_id}/apply",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode()}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def verify_widgets_on_canvas(expected_count):
    """Verify widgets exist on the Davinci canvas."""
    try:
        req = urllib.request.Request(f"{DAVINCI_API}/api/widgets")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            widgets = result.get("widgets", [])
            return {
                "verified": len(widgets) >= expected_count,
                "widget_count": len(widgets),
                "expected": expected_count,
                "widgets": widgets,
            }
    except urllib.error.HTTPError as e:
        return {"verified": False, "error": f"HTTP {e.code}: {e.read().decode()}", "widget_count": 0}
    except Exception as e:
        return {"verified": False, "error": str(e), "widget_count": 0}


def clear_davinci_builds():
    """Clear all builds from Davinci to keep tests clean."""
    try:
        req = urllib.request.Request(
            f"{DAVINCI_API}/api/bridge/builds/clear",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except:
        return {"ok": False}


def record_test_to_auto_learn(design_name, category, passed, widget_count, details):
    """Record the test result to the auto-learn system."""
    try:
        record = {
            "type": "davinci_gui_test",
            "content": f"Tested {design_name} ({category}): {'PASS' if passed else 'FAIL'} - {widget_count} widgets",
            "metadata": {
                "design": design_name,
                "category": category,
                "passed": passed,
                "widget_count": widget_count,
                "details": details,
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


def check_davinci_status():
    """Check if Davinci backend is reachable and return status."""
    try:
        req = urllib.request.Request(f"{DAVINCI_API}/api/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


def check_architect_status():
    """Check if Architect backend is reachable."""
    try:
        req = urllib.request.Request(f"{ARCHITECT_API}/api/auto-learn/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Main Test Runner ──────────────────────────────────────────────────

def run_test(design, category=None, verbose=True):
    """Run a complete test for a single design."""
    name = design.get("name", "Unknown")
    if category is None:
        category = infer_category(design)

    if verbose:
        print(f"\n  ── Testing: {name} ({category}) ──")

    # Step 1: Generate widgets
    widgets = generate_widgets(design, category)
    if verbose:
        print(f"    1. Generated {len(widgets)} GUI widgets")

    # Step 2: Build architect nodes
    architect_nodes = build_architect_nodes(design)
    if verbose:
        print(f"    2. Built {len(architect_nodes)} architect nodes")

    # Step 3: Push build to Davinci
    push_result = push_build_to_davinci(design, widgets, architect_nodes)
    if verbose:
        if push_result.get("received"):
            print(f"    3. ✅ Push to Davinci: received (build_id={push_result.get('build_id', 'unknown')})")
        else:
            print(f"    3. ❌ Push to Davinci FAILED: {push_result.get('error', 'unknown error')}")
            record_test_to_auto_learn(name, category, False, len(widgets), str(push_result))
            return {
                "name": name, "category": category, "passed": False,
                "widgets": len(widgets), "reason": f"Push failed: {push_result.get('error')}"
            }

    build_id = push_result.get("build_id")

    # Step 4: Verify build on Davinci
    time.sleep(0.5)  # Let Davinci process
    verify_result = verify_build_on_davinci(build_id)
    if verify_result.get("verified"):
        if verbose:
            print(f"    4. ✅ Build verified on Davinci: {verify_result['build'].get('widgetCount', 0)} widgets in build")
    else:
        if verbose:
            print(f"    4. ❌ Build verification FAILED: {verify_result.get('error', 'unknown')}")
        record_test_to_auto_learn(name, category, False, len(widgets), str(verify_result))
        return {
            "name": name, "category": category, "passed": False,
            "widgets": len(widgets), "reason": f"Verify failed: {verify_result.get('error')}"
        }

    # Step 5: Apply build to canvas
    apply_result = apply_build_on_davinci(build_id)
    if apply_result.get("ok") or apply_result.get("widgets_applied"):
        if verbose:
            print(f"    5. ✅ Build applied: {apply_result.get('widgets_applied', '?')} widgets on canvas")
    else:
        if verbose:
            print(f"    5. ❌ Apply FAILED: {apply_result.get('error', 'unknown')}")
        record_test_to_auto_learn(name, category, False, len(widgets), str(apply_result))
        return {
            "name": name, "category": category, "passed": False,
            "widgets": len(widgets), "reason": f"Apply failed: {apply_result.get('error')}"
        }

    # Step 6: Verify widgets on canvas
    canvas_verify = verify_widgets_on_canvas(len(widgets))
    if canvas_verify.get("verified"):
        if verbose:
            print(f"    6. ✅ Canvas verification PASSED: {canvas_verify['widget_count']} widgets present (expected >= {len(widgets)})")
    else:
        if verbose:
            print(f"    6. ⚠️ Canvas verification: {canvas_verify['widget_count']} widgets (expected >= {len(widgets)})")

    # Record to auto-learn
    passed = canvas_verify.get("verified", False)
    record_test_to_auto_learn(name, category, passed, canvas_verify.get("widget_count", 0),
                              {"applied": apply_result, "canvas": canvas_verify.get("widget_count", 0)})

    return {
        "name": name,
        "category": category,
        "passed": passed,
        "widgets": canvas_verify.get("widget_count", len(widgets)),
        "expected_widgets": len(widgets),
        "build_id": build_id,
    }


def run_batch(batch_num, category_key, limit=None, verbose=True):
    """Run tests for an entire batch/category."""
    designs = load_designs()
    batch_designs = [d for d in designs if category_key in d.get("tags", []) or
                     category_key in d.get("name", "").lower()]

    if limit:
        batch_designs = batch_designs[:limit]

    if not batch_designs:
        print(f"\n⚠️  No designs found for category '{category_key}'")
        return []

    print(f"\n{'='*60}")
    print(f"  Batch {batch_num}: {category_key.upper()} ({len(batch_designs)} designs)")
    print(f"{'='*60}")

    results = []
    passed = 0
    failed = 0

    for i, design in enumerate(batch_designs):
        result = run_test(design, category_key, verbose)
        results.append(result)
        if result["passed"]:
            passed += 1
        else:
            failed += 1

        # Print summary line
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"     [{i+1}/{len(batch_designs)}] {status} → {result['name']}: {result['widgets']} widgets")

        # Clear builds between each design to keep test clean
        clear_davinci_builds()

    # Batch summary
    print(f"\n  Batch {batch_num} Summary: {passed}/{len(batch_designs)} passed, {failed} failed")
    if failed > 0:
        for r in results:
            if not r["passed"]:
                print(f"    ❌ {r['name']}: {r.get('reason', 'unknown error')}")

    return results


def run_all_tests(limit_per_batch=None, verbose=True):
    """Run tests for all categories."""
    check_davinci_status()
    categories = [
        (1, "fundamentals"),
        (2, "games"),
        (3, "desktop"),
        (4, "systems"),
        (5, "database"),
        (6, "mathematics"),
        (7, "specialized"),
        (8, "data-engineering"),
        (9, "devops"),
        (10, "search"),
    ]

    all_results = {}
    total_passed = 0
    total_failed = 0

    for batch_num, cat in categories:
        results = run_batch(batch_num, cat, limit_per_batch, verbose)
        all_results[cat] = results
        for r in results:
            if r["passed"]:
                total_passed += 1
            else:
                total_failed += 1

    # Grand summary
    print(f"\n{'='*60}")
    print(f"  GRAND SUMMARY")
    print(f"{'='*60}")
    print(f"  Total designs tested: {total_passed + total_failed}")
    print(f"  Passed: {total_passed}")
    print(f"  Failed: {total_failed}")
    print(f"  Success rate: {total_passed/(total_passed+total_failed)*100:.1f}%" if (total_passed + total_failed) > 0 else "  No tests run")

    # Also record to auto-learn
    try:
        record = {
            "type": "davinci_gui_batch_test",
            "content": f"Ran {total_passed + total_failed} Davinci GUI tests: {total_passed} passed, {total_failed} failed",
            "metadata": {
                "total": total_passed + total_failed,
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


# ─── Command Line Interface ────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Davinci GUI pipeline for app designs")
    parser.add_argument("--batch", type=int, help="Run a specific batch (1-10)")
    parser.add_argument("--design", type=str, help="Test a specific design by name")
    parser.add_argument("--all", action="store_true", help="Run tests for all categories")
    parser.add_argument("--limit", type=int, default=None, help="Limit designs per batch")
    parser.add_argument("--quiet", action="store_true", help="Less verbose output")
    parser.add_argument("--status", action="store_true", help="Just check Davinci status")
    parser.add_argument("--clear", action="store_true", help="Clear all Davinci builds")
    args = parser.parse_args()

    verbose = not args.quiet

    # Just check status
    if args.status:
        print("\nChecking service status...")
        davinci = check_davinci_status()
        architect = check_architect_status()
        print(f"\n  Davinci Studio: {'✅ ' + davinci.get('status', 'unknown') if davinci.get('status') == 'ok' else '❌ ' + davinci.get('error', 'unreachable')}")
        print(f"  Widgets on canvas: {davinci.get('widget_count', '?')}")
        print(f"  Projects: {davinci.get('project_count', '?')}")
        print(f"\n  Architect Backend: {'✅ running' if architect.get('success') else '❌ ' + architect.get('error', 'unreachable')}")
        print(f"  Auto-learn captured: {architect.get('capturedCount', 0)}")
        sys.exit(0)

    # Clear all builds
    if args.clear:
        result = clear_davinci_builds()
        print(f"Davinci builds cleared: {result.get('ok', False)}")
        sys.exit(0)

    # Check services first
    davinci = check_davinci_status()
    if davinci.get("status") != "ok":
        print(f"\n❌ Davinci Studio is not reachable at {DAVINCI_API}")
        print(f"   Error: {davinci.get('error', 'connection refused')}")
        print(f"   Start it with: cd davinci-app && bash start.sh")
        sys.exit(1)

    architect = check_architect_status()
    if not architect.get("success"):
        print(f"\n❌ Architect backend is not reachable at {ARCHITECT_API}")
        sys.exit(1)

    print(f"\n✅ Both services running")
    print(f"   Davinci Studio: {DAVINCI_API}")
    print(f"   Architect Backend: {ARCHITECT_API}")
    print(f"   Widgets on canvas: {davinci.get('widget_count', '?')}")

    # Run tests
    categories = {
        1: "fundamentals", 2: "games", 3: "desktop", 4: "systems",
        5: "database", 6: "mathematics", 7: "specialized",
        8: "data-engineering", 9: "devops", 10: "search",
    }

    if args.all:
        run_all_tests(args.limit, verbose)
    elif args.batch:
        if args.batch in categories:
            run_batch(args.batch, categories[args.batch], args.limit, verbose)
        else:
            print(f"Invalid batch number {args.batch}. Valid: 1-10")
            sys.exit(1)
    elif args.design:
        designs = load_designs()
        matches = [d for d in designs if args.design.lower() in d.get("name", "").lower()]
        if not matches:
            print(f"No designs matching '{args.design}'")
            sys.exit(1)
        for d in matches:
            cat = infer_category(d)
            run_test(d, cat, verbose)
            clear_davinci_builds()
    else:
        # Default: run a quick test with 2 designs from each batch
        print(f"\nQuick test mode: 2 designs per batch")
        run_all_tests(limit_per_batch=2, verbose=verbose)
