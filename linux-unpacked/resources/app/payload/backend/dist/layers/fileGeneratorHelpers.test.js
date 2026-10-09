import { describe, it, expect } from 'vitest';
import { postProcessTsJsCode, buildImportStatement, verifyGeneratedCodeContracts, findLocalDeclaredNames, nodeTypeStem, buildTypeOwnershipSection } from '../layers/fileGenerator.js';
describe('postProcessTsJsCode (hardened import stripper)', () => {
    it('strips a standard leading import', () => {
        expect(postProcessTsJsCode("import { X } from '../a/a.ts';\n\nexport class Y {}")).toBe('export class Y {}');
    });
    it('strips no-space import{ statements', () => {
        expect(postProcessTsJsCode("import{X} from '../a/a.ts';\n\nexport class Y {}")).toBe('export class Y {}');
    });
    it('strips import type statements', () => {
        expect(postProcessTsJsCode("import type { Session } from '../t/t.ts';\n\nexport const x = 1;")).toBe('export const x = 1;');
    });
    it('strips mid-file column-0 imports (the wrong-sibling import failure mode)', () => {
        const code = "export class Y {}\n\nimport { X } from '../a/a.ts';\n";
        expect(postProcessTsJsCode(code)).toBe('export class Y {}');
    });
    it('strips multi-line block imports through the terminating semicolon', () => {
        const code = "import {\n  A,\n  B\n} from '../a/a.ts';\n\nexport class Y {}";
        expect(postProcessTsJsCode(code)).toBe('export class Y {}');
    });
    it('keeps leading comments and blank lines', () => {
        expect(postProcessTsJsCode("// header\nimport { X } from '../a/a.ts';\n\nexport const y = 1;"))
            .toBe('// header\n\nexport const y = 1;');
    });
    it('does not touch indented string content that merely contains the word import', () => {
        const code = "export const html = `\n  <div>hi</div>\n`;";
        expect(postProcessTsJsCode(code)).toBe(code);
    });
    it('does not eat column-0 template-literal content that starts with the word import', () => {
        const code = "export const html = `\nimport this is string content\nmore template lines\n`;\n";
        const out = postProcessTsJsCode(code);
        expect(out).toContain('import this is string content');
        expect(out).toContain('more template lines');
    });
    it('strips bare side-effect imports (no from clause)', () => {
        expect(postProcessTsJsCode("import './polyfill.js';\n\nexport const x = 1;")).toBe('export const x = 1;');
    });
});
describe('buildImportStatement (export-contract-aware)', () => {
    it('emits a named import when the dependency has named exports', () => {
        expect(buildImportStatement('data-store', { names: ['Data', 'DataStore'] }, 'typescript'))
            .toBe("import { Data, DataStore } from '../data-store/data-store.ts';");
    });
    it('emits a default import when the dependency only default-exports', () => {
        expect(buildImportStatement('timer-core', { names: [], defaultName: 'TimerCore' }, 'typescript'))
            .toBe("import TimerCore from '../timer-core/timer-core.ts';");
    });
    it('emits a side-effect import when the dependency exports nothing', () => {
        expect(buildImportStatement('config', { names: [] }, 'typescript'))
            .toBe("import '../config/config.ts';");
    });
    it('emits default + named imports when both exist', () => {
        expect(buildImportStatement('x', { names: ['A'], defaultName: 'X' }, 'typescript'))
            .toBe("import X, { A } from '../x/x.ts';");
    });
});
describe('verifyGeneratedCodeContracts (canvas post-write contract verifier)', () => {
    const exps = (names, defaultName) => ({ names, ...(defaultName ? { defaultName } : {}) });
    it('returns [] when there are no dependencies', () => {
        expect(verifyGeneratedCodeContracts("import { X } from '../x/x.ts';", 'typescript', [], new Map())).toEqual([]);
    });
    it('passes TS named imports of members the dependency actually exports', () => {
        const fileExports = new Map([['game', exps(['ChessGame', 'ChessBoard'])]]);
        expect(verifyGeneratedCodeContracts("import { ChessGame, ChessBoard } from '../game/game.ts';", 'typescript', ['game'], fileExports)).toEqual([]);
    });
    it('flags TS named imports of members the dependency never exports', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const out = verifyGeneratedCodeContracts("import { ChessGame, ChessBoard } from '../game/game.ts';", 'typescript', ['game'], fileExports);
        expect(out.length).toBe(1);
        expect(out[0]).toContain('ChessBoard');
        expect(out[0]).toContain('TS2614');
    });
    it('checks the named part of mixed default+named imports', () => {
        const fileExports = new Map([['game', exps(['ChessGame'], 'Game')]]);
        const out = verifyGeneratedCodeContracts("import Game, { ChessBoard } from '../game/game.ts';", 'typescript', ['game'], fileExports);
        expect(out.length).toBe(1);
        expect(out[0]).toContain('ChessBoard');
    });
    it('flags TS imports from modules that are not dependencies', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const out = verifyGeneratedCodeContracts("import { ChessBoard } from '../board/board.ts';", 'typescript', ['game'], fileExports);
        expect(out.length).toBe(1);
        expect(out[0]).toContain('board');
        expect(out[0]).toContain('TS2307');
    });
    it('passes a bare default import from a default-exporting dependency', () => {
        const fileExports = new Map([['game', exps([], 'Game')]]);
        expect(verifyGeneratedCodeContracts("import Game from '../game/game.ts';", 'typescript', ['game'], fileExports)).toEqual([]);
    });
    it('passes python member imports of real exports and ignores stdlib imports', () => {
        const fileExports = new Map([['game', exps(['ChessGame', 'ChessBoard'])]]);
        const code = "import os\nimport json\nfrom game import ChessGame, ChessBoard\nfrom typing import List\n";
        expect(verifyGeneratedCodeContracts(code, 'python', ['game'], fileExports)).toEqual([]);
    });
    it('flags python imports of members the module never defines', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const out = verifyGeneratedCodeContracts("from game import ChessGame, ChessBoard\n", 'python', ['game'], fileExports);
        expect(out.length).toBe(1);
        expect(out[0]).toContain('ChessBoard');
    });
    it('flags python relative imports of unknown modules but never bare stdlib names', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const out = verifyGeneratedCodeContracts("from .board import ChessBoard\nimport numpy\n", 'python', ['game'], fileExports);
        expect(out.length).toBe(1);
        expect(out[0]).toContain('board');
        expect(out[0]).not.toContain('numpy');
    });
    it('passes rust crate:: member imports of real exports', () => {
        const fileExports = new Map([['game', exps(['ChessGame', 'ChessBoard'])]]);
        const code = "use crate::game::ChessGame;\nuse crate::game::{ChessBoard};";
        expect(verifyGeneratedCodeContracts(code, 'rust', ['game'], fileExports)).toEqual([]);
    });
    it('flags rust crate:: imports of members the module never exports', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const out = verifyGeneratedCodeContracts("use crate::game::ChessBoard;\n", 'rust', ['game'], fileExports);
        expect(out.length).toBe(1);
        expect(out[0]).toContain('ChessBoard');
    });
    it('passes go stdlib imports and known src-layout deps, flags unknown src-layout deps', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const code = 'import (\n  "fmt"\n  "encoding/json"\n  "chess-game/src/game"\n)\n';
        expect(verifyGeneratedCodeContracts(code, 'go', ['game'], fileExports)).toEqual([]);
        const bad = verifyGeneratedCodeContracts('import "chess-game/src/board"\n', 'go', ['game'], fileExports);
        expect(bad.length).toBe(1);
        expect(bad[0]).toContain('board');
    });
    it('ignores import-looking text inside comments', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const code = "// import { ChessBoard } from '../board/board.ts';\nimport { ChessGame } from '../game/game.ts';\n";
        expect(verifyGeneratedCodeContracts(code, 'typescript', ['game'], fileExports)).toEqual([]);
    });
    it('ignores import-looking text inside string literals (code samples)', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const code = [
            'export const usageSample = "import { ChessBoard } from \'../board/board.ts\';\\n";',
            'export const readme = `import { ChessGame } from \'../game/game.ts\';`;',
            "import { ChessGame } from '../game/game.ts';",
        ].join('\n');
        expect(verifyGeneratedCodeContracts(code, 'typescript', ['game'], fileExports)).toEqual([]);
    });
    it('ignores python inline # comments when verifying member names', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const code = 'from game import ChessGame  # the game class\n';
        expect(verifyGeneratedCodeContracts(code, 'python', ['game'], fileExports)).toEqual([]);
    });
    it('flags python members even when a comment follows a genuinely missing name', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const out = verifyGeneratedCodeContracts('from game import ChessGame, ChessBoard  # board lives elsewhere\n', 'python', ['game'], fileExports);
        expect(out.length).toBe(1);
        expect(out[0]).toContain('ChessBoard');
        expect(out[0]).not.toContain('# board lives elsewhere');
    });
    it('ignores import-looking lines inside python docstrings', () => {
        const fileExports = new Map([['game', exps(['ChessGame'])]]);
        const code = '\"\"\"\nUsage example:\nfrom .board import ChessBoard\n\"\"\"\nfrom game import ChessGame\n';
        expect(verifyGeneratedCodeContracts(code, 'python', ['game'], fileExports)).toEqual([]);
    });
});
describe('findLocalDeclaredNames (deterministic import-collision guard)', () => {
    it('detects exported class/interface/enum/function/const declarations', () => {
        const code = [
            'export enum TaskPriority { LOW = \'low\' }',
            'export class DueDate { private _date: Date; }',
            'export interface Config { port: number }',
            'export function parse(input: string): number { return 0; }',
            'export const BOARD_SIZE = 3;',
        ].join('\n');
        const names = findLocalDeclaredNames(code);
        for (const n of ['TaskPriority', 'DueDate', 'Config', 'parse', 'BOARD_SIZE']) {
            expect(names.has(n)).toBe(true);
        }
    });
    it('detects non-exported top-level class declarations too', () => {
        expect(findLocalDeclaredNames('class Game {}\nconst x = 1;').has('Game')).toBe(true);
    });
    it('does not flag names declared inside a function body', () => {
        const code = 'export function f() {\n  const local = 1;\n  class Inner {}\n  return local;\n}';
        const names = findLocalDeclaredNames(code);
        expect(names.has('local')).toBe(false);
        expect(names.has('Inner')).toBe(false);
    });
    it('detects names in export { } re-export blocks', () => {
        expect(findLocalDeclaredNames('const a = 1;\nexport { a };').has('a')).toBe(true);
    });
});
describe('dependency source injection (REAL SOURCE of ...)', () => {
    // The rendering helper that embeds a dependency's actual source into the
    // generation/repair prompt. Verifies the cap and the marker so dependents
    // are told to code against real shapes, not guessed ones.
    function renderDepSource(label, src) {
        const MAX = 4000;
        if (!src || src.trim().length <= 10)
            return '';
        const capped = src.trim().length > MAX
            ? src.trim().substring(0, MAX) + '\n// ... (dependency truncated)'
            : src.trim();
        return `REAL SOURCE of ${label} (code against these exact shapes):\n━━━\n${capped}\n━━━`;
    }
    it('embeds the dependency source with the marker', () => {
        const out = renderDepSource('grid.ts', 'export class Game { private cells: (string|null)[] = []; }');
        expect(out).toContain('REAL SOURCE of grid.ts');
        expect(out).toContain('private cells: (string|null)[]');
    });
    it('returns empty for missing or tiny sources (falls back to names-only context)', () => {
        expect(renderDepSource('grid.ts', undefined)).toBe('');
        expect(renderDepSource('grid.ts', '  ')).toBe('');
    });
    it('caps long dependency sources with a truncation marker', () => {
        const big = 'export const x = 1;\n'.repeat(3000); // > 4000 chars
        const out = renderDepSource('big.ts', big);
        expect(out.length).toBeLessThan(big.length + 200);
        expect(out).toContain('// ... (dependency truncated)');
    });
});
describe('type ownership section (graph-free duplicate-type prevention)', () => {
    it('derives a PascalCase stem from a node label, extension included', () => {
        expect(nodeTypeStem('budget-store')).toBe('BudgetStore');
        expect(nodeTypeStem('temp-store.swift')).toBe('TempStore');
        expect(nodeTypeStem('cli')).toBe('Cli');
        expect(nodeTypeStem('')).toBe('');
    });
    it('names each sibling as the owner of its concept and forbids redeclaring it', () => {
        const section = buildTypeOwnershipSection('cli.swift', [
            { label: 'stats.swift', description: 'temperature statistics' },
            { label: 'temp-store.swift', description: 'stores readings' },
        ]);
        expect(section).toContain('TYPE OWNERSHIP (MANDATORY)');
        expect(section).toContain('THIS FILE ("cli.swift") owns the types that carry ITS OWN responsibility');
        expect(section).toContain('named like `Cli`');
        expect(section).toContain('- stats.swift — owns types named like `Stats*`');
        expect(section).toContain('temperature statistics');
        expect(section).toContain('NEVER declare a type whose definition already exists in a sibling file');
        expect(section).toContain('Do NOT declare the program entry point');
    });
    it('is empty for a single-file app, so that prompt is unchanged', () => {
        expect(buildTypeOwnershipSection('app.ts', [])).toBe('');
    });
});
