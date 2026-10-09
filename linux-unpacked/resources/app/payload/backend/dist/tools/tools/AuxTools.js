/**
 * AuxTools — Additional mini agents and utility tools for the Veronica Tool System.
 *
 * Categories: development, testing, network, data, design, diagram, monitoring, notification
 *
 * Mini Agents (use AITranslator for AI-powered tasks):
 *   - code_review_mini      Review code for bugs and improvements
 *   - doc_writer_mini       Generate documentation from code
 *   - test_writer_mini      Generate test cases from code
 *   - refactor_mini         Suggest code refactors
 *   - explain_code_mini     Explain code in plain language
 *
 * Utility Tools (direct Node.js APIs):
 *   - json_query            Query/filter JSON data using dot notation
 *   - csv_parse             Parse CSV text to structured data
 *   - json_to_csv           Convert JSON array to CSV
 *   - data_validate         Validate data against JSON schema
 *   - http_request          Make HTTP requests (GET/POST/PUT/DELETE)
 *   - url_analyze           Analyze and validate URLs
 *   - git_status            Get git repository status
 *   - git_log               Get recent git commit history
 *   - uuid_gen              Generate UUIDs (v4)
 *   - hash_text             Generate hash of text (MD5, SHA1, SHA256)
 *   - system_info           Get system hardware/OS info
 *   - network_info          Get network interface info
 *   - diagram_flow          Generate Mermaid flow diagrams from descriptions
 *   - notify_send           Send OS desktop notification
 *   - design_search         Search the design library for existing designs
 */
