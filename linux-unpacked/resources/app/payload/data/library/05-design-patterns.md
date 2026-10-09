# 🎨 Design Patterns for Generated Code

> Common design patterns used when generating application code from node designs.
> Each pattern includes a description, when to use it, and code examples.

---

## 1. Module Pattern

### Purpose
Encapsulate related functionality into self-contained modules with clear interfaces.

### When to Use
- Every node in the design becomes a module
- Separating concerns between different app layers
- Organizing code by feature

```typescript
// modules/media-library.ts
export interface MediaLibrary {
  scan(): Promise<MediaItem[]>;
  get(id: string): Promise<MediaItem | null>;
  search(query: string): Promise<MediaItem[]>;
}

export function createMediaLibrary(db: Database): MediaLibrary {
  // Return an object with the interface — no class needed
  return {
    async scan() { /* ... */ },
    async get(id) { /* ... */ },
    async search(query) { /* ... */ },
  };
}
```

---

## 2. Repository Pattern

### Purpose
Abstract data storage behind a clean interface, making it easy to swap storage backends.

### When to Use
- Any database/datastore node
- When you might migrate storage (SQLite → PostgreSQL)
- For testability (mock the repository)

```typescript
// db/repositories/user-repository.ts
export interface UserRepository {
  findById(id: number): Promise<User | null>;
  findByEmail(email: string): Promise<User | null>;
  create(data: CreateUserInput): Promise<User>;
  update(id: number, data: Partial<User>): Promise<User>;
  delete(id: number): Promise<boolean>;
}

// SQLite implementation
export function createSqliteUserRepository(db: Database.Database): UserRepository {
  const stmts = {
    findById: db.prepare('SELECT * FROM users WHERE id = ?'),
    findByEmail: db.prepare('SELECT * FROM users WHERE email = ?'),
    create: db.prepare('INSERT INTO users (name, email) VALUES (?, ?)'),
    // ...
  };

  return {
    async findById(id) { return stmts.findById.get(id) as User | null; },
    async findByEmail(email) { return stmts.findByEmail.get(email) as User | null; },
    async create(data) {
      const result = stmts.create.run(data.name, data.email);
      return this.findById(result.lastInsertRowid as number) as Promise<User>;
    },
    // ...
  };
}
```

---

## 3. Service Layer Pattern

### Purpose
Encapsulate business logic between the API layer and data layer. Routes call services, services call repositories.

### When to Use
- Any app with more than trivial logic
- When business rules need to be enforced
- When you need to coordinate multiple operations

```typescript
// services/user-service.ts
export class UserService {
  constructor(
    private readonly users: UserRepository,
    private readonly logger: Logger,
  ) {}

  async createUser(input: CreateUserInput): Promise<User> {
    // 1. Validate business rules
    if (input.role === 'admin' && !input.inviteCode) {
      throw new AppError('Admin registration requires invite code', 'ERR_INVITE_REQUIRED');
    }

    // 2. Check for duplicates
    const existing = await this.users.findByEmail(input.email);
    if (existing) {
      throw new AppError('Email already registered', 'ERR_DUPLICATE_EMAIL');
    }

    // 3. Execute
    const user = await this.users.create(input);

    // 4. Side effects (email notification, audit log, etc.)
    this.logger.info({ userId: user.id }, 'User created');

    return user;
  }
}
```

### Node-to-Service Mapping
```
Input Node  → Route handler (validate HTTP/CLI input)
Logic Node  → Service layer (business logic here)
Database Node → Repository layer (data access here)
API Node    → External service client (injected into services)
UI Node     → View/Presenter (renders data from services)
```

---

## 4. Pipeline / Chain Pattern

### Purpose
Process data through a sequence of steps, where each step transforms the data and passes it to the next.

### When to Use
- Multi-step data processing
- Media transcoding pipelines
- ETL (Extract, Transform, Load) workflows
- Any flow with a clear input → process → output path

