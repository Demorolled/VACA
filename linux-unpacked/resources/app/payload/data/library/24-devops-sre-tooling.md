# 🔧 DevOps & SRE Tooling

> Reference for DevOps and Site Reliability Engineering — monitoring, alerting, observability, incident response, and reliability engineering.
> Extracted from The Programming Bible's DevOps/SRE Tooling level.

---

## 1. DevOps Principles (CALMS)

| Principle | Description |
|---|---|
| **Culture** | Collaboration, shared responsibility, breaking down silos |
| **Automation** | Eliminating manual toil, everything-as-code |
| **Lean** | Flow efficiency, reducing waste, continuous improvement |
| **Measurement** | Data-driven decisions, actionable metrics |
| **Sharing** | Knowledge sharing, blameless postmortems, cross-team learning |

### The Three Ways

```
┌─────────────────────────────────────────────────────────┐
│  The First Way: Flow                                      │
│  Systems thinking — optimize the entire delivery flow     │
│  from Dev → Ops.                                          │
│                                                           │
│  The Second Way: Feedback                                 │
│  Shorten feedback loops — monitoring and alerts from      │
│  production back to developers.                           │
│                                                           │
│  The Third Way: Continuous Learning                       │
│  Experimentation, risk-taking, and constant improvement.  │
│  Blameless postmortems, chaos engineering.                │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Service Level Concepts

| Term | Definition | Example |
|---|---|---|
| **SLI** (Service Level Indicator) | Quantitative measure of service behavior | Request latency p99, error rate, uptime |
| **SLO** (Service Level Objective) | Target value for an SLI | 99.9% of requests < 200ms |
| **SLA** (Service Level Agreement) | Contractual commitment with consequences | 99.9% uptime SLA with credits |
| **Error Budget** | 100% - SLO — allowable unreliability | 0.1% for 99.9% SLO |

### Error Budget Policy

```typescript
interface ErrorBudget {
  slo: number;                    // e.g., 0.999 for 99.9%
  window: Duration;               // e.g., 30 days
  budget: number;                 // 1 - slo (e.g., 0.001)
  consumed: number;               // Current error rate
  remaining: number;              // budget - consumed
  burnRate: number;               // How fast budget is consumed
}

function calculateErrorBudget(slo: number, totalRequests: number, failedRequests: number): ErrorBudget {
  const budget = 1 - slo;
  const consumed = failedRequests / totalRequests;
  
  return {
    slo,
    window: { days: 30 },
    budget,
    consumed,
    remaining: budget - consumed,
    burnRate: consumed / budget,
  };
}

// Alert when burn rate indicates budget exhaustion
// e.g., 2x burn rate for 6 hours = 50% budget consumed in 6 hours
function checkBurnRateAlert(budget: ErrorBudget): string | null {
  if (budget.burnRate >= 2) {
    return `CRITICAL: Budget burning at ${(budget.burnRate * 100).toFixed(0)}% rate`;
  }
  if (budget.burnRate >= 1) {
    return `WARNING: Budget burning at ${(budget.burnRate * 100).toFixed(0)}% rate`;
  }
  return null;
}
```

---

## 3. Monitoring & Alerting (Prometheus)

### Metrics Collection Architecture

```
Application / Exporter
    │  /metrics (HTTP endpoint)
    ▼
Prometheus Server
    │  (pull model, scrape targets)
    ▼
┌──────────────┬──────────────┐
│              │              │
▼              ▼              ▼
Alertmanager   Thanos        Grafana
(Alerting)     (Long-term)   (Visualization)
```

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # Kubernetes service discovery
  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__

  # Static targets
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
        labels:
          env: 'production'
```

### PromQL Cheatsheet

```promql
# Request rate (per second)
rate(http_requests_total[5m])

# Request latency p99
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Error ratio
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# CPU utilization
avg(rate(node_cpu_seconds_total{mode!="idle"}[5m])) by (instance)

# Memory utilization
(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100

# Up/down status
up{job="api-server"} == 0  # Alerts when service is down

# Predict disk full in 24 hours
predict_linear(node_filesystem_free_bytes{mountpoint="/"}[6h], 86400) < 0
```

