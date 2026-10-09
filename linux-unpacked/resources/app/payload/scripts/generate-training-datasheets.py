#!/usr/bin/env python3
"""
Generate Training Datasheets for MindSpace
==========================================
Creates comprehensive training datasheets from:
  1. All 807 designs in designs.json (one datasheet per category)
  2. 35+ specialized knowledge domains
  3. Auto-learn interaction data

Writes all datasheets to the MindSpace trainer directory for progressive training.

Usage:
  python3 scripts/generate-training-datasheets.py [--all] [--designs] [--specialized] [--count]
"""

import json, os, sys, time, re
from pathlib import Path

MINDSPACE_TRAINER = Path("/media/final-flash1/a47f2c6e-f5fa-4e60-bcea-95767738c074/MindSpace/trainer")
DESIGNS_FILE = Path("data/designs.json")
AUTO_LEARN_DIR = Path("backend/knowledge/auto-learn")

# Category mapping for designs
CATEGORY_MAP = {
    "01-fundamentals": "fundamentals", "02-games": "games", "03-desktop-apps": "desktop",
    "05-systems-programming": "systems", "06-databases": "database", "13-math": "mathematics",
    "20-specialized-computing": "specialized", "27-data-engineering": "data-engineering",
    "33-devops-sre-tooling": "devops", "36-search-recs-personalization": "search"
}

