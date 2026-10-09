#!/usr/bin/env python3
"""
Master Pipeline v2
==================
Efficient batch generation of 600+ designs with Davinci GUI pipeline testing.

Flow per batch:
  1. Read design specs from data/design-specs-v2.json
  2. Auto-generate nodes/edges using category templates
  3. Write to designs.json and bible reference files
  4. Push to Davinci Studio via HTTP bridge
  5. Verify build received, applied, and widgets present on canvas
  6. Clean up builds to save space
  7. Record results to auto-learn

Usage:
  python3 scripts/master-pipeline-v2.py [--batch 1-4] [--all] [--quick]
"""

import json, os, sys, time, re, math, urllib.request, urllib.error
from datetime import datetime

# ─── Config ─────────────────────────────────────────────────────────────
ARCHITECT_API = "http://localhost:3001"
DAVINCI_API = "http://localhost:8000"
SPECS_FILE = "data/design-specs-v2.json"
DESIGNS_FILE = "data/designs.json"
BIBLE_BASE = "bible-reference/00-app-designs"
NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

# ─── Tag → Category mapping ─────────────────────────────────────────────
TAG_CATEGORY = {
    "algorithms":"fundamentals","data-structures":"fundamentals","complexity":"fundamentals",
    "arrays":"fundamentals","linked-list":"fundamentals","binary":"fundamentals",
    "sorting":"fundamentals","searching":"fundamentals","recursion":"fundamentals",
    "backtracking":"fundamentals","dp":"fundamentals","dynamic-programming":"fundamentals",
    "greedy":"fundamentals","hash-table":"fundamentals","string":"fundamentals",
    "stack":"fundamentals","queue":"fundamentals","graph":"fundamentals",
    "tree":"fundamentals","bst":"fundamentals","geometry":"fundamentals",
    "game":"games","arcade":"games","puzzle":"games","card-game":"games",
    "classic":"games","platformer":"games","maze":"games",
    "desktop":"desktop","utility":"desktop","productivity":"desktop",
    "design":"desktop","editor":"desktop",
    "database":"database","sql":"database","nosql":"database","postgresql":"database",
    "redis":"database","mongodb":"database",
    "systems":"systems","low-level":"systems","concurrency":"systems","linux":"systems",
    "compiler":"systems","binary":"systems","memory":"systems","cpu":"systems",
    "networking":"systems","ipc":"systems","debugging":"systems",
    "mathematics":"mathematics","linear-algebra":"mathematics","calculus":"mathematics",
    "statistics":"mathematics","probability":"mathematics","numerical":"mathematics",
    "visualization":"mathematics","education":"mathematics",
    "specialized":"specialized","computation":"specialized","simulation":"specialized",
    "science":"specialized","graphics":"specialized","physics":"specialized",
    "robotics":"specialized","ml":"specialized","deep-learning":"specialized",
    "optimization":"specialized",
    "data-engineering":"data-engineering","etl":"data-engineering","pipeline":"data-engineering",
    "data-quality":"data-engineering","analytics":"data-engineering","streaming":"data-engineering",
    "lakehouse":"data-engineering",
    "devops":"devops","devops":"devops","sre":"devops","monitoring":"devops",
    "ci-cd":"devops","docker":"devops","kubernetes":"devops","iac":"devops",
    "observability":"devops","security":"devops",
    "search":"search","recommendation":"search","personalization":"search",
    "ranking":"search","nlp":"search","embeddings":"search","information-retrieval":"search",
    "clustering":"search"
}

CATEGORY_LABELS = {
    "fundamentals":"01-fundamentals","games":"02-games","desktop":"03-desktop-apps",
    "systems":"05-systems-programming","database":"06-databases",
    "mathematics":"13-math","specialized":"20-specialized-computing",
    "data-engineering":"27-data-engineering","devops":"33-devops-sre-tooling",
    "search":"36-search-recs-personalization"
}

# ─── Category-Specific Node Templates ──────────────────────────────────
# Each template yields 5 nodes with types/labels/descriptions/positions

