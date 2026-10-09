# 🌐 Browser Engineering — Rendering, DOM, JavaScript & WebAssembly

> Reference sheet for modern multi-process browser architecture, the HTML/CSS rendering pipeline, JavaScript engine internals, compositing, and WebAssembly runtime. Use this when building web applications, browser-based tools, or needing to optimize front-end performance.

**Source Bible Level:** 22 — Browser Engineering

---

## 🏗️ Multi-Process Architecture

Modern browsers (Chromium-derived) use a multi-process architecture for security, stability, and performance.

### Process Types

| Process | Responsibility | Isolation |
|---|---|---|
| **Browser** | Window management, UI chrome, infrastructure, policy | Single process |
| **Renderer** | Blink rendering engine, V8 JS execution | Per tab/frame (sandboxed) |
| **GPU** | Graphics, WebGL, hardware acceleration | Own process (driver crash isolation) |
| **Network** | HTTP/3, TLS, DNS, proxy, cache | Own process |
| **Utility** | Sandboxed helpers (data decoding, printing) | Per-task |
| **Extension** | Extension code execution | Elevated privileges |

**Inter-Process Communication:**
- **Mojo IPC** — Control messages and data streaming via message/data pipes
- **Mojo Shared Buffer** — Zero-copy transfer of large data (images, WebAssembly memory)

### Sandboxing By Platform

```cpp
// Linux sandbox via seccomp-bpf + namespaces
void InitializeSandbox() {
  // Create user/network/PID namespaces
  unshare(CLONE_NEWUSER | CLONE_NEWNET | CLONE_NEWIPC);

  // Install seccomp-bpf filter — whitelist only necessary syscalls
  struct sock_filter filter[] = {
    ALLOW_SYSCALL(read),
    ALLOW_SYSCALL(write),
    ALLOW_SYSCALL(mmap),
    ALLOW_SYSCALL(munmap),
    ALLOW_SYSCALL(exit_group),
    KILL_PROCESS,  // Default: kill on any unlisted syscall
  };
  struct sock_fprog prog = { .len = sizeof(filter) / sizeof(filter[0]), .filter = filter };
  syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, 0, &prog);
}
```

---

## 🧬 HTML Parsing & DOM Construction

The HTML tokenizer is a state machine based on the WHATWG HTML Living Standard with ~80 states for error-tolerant parsing.

### Tokenizer State Machine

```
DATA ──► TAG_OPEN ──► TAG_NAME ──► ATTRIBUTES ──► SELF_CLOSING
  │         │              │              │
  │         ▼              ▼              ▼
  └── CHAR  └── TAG_CLOSE └── ATTRIBUTE  └── CONSUME
```

### Minimal HTML Tokenizer (C++)

```cpp
enum class TokenType { DOCTYPE, StartTag, EndTag, Comment, Char, EOF_TOKEN };

struct Token {
  TokenType type;
  std::string tag_name;
  std::vector<std::pair<std::string, std::string>> attributes;
  std::string data;
};

class HTMLTokenizer {
  std::string input;
  size_t pos = 0;
  enum State { DATA, TAG_OPEN, TAG_NAME, BEFORE_ATTR_NAME, ATTR_NAME,
               AFTER_ATTR_NAME, BEFORE_ATTR_VALUE, ATTR_VALUE_DQ,
               ATTR_VALUE_SQ, ATTR_VALUE_UQ, SELF_CLOSING_START_TAG };
  State state = DATA;

public:
  Token nextToken() {
    while (pos < input.size()) {
      char c = input[pos++];
      switch (state) {
        case DATA:
          if (c == '<')  { state = TAG_OPEN; continue; }
          return {TokenType::Char, "", {}, std::string(1, c)};
        case TAG_OPEN:
          if (c == '/')  { state = TAG_NAME; return startEndTag(); }
          if (isalpha(c)) { state = TAG_NAME; return startStartTag(c); }
          // ... additional state transitions
      }
    }
    return {TokenType::EOF_TOKEN};
  }
};
```

### DOM Tree Construction

