import { describe, it, expect } from 'vitest';
import { execFileSync } from 'node:child_process';
import * as os from 'os';
import { runProjectGates, runNonTsGatesWithRepair, sanitizeNonTsSource, buildNonTsRepairPrompt, groupGateErrorsByFile, fixUnusedGoVariables } from './nonTsRepair.js';
const hasGo = (() => {
    try {
        execFileSync('go', ['version'], { stdio: 'ignore' });
        return true;
    }
    catch {
        return false;
    }
})();
const tsContracts = [
    { path: 'src/game.ts', summary: '', language: 'typescript', exports: ['checkWin'], uses: [] },
];
describe('runProjectGates (shared non-TS + stub + contract-aware gate)', () => {
    it('flags a planned export whose body is a single placeholder return', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return false; }' }];
        const res = await runProjectGates('game', files, tsContracts);
        expect(res.stubFailures.some((s) => s.includes("'checkWin'"))).toBe(true);
    });
    it('accepts a real implementation', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return computeWinner() !== null; }' }];
        const res = await runProjectGates('game', files, tsContracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('accepts a real PYTHON implementation (indented body, no braces)', async () => {
        // The brace-based body classifier found nothing in a .py file, so every
        // planned export came back 'absent' — which the gate reports as
        // "not implemented" for non-TS languages. Real Python nodes were rejected.
        const pyContracts = [
            { path: 'src/converter/converter.py', summary: '', language: 'python', exports: ['celsius_to_fahrenheit'], uses: [] },
        ];
        const files = [{
                path: 'src/converter/converter.py',
                content: 'def celsius_to_fahrenheit(celsius: float) -> float:\n    return (celsius * 9/5) + 32\n',
            }];
        const res = await runProjectGates('temp converter', files, pyContracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('still flags a Python export whose body is only `pass`', async () => {
        const pyContracts = [
            { path: 'src/converter/converter.py', summary: '', language: 'python', exports: ['convert'], uses: [] },
        ];
        const files = [{ path: 'src/converter/converter.py', content: 'def convert(value):\n    pass\n' }];
        const res = await runProjectGates('temp converter', files, pyContracts);
        expect(res.stubFailures.some((s) => s.includes("'convert'"))).toBe(true);
    });
});
describe('sanitizeNonTsSource — Go node files never claim `package main`', () => {
    it('rewrites `package main` to the node directory package when there is no func main()', () => {
        const src = 'package main\n\nfunc reverseString(s string) string { return s }\n';
        const fixed = sanitizeNonTsSource(src, 'go', 'src/cli/cli.go');
        expect(fixed).toContain('package cli');
        expect(fixed).not.toContain('package main');
    });
    it('leaves a real Go program (func main) alone', () => {
        const prog = 'package main\n\nfunc main() { println("hi") }\n';
        expect(sanitizeNonTsSource(prog, 'go', 'src/cli/cli.go')).toBeNull();
    });
    it('strips a stray leading dot before the `package` clause', () => {
        // Measured live: a generated Go json→yaml tool shipped `.package main`, so
        // `go build` reported `expected 'package', found '.'` — which masks every
        // other error in the file. The clause is mandatory and first (comments
        // aside), so a dot before it can never be correct.
        const fixed = sanitizeNonTsSource('.package main\n\nfunc main() {}\n', 'go', 'main.go');
        expect(fixed).toBe('package main\n\nfunc main() {}\n');
    });
    it('strips a stray leading dot on its own line ANYWHERE in the file', () => {
        // Measured live: the generated file-size CLI shipped `.GetFilesAndSizes(dir)`
        // as a statement inside `main()`, so `go build` rejected the whole project
        // with `expected operand, found '.'`. No Go statement begins with a dot.
        const src = [
            'package main',
            '',
            'func main() {',
            '\tdir := "."',
            '\t.GetFilesAndSizes(dir)',
            '}',
            '',
            'func GetFilesAndSizes(d string) {}',
            '',
        ].join('\n');
        const fixed = sanitizeNonTsSource(src, 'go', 'go_sizes.go');
        expect(fixed).toContain('\tGetFilesAndSizes(dir)');
        expect(fixed).not.toContain('.GetFilesAndSizes');
    });
    it('never rewrites a raw string or a comment that starts with a dot', () => {
        // A dot-file listing (or any prose) printed from a raw string must survive:
        // only a dot that Go would read as a statement may be stripped.
        const src = [
            'package main',
            '',
            'import "fmt"',
            '',
            'const usage = `',
            '.hidden',
            '.config/tool',
            '`',
            '',
            '// .notacall()',
            'func main() { fmt.Println(usage) }',
            '',
        ].join('\n');
        expect(sanitizeNonTsSource(src, 'go', 'main.go')).toBeNull();
    });
    it('rewrites a non-main package that still declares func main() to `package main`', () => {
        // Measured live: the generated SHA-256 CLI shipped `package app` + a real
        // `func main()`. Go builds that as a LIBRARY — no binary, so the CLI can
        // never run — while the compile gate still reports the file clean; the
        // defect only surfaced later as a CLI-smoke failure. A top-level `func main`
        // is legal ONLY in `package main`.
        const fixed = sanitizeNonTsSource('package app\n\nimport "fmt"\n\nfunc main() { fmt.Println("hi") }\n', 'go', 'go_sha256.go');
        expect(fixed).toContain('package main');
        expect(fixed).not.toContain('package app');
    });
    it('leaves a LIBRARY package (no func main) alone', () => {
        expect(sanitizeNonTsSource('package utils\n\nfunc Helper() {}\n', 'go', 'utils/util.go')).toBeNull();
    });
    it('does not touch a Go file whose package clause is already correct', () => {
        expect(sanitizeNonTsSource('package main\n\nfunc main() {}\n', 'go', 'main.go')).toBeNull();
        // A leading comment (and blank lines) is legal and must be preserved.
        expect(sanitizeNonTsSource('// tool\npackage main\n\nfunc main() {}\n', 'go', 'main.go')).toBeNull();
    });
    it('rewrites a fatal RELATIVE Go import to the go.mod module path', () => {
        // `go build` rejects `import "./src/hashutil"` outright in module mode
        // ("relative import paths are not supported in module mode"). Measured live
        // on two consecutive Go builds that both failed this exact way after the
        // prompt told the model to use the module path — so it is fixed
        // deterministically instead of by prompt wording.
        const src = 'package main\n\nimport (\n\t"flag"\n\t"./src/hashutil"\n)\n\nfunc main() {}\n';
        const fixed = sanitizeNonTsSource(src, 'go', 'main.go', { goModuleName: 'a-go-cli-tool' });
        expect(fixed).toContain('"a-go-cli-tool/src/hashutil"');
        expect(fixed).not.toContain('"./src/hashutil"');
        // A real standard-library import is untouched.
        expect(fixed).toContain('"flag"');
    });
    it('also fixes a single-line relative import and the ../ form', () => {
        const one = sanitizeNonTsSource('package main\n\nimport "./parser"\n\nfunc main() {}\n', 'go', 'main.go', { goModuleName: 'json2yaml' });
        expect(one).toContain('"json2yaml/parser"');
        const up = sanitizeNonTsSource('package main\n\nimport "../pkg/util"\n\nfunc main() {}\n', 'go', 'cmd/tool.go', { goModuleName: 'json2yaml' });
        expect(up).toContain('"json2yaml/pkg/util"');
    });
    it('leaves relative imports alone when no module name is supplied', () => {
        const src = 'package main\n\nimport "./parser"\n\nfunc main() {}\n';
        expect(sanitizeNonTsSource(src, 'go', 'main.go')).toBeNull();
    });
    it('falls back to `app` for an unusable directory name', () => {
        const src = 'package main\n\nfunc f() {}\n';
        expect(sanitizeNonTsSource(src, 'go', 'src/2d/render.go')).toContain('package app');
    });
});
describe('fixUnusedGoVariables — Go\'s unused-local error has an exact fix', () => {
    it('inserts `_ = name` after the declaration the compiler names', () => {
        // Measured live: the generated file-size CLI captured `err` from
        // `filepath.Walk` and never used it, so `go build` failed with
        // `src/main.go:20:2: declared and not used: err` — the first REAL error the
        // gate reached once the staging artifacts were fixed.
        const src = [
            'package main',
            '',
            'func main() {',
            '\terr := run()',
            '\tprintln("done")',
            '}',
            '',
            'func run() error { return nil }',
            '',
        ].join('\n');
        const fixed = fixUnusedGoVariables(src, ['src/main.go:4:2: declared and not used: err']);
        expect(fixed).toContain('\terr := run()\n\t_ = err\n');
    });
    it('keeps the indentation and fixes several names bottom-up', () => {
        const src = 'package main\n\nfunc main() {\n\ta := 1\n\tb := 2\n\tprintln(a)\n}\n';
        const fixed = fixUnusedGoVariables(src, ['main.go:5:2: declared and not used: b']);
        expect(fixed).toContain('\tb := 2\n\t_ = b\n');
    });
    it('leaves a multi-line declaration alone (no statement may be split)', () => {
        // `x, err := os.Open(\n path)` continues onto the next line: inserting a
        // statement after the reported line would cut the call in half.
        const src = 'package main\n\nfunc main() {\n\tf, err := os.Open(\n\t\t"x",\n\t)\n\tf.Close()\n}\n';
        expect(fixUnusedGoVariables(src, ['main.go:4:5: declared and not used: err'])).toBeNull();
        // A `for` header ends in `{` — its body is not ours to edit.
        const loop = 'package main\n\nfunc main() {\n\tfor _, e := range []int{1} {\n\t\tprintln(e)\n\t}\n}\n';
        expect(fixUnusedGoVariables(loop, ['main.go:4:6: declared and not used: e'])).toBeNull();
    });
    it('ignores errors that are not the unused-local class', () => {
        expect(fixUnusedGoVariables('package main\n', ['main.go:1:1: missing return'])).toBeNull();
        expect(fixUnusedGoVariables('package main\n', [])).toBeNull();
    });
});
describe('runNonTsGatesWithRepair (shared repair loop, injected LLM)', () => {
    it('repairs a stub body and clears the failure', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return false; }' }];
        let calls = 0;
        const res = await runNonTsGatesWithRepair({
            request: 'game',
            files,
            contractFiles: tsContracts,
            exportDir: os.tmpdir(),
            timeoutMs: 5_000,
            canRepair: () => true,
            consumeRepair: () => { calls += 1; },
            repairCall: async () => 'export function checkWin(): boolean { return scanBoard() !== null; }',
        });
        expect(calls).toBeGreaterThan(0);
        expect(res.stubFailures).toEqual([]);
        expect(files[0].content).toContain('scanBoard');
    });
    it('stops after one round when the LLM makes no change', async () => {
        const files = [{ path: 'src/game.ts', content: 'export function checkWin(): boolean { return false; }' }];
        const res = await runNonTsGatesWithRepair({
            request: 'game',
            files,
            contractFiles: tsContracts,
            exportDir: os.tmpdir(),
            timeoutMs: 5_000,
            canRepair: () => true,
            consumeRepair: () => { },
            repairCall: async () => '', // no usable rewrite
        });
        expect(res.rounds).toBe(1);
        expect(res.stubFailures.length).toBeGreaterThan(0);
    });
    it.skipIf(!hasGo)('clears a Go unused-local failure without spending a repair round', async () => {
        const files = [{
                path: 'main.go',
                content: [
                    'package main',
                    '',
                    'import (',
                    '\t"fmt"',
                    '\t"os"',
                    ')',
                    '',
                    'func main() {',
                    '\terr := run()',
                    '\tfmt.Println("done")',
                    '}',
                    '',
                    'func run() error { return os.ErrNotExist }',
                    '',
                ].join('\n'),
            }];
        const contracts = [{ path: 'main.go', summary: '', language: 'go', exports: ['main'], uses: [] }];
        let calls = 0;
        const res = await runNonTsGatesWithRepair({
            request: 'a go cli',
            files,
            contractFiles: contracts,
            exportDir: os.tmpdir(),
            timeoutMs: 5_000,
            canRepair: () => true,
            consumeRepair: () => { calls += 1; },
            repairCall: async () => '', // the LLM would return nothing usable
        });
        // Fixed deterministically: the LLM was never asked, and the gates close.
        expect(calls).toBe(0);
        expect(res.rounds).toBe(0);
        expect(res.languageGates.find((g) => g.language === 'go')?.errors ?? ['missing go gate']).toEqual([]);
        expect(files[0].content).toContain('_ = err');
    });
});
describe('header contracts are judged against the whole build', () => {
    it('accepts a header whose export is DEFINED in its sibling .c', async () => {
        // Measured live: a generated C to-hex tool was rejected with
        // "src/convert.h: planned export 'toHexadecimal' is not implemented" while
        // `toHexadecimal` was fully implemented in src/convert.c — the matcher only
        // ever looked inside the header that DECLARED it.
        const contracts = [
            { path: 'src/convert.h', summary: 'conversion utils', language: 'c', exports: ['toHexadecimal'], uses: [] },
        ];
        const files = [
            { path: 'src/convert.h', content: '#ifndef CONVERT_H\n#define CONVERT_H\n\nconst char* toHexadecimal(long number);\n\n#endif\n' },
            { path: 'src/convert.c', content: '#include "convert.h"\n\nconst char* toHexadecimal(long number) {\n    return formatHex(number);\n}\n' },
        ];
        const res = await runProjectGates('c to hex', files, contracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('still flags a header export that is implemented nowhere', async () => {
        const contracts = [
            { path: 'src/convert.h', summary: 'conversion utils', language: 'c', exports: ['toHexadecimal'], uses: [] },
        ];
        const files = [
            { path: 'src/convert.h', content: 'const char* toHexadecimal(long number);\n' },
            { path: 'src/convert.c', content: 'int unused(void) { return 1; }\n' },
        ];
        const res = await runProjectGates('c to hex', files, contracts);
        expect(res.stubFailures.some((s) => s.includes('toHexadecimal'))).toBe(true);
    });
    it("keeps a C++ project's bare .h so the .cpp that includes it still compiles", async () => {
        // Measured live: a generated C++ string-reverser shipped src/main.cpp,
        // src/string_reverser.cpp and src/string_reverser.h. The planner left the
        // header unlabelled (`.h` is shared by C and C++, so resolveGateLanguage
        // returns null for it), and runProjectGates' `.filter((f) => f.language)`
        // DISCARDED it before runNonTsProjectGates could route it. The gate then
        // failed with `src/main.cpp:2:10: fatal error: string_reverser.h: No such
        // file or directory` while the header was sitting in the export the whole
        // time — so the `.h` routing inside the gate was unreachable from here.
        const contracts = [
            { path: 'src/main.cpp', summary: 'entry', language: 'cpp', exports: [], uses: [] },
            { path: 'src/string_reverser.cpp', summary: 'reverser', language: 'cpp', exports: ['reverseString'], uses: [] },
            { path: 'src/string_reverser.h', summary: 'reverser decl', language: '', exports: [], uses: [] },
        ];
        const files = [
            { path: 'src/main.cpp', content: '#include <iostream>\n#include "string_reverser.h"\n\nint main() {\n    std::cout << reverseString("ab") << std::endl;\n    return 0;\n}\n' },
            { path: 'src/string_reverser.cpp', content: '#include "string_reverser.h"\n#include <algorithm>\n\nstd::string reverseString(const std::string& input) {\n    std::string out = input;\n    std::reverse(out.begin(), out.end());\n    return out;\n}\n' },
            { path: 'src/string_reverser.h', content: '#pragma once\n\n#include <string>\n\nstd::string reverseString(const std::string& input);\n' },
        ];
        const res = await runProjectGates('a C++ command line tool that reverses a string', files, contracts);
        const cpp = res.languageGates.find((g) => g.language === 'cpp');
        expect(cpp, 'cpp gate should have run').toBeTruthy();
        expect(cpp.errors).toEqual([]);
        expect(cpp.clean).toBe(true);
    });
    it('does not flag a C/C++ typedef planned as an export', async () => {
        // `typedef long long NumberType;` puts the name LAST, so the
        // class/interface/enum prefix regex could never match it and the header was
        // reported as an unimplemented stub.
        const files = [{ path: 'src/types.h', content: '#ifndef TYPES_H\n#define TYPES_H\n\ntypedef long long NumberType;\n\n#endif\n' }];
        const contracts = [{ path: 'src/types.h', summary: 'types', language: 'cpp', exports: ['NumberType'], uses: [] }];
        const res = await runProjectGates('gcd', files, contracts);
        expect(res.stubFailures).toEqual([]);
    });
});
describe('Ruby exports: a class/module or a `def self.` method counts as implemented', () => {
    it('accepts a fully-implemented `class WordCounter` planned as an export', async () => {
        // Measured live: the Ruby word-counter row was rejected with "planned export
        // 'WordCounter' is not implemented" while the class was fully implemented —
        // the indented classifier only ever matched `def NAME`, never a class/module.
        const contracts = [
            { path: 'lib/word_counter.rb', summary: 'word counting', language: 'ruby', exports: ['WordCounter'], uses: [] },
        ];
        const files = [{
                path: 'lib/word_counter.rb',
                content: 'class WordCounter\n  def initialize(string)\n    @string = string\n  end\n\n  def count_words\n    @string.split.length\n  end\nend\n',
            }];
        const res = await runProjectGates('word counter', files, contracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('accepts a `module ... def self.method` planned as the export', async () => {
        // `def self.to_title_case` did not match `def NAME`, so the module was
        // reported as an unimplemented stub despite being fully implemented.
        const contracts = [
            { path: 'lib/title_case_converter.rb', summary: 'title case', language: 'ruby', exports: ['to_title_case'], uses: [] },
        ];
        const files = [{
                path: 'lib/title_case_converter.rb',
                content: 'module TitleCaseConverter\n  def self.to_title_case(str)\n    str.split.map { |word| word.capitalize }.join(" ")\n  end\nend\n',
            }];
        const res = await runProjectGates('title case', files, contracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('still flags a Ruby export that appears nowhere', async () => {
        const contracts = [
            { path: 'lib/title_case_converter.rb', summary: 'title case', language: 'ruby', exports: ['to_snake_case'], uses: [] },
        ];
        const files = [{
                path: 'lib/title_case_converter.rb',
                content: 'module TitleCaseConverter\n  def self.to_title_case(str)\n    str.capitalize\n  end\nend\n',
            }];
        const res = await runProjectGates('title case', files, contracts);
        expect(res.stubFailures.some((s) => s.includes('to_snake_case'))).toBe(true);
    });
});
describe('a planned `main` export means "runnable entry", not a function named main', () => {
    it('accepts a Python CLI that runs under `if __name__ == "__main__":`', async () => {
        // Measured live: a correct, runnable Python file-renamer was rejected with
        // "src/main.py: planned export 'main' is not implemented in the generated
        // code" — the gate demanded a `def main`, which the plan's `main` export is
        // not actually a contract for.
        const contracts = [
            { path: 'src/main.py', summary: 'CLI entry', language: 'python', exports: ['main'], uses: [] },
        ];
        const files = [{
                path: 'src/main.py',
                content: 'import os\n\ndef rename_all(d):\n    for f in os.listdir(d):\n        os.rename(os.path.join(d, f), os.path.join(d, f.lower()))\n\nif __name__ == "__main__":\n    import sys\n    rename_all(sys.argv[1])\n',
            }];
        const res = await runProjectGates('renamer', files, contracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('accepts a Ruby CLI that runs under `if __FILE__ == $0`', async () => {
        const contracts = [
            { path: 'main.rb', summary: 'CLI entry', language: 'ruby', exports: ['main'], uses: [] },
        ];
        const files = [{
                path: 'main.rb',
                content: 'def greet(n)\n  "hi #{n}"\nend\n\nif __FILE__ == $0\n  puts greet(ARGV[0])\nend\n',
            }];
        const res = await runProjectGates('greeter', files, contracts);
        expect(res.stubFailures).toEqual([]);
    });
    it('still flags a `main` export whose body is a placeholder', async () => {
        const contracts = [
            { path: 'src/main.py', summary: 'CLI entry', language: 'python', exports: ['main'], uses: [] },
        ];
        const files = [{ path: 'src/main.py', content: 'def main():\n    pass\n' }];
        const res = await runProjectGates('cli', files, contracts);
        expect(res.stubFailures.length).toBeGreaterThan(0);
    });
});
describe('entry-point failures are attributed to a FILE so the loop can fix them', () => {
    it('repairs a Python CLI that was a bag of declarations', async () => {
        // Measured live: two "Python CLI tool" builds shipped as bare functions.
        // The gate was right to reject them, but its error named NO file, so
        // groupGateErrorsByFile() routed nothing, the loop broke out at round 0
        // (repairRounds: 0) and the model was never shown the problem.
        const files = [{ path: 'word_counter.py', content: 'def count_words_and_lines(path):\n    return len(open(path).read().split())\n' }];
        const contracts = [
            { path: 'word_counter.py', summary: 'CLI', language: 'python', exports: ['count_words_and_lines'], uses: [] },
        ];
        let promptSeen = '';
        const res = await runNonTsGatesWithRepair({
            request: 'a Python CLI tool that counts the words in a file',
            files,
            contractFiles: contracts,
            exportDir: os.tmpdir(),
            timeoutMs: 5_000,
            canRepair: () => true,
            consumeRepair: () => { },
            repairCall: async (prompt) => {
                promptSeen = prompt;
                return 'import sys\n\ndef count_words_and_lines(path):\n    return len(open(path).read().split())\n\nif __name__ == "__main__":\n    print(count_words_and_lines(sys.argv[1]))\n';
            },
        });
        expect(promptSeen).toContain('no runnable entry point');
        expect(promptSeen).toContain('word_counter.py');
        expect(files[0].content).toContain('__main__');
        expect(res.rounds).toBeGreaterThan(0);
    });
});
describe('gate errors are attributed to a file even when the planned path has a ./ prefix', () => {
    // Measured live: the Go planner emitted nodes as `./converter/converter.go`
    // while the compiler named `converter/converter.go`, so the raw
    // `line.includes(f.path)` test matched nothing, the loop found no failing
    // file and broke out at round 0 — the invented import `os/yaml` was never
    // shown to the model and `repairRounds` stayed 0.
    it('routes `converter/converter.go` to the `./converter/converter.go` node', () => {
        const files = [{ path: './converter/converter.go', content: '' }, { path: './main.go', content: '' }];
        const byFile = groupGateErrorsByFile([{ language: 'go', clean: false, errors: ['converter/converter.go:6:2: package os/yaml is not in std'] }], files);
        expect([...byFile.keys()]).toEqual(['./converter/converter.go']);
        expect(byFile.get('./converter/converter.go')?.join(' ')).toContain('os/yaml');
    });
    it('still prefers the LONGEST matching path', () => {
        const files = [{ path: 'src/a.java', content: '' }, { path: 'a.java', content: '' }];
        const byFile = groupGateErrorsByFile([{ language: 'java', clean: false, errors: ['src/a.java:3: error: cannot find symbol'] }], files);
        expect([...byFile.keys()]).toEqual(['src/a.java']);
    });
});
describe('the repair prompt carries the language primer', () => {
    // The repair round writes real code, so it needs the SAME toolchain primer the
    // generation prompt gets. Measured without it: a Kotlin repair added a second
    // `fun factorial(n: Int): Long` in a sibling file (`conflicting overloads`),
    // and Go repairs invented `github.com/yourusername/...` import paths.
    it('injects Kotlin guidance (one main, no duplicate overloads)', () => {
        const p = buildNonTsRepairPrompt('a Kotlin CLI tool that computes the factorial of a number', { path: 'src/FactorialCalculator.kt', summary: 'factorial', language: 'kotlin', exports: ['factorial'], uses: [] }, 'fun factorial(n: Int): Long { return 1 }', { compilerErrors: ['src/FactorialCalculator.kt:1:1: error: conflicting overloads: fun factorial(n: Int): Long'] }, []);
        expect(p).toContain('LANGUAGE GUIDANCE (Kotlin');
        expect(p).toContain('conflicting overloads');
        expect(p).toContain('EXACTLY ONCE');
    });
    it('injects Go guidance with the real module path and the no-placeholder rule', () => {
        const p = buildNonTsRepairPrompt('a Go CLI tool that computes the SHA-256 of a file', { path: 'main.go', summary: 'cli', language: 'go', exports: ['main'], uses: [] }, 'package main\nfunc main() {}', { compilerErrors: ['main.go:8:2: no required module provides package github.com/yourusername/VACA/app/hasher'] }, []);
        expect(p).toContain('LANGUAGE GUIDANCE (Go');
        expect(p).toContain('github.com');
        // The real module path is handed to the repair round, not just the generator.
        expect(p).toContain('module a-go-cli-tool-that-computes-the-sha-256-of-a-file');
    });
    it('injects Swift guidance (never @main in main.swift)', () => {
        const p = buildNonTsRepairPrompt('a Swift CLI tool that counts the vowels in a string', { path: 'Sources/VowelCounter/main.swift', summary: 'cli', language: 'swift', exports: ['main'], uses: [] }, '@main\nstruct VowelCounter {}', { compilerErrors: ["Sources/VowelCounter/main.swift:6:1: error: 'main' attribute cannot be used in a module that contains top-level code"] }, []);
        expect(p).toContain('LANGUAGE GUIDANCE (Swift');
        expect(p).toContain('top-level code');
    });
});
