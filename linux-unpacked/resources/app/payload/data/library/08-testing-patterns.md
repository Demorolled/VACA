# 🧪 Testing Patterns

> Comprehensive testing strategies for generated applications.
> Covers unit, integration, end-to-end, and property-based testing across TypeScript, Python, and Go.

---

## 1. Testing Philosophy

### The Testing Trophy (Not Pyramid)

```
         ╱  E2E Tests  ╲         ← Few: critical user journeys
        ╱  Integration   ╲        ← Many: service boundaries, DB, APIs
       ╱   Unit Tests     ╲       ← Lots: pure logic, validation
      ╱  Static Analysis   ╲      ← All: types, linting, formatting
```

For generated apps, **integration tests are the sweet spot** — they verify that the generated wiring between nodes actually works.

### Code Coverage Targets (from Manifesto)

| Layer | Minimum | Target | What to Cover |
|---|---|---|---|
| Input/Validation | 90% | 100% | Valid, invalid, edge cases, boundary values |
| Logic (pure) | 90% | 100% | All branches, error paths, edge cases |
| Logic (I/O) | 70% | 85% | Happy path, error handling, timeout |
| Database | 80% | 90% | CRUD, constraints, transactions, migration |
| API integration | 75% | 85% | Success, failure, retry, auth, rate limit |
| UI components | 70% | 80% | Render states, user interactions, error display |

---

## 2. Test Structure & Organization

### 2.1 File Placement

Tests are always **co-located** with source files:

```
src/
├── services/
│   ├── user-service.ts
│   ├── user-service.test.ts        ← Unit tests
│   └── user-service.integration.test.ts  ← Integration tests
├── db/
│   ├── repository.ts
│   ├── repository.test.ts
│   └── repository.integration.test.ts
└── api/
    ├── router.ts
    └── router.test.ts
```

### 2.2 Test Naming Conventions

| Language | Unit Test | Integration Test | E2E Test |
|---|---|---|---|
| TypeScript | `*.test.ts` | `*.integration.test.ts` | `*.e2e.test.ts` |
| Python | `test_*.py` | `test_*_integration.py` | `test_*_e2e.py` |
| Go | `*_test.go` | `*_integration_test.go` | `*_e2e_test.go` |

### 2.3 Test Description Style

```typescript
// ✅ Behavior-driven descriptions
describe('UserService', () => {
  describe('createUser', () => {
    it('should create a user with valid input', async () => { ... });
    it('should reject duplicate email', async () => { ... });
    it('should throw AppError when database fails', async () => { ... });
  });
});

// ❌ Implementation-focused descriptions
describe('UserService', () => {
  describe('createUser method', () => {
    it('should call repository.create', async () => { ... });
  });
});
```

---

## 3. Language-Specific Testing Frameworks

### 3.1 TypeScript: Vitest

```typescript
// user-service.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dependencies
const mockRepo = {
  findByEmail: vi.fn(),
  create: vi.fn(),
};

const userService = new UserService(mockRepo, mockLogger);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('createUser', () => {
  const validInput = { name: 'Alice', email: 'alice@example.com' };

  it('should create user successfully', async () => {
    mockRepo.findByEmail.mockResolvedValue(null);
    mockRepo.create.mockResolvedValue({ id: 1, ...validInput });

    const result = await userService.createUser(validInput);

    expect(result).toMatchObject({ name: 'Alice' });
    expect(mockRepo.create).toHaveBeenCalledWith(validInput);
  });

  it('should reject duplicate email', async () => {
    mockRepo.findByEmail.mockResolvedValue({ id: 2, email: validInput.email });

    await expect(userService.createUser(validInput)).rejects.toThrow(AppError);
    expect(mockRepo.create).not.toHaveBeenCalled();
  });

  it('should handle unexpected errors', async () => {
    mockRepo.findByEmail.mockRejectedValue(new Error('DB connection failed'));

    await expect(userService.createUser(validInput)).rejects.toThrow(AppError);
  });
});
```

**Vitest Configuration** (`vitest.config.ts`):
```typescript
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/**/*.integration.test.ts'],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
        statements: 80,
      },
    },
    setupFiles: ['./test/setup.ts'],
  },
});
```

