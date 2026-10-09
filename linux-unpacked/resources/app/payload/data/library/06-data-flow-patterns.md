# 🔀 Data Flow Patterns

> Reference for designing data flow between nodes in generated applications.
> Every app has a data flow — design it first, build around it.

---

## 1. The Fundamental Data Flow

Every application follows this core pattern:

```
┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│ INPUT  │───▶│ LOGIC  │───▶│ STORE  │───▶│ OUTPUT │
│ (gather)│   │(process)│   │(persist)│   │(present)│
└────────┘    └────────┘    └────────┘    └────────┘
```

This maps to the Visual AI Architect nodes as:
- **Input** → User Input, File Scanner, API Fetcher, System Collector
- **Logic** → Core Logic, Transform Engine, Check Engine, Converter
- **Store** → Database, File System, In-Memory Cache
- **Output** → UI, Report, Export, Terminal, API Response

---

## 2. Common Data Flow Patterns

### 2.1 Sequential Flow

Simplest pattern — data flows through nodes one after another.

```
Input → Logic → Database → UI
```

**When to use:** Simple CRUD apps, calculators, basic tools

**Example:** Task Management App
```
User Input (create task) → Core Logic (validate) → Database (save) → UI (show list)
```

### 2.2 Parallel Flow

Data is processed in multiple independent paths simultaneously.

```
          ┌─── Logic A ───┐
Input ────┤               ├─── Merge ─── UI
          └─── Logic B ───┘
```

**When to use:** System diagnostics, data aggregation, dashboards

**Example:** System Diagnostic Tool
```
System Collector ─┬── CPU Check ──┐
                  ├── Memory Check┤── Report Builder → UI
                  ├── Disk Check  │
                  └── Network Chk─┘
```

### 2.3 Pipeline Flow

Data passes through a series of transformation steps.

```
Input → Step 1 → Step 2 → Step 3 → ... → Output
```

**When to use:** Media processing, ETL pipelines, data transformation

**Example:** Media Converter
```
File Scan → Parse Metadata → Transcode → Generate Thumbnail → Save → Notify UI
```

### 2.4 Event-Driven Flow

Components communicate through events — loosely coupled, reactive.

```
Input ──emit──▶ Event Bus ──dispatch──▶ Logic
UI ◀──update── (events) ◀──result─────┘
```

**When to use:** Real-time apps, media players, collaborative tools

**Example:** Media Player
```
User clicks "Play" → Event Bus emits play event
Player Service receives play event → starts playback
Player Service emits "now playing" event → UI updates
```

### 2.5 Feedback Loop Flow

Output feeds back into input, creating a cycle.

```
         ┌──────────────────────────┐
         │                          ▼
Input ───▶ Logic ───▶ Output ───▶ Feedback ──┘
```

**When to use:** Continuous monitoring, streaming, log tailing

**Example:** System Monitor
```
System Scan → Health Check → Report → Wait 5 min → System Scan (loop)
```

---

## 3. Data Flow by Node Type

### 3.1 Input Node Flow Patterns

| Input Type | Data Direction | Flow Pattern |
|---|---|---|
| CLI arguments | One-shot | Sequential |
| HTTP request | Request → Response | Sequential with API response |
| File watch | Continuous stream | Event-driven |
| Stdin pipe | Stream | Pipeline |
| User form | Submit → Process | Sequential |
| System collector | On-demand | Parallel → Merge |

### 3.2 Logic Node Data Transformation

Common transformation patterns:

```
Filter:    [A, B, C, D] → [A, C]           (select subset)
Map:       [1, 2, 3]    → [2, 4, 6]        (transform each)
Reduce:    [1, 2, 3, 4] → 10                (aggregate)
Group:     [A, A, B, B] → {A:[A,A], B:[B,B]} (categorize)
Validate:  raw_input    → validated_output  (check & clean)
Enrich:    {id:1}       → {id:1, name:"x"} (add data)
```

### 3.3 Database Node Flow Patterns

| Operation | Flow |
|---|---|
| **Read** | Request → Query → Format → Response |
| **Write** | Input → Validate → Write → Confirm |
| **Search** | Query → Index Lookup → Rank → Results |
| **Sync** | Source → Diff → Merge → Resolve Conflicts |

### 3.4 UI Node Data Binding

```
State Changes → UI Re-render → User Interacts → State Changes (loop)
```

**Three approaches:**

