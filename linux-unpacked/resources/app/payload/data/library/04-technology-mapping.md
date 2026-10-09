# 🛠️ Technology Mapping

> Reference for selecting the right languages, frameworks, and libraries for each node type and application scenario.

---

## 1. Language Selection Matrix

| App Type | Primary Lang | Alternative | When to Use Alternative |
|---|---|---|---|
| **CLI Tool** | Go | TypeScript | When existing ecosystem is JS/TS |
| **System Tool** | Go | Python | When heavy data processing needed |
| **Web App** | TypeScript | Python | When team knows Python better |
| **Media Server** | TypeScript + Python | Go | Go for performance-critical streaming |
| **Desktop Web App** | TypeScript | — | React + Vite is the standard |
| **API Server** | TypeScript | Python / Go | FastAPI for auto-docs, Go for perf |
| **Data Processor** | Python | TypeScript | Python for ML/NLP/scraping |
| **Game** | TypeScript | Go | Go for performance-critical game loops |

### Decision Tree

```
Is performance critical?
├── Yes → Go (single binary, fast, low memory)
└── No → Is it data/ML heavy?
    ├── Yes → Python (rich ecosystem)
    └── No → TypeScript (best DX, type safety, versatile)
```

---

## 2. Framework Selection per Node Type

### 2.1 Input Nodes

| Input Method | TypeScript | Python | Go |
|---|---|---|---|
| **CLI Args** | `commander`, `yargs` | `click`, `typer` | `cobra`, `urfave/cli` |
| **HTTP Request** | `express`, `fastify` | `fastapi`, `flask` | `gin`, `chi`, `echo` |
| **File Watch** | `chokidar` | `watchdog` | `fsnotify` |
| **WebSocket** | `ws`, `socket.io` | `websockets` | `gorilla/websocket` |
| **Stdin** | `readline` | `sys.stdin` | `bufio.Scanner` |

### 2.2 Logic Nodes

| Logic Type | TypeScript | Python | Go |
|---|---|---|---|
| **Data Transform** | Lodash, `Array.map/filter/reduce` | `pandas`, builtins | `slices`, `maps` |
| **State Machine** | `xstate` | `transitions` | `looplab/fsm` |
| **Validation** | `zod`, `yup` | `pydantic` | `go-playground/validator` |
| **Scheduling** | `node-cron` | `schedule`, `apscheduler` | `robfig/cron` |
| **Stream Processing** | Node streams | `apache-beam` | `samara` (Kafka) |

### 2.3 Database Nodes

| Database | TypeScript | Python | Go |
|---|---|---|---|
| **SQLite** | `better-sqlite3` | `sqlite3`, `sqlalchemy` | `modernc.org/sqlite` |
| **PostgreSQL** | `pg`, `drizzle-orm` | `psycopg2`, `sqlalchemy` | `pgx`, `jackc/pgx` |
| **In-Memory** | `Map`, `lru-cache` | `dict`, `cachetools` | `sync.Map`, `hashicorp/golang-lru` |
| **JSON File** | `fs` module | `json` module | `encoding/json` |
| **FTS (Search)** | SQLite FTS5 | SQLite FTS5 | SQLite FTS5 via `modernc.org/sqlite` |

### 2.4 UI Nodes

| UI Type | TypeScript | Python | Go |
|---|---|---|---|
| **Web (React)** | React + Vite + Tailwind | — | — |
| **Web (Simple)** | Vanilla HTML/JS | — | — |
| **Terminal** | `ink` | `rich` | `bubbletea`, `tview` |
| **Desktop (Web)** | Capacitor + React | — | — |
| **Native Linux** | — | `PyQt`, `tkinter` | `gotk3`, `fyne` |

### 2.5 API Nodes

| API Type | TypeScript | Python | Go |
|---|---|---|---|
| **REST Client** | `fetch`, `axios` | `httpx`, `requests` | `net/http` |
| **GraphQL** | `graphql-request`, `urql` | `sgqlc` | `shurcooL/graphql` |
| **gRPC** | `@grpc/grpc-js` | `grpcio` | `google.golang.org/grpc` |
| **WebSocket** | `ws` | `websockets` | `gorilla/websocket` |
| **OAuth** | `openid-client` | `authlib` | `golang.org/x/oauth2` |

---

## 3. Database Selection Guide

### Decision Matrix

| Requirement | Recommendation | Why |
|---|---|---|
| **Zero config, single file** | SQLite | Perfect for desktop apps, no server needed |
| **Multi-user, network access** | PostgreSQL | Robust, concurrent, feature-rich |
| **Cache only** | In-Memory | Fastest, no persistence needed |
| **Small data, simple** | JSON file | Humans can read/edit, no dependency |
| **Search-heavy** | SQLite FTS5 | Full-text search, no extra infra |
| **Time-series** | SQLite + custom schema | Or consider InfluxDB for scale |

### SQLite Configuration (Default — Manifesto Preferred)

```typescript
const db = new Database('app.db');
db.pragma('journal_mode = WAL');      // Better concurrent reads
db.pragma('foreign_keys = ON');        // Referential integrity
db.pragma('synchronous = NORMAL');     // Balance safety & speed
db.pragma('cache_size = -64000');      // 64MB cache
```

---

## 4. Validation Library Selection

| Language | Library | Features |
|---|---|---|
| **TypeScript** | `zod` | TypeScript-first, type inference, composable |
| **Python** | `pydantic` | Dataclass-style, JSON schema generation |
| **Go** | `go-playground/validator` | Struct tags, extensive validators |

---

## 5. Logging Library Selection

| Language | Library | Features |
|---|---|---|
| **TypeScript** | `pino` | Fast, structured JSON logging |
| **Python** | `loguru` | Drop-in replacement for `logging`, easy setup |
| **Go** | `log/slog` (stdlib) | Structured logging, leveled, fast |

### Logging Pattern

```typescript
// Always log at entry and exit points
import pino from 'pino';

const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  transport: { target: 'pino/file', options: { destination: './app.log' } },
});

export function createUser(input: CreateUserInput): User {
  logger.info({ input }, 'Creating user');
  try {
    const user = userRepository.create(input);
    logger.info({ userId: user.id }, 'User created successfully');
    return user;
  } catch (err) {
    logger.error({ err, input }, 'Failed to create user');
    throw new AppError('User creation failed', 'ERR_CREATE_USER');
  }
}
```

---

## 6. Testing Framework Selection

| Language | Framework | Features |
|---|---|---|
| **TypeScript** | `vitest` | Fast, TypeScript-native, compatible with Jest API |
| **Python** | `pytest` | Simple, powerful fixtures, great plugins |
| **Go** | `testing` (stdlib) + `testify` | Built-in, `testify/assert` for convenience |

---

## 7. Build / Package Selection

| Language | Package | Output |
|---|---|---|
| **TypeScript** | `tsup` or `esbuild` | Bundled JS (single file) |
| **Go** | `go build` | Single static binary |
| **Python** | `pyinstaller` | Single executable (or source distribution) |

### Build Targets (Linux-focused)

```makefile
# Go
build:
	go build -ldflags="-s -w" -o bin/app ./cmd/app

# TypeScript
build:
	tsup src/index.ts --minify --target node20

# Python
build:
	pyinstaller --onefile --name app src/main.py
```

---

*For deeper technology comparisons, see `bible-reference/04-web-apps/`, `bible-reference/05-systems-programming/`, and `bible-reference/11-database-internals/`*
