# 🌐 Web Application Architecture

> Reference for building web applications — frontend, backend, API design, full-stack patterns.
> Extracted from The Programming Bible's Web Apps level. Apply these when generating web app code.

---

## 1. Web Architecture Evolution

| Generation | Pattern | Tech | Characteristics |
|---|---|---|---|
| **Gen 1** | Static Documents | HTML over HTTP/0.9 | No dynamic content |
| **Gen 2** | Server-Generated | CGI, PHP, JSP, SSR | Dynamic HTML generated server-side |
| **Gen 3** | AJAX & SPA | React, Vue, Angular | Browser as app runtime, async data |
| **Gen 4** | API-First | REST, GraphQL, microservices | Multiple clients, decoupled backends |
| **Gen 5** | Edge & JAMstack | CDN, edge functions, SSG | Pre-rendered, globally distributed |

### Three-Tier Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Presentation   │     │   Application   │     │      Data       │
│     (Tier 1)    │────▶│    (Tier 2)     │────▶│    (Tier 3)     │
│                 │     │                 │     │                 │
│  Browser / SPA  │     │  API Server     │     │  Database        │
│  React/Vue      │     │  Express/FastAPI│     │  SQLite/PG      │
│  HTML/CSS/JS    │     │  Business Logic │     │  File Storage   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                      │                        │
         │                      │                        │
         └────────── CDN / Load Balancer ───────────────┘
```

---

## 2. Frontend Core

### DOM API Fundamentals

```typescript
// Node tree traversal
const parent = element.parentNode;
const children = element.children;       // HTMLCollection (live)
const siblings = element.parentNode?.children;
const next = element.nextElementSibling;

// Query selectors
const single = document.querySelector('.my-class');     // First match
const all = document.querySelectorAll('.item');          // NodeList (static)

// DOM manipulation
const div = document.createElement('div');
div.textContent = 'Hello';
div.classList.add('active');
parent.appendChild(div);
parent.insertBefore(div, referenceNode);
parent.removeChild(div);
div.remove();  // Modern

// innerHTML vs textContent
element.textContent = 'Safe text <script>no injection</script>';  // ✅ Safe
element.innerHTML = '<span>Rich HTML</span>';                      // ⚠️ XSS risk - sanitize!
```

### Event System

```typescript
// Event phases: Capture → Target → Bubbling
element.addEventListener('click', handler, { capture: true });  // Capture phase
element.addEventListener('click', handler);                      // Bubble phase (default)

// Event delegation (efficient for many children)
parent.addEventListener('click', (event) => {
  const button = (event.target as HTMLElement).closest('.list-item');
  if (button) {
    console.log('Clicked item:', button.dataset.id);
  }
});

// Custom events
const event = new CustomEvent('item:selected', {
  detail: { id: 42, name: 'Example' },
  bubbles: true,
});
element.dispatchEvent(event);

// Intersection Observer (lazy loading, infinite scroll)
const observer = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (entry.isIntersecting) {
      loadContent(entry.target);
      observer.unobserve(entry.target);
    }
  }
}, { rootMargin: '200px' });
observer.observe(element);
```

### State Management Patterns

| Pattern | Complexity | When to Use |
|---|---|---|
| **Local state** (`useState`) | Low | Component-local data |
| **Context** (`React.createContext`) | Medium | Theme, auth, locale |
| **Atomic state** (Jotai, Recoil) | Medium | Granular shared state |
| **Global store** (Redux, Zustand) | High | Complex app state, undo/history |
| **Server state** (TanStack Query) | Medium | API data caching & sync |

---

## 3. Backend Framework Patterns

### Request/Response Lifecycle

```
1. Web Server ──→ Parse TCP stream into HTTP request
2. Framework Init ──→ Initialize request/response objects
3. Global Middleware ──→ Logging, CORS, Auth, Rate limiting
4. Router ──→ Match URL to route handler
5. Route Middleware ──→ Validation, caching, permission checks
6. Route Handler ──→ Execute business logic, call services
7. Response Transform ──→ Serialize, compress, set headers
8. Send ──→ Write response to client
```

### Middleware Pattern

```typescript
// Express/Fastify-style middleware
type Middleware = (req: Request, res: Response, next: (err?: Error) => void) => void;

// Standard middleware
const logger: Middleware = (req, _res, next) => {
  console.log(`${req.method} ${req.url}`);
  next();
};

// Error-handling middleware (4 params)
const errorHandler: Middleware = (err, _req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(500).json({
    error: 'Internal server error',
    code: 'ERR_INTERNAL',
    requestId: req.id,
  });
};

// Registration order matters!
app.use(logger);
app.use(cors());
app.use('/api', authMiddleware);
app.use('/api/tasks', taskRouter);
app.use(errorHandler); // Always last
```

### Route Handler Pattern

```typescript
// Clean separation: validation → service → response
import { z } from 'zod';

