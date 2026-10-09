import { Router } from "express";
import { suggestForBlueprint, suggestForNode, } from "../blueprint/suggester.js";
import { getSearchService } from "../search/webSearch.js";
import { researchDesign, formatResearchContext } from "../search/designResearch.js";
import { getBlueprintByType, matchBlueprint, blueprintToProject, loadBlueprints, } from "../blueprint/bible.js";
import { projects } from "../db/projects.js";
import { FileGenerator, projectGraphSignature } from "../layers/fileGenerator.js";
import { broadcastGenerationProgress } from "../socket/socketManager.js";
import { captureVerifiedGeneration } from "../training/verifiedGenerationCapture.js";
import { buildGuiMockupHtml, renderGuiMockupToPng, compareModulesToFiles } from "../blueprint/mockup.js";
import { gatherInternalKnowledge } from "../knowledge/internalKnowledge.js";
import { learningEngine } from "../knowledge/learningEngine.js";
const router = Router();
const fileGenerator = new FileGenerator();
/**
 * Shared blueprint-resolution used by BOTH /build and /mockup so the two
 * routes can never drift apart on which blueprint a goal matches. Mirrors the
 * exact semantics of /build's inline matching: explicit appType wins, then
 * semantic (with the 0.30 floor), then the generic fallback.
 */
