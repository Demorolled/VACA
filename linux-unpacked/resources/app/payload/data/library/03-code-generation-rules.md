# 📝 Code Generation Rules

> Rules and patterns for generating clean, idiomatic, production-ready code from node designs.
> These rules enforce the Design Manifesto's quality standards.

---

## 1. Universal Code Rules

These rules apply to ALL generated code, regardless of language:

### 1.1 Structure Rules

| Rule | Enforced | Description |
|---|---|---|
| **Single Responsibility** | Always | One function = one job. Max 50 lines per function. |
| **Early Returns** | Always | Avoid deeply nested conditionals. Guard clauses first. |
| **No Magic Values** | Always | Extract strings/numbers to named constants. |
| **Error Handling** | Always | Every fallible operation must handle errors explicitly. |
| **Type Annotations** | Always | Every parameter and return value must be typed. |
| **No `any`** | Always | Use specific types or `unknown` with type guards. |
| **No Dead Code** | Always | Remove unused imports, variables, and functions. |
| **No Console.log** | Always | Use proper logging library for production code. |
| **Async/Await** | Always | Prefer `async/await` over raw promises. |
| **No Nested > 3** | Always | Maximum 3 levels of nesting (use early returns). |

### 1.2 Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Variables | `camelCase` | `userName`, `itemCount` |
| Functions | `verbNoun()` | `getUser()`, `processFile()` |
| Classes | `PascalCase` | `UserService`, `FileProcessor` |
| Interfaces | `PascalCase` | `UserInput`, `ProcessResult` |
| Types | `PascalCase` | `AppConfig`, `NodeType` |
| Files | `kebab-case` | `user-service.ts`, `db-handler.go` |
| Constants | `UPPER_CASE` | `MAX_RETRY_COUNT`, `API_BASE_URL` |
| Private | `_prefix` | `_internalHelper()`, `_cache` |

### 1.3 Error Handling Pattern

```typescript
// ✅ GOOD: Explit error handling with typed errors
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'AppError';
  }
}

export function processData(input: unknown): Result {
  // Guard clauses first
  if (!input) throw new AppError('Input required', 'ERR_EMPTY_INPUT');
  if (typeof input !== 'object') throw new AppError('Invalid input type', 'ERR_TYPE');

  try {
    const result = transform(input);
    return { success: true, data: result };
  } catch (err) {
    // Wrap unexpected errors
    throw new AppError(
      'Processing failed',
      'ERR_PROCESS',
      { original: (err as Error).message }
    );
  }
}

// ❌ BAD: Silent error swallowing
function processData(input: unknown) {
  try {
    // ...
  } catch {
    // Silently ignored!
  }
}
```

---

## 2. Language-Specific Rules

### 2.1 TypeScript Rules

```typescript
// ✅ Use strict types, never any
type Result<T> = { success: true; data: T } | { success: false; error: string };

// ✅ Prefer interfaces for object shapes
interface UserConfig {
  readonly name: string;
  readonly maxItems: number;
}

// ✅ Use const assertions for configs
export const DEFAULTS = {
  port: 3000,
  host: 'localhost',
} as const;

// ✅ Utility types over manual mapping
type UserKeys = keyof UserConfig;
type PartialConfig = Partial<UserConfig>;

// ✅ Discriminated unions for state
type AppState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: unknown }
  | { status: 'error'; error: string };
```

### 2.2 Python Rules

```python
# ✅ Type hints on everything
from typing import Optional, Protocol

class Processor(Protocol):
    def process(self, data: bytes) -> bytes: ...

# ✅ Dataclasses for data containers
@dataclass(frozen=True)
class Config:
    host: str
    port: int = 3000

# ✅ Explit error types
class AppError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code

# ✅ Context managers for resources
with open('file.txt', 'r') as f:
    content = f.read()
```

### 2.3 Go Rules

```go
// ✅ Explit error handling
func Process(input string) (Result, error) {
    if input == "" {
        return Result{}, errors.New("input cannot be empty")
    }
    result, err := transform(input)
    if err != nil {
        return Result{}, fmt.Errorf("transform failed: %w", err)
    }
    return result, nil
}

// ✅ Clean interface definitions
type Storage interface {
    Get(id string) (Item, error)
    Put(item Item) error
    Delete(id string) error
}

// ✅ Constructor functions
func NewService(storage Storage) *Service {
    return &Service{
        storage: storage,
        logger:  slog.New(slog.NewJSONHandler(os.Stdout, nil)),
    }
}
```

---

## 3. File Generation Rules

