import { describe, it, expect } from 'vitest';
import { applyContentDrivenImportFix, applyDeterministicExportNameFix, applyDeterministicLocalCollisionFix, applyDeterministicMissingExportFix, applyDeterministicMissingReturnFix, applyDeterministicPartialObjectFix, applyDeterministicPrivateAccessFix, applyDeterministicSiblingPathFix, applyDeterministicVoidReturnFix, normalizeImportExtensions, stripCircularSelfImports, stripPhantomPackageImports, tscErrorPos, } from './deterministicFixers.js';
// NOTE: every error string in this file uses the FILEGENERATOR error format
// (`TSxxxx: message (line N)`, no `error ` prefix, line at the END) — the
// whole point of the shared module is format tolerance, so codePlanner's
// `(line,col): error TSxxxx:`-prefixed strings AND fileGenerator's suffixed
// strings must both parse.
describe('tscErrorPos (format tolerance)', () => {
    it('parses codePlanner format (line,col prefix)', () => {
        expect(tscErrorPos('src/a.ts(1,62): error TS2307: Cannot find module \'../controllers\'.')).toEqual({ line: 1, col: 62 });
    });
    it('parses fileGenerator format (suffixed line)', () => {
        expect(tscErrorPos('TS2307: Cannot find module \'../controllers\' (line 3)')).toEqual({ line: 3 });
        expect(tscErrorPos('TS2304: Cannot find name \'X\' (line 9)')).toEqual({ line: 9 });
    });
    it('returns null for non-positional strings', () => {
        expect(tscErrorPos('no position here')).toBeNull();
    });
});
describe('applyDeterministicExportNameFix (TS2724/TS2614/TS2305 name mismatch)', () => {
    it('rewrites the imported member to the name tsc suggests (fileGenerator format)', () => {
        const content = "import { GameState } from '../game-state/game-state';\nexport class GameController {}\n";
        const errs = [
            `TS2724: '"../game-state/game-state.ts"' has no exported member named 'GameState'. Did you mean 'gameState'? (line 1)`,
        ];
        const patched = applyDeterministicExportNameFix(content, errs);
        expect(patched).toContain("import { gameState } from '../game-state/game-state';");
        // The body must be untouched — only the import binding is rewritten.
        expect(patched).toContain('export class GameController {}');
    });
    it('preserves a local alias while fixing the imported name', () => {
        const content = "import { GameState as State } from '../state/state';\nexport const x = new State();\n";
        const errs = ["TS2724: Module has no exported member named 'GameState'. Did you mean 'gameState'? (line 1)"];
        const patched = applyDeterministicExportNameFix(content, errs);
        expect(patched).toContain("import { gameState as State } from '../state/state';");
        expect(patched).toContain('new State()');
    });
    it('handles codePlanner format and TS2305 too', () => {
        const content = "import { Todo } from './todo';\nexport const t = 1;\n";
        const errs = ["src/main.ts(1,10): error TS2305: Module '\"./todo\"' has no exported member 'Todo'. Did you mean 'todo'? "];
        const patched = applyDeterministicExportNameFix(content, errs);
        expect(patched).toContain("import { todo } from './todo';");
    });
    it('fixes several members in one import statement', () => {
        const content = "import { GameState, GameEngine } from '../core/core';\nexport const x = 1;\n";
        const errs = [
            "TS2724: Module has no exported member named 'GameState'. Did you mean 'gameState'? (line 1)",
            "TS2724: Module has no exported member named 'GameEngine'. Did you mean 'gameEngine'? (line 1)",
        ];
        const patched = applyDeterministicExportNameFix(content, errs);
        expect(patched).toContain('import { gameState, gameEngine } from');
    });
    it('returns null when tsc gives no suggestion', () => {
        const content = "import { Nope } from './x';\n";
        const errs = ["TS2614: Module 'x' has no exported member 'Nope'. ONLY these are exported: a, b."];
        expect(applyDeterministicExportNameFix(content, errs)).toBeNull();
    });
    it('returns null when the suggestion is identical (nothing to do)', () => {
        const content = "import { same } from './x';\n";
        const errs = ["TS2305: Module has no exported member 'same'. Did you mean 'same'? (line 1)"];
        expect(applyDeterministicExportNameFix(content, errs)).toBeNull();
    });
    it('returns null when the name is not imported by this file', () => {
        const content = "import { Other } from './x';\nexport const y = 1;\n";
        const errs = ["TS2724: Module has no exported member named 'GameState'. Did you mean 'gameState'? (line 1)"];
        expect(applyDeterministicExportNameFix(content, errs)).toBeNull();
    });
});
describe('applyDeterministicSiblingPathFix', () => {
    it('fixes a wrong `../` specifier for a same-dir sibling (fileGenerator format)', () => {
        const content = "import { Board } from '../board';\nexport const x = 1;\n";
        const files = [
            { path: 'src/game/game.ts' },
            { path: 'src/board/board.ts' },
        ];
        const errs = ["TS2307: Cannot find module '../board' (line 1)"];
        const patched = applyDeterministicSiblingPathFix(content, 'src/game/game.ts', files, errs);
        expect(patched).toContain("from '../board/board'");
        expect(patched).not.toContain("'../board'");
    });
    it('equates underscore labels with hyphenated scaffold files (core_engine → core-engine)', () => {
        // Canvas layout: node LABELS are underscored (input_handler) but
        // labelToFileName() hyphenates the real file (input-handler.ts). The model
        // writes the underscored form; the fixer must resolve it to the real file.
        const content = "import { InputHandler } from '../input_handler/input_handler.ts';\nexport const x = 1;\n";
        const files = [
            { path: 'src/game/game.ts' },
            { path: 'src/input-handler/input-handler.ts' },
        ];
        const errs = ["TS2307: Cannot find module '../input_handler/input_handler.ts' (line 1)"];
        const patched = applyDeterministicSiblingPathFix(content, 'src/game/game.ts', files, errs);
        expect(patched).toContain("from '../input-handler/input-handler'");
        expect(patched).not.toContain('input_handler');
    });
    it('fixes a .ts-extension specifier on a sibling path', () => {
        const content = "import { save } from '../db/db.ts';\nexport const x = 1;\n";
        const files = [{ path: 'src/app/app.ts' }, { path: 'src/db/db.ts' }];
        const errs = ["TS2307: Cannot find module '../db/db.ts' (line 1)"];
        const patched = applyDeterministicSiblingPathFix(content, 'src/app/app.ts', files, errs);
        expect(patched).toContain("from '../db/db'");
    });
    it('returns null when ambiguous (two files share the basename)', () => {
        const content = "import { X } from '../mod';\nexport const x = 1;\n";
        const files = [{ path: 'src/a/mod.ts' }, { path: 'src/b/mod.ts' }];
        const errs = ["TS2307: Cannot find module '../mod' (line 1)"];
        expect(applyDeterministicSiblingPathFix(content, 'src/a/self.ts', files, errs)).toBeNull();
    });
    it('returns null when no file matches the basename (unresolved → LLM)', () => {
        const content = "import { Zebra } from '../zebra';\nZebra();\n";
        const files = [{ path: 'src/self/self.ts' }];
        const errs = ["TS2307: Cannot find module '../zebra' (line 1)"];
        expect(applyDeterministicSiblingPathFix(content, 'src/self/self.ts', files, errs)).toBeNull();
    });
});
describe('applyDeterministicMissingExportFix', () => {
    it('adds export to the CAUSING sibling file', () => {
        const files = [
            { path: 'src/server/server.ts', content: "import { Note } from '../note/note.ts';\nexport function go() { return new Note(); }\n" },
            { path: 'src/note/note.ts', content: 'interface Note { id: number; title: string }\nexport class NoteStore {}\n' },
        ];
        const errs = ["TS2459: Module '\"../note/note.ts\"' declares 'Note' locally, but it is not exported (line 1)"];
        const fixed = applyDeterministicMissingExportFix('src/server/server.ts', files, errs);
        expect(fixed.path).toBe('src/note/note.ts');
        expect(fixed.content).toContain('export interface Note');
    });
    it('returns null when the declaration is already exported', () => {
        const files = [
            { path: 'src/server/server.ts', content: "import { Note } from '../note/note.ts';\n" },
            { path: 'src/note/note.ts', content: 'export interface Note { id: number }\n' },
        ];
        const errs = ["TS2459: Module '\"../note/note.ts\"' declares 'Note' locally, but it is not exported (line 1)"];
        expect(applyDeterministicMissingExportFix('src/server/server.ts', files, errs)).toBeNull();
    });
});
describe('applyContentDrivenImportFix', () => {
    it('inserts an import when exactly one sibling exports the missing name', () => {
        const content = "export function render() { return new Widget(); }\n";
        const files = [
            { path: 'src/app/app.ts', content },
            { path: 'src/widget/widget.ts', content: 'export class Widget {}\n' },
        ];
        const errs = ["TS2304: Cannot find name 'Widget' (line 1)"];
        const patched = applyContentDrivenImportFix(content, 'src/app/app.ts', files, errs);
        expect(patched).toContain("import { Widget } from '../widget/widget';");
    });
    it('skips names declared locally or already imported', () => {
        const content = "export class Widget {}\nexport function render() { return new Widget(); }\n";
        const files = [
            { path: 'src/app/app.ts', content },
            { path: 'src/widget/widget.ts', content: 'export class Widget {}\n' },
        ];
        const errs = ["TS2304: Cannot find name 'Widget' (line 2)"];
        expect(applyContentDrivenImportFix(content, 'src/app/app.ts', files, errs)).toBeNull();
    });
    it('returns null when multiple siblings export the name (ambiguous)', () => {
        const content = "export function render() { return new Widget(); }\n";
        const files = [
            { path: 'src/app/app.ts', content },
            { path: 'src/a/widget.ts', content: 'export class Widget {}\n' },
            { path: 'src/b/widget.ts', content: 'export class Widget {}\n' },
        ];
        const errs = ["TS2304: Cannot find name 'Widget' (line 1)"];
        expect(applyContentDrivenImportFix(content, 'src/app/app.ts', files, errs)).toBeNull();
    });
});
describe('applyDeterministicPartialObjectFix', () => {
    it('inserts missing primitive members at a single-line partial-object call site', () => {
        const content = "addNote({ title: 'x' });\n";
        const files = [
            { path: 'src/store/store.ts', content: 'interface Note {\n  id: number;\n  title: string;\n  content: string;\n}\nexport function addNote(n: Note): void {}\n' },
            { path: 'src/app/app.ts', content },
        ];
        const errs = ["TS2345: Argument of type '{ title: string; }' is not assignable to parameter of type 'Note' (line 1)"];
        const patched = applyDeterministicPartialObjectFix(content, 'src/app/app.ts', files, errs);
        expect(patched).toContain("addNote({ title: 'x', id: 0, content: '' });");
    });
    it('returns null when a missing member is complex-typed (no safe placeholder)', () => {
        const content = "addNote({ title: 'x' });\n";
        const files = [
            { path: 'src/store/store.ts', content: 'interface Note {\n  title: string;\n  created: Date;\n}\nexport function addNote(n: Note): void {}\n' },
            { path: 'src/app/app.ts', content },
        ];
        const errs = ["TS2345: Argument of type '{ title: string; }' is not assignable to parameter of type 'Note' (line 1)"];
        expect(applyDeterministicPartialObjectFix(content, 'src/app/app.ts', files, errs)).toBeNull();
    });
});
describe('applyDeterministicMissingReturnFix / applyDeterministicVoidReturnFix', () => {
    it('inserts a default return before the closing brace (fileGenerator format, no column)', () => {
        const content = "export function count(): number {\n  return 1;\n}\n\nexport function total(): number {\n  const t = 5;\n}\n";
        const errs = ["TS2355: A function whose declared type is neither 'undefined', 'void', nor 'any' must return a value (line 5)"];
        const patched = applyDeterministicMissingReturnFix(content, errs);
        expect(patched).toContain('  return 0;');
    });
    it('rewrites a literal return in a void function to bare return', () => {
        const content = "export function log(): void {\n  console.log('hi');\n  return 42;\n}\n";
        const errs = ["TS2322: Type 'number' is not assignable to type 'void' (line 3)"];
        const patched = applyDeterministicVoidReturnFix(content, errs);
        expect(patched).toContain('  return;');
        expect(patched).not.toContain('return 42;');
    });
    it('leaves non-literal returns alone (could be side-effecting)', () => {
        const content = "export function log(): void {\n  return compute();\n}\n";
        const errs = ["TS2322: Type 'number' is not assignable to type 'void' (line 2)"];
        expect(applyDeterministicVoidReturnFix(content, errs)).toBeNull();
    });
});
describe('applyDeterministicLocalCollisionFix', () => {
    it('drops an imported member that collides with a local declaration', () => {
        const content = "import { Widget } from '../widget/widget.ts';\nexport class Widget {}\nexport const x = new Widget();\n";
        const errs = ["TS2451: Cannot redeclare block-scoped variable 'Widget' (line 2)"];
        const patched = applyDeterministicLocalCollisionFix(content, errs);
        expect(patched).not.toContain('import { Widget }');
    });
});
describe('stripPhantomPackageImports', () => {
    it('removes invented npm imports but keeps builtins and installed packages', () => {
        const content = "import fs from 'fs';\nimport { render } from 'react';\nimport csv from 'csv-parser';\nexport const x = 1;\n";
        const stripped = stripPhantomPackageImports(content);
        expect(stripped).toContain("import fs from 'fs';");
        expect(stripped).toContain("import { render } from 'react';");
        expect(stripped).not.toContain('csv-parser');
    });
});
describe('normalizeImportExtensions', () => {
    it('strips a resolvable .ts extension from a relative import', () => {
        const content = "import { save } from '../db/db.ts';\nexport const x = 1;\n";
        const files = [{ path: 'src/db/db.ts' }];
        const patched = normalizeImportExtensions(content, 'src/app/app.ts', files);
        expect(patched).toContain("from '../db/db'");
    });
    it('leaves an unresolvable extension alone', () => {
        const content = "import { save } from '../missing/missing.ts';\nexport const x = 1;\n";
        const files = [{ path: 'src/db/db.ts' }];
        expect(normalizeImportExtensions(content, 'src/app/app.ts', files)).toBeNull();
    });
});
describe('applyDeterministicPrivateAccessFix', () => {
    it('promotes a private field in the declaring sibling (fileGenerator format)', () => {
        const declaring = `export class PomodoroTimer {\n  private state: string = 'stopped';\n\n  start(): void {}\n}\n`;
        const caller = `import { PomodoroTimer } from '../core-engine/core-engine.ts';\nexport function render() {\n  const t = new PomodoroTimer();\n  console.log(t.state);\n}\n`;
        const files = [
            { path: 'src/core-engine/core-engine.ts', content: declaring },
            { path: 'src/ui-screens/ui-screens.ts', content: caller },
        ];
        const errs = ["TS2341: Property 'state' is private and only accessible within class 'PomodoroTimer'. (line 53)"];
        const fixed = applyDeterministicPrivateAccessFix('src/ui-screens/ui-screens.ts', files, errs);
        expect(fixed.path).toBe('src/core-engine/core-engine.ts');
        expect(fixed.content).toContain('public state: string');
        expect(fixed.content).not.toContain('private state');
    });
    it('keeps readonly when promoting', () => {
        const declaring = `export class Engine {\n  private readonly id: string = 'x';\n}\n`;
        const files = [
            { path: 'src/engine/engine.ts', content: declaring },
        ];
        const errs = ["TS2341: Property 'id' is private and only accessible within class 'Engine'. (line 5)"];
        const fixed = applyDeterministicPrivateAccessFix('src/main/main.ts', files, errs);
        expect(fixed.content).toContain('public readonly id: string');
    });
    it('does not promote a private method (only fields)', () => {
        const declaring = `export class Engine {\n  private run(): void {}\n}\n`;
        const files = [
            { path: 'src/engine/engine.ts', content: declaring },
        ];
        const errs = ["TS2341: Property 'run' is private and only accessible within class 'Engine'. (line 5)"];
        expect(applyDeterministicPrivateAccessFix('src/main/main.ts', files, errs)).toBeNull();
    });
    it('returns null when the member is not declared in any file', () => {
        const files = [
            { path: 'src/engine/engine.ts', content: 'export class Engine {}\n' },
        ];
        const errs = ["TS2341: Property 'ghost' is private and only accessible within class 'Engine'. (line 2)"];
        expect(applyDeterministicPrivateAccessFix('src/main/main.ts', files, errs)).toBeNull();
    });
});
describe('stripCircularSelfImports', () => {
    it('drops an import pointing at the file itself (phantom type)', () => {
        const content = `import { Request } from '../core-engine/core-engine.ts';

export class CoreEngine {
  private requests: Request[] = [];
}`;
        const stripped = stripCircularSelfImports(content, 'src/core-engine/core-engine.ts');
        expect(stripped).not.toBeNull();
        expect(stripped).not.toContain("from '../core-engine/core-engine.ts'");
        expect(stripped).toContain('private requests: Request[]');
    });
    it('keeps legitimate sibling imports untouched', () => {
        const content = `import { DataStore } from '../data-store/data-store.ts';
export class TimerCore { private data: DataStore; }`;
        const stripped = stripCircularSelfImports(content, 'src/timer-core/timer-core.ts');
        expect(stripped).toBeNull();
    });
    it('strips an explicit self-relative import too', () => {
        const content = `import { Board } from './board.ts';
export class Game {}`;
        const stripped = stripCircularSelfImports(content, 'src/board/board.ts');
        expect(stripped).not.toBeNull();
        expect(stripped).not.toContain("from './board.ts'");
    });
});
