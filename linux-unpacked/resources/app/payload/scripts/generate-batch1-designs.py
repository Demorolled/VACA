#!/usr/bin/env python3
"""Generate Batch 1: 20 CS Fundamentals designs for visual-ai-architect."""
import json, os, time

DESIGNS_PATH = "data/designs.json"
BIBLE_DIR = "bible-reference/00-app-designs/01-fundamentals"
NOW = "2026-06-19T14:00:00.000Z"

# Load existing designs
existing = []
if os.path.exists(DESIGNS_PATH):
    with open(DESIGNS_PATH) as f:
        existing = json.load(f)

def make_design(name, goal, purpose, nodes, edges, tags):
    return {
        "id": f"design_b1_{int(time.time()*1000)}_{len(existing)+len(globals().get('created', []))}",
        "name": name,
        "goal": goal,
        "purpose": purpose,
        "targetOS": "linux",
        "nodes": nodes,
        "edges": edges,
        "roadmap": f"App: {name}\nTarget OS: linux\nNodes: {len(nodes)}\nConnections: {len(edges)}",
        "createdAt": NOW,
        "updatedAt": NOW,
        "source": "local",
        "tags": tags
    }

def n(id, type_, label, desc, lang, x, y):
    return {"id": f"saved_{id}", "type": type_, "label": label, "description": desc, "language": lang, "position": {"x": x, "y": y}}

def e(src, tgt):
    return {"source": f"node_{src}", "target": f"node_{tgt}"}

created = []

# 1. Big O Analyzer
created.append(make_design(
    "Big O Analyzer", 
    "Visualize and compare algorithm time/space complexity with interactive charts",
    "An educational tool that runs algorithms on sample data and plots their growth curves to teach Big O notation, with step-by-step animation of each operation",
    [
        n(0,"input","Algorithm Selector","Dropdown to pick algorithm (bubble, merge, quick, binary search, etc.)","typescript",50,100),
        n(1,"logic","Complexity Engine","Runs selected algorithm on growing input sizes, measures operations and time","typescript",250,100),
        n(2,"database","Results Store","Stores measurement data points: input size, operations count, execution time","sqlite",250,300),
        n(3,"logic","Curve Fitter","Fits measured data to known complexity curves (O(1), O(n), O(n²), O(n log n))","python",450,100),
        n(4,"ui","Chart Renderer","Plots actual vs theoretical complexity curves with interactive tooltips","typescript",450,300)
    ],
    [e(0,1), e(1,2), e(1,3), e(3,4), e(2,4)],
    ["complexity","big-o","visualization","education","algorithms"]
))

