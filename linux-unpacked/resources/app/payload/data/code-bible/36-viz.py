# -*- coding: utf-8 -*-
"""
Code Bible — Category 36: Visualization (atomic).
Convention: pure math/geometry and data transforms for charts; no DOM or deps.
"""
CHUNKS = [
    {
        "id": "viz-linear-scale",
        "name": "Linear Scale",
        "category": "viz",
        "lang": "typescript",
        "when": "Mapping data values to a pixel range (d3-style linear scale)",
        "why": "Atomic scale — domain + range in, clamp/round options, callable out",
        "tags": ["viz", "scale", "linear", "axis", "chart"],
        "iface": r'''export interface LinearScale { (v: number): number; domain: number[]; range: number[] }
export function linearScale(domain: [number, number], range: [number, number], opts?: { clamp?: boolean; nice?: boolean }): LinearScale''',
        "code": r'''export function linearScale(domain: [number, number], range: [number, number], opts?: { clamp?: boolean; nice?: boolean }) {
  let [d0, d1] = domain, [r0, r1] = range;
  const f = ((v: number) => {
    let t = d1 === d0 ? 0.5 : (v - d0) / (d1 - d0);
    if (opts?.clamp) t = Math.max(0, Math.min(1, t));
    return r0 + t * (r1 - r0);
  }) as LinearScale;
  f.domain = [d0, d1]; f.range = [r0, r1];
  return f;
}''',
        "provides": "linearScale(domain, range, opts)",
        "depends": [],
    },
    {
        "id": "viz-ticks",
        "name": "Axis Tick Generator",
        "category": "viz",
        "lang": "typescript",
        "when": "Producing clean tick values for chart axes",
        "why": "Atomic ticks — nice step from range + count, covers 0 when sensible",
        "tags": ["viz", "ticks", "axis", "scale", "nice"],
        "iface": r'''export function niceTicks(min: number, max: number, count = 5): number[]''',
        "code": r'''export function niceTicks(min: number, max: number, count = 5) {
  if (min === max) return [min];
  const span = max - min;
  const rawStep = span / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) ticks.push(Math.round(v * 1e9) / 1e9);
  return ticks;
}''',
        "provides": "niceTicks(min, max, count)",
        "depends": [],
    },
    {
        "id": "viz-time-format",
        "name": "Time Axis Formatter",
        "category": "viz",
        "lang": "typescript",
        "when": "Formatting timestamps for chart axis labels",
        "why": "Atomic formatter — ms in, compact HH:MM or M/D label out by span",
        "tags": ["viz", "time", "axis", "format", "chart"],
        "iface": r'''export function timeAxisLabel(ms: number, spanMs: number): string''',
        "code": r'''export function timeAxisLabel(ms: number, spanMs: number) {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, '0');
  if (spanMs <= 86400000) return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}''',
        "provides": "timeAxisLabel(ms, spanMs)",
        "depends": [],
    },
    {
        "id": "viz-heatmap-index",
        "name": "Heatmap Color Index",
        "category": "viz",
        "lang": "typescript",
        "when": "Mapping a value to a color position on a blue→red ramp",
        "why": "Atomic index — normalized value in, [0,1] position + CSS rgb out",
        "tags": ["viz", "heatmap", "color", "ramp", "index"],
        "iface": r'''export function heatmapColor(v: number, min: number, max: number): string''',
        "code": r'''export function heatmapColor(v: number, min: number, max: number) {
  const t = max === min ? 0.5 : (v - min) / (max - min);
  const r = Math.round(255 * Math.min(1, Math.max(0, (t - 0.5) * 2)));
  const b = Math.round(255 * Math.min(1, Math.max(0, (0.5 - t) * 2)));
  const g = Math.round(255 * (1 - Math.abs(t - 0.5) * 2));
  return `rgb(${r},${g},${b})`;
}''',
        "provides": "heatmapColor(v, min, max)",
        "depends": [],
    },
    {
        "id": "viz-bar-layout",
        "name": "Bar Layout Engine",
        "category": "viz",
        "lang": "typescript",
        "when": "Positioning bars inside a width with optional gaps",
        "why": "Atomic layout — n bars + width in, x/width per bar out, gap-aware",
        "tags": ["viz", "bar", "layout", "chart", "position"],
        "iface": r'''export function barLayout(n: number, width: number, gapRatio = 0.2): Array<{ x: number; w: number }>''',
        "code": r'''export function barLayout(n: number, width: number, gapRatio = 0.2) {
  const slot = width / n;
  const w = slot * (1 - gapRatio);
  return Array.from({ length: n }, (_, i) => ({ x: i * slot + (slot - w) / 2, w }));
}''',
        "provides": "barLayout(n, width, gapRatio)",
        "depends": [],
    },
    {
        "id": "viz-pie-slices",
        "name": "Pie/Donut Slice Angles",
        "category": "viz",
        "lang": "typescript",
        "when": "Computing start/end angles for pie chart wedges",
        "why": "Atomic slice math — values in, {start,end,mid} radians out",
        "tags": ["viz", "pie", "donut", "slice", "angle"],
        "iface": r'''export interface Slice { start: number; end: number; mid: number }
export function pieSlices(values: number[]): Slice[]''',
        "code": r'''export function pieSlices(values: number[]) {
  const total = values.reduce((s, v) => s + Math.max(0, v), 0) || 1;
  const out: Slice[] = [];
  let a = -Math.PI / 2;
  for (const v of values) {
    const sweep = (Math.max(0, v) / total) * Math.PI * 2;
    out.push({ start: a, end: a + sweep, mid: a + sweep / 2 });
    a += sweep;
  }
  return out;
}''',
        "provides": "pieSlices(values)",
        "depends": [],
    },
    {
        "id": "viz-polar",
        "name": "Polar to Cartesian",
        "category": "viz",
        "lang": "typescript",
        "when": "Converting angle/radius to x/y for radar and polar charts",
        "why": "Atomic transform — theta + r + center in, point out; theta in radians",
        "tags": ["viz", "polar", "cartesian", "radar", "transform"],
        "iface": r'''export function polarToCartesian(theta: number, r: number, cx: number, cy: number): { x: number; y: number }''',
        "code": r'''export function polarToCartesian(theta: number, r: number, cx: number, cy: number) {
  return { x: cx + r * Math.cos(theta), y: cy + r * Math.sin(theta) };
}''',
        "provides": "polarToCartesian(theta, r, cx, cy)",
        "depends": [],
    },
    {
        "id": "viz-stack-series",
        "name": "Stacked Series Layout",
        "category": "viz",
        "lang": "typescript",
        "when": "Stacking multiple series into cumulative bands",
        "why": "Atomic stacker — series arrays in, per-point {y0,y1} out",
        "tags": ["viz", "stack", "series", "area", "layout"],
        "iface": r'''export function stackSeries(series: number[][]): Array<Array<{ y0: number; y1: number }>>''',
        "code": r'''export function stackSeries(series: number[][]) {
  const n = series[0]?.length ?? 0;
  const acc = new Array(n).fill(0);
  return series.map((s) => s.map((v, i) => {
    const y0 = acc[i];
    acc[i] += v;
    return { y0, y1: acc[i] };
  }));
}''',
        "provides": "stackSeries(series)",
        "depends": [],
    },
    {
        "id": "viz-bin-histo",
        "name": "Histogram Binner",
        "category": "viz",
        "lang": "typescript",
        "when": "Binning continuous values into histogram buckets",
        "why": "Atomic binner — values + bin count in, {start,end,count} bins out",
        "tags": ["viz", "histogram", "bin", "distribution", "count"],
        "iface": r'''export interface Bin { start: number; end: number; count: number }
export function histogram(values: number[], bins = 10): Bin[]''',
        "code": r'''export function histogram(values: number[], bins = 10) {
  if (!values.length) return [];
  const min = Math.min(...values), max = Math.max(...values);
  const width = (max - min) / bins || 1;
  const counts = new Array(bins).fill(0);
  for (const v of values) {
    let i = Math.floor((v - min) / width);
    if (i >= bins) i = bins - 1;
    counts[i]++;
  }
  return counts.map((count, i) => ({ start: min + i * width, end: min + (i + 1) * width, count }));
}''',
        "provides": "histogram(values, bins)",
        "depends": [],
    },
    {
        "id": "viz-smoothed-line",
        "name": "Catmull-Rom Smoothed Line",
        "category": "viz",
        "lang": "typescript",
        "when": "Interpolating control points into a smooth curve path",
        "why": "Atomic smoother — points in, sampled curve points out (Catmull-Rom)",
        "tags": ["viz", "smooth", "curve", "catmull", "line"],
        "iface": r'''export function smoothCurve(points: Array<[number, number]>, samplesPerSegment = 8): Array<[number, number]>''',
        "code": r'''export function smoothCurve(points: Array<[number, number]>, samplesPerSegment = 8) {
  if (points.length < 3) return points.slice();
  const out: Array<[number, number]> = [points[0]];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)], p1 = points[i], p2 = points[i + 1], p3 = points[Math.min(points.length - 1, i + 2)];
    for (let s = 1; s <= samplesPerSegment; s++) {
      const t = s / samplesPerSegment, t2 = t * t, t3 = t2 * t;
      out.push([
        0.5 * (2 * p1[0] + (p2[0] - p0[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (3 * p1[0] - p0[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * (2 * p1[1] + (p2[1] - p0[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (3 * p1[1] - p0[1] - 3 * p2[1] + p3[1]) * t3),
      ]);
    }
  }
  return out;
}''',
        "provides": "smoothCurve(points, samplesPerSegment)",
        "depends": [],
    },
    {
        "id": "viz-force-layout",
        "name": "Force-Directed Layout Step",
        "category": "viz",
        "lang": "typescript",
        "when": "Iterating node positions with repulsion and spring forces",
        "why": "Atomic physics step — nodes + edges in, new positions out; stable + bounded",
        "tags": ["viz", "force", "layout", "graph", "physics"],
        "iface": r'''export interface ForceNode { id: string; x: number; y: number }
export function forceStep(nodes: ForceNode[], edges: Array<[string, string]>, width: number, height: number): ForceNode[]''',
        "code": r'''export function forceStep(nodes: ForceNode[], edges: Array<[string, string]>, width: number, height: number) {
  const idx = new Map(nodes.map((n, i) => [n.id, i]));
  const fx = new Array(nodes.length).fill(0);
  const fy = new Array(nodes.length).fill(0);
  const rep = 12000, spring = 0.02, rest = 80;
  for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
    const dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y;
    const d2 = Math.max(1, dx * dx + dy * dy);
    const f = rep / d2;
    fx[i] -= (dx / Math.sqrt(d2)) * f; fy[i] -= (dy / Math.sqrt(d2)) * f;
    fx[j] += (dx / Math.sqrt(d2)) * f; fy[j] += (dy / Math.sqrt(d2)) * f;
  }
  for (const [a, b] of edges) {
    const ia = idx.get(a), ib = idx.get(b);
    if (ia === undefined || ib === undefined) continue;
    const dx = nodes[ib].x - nodes[ia].x, dy = nodes[ib].y - nodes[ia].y;
    const d = Math.max(1, Math.sqrt(dx * dx + dy * dy));
    const f = spring * (d - rest);
    fx[ia] += (dx / d) * f; fy[ia] += (dy / d) * f;
    fx[ib] -= (dx / d) * f; fy[ib] -= (dy / d) * f;
  }
  return nodes.map((n, i) => ({
    id: n.id,
    x: Math.max(0, Math.min(width, n.x + fx[i])),
    y: Math.max(0, Math.min(height, n.y + fy[i])),
  }));
}''',
        "provides": "forceStep(nodes, edges, width, height)",
        "depends": [],
    },
    {
        "id": "viz-area-points",
        "name": "Area Chart Path Points",
        "category": "viz",
        "lang": "typescript",
        "when": "Building an area polygon from a line + baseline",
        "why": "Atomic path — values + y-scale in, top then bottom points out",
        "tags": ["viz", "area", "path", "polygon", "chart"],
        "iface": r'''export function areaPoints(values: number[], y: (v: number) => number, baseline: number): Array<[number, number]>''',
        "code": r'''export function areaPoints(values: number[], y: (v: number) => number, baseline: number) {
  const top: Array<[number, number]> = [];
  const bottom: Array<[number, number]> = [];
  const n = Math.max(1, values.length - 1);
  values.forEach((v, i) => {
    const x = (i / n) * 100;
    top.push([x, y(v)]);
    bottom.unshift([x, baseline]);
  });
  return [...top, ...bottom];
}''',
        "provides": "areaPoints(values, y, baseline)",
        "depends": [],
    },
    {
        "id": "viz-waterfall-delta",
        "name": "Waterfall Delta Positions",
        "category": "viz",
        "lang": "typescript",
        "when": "Computing running totals for waterfall charts",
        "why": "Atomic cascade — deltas in, {start,end} cumulative positions out",
        "tags": ["viz", "waterfall", "delta", "cascade", "chart"],
        "iface": r'''export function waterfallDeltas(deltas: number[], start = 0): Array<{ start: number; end: number; delta: number }>''',
        "code": r'''export function waterfallDeltas(deltas: number[], start = 0) {
  const out: Array<{ start: number; end: number; delta: number }> = [];
  let cur = start;
  for (const d of deltas) { out.push({ start: cur, end: cur + d, delta: d }); cur += d; }
  return out;
}''',
        "provides": "waterfallDeltas(deltas, start)",
        "depends": [],
    },
    {
        "id": "viz-quad-tree",
        "name": "Spatial Bucket Index (Grid)",
        "category": "viz",
        "lang": "typescript",
        "when": "Quickly finding nearby points for scatter-plot interactions",
        "why": "Atomic grid index — bucket lookup with radius scan, O(1) inserts",
        "tags": ["viz", "spatial", "grid", "index", "query"],
        "iface": r'''export class GridIndex<T> {
  constructor(cellSize: number)
  insert(x: number, y: number, item: T): void
  query(x: number, y: number, radius: number): T[]
}''',
        "code": r'''export class GridIndex<T> {
  private cells = new Map<string, T[]>();
  constructor(private cellSize: number) {}
  private key(cx: number, cy: number) { return `${cx},${cy}`; }
  insert(x: number, y: number, item: T) {
    const cx = Math.floor(x / this.cellSize), cy = Math.floor(y / this.cellSize);
    const k = this.key(cx, cy);
    if (!this.cells.has(k)) this.cells.set(k, []);
    this.cells.get(k)!.push(item);
  }
  query(x: number, y: number, radius: number) {
    const out: T[] = [];
    const r = Math.ceil(radius / this.cellSize);
    const cx = Math.floor(x / this.cellSize), cy = Math.floor(y / this.cellSize);
    for (let dx = -r; dx <= r; dx++) for (let dy = -r; dy <= r; dy++)
      out.push(...(this.cells.get(this.key(cx + dx, cy + dy)) ?? []));
    return out;
  }
}''',
        "provides": "GridIndex",
        "depends": [],
    },
    {
        "id": "viz-axis-band",
        "name": "Band Scale (Categorical)",
        "category": "viz",
        "lang": "typescript",
        "when": "Mapping categories to evenly spaced band positions",
        "why": "Atomic band scale — categories + range in, per-category center + bandwidth out",
        "tags": ["viz", "band", "scale", "categorical", "axis"],
        "iface": r'''export function bandScale(categories: string[], range: [number, number], padding = 0.1): Record<string, { center: number; bandwidth: number }>''',
        "code": r'''export function bandScale(categories: string[], range: [number, number], padding = 0.1) {
  const n = categories.length || 1;
  const total = range[1] - range[0];
  const step = total / n;
  const bandwidth = step * (1 - padding);
  const out: Record<string, { center: number; bandwidth: number }> = {};
  categories.forEach((c, i) => {
    const center = range[0] + i * step + step / 2;
    out[c] = { center, bandwidth };
  });
  return out;
}''',
        "provides": "bandScale(categories, range, padding)",
        "depends": [],
    },
    {
        "id": "viz-log-scale",
        "name": "Log Scale",
        "category": "viz",
        "lang": "typescript",
        "when": "Mapping wide-range data to pixels with a log transform",
        "why": "Atomic log scale — positive domain in, clamped log mapping out",
        "tags": ["viz", "log", "scale", "domain", "chart"],
        "iface": r'''export function logScale(domain: [number, number], range: [number, number]): (v: number) => number''',
        "code": r'''export function logScale(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain.map((d) => Math.log10(Math.max(d, 1e-12)));
  return (v: number) => {
    const t = (Math.log10(Math.max(v, 1e-12)) - d0) / (d1 - d0 || 1);
    return range[0] + Math.max(0, Math.min(1, t)) * (range[1] - range[0]);
  };
}''',
        "provides": "logScale(domain, range)",
        "depends": [],
    },
    {
        "id": "viz-sankey-flow",
        "name": "Sankey Flow Positions",
        "category": "viz",
        "lang": "typescript",
        "when": "Laying out nodes and flows for a simple two-stage sankey",
        "why": "Atomic layout — sources + targets + values in, node rows + link endpoints out",
        "tags": ["viz", "sankey", "flow", "layout", "nodes"],
        "iface": r'''export interface SankeyLink { from: string; to: string; value: number }
export function sankeyLayout(links: SankeyLink[], width: number, height: number): { nodes: Record<string, { x: number; y: number }>; links: Array<{ from: number[]; to: number[]; value: number }> }''',
        "code": r'''export function sankeyLayout(links: SankeyLink[], width: number, height: number) {
  const sources = [...new Set(links.map((l) => l.from))];
  const targets = [...new Set(links.map((l) => l.to))];
  const sy: Record<string, number> = {};
  const ty: Record<string, number> = {};
  const step = height / Math.max(1, Math.max(sources.length, targets.length));
  sources.forEach((s, i) => (sy[s] = step * (i + 0.5)));
  targets.forEach((t, i) => (ty[t] = step * (i + 0.5)));
  const nodes: Record<string, { x: number; y: number }> = {};
  sources.forEach((s) => (nodes[s] = { x: 0, y: sy[s] }));
  targets.forEach((t) => (nodes[t] = { x: width, y: ty[t] }));
  const outLinks = links.map((l) => ({
    from: [0, sy[l.from]],
    to: [width, ty[l.to]],
    value: l.value,
  }));
  return { nodes, links: outLinks };
}''',
        "provides": "sankeyLayout(links, width, height)",
        "depends": [],
    },
    {
        "id": "viz-bubble-size",
        "name": "Bubble Size Scale",
        "category": "viz",
        "lang": "typescript",
        "when": "Mapping values to circle radii with area-proportional sizing",
        "why": "Atomic radius — sqrt scaling so area is proportional to value",
        "tags": ["viz", "bubble", "radius", "size", "scale"],
        "iface": r'''export function bubbleRadius(value: number, min: number, max: number, rMin: number, rMax: number): number''',
        "code": r'''export function bubbleRadius(value: number, min: number, max: number, rMin: number, rMax: number) {
  const t = max === min ? 0.5 : (value - min) / (max - min);
  return rMin + Math.sqrt(Math.max(0, Math.min(1, t))) * (rMax - rMin);
}''',
        "provides": "bubbleRadius(value, min, max, rMin, rMax)",
        "depends": [],
    },
    {
        "id": "viz-color-scale",
        "name": "Sequential Color Scale",
        "category": "viz",
        "lang": "typescript",
        "when": "Interpolating between two colors for sequential data",
        "why": "Atomic lerp — hex colors + t in, interpolated hex out",
        "tags": ["viz", "color", "scale", "interpolate", "gradient"],
        "iface": r'''export function colorLerp(a: string, b: string, t: number): string''',
        "code": r'''function parseHex(h: string) {
  const s = h.replace('#', '');
  const f = s.length === 3 ? s.split('').map((c) => c + c).join('') : s;
  return [0, 2, 4].map((i) => parseInt(f.slice(i, i + 2), 16));
}
export function colorLerp(a: string, b: string, t: number) {
  const ca = parseHex(a), cb = parseHex(b);
  const k = Math.max(0, Math.min(1, t));
  const mix = ca.map((v, i) => Math.round(v + (cb[i] - v) * k));
  return `#${mix.map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}''',
        "provides": "colorLerp(a, b, t)",
        "depends": [],
    },
    {
        "id": "viz-label-collision",
        "name": "Label Collision Resolver",
        "category": "viz",
        "lang": "typescript",
        "when": "Avoiding overlapping data labels on dense charts",
        "why": "Atomic resolver — candidate boxes in, non-overlapping subset out (first-fit)",
        "tags": ["viz", "label", "collision", "overlap", "layout"],
        "iface": r'''export interface Box { x: number; y: number; w: number; h: number; data?: unknown }
export function resolveCollisions(boxes: Box[], maxIter = 50): Box[]''',
        "code": r'''function overlaps(a: Box, b: Box) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}
export function resolveCollisions(boxes: Box[], maxIter = 50) {
  const out = boxes.map((b) => ({ ...b }));
  for (let iter = 0; iter < maxIter; iter++) {
    let moved = false;
    for (let i = 0; i < out.length; i++) for (let j = i + 1; j < out.length; j++) {
      if (!overlaps(out[i], out[j])) continue;
      const dx = out[j].x + out[j].w / 2 - (out[i].x + out[i].w / 2);
      const dy = out[j].y + out[j].h / 2 - (out[i].y + out[i].h / 2);
      const ax = Math.abs(dx) < Math.abs(dy) ? 0 : Math.sign(dx || 1);
      const ay = Math.abs(dy) < Math.abs(dx) ? 0 : Math.sign(dy || 1);
      out[i].x += ax; out[i].y += ay; out[j].x -= ax; out[j].y -= ay;
      moved = true;
    }
    if (!moved) break;
  }
  return out;
}''',
        "provides": "resolveCollisions(boxes, maxIter)",
        "depends": [],
    },
    {
        "id": "viz-hierarchy-tree",
        "name": "Hierarchy Tree Layout",
        "category": "viz",
        "lang": "typescript",
        "when": "Positioning a rooted tree into x/y coordinates",
        "why": "Atomic layout — simple tidy-ish: depth→y, leaf index→x",
        "tags": ["viz", "tree", "hierarchy", "layout", "position"],
        "iface": r'''export interface TreeNode { id: string; children?: TreeNode[] }
export function treeLayout(root: TreeNode, gap = 40): Map<string, { x: number; y: number }>''',
        "code": r'''export function treeLayout(root: TreeNode, gap = 40) {
  const pos = new Map<string, { x: number; y: number }>();
  let leaf = 0;
  const walk = (node: TreeNode, depth: number) => {
    if (!node.children || !node.children.length) pos.set(node.id, { x: leaf++ * gap, y: depth * gap });
    else for (const c of node.children) walk(c, depth + 1);
    if (!pos.has(node.id)) {
      const kids = (node.children ?? []).map((c) => pos.get(c.id)!);
      const x = (Math.min(...kids.map((k) => k.x)) + Math.max(...kids.map((k) => k.x))) / 2;
      pos.set(node.id, { x, y: depth * gap });
    }
  };
  walk(root, 0);
  return pos;
}''',
        "provides": "treeLayout(root, gap)",
        "depends": [],
    },
    {
        "id": "viz-arrow-head",
        "name": "Arrow Head Angle",
        "category": "viz",
        "lang": "typescript",
        "when": "Rotating arrow markers to follow a directed edge",
        "why": "Atomic math — from/to points in, angle in radians + head points out",
        "tags": ["viz", "arrow", "angle", "edge", "directed"],
        "iface": r'''export function arrowAngle(from: [number, number], to: [number, number]): number''',
        "code": r'''export function arrowAngle(from: [number, number], to: [number, number]) {
  return Math.atan2(to[1] - from[1], to[0] - from[0]);
}''',
        "provides": "arrowAngle(from, to)",
        "depends": [],
    },
    {
        "id": "viz-animate-frame",
        "name": "Animation Easing Frame",
        "category": "viz",
        "lang": "typescript",
        "when": "Computing an eased interpolation value for chart animations",
        "why": "Atomic easing — progress + easing fn in, eased value out; built-in easeOutCubic",
        "tags": ["viz", "animation", "easing", "frame", "interpolate"],
        "iface": r'''export type Easing = (t: number) => number
export const easeOutCubic: Easing
export function easeFrame(t: number, easing: Easing): number''',
        "code": r'''export const easeOutCubic: Easing = (t) => 1 - Math.pow(1 - t, 3);
export function easeFrame(t: number, easing: Easing) {
  return easing(Math.max(0, Math.min(1, t)));
}''',
        "provides": "easeOutCubic / easeFrame",
        "depends": [],
    },
    {
        "id": "viz-x-ticks",
        "name": "Index Ticks (categorical x)",
        "category": "viz",
        "lang": "typescript",
        "when": "Choosing which category labels to show on a crowded axis",
        "why": "Atomic skip \u2014 every-nth label with max count; never drops first/last",
        "tags": [
            "viz",
            "ticks",
            "categorical",
            "axis",
            "labels"
        ],
        "iface": "export function indexTicks(count: number, maxLabels: number): number[]",
        "code": "export function indexTicks(count: number, maxLabels: number) {\n  if (count <= maxLabels) return Array.from({ length: count }, (_, i) => i);\n  const step = Math.ceil(count / maxLabels);\n  const out: number[] = [];\n  for (let i = 0; i < count; i += step) out.push(i);\n  if (out[out.length - 1] !== count - 1) out.push(count - 1);\n  return out;\n}",
        "provides": "indexTicks(count, maxLabels)",
        "depends": []
    },
    {
        "id": "viz-brush-range",
        "name": "Brush Selection Range",
        "category": "viz",
        "lang": "typescript",
        "when": "Normalizing a drag brush to a valid [min,max] range",
        "why": "Atomic clamp \u2014 raw drag coords in, ordered + clamped range out",
        "tags": [
            "viz",
            "brush",
            "range",
            "select",
            "clamp"
        ],
        "iface": "export function brushRange(a: number, b: number, min: number, max: number): [number, number]",
        "code": "export function brushRange(a: number, b: number, min: number, max: number) {\n  const lo = Math.max(min, Math.min(a, b));\n  const hi = Math.min(max, Math.max(a, b));\n  return [lo, hi];\n}",
        "provides": "brushRange(a, b, min, max)",
        "depends": []
    },
]