```typescript
// Pipeline pattern
interface PipelineStep<I, O> {
  execute(input: I): Promise<O>;
}

class Pipeline {
  private steps: PipelineStep<unknown, unknown>[] = [];

  addStep<I, O>(step: PipelineStep<I, O>): this {
    this.steps.push(step as PipelineStep<unknown, unknown>);
    return this;
  }

  async execute<I, O>(initial: I): Promise<O> {
    let result: unknown = initial;
    for (const step of this.steps) {
      result = await step.execute(result);
    }
    return result as O;
  }
}

// Usage
const mediaPipeline = new Pipeline()
  .addStep(new FileScanner())
  .addStep(new MetadataExtractor())
  .addStep(new ThumbnailGenerator())
  .addStep(new DatabaseWriter());

const result = await mediaPipeline.execute('/path/to/media');
```

---

## 5. Observer / Event Pattern

### Purpose
Decouple components by emitting and listening to events. When one component does something, others can react without knowing about each other.

### When to Use
- UI updates in response to data changes
- Logging and monitoring
- Plugin/extension systems
- Real-time features

```typescript
// Simple event emitter
type EventHandler = (data: unknown) => void;

class EventBus {
  private handlers = new Map<string, EventHandler[]>();

  on(event: string, handler: EventHandler): void {
    const handlers = this.handlers.get(event) ?? [];
    handlers.push(handler);
    this.handlers.set(event, handlers);
  }

  emit(event: string, data: unknown): void {
    const handlers = this.handlers.get(event);
    if (handlers) {
      for (const handler of handlers) {
        try { handler(data); } catch (err) {
          console.error(`Event handler failed for ${event}:`, err);
        }
      }
    }
  }

  off(event: string, handler: EventHandler): void {
    const handlers = this.handlers.get(event);
    if (handlers) {
      this.handlers.set(event, handlers.filter(h => h !== handler));
    }
  }
}

// Usage
const bus = new EventBus();
bus.on('file:scanned', (file) => updateUI(file));
bus.on('file:scanned', (file) => logScan(file));
scanner.onFileFound((file) => bus.emit('file:scanned', file));
```

---

## 6. Strategy Pattern

### Purpose
Select an algorithm at runtime. Different strategies for different scenarios.

### When to Use
- Multiple output formats (JSON, HTML, Markdown)
- Different validation rules for different input types
- Pluggable rendering backends

```typescript
// Strategy interface
interface OutputFormatter {
  format(data: ReportData): string;
  mimeType: string;
}

// Concrete strategies
class JsonFormatter implements OutputFormatter {
  mimeType = 'application/json';
  format(data: ReportData): string {
    return JSON.stringify(data, null, 2);
  }
}

class MarkdownFormatter implements OutputFormatter {
  mimeType = 'text/markdown';
  format(data: ReportData): string {
    return `# ${data.title}\n\n${data.body}`;
  }
}

// Strategy selector
const formatters: Record<string, OutputFormatter> = {
  json: new JsonFormatter(),
  md: new MarkdownFormatter(),
};

export function formatReport(data: ReportData, format: string): string {
  const formatter = formatters[format];
  if (!formatter) throw new AppError(`Unknown format: ${format}`, 'ERR_FORMAT');
  return formatter.format(data);
}
```

---

## 7. Adapter Pattern

### Purpose
Wrap external dependencies behind an interface your application controls.

### When to Use
- Every external API call
- System command execution
- File system operations (for testability)

```typescript
// Adapter interface (your app controls this)
interface MediaPlayer {
  play(path: string): Promise<void>;
  pause(): Promise<void>;
  stop(): Promise<void>;
  getStatus(): PlayerStatus;
}

// Concrete adapter for VLC
class VlcAdapter implements MediaPlayer {
  private process: ChildProcess | null = null;

  async play(path: string): Promise<void> {
    this.process = spawn('vlc', ['--intf', 'rc', path]);
    // Handle process events
  }

  async pause(): Promise<void> {
    if (this.process) {
      this.process.stdin?.write('pause\n');
    }
  }

  async stop(): Promise<void> {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
  }

  getStatus(): PlayerStatus {
    // Parse VLC remote control output
    return { playing: this.process !== null };
  }
}

// Mock adapter for testing
class MockMediaPlayer implements MediaPlayer {
  private status: PlayerStatus = { playing: false };