```javascript
// Simplified DOM node class
class Node {
  constructor(tagName, attributes = {}) {
    this.tagName = tagName;
    this.attributes = attributes;
    this.children = [];
    this.parentNode = null;
    this.style = {};       // Computed styles (populated by CSSOM)
    this.layout = null;    // Layout box (populated by layout phase)
  }

  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
  }

  getElementById(id) {
    if (this.attributes.id === id) return this;
    for (const child of this.children) {
      const result = child.getElementById(id);
      if (result) return result;
    }
    return null;
  }

  querySelectorAll(selector) {
    // CSS selector matching via specificity-based rule application
    const results = [];
    // Walk tree, apply selector matching
    return results;
  }
}

// Tree construction from token stream
function buildDOMTree(tokens) {
  const root = new Node('#document');
  const stack = [root];
  let current = root;

  for (const token of tokens) {
    switch (token.type) {
      case 'StartTag': {
        const node = new Node(token.tagName, token.attributes);
        current.appendChild(node);
        if (!token.selfClosing) {
          stack.push(node);
          current = node;
        }
        break;
      }
      case 'EndTag': {
        // Pop up to matching open tag
        while (stack.length > 0 && stack[stack.length - 1].tagName !== token.tagName) {
          stack.pop();
        }
        if (stack.length > 0) {
          stack.pop();
          current = stack[stack.length - 1];
        }
        break;
      }
      case 'Text': {
        current.appendChild(new TextNode(token.data));
        break;
      }
    }
  }
  return root;
}
```

---

## 🎨 CSS Engine & Layout

### Style Computation Pipeline

```
Raw CSS ──► Tokenizer ──► Parser ──► Style Rules ──► Cascade ──► Computed Styles
   │                                                      │
   ▼                                                      ▼
Selector parsing                                     Specificity sorting
Value parsing                                        Inheritance resolution
```

### Block Layout Engine

```typescript
interface LayoutBox {
  type: 'BlockNode' | 'InlineNode' | 'AnonymousBlock';
  node: DOMNode;
  dimensions: Rect;
  children: LayoutBox[];
}

interface Rect {
  x: number; y: number;
  width: number; height: number;
  padding: EdgeSizes;
  margin: EdgeSizes;
  border: EdgeSizes;
}

interface EdgeSizes {
  top: number; right: number; bottom: number; left: number;
}

function layout(node: DOMNode, containingBlock: Rect): LayoutBox {
  const box = createLayoutBox(node);

  // 1. Calculate width
  box.dimensions.width = calculateWidth(node, containingBlock);

  // 2. Calculate position (x, y) from containing block
  box.dimensions.x = containingBlock.x + box.dimensions.margin.left
    + containingBlock.padding.left + containingBlock.border.left;
  box.dimensions.y = containingBlock.y + box.dimensions.margin.top
    + containingBlock.padding.top + containingBlock.border.top;

  // 3. Layout children recursively
  for (const child of node.children) {
    if (isBlockElement(child)) {
      const childBox = layoutBlockChild(child, box);
      box.children.push(childBox);
      // Stack vertically
      box.dimensions.height += childBox.dimensions.height;
    } else if (isInlineElement(child)) {
      // Inline layout — line wrapping
      layoutInlineChildren(child, box);
    }
  }

  // 4. Calculate auto height from content
  if (box.dimensions.height === 0) {
    box.dimensions.height = calculateAutoHeight(node, box);
  }

  return box;
}
```

### Compositing & Rendering

```typescript
interface CompositorLayer {
  id: number;
  scrollOffset: { x: number; y: number };
  contents: PaintRecord[];
  // Each layer has its own backing store (GPU texture or CPU bitmap)
  backingStore: GPUTexture | null;
  // Layer properties for compositing
  transform: Matrix4;
  opacity: number;
  clipRect: Rect | null;
}

function compositeFrame(layers: CompositorLayer[]): Frame {
  // 1. Determine which layers need re-drawing (damage tracking)
  const damagedLayers = layers.filter(l => l.backingStore === null || l.hasPendingChanges);

  // 2. Rasterize damaged layers (CPU → GPU transfer)
  for (const layer of damagedLayers) {
    layer.backingStore = rasterizeLayer(layer);
  }

  // 3. Composite all layers in tree order
  const finalImage = new ImageBuffer(screenWidth, screenHeight);
  for (const layer of layers) {
    // Apply transforms, opacity, clipping
    finalImage.drawLayer(layer);
  }

  // 4. Present to display (swap buffers or send to GPU process)
  return new Frame(finalImage, layers);
}

// Layer promotion heuristics
function shouldPromoteToLayer(element: DOMNode): boolean {
  return (
    element.style.transform !== 'none' ||
    element.style.opacity < 1 ||
    element.style.willChange === 'transform' ||
    element.style.position === 'fixed' ||
    element.tagName === 'canvas' ||
    element.tagName === 'video'
  );
}
```

---

## ⚡ JavaScript Engine Internals (V8)

### Pipeline: Source → Optimized Machine Code

```
Source ──► Scanner ──► Parser ──► AST ──► Bytecode ──► Interpreter ──► Baseline ──► Optimized
                    │                  │   (Ignition)    Compiler     Compiler (TurboFan)
                    ▼                  ▼                  │                │
              Pre-parser          Scope chain          Profile            Deopt
             (lazy parse)        (early errors)      (feedback)        (bailout)
```

### Lazy Parsing Strategy

