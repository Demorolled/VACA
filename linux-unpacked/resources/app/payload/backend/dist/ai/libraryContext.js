//
// Reference Library & Bible Context Service
// ==========================================
//
// Loads and caches:
//   1. Library reference files (data/library/*.md) — patterns, templates, rules
//   2. Bible reference indexes (bible-reference/*/00-index.*) — deep technical guides
//   3. Bible MASTER-INDEX.txt — the full 42-level curriculum overview
//
// Provides context injection methods so every architecture plan, code generation
// step, and suggestion can reference both sets of knowledge.
//
// Mirrors the pattern used by manifesto.ts for caching and prompt injection.
import * as fs from 'fs';
import * as path from 'path';
import { semanticRetrieve } from './semanticRetrieval.js';
import { ragRetrieveBibleLevels, buildBlueprintRequirements } from './ragIndex.js';
import { denseEmbedQuery } from './denseEmbedding.js';
import { denseRetrieveSheets, denseRetrieveBibleLevels, denseBuildBlueprintRequirements, } from './denseRetrieval.js';
// ─── Paths ────────────────────────────────────────────────────────────────
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const LIBRARY_DIR = path.join(PROJECT_ROOT, 'data', 'library');
const BIBLE_DIR = path.join(PROJECT_ROOT, 'bible-reference');
const WIKI_PATH = path.join(PROJECT_ROOT, 'modelVeronice.txt');
const KNOWLEDGE_PATH = path.join(PROJECT_ROOT, 'data', 'VACA-MASTER-KNOWLEDGE.md');
let cachedLibraryFiles = null;
let cachedBibleFiles = null;
let cachedMasterIndex = null;
let lastLoadTime = 0;
const CACHE_TTL_MS = 30_000; // Re-read from disk every 30s
// ─── Library file metadata ────────────────────────────────────────────────
const FILE_TOPICS = {
    '00-reference-index.md': ['index', 'master', 'overview', 'reference'],
    '01-node-architecture-reference.md': ['node', 'architecture', 'type', 'input', 'output', 'logic', 'database', 'ui', 'api'],
    '02-app-type-templates.md': ['template', 'app', 'cli', 'web', 'desktop', 'api', 'media', 'system', 'data', 'pipeline'],
    '03-code-generation-rules.md': ['code', 'generation', 'rules', 'naming', 'style', 'error', 'security', 'quality'],
    '04-technology-mapping.md': ['technology', 'language', 'framework', 'database', 'selection', 'stack'],
    '05-design-patterns.md': ['design', 'pattern', 'architecture', 'mvc', 'event', 'pipeline', 'strategy'],
    '06-data-flow-patterns.md': ['data', 'flow', 'stream', 'pipeline', 'reactive', 'batch'],
    '07-node-implementation-guide.md': ['implementation', 'generate', 'codegen', 'node', 'convert'],
    '08-testing-patterns.md': ['test', 'testing', 'unit', 'integration', 'e2e', 'mock', 'coverage'],
    '09-deployment-templates.md': ['deploy', 'deployment', 'systemd', 'docker', 'packaging', 'deb', 'fhs'],
    '10-cicd-configuration.md': ['ci', 'cd', 'cicd', 'github', 'actions', 'pipeline', 'automation'],
    '11-debugging-strategies.md': ['debug', 'logging', 'error', 'diagnostic', 'troubleshoot'],
    '12-game-development-patterns.md': ['game', 'game loop', 'ecs', 'entity component', 'collision', 'ai', 'netcode', 'game development'],
    '13-desktop-application-architecture.md': ['desktop app', 'event loop', 'widget', 'linux desktop', 'gui', 'windowing', 'fhs'],
    '14-web-application-architecture.md': ['web app', 'frontend', 'backend', 'fullstack', 'rest', 'api design', 'middleware', 'http'],
    '15-database-design-patterns.md': ['database design', 'indexing', 'btree', 'query optimization', 'schema', 'migration', 'sql'],
    '16-systems-programming-guide.md': ['systems', 'memory management', 'concurrency', 'compiler', 'performance', 'profiling'],
    '17-security-architecture-guide.md': ['security', 'threat modeling', 'authentication', 'xss', 'sql injection', 'owasp', 'auth'],
    '18-media-multimedia-processing.md': ['media', 'audio', 'video', 'streaming', 'codec', 'ffmpeg', 'image processing'],
    '19-ai-ml-integration-guide.md': ['ai', 'machine learning', 'model serving', 'llm', 'training', 'onnx', 'embedding', 'mlops'],
    '20-networking-communication-protocols.md': ['networking', 'tcp', 'udp', 'http2', 'http3', 'quic', 'websocket', 'webrtc'],
    '21-iot-embedded-systems.md': ['iot', 'embedded', 'mqtt', 'rtos', 'sensor', 'edge computing', 'firmware'],
    '22-enterprise-systems-integration.md': ['enterprise', 'erp', 'crm', 'scm', 'integration', 'api gateway', 'event bus'],
    '23-cloud-native-infrastructure.md': ['cloud native', 'kubernetes', 'container', 'docker', 'gitops', 'service mesh', 'terraform'],
    '24-devops-sre-tooling.md': ['devops', 'sre', 'monitoring', 'prometheus', 'alerting', 'observability', 'incident response'],
    '25-distributed-systems.md': ['distributed systems', 'consensus', 'raft', 'paxos', 'message queue', 'kafka', 'cap theorem'],
    '26-data-engineering-analytics.md': ['data engineering', 'etl', 'airflow', 'stream processing', 'data warehouse', 'analytics'],
    '27-mobile-cross-platform.md': ['mobile', 'react native', 'flutter', 'ios', 'android', 'cross platform', 'push notification'],
    '28-fintech-insurance-systems.md': ['fintech', 'payment', 'banking', 'ledger', 'insurance', 'compliance', 'pci dss'],
    '29-healthcare-life-sciences.md': ['healthcare', 'ehr', 'fhir', 'hipaa', 'dicom', 'clinical', 'medical'],
    '30-browser-engineering.md': ['browser', 'rendering engine', 'dom', 'javascript engine', 'webassembly', 'compositing', 'css'],
    '31-compilers-language-design.md': ['compiler', 'language design', 'parser', 'lexer', 'type system', 'optimization', 'codegen'],
    '32-realtime-collaboration-systems.md': ['realtime', 'collaboration', 'crdt', 'websocket', 'operational transform', 'sync'],
    '33-search-recommendation-engines.md': ['search', 'recommendation', 'information retrieval', 'bm25', 'vector search', 'personalization'],
    '34-llm-ops-platform-engineering.md': ['llm ops', 'model serving', 'rag', 'retrieval augmented generation', 'fine tuning', 'lora', 'prompt engineering', 'evaluation', 'ai platform'],
    '35-computer-graphics-gpu.md': ['computer graphics', 'gpu', 'rendering', 'shader', 'webgpu', 'opengl', 'vulkan', 'visualization', 'rasterization'],
    '36-api-integration-platforms.md': ['api integration', 'api gateway', 'graphql federation', 'grpc', 'protobuf', 'webhook', 'ipaas', 'event bus'],
    '37-media-entertainment-social.md': ['media platform', 'video streaming', 'social feed', 'content moderation', 'messaging', 'chat', 'creator economy'],
    '38-marketplace-ecommerce.md': ['marketplace', 'ecommerce', 'two sided marketplace', 'escrow', 'payment', 'listing', 'inventory', 'trust safety'],
    '39-education-learning-platforms.md': ['education', 'learning management', 'lms', 'edtech', 'adaptive learning', 'spaced repetition', 'gamification', 'virtual classroom'],
    '40-formal-methods-verification.md': ['formal methods', 'verification', 'model checking', 'tla plus', 'sat solver', 'smt solver', 'static analysis', 'property based testing'],
    '41-emerging-technologies.md': ['emerging tech', 'blockchain', 'web3', 'smart contract', 'edge computing', 'digital twin', 'augmented reality', 'virtual reality', 'green computing'],
};
// ─── Bible level topic mappings ───────────────────────────────────────────
// Maps Bible level dir names to topics relevant for app-building context.
// Includes 204 atomic code-chunk entries from data/code-bible/ (tags double as topics).
const BIBLE_LEVEL_TOPICS = {
    '01-foundations': ['algorithms', 'data structures', 'computational thinking', 'design patterns', 'testing', 'debugging', 'foundations'],
    '01-fundamentals': ['fundamentals', 'basics', 'core concepts', 'programming'],
    '02-board-games': ['game logic', 'state machines', 'event loops', 'ai opponent'],
    '02-games': ['game development', 'rendering', 'game loop', 'physics'],
    '03-desktop-apps': ['desktop', 'gui', 'widget', 'event handling', 'window'],
    '03-encryption': ['encryption', 'cipher', 'cryptography', 'security'],
    '04-web': ['web', 'http', 'browser', 'frontend', 'backend'],
    '04-web-apps': ['web application', 'fullstack', 'api', 'rest', 'graphql', 'database design'],
    '05-systems': ['systems programming', 'memory', 'process', 'io', 'concurrency'],
    '05-systems-programming': ['systems', 'c', 'c++', 'rust', 'memory management', 'performance'],
    '06-databases': ['database', 'sql', 'nosql', 'query', 'schema', 'indexing'],
    '06-os-kernel': ['os', 'kernel', 'boot', 'scheduler', 'file system', 'driver'],
    '07-ai-ml': ['ai', 'machine learning', 'neural network', 'deep learning', 'cnn', 'rnn', 'transformer'],
    '07-llm-guide': ['llm', 'prompt engineering', 'architecture', 'system design', 'reasoning'],
    '08-computer-graphics': ['graphics', 'rendering', 'shader', 'opengl', 'vulkan'],
    '08-graphics': ['graphics', 'image processing', 'visualization'],
    '09-game-engines': ['game engine', 'entity', 'component', 'physics', 'scene'],
    '09-hardware': ['hardware', 'cpu', 'gpu', 'architecture'],
    '10-machine-learning': ['ml', 'model training', 'inference', 'feature engineering'],
    '10-security': ['security', 'authentication', 'authorization', 'xss', 'sql injection', 'owasp'],
    '11-database-internals': ['database internals', 'btree', 'transaction', 'isolation', 'storage engine'],
    '11-language-design': ['language design', 'compiler', 'interpreter', 'parser', 'type system'],
    '12-devops': ['devops', 'ci', 'cd', 'deployment', 'monitoring', 'infrastructure'],
    '12-distributed-systems': ['distributed', 'consensus', 'raft', 'paxos', 'cap theorem'],
    '13-math': ['mathematics', 'linear algebra', 'calculus', 'statistics', 'logic'],
    '13-networking-deep': ['networking', 'tcp', 'ip', 'dns', 'load balancing', 'latency'],
    '14-cryptography-security': ['cryptography', 'encryption', 'hashing', 'signature', 'tls'],
    '14-protocols': ['protocols', 'grpc', 'websocket', 'http2', 'rest'],
    '15-programming-languages': ['programming languages', 'paradigm', 'type theory', 'syntax'],
    '16-computer-architecture': ['computer architecture', 'cpu', 'memory hierarchy', 'pipeline'],
    '17-virtualization-containers': ['virtualization', 'container', 'docker', 'vm', 'kubernetes'],
    '18-advanced-domains': ['advanced computing', 'quantum', 'bioinformatics'],
    '19-formal-methods-tools': ['formal methods', 'verification', 'model checking', 'proof'],
    '20-specialized-computing': ['specialized computing', 'gpgpu', 'fpga', 'asic'],
    '21-digital-content-media': ['digital media', 'streaming', 'video', 'audio', 'content delivery'],
    '22-browser-engineering': ['browser engine', 'rendering', 'dom', 'javascript engine'],
    '23-iot-embedded-deep': ['iot', 'embedded', 'firmware', 'sensor', 'microcontroller'],
    '24-autonomous-adas': ['autonomous', 'adas', 'self-driving', 'computer vision', 'lidar'],
    '25-industrial-manufacturing': ['industrial', 'manufacturing', 'automation', 'plc', 'scada'],
    '26-enterprise-systems': ['enterprise', 'erp', 'crm', 'workflow', 'business logic'],
    '27-data-engineering': ['data engineering', 'etl', 'warehouse', 'spark', 'data pipeline'],
    '28-trust-security-deep': ['trust', 'security deep', 'zero trust', 'iam', 'compliance'],
    '29-emerging-tech': ['emerging tech', 'blockchain', 'web3', 'edge computing'],
    '30-software-process': ['software process', 'agile', 'scrum', 'methodology', 'estimation'],
    '31-mobile-cross-platform': ['mobile', 'ios', 'android', 'cross platform', 'react native', 'flutter'],
    '32-cloud-native-infra': ['cloud native', 'microservices', 'service mesh', 'serverless'],
    '33-devops-sre-tooling': ['devops', 'sre', 'observability', 'incident response', 'slo'],
    '34-api-integration-platforms': ['api integration', 'api gateway', 'webhook', 'soap', 'rest'],
    '35-realtime-collaboration': ['realtime', 'collaboration', 'websocket', 'crdt', 'operational transform'],
    '36-search-recs-personalization': ['search', 'recommendation', 'personalization', 'indexing', 'ranking'],
    '37-aiml-platforms-llmops': ['ai platform', 'mlops', 'llmops', 'model serving', 'fine tuning'],
    '38-fintech-insurance': ['fintech', 'payments', 'insurance', 'banking', 'compliance'],
    '39-healthcare-life-sciences': ['healthcare', 'hipaa', 'medical', 'life sciences', 'ehr'],
    '40-media-entertainment-social': ['media', 'entertainment', 'social', 'content platform'],
    '41-marketplace-sharing-economy': ['marketplace', 'sharing economy', 'platform', 'two sided'],
    '42-education-learning': ['education', 'learning management', 'edtech', 'lms'],
    'acc-announce': ['acc', 'announce', 'live-region', 'polite', 'assertive'],
    'acc-aria-expanded': ['acc', 'aria-expanded', 'disclosure', 'toggle'],
    'acc-assist-label': ['acc', 'label', 'accessible-name', 'text'],
    'acc-contrast': ['acc', 'contrast', 'wcag', 'luminance', 'aa'],
    'acc-dialog-wiring': ['acc', 'dialog', 'aria-modal', 'modal', 'labelledby'],
    'acc-focus-manager': ['acc', 'focus', 'keyboard', 'navigation', 'manager'],
    'acc-focus-restore': ['acc', 'focus', 'restore', 'modal', 'close'],
    'acc-focus-visible': ['acc', 'focus-visible', 'keyboard', 'focus-ring'],
    'acc-form-announce': ['acc', 'form', 'error', 'aria-invalid', 'announce'],
    'acc-heading-order': ['acc', 'heading', 'outline', 'audit', 'h1'],
    'acc-icon-button': ['acc', 'icon', 'button', 'aria-label', 'name'],
    'acc-inert': ['acc', 'inert', 'modal', 'background', 'tab-order'],
    'acc-kbd-grid': ['acc', 'keyboard', 'grid', 'navigation', 'arrows'],
    'acc-label-link': ['acc', 'label', 'form', 'association', 'for'],
    'acc-landmark': ['acc', 'landmark', 'navigation', 'main', 'audit'],
    'acc-live-queue': ['acc', 'live-region', 'queue', 'announce', 'order'],
    'acc-live-region': ['acc', 'aria', 'live-region', 'screen-reader', 'announce'],
    'acc-reduced-data': ['acc', 'reduced-data', 'media', 'save-data'],
    'acc-reduced-motion': ['acc', 'reduced-motion', 'animation', 'media-query'],
    'acc-skip-link': ['acc', 'skip-link', 'keyboard', 'navigation'],
    'acc-sr-only': ['acc', 'sr-only', 'screen-reader', 'visually-hidden'],
    'acc-status-timer': ['acc', 'status', 'timer', 'announce', 'role'],
    'acc-table-semantics': ['acc', 'table', 'semantics', 'th', 'scope'],
    'acc-target-size': ['acc', 'target-size', 'touch', 'wcag', 'audit'],
    'acc-touch-audit': ['acc', 'touch', 'audit', 'target', 'mobile'],
    'alg-bellman-ford': ['alg', 'graph', 'shortest-path', 'negative-weights'],
    'alg-bipartite': ['alg', 'graph', 'bipartite', '2-color', 'bfs'],
    'alg-bucket-sort': ['alg', 'sort', 'bucket', 'float'],
    'alg-counting-sort': ['alg', 'sort', 'counting', 'linear'],
    'alg-crt': ['alg', 'number-theory', 'crt', 'congruence'],
    'alg-exponential-search': ['alg', 'search', 'exponential', 'sorted'],
    'alg-extended-euclid': ['alg', 'number-theory', 'euclid', 'modular-inverse'],
    'alg-floyd-warshall': ['alg', 'graph', 'all-pairs', 'shortest-path', 'dp'],
    'alg-heapsort': ['alg', 'sort', 'heapsort', 'in-place'],
    'alg-interpolation-search': ['alg', 'search', 'interpolation', 'sorted'],
    'alg-jump-search': ['alg', 'search', 'jump', 'sorted'],
    'alg-kmp': ['alg', 'string', 'kmp', 'search', 'pattern'],
    'alg-kruskal': ['alg', 'graph', 'mst', 'kruskal', 'union-find'],
    'alg-lcs': ['alg', 'dp', 'lcs', 'diff', 'sequence'],
    'alg-lis': ['alg', 'dp', 'lis', 'subsequence'],
    'alg-manacher': ['alg', 'string', 'palindrome', 'manacher', 'linear'],
    'alg-max-flow': ['alg', 'graph', 'max-flow', 'edmonds-karp', 'network'],
    'alg-miller-rabin': ['alg', 'number-theory', 'primality', 'miller-rabin'],
    'alg-prim': ['alg', 'graph', 'mst', 'prim'],
    'alg-rabin-karp': ['alg', 'string', 'rabin-karp', 'rolling-hash', 'search'],
    'alg-radix-sort': ['alg', 'sort', 'radix', 'integer'],
    'alg-tarjan-scc': ['alg', 'graph', 'scc', 'tarjan', 'strongly-connected'],
    'alg-timsort': ['alg', 'sort', 'timsort', 'stable', 'hybrid'],
    'alg-union-find': ['alg', 'union-find', 'disjoint-set', 'components'],
    'alg-z-algorithm': ['alg', 'string', 'z-algorithm', 'prefix'],
    'api-auth-middleware': ['auth', 'middleware', 'bearer', 'token', 'guard'],
    'api-body-parser': ['body', 'parse', 'validate', 'json', 'schema'],
    'api-config-loader': ['config', 'env', 'environment', 'settings', 'boot'],
    'api-cors-middleware': ['cors', 'origin', 'preflight', 'browser', 'headers'],
    'api-download-stream': ['download', 'stream', 'file', 'attachment', 'headers'],
    'api-error-handler': ['error', 'handler', 'async', 'catch', '500'],
    'api-etag-cache': ['etag', 'cache', 'http', '304', 'conditional'],
    'api-fetch-retry': ['fetch', 'retry', 'network', 'resilience', 'idempotent'],
    'api-graphql-resolver': ['graphql', 'resolver', 'schema', 'query', 'api'],
    'api-health-check': ['health', 'liveness', 'readiness', 'monitor', 'uptime'],
    'api-http-client': ['http', 'client', 'fetch', 'json', 'typed'],
    'api-http-server': ['http', 'server', 'bootstrap', 'listen', 'node'],
    'api-idempotency': ['idempotency', 'dedupe', 'retry', 'post', 'safe'],
    'api-json-response': ['json', 'response', 'envelope', 'success', 'error'],
    'api-jwt-sign': ['jwt', 'token', 'sign', 'hs256', 'session'],
    'api-jwt-verify': ['jwt', 'verify', 'token', 'signature', 'expiry'],
    'api-metrics-middleware': ['metrics', 'counters', 'middleware', 'observability', 'stats'],
    'api-paginated-response': ['paginate', 'list', 'response', 'cursor', 'meta'],
    'api-rate-limiter': ['rate', 'limit', 'throttle', 'abuse', 'window'],
    'api-request-logger': ['log', 'logger', 'request', 'middleware', 'metrics'],
    'api-rest-router': ['router', 'rest', 'route', 'method', 'dispatch'],
    'api-search-filter': ['filter', 'sort', 'query', 'params', 'list'],
    'api-sse-emitter': ['sse', 'server-sent', 'stream', 'eventsource', 'realtime'],
    'api-upload-handler': ['upload', 'multipart', 'file', 'stream', 'storage'],
    'api-webhook-receiver': ['webhook', 'receiver', 'verify', 'signature', 'callback'],
    'api-ws-server': ['websocket', 'server', 'realtime', 'rooms', 'broadcast'],
    'arch-adapter': ['arch', 'adapter', 'bridge', 'interface', 'translate'],
    'arch-backpressure': ['arch', 'backpressure', 'queue', 'bounded', 'flow-control'],
    'arch-builder': ['arch', 'builder', 'fluent', 'immutable', 'construction'],
    'arch-bulkhead': ['arch', 'bulkhead', 'isolation', 'semaphore', 'concurrency'],
    'arch-chain-responsibility': ['arch', 'chain', 'responsibility', 'handlers', 'pipeline'],
    'arch-circuit-breaker': ['arch', 'circuit-breaker', 'resilience', 'failure'],
    'arch-command': ['arch', 'command', 'undo', 'action', 'queue'],
    'arch-composite': ['arch', 'composite', 'tree', 'recursive', 'group'],
    'arch-cqrs': ['arch', 'cqrs', 'command', 'query', 'write-model'],
    'arch-decorator': ['arch', 'decorator', 'wrapper', 'composition', 'higher-order'],
    'arch-di-container': ['arch', 'di', 'container', 'ioc', 'singleton'],
    'arch-event-sourcing': ['arch', 'event-sourcing', 'events', 'replay', 'fold'],
    'arch-facade': ['arch', 'facade', 'simplify', 'subsystem'],
    'arch-factory': ['arch', 'factory', 'creation', 'registry'],
    'arch-feature-flags': ['arch', 'feature-flag', 'rollout', 'targeting'],
    'arch-flyweight': ['arch', 'flyweight', 'pool', 'memory', 'cache'],
    'arch-hexagonal': ['arch', 'hexagonal', 'ports', 'adapters', 'di'],
    'arch-layered': ['arch', 'layers', 'boundary', 'dependency', 'structure'],
    'arch-mediator': ['arch', 'mediator', 'decouple', 'routing'],
    'arch-memento': ['arch', 'memento', 'snapshot', 'restore', 'state'],
    'arch-plugin-registry': ['arch', 'plugin', 'registry', 'extension', 'lifecycle'],
    'arch-proxy': ['arch', 'proxy', 'intercept', 'guard', 'access-control'],
    'arch-saga': ['arch', 'saga', 'transaction', 'compensation', 'orchestration'],
    'arch-strategy': ['arch', 'strategy', 'algorithm', 'polymorphism'],
    'arch-unit-of-work': ['arch', 'unit-of-work', 'transaction', 'tracking'],
    'brw-audio-unlock': ['brw', 'audio', 'unlock', 'autoplay', 'webaudio'],
    'brw-clipboard': ['brw', 'clipboard', 'copy', 'text', 'fallback'],
    'brw-cookie': ['brw', 'cookie', 'get', 'set', 'delete'],
    'brw-debounce-resize': ['brw', 'resize', 'debounce', 'window', 'handler'],
    'brw-dom-ready': ['brw', 'dom', 'ready', 'init', 'load'],
    'brw-download-blob': ['brw', 'download', 'blob', 'file', 'save'],
    'brw-drag-files': ['brw', 'drag', 'drop', 'files', 'upload'],
    'brw-element-size': ['brw', 'resize', 'observer', 'element', 'size'],
    'brw-focus-trap': ['brw', 'focus', 'trap', 'modal', 'a11y'],
    'brw-form-serialize': ['brw', 'form', 'serialize', 'formdata', 'object'],
    'brw-fullscreen': ['brw', 'fullscreen', 'toggle', 'element', 'screen'],
    'brw-hash-router': ['brw', 'hash', 'router', 'spa', 'route'],
    'brw-image-preload': ['brw', 'image', 'preload', 'load', 'cache'],
    'brw-keyboard': ['brw', 'keyboard', 'shortcut', 'hotkey', 'registry'],
    'brw-media-query': ['brw', 'media', 'query', 'responsive', 'match'],
    'brw-network-status': ['brw', 'network', 'online', 'offline', 'status'],
    'brw-notify': ['brw', 'notification', 'permission', 'toast', 'wrapper'],
    'brw-open-tab': ['brw', 'open', 'tab', 'noopener', 'link'],
    'brw-position': ['brw', 'position', 'rect', 'tooltip', 'geometry'],
    'brw-quota': ['brw', 'storage', 'quota', 'estimate', 'persist'],
    'brw-raf-loop': ['brw', 'raf', 'loop', 'frame', 'animation'],
    'brw-scroll': ['brw', 'scroll', 'smooth', 'position', 'element'],
    'brw-storage': ['brw', 'localstorage', 'storage', 'typed', 'persist'],
    'brw-title-flash': ['brw', 'title', 'flash', 'notification', 'tab'],
    'brw-url-query': ['brw', 'url', 'query', 'params', 'parse'],
    'brw-visibility': ['brw', 'visibility', 'hidden', 'tab', 'tracker'],
    'cli-banner': ['cli', 'banner', 'ascii', 'title', 'separator'],
    'cli-colorize': ['cli', 'ansi', 'color', 'style', 'terminal'],
    'cli-command-router': ['cli', 'command', 'router', 'dispatch', 'handler'],
    'cli-confirm-parse': ['cli', 'confirm', 'yes', 'no', 'parse'],
    'cli-csv-quote': ['cli', 'csv', 'quote', 'escape', 'field'],
    'cli-exit-codes': ['cli', 'exit', 'code', 'status', 'error'],
    'cli-glob-match': ['cli', 'glob', 'match', 'pattern', 'files'],
    'cli-help-screen': ['cli', 'help', 'usage', 'options', 'screen'],
    'cli-human-size': ['cli', 'bytes', 'format', 'size', 'human'],
    'cli-indent-block': ['cli', 'indent', 'block', 'prefix', 'format'],
    'cli-json-out': ['cli', 'json', 'pretty', 'print', 'format'],
    'cli-key-value-parse': ['cli', 'key-value', 'parse', 'tokens', 'env'],
    'cli-paginate': ['cli', 'page', 'paginate', 'window', 'list'],
    'cli-parse-args': ['cli', 'args', 'parse', 'flags', 'terminal'],
    'cli-path-resolve': ['cli', 'path', 'resolve', 'normalize', 'segments'],
    'cli-progress': ['cli', 'progress', 'eta', 'percent', 'format'],
    'cli-prompt-menu': ['cli', 'menu', 'prompt', 'interactive', 'options'],
    'cli-quote-shell': ['cli', 'shell', 'quote', 'escape', 'security'],
    'cli-rate-limit': ['cli', 'rate', 'limit', 'throttle', 'bucket'],
    'cli-search-filter': ['cli', 'filter', 'search', 'prefix', 'list'],
    'cli-spinner-frames': ['cli', 'spinner', 'frames', 'animate', 'tick'],
    'cli-table': ['cli', 'table', 'ascii', 'render', 'terminal'],
    'cli-timeout-wrap': ['cli', 'timeout', 'promise', 'async', 'wrapper'],
    'cli-truncate': ['cli', 'truncate', 'ellipsis', 'width', 'string'],
    'cli-word-wrap': ['cli', 'wrap', 'width', 'text', 'terminal'],
    'col-avltree': ['col', 'avl', 'tree', 'balanced', 'bst'],
    'col-capacity-set': ['col', 'set', 'capacity', 'eviction', 'cache'],
    'col-chunker': ['col', 'chunk', 'partition', 'batch', 'paging'],
    'col-difference-array': ['col', 'difference', 'array', 'range-update'],
    'col-fenwick': ['col', 'fenwick', 'bit', 'prefix-sum', 'query'],
    'col-freq-counter': ['col', 'frequency', 'counter', 'histogram', 'top-n'],
    'col-interval-merge': ['col', 'interval', 'merge', 'overlap', 'sweep'],
    'col-interval-tree': ['col', 'interval', 'tree', 'overlap', 'query'],
    'col-kdtree': ['col', 'kd-tree', 'nearest-neighbor', 'spatial', '2d'],
    'col-linked-list': ['col', 'linked-list', 'list', 'deque', 'data-structure'],
    'col-minmax-heap': ['col', 'minmax-heap', 'heap', 'priority-queue'],
    'col-monotonic': ['col', 'monotonic', 'stack', 'queue', 'sliding-window'],
    'col-pairing': ['col', 'pair', 'adjacent', 'window', 'group'],
    'col-partition': ['col', 'partition', 'filter', 'split', 'predicate'],
    'col-prefix-sum': ['col', 'prefix-sum', '2d', 'rectangle', 'query'],
    'col-redblack': ['col', 'red-black', 'tree', 'balanced', 'bst'],
    'col-rotate': ['col', 'rotate', 'array', 'shift', 'in-place'],
    'col-segment-tree': ['col', 'segment-tree', 'range-query', 'update'],
    'col-skip-list': ['col', 'skip-list', 'ordered', 'probabilistic'],
    'col-sparse-matrix': ['col', 'sparse', 'matrix', 'memory', '2d'],
    'col-sparse-table': ['col', 'sparse-table', 'rmq', 'range-min', 'immutable'],
    'col-timestamped-queue': ['col', 'queue', 'timestamp', 'ttl', 'eviction'],
    'col-treap': ['col', 'treap', 'randomized', 'bst', 'split'],
    'col-unique-sorted': ['col', 'sorted', 'unique', 'insert', 'binary-search'],
    'col-zipper': ['col', 'zipper', 'cursor', 'focus', 'list'],
    'crypto-aes-decrypt': ['aes', 'gcm', 'decrypt', 'cipher', 'auth'],
    'crypto-aes-encrypt': ['aes', 'gcm', 'encrypt', 'cipher', 'crypto'],
    'crypto-base64': ['base64', 'encode', 'decode', 'codec', 'binary'],
    'crypto-constant-time': ['constant', 'time', 'compare', 'timing', 'safe'],
    'crypto-envelope': ['envelope', 'hybrid', 'encrypt', 'publickey', 'seal'],
    'crypto-hmac': ['hmac', 'sha256', 'mac', 'authenticate', 'digest'],
    'crypto-key-derivation': ['pbkdf2', 'derive', 'key', 'password', 'kdf'],
    'crypto-password-hash': ['password', 'hash', 'scrypt', 'salt', 'security'],
    'crypto-pem-parse': ['pem', 'key', 'parse', 'certificate', 'der'],
    'crypto-random': ['random', 'secure', 'token', 'csprng', 'secret'],
    'crypto-rsa-keygen': ['rsa', 'keygen', 'keys', 'asymmetric', 'pem'],
    'crypto-rsa-sign': ['rsa', 'sign', 'verify', 'signature', 'authenticity'],
    'crypto-salt-generator': ['salt', 'generate', 'random', 'hash', 'crypto'],
    'crypto-sha256': ['sha256', 'hash', 'digest', 'checksum', 'fingerprint'],
    'crypto-token-bucket': ['token', 'bucket', 'rate', 'limit', 'burst'],
    'crypto-totp': ['totp', '2fa', 'otp', 'mfa', 'authenticator'],
    'crypto-xss-sanitize': ['xss', 'sanitize', 'html', 'security', 'escape'],
    'data-binary-search': ['binary', 'search', 'sorted', 'logn', 'algorithm'],
    'data-blob-store': ['blob', 'binary', 'storage', 'upload', 'bytes'],
    'data-bloom-filter': ['bloom', 'filter', 'membership', 'probabilistic', 'memory'],
    'data-connection-pool': ['pool', 'connection', 'resource', 'concurrency', 'reuse'],
    'data-csv-parse': ['csv', 'parse', 'import', 'tabular', 'text'],
    'data-csv-write': ['csv', 'write', 'export', 'serialize', 'tabular'],
    'data-event-log': ['event', 'log', 'append', 'audit', 'ledger'],
    'data-fulltext-index': ['fulltext', 'search', 'inverted', 'index', 'tokenize'],
    'data-hash-table': ['hash', 'table', 'map', 'lookup', 'data structure'],
    'data-id-generator': ['id', 'uuid', 'generator', 'unique', 'sortable'],
    'data-indexeddb-store': ['indexeddb', 'browser', 'store', 'offline', 'persist'],
    'data-json-file-store': ['json', 'file', 'store', 'persist', 'atomic write'],
    'data-migration-runner': ['migration', 'schema', 'version', 'ddl', 'database'],
    'data-mongo-connect': ['mongodb', 'nosql', 'database', 'connect', 'document'],
    'data-pagination-query': ['pagination', 'offset', 'page', 'slice', 'query'],
    'data-pg-pool': ['postgres', 'sql', 'pool', 'database', 'server'],
    'data-query-builder': ['query', 'builder', 'sql', 'parameterized', 'safe'],
    'data-repository-crud': ['repository', 'crud', 'dao', 'abstraction', 'data'],
    'data-schema-validator': ['validate', 'schema', 'types', 'input', 'check'],
    'data-snapshot-store': ['snapshot', 'backup', 'restore', 'state', 'copy'],
    'data-sqlite-connect': ['sqlite', 'database', 'connect', 'wal', 'local'],
    'data-transaction': ['transaction', 'atomic', 'commit', 'rollback', 'database'],
    'data-vector-store': ['vector', 'embedding', 'similarity', 'cosine', 'rag'],
    'db-audit-columns': ['db', 'audit', 'columns', 'timestamp', 'created-at'],
    'db-batch-insert': ['db', 'batch', 'insert', 'chunk', 'bulk'],
    'db-connection-retry': ['db', 'pool', 'connection', 'retry', 'acquire'],
    'db-counter-inc': ['db', 'counter', 'increment', 'atomic', 'sequence'],
    'db-cursor-codec': ['db', 'cursor', 'codec', 'pagination', 'base64url'],
    'db-explain-format': ['db', 'explain', 'plan', 'format', 'query'],
    'db-fulltext-tokenize': ['db', 'fulltext', 'tokenize', 'search', 'stopwords'],
    'db-group-agg': ['db', 'group', 'aggregate', 'reduce', 'groupby'],
    'db-json-filter': ['db', 'json', 'filter', 'nested', 'query'],
    'db-keyset-paginate': ['db', 'pagination', 'keyset', 'cursor', 'query'],
    'db-memory-table': ['db', 'memory', 'store', 'crud', 'table'],
    'db-migration-runner': ['db', 'migration', 'version', 'schema', 'apply'],
    'db-migration-stamp': ['db', 'migration', 'stamp', 'idempotent', 'version'],
    'db-order-builder': ['db', 'order', 'sort', 'allowlist', 'sql'],
    'db-param-builder': ['db', 'sql', 'parameter', 'injection', 'safe'],
    'db-query-logger': ['db', 'query', 'log', 'slow', 'duration'],
    'db-query-throttle': ['db', 'query', 'throttle', 'debounce', 'cache'],
    'db-replica-router': ['db', 'replica', 'router', 'read', 'write'],
    'db-result-mapper': ['db', 'mapper', 'row', 'object', 'snake-case'],
    'db-schema-diff': ['db', 'schema', 'diff', 'columns', 'migration'],
    'db-snapshot-store': ['db', 'snapshot', 'json', 'persist', 'store'],
    'db-soft-delete': ['db', 'soft', 'delete', 'archive', 'timestamp'],
    'db-transaction-wrap': ['db', 'transaction', 'atomic', 'commit', 'rollback'],
    'db-upsert-builder': ['db', 'upsert', 'sql', 'insert', 'conflict'],
    'db-where-builder': ['db', 'where', 'sql', 'filter', 'builder'],
    'devops-archive-keep': ['devops', 'retention', 'archive', 'prune', 'keep'],
    'devops-backoff-retry': ['devops', 'retry', 'backoff', 'jitter', 'resilience'],
    'devops-changelog-parse': ['devops', 'changelog', 'parse', 'release', 'notes'],
    'devops-ci-matrix': ['devops', 'ci', 'matrix', 'expand', 'cartesian'],
    'devops-config-merge': ['devops', 'config', 'merge', 'defaults', 'deep'],
    'devops-config-validate': ['devops', 'config', 'validate', 'required', 'env'],
    'devops-cron-validate': ['devops', 'cron', 'validate', 'schedule', 'timer'],
    'devops-deadline-timer': ['devops', 'deadline', 'timer', 'expiry', 'timeout'],
    'devops-diff-summary': ['devops', 'diff', 'summary', 'stats', 'changes'],
    'devops-disk-estimate': ['devops', 'size', 'format', 'bytes', 'disk'],
    'devops-env-file': ['devops', 'env', 'dotenv', 'parse', 'write', 'config'],
    'devops-health-aggregate': ['devops', 'health', 'aggregate', 'status', 'probe'],
    'devops-health-wait': ['devops', 'health', 'wait', 'poll', 'readiness'],
    'devops-http-cache': ['devops', 'cache', 'http', 'cache-control', 'headers'],
    'devops-log-rotate': ['devops', 'log', 'rotate', 'size', 'policy'],
    'devops-pin-check': ['devops', 'dependency', 'pin', 'semver', 'range'],
    'devops-port-alloc': ['devops', 'port', 'alloc', 'tcp', 'server'],
    'devops-rate-limit': ['devops', 'rate', 'limit', 'window', 'throttle'],
    'devops-release-notes': ['devops', 'release', 'notes', 'conventional', 'commits'],
    'devops-secret-mask': ['devops', 'secret', 'redact', 'mask', 'log'],
    'devops-semver': ['devops', 'semver', 'version', 'bump', 'compare'],
    'devops-shutdown-coord': ['devops', 'shutdown', 'graceful', 'cleanup', 'lifecycle'],
    'devops-timeout-wrap': ['devops', 'timeout', 'async', 'guard', 'deadline'],
    'devops-version-stamp': ['devops', 'version', 'stamp', 'build', 'id'],
    'devops-warmup-check': ['devops', 'startup', 'readiness', 'poll', 'warmup'],
    'edu-answer-feedback': ['edu', 'feedback', 'answer', 'message', 'quiz'],
    'edu-badge-progress': ['edu', 'badge', 'achievement', 'unlock', 'milestone'],
    'edu-cloze-check': ['edu', 'cloze', 'fill-blank', 'answer', 'normalize'],
    'edu-confidence-rating': ['edu', 'confidence', 'rating', 'review', 'priority'],
    'edu-flashcard-deck': ['edu', 'flashcard', 'deck', 'due', 'review'],
    'edu-forgetting-curve': ['edu', 'forgetting', 'curve', 'retention', 'memory'],
    'edu-gpa': ['edu', 'gpa', 'grade-point', 'credits', 'average'],
    'edu-grading-scale': ['edu', 'grade', 'letter', 'score', 'scale'],
    'edu-learning-plan': ['edu', 'plan', 'study', 'schedule', 'distribute'],
    'edu-lesson-lock': ['edu', 'lesson', 'unlock', 'gate', 'course'],
    'edu-mastery-level': ['edu', 'mastery', 'level', 'estimate', 'scores'],
    'edu-multiple-choice': ['edu', 'multiple-choice', 'score', 'answers', 'quiz'],
    'edu-normal-curve': ['edu', 'curve', 'normal', 'grade', 'adjust'],
    'edu-passing-check': ['edu', 'pass', 'fail', 'threshold', 'check'],
    'edu-progress-ring': ['edu', 'progress', 'course', 'lesson', 'percent'],
    'edu-quiz-shuffle': ['edu', 'quiz', 'shuffle', 'seed', 'order'],
    'edu-quiz-timer': ['edu', 'quiz', 'timer', 'pace', 'remaining'],
    'edu-review-mix': ['edu', 'review', 'mix', 'interleave', 'schedule'],
    'edu-score-normalize': ['edu', 'score', 'normalize', 'percent', 'scale'],
    'edu-sm2': ['edu', 'spaced', 'repetition', 'sm2', 'flashcard'],
    'edu-streak': ['edu', 'streak', 'habit', 'days', 'activity'],
    'edu-syllable-count': ['edu', 'syllable', 'count', 'reading', 'word'],
    'edu-text-difficulty': ['edu', 'reading', 'flesch', 'difficulty', 'readability'],
    'edu-timer-sessions': ['edu', 'timer', 'session', 'study', 'pomodoro'],
    'edu-vocab-list': ['edu', 'vocab', 'list', 'dedupe', 'sort'],
    'embed-avg-filter': ['embed', 'average', 'filter', 'smooth', 'adc'],
    'embed-baud-rate': ['embed', 'baud', 'serial', 'timing', 'uart'],
    'embed-bit-crc16': ['embed', 'crc16', 'ccitt', 'checksum', 'frame'],
    'embed-bitfield': ['embed', 'bitfield', 'register', 'mask', 'bits'],
    'embed-boot-check': ['embed', 'boot', 'self-test', 'check', 'diagnostic'],
    'embed-byte-ops': ['embed', 'byte', 'pack', 'endian', 'binary'],
    'embed-crc8': ['embed', 'crc8', 'checksum', 'integrity', 'packet'],
    'embed-debounce': ['embed', 'debounce', 'button', 'events', 'delay'],
    'embed-frame-codec': ['embed', 'frame', 'codec', 'serial', 'protocol'],
    'embed-gpio-sim': ['embed', 'gpio', 'pin', 'simulate', 'edge'],
    'embed-hex-dump': ['embed', 'hex', 'dump', 'debug', 'bytes'],
    'embed-leb128': ['embed', 'leb128', 'varint', 'encode', 'stream'],
    'embed-nibble': ['embed', 'nibble', 'byte', 'split', 'hex'],
    'embed-parse-fixed': ['embed', 'fixed-point', 'parse', 'format', 'int'],
    'embed-pwm': ['embed', 'pwm', 'duty', 'cycle', 'timing'],
    'embed-queued-worker': ['embed', 'queue', 'worker', 'jobs', 'serial'],
    'embed-reset-causes': ['embed', 'reset', 'cause', 'decode', 'flags'],
    'embed-ring-buffer': ['embed', 'ring', 'buffer', 'fifo', 'bounded'],
    'embed-sample-hold': ['embed', 'sample', 'hold', 'sensor', 'read'],
    'embed-state-machine': ['embed', 'state', 'machine', 'fsm', 'transition'],
    'embed-throttle': ['embed', 'throttle', 'rate', 'events', 'interval'],
    'embed-timer-wheel': ['embed', 'timer', 'wheel', 'schedule', 'tick'],
    'embed-uptime': ['embed', 'uptime', 'duration', 'format', 'time'],
    'embed-vector-scale': ['embed', 'sensor', 'scale', 'calibrate', 'adc'],
    'embed-watchdog': ['embed', 'watchdog', 'heartbeat', 'kick', 'timeout'],
    'fin-amortization': ['fin', 'amortization', 'loan', 'mortgage', 'schedule'],
    'fin-annuity-fv': ['fin', 'annuity', 'future-value', 'compound', 'interest'],
    'fin-bill-due': ['fin', 'bill', 'due', 'calendar', 'schedule'],
    'fin-budget-category': ['fin', 'budget', 'category', 'expense', 'tracker'],
    'fin-capm': ['fin', 'capm', 'beta', 'expected-return', 'risk'],
    'fin-compound-interest': ['fin', 'compound', 'interest', 'growth', 'balance'],
    'fin-currency-format': ['fin', 'currency', 'format', 'money', 'display'],
    'fin-dca': ['fin', 'dca', 'dollar-cost', 'average', 'invest'],
    'fin-debt-avalanche': ['fin', 'debt', 'avalanche', 'interest', 'payoff'],
    'fin-debt-snowball': ['fin', 'debt', 'snowball', 'payoff', 'order'],
    'fin-envelope-method': ['fin', 'envelope', 'budget', 'allocation', 'income'],
    'fin-expense-trend': ['fin', 'expense', 'trend', 'compare', 'delta'],
    'fin-interest-split': ['fin', 'interest', 'principal', 'payment', 'split'],
    'fin-invoice-due': ['fin', 'invoice', 'aging', 'overdue', 'report'],
    'fin-irr': ['fin', 'irr', 'internal-rate', 'return', 'bisection'],
    'fin-npv': ['fin', 'npv', 'net-present-value', 'valuation', 'cash-flow'],
    'fin-portfolio-alloc': ['fin', 'portfolio', 'allocation', 'weights', 'assets'],
    'fin-pv': ['fin', 'present-value', 'discount', 'cash-flow', 'npv'],
    'fin-rebalance': ['fin', 'rebalance', 'trades', 'portfolio', 'target'],
    'fin-return-pct': ['fin', 'return', 'cagr', 'annualized', 'growth'],
    'fin-savings-goal': ['fin', 'savings', 'goal', 'progress', 'eta'],
    'fin-simple-interest': ['fin', 'simple', 'interest', 'accrual'],
    'fin-tax-bracket': ['fin', 'tax', 'bracket', 'marginal', 'income'],
    'fin-tip-split': ['fin', 'tip', 'split', 'bill', 'calculator'],
    'fin-vwap': ['fin', 'vwap', 'volume', 'average', 'price'],
    'fs-recent-files': ['fsys', 'recent', 'sort', 'modified', 'files'],
    'fsys-atomic-rename': ['fsys', 'atomic', 'rename', 'write', 'safe'],
    'fsys-binary-header': ['fsys', 'binary', 'header', 'parse', 'data-view'],
    'fsys-buffered-writer': ['fsys', 'buffer', 'writer', 'batch', 'flush'],
    'fsys-chunked-reader': ['fsys', 'chunk', 'stream', 'reader', 'iterator'],
    'fsys-copy-tree': ['fsys', 'copy', 'tree', 'mirror', 'filter'],
    'fsys-dedupe-hash': ['fsys', 'dedupe', 'hash', 'duplicate', 'group'],
    'fsys-dir-checksum': ['fsys', 'checksum', 'fingerprint', 'directory', 'change-detect'],
    'fsys-dir-tree': ['fsys', 'tree', 'directory', 'render', 'ascii'],
    'fsys-disk-usage': ['fsys', 'disk', 'usage', 'size', 'aggregate'],
    'fsys-extension-map': ['fsys', 'extension', 'mime', 'file-type', 'lookup'],
    'fsys-file-split': ['fsys', 'split', 'join', 'chunk', 'parts'],
    'fsys-find-dup-names': ['fsys', 'duplicate', 'collision', 'names', 'case'],
    'fsys-home-expand': ['fsys', 'home', 'tilde', 'expand', 'env'],
    'fsys-jsonl-stream': ['fsys', 'jsonl', 'stream', 'parser', 'ndjson'],
    'fsys-line-counter': ['fsys', 'line', 'count', 'stream', 'wc'],
    'fsys-offset-reader': ['fsys', 'offset', 'range', 'reader', 'partial'],
    'fsys-path-join': ['fsys', 'path', 'join', 'resolve', 'segments'],
    'fsys-path-normalize': ['fsys', 'path', 'normalize', 'resolve', 'segments'],
    'fsys-recursive-delete': ['fsys', 'delete', 'recursive', 'guard', 'safe'],
    'fsys-safe-filename': ['fsys', 'filename', 'sanitize', 'safe', 'security'],
    'fsys-sort-by-size': ['fsys', 'sort', 'size', 'ranking', 'cleanup'],
    'fsys-staging-dir': ['fsys', 'staging', 'commit', 'transaction', 'temp'],
    'fsys-tail-reader': ['fsys', 'tail', 'last-lines', 'reader', 'reverse'],
    'fsys-temp-file': ['fsys', 'temp', 'temporary', 'unique', 'cleanup'],
    'game-aabb-collision': ['collision', 'aabb', 'rect', 'overlap', 'physics'],
    'game-achievement': ['achievement', 'badge', 'unlock', 'progress', 'gamification'],
    'game-audio-manager': ['audio', 'sound', 'webaudio', 'sfx', 'volume'],
    'game-camera': ['camera', 'follow', 'scroll', 'viewport', 'transform'],
    'game-ecs': ['ecs', 'entity', 'component', 'system', 'game'],
    'game-fixed-timestep': ['timestep', 'fixed', 'physics', 'deterministic', 'accumulator'],
    'game-highscore-table': ['highscore', 'leaderboard', 'rank', 'score', 'table'],
    'game-input-manager': ['input', 'keyboard', 'mouse', 'controls', 'keys'],
    'game-level-loader': ['level', 'loader', 'map', 'ascii', 'tiles'],
    'game-loop': ['game', 'loop', 'raf', 'delta', 'update'],
    'game-particles': ['particles', 'effects', 'explosion', 'confetti', 'emitter'],
    'game-save-load': ['save', 'load', 'persist', 'checkpoint', 'game'],
    'game-score-system': ['score', 'combo', 'level', 'lives', 'points'],
    'game-sprite-renderer': ['sprite', 'canvas', 'render', 'draw', 'image'],
    'game-tilemap': ['tilemap', 'tiles', 'grid', 'render', 'level'],
    'gen-arg-parser': ['gen', 'cli', 'args', 'parse', 'flags'],
    'gen-camel-case': ['gen', 'camel', 'case', 'identifier', 'naming'],
    'gen-doc-comment': ['gen', 'jsdoc', 'comment', 'doc', 'documentation'],
    'gen-env-default': ['gen', 'env', 'config', 'default', 'reader'],
    'gen-export-walk': ['gen', 'export', 'walk', 'parse', 'symbols'],
    'gen-file-tree': ['gen', 'tree', 'files', 'render', 'ascii'],
    'gen-hex-color': ['gen', 'color', 'hex', 'palette', 'generate'],
    'gen-import-sort': ['gen', 'import', 'sort', 'module', 'statement'],
    'gen-indent': ['gen', 'indent', 'format', 'source', 'whitespace'],
    'gen-kebab-case': ['gen', 'kebab', 'slug', 'case', 'filename'],
    'gen-line-diff': ['gen', 'diff', 'lines', 'lcs', 'compare'],
    'gen-lint-config': ['gen', 'config', 'merge', 'defaults', 'overrides'],
    'gen-num-format': ['gen', 'number', 'format', 'si', 'compact'],
    'gen-pascal-case': ['gen', 'pascal', 'case', 'class', 'component'],
    'gen-pluralize': ['gen', 'plural', 'singular', 'english', 'word'],
    'gen-progress-bar': ['gen', 'progress', 'bar', 'ascii', 'render'],
    'gen-random-id': ['gen', 'random', 'id', 'unique', 'generate'],
    'gen-snake-case': ['gen', 'snake', 'case', 'underscore', 'constant'],
    'gen-string-builder': ['gen', 'string', 'builder', 'accumulate', 'lines'],
    'gen-stub-func': ['gen', 'stub', 'function', 'scaffold', 'todo'],
    'gen-template-render': ['gen', 'template', 'render', 'placeholder', 'string'],
    'gen-ts-compile-error': ['gen', 'tsc', 'error', 'parse', 'typescript'],
    'gen-type-interface': ['gen', 'interface', 'typescript', 'types', 'infer'],
    'gen-unique-name': ['gen', 'unique', 'name', 'dedupe', 'generate'],
    'gen-version-bump': ['gen', 'semver', 'version', 'bump', 'release'],
    'gfx-arc': ['gfx', 'arc', 'dial', 'progress', 'ring'],
    'gfx-aspect-fit': ['gfx', 'image', 'aspect', 'fit', 'cover'],
    'gfx-bezier': ['gfx', 'bezier', 'curve', 'sample', 'de-casteljau'],
    'gfx-blur': ['gfx', 'blur', 'gaussian', 'kernel', 'image'],
    'gfx-camera': ['gfx', 'camera', 'zoom', 'pan', 'world'],
    'gfx-canvas-size': ['gfx', 'canvas', 'hidpi', 'retina', 'dpr'],
    'gfx-collision': ['gfx', 'collision', 'aabb', 'circle', 'hit-test'],
    'gfx-color': ['gfx', 'color', 'hex', 'rgb', 'hsl'],
    'gfx-easing': ['gfx', 'easing', 'animation', 'tween', 'interpolate'],
    'gfx-gradient': ['gfx', 'gradient', 'canvas', 'linear', 'radial'],
    'gfx-grid-layout': ['gfx', 'grid', 'layout', 'tiles', 'cells'],
    'gfx-lerp-color': ['gfx', 'lerp', 'color', 'interpolate', 'rgb'],
    'gfx-matrix2d': ['gfx', 'matrix', 'affine', 'transform', '2d'],
    'gfx-noise': ['gfx', 'perlin', 'noise', 'fbm', 'texture'],
    'gfx-offscreen': ['gfx', 'offscreen', 'canvas', 'cache', 'render'],
    'gfx-palette': ['gfx', 'palette', 'hsl', 'generate', 'chart'],
    'gfx-particle': ['gfx', 'particle', 'emitter', 'effect', 'confetti'],
    'gfx-pixels': ['gfx', 'pixel', 'imagedata', 'rgba', 'buffer'],
    'gfx-round-rect': ['gfx', 'round', 'rect', 'canvas', 'path'],
    'gfx-shadow': ['gfx', 'shadow', 'canvas', 'blur', 'style'],
    'gfx-sprite-frame': ['gfx', 'sprite', 'frame', 'animation', 'clock'],
    'gfx-svg-path': ['gfx', 'svg', 'path', 'builder', 'd'],
    'gfx-text-wrap': ['gfx', 'text', 'wrap', 'canvas', 'measure'],
    'gfx-vec2': ['gfx', 'vector', 'vec2', 'math', '2d'],
    'gfx-voronoi': ['gfx', 'voronoi', 'partition', 'nearest', 'seeds'],
    'http-accept-parse': ['http', 'accept', 'parser', 'q-value', 'negotiation'],
    'http-basic-auth': ['http', 'basic-auth', 'authorization', 'base64'],
    'http-bearer-token': ['http', 'bearer', 'token', 'authorization', 'extract'],
    'http-cache-revalidate': ['http', 'cache', 'revalidate', 'max-age', 'freshness'],
    'http-chunked-decode': ['http', 'chunked', 'transfer-encoding', 'decode'],
    'http-conditional': ['http', 'conditional', 'if-none-match', '304', 'etag'],
    'http-content-negotiation': ['http', 'negotiation', 'content-type', 'accept', 'pick'],
    'http-cookie-jar': ['http', 'cookie', 'jar', 'session', 'domain'],
    'http-date-header': ['http', 'date', 'header', 'rfc7231', 'imf-fixdate'],
    'http-form-urlencode': ['http', 'form', 'urlencoded', 'encode', 'parse'],
    'http-link-header': ['http', 'link', 'header', 'pagination', 'rel'],
    'http-longpoll': ['http', 'long-poll', 'comet', 'timeout', 'wait'],
    'http-method-allow': ['http', 'method', 'allow', '405', 'allowlist'],
    'http-multipart-parse': ['http', 'multipart', 'form-data', 'parser', 'boundary'],
    'http-oauth-refresh': ['http', 'oauth', 'refresh', 'token', 'expiry'],
    'http-range-respond': ['http', 'range', 'bytes', 'partial', '206'],
    'http-rate-header': ['http', 'rate-limit', 'header', '429', 'remaining'],
    'http-redirect-chain': ['http', 'redirect', 'chain', 'follow', 'loop'],
    'http-request-id': ['http', 'request-id', 'trace', 'correlation', 'id'],
    'http-retry-after': ['http', 'retry-after', '429', '503', 'parser'],
    'http-reverse-proxy': ['http', 'proxy', 'reverse', 'forward', 'backend'],
    'http-sse-client': ['http', 'sse', 'eventsource', 'stream', 'parser'],
    'http-status-text': ['http', 'status', 'code', 'reason', 'phrase'],
    'http-url-signer': ['http', 'url', 'sign', 'hmac', 'expiry'],
    'http-webhook-signature': ['http', 'webhook', 'signature', 'hmac', 'verify'],
    'i18n-bidi': ['i18n', 'bidi', 'rtl', 'order', 'mixed'],
    'i18n-calendar': ['i18n', 'calendar', 'gregory', 'resolvedOptions'],
    'i18n-collate': ['i18n', 'collation', 'sort', 'locale', 'compare'],
    'i18n-compact': ['i18n', 'compact', 'notation', 'abbreviate', 'number'],
    'i18n-currency': ['i18n', 'currency', 'money', 'format', 'Intl'],
    'i18n-date': ['i18n', 'date', 'format', 'Intl', 'locale'],
    'i18n-default-locale': ['i18n', 'locale', 'default', 'navigator', 'resolve'],
    'i18n-digit-strings': ['i18n', 'digit', 'grouping', 'thousands', 'separator'],
    'i18n-grapheme': ['i18n', 'grapheme', 'segmenter', 'unicode', 'emoji'],
    'i18n-interpolation': ['i18n', 'interpolate', 'template', 'placeholder', 'format'],
    'i18n-key-fallback': ['i18n', 'fallback', 'translation', 'locale-chain', 'key'],
    'i18n-locale-negotiate': ['i18n', 'negotiation', 'accept-language', 'locale', 'match'],
    'i18n-locale-sort': ['i18n', 'sort', 'locale', 'collator', 'natural'],
    'i18n-message-format': ['i18n', 'message', 'format', 'placeholder', 'icu'],
    'i18n-number': ['i18n', 'number', 'format', 'Intl', 'grouping'],
    'i18n-ordinal': ['i18n', 'ordinal', '1st', 'suffix', 'pluralrules'],
    'i18n-percent': ['i18n', 'percent', 'format', 'ratio', 'Intl'],
    'i18n-pluralize-rules': ['i18n', 'plural', 'pluralrules', 'locale', 'count'],
    'i18n-relative-time': ['i18n', 'relative-time', 'ago', 'Intl', 'delta'],
    'i18n-rtl': ['i18n', 'rtl', 'ltr', 'direction', 'bidi'],
    'i18n-surrogates': ['i18n', 'surrogate', 'slice', 'unicode', 'safe'],
    'i18n-text-direction': ['i18n', 'direction', 'bidi', 'rtl', 'classify'],
    'i18n-timezone-list': ['i18n', 'timezone', 'iana', 'list', 'Intl'],
    'i18n-unit': ['i18n', 'unit', 'format', 'Intl', 'measurement'],
    'i18n-week-start': ['i18n', 'week', 'calendar', 'start-day'],
    'llm-batch-collector': ['llm', 'batch', 'collect', 'queue', 'latency'],
    'llm-chat-memory': ['llm', 'memory', 'ring', 'buffer', 'history', 'context'],
    'llm-context-assembler': ['llm', 'context', 'assemble', 'messages', 'budget'],
    'llm-conversation-summarizer': ['llm', 'summary', 'history', 'condense', 'context'],
    'llm-dedupe': ['llm', 'dedupe', 'similarity', 'filter', 'duplicate'],
    'llm-doc-chunker': ['llm', 'chunk', 'split', 'overlap', 'embedding', 'rag'],
    'llm-embedding-cache': ['llm', 'embedding', 'cache', 'lru', 'hash'],
    'llm-fence-checker': ['llm', 'adherence', 'fence', 'validate', 'format'],
    'llm-history-window': ['llm', 'history', 'window', 'slide', 'turns'],
    'llm-hybrid-fusion': ['llm', 'hybrid', 'bm25', 'vector', 'fusion', 'rag'],
    'llm-json-extractor': ['llm', 'json', 'parse', 'extract', 'fence'],
    'llm-prompt-template': ['llm', 'prompt', 'template', 'render', 'placeholder'],
    'llm-prompt-trimmer': ['llm', 'trim', 'budget', 'context', 'max-tokens'],
    'llm-rag-retriever': ['llm', 'rag', 'retriever', 'topk', 'embedding', 'search'],
    'llm-reflection-loop': ['llm', 'reflection', 'critique', 'revise', 'loop'],
    'llm-rerank-fusion': ['llm', 'rerank', 'fusion', 'score', 'ranking'],
    'llm-sampling-config': ['llm', 'sampling', 'temperature', 'topp', 'config'],
    'llm-sources-formatter': ['llm', 'sources', 'format', 'citation', 'answer'],
    'llm-stop-detector': ['llm', 'stop', 'sequence', 'stream', 'detector'],
    'llm-stream-accumulator': ['llm', 'stream', 'accumulator', 'chunk', 'delta'],
    'llm-token-estimate': ['llm', 'token', 'estimate', 'budget', 'count'],
    'llm-tool-call-parser': ['llm', 'tool', 'function', 'call', 'parse'],
    'llm-tool-dispatcher': ['llm', 'tool', 'dispatch', 'registry', 'handler'],
    'llm-usage-tracker': ['llm', 'usage', 'token', 'budget', 'tracker'],
    'llm-vector-ranker': ['llm', 'vector', 'ranker', 'cosine', 'similarity'],
    'logic-alpha-beta': ['alpha', 'beta', 'pruning', 'minimax', 'search'],
    'logic-astar': ['astar', 'pathfinding', 'grid', 'search', 'heuristic'],
    'logic-bfs': ['bfs', 'breadth', 'search', 'graph', 'level'],
    'logic-cellular-auto': ['cellular', 'automata', 'life', 'simulation', 'grid'],
    'logic-chess-movegen': ['chess', 'move', 'generation', 'board', 'pieces'],
    'logic-connect4': ['connect4', 'gravity', 'win', 'column', 'board'],
    'logic-dfs': ['dfs', 'depth', 'search', 'graph', 'cycle'],
    'logic-dijkstra': ['dijkstra', 'shortest', 'path', 'graph', 'weighted'],
    'logic-fen-parse': ['fen', 'chess', 'board', 'parse', 'position'],
    'logic-graph-adjacency': ['graph', 'adjacency', 'nodes', 'edges', 'topology'],
    'logic-heap': ['heap', 'priority', 'queue', 'binary', 'minmax'],
    'logic-huffman': ['huffman', 'compress', 'encode', 'decode', 'tree'],
    'logic-infix-eval': ['math', 'evaluate', 'expression', 'parser', 'calculator'],
    'logic-knapsack': ['knapsack', 'dynamic', 'programming', 'optimization', 'weight'],
    'logic-maze-gen': ['maze', 'generate', 'procedural', 'backtracking', 'grid'],
    'logic-mergesort': ['sort', 'mergesort', 'stable', 'divide', 'conquer'],
    'logic-minimax': ['minimax', 'ai', 'search', 'game', 'adversarial'],
    'logic-nqueens': ['nqueens', 'backtracking', 'queens', 'constraint', 'search'],
    'logic-prime-sieve': ['prime', 'sieve', 'number', 'math', 'primes'],
    'logic-quicksort': ['sort', 'quicksort', 'partition', 'algorithm', 'compare'],
    'logic-regex-match': ['regex', 'glob', 'wildcard', 'match', 'pattern'],
    'logic-shuffle': ['shuffle', 'random', 'fisher', 'yates', 'order'],
    'logic-sudoku-solve': ['sudoku', 'solve', 'backtracking', 'grid', 'puzzle'],
    'logic-tictactoe': ['tictactoe', 'win', 'check', 'board', '3x3'],
    'logic-tokenizer': ['tokenizer', 'lexer', 'parse', 'tokens', 'source'],
    'logic-trie': ['trie', 'prefix', 'autocomplete', 'search', 'dictionary'],
    'media-audio-player': ['audio', 'player', 'play', 'pause', 'seek'],
    'media-audio-recorder': ['record', 'microphone', 'audio', 'media', 'capture'],
    'media-audio-visualizer': ['visualizer', 'frequency', 'fft', 'analyser', 'bars'],
    'media-canvas-resize': ['resize', 'image', 'canvas', 'thumbnail', 'scale'],
    'media-clip-trim': ['trim', 'clip', 'in', 'out', 'timeline'],
    'media-color-quantize': ['quantize', 'palette', 'colors', 'pixel', 'gif'],
    'media-frame-extractor': ['video', 'frame', 'thumbnail', 'extract', 'capture'],
    'media-image-filters': ['filter', 'image', 'grayscale', 'sepia', 'pixel'],
    'media-metadata-reader': ['metadata', 'audio', 'tags', 'duration', 'music'],
    'media-playlist': ['playlist', 'queue', 'shuffle', 'repeat', 'music'],
    'media-slideshow': ['slideshow', 'slide', 'timer', 'advance', 'carousel'],
    'media-sprite-sheet': ['sprite', 'sheet', 'animation', 'frames', 'fps'],
    'media-video-player': ['video', 'player', 'playback', 'controls', 'element'],
    'media-waveform': ['waveform', 'audio', 'visualize', 'canvas', 'peaks'],
    'ml-auc-threshold': ['ml', 'roc', 'auc', 'threshold', 'evaluation'],
    'ml-confusion-matrix': ['ml', 'confusion', 'matrix', 'evaluation', 'tp', 'fp'],
    'ml-cooccurrence': ['ml', 'cooccurrence', 'nlp', 'context', 'word'],
    'ml-correlation': ['ml', 'correlation', 'pearson', 'statistics', 'association'],
    'ml-cosine-sim': ['ml', 'cosine', 'similarity', 'vector', 'dot-product'],
    'ml-decision-tree': ['ml', 'decision-tree', 'id3', 'entropy', 'classifier'],
    'ml-distance': ['ml', 'distance', 'euclidean', 'manhattan', 'haversine'],
    'ml-feature-hash': ['ml', 'feature', 'hash', 'hashing-trick', 'encoding'],
    'ml-gradient-descent': ['ml', 'gradient', 'descent', 'optimizer', 'sgd'],
    'ml-kfold': ['ml', 'kfold', 'cross-validation', 'folds', 'evaluation'],
    'ml-kmeans': ['ml', 'kmeans', 'cluster', 'centroid', 'unsupervised'],
    'ml-knn': ['ml', 'knn', 'classifier', 'distance', 'vote'],
    'ml-linear-regression': ['ml', 'linear', 'regression', 'least-squares', 'fit', 'predict'],
    'ml-logistic-regression': ['ml', 'logistic', 'sigmoid', 'sgd', 'probability'],
    'ml-naive-bayes': ['ml', 'naive-bayes', 'bayes', 'gaussian', 'probabilistic'],
    'ml-normalizer': ['ml', 'normalize', 'minmax', 'zscore', 'scale', 'preprocess'],
    'ml-one-hot': ['ml', 'one-hot', 'encode', 'categorical', 'feature'],
    'ml-pca': ['ml', 'pca', 'dimensionality', 'reduction', 'projection', 'eigenvector'],
    'ml-perceptron': ['ml', 'perceptron', 'linear', 'classifier', 'online'],
    'ml-prf': ['ml', 'precision', 'recall', 'f1', 'metrics', 'score'],
    'ml-rolling-mean': ['ml', 'rolling', 'mean', 'ema', 'smooth', 'time-series'],
    'ml-sgd-update': ['ml', 'sgd', 'online', 'update', 'streaming'],
    'ml-stratified-sample': ['ml', 'stratified', 'sample', 'imbalanced', 'resample'],
    'ml-tfidf': ['ml', 'tfidf', 'tf-idf', 'vectorize', 'retrieval', 'nlp'],
    'ml-train-test-split': ['ml', 'split', 'train', 'test', 'seed', 'shuffle'],
    'mob-app-state': ['mob', 'app-state', 'background', 'foreground', 'monitor'],
    'mob-battery': ['mob', 'battery', 'status', 'level', 'listener'],
    'mob-biometric': ['mob', 'biometric', 'auth', 'webauthn', 'face-id'],
    'mob-camera': ['mob', 'camera', 'capture', 'photo', 'video'],
    'mob-deep-link': ['mob', 'deep-link', 'parse', 'scheme', 'universal'],
    'mob-haptics': ['mob', 'haptic', 'vibrate', 'feedback', 'touch'],
    'mob-image-picker': ['mob', 'image', 'picker', 'upload', 'select'],
    'mob-keyboard': ['mob', 'keyboard', 'viewport', 'resize', 'input'],
    'mob-network-required': ['mob', 'network', 'offline', 'guard', 'online'],
    'mob-notif-schedule': ['mob', 'notification', 'schedule', 'reminder', 'local'],
    'mob-offline-queue': ['mob', 'offline', 'queue', 'sync', 'persist'],
    'mob-orientation': ['mob', 'orientation', 'lock', 'landscape', 'screen'],
    'mob-permissions': ['mob', 'permissions', 'geolocation', 'camera', 'request'],
    'mob-platform': ['mob', 'platform', 'ios', 'android', 'detect'],
    'mob-pull-refresh': ['mob', 'pull', 'refresh', 'gesture', 'touch'],
    'mob-reader-mode': ['mob', 'reader', 'extract', 'text', 'article'],
    'mob-responsive-font': ['mob', 'responsive', 'font', 'scale', 'viewport'],
    'mob-safe-area': ['mob', 'safe-area', 'inset', 'notch', 'layout'],
    'mob-screen-brightness': ['mob', 'wakelock', 'screen', 'awake', 'video'],
    'mob-session-restore': ['mob', 'session', 'restore', 'persist', 'state'],
    'mob-share': ['mob', 'share', 'native', 'sheet', 'web-share'],
    'mob-swipe': ['mob', 'swipe', 'gesture', 'touch', 'detect'],
    'mob-version-check': ['mob', 'version', 'update', 'stale', 'check'],
    'mob-viewport-meta': ['mob', 'viewport', 'meta', 'zoom', 'canvas'],
    'msg-at-least-once': ['msg', 'ack', 'at-least-once', 'redelivery', 'timeout'],
    'msg-channel-mux': ['msg', 'multiplex', 'channel', 'merge', 'fan-in'],
    'msg-compacted-topic': ['msg', 'compact', 'topic', 'key', 'latest'],
    'msg-consumer-lag': ['msg', 'lag', 'consumer', 'monitor', 'offset'],
    'msg-dead-letter-alert': ['msg', 'dead-letter', 'alert', 'threshold', 'monitor'],
    'msg-delay-queue': ['msg', 'delay', 'queue', 'schedule', 'timer'],
    'msg-event-replay': ['msg', 'replay', 'events', 'projection', 'rebuild'],
    'msg-event-store': ['msg', 'event-store', 'append', 'replay', 'log'],
    'msg-event-versioning': ['msg', 'event', 'version', 'schema', 'migration'],
    'msg-exactly-once': ['msg', 'exactly-once', 'dedupe', 'idempotent', 'cache'],
    'msg-fan-in': ['msg', 'fan-in', 'aggregate', 'collect', 'workers'],
    'msg-group-consumer': ['msg', 'group', 'consumer', 'partition', 'membership'],
    'msg-idempotent-consumer': ['msg', 'idempotent', 'dedupe', 'consumer', 'delivery'],
    'msg-message-envelope': ['msg', 'envelope', 'message', 'metadata', 'trace'],
    'msg-ordered-consumer': ['msg', 'ordered', 'partition', 'consumer', 'fifo'],
    'msg-poison-message': ['msg', 'poison', 'retry', 'quarantine', 'dead-letter'],
    'msg-priority-queue': ['msg', 'priority', 'queue', 'ordering'],
    'msg-req-reply': ['msg', 'request-reply', 'correlation', 'promise', 'async'],
    'msg-routing-bus': ['msg', 'routing', 'bus', 'wildcard', 'topic'],
    'msg-schema-registry': ['msg', 'schema', 'registry', 'validate', 'version'],
    'msg-subscription-checkpoint': ['msg', 'checkpoint', 'offset', 'subscription', 'resume'],
    'msg-topic-partitioner': ['msg', 'partition', 'topic', 'hash', 'ordering'],
    'msg-transactional': ['msg', 'transactional', 'commit', 'rollback', 'batch'],
    'msg-webhook-dispatch': ['msg', 'webhook', 'dispatch', 'retry', 'delivery'],
    'msg-window-agg': ['msg', 'window', 'aggregate', 'stream', 'sliding'],
    'mth-angle': ['mth', 'angle', 'radians', 'degrees', 'normalize'],
    'mth-base-convert': ['mth', 'base', 'convert', 'radix', 'encoding'],
    'mth-bit-ops': ['mth', 'bit', 'mask', 'flags', 'binary'],
    'mth-combinatorics': ['mth', 'combinatorics', 'ncr', 'factorial', 'permutation'],
    'mth-complex': ['mth', 'complex', 'number', 'imaginary', 'math'],
    'mth-decimal': ['mth', 'decimal', 'precision', 'money', 'round'],
    'mth-distributions': ['mth', 'random', 'distribution', 'normal', 'triangular'],
    'mth-fib-fast': ['mth', 'fibonacci', 'fast', 'doubling', 'bigint'],
    'mth-gcd-lcm': ['mth', 'gcd', 'lcm', 'euclid', 'number-theory'],
    'mth-integrate': ['mth', 'integrate', 'trapezoid', 'simpson', 'calculus'],
    'mth-interp': ['mth', 'lerp', 'remap', 'clamp', 'interpolate'],
    'mth-linear-solve': ['mth', 'linear', 'solve', 'cramer', 'system'],
    'mth-matrix': ['mth', 'matrix', 'multiply', 'linear', 'algebra'],
    'mth-metrics': ['mth', 'distance', 'metric', 'euclidean', 'minkowski'],
    'mth-mod-exp': ['mth', 'modular', 'exponent', 'power', 'crypto'],
    'mth-polynomial': ['mth', 'polynomial', 'horner', 'evaluate', 'coeff'],
    'mth-prime-factor': ['mth', 'prime', 'factor', 'factorization', 'number'],
    'mth-prng': ['mth', 'prng', 'seed', 'deterministic', 'random'],
    'mth-quaternion': ['mth', 'quaternion', 'rotation', '3d', 'axis'],
    'mth-rational': ['mth', 'rational', 'fraction', 'arithmetic', 'exact'],
    'mth-roots': ['mth', 'roots', 'bisection', 'newton', 'solve'],
    'mth-series': ['mth', 'series', 'exp', 'ln', 'pi'],
    'mth-smoothstep': ['mth', 'smoothstep', 'hermite', 'easing', 'transition'],
    'mth-stats': ['mth', 'statistics', 'mean', 'variance', 'stddev'],
    'mth-ternary': ['mth', 'ternary', 'search', 'unimodal', 'optimize'],
    'mth-vector-ops': ['mth', 'vector', 'ndim', 'ops', 'math'],
    'net-dns-resolve': ['dns', 'resolve', 'hostname', 'ip', 'lookup'],
    'net-http-benchmark': ['benchmark', 'load', 'latency', 'throughput', 'test'],
    'net-http-client': ['http', 'client', 'request', 'node', 'fetch'],
    'net-ip-range': ['ip', 'cidr', 'subnet', 'range', 'network'],
    'net-ping': ['ping', 'latency', 'reachable', 'network', 'probe'],
    'net-port-scanner': ['port', 'scan', 'open', 'network', 'discover'],
    'net-proxy': ['proxy', 'forward', 'http', 'tunnel', 'relay'],
    'net-tcp-client': ['tcp', 'client', 'socket', 'connect', 'send'],
    'net-tcp-server': ['tcp', 'server', 'socket', 'listen', 'protocol'],
    'net-ws-client': ['websocket', 'client', 'socket', 'realtime', 'node'],
    'obs-alert-check': ['obs', 'alert', 'threshold', 'hysteresis', 'fire'],
    'obs-cardinality': ['obs', 'cardinality', 'distinct', 'count', 'unique'],
    'obs-correlation-id': ['obs', 'correlation', 'id', 'trace', 'middleware'],
    'obs-dlq': ['obs', 'dead-letter', 'queue', 'failed', 'tracker'],
    'obs-error-budget': ['obs', 'error', 'budget', 'slo', 'availability'],
    'obs-error-envelope': ['obs', 'error', 'envelope', 'structured', 'normalize'],
    'obs-health-json': ['obs', 'health', 'json', 'builder', 'status'],
    'obs-histogram': ['obs', 'histogram', 'bucket', 'distribution', 'latency'],
    'obs-json-logger': ['obs', 'log', 'json', 'structured', 'logger'],
    'obs-level-filter': ['obs', 'log', 'level', 'filter', 'threshold'],
    'obs-log-redact': ['obs', 'redact', 'log', 'pii', 'filter'],
    'obs-metrics-registry': ['obs', 'metrics', 'counter', 'gauge', 'registry'],
    'obs-percentile': ['obs', 'percentile', 'p95', 'p99', 'latency'],
    'obs-rate-counter': ['obs', 'rate', 'counter', 'events', 'per-second'],
    'obs-req-log': ['obs', 'request', 'log', 'access', 'format'],
    'obs-resource-meter': ['obs', 'resource', 'memory', 'cpu', 'meter'],
    'obs-sampler': ['obs', 'sampler', 'sample', 'rate', 'trace'],
    'obs-slo-check': ['obs', 'slo', 'conformance', 'check', 'target'],
    'obs-slow-reporter': ['obs', 'slow', 'reporter', 'threshold', 'performance'],
    'obs-timer': ['obs', 'timer', 'duration', 'latency', 'measure'],
    'obs-trace-span': ['obs', 'trace', 'span', 'start', 'end'],
    'obs-trend': ['obs', 'trend', 'slope', 'detector', 'regression'],
    'obs-uptime': ['obs', 'uptime', 'availability', 'tracker', 'health'],
    'obs-window-stats': ['obs', 'rolling', 'window', 'stats', 'aggregate'],
    'rtc-broadcast-channel': ['rtc', 'broadcast', 'channel', 'tabs', 'sync'],
    'rtc-changelog': ['rtc', 'changelog', 'append', 'merge', 'sync'],
    'rtc-cursors': ['rtc', 'cursor', 'live', 'presence', 'collab'],
    'rtc-delta-diff': ['rtc', 'delta', 'diff', 'compress', 'path'],
    'rtc-ewma-clock': ['rtc', 'clock', 'offset', 'skew', 'ntp'],
    'rtc-fanout': ['rtc', 'broadcast', 'fanout', 'delivery', 'send'],
    'rtc-gcounter': ['rtc', 'crdt', 'counter', 'gcounter', 'pncounter'],
    'rtc-gossip': ['rtc', 'gossip', 'merge', 'eventual', 'peers'],
    'rtc-lamport': ['rtc', 'lamport', 'clock', 'ordering', 'distributed'],
    'rtc-lww-register': ['rtc', 'crdt', 'lww', 'merge', 'last-writer-wins'],
    'rtc-merge-doc': ['rtc', 'merge', 'document', 'field', 'lww'],
    'rtc-orset': ['rtc', 'crdt', 'orset', 'set', 'tombstone'],
    'rtc-ot-text': ['rtc', 'ot', 'operational', 'transform', 'text'],
    'rtc-outbox': ['rtc', 'outbox', 'ack', 'delivery', 'reliable'],
    'rtc-ping-pong': ['rtc', 'ping', 'pong', 'keepalive', 'websocket'],
    'rtc-presence': ['rtc', 'presence', 'heartbeat', 'online', 'ttl'],
    'rtc-rate-limiter-dist': ['rtc', 'rate', 'limit', 'distributed', 'key'],
    'rtc-reconnect': ['rtc', 'reconnect', 'backoff', 'websocket', 'retry'],
    'rtc-retry-queue': ['rtc', 'retry', 'queue', 'persist', 'outbox'],
    'rtc-rooms': ['rtc', 'rooms', 'membership', 'join', 'broadcast'],
    'rtc-seq-alloc': ['rtc', 'sequence', 'allocator', 'monotonic', 'order'],
    'rtc-snapshot-sync': ['rtc', 'snapshot', 'sync', 'delta', 'bootstrap'],
    'rtc-sub-filter': ['rtc', 'subscribe', 'topic', 'filter', 'wildcard'],
    'rtc-sync-scheduler': ['rtc', 'sync', 'scheduler', 'push', 'pull'],
    'rtc-sync-state': ['rtc', 'sync', 'state', 'machine', 'status'],
    'rtc-version-vector': ['rtc', 'version', 'vector', 'causality', 'lamport'],
    'sec-account-lockout': ['sec', 'lockout', 'account', 'attempts', 'brute-force'],
    'sec-audit-writer': ['sec', 'audit', 'log', 'actor', 'trail'],
    'sec-cmd-block': ['sec', 'command', 'injection', 'shell', 'blocklist'],
    'sec-content-type': ['sec', 'content-type', 'allowlist', 'upload', 'mime'],
    'sec-cors-allow': ['sec', 'cors', 'origin', 'allowlist', 'headers'],
    'sec-csrf': ['sec', 'csrf', 'token', 'validate', 'constant-time'],
    'sec-email-validate': ['sec', 'email', 'validate', 'format', 'regex'],
    'sec-file-sniff': ['sec', 'file', 'sniff', 'magic', 'upload'],
    'sec-header-clean': ['sec', 'header', 'sanitize', 'crlf', 'injection'],
    'sec-html-escape': ['sec', 'html', 'escape', 'xss', 'sanitize'],
    'sec-input-limit': ['sec', 'input', 'length', 'limit', 'validate'],
    'sec-ip-limit': ['sec', 'ip', 'rate', 'limit', 'abuse'],
    'sec-mfa-verify': ['sec', 'mfa', 'otp', 'verify', '2fa'],
    'sec-password-meter': ['sec', 'password', 'strength', 'score', 'meter'],
    'sec-path-guard': ['sec', 'path', 'traversal', 'guard', 'directory'],
    'sec-payload-limit': ['sec', 'payload', 'size', 'limit', 'body'],
    'sec-rbac': ['sec', 'rbac', 'permission', 'role', 'authorization'],
    'sec-redirect-safe': ['sec', 'redirect', 'open-redirect', 'validate', 'url'],
    'sec-regex-guard': ['sec', 'regex', 'redos', 'guard', 'backtracking'],
    'sec-role-hierarchy': ['sec', 'role', 'hierarchy', 'inherit', 'resolve'],
    'sec-session-token': ['sec', 'session', 'token', 'generator', 'crypto'],
    'sec-sql-escape': ['sec', 'sql', 'escape', 'injection', 'string'],
    'sec-timing-safe': ['sec', 'timing', 'safe', 'compare', 'constant-time'],
    'sec-url-scheme': ['sec', 'url', 'scheme', 'allowlist', 'redirect'],
    'state-async-generator': ['async', 'generator', 'stream', 'iterator', 'producer'],
    'state-atomic-counter': ['counter', 'atomic', 'id', 'unique', 'sequence'],
    'state-backoff-retry': ['retry', 'backoff', 'exponential', 'jitter', 'resilience'],
    'state-cancellation-token': ['cancel', 'abort', 'async', 'token', 'unmount'],
    'state-crdt-lww': ['crdt', 'merge', 'conflict', 'offline', 'sync'],
    'state-create-store': ['store', 'state', 'subscribe', 'observer', 'reactive'],
    'state-debounce': ['debounce', 'delay', 'timer', 'search', 'performance'],
    'state-event-emitter': ['emitter', 'events', 'listener', 'publish', 'observer'],
    'state-finite-machine': ['fsm', 'state machine', 'transitions', 'guard', 'wizard'],
    'state-idle-timer': ['idle', 'timeout', 'activity', 'presence', 'lock'],
    'state-local-storage': ['localstorage', 'persist', 'storage', 'serialize', 'json'],
    'state-lru-cache': ['lru', 'cache', 'memory', 'eviction', 'performance'],
    'state-memo-selector': ['memo', 'selector', 'cache', 'derived', 'performance'],
    'state-optimistic-update': ['optimistic', 'optimisticui', 'rollback', 'snapshot', 'mutation'],
    'state-polling-hook': ['polling', 'interval', 'refresh', 'hook', 'fetch'],
    'state-pubsub-bus': ['pubsub', 'bus', 'topics', 'decouple', 'messaging'],
    'state-queue': ['queue', 'fifo', 'worker', 'async', 'tasks'],
    'state-reducer': ['reducer', 'action', 'state', 'pure', 'redux'],
    'state-session-store': ['session', 'storage', 'persist', 'tab'],
    'state-signal-slot': ['signal', 'slot', 'callback', 'typed', 'connect'],
    'state-throttle': ['throttle', 'rate', 'limit', 'scroll', 'performance'],
    'state-ttl-cache': ['ttl', 'cache', 'expiry', 'timeout', 'session'],
    'state-undo-stack': ['undo', 'redo', 'history', 'stack', 'editor'],
    'state-websocket-hook': ['websocket', 'socket', 'hook', 'realtime', 'reconnect'],
    'str-case-converter': ['str', 'case', 'camel', 'snake', 'kebab', 'pascal'],
    'str-compact-whitespace': ['str', 'whitespace', 'collapse', 'trim', 'normalize'],
    'str-delimiter-join': ['str', 'join', 'split', 'delimiter', 'concat'],
    'str-diacritics': ['str', 'diacritics', 'accents', 'normalize', 'search'],
    'str-email-mask': ['str', 'email', 'mask', 'pii', 'privacy'],
    'str-glob-match': ['str', 'glob', 'pattern', 'match', 'path'],
    'str-indent': ['str', 'indent', 'block', 'format'],
    'str-initials': ['str', 'initials', 'abbreviation', 'avatar', 'acronym'],
    'str-interleave': ['str', 'interleave', 'merge', 'zip'],
    'str-json-beautify': ['str', 'json', 'beautify', 'pretty', 'format'],
    'str-levenshtein': ['str', 'levenshtein', 'edit-distance', 'fuzzy', 'similarity'],
    'str-lorem': ['str', 'lorem', 'placeholder', 'generator', 'fixture'],
    'str-metaphone': ['str', 'metaphone', 'phonetic', 'fuzzy', 'english'],
    'str-natural-sort': ['str', 'sort', 'natural', 'numeric', 'comparator'],
    'str-number-words': ['str', 'number', 'words', 'spell', 'english'],
    'str-pad': ['str', 'pad', 'align', 'format'],
    'str-pluralize': ['str', 'plural', 'singular', 'inflection', 'english'],
    'str-roman-numerals': ['str', 'roman', 'numeral', 'convert'],
    'str-slugify': ['str', 'slug', 'url', 'normalize'],
    'str-soundex': ['str', 'soundex', 'phonetic', 'fuzzy', 'name'],
    'str-title-case': ['str', 'title', 'case', 'capitalize', 'heading'],
    'str-truncate': ['str', 'truncate', 'grapheme', 'unicode', 'ellipsis'],
    'str-unicode-normalize': ['str', 'unicode', 'normalize', 'nfc', 'nfkd'],
    'str-wildcard': ['str', 'wildcard', 'match', 'pattern', 'search'],
    'str-words-number': ['str', 'words', 'number', 'parse', 'english'],
    'sys-atomic-write': ['atomic', 'write', 'file', 'fsync', 'safe'],
    'sys-config-loader': ['config', 'loader', 'json', 'defaults', 'settings'],
    'sys-cron-scheduler': ['cron', 'schedule', 'job', 'timer', 'recurring'],
    'sys-daemonize': ['daemon', 'background', 'pidfile', 'fork', 'service'],
    'sys-dir-walker': ['directory', 'walk', 'recursive', 'files', 'scan'],
    'sys-file-watcher': ['file', 'watch', 'fs', 'reload', 'debounce'],
    'sys-job-queue': ['queue', 'job', 'worker', 'retry', 'persist'],
    'sys-lock-file': ['lock', 'mutex', 'file', 'exclusive', 'concurrency'],
    'sys-logger': ['log', 'logger', 'structured', 'json', 'levels'],
    'sys-memory-meter': ['memory', 'cpu', 'meter', 'monitor', 'rss'],
    'sys-process-spawn': ['process', 'spawn', 'child', 'exec', 'shell'],
    'sys-signal-handler': ['signal', 'shutdown', 'graceful', 'sigint', 'sigterm'],
    'sys-temp-dir': ['temp', 'tmp', 'directory', 'cleanup', 'filesystem'],
    'test-assert': ['test', 'assert', 'deepequal', 'throws', 'matcher'],
    'test-benchmark': ['test', 'benchmark', 'perf', 'ops', 'timing'],
    'test-contract-assert': ['test', 'contract', 'shape', 'schema', 'validate'],
    'test-coverage-map': ['test', 'coverage', 'branch', 'tracker', 'percent'],
    'test-dom-query': ['test', 'dom', 'query', 'getby', 'role'],
    'test-eventually': ['test', 'async', 'eventually', 'wait', 'poll'],
    'test-fake-network': ['test', 'network', 'fake', 'latency', 'fault'],
    'test-fake-timers': ['test', 'timers', 'fake', 'clock', 'deterministic'],
    'test-fixture-load': ['test', 'fixture', 'load', 'cache', 'data'],
    'test-fuzz-input': ['test', 'fuzz', 'input', 'mutation', 'hostile'],
    'test-leak-detector': ['test', 'leak', 'detector', 'listener', 'interval'],
    'test-matrix': ['test', 'matrix', 'combinations', 'cases', 'cartesian'],
    'test-mock-fn': ['test', 'mock', 'stub', 'recorder', 'spy'],
    'test-name-format': ['test', 'name', 'describe', 'format', 'hierarchy'],
    'test-pairwise': ['test', 'pairwise', 'combinatorial', 'cover', 'design'],
    'test-property-check': ['test', 'property', 'fuzz', 'generator', 'random'],
    'test-record-eq': ['test', 'equal', 'partial', 'subset', 'matcher'],
    'test-retry-flaky': ['test', 'flaky', 'retry', 'stable', 'rerun'],
    'test-seed-harness': ['test', 'seed', 'random', 'harness', 'reproducible'],
    'test-skip-filter': ['test', 'skip', 'only', 'filter', 'pattern'],
    'test-snapshot': ['test', 'snapshot', 'compare', 'golden', 'diff'],
    'test-stub-server': ['test', 'stub', 'server', 'http', 'mock'],
    'test-tap-reporter': ['test', 'tap', 'reporter', 'output', 'ci'],
    'test-threshold-sweep': ['test', 'threshold', 'sweep', 'bisect', 'search'],
    'test-time-window': ['test', 'time', 'window', 'timestamp', 'tolerance'],
    'time-age': ['time', 'age', 'birthday', 'years', 'date'],
    'time-business-days': ['time', 'business', 'workday', 'calendar', 'holiday'],
    'time-countdown-until': ['time', 'countdown', 'timer', 'remaining', 'tick'],
    'time-date-range': ['time', 'range', 'iterator', 'days', 'generate'],
    'time-dst-safe': ['time', 'dst', 'date-math', 'calendar', 'add-days'],
    'time-duration-human': ['time', 'duration', 'human', 'format', 'ms'],
    'time-duration-parse': ['time', 'duration', 'iso8601', 'parse', 'ms'],
    'time-elapsed-format': ['time', 'elapsed', 'format', 'mmss', 'timer'],
    'time-epoch': ['time', 'epoch', 'unix', 'convert', 'timestamp'],
    'time-first-last-day': ['time', 'month', 'first', 'last', 'boundary'],
    'time-frac-seconds': ['time', 'fractional', 'seconds', 'format', 'precision'],
    'time-half-open': ['time', 'interval', 'half-open', 'overlap', 'contains'],
    'time-interval-align': ['time', 'interval', 'align', 'bucket', 'round'],
    'time-iso-week': ['time', 'iso', 'week', 'calendar', 'date'],
    'time-lap-stopwatch': ['time', 'stopwatch', 'lap', 'timer', 'measure'],
    'time-leap-year': ['time', 'leap-year', 'days-in-month', 'calendar'],
    'time-monotonic': ['time', 'monotonic', 'clock', 'elapsed', 'performance'],
    'time-next-birthday': ['time', 'birthday', 'anniversary', 'next', 'date'],
    'time-quarter': ['time', 'quarter', 'fiscal', 'year', 'date'],
    'time-round-time': ['time', 'round', 'interval', 'minutes', 'nearest'],
    'time-rrule': ['time', 'recurrence', 'rrule', 'calendar', 'schedule'],
    'time-schedule-next': ['time', 'schedule', 'next', 'fire', 'cron'],
    'time-timezone-convert': ['time', 'timezone', 'convert', 'intl', 'wall-clock'],
    'time-utc-offset': ['time', 'utc', 'offset', 'timezone', 'dst'],
    'time-working-hours': ['time', 'working-hours', 'shift', 'business', 'check'],
    'ui-accordion': ['accordion', 'collapse', 'expand', 'faq', 'sections'],
    'ui-avatar': ['avatar', 'profile', 'image', 'user'],
    'ui-badge': ['badge', 'pill', 'tag', 'status', 'label'],
    'ui-breadcrumb': ['breadcrumb', 'navigation', 'path', 'trail'],
    'ui-calendar-grid': ['calendar', 'date', 'month', 'grid', 'picker'],
    'ui-carousel': ['carousel', 'slideshow', 'gallery', 'slider'],
    'ui-chart-bar': ['chart', 'bar', 'histogram', 'visualization'],
    'ui-chart-line': ['chart', 'line', 'plot', 'graph', 'svg', 'visualization'],
    'ui-chart-pie': ['chart', 'pie', 'donut', 'proportion', 'visualization'],
    'ui-code-editor': ['editor', 'code', 'textarea', 'monospace'],
    'ui-color-picker': ['color', 'picker', 'palette', 'input'],
    'ui-context-menu': ['context', 'menu', 'rightclick', 'actions'],
    'ui-data-table': ['table', 'grid', 'rows', 'columns', 'sort'],
    'ui-drag-drop-list': ['drag', 'drop', 'reorder', 'list', 'sort'],
    'ui-dropdown-menu': ['dropdown', 'select', 'menu', 'options'],
    'ui-empty-state': ['empty', 'state', 'placeholder', 'no results'],
    'ui-file-dropzone': ['file', 'upload', 'dropzone', 'drag', 'dragdrop'],
    'ui-form-builder': ['form', 'builder', 'schema', 'fields', 'dynamic'],
    'ui-infinite-scroll': ['infinite', 'scroll', 'feed', 'lazy', 'intersection'],
    'ui-kanban-card': ['kanban', 'board', 'card', 'drag', 'agile'],
    'ui-loading-spinner': ['loading', 'spinner', 'loader', 'skeleton'],
    'ui-login-form': ['login', 'auth', 'form', 'email', 'password', 'authentication'],
    'ui-markdown-renderer': ['markdown', 'renderer', 'html', 'docs', 'content'],
    'ui-modal-dialog': ['modal', 'dialog', 'overlay', 'popup', 'focus'],
    'ui-pagination-bar': ['pagination', 'pager', 'pages', 'navigation'],
    'ui-progress-bar': ['progress', 'percent', 'loading', 'bar'],
    'ui-search-input': ['search', 'input', 'query', 'filter'],
    'ui-signup-form': ['signup', 'registration', 'form', 'validation', 'auth'],
    'ui-slider-input': ['slider', 'range', 'input', 'number'],
    'ui-stat-card': ['stat', 'kpi', 'metric', 'dashboard', 'card'],
    'ui-tab-bar': ['tabs', 'navigation', 'panel', 'view'],
    'ui-timeline': ['timeline', 'history', 'events', 'feed', 'activity'],
    'ui-toast-notification': ['toast', 'notification', 'snackbar', 'message'],
    'ui-todo-item': ['todo', 'task', 'list', 'checkbox', 'item'],
    'ui-toggle-switch': ['toggle', 'switch', 'checkbox', 'boolean', 'settings'],
    'ui-tooltip': ['tooltip', 'hover', 'hint', 'popover'],
    'viz-animate-frame': ['viz', 'animation', 'easing', 'frame', 'interpolate'],
    'viz-area-points': ['viz', 'area', 'path', 'polygon', 'chart'],
    'viz-arrow-head': ['viz', 'arrow', 'angle', 'edge', 'directed'],
    'viz-axis-band': ['viz', 'band', 'scale', 'categorical', 'axis'],
    'viz-bar-layout': ['viz', 'bar', 'layout', 'chart', 'position'],
    'viz-bin-histo': ['viz', 'histogram', 'bin', 'distribution', 'count'],
    'viz-brush-range': ['viz', 'brush', 'range', 'select', 'clamp'],
    'viz-bubble-size': ['viz', 'bubble', 'radius', 'size', 'scale'],
    'viz-color-scale': ['viz', 'color', 'scale', 'interpolate', 'gradient'],
    'viz-force-layout': ['viz', 'force', 'layout', 'graph', 'physics'],
    'viz-heatmap-index': ['viz', 'heatmap', 'color', 'ramp', 'index'],
    'viz-hierarchy-tree': ['viz', 'tree', 'hierarchy', 'layout', 'position'],
    'viz-label-collision': ['viz', 'label', 'collision', 'overlap', 'layout'],
    'viz-linear-scale': ['viz', 'scale', 'linear', 'axis', 'chart'],
    'viz-log-scale': ['viz', 'log', 'scale', 'domain', 'chart'],
    'viz-pie-slices': ['viz', 'pie', 'donut', 'slice', 'angle'],
    'viz-polar': ['viz', 'polar', 'cartesian', 'radar', 'transform'],
    'viz-quad-tree': ['viz', 'spatial', 'grid', 'index', 'query'],
    'viz-sankey-flow': ['viz', 'sankey', 'flow', 'layout', 'nodes'],
    'viz-smoothed-line': ['viz', 'smooth', 'curve', 'catmull', 'line'],
    'viz-stack-series': ['viz', 'stack', 'series', 'area', 'layout'],
    'viz-ticks': ['viz', 'ticks', 'axis', 'scale', 'nice'],
    'viz-time-format': ['viz', 'time', 'axis', 'format', 'chart'],
    'viz-waterfall-delta': ['viz', 'waterfall', 'delta', 'cascade', 'chart'],
    'viz-x-ticks': ['viz', 'ticks', 'categorical', 'axis', 'labels'],
};
const NODE_TYPE_TO_BIBLE_LEVELS = {
    input: ['01-foundations', '04-web-apps', '05-systems-programming', '13-networking-deep', '34-api-integration-platforms', '29-emerging-tech', 'data-id-generator', 'data-schema-validator', 'data-json-file-store', 'data-binary-search', 'logic-regex-match', 'api-body-parser', 'state-debounce', 'data-csv-parse', 'brw-audio-unlock', 'brw-clipboard', 'brw-cookie', 'brw-debounce-resize', 'brw-dom-ready', 'acc-announce', 'acc-aria-expanded', 'acc-assist-label', 'acc-contrast', 'acc-dialog-wiring', 'embed-avg-filter', 'embed-baud-rate', 'embed-bit-crc16', 'embed-bitfield', 'embed-boot-check'],
    output: ['01-foundations', '04-web-apps', '08-computer-graphics', '21-digital-content-media', '40-media-entertainment-social', 'ui-data-table', 'ui-chart-line', 'ui-chart-bar', 'ui-chart-pie', 'ui-markdown-renderer', 'ui-pagination-bar', 'ui-toast-notification', 'media-canvas-resize', 'ui-progress-bar', 'brw-audio-unlock', 'brw-clipboard', 'brw-cookie', 'brw-debounce-resize', 'brw-dom-ready', 'mob-app-state', 'mob-battery', 'mob-biometric', 'mob-camera', 'mob-deep-link', 'gfx-arc', 'gfx-aspect-fit', 'gfx-bezier', 'gfx-blur', 'gfx-camera', 'rtc-broadcast-channel', 'rtc-changelog', 'rtc-cursors', 'rtc-delta-diff', 'rtc-ewma-clock', 'str-case-converter', 'str-compact-whitespace', 'str-delimiter-join', 'str-diacritics', 'str-email-mask', 'acc-announce', 'acc-aria-expanded', 'acc-assist-label', 'acc-contrast', 'acc-dialog-wiring', 'i18n-bidi', 'i18n-calendar', 'i18n-collate', 'i18n-compact', 'i18n-currency', 'viz-animate-frame', 'viz-area-points', 'viz-arrow-head', 'viz-axis-band', 'viz-bar-layout'],
    logic: ['01-foundations', '07-ai-ml', '12-distributed-systems', '05-design-patterns', '06-data-flow-patterns', '02-games', '37-aiml-platforms-llmops', '19-formal-methods-tools', 'state-finite-machine', 'state-reducer', 'state-undo-stack', 'logic-minimax', 'logic-alpha-beta', 'logic-astar', 'logic-bfs', 'logic-dfs', 'logic-quicksort', 'logic-heap', 'logic-trie', 'logic-fen-parse', 'logic-sudoku-solve', 'logic-maze-gen', 'logic-cellular-auto', 'state-lru-cache', 'state-memo-selector', 'logic-knapsack', 'logic-nqueens', 'state-queue', 'ml-auc-threshold', 'ml-confusion-matrix', 'ml-cooccurrence', 'ml-correlation', 'ml-cosine-sim', 'llm-batch-collector', 'llm-chat-memory', 'llm-context-assembler', 'llm-conversation-summarizer', 'llm-dedupe', 'test-assert', 'test-benchmark', 'test-contract-assert', 'test-coverage-map', 'test-dom-query', 'mth-angle', 'mth-base-convert', 'mth-bit-ops', 'mth-combinatorics', 'mth-complex', 'alg-bellman-ford', 'alg-bipartite', 'alg-bucket-sort', 'alg-counting-sort', 'alg-crt', 'str-case-converter', 'str-compact-whitespace', 'str-delimiter-join', 'str-diacritics', 'str-email-mask', 'col-avltree', 'col-capacity-set', 'col-chunker', 'col-difference-array', 'col-fenwick', 'time-age', 'time-business-days', 'time-countdown-until', 'time-date-range', 'time-dst-safe', 'fin-amortization', 'fin-annuity-fv', 'fin-bill-due', 'fin-budget-category', 'fin-capm', 'edu-answer-feedback', 'edu-badge-progress', 'edu-cloze-check', 'edu-confidence-rating', 'edu-flashcard-deck', 'embed-avg-filter', 'embed-baud-rate', 'embed-bit-crc16', 'embed-bitfield', 'embed-boot-check'],
    api: ['04-web-apps', '34-api-integration-platforms', '14-protocols', '10-security', '13-networking-deep', '38-fintech-insurance', '40-media-entertainment-social', 'api-http-server', 'api-rest-router', 'api-json-response', 'api-error-handler', 'api-auth-middleware', 'api-jwt-sign', 'api-jwt-verify', 'api-rate-limiter', 'api-cors-middleware', 'api-body-parser', 'api-webhook-receiver', 'api-graphql-resolver', 'api-ws-server', 'api-sse-emitter', 'api-http-client', 'api-paginated-response', 'api-health-check', 'api-idempotency', 'api-config-loader', 'api-request-logger', 'fs-recent-files', 'llm-batch-collector', 'llm-chat-memory', 'llm-context-assembler', 'llm-conversation-summarizer', 'llm-dedupe', 'devops-archive-keep', 'devops-backoff-retry', 'devops-changelog-parse', 'devops-ci-matrix', 'devops-config-merge', 'db-audit-columns', 'db-batch-insert', 'db-connection-retry', 'db-counter-inc', 'db-cursor-codec', 'obs-alert-check', 'obs-cardinality', 'obs-correlation-id', 'obs-dlq', 'obs-error-budget', 'sec-account-lockout', 'sec-audit-writer', 'sec-cmd-block', 'sec-content-type', 'sec-cors-allow', 'rtc-broadcast-channel', 'rtc-changelog', 'rtc-cursors', 'rtc-delta-diff', 'rtc-ewma-clock', 'arch-adapter', 'arch-backpressure', 'arch-builder', 'arch-bulkhead', 'arch-chain-responsibility', 'fsys-atomic-rename', 'fsys-binary-header', 'fsys-buffered-writer', 'fsys-chunked-reader', 'msg-at-least-once', 'msg-channel-mux', 'msg-compacted-topic', 'msg-consumer-lag', 'msg-dead-letter-alert', 'http-accept-parse', 'http-basic-auth', 'http-bearer-token', 'http-cache-revalidate', 'http-chunked-decode', 'gen-arg-parser', 'gen-camel-case', 'gen-doc-comment', 'gen-env-default', 'gen-export-walk', 'cli-banner', 'cli-colorize', 'cli-command-router', 'cli-confirm-parse', 'cli-csv-quote'],
    database: ['06-databases', '11-database-internals', '27-data-engineering', '26-enterprise-systems', '29-emerging-tech', 'data-sqlite-connect', 'data-pg-pool', 'data-mongo-connect', 'data-repository-crud', 'data-migration-runner', 'data-query-builder', 'data-json-file-store', 'data-csv-parse', 'data-pagination-query', 'data-transaction', 'data-id-generator', 'data-indexeddb-store', 'data-vector-store', 'data-fulltext-index', 'data-event-log', 'data-blob-store', 'data-connection-pool', 'db-audit-columns', 'db-batch-insert', 'db-connection-retry', 'db-counter-inc', 'db-cursor-codec', 'obs-alert-check', 'obs-cardinality', 'obs-correlation-id', 'obs-dlq', 'obs-error-budget', 'sec-account-lockout', 'sec-audit-writer', 'sec-cmd-block', 'sec-content-type', 'sec-cors-allow', 'fin-amortization', 'fin-annuity-fv', 'fin-bill-due', 'fin-budget-category', 'fin-capm'],
    ui: ['03-desktop-apps', '22-browser-engineering', '08-computer-graphics', '31-mobile-cross-platform', '04-web-apps', '40-media-entertainment-social', 'ui-login-form', 'ui-signup-form', 'ui-modal-dialog', 'ui-toast-notification', 'ui-dropdown-menu', 'ui-tab-bar', 'ui-data-table', 'ui-search-input', 'ui-form-builder', 'ui-file-dropzone', 'ui-calendar-grid', 'ui-chart-line', 'ui-markdown-renderer', 'ui-code-editor', 'ui-drag-drop-list', 'ui-infinite-scroll', 'ui-context-menu', 'ui-carousel', 'ui-pagination-bar', 'ui-toggle-switch', 'ui-slider-input', 'ui-empty-state', 'ui-loading-spinner', 'sec-account-lockout', 'sec-audit-writer', 'sec-cmd-block', 'sec-content-type', 'sec-cors-allow', 'brw-audio-unlock', 'brw-clipboard', 'brw-cookie', 'brw-debounce-resize', 'brw-dom-ready', 'mob-app-state', 'mob-battery', 'mob-biometric', 'mob-camera', 'mob-deep-link', 'gfx-arc', 'gfx-aspect-fit', 'gfx-bezier', 'gfx-blur', 'gfx-camera', 'str-case-converter', 'str-compact-whitespace', 'str-delimiter-join', 'str-diacritics', 'str-email-mask', 'time-age', 'time-business-days', 'time-countdown-until', 'time-date-range', 'time-dst-safe', 'acc-announce', 'acc-aria-expanded', 'acc-assist-label', 'acc-contrast', 'acc-dialog-wiring', 'i18n-bidi', 'i18n-calendar', 'i18n-collate', 'i18n-compact', 'i18n-currency', 'fin-amortization', 'fin-annuity-fv', 'fin-bill-due', 'fin-budget-category', 'fin-capm', 'edu-answer-feedback', 'edu-badge-progress', 'edu-cloze-check', 'edu-confidence-rating', 'edu-flashcard-deck', 'viz-animate-frame', 'viz-area-points', 'viz-arrow-head', 'viz-axis-band', 'viz-bar-layout'],
    master: ['01-foundations', '07-llm-guide', '30-software-process', '16-computer-architecture', '32-cloud-native-infra', '33-devops-sre-tooling', '37-aiml-platforms-llmops', '19-formal-methods-tools', '29-emerging-tech', '42-education-learning', 'state-create-store', 'state-event-emitter', 'state-pubsub-bus', 'api-config-loader', 'sys-config-loader', 'sys-logger', 'sys-signal-handler', 'sys-job-queue', 'crypto-password-hash', 'api-health-check', 'sys-atomic-write', 'state-local-storage', 'fs-recent-files', 'ml-auc-threshold', 'ml-confusion-matrix', 'ml-cooccurrence', 'ml-correlation', 'ml-cosine-sim', 'llm-batch-collector', 'llm-chat-memory', 'llm-context-assembler', 'llm-conversation-summarizer', 'llm-dedupe', 'devops-archive-keep', 'devops-backoff-retry', 'devops-changelog-parse', 'devops-ci-matrix', 'devops-config-merge', 'obs-alert-check', 'obs-cardinality', 'obs-correlation-id', 'obs-dlq', 'obs-error-budget', 'test-assert', 'test-benchmark', 'test-contract-assert', 'test-coverage-map', 'test-dom-query', 'rtc-broadcast-channel', 'rtc-changelog', 'rtc-cursors', 'rtc-delta-diff', 'rtc-ewma-clock', 'alg-bellman-ford', 'alg-bipartite', 'alg-bucket-sort', 'alg-counting-sort', 'alg-crt', 'arch-adapter', 'arch-backpressure', 'arch-builder', 'arch-bulkhead', 'arch-chain-responsibility', 'fsys-atomic-rename', 'fsys-binary-header', 'fsys-buffered-writer', 'fsys-chunked-reader', 'msg-at-least-once', 'msg-channel-mux', 'msg-compacted-topic', 'msg-consumer-lag', 'msg-dead-letter-alert', 'gen-arg-parser', 'gen-camel-case', 'gen-doc-comment', 'gen-env-default', 'gen-export-walk', 'cli-banner', 'cli-colorize', 'cli-command-router', 'cli-confirm-parse', 'cli-csv-quote'],
};
const LANGUAGE_TO_BIBLE_LEVELS = {
    typescript: ['04-web-apps', '22-browser-engineering', '15-programming-languages', 'fs-recent-files', 'ml-auc-threshold', 'ml-confusion-matrix', 'ml-cooccurrence', 'llm-batch-collector', 'llm-chat-memory', 'llm-context-assembler', 'devops-archive-keep', 'devops-backoff-retry', 'devops-changelog-parse', 'db-audit-columns', 'db-batch-insert', 'db-connection-retry', 'obs-alert-check', 'obs-cardinality', 'obs-correlation-id', 'sec-account-lockout', 'sec-audit-writer', 'sec-cmd-block', 'brw-audio-unlock', 'brw-clipboard', 'brw-cookie', 'mob-app-state', 'mob-battery', 'mob-biometric', 'test-assert', 'test-benchmark', 'test-contract-assert', 'gfx-arc', 'gfx-aspect-fit', 'gfx-bezier', 'mth-angle', 'mth-base-convert', 'mth-bit-ops', 'rtc-broadcast-channel', 'rtc-changelog', 'rtc-cursors', 'alg-bellman-ford', 'alg-bipartite', 'alg-bucket-sort', 'arch-adapter', 'arch-backpressure', 'arch-builder', 'str-case-converter', 'str-compact-whitespace', 'str-delimiter-join', 'col-avltree', 'col-capacity-set', 'col-chunker', 'fsys-atomic-rename', 'fsys-binary-header', 'time-age', 'time-business-days', 'time-countdown-until', 'msg-at-least-once', 'msg-channel-mux', 'msg-compacted-topic', 'http-accept-parse', 'http-basic-auth', 'http-bearer-token', 'acc-announce', 'acc-aria-expanded', 'acc-assist-label', 'i18n-bidi', 'i18n-calendar', 'i18n-collate', 'fin-amortization', 'fin-annuity-fv', 'fin-bill-due', 'edu-answer-feedback', 'edu-badge-progress', 'edu-cloze-check', 'gen-arg-parser', 'gen-camel-case', 'gen-doc-comment', 'viz-animate-frame', 'viz-area-points', 'viz-arrow-head', 'cli-banner', 'cli-colorize', 'cli-command-router', 'embed-avg-filter', 'embed-baud-rate', 'embed-bit-crc16'],
    javascript: ['04-web-apps', '22-browser-engineering', 'brw-audio-unlock', 'brw-clipboard', 'brw-cookie', 'str-case-converter', 'str-compact-whitespace', 'str-delimiter-join', 'acc-announce', 'acc-aria-expanded', 'acc-assist-label', 'i18n-bidi', 'i18n-calendar', 'i18n-collate', 'edu-answer-feedback', 'edu-badge-progress', 'edu-cloze-check', 'gen-arg-parser', 'gen-camel-case', 'gen-doc-comment', 'viz-animate-frame', 'viz-area-points', 'viz-arrow-head'],
    python: ['07-ai-ml', '10-machine-learning', '27-data-engineering', 'fs-recent-files', 'ml-auc-threshold', 'ml-confusion-matrix', 'ml-cooccurrence', 'llm-batch-collector', 'llm-chat-memory', 'llm-context-assembler', 'devops-archive-keep', 'devops-backoff-retry', 'devops-changelog-parse', 'db-audit-columns', 'db-batch-insert', 'db-connection-retry', 'obs-alert-check', 'obs-cardinality', 'obs-correlation-id', 'sec-account-lockout', 'sec-audit-writer', 'sec-cmd-block', 'test-assert', 'test-benchmark', 'test-contract-assert', 'mth-angle', 'mth-base-convert', 'mth-bit-ops', 'alg-bellman-ford', 'alg-bipartite', 'alg-bucket-sort', 'str-case-converter', 'str-compact-whitespace', 'str-delimiter-join', 'col-avltree', 'col-capacity-set', 'col-chunker', 'fsys-atomic-rename', 'fsys-binary-header', 'time-age', 'time-business-days', 'time-countdown-until', 'msg-at-least-once', 'msg-channel-mux', 'msg-compacted-topic', 'http-accept-parse', 'http-basic-auth', 'http-bearer-token', 'i18n-bidi', 'i18n-calendar', 'i18n-collate', 'fin-amortization', 'fin-annuity-fv', 'fin-bill-due', 'viz-animate-frame', 'viz-area-points', 'viz-arrow-head', 'cli-banner', 'cli-colorize', 'cli-command-router'],
    go: ['12-distributed-systems', '05-systems-programming', '34-api-integration-platforms', 'fs-recent-files', 'devops-archive-keep', 'devops-backoff-retry', 'devops-changelog-parse', 'db-audit-columns', 'db-batch-insert', 'db-connection-retry', 'obs-alert-check', 'obs-cardinality', 'obs-correlation-id', 'rtc-broadcast-channel', 'rtc-changelog', 'rtc-cursors', 'arch-adapter', 'arch-backpressure', 'arch-builder', 'fsys-atomic-rename', 'fsys-binary-header', 'time-age', 'time-business-days', 'time-countdown-until', 'msg-at-least-once', 'msg-channel-mux', 'msg-compacted-topic', 'http-accept-parse', 'http-basic-auth', 'http-bearer-token', 'cli-banner', 'cli-colorize', 'cli-command-router'],
    rust: ['05-systems-programming', '16-computer-architecture', '10-security', 'sec-account-lockout', 'sec-audit-writer', 'sec-cmd-block'],
    c: ['05-systems-programming', '06-os-kernel', '16-computer-architecture', 'embed-avg-filter', 'embed-baud-rate', 'embed-bit-crc16'],
    cpp: ['08-computer-graphics', '09-game-engines', '05-systems-programming', 'gfx-arc', 'gfx-aspect-fit', 'gfx-bezier', 'alg-bellman-ford', 'alg-bipartite', 'alg-bucket-sort', 'embed-avg-filter', 'embed-baud-rate', 'embed-bit-crc16'],
    java: ['31-mobile-cross-platform', '26-enterprise-systems', '04-web-apps', 'arch-adapter', 'arch-backpressure', 'arch-builder', 'col-avltree', 'col-capacity-set', 'col-chunker'],
    kotlin: ['31-mobile-cross-platform', 'mob-app-state', 'mob-battery', 'mob-biometric'],
    swift: ['31-mobile-cross-platform', '08-computer-graphics', 'mob-app-state', 'mob-battery', 'mob-biometric'],
    dart: ['31-mobile-cross-platform', 'mob-app-state', 'mob-battery', 'mob-biometric'],
    csharp: ['26-enterprise-systems', '04-web-apps', 'arch-adapter', 'arch-backpressure', 'arch-builder'],
    php: ['04-web-apps', '22-browser-engineering', 'http-accept-parse', 'http-basic-auth', 'http-bearer-token'],
    ruby: ['04-web-apps', 'gen-arg-parser', 'gen-camel-case', 'gen-doc-comment', 'str-case-converter', 'str-compact-whitespace', 'str-delimiter-join'],
};
// ─── Node type → library files ────────────────────────────────────────────
const NODE_TYPE_TO_FILES = {
    input: ['01-node-architecture-reference.md', '07-node-implementation-guide.md', '03-code-generation-rules.md', '20-networking-communication-protocols.md', '17-security-architecture-guide.md', '36-api-integration-platforms.md'],
    output: ['01-node-architecture-reference.md', '07-node-implementation-guide.md', '03-code-generation-rules.md', '18-media-multimedia-processing.md', '26-data-engineering-analytics.md', '35-computer-graphics-gpu.md'],
    logic: ['01-node-architecture-reference.md', '05-design-patterns.md', '06-data-flow-patterns.md', '07-node-implementation-guide.md', '12-game-development-patterns.md', '25-distributed-systems.md', '19-ai-ml-integration-guide.md', '34-llm-ops-platform-engineering.md', '40-formal-methods-verification.md'],
    api: ['01-node-architecture-reference.md', '02-app-type-templates.md', '04-technology-mapping.md', '07-node-implementation-guide.md', '20-networking-communication-protocols.md', '17-security-architecture-guide.md', '22-enterprise-systems-integration.md', '36-api-integration-platforms.md'],
    database: ['01-node-architecture-reference.md', '04-technology-mapping.md', '06-data-flow-patterns.md', '07-node-implementation-guide.md', '15-database-design-patterns.md', '26-data-engineering-analytics.md', '41-emerging-technologies.md'],
    ui: ['01-node-architecture-reference.md', '02-app-type-templates.md', '07-node-implementation-guide.md', '13-desktop-application-architecture.md', '14-web-application-architecture.md', '27-mobile-cross-platform.md', '35-computer-graphics-gpu.md'],
    master: ['01-node-architecture-reference.md', '02-app-type-templates.md', '05-design-patterns.md', '03-code-generation-rules.md', '09-deployment-templates.md', '23-cloud-native-infrastructure.md', '24-devops-sre-tooling.md', '30-browser-engineering.md', '31-compilers-language-design.md', '34-llm-ops-platform-engineering.md', '41-emerging-technologies.md'],
};
// ─── Language → library files ────────────────────────────────────────────
const LANGUAGE_TO_FILES = {
    typescript: ['04-technology-mapping.md', '08-testing-patterns.md', '11-debugging-strategies.md', '14-web-application-architecture.md', '23-cloud-native-infrastructure.md', '22-enterprise-systems-integration.md', '34-llm-ops-platform-engineering.md'],
    javascript: ['04-technology-mapping.md', '08-testing-patterns.md', '11-debugging-strategies.md', '14-web-application-architecture.md'],
    python: ['04-technology-mapping.md', '08-testing-patterns.md', '09-deployment-templates.md', '10-cicd-configuration.md', '19-ai-ml-integration-guide.md', '26-data-engineering-analytics.md', '21-iot-embedded-systems.md', '34-llm-ops-platform-engineering.md', '40-formal-methods-verification.md'],
    go: ['04-technology-mapping.md', '08-testing-patterns.md', '09-deployment-templates.md', '10-cicd-configuration.md', '16-systems-programming-guide.md', '25-distributed-systems.md', '23-cloud-native-infrastructure.md', '36-api-integration-platforms.md'],
    rust: ['16-systems-programming-guide.md', '10-cicd-configuration.md', '17-security-architecture-guide.md', '40-formal-methods-verification.md'],
    dart: ['27-mobile-cross-platform.md', '08-testing-patterns.md'],
    kotlin: ['27-mobile-cross-platform.md'],
    swift: ['27-mobile-cross-platform.md', '13-desktop-application-architecture.md'],
    csharp: ['22-enterprise-systems-integration.md', '09-deployment-templates.md'],
    c: ['16-systems-programming-guide.md', '21-iot-embedded-systems.md', '40-formal-methods-verification.md'],
    cpp: ['16-systems-programming-guide.md', '35-computer-graphics-gpu.md', '12-game-development-patterns.md'],
    java: ['22-enterprise-systems-integration.md', '27-mobile-cross-platform.md', '08-testing-patterns.md'],
    php: ['14-web-application-architecture.md', '36-api-integration-platforms.md', '04-technology-mapping.md'],
    ruby: ['14-web-application-architecture.md', '04-technology-mapping.md', '08-testing-patterns.md'],
};
// ─── App type keyword → library file mappings ─────────────────────────────
const APP_TYPE_KEYWORDS = {
    cli: '02-app-type-templates.md',
    terminal: '02-app-type-templates.md',
    'command line': '02-app-type-templates.md',
    web: '02-app-type-templates.md',
    website: '02-app-type-templates.md',
    server: '02-app-type-templates.md',
    desktop: '02-app-type-templates.md',
    gui: '02-app-type-templates.md',
    api: '02-app-type-templates.md',
    rest: '02-app-type-templates.md',
    'data pipeline': '02-app-type-templates.md',
    etl: '02-app-type-templates.md',
    'media': '02-app-type-templates.md',
    audio: '02-app-type-templates.md',
    'system tool': '02-app-type-templates.md',
    daemon: '02-app-type-templates.md',
    game: '12-game-development-patterns.md',
    gaming: '12-game-development-patterns.md',
    'linux app': '13-desktop-application-architecture.md',
    'desktop app': '13-desktop-application-architecture.md',
    fullstack: '14-web-application-architecture.md',
    'web app': '14-web-application-architecture.md',
    database: '15-database-design-patterns.md',
    event: '25-distributed-systems.md',
    streaming: '18-media-multimedia-processing.md',
    ai: '19-ai-ml-integration-guide.md',
    ml: '19-ai-ml-integration-guide.md',
    llm: '19-ai-ml-integration-guide.md',
    network: '20-networking-communication-protocols.md',
    iot: '21-iot-embedded-systems.md',
    embedded: '21-iot-embedded-systems.md',
    erp: '22-enterprise-systems-integration.md',
    crm: '22-enterprise-systems-integration.md',
    kubernetes: '23-cloud-native-infrastructure.md',
    container: '23-cloud-native-infrastructure.md',
    monitoring: '24-devops-sre-tooling.md',
    mobile: '27-mobile-cross-platform.md',
    ios: '27-mobile-cross-platform.md',
    android: '27-mobile-cross-platform.md',
    payment: '28-fintech-insurance-systems.md',
    fintech: '28-fintech-insurance-systems.md',
    banking: '28-fintech-insurance-systems.md',
    healthcare: '29-healthcare-life-sciences.md',
    medical: '29-healthcare-life-sciences.md',
    video: '37-media-entertainment-social.md',
    social: '37-media-entertainment-social.md',
    chat: '37-media-entertainment-social.md',
    messaging: '37-media-entertainment-social.md',
    marketplace: '38-marketplace-ecommerce.md',
    ecommerce: '38-marketplace-ecommerce.md',
    'adaptive learning': '39-education-learning-platforms.md',
    'spaced repetition': '39-education-learning-platforms.md',
    'web3': '41-emerging-technologies.md',
    blockchain: '41-emerging-technologies.md',
    'digital twin': '41-emerging-technologies.md',
    'edge': '41-emerging-technologies.md',
    'ar/vr': '41-emerging-technologies.md',
    verification: '40-formal-methods-verification.md',
    'model checking': '40-formal-methods-verification.md',
};
// ─── Helpers ──────────────────────────────────────────────────────────────
/**
 * Load all library files from disk into cache.
 */