  async play(_path: string): Promise<void> {
    this.status = { playing: true };
  }
  async pause(): Promise<void> { this.status = { playing: false }; }
  async stop(): Promise<void> { this.status = { playing: false }; }
  getStatus(): PlayerStatus { return this.status; }
}
```

---

## 8. Builder Pattern

### Purpose
Construct complex objects step by step. Especially useful for building configurations, queries, and reports.

### When to Use
- Building SQL queries dynamically
- Constructing report configurations
- Assembly of complex output documents

```typescript
// Query builder (simplified)
class QueryBuilder {
  private table = '';
  private where: string[] = [];
  private orderBy = '';
  private limit = 0;

  from(table: string): this {
    this.table = table;
    return this;
  }

  where(condition: string, params: unknown[]): this {
    this.where.push(condition);
    return this;
  }

  order(column: string, dir: 'ASC' | 'DESC' = 'ASC'): this {
    this.orderBy = `${column} ${dir}`;
    return this;
  }

  take(limit: number): this {
    this.limit = limit;
    return this;
  }

  build(): { sql: string; params: unknown[] } {
    let sql = `SELECT * FROM ${this.table}`;
    if (this.where.length > 0) sql += ` WHERE ${this.where.join(' AND ')}`;
    if (this.orderBy) sql += ` ORDER BY ${this.orderBy}`;
    if (this.limit > 0) sql += ` LIMIT ${this.limit}`;
    return { sql, params: [] };
  }
}

// Usage
const query = new QueryBuilder()
  .from('users')
  .where('age >= ?', [18])
  .where('active = ?', [true])
  .order('name', 'ASC')
  .take(50)
  .build();
```

---

## 9. Factory Pattern

### Purpose
Create objects without specifying the exact class. The factory decides which implementation to return based on context.

### When to Use
- Creating different types of nodes from a design
- Platform-specific implementations
- Creating database connections based on config

```typescript
interface DatabaseFactory {
  createConnection(config: DbConfig): Database;
}

class SqliteFactory implements DatabaseFactory {
  createConnection(config: DbConfig): Database {
    return new Database(config.path ?? './data.db');
  }
}

class PostgresFactory implements DatabaseFactory {
  createConnection(config: DbConfig): Database {
    return new Pool({ connectionString: config.url });
  }
}

export function getDatabaseFactory(type: DbType): DatabaseFactory {
  switch (type) {
    case 'sqlite': return new SqliteFactory();
    case 'postgres': return new PostgresFactory();
    default: throw new AppError(`Unknown database type: ${type}`, 'ERR_DB_TYPE');
  }
}
```

---

## 10. Composite Pattern

### Purpose
Treat individual objects and compositions uniformly. A group of items can be processed the same way as a single item.

### When to Use
- Nested UI components
- Hierarchical data structures
- File system trees
- Node graph traversal

```typescript
interface FileSystemNode {
  name: string;
  getSize(): number;
  list(): string[];
}

class File implements FileSystemNode {
  constructor(
    public name: string,
    private size: number,
  ) {}
  getSize(): number { return this.size; }
  list(): string[] { return [this.name]; }
}

class Directory implements FileSystemNode {
  constructor(
    public name: string,
    private children: FileSystemNode[] = [],
  ) {}
  getSize(): number {
    return this.children.reduce((sum, child) => sum + child.getSize(), 0);
  }
  list(): string[] {
    return this.children.flatMap(child => child.list().map(
      name => `${this.name}/${name}`
    ));
  }
  add(child: FileSystemNode): void { this.children.push(child); }
}
```

---

## Quick Reference: Pattern Selection

| When building... | Use pattern(s) |
|---|---|
| A data processing pipeline | Pipeline, Module |
| A CRUD application | Repository, Service Layer |
| A media streaming app | Pipeline, Observer, Adapter |
| A CLI tool with multiple output formats | Strategy, Module |
| A web app with external API calls | Adapter, Service Layer |
| A system diagnostic tool | Module, Strategy, Builder |
| An app with complex configuration | Builder, Factory |
| A real-time collaboration feature | Observer, Pipeline |

---

*For more architectural patterns, see `bible-reference/01-foundations/` (design patterns section) and `bible-reference/07-ai-ml/` (LLM pattern guide)*
