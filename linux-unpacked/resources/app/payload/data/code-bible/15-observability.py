# -*- coding: utf-8 -*-
"""
Code Bible — Category 15: Observability (atomic, single-responsibility).
Convention: pure aggregators/formatters; sinks are injected, never imported.
"""
CHUNKS = [
    {
        "id": "obs-json-logger",
        "name": "Structured JSON Logger",
        "category": "obs",
        "lang": "typescript",
        "when": "Emitting searchable JSON log lines with levels and context",
        "why": "Atomic logger: level + message + fields in, one-line JSON out, sink injected",
        "tags": ["obs", "log", "json", "structured", "logger"],
        "iface": r'''export type LogLevel = 'debug' | 'info' | 'warn' | 'error'
export class JsonLogger {
  constructor(opts?: { level?: LogLevel; sink?: (line: string) => void; baseFields?: Record<string, unknown> })
  log(level: LogLevel, message: string, fields?: Record<string, unknown>): void
  info(msg: string, fields?: Record<string, unknown>): void
  warn(msg: string, fields?: Record<string, unknown>): void
  error(msg: string, fields?: Record<string, unknown>): void
  child(baseFields: Record<string, unknown>): JsonLogger
}''',
        "code": r'''const ORDER: LogLevel[] = ['debug', 'info', 'warn', 'error'];
export class JsonLogger {
  private levelIdx: number;
  constructor(private opts: { level?: LogLevel; sink?: (line: string) => void; baseFields?: Record<string, unknown> } = {}) {
    this.levelIdx = ORDER.indexOf(opts.level ?? 'info');
  }
  log(level: LogLevel, message: string, fields: Record<string, unknown> = {}) {
    if (ORDER.indexOf(level) < this.levelIdx) return;
    const line = JSON.stringify({ ts: new Date().toISOString(), level, msg: message, ...this.opts.baseFields, ...fields });
    (this.opts.sink ?? console.log)(line);
  }
  info(msg: string, f?: Record<string, unknown>) { this.log('info', msg, f); }
  warn(msg: string, f?: Record<string, unknown>) { this.log('warn', msg, f); }
  error(msg: string, f?: Record<string, unknown>) { this.log('error', msg, f); }
  child(baseFields: Record<string, unknown>) {
    return new JsonLogger({ ...this.opts, baseFields: { ...this.opts.baseFields, ...baseFields } });
  }
}''',
        "provides": "JsonLogger",
        "depends": [],
    },
    {
        "id": "obs-metrics-registry",
        "name": "Metrics Registry (counters/gauges)",
        "category": "obs",
        "lang": "typescript",
        "when": "Collecting runtime counters and gauges for Prometheus-style scraping",
        "why": "Atomic registry: named counters/gauges, snapshot for exporters, no deps",
        "tags": ["obs", "metrics", "counter", "gauge", "registry"],
        "iface": r'''export class MetricsRegistry {
  counter(name: string, delta?: number): number
  gauge(name: string, value?: number): number | undefined
  labels(name: string, labels: Record<string, string>, delta?: number): void
  snapshot(): Record<string, number | string>
}''',
        "code": r'''export class MetricsRegistry {
  private counters = new Map<string, number>();
  private gauges = new Map<string, number>();
  private labelCounters = new Map<string, Map<string, number>>();
  counter(name: string, delta = 1) {
    const v = (this.counters.get(name) ?? 0) + delta;
    this.counters.set(name, v);
    return v;
  }
  gauge(name: string, value?: number) {
    if (value !== undefined) this.gauges.set(name, value);
    return this.gauges.get(name);
  }
  labels(name: string, labels: Record<string, string>, delta = 1) {
    if (!this.labelCounters.has(name)) this.labelCounters.set(name, new Map());
    const m = this.labelCounters.get(name)!;
    const key = Object.entries(labels).map(([k, v]) => `${k}="${v}"`).join(',');
    m.set(key, (m.get(key) ?? 0) + delta);
  }
  snapshot() {
    const out: Record<string, number | string> = {};
    for (const [k, v] of this.counters) out[`counter_${k}`] = v;
    for (const [k, v] of this.gauges) out[`gauge_${k}`] = v;
    return out;
  }
}''',
        "provides": "MetricsRegistry",
        "depends": [],
    },
    {
        "id": "obs-timer",
        "name": "Timer (duration capture)",
        "category": "obs",
        "lang": "typescript",
        "when": "Measuring how long an operation took and reporting it",
        "why": "Atomic timer: start/stop, ms out with label, no monkey-patching",
        "tags": ["obs", "timer", "duration", "latency", "measure"],
        "iface": r'''export class Stopwatch {
  start(): void
  stop(): number
  get elapsedMs(): number
}
export function timeAsync<T>(label: string, fn: () => Promise<T>, report: (label: string, ms: number) => void): Promise<T>''',
        "code": r'''export class Stopwatch {
  private t0 = 0;
  start() { this.t0 = performance.now(); }
  stop() { return this.elapsedMs; }
  get elapsedMs() { return this.t0 ? performance.now() - this.t0 : 0; }
}
export async function timeAsync<T>(label: string, fn: () => Promise<T>, report: (label: string, ms: number) => void) {
  const w = new Stopwatch();
  w.start();
  try { return await fn(); } finally { report(label, w.elapsedMs); }
}''',
        "provides": "Stopwatch / timeAsync",
        "depends": [],
    },
    {
        "id": "obs-correlation-id",
        "name": "Correlation ID Middleware",
        "category": "obs",
        "lang": "typescript",
        "when": "Propagating a request ID through logs and downstream calls",
        "why": "Atomic middleware: incoming id or generated, stored on context, async-local optional",
        "tags": ["obs", "correlation", "id", "trace", "middleware"],
        "iface": r'''export function correlationId(headerValue?: string): string
export function withCorrelation<T>(id: string, fn: () => T): T
export class Correlator {
  current(): string
  run<T>(fn: () => T): T
}''',
        "code": r'''let cur = '';
export function correlationId(headerValue?: string) {
  return headerValue || Math.random().toString(36).slice(2, 12);
}
export function withCorrelation<T>(id: string, fn: () => T) { const prev = cur; cur = id; try { return fn(); } finally { cur = prev; } }
export class Correlator {
  current() { return cur || 'no-corr'; }
  run<T>(fn: () => T) { return withCorrelation(this.current(), fn); }
}''',
        "provides": "correlationId / withCorrelation / Correlator",
        "depends": [],
    },
    {
        "id": "obs-trace-span",
        "name": "Trace Span (start/end)",
        "category": "obs",
        "lang": "typescript",
        "when": "Recording a named operation with start/end times and status",
        "why": "Atomic span: begin/end in, W3C-style span object out, parent id optional",
        "tags": ["obs", "trace", "span", "start", "end"],
        "iface": r'''export interface Span { id: string; name: string; startMs: number; endMs: number; durationMs: number; status: 'ok' | 'error'; parentId?: string }
export class SpanBuilder {
  constructor(name: string, opts?: { parentId?: string })
  end(status?: 'ok' | 'error'): Span
  get durationMs(): number
}''',
        "code": r'''export class SpanBuilder {
  private startMs = performance.now();
  private endMs = 0;
  readonly id: string;
  constructor(public name: string, public parentId?: string) {
    this.id = Math.random().toString(36).slice(2, 12);
  }
  end(status: 'ok' | 'error' = 'ok') {
    this.endMs = performance.now();
    return { id: this.id, name: this.name, startMs: this.startMs, endMs: this.endMs, durationMs: this.durationMs, status, parentId: this.parentId };
  }
  get durationMs() { return (this.endMs || performance.now()) - this.startMs; }
}''',
        "provides": "SpanBuilder",
        "depends": [],
    },
    {
        "id": "obs-level-filter",
        "name": "Log Level Filter",
        "category": "obs",
        "lang": "typescript",
        "when": "Deciding whether a log line at a given level should be emitted",
        "why": "Atomic filter: configured level + candidate in, boolean out — no logging side effects",
        "tags": ["obs", "log", "level", "filter", "threshold"],
        "iface": r'''export type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'silent'
export function shouldLog(configured: LogLevel, candidate: LogLevel): boolean''',
        "code": r'''const RANK: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3, silent: 99 };
export function shouldLog(configured: LogLevel, candidate: LogLevel) {
  return RANK[candidate] >= RANK[configured];
}''',
        "provides": "shouldLog(configured, candidate)",
        "depends": [],
    },
    {
        "id": "obs-error-budget",
        "name": "Error Budget Calculator",
        "category": "obs",
        "lang": "typescript",
        "when": "Computing remaining SLO error budget from availability",
        "why": "Atomic calculator: SLO + window + observed in, budget % out",
        "tags": ["obs", "error", "budget", "slo", "availability"],
        "iface": r'''export function errorBudget(opts: { sloPct: number; windowSeconds: number; unavailableSeconds: number }): { errorBudgetPct: number; remaining: number; burnedPct: number }''',
        "code": r'''export function errorBudget(opts: { sloPct: number; windowSeconds: number; unavailableSeconds: number }) {
  const allowed = (1 - opts.sloPct / 100) * opts.windowSeconds;
  const burnedPct = (opts.unavailableSeconds / allowed) * 100;
  return {
    errorBudgetPct: opts.sloPct,
    remaining: Math.max(0, allowed - opts.unavailableSeconds),
    burnedPct: Math.min(100, burnedPct),
  };
}''',
        "provides": "errorBudget(opts)",
        "depends": [],
    },
    {
        "id": "obs-window-stats",
        "name": "Rolling Window Stats",
        "category": "obs",
        "lang": "typescript",
        "when": "Computing mean/min/max over the last N samples",
        "why": "Atomic aggregator: sample in, windowed stats out, ring-buffer storage",
        "tags": ["obs", "rolling", "window", "stats", "aggregate"],
        "iface": r'''export class RollingStats {
  constructor(window?: number)
  push(value: number): void
  get stats(): { mean: number; min: number; max: number; last: number; n: number }
  reset(): void
}''',
        "code": r'''export class RollingStats {
  private buf: number[] = [];
  constructor(private window = 100) {}
  push(value: number) {
    this.buf.push(value);
    if (this.buf.length > this.window) this.buf.shift();
  }
  get stats() {
    if (!this.buf.length) return { mean: 0, min: 0, max: 0, last: 0, n: 0 };
    const min = Math.min(...this.buf), max = Math.max(...this.buf);
    const sum = this.buf.reduce((s, v) => s + v, 0);
    return { mean: sum / this.buf.length, min, max, last: this.buf[this.buf.length - 1], n: this.buf.length };
  }
  reset() { this.buf = []; }
}''',
        "provides": "RollingStats",
        "depends": [],
    },
    {
        "id": "obs-percentile",
        "name": "Percentile Calculator",
        "category": "obs",
        "lang": "typescript",
        "when": "Computing p50/p95/p99 latency from samples",
        "why": "Atomic quantile: nearest-rank method, sorted copy, no mutation",
        "tags": ["obs", "percentile", "p95", "p99", "latency"],
        "iface": r'''export function percentile(sortedOrRaw: number[], p: number): number
export function latencySummary(samples: number[]): { p50: number; p95: number; p99: number; max: number }''',
        "code": r'''export function percentile(sortedOrRaw: number[], p: number) {
  const s = [...sortedOrRaw].sort((a, b) => a - b);
  if (!s.length) return 0;
  const idx = Math.min(s.length - 1, Math.max(0, Math.ceil((p / 100) * s.length) - 1));
  return s[idx];
}
export function latencySummary(samples: number[]) {
  return { p50: percentile(samples, 50), p95: percentile(samples, 95), p99: percentile(samples, 99), max: samples.length ? Math.max(...samples) : 0 };
}''',
        "provides": "percentile / latencySummary",
        "depends": [],
    },
    {
        "id": "obs-alert-check",
        "name": "Alert Threshold Checker",
        "category": "obs",
        "lang": "typescript",
        "when": "Firing alerts when a metric crosses a threshold with hysteresis",
        "why": "Atomic checker: value + threshold in, stateful edge detection out",
        "tags": ["obs", "alert", "threshold", "hysteresis", "fire"],
        "iface": r'''export class ThresholdAlert {
  constructor(opts: { upper: number; lower?: number; onFire: () => void; onClear?: () => void })
  update(value: number): 'fired' | 'cleared' | 'ok'
  get active(): boolean
}''',
        "code": r'''export class ThresholdAlert {
  private fired = false;
  constructor(private opts: { upper: number; lower?: number; onFire: () => void; onClear?: () => void }) {}
  update(value: number) {
    if (value >= this.opts.upper && !this.fired) { this.fired = true; this.opts.onFire(); return 'fired'; }
    const lower = this.opts.lower ?? this.opts.upper;
    if (value <= lower && this.fired) { this.fired = false; this.opts.onClear?.(); return 'cleared'; }
    return 'ok';
  }
  get active() { return this.fired; }
}''',
        "provides": "ThresholdAlert",
        "depends": [],
    },
    {
        "id": "obs-rate-counter",
        "name": "Event Rate Counter",
        "category": "obs",
        "lang": "typescript",
        "when": "Computing events-per-second from a timestamp stream",
        "why": "Atomic counter: event() in, events/sec out over a sliding window",
        "tags": ["obs", "rate", "counter", "events", "per-second"],
        "iface": r'''export class RateCounter {
  constructor(windowMs?: number)
  event(): void
  get ratePerSecond(): number
}''',
        "code": r'''export class RateCounter {
  private stamps: number[] = [];
  constructor(private windowMs = 1000) {}
  event() {
    const now = Date.now();
    this.stamps.push(now);
    while (this.stamps.length && now - this.stamps[0] > this.windowMs) this.stamps.shift();
  }
  get ratePerSecond() { return this.stamps.length / (this.windowMs / 1000); }
}''',
        "provides": "RateCounter",
        "depends": [],
    },
    {
        "id": "obs-sampler",
        "name": "Sampling Rate Limiter",
        "category": "obs",
        "lang": "typescript",
        "when": "Keeping only a fraction of events for logs or traces",
        "why": "Atomic sampler: ratio in, deterministic-ish accept in, seeded option",
        "tags": ["obs", "sampler", "sample", "rate", "trace"],
        "iface": r'''export function shouldSample(ratio: number, seed?: string): boolean''',
        "code": r'''export function shouldSample(ratio: number, seed?: string) {
  if (ratio >= 1) return true;
  if (ratio <= 0) return false;
  if (seed) {
    let h = 2166136261;
    for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
    return ((h >>> 0) % 10000) / 10000 < ratio;
  }
  return Math.random() < ratio;
}''',
        "provides": "shouldSample(ratio, seed)",
        "depends": [],
    },
    {
        "id": "obs-log-redact",
        "name": "Log Redaction Filter",
        "category": "obs",
        "lang": "typescript",
        "when": "Stripping PII/keys from log payloads before they leave the process",
        "why": "Atomic filter: object in, deep-redacted clone out, key-name based",
        "tags": ["obs", "redact", "log", "pii", "filter"],
        "iface": r'''export function redactLog<T>(value: T, sensitiveKeys?: RegExp): T''',
        "code": r'''const DEFAULT_KEY = /(password|passwd|secret|token|api[_-]?key|authorization|cookie|ssn)/i;
export function redactLog<T>(value: T, sensitiveKeys: RegExp = DEFAULT_KEY): T {
  if (Array.isArray(value)) return value.map((v) => redactLog(v, sensitiveKeys)) as unknown as T;
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = sensitiveKeys.test(k) ? '***' : redactLog(v, sensitiveKeys);
    }
    return out as T;
  }
  return value;
}''',
        "provides": "redactLog(value, sensitiveKeys)",
        "depends": [],
    },
    {
        "id": "obs-slow-reporter",
        "name": "Slow-Operation Reporter",
        "category": "obs",
        "lang": "typescript",
        "when": "Flagging operations slower than a threshold",
        "why": "Atomic reporter: duration in, threshold applied, report callback on breach",
        "tags": ["obs", "slow", "reporter", "threshold", "performance"],
        "iface": r'''export function reportIfSlow(opts: { label: string; ms: number; thresholdMs: number; onSlow: (label: string, ms: number, overByMs: number) => void }): boolean''',
        "code": r'''export function reportIfSlow(opts: { label: string; ms: number; thresholdMs: number; onSlow: (label: string, ms: number, overByMs: number) => void }) {
  if (opts.ms >= opts.thresholdMs) {
    opts.onSlow(opts.label, opts.ms, opts.ms - opts.thresholdMs);
    return true;
  }
  return false;
}''',
        "provides": "reportIfSlow(opts)",
        "depends": [],
    },
    {
        "id": "obs-uptime",
        "name": "Uptime Tracker",
        "category": "obs",
        "lang": "typescript",
        "when": "Tracking service availability over check intervals",
        "why": "Atomic tracker: ok/fail in, availability % + duration out",
        "tags": ["obs", "uptime", "availability", "tracker", "health"],
        "iface": r'''export class UptimeTracker {
  constructor(windowChecks?: number)
  record(ok: boolean): void
  get availabilityPct(): number
  get consecutiveFailures(): number
}''',
        "code": r'''export class UptimeTracker {
  private checks: boolean[] = [];
  constructor(private windowChecks = 1000) {}
  record(ok: boolean) {
    this.checks.push(ok);
    if (this.checks.length > this.windowChecks) this.checks.shift();
  }
  get availabilityPct() {
    if (!this.checks.length) return 100;
    return (this.checks.filter(Boolean).length / this.checks.length) * 100;
  }
  get consecutiveFailures() {
    let n = 0;
    for (let i = this.checks.length - 1; i >= 0 && !this.checks[i]; i--) n++;
    return n;
  }
}''',
        "provides": "UptimeTracker",
        "depends": [],
    },
    {
        "id": "obs-resource-meter",
        "name": "Resource Meter",
        "category": "obs",
        "lang": "typescript",
        "when": "Sampling process memory and CPU usage",
        "why": "Atomic meter: process.memoryUsage in, MB snapshot out, delta-aware",
        "tags": ["obs", "resource", "memory", "cpu", "meter"],
        "iface": r'''export function memorySnapshot(processRef: NodeJS.Process = process): { rssMb: number; heapUsedMb: number; heapTotalMb: number }''',
        "code": r'''export function memorySnapshot(processRef: NodeJS.Process = process) {
  const m = processRef.memoryUsage();
  return { rssMb: +(m.rss / 1048576).toFixed(1), heapUsedMb: +(m.heapUsed / 1048576).toFixed(1), heapTotalMb: +(m.heapTotal / 1048576).toFixed(1) };
}''',
        "provides": "memorySnapshot(processRef)",
        "depends": [],
    },
    {
        "id": "obs-error-envelope",
        "name": "Structured Error Envelope",
        "category": "obs",
        "lang": "typescript",
        "when": "Normalizing thrown errors into machine-readable error objects",
        "why": "Atomic envelope: unknown thrown in, {code, message, cause, stack} out",
        "tags": ["obs", "error", "envelope", "structured", "normalize"],
        "iface": r'''export interface ErrorEnvelope { code: string; message: string; cause?: string; stack?: string }
export function toEnvelope(err: unknown, fallbackCode = 'UNKNOWN'): ErrorEnvelope''',
        "code": r'''export function toEnvelope(err: unknown, fallbackCode = 'UNKNOWN'): ErrorEnvelope {
  if (err instanceof Error) {
    return { code: (err as Error & { code?: string }).code ?? fallbackCode, message: err.message, stack: err.stack };
  }
  if (typeof err === 'object' && err !== null) {
    const e = err as Record<string, unknown>;
    return { code: String(e.code ?? fallbackCode), message: String(e.message ?? JSON.stringify(e)) };
  }
  return { code: fallbackCode, message: String(err) };
}''',
        "provides": "toEnvelope(err, fallbackCode)",
        "depends": [],
    },
    {
        "id": "obs-req-log",
        "name": "Request Log Formatter",
        "category": "obs",
        "lang": "typescript",
        "when": "Formatting an HTTP request line for access logs",
        "why": "Atomic formatter: method/path/status/ms in, access-log line out",
        "tags": ["obs", "request", "log", "access", "format"],
        "iface": r'''export function accessLine(opts: { method: string; path: string; status: number; ms: number; ip?: string; userAgent?: string }): string''',
        "code": r'''export function accessLine(opts: { method: string; path: string; status: number; ms: number; ip?: string; userAgent?: string }) {
  return `${new Date().toISOString()} ${opts.ip ?? '-'} "${opts.method} ${opts.path}" ${opts.status} ${opts.ms.toFixed(1)}ms ${opts.userAgent ?? '-'}`;
}''',
        "provides": "accessLine(opts)",
        "depends": [],
    },
    {
        "id": "obs-trend",
        "name": "Trend Slope Detector",
        "category": "obs",
        "lang": "typescript",
        "when": "Detecting whether a metric is trending up or down",
        "why": "Atomic trend: least-squares slope over samples, normalized, sign out",
        "tags": ["obs", "trend", "slope", "detector", "regression"],
        "iface": r'''export function trendSlope(samples: number[]): number
export function trendDirection(samples: number[]): 'up' | 'down' | 'flat' ''',
        "code": r'''export function trendSlope(samples: number[]) {
  const n = samples.length;
  if (n < 2) return 0;
  const xs = samples.map((_, i) => i);
  const mx = xs.reduce((s, v) => s + v, 0) / n;
  const my = samples.reduce((s, v) => s + v, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) { num += (xs[i] - mx) * (samples[i] - my); den += (xs[i] - mx) ** 2; }
  return den ? num / den : 0;
}
export function trendDirection(samples: number[]) {
  const s = trendSlope(samples);
  return s > 1e-6 ? 'up' : s < -1e-6 ? 'down' : 'flat';
}''',
        "provides": "trendSlope / trendDirection",
        "depends": [],
    },
    {
        "id": "obs-cardinality",
        "name": "Cardinality Counter",
        "category": "obs",
        "lang": "typescript",
        "when": "Counting distinct values (unique users, unique keys)",
        "why": "Atomic counter: value in, distinct count out with optional cap",
        "tags": ["obs", "cardinality", "distinct", "count", "unique"],
        "iface": r'''export class CardinalityCounter {
  constructor(maxTracked?: number)
  add(value: string): number
  get count(): number
}''',
        "code": r'''export class CardinalityCounter {
  private set = new Set<string>();
  constructor(private maxTracked = 100000) {}
  add(value: string) {
    if (this.set.size < this.maxTracked) this.set.add(value);
    return this.set.size;
  }
  get count() { return this.set.size; }
}''',
        "provides": "CardinalityCounter",
        "depends": [],
    },
    {
        "id": "obs-histogram",
        "name": "Bucketed Histogram",
        "category": "obs",
        "lang": "typescript",
        "when": "Tallying values into latency buckets",
        "why": "Atomic histogram: value in, bucket counts out with cumulative option",
        "tags": ["obs", "histogram", "bucket", "distribution", "latency"],
        "iface": r'''export class Histogram {
  constructor(buckets?: number[])
  observe(value: number): void
  get counts(): Record<string, number>
  get cumulative(): Record<string, number>
}''',
        "code": r'''const DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];
export class Histogram {
  private counts = new Map<number, number>();
  private overflow = 0;
  constructor(private buckets = DEFAULT_BUCKETS) {}
  observe(value: number) {
    let placed = false;
    for (const b of this.buckets) {
      if (value <= b) { this.counts.set(b, (this.counts.get(b) ?? 0) + 1); placed = true; break; }
    }
    if (!placed) this.overflow++;
  }
  get counts() {
    const out: Record<string, number> = {};
    for (const [b, c] of this.counts) out[`le_${b}`] = c;
    if (this.overflow) out.overflow = this.overflow;
    return out;
  }
  get cumulative() {
    const out: Record<string, number> = {};
    let running = 0;
    for (const b of this.buckets) { running += this.counts.get(b) ?? 0; out[`le_${b}`] = running; }
    out.overflow = this.overflow;
    return out;
  }
}''',
        "provides": "Histogram",
        "depends": [],
    },
    {
        "id": "obs-dlq",
        "name": "Dead-Letter Tracker",
        "category": "obs",
        "lang": "typescript",
        "when": "Tracking failed jobs/messages that exhausted retries",
        "why": "Atomic tracker: record in, count + oldest/newest out, capped storage",
        "tags": ["obs", "dead-letter", "queue", "failed", "tracker"],
        "iface": r'''export interface DeadLetterRecord { id: string; error: string; at: number; attempts: number }
export class DeadLetterTracker {
  constructor(cap?: number)
  record(r: DeadLetterRecord): void
  get count(): number
  drain(): DeadLetterRecord[]
}''',
        "code": r'''export class DeadLetterTracker {
  private items: DeadLetterRecord[] = [];
  constructor(private cap = 1000) {}
  record(r: DeadLetterRecord) {
    this.items.push(r);
    if (this.items.length > this.cap) this.items.shift();
  }
  get count() { return this.items.length; }
  drain() { const all = this.items; this.items = []; return all; }
}''',
        "provides": "DeadLetterTracker",
        "depends": [],
    },
    {
        "id": "obs-slo-check",
        "name": "SLO Conformance Checker",
        "category": "obs",
        "lang": "typescript",
        "when": "Verifying a service still meets its SLO from measured availability",
        "why": "Atomic checker: measured + target in, pass/fail + gap out",
        "tags": ["obs", "slo", "conformance", "check", "target"],
        "iface": r'''export function sloCheck(measuredPct: number, targetPct: number): { pass: boolean; gapPct: number; marginPct: number }''',
        "code": r'''export function sloCheck(measuredPct: number, targetPct: number) {
  return { pass: measuredPct >= targetPct, gapPct: Math.max(0, targetPct - measuredPct), marginPct: measuredPct - targetPct };
}''',
        "provides": "sloCheck(measuredPct, targetPct)",
        "depends": [],
    },
    {
        "id": "obs-health-json",
        "name": "Health Response Builder",
        "category": "obs",
        "lang": "typescript",
        "when": "Assembling the standard /health JSON payload",
        "why": "Atomic builder: component checks in, consistent health object out",
        "tags": ["obs", "health", "json", "builder", "status"],
        "iface": r'''export interface HealthComponent { name: string; status: 'up' | 'down' | 'degraded'; latencyMs?: number }
export function healthPayload(components: HealthComponent[], version?: string): Record<string, unknown>''',
        "code": r'''export function healthPayload(components: HealthComponent[], version?: string) {
  const down = components.filter((c) => c.status === 'down').map((c) => c.name);
  const degraded = components.filter((c) => c.status === 'degraded').map((c) => c.name);
  return {
    status: down.length ? 'degraded' : degraded.length ? 'degraded' : 'ok',
    checks: components,
    ...(version ? { version } : {}),
    ...(down.length ? { down } : {}),
    ...(degraded.length ? { degraded } : {}),
    timestamp: new Date().toISOString(),
  };
}''',
        "provides": "healthPayload(components, version)",
        "depends": [],
    },
]
