# -*- coding: utf-8 -*-
"""
Code Bible — Category 29: Messaging & Events (atomic).
Convention: topic/partition string keys, JSON-serializable payloads, no deps.
"""
CHUNKS = [
    {
        "id": "msg-routing-bus",
        "name": "Routing-Key Bus",
        "category": "msg",
        "lang": "typescript",
        "when": "Routing messages to subscribers by dotted routing keys with wildcards",
        "why": "Atomic topic router — '*' matches one segment, '#' matches the rest",
        "tags": ["msg", "routing", "bus", "wildcard", "topic"],
        "iface": r'''export class RoutingBus {
  subscribe(pattern: string, h: (msg: unknown, key: string) => void): () => void
  publish(key: string, msg: unknown): void
}''',
        "code": r'''export class RoutingBus {
  private subs = new Map<string, Array<(msg: unknown, key: string) => void>>();
  private matches(pattern: string, key: string) {
    const p = pattern.split('.'), k = key.split('.');
    for (let i = 0; i < p.length; i++) {
      if (p[i] === '#') return true;
      if (i >= k.length || (p[i] !== '*' && p[i] !== k[i])) return false;
    }
    return p.length === k.length;
  }
  subscribe(pattern: string, h: (msg: unknown, key: string) => void) {
    if (!this.subs.has(pattern)) this.subs.set(pattern, []);
    this.subs.get(pattern)!.push(h);
    return () => {
      const arr = this.subs.get(pattern)!;
      arr.splice(arr.indexOf(h), 1);
    };
  }
  publish(key: string, msg: unknown) {
    for (const [pattern, hs] of this.subs) if (this.matches(pattern, key)) hs.forEach((h) => h(msg, key));
  }
}''',
        "provides": "RoutingBus",
        "depends": [],
    },
    {
        "id": "msg-topic-partitioner",
        "name": "Topic Partitioner",
        "category": "msg",
        "lang": "typescript",
        "when": "Assigning messages to a fixed partition count for ordered consumption",
        "why": "Atomic partitioner — stable hash of a key, spreads load deterministically",
        "tags": ["msg", "partition", "topic", "hash", "ordering"],
        "iface": r'''export function partitionForKey(key: string, partitions: number): number''',
        "code": r'''export function partitionForKey(key: string, partitions: number) {
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) { h ^= key.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) % partitions;
}''',
        "provides": "partitionForKey(key, partitions)",
        "depends": [],
    },
    {
        "id": "msg-message-envelope",
        "name": "Message Envelope",
        "category": "msg",
        "lang": "typescript",
        "when": "Wrapping a payload with id, timestamp, type, and metadata",
        "why": "Atomic envelope — every message gets traceable identity + routing metadata",
        "tags": ["msg", "envelope", "message", "metadata", "trace"],
        "iface": r'''export interface Envelope<T> { id: string; type: string; ts: number; payload: T; meta?: Record<string, unknown> }
export function wrap<T>(type: string, payload: T, id?: string): Envelope<T>''',
        "code": r'''export function wrap<T>(type: string, payload: T, id?: string): Envelope<T> {
  return { id: id ?? Math.random().toString(36).slice(2) + Date.now().toString(36), type, ts: Date.now(), payload };
}''',
        "provides": "wrap(type, payload, id?)",
        "depends": [],
    },
    {
        "id": "msg-event-versioning",
        "name": "Event Versioner",
        "category": "msg",
        "lang": "typescript",
        "when": "Tagging events with a schema version so consumers can migrate",
        "why": "Atomic version stamp — adds version + schema name, lets consumers dispatch",
        "tags": ["msg", "event", "version", "schema", "migration"],
        "iface": r'''export interface Versioned { __version: number; __schema: string }
export function stampVersion<T extends object>(obj: T, schema: string, version: number): T & Versioned''',
        "code": r'''export function stampVersion<T extends object>(obj: T, schema: string, version: number) {
  return { ...obj, __version: version, __schema: schema } as T & Versioned;
}''',
        "provides": "stampVersion(obj, schema, version)",
        "depends": [],
    },
    {
        "id": "msg-idempotent-consumer",
        "name": "Idempotent Consumer",
        "category": "msg",
        "lang": "typescript",
        "when": "Guarding a handler against duplicate deliveries via message ids",
        "why": "Atomic dedupe gate — seen-id cache (bounded), returns false on repeat",
        "tags": ["msg", "idempotent", "dedupe", "consumer", "delivery"],
        "iface": r'''export class IdempotentConsumer {
  constructor(maxCache?: number)
  process<T>(id: string, fn: () => T): T | null
}''',
        "code": r'''export class IdempotentConsumer {
  private seen = new Set<string>();
  constructor(private maxCache = 10000) {}
  process<T>(id: string, fn: () => T): T | null {
    if (this.seen.has(id)) return null;
    this.seen.add(id);
    if (this.seen.size > this.maxCache) this.seen.delete(this.seen.values().next().value as string);
    return fn();
  }
}''',
        "provides": "IdempotentConsumer",
        "depends": [],
    },
    {
        "id": "msg-at-least-once",
        "name": "At-Least-Once Ack Manager",
        "category": "msg",
        "lang": "typescript",
        "when": "Tracking unacked deliveries and re-delivering after a timeout",
        "why": "Atomic ack window — claim with deadline, ack/nack, redeliver expired",
        "tags": ["msg", "ack", "at-least-once", "redelivery", "timeout"],
        "iface": r'''export class AckManager {
  constructor(timeoutMs?: number)
  claim(id: string): boolean
  ack(id: string): void
  expired(): string[]
}''',
        "code": r'''export class AckManager {
  private pending = new Map<string, number>();
  constructor(private timeoutMs = 30000) {}
  claim(id: string) {
    if (this.pending.has(id)) return false;
    this.pending.set(id, Date.now() + this.timeoutMs);
    return true;
  }
  ack(id: string) { this.pending.delete(id); }
  expired() {
    const now = Date.now();
    const out: string[] = [];
    for (const [id, deadline] of this.pending) if (deadline < now) { out.push(id); this.pending.delete(id); }
    return out;
  }
}''',
        "provides": "AckManager",
        "depends": [],
    },
    {
        "id": "msg-ordered-consumer",
        "name": "Ordered Partition Consumer",
        "category": "msg",
        "lang": "typescript",
        "when": "Preserving per-key order while processing a stream with a worker limit",
        "why": "Atomic per-key FIFO — dispatch strips key order, worker cap bounds concurrency",
        "tags": ["msg", "ordered", "partition", "consumer", "fifo"],
        "iface": r'''export class OrderedConsumer<T> {
  constructor(process: (key: string, msg: T) => Promise<void>, concurrency?: number)
  submit(key: string, msg: T): void
  get queued(): number
}''',
        "code": r'''export class OrderedConsumer<T> {
  private queues = new Map<string, T[]>();
  private active = 0;
  constructor(private process: (key: string, msg: T) => Promise<void>, private concurrency = 4) {}
  submit(key: string, msg: T) {
    if (!this.queues.has(key)) this.queues.set(key, []);
    this.queues.get(key)!.push(msg);
    this.drain();
  }
  private drain() {
    while (this.active < this.concurrency) {
      let next: [string, T] | null = null;
      for (const [key, q] of this.queues) {
        if (q.length) { next = [key, q.shift()!]; break; }
      }
      if (!next) break;
      this.active++;
      const [key, msg] = next;
      this.process(key, msg).finally(() => { this.active--; this.drain(); });
    }
  }
  get queued() { return [...this.queues.values()].reduce((s, q) => s + q.length, 0); }
}''',
        "provides": "OrderedConsumer",
        "depends": [],
    },
    {
        "id": "msg-event-store",
        "name": "Event Store (append + replay)",
        "category": "msg",
        "lang": "typescript",
        "when": "Appending events and replaying them from a sequence number",
        "why": "Atomic log with offsets — append returns seq, replay from seq, snapshot hint",
        "tags": ["msg", "event-store", "append", "replay", "log"],
        "iface": r'''export class EventStoreLog<T> {
  append(event: T): number
  replay(fromSeq: number): Array<{ seq: number; event: T }>
  get lastSeq(): number
}''',
        "code": r'''export class EventStoreLog<T> {
  private events: Array<{ seq: number; event: T }> = [];
  private nextSeq = 0;
  append(event: T) {
    const seq = this.nextSeq++;
    this.events.push({ seq, event });
    return seq;
  }
  replay(fromSeq: number) { return this.events.filter((e) => e.seq >= fromSeq); }
  get lastSeq() { return this.nextSeq - 1; }
}''',
        "provides": "EventStoreLog",
        "depends": [],
    },
    {
        "id": "msg-req-reply",
        "name": "Request/Reply Correlation",
        "category": "msg",
        "lang": "typescript",
        "when": "Matching async replies to their original requests",
        "why": "Atomic correlation registry — request in, promise keyed by id, reply resolves it",
        "tags": ["msg", "request-reply", "correlation", "promise", "async"],
        "iface": r'''export class RequestReply {
  request<T>(id: string): Promise<T>
  reply<T>(id: string, payload: T): void
  fail(id: string, err: Error): void
}''',
        "code": r'''export class RequestReply {
  private pending = new Map<string, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  request<T>(id: string) {
    return new Promise<T>((resolve, reject) => this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject }));
  }
  reply<T>(id: string, payload: T) {
    this.pending.get(id)?.resolve(payload);
    this.pending.delete(id);
  }
  fail(id: string, err: Error) {
    this.pending.get(id)?.reject(err);
    this.pending.delete(id);
  }
}''',
        "provides": "RequestReply",
        "depends": [],
    },
    {
        "id": "msg-consumer-lag",
        "name": "Consumer Lag Tracker",
        "category": "msg",
        "lang": "typescript",
        "when": "Monitoring how far a consumer falls behind the producer",
        "why": "Atomic lag gauge — high-water mark vs consumer offset per group",
        "tags": ["msg", "lag", "consumer", "monitor", "offset"],
        "iface": r'''export class LagTracker {
  setHighWater(offset: number): void
  setConsumerOffset(group: string, offset: number): void
  lag(group: string): number
}''',
        "code": r'''export class LagTracker {
  private high = 0;
  private consumers = new Map<string, number>();
  setHighWater(offset: number) { this.high = Math.max(this.high, offset); }
  setConsumerOffset(group: string, offset: number) { this.consumers.set(group, offset); }
  lag(group: string) { return Math.max(0, this.high - (this.consumers.get(group) ?? 0)); }
}''',
        "provides": "LagTracker",
        "depends": [],
    },
    {
        "id": "msg-channel-mux",
        "name": "Channel Multiplexer",
        "category": "msg",
        "lang": "typescript",
        "when": "Merging multiple input streams into one ordered output",
        "why": "Atomic multiplexer — register sources, fan-in with optional tags",
        "tags": ["msg", "multiplex", "channel", "merge", "fan-in"],
        "iface": r'''export class ChannelMux<T> {
  addSource(name: string, source: Iterable<T>): void
  *drain(): Generator<{ source: string; value: T }>
}''',
        "code": r'''export class ChannelMux<T> {
  private sources: Array<{ name: string; source: Iterable<T> }> = [];
  addSource(name: string, source: Iterable<T>) { this.sources.push({ name, source }); }
  *drain() {
    for (const { name, source } of this.sources) for (const value of source) yield { source: name, value };
  }
}''',
        "provides": "ChannelMux",
        "depends": [],
    },
    {
        "id": "msg-fan-in",
        "name": "Fan-In Aggregator",
        "category": "msg",
        "lang": "typescript",
        "when": "Collecting results from N workers and resolving when all finish",
        "why": "Atomic aggregator — per-id counts, all-done callback, error escalation",
        "tags": ["msg", "fan-in", "aggregate", "collect", "workers"],
        "iface": r'''export class FanIn {
  constructor(total: number, onComplete: (results: unknown[]) => void, onError?: (e: Error) => void)
  submit(index: number, value: unknown): void
  fail(e: Error): void
}''',
        "code": r'''export class FanIn {
  private results: unknown[] = [];
  private done = 0;
  constructor(private total: number, private onComplete: (results: unknown[]) => void, private onError?: (e: Error) => void) {}
  submit(index: number, value: unknown) {
    this.results[index] = value;
    if (++this.done >= this.total) this.onComplete(this.results);
  }
  fail(e: Error) { this.onError?.(e); }
}''',
        "provides": "FanIn",
        "depends": [],
    },
    {
        "id": "msg-poison-message",
        "name": "Poison Message Handler",
        "category": "msg",
        "lang": "typescript",
        "when": "Retrying a failing message with a cap, then quarantining it",
        "why": "Atomic retry-quarantine — attempt count per id, quarantine after cap",
        "tags": ["msg", "poison", "retry", "quarantine", "dead-letter"],
        "iface": r'''export class PoisonHandler {
  constructor(maxAttempts?: number)
  attempt<T>(id: string, fn: () => Promise<T>): Promise<T | 'quarantined'>
}''',
        "code": r'''export class PoisonHandler {
  private attempts = new Map<string, number>();
  constructor(private maxAttempts = 3) {}
  async attempt<T>(id: string, fn: () => Promise<T>): Promise<T | 'quarantined'> {
    const n = (this.attempts.get(id) ?? 0) + 1;
    this.attempts.set(id, n);
    try { return await fn(); }
    catch (err) {
      if (n >= this.maxAttempts) { this.attempts.delete(id); return 'quarantined'; }
      throw err;
    }
  }
}''',
        "provides": "PoisonHandler",
        "depends": [],
    },
    {
        "id": "msg-schema-registry",
        "name": "Schema Registry Client",
        "category": "msg",
        "lang": "typescript",
        "when": "Versioning message schemas and validating payloads against them",
        "why": "Atomic registry — register schema (predicate), look up by name+version, validate",
        "tags": ["msg", "schema", "registry", "validate", "version"],
        "iface": r'''export class SchemaRegistry {
  register(name: string, version: number, validate: (p: unknown) => string | null): void
  validate(name: string, version: number, payload: unknown): string | null
}''',
        "code": r'''export class SchemaRegistry {
  private schemas = new Map<string, (p: unknown) => string | null>();
  register(name: string, version: number, validate: (p: unknown) => string | null) {
    this.schemas.set(name + '@' + version, validate);
  }
  validate(name: string, version: number, payload: unknown) {
    const v = this.schemas.get(name + '@' + version);
    if (!v) return `Unknown schema ${name}@${version}`;
    return v(payload);
  }
}''',
        "provides": "SchemaRegistry",
        "depends": [],
    },
    {
        "id": "msg-webhook-dispatch",
        "name": "Webhook Dispatcher (retry)",
        "category": "msg",
        "lang": "typescript",
        "when": "Delivering events to HTTP endpoints with retries and backoff",
        "why": "Atomic dispatcher — deliver(url, payload) with retry count + delay, logs failures",
        "tags": ["msg", "webhook", "dispatch", "retry", "delivery"],
        "iface": r'''export class WebhookDispatcher {
  constructor(post: (url: string, body: unknown) => Promise<void>, retries?: number, delayMs?: number)
  async deliver(url: string, payload: unknown): Promise<boolean>
}''',
        "code": r'''export class WebhookDispatcher {
  constructor(private post: (url: string, body: unknown) => Promise<void>, private retries = 3, private delayMs = 1000) {}
  async deliver(url: string, payload: unknown) {
    for (let attempt = 0; attempt <= this.retries; attempt++) {
      try { await this.post(url, payload); return true; }
      catch { if (attempt < this.retries) await new Promise((r) => setTimeout(r, this.delayMs * (attempt + 1))); }
    }
    return false;
  }
}''',
        "provides": "WebhookDispatcher",
        "depends": [],
    },
    {
        "id": "msg-event-replay",
        "name": "Event Replay",
        "category": "msg",
        "lang": "typescript",
        "when": "Re-applying a stored event sequence to rebuild or re-sync state",
        "why": "Atomic replayer — events + projector in, state out, idempotent by seq filter",
        "tags": ["msg", "replay", "events", "projection", "rebuild"],
        "iface": r'''export function replayEvents<S>(events: Array<{ seq: number; event: unknown }>, initialState: S, apply: (s: S, e: unknown) => S): S''',
        "code": r'''export function replayEvents<S>(events: Array<{ seq: number; event: unknown }>, initialState: S, apply: (s: S, e: unknown) => S) {
  return events.slice().sort((a, b) => a.seq - b.seq).reduce((state, e) => apply(state, e.event), initialState);
}''',
        "provides": "replayEvents(events, initialState, apply)",
        "depends": [],
    },
    {
        "id": "msg-group-consumer",
        "name": "Group Consumer Tracker",
        "category": "msg",
        "lang": "typescript",
        "when": "Tracking which consumer group members own which partitions",
        "why": "Atomic group registry — assign/revoke partitions, membership with heartbeats",
        "tags": ["msg", "group", "consumer", "partition", "membership"],
        "iface": r'''export class GroupTracker {
  join(memberId: string): void
  assign(memberId: string, partitions: number[]): void
  partitionsOf(memberId: string): number[]
}''',
        "code": r'''export class GroupTracker {
  private members = new Map<string, number[]>();
  join(memberId: string) { if (!this.members.has(memberId)) this.members.set(memberId, []); }
  assign(memberId: string, partitions: number[]) { this.members.set(memberId, partitions); }
  partitionsOf(memberId: string) { return this.members.get(memberId) ?? []; }
}''',
        "provides": "GroupTracker",
        "depends": [],
    },
    {
        "id": "msg-compacted-topic",
        "name": "Compacted Topic Reader",
        "category": "msg",
        "lang": "typescript",
        "when": "Keeping only the latest value per key (compaction) when reading a log",
        "why": "Atomic compact — keyed reduce keeps last write, preserves key order",
        "tags": ["msg", "compact", "topic", "key", "latest"],
        "iface": r'''export function compactByKey<T>(events: Array<{ key: string; value: T }>): Array<{ key: string; value: T }>''',
        "code": r'''export function compactByKey<T>(events: Array<{ key: string; value: T }>) {
  const last = new Map<string, T>();
  for (const e of events) last.set(e.key, e.value);
  return [...last.entries()].map(([key, value]) => ({ key, value }));
}''',
        "provides": "compactByKey(events)",
        "depends": [],
    },
    {
        "id": "msg-transactional",
        "name": "Transactional Message",
        "category": "msg",
        "lang": "typescript",
        "when": "Bundling several sends that all commit or all roll back",
        "why": "Atomic multi-send — stage sends, commit flushes all, rollback discards",
        "tags": ["msg", "transactional", "commit", "rollback", "batch"],
        "iface": r'''export class TransactionalSink<T> {
  constructor(send: (msg: T) => void)
  stage(msg: T): void
  commit(): void
  rollback(): void
}''',
        "code": r'''export class TransactionalSink<T> {
  private staged: T[] = [];
  constructor(private send: (msg: T) => void) {}
  stage(msg: T) { this.staged.push(msg); }
  commit() { const batch = this.staged.splice(0); batch.forEach((m) => this.send(m)); }
  rollback() { this.staged = []; }
}''',
        "provides": "TransactionalSink",
        "depends": [],
    },
    {
        "id": "msg-exactly-once",
        "name": "Exactly-Once Dedupe",
        "category": "msg",
        "lang": "typescript",
        "when": "Guaranteeing a side effect runs once even if a message repeats",
        "why": "Atomic result cache — stores outcome by id so repeats replay the result, not the effect",
        "tags": ["msg", "exactly-once", "dedupe", "idempotent", "cache"],
        "iface": r'''export class ExactlyOnce<T> {
  constructor(run: (id: string) => T | Promise<T>)
  get(id: string): Promise<T>
}''',
        "code": r'''export class ExactlyOnce<T> {
  private cache = new Map<string, Promise<T>>();
  constructor(private run: (id: string) => T | Promise<T>) {}
  get(id: string) {
    if (!this.cache.has(id)) this.cache.set(id, Promise.resolve(this.run(id)));
    return this.cache.get(id)!;
  }
}''',
        "provides": "ExactlyOnce",
        "depends": [],
    },
    {
        "id": "msg-window-agg",
        "name": "Streaming Window Aggregator",
        "category": "msg",
        "lang": "typescript",
        "when": "Aggregating events in sliding time windows and expiring old ones",
        "why": "Atomic tumbling/sliding windows — timestamped adds, aggregate fn, auto-expire",
        "tags": ["msg", "window", "aggregate", "stream", "sliding"],
        "iface": r'''export class WindowAggregator<T, A> {
  constructor(windowMs: number, fold: (acc: A, item: T) => A, init: A)
  add(item: T): A
  prune(now?: number): void
  get current(): A
}''',
        "code": r'''export class WindowAggregator<T, A> {
  private items: Array<{ t: number; v: T }> = [];
  constructor(private windowMs: number, private fold: (acc: A, item: T) => A, private init: A) {}
  add(item: T) {
    this.items.push({ t: Date.now(), v: item });
    this.prune();
    return this.fold(this.items.slice().reverse().reduce((acc, i) => this.fold(acc, i.v), this.init), item) as A;
  }
  prune(now = Date.now()) {
    const cutoff = now - this.windowMs;
    this.items = this.items.filter((i) => i.t >= cutoff);
  }
  get current() { return this.items.reduce((acc, i) => this.fold(acc, i.v), this.init); }
}''',
        "provides": "WindowAggregator",
        "depends": [],
    },
    {
        "id": "msg-dead-letter-alert",
        "name": "Dead-Letter Alert",
        "category": "msg",
        "lang": "typescript",
        "when": "Notifying when dead-lettered messages cross a threshold",
        "why": "Atomic alert gate — count per queue, fires callback once when crossed",
        "tags": ["msg", "dead-letter", "alert", "threshold", "monitor"],
        "iface": r'''export class DeadLetterAlert {
  constructor(queue: string, threshold: number, onAlert: (q: string, n: number) => void)
  record(): void
  reset(): void
}''',
        "code": r'''export class DeadLetterAlert {
  private count = 0;
  private fired = false;
  constructor(private queue: string, private threshold: number, private onAlert: (q: string, n: number) => void) {}
  record() {
    this.count++;
    if (this.count >= this.threshold && !this.fired) { this.fired = true; this.onAlert(this.queue, this.count); }
  }
  reset() { this.count = 0; this.fired = false; }
}''',
        "provides": "DeadLetterAlert",
        "depends": [],
    },
    {
        "id": "msg-priority-queue",
        "name": "Priority Message Queue",
        "category": "msg",
        "lang": "typescript",
        "when": "Draining high-priority messages before lower ones",
        "why": "Atomic bucket queue — push(level), shift highest first, FIFO within level",
        "tags": ["msg", "priority", "queue", "ordering"],
        "iface": r'''export class PriorityQueue<T> {
  constructor(levels?: number)
  push(level: number, item: T): void
  shift(): T | undefined
  get size(): number
}''',
        "code": r'''export class PriorityQueue<T> {
  private buckets: T[][];
  constructor(private levels = 3) { this.buckets = Array.from({ length: levels }, () => []); }
  push(level: number, item: T) { this.buckets[Math.max(0, Math.min(level, this.levels - 1))].push(item); }
  shift() {
    for (const b of this.buckets) if (b.length) return b.shift();
    return undefined;
  }
  get size() { return this.buckets.reduce((s, b) => s + b.length, 0); }
}''',
        "provides": "PriorityQueue",
        "depends": [],
    },
    {
        "id": "msg-delay-queue",
        "name": "Delayed Message Queue",
        "category": "msg",
        "lang": "typescript",
        "when": "Scheduling a message to become visible after a delay",
        "why": "Atomic delayed FIFO — push(delayMs), popDue returns only matured items",
        "tags": ["msg", "delay", "queue", "schedule", "timer"],
        "iface": r'''export class DelayedQueue<T> {
  push(item: T, delayMs: number): void
  popDue(now?: number): T[]
  get pending(): number
}''',
        "code": r'''export class DelayedQueue<T> {
  private items: Array<{ due: number; v: T }> = [];
  push(item: T, delayMs: number) { this.items.push({ due: Date.now() + delayMs, v: item }); }
  popDue(now = Date.now()) {
    const due: T[] = [];
    this.items = this.items.filter((i) => {
      if (i.due <= now) { due.push(i.v); return false; }
      return true;
    });
    return due;
  }
  get pending() { return this.items.length; }
}''',
        "provides": "DelayedQueue",
        "depends": [],
    },
    {
        "id": "msg-subscription-checkpoint",
        "name": "Subscription Checkpoint",
        "category": "msg",
        "lang": "typescript",
        "when": "Persisting a consumer's last-read offset so it can resume",
        "why": "Atomic checkpoint store — get/set offset per subscription, in-memory default",
        "tags": ["msg", "checkpoint", "offset", "subscription", "resume"],
        "iface": r'''export class SubscriptionCheckpoint {
  constructor(load?: (key: string) => number | undefined, save?: (key: string, offset: number) => void)
  get(key: string): number | undefined
  set(key: string, offset: number): void
}''',
        "code": r'''export class SubscriptionCheckpoint {
  private memory = new Map<string, number>();
  constructor(private load?: (key: string) => number | undefined, private save?: (key: string, offset: number) => void) {}
  get(key: string) { return this.memory.has(key) ? this.memory.get(key) : this.load?.(key); }
  set(key: string, offset: number) { this.memory.set(key, offset); this.save?.(key, offset); }
}''',
        "provides": "SubscriptionCheckpoint",
        "depends": [],
    },
]