# 35+ specialized knowledge domains
SPECIALIZED_TOPICS = {
    "security": [
        ("Input Validation", "Validate and sanitize all user inputs: SQL injection, XSS, command injection, path traversal"),
        ("Authentication", "Implement OAuth2, JWT, session management, MFA, password hashing with bcrypt/argon2"),
        ("Authorization", "RBAC, ABAC, permission checking, ACLs, policy-based access control"),
        ("Encryption", "AES-256-GCM for data at rest, TLS 1.3 for transit, key management, PKI infrastructure"),
        ("CSRF Protection", "Anti-forgery tokens, SameSite cookies, origin checking, double-submit cookie pattern"),
        ("Secure Headers", "Content-Security-Policy, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy"),
        ("Rate Limiting", "Token bucket, sliding window, per-user/IP rate limiting, exponential backoff"),
        ("Audit Logging", "Structured audit trails, tamper-evident logs, log aggregation, SIEM integration"),
        ("Secret Management", "Vault, environment variables, encrypted config, rotation policies, service accounts"),
        ("Dependency Scanning", "SBOM generation, CVE monitoring, automated updates, supply chain security"),
        ("Container Security", "Image scanning, minimal base images, non-root users, seccomp profiles, AppArmor"),
        ("Network Security", "Zero-trust architecture, mTLS, network policies, egress filtering, WAF rules"),
    ],
    "database": [
        ("Schema Design", "Normalization (1NF-5NF), denormalization strategies, star/snowflake schemas, data types"),
        ("Query Optimization", "EXPLAIN plans, index selection, covering indexes, query rewriting, materialized views"),
        ("Transaction Management", "ACID properties, isolation levels, optimistic/pessimistic locking, two-phase commit"),
        ("Connection Pooling", "PgBouncer, HikariCP, max connections, pool sizing, connection health checks"),
        ("Backup and Recovery", "Full/differential/incremental backups, PITR, WAL archiving, restore testing"),
        ("Replication", "Streaming replication, logical replication, read replicas, failover, consistency models"),
        ("Sharding", "Horizontal partitioning, consistent hashing, range sharding, resharding strategies"),
        ("Indexing Strategies", "B-tree, Hash, GiST, GIN, BRIN indexes, composite indexes, partial indexes"),
        ("Full-Text Search", "GIN indexes, tsvector/tsquery, ranking, thesaurus, dictionary configuration"),
        ("Time-Series Data", "TimescaleDB hypertables, continuous aggregates, data retention, chunk management"),
        ("JSON/NoSQL Patterns", "JSONB indexing, path queries, document modeling, hybrid relational-document design"),
        ("Migration Strategies", "Zero-downtime migrations, expand-migrate-contract pattern, versioned schemas"),
    ],
    "performance": [
        ("Profiling", "CPU profiling, memory profiling, I/O profiling, flame graphs, tracing, perf tools"),
        ("Caching Strategies", "Multi-level cache, write-through, write-behind, cache invalidation, CDN, Redis patterns"),
        ("Load Testing", "k6, Locust, Artillery, ramp-up patterns, soak testing, spike testing, SLO validation"),
        ("Database Performance", "Query profiling, index tuning, connection pooling, read replicas, prepared statements"),
        ("Memory Management", "GC tuning, memory pools, object pooling, off-heap memory, memory-mapped files"),
        ("Async Processing", "Event loops, message queues, worker pools, backpressure, bulkheading pattern"),
        ("CDN and Edge Caching", "Reverse proxy caching, edge workers, cache-control headers, stale-while-revalidate"),
        ("Compression", "Gzip/Brotli, image optimization, WebP/AVIF, minification, tree-shaking, code splitting"),
        ("Lazy Loading", "Code splitting, dynamic imports, lazy initialization, virtual scrolling, pagination"),
        ("Connection Management", "Keepalive, HTTP/2 multiplexing, connection pooling, circuit breakers, retry logic"),
        ("Static Analysis", "Linting, type checking, dead code elimination, bundle analysis, dependency auditing"),
        ("Observability", "Metrics, traces, logs, OpenTelemetry, dashboards, alerting, SLO monitoring"),
    ],
    "architecture": [
        ("Microservices", "Service boundaries, Bounded Contexts, API gateways, service mesh, inter-service communication"),
        ("Event-Driven Architecture", "Event sourcing, CQRS, event buses, message brokers, outbox pattern, sagas"),
        ("Hexagonal Architecture", "Ports and adapters, dependency inversion, domain-driven design, repository pattern"),
        ("Clean Architecture", "Use cases, entities, interface adapters, frameworks as details, dependency rule"),
        ("SOLID Principles", "Single responsibility, Open-closed, Liskov substitution, Interface segregation, Dependency injection"),
        ("Design Patterns", "Factory, Builder, Strategy, Observer, Decorator, Proxy, Command, Template Method"),
        ("RESTful Design", "Resource modeling, HATEOAS, versioning, pagination, hypermedia, status codes"),
        ("GraphQL Design", "Schema-first, resolvers, DataLoader, subscriptions, federation, cost analysis"),
        ("API Gateway Pattern", "Rate limiting, auth, routing, aggregation, transformation, circuit breaking"),
        ("Backend-for-Frontend", "BFF pattern, per-client APIs, aggregation, device-specific optimization"),
        ("Saga Pattern", "Choreography vs orchestration, compensating transactions, rollback strategies"),
        ("Strangler Fig Pattern", "Incremental migration, feature toggles, proxy routing, parallel run, cut-over"),
    ],
    "frontend": [
        ("Component Architecture", "Atomic design, composition, compound components, render props, higher-order components"),
        ("State Management", "Redux Toolkit, Zustand, Jotai, Recoil, Context API, state machines, XState"),
        ("Performance Optimization", "Virtual DOM, memoization, lazy loading, code splitting, bundle optimization"),
        ("Responsive Design", "CSS Grid, Flexbox, media queries, container queries, mobile-first, fluid typography"),
        ("Accessibility", "ARIA attributes, keyboard navigation, screen reader support, focus management"),
        ("Testing Strategy", "Unit tests, integration tests, E2E tests, visual regression, accessibility testing"),
        ("Build Tooling", "Webpack, Vite, esbuild, Turbopack, SWC, module federation, code splitting config"),
        ("CSS Architecture", "CSS Modules, Tailwind, CSS-in-JS, design tokens, utility-first, BEM methodology"),
        ("Form Handling", "Validation, controlled/uncontrolled inputs, form libraries, error handling, multi-step forms"),
        ("Routing", "Client-side routing, nested routes, route guards, lazy loading routes, SSR compatibility"),
        ("Internationalization", "i18n libraries, locale management, RTL support, pluralization, date/number formatting"),
        ("Error Boundaries", "Error recovery, fallback UI, error logging, graceful degradation, retry logic"),
    ],
    "backend": [
        ("API Design", "RESTful resources, GraphQL schemas, gRPC services, versioning, OpenAPI/Swagger documentation"),
        ("Authentication", "Session-based auth, JWT tokens, OAuth2 flows, API keys, service-to-service auth"),
        ("File Processing", "Upload handling, streaming, chunked uploads, virus scanning, file type validation"),
        ("Background Jobs", "Job queues, cron scheduling, worker pools, retry logic, dead letter queues, job monitoring"),
        ("Data Validation", "Request validation, schema validation, business rules, idempotency keys, data integrity"),
        ("Error Handling", "Global error handlers, structured errors, error codes, retry policies, circuit breakers"),
        ("Logging", "Structured logging, log levels, correlation IDs, centralized logging, log rotation"),
        ("Middleware Pipeline", "Auth middleware, rate limiting, logging, compression, CORS, request ID, caching"),
        ("WebSocket Handling", "Connection management, pub/sub, broadcasting, reconnection, presence, rooms"),
        ("Health Checks", "Readiness probes, liveness probes, dependency checks, startup checks, status endpoints"),
        ("Graceful Shutdown", "Signal handling, draining connections, completing in-flight requests, cleanup resources"),
        ("Testing Patterns", "Unit testing, integration testing, contract testing, end-to-end testing, mock services"),
    ],
    "devops": [
        ("CI/CD Pipelines", "GitHub Actions, GitLab CI, Jenkins, build caching, parallel stages, deployment gates"),
        ("Container Orchestration", "Kubernetes, pod specs, deployments, services, ingress, configmaps, secrets"),
        ("Infrastructure as Code", "Terraform, Pulumi, CloudFormation, state management, modules, remote backends"),
        ("Monitoring and Alerting", "Prometheus, Grafana, alert rules, recording rules, service monitors, dashboards"),
        ("Log Aggregation", "ELK Stack, Loki, Fluentd, structured logging, log parsing, retention policies"),
        ("Service Mesh", "Istio, Linkerd, mTLS, traffic routing, fault injection, observability, circuit breaking"),
        ("GitOps", "ArgoCD, Flux, declarative config, sync policies, drift detection, rollback strategies"),
        ("Secrets Management", "HashiCorp Vault, AWS Secrets Manager, encryption, rotation, access policies"),
        ("Disaster Recovery", "Backup strategies, restore testing, multi-region, RTO/RPO, failover automation"),
        ("Security Scanning", "SAST, DAST, container scanning, dependency scanning, compliance checks, SBOM"),
        ("Cost Optimization", "Resource right-sizing, spot instances, auto-scaling, cost allocation, reserved instances"),
        ("Chaos Engineering", "Chaos Monkey, Gremlin, fault injection, steady-state hypothesis, blast radius"),
    ],
    "testing": [
        ("Unit Testing", "Test structure, mocking, stubbing, parameterized tests, code coverage, test naming"),
        ("Integration Testing", "Test containers, database testing, API testing, contract testing, wiremock"),
        ("End-to-End Testing", "Cypress, Playwright, Selenium, user flows, visual regression, cross-browser testing"),
        ("Performance Testing", "k6, Locust, JMeter, load profiles, assertions, thresholds, breakpoint testing"),
        ("Property-Based Testing", "Hypothesis, QuickCheck, invariant testing, random generation, shrinking"),
        ("Mutation Testing", "Mutmut, Stryker, test quality, surviving mutants, test strength analysis"),
        ("Test Fixtures", "Setup/teardown, factories, builders, test data generation, database seeding"),
        ("Mocking Strategies", "Mock objects, fakes, spies, stubs, dependency injection for testability"),
        ("BDD and TDD", "Given-when-then, behavior specifications, red-green-refactor, acceptance criteria"),
        ("Regression Testing", "Snapshot testing, visual regression, API diffing, golden files, smoke tests"),
        ("Test Parallelization", "Test splitting, parallel execution, isolated state, shared fixtures pattern"),
        ("Continuous Testing", "Test selection, failure categorization, flaky test detection, quarantine, auto-retry"),
    ],
    "data-science": [
        ("Feature Engineering", "Feature selection, encoding, scaling, extraction, generation, storage, serving"),
        ("Model Training", "Training loops, validation, hyperparameter tuning, early stopping, checkpointing"),
        ("Model Evaluation", "Metrics selection, cross-validation, confusion matrix, ROC curves, bias detection"),
        ("ML Pipeline", "Data ingestion, preprocessing, training, evaluation, deployment, monitoring, retraining"),
        ("Deep Learning", "CNN, RNN, LSTM, Transformer, attention mechanisms, transfer learning, fine-tuning"),
        ("NLP", "Tokenization, embeddings, BERT, GPT, sequence labeling, text classification, NER, sentiment"),
        ("Computer Vision", "Image classification, object detection, segmentation, GANs, data augmentation"),
        ("Recommendation Systems", "Collaborative filtering, content-based, hybrid, matrix factorization, deep recs"),
        ("Time Series", "ARIMA, Prophet, LSTMs, seasonality, trend decomposition, forecasting, anomaly detection"),
        ("Model Serving", "ONNX, TensorRT, Triton, model optimization, quantization, batching, A/B testing"),
        ("MLOps", "Experiment tracking, model registry, feature store, pipeline automation, model governance"),
        ("Explainability", "SHAP, LIME, feature importance, partial dependence, counterfactual explanations"),
    ],
    "ai-ml": [
        ("Large Language Models", "GPT, Claude, Llama, prompt engineering, RAG, fine-tuning, quantization, deployment"),
        ("Reinforcement Learning", "Q-learning, PPO, DQN, reward shaping, policy gradients, exploration strategies"),
        ("Generative AI", "GANs, diffusion models, stable diffusion, image generation, text-to-image, controlnets"),
        ("Transfer Learning", "Pre-trained models, domain adaptation, feature extraction, fine-tuning strategies"),
        ("Model Compression", "Pruning, quantization, distillation, low-rank factorization, efficient architectures"),
        ("Prompt Engineering", "Chain-of-thought, few-shot, system prompts, instruction tuning, prompt chaining"),
        ("Vector Databases", "Pinecone, Weaviate, Qdrant, Milvus, embeddings, similarity search, hybrid search"),
        ("Retrieval-Augmented Gen", "RAG architecture, document chunking, embedding retrieval, fusion, re-ranking"),
        ("Model Alignment", "RLHF, DPO, constitutional AI, safety training, bias mitigation, red teaming"),
        ("Multi-Modal Models", "CLIP, LLaVA, GPT-4V, vision-language, audio-language, multi-modal embeddings"),
        ("Agent Frameworks", "LangChain, AutoGPT, function calling, tool use, planning, memory, reflection"),
        ("Edge AI", "ONNX Runtime, TensorRT, CoreML, TFLite, model optimization for edge devices"),
    ],
    "cloud": [
        ("AWS Core Services", "EC2, S3, Lambda, VPC, IAM, RDS, DynamoDB, CloudFront, Route53, SQS, SNS"),
        ("Azure Services", "Azure VMs, Blob Storage, Functions, AKS, CosmosDB, Service Bus, DevOps pipelines"),
        ("GCP Services", "Compute Engine, Cloud Storage, Cloud Functions, GKE, BigQuery, Pub/Sub, Cloud Run"),
        ("Serverless Architecture", "Lambda functions, cold starts, event sources, step functions, API Gateway, Fargate"),
        ("Cloud Networking", "VPC design, subnets, security groups, NACLs, VPN, Direct Connect, Transit Gateway"),
        ("Cloud Storage", "Object storage, block storage, file storage, lifecycle policies, tiering, replication"),
        ("Cost Management", "Reserved instances, savings plans, spot instances, cost allocation, budget alerts"),
        ("Identity and Access Mgmt", "IAM policies, roles, service accounts, OIDC federation, permission boundaries"),
        ("Auto Scaling", "Launch templates, target tracking, scheduled scaling, predictive scaling, warm pools"),
        ("Disaster Recovery", "Multi-region, active-passive, pilot light, warm standby, RTO/RPO, failover testing"),
        ("Cloud Security", "Shared responsibility model, cloud SIEM, CASB, CSPM, CWPP, cloud compliance"),
        ("Multi-Cloud Strategy", "Abstraction layers, portability, provider-agnostic tools, cloud-agnostic patterns"),
    ],
    "mobile": [
        ("iOS Development", "Swift, SwiftUI, UIKit, CoreData, Combine, async/await, Xcode, TestFlight, App Store"),
        ("Android Development", "Kotlin, Jetpack Compose, Material Design, Room, Coroutines, Gradle, Play Store"),
        ("React Native", "Bridge architecture, Hermes, TurboModules, Fabric, navigation, native modules, Expo"),
        ("Flutter", "Widget tree, Dart, BLoC, Provider, Riverpod, CustomPaint, platform channels, Hot Reload"),
        ("Mobile UI/UX", "Material Design, Human Interface Guidelines, responsive layouts, gestures, haptics"),
        ("Offline-First", "Local storage, sync strategies, conflict resolution, background sync, offline queue"),
        ("Push Notifications", "APNs, FCM, notification payloads, rich notifications, silent pushes, grouping"),
        ("Deep Linking", "Universal links, app links, custom schemes, deferred deep linking, fallback URLs"),
        ("Mobile Security", "Code obfuscation, certificate pinning, secure storage, biometric auth, app sandbox"),
        ("App Performance", "Startup time, memory profiling, battery optimization, network optimization, rendering"),
        ("Cross-Platform", "Xamarin, Ionic, Cordova, Capacitor, Tauri, progressive web apps, hybrid strategies"),
        ("Mobile Testing", "UI testing, device farms, emulators, real device testing, beta testing, crash reporting"),
    ],
    "networking": [
        ("TCP/IP Stack", "TCP congestion control, three-way handshake, sliding window, IP routing, subnetting"),
        ("HTTP Protocol", "HTTP/1.1, HTTP/2 multiplexing, HTTP/3 QUIC, keepalive, pipelining, connection pooling"),
        ("DNS Resolution", "Recursive resolution, authoritative DNS, DNSSEC, DoH, DoT, CDN routing, latency"),
        ("Load Balancing", "Round-robin, least connections, IP hash, weighted distribution, health checks, sticky sessions"),
        ("WebSockets", "Upgrade handshake, framing, ping/pong, reconnection, backpressure, room management"),
        ("gRPC", "Protocol buffers, bidirectional streaming, flow control, deadlines, interceptors, health protocol"),
        ("Message Queues", "RabbitMQ, Kafka, SQS, pub/sub, consumer groups, partitioning, exactly-once delivery"),
        ("CDN Architecture", "Edge servers, origin pull, cache rules, purging, dynamic acceleration, WAF integration"),
        ("API Gateways", "Kong, Tyk, AWS API Gateway, rate limiting, authentication, request transformation"),
        ("Service Mesh", "Istio, Linkerd, Envoy, sidecar proxy, traffic management, observability, mTLS"),
        ("Network Security", "Firewalls, IDS/IPS, VPN, zero-trust, micro-segmentation, DDoS protection, WAF"),
        ("Observability", "Distributed tracing, metrics collection, logging, OpenTelemetry, service graphs"),
    ],
    "game-dev": [
        ("Game Loop", "Fixed timestep, variable timestep, update/render separation, interpolation, delta time"),
        ("Physics Engine", "Rigid body dynamics, collision detection, broad/narrow phase, constraints, joints"),
        ("Rendering Pipeline", "Vertex shader, fragment shader, compute shader, deferred rendering, PBR, HDR"),
        ("Entity Component System", "ECS architecture, archetypes, queries, systems, component storage, chunk allocation"),
        ("Animation System", "Skeletal animation, blend trees, inverse kinematics, pose blending, animation events"),
        ("AI for Games", "Behavior trees, state machines, pathfinding, navmesh, GOAP, utility AI, flocking"),
        ("Audio Engine", "Spatial audio, FMOD, Wwise, sound banks, mixing, DSP effects, occlusion, reverb"),
        ("Input Handling", "Action mapping, input buffering, rebinding, controller support, touch gestures, gyro"),
        ("Multiplayer Networking", "Client-server, peer-to-peer, rollback netcode, lag compensation, matchmaking"),
        ("Save Systems", "Serialization, binary formats, compression, cloud saves, cross-platform sync"),
        ("Procedural Generation", "Perlin noise, wave function collapse, L-systems, dungeon generation, terrain generation"),
        ("Optimization", "Draw call batching, LODs, occlusion culling, object pooling, memory budgeting"),
    ],
    "ui-ux": [
        ("Design Systems", "Design tokens, component libraries, Figma/Sketch integration, documentation, versioning"),
        ("Color Theory", "Color palettes, accessibility contrast, dark mode, semantic colors, brand guidelines"),
        ("Typography", "Type scale, font pairing, readability, line height, web fonts, variable fonts, kerning"),
        ("Layout Systems", "CSS Grid, Flexbox, auto layout, responsive breakpoints, spacing scale, containers"),
        ("Interaction Design", "Micro-interactions, transitions, animations, gesture recognition, feedback loops"),
        ("Information Architecture", "Navigation patterns, content hierarchy, search, filtering, categorization, sitemaps"),
        ("Accessibility", "WCAG 2.1, ARIA, screen readers, keyboard navigation, focus management, color contrast"),
        ("Prototyping", "Figma prototypes, interactive mockups, user flows, usability testing, iterations"),
        ("User Research", "User interviews, surveys, A/B testing, analytics, heatmaps, session recordings"),
        ("Design Tokens", "Color, spacing, typography, shadow, breakpoint tokens, platform-specific overrides"),
        ("Motion Design", "Easing curves, duration, stagger, shared element transitions, parallax, Lottie"),
        ("Data Visualization", "Charts, graphs, dashboards, D3.js, chart libraries, accessibility in data viz"),
    ],
    "api": [
        ("RESTful Design", "Resource modeling, URL structure, HTTP methods, status codes, hypermedia, versioning"),
        ("GraphQL", "Schema definition, resolvers, queries, mutations, subscriptions, DataLoader, federation"),
        ("gRPC", "Service definitions, protocol buffers, streaming, interceptors, deadlines, error handling"),
        ("OpenAPI/Swagger", "Specification, code generation, documentation, validation, mocking, client SDKs"),
        ("API Versioning", "URI versioning, header versioning, content negotiation, backward compatibility"),
        ("Authentication", "API keys, JWT, OAuth2, mTLS, HMAC, basic auth, rate limiting per token"),
        ("Rate Limiting", "Token bucket, sliding window, concurrent requests, quota management, headers"),
        ("Pagination", "Cursor-based, offset-based, keyset pagination, page size, total count, infinite scroll"),
        ("Error Handling", "Error codes, error responses, retry-after, idempotency, problem details RFC"),
        ("Webhooks", "Event delivery, retry policies, signatures, idempotency keys, payload verification"),
        ("API Testing", "Integration tests, contract tests, Postman, Newman, mock servers, schema validation"),
        ("API Documentation", "OpenAPI, ReadMe, developer portals, changelogs, SDK generation, quickstart guides"),
    ],
    "streaming": [
        ("Real-Time Data", "Kafka, Pulsar, NATS, event streaming, consumer groups, partitioning, offsets"),
        ("Stream Processing", "Flink, Spark Streaming, Beam, watermarks, event time, exactly-once, state management"),
        ("Video Streaming", "HLS, DASH, WebRTC, transcoding, adaptive bitrate, low-latency streaming"),
        ("Audio Streaming", "Icecast, SHOUTcast, Opus, AAC, real-time audio, jitter buffer, WebAudio API"),
        ("Change Data Capture", "Debezium, Kafka Connect, CDC pipelines, schema evolution, snapshotting"),
        ("Event Sourcing", "Event store, aggregate reconstruction, snapshots, event versioning, projections"),
        ("CQRS", "Command model, query model, separate read/write stores, eventual consistency, materialized views"),
        ("Streaming Databases", "Materialize, RisingWave, ksqlDB, continuous queries, materialized views"),
        ("Realtime Analytics", "HyperLogLog, t-digest, sliding windows, top-N, anomaly detection, dashboards"),
        ("Pub/Sub Systems", "Redis Pub/Sub, MQTT, AMQP, fan-out, routing keys, topic hierarchies, subscriptions"),
        ("Low-Latency Networks", "UDP, QUIC, WebRTC data channels, real-time protocols, jitter, latency budgets"),
        ("Streaming ETL", "Streaming ingestion, transformations, enrichment, joins, windowed aggregations"),
    ],
    "robotics": [
        ("ROS Architecture", "Nodes, topics, services, actions, parameters, launch files, ROS 2 vs ROS 1"),
        ("Sensor Fusion", "Kalman filters, particle filters, IMU, GPS, LIDAR, camera fusion, sensor models"),
        ("SLAM", "Visual SLAM, LIDAR SLAM, loop closure, graph optimization, feature extraction"),
        ("Motion Planning", "RRT, A*, PRM, trajectory optimization, collision avoidance, potential fields"),
        ("Control Systems", "PID controllers, model predictive control, LQR, state feedback, observers"),
        ("Computer Vision", "Object detection, depth estimation, visual odometry, AR tag detection, stereo vision"),
        ("Manipulation", "Inverse kinematics, grasp planning, force control, compliant motion, trajectory planning"),
        ("Localization", "Monte Carlo localization, AMCL, adaptive localization, Markov localization"),
        ("Robot Navigation", "Global planning, local planning, costmaps, recovery behaviors, dynamic obstacles"),
        ("Embedded Systems", "Microcontrollers, real-time constraints, sensor drivers, actuator control, RTOS"),
        ("Human-Robot Interaction", "Speech interfaces, gesture recognition, safety, collaborative robotics"),
        ("Simulation", "Gazebo, Unity, MuJoCo, hardware-in-the-loop, sensor simulation, digital twins"),
    ],
    "blockchain": [
        ("Consensus Mechanisms", "Proof of Work, Proof of Stake, PBFT, Raft, DPoS, finality, fork choice rules"),
        ("Smart Contracts", "Solidity, Vyper, Rust, gas optimization, security patterns, upgradeability"),
        ("DeFi", "AMMs, liquidity pools, lending protocols, yield farming, stablecoins, oracles"),
        ("Layer 2", "Rollups, state channels, plasma, validium, fraud proofs, ZK proofs, data availability"),
        ("Token Standards", "ERC-20, ERC-721, ERC-1155, tokenomics, vesting, bonding curves"),
        ("Web3 Architecture", "Ethereum, Solana, Polkadot, Cosmos, cross-chain bridges, IBC protocol"),
        ("Wallets", "HD wallets, EIP-1193, WalletConnect, account abstraction, multi-sig, key management"),
        ("Oracles", "Chainlink, price feeds, randomness, data verification, decentralized oracles"),
        ("Zero-Knowledge Proofs", "ZK-SNARKs, ZK-STARKs, zk-rollups, circom, proof generation/verification"),
        ("NFT Standards", "ERC-721, ERC-1155, metadata, IPFS, royalties, marketplaces, fractionalization"),
        ("DAO Architecture", "Governance tokens, voting, treasury management, proposals, delegation"),
        ("Cryptography", "Elliptic curve, hash functions, digital signatures, Merkle trees, Pedersen commitments"),
    ],
    "embedded": [
        ("Microcontroller Arch", "ARM Cortex-M, RISC-V, AVR, memory-mapped I/O, interrupts, DMA, watchdog timers"),
        ("Real-Time OS", "FreeRTOS, Zephyr, RT-Thread, task scheduling, semaphores, mutexes, queues"),
        ("Device Drivers", "Character devices, block devices, interrupt handlers, SPI, I2C, UART, GPIO"),
        ("Memory Management", "Flash memory, RAM optimization, stack/heap, memory-mapped files, EEPROM"),
        ("Firmware Updates", "OTA updates, bootloaders, firmware signing, rollback, delta updates"),
        ("Power Management", "Sleep modes, clock gating, dynamic voltage scaling, battery optimization"),
        ("Bare Metal Programming", "Startup code, linker scripts, interrupt vectors, register manipulation"),
        ("Sensor Interfacing", "ADC, DAC, I2C sensors, SPI sensors, PWM, timing, filtering, calibration"),
        ("Communication Protocols", "CAN bus, Modbus, MQTT, BLE, Zigbee, LoRaWAN, Thread, Matter"),
        ("Safety-Critical Systems", "MISRA C, ISO 26262, DO-178C, fault tolerance, redundancy, watchdog"),
        ("Debugging Tools", "JTAG, SWD, logic analyzers, oscilloscopes, GDB, profiling, tracing"),
        ("Digital Signal Processing", "Filters, FFT, sample rate conversion, fixed-point arithmetic, audio processing"),
    ],
    "quantum": [
        ("Quantum Gates", "Hadamard, Pauli, CNOT, Toffoli, phase gates, unitary operations, gate decomposition"),
        ("Quantum Algorithms", "Shor's algorithm, Grover's search, QFT, quantum phase estimation, HHL"),
        ("Quantum Error Correction", "Surface codes, Shor codes, stabilizer formalism, fault tolerance, syndrome measurement"),
        ("Quantum Computing HW", "Superconducting qubits, trapped ions, photonic quantum computing, topological qubits"),
        ("Quantum Machine Learning", "Quantum neural networks, QSVM, quantum kernel methods, variational circuits"),
        ("QKD and Cryptography", "BB84 protocol, E91, quantum key distribution, post-quantum cryptography"),
        ("Quantum Simulation", "Hamiltonian simulation, variational quantum eigensolver, quantum chemistry"),
        ("Quantum Programming", "Qiskit, Cirq, Q#, PennyLane, quantum circuits, noise models, transpilation"),
        ("Adiabatic Computing", "Quantum annealing, D-Wave, Ising models, QUBO, combinatorial optimization"),
        ("Entanglement", "Bell states, GHZ states, entanglement swapping, teleportation, dense coding"),
        ("Quantum Supremacy", "Random circuit sampling, boson sampling, computational advantage benchmarks"),
        ("Noise and Decoherence", "T1/T2 times, dephasing, amplitude damping, error mitigation techniques"),
    ],
    "graphics": [
        ("Rendering Pipeline", "Vertex processing, rasterization, fragment shading, compute shaders, GPU architecture"),
        ("Ray Tracing", "BVH, path tracing, Monte Carlo integration, importance sampling, denoising"),
        ("Shader Programming", "HLSL, GLSL, SPIR-V, compute shaders, geometry shaders, tessellation"),
        ("3D Mathematics", "Matrices, quaternions, transformations, projection, intersection tests"),
        ("Lighting Models", "Phong, Blinn-Phong, PBR, GGX, Fresnel, image-based lighting, ambient occlusion"),
        ("GPU Architecture", "CUDA cores, tensor cores, RT cores, memory hierarchy, warp scheduling"),
        ("Textures and Materials", "UV mapping, mipmapping, normal maps, displacement maps, PBR materials"),
        ("Post-Processing", "Bloom, HDR tone mapping, motion blur, depth of field, color grading, anti-aliasing"),
        ("Animation", "Skinning, blend shapes, morph targets, bone hierarchy, GPU skinning, animation blending"),
        ("Compute on GPU", "CUDA, OpenCL, Vulkan compute, particle systems, image processing, physics"),
        ("Vulkan/Metal/DirectX", "Command buffers, render passes, descriptor sets, synchronization, pipelines"),
        ("Procedural Generation", "Noise algorithms, geometry generation, L-systems, fractals, terrain synthesis"),
    ],
    "audio": [
        ("Digital Audio", "Sampling theory, PCM, bit depth, sample rate, aliasing, quantization, dithering"),
        ("Audio DSP", "FIR filters, IIR filters, convolution, FFT, spectral processing, phase vocoder"),
        ("Sound Synthesis", "Subtractive, additive, FM synthesis, wavetable, granular, physical modeling"),
        ("Audio Codecs", "MP3, AAC, Opus, FLAC, Vorbis, psychoacoustic models, compression ratios"),
        ("Spatial Audio", "HRTF, binaural rendering, Ambisonics, object-based audio, Dolby Atmos"),
        ("Music Information Retrieval", "Pitch detection, onset detection, beat tracking, chroma features, MFCC"),
        ("Audio Programming", "PortAudio, JACK, ASIO, CoreAudio, WASAPI, low-latency audio, ring buffers"),
        ("MIDI Protocol", "MIDI messages, SysEx, MIDI 2.0, CC parameters, clock sync, MIDI files"),
        ("Voice Processing", "VAD, pitch shifting, time stretching, formant shifting, voice conversion"),
        ("Noise Reduction", "Spectral subtraction, Wiener filter, RNNoise, adaptive filtering, gate"),
        ("Audio Plugins", "VST3, AU, AAX, LV2, plugin architecture, parameter smoothing, preset management"),
        ("Game Audio", "FMOD, Wwise, sound banks, event system, dynamic mixing, occlusion, reverb zones"),
    ],
    "iot": [
        ("IoT Architecture", "Device layer, edge gateway, cloud backend, communication protocols, data pipeline"),
        ("MQTT Protocol", "Pub/sub, QoS levels, retained messages, last will, topics, MQTT 5.0 features"),
        ("CoAP Protocol", "REST for constrained devices, observe pattern, block-wise transfer, DTLS security"),
        ("Edge Computing", "Edge gateways, local processing, edge analytics, firmware management, offline operation"),
        ("Sensor Networks", "Mesh networking, Zigbee, Thread, BLE mesh, 6LoWPAN, routing, sleep scheduling"),
        ("Device Management", "Provisioning, OTA updates, device registration, remote monitoring, decommissioning"),
        ("LPWAN Technologies", "LoRaWAN, NB-IoT, LTE-M, Sigfox, range vs bandwidth, battery life"),
        ("IoT Security", "Device identity, secure boot, hardware root of trust, TLS, certificate management"),
        ("Protocol Gateways", "Protocol translation, MQTT to HTTP, OPC-UA, Modbus TCP, BACnet"),
        ("Digital Twins", "Asset modeling, twin synchronization, simulation, predictive maintenance"),
        ("Time-Series IoT Data", "InfluxDB, TimescaleDB, data retention, downsampling, continuous queries"),
        ("IoT Dashboards", "Real-time monitoring, Grafana, data visualization, alerting, historical analysis"),
    ],
    "edge": [
        ("Edge Architecture", "Edge nodes, fog computing, cloud edge, local processing, data gravity"),
        ("Edge Inference", "ONNX Runtime, TensorRT, OpenVINO, CoreML, TFLite, model optimization"),
        ("WebAssembly at Edge", "WASI, WasmEdge, Fastly Compute, Cloudflare Workers, serverless edge"),
        ("CDN Edge Computing", "Cloudflare Workers, Fastly, Vercel Edge, Lambda@Edge, edge KV stores"),
        ("Edge Storage", "Local databases, SQLite, LevelDB, RocksDB, edge caching, conflict resolution"),
        ("Offline-First Edge", "Local-first, CRDTs, sync protocols, conflict-free data types, P2P sync"),
        ("Edge Security", "TPM, secure enclave, measured boot, attestation, hardware security module"),
        ("Latency Optimization", "Edge caching, precomputation, speculative execution, warm starts"),
        ("Edge ML", "TinyML, TensorFlow Micro, embedded ML, model distillation, on-device learning"),
        ("IoT Edge Gateway", "Protocol bridging, data aggregation, filtering, local rules engine"),
        ("Edge Observability", "Distributed tracing, metrics collection, log forwarding, health checks"),
        ("Edge Networking", "5G MEC, private LTE, local breakout, network slicing, ultra-low latency"),
    ],
    "realtime": [
        ("Realtime Architecture", "Event-driven, pub/sub, websockets, SSE, polling, long-polling tradeoffs"),
        ("WebSocket Servers", "uWebSockets, ws, Socket.IO, connection management, broadcasting, rooms"),
        ("Server-Sent Events", "EventSource API, auto-reconnect, event IDs, custom events, keepalive"),
        ("WebRTC", "ICE/STUN/TURN, peer connection, data channels, media streams, signaling"),
        ("Distributed Realtime", "Ably, Pusher, Supabase Realtime, Liveblocks, CRDTs, presence"),
        ("Operational Transforms", "OT, conflict resolution, collaboration, undo/redo, version vectors"),
        ("Conflict-Free Replicated", "CRDTs, LWW-Register, GCounter, PNCounter, OR-Set, delta-state"),
        ("Realtime Databases", "Firebase RTDB, Supabase Realtime, RethinkDB, changefeeds, subscriptions"),
        ("Realtime Analytics", "Streaming aggregation, sliding windows, top-K, anomaly detection, alerts"),
        ("Collaboration", "Shared cursors, live cursors, presence, selection sync, document sync"),
        ("Live Streaming", "HLS, DASH, WebRTC broadcast, SRT, latency, adaptive bitrate, simulcast"),
        ("Realtime ML", "Online learning, streaming features, real-time inference, model updates"),
    ],
    "analytics": [
        ("Data Warehousing", "Snowflake, BigQuery, Redshift, Databricks, lakehouse architecture, star schemas"),
        ("OLAP vs OLTP", "Columnar storage, compression, vectorized execution, MPP architecture, materialized views"),
        ("Data Modeling", "Dimensional modeling, Kimball, Inmon, data vault, slowly changing dimensions"),
        ("BI Tools", "Tableau, Looker, PowerBI, Metabase, Superset, embedded analytics, dashboards"),
        ("ETL/ELT Pipelines", "dbt, Airflow, Fivetran, Dagster, data transformation, incremental loading"),
        ("Metrics and KPIs", "Vanity vs actionable metrics, North Star metric, cohort analysis, funnel analysis"),
        ("Cohort Analysis", "Retention analysis, user cohorts, time-based cohorts, behavioral cohorts"),
        ("A/B Testing", "Hypothesis testing, statistical significance, sample size, MVT, experimentation platforms"),
        ("Customer Analytics", "LTV, churn prediction, segmentation, RFM analysis, behavioral scoring"),
        ("Product Analytics", "Mixpanel, Amplitude, Heap, event tracking, funnels, retention, stickiness"),
        ("Data Governance", "Data cataloging, lineage, quality, privacy, access control, compliance"),
        ("Statistical Analysis", "Descriptive statistics, inference, regression, correlation, hypothesis testing"),
    ],
}

