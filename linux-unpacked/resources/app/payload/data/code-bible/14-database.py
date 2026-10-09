# -*- coding: utf-8 -*-
"""
Code Bible — Category 14: Database & persistence (atomic, single-responsibility).
Convention: pure SQL builders and in-memory store helpers; no driver-specific code.
"""
CHUNKS = [
    {
        "id": "db-param-builder",
        "name": "SQL Parameter Builder",
        "category": "db",
        "lang": "typescript",
        "when": "Building parameterized SQL so user input can never inject SQL",
        "why": "Atomic builder: values in, placeholders + ordered params out — injection-safe",
        "tags": ["db", "sql", "parameter", "injection", "safe"],
        "iface": r'''export function paramSql(parts: string[], values: unknown[]): { sql: string; params: unknown[] }''',
        "code": r'''export function paramSql(parts: string[], values: unknown[]) {
  const params: unknown[] = [];
  const sql = parts.map((p, i) => {
    if (i === parts.length - 1) return p;
    params.push(values[i]);
    return p + `$${params.length}`;
  }).join('');
  return { sql, params };
}''',
        "provides": "paramSql(parts, values)",
        "depends": [],
    },
    {
        "id": "db-keyset-paginate",
        "name": "Keyset Pagination",
        "category": "db",
        "lang": "typescript",
        "when": "Paging large tables without OFFSET drift using a last-seen cursor",
        "why": "Atomic paginator: cursor + size in, WHERE clause + next cursor out",
        "tags": ["db", "pagination", "keyset", "cursor", "query"],
        "iface": r'''export interface KeysetCursor { key: string | number; id: string }
export function keysetWhere(cursor: KeysetCursor | null, size: number, orderCol = 'created_at'): { where: string; params: unknown[]; next: KeysetCursor | null }''',
        "code": r'''export function keysetWhere(cursor: KeysetCursor | null, size: number, orderCol = 'created_at') {
  if (!cursor) return { where: `ORDER BY ${orderCol} ASC LIMIT $1`, params: [size], next: null };
  return {
    where: `WHERE (${orderCol}, id) > ($1, $2) ORDER BY ${orderCol} ASC LIMIT $3`,
    params: [cursor.key, cursor.id, size],
    next: cursor,
  };
}''',
        "provides": "keysetWhere(cursor, size, orderCol)",
        "depends": [],
    },
    {
        "id": "db-memory-table",
        "name": "In-Memory Table Store",
        "category": "db",
        "lang": "typescript",
        "when": "CRUD over a typed collection without a real database",
        "why": "Atomic store: insert/find/update/delete by id, optional secondary index",
        "tags": ["db", "memory", "store", "crud", "table"],
        "iface": r'''export class MemoryTable<T extends { id: string }> {
  constructor(indexKeys?: Array<keyof T>)
  insert(row: T): T
  get(id: string): T | undefined
  update(id: string, patch: Partial<T>): T | undefined
  delete(id: string): boolean
  find(predicate: (row: T) => boolean): T[]
  all(): T[]
}''',
        "code": r'''export class MemoryTable<T extends { id: string }> {
  private rows = new Map<string, T>();
  constructor(private indexKeys: Array<keyof T> = []) {}
  insert(row: T) { this.rows.set(row.id, row); return row; }
  get(id: string) { return this.rows.get(id); }
  update(id: string, patch: Partial<T>) {
    const cur = this.rows.get(id);
    if (!cur) return undefined;
    const next = { ...cur, ...patch };
    this.rows.set(id, next);
    return next;
  }
  delete(id: string) { return this.rows.delete(id); }
  find(predicate: (row: T) => boolean) { return [...this.rows.values()].filter(predicate); }
  all() { return [...this.rows.values()]; }
}''',
        "provides": "MemoryTable",
        "depends": [],
    },
    {
        "id": "db-transaction-wrap",
        "name": "Transaction Wrapper",
        "category": "db",
        "lang": "typescript",
        "when": "Running a unit of work atomically with commit or rollback",
        "why": "Atomic wrapper: begin/commit/rollback callbacks in, all-or-nothing out",
        "tags": ["db", "transaction", "atomic", "commit", "rollback"],
        "iface": r'''export interface TransactionAdapter {
  begin(): Promise<void>; commit(): Promise<void>; rollback(): Promise<void>
}
export async function withTransaction<T>(adapter: TransactionAdapter, work: () => Promise<T>): Promise<T>''',
        "code": r'''export async function withTransaction<T>(adapter: TransactionAdapter, work: () => Promise<T>) {
  await adapter.begin();
  try {
    const result = await work();
    await adapter.commit();
    return result;
  } catch (e) {
    try { await adapter.rollback(); } catch { /* rollback failed too */ }
    throw e;
  }
}''',
        "provides": "withTransaction(adapter, work)",
        "depends": [],
    },
    {
        "id": "db-migration-runner",
        "name": "Versioned Migration Runner",
        "category": "db",
        "lang": "typescript",
        "when": "Applying only the not-yet-run migrations in version order",
        "why": "Atomic runner: migrations + applied set in, newly applied list out",
        "tags": ["db", "migration", "version", "schema", "apply"],
        "iface": r'''export interface Migration { version: number; name: string; up: () => Promise<void> }
export async function runMigrations(migrations: Migration[], applied: Set<number>): Promise<Migration[]>''',
        "code": r'''export async function runMigrations(migrations: Migration[], applied: Set<number>) {
  const pending = migrations
    .filter((m) => !applied.has(m.version))
    .sort((a, b) => a.version - b.version);
  for (const m of pending) await m.up();
  return pending;
}''',
        "provides": "runMigrations(migrations, applied)",
        "depends": [],
    },
    {
        "id": "db-upsert-builder",
        "name": "Upsert SQL Builder",
        "category": "db",
        "lang": "typescript",
        "when": "Inserting or updating a row in one statement",
        "why": "Atomic builder: table + row + conflict key in, ON CONFLICT SQL out",
        "tags": ["db", "upsert", "sql", "insert", "conflict"],
        "iface": r'''export function upsertSql(table: string, row: Record<string, unknown>, conflictKey: string): { sql: string; params: unknown[] }''',
        "code": r'''export function upsertSql(table: string, row: Record<string, unknown>, conflictKey: string) {
  const keys = Object.keys(row);
  const params: unknown[] = [];
  const cols = keys.join(', ');
  const placeholders = keys.map((k, i) => { params.push(row[k]); return `$${i + 1}`; }).join(', ');
  const updates = keys
    .filter((k) => k !== conflictKey)
    .map((k) => { params.push(row[k]); return `${k} = $${params.length}`; })
    .join(', ');
  const sql = `INSERT INTO ${table} (${cols}) VALUES (${placeholders}) ON CONFLICT (${conflictKey}) DO UPDATE SET ${updates || conflictKey} = EXCLUDED.${conflictKey}`;
  return { sql, params };
}''',
        "provides": "upsertSql(table, row, conflictKey)",
        "depends": [],
    },
    {
        "id": "db-where-builder",
        "name": "WHERE Clause Builder",
        "category": "db",
        "lang": "typescript",
        "when": "Composing AND/OR filters with bound parameters",
        "why": "Atomic builder: filter map in, WHERE + params out, empty → no clause",
        "tags": ["db", "where", "sql", "filter", "builder"],
        "iface": r'''export interface WhereFilter { [col: string]: unknown | { gt?: unknown; lt?: unknown; like?: string; in?: unknown[] } }
export function buildWhere(filter: WhereFilter, startAt = 1): { clause: string; params: unknown[] }''',
        "code": r'''export function buildWhere(filter: WhereFilter, startAt = 1) {
  const params: unknown[] = [];
  const conds: string[] = [];
  for (const [col, spec] of Object.entries(filter)) {
    if (spec === undefined) continue;
    if (typeof spec === 'object' && spec !== null && !Array.isArray(spec) && !(spec instanceof Date)) {
      const s = spec as Record<string, unknown>;
      for (const op of ['gt', 'lt', 'like', 'in'] as const) {
        if (s[op] === undefined) continue;
        params.push(s[op]);
        conds.push(op === 'like' ? `${col} ILIKE $${params.length}` : `${col} ${op === 'gt' ? '>' : op === 'lt' ? '<' : op === 'in' ? '= ANY' : ''} $${params.length}`);
      }
    } else {
      params.push(spec);
      conds.push(`${col} = $${params.length}`);
    }
  }
  return { clause: conds.length ? `WHERE ${conds.join(' AND ')}` : '', params };
}''',
        "provides": "buildWhere(filter, startAt)",
        "depends": [],
    },
    {
        "id": "db-result-mapper",
        "name": "Row → Object Mapper",
        "category": "db",
        "lang": "typescript",
        "when": "Converting snake_case DB rows to camelCase domain objects",
        "why": "Atomic mapper: row + rename map in, typed object out, unknown cols dropped",
        "tags": ["db", "mapper", "row", "object", "snake-case"],
        "iface": r'''export function mapRow<T>(row: Record<string, unknown>, rename?: Record<string, keyof T>): T''',
        "code": r'''export function mapRow<T>(row: Record<string, unknown>, rename?: Record<string, keyof T>) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) {
    const key = rename?.[k] ?? k.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
    out[String(key)] = v;
  }
  return out as T;
}''',
        "provides": "mapRow(row, rename)",
        "depends": [],
    },
    {
        "id": "db-batch-insert",
        "name": "Batch Inserter",
        "category": "db",
        "lang": "typescript",
        "when": "Inserting many rows in chunked multi-value statements",
        "why": "Atomic inserter: rows + chunk size in, per-chunk statements out",
        "tags": ["db", "batch", "insert", "chunk", "bulk"],
        "iface": r'''export function batchInsertSql(table: string, rows: Array<Record<string, unknown>>, chunkSize = 100): Array<{ sql: string; params: unknown[] }>''',
        "code": r'''export function batchInsertSql(table: string, rows: Array<Record<string, unknown>>, chunkSize = 100) {
  const cols = Object.keys(rows[0] ?? {});
  const out: Array<{ sql: string; params: unknown[] }> = [];
  for (let c = 0; c < rows.length; c += chunkSize) {
    const chunk = rows.slice(c, c + chunkSize);
    const params: unknown[] = [];
    const valueGroups = chunk.map((row) => {
      const placeholders = cols.map((col) => { params.push(row[col]); return `$${params.length}`; });
      return `(${placeholders.join(', ')})`;
    });
    out.push({ sql: `INSERT INTO ${table} (${cols.join(', ')}) VALUES ${valueGroups.join(', ')}`, params });
  }
  return out;
}''',
        "provides": "batchInsertSql(table, rows, chunkSize)",
        "depends": [],
    },
    {
        "id": "db-group-agg",
        "name": "In-Memory Group Aggregator",
        "category": "db",
        "lang": "typescript",
        "when": "Grouping rows by key and aggregating without SQL",
        "why": "Atomic aggregator: rows + key + reducer in, grouped results out",
        "tags": ["db", "group", "aggregate", "reduce", "groupby"],
        "iface": r'''export function groupBy<T, K extends string | number>(rows: T[], key: (r: T) => K): Map<K, T[]>
export function summarize<T>(rows: T[], key: (r: T) => string, pick: (r: T) => number, mode?: 'sum' | 'avg' | 'max' | 'min'): Map<string, number>''',
        "code": r'''export function groupBy<T, K extends string | number>(rows: T[], key: (r: T) => K) {
  const out = new Map<K, T[]>();
  for (const r of rows) {
    const k = key(r);
    if (!out.has(k)) out.set(k, []);
    out.get(k)!.push(r);
  }
  return out;
}
export function summarize<T>(rows: T[], key: (r: T) => string, pick: (r: T) => number, mode: 'sum' | 'avg' | 'max' | 'min' = 'sum') {
  const grouped = groupBy(rows, key);
  const out = new Map<string, number>();
  for (const [k, rs] of grouped) {
    const vals = rs.map(pick);
    let v = vals[0];
    for (const x of vals.slice(1)) {
      if (mode === 'sum') v += x;
      else if (mode === 'max') v = Math.max(v, x);
      else if (mode === 'min') v = Math.min(v, x);
      else v += x;
    }
    out.set(k, mode === 'avg' ? v / vals.length : v);
  }
  return out;
}''',
        "provides": "groupBy / summarize",
        "depends": [],
    },
    {
        "id": "db-json-filter",
        "name": "JSON Column Filter",
        "category": "db",
        "lang": "typescript",
        "when": "Filtering rows by a value nested inside a JSON field",
        "why": "Atomic filter: path + expected in, predicate out — works on parsed JSON, not SQL",
        "tags": ["db", "json", "filter", "nested", "query"],
        "iface": r'''export function jsonPath<T>(obj: T, path: string): unknown
export function jsonFilter<T>(rows: T[], path: string, expected: unknown): T[]''',
        "code": r'''export function jsonPath<T>(obj: T, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) =>
    (acc && typeof acc === 'object' ? (acc as Record<string, unknown>)[key] : undefined), obj);
}
export function jsonFilter<T>(rows: T[], path: string, expected: unknown) {
  return rows.filter((r) => jsonPath(r, path) === expected);
}''',
        "provides": "jsonPath / jsonFilter",
        "depends": [],
    },
    {
        "id": "db-snapshot-store",
        "name": "JSON Snapshot Store",
        "category": "db",
        "lang": "typescript",
        "when": "Persisting and restoring an object graph as JSON with atomic writes",
        "why": "Atomic snapshot: load/save with version + timestamp, corrupt-file safe load",
        "tags": ["db", "snapshot", "json", "persist", "store"],
        "iface": r'''export interface SnapshotStore<T> {
  load(): Promise<T | null>
  save(data: T): Promise<void>
  exists(): Promise<boolean>
}
export function createSnapshotStore<T>(opts: { read: () => Promise<string>; write: (s: string) => Promise<void> }): SnapshotStore<T>''',
        "code": r'''export function createSnapshotStore<T>(opts: { read: () => Promise<string>; write: (s: string) => Promise<void> }): SnapshotStore<T> {
  return {
    async load() {
      try { return JSON.parse(await opts.read()) as T; } catch { return null; }
    },
    async save(data) { await opts.write(JSON.stringify(data, null, 2)); },
    async exists() { try { await opts.read(); return true; } catch { return false; } },
  };
}''',
        "provides": "createSnapshotStore(opts)",
        "depends": [],
    },
    {
        "id": "db-replica-router",
        "name": "Read-Replica Router",
        "category": "db",
        "lang": "typescript",
        "when": "Sending reads to replicas and writes to the primary",
        "why": "Atomic router: method in, endpoint out, explicit replica list + sticky option",
        "tags": ["db", "replica", "router", "read", "write"],
        "iface": r'''export class ReplicaRouter {
  constructor(primary: string, replicas: string[], sticky?: boolean)
  route(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'): string
  resetSticky(): void
}''',
        "code": r'''export class ReplicaRouter {
  private idx = 0;
  private stickyTo = -1;
  constructor(private primary: string, private replicas: string[], private sticky = false) {}
  route(method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE') {
    if (method !== 'GET') { this.stickyTo = -1; return this.primary; }
    if (this.sticky && this.stickyTo >= 0) return this.replicas[this.stickyTo];
    if (!this.replicas.length) return this.primary;
    const i = this.idx++ % this.replicas.length;
    if (this.sticky) this.stickyTo = i;
    return this.replicas[i];
  }
  resetSticky() { this.stickyTo = -1; }
}''',
        "provides": "ReplicaRouter",
        "depends": [],
    },
    {
        "id": "db-migration-stamp",
        "name": "Idempotent Migration Stamp",
        "category": "db",
        "lang": "typescript",
        "when": "Marking a migration applied exactly once even if retried",
        "why": "Atomic stamp: version + set in, boolean out — no double apply possible",
        "tags": ["db", "migration", "stamp", "idempotent", "version"],
        "iface": r'''export function stampApplied(version: number, applied: Set<number>): boolean''',
        "code": r'''export function stampApplied(version: number, applied: Set<number>) {
  if (applied.has(version)) return false;
  applied.add(version);
  return true;
}''',
        "provides": "stampApplied(version, applied)",
        "depends": [],
    },
    {
        "id": "db-soft-delete",
        "name": "Soft-Delete Helper",
        "category": "db",
        "lang": "typescript",
        "when": "Marking rows deleted without removing them",
        "why": "Atomic helper: row in, deleted_at-stamped clone out + visibility predicate",
        "tags": ["db", "soft", "delete", "archive", "timestamp"],
        "iface": r'''export function softDelete<T extends Record<string, unknown>>(row: T, at = new Date()): T & { deleted_at: Date }
export function isDeleted(row: Record<string, unknown>): boolean''',
        "code": r'''export function softDelete<T extends Record<string, unknown>>(row: T, at = new Date()) {
  return { ...row, deleted_at: at } as T & { deleted_at: Date };
}
export function isDeleted(row: Record<string, unknown>) {
  return row.deleted_at !== undefined && row.deleted_at !== null;
}''',
        "provides": "softDelete / isDeleted",
        "depends": [],
    },
    {
        "id": "db-audit-columns",
        "name": "Audit Column Updater",
        "category": "db",
        "lang": "typescript",
        "when": "Stamping created_at/updated_at/by fields on writes",
        "why": "Atomic stamper: row + actor in, timestamped clone out, no DB coupling",
        "tags": ["db", "audit", "columns", "timestamp", "created-at"],
        "iface": r'''export interface AuditContext { actor?: string; now?: Date }
export function withAudit<T extends Record<string, unknown>>(row: T, opts?: AuditContext): T''',
        "code": r'''export function withAudit<T extends Record<string, unknown>>(row: T, opts: AuditContext = {}) {
  const now = opts.now ?? new Date();
  const actor = opts.actor ?? null;
  const isNew = row.created_at === undefined;
  return {
    ...row,
    ...(isNew ? { created_at: now, created_by: actor } : {}),
    updated_at: now,
    updated_by: actor,
  };
}''',
        "provides": "withAudit(row, opts)",
        "depends": [],
    },
    {
        "id": "db-counter-inc",
        "name": "Counter Table Incrementer",
        "category": "db",
        "lang": "typescript",
        "when": "Atomically incrementing a numeric counter keyed by name",
        "why": "Atomic counter: name + delta in, new value out with initial default",
        "tags": ["db", "counter", "increment", "atomic", "sequence"],
        "iface": r'''export class NamedCounter {
  constructor(seed?: Record<string, number>)
  inc(name: string, by?: number): number
  get(name: string): number
  snapshot(): Record<string, number>
}''',
        "code": r'''export class NamedCounter {
  private counts: Record<string, number>;
  constructor(seed: Record<string, number> = {}) { this.counts = { ...seed }; }
  inc(name: string, by = 1) { this.counts[name] = (this.counts[name] ?? 0) + by; return this.counts[name]; }
  get(name: string) { return this.counts[name] ?? 0; }
  snapshot() { return { ...this.counts }; }
}''',
        "provides": "NamedCounter",
        "depends": [],
    },
    {
        "id": "db-schema-diff",
        "name": "Column Schema Diff",
        "category": "db",
        "lang": "typescript",
        "when": "Detecting added/removed/changed columns between two schemas",
        "why": "Atomic differ: two column maps in, add/remove/change lists out",
        "tags": ["db", "schema", "diff", "columns", "migration"],
        "iface": r'''export interface SchemaColumn { name: string; type: string; nullable?: boolean }
export function schemaDiff(before: SchemaColumn[], after: SchemaColumn[]): { added: SchemaColumn[]; removed: SchemaColumn[]; changed: Array<{ name: string; from: string; to: string }> }''',
        "code": r'''export function schemaDiff(before: SchemaColumn[], after: SchemaColumn[]) {
  const b = new Map(before.map((c) => [c.name, c]));
  const a = new Map(after.map((c) => [c.name, c]));
  const added = after.filter((c) => !b.has(c.name));
  const removed = before.filter((c) => !a.has(c.name));
  const changed = after
    .filter((c) => b.has(c.name) && (b.get(c.name)!.type !== c.type || b.get(c.name)!.nullable !== c.nullable))
    .map((c) => ({ name: c.name, from: `${b.get(c.name)!.type}${b.get(c.name)!.nullable ? '?' : ''}`, to: `${c.type}${c.nullable ? '?' : ''}` }));
  return { added, removed, changed };
}''',
        "provides": "schemaDiff(before, after)",
        "depends": [],
    },
    {
        "id": "db-query-logger",
        "name": "Query Logger",
        "category": "db",
        "lang": "typescript",
        "when": "Logging slow queries with duration and params redaction",
        "why": "Atomic logger: query + ms + params in, formatted line out, secret-safe",
        "tags": ["db", "query", "log", "slow", "duration"],
        "iface": r'''export function logQuery(opts: { sql: string; ms: number; params?: unknown[]; thresholdMs?: number; redact?: string[] }): string | null''',
        "code": r'''export function logQuery(opts: { sql: string; ms: number; params?: unknown[]; thresholdMs?: number; redact?: string[] }) {
  if (opts.ms < (opts.thresholdMs ?? 0)) return null;
  const params = (opts.params ?? []).map((p) => {
    const s = typeof p === 'string' ? p : JSON.stringify(p);
    return opts.redact?.some((k) => s.includes(k)) ? '***' : s;
  });
  return `[db ${opts.ms.toFixed(1)}ms] ${opts.sql.replace(/\s+/g, ' ').trim()} ${params.length ? `-- ${params.join(', ')}` : ''}`;
}''',
        "provides": "logQuery(opts)",
        "depends": [],
    },
    {
        "id": "db-explain-format",
        "name": "EXPLAIN Plan Formatter",
        "category": "db",
        "lang": "typescript",
        "when": "Turning raw EXPLAIN rows into a readable indented tree",
        "why": "Atomic formatter: plan rows in, tree-text out, costs annotated",
        "tags": ["db", "explain", "plan", "format", "query"],
        "iface": r'''export interface ExplainRow { 'QUERY PLAN': string }
export function formatExplain(rows: ExplainRow[]): string''',
        "code": r'''export function formatExplain(rows: ExplainRow[]) {
  return rows.map((r) => {
    const line = r['QUERY PLAN'];
    const indent = line.match(/^\s*/)?.[0].length ?? 0;
    const cost = line.match(/cost=([\d.]+\.\.[\d.]+)/)?.[1];
    return '  '.repeat(indent) + line.trim() + (cost ? `  [cost=${cost}]` : '');
  }).join('\n');
}''',
        "provides": "formatExplain(rows)",
        "depends": [],
    },
    {
        "id": "db-connection-retry",
        "name": "Connection Retry Pool",
        "category": "db",
        "lang": "typescript",
        "when": "Handing out pooled connections and retrying acquisition on failure",
        "why": "Atomic pool: acquire/release callbacks, bounded retries, queue under pressure",
        "tags": ["db", "pool", "connection", "retry", "acquire"],
        "iface": r'''export class ConnectionPool<T> {
  constructor(opts: { create: () => Promise<T>; max: number; acquireRetries?: number })
  withConnection<R>(fn: (conn: T) => Promise<R>): Promise<R>
  drain(): Promise<void>
}''',
        "code": r'''export class ConnectionPool<T> {
  private free: T[] = [];
  private inUse = 0;
  private waiters: Array<(c: T) => void> = [];
  constructor(private opts: { create: () => Promise<T>; max: number; acquireRetries?: number }) {}
  private async acquire(): Promise<T> {
    for (let attempt = 0; ; attempt++) {
      if (this.free.length) return this.free.pop()!;
      if (this.inUse < this.opts.max) { this.inUse++; return this.opts.create(); }
      if (attempt >= (this.opts.acquireRetries ?? 5)) throw new Error('Pool exhausted');
      await new Promise((r) => setTimeout(r, 50));
    }
  }
  private release(conn: T) { this.inUse--; this.free.push(conn); }
  async withConnection<R>(fn: (conn: T) => Promise<R>) {
    const conn = await this.acquire();
    try { return await fn(conn); } finally { this.release(conn); }
  }
  async drain() { this.free = []; }
}''',
        "provides": "ConnectionPool",
        "depends": [],
    },
    {
        "id": "db-fulltext-tokenize",
        "name": "Full-Text Tokenizer",
        "category": "db",
        "lang": "typescript",
        "when": "Preparing searchable tokens with stemming-lite and stopwords",
        "why": "Atomic tokenizer: text in, normalized unique tokens out with positions",
        "tags": ["db", "fulltext", "tokenize", "search", "stopwords"],
        "iface": r'''export interface SearchToken { term: string; position: number }
export function tokenizeForSearch(text: string, stopwords?: Set<string>): SearchToken[]''',
        "code": r'''const DEFAULT_STOP = new Set('a an and are as at be but by for from has he her his in is it its of on or that the their they this to was were will with'.split(' '));
export function tokenizeForSearch(text: string, stopwords = DEFAULT_STOP) {
  const words = text.toLowerCase().match(/[a-z0-9']+/g) ?? [];
  const out: SearchToken[] = [];
  words.forEach((raw, i) => {
    const term = raw.replace(/'s$/, '').slice(0, 24);
    if (term.length > 1 && !stopwords.has(term)) out.push({ term, position: i });
  });
  return out;
}''',
        "provides": "tokenizeForSearch(text, stopwords)",
        "depends": [],
    },
    {
        "id": "db-query-throttle",
        "name": "Query Throttle / Debounce",
        "category": "db",
        "lang": "typescript",
        "when": "Coalescing rapid identical queries into one execution",
        "why": "Atomic debouncer: key + fn in, single shared promise out per window",
        "tags": ["db", "query", "throttle", "debounce", "cache"],
        "iface": r'''export class QueryDebouncer {
  constructor(windowMs?: number)
  run<T>(key: string, fn: () => Promise<T>): Promise<T>
  invalidate(key?: string): void
}''',
        "code": r'''export class QueryDebouncer {
  private pending = new Map<string, Promise<unknown>>();
  private last = new Map<string, number>();
  constructor(private windowMs = 1000) {}
  run<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const now = Date.now();
    const last = this.last.get(key);
    if (last !== undefined && now - last < this.windowMs && this.pending.has(key)) {
      return this.pending.get(key) as Promise<T>;
    }
    this.last.set(key, now);
    const p = fn().finally(() => { this.pending.delete(key); });
    this.pending.set(key, p);
    return p;
  }
  invalidate(key?: string) {
    if (key) { this.pending.delete(key); this.last.delete(key); }
    else { this.pending.clear(); this.last.clear(); }
  }
}''',
        "provides": "QueryDebouncer",
        "depends": [],
    },
    {
        "id": "db-order-builder",
        "name": "ORDER BY Builder (allowlist)",
        "category": "db",
        "lang": "typescript",
        "when": "Sorting query results by user-supplied columns without injection",
        "why": "Atomic builder: requested + allowed columns in, safe ORDER BY out",
        "tags": ["db", "order", "sort", "allowlist", "sql"],
        "iface": r'''export function buildOrderBy(sort: string | undefined, allowed: string[], defaultOrder = 'id ASC'): string''',
        "code": r'''export function buildOrderBy(sort: string | undefined, allowed: string[], defaultOrder = 'id ASC') {
  if (!sort) return defaultOrder;
  const [col, dir] = sort.split(/\s+/, 2);
  if (!allowed.includes(col)) return defaultOrder;
  const safeDir = dir?.toUpperCase() === 'DESC' ? 'DESC' : 'ASC';
  return `${col} ${safeDir}`;
}''',
        "provides": "buildOrderBy(sort, allowed, defaultOrder)",
        "depends": [],
    },
    {
        "id": "db-cursor-codec",
        "name": "Opaque Cursor Codec",
        "category": "db",
        "lang": "typescript",
        "when": "Encoding pagination cursors so clients can't forge or read them",
        "why": "Atomic codec: value + salt in, signed base64url cursor out, tamper detection",
        "tags": ["db", "cursor", "codec", "pagination", "base64url"],
        "iface": r'''export function encodeCursor(offset: number, salt: string): string
export function decodeCursor(cursor: string, salt: string): number | null''',
        "code": r'''function hash(s: string) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); }
function b64(input: string) { return Buffer.from(input).toString('base64url'); }
export function encodeCursor(offset: number, salt: string) {
  const payload = JSON.stringify({ o: offset });
  return b64(payload + '.' + hash(payload + salt));
}
export function decodeCursor(cursor: string, salt: string) {
  try {
    const raw = Buffer.from(cursor, 'base64url').toString();
    const [payload, sig] = raw.split('.');
    if (!payload || sig !== hash(payload + salt)) return null;
    const parsed = JSON.parse(payload) as { o: number };
    return Number.isInteger(parsed.o) && parsed.o >= 0 ? parsed.o : null;
  } catch {
    return null;
  }
}''',
        "provides": "encodeCursor / decodeCursor",
        "depends": [],
    },
]