### Application Metrics Instrumentation

```typescript
// Custom metrics for your application
import prometheus from 'prom-client';

// Create a registry
const register = new prometheus.Registry();
prometheus.collectDefaultMetrics({ register });

// HTTP request counter
const httpRequestsTotal = new prometheus.Counter({
  name: 'http_requests_total',
  help: 'Total number of HTTP requests',
  labelNames: ['method', 'route', 'status'],
  registers: [register],
});

// Request duration histogram
const httpRequestDuration = new prometheus.Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['method', 'route'],
  buckets: [0.01, 0.05, 0.1, 0.5, 1, 2, 5],
  registers: [register],
});

// Active requests gauge
const activeRequests = new prometheus.Gauge({
  name: 'http_requests_active',
  help: 'Number of active HTTP requests',
  registers: [register],
});

// Middleware
function metricsMiddleware(req: any, res: any, next: any): void {
  const end = httpRequestDuration.startTimer();
  activeRequests.inc();

  res.on('finish', () => {
    httpRequestsTotal.inc({ method: req.method, route: req.route?.path ?? 'unknown', status: res.statusCode });
    end({ method: req.method, route: req.route?.path ?? 'unknown' });
    activeRequests.dec();
  });

  next();
}

// Metrics endpoint
app.get('/metrics', async (_req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});
```

---

## 4. Logging & Observability Pipeline

### Pipeline Architecture

```
Source → Shipper → Buffer → Indexer → Storage → Visualization
  │         │          │        │          │          │
  │     Fluent Bit  Kafka  Logstash  Elasticsearch  Kibana
  │     Vector            Fluentd  Loki         Grafana
  │     Promtail                    ClickHouse
```

### Structured Logging Pattern

```typescript
// Structured log format for observability
interface LogEntry {
  '@timestamp': string;
  message: string;
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'FATAL';
  service: string;
  request_id: string;
  trace_id?: string;
  span_id?: string;
  user_id?: string;
  duration_ms?: number;
  error?: {
    type: string;
    message: string;
    stack_trace: string;
  };
  metadata?: Record<string, unknown>;
}

// Structured logger
class StructuredLogger {
  constructor(private service: string) {}

  info(message: string, metadata?: Record<string, unknown>): void {
    this.log('INFO', message, metadata);
  }

  error(message: string, error?: Error, metadata?: Record<string, unknown>): void {
    this.log('ERROR', message, {
      ...metadata,
      error: error ? {
        type: error.name,
        message: error.message,
        stack_trace: error.stack ?? '',
      } : undefined,
    });
  }

  private log(level: string, message: string, metadata?: Record<string, unknown>): void {
    const entry: LogEntry = {
      '@timestamp': new Date().toISOString(),
      message,
      level: level as LogEntry['level'],
      service: this.service,
      request_id: metadata?.request_id as string ?? '',
      ...metadata,
    };

    // Write as JSON to stdout (captured by log shipper)
    process.stdout.write(JSON.stringify(entry) + '\n');
  }
}

// Usage
const logger = new StructuredLogger('api-server');
logger.info('Request received', { method: 'GET', path: '/users', request_id: 'abc-123' });
logger.error('Database query failed', new Error('Connection timeout'), { query: 'SELECT...' });
```

### Elasticsearch Index Template

```json
{
  "index_patterns": ["logs-*"],
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 2,
      "index.lifecycle.name": "logs-policy",
      "index.lifecycle.rollover_alias": "logs"
    },
    "mappings": {
      "dynamic": "strict",
      "properties": {
        "@timestamp": { "type": "date" },
        "message": { "type": "text" },
        "level": { "type": "keyword" },
        "service": { "type": "keyword" },
        "request_id": { "type": "keyword" },
        "trace_id": { "type": "keyword" },
        "duration_ms": { "type": "integer" },
        "error": {
          "properties": {
            "type": { "type": "keyword" },
            "message": { "type": "text" },
            "stack_trace": { "type": "text", "index": false }
          }
        }
      }
    }
  }
}
```

