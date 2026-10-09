# -*- coding: utf-8 -*-
"""
Code Bible — Category 10: System & process (atomic).
Convention: managers expose start/stop/status; helpers are pure or single-IO.
"""
CHUNKS = [
    {
        "id": "sys-process-spawn",
        "name": "Process Spawn Helper",
        "category": "sys",
        "lang": "typescript",
        "when": "Running child processes with captured output and timeouts",
        "why": "Atomic spawner; command + args in, {code, stdout, stderr} out — timeout + kill included",
        "tags": ["process", "spawn", "child", "exec", "shell"],
        "iface": r'''export interface SpawnResult { code: number | null; stdout: string; stderr: string }
export function runProcess(
  command: string,
  args?: string[],
  options?: { cwd?: string; timeoutMs?: number; env?: Record<string, string> },
): Promise<SpawnResult>''',
        "code": r'''import { spawn } from 'child_process';

export function runProcess(command: string, args: string[] = [], options?: {
  cwd?: string; timeoutMs?: number; env?: Record<string, string>;
}): Promise<SpawnResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options?.cwd,
      env: { ...process.env, ...options?.env },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d: Buffer) => { stdout += d.toString(); });
    child.stderr.on('data', (d: Buffer) => { stderr += d.toString(); });

    const timer = options?.timeoutMs
      ? setTimeout(() => child.kill('SIGKILL'), options.timeoutMs)
      : undefined;

    child.on('error', (err) => { if (timer) clearTimeout(timer); reject(err); });
    child.on('close', (code) => {
      if (timer) clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });
  });
}''',
        "provides": "runProcess(command, args?, options?)",
        "depends": [],
    },
    {
        "id": "sys-file-watcher",
        "name": "File Watcher",
        "category": "sys",
        "lang": "typescript",
        "when": "Reacting to file changes (hot reload, builds, syncing)",
        "why": "Atomic watcher; dir + events in, start/stop out — debounced change notifications",
        "tags": ["file", "watch", "fs", "reload", "debounce"],
        "iface": r'''export function watchDirectory(
  dir: string,
  onEvent: (type: 'add' | 'change' | 'unlink', path: string) => void,
  options?: { recursive?: boolean; debounceMs?: number; filter?: (p: string) => boolean },
): { start(): void; stop(): void; get watching(): boolean }''',
        "code": r'''import * as fs from 'fs';

export function watchDirectory(dir: string, onEvent: (type: 'add' | 'change' | 'unlink', path: string) => void, options?: {
  recursive?: boolean; debounceMs?: number; filter?: (p: string) => boolean;
}) {
  let watcher: fs.FSWatcher | null = null;
  const pending = new Map<string, ReturnType<typeof setTimeout>>();
  const debounceMs = options?.debounceMs ?? 100;

  function emit(type: 'add' | 'change' | 'unlink', path: string) {
    if (options?.filter && !options.filter(path)) return;
    const key = type + ':' + path;
    const existing = pending.get(key);
    if (existing) clearTimeout(existing);
    pending.set(key, setTimeout(() => { pending.delete(key); onEvent(type, path); }, debounceMs));
  }

  return {
    start() {
      if (watcher) return;
      watcher = fs.watch(dir, { recursive: options?.recursive ?? true }, (eventType, filename) => {
        if (!filename) return;
        const full = require('path').join(dir, filename.toString());
        emit(eventType as 'add' | 'change' | 'unlink', full);
      });
    },
    stop() {
      watcher?.close();
      watcher = null;
      for (const t of pending.values()) clearTimeout(t);
      pending.clear();
    },
    get watching() { return watcher !== null; },
  };
}''',
        "provides": "watchDirectory(dir, onEvent, options?)",
        "depends": [],
    },
    {
        "id": "sys-dir-walker",
        "name": "Directory Walker",
        "category": "sys",
        "lang": "typescript",
        "when": "Recursively listing files (indexing, builds, backups)",
        "why": "Atomic walker; root in, file list out — extension/skip filters, no side effects",
        "tags": ["directory", "walk", "recursive", "files", "scan"],
        "iface": r'''export interface WalkOptions { extensions?: string[]; skipDirs?: string[]; maxDepth?: number }
export async function walkDirectory(root: string, options?: WalkOptions): Promise<string[]>''',
        "code": r'''import * as fs from 'fs/promises';
import * as path from 'path';

export async function walkDirectory(root: string, options: WalkOptions = {}): Promise<string[]> {
  const out: string[] = [];

  async function walk(dir: string, depth: number) {
    if (options.maxDepth !== undefined && depth > options.maxDepth) return;
    let entries;
    try { entries = await fs.readdir(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (options.skipDirs?.includes(entry.name)) continue;
        await walk(full, depth + 1);
      } else if (entry.isFile()) {
        if (options.extensions && !options.extensions.some((e) => full.endsWith(e))) continue;
        out.push(full);
      }
    }
  }

  await walk(root, 0);
  return out;
}''',
        "provides": "walkDirectory(root, options?)",
        "depends": [],
    },
    {
        "id": "sys-config-loader",
        "name": "Config File Loader",
        "category": "sys",
        "lang": "typescript",
        "when": "Loading app config from JSON/JS files with schema validation",
        "why": "Atomic loader; path + defaults in, merged config out — missing file falls back to defaults",
        "tags": ["config", "loader", "json", "defaults", "settings"],
        "iface": r'''export async function loadConfigFile<T extends Record<string, unknown>>(
  filePath: string,
  defaults: T,
  validate?: (c: T) => string | null,
): Promise<T>''',
        "code": r'''import * as fs from 'fs/promises';

export async function loadConfigFile<T extends Record<string, unknown>>(
  filePath: string,
  defaults: T,
  validate?: (c: T) => string | null,
): Promise<T> {
  let fileConfig: Partial<T> = {};
  try {
    const raw = await fs.readFile(filePath, 'utf-8');
    fileConfig = JSON.parse(raw) as Partial<T>;
  } catch {
    // Missing or invalid file — use defaults.
  }
  const merged = { ...defaults, ...fileConfig };
  const error = validate?.(merged);
  if (error) throw new Error(`config_invalid: ${error}`);
  return merged;
}''',
        "provides": "loadConfigFile<T>(filePath, defaults, validate?)",
        "depends": [],
    },
    {
        "id": "sys-logger",
        "name": "Structured Logger",
        "category": "sys",
        "lang": "typescript",
        "when": "Logging with levels, timestamps, and JSON output",
        "why": "Atomic logger; scope in, info/warn/error out — single line JSON, level filtering",
        "tags": ["log", "logger", "structured", "json", "levels"],
        "iface": r'''export interface Logger {
  info(msg: string, meta?: Record<string, unknown>): void;
  warn(msg: string, meta?: Record<string, unknown>): void;
  error(msg: string, meta?: Record<string, unknown>): void;
  debug(msg: string, meta?: Record<string, unknown>): void;
  child(scope: string): Logger;
}
export function createLogger(scope: string, options?: { level?: 'debug' | 'info' | 'warn' | 'error'; sink?: (line: string) => void }): Logger''',
        "code": r'''const LEVELS = { debug: 0, info: 1, warn: 2, error: 3 } as const;

export function createLogger(scope: string, options?: {
  level?: keyof typeof LEVELS;
  sink?: (line: string) => void;
}): Logger {
  const min = LEVELS[options?.level ?? 'info'];
  const sink = options?.sink ?? ((line: string) => console.log(line));

  function emit(level: keyof typeof LEVELS, msg: string, meta?: Record<string, unknown>) {
    if (LEVELS[level] < min) return;
    const entry = { ts: new Date().toISOString(), level, scope, msg, ...meta };
    sink(JSON.stringify(entry));
  }

  return {
    info: (m, meta) => emit('info', m, meta),
    warn: (m, meta) => emit('warn', m, meta),
    error: (m, meta) => emit('error', m, meta),
    debug: (m, meta) => emit('debug', m, meta),
    child: (sub) => createLogger(`${scope}:${sub}`, options),
  };
}''',
        "provides": "createLogger(scope, options?)",
        "depends": [],
    },
    {
        "id": "sys-signal-handler",
        "name": "Graceful Shutdown",
        "category": "sys",
        "lang": "typescript",
        "when": "Cleaning up resources before the process exits",
        "why": "Atomic shutdown manager; cleanup fns in, handler out — SIGINT/SIGTERM + forced exit",
        "tags": ["signal", "shutdown", "graceful", "sigint", "sigterm"],
        "iface": r'''export function registerGracefulShutdown(
  cleanup: () => Promise<void> | void,
  options?: { timeoutMs?: number; onSignal?: (signal: string) => void },
): { shutdown(signal: string): Promise<void>; unregister(): void }''',
        "code": r'''export function registerGracefulShutdown(
  cleanup: () => Promise<void> | void,
  options?: { timeoutMs?: number; onSignal?: (signal: string) => void },
) {
  let shuttingDown = false;

  async function shutdown(signal: string) {
    if (shuttingDown) return;
    shuttingDown = true;
    options?.onSignal?.(signal);
    const force = setTimeout(() => {
      console.error(`[shutdown] forced exit after ${options?.timeoutMs ?? 10_000}ms`);
      process.exit(1);
    }, options?.timeoutMs ?? 10_000);
    force.unref();
    try { await cleanup(); } finally { clearTimeout(force); process.exit(0); }
  }

  const onSigint = () => void shutdown('SIGINT');
  const onSigterm = () => void shutdown('SIGTERM');
  process.on('SIGINT', onSigint);
  process.on('SIGTERM', onSigterm);

  return {
    shutdown,
    unregister() {
      process.removeListener('SIGINT', onSigint);
      process.removeListener('SIGTERM', onSigterm);
    },
  };
}''',
        "provides": "registerGracefulShutdown(cleanup, options?)",
        "depends": [],
    },
    {
        "id": "sys-daemonize",
        "name": "Daemonize Helper",
        "category": "sys",
        "lang": "typescript",
        "when": "Forking a long-running background process with pidfile management",
        "why": "Atomic daemon helper; pidfile + log path in, spawn/detach out — double-fork pattern",
        "tags": ["daemon", "background", "pidfile", "fork", "service"],
        "iface": r'''export async function daemonize(options?: { pidFile?: string; logFile?: string; cwd?: string }): Promise<void>''',
        "code": r'''import * as fs from 'fs';
import * as path from 'path';

export async function daemonize(options?: { pidFile?: string; logFile?: string; cwd?: string }): Promise<void> {
  // Fork the current process detached so it survives the parent's exit.
  const { spawn } = await import('child_process');
  const args = process.argv.slice(2);
  const child = spawn(process.execPath, [process.argv[1], ...args], {
    detached: true,
    stdio: options?.logFile
      ? ['ignore', fs.openSync(options.logFile, 'a'), fs.openSync(options.logFile, 'a')]
      : 'ignore',
    cwd: options?.cwd,
    env: process.env,
  });
  child.unref();

  if (options?.pidFile) {
    await fs.promises.mkdir(path.dirname(options.pidFile), { recursive: true });
    await fs.promises.writeFile(options.pidFile, String(child.pid));
  }
}''',
        "provides": "daemonize(options?)",
        "depends": [],
    },
    {
        "id": "sys-cron-scheduler",
        "name": "Cron Scheduler",
        "category": "sys",
        "lang": "typescript",
        "when": "Running jobs on a schedule (backups, cleanups, reports)",
        "why": "Atomic scheduler; cron string + job in, start/stop out — 5-field cron, next-run preview",
        "tags": ["cron", "schedule", "job", "timer", "recurring"],
        "iface": r'''export interface CronJob { schedule: string; run: () => void | Promise<void> }
export function createCronScheduler() {
  return {
    add(id: string, schedule: string, run: () => void | Promise<void>): void,
    remove(id: string): void,
    start(): void,
    stop(): void,
    nextRun(id: string): Date | null,
  };
}''',
        "code": r'''export function createCronScheduler() {
  const jobs = new Map<string, { schedule: string; run: () => void | Promise<void>; timer: ReturnType<typeof setTimeout> | null }>();
  let started = false;

  // Simple 5-field matcher: "min hour dom mon dow" with * and comma lists.
  function matches(schedule: string, date: Date): boolean {
    const [min, hour, dom, mon, dow] = schedule.trim().split(/\s+/);
    const match = (field: string | undefined, v: number) => {
      if (!field || field === '*') return true;
      return field.split(',').some((p) => {
        if (p.includes('/')) { const [, step] = p.split('/'); return v % Number(step) === 0; }
        if (p.includes('-')) { const [a, b] = p.split('-'); return v >= Number(a) && v <= Number(b); }
        return Number(p) === v;
      });
    };
    return match(min, date.getMinutes()) && match(hour, date.getHours()) &&
      match(dom, date.getDate()) && match(mon, date.getMonth() + 1) &&
      match(dow, date.getDay());
  }

  function schedule(job: { schedule: string; run: () => void | Promise<void>; timer: null }) {
    const now = new Date();
    // Check every 30s; cheap and accurate to the minute.
    job.timer = setTimeout(() => {
      const d = new Date();
      if (matches(job.schedule, d)) void job.run();
      schedule(job);
    }, 30_000 - (now.getSeconds() * 1000 + now.getMilliseconds()));
  }

  return {
    add(id, schedule, run) {
      this.remove(id);
      const job = { schedule, run, timer: null };
      jobs.set(id, job);
      if (started) schedule(job);
    },
    remove(id) {
      const job = jobs.get(id);
      if (job?.timer) clearTimeout(job.timer);
      jobs.delete(id);
    },
    start() {
      started = true;
      for (const job of jobs.values()) schedule(job);
    },
    stop() {
      started = false;
      for (const job of jobs.values()) if (job.timer) clearTimeout(job.timer);
    },
    nextRun(id) {
      const job = jobs.get(id);
      if (!job) return null;
      const d = new Date();
      for (let i = 0; i < 60 * 24 * 60; i++) {
        d.setSeconds(0);
        if (matches(job.schedule, d)) return new Date(d);
        d.setMinutes(d.getMinutes() + 1);
      }
      return null;
    },
  };
}''',
        "provides": "createCronScheduler()",
        "depends": [],
    },
    {
        "id": "sys-job-queue",
        "name": "Persistent Job Queue",
        "category": "sys",
        "lang": "typescript",
        "when": "Enqueueing work with retries and persistence across restarts",
        "why": "Atomic queue; worker + storage in, enqueue/status out — retries, backoff, persistence",
        "tags": ["queue", "job", "worker", "retry", "persist"],
        "iface": r'''export interface QueuedJob<T = unknown> { id: string; payload: T; attempts: number; status: 'queued' | 'running' | 'done' | 'failed'; error?: string }
export function createJobQueue<T = unknown>(
  worker: (payload: T) => Promise<void>,
  storage?: StorageAdapter<QueuedJob<T>[]>,
  options?: { maxAttempts?: number },
) {
  return {
    enqueue(payload: T): string,
    get size(): number,
    start(): void,
    stop(): void,
    statusOf(id: string): QueuedJob<T> | undefined,
  };
}''',
        "code": r'''export function createJobQueue<T = unknown>(
  worker: (payload: T) => Promise<void>,
  storage?: StorageAdapter<QueuedJob<T>[]>,
  options?: { maxAttempts?: number },
) {
  const maxAttempts = options?.maxAttempts ?? 3;
  const jobs = new Map<string, QueuedJob<T>>();
  const order: string[] = [];
  let running = false;
  let started = false;

  if (storage) {
    const saved = storage.load() ?? [];
    for (const j of saved) if (j.status === 'queued' || j.status === 'failed') { jobs.set(j.id, { ...j, status: 'queued' }); order.push(j.id); }
  }

  function persist() {
    storage?.save([...jobs.values()]);
  }

  async function pump() {
    if (running || !started) return;
    running = true;
    while (order.length > 0 && started) {
      const id = order.shift()!;
      const job = jobs.get(id);
      if (!job || job.status === 'done') continue;
      job.status = 'running';
      persist();
      try {
        await worker(job.payload);
        job.status = 'done';
      } catch (e) {
        job.attempts++;
        job.error = (e as Error).message;
        if (job.attempts >= maxAttempts) job.status = 'failed';
        else { job.status = 'queued'; order.push(id); }
      }
      persist();
    }
    running = false;
  }

  return {
    enqueue(payload) {
      const id = crypto.randomUUID();
      jobs.set(id, { id, payload, attempts: 0, status: 'queued' });
      order.push(id);
      persist();
      void pump();
      return id;
    },
    get size() { return order.length; },
    start() { started = true; void pump(); },
    stop() { started = false; },
    statusOf(id) { return jobs.get(id); },
  };
}''',
        "provides": "createJobQueue<T>(worker, storage?, options?)",
        "depends": ["state-local-storage"],
    },
    {
        "id": "sys-memory-meter",
        "name": "Memory/CPU Meter",
        "category": "sys",
        "lang": "typescript",
        "when": "Sampling process resource usage for dashboards and monitoring",
        "why": "Atomic sampler; interval in, snapshot fn out — rss/heap/cpu%, no storage",
        "tags": ["memory", "cpu", "meter", "monitor", "rss"],
        "iface": r'''export function createResourceMeter(intervalMs?: number) {
  return {
    start(): void,
    stop(): void,
    sample(): { rssMB: number; heapMB: number; cpuPct: number; uptimeSec: number },
    onSample(cb: (s: { rssMB: number; heapMB: number; cpuPct: number; uptimeSec: number }) => void): () => void,
  };
}''',
        "code": r'''export function createResourceMeter(intervalMs = 2000) {
  let timer: ReturnType<typeof setInterval> | undefined;
  let lastCpu = process.cpuUsage();
  let lastTime = Date.now();
  const listeners = new Set<(s: { rssMB: number; heapMB: number; cpuPct: number; uptimeSec: number }) => void>();

  function sample() {
    const now = Date.now();
    const cpu = process.cpuUsage();
    const elapsed = (now - lastTime) / 1000;
    const cpuDelta = (cpu.user - lastCpu.user + cpu.system - lastCpu.system) / 1000;  // µs -> ms
    lastCpu = cpu;
    lastTime = now;
    const mem = process.memoryUsage();
    return {
      rssMB: Math.round(mem.rss / 1024 / 1024),
      heapMB: Math.round(mem.heapUsed / 1024 / 1024),
      cpuPct: elapsed > 0 ? Math.round(cpuDelta / elapsed / 10) : 0,
      uptimeSec: Math.round(process.uptime()),
    };
  }

  return {
    start() {
      if (timer) return;
      timer = setInterval(() => {
        const s = sample();
        listeners.forEach((cb) => cb(s));
      }, intervalMs);
    },
    stop() { if (timer) clearInterval(timer); timer = undefined; },
    sample,
    onSample(cb) { listeners.add(cb); return () => listeners.delete(cb); },
  };
}''',
        "provides": "createResourceMeter(intervalMs?)",
        "depends": [],
    },
    {
        "id": "sys-lock-file",
        "name": "Lock File",
        "category": "sys",
        "lang": "typescript",
        "when": "Preventing two processes from running the same task concurrently",
        "why": "Atomic lock; path in, acquire/release out — stale-lock detection via pid",
        "tags": ["lock", "mutex", "file", "exclusive", "concurrency"],
        "iface": r'''export function createLockFile(lockPath: string) {
  return {
    async acquire(staleMs?: number): Promise<boolean>,
    async release(): Promise<void>,
    async isLocked(): Promise<boolean>,
  };
}''',
        "code": r'''import * as fs from 'fs/promises';

export function createLockFile(lockPath: string) {
  return {
    async acquire(staleMs = 60_000): Promise<boolean> {
      try {
        const fd = await fs.open(lockPath, 'wx');
        await fd.writeFile(JSON.stringify({ pid: process.pid, at: Date.now() }));
        await fd.close();
        return true;
      } catch {
        // Lock exists — check staleness.
        try {
          const raw = await fs.readFile(lockPath, 'utf-8');
          const meta = JSON.parse(raw) as { pid: number; at: number };
          if (Date.now() - meta.at > staleMs) {
            await fs.unlink(lockPath).catch(() => {});
            return this.acquire(staleMs);
          }
        } catch { /* unreadable — treat as stale */ }
        return false;
      }
    },
    async release() {
      await fs.unlink(lockPath).catch(() => {});
    },
    async isLocked() {
      try { await fs.access(lockPath); return true; } catch { return false; }
    },
  };
}''',
        "provides": "createLockFile(lockPath)",
        "depends": [],
    },
    {
        "id": "sys-temp-dir",
        "name": "Temp Dir Manager",
        "category": "sys",
        "lang": "typescript",
        "when": "Creating scoped temp directories that self-clean",
        "why": "Atomic temp manager; prefix in, create/remove out — cleanup on process exit",
        "tags": ["temp", "tmp", "directory", "cleanup", "filesystem"],
        "iface": r'''export function createTempManager(prefix?: string) {
  return {
    async createDir(): Promise<string>,
    async createFile(name: string, contents?: string): Promise<string>,
    async cleanup(): Promise<void>,
  };
}''',
        "code": r'''import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';

export function createTempManager(prefix = 'app-') {
  const root = fs.mkdtemp(path.join(os.tmpdir(), prefix));
  let cleaned = false;

  async function ensureRoot() {
    const r = await root;
    if (cleaned) throw new Error('temp manager cleaned');
    return r;
  }

  process.once('exit', () => { void fs.rm(path.join(os.tmpdir(), prefix), { recursive: true, force: true }).catch(() => {}); });

  return {
    async createDir() {
      const r = await ensureRoot();
      return fs.mkdir(path.join(r, `d${Date.now()}-${Math.random().toString(36).slice(2)}`), { recursive: true });
    },
    async createFile(name, contents = '') {
      const r = await ensureRoot();
      const safe = path.basename(name);
      const full = path.join(r, safe);
      await fs.writeFile(full, contents);
      return full;
    },
    async cleanup() {
      const r = await root;
      await fs.rm(r, { recursive: true, force: true });
      cleaned = true;
    },
  };
}''',
        "provides": "createTempManager(prefix?)",
        "depends": [],
    },
    {
        "id": "sys-atomic-write",
        "name": "Atomic File Write",
        "category": "sys",
        "lang": "typescript",
        "when": "Writing files without corruption risk on crash",
        "why": "Atomic writer; path + data in, promise out — temp + rename, fsync included",
        "tags": ["atomic", "write", "file", "fsync", "safe"],
        "iface": r'''export async function atomicWriteFile(filePath: string, data: string | Uint8Array): Promise<void>''',
        "code": r'''import * as fs from 'fs/promises';
import * as path from 'path';

export async function atomicWriteFile(filePath: string, data: string | Uint8Array): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  const tmp = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  const fh = await fs.open(tmp, 'w');
  try {
    await fh.writeFile(data);
    await fh.sync();            // flush to disk before rename
  } finally {
    await fh.close();
  }
  await fs.rename(tmp, filePath);
}''',
        "provides": "atomicWriteFile(filePath, data)",
        "depends": [],
    },
]
