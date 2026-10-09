/**
 * Venorica 50,000 Pattern Generator
 *
 * Generates 50,000 diverse code training patterns from:
 * 1. All project source files (function/class/interface extraction)
 * 2. Training dataset JSONL files (instruction-output pairs)
 * 3. Generated export projects (Go/TS code)
 * 4. Library reference documents (code snippets)
 * 5. Synthetic template-based variations
 *
 * Run with: npx tsx backend/src/scripts/generate-50000-patterns.ts
 */
import * as fs from 'fs';
import * as path from 'path';
// ─── Configuration ─────────────────────────────────────────────────
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const EXCLUDE_DIRS = new Set(['node_modules', 'dist', '.git', 'exports', '__pycache__', '.venv']);
const TARGET = 90000;
const EXTENSION_MAP = {
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.go': 'go',
    '.py': 'python',
    '.css': 'css',
    '.html': 'html',
    '.md': 'markdown',
};
// ─── 1. Source File Scanner ────────────────────────────────────────
function collectSourceFiles(rootDirs) {
    const files = [];
    function walk(dir) {
        let entries;
        try {
            entries = fs.readdirSync(dir, { withFileTypes: true });
        }
        catch {
            return;
        }
        for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            if (entry.isDirectory()) {
                if (EXCLUDE_DIRS.has(entry.name))
                    continue;
                if (entry.name.startsWith('.'))
                    continue;
                walk(fullPath);
                continue;
            }
            const ext = path.extname(entry.name).toLowerCase();
            const lang = EXTENSION_MAP[ext];
            if (!lang)
                continue;
            let content;
            try {
                content = fs.readFileSync(fullPath, 'utf-8');
            }
            catch {
                continue;
            }
            if (content.trim().length < 20)
                continue;
            const relativePath = path.relative(PROJECT_ROOT, fullPath);
            files.push({ path: fullPath, relativePath, content, language: lang });
        }
    }
    for (const dir of rootDirs) {
        if (fs.existsSync(dir))
            walk(dir);
    }
    return files;
}
// ─── 2. Code Unit Extractor ───────────────────────────────────────
function extractTSUnits(content, filePath) {
    const units = [];
    let m;
    const funcRegex = /(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([\s\S]*?(?=\nfunction|\nclass|\ninterface|\nexport|\n\/\*|\n\/\/|\n$)/g;
    while ((m = funcRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'function', code: m[0].trim(), language: 'typescript', filePath });
    }
    const arrowRegex = /(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([\s\S]*?(?=\n(?:const|let|var|export|function|class|interface|\/\/|\/\*|\n$))/g;
    while ((m = arrowRegex.exec(content)) !== null) {
        const code = m[0].trim();
        if (code.length > 30 && code.includes('=>')) {
            units.push({ name: m[1], kind: 'function', code, language: 'typescript', filePath });
        }
    }
    const classRegex = /(?:export\s+)?(?:abstract\s+)?class\s+(\w+)[\s\S]*?(?=\n(?:export|class|interface|function|\/\/|\/\*|\n$))/g;
    while ((m = classRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'class', code: m[0].trim(), language: 'typescript', filePath });
    }
    const interfaceRegex = /(?:export\s+)?interface\s+(\w+)[\s\S]*?(?=\n(?:export|interface|class|function|\/\/|\/\*|\n$))/g;
    while ((m = interfaceRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'interface', code: m[0].trim(), language: 'typescript', filePath });
    }
    const typeRegex = /(?:export\s+)?type\s+(\w+)\s*=[\s\S]*?(?=\n(?:export|type|interface|class|function|\/\/|\/\*|\n$))/g;
    while ((m = typeRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'type', code: m[0].trim(), language: 'typescript', filePath });
    }
    return units;
}
function extractGoUnits(content, filePath) {
    const units = [];
    let m;
    const goFuncRegex = /func\s+(?:\([\w\s*,.]+\)\s+)?(\w+)\s*\([\s\S]*?(?=\nfunc\s|\n\/\/|\n\*\/|\ntype\s|\nvar\s|\nconst\s|}$)/g;
    while ((m = goFuncRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'function', code: m[0].trim(), language: 'go', filePath });
    }
    const goTypeRegex = /type\s+(\w+)\s+(?:struct|interface)\s*\{[\s\S]*?\}(?:\n|$)/g;
    while ((m = goTypeRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'type', code: m[0].trim() + '\n}', language: 'go', filePath });
    }
    return units;
}
function extractPythonUnits(content, filePath) {
    const units = [];
    let m;
    const pyFuncRegex = /(?:async\s+)?def\s+(\w+)\s*\([\s\S]*?(?=\n(?:def\s|class\s|#\s|$))/g;
    while ((m = pyFuncRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'function', code: m[0].trim(), language: 'python', filePath });
    }
    const pyClassRegex = /class\s+(\w+)[\s\S]*?(?=\n(?:class\s|def\s|#\s|$))/g;
    while ((m = pyClassRegex.exec(content)) !== null) {
        units.push({ name: m[1], kind: 'class', code: m[0].trim(), language: 'python', filePath });
    }
    return units;
}
function extractUnits(file) {
    const units = [];
    const { content, language, relativePath } = file;
    // Always add the full file as a pattern
    const fileName = path.basename(file.path);
    units.push({
        name: fileName,
        kind: 'full_file',
        code: content,
        language,
        filePath: relativePath,
    });
    if (language === 'typescript' || language === 'javascript') {
        units.push(...extractTSUnits(content, relativePath));
    }
    else if (language === 'go') {
        units.push(...extractGoUnits(content, relativePath));
    }
    else if (language === 'python') {
        units.push(...extractPythonUnits(content, relativePath));
    }
    return units;
}
// ─── 3. Training Data Parser ────────────────────────────────────────
function parseTrainingData(filePath) {
    const units = [];
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        const lines = content.split('\n').filter((l) => l.trim());
        for (const line of lines) {
            try {
                const entry = JSON.parse(line);
                const code = String(entry.output || entry.code || entry.text || '');
                const instruction = String(entry.instruction || entry.title || '');
                if (code.length < 30)
                    continue;
                const lang = detectLanguage(code, String(entry.language || ''));
                units.push({
                    name: instruction.substring(0, 60),
                    kind: 'full_file',
                    code: code.substring(0, 2000),
                    language: lang,
                    filePath: `training/${path.basename(filePath)}`,
                });
            }
            catch {
                continue;
            }
        }
    }
    catch { /* skip */ }
    return units;
}
function detectLanguage(code, hint) {
    if (hint)
        return hint;
    if (/import\s+(?:\*|{)\s+from/.test(code) || /export\s+(?:default|const|function|class|interface)/.test(code))
        return 'typescript';
    if (/^package\s+\w+/m.test(code) || /^func\s/m.test(code))
        return 'go';
    if (/^import\s+\w+/m.test(code) || /^def\s/m.test(code) || /^class\s/m.test(code))
        return 'python';
    if (/^<[a-z]+/m.test(code) || /<\/[a-z]+>/m.test(code))
        return 'html';
    if (/^\.[\w-]+\s*\{/m.test(code) || /#[\w-]+\s*\{/m.test(code))
        return 'css';
    return 'typescript';
}
// ─── 4. Export Project Scanner ─────────────────────────────────────
function scanExports(exportRoot) {
    const units = [];
    if (!fs.existsSync(exportRoot))
        return units;
    const dirs = fs.readdirSync(exportRoot, { withFileTypes: true })
        .filter(d => d.isDirectory())
        .map(d => path.join(exportRoot, d.name));
    for (const dir of dirs) {
        const files = collectSourceFiles([dir]);
        for (const file of files) {
            units.push(...extractUnits(file));
        }
    }
    return units;
}
// ─── 5. Library Document Parser ────────────────────────────────────
function parseLibraryDocs(docsDir) {
    const units = [];
    if (!fs.existsSync(docsDir))
        return units;
    const files = fs.readdirSync(docsDir).filter(f => f.endsWith('.md'));
    for (const file of files) {
        const content = fs.readFileSync(path.join(docsDir, file), 'utf-8');
        const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
        let m;
        while ((m = codeBlockRegex.exec(content)) !== null) {
            const lang = m[1] ? detectLanguage(m[2], m[1]) : 'typescript';
            const code = m[2].trim();
            if (code.length >= 30) {
                units.push({
                    name: `Library: ${file.replace('.md', '')}`,
                    kind: 'full_file',
                    code: code.substring(0, 2000),
                    language: lang,
                    filePath: `library/${file}`,
                });
            }
        }
    }
    return units;
}
const syntheticTemplates = [];
function registerSyntheticTemplates() {
    // TypeScript function patterns
    const tsFuncNames = ['fetchData', 'processUser', 'validateInput', 'transformResponse',
        'calculateStats', 'formatOutput', 'parseConfig', 'mergeResults', 'sortItems', 'filterArray',
        'getUserById', 'createRecord', 'updateEntry', 'deleteItem', 'searchResults',
        'handleError', 'buildQuery', 'renderView', 'parseDate', 'generateToken',
        'serializeData', 'deserializeInput', 'mapCollection', 'reduceMetrics', 'aggregateStats'];
    const tsReturnTypes = ['Promise<T>', 'string', 'number', 'boolean', 'void', 'Record<string, T>', 'T[]'];
    for (let i = 0; i < 500; i++) {
        const base = i % tsFuncNames.length;
        const fn = tsFuncNames[base];
        const rt = tsReturnTypes[i % tsReturnTypes.length];
        const variant = Math.floor(i / tsFuncNames.length);
        syntheticTemplates.push({
            name: `ts-func-${fn}-v${variant}`,
            language: 'typescript',
            nodeType: 'logic',
            generate: (seed) => {
                const num = seed % 100;
                const code = [
                    `/**`,
                    ` * ${fn} — Generated function variant ${num}`,
                    ` */`,
                    `export async function ${fn}${num}(input: ${rt}, options?: { debug?: boolean; timeout?: number }): ${rt} {`,
                    `  try {`,
                    `    const result = await processInput(input, options);`,
                    `    return transform${num}(result);`,
                    `  } catch (error) {`,
                    `    console.error(\`[${fn}] Failed:\`, error);`,
                    `    throw new Error(\`${fn} failed: \${error.message}\`);`,
                    `  }`,
                    `}`,
                    ``,
                    `async function processInput(input: ${rt}, opts?: { debug?: boolean; timeout?: number }): ${rt} {`,
                    `  const config = { ...opts, timestamp: Date.now() };`,
                    `  if (config.debug) {`,
                    `    console.log('[DEBUG] Processing:', JSON.stringify(input));`,
                    `  }`,
                    `  return input;`,
                    `}`,
                    ``,
                    `function transform${num}(data: ${rt}): ${rt} {`,
                    `  if (Array.isArray(data)) {`,
                    `    return data.map(item => ({ ...item, processed: true, ts: Date.now() })) as unknown as ${rt};`,
                    `  }`,
                    `  if (typeof data === 'object' && data !== null) {`,
                    `    return { ...data, transformed: true, version: ${num} } as ${rt};`,
                    `  }`,
                    `  return data;`,
                    `}`,
                ].join('\n');
                return {
                    code,
                    title: `${fn} — Async processing function (variant ${num})`,
                    description: `TypeScript async function that processes input with error handling, debug logging, and transformation. Pattern variant ${num} of ${fn}.`,
                    tags: ['typescript', 'async', 'function', 'logic', `variant-${num}`],
                };
            },
        });
    }
    // Go function patterns
    const goFuncNames = ['HandleRequest', 'ProcessData', 'ValidateSchema', 'ExecuteCommand',
        'QueryDatabase', 'TransformPayload', 'ParseMessage', 'MergeConfig', 'GenerateReport',
        'SerializeOutput', 'DeserializeInput', 'MapCollection', 'ReduceMetrics', 'AggregateStats'];
    for (let i = 0; i < 500; i++) {
        const fn = goFuncNames[i % goFuncNames.length];
        const variant = Math.floor(i / goFuncNames.length);
        syntheticTemplates.push({
            name: `go-func-${fn}-v${variant}`,
            language: 'go',
            nodeType: 'logic',
            generate: (seed) => {
                const num = seed % 50;
                const code = [
                    `package handler`,
                    ``,
                    `import (`,
                    `\t"context"`,
                    `\t"fmt"`,
                    `\t"time"`,
                    `)`,
                    ``,
                    `// ${fn} handles the request with variant ${variant}${num}`,
                    `func ${fn}(ctx context.Context, input string) (string, error) {`,
                    `\tif input == "" {`,
                    `\t\treturn "", fmt.Errorf("${fn}: empty input")`,
                    `\t}`,
                    ``,
                    `\tresult, err := process${fn}Input(ctx, input, ${num})`,
                    `\tif err != nil {`,
                    `\t\treturn "", fmt.Errorf("${fn}: %w", err)`,
                    `\t}`,
                    ``,
                    `\treturn result, nil`,
                    `}`,
                    ``,
                    `func process${fn}Input(ctx context.Context, data string, variant int) (string, error) {`,
                    `\tselect {`,
                    `\tcase <-ctx.Done():`,
                    `\t\treturn "", ctx.Err()`,
                    `\tdefault:`,
                    `\t}`,
                    ``,
                    `\tresult := fmt.Sprintf("[%s] Processed variant %d: %s", time.Now().Format(time.RFC3339), variant, data)`,
                    `\treturn result, nil`,
                    `}`,
                ].join('\n');
                return {
                    code,
                    title: `${fn} — Go handler function (variant ${variant}${num})`,
                    description: `Go function that handles ${fn.toLowerCase()} with context, error handling, and timeouts. Pattern variant ${variant} in the Go function series.`,
                    tags: ['go', 'function', 'handler', 'logic', 'concurrent'],
                };
            },
        });
    }
    // Python function patterns
    const pyFuncNames = ['process_data', 'handle_request', 'validate_schema', 'transform_payload',
        'query_database', 'parse_config', 'generate_report', 'merge_results', 'calculate_metrics',
        'serialize_output', 'deserialize_input', 'map_collection', 'reduce_metrics'];
    for (let i = 0; i < 500; i++) {
        const fn = pyFuncNames[i % pyFuncNames.length];
        const variant = Math.floor(i / pyFuncNames.length);
        syntheticTemplates.push({
            name: `py-func-${fn}-v${variant}`,
            language: 'python',
            nodeType: 'logic',
            generate: (seed) => {
                const num = seed % 60;
                const code = [
                    `"""${fn.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())} — Generated pattern variant ${variant}${num}"""`,
                    ``,
                    `import json`,
                    `import logging`,
                    `from typing import Any, Optional`,
                    `from datetime import datetime`,
                    ``,
                    `logger = logging.getLogger(__name__)`,
                    ``,
                    ``,
                    `async def ${fn}(`,
                    `    input_data: Any,`,
                    `    options: Optional[dict] = None,`,
                    `) -> dict:`,
                    `    """Process input data with ${fn.replace(/_/g, ' ')} logic."""`,
                    `    opts = options or {}`,
                    `    debug = opts.get("debug", False)`,
                    `    `,
                    `    if debug:`,
                    `        logger.debug(f"Processing variant ${variant}${num}: {json.dumps(str(input_data))[:200]}")`,
                    `    `,
                    `    try:`,
                    `        result = await _process_internal(input_data, variant=${num})`,
                    `        return {`,
                    `            "success": True,`,
                    `            "data": result,`,
                    `            "variant": ${num},`,
                    `            "timestamp": datetime.utcnow().isoformat(),`,
                    `        }`,
                    `    except Exception as e:`,
                    `        logger.error(f"${fn} failed: {e}")`,
                    `        return {`,
                    `            "success": False,`,
                    `            "error": str(e),`,
                    `            "variant": ${num},`,
                    `        }`,
                    ``,
                    ``,
                    `async def _process_internal(data: Any, variant: int) -> Any:`,
                    `    """Internal processing with variant-specific behavior."""`,
                    `    if isinstance(data, dict):`,
                    `        return {k: f"processed_{v}" if isinstance(v, str) else v for k, v in data.items()}`,
                    `    elif isinstance(data, list):`,
                    `        return [item for item in data if item is not None][:variant + 10]`,
                    `    elif isinstance(data, str):`,
                    `        return data.strip().upper()`,
                    `    return data`,
                ].join('\n');
                return {
                    code,
                    title: `${fn} — Python async processor (variant ${variant}${num})`,
                    description: `Python async function that processes data with structured error handling, logging, and variant-specific behavior. Variant ${variant} of ${fn}.`,
                    tags: ['python', 'async', 'function', 'logic', 'processing'],
                };
            },
        });
    }
    // TypeScript class patterns
    const tsClassNames = ['UserService', 'DataProvider', 'ConfigManager', 'EventEmitter', 'CacheStore',
        'AuthHandler', 'QueueProcessor', 'TemplateEngine', 'StateManager', 'LoggerAdapter'];
    const tsMethods = ['initialize', 'execute', 'validate', 'transform', 'dispatch',
        'process', 'handle', 'render', 'compute', 'analyze'];
    for (let i = 0; i < 300; i++) {
        const className = tsClassNames[i % tsClassNames.length];
        const method = tsMethods[Math.floor(i / tsClassNames.length) % tsMethods.length];
        syntheticTemplates.push({
            name: `ts-class-${className}-${method}`,
            language: 'typescript',
            nodeType: 'ui-functions',
            generate: (seed) => {
                const num = seed % 30;
                const code = [
                    `/**`,
                    ` * ${className} — Service class for pattern generation (variant ${num})`,
                    ` */`,
                    `export class ${className} {`,
                    `  private initialized = false;`,
                    `  private config: Record<string, unknown>;`,
                    ``,
                    `  constructor(config?: Partial<Record<string, unknown>>) {`,
                    `    this.config = {`,
                    `      retries: 3,`,
                    `      timeout: 5000,`,
                    `      debug: false,`,
                    `      version: ${num},`,
                    `      ...config,`,
                    `    };`,
                    `  }`,
                    ``,
                    `  async ${method}(input: unknown): Promise<unknown> {`,
                    `    if (!this.initialized) {`,
                    `      await this.initialize();`,
                    `    }`,
                    ``,
                    `    try {`,
                    `      const result = await this.processInternal(input);`,
                    `      return result;`,
                    `    } catch (error) {`,
                    `      console.error(\`[${className}] ${method} failed:\`, error);`,
                    `      throw error;`,
                    `    }`,
                    `  }`,
                    ``,
                    `  private async initialize(): Promise<void> {`,
                    `    this.initialized = true;`,
                    `  }`,
                    ``,
                    `  private async processInternal(input: unknown): Promise<unknown> {`,
                    `    return { input, processed: true, timestamp: Date.now(), variant: ${num} };`,
                    `  }`,
                    ``,
                    `  getStatus(): { ready: boolean; variant: number } {`,
                    `    return { ready: this.initialized, variant: ${num} };`,
                    `  }`,
                    `}`,
                ].join('\n');
                return {
                    code,
                    title: `${className}.${method} — Service class (variant ${num})`,
                    description: `TypeScript service class with ${method} method, configuration, initialization lifecycle, and error handling. Variant ${num}.`,
                    tags: ['typescript', 'class', 'service', 'ui-functions'],
                };
            },
        });
    }
    // Go struct patterns
    const goStructNames = ['Config', 'Request', 'Response', 'Handler', 'Service',
        'Repository', 'Middleware', 'Controller', 'Adapter', 'Builder'];
    for (let i = 0; i < 200; i++) {
        const structName = goStructNames[i % goStructNames.length];
        syntheticTemplates.push({
            name: 'go-struct-' + structName,
            language: 'go',
            nodeType: 'database',
            generate: (seed) => {
                const num = seed % 40;
                const code = [
                    'package models',
                    '',
                    'import (',
                    '\t"fmt"',
                    '\t"time"',
                    ')',
                    '',
                    `// ${structName}${num} represents a data model with variant ${num}`,
                    `type ${structName}${num} struct {`,
                    `\tID        string    \`json:"id"\``,
                    `\tName      string    \`json:"name"\``,
                    `\tVariant   int       \`json:"variant"\``,
                    `\tCreatedAt time.Time \`json:"created_at"\``,
                    `\tUpdatedAt time.Time \`json:"updated_at"\``,
                    `\tMetadata  map[string]interface{} \`json:"metadata,omitempty"\``,
                    `}`,
                    '',
                    `// New${structName}${num} creates a new instance`,
                    `func New${structName}${num}(name string) *${structName}${num} {`,
                    `\treturn &${structName}${num}{`,
                    `\t\tID:        generateID(),`,
                    `\t\tName:      name,`,
                    `\t\tVariant:   ${num},`,
                    `\t\tCreatedAt: time.Now(),`,
                    `\t\tUpdatedAt: time.Now(),`,
                    `\t\tMetadata:  make(map[string]interface{}),`,
                    `\t}`,
                    `}`,
                    ``,
                    `func generateID() string {`,
                    `\treturn fmt.Sprintf("%s-%d", time.Now().Format("20060102150405"), ${num})`,
                    `}`,
                ].join('\n');
                return {
                    code,
                    title: `${structName}${num} — Go data model (variant ${num})`,
                    description: `Go struct representing a ${structName.toLowerCase()} data model with JSON tags, constructor, and ID generation. Variant ${num}.`,
                    tags: ['go', 'struct', 'model', 'database'],
                };
            },
        });
    }
    // Python class patterns
    const pyClassName = ['DataProcessor', 'ConfigLoader', 'RequestHandler', 'ResultBuilder',
        'CacheManager', 'EventDispatcher', 'MetricsCollector', 'TemplateRenderer'];
    for (let i = 0; i < 200; i++) {
        const className = pyClassName[i % pyClassName.length];
        syntheticTemplates.push({
            name: 'py-class-' + className,
            language: 'python',
            nodeType: 'logic',
            generate: (seed) => {
                const num = seed % 50;
                const code = [
                    `"""${className} — Python class pattern variant ${num}"""`,
                    ``,
                    `import json`,
                    `import time`,
                    `from typing import Any, Optional`,
                    `from dataclasses import dataclass, field`,
                    ``,
                    ``,
                    `@dataclass`,
                    `class ${className}:`,
                    `    """${className.replace(/([A-Z])/g, ' $1').trim()} — variant ${num}."""`,
                    `    name: str`,
                    `    options: Optional[dict] = None`,
                    `    _initialized: bool = field(default=False, repr=False)`,
                    `    _data: dict = field(default_factory=dict, repr=False)`,
                    `    variant: int = ${num}`,
                    ``,
                    `    def __post_init__(self):`,
                    `        self.options = self.options or {}`,
                    `        self._data = {"created": time.time(), "variant": self.variant}`,
                    ``,
                    `    async def process(self, input_data: Any) -> dict:`,
                    `        """Process input data through this ${className} instance."""`,
                    `        if not self._initialized:`,
                    `            await self._initialize()`,
                    `        `,
                    `        result = {`,
                    `            "input": str(input_data)[:100],`,
                    `            "processed": True,`,
                    `            "variant": self.variant,`,
                    `            "timestamp": time.time(),`,
                    `        }`,
                    `        return result`,
                    ``,
                    `    async def _initialize(self):`,
                    `        """Initialize the processor."""`,
                    `        self._initialized = True`,
                    `        self._data["initialized_at"] = time.time()`,
                    ``,
                    `    def to_dict(self) -> dict:`,
                    `        """Serialize to dictionary."""`,
                    `        return {`,
                    `            "name": self.name,`,
                    `            "variant": self.variant,`,
                    `            "initialized": self._initialized,`,
                    `        }`,
                ].join('\n');
                return {
                    code,
                    title: `${className} — Python dataclass (variant ${num})`,
                    description: `Python dataclass-based ${className.toLowerCase()} with async processing, serialization, and variant ${num} configuration.`,
                    tags: ['python', 'class', 'dataclass', 'logic'],
                };
            },
        });
    }
    // TypeScript React component patterns
    const compNames = ['DataTable', 'UserProfile', 'ConfigPanel', 'SearchBar', 'NotificationList',
        'ChartWidget', 'FormBuilder', 'ModalDialog', 'SidebarNav', 'BreadcrumbTrail',
        'FileUploader', 'ProgressBar', 'DropdownMenu', 'TabPanel', 'AccordionGroup'];
    for (let i = 0; i < 300; i++) {
        const compName = compNames[i % compNames.length];
        syntheticTemplates.push({
            name: 'ts-react-' + compName,
            language: 'typescript',
            nodeType: 'ui',
            generate: (seed) => {
                const num = seed % 30;
                const code = [
                    `import React, { useState, useEffect, useCallback } from 'react';`,
                    ``,
                    `interface ${compName}Props {`,
                    `  id?: string;`,
                    `  title?: string;`,
                    `  variant?: number;`,
                    `  onAction?: (action: string) => void;`,
                    `  children?: React.ReactNode;`,
                    `}`,
                    ``,
                    `/**`,
                    ` * ${compName} — React component variant ${num}`,
                    ` */`,
                    `export const ${compName}: React.FC<${compName}Props> = ({`,
                    `  id = 'default',`,
                    `  title = '${compName}',`,
                    `  variant = ${num},`,
                    `  onAction,`,
                    `  children,`,
                    `}) => {`,
                    `  const [isActive, setIsActive] = useState<boolean>(false);`,
                    `  const [count, setCount] = useState(0);`,
                    ``,
                    `  useEffect(() => {`,
                    `    console.log(\`[${compName}] Mounted variant \${variant}\`);`,
                    `    return () => console.log(\`[${compName}] Unmounted\`);`,
                    `  }, [variant]);`,
                    ``,
                    `  const handleClick = useCallback(() => {`,
                    `    setIsActive(prev => !prev);`,
                    `    setCount(c => c + 1);`,
                    `    onAction?.(\`click-\${id}\`);`,
                    `  }, [id, onAction]);`,
                    ``,
                    `  return (`,
                    `    <div className={\`comp-\${id} \${isActive ? 'active' : ''}\`}>`,
                    `      <h3>{title}</h3>`,
                    `      <p>Variant: {variant} | Clicks: {count}</p>`,
                    `      <button onClick={handleClick}>`,
                    `        {isActive ? 'Deactivate' : 'Activate'}`,
                    `      </button>`,
                    `      {children && <div className="content">{children}</div>}`,
                    `    </div>`,
                    `  );`,
                    `};`,
                    ``,
                    `export default ${compName};`,
                ].join('\n');
                return {
                    code,
                    title: `${compName} — React component (variant ${num})`,
                    description: `React functional component with useState, useEffect, useCallback hooks, state management, and event handling. Variant ${num}.`,
                    tags: ['typescript', 'react', 'component', 'ui'],
                };
            },
        });
    }
    // API route handlers
    const routeNames = ['users', 'posts', 'config', 'events', 'metrics', 'assets', 'tasks', 'jobs', 'logs', 'files'];
    const httpMethods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];
    for (let i = 0; i < 200; i++) {
        const route = routeNames[i % routeNames.length];
        const method = httpMethods[Math.floor(i / routeNames.length) % httpMethods.length];
        syntheticTemplates.push({
            name: `api-${method}-${route}`,
            language: 'typescript',
            nodeType: 'api',
            generate: (seed) => {
                const num = seed % 40;
                const typeName = route.charAt(0).toUpperCase() + route.slice(1).replace(/s$/, '');
                const code = [
                    `import { Router, Request, Response } from 'express';`,
                    ``,
                    `const router = Router();`,
                    ``,
                    `interface ${typeName}Params {`,
                    `  id: string;`,
                    `  variant: number;`,
                    `}`,
                    ``,
                    `/**`,
                    ` * ${method} /api/${route}/:id — Handler variant ${num}`,
                    ` */`,
                    `router.${method.toLowerCase()}('/${route}/:id', async (req: Request<${typeName}Params>, res: Response) => {`,
                    `  try {`,
                    `    const { id } = req.params;`,
                    `    const variant = ${num};`,
                    ``,
                    `    const result = await handle${typeName}Request(id, variant);`,
                    `    `,
                    `    res.json({`,
                    `      success: true,`,
                    `      data: result,`,
                    `      variant,`,
                    `      timestamp: new Date().toISOString(),`,
                    `    });`,
                    `  } catch (error: any) {`,
                    `    res.status(500).json({`,
                    `      success: false,`,
                    `      error: error.message,`,
                    `    });`,
                    `  }`,
                    `});`,
                    ``,
                    `async function handle${typeName}Request(id: string, variant: number): Promise<Record<string, unknown>> {`,
                    `  return {`,
                    `    id,`,
                    `    variant,`,
                    `    processed: true,`,
                    `    timestamp: Date.now(),`,
                    `  };`,
                    `}`,
                    ``,
                    `export default router;`,
                ].join('\n');
                return {
                    code,
                    title: `${method} /api/${route} — Express route handler (variant ${num})`,
                    description: `Express route handler for ${method} /api/${route}/:id with TypeScript types, error handling, and variant ${num} processing.`,
                    tags: ['typescript', 'express', 'api', 'route'],
                };
            },
        });
    }
}
function generateSyntheticVariations(count) {
    registerSyntheticTemplates();
    const units = [];
    const perTemplate = Math.ceil(count / syntheticTemplates.length);
    for (let ti = 0; ti < syntheticTemplates.length; ti++) {
        const template = syntheticTemplates[ti];
        for (let vi = 0; vi < perTemplate; vi++) {
            if (units.length >= count)
                break;
            const seed = ti * 1000 + vi;
            const { code, title, description, tags } = template.generate(seed);
            units.push({
                name: title,
                kind: 'full_file',
                code: code.substring(0, 2000),
                language: template.language,
                filePath: `synthetic/${template.name}/v${vi}`,
            });
        }
        if (units.length >= count)
            break;
    }
    return units;
}
// ─── 7. Main Generator ─────────────────────────────────────────────
function unitsToPatterns(units) {
    const patterns = [];
    const seen = new Set();
    const baseTime = Date.now();
    for (let idx = 0; idx < units.length; idx++) {
        const unit = units[idx];
        const key = `${unit.language}:${unit.kind}:${unit.name}:${unit.code.substring(0, 100)}`;
        if (seen.has(key))
            continue;
        seen.add(key);
        const code = unit.code.substring(0, 2000);
        if (code.length < 30)
            continue;
        const nodeType = unit.kind === 'class' ? 'ui-functions' :
            unit.kind === 'interface' || unit.kind === 'type' ? 'database' :
                'logic';
        const tags = [unit.language, unit.kind, nodeType];
        if (unit.filePath) {
            tags.push(unit.filePath.replace(/\//g, '-').replace(/\./g, '-').substring(0, 40));
        }
        const fileName = unit.name.substring(0, 80);
        const now = new Date(baseTime + idx).toISOString();
        patterns.push({
            id: `pat_${baseTime}_${Math.random().toString(36).substr(2, 10)}`,
            category: 'code_pattern',
            title: `${fileName} — ${unit.kind} pattern in ${unit.language}`,
            code,
            description: `Extracted ${unit.kind} "${unit.name}" from ${unit.filePath}. Language: ${unit.language}.`,
            tags,
            projectId: 'bulk-generator',
            targetOS: 'linux',
            nodeType,
            language: unit.language,
            success: true,
            qualityScore: unit.filePath.startsWith('synthetic/') ? 5.0 : 7.0,
            usageCount: 0,
            createdAt: now,
            lastUsed: now,
        });
    }
    return patterns;
}
function generateSheetArchives(patterns, sheetCap = 100) {
    const sheetsDir = path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
    if (!fs.existsSync(sheetsDir)) {
        fs.mkdirSync(sheetsDir, { recursive: true });
    }
    let sheetNum = 1;
    const batchTimestamp = Date.now();
    for (let i = 0; i < patterns.length; i += sheetCap) {
        const chunk = patterns.slice(i, i + sheetCap);
        const filename = `venorica-sheet-${String(sheetNum).padStart(3, '0')}-bulk-${batchTimestamp}.jsonl`;
        const filepath = path.join(sheetsDir, filename);
        const lines = chunk.map(p => JSON.stringify({
            text: p.code,
            title: p.title,
            language: p.language,
            nodeType: p.nodeType,
            tags: p.tags,
            sheet: sheetNum,
            source: 'venorica-bulk-generator',
            timestamp: p.createdAt,
        }));
        fs.writeFileSync(filepath, lines.join('\n'), 'utf-8');
        process.stdout.write(`\r  Sheet #${sheetNum}: ${chunk.length} patterns → ${filename}`);
        sheetNum++;
    }
    console.log();
}
async function main() {
    console.log('╔══════════════════════════════════════════════════════════════╗');
    console.log('║       Venorica 50,000 Pattern Generator                     ║');
    console.log('╚══════════════════════════════════════════════════════════════╝');
    console.log();
    const startTime = Date.now();
    const allUnits = [];
    // Step 1: Source File Scanning
    console.log('📁 Step 1/5: Scanning project source files...');
    const srcDirs = [
        path.join(PROJECT_ROOT, 'backend', 'src'),
        path.join(PROJECT_ROOT, 'frontend', 'src'),
        path.join(PROJECT_ROOT, 'scripts'),
        path.join(PROJECT_ROOT, 'data'),
        path.join(PROJECT_ROOT, 'training'),
    ];
    const sourceFiles = collectSourceFiles(srcDirs);
    console.log(`  Found ${sourceFiles.length} source files`);
    for (const file of sourceFiles) {
        const units = extractUnits(file);
        allUnits.push(...units);
    }
    console.log(`  Extracted ${allUnits.length.toLocaleString()} units from source files`);
    // Step 2: Training Data Parsing
    console.log('\n📖 Step 2/5: Parsing training datasets...');
    const trainingDir = path.join(PROJECT_ROOT, 'training', 'dataset');
    if (fs.existsSync(trainingDir)) {
        for (const file of fs.readdirSync(trainingDir)) {
            if (file.endsWith('.jsonl')) {
                const units = parseTrainingData(path.join(trainingDir, file));
                allUnits.push(...units);
                console.log(`  ${file}: ${units.length} patterns`);
            }
        }
    }
    else {
        console.log('  Training dataset directory not found, skipping.');
    }
    // Step 3: Export Project Scanning
    console.log('\n🚀 Step 3/5: Scanning export projects...');
    const exportsDir = path.join(BACKEND_DIR, 'exports');
    if (fs.existsSync(exportsDir)) {
        const exportUnits = scanExports(exportsDir);
        allUnits.push(...exportUnits);
        console.log(`  ${exportUnits.length} units from export projects`);
    }
    else {
        console.log('  Exports directory not found, skipping.');
    }
    // Step 4: Library Documentation
    console.log('\n📚 Step 4/5: Parsing library documentation...');
    const libraryDir = path.join(PROJECT_ROOT, 'data', 'library');
    if (fs.existsSync(libraryDir)) {
        const libUnits = parseLibraryDocs(libraryDir);
        allUnits.push(...libUnits);
        console.log(`  ${libUnits.length} units from library docs`);
    }
    else {
        console.log('  Library directory not found, skipping.');
    }
    // De-duplicate
    const uniqueMap = new Map();
    for (const unit of allUnits) {
        const key = `${unit.language}:${unit.kind}:${unit.code.substring(0, 80)}`;
        if (!uniqueMap.has(key)) {
            uniqueMap.set(key, unit);
        }
    }
    const uniqueUnits = Array.from(uniqueMap.values());
    console.log(`\n  After dedup: ${uniqueUnits.length.toLocaleString()} unique units (from ${allUnits.length.toLocaleString()} total)`);
    // Step 5: Synthetic Generation
    const realCount = uniqueUnits.length;
    const syntheticNeeded = Math.max(0, TARGET - realCount);
    console.log(`\n🤖 Step 5/5: Generating ${syntheticNeeded.toLocaleString()} synthetic patterns...`);
    if (syntheticNeeded > 0) {
        const syntheticUnits = generateSyntheticVariations(syntheticNeeded);
        uniqueUnits.push(...syntheticUnits);
        console.log(`  Generated ${syntheticUnits.length.toLocaleString()} synthetic patterns`);
    }
    // Convert to patterns
    console.log('\n🔄 Converting to pattern entries...');
    const patterns = unitsToPatterns(uniqueUnits);
    const finalCount = Math.min(patterns.length, TARGET);
    const finalPatterns = patterns.slice(0, finalCount);
    console.log(`  Total patterns: ${finalPatterns.length.toLocaleString()}`);
    // Save the active patterns.json (last 100 for live use)
    const activePatterns = finalPatterns.slice(0, Math.min(100, finalPatterns.length));
    const knowledgeDir = path.join(BACKEND_DIR, 'knowledge');
    if (!fs.existsSync(knowledgeDir)) {
        fs.mkdirSync(knowledgeDir, { recursive: true });
    }
    const patternsPath = path.join(knowledgeDir, 'patterns.json');
    fs.writeFileSync(patternsPath, JSON.stringify(activePatterns, null, 2), 'utf-8');
    console.log(`\n✅ Saved ${activePatterns.length} active patterns to patterns.json`);
    // Archive all patterns into sheets
    console.log('\n📦 Archiving all patterns into training sheets...');
    generateSheetArchives(finalPatterns);
    const totalSheets = Math.ceil(finalPatterns.length / 100);
    console.log(`  Total sheets: ${totalSheets}`);
    console.log(`  Total patterns archived: ${finalPatterns.length.toLocaleString()}`);
    // Summary
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const byLang = {};
    for (const p of finalPatterns) {
        byLang[p.language] = (byLang[p.language] || 0) + 1;
    }
    console.log('\n' + '='.repeat(60));
    console.log('  GENERATION SUMMARY');
    console.log('='.repeat(60));
    console.log(`  Time elapsed:       ${elapsed}s`);
    console.log(`  Total patterns:     ${finalPatterns.length.toLocaleString()}`);
    console.log(`  Active (live):      ${activePatterns.length}`);
    console.log(`  Archived (sheets):  ${(finalPatterns.length - activePatterns.length).toLocaleString()}`);
    console.log(`  Unique real units:  ${realCount.toLocaleString()}`);
    console.log(`  Synthetic units:    ${(syntheticNeeded > 0 ? syntheticNeeded : 0).toLocaleString()}`);
    console.log(`  By language:`);
    const sortedLangs = Object.entries(byLang).sort((a, b) => b[1] - a[1]);
    for (const [lang, count] of sortedLangs) {
        console.log(`    ${lang.padEnd(15)} ${count.toLocaleString().padStart(6)}`);
    }
    console.log(`\n  Active patterns saved to: ${patternsPath}`);
    console.log(`  Archived sheets saved to: ${path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads')}`);
    console.log(`\n✅ Generation complete! Restart the backend to load new patterns.`);
}
main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
