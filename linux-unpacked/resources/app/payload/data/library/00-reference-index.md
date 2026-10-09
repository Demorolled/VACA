# 📚 Visual AI Architect — Reference Library Index

> Master index of all reference materials available to the LLM app builder.
> Use this index to locate the right reference file for any code generation task.

---

## 🗂️ Library Structure

```
data/
├── library/                          ← App-builder-specific reference
│   ├── 00-reference-index.md         ← THIS FILE — Master index
│   ├── 01-node-architecture-reference.md  ← Node type specs & code generation patterns
│   ├── 02-app-type-templates.md      ← Templates for common app architectures
│   ├── 03-code-generation-rules.md   ← Rules & patterns for clean code generation
│   ├── 04-technology-mapping.md      ← Language/framework selection per node type
│   ├── 05-design-patterns.md         ← Common design patterns for generated code
│   ├── 06-data-flow-patterns.md      ← Data flow patterns for node-based apps
│   ├── 07-node-implementation-guide.md  ← How to implement each node type in code
│   ├── 08-testing-patterns.md          ← Testing strategies: unit, integration, E2E, property-based
│   ├── 09-deployment-templates.md      ← Deployment: systemd, FHS, .deb packages, Nginx
│   ├── 10-cicd-configuration.md        ← CI/CD: GitHub Actions, pre-commit, release workflows
│   ├── 11-debugging-strategies.md      ← Debugging: logging, error diagnosis, profiling
│   ├── 12-game-development-patterns.md ← Game dev: game loop, ECS, collision, AI, networking
│   ├── 13-desktop-application-architecture.md ← Desktop apps: event loop, widgets, Linux integration
│   ├── 14-web-application-architecture.md  ← Full-stack web: frontend, backend, API design, middleware
│   ├── 15-database-design-patterns.md  ← DB design: B+Trees, indexing, query optimization, migrations
│   ├── 16-systems-programming-guide.md ← Systems: memory mgmt, concurrency, compilers, profiling
│   ├── 17-security-architecture-guide.md  ← Security: threat modeling, auth, XSS/SQLi prevention
│   ├── 18-media-multimedia-processing.md ← Media: audio/video codecs, streaming, DCC architecture
│   ├── 19-ai-ml-integration-guide.md     ← AI/ML: model serving, training pipelines, LLM integration
│   ├── 20-networking-communication-protocols.md ← Networking: TCP/IP, HTTP/3, WebRTC, WebSocket
│   ├── 21-iot-embedded-systems.md        ← IoT: MQTT, RTOS, edge computing, device protocols
│   ├── 22-enterprise-systems-integration.md  ← Enterprise: ERP, CRM, APIs, event-driven integration
│   ├── 23-cloud-native-infrastructure.md ← Cloud: Kubernetes, containers, GitOps, service mesh
│   ├── 24-devops-sre-tooling.md         ← DevOps/SRE: monitoring, alerting, SLOs, observability
│   ├── 25-distributed-systems.md        ← Distributed: consensus, Raft, message queues, CAP
│   ├── 26-data-engineering-analytics.md ← Data: ETL, stream processing, warehousing, Airflow
│   ├── 27-mobile-cross-platform.md      ← Mobile: React Native, Flutter, offline-first, push
│   ├── 28-fintech-insurance-systems.md  ← Fintech: payments, banking, ledger, insurance
│   ├── 29-healthcare-life-sciences.md   ← Healthcare: EHR, FHIR, HIPAA, clinical data
│   ├── 30-browser-engineering.md        ← Browser: rendering engine, DOM, JS engine, WebAssembly
│   ├── 31-compilers-language-design.md  ← Compilers: lexing, parsing, type systems, optimization
│   ├── 32-realtime-collaboration-systems.md ← Realtime: CRDTs, WebSocket, collaborative editing
│   ├── 33-search-recommendation-engines.md  ← Search: TF-IDF, BM25, vector search, recommendations
│   ├── 34-llm-ops-platform-engineering.md   ← LLM Ops: model serving, RAG, fine-tuning, prompt eng
│   ├── 35-computer-graphics-gpu.md          ← Graphics: rendering pipelines, shaders, GPU, WebGPU
│   ├── 36-api-integration-platforms.md      ← API: gateways, GraphQL federation, gRPC, webhooks
│   ├── 37-media-entertainment-social.md    ← Media: streaming, social feeds, moderation, messaging
│   ├── 38-marketplace-ecommerce.md         ← Marketplace: listings, escrow, trust/safety, logistics
│   ├── 39-education-learning-platforms.md  ← EdTech: LMS, adaptive learning, spaced repetition
│   ├── 40-formal-methods-verification.md   ← Formal: model checking, SAT/SMT, static analysis
│   └── 41-emerging-technologies.md         ← Emerging: Web3, edge, digital twins, AR/VR, green IT
│
├── design-manifesto.md               ← Design philosophy & coding preferences
├── ubuntu-diag-architecture.md       ← Example: system diagnostic tool architecture
├── designs.json                      ← Saved user designs (reference examples)
└── session-memory.json               ← Session & build history

dextrous-internal-system-design.txt  ← Reference: complete system design analysis (card game platform)

bible-reference/                      ← The Programming Bible (42 levels)
├── MASTER-INDEX.txt                  ← Full index of all 42 levels
├── 01-foundations/                   ← Level 1: Fundamentals
├── 02-games/                         ← Level 2: Games & Simple Apps
├── 03-desktop-apps/                  ← Level 3: Desktop Applications
├── 04-web-apps/                      ← Level 4: Web Applications
├── 05-systems-programming/           ← Level 5: Systems Programming
├── 06-os-kernel/                     ← Level 6: OS Kernel
├── 07-ai-ml/                         ← Level 7: AI/ML & LLM Guide
├── ...
└── 42-education-learning/            ← Level 42: Education Platforms

backend/knowledge/                    ← Learned patterns & model data
├── patterns.json                     ← Saved architecture patterns
├── rnn-model.json                    ← RNN model weights
└── auto-learn/                       ← Auto-learned interaction data
```