def safe_fn(name):
    s = name.lower().replace(' ','-').replace('/','-').replace('\\','-')
    s = re.sub(r'[^a-z0-9-]','',s)
    s = re.sub(r'-+','-',s).strip('-')
    return s[:60]

def generate_from_designs():
    """Generate category-based training datasheets from all designs."""
    if not DESIGNS_FILE.exists():
        print(f"  Designs file not found: {DESIGNS_FILE}")
        return 0

    with open(DESIGNS_FILE) as f:
        designs = json.load(f)

    MINDSPACE_TRAINER.mkdir(parents=True, exist_ok=True)

    # Group designs by their bible category
    cat_designs = {}
    for d in designs:
        tags = d.get("tags", [])
        cat = "general"
        for t in tags:
            t_lower = t.lower()
            for prefix, name in CATEGORY_MAP.items():
                if name in t_lower or prefix in t_lower:
                    cat = name
                    break
            if cat != "general":
                break
        cat_designs.setdefault(cat, []).append(d)

    total = 0
    for cat, cat_list in cat_designs.items():
        filename = f"datasheet-designs-{cat}.jsonl"
        filepath = MINDSPACE_TRAINER / filename

        with open(filepath, 'w') as out:
            count = 0
            for d in cat_list:
                name = d.get("name", "Design")
                goal = d.get("goal", "")
                purpose = d.get("purpose", "")
                nodes = d.get("nodes", [])
                node_text = "\n".join([f"- {n.get('label','Node')} ({n.get('type','logic')}): {n.get('description','')}" for n in nodes[:5]])
                entry = {
                    "text": f"Design: {name}\nGoal: {goal}\nPurpose: {purpose}\n\nNodes:\n{node_text}\n\nThis {cat} design implements {name.lower()} with {len(nodes)} nodes for the Visual AI Architect system.",
                    "source": f"designs-{cat}",
                    "title": name,
                    "language": "mixed",
                    "tags": [cat, "design", "architecture"] + d.get("tags", [])[:3],
                    "timestamp": d.get("createdAt", time.strftime("%Y-%m-%dT%H:%M:%S.000Z")),
                }
                out.write(json.dumps(entry) + "\n")
                count += 1
            total += count
        print(f"  {filename}: {count} entries")
    return total