import { execSync } from 'child_process';
import { networkInterfaces, cpus, totalmem, freemem, type, hostname } from 'os';
import { randomUUID, createHash } from 'crypto';
import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';
// ─── Lazy imports (loaded on first use) ─────────────────────────────────────
async function getTranslator() {
    const mod = await import('../../ai/translator.js');
    return mod;
}
// ─── LLM Fallback Helper ────────────────────────────────────────────────────
// When the LLM is not connected (e.g. Ollama not running), return a helpful
// explanation instead of a raw connection error.
function isLLMConnectionError(err) {
    const msg = (err instanceof Error ? err.message : String(err)).toLowerCase();
    return /econnrefused|fetch failed|connection error|connect econnrefused|ollama|translator.*error|reasoning.*failed/i.test(msg);
}
function llmFallbackResponse(toolName, hint, primaryField) {
    const data = {
        _fallback: true,
        _notice: `LLM not available — ${toolName} requires a local LLM server: DSpark on port 8000 (scripts/start-dspark.sh) or ollama serve. Showing guidance instead.`,
        guidance: hint,
    };
    if (primaryField) {
        data[primaryField] = hint;
    }
    return { success: true, data };
}
// ═════════════════════════════════════════════════════════════════════════════
// SECTION 1 — Mini Agents (AI-powered using AITranslator)
// ═════════════════════════════════════════════════════════════════════════════
// ─── Finding Counter (used by code_review_mini) ─────────────────────────────
// Counts ACTUAL findings from the LLM's list output instead of matching
// severity words. Handles "1." / "1)" numbered lists, "-" / "•" bullets, and
// "Finding N:" / "Issue N:" labels. Returns 0 for prose-only output (an
// honest "couldn't parse" rather than a wrong number).
export function countReviewFindings(review) {
    const lines = review.split('\n');
    // Require whitespace after the delimiter so decimals (0.5, 3.14) and
    // version numbers at line start inside fix code blocks aren't miscounted.
    const numbered = lines.filter((l) => /^\s*\d+[.)]\s+/.test(l)).length;
    if (numbered > 0)
        return numbered;
    const bullets = lines.filter((l) => /^\s*[-*•]\s+/.test(l)).length;
    if (bullets > 0)
        return bullets;
    return lines.filter((l) => /^\s*(?:finding|issue)\s*\d+\b\s*[:.]/i.test(l)).length;
}
const codeReviewMiniDef = {
    name: 'code_review_mini',
    description: 'Review source code for bugs, security issues, performance problems, and style improvements using AI',
    category: 'development',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            code: { type: 'string', description: 'Source code to review' },
            language: { type: 'string', description: 'Programming language (auto-detected if omitted)', required: false },
            focus: { type: 'string', description: 'Review focus area', enum: ['bugs', 'security', 'performance', 'style', 'all'], default: 'all' },
        },
        required: ['code'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const lang = input.language || 'unknown';
            const focusMap = {
                bugs: 'bugs and logic errors',
                security: 'security vulnerabilities',
                performance: 'performance bottlenecks',
                style: 'code style and readability',
                all: 'bugs, security, performance, and style',
            };
            const focusText = focusMap[input.focus || 'all'];
            const result = await translator.reason(`Review this ${lang} code focusing on ${focusText}. List each issue with line numbers, severity (critical/major/minor), and concrete fix suggestions.\n\n\`\`\`${lang}\n${input.code}\n\`\`\``, 'You are an expert code reviewer. Be thorough, specific, and constructive. Return findings as a structured list with severity ratings.', { maxTokens: 2048 });
            const issueCount = countReviewFindings(result);
            return { success: true, data: { review: result, issues: issueCount } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('code_review_mini', 'To review code manually, check for:\n' +
                    '  • Null pointer dereferences and undefined variables\n' +
                    '  • Off-by-one errors in loops and array access\n' +
                    '  • Unhandled promise rejections and async errors\n' +
                    '  • SQL injection and XSS vulnerabilities\n' +
                    '  • Memory leaks (unclosed connections, listeners)\n' +
                    '  • Type mismatches and missing edge cases\n' +
                    '  • Hardcoded secrets and credentials\n' +
                    'Start the DSpark LLM server (port 8000): scripts/start-dspark.sh  (or ollama serve) then retry this tool', 'review');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'CODE_REVIEW_ERROR' };
        }
    },
};
const docWriterMiniDef = {
    name: 'doc_writer_mini',
    description: 'Generate documentation (JSDoc, comments, markdown, or README) from source code using AI',
    category: 'development',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            code: { type: 'string', description: 'Source code to document' },
            language: { type: 'string', description: 'Programming language', required: false },
            style: { type: 'string', description: 'Documentation format', enum: ['jsdoc', 'comments', 'markdown', 'readme'], default: 'jsdoc' },
        },
        required: ['code'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const lang = input.language || 'source';
            const styleInstructions = {
                jsdoc: 'Add JSDoc-style documentation comments above each function, class, and interface.',
                comments: 'Add inline comments explaining the logic and purpose of key sections.',
                markdown: 'Generate a Markdown API reference document covering all exported symbols.',
                readme: 'Generate a README.md section explaining what this code does, how to use it, and its API.',
            };
            const result = await translator.reason(`Document this ${lang} code in ${input.style} format:\n\n\`\`\`${lang}\n${input.code}\n\`\`\`\n\n${styleInstructions[input.style || 'jsdoc']}`, 'You are a technical documentation expert. Generate clear, concise, and accurate documentation.', { maxTokens: 2048 });
            return { success: true, data: { documentation: result } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('doc_writer_mini', 'To document code manually:\n' +
                    '  • Add JSDoc/TSDoc comments above each exported function explaining parameters and return values\n' +
                    '  • Describe the purpose of each class and its public methods\n' +
                    '  • Include @example tags for complex functions\n' +
                    '  • Document edge cases and error conditions\n' +
                    '  • Keep comments concise and focused on WHY not WHAT\n' +
                    'Start the DSpark LLM server (port 8000): scripts/start-dspark.sh  (or ollama serve) then retry this tool', 'documentation');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'DOC_WRITER_ERROR' };
        }
    },
};
const testWriterMiniDef = {
    name: 'test_writer_mini',
    description: 'Generate unit tests for source code using AI (Vitest, Jest, pytest, etc.)',
    category: 'testing',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            code: { type: 'string', description: 'Source code to generate tests for' },
            language: { type: 'string', description: 'Programming language', required: false },
            framework: { type: 'string', description: 'Test framework (vitest, jest, pytest, etc.)', default: 'vitest' },
        },
        required: ['code'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const lang = input.language || 'typescript';
            const framework = input.framework || 'vitest';
            const result = await translator.reason(`Generate comprehensive ${framework} unit tests for this ${lang} code. Cover all functions, edge cases, and error paths.\n\n\`\`\`${lang}\n${input.code}\n\`\`\``, `You are an expert in ${framework} testing. Generate thorough, well-structured test cases. Include describe/it blocks, mocks where needed, and edge case coverage.`, { maxTokens: 3072 });
            return { success: true, data: { tests: result } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('test_writer_mini', 'To write tests manually:\n' +
                    '  • Test happy path: normal inputs produce expected outputs\n' +
                    '  • Test edge cases: empty inputs, null, boundary values\n' +
                    '  • Test error paths: invalid inputs produce proper errors\n' +
                    '  • Test async code: promises resolve/reject, timeouts\n' +
                    '  • Mock external dependencies (APIs, databases, filesystem)\n' +
                    '  • Aim for >80% code coverage on critical paths\n' +
                    'Start the DSpark LLM server (port 8000): scripts/start-dspark.sh  (or ollama serve) then retry this tool', 'tests');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'TEST_WRITER_ERROR' };
        }
    },
};
const refactorMiniDef = {
    name: 'refactor_mini',
    description: 'Analyze and suggest refactoring improvements for code using AI',
    category: 'development',
    riskLevel: 'medium',
    inputSchema: {
        type: 'object',
        properties: {
            code: { type: 'string', description: 'Source code to refactor' },
            language: { type: 'string', description: 'Programming language', required: false },
            goal: { type: 'string', description: 'Refactoring goal (e.g., "extract functions", "reduce complexity", "add types")', default: 'improve readability and maintainability' },
        },
        required: ['code'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const lang = input.language || 'source';
            const goal = input.goal || 'improve readability and maintainability';
            const result = await translator.reason(`Refactor this ${lang} code with the goal: ${goal}.\nShow BOTH the original problematic patterns AND the improved code.\n\n\`\`\`${lang}\n${input.code}\n\`\`\``, 'You are an expert software architect. Provide specific, actionable refactoring suggestions with before/after code examples.', { maxTokens: 3072 });
            // Extract summary from first few lines
            const summary = result.split('\n').slice(0, 5).join('\n').trim();
            return { success: true, data: { refactored: result, summary } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('refactor_mini', 'To refactor code manually:\n' +
                    '  • Extract long functions into smaller, focused ones\n' +
                    '  • Replace repeated code with shared helpers\n' +
                    '  • Use early returns to reduce nesting depth\n' +
                    '  • Replace magic strings/numbers with named constants\n' +
                    '  • Add TypeScript types to catch errors at compile time\n' +
                    '  • Split large files into modules by responsibility\n' +
                    'Start the DSpark LLM server (port 8000): scripts/start-dspark.sh  (or ollama serve) then retry this tool', 'refactored');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'REFACTOR_ERROR' };
        }
    },
};
const explainCodeMiniDef = {
    name: 'explain_code_mini',
    description: 'Explain source code in plain language using AI at different detail levels',
    category: 'development',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            code: { type: 'string', description: 'Source code to explain' },
            language: { type: 'string', description: 'Programming language', required: false },
            level: { type: 'string', description: 'Explanation detail level', enum: ['simple', 'detailed', 'expert'], default: 'detailed' },
        },
        required: ['code'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const lang = input.language || 'code';
            const levelInstructions = {
                simple: 'Explain as if to a junior developer. Use analogies and avoid jargon.',
                detailed: 'Explain thoroughly covering what each part does, why it works, and any tradeoffs.',
                expert: 'Explain at an expert level focusing on architecture patterns, performance implications, and design choices.',
            };
            const result = await translator.reason(`Explain this ${lang} code at a "${input.level || 'detailed'}" level:\n\n\`\`\`${lang}\n${input.code}\n\`\`\`\n\n${levelInstructions[input.level || 'detailed']}`, 'You are a skilled programming teacher. Provide clear, accurate explanations tailored to the requested level.', { maxTokens: 2048 });
            return { success: true, data: { explanation: result } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('explain_code_mini', 'To understand code without AI:\n' +
                    '  • Read function signatures first — names, parameters, return types\n' +
                    '  • Trace the data flow: inputs → transformations → outputs\n' +
                    '  • Look for side effects: I/O, network calls, state mutations\n' +
                    '  • Check error handling: try/catch, error boundaries, fallbacks\n' +
                    '  • Identify the design pattern: MVC, observer, factory, etc.\n' +
                    '  • Use debugger or console.log to trace execution step by step\n' +
                    'Start the DSpark LLM server (port 8000): scripts/start-dspark.sh  (or ollama serve) then retry this tool', 'explanation');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'EXPLAIN_ERROR' };
        }
    },
};
const jsonQueryDef = {
    name: 'json_query',
    description: 'Query and extract values from JSON using dot-notation path (e.g., "users.0.name")',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            json: { type: 'string', description: 'JSON string to query' },
            path: { type: 'string', description: 'Dot-notation path (e.g., "data.users.0.name")' },
        },
        required: ['json', 'path'],
    },
    async call(input, _ctx) {
        try {
            const data = JSON.parse(input.json);
            const parts = input.path.split('.');
            let current = data;
            for (const part of parts) {
                if (current === null || current === undefined) {
                    return { success: false, error: `Path not found: ${input.path} (traversed to: ${part})`, errorCode: 'PATH_NOT_FOUND' };
                }
                if (Array.isArray(current)) {
                    const idx = parseInt(part, 10);
                    if (isNaN(idx)) {
                        // Try to access array property
                        current = current[part];
                    }
                    else {
                        current = current[idx];
                    }
                }
                else if (typeof current === 'object') {
                    current = current[part];
                }
                else {
                    return { success: false, error: `Cannot traverse into primitive at path part: ${part}`, errorCode: 'PATH_ERROR' };
                }
            }
            return { success: true, data: { result: current } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'JSON_QUERY_ERROR' };
        }
    },
};
const csvParseDef = {
    name: 'csv_parse',
    description: 'Parse CSV text into structured JSON array of objects',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            csv: { type: 'string', description: 'CSV text to parse' },
            delimiter: { type: 'string', description: 'Column delimiter', default: ',' },
            hasHeader: { type: 'boolean', description: 'Whether first row is a header', default: true },
        },
        required: ['csv'],
    },
    async call(input, _ctx) {
        try {
            const delimiter = input.delimiter || ',';
            const lines = input.csv.trim().split('\n').filter(l => l.trim());
            if (lines.length === 0) {
                return { success: false, error: 'Empty CSV input', errorCode: 'EMPTY_INPUT' };
            }
            const parseLine = (line) => {
                const result = [];
                let current = '';
                let inQuotes = false;
                for (const ch of line) {
                    if (ch === '"') {
                        inQuotes = !inQuotes;
                    }
                    else if (ch === delimiter && !inQuotes) {
                        result.push(current.trim());
                        current = '';
                    }
                    else {
                        current += ch;
                    }
                }
                result.push(current.trim());
                return result;
            };
            const headers = input.hasHeader !== false ? parseLine(lines[0]) : [];
            const dataLines = input.hasHeader !== false ? lines.slice(1) : lines;
            const columns = headers.length > 0 ? headers : parseLine(lines[0]).map((_, i) => `column_${i}`);
            const data = dataLines.map(line => {
                const values = parseLine(line);
                const row = {};
                columns.forEach((col, i) => {
                    row[col] = values[i] || '';
                });
                return row;
            });
            return { success: true, data: { data, columns, rowCount: data.length } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'CSV_PARSE_ERROR' };
        }
    },
};
const jsonToCsvDef = {
    name: 'json_to_csv',
    description: 'Convert a JSON array of objects to CSV format',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            json: { type: 'string', description: 'JSON array string to convert' },
            columns: { type: 'array', description: 'Specific columns to include (omit for all)', required: false },
        },
        required: ['json'],
    },
    async call(input, _ctx) {
        try {
            const data = JSON.parse(input.json);
            if (!Array.isArray(data)) {
                return { success: false, error: 'Input must be a JSON array', errorCode: 'NOT_ARRAY' };
            }
            if (data.length === 0) {
                return { success: true, data: { csv: '', columns: [], rowCount: 0 } };
            }
            const columns = input.columns || Object.keys(data[0]);
            const escapeCsv = (val) => {
                const str = String(val ?? '');
                if (str.includes(',') || str.includes('"') || str.includes('\n')) {
                    return `"${str.replace(/"/g, '""')}"`;
                }
                return str;
            };
            const header = columns.join(',');
            const rows = data.map(row => columns.map(col => escapeCsv(row[col])).join(','));
            const csv = [header, ...rows].join('\n');
            return { success: true, data: { csv, columns, rowCount: data.length } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'JSON_TO_CSV_ERROR' };
        }
    },
};
const dataValidateDef = {
    name: 'data_validate',
    description: 'Validate data against a simple JSON schema (check required fields, types, and patterns)',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            data: { type: 'string', description: 'JSON data string to validate' },
            schema: { type: 'object', description: 'Schema object with field definitions: { fieldName: { type: "string|number|boolean|array|object", required?: boolean, pattern?: string } }' },
        },
        required: ['data', 'schema'],
    },
    async call(input, _ctx) {
        try {
            let parsed;
            try {
                parsed = JSON.parse(input.data);
            }
            catch {
                return { success: false, error: 'Invalid JSON data', errorCode: 'INVALID_JSON' };
            }
            const errors = [];
            for (const [field, rules] of Object.entries(input.schema)) {
                const rule = rules;
                const value = parsed[field];
                // Check required
                if (rule.required && (value === undefined || value === null)) {
                    errors.push(`Missing required field: "${field}"`);
                    continue;
                }
                if (value === undefined || value === null)
                    continue;
                // Check type
                if (rule.type) {
                    const actualType = Array.isArray(value) ? 'array' : typeof value;
                    if (actualType !== rule.type) {
                        errors.push(`Field "${field}" expected type "${rule.type}", got "${actualType}"`);
                    }
                }
                // Check pattern (for strings)
                if (rule.pattern && typeof value === 'string') {
                    try {
                        const regex = new RegExp(rule.pattern);
                        if (!regex.test(value)) {
                            errors.push(`Field "${field}" does not match pattern: ${rule.pattern}`);
                        }
                    }
                    catch { /* invalid regex, skip */ }
                }
            }
            return { success: true, data: { valid: errors.length === 0, errors } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'VALIDATE_ERROR' };
        }
    },
};
const httpRequestDef = {
    name: 'http_request',
    description: 'Make HTTP requests to test and interact with API endpoints',
    category: 'network',
    riskLevel: 'medium',
    inputSchema: {
        type: 'object',
        properties: {
            url: { type: 'string', description: 'Full URL to request' },
            method: { type: 'string', description: 'HTTP method', enum: ['GET', 'POST', 'PUT', 'DELETE'], default: 'GET' },
            headers: { type: 'object', description: 'Request headers', required: false },
            body: { type: 'string', description: 'Request body (for POST/PUT)', required: false },
            timeout: { type: 'number', description: 'Timeout in ms', default: 15000 },
        },
        required: ['url'],
    },
    timeoutMs: 30000,
    async call(input, ctx) {
        const controller = new AbortController();
        const timeout = input.timeout || 15000;
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        // Connect parent signal
        ctx.signal?.addEventListener('abort', () => controller.abort(), { once: true });
        try {
            const response = await fetch(input.url, {
                method: input.method || 'GET',
                headers: {
                    ...(input.body ? { 'Content-Type': 'application/json' } : {}),
                    ...(input.headers || {}),
                },
                body: input.body || undefined,
                signal: controller.signal,
            });
            const responseHeaders = {};
            response.headers.forEach((value, key) => { responseHeaders[key] = value; });
            let body;
            const contentType = responseHeaders['content-type'] || '';
            if (contentType.includes('application/json')) {
                body = JSON.stringify(await response.json(), null, 2);
            }
            else {
                body = await response.text();
            }
            return {
                success: true,
                data: {
                    status: response.status,
                    headers: responseHeaders,
                    body: body.length > 50000 ? body.slice(0, 50000) + '\n... (truncated)' : body,
                    contentType,
                },
            };
        }
        catch (err) {
            const isAbort = err instanceof Error && err.name === 'AbortError';
            return {
                success: false,
                error: isAbort ? 'Request timed out' : (err instanceof Error ? err.message : String(err)),
                errorCode: isAbort ? 'TIMEOUT' : 'HTTP_ERROR',
            };
        }
        finally {
            clearTimeout(timeoutId);
        }
    },
};
const urlAnalyzeDef = {
    name: 'url_analyze',
    description: 'Parse, analyze, and validate a URL into its components',
    category: 'network',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            url: { type: 'string', description: 'URL to analyze' },
        },
        required: ['url'],
    },
    async call(input, _ctx) {
        try {
            let parsed;
            try {
                parsed = new URL(input.url);
            }
            catch {
                return { success: true, data: { valid: false, parts: { error: 'Invalid URL format' } } };
            }
            const parts = {
                protocol: parsed.protocol.replace(':', ''),
                hostname: parsed.hostname,
                port: parsed.port || '(default)',
                host: parsed.host,
                pathname: parsed.pathname,
                search: parsed.search || '(none)',
                hash: parsed.hash || '(none)',
                origin: parsed.origin,
            };
            // Validate protocol
            const validProtocols = ['http', 'https', 'ftp', 'ws', 'wss', 'file'];
            if (!validProtocols.includes(parts.protocol)) {
                parts.warning = `Unusual protocol: ${parts.protocol}`;
            }
            return { success: true, data: { valid: true, parts } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'URL_ERROR' };
        }
    },
};
// ═════════════════════════════════════════════════════════════════════════════
// SECTION 4 — Development Tools
// ═════════════════════════════════════════════════════════════════════════════
// ─── Shared: resolve the nearest git work-tree root ─────────────────────────
// git_status / git_log default to the server CWD (backend/), which is not the
// repo root. Walk up from CWD to the nearest ancestor containing a .git so the
// tools work regardless of where the server was started. Falls back to CWD.
export function resolveGitRoot(inputPath) {
    if (inputPath)
        return inputPath;
    let dir = resolve(process.cwd());
    for (let i = 0; i < 8; i++) {
        if (existsSync(resolve(dir, '.git')))
            return dir;
        const parent = resolve(dir, '..');
        if (parent === dir)
            break;
        dir = parent;
    }
    return resolve(process.cwd());
}
const gitStatusDef = {
    name: 'git_status',
    description: 'Get the current git repository status (branch, changed files, staged/unstaged)',
    category: 'development',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            path: { type: 'string', description: 'Path to git repository (default: project root)', required: false },
        },
        required: [],
    },
    timeoutMs: 10000,
    async call(input, _ctx) {
        try {
            const cwd = resolveGitRoot(input.path);
            const opts = { cwd, encoding: 'utf-8', timeout: 8000 };
            // Confirm it is a git repo first — rev-parse --git-dir works even with zero commits.
            try {
                execSync('git rev-parse --git-dir', opts);
            }
            catch {
                return { success: false, error: `Not a git repository at ${cwd} — initialize one with: git init`, errorCode: 'NOT_GIT_REPO' };
            }
            let branch;
            try {
                branch = execSync('git rev-parse --abbrev-ref HEAD', opts).toString().trim();
            }
            catch {
                branch = '(no commits yet)';
            }
            const statusRaw = execSync('git status --short', opts).toString().trim();
            const changed = statusRaw ? statusRaw.split('\n').length : 0;
            const summary = changed === 0 ? 'Clean working tree' : `${changed} changed file(s)`;
            return { success: true, data: { branch, status: statusRaw || 'clean', changed, summary } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'GIT_STATUS_ERROR' };
        }
    },
};
const gitLogDef = {
    name: 'git_log',
    description: 'Get recent git commit history with hashes, authors, dates, and messages',
    category: 'development',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            path: { type: 'string', description: 'Path to git repository', required: false },
            maxCount: { type: 'number', description: 'Max commits to show', default: 10 },
            format: { type: 'string', description: 'Output format (short, oneline, full)', default: 'short' },
        },
        required: [],
    },
    timeoutMs: 10000,
    async call(input, _ctx) {
        try {
            const cwd = resolveGitRoot(input.path);
            const count = input.maxCount || 10;
            const opts = { cwd, encoding: 'utf-8', timeout: 8000 };
            // Check if git repo first (--git-dir works even with zero commits)
            try {
                execSync('git rev-parse --git-dir', opts);
            }
            catch {
                return { success: false, error: `Not a git repository at ${cwd} — initialize one with: git init`, errorCode: 'NOT_GIT_REPO' };
            }
            // Quote the --format so /bin/sh doesn't treat `|||` as pipes — git_log
            // previously ALWAYS failed with a shell syntax error.
            let raw;
            try {
                raw = execSync(`git log -${count} '--format=%H|||%an|||%ai|||%s'`, opts).toString().trim();
            }
            catch {
                return { success: true, data: { commits: [] } }; // fresh repo, no commits yet
            }
            const commits = raw.split('\n').filter(Boolean).map(line => {
                const [hash, author, date, ...msgParts] = line.split('|||');
                return {
                    hash: hash?.substring(0, 8) || '',
                    author: author || '',
                    date: date || '',
                    message: msgParts.join('|||').trim() || '',
                };
            });
            return { success: true, data: { commits } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'GIT_LOG_ERROR' };
        }
    },
};
const uuidGenDef = {
    name: 'uuid_gen',
    description: 'Generate one or more UUID v4 identifiers',
    category: 'utility',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            count: { type: 'number', description: 'Number of UUIDs to generate', default: 1 },
        },
        required: [],
    },
    async call(input, _ctx) {
        const count = Math.min(Math.max(1, input.count || 1), 100);
        const uuids = [];
        for (let i = 0; i < count; i++) {
            uuids.push(randomUUID());
        }
        return { success: true, data: { uuids } };
    },
};
const hashTextDef = {
    name: 'hash_text',
    description: 'Generate cryptographic hash (MD5, SHA1, SHA256) of text input',
    category: 'utility',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            text: { type: 'string', description: 'Text to hash' },
            algorithm: { type: 'string', description: 'Hash algorithm', enum: ['md5', 'sha1', 'sha256'], default: 'sha256' },
        },
        required: ['text'],
    },
    async call(input, _ctx) {
        try {
            const algorithm = input.algorithm || 'sha256';
            const hash = createHash(algorithm).update(input.text).digest('hex');
            return { success: true, data: { algorithm, hash, length: hash.length } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'HASH_ERROR' };
        }
    },
};
const systemInfoDef = {
    name: 'system_info',
    description: 'Get system information (OS, CPU cores, memory usage, uptime)',
    category: 'monitoring',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            detailed: { type: 'boolean', description: 'Include detailed CPU info', default: false },
        },
        required: [],
    },
    async call(input, _ctx) {
        try {
            const cpuInfo = cpus();
            const totalMem = totalmem();
            const freeMem = freemem();
            const data = {
                os: type(),
                hostname: hostname(),
                platform: process.platform,
                arch: process.arch,
                nodeVersion: process.version,
                cpus: cpuInfo.length,
                cpuModel: cpuInfo[0]?.model || 'unknown',
                memory: {
                    total: `${(totalMem / 1024 / 1024 / 1024).toFixed(2)} GB`,
                    free: `${(freeMem / 1024 / 1024 / 1024).toFixed(2)} GB`,
                    used: `${((totalMem - freeMem) / 1024 / 1024 / 1024).toFixed(2)} GB`,
                    usagePercent: `${((1 - freeMem / totalMem) * 100).toFixed(1)}%`,
                },
                uptime: process.uptime(),
                uptimeFormatted: formatUptime(process.uptime()),
            };
            if (input.detailed) {
                data.cpuDetails = cpuInfo.slice(0, 4).map((c, i) => ({
                    core: i,
                    model: c.model,
                    speed: `${c.speed} MHz`,
                    times: c.times,
                }));
            }
            return { success: true, data };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'SYS_INFO_ERROR' };
        }
    },
};
function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const parts = [];
    if (days > 0)
        parts.push(`${days}d`);
    if (hours > 0)
        parts.push(`${hours}h`);
    parts.push(`${mins}m`);
    return parts.join(' ');
}
const networkInfoDef = {
    name: 'network_info',
    description: 'Get network interface information (interfaces, IP addresses, MACs)',
    category: 'monitoring',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            detailed: { type: 'boolean', description: 'Include detailed interface info', default: false },
        },
        required: [],
    },
    async call(input, _ctx) {
        try {
            const nets = networkInterfaces();
            const interfaces = [];
            for (const [name, netList] of Object.entries(nets)) {
                if (!netList)
                    continue;
                const addresses = netList.map(n => n.address);
                const entry = { name, addresses };
                if (input.detailed) {
                    entry.mac = netList[0]?.mac || '';
                    entry.internal = netList[0]?.internal || false;
                    entry.family = netList[0]?.family || '';
                    entry.netmask = netList[0]?.netmask || '';
                }
                interfaces.push(entry);
            }
            return { success: true, data: { interfaces, interfaceCount: interfaces.length } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'NET_INFO_ERROR' };
        }
    },
};
const designSearchDef = {
    name: 'design_search',
    description: 'Search the design library for existing designs matching a query or tags',
    category: 'design',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            query: { type: 'string', description: 'Search query (name, description, or node labels)' },
            tags: { type: 'array', description: 'Filter by tags', required: false },
            maxResults: { type: 'number', description: 'Maximum results', default: 10 },
        },
        required: ['query'],
    },
    async call(input, _ctx) {
        try {
            const q = input.query.toLowerCase();
            const maxResults = input.maxResults || 10;
            // Try loading designs from the JSON file
            const designsJsonPath = resolve(import.meta.dirname, '..', '..', 'data', 'designs.json');
            let designs = [];
            if (existsSync(designsJsonPath)) {
                const content = readFileSync(designsJsonPath, 'utf-8');
                try {
                    designs = JSON.parse(content);
                    if (!Array.isArray(designs))
                        designs = [designs];
                }
                catch {
                    designs = [];
                }
            }
            // Filter by query and tags
            let results = designs.filter((d) => {
                const name = (d.name || '').toLowerCase();
                const goal = (d.goal || '').toLowerCase();
                const desc = (d.description || '').toLowerCase();
                const designTags = (d.tags || []).map((t) => t.toLowerCase());
                const queryMatch = name.includes(q) || goal.includes(q) || desc.includes(q);
                const tagMatch = input.tags
                    ? input.tags.some(t => designTags.includes(t.toLowerCase()))
                    : true;
                return queryMatch && tagMatch;
            });
            // Sort by node count (more complex designs first)
            results.sort((a, b) => (b.nodes?.length || 0) - (a.nodes?.length || 0));
            results = results.slice(0, maxResults);
            return { success: true, data: { designs: results, total: results.length } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'DESIGN_SEARCH_ERROR' };
        }
    },
};
const designTemplateDef = {
    name: 'design_template',
    description: 'Generate a design template suggestion (node types, connections) for an app idea using AI',
    category: 'design',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            appType: { type: 'string', description: 'Type of app (e.g., web app, CLI tool, game, API server)' },
            description: { type: 'string', description: 'Brief description of what the app does' },
            language: { type: 'string', description: 'Preferred programming language', required: false },
        },
        required: ['appType', 'description'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const lang = input.language || 'typescript';
            const result = await translator.reason(`Design a ${input.appType} app: ${input.description}\n\n` +
                `List the recommended node types (input, logic, api, database, ui, ui-functions, output) and describe what each node should do.\n` +
                `Preferred language: ${lang}\n` +
                `Format as a structured list with node type, name, and description for each node.`, 'You are a software architect. Suggest practical node layouts for the VACA canvas.', { maxTokens: 1536 });
            const nodeCount = (result.match(/node:/gi) || result.match(/- /g) || []).length;
            const suggestedNodes = result.split('\n')
                .filter(l => l.match(/^\s*[-*]\s+/))
                .map(l => l.replace(/^\s*[-*]\s+/, '').trim());
            return { success: true, data: { template: result, nodeCount: Math.max(nodeCount, 1), suggestedNodes } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('design_template', 'To design an app architecture manually:\n' +
                    '  • Identify the main components: UI, API, data storage, business logic\n' +
                    '  • Map data flow between components (inputs/outputs)\n' +
                    '  • Choose appropriate node types: input, output, logic, api, database, ui\n' +
                    '  • Plan the file structure: routes, models, controllers, services\n' +
                    '  • Consider cross-cutting concerns: auth, logging, config, error handling\n' +
                    '  • Draw the architecture as a flowchart or node diagram\n' +
                    'Start the DSpark LLM server (port 8000): scripts/start-dspark.sh  (or ollama serve) then retry this tool', 'template');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'DESIGN_TEMPLATE_ERROR' };
        }
    },
};
const diagramFlowDef = {
    name: 'diagram_flow',
    description: 'Generate Mermaid.js flow/sequence/class/mindmap diagram markup from a text description using AI',
    category: 'diagram',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            description: { type: 'string', description: 'Description of the diagram content' },
            type: { type: 'string', description: 'Diagram type', enum: ['flowchart', 'sequence', 'class', 'mindmap'], default: 'flowchart' },
        },
        required: ['description'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const diagramType = input.type || 'flowchart';
            const result = await translator.reason(`Generate a Mermaid.js ${diagramType} diagram based on this description:\n\n${input.description}\n\n` +
                `Return ONLY the Mermaid markup, starting with the diagram type declaration. No explanations.`, `You are an expert at creating Mermaid.js diagrams. Generate correct, well-formatted ${diagramType} diagrams.`, { maxTokens: 1024 });
            // Extract mermaid code block if wrapped
            let mermaid = result;
            const mermaidMatch = result.match(/```mermaid\s*\n([\s\S]*?)```/);
            if (mermaidMatch) {
                mermaid = mermaidMatch[1].trim();
            }
            return { success: true, data: { mermaid, type: diagramType } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('diagram_flow', '```mermaid\ngraph TD;\n  A[Start] --> B{Decision};\n  B -->|Yes| C[Process];\n  B -->|No| D[End];\n```\n' +
                    'To create diagrams without AI, use Mermaid.js syntax directly. ' +
                    'Visit https://mermaid.js.org/syntax for the full reference.\n' +
                    'Start the DSpark LLM server (port 8000): scripts/start-dspark.sh  (or ollama serve) then retry this tool', 'mermaid');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'DIAGRAM_ERROR' };
        }
    },
};
const notifySendDef = {
    name: 'notify_send',
    description: 'Send a desktop notification (uses notify-send on Linux, terminal bell as fallback)',
    category: 'notification',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            title: { type: 'string', description: 'Notification title' },
            message: { type: 'string', description: 'Notification message body' },
            urgency: { type: 'string', description: 'Urgency level', enum: ['low', 'normal', 'critical'], default: 'normal' },
        },
        required: ['title', 'message'],
    },
    timeoutMs: 5000,
    async call(input, _ctx) {
        try {
            const urgency = input.urgency || 'normal';
            let method = 'none';
            // Try notify-send (Linux)
            try {
                execSync(`notify-send "${input.title.replace(/"/g, '\\"')}" "${input.message.replace(/"/g, '\\"')}" -u ${urgency}`, { timeout: 3000, encoding: 'utf-8' });
                method = 'notify-send';
            }
            catch {
                // Fallback: log to console (always works)
                console.log(`\n=== NOTIFICATION: ${input.title} ===`);
                console.log(`${input.message}`);
                console.log(`=== urgency: ${urgency} ===\n`);
                method = 'console';
            }
            return { success: true, data: { sent: true, method } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'NOTIFY_ERROR' };
        }
    },
};
// ═════════════════════════════════════════════════════════════════════════════
// Export all aux tools as a single array
// ═════════════════════════════════════════════════════════════════════════════
export const auxTools = [
    // Mini Agents (AI-powered)
    codeReviewMiniDef,
    docWriterMiniDef,
    testWriterMiniDef,
    refactorMiniDef,
    explainCodeMiniDef,
    // Data Tools
    jsonQueryDef,
    csvParseDef,
    jsonToCsvDef,
    dataValidateDef,
    // Network Tools
    httpRequestDef,
    urlAnalyzeDef,
    // Development Tools
    gitStatusDef,
    gitLogDef,
    uuidGenDef,
    hashTextDef,
    // System / Monitoring Tools
    systemInfoDef,
    networkInfoDef,
    // Design Tools
    designSearchDef,
    designTemplateDef,
    // Diagram Tools
    diagramFlowDef,
    // Notification Tools
    notifySendDef,
];
// Named exports for individual registration
export { codeReviewMiniDef as codeReviewMini, docWriterMiniDef as docWriterMini, testWriterMiniDef as testWriterMini, refactorMiniDef as refactorMini, explainCodeMiniDef as explainCodeMini, jsonQueryDef as jsonQuery, csvParseDef as csvParse, jsonToCsvDef as jsonToCsv, dataValidateDef as dataValidate, httpRequestDef as httpRequest, urlAnalyzeDef as urlAnalyze, gitStatusDef as gitStatus, gitLogDef as gitLog, uuidGenDef as uuidGen, hashTextDef as hashText, systemInfoDef as systemInfo, networkInfoDef as networkInfo, designSearchDef as designSearch, designTemplateDef as designTemplate, diagramFlowDef as diagramFlow, notifySendDef as notifySend, };
