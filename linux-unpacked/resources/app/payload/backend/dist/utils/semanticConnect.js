/**
 * Semantic Connect — interpret "how should these two merged apps wire together?"
 *
 * After a structural merge dumps Project B beside Project A (see graphMerge.ts),
 * the user picks a SOURCE node (from the dropped app B), a TARGET node (from the
 * existing app A), and describes the connection in plain language. The LLM turns
 * that description into a SEMANTIC edge:
 *
 *   - label     short display name for the connection
 *   - relation  one line describing what flows / what the connection means
 *   - codeHint  concrete guidance for codegen (what to export, how to consume)
 *
 * The result is stored on the edge's `data` field (semantic: true) so it:
 *   1. creates a real import dependency in codegen — VACA edge semantics are
 *      "A → B means B depends on A / B consumes A's output" (bible 04-web)
 *   2. is injected into the per-node generation prompts as a SEMANTIC
 *      CONNECTIONS section so generated files actually implement the wiring
 *   3. persists into export dependency-graph.json for the scaffolding output
 *
 * Everything here is pure (no I/O, no LLM) so it is unit-testable; the route
 * (routes/merge.ts → POST /connect) wires these helpers to the LLM.
 */
/** Cap fields so a runaway LLM response can never bloat a prompt or a file. */
const MAX_LABEL = 60;
const MAX_RELATION = 240;
const MAX_HINT = 420;
const MAX_DESCRIPTION = 400;
function trimTo(text, max) {
    const t = (text || '').trim();
    return t.length > max ? t.slice(0, max - 1).trimEnd() + '…' : t;
}
function nodeRef(n) {
    return {
        id: n?.id ?? '',
        label: n?.data?.label ?? n?.label ?? n?.id ?? '?',
        type: n?.data?.type ?? n?.type ?? 'logic',
        description: n?.data?.description ?? n?.description ?? '',
    };
}
/**
 * Build the LLM prompt that interprets a user's connection description into a
 * semantic edge. VACA edge semantics are spelled out explicitly so the model
 * cannot guess the direction backwards.
 */
export function buildConnectPrompt(ctx) {
    const src = nodeRef(ctx.nodes.find(n => n.id === ctx.sourceNodeId));
    const tgt = nodeRef(ctx.nodes.find(n => n.id === ctx.targetNodeId));
    const lines = [];
    lines.push('You are the wiring architect for a merged application. Two apps were combined and the user is describing how they should plug together.');
    lines.push('');
    lines.push(`PROJECT: ${ctx.projectName || 'Merged App'}${ctx.targetOS ? ` · TARGET OS: ${ctx.targetOS}` : ''}`);
    lines.push('');
    lines.push(`SOURCE MODULE (from the dropped app):`);
    lines.push(`  - id: ${src.id}`);
    lines.push(`  - label: "${src.label}"`);
    lines.push(`  - type: ${src.type}`);
    if (src.description)
        lines.push(`  - description: ${src.description}`);
    lines.push('');
    lines.push(`TARGET MODULE (from the existing app):`);
    lines.push(`  - id: ${tgt.id}`);
    lines.push(`  - label: "${tgt.label}"`);
    lines.push(`  - type: ${tgt.type}`);
    if (tgt.description)
        lines.push(`  - description: ${tgt.description}`);
    lines.push('');
    lines.push(`THE USER WANTS THE CONNECTION TO BE:`);
    lines.push(`  "${trimTo(ctx.description, MAX_DESCRIPTION) || '(no description given — infer the most sensible wiring between these two modules)'}"`);
    lines.push('');
    lines.push('EDGE SEMANTICS (MANDATORY): an edge source → target means the TARGET depends on the SOURCE and consumes the SOURCE\'s output. The source module must EXPORT the data/function the target needs; the target module must IMPORT and USE it.');
    lines.push('');
    lines.push('Return ONLY a JSON object with exactly these five keys (no markdown, no commentary):');
    lines.push('{');
    lines.push('  "label": "a short 2-4 word name for this connection",');
    lines.push('  "relation": "one sentence describing what flows between source and target",');
    lines.push('  "sourceHint": "concrete instruction for the SOURCE module only: what it must EXPORT (function names / data shapes / return types)",');
    lines.push('  "targetHint": "concrete instruction for the TARGET module only: how it should IMPORT the source\'s exports and USE them",');
    lines.push('  "codeHint": "a combined short version of both hints for documentation"');
    lines.push('}');
    return lines.join('\n');
}
/**
 * Robustly parse the LLM's response into a SemanticConnection. Handles plain
 * JSON, JSON wrapped in markdown fences, JSON with trailing prose, and a
 * line-based fallback for the small model's sloppier output.
 */
