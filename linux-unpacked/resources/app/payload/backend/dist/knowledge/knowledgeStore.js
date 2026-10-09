import * as fs from 'fs';
import * as path from 'path';
import { KNOWLEDGE_DIR } from './knowledgeTypes.js';
import { isQualityCode, isAutoLearnDisabled } from './qualityGate.js';
class KnowledgeStore {
    patterns = [];
    currentSheet = 1;
    sheetMetaPath = '';
    isArchiving = false;
    isBatchLoading = false;
    static SHEET_CAP = 100;
    filePath;
    constructor() {
        // `VACA_KNOWLEDGE_DIR` redirects the store to a throwaway directory. Set it
        // (before this singleton is constructed) in any TEST that writes patterns,
        // so a test run never mutates the real `knowledge/patterns.json` — a test
        // isolation hazard observed live (a run truncated the committed store).
        const override = process.env.VACA_KNOWLEDGE_DIR;
        const baseDir = override ? path.resolve(override) : path.join(process.cwd(), KNOWLEDGE_DIR);
        if (!fs.existsSync(baseDir)) {
            fs.mkdirSync(baseDir, { recursive: true });
        }
        this.filePath = path.join(baseDir, 'patterns.json');
        this.load();
        this.sheetMetaPath = path.join(baseDir, 'sheet-meta.json');
        this.loadSheetMeta();
    }
    load() {
        try {
            if (fs.existsSync(this.filePath)) {
                const data = fs.readFileSync(this.filePath, 'utf-8');
                this.patterns = JSON.parse(data);
                console.log(`[knowledge] Loaded ${this.patterns.length} patterns`);
            }
        }
        catch (err) {
            console.error('[knowledge] Error loading patterns:', err);
            this.patterns = [];
        }
    }
    save() {
        try {
            const dir = path.dirname(this.filePath);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
            fs.writeFileSync(this.filePath, JSON.stringify(this.patterns, null, 2), 'utf-8');
        }
        catch (err) {
            console.error('[knowledge] Error saving patterns:', err);
        }
    }
    saveSheetMeta() {
        try {
            if (!this.sheetMetaPath)
                return;
            const dir = path.dirname(this.sheetMetaPath);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
            fs.writeFileSync(this.sheetMetaPath, JSON.stringify({ currentSheet: this.currentSheet }, null, 2), 'utf-8');
        }
        catch { }
    }
    loadSheetMeta() {
        try {
            if (this.sheetMetaPath && fs.existsSync(this.sheetMetaPath)) {
                const data = JSON.parse(fs.readFileSync(this.sheetMetaPath, 'utf-8'));
                this.currentSheet = data.currentSheet || 1;
                console.log(`[knowledge] Sheet #${this.currentSheet} (${this.count()}/${KnowledgeStore.SHEET_CAP} patterns)`);
            }
        }
        catch {
            this.currentSheet = 1;
        }
    }
    getAll() {
        return [...this.patterns];
    }
    getById(id) {
        return this.patterns.find(p => p.id === id);
    }
    query(query) {
        let results = [...this.patterns];
        if (query.tags && query.tags.length > 0) {
            results = results.filter(p => query.tags.some(tag => p.tags.includes(tag)));
        }
        if (query.nodeType) {
            results = results.filter(p => p.nodeType === query.nodeType);
        }
        if (query.language) {
            results = results.filter(p => p.language === query.language);
        }
        if (query.targetOS) {
            results = results.filter(p => p.targetOS === query.targetOS);
        }
        // Token hits per pattern, when a searchText was given. Kept alongside the
        // results so the final sort can rank by relevance with quality as the
        // TIEBREAK (see below).
        const hitsByPattern = new Map();
        if (query.searchText) {
            // Tokenized matching: split the query into words and require at least
            // one token to hit, ranking by how many tokens hit. A whole-phrase
            // substring still matches (strongest signal), but natural multi-word
            // queries like "what do you know about building arcade games" no longer
            // fall through empty — "arcade" alone would match the game patterns.
            const text = query.searchText.toLowerCase();
            const stopwords = new Set([
                'the', 'and', 'for', 'with', 'about', 'what', 'do', 'you', 'your',
                'have', 'has', 'are', 'this', 'that', 'from', 'how', 'why', 'does',
                'any', 'some', 'tell', 'me', 'know', 'building', 'apps', 'app',
            ]);
            const tokens = text
                .split(/[^a-z0-9]+/)
                .filter(t => t.length >= 3 && !stopwords.has(t));
            const haystack = (p) => `${p.title} ${p.description} ${p.code} ${p.tags.join(' ')}`.toLowerCase();
            const phraseHit = (p) => text.length > 0 && haystack(p).includes(text);
            const tokenHits = (p) => tokens.filter(t => haystack(p).includes(t)).length;
            const scored = results
                .map(p => ({ p, hits: phraseHit(p) ? tokens.length + 1 : tokenHits(p) }))
                .filter(({ hits }) => hits > 0);
            for (const { p, hits } of scored)
                hitsByPattern.set(p, hits);
            results = scored.map(({ p }) => p);
        }
        // Relevance ranks ABOVE quality; quality is the tiebreak.
        //
        // This used to be two sequential sorts — relevance, then an unconditional
        // quality sort. Since Array.sort is stable, that only preserved relevance
        // on exact quality ties, so a merely higher-scored pattern buried a more
        // relevant one: for the goal "compute the factorial of a number", the
        // hand-curated C++ interactive-loop pattern (qualityScore 8) came back
        // ahead of `Factorial (java)` (7). Quality is now a tiebreak inside
        // relevance, where it belongs. With no searchText this is the same pure
        // quality/usage ordering as before.
        results.sort((a, b) => {
            if (query.searchText) {
                const hitDelta = (hitsByPattern.get(b) ?? 0) - (hitsByPattern.get(a) ?? 0);
                if (hitDelta !== 0)
                    return hitDelta;
            }
            const scoreA = a.qualityScore + (a.usageCount * 0.1);
            const scoreB = b.qualityScore + (b.usageCount * 0.1);
            return scoreB - scoreA;
        });
        if (query.limit && query.limit > 0) {
            results = results.slice(0, query.limit);
        }
        return results;
    }
    /**
     * Add a pattern to the knowledge store — the ONE funnel every capture path
     * (learning engine, auto-learn service, scanner, ServiceTools, manual API)
     * must go through. Enforces:
     *   1. The AUTO_LEARN_DISABLED kill switch (poisoning-loop quarantine).
     *   2. The isQualityCode gate (no markdown leaks / prose / stubs / prompt
     *      artifacts / JSX-in-ts), so re-enabling capture can't re-poison.
     * Returns null when rejected — callers must handle it.
     */
    addPattern(pattern) {
        // Kill switch — hard quarantine. Nothing enters the store while disabled,
        // regardless of which caller or what `success` flag it passes.
        if (isAutoLearnDisabled()) {
            console.log(`[knowledge] ⛔ REJECTED (AUTO_LEARN_DISABLED): ${pattern.title} — capture quarantined`);
            return null;
        }
        // Quality gate — permanent poison filter, active even when capture is
        // re-enabled. Never store markdown-fenced prose or stub/placeholder code.
        const code = pattern.code || '';
        const lang = pattern.language || 'typescript';
        if (!isQualityCode(code, lang)) {
            console.log(`[knowledge] ⛔ REJECTED (quality gate): ${pattern.title} — content is not clean code`);
            return null;
        }
        const entry = {
            ...pattern,
            id: `pat_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
            usageCount: 0,
            createdAt: new Date().toISOString(),
            lastUsed: pattern.lastUsed || new Date().toISOString(),
        };
        this.patterns.push(entry);
        this.save();
        console.log(`[knowledge] Added pattern: ${entry.title}`);
        // Auto-trigger lightweight RNN training on any new pattern
        if (!this.isBatchLoading) {
            this.quickTrainOnPattern();
        }
        // Check if we have hit the 100-pattern cap - archive sheet and start fresh
        if (this.patterns.length >= KnowledgeStore.SHEET_CAP) {
            // Defer archive to next tick to avoid blocking
            this.isArchiving = true;
            setTimeout(() => { this.archiveCurrentSheet(); this.isArchiving = false; }, 0);
        }
        return entry;
    }
    /**
     * Add multiple patterns at once, skipping individual auto-training.
     * Triggers a single quick-train at the end if there are new patterns.
     */
    batchAddPatterns(patterns) {
        const added = [];
        this.isBatchLoading = true;
        try {
            for (const pattern of patterns) {
                // addPattern returns null when the kill switch / quality gate rejects
                // it — only keep patterns that actually got stored.
                const stored = this.addPattern(pattern);
                if (stored)
                    added.push(stored);
            }
        }
        finally {
            this.isBatchLoading = false;
        }
        // Single consolidated quick-train at the end
        if (added.length > 0) {
            this.quickTrainOnPattern();
        }
        return added;
    }
    quickTrainOnPattern() {
        (async () => {
            try {
                const { rnnEngine } = await import('../neural/trainer.js');
                if (!rnnEngine.isTraining) {
                    const result = await rnnEngine.learnFromKnowledge(50);
                    if (result.chars > 0) {
                        console.log(`[knowledge] RNN quick-trained: loss=${result.loss.toFixed(2)}`);
                    }
                }
            }
            catch {
                // Neural module not available - optional
            }
        })();
    }
    usePattern(id) {
        const pattern = this.getById(id);
        if (pattern) {
            pattern.usageCount++;
            pattern.lastUsed = new Date().toISOString();
            this.save();
        }
    }
    updateQuality(id, score) {
        const pattern = this.getById(id);
        if (pattern) {
            pattern.qualityScore = Math.max(0, Math.min(10, score));
            pattern.lastUsed = new Date().toISOString();
            this.save();
        }
    }
    deletePattern(id) {
        const index = this.patterns.findIndex(p => p.id === id);
        if (index !== -1) {
            this.patterns.splice(index, 1);
            this.save();
            return true;
        }
        return false;
    }
    getRelevantContext(nodeType, language, targetOS, limit = 5, searchText) {
        // Goal-aware when a goal is supplied: prefer patterns that actually match
        // it. Falls back to the plain top-N so a goal sharing no tokens with any
        // pattern never strips a language's examples away entirely.
        let results = searchText
            ? this.query({ nodeType, language, targetOS, limit, searchText })
            : [];
        if (results.length === 0) {
            results = this.query({ nodeType, language, targetOS, limit });
        }
        if (results.length === 0)
            return '';
        let context = '\n\n--- Learned Patterns from Previous Projects ---\n';
        context += 'Here are some successful code patterns that may be relevant:\n\n';
        results.forEach((pattern, i) => {
            context += `Pattern ${i + 1}: ${pattern.title}\n`;
            context += `Description: ${pattern.description}\n`;
            context += `Tags: ${pattern.tags.join(', ')}\n`;
            context += `Code:\n${pattern.code}\n\n`;
        });
        context += '--- End of Learned Patterns ---\n';
        return context;
    }
    count() {
        return this.patterns.length;
    }
    getCurrentSheet() {
        return this.currentSheet;
    }
    /**
     * Archive all current patterns as a training sheet, export to LLM Training Studio,
     * and reset for a new sheet. Automatically triggered at 750 patterns.
     * Returns info about the archived sheet, or null if there were no patterns.
     */
    archiveCurrentSheet() {
        const patterns = this.patterns;
        if (patterns.length === 0)
            return null;
        const sheetNumber = this.currentSheet;
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `venorica-sheet-${String(sheetNumber).padStart(3, '0')}-${timestamp}.jsonl`;
        // Build export path to Training Studio
        const studioDir = path.join(process.cwd(), 'llm-training-app', 'data', 'uploads');
        let exportPath = null;
        try {
            if (!fs.existsSync(studioDir)) {
                fs.mkdirSync(studioDir, { recursive: true });
            }
            const fullPath = path.join(studioDir, filename);
            const lines = patterns.map(p => JSON.stringify({
                text: p.code,
                title: p.title,
                language: p.language,
                nodeType: p.nodeType,
                tags: p.tags,
                sheet: sheetNumber,
                source: 'venorica-sheet',
                timestamp: p.createdAt,
            }));
            fs.writeFileSync(fullPath, lines.join('\n'), 'utf-8');
            exportPath = fullPath;
            console.log(`[knowledge] Sheet #${sheetNumber} archived: ${patterns.length} patterns -> ${fullPath}`);
        }
        catch (e) {
            console.error('[knowledge] Failed to archive sheet:', e);
        }
        // Clear patterns and advance sheet
        this.patterns = [];
        this.currentSheet++;
        this.save();
        this.saveSheetMeta();
        console.log(`[knowledge] Started sheet #${this.currentSheet}`);
        return { sheetNumber, patternCount: patterns.length, exportPath };
    }
}
export const knowledgeStore = new KnowledgeStore();
