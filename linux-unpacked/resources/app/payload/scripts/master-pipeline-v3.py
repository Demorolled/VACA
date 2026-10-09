#!/usr/bin/env python3
"""
Master Pipeline v3 (Fixed)
==========================
Fixed issues:
  - Expanded TAG_CATEGORY map with 100+ missing tags
  - Fixed batch numbering (no double +1)
  - os.urandom(4) for unique IDs
  - added dedup check (skip if name exists)
  - added --cleanup flag
  - added per-design node position offsets
  - specific purpose per design
  - better error handling in test pipeline

Usage:
  python3 scripts/master-pipeline-v3.py [--all] [--cleanup] [--quick N]
"""

import json, os, sys, time, re, math, hashlib, urllib.request, urllib.error
from datetime import datetime
from collections import OrderedDict

ARCHITECT_API = "http://localhost:3001"
DAVINCI_API = "http://localhost:8000"
SPECS_FILE = "data/design-specs-v2.json"
DESIGNS_FILE = "data/designs.json"
BIBLE_BASE = "bible-reference/00-app-designs"
NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

# ─── Expanded TAG_CATEGORY map (100+ entries) ──────────────────────────
TAG_CATEGORY = {
    # fundamentals
    "algorithms":"fundamentals","data-structures":"fundamentals","complexity":"fundamentals",
    "arrays":"fundamentals","linked-list":"fundamentals","binary":"fundamentals",
    "sorting":"fundamentals","searching":"fundamentals","recursion":"fundamentals",
    "backtracking":"fundamentals","dp":"fundamentals","dynamic-programming":"fundamentals",
    "greedy":"fundamentals","hash-table":"fundamentals","hashing":"fundamentals",
    "string":"fundamentals","stack":"fundamentals","queue":"fundamentals",
    "graph":"fundamentals","tree":"fundamentals","bst":"fundamentals",
    "geometry":"fundamentals","sliding-window":"fundamentals","two-pointer":"fundamentals",
    "divide-conquer":"fundamentals","cache":"fundamentals","lru":"fundamentals",
    "bloom-filter":"fundamentals","probabilistic":"fundamentals","skip-list":"fundamentals",
    "union-find":"fundamentals","disjoint-set":"fundamentals","segment-tree":"fundamentals",
    "range-query":"fundamentals","trees":"fundamentals","fenwick-tree":"fundamentals",
    "bit":"fundamentals","suffix-array":"fundamentals","pattern-matching":"fundamentals",
    "avl-tree":"fundamentals","balancing":"fundamentals","red-black-tree":"fundamentals",
    "splay-tree":"fundamentals","amortized":"fundamentals","treap":"fundamentals",
    "randomized":"fundamentals","b-tree":"fundamentals","balanced-tree":"fundamentals",
    "radix-sort":"fundamentals","non-comparison":"fundamentals","counting-sort":"fundamentals",
    "linear-time":"fundamentals","bucket-sort":"fundamentals","distribution":"fundamentals",
    "topological-sort":"fundamentals","dag":"fundamentals","strongly-connected":"fundamentals",
    "kosaraju":"fundamentals","mst":"fundamentals","kruskal":"fundamentals","prim":"fundamentals",
    "max-flow":"fundamentals","ford-fulkerson":"fundamentals","bipartite":"fundamentals",
    "matching":"fundamentals","tsp":"fundamentals","knapsack":"fundamentals",
    "optimization":"fundamentals","n-queens":"fundamentals","constraint":"fundamentals",
    "sudoku":"fundamentals","kmp":"fundamentals","rabin-karp":"fundamentals",
    "rolling-hash":"fundamentals","z-algorithm":"fundamentals","manacher":"fundamentals",
    "palindrome":"fundamentals","convex-hull":"fundamentals","graham-scan":"fundamentals",
    "two-pointer":"fundamentals","lru":"fundamentals","cache":"fundamentals",
    # games
    "game":"games","arcade":"games","puzzle":"games","card-game":"games",
    "classic":"games","platformer":"games","maze":"games","physics":"games",
    "bubble-shooter":"games","match-3":"games","casual":"games","flappy-bird":"games",
    "jump":"games","minesweeper":"games","logic":"games","word-search":"games",
    "vocabulary":"games","crossword":"games","word-game":"games","memory":"games",
    "hangman":"games","typing":"games","education":"games","speed":"games",
    "simon":"games","reaction":"games","whack-a-mole":"games","simulation":"games",
    "lunar-lander":"games","asteroids":"games","shooter":"games","space-invaders":"games",
    "pac-man":"games","frogger":"games","tetris-attack":"games","dr-mario":"games",
    "boulder-dash":"games","mining":"games","lode-runner":"games","candy-crush":"games",
    "breakout":"games","ball-physics":"games","pong":"games","multiplayer":"games",
    "snake":"games","tower-defense":"games","strategy":"games","tactical":"games",
    "generation":"games","pathfinding":"games","2048":"games","sliding":"games",
    "checkers":"games","board-game":"games","ai":"games","connect-four":"games",
    "minimax":"games",
    # desktop
    "desktop":"desktop","utility":"desktop","productivity":"desktop",
    "design":"desktop","editor":"desktop","dictionary":"desktop","reference":"desktop",
    "color-picker":"desktop","typography":"desktop","graphics":"desktop",
    "icon-editor":"desktop","svg-editor":"desktop","vector":"desktop",
    "unit-converter":"desktop","currency-converter":"desktop","finance":"desktop",
    "timer":"desktop","stopwatch":"desktop","world-clock":"desktop","timezone":"desktop",
    "recipe-manager":"desktop","lifestyle":"desktop","expense-tracker":"desktop",
    "budgeting":"desktop","habit-tracker":"desktop","self-improvement":"desktop",
    "workout-logger":"desktop","fitness":"desktop","health":"desktop","meal-planner":"desktop",
    "nutrition":"desktop","journal":"desktop","diary":"desktop","writing":"desktop",
    "flashcards":"desktop","study":"desktop","pomodoro":"desktop","mind-map":"desktop",
    "brainstorming":"desktop","whiteboard":"desktop","drawing":"desktop","collaboration":"desktop",
    "screen-ruler":"desktop","developer-tools":"desktop","qr-code":"desktop","encoding":"desktop",
    "barcode":"desktop","scanner":"desktop","pdf-merger":"desktop","document":"desktop",
    "ocr":"desktop","text-extraction":"desktop","file-renamer":"desktop","batch":"desktop",
    "duplicate-finder":"desktop","file-management":"desktop","cleanup":"desktop",
    "disk-analyzer":"desktop","storage":"desktop","audio-recorder":"desktop","recording":"desktop",
    "sound":"desktop","screen":"desktop",
    # systems
    "systems":"systems","low-level":"systems","concurrency":"systems","linux":"systems",
    "compiler":"systems","binary":"systems","memory":"systems","cpu":"systems",
    "networking":"systems","ipc":"systems","debugging":"systems","elf":"systems",
    "analyzer":"systems","pe":"systems","windows":"systems","hex-editor":"systems",
    "disassembler":"systems","x86":"systems","register-allocator":"systems",
    "instruction-scheduler":"systems","cache-simulator":"systems","branch-predictor":"systems",
    "pipeline":"systems","hazard":"systems","tlb":"systems","virtual-memory":"systems",
    "mmu":"systems","numa":"systems","memory-topology":"systems","performance":"systems",
    "copy-on-write":"systems","fork":"systems","memory-pool":"systems","allocator":"systems",
    "arena-allocator":"systems","lock-free":"systems","rwlock":"systems",
    "synchronization":"systems","barrier":"systems","work-stealing":"systems",
    "parallelism":"systems","coroutine":"systems","async":"systems","raw-socket":"systems",
    "packet":"systems","network-benchmark":"systems","tcp":"systems","udp":"systems",
    "unix-sockets":"systems","event-loop":"systems","reactor":"systems",
    "io-multiplexing":"systems","epoll":"systems","zero-copy":"systems","io":"systems",
    "mmap":"systems","memory-mapped":"systems","dns":"systems","http-parser":"systems",
    "protocol":"systems","parsing":"systems","ring-buffer":"systems","shared-memory":"systems",
    "posix":"systems","semaphore":"systems","stack":"systems","unwinding":"systems",
    # database
    "database":"database","sql":"database","nosql":"database","postgresql":"database",
    "redis":"database","mongodb":"database","lsm-tree":"database","compaction":"database",
    "wal":"database","write-ahead":"database","recovery":"database","buffer-pool":"database",
    "lock-manager":"database","transactions":"database","raft":"database","consensus":"database",
    "distributed":"database","paxos":"database","gossip":"database","membership":"database",
    "consistent-hashing":"database","sharding":"database","cuckoo-filter":"database",
    "hyperloglog":"database","cardinality":"database","count-min-sketch":"database",
    "frequency":"database","rocksdb":"database","configuration":"database",
    "sql-injection":"database","security":"database","normalization":"database",
    "schema-design":"database","json":"database","jsonb":"database","full-text-search":"database",
    "ranking":"database","plpgsql":"database","debugger":"database","postgis":"database",
    "gis":"database","spatial":"database","timescaledb":"database","time-series":"database",
    "connection-pool":"database","scalability":"database","query-plan":"database",
    # mathematics
    "mathematics":"mathematics","linear-algebra":"mathematics","calculus":"mathematics",
    "statistics":"mathematics","probability":"mathematics","numerical":"mathematics",
    "visualization":"mathematics","polynomial":"mathematics","algebra":"mathematics",
    "root-finding":"mathematics","trigonometry":"mathematics","matrix":"mathematics",
    "decomposition":"mathematics","eigenvalues":"mathematics","vector-space":"mathematics",
    "kernel":"mathematics","gram-schmidt":"mathematics","orthogonal":"mathematics",
    "least-squares":"mathematics","regression":"mathematics","interpolation":"mathematics",
    "spline":"mathematics","newton":"mathematics","numerical-integration":"mathematics",
    "monte-carlo":"mathematics","differentiation":"mathematics","series":"mathematics",
    "taylor":"mathematics","ode":"mathematics","phase-portrait":"mathematics",
    "differential-equations":"mathematics","pde":"mathematics","finite-difference":"mathematics",
    "fft":"mathematics","spectrum":"mathematics","signal":"mathematics","wavelet":"mathematics",
    "dwt":"mathematics","convolution":"mathematics","group-theory":"mathematics",
    "abstract-algebra":"mathematics","combinatorics":"mathematics","permutations":"mathematics",
    "counting":"mathematics","graph-coloring":"mathematics","game-theory":"mathematics",
    "nash-equilibrium":"mathematics","information-theory":"mathematics","entropy":"mathematics",
    "coding":"mathematics","markov-chain":"mathematics","bayesian":"mathematics",
    "inference":"mathematics","hypothesis-testing":"mathematics","p-value":"mathematics",
    "anova":"mathematics","variance":"mathematics","random":"mathematics","prng":"mathematics",
    "cellular-automata":"mathematics","l-system":"mathematics","fractal":"mathematics",
    "turtle":"mathematics","science":"mathematics",
    # specialized
    "specialized":"specialized","computation":"specialized","simulation":"specialized",
    "science":"specialized","graphics":"specialized","physics":"specialized",
    "robotics":"specialized","ml":"specialized","deep-learning":"specialized",
    "ray-tracing":"specialized","rendering":"specialized","rasterizer":"specialized",
    "3d":"specialized","noise":"specialized","procedural":"specialized",
    "physics-engine":"specialized","2d":"specialized","cloth-simulation":"specialized",
    "sph":"specialized","fluid":"specialized","particles":"specialized",
    "rigid-body":"specialized","soft-body":"specialized","deformation":"specialized",
    "inverse-kinematics":"specialized","animation":"specialized","pid-controller":"specialized",
    "control-systems":"specialized","kalman-filter":"specialized","estimation":"specialized",
    "control":"specialized","genetic-algorithm":"specialized","evolutionary":"specialized",
    "particle-swarm":"specialized","swarm":"specialized","simulated-annealing":"specialized",
    "metaheuristic":"specialized","ant-colony":"specialized","reinforcement-learning":"specialized",
    "q-learning":"specialized","neural-network":"specialized","decision-tree":"specialized",
    "classification":"specialized","k-means":"specialized","clustering":"specialized",
    "knn":"specialized","svm":"specialized","pca":"specialized","dimensionality-reduction":"specialized",
    "tsne":"specialized","naive-bayes":"specialized","logistic-regression":"specialized",
    "linear-regression":"specialized","gradient-descent":"specialized","backpropagation":"specialized",
    "cnn":"specialized","attention":"specialized","transformer":"specialized","lstm":"specialized",
    "rnn":"specialized",
    # data-engineering
    "data-engineering":"data-engineering","etl":"data-engineering","pipeline":"data-engineering",
    "data-quality":"data-engineering","analytics":"data-engineering","parquet":"data-engineering",
    "file-format":"data-engineering","avro":"data-engineering","serialization":"data-engineering",
    "orc":"data-engineering","benchmark":"data-engineering","delta-lake":"data-engineering",
    "lakehouse":"data-engineering","versioning":"data-engineering","iceberg":"data-engineering",
    "table-format":"data-engineering","hudi":"data-engineering","merge":"data-engineering",
    "spark":"data-engineering","flink":"data-engineering","streaming":"data-engineering",
    "kafka":"data-engineering","topic":"data-engineering","partition":"data-engineering",
    "schema-registry":"data-engineering","compatibility":"data-engineering","dbt":"data-engineering",
    "transformation":"data-engineering","airflow":"data-engineering","scheduler":"data-engineering",
    "great-expectations":"data-engineering","testing":"data-engineering",
    "data-contract":"data-engineering","governance":"data-engineering","data-profiling":"data-engineering",
    "anomaly-detection":"data-engineering","data-diff":"data-engineering","comparison":"data-engineering",
    "s3":"data-engineering","select":"data-engineering","cloud":"data-engineering","glue":"data-engineering",
    "catalog":"data-engineering","aws":"data-engineering","external-table":"data-engineering",
    "hive":"data-engineering","monitoring":"data-engineering","alerts":"data-engineering",
    "sla":"data-engineering","cost-attribution":"data-engineering","finops":"data-engineering",
    # devops
    "devops":"devops","sre":"devops","monitoring":"devops","ci-cd":"devops",
    "docker":"devops","container":"devops","kubernetes":"devops","iac":"devops",
    "observability":"devops","dockerfile":"devops","docker-compose":"devops",
    "pod":"devops","spec":"devops","helm":"devops","chart":"devops","kustomize":"devops",
    "overlay":"devops","ingress":"devops","pvc":"devops","rbac":"devops",
    "network-policy":"devops","hpa":"devops","autoscaling":"devops","promql":"devops",
    "prometheus":"devops","metrics":"devops","grafana":"devops","dashboard":"devops",
    "alertmanager":"devops","notification":"devops","loki":"devops","logql":"devops",
    "logging":"devops","tempo":"devops","tracing":"devops","traceql":"devops",
    "opentelemetry":"devops","instrumentation":"devops","jaeger":"devops","rules":"devops",
    "alerting":"devops","node-exporter":"devops","blackbox":"devops","probe":"devops",
    "crossplane":"devops","composition":"devops","pulumi":"devops","typescript":"devops",
    "terragrunt":"devops","terraform":"devops","ansible":"devops","playbook":"devops",
    "configuration-management":"devops","vault":"devops","infrastructure":"devops",
    # search
    "search":"search","recommendation":"search","personalization":"search",
    "ranking":"search","nlp":"search","embeddings":"search","information-retrieval":"search",
    "tf-idf":"search","inverted-index":"search","indexing":"search","bm25":"search",
    "query-expansion":"search","spell-checker":"search","edit-distance":"search",
    "phonetic":"search","soundex":"search","metaphone":"search","faceted-search":"search",
    "navigation":"search","filtering":"search","geospatial":"search","geo":"search",
    "distance":"search","did-you-mean":"search","suggestion":"search","correction":"search",
    "snippet":"search","highlighting":"search","summarization":"search","text":"search",
    "keyword-extraction":"search","ner":"search","named-entity":"search","sentiment":"search",
    "topic-modeling":"search","lda":"search","word2vec":"search","text-classification":"search",
    "scatter-gather":"search","evaluation":"search","session-based":"search","sequential":"search",
    "collaborative-filtering":"search","cf":"search","matrix-factorization":"search",
    "als":"search","bandit":"search","exploration":"search","exploitation":"search"
}