---

## 📋 Reference File Quick-Use Guide

| When the app builder needs to... | Reference file(s) to consult |
|---|---|
| **Understand what node types exist & how they generate code** | `01-node-architecture-reference.md` |
| **Pick a starting architecture template for a user request** | `02-app-type-templates.md` |
| **Generate clean, idiomatic code from a node design** | `03-code-generation-rules.md` |
| **Choose which language/framework to use for a node** | `04-technology-mapping.md` |
| **Apply proven design patterns to generated code** | `05-design-patterns.md` |
| **Design data flow between nodes** | `06-data-flow-patterns.md` |
| **Implement a specific node type in detail** | `07-node-implementation-guide.md` |
| **Write tests for generated code** | `08-testing-patterns.md` |
| **Deploy the generated app to production** | `09-deployment-templates.md` |
| **Set up CI/CD pipelines** | `10-cicd-configuration.md` |
| **Debug issues in generated code** | `11-debugging-strategies.md` |
| **Build a game (game loop, ECS, AI, netcode)** | `12-game-development-patterns.md` |
| **Build a Linux desktop application** | `13-desktop-application-architecture.md` |
| **Build a full-stack web application** | `14-web-application-architecture.md` |
| **Design database schema & queries** | `15-database-design-patterns.md` |
| **Understand memory, concurrency, compilers** | `16-systems-programming-guide.md` |
| **Secure the generated application** | `17-security-architecture-guide.md` |
| **Process media files (audio/video/images)** | `18-media-multimedia-processing.md` |
| **Integrate AI/ML models into an app** | `19-ai-ml-integration-guide.md` |
| **Add networking, WebRTC, or protocol handling** | `20-networking-communication-protocols.md` |
| **Build IoT/embedded device applications** | `21-iot-embedded-systems.md` |
| **Integrate with ERP, CRM, or enterprise systems** | `22-enterprise-systems-integration.md` |
| **Deploy to Kubernetes or cloud-native infra** | `23-cloud-native-infrastructure.md` |
| **Set up monitoring, alerting, and SRE practices** | `24-devops-sre-tooling.md` |
| **Build distributed systems with consensus & queues** | `25-distributed-systems.md` |
| **Design ETL pipelines and data warehouses** | `26-data-engineering-analytics.md` |
| **Build a mobile or cross-platform app** | `27-mobile-cross-platform.md` |
| **Integrate payment processing or banking APIs** | `28-fintech-insurance-systems.md` |
| **Build healthcare/EHR applications (HIPAA)** | `29-healthcare-life-sciences.md` |
| **Build LLM serving, RAG pipelines, or fine-tuning** | `34-llm-ops-platform-engineering.md` |
| **Render 3D graphics, write shaders, or use WebGPU** | `35-computer-graphics-gpu.md` |
| **Design API gateways, GraphQL federation, or gRPC** | `36-api-integration-platforms.md` |
| **Build video streaming, social feeds, or messaging** | `37-media-entertainment-social.md` |
| **Build a marketplace, escrow, or e-commerce app** | `38-marketplace-ecommerce.md` |
| **Build an LMS, adaptive learning, or spaced repetition** | `39-education-learning-platforms.md` |
| **Apply formal verification, SAT/SMT, or model checking** | `40-formal-methods-verification.md` |
| **Build with Web3, edge, digital twins, or AR/VR** | `41-emerging-technologies.md` |
| **Match the user's design philosophy** | `design-manifesto.md` |
| **Learn a deep technical concept (databases, networking, etc.)** | `bible-reference/`* |
| **See previously saved design examples** | `designs.json` |
| **Understand project conventions & preferences** | `design-manifesto.md` |
| **Learn from a complete system design analysis (Dextrous)** | `dextrous-internal-system-design.txt` |
| **Review previously learned architecture patterns** | `backend/knowledge/patterns.json` |

