import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { execFileSync } from 'child_process';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import * as zlib from 'zlib';
import { jarManifestInfo, runNonTsProjectGates, resolveGateLanguage, fileDeclaresEntryPoint, goStagePath, planGoStaging, goLocalImportPaths, goFilePackage, goDeclaresMainFunc } from './nonTsCompileGate.js';
const has = (bin, args = ['--version']) => {
    try {
        execFileSync(bin, args, { stdio: 'ignore' });
        return true;
    }
    catch {
        return false;
    }
};
const hasGcc = has('gcc');
const hasGpp = has('g++');
const hasNode = has('node');
const hasRuby = has('ruby');
const hasGo = has('go', ['version']);
/**
 * Build a minimal single-entry jar by hand. `method` 0 stores the manifest
 * (kotlinc stores it uncompressed) and 8 deflates it, so both branches of the
 * reader are exercised. The reader never verifies the CRC, so it is left zero.
 */
function makeJar(manifest, method) {
    const name = 'META-INF/MANIFEST.MF';
    const nameBuf = Buffer.from(name, 'utf8');
    const data = Buffer.from(manifest === null ? '' : manifest, 'utf8');
    const stored = method === 0 ? data : zlib.deflateRawSync(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(method, 8);
    local.writeUInt32LE(stored.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    const cd = Buffer.alloc(46);
    cd.writeUInt32LE(0x02014b50, 0);
    cd.writeUInt16LE(20, 4);
    cd.writeUInt16LE(20, 6);
    cd.writeUInt16LE(method, 10);
    cd.writeUInt32LE(stored.length, 20);
    cd.writeUInt32LE(data.length, 24);
    cd.writeUInt16LE(nameBuf.length, 28);
    cd.writeUInt32LE(0, 42); // local header offset
    const cdStart = 30 + nameBuf.length + stored.length;
    const cdSize = 46 + nameBuf.length;
    const eocd = Buffer.alloc(22);
    eocd.writeUInt32LE(0x06054b50, 0);
    eocd.writeUInt16LE(1, 8);
    eocd.writeUInt16LE(1, 10);
    eocd.writeUInt32LE(cdSize, 12);
    eocd.writeUInt32LE(cdStart, 16);
    return Buffer.concat([local, nameBuf, stored, cd, nameBuf, eocd]).toString('base64');
}
let dir;
beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-jar-test-'));
});
afterEach(() => {
    fs.rmSync(dir, { recursive: true, force: true });
});
function writeJar(manifest, method) {
    const p = path.join(dir, 'out.jar');
    fs.writeFileSync(p, Buffer.from(makeJar(manifest, method), 'base64'));
    return p;
}
describe('jarManifestInfo', () => {
    it('reads the Main-Class from a stored manifest', () => {
        const p = writeJar('Manifest-Version: 1.0\r\nMain-Class: MKt\r\n\r\n', 0);
        expect(jarManifestInfo(p)).toEqual({ read: true, mainClass: 'MKt' });
    });
    it('reads the Main-Class from a deflated manifest', () => {
        const p = writeJar('Manifest-Version: 1.0\r\nMain-Class: com.example.MainKt\r\n\r\n', 8);
        expect(jarManifestInfo(p)).toEqual({ read: true, mainClass: 'com.example.MainKt' });
    });
    it('reports a manifest with no Main-Class as read but null', () => {
        const p = writeJar('Manifest-Version: 1.0\r\n\r\n', 0);
        expect(jarManifestInfo(p)).toEqual({ read: true, mainClass: null });
    });
    it('reports an unparseable file as unread, never as "no entry point"', () => {
        const p = path.join(dir, 'broken.jar');
        fs.writeFileSync(p, Buffer.from('this is not a zip file'));
        expect(jarManifestInfo(p)).toEqual({ read: false, mainClass: null });
    });
    it('reports a missing file as unread', () => {
        expect(jarManifestInfo(path.join(dir, 'does-not-exist.jar'))).toEqual({ read: false, mainClass: null });
    });
});
/**
 * The entry-point gate used to emit a pathless error, which made it unroutable:
 * the non-TS repair loop attributes failures to files
 * (`groupGateErrorsByFile`) and found none, so it broke out at round 0 and the
 * model was never shown the problem. The error must name the file it applies to.
 */