CATEGORY_LABELS = OrderedDict([
    ("fundamentals","01-fundamentals"), ("games","02-games"), ("desktop","03-desktop-apps"),
    ("systems","05-systems-programming"), ("database","06-databases"),
    ("mathematics","13-math"), ("specialized","20-specialized-computing"),
    ("data-engineering","27-data-engineering"), ("devops","33-devops-sre-tooling"),
    ("search","36-search-recs-personalization")
])
CATEGORY_LIST = list(CATEGORY_LABELS.keys())

# ─── Node Templates ──────────────────────────────────────────────────
NODE_TEMPLATES = {
    "fundamentals": [
        ("input","Data Input","algorithm configuration and input parameters","typescript",50,50),
        ("logic","Core Algorithm","algorithm implementation with step tracking","python",250,50),
        ("database","Results Store","computation results and state data","typescript",50,250),
        ("logic","Analysis Engine","result analysis and performance metrics","python",450,50),
        ("ui","Visualization","interactive charts and data display","typescript",450,250)
    ],
    "games": [
        ("input","Game Controller","keyboard/mouse/touch input handling","typescript",50,50),
        ("logic","Game Engine","core game loop with physics and scoring","typescript",250,50),
        ("database","Game State","player stats and save data","typescript",50,250),
        ("logic","AI Opponent","computer opponent with difficulty levels","typescript",450,50),
        ("ui","Render View","game canvas and HUD rendering","typescript",450,250)
    ],
    "desktop": [
        ("input","User Input","file ops, interactions, configuration","typescript",50,50),
        ("logic","Core Logic","business logic and data processing","typescript",250,50),
        ("database","Data Store","app data, preferences, content","sqlite",50,250),
        ("logic","Search & Filter","search, sort, and filter operations","typescript",450,50),
        ("ui","User Interface","desktop UI panels and controls","typescript",450,250)
    ],
    "systems": [
        ("input","System Config","target selection and parameters","typescript",50,50),
        ("logic","Core Engine","systems-level logic and analysis","cpp",250,50),
        ("database","Data Collection","metrics, traces, profiling data","typescript",50,250),
        ("logic","Analysis Module","pattern detection and reports","python",450,50),
        ("ui","Dashboard View","visualizations and state display","typescript",450,250)
    ],
    "database": [
        ("input","Query/Config","SQL queries and schema input","typescript",50,50),
        ("logic","Database Engine","query processing and storage ops","typescript",250,50),
        ("database","Data Store","tables, indexes, metadata","sqlite",50,250),
        ("logic","Analysis & Optimization","performance analysis and advice","python",450,50),
        ("ui","Results Display","query results and execution plans","typescript",450,250)
    ],
    "mathematics": [
        ("input","Math Input","equations and parameters","typescript",50,50),
        ("logic","Math Engine","mathematical computation engine","python",250,50),
        ("database","Data Storage","results and reference data","typescript",50,250),
        ("logic","Analysis Module","error analysis and validation","python",450,50),
        ("ui","Visualization","graphs and interactive plots","typescript",450,250)
    ],
    "specialized": [
        ("input","Domain Input","domain-specific parameters","typescript",50,50),
        ("logic","Core Algorithm","specialized domain algorithm","python",250,50),
        ("database","Data Store","simulation data and references","typescript",50,250),
        ("logic","Analysis Engine","validation and error computation","python",450,50),
        ("ui","Visualization","domain-specific 3D/plots","typescript",450,250)
    ],
    "data-engineering": [
        ("input","Pipeline Config","source/target config, format","typescript",50,50),
        ("logic","Data Processor","transform and validate data","python",250,50),
        ("database","Data Store","metadata, catalogs, logs","sqlite",50,250),
        ("logic","Orchestrator","workflow and scheduling logic","python",450,50),
        ("ui","Pipeline Dashboard","DAG view and metrics display","typescript",450,250)
    ],
    "devops": [
        ("input","Config Input","infrastructure config input","typescript",50,50),
        ("logic","Orchestrator","deployment and automation logic","python",250,50),
        ("database","State Store","infrastructure state and config","sqlite",50,250),
        ("logic","Analysis Engine","metrics and compliance analysis","python",450,50),
        ("ui","Ops Dashboard","dashboards and alert panels","typescript",450,250)
    ],
    "search": [
        ("input","Query Input","search query and user profile","typescript",50,50),
        ("logic","Search Engine","indexing, retrieval, ranking","python",250,50),
        ("database","Index & Data","index, profiles, interaction logs","sqlite",50,250),
        ("logic","Evaluation Module","relevance metrics and A/B testing","python",450,50),
        ("ui","Results Display","search results and recommendations","typescript",450,250)
    ]
}