\* *Consult `bible-reference/MASTER-INDEX.txt` to find the specific Bible level needed*

---

## 🔗 Additional Knowledge Sources

- **`backend/knowledge/patterns.json`** — Previously saved architecture patterns from the auto-learn engine. Good for seeing what patterns have been successfully generated before.
- **`backend/knowledge/auto-learn/`** — Interaction logs from the learning engine. Can be used to understand user behavior patterns.
- **`dextrous-internal-system-design.txt`** — A complete third-party system design analysis (Dextrous card game platform). Excellent reference for how complex SaaS tools are architected.
- **`projects/`** — Generated HTML project examples (calculator, tictactoe, etc.). Working reference implementations.

## 🔗 Cross-Reference: Bible Levels by Topic

| Topic Area | Bible Level(s) | Library File |
|---|---|---|
| App fundamentals / architecture | 01 Foundations, 07 LLM Guide | `02-app-type-templates.md` |
| Web applications | 04 Web Apps | `02-app-type-templates.md` |
| Desktop / Linux apps | 03 Desktop Apps, 05 Systems | `02-app-type-templates.md` |
| Database design | 11 Database Internals | `06-data-flow-patterns.md` |
| Media / streaming | 40 Media & Entertainment | `02-app-type-templates.md` |
| AI / ML features | 10 Machine Learning, 37 AI/ML Ops | `04-technology-mapping.md` |
| Error handling | 01 Foundations, 19 Formal Methods | `03-code-generation-rules.md` |
| Security | 14 Cryptography & Security | `03-code-generation-rules.md` |
| Networking | 13 Deep Networking | `06-data-flow-patterns.md` |
| UI / Frontend | 04 Web Apps, 22 Browser Engineering | `07-node-implementation-guide.md` |
| Game development | 02 Games, 09 Game Engines | `12-game-development-patterns.md` |
| Desktop application development | 03 Desktop Apps | `13-desktop-application-architecture.md` |
| Systems programming | 05 Systems Programming, 06 OS Kernel | `16-systems-programming-guide.md` |
| Security architecture | 10 Security, 14 Cryptography | `17-security-architecture-guide.md` |
| Multimedia / digital content | 21 Digital Content Media | `18-media-multimedia-processing.md` |
| AI/ML integration | 07 AI/ML, 10 Machine Learning, 37 AI/ML Ops | `19-ai-ml-integration-guide.md` |
| Networking / protocols | 13 Networking Deep, 14 Protocols | `20-networking-communication-protocols.md` |
| IoT / embedded | 23 IoT Embedded Deep | `21-iot-embedded-systems.md` |
| Enterprise systems | 26 Enterprise Systems | `22-enterprise-systems-integration.md` |
| Cloud-native / containers | 17 Virtualization, 32 Cloud Native Infra | `23-cloud-native-infrastructure.md` |
| DevOps / SRE | 33 DevOps SRE Tooling, 12 DevOps | `24-devops-sre-tooling.md` |
| Distributed systems | 12 Distributed Systems | `25-distributed-systems.md` |
| Data engineering | 27 Data Engineering | `26-data-engineering-analytics.md` |
| Mobile / cross-platform | 31 Mobile Cross Platform | `27-mobile-cross-platform.md` |
| Fintech / insurance | 38 Fintech Insurance | `28-fintech-insurance-systems.md` |
| Healthcare / life sciences | 39 Healthcare Life Sciences | `29-healthcare-life-sciences.md` |
| Browser engineering | 22 Browser Engineering | `30-browser-engineering.md` |
| Compilers & language design | 11 Language Design, 15 Programming Languages | `31-compilers-language-design.md` |
| Realtime collaboration | 35 Realtime Collaboration | `32-realtime-collaboration-systems.md` |
| Search & recommendation | 36 Search Recs Personalization | `33-search-recommendation-engines.md` |
| LLM Ops & AI platforms | 37 AI/ML Platforms LLM Ops | `34-llm-ops-platform-engineering.md` |
| Computer graphics & GPU | 08 Computer Graphics, 16 Computer Architecture | `35-computer-graphics-gpu.md` |
| API integration | 34 API Integration Platforms | `36-api-integration-platforms.md` |
| Media & social platforms | 40 Media Entertainment Social | `37-media-entertainment-social.md` |
| Marketplace & e-commerce | 41 Marketplace Sharing Economy | `38-marketplace-ecommerce.md` |
| Education & learning | 42 Education Learning | `39-education-learning-platforms.md` |
| Formal methods | 19 Formal Methods Tools | `40-formal-methods-verification.md` |
| Emerging technologies | 29 Emerging Tech | `41-emerging-technologies.md` |
| Component manifest | — (cross-cutting) | `43-component-manifest.md` |
| **Three.js 3D scenes** | 08 Computer Graphics, 22 Browser Engineering | `44-threejs-scene-recipes.md` |

