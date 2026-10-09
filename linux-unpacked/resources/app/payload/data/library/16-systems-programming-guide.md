# ⚙️ Systems Programming Guide

> Reference for systems-level programming — memory management, concurrency, compilers, and performance optimization.
> Extracted from The Programming Bible's Systems Programming and OS Kernel levels.

---

## 1. Memory Management

### Process Memory Layout (Linux x86-64)

```
High Address
─────────────────────────
  Stack (grows down)      ← Local variables, function calls (~8MB default)
  │
  Memory-mapped files     ← Shared libraries, mmap(), large allocations
  │
  Heap (grows up)         ← Dynamic allocations (malloc, new)
  │
  BSS section             ← Uninitialized global/static variables
  Data section            ← Initialized global/static variables
  Text section (code)     ← Program instructions (read-only)
─────────────────────────
Low Address
```

### Stack vs Heap Allocation

| Aspect | Stack | Heap |
|---|---|---|
| **Speed** | ~1 instruction (adjust `rsp`) | Hundreds of instructions |
| **Lifetime** | Function scope | Manual or GC-managed |
| **Size limit** | ~8MB (configurable via `ulimit`) | GB (limited by RAM/Swap) |
| **Fragmentation** | None — LIFO allocation | Can fragment over time |
| **Thread safety** | Per-thread (automatic) | Must synchronize |
| **Prefer when** | Fixed-size, short-lived data | Dynamic size, long-lived data |

### Manual Memory Management Patterns

```go
// Go memory layout example (no explicit free needed — GC handles it)
type Buffer struct {
    data  []byte
    size  int
}

func NewBuffer(size int) *Buffer {
    return &Buffer{
        data: make([]byte, size),
        size: size,
    }
}

// Arena allocator pattern (for game engines, parsers)
type Arena struct {
    memory  []byte
    offset  int
}

func NewArena(capacity int) *Arena {
    return &Arena{memory: make([]byte, capacity)}
}

func (a *Arena) Alloc(size int) []byte {
    if a.offset+size > len(a.memory) {
        panic("arena full")
    }
    chunk := a.memory[a.offset : a.offset+size]
    a.offset += size
    return chunk
}

func (a *Arena) Reset() {
    a.offset = 0 // O(1) free — just reset pointer
}
```

### Memory Debugging

```bash
# Valgrind — detect memory leaks and errors
valgrind --leak-check=full ./myprogram

# AddressSanitizer — fast memory error detection
# Compile with: -fsanitize=address -g
./myprogram  # Reports use-after-free, buffer overflows, etc.

# Check memory usage
top -p $(pgrep myprogram)
pmap -x $(pgrep myprogram)
cat /proc/$(pgrep myprogram)/maps
```

---

## 2. Concurrency & Parallelism

### Fundamental Distinctions

| Concept | Definition | Requires Multiple Cores? |
|---|---|---|
| **Concurrency** | Dealing with multiple things at once (logical simultaneity) | No |
| **Parallelism** | Executing multiple operations simultaneously (physical simultaneity) | Yes |
| **Asynchrony** | Non-blocking operations, callbacks, futures | No |

### Performance Laws

```
Amdahl's Law:    Speedup = 1 / ((1 - P) + P/N)
Gustafson's Law: Speedup = N - (N - 1) × S

Where: P = parallel portion, N = processors, S = serial portion
```

**Key insight:** Amdahl says serial bottlenecks limit speedup. Gustafson says problem size scales with resources. Both are true — profile your specific bottleneck.

### Processes vs Threads

```go
// Go — goroutines (lightweight threads)
func main() {
    var wg sync.WaitGroup
    
    for i := 0; i < 10; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            processItem(id)
        }(i)
    }
    
    wg.Wait() // Wait for all goroutines
}
```

| Aspect | Processes | Threads | Goroutines |
|---|---|---|---|
| **Memory** | Separate address space | Shared | Shared |
| **Creation cost** | High (fork/exec) | Medium | Very low (~4KB) |
| **Context switch** | Kernel-mediated | Kernel-mediated | User-space (M:N scheduling) |
| **Isolation** | Strong | Weak | Weak |
| **Communication** | IPC (pipes, sockets, shared memory) | Shared memory + mutex | Channels (CSP) |

### Synchronization Primitives

```typescript
// Node.js worker_threads (shared memory via SharedArrayBuffer)
import { Worker, isMainThread, parentPort, workerData } from 'worker_threads';

// Mutex using Atomics (lock-free synchronization)
class Mutex {
  private locked = new Int32Array(new SharedArrayBuffer(4));

  lock(): void {
    while (Atomics.compareExchange(this.locked, 0, 0, 1) !== 0) {
      Atomics.wait(this.locked, 0, 1); // Wait for unlock
    }
  }

  unlock(): void {
    Atomics.store(this.locked, 0, 0);
    Atomics.notify(this.locked, 1); // Wake waiting threads
  }
}
```

