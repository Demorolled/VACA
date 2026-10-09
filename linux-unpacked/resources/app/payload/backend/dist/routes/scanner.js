import { Router } from 'express';
import { codeScanner } from '../scanner/CodeScanner.js';
import { AITranslator } from '../ai/translator.js';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { writeFileSync, existsSync, mkdirSync, readFileSync } from 'fs';
import path from 'path';
import { scanDirectoryTree, readDirectoryFiles, processFiles, processFilesWithTools } from '../services/veronicaFileService.js';
import { getIO } from '../socket/socketManager.js';
import { PLAN_NODE_TYPES } from '../types.js';
export const scannerRoutes = Router();
// ─── Rule-based fallback analyzer ──────────────────────────────────
// Canonical file-node types (single source of truth in types.ts) — previously
// a local list that silently dropped 'gui-layout' relative to the planner.
const NODE_TYPES = [...PLAN_NODE_TYPES];
const FILE_CLASSIFIERS = [
    { patterns: [/route/i, /endpoint/i, /controller/i, /middleware/i], type: 'api', score: 8, labelHint: 'API Routes' },
    { patterns: [/store\//, /state/, /redux/, /store\./, /context/, /reducer/], type: 'logic', score: 8, labelHint: 'State Management' },
    { patterns: [/database/, /db\//, /schema/, /model/, /entity/, /repository/, /prisma/, /migration/], type: 'database', score: 8, labelHint: 'Database' },
    { patterns: [/component/, /pages?\//, /ui\//, /views?\//, /screen/, /layout/, /template/], type: 'ui', score: 7, labelHint: 'UI Components' },
    { patterns: [/form/, /input/, /select/, /button/, /modal/, /dialog/], type: 'input', score: 6, labelHint: 'User Input' },
    { patterns: [/display/, /output/, /result/, /list/, /table/, /card/, /chart/], type: 'output', score: 6, labelHint: 'Display Output' },
    { patterns: [/utils?\//, /helpers?\//, /lib\//, /services?\//, /hooks?\//], type: 'logic', score: 6, labelHint: 'Utilities & Logic' },
    { patterns: [/auth/, /login/, /signup/, /session/, /permission/], type: 'api', score: 7, labelHint: 'Authentication' },
    { patterns: [/config/, /settings/, /constants/, /env/], type: 'logic', score: 5, labelHint: 'Configuration' },
    { patterns: [/test/, /spec/, /\.test\./, /\.spec\./], type: 'logic', score: 3, labelHint: 'Tests' },
    { patterns: [/style/, /\bcss\b/, /theme/, /tailwind/], type: 'ui', score: 5, labelHint: 'Styles & Theme' },
    { patterns: [/worker/, /cron/, /task/, /job/, /queue/], type: 'logic', score: 6, labelHint: 'Background Jobs' },
    { patterns: [/api\//, /graphql/, /rest/, /resolver/], type: 'api', score: 9, labelHint: 'API Layer' },
    { patterns: [/plugin/, /extension/, /integration/], type: 'api', score: 6, labelHint: 'Integration' },
    { patterns: [/main\./, /app\./, /index\./, /entry/, /bootstrap/], type: 'logic', score: 7, labelHint: 'App Entry' },
];
const FRAMEWORK_DETECTORS = [
    { patterns: [/react/i, /jsx/i, /tsx/i], name: 'React' },
    { patterns: [/vue/i, /\.vue$/], name: 'Vue' },
    { patterns: [/angular/i], name: 'Angular' },
    { patterns: [/express/i, /fastify/i, /hono/i], name: 'Express' },
    { patterns: [/django/i, /flask/i, /fastapi/i], name: 'Python Web' },
    { patterns: [/next[\.\-\s]?js/i, /nuxt/i, /remix/i], name: 'Next.js' },
    { patterns: [/prisma/i, /typeorm/i, /drizzle/i], name: 'ORM/Database' },
    { patterns: [/tailwind/i, /bootstrap/i, /material/i], name: 'CSS Framework' },
];
function classifyFile(filePath) {
    let best = { type: 'logic', score: 0, labelHint: 'Logic' };
    for (const classifier of FILE_CLASSIFIERS) {
        for (const pattern of classifier.patterns) {
            if (pattern.test(filePath)) {
                if (classifier.score > best.score) {
                    best = classifier;
                }
                break;
            }
        }
    }
    return { type: best.type, labelHint: best.labelHint };
}
function detectFramework(files) {
    const allContent = files.map(f => f.path + '\n' + f.content.substring(0, 500)).join('\n');
    const detected = [];
    for (const detector of FRAMEWORK_DETECTORS) {
        for (const pattern of detector.patterns) {
            if (pattern.test(allContent)) {
                detected.push(detector.name);
                break;
            }
        }
    }
    const exts = new Set(files.map(f => f.path.split('.').pop()?.toLowerCase()));
    let projectType = 'unknown';
    if (exts.has('tsx') || exts.has('ts') || exts.has('jsx'))
        projectType = 'frontend';
    if (exts.has('py'))
        projectType = 'python';
    if (detected.some(d => d === 'Express' || d === 'FastAPI'))
        projectType = 'fullstack';
    return { projectType, frameworks: [...new Set(detected)] };
}
function extractImports(content) {
    const imports = [];
    const tsImports = content.matchAll(/from\s+['"]([^'"]+)['"]/g);
    for (const match of tsImports)
        imports.push(match[1]);
    const pyImports = content.matchAll(/^(?:from|import)\s+(\S+)/gm);
    for (const match of pyImports)
        imports.push(match[1]);
    const reqImports = content.matchAll(/(?:require|import)\s*\(\s*['"]([^'"]+)['"]\s*\)/g);
    for (const match of reqImports)
        imports.push(match[1]);
    return [...new Set(imports)];
}
const URL_CALL_RE = /\.(?:get|post|put|patch|delete|request|head|options)\s*\(\s*['"`]([^'"`]+)['"`]|fetch\s*\(\s*['"`]([^'"`]+)['"`]|new\s+WebSocket\s*\(\s*['"`]([^'"`]+)['"`]|(?:http|https|ws|wss):\/\/[^'"`\s)]+/g;
function looksLikeUrl(spec) {
    return /^(?:https?:\/\/|wss?:\/\/|\/\/)/.test(spec) || spec.startsWith('/');
}
function isRelative(spec) {
    return spec.startsWith('./') || spec.startsWith('../') || spec === '.' || spec === '..';
}
/** Bare import specifier → npm/pip package name ('react-dom/client' → 'react-dom'). */
function packageNameFromSpec(spec) {
    const clean = spec.split('/');
    if (spec.startsWith('@'))
        return clean.slice(0, 2).join('/'); // scoped: @org/pkg
    return clean[0];
}
/** Human label for a service URL: host + first path segment. */
function serviceNameFromUrl(url) {
    const trimmed = url.trim();
    const m = trimmed.match(/^(?:https?:\/\/|wss?:\/\/|\/\/)?([^/\s]+)?(\/[^?#\s]*)?/);
    const host = m?.[1] || '';
    const pathSeg = (m?.[2] || '').split('/').filter(Boolean)[0] || '';
    const hostShort = host ? host.replace(/^www\./, '') : '';
    return pathSeg && hostShort ? `${hostShort}/${pathSeg}` : hostShort || trimmed.slice(0, 60);
}
/**
 * Build the "how it connects to other apps / services" list for a set of
 * dropped files. Classifies every reference it finds:
 *   • bare import specifiers      → 'package' (npm/pip deps)
 *   • http(s)/ws(s) URLs + /api calls → 'service' (external APIs & backends)
 *   • references to ANOTHER top-level dropped folder → 'app' (sibling app)
 */
export function buildScanConnections(files) {
    const roots = new Set();
    for (const f of files) {
        const root = f.path.split('/')[0];
        if (root)
            roots.add(root);
    }
    const otherRoots = [...roots];
    const byKey = new Map();
    const keyOf = (kind, name) => `${kind}:${name}`;
    const addUse = (kind, name, filePath) => {
        if (!name)
            return;
        const key = keyOf(kind, name);
        let conn = byKey.get(key);
        if (!conn) {
            conn = { name, kind, usedBy: [] };
            byKey.set(key, conn);
        }
        if (!conn.usedBy.includes(filePath))
            conn.usedBy.push(filePath);
    };
    for (const file of files) {
        const content = file.content || '';
        // 1. Imports / requires → packages or sibling apps
        for (const imp of extractImports(content)) {
            const trimmed = imp.trim();
            if (!trimmed)
                continue;
            if (looksLikeUrl(trimmed)) {
                addUse('service', serviceNameFromUrl(trimmed), file.path);
                continue;
            }
            if (isRelative(trimmed)) {
                // ../other-app/... → sibling app reference
                const m = trimmed.match(/^(?:\.\.\/)+([^/]+)/);
                const target = m?.[1];
                if (target && otherRoots.includes(target) && target !== file.path.split('/')[0]) {
                    addUse('app', target, file.path);
                }
                continue;
            }
            // Bare specifier → npm/pip package (skip node builtins and junk like "{"
            // that the Python-style import regex can capture from "import { x } …")
            const pkg = packageNameFromSpec(trimmed);
            if (pkg &&
                /^[A-Za-z@][A-Za-z0-9._@/\-]*$/.test(pkg) &&
                // npm package names are lowercase — an uppercase specifier is the
                // imported BINDING from `import React from "react"` (Python-style
                // regex artifact), not a package
                !/^[A-Z]/.test(pkg) &&
                !/^(node:|fs$|path$|os$|http$|https$|crypto$|child_process$|util$|stream$|events$|url$|buffer$|zlib$|net$|dns$|timers$|querystring$|assert$|process$|console$)/.test(pkg) &&
                // never treat a lone "from" as a package
                pkg !== 'from') {
                addUse('package', pkg, file.path);
            }
        }
        // 2. URL calls (fetch / axios.get / http.get / WebSocket / bare URLs)
        let m;
        URL_CALL_RE.lastIndex = 0;
        while ((m = URL_CALL_RE.exec(content)) !== null) {
            const url = (m[1] || m[2] || m[3] || m[4] || '').trim();
            if (url && looksLikeUrl(url))
                addUse('service', serviceNameFromUrl(url), file.path);
        }
        // 3. package.json → declared dependencies (usedBy = the manifest itself)
        if (/package\.json$/i.test(file.path)) {
            try {
                const pkg = JSON.parse(content);
                const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
                for (const dep of Object.keys(deps))
                    addUse('package', dep, file.path);
            }
            catch {
                // unparseable manifest — imports already covered it
            }
        }
    }
    return [...byKey.values()]
        .sort((a, b) => b.usedBy.length - a.usedBy.length || a.name.localeCompare(b.name));
}
/** Distinct top-level folder roots among the dropped files (>1 = multiple apps dropped). */
export function detectApps(files) {
    const roots = new Set();
    for (const f of files) {
        const root = f.path.split('/')[0];
        if (root)
            roots.add(root);
    }
    return [...roots];
}
function buildRelationshipGraph(files) {
    const nameToFiles = new Map();
    const relationships = new Map();
    for (const file of files) {
        const basename = file.path.split('/').pop()?.replace(/\.[^.]+$/, '') || '';
        nameToFiles.set(basename, [file.path]);
        nameToFiles.set(file.path, [file.path]);
        const parts = file.path.split('/');
        for (let i = 0; i < parts.length; i++) {
            const partial = parts.slice(i).join('/').replace(/\.[^.]+$/, '');
            if (!nameToFiles.has(partial)) {
                nameToFiles.set(partial, [file.path]);
            }
            else {
                nameToFiles.get(partial)?.push(file.path);
            }
        }
    }
    for (const file of files) {
        const imports = extractImports(file.content);
        const source = file.path;
        relationships.set(source, new Set());
        for (const imp of imports) {
            const cleanPath = imp.replace(/^\.\.?\/+/, '').split('/').slice(0, 2).join('/');
            const matched = nameToFiles.get(cleanPath) || nameToFiles.get(imp.split('/')[0]);
            if (matched) {
                for (const target of matched) {
                    if (target !== source) {
                        relationships.get(source)?.add(target);
                    }
                }
            }
        }
    }
    return relationships;
}
function generateFallbackArchitecture(files) {
    const { projectType, frameworks } = detectFramework(files);
    const relationships = buildRelationshipGraph(files);
    const dirGroups = new Map();
    for (const file of files) {
        const dir = file.path.split('/').length > 1
            ? file.path.split('/').slice(0, -1).join('/')
            : 'root';
        if (!dirGroups.has(dir))
            dirGroups.set(dir, []);
        dirGroups.get(dir).push(file);
    }
    const nodes = [];
    const nodeLabels = [];
    let yPos = 100;
    for (const [dir, groupFiles] of dirGroups) {
        let bestType = 'logic';
        let bestHint = 'Logic';
        let bestScore = 0;
        for (const file of groupFiles) {
            const classification = classifyFile(file.path);
            const score = FILE_CLASSIFIERS.find(c => c.type === classification.type)?.score || 5;
            if (score > bestScore) {
                bestType = classification.type;
                bestHint = classification.labelHint;
                bestScore = score;
            }
        }
        const dirName = dir === 'root' ? 'App Entry' : dir.split('/').pop()
            .replace(/[-_]/g, ' ')
            .replace(/\b\w/g, c => c.toUpperCase());
        const label = `${dirName} — ${bestHint}`;
        if (nodeLabels.includes(label))
            continue;
        nodeLabels.push(label);
        const fileList = groupFiles.map(f => f.path);
        const fileSummaries = groupFiles.map(f => `ﾷ ${f.path}: ${f.content.split('\n')[0]?.substring(0, 80) || ''}`);
        nodes.push({
            label,
            description: `${fileSummaries.length} files — ${dirName} module. ${bestHint} layer of the application.`,
            type: bestType,
            language: groupFiles.some(f => f.path.endsWith('.py')) ? 'python' : 'typescript',
            files: fileList,
            position: { x: 250 + (nodes.length % 2) * 350, y: yPos },
        });
        yPos += 170;
    }
    const edges = [];
    for (const [sourceFile, targets] of relationships) {
        const sourceLabel = nodes.find(n => n.files.includes(sourceFile))?.label;
        if (!sourceLabel)
            continue;
        for (const targetFile of targets) {
            const targetLabel = nodes.find(n => n.files.includes(targetFile))?.label;
            if (targetLabel && sourceLabel !== targetLabel) {
                const exists = edges.some(e => e.source === sourceLabel && e.target === targetLabel);
                if (!exists) {
                    edges.push({ source: sourceLabel, target: targetLabel, description: `${sourceFile.split('/').pop()} imports ${targetFile.split('/').pop()}` });
                }
            }
        }
    }
    return { projectName: files[0]?.path.split('/')[0] || 'Imported Project', projectType, frameworks, nodes, edges };
}
// ─── LLM-powered deep scan ─────────────────────────────────────────
const DEEP_SCAN_SYSTEM_PROMPT = `You are a software architecture analyst. Analyze the provided project files and produce a complete node-based architecture diagram.

Each node you create is a PLACEHOLDER that represents a group of actual files and resources on disk. Think of every node as answering "what real files belong to this component?"

For each logical module or component in the project, create a node. Each node must have:
- label: A clear, descriptive name
- description: What this module does (2-3 sentences max)
- type: One of: "input" (user entry points), "output" (display/results), "logic" (processing/state/rules), "api" (external services), "database" (storage), "ui" (interface components)
- language: "typescript", "python", "javascript", etc.
- files: Array of ALL file paths belonging to this node (this is critical — every file in the project should be assigned to a node)

Also identify connections between nodes (edges) with source/target matching node labels.

Return ONLY valid JSON with this exact structure:
{
  "projectName": "string",
  "projectType": "frontend|backend|fullstack|cli|library|unknown",
  "frameworks": ["list", "of", "detected", "frameworks"],
  "nodes": [
    {
      "label": "string",
      "description": "string",
      "type": "input|output|logic|api|database|ui",
      "language": "string",
      "files": ["path/to/file1.ts", "path/to/file2.ts"],
      "position": { "x": number, "y": number }
    }
  ],
  "edges": [
    { "source": "Node Label", "target": "Node Label", "description": "which files connect them, e.g. 'index.ts imports utils.ts' (optional)" }
  ],
  "externalConnections": [
    { "name": "express", "kind": "package", "description": "HTTP server framework (optional)" }
  ]
}

IMPORTANT:
- Each node is a PLACEHOLDER for the actual files it contains. The "files" array should list every real file that belongs to that component.
- Analyze imports and dependencies between files to find real connections
- Group related files into the same node (don't make separate nodes for individual files)
- Make sure EVERY provided file is assigned to at least one node — no orphan files
- Create nodes at different positions so they don't overlap (use x: 200-1200, y: 100-1400)
- "externalConnections" is OPTIONAL and only for things OUTSIDE this codebase the app talks to: npm packages it imports, external APIs/services it calls (URLs, hosts), or other apps it references. The platform also computes these deterministically, so keep it brief.
- Return ONLY the JSON. No markdown, no explanations.`;
// ─── Existing routes (preserved) ────────────────────────────────────
scannerRoutes.post('/scan-file', async (req, res) => {
    try {
        const { filePath, content } = req.body;
        if (!filePath) {
            res.status(400).json({ success: false, error: 'filePath required' });
            return;
        }
        const result = codeScanner.scanFile(filePath, content);
        res.json({ success: true, result });
    }
    catch (err) {
        res.status(500).json({ success: false, error: String(err) });
    }
});
scannerRoutes.post('/scan-directory', async (req, res) => {
    try {
        const { dirPath, pattern } = req.body;
        if (!dirPath) {
            res.status(400).json({ success: false, error: 'dirPath required' });
            return;
        }
        const patternRegex = pattern ? new RegExp(pattern) : undefined;
        const results = codeScanner.scanDirectory(dirPath, patternRegex);
        const summary = {
            files: results.length,
            totalErrors: results.reduce((a, r) => a + r.summary.errors, 0),
            totalWarnings: results.reduce((a, r) => a + r.summary.warnings, 0),
            totalInfos: results.reduce((a, r) => a + r.summary.infos, 0),
        };
        res.json({ success: true, results, summary });
    }
    catch (err) {
        res.status(500).json({ success: false, error: String(err) });
    }
});
scannerRoutes.post('/security-scan', async (req, res) => {
    try {
        const { filePath, content } = req.body;
        if (!filePath) {
            res.status(400).json({ success: false, error: 'filePath required' });
            return;
        }
        const result = codeScanner.securityScan(filePath, content);
        res.json({ success: true, result });
    }
    catch (err) {
        res.status(500).json({ success: false, error: String(err) });
    }
});
scannerRoutes.post('/analyze-complexity', async (req, res) => {
    try {
        const { source } = req.body;
        if (!source) {
            res.status(400).json({ success: false, error: 'source required' });
            return;
        }
        const result = codeScanner.analyzeComplexity(source);
        res.json({ success: true, result });
    }
    catch (err) {
        res.status(500).json({ success: false, error: String(err) });
    }
});
scannerRoutes.post('/debug/inject-logs', async (req, res) => {
    try {
        const { filePath, expression } = req.body;
        if (!filePath) {
            res.status(400).json({ success: false, error: 'filePath required' });
            return;
        }
        const source = codeScanner.debugInjectLogs(filePath, expression);
        res.json({ success: true, message: 'Debug logs injected', source });
    }
    catch (err) {
        res.status(500).json({ success: false, error: String(err) });
    }
});
scannerRoutes.post('/debug/remove-logs', async (req, res) => {
    try {
        const { filePath } = req.body;
        if (!filePath) {
            res.status(400).json({ success: false, error: 'filePath required' });
            return;
        }
        const result = codeScanner.debugRemoveLogs(filePath);
        res.json({ success: true, ...result });
    }
    catch (err) {
        res.status(500).json({ success: false, error: String(err) });
    }
});
// ─── Deep scan route (restored) ─────────────────────────────────────
scannerRoutes.post('/deep', async (req, res) => {
    try {
        const { files, useRuleBased = false } = req.body;
        if (!files || !Array.isArray(files) || files.length === 0) {
            res.status(400).json({ error: 'No files provided for scanning' });
            return;
        }
        const MAX_FILES = 400;
        const filesToScan = files.slice(0, MAX_FILES);
        if (files.length > MAX_FILES) {
            console.log(`[scanner] Truncated ${files.length} files to ${MAX_FILES} for scanning`);
        }
        // Deterministic connection pass (packages, external services, sibling apps)
        // — attached to whatever architecture comes back so the node build always
        // shows "how the app connects to other apps".
        const scanConnections = buildScanConnections(filesToScan);
        const apps = detectApps(filesToScan);
        const attachConnections = (architecture) => {
            architecture.externalDeps = scanConnections;
            architecture.apps = apps;
            return architecture;
        };
        if (useRuleBased) {
            const architecture = attachConnections(generateFallbackArchitecture(filesToScan));
            res.json({ success: true, architecture, source: 'rule-based' });
            return;
        }
        const fileSummary = filesToScan.map(f => {
            const lines = f.content.split('\n');
            const head = lines.slice(0, 30).join('\n');
            const tail = lines.length > 30 ? `\n... (${lines.length - 30} more lines)` : '';
            return `--- ${f.path} ---\n${head}${tail}`;
        }).join('\n\n');
        const prompt = `Analyze this project's architecture from the following files:\n\n${fileSummary}\n\n${files.length > MAX_FILES ? `\n(Note: ${files.length - MAX_FILES} more files were omitted)\n` : ''}\n\nReturn the complete node architecture as JSON.`;
        const translator = new AITranslator();
        let response;
        try {
            response = await translator.reason(prompt, DEEP_SCAN_SYSTEM_PROMPT, { maxTokens: 8192 });
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            console.warn('[scanner] LLM scan failed, falling back to rule-based:', msg);
            const architecture = attachConnections(generateFallbackArchitecture(filesToScan));
            res.json({ success: true, architecture, source: 'rule-based', llmError: msg });
            return;
        }
        let architecture = null;
        try {
            const cleaned = response.replace(/```json\s*[\n\r]?/g, '').replace(/```\s*[\n\r]?/g, '').trim();
            architecture = JSON.parse(cleaned);
        }
        catch {
            const jsonMatch = response.match(/\{[\s\S]*"projectName"[\s\S]*"nodes"[\s\S]*"edges"[\s\S]*\}/);
            if (jsonMatch) {
                try {
                    architecture = JSON.parse(jsonMatch[0]);
                }
                catch {
                    architecture = null;
                }
            }
        }
        if (!architecture || !Array.isArray(architecture.nodes) || architecture.nodes.length === 0) {
            console.warn('[scanner] LLM returned unparseable architecture, falling back to rule-based');
            const fallback = attachConnections(generateFallbackArchitecture(filesToScan));
            res.json({ success: true, architecture: fallback, source: 'rule-based', llmRaw: response });
            return;
        }
        const validTypes = new Set(NODE_TYPES);
        for (const node of architecture.nodes) {
            if (!validTypes.has(node.type))
                node.type = 'logic';
            if (!node.language) {
                const isPython = node.files?.some((f) => f.endsWith('.py'));
                node.language = isPython ? 'python' : 'typescript';
            }
            if (!node.position || typeof node.position.x !== 'number') {
                node.position = { x: 250, y: 100 + architecture.nodes.indexOf(node) * 170 };
            }
        }
        const nodeLabels = new Set(architecture.nodes.map((n) => n.label));
        architecture.edges = (architecture.edges || []).filter((e) => e.source && e.target && nodeLabels.has(e.source) && nodeLabels.has(e.target));
        attachConnections(architecture);
        try {
            const tags = ['scan', 'architecture', ...architecture.frameworks.map((f) => f.toLowerCase().replace(/\s+/g, '-'))];
            knowledgeStore.addPattern({
                category: 'architecture',
                title: `Architecture: ${architecture.projectName}`,
                code: JSON.stringify(architecture, null, 2).substring(0, 2000),
                description: `Deep scan of ${architecture.projectName}: ${architecture.nodes.length} nodes, ${architecture.edges.length} edges. Type: ${architecture.projectType}. Frameworks: ${architecture.frameworks.join(', ')}`,
                tags,
                projectId: 'scanner',
                targetOS: 'linux',
                nodeType: 'master',
                language: 'typescript',
                success: true,
                qualityScore: 7.0,
            });
        }
        catch (err) {
            console.warn('[scanner] Failed to record pattern:', err);
        }
        res.json({ success: true, architecture, source: 'llm' });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('[scanner] Scan error:', message);
        res.status(500).json({ error: 'Deep scan failed.', details: message });
    }
});
// ─── Classify a single file ─────────────────────────────────────────
scannerRoutes.post('/classify', (req, res) => {
    try {
        const { path: filePath } = req.body;
        if (!filePath) {
            res.status(400).json({ error: 'File path required' });
            return;
        }
        const classification = classifyFile(filePath);
        res.json({ success: true, classification });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.status(500).json({ error: message });
    }
});
// ─── Export training data for MindSpace ────────────────────────
scannerRoutes.post('/export-training', (req, res) => {
    try {
        const { category } = req.body;
        const allPatterns = knowledgeStore.getAll();
        const patterns = category ? allPatterns.filter(p => p.category === category) : allPatterns;
        if (patterns.length === 0) {
            res.json({
                success: true,
                exported: 0,
                message: category ? `No patterns found with category "${category}"` : 'No patterns found in knowledge store',
            });
            return;
        }
        const entries = patterns.map(p => ({
            text: [p.code, p.description].filter(Boolean).join('\n\n'),
            title: p.title,
            language: p.language || 'unknown',
            nodeType: p.nodeType || 'generic',
            tags: p.tags || [],
            source: 'knowledge-base',
            category: p.category || 'code_pattern',
            timestamp: p.createdAt || new Date().toISOString(),
        }));
        const mindspaceTrainerDir = path.resolve(import.meta.dirname, '..', '..', '..', 'MindSpace', 'trainer');
        if (!existsSync(mindspaceTrainerDir)) {
            mkdirSync(mindspaceTrainerDir, { recursive: true });
        }
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const categoryLabel = (category || 'all-patterns').replace(/[^a-z0-9_-]/gi, '_').toLowerCase();
        const filename = `datasheet-${categoryLabel}-${timestamp}.jsonl`;
        const filepath = path.join(mindspaceTrainerDir, filename);
        const lines = entries.map(e => JSON.stringify(e)).join('\n');
        writeFileSync(filepath, lines, 'utf-8');
        const aliasPath = path.join(mindspaceTrainerDir, `datasheet-${categoryLabel}.jsonl`);
        writeFileSync(aliasPath, lines, 'utf-8');
        console.log(`[scanner] Exported ${entries.length} patterns to MindSpace training: ${filename}`);
        res.json({
            success: true,
            exported: entries.length,
            filename,
            filepath,
            message: `Exported ${entries.length} patterns to MindSpace training datasheet.`,
            stats: {
                totalPatterns: allPatterns.length,
                exportedPatterns: entries.length,
                categories: [...new Set(entries.map(e => e.category))],
                languages: [...new Set(entries.map(e => e.language))],
                nodeTypes: [...new Set(entries.map(e => e.nodeType))],
            },
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('[scanner] Export training error:', message);
        res.status(500).json({ error: 'Failed to export training data.', details: message });
    }
});
// ─── Scan a directory path on the filesystem ──────────────────────────
scannerRoutes.post('/scan-dir', async (req, res) => {
    try {
        const { path: dirPath, recursive = true, maxDepth = 5, includeFiles = false } = req.body;
        if (!dirPath) {
            res.status(400).json({ success: false, error: 'path is required' });
            return;
        }
        const tree = scanDirectoryTree(dirPath, recursive ? maxDepth : 0);
        const fileCount = (function count(entries) {
            return entries.reduce((acc, e) => acc + (e.type === 'file' ? 1 : 0) + (e.children ? count(e.children) : 0), 0);
        })(tree);
        let files = [];
        if (includeFiles) {
            files = readDirectoryFiles(tree);
        }
        const io = getIO();
        if (io) {
            io.emit('scan:directory_result', {
                path: dirPath,
                entries: tree.length,
                files: fileCount,
                timestamp: new Date().toISOString(),
            });
        }
        res.json({
            success: true,
            path: dirPath,
            entries: tree.length,
            fileCount,
            tree,
            files: includeFiles ? files : undefined,
            message: `Scanned ${dirPath}: ${tree.length} top-level entries, ${fileCount} files total`,
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.status(500).json({ success: false, error: message });
    }
});
// ─── Send files to Veronica for scan & repair ─────────────────────────
scannerRoutes.post('/veronica-process', async (req, res) => {
    try {
        const { files, instructions, useToolLoop = true } = req.body;
        if (!files || !Array.isArray(files) || files.length === 0) {
            res.status(400).json({ error: 'files array is required' });
            return;
        }
        const MAX_FILES = 50;
        const filesToProcess = files.slice(0, MAX_FILES);
        // Broadcast that processing started
        const io = getIO();
        if (io) {
            io.emit('veronica:processing_started', {
                fileCount: filesToProcess.length,
                instructions: instructions || 'Default scan & repair',
                timestamp: new Date().toISOString(),
            });
        }
        let result;
        if (useToolLoop) {
            result = await processFilesWithTools(filesToProcess, instructions);
        }
        else {
            result = await processFiles(filesToProcess, instructions);
        }
        // Broadcast completion
        if (io) {
            io.emit('veronica:processing_complete', {
                findings: result.findings.length,
                repairs: result.repairs.length,
                timestamp: new Date().toISOString(),
            });
        }
        res.json({
            ...result,
            filesProcessed: filesToProcess.length,
            totalFiles: files.length,
            message: `Veronica processed ${filesToProcess.length} file(s): ${result.repairs.length} actions taken`,
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('[scanner] veronica-process error:', message);
        res.status(500).json({ success: false, error: message });
    }
});
// ─── Scan a single file from filesystem path and repair via Veronica ──
scannerRoutes.post('/scan-and-repair', async (req, res) => {
    try {
        const { path: filePath, instructions } = req.body;
        if (!filePath) {
            res.status(400).json({ error: 'path is required' });
            return;
        }
        if (!existsSync(filePath)) {
            res.status(404).json({ error: `File not found: ${filePath}` });
            return;
        }
        const content = readFileSync(filePath, 'utf-8');
        const files = [{ path: filePath, content }];
        const result = await processFilesWithTools(files, instructions || 'Scan this file for issues and fix any problems found. Check for: syntax errors, bugs, security vulnerabilities, unused imports, undefined variables, deprecated APIs, and code quality issues.');
        res.json({
            filePath,
            ...result,
            message: result.repairs.length > 0
                ? `Repaired ${result.repairs.length} issue(s) in ${filePath}`
                : `Scanned ${filePath} — no issues found`,
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        res.status(500).json({ success: false, error: message });
    }
});