NODE_TEMPLATES = {
    "fundamentals": [
        ("input","Data Input","User input and configuration parameters","typescript",50,50),
        ("logic","Core Algorithm","Algorithm implementation with step-by-step execution","python",250,50),
        ("database","Results Store","Computation results, state, and performance data","typescript",50,250),
        ("logic","Analysis Engine","Result analysis, comparison, and insights generation","typescript",450,50),
        ("ui","Visualization","Interactive charts, graphs, and data visualization","typescript",450,250)
    ],
    "games": [
        ("input","Game Controller","Player input: keyboard, mouse, or touch controls","typescript",50,50),
        ("logic","Game Engine","Core game loop: update, physics, collision, scoring","typescript",250,50),
        ("database","Game State","Player stats, level state, high scores, save data","typescript",50,250),
        ("logic","AI Opponent","Computer opponent logic and difficulty management","typescript",450,50),
        ("ui","Render View","Game canvas, HUD, menus, and visual effects","typescript",450,250)
    ],
    "desktop": [
        ("input","User Input","File operations, user interactions, configuration","typescript",50,50),
        ("logic","Core Logic","Business logic, data processing, file management","typescript",250,50),
        ("database","Data Store","Application data, preferences, user content","sqlite",50,250),
        ("logic","Search & Filter","Search, sort, filter, and data management operations","typescript",450,50),
        ("ui","User Interface","Desktop UI with panels, dialogs, and controls","typescript",450,250)
    ],
    "systems": [
        ("input","System Config","Configuration, target selection, parameter input","typescript",50,50),
        ("logic","Core Engine","Systems-level logic: tracing, analysis, simulation","cpp",250,50),
        ("database","Data Collection","Metrics, traces, state data, profiling results","typescript",50,250),
        ("logic","Analysis Module","Data analysis, pattern detection, report generation","python",450,50),
        ("ui","Dashboard View","Visualizations, charts, system state display","typescript",450,250)
    ],
    "database": [
        ("input","Query/Config","SQL queries, schema design, configuration input","typescript",50,50),
        ("logic","Database Engine","Core database operations: query processing, storage","typescript",250,50),
        ("database","Data Store","Tables, indexes, schemas, metadata storage","sqlite",50,250),
        ("logic","Analysis & Optimization","Query optimization, index advice, performance analysis","python",450,50),
        ("ui","Results Display","Query results, execution plans, performance charts","typescript",450,250)
    ],
    "mathematics": [
        ("input","Math Input","Equations, parameters, data points, configuration","typescript",50,50),
        ("logic","Math Engine","Mathematical computation and algorithm implementation","python",250,50),
        ("database","Data Storage","Results, history, parameter sets, reference data","typescript",50,250),
        ("logic","Analysis Module","Error analysis, validation, comparison, statistics","python",450,50),
        ("ui","Visualization","Graphs, 3D plots, charts, and interactive displays","typescript",450,250)
    ],
    "specialized": [
        ("input","Domain Input","Domain-specific parameters, data loading, config","typescript",50,50),
        ("logic","Core Algorithm","Specialized algorithm for the domain","python",250,50),
        ("database","Data Store","Simulation data, results, references, parameters","typescript",50,250),
        ("logic","Analysis Engine","Result analysis, validation, error computation","python",450,50),
        ("ui","Visualization","Domain-specific viz: 3D, plots, animations","typescript",450,250)
    ],
    "data-engineering": [
        ("input","Pipeline Config","Source/target config, data format, schedule","typescript",50,50),
        ("logic","Data Processor","Transform, validate, process data pipeline stage","python",250,50),
        ("database","Data Store","Metadata, catalogs, quality metrics, logs","sqlite",50,250),
        ("logic","Orchestrator","Workflow orchestration, scheduling, monitoring","python",450,50),
        ("ui","Pipeline Dashboard","DAG view, metrics, status, data preview","typescript",450,250)
    ],
    "devops": [
        ("input","Config Input","Infrastructure config, pipeline definition, settings","typescript",50,50),
        ("logic","Orchestrator","Workflow orchestration, deployment, automation","python",250,50),
        ("database","State Store","Infrastructure state, secret data, config cache","sqlite",50,250),
        ("logic","Analysis Engine","Metrics analysis, compliance check, cost calc","python",450,50),
        ("ui","Ops Dashboard","Dashboards, pipeline views, alerts, charts","typescript",450,250)
    ],
    "search": [
        ("input","Query Input","Search query, user profile, content to index","typescript",50,50),
        ("logic","Search Engine","Indexing, retrieval, ranking, personalization","python",250,50),
        ("database","Index & Data","Search index, user profiles, interaction logs","sqlite",50,250),
        ("logic","Evaluation Module","Relevance metrics, A/B testing, performance","python",450,50),
        ("ui","Results Display","Search results, recommendations, dashboards","typescript",450,250)
    ]
}

