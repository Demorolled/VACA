# 🐛 Debugging Strategies

> Debugging and troubleshooting patterns for generated applications.
> Covers local debugging, logging, error diagnosis, and runtime investigation.

---

## 1. Debugging Philosophy

Generated code will have bugs. The key is to **make bugs easy to find and fix**.

### Three Rules of Debugging

1. **Make it fail fast** — validate inputs early, crash on unexpected states
2. **Make it observable** — log entry/exit of every operation with context
3. **Make it reproducible** — deterministic behavior, seeded randomness

### The Debugging Hierarchy

```
1. Static Analysis     ← TypeScript types, Go vet, Python mypy
2. Logging             ← Structured logs with context
3. Interactive Debug   ← breakpoints, step-through
4. Tracing             ← Distributed tracing for async flows
5. Profiling           ← CPU, memory, I/O bottlenecks
```

---

## 2. Logging Best Practices

### 2.1 Structured Logging

Always use structured logging (never `console.log`):

```typescript
// ✅ GOOD: Structured, searchable
import pino from 'pino';

const logger = pino({
  level: process.env.LOG_LEVEL ?? 'info',
  transport: { target: 'pino/file', options: { destination: './app.log' } },
});

export function processFile(filePath: string): Result {
  logger.info({ filePath }, 'Processing file');
  try {
    const result = doWork(filePath);
    logger.info({ filePath, resultSize: result.length }, 'File processed');
    return result;
  } catch (err) {
    logger.error({ err, filePath }, 'Failed to process file');
    throw new AppError('File processing failed', 'ERR_PROCESS_FILE');
  }
}

// ❌ BAD: Console.log
console.log('Processing file:', filePath);
console.log('Error:', err);
```

### 2.2 Log Levels

| Level | When to Use | Example |
|---|---|---|
| `error` | Operation failed, data may be lost | DB connection failed, API returned 500 |
| `warn` | Something unexpected but recoverable | Rate limit approaching, config missing |
| `info` | Normal operation milestones | "User created", "File processed" |
| `debug` | Detailed diagnostic information | SQL queries, API request bodies |
| `trace` | Very detailed, noisy | Loop iterations, function parameters |

### 2.3 What to Log (and What NOT to Log)

```typescript
// ✅ DO log:
logger.info({ userId, action: 'login' }, 'User logged in');
logger.error({ err, operation: 'db_query' }, 'Database query failed');

// ❌ DON'T log:
logger.info({ password: userInput.password }, 'User input'); // SECURITY RISK
logger.info({ fullDbDump: JSON.stringify(db) }, 'DB state'); // TOO MUCH
```

**Never log:** passwords, tokens, API keys, credit card numbers, personal data.

### 2.4 Logging Configuration

```typescript
// config.ts — Environment-based logging
export function createLogger(): Logger {
  const isDev = process.env.NODE_ENV === 'development';
  const isTest = process.env.NODE_ENV === 'test';

  return pino({
    // In dev: pretty-print to console
    // In prod: JSON to file
    ...(isDev ? {
      transport: { target: 'pino-pretty', options: { colorize: true } },
    } : {}),
    // In test: silent
    ...(isTest ? { enabled: false } : {}),
    level: process.env.LOG_LEVEL ?? (isDev ? 'debug' : 'info'),
  });
}
```

---

## 3. Runtime Debugging

### 3.1 Node.js Debugging

```bash
# 1. Built-in inspector
node --inspect src/index.js
# Open chrome://inspect in Chrome

# 2. Debug with breakpoints
node --inspect-brk src/index.js
# Pauses on first line, waits for debugger

# 3. Environment variables for debugging
NODE_ENV=development
LOG_LEVEL=debug
DEBUG=app:*  # Namespace-based debugging
```

### 3.2 Go Debugging

```bash
# 1. Delve debugger
dlv debug ./cmd/app -- --flag value
dlv debug ./cmd/app --headless --listen=:2345

# 2. Print stack trace on SIGQUIT
# Send SIGQUIT (Ctrl+\) to a running Go program
kill -QUIT <pid>
# Go runtime dumps all goroutine stacks

# 3. Race detector
go test -race ./...
go run -race ./cmd/app
```

### 3.3 Python Debugging

```bash
# 1. Built-in debugger
python -m pdb src/main.py

# 2. Post-mortem debugging
python -m pdb -c continue src/main.py
# Then: (Pdb) where
#       (Pdb) post_mortem()

# 3. Remote debugging with debugpy
pip install debugpy
python -m debugpy --listen 0.0.0.0:5678 src/main.py
```

