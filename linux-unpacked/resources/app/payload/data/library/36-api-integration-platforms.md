# 🔌 API Design & Integration Platforms

> Reference for building API platforms — API gateways, GraphQL federation, gRPC, webhooks, event-driven integration, and iPaaS patterns.
> Extracted from The Programming Bible's API & Integration Platforms level.

---

## 1. API Platform Architecture

### API Lifecycle

```
Design → Develop → Test → Deploy → Monitor → Version → Deprecate
  │         │        │        │        │         │          │
  │ OpenAPI │        │        │        │         │          │
  │ Spec    │        │        │        │         │          │
  └─────────┴────────┴────────┴────────┴─────────┴──────────┘
                API Gateway (Auth, Rate Limit, Routing)
```

### API Styles Comparison

| Style | Protocol | Data Format | Caching | Tooling |
|---|---|---|---|---|
| **REST** | HTTP/1.1, HTTP/2 | JSON, XML | Native HTTP | Mature |
| **GraphQL** | HTTP, WebSocket | JSON (query) | Manual | Strong |
| **gRPC** | HTTP/2 | Protobuf (binary) | Not built-in | Code gen |
| **WebSocket** | WS, WSS | Binary/Text | N/A | Moderate |
| **Webhook** | HTTP POST | JSON | N/A | Callback pattern |

---

## 2. API Gateway Pattern

### Gateway Responsibilities

```typescript
// API Gateway — unified entry point
import express from 'express';
import rateLimit from 'express-rate-limit';
import jwt from 'jsonwebtoken';

const gateway = express();

// 1. Rate limiting
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000,  // 15 minutes
    max: 100,                   // 100 requests per window
    standardHeaders: true,
    message: { error: 'Too many requests', retryAfter: 900 },
});

gateway.use('/api/', limiter);

// 2. Authentication middleware
gateway.use('/api/', async (req, res, next) => {
    const authHeader = req.headers.authorization;
    if (!authHeader?.startsWith('Bearer ')) {
        return res.status(401).json({ error: 'Missing token' });
    }

    try {
        const token = authHeader.slice(7);
        const payload = jwt.verify(token, process.env.JWT_SECRET!);
        req.user = payload;
        next();
    } catch (err) {
        return res.status(401).json({ error: 'Invalid token' });
    }
});

// 3. Route forwarding (proxy)
const services = {
    users: 'http://user-service:3001',
    orders: 'http://order-service:3002',
    payments: 'http://payment-service:3003',
};

gateway.all('/api/:service/*', async (req, res) => {
    const service = services[req.params.service];
    if (!service) {
        return res.status(404).json({ error: 'Service not found' });
    }

    const targetUrl = `${service}${req.originalUrl.replace('/api/', '/')}`;
    try {
        const response = await fetch(targetUrl, {
            method: req.method,
            headers: { 'Content-Type': 'application/json' },
            body: req.method !== 'GET' ? JSON.stringify(req.body) : undefined,
        });
        res.status(response.status).json(await response.json());
    } catch (err) {
        res.status(502).json({ error: 'Service unavailable' });
    }
});
```

### Kong API Gateway Configuration

```yaml
# Kong declarative config (decK format)
_format_version: "3.0"
services:
  - name: user-service
    url: http://user-service:3001
    routes:
      - name: user-routes
        paths:
          - /api/users
        methods: [GET, POST, PUT, DELETE]
    plugins:
      - name: rate-limiting
        config:
          minute: 60
          hour: 1000
      - name: cors
        config:
          origins: ["https://app.example.com"]
          methods: ["GET", "POST", "PUT", "DELETE"]

  - name: order-service
    url: http://order-service:3002
    routes:
      - name: order-routes
        paths:
          - /api/orders
    plugins:
      - name: key-auth
        config:
          key_names: ["X-API-Key"]

consumers:
  - username: service-account
    keyauth_credentials:
      - key: sk_live_abc123
```

---

## 3. GraphQL Federation

### Federation Architecture

```
                    Gateway (Apollo Router)
                   /          |           \
                  /           |            \
        Subgraph A        Subgraph B     Subgraph C
        (Users)           (Orders)        (Payments)
```

### Subgraph Definition

