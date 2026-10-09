# 🧩 Node Architecture Reference

> Complete reference for all node types in the Visual AI Architect.
> Each node type has specific code generation rules, language mappings, and implementation patterns.

---

## 1. Node Type Overview

The Visual AI Architect uses a **node-based design system** with the following node types:

| Node Type | Icon | Purpose | Output |
|---|---|---|---|
| `input` | 📥 | Handle user input, validate, sanitize | Validated data |
| `logic` | ⚙️ | Business logic, processing, computation | Processed data |
| `database` | 💾 | Data persistence, storage, retrieval | Stored/queried data |
| `ui` | 🖥️ | User interface rendering | Visual output |
| `api` | 🔌 | External service integration | API responses |

Each node is a **self-contained module** with:
- Clear input/output contracts (typed interfaces)
- Single responsibility
- Testable in isolation
- Language-specific implementation patterns

---

## 2. Input Node (`input`)

### Purpose
Capture, validate, and sanitize user input before passing it to logic nodes.

### Code Generation Rules

```
┌────────────────────────────────────────────┐
│                INPUT NODE                    │
│                                              │
│  Raw Input → [Parse] → [Validate] → [Output] │
│                  → [Sanitize]                │
└────────────────────────────────────────────┘
```

#### TypeScript Pattern
```typescript
// input.node.ts
import { z } from 'zod';

// 1. Define schema with validation rules
export const InputSchema = z.object({
  username: z.string().min(3).max(50).trim(),
  email: z.string().email().toLowerCase(),
  age: z.number().int().min(0).max(150).optional(),
});

export type ValidatedInput = z.infer<typeof InputSchema>;

// 2. Parse & validate
export function handleInput(raw: unknown): ValidatedInput {
  const parsed = InputSchema.parse(raw);
  return parsed; // typed & validated
}

// 3. Error handling
export class InputValidationError extends Error {
  constructor(issues: z.ZodIssue[]) {
    super(`Input validation failed: ${issues.map(i => i.message).join(', ')}`);
    this.name = 'InputValidationError';
  }
}
```

#### Python Pattern
```python
# input_node.py
from pydantic import BaseModel, Field, ValidationError

class UserInput(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    age: int | None = Field(None, ge=0, le=150)

def handle_input(raw: dict) -> UserInput:
    try:
        return UserInput(**raw)
    except ValidationError as e:
        raise InputValidationError(str(e))
```

#### Go Pattern
```go
// input.go
type UserInput struct {
    Username string `json:"username" validate:"required,min=3,max=50"`
    Email    string `json:"email"    validate:"required,email"`
    Age      *int   `json:"age,omitempty" validate:"omitempty,min=0,max=150"`
}

func HandleInput(raw []byte) (*UserInput, error) {
    var input UserInput
    if err := json.Unmarshal(raw, &input); err != nil {
        return nil, fmt.Errorf("parse error: %w", err)
    }
    validate := validator.New()
    if err := validate.Struct(&input); err != nil {
        return nil, fmt.Errorf("validation error: %w", err)
    }
    return &input, nil
}
```

### Input Node Variants

| Variant | When to Use | Example |
|---|---|---|
| **CLI Args** | Command-line tools | `process.argv`, `cobra.Command` |
| **HTTP Request** | Web/API apps | Express `req.body`, FastAPI `Body()` |
| **File Input** | File processing tools | `fs.readFile`, `open()` |
| **Form Input** | Web UI forms | React form state + validation |
| **WebSocket** | Real-time apps | WS message validation |
| **Stdin** | Pipe-friendly CLI tools | `readline`, `bufio.Scanner` |

---

## 3. Logic Node (`logic`)

### Purpose
Core business logic — the processing engine that transforms input data into meaningful output.

### Code Generation Rules

```
┌────────────────────────────────────────────┐
│               LOGIC NODE                    │
│                                              │
│  Input → [Transform] → [Compute] → [Output] │
│         → [Filter]    → [Aggregate]         │
└────────────────────────────────────────────┘
```

#### TypeScript Pattern
```typescript
// logic.node.ts
// 1. Define domain types
export interface ProcessResult {
  success: boolean;
  data: unknown;
  metrics?: Record<string, number>;
}

// 2. Pure business logic function
export function processData(input: ValidatedInput): ProcessResult {
  // Business logic here — pure functions preferred
  const result = transform(input);
  validateOutput(result);
  return { success: true, data: result };
}

// 3. Helper functions (extracted for testability)
function transform(input: ValidatedInput): unknown {
  // Single responsibility per function
  return input;
}

function validateOutput(result: unknown): asserts result is ProcessResult {
  if (!result) throw new Error('Processing failed: empty result');
}
```

### Logic Node Anti-Patterns

| ❌ Bad Practice | ✅ Good Practice |
|---|---|
| Mixing I/O with business logic | Pure functions for logic, I/O in dedicated nodes |
| Functions > 50 lines | Extract helpers, max 50 lines per function |
| Silent error catching | Always throw or return explicit errors |
| Magic numbers/strings | Named constants and config values |
| Deeply nested conditionals | Early returns, guard clauses, polymorphism |

---

## 4. Database Node (`database`)

### Purpose
Persistent data storage, retrieval, querying, and management.

### Code Generation Rules

