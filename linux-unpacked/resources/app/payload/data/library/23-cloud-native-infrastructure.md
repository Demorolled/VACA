# ☁️ Cloud-Native Infrastructure

> Reference for cloud-native applications — Kubernetes, containers, GitOps, service mesh, and infrastructure-as-code patterns.
> Extracted from The Programming Bible's Cloud-Native Infrastructure and Virtualization/Containers levels.

---

## 1. Cloud-Native Architecture Principles

### CNCF Definition

| Principle | Description |
|---|---|
| **Containers** | OCI-compliant images for packaging applications |
| **Microservices** | Independently deployable services with bounded contexts |
| **Orchestration** | Cluster schedulers (Kubernetes) for managing containers |
| **Declarative APIs** | Desired state reconciliation — never imperative |
| **Immutable Infrastructure** | Never update in place — always replace |
| **Observability** | Metrics, logs, traces, and events for insight |

### Architecture Comparison

| Aspect | Traditional | Cloud-Native |
|---|---|---|
| **Deployment** | Bare metal or VMs | Containers |
| **Scaling** | Vertical (bigger server) | Horizontal (more replicas) |
| **Updates** | In-place patching | Rolling replacements |
| **State** | Local state, sticky sessions | Stateless, externalized state |
| **Config** | Config files on disk | Environment/ConfigMaps |
| **Discovery** | Hardcoded IPs or DNS | Service registry / DNS |

---

## 2. Container Fundamentals

### Linux Kernel Features

```
┌──────────────────────────────────────────────┐
│                  CONTAINER                     │
│                                                 │
│  ┌──────────────────┐  ┌──────────────────┐   │
│  │   Namespaces     │  │   Cgroups        │   │
│  │                  │  │                  │   │
│  │ PID namespace    │  │ CPU limit        │   │
│  │ Network namespace│  │ Memory limit     │   │
│  │ Mount namespace  │  │ I/O limit        │   │
│  │ User namespace   │  │ PID limit        │   │
│  │ UTS namespace    │  │                  │   │
│  │ IPC namespace    │  │                  │   │
│  └──────────────────┘  └──────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │               Union FS                    │  │
│  │  (OverlayFS — container image layers)     │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

### OCI Container Lifecycle

```bash
# Container lifecycle commands
docker pull alpine:latest          # Download image layers
docker create --name myapp alpine  # Create container (writable layer)
docker start myapp                  # Start (cgroup + namespace setup)
docker exec myapp ls               # Execute in namespace
docker stop myapp                   # SIGTERM → SIGKILL
docker rm myapp                     # Remove writable layer
```

### Container Runtime

```go
// Minimal container runner (simplified — demonstrates concepts)
package main

import (
    "os/exec"
    "syscall"
)

func createContainer(imagePath string, command []string) error {
    cmd := exec.Command(command[0], command[1:]...)

    // Namespace isolation
    cmd.SysProcAttr = &syscall.SysProcAttr{
        Cloneflags: syscall.CLONE_NEWPID |  // Isolated PID space
            syscall.CLONE_NEWNS |            // Isolated mount table
            syscall.CLONE_NEWNET |           // Isolated network stack
            syscall.CLONE_NEWUTS,            // Isolated hostname
    }

    // Set cgroup limits (simplified — normally done via cgroupfs)
    // echo "100000" > /sys/fs/cgroup/pids/container/pids.max

    // Chroot into the container filesystem
    cmd.Dir = imagePath
    cmd.SysProcAttr.Chroot = imagePath

    return cmd.Run()
}
```

---

## 3. Kubernetes Architecture

```
                        ┌──────────────────────┐
                        │    CONTROL PLANE       │
                        │                        │
                        │  ┌────────────────┐   │
                        │  │  kube-apiserver│   │
                        │  └───────┬────────┘   │
                        │          │            │
                        │  ┌───────▼────────┐   │
                        │  │     etcd       │   │
                        │  └────────────────┘   │
                        │                        │
                        │  ┌────────────────┐   │
                        │  │ kube-scheduler │   │
                        │  └────────────────┘   │
                        │                        │
                        │  ┌────────────────┐   │
                        │  │kube-controller- │   │
                        │  │   manager      │   │
                        │  └────────────────┘   │
                        └──────────────────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                  │
        ┌───────▼──────┐  ┌──────▼───────┐  ┌──────▼───────┐
        │  WORKER NODE  │  │ WORKER NODE  │  │ WORKER NODE  │
        │               │  │              │  │              │
        │ ┌───────────┐ │  │ ┌──────────┐│  │ ┌──────────┐ │
        │ │  kubelet  │ │  │ │ kubelet  ││  │ │ kubelet  │ │
        │ └───────────┘ │  │ └──────────┘│  │ └──────────┘ │
        │ ┌───────────┐ │  │ ┌──────────┐│  │ ┌──────────┐ │
        │ │  kube-proxy│ │  │ │kube-proxy││  │ │kube-proxy│ │
        │ └───────────┘ │  │ └──────────┘│  │ └──────────┘ │
        │ ┌────┐ ┌────┐ │  │ ┌────┐ ┌───┐│  │ ┌────┐ ┌───┐│
        │ │Pod │ │Pod │ │  │ │Pod │ │Pod││  │ │Pod │ │Pod││
        │ └────┘ └────┘ │  │ └────┘ └───┘│  │ └────┘ └───┘│
        └───────────────┘  └──────────────┘  └─────────────┘
