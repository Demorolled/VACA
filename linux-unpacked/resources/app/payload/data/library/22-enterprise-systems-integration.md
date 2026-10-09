# 🏢 Enterprise Systems Integration

> Reference for building enterprise applications and integrating with business systems — ERP, CRM, SCM, and enterprise architecture patterns.
> Extracted from The Programming Bible's Enterprise Systems level.

---

## 1. Enterprise System Landscape

### Core Business Systems

```
┌─────────────────────────────────────────────────────┐
│              ENTERPRISE SYSTEM LANDSCAPE             │
│                                                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐  │
│  │   ERP   │  │   CRM   │  │   SCM   │  │  HCM   │  │
│  │ Finance│  │  Sales  │  │  Supply │  │  HR    │  │
│  │  Ops   │  │Service  │  │  Chain  │  │Payroll │  │
│  └────┬────┘  └────┬────┘  └────┬────┘  └───┬────┘  │
│       │            │            │            │       │
│       └────────────┴────────────┴────────────┘       │
│                        │                              │
│                 ┌──────▼──────┐                       │
│                 │ Integration │                       │
│                 │    Bus      │                       │
│                 │ (ESB/API)   │                       │
│                 └─────────────┘                       │
└─────────────────────────────────────────────────────┘
```

| System | Function | Key Data |
|---|---|---|
| **ERP** (Enterprise Resource Planning) | Finance, accounting, procurement, manufacturing | GL accounts, POs, invoices, inventory |
| **CRM** (Customer Relationship Management) | Sales, marketing, customer service | Contacts, leads, opportunities, cases |
| **SCM** (Supply Chain Management) | Logistics, warehousing, transportation | Orders, shipments, inventory levels |
| **HCM** (Human Capital Management) | HR, payroll, recruiting | Employees, org structure, time tracking |
| **EAM** (Enterprise Asset Management) | Asset lifecycle, maintenance | Equipment, work orders, maintenance schedules |
| **BI/Analytics** | Reporting, dashboards, KPIs | Aggregated data from all systems |

---

## 2. Enterprise Architecture Patterns

### Integration Patterns

| Pattern | Description | When to Use |
|---|---|---|
| **Point-to-Point** | Direct connections between systems | Small number of integrations (< 5) |
| **ESB** (Enterprise Service Bus) | Central message routing hub | Many integrations with transformation |
| **API Gateway** | Unified API layer for services | Microservices, external access |
| **Event-Driven** | Async publish/subscribe | Real-time data sync, decoupled systems |
| **Batch/ETL** | Scheduled data transfers | Nightly syncs, data warehousing |
| **Change Data Capture** | Real-time DB change streaming | Keeping systems in sync |

### API Gateway Pattern for Enterprise

```typescript
// Enterprise API Gateway pattern
import express from 'express';
import rateLimit from 'express-rate-limit';

interface EnterpriseService {
  name: string;
  baseUrl: string;
  routes: EnterpriseRoute[];
  authType: 'apiKey' | 'oauth2' | 'jwt' | 'mutualTls';
}

interface EnterpriseRoute {
  path: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  targetPath: string;
  rateLimit?: number; // requests per minute
  requiredRoles?: string[];
}

class EnterpriseGateway {
  private app = express();
  private services: Map<string, EnterpriseService> = new Map();

  registerService(service: EnterpriseService): void {
    this.services.set(service.name, service);

    for (const route of service.routes) {
      const fullPath = `/api/v1/${service.name}${route.path}`;

      // Apply rate limiting if configured
      const middleware: any[] = [];
      if (route.rateLimit) {
        middleware.push(rateLimit({
          windowMs: 60 * 1000,
          max: route.rateLimit,
          message: { error: 'Rate limit exceeded', code: 'ERR_RATE_LIMIT' },
        }));
      }

      // Auth middleware
      middleware.push(this.authMiddleware(service));

      // Role check
      if (route.requiredRoles?.length) {
        middleware.push(this.roleMiddleware(route.requiredRoles));
      }

      this.app[route.method.toLowerCase() as keyof express.Express](
        fullPath,
        ...middleware,
        async (req, res) => {
          await this.proxyRequest(req, res, service, route);
        }
      );
    }
  }

  private async proxyRequest(req: express.Request, res: express.Response, service: EnterpriseService, route: EnterpriseRoute): Promise<void> {
    const targetUrl = `${service.baseUrl}${route.targetPath}`;
    const startTime = Date.now();

    try {
      const response = await fetch(targetUrl, {
        method: req.method,
        headers: {
          'Content-Type': 'application/json',
          'X-Request-Id': req.headers['x-request-id'] as string ?? crypto.randomUUID(),
          ...this.getServiceAuthHeaders(service),
        },
        body: req.method !== 'GET' ? JSON.stringify(req.body) : undefined,
      });

      const data = await response.json();
      const duration = Date.now() - startTime;

      // Log for audit trail
      console.log({
        service: service.name,
        path: route.path,
        status: response.status,
        duration,
        requestId: req.headers['x-request-id'],
      });

      res.status(response.status).json(data);
    } catch (err) {
      console.error(`Gateway error: ${service.name}/${route.path}`, err);
      res.status(502).json({
        error: `Service ${service.name} unavailable`,
        code: 'ERR_SERVICE_UNAVAILABLE',
      });
    }
  }

  private authMiddleware(service: EnterpriseService): express.RequestHandler {
    return (req, _res, next) => {
      // Implement auth check based on service.authType
      next();
    };
  }

  private roleMiddleware(roles: string[]): express.RequestHandler {
    return (req, res, next) => {
      const userRoles = (req as any).user?.roles ?? [];
      const hasRole = roles.some(r => userRoles.includes(r));
      if (!hasRole) {
        return res.status(403).json({ error: 'Insufficient permissions', code: 'ERR_FORBIDDEN' });
      }
      next();
    };
  }

  private getServiceAuthHeaders(service: EnterpriseService): Record<string, string> {
    // Return appropriate auth headers for the service
    return {};
  }

  listen(port: number): void {
    this.app.listen(port, () => {
      console.log(`Enterprise gateway listening on port ${port}`);
    });
  }
}
```