```typescript
// 1. One-way binding (simple, predictable)
function render(state: AppState): void {
  document.getElementById('app')!.innerHTML = template(state);
}

// 2. Two-way binding (interactive forms)
// React pattern: state → view, events → state
function Form() {
  const [name, setName] = useState('');
  return <input value={name} onChange={e => setName(e.target.value)} />;
}

// 3. Declarative (React/Vue/Svelte)
function App() {
  const { data, loading } = useData();
  if (loading) return <Spinner />;
  return <DataView items={data} />;
}
```

---

## 4. Data Flow for Common App Types

### 4.1 Music Streaming App

```
┌──────────────────────────────────────────────────────────┐
│                     MUSIC STREAMER                        │
│                                                           │
│  File Scanner ──▶ Metadata Parser ──▶ Library DB         │
│       ▲                                      │            │
│       │                                      ▼            │
│  Folder Watch                           Search Logic      │
│                                              │            │
│  User Input ──▶ Playback Logic ◀── Media Player          │
│                      │                     ▲              │
│                      ▼                     │              │
│                 Streaming Server ──── HTTP Stream         │
│                                                           │
│  Web UI ◀─── API Layer ◀─── (all above)                  │
└──────────────────────────────────────────────────────────┘
```

**Data flow:**
1. File Scanner reads music files → Metadata Parser extracts tags → Library DB stores
2. Folder Watch detects new files → triggers Scanner
3. User searches → API → Search Logic → Library DB → Results → UI
4. User plays → API → Playback Logic → Streaming Server → Audio → UI

### 4.2 System Diagnostic Tool

```
┌──────────────────────────────────────────────────────────┐
│                   SYSTEM DIAGNOSTIC                       │
│                                                           │
│  ┌── CPU Collector ──┐                                    │
│  ├── Memory Coll. ───┤                                    │
│  ├── Disk Collector ─┤──▶ Health Check Engine ──▶ Report  │
│  ├── Network Coll. ──┤         │                          │
│  ├── Service Check ──┤         ▼                          │
│  └── Journal Reader ─┘    Diagnostic DB                   │
│                                  │                        │
│  CLI / TUI ◀─── Report Builder ◀─┘                        │
└──────────────────────────────────────────────────────────┘
```

**Data flow:**
1. All collectors run in parallel → each returns structured data
2. Health Check Engine runs rules against collected data
3. Results stored in Diagnostic DB (history for trends)
4. Report Builder formats output → CLI/TUI displays

### 4.3 Web Application

```
┌──────────────────────────────────────────────────────────┐
│                    WEB APPLICATION                         │
│                                                           │
│  Browser ──HTTP──▶ Router ──▶ Auth Middleware             │
│    ▲                            │                         │
│    │                            ▼                         │
│    │                       Route Handler                  │
│    │                            │                         │
│    │                     ┌──────┴──────┐                  │
│    │                     │             │                  │
│    │              API Service    Page Render              │
│    │                     │             │                  │
│    │                     ▼             ▼                  │
│    │               Business Logic  Template Engine        │
│    │                     │                                │
│    │                     ▼                                │
│    │               Database / External API                │
│    └───────────── HTML/JSON ◀─────────────┘              │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Data Flow Anti-Patterns

| ❌ Bad Pattern | Why It's Bad | ✅ Fix |
|---|---|---|
| **Circular dependency** | Infinite loops, hard to debug | Use event-driven with loop detection |
| **God node** | One node does everything | Split into focused nodes |
| **Skip layers** | Input → Database (no logic) | Add validation logic layer |
| **Tight coupling** | Nodes know each other's internals | Use interfaces/contracts |
| **No error flow** | Failures are silent | Add error output paths |
| **Blocking chains** | One slow step blocks everything | Use parallel flows + async |

---

## 6. Error Flow Pattern

Every data flow should include error paths:

```
              ┌── Success Path ──▶ Logic ──▶ Output
              │
Input ────▶ Validate
              │
              └── Error Path ──▶ Error Handler ──▶ Error UI
                                      │
                                      ▼
                                 Log Error
```

```typescript
// Error flow implementation
async function dataFlow(input: unknown): Promise<void> {
  try {
    const validated = validateInput(input);
    const processed = await processData(validated);
    await saveToDatabase(processed);
    renderSuccess(processed);
  } catch (err) {
    const error = normalizeError(err);
    logError(error);
    renderError(error);
    // Optionally: attempt recovery
  }
}
```

---

*For deep technical coverage of data flow in distributed systems, see `bible-reference/12-distributed-systems/` and `bible-reference/05-systems/`*