const CreateTaskSchema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().max(1000).optional(),
  priority: z.enum(['low', 'medium', 'high']).default('medium'),
});

router.post('/tasks', async (req, res, next) => {
  try {
    // 1. Validate input
    const input = CreateTaskSchema.parse(req.body);
    
    // 2. Authorize
    if (!req.user.canCreateTasks) {
      return res.status(403).json({ error: 'Forbidden' });
    }
    
    // 3. Execute service
    const task = await taskService.create(req.user.id, input);
    
    // 4. Return response
    res.status(201).json(task);
  } catch (err) {
    if (err instanceof z.ZodError) {
      return res.status(400).json({ error: 'Validation failed', details: err.issues });
    }
    next(err); // Pass to error handler
  }
});
```

---

## 4. REST API Design

### Resource Naming & HTTP Methods

| Method | URL Pattern | Action | Status Codes |
|---|---|---|---|
| `GET` | `/tasks` | List collection | 200 |
| `GET` | `/tasks/:id` | Read one | 200, 404 |
| `POST` | `/tasks` | Create | 201, 400 |
| `PUT` | `/tasks/:id` | Replace | 200, 404 |
| `PATCH` | `/tasks/:id` | Partial update | 200, 404 |
| `DELETE` | `/tasks/:id` | Delete | 204, 404 |

### Response Envelope

```typescript
// Success response
interface SuccessResponse<T> {
  data: T;
  meta?: {
    page: number;
    pageSize: number;
    total: number;
  };
  links?: {
    self: string;
    next: string | null;
    prev: string | null;
  };
}

// Error response
interface ErrorResponse {
  error: {
    code: string;           // Machine-readable: 'ERR_VALIDATION'
    message: string;        // Human-readable: 'Title is required'
    details?: unknown;      // Validation errors, stack trace (dev only)
  };
  requestId: string;        // For log correlation
}
```

### API Versioning Strategies

| Strategy | Example | Pros | Cons |
|---|---|---|---|
| **URI** | `/v2/tasks` | Simple, visible | URL pollution |
| **Header** | `Accept: application/vnd.app.v2+json` | Clean URLs | Harder to test |
| **Query param** | `/tasks?version=2` | Easy to switch | Caching issues |
| **Content type** | Different media types | RESTful | Complex clients |

---

## 5. Full-Stack Application Structure

```
fullstack-app/
├── frontend/
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   ├── pages/              # Route-level page components
│   │   ├── api/                # API client (fetch wrappers)
│   │   ├── hooks/              # Custom React hooks
│   │   ├── stores/             # State management
│   │   ├── types.ts            # Shared TypeScript types
│   │   ├── App.tsx             # Root component + routing
│   │   └── main.tsx            # Entry point
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/             # Route handlers
│   │   ├── services/           # Business logic
│   │   ├── middleware/         # Express/Fastify middleware
│   │   ├── db/                 # Database access
│   │   │   ├── schema.ts       # Schema definitions
│   │   │   └── repository.ts   # Query functions
│   │   ├── types.ts            # Backend types
│   │   └── index.ts           # Server entry point
│   ├── package.json
│   └── tsconfig.json
└── README.md
```

### Shared Types (Full-Stack TypeScript)

```typescript
// shared/types.ts — Used by both frontend and backend
export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: 'pending' | 'in_progress' | 'done';
  priority: 'low' | 'medium' | 'high';
  created_at: string;
  updated_at: string;
}

export interface CreateTaskInput {
  title: string;
  description?: string;
  priority?: 'low' | 'medium' | 'high';
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: { page: number; pageSize: number; total: number };
}
```

---

## 6. Web Application Data Flow

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  User     │     │  Browser │     │  Backend  │     │ Database  │
│  Action   │────▶│  (React) │────▶│  (API)   │────▶│ (SQLite) │
└──────────┘     └────┬─────┘     └────┬─────┘     └──────────┘
                      │                │                  │
                      │  Loading UI    │                  │
                      │◀───────────────│                  │
                      │                │   Query          │
                      │                │─────────────────▶│
                      │                │                  │
                      │                │   Results        │
                      │                │◀─────────────────│
                      │  Data + Render │                  │
                      │◀───────────────│                  │
                      │                │                  │
                      │  User sees UI  │                  │
```

---

## Quick Reference: Web App by Node Type

| Node Type | Web App Mapping |
|---|---|
| **Input** | HTTP request validation (Zod/Pydantic), form handling |
| **Logic** | Service layer, business rules, workflows |
| **Database** | SQLite/PostgreSQL via ORM or raw queries |
| **UI** | React/Vue components, pages, layouts, routing |
| **API** | REST endpoints, GraphQL resolvers, external integrations |

---

*For deeper web development concepts, see Bible level `04-web-apps/` — full-stack architecture, database design, API design, and web security.*