# Standard edges for 5-node architecture: input→logic1→db→logic2→ui
def make_edges():
    return [
        {"source":"node_0","target":"node_1"},
        {"source":"node_1","target":"node_2"},
        {"source":"node_2","target":"node_3"},
        {"source":"node_3","target":"node_4"},
        {"source":"node_1","target":"node_4"}
    ]

def generate_nodes(category, name_slug):
    """Generate nodes for a design based on category template."""
    tmpl = NODE_TEMPLATES.get(category, NODE_TEMPLATES["fundamentals"])
    nodes = []
    for i, (n_type, n_label_prefix, n_desc_suffix, n_lang, n_x, n_y) in enumerate(tmpl):
        label = f"{n_label_prefix}"
        desc = f"{n_desc_suffix} for {name_slug}"
        # Offset positions slightly per design to prevent overlap
        offset_x = 0  # (hash(name_slug) % 3) * 10
        nodes.append({
            "id": f"saved_{i}",
            "type": n_type,
            "label": label,
            "description": desc.strip(),
            "language": n_lang,
            "position": {"x": n_x + offset_x, "y": n_y}
        })
    return nodes

def save_design(name, goal, purpose, nodes, edges, tags):
    """Create a design dict matching designs.json format."""
    return {
        "id": f"design_v2_{int(time.time()*1000)}_{os.urandom(2).hex()}",
        "name": name, "goal": goal, "purpose": purpose,
        "targetOS": "linux", "nodes": nodes, "edges": edges,
        "roadmap": f"App: {name}\nTarget: linux\nNodes: {len(nodes)}\nConnections: {len(edges)}",
        "createdAt": NOW, "updatedAt": NOW, "source": "local",
        "tags": tags[:5]
    }

def infer_category(tags):
    for t in tags:
        if t in TAG_CATEGORY:
            return TAG_CATEGORY[t]
    return "fundamentals"

def safe_fn(name):
    s = name.lower().replace(' ','-').replace('/','-').replace('\\','-')
    s = re.sub(r'[^a-z0-9-]','',s)
    s = re.sub(r'-+','-',s).strip('-')
    return s[:60]

def write_bible_ref(design, category):
    """Write a bible reference markdown file for a design."""
    cat_label = CATEGORY_LABELS.get(category, category)
    bible_dir = os.path.join(BIBLE_BASE, cat_label)
    os.makedirs(bible_dir, exist_ok=True)
    fn = f"{safe_fn(design['name'])}.md"
    path = os.path.join(bible_dir, fn)

    nodes_str = '\n'.join([f"  - **{n['label']}** ({n['type']}): {n['description']}" for n in design['nodes']])
    edges_str = '\n'.join([f"  - `{e['source']}` → `{e['target']}`" for e in design['edges'][:5]])

    content = f"""# {design['name']}

**Design ID:** `{design['id']}` | **Category:** {cat_label}

## Goal
{design['goal']}

## Purpose
{design.get('purpose','')}

## Nodes
{nodes_str}

## Edges
{edges_str}

## Tags
{', '.join(design['tags'][:5])}

---
*Design generated for Visual AI Architect | {NOW}*
"""
    with open(path, 'w') as f:
        f.write(content)
    return path

# ─── Davinci GUI Testing ──────────────────────────────────────────────
WIDGET_DEFAULTS = {"button":{"w":120,"h":36},"slider":{"w":200,"h":28},"toggle":{"w":56,"h":28},"display":{"w":260,"h":80},"input":{"w":200,"h":32},"knob":{"w":52,"h":52},"label":{"w":120,"h":24}}
ZONES = {"topbar":{"x":8,"y":8,"mx":780,"my":56},"main":{"x":8,"y":68,"mx":600,"my":480},"sidebar":{"x":610,"y":68,"mx":780,"my":480},"bottom":{"x":8,"y":500,"mx":780,"my":560}}