---

## 3. ERP Core Concepts

### Financial Data Model

```
Double-Entry Accounting: Every transaction has equal debits and credits

                     General Ledger
                     ┌─────────────┐
                     │ Account     │
                     │ Number: 4000│
                     │ Type: P&L   │
                     └──────┬──────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
         ┌────▼───┐   ┌────▼───┐   ┌────▼───┐
         │AP      │   │AR      │   │Fixed   │
         │Subledger│   │Subledger│  │Assets  │
         └────────┘   └────────┘   └────────┘
```

### Chart of Accounts Structure

```typescript
interface GLAccount {
  accountNumber: string;       // e.g., '4000-100'
  name: string;                // e.g., 'Revenue - Product Sales'
  type: 'asset' | 'liability' | 'equity' | 'revenue' | 'expense';
  category: string;            // e.g., 'Cash', 'Accounts Receivable'
  isControlAccount: boolean;   // Links to subledger
  isOpenItemManaged: boolean;  // Tracks individual items (invoices)
  currency: string;
  taxRelevant: boolean;
  active: boolean;
}

interface JournalEntry {
  id: string;
  documentNumber: string;      // Unique doc per company code
  companyCode: string;
  postingDate: Date;
  documentDate: Date;
  currency: string;
  headerText: string;
  reference: string;
  lines: JournalEntryLine[];
  createdBy: string;
  createdAt: Date;
  approved: boolean;
}

interface JournalEntryLine {
  accountNumber: string;
  debitAmount: number;
  creditAmount: number;
  text: string;
  costCenter?: string;
  profitCenter?: string;
  taxCode?: string;
}
```

### ERP Integration Pattern

