/**
 * Dry-run harness — build a REALLY SMALL app several times, once per language,
 * through VACA's real plan + write pipeline, then dump every generated file so
 * it can be compiled and run with the real toolchain.
 *
 * This is the round-0 path the micro-experimenter uses (planProject →
 * generatePlanFiles), run directly so a failed build still leaves its output on
 * disk for inspection (the experimenter only keeps gate-passing artifacts).
 *
 * Usage (from backend/):
 *   node ../node_modules/.bin/tsx src/scripts/dry-run-languages.ts [--out DIR] [--only python,go]
 *
 * Output:
 *   <out>/<language>/…            generated source files (real plan paths)
 *   <out>/<language>/_meta.json   purpose, planned paths, gate verdicts, errors
 *   <out>/_summary.json           one row per language (written after each case)
 */
import fs from 'fs';
import os from 'os';
import path from 'path';
import { planProject, generatePlanFiles } from '../routes/codePlanner.js';
import { languageFromPath } from '../utils/languageFromPath.js';
// One tiny CLI app per gate language. Mirrors the micro-experimenter catalog so
// the same purposes the self-improvement loop uses are exercised here.
const CASES = [
    { language: 'python', purpose: 'a palindrome checker in python CLI program' },
    { language: 'go', purpose: 'a word frequency counter in go CLI program' },
    { language: 'rust', purpose: 'a word counter in rust CLI program' },
    { language: 'c', purpose: 'a dice roller in c CLI program' },
    { language: 'cpp', purpose: 'a number guessing game in c++ CLI program' },
    { language: 'java', purpose: 'a bank account in java CLI program' },
    { language: 'csharp', purpose: 'a todo list in c# CLI program' },
    { language: 'kotlin', purpose: 'a temperature stats in kotlin CLI program' },
    { language: 'swift', purpose: 'a word reverser in swift CLI program' },
    { language: 'php', purpose: 'a csv parser in php CLI program' },
    { language: 'ruby', purpose: 'an anagram grouper in ruby CLI program' },
];
function argValue(flag) {
    const i = process.argv.indexOf(flag);
    return i >= 0 ? process.argv[i + 1] : undefined;
}
const OUT = path.resolve(argValue('--out') || path.join(os.tmpdir(), 'vaca-dryrun'));
const ONLY = (argValue('--only') || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
const TIMEOUT_MS = Number(process.env.DRYRUN_TIMEOUT_MS || 300_000);
function summaryPath() {
    return path.join(OUT, '_summary.json');
}
function loadSummary() {
    try {
        return JSON.parse(fs.readFileSync(summaryPath(), 'utf-8'));
    }
    catch {
        return [];
    }
}
function saveSummary(rows) {
    fs.mkdirSync(OUT, { recursive: true });
    fs.writeFileSync(summaryPath(), JSON.stringify(rows, null, 2), 'utf-8');
}
async function runCase(c) {
    const dir = path.join(OUT, c.language);
    fs.mkdirSync(dir, { recursive: true });
    const row = {
        language: c.language,
        purpose: c.purpose,
        dir,
        ok: false,
        generated: 0,
        paths: [],
        gateClean: null,
        gateErrors: [],
        compileStatus: null,
        stubFailures: [],
        error: null,
        ms: 0,
    };
    const t0 = Date.now();
    try {
        const planned = await planProject(c.purpose, 'small');
        if (!planned || !planned.plan?.files?.length) {
            row.error = 'plan failed';
            row.ms = Date.now() - t0;
            return row;
        }
        const plannedPaths = planned.plan.files.map((f) => f.path);
        const gen = await generatePlanFiles(c.purpose, planned.plan, undefined, TIMEOUT_MS, undefined, 1, planned.intent);
        if (!gen || !gen.files?.length) {
            row.error = 'generation returned no files';
            row.paths = plannedPaths;
            row.ms = Date.now() - t0;
            return row;
        }
        // Persist every produced file at its real plan path.
        for (const f of gen.files) {
            const rel = String(f.path || '').replace(/^\/+/, '');
            const abs = path.join(dir, rel);
            if (!abs.startsWith(dir + path.sep))
                continue;
            fs.mkdirSync(path.dirname(abs), { recursive: true });
            fs.writeFileSync(abs, f.content ?? '', 'utf-8');
        }
        row.generated = gen.files.length;
        row.paths = gen.files.map((f) => f.path);
        row.plannedLanguage = languageFromPath(gen.files[0]?.path || '');
        row.compileStatus = gen.compileStatus ?? null;
        row.gateClean = gen.languageGates?.length
            ? gen.languageGates.every((g) => g.clean)
            : null;
        row.gateErrors = (gen.languageGates || [])
            .filter((g) => !g.clean)
            .flatMap((g) => (g.errors || []).slice(0, 8).map((e) => `[${g.language}] ${e}`));
        row.stubFailures = gen.stubFailures || [];
        row.mode = gen.mode;
        row.repairRounds = gen.repairRounds ?? null;
        row.ok = true;
    }
    catch (err) {
        row.error = err?.message || String(err);
    }
    row.ms = Date.now() - t0;
    fs.writeFileSync(path.join(dir, '_meta.json'), JSON.stringify(row, null, 2), 'utf-8');
    return row;
}
async function main() {
    const cases = ONLY.length ? CASES.filter((c) => ONLY.includes(c.language)) : CASES;
    if (!cases.length) {
        console.error(`No cases match --only=${ONLY.join(',')}. Known: ${CASES.map((c) => c.language).join(', ')}`);
        process.exit(1);
    }
    fs.mkdirSync(OUT, { recursive: true });
    console.log(`[dry-run] out=${OUT} cases=${cases.map((c) => c.language).join(', ')}`);
    const rows = loadSummary();
    for (const c of cases) {
        process.stdout.write(`[dry-run] ${c.language}: building "${c.purpose}" … `);
        const row = await runCase(c);
        const idx = rows.findIndex((r) => r.language === c.language);
        if (idx >= 0)
            rows[idx] = row;
        else
            rows.push(row);
        saveSummary(rows);
        console.log(row.error
            ? `FAILED (${row.error})`
            : `ok files=${row.generated} gateClean=${row.gateClean} compile=${row.compileStatus} ${row.ms}ms`);
    }
    console.log(`[dry-run] done → ${summaryPath()}`);
}
main().catch((err) => {
    console.error('[dry-run] fatal:', err?.stack || err);
    process.exit(1);
});