### 3.2 Python: pytest

```python
# test_user_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.find_by_email = AsyncMock()
    repo.create = AsyncMock()
    return repo

@pytest.fixture
def service(mock_repo):
    return UserService(mock_repo, MockLogger())

class TestCreateUser:
    valid_input = {"name": "Alice", "email": "alice@example.com"}

    @pytest.mark.asyncio
    async def test_creates_user_successfully(self, service, mock_repo):
        mock_repo.find_by_email.return_value = None
        mock_repo.create.return_value = {"id": 1, **self.valid_input}

        result = await service.create_user(self.valid_input)

        assert result["name"] == "Alice"
        mock_repo.create.assert_called_once_with(self.valid_input)

    @pytest.mark.asyncio
    async def test_rejects_duplicate_email(self, service, mock_repo):
        mock_repo.find_by_email.return_value = {"id": 2}
        
        with pytest.raises(AppError) as exc:
            await service.create_user(self.valid_input)
        assert "already registered" in str(exc.value)
        mock_repo.create.assert_not_called()
```

**pytest Configuration** (`pyproject.toml`):
```toml
[tool.pytest.ini_options]
testpaths = ["src"]
python_files = ["test_*.py", "*_test.py"]
asyncio_mode = "auto"

[tool.coverage.run]
source = ["src"]
omit = ["*/test_*", "*/tests/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

### 3.3 Go: Standard Testing + Testify

```go
// user_service_test.go
package service

import (
	"testing"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

type MockUserRepo struct {
	mock.Mock
}

func (m *MockUserRepo) FindByEmail(email string) (*User, error) {
	args := m.Called(email)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*User), args.Error(1)
}

func (m *MockUserRepo) Create(input CreateUserInput) (*User, error) {
	args := m.Called(input)
	return args.Get(0).(*User), args.Error(1)
}

func TestCreateUser_Success(t *testing.T) {
	repo := new(MockUserRepo)
	repo.On("FindByEmail", "alice@example.com").Return(nil, nil)
	repo.On("Create", validInput).Return(&User{ID: 1, Name: "Alice"}, nil)

	service := NewUserService(repo)
	result, err := service.CreateUser(validInput)

	require.NoError(t, err)
	assert.Equal(t, "Alice", result.Name)
	repo.AssertExpectations(t)
}

func TestCreateUser_DuplicateEmail(t *testing.T) {
	repo := new(MockUserRepo)
	repo.On("FindByEmail", "alice@example.com").Return(&User{ID: 2}, nil)

	service := NewUserService(repo)
	_, err := service.CreateUser(validInput)

	assert.Error(t, err)
	assert.Contains(t, err.Error(), "already registered")
}
```

---

## 4. Test Categories & When to Use Each

### 4.1 Unit Tests (Fast, Isolated)

```typescript
// Pure logic — no mocks needed
describe('transformItem', () => {
  it('should trim whitespace from names', () => {
    expect(transformItem({ name: '  Alice  ' }).name).toBe('Alice');
  });

  it('should derive correct status', () => {
    expect(deriveStatus({ active: true, verified: true })).toBe('active');
    expect(deriveStatus({ active: false })).toBe('inactive');
    expect(deriveStatus({ active: true, verified: false })).toBe('pending');
  });

  it('should handle missing optional fields', () => {
    expect(() => transformItem({})).not.toThrow();
  });
});
```

### 4.2 Integration Tests (Real Dependencies)

```typescript
// db/queries.integration.test.ts
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Database from 'better-sqlite3';
import { createItem, getItem } from './queries';
import { initializeDatabase } from './schema';

// Use a temporary database
const db = initializeDatabase(':memory:');

