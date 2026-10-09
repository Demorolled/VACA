import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { execFileSync } from 'child_process';
import { PerFileScaffolder, pythonModuleName, pythonNoArgFuncs, rubyNoArgFuncs, goNoArgFuncs, rustNoArgFuncs, rustPublicFns, cNoArgFuncs, javaStaticNoArgFuncs, csharpStaticNoArgFuncs, swiftNoArgFuncs, kotlinTopLevelFuncs, planModuleWiring, } from './perFileScaffolder.js';
const scaffolder = new PerFileScaffolder();
let tmpDir;
let outputDir;
const files = [
    {
        fileName: 'timer-input.ts',
        language: 'typescript',
        code: `export class TimerInput {\n  readSeconds(): number { return 60; }\n}\n`,
        nodeId: 'n1',
        nodeLabel: 'timer-input.ts',
        dependencies: [],
        exports: ['TimerInput'],
        errors: [],
        validated: true,
    },
    {
        fileName: 'timer-logic.ts',
        language: 'typescript',
        code: `import { TimerInput } from '../timer-input/timer-input.ts';\nexport class CountdownTimer {\n  start(): void {}\n}\n`,
        nodeId: 'n2',
        nodeLabel: 'timer-logic.ts',
        dependencies: ['timer-input.ts'],
        exports: ['CountdownTimer'],
        errors: [],
        validated: true,
    },
];
beforeAll(async () => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-test-'));
    const result = await scaffolder.scaffold({
        projectName: 'scaffold-test-app',
        targetOS: 'linux',
        files,
        nodes: [],
        edges: [],
        outputDir: tmpDir,
    });
    outputDir = result.outputPath;
});
afterAll(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
});
describe('PerFileScaffolder TS project config', () => {
    it('writes a tsconfig that compiles structurally: no rootDir conflict (TS6059), .ts import extensions allowed (TS5097), noEmit typecheck', () => {
        const tsconfig = JSON.parse(fs.readFileSync(path.join(outputDir, 'tsconfig.json'), 'utf-8'));
        // No rootDir at all → no TS6059 (index.ts at root + src/ files both included).
        expect(tsconfig.compilerOptions.rootDir).toBeUndefined();
        expect(tsconfig.compilerOptions.allowImportingTsExtensions).toBe(true);
        expect(tsconfig.compilerOptions.noEmit).toBe(true);
        expect(tsconfig.include).toContain('index.ts');
        expect(tsconfig.include).toContain('src/**/*.ts');
    });
    it('writes a start script that can actually run TypeScript (tsx, not node)', () => {
        const pkg = JSON.parse(fs.readFileSync(path.join(outputDir, 'package.json'), 'utf-8'));
        expect(pkg.scripts.start).toBe('tsx index.ts');
        expect(pkg.scripts.build).toBe('tsc');
    });
    it('builds the entry point from the REAL exports of the generated files', () => {
        const entry = fs.readFileSync(path.join(outputDir, 'index.ts'), 'utf-8');
        // Must import the actual exported symbol names, never fabricated ones.
        expect(entry).toContain("import { TimerInput as TimerInput } from './src/timer-input/timer-input.ts'");
        expect(entry).toContain("import { CountdownTimer as CountdownTimer } from './src/timer-logic/timer-logic.ts'");
        // Side-effect import for files with no exports must not fabricate a name.
        expect(entry).not.toMatch(/import \{ \w+ \} from '\.\/src\/\w+-\w+\/(\w+)\.ts';/);
    });
    it('writes the generated source files under src/<node>/ with dirs matching the import paths', () => {
        // Dir names must match the generator's import paths (labelToFileName,
        // extension stripped) or every cross-file import breaks with TS2307.
        expect(fs.existsSync(path.join(outputDir, 'src', 'timer-input', 'timer-input.ts'))).toBe(true);
        expect(fs.existsSync(path.join(outputDir, 'src', 'timer-logic', 'timer-logic.ts'))).toBe(true);
        // And the node file's own sibling import must resolve: ../timer-input/timer-input.ts
        const logic = fs.readFileSync(path.join(outputDir, 'src', 'timer-logic', 'timer-logic.ts'), 'utf-8');
        expect(logic).toContain("from '../timer-input/timer-input.ts'");
        expect(fs.existsSync(path.join(outputDir, 'src', 'timer-input', 'timer-input.ts'))).toBe(true);
    });
    it('never imports a TYPE-ONLY export as a runtime value (the ESM entry crash)', async () => {
        const t1 = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-types-'));
        try {
            const typeFiles = [
                {
                    fileName: 'config.ts',
                    language: 'typescript',
                    code: `export interface Config {\n  port: number;\n}\nexport const config: Config = { port: 3000 };\nexport function validateConfig(c: Config): void {}\n`,
                    nodeId: 'n1',
                    nodeLabel: 'config.ts',
                    dependencies: [],
                    exports: ['Config', 'config', 'validateConfig'],
                    errors: [],
                    validated: true,
                },
            ];
            const res = await scaffolder.scaffold({
                projectName: 'types-first-app', targetOS: 'linux', files: typeFiles, nodes: [], edges: [], outputDir: t1,
            });
            const entry = fs.readFileSync(path.join(res.outputPath, 'index.ts'), 'utf-8');
            // The first export is the interface Config — it must NOT be imported.
            expect(entry).not.toContain("import { Config");
            expect(entry).toContain("import { config as config } from './src/config/config.ts'");
            // Type-only names must not be re-exported either (no runtime binding).
            expect(entry).not.toMatch(/^\s*Config,/m);
        }
        finally {
            fs.rmSync(t1, { recursive: true, force: true });
        }
    });
    it('bootstraps a non-UI project by calling its start/main entry', async () => {
        const t1 = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-boot-'));
        try {
            const bootFiles = [
                {
                    fileName: 'main.ts',
                    language: 'typescript',
                    code: `export function start(): void {\n  console.log('app started');\n}\n`,
                    nodeId: 'n1',
                    nodeLabel: 'main.ts',
                    dependencies: [],
                    exports: ['start'],
                    errors: [],
                    validated: true,
                },
            ];
            const res = await scaffolder.scaffold({
                projectName: 'boot-app', targetOS: 'linux', files: bootFiles, nodes: [], edges: [], outputDir: t1,
            });
            const entry = fs.readFileSync(path.join(res.outputPath, 'index.ts'), 'utf-8');
            expect(entry).toContain("if (typeof start === 'function') { start(); }");
        }
        finally {
            fs.rmSync(t1, { recursive: true, force: true });
        }
    });
    it('does NOT auto-bootstrap UI entry names (render/init/mount) on UI projects — the preview wrapper drives those', async () => {
        const t1 = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-ui-'));
        try {
            const uiFiles = [
                {
                    fileName: 'ui.ts',
                    language: 'typescript',
                    code: `export function render(): void {\n  console.log('ui render');\n}\n`,
                    nodeId: 'n1',
                    nodeLabel: 'ui.ts',
                    dependencies: [],
                    exports: ['render'],
                    errors: [],
                    validated: true,
                },
            ];
            const res = await scaffolder.scaffold({
                projectName: 'ui-app', targetOS: 'linux', files: uiFiles, nodes: [{ id: 'n1', type: 'ui', position: { x: 0, y: 0 }, data: { label: 'ui.ts' } }], edges: [], outputDir: t1,
            });
            const entry = fs.readFileSync(path.join(res.outputPath, 'index.ts'), 'utf-8');
            expect(entry).not.toContain("render();");
        }
        finally {
            fs.rmSync(t1, { recursive: true, force: true });
        }
    });
    it('bootstraps a UI-named entry (render) when the project has NO ui node (the F2 dead-app fix)', async () => {
        const t1 = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-render-'));
        try {
            const renderFiles = [
                {
                    fileName: 'ui.ts',
                    language: 'typescript',
                    code: `export function render(): void {\n  console.log('rendered');\n}\n`,
                    nodeId: 'n1',
                    nodeLabel: 'ui.ts',
                    dependencies: [],
                    exports: ['render'],
                    errors: [],
                    validated: true,
                },
            ];
            const res = await scaffolder.scaffold({
                projectName: 'render-app', targetOS: 'linux', files: renderFiles, nodes: [], edges: [], outputDir: t1,
            });
            const entry = fs.readFileSync(path.join(res.outputPath, 'index.ts'), 'utf-8');
            expect(entry).toContain("if (typeof render === 'function') { render(); }");
        }
        finally {
            fs.rmSync(t1, { recursive: true, force: true });
        }
    });
    it('builds a Go entry point whose imports are all USED (no "imported and not used" go build failure)', async () => {
        const t1 = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-go-'));
        try {
            const goFiles = [
                {
                    fileName: 'types.go',
                    language: 'go',
                    code: `package types\n\ntype Task struct {\n\tID uint\n}\n\nfunc NewTask(id uint) Task {\n\treturn Task{ID: id}\n}\n`,
                    nodeId: 'n1',
                    nodeLabel: 'types.go',
                    dependencies: [],
                    exports: ['Task', 'NewTask'],
                    errors: [],
                    validated: true,
                },
                {
                    fileName: 'store.go',
                    language: 'go',
                    code: `package store\n\ntype Store struct{}\n\nfunc NewStore() *Store {\n\treturn &Store{}\n}\n`,
                    nodeId: 'n2',
                    nodeLabel: 'store.go',
                    dependencies: [],
                    exports: ['Store', 'NewStore'],
                    errors: [],
                    validated: true,
                },
            ];
            const res = await scaffolder.scaffold({
                projectName: 'go-app', targetOS: 'linux', files: goFiles, nodes: [], edges: [], outputDir: t1,
            });
            const entry = fs.readFileSync(path.join(res.outputPath, 'main.go'), 'utf-8');
            // Value exports are referenced (types.NewTask, store.NewStore)...
            expect(entry).toContain('_ = pkg0.NewTask');
            expect(entry).toContain('_ = pkg1.NewStore');
            // ...and the TYPE-only export (Task) is never referenced as a value.
            expect(entry).not.toContain('.Task');
            // Blank import is only used when a package has NO value exports.
            expect(entry).not.toContain('import _');
        }
        finally {
            fs.rmSync(t1, { recursive: true, force: true });
        }
    });
});
// ─── Tree Mode: separate apps + a shared bridge ────────────────────
const trees = [
    { id: 'tree_1', name: 'Expense Tracker', goal: 'track spending', targetOS: 'linux', rootNodeId: 'master-1' },
    { id: 'tree_2', name: 'Report Mailer', goal: 'email the report', targetOS: 'linux', rootNodeId: 'master-2' },
];
/** The files a two-app build produces: one module per app + one bridge. */
const twoAppFiles = () => [
    {
        fileName: 'auth-store.ts',
        language: 'typescript',
        code: `export function provideSession(): string {\n  return 'token';\n}\n`,
        nodeId: 'A1',
        nodeLabel: 'auth-store',
        treeId: 'tree_1',
        appDir: 'apps/expense-tracker',
        dependencies: [],
        exports: ['provideSession'],
        errors: [],
        validated: true,
    },
    {
        fileName: 'report-sender.ts',
        language: 'typescript',
        code: `export function sendReport(): void {}\n`,
        nodeId: 'B1',
        nodeLabel: 'report-sender',
        treeId: 'tree_2',
        appDir: 'apps/report-mailer',
        dependencies: [],
        exports: ['sendReport'],
        errors: [],
        validated: true,
    },
    {
        fileName: 'bridge-auth-session.ts',
        language: 'typescript',
        code: `export interface Session {\n  token: string;\n}\nexport function readSession(): Session {\n  return { token: '' };\n}\n`,
        nodeId: 'bridge:tree_1->tree_2:auth-session',
        nodeLabel: 'bridge-auth-session',
        isBridge: true,
        treeIds: ['tree_1', 'tree_2'],
        dependencies: [],
        exports: ['Session', 'readSession'],
        errors: [],
        validated: true,
    },
];
const treeEdges = [
    {
        id: 'e2',
        source: 'A1',
        target: 'B1',
        data: {
            kind: 'cross-tree',
            semantic: true,
            label: 'Login session',
            relation: 'pass the login info to the report app',
            payloadType: 'auth-session',
            payloadLabel: 'Login session',
            sourceTreeId: 'tree_1',
            targetTreeId: 'tree_2',
            description: 'pass the login info through',
        },
    },
];
const treeNodes = [
    { id: 'master-1', type: 'master', position: { x: 0, y: 0 }, data: { label: 'Expense Tracker', description: '', status: 'pending' } },
    { id: 'A1', type: 'logic', position: { x: 0, y: 0 }, data: { label: 'auth-store', description: '', status: 'pending', treeId: 'tree_1' } },
    { id: 'B1', type: 'logic', position: { x: 0, y: 0 }, data: { label: 'report-sender', description: '', status: 'pending', treeId: 'tree_2' } },
];
describe('PerFileScaffolder Tree Mode', () => {
    let dir;
    let result;
    beforeAll(async () => {
        dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-trees-'));
        result = await scaffolder.scaffold({
            projectName: 'two-app-project',
            targetOS: 'linux',
            files: twoAppFiles(),
            nodes: treeNodes,
            edges: treeEdges,
            trees: trees,
            outputDir: dir,
        });
    });
    afterAll(() => {
        fs.rmSync(dir, { recursive: true, force: true });
    });
    const out = () => result.outputPath;
    it('builds each app tree as its own app directory', () => {
        expect(fs.existsSync(path.join(out(), 'apps', 'expense-tracker', 'src', 'auth-store', 'auth-store.ts'))).toBe(true);
        expect(fs.existsSync(path.join(out(), 'apps', 'report-mailer', 'src', 'report-sender', 'report-sender.ts'))).toBe(true);
        // App 2's source must NOT be merged into app 1's tree.
        expect(fs.existsSync(path.join(out(), 'apps', 'expense-tracker', 'src', 'report-sender'))).toBe(false);
        expect(result.perNodeFiles.map((f) => f.filePath).sort()).toEqual([
            'apps/expense-tracker/src/auth-store/auth-store.ts',
            'apps/report-mailer/src/report-sender/report-sender.ts',
            'bridge/bridge-auth-session.ts',
        ]);
    });
    it('gives every app its own entry point and project config', () => {
        for (const app of ['expense-tracker', 'report-mailer']) {
            expect(fs.existsSync(path.join(out(), 'apps', app, 'index.ts'))).toBe(true);
            expect(fs.existsSync(path.join(out(), 'apps', app, 'package.json'))).toBe(true);
            expect(fs.existsSync(path.join(out(), 'apps', app, 'tsconfig.json'))).toBe(true);
        }
        // One app directory, one program — there is no project-root entry point.
        expect(fs.existsSync(path.join(out(), 'index.ts'))).toBe(false);
        expect(fs.existsSync(path.join(out(), 'package.json'))).toBe(false);
        // An app's entry imports only its OWN modules.
        const entry = fs.readFileSync(path.join(out(), 'apps', 'expense-tracker', 'index.ts'), 'utf-8');
        expect(entry).toContain("import { provideSession as provideSession } from './src/auth-store/auth-store.ts'");
        expect(entry).not.toContain('report-sender');
    });
    it('puts the bridge in the shared bridge/ dir and re-exports it from both apps', () => {
        expect(fs.existsSync(path.join(out(), 'bridge', 'bridge-auth-session.ts'))).toBe(true);
        for (const app of ['expense-tracker', 'report-mailer']) {
            const entry = fs.readFileSync(path.join(out(), 'apps', app, 'index.ts'), 'utf-8');
            expect(entry).toContain("export * as bridgeAuthSession from '../../bridge/bridge-auth-session.ts';");
        }
    });
    it('records the apps, the per-file app dirs and the cross-app handoff in dependency-graph.json', () => {
        const graph = JSON.parse(fs.readFileSync(path.join(out(), 'dependency-graph.json'), 'utf-8'));
        expect(graph.apps).toEqual([
            { id: 'tree_1', name: 'Expense Tracker', goal: 'track spending', dir: 'apps/expense-tracker' },
            { id: 'tree_2', name: 'Report Mailer', goal: 'email the report', dir: 'apps/report-mailer' },
        ]);
        const authStore = graph.nodes.find((n) => n.nodeLabel === 'auth-store');
        expect(authStore.appDir).toBe('apps/expense-tracker');
        expect(authStore.treeId).toBe('tree_1');
        expect(graph.bridges).toEqual([
            {
                fileName: 'bridge-auth-session.ts',
                path: 'bridge/bridge-auth-session.ts',
                treeIds: ['tree_1', 'tree_2'],
                exports: ['Session', 'readSession'],
                validated: true,
            },
        ]);
        const cross = graph.edges.find((e) => e.kind === 'cross-tree');
        expect(cross).toMatchObject({
            source: 'A1',
            target: 'B1',
            sourceTreeId: 'tree_1',
            targetTreeId: 'tree_2',
            payloadType: 'auth-session',
            payloadLabel: 'Login session',
        });
    });
    it('documents the apps and their connection in the README', () => {
        const readme = fs.readFileSync(path.join(out(), 'README.md'), 'utf-8');
        expect(readme).toContain('**Tree Mode:** this project holds **2 separate apps**');
        expect(readme).toContain('├── expense-tracker/');
        expect(readme).toContain('└── report-mailer/');
        expect(readme).toContain('├── bridge/');
        expect(readme).toContain('└── bridge-auth-session.ts');
        expect(readme).toContain('## 🔗 Cross-App Connections (Tree Mode)');
        expect(readme).toContain('**bridge-auth-session** — `Login session`: **Expense Tracker** → **Report Mailer**');
        expect(readme).toContain('cd apps/report-mailer && npm install && npm run dev');
    });
    it('separates two trees into their own apps even with no cross-app connection', async () => {
        const t1 = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-notrees-'));
        try {
            const res = await scaffolder.scaffold({
                projectName: 'no-bridge-project',
                targetOS: 'linux',
                files: twoAppFiles().filter((f) => !f.isBridge),
                nodes: treeNodes,
                edges: [],
                trees: trees,
                outputDir: t1,
            });
            expect(fs.existsSync(path.join(res.outputPath, 'apps', 'expense-tracker', 'index.ts'))).toBe(true);
            expect(fs.existsSync(path.join(res.outputPath, 'apps', 'report-mailer', 'index.ts'))).toBe(true);
            expect(fs.existsSync(path.join(res.outputPath, 'bridge'))).toBe(false);
            const readme = fs.readFileSync(path.join(res.outputPath, 'README.md'), 'utf-8');
            expect(readme).not.toContain('## 🔗 Cross-App Connections');
        }
        finally {
            fs.rmSync(t1, { recursive: true, force: true });
        }
    });
    it('routes a file that only knows its treeId into that app (pre-layout build)', async () => {
        const t1 = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-scaffold-stamp-'));
        try {
            const legacy = twoAppFiles().map((f) => ({ ...f, appDir: undefined }));
            const res = await scaffolder.scaffold({
                projectName: 'legacy-layout-project',
                targetOS: 'linux',
                files: legacy,
                nodes: treeNodes,
                edges: treeEdges,
                trees: trees,
                outputDir: t1,
            });
            expect(fs.existsSync(path.join(res.outputPath, 'apps', 'expense-tracker', 'src', 'auth-store', 'auth-store.ts'))).toBe(true);
            expect(fs.existsSync(path.join(res.outputPath, 'apps', 'report-mailer', 'src', 'report-sender', 'report-sender.ts'))).toBe(true);
        }
        finally {
            fs.rmSync(t1, { recursive: true, force: true });
        }
    });
});
// Language coverage: every core desktop/server language gets a real entry point
// and a project config instead of silently falling back to the TS scaffold.
describe('PerFileScaffolder entry point + config per language', () => {
    const cases = [
        { lang: 'java', ext: 'java', entry: 'Main.java', config: 'Makefile', marker: /public class Main/ },
        { lang: 'c', ext: 'c', entry: 'main.c', config: 'Makefile', marker: /int main\(int argc, char \*\*argv\)/ },
        { lang: 'cpp', ext: 'cpp', entry: 'main.cpp', config: 'Makefile', marker: /std::cout/ },
        { lang: 'csharp', ext: 'cs', entry: 'Program.cs', config: 'app.csproj', marker: /static void Main/ },
        { lang: 'php', ext: 'php', entry: 'index.php', config: 'composer.json', marker: /^<\?php/m },
        { lang: 'ruby', ext: 'rb', entry: 'main.rb', config: 'Gemfile', marker: /require_relative/ },
        { lang: 'swift', ext: 'swift', entry: 'main.swift', config: 'Makefile', marker: /print\("/ },
        { lang: 'kotlin', ext: 'kt', entry: 'Main.kt', config: 'Makefile', marker: /fun main\(\)/ },
    ];
    for (const c of cases) {
        it(`scaffolds ${c.lang}: ${c.entry} + ${c.config}`, async () => {
            const dir = fs.mkdtempSync(path.join(os.tmpdir(), `vaca-scaffold-${c.lang}-`));
            try {
                const gen = [{
                        fileName: `core.${c.ext}`,
                        language: c.lang,
                        code: '// node module',
                        nodeId: 'n1',
                        nodeLabel: `core.${c.ext}`,
                        dependencies: [],
                        exports: [],
                        errors: [],
                        validated: true,
                    }];
                const res = await scaffolder.scaffold({
                    projectName: `${c.lang}-app`,
                    targetOS: 'linux',
                    files: gen,
                    nodes: [],
                    edges: [],
                    outputDir: dir,
                });
                const out = res.outputPath;
                expect(fs.existsSync(path.join(out, c.entry))).toBe(true);
                expect(fs.existsSync(path.join(out, c.config))).toBe(true);
                expect(fs.readFileSync(path.join(out, c.entry), 'utf-8')).toMatch(c.marker);
                // The node file is written under src/<node>/ and no TS index.ts leaks in.
                expect(fs.existsSync(path.join(out, 'index.ts'))).toBe(false);
            }
            finally {
                fs.rmSync(dir, { recursive: true, force: true });
            }
        });
    }
});
// Compiled languages: the entry point must wire the generated node modules in,
// not just print a banner. Only a no-argument function read out of the node
// file is ever called — nothing is guessed.
describe('compiled-language entry points call their node modules', () => {
    function nodeFile(lang, ext, name, code) {
        return {
            fileName: `${name}.${ext}`,
            language: lang,
            code,
            nodeId: `n-${name}`,
            nodeLabel: `${name}.${ext}`,
            dependencies: [],
            exports: [],
            errors: [],
            validated: true,
        };
    }
    async function entryFor(lang, ext, name, code, entry) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), `vaca-wire-${lang}-`));
        try {
            const res = await scaffolder.scaffold({
                projectName: `${lang}-wire-app`,
                targetOS: 'linux',
                files: [nodeFile(lang, ext, name, code)],
                nodes: [],
                edges: [],
                outputDir: dir,
            });
            return fs.readFileSync(path.join(res.outputPath, entry), 'utf-8');
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    }
    const cases = [
        {
            lang: 'c', ext: 'c', entry: 'main.c',
            // `run` is preferred over the earlier non-conventional helper.
            code: 'int helper(void) { return 1; }\nint run(void) { return 0; }\n',
            want: [/extern int run\(void\);/, /\(void\)run\(\);/],
        },
        {
            lang: 'cpp', ext: 'cpp', entry: 'main.cpp',
            code: 'int helper() { return 1; }\nint run() { return 0; }\n',
            want: [/extern int run\(void\);/, /\(void\)run\(\);/],
        },
        {
            lang: 'go', ext: 'go', entry: 'main.go',
            code: 'package game\n\nfunc NewBoard(w int) *Board { return nil }\nfunc Run() { }\n',
            // A call with no result is a bare statement; one with a result is discarded.
            want: [/^\s*pkg0\.Run\(\)$/m, /import pkg0 /],
        },
        {
            lang: 'rust', ext: 'rs', entry: 'main.rs',
            code: 'pub struct Board { pub w: usize }\npub fn build(w: usize) -> Board { Board { w } }\npub fn run() { }\n',
            want: [/let _ = core::run\(\);/],
        },
        {
            lang: 'java', ext: 'java', entry: 'Main.java',
            code: 'public class Player {\n  private int x;\n  public Player(int x) { this.x = x; }\n  public static void run() { }\n  public void move(int d) { x += d; }\n}\n',
            want: [/Class<\?> _module0 = Player\.class;/, /Player\.run\(\);/],
        },
        {
            lang: 'csharp', ext: 'cs', entry: 'Program.cs',
            code: 'public class Engine\n{\n    public static void Run() { }\n    public void Tick() { }\n}\n',
            want: [/var _module0 = typeof\(Engine\);/, /Engine\.Run\(\);/],
        },
        {
            lang: 'swift', ext: 'swift', entry: 'main.swift',
            code: 'struct Board {\n    static func run() { }\n    func place() { }\n}\n',
            want: [/^_ = Board\.self$/m, /^Board\.run\(\)$/m],
        },
        {
            lang: 'kotlin', ext: 'kt', entry: 'Main.kt',
            code: 'class Board {\n    fun place() { }\n}\nfun run() { }\n',
            want: [/val _module0 = Board::class/, /^\s+run\(\)$/m],
        },
        {
            lang: 'python', ext: 'py', entry: 'main.py',
            code: 'def helper(x):\n    return x\n\ndef main():\n    print("hi")\n',
            // Qualified with the module: every CLI node calls its entry `main`, so a
            // bare `main()` would run one node's work several times over the others.
            want: [/^import core\b/m, /^\s+core\.main\(\)$/m],
        },
    ];
    for (const c of cases) {
        it(`wires the node module into ${c.lang}`, async () => {
            const entry = await entryFor(c.lang, c.ext, 'core', c.code, c.entry);
            for (const w of c.want)
                expect(entry).toMatch(w);
        });
    }
    it('never guesses: a module with no callable entry is left unwired', async () => {
        const cEntry = await entryFor('c', 'c', 'core', 'int add(int a, int b) { return a + b; }\n', 'main.c');
        expect(cEntry).not.toMatch(/add/);
        expect(cEntry).toMatch(/none exposes a no-argument entry function/);
        // A Java class with only instance methods is referenced, never called.
        const javaEntry = await entryFor('java', 'java', 'core', 'public class Player {\n  public void move(int d) { }\n}\n', 'Main.java');
        expect(javaEntry).toMatch(/Class<\?> _module0 = Player\.class;/);
        expect(javaEntry).not.toMatch(/Player\.move/);
    });
    it('references (but does not call) a Rust module whose only fn takes arguments', async () => {
        const entry = await entryFor('rust', 'rs', 'core', 'pub fn build(w: usize) -> usize { w }\n', 'main.rs');
        expect(entry).toMatch(/let _ = core::build;/);
        expect(entry).not.toMatch(/core::build\(\)/);
    });
    it('extracts only zero-argument declarations, and never C library names', () => {
        expect(goNoArgFuncs('package p\nfunc Run() {}\nfunc Add(a int) int { return a }\n').map((f) => f.name)).toEqual(['Run']);
        expect(rustNoArgFuncs('pub fn run() {}\npub fn build(x: u8) {}\n').map((f) => f.name)).toEqual(['run']);
        expect(rustPublicFns('pub fn build(x: u8) {}\n')).toEqual(['build']);
        expect(cNoArgFuncs('int printf(void) { return 0; }\nint run(void) { return 0; }\n', 'c').map((f) => f.name)).toEqual(['run']);
        expect(javaStaticNoArgFuncs('public static void main(String[] args) {}\npublic static void run() {}\n').map((f) => f.name)).toEqual(['run']);
        expect(csharpStaticNoArgFuncs('static void Main(string[] args) {}\npublic static void Run() {}\n').map((f) => f.name)).toEqual(['Run']);
        expect(swiftNoArgFuncs('struct B {\n    static func go() {}\n}\nfunc help(x: Int) {}\nfunc run() {}\n').map((f) => f.name)).toEqual(['run', 'go']);
        expect(kotlinTopLevelFuncs('fun main() {}\nfun run() {}\nfun helper(x: Int) {}\n').map((f) => f.name).sort()).toEqual(['main', 'run']);
    });
    it('plans nothing for a language it has no wiring for', () => {
        expect(planModuleWiring('php', '<?php\nfunction run() {}\n', 'core', 0)).toEqual({
            declarations: [],
            references: [],
            calls: [],
        });
    });
    it('calls only ZERO-argument Python defs, never a def that needs arguments', () => {
        expect(pythonNoArgFuncs('def run():\n    pass\n\ndef convert(v, unit):\n    return v\n').map((f) => f.name))
            .toEqual(['run']);
        expect(pythonModuleName('arg-parser')).toBe('arg_parser');
        expect(pythonModuleName('2d-renderer')).toBe('_2d_renderer');
    });
    it('calls only ZERO-argument Ruby defs, in either paren style', () => {
        expect(rubyNoArgFuncs('def run\n  puts 1\nend\n\ndef convert(v, unit)\n  v\nend\n').map((f) => f.name))
            .toEqual(['run']);
        expect(rubyNoArgFuncs('def start()\nend\ndef main(input_file, output_file)\nend\n').map((f) => f.name))
            .toEqual(['start']);
        // A `def` comment must not be mistaken for a definition.
        expect(rubyNoArgFuncs('# def fake\ndef real\nend\n').map((f) => f.name)).toEqual(['real']);
        expect(planModuleWiring('ruby', 'def run\n  puts 1\nend\n', 'core', 0).calls).toEqual(['run()']);
    });
    it('wires a Ruby node that exposes a zero-argument entry into main.rb', async () => {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-ruby-run-'));
        try {
            const res = await scaffolder.scaffold({
                projectName: 'ruby runner',
                targetOS: 'linux',
                files: [{
                        fileName: 'runner.rb',
                        language: 'ruby',
                        code: 'def run\n  puts "ran"\nend\n',
                        nodeId: 'n1',
                        nodeLabel: 'runner',
                        dependencies: [],
                        exports: ['run'],
                        errors: [],
                        validated: true,
                    }],
                nodes: [],
                edges: [],
                outputDir: dir,
            });
            const entry = fs.readFileSync(path.join(res.outputPath, 'main.rb'), 'utf-8');
            expect(entry).toContain("require_relative 'src/runner/runner.rb'");
            expect(entry).toMatch(/^run\(\)$/m);
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
    it('calls a repeated Ruby entry name only once (no per-file namespace)', async () => {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-ruby-dup-'));
        try {
            const node = (name) => ({
                fileName: `${name}.rb`,
                language: 'ruby',
                code: 'def run\n  puts "ran"\nend\n',
                nodeId: name,
                nodeLabel: name,
                dependencies: [],
                exports: ['run'],
                errors: [],
                validated: true,
            });
            const res = await scaffolder.scaffold({
                projectName: 'ruby dup',
                targetOS: 'linux',
                files: [node('alpha'), node('beta')],
                nodes: [],
                edges: [],
                outputDir: dir,
            });
            const entry = fs.readFileSync(path.join(res.outputPath, 'main.rb'), 'utf-8');
            expect(entry.match(/^run\(\)$/gm)?.length).toBe(1);
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
});
// ── Generated apps must be RUNNABLE, not just structurally tidy ──────────────
describe('Python packages are importable (hyphenated node labels)', () => {
    let pyOut = '';
    const pyFile = {
        fileName: 'arg-parser.py',
        language: 'python',
        code: 'import sys\n\ndef main():\n    print("converted")\n',
        nodeId: 'n1',
        nodeLabel: 'arg-parser',
        dependencies: [],
        exports: ['main'],
        errors: [],
        validated: true,
    };
    beforeAll(async () => {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-py-args-'));
        const res = await scaffolder.scaffold({
            projectName: 'py temp converter',
            targetOS: 'linux',
            files: [pyFile],
            nodes: [],
            edges: [],
            outputDir: dir,
        });
        pyOut = res.outputPath;
    });
    it('writes the module under an underscored name, never `arg-parser.py`', () => {
        expect(fs.existsSync(path.join(pyOut, 'src/arg_parser/arg_parser.py'))).toBe(true);
        expect(fs.existsSync(path.join(pyOut, 'src/arg_parser/arg-parser.py'))).toBe(false);
    });
    it('re-exports from the importable module name', () => {
        const init = fs.readFileSync(path.join(pyOut, 'src/arg_parser/__init__.py'), 'utf-8');
        expect(init).toContain('from .arg_parser import *');
        expect(init).not.toContain('.arg-parser');
    });
    it('imports the module from main.py and RUNS its entry function', () => {
        const main = fs.readFileSync(path.join(pyOut, 'main.py'), 'utf-8');
        expect(main).toContain('import arg_parser');
        expect(main).toContain('arg_parser.main()');
    });
    const hasPython = (() => {
        try {
            execFileSync('python3', ['--version'], { stdio: 'ignore' });
            return true;
        }
        catch {
            return false;
        }
    })();
    it.skipIf(!hasPython)('compiles and imports with the real interpreter (SyntaxError regression)', () => {
        execFileSync('python3', ['-m', 'py_compile', path.join(pyOut, 'main.py')], { stdio: 'pipe' });
        execFileSync('python3', ['-m', 'py_compile', path.join(pyOut, 'src/arg_parser/__init__.py')], { stdio: 'pipe' });
        // `import arg_parser` must resolve the package and its __init__ re-export.
        const out = execFileSync('python3', ['-c', 'import sys; sys.path.insert(0, "src"); import arg_parser; arg_parser.main()'], {
            cwd: pyOut,
            encoding: 'utf-8',
        });
        expect(out).toContain('converted');
    });
});
// A node file that already IS the program must not be duplicated by the
// scaffold's own entry point (C/C++ link every unit into one binary).
describe('a C node that defines main() becomes the program entry', () => {
    async function scaffoldC(files) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-c-entry-'));
        const res = await scaffolder.scaffold({
            projectName: 'c word counter',
            targetOS: 'linux',
            files,
            nodes: [],
            edges: [],
            outputDir: dir,
        });
        return res.outputPath;
    }
    const program = {
        fileName: 'word-counter.c',
        language: 'c',
        code: '#include <stdio.h>\n\nint count_words(void) { return 3; }\n\nint main(int argc, char **argv) {\n  (void)argc; (void)argv;\n  printf("words: %d\\n", count_words());\n  return 0;\n}\n',
        nodeId: 'n1',
        nodeLabel: 'word-counter',
        dependencies: [],
        exports: [],
        errors: [],
        validated: true,
    };
    it('emits NO second main file and compiles every source it finds', async () => {
        const out = await scaffoldC([program]);
        expect(fs.existsSync(path.join(out, 'main.c'))).toBe(false);
        const makefile = fs.readFileSync(path.join(out, 'Makefile'), 'utf-8');
        expect(makefile).toContain('SRCS := $(wildcard *.c) $(wildcard src/*/*.c)');
        expect(makefile).not.toContain('main.c ');
        expect(fs.readFileSync(path.join(out, 'README.md'), 'utf-8')).toContain('Program entry point');
    });
    const hasGcc = (() => {
        try {
            execFileSync('gcc', ['--version'], { stdio: 'ignore' });
            return true;
        }
        catch {
            return false;
        }
    })();
    it.skipIf(!hasGcc)('links and RUNS the promoted node file (duplicate-main regression)', async () => {
        const out = await scaffoldC([program]);
        const src = path.join(out, 'src/word-counter/word-counter.c');
        const bin = path.join(out, 'app');
        // Exactly the sources the Makefile builds: the promoted node, no main.c.
        execFileSync('gcc', ['-std=c11', '-o', bin, src], { stdio: 'pipe' });
        expect(execFileSync(bin, { encoding: 'utf-8' })).toContain('words: 3');
    });
    it('keeps the scaffold’s own entry point when no node defines main()', async () => {
        const helper = { ...program, code: 'int count_words(void) { return 3; }\n' };
        const out = await scaffoldC([helper]);
        expect(fs.existsSync(path.join(out, 'main.c'))).toBe(true);
        expect(fs.readFileSync(path.join(out, 'Makefile'), 'utf-8')).toContain('SRCS := main.c');
    });
});
// The same collision in the languages whose entry file the toolchain does NOT
// require to be named in a fixed way (C#, Kotlin) — measured live: the C#
// expense tracker failed `dotnet build` with CS0101 (two `class Program`) and
// CS0111 (two `Main`), because its cli node IS the program.
describe('C#/Kotlin nodes that own the entry point replace the scaffold’s own', () => {
    async function scaffoldOne(language, fileName, code) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), `vaca-entry-${language}-`));
        const file = {
            fileName,
            language,
            code,
            nodeId: 'n1',
            nodeLabel: fileName.replace(/\.[a-z]+$/, ''),
            dependencies: [],
            exports: [],
            errors: [],
            validated: true,
        };
        const res = await scaffolder.scaffold({
            projectName: `${language} entry app`,
            targetOS: 'linux',
            files: [file],
            nodes: [],
            edges: [],
            outputDir: dir,
        });
        return res.outputPath;
    }
    it('C#: a node with `static Main` suppresses Program.cs', async () => {
        const cs = [
            'using System;',
            'public class Program {',
            '    public static void Main(string[] args) { Console.WriteLine("ok"); }',
            '}',
        ].join('\n');
        const out = await scaffoldOne('csharp', 'cli.cs', cs);
        expect(fs.existsSync(path.join(out, 'Program.cs'))).toBe(false);
        expect(fs.existsSync(path.join(out, 'src/cli/cli.cs'))).toBe(true);
        // The csproj globs its sources, so nothing else has to change.
        expect(fs.readFileSync(path.join(out, 'app.csproj'), 'utf-8')).toContain('Microsoft.NET.Sdk');
    });
    it('C#: an ordinary class keeps the scaffold entry point', async () => {
        const out = await scaffoldOne('csharp', 'store.cs', 'public class Store { public int Total() { return 0; } }\n');
        expect(fs.existsSync(path.join(out, 'Program.cs'))).toBe(true);
    });
    it('Kotlin: a node with `fun main()` suppresses Main.kt and the Makefile globs', async () => {
        const out = await scaffoldOne('kotlin', 'cli.kt', 'fun main() {\n    println("ok")\n}\n');
        expect(fs.existsSync(path.join(out, 'Main.kt'))).toBe(false);
        const makefile = fs.readFileSync(path.join(out, 'Makefile'), 'utf-8');
        expect(makefile).toContain('SRCS := $(wildcard *.kt) $(wildcard src/*/*.kt)');
        expect(makefile).not.toContain('Main.kt ');
    });
    it('two Kotlin owners still suppress Main.kt (never add a third competing entry)', async () => {
        // Measured live: three nodes each with `fun main()` plus the scaffold's
        // Main.kt failed kotlinc — the ambiguous `main()` CALL in Main.kt was the
        // scaffold's own contribution to the failure. A multi-node generation
        // defect is the gate's to report; the scaffold must not add its own error.
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-entry-kotlin2-'));
        const mk = (name, code) => ({
            fileName: `${name}.kt`, language: 'kotlin', code, nodeId: `n-${name}`, nodeLabel: `${name}.kt`,
            dependencies: [], exports: [], errors: [], validated: true,
        });
        const res = await scaffolder.scaffold({
            projectName: 'kotlin two owners',
            targetOS: 'linux',
            files: [
                mk('cli', 'fun main() {\n    println("a")\n}\n'),
                mk('report', 'fun main() {\n    println("b")\n}\n'),
            ],
            nodes: [],
            edges: [],
            outputDir: dir,
        });
        expect(fs.existsSync(path.join(res.outputPath, 'Main.kt'))).toBe(false);
        expect(fs.readFileSync(path.join(res.outputPath, 'Makefile'), 'utf-8'))
            .toContain('SRCS := $(wildcard *.kt)');
    });
});