```
┌────────────────────────────────────────────┐
│             DATABASE NODE                   │
│                                              │
│  Request → [Query] → [Process] → [Response] │
│         → [Write]   → [Cache]               │
└────────────────────────────────────────────┘
```

#### SQLite Pattern (Default — Manifesto Preference)
```typescript
// database.node.ts
import Database from 'better-sqlite3';

const DB_PATH = './data/app.db';

// 1. Schema definition
export function initializeDatabase(): Database.Database {
  const db = new Database(DB_PATH);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  db.exec(`
    CREATE TABLE IF NOT EXISTS items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      created_at TEXT DEFAULT (datetime('now'))
    )
  `);
  return db;
}

// 2. Type-safe queries
interface Item {
  id: number;
  name: string;
  created_at: string;
}

export function createItem(db: Database.Database, name: string): Item {
  const stmt = db.prepare('INSERT INTO items (name) VALUES (?)');
  const result = stmt.run(name);
  return db.prepare('SELECT * FROM items WHERE id = ?').get(result.lastInsertRowid) as Item;
}

export function getItem(db: Database.Database, id: number): Item | undefined {
  return db.prepare('SELECT * FROM items WHERE id = ?').get(id) as Item | undefined;
}
```

### Database Node Variants

| Variant | When to Use | Example |
|---|---|---|
| **SQLite** | Default for Linux desktop apps | `better-sqlite3`, `sqlite3` |
| **PostgreSQL** | Multi-user web apps | `pg` (Node), `psycopg2` (Python) |
| **JSON File** | Minimal config/data storage | `fs.readFile`/`writeFile` |
| **In-Memory** | Cache, session, ephemeral data | `Map`, `WeakMap`, LRU cache |

---

## 5. UI Node (`ui`)

### Purpose
Render the user interface — web, terminal, or desktop.

### Code Generation Rules

```
┌────────────────────────────────────────────┐
│                UI NODE                      │
│                                              │
│  State → [Render] → [Display] → [Feedback]  │
│       → [Style]    → [Events]               │
└────────────────────────────────────────────┘
```

#### Web UI Pattern (React + TypeScript)
```typescript
// ui.node.tsx
import { useState, useEffect } from 'react';

interface UIState {
  data: unknown;
  loading: boolean;
  error: string | null;
}

export function AppComponent() {
  const [state, setState] = useState<UIState>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    loadData()
      .then(data => setState({ data, loading: false, error: null }))
      .catch(err => setState({ data: null, loading: false, error: err.message }));
  }, []);

  if (state.loading) return <div>Loading...</div>;
  if (state.error) return <div className="error">{state.error}</div>;
  return <MainView data={state.data} />;
}
```

#### Terminal UI Pattern (Go + Bubble Tea)
```go
// ui.go
type model struct {
    data    []string
    loading bool
    err     error
}

func (m model) Init() tea.Cmd { return fetchData }
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    switch msg := msg.(type) {
    case dataMsg:
        m.data = msg.data
        m.loading = false
        return m, nil
    case errMsg:
        m.err = msg.err
        m.loading = false
        return m, nil
    }
    return m, nil
}
func (m model) View() string {
    if m.loading { return "Loading..." }
    if m.err != nil { return fmt.Sprintf("Error: %v", m.err) }
    return strings.Join(m.data, "\n")
}
```

---

## 6. API Node (`api`)

### Purpose
Interface with external services — REST APIs, WebSockets, system commands.

### Code Generation Rules

```
┌────────────────────────────────────────────┐
│               API NODE                      │
│                                              │
│  Request → [Auth] → [Call] → [Parse] → Out  │
│         → [Retry]   → [Cache]              │
└────────────────────────────────────────────┘
```

#### TypeScript Pattern
```typescript
// api.node.ts
const API_BASE = 'https://api.example.com/v1';

interface ApiResponse<T> {
  data: T;
  error: string | null;
}

export async function callApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    return { data: data as T, error: null };
  } catch (err) {
    return { data: null as T, error: (err as Error).message };
  }
}
```

---

## 7. Node Connection Rules

When designing the node graph, follow these connection rules:

| Connection | Valid? | Notes |
|---|---|---|
| `input → logic` | ✅ | Standard data flow |
| `input → database` | ⚠️ | Rare — only if input directly queries |
| `input → ui` | ⚠️ | Input triggers UI refresh |
| `logic → database` | ✅ | Store processed results |
| `logic → ui` | ✅ | Display processed data |
| `database → logic` | ✅ | Load data for processing |
| `database → ui` | ✅ | Display stored data |
| `api → logic` | ✅ | External data for processing |
| `api → ui` | ⚠️ | Direct display of API data |
| `ui → logic` | ✅ | User actions trigger logic |
| `logic → api` | ✅ | Process data before sending |

---

## 8. Node Metadata Schema

Each saved node should include this metadata:

```typescript
interface NodeMetadata {
  id: string;              // Unique node ID
  type: 'input' | 'logic' | 'database' | 'ui' | 'api';
  label: string;           // Display name
  description: string;     // What this node does
  language: string;        // Target language (typescript, python, go)
  position: { x: number; y: number };  // Position on canvas
  config?: Record<string, unknown>;     // Node-specific configuration
  dependencies?: string[]; // IDs of nodes this depends on
  outputType?: string;     // Type of data this node outputs
}
```

---

*For deeper technical details on any topic, consult the corresponding bible-reference/ level via MASTER-INDEX.txt*