```go
// Go — channels (CSP — Communicating Sequential Processes)
func worker(id int, jobs <-chan Job, results chan<- Result) {
    for job := range jobs {
        result := process(job)
        results <- result
    }
}

// Mutex (traditional)
type SafeCounter struct {
    mu    sync.Mutex
    value map[string]int
}

func (c *SafeCounter) Increment(key string) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.value[key]++
}
```

### Common Concurrency Patterns

| Pattern | Description | Use Case |
|---|---|---|
| **Fan-Out** | One producer, many workers | Parallel processing |
| **Fan-In** | Many producers, one consumer | Aggregating results |
| **Pipeline** | Stage 1 → Stage 2 → Stage 3 | Stream processing |
| **Pub/Sub** | Publisher → channel → multiple subscribers | Event-driven systems |
| **Worker Pool** | Fixed number of workers processing jobs | Rate-limited tasks |
| **Circuit Breaker** | Fail fast when downstream is down | Resilient services |

---

## 3. Compiler Design Overview

### Compilation Pipeline

```
Source Code
    │
    ▼
┌──────────────┐
│   Lexer      │  Character stream → Token stream
└──────┬───────┘
       ▼
┌──────────────┐
│   Parser     │  Token stream → AST (Abstract Syntax Tree)
└──────┬───────┘
       ▼
┌──────────────┐
│   Semantic   │  Type checking, symbol resolution, scope analysis
│   Analysis   │
└──────┬───────┘
       ▼
┌──────────────┐
│   IR Gen     │  AST → Intermediate Representation (IR)
└──────┬───────┘
       ▼
┌──────────────┐
│ Optimizer    │  Dead code elimination, constant folding, inlining
└──────┬───────┘
       ▼
┌──────────────┐
│ Code Gen     │  IR → Assembly / Machine Code
└──────┬───────┘
       ▼
    Executable
```

### Key Compiler Concepts

| Concept | Description |
|---|---|
| **Lexer** | Regex-based tokenization — identifies keywords, identifiers, literals |
| **Parser** | Grammar-based (LL, LR, PEG) — builds AST from tokens |
| **AST** | Tree representation of program structure — nodes are expressions, statements |
| **IR** | Lower-level representation — three-address code, SSA form, bytecode |
| **SSA** | Static Single Assignment — each variable assigned exactly once, enables optimizations |
| **Code Gen** | Register allocation, instruction selection, peephole optimization |

---

## 4. Performance Optimization

### Profiling Tools

| Tool | Use Case | Command |
|---|---|---|
| **perf** (Linux) | CPU profiling, cache misses, branches | `perf record ./app && perf report` |
| **pprof** (Go) | CPU, memory, goroutine, mutex profiling | `go tool pprof http://localhost:6060/debug/pprof/heap` |
| **flamegraph** | Visual call stack sampling | `perf script | stackcollapse-perf.pl | flamegraph.pl > graph.svg` |
| **Valgrind/Cachegrind** | Cache simulation, branch prediction | `valgrind --tool=cachegrind ./app` |

### Optimization Strategies

```
1. Profile first — never guess where bottlenecks are
2. Measure baseline — establish performance metrics
3. Focus on the hot path — 90% of time is in 10% of code
4. Reduce allocations — GC pressure kills throughput
5. Batch operations — amortize overhead
6. Use the right data structures — O(n) vs O(log n) matters
```

```go
// ✅ GOOD: Batch I/O operations
func readFileBuffered(path string) ([]byte, error) {
    f, err := os.Open(path)
    if err != nil {
        return nil, err
    }
    defer f.Close()
    
    // Buffered read — reduces syscalls
    const bufSize = 32 * 1024 // 32KB buffer
    reader := bufio.NewReaderSize(f, bufSize)
    return io.ReadAll(reader)
}

// ✅ GOOD: Object pool to reduce allocations
var bufferPool = sync.Pool{
    New: func() any {
        return make([]byte, 4096)
    },
}

func process() {
    buf := bufferPool.Get().([]byte)
    defer bufferPool.Put(buf)
    // Use buf without allocating new memory
}
```

---

## 5. Systems Programming Language Comparison

| Feature | Go | Rust | C |
|---|---|---|---|
| **Memory safety** | GC | Ownership/borrower | Manual |
| **Concurrency** | Goroutines + channels | async/await + threads | pthreads |
| **Compilation speed** | Very fast | Slow | Fast |
| **Binary size** | ~5-15MB | ~1-5MB | ~100KB |
| **Learning curve** | Low | High | Medium |
| **When to use** | CLI, servers, tools | Performance-critical, safe systems | Embedded, kernel, legacy |

---

## Quick Reference: Systems Programming by Node Type

| Node Type | Systems Programming Mapping |
|---|---|
| **Input** | Command-line parsing, file I/O, signal handling |
| **Logic** | Algorithms, data structures, performance-critical computation |
| **Database** | Custom storage engines, file-based persistence |
| **UI** | Terminal UI (bubbletea/tview), native rendering |
| **API** | Network I/O, IPC, protocol implementations, RPC |

---

*For deeper systems programming concepts, see Bible levels `05-systems-programming/`, `05-systems/`, and `06-os-kernel/` — memory management, concurrency, compilers, debuggers, file systems.*
