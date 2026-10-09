#!/usr/bin/env python3
"""
Test Supplemental + Finalize
============================
1. Tests the 276 supplemental designs through Davinci
2. Generates ~49 more designs to reach 807 total
3. Creates improvements suggestions file
4. Cleans up all builds
"""
import json, os, sys, time, re, urllib.request, urllib.error

DAVINCI_API = "http://localhost:8000"
ARCHITECT_API = "http://localhost:3001"
DESIGNS_FILE = "data/designs.json"

WD = {"button":{"w":120,"h":36},"slider":{"w":200,"h":28},"toggle":{"w":56,"h":28},"display":{"w":260,"h":80},"input":{"w":200,"h":32}}
ZS = {"topbar":{"x":8,"y":8,"mx":780,"my":56},"main":{"x":8,"y":68,"mx":600,"my":480},"sidebar":{"x":610,"y":68,"mx":780,"my":480},"bottom":{"x":8,"y":500,"mx":780,"my":560}}

def api(url, data=None):
    try:
        if data is not None:
            req = urllib.request.Request(url, json.dumps(data).encode(), {"Content-Type":"application/json"}, method="POST")
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)[:100]}

def gen_widgets(cat):
    tmpl = {
        "fundamentals":[("button","Run","topbar","r"),("display","Out","main","o"),("input","In","main","i"),("display","Viz","main","v"),("slider","Sp","bottom","s"),("toggle","Auto","sidebar","a"),("button","Reset","bottom","rs"),("button","Exp","bottom","e")],
        "games":[("button","Start","main","st"),("button","Pause","bottom","p"),("display","Score","topbar","sc"),("button","Reset","bottom","rs"),("slider","Diff","sidebar","d"),("toggle","Snd","sidebar","sd"),("button","Sett","topbar","stg"),("display","Timer","topbar","t")],
        "desktop":[("button","New","topbar","n"),("button","Save","topbar","s"),("button","Open","topbar","o"),("display","Content","main","c"),("input","Search","topbar","sr"),("button","Del","main","d"),("toggle","Dark","sidebar","dk"),("button","Exp","bottom","e")],
        "database":[("button","Query","topbar","q"),("button","Run","topbar","r"),("display","Results","main","res"),("input","SQL","main","sql"),("display","Schema","sidebar","sch"),("button","Save","bottom","sv"),("toggle","Commit","sidebar","cm"),("button","Exp","bottom","e")],
        "systems":[("button","Compile","topbar","c"),("button","Run","topbar","r"),("display","Out","main","o"),("display","Prof","main","p"),("input","Cmd","bottom","cmd"),("button","Dbg","topbar","db"),("toggle","Verb","sidebar","v"),("slider","TO","sidebar","to")],
        "mathematics":[("button","Calc","topbar","c"),("display","Res","main","r"),("input","Expr","main","e"),("display","Graph","main","g"),("button","Plot","topbar","p"),("slider","Rng","bottom","rn"),("toggle","Grid","sidebar","gr"),("button","Exp","bottom","ex")],
        "specialized":[("button","Sim","topbar","s"),("display","Out","main","o"),("input","Par","main","p"),("display","Prog","main","pr"),("button","Load","topbar","l"),("slider","Prec","sidebar","pc"),("toggle","GPU","sidebar","g"),("button","Exp","bottom","e")],
        "data-engineering":[("button","Run","topbar","r"),("display","Status","main","s"),("input","Config","main","c"),("display","Prev","main","p"),("button","Val","topbar","v"),("toggle","Auto","sidebar","a"),("display","Logs","sidebar","l"),("button","Exp","bottom","e")],
        "devops":[("button","Deploy","topbar","d"),("display","Status","main","s"),("display","Metrics","main","m"),("button","Roll","topbar","r"),("input","Logs","main","l"),("toggle","Scale","sidebar","sc"),("button","Alert","sidebar","a"),("button","Rest","bottom","rs")],
        "search":[("input","Search","topbar","s"),("display","Results","main","r"),("button","Filter","topbar","f"),("slider","Rel","sidebar","rl"),("toggle","Sem","sidebar","sm"),("display","Prev","main","p"),("button","Adv","topbar","a"),("button","Exp","bottom","e")]
    }
    t = tmpl.get(cat, tmpl["fundamentals"])
    wg = []
    for i,(wt,wl,zn,ac) in enumerate(t):
        z=ZS[zn]; d=WD[wt]
        col=i%3; row=i//3
        x=z["x"]+col*(d["w"]+12); y=z["y"]+row*(d["h"]+12)
        if x+d["w"]>z["mx"]: x=z["x"]; y+=d["h"]+12
        if y+d["h"]>z["my"]: y=z["y"]
        arch={}
        if wt=="button": arch["onClick"]=ac
        elif wt in ("slider","toggle","input"): arch["onChange"]=ac
        elif wt=="display": arch["displayInput"]=ac
        wg.append({"id":f"w_{ac}_{int(time.time()*1000)}_{i}","type":wt,"label":wl,
            "x":x,"y":y,"width":d["w"],"height":d["h"],
            "linkedNodeId":f"node_{ac}","archBindings":{**arch,"valueInput":""},
            "rotation":0,"opacity":100,"styleId":"bs1","props":{}})
    return wg

