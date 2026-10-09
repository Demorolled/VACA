# 🗄️ Database Design Patterns

> Reference for database design, indexing strategies, query optimization, and storage patterns.
> Extracted from The Programming Bible's Databases and Database Internals levels.

---

## 1. Database Type Selection

### Decision Matrix

| Requirement | Recommendation | Why |
|---|---|---|
| **Zero config, single file** | SQLite | Perfect for desktop apps, no server needed |
| **Multi-user, network access** | PostgreSQL | Robust, concurrent, feature-rich |
| **High write throughput** | LSM-based (RocksDB) | Optimized for write-heavy workloads |
| **Document storage** | MongoDB (or SQLite JSON) | Flexible schemas, nested data |
| **Cache only** | In-Memory (Redis/Memcached) | Fastest, no persistence needed |
| **Full-text search** | SQLite FTS5 / Elasticsearch | Advanced search capabilities |
| **Time series** | SQLite + custom schema / InfluxDB | Event logging, metrics |
| **Graph data** | PostgreSQL + pgRouting / Neo4j | Relationships, path finding |

### ACID vs BASE

| Property | ACID (SQL) | BASE (NoSQL) |
|---|---|---|
| **Consistency** | Strong — all or nothing | Eventual — data converges |
| **Availability** | Lower — prefers consistency | Higher — prefers uptime |
| **Partition tolerance** | Lower | Higher — designed for distribution |
| **Use case** | Financial, transactional | Analytics, logging, caches |

---

## 2. B+Tree Indexes

The fundamental indexing structure in most relational databases.

### Structure

```
Root (Internal)
    │
    ├── [Key: 10] → [Key: 20] → [Key: 30]
    │       │            │            │
    ▼       ▼            ▼            ▼
Internal  [10-20)    [20-30)       [30-...)
    │       │            │            │
    ▼       ▼            ▼            ▼
Leaf    [1,2,5,8]  [10,12,15]  [20,22,28]  [30,35,40]
    ───────────────────────────────────────────────→  (Linked list for range scans)
```

### Key Properties

| Property | B+Tree | B-Tree |
|---|---|---|
| **Data storage** | Only in leaf nodes | In every node |
| **Range scan** | ✅ Fast — linked leaves | ❌ Must traverse up/down |
| **Cache efficiency** | Higher — internal nodes are smaller | Lower |
| **Space utilization** | ~67% minimum | Same |
| **Search complexity** | O(log_f N) | O(log_f N) |

### SQLite B+Tree Configuration

```typescript
import Database from 'better-sqlite3';

const db = new Database('app.db');

// Performance pragmas
db.pragma('journal_mode = WAL');        // Write-Ahead Logging — better concurrent reads
db.pragma('foreign_keys = ON');         // Enable foreign key constraints
db.pragma('synchronous = NORMAL');      // Balance safety & speed
db.pragma('cache_size = -64000');       // 64MB page cache
db.pragma('temp_store = MEMORY');       // Store temp tables in memory
db.pragma('mmap_size = 268435456');     // 256MB memory-mapped I/O

// Create indexes for query performance
db.exec(`
  CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
  CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id, status);
  CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
`);
```

### Index Selection Guide

```sql
-- ✅ GOOD: Index for common queries
CREATE INDEX idx_orders_user_date ON orders(user_id, order_date DESC);

-- Serves these queries:
SELECT * FROM orders WHERE user_id = 42 ORDER BY order_date DESC;
SELECT * FROM orders WHERE user_id = 42 AND order_date > '2024-01-01';

-- ❌ BAD: Index on low-cardinality column (few distinct values)
CREATE INDEX idx_users_active ON users(active);  -- Only true/false

-- ✅ BETTER: Composite index with high-cardinality first
CREATE INDEX idx_users_active_created ON users(active, created_at DESC);
```

---

## 3. Query Optimization

### EXPLAIN Query Plans

```sql
-- SQLite: EXPLAIN QUERY PLAN
EXPLAIN QUERY PLAN
SELECT t.*, u.name 
FROM tasks t
JOIN users u ON t.user_id = u.id
WHERE t.status = 'pending'
ORDER BY t.created_at DESC;

-- Output:
-- |--SEARCH t USING INDEX idx_tasks_status (status=?)
-- |--SEARCH u USING INTEGER PRIMARY KEY (rowid=?)
-- `--USE TEMP B-TREE FOR ORDER BY

-- Indicates: Index lookup on status, primary key lookup on users, 
-- but needs improvement on the ORDER BY (should add composite index)
```

### Performance Anti-Patterns

| ❌ Bad Pattern | Why | ✅ Fix |
|---|---|---|
| `SELECT *` | Fetches unnecessary columns, prevents covering index | Select only needed columns |
| Missing WHERE on indexed column | Full table scan | Add filter on indexed column |
| `LIKE '%pattern'` | Cannot use index (wildcard prefix) | Use full-text search (FTS) |
| Function on indexed column: `WHERE YEAR(date) = 2024` | Cannot use index | Use range: `date >= '2024-01-01' AND date < '2025-01-01'` |
| N+1 queries | 1 query + N queries per row | Use JOIN or batch loading |
| No pagination limit | Returns all rows | Always use LIMIT/OFFSET or cursor pagination |

### Pagination Patterns

```typescript
// Offset pagination (simple, but slow for large offsets)
const tasks = db.prepare(`
  SELECT * FROM tasks 
  WHERE user_id = ? 
  ORDER BY created_at DESC 
  LIMIT ? OFFSET ?
`).all(userId, pageSize, (page - 1) * pageSize);