```

### Core Kubernetes Resources

| Resource | Kind | Purpose |
|---|---|---|
| **Pod** | Pod | Smallest deployable unit — one or more containers |
| **Deployment** | Deployment | Declarative updates for Pods (ReplicaSet management) |
| **Service** | Service | Stable network endpoint for Pods (ClusterIP, NodePort, LB) |
| **ConfigMap** | ConfigMap | Non-sensitive configuration (env vars, files) |
| **Secret** | Secret | Sensitive data (base64 encoded) |
| **Ingress** | Ingress | HTTP/HTTPS routing to Services |
| **PersistentVolumeClaim** | PVC | Storage request for Pods |
| **StatefulSet** | StatefulSet | Stateful applications with stable identities |
| **DaemonSet** | DaemonSet | One Pod per Node (logging, monitoring) |
| **Job/CronJob** | Job | Batch and scheduled workloads |

### Kubernetes YAML Pattern

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  labels:
    app: myapp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: myapp
  template:
    metadata:
      labels:
        app: myapp
    spec:
      containers:
      - name: app
        image: myapp:1.0.0
        ports:
        - containerPort: 3000
        env:
        - name: NODE_ENV
          value: "production"
        - name: DB_URL
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: database-url
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "256Mi"
        livenessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 10
          periodSeconds: 15
        readinessProbe:
          httpGet:
            path: /ready
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: myapp-service
spec:
  selector:
    app: myapp
  ports:
  - port: 80
    targetPort: 3000
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp-ingress
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  rules:
  - host: app.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: myapp-service
            port:
              number: 80
```

### Kubernetes Operator Pattern

```typescript
// Operator reconciliation loop (conceptual)
interface CustomResource {
  apiVersion: string;
  kind: string;
  metadata: { name: string; namespace: string };
  spec: {
    replicas: number;
    image: string;
    version: string;
    storage: { size: string; class: string };
  };
  status: {
    phase: 'pending' | 'running' | 'failed';
    conditions: Condition[];
  };
}

class OperatorReconciler {
  async reconcile(resource: CustomResource): Promise<void> {
    // 1. Get current state from cluster
    const currentDeployment = await this.getDeployment(resource);

    // 2. Compare with desired state
    const desiredReplicas = resource.spec.replicas;
    const currentReplicas = currentDeployment?.spec.replicas ?? 0;

    // 3. Reconcile differences
    if (currentReplicas !== desiredReplicas) {
      await this.updateDeployment(resource, { replicas: desiredReplicas });
    }

    // 4. Create resources if they don't exist
    if (!currentDeployment) {
      await this.createDeployment(resource);
      await this.createService(resource);
      await this.createPVC(resource);
    }

    // 5. Update status
    await this.updateStatus(resource, {
      phase: 'running',
      conditions: [{ type: 'Ready', status: 'True' }],
    });
  }
}
```

---

## 4. GitOps & Continuous Delivery

### GitOps Principles

```
Git Repository (Source of Truth)
    │
    │  ┌─────────────┐
    ├──│ Manifests   │  ← Kubernetes YAML, Helm charts
    │  └─────────────┘
    │  ┌─────────────┐
    ├──│ Kustomize   │  ← Environment overlays
    │  └─────────────┘
    │
    ▼
GitOps Operator (ArgoCD / Flux)
    │
    ├── Pull changes from Git
    ├── Diff against cluster state
    └── Apply to cluster
          │
          ▼
    Kubernetes Cluster
```

### ArgoCD Architecture