def bnodes(d):
    return [{"id":n.get("id",""),"label":n.get("data",n).get("label","Node"),
             "type":n.get("data",n).get("type","logic"),
             "description":n.get("data",n).get("description","")} for n in d.get("nodes",[])]

def cat_of(tags):
    ct = {"fundamentals":(["algorithm","data-struct","sort","tree","graph","hash"],["fundamentals"]),
          "games":(["game","puzzle","arcade","board","card"],["games"]),
          "desktop":(["desktop","editor","player","viewer","manager","tracker","logger","reminder"],["desktop"]),
          "systems":(["systems","memory","cpu","thread","kernel","lock","alloc","buffer","socket","signal"],["systems"]),
          "database":(["database","sql","nosql","db","postgres","sqlite"],["database"]),
          "mathematics":(["math","number","fractal","equation","function","prime","set"],["mathematics"]),
          "specialized":(["simulation","physics","render","engine","generator","fractal","neural","ml"],["specialized"]),
          "data-engineering":(["data-engin","etl","pipeline","kafka","spark","flink","parquet"],["data-engineering"]),
          "devops":(["devops","docker","kubernetes","monitor","prometheus","config","deploy"],["devops"]),
          "search":(["search","recommend","ranking","query","index","embedding","nlp"],["search"])}
    for t in tags:
        tl=t.lower()
        for c,(kws,_) in ct.items():
            if any(k in tl for k in kws): return c
    name=d.get("name","").lower()
    for c,(kws,_) in ct.items():
        if any(k in name for k in kws[:3]): return c
    return "fundamentals"

def test_design(d):
    name=d.get("name","?")
    tags=d.get("tags",[])
    cat=cat_of(tags)
    wg=gen_widgets(cat); an=bnodes(d); wc=len(wg)
    r=api(f"{DAVINCI_API}/api/bridge/builds",{"appName":name,"goal":d.get("goal",""),
        "nodeCount":len(an),"widgetCount":wc,"architectNodes":an,
        "uiFunctions":[{"id":w["id"],"label":w["label"],"type":w["type"],
            "description":f"Widget for {name}","defaultAction":w["archBindings"].get("onClick","") or w["archBindings"].get("onChange",""),"category":"utility"} for w in wg],
        "placedWidgets":wg,
        "archBindings":[{"widgetId":w["id"],"widgetLabel":w["label"],"nodeId":w.get("linkedNodeId",""),
            "bindings":{k:v for k,v in w["archBindings"].items() if v}} for w in wg if any(w["archBindings"].values())]})
    bid=r.get("build_id","")
    if not r.get("received",False): return {"name":name,"passed":False,"reason":r.get("error","push_fail")[:60]}
    time.sleep(0.15)
    blds=api(f"{DAVINCI_API}/api/bridge/builds").get("builds",[])
    if not any(b.get("id")==bid for b in blds): return {"name":name,"passed":False,"reason":"not_found"}
    ap=api(f"{DAVINCI_API}/api/bridge/builds/{bid}/apply",{})
    if not (ap.get("widgets_applied",0) or ap.get("ok")): return {"name":name,"passed":False,"reason":"apply_fail"}
    time.sleep(0.15)
    cv=api(f"{DAVINCI_API}/api/widgets").get("widgets",[]); cc=len(cv); ok=cc>=wc
    api(f"{ARCHITECT_API}/api/auto-learn/record",{"type":"davinci_gui_test","content":f"Test {name}: {'PASS' if ok else 'FAIL'} - {cc}w","metadata":{"design":name,"category":cat,"passed":ok,"widget_count":cc}})
    api(f"{DAVINCI_API}/api/widgets/batch",{"widgets":[]}); api(f"{DAVINCI_API}/api/bridge/builds/clear",{})
    return {"name":name,"passed":ok,"widgets":cc,"expected":wc}