```typescript
// SAP/REST integration pattern
class ERPConnector {
  constructor(
    private baseUrl: string,
    private clientId: string,
    private clientSecret: string,
  ) {}

  private async getToken(): Promise<string> {
    const response = await fetch(`${this.baseUrl}/oauth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'client_credentials',
        client_id: this.clientId,
        client_secret: this.clientSecret,
      }),
    });

    const data = await response.json();
    return data.access_token;
  }

  async createSalesOrder(order: SalesOrder): Promise<SalesOrderResponse> {
    const token = await this.getToken();
    const response = await fetch(`${this.baseUrl}/api/v2/salesorders`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        salesOrderType: 'OR',  // Standard order
        soldToParty: order.customerId,
        requestedDeliveryDate: order.requestedDelivery.toISOString(),
        items: order.items.map(item => ({
          material: item.productCode,
          quantity: item.quantity,
          unitPrice: item.unitPrice,
          currency: 'USD',
        })),
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ERP error: ${response.status} - ${error}`);
    }

    return response.json();
  }

  async checkInventory(plant: string, material: string): Promise<number> {
    const token = await this.getToken();
    const response = await fetch(
      `${this.baseUrl}/api/v2/inventory?plant=${plant}&material=${material}`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    );

    const data = await response.json();
    return data.stockQuantity;
  }
}
```

---

## 4. CRM Data Model

### Core CRM Objects

```
              ┌──────────┐
              │ Account  │   (Company/Organization)
              │──────────│
              │ Industry │   ──┐
              │ Revenue  │     ├── Firmographics
              │ Employees│   ──┘
              │ Territory│
              └────┬─────┘
                   │
         ┌─────────┼─────────┐
         │         │         │
    ┌────▼───┐ ┌───▼───┐ ┌──▼────┐
    │Contact │ │Opportunity│ │ Case │
    │────────│ │──────────│ │──────│
    │Email   │ │Stage     │ │Status│
    │Phone   │ │Amount    │ │Origin│
    │Title   │ │CloseDate │ │      │
    └────────┘ └──────────┘ └──────┘
```

### CRM Integration

```typescript
interface CRMContact {
  id: string;
  accountId: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  title: string;
  ownerId: string;
  createdAt: Date;
  lastActivity: Date;
}

class CRMClient {
  constructor(private apiUrl: string, private apiKey: string) {}

  async syncContact(contact: Partial<CRMContact>): Promise<CRMContact> {
    const response = await fetch(`${this.apiUrl}/crm/v3/objects/contacts`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        properties: {
          firstname: contact.firstName,
          lastname: contact.lastName,
          email: contact.email,
          phone: contact.phone,
          jobtitle: contact.title,
        },
      }),
    });

    if (!response.ok) {
      throw new Error(`CRM sync failed: ${response.status}`);
    }

    const data = await response.json();
    return this.mapCRMResponse(data);
  }

  async searchContacts(email: string): Promise<CRMContact[]> {
    const response = await fetch(`${this.apiUrl}/crm/v3/objects/contacts/search`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filterGroups: [{
          filters: [{ propertyName: 'email', operator: 'EQ', value: email }],
        }],
      }),
    });

    const data = await response.json();
    return data.results.map(this.mapCRMResponse);
  }

  private mapCRMResponse(data: any): CRMContact {
    return {
      id: data.id,
      accountId: data.properties?.company ?? '',
      firstName: data.properties?.firstname ?? '',
      lastName: data.properties?.lastname ?? '',
      email: data.properties?.email ?? '',
      phone: data.properties?.phone ?? '',
      title: data.properties?.jobtitle ?? '',
      ownerId: data.properties?.hubspot_owner_id ?? '',
      createdAt: new Date(data.createdAt),
      lastActivity: new Date(data.updatedAt),
    };
  }
}
```

---

## 5. Enterprise Integration Patterns

### Event-Driven Integration

```typescript
// Enterprise event bus pattern
interface EnterpriseEvent {
  source: string;      // 'erp', 'crm', 'scm'
  type: string;        // 'order.created', 'invoice.paid'
  payload: unknown;
  timestamp: Date;
  correlationId: string;
}

class EnterpriseEventBus {
  private handlers: Map<string, ((event: EnterpriseEvent) => Promise<void>)[]> = new Map();
  private deadLetterQueue: EnterpriseEvent[] = [];

  on(eventType: string, handler: (event: EnterpriseEvent) => Promise<void>): void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, []);
    }
    this.handlers.get(eventType)!.push(handler);
  }

  async emit(event: EnterpriseEvent): Promise<void> {
    console.log(`Event: ${event.source}/${event.type}`, { correlationId: event.correlationId });

    const handlers = this.handlers.get(event.type) ?? [];
    for (const handler of handlers) {
      try {
        await handler(event);
      } catch (err) {
        console.error(`Handler failed for ${event.type}:`, err);
        this.deadLetterQueue.push(event);
      }
    }
  }

  // Orchestration: order → inventory check → invoice → shipping
  async placeOrder(order: SalesOrder): Promise<void> {
    const correlationId = crypto.randomUUID();

    await this.emit({
      source: 'app',
      type: 'order.created',
      payload: order,
      timestamp: new Date(),
      correlationId,
    });

    // The event bus will trigger:
    // 1. CRM: create opportunity
    // 2. ERP: check inventory, create sales order
    // 3. SCM: initiate fulfillment
    // 4. Notification: send confirmation
  }
}
```

---

## Quick Reference: Enterprise by Node Type

| Node Type | Enterprise Mapping |
|---|---|
| **Input** | API gateway, EDI parsing, file import, webhook receiver |
| **Logic** | Business rules engine, approval workflow, data transformation |
| **Database** | Multi-tenant DB, audit trail, data warehouse, reporting |
| **UI** | Dashboard, admin panel, report viewer, approval screen |
| **API** | REST/SOAP integration, OData, event bus, batch sync |

---

*For deeper enterprise concepts, see Bible level `26-enterprise-systems/` — ERP, CRM, SCM, e-commerce, CMS, HR systems, and supply chain.*