// Cursor pagination (fast, stable for large datasets)
const tasks = db.prepare(`
  SELECT * FROM tasks 
  WHERE user_id = ? 
    AND (created_at, id) < (?, ?)  -- Cursor: (last_created_at, last_id)
  ORDER BY created_at DESC, id DESC 
  LIMIT ?
`).all(userId, lastCreatedAt, lastId, pageSize);
```

---

## 4. Schema Design Patterns

### Normalization Levels

| Normal Form | Rule | Example Violation |
|---|---|---|
| **1NF** | Atomic values, no repeated groups | `tags: "tag1,tag2,tag3"` in single column |
| **2NF** | No partial dependencies (composite keys) | `order_id, product_id → customer_name` |
| **3NF** | No transitive dependencies | `order_id → customer_id → customer_name` |

### Practical Schema Example

```sql
-- Users
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tasks
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'done')),
  priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
  due_date TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tags (normalized many-to-many)
CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE task_tags (
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (task_id, tag_id)
);

-- Indexes for performance
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX idx_tasks_due_date ON tasks(due_date) WHERE due_date IS NOT NULL;
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
```

### Migration Strategy

```typescript
// Schema migration pattern
interface Migration {
  version: number;
  name: string;
  up: (db: Database.Database) => void;
  down: (db: Database.Database) => void;
}

const migrations: Migration[] = [
  {
    version: 1,
    name: 'create_users_and_tasks',
    up(db) {
      db.exec(`CREATE TABLE users (...)`);
      db.exec(`CREATE TABLE tasks (...)`);
    },
    down(db) {
      db.exec(`DROP TABLE IF EXISTS tasks`);
      db.exec(`DROP TABLE IF EXISTS users`);
    },
  },
  {
    version: 2,
    name: 'add_tags',
    up(db) {
      db.exec(`CREATE TABLE tags (...)`);
      db.exec(`CREATE TABLE task_tags (...)`);
    },
    down(db) {
      db.exec(`DROP TABLE IF EXISTS task_tags`);
      db.exec(`DROP TABLE IF EXISTS tags`);
    },
  },
];

function runMigrations(db: Database.Database): void {
  // Create migrations tracking table
  db.exec(`
    CREATE TABLE IF NOT EXISTS _migrations (
      version INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);

  const applied = new Set(
    db.prepare('SELECT version FROM _migrations').all()
      .map((r: any) => r.version)
  );

  for (const migration of migrations) {
    if (!applied.has(migration.version)) {
      console.log(`Running migration: ${migration.name}`);
      db.transaction(() => {
        migration.up(db);
        db.prepare('INSERT INTO _migrations (version, name) VALUES (?, ?)')
          .run(migration.version, migration.name);
      })();
    }
  }
}
```

---

## 5. Transaction Patterns

```typescript
// Basic transaction
function transferFunds(fromId: number, toId: number, amount: number): void {
  const db = getDb();
  const transfer = db.transaction(() => {
    const from = db.prepare('SELECT balance FROM accounts WHERE id = ?').get(fromId) as any;
    if (from.balance < amount) throw new AppError('Insufficient funds', 'ERR_BALANCE');

    db.prepare('UPDATE accounts SET balance = balance - ? WHERE id = ?').run(amount, fromId);
    db.prepare('UPDATE accounts SET balance = balance + ? WHERE id = ?').run(amount, toId);
  });

  transfer(); // Auto-commit or rollback on error
}

// Retry on serialization conflicts (WAL mode)
function withRetry<T>(fn: () => T, maxRetries = 3): T {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return fn();
    } catch (err) {
      if (err instanceof Error && err.message.includes('SQLITE_BUSY') && attempt < maxRetries) {
        continue;
      }
      throw err;
    }
  }
  throw new AppError('Transaction failed after retries', 'ERR_TX_RETRY');
}
```

---

## 6. LSM-Tree Storage (Write-Optimized)

For write-heavy workloads where B+Trees struggle:

```
MemTable (sorted in memory)
    │  (flush when full)
    ▼
Level 0: [SSTable] [SSTable]
    │  (compaction)
    ▼
Level 1: [SSTable (sorted, non-overlapping)]
    │  (merge)
    ▼
Level N: [SSTable ...]
```

| Property | B+Tree | LSM-Tree |
|---|---|---|
| **Write amplification** | Lower | Higher |
| **Read amplification** | Lower (single lookup) | Higher (check multiple levels) |
| **Write throughput** | Moderate | Very high |
| **Space amplification** | Lower (in-place updates) | Higher (obsolete entries) |
| **Use case** | Read-heavy workloads | Write-heavy workloads |

---

## Quick Reference: Database by Node Type

| Node Type | Database Mapping |
|---|---|
| **Input** | Validate before storing, parameterize queries |
| **Logic** | Repository pattern, transaction coordination |
| **Database** | SQLite/PostgreSQL, schema design, indexing |
| **UI** | Data display, pagination, search results |
| **API** | External data caching, rate limiting |

---

*For deeper database concepts, see Bible levels `06-databases/` and `11-database-internals/` — SQL engines, distributed databases, query optimization, transactions.*
