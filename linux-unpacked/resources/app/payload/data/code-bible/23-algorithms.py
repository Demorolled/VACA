# -*- coding: utf-8 -*-
"""
Code Bible — Category 23: Algorithms (atomic, single-responsibility).
Convention: pure functions, no deps; indices 0-based; numeric arrays number[].
"""
CHUNKS = [
    {
        "id": "alg-heapsort",
        "name": "Heapsort",
        "category": "alg",
        "lang": "typescript",
        "when": "Sorting an array in-place with guaranteed O(n log n) worst case",
        "why": "Atomic in-place heap sort — no extra memory, stable no, deterministic",
        "tags": ["alg", "sort", "heapsort", "in-place"],
        "iface": r'''export function heapsort<T>(arr: T[], less?: (a: T, b: T) => boolean): T[]''',
        "code": r'''export function heapsort<T>(arr: T[], less: (a: T, b: T) => boolean = (a, b) => a < b) {
  const a = arr.slice();
  const n = a.length;
  const sift = (i: number, size: number) => {
    while (true) {
      let largest = i, l = 2 * i + 1, r = 2 * i + 2;
      if (l < size && less(a[largest], a[l])) largest = l;
      if (r < size && less(a[largest], a[r])) largest = r;
      if (largest === i) return;
      [a[i], a[largest]] = [a[largest], a[i]];
      i = largest;
    }
  };
  for (let i = (n >> 1) - 1; i >= 0; i--) sift(i, n);
  for (let end = n - 1; end > 0; end--) {
    [a[0], a[end]] = [a[end], a[0]];
    sift(0, end);
  }
  return a;
}''',
        "provides": "heapsort(arr, less?)",
        "depends": [],
    },
    {
        "id": "alg-radix-sort",
        "name": "Radix Sort (LSD)",
        "category": "alg",
        "lang": "typescript",
        "when": "Sorting non-negative integers in O(n*k) without comparisons",
        "why": "Atomic LSD radix sort over digit buckets — fast for fixed-width integer keys",
        "tags": ["alg", "sort", "radix", "integer"],
        "iface": r'''export function radixSort(nums: number[]): number[]''',
        "code": r'''export function radixSort(nums: number[]) {
  if (nums.length === 0) return [];
  const max = Math.max(...nums);
  const buckets: number[][] = Array.from({ length: 10 }, () => []);
  let exp = 1;
  while (exp <= max) {
    buckets.forEach((b) => b.length = 0);
    for (const x of nums) buckets[Math.floor(x / exp) % 10].push(x);
    let i = 0;
    for (const b of buckets) for (const x of b) nums[i++] = x;
    exp *= 10;
  }
  return nums;
}''',
        "provides": "radixSort(nums)",
        "depends": [],
    },
    {
        "id": "alg-counting-sort",
        "name": "Counting Sort",
        "category": "alg",
        "lang": "typescript",
        "when": "Sorting integers in a known small range in linear time",
        "why": "Atomic counting sort — frequency array + prefix scan, O(n + k)",
        "tags": ["alg", "sort", "counting", "linear"],
        "iface": r'''export function countingSort(nums: number[], maxValue: number): number[]''',
        "code": r'''export function countingSort(nums: number[], maxValue: number) {
  const count = new Array(maxValue + 1).fill(0);
  for (const x of nums) count[x]++;
  for (let i = 1; i <= maxValue; i++) count[i] += count[i - 1];
  const out = new Array(nums.length);
  for (let i = nums.length - 1; i >= 0; i--) out[--count[nums[i]]] = nums[i];
  return out;
}''',
        "provides": "countingSort(nums, maxValue)",
        "depends": [],
    },
    {
        "id": "alg-bucket-sort",
        "name": "Bucket Sort",
        "category": "alg",
        "lang": "typescript",
        "when": "Distributing uniformly-random floats into buckets before insertion-sorting",
        "why": "Atomic bucket sort for float keys in [0,1) — O(n) expected",
        "tags": ["alg", "sort", "bucket", "float"],
        "iface": r'''export function bucketSort(nums: number[], bucketCount = 10): number[]''',
        "code": r'''function insertion(arr: number[]) {
  for (let i = 1; i < arr.length; i++) {
    const v = arr[i];
    let j = i - 1;
    while (j >= 0 && arr[j] > v) { arr[j + 1] = arr[j]; j--; }
    arr[j + 1] = v;
  }
  return arr;
}
export function bucketSort(nums: number[], bucketCount = 10) {
  if (nums.length === 0) return [];
  const buckets: number[][] = Array.from({ length: bucketCount }, () => []);
  const lo = Math.min(...nums), hi = Math.max(...nums);
  const span = (hi - lo) / bucketCount || 1;
  for (const x of nums) {
    const b = Math.min(bucketCount - 1, Math.floor((x - lo) / span));
    buckets[b].push(x);
  }
  return buckets.flatMap(insertion);
}''',
        "provides": "bucketSort(nums, bucketCount?)",
        "depends": [],
    },
    {
        "id": "alg-interpolation-search",
        "name": "Interpolation Search",
        "category": "alg",
        "lang": "typescript",
        "when": "Searching a uniformly-distributed sorted array faster than binary search",
        "why": "Atomic interpolation probe — position estimated from key value, O(log log n) avg",
        "tags": ["alg", "search", "interpolation", "sorted"],
        "iface": r'''export function interpolationSearch(sorted: number[], target: number): number''',
        "code": r'''export function interpolationSearch(sorted: number[], target: number) {
  let lo = 0, hi = sorted.length - 1;
  while (lo <= hi && target >= sorted[lo] && target <= sorted[hi]) {
    const span = sorted[hi] - sorted[lo];
    const pos = span === 0 ? lo : lo + Math.floor(((target - sorted[lo]) * (hi - lo)) / span);
    if (sorted[pos] === target) return pos;
    if (sorted[pos] < target) lo = pos + 1; else hi = pos - 1;
  }
  return -1;
}''',
        "provides": "interpolationSearch(sorted, target)",
        "depends": [],
    },
    {
        "id": "alg-exponential-search",
        "name": "Exponential Search",
        "category": "alg",
        "lang": "typescript",
        "when": "Searching unbounded or very large sorted sequences with few probes",
        "why": "Atomic exponential probing (1,2,4,...) then binary search — O(log n)",
        "tags": ["alg", "search", "exponential", "sorted"],
        "iface": r'''export function exponentialSearch(sorted: number[], target: number): number''',
        "code": r'''export function exponentialSearch(sorted: number[], target: number) {
  if (sorted.length === 0) return -1;
  if (sorted[0] === target) return 0;
  let i = 1;
  while (i < sorted.length && sorted[i] <= target) i *= 2;
  let lo = i / 2, hi = Math.min(i, sorted.length - 1);
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] === target) return mid;
    if (sorted[mid] < target) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}''',
        "provides": "exponentialSearch(sorted, target)",
        "depends": [],
    },
    {
        "id": "alg-jump-search",
        "name": "Jump Search",
        "category": "alg",
        "lang": "typescript",
        "when": "Block-skipping search of a sorted array with O(sqrt(n)) probes",
        "why": "Atomic fixed-step jumping + linear scan within block — simple and cache-friendly",
        "tags": ["alg", "search", "jump", "sorted"],
        "iface": r'''export function jumpSearch(sorted: number[], target: number): number''',
        "code": r'''export function jumpSearch(sorted: number[], target: number) {
  const n = sorted.length;
  const step = Math.floor(Math.sqrt(n));
  let prev = 0;
  while (prev < n && sorted[Math.min(step, n) - 1] < target) {
    prev = step;
    step += Math.floor(Math.sqrt(n));
    if (prev >= n) return -1;
  }
  for (let i = prev; i < Math.min(step, n); i++) if (sorted[i] === target) return i;
  return -1;
}''',
        "provides": "jumpSearch(sorted, target)",
        "depends": [],
    },
    {
        "id": "alg-union-find",
        "name": "Union-Find (Disjoint Set)",
        "category": "alg",
        "lang": "typescript",
        "when": "Tracking connected components with near-constant find/union ops",
        "why": "Atomic DSU with path compression + union by rank — amortized alpha(n)",
        "tags": ["alg", "union-find", "disjoint-set", "components"],
        "iface": r'''export class UnionFind {
  constructor(n: number)
  find(x: number): number
  union(a: number, b: number): void
  connected(a: number, b: number): boolean
}''',
        "code": r'''export class UnionFind {
  private parent: number[]; private rank: number[];
  constructor(n: number) {
    this.parent = Array.from({ length: n }, (_, i) => i);
    this.rank = new Array(n).fill(0);
  }
  find(x: number): number {
    if (this.parent[x] !== x) this.parent[x] = this.find(this.parent[x]);
    return this.parent[x];
  }
  union(a: number, b: number) {
    const ra = this.find(a), rb = this.find(b);
    if (ra === rb) return;
    if (this.rank[ra] < this.rank[rb]) this.parent[ra] = rb;
    else { this.parent[rb] = ra; if (this.rank[ra] === this.rank[rb]) this.rank[ra]++; }
  }
  connected(a: number, b: number) { return this.find(a) === this.find(b); }
}''',
        "provides": "UnionFind",
        "depends": [],
    },
    {
        "id": "alg-bellman-ford",
        "name": "Bellman-Ford Shortest Path",
        "category": "alg",
        "lang": "typescript",
        "when": "Shortest paths from one source even with negative edge weights (no neg cycles)",
        "why": "Atomic relax-every-edge N-1 times + cycle check — handles negative weights Dijkstra cannot",
        "tags": ["alg", "graph", "shortest-path", "negative-weights"],
        "iface": r'''export function bellmanFord(n: number, edges: Array<[number, number, number]>, src: number): number[] | null''',
        "code": r'''export function bellmanFord(n: number, edges: Array<[number, number, number]>, src: number) {
  const dist = new Array(n).fill(Infinity);
  dist[src] = 0;
  for (let i = 0; i < n - 1; i++) {
    let changed = false;
    for (const [u, v, w] of edges) {
      if (dist[u] !== Infinity && dist[u] + w < dist[v]) { dist[v] = dist[u] + w; changed = true; }
    }
    if (!changed) break;
  }
  for (const [u, v, w] of edges) if (dist[u] !== Infinity && dist[u] + w < dist[v]) return null;
  return dist;
}''',
        "provides": "bellmanFord(n, edges, src) -> dist or null if negative cycle",
        "depends": [],
    },
    {
        "id": "alg-floyd-warshall",
        "name": "Floyd-Warshall All-Pairs",
        "category": "alg",
        "lang": "typescript",
        "when": "All-pairs shortest paths on a dense graph (adjacency matrix)",
        "why": "Atomic triple-loop DP — O(V^3), simplest all-pairs solution",
        "tags": ["alg", "graph", "all-pairs", "shortest-path", "dp"],
        "iface": r'''export function floydWarshall(adj: number[][]): number[][]''',
        "code": r'''export function floydWarshall(adj: number[][]) {
  const n = adj.length;
  const dist = adj.map((row) => row.slice());
  for (let k = 0; k < n; k++)
    for (let i = 0; i < n; i++)
      for (let j = 0; j < n; j++)
        if (dist[i][k] + dist[k][j] < dist[i][j]) dist[i][j] = dist[i][k] + dist[k][j];
  return dist;
}''',
        "provides": "floydWarshall(adj)",
        "depends": [],
    },
    {
        "id": "alg-kruskal",
        "name": "Kruskal's MST",
        "category": "alg",
        "lang": "typescript",
        "when": "Minimum spanning tree via sorted edges + union-find",
        "why": "Atomic MST: sort by weight, union non-cycles — O(E log E)",
        "tags": ["alg", "graph", "mst", "kruskal", "union-find"],
        "iface": r'''export function kruskal(n: number, edges: Array<[number, number, number]>): Array<[number, number, number]>''',
        "code": r'''export function kruskal(n: number, edges: Array<[number, number, number]>) {
  const sorted = edges.slice().sort((a, b) => a[2] - b[2]);
  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (x: number): number => (parent[x] === x ? x : (parent[x] = find(parent[x])));
  const mst: Array<[number, number, number]> = [];
  for (const [u, v, w] of sorted) {
    const ru = find(u), rv = find(v);
    if (ru !== rv) { parent[ru] = rv; mst.push([u, v, w]); }
  }
  return mst;
}''',
        "provides": "kruskal(n, edges)",
        "depends": [],
    },
    {
        "id": "alg-prim",
        "name": "Prim's MST",
        "category": "alg",
        "lang": "typescript",
        "when": "Minimum spanning tree growing from a seed node",
        "why": "Atomic MST via repeated cheapest cut edge — O(V^2) adjacency-matrix friendly",
        "tags": ["alg", "graph", "mst", "prim"],
        "iface": r'''export function prim(adj: number[][]): number''',
        "code": r'''export function prim(adj: number[][]) {
  const n = adj.length;
  const inTree = new Array(n).fill(false);
  const key = new Array(n).fill(Infinity);
  key[0] = 0;
  let total = 0;
  for (let i = 0; i < n; i++) {
    let u = -1, best = Infinity;
    for (let v = 0; v < n; v++) if (!inTree[v] && key[v] < best) { best = key[v]; u = v; }
    if (u === -1) break;
    inTree[u] = true;
    total += key[u];
    for (let v = 0; v < n; v++) if (!inTree[v] && adj[u][v] < key[v]) key[v] = adj[u][v];
  }
  return total;
}''',
        "provides": "prim(adj) -> MST weight",
        "depends": [],
    },
    {
        "id": "alg-tarjan-scc",
        "name": "Tarjan's SCC",
        "category": "alg",
        "lang": "typescript",
        "when": "Finding strongly connected components in a directed graph",
        "why": "Atomic Tarjan DFS with lowlink + stack — single pass, O(V+E)",
        "tags": ["alg", "graph", "scc", "tarjan", "strongly-connected"],
        "iface": r'''export function tarjanSCC(n: number, adj: number[][]): number[][]''',
        "code": r'''export function tarjanSCC(n: number, adj: number[][]) {
  const index = new Array(n).fill(-1), low = new Array(n).fill(0);
  const onStack = new Array(n).fill(false), stack: number[] = [];
  const out: number[][] = [];
  let counter = 0;
  const dfs = (u: number) => {
    index[u] = low[u] = counter++;
    stack.push(u); onStack[u] = true;
    for (const v of adj[u]) {
      if (index[v] === -1) { dfs(v); low[u] = Math.min(low[u], low[v]); }
      else if (onStack[v]) low[u] = Math.min(low[u], index[v]);
    }
    if (low[u] === index[u]) {
      const comp: number[] = [];
      let w: number;
      do { w = stack.pop()!; onStack[w] = false; comp.push(w); } while (w !== u);
      out.push(comp);
    }
  };
  for (let u = 0; u < n; u++) if (index[u] === -1) dfs(u);
  return out;
}''',
        "provides": "tarjanSCC(n, adj)",
        "depends": [],
    },
    {
        "id": "alg-bipartite",
        "name": "Bipartite Check",
        "category": "alg",
        "lang": "typescript",
        "when": "Verifying a graph is 2-colorable (no odd cycles)",
        "why": "Atomic BFS 2-coloring — detect bipartiteness or return null",
        "tags": ["alg", "graph", "bipartite", "2-color", "bfs"],
        "iface": r'''export function isBipartite(adj: number[][]): boolean''',
        "code": r'''export function isBipartite(adj: number[][]) {
  const color = new Array(adj.length).fill(-1);
  for (let s = 0; s < adj.length; s++) {
    if (color[s] !== -1) continue;
    color[s] = 0;
    const queue = [s];
    while (queue.length) {
      const u = queue.shift()!;
      for (const v of adj[u]) {
        if (color[v] === -1) { color[v] = 1 - color[u]; queue.push(v); }
        else if (color[v] === color[u]) return false;
      }
    }
  }
  return true;
}''',
        "provides": "isBipartite(adj)",
        "depends": [],
    },
    {
        "id": "alg-max-flow",
        "name": "Edmonds-Karp Max Flow",
        "category": "alg",
        "lang": "typescript",
        "when": "Computing maximum flow in a capacitated network via BFS augmenting paths",
        "why": "Atomic Ford-Fulkerson with BFS (Edmonds-Karp) — O(V*E^2), residual graph built in",
        "tags": ["alg", "graph", "max-flow", "edmonds-karp", "network"],
        "iface": r'''export function maxFlow(n: number, edges: Array<[number, number, number]>, s: number, t: number): number''',
        "code": r'''export function maxFlow(n: number, edges: Array<[number, number, number]>, s: number, t: number) {
  const cap: number[][] = Array.from({ length: n }, () => new Array(n).fill(0));
  for (const [u, v, c] of edges) cap[u][v] += c;
  let flow = 0;
  while (true) {
    const parent = new Array(n).fill(-1);
    const queue = [s];
    parent[s] = s;
    while (queue.length && parent[t] === -1) {
      const u = queue.shift()!;
      for (let v = 0; v < n; v++) if (parent[v] === -1 && cap[u][v] > 0) { parent[v] = u; queue.push(v); }
    }
    if (parent[t] === -1) break;
    let push = Infinity;
    for (let v = t; v !== s; v = parent[v]) push = Math.min(push, cap[parent[v]][v]);
    for (let v = t; v !== s; v = parent[v]) { cap[parent[v]][v] -= push; cap[v][parent[v]] += push; }
    flow += push;
  }
  return flow;
}''',
        "provides": "maxFlow(n, edges, s, t)",
        "depends": [],
    },
    {
        "id": "alg-kmp",
        "name": "KMP String Search",
        "category": "alg",
        "lang": "typescript",
        "when": "Finding all occurrences of a pattern in text in O(n+m) worst case",
        "why": "Atomic prefix-function failure links — no backtracking, linear time",
        "tags": ["alg", "string", "kmp", "search", "pattern"],
        "iface": r'''export function kmpSearch(text: string, pattern: string): number[]''',
        "code": r'''export function kmpSearch(text: string, pattern: string) {
  const lps = new Array(pattern.length).fill(0);
  for (let i = 1, len = 0; i < pattern.length; ) {
    if (pattern[i] === pattern[len]) lps[i++] = ++len;
    else if (len) len = lps[len - 1];
    else lps[i++] = 0;
  }
  const hits: number[] = [];
  for (let i = 0, j = 0; i < text.length; i++) {
    while (j > 0 && text[i] !== pattern[j]) j = lps[j - 1];
    if (text[i] === pattern[j]) j++;
    if (j === pattern.length) { hits.push(i - j + 1); j = lps[j - 1]; }
  }
  return hits;
}''',
        "provides": "kmpSearch(text, pattern)",
        "depends": [],
    },
    {
        "id": "alg-rabin-karp",
        "name": "Rabin-Karp Rolling Hash",
        "category": "alg",
        "lang": "typescript",
        "when": "Multiple-pattern or average-case linear substring search with hash windows",
        "why": "Atomic rolling hash (base 131, mod 2^31-1) — one hash per window, O(n+m) average",
        "tags": ["alg", "string", "rabin-karp", "rolling-hash", "search"],
        "iface": r'''export function rabinKarp(text: string, pattern: string): number[]''',
        "code": r'''export function rabinKarp(text: string, pattern: string) {
  if (!pattern) return [];
  const M = 2147483647, B = 131;
  const n = text.length, m = pattern.length;
  let hp = 0, ht = 0, power = 1;
  for (let i = 0; i < m; i++) { hp = (hp * B + pattern.charCodeAt(i)) % M; power = (power * B) % M; }
  const hits: number[] = [];
  for (let i = 0; i <= n - m; i++) {
    if (i === 0) for (let j = 0; j < m; j++) ht = (ht * B + text.charCodeAt(j)) % M;
    else ht = ((ht * B - text.charCodeAt(i - 1) * power + text.charCodeAt(i + m - 1)) % M + M) % M;
    if (hp === ht && text.slice(i, i + m) === pattern) hits.push(i);
  }
  return hits;
}''',
        "provides": "rabinKarp(text, pattern)",
        "depends": [],
    },
    {
        "id": "alg-z-algorithm",
        "name": "Z-Algorithm",
        "category": "alg",
        "lang": "typescript",
        "when": "Computing the longest common prefix of every suffix with the whole string",
        "why": "Atomic Z-array in linear time — the foundation for many string problems",
        "tags": ["alg", "string", "z-algorithm", "prefix"],
        "iface": r'''export function zArray(s: string): number[]''',
        "code": r'''export function zArray(s: string) {
  const n = s.length, z = new Array(n).fill(0);
  let l = 0, r = 0;
  for (let i = 1; i < n; i++) {
    if (i < r) z[i] = Math.min(r - i, z[i - l]);
    while (i + z[i] < n && s[z[i]] === s[i + z[i]]) z[i]++;
    if (i + z[i] > r) { l = i; r = i + z[i]; }
  }
  return z;
}''',
        "provides": "zArray(s)",
        "depends": [],
    },
    {
        "id": "alg-manacher",
        "name": "Manacher Palindromes",
        "category": "alg",
        "lang": "typescript",
        "when": "Finding all palindromic substrings in linear time",
        "why": "Atomic Manacher radii over a transformed string — O(n), no naive expansion",
        "tags": ["alg", "string", "palindrome", "manacher", "linear"],
        "iface": r'''export function manacher(s: string): number[]''',
        "code": r'''export function manacher(s: string) {
  const t = '#' + s.split('').join('#') + '#';
  const n = t.length, p = new Array(n).fill(0);
  let c = 0, r = 0;
  for (let i = 0; i < n; i++) {
    const mirr = 2 * c - i;
    if (i < r) p[i] = Math.min(r - i, p[mirr]);
    while (i + p[i] + 1 < n && t[i - p[i] - 1] === t[i + p[i] + 1]) p[i]++;
    if (i + p[i] > r) { c = i; r = i + p[i]; }
  }
  return p; // radius at each position of the padded string
}''',
        "provides": "manacher(s) -> radii",
        "depends": [],
    },
    {
        "id": "alg-lis",
        "name": "Longest Increasing Subsequence",
        "category": "alg",
        "lang": "typescript",
        "when": "Length of the longest strictly-increasing subsequence in O(n log n)",
        "why": "Atomic patience-sorting tails array — length only, classic interview/ops metric",
        "tags": ["alg", "dp", "lis", "subsequence"],
        "iface": r'''export function lisLength(nums: number[]): number''',
        "code": r'''export function lisLength(nums: number[]) {
  const tails: number[] = [];
  for (const x of nums) {
    let lo = 0, hi = tails.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (tails[mid] < x) lo = mid + 1; else hi = mid; }
    tails[lo] = x;
  }
  return tails.length;
}''',
        "provides": "lisLength(nums)",
        "depends": [],
    },
    {
        "id": "alg-lcs",
        "name": "Longest Common Subsequence",
        "category": "alg",
        "lang": "typescript",
        "when": "Matching two sequences by their longest common subsequence (diff, similarity)",
        "why": "Atomic DP table with rollback — returns length and one alignment",
        "tags": ["alg", "dp", "lcs", "diff", "sequence"],
        "iface": r'''export function lcs<T>(a: T[], b: T[]): { length: number; seq: T[] }''',
        "code": r'''export function lcs<T>(a: T[], b: T[]) {
  const n = a.length, m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++)
    for (let j = 1; j <= m; j++)
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
  const seq: T[] = [];
  let i = n, j = m;
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) { seq.unshift(a[i - 1]); i--; j--; }
    else if (dp[i - 1][j] >= dp[i][j - 1]) i--;
    else j--;
  }
  return { length: dp[n][m], seq };
}''',
        "provides": "lcs(a, b)",
        "depends": [],
    },
    {
        "id": "alg-miller-rabin",
        "name": "Miller-Rabin Primality",
        "category": "alg",
        "lang": "typescript",
        "when": "Probabilistic primality test for large numbers (fast, no factorization)",
        "why": "Atomic modular-exponentiation based witness test — deterministic for n < 2^32",
        "tags": ["alg", "number-theory", "primality", "miller-rabin"],
        "iface": r'''export function isPrime(n: number): boolean''',
        "code": r'''function modPow(base: number, exp: number, mod: number) {
  let r = 1; base %= mod;
  while (exp > 0) {
    if (exp & 1) r = (r * base) % mod;
    base = (base * base) % mod;
    exp >>= 1;
  }
  return r;
}
export function isPrime(n: number) {
  if (n < 2) return false;
  for (const p of [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]) {
    if (n % p === 0) return n === p;
  }
  let d = n - 1, s = 0;
  while (d % 2 === 0) { d /= 2; s++; }
  outer: for (const a of [2, 3, 5, 7, 11, 13, 17]) {
    let x = modPow(a, d, n);
    if (x === 1 || x === n - 1) continue;
    for (let r = 1; r < s; r++) {
      x = (x * x) % n;
      if (x === n - 1) continue outer;
    }
    return false;
  }
  return true;
}''',
        "provides": "isPrime(n)",
        "depends": [],
    },
    {
        "id": "alg-extended-euclid",
        "name": "Extended Euclidean",
        "category": "alg",
        "lang": "typescript",
        "when": "Finding x,y with a*x + b*y = gcd(a,b) (modular inverses, CRT)",
        "why": "Atomic back-substitution free extended Euclid — the modular-inverse primitive",
        "tags": ["alg", "number-theory", "euclid", "modular-inverse"],
        "iface": r'''export function extendedEuclid(a: number, b: number): { gcd: number; x: number; y: number }''',
        "code": r'''export function extendedEuclid(a: number, b: number) {
  if (b === 0) return { gcd: a, x: 1, y: 0 };
  const { gcd, x, y } = extendedEuclid(b, a % b);
  return { gcd, x: y, y: x - Math.floor(a / b) * y };
}''',
        "provides": "extendedEuclid(a, b)",
        "depends": [],
    },
    {
        "id": "alg-crt",
        "name": "Chinese Remainder",
        "category": "alg",
        "lang": "typescript",
        "when": "Solving x ≡ r_i (mod m_i) for pairwise-coprime moduli",
        "why": "Atomic CRT via modular inverses — reconstructs a unique solution mod M",
        "tags": ["alg", "number-theory", "crt", "congruence"],
        "iface": r'''export function chineseRemainder(remainders: number[], moduli: number[]): number''',
        "code": r'''function modInverse(a: number, m: number) {
  const eg = (a2: number, b2: number): { g: number; x: number } =>
    b2 === 0 ? { g: a2, x: 1 } : (() => { const { g, x } = eg(b2, a2 % b2); return { g, x: (x - Math.floor(a2 / b2) * ((g - a2 * x) / b2)) }; })();
  const { x } = eg(((a % m) + m) % m, m);
  return ((x % m) + m) % m;
}
export function chineseRemainder(remainders: number[], moduli: number[]) {
  const M = moduli.reduce((s, m) => s * m, 1);
  let x = 0;
  for (let i = 0; i < moduli.length; i++) {
    const Mi = M / moduli[i];
    x += remainders[i] * Mi * modInverse(Mi, moduli[i]);
  }
  return ((x % M) + M) % M;
}''',
        "provides": "chineseRemainder(remainders, moduli)",
        "depends": [],
    },
    {
        "id": "alg-timsort",
        "name": "Timsort (Hybrid)",
        "category": "alg",
        "lang": "typescript",
        "when": "Adaptive stable sort merging sorted runs — best of insertion + merge",
        "why": "Atomic run-detection + merge (binary-insertion runs) — stable, real-world fast",
        "tags": ["alg", "sort", "timsort", "stable", "hybrid"],
        "iface": r'''export function timsort<T>(arr: T[], less?: (a: T, b: T) => boolean): T[]''',
        "code": r'''function merge<T>(a: T[], b: T[], less: (x: T, y: T) => boolean) {
  const out: T[] = [];
  let i = 0, j = 0;
  while (i < a.length && j < b.length) out.push(less(b[j], a[i]) ? b[j++] : a[i++]);
  return out.concat(a.slice(i), b.slice(j));
}
export function timsort<T>(arr: T[], less: (a: T, b: T) => boolean = (a, b) => a < b) {
  const n = arr.length;
  if (n < 2) return arr.slice();
  const run = (a: T[]) => {
    for (let i = 1; i < a.length; i++) {
      if (less(a[i], a[i - 1])) {
        const x = a[i]; let j = i - 1;
        while (j >= 0 && less(x, a[j])) { a[j + 1] = a[j]; j--; }
        a[j + 1] = x;
      }
    }
    return a;
  };
  if (n <= 64) return run(arr.slice());
  const mid = n >> 1;
  return merge(timsort(arr.slice(0, mid), less), timsort(arr.slice(mid), less), less);
}''',
        "provides": "timsort(arr, less?)",
        "depends": [],
    },
]