---

*Last updated: 2026-08-10 — 44 reference sheets total (00–41, 43, 44), plus the 42-level Bible curriculum*

### 📜 Bible Reference Integration

The **bible-reference/** directory contains 42 levels of deep technical reference (>300 files, 17MB).
The LLM app builder automatically loads Bible level overviews when generating code:

1. **Context-aware injection**: When you describe an app goal or node, the system automatically finds relevant Bible levels and injects their overview content into the LLM prompt.
2. **Node-type mapping**: Each node type (input, logic, database, ui, api) is mapped to the most relevant Bible levels for implementation guidance.
3. **Language mapping**: Each programming language is mapped to Bible levels for language-specific best practices.
4. **Full-text search**: The `/api/library/context` endpoint searches across ALL library files AND Bible indexes.
5. **Frontend browser**: Open the Reference Library panel in the app and switch to the "📜 Bible" tab to browse all 42 levels.

**How the Bible helps the LLM**:
- Deep technical dives for complex features (e.g., Bible level 06-databases for SQL engine design)
- Architecture patterns from proven system designs
- Implementation guidance in C, Python, Rust, C++, assembly, JS across all levels
- Cross-cutting concerns across all 42 levels

*To access Bible content programmatically, call `POST /api/library/context` with `{ searchText: "your topic" }`.*