function loadAllLibraryFiles() {
    const files = new Map();
    try {
        if (!fs.existsSync(LIBRARY_DIR)) {
            console.warn('[libraryContext] Library directory not found:', LIBRARY_DIR);
            return files;
        }
        const entries = fs.readdirSync(LIBRARY_DIR).sort();
        for (const entry of entries) {
            if (!entry.endsWith('.md'))
                continue;
            const filePath = path.join(LIBRARY_DIR, entry);
            try {
                const content = fs.readFileSync(filePath, 'utf-8');
                files.set(entry, { name: entry, content, loadedAt: Date.now() });
            }
            catch (err) {
                console.warn(`[libraryContext] Failed to read ${entry}:`, err);
            }
        }
        console.log(`[libraryContext] Loaded ${files.size} library files`);
    }
    catch (err) {
        console.error('[libraryContext] Failed to load library files:', err);
    }
    return files;
}
/**
 * Load Bible level index files (00-index.*) and MASTER-INDEX.txt.
 * Full content files are not loaded to keep memory manageable; the index
 * files and MASTER-INDEX provide sufficient overview for LLM context injection.
 */
function loadBibleFiles() {
    const files = new Map();
    let masterIndex = null;
    try {
        if (!fs.existsSync(BIBLE_DIR)) {
            console.warn('[libraryContext] Bible directory not found:', BIBLE_DIR);
            return { files, masterIndex: null };
        }
        // Load MASTER-INDEX.txt
        const masterIndexPath = path.join(BIBLE_DIR, 'MASTER-INDEX.txt');
        if (fs.existsSync(masterIndexPath)) {
            masterIndex = fs.readFileSync(masterIndexPath, 'utf-8');
        }
        // Load 00-index.* from each level directory
        const entries = fs.readdirSync(BIBLE_DIR, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
        for (const entry of entries) {
            if (!entry.isDirectory())
                continue;
            const levelDir = entry.name;
            // Skip levels we don't have topic mappings for (unlikely but defensive)
            if (!BIBLE_LEVEL_TOPICS[levelDir])
                continue;
            const dirPath = path.join(BIBLE_DIR, levelDir);
            let indexFiles = [];
            try {
                const dirEntries = fs.readdirSync(dirPath);
                indexFiles = dirEntries.filter(f => f.startsWith('00-index.'));
            }
            catch {
                continue;
            }
            // Load the first 00-index file found
            for (const indexFile of indexFiles) {
                try {
                    const content = fs.readFileSync(path.join(dirPath, indexFile), 'utf-8');
                    const cacheKey = `${levelDir}/${indexFile}`;
                    files.set(cacheKey, { name: indexFile, level: levelDir, content, loadedAt: Date.now() });
                    break; // Only load the first index file per level
                }
                catch (err) {
                    console.warn(`[libraryContext] Failed to read ${levelDir}/${indexFile}:`, err);
                }
            }
        }
        console.log(`[libraryContext] Loaded ${files.size} Bible level indexes${masterIndex ? ' + MASTER-INDEX' : ''}`);
    }
    catch (err) {
        console.error('[libraryContext] Failed to load Bible files:', err);
    }
    return { files, masterIndex };
}
/**
 * Get cached library files, reloading if cache is stale.
 */
function getLibraryCache() {
    const now = Date.now();
    if (cachedLibraryFiles === null || (now - lastLoadTime) > CACHE_TTL_MS) {
        cachedLibraryFiles = loadAllLibraryFiles();
        lastLoadTime = now;
    }
    return cachedLibraryFiles;
}
/**
 * Get cached Bible files, reloading if cache is stale.
 */
function getBibleCache() {
    const now = Date.now();
    if (cachedBibleFiles === null || (now - lastLoadTime) > CACHE_TTL_MS) {
        const loaded = loadBibleFiles();
        cachedBibleFiles = loaded.files;
        cachedMasterIndex = loaded.masterIndex;
        lastLoadTime = now;
    }
    return { files: cachedBibleFiles, masterIndex: cachedMasterIndex };
}
/**
 * Extract a concise summary from a markdown/text file by pulling headings
 * and first substantive paragraph under each heading.
 */
function extractSummary(content, maxChars = 600) {
    const lines = content.split('\n');
    const sections = [];
    let currentHeading = '';
    let currentText = '';
    for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('## ') || trimmed.startsWith('# ')) {
            if (currentText) {
                sections.push(currentHeading ? `[${currentHeading}] ${currentText}` : currentText);
                currentText = '';
            }
            currentHeading = trimmed.replace(/^#+\s+/, '');
            continue;
        }
        // Collect non-empty, non-boilerplate text
        if (trimmed &&
            !trimmed.startsWith('- [') &&
            !trimmed.startsWith('>') &&
            !trimmed.startsWith('---') &&
            !trimmed.startsWith('```') &&
            !trimmed.startsWith('|') &&
            trimmed.length > 10) {
            currentText += (currentText ? ' ' : '') + trimmed.replace(/\*\*/g, '').replace(/`/g, '');
        }
    }
    if (currentText) {
        sections.push(currentHeading ? `[${currentHeading}] ${currentText}` : currentText);
    }
    const result = sections.slice(0, 5).join('\n');
    return result.length > maxChars ? result.substring(0, maxChars) + '...' : result;
}
/**
 * Find which library files are most relevant to a given search text.
 *
 * PRIMARY: semantic retrieval — embed the search text and take the top sheets
 * by cosine similarity (vector matching, replaces the keyword matcher).
 * FALLBACK: the keyword path only when semantic retrieval finds nothing (very
 * short / generic queries), so we never lose the ability to surface a sheet.
 * Always includes the index + code-generation rules (small, high-value).
 */
function findRelevantFiles(searchText) {
    const semantic = semanticRetrieve(searchText, 6);
    const matched = new Set(semantic.map(s => s.id));
    if (matched.size === 0) {
        const lower = searchText.toLowerCase();
        for (const [filename, topics] of Object.entries(FILE_TOPICS)) {
            for (const topic of topics) {
                if (lower.includes(topic) || topic.includes(lower)) {
                    matched.add(filename);
                    break;
                }
            }
        }
        for (const [keyword, filename] of Object.entries(APP_TYPE_KEYWORDS)) {
            if (lower.includes(keyword))
                matched.add(filename);
        }
    }
    // Always include index and code generation rules
    matched.add('00-reference-index.md');
    matched.add('03-code-generation-rules.md');
    return Array.from(matched).slice(0, 8);
}
/**
 * Word-boundary match: true when `word` appears in `text` as a whole word.
 * Avoids substring false-positives like 'id' matching 'grid' or 'ecs' in
 * 'sections' — important now that the code-chunk library adds short tags.
 */
function containsWord(text, word) {
    if (!word)
        return false;
    const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`(^|[^a-z0-9])${escaped}($|[^a-z0-9])`).test(text);
}
/**
 * Find which Bible levels are most relevant to a given search text.
 *
 * PRIMARY: vector retrieval over the unified RAG index (every bible page is
 * embedded) — semantic, catches topics the keyword map misses.
 * FALLBACK: keyword/topic matching when the vector pass finds nothing (very
 * short / generic queries), so we never lose the ability to surface a level.
 * Always includes the LLM guide and foundations as defaults.
 */
function findRelevantBibleLevels(searchText, maxLevels = 3) {
    const semantic = ragRetrieveBibleLevels(searchText, maxLevels);
    if (semantic.length > 0) {
        const result = new Set(semantic);
        result.add('07-llm-guide');
        result.add('01-foundations');
        return Array.from(result).slice(0, maxLevels + 1);
    }
    const lower = searchText.toLowerCase();
    const scored = [];
    for (const [level, topics] of Object.entries(BIBLE_LEVEL_TOPICS)) {
        let score = 0;
        for (const topic of topics) {
            const topicWords = topic.split(' ');
            for (const word of topicWords) {
                if (word.length > 2 && containsWord(lower, word)) {
                    score += 3;
                }
            }
            if (containsWord(lower, topic) || containsWord(topic, lower)) {
                score += 10;
            }
        }
        if (score > 0) {
            scored.push({ level, score });
        }
    }
    scored.sort((a, b) => b.score - a.score);
    // Always include the LLM guide and foundations as defaults
    const result = new Set(scored.slice(0, maxLevels).map(s => s.level));
    result.add('07-llm-guide');
    result.add('01-foundations');
    return Array.from(result).slice(0, maxLevels + 1);
}
/**
 * Get the formatted name for a Bible level directory.
 */
function getBibleLevelName(levelDir) {
    const match = levelDir.match(/^(\d+)-(.+)$/);
    if (match) {
        return `${match[1]} — ${match[2].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}`;
    }
    return levelDir.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
// ─── Public API ───────────────────────────────────────────────────────────
/**
 * Build a compact overview of the wiki knowledge base (modelVeronice.txt
 * section headers + VACA-MASTER-KNOWLEDGE.md part headers) so the LLM knows
 * what the wiki covers and can reference it when answering.
 */
function getWikiOverview(maxChars = 700) {
    const lines = [];
    try {
        if (fs.existsSync(WIKI_PATH)) {
            const wiki = fs.readFileSync(WIKI_PATH, 'utf-8').split('\n');
            const headers = wiki
                .map((l) => l.trim())
                .filter((l) => /^\d+\.\s+[A-Z]/.test(l) && l.length < 90);
            if (headers.length > 0) {
                lines.push('modelVeronice.txt sections: ' + headers.slice(0, 60).map((h) => h.replace(/\s*—.*$/, '')).join(', '));
            }
        }
        if (fs.existsSync(KNOWLEDGE_PATH)) {
            const kb = fs.readFileSync(KNOWLEDGE_PATH, 'utf-8').split('\n');
            const parts = kb
                .map((l) => l.trim())
                .filter((l) => /^## Part [A-Z]/.test(l));
            if (parts.length > 0) {
                lines.push('VACA-MASTER-KNOWLEDGE.md parts: ' + parts.map((p) => p.replace(/^## /, '')).join(', '));
            }
        }
    }
    catch {
        // Wiki missing — context degrades gracefully to library + bible only
    }
    const joined = lines.join('\n');
    return joined.length > maxChars ? joined.substring(0, maxChars) + '…' : joined;
}
/**
 * Get a compact context string from the wiki overview, library files AND
 * Bible levels relevant to a specific search query (e.g., the user's app
 * goal or node description).
 *
 * This is the primary function for prompt injection — call it with the app
 * goal, node description, or any user-provided text, and it returns relevant
 * wiki + library + Bible snippets.
 */
/**
 * Assemble the full reference block from pre-resolved relevance. Shared by the
 * hashing path (getLibraryContext) and the dense path (getLibraryContextDense)
 * so the injected prompt text is identical in shape regardless of ranker.
 */
function assembleLibraryContext(searchText, relevantLibFiles, relevantBibleLevels, blueprintReqs) {
    const libFiles = getLibraryCache();
    const bibleData = getBibleCache();
    const bibleFiles = bibleData.files;
    const hasLibContent = libFiles.size > 0;
    const hasBibleContent = bibleFiles.size > 0 || !!bibleData.masterIndex;
    if (!hasLibContent && !hasBibleContent)
        return '';
    const parts = [
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '📚 REFERENCE — wiki + library + bible. Consult ALL THREE sources:',
        '📗 WIKI — modelVeronice.txt + data/VACA-MASTER-KNOWLEDGE.md (platform knowledge, history, lessons).',
        '📜 BIBLE — bible-reference/ deep technical guides (42 levels).',
        '📖 LIBRARY — data/library/ sheets (patterns, rules, templates).',
        'Use these references to inform architecture, code generation, and implementation.',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    ];
    // Inject compact wiki overview (what the wiki covers)
    const wikiOverview = getWikiOverview();
    if (wikiOverview) {
        parts.push(`\n── 📗 WIKI KNOWLEDGE BASE ──`);
        parts.push(wikiOverview);
    }
    // Inject relevant library file summaries
    if (hasLibContent) {
        for (const name of relevantLibFiles) {
            const file = libFiles.get(name);
            if (!file)
                continue;
            const meta = FILE_TOPICS[name];
            const topics = meta ? ` (${meta.join(', ')})` : '';
            const summary = extractSummary(file.content, 400);
            parts.push(`\n── 📖 ${name.replace('.md', '')}${topics} ──`);
            parts.push(summary);
        }
    }
    // Inject the exact blueprint requirements for this goal (RAG prong 2 —
    // "pull the pre-approved architecture and inject it into the prompt").
    // Only for free-text queries; empty string when nothing clears the floor.
    if (searchText) {
        const blueprintReqs = buildBlueprintRequirements(searchText);
        if (blueprintReqs)
            parts.push(`\n${blueprintReqs}`);
    }
    // Inject relevant Bible level overviews
    if (hasBibleContent) {
        for (const level of relevantBibleLevels) {
            // Try to find the index file for this level
            let indexContent = null;
            for (const [key, file] of bibleFiles) {
                if (file.level === level) {
                    indexContent = file.content;
                    break;
                }
            }
            const levelName = getBibleLevelName(level);
            const topics = BIBLE_LEVEL_TOPICS[level] || [];
            const topicStr = topics.length > 0 ? ` (${topics.join(', ')})` : '';
            parts.push(`\n── 📜 Bible: ${levelName}${topicStr} ──`);
            if (indexContent) {
                parts.push(extractSummary(indexContent, 350));
            }
            else {
                parts.push(`Reference level covering: ${topics.join(', ')}.`);
            }
        }
        // Include relevant lines from MASTER-INDEX for the selected levels
        if (bibleData.masterIndex && searchText) {
            const masterLines = bibleData.masterIndex.split('\n');
            const relevantMasterLines = [];
            for (const line of masterLines) {
                const trimmed = line.trim();
                // Look for lines that mention our relevant levels
                for (const level of relevantBibleLevels) {
                    const levelNum = level.match(/^(\d+)/)?.[1];
                    if (levelNum && (trimmed.startsWith(levelNum + '.') || trimmed.startsWith(levelNum + ' —'))) {
                        relevantMasterLines.push(trimmed);
                        break;
                    }
                }
            }
            if (relevantMasterLines.length > 0) {
                parts.push('\n  (From MASTER-INDEX:)');
                parts.push(...relevantMasterLines.map(l => `  ${l}`));
            }
        }
    }
    parts.push('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    parts.push('Use the reference library and Bible guides above when generating code. Follow the patterns, rules, and best practices documented.\n');
    return parts.join('\n');
}
/**
 * Reference context for a goal — hashing-trick retrieval (default path).
 * Synchronous; the dense upgrade getLibraryContextDense() falls back to this.
 */
export function getLibraryContext(searchText) {
    const libFiles = getLibraryCache();
    const relevantLibFiles = searchText
        ? findRelevantFiles(searchText)
        : Array.from(libFiles.keys()).slice(0, 3);
    const relevantBibleLevels = searchText
        ? findRelevantBibleLevels(searchText)
        : ['01-foundations', '07-llm-guide'];
    const blueprintReqs = searchText ? buildBlueprintRequirements(searchText) : '';
    return assembleLibraryContext(searchText, relevantLibFiles, relevantBibleLevels, blueprintReqs);
}
/**
 * Reference context with DENSE (Ollama nomic-embed) retrieval — the model-based
 * upgrade of the hashing-trick ranker. Per-piece fallback: anything the dense
 * ranker can't answer (snapshot missing, Ollama down, nothing above the floor)
 * falls back to the hashing path, so this is always at least as good as
 * getLibraryContext() and never throws.
 */
export async function getLibraryContextDense(searchText) {
    if (!searchText)
        return getLibraryContext(searchText);
    try {
        const qv = await denseEmbedQuery(searchText);
        if (!qv)
            return getLibraryContext(searchText);
        const [denseFiles, denseLevels, denseBlueprint] = await Promise.all([
            denseRetrieveSheets(qv, 6),
            denseRetrieveBibleLevels(qv, 3),
            denseBuildBlueprintRequirements(qv, searchText, 2),
        ]);
        const relevantLibFiles = denseFiles ?? findRelevantFiles(searchText);
        const relevantBibleLevels = denseLevels ?? findRelevantBibleLevels(searchText);
        const blueprintReqs = denseBlueprint ?? buildBlueprintRequirements(searchText);
        return assembleLibraryContext(searchText, relevantLibFiles, relevantBibleLevels, blueprintReqs);
    }
    catch (err) {
        console.warn('[libraryContext] dense retrieval failed — falling back to hashing:', err.message);
        return getLibraryContext(searchText);
    }
}
/**
 * Get context filtered by node type and language, including Bible references.
 * Used during code generation to inject the most relevant references.
 */
export function getLibraryContextForNodeType(nodeType, language) {
    const libFiles = getLibraryCache();
    const bibleData = getBibleCache();
    const bibleFiles = bibleData.files;
    const hasLibContent = libFiles.size > 0;
    const hasBibleContent = bibleFiles.size > 0;
    if (!hasLibContent && !hasBibleContent)
        return '';
    const relevantLibFiles = new Set();
    const relevantBibleLevels = new Set();
    // Library files from node type
    const typeFiles = NODE_TYPE_TO_FILES[nodeType] || NODE_TYPE_TO_FILES['logic'];
    for (const f of typeFiles)
        relevantLibFiles.add(f);
    // Library files from language
    if (language) {
        const langFiles = LANGUAGE_TO_FILES[language.toLowerCase()] || [];
        for (const f of langFiles)
            relevantLibFiles.add(f);
    }
    relevantLibFiles.add('00-reference-index.md');
    // Always-on core levels go FIRST so the MAX_BIBLE_LEVELS_INJECTED cap below
    // can never starve them, no matter how large the maps grow.
    relevantBibleLevels.add('01-foundations');
    relevantBibleLevels.add('07-llm-guide');
    // Bible levels from node type
    const bibleLevels = NODE_TYPE_TO_BIBLE_LEVELS[nodeType] || NODE_TYPE_TO_BIBLE_LEVELS['master'];
    for (const l of bibleLevels)
        relevantBibleLevels.add(l);
    // Bible levels from language
    if (language) {
        const langBibleLevels = LANGUAGE_TO_BIBLE_LEVELS[language.toLowerCase()] || [];
        for (const l of langBibleLevels)
            relevantBibleLevels.add(l);
    }
    const parts = [
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        `📚 REFERENCE — Relevant patterns for ${nodeType} node${language ? ` (${language})` : ''}.`,
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    ];
    // Library files
    if (hasLibContent) {
        for (const name of relevantLibFiles) {
            const file = libFiles.get(name);
            if (!file)
                continue;
            const summary = extractSummary(file.content, 300);
            parts.push(`\n── 📖 ${name.replace('.md', '')} ──`);
            parts.push(summary);
        }
    }
    // Bible levels
    if (hasBibleContent) {
        // Cap always-injected levels: the node+language maps can grow large as the
        // chunk library expands, and each level costs ~250 chars of context.
        const MAX_BIBLE_LEVELS_INJECTED = 24;
        let injected = 0;
        for (const level of relevantBibleLevels) {
            if (injected >= MAX_BIBLE_LEVELS_INJECTED)
                break;
            let indexContent = null;
            for (const [, file] of bibleFiles) {
                if (file.level === level) {
                    indexContent = file.content;
                    break;
                }
            }
            const levelName = getBibleLevelName(level);
            const topics = BIBLE_LEVEL_TOPICS[level] || [];
            parts.push(`\n── 📜 Bible: ${levelName} ──`);
            if (indexContent) {
                parts.push(extractSummary(indexContent, 250));
            }
            else if (topics.length > 0) {
                parts.push(`Covers: ${topics.join(', ')}.`);
            }
            injected++;
        }
    }
    parts.push('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    return parts.join('\n');
}
/**
 * Get context specifically from Bible references for a search query.
 * Useful for the /api/library/context endpoint.
 */
export function getBibleContext(searchText, maxLevels = 3) {
    const bibleData = getBibleCache();
    const bibleFiles = bibleData.files;
    const masterIndex = bibleData.masterIndex;
    if (bibleFiles.size === 0 && !masterIndex)
        return 'No Bible references loaded.';
    const relevantLevels = searchText
        ? findRelevantBibleLevels(searchText, maxLevels)
        : ['01-foundations', '07-llm-guide', '04-web-apps'];
    const parts = [
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '📜 BIBLE REFERENCE — Deep technical guides across 42 levels.',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    ];
    for (const level of relevantLevels) {
        let indexContent = null;
        for (const [, file] of bibleFiles) {
            if (file.level === level) {
                indexContent = file.content;
                break;
            }
        }
        const levelName = getBibleLevelName(level);
        const topics = BIBLE_LEVEL_TOPICS[level] || [];
        parts.push(`\n── 📜 ${levelName} ──`);
        parts.push(`Topics: ${topics.join(', ')}`);
        if (indexContent) {
            parts.push(extractSummary(indexContent, 400));
        }
        // Include MASTER-INDEX entry for this level
        if (masterIndex) {
            const levelNum = level.match(/^(\d+)/)?.[1];
            if (levelNum) {
                for (const line of masterIndex.split('\n')) {
                    const trimmed = line.trim();
                    if (trimmed.startsWith(levelNum + '.') || trimmed.startsWith(levelNum + ' —')) {
                        parts.push(`  ${trimmed}`);
                        break;
                    }
                }
            }
        }
    }
    parts.push('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    return parts.join('\n');
}
/**
 * Get the complete library + Bible index content as a single string.
 */
export function getCompleteLibrary() {
    const libFiles = getLibraryCache();
    const bibleData = getBibleCache();
    const bibleFiles = bibleData.files;
    const parts = [
        '# Reference Library & Bible — Complete Index',
        '',
        `Library files: ${libFiles.size}`,
        `Bible levels loaded: ${bibleFiles.size}`,
        '',
    ];
    if (libFiles.size > 0) {
        parts.push('---\n# Library Files\n');
        for (const [name, file] of libFiles) {
            parts.push(`\n## ${name}\n`);
            parts.push(file.content.substring(0, 2000) + '\n...');
        }
    }
    if (bibleFiles.size > 0) {
        parts.push('---\n# Bible Level Indexes\n');
        for (const [, file] of bibleFiles) {
            parts.push(`\n## ${file.level} (${file.name})\n`);
            parts.push(file.content.substring(0, 1500) + '\n...');
        }
    }
    if (bibleData.masterIndex) {
        parts.push('---\n# Bible MASTER-INDEX (Curriculum Overview)\n\n');
        parts.push(bibleData.masterIndex.substring(0, 3000) + '\n...\n');
    }
    return parts.join('\n');
}
/**
 * Get the content of a specific library file by name.
 */
export function getLibraryFile(filename) {
    const files = getLibraryCache();
    const file = files.get(filename);
    if (!file)
        return null;
    return { name: file.name, content: file.content };
}
/**
 * Search across library files AND Bible level indexes for a query string.
 */
export function searchLibrary(query, maxResults = 8) {
    const libFiles = getLibraryCache();
    const bibleData = getBibleCache();
    const results = [];
    const lowerQuery = query.toLowerCase();
    // Search library files
    for (const [name, file] of libFiles) {
        const lowerContent = file.content.toLowerCase();
        const index = lowerContent.indexOf(lowerQuery);
        if (index === -1)
            continue;
        const start = Math.max(0, index - 100);
        const end = Math.min(file.content.length, index + query.length + 200);
        let snippet = file.content.substring(start, end);
        if (start > 0)
            snippet = '...' + snippet;
        if (end < file.content.length)
            snippet = snippet + '...';
        const matchCount = (lowerContent.match(new RegExp(lowerQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length;
        const relevance = matchCount * 10 + (index < 500 ? 5 : 0);
        results.push({ file: `📖 ${name}`, snippet, relevance });
    }
    // Search Bible level indexes and MASTER-INDEX
    for (const [, file] of bibleData.files) {
        const lowerContent = file.content.toLowerCase();
        const index = lowerContent.indexOf(lowerQuery);
        if (index === -1)
            continue;
        const start = Math.max(0, index - 100);
        const end = Math.min(file.content.length, index + query.length + 200);
        let snippet = file.content.substring(start, end);
        if (start > 0)
            snippet = '...' + snippet;
        if (end < file.content.length)
            snippet = snippet + '...';
        const matchCount = (lowerContent.match(new RegExp(lowerQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length;
        const relevance = (matchCount * 10 + (index < 500 ? 5 : 0)) + 2; // Slight boost for Bible
        const levelName = getBibleLevelName(file.level);
        results.push({ file: `📜 ${levelName} (${file.name})`, snippet, relevance });
    }
    // Search MASTER-INDEX
    if (bibleData.masterIndex) {
        const lowerContent = bibleData.masterIndex.toLowerCase();
        const index = lowerContent.indexOf(lowerQuery);
        if (index !== -1) {
            const start = Math.max(0, index - 150);
            const end = Math.min(bibleData.masterIndex.length, index + query.length + 300);
            let snippet = bibleData.masterIndex.substring(start, end);
            if (start > 0)
                snippet = '...' + snippet;
            if (end < bibleData.masterIndex.length)
                snippet = snippet + '...';
            const relevance = 50; // High relevance — MASTER-INDEX is a key reference
            results.push({ file: '📜 MASTER-INDEX (Curriculum Overview)', snippet, relevance });
        }
    }
    // Sort by relevance
    results.sort((a, b) => b.relevance - a.relevance);
    return results.slice(0, maxResults);
}
/**
 * Check if the library has been loaded (has content).
 */
export function hasLibraryContent() {
    return getLibraryCache().size > 0 || getBibleCache().files.size > 0;
}
/**
 * Invalidate the cache forcing a re-read from disk on next load.
 */
export function invalidateCache() {
    cachedLibraryFiles = null;
    cachedBibleFiles = null;
    cachedMasterIndex = null;
    lastLoadTime = 0;
}
/**
 * Get file listing for the API (library files + Bible levels).
 */
export function getLibraryFileList() {
    const libFiles = getLibraryCache();
    const bibleData = getBibleCache();
    const list = [];
    // Library files
    for (const [name] of libFiles) {
        list.push({
            name,
            title: name.replace('.md', '').replace(/^\d+-/, '').replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
            topics: FILE_TOPICS[name] || [],
            source: 'library',
        });
    }
    // Bible levels
    if (bibleData.masterIndex) {
        list.push({
            name: 'MASTER-INDEX.txt',
            title: 'Bible MASTER-INDEX — 42-Level Curriculum Overview',
            topics: ['all', 'curriculum', 'overview', 'index'],
            source: 'bible',
        });
    }
    for (const [, file] of bibleData.files) {
        const levelName = getBibleLevelName(file.level);
        list.push({
            name: `${file.level}/${file.name}`,
            title: `📜 ${levelName}`,
            topics: BIBLE_LEVEL_TOPICS[file.level] || [],
            source: 'bible',
        });
    }
    return list;
}
