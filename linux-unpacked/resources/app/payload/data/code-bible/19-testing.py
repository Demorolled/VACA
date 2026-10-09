# -*- coding: utf-8 -*-
"""
Code Bible — Category 19: Testing utilities (atomic, single-responsibility).
Convention: framework-agnostic helpers; zero dependencies, no globals.
"""
CHUNKS = [
    {
        "id": "test-fake-timers",
        "name": "Fake Timers",
        "category": "test",
        "lang": "typescript",
        "when": "Advancing time deterministically in unit tests",
        "why": "Atomic clock: install/uninstall, advance, flush — no sinon dependency",
        "tags": ["test", "timers", "fake", "clock", "deterministic"],
        "iface": r'''export class FakeTimers {
  constructor()
  install(): void
  uninstall(): void
  advance(ms: number): void
  flush(): void
  get now(): number
}''',
        "code": r'''export class FakeTimers {
  private real: { setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout; Date: DateConstructor } | null = null;
  private tasks: Array<{ id: number; at: number; fn: () => void }> = [];
  private nextId = 1;
  private _now = 0;
  install() {
    this.real = { setTimeout, clearTimeout, Date };
    const self = this;
    (globalThis as any).setTimeout = (fn: () => void, ms = 0) => { const id = self.nextId++; self.tasks.push({ id, at: self._now + ms, fn }); return id; };
    (globalThis as any).clearTimeout = (id: number) => { self.tasks = self.tasks.filter((t) => t.id !== id); };
    (globalThis as any).Date = class extends Date { constructor(...args: any[]) { super(...(args.length ? args : [self._now])); } };
  }
  uninstall() {
    if (!this.real) return;
    globalThis.setTimeout = this.real.setTimeout;
    globalThis.clearTimeout = this.real.clearTimeout;
    globalThis.Date = this.real.Date;
    this.real = null;
  }
  advance(ms: number) {
    const target = this._now + ms;
    let guard = 0;
    while (guard++ < 10000) {
      const due = this.tasks.filter((t) => t.at <= target).sort((a, b) => a.at - b.at);
      if (!due.length) break;
      this._now = due[0].at;
      this.tasks = this.tasks.filter((t) => t.id !== due[0].id);
      due[0].fn();
    }
    this._now = target;
  }
  flush() { this.advance(Number.MAX_SAFE_INTEGER); }
  get now() { return this._now; }
}''',
        "provides": "FakeTimers",
        "depends": [],
    },
    {
        "id": "test-assert",
        "name": "Assertion Helpers",
        "category": "test",
        "lang": "typescript",
        "when": "Asserting without pulling in a full test framework",
        "why": "Atomic asserts: deepEqual, approxEqual, throws — clear failure messages",
        "tags": ["test", "assert", "deepequal", "throws", "matcher"],
        "iface": r'''export function assert(cond: boolean, msg?: string): asserts cond
export function assertEqual<T>(actual: T, expected: T, msg?: string): void
export function assertDeepEqual(actual: unknown, expected: unknown, msg?: string): void
export function assertApprox(actual: number, expected: number, tol?: number, msg?: string): void
export function assertThrows(fn: () => void, msg?: string): void''',
        "code": r'''export function assert(cond: boolean, msg = 'assertion failed') { if (!cond) throw new Error(msg); }
export function assertEqual<T>(actual: T, expected: T, msg = 'not equal') {
  if (actual !== expected) throw new Error(`${msg}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}
export function assertDeepEqual(actual: unknown, expected: unknown, msg = 'not deep equal') {
  const a = JSON.stringify(actual), b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${msg}: expected ${b}, got ${a}`);
}
export function assertApprox(actual: number, expected: number, tol = 1e-6, msg = 'not approx') {
  if (Math.abs(actual - expected) > tol) throw new Error(`${msg}: expected ~${expected}, got ${actual}`);
}
export function assertThrows(fn: () => void, msg = 'expected to throw') {
  try { fn(); } catch { return; }
  throw new Error(msg);
}''',
        "provides": "assert / assertEqual / assertDeepEqual / assertApprox / assertThrows",
        "depends": [],
    },
    {
        "id": "test-tap-reporter",
        "name": "TAP Reporter",
        "category": "test",
        "lang": "typescript",
        "when": "Emitting test results in the Test Anything Protocol format",
        "why": "Atomic reporter: results in, TAP text out, pipeable to CI parsers",
        "tags": ["test", "tap", "reporter", "output", "ci"],
        "iface": r'''export interface TestResult { name: string; ok: boolean; error?: string }
export function tapReport(results: TestResult[]): string''',
        "code": r'''export function tapReport(results: TestResult[]) {
  const lines = [`TAP version 13`, `1..${results.length}`];
  results.forEach((r, i) => {
    lines.push(`${r.ok ? 'ok' : 'not ok'} ${i + 1} - ${r.name.replace(/\n/g, ' ')}`);
    if (!r.ok && r.error) lines.push(`  ---`, `  message: ${JSON.stringify(r.error)}`, `  ...`);
  });
  return lines.join('\n') + '\n';
}''',
        "provides": "tapReport(results)",
        "depends": [],
    },
    {
        "id": "test-mock-fn",
        "name": "Mock Function Recorder",
        "category": "test",
        "lang": "typescript",
        "when": "Recording calls and return values of a stub",
        "why": "Atomic mock: wrap fn, record calls, control returns — assertions on calls",
        "tags": ["test", "mock", "stub", "recorder", "spy"],
        "iface": r'''export interface MockFn<Args extends unknown[] = unknown[], R = unknown> {
  (...args: Args): R
  calls: Args[]
  results: R[]
  clear(): void
  mockReturnValue(value: R): void
}
export function mockFn<Args extends unknown[] = unknown[], R = unknown>(impl?: (...a: Args) => R): MockFn<Args, R>''',
        "code": r'''export function mockFn<Args extends unknown[] = unknown[], R = unknown>(impl?: (...a: Args) => R): MockFn<Args, R> {
  let ret: R | undefined;
  const calls: Args[] = [];
  const results: R[] = [];
  const fn = ((...args: Args) => {
    calls.push(args);
    const v = ret !== undefined ? ret : impl?.(...args);
    results.push(v as R);
    return v as R;
  }) as MockFn<Args, R>;
  fn.calls = calls;
  fn.results = results;
  fn.clear = () => { calls.length = 0; results.length = 0; };
  fn.mockReturnValue = (value: R) => { ret = value; };
  return fn;
}''',
        "provides": "mockFn(impl)",
        "depends": [],
    },
    {
        "id": "test-fixture-load",
        "name": "Fixture Loader",
        "category": "test",
        "lang": "typescript",
        "when": "Loading test fixtures with caching and deep freeze",
        "why": "Atomic loader: path or inline data in, typed + frozen fixture out",
        "tags": ["test", "fixture", "load", "cache", "data"],
        "iface": r'''export class FixtureStore<T> {
  constructor(load: (name: string) => T, options?: { cache?: boolean; freeze?: boolean })
  get(name: string): T
  all(): string[]
}''',
        "code": r'''export class FixtureStore<T> {
  private cache = new Map<string, T>();
  private names: string[] = [];
  constructor(private load: (name: string) => T, private options: { cache?: boolean; freeze?: boolean } = {}) {}
  get(name: string) {
    if (this.options.cache && this.cache.has(name)) return this.cache.get(name)!;
    const raw = this.load(name);
    const value = this.options.freeze ? deepFreeze(raw) : raw;
    if (this.options.cache) this.cache.set(name, value);
    this.names.push(name);
    return value;
  }
  all() { return this.names; }
}
function deepFreeze<T>(v: T): T {
  if (v && typeof v === 'object') { Object.freeze(v); for (const k of Object.values(v as Record<string, unknown>)) deepFreeze(k); }
  return v;
}''',
        "provides": "FixtureStore",
        "depends": [],
    },
    {
        "id": "test-property-check",
        "name": "Property-Based Generator",
        "category": "test",
        "lang": "typescript",
        "when": "Fuzzing functions with random inputs and invariants",
        "why": "Atomic generator: int/float/string/array, seeded, shrinkable to failing case",
        "tags": ["test", "property", "fuzz", "generator", "random"],
        "iface": r'''export interface Gen<T> { next(): T }
export const gens: {
  int(min: number, max: number, seed?: number): Gen<number>
  float(min: number, max: number, seed?: number): Gen<number>
  string(length: number, alphabet?: string, seed?: number): Gen<string>
  array<T>(g: Gen<T>, maxLen: number): Gen<T[]>
}
export function check<T>(g: Gen<T>, property: (t: T) => boolean, runs?: number): { ok: boolean; counterexample?: T; runs: number }''',
        "code": r'''function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
export const gens = {
  int(min: number, max: number, seed = 42) { const r = rng(seed); return { next: () => min + Math.floor(r() * (max - min + 1)) }; },
  float(min: number, max: number, seed = 42) { const r = rng(seed); return { next: () => min + r() * (max - min) }; },
  string(length: number, alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789', seed = 42) {
    const r = rng(seed);
    return { next: () => Array.from({ length }, () => alphabet[Math.floor(r() * alphabet.length)]).join('') };
  },
  array<T>(g: Gen<T>, maxLen: number) { return { next: () => Array.from({ length: Math.floor(Math.random() * (maxLen + 1)) }, () => g.next()) }; },
};
export function check<T>(g: Gen<T>, property: (t: T) => boolean, runs = 100) {
  for (let i = 0; i < runs; i++) { const t = g.next(); if (!property(t)) return { ok: false, counterexample: t, runs: i + 1 }; }
  return { ok: true, runs };
}''',
        "provides": "gens / check",
        "depends": [],
    },
    {
        "id": "test-snapshot",
        "name": "Snapshot Compare",
        "category": "test",
        "lang": "typescript",
        "when": "Detecting unexpected output changes across runs",
        "why": "Atomic snapshots: normalize + store in, diff vs stored out, update mode",
        "tags": ["test", "snapshot", "compare", "golden", "diff"],
        "iface": r'''export class SnapshotStore {
  constructor(load: (name: string) => string | null, save: (name: string, value: string) => void)
  match(name: string, value: unknown, opts?: { update?: boolean; normalize?: (s: string) => string }): { ok: boolean; diff?: string }
}''',
        "code": r'''export class SnapshotStore {
  constructor(private load: (name: string) => string | null, private save: (name: string, value: string) => void) {}
  match(name: string, value: unknown, opts: { update?: boolean; normalize?: (s: string) => string } = {}) {
    const text = opts.normalize ? opts.normalize(JSON.stringify(value, null, 2)) : JSON.stringify(value, null, 2);
    const stored = this.load(name);
    if (opts.update || stored === null) { this.save(name, text); return { ok: true }; }
    const normalizedStored = opts.normalize ? opts.normalize(stored) : stored;
    return normalizedStored === text ? { ok: true } : { ok: false, diff: `stored:\n${stored}\n---\nnew:\n${text}` };
  }
}''',
        "provides": "SnapshotStore",
        "depends": [],
    },
    {
        "id": "test-retry-flaky",
        "name": "Flaky Test Retry",
        "category": "test",
        "lang": "typescript",
        "when": "Retrying flaky tests a bounded number of times",
        "why": "Atomic retrier: fn + attempts in, first pass or final error out",
        "tags": ["test", "flaky", "retry", "stable", "rerun"],
        "iface": r'''export async function retryTest(fn: () => Promise<void>, attempts?: number): Promise<void>''',
        "code": r'''export async function retryTest(fn: () => Promise<void>, attempts = 3) {
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try { await fn(); return; } catch (e) { last = e; }
  }
  throw last;
}''',
        "provides": "retryTest(fn, attempts)",
        "depends": [],
    },
    {
        "id": "test-matrix",
        "name": "Test Case Matrix Generator",
        "category": "test",
        "lang": "typescript",
        "when": "Generating every combination of input dimensions",
        "why": "Atomic matrix: dimension lists in, cartesian combos out with names",
        "tags": ["test", "matrix", "combinations", "cases", "cartesian"],
        "iface": r'''export function testMatrix<T extends Record<string, unknown>>(dimensions: Record<string, unknown[]>): Array<{ name: string; values: T }>''',
        "code": r'''export function testMatrix<T extends Record<string, unknown>>(dimensions: Record<string, unknown[]>) {
  const keys = Object.keys(dimensions);
  const out: Array<{ name: string; values: T }> = [];
  const walk = (idx: number, acc: Record<string, unknown>, parts: string[]) => {
    if (idx === keys.length) { out.push({ name: parts.join(' | ') || 'default', values: acc as T }); return; }
    for (const v of dimensions[keys[idx]]) walk(idx + 1, { ...acc, [keys[idx]]: v }, [...parts, `${keys[idx]}=${JSON.stringify(v)}`]);
  };
  walk(0, {}, []);
  return out;
}''',
        "provides": "testMatrix(dimensions)",
        "depends": [],
    },
    {
        "id": "test-eventually",
        "name": "Async 'Eventually' Assertion",
        "category": "test",
        "lang": "typescript",
        "when": "Waiting for async state to settle before asserting",
        "why": "Atomic poller: assertion fn in, retried until pass or timeout",
        "tags": ["test", "async", "eventually", "wait", "poll"],
        "iface": r'''export async function eventually(fn: () => void | Promise<void>, opts?: { timeoutMs?: number; intervalMs?: number }): Promise<void>''',
        "code": r'''export async function eventually(fn: () => void | Promise<void>, opts: { timeoutMs?: number; intervalMs?: number } = {}) {
  const { timeoutMs = 2000, intervalMs = 20 } = opts;
  const deadline = Date.now() + timeoutMs;
  let lastErr: unknown;
  while (Date.now() < deadline) {
    try { await fn(); return; } catch (e) { lastErr = e; }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw lastErr;
}''',
        "provides": "eventually(fn, opts)",
        "depends": [],
    },
    {
        "id": "test-stub-server",
        "name": "In-Memory Stub HTTP Server",
        "category": "test",
        "lang": "typescript",
        "when": "Stubbing API responses in tests without real network",
        "why": "Atomic stub: route table in, fetch-like dispatcher out, delay simulation",
        "tags": ["test", "stub", "server", "http", "mock"],
        "iface": r'''export interface StubResponse { status: number; body: unknown; delayMs?: number }
export class StubServer {
  route(method: string, pattern: string, handler: (req: { url: string; body: unknown }) => StubResponse | Promise<StubResponse>): void
  fetch(input: RequestInfo, init?: RequestInit): Promise<Response>
  reset(): void
}''',
        "code": r'''export class StubServer {
  private routes: Array<{ method: string; re: RegExp; handler: (req: { url: string; body: unknown }) => StubResponse | Promise<StubResponse> }> = [];
  route(method: string, pattern: string, handler: (req: { url: string; body: unknown }) => StubResponse | Promise<StubResponse>) {
    this.routes.push({ method, re: new RegExp('^' + pattern.replace(/\*/g, '.*') + '$'), handler });
  }
  async fetch(input: RequestInfo, init: RequestInit = {}) {
    const url = typeof input === 'string' ? input : input.url;
    const method = (init.method ?? 'GET').toUpperCase();
    const body = init.body ? JSON.parse(String(init.body)) : undefined;
    const path = url.split('?')[0];
    for (const r of this.routes) {
      if (r.method.toUpperCase() === method && r.re.test(path)) {
        const res = await r.handler({ url: path, body });
        if (res.delayMs) await new Promise((r2) => setTimeout(r2, res.delayMs));
        return new Response(JSON.stringify(res.body), { status: res.status, headers: { 'Content-Type': 'application/json' } });
      }
    }
    return new Response(JSON.stringify({ error: 'not found' }), { status: 404 });
  }
  reset() { this.routes = []; }
}''',
        "provides": "StubServer",
        "depends": [],
    },
    {
        "id": "test-coverage-map",
        "name": "Branch Coverage Tracker",
        "category": "test",
        "lang": "typescript",
        "when": "Counting exercised branches in hand-written tests",
        "why": "Atomic tracker: named branches, hit counts, coverage % out",
        "tags": ["test", "coverage", "branch", "tracker", "percent"],
        "iface": r'''export class BranchTracker {
  declare(name: string): void
  hit(name: string): void
  get coveragePct(): number
  report(): Array<{ name: string; hit: boolean }>
}''',
        "code": r'''export class BranchTracker {
  private declared = new Set<string>();
  private hitSet = new Set<string>();
  declare(name: string) { this.declared.add(name); }
  hit(name: string) { this.declared.add(name); this.hitSet.add(name); }
  get coveragePct() { return this.declared.size ? (this.hitSet.size / this.declared.size) * 100 : 100; }
  report() { return [...this.declared].map((name) => ({ name, hit: this.hitSet.has(name) })); }
}''',
        "provides": "BranchTracker",
        "depends": [],
    },
    {
        "id": "test-seed-harness",
        "name": "Seeded Random Harness",
        "category": "test",
        "lang": "typescript",
        "when": "Reproducible random in tests",
        "why": "Atomic harness: seeded PRNG, swap Math.random, restore on uninstall",
        "tags": ["test", "seed", "random", "harness", "reproducible"],
        "iface": r'''export class SeededRandom {
  constructor(seed?: number)
  next(): number
  int(min: number, max: number): number
  pick<T>(arr: T[]): T
  static install(seed?: number): () => void
}''',
        "code": r'''export class SeededRandom {
  private s: number;
  constructor(seed = 42) { this.s = seed; }
  next() { this.s |= 0; this.s = (this.s + 0x6d2b79f5) | 0; let t = Math.imul(this.s ^ (this.s >>> 15), 1 | this.s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }
  int(min: number, max: number) { return min + Math.floor(this.next() * (max - min + 1)); }
  pick<T>(arr: T[]) { return arr[Math.floor(this.next() * arr.length)]; }
  static install(seed = 42) {
    const r = new SeededRandom(seed);
    const orig = Math.random;
    Math.random = () => r.next();
    return () => { Math.random = orig; };
  }
}''',
        "provides": "SeededRandom",
        "depends": [],
    },
    {
        "id": "test-benchmark",
        "name": "Micro-Benchmark Runner",
        "category": "test",
        "lang": "typescript",
        "when": "Comparing performance of implementations",
        "why": "Atomic runner: fn + iterations in, ops/sec + mean ms out",
        "tags": ["test", "benchmark", "perf", "ops", "timing"],
        "iface": r'''export interface BenchResult { name: string; opsPerSec: number; meanMs: number; minMs: number }
export function benchmark(name: string, fn: () => void, iterations?: number): BenchResult''',
        "code": r'''export function benchmark(name: string, fn: () => void, iterations = 10000) {
  const times: number[] = [];
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    fn();
    times.push(performance.now() - t0);
  }
  const meanMs = times.reduce((s, t) => s + t, 0) / times.length;
  return { name, opsPerSec: Math.round(1000 / meanMs), meanMs: +meanMs.toFixed(4), minMs: +Math.min(...times).toFixed(4) };
}''',
        "provides": "benchmark(name, fn, iterations)",
        "depends": [],
    },
    {
        "id": "test-fuzz-input",
        "name": "Input Fuzzer (strings)",
        "category": "test",
        "lang": "typescript",
        "when": "Fuzzing parsers and validators with hostile inputs",
        "why": "Atomic fuzzer: base + mutation pool in, mutated strings out",
        "tags": ["test", "fuzz", "input", "mutation", "hostile"],
        "iface": r'''export function fuzzInputs(base: string, count?: number): string[]''',
        "code": r'''const MUTATIONS = ['', ' ', '\n', '\r\n', '\t', '"', "'", '<script>', '../', '\\', 'null', 'undefined', 'NaN', '%00', '`', ';', '{}', '[]', '\\u0000', '❌', 'A'.repeat(1000)];
export function fuzzInputs(base: string, count = 50) {
  const out: string[] = [];
  out.push(base);
  for (let i = 0; i < count; i++) {
    const m = MUTATIONS[i % MUTATIONS.length];
    const pos = (i * 7) % (base.length + 1);
    out.push(base.slice(0, pos) + m + base.slice(pos));
  }
  return out;
}''',
        "provides": "fuzzInputs(base, count)",
        "depends": [],
    },
    {
        "id": "test-dom-query",
        "name": "DOM Query Helper",
        "category": "test",
        "lang": "typescript",
        "when": "Finding elements by text or role in DOM tests",
        "why": "Atomic helper: getByText/getByRole in-memory queries, no framework coupling",
        "tags": ["test", "dom", "query", "getby", "role"],
        "iface": r'''export function getByText(root: HTMLElement, text: string): HTMLElement | null
export function getByRole(root: HTMLElement, role: string): HTMLElement | null''',
        "code": r'''export function getByText(root: HTMLElement, text: string) {
  return [...root.querySelectorAll<HTMLElement>('*')].find((el) => el.children.length === 0 && el.textContent?.trim() === text) ?? null;
}
export function getByRole(root: HTMLElement, role: string) {
  const found = root.querySelector<HTMLElement>(`[role="${role}"]`);
  return found ?? [...root.querySelectorAll<HTMLElement>('button, a, input, select, textarea')].find((el) => {
    const r = el.getAttribute('role');
    if (r) return r === role;
    return (el.tagName.toLowerCase() === 'button' || el.tagName.toLowerCase() === 'a') && role === 'button';
  }) ?? null;
}''',
        "provides": "getByText / getByRole",
        "depends": [],
    },
    {
        "id": "test-contract-assert",
        "name": "Contract (shape) Assertion",
        "category": "test",
        "lang": "typescript",
        "when": "Validating an API response matches an expected shape",
        "why": "Atomic matcher: value + schema in, missing/type-mismatch list out",
        "tags": ["test", "contract", "shape", "schema", "validate"],
        "iface": r'''export type FieldSchema = 'string' | 'number' | 'boolean' | 'object' | 'array' | { type: 'array'; of: FieldSchema } | { type: 'object'; fields: Record<string, FieldSchema> }
export function validateShape(value: unknown, schema: Record<string, FieldSchema>): string[]''',
        "code": r'''function checkOne(v: unknown, s: FieldSchema, path: string, errors: string[]) {
  if (typeof s === 'object' && 'type' in s) {
    if (s.type === 'array') {
      if (!Array.isArray(v)) { errors.push(`${path} should be array`); return; }
      for (let i = 0; i < v.length; i++) checkOne(v[i], (s as { of: FieldSchema }).of, `${path}[${i}]`, errors);
    } else {
      if (typeof v !== 'object' || v === null) { errors.push(`${path} should be object`); return; }
      for (const [k, sub] of Object.entries((s as { fields: Record<string, FieldSchema> }).fields)) {
        checkOne((v as Record<string, unknown>)[k], sub, `${path}.${k}`, errors);
      }
    }
    return;
  }
  const actual = Array.isArray(v) ? 'array' : typeof v;
  if (s === 'array') { if (!Array.isArray(v)) errors.push(`${path} should be array`); return; }
  if (actual !== s) errors.push(`${path} should be ${s}, got ${actual}`);
}
export function validateShape(value: unknown, schema: Record<string, FieldSchema>) {
  const errors: string[] = [];
  if (typeof value !== 'object' || value === null) { errors.push('root should be object'); return errors; }
  for (const [k, s] of Object.entries(schema)) checkOne((value as Record<string, unknown>)[k], s, k, errors);
  return errors;
}''',
        "provides": "validateShape(value, schema)",
        "depends": [],
    },
    {
        "id": "test-leak-detector",
        "name": "Handle Leak Detector",
        "category": "test",
        "lang": "typescript",
        "when": "Catching listener/interval leaks between tests",
        "why": "Atomic detector: snapshot before/after, leaked handle count out",
        "tags": ["test", "leak", "detector", "listener", "interval"],
        "iface": "export class LeakDetector {\n  constructor()\n  snapshot(): { listeners: number; intervals: number; timeouts: number }\n  diff(before: ReturnType<LeakDetector['snapshot']>): string[]\n}",
        "code": r'''export class LeakDetector {
  snapshot() {
    const getCount = (name: string) => {
      const w = globalThis as Record<string, unknown>;
      const list = w[name] as Map<unknown, unknown> | undefined;
      return list ? list.size : 0;
    };
    return {
      listeners: typeof process !== 'undefined' ? process.listenerCount(process as unknown as NodeJS.EventEmitter) : 0,
      intervals: getCount('intervalList'),
      timeouts: getCount('timeoutList'),
    };
  }
  diff(before: ReturnType<LeakDetector['snapshot']>) {
    const after = this.snapshot();
    const out: string[] = [];
    for (const k of ['listeners', 'intervals', 'timeouts'] as const) {
      if (after[k] > before[k]) out.push(`${k}: ${before[k]} → ${after[k]}`);
    }
    return out;
  }
}''',
        "provides": "LeakDetector",
        "depends": [],
    },
    {
        "id": "test-time-window",
        "name": "Time-Window Matcher",
        "category": "test",
        "lang": "typescript",
        "when": "Asserting timestamps are within a tolerance",
        "why": "Atomic matcher: timestamp in, within range assertion helpers out",
        "tags": ["test", "time", "window", "timestamp", "tolerance"],
        "iface": r'''export function within(ts: number, expected: number, toleranceMs?: number): boolean
export function recent(ts: number, maxAgeMs?: number): boolean''',
        "code": r'''export function within(ts: number, expected: number, toleranceMs = 1000) {
  return Math.abs(ts - expected) <= toleranceMs;
}
export function recent(ts: number, maxAgeMs = 5000) {
  return Math.abs(Date.now() - ts) <= maxAgeMs;
}''',
        "provides": "within / recent",
        "depends": [],
    },
    {
        "id": "test-record-eq",
        "name": "Record Equality (partial)",
        "category": "test",
        "lang": "typescript",
        "when": "Asserting only the expected subset of a large object",
        "why": "Atomic matcher: actual + subset in, boolean + missing/mismatch detail out",
        "tags": ["test", "equal", "partial", "subset", "matcher"],
        "iface": r'''export function containsSubset(actual: Record<string, unknown>, expected: Record<string, unknown>): { ok: boolean; detail: string[] }''',
        "code": r'''export function containsSubset(actual: Record<string, unknown>, expected: Record<string, unknown>) {
  const detail: string[] = [];
  for (const [k, v] of Object.entries(expected)) {
    if (!(k in actual)) { detail.push(`missing: ${k}`); continue; }
    if (JSON.stringify(actual[k]) !== JSON.stringify(v)) detail.push(`${k}: expected ${JSON.stringify(v)}, got ${JSON.stringify(actual[k])}`);
  }
  return { ok: detail.length === 0, detail };
}''',
        "provides": "containsSubset(actual, expected)",
        "depends": [],
    },
    {
        "id": "test-fake-network",
        "name": "Fake Network Layer",
        "category": "test",
        "lang": "typescript",
        "when": "Simulating latency and failures for fetch",
        "why": "Atomic layer: wrapped fetch in, fault injection (latency, rate of errors) out",
        "tags": ["test", "network", "fake", "latency", "fault"],
        "iface": r'''export class FakeNetwork {
  constructor(opts?: { latencyMs?: number; failRate?: number; baseFetch?: typeof fetch })
  install(): void
  uninstall(): void
  get callCount(): number
}''',
        "code": r'''export class FakeNetwork {
  private orig: typeof fetch;
  private count = 0;
  constructor(private opts: { latencyMs?: number; failRate?: number; baseFetch?: typeof fetch } = {}, baseFetch: typeof fetch = globalThis.fetch.bind(globalThis)) {
    this.orig = baseFetch;
  }
  install() {
    const self = this;
    const base = this.opts.baseFetch ?? this.orig;
    globalThis.fetch = async (...args: Parameters<typeof fetch>) => {
      self.count++;
      if (self.opts.latencyMs) await new Promise((r) => setTimeout(r, self.opts.latencyMs));
      if (self.opts.failRate && Math.random() < self.opts.failRate) throw new Error('network failure (injected)');
      return base(...args);
    };
  }
  uninstall() { globalThis.fetch = this.orig; }
  get callCount() { return this.count; }
}''',
        "provides": "FakeNetwork",
        "depends": [],
    },
    {
        "id": "test-name-format",
        "name": "Test Name Hierarchizer",
        "category": "test",
        "lang": "typescript",
        "when": "Building readable hierarchical test names from describe/it",
        "why": "Atomic formatter: parts in, joined full name out, skips empties",
        "tags": ["test", "name", "describe", "format", "hierarchy"],
        "iface": r'''export function testName(...parts: Array<string | undefined>): string''',
        "code": r'''export function testName(...parts: Array<string | undefined>) {
  return parts.filter(Boolean).map((p) => p!.trim()).join(' › ');
}''',
        "provides": "testName(...parts)",
        "depends": [],
    },
    {
        "id": "test-skip-filter",
        "name": "Skip/Only Filter",
        "category": "test",
        "lang": "typescript",
        "when": "Running only a subset of tests during development",
        "why": "Atomic filter: names + pattern in, matched subset out, focused mode",
        "tags": ["test", "skip", "only", "filter", "pattern"],
        "iface": r'''export function filterTests<T extends { name: string }>(tests: T[], pattern?: string, onlyPattern?: string): T[]''',
        "code": r'''export function filterTests<T extends { name: string }>(tests: T[], pattern?: string, onlyPattern?: string) {
  const only = onlyPattern ? tests.filter((t) => t.name.includes(onlyPattern)) : [];
  if (only.length) return only;
  return pattern ? tests.filter((t) => t.name.includes(pattern)) : tests;
}''',
        "provides": "filterTests(tests, pattern, onlyPattern)",
        "depends": [],
    },
    {
        "id": "test-threshold-sweep",
        "name": "Threshold Sweep",
        "category": "test",
        "lang": "typescript",
        "when": "Finding the input value where behavior flips",
        "why": "Atomic sweep: fn + range in, bisection to first flip, bounded iterations",
        "tags": ["test", "threshold", "sweep", "bisect", "search"],
        "iface": r'''export function findThreshold(fn: (x: number) => boolean, lo: number, hi: number, precision?: number): number''',
        "code": r'''export function findThreshold(fn: (x: number) => boolean, lo: number, hi: number, precision = 1e-6) {
  let left = lo, right = hi;
  while (right - left > precision) {
    const mid = (left + right) / 2;
    if (fn(mid) === fn(lo)) left = mid; else right = mid;
  }
  return (left + right) / 2;
}''',
        "provides": "findThreshold(fn, lo, hi, precision)",
        "depends": [],
    },
    {
        "id": "test-pairwise",
        "name": "Pairwise Combiner",
        "category": "test",
        "lang": "typescript",
        "when": "Generating pairwise test combinations to limit combinatorial explosion",
        "why": "Atomic combiner: dimension lists in, pairwise cover of pairs out",
        "tags": ["test", "pairwise", "combinatorial", "cover", "design"],
        "iface": r'''export function pairwise<T extends Record<string, unknown>>(dimensions: Record<string, unknown[]>): Array<T>''',
        "code": r'''export function pairwise<T extends Record<string, unknown>>(dimensions: Record<string, unknown[]>) {
  const keys = Object.keys(dimensions);
  if (!keys.length) return [];
  const combos = keys.map((k) => dimensions[k].map((v) => ({ [k]: v })));
  const out: Array<Record<string, unknown>> = [];
  const seenPairs = new Set<string>();
  const all = (() => { let total = 1; for (const c of combos) total *= c.length; return total; })();
  for (let i = 0; i < Math.min(all, 2000); i++) {
    const row: Record<string, unknown> = {};
    for (let d = 0; d < keys.length; d++) row[keys[d]] = combos[d][(i * 7 + d * 13) % combos[d].length][keys[d]];
    let newPairs = 0;
    for (let a = 0; a < keys.length; a++) for (let b = a + 1; b < keys.length; b++) {
      const p = `${a}:${JSON.stringify(row[keys[a]])}|${b}:${JSON.stringify(row[keys[b]])}`;
      if (!seenPairs.has(p)) { seenPairs.add(p); newPairs++; }
    }
    if (newPairs) out.push(row);
  }
  return out as T[];
}''',
        "provides": "pairwise(dimensions)",
        "depends": [],
    },
]
