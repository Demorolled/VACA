import { knowledgeStore } from './knowledgeStore.js';
import { isQualityCode, isAutoLearnDisabled, MARKDOWN_FENCE_RE, BATCH_SEPARATOR_RE, PROMPT_ARTIFACT_RE } from './qualityGate.js';
import { languageFromPath as detectLanguageFromPath } from '../utils/languageFromPath.js';
/**
 * Deterministic file-path → node label (write path: no canvas node exists, so
 * the file's stem becomes the node label the pattern is stored under).
 */
function labelFromPath(p) {
    const base = p.split('/').pop() || p;
    const dot = base.lastIndexOf('.');
    const stem = dot > 0 ? base.slice(0, dot) : base;
    return stem.replace(/[^a-zA-Z0-9_-]+/g, '_') || base;
}
class LearningEngine {
    /**
     * Extract code patterns from a generated project and store them in the knowledge base
     */
    learnFromProject(project, generatedCode, success) {
        const entries = [];
        // Kill switch: AUTO_LEARN_DISABLED=true|1 stops ALL pattern capture. The
        // poisoning loop stored broken output (markdown fences, prose, hallucinated
        // APIs) as "successful" patterns with qualityScore up to 7.5 — this gate
        // makes capture opt-in until the loop is proven fixed. Mirrors the
        // VENORICA_DISABLED convention. Covers every caller: the per-file capture in
        // fileGenerator.ts and the POST /api/knowledge/learn route. (Even if a
        // caller skips this check, addPattern itself is gated at the funnel.)
        if (isAutoLearnDisabled())
            return entries;
        if (!project.nodes || project.nodes.length === 0)
            return entries;
        for (const node of project.nodes) {
            const code = node.data?.generatedCode || '';
            if (!code.trim())
                continue;
            // Only store patterns from successful generations
            const nodeSuccess = node.data?.status === 'valid' || success;
            if (!nodeSuccess)
                continue;
            // Deterministic quality gate — never learn from stub/prose/JSX-in-ts code
            if (!isQualityCode(code, node.data?.language || 'typescript'))
                continue;
            // Generate tags from node data
            const tags = [node.type];
            if (node.data?.language)
                tags.push(node.data.language);
            if (project.targetOS)
                tags.push(project.targetOS);
            if (node.data?.label)
                tags.push(node.data.label.toLowerCase().replace(/\s+/g, '_'));
            // Extract key patterns from the code (language-aware: the TS regexes
            // never match Rust/C++/Go, which used to truncate non-TS code mid-block).
            const patternCode = this.extractKeyPattern(code, node.data?.language);
            if (!patternCode)
                continue;
            const entry = knowledgeStore.addPattern({
                category: 'code_pattern',
                title: `${node.data?.label || node.type} - ${node.type} pattern`,
                code: patternCode,
                description: `A ${node.type} node implementation for ${project.name}. Language: ${node.data?.language || 'unknown'}, OS: ${project.targetOS}`,
                tags,
                projectId: project.id,
                targetOS: project.targetOS || 'linux',
                nodeType: node.type,
                language: node.data?.language || 'javascript',
                success: true,
                qualityScore: Math.max(5.0, this.rateGeneratedCode(patternCode, node.data?.language)),
            });
            // addPattern returns null when the kill switch or the funnel quality
            // gate rejects it — only count patterns that actually got stored.
            if (entry)
                entries.push(entry);
        }
        // Also store the overall architecture as a pattern
        if (generatedCode && success && generatedCode.length > 50) {
            const archTags = ['architecture', project.targetOS || 'linux'];
            project.nodes.forEach(n => {
                if (!archTags.includes(n.type))
                    archTags.push(n.type);
            });
            knowledgeStore.addPattern({
                category: 'architecture',
                lastUsed: new Date().toISOString(),
                title: `${project.name} - Full architecture`,
                code: generatedCode.substring(0, 2000), // Store first 2000 chars
                description: `Complete project architecture for ${project.name} with ${project.nodes.length} nodes targeting ${project.targetOS}`,
                tags: archTags,
                projectId: project.id,
                targetOS: project.targetOS || 'linux',
                nodeType: 'master',
                language: 'mixed',
                success: true,
                qualityScore: 5.0,
            });
        }
        console.log(`[learning] Stored ${entries.length} patterns from project "${project.name}"`);
        // Auto-trigger RNN training on new patterns (fire-and-forget)
        if (entries.length > 0) {
            // Fire-and-forget: train RNN on new patterns
            (async () => {
                try {
                    const { rnnEngine } = await import('../neural/trainer.js');
                    const result = await rnnEngine.learnFromKnowledge(100);
                    // Only log when training actually ran (skipped silently when Venorica
                    // is disabled or there was nothing to train — keeps the log quiet).
                    if (result.chars > 0) {
                        console.log(`[learning] RNN trained: loss=${result.loss.toFixed(4)}, chars=${result.chars}`);
                    }
                }
                catch (err) {
                    // Neural module not available or training failed — not critical
                }
            })();
        }
        return entries;
    }
    /**
     * Learn from a set of generated files belonging to an existing project
     * (canvas / blueprint builds). Populates each node's generatedCode exactly
     * like the frontend does after generation, then runs the same verified
     * learning loop as learnFromProject. Extracted from fileGenerator.ts so the
     * blueprint build route — which skips FileGenerator's generic learning while
     * skipVerifiedCapture is set — can close the SAME loop with one call.
     */
    learnFromGeneratedFiles(project, files) {
        if (isAutoLearnDisabled() || !project.nodes?.length)
            return [];
        // Shallow-copy the project so learning never mutates the store's live
        // project object — only the copy carries generatedCode.
        const learnProject = {
            ...project,
            nodes: project.nodes.map((n) => ({ ...n, data: { ...n.data } })),
        };
        for (const file of files) {
            const node = learnProject.nodes.find((n) => n.id === file.nodeId);
            if (node && file.code && file.validated && file.nodeId !== 'preview_gui_wrapper') {
                node.data.generatedCode = file.code;
                node.data.status = 'valid';
            }
        }
        const fullAppCode = files
            .filter((f) => f.nodeId && f.nodeId !== 'preview_gui_wrapper')
            .map((f) => f.code)
            .join('\n\n');
        return this.learnFromProject(learnProject, fullAppCode, true);
    }
    /**
     * Learn from a flat list of files with no project graph (the codePlanner
     * write path — plan-code → write-code produces {path, content} files, not
     * canvas nodes). Builds a synthetic one-node-per-file project so the SAME
     * verified learning loop stores patterns from chat writes. The write route
     * only calls this AFTER its tsc gate reports clean — broken output never
     * enters the store.
     */
    learnFromFiles(opts) {
        if (isAutoLearnDisabled() || !opts.files.length)
            return [];
        const nodes = opts.files.map((f, i) => {
            const language = f.language || detectLanguageFromPath(f.path);
            return {
                id: `file_${i}`,
                type: 'logic',
                position: { x: 0, y: i * 80 },
                data: {
                    label: labelFromPath(f.path),
                    description: `Generated file ${f.path}`,
                    status: 'valid',
                    language,
                    generatedCode: f.content,
                },
            };
        });
        const project = {
            id: opts.projectId || `write_${Date.now()}`,
            name: opts.projectName,
            targetOS: opts.targetOS || 'linux',
            nodes,
            edges: [],
            createdAt: new Date(),
            updatedAt: new Date(),
        };
        const fullAppCode = opts.files.map((f) => f.content).join('\n\n');
        return this.learnFromProject(project, fullAppCode, true);
    }
    /**
     * Get context from past patterns to inject into LLM prompts
     */
    getGenerationContext(nodeType, language, targetOS, searchText) {
        return knowledgeStore.getRelevantContext(nodeType, language, targetOS, 3, searchText);
    }
    /**
     * Extract the most relevant portion of code as a reusable pattern
     */
    extractKeyPattern(code, language) {
        const cleaned = code.trim();
        if (cleaned.length <= 500)
            return cleaned;
        const lang = (language || 'typescript').toLowerCase();
        if (lang === 'typescript' || lang === 'javascript') {
            // Prioritize: function definitions > class definitions > the rest
            const funcMatch = cleaned.match(/((?:async\s+)?function\s+\w+[^{]*\{[^}]*\})/);
            if (funcMatch)
                return funcMatch[1];
            const classMatch = cleaned.match(/(class\s+\w+[^{]*\{[^}]*\})/);
            if (classMatch)
                return classMatch[1];
            return cleaned.substring(0, 500) + '\n// ... (truncated)';
        }
        // Non-TS: the TS regexes never match `fn`, `func`, `struct`, `impl`, `def`,
        // `int main`, … so a long file was cut to 500 chars mid-construct. Extract
        // the FIRST brace-balanced top-level block instead (a whole declaration).
        const firstBrace = cleaned.indexOf('{');
        if (firstBrace >= 0) {
            let depth = 0;
            for (let i = firstBrace; i < cleaned.length; i++) {
                if (cleaned[i] === '{')
                    depth++;
                else if (cleaned[i] === '}') {
                    depth--;
                    if (depth === 0)
                        return cleaned.slice(0, i + 1).slice(0, 2000);
                }
            }
        }
        // Brace-less languages (Python/Ruby) or an unbalanced tail: keep a larger
        // head so a whole statement block survives.
        return cleaned.slice(0, 1500);
    }
    /**
     * Rate the quality of generated code and update stored patterns
     */
    rateGeneratedCode(code, language) {
        let score = 5.0; // Start at neutral
        // Positive signals — TS/JS shapes, plus a language-specific marker so a
        // clean Rust/C++/Go/Java pattern is not scored as if it had no structure.
        if (code.includes('function') || code.includes('class'))
            score += 1.0;
        if (code.includes('try') || code.includes('catch'))
            score += 0.5;
        if (code.includes('const') || code.includes('let'))
            score += 0.5;
        if (code.length > 200)
            score += 0.5;
        if (code.includes('export'))
            score += 0.5;
        const lang = (language || '').toLowerCase();
        const MARKERS = {
            rust: /\bfn\s+\w+|\bstruct\b|\bimpl\b|\bResult\b|\buse\s+std::/,
            cpp: /#include\s*<|std::|\bclass\b|\bint\s+main\b/,
            c: /#include\s*<|\bint\s+main\b|\bprintf\b/,
            go: /package\s+main|\bfunc\s+\w+|\bimport\b/,
            java: /public\s+class|\bimport\s+java\.|System\.out/,
            csharp: /using\s+System|\bclass\b|Console\./,
            python: /\bdef\s+\w+|\bclass\b|\bimport\b/,
            php: /<\?php|\bfunction\s+\w+/,
            ruby: /\bdef\s+\w+|\bclass\b|\brequire/,
            kotlin: /\bfun\s+\w+|\bclass\b|\bval\b/,
            swift: /\bfunc\s+\w+|\bimport\s+\w+|\blet\b/,
        };
        if (MARKERS[lang]?.test(code))
            score += 1.0;
        // Negative signals
        if (code.includes('any'))
            score -= 0.3;
        if (code.includes('var '))
            score -= 0.3;
        if (code.includes('TODO'))
            score -= 0.2;
        if (code.includes('FIXME'))
            score -= 0.2;
        // Markdown leaks are fatal — heavy penalty as belt-and-braces on top of
        // the isQualityCode gate (some callers may skip the gate).
        if (MARKDOWN_FENCE_RE.test(code))
            score -= 4;
        if (BATCH_SEPARATOR_RE.test(code))
            score -= 3;
        if (PROMPT_ARTIFACT_RE.test(code))
            score -= 3;
        return Math.max(0, Math.min(10, score));
    }
}
export const learningEngine = new LearningEngine();
