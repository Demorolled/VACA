#!/usr/bin/env python3
"""
Supplemental Design Generator
=============================
Generates ~330 additional designs programmatically by combining topics
from the bible-reference knowledge base with pattern-based node templates.

Usage:
  python3 scripts/generate-supplemental.py [--count 60] [--category fundamentals] [--all]
"""

import json, os, sys, time, re, hashlib

DESIGNS_FILE = "data/designs.json"
BIBLE_BASE = "bible-reference"
BIBLE_DESIGNS_BASE = "bible-reference/00-app-designs"
NOW = "2026-06-19T22:00:00.000Z"

CATEGORIES = {
    "fundamentals": "01-fundamentals",
    "games": "02-games",
    "desktop": "03-desktop-apps",
    "systems": "05-systems-programming",
    "database": "06-databases",
    "mathematics": "13-math",
    "specialized": "20-specialized-computing",
    "data-engineering": "27-data-engineering",
    "devops": "33-devops-sre-tooling",
    "search": "36-search-recs-personalization"
}

# Additional design topics per category - these are new topics beyond what's in spec-v2
EXTRA_TOPICS = {
    "fundamentals": [
        ("Ternary Search Explorer","Ternary search on unimodal functions with precision control"),
        ("Interpolation Search","Interpolation search on uniformly distributed sorted arrays"),
        ("Exponential Search Lab","Exponential search combining binary search with range doubling"),
        ("Jump Search Visualizer","Jump search algorithm with block size optimization visualization"),
        ("Fibonacci Search","Fibonacci search using golden ratio for array partitioning"),
        ("Shell Sort Studio","Shell sort with gap sequences (Shell, Knuth, Sedgewick) visualization"),
        ("Cocktail Shaker Sort","Bidirectional bubble sort with cocktail shaker visualization"),
        ("Cycle Sort Lab","In-place cycle sort with minimal memory writes visualization"),
        ("Pancake Sort Visualizer","Pancake sorting with flip operations and cost analysis"),
        ("Bitonic Sort Lab","Parallel bitonic sort with comparator network visualization"),
        ("Tim Sort Explorer","TimSort hybrid sorting with run detection and merging"),
        ("Odd-Even Sort Lab","Parallel odd-even transposition sort visualization"),
        ("Double-Ended Queue","Deque implementation with array and linked-list variants"),
        ("Circular Buffer Lab","Fixed-size circular buffer with producer-consumer patterns"),
        ("Priority Queue Simulator","Binary heap-based priority queue with decrease-key operation"),
        ("Multi-Queue Scheduler","Multi-level queue scheduling with priority feedback"),
        ("Interval Tree Lab","Interval tree for overlapping interval queries"),
        ("Quad Tree Spatial Index","Quad tree for 2D spatial partitioning and range queries"),
        ("KD Tree Lab","K-dimensional tree for nearest neighbor search"),
        ("Huffman Coding Lab","Huffman compression with prefix code tree visualization"),
        ("Run-Length Encoding","RLE compression with various encoding schemes"),
        ("LZW Compression Lab","Lempel-Ziv-Welch dictionary-based compression algorithm"),
        ("Arithmetic Coding Lab","Arithmetic coding with high-precision interval arithmetic"),
        ("Burrows-Wheeler Transform","BWT with move-to-front transform for compression"),
        ("Disk Scheduling Sim","Disk scheduling: FCFS, SSTF, SCAN, C-SCAN, LOOK algorithms"),
        ("Page Replacement Lab","Page replacement: FIFO, LRU, OPT, Clock, NFU, Working Set"),
        ("Banker's Algorithm","Deadlock avoidance with Banker's algorithm safety check"),
        ("Dining Philosophers","Classic synchronization problem with deadlock-free solution"),
        ("Readers-Writers Lab","Readers-writers problem with priority variations"),
        ("Producer Consumer","Bounded buffer producer-consumer with semaphores"),
        ("Sleeping Barber","Classic sleeping barber synchronization problem"),
        ("Counting Sort Visualizer","Integer counting sort with stable sort extension"),
        ("Cycle Detection Lab","Floyd's tortoise and hare cycle detection in linked structures"),
        ("Subarray Sum Finder","Kadane's algorithm for maximum subarray sum visualization"),
        ("Edit Distance Lab","Levenshtein, Hamming, and Damerau-Levenshtein distance comparison"),
        ("Longest Common Subseq","LCS with DP table and backtracking reconstruction"),
        ("Matrix Chain Order","Matrix chain multiplication optimal parenthesization DP"),
        ("Water Jug Problem","Water jug puzzle solver using BFS and GCD approaches"),
    ],
    "games": [
        ("Peg Solitaire","Classic peg solitaire puzzle with board variations"),
        ("Klondike Solitaire","Classic Klondike solitaire card game with drag-drop"),
        ("FreeCell Solitaire","FreeCell solitaire with unlimited undo and hints"),
        ("Spider Solitaire","Spider solitaire with 1/2/4 suit difficulty levels"),
        ("Mahjong Solitaire","Mahjong solitaire tile-matching game"),
        ("Othello/Reversi","Othello board game with AI (minimax/eval function)"),
        ("Backgammon","Backgammon board game with dice and AI opponent"),
        ("Dominoes","Dominoes game with AI and multiple rule sets"),
        ("Battleship","Classic Battleship guessing game with AI"),
        ("Mastermind","Mastermind code-breaking game with feedback pegs"),
        ("Yahtzee","Yahtzee dice game with scoring categories"),
        ("Crazy Eights","Crazy Eights card game with AI opponents"),
        ("Go (Board Game)","Go board game with territory scoring and AI"),
        ("Shogi (Japanese Chess)","Shogi chess variant with promoted pieces and drops"),
        ("Mancala","Mancala seed-sowing game with AI opponent"),
        ("Scrabble Word Game","Scrabble word game with tile rack and dictionary"),
        ("Boggle","Boggle word search game with timer and scoring"),
        ("Set Card Game","Set pattern-matching card game with visual cards"),
        ("Spot It!","Fast-paced pattern matching card game"),
        ("Block Puzzle","Tetris-like block puzzle with grid placement"),
        ("Lumines Style","Rhythm-action puzzle with block clearing"),
        ("Bejeweled Style","Classic gem-swapping puzzle game"),
        ("Snowboard Slalom","Snowboard racing game with obstacle dodging"),
        ("Bike Racing","2D bike racing game with tracks and AI opponents"),
        ("Golf Mini-Game","2D golf game with wind, terrain, and club selection"),
        ("Bowling Simulator","Bowling with physics-based ball and pin collision"),
        ("Pool/Billiards","8-ball pool with cue physics and ball collisions"),
        ("Darts","Darts game with aiming and scoring mechanics"),
        ("Archery Game","Archery with wind, distance, and scoring"),
        ("Fishing Game","Fishing game with casting, reeling, and catch variety"),
        ("Tic-Tac-Toe Ultimate","Ultimate tic-tac-toe with nested boards and AI"),
        ("Racing Game","Top-down racing game with drifting mechanic"),
        ("Pinball Simulator","Pinball with flippers, bumpers, and scoring"),
        ("Carrom Board","Carrom disc-striking game with physics"),
        ("Cribbage","Classic cribbage card game with pegging"),
    ],
    "desktop": [
        ("IP Address Calculator","IPv4/IPv6 subnet calculator with CIDR notation"),
        ("MAC Address Lookup","MAC address vendor lookup and OUI database browser"),
        ("Port Scanner Tool","TCP/UDP port scanner with service detection"),
        ("Network Speed Test","Bandwidth test tool with ping/jitter measurement"),
        ("WiFi Analyzer","WiFi signal strength analyzer with channel graph"),
        ("Bluetooth Scanner","Bluetooth device discovery and service browser"),
        ("MIDI Keyboard Player","Virtual MIDI keyboard with sound synthesis"),
        ("Tuner & Metronome","Instrument tuner and metronome for musicians"),
        ("Chords & Scales","Music theory tool with chord/scale diagrams"),
        ("Sheet Music Reader","Digital sheet music viewer with playback"),
        ("Cooking Timer","Multi-timer cooking assistant with recipe steps"),
        ("Grocery List Maker","Smart grocery list with categories and auto-sort"),
        ("Wine Cellar Manager","Wine inventory with tasting notes and aging tracker"),
        ("Plant Care Tracker","Plant watering schedule with species database"),
        ("Pet Health Logger","Pet vaccination, feeding, and vet appointment tracker"),
        ("Medication Reminder","Medication schedule with dosage tracking"),
        ("Sleep Tracker","Sleep quality logger with alarm and statistics"),
        ("Blood Pressure Log","Health metric tracker with trend charts"),
        ("Calorie Counter","Food diary with calorie and macronutrient tracking"),
        ("Water Intake Tracker","Daily water consumption tracker with reminders"),
        ("Posture Reminder","Ergonomic posture reminder with break timer"),
        ("Eye Care Reminder","20-20-20 rule eye exercise reminder tool"),
        ("Desk Stretch Guide","Office stretch routine guide with animations"),
        ("Breathing Exercise","Guided breathing exercise with animations"),
        ("Mood Journal","Daily mood tracker with journaling and charts"),
        ("Gratitude Journal","Daily gratitude practice with prompts"),
        ("Dream Journal","Dream logging with symbol analysis"),
        ("Password Generator","Cryptographically secure password generator"),
        ("File Encryption Tool","AES-256 file encryption/decryption utility"),
        ("Checksum Verifier","File hash verification: MD5, SHA-1, SHA-256, SHA-512"),
        ("ASCII Art Studio","Convert images to ASCII art with character sets"),
        ("Binary Clock","Binary clock display with time conversion"),
        ("Countdown App","Event countdown with days/hours/minutes/seconds"),
        ("Random Quote Generator","Inspirational quote display with categories"),
        ("Name Generator","Random name generator with cultural origin filters"),
    ],
    "systems": [
        ("Atomic Operation Lab","Compare-and-swap, fetch-add, test-and-set atomic ops"),
        ("Memory Barrier Lab","Memory ordering: acquire, release, sequential consistency"),
        ("Transactional Memory","Software transactional memory with conflict detection"),
        ("RCU (Read-Copy-Update)","RCU synchronization with grace period detection"),
        ("Hazard Pointer Lab","Hazard pointers for safe memory reclamation"),
        ("Epoch-Based Reclamation","EBR with quiescent states and deferral"),
        ("Per-CPU Data Lab","Per-CPU data structures with scalability analysis"),
        ("SeqLock Implementation","Sequence lock for fast read-heavy workloads"),
        ("MCS Lock Lab","MCS scalable spinlock with NUMA awareness"),
        ("Ticket Lock Lab","Ticket spinlock with fair FIFO ordering"),
        ("UDP Server Template","UDP echo server with packet handling patterns"),
        ("TCP Client-Server","TCP client-server with non-blocking I/O"),
        ("UNIX Socket Pair","socketpair() communication between processes"),
        ("Multicast Listener","UDP multicast sender/receiver implementation"),
        ("Unix Signal Handling","Signal handlers, sigaction, sigprocmask usage"),
        ("TimerFD Lab","Linux timerfd for interval and one-shot timers"),
        ("EventFD Lab","Linux eventfd for event notification between processes"),
        ("Signalfd Usage","Linux signalfd for signal handling via file descriptor"),
        ("Inotify File Monitor","Linux inotify for filesystem event monitoring"),
        ("Fanotify Lab","Linux fanotify for filesystem access monitoring"),
        ("Auditd Log Viewer","Linux audit log parser and viewer"),
        ("Capability Lab","Linux capabilities: bounding set, ambient, inheritable"),
        ("Seccomp BPF Lab","Seccomp-BPF syscall filter builder and tester"),
        ("Namespace Explorer","Linux namespace: pid, net, mount, user, cgroup"),
        ("Control Group Stats","Cgroup v2 CPU, memory, IO statistics viewer"),
        ("Sysfs Browser","Sysfs filesystem navigation and parameter viewer"),
        ("Procfs Explorer","Process filesystem deep inspection tool"),
        ("Udev Rule Lab","Linux udev rule builder for device management"),
        ("ACPI Info Viewer","ACPI table and battery/thermal information viewer"),
        ("Kernel Module Lab","Loadable kernel module parameter and log viewer"),
        ("SysRq Key Lab","Linux Magic SysRq key combinations explorer"),
        ("Kprobe Lab","Linux kprobe dynamic instrumentation tool"),
        ("Uprobe Lab","Linux uprobe user-space probing tool"),
        ("Tracepoint Lab","Linux tracepoint event listing and monitoring"),
    ],
    "database": [
        ("Aurora DB Config Lab","AWS Aurora configuration and performance tuning"),
        ("CockroachDB Explorer","CockroachDB distributed SQL with node management"),
        ("YugaByte DB Lab","YugabyteDB distributed SQL query analyzer"),
        ("ClickHouse Analyzer","ClickHouse columnar analytics query performance viewer"),
        ("DuckDB Lab","DuckDB embedded OLAP query and storage viewer"),
        ("SQLite FTS Lab","SQLite FTS5 full-text search configuration"),
        ("SQLite Encryption Lab","SQLite SEE and encryption at rest configuration"),
        ("MariaDB Tuner","MariaDB configuration optimization advisor"),
        ("MySQL InnoDB Lab","InnoDB buffer pool, transaction log, and lock viewer"),
        ("Index Merge Lab","PostgreSQL bitmap index scan and index merging"),
        ("Bloom Index Lab","PostgreSQL bloom index for multi-column queries"),
        ("BRIN Index Lab","PostgreSQL BRIN index for large tables"),
        ("SP-GIST Lab","PostgreSQL SP-GiST index for partitioned trees"),
        ("GIN Index Explorer","PostgreSQL GIN index for array and JSON queries"),
        ("JSON Path Lab","PostgreSQL SQL/JSON path query builder and tester"),
        ("Range Type Lab","PostgreSQL range types and exclusion constraints"),
        ("Enum Type Lab","PostgreSQL enum type creation and management"),
        ("Domain Type Lab","PostgreSQL custom domain types with constraints"),
        ("Foreign Data Wrapper","PostgreSQL FDW for remote data access"),
        ("Table Inheritance Lab","PostgreSQL table inheritance and partitioning"),
        ("Parallel Query Lab","PostgreSQL parallel query execution analysis"),
        ("JIT Compilation Lab","PostgreSQL JIT compilation performance analysis"),
        ("Merge Join Lab","PostgreSQL merge join vs hash join comparison"),
        ("Memoize Lab","PostgreSQL memoize cache for parameterized queries"),
        ("Custom Aggregate Lab","PostgreSQL custom aggregate function builder"),
        ("Window Function Lab","PostgreSQL window function framework explorer"),
        ("CTE Lab","PostgreSQL common table expression recursive query builder"),
        ("Partial Index Lab","PostgreSQL partial index for filtered queries"),
    ],
    "mathematics": [
        ("Goldbach Conjecture","Goldbach's conjecture verification and visualization"),
        ("Collatz Conjecture","Collatz sequence explorer with stopping time charts"),
        ("Riemann Zeta Lab","Riemann zeta function visualization and zeros"),
        ("Prime Number Lab","Prime counting, gaps, and distribution visualization"),
        ("Diophantine Solver","Integer solutions to polynomial equations"),
        ("Chinese Remainder Lab","Chinese remainder theorem solver with CRT visualization"),
        ("Elliptic Curve Lab","Elliptic curve arithmetic and point addition"),
        ("Modular Arithmetic Lab","Modular exponentiation, inverse, discrete log"),
        ("Continued Fraction Lab","Continued fraction expansion and rational approximation"),
        ("Catalan Numbers","Catalan number generator and combinatorial applications"),
        ("Stirling Numbers","Stirling numbers of first and second kind"),
        ("Bernoulli Numbers","Bernoulli number generator and polynomial expansion"),
        ("Partition Function","Integer partition function and Young diagrams"),
        ("Fibonacci Explorer","Fibonacci sequence: Binet formula, Pisano period"),
        ("Pascal's Triangle","Pascal's triangle with binomial coefficient highlighting"),
        ("Mandelbrot Set Explorer","Mandelbrot set with zoom and coloring algorithms"),
        ("Julia Set Explorer","Julia set fractal with parameter variation"),
        ("Sierpinski Triangle","Sierpinski triangle with chaos game and recursion"),
        ("Koch Snowflake","Koch snowflake fractal with iteration steps"),
        ("Dragon Curve","Heighway dragon curve fractal generation"),
        ("Hilbert Curve","Hilbert space-filling curve with order levels"),
        ("Newton Fractal Lab","Newton fractal with root basins of attraction"),
        ("Buddhabrot Renderer","Buddhabrot fractal rendering technique"),
        ("Lyapunov Fractal","Lyapunov fractal with stability visualization"),
        ("Gaussian Function Lab","Gaussian function: bell curves, normal distribution"),
        ("Logistic Map Lab","Logistic map: bifurcation diagram and chaos"),
        ("Lorenz Attractor","Lorenz system strange attractor visualization"),
        ("Rossler Attractor","Rossler attractor with parameter exploration"),
        ("Henon Map Lab","Henon map chaotic attractor visualization"),
        ("Double Pendulum","Double pendulum chaotic motion simulation"),
        ("Hodgkin-Huxley Lab","Hodgkin-Huxley neuron model action potential simulation"),
        ("FitzHugh-Nagumo Lab","FitzHugh-Nagumo neuron model simplified dynamics"),
        ("SIR Model Lab","SIR compartmental epidemic model with R0 calculation"),
        ("Langtons Ant Lab","Langton's ant cellular automaton with rule variations"),
        ("Rule 30 Lab","Wolfram Rule 30 cellular automaton for randomness"),
    ],
    "specialized": [
        ("Voxel Renderer","3D voxel engine with ray marching and lighting"),
        ("Signed Distance Fields","SDF rendering with sphere tracing and CSG ops"),
        ("Bezier Curve Lab","Bezier and B-spline curve editor with de Casteljau"),
        ("NURBS Surface Editor","NURBS surface modeling with control points"),
        ("Catmull-Clark Subdiv","Catmull-Clark subdivision surface viewer"),
        ("Bloom Post-Processing","Bloom/HDR glow effect for real-time rendering"),
        ("SSAO Render Pass","Screen-space ambient occlusion effect"),
        ("Shadow Mapping Lab","Shadow map generation with PCF filtering"),
        ("PBR Shader Viewer","Physically-based rendering shader parameter editor"),
        ("SSR Effect Lab","Screen-space reflections effect implementation"),
        ("Crowd Simulation","Boids flocking algorithm with separation/alignment"),
        ("Traffic Flow Sim","Nagel-Schreckenberg traffic flow cellular automaton"),
        ("Gas Diffusion Lab","Gas particle diffusion simulation with Fick's law"),
        ("Heat Transfer Sim","Finite element heat transfer visualization"),
        ("Wave Equation Lab","2D wave equation solver with ripple visualization"),
        ("Elasticity Simulator","Deformable object elasticity simulation"),
        ("Granular Flow Lab","Granular material flow with particle contacts"),
        ("Sandpile Model","Abelian sandpile model with criticality"),
        ("Forest Fire Sim","Forest fire spread simulation with wind"),
        ("Epidemic Model Lab","SIR/SEIR epidemic spread simulation tool"),
        ("Predator-Prey Lab","Lotka-Volterra predator-prey population dynamics"),
        ("Ecosystem Simulator","Multi-species ecosystem with food webs"),
        ("Ant Foraging Sim","Ant colony foraging and pheromone trail simulation"),
        ("Bee Colony Sim","Bee colony swarm intelligence simulation"),
        ("Slime Mold Lab","Slime mold pathfinding and nutrient seeking"),
        ("Morphogenesis Lab","Turing reaction-diffusion pattern formation"),
        ("L-System Tree Gen","L-system procedural tree generation with rules"),
        ("Terrain Generator","Perlin noise-based procedural terrain generation"),
        ("City Generator","Procedural city layout with road networks"),
        ("Dungeon Generator","Procedural dungeon room generation with BSP"),
        ("Impostor Syndrome Lab","Social simulation of impostor detection game"),
        ("Swarm Robotics Lab","Swarm robot coordination simulation tool"),
        ("Optical Flow Lab","Lucas-Kanade optical flow tracking visualization"),
        ("Sobel Edge Lab","Sobel/Canny edge detection with threshold tuning"),
    ],
    "data-engineering": [
        ("Trino Query Lab","Trino/Presto distributed SQL query federation"),
        ("Snowflake Warehouse","Snowflake data warehouse configuration explorer"),
        ("BigQuery Lab","Google BigQuery query analysis and slot monitoring"),
        ("Redshift Spectrum","AWS Redshift spectrum external table querying"),
        ("Databricks Notebook","Databricks Spark notebook viewer and executor"),
        ("EMR Cluster Config","AWS EMR cluster configuration and optimization"),
        ("Data Proc Lab","GCP Dataproc cluster configuration"),
        ("Synapse Analytics","Azure Synapse dedicated/ serverless SQL pool config"),
        ("Kinesis Stream Lab","AWS Kinesis data stream producer/consumer tool"),
        ("Pub/Sub Lab","GCP Pub/Sub topic/subscription management tool"),
        ("RabbitMQ Explorer","RabbitMQ exchange/queue binding visualization"),
        ("NATS Messaging Lab","NATS messaging pub/sub and request/reply patterns"),
        ("Pulsar Topic Viewer","Apache Pulsar topic subscription management"),
        ("NiFi Flow Designer","Apache NiFi data flow processor configuration"),
        ("StreamSets Pipeline","StreamSets data collector pipeline builder"),
        ("Logstash Config Lab","Logstash pipeline configuration with filter plugins"),
        ("Fluentd Lab","Fluentd log collector and output configuration"),
        ("Vector Dev Tool","Vector observability data pipeline builder"),
        ("Census Data Loader","Census data ETL with demographic data sources"),
        ("Open Data Explorer","Open data portal API explorer and data downloader"),
        ("Financial Data Feed","Stock/financial market data ETL pipeline tool"),
        ("Social Media Ingestion","Social media API data ingestion pipeline"),
        ("Web Scraper Pipeline","Web scraping pipeline with scheduling and storage"),
        ("IoT Data Ingestor","IoT sensor data ingestion and processing pipeline"),
        ("Data Reconciliation","Data reconciliation between source and target systems"),
        ("Slowly Changing Dim","SCD Type 1/2/3 dimension implementation lab"),
        ("Metric Store Lab","Custom metric aggregation and storage tool"),
        ("Data Retention Lab","Data lifecycle and retention policy management"),
        ("File Watcher Pipeline","Directory file watcher triggering pipeline execution"),
    ],
    "devops": [
        ("Nginx Config Lab","Nginx configuration visual builder and tester"),
        ("HAProxy Config Lab","HAProxy load balancer configuration tool"),
        ("Envoy Proxy Lab","Envoy proxy configuration with xDS protocol"),
        ("Traefik Dashboard","Traefik ingress controller dashboard and config"),
        ("Caddy Config Lab","Caddy web server configuration with automatic HTTPS"),
        ("Vault Policy Lab","HashiCorp Vault policy and secret engine explorer"),
        ("Consul Service Mesh","HashiCorp Consul service mesh configuration"),
        ("Nomad Job Lab","HashiCorp Nomad job specification builder"),
        ("Packer Image Lab","HashiCorp Packer machine image builder"),
        ("Vagrant Lab","Vagrant multi-machine VM environment manager"),
        ("Helmfile Lab","Helmfile declarative Helm chart deployment tool"),
        ("Krew Plugin Lab","Krew kubectl plugin manager and plugin browser"),
        ("K9s Cluster Viewer","K9s terminal-based Kubernetes cluster manager"),
        ("Stern Log Viewer","Stern multi-pod log tailing configuration"),
        ("Kubetail Lab","Kubetail multi-pod log aggregation and following"),
        ("ArgoCD Lab","ArgoCD GitOps application and sync configuration"),
        ("Flux CD Lab","Flux GitOps toolkit configuration and automation"),
        ("Rancher Manager","Rancher multi-cluster Kubernetes management"),
        ("OpenShift Config","Red Hat OpenShift cluster configuration tool"),
        ("Rook Storage Lab","Rook Ceph storage orchestrator configuration"),
        ("Longhorn Lab","Longhorn distributed block storage management"),
        ("MinIO Object Store","MinIO S3-compatible object storage config tool"),
        ("Ceph Dashboard","Ceph distributed storage cluster monitor"),
        ("Velero Backup Lab","Velero Kubernetes backup and restore tool"),
        ("Kubescape Lab","Kubescape Kubernetes security scanning tool"),
        ("Trivy Scanner Lab","Trivy container and filesystem vulnerability scanner"),
        ("Falco Rule Lab","Falco runtime security rule builder"),
        ("OPA Policy Lab","Open Policy Agent Rego policy builder and tester"),
        ("Kyverno Policy Lab","Kyverno Kubernetes policy engine rule editor"),
    ],
    "search": [
        ("Whoosh Search Lab","Pure-Python Whoosh search engine indexing demo"),
        ("MeiliSearch Lab","MeiliSearch typo-tolerant search configuration"),
        ("Typesense Lab","Typesense fast search engine configuration tool"),
        ("Solr Config Lab","Apache Solr schema and query configuration"),
        ("Sphinx Search Lab","Sphinx search index and query configuration"),
        ("Tantivy Lab","Tantivy Rust-based search engine builder"),
        ("Quickwit Lab","Quickwit log search and analytics configuration"),
        ("Query Understanding","Search query parsing: tokenization, stemming, lemmatization"),
        ("Language Detection","Automatic text language detection classifier"),
        ("Text Embedding Lab","Text embedding generation with Sentence Transformers"),
        ("Transformer Encoder","BERT-style transformer encoder visualization"),
        ("Cross-Encoder Lab","Cross-encoder for text pair classification"),
        ("Retrieval Augmented Gen","RAG pipeline with retrieval + LLM generation"),
        ("Dense Passage Retrieval","DPR with bi-encoder query/passage embedding"),
        ("ColBERT Lab","ColBERT late interaction retrieval model viewer"),
        ("Hybrid Search Lab","Hybrid sparse + dense vector search fusion"),
        ("Multi-Stage Ranking","Multi-stage: first-pass BM25, second-pass neural"),
        ("Cascade Ranking Lab","Cascade ranking with progressively expensive models"),
        ("Online Learning Lab","Online learning for CTR prediction models"),
        ("Explore-Exploit Lab","Explore-exploit strategies in recommendation"),
        ("Contextual Bandit","Contextual bandit for news article recommendation"),
        ("Popularity Bias Lab","Popularity bias analysis and debiasing in recs"),
        ("Cold Start Lab","Cold start recommendation strategies explorer"),
        ("Serendipity Lab","Novelty and serendipity metrics in recommendations"),
        ("Image Captioning Lab","Image caption generation with encoder-decoder model"),
        ("Question Answering","QA system with passage retrieval and answer extraction"),
        ("Knowledge Graph Lab","Knowledge graph construction and query explorer"),
        ("Graph Embedding Lab","Node2Vec/TransE knowledge graph embedding viewer"),
        ("Cross-Lingual Search","Cross-lingual retrieval using multilingual embeddings"),
    ]
}