function resolveBlueprint(body) {
    const { goal, appType } = body || {};
    const LOW_SCORE_THRESHOLD = 0.30;
    const candidates = matchBlueprint(goal.trim(), 5, LOW_SCORE_THRESHOLD);
    let matched;
    let matchedBy = "semantic";
    if (typeof appType === "string" && appType.trim()) {
        const bp = getBlueprintByType(appType.trim());
        if (bp) {
            matched = { blueprint: bp, score: 1 };
            matchedBy = "explicit";
        }
        else {
            return {
                error: { status: 404, body: { error: `No blueprint of type '${appType}'`, available: loadBlueprints().map(b => b.app_type) } },
            };
        }
    }
    else {
        const best = candidates[0];
        if (best) {
            matched = best;
            matchedBy = "semantic";
        }
        else {
            const fallback = getBlueprintByType("generic_fullstack_app");
            if (fallback) {
                matched = { blueprint: fallback, score: 0 };
                matchedBy = "fallback";
            }
        }
    }
    if (!matched) {
        return {
            error: { status: 422, body: { error: "No matching blueprint available.", available: loadBlueprints().map(b => b.app_type) } },
        };
    }
    return { matched, matchedBy, candidates };
}
// ---------------------------------------------------------------------------
// POST /api/blueprint/mockup  –  pre-build GUI mockup (fast preview image)
// ---------------------------------------------------------------------------
// The "GUI before code" flow: match the user's goal to the blueprint bible
// (same matching as /build), then render a DETERMINISTIC mockup image of how
// the app's GUI should look — module sidebar, palette, data-flow cards — with
// NO LLM call and NO file generation. The frontend shows this image to the
// user BEFORE generating code, so they can sanity-check the design and then
// approve the full build (POST /api/blueprint/build) with the real files.
//
// Body: { goal, purpose?, targetOS?, language?, appType? }
// Returns: { success, mockup: { available, imageBase64?, html, appType, matchScore, matchedBy }, timingMs }
router.post("/mockup", async (req, res) => {
    const startTime = Date.now();
    try {
        const { goal, purpose, targetOS, language, appType, theme, layout } = req.body || {};
        if (!goal || typeof goal !== "string" || goal.trim().length === 0) {
            res.status(400).json({ error: "A non-empty 'goal' string is required." });
            return;
        }
        const resolved = resolveBlueprint(req.body);
        if (resolved.error) {
            res.status(resolved.error.status).json(resolved.error.body);
            return;
        }
        const { matched, matchedBy } = resolved;
        const html = buildGuiMockupHtml(matched.blueprint, goal.trim(), { purpose, targetOS, language, theme, layout });
        // Render to a real PNG when Chromium is available; the HTML is always
        // returned so the frontend can display it in an iframe as a fallback.
        const render = await renderGuiMockupToPng(html);
        res.json({
            success: true,
            mockup: {
                available: render.available,
                reason: render.reason,
                imageBase64: render.imageBase64,
                html: render.html,
                appType: matched.blueprint.app_type,
                description: matched.blueprint.description,
                modules: matched.blueprint.architecture_checklist,
                wiring: matched.blueprint.wiring_graph,
                matchScore: matched.score,
                matchedBy,
                theme: theme || null,
                layout: layout || null,
            },
            timingMs: {
                total: Date.now() - startTime,
                render: render.durationMs,
            },
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error("[blueprint] Mockup error:", message);
        res.status(500).json({ error: "GUI mockup failed.", details: message });
    }
});
// ---------------------------------------------------------------------------
// POST /api/blueprint/suggest  –  high-level suggestions for the whole app idea
// ---------------------------------------------------------------------------
router.post("/suggest", async (req, res) => {
    try {
        const { goal, purpose, targetOS } = req.body;
        if (!goal || typeof goal !== "string" || goal.trim().length === 0) {
            res.status(400).json({ error: "A non-empty 'goal' string is required." });
            return;
        }
        const searchService = getSearchService();
        const suggestions = await suggestForBlueprint({ goal: goal.trim(), purpose, targetOS }, searchService);
        res.json({ suggestions });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error("[blueprint] Suggestion error:", message);
        res.status(500).json({ error: "Failed to generate suggestions.", details: message });
    }
});
// ---------------------------------------------------------------------------
// POST /api/blueprint/suggest-node  –  node-specific implementation suggestions
// ---------------------------------------------------------------------------
router.post("/suggest-node", async (req, res) => {
    try {
        const { nodeType, nodeLabel, nodeDescription, language, goal, purpose, targetOS } = req.body;
        if (!goal || typeof goal !== "string") {
            res.status(400).json({ error: "A 'goal' string is required." });
            return;
        }
        if (!nodeType || typeof nodeType !== "string") {
            res.status(400).json({ error: "A 'nodeType' string is required." });
            return;
        }
        const result = await suggestForNode({
            nodeType,
            nodeLabel: nodeLabel || nodeType,
            nodeDescription: nodeDescription || "",
            language,
            goal,
            purpose,
            targetOS,
        });
        res.json(result);
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error("[blueprint] Node suggestion error:", message);
        res.status(500).json({ error: "Failed to generate node suggestions.", details: message });
    }
});
// ---------------------------------------------------------------------------
// POST /api/blueprint/build  –  blueprint-driven end-to-end app build
// ---------------------------------------------------------------------------
// The doc's Step 1–4 flow: match the user's goal to the closest blueprint in
// the embedded bible, translate it into a VACA project (one node per checklist
// module, edges from the wiring graph), fuse the blueprint constraints into
// the generation prompt, then run the existing FileGenerator over the project.
//
// Body: { goal, purpose?, targetOS?, language?, scale?, appType?, skipValidation? }
//   - goal        : natural-language description of the app to build (required)
//   - appType     : force a specific blueprint (e.g. "home_media_server");
//                   otherwise the closest match is chosen semantically
//   - language    : override the language derived from the blueprint stack
//   - scale       : small | medium | large | enterprise
//   - skipValidation: fast preview build (skips sandbox + live tsc loop)
router.post("/build", async (req, res) => {
    const startTime = Date.now();
    try {
        const { goal, purpose, targetOS, language, scale, appType, skipValidation, } = req.body || {};
        if (!goal || typeof goal !== "string" || goal.trim().length === 0) {
            res.status(400).json({ error: "A non-empty 'goal' string is required." });
            return;
        }
        // ── Step 1+3: match the request to a bible blueprint ──
        // Scores below this floor are embedding noise — prefer the safe generic
        // blueprint so a weakly-matched goal doesn't get misrouted into an
        // unrelated architecture. Exact lexical hits (a goal token matching a
        // blueprint's app_type/keywords) are boosted inside matchBlueprint, so a
        // genuine domain match ("recipes" → recipe_manager) clears the floor while
        // weak unrelated noise (e.g. code_playground at ~0.27) does not.
        const resolved = resolveBlueprint(req.body);
        if (resolved.error) {
            res.status(resolved.error.status).json(resolved.error.body);
            return;
        }
        const { matched, matchedBy, candidates } = resolved;
        // ── Step 0: design research — actually search the web for the design ──
        // The build used to skip research entirely (canned plan, no references),
        // which is why "search the internet for the design" produced boilerplate.
        // Run web + GitHub + open-source research for the goal and fuse a compact
        // context into the master node's blueprintContext so EVERY module prompt
        // carries the references. Non-fatal: a slow/hanging search (or a flaky
        // network) must never block the build, so race it against a 15s timeout.
        let research = null;
        try {
            const searchText = purpose ? `${goal.trim()} ${purpose}` : goal.trim();
            broadcastGenerationProgress({ batch: 0, totalBatches: 1, batchSize: 1, generatingNodes: [], percent: 2, phase: "researching" });
            research = await Promise.race([
                researchDesign(searchText, getSearchService(), 2),
                new Promise((_, reject) => setTimeout(() => reject(new Error("Design research timed out after 15s")), 15000)),
            ]);
            if (research && research.totalReferences > 0) {
                console.log(`[blueprint] Injected ${research.totalReferences} design references for "${goal.trim().substring(0, 50)}..." (web: ${research.webResults.length}, github: ${research.githubResults.length}, alt: ${research.altResults.totalFound})`);
            }
            else {
                research = null;
                console.log(`[blueprint] Design research returned no references for "${goal.trim().substring(0, 50)}..." — building without research (non-fatal)`);
            }
        }
        catch (err) {
            research = null;
            console.warn('[blueprint] Design research skipped (non-fatal):', err.message);
        }
        // ── Step 0b: internal knowledge — consult VACA's OWN wiki + patterns ──
        // Same fix family as research: the build used to generate with no access
        // to what VACA already knows. Query the knowledge store (patterns from
        // past builds) and token-match wiki sections for the goal, then fuse the
        // compact block into the master's blueprintContext so every module prompt
        // carries it. Non-fatal: internal knowledge is an enhancement, never a
        // build blocker.
        let internalKnowledge = null;
        try {
            internalKnowledge = gatherInternalKnowledge(`${goal.trim()} ${purpose || ''}`.trim(), { language });
            if (internalKnowledge.context) {
                console.log(`[blueprint] Injected internal knowledge for "${goal.trim().substring(0, 50)}..." (patterns: ${internalKnowledge.patternCount}, wiki sections: ${internalKnowledge.wikiSectionCount})`);
            }
        }
        catch (err) {
            internalKnowledge = null;
            console.warn('[blueprint] Internal knowledge skipped (non-fatal):', err.message);
        }
        // ── Translate blueprint → VACA project ──
        const project = blueprintToProject(matched.blueprint, {
            goal: goal.trim(),
            purpose,
            targetOS,
            language,
            scale,
            researchContext: research ? formatResearchContext(research) : undefined,
            internalKnowledgeContext: internalKnowledge?.context || undefined,
        });
        projects.create(project);
        // ── Step 4: run the existing FileGenerator over the project ──
        // The blueprint constraints are already fused into every node prompt via
        // the master node's blueprintContext (see layers/fileGenerator.ts).
        const onProgress = (progress) => {
            broadcastGenerationProgress({
                batch: progress.batch,
                totalBatches: progress.totalBatches,
                batchSize: progress.batchSize,
                generatingNodes: progress.generatingNodes,
                percent: progress.percent,
                phase: progress.phase,
            });
        };
        const generation = await fileGenerator.generateFiles(project, skipValidation === true, onProgress);
        // The skipVerifiedCapture flag exists only for the duration of this build:
        // FileGenerator consumed it (skipping its generic capture) and this route
        // performs the blueprint-enriched capture below. Clear it so a later
        // regeneration of this project via the normal canvas path captures normally.
        const master = project.nodes.find(n => n.type === 'master');
        if (master?.data?.skipVerifiedCapture)
            delete master.data.skipVerifiedCapture;
        // ── Cache this build's generation so a follow-up EXPORT reuses it ──
        // /api/export/:projectId/per-file-scaffold only reuses a cached result
        // whose graph signature still matches. This route never populated that
        // cache, so "build, then export" ran the ENTIRE LLM generation twice —
        // 5-7 minutes of duplicate work on the 14B for code that had just been
        // produced (and, because the generation is stochastic, the exported code
        // could even differ from what the user reviewed). The signature is
        // computed here, AFTER the master-node flag above is cleared, so it is
        // identical to the one the export route computes from the same project.
        projects.setGenerationCache(project.id, {
            sig: projectGraphSignature(project),
            result: generation,
            at: Date.now(),
        });
        console.log(`[blueprint] Cached generation for export reuse (${generation.files.length} files, tsClean=${generation.tsCompileClean})`);
        // ── Close the learning loop (the doc's Step 5): capture VERIFIED
        // blueprint-driven files into training/dataset/verified-generations.jsonl,
        // a priority source for the fine-tune pipeline (build-vaca-knowledge-dataset
        // and merge-campaign50-into-dataset both guarantee it into train). The
        // instruction embeds the blueprint constraints so the model learns
        // blueprint-constrained generation; FileGenerator's generic capture is
        // disabled for blueprint builds (master data flag) so each build yields
        // exactly one set of rows. Only real (non-preview) builds — broken output
        // never enters the dataset.
        let verifiedCapture = null;
        if (skipValidation !== true) {
            try {
                verifiedCapture = captureVerifiedGeneration(project, generation.files, {
                    // Use FileGenerator's authoritative verdict: rows are only captured
                    // when the live tsc loop really passed every TS/JS file.
                    tsCompileClean: generation.tsCompileClean,
                    blueprintContext: master?.data?.blueprintContext,
                    sourceTag: `blueprint-verified:${matched.blueprint.app_type}`,
                });
                if (verifiedCapture.captured > 0) {
                    console.log(`[blueprint] Captured ${verifiedCapture.captured} verified file(s) for blueprint '${matched.blueprint.app_type}' (${verifiedCapture.filePath})`);
                }
                else if (verifiedCapture.skipped > 0) {
                    console.log(`[blueprint] Verified capture skipped ${verifiedCapture.skipped} file(s): ${JSON.stringify(verifiedCapture.reasons)}`);
                }
            }
            catch (err) {
                console.warn('[blueprint] Verified-generation capture failed (non-fatal):', err);
            }
        }
        // ── Close the knowledge-store learning loop for blueprint builds ──
        // FileGenerator skips its generic learning while skipVerifiedCapture is
        // set, so this route performs the same verified-gated learning itself
        // (tsc-clean blueprint builds now teach the pattern store). Same gate as
        // the training capture: broken output never enters the store.
        if (skipValidation !== true && generation.tsCompileClean) {
            try {
                const entries = learningEngine.learnFromGeneratedFiles(project, generation.files);
                if (entries.length > 0) {
                    console.log(`[blueprint] Learned ${entries.length} pattern(s) from blueprint build '${matched.blueprint.app_type}'`);
                }
            }
            catch (err) {
                console.warn('[blueprint] Knowledge-store learning failed (non-fatal):', err);
            }
        }
        const blueprintOut = {
            app_type: matched.blueprint.app_type,
            description: matched.blueprint.description,
            target_stack: matched.blueprint.target_stack,
            architecture_checklist: matched.blueprint.architecture_checklist,
            wiring_graph: matched.blueprint.wiring_graph,
        };
        // ── Blueprint-drift report ──
        // Compare the modules the mockup promised (the blueprint checklist the
        // user saw in the pre-build preview) against the files the build actually
        // produced. A promised module with no file — or a file matching no
        // promised module — is drift the user should see, not a silent surprise.
        const drift = compareModulesToFiles(matched.blueprint.architecture_checklist, generation.files);
        res.json({
            success: true,
            projectId: project.id,
            matchedBy,
            matchScore: matched.score,
            blueprint: blueprintOut,
            research: research ? {
                searched: true,
                totalReferences: research.totalReferences,
                web: research.webResults.length,
                github: research.githubResults.length,
                openSourceAlt: research.altResults.totalFound,
                context: formatResearchContext(research),
            } : {
                searched: false,
                reason: 'No design references found within the 15s research window',
            },
            internalKnowledge: internalKnowledge?.context
                ? {
                    searched: true,
                    patterns: internalKnowledge.patternCount,
                    wikiSections: internalKnowledge.wikiSectionCount,
                    context: internalKnowledge.context,
                }
                : {
                    searched: false,
                    reason: 'No matching internal patterns or wiki sections',
                },
            candidates: (candidates || []).map(c => ({ app_type: c.blueprint.app_type, score: c.score })),
            project: {
                id: project.id,
                name: project.name,
                targetOS: project.targetOS,
                nodeCount: project.nodes.length,
                edgeCount: project.edges.length,
                nodes: project.nodes.map(n => ({ id: n.id, type: n.type, label: n.data.label })),
                edges: project.edges,
            },
            verifiedCapture,
            drift,
            ...generation,
            // Behavioral smoke verdicts (the canvas path's load-and-click gate).
            // Surfaced so the UI can show WHY a build was or wasn't trusted; null when
            // the gate was skipped (fast preview builds) or could not run.
            smoke: {
                render: generation.renderSmoke ?? null,
                cli: generation.cliSmoke ?? null,
                anyFailed: generation.renderSmoke?.status === 'failed' || generation.cliSmoke?.status === 'failed',
            },
            summary: {
                totalFiles: generation.files.length,
                totalChars: generation.totalChars,
                totalErrors: generation.totalErrors,
                validated: generation.validatedCount,
                failed: generation.failedCount,
                isAllValidated: generation.failedCount === 0,
            },
            timingMs: {
                total: Date.now() - startTime,
            },
        });
    }
    catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error("[blueprint] Build error:", message);
        res.status(500).json({ error: "Blueprint build failed.", details: message });
    }
});
export default router;
