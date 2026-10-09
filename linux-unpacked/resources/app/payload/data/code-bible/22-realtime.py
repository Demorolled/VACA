# -*- coding: utf-8 -*-
"""
Code Bible — Category 22: Realtime & collaboration (atomic, single-responsibility).
Convention: CRDT/logic primitives are pure; transport is injected, never imported.
"""
CHUNKS = [
    {
        "id": "rtc-lww-register",
        "name": "LWW Register CRDT",
        "category": "rtc",
        "lang": "typescript",
        "lang_extra": "typescript",
        "when": "Merging concurrent writes to a single field with last-writer-wins",
        "why": "Atomic CRDT: timestamped value + merge, concurrent-safe, no server",
        "tags": ["rtc", "crdt", "lww", "merge", "last-writer-wins"],
        "iface": r'''export interface LwwValue<T> { value: T; ts: number; actor: string }
export class LwwRegister<T> {
  constructor(initial?: T, actor?: string)
  set(value: T): void
  merge(other: LwwValue<T>): void
  get(): T
  snapshot(): LwwValue<T>
}''',
        "code": r'''export class LwwRegister<T> {
  private state: LwwValue<T>;
  constructor(initial: T, private actor = 'anon') {
    this.state = { value: initial, ts: 0, actor };
  }
  set(value: T) {
    this.state = { value, ts: Date.now(), actor: this.actor };
  }
  merge(other: LwwValue<T>) {
    if (other.ts > this.state.ts || (other.ts === this.state.ts && other.actor > this.state.actor)) {
      this.state = other;
    }
  }
  get() { return this.state.value; }
  snapshot() { return { ...this.state }; }
}''',
        "provides": "LwwRegister",
        "depends": [],
    },
    {
        "id": "rtc-gcounter",
        "name": "G-Counter / PN-Counter",
        "category": "rtc",
        "lang": "typescript",
        "when": "Increment-only or signed counters that merge across replicas",
        "why": "Atomic CRDT counters: per-actor vectors, merge = elementwise max",
        "tags": ["rtc", "crdt", "counter", "gcounter", "pncounter"],
        "iface": r'''export class GCounter {
  constructor(actor?: string)
  increment(by?: number): void
  merge(other: Record<string, number>): void
  value(): number
  state(): Record<string, number>
}''',
        "code": r'''export class GCounter {
  private counts: Record<string, number> = {};
  constructor(private actor = 'anon') { this.counts[actor] = 0; }
  increment(by = 1) { this.counts[this.actor] = (this.counts[this.actor] ?? 0) + by; }
  merge(other: Record<string, number>) {
    for (const [k, v] of Object.entries(other)) this.counts[k] = Math.max(this.counts[k] ?? 0, v);
  }
  value() { return Object.values(this.counts).reduce((s, v) => s + v, 0); }
  state() { return { ...this.counts }; }
}''',
        "provides": "GCounter",
        "depends": [],
    },
    {
        "id": "rtc-orset",
        "name": "OR-Set (add/remove)",
        "category": "rtc",
        "lang": "typescript",
        "when": "Sets where concurrent add/remove don't lose elements",
        "why": "Atomic CRDT set: tombstones per add/remove, merge = union of states",
        "tags": ["rtc", "crdt", "orset", "set", "tombstone"],
        "iface": r'''export class OrSet<T> {
  constructor()
  add(value: T): void
  remove(value: T): void
  has(value: T): boolean
  values(): T[]
  merge(other: { adds: Map<string, T>; removes: Set<string> }): void
  state(): { adds: Array<{ id: string; value: T }>; removes: string[] }
}''',
        "code": r'''export class OrSet<T> {
  private adds = new Map<string, T>();
  private removes = new Set<string>();
  private key(v: T) { return JSON.stringify(v); }
  add(value: T) {
    const k = this.key(value) + ':' + Math.random().toString(36).slice(2, 8);
    this.adds.set(k, value);
    this.removes.delete(k);
  }
  remove(value: T) {
    for (const [k, v] of this.adds) if (this.key(v) === this.key(value)) this.removes.add(k);
  }
  has(value: T) {
    const k = this.key(value);
    return [...this.adds.entries()].some(([id, v]) => this.key(v) === k && !this.removes.has(id));
  }
  values() { return [...this.adds.entries()].filter(([id]) => !this.removes.has(id)).map(([, v]) => v); }
  merge(other: { adds: Map<string, T>; removes: Set<string> }) {
    for (const [id, v] of other.adds) this.adds.set(id, v);
    for (const id of other.removes) this.removes.add(id);
  }
  state() { return { adds: [...this.adds].map(([id, value]) => ({ id, value })), removes: [...this.removes] }; }
}''',
        "provides": "OrSet",
        "depends": [],
    },
    {
        "id": "rtc-version-vector",
        "name": "Version Vector Compare",
        "category": "rtc",
        "lang": "typescript",
        "when": "Ordering events and detecting causality in distributed sync",
        "why": "Atomic vector clocks: bump/merge/causal-compare, lamport-style",
        "tags": ["rtc", "version", "vector", "causality", "lamport"],
        "iface": r'''export class VersionVector {
  constructor()
  bump(actor: string): number
  merge(other: Record<string, number>): void
  compare(other: Record<string, number>): 'before' | 'after' | 'concurrent' | 'equal'
  state(): Record<string, number>
}''',
        "code": r'''export class VersionVector {
  private v: Record<string, number> = {};
  bump(actor: string) { this.v[actor] = (this.v[actor] ?? 0) + 1; return this.v[actor]; }
  merge(other: Record<string, number>) { for (const [k, n] of Object.entries(other)) this.v[k] = Math.max(this.v[k] ?? 0, n); }
  compare(other: Record<string, number>) {
    const keys = new Set([...Object.keys(this.v), ...Object.keys(other)]);
    let before = true, after = true, equal = true;
    for (const k of keys) {
      const a = this.v[k] ?? 0, b = other[k] ?? 0;
      if (a > b) after = false, equal = false;
      if (a < b) before = false, equal = false;
      if (a !== b) equal = false;
    }
    return equal ? 'equal' : before ? 'before' : after ? 'after' : 'concurrent';
  }
  state() { return { ...this.v }; }
}''',
        "provides": "VersionVector",
        "depends": [],
    },
    {
        "id": "rtc-ot-text",
        "name": "Operational Transform (text)",
        "category": "rtc",
        "lang": "typescript",
        "when": "Applying and merging text insert/delete operations from multiple editors",
        "why": "Atomic OT: op apply + transform against concurrent ops, index-shift safe",
        "tags": ["rtc", "ot", "operational", "transform", "text"],
        "iface": r'''export type TextOp = { type: 'insert'; pos: number; text: string } | { type: 'delete'; pos: number; len: number }
export function applyOp(text: string, op: TextOp): string
export function transform(a: TextOp, against: TextOp): TextOp
export function compose(a: TextOp, b: TextOp): TextOp''',
        "code": r'''export function applyOp(text: string, op: TextOp) {
  if (op.type === 'insert') return text.slice(0, op.pos) + op.text + text.slice(op.pos);
  return text.slice(0, op.pos) + text.slice(op.pos + op.len);
}
export function transform(a: TextOp, against: TextOp): TextOp {
  if (against.type === 'insert') {
    if (a.pos >= against.pos) return { ...a, pos: a.pos + against.text.length };
    return a;
  }
  // against is delete
  if (a.type === 'insert') {
    if (a.pos > against.pos) return { ...a, pos: a.pos - Math.min(against.len, a.pos - against.pos) };
    return a;
  }
  // both delete
  if (a.pos >= against.pos + against.len) return { ...a, pos: a.pos - against.len };
  if (a.pos >= against.pos) return { ...a, pos: against.pos, len: Math.max(0, a.len - (against.pos + against.len - a.pos)) };
  return a;
}
export function compose(a: TextOp, b: TextOp): TextOp {
  const t = transform(b, a);
  if (a.type === 'insert' && t.type === 'insert') return { type: 'insert', pos: a.pos, text: a.text + t.text };
  return t;
}''',
        "provides": "applyOp / transform / compose",
        "depends": [],
    },
    {
        "id": "rtc-presence",
        "name": "Presence Heartbeat",
        "category": "rtc",
        "lang": "typescript",
        "when": "Tracking who is online with timeout-based expiry",
        "why": "Atomic presence: touch/expire loop, online list out, TTL configurable",
        "tags": ["rtc", "presence", "heartbeat", "online", "ttl"],
        "iface": r'''export class Presence {
  constructor(ttlMs?: number)
  touch(userId: string, meta?: Record<string, unknown>): void
  sweep(): string[]
  get online(): Array<{ userId: string; meta?: Record<string, unknown> }>
}''',
        "code": r'''export class Presence {
  private users = new Map<string, { last: number; meta?: Record<string, unknown> }>();
  constructor(private ttlMs = 30000) {}
  touch(userId: string, meta?: Record<string, unknown>) { this.users.set(userId, { last: Date.now(), meta }); }
  sweep() {
    const now = Date.now();
    const gone: string[] = [];
    for (const [id, u] of this.users) if (now - u.last > this.ttlMs) { this.users.delete(id); gone.push(id); }
    return gone;
  }
  get online() {
    this.sweep();
    return [...this.users.entries()].map(([userId, u]) => ({ userId, meta: u.meta }));
  }
}''',
        "provides": "Presence",
        "depends": [],
    },
    {
        "id": "rtc-rooms",
        "name": "Room Membership Manager",
        "category": "rtc",
        "lang": "typescript",
        "when": "Joining/leaving chat rooms and broadcasting to members",
        "why": "Atomic rooms: join/leave/list/broadcast, capacity + duplicates safe",
        "tags": ["rtc", "rooms", "membership", "join", "broadcast"],
        "iface": r'''export class RoomManager<T> {
  constructor(capacityPerRoom?: number)
  join(room: string, member: T): boolean
  leave(room: string, member: T): void
  members(room: string): T[]
  rooms(): string[]
  broadcast(room: string, send: (m: T) => void): void
}''',
        "code": r'''export class RoomManager<T> {
  private roomsMap = new Map<string, T[]>();
  constructor(private capacityPerRoom = 100) {}
  join(room: string, member: T) {
    const list = this.roomsMap.get(room) ?? [];
    if (list.includes(member) || list.length >= this.capacityPerRoom) return false;
    list.push(member);
    this.roomsMap.set(room, list);
    return true;
  }
  leave(room: string, member: T) {
    const list = this.roomsMap.get(room);
    if (!list) return;
    this.roomsMap.set(room, list.filter((m) => m !== member));
  }
  members(room: string) { return (this.roomsMap.get(room) ?? []).slice(); }
  rooms() { return [...this.roomsMap.keys()]; }
  broadcast(room: string, send: (m: T) => void) { for (const m of this.members(room)) send(m); }
}''',
        "provides": "RoomManager",
        "depends": [],
    },
    {
        "id": "rtc-cursors",
        "name": "Live Cursor Broadcast",
        "category": "rtc",
        "lang": "typescript",
        "when": "Showing other users' cursors in collaborative editors",
        "why": "Atomic cursors: per-user position, throttle + expiry, snapshot out",
        "tags": ["rtc", "cursor", "live", "presence", "collab"],
        "iface": r'''export class CursorTracker {
  constructor(expiryMs?: number)
  move(userId: string, pos: { x: number; y: number }, meta?: Record<string, unknown>): void
  prune(): string[]
  get cursors(): Array<{ userId: string; x: number; y: number; meta?: Record<string, unknown> }>
}''',
        "code": r'''export class CursorTracker {
  private map = new Map<string, { x: number; y: number; t: number; meta?: Record<string, unknown> }>();
  constructor(private expiryMs = 15000) {}
  move(userId: string, pos: { x: number; y: number }, meta?: Record<string, unknown>) {
    this.map.set(userId, { x: pos.x, y: pos.y, t: Date.now(), meta });
  }
  prune() {
    const now = Date.now();
    const gone: string[] = [];
    for (const [id, c] of this.map) if (now - c.t > this.expiryMs) { this.map.delete(id); gone.push(id); }
    return gone;
  }
  get cursors() {
    this.prune();
    return [...this.map.entries()].map(([userId, c]) => ({ userId, x: c.x, y: c.y, meta: c.meta }));
  }
}''',
        "provides": "CursorTracker",
        "depends": [],
    },
    {
        "id": "rtc-changelog",
        "name": "Change Log (append + merge)",
        "category": "rtc",
        "lang": "typescript",
        "when": "Syncing ordered changes with dedupe across replicas",
        "why": "Atomic log: append + merge by id, sorted by seq, no duplicates",
        "tags": ["rtc", "changelog", "append", "merge", "sync"],
        "iface": r'''export interface LogEntry { id: string; seq: number; actor: string; op: unknown }
export class ChangeLog {
  constructor()
  append(op: unknown, actor?: string): LogEntry
  merge(entries: LogEntry[]): void
  all(): LogEntry[]
  lastSeq(): number
}''',
        "code": r'''export class ChangeLog {
  private entries = new Map<string, LogEntry>();
  private seq = 0;
  append(op: unknown, actor = 'anon') {
    this.seq++;
    const e: LogEntry = { id: `${actor}:${this.seq}:${Math.random().toString(36).slice(2, 7)}`, seq: this.seq, actor, op };
    this.entries.set(e.id, e);
    return e;
  }
  merge(incoming: LogEntry[]) {
    for (const e of incoming) {
      if (!this.entries.has(e.id)) this.entries.set(e.id, e);
      this.seq = Math.max(this.seq, e.seq);
    }
  }
  all() { return [...this.entries.values()].sort((a, b) => a.seq - b.seq); }
  lastSeq() { return this.seq; }
}''',
        "provides": "ChangeLog",
        "depends": [],
    },
    {
        "id": "rtc-seq-alloc",
        "name": "Sequence Number Allocator",
        "category": "rtc",
        "lang": "typescript",
        "when": "Issuing monotonic order numbers across distributed writers",
        "why": "Atomic allocator: base + increments, monotonic even with missed syncs",
        "tags": ["rtc", "sequence", "allocator", "monotonic", "order"],
        "iface": r'''export class SeqAllocator {
  constructor(start?: number)
  next(): number
  observe(seen: number): void
  get current(): number
}''',
        "code": r'''export class SeqAllocator {
  private cur: number;
  constructor(start = 0) { this.cur = start; }
  next() { return ++this.cur; }
  observe(seen: number) { this.cur = Math.max(this.cur, seen); }
  get current() { return this.cur; }
}''',
        "provides": "SeqAllocator",
        "depends": [],
    },
    {
        "id": "rtc-reconnect",
        "name": "Reconnect with Backoff",
        "category": "rtc",
        "lang": "typescript",
        "when": "Auto-reconnecting websockets with capped exponential delay",
        "why": "Atomic reconnector: connect fn in, backoff + jitter, stop() out",
        "tags": ["rtc", "reconnect", "backoff", "websocket", "retry"],
        "iface": r'''export class Reconnector {
  constructor(connect: () => Promise<void>, opts?: { baseMs?: number; maxMs?: number; maxRetries?: number })
  start(): void
  stop(): void
  reset(): void
  get attempts(): number
}''',
        "code": r'''export class Reconnector {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private _attempts = 0;
  constructor(private connect: () => Promise<void>, private opts: { baseMs?: number; maxMs?: number; maxRetries?: number } = {}) {}
  start() {
    this.stopped = false;
    const attempt = async () => {
      if (this.stopped) return;
      try {
        await this.connect();
        this._attempts = 0;
        if (!this.stopped) this.timer = setTimeout(attempt, this.opts.baseMs ?? 1000);
      } catch {
        this._attempts++;
        if (this.opts.maxRetries && this._attempts >= this.opts.maxRetries) return;
        const delay = Math.min(this.opts.maxMs ?? 30000, (this.opts.baseMs ?? 1000) * 2 ** this._attempts) * (0.8 + Math.random() * 0.4);
        this.timer = setTimeout(attempt, delay);
      }
    };
    void attempt();
  }
  stop() { this.stopped = true; if (this.timer) clearTimeout(this.timer); }
  reset() { this._attempts = 0; }
  get attempts() { return this._attempts; }
}''',
        "provides": "Reconnector",
        "depends": [],
    },
    {
        "id": "rtc-outbox",
        "name": "Outbox with Ack",
        "category": "rtc",
        "lang": "typescript",
        "when": "Reliable message delivery with acknowledgement and resend",
        "why": "Atomic outbox: enqueue/ack/resend unacked, at-least-once semantics",
        "tags": ["rtc", "outbox", "ack", "delivery", "reliable"],
        "iface": "export interface OutboxMessage<T> { id: string; payload: T; sentAt: number }\nexport class Outbox<T> {\n  constructor(retryMs?: number)\n  enqueue(payload: T): OutboxMessage<T>\n  ack(id: string): void\n  pending(retryAfterMs?: number): OutboxMessage<T>[]\n  get size(): number\n}",
        "code": r'''export class Outbox<T> {
  private msgs = new Map<string, OutboxMessage<T>>();
  constructor(private retryMs = 3000) {}
  enqueue(payload: T) {
    const m: OutboxMessage<T> = { id: Math.random().toString(36).slice(2, 12), payload, sentAt: Date.now() };
    this.msgs.set(m.id, m);
    return m;
  }
  ack(id: string) { this.msgs.delete(id); }
  pending(retryAfterMs = this.retryMs) {
    const now = Date.now();
    return [...this.msgs.values()].filter((m) => now - m.sentAt >= retryAfterMs);
  }
  get size() { return this.msgs.size; }
}''',
        "provides": "Outbox",
        "depends": [],
    },
    {
        "id": "rtc-delta-diff",
        "name": "Key-Path Delta Compressor",
        "category": "rtc",
        "lang": "typescript",
        "when": "Sending only changed nested fields instead of whole documents",
        "why": "Atomic diff: two objects in, changed key-paths + values out",
        "tags": ["rtc", "delta", "diff", "compress", "path"],
        "iface": r'''export type DeltaPatch = Array<{ path: string; value: unknown }>
export function diffPaths(before: Record<string, unknown>, after: Record<string, unknown>): DeltaPatch
export function applyPatch(target: Record<string, unknown>, patch: DeltaPatch): Record<string, unknown>''',
        "code": r'''export function diffPaths(before: Record<string, unknown>, after: Record<string, unknown>): DeltaPatch {
  const patch: DeltaPatch = [];
  const walk = (a: Record<string, unknown>, b: Record<string, unknown>, base: string) => {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of keys) {
      const path = base ? `${base}.${k}` : k;
      const av = a[k], bv = b[k];
      if (JSON.stringify(av) === JSON.stringify(bv)) continue;
      if (av && bv && typeof av === 'object' && typeof bv === 'object' && !Array.isArray(av) && !Array.isArray(bv)) {
        walk(av as Record<string, unknown>, bv as Record<string, unknown>, path);
      } else {
        patch.push({ path, value: bv });
      }
    }
  };
  walk(before, after, '');
  return patch;
}
export function applyPatch(target: Record<string, unknown>, patch: DeltaPatch) {
  const out: Record<string, unknown> = JSON.parse(JSON.stringify(target));
  for (const { path, value } of patch) {
    const parts = path.split('.');
    let node = out;
    for (let i = 0; i < parts.length - 1; i++) node = node[parts[i]] as Record<string, unknown>;
    node[parts[parts.length - 1]] = value;
  }
  return out;
}''',
        "provides": "diffPaths / applyPatch",
        "depends": [],
    },
    {
        "id": "rtc-snapshot-sync",
        "name": "Snapshot + Incremental Sync",
        "category": "rtc",
        "lang": "typescript",
        "when": "Bootstrap new peers with a snapshot then stream deltas",
        "why": "Atomic sync: snapshot + deltas in, merged state out with version guard",
        "tags": ["rtc", "snapshot", "sync", "delta", "bootstrap"],
        "iface": r'''export interface SyncState<T> { version: number; data: T }
export function mergeSync<T>(local: SyncState<T>, incoming: SyncState<T> & { deltas?: Array<{ version: number; apply: (d: T) => T }> }): { state: SyncState<T>; applied: number }''',
        "code": r'''export function mergeSync<T>(local: SyncState<T>, incoming: SyncState<T> & { deltas?: Array<{ version: number; apply: (d: T) => T }> }) {
  let data = local.data;
  let applied = 0;
  if (incoming.version > local.version) {
    if (incoming.deltas) {
      for (const d of incoming.deltas) { if (d.version > local.version) { data = d.apply(data); applied++; } }
    } else {
      data = incoming.data;
      applied = 1;
    }
    return { state: { version: Math.max(local.version, incoming.version), data }, applied };
  }
  return { state: local, applied: 0 };
}''',
        "provides": "mergeSync(local, incoming)",
        "depends": [],
    },
    {
        "id": "rtc-sync-scheduler",
        "name": "Bidirectional Sync Scheduler",
        "category": "rtc",
        "lang": "typescript",
        "when": "Coordinating periodic pull/push between local and server",
        "why": "Atomic scheduler: push/pull fns + intervals, backoff on failure, stop() out",
        "tags": ["rtc", "sync", "scheduler", "push", "pull"],
        "iface": r'''export class SyncScheduler {
  constructor(opts: { push: () => Promise<void>; pull: () => Promise<void>; intervalMs?: number; retryBaseMs?: number })
  start(): void
  stop(): void
  syncNow(): Promise<void>
}''',
        "code": r'''export class SyncScheduler {
  private timer: ReturnType<typeof setInterval> | null = null;
  private syncing = false;
  private failures = 0;
  constructor(private opts: { push: () => Promise<void>; pull: () => Promise<void>; intervalMs?: number; retryBaseMs?: number }) {}
  start() {
    if (this.timer) return;
    this.timer = setInterval(() => { void this.syncNow(); }, this.opts.intervalMs ?? 30000);
    void this.syncNow();
  }
  stop() { if (this.timer) { clearInterval(this.timer); this.timer = null; } }
  async syncNow() {
    if (this.syncing) return;
    this.syncing = true;
    try {
      await this.opts.push();
      await this.opts.pull();
      this.failures = 0;
    } catch {
      this.failures++;
    } finally {
      this.syncing = false;
    }
  }
  get failureCount() { return this.failures; }
}''',
        "provides": "SyncScheduler",
        "depends": [],
    },
    {
        "id": "rtc-lamport",
        "name": "Lamport Clock",
        "category": "rtc",
        "lang": "typescript",
        "when": "Ordering events across processes without synchronized clocks",
        "why": "Atomic clock: tick/observe, total order via (time, pid) tuples",
        "tags": ["rtc", "lamport", "clock", "ordering", "distributed"],
        "iface": r'''export class LamportClock {
  constructor(processId?: string)
  tick(): number
  observe(remote: number): void
  timestamp(): { time: number; pid: string }
  get time(): number
}''',
        "code": r'''export class LamportClock {
  private t = 0;
  constructor(private pid = Math.random().toString(36).slice(2, 8)) {}
  tick() { this.t++; return this.t; }
  observe(remote: number) { this.t = Math.max(this.t, remote) + 1; }
  timestamp() { return { time: this.t, pid: this.pid }; }
  get time() { return this.t; }
}''',
        "provides": "LamportClock",
        "depends": [],
    },
    {
        "id": "rtc-sub-filter",
        "name": "Subscriber Topic Filter",
        "category": "rtc",
        "lang": "typescript",
        "when": "Routing messages to subscribers by topic patterns",
        "why": "Atomic filter: wildcard topics, matches, fan-out by pattern",
        "tags": ["rtc", "subscribe", "topic", "filter", "wildcard"],
        "iface": r'''export function topicMatches(pattern: string, topic: string): boolean
export class TopicFilter {
  subscribe(pattern: string, cb: (topic: string, payload: unknown) => void): () => void
  publish(topic: string, payload: unknown): void
}''',
        "code": r'''export function topicMatches(pattern: string, topic: string) {
  const re = new RegExp('^' + pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]+').replace(/#/g, '.*') + '$');
  return re.test(topic);
}
export class TopicFilter {
  private subs: Array<{ pattern: string; cb: (topic: string, payload: unknown) => void }> = [];
  subscribe(pattern: string, cb: (topic: string, payload: unknown) => void) {
    this.subs.push({ pattern, cb });
    return () => { this.subs = this.subs.filter((s) => s.cb !== cb); };
  }
  publish(topic: string, payload: unknown) {
    for (const s of this.subs) if (topicMatches(s.pattern, topic)) s.cb(topic, payload);
  }
}''',
        "provides": "topicMatches / TopicFilter",
        "depends": [],
    },
    {
        "id": "rtc-merge-doc",
        "name": "Field-by-Field Doc Merge",
        "category": "rtc",
        "lang": "typescript",
        "when": "Merging documents with per-field LWW semantics",
        "why": "Atomic merge: field-level resolution + tombstone map, concurrent-safe",
        "tags": ["rtc", "merge", "document", "field", "lww"],
        "iface": "export interface FieldState<T> { value: T; ts: number; actor: string; deleted: boolean }\nexport class DocMerge<T extends Record<string, unknown>> {\n  constructor(actor?: string)\n  setField<K extends keyof T>(key: K, value: T[K]): void\n  deleteField(key: keyof T): void\n  merge(remote: Record<string, FieldState<unknown>>): void\n  getDocument(): Partial<T>\n  snapshot(): Record<string, FieldState<unknown>>\n}",
        "code": r'''export class DocMerge<T extends Record<string, unknown>> {
  private fields = new Map<string, FieldState<unknown>>();
  constructor(private actor = 'anon') {}
  setField<K extends keyof T>(key: K, value: T[K]) {
    this.fields.set(String(key), { value, ts: Date.now(), actor: this.actor, deleted: false });
  }
  deleteField(key: keyof T) {
    const cur = this.fields.get(String(key));
    this.fields.set(String(key), { value: cur?.value, ts: Date.now(), actor: this.actor, deleted: true });
  }
  merge(remote: Record<string, FieldState<unknown>>) {
    for (const [k, r] of Object.entries(remote)) {
      const l = this.fields.get(k);
      if (!l || r.ts > l.ts || (r.ts === l.ts && r.actor > l.actor)) this.fields.set(k, r);
    }
  }
  getDocument() {
    const out: Record<string, unknown> = {};
    for (const [k, f] of this.fields) if (!f.deleted) out[k] = f.value;
    return out as Partial<T>;
  }
  snapshot() { return Object.fromEntries([...this.fields].map(([k, v]) => [k, { ...v }])); }
}''',
        "provides": "DocMerge",
        "depends": [],
    },
    {
        "id": "rtc-ping-pong",
        "name": "WebSocket Keepalive Ping/Pong",
        "category": "rtc",
        "lang": "typescript",
        "when": "Detecting dead connections on idle websockets",
        "why": "Atomic keepalive: interval + timeout, dead detection, cleanup",
        "tags": ["rtc", "ping", "pong", "keepalive", "websocket"],
        "iface": r'''export function keepalive(opts: { ping: () => void; isAlive: () => boolean; onDead: () => void; intervalMs?: number; timeoutMs?: number }): () => void''',
        "code": r'''export function keepalive(opts: { ping: () => void; isAlive: () => boolean; onDead: () => void; intervalMs?: number; timeoutMs?: number }) {
  let lastPong = Date.now();
  const check = setInterval(() => {
    if (Date.now() - lastPong > (opts.timeoutMs ?? 30000) || !opts.isAlive()) { opts.onDead(); return; }
    opts.ping();
  }, opts.intervalMs ?? 15000);
  const mark = () => { lastPong = Date.now(); };
  // Caller invokes mark() on pong message.
  return () => clearInterval(check);
}''',
        "provides": "keepalive(opts)",
        "depends": [],
    },
    {
        "id": "rtc-ewma-clock",
        "name": "Server Clock Offset Estimator",
        "category": "rtc",
        "lang": "typescript",
        "when": "Estimating the skew between client and server clocks",
        "why": "Atomic estimator: round-trip samples in, median offset + RTT out",
        "tags": ["rtc", "clock", "offset", "skew", "ntp"],
        "iface": r'''export class ClockOffset {
  constructor(samples?: number)
  observe(sent: number, serverTime: number, received: number): void
  get offsetMs(): number
  get rttMs(): number
  estimateServerNow(): number
}''',
        "code": r'''export class ClockOffset {
  private offsets: number[] = [];
  private rtts: number[] = [];
  constructor(private maxSamples = 20) {}
  observe(sent: number, serverTime: number, received: number) {
    const rtt = received - sent;
    this.offsets.push(serverTime - (sent + received) / 2);
    this.rtts.push(rtt);
    if (this.offsets.length > this.maxSamples) { this.offsets.shift(); this.rtts.shift(); }
  }
  private median(arr: number[]) { const s = [...arr].sort((a, b) => a - b); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; }
  get offsetMs() { return this.offsets.length ? this.median(this.offsets) : 0; }
  get rttMs() { return this.rtts.length ? this.median(this.rtts) : 0; }
  estimateServerNow() { return Date.now() + this.offsetMs; }
}''',
        "provides": "ClockOffset",
        "depends": [],
    },
    {
        "id": "rtc-rate-limiter-dist",
        "name": "Distributed Rate Limiter Key",
        "category": "rtc",
        "lang": "typescript",
        "when": "Building distributed rate limit keys that are load-balancer safe",
        "why": "Atomic keying: consistent hash of client identity, window-bucketed",
        "tags": ["rtc", "rate", "limit", "distributed", "key"],
        "iface": r'''export function rateLimitKey(identity: string, windowMs: number): string
export function consistentBucket(identity: string, buckets: number): number''',
        "code": r'''export function rateLimitKey(identity: string, windowMs: number) {
  const bucket = Math.floor(Date.now() / windowMs);
  return `${identity}:${bucket}`;
}
export function consistentBucket(identity: string, buckets: number) {
  let h = 2166136261;
  for (let i = 0; i < identity.length; i++) { h ^= identity.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) % buckets;
}''',
        "provides": "rateLimitKey / consistentBucket",
        "depends": [],
    },
    {
        "id": "rtc-broadcast-channel",
        "name": "Tab Broadcast Channel",
        "category": "rtc",
        "lang": "typescript",
        "when": "Syncing state between browser tabs of the same app",
        "why": "Atomic channel: post/sub with source filter, cleanup on unsubscribe",
        "tags": ["rtc", "broadcast", "channel", "tabs", "sync"],
        "iface": r'''export class TabChannel {
  constructor(name?: string)
  post(message: unknown): void
  subscribe(cb: (message: unknown, origin: string) => void): () => void
  close(): void
}''',
        "code": r'''export class TabChannel {
  private channel: BroadcastChannel | null;
  constructor(name = 'app-sync') {
    this.channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(name) : null;
  }
  post(message: unknown) { this.channel?.postMessage(message); }
  subscribe(cb: (message: unknown, origin: string) => void) {
    if (!this.channel) return () => {};
    const handler = (e: MessageEvent) => cb(e.data, e.origin);
    this.channel.addEventListener('message', handler);
    return () => this.channel?.removeEventListener('message', handler);
  }
  close() { this.channel?.close(); }
}''',
        "provides": "TabChannel",
        "depends": [],
    },
    {
        "id": "rtc-retry-queue",
        "name": "Retry Outbox (persisted)",
        "category": "rtc",
        "lang": "typescript",
        "when": "Persisting unsent messages across page reloads",
        "why": "Atomic queue: enqueue/send/settle, injected persistence, attempts per message",
        "tags": ["rtc", "retry", "queue", "persist", "outbox"],
        "iface": r'''export interface RetryItem<T> { id: string; payload: T; attempts: number; nextTryAt: number }
export class RetryOutbox<T> {
  constructor(store?: { load: () => RetryItem<T>[]; save: (q: RetryItem<T>[]) => void }, maxAttempts?: number)
  enqueue(payload: T): void
  send(sender: (item: RetryItem<T>) => Promise<void>): Promise<number>
  get pending(): RetryItem<T>[]
}''',
        "code": r'''export class RetryOutbox<T> {
  private queue: RetryItem<T>[] = [];
  constructor(private store?: { load: () => RetryItem<T>[]; save: (q: RetryItem<T>[]) => void }, private maxAttempts = 5) {
    this.queue = store?.load() ?? [];
  }
  private persist() { this.store?.save(this.queue); }
  enqueue(payload: T) {
    this.queue.push({ id: Math.random().toString(36).slice(2, 12), payload, attempts: 0, nextTryAt: 0 });
    this.persist();
  }
  async send(sender: (item: RetryItem<T>) => Promise<void>) {
    const due = this.queue.filter((q) => q.nextTryAt <= Date.now());
    let sent = 0;
    for (const item of due) {
      try {
        await sender(item);
        this.queue = this.queue.filter((q) => q.id !== item.id);
        sent++;
      } catch {
        item.attempts++;
        item.nextTryAt = Date.now() + 1000 * 2 ** item.attempts;
        if (item.attempts >= this.maxAttempts) this.queue = this.queue.filter((q) => q.id !== item.id);
      }
    }
    this.persist();
    return sent;
  }
  get pending() { return this.queue.slice(); }
}''',
        "provides": "RetryOutbox",
        "depends": [],
    },
    {
        "id": "rtc-sync-state",
        "name": "Sync State Machine",
        "category": "rtc",
        "lang": "typescript",
        "when": "Tracking whether the client is in sync, syncing, or behind",
        "why": "Atomic FSM: idle/syncing/behind/error transitions, event callbacks",
        "tags": ["rtc", "sync", "state", "machine", "status"],
        "iface": r'''export type SyncStatus = 'idle' | 'syncing' | 'behind' | 'error'
export class SyncStateMachine {
  constructor(onChange?: (s: SyncStatus) => void)
  beginSync(): void
  syncComplete(): void
  markBehind(): void
  markError(): void
  get status(): SyncStatus
}''',
        "code": r'''export class SyncStateMachine {
  private _status: SyncStatus = 'idle';
  constructor(private onChange?: (s: SyncStatus) => void) {}
  private set(status: SyncStatus) { this._status = status; this.onChange?.(status); }
  beginSync() { this.set('syncing'); }
  syncComplete() { this.set('idle'); }
  markBehind() { this.set('behind'); }
  markError() { this.set('error'); }
  get status() { return this._status; }
}''',
        "provides": "SyncStateMachine",
        "depends": [],
    },
    {
        "id": "rtc-fanout",
        "name": "Broadcast Fan-Out Helper",
        "category": "rtc",
        "lang": "typescript",
        "when": "Delivering a message to all connected clients without blocking",
        "why": "Atomic fan-out: list + send fn in, per-client try/catch, error summary out",
        "tags": ["rtc", "broadcast", "fanout", "delivery", "send"],
        "iface": r'''export async function fanOut<T>(clients: T[], send: (client: T) => Promise<void>): Promise<{ ok: number; failed: number }>''',
        "code": r'''export async function fanOut<T>(clients: T[], send: (client: T) => Promise<void>) {
  const results = await Promise.allSettled(clients.map((c) => send(c)));
  return { ok: results.filter((r) => r.status === 'fulfilled').length, failed: results.filter((r) => r.status === 'rejected').length };
}''',
        "provides": "fanOut(clients, send)",
        "depends": [],
    },
    {
        "id": "rtc-gossip",
        "name": "Gossip Merge Loop",
        "category": "rtc",
        "lang": "typescript",
        "when": "Eventually-consistent state propagation to random peers",
        "why": "Atomic gossip: local state in, random-peer exchange + merge, rounds out",
        "tags": ["rtc", "gossip", "merge", "eventual", "peers"],
        "iface": r'''export class GossipState<T> {
  constructor(merge: (a: T, b: T) => T)
  update(local: T): void
  exchange(peerState: T): T
  get state(): T
}''',
        "code": r'''export class GossipState<T> {
  private s: T;
  constructor(private merge: (a: T, b: T) => T, initial: T) { this.s = initial; }
  update(local: T) { this.s = local; }
  exchange(peerState: T) { const before = this.s; this.s = this.merge(this.s, peerState); return before; }
  get state() { return this.s; }
}''',
        "provides": "GossipState",
        "depends": [],
    },
]