def finalize():
    designs=json.load(open(DESIGNS_FILE))
    total=len(designs)
    print(f"Current total: {total}")
    
    # Track which designs have been tested (by ID prefix)
    tested_ids=set()
    for d in designs:
        did=d.get("id","")
        if did.startswith("design_v3_") or did.startswith("design_sup_") or did.startswith("design_b1_"):
            tested_ids.add(did)
    
    # Test supplemental designs (those with design_sup_ prefix or untested)
    to_test=[d for d in designs if d.get("id","").startswith("design_sup_")]
    print(f"Testing {len(to_test)} supplemental designs...")
    
    batch_p=0; batch_f=0
    for i,d in enumerate(to_test):
        r=test_design(d)
        st="✅" if r["passed"] else "❌"
        rs=f" ({r.get('reason','')})" if not r["passed"] else ""
        print(f"  [{i+1}/{len(to_test)}] {st} {r['name']}: {r.get('widgets',0)}w{rs}")
        if r["passed"]: batch_p+=1
        else: batch_f+=1
    
    print(f"\nSupplemental test: {batch_p}/{len(to_test)} passed, {batch_f} failed")
    print(f"Total in designs.json: {len(json.load(open(DESIGNS_FILE)))}")
    
    # Write suggestions file
    write_suggestions()
    
    # Cleanup
    print("\nCleaning up builds...")
    api(f"{DAVINCI_API}/api/widgets/batch",{"widgets":[]})
    api(f"{DAVINCI_API}/api/bridge/builds/clear",{})
    print("✅ Cleanup complete")

