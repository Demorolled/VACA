# -*- coding: utf-8 -*-
"""
Code Bible — Category 05: Logic & algorithms (atomic, pure functions).
Convention: `run(input: XxxInput): XxxOutput` — no side effects, no I/O.
"""
CHUNKS = [
    {
        "id": "logic-minimax",
        "name": "Minimax Search",
        "category": "logic",
        "lang": "typescript",
        "when": "Building turn-based AI that assumes the opponent plays optimally",
        "why": "Atomic minimax; state/evaluator in, best move out — game rules injected, never embedded",
        "tags": ["minimax", "ai", "search", "game", "adversarial"],
        "iface": r'''export interface MinimaxGame<S, M> {
  getMoves(state: S): M[];
  apply(state: S, move: M): S;
  isTerminal(state: S): boolean;
  evaluate(state: S): number;   // from current player's perspective
}
export function minimax<S, M>(game: MinimaxGame<S, M>, state: S, depth: number, isMax: boolean): number
export function bestMove<S, M>(game: MinimaxGame<S, M>, state: S, depth?: number): M | null''',
        "code": r'''export function minimax<S, M>(game: MinimaxGame<S, M>, state: S, depth: number, isMax: boolean): number {
  if (depth === 0 || game.isTerminal(state)) return game.evaluate(state);
  const moves = game.getMoves(state);
  if (moves.length === 0) return game.evaluate(state);

  if (isMax) {
    let best = -Infinity;
    for (const m of moves) best = Math.max(best, minimax(game, game.apply(state, m), depth - 1, false));
    return best;
  }
  let best = Infinity;
  for (const m of moves) best = Math.min(best, minimax(game, game.apply(state, m), depth - 1, true));
  return best;
}

export function bestMove<S, M>(game: MinimaxGame<S, M>, state: S, depth = 4): M | null {
  let best: M | null = null;
  let bestScore = -Infinity;
  for (const m of game.getMoves(state)) {
    const score = minimax(game, game.apply(state, m), depth - 1, false);
    if (score > bestScore) { bestScore = score; best = m; }
  }
  return best;
}''',
        "provides": "minimax<S,M>(game, state, depth, isMax), bestMove<S,M>(game, state, depth?)",
        "depends": [],
    },
    {
        "id": "logic-alpha-beta",
        "name": "Alpha-Beta Pruning",
        "category": "logic",
        "lang": "typescript",
        "when": "Speeding up minimax by pruning provably-worse branches",
        "why": "Atomic alpha-beta; same game interface as minimax in, best move out — orders of magnitude faster",
        "tags": ["alpha", "beta", "pruning", "minimax", "search"],
        "iface": r'''export function alphaBeta<S, M>(game: MinimaxGame<S, M>, state: S, depth: number, alpha: number, beta: number, isMax: boolean): number
export function bestMoveAB<S, M>(game: MinimaxGame<S, M>, state: S, depth?: number): M | null''',
        "code": r'''export function alphaBeta<S, M>(
  game: MinimaxGame<S, M>, state: S, depth: number, alpha: number, beta: number, isMax: boolean,
): number {
  if (depth === 0 || game.isTerminal(state)) return game.evaluate(state);
  const moves = game.getMoves(state);
  if (moves.length === 0) return game.evaluate(state);

  if (isMax) {
    let value = -Infinity;
    for (const m of moves) {
      value = Math.max(value, alphaBeta(game, game.apply(state, m), depth - 1, alpha, beta, false));
      alpha = Math.max(alpha, value);
      if (alpha >= beta) break;   // prune
    }
    return value;
  }
  let value = Infinity;
  for (const m of moves) {
    value = Math.min(value, alphaBeta(game, game.apply(state, m), depth - 1, alpha, beta, true));
    beta = Math.min(beta, value);
    if (alpha >= beta) break;     // prune
  }
  return value;
}

export function bestMoveAB<S, M>(game: MinimaxGame<S, M>, state: S, depth = 6): M | null {
  let best: M | null = null;
  let bestScore = -Infinity;
  let alpha = -Infinity;
  const beta = Infinity;
  for (const m of game.getMoves(state)) {
    const score = alphaBeta(game, game.apply(state, m), depth - 1, alpha, beta, false);
    if (score > bestScore) { bestScore = score; best = m; }
    alpha = Math.max(alpha, score);
  }
  return best;
}''',
        "provides": "alphaBeta<S,M>(...), bestMoveAB<S,M>(game, state, depth?)",
        "depends": [],
    },
    {
        "id": "logic-astar",
        "name": "A* Pathfinding",
        "category": "logic",
        "lang": "typescript",
        "when": "Finding shortest paths on grids or graphs with a heuristic",
        "why": "Atomic A*; grid + start/goal in, path out — heuristic injectable, works on any cost grid",
        "tags": ["astar", "pathfinding", "grid", "search", "heuristic"],
        "iface": r'''export interface AStarOptions { allowDiagonal?: boolean; heuristic?: (a: [number, number], b: [number, number]) => number }
export function astar(
  grid: number[][],                       // 0 = walkable, >0 = cost
  start: [number, number],
  goal: [number, number],
  options?: AStarOptions,
): Array<[number, number]> | null''',
        "code": r'''export function astar(grid: number[][], start: [number, number], goal: [number, number],
  options?: AStarOptions): Array<[number, number]> | null {
  const rows = grid.length, cols = grid[0]?.length ?? 0;
  const heuristic = options?.heuristic ?? ((a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]));
  const dirs = options?.allowDiagonal
    ? [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]
    : [[1, 0], [-1, 0], [0, 1], [0, -1]];

  const g = new Map<string, number>();
  const cameFrom = new Map<string, string>();
  const open: Array<[number, number]> = [start];
  const key = (r: number, c: number) => `${r},${c}`;
  g.set(key(start[0], start[1]), 0);

  function fScore(r: number, c: number): number {
    return (g.get(key(r, c)) ?? Infinity) + heuristic([r, c], goal);
  }

  while (open.length > 0) {
    open.sort((a, b) => fScore(a[0], a[1]) - fScore(b[0], b[1]));
    const [r, c] = open.shift()!;
    if (r === goal[0] && c === goal[1]) {
      const path: Array<[number, number]> = [[r, c]];
      let cur = key(r, c);
      while (cameFrom.has(cur)) {
        const [pr, pc] = cur.split(',').map(Number);
        cur = cameFrom.get(cur)!;
        path.unshift([pr, pc]);
      }
      return path;
    }
    for (const [dr, dc] of dirs) {
      const nr = r + dr, nc = c + dc;
      if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) continue;
      if (grid[nr][nc] === 0 && !(nr === goal[0] && nc === goal[1])) continue;  // wall
      const cost = grid[nr][nc] === 0 ? 1 : grid[nr][nc];
      const tentative = (g.get(key(r, c)) ?? Infinity) + cost;
      if (tentative < (g.get(key(nr, nc)) ?? Infinity)) {
        g.set(key(nr, nc), tentative);
        cameFrom.set(key(nr, nc), key(r, c));
        if (!open.some(([or, oc]) => or === nr && oc === nc)) open.push([nr, nc]);
      }
    }
  }
  return null;
}''',
        "provides": "astar(grid, start, goal, options?)",
        "depends": [],
    },
    {
        "id": "logic-dijkstra",
        "name": "Dijkstra Shortest Path",
        "category": "logic",
        "lang": "typescript",
        "when": "Shortest paths in weighted graphs without a heuristic",
        "why": "Atomic Dijkstra; adjacency + start in, distances + prev out — works with any non-negative weights",
        "tags": ["dijkstra", "shortest", "path", "graph", "weighted"],
        "iface": r'''export interface WeightedGraph { neighbors(node: string): Array<{ to: string; weight: number }> }
export function dijkstra(
  graph: WeightedGraph,
  start: string,
  goal?: string,
): { distances: Map<string, number>; previous: Map<string, string | null> }''',
        "code": r'''export function dijkstra(graph: WeightedGraph, start: string, goal?: string) {
  const distances = new Map<string, number>();
  const previous = new Map<string, string | null>();
  const visited = new Set<string>();
  const pq: Array<[string, number]> = [[start, 0]];
  distances.set(start, 0);

  while (pq.length > 0) {
    pq.sort((a, b) => a[1] - b[1]);
    const [node, dist] = pq.shift()!;
    if (visited.has(node)) continue;
    visited.add(node);
    if (goal !== undefined && node === goal) break;

    for (const { to, weight } of graph.neighbors(node)) {
      const nd = dist + weight;
      if (nd < (distances.get(to) ?? Infinity)) {
        distances.set(to, nd);
        previous.set(to, node);
        pq.push([to, nd]);
      }
    }
  }
  return { distances, previous };
}

export function reconstructPath(previous: Map<string, string | null>, goal: string): string[] {
  const path: string[] = [];
  let cur: string | null = goal;
  while (cur) { path.unshift(cur); cur = previous.get(cur) ?? null; }
  return path;
}''',
        "provides": "dijkstra(graph, start, goal?), reconstructPath(previous, goal)",
        "depends": [],
    },
    {
        "id": "logic-bfs",
        "name": "Breadth-First Search",
        "category": "logic",
        "lang": "typescript",
        "when": "Unweighted shortest paths, level-order traversal, connectivity checks",
        "why": "Atomic BFS; start + neighbors in, order + distances out — no recursion, no weights",
        "tags": ["bfs", "breadth", "search", "graph", "level"],
        "iface": r'''export interface BfsResult { order: string[]; distances: Map<string, number> }
export function bfs(
  start: string,
  neighbors: (node: string) => string[],
): BfsResult''',
        "code": r'''export function bfs(start: string, neighbors: (node: string) => string[]): BfsResult {
  const queue: string[] = [start];
  const order: string[] = [];
  const distances = new Map<string, number>();
  distances.set(start, 0);

  while (queue.length > 0) {
    const node = queue.shift()!;
    order.push(node);
    for (const next of neighbors(node)) {
      if (distances.has(next)) continue;
      distances.set(next, distances.get(node)! + 1);
      queue.push(next);
    }
  }
  return { order, distances };
}''',
        "provides": "bfs(start, neighbors)",
        "depends": [],
    },
    {
        "id": "logic-dfs",
        "name": "Depth-First Search",
        "category": "logic",
        "lang": "typescript",
        "when": "Maze solving, topological ordering, cycle detection",
        "why": "Atomic DFS; start + neighbors in, traversal order out — iterative to avoid stack overflow",
        "tags": ["dfs", "depth", "search", "graph", "cycle"],
        "iface": r'''export interface DfsResult { order: string[]; found: (target: string) => boolean }
export function dfs(
  start: string,
  neighbors: (node: string) => string[],
  target?: string,
): DfsResult''',
        "code": r'''export function dfs(start: string, neighbors: (node: string) => string[], target?: string): DfsResult {
  const visited = new Set<string>();
  const order: string[] = [];
  const stack: string[] = [start];
  let foundTarget = target === start;

  while (stack.length > 0) {
    const node = stack.pop()!;
    if (visited.has(node)) continue;
    visited.add(node);
    order.push(node);
    if (target !== undefined && node === target) { foundTarget = true; break; }
    for (const next of neighbors(node)) {
      if (!visited.has(next)) stack.push(next);
    }
  }
  return { order, found: (t) => foundTarget || (t !== undefined && visited.has(t)) };
}''',
        "provides": "dfs(start, neighbors, target?)",
        "depends": [],
    },
    {
        "id": "logic-quicksort",
        "name": "Quicksort",
        "category": "logic",
        "lang": "typescript",
        "when": "In-place sorting with good average performance",
        "why": "Atomic quicksort; array in, sorted copy out — pure, comparator-injectable, median-of-3 pivot",
        "tags": ["sort", "quicksort", "partition", "algorithm", "compare"],
        "iface": r'''export function quicksort<T>(items: T[], compare?: (a: T, b: T) => number): T[]''',
        "code": r'''export function quicksort<T>(items: T[], compare?: (a: T, b: T) => number): T[] {
  const arr = [...items];
  const cmp = compare ?? ((a: T, b: T) => (a < b ? -1 : a > b ? 1 : 0));

  function partition(lo: number, hi: number): number {
    const mid = (lo + hi) >> 1;
    const pivot = arr[mid];
    [arr[mid], arr[hi]] = [arr[hi], arr[mid]];
    let i = lo;
    for (let j = lo; j < hi; j++) {
      if (cmp(arr[j], pivot) < 0) { [arr[i], arr[j]] = [arr[j], arr[i]]; i++; }
    }
    [arr[i], arr[hi]] = [arr[hi], arr[i]];
    return i;
  }

  function sort(lo: number, hi: number) {
    if (lo >= hi) return;
    const p = partition(lo, hi);
    sort(lo, p - 1);
    sort(p + 1, hi);
  }

  sort(0, arr.length - 1);
  return arr;
}''',
        "provides": "quicksort<T>(items, compare?)",
        "depends": [],
    },
    {
        "id": "logic-mergesort",
        "name": "Mergesort",
        "category": "logic",
        "lang": "typescript",
        "when": "Stable sorting with guaranteed O(n log n)",
        "why": "Atomic mergesort; array in, sorted stable copy out — no mutation of input",
        "tags": ["sort", "mergesort", "stable", "divide", "conquer"],
        "iface": r'''export function mergesort<T>(items: T[], compare?: (a: T, b: T) => number): T[]''',
        "code": r'''export function mergesort<T>(items: T[], compare?: (a: T, b: T) => number): T[] {
  const cmp = compare ?? ((a: T, b: T) => (a < b ? -1 : a > b ? 1 : 0));

  function merge(left: T[], right: T[]): T[] {
    const out: T[] = [];
    let i = 0, j = 0;
    while (i < left.length && j < right.length) {
      if (cmp(left[i], right[j]) <= 0) out.push(left[i++]);
      else out.push(right[j++]);
    }
    return out.concat(left.slice(i), right.slice(j));
  }

  function sort(arr: T[]): T[] {
    if (arr.length <= 1) return arr;
    const mid = arr.length >> 1;
    return merge(sort(arr.slice(0, mid)), sort(arr.slice(mid)));
  }

  return sort([...items]);
}''',
        "provides": "mergesort<T>(items, compare?)",
        "depends": [],
    },
    {
        "id": "logic-heap",
        "name": "Binary Heap",
        "category": "logic",
        "lang": "typescript",
        "when": "Priority queues, Dijkstra, k-largest problems",
        "why": "Atomic min/max heap; push/pop/peek out — comparator-injectable, array-backed",
        "tags": ["heap", "priority", "queue", "binary", "minmax"],
        "iface": r'''export function createHeap<T>(compare?: (a: T, b: T) => number) {
  return {
    push(value: T): void,
    pop(): T | undefined,
    peek(): T | undefined,
    get size(): number,
    get isEmpty(): boolean,
  };
}''',
        "code": r'''export function createHeap<T>(compare?: (a: T, b: T) => number) {
  const arr: T[] = [];
  const cmp = compare ?? ((a: T, b: T) => (a < b ? -1 : a > b ? 1 : 0));

  function siftUp(i: number) {
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (cmp(arr[i], arr[parent]) >= 0) break;
      [arr[i], arr[parent]] = [arr[parent], arr[i]];
      i = parent;
    }
  }

  function siftDown(i: number) {
    const n = arr.length;
    while (true) {
      let smallest = i;
      const l = 2 * i + 1, r = 2 * i + 2;
      if (l < n && cmp(arr[l], arr[smallest]) < 0) smallest = l;
      if (r < n && cmp(arr[r], arr[smallest]) < 0) smallest = r;
      if (smallest === i) break;
      [arr[i], arr[smallest]] = [arr[smallest], arr[i]];
      i = smallest;
    }
  }

  return {
    push(value) { arr.push(value); siftUp(arr.length - 1); },
    pop() {
      if (arr.length === 0) return undefined;
      const top = arr[0];
      const last = arr.pop()!;
      if (arr.length > 0) { arr[0] = last; siftDown(0); }
      return top;
    },
    peek: () => arr[0],
    get size() { return arr.length; },
    get isEmpty() { return arr.length === 0; },
  };
}''',
        "provides": "createHeap<T>(compare?)",
        "depends": [],
    },
    {
        "id": "logic-trie",
        "name": "Trie (Prefix Tree)",
        "category": "logic",
        "lang": "typescript",
        "when": "Autocomplete, spellcheck, prefix matching over word sets",
        "why": "Atomic trie; insert/search/prefix/autocomplete out — O(word length) lookups",
        "tags": ["trie", "prefix", "autocomplete", "search", "dictionary"],
        "iface": r'''export function createTrie() {
  return {
    insert(word: string): void,
    search(word: string): boolean,
    startsWith(prefix: string): boolean,
    autocomplete(prefix: string, limit?: number): string[],
  };
}''',
        "code": r'''export function createTrie() {
  interface Node { children: Map<string, Node>; end: boolean }
  const root: Node = { children: new Map(), end: false };

  function collect(node: Node, prefix: string, out: string[], limit: number) {
    if (out.length >= limit) return;
    if (node.end) out.push(prefix);
    for (const [ch, child] of node.children) collect(child, prefix + ch, out, limit);
  }

  return {
    insert(word) {
      let node = root;
      for (const ch of word) {
        if (!node.children.has(ch)) node.children.set(ch, { children: new Map(), end: false });
        node = node.children.get(ch)!;
      }
      node.end = true;
    },
    search(word) {
      let node = root;
      for (const ch of word) {
        node = node.children.get(ch);
        if (!node) return false;
      }
      return node.end;
    },
    startsWith(prefix) {
      let node = root;
      for (const ch of prefix) {
        node = node.children.get(ch);
        if (!node) return false;
      }
      return true;
    },
    autocomplete(prefix, limit = 10) {
      let node = root;
      for (const ch of prefix) {
        node = node.children.get(ch);
        if (!node) return [];
      }
      const out: string[] = [];
      collect(node, prefix, out, limit);
      return out;
    },
  };
}''',
        "provides": "createTrie()",
        "depends": [],
    },
    {
        "id": "logic-graph-adjacency",
        "name": "Adjacency Graph",
        "category": "logic",
        "lang": "typescript",
        "when": "Modeling relationships for traversal, dependency order, or communities",
        "why": "Atomic graph; addEdge/getNeighbors/topologicalSort out — directed or undirected",
        "tags": ["graph", "adjacency", "nodes", "edges", "topology"],
        "iface": r'''export function createGraph() {
  return {
    addNode(id: string): void,
    addEdge(from: string, to: string, weight?: number): void,
    neighbors(id: string): Array<{ to: string; weight?: number }>,
    topologicalSort(): string[],
    get size(): number,
  };
}''',
        "code": r'''export function createGraph() {
  const adj = new Map<string, Array<{ to: string; weight?: number }>>();

  return {
    addNode(id) { if (!adj.has(id)) adj.set(id, []); },
    addEdge(from, to, weight) {
      this.addNode(from); this.addNode(to);
      adj.get(from)!.push({ to, weight });
    },
    neighbors(id) { return adj.get(id) ?? []; },
    topologicalSort() {
      const visited = new Set<string>();
      const order: string[] = [];
      function visit(id: string) {
        if (visited.has(id)) return;
        visited.add(id);
        for (const { to } of adj.get(id) ?? []) visit(to);
        order.unshift(id);
      }
      for (const id of adj.keys()) visit(id);
      return order;
    },
    get size() { return adj.size; },
  };
}''',
        "provides": "createGraph()",
        "depends": [],
    },
    {
        "id": "logic-fen-parse",
        "name": "FEN Chess Parser",
        "category": "logic",
        "lang": "typescript",
        "when": "Loading chess positions from FEN strings into a board array",
        "why": "Atomic FEN parser; fen in, 8x8 board + metadata out — pure string→state, no moves inside",
        "tags": ["fen", "chess", "board", "parse", "position"],
        "iface": r'''export type Piece = 'p' | 'n' | 'b' | 'r' | 'q' | 'k' | 'P' | 'N' | 'B' | 'R' | 'Q' | 'K';
export interface ParsedFen {
  board: Array<Array<Piece | null>>;
  turn: 'w' | 'b';
  castling: string;
  enPassant: string | null;
  halfmove: number;
  fullmove: number;
}
export function parseFen(fen: string): ParsedFen | null''',
        "code": r'''export function parseFen(fen: string): ParsedFen | null {
  const parts = fen.trim().split(/\s+/);
  if (parts.length < 4) return null;
  const [placement, turn, castling, enPassant, halfmove = '0', fullmove = '1'] = parts;

  const ranks = placement.split('/');
  if (ranks.length !== 8) return null;

  const board: Array<Array<Piece | null>> = [];
  for (const rank of ranks) {
    const row: Array<Piece | null> = [];
    for (const ch of rank) {
      if (/[1-8]/.test(ch)) {
        for (let i = 0; i < Number(ch); i++) row.push(null);
      } else if (/[pnbrqkPNBRQK]/.test(ch)) {
        row.push(ch as Piece);
      } else {
        return null;
      }
    }
    if (row.length !== 8) return null;
    board.push(row);
  }

  return {
    board,
    turn: turn === 'b' ? 'b' : 'w',
    castling,
    enPassant: enPassant === '-' ? null : enPassant,
    halfmove: Number(halfmove) || 0,
    fullmove: Number(fullmove) || 1,
  };
}''',
        "provides": "parseFen(fen)",
        "depends": [],
    },
    {
        "id": "logic-chess-movegen",
        "name": "Chess Move Generator",
        "category": "logic",
        "lang": "typescript",
        "when": "Enumerating legal moves for a piece on an 8x8 board",
        "why": "Atomic movegen; board + square in, legal destinations out — pure, piece-type switch only",
        "tags": ["chess", "move", "generation", "board", "pieces"],
        "iface": r'''export function generatePieceMoves(
  board: Array<Array<Piece | null>>,
  row: number,
  col: number,
): Array<[number, number]>''',
        "code": r'''const KNIGHT = [[2, 1], [2, -1], [-2, 1], [-2, -1], [1, 2], [1, -2], [-1, 2], [-1, -2]];
const KING = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]];
const DIRS: Record<'r' | 'b' | 'q', Array<[number, number]>> = {
  r: [[1, 0], [-1, 0], [0, 1], [0, -1]],
  b: [[1, 1], [1, -1], [-1, 1], [-1, -1]],
  q: [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]],
};

export function generatePieceMoves(board: Array<Array<Piece | null>>, row: number, col: number): Array<[number, number]> {
  const piece = board[row]?.[col];
  if (!piece) return [];
  const moves: Array<[number, number]> = [];
  const lower = piece.toLowerCase() as Piece;
  const isWhite = piece === piece.toUpperCase();

  function pushIf(r: number, c: number): boolean {
    if (r < 0 || r > 7 || c < 0 || c > 7) return false;
    const target = board[r][c];
    if (target === null) { moves.push([r, c]); return true; }
    const targetIsWhite = target === target.toUpperCase();
    if (targetIsWhite !== isWhite) moves.push([r, c]);
    return false;   // blocked
  }

  if (lower === 'n') {
    for (const [dr, dc] of KNIGHT) pushIf(row + dr, col + dc);
  } else if (lower === 'k') {
    for (const [dr, dc] of KING) pushIf(row + dr, col + dc);
  } else if (lower === 'p') {
    const dir = isWhite ? -1 : 1;
    pushIf(row + dir, col);                       // advance
    pushIf(row + dir, col + 1);                   // capture
    pushIf(row + dir, col - 1);                   // capture
  } else if (lower === 'r' || lower === 'b' || lower === 'q') {
    for (const [dr, dc] of DIRS[lower]) {
      let r = row + dr, c = col + dc;
      while (pushIf(r, c)) { r += dr; c += dc; }
    }
  }
  return moves;
}''',
        "provides": "generatePieceMoves(board, row, col)",
        "depends": [],
    },
    {
        "id": "logic-sudoku-solve",
        "name": "Sudoku Solver",
        "category": "logic",
        "lang": "typescript",
        "when": "Solving 9x9 sudoku puzzles with backtracking",
        "why": "Atomic solver; 9x9 grid in, solved grid or null out — pure constraint satisfaction",
        "tags": ["sudoku", "solve", "backtracking", "grid", "puzzle"],
        "iface": r'''export function solveSudoku(grid: number[][]): number[][] | null''',
        "code": r'''export function solveSudoku(grid: number[][]): number[][] | null {
  const board = grid.map((row) => [...row]);

  function isValid(r: number, c: number, v: number): boolean {
    for (let i = 0; i < 9; i++) {
      if (board[r][i] === v || board[i][c] === v) return false;
    }
    const br = Math.floor(r / 3) * 3, bc = Math.floor(c / 3) * 3;
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        if (board[br + i][bc + j] === v) return false;
      }
    }
    return true;
  }

  function solve(): boolean {
    for (let r = 0; r < 9; r++) {
      for (let c = 0; c < 9; c++) {
        if (board[r][c] !== 0) continue;
        for (let v = 1; v <= 9; v++) {
          if (isValid(r, c, v)) {
            board[r][c] = v;
            if (solve()) return true;
            board[r][c] = 0;
          }
        }
        return false;
      }
    }
    return true;
  }

  return solve() ? board : null;
}''',
        "provides": "solveSudoku(grid)",
        "depends": [],
    },
    {
        "id": "logic-tictactoe",
        "name": "Tic-Tac-Toe Win Check",
        "category": "logic",
        "lang": "typescript",
        "when": "Detecting wins/draws on a 3x3 board",
        "why": "Atomic win detector; board in, winner out — reusable by any 3x3 game UI",
        "tags": ["tictactoe", "win", "check", "board", "3x3"],
        "iface": r'''export type Cell = 'X' | 'O' | null;
export function checkTicTacToe(board: Cell[]): { winner: 'X' | 'O'; line: number[] } | { winner: null; draw: boolean }''',
        "code": r'''const LINES = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8],
  [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6],
];

export function checkTicTacToe(board: Cell[]) {
  for (const line of LINES) {
    const [a, b, c] = line;
    if (board[a] && board[a] === board[b] && board[a] === board[c]) {
      return { winner: board[a] as 'X' | 'O', line };
    }
  }
  return { winner: null, draw: board.every((c) => c !== null) };
}''',
        "provides": "checkTicTacToe(board)",
        "depends": [],
    },
    {
        "id": "logic-connect4",
        "name": "Connect Four Drop + Win",
        "category": "logic",
        "lang": "typescript",
        "when": "Handling column drops and 4-in-a-row detection",
        "why": "Atomic connect4 rules; board + column in, result out — gravity and win check only",
        "tags": ["connect4", "gravity", "win", "column", "board"],
        "iface": r'''export type Connect4Cell = 1 | 2 | null;
export function dropDisc(board: Connect4Cell[][], column: number, player: 1 | 2): { ok: boolean; row?: number }
export function checkConnect4Win(board: Connect4Cell[][], row: number, col: number): boolean''',
        "code": r'''export function dropDisc(board: Connect4Cell[][], column: number, player: 1 | 2): { ok: boolean; row?: number } {
  for (let r = board.length - 1; r >= 0; r--) {
    if (board[r][column] === null) {
      board[r][column] = player;
      return { ok: true, row: r };
    }
  }
  return { ok: false };
}

export function checkConnect4Win(board: Connect4Cell[][], row: number, col: number): boolean {
  const player = board[row][col];
  if (player === null) return false;
  const dirs = [[0, 1], [1, 0], [1, 1], [1, -1]];
  for (const [dr, dc] of dirs) {
    let count = 1;
    for (const sign of [1, -1]) {
      let r = row + dr * sign, c = col + dc * sign;
      while (r >= 0 && r < board.length && c >= 0 && c < board[0].length && board[r][c] === player) {
        count++;
        r += dr * sign; c += dc * sign;
      }
    }
    if (count >= 4) return true;
  }
  return false;
}''',
        "provides": "dropDisc(board, column, player), checkConnect4Win(board, row, col)",
        "depends": [],
    },
    {
        "id": "logic-maze-gen",
        "name": "Maze Generator",
        "category": "logic",
        "lang": "typescript",
        "when": "Procedurally generating mazes for games or puzzles",
        "why": "Atomic generator; width/height in, 2D grid out — recursive backtracker, every cell reachable",
        "tags": ["maze", "generate", "procedural", "backtracking", "grid"],
        "iface": r'''export interface MazeCell { top: boolean; right: boolean; bottom: boolean; left: boolean; visited?: boolean }
export function generateMaze(width: number, height: number): MazeCell[][]''',
        "code": r'''export function generateMaze(width: number, height: number): MazeCell[][] {
  const grid: MazeCell[][] = Array.from({ length: height }, () =>
    Array.from({ length: width }, () => ({ top: true, right: true, bottom: true, left: true })),
  );
  const stack: Array<[number, number]> = [[0, 0]];
  grid[0][0].visited = true;
  const dirs = [[0, -1], [1, 0], [0, 1], [-1, 0]];  // up right down left

  while (stack.length > 0) {
    const [r, c] = stack[stack.length - 1];
    const unvisited: Array<[number, number, number]> = [];
    for (let i = 0; i < 4; i++) {
      const nr = r + dirs[i][0], nc = c + dirs[i][1];
      if (nr >= 0 && nr < height && nc >= 0 && nc < width && !grid[nr][nc].visited) {
        unvisited.push([nr, nc, i]);
      }
    }
    if (unvisited.length === 0) { stack.pop(); continue; }
    const [nr, nc, dir] = unvisited[Math.floor(Math.random() * unvisited.length)];
    if (dir === 0) { grid[r][c].top = false; grid[nr][nc].bottom = false; }
    if (dir === 1) { grid[r][c].right = false; grid[nr][nc].left = false; }
    if (dir === 2) { grid[r][c].bottom = false; grid[nr][nc].top = false; }
    if (dir === 3) { grid[r][c].left = false; grid[nr][nc].right = false; }
    grid[nr][nc].visited = true;
    stack.push([nr, nc]);
  }
  return grid;
}''',
        "provides": "generateMaze(width, height)",
        "depends": [],
    },
    {
        "id": "logic-cellular-auto",
        "name": "Cellular Automata",
        "category": "logic",
        "lang": "typescript",
        "when": "Simulating life-like grids (Game of Life, cave generation, fire spread)",
        "why": "Atomic CA step; grid + rules in, next grid out — rule function injectable",
        "tags": ["cellular", "automata", "life", "simulation", "grid"],
        "iface": r'''export function cellularStep<T>(
  grid: T[][],
  neighborsOf: (r: number, c: number) => T[],
  nextCell: (cell: T, neighbors: T[], r: number, c: number) => T,
): T[][]''',
        "code": r'''export function cellularStep<T>(
  grid: T[][],
  neighborsOf: (r: number, c: number) => T[],
  nextCell: (cell: T, neighbors: T[], r: number, c: number) => T,
): T[][] {
  return grid.map((row, r) =>
    row.map((cell, c) => nextCell(cell, neighborsOf(r, c), r, c)),
  );
}

export function gameOfLifeStep(grid: number[][]): number[][] {
  const h = grid.length, w = grid[0]?.length ?? 0;
  function aliveNeighbors(r: number, c: number): number {
    let n = 0;
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        if (dr === 0 && dc === 0) continue;
        const nr = (r + dr + h) % h, nc = (c + dc + w) % w;
        if (grid[nr][nc] === 1) n++;
      }
    }
    return n;
  }
  return grid.map((row, r) =>
    row.map((cell, c) => {
      const n = aliveNeighbors(r, c);
      return cell === 1 ? (n === 2 || n === 3 ? 1 : 0) : (n === 3 ? 1 : 0);
    }),
  );
}''',
        "provides": "cellularStep<T>(...), gameOfLifeStep(grid)",
        "depends": [],
    },
    {
        "id": "logic-huffman",
        "name": "Huffman Coding",
        "category": "logic",
        "lang": "typescript",
        "when": "Lossless compression of text or symbol streams",
        "why": "Atomic huffman; text in, {codes, encode, decode} out — tree built from frequencies",
        "tags": ["huffman", "compress", "encode", "decode", "tree"],
        "iface": r'''export function huffmanCompress(text: string): {
  codes: Record<string, string>;
  encode: (s: string) => string;
  decode: (bits: string) => string;
}''',
        "code": r'''export function huffmanCompress(text: string) {
  const freq = new Map<string, number>();
  for (const ch of text) freq.set(ch, (freq.get(ch) ?? 0) + 1);

  interface Node { ch?: string; freq: number; left?: Node; right?: Node }
  const nodes: Node[] = [...freq.entries()].map(([ch, f]) => ({ ch, freq: f }));
  nodes.sort((a, b) => a.freq - b.freq);

  while (nodes.length > 1) {
    const a = nodes.shift()!, b = nodes.shift()!;
    const merged: Node = { freq: a.freq + b.freq, left: a, right: b };
    let i = 0;
    while (i < nodes.length && nodes[i].freq < merged.freq) i++;
    nodes.splice(i, 0, merged);
  }

  const codes: Record<string, string> = {};
  function walk(node: Node | undefined, prefix: string) {
    if (!node) return;
    if (node.ch !== undefined) codes[node.ch] = prefix || '0';
    walk(node.left, prefix + '0');
    walk(node.right, prefix + '1');
  }
  walk(nodes[0], '');

  return {
    codes,
    encode: (s) => [...s].map((ch) => codes[ch]).join(''),
    decode(bits) {
      let out = '';
      let node = nodes[0];
      for (const bit of bits) {
        node = bit === '0' ? node.left! : node.right!;
        if (node.ch !== undefined) { out += node.ch; node = nodes[0]; }
      }
      return out;
    },
  };
}''',
        "provides": "huffmanCompress(text)",
        "depends": [],
    },
    {
        "id": "logic-knapsack",
        "name": "0/1 Knapsack (DP)",
        "category": "logic",
        "lang": "typescript",
        "when": "Selecting items to maximize value under a weight budget",
        "why": "Atomic knapsack; items + capacity in, selection out — classic dynamic programming",
        "tags": ["knapsack", "dynamic", "programming", "optimization", "weight"],
        "iface": r'''export interface KnapsackItem { id: string; weight: number; value: number }
export function knapsack(items: KnapsackItem[], capacity: number): { ids: string[]; totalValue: number; totalWeight: number }''',
        "code": r'''export function knapsack(items: KnapsackItem[], capacity: number) {
  const n = items.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => Array(capacity + 1).fill(0));

  for (let i = 1; i <= n; i++) {
    for (let w = 0; w <= capacity; w++) {
      if (items[i - 1].weight <= w) {
        dp[i][w] = Math.max(dp[i - 1][w], dp[i - 1][w - items[i - 1].weight] + items[i - 1].value);
      } else {
        dp[i][w] = dp[i - 1][w];
      }
    }
  }

  const ids: string[] = [];
  let w = capacity;
  for (let i = n; i > 0 && w > 0; i--) {
    if (dp[i][w] !== dp[i - 1][w]) {
      ids.unshift(items[i - 1].id);
      w -= items[i - 1].weight;
    }
  }

  const totalWeight = ids.reduce((s, id) => s + items.find((i) => i.id === id)!.weight, 0);
  return { ids, totalValue: dp[n][capacity], totalWeight };
}''',
        "provides": "knapsack(items, capacity)",
        "depends": [],
    },
    {
        "id": "logic-nqueens",
        "name": "N-Queens Solver",
        "category": "logic",
        "lang": "typescript",
        "when": "Placing N queens on an NxN board without attacks",
        "why": "Atomic backtracker; n in, all solutions out — classic constraint search",
        "tags": ["nqueens", "backtracking", "queens", "constraint", "search"],
        "iface": r'''export function solveNQueens(n: number): number[][]''',
        "code": r'''export function solveNQueens(n: number): number[][] {
  const solutions: number[][] = [];
  const cols = new Set<number>();
  const diag1 = new Set<number>();
  const diag2 = new Set<number>();
  const board: number[] = [];

  function place(row: number) {
    if (row === n) { solutions.push([...board]); return; }
    for (let col = 0; col < n; col++) {
      if (cols.has(col) || diag1.has(row - col) || diag2.has(row + col)) continue;
      cols.add(col); diag1.add(row - col); diag2.add(row + col);
      board.push(col);
      place(row + 1);
      board.pop();
      cols.delete(col); diag1.delete(row - col); diag2.delete(row + col);
    }
  }

  place(0);
  return solutions;
}''',
        "provides": "solveNQueens(n)",
        "depends": [],
    },
    {
        "id": "logic-regex-match",
        "name": "Regex Matcher (No Deps)",
        "category": "logic",
        "lang": "typescript",
        "when": "Simple wildcard/glob matching without regex engines (filenames, filters)",
        "why": "Atomic glob matcher; pattern + text in, boolean out — supports * and ?",
        "tags": ["regex", "glob", "wildcard", "match", "pattern"],
        "iface": r'''export function globMatch(pattern: string, text: string): boolean
export function wildcardToRegex(pattern: string): RegExp''',
        "code": r'''export function wildcardToRegex(pattern: string): RegExp {
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.');
  return new RegExp(`^${escaped}$`);
}

export function globMatch(pattern: string, text: string): boolean {
  return wildcardToRegex(pattern).test(text);
}''',
        "provides": "globMatch(pattern, text), wildcardToRegex(pattern)",
        "depends": [],
    },
    {
        "id": "logic-infix-eval",
        "name": "Infix Expression Evaluator",
        "category": "logic",
        "lang": "typescript",
        "when": "Evaluating arithmetic strings like \"(2+3)*4\" safely",
        "why": "Atomic evaluator; expression in, number out — shunting-yard, no eval() used",
        "tags": ["math", "evaluate", "expression", "parser", "calculator"],
        "iface": r'''export function evaluateExpression(expr: string): number''',
        "code": r'''export function evaluateExpression(expr: string): number {
  const tokens = expr.replace(/\s+/g, '').match(/(\d+\.?\d*|[+\-*/()])/g);
  if (!tokens) throw new Error('invalid_expression');

  const output: string[] = [];
  const ops: string[] = [];
  const precedence: Record<string, number> = { '+': 1, '-': 1, '*': 2, '/': 2 };

  for (const t of tokens) {
    if (/\d/.test(t)) {
      output.push(t);
    } else if (t === '(') {
      ops.push(t);
    } else if (t === ')') {
      while (ops.length && ops[ops.length - 1] !== '(') output.push(ops.pop()!);
      ops.pop();
    } else {
      while (ops.length && precedence[ops[ops.length - 1]] >= precedence[t]) output.push(ops.pop()!);
      ops.push(t);
    }
  }
  while (ops.length) output.push(ops.pop()!);

  const stack: number[] = [];
  for (const t of output) {
    if (/\d/.test(t)) stack.push(Number(t));
    else {
      const b = stack.pop()!, a = stack.pop()!;
      if (t === '+') stack.push(a + b);
      if (t === '-') stack.push(a - b);
      if (t === '*') stack.push(a * b);
      if (t === '/') stack.push(a / b);
    }
  }
  return stack[0];
}''',
        "provides": "evaluateExpression(expr)",
        "depends": [],
    },
    {
        "id": "logic-tokenizer",
        "name": "Tokenizer",
        "category": "logic",
        "lang": "typescript",
        "when": "Splitting source text into tokens for parsers or analysis",
        "why": "Atomic lexer; source + token rules in, token list out — rule-driven, position-tracked",
        "tags": ["tokenizer", "lexer", "parse", "tokens", "source"],
        "iface": r'''export interface Token { type: string; value: string; pos: number }
export interface TokenRule { type: string; pattern: RegExp }
export function tokenize(source: string, rules: TokenRule[], skip?: Set<string>): Token[]''',
        "code": r'''export function tokenize(source: string, rules: TokenRule[], skip: Set<string> = new Set(['ws'])): Token[] {
  const tokens: Token[] = [];
  let pos = 0;
  let safety = 0;

  while (pos < source.length && safety++ < 1_000_000) {
    let matched = false;
    for (const rule of rules) {
      rule.pattern.lastIndex = 0;
      const m = rule.pattern.exec(source.slice(pos));
      if (m && m.index === 0 && m[0].length > 0) {
        if (!skip.has(rule.type)) tokens.push({ type: rule.type, value: m[0], pos });
        pos += m[0].length;
        matched = true;
        break;
      }
    }
    if (!matched) throw new Error(`unexpected char at ${pos}: '${source[pos]}'`);
  }
  return tokens;
}

export const TYPESCRIPT_BASIC_RULES: TokenRule[] = [
  { type: 'ws', pattern: /\s+/y },
  { type: 'string', pattern: /"([^"\\]|\\.)*"|'([^'\\]|\\.)*'/y },
  { type: 'number', pattern: /\d+\.?\d*/y },
  { type: 'ident', pattern: /[a-zA-Z_$][a-zA-Z0-9_$]*/y },
  { type: 'punct', pattern: /[{}()[\];,.:?]/y },
  { type: 'op', pattern: /[+\-*/=<>!&|]+/y },
];''',
        "provides": "tokenize(source, rules, skip?), TYPESCRIPT_BASIC_RULES",
        "depends": [],
    },
    {
        "id": "logic-shuffle",
        "name": "Fisher-Yates Shuffle",
        "category": "logic",
        "lang": "typescript",
        "when": "Unbiased random ordering (card decks, question order, playlists)",
        "why": "Atomic shuffle; array in, shuffled copy out — uniform distribution, no mutation",
        "tags": ["shuffle", "random", "fisher", "yates", "order"],
        "iface": r'''export function shuffle<T>(items: T[], random?: () => number): T[]''',
        "code": r'''export function shuffle<T>(items: T[], random: () => number = Math.random): T[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}''',
        "provides": "shuffle<T>(items, random?)",
        "depends": [],
    },
    {
        "id": "logic-prime-sieve",
        "name": "Sieve of Eratosthenes",
        "category": "logic",
        "lang": "typescript",
        "when": "Generating primes up to N efficiently (math tools, number puzzles)",
        "why": "Atomic sieve; limit in, prime list + isPrime out — O(n log log n)",
        "tags": ["prime", "sieve", "number", "math", "primes"],
        "iface": r'''export function sievePrimes(limit: number): number[]
export function isPrime(n: number): boolean''',
        "code": r'''export function sievePrimes(limit: number): number[] {
  if (limit < 2) return [];
  const sieve = new Uint8Array(limit + 1);
  sieve[0] = sieve[1] = 1;
  for (let i = 2; i * i <= limit; i++) {
    if (!sieve[i]) {
      for (let j = i * i; j <= limit; j += i) sieve[j] = 1;
    }
  }
  const primes: number[] = [];
  for (let i = 2; i <= limit; i++) if (!sieve[i]) primes.push(i);
  return primes;
}

export function isPrime(n: number): boolean {
  if (n < 2) return false;
  if (n < 4) return true;
  if (n % 2 === 0 || n % 3 === 0) return false;
  for (let i = 5; i * i <= n; i += 6) {
    if (n % i === 0 || n % (i + 2) === 0) return false;
  }
  return true;
}''',
        "provides": "sievePrimes(limit), isPrime(n)",
        "depends": [],
    },
]