describe('ItemRepository', () => {
  it('should create and retrieve an item', () => {
    const item = createItem(db, 'test-item');
    expect(item.id).toBeGreaterThan(0);
    expect(item.name).toBe('test-item');
  });

  it('should return undefined for non-existent items', () => {
    expect(getItem(db, 999)).toBeUndefined();
  });

  it('should enforce NOT NULL constraint', () => {
    expect(() => createItem(db, null as unknown as string)).toThrow();
  });
});
```

### 4.3 Snapshot Tests (UI / Output)

```typescript
// report.test.ts
describe('ReportBuilder', () => {
  it('should generate consistent markdown output', () => {
    const report = buildReport(sampleData, 'markdown');
    expect(report).toMatchSnapshot();
  });

  it('should generate consistent JSON output', () => {
    const report = buildReport(sampleData, 'json');
    expect(JSON.parse(report)).toMatchSnapshot();
  });
});
```

### 4.4 Property-Based Tests (Randomized)

```typescript
// validation.test.ts
import { fc, test } from '@fast-check/vitest';

test.prop([fc.string({ minLength: 1, maxLength: 50 }), fc.emailAddress()])(
  'should accept any valid username and email combo',
  (username, email) => {
    const result = handleInput({ username, email });
    expect(result.username).toBe(username.trim());
    expect(result.email).toBe(email.toLowerCase());
  }
);
```

### 4.5 E2E Tests (Critical User Journeys)

```typescript
// api.e2e.test.ts
import { describe, it, expect } from 'vitest';

