# 🛠️ Node Implementation Guide

> Step-by-step guide for implementing each node type in code.
> From design canvas to working code — the complete transformation.

---

## 1. The Code Generation Pipeline

When the user creates a node design and requests code generation:

```
Node Design (JSON)
    │
    ▼
1. Parse Design ─── Read nodes, edges, metadata
    │
    ▼
2. Validate ─────── Check connections, detect cycles, verify completeness
    │
    ▼
3. Analyze ──────── Determine app type, language, framework
    │
    ▼
4. Scaffold ─────── Create project structure, config files
    │
    ▼
5. Generate ─────── Create code for each node
    │
    ▼
6. Wire ──────────── Connect nodes together (imports, data flow)
    │
    ▼
7. Polish ───────── Lint, format, add README
    │
    ▼
Working Application
```

---

## 2. Parsing the Design JSON

### Input Format

Each saved design has this structure (from `designs.json`):

```json
{
  "id": "design_123",
  "name": "Task Management App",
  "goal": "A web app to manage tasks",
  "purpose": "Create, read, update, delete tasks",
  "targetOS": "linux",
  "nodes": [
    {
      "id": "node_0",
      "type": "input",
      "label": "User Input",
      "description": "Handle user input and validate entries.",
      "language": "typescript",
      "position": { "x": 250, "y": 300 }
    },
    {
      "id": "node_1",
      "type": "logic",
      "label": "Core Logic",
      "description": "Main application processing logic.",
      "language": "typescript",
      "position": { "x": 250, "y": 470 }
    }
  ],
  "edges": [
    { "source": "node_0", "target": "node_1" }
  ]
}
```

### Node Type Detection

From the design, detect the app type:

| Pattern in Design | App Type |
|---|---|
| Only input, logic, ui | CLI Tool |
| input, logic, database, ui | Basic Full-Stack App |
| Multiple logic nodes, databases | Complex App |
| API nodes present | External integrations |
| Media-related descriptions | Media Server |
| System/diagnostic descriptions | System Tool |

---

## 3. Per-Node Code Generation

### 3.1 Input Node → Code

**Input: CLI Args**
```typescript
// Generated from Input Node (CLI)
import { Command } from 'commander';
import { z } from 'zod';

const program = new Command();
program
  .name('app')
  .description('Node: User Input — Handle user input and validate entries.')
  .argument('<path>', 'Path to process')
  .option('-o, --output <file>', 'Output file path')
  .parse(process.argv);

const InputSchema = z.object({
  path: z.string().min(1),
  output: z.string().optional(),
});

export const parsedInput = InputSchema.parse({
  path: program.args[0],
  output: program.opts().output,
});
```

**Input: HTTP Request**
```typescript
// Generated from Input Node (HTTP)
import { z } from 'zod';

export const CreateTaskSchema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().max(1000).optional(),
  priority: z.enum(['low', 'medium', 'high']).default('medium'),
});

export type CreateTaskInput = z.infer<typeof CreateTaskSchema>;
```

**Input: System Collector**
```go
// Generated from Input Node (System Collector)
package collector

import (
	"os"
	"runtime"
	"time"
)

type SystemSnapshot struct {
	CPU    CPUInfo    `json:"cpu"`
	Memory MemoryInfo `json:"memory"`
	Disk   DiskInfo   `json:"disk"`
	Time   time.Time  `json:"time"`
}

func Collect() (*SystemSnapshot, error) {
	return &SystemSnapshot{
		CPU:    collectCPU(),
		Memory: collectMemory(),
		Disk:   collectDisk(),
		Time:   time.Now(),
	}, nil
}
```

### 3.2 Logic Node → Code

**Basic Business Logic**
```typescript
// Generated from Logic Node: Core Logic
import type { ValidatedInput } from '../input/types';

export interface ProcessResult {
  items: ProcessedItem[];
  total: number;
  timestamp: string;
}

export function process(input: ValidatedInput): ProcessResult {
  const items = input.rawData.map(transformItem);
  return {
    items,
    total: items.length,
    timestamp: new Date().toISOString(),
  };
}

function transformItem(item: RawItem): ProcessedItem {
  return {
    id: item.id,
    name: item.name.trim(),
    status: deriveStatus(item),
  };
}

function deriveStatus(item: RawItem): 'active' | 'inactive' | 'pending' {
  if (item.active && item.verified) return 'active';
  if (!item.active) return 'inactive';
  return 'pending';
}
```

