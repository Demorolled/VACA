/**
 * Micro-App Experimenter (idle-time self-improvement loop)
 * ========================================================
 *
 * While the backend is idle (> IDLE_EXPERIMENTER_THRESHOLD_MS, default 60s),
 * this service makes the LLM build a micro-app "from the ground up" and then
 * iteratively REWRITES that same app to be smaller and faster and more
 * universal. Each accepted rewrite (still compiles + passes smoke, with a lower
 * balanced size/speed score) is stored as a "new idea" in the ideas database
 * (`data/micro-app-ideas.json`) — capturing the new design, the purpose of the
 * app it built, and the winning code. That database is later transformed into
 * training data via `exportTrainingData()` (JSONL, matching the project's
 * existing venorica-sheet / auto-learn capture format).
 *
 * OFF BY DEFAULT: the whole loop is inert unless IDLE_EXPERIMENTER_ENABLED=1.
 *
 * Env knobs:
 *   IDLE_EXPERIMENTER_ENABLED        =1|0   (default 0)
 *   IDLE_EXPERIMENTER_THRESHOLD_MS         (default 60000)
 *   IDLE_EXPERIMENTER_COOLDOWN_MS          (default 600000 — 10 min between runs)
 *   IDLE_EXPERIMENTER_MAX_ROUNDS           (default 4 rewrite rounds per run)
 *   IDLE_EXPERIMENTER_LLM_TIMEOUT_MS       (default 300000)
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { AITranslator, setExperimenterTranslator, clearExperimenterTranslator } from '../ai/translator.js';
import { idleMonitor } from './idleMonitor.js';
import { updateStatus, getCurrentStatus } from '../socket/socketManager.js';
import { planProject, generatePlanFiles, runTscCheck, runRenderSmoke, runCliSmoke, repairLLMJson, emitCodegenProgress } from '../routes/codePlanner.js';
import { buildReferenceSection, MICRO_CATALOG, matchReference } from './microExperimenterReference.js';
import { loadBlueprints, blueprintToProject, findBlueprintFile } from '../blueprint/bible.js';
import { compareModulesToFiles } from '../blueprint/mockup.js';
import { FileGenerator, labelToFileName } from '../layers/fileGenerator.js';
import { runScaffoldExperiment as runScaffoldVariationSearch, } from './scaffoldExperiment.js';
import { isValidVariant } from './scaffoldVariation.js';
import { getLibraryContextForNodeType } from '../ai/libraryContext.js';
import { knowledgeStore } from '../knowledge/knowledgeStore.js';
import { runNonTsProjectGates, sanitizeGoModuleName } from '../sandbox/nonTsCompileGate.js';
import { languageFromPath } from '../utils/languageFromPath.js';
// ─── Paths ────────────────────────────────────────────────────────────────
const SVC_DIR = import.meta.dirname;
const BACKEND_DIR = path.resolve(SVC_DIR, '..', '..');
const PROJECT_ROOT = path.resolve(SVC_DIR, '..', '..', '..');
// Paths are overridable via env so tests can redirect all writes to a temp dir
// (and advanced operators can move the ideas DB). Falls back to project paths.
const DATA_DIR = process.env.IDLE_EXPERIMENTER_DATA_DIR || path.join(PROJECT_ROOT, 'data');
const IDEAS_FILE = path.join(DATA_DIR, 'micro-app-ideas.json');
const STATE_FILE = path.join(DATA_DIR, 'micro-experiment-state.json');
const EXPORTS_ROOT = process.env.IDLE_EXPERIMENTER_EXPORTS_DIR
    ? path.join(process.env.IDLE_EXPERIMENTER_EXPORTS_DIR)
    : path.join(BACKEND_DIR, 'exports', '__micro_experiments__');
const TRAINING_OUT = process.env.IDLE_EXPERIMENTER_TRAINING_DIR
    ? path.join(process.env.IDLE_EXPERIMENTER_TRAINING_DIR, 'micro-app-ideas.jsonl')
    : path.join(PROJECT_ROOT, 'training', 'dataset', 'micro-app-ideas.jsonl');
const TRAINING_UPLOADS = process.env.IDLE_EXPERIMENTER_UPLOADS_DIR
    ? path.join(process.env.IDLE_EXPERIMENTER_UPLOADS_DIR)
    : path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
const ORPO_OUT = process.env.IDLE_EXPERIMENTER_ORPO_DIR
    ? path.join(process.env.IDLE_EXPERIMENTER_ORPO_DIR, 'micro-orpo-pairs.jsonl')
    : path.join(PROJECT_ROOT, 'training', 'dataset', 'micro-orpo-pairs.jsonl');
// Scaffold self-improvement store: winning SCAFFOLD variants (mutated
// blueprints) land here. They are NOT auto-promoted into backend/blueprints/
// (loadBlueprints scans that dir recursively, so writing there would silently
// add a competing blueprint) — promotion is an explicit, reviewable step.
const SCAFFOLD_IDEAS_FILE = process.env.IDLE_EXPERIMENTER_DATA_DIR
    ? path.join(process.env.IDLE_EXPERIMENTER_DATA_DIR, 'scaffold-variants.json')
    : path.join(DATA_DIR, 'scaffold-variants.json');
function loadConfig() {
    const on = (process.env.IDLE_EXPERIMENTER_ENABLED || '').trim();
    return {
        enabled: on === '1' || on === 'true',
        thresholdMs: Number(process.env.IDLE_EXPERIMENTER_THRESHOLD_MS || 60000),
        cooldownMs: Number(process.env.IDLE_EXPERIMENTER_COOLDOWN_MS || 600000),
        maxRounds: Math.max(1, Number(process.env.IDLE_EXPERIMENTER_MAX_ROUNDS || 6)),
        llmTimeoutMs: Number(process.env.IDLE_EXPERIMENTER_LLM_TIMEOUT_MS || 300000),
        // Mini-model validator (judge) gate. When judgeModel+judgeBaseUrl are set,
        // a small/cheap model (e.g. qwen2.5-coder:0.5b on a local Ollama endpoint)
        // reviews each accepted build for completeness/universality/clarity before
        // it is stored. Without a dedicated endpoint it falls back to the primary.
        judgeEnabled: (process.env.IDLE_EXPERIMENTER_JUDGE || '').trim() === '1',
        judgeModel: process.env.IDLE_EXPERIMENTER_JUDGE_MODEL || 'qwen2.5-coder:0.5b',
        judgeBaseUrl: process.env.IDLE_EXPERIMENTER_JUDGE_BASE_URL || '',
        coderBaseUrl: process.env.IDLE_EXPERIMENTER_CODER_BASE_URL || 'http://127.0.0.1:11434/v1',
        coderModel: process.env.IDLE_EXPERIMENTER_CODER_MODEL || 'qwen2.5-coder:14b-gpu',
        scaffoldMaxVariants: Math.max(1, Number(process.env.IDLE_EXPERIMENTER_SCAFFOLD_MAX_VARIANTS || 4)),
    };
}
let ideasCache = [];
let stateCache = null;
function ensureDirs() {
    for (const d of [DATA_DIR, EXPORTS_ROOT, path.dirname(TRAINING_OUT), TRAINING_UPLOADS, path.dirname(ORPO_OUT), path.dirname(SCAFFOLD_IDEAS_FILE)]) {
        try {
            fs.mkdirSync(d, { recursive: true });
        }
        catch { /* best-effort */ }
    }
}
function loadIdeas() {
    if (ideasCache.length)
        return ideasCache;
    try {
        if (fs.existsSync(IDEAS_FILE))
            ideasCache = JSON.parse(fs.readFileSync(IDEAS_FILE, 'utf-8'));
    }
    catch {
        ideasCache = [];
    }
    return ideasCache;
}
function saveIdeas() {
    ensureDirs();
    fs.writeFileSync(IDEAS_FILE, JSON.stringify(ideasCache, null, 2), 'utf-8');
}
let scaffoldIdeasCache = [];
function loadScaffoldIdeas() {
    if (scaffoldIdeasCache.length)
        return scaffoldIdeasCache;
    try {
        if (fs.existsSync(SCAFFOLD_IDEAS_FILE)) {
            scaffoldIdeasCache = JSON.parse(fs.readFileSync(SCAFFOLD_IDEAS_FILE, 'utf-8'));
        }
    }
    catch {
        scaffoldIdeasCache = [];
    }
    return scaffoldIdeasCache;
}
function saveScaffoldIdeas() {
    ensureDirs();
    fs.writeFileSync(SCAFFOLD_IDEAS_FILE, JSON.stringify(scaffoldIdeasCache, null, 2), 'utf-8');
}
/**
 * Deterministic domain names offered to the split/leaf operators. The LLM is
 * not asked to name modules here — a small, generic vocabulary is enough for
 * the search to explore a split, and keeps this path LLM-free.
 */
