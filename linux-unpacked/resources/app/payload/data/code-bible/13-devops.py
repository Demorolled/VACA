# -*- coding: utf-8 -*-
"""
Code Bible — Category 13: DevOps & tooling (atomic, single-responsibility).
Convention: pure helpers; no process execution, no global state.
"""
CHUNKS = [
    {
        "id": "devops-semver",
        "name": "SemVer Compare & Bump",
        "category": "devops",
        "lang": "typescript",
        "when": "Comparing version strings and computing the next release version",
        "why": "Atomic semver: parse/compare/bump majors, minors and patches without a lib",
        "tags": ["devops", "semver", "version", "bump", "compare"],
        "iface": r'''export interface SemVer { major: number; minor: number; patch: number }
export function parseSemVer(v: string): SemVer | null
export function compareSemVer(a: SemVer, b: SemVer): number
export function bumpSemVer(v: string, part: 'major' | 'minor' | 'patch'): string''',
        "code": r'''export function parseSemVer(v: string): SemVer | null {
  const m = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(v.trim());
  return m ? { major: +m[1], minor: +m[2], patch: +m[3] } : null;
}
export function compareSemVer(a: SemVer, b: SemVer) {
  for (const k of ['major', 'minor', 'patch'] as const) {
    if (a[k] !== b[k]) return a[k] > b[k] ? 1 : -1;
  }
  return 0;
}
export function bumpSemVer(v: string, part: 'major' | 'minor' | 'patch') {
  const s = parseSemVer(v);
  if (!s) return v;
  if (part === 'major') { s.major++; s.minor = 0; s.patch = 0; }
  else if (part === 'minor') { s.minor++; s.patch = 0; }
  else s.patch++;
  return `${s.major}.${s.minor}.${s.patch}`;
}''',
        "provides": "parseSemVer / compareSemVer / bumpSemVer",
        "depends": [],
    },
    {
        "id": "devops-env-file",
        "name": "Env File Parser/Writer",
        "category": "devops",
        "lang": "typescript",
        "when": "Reading and writing .env files without a dependency",
        "why": "Atomic dotenv: comments/quotes handled, round-trip safe write",
        "tags": ["devops", "env", "dotenv", "parse", "write", "config"],
        "iface": r'''export function parseEnv(content: string): Record<string, string>
export function serializeEnv(env: Record<string, string>): string''',
        "code": r'''export function parseEnv(content: string) {
  const out: Record<string, string> = {};
  for (const line of content.split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq < 0) continue;
    const key = t.slice(0, eq).trim();
    let val = t.slice(eq + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    out[key] = val;
  }
  return out;
}
export function serializeEnv(env: Record<string, string>) {
  return Object.entries(env).map(([k, v]) => `${k}=${/[\s#]/.test(v) ? JSON.stringify(v) : v}`).join('\n') + '\n';
}''',
        "provides": "parseEnv / serializeEnv",
        "depends": [],
    },
    {
        "id": "devops-cron-validate",
        "name": "Cron Expression Validator",
        "category": "devops",
        "lang": "typescript",
        "when": "Checking a 5-field cron expression before scheduling",
        "why": "Atomic validator: field range checks, * and step forms, no parsing side effects",
        "tags": ["devops", "cron", "validate", "schedule", "timer"],
        "iface": r'''export function isValidCron(expr: string): boolean''',
        "code": r'''export function isValidCron(expr: string) {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  const ranges = [[0, 59], [0, 23], [1, 31], [1, 12], [0, 7]];
  return parts.every((part, i) => {
    for (const field of part.split(',')) {
      const [lo, hi] = ranges[i];
      const m = /^(\*|\d+)(?:\/(\d+))?$/.exec(field);
      if (!m) return false;
      if (m[1] !== '*') { const v = +m[1]; if (v < lo || v > hi) return false; }
      if (m[2] && (+m[2] <= 0 || +m[2] > hi)) return false;
    }
    return true;
  });
}''',
        "provides": "isValidCron(expr)",
        "depends": [],
    },
    {
        "id": "devops-health-wait",
        "name": "Health Wait Poller",
        "category": "devops",
        "lang": "typescript",
        "when": "Polling an endpoint until it reports healthy or a deadline passes",
        "why": "Atomic readiness loop: check fn + interval + deadline, resolved or timeout",
        "tags": ["devops", "health", "wait", "poll", "readiness"],
        "iface": r'''export async function waitForHealthy(check: () => Promise<boolean>, opts?: { intervalMs?: number; timeoutMs?: number }): Promise<boolean>''',
        "code": r'''export async function waitForHealthy(check: () => Promise<boolean>, opts = {}) {
  const { intervalMs = 1000, timeoutMs = 60000 } = opts;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { if (await check()) return true; } catch { /* not ready yet */ }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}''',
        "provides": "waitForHealthy(check, opts)",
        "depends": [],
    },
    {
        "id": "devops-port-alloc",
        "name": "Free Port Allocator",
        "category": "devops",
        "lang": "typescript",
        "when": "Finding an unused local TCP port for a dev server",
        "why": "Atomic allocator: try port then random fallbacks, returns bound-and-closed port",
        "tags": ["devops", "port", "alloc", "tcp", "server"],
        "iface": r'''export async function findFreePort(preferred?: number): Promise<number>''',
        "code": r'''import * as net from 'net';
export async function findFreePort(preferred?: number) {
  const candidates = preferred ? [preferred, ...Array.from({ length: 10 }, (_, i) => 2000 + Math.floor(Math.random() * 20000))] : [];
  for (const port of candidates) {
    const ok = await new Promise<boolean>((resolve) => {
      const srv = net.createServer();
      srv.once('error', () => resolve(false));
      srv.once('listening', () => srv.close(() => resolve(true)));
      srv.listen(port, '127.0.0.1');
    });
    if (ok) return port;
  }
  throw new Error('No free port found');
}''',
        "provides": "findFreePort(preferred)",
        "depends": [],
    },
    {
        "id": "devops-timeout-wrap",
        "name": "Timeout Wrapper",
        "category": "devops",
        "lang": "typescript",
        "when": "Bounding any async operation so it fails fast instead of hanging",
        "why": "Atomic guard: promise + ms in, settled promise out, original timer cleared",
        "tags": ["devops", "timeout", "async", "guard", "deadline"],
        "iface": r'''export function withTimeout<T>(p: Promise<T>, ms: number, label = 'operation'): Promise<T>''',
        "code": r'''export function withTimeout<T>(p: Promise<T>, ms: number, label = 'operation') {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}''',
        "provides": "withTimeout(p, ms, label)",
        "depends": [],
    },
    {
        "id": "devops-backoff-retry",
        "name": "Exponential Backoff Retry",
        "category": "devops",
        "lang": "typescript",
        "when": "Retrying a flaky operation with capped exponential backoff and jitter",
        "why": "Atomic retrier: attempts + base delay + jitter, last error surfaced",
        "tags": ["devops", "retry", "backoff", "jitter", "resilience"],
        "iface": r'''export async function retry<T>(fn: () => Promise<T>, opts?: { attempts?: number; baseMs?: number; maxMs?: number }): Promise<T>''',
        "code": r'''export async function retry<T>(fn: () => Promise<T>, opts = {}) {
  const { attempts = 3, baseMs = 200, maxMs = 5000 } = opts;
  let lastErr: unknown;
  for (let i = 0; i < attempts; i++) {
    try { return await fn(); } catch (e) { lastErr = e; }
    if (i < attempts - 1) {
      const jitter = Math.random() * baseMs;
      await new Promise((r) => setTimeout(r, Math.min(maxMs, baseMs * 2 ** i + jitter)));
    }
  }
  throw lastErr;
}''',
        "provides": "retry(fn, opts)",
        "depends": [],
    },
    {
        "id": "devops-rate-limit",
        "name": "Fixed-Window Rate Limiter",
        "category": "devops",
        "lang": "typescript",
        "when": "Allowing at most N calls per window per key",
        "why": "Atomic limiter: key + max + window, tryAcquire boolean, in-memory only",
        "tags": ["devops", "rate", "limit", "window", "throttle"],
        "iface": r'''export class FixedWindowLimiter {
  constructor(max: number, windowMs: number)
  tryAcquire(key: string): boolean
  reset(key?: string): void
}''',
        "code": r'''export class FixedWindowLimiter {
  private windows = new Map<string, { start: number; count: number }>();
  constructor(private max: number, private windowMs: number) {}
  tryAcquire(key: string) {
    const now = Date.now();
    let w = this.windows.get(key);
    if (!w || now - w.start >= this.windowMs) { w = { start: now, count: 0 }; this.windows.set(key, w); }
    if (w.count >= this.max) return false;
    w.count++;
    return true;
  }
  reset(key?: string) { if (key) this.windows.delete(key); else this.windows.clear(); }
}''',
        "provides": "FixedWindowLimiter",
        "depends": [],
    },
    {
        "id": "devops-disk-estimate",
        "name": "Size Formatter",
        "category": "devops",
        "lang": "typescript",
        "when": "Formatting byte counts as human-readable sizes",
        "why": "Atomic formatter: bytes in, 1.2 GB style strings out, binary units",
        "tags": ["devops", "size", "format", "bytes", "disk"],
        "iface": r'''export function formatBytes(bytes: number, decimals?: number): string''',
        "code": r'''export function formatBytes(bytes: number, decimals = 1) {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0, v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i === 0 ? 0 : decimals)} ${units[i]}`;
}''',
        "provides": "formatBytes(bytes, decimals)",
        "depends": [],
    },
    {
        "id": "devops-secret-mask",
        "name": "Secret Redactor",
        "category": "devops",
        "lang": "typescript",
        "when": "Masking secret values in logs and error messages",
        "why": "Atomic redactor: known keys + generic token patterns, keeps first/last chars",
        "tags": ["devops", "secret", "redact", "mask", "log"],
        "iface": r'''export function redactSecrets(text: string, keys?: string[]): string''',
        "code": r'''export function redactSecrets(text: string, keys: string[] = []) {
  let out = text;
  const patterns = [
    ...keys.map((k) => new RegExp(`(${k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*[=:]\\s*)([^\\s,;}]+)`, 'gi')),
    /(Bearer\s+)[A-Za-z0-9._~+/-]+=*/gi,
    /(sk-[A-Za-z0-9]{6})[A-Za-z0-9]+/g,
    /("(?:api[_-]?key|token|secret|password)"\s*:\s*")[^"]+(")/gi,
  ];
  for (const re of patterns) {
    out = out.replace(re, (m, ...groups) => {
      const head = groups[0] ?? '';
      const tail = groups[1] ?? '';
      return `${head}***${tail}`;
    });
  }
  return out;
}''',
        "provides": "redactSecrets(text, keys)",
        "depends": [],
    },
    {
        "id": "devops-version-stamp",
        "name": "Build Version Stamp",
        "category": "devops",
        "lang": "typescript",
        "when": "Composing a unique build identifier from package + commit info",
        "why": "Atomic stamper: inputs in, dedup-safe string out with timestamp",
        "tags": ["devops", "version", "stamp", "build", "id"],
        "iface": r'''export function buildStamp(pkg: { name: string; version: string }, commit?: string): string''',
        "code": r'''export function buildStamp(pkg: { name: string; version: string }, commit?: string) {
  const date = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rev = commit ? commit.slice(0, 8) : 'local';
  return `${pkg.name}@${pkg.version}-${rev}-${date}`;
}''',
        "provides": "buildStamp(pkg, commit)",
        "depends": [],
    },
    {
        "id": "devops-changelog-parse",
        "name": "Changelog Parser",
        "category": "devops",
        "lang": "typescript",
        "when": "Extracting the latest release section from a CHANGELOG",
        "why": "Atomic parser: ## headers split, first non-unreleased section out",
        "tags": ["devops", "changelog", "parse", "release", "notes"],
        "iface": r'''export function latestChangelogEntry(markdown: string, skipUnreleased = true): { version: string; body: string } | null''',
        "code": r'''export function latestChangelogEntry(markdown: string, skipUnreleased = true) {
  const lines = markdown.split('\n');
  let current: { version: string; body: string[] } | null = null;
  for (const line of lines) {
    const m = /^##\s+\[?([^\]]+?)\]?\s*(?:-.*)?$/.exec(line.trim());
    if (m) {
      if (current && !(skipUnreleased && /unreleased/i.test(current.version))) break;
      current = { version: m[1], body: [] };
    } else if (current) {
      current.body.push(line);
    }
  }
  return current && !(skipUnreleased && /unreleased/i.test(current.version))
    ? { version: current.version, body: current.body.join('\n').trim() }
    : null;
}''',
        "provides": "latestChangelogEntry(markdown)",
        "depends": [],
    },
    {
        "id": "devops-health-aggregate",
        "name": "Health Probe Aggregator",
        "category": "devops",
        "lang": "typescript",
        "when": "Combining many component health checks into one status",
        "why": "Atomic aggregator: named probes in, overall status + failing list out",
        "tags": ["devops", "health", "aggregate", "status", "probe"],
        "iface": r'''export interface ProbeResult { name: string; ok: boolean; detail?: string }
export function aggregateHealth(probes: ProbeResult[]): { ok: boolean; failing: string[]; detail: ProbeResult[] }''',
        "code": r'''export function aggregateHealth(probes: ProbeResult[]) {
  const failing = probes.filter((p) => !p.ok).map((p) => p.name);
  return { ok: failing.length === 0, failing, detail: probes };
}''',
        "provides": "aggregateHealth(probes)",
        "depends": [],
    },
    {
        "id": "devops-shutdown-coord",
        "name": "Graceful Shutdown Coordinator",
        "category": "devops",
        "lang": "typescript",
        "when": "Running cleanup tasks in order once on process shutdown",
        "why": "Atomic coordinator: idempotent run-once, ordered tasks, error containment",
        "tags": ["devops", "shutdown", "graceful", "cleanup", "lifecycle"],
        "iface": r'''export class ShutdownCoordinator {
  onShutdown(task: () => Promise<void> | void): void
  shutdown(): Promise<void>
  get triggered(): boolean
}''',
        "code": r'''export class ShutdownCoordinator {
  private tasks: Array<() => Promise<void> | void> = [];
  private done = false;
  onShutdown(task: () => Promise<void> | void) { this.tasks.push(task); }
  async shutdown() {
    if (this.done) return;
    this.done = true;
    for (const t of this.tasks) { try { await t(); } catch { /* best effort */ } }
  }
  get triggered() { return this.done; }
}''',
        "provides": "ShutdownCoordinator",
        "depends": [],
    },
    {
        "id": "devops-ci-matrix",
        "name": "CI Matrix Expander",
        "category": "devops",
        "lang": "typescript",
        "when": "Expanding a CI job matrix into concrete (os, node, env) combinations",
        "why": "Atomic expander: dimension lists in, cartesian product out, overrides honored",
        "tags": ["devops", "ci", "matrix", "expand", "cartesian"],
        "iface": r'''export function expandMatrix(matrix: Record<string, string[]>): Array<Record<string, string>>''',
        "code": r'''export function expandMatrix(matrix: Record<string, string[]>) {
  const keys = Object.keys(matrix);
  if (!keys.length) return [{}];
  const out: Array<Record<string, string>> = [];
  const walk = (idx: number, acc: Record<string, string>) => {
    if (idx === keys.length) { out.push({ ...acc }); return; }
    for (const v of matrix[keys[idx]]) walk(idx + 1, { ...acc, [keys[idx]]: v });
  };
  walk(0, {});
  return out;
}''',
        "provides": "expandMatrix(matrix)",
        "depends": [],
    },
    {
        "id": "devops-log-rotate",
        "name": "Log Rotation Helper",
        "category": "devops",
        "lang": "typescript",
        "when": "Deciding when to rotate logs by size or age",
        "why": "Atomic policy: size/age thresholds in, rotate decision + new name out",
        "tags": ["devops", "log", "rotate", "size", "policy"],
        "iface": r'''export function shouldRotate(opts: { size: number; maxBytes: number; ageMs: number; maxAgeMs: number; rotatedAt?: number }): boolean''',
        "code": r'''export function shouldRotate(opts: { size: number; maxBytes: number; ageMs: number; maxAgeMs: number; rotatedAt?: number }) {
  if (opts.size >= opts.maxBytes) return true;
  const age = Date.now() - (opts.rotatedAt ?? Date.now());
  return age >= opts.maxAgeMs;
}''',
        "provides": "shouldRotate(opts)",
        "depends": [],
    },
    {
        "id": "devops-config-merge",
        "name": "Deep Config Merge",
        "category": "devops",
        "lang": "typescript",
        "when": "Merging layered config with defaults without clobbering nested objects",
        "why": "Atomic merger: recursive plain-object merge, arrays replaced, null resets",
        "tags": ["devops", "config", "merge", "defaults", "deep"],
        "iface": r'''export function deepMerge<T>(base: T, override: Partial<T>): T''',
        "code": r'''function isPlain(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}
export function deepMerge<T>(base: T, override: Partial<T>): T {
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const [k, v] of Object.entries(override ?? {})) {
    if (v === undefined) continue;
    out[k] = isPlain(v) && isPlain(out[k]) ? deepMerge(out[k], v) : v;
  }
  return out as T;
}''',
        "provides": "deepMerge(base, override)",
        "depends": [],
    },
    {
        "id": "devops-deadline-timer",
        "name": "Deadline Timer",
        "category": "devops",
        "lang": "typescript",
        "when": "Computing remaining time and expiry from a deadline",
        "why": "Atomic timer: deadline in, remaining/expired helpers out, no async state",
        "tags": ["devops", "deadline", "timer", "expiry", "timeout"],
        "iface": r'''export class Deadline {
  constructor(ms: number)
  get remainingMs(): number
  get expired(): boolean
  extend(ms: number): void
}''',
        "code": r'''export class Deadline {
  private at: number;
  constructor(ms: number) { this.at = Date.now() + ms; }
  get remainingMs() { return Math.max(0, this.at - Date.now()); }
  get expired() { return Date.now() >= this.at; }
  extend(ms: number) { this.at = Date.now() + ms; }
}''',
        "provides": "Deadline",
        "depends": [],
    },
    {
        "id": "devops-diff-summary",
        "name": "Diff Summary",
        "category": "devops",
        "lang": "typescript",
        "when": "Summarizing a text diff into add/del counts per file",
        "why": "Atomic summarizer: unified-diff text in, compact stats out",
        "tags": ["devops", "diff", "summary", "stats", "changes"],
        "iface": r'''export interface DiffStat { file: string; added: number; removed: number }
export function diffSummary(unifiedDiff: string): DiffStat[]''',
        "code": r'''export function diffSummary(unifiedDiff: string) {
  const stats: DiffStat[] = [];
  let cur: DiffStat | null = null;
  for (const line of unifiedDiff.split('\n')) {
    if (line.startsWith('+++ ')) {
      const file = line.slice(4).trim();
      cur = { file, added: 0, removed: 0 };
      stats.push(cur);
    } else if (cur) {
      if (line.startsWith('+')) cur.added++;
      else if (line.startsWith('-')) cur.removed++;
    }
  }
  return stats;
}''',
        "provides": "diffSummary(unifiedDiff)",
        "depends": [],
    },
    {
        "id": "devops-release-notes",
        "name": "Release Notes Generator",
        "category": "devops",
        "lang": "typescript",
        "when": "Grouping conventional-commit messages into a release notes section",
        "why": "Atomic generator: commits in, categorized bullets out, feat/fix/breaking only",
        "tags": ["devops", "release", "notes", "conventional", "commits"],
        "iface": r'''export function releaseNotes(commits: string[], version?: string): string''',
        "code": r'''export function releaseNotes(commits: string[], version?: string) {
  const cats: Array<[string, string, string[]]> = [
    ['Breaking changes', '!', []],
    ['Features', 'feat', []],
    ['Fixes', 'fix', []],
    ['Other', '', []],
  ];
  for (const c of commits) {
    const m = /^(feat|fix)(!)?: (.*)$/.exec(c.trim());
    if (!m) { cats[3][2].push(c.trim()); continue; }
    if (m[2]) cats[0][2].push(m[3]);
    else if (m[1] === 'feat') cats[1][2].push(m[3]);
    else cats[2][2].push(m[3]);
  }
  const lines = version ? [`## ${version}`, ''] : [];
  for (const [title, , items] of cats) {
    if (items.length) { lines.push(`### ${title}`, ...items.map((i) => `- ${i}`), ''); }
  }
  return lines.join('\n').trim();
}''',
        "provides": "releaseNotes(commits, version)",
        "depends": [],
    },
    {
        "id": "devops-pin-check",
        "name": "Dependency Pin Check",
        "category": "devops",
        "lang": "typescript",
        "when": "Verifying a package.json dependency uses an exact or compatible version",
        "why": "Atomic checker: spec in, {exact, compatible, range} classification out",
        "tags": ["devops", "dependency", "pin", "semver", "range"],
        "iface": r'''export type PinKind = 'exact' | 'caret' | 'tilde' | 'range' | 'wildcard' | 'invalid'
export function pinKind(spec: string): PinKind''',
        "code": r'''export function pinKind(spec: string): PinKind {
  const s = spec.trim();
  if (!s || !/^[\^~<>=0-9.*xX\s|-]+$/.test(s)) return 'invalid';
  if (/^\d+\.\d+\.\d+$/.test(s)) return 'exact';
  if (/^\^/.test(s)) return 'caret';
  if (/^~/.test(s)) return 'tilde';
  if (/^[<>=]/.test(s) || s.includes(' - ') || s.includes('||')) return 'range';
  if (/[*xX]/.test(s)) return 'wildcard';
  return 'invalid';
}''',
        "provides": "pinKind(spec)",
        "depends": [],
    },
    {
        "id": "devops-warmup-check",
        "name": "Startup Readiness Poller",
        "category": "devops",
        "lang": "typescript",
        "when": "Waiting for a service's prerequisite flags before declaring it ready",
        "why": "Atomic readiness gate: required conditions in, once-all-true signal out",
        "tags": ["devops", "startup", "readiness", "poll", "warmup"],
        "iface": r'''export class ReadinessGate {
  constructor(check: () => boolean, pollMs?: number)
  wait(timeoutMs?: number): Promise<boolean>
}''',
        "code": r'''export class ReadinessGate {
  constructor(private check: () => boolean, private pollMs = 200) {}
  wait(timeoutMs = 30000) {
    return new Promise<boolean>((resolve) => {
      const start = Date.now();
      const tick = () => {
        if (this.check()) return resolve(true);
        if (Date.now() - start >= timeoutMs) return resolve(false);
        setTimeout(tick, this.pollMs);
      };
      tick();
    });
  }
}''',
        "provides": "ReadinessGate",
        "depends": [],
    },
    {
        "id": "devops-config-validate",
        "name": "Required Config Validator",
        "category": "devops",
        "lang": "typescript",
        "when": "Failing fast when a config object misses required keys",
        "why": "Atomic validator: keys in, missing list out — no throw, caller decides",
        "tags": ["devops", "config", "validate", "required", "env"],
        "iface": r'''export function missingKeys(config: Record<string, unknown>, required: string[]): string[]''',
        "code": r'''export function missingKeys(config: Record<string, unknown>, required: string[]) {
  return required.filter((k) => config[k] === undefined || config[k] === null || config[k] === '');
}''',
        "provides": "missingKeys(config, required)",
        "depends": [],
    },
    {
        "id": "devops-archive-keep",
        "name": "Retention Policy (keep newest N)",
        "category": "devops",
        "lang": "typescript",
        "when": "Deciding which old artifacts to delete to respect a keep-count policy",
        "why": "Atomic retention: sorted items + keep N in, deletion candidates out",
        "tags": ["devops", "retention", "archive", "prune", "keep"],
        "iface": r'''export function pruneCandidates<T>(items: Array<{ id: string; ts: number }>, keep: number): string[]''',
        "code": r'''export function pruneCandidates<T>(items: Array<{ id: string; ts: number }>, keep: number) {
  return items.sort((a, b) => b.ts - a.ts).slice(keep).map((i) => i.id);
}''',
        "provides": "pruneCandidates(items, keep)",
        "depends": [],
    },
    {
        "id": "devops-http-cache",
        "name": "Cache-Control Builder",
        "category": "devops",
        "lang": "typescript",
        "when": "Setting correct HTTP caching headers for static and dynamic resources",
        "why": "Atomic builder: TTLs in, cache-control string out, no framework coupling",
        "tags": ["devops", "cache", "http", "cache-control", "headers"],
        "iface": r'''export interface CachePolicy { maxAgeSec: number; staleWhileRevalidateSec?: number; immutable?: boolean; noStore?: boolean; private?: boolean }
export function cacheControl(policy: CachePolicy): string''',
        "code": r'''export function cacheControl(policy: CachePolicy) {
  if (policy.noStore) return 'no-store';
  const parts = [`max-age=${policy.maxAgeSec}`];
  if (policy.immutable) parts.push('immutable');
  if (policy.private) parts.unshift('private');
  else parts.unshift('public');
  if (policy.staleWhileRevalidateSec !== undefined) parts.push(`stale-while-revalidate=${policy.staleWhileRevalidateSec}`);
  return parts.join(', ');
}''',
        "provides": "cacheControl(policy)",
        "depends": [],
    },
]