---

## 5. Incident Response

### Incident Severity Levels

| Level | Description | Response Time | Example |
|---|---|---|---|
| **SEV-1** | Critical — service down or data loss | Immediate, <15min | Production outage |
| **SEV-2** | Major — degraded service | <30min | Slow responses, partial outage |
| **SEV-3** | Minor — non-critical issue | <4hrs | UI bug, non-critical feature broken |
| **SEV-4** | Low — cosmetic or minor | <1 week | Documentation, minor improvements |

### Incident Response Flow

```
1. Detection (Alert / User Report)
      │
2. Triage ──→ Is it real? How severe?
      │
3. Mitigate ──→ Stop the bleeding (rollback, redirect traffic, feature flag)
      │
4. Resolve ──→ Fix root cause
      │
5. Postmortem ──→ What happened? How do we prevent recurrence?
```

### Blameless Postmortem Template

```markdown
## Postmortem: [Title]
**Date:** YYYY-MM-DD
**Severity:** SEV-1
**Duration:** 45 minutes (14:30 - 15:15 UTC)

### Summary
Brief description of what happened and impact.

### Timeline
- **14:30** — Alert fired: HTTP error rate > 5%
- **14:32** — Engineer on-call acknowledged
- **14:35** — Identified deployment v2.3.1 caused issue
- **14:37** — Rollback initiated to v2.3.0
- **14:45** — Rollback complete, error rate normalizing
- **15:15** — Monitoring confirmed all-clear

### Root Cause
New deployment included a database migration that held a long-running lock.

### Action Items
- [ ] Add automated rollback trigger for error rate > 3%
- [ ] Add pre-deploy DB migration lock check
- [ ] Update deployment checklist to include migration review

### Lessons Learned
- What went well: Fast detection via metrics alert
- What went wrong: Migration not reviewed by DBA
- What to improve: Automated rollback triggers
```

---

## 6. Chaos Engineering

| Principle | Description |
|---|---|
| **Steady state hypothesis** | Define what normal looks like |
| **Run experiments** | Inject failures in a controlled way |
| **Minimize blast radius** | Start small, expand gradually |
| **Automate experiments** | Run continuously as part of CI |

```typescript
// Chaos experiment example
interface ChaosExperiment {
  name: string;
  target: string;           // Service, pod, or region
  attack: string;           // 'kill', 'latency', 'error'
  duration: number;         // Seconds
  blastRadius: number;      // Percentage of targets affected
}

async function runChaosExperiment(exp: ChaosExperiment): Promise<void> {
  console.log(`Running experiment: ${exp.name}`);
  console.log(`Target: ${exp.target}, Attack: ${exp.attack}`);

  // 1. Establish steady state
  const baselineMetrics = await captureMetrics(exp.target);

  // 2. Inject failure
  await injectFault(exp.target, exp.attack, exp.duration, exp.blastRadius);

  // 3. Observe impact
  await sleep(exp.duration * 1000);

  // 4. Compare metrics
  const impactedMetrics = await captureMetrics(exp.target);
  const degraded = compareMetrics(baselineMetrics, impactedMetrics);

  if (degraded) {
    console.log(`Experiment caused degradation — validate mitigation or accept risk`);
  } else {
    console.log(`System resilient to ${exp.attack} on ${exp.target}`);
  }
}
```

---

## Quick Reference: DevOps/SRE by Node Type

| Node Type | DevOps/SRE Mapping |
|---|---|
| **Input** | Alert webhooks, metric collection, log ingestion |
| **Logic** | Alert evaluation, error budget calculation, incident orchestration |
| **Database** | Metrics TSDB, log storage, incident tracking DB |
| **UI** | Monitoring dashboards, incident management console, on-call schedule |
| **API** | Prometheus/Grafana APIs, PagerDuty integration, status page |

---

*For deeper DevOps/SRE concepts, see Bible level `33-devops-sre-tooling/` and `12-devops/` — CI/CD, IaC, secrets management, container security, and observability.*