# 2. Array Explorer
created.append(make_design(
    "Array Explorer",
    "Interactive visualization of static/dynamic array operations with memory layout display",
    "Demonstrates array internals: contiguous memory, O(1) access, insertion/deletion costs, dynamic resizing (geometric growth), and cache-line behavior with a memory address visualizer",
    [
        n(0,"input","Array Builder","Configure array type (static/dynamic), initial size, and element values","typescript",50,50),
        n(1,"logic","Operation Engine","Performs insert, delete, search, access operations with step-by-step execution","typescript",250,50),
        n(2,"database","Memory Store","Simulates contiguous memory blocks with addresses and cache lines","typescript",50,250),
        n(3,"logic","Growth Simulator","Models dynamic array geometric resizing (1.5x, 2x) with copy overhead calculation","typescript",450,50),
        n(4,"ui","Memory Map Viewer","Renders memory layout with highlighted cache lines, address labels, and element highlighting","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(1,3), e(2,4), e(3,4)],
    ["arrays","memory","data-structures","visualization","cache"]
))

# 3. Linked List Visualizer
created.append(make_design(
    "Linked List Visualizer",
    "Interactive singly/doubly/circular linked list with pointer manipulation visualization",
    "Teaches pointer-based data structures through visual node-link diagrams. Supports insert/delete/reverse/cycle detection with step animations showing next/prev pointer updates",
    [
        n(0,"input","List Controller","Create/select list type (singly, doubly, circular) and perform operations","typescript",50,50),
        n(1,"logic","Pointer Engine","Executes pointer manipulations: insertion, deletion, reversal, cycle detection (Floyd's)","typescript",250,50),
        n(2,"database","Node Store","Maintains linked list of node objects with next/prev pointers and data values","typescript",50,250),
        n(3,"logic","Cycle Detector","Implements tortoise and hare algorithm with step visualization","typescript",450,50),
        n(4,"ui","Node Graph Renderer","Draws node-link diagram with animated pointer changes, highlighting active nodes","typescript",450,250),
        n(5,"ui","Pointer Inspector","Shows raw pointer values, memory addresses, and next/prev references for each node","typescript",650,150)
    ],
    [e(0,1), e(1,2), e(1,3), e(2,4), e(3,4), e(2,5)],
    ["linked-list","pointers","data-structures","visualization","education"]
))

# 4. Hash Table Demo
created.append(make_design(
    "Hash Table Demo",
    "Interactive hash table with multiple collision resolution strategies visualization",
    "Explores hashing strategies: separate chaining, open addressing (linear/quadratic/double), cuckoo hashing, and Robin Hood. Shows hash function output, bucket placement, load factor, and resize events",
    [
        n(0,"input","Hash Configurator","Choose hash function, collision strategy, load factor threshold, and initial capacity","typescript",50,50),
        n(1,"logic","Hash Function Engine","Applies selected hash (Murmur, xxHash, SipHash) to keys and computes bucket index","typescript",250,50),
        n(2,"database","Bucket Store","Manages hash table array with buckets (chains or slots) and load factor tracking","typescript",50,250),
        n(3,"logic","Collision Resolver","Implements selected strategy: chaining, probing, or cuckoo with step animation","typescript",450,50),
        n(4,"ui","Table Visualizer","Renders bucket array with color-coded occupancy, chain lengths, and probe sequences","typescript",450,250),
        n(5,"ui","Hash Inspector","Shows binary hash output, bucket index calculation, and collision statistics","typescript",650,150)
    ],
    [e(0,1), e(1,2), e(1,3), e(2,3), e(3,4), e(2,5)],
    ["hash-table","hashing","collision","data-structures","visualization"]
))

# 5. Binary Tree Viewer
created.append(make_design(
    "Binary Tree Viewer",
    "Comprehensive BST/AVL/Red-Black tree viewer with rotation animations and traversal demos",
    "Visualizes tree data structures with auto-layout, color-coded nodes (balance factor, red/black), rotation animations, and all traversal orders (in/pre/post/level). Supports insert/delete/search with self-balancing",
    [
        n(0,"input","Tree Builder","Add/delete nodes, select tree type (BST, AVL, Red-Black), generate random trees","typescript",50,50),
        n(1,"logic","Tree Engine","Core BST operations: insertion, deletion, search, successor/predecessor","typescript",250,50),
        n(2,"logic","Balance Manager","AVL rotations (LL/RR/LR/RL) and Red-Black fixup with step-by-step animation","typescript",250,250),
        n(3,"database","Node Store","Tree node storage with parent/left/right pointers, height, color, balance factor","typescript",50,450),
        n(4,"logic","Traversal Engine","Inorder, preorder, postorder, level-order traversals with output streaming","typescript",450,50),
        n(5,"ui","Tree Canvas","Renders tree with Reingold-Tilford layout, highlights search path and rotation nodes","typescript",450,250),
        n(6,"ui","Traversal Output","Shows traversal sequence with highlighted current node and output array","typescript",650,150)
    ],
    [e(0,1), e(1,2), e(2,3), e(1,4), e(3,5), e(4,6), e(2,5)],
    ["binary-tree","bst","avl","red-black","tree","visualization"]
))

# 6. Sorting Visualizer
created.append(make_design(
    "Sorting Visualizer",
    "Compare 10+ sorting algorithms side-by-side with bar chart animations and complexity stats",
    "Visually demonstrates bubble, selection, insertion, shell, merge, quick, heap, counting, radix, bucket, timsort. Shows comparisons, swaps, and auxiliary memory usage with real-time statistics",
    [
        n(0,"input","Sort Controller","Select algorithms, array size, sorting speed, and data distribution (random/sorted/reversed)","typescript",50,50),
        n(1,"logic","Algorithm Runner","Executes selected sorting algorithms in parallel with step synchronization","typescript",250,50),
        n(2,"database","Data Store","Maintains array copies and tracks comparison/swap counts per algorithm","typescript",50,250),
        n(3,"ui","Bar Chart View","Renders animated bar charts showing comparison and swap operations in real-time","typescript",450,50),
        n(4,"ui","Stats Dashboard","Displays comparison count, swap count, execution time, and memory usage per algorithm","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(1,3), e(2,4)],
    ["sorting","algorithms","visualization","comparison","education"]
))

# 7. Recursion Tree Builder
created.append(make_design(
    "Recursion Tree Builder",
    "Visualize recursive algorithms as tree diagrams with stack frame animation",
    "Builds recursion trees for Fibonacci, factorial, Towers of Hanoi, permutations, and N-Queens. Shows stack frame push/pop with variable values, return propagation, and base case highlighting",
    [
        n(0,"input","Recursion Picker","Choose recursive algorithm and input parameters (n value, board size, etc.)","typescript",50,50),
        n(1,"logic","Recursion Engine","Executes recursive algorithm with step-by-step call/return tracking","typescript",250,50),
        n(2,"database","Call Stack Store","Maintains call stack with frame objects (parameters, local vars, return address)","typescript",50,250),
        n(3,"ui","Recursion Tree View","Renders tree of recursive calls with depth coloring and active call highlighting","typescript",450,50),
        n(4,"ui","Stack Frame Panel","Shows current stack with frame contents, variable values, and return propagation animation","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(2,3), e(1,4)],
    ["recursion","backtracking","call-stack","visualization","education"]
))

# 8. DP Solver Studio
created.append(make_design(
    "DP Solver Studio",
    "Interactive dynamic programming table builder with memoization vs tabulation comparison",
    "Solves classic DP problems (knapsack, LCS, edit distance, subset sum, matrix chain) with visual DP tables, memoization tree highlighting, and optimal substructure exploration",
    [
        n(0,"input","Problem Config","Select DP problem (knapsack, LCS, edit dist, etc.) and input parameters","typescript",50,50),
        n(1,"logic","DP Engine","Top-down (memoization) and bottom-up (tabulation) DP solver","typescript",250,50),
        n(2,"database","DP Table Store","2D DP table storage with memo cache and optimal path tracking","typescript",50,250),
        n(3,"logic","Optimal Path Finder","Backtrack through DP table to reconstruct optimal solution","typescript",450,50),
        n(4,"ui","DP Table Viewer","Renders DP table with color-coded cells and optimal path highlighting","typescript",450,250),
        n(5,"ui","Solution Panel","Displays computed result, optimal value, and reconstructed solution with steps","typescript",650,150)
    ],
    [e(0,1), e(1,2), e(2,3), e(2,4), e(3,5)],
    ["dynamic-programming","dp","memoization","tabulation","algorithms"]
))

# 9. Greedy Algorithm Lab
created.append(make_design(
    "Greedy Algorithm Lab",
    "Interactive greedy algorithm laboratory with exchange argument visualizations",
    "Demonstrates greedy algorithms: interval scheduling, fractional knapsack, Huffman coding, MST (Kruskal/Prim), Dijkstra. Shows greedy choice property proofs with exchange argument animations",
    [
        n(0,"input","Problem Selector","Choose greedy problem and input data (intervals, items, graph edges)","typescript",50,50),
        n(1,"logic","Greedy Engine","Applies greedy strategy: sorting by key function, making locally optimal choices","typescript",250,50),
        n(2,"database","Solution Store","Stores solution steps, choices made, and optimality verification data","typescript",50,250),
        n(3,"ui","Step Visualizer","Shows each greedy choice with before/after state and optimality reasoning","typescript",450,50),
        n(4,"ui","Proof Assistant","Visual exchange argument: swapping greedy solution with optimal, step-by-step","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(1,3), e(2,4)],
    ["greedy","algorithms","optimization","exchange-argument","education"]
))

# 10. Graph Pathfinder
created.append(make_design(
    "Graph Pathfinder",
    "Complete graph algorithm visualizer with BFS/DFS, Dijkstra, A*, Bellman-Ford, Floyd-Warshall",
    "Interactive graph editor and algorithm runner. Add vertices/edges with weights, run shortest path algorithms with step animation, see priority queue operations, relaxation steps, and final path highlighting",
    [
        n(0,"input","Graph Editor","Add/remove vertices and weighted edges, drag to position, select start/end nodes","typescript",50,50),
        n(1,"logic","Graph Engine","Adjacency list/matrix management with edge weight validation","typescript",250,50),
        n(2,"database","Graph Store","Stores graph structure, traversal states, distance/prev arrays","typescript",50,250),
        n(3,"logic","Path Algorithm Runner","BFS, DFS, Dijkstra (binary heap), A*, Bellman-Ford, Floyd-Warshall with step capture","typescript",450,50),
        n(4,"ui","Graph Canvas","Renders graph with force-directed layout, highlights visited/active/path nodes","typescript",450,250),
        n(5,"ui","Algorithm Console","Shows step-by-step algorithm state: queue contents, distance updates, relaxation steps","typescript",650,50),
        n(6,"ui","Path Result Viewer","Displays final shortest path with total distance and vertex sequence","typescript",650,250)
    ],
    [e(0,1), e(1,2), e(2,3), e(3,4), e(3,5), e(2,6)],
    ["graph","pathfinding","dijkstra","bfs","dfs","algorithms"]
))

# 11. String Pattern Matcher
created.append(make_design(
    "String Pattern Matcher",
    "Visual string matching laboratory with KMP, Rabin-Karp, Z-algorithm, and Aho-Corasick",
    "Interactive pattern matching across multiple algorithms. Shows character-by-character comparison, failure function construction, rolling hash computation, and automaton state transitions",
    [
        n(0,"input","Pattern Config","Enter text and pattern strings, select matching algorithm(s)","typescript",50,100),
        n(1,"logic","Match Engine","Implements KMP (prefix function), Rabin-Karp (rolling hash), Z-algorithm","typescript",250,100),
        n(2,"database","Match Store","Stores match positions, comparison counts, failure function values","typescript",250,300),
        n(3,"ui","Text Visualizer","Renders text with sliding window, character comparison highlighting, match markers","typescript",450,100),
        n(4,"ui","Algorithm Details","Shows prefix function array, rolling hash values, Z-array with step explanation","typescript",450,300)
    ],
    [e(0,1), e(1,2), e(2,3), e(1,4)],
    ["string-matching","kmp","rabin-karp","z-algorithm","algorithms"]
))

# 12. Stack & Queue Simulator
created.append(make_design(
    "Stack & Queue Simulator",
    "Interactive LIFO/FIFO data structure simulator with array and linked-list implementations",
    "Visualizes stack (push/pop/peek) and queue (enqueue/dequeue/peek) operations. Shows both array and linked-list implementations side-by-side with memory layout and operation complexity",
    [
        n(0,"input","Operation Panel","Choose structure (stack/queue) and implementation (array/linked list), push/pop values","typescript",50,50),
        n(1,"logic","Structure Engine","Executes push/pop/enqueue/dequeue with overflow/underflow checking","typescript",250,50),
        n(2,"database","Data Store","Maintains underlying array or linked nodes with head/tail/front/back pointers","typescript",50,250),
        n(3,"ui","Structure View","Renders stack/queue with element highlighting, shows head/tail/top pointers","typescript",450,50),
        n(4,"ui","Operation Log","Lists each operation with before/after state and time complexity annotation","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(2,3), e(1,4)],
    ["stack","queue","lifo","fifo","data-structures"]
))

# 13. Trie Auto-Complete
created.append(make_design(
    "Trie Auto-Complete",
    "Prefix tree auto-complete engine with visualization, search suggestions, and compression",
    "Builds a trie from a word list, demonstrates prefix search with auto-complete suggestions, shows trie structure with node compression (radix tree), and displays traversal paths",
    [
        n(0,"input","Dictionary Loader","Load word list, add custom words, set minimum prefix length","typescript",50,50),
        n(1,"logic","Trie Builder","Inserts words into trie structure with shared prefix optimization","typescript",250,50),
        n(2,"database","Trie Node Store","Maintains trie nodes with children map, end-of-word flag, and suggestion ranking","typescript",50,250),
        n(3,"logic","Search & Suggest","Prefix search with DFS traversal, returns ranked suggestions by frequency","typescript",450,50),
        n(4,"ui","Trie Visualizer","Renders trie as tree with colored prefixes, shows search path and suggestions","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(2,3), e(3,4)],
    ["trie","prefix-tree","auto-complete","search","data-structures"]
))

# 14. Heap Priority Queue
created.append(make_design(
    "Heap Priority Queue",
    "Min-heap and max-heap visualizer with heapify, push/pop, and heap sort animations",
    "Visualizes binary heap operations: sift-up, sift-down, heapify, extract-min/max, decrease-key. Shows array representation alongside tree view with complete/invariant check",
    [
        n(0,"input","Heap Controller","Choose min/max heap, insert values, extract, build from array","typescript",50,50),
        n(1,"logic","Heap Engine","Sift-up, sift-down, heapify, heap sort with step-by-step execution","typescript",250,50),
        n(2,"database","Array Store","Maintains underlying array representation with heap property validation","typescript",50,250),
        n(3,"ui","Tree View","Renders heap as complete binary tree with parent-child relationship arrows","typescript",450,50),
        n(4,"ui","Array View","Shows array representation with parent/child index highlighting","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(2,3), e(2,4)],
    ["heap","priority-queue","heapify","heap-sort","data-structures"]
))

# 15. Binary Search Tester
created.append(make_design(
    "Binary Search Tester",
    "Interactive binary search lab with classic, lower_bound, upper_bound, and exponential search",
    "Teaches binary search variants on sorted arrays. Shows search interval (low/mid/high pointers), decision tree, comparison count, and handles edge cases (empty, duplicates, not found)",
    [
        n(0,"input","Search Config","Configure sorted array, target value, search variant (classic/lower/upper/exp)","typescript",50,100),
        n(1,"logic","Search Engine","Implements binary search variants with step tracking and invariant checking","typescript",250,100),
        n(2,"database","Step Store","Records each comparison: low, high, mid indices, decision (go left/right/found)","typescript",250,300),
        n(3,"ui","Search Visualizer","Shows array with low/mid/high pointers, highlights searched region, found position","typescript",450,100),
        n(4,"ui","Decision Tree","Renders binary decision tree showing search path and comparisons","typescript",450,300)
    ],
    [e(0,1), e(1,2), e(2,3), e(2,4)],
    ["binary-search","searching","algorithms","decision-tree","education"]
))

# 16. Bit Manipulation Tool
created.append(make_design(
    "Bit Manipulation Tool",
    "Interactive bitwise operation sandbox with binary representation and bit hacks",
    "Visualizes bitwise operations (AND, OR, XOR, NOT, shifts) on integers. Shows binary/hex/decimal representations with animated bit flips. Demonstrates bit hacks: population count, bit reversal, power-of-2 detection",
    [
        n(0,"input","Bit Workshop","Enter values, select operation (AND/OR/XOR/NOT/shift), apply bit masks","typescript",50,100),
        n(1,"logic","Bit Engine","Executes bitwise operations, bit counting (popcount), bit manipulation hacks","typescript",250,100),
        n(2,"database","Bit Store","Stores operation history, previous values, and common bit patterns","typescript",250,300),
        n(3,"ui","Bit Display","Renders 32-bit or 64-bit binary with per-bit animation, hex/decimal conversion","typescript",450,100),
        n(4,"ui","Hack Library","Shows common bit manipulation patterns with explanation and live demo","typescript",450,300)
    ],
    [e(0,1), e(1,2), e(2,3), e(1,4)],
    ["bitwise","bit-manipulation","binary","hacks","low-level"]
))

# 17. Design Pattern Explorer
created.append(make_design(
    "Design Pattern Explorer",
    "Interactive catalog of 23 GoF design patterns with UML diagrams and code generation",
    "Browse and explore creational, structural, and behavioral patterns. Each pattern includes UML class diagram, sequence diagram, TypeScript/Python implementation, and interactive demo showing pattern in action",
    [
        n(0,"input","Pattern Browser","Browse/filter 23 GoF patterns by category (creational/structural/behavioral)","typescript",50,50),
        n(1,"logic","Pattern Engine","Generates pattern-specific UML structure and code implementation","typescript",250,50),
        n(2,"database","Pattern Store","Stores pattern definitions, UML data, code templates, and examples","typescript",50,250),
        n(3,"ui","UML Diagram View","Renders class/sequence diagrams for selected pattern with interactive elements","typescript",450,50),
        n(4,"ui","Code Viewer","Shows pattern implementation in TypeScript/Python with syntax highlighting","typescript",450,250),
        n(5,"api","Pattern Demo Runner","Runs interactive demo showing the pattern in action with live objects","typescript",250,450)
    ],
    [e(0,1), e(1,2), e(2,3), e(2,4), e(1,5)],
    ["design-patterns","uml","gof","software-design","education"]
))

# 18. Concurrency Visualizer
created.append(make_design(
    "Concurrency Visualizer",
    "Interactive thread/process visualization with mutex, semaphore, and deadlock detection",
    "Simulates concurrent programs with multiple threads, mutex locks, semaphores, condition variables, and barriers. Shows thread states (running/blocked/ready), context switches, and deadlock detection with cycle detection",
    [
        n(0,"input","Thread Config","Configure thread count, resources, locking strategy, and execution scenario","typescript",50,50),
        n(1,"logic","Scheduler Sim","Simulates thread lifecycle with context switches, lock acquire/release, and timing","typescript",250,50),
        n(2,"database","Thread State Store","Maintains thread states, lock ownership, wait queues, and resource allocation","typescript",50,250),
        n(3,"logic","Deadlock Detector","Waits-for graph construction with cycle detection (DFS) for deadlock identification","typescript",450,50),
        n(4,"ui","Thread Timeline","Gantt chart showing thread states over time with lock acquisition events","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(2,3), e(1,4), e(3,4)],
    ["concurrency","threads","mutex","deadlock","visualization"]
))

# 19. Memory Allocator Lab
created.append(make_design(
    "Memory Allocator Lab",
    "Interactive memory allocator simulator with stack, heap, pool, and slab allocators",
    "Visualizes memory allocation strategies: bump allocator, free-list, buddy system, slab allocator, arena. Shows memory fragmentation, allocation/deallocation patterns, and garbage collection (mark-sweep, copying)",
    [
        n(0,"input","Alloc Config","Select allocator type, memory pool size, allocation pattern (sequential/random)","typescript",50,50),
        n(1,"logic","Allocation Engine","Handles malloc/free with selected strategy, tracks blocks and fragmentation","typescript",250,50),
        n(2,"database","Memory Block Store","Maintains allocated/free block list with addresses, sizes, and metadata","typescript",50,250),
        n(3,"logic","GC Simulator","Mark-sweep and copying garbage collection with root scanning animation","typescript",450,50),
        n(4,"ui","Memory Map","Renders memory layout with color-coded blocks (allocated/free/GC roots)","typescript",450,250)
    ],
    [e(0,1), e(1,2), e(2,3), e(1,4), e(3,4)],
    ["memory-management","allocator","gc","fragmentation","low-level"]
))

# 20. Algorithm Race Track
created.append(make_design(
    "Algorithm Race Track",
    "Side-by-side algorithm comparison with live benchmark charts and complexity verification",
    "Competitive algorithm benchmarking tool. Runs multiple algorithms on identical data, measures execution time, operations count, and memory usage. Generates comparison charts and complexity analysis reports",
    [
        n(0,"input","Race Config","Select algorithms, input sizes, data distributions, and metrics to track","typescript",50,50),
        n(1,"logic","Race Engine","Runs selected algorithms in sequence, captures performance metrics per run","typescript",250,50),
        n(2,"database","Benchmark Store","Stores benchmark results: execution time, operations, memory per algorithm per size","typescript",50,250),
        n(3,"logic","Complexity Verifier","Compares empirical results against theoretical complexity curves","typescript",450,50),
        n(4,"ui","Benchmark Charts","Renders comparison bar/line charts with color-coded algorithm series","typescript",450,250),
        n(5,"ui","Report Generator","Generates comprehensive comparison report with winner declarations","typescript",650,150)
    ],
    [e(0,1), e(1,2), e(2,3), e(2,4), e(3,5)],
    ["benchmark","algorithms","comparison","complexity","performance"]
))

# Write all to designs.json
existing.extend(created)
with open(DESIGNS_PATH, 'w') as f:
    json.dump(existing, f, indent=2)

print(f"✅ Wrote {len(created)} designs to {DESIGNS_PATH}")
print(f"   Total designs now: {len(existing)}")

# Generate bible reference files
for i, d in enumerate(created):
    name_short = d['name'].lower().replace(' ', '-').replace('---','-')
    bfile = os.path.join(BIBLE_DIR, f"{i+1:02d}-{name_short}.md")
    tags_str = ', '.join(d['tags'])
    nodes_str = '\n'.join([f"  - **{n['label']}** ({n['type']}): {n['description']}" for n in d['nodes']])
    edges_str = '\n'.join([f"  - `{e['source']}` → `{e['target']}`" for e in d['edges']])
    
    content = f"""# 🏗️ {d['name']}

> **Design ID:** `{d['id']}`
> **Category:** 01-fundamentals
> **Tags:** {tags_str}
> **Target OS:** {d['targetOS']}

## Goal

{d['goal']}

## Purpose

{d['purpose']}

## Node Architecture

{d['nodes'][0]['position']['x'] < 200 and d['nodes'][0]['position']['y'] < 200 and "```" or ""}
Input → Processing → Storage → Display
{"```" if d['nodes'][0]['position']['x'] < 200 and d['nodes'][0]['position']['y'] < 200 else ""}

### Nodes ({len(d['nodes'])})

{nodes_str}

### Edges ({len(d['edges'])})

{edges_str}

## Bible Reference

This design teaches concepts from **bible-reference/01-fundamentals/**

Related files:
{chr(10).join([f"- `01-fundamentals/{t}.md`" for t in d['tags'] if t in ['arrays','linked-list','hash-table','binary-tree','tree','graph','trie','heap','stack','queue','sorting','searching','binary-search','recursion','backtracking','dynamic-programming','greedy','complexity','bit-manipulation','memory-management','concurrency','design-patterns','uml','algorithms','data-structures','performance','education','visualization','comparison','low-level']])}

## Generated Code

When built, this design generates a complete Linux application with:
- Input handling and validation
- Core algorithmic logic
- Data persistence layer
- Interactive visualization UI
- Performance metrics and reporting

---

*Design generated for the Visual AI Architect system*
"""
    with open(bfile, 'w') as f:
        f.write(content)
    print(f"   📄 Created {bfile}")

print(f"\n✅ Batch 1 complete: {len(created)} designs created with bible reference files")
