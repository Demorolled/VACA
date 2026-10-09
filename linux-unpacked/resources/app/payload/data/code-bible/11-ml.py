# -*- coding: utf-8 -*-
"""
Code Bible — Category 11: ML & AI (atomic, single-responsibility).
Convention: pure functions/classes, no side effects; numeric arrays are number[].
"""
CHUNKS = [
    {
        "id": "ml-linear-regression",
        "name": "Linear Regression (Least Squares)",
        "category": "ml",
        "lang": "typescript",
        "when": "Fitting a line y = slope*x + intercept to (x, y) pairs and predicting new x",
        "why": "Atomic fit/predict pair via closed-form least squares — no iteration, no deps",
        "tags": ["ml", "linear", "regression", "least-squares", "fit", "predict"],
        "iface": r'''export interface LinearRegressionResult { slope: number; intercept: number; predict(x: number): number }
export function linearRegression(points: Array<[number, number]>): LinearRegressionResult''',
        "code": r'''export function linearRegression(points: Array<[number, number]>) {
  const n = points.length;
  let sx = 0, sy = 0, sxy = 0, sxx = 0;
  for (const [x, y] of points) { sx += x; sy += y; sxy += x * y; sxx += x * x; }
  const denom = n * sxx - sx * sx;
  const slope = denom === 0 ? 0 : (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  return { slope, intercept, predict: (x: number) => slope * x + intercept };
}''',
        "provides": "linearRegression(points)",
        "depends": [],
    },
    {
        "id": "ml-kmeans",
        "name": "K-Means Clustering",
        "category": "ml",
        "lang": "typescript",
        "when": "Grouping points into k clusters by euclidean proximity",
        "why": "Atomic Lloyd's algorithm: centroids + assignments, k and iterations in, result out",
        "tags": ["ml", "kmeans", "cluster", "centroid", "unsupervised"],
        "iface": r'''export interface KMeansResult { centroids: number[][]; assignments: number[] }
export function kMeans(points: number[][], k: number, maxIter = 100): KMeansResult''',
        "code": r'''function dist(a: number[], b: number[]) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += (a[i] - b[i]) ** 2;
  return Math.sqrt(s);
}
export function kMeans(points: number[][], k: number, maxIter = 100) {
  // Farthest-first seeding for stable, spread-out centroids.
  const centroids: number[][] = [points[0].slice()];
  while (centroids.length < k) {
    let best: number[] | null = null, bestD = -1;
    for (const p of points) {
      const d = Math.min(...centroids.map((c) => dist(p, c)));
      if (d > bestD) { bestD = d; best = p; }
    }
    centroids.push(best!.slice());
  }
  const assignments = new Array(points.length).fill(0);
  for (let iter = 0; iter < maxIter; iter++) {
    let moved = false;
    points.forEach((p, i) => {
      let ci = 0, bd = Infinity;
      centroids.forEach((c, j) => { const d = dist(p, c); if (d < bd) { bd = d; ci = j; } });
      if (assignments[i] !== ci) { assignments[i] = ci; moved = true; }
    });
    if (!moved) break;
    centroids.forEach((_, j) => {
      const members = points.filter((_, i) => assignments[i] === j);
      if (!members.length) return;
      const dim = points[0].length;
      centroids[j] = Array.from({ length: dim }, (_, d) =>
        members.reduce((s, m) => s + m[d], 0) / members.length);
    });
  }
  return { centroids, assignments };
}''',
        "provides": "kMeans(points, k, maxIter)",
        "depends": [],
    },
    {
        "id": "ml-knn",
        "name": "K-Nearest Neighbors Classifier",
        "category": "ml",
        "lang": "typescript",
        "when": "Classifying an unlabeled point by majority vote of its k nearest labeled neighbors",
        "why": "Atomic lazy classifier — no training phase, distance + vote only",
        "tags": ["ml", "knn", "classifier", "distance", "vote"],
        "iface": r'''export interface KnnSample { x: number[]; label: string }
export function knn(train: KnnSample[], query: number[], k = 3): string''',
        "code": r'''export function knn(train: KnnSample[], query: number[], k = 3) {
  const dist = (a: number[], b: number[]) => {
    let s = 0;
    for (let i = 0; i < a.length; i++) s += (a[i] - b[i]) ** 2;
    return Math.sqrt(s);
  };
  const nearest = train
    .map((s) => ({ label: s.label, d: dist(s.x, query) }))
    .sort((a, b) => a.d - b.d)
    .slice(0, k);
  const tally = new Map<string, number>();
  for (const n of nearest) tally.set(n.label, (tally.get(n.label) ?? 0) + 1);
  let best = nearest[0].label, bestN = -1;
  for (const [label, n] of tally) if (n > bestN) { bestN = n; best = label; }
  return best;
}''',
        "provides": "knn(train, query, k)",
        "depends": [],
    },
    {
        "id": "ml-naive-bayes",
        "name": "Gaussian Naive Bayes",
        "category": "ml",
        "lang": "typescript",
        "when": "Probabilistic classification assuming independent gaussian features per class",
        "why": "Atomic fit/predict class — per-class mean/variance + log-sum classification",
        "tags": ["ml", "naive-bayes", "bayes", "gaussian", "probabilistic"],
        "iface": r'''export class GaussianNaiveBayes {
  fit(samples: { x: number[]; label: string }[]): void
  predict(x: number[]): string
}''',
        "code": r'''export class GaussianNaiveBayes {
  private classes: Map<string, { mean: number[]; var: number[]; prior: number }> = new Map();
  fit(samples: { x: number[]; label: string }[]) {
    const byLabel = new Map<string, number[][]>();
    for (const s of samples) {
      if (!byLabel.has(s.label)) byLabel.set(s.label, []);
      byLabel.get(s.label)!.push(s.x);
    }
    const n = samples.length;
    for (const [label, xs] of byLabel) {
      const dim = xs[0].length;
      const mean = Array.from({ length: dim }, (_, d) =>
        xs.reduce((s, x) => s + x[d], 0) / xs.length);
      const variance = Array.from({ length: dim }, (_, d) =>
        xs.reduce((s, x) => s + (x[d] - mean[d]) ** 2, 0) / xs.length);
      this.classes.set(label, { mean, var: variance.map((v) => v + 1e-9), prior: xs.length / n });
    }
  }
  predict(x: number[]) {
    let best = '', bestScore = -Infinity;
    for (const [label, c] of this.classes) {
      let score = Math.log(c.prior);
      for (let d = 0; d < x.length; d++) {
        const diff = x[d] - c.mean[d];
        score -= 0.5 * (Math.log(2 * Math.PI * c.var[d]) + (diff * diff) / c.var[d]);
      }
      if (score > bestScore) { bestScore = score; best = label; }
    }
    return best;
  }
}''',
        "provides": "GaussianNaiveBayes",
        "depends": [],
    },
    {
        "id": "ml-tfidf",
        "name": "TF-IDF Vectorizer",
        "category": "ml",
        "lang": "typescript",
        "when": "Weighting terms in a document corpus for retrieval or similarity",
        "why": "Atomic bag-of-words → tf-idf scores; smoothing (1+log) and idf log(N/df) built in",
        "tags": ["ml", "tfidf", "tf-idf", "vectorize", "retrieval", "nlp"],
        "iface": r'''export interface TfidfResult { terms: string[]; vectors: number[][] }
export function tfidf(docs: string[]): TfidfResult''',
        "code": r'''function tokens(text: string) {
  return text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
}
export function tfidf(docs: string[]) {
  const docTokens = docs.map(tokens);
  const df = new Map<string, number>();
  for (const dt of docTokens) for (const t of new Set(dt)) df.set(t, (df.get(t) ?? 0) + 1);
  const terms = [...df.keys()].sort();
  const n = docs.length;
  const vectors = docTokens.map((dt) => {
    const tf = new Map<string, number>();
    for (const t of dt) tf.set(t, (tf.get(t) ?? 0) + 1);
    const len = dt.length || 1;
    return terms.map((term) => {
      const f = tf.get(term) ?? 0;
      const tfs = f === 0 ? 0 : 1 + Math.log(f / len);
      return tfs * Math.log(n / (df.get(term) ?? 1));
    });
  });
  return { terms, vectors };
}''',
        "provides": "tfidf(docs)",
        "depends": [],
    },
    {
        "id": "ml-perceptron",
        "name": "Binary Perceptron",
        "category": "ml",
        "lang": "typescript",
        "when": "Linearly separable binary classification with an online mistake-driven update",
        "why": "Atomic trainer: weights + bias, epoch loops, sign prediction — no matrix lib",
        "tags": ["ml", "perceptron", "linear", "classifier", "online"],
        "iface": r'''export class Perceptron {
  constructor(dim: number)
  fit(samples: { x: number[]; label: number }[], epochs = 10): void
  predict(x: number[]): number
}''',
        "code": r'''export class Perceptron {
  private w: number[];
  private b = 0;
  constructor(dim: number) { this.w = new Array(dim).fill(0); }
  fit(samples: { x: number[]; label: number }[], epochs = 10) {
    for (let e = 0; e < epochs; e++) {
      for (const s of samples) {
        const pred = this.predict(s.x);
        if (pred !== s.label) {
          const lr = 1 / (e + 1);
          for (let i = 0; i < this.w.length; i++) this.w[i] += lr * s.label * s.x[i];
          this.b += lr * s.label;
        }
      }
    }
  }
  predict(x: number[]) {
    const z = this.w.reduce((s, wi, i) => s + wi * x[i], 0) + this.b;
    return z >= 0 ? 1 : -1;
  }
}''',
        "provides": "Perceptron",
        "depends": [],
    },
    {
        "id": "ml-logistic-regression",
        "name": "Logistic Regression (SGD)",
        "category": "ml",
        "lang": "typescript",
        "when": "Probabilistic binary classification with sigmoid outputs and gradient descent",
        "why": "Atomic probabilistic classifier: sigmoid + SGD on log loss, predict returns [0,1]",
        "tags": ["ml", "logistic", "sigmoid", "sgd", "probability"],
        "iface": r'''export class LogisticRegression {
  constructor(dim: number)
  fit(samples: { x: number[]; label: number }[], epochs = 50, lr = 0.01): void
  predict(x: number[]): number
}''',
        "code": r'''export class LogisticRegression {
  private w: number[]; private b = 0;
  constructor(dim: number) { this.w = new Array(dim).fill(0); }
  private sigmoid(z: number) { return 1 / (1 + Math.exp(-z)); }
  fit(samples: { x: number[]; label: number }[], epochs = 50, lr = 0.01) {
    for (let e = 0; e < epochs; e++) {
      for (const s of samples) {
        const p = this.sigmoid(this.w.reduce((sum, wi, i) => sum + wi * s.x[i], 0) + this.b);
        const err = p - (s.label > 0 ? 1 : 0);
        for (let i = 0; i < this.w.length; i++) this.w[i] -= lr * err * s.x[i];
        this.b -= lr * err;
      }
    }
  }
  predict(x: number[]) {
    return this.sigmoid(this.w.reduce((s, wi, i) => s + wi * x[i], 0) + this.b);
  }
}''',
        "provides": "LogisticRegression",
        "depends": [],
    },
    {
        "id": "ml-decision-tree",
        "name": "Decision Tree (ID3)",
        "category": "ml",
        "lang": "typescript",
        "when": "Interpretable classification with recursive entropy-based feature splits",
        "why": "Atomic ID3 tree: entropy gain, best feature split, predict by traversal",
        "tags": ["ml", "decision-tree", "id3", "entropy", "classifier"],
        "iface": r'''export interface TreeSample { x: Record<string, number | string>; label: string }
export class DecisionTree {
  fit(samples: TreeSample[]): void
  predict(x: Record<string, number | string>): string
}''',
        "code": r'''function entropy(counts: Map<string, number>, total: number) {
  let h = 0;
  for (const c of counts.values()) { const p = c / total; h -= p * Math.log2(p || 1); }
  return h;
}
export class DecisionTree {
  private root: any = null;
  fit(samples: TreeSample[]) {
    const features = Object.keys(samples[0]?.x ?? {});
    const build = (rows: TreeSample[], feats: string[]): any => {
      const counts = new Map<string, number>();
      for (const r of rows) counts.set(r.label, (counts.get(r.label) ?? 0) + 1);
      if (counts.size === 1) return { leaf: [...counts.keys()][0] };
      if (!feats.length) {
        let best = '', n = -1;
        for (const [l, c] of counts) if (c > n) { n = c; best = l; }
        return { leaf: best };
      }
      const h = entropy(counts, rows.length);
      let bestFeat = feats[0], bestGain = 0, bestParts: Record<string, TreeSample[]> = {};
      for (const f of feats) {
        const parts: Record<string, TreeSample[]> = {};
        for (const r of rows) (parts[String(r.x[f])] ??= []).push(r);
        const weighted = Object.values(parts).reduce((s, p) => {
          const c = new Map<string, number>();
          for (const r of p) c.set(r.label, (c.get(r.label) ?? 0) + 1);
          return s + (p.length / rows.length) * entropy(c, p.length);
        }, 0);
        const gain = h - weighted;
        if (gain > bestGain) { bestGain = gain; bestFeat = f; bestParts = parts; }
      }
      const children: Record<string, any> = {};
      for (const [v, p] of Object.entries(bestParts)) children[v] = build(p, feats.filter((f) => f !== bestFeat));
      return { feature: bestFeat, children };
    };
    this.root = build(samples, features);
  }
  predict(x: Record<string, number | string>): string {
    let node = this.root;
    while (node.children) node = node.children[String(x[node.feature])] ?? Object.values(node.children)[0];
    return node.leaf;
  }
}''',
        "provides": "DecisionTree",
        "depends": [],
    },
    {
        "id": "ml-pca",
        "name": "PCA Projection (Power Iteration)",
        "category": "ml",
        "lang": "typescript",
        "when": "Reducing a centered dataset to its top principal component",
        "why": "Atomic 1-D PCA: covariance + power iteration eigenvector + projection, no deps",
        "tags": ["ml", "pca", "dimensionality", "reduction", "projection", "eigenvector"],
        "iface": r'''export function pca1D(points: number[][]): { component: number[]; scores: number[] }''',
        "code": r'''export function pca1D(points: number[][]) {
  const dim = points[0].length;
  const mean = Array.from({ length: dim }, (_, d) =>
    points.reduce((s, p) => s + p[d], 0) / points.length);
  const centered = points.map((p) => p.map((v, d) => v - mean[d]));
  const cov = Array.from({ length: dim }, () => new Array(dim).fill(0));
  for (const p of centered)
    for (let i = 0; i < dim; i++)
      for (let j = 0; j < dim; j++) cov[i][j] += (p[i] * p[j]) / points.length;
  // Power iteration: dominant eigenvector of the covariance matrix.
  let v = centered[0].slice();
  for (let it = 0; it < 50; it++) {
    const nv = Array.from({ length: dim }, (_, i) =>
      cov[i].reduce((s, c, j) => s + c * v[j], 0));
    const norm = Math.sqrt(nv.reduce((s, x) => s + x * x, 0)) || 1;
    v = nv.map((x) => x / norm);
  }
  const scores = centered.map((p) => p.reduce((s, x, d) => s + x * v[d], 0));
  return { component: v, scores };
}''',
        "provides": "pca1D(points)",
        "depends": [],
    },
    {
        "id": "ml-normalizer",
        "name": "Feature Normalizer (Min-Max / Z-Score)",
        "category": "ml",
        "lang": "typescript",
        "when": "Scaling features before training so no single dimension dominates",
        "why": "Atomic scaler: fit computes stats, transform scales — reversible and dependency-free",
        "tags": ["ml", "normalize", "minmax", "zscore", "scale", "preprocess"],
        "iface": r'''export type NormalizerMode = 'minmax' | 'zscore'
export class Normalizer {
  constructor(mode?: NormalizerMode)
  fit(rows: number[][]): void
  transform(rows: number[][]): number[][]
}''',
        "code": r'''export class Normalizer {
  private mode: NormalizerMode;
  private mins: number[] = []; private maxs: number[] = [];
  private means: number[] = []; private stds: number[] = [];
  constructor(mode: NormalizerMode = 'minmax') { this.mode = mode; }
  fit(rows: number[][]) {
    const dim = rows[0].length;
    for (let d = 0; d < dim; d++) {
      const col = rows.map((r) => r[d]);
      this.mins[d] = Math.min(...col); this.maxs[d] = Math.max(...col);
      this.means[d] = col.reduce((s, v) => s + v, 0) / col.length;
      this.stds[d] = Math.sqrt(col.reduce((s, v) => s + (v - this.means[d]) ** 2, 0) / col.length) || 1;
    }
  }
  transform(rows: number[][]) {
    return rows.map((r) => r.map((v, d) =>
      this.mode === 'minmax'
        ? (this.maxs[d] === this.mins[d] ? 0 : (v - this.mins[d]) / (this.maxs[d] - this.mins[d]))
        : (v - this.means[d]) / this.stds[d]));
  }
}''',
        "provides": "Normalizer",
        "depends": [],
    },
    {
        "id": "ml-train-test-split",
        "name": "Seeded Train/Test Split",
        "category": "ml",
        "lang": "typescript",
        "when": "Splitting labeled data into train/test with a reproducible shuffle",
        "why": "Atomic seeded splitter: same seed → same split, deterministic experiments",
        "tags": ["ml", "split", "train", "test", "seed", "shuffle"],
        "iface": r'''export function trainTestSplit<T>(data: T[], testRatio = 0.2, seed = 42): { train: T[]; test: T[] }''',
        "code": r'''export function trainTestSplit<T>(data: T[], testRatio = 0.2, seed = 42) {
  // mulberry32 — deterministic, dependency-free PRNG.
  const rand = () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const idx = data.map((_, i) => i);
  for (let i = idx.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  const nTest = Math.round(data.length * testRatio);
  return { train: idx.slice(nTest).map((i) => data[i]), test: idx.slice(0, nTest).map((i) => data[i]) };
}''',
        "provides": "trainTestSplit(data, testRatio, seed)",
        "depends": [],
    },
    {
        "id": "ml-confusion-matrix",
        "name": "Confusion Matrix",
        "category": "ml",
        "lang": "typescript",
        "when": "Summarizing classifier predictions into TP/FP/FN/TN counts",
        "why": "Atomic evaluator: predictions vs labels in, per-class matrix + totals out",
        "tags": ["ml", "confusion", "matrix", "evaluation", "tp", "fp"],
        "iface": r'''export interface ConfusionCell { tp: number; fp: number; fn: number; tn: number }
export function confusionMatrix(labels: string[], predictions: string[]): Record<string, ConfusionCell>''',
        "code": r'''export function confusionMatrix(labels: string[], predictions: string[]) {
  const classes = [...new Set([...labels, ...predictions])];
  const out: Record<string, ConfusionCell> = {};
  for (const c of classes) out[c] = { tp: 0, fp: 0, fn: 0, tn: 0 };
  for (let i = 0; i < labels.length; i++) {
    for (const c of classes) {
      const cell = out[c];
      if (labels[i] === c && predictions[i] === c) cell.tp++;
      else if (labels[i] !== c && predictions[i] === c) cell.fp++;
      else if (labels[i] === c && predictions[i] !== c) cell.fn++;
      else cell.tn++;
    }
  }
  return out;
}''',
        "provides": "confusionMatrix(labels, predictions)",
        "depends": [],
    },
    {
        "id": "ml-prf",
        "name": "Precision / Recall / F1",
        "category": "ml",
        "lang": "typescript",
        "when": "Scoring a binary classifier's outputs per class",
        "why": "Atomic metrics: precision, recall, F1 (+ support) from a confusion cell",
        "tags": ["ml", "precision", "recall", "f1", "metrics", "score"],
        "iface": r'''export interface Prf { precision: number; recall: number; f1: number; support: number }
export function prf(cell: { tp: number; fp: number; fn: number }): Prf''',
        "code": r'''export function prf(cell: { tp: number; fp: number; fn: number }) {
  const { tp, fp, fn } = cell;
  const precision = tp + fp === 0 ? 0 : tp / (tp + fp);
  const recall = tp + fn === 0 ? 0 : tp / (tp + fn);
  const f1 = precision + recall === 0 ? 0 : (2 * precision * recall) / (precision + recall);
  return { precision, recall, f1, support: tp + fn };
}''',
        "provides": "prf(cell)",
        "depends": [],
    },
    {
        "id": "ml-rolling-mean",
        "name": "Rolling Mean / EMA",
        "category": "ml",
        "lang": "typescript",
        "when": "Smoothing a noisy time series with SMA or exponential moving average",
        "why": "Atomic smoothers: windowed mean and recursive EMA, streaming-friendly",
        "tags": ["ml", "rolling", "mean", "ema", "smooth", "time-series"],
        "iface": r'''export function rollingMean(values: number[], window: number): number[]
export function ema(values: number[], alpha?: number): number[]''',
        "code": r'''export function rollingMean(values: number[], window: number) {
  const out: number[] = []; let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    out.push(i < window - 1 ? NaN : sum / Math.min(window, i + 1));
  }
  return out;
}
export function ema(values: number[], alpha = 0.2) {
  const out: number[] = [];
  let prev = values[0] ?? NaN;
  for (const v of values) { prev = out.length === 0 ? v : alpha * v + (1 - alpha) * prev; out.push(prev); }
  return out;
}''',
        "provides": "rollingMean / ema",
        "depends": [],
    },
    {
        "id": "ml-correlation",
        "name": "Pearson Correlation",
        "category": "ml",
        "lang": "typescript",
        "when": "Measuring linear association strength between two series in [-1, 1]",
        "why": "Atomic statistic: centered covariance over product of std devs, NaN-guarded",
        "tags": ["ml", "correlation", "pearson", "statistics", "association"],
        "iface": r'''export function pearson(a: number[], b: number[]): number''',
        "code": r'''export function pearson(a: number[], b: number[]) {
  const n = Math.min(a.length, b.length);
  if (n === 0) return NaN;
  const ma = a.reduce((s, v) => s + v, 0) / n;
  const mb = b.reduce((s, v) => s + v, 0) / n;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < n; i++) {
    num += (a[i] - ma) * (b[i] - mb);
    da += (a[i] - ma) ** 2; db += (b[i] - mb) ** 2;
  }
  const denom = Math.sqrt(da * db);
  return denom === 0 ? 0 : num / denom;
}''',
        "provides": "pearson(a, b)",
        "depends": [],
    },
    {
        "id": "ml-feature-hash",
        "name": "Feature Hashing (Hashing Trick)",
        "category": "ml",
        "lang": "typescript",
        "when": "Mapping high-cardinality categorical strings into a fixed-size numeric vector",
        "why": "Atomic hashing trick: stable hash → bucket index, no vocabulary table needed",
        "tags": ["ml", "feature", "hash", "hashing-trick", "encoding"],
        "iface": r'''export function featureHash(terms: string[], buckets: number): number[]''',
        "code": r'''function hashStr(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
export function featureHash(terms: string[], buckets: number) {
  const vec = new Array(buckets).fill(0);
  for (const t of terms) {
    const idx = hashStr(t) % buckets;
    vec[idx] += (hashStr(t + ':sign') & 1) === 0 ? 1 : -1; // signed hashing reduces collisions
  }
  return vec;
}''',
        "provides": "featureHash(terms, buckets)",
        "depends": [],
    },
    {
        "id": "ml-one-hot",
        "name": "One-Hot Encoder",
        "category": "ml",
        "lang": "typescript",
        "when": "Converting categorical values to binary indicator vectors",
        "why": "Atomic encoder: vocabulary inferred from fit data, unknown → all-zero row",
        "tags": ["ml", "one-hot", "encode", "categorical", "feature"],
        "iface": r'''export class OneHotEncoder {
  fit(values: string[]): void
  transform(values: string[]): number[][]
  get categories(): string[]
}''',
        "code": r'''export class OneHotEncoder {
  private cats: string[] = [];
  fit(values: string[]) { this.cats = [...new Set(values)].sort(); }
  transform(values: string[]) {
    return values.map((v) => {
      const row = new Array(this.cats.length).fill(0);
      const i = this.cats.indexOf(v);
      if (i >= 0) row[i] = 1;
      return row;
    });
  }
  get categories() { return this.cats; }
}''',
        "provides": "OneHotEncoder",
        "depends": [],
    },
    {
        "id": "ml-cooccurrence",
        "name": "Word Co-occurrence Matrix",
        "category": "ml",
        "lang": "typescript",
        "when": "Capturing which terms appear together in documents (context statistics)",
        "why": "Atomic co-occurrence counter: windowed term pairs in, sparse index out",
        "tags": ["ml", "cooccurrence", "nlp", "context", "word"],
        "iface": r'''export function cooccurrence(docs: string[], window = 2): Map<string, Map<string, number>>''',
        "code": r'''function words(text: string) {
  return text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
}
export function cooccurrence(docs: string[], window = 2) {
  const out = new Map<string, Map<string, number>>();
  const bump = (a: string, b: string) => {
    if (a === b) return;
    if (!out.has(a)) out.set(a, new Map());
    const m = out.get(a)!;
    m.set(b, (m.get(b) ?? 0) + 1);
  };
  for (const doc of docs) {
    const ws = words(doc);
    for (let i = 0; i < ws.length; i++)
      for (let j = Math.max(0, i - window); j <= Math.min(ws.length - 1, i + window); j++)
        bump(ws[i], ws[j]);
  }
  return out;
}''',
        "provides": "cooccurrence(docs, window)",
        "depends": [],
    },
    {
        "id": "ml-cosine-sim",
        "name": "Cosine Similarity",
        "category": "ml",
        "lang": "typescript",
        "when": "Comparing two non-zero vectors regardless of magnitude",
        "why": "Atomic similarity: dot product over norms — the standard vector retriever kernel",
        "tags": ["ml", "cosine", "similarity", "vector", "dot-product"],
        "iface": r'''export function cosineSimilarity(a: number[], b: number[]): number''',
        "code": r'''export function cosineSimilarity(a: number[], b: number[]) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}''',
        "provides": "cosineSimilarity(a, b)",
        "depends": [],
    },
    {
        "id": "ml-distance",
        "name": "Distance Metrics (Euclid / Manhattan / Haversine)",
        "category": "ml",
        "lang": "typescript",
        "when": "Choosing a distance for clustering, KNN, or geo lookup",
        "why": "Atomic metric set: three pure distances, one import",
        "tags": ["ml", "distance", "euclidean", "manhattan", "haversine"],
        "iface": r'''export function euclidean(a: number[], b: number[]): number
export function manhattan(a: number[], b: number[]): number
export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number''',
        "code": r'''export function euclidean(a: number[], b: number[]) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += (a[i] - b[i]) ** 2;
  return Math.sqrt(s);
}
export function manhattan(a: number[], b: number[]) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]);
  return s;
}
export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}''',
        "provides": "euclidean / manhattan / haversineKm",
        "depends": [],
    },
    {
        "id": "ml-gradient-descent",
        "name": "Gradient Descent Step",
        "category": "ml",
        "lang": "typescript",
        "when": "Optimizing any differentiable loss by descending its gradient",
        "why": "Atomic optimizer core: params + gradient fn + lr in, updated params out — reusable by any model",
        "tags": ["ml", "gradient", "descent", "optimizer", "sgd"],
        "iface": r'''export function gradientStep(params: number[], grad: number[], lr: number): number[]''',
        "code": r'''export function gradientStep(params: number[], grad: number[], lr: number) {
  return params.map((p, i) => p - lr * grad[i]);
}''',
        "provides": "gradientStep(params, grad, lr)",
        "depends": [],
    },
    {
        "id": "ml-auc-threshold",
        "name": "ROC Threshold Sweep / AUC",
        "category": "ml",
        "lang": "typescript",
        "when": "Evaluating a scoring classifier across all decision thresholds",
        "why": "Atomic evaluator: scores + labels in, ROC points + AUC approximation out",
        "tags": ["ml", "roc", "auc", "threshold", "evaluation"],
        "iface": r'''export interface RocResult { points: Array<[number, number]>; auc: number }
export function rocAuc(scores: number[], labels: number[]): RocResult''',
        "code": r'''export function rocAuc(scores: number[], labels: number[]) {
  const pairs = scores.map((s, i) => ({ s, y: labels[i] })).sort((a, b) => b.s - a.s);
  const points: Array<[number, number]> = [[0, 0]];
  let tp = 0, fp = 0, pos = labels.filter((y) => y > 0).length;
  const neg = labels.length - pos;
  for (const p of pairs) { if (p.y > 0) tp++; else fp++; points.push([fp / (neg || 1), tp / (pos || 1)]); }
  let auc = 0;
  for (let i = 1; i < points.length; i++) auc += (points[i][0] - points[i - 1][0]) * (points[i][1] + points[i - 1][1]) / 2;
  return { points, auc };
}''',
        "provides": "rocAuc(scores, labels)",
        "depends": [],
    },
    {
        "id": "ml-stratified-sample",
        "name": "Stratified Sample",
        "category": "ml",
        "lang": "typescript",
        "when": "Sampling so each class keeps its proportion (imbalanced data)",
        "why": "Atomic resampler: per-class seeded shuffle, ratio preserved exactly",
        "tags": ["ml", "stratified", "sample", "imbalanced", "resample"],
        "iface": r'''export function stratifiedSample<T>(items: T[], label: (t: T) => string, ratio: number, seed = 42): T[]''',
        "code": r'''export function stratifiedSample<T>(items: T[], label: (t: T) => string, ratio: number, seed = 42) {
  const rand = () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const groups = new Map<string, T[]>();
  for (const it of items) {
    const k = label(it);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k)!.push(it);
  }
  const out: T[] = [];
  for (const g of groups.values()) {
    for (let i = g.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [g[i], g[j]] = [g[j], g[i]]; }
    out.push(...g.slice(0, Math.max(1, Math.round(g.length * ratio))));
  }
  return out;
}''',
        "provides": "stratifiedSample(items, label, ratio, seed)",
        "depends": [],
    },
    {
        "id": "ml-sgd-update",
        "name": "Online SGD Update",
        "category": "ml",
        "lang": "typescript",
        "when": "Updating weights from a single training example (streaming learning)",
        "why": "Atomic online step: one sample's gradient in, updated weights out — no batch buffering",
        "tags": ["ml", "sgd", "online", "update", "streaming"],
        "iface": r'''export function sgdUpdate(weights: number[], feature: number[], error: number, lr: number): number[]''',
        "code": r'''export function sgdUpdate(weights: number[], feature: number[], error: number, lr: number) {
  return weights.map((w, i) => w - lr * error * feature[i]);
}''',
        "provides": "sgdUpdate(weights, feature, error, lr)",
        "depends": [],
    },
    {
        "id": "ml-kfold",
        "name": "K-Fold Cross-Validation Folds",
        "category": "ml",
        "lang": "typescript",
        "when": "Generating train/val folds so every example is validated exactly once",
        "why": "Atomic fold generator: data + k in, fold index arrays out — deterministic and stratified-free",
        "tags": ["ml", "kfold", "cross-validation", "folds", "evaluation"],
        "iface": r'''export function kFold(n: number, k: number, seed = 42): Array<{ train: number[]; val: number[] }>''',
        "code": r'''export function kFold(n: number, k: number, seed = 42) {
  const rand = () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const idx = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
  const folds: Array<{ train: number[]; val: number[] }> = [];
  const size = Math.ceil(n / k);
  for (let f = 0; f < k; f++) {
    const val = idx.slice(f * size, Math.min(n, (f + 1) * size));
    folds.push({ val, train: idx.filter((i) => !val.includes(i)) });
  }
  return folds;
}''',
        "provides": "kFold(n, k, seed)",
        "depends": [],
    },
]