```graphql
# Subgraph A: Users service
extend type Query {
    user(id: ID!): User
}

type User @key(fields: "id") {
    id: ID!
    name: String!
    email: String!
    orders: [Order!]  # Resolved by Order subgraph
}
```

```graphql
# Subgraph B: Orders service
extend type Query {
    order(id: ID!): Order
}

type Order @key(fields: "id") {
    id: ID!
    userId: ID!
    total: Float!
    status: OrderStatus!
    items: [OrderItem!]!
}

extend type User @key(fields: "id") {
    id: ID! @external
    orders: [Order!] @requires(fields: "id")
}
```

### Apollo Router Configuration

```yaml
# router.yaml
supergraph:
  path: /supergraph.graphql

listen: 0.0.0.0:4000

cors:
  origins:
    - https://app.example.com

headers:
  all:
    request:
      - propagate:
          named: "authorization"

rhai:
  scripts: ./rhai-scripts/

limits:
  max_depth: 10       # Prevent deep queries
  max_height: 100     # Limit query complexity
  max_aliases: 30     # Prevent alias abuse
```

---

## 4. gRPC & Protobuf

### Protocol Buffer Definition

```protobuf
// user.proto
syntax = "proto3";

package users;

service UserService {
    rpc GetUser (GetUserRequest) returns (User);
    rpc ListUsers (ListUsersRequest) returns (ListUsersResponse);
    rpc CreateUser (CreateUserRequest) returns (User);
    rpc UpdateUser (UpdateUserRequest) returns (User);
    rpc DeleteUser (DeleteUserRequest) returns (Empty);
    rpc StreamUsers (Empty) returns (stream User);
}

message User {
    string id = 1;
    string name = 2;
    string email = 3;
    UserRole role = 4;
    int64 created_at = 5;  // Unix timestamp

    enum UserRole {
        USER = 0;
        ADMIN = 1;
        MODERATOR = 2;
    }
}

message GetUserRequest {
    string id = 1;
}

message ListUsersRequest {
    int32 page_size = 1;
    string page_token = 2;
    string filter = 3;  // e.g., "role=ADMIN"
}

message ListUsersResponse {
    repeated User users = 1;
    string next_page_token = 2;
    int32 total_count = 3;
}
```

### gRPC Server & Client

```typescript
// gRPC server (TypeScript with @grpc/grpc-js)
import * as grpc from '@grpc/grpc-js';
import { UserService } from './generated/user';

class UserServiceImpl implements UserService {
    async getUser(call: grpc.ServerUnaryCall<GetUserRequest, User>) {
        const { id } = call.request;
        const user = await db.users.findById(id);
        if (!user) {
            throw { code: grpc.status.NOT_FOUND, message: 'User not found' };
        }
        return user;
    }

    async streamUsers(call: grpc.ServerWritableStream<Empty, User>) {
        const users = await db.users.findAll();
        for (const user of users) {
            call.write(user);
        }
        call.end();
    }
}

const server = new grpc.Server();
server.addService(UserService, new UserServiceImpl());
server.bindAsync('0.0.0.0:50051',
    grpc.ServerCredentials.createInsecure(),
    () => server.start()
);
```

---

## 5. Webhooks & Event-Driven Integration

### Webhook Architecture

```
Publisher                          Subscriber
     │                                  │
     │  Create Webhook (POST /webhooks) │
     │◄─────────────────────────────────│
     │         secret: whsec_xxx        │
     │                                  │
     │  Event Occurs                    │
     │     │                            │
     │  POST /callback                  │
     │─────────────────────────────────►│
     │  Signature: sha256(body+secret)  │
     │◄─────── 200 OK / 409 ────────────│
     │                                  │
     │  Retry if not 2xx (3x, backoff)  │
     │─────────────────────────────────►│
```

### Webhook Dispatcher Implementation