def safe_fn(name):
    s = name.lower().replace(' ','-').replace('/','-').replace('\\','-')
    s = re.sub(r'[^a-z0-9-]','',s); s = re.sub(r'-+','-',s).strip('-')
    return s[:60]

def generate_nodes(category, idx):
    """Generate 5 nodes with position offsets for visual variety."""
    base_nodes = {
        "fundamentals":[("input","Data Input","algorithm configuration","typescript",50,50),("logic","Core Algorithm","algorithm implementation","python",250,50),("database","Results Store","computation results","typescript",50,250),("logic","Analysis Engine","performance analysis","python",450,50),("ui","Visualization","interactive display","typescript",450,250)],
        "games":[("input","Game Controller","player input handling","typescript",50,50),("logic","Game Engine","game loop and physics","typescript",250,50),("database","Game State","player stats and save data","typescript",50,250),("logic","AI Opponent","computer opponent AI","typescript",450,50),("ui","Render View","game canvas and HUD","typescript",450,250)],
        "desktop":[("input","User Input","file ops and config","typescript",50,50),("logic","Core Logic","business logic","typescript",250,50),("database","Data Store","app data storage","sqlite",50,250),("logic","Search & Filter","filter operations","typescript",450,50),("ui","User Interface","desktop UI","typescript",450,250)],
        "systems":[("input","System Config","target configuration","typescript",50,50),("logic","Core Engine","systems-level logic","cpp",250,50),("database","Data Collection","metrics and traces","typescript",50,250),("logic","Analysis Module","pattern detection","python",450,50),("ui","Dashboard View","data display","typescript",450,250)],
        "database":[("input","Query/Config","SQL and schema input","typescript",50,50),("logic","Database Engine","query processing","typescript",250,50),("database","Data Store","tables and indexes","sqlite",50,250),("logic","Analysis Module","performance analysis","python",450,50),("ui","Results Display","query visualization","typescript",450,250)],
        "mathematics":[("input","Math Input","equations and params","typescript",50,50),("logic","Math Engine","mathematical computation","python",250,50),("database","Data Storage","results and references","typescript",50,250),("logic","Analysis Module","validation and error","python",450,50),("ui","Visualization","graphs and plots","typescript",450,250)],
        "specialized":[("input","Domain Input","domain parameters","typescript",50,50),("logic","Core Algorithm","domain algorithm","python",250,50),("database","Data Store","simulation data","typescript",50,250),("logic","Analysis Engine","error computation","python",450,50),("ui","Visualization","domain viz","typescript",450,250)],
        "data-engineering":[("input","Pipeline Config","source/target config","typescript",50,50),("logic","Data Processor","transform and validate","python",250,50),("database","Data Store","metadata and logs","sqlite",50,250),("logic","Orchestrator","workflow management","python",450,50),("ui","Pipeline Dashboard","DAG and metrics","typescript",450,250)],
        "devops":[("input","Config Input","infra configuration","typescript",50,50),("logic","Orchestrator","automation logic","python",250,50),("database","State Store","infra state data","sqlite",50,250),("logic","Analysis Engine","metrics analysis","python",450,50),("ui","Ops Dashboard","dashboard panels","typescript",450,250)],
        "search":[("input","Query Input","search and profile","typescript",50,50),("logic","Search Engine","retrieval and ranking","python",250,50),("database","Index & Data","index and profiles","sqlite",50,250),("logic","Evaluation Module","relevance metrics","python",450,50),("ui","Results Display","search results UI","typescript",450,250)]
    }
    tmpl = base_nodes.get(category, base_nodes["fundamentals"])
    offset = idx % 50
    nodes = []
    for i,(nt,nl,nd,nlang,nx,ny) in enumerate(tmpl):
        nodes.append({"id":f"saved_{i}","type":nt,"label":nl,
            "description":f"{nd} — auto-generated design",
            "language":nlang,
            "position":{"x":nx+(i%2)*30+offset%15,"y":ny+(i//2)*20+offset//15*5}})
    return nodes

def make_edges():
    return [{"source":"node_0","target":"node_1"},{"source":"node_1","target":"node_2"},
            {"source":"node_2","target":"node_3"},{"source":"node_3","target":"node_4"},
            {"source":"node_1","target":"node_4"}]

def generate(limit_per_category=None):
    existing = []
    if os.path.exists(DESIGNS_FILE):
        with open(DESIGNS_FILE) as f: existing=json.load(f)
    
    existing_names = {d.get("name","") for d in existing}
    count = len(existing)
    target = 807  # 207 original + 600 new
    total_created = 0

    for cat, bible_dir in CATEGORIES.items():
        topics = EXTRA_TOPICS.get(cat, [])
        if limit_per_category:
            topics = topics[:limit_per_category]
        
        cat_new = []
        for idx,(name,goal) in enumerate(topics):
            if name in existing_names:
                continue
            
            purpose = f"Interactive {cat.replace('-',' ')} tool for {name.lower()}"
            tags = [cat] + name.lower().split()[:3]
            
            nodes = generate_nodes(cat, idx)
            edges = make_edges()
            
            design = {
                "id": f"design_sup_{int(time.time()*1000)}_{os.urandom(4).hex()}",
                "name": name, "goal": goal, "purpose": purpose,
                "targetOS": "linux", "nodes": nodes, "edges": edges,
                "roadmap": f"App: {name}\nTarget: linux\nNodes: {len(nodes)}\nConnections: {len(edges)}",
                "createdAt": NOW, "updatedAt": NOW, "source": "local",
                "tags": tags[:5]
            }
            
            cat_new.append(design)
            existing.append(design)
            existing_names.add(name)
            
            # Write bible ref
            bdir = f"{BIBLE_DESIGNS_BASE}/{bible_dir}"
            os.makedirs(bdir, exist_ok=True)
            fn = f"{safe_fn(name)}.md"
            nodes_s = '\n'.join([f"  - **{n['label']}** ({n['type']}): {n['description']}" for n in nodes])
            edges_s = '\n'.join([f"  - `{e['source']}` → `{e['target']}`" for e in edges])
            path = os.path.join(bdir, fn)
            with open(path, 'w') as f:
                f.write(f"# {name}\n\n**Design ID:** `{design['id']}` | **Category:** {bible_dir}\n\n## Goal\n{goal}\n\n## Nodes\n{nodes_s}\n\n## Edges\n{edges_s}\n\n---\n*Supplemental design | {NOW}*\n")
        
        with open(DESIGNS_FILE, 'w') as f: json.dump(existing, f, indent=2)
        total_created += len(cat_new)
        print(f"  {cat}: {len(cat_new)} new designs (total: {len(existing)})")
    
    print(f"\n✅ Generated {total_created} new supplemental designs")
    print(f"   Total in designs.json: {len(existing)}")
    return total_created

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit per category")
    parser.add_argument("--count", action="store_true", help="Count available topics")
    args = parser.parse_args()
    
    if args.count:
        total = sum(len(v) for v in EXTRA_TOPICS.values())
        print(f"Available supplemental topics: {total}")
        for cat, topics in EXTRA_TOPICS.items():
            print(f"  {cat}: {len(topics)}")
        sys.exit(0)
    
    generate(args.limit)