```typescript
class Parser {
  // Top-level: fully parsed immediately
  parseProgram(source: string): Program {
    const scanner = new Scanner(source);
    const tokens = scanner.scan();

    // Parse top-level declarations + immediate statements
    return this.parseTopLevel(tokens);
  }

  // Function bodies: skip on first pass
  preParseFunction(token: Token): FunctionOffset {
    const start = token.pos;
    // Quickly scan for matching '}' without building AST
    let depth = 1;
    while (depth > 0 && token.next()) {
      if (token.is('{')) depth++;
      if (token.is('}')) depth--;
    }
    return { start, end: token.pos };
  }

  // Full parse on first invocation
  parseFunction(offset: FunctionOffset): FunctionAST {
    const scanner = new Scanner(this.source.slice(offset.start, offset.end));
    // Build complete AST for this function
    return this.parseFunctionBody(scanner.scan());
  }
}
```

### Hidden Classes & Inline Caching

```typescript
// V8 optimizes object property access via hidden classes (maps/shapes)
interface HiddenClass {
  properties: Map<string, number>;   // property → offset
  transition: Map<string, HiddenClass>; // adding property → new class
  backPointer: HiddenClass | null;     // for deoptimization
  prototype: object | null;
}

// Object representation (two-pointer)
interface JSObject {
  map: HiddenClass;           // Shape/class pointer
  elements: Property[];      // Array-indexed properties
  properties: Property[];    // Named properties (by map offset)
}

// Inline Cache (IC) — monomorphic to polymorphic to megamorphic
class InlineCache {
  state: 'uninitialized' | 'monomorphic' | 'polymorphic' | 'megamorphic';
  cachedClass: HiddenClass | null;
  cachedOffset: number | null;
  polymorphicCache: Map<HiddenClass, number>;

  load(object: JSObject, property: string): any {
    switch (this.state) {
      case 'uninitialized':
        this.cachedClass = object.map;
        this.cachedOffset = object.map.properties.get(property);
        this.state = 'monomorphic';
        return object.properties[this.cachedOffset];
      case 'monomorphic':
        if (object.map === this.cachedClass) {
          return object.properties[this.cachedOffset]; // Fast path!
        }
        // Transition to polymorphic
        this.state = 'polymorphic';
        this.polymorphicCache = new Map();
        this.polymorphicCache.set(this.cachedClass!, this.cachedOffset!);
        return this.loadPolymorphic(object, property);
      case 'polymorphic':
        return this.loadPolymorphic(object, property);
      default: // megamorphic — full dictionary lookup
        return object.map.properties.get(property);
    }
  }
}
```

### Garbage Collection (Orinoco + Oilpan)

```typescript
class V8Heap {
  // Generational: Young (nursery) + Old generation
  youngGeneration: SemiSpace;   // Two semi-spaces (from-space, to-space)
  oldGeneration: MarkSweepSpace;
  largeObjectSpace: LargeObjectSpace;

  allocate(size: number): Address {
    // Try bump-pointer allocation in young generation
    const addr = this.youngGeneration.bumpAllocate(size);
    if (addr) return addr;

    // Young GC (Scavenge) — minor GC
    this.scavenge();

    // Retry
    const retry = this.youngGeneration.bumpAllocate(size);
    if (retry) return retry;

    // Fall back to old generation
    return this.oldGeneration.allocate(size);
  }

  scavenge(): void {
    // Copy live objects from from-space to to-space
    // Objects surviving 2+ GCs get promoted to old generation
    // Then swap semi-spaces
  }
}

// Concurrent marking (Orinoco)
function concurrentMark(roots: object[]) {
  // 1. Mark roots as gray
  // 2. Worker threads traverse gray objects in parallel
  // 3. White objects are unreachable → sweep
  // 4. Incremental sweeping with write barriers
}
```

---

## 🧩 WebAssembly Runtime

### Module Compilation Pipeline

```wat
(module
  (func $add (param i32 i32) (result i32)
    local.get 0
    local.get 1
    i32.add
  )
  (export "add" (func $add))
)
```

### Wasm Runtime Architecture

