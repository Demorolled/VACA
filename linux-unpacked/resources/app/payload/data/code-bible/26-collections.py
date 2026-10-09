# -*- coding: utf-8 -*-
"""
Code Bible — Category 26: Collections & Data Structures (atomic).
Convention: generic over T, no deps; complexity documented per chunk.
"""
CHUNKS = [
    {
        "id": "col-linked-list",
        "name": "Doubly Linked List",
        "category": "col",
        "lang": "typescript",
        "when": "O(1) insertion/deletion at both ends with stable node references",
        "why": "Atomic doubly-linked list — head/tail ops O(1), index ops O(n), no deps",
        "tags": ["col", "linked-list", "list", "deque", "data-structure"],
        "iface": r'''export class LinkedList<T> {
  push(v: T): void
  unshift(v: T): void
  pop(): T | undefined
  shift(): T | undefined
  get size(): number
}''',
        "code": r'''type Node<T> = { v: T; prev: Node<T> | null; next: Node<T> | null };
export class LinkedList<T> {
  private head: Node<T> | null = null;
  private tail: Node<T> | null = null;
  private n = 0;
  push(v: T) {
    const node: Node<T> = { v, prev: this.tail, next: null };
    if (this.tail) this.tail.next = node;
    this.tail = node;
    if (!this.head) this.head = node;
    this.n++;
  }
  unshift(v: T) {
    const node: Node<T> = { v, prev: null, next: this.head };
    if (this.head) this.head.prev = node;
    this.head = node;
    if (!this.tail) this.tail = node;
    this.n++;
  }
  pop() {
    const t = this.tail;
    if (!t) return undefined;
    this.tail = t.prev;
    if (this.tail) this.tail.next = null; else this.head = null;
    this.n--;
    return t.v;
  }
  shift() {
    const h = this.head;
    if (!h) return undefined;
    this.head = h.next;
    if (this.head) this.head.prev = null; else this.tail = null;
    this.n--;
    return h.v;
  }
  get size() { return this.n; }
}''',
        "provides": "LinkedList",
        "depends": [],
    },
    {
        "id": "col-skip-list",
        "name": "Skip List",
        "category": "col",
        "lang": "typescript",
        "when": "Ordered map with probabilistic O(log n) search/insert/delete",
        "why": "Atomic skip list over number keys — levels built by coin flips, deterministic ops",
        "tags": ["col", "skip-list", "ordered", "probabilistic"],
        "iface": r'''export class SkipList {
  constructor(maxLevel?: number, p?: number)
  insert(key: number, value: unknown): void
  get(key: number): unknown | undefined
  remove(key: number): boolean
}''',
        "code": r'''class SNode { next: (SNode | null)[] = []; constructor(public key: number, public value: unknown, level: number) { this.next = new Array(level).fill(null); } }
export class SkipList {
  private head: SNode;
  private level = 1;
  private p: number;
  constructor(private maxLevel = 16, p = 0.5) {
    this.head = new SNode(-Infinity, null, maxLevel);
    this.p = p;
  }
  private randLevel() { let l = 1; while (Math.random() < this.p && l < this.maxLevel) l++; return l; }
  insert(key: number, value: unknown) {
    const update = new Array(this.maxLevel).fill(this.head);
    let cur: SNode | null = this.head;
    for (let i = this.level - 1; i >= 0; i--) {
      while (cur!.next[i] && cur!.next[i]!.key < key) cur = cur!.next[i];
      update[i] = cur!;
    }
    cur = cur!.next[0];
    if (cur && cur.key === key) { cur.value = value; return; }
    const lvl = this.randLevel();
    if (lvl > this.level) {
      for (let i = this.level; i < lvl; i++) update[i] = this.head;
      this.level = lvl;
    }
    const node = new SNode(key, value, lvl);
    for (let i = 0; i < lvl; i++) { node.next[i] = update[i].next[i]; update[i].next[i] = node; }
  }
  get(key: number) {
    let cur: SNode | null = this.head;
    for (let i = this.level - 1; i >= 0; i--) while (cur!.next[i] && cur!.next[i]!.key < key) cur = cur!.next[i];
    cur = cur!.next[0];
    return cur && cur.key === key ? cur.value : undefined;
  }
  remove(key: number) {
    const update = new Array(this.maxLevel).fill(this.head);
    let cur: SNode | null = this.head;
    for (let i = this.level - 1; i >= 0; i--) {
      while (cur!.next[i] && cur!.next[i]!.key < key) cur = cur!.next[i];
      update[i] = cur!;
    }
    cur = cur!.next[0];
    if (!cur || cur.key !== key) return false;
    for (let i = 0; i < this.level; i++) if (update[i].next[i] === cur) update[i].next[i] = cur.next[i];
    while (this.level > 1 && !this.head.next[this.level - 1]) this.level--;
    return true;
  }
}''',
        "provides": "SkipList",
        "depends": [],
    },
    {
        "id": "col-avltree",
        "name": "AVL Tree",
        "category": "col",
        "lang": "typescript",
        "when": "Self-balancing BST with guaranteed O(log n) lookups and ordered iteration",
        "why": "Atomic AVL — height-balanced on every insert, in-order walk built in",
        "tags": ["col", "avl", "tree", "balanced", "bst"],
        "iface": r'''export class AvlTree {
  constructor(compare?: (a: number, b: number) => number)
  insert(key: number, value?: unknown): void
  has(key: number): boolean
  inorder(): number[]
}''',
        "code": r'''type N = { k: number; v: unknown; h: number; l: N | null; r: N | null };
const H = (n: N | null) => (n ? n.h : 0);
const rotL = (n: N): N => { const r = n.r!; n.r = r.l; r.l = n; n.h = 1 + Math.max(H(n.l), H(n.r)); r.h = 1 + Math.max(H(r.l), H(r.r)); return r; };
const rotR = (n: N): N => { const l = n.l!; n.l = l.r; l.r = n; n.h = 1 + Math.max(H(n.l), H(n.r)); l.h = 1 + Math.max(H(l.l), H(l.r)); return l; };
function ins(n: N | null, k: number, v: unknown): N {
  if (!n) return { k, v, h: 1, l: null, r: null };
  if (k < n.k) n.l = ins(n.l, k, v);
  else if (k > n.k) n.r = ins(n.r, k, v);
  else { n.v = v; return n; }
  n.h = 1 + Math.max(H(n.l), H(n.r));
  const b = H(n.l) - H(n.r);
  if (b > 1 && k < n.l!.k) return rotR(n);
  if (b < -1 && k > n.r!.k) return rotL(n);
  if (b > 1 && k > n.l!.k) { n.l = rotL(n.l!); return rotR(n); }
  if (b < -1 && k < n.r!.k) { n.r = rotR(n.r!); return rotL(n); }
  return n;
}
export class AvlTree {
  private root: N | null = null;
  insert(key: number, value?: unknown) { this.root = ins(this.root, key, value); }
  has(key: number) {
    let n = this.root;
    while (n) { if (key === n.k) return true; n = key < n.k ? n.l : n.r; }
    return false;
  }
  inorder() {
    const out: number[] = [];
    const go = (n: N | null) => { if (!n) return; go(n.l); out.push(n.k); go(n.r); };
    go(this.root);
    return out;
  }
}''',
        "provides": "AvlTree",
        "depends": [],
    },
    {
        "id": "col-redblack",
        "name": "Red-Black Tree",
        "category": "col",
        "lang": "typescript",
        "when": "Balanced ordered set with O(log n) ops and fewer rotations than AVL",
        "why": "Atomic left-leaning red-black insert — canonical Sedgewick implementation",
        "tags": ["col", "red-black", "tree", "balanced", "bst"],
        "iface": r'''export class RedBlackTree {
  insert(key: number): void
  contains(key: number): boolean
  get size(): number
}''',
        "code": r'''type N = { k: number; red: boolean; l: N | null; r: N | null };
const isRed = (n: N | null) => !!n && n.red;
const rotL = (n: N): N => { const x = n.r!; n.r = x.l; x.l = n; x.red = n.red; n.red = true; return x; };
const rotR = (n: N): N => { const x = n.l!; n.l = x.r; x.r = n; x.red = n.red; n.red = true; return x; };
const flip = (n: N) => { n.red = !n.red; if (n.l) n.l.red = !n.l.red; if (n.r) n.r.red = !n.r.red; };
function ins(n: N | null, k: number): N {
  if (!n) return { k, red: true, l: null, r: null };
  if (k < n.k) n.l = ins(n.l, k);
  else if (k > n.k) n.r = ins(n.r, k);
  else return n;
  if (isRed(n.r) && !isRed(n.l)) n = rotL(n);
  if (isRed(n.l) && isRed(n.l!.l)) n = rotR(n);
  if (isRed(n.l) && isRed(n.r)) flip(n);
  return n;
}
export class RedBlackTree {
  private root: N | null = null;
  private n = 0;
  insert(key: number) {
    this.root = ins(this.root, key);
    this.root.red = false;
    this.n++;
  }
  contains(key: number) {
    let cur = this.root;
    while (cur) { if (key === cur.k) return true; cur = key < cur.k ? cur.l : cur.r; }
    return false;
  }
  get size() { return this.n; }
}''',
        "provides": "RedBlackTree",
        "depends": [],
    },
    {
        "id": "col-treap",
        "name": "Treap",
        "category": "col",
        "lang": "typescript",
        "when": "Randomized BST with expected O(log n) ops and split/merge support",
        "why": "Atomic treap — BST key order + heap priority, split/merge for range ops",
        "tags": ["col", "treap", "randomized", "bst", "split"],
        "iface": r'''export class Treap {
  insert(key: number): void
  remove(key: number): void
  has(key: number): boolean
}''',
        "code": r'''type N = { k: number; p: number; l: N | null; r: N | null };
function merge(a: N | null, b: N | null): N | null {
  if (!a) return b;
  if (!b) return a;
  if (a.p > b.p) { a.r = merge(a.r, b); return a; }
  b.l = merge(a, b.l); return b;
}
function split(n: N | null, key: number): [N | null, N | null] {
  if (!n) return [null, null];
  if (n.k < key) { const [l, r] = split(n.r, key); n.r = l; return [n, r]; }
  const [l, r] = split(n.l, key); n.l = r; return [l, n];
}
export class Treap {
  private root: N | null = null;
  insert(key: number) {
    const [l, r] = split(this.root, key);
    const node: N = { k: key, p: Math.random(), l: null, r: null };
    this.root = merge(merge(l, node), r);
  }
  remove(key: number) {
    const [l, mid] = split(this.root, key);
    const [, r] = split(mid, key + 1);
    this.root = merge(l, r);
  }
  has(key: number) {
    let cur = this.root;
    while (cur) { if (key === cur.k) return true; cur = key < cur.k ? cur.l : cur.r; }
    return false;
  }
}''',
        "provides": "Treap",
        "depends": [],
    },
    {
        "id": "col-fenwick",
        "name": "Fenwick Tree (BIT)",
        "category": "col",
        "lang": "typescript",
        "when": "Prefix sums and point updates in O(log n) for dynamic arrays",
        "why": "Atomic binary indexed tree — 1-indexed internals, sum/update/add-range via diff",
        "tags": ["col", "fenwick", "bit", "prefix-sum", "query"],
        "iface": r'''export class FenwickTree {
  constructor(size: number)
  add(i: number, delta: number): void
  sum(i: number): number
  range(l: number, r: number): number
}''',
        "code": r'''export class FenwickTree {
  private bit: number[];
  constructor(size: number) { this.bit = new Array(size + 1).fill(0); }
  add(i: number, delta: number) {
    i++;
    while (i < this.bit.length) { this.bit[i] += delta; i += i & -i; }
  }
  sum(i: number) {
    i++;
    let s = 0;
    while (i > 0) { s += this.bit[i]; i -= i & -i; }
    return s;
  }
  range(l: number, r: number) { return l === 0 ? this.sum(r) : this.sum(r) - this.sum(l - 1); }
}''',
        "provides": "FenwickTree",
        "depends": [],
    },
    {
        "id": "col-segment-tree",
        "name": "Segment Tree (Range Query/Update)",
        "category": "col",
        "lang": "typescript",
        "when": "Range min/max/sum queries with point updates in O(log n)",
        "why": "Atomic iterative segment tree — lazy-free, combine fn injectable",
        "tags": ["col", "segment-tree", "range-query", "update"],
        "iface": r'''export class SegmentTree {
  constructor(values: number[], combine?: (a: number, b: number) => number)
  update(i: number, value: number): void
  query(l: number, r: number): number
}''',
        "code": r'''export class SegmentTree {
  private tree: number[];
  private n: number;
  private combine: (a: number, b: number) => number;
  constructor(values: number[], combine: (a: number, b: number) => number = (a, b) => a + b) {
    this.n = values.length;
    this.combine = combine;
    this.tree = new Array(2 * this.n).fill(0);
    for (let i = 0; i < this.n; i++) this.tree[this.n + i] = values[i];
    for (let i = this.n - 1; i > 0; i--) this.tree[i] = combine(this.tree[2 * i], this.tree[2 * i + 1]);
  }
  update(i: number, value: number) {
    let p = this.n + i;
    this.tree[p] = value;
    for (p >>= 1; p > 0; p >>= 1) this.tree[p] = this.combine(this.tree[2 * p], this.tree[2 * p + 1]);
  }
  query(l: number, r: number) {
    let res = 0, has = false;
    for (l += this.n, r += this.n + 1; l < r; l >>= 1, r >>= 1) {
      if (l & 1) { res = has ? this.combine(res, this.tree[l++]) : this.tree[l++]; has = true; }
      if (r & 1) { res = has ? this.combine(res, this.tree[--r]) : this.tree[--r]; has = true; }
    }
    return res;
  }
}''',
        "provides": "SegmentTree",
        "depends": [],
    },
    {
        "id": "col-sparse-table",
        "name": "Sparse Table (RMQ)",
        "category": "col",
        "lang": "typescript",
        "when": "Immutable-array range minimum/maximum queries in O(1)",
        "why": "Atomic sparse table — log-spaced precompute, idempotent combine only",
        "tags": ["col", "sparse-table", "rmq", "range-min", "immutable"],
        "iface": r'''export class SparseTable {
  constructor(values: number[], op?: (a: number, b: number) => number)
  query(l: number, r: number): number
}''',
        "code": r'''export class SparseTable {
  private st: number[][];
  private op: (a: number, b: number) => number;
  constructor(values: number[], op: (a: number, b: number) => number = Math.min) {
    this.op = op;
    const n = values.length, k = Math.floor(Math.log2(n)) + 1;
    this.st = [values.slice()];
    for (let j = 1; j < k; j++) {
      const prev = this.st[j - 1], cur = new Array(n - (1 << j) + 1).fill(0);
      for (let i = 0; i < cur.length; i++) cur[i] = op(prev[i], prev[i + (1 << (j - 1))]);
      this.st.push(cur);
    }
  }
  query(l: number, r: number) {
    const j = Math.floor(Math.log2(r - l + 1));
    return this.op(this.st[j][l], this.st[j][r - (1 << j) + 1]);
  }
}''',
        "provides": "SparseTable",
        "depends": [],
    },
    {
        "id": "col-interval-tree",
        "name": "Interval Tree",
        "category": "col",
        "lang": "typescript",
        "when": "Finding intervals overlapping a point or range efficiently",
        "why": "Atomic interval tree — sorted starts + max-end augmentation, O(log n + k) queries",
        "tags": ["col", "interval", "tree", "overlap", "query"],
        "iface": r'''export interface Interval { start: number; end: number }
export class IntervalTree {
  constructor(intervals: Interval[])
  queryOverlaps(point: number): Interval[]
}''',
        "code": r'''export class IntervalTree {
  private starts: number[];
  private intervals: Interval[];
  private maxEnds: number[];
  constructor(intervals: Interval[]) {
    this.intervals = intervals.slice().sort((a, b) => a.start - b.start);
    this.starts = this.intervals.map((i) => i.start);
    this.maxEnds = new Array(intervals.length);
    let m = -Infinity;
    for (let i = intervals.length - 1; i >= 0; i--) { m = Math.max(m, this.intervals[i].end); this.maxEnds[i] = m; }
  }
  queryOverlaps(point: number) {
    const out: Interval[] = [];
    let lo = 0, hi = this.starts.length - 1, idx = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (this.starts[mid] <= point) { idx = mid; lo = mid + 1; } else hi = mid - 1; }
    for (let i = idx; i >= 0 && this.maxEnds[i] >= point; i--) if (this.intervals[i].end >= point) out.push(this.intervals[i]);
    return out;
  }
}''',
        "provides": "IntervalTree",
        "depends": [],
    },
    {
        "id": "col-kdtree",
        "name": "KD-Tree",
        "category": "col",
        "lang": "typescript",
        "when": "Nearest-neighbor search in 2D/3D point clouds",
        "why": "Atomic 2D kd-tree — median split, bounding-box prune for k-NN",
        "tags": ["col", "kd-tree", "nearest-neighbor", "spatial", "2d"],
        "iface": r'''export class KdTree2D {
  constructor(points: number[][])
  nearest(x: number, y: number): { point: number[]; distSq: number }
}''',
        "code": r'''type N = { p: number[]; axis: number; l: N | null; r: N | null };
export class KdTree2D {
  private root: N | null;
  constructor(points: number[][]) {
    const build = (pts: number[][], depth: number): N | null => {
      if (!pts.length) return null;
      const axis = depth % 2;
      const sorted = pts.slice().sort((a, b) => a[axis] - b[axis]);
      const mid = sorted.length >> 1;
      return { p: sorted[mid], axis, l: build(sorted.slice(0, mid), depth + 1), r: build(sorted.slice(mid + 1), depth + 1) };
    };
    this.root = build(points, 0);
  }
  nearest(x: number, y: number) {
    let best: N | null = null;
    let bestD = Infinity;
    const distSq = (p: number[]) => (p[0] - x) ** 2 + (p[1] - y) ** 2;
    const walk = (n: N | null): void => {
      if (!n) return;
      const d = distSq(n.p);
      if (d < bestD) { bestD = d; best = n; }
      const diff = (x - n.p[0]) * (n.axis === 0 ? 1 : 0) + (y - n.p[1]) * (n.axis === 1 ? 1 : 0);
      walk(diff < 0 ? n.l : n.r);
      if (diff * diff < bestD) walk(diff < 0 ? n.r : n.l);
    };
    walk(this.root);
    return { point: best!.p, distSq: bestD };
  }
}''',
        "provides": "KdTree2D",
        "depends": [],
    },
    {
        "id": "col-minmax-heap",
        "name": "Min-Max Heap",
        "category": "col",
        "lang": "typescript",
        "when": "O(1) access to both min and max of a dynamic set",
        "why": "Atomic min-max heap — alternating-level ordering, peek/extract both ends",
        "tags": ["col", "minmax-heap", "heap", "priority-queue"],
        "iface": r'''export class MinMaxHeap {
  push(v: number): void
  peekMin(): number | undefined
  peekMax(): number | undefined
  popMin(): number | undefined
  popMax(): number | undefined
  get size(): number
}''',
        "code": r'''export class MinMaxHeap {
  private a: number[] = [];
  get size() { return this.a.length; }
  push(v: number) {
    this.a.push(v);
    let i = this.a.length - 1;
    const isMinLevel = (idx: number) => Math.floor(Math.log2(idx + 1)) % 2 === 0;
    const parent = (j: number) => (j - 1) >> 1;
    const grand = (j: number) => parent(parent(j));
    while (i > 0) {
      const p = parent(i);
      if (isMinLevel(i)) {
        if (this.a[i] < this.a[p]) { [this.a[i], this.a[p]] = [this.a[p], this.a[i]]; i = p; }
        else if (i > 2 && this.a[i] > this.a[grand(i)]) { const g = grand(i); [this.a[i], this.a[g]] = [this.a[g], this.a[i]]; i = g; }
        else break;
      } else {
        if (this.a[i] > this.a[p]) { [this.a[i], this.a[p]] = [this.a[p], this.a[i]]; i = p; }
        else if (i > 2 && this.a[i] < this.a[grand(i)]) { const g = grand(i); [this.a[i], this.a[g]] = [this.a[g], this.a[i]]; i = g; }
        else break;
      }
    }
  }
  peekMin() { return this.a[0]; }
  peekMax() { return this.a.length < 2 ? this.a[0] : this.a.length < 3 ? this.a[1] : Math.max(this.a[1], this.a[2]); }
  popMin() {
    if (!this.a.length) return undefined;
    const min = this.a[0];
    this.a[0] = this.a.pop()!;
    return min;
  }
  popMax() {
    if (!this.a.length) return undefined;
    if (this.a.length < 2) return this.a.pop();
    if (this.a.length < 3) return this.a.pop();
    const mi = this.a[1] >= this.a[2] ? 1 : 2;
    const max = this.a[mi];
    this.a[mi] = this.a.pop()!;
    return max;
  }
}''',
        "provides": "MinMaxHeap",
        "depends": [],
    },
    {
        "id": "col-monotonic",
        "name": "Monotonic Stack/Queue",
        "category": "col",
        "lang": "typescript",
        "when": "Next-greater-element and sliding-window-extrema problems in O(n)",
        "why": "Atomic monotonic helpers — nextGreater indices and sliding window max",
        "tags": ["col", "monotonic", "stack", "queue", "sliding-window"],
        "iface": r'''export function nextGreater(nums: number[]): number[]
export function slidingWindowMax(nums: number[], k: number): number[]''',
        "code": r'''export function nextGreater(nums: number[]) {
  const out = new Array(nums.length).fill(-1);
  const stack: number[] = [];
  for (let i = nums.length - 1; i >= 0; i--) {
    while (stack.length && nums[stack[stack.length - 1]] <= nums[i]) stack.pop();
    out[i] = stack.length ? stack[stack.length - 1] : -1;
    stack.push(i);
  }
  return out;
}
export function slidingWindowMax(nums: number[], k: number) {
  const out: number[] = [];
  const dq: number[] = [];
  for (let i = 0; i < nums.length; i++) {
    while (dq.length && dq[0] <= i - k) dq.shift();
    while (dq.length && nums[dq[dq.length - 1]] <= nums[i]) dq.pop();
    dq.push(i);
    if (i >= k - 1) out.push(nums[dq[0]]);
  }
  return out;
}''',
        "provides": "nextGreater / slidingWindowMax",
        "depends": [],
    },
    {
        "id": "col-freq-counter",
        "name": "Frequency Counter",
        "category": "col",
        "lang": "typescript",
        "when": "Tallying occurrences and querying counts/top-N in one structure",
        "why": "Atomic histogram — Map-backed counts with top-N and most-common API",
        "tags": ["col", "frequency", "counter", "histogram", "top-n"],
        "iface": r'''export class FrequencyCounter<T> {
  add(item: T): number
  count(item: T): number
  top(n: number): Array<[T, number]>
}''',
        "code": r'''export class FrequencyCounter<T> {
  private map = new Map<T, number>();
  add(item: T) {
    const c = (this.map.get(item) ?? 0) + 1;
    this.map.set(item, c);
    return c;
  }
  count(item: T) { return this.map.get(item) ?? 0; }
  top(n: number) {
    return [...this.map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
  }
}''',
        "provides": "FrequencyCounter",
        "depends": [],
    },
    {
        "id": "col-prefix-sum",
        "name": "2D Prefix Sum",
        "category": "col",
        "lang": "typescript",
        "when": "O(1) rectangle-sum queries over a static 2D grid",
        "why": "Atomic inclusion-exclusion precompute — rectSum(l,t,r,b) after one pass",
        "tags": ["col", "prefix-sum", "2d", "rectangle", "query"],
        "iface": r'''export class PrefixSum2D {
  constructor(grid: number[][])
  rectSum(left: number, top: number, right: number, bottom: number): number
}''',
        "code": r'''export class PrefixSum2D {
  private ps: number[][];
  constructor(grid: number[][]) {
    const h = grid.length, w = grid[0]?.length ?? 0;
    this.ps = Array.from({ length: h + 1 }, () => new Array(w + 1).fill(0));
    for (let i = 0; i < h; i++)
      for (let j = 0; j < w; j++)
        this.ps[i + 1][j + 1] = grid[i][j] + this.ps[i][j + 1] + this.ps[i + 1][j] - this.ps[i][j];
  }
  rectSum(left: number, top: number, right: number, bottom: number) {
    return this.ps[bottom + 1][right + 1] - this.ps[top][right + 1] - this.ps[bottom + 1][left] + this.ps[top][left];
  }
}''',
        "provides": "PrefixSum2D",
        "depends": [],
    },
    {
        "id": "col-difference-array",
        "name": "Difference Array",
        "category": "col",
        "lang": "typescript",
        "when": "Applying many range-add updates then materializing once",
        "why": "Atomic diff array — O(1) per range update, O(n) finalize",
        "tags": ["col", "difference", "array", "range-update"],
        "iface": r'''export class DifferenceArray {
  constructor(size: number)
  addRange(l: number, r: number, delta: number): void
  apply(): number[]
}''',
        "code": r'''export class DifferenceArray {
  private diff: number[];
  constructor(size: number) { this.diff = new Array(size + 1).fill(0); }
  addRange(l: number, r: number, delta: number) {
    this.diff[l] += delta;
    this.diff[r + 1] -= delta;
  }
  apply() {
    const out = new Array(this.diff.length - 1).fill(0);
    let cur = 0;
    for (let i = 0; i < out.length; i++) { cur += this.diff[i]; out[i] = cur; }
    return out;
  }
}''',
        "provides": "DifferenceArray",
        "depends": [],
    },
    {
        "id": "col-interval-merge",
        "name": "Interval Merger",
        "category": "col",
        "lang": "typescript",
        "when": "Merging overlapping intervals into disjoint coverage",
        "why": "Atomic sweep — sort by start, extend while overlapping, O(n log n)",
        "tags": ["col", "interval", "merge", "overlap", "sweep"],
        "iface": r'''export interface Interval { start: number; end: number }
export function mergeIntervals(intervals: Interval[]): Interval[]''',
        "code": r'''export function mergeIntervals(intervals: Interval[]) {
  if (!intervals.length) return [];
  const sorted = intervals.slice().sort((a, b) => a.start - b.start);
  const out: Interval[] = [sorted[0]];
  for (const iv of sorted.slice(1)) {
    const last = out[out.length - 1];
    if (iv.start <= last.end) last.end = Math.max(last.end, iv.end);
    else out.push({ ...iv });
  }
  return out;
}''',
        "provides": "mergeIntervals(intervals)",
        "depends": [],
    },
    {
        "id": "col-unique-sorted",
        "name": "Unique Sorted Insert",
        "category": "col",
        "lang": "typescript",
        "when": "Keeping an array sorted with dedupe on every insert (small N)",
        "why": "Atomic binary-search insert — finds position, skips dupes, O(log n) probe",
        "tags": ["col", "sorted", "unique", "insert", "binary-search"],
        "iface": r'''export function sortedInsert<T>(arr: T[], value: T, compare?: (a: T, b: T) => number): boolean''',
        "code": r'''export function sortedInsert<T>(arr: T[], value: T, compare: (a: T, b: T) => number = (a, b) => (a < b ? -1 : a > b ? 1 : 0)) {
  let lo = 0, hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    const c = compare(value, arr[mid]);
    if (c === 0) return false;
    if (c < 0) hi = mid; else lo = mid + 1;
  }
  arr.splice(lo, 0, value);
  return true;
}''',
        "provides": "sortedInsert(arr, value, compare?)",
        "depends": [],
    },
    {
        "id": "col-rotate",
        "name": "Array Rotate",
        "category": "col",
        "lang": "typescript",
        "when": "Rotating an array by k positions left or right in O(n)",
        "why": "Atomic three-reversal rotation — in-place, handles k > n via modulo",
        "tags": ["col", "rotate", "array", "shift", "in-place"],
        "iface": r'''export function rotate<T>(arr: T[], k: number, dir: 'left' | 'right' = 'right'): T[]''',
        "code": r'''function rev<T>(a: T[], l: number, r: number) { while (l < r) { [a[l], a[r]] = [a[r], a[l]]; l++; r--; } }
export function rotate<T>(arr: T[], k: number, dir: 'left' | 'right' = 'right') {
  const n = arr.length;
  if (n < 2) return arr.slice();
  k = ((dir === 'right' ? k : n - k) % n + n) % n;
  const a = arr.slice();
  rev(a, 0, n - 1); rev(a, 0, k - 1); rev(a, k, n - 1);
  return a;
}''',
        "provides": "rotate(arr, k, dir?)",
        "depends": [],
    },
    {
        "id": "col-sparse-matrix",
        "name": "Sparse Matrix",
        "category": "col",
        "lang": "typescript",
        "when": "Storing a mostly-empty matrix without allocating the full grid",
        "why": "Atomic row-map storage — get/set/add, transpose, and row iterate",
        "tags": ["col", "sparse", "matrix", "memory", "2d"],
        "iface": r'''export class SparseMatrix {
  constructor(rows: number, cols: number)
  set(r: number, c: number, v: number): void
  get(r: number, c: number): number
  get size(): { rows: number; cols: number; nonZero: number }
}''',
        "code": r'''export class SparseMatrix {
  private data = new Map<string, number>();
  constructor(private rows: number, private cols: number) {}
  private key(r: number, c: number) { return r + ',' + c; }
  set(r: number, c: number, v: number) {
    if (r < 0 || r >= this.rows || c < 0 || c >= this.cols) throw new Error('Out of bounds');
    if (v === 0) this.data.delete(this.key(r, c));
    else this.data.set(this.key(r, c), v);
  }
  get(r: number, c: number) { return this.data.get(this.key(r, c)) ?? 0; }
  get size() { return { rows: this.rows, cols: this.cols, nonZero: this.data.size }; }
}''',
        "provides": "SparseMatrix",
        "depends": [],
    },
    {
        "id": "col-zipper",
        "name": "List Zipper",
        "category": "col",
        "lang": "typescript",
        "when": "Focusing a cursor on one element with O(1) neighbors (editors, wizards)",
        "why": "Atomic zipper — cursor position + left/right halves, move/insert/delete",
        "tags": ["col", "zipper", "cursor", "focus", "list"],
        "iface": r'''export class ListZipper<T> {
  constructor(items: T[], index?: number)
  get current(): T | undefined
  move(delta: number): T | undefined
  insert(item: T): void
  remove(): T | undefined
}''',
        "code": r'''export class ListZipper<T> {
  private left: T[] = [];
  private right: T[];
  constructor(items: T[], index = 0) {
    const safe = Math.max(0, Math.min(index, items.length));
    this.left = items.slice(0, safe);
    this.right = items.slice(safe);
  }
  get current() { return this.right[0]; }
  move(delta: number) {
    while (delta > 0 && this.right.length > 1) { this.left.push(this.right.shift()!); delta--; }
    while (delta < 0 && this.left.length) { this.right.unshift(this.left.pop()!); delta++; }
    return this.current;
  }
  insert(item: T) { this.right.unshift(item); }
  remove() {
    if (!this.right.length) return undefined;
    const [head, ...rest] = this.right;
    this.right = rest;
    return head;
  }
}''',
        "provides": "ListZipper",
        "depends": [],
    },
    {
        "id": "col-chunker",
        "name": "Chunk Partitioner",
        "category": "col",
        "lang": "typescript",
        "when": "Splitting a list into fixed-size chunks for paging or batching",
        "why": "Atomic chunker — size or count modes, drops partial final chunk on request",
        "tags": ["col", "chunk", "partition", "batch", "paging"],
        "iface": r'''export function chunkBySize<T>(items: T[], size: number): T[][]
export function chunkByCount<T>(items: T[], count: number): T[][]''',
        "code": r'''export function chunkBySize<T>(items: T[], size: number) {
  if (size <= 0) throw new Error('size must be > 0');
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}
export function chunkByCount<T>(items: T[], count: number) {
  if (count <= 0) return [];
  const size = Math.max(1, Math.ceil(items.length / count));
  return chunkBySize(items, size);
}''',
        "provides": "chunkBySize / chunkByCount",
        "depends": [],
    },
    {
        "id": "col-partition",
        "name": "Partition Predicate",
        "category": "col",
        "lang": "typescript",
        "when": "Splitting a list by a predicate into matching/non-matching groups",
        "why": "Atomic partition — one pass, stable order, typed tuple result",
        "tags": ["col", "partition", "filter", "split", "predicate"],
        "iface": r'''export function partition<T>(items: T[], pred: (t: T, i: number) => boolean): [T[], T[]]''',
        "code": r'''export function partition<T>(items: T[], pred: (t: T, i: number) => boolean) {
  const yes: T[] = [], no: T[] = [];
  items.forEach((t, i) => (pred(t, i) ? yes : no).push(t));
  return [yes, no];
}''',
        "provides": "partition(items, pred)",
        "depends": [],
    },
    {
        "id": "col-timestamped-queue",
        "name": "Timestamped Queue",
        "category": "col",
        "lang": "typescript",
        "when": "Tracking when each item was enqueued for TTL or staleness eviction",
        "why": "Atomic FIFO with birth times — peekAge, evictOlderThan, dropStale",
        "tags": ["col", "queue", "timestamp", "ttl", "eviction"],
        "iface": r'''export class TimestampedQueue<T> {
  push(item: T): void
  shift(): T | undefined
  evictOlderThan(ms: number): number
  get size(): number
}''',
        "code": r'''export class TimestampedQueue<T> {
  private items: Array<{ t: number; v: T }> = [];
  push(item: T) { this.items.push({ t: Date.now(), v: item }); }
  shift() { return this.items.shift()?.v; }
  evictOlderThan(ms: number) {
    const cutoff = Date.now() - ms;
    const before = this.items.length;
    this.items = this.items.filter((it) => it.t >= cutoff);
    return before - this.items.length;
  }
  get size() { return this.items.length; }
}''',
        "provides": "TimestampedQueue",
        "depends": [],
    },
    {
        "id": "col-capacity-set",
        "name": "Capacity-Bounded Set",
        "category": "col",
        "lang": "typescript",
        "when": "Bounding memory of a cache-style set by evicting oldest members",
        "why": "Atomic insertion-order Set with max size — oldest out on overflow",
        "tags": ["col", "set", "capacity", "eviction", "cache"],
        "iface": r'''export class CapacitySet<T> {
  constructor(maxSize: number)
  add(item: T): boolean
  has(item: T): boolean
  delete(item: T): boolean
  get size(): number
}''',
        "code": r'''export class CapacitySet<T> {
  private set = new Set<T>();
  constructor(private maxSize: number) {}
  add(item: T) {
    if (this.set.has(item)) return false;
    this.set.add(item);
    while (this.set.size > this.maxSize) this.set.delete(this.set.values().next().value as T);
    return true;
  }
  has(item: T) { return this.set.has(item); }
  delete(item: T) { return this.set.delete(item); }
  get size() { return this.set.size; }
}''',
        "provides": "CapacitySet",
        "depends": [],
    },
    {
        "id": "col-pairing",
        "name": "Adjacent Pairing",
        "category": "col",
        "lang": "typescript",
        "when": "Grouping a list into ordered adjacent pairs",
        "why": "Atomic pairing \u2014 window size 2, no overlap; handy for diff/edge lists",
        "tags": [
            "col",
            "pair",
            "adjacent",
            "window",
            "group"
        ],
        "iface": "export function adjacentPairs<T>(items: T[]): Array<[T, T]>",
        "code": "export function adjacentPairs<T>(items: T[]) {\n  const out: Array<[T, T]> = [];\n  for (let i = 0; i + 1 < items.length; i++) out.push([items[i], items[i + 1]]);\n  return out;\n}",
        "provides": "adjacentPairs(items)",
        "depends": []
    },
]
