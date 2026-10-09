# -*- coding: utf-8 -*-
"""
Code Bible — Category 24: Architecture & Design Patterns (atomic).
Convention: one pattern per chunk, TypeScript, dependency-free.
"""
CHUNKS = [
    {
        "id": "arch-layered",
        "name": "Layered Architecture",
        "category": "arch",
        "lang": "typescript",
        "when": "Separating a module into presentation / domain / data layers with one-way deps",
        "why": "Atomic layer boundary — domain never imports presentation, keeping dependencies acyclic",
        "tags": ["arch", "layers", "boundary", "dependency", "structure"],
        "iface": r'''export type Layer = 'presentation' | 'domain' | 'data'
export function isLegalDependency(from: Layer, to: Layer): boolean''',
        "code": r'''export function isLegalDependency(from: Layer, to: Layer) {
  const rank: Record<Layer, number> = { presentation: 2, domain: 1, data: 0 };
  return rank[to] <= rank[from];
}''',
        "provides": "isLegalDependency(from, to)",
        "depends": [],
    },
    {
        "id": "arch-hexagonal",
        "name": "Hexagonal (Ports & Adapters)",
        "category": "arch",
        "lang": "typescript",
        "when": "Wiring a domain core to IO through interfaces so adapters can be swapped",
        "why": "Atomic port contract + adapter registration — core depends on abstractions, never implementations",
        "tags": ["arch", "hexagonal", "ports", "adapters", "di"],
        "iface": r'''export interface Port<Req, Res> { execute(req: Req): Promise<Res> }
export class PortRegistry {
  register<K extends string, Req, Res>(name: K, impl: Port<Req, Res>): void
  get<K extends string, Req, Res>(name: K): Port<Req, Res>
}''',
        "code": r'''export class PortRegistry {
  private impls = new Map<string, Port<unknown, unknown>>();
  register<K extends string>(name: K, impl: Port<unknown, unknown>) { this.impls.set(name, impl); }
  get<K extends string>(name: K) {
    const impl = this.impls.get(name);
    if (!impl) throw new Error(`No adapter bound for port "${name}"`);
    return impl;
  }
}''',
        "provides": "PortRegistry",
        "depends": [],
    },
    {
        "id": "arch-cqrs",
        "name": "CQRS Split",
        "category": "arch",
        "lang": "typescript",
        "when": "Separating the write model from the read model so each is tuned independently",
        "why": "Atomic command/query splitter — distinct handlers, optional separate stores",
        "tags": ["arch", "cqrs", "command", "query", "write-model"],
        "iface": r'''export interface Command { type: string; payload: unknown }
export interface Query { type: string; params: unknown }
export class CqrsBus {
  onCommand(type: string, h: (c: Command) => void): void
  onQuery<T>(type: string, h: (q: Query) => T): void
  dispatch(c: Command): void
  ask<T>(q: Query): T
}''',
        "code": r'''export class CqrsBus {
  private commands = new Map<string, (c: Command) => void>();
  private queries = new Map<string, (q: Query) => unknown>();
  onCommand(type: string, h: (c: Command) => void) { this.commands.set(type, h); }
  onQuery<T>(type: string, h: (q: Query) => T) { this.queries.set(type, h); }
  dispatch(c: Command) {
    const h = this.commands.get(c.type);
    if (!h) throw new Error(`No command handler: ${c.type}`);
    h(c);
  }
  ask<T>(q: Query): T {
    const h = this.queries.get(q.type);
    if (!h) throw new Error(`No query handler: ${q.type}`);
    return h(q) as T;
  }
}''',
        "provides": "CqrsBus",
        "depends": [],
    },
    {
        "id": "arch-event-sourcing",
        "name": "Event Sourcing Store",
        "category": "arch",
        "lang": "typescript",
        "when": "Rebuilding state from an append-only event log instead of storing current state",
        "why": "Atomic event stream + fold — replay any time, audit trail for free",
        "tags": ["arch", "event-sourcing", "events", "replay", "fold"],
        "iface": r'''export class EventStore<S, E> {
  append(e: E): void
  fold(initial: S, apply: (s: S, e: E) => S): S
  get all(): E[]
}''',
        "code": r'''export class EventStore<S, E> {
  private events: E[] = [];
  append(e: E) { this.events.push(e); }
  fold(initial: S, apply: (s: S, e: E) => S) { return this.events.reduce(apply, initial); }
  get all() { return this.events.slice(); }
}''',
        "provides": "EventStore",
        "depends": [],
    },
    {
        "id": "arch-saga",
        "name": "Saga Coordinator",
        "category": "arch",
        "lang": "typescript",
        "when": "Orchestrating a multi-step transaction with compensating rollbacks",
        "why": "Atomic saga runner — each step maps to a compensate fn, failures unwind in reverse",
        "tags": ["arch", "saga", "transaction", "compensation", "orchestration"],
        "iface": r'''export interface SagaStep<T> { name: string; run: () => Promise<T>; compensate: () => Promise<void> }
export async function runSaga<T>(steps: Array<SagaStep<T>>): Promise<T[]>''',
        "code": r'''export async function runSaga<T>(steps: Array<SagaStep<T>>) {
  const done: Array<SagaStep<T>> = [];
  try {
    for (const s of steps) { await s.run(); done.push(s); }
    return done;
  } catch (err) {
    for (const s of done.reverse()) { try { await s.compensate(); } catch { /* best-effort */ } }
    throw err;
  }
}''',
        "provides": "runSaga(steps)",
        "depends": [],
    },
    {
        "id": "arch-circuit-breaker",
        "name": "Circuit Breaker",
        "category": "arch",
        "lang": "typescript",
        "when": "Short-circuiting a failing dependency so it cannot cascade into the caller",
        "why": "Atomic 3-state breaker (closed/open/half-open) with failure thresholds and cooldown",
        "tags": ["arch", "circuit-breaker", "resilience", "failure"],
        "iface": r'''export class CircuitBreaker {
  constructor(opts?: { threshold?: number; cooldownMs?: number })
  async call<T>(fn: () => Promise<T>): Promise<T>
  get state(): 'closed' | 'open' | 'half-open'
}''',
        "code": r'''export class CircuitBreaker {
  private threshold: number; private cooldownMs: number;
  private failures = 0; private openedAt = 0; private state_: 'closed' | 'open' | 'half-open' = 'closed';
  constructor(opts: { threshold?: number; cooldownMs?: number } = {}) {
    this.threshold = opts.threshold ?? 5;
    this.cooldownMs = opts.cooldownMs ?? 30_000;
  }
  get state() { return this.state_; }
  async call<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state_ === 'open' && Date.now() - this.openedAt >= this.cooldownMs) this.state_ = 'half-open';
    if (this.state_ === 'open') throw new Error('Circuit open');
    try {
      const r = await fn();
      this.failures = 0; this.state_ = 'closed';
      return r;
    } catch (err) {
      this.failures++;
      if (this.failures >= this.threshold || this.state_ === 'half-open') {
        this.state_ = 'open'; this.openedAt = Date.now();
      }
      throw err;
    }
  }
}''',
        "provides": "CircuitBreaker",
        "depends": [],
    },
    {
        "id": "arch-bulkhead",
        "name": "Bulkhead Pool",
        "category": "arch",
        "lang": "typescript",
        "when": "Isolating failure domains with separate bounded concurrency pools",
        "why": "Atomic per-key semaphore — one slow dependency cannot exhaust shared workers",
        "tags": ["arch", "bulkhead", "isolation", "semaphore", "concurrency"],
        "iface": r'''export class Bulkhead {
  constructor(limit: number)
  async run<T>(domain: string, fn: () => Promise<T>): Promise<T>
}''',
        "code": r'''export class Bulkhead {
  private pools = new Map<string, number>();
  private waiters = new Map<string, Array<() => void>>();
  constructor(private limit: number) {}
  async run<T>(domain: string, fn: () => Promise<T>): Promise<T> {
    const used = this.pools.get(domain) ?? 0;
    if (used >= this.limit) {
      await new Promise<void>((res) => {
        if (!this.waiters.has(domain)) this.waiters.set(domain, []);
        this.waiters.get(domain)!.push(res);
      });
    }
    this.pools.set(domain, (this.pools.get(domain) ?? 0) + 1);
    try { return await fn(); }
    finally {
      this.pools.set(domain, (this.pools.get(domain) ?? 1) - 1);
      const q = this.waiters.get(domain);
      if (q && q.length) q.shift()!();
    }
  }
}''',
        "provides": "Bulkhead",
        "depends": [],
    },
    {
        "id": "arch-backpressure",
        "name": "Backpressure Valve",
        "category": "arch",
        "lang": "typescript",
        "when": "Pausing a producer when a consumer is slower than it",
        "why": "Atomic bounded queue with producer blocking — prevents unbounded memory growth",
        "tags": ["arch", "backpressure", "queue", "bounded", "flow-control"],
        "iface": r'''export class BackpressureQueue<T> {
  constructor(capacity: number)
  push(item: T): Promise<void>
  shift(): Promise<T>
}''',
        "code": r'''export class BackpressureQueue<T> {
  private items: T[] = [];
  private notFull: Array<() => void> = [];
  private notEmpty: Array<(v: T) => void> = [];
  constructor(private capacity: number) {}
  async push(item: T) {
    while (this.items.length >= this.capacity) await new Promise<void>((r) => this.notFull.push(r));
    this.items.push(item);
    this.notEmpty.splice(0).forEach((r) => r(this.items.shift()!));
  }
  async shift() {
    while (this.items.length === 0) await new Promise<T>((r) => this.notEmpty.push(r));
    this.notFull.splice(0).forEach((r) => r());
    return this.items.shift()!;
  }
}''',
        "provides": "BackpressureQueue",
        "depends": [],
    },
    {
        "id": "arch-factory",
        "name": "Factory",
        "category": "arch",
        "lang": "typescript",
        "when": "Creating objects by type key so callers never touch concrete constructors",
        "why": "Atomic registry factory — register builders, create by string key, typed output",
        "tags": ["arch", "factory", "creation", "registry"],
        "iface": r'''export class Factory<K extends string, T> {
  register(key: K, build: () => T): void
  create(key: K): T
}''',
        "code": r'''export class Factory<K extends string, T> {
  private builders = new Map<K, () => T>();
  register(key: K, build: () => T) { this.builders.set(key, build); }
  create(key: K) {
    const b = this.builders.get(key);
    if (!b) throw new Error(`Unknown factory key: ${key}`);
    return b();
  }
}''',
        "provides": "Factory",
        "depends": [],
    },
    {
        "id": "arch-builder",
        "name": "Builder",
        "category": "arch",
        "lang": "typescript",
        "when": "Constructing complex objects step-by-step with a fluent API",
        "why": "Atomic fluent builder — optional fields with validation on build()",
        "tags": ["arch", "builder", "fluent", "immutable", "construction"],
        "iface": r'''export class ConfigBuilder<T extends object> {
  set<K extends keyof T>(key: K, value: T[K]): this
  build(): T
}''',
        "code": r'''export class ConfigBuilder<T extends object> {
  private state: Partial<T> = {};
  set<K extends keyof T>(key: K, value: T[K]) { this.state[key] = value; return this; }
  build() {
    const missing = Object.entries(this.state).filter(([, v]) => v === undefined).map(([k]) => k);
    if (missing.length) throw new Error(`Missing required fields: ${missing.join(', ')}`);
    return { ...this.state } as T;
  }
}''',
        "provides": "ConfigBuilder",
        "depends": [],
    },
    {
        "id": "arch-strategy",
        "name": "Strategy Selector",
        "category": "arch",
        "lang": "typescript",
        "when": "Swapping an algorithm at runtime behind one interface",
        "why": "Atomic strategy map — select implementation by key, replace without call-site changes",
        "tags": ["arch", "strategy", "algorithm", "polymorphism"],
        "iface": r'''export class Strategy<K extends string, R, A extends unknown[]> {
  set(key: K, fn: (...args: A) => R): void
  run(key: K, ...args: A): R
}''',
        "code": r'''export class Strategy<K extends string, R, A extends unknown[]> {
  private map = new Map<K, (...args: A) => R>();
  set(key: K, fn: (...args: A) => R) { this.map.set(key, fn); }
  run(key: K, ...args: A) {
    const fn = this.map.get(key);
    if (!fn) throw new Error(`No strategy for: ${key}`);
    return fn(...args);
  }
}''',
        "provides": "Strategy",
        "depends": [],
    },
    {
        "id": "arch-decorator",
        "name": "Decorator Wrapper",
        "category": "arch",
        "lang": "typescript",
        "when": "Adding behavior around a function without editing it (logging, timing, retry)",
        "why": "Atomic higher-order decorators — compose tiny wrappers, keep the core pure",
        "tags": ["arch", "decorator", "wrapper", "composition", "higher-order"],
        "iface": r'''export function timed<A extends unknown[], R>(fn: (...args: A) => R): ((...args: A) => { result: R; ms: number })''',
        "code": r'''export function timed<A extends unknown[], R>(fn: (...args: A) => R) {
  return (...args: A) => {
    const t0 = performance.now();
    const result = fn(...args);
    return { result, ms: performance.now() - t0 };
  };
}''',
        "provides": "timed(fn)",
        "depends": [],
    },
    {
        "id": "arch-adapter",
        "name": "Adapter Bridge",
        "category": "arch",
        "lang": "typescript",
        "when": "Adapting one interface to another so a third-party API fits your domain types",
        "why": "Atomic shape translator — normalize foreign objects to a stable internal contract",
        "tags": ["arch", "adapter", "bridge", "interface", "translate"],
        "iface": r'''export function adapt<T, U>(foreign: T, map: (t: T) => U): U''',
        "code": r'''export function adapt<T, U>(foreign: T, map: (t: T) => U): U {
  if (foreign == null) throw new Error('Cannot adapt nullish value');
  return map(foreign);
}''',
        "provides": "adapt(foreign, map)",
        "depends": [],
    },
    {
        "id": "arch-facade",
        "name": "Facade",
        "category": "arch",
        "lang": "typescript",
        "when": "Exposing one simple API over a bundle of complex subsystems",
        "why": "Atomic facade object — hide orchestration behind 2-3 high-level methods",
        "tags": ["arch", "facade", "simplify", "subsystem"],
        "iface": r'''export class Facade<T extends Record<string, unknown>> {
  constructor(private deps: T)
  delegate<K extends keyof T>(key: K, method: string, ...args: unknown[]): unknown
}''',
        "code": r'''export class Facade<T extends Record<string, unknown>> {
  constructor(private deps: T) {}
  delegate<K extends keyof T>(key: K, method: string, ...args: unknown[]) {
    const dep = this.deps[key] as Record<string, (...a: unknown[]) => unknown>;
    const fn = dep[method];
    if (typeof fn !== 'function') throw new Error(`No method ${String(key)}.${method}`);
    return fn.apply(dep, args);
  }
}''',
        "provides": "Facade",
        "depends": [],
    },
    {
        "id": "arch-proxy",
        "name": "Proxy Guard",
        "category": "arch",
        "lang": "typescript",
        "when": "Intercepting access to an object for guards, logging, or lazy init",
        "why": "Atomic Proxy-based interceptor — validate/measure access without touching the target",
        "tags": ["arch", "proxy", "intercept", "guard", "access-control"],
        "iface": r'''export function guarded<T extends object>(target: T, allow: (prop: string | symbol) => boolean): T''',
        "code": r'''export function guarded<T extends object>(target: T, allow: (prop: string | symbol) => boolean): T {
  return new Proxy(target, {
    get(obj, prop, recv) {
      if (!allow(prop)) throw new Error(`Access denied: ${String(prop)}`);
      return Reflect.get(obj, prop, recv);
    },
    set(obj, prop, value) {
      if (!allow(prop)) throw new Error(`Access denied: ${String(prop)}`);
      return Reflect.set(obj, prop, value);
    },
  });
}''',
        "provides": "guarded(target, allow)",
        "depends": [],
    },
    {
        "id": "arch-command",
        "name": "Command",
        "category": "arch",
        "lang": "typescript",
        "when": "Encapsulating an action + its undo so it can be queued or rolled back",
        "why": "Atomic command object with undo — the primitive for undoable op stacks",
        "tags": ["arch", "command", "undo", "action", "queue"],
        "iface": r'''export interface Command<T = void> { execute(): T; undo(): void }
export class CommandStack {
  push(c: Command): void
  undo(): void
  get depth(): number
}''',
        "code": r'''export class CommandStack {
  private stack: Command[] = [];
  push(c: Command) { c.execute(); this.stack.push(c); }
  undo() {
    const c = this.stack.pop();
    if (c) c.undo();
  }
  get depth() { return this.stack.length; }
}''',
        "provides": "CommandStack",
        "depends": [],
    },
    {
        "id": "arch-mediator",
        "name": "Mediator",
        "category": "arch",
        "lang": "typescript",
        "when": "Routing messages between peers so they never reference each other",
        "why": "Atomic mediator bus — peers register, mediator forwards, decoupled topology",
        "tags": ["arch", "mediator", "decouple", "routing"],
        "iface": r'''export class Mediator {
  on(topic: string, h: (msg: unknown) => void): () => void
  emit(topic: string, msg: unknown): void
}''',
        "code": r'''export class Mediator {
  private handlers = new Map<string, Set<(msg: unknown) => void>>();
  on(topic: string, h: (msg: unknown) => void) {
    if (!this.handlers.has(topic)) this.handlers.set(topic, new Set());
    this.handlers.get(topic)!.add(h);
    return () => this.handlers.get(topic)?.delete(h);
  }
  emit(topic: string, msg: unknown) { this.handlers.get(topic)?.forEach((h) => h(msg)); }
}''',
        "provides": "Mediator",
        "depends": [],
    },
    {
        "id": "arch-memento",
        "name": "Memento Snapshot",
        "category": "arch",
        "lang": "typescript",
        "when": "Capturing and restoring object state without exposing internals",
        "why": "Atomic snapshot/restore on a state object — history checkpoints for free",
        "tags": ["arch", "memento", "snapshot", "restore", "state"],
        "iface": r'''export class Memento<T> {
  snapshot(): T
  restore(s: T): void
}''',
        "code": r'''export class Memento<T> {
  constructor(private state: T) {}
  snapshot() { return structuredClone(this.state); }
  restore(s: T) { this.state = structuredClone(s); }
  get value() { return this.state; }
}''',
        "provides": "Memento",
        "depends": [],
    },
    {
        "id": "arch-chain-responsibility",
        "name": "Chain of Responsibility",
        "category": "arch",
        "lang": "typescript",
        "when": "Passing a request through a chain of handlers until one handles it",
        "why": "Atomic handler chain — each link can process, delegate, or reject",
        "tags": ["arch", "chain", "responsibility", "handlers", "pipeline"],
        "iface": r'''export type Handler<T> = (req: T, next: () => T) => T
export function chain<T>(handlers: Handler<T>[]): (req: T) => T''',
        "code": r'''export function chain<T>(handlers: Handler<T>[]) {
  return (req: T) => {
    let i = 0;
    const next = (): T => {
      const h = handlers[i++];
      if (!h) return req;
      return h(req, next);
    };
    return next();
  };
}''',
        "provides": "chain(handlers)",
        "depends": [],
    },
    {
        "id": "arch-flyweight",
        "name": "Flyweight Pool",
        "category": "arch",
        "lang": "typescript",
        "when": "Reusing shared immutable instances instead of allocating duplicates",
        "why": "Atomic dedupe cache — same key returns the same instance, memory stays flat",
        "tags": ["arch", "flyweight", "pool", "memory", "cache"],
        "iface": r'''export class Flyweight<K, V> {
  get(key: K, create: () => V): V
  get size(): number
}''',
        "code": r'''export class Flyweight<K, V> {
  private map = new Map<K, V>();
  get(key: K, create: () => V) {
    let v = this.map.get(key);
    if (v === undefined) { v = create(); this.map.set(key, v); }
    return v;
  }
  get size() { return this.map.size; }
}''',
        "provides": "Flyweight",
        "depends": [],
    },
    {
        "id": "arch-composite",
        "name": "Composite Tree",
        "category": "arch",
        "lang": "typescript",
        "when": "Treating single items and groups of items uniformly",
        "why": "Atomic tree node with leaf/group operations — render or price a whole hierarchy in one call",
        "tags": ["arch", "composite", "tree", "recursive", "group"],
        "iface": r'''export interface TreeNode<T> { value: T; children: TreeNode<T>[] }
export function walk<T>(root: TreeNode<T>, visit: (n: TreeNode<T>, depth: number) => void): void''',
        "code": r'''export function walk<T>(root: TreeNode<T>, visit: (n: TreeNode<T>, depth: number) => void) {
  const go = (n: TreeNode<T>, d: number) => {
    visit(n, d);
    n.children.forEach((c) => go(c, d + 1));
  };
  go(root, 0);
}''',
        "provides": "walk(root, visit)",
        "depends": [],
    },
    {
        "id": "arch-di-container",
        "name": "DI Container",
        "category": "arch",
        "lang": "typescript",
        "when": "Resolving dependencies by name with lazy singleton construction",
        "why": "Atomic IoC container — register factories, resolve singletons, no framework",
        "tags": ["arch", "di", "container", "ioc", "singleton"],
        "iface": r'''export class Container {
  register<T>(name: string, factory: () => T): void
  resolve<T>(name: string): T
  get singleton<T>(name: string): T
}''',
        "code": r'''export class Container {
  private factories = new Map<string, () => unknown>();
  private singletons = new Map<string, unknown>();
  register<T>(name: string, factory: () => T) { this.factories.set(name, factory); }
  resolve<T>(name: string): T {
    const f = this.factories.get(name);
    if (!f) throw new Error(`Unregistered dependency: ${name}`);
    return f() as T;
  }
  singleton<T>(name: string): T {
    if (!this.singletons.has(name)) this.singletons.set(name, this.resolve<T>(name));
    return this.singletons.get(name) as T;
  }
}''',
        "provides": "Container",
        "depends": [],
    },
    {
        "id": "arch-plugin-registry",
        "name": "Plugin Registry",
        "category": "arch",
        "lang": "typescript",
        "when": "Loading extensions by id with dependency/version checks",
        "why": "Atomic plugin registry — install/enable/uninstall lifecycle, idempotent",
        "tags": ["arch", "plugin", "registry", "extension", "lifecycle"],
        "iface": r'''export interface Plugin { id: string; version: string; activate(): void }
export class PluginRegistry {
  install(p: Plugin): void
  activate(id: string): void
  uninstall(id: string): void
}''',
        "code": r'''export class PluginRegistry {
  private plugins = new Map<string, Plugin>();
  install(p: Plugin) { if (this.plugins.has(p.id)) throw new Error(`Plugin exists: ${p.id}`); this.plugins.set(p.id, p); }
  activate(id: string) { this.plugins.get(id)?.activate(); }
  uninstall(id: string) { if (!this.plugins.delete(id)) throw new Error(`Unknown plugin: ${id}`); }
}''',
        "provides": "PluginRegistry",
        "depends": [],
    },
    {
        "id": "arch-unit-of-work",
        "name": "Unit of Work",
        "category": "arch",
        "lang": "typescript",
        "when": "Batching tracked changes into one commit with rollback on error",
        "why": "Atomic change tracker — collect dirty entities, commit or rollback atomically",
        "tags": ["arch", "unit-of-work", "transaction", "tracking"],
        "iface": r'''export class UnitOfWork<T> {
  track(item: T): void
  commit(flush: (items: T[]) => Promise<void>): Promise<void>
  get pending(): number
}''',
        "code": r'''export class UnitOfWork<T> {
  private items: T[] = [];
  track(item: T) { this.items.push(item); }
  async commit(flush: (items: T[]) => Promise<void>) {
    const batch = this.items.splice(0);
    try { await flush(batch); }
    catch (err) { this.items.unshift(...batch); throw err; }
  }
  get pending() { return this.items.length; }
}''',
        "provides": "UnitOfWork",
        "depends": [],
    },
    {
        "id": "arch-feature-flags",
        "name": "Feature Flag Evaluator",
        "category": "arch",
        "lang": "typescript",
        "when": "Rolling out features gradually with user- or percent-based targeting",
        "why": "Atomic flag evaluator — percentage + user-hash + allowlist, no external service",
        "tags": ["arch", "feature-flag", "rollout", "targeting"],
        "iface": r'''export interface FlagRule { key: string; enabled: boolean; percent?: number; users?: string[] }
export function evaluateFlag(rule: FlagRule, userId: string): boolean''',
        "code": r'''function hashStr(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
export function evaluateFlag(rule: FlagRule, userId: string) {
  if (!rule.enabled) return false;
  if (rule.users?.includes(userId)) return true;
  if (rule.percent != null) return (hashStr(rule.key + ':' + userId) % 100) < rule.percent;
  return true;
}''',
        "provides": "evaluateFlag(rule, userId)",
        "depends": [],
    },
]