---

## 4. Common Error Diagnosis

### 4.1 Error Type Reference

```typescript
// Standard error hierarchy for generated apps
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'AppError';
  }
}

export class DatabaseError extends AppError {
  constructor(message: string, details?: unknown) {
    super(message, 'ERR_DATABASE', details);
    this.name = 'DatabaseError';
  }
}

export class ValidationError extends AppError {
  constructor(message: string, details?: unknown) {
    super(message, 'ERR_VALIDATION', details);
    this.name = 'ValidationError';
  }
}

export class ApiError extends AppError {
  constructor(
    message: string,
    public readonly statusCode: number,
    details?: unknown,
  ) {
    super(message, 'ERR_API', details);
    this.name = 'ApiError';
  }
}
```

### 4.2 Error Diagnosis Flowchart

```
Application error
│
▼
Is there a stack trace?
├── No → Enable LOG_LEVEL=debug, reproduce
└── Yes → Read the top frame
    │
    ▼
    Where is the error?
    ├── Input/Validation → Check input schema, validation rules
    ├── Logic/Business → Check business rules, data transformation
    ├── Database → Check SQL syntax, constraints, connection
    ├── API/External → Check network, auth, request format
    └── UI/Render → Check state, props, component hierarchy
```

### 4.3 Quick Diagnostic Commands

```bash
# Check if the process is running
systemctl status myapp
ps aux | grep myapp

# Check logs
journalctl -u myapp -n 100 --no-pager
journalctl -u myapp -f  # Follow logs

# Check resource usage
top -p $(pgrep myapp)
lsof -p $(pgrep myapp)

# Check network
ss -tlnp | grep myapp
curl -v http://localhost:3000/health

# Check database
sqlite3 /var/lib/myapp/data.db "PRAGMA integrity_check;"
sqlite3 /var/lib/myapp/data.db "SELECT COUNT(*) FROM sqlite_master;"
```

---

## 5. Debugging by Layer

### 5.1 Input Layer Debugging

```typescript
// Enable verbose input logging
export function debugInput(raw: unknown): void {
  logger.debug({
    inputType: typeof raw,
    inputKeys: typeof raw === 'object' ? Object.keys(raw as object) : undefined,
    inputPreview: JSON.stringify(raw).slice(0, 200),
  }, 'Raw input received');
}

// Common input issues:
// - Undefined/null where value expected
// - Wrong type (string instead of number)
// - Missing required fields
// - Extra unexpected fields
// - Encoding issues (UTF-8 vs ASCII)
```

### 5.2 Database Layer Debugging

```typescript
export function debugQuery(sql: string, params: unknown[]): void {
  logger.debug({
    sql: sql.replace(/\s+/g, ' ').trim(),
    params,
    paramTypes: params.map(p => typeof p),
  }, 'Executing query');
}

// Common database issues:
// - SQL syntax errors
// - Column not found (wrong table or typo)
// - Foreign key constraint violation
// - NOT NULL constraint violation
// - UNIQUE constraint violation
// - Database locked (WAL mode helps)
// - Connection pool exhaustion
```

### 5.3 API Layer Debugging

```typescript
export async function debugApiCall<T>(
  url: string,
  options: RequestInit
): Promise<Response> {
  logger.debug({
    url,
    method: options.method ?? 'GET',
    headers: sanitizeHeaders(options.headers), // Remove auth tokens from logs
    bodyPreview: typeof options.body === 'string'
      ? options.body.slice(0, 500) : undefined,
  }, 'API request');

  const start = Date.now();
  try {
    const response = await fetch(url, options);
    const duration = Date.now() - start;
    logger.debug({
      url,
      status: response.status,
      duration,
    }, 'API response');
    return response;
  } catch (err) {
    logger.error({
      url,
      duration: Date.now() - start,
      err,
    }, 'API request failed');
    throw err;
  }
}
```

### 5.4 UI Layer Debugging

```typescript
// React DevTools patterns
export function useDebugState<T>(name: string, initialState: T): [T, (v: T) => void] {
  const [state, setState] = useState(initialState);
  useEffect(() => {
    logger.debug({ state, component: name }, `State change: ${name}`);
  }, [state, name]);
  return [state, setState];
}

// Common UI issues:
// - State not updating (missing setState call)
// - Infinite re-renders (missing dependency array)
// - Undefined in render (accessing property of null)
// - Wrong data type (string instead of array for .map())
// - Missing key prop in lists
```