describe('entry-point gate errors are file-attributed', () => {
    it('prefixes the entry-point error with the candidate entry file', async () => {
        const gates = await runNonTsProjectGates([{ relPath: 'src/util/helpers.py', code: 'def helper(x):\n    return x + 1\n', language: 'python' }], 'helpers');
        const py = gates.find((g) => g.language === 'python');
        expect(py?.clean).toBe(false);
        const entry = (py?.errors || []).find((e) => /no runnable entry point/i.test(e));
        expect(entry).toBeDefined();
        expect(entry.startsWith('src/util/helpers.py: ')).toBe(true);
    });
    it('accepts the idiomatic Ruby `if __FILE__ == $0` entry guard', async () => {
        // Measured live: two generated Ruby CLI tools ended in exactly this guard
        // and DO run under `ruby x.rb`, but the gate called them "no runnable entry
        // point" — Python's `if __name__ == "__main__":` was special-cased and
        // Ruby's equivalent was not.
        const gates = await runNonTsProjectGates([{
                relPath: 'fibonacci.rb',
                language: 'ruby',
                code: 'def generate_fibonacci(n)\n  [0, 1].first(n).join(\' \')\nend\n\nif __FILE__ == $0\n  puts generate_fibonacci(ARGV[0].to_i)\nend\n',
            }], 'fib');
        const rb = gates.find((g) => g.language === 'ruby');
        expect((rb?.errors || []).some((e) => /no runnable entry point/i.test(e))).toBe(false);
    });
    it('accepts a bare top-level `puts` as a Ruby entry point', async () => {
        const gates = await runNonTsProjectGates([{ relPath: 'hello.rb', language: 'ruby', code: 'def greet(n)\n  "hi #{n}"\nend\n\nputs greet(ARGV[0])\n' }], 'hello');
        const rb = gates.find((g) => g.language === 'ruby');
        expect((rb?.errors || []).some((e) => /no runnable entry point/i.test(e))).toBe(false);
    });
    it.skipIf(!hasGcc)('puts every source directory on the include path so a root file can include a header under src/', async () => {
        // Measured live: `c char-count` produced src/counter.h + src/counter.c +
        // root main.c doing `#include "counter.h"`. The gate passed only the root
        // and the including file's own dir, so gcc reported "counter.h: No such file
        // or directory" and the row was a false FAIL.
        const gates = await runNonTsProjectGates([
            { relPath: 'main.c', language: 'c', code: '#include <stdio.h>\n#include "counter.h"\nint main(void) { printf("%d\\n", count_chars("abc")); return 0; }\n' },
            { relPath: 'src/counter.h', language: 'c', code: '#ifndef COUNTER_H\n#define COUNTER_H\nint count_chars(const char *s);\n#endif\n' },
            { relPath: 'src/counter.c', language: 'c', code: '#include "counter.h"\nint count_chars(const char *s) { int n = 0; while (s[n]) n++; return n; }\n' },
        ], 'charcount');
        const c = gates.find((g) => g.language === 'c');
        expect(c?.errors || []).toEqual([]);
        expect(c?.clean).toBe(true);
    });
    it.skipIf(!hasGpp)('puts every source directory on the include path for C++ too', async () => {
        const gates = await runNonTsProjectGates([
            { relPath: 'main.cpp', language: 'cpp', code: '#include <iostream>\n#include "counter.hpp"\nint main() { std::cout << count_chars("abc") << "\\n"; return 0; }\n' },
            { relPath: 'src/counter.hpp', language: 'cpp', code: '#pragma once\nint count_chars(const char *s);\n' },
            { relPath: 'src/counter.cpp', language: 'cpp', code: '#include "counter.hpp"\nint count_chars(const char *s) { int n = 0; while (s[n]) n++; return n; }\n' },
        ], 'charcount');
        const cpp = gates.find((g) => g.language === 'cpp');
        expect(cpp?.errors || []).toEqual([]);
        expect(cpp?.clean).toBe(true);
    });
    it('prefers a file named like an entry point over the first file', async () => {
        const gates = await runNonTsProjectGates([
            { relPath: 'src/graph.py', code: 'def build():\n    return []\n', language: 'python' },
            { relPath: 'cli.py', code: 'def parse(a):\n    return a\n', language: 'python' },
        ], 'graph');
        const py = gates.find((g) => g.language === 'python');
        const entry = (py?.errors || []).find((e) => /no runnable entry point/i.test(e));
        expect(entry.startsWith('cli.py: ')).toBe(true);
    });
});
describe('the project root is always on the include path', () => {
    it.skipIf(!hasGpp)('keeps the PROJECT ROOT on the include path so a test can include "src/x.h"', async () => {
        // Measured live: a generated C++ GCD app had every file under src/ + tests/,
        // so the root was no file's own directory; `tests/test_gcd.cpp` did
        // `#include "src/gcd.h"` and g++ reported "src/gcd.h: No such file". The
        // root must always be an include dir, alongside each file's own directory.
        const gates = await runNonTsProjectGates([
            { relPath: 'src/gcd.h', language: 'cpp', code: '#pragma once\nnamespace math { int computeGCD(int a, int b); }\n' },
            { relPath: 'src/gcd.cpp', language: 'cpp', code: '#include "src/gcd.h"\nnamespace math { int computeGCD(int a, int b) { return b ? computeGCD(b, a % b) : a; } }\n' },
            { relPath: 'src/main.cpp', language: 'cpp', code: '#include "src/gcd.h"\nint main() { return math::computeGCD(48, 18) == 6 ? 0 : 1; }\n' },
            { relPath: 'tests/test_gcd.cpp', language: 'cpp', code: '#include "src/gcd.h"\nint main() { return math::computeGCD(56, 98) == 14 ? 0 : 1; }\n' },
        ], 'gcd');
        const cpp = gates.find((g) => g.language === 'cpp');
        expect(cpp?.errors || []).toEqual([]);
        expect(cpp?.clean).toBe(true);
    });
});
describe('bare `.h` headers are attached to the C/C++ gate', () => {
    it.skipIf(!hasGcc)('C: an unlabelled header is staged so its includers resolve', async () => {
        // Measured live: a generated C to-hex tool shipped src/main.c,
        // src/convert_hex.c and src/convert_hex.h. The header had no declared
        // language and `.h` maps to no gate, so it was dropped and the row failed on
        // `#include "convert_hex.h"` even though the header existed.
        const gates = await runNonTsProjectGates([
            { relPath: 'src/main.c', language: 'c', code: '#include "convert_hex.h"\nint main(void) { return to_hex(1) >= 0 ? 0 : 1; }\n' },
            { relPath: 'src/convert_hex.c', language: 'c', code: '#include "convert_hex.h"\nint to_hex(int n) { return n; }\n' },
            { relPath: 'src/convert_hex.h', language: undefined, code: '#ifndef C_H\n#define C_H\nint to_hex(int n);\n#endif\n' },
        ], 'tohex');
        const c = gates.find((g) => g.language === 'c');
        expect(c?.errors || []).toEqual([]);
        expect(c?.clean).toBe(true);
    });
    it.skipIf(!hasGpp)('C++: a `.h` labelled `c` still joins the cpp gate (shared header)', async () => {
        // Measured live: the planner labelled the header `c` in a C++ project, so it
        // was staged in the SEPARATE C gate dir and the C++ files could not find it:
        // "src/main.cpp: #include \"string_reverser.h\": No such file or directory".
        const gates = await runNonTsProjectGates([
            { relPath: 'src/main.cpp', language: 'cpp', code: '#include "prime_logic.h"\nint main() { return isPrime(2) ? 0 : 1; }\n' },
            { relPath: 'src/prime_logic.cpp', language: 'cpp', code: '#include "prime_logic.h"\nbool isPrime(int n) { if (n < 2) return false; for (int i = 2; i * i <= n; i++) if (n % i == 0) return false; return true; }\n' },
            { relPath: 'src/prime_logic.h', language: 'c', code: '#pragma once\nbool isPrime(int n);\n' },
        ], 'primes');
        const cpp = gates.find((g) => g.language === 'cpp');
        expect(cpp?.errors || []).toEqual([]);
        expect(cpp?.clean).toBe(true);
    });
    it.skipIf(!hasGpp)('C++: an unlabelled `.h` joins the cpp gate too', async () => {
        const gates = await runNonTsProjectGates([
            { relPath: 'src/main.cpp', language: 'cpp', code: '#include "prime_logic.h"\nint main() { return isPrime(2) ? 0 : 1; }\n' },
            { relPath: 'src/prime_logic.h', language: undefined, code: '#pragma once\nbool isPrime(int n);\n' },
            { relPath: 'src/prime_logic.cpp', language: 'cpp', code: '#include "prime_logic.h"\nbool isPrime(int n) { if (n < 2) return false; for (int i = 2; i * i <= n; i++) if (n % i == 0) return false; return true; }\n' },
        ], 'primes');
        const cpp = gates.find((g) => g.language === 'cpp');
        expect(cpp?.errors || []).toEqual([]);
        expect(cpp?.clean).toBe(true);
    });
});
describe('config dotfiles are not linted as source', () => {
    it.skipIf(!hasRuby)('skips `.rspec` in the Ruby per-file gate', async () => {
        // Measured live: a generated Ruby word-count CLI shipped a `.rspec` config
        // (`--require spec_helper`) that the planner labelled as ruby, so `ruby -c`
        // reported a syntax error and the valid project became a hard FAIL.
        const gates = await runNonTsProjectGates([
            { relPath: 'bin/word_count_tool', language: 'ruby', code: '#!/usr/bin/env ruby\nputs "hi"\n' },
            { relPath: 'lib/word_counter.rb', language: 'ruby', code: 'class WordCounter\n  def count(s)\n    s.split.length\n  end\nend\n' },
            { relPath: '.rspec', language: 'ruby', code: '--require spec_helper\n--format documentation\n' },
        ], 'wordcount');
        const rb = gates.find((g) => g.language === 'ruby');
        expect(rb?.clean).toBe(true);
    });
});
/**
 * A JavaScript build used to fall through every gate and report the catch-all
 * "no gate applied (unverified)" — the one matrix row with no verdict at all.
 * `node --check` gives it a real syntax gate (and the same entry-point rule the
 * other script languages get).
 */
