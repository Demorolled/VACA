/**
 * Plan Mode — file helpers.
 *
 * Plan Mode captures the user's app ideas and writes them to a text file
 * (data/plans/<project-name>.txt) so they can be built later. The user names
 * the project; if they don't, the UI/API asks for one before saving.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync, statSync } from 'fs';
import path from 'path';
export const PLANS_DIR = process.env.VACA_PLANS_DIR ||
    path.resolve(import.meta.dirname, '..', '..', '..', 'data', 'plans');
/** Make a filesystem-safe plan filename from a project name. */
export function safePlanName(name) {
    const cleaned = name
        .trim()
        .replace(/[^a-zA-Z0-9 _-]/g, '')
        .replace(/\s+/g, '_')
        .replace(/_+/g, '_')
        .slice(0, 80);
    return cleaned || 'untitled-plan';
}
/** Format a complete plan text file body. */
export function formatPlanFile(opts) {
    const { projectName, ideas, guidance, questions, updatedAt } = opts;
    const rule = '='.repeat(60);
    const lines = [
        rule,
        `PLAN: ${projectName}`,
        rule,
        `Status: PLANNED`,
        `Last updated: ${updatedAt}`,
        '',
        '## Ideas / Notes',
        '--------------------',
        ideas.trim() || '(no ideas captured yet)',
        '',
        '## AI Guidance / Assistance',
        '--------------------',
        guidance.trim() || '(no guidance yet — click "✨ Help me plan" in Plan Mode)',
        '',
        '## Open Questions',
        '--------------------',
        questions.trim() || '(none)',
        '',
        '---',
        'Auto-saved by VACA Plan Mode — ready to build when you are.',
        '',
    ];
    return lines.join('\n');
}
/** Save a plan to data/plans/<name>.txt. Returns the record. */
export function savePlanFile(data) {
    const projectName = data.projectName.trim();
    const fileName = `${safePlanName(projectName)}.txt`;
    if (!existsSync(PLANS_DIR))
        mkdirSync(PLANS_DIR, { recursive: true });
    const filePath = path.join(PLANS_DIR, fileName);
    const updatedAt = new Date().toISOString();
    const body = formatPlanFile({
        projectName,
        ideas: data.ideas,
        guidance: data.guidance || '',
        questions: data.questions || '',
        updatedAt,
    });
    writeFileSync(filePath, body, 'utf-8');
    return { projectName, fileName, filePath, updatedAt };
}
/** List saved plan files. */
export function listPlanFiles() {
    if (!existsSync(PLANS_DIR))
        return [];
    return readdirSync(PLANS_DIR)
        .filter(f => f.endsWith('.txt'))
        .sort()
        .map(f => {
        const filePath = path.join(PLANS_DIR, f);
        const stat = existsSync(filePath)
            ? (() => { try {
                return statSync(filePath);
            }
            catch {
                return null;
            } })()
            : null;
        return {
            projectName: f.replace(/\.txt$/, '').replace(/_/g, ' '),
            fileName: f,
            filePath,
            updatedAt: stat ? stat.mtime.toISOString() : '',
        };
    });
}
/**
 * Read a plan file's text content by project name (or file name).
 * Always sanitizes through safePlanName — never join a raw user string into
 * the path (guards against path traversal via encoded '/' or '..').
 */
