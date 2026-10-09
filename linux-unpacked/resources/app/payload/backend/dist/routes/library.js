/**
 * Reference Library API Routes
 * =============================
 *
 * Serves the Markdown library files (data/library/*.md) and Bible reference
 * (bible-reference/) to the frontend ReferenceLibrary panel.
 *
 * GET  /api/library              — List all library files with metadata
 * GET  /api/library/:filename    — Return content of a specific library file
 * GET  /api/library/bible/levels — List all Bible level directories
 * GET  /api/library/bible/:level — List files in a Bible level
 * GET  /api/library/bible/:level/:filename — Return content of a Bible file
 */
import { Router } from 'express';
import * as fs from 'fs';
import * as path from 'path';
import { getLibraryContext, getLibraryContextForNodeType, searchLibrary, getLibraryFileList } from '../ai/libraryContext.js';
const router = Router();
// ─── Paths ────────────────────────────────────────────────────────────────
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const LIBRARY_DIR = path.join(PROJECT_ROOT, 'data', 'library');
const BIBLE_DIR = path.join(PROJECT_ROOT, 'bible-reference');
// ─── Library file metadata ────────────────────────────────────────────────
const LIBRARY_META = {
    '00-reference-index.md': {
        title: 'Reference Index',
        description: 'Master index linking all project references, library files, and Bible levels.',
    },
    '01-node-architecture-reference.md': {
        title: 'Node Architecture Reference',
        description: 'Five node types (input/logic/database/ui/api) with TypeScript, Python, and Go patterns.',
    },
    '02-app-type-templates.md': {
        title: 'App Type Templates',
        description: 'Seven architecture templates: CLI, Web, Media Server, System Tool, Desktop, API, Data Pipeline.',
    },
    '03-code-generation-rules.md': {
        title: 'Code Generation Rules',
        description: 'Code quality rules, naming conventions, error handling, security, and testing standards.',
    },
    '04-technology-mapping.md': {
        title: 'Technology Mapping',
        description: 'Language, framework, and database selection per node type and scenario.',
    },
    '05-design-patterns.md': {
        title: 'Design Patterns',
        description: 'Ten design patterns with generated code examples for common architectures.',
    },
    '06-data-flow-patterns.md': {
        title: 'Data Flow Patterns',
        description: 'Five data flow patterns with diagrams for common app types.',
    },
    '07-node-implementation-guide.md': {
        title: 'Node Implementation Guide',
        description: 'Step-by-step process from design JSON to working code generation.',
    },
    '08-testing-patterns.md': {
        title: 'Testing Patterns',
        description: 'Unit, integration, E2E, and property-based testing for TypeScript, Python, and Go.',
    },
    '09-deployment-templates.md': {
        title: 'Deployment Templates',
        description: 'Binary deployment, systemd services, Nginx reverse proxy, .deb packaging, FHS layout.',
    },
    '10-cicd-configuration.md': {
        title: 'CI/CD Configuration',
        description: 'GitHub Actions, matrix builds, pre-commit hooks, Makefile targets, semantic versioning.',
    },
    '11-debugging-strategies.md': {
        title: 'Debugging Strategies',
        description: 'Structured logging, error hierarchy, layer-by-layer debugging, health endpoints, debug mode.',
    },
    '30-browser-engineering.md': {
        title: 'Browser Engineering',
        description: 'Rendering engine architecture, DOM, CSS layout, JavaScript engine internals, WebAssembly.',
    },
    '31-compilers-language-design.md': {
        title: 'Compilers & Language Design',
        description: 'Lexing, parsing, type systems, SSA optimization, interpreters, VMs, DSL design.',
    },
    '32-realtime-collaboration-systems.md': {
        title: 'Realtime Collaboration Systems',
        description: 'CRDTs, operational transform, WebSocket messaging, collaborative editing, multiplayer game servers.',
    },
    '33-search-recommendation-engines.md': {
        title: 'Search & Recommendation Engines',
        description: 'TF-IDF, BM25, inverted index, vector search, collaborative filtering, recommendation systems.',
    },
    '34-llm-ops-platform-engineering.md': {
        title: 'LLM Ops & AI Platform Engineering',
        description: 'LLM serving (vLLM, TensorRT-LLM), RAG pipelines, fine-tuning (LoRA/QLoRA), prompt engineering, model evaluation.',
    },
    '35-computer-graphics-gpu.md': {
        title: 'Computer Graphics & GPU Programming',
        description: 'Rendering pipelines, GPU architecture, GLSL/WGSL shaders, WebGPU, visualization techniques, software rasterizer.',
    },
    '36-api-integration-platforms.md': {
        title: 'API Design & Integration Platforms',
        description: 'API gateways, GraphQL federation, gRPC & Protobuf, webhooks, event-driven integration, iPaaS patterns.',
    },
    '37-media-entertainment-social.md': {
        title: 'Media, Entertainment & Social Platforms',
        description: 'Video streaming (HLS/DASH), social feed architecture, content moderation, messaging/chat, creator economy.',
    },
    '38-marketplace-ecommerce.md': {
        title: 'Marketplace & E-Commerce Platforms',
        description: 'Two-sided marketplace design, product search, escrow payments, trust & safety, logistics, inventory management.',
    },
    '39-education-learning-platforms.md': {
        title: 'Education & Learning Platforms',
        description: 'LMS architecture, adaptive learning (BKT), spaced repetition (SM-2), gamification engine, virtual classroom (WebRTC).',
    },
    '40-formal-methods-verification.md': {
        title: 'Formal Methods & Program Verification',
        description: 'Model checking (TLA+), SAT/SMT solvers (Z3), static analysis, abstract interpretation, design by contract, property-based testing.',
    },
    '41-emerging-technologies.md': {
        title: 'Emerging Technologies',
        description: 'Web3/blockchain smart contracts, edge computing (Workers), digital twins, AR/VR (WebXR), sustainable green computing.',
    },
    '43-component-manifest.md': {
        title: 'Component Manifest',
        description: 'Complete component (node + file) list required per app type — the cross-cutting manifest for generated apps.',
    },
    '44-threejs-scene-recipes.md': {
        title: 'Three.js 3D Scene Recipes',
        description: 'CDN-safe Three.js recipes for single-file HTML apps: scene skeleton, lighting/shadows, materials, LatheGeometry chess pieces, checkerboard board, movement animation, particles, CSS-3D fallback, failure modes.',
    },
};
// ─── Helpers ──────────────────────────────────────────────────────────────
function getBibleLevelName(dirName) {
    // Convert "01-foundations" to "01 — Foundations"
    const match = dirName.match(/^(\d+)-(.+)$/);
    if (match) {
        return `${match[1]} — ${match[2].replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}`;
    }
    return dirName.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
// ─── Routes ───────────────────────────────────────────────────────────────
/**
 * GET /api/library
 *
 * List all library files with metadata (title, description, last modified).
 */
router.get('/', (_req, res) => {
    try {
        const files = [];
        if (fs.existsSync(LIBRARY_DIR)) {
            const entries = fs.readdirSync(LIBRARY_DIR).sort();
            for (const entry of entries) {
                if (!entry.endsWith('.md'))
                    continue;
                const filePath = path.join(LIBRARY_DIR, entry);
                const stat = fs.statSync(filePath);
                const meta = LIBRARY_META[entry] || { title: entry.replace('.md', ''), description: '' };
                files.push({
                    name: entry,
                    title: meta.title,
                    description: meta.description,
                    modified: stat.mtime.toISOString(),
                    size: stat.size,
                });
            }
        }
        res.json({ success: true, files });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * GET /api/library/:filename
 *
 * Return content of a specific library file.
 */
router.get('/:filename', (req, res) => {
    try {
        const { filename } = req.params;
        // Prevent directory traversal
        if (filename.includes('..') || filename.includes('/')) {
            res.status(400).json({ error: 'Invalid filename' });
            return;
        }
        const filePath = path.join(LIBRARY_DIR, filename);
        if (!fs.existsSync(filePath)) {
            res.status(404).json({ error: 'File not found' });
            return;
        }
        const content = fs.readFileSync(filePath, 'utf-8');
        const stat = fs.statSync(filePath);
        const meta = LIBRARY_META[filename] || { title: filename.replace('.md', ''), description: '' };
        res.json({
            success: true,
            file: {
                name: filename,
                title: meta.title,
                description: meta.description,
                content,
                size: stat.size,
                modified: stat.mtime.toISOString(),
            },
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/library/context
 *
 * LLM-queryable context endpoint. Accepts search criteria and returns
 * relevant snippets from the reference library for contextual injection
 * during code generation and architecture planning.
 *
 * Body: {
 *   searchText?: string   — Free-text search (e.g., app goal, node description)
 *   nodeType?: string     — Filter by node type (input, output, logic, api, database, ui)
 *   language?: string     — Filter by programming language
 *   mode?: 'compact' | 'full' — How much context to return (default: 'compact')
 * }
 */
router.post('/context', (req, res) => {
    try {
        const { searchText, nodeType, language, mode } = req.body;
        let context = '';
        if (nodeType) {
            // Get context tailored to a specific node type + language
            context = getLibraryContextForNodeType(nodeType, language);
        }
        else if (searchText) {
            // Get context relevant to the search text (app goal, etc.)
            if (mode === 'full') {
                // Return search results with snippets
                const results = searchLibrary(searchText, 8);
                if (results.length === 0) {
                    context = getLibraryContext(searchText); // Fallback to topic-based
                }
                else {
                    const parts = [
                        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
                        '📚 REFERENCE LIBRARY — Search results',
                        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
                    ];
                    for (const r of results) {
                        parts.push(`\n── ${r.file.replace('.md', '')} ──`);
                        parts.push(r.snippet);
                    }
                    parts.push('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                    context = parts.join('\n');
                }
            }
            else {
                context = getLibraryContext(searchText);
            }
        }
        else {
            // No search criteria — return general library overview
            const fileList = getLibraryFileList();
            const parts = [
                '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
                '📚 REFERENCE LIBRARY — Available topics',
                '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
                '',
                'The following reference files are available. To get context on a specific',
                'topic, send a POST request with searchText matching your app goal or',
                'nodeType matching your current node type.',
                '',
            ];
            for (const f of fileList) {
                parts.push(`  • ${f.title} — Topics: ${f.topics.join(', ')}`);
            }
            parts.push('');
            parts.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
            parts.push('Pass searchText matching your app goal, or nodeType+language for targeted context.');
            context = parts.join('\n');
        }
        res.json({
            success: true,
            context,
            hasContent: !!context,
            chars: context.length,
            source: 'library',
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * GET /api/library/bible/levels
 *
 * List all Bible level directories.
 */
router.get('/bible/levels', (_req, res) => {
    try {
        const levels = [];
        if (fs.existsSync(BIBLE_DIR)) {
            const entries = fs.readdirSync(BIBLE_DIR, { withFileTypes: true }).sort((a, b) => {
                return a.name.localeCompare(b.name);
            });
            for (const entry of entries) {
                if (!entry.isDirectory())
                    continue;
                const dirPath = path.join(BIBLE_DIR, entry.name);
                const files = fs.readdirSync(dirPath).filter(f => f.endsWith('.md') || f.endsWith('.txt'));
                levels.push({
                    dir: entry.name,
                    name: getBibleLevelName(entry.name),
                    fileCount: files.length,
                    hasMasterIndex: fs.existsSync(path.join(dirPath, 'MASTER-INDEX.txt')),
                });
            }
        }
        res.json({ success: true, levels });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * GET /api/library/bible/:level
 *
 * List files in a Bible level.
 */
router.get('/bible/:level', (req, res) => {
    try {
        const { level } = req.params;
        // Prevent directory traversal
        if (level.includes('..') || level.includes('/')) {
            res.status(400).json({ error: 'Invalid level' });
            return;
        }
        const levelPath = path.join(BIBLE_DIR, level);
        if (!fs.existsSync(levelPath) || !fs.statSync(levelPath).isDirectory()) {
            res.status(404).json({ error: 'Level not found' });
            return;
        }
        const files = [];
        const dirs = [];
        // Recursively list files in this level (up to 2 levels deep)
        const walk = (dir, relativePath, depth) => {
            if (depth > 2)
                return;
            const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                const relPath = relativePath ? `${relativePath}/${entry.name}` : entry.name;
                if (entry.isDirectory()) {
                    if (depth === 0)
                        dirs.push(entry.name);
                    walk(fullPath, relPath, depth + 1);
                }
                else if (entry.name.endsWith('.md') || entry.name.endsWith('.txt')) {
                    const stat = fs.statSync(fullPath);
                    files.push({
                        name: relPath,
                        path: level + '/' + relPath,
                        size: stat.size,
                    });
                }
            }
        };
        walk(levelPath, '', 0);
        // Also check for MASTER-INDEX.txt at the Bible root
        let masterIndex = null;
        const masterIndexPath = path.join(BIBLE_DIR, 'MASTER-INDEX.txt');
        if (fs.existsSync(masterIndexPath)) {
            const content = fs.readFileSync(masterIndexPath, 'utf-8');
            // Extract the section for this specific level
            const lines = content.split('\n');
            const levelSection = [];
            let inSection = false;
            const levelNum = level.match(/^(\d+)/)?.[1] || '';
            for (const line of lines) {
                if (line.trim().startsWith(levelNum + '.') || line.trim().startsWith(levelNum + ' —')) {
                    inSection = true;
                }
                if (inSection) {
                    if (line.trim().match(/^\d+\./) && !line.trim().startsWith(levelNum + '.')) {
                        break;
                    }
                    levelSection.push(line);
                }
            }
            if (levelSection.length > 0) {
                masterIndex = levelSection.join('\n');
            }
        }
        res.json({
            success: true,
            level: {
                dir: level,
                name: getBibleLevelName(level),
            },
            files,
            subdirectories: dirs,
            masterIndex,
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
/**
 * GET /api/library/bible/:level/:filename
 *
 * Return content of a file within a Bible level.
 */
router.get('/bible/:level/:filename(*)', (req, res) => {
    try {
        const { level, filename } = req.params;
        // Prevent directory traversal
        if (level.includes('..') || filename.includes('..')) {
            res.status(400).json({ error: 'Invalid path' });
            return;
        }
        const filePath = path.join(BIBLE_DIR, level, filename);
        if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
            res.status(404).json({ error: 'File not found' });
            return;
        }
        const content = fs.readFileSync(filePath, 'utf-8');
        const stat = fs.statSync(filePath);
        res.json({
            success: true,
            file: {
                name: filename,
                path: level + '/' + filename,
                content,
                size: stat.size,
                modified: stat.mtime.toISOString(),
            },
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
export default router;