```typescript
// Event-driven webhook dispatcher
interface WebhookEvent {
    id: string;
    type: string;
    created: string;
    data: Record<string, unknown>;
}

interface WebhookSubscription {
    id: string;
    url: string;
    secret: string;
    events: string[];
    retryCount: number;
}

class WebhookDispatcher {
    private subscriptions: Map<string, WebhookSubscription> = new Map();

    async register(sub: WebhookSubscription): Promise<void> {
        // Verify URL is reachable (challenge)
        await this.sendChallenge(sub.url, sub.secret);
        this.subscriptions.set(sub.id, sub);
    }

    async dispatch(event: WebhookEvent): Promise<void> {
        const matched = Array.from(this.subscriptions.values())
            .filter(sub => sub.events.includes(event.type));

        await Promise.allSettled(
            matched.map(sub => this.deliverWithRetry(sub, event))
        );
    }

    private async deliverWithRetry(
        sub: WebhookSubscription,
        event: WebhookEvent,
        attempt: number = 0,
    ): Promise<void> {
        const maxRetries = 3;

        try {
            const signature = this.sign(event, sub.secret);
            const response = await fetch(sub.url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Webhook-ID': event.id,
                    'X-Webhook-Signature': signature,
                    'X-Webhook-Retry': String(attempt),
                },
                body: JSON.stringify(event),
            });

            if (!response.ok && attempt < maxRetries) {
                const backoff = Math.pow(2, attempt) * 1000;
                await new Promise(r => setTimeout(r, backoff));
                return this.deliverWithRetry(sub, event, attempt + 1);
            }
        } catch (err) {
            if (attempt < maxRetries) {
                const backoff = Math.pow(2, attempt) * 1000;
                await new Promise(r => setTimeout(r, backoff));
                return this.deliverWithRetry(sub, event, attempt + 1);
            }
            console.error(`Webhook ${sub.id} failed after ${maxRetries} retries`);
        }
    }

    private sign(event: WebhookEvent, secret: string): string {
        const crypto = require('crypto');
        const payload = JSON.stringify(event);
        return crypto
            .createHmac('sha256', secret)
            .update(payload)
            .digest('hex');
    }
}
```

---

## 6. Integration Platform (iPaaS) Patterns

### Common Integration Patterns

| Pattern | Description | Example |
|---|---|---|
| **Fan-out** | One event → many services | User registered → email, analytics, CRM |
| **Aggregator** | Many services → one response | Dashboard widgets from multiple sources |
| **Splitter** | One message → multiple parts | Invoice → line items |
| **Router** | Route based on content | Payment method → Stripe/PayPal |
| **Translator** | Transform formats | XML → JSON, SOAP → REST |
| **Enricher** | Add data from external source | Order → add customer details |
| **Deduplicator** | Idempotent processing | Payment webhook dedup by idempotency key |

### Event Bus Integration

```typescript
// CloudEvents-compatible event bus
interface CloudEvent {
    specversion: string;       // "1.0"
    type: string;              // "com.example.order.created"
    source: string;            // "/orders/v1"
    id: string;                // UUID
    time: string;              // ISO 8601
    dataschema?: string;       // Schema URL
    data: Record<string, unknown>;
}

class EventBus {
    constructor(private broker: MessageBroker) {}

    async publish(event: CloudEvent): Promise<void> {
        // Validate CloudEvent spec
        if (!event.specversion || !event.type || !event.id) {
            throw new Error('Invalid CloudEvent format');
        }

        await this.broker.publish('app-events', {
            key: event.type,
            value: event,
            headers: {
                'ce-specversion': event.specversion,
                'ce-type': event.type,
                'ce-source': event.source,
                'ce-id': event.id,
            },
        });
    }

    subscribe(eventType: string, handler: (event: CloudEvent) => Promise<void>) {
        this.broker.subscribe('app-events', async (msg) => {
            if (msg.value.type === eventType) {
                try {
                    await handler(msg.value);
                    msg.ack();
                } catch (err) {
                    msg.nack(false, true); // Requeue
                }
            }
        });
    }
}
```

---

## Quick Reference: API Integration by Node Type

| Node Type | API Integration Mapping |
|---|---|
| **Input** | Request validation, rate limiting, auth, webhook receiver |
| **Logic** | Data transformation, orchestration, aggregation, routing |
| **Database** | API key store, webhook registration, event log |
| **UI** | API explorer (Swagger UI), webhook testing console |
| **API** | Gateway, subgraph, gRPC service, event producer/consumer |

---

*For deeper API concepts, see Bible levels `34-api-integration-platforms/`, `04-web-apps/`, `14-protocols/`, and `35-realtime-collaboration/`.*
