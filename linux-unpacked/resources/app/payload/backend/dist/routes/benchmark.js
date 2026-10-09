import { Router } from 'express';
const router = Router();
const MODELS = [
    {
        name: '0.5b-cpu',
        label: '0.5B (CPU)',
        baseUrl: 'http://127.0.0.1:11436',
        model: 'qwen2.5-coder:0.5b',
    },
    {
        name: '1.5b-gpu',
        label: '1.5B (GPU)',
        baseUrl: process.env.OLLAMA_BASE_URL || 'http://192.168.1.234:11434',
        model: 'qwen2.5-coder:1.5b',
    },
    {
        name: '7b-gpu',
        label: '7B (GPU)',
        baseUrl: process.env.OLLAMA_BASE_URL || 'http://192.168.1.234:11434',
        model: 'qwen2.5-7b-instruct-uncensored',
    },
];
/**
 * Call Ollama generate API with timing.
 * Returns generated text and timing info.
 */
async function callModel(endpoint, prompt, maxTokens) {
    const url = `${endpoint.baseUrl}/api/generate`;
    const payload = {
        model: endpoint.model,
        prompt,
        stream: true,
        options: {
            num_predict: maxTokens,
            temperature: 0.2,
        },
    };
    const startTime = Date.now();
    let firstTokenTime = 0;
    let fullText = '';
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(120000),
        });
        if (!response.ok) {
            const errText = await response.text().catch(() => 'unknown error');
            return {
                success: false,
                text: '',
                timeToFirstToken: 0,
                totalTime: Date.now() - startTime,
                chars: 0,
                error: `HTTP ${response.status}: ${errText.slice(0, 200)}`,
            };
        }
        const reader = response.body?.getReader();
        if (!reader) {
            return {
                success: false,
                text: '',
                timeToFirstToken: 0,
                totalTime: Date.now() - startTime,
                chars: 0,
                error: 'No response body',
            };
        }
        const decoder = new TextDecoder();
        let buffer = '';
        let gotFirstToken = false;
        while (true) {
            const { done, value } = await reader.read();
            if (done)
                break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed)
                    continue;
                try {
                    const obj = JSON.parse(trimmed);
                    const token = obj.response || '';
                    if (!gotFirstToken && token.trim()) {
                        firstTokenTime = Date.now();
                        gotFirstToken = true;
                    }
                    fullText += token;
                    if (obj.done)
                        break;
                }
                catch {
                    // Skip malformed JSON lines
                }
            }
        }
        const totalTime = Date.now() - startTime;
        const ttft = gotFirstToken
            ? (firstTokenTime - startTime) / 1000
            : totalTime / 1000;
        // Clean markdown fences
        let cleaned = fullText.trim();
        cleaned = cleaned.replace(/^```(?:\w+)?\s*\n?/i, '');
        cleaned = cleaned.replace(/\n?```\s*$/i, '');
        return {
            success: true,
            text: cleaned.trim(),
            timeToFirstToken: parseFloat(ttft.toFixed(3)),
            totalTime: parseFloat((totalTime / 1000).toFixed(1)),
            chars: cleaned.trim().length,
        };
    }
    catch (err) {
        const msg = err.name === 'AbortError' ? 'Request timed out after 120s' : err.message;
        return {
            success: false,
            text: '',
            timeToFirstToken: 0,
            totalTime: Date.now() - startTime,
            chars: 0,
            error: msg,
        };
    }
}
/**
 * Evaluate code quality for benchmark comparison.
 */
function evaluateQuality(text) {
    if (!text) {
        return { score: 0, hasCode: false, syntaxValid: false, lines: 0, chars: 0, issues: ['Empty response'] };
    }
    const issues = [];
    let score = 100;
    const hasCode = text.length > 50;
    const hasFences = text.includes('```');
    const hasExplanation = /here|here's|this code|the code|explanation|note:/i.test(text);
    if (hasFences) {
        issues.push('Markdown fences');
        score -= 10;
    }
    if (hasExplanation) {
        issues.push('Explanatory text');
        score -= 5;
    }
    // Count exports (TS), function defs, CSS selectors
    const exports = (text.match(/\bexport\s+(?:function|class|interface|type|const|enum|default)\b/g) || []).length;
    if (exports === 0 && text.length > 200) {
        score -= 10;
    }
    const lines = text.split('\n').length;
    const chars = text.length;
    if (chars < 100) {
        issues.push('Very short');
        score -= 20;
    }
    else if (chars > 8000) {
        issues.push('Very long');
        score -= 5;
    }
    const syntaxValid = exports > 0 || /\b(?:function|def|class|import|export|const|let|var)\b/.test(text);
    return {
        score: Math.max(0, Math.min(100, score)),
        hasCode,
        syntaxValid,
        lines,
        chars,
        issues,
    };
}
/**
 * POST /api/benchmark/run
 * Runs a prompt against all 3 models in parallel with timing.
 */