export function readPlanFile(name) {
    const base = name.endsWith('.txt') ? name.slice(0, -4) : name;
    const fileName = `${safePlanName(base)}.txt`;
    const filePath = path.join(PLANS_DIR, fileName);
    if (!existsSync(filePath))
        return null;
    return { content: readFileSync(filePath, 'utf-8'), filePath };
}
/** Render the plan folder's plan.md. */
export function formatPlanMarkdown(opts) {
    const { projectName, goal, nodes, edges, updatedAt } = opts;
    const rule = '='.repeat(60);
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const lines = [
        rule,
        `PLAN: ${projectName}`,
        rule,
        'Status: DESIGNING (Big Plan Mode)',
        `Last saved: ${updatedAt}`,
        '',
        '## What are we building?',
        '--------------------',
        goal.trim() || '(the master node has no description yet)',
        '',
        '## Functions (nodes)',
        '--------------------',
    ];
    if (nodes.length === 0) {
        lines.push('(no nodes yet)');
    }
    else {
        for (const n of nodes) {
            const lang = n.language ? ` [${n.type}/${n.language}]` : ` [${n.type}]`;
            const mark = n.isMaster ? '● ' : '- ';
            lines.push(`${mark}${n.label}${lang}`);
            lines.push(`    ${(n.description || '(no function declared yet)').trim()}`);
            for (const qa of n.qa || []) {
                if (!qa?.a)
                    continue;
                lines.push(`    Q: ${(qa.q || '').trim()}`);
                lines.push(`    A: ${qa.a.trim()}`);
            }
        }
    }
    lines.push('', '## Wiring', '--------------------');
    if (edges.length === 0) {
        lines.push('(no edges yet)');
    }
    else {
        for (const e of edges) {
            const from = byId.get(e.source)?.label || e.source;
            const to = byId.get(e.target)?.label || e.target;
            lines.push(`- ${from} -> ${to}${e.label ? `  (${e.label})` : ''}`);
        }
    }
    lines.push('', '---', 'Auto-saved by Big Plan Mode every 5 minutes. Nothing is generated from this', 'plan until you choose to build it.', '');
    return lines.join('\n');
}
/**
 * Save (create or update) a plan graph folder. Creates the directory on first
 * call, which is what "auto-create the files and folders" means here: the plan
 * starts existing on disk as soon as there is something to save.
 */
export function savePlanGraph(data) {
    const projectName = (data.projectName || 'Untitled Project').trim();
    const dirName = safePlanName(projectName);
    const dirPath = path.join(PLANS_DIR, dirName);
    const nodes = Array.isArray(data.nodes) ? data.nodes : [];
    const edges = Array.isArray(data.edges) ? data.edges : [];
    const updatedAt = new Date().toISOString();
    mkdirSync(dirPath, { recursive: true });
    writeFileSync(path.join(dirPath, 'graph.json'), JSON.stringify({ projectName, goal: data.goal || '', nodes, edges, updatedAt }, null, 2), 'utf-8');
    writeFileSync(path.join(dirPath, 'plan.md'), formatPlanMarkdown({ projectName, goal: data.goal || '', nodes, edges, updatedAt }), 'utf-8');
    return {
        projectName,
        dirName,
        dirPath,
        files: ['plan.md', 'graph.json'],
        nodeCount: nodes.length,
        edgeCount: edges.length,
        updatedAt,
    };
}
/**
 * List saved Big Plan Mode designs (the folders written by savePlanGraph).
 *
 * Separate from listPlanFiles(): those are the old single-file `.txt` plans.
 * A plan graph is a folder holding graph.json + plan.md, and only the folders
 * can be reloaded onto the canvas — so the "open a saved plan" picker needs
 * this list, not the .txt one. A folder without a readable graph.json is
 * skipped rather than listed as broken: it is either mid-write or was never a
 * plan graph.
 */
export function listPlanGraphs() {
    if (!existsSync(PLANS_DIR))
        return [];
    const out = [];
    for (const entry of readdirSync(PLANS_DIR)) {
        const dirPath = path.join(PLANS_DIR, entry);
        try {
            if (!statSync(dirPath).isDirectory())
                continue;
        }
        catch {
            continue;
        }
        const graphPath = path.join(dirPath, 'graph.json');
        if (!existsSync(graphPath))
            continue;
        try {
            const raw = JSON.parse(readFileSync(graphPath, 'utf-8'));
            out.push({
                projectName: raw.projectName || entry,
                dirName: entry,
                goal: raw.goal || '',
                nodeCount: Array.isArray(raw.nodes) ? raw.nodes.length : 0,
                edgeCount: Array.isArray(raw.edges) ? raw.edges.length : 0,
                updatedAt: raw.updatedAt || '',
            });
        }
        catch {
            continue;
        }
    }
    // Most recently saved first: the design you were just working on is the one
    // you are most likely reopening.
    return out.sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
}
/** Read a plan graph folder back (for reloading a design onto the canvas). */
export function readPlanGraph(name) {
    const dirPath = path.join(PLANS_DIR, safePlanName(name));
    const graphPath = path.join(dirPath, 'graph.json');
    if (!existsSync(graphPath))
        return null;
    try {
        const raw = JSON.parse(readFileSync(graphPath, 'utf-8'));
        return {
            projectName: raw.projectName || name,
            goal: raw.goal || '',
            nodes: Array.isArray(raw.nodes) ? raw.nodes : [],
            edges: Array.isArray(raw.edges) ? raw.edges : [],
            dirPath,
        };
    }
    catch {
        return null;
    }
}
