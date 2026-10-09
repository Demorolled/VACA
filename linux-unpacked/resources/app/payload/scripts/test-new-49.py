#!/usr/bin/env python3
"""Test the 49 newest designs through Davinci GUI pipeline."""
import json, os, sys, time, urllib.request, urllib.error

DAVINCI = "http://localhost:8000"
DESIGNS_FILE = "data/designs.json"

DAVINCI_CATEGORIES = {
    "fundamentals":"01-fundamentals","games":"02-games","desktop":"03-desktop-apps",
    "systems":"05-systems-programming","database":"06-databases","mathematics":"13-math",
    "specialized":"20-specialized-computing","data-engineering":"27-data-engineering",
    "devops":"33-devops-sre-tooling","search":"36-search-recs-personalization"
}

WIDGET_GROUPS = {
    "fundamentals":[("display","Visualization","main"),("button","Analyze","main"),("input","Config","main"),("display","Status","statusbar"),("button","Export","bottom")],
    "games":[("display","Game Canvas","main"),("button","Move","topbar"),("display","Score","topbar"),("slider","Difficulty","sidebar"),("button","Reset","bottom")],
    "desktop":[("button","New","topbar"),("display","List View","main"),("input","Search","sidebar"),("toggle","Settings","sidebar"),("display","Detail","main")],
    "systems":[("display","Metrics","main"),("button","Start","topbar"),("toggle","Monitor","sidebar"),("display","Logs","bottom"),("slider","Threshold","sidebar")],
    "database":[("display","Query Result","main"),("input","SQL Input","topbar"),("button","Execute","topbar"),("display","Schema","sidebar"),("button","Export","bottom")],
    "mathematics":[("display","Plot","main"),("input","Parameters","sidebar"),("button","Compute","topbar"),("display","Data Table","bottom"),("slider","Range","sidebar")],
    "specialized":[("display","Simulation","main"),("slider","Parameter","sidebar"),("button","Run","topbar"),("display","Output","bottom"),("toggle","Mode","sidebar")],
    "data-engineering":[("display","Pipeline DAG","main"),("button","Run","topbar"),("display","Metrics","sidebar"),("input","Config","topbar"),("toggle","Auto-Sync","sidebar")],
    "devops":[("display","Dashboard","main"),("toggle","Auto-Refresh","topbar"),("display","Alerts","sidebar"),("button","Action","bottom"),("slider","Threshold","sidebar")],
    "search":[("input","Query","topbar"),("display","Results","main"),("slider","Relevance","sidebar"),("toggle","Filters","sidebar"),("display","Stats","bottom")]
}

def infer_category(tags, name, goal):
    tag = (tags or [None])[0]
    if tag in DAVINCI_CATEGORIES:
        return tag
    for k in DAVINCI_CATEGORIES:
        if k in name.lower()[:20] or k in goal.lower()[:80]:
            return k
    return "fundamentals"

def api_post(url, data=None):
    try:
        body = json.dumps(data).encode() if data else b'{}'
        req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  [warn] {url}: {str(e)[:80]}")
        return None

def api_get(url):
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  [warn] {url}: {str(e)[:80]}")
        return None