router.post('/run', async (req, res) => {
    try {
        const { prompt, maxTokens } = req.body;
        if (!prompt || typeof prompt !== 'string') {
            return res.status(400).json({ success: false, error: 'prompt is required (string)' });
        }
        const tokens = Math.min(Math.max(maxTokens || 2048, 64), 8192);
        // Run all 3 models in parallel
        const startTime = Date.now();
        const results = await Promise.allSettled(MODELS.map(model => callModel(model, prompt, tokens)));
        const wallTime = ((Date.now() - startTime) / 1000).toFixed(1);
        const output = {};
        for (let i = 0; i < MODELS.length; i++) {
            const model = MODELS[i];
            const result = results[i];
            if (result.status === 'fulfilled' && result.value.success) {
                const r = result.value;
                output[model.name] = {
                    label: model.label,
                    success: true,
                    text: r.text,
                    timeToFirstToken: r.timeToFirstToken,
                    totalTime: r.totalTime,
                    chars: r.chars,
                    quality: evaluateQuality(r.text),
                };
            }
            else {
                const err = result.status === 'rejected' ? result.reason?.message || 'Unknown error' :
                    result.value?.error || 'Generation failed';
                output[model.name] = {
                    label: model.label,
                    success: false,
                    text: '',
                    timeToFirstToken: 0,
                    totalTime: result.status === 'fulfilled' ? result.value.totalTime / 1000 : 0,
                    chars: 0,
                    error: err,
                    quality: { score: 0, hasCode: false, syntaxValid: false, lines: 0, chars: 0, issues: [err] },
                };
            }
        }
        // Compute speedup ratios
        const sevenB = output['7b-gpu'];
        const halfB = output['0.5b-cpu'];
        const oneFiveB = output['1.5b-gpu'];
        let speedups = {};
        if (sevenB?.success && halfB?.success && sevenB.totalTime > 0 && halfB.totalTime > 0) {
            speedups['0.5b-vs-7b'] = `${(sevenB.totalTime / halfB.totalTime).toFixed(1)}x`;
        }
        if (sevenB?.success && oneFiveB?.success && sevenB.totalTime > 0 && oneFiveB.totalTime > 0) {
            speedups['1.5b-vs-7b'] = `${(sevenB.totalTime / oneFiveB.totalTime).toFixed(1)}x`;
        }
        res.json({
            success: true,
            prompt,
            maxTokens: tokens,
            wallTime: parseFloat(wallTime),
            speedups,
            models: output,
        });
    }
    catch (err) {
        res.status(500).json({
            success: false,
            error: err.message || 'Benchmark failed',
        });
    }
});
/**
 * GET /api/benchmark/presets
 * Returns a list of preset prompts for quick testing.
 */
router.get('/presets', (_req, res) => {
    res.json({
        success: true,
        presets: [
            {
                id: 'types',
                label: 'Type Definitions',
                complexity: 'simple',
                prompt: `Generate TypeScript type definitions for a user management system.
Include types for: User, UserRole (Admin, Editor, Viewer), CreateUserDto, UpdateUserDto, UserFilter.
Use interfaces and enums where appropriate. Return ONLY valid TypeScript code, no explanations.`,
            },
            {
                id: 'css',
                label: 'CSS Styles',
                complexity: 'simple',
                prompt: `Generate CSS for a dark-mode admin dashboard sidebar.
Include: sidebar container (280px, dark bg #1a1a2e), nav items with hover states,
active item indicator, collapsible sections, smooth transitions.
Use CSS variables for colors. Return ONLY valid CSS, no explanations.`,
            },
            {
                id: 'api',
                label: 'Express API Handler',
                complexity: 'medium',
                prompt: `Generate a Node.js Express route handler for a task management API.
Include endpoints: GET /tasks (list with pagination), POST /tasks (create),
PUT /tasks/:id (update), DELETE /tasks/:id (soft delete).
Each endpoint should have input validation, error handling, and proper HTTP status codes.
Use async/await. Return ONLY valid TypeScript code, no explanations.`,
            },
            {
                id: 'utility',
                label: 'Data Transformation',
                complexity: 'medium',
                prompt: `Generate a Python utility module for data transformation.
Include functions:
- flatten_dict(d, parent_key='', sep='.') - flattens nested dicts
- group_by(iterable, key_fn) - groups items by a key function
- chunk_list(lst, chunk_size) - splits list into chunks
- merge_dicts(*dicts, strategy='overwrite') - merges multiple dicts
Each function should have proper type hints, docstrings, and edge case handling.
Return ONLY valid Python code, no explanations.`,
            },
            {
                id: 'chess',
                label: 'Chess Move Validator',
                complexity: 'complex',
                prompt: `Generate a TypeScript chess move validator class.
Implement: board representation (8x8 array), piece placement,
move validation for all pieces (pawn, rook, knight, bishop, queen, king),
check detection, checkmate detection, en passant, castling.
Include proper error handling and type definitions.
Focus on the core logic - board state management and legal move generation.
Return ONLY valid TypeScript code, no explanations.`,
            },
            {
                id: 'database',
                label: 'Database Repository',
                complexity: 'complex',
                prompt: `Generate a TypeScript database repository class using SQLite.
Implement a UserRepository with CRUD operations, paginated list with search,
parameterized queries, and transaction support.
Include proper TypeScript types and error handling.
Return ONLY valid TypeScript code, no explanations.`,
            },
        ],
    });
});
export { router as benchmarkRoutes };
