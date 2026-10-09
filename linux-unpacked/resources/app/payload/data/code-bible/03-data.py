# -*- coding: utf-8 -*-
"""
Code Bible — Category 03: Data access & persistence (atomic).
Convention: repositories expose `find/findAll/create/update/remove`;
adapters wrap a single backend behind a stable interface.
"""
CHUNKS = [
    {
        "id": "data-sqlite-connect",
        "name": "SQLite Connection",
        "category": "data",
        "lang": "typescript",
        "when": "Opening a local SQLite database with WAL mode and pragmas",
        "why": "Atomic DB open; path in, db handle out — one responsibility, ready for a repository chunk",
        "tags": ["sqlite", "database", "connect", "wal", "local"],
        "iface": r'''export interface SqliteOpenResult { db: unknown; close(): Promise<void> }
export async function openSqlite(path: string): Promise<SqliteOpenResult>''',
        "code": r'''import { Database } from 'better-sqlite3';

export async function openSqlite(path: string): Promise<SqliteOpenResult> {
  const db = new Database(path);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  db.pragma('synchronous = NORMAL');
  return {
    db,
    close: async () => { db.close(); },
  };
}''',
        "provides": "openSqlite(path)",
        "depends": [],
    },
    {
        "id": "data-pg-pool",
        "name": "Postgres Connection Pool",
        "category": "data",
        "lang": "typescript",
        "when": "Connecting a backend to Postgres with a pooled, reusable client",
        "why": "Atomic pool; config in, query fn out — connection lifecycle owned by pg, caller only queries",
        "tags": ["postgres", "sql", "pool", "database", "server"],
        "iface": r'''export interface PgPoolResult {
  query<T = unknown>(sql: string, params?: unknown[]): Promise<{ rows: T[]; rowCount: number }>;
  close(): Promise<void>;
}
export async function createPgPool(config: {
  host: string; port?: number; database: string; user: string; password: string;
}): Promise<PgPoolResult>''',
        "code": r'''import { Pool } from 'pg';

export async function createPgPool(config: {
  host: string; port?: number; database: string; user: string; password: string;
}): Promise<PgPoolResult> {
  const pool = new Pool({ ...config, max: 10 });
  return {
    async query<T = unknown>(sql: string, params: unknown[] = []) {
      const res = await pool.query<T>(sql, params);
      return { rows: res.rows, rowCount: res.rowCount ?? 0 };
    },
    close: () => pool.end(),
  };
}''',
        "provides": "createPgPool(config)",
        "depends": [],
    },
    {
        "id": "data-mongo-connect",
        "name": "MongoDB Connection",
        "category": "data",
        "lang": "typescript",
        "when": "Connecting to a MongoDB server with a shared client and collection helper",
        "why": "Atomic mongo client; uri/db in, typed collection accessor out",
        "tags": ["mongodb", "nosql", "database", "connect", "document"],
        "iface": r'''export interface MongoResult {
  collection<T extends Document = Document>(name: string): Collection<T>;
  close(): Promise<void>;
}
export async function connectMongo(uri: string, dbName: string): Promise<MongoResult>''',
        "code": r'''import { MongoClient, Collection, Document } from 'mongodb';

export async function connectMongo(uri: string, dbName: string): Promise<MongoResult> {
  const client = new MongoClient(uri);
  await client.connect();
  const db = client.db(dbName);
  return {
    collection: (name) => db.collection(name),
    close: () => client.close(),
  };
}''',
        "provides": "connectMongo(uri, dbName)",
        "depends": [],
    },
    {
        "id": "data-repository-crud",
        "name": "Generic Repository",
        "category": "data",
        "lang": "typescript",
        "when": "Abstracting CRUD behind one interface so callers never touch SQL directly",
        "why": "Atomic repository contract; id/patch types in, findAll/find/create/update/remove out — swap backends freely",
        "tags": ["repository", "crud", "dao", "abstraction", "data"],
        "iface": r'''export interface Entity { id: string }
export interface Repository<T extends Entity> {
  findAll(): Promise<T[]>;
  find(id: string): Promise<T | null>;
  create(item: T): Promise<T>;
  update(id: string, patch: Partial<T>): Promise<T | null>;
  remove(id: string): Promise<boolean>;
}
export function createInMemoryRepository<T extends Entity>(): Repository<T>''',
        "code": r'''export function createInMemoryRepository<T extends Entity>(): Repository<T> {
  const rows = new Map<string, T>();

  return {
    async findAll() { return [...rows.values()]; },
    async find(id) { return rows.get(id) ?? null; },
    async create(item) { rows.set(item.id, item); return item; },
    async update(id, patch) {
      const existing = rows.get(id);
      if (!existing) return null;
      const next = { ...existing, ...patch, id };
      rows.set(id, next);
      return next;
    },
    async remove(id) { return rows.delete(id); },
  };
}''',
        "provides": "createInMemoryRepository<T>()",
        "depends": [],
    },
    {
        "id": "data-migration-runner",
        "name": "Schema Migration Runner",
        "category": "data",
        "lang": "typescript",
        "when": "Applying ordered schema migrations exactly once per environment",
        "why": "Atomic migrator; migration list in, applied ids out — tracks a schema_migrations table",
        "tags": ["migration", "schema", "version", "ddl", "database"],
        "iface": r'''export interface Migration { id: string; up: (sql: (q: string) => Promise<void>) => Promise<void> }
export async function runMigrations(
  sql: (q: string) => Promise<void>,
  migrations: Migration[],
  queryApplied: () => Promise<string[]>,
): Promise<string[]>''',
        "code": r'''export async function runMigrations(
  sql: (q: string) => Promise<void>,
  migrations: Migration[],
  queryApplied: () => Promise<string[]>,
): Promise<string[]> {
  await sql(`CREATE TABLE IF NOT EXISTS schema_migrations (id TEXT PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))`);
  const applied = new Set(await queryApplied());
  const ran: string[] = [];

  for (const m of migrations.sort((a, b) => a.id.localeCompare(b.id))) {
    if (applied.has(m.id)) continue;
    await m.up(sql);
    await sql(`INSERT INTO schema_migrations (id) VALUES ('${m.id}')`);
    ran.push(m.id);
  }
  return ran;
}''',
        "provides": "runMigrations(sql, migrations, queryApplied)",
        "depends": [],
    },
    {
        "id": "data-query-builder",
        "name": "Query Builder",
        "category": "data",
        "lang": "typescript",
        "when": "Composing parameterized SQL without string concatenation",
        "why": "Atomic builder: chained where/order/limit in, {sql, params} out — injection-safe by construction",
        "tags": ["query", "builder", "sql", "parameterized", "safe"],
        "iface": r'''export interface BuiltQuery { sql: string; params: unknown[] }
export class QueryBuilder {
  constructor(table: string);
  where(column: string, op: '=' | '>' | '<' | '>=' | '<=' | 'LIKE', value: unknown): this;
  orderBy(column: string, dir?: 'ASC' | 'DESC'): this;
  limit(n: number): this;
  build(): BuiltQuery;
}''',
        "code": r'''export class QueryBuilder {
  private clauses: string[] = [];
  private values: unknown[] = [];
  private order = '';
  private lim = '';

  constructor(private table: string) {}

  where(column: string, op: '=' | '>' | '<' | '>=' | '<=' | 'LIKE', value: unknown) {
    this.clauses.push(`${column} ${op} ?`);
    this.values.push(value);
    return this;
  }

  orderBy(column: string, dir: 'ASC' | 'DESC' = 'ASC') {
    this.order = ` ORDER BY ${column} ${dir}`;
    return this;
  }

  limit(n: number) {
    this.lim = ` LIMIT ${Math.max(0, Math.floor(n))}`;
    return this;
  }

  build(): BuiltQuery {
    const where = this.clauses.length ? ` WHERE ${this.clauses.join(' AND ')}` : '';
    return { sql: `SELECT * FROM ${this.table}${where}${this.order}${this.lim}`, params: this.values };
  }
}''',
        "provides": "QueryBuilder(table)",
        "depends": [],
    },
    {
        "id": "data-json-file-store",
        "name": "JSON File Store",
        "category": "data",
        "lang": "typescript",
        "when": "Persisting small datasets to a JSON file (config, settings, prototypes)",
        "why": "Atomic file store; file path in, load/save/update out — atomic write via temp+rename",
        "tags": ["json", "file", "store", "persist", "atomic write"],
        "iface": r'''export function createJsonFileStore<T>(filePath: string, fallback: T) {
  return {
    load(): Promise<T>,
    save(value: T): Promise<void>,
    update(fn: (current: T) => T): Promise<T>,
  };
}''',
        "code": r'''import { promises as fs } from 'fs';
import * as path from 'path';

export function createJsonFileStore<T>(filePath: string, fallback: T) {
  return {
    async load(): Promise<T> {
      try {
        const raw = await fs.readFile(filePath, 'utf-8');
        return JSON.parse(raw) as T;
      } catch {
        return fallback;
      }
    },
    async save(value: T) {
      await fs.mkdir(path.dirname(filePath), { recursive: true });
      const tmp = filePath + '.tmp';
      await fs.writeFile(tmp, JSON.stringify(value, null, 2), 'utf-8');
      await fs.rename(tmp, filePath);   // atomic on same filesystem
    },
    async update(fn: (current: T) => T): Promise<T> {
      const next = fn(await this.load());
      await this.save(next);
      return next;
    },
  };
}''',
        "provides": "createJsonFileStore<T>(filePath, fallback)",
        "depends": [],
    },
    {
        "id": "data-csv-parse",
        "name": "CSV Parser",
        "category": "data",
        "lang": "typescript",
        "when": "Parsing CSV text into typed rows (imports, exports, reports)",
        "why": "Atomic parser: raw csv in, records out — handles quotes/commas/newlines inside fields",
        "tags": ["csv", "parse", "import", "tabular", "text"],
        "iface": r'''export interface ParseCsvResult { headers: string[]; rows: Record<string, string>[] }
export function parseCsv(text: string, options?: { delimiter?: string }): ParseCsvResult''',
        "code": r'''export function parseCsv(text: string, options?: { delimiter?: string }): ParseCsvResult {
  const delim = options?.delimiter ?? ',';
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === delim) { row.push(field); field = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field); field = '';
      if (row.some((f) => f.length > 0)) rows.push(row);
      row = [];
    } else field += c;
  }
  if (field.length > 0 || row.length > 0) { row.push(field); rows.push(row); }

  const [headers, ...data] = rows;
  return { headers: headers ?? [], rows: data.map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i] ?? '']))) };
}''',
        "provides": "parseCsv(text, options?)",
        "depends": [],
    },
    {
        "id": "data-csv-write",
        "name": "CSV Writer",
        "category": "data",
        "lang": "typescript",
        "when": "Serializing records to CSV for export/download",
        "why": "Atomic writer: headers + rows in, csv string out — escapes quotes/commas correctly",
        "tags": ["csv", "write", "export", "serialize", "tabular"],
        "iface": r'''export function toCsv(headers: string[], rows: Array<Array<string | number | boolean | null>>): string''',
        "code": r'''export function toCsv(headers: string[], rows: Array<Array<string | number | boolean | null>>): string {
  function esc(v: string | number | boolean | null): string {
    const s = v === null ? '' : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }
  const head = headers.map(esc).join(',');
  const body = rows.map((r) => r.map(esc).join(','));
  return [head, ...body].join('\n');
}''',
        "provides": "toCsv(headers, rows)",
        "depends": [],
    },
    {
        "id": "data-pagination-query",
        "name": "Offset Pagination Query",
        "category": "data",
        "lang": "typescript",
        "when": "Slicing query results into pages with stable ordering",
        "why": "Atomic paginator: page/pageSize/total in, {items, meta} out — deterministic order required",
        "tags": ["pagination", "offset", "page", "slice", "query"],
        "iface": r'''export interface Page<T> { items: T[]; page: number; pageSize: number; total: number; totalPages: number; hasNext: boolean }
export function paginate<T>(items: T[], page: number, pageSize: number): Page<T>''',
        "code": r'''export function paginate<T>(items: T[], page: number, pageSize: number): Page<T> {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  const p = Math.max(0, Math.min(page, totalPages - 1));
  const start = p * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    page: p,
    pageSize,
    total,
    totalPages,
    hasNext: p < totalPages - 1,
  };
}''',
        "provides": "paginate<T>(items, page, pageSize)",
        "depends": [],
    },
    {
        "id": "data-transaction",
        "name": "Transaction Wrapper",
        "category": "data",
        "lang": "typescript",
        "when": "Running multiple writes atomically — all succeed or all roll back",
        "why": "Atomic transaction helper; fn in, committed result out — BEGIN/COMMIT/ROLLBACK handled here",
        "tags": ["transaction", "atomic", "commit", "rollback", "database"],
        "iface": r'''export interface TxExecutor {
  run(sql: string, params?: unknown[]): Promise<void>;
  query<T = unknown>(sql: string, params?: unknown[]): Promise<T[]>;
}
export async function withTransaction<T>(
  begin: () => Promise<TxExecutor>,
  commit: () => Promise<void>,
  rollback: () => Promise<void>,
  fn: (tx: TxExecutor) => Promise<T>,
): Promise<T>''',
        "code": r'''export async function withTransaction<T>(
  begin: () => Promise<TxExecutor>,
  commit: () => Promise<void>,
  rollback: () => Promise<void>,
  fn: (tx: TxExecutor) => Promise<T>,
): Promise<T> {
  const tx = await begin();
  try {
    const result = await fn(tx);
    await commit();
    return result;
  } catch (e) {
    try { await rollback(); } catch { /* best effort */ }
    throw e;
  }
}''',
        "provides": "withTransaction<T>(begin, commit, rollback, fn)",
        "depends": [],
    },
    {
        "id": "data-id-generator",
        "name": "ID Generator",
        "category": "data",
        "lang": "typescript",
        "when": "Creating collision-resistant ids for entities, files, sessions",
        "why": "Atomic id factory; prefix in, sortable/timestamped id out — no external deps",
        "tags": ["id", "uuid", "generator", "unique", "sortable"],
        "iface": r'''export function createIdGenerator(prefix?: string, random?: () => number): () => string
export function nanoid(len?: number): string''',
        "code": r'''const ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';

export function nanoid(len = 21): string {
  let out = '';
  const bytes = new Uint8Array(len);
  crypto.getRandomValues(bytes);
  for (let i = 0; i < len; i++) out += ALPHABET[bytes[i] % ALPHABET.length];
  return out;
}

export function createIdGenerator(prefix = '', random: () => number = Math.random): () => string {
  let seq = 0;
  return () => {
    seq += 1;
    const ts = Date.now().toString(36);
    const rand = Math.floor(random() * 0xffffff).toString(36).padStart(4, '0');
    return `${prefix}${ts}${rand}${seq.toString(36).padStart(3, '0')}`;
  };
}''',
        "provides": "nanoid(len?), createIdGenerator(prefix?, random?)",
        "depends": [],
    },
    {
        "id": "data-schema-validator",
        "name": "Schema Validator",
        "category": "data",
        "lang": "typescript",
        "when": "Validating untrusted input against a field schema (API bodies, config)",
        "why": "Atomic validator: schema + value in, {ok, errors} out — no coercion, no side effects",
        "tags": ["validate", "schema", "types", "input", "check"],
        "iface": r'''export type FieldRule =
  | { kind: 'string'; required?: boolean; min?: number; max?: number; pattern?: string }
  | { kind: 'number'; required?: boolean; min?: number; max?: number }
  | { kind: 'boolean'; required?: boolean };
export function validateSchema(value: unknown, schema: Record<string, FieldRule>): { ok: boolean; errors: Record<string, string> }''',
        "code": r'''export function validateSchema(value: unknown, schema: Record<string, FieldRule>) {
  const errors: Record<string, string> = {};
  const obj = (value ?? {}) as Record<string, unknown>;

  for (const [key, rule] of Object.entries(schema)) {
    const raw = obj[key];
    if (rule.required && (raw === undefined || raw === null || raw === '')) {
      errors[key] = 'required';
      continue;
    }
    if (raw === undefined || raw === null) continue;
    if (rule.kind === 'string') {
      const s = String(raw);
      if (rule.min !== undefined && s.length < rule.min) errors[key] = `min ${rule.min}`;
      if (rule.max !== undefined && s.length > rule.max) errors[key] = `max ${rule.max}`;
      if (rule.pattern && !new RegExp(rule.pattern).test(s)) errors[key] = 'format';
    } else if (rule.kind === 'number') {
      const n = Number(raw);
      if (Number.isNaN(n)) errors[key] = 'number';
      if (rule.min !== undefined && n < rule.min) errors[key] = `min ${rule.min}`;
      if (rule.max !== undefined && n > rule.max) errors[key] = `max ${rule.max}`;
    } else if (rule.kind === 'boolean' && typeof raw !== 'boolean') {
      errors[key] = 'boolean';
    }
  }
  return { ok: Object.keys(errors).length === 0, errors };
}''',
        "provides": "validateSchema(value, schema)",
        "depends": [],
    },
    {
        "id": "data-indexeddb-store",
        "name": "IndexedDB Store",
        "category": "data",
        "lang": "typescript",
        "when": "Persisting large datasets client-side (offline apps, caches)",
        "why": "Atomic IndexedDB wrapper; db name + store in, typed get/set/remove/keys out — promisified",
        "tags": ["indexeddb", "browser", "store", "offline", "persist"],
        "iface": r'''export function createIndexedDbStore(dbName: string, storeName: string) {
  return {
    get<T = unknown>(key: string): Promise<T | undefined>,
    set(key: string, value: unknown): Promise<void>,
    remove(key: string): Promise<void>,
    keys(): Promise<string[]>,
  };
}''',
        "code": r'''export function createIndexedDbStore(dbName: string, storeName: string) {
  function open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(dbName, 1);
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains(storeName)) {
          req.result.createObjectStore(storeName);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  function tx<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    return open().then(
      (db) =>
        new Promise<T>((resolve, reject) => {
          const t = db.transaction(storeName, mode);
          const req = fn(t.objectStore(storeName));
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => reject(req.error);
        }),
    );
  }

  return {
    get: (key) => tx('readonly', (s) => s.get(key)),
    set: (key, value) => tx('readwrite', (s) => s.put(value, key)).then(() => undefined),
    remove: (key) => tx('readwrite', (s) => s.delete(key)).then(() => undefined),
    keys: () => tx('readonly', (s) => s.getAllKeys()).then((k) => k.map(String)),
  };
}''',
        "provides": "createIndexedDbStore(dbName, storeName)",
        "depends": [],
    },
    {
        "id": "data-binary-search",
        "name": "Binary Search",
        "category": "data",
        "lang": "typescript",
        "when": "Finding an element in a sorted array in O(log n)",
        "why": "Atomic search; sorted array + target in, index out (-1 if missing) — pure, no mutation",
        "tags": ["binary", "search", "sorted", "logn", "algorithm"],
        "iface": r'''export function binarySearch<T>(sorted: T[], target: T, compare?: (a: T, b: T) => number): number
export function lowerBound<T>(sorted: T[], target: T, compare?: (a: T, b: T) => number): number''',
        "code": r'''export function binarySearch<T>(sorted: T[], target: T, compare?: (a: T, b: T) => number): number {
  let lo = 0, hi = sorted.length - 1;
  const cmp = compare ?? ((a: T, b: T) => (a < b ? -1 : a > b ? 1 : 0));
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const c = cmp(sorted[mid], target);
    if (c === 0) return mid;
    if (c < 0) lo = mid + 1;
    else hi = mid - 1;
  }
  return -1;
}

export function lowerBound<T>(sorted: T[], target: T, compare?: (a: T, b: T) => number): number {
  let lo = 0, hi = sorted.length;
  const cmp = compare ?? ((a: T, b: T) => (a < b ? -1 : a > b ? 1 : 0));
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cmp(sorted[mid], target) < 0) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}''',
        "provides": "binarySearch<T>, lowerBound<T>",
        "depends": [],
    },
    {
        "id": "data-hash-table",
        "name": "Hash Table",
        "category": "data",
        "lang": "typescript",
        "when": "Key-value lookup with average O(1) access in pure JS",
        "why": "Atomic hash map with chaining; get/set/delete/keys out — demonstrates collisions handled",
        "tags": ["hash", "table", "map", "lookup", "data structure"],
        "iface": r'''export function createHashTable<K, V>(capacity?: number) {
  return {
    set(key: K, value: V): void,
    get(key: K): V | undefined,
    has(key: K): boolean,
    delete(key: K): boolean,
    get size(): number,
    keys(): K[],
  };
}''',
        "code": r'''export function createHashTable<K, V>(capacity = 64) {
  const buckets: Array<Array<[K, V]>> = Array.from({ length: capacity }, () => []);
  let count = 0;

  function hash(key: K): number {
    const s = String(key);
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return h % capacity;
  }

  return {
    set(key, value) {
      const b = buckets[hash(key)];
      const found = b.find(([k]) => k === key);
      if (found) found[1] = value;
      else { b.push([key, value]); count++; }
    },
    get(key) {
      return buckets[hash(key)].find(([k]) => k === key)?.[1];
    },
    has(key) {
      return buckets[hash(key)].some(([k]) => k === key);
    },
    delete(key) {
      const b = buckets[hash(key)];
      const idx = b.findIndex(([k]) => k === key);
      if (idx === -1) return false;
      b.splice(idx, 1);
      count--;
      return true;
    },
    get size() { return count; },
    keys() { return buckets.flat().map(([k]) => k); },
  };
}''',
        "provides": "createHashTable<K,V>(capacity?)",
        "depends": [],
    },
    {
        "id": "data-bloom-filter",
        "name": "Bloom Filter",
        "category": "data",
        "lang": "typescript",
        "when": "Pre-filtering membership checks with tiny memory (caches, dedupe, spellcheck)",
        "why": "Atomic bloom; add/has/maybeContains out — false positives allowed, false negatives impossible",
        "tags": ["bloom", "filter", "membership", "probabilistic", "memory"],
        "iface": r'''export function createBloomFilter(size?: number, hashCount?: number) {
  return {
    add(item: string): void,
    has(item: string): boolean,     // true = maybe present
    clear(): void,
    get usedBits(): number,
  };
}''',
        "code": r'''function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}

export function createBloomFilter(size = 256, hashCount = 3) {
  const bits = new Uint8Array(Math.ceil(size / 8));
  let used = 0;

  function indexes(item: string): number[] {
    const a = fnv1a(item);
    const b = fnv1a('salt:' + item);
    return Array.from({ length: hashCount }, (_, i) => (a + i * b) % size);
  }

  return {
    add(item) {
      for (const i of indexes(item)) {
        const byte = i >> 3, mask = 1 << (i & 7);
        if (!(bits[byte] & mask)) { bits[byte] |= mask; used++; }
      }
    },
    has(item) {
      for (const i of indexes(item)) {
        if (!(bits[i >> 3] & (1 << (i & 7)))) return false;
      }
      return true;
    },
    clear() { bits.fill(0); used = 0; },
    get usedBits() { return used; },
  };
}''',
        "provides": "createBloomFilter(size?, hashCount?)",
        "depends": [],
    },
    {
        "id": "data-vector-store",
        "name": "In-Memory Vector Store",
        "category": "data",
        "lang": "typescript",
        "when": "Embedding-based similarity search for RAG and semantic lookup",
        "why": "Atomic vector store; add/search out with cosine similarity — brute force, ideal for small sets",
        "tags": ["vector", "embedding", "similarity", "cosine", "rag"],
        "iface": r'''export interface VectorItem { id: string; vector: number[]; meta?: Record<string, unknown> }
export function createVectorStore() {
  return {
    add(item: VectorItem): void,
    search(vector: number[], topK?: number): Array<{ id: string; score: number; meta?: Record<string, unknown> }>,
    get size(): number,
    clear(): void,
  };
}''',
        "code": r'''export function createVectorStore() {
  const items: VectorItem[] = [];

  function cosine(a: number[], b: number[]): number {
    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < a.length; i++) {
      dot += a[i] * b[i];
      na += a[i] * a[i];
      nb += b[i] * b[i];
    }
    return na === 0 || nb === 0 ? 0 : dot / (Math.sqrt(na) * Math.sqrt(nb));
  }

  return {
    add(item) { items.push(item); },
    search(vector, topK = 5) {
      return items
        .map((it) => ({ id: it.id, score: cosine(vector, it.vector), meta: it.meta }))
        .sort((a, b) => b.score - a.score)
        .slice(0, topK);
    },
    get size() { return items.length; },
    clear() { items.length = 0; },
  };
}''',
        "provides": "createVectorStore()",
        "depends": [],
    },
    {
        "id": "data-fulltext-index",
        "name": "Full-Text Inverted Index",
        "category": "data",
        "lang": "typescript",
        "when": "Searching documents by keyword without a database (notes, docs, mail)",
        "why": "Atomic inverted index; add/search out — tokenizes, stops, and ranks by frequency",
        "tags": ["fulltext", "search", "inverted", "index", "tokenize"],
        "iface": r'''export function createFullTextIndex() {
  return {
    add(id: string, text: string): void,
    search(query: string, topK?: number): Array<{ id: string; score: number }>,
    remove(id: string): void,
  };
}''',
        "code": r'''const STOP = new Set(['the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with', 'is', 'are']);

export function createFullTextIndex() {
  const postings = new Map<string, Map<string, number>>();   // term -> docId -> count

  function tokens(text: string): string[] {
    return text.toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length > 1 && !STOP.has(t));
  }

  return {
    add(id, text) {
      for (const term of tokens(text)) {
        if (!postings.has(term)) postings.set(term, new Map());
        postings.get(term)!.set(id, (postings.get(term)!.get(id) ?? 0) + 1);
      }
    },
    search(query, topK = 10) {
      const scores = new Map<string, number>();
      for (const term of tokens(query)) {
        const docs = postings.get(term);
        if (!docs) continue;
        for (const [docId, count] of docs) scores.set(docId, (scores.get(docId) ?? 0) + count);
      }
      return [...scores.entries()]
        .map(([id, score]) => ({ id, score }))
        .sort((a, b) => b.score - a.score)
        .slice(0, topK);
    },
    remove(id) {
      for (const docs of postings.values()) docs.delete(id);
    },
  };
}''',
        "provides": "createFullTextIndex()",
        "depends": [],
    },
    {
        "id": "data-event-log",
        "name": "Append-Only Event Log",
        "category": "data",
        "lang": "typescript",
        "when": "Recording immutable audit/history entries (activity, ledger, telemetry)",
        "why": "Atomic event log: append/readRange/trim out — append-only by contract, no updates",
        "tags": ["event", "log", "append", "audit", "ledger"],
        "iface": r'''export interface LogEntry { seq: number; ts: number; type: string; payload: unknown }
export function createEventLog() {
  return {
    append(type: string, payload: unknown): LogEntry,
    readRange(fromSeq: number, toSeq?: number): LogEntry[],
    tail(count?: number): LogEntry[],
    get size(): number,
    trim(keepLast: number): void,
  };
}''',
        "code": r'''export function createEventLog() {
  const entries: LogEntry[] = [];
  let seq = 0;

  return {
    append(type, payload) {
      const entry: LogEntry = { seq: seq++, ts: Date.now(), type, payload };
      entries.push(entry);
      return entry;
    },
    readRange(fromSeq, toSeq = Number.MAX_SAFE_INTEGER) {
      return entries.filter((e) => e.seq >= fromSeq && e.seq <= toSeq);
    },
    tail(count = 10) {
      return entries.slice(-count);
    },
    get size() { return entries.length; },
    trim(keepLast) {
      entries.splice(0, Math.max(0, entries.length - keepLast));
    },
  };
}''',
        "provides": "createEventLog()",
        "depends": [],
    },
    {
        "id": "data-snapshot-store",
        "name": "Snapshot Store",
        "category": "data",
        "lang": "typescript",
        "when": "Capturing point-in-time states for backup or time-travel",
        "why": "Atomic snapshotter; capture/restore/list out — stores deep copies, not references",
        "tags": ["snapshot", "backup", "restore", "state", "copy"],
        "iface": r'''export function createSnapshotStore<T>() {
  return {
    capture(name: string, state: T): void,
    restore(name: string): T | null,
    list(): string[],
    clear(): void,
  };
}''',
        "code": r'''export function createSnapshotStore<T>() {
  const snapshots = new Map<string, T>();

  return {
    capture(name, state) {
      snapshots.set(name, structuredClone(state));
    },
    restore(name) {
      const s = snapshots.get(name);
      return s === undefined ? null : structuredClone(s);
    },
    list() { return [...snapshots.keys()]; },
    clear() { snapshots.clear(); },
  };
}''',
        "provides": "createSnapshotStore<T>()",
        "depends": [],
    },
    {
        "id": "data-blob-store",
        "name": "Blob Store",
        "category": "data",
        "lang": "typescript",
        "when": "Storing binary content keyed by id (uploads, images, exports)",
        "why": "Atomic blob store; put/get/delete out — bytes in and out, no parsing or typing inside",
        "tags": ["blob", "binary", "storage", "upload", "bytes"],
        "iface": r'''export function createBlobStore() {
  return {
    put(id: string, data: Uint8Array): Promise<void>,
    get(id: string): Promise<Uint8Array | null>,
    delete(id: string): Promise<boolean>,
    list(): Promise<string[]>,
  };
}''',
        "code": r'''export function createBlobStore() {
  const map = new Map<string, Uint8Array>();

  return {
    async put(id, data) { map.set(id, new Uint8Array(data)); },
    async get(id) { const v = map.get(id); return v ? new Uint8Array(v) : null; },
    async delete(id) { return map.delete(id); },
    async list() { return [...map.keys()]; },
  };
}''',
        "provides": "createBlobStore()",
        "depends": [],
    },
    {
        "id": "data-connection-pool",
        "name": "Generic Connection Pool",
        "category": "data",
        "lang": "typescript",
        "when": "Reusing expensive connections (db, redis) under concurrency",
        "why": "Atomic pool: acquire/release out — borrows, waits, and recycles without leaking",
        "tags": ["pool", "connection", "resource", "concurrency", "reuse"],
        "iface": r'''export function createConnectionPool<T>(
  create: () => Promise<T>,
  options?: { max?: number; destroy?: (conn: T) => Promise<void> },
) {
  return {
    acquire(): Promise<T>,
    release(conn: T): void,
    get available(): number,
    get inUse(): number,
    close(): Promise<void>,
  };
}''',
        "code": r'''export function createConnectionPool<T>(
  create: () => Promise<T>,
  options?: { max?: number; destroy?: (conn: T) => Promise<void> },
) {
  const max = options?.max ?? 10;
  const idle: T[] = [];
  const waiters: Array<(c: T) => void> = [];
  let active = 0;

  return {
    async acquire(): Promise<T> {
      if (idle.length > 0) { active++; return idle.pop()!; }
      if (active < max) { active++; return create(); }
      return new Promise((resolve) => waiters.push(resolve));
    },
    release(conn) {
      const waiter = waiters.shift();
      if (waiter) waiter(conn);
      else idle.push(conn);
    },
    get available() { return idle.length; },
    get inUse() { return active; },
    async close() {
      for (const conn of idle) await options?.destroy?.(conn);
      idle.length = 0;
    },
  };
}''',
        "provides": "createConnectionPool<T>(create, options?)",
        "depends": [],
    },
]