def gen_widgets(cat, idx, name):
    tmpl = WIDGET_GROUPS.get(cat, WIDGET_GROUPS["fundamentals"])
    widgets = []
    for i,(wt, wl, zone) in enumerate(tmpl):
        widgets.append({
            "id": f"w_{idx}_{i}", "type": wt, "label": f"{wl}",
            "x": 30 + i*120, "y": 30 + (i//3)*60,
            "width": 100, "height": 40,
            "config": {"text": wl, "action": f"{wl.lower()}_{name[:12].lower().replace(' ', '_')}"},
            "archBindings": {"nodeId": f"saved_{i}", "action": wl.lower()}
        })
    return widgets

def test_new_designs():
    with open(DESIGNS_FILE) as f: designs = json.load(f)
    existing_count = len(designs)
    # Test only the last 55 designs (newly added supplemental)
    to_test = designs[-55:]
    
    passed = 0
    failed = 0
    results = []
    
    print(f"Testing {len(to_test)} newest designs through Davinci GUI pipeline...\n")
    
    for d in to_test:
        name = d.get("name", "Unnamed")
        tags = d.get("tags", [])
        goal = d.get("goal", "")
        cat = infer_category(tags, name, goal)
        idx = to_test.index(d)
        
        widgets = gen_widgets(cat, idx, name)
        
        # Push build via bridge API (using the correct field names from v3 pipeline)
        arch_nodes = [{"id": n.get("id",""), "label": n.get("label","Node"),
            "type": n.get("type","logic"), "description": n.get("description","")}
            for n in d.get("nodes",[])]
        ui_funcs = [{"id": w["id"], "label": w["label"], "type": w["type"],
            "description": f"Widget for {goal}",
            "defaultAction": w["archBindings"].get("onClick","") or w["archBindings"].get("onChange",""),
            "category": "utility"} for w in widgets]
        arch_binds = [{"widgetId": w["id"], "widgetLabel": w["label"],
            "nodeId": w.get("linkedNodeId",""),
            "bindings": {k:v for k,v in w["archBindings"].items() if v}}
            for w in widgets if any(w["archBindings"].values())]
        build = {"appName": name, "goal": goal, "nodeCount": len(arch_nodes),
            "widgetCount": len(widgets), "architectNodes": arch_nodes,
            "uiFunctions": ui_funcs, "placedWidgets": widgets,
            "archBindings": arch_binds}
        push_resp = api_post(f"{DAVINCI}/api/bridge/builds", build)
        
        if push_resp and push_resp.get("received"):
            build_id = push_resp.get("build_id", d["id"])
            # Verify build in list
            builds_data = api_get(f"{DAVINCI}/api/bridge/builds")
            build_list = builds_data.get("builds", []) if isinstance(builds_data, dict) else (builds_data or [])
            received = any(b.get("id") == build_id for b in build_list)
            if received:
                # Apply build to canvas
                apply_resp = api_post(f"{DAVINCI}/api/bridge/builds/{build_id}/apply")
                if apply_resp:
                    # Verify widgets on canvas
                    canvas = api_get(f"{DAVINCI}/api/widgets")
                    if canvas is not None:
                        cw = canvas.get("widgets", canvas if isinstance(canvas, list) else [])
                        if len(cw) >= 2:
                            passed += 1
                            results.append(f"  ✅ {name:45s} | {len(cw)} widgets on canvas")
                        else:
                            failed += 1
                            results.append(f"  ⚠️ {name:45s} | only {len(cw)} widgets on canvas")
                    else:
                        failed += 1
                        results.append(f"  ⚠️ {name:45s} | widgets fetch failed")
                else:
                    failed += 1
                    results.append(f"  ⚠️ {name:45s} | apply failed")
            else:
                failed += 1
                results.append(f"  ⚠️ {name:45s} | build not in list")
        else:
            failed += 1
            results.append(f"  ⚠️ {name:45s} | bridge push failed")
        
        time.sleep(0.1)
    
    print(f"\nResults ({len(to_test)} designs):")
    for r in results:
        print(r)
    
    print(f"\n{'='*60}")
    print(f"Passed: {passed}/{len(to_test)} | Failed: {failed}")
    
    # Cleanup
    print("\nCleaning up builds...")
    api_post(f"{DAVINCI}/api/bridge/builds/clear")
    try:
        req = urllib.request.Request(f"{DAVINCI}/api/widgets/batch", data=json.dumps({"widgets": []}).encode(), headers={"Content-Type":"application/json"}, method="PUT")
        urllib.request.urlopen(req, timeout=5)
    except:
        pass
    
    # Record to auto-learn
    try:
        auto = {"type":"design_test_batch","content":f"Tested {len(to_test)} supplemental designs reaching 807 total","metadata":{"passed":passed,"failed":failed,"total":807}}
        req = urllib.request.Request("http://localhost:3001/api/auto-learn/record", data=json.dumps(auto).encode(), headers={"Content-Type":"application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5)
        print("✅ Auto-learn recorded")
    except:
        print("⚠️ Auto-learn record skipped")
    
    return failed == 0

if __name__ == "__main__":
    success = test_new_designs()
    sys.exit(0 if success else 1)