**Health Check Logic**
```go
// Generated from Logic Node: Health Check Engine
package checks

type CheckResult struct {
	Name   string `json:"name"`
	Status string `json:"status"` // pass, warn, fail
	Score  int    `json:"score"`  // 0-100
	Detail string `json:"detail,omitempty"`
}

type HealthReport struct {
	Results    []CheckResult `json:"results"`
	Overall    int           `json:"overall"` // 0-100
	Critical   int           `json:"critical"`
	Warnings   int           `json:"warnings"`
}

func RunAllChecks(snapshot *collector.SystemSnapshot) *HealthReport {
	checks := []CheckResult{
		checkCPU(snapshot.CPU),
		checkMemory(snapshot.Memory),
		checkDisk(snapshot.Disk),
	}

	report := &HealthReport{Results: checks}
	for _, c := range checks {
		report.Overall += c.Score
		switch c.Status {
		case "fail": report.Critical++
		case "warn": report.Warnings++
		}
	}
	report.Overall /= len(checks)
	return report
}
```

### 3.3 Database Node → Code

**SQLite CRUD**
```typescript
// Generated from Database Node: Data Storage
import Database from 'better-sqlite3';
import path from 'path';

const DB_PATH = path.join(process.cwd(), 'data', 'app.db');

let db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    db.pragma('foreign_keys = ON');
    initializeSchema(db);
  }
  return db;
}

function initializeSchema(db: Database.Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS tasks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: 'pending' | 'in_progress' | 'done';
  created_at: string;
  updated_at: string;
}

export const tasks = {
  create(title: string, description?: string): Task {
    const stmt = getDb().prepare(
      'INSERT INTO tasks (title, description) VALUES (?, ?)'
    );
    const result = stmt.run(title, description ?? null);
    return getDb().prepare('SELECT * FROM tasks WHERE id = ?').get(
      result.lastInsertRowid
    ) as Task;
  },

  findAll(): Task[] {
    return getDb().prepare('SELECT * FROM tasks ORDER BY created_at DESC').all() as Task[];
  },

  findById(id: number): Task | undefined {
    return getDb().prepare('SELECT * FROM tasks WHERE id = ?').get(id) as Task | undefined;
  },

  update(id: number, data: Partial<Task>): Task {
    const fields = Object.keys(data).filter(k => k !== 'id');
    const setClause = fields.map(f => `${f} = ?`).join(', ');
    const values = fields.map(f => (data as Record<string, unknown>)[f]);
    values.push(new Date().toISOString(), id);
    getDb().prepare(
      `UPDATE tasks SET ${setClause}, updated_at = ? WHERE id = ?`
    ).run(...values);
    return this.findById(id)!;
  },

  delete(id: number): boolean {
    const result = getDb().prepare('DELETE FROM tasks WHERE id = ?').run(id);
    return result.changes > 0;
  },
};
```

### 3.4 UI Node → Code

**React Component**
```typescript
// Generated from UI Node: User Interface
import { useState, useEffect } from 'react';
import type { Task } from '../../db/schema';

interface Props {
  initialData?: Task[];
}

export function App({ initialData = [] }: Props) {
  const [tasks, setTasks] = useState<Task[]>(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadTasks();
  }, []);

  async function loadTasks() {
    try {
      setLoading(true);
      const response = await fetch('/api/tasks');
      if (!response.ok) throw new Error('Failed to load tasks');
      const data = await response.json();
      setTasks(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <div className="spinner">Loading...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="app">
      <header>
        <h1>Task Manager</h1>
        <TaskForm onCreated={loadTasks} />
      </header>
      <main>
        <TaskList tasks={tasks} onUpdate={loadTasks} />
      </main>
    </div>
  );
}
```