### 3.1 File Organization

```
src/
├── index.ts              # Entry point (thin — just bootstraps)
├── types.ts              # Shared types/interfaces
├── config.ts             # Configuration constants
├── services/             # Business logic (one file per service)
│   ├── user-service.ts
│   └── file-service.ts
├── db/                   # Database layer
│   ├── schema.ts
│   └── queries.ts
└── utils/                # Shared utilities
    └── errors.ts
```

### 3.2 File Header Template

```typescript
/**
 * [filename] — [purpose of this file]
 * 
 * This file is auto-generated by Visual AI Architect.
 * Last generated: [timestamp]
 */

// External imports (grouped by source)
import { z } from 'zod';
import Database from 'better-sqlite3';

// Internal imports
import type { AppConfig } from '../types';
import { AppError } from '../utils/errors';

// Constants
const MAX_RETRIES = 3;

// Types/Interfaces (if not in shared types.ts)
export interface LocalType {
  // ...
}

// Implementation
export function doSomething(): void {
  // ...
}
```

### 3.3 Import Ordering

```
1. Node built-ins    (fs, path, os)
2. Third-party       (express, zod, better-sqlite3)
3. Internal modules  (../services, ../types)
4. Types             (import type { ... })
```

---

## 4. Testing Rules

### 4.1 Test File Placement

```
src/
├── services/
│   ├── user-service.ts
│   └── user-service.test.ts    ← Co-located with source
```

### 4.2 Test Pattern

```typescript
// ✅ Describes behavior, not implementation
describe('UserService', () => {
  describe('createUser', () => {
    it('should create a user with valid input', async () => {
      const result = await userService.createUser(validInput);
      expect(result).toMatchObject({ name: 'test', email: 'test@example.com' });
    });

    it('should reject invalid email', async () => {
      await expect(
        userService.createUser({ ...validInput, email: 'bad' })
      ).rejects.toThrow('Invalid email');
    });

    it('should handle database errors gracefully', async () => {
      // Mock failure
      mockDb.prepare.mockRejectedValue(new Error('DB down'));
      await expect(
        userService.createUser(validInput)
      ).rejects.toThrow(AppError);
    });
  });
});
```

### 4.3 Test Coverage Requirements

| Layer | Coverage Goal | What to Test |
|---|---|---|
| Input nodes | 100% of validation rules | Valid inputs, invalid inputs, edge cases |
| Logic nodes | 100% of branches | Happy path, error paths, edge cases |
| Database nodes | 90%+ | CRUD operations, error states, transactions |
| UI nodes | 80%+ | Render states, user interactions, error displays |
| API nodes | 90%+ | Success, failure, timeout, auth errors |

---

## 5. Security Rules

### 5.1 Input Validation

```typescript
// ✅ Validate everything at boundaries
function sanitizePath(userInput: string): string {
  // Prevent path traversal
  const sanitized = path.basename(userInput);
  if (sanitized.includes('..') || sanitized.includes('/')) {
    throw new AppError('Invalid path', 'ERR_PATH');
  }
  return sanitized;
}

// ✅ SQL injection prevention (use parameterized queries)
const stmt = db.prepare('SELECT * FROM users WHERE id = ?');
stmt.get(userId);  // NOT: `WHERE id = '${userId}'`
```

### 5.2 File Operations

```typescript
// ✅ Atomic writes
function writeFileAtomic(filePath: string, data: string): void {
  const tmpPath = `${filePath}.tmp`;
  fs.writeFileSync(tmpPath, data, 'utf-8');
  fs.renameSync(tmpPath, filePath);  // Atomic on Unix
}

// ✅ Proper permissions
fs.writeFileSync(configPath, content, { mode: 0o600 });  // Owner-only
```

---

## 6. Code Review Checklist

Before finalizing generated code, verify:

- [ ] All types are explicit (no `any`)
- [ ] Every function has error handling
- [ ] No magic numbers/strings
- [ ] Functions are ≤ 50 lines
- [ ] No nested conditionals > 3 levels
- [ ] No commented-out code
- [ ] No `TODO`/`FIXME` in production code
- [ ] All imports are used (no orphans)
- [ ] File naming follows `kebab-case`
- [ ] Tests cover happy and error paths
- [ ] Database queries use parameterized statements
- [ ] File paths are sanitized
- [ ] Logging is used instead of `console.log`
- [ ] Async operations have error boundaries

---

*For language-specific deep dives, see `bible-reference/01-foundations/` and `bible-reference/05-systems-programming/`*