def generate_specialized():
    """Generate training datasheets for all specialized knowledge domains."""
    MINDSPACE_TRAINER.mkdir(parents=True, exist_ok=True)
    total = 0

    for domain, topics in SPECIALIZED_TOPICS.items():
        filename = f"datasheet-{domain}.jsonl"
        filepath = MINDSPACE_TRAINER / filename

        with open(filepath, 'w') as out:
            count = 0
            for title, content in topics:
                entry = {
                    "text": f"{title}: {content}\n\nBest practices and implementation patterns for {title.lower()} in software engineering. This covers key concepts, common pitfalls, and production-ready approaches for integrating {title.lower()} into modern applications.",
                    "source": f"knowledge-{domain}",
                    "title": title,
                    "language": "mixed",
                    "tags": [domain, "knowledge", "best-practice", safe_fn(title)],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                }
                out.write(json.dumps(entry) + "\n")
                count += 1
            total += count
        print(f"  {filename}: {count} entries")

    return total

def generate_from_auto_learn():
    """Consolidate auto-learn interactions into a training datasheet."""
    if not AUTO_LEARN_DIR.exists():
        print(f"  Auto-learn directory not found: {AUTO_LEARN_DIR}")
        return 0

    MINDSPACE_TRAINER.mkdir(parents=True, exist_ok=True)
    filepath = MINDSPACE_TRAINER / "datasheet-auto-learn.jsonl"

    total_lines = 0
    with open(filepath, 'w') as out:
        for f in sorted(AUTO_LEARN_DIR.glob("interactions-*.jsonl")):
            with open(f) as inf:
                for line in inf:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)  # validate
                        out.write(line + "\n")
                        total_lines += 1
                    except json.JSONDecodeError:
                        pass

    print(f"  datasheet-auto-learn.jsonl: {total_lines} entries")
    return total_lines