CAT_WIDGETS = {
    "fundamentals":[("button","Run","topbar","run"),("display","Output","main","showResult"),("input","Input","main","inputData"),("display","Visualization","main","showViz"),("slider","Speed","bottom","setSpeed"),("toggle","Auto","sidebar","toggleAuto"),("button","Reset","bottom","reset"),("button","Export","bottom","export")],
    "games":[("button","Start","main","startGame"),("button","Pause","bottom","pause"),("display","Score","topbar","score"),("display","Timer","topbar","timer"),("button","Restart","bottom","restart"),("slider","Difficulty","sidebar","diff"),("toggle","Sound","sidebar","sound"),("button","Settings","topbar","settings")],
    "desktop":[("button","New","topbar","new"),("button","Save","topbar","save"),("button","Open","topbar","open"),("display","Content","main","content"),("input","Search","topbar","search"),("button","Delete","main","delete"),("toggle","Dark Mode","sidebar","darkMode"),("button","Export","bottom","export")],
    "database":[("button","New Query","topbar","newQuery"),("button","Run","topbar","runQuery"),("display","Results","main","results"),("input","SQL","main","inputSQL"),("display","Schema","sidebar","schema"),("button","Save","bottom","save"),("toggle","Auto-Commit","sidebar","autoCommit"),("button","Export","bottom","export")],
    "systems":[("button","Compile","topbar","compile"),("button","Run","topbar","run"),("display","Output","main","output"),("display","Profile","main","profile"),("input","Command","bottom","cmd"),("button","Debug","topbar","debug"),("toggle","Verbose","sidebar","verbose"),("slider","Timeout","sidebar","timeout")],
    "mathematics":[("button","Calculate","topbar","calc"),("display","Result","main","result"),("input","Expression","main","expr"),("display","Graph","main","graph"),("button","Plot","topbar","plot"),("slider","Range","bottom","range"),("toggle","Grid","sidebar","grid"),("button","Export","bottom","export")],
    "specialized":[("button","Simulate","topbar","simulate"),("display","Output","main","output"),("input","Params","main","params"),("display","Progress","main","progress"),("button","Load","topbar","load"),("slider","Precision","sidebar","precision"),("toggle","GPU","sidebar","gpu"),("button","Export","bottom","export")],
    "data-engineering":[("button","Run Pipeline","topbar","runPipeline"),("display","Status","main","status"),("input","Config","main","config"),("display","Preview","main","preview"),("button","Validate","topbar","validate"),("toggle","Auto","sidebar","autoRun"),("display","Logs","sidebar","logs"),("button","Export","bottom","export")],
    "devops":[("button","Deploy","topbar","deploy"),("display","Status","main","status"),("display","Metrics","main","metrics"),("button","Rollback","topbar","rollback"),("input","Search Logs","main","searchLogs"),("toggle","Auto-Scale","sidebar","scale"),("button","Alert Config","sidebar","alerts"),("button","Restart","bottom","restart")],
    "search":[("input","Search","topbar","search"),("display","Results","main","results"),("button","Filter","topbar","filter"),("slider","Relevance","sidebar","relevance"),("toggle","Semantic","sidebar","semantic"),("display","Preview","main","preview"),("button","Advanced","topbar","advanced"),("button","Export","bottom","export")]
}

def generate_widgets(goal, category):
    """Generate 8 GUI widgets for a design."""
    tmpl = CAT_WIDGETS.get(category, CAT_WIDGETS["fundamentals"])
    widgets = []
    occupied = []
    for i, (wt, wl, zn, act) in enumerate(tmpl):
        z = ZONES[zn]
        wd = WIDGET_DEFAULTS[wt]
        col = i % 3
        row = i // 3
        x = z["x"] + col * (wd["w"] + 12)
        y = z["y"] + row * (wd["h"] + 12)
        if x + wd["w"] > z["mx"]: x = z["x"]; y += wd["h"] + 12
        if y + wd["h"] > z["my"]: y = z["y"]
        wid = f"w_{act}_{int(time.time()*1000)}_{i}"
        arch = {}
        if wt == "button": arch["onClick"] = act
        elif wt in ("slider","toggle","input","knob"): arch["onChange"] = act
        elif wt == "display": arch["displayInput"] = act
        widgets.append({"id":wid,"type":wt,"label":wl,"x":x,"y":y,
            "width":wd["w"],"height":wd["h"],
            "linkedNodeId":f"node_{act}",
            "archBindings":{**arch,"valueInput":""},
            "rotation":0,"opacity":100,"styleId":"bs1","props":{}})
        occupied.append((x,y,wd["w"],wd["h"]))
    return widgets

def build_nodes(design):
    out = []
    for node in design.get("nodes",[]):
        nd = node.get("data",node)
        out.append({"id":node.get("id",""),"label":nd.get("label","Node"),"type":nd.get("type","logic"),"description":nd.get("description","")})
    return out