describe('javascript is gated (node --check)', () => {
    it.skipIf(!hasNode)('accepts a valid JS CLI with a top-level entry point', async () => {
        const gates = await runNonTsProjectGates([{
                relPath: 'src/main.js',
                language: 'javascript',
                code: 'const fs = require("fs");\nconst args = process.argv.slice(2);\nif (!args[0]) { console.error("usage"); process.exit(1); }\nconsole.log(args[0]);\n',
            }], 'jscli');
        const js = gates.find((g) => g.language === 'javascript');
        expect(js?.clean).toBe(true);
        expect(js?.errors || []).toEqual([]);
    });
    it.skipIf(!hasNode)('reports a real syntax error, attributed to the file', async () => {
        const gates = await runNonTsProjectGates([{ relPath: 'src/main.js', language: 'javascript', code: 'function foo( {\nconsole.log(1);\n' }], 'jscli');
        const js = gates.find((g) => g.language === 'javascript');
        expect(js?.clean).toBe(false);
        expect((js?.errors || []).some((e) => e.startsWith('src/main.js:'))).toBe(true);
    });
    it.skipIf(!hasNode)('accepts an ESM-only file (import/export)', async () => {
        const gates = await runNonTsProjectGates([{ relPath: 'bin/tool.mjs', language: 'javascript', code: 'import fs from "fs";\nconsole.log(fs.existsSync("/"));\n' }], 'esm');
        const js = gates.find((g) => g.language === 'javascript');
        expect(js?.errors || []).toEqual([]);
        expect(js?.clean).toBe(true);
    });
    it('resolves .js/.mjs/.cjs by extension, and keeps TypeScript OUT of this gate', () => {
        expect(resolveGateLanguage(undefined, 'src/a.js')).toBe('javascript');
        expect(resolveGateLanguage(undefined, 'src/a.mjs')).toBe('javascript');
        expect(resolveGateLanguage(undefined, 'src/a.cjs')).toBe('javascript');
        expect(resolveGateLanguage('js', 'x')).toBe('javascript');
        // TypeScript has its own tsc gate and must not be double-gated here.
        expect(resolveGateLanguage('typescript', 'a.ts')).toBe(null);
        expect(resolveGateLanguage(undefined, 'a.tsx')).toBe(null);
    });
});
describe('goStagePath — a root Go file gets the directory its import path names', () => {
    // Go resolves an import by DIRECTORY, and the model picks the package name
    // itself. Measured live on 3 consecutive Go builds: a root `hasher.go` came
    // back as `package hasher` while `main.go` imported `<module>/hasher`, so
    // `go build ./...` failed with `package <module>/hasher is not in std`; a root
    // `converter.go` written as `package app` collided with main.go in one dir.
    it('moves a root non-main file under a directory named after its package', () => {
        expect(goStagePath('hasher.go', 'package hasher\n\nimport "crypto/sha256"\n')).toBe('hasher/hasher.go');
        expect(goStagePath('./converter.go', 'package app\n')).toBe('app/converter.go');
    });
    it('leaves package main files and subdirectory files alone', () => {
        expect(goStagePath('main.go', 'package main\n\nfunc main() {}\n')).toBe('main.go');
        expect(goStagePath('utils.go', 'package main\n')).toBe('utils.go');
        expect(goStagePath('fileutil/file.go', 'package fileutil\n')).toBe('fileutil/file.go');
        expect(goStagePath('./fileutil/file.go', 'package fileutil\n')).toBe('fileutil/file.go');
    });
    it('falls back to a usable path when the plan gives none', () => {
        expect(goStagePath('', 'package hasher\n')).toBe('hasher/main.go');
        expect(goStagePath('', 'package main\n')).toBe('main.go');
    });
});
describe('goLocalImportPaths / goFilePackage', () => {
    it('finds module-prefixed and relative local imports, ignoring stdlib', () => {
        const code = [
            'package main',
            '',
            'import (',
            '\t"crypto/sha256"',
            '\t"fmt"',
            '\thc "my-app/src/hash_computer"',
            ')',
            '',
            'import "my-app/util"',
            'import "./parser"',
            '// import "my-app/commented"',
            '',
            'func main() {}',
        ].join('\n');
        expect(goLocalImportPaths(code, 'my-app').sort()).toEqual(['./parser', 'my-app/src/hash_computer', 'my-app/util']);
        expect(goFilePackage(code)).toBe('main');
        expect(goFilePackage('  package   src\nfunc f() {}')).toBe('src');
        expect(goFilePackage('// no package here')).toBe('');
    });
    it('detects the entry point only at TOP LEVEL', () => {
        expect(goDeclaresMainFunc('package main\n\nfunc main() {}\n')).toBe(true);
        // `func main` with a receiver or indentation is not the entry point, and a
        // commented-out one must not make a library package look runnable.
        expect(goDeclaresMainFunc('package app\n\nfunc (t T) main() {}\n')).toBe(false);
        expect(goDeclaresMainFunc('package app\n\n\tfunc main() {}\n')).toBe(false);
        expect(goDeclaresMainFunc('package app\n\n// func main() {}\n')).toBe(false);
        expect(goDeclaresMainFunc('package app\n\nfunc mainish() {}\n')).toBe(false);
    });
});
describe('planGoStaging — auto-resolve Go imports against the real layout', () => {
    // The real class from a live build (export …sha-256…1791418221437): main.go
    // imports `<module>/src/hash_computer` and `<module>/src/file_reader`, but the
    // model put BOTH files in one `src/` dir and declared them `package src` — so
    // the import path's last segment names a directory that does not exist and
    // `go build ./...` fails with `package <module>/src/file_reader is not in std`.
    const MOD = 'a-go-cli-tool-that-computes-the-sha-256-hash-of-a-file';
    const mainGo = [
        'package main',
        '',
        'import (',
        `\t"${MOD}/src/hash_computer"`,
        `\t"${MOD}/src/file_reader"`,
        ')',
        '',
        'func main() {',
        '\tfile_reader.ReadFileContent("x")',
        '\thash_computer.ComputeSHA256(nil)',
        '}',
    ].join('\n');
    it('stages each shared-dir package into the directory its import names, aligning the package clause', () => {
        const out = planGoStaging([
            { relPath: 'cmd/cli-tool/main.go', code: mainGo, language: 'go' },
            { relPath: 'src/hash_computer.go', code: 'package src\n\nfunc ComputeSHA256(b []byte) {}\n', language: 'go' },
            { relPath: 'src/file_reader.go', code: 'package src\n\nfunc ReadFileContent(p string) {}\n', language: 'go' },
        ], MOD);
        const byPath = Object.fromEntries(out.map((f) => [f.relPath, f.code]));
        expect(Object.keys(byPath).sort()).toEqual([
            'cmd/cli-tool/main.go',
            'src/file_reader/file_reader.go',
            'src/hash_computer/hash_computer.go',
        ]);
        // The package clause must match the new directory so the call-site
        // qualifier (`file_reader.X` / `hash_computer.X`) still resolves.
        expect(goFilePackage(byPath['src/file_reader/file_reader.go'])).toBe('file_reader');
        expect(goFilePackage(byPath['src/hash_computer/hash_computer.go'])).toBe('hash_computer');
        expect(byPath['cmd/cli-tool/main.go']).toBe(mainGo);
    });
    it('keeps a file already staged where its import resolves', () => {
        const out = planGoStaging([
            { relPath: 'main.go', code: 'package main\n\nimport "./fileutil"\n', language: 'go' },
            { relPath: 'fileutil/file.go', code: 'package fileutil\n', language: 'go' },
        ], 'my-app');
        expect(out.map((f) => f.relPath)).toEqual(['main.go', 'fileutil/file.go']);
        expect(goFilePackage(out[1].code)).toBe('fileutil');
    });
    it('still moves a root file with no importer under its own package dir (old behaviour)', () => {
        const out = planGoStaging([
            { relPath: 'hasher.go', code: 'package hasher\n\nimport "crypto/sha256"\n', language: 'go' },
        ], 'my-app');
        expect(out.map((f) => f.relPath)).toEqual(['hasher/hasher.go']);
    });
    it('never restages package main', () => {
        const out = planGoStaging([
            { relPath: 'main.go', code: 'package main\n\nimport "my-app/src/util"\nfunc main() {}\n', language: 'go' },
        ], 'my-app');
        expect(out.map((f) => f.relPath)).toEqual(['main.go']);
    });
    it('folds a non-main file that shares a directory with package main (one package per dir)', () => {
        // Measured live: a generated file-size tool put `src/files.go` (`package
        // src`) next to `src/main.go`, so `go build` failed with "found packages src
        // (files.go) and main (main.go) in src". Nothing imports that file, so the
        // buildable fix is to fold it into the entry package.
        const out = planGoStaging([
            { relPath: 'src/main.go', code: 'package main\n\nfunc main() {}\n', language: 'go' },
            { relPath: 'src/files.go', code: 'package src\n\nfunc GetDirectorySize() {}\n', language: 'go' },
        ], 'my-app');
        const byPath = Object.fromEntries(out.map((f) => [f.relPath, f.code]));
        expect(goFilePackage(byPath['src/files.go'])).toBe('main');
        expect(byPath['src/main.go']).toBe('package main\n\nfunc main() {}\n');
    });
    it('does not fold a package an importer actually imports', () => {
        const out = planGoStaging([
            { relPath: 'src/main.go', code: 'package main\n\nimport "my-app/src/util"\n\nfunc main() { util.Helper() }\n', language: 'go' },
            { relPath: 'src/util.go', code: 'package util\n\nfunc Helper() {}\n', language: 'go' },
        ], 'my-app');
        const byPath = Object.fromEntries(out.map((f) => [f.relPath, f.code]));
        expect(goFilePackage(byPath['src/util/util.go'])).toBe('util');
    });
    it('keeps the entry point at its own path and forces `package main`', () => {
        // Measured live: the generated SHA-256 CLI came back as `package app` with a
        // real `func main()`. `go build ./...` compiled it as a LIBRARY — no binary,
        // so the CLI could never run, yet the gate reported the file CLEAN — and the
        // rule for a root non-main file additionally buried it in `app/`.
        const out = planGoStaging([
            { relPath: 'go_sha256.go', code: 'package app\n\nimport "fmt"\n\nfunc main() { fmt.Println("x") }\n', language: 'go' },
        ], MOD);
        expect(out.map((f) => f.relPath)).toEqual(['go_sha256.go']);
        expect(goFilePackage(out[0].code)).toBe('main');
    });
    it('treats a `func main` file as the entry even when nothing declares `package main`', () => {
        const out = planGoStaging([
            { relPath: 'src/main.go', code: 'package src\n\nfunc main() {}\n', language: 'go' },
            { relPath: 'src/helpers.go', code: 'package src\n\nfunc helper() {}\n', language: 'go' },
        ], MOD);
        expect(out.map((f) => f.relPath)).toEqual(['src/main.go', 'src/helpers.go']);
        // One package per directory: the sibling folds into the entry package.
        expect(out.map((f) => goFilePackage(f.code))).toEqual(['main', 'main']);
    });
    // End-to-end through the REAL gate: the planned layout must make `go build
    // ./...` close. Skipped when the toolchain is not on PATH.
    it.skipIf(!hasGo)('the import-resolved layout actually compiles through runNonTsProjectGates', async () => {
        const gates = await runNonTsProjectGates([
            { relPath: 'cmd/cli-tool/main.go', code: mainGo, language: 'go' },
            { relPath: 'src/hash_computer.go', code: 'package src\n\nimport "crypto/sha256"\n\nfunc ComputeSHA256(b []byte) string {\n\th := sha256.Sum256(b)\n\treturn string(h[:])\n}\n', language: 'go' },
            { relPath: 'src/file_reader.go', code: 'package src\n\nimport "os"\n\nfunc ReadFileContent(p string) ([]byte, error) {\n\treturn os.ReadFile(p)\n}\n', language: 'go' },
        ], MOD);
        const go = gates.find((g) => g.language === 'go');
        expect(go, 'a go gate entry must exist').toBeTruthy();
        expect(go?.errors ?? []).toEqual([]);
        expect(go?.clean).toBe(true);
    });
    it.skipIf(!hasGo)('builds a main package that lives in a SUBDIRECTORY', async () => {
        // Measured live on a generated file-size CLI: with `package main` in `src/`,
        // plain `go build ./...` fails with `go: build output "src" already exists
        // and is a directory` — the binary takes the package directory's name and is
        // written into the module root, where that very directory sits. The gate
        // builds into a scratch output dir instead.
        const gates = await runNonTsProjectGates([
            { relPath: 'src/main.go', code: 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println(helper()) }\n', language: 'go' },
            { relPath: 'src/files.go', code: 'package src\n\nfunc helper() string { return "hi" }\n', language: 'go' },
        ], MOD);
        const go = gates.find((g) => g.language === 'go');
        expect(go, 'a go gate entry must exist').toBeTruthy();
        expect(go?.errors ?? []).toEqual([]);
        expect(go?.clean).toBe(true);
    });
});
describe('fileDeclaresEntryPoint — Swift top-level control flow counts as an entry', () => {
    // Measured live: a generated Swift c→f converter shipped a correct
    // `main.swift` whose entry is `if CommandLine.argc > 1 { ... }`. It compiles
    // and runs, but the detector only knew top-level `let`/`var`/calls, so it
    // reported "no runnable entry point" and burned two repair rounds on a file
    // that was never broken.
    it('accepts a main.swift guarded by a top-level `if`', () => {
        const code = [
            'import Foundation',
            '',
            'func celsiusToFahrenheit(_ celsius: Double) -> Double {',
            '    return (celsius * 9/5) + 32',
            '}',
            '',
            'if CommandLine.argc > 1 {',
            '    print("\\(CommandLine.arguments[1])")',
            '} else {',
            '    print("Usage: app <celsius>")',
            '}',
            '',
        ].join('\n');
        expect(fileDeclaresEntryPoint(code, 'swift', 'main.swift')).toBe(true);
    });
    it('still accepts @main, a top-level call, and rejects a bag of declarations', () => {
        expect(fileDeclaresEntryPoint('@main\nstruct A { static func main() {} }\n', 'swift', 'App.swift')).toBe(true);
        expect(fileDeclaresEntryPoint('countVowels()', 'swift', 'main.swift')).toBe(true);
        expect(fileDeclaresEntryPoint('import Foundation\nfunc f() {}\n', 'swift', 'VowelService.swift')).toBe(false);
    });
});
describe('fileDeclaresEntryPoint — a PHP one-liner still declares an entry', () => {
    // Measured live through the detector: `<?php echo "hi";` — a valid script —
    // was reported as "no runnable entry point" because the php branch skipped
    // any line starting with the opening tag, statement and all.
    it('accepts `<?php echo ...;` on the opening line', () => {
        expect(fileDeclaresEntryPoint('<?php echo "hello world";', 'php', 'cli.php')).toBe(true);
    });
    it('accepts a same-line top-level assignment', () => {
        expect(fileDeclaresEntryPoint('<?php $argv = $argv ?? [];', 'php', 'cli.php')).toBe(true);
    });
    it('still accepts the tag on its own line with the statement below', () => {
        expect(fileDeclaresEntryPoint('<?php\necho "hi";\n', 'php', 'cli.php')).toBe(true);
    });
    it('still rejects a bag of function definitions with no top-level code', () => {
        const code = ['<?php', '', 'function run() {', '    echo "hi";', '}', '', 'function other() {', '    return [];', '}'].join('\n');
        expect(fileDeclaresEntryPoint(code, 'php', 'cli.php')).toBe(false);
    });
});