def make_edges():
    return [{"source":"node_0","target":"node_1"},{"source":"node_1","target":"node_2"},
            {"source":"node_2","target":"node_3"},{"source":"node_3","target":"node_4"},
            {"source":"node_1","target":"node_4"}]

def generate_nodes(category, name_slug, idx):
    tmpl = NODE_TEMPLATES.get(category, NODE_TEMPLATES["fundamentals"])
    nodes = []
    offset = (hash(name_slug) % 30)  # Per-design position offset
    for i, (n_type, n_label, n_desc, n_lang, n_x, n_y) in enumerate(tmpl):
        nodes.append({
            "id": f"saved_{i}", "type": n_type,
            "label": n_label,
            "description": f"{n_desc} — {name_slug.replace('-',' ')}",
            "language": n_lang,
            "position": {"x": n_x + (idx % 3) * 40 + offset % 20, "y": n_y + (idx // 3) * 20}
        })
    return nodes

def save_design(name, goal, purpose, nodes, edges, tags):
    return {
        "id": f"design_v3_{int(time.time()*1000)}_{os.urandom(4).hex()}",
        "name": name, "goal": goal, "purpose": purpose,
        "targetOS": "linux", "nodes": nodes, "edges": edges,
        "roadmap": f"App: {name}\nTarget: linux\nNodes: {len(nodes)}\nConnections: {len(edges)}",
        "createdAt": NOW, "updatedAt": NOW, "source": "local",
        "tags": tags[:5]
    }

def infer_category(tags):
    for t in tags:
        t = t.lower().strip()
        if t in TAG_CATEGORY:
            return TAG_CATEGORY[t]
    return "fundamentals"

def safe_fn(name):
    s = name.lower().replace(' ','-').replace('/','-').replace('\\','-')
    s = re.sub(r'[^a-z0-9-]','',s); s = re.sub(r'-+','-',s).strip('-')
    return s[:60]

def write_bible_ref(design, cat_label):
    bible_dir = os.path.join(BIBLE_BASE, cat_label)
    os.makedirs(bible_dir, exist_ok=True)
    fn = f"{safe_fn(design['name'])}.md"
    path = os.path.join(bible_dir, fn)
    nodes_s = '\n'.join([f"  - **{n['label']}** ({n['type']}): {n['description']}" for n in design['nodes']])
    edges_s = '\n'.join([f"  - `{e['source']}` → `{e['target']}`" for e in design['edges'][:5]])
    content = f"# {design['name']}\n\n**Design ID:** `{design['id']}` | **Category:** {cat_label}\n\n## Goal\n{design['goal']}\n\n## Purpose\n{design.get('purpose','')}\n\n## Nodes\n{nodes_s}\n\n## Edges\n{edges_s}\n\n## Tags\n{', '.join(design['tags'][:5])}\n\n---\n*Design generated for Visual AI Architect | {NOW}*\n"
    with open(path,'w') as f: f.write(content)
    return path

# ─── Davinci GUI Pipeline ──────────────────────────────────────────
def api_post(url, data):
    try:
        req = urllib.request.Request(url, json.dumps(data).encode(), {"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode())
    except Exception as e: return {"error": str(e)[:120]}

def api_get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r: return json.loads(r.read().decode())
    except: return {}

WD = {"button":{"w":120,"h":36},"slider":{"w":200,"h":28},"toggle":{"w":56,"h":28},"display":{"w":260,"h":80},"input":{"w":200,"h":32}}
ZS = {"topbar":{"x":8,"y":8,"mx":780,"my":56},"main":{"x":8,"y":68,"mx":600,"my":480},"sidebar":{"x":610,"y":68,"mx":780,"my":480},"bottom":{"x":8,"y":500,"mx":780,"my":560}}

CW = {
    "fundamentals":[("button","Run","topbar","run"),("display","Output","main","show"),("input","Data","main","input"),("display","Viz","main","viz"),("slider","Speed","bottom","speed"),("toggle","Auto","sidebar","auto"),("button","Reset","bottom","reset"),("button","Export","bottom","export")],
    "games":[("button","Start","main","start"),("button","Pause","bottom","pause"),("display","Score","topbar","score"),("button","Restart","bottom","restart"),("slider","Difficulty","sidebar","diff"),("toggle","Sound","sidebar","sound"),("button","Settings","topbar","settings"),("display","Timer","topbar","timer")],
    "desktop":[("button","New","topbar","new"),("button","Save","topbar","save"),("button","Open","topbar","open"),("display","Content","main","content"),("input","Search","topbar","search"),("button","Delete","main","delete"),("toggle","Dark","sidebar","dark"),("button","Export","bottom","export")],
    "database":[("button","Query","topbar","query"),("button","Run","topbar","run"),("display","Results","main","results"),("input","SQL","main","sql"),("display","Schema","sidebar","schema"),("button","Save","bottom","save"),("toggle","Commit","sidebar","commit"),("button","Export","bottom","export")],
    "systems":[("button","Compile","topbar","compile"),("button","Run","topbar","run"),("display","Output","main","output"),("display","Profile","main","profile"),("input","Cmd","bottom","cmd"),("button","Debug","topbar","debug"),("toggle","Verbose","sidebar","verbose"),("slider","Timeout","sidebar","timeout")],
    "mathematics":[("button","Calc","topbar","calc"),("display","Result","main","result"),("input","Expr","main","expr"),("display","Graph","main","graph"),("button","Plot","topbar","plot"),("slider","Range","bottom","range"),("toggle","Grid","sidebar","grid"),("button","Export","bottom","export")],
    "specialized":[("button","Simulate","topbar","sim"),("display","Output","main","output"),("input","Params","main","params"),("display","Progress","main","progress"),("button","Load","topbar","load"),("slider","Precision","sidebar","precision"),("toggle","GPU","sidebar","gpu"),("button","Export","bottom","export")],
    "data-engineering":[("button","Run","topbar","run"),("display","Status","main","status"),("input","Config","main","config"),("display","Preview","main","preview"),("button","Validate","topbar","validate"),("toggle","Auto","sidebar","auto"),("display","Logs","sidebar","logs"),("button","Export","bottom","export")],
    "devops":[("button","Deploy","topbar","deploy"),("display","Status","main","status"),("display","Metrics","main","metrics"),("button","Rollback","topbar","rollback"),("input","Logs","main","logs"),("toggle","Scale","sidebar","scale"),("button","Alert Config","sidebar","alerts"),("button","Restart","bottom","restart")],
    "search":[("input","Search","topbar","search"),("display","Results","main","results"),("button","Filter","topbar","filter"),("slider","Rel","sidebar","rel"),("toggle","Semantic","sidebar","semantic"),("display","Preview","main","preview"),("button","Advanced","topbar","adv"),("button","Export","bottom","export")]
}

def gen_widgets(goal, category):
    tmpl = CW.get(category, CW["fundamentals"])
    wg = []; occ = []
    for i,(wt,wl,zn,ac) in enumerate(tmpl):
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

def bnodes(design):
    return [{"id":n.get("id",""),"label":n.get("data",n).get("label","Node"),
             "type":n.get("data",n).get("type","logic"),
             "description":n.get("data",n).get("description","")} for n in design.get("nodes",[])]

def test_design(design, category):
    name=design.get("name","?"); goal=design.get("goal","")
    wg=gen_widgets(goal,category); an=bnodes(design); wc=len(wg)
    r=api_post(f"{DAVINCI_API}/api/bridge/builds",{"appName":name,"goal":goal,
        "nodeCount":len(an),"widgetCount":wc,"architectNodes":an,
        "uiFunctions":[{"id":w["id"],"label":w["label"],"type":w["type"],
            "description":f"Widget for {goal}","defaultAction":w["archBindings"].get("onClick","") or w["archBindings"].get("onChange",""),"category":"utility"} for w in wg],
        "placedWidgets":wg,
        "archBindings":[{"widgetId":w["id"],"widgetLabel":w["label"],"nodeId":w.get("linkedNodeId",""),
            "bindings":{k:v for k,v in w["archBindings"].items() if v}} for w in wg if any(w["archBindings"].values())]})
    bid=r.get("build_id","")
    if not r.get("received",False):
        return {"name":name,"passed":False,"widgets":wc,"reason":r.get("error","push_fail")[:60]}
    time.sleep(0.2)
    blds=api_get(f"{DAVINCI_API}/api/bridge/builds").get("builds",[])
    if not any(b.get("id")==bid for b in blds):
        return {"name":name,"passed":False,"widgets":wc,"reason":"not_found"}
    ap=api_post(f"{DAVINCI_API}/api/bridge/builds/{bid}/apply",{})
    if not (ap.get("widgets_applied",0) or ap.get("ok")):
        canvas_cleanup(); clear_builds()
        return {"name":name,"passed":False,"widgets":wc,"reason":"apply_fail"}
    time.sleep(0.2)
    cv=api_get(f"{DAVINCI_API}/api/widgets").get("widgets",[]); cc=len(cv); ok=cc>=wc
    api_post(f"{ARCHITECT_API}/api/auto-learn/record",
        {"type":"davinci_gui_test","content":f"Test {name}: {'PASS' if ok else 'FAIL'} - {cc}w",
         "metadata":{"design":name,"category":category,"passed":ok,"widget_count":cc}})
    canvas_cleanup(); clear_builds()
    return {"name":name,"passed":ok,"widgets":cc,"expected":wc}

def canvas_cleanup():
    try: api_post(f"{DAVINCI_API}/api/widgets/batch",{"widgets":[]})
    except: pass
def clear_builds():
    try: api_post(f"{DAVINCI_API}/api/bridge/builds/clear",{})
    except: pass

# ─── Main ────────────────────────────────────────────────────────────
def run(batch_nums=None, limit=None):
    specs=json.load(open(SPECS_FILE))
    existing=[]
    if os.path.exists(DESIGNS_FILE):
        with open(DESIGNS_FILE) as f: existing=json.load(f)
    existing_names={d.get("name","") for d in existing}
    print(f"📂 {len(existing)} existing, loaded {len(existing_names)} names for dedup")
    
    cats = [CATEGORY_LIST[i-1] for i in batch_nums] if batch_nums else CATEGORY_LIST
    total_new=0; total_t=0; total_p=0; total_w=0
    
    for bi,cat in enumerate(cats):
        cat_specs=specs["categories"].get(cat,{})
        dlist=cat_specs.get("designs",[])
        cat_label=CATEGORY_LABELS.get(cat,cat)
        climit=limit or len(dlist)
        if limit: dlist=dlist[:climit]
        
        print(f"\n{'='*50}\n  Batch {bi+1}: {cat.upper()} ({len(dlist)} designs)\n{'='*50}")
        
        batch=[]
        for idx,spec in enumerate(dlist):
            name=spec["name"]
            if name in existing_names:
                if not limit: print(f"  ⏭️  Skip duplicate: {name}")
                continue
            goal=spec["goal"]
            purpose=spec.get("purpose",f"Interactive {name.lower()} with real-time visualization and analysis")
            tags=spec["tags"]+[cat]
            slug=safe_fn(name)
            nodes=generate_nodes(cat,slug,idx)
            edges=make_edges()
            d=save_design(name,goal,purpose,nodes,edges,tags)
            batch.append(d)
            existing.append(d)
            existing_names.add(name)
            write_bible_ref(d,cat_label)
        
        if not batch:
            print("  No new designs (all duplicates)")
            continue
        
        with open(DESIGNS_FILE,'w') as f: json.dump(existing,f,indent=2)
        total_new+=len(batch)
        print(f"  ✅ Generated {len(batch)} new designs, total={len(existing)}")
        
        # Test
        print(f"  Testing {len(batch)} designs...")
        bp=0; bf=0
        for i,d in enumerate(batch):
            res=test_design(d,cat)
            st="✅" if res["passed"] else "❌"
            rs=f" ({res.get('reason','')})" if not res["passed"] else ""
            print(f"    [{i+1}/{len(batch)}] {st} {res['name']}: {res.get('widgets',0)}w{rs}")
            if res["passed"]: bp+=1; total_p+=1
            else: bf+=1
            total_t+=1; total_w+=res.get("widgets",0)
        
        print(f"  → Batch {bi+1}: {bp}/{len(batch)} passed")
    
    print(f"\n{'='*50}\n  🏁 DONE\n{'='*50}")
    print(f"  New: {total_new} | Total: {len(existing)}")
    print(f"  Tested: {total_t} | Passed: {total_p} | Widgets: {total_w}")
    if total_t: print(f"  Rate: {total_p/total_t*100:.1f}%")
    
    api_post(f"{ARCHITECT_API}/api/auto-learn/record",
        {"type":"davinci_gui_batch","content":f"Pipeline: {total_new} new, {total_t} tested, {total_p} passed",
         "metadata":{"new":total_new,"tested":total_t,"passed":total_p,"total":len(existing)}})
    return total_new,total_p,total_t

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--all",action="store_true"); p.add_argument("--batch",type=int,nargs="+",choices=range(1,11))
    p.add_argument("--limit",type=int); p.add_argument("--quick",type=int,default=0)
    p.add_argument("--status",action="store_true"); p.add_argument("--cleanup",action="store_true")
    p.add_argument("--reindex",action="store_true",help="Recreate bible refs for all existing designs")
    args=p.parse_args()
    
    if args.status:
        d=api_get(f"{DAVINCI_API}/api/status"); a=api_get(f"{ARCHITECT_API}/api/auto-learn/status")
        print(f"Davinci: {'✅' if d.get('status')=='ok' else '❌'} | Architect: {'✅' if a.get('success') else '❌'}")
        sys.exit(0)
    
    if args.cleanup:
        canvas_cleanup(); clear_builds()
        print("✅ Davinci canvas and builds cleared")
        sys.exit(0)
    
    if args.reindex:
        designs=json.load(open(DESIGNS_FILE))
        count=0
        for d in designs:
            cat=infer_category(d.get("tags",[]))
            cl=CATEGORY_LABELS.get(cat,"01-fundamentals")
            write_bible_ref(d,cl)
            count+=1
        print(f"✅ Wrote {count} bible refs")
        sys.exit(0)
    
    limit=None
    if args.quick:
        limit=args.quick
        print(f"Quick mode: {limit} per category")
    
    run(batch_nums=args.batch, limit=limit)