# ─── API Helpers ───────────────────────────────────────────────────────
def api_post(url, data):
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error":f"HTTP {e.code}"}
    except Exception as e:
        return {"error":str(e)[:80]}

def api_get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode())
    except:
        return {}

def push_to_davinci(design, widgets, arch_nodes):
    goal = design.get("goal","") or design.get("name","")
    data = {"appName":design.get("name","Untitled"),"goal":goal,
        "nodeCount":len(arch_nodes),"widgetCount":len(widgets),
        "architectNodes":arch_nodes,
        "uiFunctions":[{"id":w["id"],"label":w["label"],"type":w["type"],
            "description":f"Widget for {goal}","defaultAction":w["archBindings"].get("onClick","") or w["archBindings"].get("onChange",""),
            "category":"utility"} for w in widgets],
        "placedWidgets":widgets,
        "archBindings":[{"widgetId":w["id"],"widgetLabel":w["label"],
            "nodeId":w.get("linkedNodeId",""),
            "bindings":{k:v for k,v in w["archBindings"].items() if v}}
            for w in widgets if any(w["archBindings"].values())]}
    return api_post(f"{DAVINCI_API}/api/bridge/builds", data)

def test_design_on_davinci(design, category):
    """Generate widgets, push to Davinci, verify, apply, verify canvas, cleanup."""
    name = design.get("name","?")
    goal = design.get("goal","")
    widgets = generate_widgets(goal, category)
    arch_nodes = build_nodes(design)
    wc = len(widgets)

    push_result = push_to_davinci(design, widgets, arch_nodes)
    bid = push_result.get("build_id","")
    if not push_result.get("received",False):
        return {"name":name,"passed":False,"widgets":wc,"reason":push_result.get("error","push_failed")}

    time.sleep(0.2)
    builds = api_get(f"{DAVINCI_API}/api/bridge/builds").get("builds",[])
    found = any(b.get("id")==bid for b in builds)
    if not found:
        return {"name":name,"passed":False,"widgets":wc,"reason":"build_not_found"}

    apply_result = api_post(f"{DAVINCI_API}/api/bridge/builds/{bid}/apply", {})
    appl = apply_result.get("widgets_applied",0) or (1 if apply_result.get("ok") else 0)
    if appl == 0:
        canvas_cleanup(); clear_builds()
        return {"name":name,"passed":False,"widgets":wc,"reason":"apply_failed"}

    time.sleep(0.2)
    canvas = api_get(f"{DAVINCI_API}/api/widgets").get("widgets",[])
    ccount = len(canvas)
    passed = ccount >= wc

    # Record to auto-learn
    record_test(name, category, passed, ccount, f"Canvas:{ccount}/{wc}")

    # Cleanup
    canvas_cleanup()
    clear_builds()

    return {"name":name,"passed":passed,"widgets":ccount,"expected":wc}

def canvas_cleanup():
    api_post(f"{DAVINCI_API}/api/widgets/batch", {"widgets":[]})
def clear_builds():
    api_post(f"{DAVINCI_API}/api/bridge/builds/clear", {})
def record_test(name, cat, passed, wc, details):
    api_post(f"{ARCHITECT_API}/api/auto-learn/record",
        {"type":"davinci_gui_test","content":f"Test {name} ({cat}): {'PASS' if passed else 'FAIL'} - {wc} widgets",
         "metadata":{"design":name,"category":cat,"passed":passed,"widget_count":wc,"details":details}})