| Component | Function |
|---|---|
| **API Server** | UI, CLI, API, RBAC, auth |
| **Repository Server** | Git clone, manifest generation (Helm/Kustomize) |
| **Application Controller** | State watcher, drift detection, reconciliation |
| **Redis** | Cache for repo manifests and controller state |
| **Dex** | Optional identity provider for SSO |

### GitOps Application Manifest

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp-production
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/org/myapp-gitops
    targetRevision: main
    path: overlays/production
    helm:
      valuesFiles:
        - values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: myapp
  syncPolicy:
    automated:
      prune: true       # Remove resources deleted from Git
      selfHeal: true    # Revert manual changes
    syncOptions:
      - CreateNamespace=true
```

---

## 5. Service Mesh (Istio)

### Service Mesh Architecture

```
Without Service Mesh:               With Service Mesh (Istio):
┌──────────────────────┐           ┌──────────────────────────┐
│  Service A ────────▶ │           │  Service A ──▶ Envoy ────▶│
│  (direct call)     Service B     │                ▲         Service B
│                      │           │                │          │
└──────────────────────┘           │           Control       │
                                    │           Plane         │
                                    │           (Istiod)      │
                                    └──────────────────────────┘
```

### Istio Components

| Component | Function |
|---|---|
| **Envoy Proxy** | Sidecar proxy — intercepts all traffic (L4/L7) |
| **Pilot** | xDS config translation (K8s CRDs → Envoy config) |
| **Citadel** | Certificate Authority — SPIFFE workload identity, mTLS |
| **Galley** | Config ingestion/validation (merged into Istiod) |
| **Istio IngressGateway** | Public-facing Envoy deployment |

### Service Mesh Features

```yaml
# Traffic routing — canary deployment
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: myapp
spec:
  hosts:
  - myapp
  http:
  - match:
    - headers:
        x-canary:
          exact: "true"
    route:
    - destination:
        host: myapp
        subset: v2
      weight: 100
  - route:
    - destination:
        host: myapp
        subset: v1
      weight: 90
    - destination:
        host: myapp
        subset: v2
      weight: 10
---
# mTLS enforcement
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system
spec:
  mtls:
    mode: STRICT  # All traffic must use mTLS
```

---

## 6. Infrastructure as Code

### Terraform Pattern

```hcl
# Terraform — declarative infrastructure
provider "kubernetes" {
  config_path = "~/.kube/config"
}

resource "kubernetes_namespace" "app" {
  metadata {
    name = var.namespace
    labels = {
      environment = var.environment
      managed-by  = "terraform"
    }
  }
}

resource "kubernetes_deployment" "app" {
  metadata {
    name      = var.app_name
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = {
        app = var.app_name
      }
    }

    template {
      metadata {
        labels = {
          app = var.app_name
        }
      }

      spec {
        container {
          image = var.image
          name  = var.app_name

          port {
            container_port = var.container_port
          }

          resources {
            requests = {
              cpu    = var.cpu_request
              memory = var.memory_request
            }
            limits = {
              cpu    = var.cpu_limit
              memory = var.memory_limit
            }
          }
        }
      }
    }
  }
}

variable "app_name" {
  type        = string
  description = "Application name"
}

variable "environment" {
  type        = string
  default     = "production"
}

variable "replicas" {
  type        = number
  default     = 3
}

variable "image" {
  type        = string
  description = "Container image with tag"
}

variable "container_port" {
  type        = number
  default     = 3000
}

variable "cpu_request" {
  type        = string
  default     = "100m"
}

variable "memory_request" {
  type        = string
  default     = "128Mi"
}

variable "cpu_limit" {
  type        = string
  default     = "500m"
}

variable "memory_limit" {
  type        = string
  default     = "256Mi"
}

output "namespace" {
  value = kubernetes_namespace.app.metadata[0].name
}
```

---

## Quick Reference: Cloud-Native by Node Type

| Node Type | Cloud-Native Mapping |
|---|---|
| **Input** | Ingress controller, API gateway, webhook receiver |
| **Logic** | Microservice handler, operator reconciliation, sidecar logic |
| **Database** | StatefulSet with PVC, ConfigMap/Secret, external DB service |
| **UI** | Dashboard (Deployment + Service + Ingress) |
| **API** | Service mesh routing, gRPC inter-service, mTLS, circuit breaking |

---

*For deeper cloud-native concepts, see Bible levels `32-cloud-native-infra/`, `17-virtualization-containers/`, and `12-devops/` — Kubernetes operators, GitOps, service mesh, eBPF, and container runtimes.*