**TUI (Terminal UI)**
```go
// Generated from UI Node (Terminal UI)
package tui

import (
	"fmt"
	"strings"
	tea "github.com/charmbracelet/bubbletea"
	lipgloss "github.com/charmbracelet/lipgloss"
)

var (
	titleStyle = lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("#FFF")).
		Background(lipgloss.Color("#00ADD8")).
		Padding(0, 1)
	itemStyle = lipgloss.NewStyle().PaddingLeft(2)
)

type model struct {
	items  []string
	choice int
	loaded bool
	err    error
}

func (m model) Init() tea.Cmd { return nil }

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
		case "j", "down":
			if m.choice < len(m.items)-1 {
				m.choice++
			}
		case "k", "up":
			if m.choice > 0 {
				m.choice--
			}
		}
	}
	return m, nil
}

func (m model) View() string {
	if m.err != nil {
		return fmt.Sprintf("Error: %v\n", m.err)
	}
	var b strings.Builder
	b.WriteString(titleStyle.Render(" Task Manager "))
	b.WriteString("\n\n")
	for i, item := range m.items {
		cursor := "  "
		if i == m.choice {
			cursor = "▸ "
		}
		b.WriteString(fmt.Sprintf("%s%s\n", cursor, itemStyle.Render(item)))
	}
	b.WriteString("\nPress q to quit\n")
	return b.String()
}

func Run() {
	p := tea.NewProgram(model{})
	if _, err := p.Run(); err != nil {
		panic(err)
	}
}
```

### 3.5 API Node → Code

```typescript
// Generated from API Node: External API Integration
import { z } from 'zod';

const API_BASE = process.env.API_BASE_URL ?? 'https://api.example.com/v1';

const ApiResponseSchema = z.object({
  data: z.unknown(),
  error: z.string().nullable(),
});

type ApiResponse = z.infer<typeof ApiResponseSchema>;

export async function apiCall<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${getToken()}`,
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, body);
  }

  const json = await response.json();
  const parsed = ApiResponseSchema.parse(json);
  if (parsed.error) throw new ApiError(500, parsed.error);
  return parsed.data as T;
}

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(`API Error (${status}): ${message}`);
    this.name = 'ApiError';
  }
}
```

---

## 4. Wiring Nodes Together

After generating each node's code, wire them together:

### Simple Sequential Wiring

```typescript
// main.ts — Wires all nodes together
import { handleInput } from './input/user-input';
import { process } from './logic/core-logic';
import { tasks } from './db/data-storage';
import { App } from './ui/user-interface';

// The data flow (matches the edge connections)
async function main() {
  // 1. Get input
  const input = handleInput(process.argv);

  // 2. Process via logic
  const result = process(input);

  // 3. Store results
  tasks.create(result.title, result.description);

  // 4. Render UI
  const app = App({ initialData: tasks.findAll() });
  // ... mount app
}

main().catch(console.error);
```

### Node Graph Wiring (Dynamic)

For complex designs, generate a wiring file dynamically:

```typescript
// generated/wiring.ts — Auto-generated from design edges
import type { NodeRegistry } from './registry';

// This file is generated from the edge connections in the design
export function wireNodes(registry: NodeRegistry): void {
  // Edge: node_0 → node_1
  registry.on('node_0:output', (data) => {
    registry.call('node_1', 'process', data);
  });

  // Edge: node_1 → node_2
  registry.on('node_1:output', (data) => {
    registry.call('node_2', 'save', data);
  });

  // Edge: node_1 → node_3
  registry.on('node_1:output', (data) => {
    registry.call('node_3', 'render', data);
  });
}
```

---

## 5. Generated File Structure

For a design with input, logic, database, and UI nodes:

```
project/
├── src/
│   ├── index.ts                 # Entry point with wiring
│   ├── types.ts                 # Shared types
│   ├── config.ts                # Configuration
│   ├── input/
│   │   ├── index.ts             # Input node code
│   │   └── validation.ts        # Validation schemas
│   ├── logic/
│   │   └── index.ts             # Logic node code
│   ├── db/
│   │   ├── schema.ts            # Database schema
│   │   └── repository.ts        # Data access
│   └── ui/
│       ├── App.tsx              # UI component
│       └── components/          # Sub-components
├── data/
│   └── app.db                   # SQLite database (auto-created)
├── package.json
├── tsconfig.json
└── README.md
```

---

*For language-specific implementation details, see `bible-reference/04-web-apps/`, `bible-reference/05-systems-programming/`, and `bible-reference/11-database-internals/`*