describe('Task API (E2E)', () => {
  it('should complete the full task lifecycle', async () => {
    // 1. Create
    const createRes = await fetch('/api/tasks', {
      method: 'POST',
      body: JSON.stringify({ title: 'Test task' }),
    });
    expect(createRes.status).toBe(201);
    const task = await createRes.json();

    // 2. Read
    const getRes = await fetch(`/api/tasks/${task.id}`);
    expect(getRes.status).toBe(200);
    expect((await getRes.json()).title).toBe('Test task');

    // 3. Update
    const updateRes = await fetch(`/api/tasks/${task.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'done' }),
    });
    expect(updateRes.status).toBe(200);

    // 4. Delete
    const deleteRes = await fetch(`/api/tasks/${task.id}`, { method: 'DELETE' });
    expect(deleteRes.status).toBe(204);
  });
});
```

---

## 5. Testing Patterns by Node Type

### 5.1 Input Node Testing

```typescript
// input/validation.test.ts
describe('Input Validation', () => {
  // Test every field
  describe('username', () => {
    it('should accept 3-50 character usernames', () => { /* ... */ });
    it('should reject empty username', () => { /* ... */ });
    it('should reject username over 50 characters', () => { /* ... */ });
    it('should trim whitespace', () => { /* ... */ });
    it('should reject special characters', () => { /* ... */ });
  });

  // Test combinations
  it('should validate all fields together', () => { /* ... */ });
  it('should provide clear error messages per field', () => { /* ... */ });
});
```

### 5.2 Logic Node Testing

```typescript
// logic/core.test.ts
describe('Core Logic', () => {
  // Happy path
  it('should process valid input correctly', () => { /* ... */ });
  
  // Edge cases
  it('should handle empty input', () => { /* ... */ });
  it('should handle maximum input size', () => { /* ... */ });
  
  // Error paths
  it('should fail gracefully on invalid data', () => { /* ... */ });
  it('should maintain idempotency', () => { /* ... */ });
});
```

### 5.3 Database Node Testing

```typescript
// db/repository.test.ts
describe('Repository', () => {
  // CRUD
  it('should create records', () => { /* ... */ });
  it('should read records by id', () => { /* ... */ });
  it('should update records', () => { /* ... */ });
  it('should delete records', () => { /* ... */ });
  
  // Constraints
  it('should enforce unique constraints', () => { /* ... */ });
  it('should enforce foreign keys', () => { /* ... */ });
  it('should rollback on error', () => { /* ... */ });
  
  // Edge cases
  it('should return empty array for no results', () => { /* ... */ });
  it('should handle concurrent writes', () => { /* ... */ });
});
```

### 5.4 API Node Testing

```typescript
// api/external-service.test.ts
describe('External API Client', () => {
  // Success cases
  it('should return parsed data on 200', () => { /* ... */ });
  it('should handle pagination', () => { /* ... */ });
  
  // Error cases
  it('should retry on 429 (rate limit)', () => { /* ... */ });
  it('should retry on 503 (service unavailable)', () => { /* ... */ });
  it('should timeout after configured duration', () => { /* ... */ });
  it('should handle network errors', () => { /* ... */ });
});
```

### 5.5 UI Node Testing

```typescript
// ui/App.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

describe('App Component', () => {
  it('should show loading state initially', () => {
    render(<App />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should display data after successful load', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => mockData });
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Task Manager')).toBeInTheDocument();
    });
  });

  it('should show error state on failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

---

## 6. Test Fixtures & Factories

### 6.1 Factory Functions

```typescript
// test/factories.ts
import type { Task, CreateTaskInput } from '../src/types';

export function createTaskInput(overrides: Partial<CreateTaskInput> = {}): CreateTaskInput {
  return {
    title: 'Default task title',
    description: 'Default description',
    priority: 'medium',
    ...overrides,
  };
}

export function createTask(overrides: Partial<Task> = {}): Task {
  return {
    id: Math.floor(Math.random() * 10000),
    title: 'Default task',
    description: null,
    status: 'pending',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}
```

### 6.2 In-Memory Database for Testing

```typescript
// test/db.ts
import Database from 'better-sqlite3';

export function createTestDb(): Database.Database {
  const db = new Database(':memory:'); // In-memory, fast
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  // Run schema
  initializeSchema(db);
  return db;
}

export function cleanTestDb(db: Database.Database): void {
  // Delete all data between tests
  const tables = db.prepare(
    "SELECT name FROM sqlite_master WHERE type='table'"
  ).all() as { name: string }[];
  
  for (const { name } of tables) {
    if (name !== 'sqlite_sequence') {
      db.prepare(`DELETE FROM ${name}`).run();
    }
  }
}
```

---

## 7. Mocking Strategies

### 7.1 When to Mock vs. Use Real Implementations

| Scenario | Approach | Why |
|---|---|---|
| Pure function | No mock | Test the actual logic |
| Database queries | Real in-memory DB | Catch real SQL errors |
| External HTTP API | Mock at transport layer | Fast, deterministic |
| File system | Mock or temp directory | Avoid side effects |
| System clock | Mock | Deterministic time-based tests |
| Random/UUID | Mock with fixed values | Reproducible tests |

### 7.2 HTTP Mocking

```typescript
// test/mocks/http.ts
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

export const server = setupServer(
  http.get('https://api.example.com/v1/users', () => {
    return HttpResponse.json([
      { id: 1, name: 'Alice' },
      { id: 2, name: 'Bob' },
    ]);
  }),

  http.post('https://api.example.com/v1/users', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: 3, ...body as object }, { status: 201 });
  }),
);

// In test setup
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

---

## 8. Test Command Scripts

### Package.json Scripts

```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "test:integration": "vitest run --config vitest.integration.config.ts",
    "test:e2e": "vitest run --config vitest.e2e.config.ts",
    "test:all": "npm run test && npm run test:integration && npm run test:e2e"
  }
}
```

### Makefile Targets

```makefile
.PHONY: test test-unit test-integration test-e2e test-coverage

test: test-unit test-integration

test-unit:
	go test -v -short -count=1 ./...

test-integration:
	go test -v -run Integration -count=1 ./...

test-e2e:
	go test -v -run E2E -count=1 ./...

test-coverage:
	go test -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html
```

---

## 9. Testing Checklist

Before considering generated code complete:

- [ ] All input validation rules have unit tests
- [ ] All business logic branches are tested
- [ ] Error paths produce the correct error types
- [ ] Database operations work against real SQLite
- [ ] External API calls are mocked with MSW or similar
- [ ] UI renders all states: loading, success, error, empty
- [ ] Coverage meets minimum thresholds (80%+)
- [ ] Integration tests verify the wiring between nodes
- [ ] Edge cases are covered: empty data, max input, nulls
- [ ] Tests are deterministic (no flaky tests due to timing)

---

*For deeper testing concepts, see `bible-reference/01-foundations/` (testing methodologies) and `bible-reference/19-formal-methods-tools/` (formal verification).*
