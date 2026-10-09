import { describe, it, expect } from 'vitest';
import { FileGenerator, assembleLegacyPreviewJs, buildDependencyGraph, buildImportStatement, bundlePreviewJs, findImportedNames, findScopeLeaks, findTruncation, genErrorSignature, genRoundSignature, normalizeGenError, postProcessTsJsCode, projectGraphSignature, verifyGeneratedCodeContracts, } from './fileGenerator.js';
import { resolveTreeScopes } from '../utils/treeScope.js';
function exp(names, defaultName) {
    return { names, ...(defaultName ? { defaultName } : {}) };
}
// ─── Tree Mode: app boundaries ─────────────────────────────────────
/**
 * A two-app project: A1 → A2 is an ordinary import inside app A, and A2 → B1
 * is a data handoff from app A into app B (the user's "pass login info from
 * tree 1 to tree 2").
 */
function twoAppProject() {
    const node = (id, label, treeId) => ({
        id,
        type: 'logic',
        position: { x: 0, y: 0 },
        data: { label, description: '', status: 'pending', treeId },
    });
    return {
        id: 'p1',
        name: 'two-app',
        targetOS: 'linux',
        createdAt: new Date(),
        updatedAt: new Date(),
        trees: [
            { id: 'tree_1', name: 'App 1', goal: 'log in', targetOS: 'linux', rootNodeId: 'master-1' },
            { id: 'tree_2', name: 'App 2', goal: 'report', targetOS: 'linux', rootNodeId: 'master-2' },
        ],
        nodes: [
            { id: 'master-1', type: 'master', position: { x: 0, y: 0 }, data: { label: 'App 1', description: '', status: 'pending' } },
            { id: 'master-2', type: 'master', position: { x: 0, y: 0 }, data: { label: 'App 2', description: '', status: 'pending' } },
            node('A1', 'auth-store', 'tree_1'),
            node('A2', 'login-screen', 'tree_1'),
            node('B1', 'report-sender', 'tree_2'),
        ],
        edges: [
            { id: 'e1', source: 'A1', target: 'A2' },
            {
                id: 'e2',
                source: 'A2',
                target: 'B1',
                data: {
                    kind: 'cross-tree',
                    semantic: true,
                    label: 'Login session',
                    payloadType: 'auth-session',
                    payloadLabel: 'Login session',
                    sourceTreeId: 'tree_1',
                    targetTreeId: 'tree_2',
                    description: 'pass the login info to the report app',
                },
            },
        ],
    };
}
describe('Tree Mode dependency scoping', () => {
    it('never turns a cross-app handoff into an import', () => {
        const project = twoAppProject();
        const scope = resolveTreeScopes(project);
        const nodes = project.nodes.map((n) => ({ id: n.id, data: { label: n.data.label } }));
        // The OLD behavior (all edges) is what broke: app 2 tried to import app 1.
        const unsplit = buildDependencyGraph(nodes, project.edges);
        expect(unsplit.get('report-sender')).toEqual(['login-screen']);
        // Scoped to one tree, the handoff is gone and the app-internal import stays.
        const scoped = buildDependencyGraph(nodes, scope.intraEdges);
        expect(scoped.get('report-sender')).toBeUndefined();
        expect(scoped.get('login-screen')).toEqual(['auth-store']);
    });
    it('keys the generation cache on tree membership', () => {
        const project = twoAppProject();
        const before = projectGraphSignature(project);
        // Moving a module into the other app must invalidate the cached build.
        const moved = twoAppProject();
        moved.nodes.find((n) => n.id === 'B1').data.treeId = 'tree_1';
        expect(projectGraphSignature(moved)).not.toBe(before);
    });
    it('keys the generation cache on the cross-app payload', () => {
        const before = projectGraphSignature(twoAppProject());
        // Same two endpoints, different payload ⇒ a different bridge module.
        const rewired = twoAppProject();
        rewired.edges[1].data.payloadType = 'records';
        rewired.edges[1].data.payloadLabel = 'Database records';
        expect(projectGraphSignature(rewired)).not.toBe(before);
    });
    // The compile gate must scaffold a multi-app build into the SAME layout the
    // export writes (apps/<app>/src/…, bridge/…) — otherwise a fixer that resolves
    // sibling specifiers against the gate's tree is reasoning about paths the user
    // never receives, and per-app files never get typechecked at all.
    it('compile-checks a multi-app build in its per-app layout', async () => {
        const file = (over) => ({
            fileName: 'x.ts',
            language: 'typescript',
            code: '',
            nodeId: 'n',
            nodeLabel: 'x',
            dependencies: [],
            exports: [],
            errors: [],
            validated: true,
            ...over,
        });
        const files = [
            file({
                fileName: 'auth-store.ts',
                nodeLabel: 'auth-store',
                nodeId: 'A1',
                treeId: 'tree_1',
                appDir: 'apps/app-1',
                code: `export function provideSession(): string {\n  return 'token';\n}\n`,
            }),
            file({
                fileName: 'login-screen.ts',
                nodeLabel: 'login-screen',
                nodeId: 'A2',
                treeId: 'tree_1',
                appDir: 'apps/app-1',
                dependencies: ['auth-store'],
                code: `import { provideSession } from '../auth-store/auth-store.ts';\nexport function showLogin(): string {\n  return provideSession();\n}\n`,
            }),
            file({
                fileName: 'report-sender.ts',
                nodeLabel: 'report-sender',
                nodeId: 'B1',
                treeId: 'tree_2',
                appDir: 'apps/app-2',
                code: `export function sendReport(): void {}\n`,
            }),
            file({
                fileName: 'bridge-auth-session.ts',
                nodeLabel: 'bridge-auth-session',
                nodeId: 'bridge:tree_1->tree_2:auth-session',
                isBridge: true,
                treeIds: ['tree_1', 'tree_2'],
                code: `export interface Session {\n  token: string;\n}\nexport function readSession(): Session {\n  return { token: '' };\n}\n`,
            }),
        ];
        // runTscCheck is private; it is the gate itself, so exercise it directly.
        const generator = new FileGenerator();
        const errors = await generator.runTscCheck(files);
        expect([...errors.entries()]).toEqual([]);
    }, 60000);
    // A bridge belongs to no node, so nothing imports it: if the gate's tsconfig
    // did not include `bridge/**`, a broken bridge would sail through the build
    // unnoticed and only fail for the user after export.
    it('typechecks the bridge module even though no file imports it', async () => {
        const badBridge = {
            fileName: 'bridge-auth-session.ts',
            language: 'typescript',
            code: `export function readSession(): string {\n  return 42;\n}\n`,
            nodeId: 'bridge:tree_1->tree_2:auth-session',
            nodeLabel: 'bridge-auth-session',
            isBridge: true,
            treeIds: ['tree_1', 'tree_2'],
            dependencies: [],
            exports: ['readSession'],
            errors: [],
            validated: true,
        };
        const generator = new FileGenerator();
        const errors = await generator.runTscCheck([badBridge]);
        expect(errors.get('bridge-auth-session')?.join(' ')).toMatch(/TS2322/);
    }, 60000);
});
describe('buildImportStatement', () => {
    it('builds a named import from a dependency with named exports', () => {
        expect(buildImportStatement('timer-input', exp(['TimerInput']), 'typescript'))
            .toBe("import { TimerInput } from '../timer-input/timer-input.ts';");
    });
    it('uses a default-only import when the dependency only default-exports', () => {
        expect(buildImportStatement('engine', exp([], 'CountdownEngine'), 'typescript'))
            .toBe("import CountdownEngine from '../engine/engine.ts';");
    });
    it('imports a dependency with no exports for its side effects', () => {
        expect(buildImportStatement('styles', exp([]), 'typescript'))
            .toBe("import '../styles/styles.ts';");
    });
    it('combines default and named imports when both exist', () => {
        expect(buildImportStatement('mod', exp(['Helper'], 'Main'), 'typescript'))
            .toBe("import Main, { Helper } from '../mod/mod.ts';");
    });
    it('handles python module naming (hyphens to underscores)', () => {
        expect(buildImportStatement('timer-logic', exp(['CountdownTimer']), 'python'))
            .toBe('from timer_logic import CountdownTimer');
    });
});
describe('verifyGeneratedCodeContracts', () => {
    const fileExports = new Map([
        ['timer-input.ts', exp(['TimerInput'])],
        ['timer-logic.ts', exp(['CountdownTimer'])],
    ]);
    it('flags an import of a member the dependency never exports (TS2614)', () => {
        // Note: verifyGeneratedCodeContracts checks IMPORT statements — a member
        // ACCESS on an imported class (obj.inventedMember()) is the separate
        // findInventedMembers scan. This is the module-level contract form.
        const code = `import { onCompletion } from '../timer-input/timer-input.ts';\n`;
        const violations = verifyGeneratedCodeContracts(code, 'typescript', ['timer-input.ts'], fileExports);
        expect(violations.some(v => v.includes("TS2614") && v.includes("onCompletion"))).toBe(true);
    });
    it('flags an import of a module that is not a declared dependency (TS2307)', () => {
        const code = `import { Something } from '../other/other.ts';\n`;
        const violations = verifyGeneratedCodeContracts(code, 'typescript', ['timer-input.ts'], fileExports);
        expect(violations.some(v => v.includes("TS2307") && v.includes("other"))).toBe(true);
    });
    it('passes clean imports of declared dependencies', () => {
        const code = `import { TimerInput } from '../timer-input/timer-input.ts';\nconst t = new TimerInput();\nt.readSeconds();\n`;
        const violations = verifyGeneratedCodeContracts(code, 'typescript', ['timer-input.ts'], fileExports);
        expect(violations).toEqual([]);
    });
    it('flags stdlib default imports (they are not declared deps — the build strips them anyway)', () => {
        // Generated node files may ONLY import declared sibling dependencies; the
        // post-processor strips every other import, so the verifier flags them
        // rather than letting them silently break the build.
        const code = `import fs from 'fs';\nimport { TimerInput } from '../timer-input/timer-input.ts';\n`;
        const violations = verifyGeneratedCodeContracts(code, 'typescript', ['timer-input.ts'], fileExports);
        expect(violations.some(v => v.includes("TS2307") && v.includes("fs"))).toBe(true);
    });
});
describe('postProcessTsJsCode', () => {
    it('strips the AI-written leading import run (the build adds its own)', () => {
        const code = `import { TimerInput } from '../timer-input/timer-input.ts';\nimport fs from 'fs';\n\nexport class App {}\n`;
        expect(postProcessTsJsCode(code)).toBe('export class App {}');
    });
    it('strips mid-file column-0 imports', () => {
        const code = `export const a = 1;\nimport { x } from './y';\nexport const b = 2;\n`;
        expect(postProcessTsJsCode(code)).toBe('export const a = 1;\nexport const b = 2;');
    });
    it('keeps indented import-looking text (template literals, strings)', () => {
        const code = `const s = \`import { x } from 'y'\`;\nexport const a = 1;\n`;
        expect(postProcessTsJsCode(code)).toContain('export const a = 1;');
    });
    it('keepSiblingImports keeps relative sibling imports but still strips bare packages', () => {
        const code = `import { Task, TaskRequest } from '../core-engine/core-engine.ts';\nimport fs from 'fs';\nimport 'fake-polyfill';\n\nexport class App {}\n`;
        const out = postProcessTsJsCode(code, { keepSiblingImports: true });
        expect(out).toContain("import { Task, TaskRequest } from '../core-engine/core-engine.ts';");
        expect(out).not.toContain("import fs");
        expect(out).not.toContain('fake-polyfill');
        expect(out).toContain('export class App {}');
    });
    it('keepSiblingImports keeps multi-line sibling block imports', () => {
        const code = `import {\n  CoreEngine,
  Task,
} from '../core-engine/core-engine.ts';\n\nexport class App {}\n`;
        const out = postProcessTsJsCode(code, { keepSiblingImports: true });
        expect(out).toContain("from '../core-engine/core-engine.ts'");
        expect(out).toContain('CoreEngine');
        expect(out).toContain('export class App {}');
    });
    it('default (no opts) still strips sibling imports — single-file mode unchanged', () => {
        const code = `import { Task } from '../core-engine/core-engine.ts';\nexport class App {}\n`;
        expect(postProcessTsJsCode(code)).toBe('export class App {}');
    });
});
describe('findImportedNames (sibling-import extraction for auto-import dedupe)', () => {
    it('extracts named, default, namespace and aliased members from relative imports', () => {
        const code = `import { Task, TaskRequest as TR } from '../core-engine/core-engine.ts';\nimport CoreEngine from '../core-engine/core-engine.ts';\nimport * as UI from '../ui-screens/ui-screens.ts';\nimport {\n  A,
  B,
} from '../data-store/data-store.ts';\nexport class App {}\n`;
        const names = findImportedNames(code);
        expect(names.has('Task')).toBe(true);
        expect(names.has('TaskRequest')).toBe(true);
        expect(names.has('TR')).toBe(true);
        expect(names.has('CoreEngine')).toBe(true);
        expect(names.has('UI')).toBe(true);
        expect(names.has('A')).toBe(true);
        expect(names.has('B')).toBe(true);
        // Bare/package imports are NOT relative — never counted.
        expect(names.has('fs')).toBe(false);
    });
});
describe('bundlePreviewJs (esbuild preview wiring)', () => {
    const mkFile = (over) => ({
        fileName: 'x.ts',
        language: 'typescript',
        code: 'export const x = 1;',
        nodeId: 'n',
        nodeLabel: 'x',
        dependencies: [],
        exports: [],
        errors: [],
        validated: true,
        ...over,
    });
    it('resolves cross-module imports into a single bundle', () => {
        const dep = mkFile({
            fileName: 'core-engine.ts',
            nodeLabel: 'core_engine',
            code: `export class ChessEngine {\n  move() { return 'ok'; }\n}`,
            exports: ['ChessEngine'],
        });
        const ui = mkFile({
            fileName: 'ui-screens.ts',
            nodeLabel: 'ui_screens',
            code: `import { ChessEngine } from '../core-engine/core-engine.ts';\nexport function render(container: HTMLElement): void {\n  container.textContent = new ChessEngine().move();\n}`,
            exports: ['render', 'createChessScreen'],
        });
        const bundled = bundlePreviewJs([dep, ui]);
        expect(bundled).not.toBeNull();
        // Dependency code is inlined (no elided-import ReferenceError possible):
        // the ChessEngine identifier + its move() body only exist in the dep file.
        expect(bundled).toContain('ChessEngine');
        expect(bundled).toContain('move()');
        // The container is resolved once and handed to whichever entry point the
        // runtime driver picks — `render` is registered as this module's candidate.
        // esbuild normalizes string literals to double quotes, so match either.
        expect(bundled).toMatch(/document\.getElementById\(["']app-container["']\)/);
        expect(bundled).toMatch(/candidates:\s*\["render"\]/);
        // No stale import statement / no legacy namespace IIFE.
        expect(bundled).not.toContain("from '../core-engine/core-engine.ts'");
        expect(bundled).not.toContain('typeof ui_screens !==');
    });
    it('does NOT call a non-entry first export (regression: seq-12 searchAndFilter crash)', () => {
        const file = mkFile({
            fileName: 'logic.ts',
            nodeLabel: 'logic',
            code: `export function boot(query: string): string[] { return []; }`,
            exports: ['boot'],
        });
        const bundled = bundlePreviewJs([file]);
        expect(bundled).not.toBeNull();
        expect(bundled).not.toContain('boot(document.getElementById(');
    });
    it('returns null when bundling fails (unresolvable import) so the caller can fall back', () => {
        const bad = mkFile({
            fileName: 'bad.ts',
            nodeLabel: 'bad',
            code: `import { x } from 'definitely-not-a-real-package-xyz';\nexport function render(c: HTMLElement): void { c.textContent = x; }`,
            exports: ['render'],
        });
        expect(bundlePreviewJs([bad])).toBeNull();
    });
    it('bundles plain JavaScript files too', () => {
        const file = mkFile({
            fileName: 'app.js',
            nodeLabel: 'app',
            language: 'javascript',
            code: `export function render(c) { c.textContent = 'hi'; }`,
            exports: ['render'],
        });
        const bundled = bundlePreviewJs([file]);
        expect(bundled).not.toBeNull();
        expect(bundled).toMatch(/document\.getElementById\(["']app-container["']\)/);
        expect(bundled).toMatch(/candidates:\s*\["render"\]/);
    });
    it('auto-invokes a camelCase entry point (renderView) — regression: blank preview', () => {
        // Real generated modules are named `renderView` / `initGame` / `startGame`,
        // not the bare `render` / `init` the exact-name list looks for. Requiring an
        // EXACT name is why a fully generated app could preview as a BLANK iframe
        // while the build reported success — every module was skipped with
        // "no entry export".
        const ui = mkFile({
            fileName: 'render-view.ts',
            nodeLabel: 'render_view',
            code: `export function renderView(container: HTMLElement): void { container.textContent = 'board'; }`,
            exports: ['renderView'],
        });
        const bundled = bundlePreviewJs([ui]);
        expect(bundled).not.toBeNull();
        expect(bundled).toMatch(/candidates:\s*\["renderView"\]/);
        expect(bundled).toMatch(/document\.getElementById\(["']app-container["']\)/);
    });
    it('registers NO candidate for a data helper — searchAndFilter stays unmatched', () => {
        // The relaxed match is prefix-only, never "contains", so a data function
        // can't be mistaken for an entry point and invoked with the container (the
        // seq-12 crash the exact-match rule was originally added for).
        const logic = mkFile({
            fileName: 'logic.ts',
            nodeLabel: 'logic',
            code: `export function searchAndFilter(q: string): string[] { return []; }`,
            exports: ['searchAndFilter'],
        });
        const bundled = bundlePreviewJs([logic]);
        expect(bundled).not.toBeNull();
        expect(bundled).toMatch(/candidates:\s*\[\]/);
    });
    it('emits a fallback panel so a module-only build is never a silent blank box', () => {
        const data = mkFile({
            fileName: 'data-store.ts',
            nodeLabel: 'data_store',
            code: `export const store = { get: () => null };`,
            exports: ['store'],
        });
        const bundled = bundlePreviewJs([data]);
        expect(bundled).not.toBeNull();
        // The preview tells the user what was built instead of rendering nothing.
        expect(bundled).toContain('no UI entry point generated');
    });
});
describe('assembleLegacyPreviewJs (fallback)', () => {
    it('emits namespaces, IIFEs and init calls (regression guard)', () => {
        const file = {
            fileName: 'ui-screens.ts',
            language: 'typescript',
            code: `export function render(c: HTMLElement): void { c.textContent = 'hi'; }`,
            nodeId: 'n',
            nodeLabel: 'ui_screens',
            dependencies: [],
            exports: ['render'],
            errors: [],
            validated: true,
        };
        const legacy = assembleLegacyPreviewJs([file]);
        expect(legacy.namespaceDeclarations).toContain('var ui_screens = {};');
        expect(legacy.jsSectionLines.join('\n')).toContain('(function(exports)');
        expect(legacy.initSetupCalls.join('\n')).toContain('ui_screens.render(document.getElementById(\'app-container\'));');
    });
    it('does NOT call a data-only export (no preferred entry) with the container', () => {
        // Regression guard for teacher-build seq 12: searchAndFilter(container)
        // crashed the preview because it takes a string, not a container.
        const file = {
            fileName: 'search-filter.ts',
            language: 'typescript',
            code: `export function searchAndFilter(query: string): string[] { return []; }`,
            nodeId: 'n',
            nodeLabel: 'search_filter',
            dependencies: [],
            exports: ['searchAndFilter'],
            errors: [],
            validated: true,
        };
        const legacy = assembleLegacyPreviewJs([file]);
        expect(legacy.initSetupCalls.join('\n')).not.toContain('searchAndFilter(document.getElementById');
    });
    it('uses relaxed entry matching so a real UI module is actually driven (renderView)', () => {
        // The legacy path used the exact-name list too, so `renderView` was skipped
        // and the preview stayed blank whenever esbuild could not bundle.
        const file = {
            fileName: 'render-view.ts',
            language: 'typescript',
            code: `export function renderView(c: HTMLElement): void { c.textContent = 'hi'; }`,
            nodeId: 'n',
            nodeLabel: 'render_view',
            dependencies: [],
            exports: ['renderView'],
            errors: [],
            validated: true,
        };
        const legacy = assembleLegacyPreviewJs([file]);
        expect(legacy.initSetupCalls.join('\n')).toContain("render_view.renderView(document.getElementById('app-container'));");
    });
    it('emits ONE script per file so a broken file cannot blank its siblings', () => {
        const mk = (label, fileName) => ({
            fileName,
            language: 'typescript',
            code: `export function render(c: HTMLElement): void { c.textContent = '${label}'; }`,
            nodeId: label,
            nodeLabel: label,
            dependencies: [],
            exports: ['render'],
            errors: [],
            validated: true,
        });
        const legacy = assembleLegacyPreviewJs([mk('a', 'a.ts'), mk('b', 'b.ts')]);
        expect(legacy.perFileScripts).toHaveLength(2);
        expect(legacy.perFileScripts[0]).toContain('a.ts');
        expect(legacy.perFileScripts[1]).toContain('b.ts');
    });
    it('reports the module inventory the empty-preview diagnostic renders', () => {
        const file = {
            fileName: 'ui-screens.ts',
            language: 'typescript',
            code: `export function render(c: HTMLElement): void { c.textContent = 'hi'; }`,
            nodeId: 'n',
            nodeLabel: 'ui_screens',
            dependencies: [],
            exports: ['render'],
            errors: [],
            validated: true,
        };
        const legacy = assembleLegacyPreviewJs([file]);
        expect(legacy.modules).toEqual([{ label: 'ui_screens', file: 'ui-screens.ts', exports: ['render'] }]);
    });
});
describe('findTruncation', () => {
    it('returns null for balanced code', () => {
        expect(findTruncation('export function a() { return 1; }\nconst b = { x: 1 };')).toBeNull();
    });
    it('detects a file cut off mid-block (more { than })', () => {
        // Simulates the seq-11 calculator failure: file ends inside a forEach.
        const truncated = "export function render(c: HTMLElement) {\n  items.forEach((i) => {\n    const btn = document.createElement('button');\n    btn.textContent = i;\n    // CUT OFF HERE — no closing braces";
        const result = findTruncation(truncated);
        expect(result).not.toBeNull();
        expect(result.open).toBeGreaterThan(result.close);
    });
    it('ignores braces inside strings and template literals', () => {
        const code = "export function a() {\n  const s = '{ not a brace }';\n  const t = `{ also not }`;\n  return s + t;\n}";
        expect(findTruncation(code)).toBeNull();
    });
    it('ignores braces inside comments', () => {
        const code = "export function a() {\n  // { not a brace\n  /* { also not } */\n  return 1;\n}";
        expect(findTruncation(code)).toBeNull();
    });
});
describe('findScopeLeaks', () => {
    it('flags inline onclick handlers that call module-local functions (seq 13 tip calc class)', () => {
        const code = `export function render(container: HTMLElement) {
  container.innerHTML = \`
    <button class="btn" onclick="appendNumber('7')">7</button>
  \`;
  let currentInput = '';
  function appendNumber(num: string) { currentInput += num; }
}`;
        const errors = findScopeLeaks(code);
        expect(errors.some((e) => e.includes('appendNumber') && e.includes('onclick'))).toBe(true);
    });
    it('flags a module-scope reference to a render-local declaration (seq 9 pw-gen class)', () => {
        const code = `export function render(container: HTMLElement) {
  let generatedPassword = '';
}
export function copyPassword() {
  navigator.clipboard.writeText(generatedPassword);
}`;
        const errors = findScopeLeaks(code);
        expect(errors.some((e) => e.includes('generatedPassword') && e.includes('module scope'))).toBe(true);
    });
    it('flags undeclared identifiers used at module scope (seq 8 checkers class)', () => {
        const code = `export function render(container: HTMLElement) {
  boardState.forEach(row => row.forEach(cell => { currentPlayer = 'white'; }));
}`;
        const errors = findScopeLeaks(code);
        expect(errors.some((e) => e.includes("boardState") && e.includes('never declared'))).toBe(true);
        expect(errors.some((e) => e.includes('currentPlayer'))).toBe(true);
    });
    it('flags a reference to an identifier only declared in a sibling function scope (seq 12 stopwatch class)', () => {
        const code = `export function render(container: HTMLElement) {
  const startBtn = document.createElement('button');
  startBtn.onclick = () => { let timerInterval: number = 0; let elapsedTime = 0; };
  const stopBtn = document.createElement('button');
  stopBtn.onclick = () => { clearInterval(timerInterval); };
}`;
        const errors = findScopeLeaks(code);
        expect(errors.some((e) => e.includes('timerInterval'))).toBe(true);
    });
    it('returns no errors for a clean multi-file module (globals, imports, params, locals)', () => {
        const code = `import { DataStore } from '../data-store/data-store.ts';
export function render(container: HTMLElement) {
  const ds = new DataStore();
  const btn = document.createElement('button');
  btn.addEventListener('click', () => ds.save('a', 1));
  container.appendChild(btn);
}
class DataStore { save(k: string, v: number) { console.log(k, v); } }`;
        expect(findScopeLeaks(code)).toEqual([]);
    });
    it('does not flag property accesses or type-position identifiers', () => {
        const code = `export function render(container: HTMLElement) {
  const state = { board: [] as string[][], currentPlayer: 'white' as string };
  state.board.push([]);
  container.textContent = state.currentPlayer;
}`;
        expect(findScopeLeaks(code)).toEqual([]);
    });
    it('does not flag optional property names in interfaces (task?: Task — the ? previously defeated the annotation skip)', () => {
        const code = `interface Task { id: number; }
interface TaskRequest {
  type: 'add' | 'update' | 'delete' | 'list';
  task?: Task;
}
export function handle(req: TaskRequest): string {
  return req.type + (req.task ? 'yes' : 'no');
}`;
        expect(findScopeLeaks(code)).toEqual([]);
    });
    it('does not flag expression-bodied arrow params (findIndex(t => t.id === id) — no brace block exists for them)', () => {
        const code = `export function find(list: Array<{ id: number }>, id: number): boolean {
  const hit = list.findIndex(t => t.id === id);
  return hit !== -1;
}`;
        expect(findScopeLeaks(code)).toEqual([]);
    });
    it('does not flag destructuring declarations (const { state, events } = x — destructuring braces are not scope blocks)', () => {
        const code = `export function update(sae: { state: { tasks: string[] }; events: { type: string } }): void {
  const { state, events } = sae;
  if (events.type === 'added') state.tasks.push('x');
}`;
        expect(findScopeLeaks(code)).toEqual([]);
    });
    it('does not flag a same-named interface property when a method param shares the name (params are method-scope, not class-scope)', () => {
        const code = `interface Task { id: number; }
interface TaskRequest { task?: Task; }
class CoreEngine {
  private addTask(task: Task): void { this.doSomething(task); }
  private doSomething(t: Task): void {}
}`;
        expect(findScopeLeaks(code)).toEqual([]);
    });
});
describe('projectGraphSignature', () => {
    it('is stable regardless of node/edge ordering', () => {
        const projectA = {
            name: 'p', targetOS: 'web',
            nodes: [
                { id: 'a', data: { label: 'x.ts', description: 'd', type: 'logic', language: 'typescript' } },
                { id: 'b', data: { label: 'y.ts', description: 'e', type: 'ui', language: 'typescript' } },
            ],
            edges: [{ source: 'a', target: 'b' }],
        };
        const projectB = {
            name: 'p', targetOS: 'web',
            nodes: [
                { id: 'b', data: { label: 'y.ts', description: 'e', type: 'ui', language: 'typescript' } },
                { id: 'a', data: { label: 'x.ts', description: 'd', type: 'logic', language: 'typescript' } },
            ],
            edges: [{ source: 'a', target: 'b' }],
        };
        expect(projectGraphSignature(projectA)).toBe(projectGraphSignature(projectB));
    });
    it('changes when the graph changes', () => {
        const base = {
            name: 'p', targetOS: 'web',
            nodes: [{ id: 'a', data: { label: 'x.ts', description: 'd', type: 'logic', language: 'typescript' } }],
            edges: [],
        };
        const changed = { ...base, nodes: [{ id: 'a', data: { label: 'z.ts', description: 'd', type: 'logic', language: 'typescript' } }] };
        expect(projectGraphSignature(base)).not.toBe(projectGraphSignature(changed));
    });
    it('changes when the app GOAL changes even though the node labels stay the same (the stale-cache chess→countdown bug)', () => {
        const base = {
            name: 'p', targetOS: 'linux',
            nodes: [
                { id: 'master', type: 'master', data: { label: 'App Blueprint', appGoal: 'a 3d chess game', appPurpose: 'play chess', scale: 'large' } },
                { id: 'a', data: { label: 'main.go', description: 'entry', type: 'logic', language: 'go' } },
            ],
            edges: [],
        };
        const relabeled = {
            ...base,
            nodes: [
                { id: 'master', type: 'master', data: { label: 'App Blueprint', appGoal: 'a simple countdown timer', appPurpose: 'count down', scale: 'small' } },
                { id: 'a', data: { label: 'main.go', description: 'entry', type: 'logic', language: 'go' } },
            ],
        };
        expect(projectGraphSignature(base)).not.toBe(projectGraphSignature(relabeled));
    });
    it('is stable when a master node has no goal fields', () => {
        const project = {
            name: 'p', targetOS: 'web',
            nodes: [{ id: 'master', type: 'master', data: { label: 'App Blueprint' } }],
            edges: [],
        };
        expect(typeof projectGraphSignature(project)).toBe('string');
    });
});
describe('compileCheckAndFix stall helpers (repair-loop convergence)', () => {
    describe('normalizeGenError', () => {
        it('strips the trailing (line N) so moved errors still count as the same issue', () => {
            expect(normalizeGenError('TS2304: Cannot find name data (line 12)')).toBe('TS2304: Cannot find name data');
            expect(normalizeGenError('TS2339: Property push does not exist (line 99)')).toBe('TS2339: Property push does not exist');
        });
        it('leaves lint messages (no line suffix) untouched', () => {
            expect(normalizeGenError('TS2304: Cannot find name data — it is referenced but never declared')).toBe('TS2304: Cannot find name data — it is referenced but never declared');
        });
    });
    describe('genErrorSignature', () => {
        it('is order-insensitive (same errors in any order → same signature)', () => {
            const a = genErrorSignature(['TS2304: Cannot find name data (line 3)', 'TS2339: push missing (line 8)']);
            const b = genErrorSignature(['TS2339: push missing (line 8)', 'TS2304: Cannot find name data (line 3)']);
            expect(a).toBe(b);
        });
        it('treats the same error at a different line as unchanged (stall detection core)', () => {
            const before = genErrorSignature(['TS2304: Cannot find name data (line 3)']);
            const after = genErrorSignature(['TS2304: Cannot find name data (line 41)']);
            expect(before).toBe(after);
        });
        it('is CLASS-aware: a renamed member on the same type is still stalled (no progress)', () => {
            // The R9 audit failure: the 14B re-invented a DIFFERENT member each round
            // (push → some → find on Task) — exact-text compare never matched, so the
            // repair loop ran all 3 slow rounds. Class-aware compare treats these as
            // the same underlying failure so the loop stops.
            expect(genErrorSignature(["TS2339: Property 'push' does not exist on type 'Task' (line 3)"])).toBe(genErrorSignature(["TS2339: Property 'find' does not exist on type 'Task' (line 41)"]));
            expect(genErrorSignature(["TS2304: Cannot find name 'data' (line 3)"])).toBe(genErrorSignature(["TS2304: Cannot find name 'task' (line 9)"]));
        });
        it('changes when the error CLASS changes (real progress)', () => {
            expect(genErrorSignature(["TS2304: Cannot find name 'data' (line 3)"])).not.toBe(genErrorSignature(["TS2339: Property 'push' does not exist (line 3)"]));
            expect(genErrorSignature(["TS2304: Cannot find name 'data' (line 3)"])).not.toBe(genErrorSignature(["TS2304: Cannot find name 'data' (line 3)", "TS2339: Property 'push' missing (line 8)"]));
        });
    });
    describe('genRoundSignature', () => {
        it('is stable regardless of file-map iteration order', () => {
            const a = new Map([
                ['core_engine', ['TS2304: Cannot find name data (line 2)']],
                ['ui_screens', ['TS2339: push missing (line 7)']],
            ]);
            const b = new Map([
                ['ui_screens', ['TS2339: push missing (line 7)']],
                ['core_engine', ['TS2304: Cannot find name data (line 2)']],
            ]);
            expect(genRoundSignature(a)).toBe(genRoundSignature(b));
        });
        it('detects no-progress rounds: same files/errors at moved lines → identical signature', () => {
            const round1 = new Map([['core_engine', ['TS2304: Cannot find name data (line 2)']]]);
            const round2 = new Map([['core_engine', ['TS2304: Cannot find name data (line 55)']]]);
            expect(genRoundSignature(round1)).toBe(genRoundSignature(round2));
        });
        it('changes when any file moves to a new error class (progress)', () => {
            const round1 = new Map([['core_engine', ["TS2304: Cannot find name 'data' (line 2)"]]]);
            const round2 = new Map([['core_engine', ["TS2304: Cannot find name 'data' (line 2)", "TS2339: Property 'push' missing (line 9)"]]]);
            expect(genRoundSignature(round1)).not.toBe(genRoundSignature(round2));
        });
        it('treats a same-class member rename as no progress (the R9 audit spiral)', () => {
            const round1 = new Map([[`task_store`, ["TS2339: Property 'some' does not exist on type 'Task' (line 4)"]]]);
            const round2 = new Map([[`task_store`, ["TS2339: Property 'find' does not exist on type 'Task' (line 12)"]]]);
            expect(genRoundSignature(round1)).toBe(genRoundSignature(round2));
        });
    });
});