def count_existing():
    """Count existing datasheets."""
    MINDSPACE_TRAINER.mkdir(parents=True, exist_ok=True)
    total = 0
    files = sorted(MINDSPACE_TRAINER.glob("datasheet-*.jsonl"))
    for f in files:
        lines = sum(1 for _ in open(f) if _.strip())
        print(f"  {f.name}: {lines} lines")
        total += lines
    print(f"\n  Total: {total} lines across {len(files)} files")
    return total

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate MindSpace training datasheets")
    parser.add_argument("--all", action="store_true", help="Generate all datasheets")
    parser.add_argument("--designs", action="store_true", help="Generate from designs.json")
    parser.add_argument("--specialized", action="store_true", help="Generate specialized knowledge datasheets")
    parser.add_argument("--auto-learn", action="store_true", help="Generate from auto-learn data")
    parser.add_argument("--count", action="store_true", help="Count existing datasheets")
    args = parser.parse_args()

    if args.count:
        print("Existing datasheets:")
        count_existing()
        sys.exit(0)

    do_all = args.all or not (args.designs or args.specialized or args.auto_learn)

    print(f"MindSpace trainer: {MINDSPACE_TRAINER}\n")

    total = 0

    if do_all or args.designs:
        print("Generating design-based training datasheets...")
        n = generate_from_designs()
        print(f"  -> {n} total design entries\n")
        total += n

    if do_all or args.specialized:
        print("Generating specialized knowledge datasheets...")
        n = generate_specialized()
        print(f"  -> {n} total specialized entries\n")
        total += n

    if do_all or args.auto_learn:
        print("Generating auto-learn datasheet...")
        n = generate_from_auto_learn()
        print(f"  -> {n} total auto-learn entries\n")
        total += n

    print("=" * 50)
    print(f"Generated {total} total training entries")

    ds_count = len(list(MINDSPACE_TRAINER.glob("datasheet-*.jsonl")))
    total_lines = sum(1 for f in MINDSPACE_TRAINER.glob("datasheet-*.jsonl") for _ in open(f) if _.strip())
    print(f"   Datasheets: {ds_count}")
    print(f"   Total lines: {total_lines}")

if __name__ == "__main__":
    main()