# ─── Main Pipeline ─────────────────────────────────────────────────────
def run_pipeline(batch_nums=None, limit_per_category=None, verbose=True):
    """Run the full generate → test → cleanup pipeline."""
    specs = json.load(open(SPECS_FILE))
    
    # Load existing designs
    existing = []
    if os.path.exists(DESIGNS_FILE):
        with open(DESIGNS_FILE) as f:
            existing = json.load(f)
    
    print(f"📂 Loaded {len(existing)} existing designs")

    # Determine which categories to process
    all_cats = list(specs["categories"].keys())
    categories = [all_cats[i-1] for i in batch_nums] if batch_nums else all_cats

    total_new = 0
    total_tested = 0
    total_passed = 0
    total_widgets = 0

    for cat_idx, cat in enumerate(categories):
        cat_specs = specs["categories"][cat]
        design_list = cat_specs["designs"]
        bible_section = cat_specs.get("bible_section", CATEGORY_LABELS.get(cat, cat))
        cat_limit = limit_per_category or len(design_list)

        if limit_per_category:
            design_list = design_list[:cat_limit]

        print(f"\n{'='*55}")
        print(f"  Batch {cat_idx+1+(batch_nums[0] if batch_nums else 0)}: {cat.upper()} ({len(design_list)} designs)")
        print(f"{'='*55}")

        batch_designs = []
        for spec in design_list:
            name = spec["name"]
            goal = spec["goal"]
            purpose = f"Interactive {cat.replace('-',' ')} visualization and analysis tool"
            tags = spec["tags"] + [cat]
            name_slug = safe_fn(name)

            nodes = generate_nodes(cat, name_slug)
            edges = make_edges()
            design = save_design(name, goal, purpose, nodes, edges, tags)
            batch_designs.append(design)

            # Write bible ref
            write_bible_ref(design, cat)

        # Write batch to designs.json
        existing.extend(batch_designs)
        with open(DESIGNS_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
        
        print(f"  ✅ Generated {len(batch_designs)} designs, wrote to {DESIGNS_FILE}")
        print(f"  📄 Created bible refs in {BIBLE_BASE}/{bible_section}")

        # Test through Davinci GUI pipeline
        print(f"\n  Testing {len(batch_designs)} designs on Davinci Studio...")
        batch_passed = 0
        batch_failed = 0

        for i, design in enumerate(batch_designs):
            result = test_design_on_davinci(design, cat)
            status = "✅" if result["passed"] else "❌"
            rsn = f" ({result.get('reason','')})" if not result["passed"] else ""
            if verbose:
                print(f"    [{i+1}/{len(batch_designs)}] {status} {result['name']}: {result.get('widgets',0)}/{result.get('expected',8)} widgets{rsn}")
            
            if result["passed"]:
                batch_passed += 1
            else:
                batch_failed += 1
            total_tested += 1
            total_widgets += result.get("widgets", 0)

        total_passed += batch_passed
        total_new += len(batch_designs)

        print(f"  → Batch result: {batch_passed}/{len(batch_designs)} passed, {batch_failed} failed")

        # Clear builds after batch
        canvas_cleanup()
        clear_builds()

    # Grand summary
    print(f"\n{'='*55}")
    print(f"  🏁 PIPELINE COMPLETE")
    print(f"{'='*55}")
    print(f"  New designs created: {total_new}")
    print(f"  Total in designs.json: {len(existing)}")
    print(f"  Tested: {total_tested}")
    print(f"  Passed: {total_passed}")
    print(f"  Widgets verified: {total_widgets}")
    if total_tested > 0:
        print(f"  Success rate: {total_passed/total_tested*100:.1f}%")

    # Record grand summary
    record_test("grand_summary", "all", True, total_widgets,
                f"Pipeline: {total_new} designs, {total_passed}/{total_tested} tests passed")

    return total_new, total_passed, total_tested


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Master Design Pipeline v2")
    parser.add_argument("--all", action="store_true", help="Process all categories")
    parser.add_argument("--batch", type=int, nargs="+", choices=range(1,11),
                        help="Batch numbers to process (1-10)")
    parser.add_argument("--limit", type=int, help="Limit designs per category")
    parser.add_argument("--quick", action="store_true", help="Quick: 5 per category")
    parser.add_argument("--status", action="store_true", help="Check services only")
    parser.add_argument("--count", action="store_true", help="Count designs in spec")
    args = parser.parse_args()

    if args.status:
        d = api_get(f"{DAVINCI_API}/api/status")
        a = api_get(f"{ARCHITECT_API}/api/auto-learn/status")
        print(f"\nDavinci Studio: {'✅' if d.get('status')=='ok' else '❌'} widgets={d.get('widget_count',0)}")
        print(f"Architect Backend: {'✅' if a.get('success') else '❌'} captured={a.get('capturedCount',0)}")
        sys.exit(0)

    if args.count:
        specs = json.load(open(SPECS_FILE))
        total = sum(len(c["designs"]) for c in specs["categories"].values())
        print(f"\nDesigns in spec file: {total}")
        for cat, cdata in specs["categories"].items():
            print(f"  {cat}: {len(cdata['designs'])} designs")
        sys.exit(0)

    if not (args.all or args.batch):
        print("⚠️  Use --all, --batch N, or --quick")
        sys.exit(1)

    limit = 5 if args.quick else args.limit
    run_pipeline(batch_nums=args.batch, limit_per_category=limit, verbose=True)
