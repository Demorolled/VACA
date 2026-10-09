/**
 * scaffoldExperiment — the scaffold self-improvement LOOP.
 *
 * Direction (2026-10-03): VACA builds the scaffold; the LLM fills in the code.
 * So the thing worth improving is the SCAFFOLD (a blueprint's architecture
 * checklist + wiring graph). This module runs ONE experiment:
 *
 *   incumbent = build(blueprint)              ← today's scaffold
 *   for each variant in generateVariants(bp):  ← mutated scaffolds
 *       score = build(variant)                 ← generate + gate + score
 *   winner = best variant that beats incumbent by a margin
 *
 * The LLM is NOT the scaffolder here — it only FILLS the files, so scoring a
 * variant measures the scaffold, not the model. (The model's own contribution
 * shows up as adherence/noise, which the margin absorbs.)
 *
 * `build` is injected so the whole search is testable without a compiler, a
 * browser, or a model: the idle service passes the real blueprint→FileGenerator
 * pipeline, tests pass a stub. No LLM, no disk in this module.
 */
import { generateVariants, scoreVariant, scoreFilesAdherence, isImprovement, describeScoredVariant, } from './scaffoldVariation.js';
/** Turn a build outcome into the scorer's metric shape. */
export function metricsFromOutcome(outcome) {
    if (!outcome)
        return null;
    const adherence = scoreFilesAdherence(outcome.files);
    return {
        tscClean: !!outcome.tsCompileClean,
        smokePassed: outcome.renderSmoke !== 'failed' && outcome.cliSmoke !== 'failed',
        adherence: adherence.score,
        fullyAdherent: adherence.fullyAdherent,
        driftMissing: outcome.driftMissing,
        driftUnexpected: outcome.driftUnexpected,
        contractViolations: outcome.contractViolations,
        fileCount: outcome.files.length,
    };
}
function measureVariant(variant, outcome) {
    const metrics = metricsFromOutcome(outcome);
    const ok = !!metrics && metrics.fileCount > 0;
    return { ...variant, metrics, score: ok ? scoreVariant(metrics) : 0, ok };
}
/**
 * Run one scaffold experiment. Builds the incumbent, then every variant, and
 * returns the best variant ONLY if it beats the incumbent by `margin` (default
 * 0.25). Everything is bounded and best-effort: a variant whose build throws is
 * recorded as `ok:false` and cannot win.
 */
export async function runScaffoldExperiment(opts) {
    const { blueprint, build } = opts;
    const margin = opts.margin ?? 0.25;
    const log = opts.log ?? (() => { });
    const result = {
        ok: false, appType: blueprint.app_type, incumbent: null,
        variants: [], winner: null, adopted: false,
    };
    const safeBuild = async (bp) => {
        try {
            return await build(bp);
        }
        catch (err) {
            log(`[scaffold-experiment] build threw: ${err?.message || err}`);
            return null;
        }
    };
    const incumbentOutcome = await safeBuild(blueprint);
    const incumbent = measureVariant({ id: 'incumbent', op: 'add_wiring', rationale: 'unchanged scaffold', blueprint }, incumbentOutcome);
    result.incumbent = incumbent;
    log(`[scaffold-experiment] ${blueprint.app_type} incumbent: ${describeScoredVariant(incumbent)}`);
    const proposed = generateVariants(blueprint, {
        max: opts.maxVariants ?? 6,
        proposedNames: opts.proposedNames,
    });
    log(`[scaffold-experiment] ${proposed.length} variant(s) proposed`);
    for (const variant of proposed) {
        const outcome = await safeBuild(variant.blueprint);
        const scored = measureVariant(variant, outcome);
        result.variants.push(scored);
        log(`[scaffold-experiment]   ${variant.op}: ${describeScoredVariant(scored)}`);
    }
    // Winner = best scoring variant that beats the incumbent by the margin.
    const buildable = result.variants.filter((v) => v.ok);
    const best = buildable.sort((a, b) => b.score - a.score)[0] || null;
    if (best && isImprovement(best, incumbent, margin)) {
        result.winner = best;
        result.adopted = true;
        result.ok = true;
        log(`[scaffold-experiment] ADOPT ${best.id} (${best.score} vs ${incumbent.score})`);
    }
    else {
        result.ok = true; // the experiment ran; it just found no improvement
        log(`[scaffold-experiment] keep incumbent (best variant ${best ? best.score : 'n/a'} vs ${incumbent.score})`);
    }
    return result;
}
// Re-export the pieces callers usually need alongside the loop.
export { generateVariants, scoreVariant, isImprovement, describeScoredVariant } from './scaffoldVariation.js';