function scaffoldNameProposals(bp) {
    const base = bp.app_type.replace(/[^a-z0-9]+/gi, '_').toLowerCase();
    return [`${base}_core`, `${base}_config`, `${base}_view`];
}
function loadState() {
    if (stateCache)
        return stateCache;
    const fresh = {
        purposeIndex: 0,
        lastRunAt: null,
        lastResult: null,
        ideasStoredTotal: 0,
        runsTotal: 0,
        lastExperimentKind: null,
    };
    try {
        if (fs.existsSync(STATE_FILE))
            stateCache = { ...fresh, ...JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8')) };
        else
            stateCache = fresh;
    }
    catch {
        stateCache = fresh;
    }
    return stateCache;
}
function saveState() {
    ensureDirs();
    try {
        fs.writeFileSync(STATE_FILE, JSON.stringify(loadState(), null, 2), 'utf-8');
    }
    catch { /* best-effort */ }
}
// ─── Micro-app catalog ─────────────────────────────────────────────────────
// The pool of micro-apps to build comes from microExperimenterReference.ts
// (MICRO_CATALOG — the same ten "mock-up" projects with worked before/after
// examples shown there). Each entry carries a VACA node type so the writer
// and rewriter pull the matching library context.
const translator = new AITranslator();
/** Next catalog entry to build, honoring an optional override by exact purpose. */
function entryFor(index, purposeOverride) {
    if (purposeOverride) {
        const hit = MICRO_CATALOG.find(e => e.purpose === purposeOverride) || MICRO_CATALOG.find(e => e.purpose.includes(purposeOverride));
        if (hit)
            return hit;
    }
    return MICRO_CATALOG[index % MICRO_CATALOG.length];
}
class MicroExperimenterService {
    running = false;
    timer = null;
    /** FileGenerator instance for scaffold experiments (its own AI translator). */
    scaffoldFileGen = new FileGenerator();
    getStatus() {
        const cfg = loadConfig();
        const st = loadState();
        return {
            enabled: cfg.enabled,
            config: {
                enabled: cfg.enabled,
                thresholdMs: cfg.thresholdMs,
                cooldownMs: cfg.cooldownMs,
                maxRounds: cfg.maxRounds,
                llmTimeoutMs: cfg.llmTimeoutMs,
                judgeEnabled: cfg.judgeEnabled,
                judgeModel: cfg.judgeModel,
                judgeBaseUrl: cfg.judgeBaseUrl,
                coderBaseUrl: cfg.coderBaseUrl,
                coderModel: cfg.coderModel,
                scaffoldMaxVariants: cfg.scaffoldMaxVariants,
            },
            idle: idleMonitor.isIdle(cfg.thresholdMs),
            lastActivityAt: idleMonitor.lastActivityAt,
            running: this.running,
            ideas: loadIdeas().length,
            lastRunAt: st.lastRunAt,
            lastResult: st.lastResult,
            runsTotal: st.runsTotal,
            ideasStoredTotal: st.ideasStoredTotal,
        };
    }
    /** Start the periodic poller (only runs experiments when idle + enabled). */
    start() {
        if (this.timer)
            return;
        if (!loadConfig().enabled) {
            console.log('[MicroExperimenter] DISABLED (IDLE_EXPERIMENTER_ENABLED is not 1) — idle self-improvement loop off');
            return;
        }
        console.log('[MicroExperimenter] Idle micro-app experimenter active');
        this.timer = setInterval(() => { void this.check(); }, 10_000);
        this.timer.unref?.();
        void this.check();
    }
    stop() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
    }
    /** Polling entry: only launch when idle, not already running, and past cooldown. */
    async check() {
        if (this.running)
            return;
        const cfg = loadConfig();
        if (!cfg.enabled)
            return;
        // Never race a user-generation: a single long build emits no activity for
        // minutes, so require the LLM to be locally idle too before experimenting.
        if (getCurrentStatus()?.isGenerating)
            return;
        const st = loadState();
        if (st.lastRunAt && Date.now() - new Date(st.lastRunAt).getTime() < cfg.cooldownMs)
            return;
        if (!idleMonitor.isIdle(cfg.thresholdMs))
            return;
        // Alternate code-improvement and scaffold-improvement so "enabled" actually
        // exercises the scaffold loop too (a scaffold experiment builds the
        // incumbent + every variant, so it takes the whole idle window).
        // IDLE_EXPERIMENTER_SCAFFOLD_EVERY=0 disables the scaffold side.
        const every = Math.max(0, Number(process.env.IDLE_EXPERIMENTER_SCAFFOLD_EVERY ?? 2));
        const prev = st.lastExperimentKind;
        const doScaffold = every > 0 && prev === 'micro';
        if (doScaffold) {
            try {
                await this.runScaffoldExperiment(false);
            }
            finally {
                st.lastExperimentKind = 'scaffold';
                saveState();
            }
        }
        else {
            try {
                await this.runExperiment();
            }
            finally {
                st.lastExperimentKind = 'micro';
                saveState();
            }
        }
    }
    /**
     * Run one full micro-app experiment cycle. When `force=true`, runs even if
     * not idle (used by the manual API trigger). `purposeOverride` selects a
     * specific catalog entry instead of rotating to the next one.
     */
    async runExperiment(force = false, purposeOverride) {
        if (this.running)
            return { ok: false, error: 'An experiment is already running', ...this.lastSummary() };
        const cfg = loadConfig();
        const st = loadState();
        if (!force) {
            if (st.lastRunAt && Date.now() - new Date(st.lastRunAt).getTime() < cfg.cooldownMs) {
                return { ok: false, error: 'In cooldown', ...this.lastSummary() };
            }
            if (!idleMonitor.isIdle(cfg.thresholdMs)) {
                return { ok: false, error: 'Not idle', ...this.lastSummary() };
            }
        }
        // Safety: even a forced/manual run yields to an in-flight user build.
        if (!force && getCurrentStatus()?.isGenerating) {
            return { ok: false, error: 'LLM is busy', ...this.lastSummary() };
        }
        this.running = true;
        updateStatus({ isGenerating: true, thinking: true, progress: 4, generationLayer: 1, projectName: 'micro-experiment' });
        // Route the whole micro-build (plan + baseline + rewrites) at the fast coder
        // so the self-improvement loop doesn't depend on the slow/weak primary LLM.
        setExperimenterTranslator(cfg.coderModel, cfg.coderBaseUrl);
        const entry = entryFor(st.purposeIndex, purposeOverride);
        try {
            const out = await this.cycle(entry, cfg);
            st.purposeIndex++;
            st.runsTotal++;
            st.lastRunAt = new Date().toISOString();
            st.lastResult = out.error ? `failed: ${out.error}` : `stored ${out.ideasStored} idea(s), ${out.rounds} round(s)`;
            st.ideasStoredTotal += out.ideasStored;
            saveState();
            return out;
        }
        catch (err) {
            console.error('[MicroExperimenter] experiment error:', err?.message || err);
            st.runsTotal++;
            st.lastRunAt = new Date().toISOString();
            st.lastResult = `failed: ${err?.message || err}`;
            saveState();
            return { ok: false, error: err?.message || String(err), ...this.lastSummary() };
        }
        finally {
            this.running = false;
            clearExperimenterTranslator();
            updateStatus({ isGenerating: false, thinking: false, progress: 100, generationLayer: 0 });
        }
    }
    /** Run the whole catalog once (the ten "mock-up" projects), collecting a 👍/👎 per iteration. */
    async runCatalog(force = false) {
        if (this.running)
            return [{ ok: false, error: 'An experiment is already running', purpose: '', rounds: 0, ideasStored: 0, baseline: null, best: null, iterations: [] }];
        const cfg = loadConfig();
        this.running = true;
        updateStatus({ isGenerating: true, thinking: true, progress: 2, generationLayer: 1, projectName: 'micro-experiment-catalog' });
        const results = [];
        try {
            for (const entry of MICRO_CATALOG) {
                if (!force) {
                    if (!idleMonitor.isIdle(cfg.thresholdMs)) {
                        results.push({ ok: false, error: 'Not idle', purpose: entry.purpose, rounds: 0, ideasStored: 0, baseline: null, best: null, nodeType: entry.nodeType, iterations: [] });
                        break;
                    }
                    if (getCurrentStatus()?.isGenerating) {
                        results.push({ ok: false, error: 'LLM is busy', purpose: entry.purpose, rounds: 0, ideasStored: 0, baseline: null, best: null, nodeType: entry.nodeType, iterations: [] });
                        break;
                    }
                }
                results.push(await this.cycle(entry, cfg));
            }
        }
        finally {
            const stored = results.reduce((s, r) => s + r.ideasStored, 0);
            const st = loadState();
            st.purposeIndex = 0;
            st.runsTotal += results.length;
            st.lastRunAt = new Date().toISOString();
            st.lastResult = `catalog run: ${results.length} app(s), stored ${stored} idea(s)`;
            st.ideasStoredTotal += stored;
            saveState();
            this.running = false;
            updateStatus({ isGenerating: false, thinking: false, progress: 100, generationLayer: 0 });
        }
        return results;
    }
    lastSummary() {
        return { purpose: '', rounds: 0, ideasStored: 0, baseline: null, best: null, iterations: [] };
    }
    /** Store an accepted "new idea" into the ideas database. */
    storeIdea(idea) {
        loadIdeas();
        const full = {
            ...idea,
            id: `idea_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            createdAt: new Date().toISOString(),
        };
        ideasCache.push(full);
        // Bounded store: each idea carries full source, so keep only the newest
        // MAX_IDEAS (rolling). Older ideas stay available until trimmed.
        const MAX_IDEAS = 200;
        if (ideasCache.length > MAX_IDEAS)
            ideasCache = ideasCache.slice(-MAX_IDEAS);
        saveIdeas();
        // Feed the discovered pattern back into VACA's library so future builds
        // can draw on it. Best-effort: the knowledge store's own quality gate is
        // the final judge, and a rejected pattern is simply not stored.
        try {
            knowledgeStore.addPattern({
                category: 'code_pattern',
                title: `Micro-app idea — ${idea.purpose}`,
                code: idea.files.map(f => `// FILE: ${f.path}\n${f.content}`).join('\n\n'),
                description: idea.design + (idea.lesson ? ` Lesson: ${idea.lesson}` : '') + ` Focus: ${idea.focus.join(', ')}`,
                tags: ['micro-app-idea', 'self-improve', ...idea.focus, idea.focus[0] || 'smaller'],
                nodeType: idea.nodeType || 'logic',
                language: dominantLanguage(idea.files),
                targetOS: 'linux',
                projectId: 'micro-experiment',
                success: true,
                qualityScore: 7.5,
            });
        }
        catch (err) {
            console.warn('[MicroExperimenter] knowledge-store pattern feedback failed (non-fatal):', err?.message || err);
        }
        console.log(`[MicroExperimenter] Stored idea "${idea.design}" — binary: ${idea.baselineMetrics.bytes}→${idea.metrics.bytes}B, ${idea.baselineMetrics.genMs}→${idea.metrics.genMs}ms`);
        return full;
    }
    getIdeas() {
        return [...loadIdeas()];
    }
    // ─── Scaffold self-improvement ──────────────────────────────────────────
    // VACA owns the scaffold, so the thing the idle loop should improve is the
    // SCAFFOLD: mutate a blueprint's checklist + wiring graph, build each
    // variant, and keep a variant only when its generated app scores higher on
    // the gates (adherence + tsc + smoke − drift − violations). The LLM still
    // only FILLS the files — it is never asked to design the architecture.
    getScaffoldIdeas() {
        return [...loadScaffoldIdeas()];
    }
    /**
     * Run ONE scaffold experiment: pick a blueprint, build today's scaffold
     * (incumbent) and every proposed mutation, then keep the best variant that
     * beats the incumbent by the margin. Writes the winner to the scaffold-idea
     * store (never auto-promoted into backend/blueprints/).
     */
    async runScaffoldExperiment(force = false, appType) {
        if (this.running)
            throw new Error('An experiment is already running');
        const cfg = loadConfig();
        const blueprints = loadBlueprints().filter((b) => (b.architecture_checklist || []).length >= 2);
        if (!blueprints.length) {
            return { ok: false, appType: appType || '', incumbent: null, variants: [], winner: null, adopted: false, error: 'No blueprints available' };
        }
        const st = loadState();
        const bp = appType ? (blueprints.find((b) => b.app_type === appType) || blueprints[0]) : blueprints[st.purposeIndex % blueprints.length];
        this.running = true;
        updateStatus({ isGenerating: true, thinking: true, progress: 4, generationLayer: 1, projectName: `scaffold-experiment:${bp.app_type}` });
        setExperimenterTranslator(cfg.coderModel, cfg.coderBaseUrl);
        const log = (m) => console.log(m);
        try {
            const result = await runScaffoldVariationSearch({
                blueprint: bp,
                build: (b) => this.buildScaffoldVariant(b),
                proposedNames: scaffoldNameProposals(bp),
                maxVariants: cfg.scaffoldMaxVariants,
                log,
            });
            if (result.adopted && result.winner) {
                this.storeScaffoldIdea(bp, result);
            }
            st.runsTotal++;
            st.lastRunAt = new Date().toISOString();
            st.lastResult = `scaffold ${bp.app_type}: ${result.adopted ? `adopted ${result.winner.op}` : 'kept incumbent'}`;
            saveState();
            return result;
        }
        finally {
            this.running = false;
            clearExperimenterTranslator();
            updateStatus({ isGenerating: false, thinking: false, progress: 100, generationLayer: 0 });
        }
    }
    /** Build one scaffold via the REAL canvas pipeline and measure it. */
    async buildScaffoldVariant(bp) {
        const project = blueprintToProject(bp, { goal: bp.description || bp.app_type });
        const gen = await this.scaffoldFileGen.generateFiles(project, false);
        const drift = compareModulesToFiles(bp.architecture_checklist, gen.files);
        return {
            // The RELATIVE on-disk path the export scaffold would use — NOT the bare
            // fileName. A flat list put every node in one directory, so the non-TS
            // gate reported "found packages X and Y in <dir>" for every multi-package
            // Go/Java/C# app and the scaffold loop could never score a PASSING build.
            files: gen.files.map((f) => ({ path: this.scaffoldRelPath(f), content: f.code, nodeLabel: f.nodeLabel })),
            tsCompileClean: gen.tsCompileClean,
            renderSmoke: gen.renderSmoke?.status ?? 'skipped',
            cliSmoke: gen.cliSmoke?.status ?? 'skipped',
            contractViolations: gen.contractViolations,
            driftMissing: drift.missing.length,
            driftUnexpected: drift.unexpected.length,
        };
    }
    /**
     * The path the export scaffold lays a generated file at: `src/<label>/<file>`
     * (or `apps/<app>/src/<label>/<file>` for a Tree-Mode app, `bridge/<file>` for
     * an integration module). Shared by both self-improvement loops so the
     * non-TS compile gate sees the real per-directory package structure.
     */
    scaffoldRelPath(f) {
        if (f.isBridge)
            return `bridge/${f.fileName}`;
        const prefix = f.appDir ? `${f.appDir}/` : '';
        return `${prefix}src/${labelToFileName(f.nodeLabel)}/${f.fileName}`;
    }
    /**
     * PROMOTE a reviewed scaffold variant into the LIVE blueprints: overwrite the
     * source file that defines `appType` with the variant's checklist + wiring.
     * Explicit and reversible — the original is backed up first, and this is the
     * ONLY path that mutates backend/blueprints/ (the loop never auto-promotes).
     *
     * Only the scaffold fields are taken from the variant: description / keywords /
     * target_stack stay from the on-disk blueprint, so promotion changes the
     * architecture, not the blueprint's identity.
     */
    promoteScaffoldIdea(id) {
        const idea = loadScaffoldIdeas().find((i) => i.id === id);
        if (!idea)
            return { ok: false, error: `No scaffold idea '${id}'` };
        const clean = isValidVariant(idea.blueprint);
        if (!clean)
            return { ok: false, error: 'Variant is not a valid blueprint (referential integrity)' };
        const target = findBlueprintFile(idea.appType);
        if (!target)
            return { ok: false, error: `No live blueprint file defines app_type '${idea.appType}'` };
        let onDisk;
        try {
            onDisk = JSON.parse(fs.readFileSync(target, 'utf-8'));
        }
        catch (err) {
            return { ok: false, error: `Cannot read ${target}: ${err?.message || err}` };
        }
        // Back up the original before mutating it.
        const backupDir = path.join(DATA_DIR, 'blueprint-backups');
        try {
            fs.mkdirSync(backupDir, { recursive: true });
        }
        catch { /* best-effort */ }
        const backup = path.join(backupDir, `${path.basename(target)}.${Date.now()}`);
        try {
            fs.copyFileSync(target, backup);
        }
        catch (err) {
            return { ok: false, error: `Cannot back up ${target}: ${err?.message || err}` };
        }
        const promoted = {
            ...onDisk,
            architecture_checklist: [...idea.blueprint.architecture_checklist],
            wiring_graph: idea.blueprint.wiring_graph.map((w) => ({ ...w })),
        };
        try {
            fs.writeFileSync(target, JSON.stringify(promoted, null, 2) + '\n', 'utf-8');
        }
        catch (err) {
            return { ok: false, error: `Cannot write ${target}: ${err?.message || err}` };
        }
        idea.promoted = true;
        saveScaffoldIdeas();
        console.log(`[MicroExperimenter] PROMOTED scaffold idea ${id} into ${target} (backup: ${backup})`);
        return { ok: true, file: target, backup };
    }
    /** Persist a winning scaffold variant (bounded, newest-first). */
    storeScaffoldIdea(base, result) {
        const ideas = loadScaffoldIdeas();
        const w = result.winner;
        const full = {
            id: `scaffold_${w.op}_${base.app_type}_${Date.now()}`,
            appType: base.app_type,
            op: w.op,
            rationale: w.rationale,
            score: w.score,
            incumbentScore: result.incumbent.score,
            metrics: w.metrics,
            blueprint: w.blueprint,
            createdAt: new Date().toISOString(),
            promoted: false,
        };
        ideas.push(full);
        const MAX = 100;
        scaffoldIdeasCache = ideas.length > MAX ? ideas.slice(-MAX) : ideas;
        saveScaffoldIdeas();
        console.log(`[MicroExperimenter] Stored scaffold idea "${full.rationale}" score ${full.score} > ${full.incumbentScore}`);
        return full;
    }
    /**
     * Convert the ideas database into training JSONL. Writes to
     * training/dataset/micro-app-ideas.jsonl and copies into the Training Studio
     * uploads dir (mirrors the auto-learn flush pattern). Returns paths + count.
     */
    exportTrainingData() {
        const ideas = loadIdeas();
        if (!ideas.length)
            return { error: 'No stored ideas to export' };
        ensureDirs();
        const ts = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `micro-app-ideas-${ts}.jsonl`;
        const outPath = path.join(path.dirname(TRAINING_OUT), filename);
        const uploadPath = path.join(TRAINING_UPLOADS, filename);
        const lines = ideas.map(idea => JSON.stringify({
            text: ideaToTrainingText(idea),
            title: `Micro-app idea — ${idea.purpose}`,
            language: dominantLanguage(idea.files),
            nodeType: 'micro_app_idea',
            tags: ['micro-app-idea', 'self-improve', 'autonomous', ...idea.focus],
            source: 'micro-app-experimenter',
            purpose: idea.purpose,
            design: idea.design,
            metrics: idea.metrics,
            baselineMetrics: idea.baselineMetrics,
            timestamp: idea.createdAt,
        }));
        fs.writeFileSync(outPath, lines.join('\n') + '\n', 'utf-8');
        try {
            fs.copyFileSync(outPath, uploadPath);
        }
        catch { /* uploads may not exist */ }
        console.log(`[MicroExperimenter] Exported ${lines.length} idea(s) → ${outPath}`);
        return { file: outPath, upload: uploadPath, count: lines.length };
    }
    /**
     * Build ORPO preference pairs from stored ideas: for each idea with a saved
     * baseline, choose the improved code (chosen) over the from-the-ground-up
     * baseline (rejected). Appends to training/dataset/micro-orpo-pairs.jsonl
     * (dedup by source) and syncs a copy into the Training Studio uploads dir.
     */
    exportOrpoPairs() {
        const ideas = loadIdeas();
        const rows = ideas.filter(i => i.baselineFiles && i.baselineFiles.length).map(i => ({
            instruction: orpoInstruction(i.purpose),
            chosen: filesBundle(i.files),
            rejected: filesBundle(i.baselineFiles),
            source: `micro-orpo-db:${i.id}`,
        }));
        if (!rows.length)
            return { error: 'No stored ideas with a baseline copy to build pairs from' };
        this.appendOrpoPairs(rows);
        return {
            file: ORPO_OUT,
            upload: path.join(TRAINING_UPLOADS, 'micro-orpo-pairs.jsonl'),
            count: rows.length,
        };
    }
    /** Append (source-deduped) {instruction, chosen, rejected} rows to the ORPO file. */
    appendOrpoPairs(rows) {
        if (!rows.length)
            return;
        ensureDirs();
        const existing = new Set();
        try {
            if (fs.existsSync(ORPO_OUT)) {
                for (const l of fs.readFileSync(ORPO_OUT, 'utf-8').split('\n')) {
                    if (!l.trim())
                        continue;
                    try {
                        const s = JSON.parse(l).source;
                        if (s)
                            existing.add(s);
                    }
                    catch { /* skip */ }
                }
            }
        }
        catch { /* best-effort */ }
        const fresh = rows.filter(r => !existing.has(r.source));
        if (!fresh.length)
            return;
        const lines = fresh.map(r => JSON.stringify(r)).join('\n');
        fs.appendFileSync(ORPO_OUT, lines + '\n', 'utf-8');
        try {
            fs.copyFileSync(ORPO_OUT, path.join(TRAINING_UPLOADS, 'micro-orpo-pairs.jsonl'));
        }
        catch { /* uploads may not exist */ }
        console.log(`[MicroExperimenter] Wrote ${fresh.length} ORPO pair(s) → ${ORPO_OUT}`);
    }
    // ─── Core experiment loop ───────────────────────────────────────────────
    async cycle(entry, cfg) {
        const purpose = entry.purpose;
        const nodeType = entry.nodeType;
        emitCodegenProgress({ phase: 'thinking', percent: 2, message: `[micro-experiment] building "${purpose}"…` });
        const planned = await planProject(purpose, 'small');
        if (!planned || !planned.plan.files || !planned.plan.files.length) {
            return { ok: false, error: 'Plan failed', purpose, rounds: 0, ideasStored: 0, baseline: null, best: null };
        }
        const plannedFiles = planned.plan.files;
        // Round 0 — baseline from the ground up, fully verified by generatePlanFiles.
        const t0 = Date.now();
        const gen = await generatePlanFiles(purpose, planned.plan, undefined, cfg.llmTimeoutMs, undefined, 1, planned.intent);
        const baselineMs = Date.now() - t0;
        if (!gen || !gen.files || !gen.files.length) {
            return { ok: false, error: 'Baseline generation failed', purpose, rounds: 0, ideasStored: 0, baseline: null, best: null };
        }
        // Normalize the one-shot into our verified working set.
        const baseFiles = normalizeForRewrite(gen.files, plannedFiles.map(f => f.path));
        const baselineVerdict = await this.verify(baseFiles, cfg);
        if (!baselineVerdict.accepted) {
            const gateNote = baselineVerdict.nonTsGates.find((g) => !g.clean)?.language;
            emitCodegenProgress({ phase: 'done', percent: 100, message: `[micro-experiment] baseline not clean (tsc=${baselineVerdict.tscStatus}, render=${baselineVerdict.render.status}, cli=${baselineVerdict.cli.status}${gateNote ? `, gate=${gateNote}` : ''}) — aborting` });
            return { ok: false, error: 'Baseline did not pass gates', purpose, rounds: 0, ideasStored: 0, baseline: null, best: null };
        }
        const baseline = { ...measure(baseFiles), genMs: baselineMs };
        // Write baseline to a stable export dir so the winner / training data point
        // at real files on disk.
        const rootExportDir = this.exportDirFor(purpose, 'baseline');
        this.writeFiles(rootExportDir, baseFiles);
        console.log(`[MicroExperimenter] baseline "${purpose}": ${baseline.bytes}B, ${baseline.lines}L, ${baseline.genMs}ms — starting ${cfg.maxRounds} rewrite round(s)`);
        // Self-rewrite iteration.
        let current = baseFiles;
        let bestScore = composite(baseline, baseline);
        let ideasStored = 0;
        let best = null;
        let rounds = 0;
        const iterations = [];
        // User rule: DELETE failed attempts, keep only winners, and keep iterating
        // until the app can't improve anymore, THEN move to the next build. Plateau
        // is detected as STALL_LIMIT consecutive non-improving rounds; maxRounds is
        // only a hard safety cap.
        let stall = 0;
        const STALL_LIMIT = 2;
        const cycleId = Date.now(); // unique per run so ORPO pair sources never collide
        for (let r = 1; r <= cfg.maxRounds; r++) {
            // Cooperate with a returning user: abort between rounds if they came back.
            if (!idleMonitor.isIdle(cfg.thresholdMs)) {
                emitCodegenProgress({ phase: 'done', percent: 100, message: '[micro-experiment] user returned — stopping experiment' });
                break;
            }
            emitCodegenProgress({ phase: 'generating', percent: 20 + Math.round((r / cfg.maxRounds) * 60), message: `[micro-experiment] rewrite round ${r}/${cfg.maxRounds}` });
            const rt0 = Date.now();
            const rewritten = await this.tryRewrite(purpose, nodeType, current, cfg);
            const genMs = Date.now() - rt0;
            if (!rewritten) {
                iterations.push({ round: r, accepted: false, improved: false, verdict: 'thumbs-down', note: 'rewrite not parseable' });
                if (++stall >= STALL_LIMIT)
                    break; // gave up / nothing parseable — can't improve further
                continue;
            }
            const attemptFiles = rewriteToCurrent(rewritten, current);
            if (!attemptFiles || attemptFiles.length === 0) {
                iterations.push({ round: r, accepted: false, improved: false, verdict: 'thumbs-down', note: 'rewrite produced no usable files' });
                if (++stall >= STALL_LIMIT)
                    break;
                continue;
            }
            const attemptDir = this.exportDirFor(purpose, `round-${r}`);
            this.writeFiles(attemptDir, attemptFiles);
            const gate = await this.verify(attemptFiles, cfg);
            if (!gate.accepted) {
                const gateNote = gate.nonTsGates.find((g) => !g.clean)?.language;
                console.log(`[MicroExperimenter] round ${r}: 👎 rejected (tsc=${gate.tscStatus}, render=${gate.render.status}, cli=${gate.cli.status}${gateNote ? `, gate=${gateNote}` : ''}) — deleting, keeping previous`);
                iterations.push({ round: r, accepted: false, improved: false, verdict: 'thumbs-down', note: `failed gates: tsc=${gate.tscStatus}, render=${gate.render.status}, cli=${gate.cli.status}${gateNote ? `, gate=${gateNote}` : ''}` });
                // ORPO pair: the working best (chosen) over this broken attempt (rejected).
                this.appendOrpoPairs([{ instruction: orpoInstruction(purpose), chosen: filesBundle(current), rejected: filesBundle(attemptFiles), source: `micro-orpo:${purpose}:${cycleId}:r${r}` }]);
                this.cleanupDir(attemptDir); // delete the failed attempt
                if (++stall >= STALL_LIMIT)
                    break;
                continue;
            }
            const metrics = { ...measure(attemptFiles), genMs };
            const score = composite(baseline, metrics);
            const improved = (score < bestScore) && gate.accepted;
            // Optional mini-model judge gate: runs on improved candidates BEFORE they
            // are stored, so a build that compiles but is a stub / hardcoded / cryptic
            // is caught by a reviewer model rather than learned from.
            let judgePass = true;
            let judgeNote = null;
            if (improved && cfg.judgeEnabled) {
                const j = await this.judgeBuild(purpose, nodeType, attemptFiles, cfg);
                judgePass = j.pass;
                judgeNote = j.reason;
            }
            const finalPass = improved && judgePass;
            console.log(`[MicroExperimenter] round ${r}: ${improved ? '👍 improved' : '👎 not improved'}${judgePass ? '' : ' BUT 👎 judge rejected'} ${baseline.bytes}→${metrics.bytes}B, ${baseline.genMs}→${genMs}ms (composite ${bestScore.toFixed(3)}→${score.toFixed(3)})`);
            iterations.push({
                round: r, accepted: true, improved: finalPass,
                verdict: finalPass ? 'thumbs-up' : 'thumbs-down',
                score,
                note: `${baseline.bytes}→${metrics.bytes}B, ${baseline.genMs}→${genMs}ms${judgeNote && !judgePass ? ` — judge: ${judgeNote}` : ''}`,
            });
            rounds = r;
            if (!finalPass) {
                // Improvement but rejected by judge (or a gate/score no-improvement).
                if (improved)
                    console.log(`[MicroExperimenter]   judge rejected (${judgeNote}) — deleting, not storing`);
                this.appendOrpoPairs([{ instruction: orpoInstruction(purpose), chosen: filesBundle(current), rejected: filesBundle(attemptFiles), source: `micro-orpo:${purpose}:${cycleId}:r${r}` }]);
                this.cleanupDir(attemptDir); // failure or judge-rejection → delete the attempt
                if (++stall >= STALL_LIMIT)
                    break; // plateau reached — done with this app
                continue;
            }
            stall = 0; // real progress — keep iterating on this app
            // ORPO pair: the improved code (chosen) over the previous best (rejected).
            this.appendOrpoPairs([{ instruction: orpoInstruction(purpose), chosen: filesBundle(attemptFiles), rejected: filesBundle(current), source: `micro-orpo:${purpose}:${cycleId}:r${r}` }]);
            current = attemptFiles;
            bestScore = score;
            best = { files: attemptFiles, metrics, score };
            // Store every accepted improvement as a new "idea" (👍) — the working
            // copy lives in the DB (and its export dir is kept on disk).
            const focus = this.detectFocus(baseline, metrics);
            this.storeIdea({
                purpose,
                design: `${purpose} — improved design`,
                focus,
                metrics,
                baselineMetrics: baseline,
                composite: score,
                exportsDir: attemptDir,
                files: attemptFiles,
                nodeType,
                verdict: 'thumbs-up',
                baselineFiles: baseFiles,
            });
            ideasStored++;
        }
        // Attempt a short design summary for the winning rewrite (best effort).
        let design = `${purpose} — iteratively minimized`;
        if (best && ideasStored > 0) {
            design = await this.describeDesign(purpose, nodeType, best.files, baseline, cfg) || design;
            // Refresh the stored idea (the most recent cache entry is the winner).
            this.updateLastIdeaDesign(design);
            this.updateLastIdeaLesson(design);
        }
        emitCodegenProgress({
            phase: 'done', percent: 100,
            message: `[micro-experiment] done: ${rounds} round(s), stored ${ideasStored} idea(s)`,
        });
        return {
            ok: true,
            purpose, rounds, ideasStored,
            baseline,
            best: best ? { metrics: best.metrics, score: best.score } : null,
            nodeType,
            iterations,
            error: undefined,
        };
    }
    /** Ask the LLM to rewrite the current app smaller/faster/more-universal. */
    async tryRewrite(purpose, nodeType, files, cfg) {
        const bundle = filesToJson(files);
        const focuses = 'SMALLER (fewer bytes/lines), FASTER (simpler/fewer operations), and more UNIVERSAL (standard, reusable approach that applies to any app of this kind)';
        const reference = buildReferenceSection(purpose, nodeType);
        const library = clip(getLibraryContextForNodeType(nodeType, dominantLanguage(files)), 900);
        const prompt = `You are rewriting an existing WORKING app to be better. The app's purpose: ${purpose}\n\n${reference ? `${reference}\n\n` : ''}${library ? `━━━ VACA LIBRARY CONTEXT (consult for universal, idiomatic shapes) ━━━\n${library}\n\n` : ''}Current files (JSON object mapping path -> content):\n${bundle}\n\nRewrite the CODE to be ${focuses} while keeping the EXACT same functionality. Rules:\n- Emulate the LESSON in the reference above — generalize the pattern to THIS app.\n- Keep the SAME set of file paths. Do NOT add or rename files.\n- Remove comments/boilerplate, merge logic, prefer the fewest statements.\n- Use a generic, standard approach (no hardcoded app-specific one-off tricks that wouldn't carry over to a similar app).\n- The result must still work when run exactly as before.\n\nReturn ONLY valid JSON — either an object mapping each "path" -> "new content", or {"files": [{"path","content"}]}. No markdown, no explanations.`;
        try {
            let raw;
            try {
                raw = await this.coderViaEndpoint(cfg, prompt);
            }
            catch (coderErr) {
                console.warn('[MicroExperimenter] fast-coder endpoint failed, falling back to primary LLM:', coderErr?.message || coderErr);
                raw = await translator.reason(prompt, REWRITE_SYSTEM, { maxTokens: 8192, timeoutMs: cfg.llmTimeoutMs, temperature: 0.3 });
            }
            return rewriteToCurrent(parseRewriteJson(raw), files);
        }
        catch (err) {
            console.warn('[MicroExperimenter] rewrite LLM call failed:', err?.message || err);
            return null;
        }
    }
    /** Talk to a dedicated fast coder (Ollama/DSpark) directly for the rewrite
     *  loop — mirrors judgeViaEndpoint but for code generation. Keeps the slow
     *  primary LLM out of the micro-build self-improvement path. */
    async coderViaEndpoint(cfg, user) {
        const base = (cfg.coderBaseUrl || '').replace(/\/+$/, '');
        if (!base)
            throw new Error('no coder endpoint configured');
        const res = await fetch(`${base}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: cfg.coderModel,
                messages: [
                    { role: 'system', content: REWRITE_SYSTEM },
                    { role: 'user', content: user },
                ],
                max_tokens: 8192,
                temperature: 0.3,
                stream: false,
            }),
            signal: AbortSignal.timeout(cfg.llmTimeoutMs),
        });
        if (!res.ok)
            throw new Error(`coder endpoint HTTP ${res.status}`);
        const body = await res.json();
        return body?.choices?.[0]?.message?.content || '';
    }
    /** One small LLM call to summarize the final design approach (best effort). */
    async describeDesign(purpose, nodeType, files, baseline, cfg) {
        try {
            const ref = matchReference(purpose, nodeType);
            const refText = ref ? ` The reference build's lesson was: ${ref.lesson}` : '';
            const filesText = filesToJson(files).slice(0, 6000);
            const prompt = `Here is the FINAL, optimized code for an app. Purpose: ${purpose}.${refText}\n\nFiles:\n${filesText}\n\nIn ONE to TWO sentences, describe the DESIGN APPROACH that makes this code small, fast, and universal enough to replace an older, larger implementation. Be concrete about the techniques (e.g. state shape, single source of truth, no dependencies, simple algorithms). This becomes the LEARNED PATTERN stored back into VACA's library.`;
            const raw = await translator.reason(prompt, REWRITE_SYSTEM, { maxTokens: 256, timeoutMs: 60000, temperature: 0.3 });
            const t = (raw || '').trim().replace(/[\n\r]+/g, ' ').replace(/^["']+|["']+$/g, '');
            return t.length > 8 ? t.slice(0, 400) : null;
        }
        catch {
            return null;
        }
    }
    updateLastIdeaDesign(design) {
        const idx = ideasCache.length - 1;
        if (idx >= 0 && ideasCache[idx]) {
            ideasCache[idx].design = design;
            saveIdeas();
        }
    }
    updateLastIdeaLesson(design) {
        const idx = ideasCache.length - 1;
        if (idx >= 0 && ideasCache[idx]) {
            ideasCache[idx].lesson = design;
            saveIdeas();
        }
    }
    /**
     * Verify a file set against the SAME gates generatePlanFiles uses: tsc +
     * render smoke (headless Chrome) + CLI smoke. Requires the files already on
     * disk (they are written by the caller). Accepted = tsc not-errors, and
     * neither smoke verdict is a hard FAILED.
     */
    async verify(files, cfg) {
        // The caller writes its own export dir, but verification is done on a
        // transient copy so a rejected rewrite never leaves partial artifacts.
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'micro-exp-verify-'));
        this.writeFiles(dir, files);
        let tscStatus = 'skipped';
        let tscErrors = 0;
        try {
            const tsc = await runTscCheck(dir, files);
            tscStatus = tsc.status;
            tscErrors = tsc.errors.length;
        }
        catch {
            tscStatus = 'unavailable';
        }
        // Non-TS compile gates (go/rust/cpp/java/…). Without this a non-TS micro-app
        // is accepted on tsc:'skipped' + smoke:'skipped' with NO verification at
        // all — the loop would then "learn" broken output. Same gate the canvas and
        // chat paths run before they trust a build.
        let nonTsGates = [];
        try {
            nonTsGates = await runNonTsProjectGates(files.map((f) => ({ relPath: f.path, code: f.content })), sanitizeGoModuleName(`${dominantLanguage(files)} micro app`));
        }
        catch (err) {
            console.warn('[MicroExperimenter] non-TS gate failed (non-fatal):', err?.message || err);
        }
        const render = await runRenderSmoke(dir, files, 35_000).catch(() => ({ status: 'unavailable', errors: [], detail: 'probe error' }));
        const cli = await runCliSmoke(dir, files, 45_000).catch(() => ({ status: 'unavailable', errors: [], detail: 'probe error' }));
        try {
            fs.rmSync(dir, { recursive: true, force: true });
        }
        catch { /* best-effort */ }
        const tscOk = tscStatus === 'clean' || tscStatus === 'skipped';
        const failedGate = nonTsGates.find((g) => !g.clean);
        const accepted = tscOk && !failedGate && render.status !== 'failed' && cli.status !== 'failed';
        return { accepted, tscStatus, tscErrors, render, cli, nonTsGates };
    }
    exportDirFor(purpose, label) {
        const slug = purpose.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'app';
        const dir = path.join(EXPORTS_ROOT, `${slug}-${Date.now()}-${label}`);
        fs.mkdirSync(dir, { recursive: true });
        return dir;
    }
    writeFiles(dir, files) {
        for (const f of files) {
            const abs = safeJoinIn(dir, f.path);
            fs.mkdirSync(path.dirname(abs), { recursive: true });
            fs.writeFileSync(abs, f.content, 'utf-8');
        }
    }
    detectFocus(base, m) {
        const focus = [];
        if (m.bytes < base.bytes)
            focus.push('smaller');
        if (m.genMs < base.genMs)
            focus.push('faster');
        if (m.files < base.files)
            focus.push('universal'); // simpler/fewer-file structure is more portable
        if (!focus.length)
            focus.push('smaller');
        return focus;
    }
    async judgeBuild(purpose, nodeType, files, cfg) {
        const bundle = filesBundle(files);
        const user = `App purpose: ${purpose} (node type: ${nodeType}). It passed compilation and smoke tests.\n\nCode:\n${bundle}\n\nReview and return ONLY JSON: {"pass": true|false, "reason": "one sentence"}.`;
        let raw;
        try {
            if (cfg.judgeBaseUrl && cfg.judgeModel) {
                raw = await this.judgeViaEndpoint(cfg, user);
            }
            else {
                raw = await translator.reason(user, JUDGE_SYSTEM, { maxTokens: 200, timeoutMs: cfg.llmTimeoutMs, temperature: 0.2 });
            }
        }
        catch (err) {
            // A flaky judge must never block learning permanently — treat as pass.
            console.warn('[MicroExperimenter] judge call failed — treating as pass:', err?.message || err);
            return { pass: true, reason: 'judge unavailable' };
        }
        const verdict = parseJudgeVerdict(raw);
        if (!verdict) {
            // Unparseable judge output — don't reject on garbage.
            return { pass: true, reason: 'judge output unparseable — treated as pass' };
        }
        return verdict;
    }
    /** Talk to a dedicated small OpenAI-compatible model (Ollama/DSpark) directly. */
    async judgeViaEndpoint(cfg, user) {
        const base = cfg.judgeBaseUrl.replace(/\/+$/, '');
        const res = await fetch(`${base}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: cfg.judgeModel,
                messages: [
                    { role: 'system', content: JUDGE_SYSTEM },
                    { role: 'user', content: user },
                ],
                max_tokens: 200,
                stream: false,
            }),
            signal: AbortSignal.timeout(cfg.llmTimeoutMs),
        });
        if (!res.ok)
            throw new Error(`judge endpoint HTTP ${res.status}`);
        const body = await res.json();
        return body?.choices?.[0]?.message?.content || '';
    }
    cleanupDir(dir) {
        try {
            fs.rmSync(dir, { recursive: true, force: true });
        }
        catch { /* best-effort */ }
    }
}
/** Balanced score (lower = better): 50% size, 50% generation speed, both vs baseline. */
export function composite(baseline, m) {
    const bytes = baseline.bytes > 0 ? m.bytes / baseline.bytes : 1;
    const speed = baseline.genMs > 0 ? m.genMs / baseline.genMs : 1;
    return 0.5 * bytes + 0.5 * speed;
}
export function measure(files) {
    const bytes = files.reduce((s, f) => s + Buffer.byteLength(f.content || '', 'utf8'), 0);
    const lines = files.reduce((s, f) => s + (f.content || '').split('\n').filter(l => l.trim().length > 0).length, 0);
    return { bytes, lines, files: files.length, genMs: 0 };
}
/** Keep only the files the plan declared, mapped to the generated set. */
export function normalizeForRewrite(gen, plannedPaths) {
    const planned = new Set(plannedPaths.map(normalizePath));
    // Include every generated file that maps to a planned path; also keep any
    // non-code artifact (index.html etc.) that the plan produced.
    return gen.filter(f => planned.has(normalizePath(f.path)) || /\.(html?|css|json)$/i.test(f.path));
}
export function rewriteToCurrent(rewritten, current) {
    if (!rewritten || rewritten.length === 0)
        return null;
    const allowed = new Set(current.map(f => f.path));
    // Constrain the rewrite to the SAME file set (never grow the app).
    const kept = rewritten.filter(f => allowed.has(f.path));
    // Ensure we still have every original file — missing ones fall back to the
    // previous version so functionality can't silently disappear.
    const byPath = new Map(kept.map(f => [f.path, f]));
    const merged = current.map(f => byPath.get(f.path) || f);
    return merged;
}
export function parseRewriteJson(text) {
    if (!text)
        return null;
    const cleaned = text.replace(/^```(?:json)?\s*|```$/g, '').trim();
    const tryParse = (s) => {
        try {
            return JSON.parse(s);
        }
        catch {
            try {
                return JSON.parse(repairLLMJson(s));
            }
            catch {
                return null;
            }
        }
    };
    let obj = tryParse(cleaned);
    if (obj === null) {
        const start = cleaned.indexOf('{');
        if (start !== -1) {
            let depth = 0, inStr = false, esc = false;
            for (let i = start; i < cleaned.length; i++) {
                const ch = cleaned[i];
                if (inStr) {
                    if (esc)
                        esc = false;
                    else if (ch === '\\')
                        esc = true;
                    else if (ch === '"')
                        inStr = false;
                    continue;
                }
                if (ch === '"')
                    inStr = true;
                else if (ch === '{')
                    depth++;
                else if (ch === '}') {
                    depth--;
                    if (depth === 0) {
                        const p = tryParse(cleaned.slice(start, i + 1));
                        if (p) {
                            obj = p;
                            break;
                        }
                    }
                }
            }
        }
    }
    if (!obj || typeof obj !== 'object')
        return null;
    const rec = obj;
    // { "files": [ { path, content } ] }
    if (Array.isArray(rec.files)) {
        const files = rec.files
            .filter((f) => !!f && typeof f === 'object')
            .map(f => ({ path: String(f.path || ''), content: String(f.content ?? '') }))
            .filter(f => f.path && f.content);
        if (files.length)
            return files;
    }
    // { "<path>": "<content>" } — also tolerate a nested { files } re-wrap.
    const inner = rec.files && typeof rec.files === 'object' ? rec.files : rec;
    const out = [];
    for (const [k, v] of Object.entries(inner)) {
        if (typeof v === 'string' && v.length > 0)
            out.push({ path: k, content: v });
    }
    return out.length ? out : null;
}
function filesToJson(files) {
    const obj = {};
    for (const f of files)
        obj[f.path] = f.content;
    return JSON.stringify(obj);
}
export function ideaToTrainingText(idea) {
    const files = idea.files.map(f => `// FILE: ${f.path}\n${f.content}`).join('\n\n');
    return `App purpose: ${idea.purpose}\nDesign: ${idea.design}\n\n${files}`;
}
/** A multi-file bundle rendered as `// FILE: path\n content` — the shape used
 * for both sides of an ORPO pair (chosen/rejected) so the model sees file paths. */
function filesBundle(files) {
    return files.map(f => `// FILE: ${f.path}\n${f.content}`).join('\n\n');
}
/** The shared rewrite instruction for an ORPO pair (same for both sides). */
function orpoInstruction(purpose) {
    return `Rewrite the WORKING app "${purpose}" to be SMALLER (fewer bytes/lines), FASTER, and more UNIVERSAL (a generic, reusable design approach) while keeping identical functionality and the same file structure. Keep the same file paths.`;
}
/** Truncate an injected context string so it never starves the response budget. */
function clip(s, max) {
    if (!s)
        return '';
    return s.length > max ? s.slice(0, max) + '\n…(truncated)' : s;
}
export function dominantLanguage(files) {
    const counts = new Map();
    for (const f of files) {
        // The ONE path→language mapping (shared with the learning engine and the
        // scaffold scorer). The old extension switch collapsed every language that
        // was not ts/js/html to 'typescript', so a Rust/C++/Go/… micro-app was
        // stored and looked up as TypeScript.
        const lang = languageFromPath(f.path);
        if (lang)
            counts.set(lang, (counts.get(lang) || 0) + 1);
    }
    let best = 'typescript';
    let bestN = 0;
    for (const [lang, n] of counts)
        if (n > bestN) {
            bestN = n;
            best = lang;
        }
    return best;
}
function normalizePath(p) {
    return (p || '').replace(/^\.\//, '').replace(/\\/g, '/');
}
function safeJoinIn(dir, rel) {
    const normalized = path.normalize(rel || 'file.txt').replace(/^(\.\.(\/|\\|$))+/, '');
    const full = path.resolve(dir, normalized);
    return full.startsWith(dir + path.sep) ? full : path.join(dir, 'file.txt');
}
// ─── System prompts ───────────────────────────────────────────────────────
const REWRITE_SYSTEM = `You are VACA's autonomous self-improvement agent. You rewrite already-working generated apps to be SMALLER (fewer bytes/lines), FASTER, and more UNIVERSAL (a generic, reusable design that can replace an older, larger implementation for other apps of the same kind). You NEVER break working functionality. You return only valid JSON when asked for JSON.`;
const JUDGE_SYSTEM = `You are a strict, honest senior code reviewer (the JUDGE) validating a generated micro-app before it is accepted into VACA's code library. The app already passed compilation and automated smoke tests. Evaluate the CODE against:
1. Completeness — does it actually implement the full purpose? Flag stubs, TODO/placeholder bodies, or hardcoded single-case output presented as real logic.
2. Correctness/wiring — are imports, calls, and state internally consistent so the described behavior is actually covered?
3. Universality — does it use a generic, reusable design rather than an app-specific one-off trick that would not carry to a similar app?
4. Clarity — is it reasonably readable, not needlessly cryptic?
Return ONLY valid JSON: {"pass": true|false, "reason": "<one short sentence>"}. "pass": false means the build should NOT be learned from or stored.`;
/** Parse a judge's {pass, reason} reply (JSON or a bare `pass:true/false`). */
export function parseJudgeVerdict(raw) {
    if (!raw)
        return null;
    const cleaned = raw.replace(/^```(?:json)?\s*|```$/g, '').trim();
    try {
        const obj = JSON.parse(cleaned);
        if (typeof obj === 'object' && obj !== null && typeof obj.pass === 'boolean') {
            return { pass: obj.pass, reason: typeof obj.reason === 'string' ? obj.reason : '' };
        }
    }
    catch {
        /* fall through to regex */
    }
    try {
        const repaired = JSON.parse(repairLLMJson(cleaned));
        if (repaired && typeof repaired.pass === 'boolean') {
            return { pass: repaired.pass, reason: typeof repaired.reason === 'string' ? repaired.reason : '' };
        }
    }
    catch { /* fall through */ }
    const m = /"?pass"?\s*[:＝]\s*(true|false)/i.exec(cleaned);
    if (m) {
        const reason = /"reason"\s*[:＝]\s*"([^"]*)"/i.exec(cleaned)?.[1] || '';
        return { pass: m[1].toLowerCase() === 'true', reason };
    }
    return null;
}
// ─── Singleton Export ─────────────────────────────────────────────────────
export const microExperimenter = new MicroExperimenterService();
// Ensure directories exist on import so the DB writes never throw.
ensureDirs();