export function parseConnectResponse(text) {
    const clean = (text || '').trim();
    let obj = null;
    const firstBrace = clean.indexOf('{');
    const lastBrace = clean.lastIndexOf('}');
    if (firstBrace !== -1 && lastBrace > firstBrace) {
        try {
            obj = JSON.parse(clean.slice(firstBrace, lastBrace + 1));
        }
        catch {
            obj = null;
        }
    }
    // Line-based fallback: `label: ...`, `relation: ...`, `codeHint: ...`
    // (each on its own line), so even prose-y output yields usable fields.
    if (!obj) {
        const grab = (key) => {
            const re = new RegExp(`(?:^|["'\\s,])${key}\\s*[:=]\\s*["']?([^"',}\\n]+)`, 'i');
            const m = clean.match(re);
            return m ? m[1].trim() : '';
        };
        obj = {
            label: grab('label'),
            relation: grab('relation'),
            codeHint: grab('codeHint'),
        };
    }
    const str = (v) => typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '';
    const codeHint = trimTo(str(obj?.codeHint) || str(obj?.hint), MAX_HINT);
    return {
        label: trimTo(str(obj?.label), MAX_LABEL) || 'connection',
        relation: trimTo(str(obj?.relation) || str(obj?.description), MAX_RELATION),
        codeHint,
        // Side-specific hints default to the combined hint so single-hint model
        // responses still reach both sides.
        sourceHint: trimTo(str(obj?.sourceHint), MAX_HINT) || codeHint,
        targetHint: trimTo(str(obj?.targetHint), MAX_HINT) || codeHint,
    };
}
/**
 * Build the SEMANTIC CONNECTIONS section injected into a single node's
 * generation prompt. Only renders when the node participates in at least one
 * semantic (user-described) edge, so ordinary builds are byte-for-byte
 * unaffected. Direction-aware: the target file is told what to consume, the
 * source file is told what to expose.
 */
export function buildSemanticSection(node, project) {
    const nodeId = node?.id;
    if (!nodeId)
        return '';
    const edges = project.edges || [];
    const semanticEdges = edges.filter((e) => e?.data && e.data.semantic === true);
    if (semanticEdges.length === 0)
        return '';
    const lines = [];
    for (const edge of semanticEdges) {
        if (edge.source !== nodeId && edge.target !== nodeId)
            continue;
        const d = edge.data || {};
        const isTarget = edge.target === nodeId; // target consumes the source's output
        const otherId = isTarget ? edge.source : edge.target;
        const other = (project.nodes || []).find((n) => n.id === otherId);
        const otherLabel = other?.data?.label ?? other?.label ?? otherId;
        const label = trimTo(d.label, MAX_LABEL) || 'connection';
        const relation = trimTo(d.relation, MAX_RELATION);
        // Side-specific hint when present; the combined codeHint is the fallback.
        const hint = isTarget
            ? trimTo(d.targetHint, MAX_HINT) || trimTo(d.codeHint, MAX_HINT)
            : trimTo(d.sourceHint, MAX_HINT) || trimTo(d.codeHint, MAX_HINT);
        if (isTarget) {
            lines.push(`  • [${label}] Data flows INTO this file from "${otherLabel}"${relation ? ` — ${relation}` : ''}`);
        }
        else {
            lines.push(`  • [${label}] This file's output FEEDS "${otherLabel}"${relation ? ` — ${relation}` : ''}`);
        }
        if (hint)
            lines.push(`    Implement (${isTarget ? 'consume' : 'export'}): ${hint}`);
    }
    if (lines.length === 0)
        return '';
    return ('\n\n━━━ SEMANTIC CONNECTIONS (user-described wiring of the merged app — implement EXACTLY) ━━━\n' +
        'These connections were described by the user and interpreted by the architect. They define how this file plugs into the merged application:\n' +
        lines.join('\n') +
        '\nFollow every "Implement" hint precisely so the two modules actually interoperate. Do not invent other cross-file connections.');
}