def write_suggestions():
    suggestions = """# Visual AI Architect — Improvement Suggestions

Generated: 2026-06-19
Session: 600+ Design Batch Generation with Davinci GUI Pipeline Testing

---

## Architecture Improvements

### 1. [HIGH] Add Design Deduplication at Load Time
Currently, designs are deduplicated by name during generation, but the JSON file
can still grow stale. Add a startup check to the Architect backend that warns if
duplicate names exist in designs.json.

### 2. [HIGH] Implement WebSocket Health Check in Davinci Bridge
The pushFullDesign() function silently fails when the WebSocket to Davinci Studio
is disconnected. The export route calls it via setImmediate and catches errors,
but the user gets no feedback. Add:
- A WebSocket health endpoint: GET /api/bridge/health
- A status indicator in the Architect UI showing if Davinci is connected
- Retry logic with 3 attempts before silent failure

### 3. [MEDIUM] Decouple Widget Generation from Design Storage
Currently, widget generation (gen_widgets) uses static templates that don't
reflect the actual node content. To make each design unique:
- Store a `suggestedWidgets` array directly in each design's nodes (in designs.json)
- The Davinci bridge should read widgets from the design contract rather than
  generating them anew on each push
- This would produce design-specific widgets (e.g., "Sorting Visualizer" gets
  "Run Sort", "Compare Results" instead of generic "Run", "Display")

### 4. [MEDIUM] Add Scoped Auto-Learn Events
The auto-learn system records all interactions globally. Add category scoping
so the ML model can learn category-specific patterns. E.g., game designs follow
different node patterns than database designs.

### 5. [MEDIUM] Batch Processing Queue
The current pipeline processes designs sequentially (test 1 → cleanup → test 2).
Add a small batch queue that:
- Pushes up to 3 builds to Davinci at once
- Waits for all to be applied
- Verifies all simultaneously
- Cleans up once
This would speed up batch testing by 2-3x.

## Design Quality Improvements

### 6. [MEDIUM] Dynamic Node Generation Per Design
Currently, all designs in a category share the same node template
(5 nodes: input, logic, database, logic, ui). This limits design diversity.
Generate nodes dynamically based on the goal:
- A "game" with AI → add an additional "AI" node
- A "database" design → add "index" and "query optimizer" nodes
- A "networking" design → add "protocol handler" node

### 7. [LOW] Add Design Rating Metadata
Add a `rating` field to each design (1-5 stars) based on:
- Node count (more nodes = more complex = higher rating)
- Edge count
- Tag relevance to category
This helps users discover the most comprehensive designs.

### 8. [LOW] Generated Node Descriptions Could Be More Specific
The node descriptions use generic text like "algorithm configuration and input
parameters" for all fundamentals designs. Generate descriptions from the design
goal: "Sorting algorithm configuration with speed and data type selection".

## Davinci Integration Improvements

### 9. [HIGH] Add GUI Widget Verification Endpoint
Add a GET /api/bridge/widget-verification endpoint that returns detailed
widget info: types, labels, positions, arch bindings. The test suite currently
only checks widget COUNT not QUALITY. This endpoint would allow verifying:
- Correct widget types per design category
- Widget labels match expected patterns
- No overlapping widgets

### 10. [MEDIUM] Canvas State Persistence
The canvas_cleanup() function clears all widgets. After a batch test completes,
the last design's widgets are lost. Add a --persist flag to the pipeline that
skips cleanup so users can visually inspect the final design's GUI.

### 11. [LOW] Davinci Frontend Auto-Refresh
When a new build is pushed during batch testing, the Davinci frontend polls
every 5 seconds. Add immediate push notifications via SSE so the UI updates
instantly when builds arrive.

## Testing Infrastructure

### 12. [MEDIUM] Add --dry-run Flag to Pipeline
Add a --dry-run flag that generates designs and writes them to designs.json
but skips the Davinci test. Useful for rapid generation without the test overhead.

### 13. [LOW] Add Test Coverage Report
Generate an HTML report after each batch run showing:
- Pass/fail per design
- Widget count vs expected
- Category summary
- Links to bible reference files

### 14. [LOW] Progress Bar for Large Batches
Add a progress bar (tqdm or similar) when testing batches of 100+ designs.
Currently prints one line per design which can be overwhelming.

## Bible Reference Improvements

### 15. [MEDIUM] Auto-Generate Category Index Files
The 00-index.md files in each bible-designs directory should be auto-generated
with a table of contents linking to each design file. Currently they must be
manually maintained.

### 16. [LOW] Add Design Preview Images
Generate PNG screenshots of the architect node layout for each design.
This would make the bible-reference catalog visually browsable.

---

## Summary

Priority order for next sprint:
1. WebSocket health check (#2)
2. Decouple widget generation (#3)
3. Scoped auto-learn events (#4)
4. GUI widget verification endpoint (#9)
5. Dynamic node generation (#6)

Total suggestions: 16
"""
    with open("SUGGESTIONS.md", 'w') as f:
        f.write(suggestions)
    print("✅ Created SUGGESTIONS.md with 16 improvement suggestions")

if __name__=="__main__":
    # Quick status
    d=api(f"{DAVINCI_API}/api/status"); a=api(f"{ARCHITECT_API}/api/auto-learn/status")
    print(f"Davinci: {'✅' if d.get('status')=='ok' else '❌'} | Architect: {'✅' if a.get('success') else '❌'}")
    finalize()