---

## 6. Debugging Tools

### 6.1 Health Endpoint

```typescript
// Every generated app should have a /health endpoint
import express from 'express';

const router = express.Router();

router.get('/health', async (_req, res) => {
  const checks = {
    status: 'ok',
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    version: process.env.APP_VERSION ?? 'dev',
  };

  // Optional: deep health checks
  try {
    await db.prepare('SELECT 1').get();
    checks['database'] = 'connected';
  } catch {
    checks['database'] = 'disconnected';
    checks.status = 'degraded';
  }

  const httpStatus = checks.status === 'ok' ? 200 : 503;
  res.status(httpStatus).json(checks);
});
```

### 6.2 Debug Mode

```typescript
// Enable debug mode via config or environment
if (config.debug) {
  // 1. Expose internal state via /debug endpoint
  router.get('/debug/state', (_req, res) => {
    res.json({
      config: sanitizeConfig(config), // Remove secrets
      memory: process.memoryUsage(),
      uptime: process.uptime(),
    });
  });

  // 2. Enable more verbose logging
  logger.level = 'debug';

  // 3. Expose metrics
  router.get('/debug/metrics', (_req, res) => {
    res.json({
      requests: requestCount,
      errors: errorCount,
      avgResponseTime: avgResponseTime,
    });
  });
}
```

### 6.3 Error Reporting

```typescript
// Global error handler
process.on('unhandledRejection', (reason) => {
  logger.fatal({ err: reason }, 'Unhandled Promise rejection');
  process.exit(1);
});

process.on('uncaughtException', (err) => {
  logger.fatal({ err }, 'Uncaught exception');
  process.exit(1);
});

// If configured, send to error tracking
export function reportError(error: Error, context?: Record<string, unknown>): void {
  logger.error({ err: error, ...context }, 'Error reported');
  
  if (config.errorReporting?.enabled) {
    // Send to error reporting service (optional)
    // e.g., Sentry, or just write to a separate error file
  }
}
```

---

## 7. Debugging Workflow

### Step 1: Reproduce

```bash
# Set debug logging
export LOG_LEVEL=debug
export NODE_ENV=development

# Run with the exact input that caused the problem
./myapp --input problem-case.txt

# Check logs
cat app.log | grep "error\|warn\|fail"
```

### Step 2: Isolate

```bash
# Test each layer independently
# 1. Input validation only
node -e "
  const { validate } = require('./src/input/validation');
  console.log(validate({ bad: 'input' }));
"

# 2. Database queries
node -e "
  const db = require('./src/db');
  console.log(db.query('SELECT * FROM items'));
"

# 3. Business logic
node -e "
  const { process } = require('./src/logic');
  console.log(process(testData));
"
```

### Step 3: Fix

```typescript
// 1. Write a test that reproduces the bug
it('should handle edge case X', () => {
  expect(() => process(edgeCase)).not.toThrow();
});

// 2. Fix the code
// 3. Verify the test passes
// 4. Check no regressions: npm test
```

### Step 4: Prevent

```typescript
// Add a type guard at the boundary
function ensureString(value: unknown): asserts value is string {
  if (typeof value !== 'string') {
    throw new AppError(
      `Expected string, got ${typeof value}`,
      'ERR_TYPE_MISMATCH'
    );
  }
}

// Add input validation at every boundary
function handleInput(raw: unknown) {
  try {
    return InputSchema.parse(raw);
  } catch (err) {
    logger.error({ err, raw }, 'Input validation failed');
    throw new ValidationError('Invalid input', err);
  }
}
```

---

## 8. Debugging Checklist

When debugging a generated application:

- [ ] Check logs at `debug` level (set `LOG_LEVEL=debug`)
- [ ] Is the error type clear? (AppError with code, DatabaseError, etc.)
- [ ] Can you reproduce with a minimal input?
- [ ] Are all inputs validated at boundaries?
- [ ] Are database parameters properly bound (not interpolated)?
- [ ] Is the error caught at the right layer?
- [ ] Does the error message tell you what to fix?
- [ ] Is the health endpoint responding?
- [ ] Are system resources sufficient? (disk space, memory, file descriptors)
- [ ] Can you run it in development mode with the inspector?

---

*For deeper debugging and profiling concepts, see `bible-reference/19-formal-methods-tools/` (static analysis, debuggers, profilers) and `bible-reference/05-systems-programming/` (memory management, optimization).*