```typescript
interface WasmModule {
  types: FuncType[];
  imports: Import[];
  functions: WasmFunction[];
  memories: Memory[];
  tables: Table[];
  globals: Global[];
  exports: Export[];
  // Compiled native code for each function
  code: Map<number, NativeCode>;
}

interface WasmFunction {
  locals: ValueType[];
  body: Uint8Array;        // Raw bytecode
  compiled: NativeCode;    // JIT-compiled or AOT
}

class WasmVm {
  stack: Value[] = [];
  memory: ArrayBuffer;
  controlStack: ControlFrame[] = [];

  executeFunction(func: WasmFunction, args: Value[]): void {
    // Push arguments
    for (const arg of args) this.stack.push(arg);

    const code = func.compiled || this.compile(func);

    // If using baseline interpreter:
    this.interpretBytecode(func.body);
  }

  interpretBytecode(bytecode: Uint8Array): void {
    let pc = 0;
    while (pc < bytecode.length) {
      const opcode = bytecode[pc++];
      switch (opcode) {
        case 0x00: // unreachable — trap
          throw new Trap();
        case 0x20: { // local.get
          const idx = this.readLEB128(bytecode, pc);
          this.stack.push(this.locals[idx]);
          break;
        }
        case 0x6a: { // i32.add
          const b = this.stack.pop() as number;
          const a = this.stack.pop() as number;
          this.stack.push((a + b) >>> 0); // i32 wrapping
          break;
        }
        // ... hundreds of opcodes
      }
    }
  }
}

// Liftoff — fast baseline compiler (single-pass, no IR)
interface LiftoffCompiler {
  // Registers for each WebAssembly local
  localRegs: Register[];
  // Machine code emitter
  masm: MacroAssembler;

  compileFunction(func: WasmFunction): NativeCode {
    for (const instr of func.body) {
      // Directly emit machine code, no intermediate representation
      switch (instr.opcode) {
        case 'local.get':
          // mov ${target_reg}, [rbp + offset_of_local]
          this.masm.emit(MOV, this.localRegs[instr.immediate], rbp, instr.immediate * 8);
          break;
        case 'i32.add':
          this.masm.emit(ADD, regA, regB);
          break;
        // One assembly instruction per wasm instruction
      }
    }
    this.masm.emit(RET);
    return this.masm.finalize();
  }
}
```

---

## 🌐 Network Stack & Security

```typescript
class BrowserNetworkStack {
  // HTTP/3 (QUIC) — connection multiplexing + 0-RTT
  quicConnections: Map<string, QUICConnection>;

  async fetch(url: URL, init: RequestInit): Promise<Response> {
    // 1. HSTS check — force HTTPS if domain is preloaded
    if (HSTS_PRELOAD_LIST.includes(url.hostname) && url.protocol !== 'https:') {
      url = new URL(`https://${url.host}${url.pathname}`);
    }

    // 2. CORS preflight for cross-origin non-simple requests
    if (needsPreflight(init.method, init.headers)) {
      await this.sendPreflight(url, init);
    }

    // 3. HTTP cache lookup
    const cached = await this.httpCache.match(url, init);
    if (cached && !isStale(cached)) return cached.response;

    // 4. DNS resolution (cached, with async prefetch)
    const ip = await this.dnsResolver.resolve(url.hostname);

    // 5. QUIC or TCP+TLS connection
    const conn = await this.establishConnection(ip, url.port || 443);

    // 6. Send request & receive response
    const response = await conn.sendRequest(url, init);

    // 7. Cache response
    await this.httpCache.store(url, response);

    // 8. CSP/COOP/COEP policy enforcement
    this.enforceSecurityPolicies(url, response);

    return response;
  }

  // Connection coalescing
  async establishConnection(ip: string, port: number): Promise<Connection> {
    // Try to reuse existing connection to same origin
    const key = `${ip}:${port}`;
    if (this.quicConnections.has(key)) {
      return this.quicConnections.get(key)!;
    }
    // Create new QUIC connection
    const conn = new QUICConnection(ip, port);
    await conn.handshake();
    this.quicConnections.set(key, conn);
    return conn;
  }
}
```

---

## 📊 Quick Reference: Browser Engineering by Node Type

| Node Type | Relevant Concepts | Implementation Notes |
|---|---|---|
| **Input** | HTTP fetch, DNS, CORS, HSTS, preload scanner | Use fetch API with proper caching headers; implement preload scanner for speculative parsing |
| **Logic** | Parser state machines, V8 hidden classes, inline caching | Prefer monomorphic property access for performance; use typed arrays for large data |
| **Database** | HTTP cache (memory + disk), Service Worker cache API | Implement Cache-First or Network-First strategies; use IndexedDB for larger storage |
| **UI** | DOM construction, style computation, layout, compositing | Minimize layout thrashing; promote animations to compositor layers; use content-visibility for below-fold content |
| **API** | Service Worker, Push API, WebSocket, WebTransport | Register SW early; use Workbox for caching strategies; implement push event handlers |
| **Output** | Canvas 2D, WebGL, WebGPU, OffscreenCanvas | Use OffscreenCanvas for worker rendering; batch draw calls; use WebGPU for compute workloads |

---

*For deeper technical details on any browser engineering concept, see Bible Level 22 — Browser Engineering, including rendering engine internals, V8 optimization strategies, and web security standards.*
