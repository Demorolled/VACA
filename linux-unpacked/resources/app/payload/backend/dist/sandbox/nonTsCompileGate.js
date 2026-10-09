/**
 * nonTsCompileGate — whole-project compile gates for NON-TypeScript languages.
 *
 * The tsc gate is blind to every other language: a project with no .ts files
 * returns status 'skipped' and would otherwise report success with NOTHING
 * compiled (the "tsCompileClean:true while 8/9 files failed" false positive).
 * These gates are the honest counterpart: stage every non-TS file into a temp
 * workspace and run the real toolchain, because a single-file check can never
 * resolve sibling imports/modules.
 *
 *   - Go:     stage the layout with a generated go.mod, `go build ./...`.
 *   - Python: `python3 -m py_compile` per file.
 *   - Rust:   `rustc --crate-type lib --emit=metadata <entry>` (whole module tree).
 *   - C:      `gcc -fsyntax-only -std=c11` per file.
 *   - C++:    `g++ -fsyntax-only -std=c++17` per file.
 *   - Java:   `javac -d <classes> <files>` (whole set — siblings resolve).
 *   - C#:     `csc -target:library <files>` (whole set).
 *   - Swift:  `swiftc -typecheck <files>` (whole set, same module).
 *   - Kotlin: `kotlinc <files> -d <out.jar>` (whole set) + a Main-Class check.
 *   - PHP:    `php -l` per file (lint).
 *   - Ruby:   `ruby -c` per file (syntax).
 *
 * An unavailable toolchain is a FAILED gate — "unverified" is never "clean".
 * Non-fatal by design: a failed gate reports itself; it never throws.
 *
 * Shared by `layers/fileGenerator.ts` (canvas path) and `routes/codePlanner.ts`
 * (chat write path) so both pipelines hold generated output to one standard.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';
import * as zlib from 'zlib';
const execFileAsync = promisify(execFile);
const IS_WINDOWS = process.platform === 'win32';
/** Every language this module can gate. */
export const GATE_LANGUAGES = [
    'go', 'python', 'rust', 'c', 'cpp', 'java', 'csharp', 'swift', 'kotlin', 'php', 'ruby',
    'javascript',
];
/** Language aliases (tool/OS names) → canonical gate language. */
const LANG_ALIASES = {
    golang: 'go', py: 'python', python3: 'python',
    rs: 'rust', rustlang: 'rust',
    'c++': 'cpp', cxx: 'cpp', cplusplus: 'cpp',
    'c#': 'csharp', cs: 'csharp', dotnet: 'csharp',
    kt: 'kotlin', kts: 'kotlin',
    rb: 'ruby',
    js: 'javascript', node: 'javascript', nodejs: 'javascript', ecmascript: 'javascript', mjs: 'javascript', cjs: 'javascript',
};
/** Extension → canonical gate language (used when `language` is missing/wrong). */
const EXT_TO_LANG = {
    go: 'go', py: 'python', rs: 'rust',
    c: 'c',
    cpp: 'cpp', cc: 'cpp', cxx: 'cpp', hpp: 'cpp', hh: 'cpp', hxx: 'cpp', inl: 'cpp', ipp: 'cpp',
    java: 'java',
    cs: 'csharp',
    swift: 'swift',
    kt: 'kotlin', kts: 'kotlin',
    php: 'php', rb: 'ruby',
    js: 'javascript', mjs: 'javascript', cjs: 'javascript',
};
/**
 * Resolve the gate language of a file from its declared language OR extension.
 * Returns null for languages this module does not gate (TS/JS, HTML, CSS, …).
 */
export function resolveGateLanguage(language, relPath) {
    const declared = (language || '').toLowerCase().trim();
    if (declared) {
        if (GATE_LANGUAGES.includes(declared))
            return declared;
        if (LANG_ALIASES[declared])
            return LANG_ALIASES[declared];
    }
    const ext = relPath.split('.').pop()?.toLowerCase() || '';
    return EXT_TO_LANG[ext] || null;
}
/**
 * Sanitize a project title into a valid Go module path segment. Using the raw
 * title (spaces, commas) produced `malformed import path ... invalid char ' '`
 * on every exported Go project — this must match the scaffolder's go.mod name.
 */
export function sanitizeGoModuleName(name) {
    return (name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'untitled';
}
/** True only when every gate that ran is clean. Empty = vacuously clean. */
export function allLanguageGatesClean(gates) {
    return gates.every((g) => g.clean);
}
export const TOOLCHAINS = {
    go: {
        bins: ['go'], versionArgs: ['version'],
        install: { linux: 'sudo apt-get install -y golang-go', windows: 'winget install GoLang.Go', macos: 'brew install go' },
    },
    python: {
        bins: ['python3', 'python'], versionArgs: ['--version'],
        install: { linux: 'sudo apt-get install -y python3', windows: 'winget install Python.Python.3.12', macos: 'brew install python' },
    },
    rust: {
        bins: ['rustc'], versionArgs: ['--version'],
        install: { linux: 'curl --proto \'=https\' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y', windows: 'winget install Rustlang.Rustup', macos: 'brew install rust' },
    },
    c: {
        bins: ['gcc', 'clang', 'cc'], versionArgs: ['--version'],
        install: { linux: 'sudo apt-get install -y build-essential', windows: 'winget install BrechtSanders.WinLibs.POSIX.UCRT', macos: 'xcode-select --install' },
    },
    cpp: {
        bins: ['g++', 'clang++', 'c++'], versionArgs: ['--version'],
        install: { linux: 'sudo apt-get install -y build-essential', windows: 'winget install BrechtSanders.WinLibs.POSIX.UCRT', macos: 'xcode-select --install' },
    },
    java: {
        bins: ['javac'], versionArgs: ['-version'],
        install: { linux: 'sudo apt-get install -y openjdk-17-jdk-headless', windows: 'winget install Microsoft.OpenJDK.17', macos: 'brew install openjdk@17' },
    },
    csharp: {
        // `dotnet` is the realistic path on both OSes (csc is bundled inside the
        // SDK and not on PATH); `mcs` covers Mono installs.
        bins: ['dotnet', 'csc', 'mcs'], versionArgs: ['--version'],
        install: { linux: 'sudo apt-get install -y dotnet-sdk-8.0', windows: 'winget install Microsoft.DotNet.SDK.8', macos: 'brew install dotnet' },
    },
    swift: {
        bins: ['swiftc'], versionArgs: ['--version'],
        // NOTE: the Debian/Ubuntu `swift` package is the OpenStack Swift object
        // store, NOT the compiler. Linux uses swiftly (swift.org's installer).
        install: {
            linux: 'curl -O https://download.swift.org/swiftly/linux/swiftly-$(uname -m).tar.gz && tar zxf swiftly-$(uname -m).tar.gz && ./swiftly init --quiet-shell-followup',
            windows: 'winget install --id Swift.Toolchain -e',
            macos: 'xcode-select --install',
        },
    },
    kotlin: {
        bins: ['kotlinc', 'kotlinc-jvm'], versionArgs: ['-version'],
        install: { linux: 'sudo snap install kotlin --classic', windows: 'winget install JetBrains.Kotlin', macos: 'brew install kotlin' },
    },
    php: {
        bins: ['php'], versionArgs: ['--version'],
        install: { linux: 'sudo apt-get install -y php-cli', windows: 'winget install PHP.PHP', macos: 'brew install php' },
    },
    ruby: {
        bins: ['ruby'], versionArgs: ['--version'],
        install: { linux: 'sudo apt-get install -y ruby-full', windows: 'winget install RubyInstallerTeam.Ruby', macos: 'brew install ruby' },
    },
    javascript: {
        // `node --check` is the syntax gate (the analogue of `php -l` / `ruby -c`).
        // Node's own runtime is the right tool and is always present for a Node
        // app, so a JS build no longer reports the catch-all "no gate applied".
        bins: ['node', 'nodejs'], versionArgs: ['--version'],
        install: { linux: 'sudo apt-get install -y nodejs', windows: 'winget install OpenJS.NodeJS.LTS', macos: 'brew install node' },
    },
};
/**
 * Well-known install directories that are NOT on a non-login shell's PATH.
 * `rustup` puts rustc/cargo in `~/.cargo/bin` and the dotnet-install script
 * puts the SDK in `~/.dotnet` — both invisible to the backend process (which is
 * spawned without a login shell), so the Rust/C# gate would report "not
 * installed" even though the toolchain is present. We search these AND return
 * the ABSOLUTE path, so the gate can exec the binary regardless of PATH.
 */
const EXTRA_BIN_DIRS = [
    path.join(os.homedir(), '.cargo', 'bin'),
    path.join(os.homedir(), '.dotnet'),
    // swiftly (the Swift toolchain installer) drops swiftc here.
    path.join(os.homedir(), '.local', 'share', 'swiftly', 'bin'),
    path.join(os.homedir(), '.local', 'bin'),
    '/usr/local/bin',
    '/snap/bin',
];
/** Find an executable for `bins` across PATH + the well-known install dirs. */
function findBinary(bins) {
    const dirs = [
        ...(process.env.PATH || '').split(path.delimiter),
        ...EXTRA_BIN_DIRS,
    ].filter(Boolean);
    const exts = IS_WINDOWS ? (process.env.PATHEXT || '.EXE;.CMD;.BAT;.COM').split(';') : [''];
    for (const bin of bins) {
        for (const dir of dirs) {
            for (const ext of exts) {
                const candidate = path.join(dir, bin + ext);
                try {
                    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile())
                        return candidate;
                }
                catch { /* unreadable dir — keep looking */ }
            }
        }
    }
    return null;
}
/**
 * The command to run for a language's gate: the ABSOLUTE path of the first
 * candidate binary found (PATH + well-known install dirs), or the canonical
 * bare name when none is found — so the gate's error is the honest
 * "<bin> is not installed — gate unavailable".
 *
 * NOT cached: the result depends on `process.env.PATH`, which callers (tests,
 * toolchain preflight) legitimately change at runtime. A cached path went stale
 * the moment PATH moved on and made a later gate exec a deleted temp binary.
 * The scan is a handful of `stat` calls — negligible next to spawning a
 * compiler.
 */
export function toolchainBin(language) {
    return findBinary(TOOLCHAINS[language].bins) || TOOLCHAINS[language].bins[0];
}
/**
 * Probe every gate toolchain and report what is (un)available. Deterministic,
 * non-throwing, and cheap enough for a preflight report — VACA can tell the
 * user exactly which languages it can verify on THIS machine and how to add
 * the rest, instead of failing a build with an opaque "gate unavailable".
 */
export async function detectToolchains() {
    const out = [];
    for (const language of GATE_LANGUAGES) {
        const spec = TOOLCHAINS[language];
        const bin = toolchainBin(language);
        const r = await runTool(bin, spec.versionArgs, { timeout: 15000 });
        out.push({
            language,
            bin,
            available: r.ok,
            version: (r.ok ? r.out : r.error).split('\n')[0].trim().slice(0, 120),
            install: spec.install,
        });
    }
    return out;
}
/** Stage a file into `dir` at its relative path, guarding against traversal. */
function stageFile(dir, relPath, code) {
    const safeRel = relPath.replace(/^[/\\]+/, '').split(/[/\\]+/).filter((p) => p && p !== '.' && p !== '..').join('/');
    const target = path.join(dir, ...(safeRel || 'untitled').split('/'));
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, code, 'utf-8');
    return target;
}
/**
 * Every distinct directory holding a staged source file. A generated project
 * splits code across directories (a root `main.c` often includes a header the
 * planner placed in `src/`), so passing one `-I` per directory lets the syntax
 * gate judge the code on its own terms rather than failing on include layout.
 * Measured live: `c char-count` produced `src/counter.h` + `src/counter.c` +
 * root `main.c` (`#include "counter.h"`) and the gate reported
 * `counter.h: No such file or directory` because only the root and each file's
 * own dir were on the include path.
 */
function includeDirsFor(root, absFiles) {
    // The project root is ALWAYS on the path: an entry point under `tests/`
    // commonly includes the header as `"src/gcd.h"` (root-relative), not
    // `"gcd.h"`. When every file lives under a subdir, the root is not any file's
    // own directory, so it must be added explicitly.
    return [...new Set([root, ...absFiles.map((f) => path.dirname(f))])];
}
/**
 * A config dotfile the planner may LABEL with the project's language but that is
 * not source (`.rspec`, `.env`, `.eslintrc`). A per-file syntax gate must skip
 * it: `ruby -c .rspec` fails on `--require spec_helper`, turning a valid Ruby
 * project into a compile-gate FAIL. Measured live on a generated `ruby
 * word-count` row that shipped `bin/word_count_tool`, `lib/word_counter.rb`,
 * `Gemfile`, and `.rspec`.
 */
function isConfigDotfile(relPath) {
    return path.basename(relPath || '').startsWith('.');
}
/** Run a tool; normalize "binary missing" into a clear, non-throwing failure. */
async function runTool(bin, args, opts) {
    try {
        const res = await execFileAsync(bin, args, { cwd: opts.cwd, timeout: opts.timeout, maxBuffer: 8 * 1024 * 1024 });
        return { ok: true, error: '', out: `${res.stdout || ''}${res.stderr || ''}` };
    }
    catch (err) {
        if (err?.code === 'ENOENT')
            return { ok: false, error: `${bin} is not installed — gate unavailable (unverified is not clean)`, out: '' };
        // Some tools print their version to stderr AND exit non-zero for a probe
        // (java -version does) — surface the output so a version report still works.
        const msg = (err?.stderr || err?.stdout || err?.message || String(err)).toString().trim().slice(0, 2000);
        return { ok: false, error: msg || `${bin} failed`, out: (err?.stdout || '').toString() };
    }
}
/** Per-file syntax/lint check (stops collecting after `maxErrors`). */
async function perFileGate(bin, argsFor, absFiles, cwd, timeout, maxErrors = 10) {
    const failures = [];
    for (const abs of absFiles) {
        const r = await runTool(bin, argsFor(abs), { cwd, timeout });
        if (!r.ok) {
            failures.push(`${path.relative(cwd, abs)}: ${r.error}`);
            if (failures.length >= maxErrors)
                break;
        }
    }
    return failures;
}
/** Whole-set compile (siblings resolve). */
async function wholeSetGate(bin, args, cwd, timeout) {
    const r = await runTool(bin, args, { cwd, timeout });
    return r.ok ? [] : [r.error];
}
function pushGate(gates, language, errors) {
    const clean = errors.length === 0;
    gates.push({ language, clean, errors: clean ? [] : errors.slice(0, 10) });
    if (clean)
        console.log(`[nonTsGate] ${language} whole-project gate: PASS`);
    else
        console.warn(`[nonTsGate] ${language} whole-project gate: FAIL — ${errors[0]?.slice(0, 160) || ''}`);
}
/**
 * Entry-point patterns for the compiled languages: a literal `main` declaration
 * proves the program can actually be launched. Script languages (Python, PHP,
 * Ruby, Swift, top-level-statement C#, and JavaScript) are handled by
 * `hasExecutableTopLevel` instead — they have no `main` keyword.
 */
const ENTRY_PATTERNS = {
    go: [/\bfunc\s+main\s*\(/],
    rust: [/\bfn\s+main\s*\(/],
    c: [/\b(?:int|void)\s+main\s*\(/],
    cpp: [/\b(?:int|void)\s+main\s*\(/],
    java: [/\b(?:public\s+static|static\s+public)\s+void\s+main\s*\(/],
    csharp: [/\bstatic\s+(?:async\s+)?(?:void|int|Task(?:<int>)?)\s+Main\s*\(/],
    kotlin: [/\bfun\s+main\s*\(/],
    swift: [/@main\b/],
};
/** Languages whose entry point is executable code at the top level of a file. */
const SCRIPT_ENTRY_LANGS = new Set(['python', 'php', 'ruby', 'swift', 'csharp', 'javascript']);
/**
 * Whether a file has EXECUTABLE TOP-LEVEL statements — i.e. it is a runnable
 * script rather than a bag of declarations. Brace/keyword-aware enough for the
 * generated shapes: a column-0 line that is not a declaration, comment, or
 * block terminator counts. Deliberately biased toward false PASSES (a docstring
 * line that looks like a call) over false FAILS.
 */
function hasExecutableTopLevel(code, language) {
    for (const raw of (code || '').split('\n')) {
        const line = raw.replace(/\s+$/, '');
        if (!line.trim())
            continue;
        if (/^\s/.test(line))
            continue; // indented → inside a block
        const t = line.trim();
        if (language === 'python') {
            if (/^#/.test(t))
                continue;
            if (/^(?:def|class|import|from|@)/.test(t))
                continue;
            if (/^if\s+__name__\s*==/.test(t))
                return true;
            if (/^[A-Za-z_][\w.]*\s*\(/.test(t))
                return true;
            continue;
        }
        if (language === 'php') {
            // A one-line script puts its ONLY statement on the same line as the
            // opening tag (`<?php echo "hi";`). Skipping every line that STARTS with
            // `<?php` therefore missed it, and a file that runs fine under
            // `php cli.php` was reported as "no runnable entry point" — measured live
            // through the real detector. Strip the tag and judge the remainder of the
            // line, so the tag and the statement on it are treated separately.
            let php = t;
            if (/^<\?php\b/i.test(php))
                php = php.replace(/^<\?php\b/i, '');
            else if (/^<\?=/.test(php))
                return true; // short echo tag prints at top level
            else if (/^<\?/.test(php))
                php = php.replace(/^<\?/, ''); // short open tag
            else if (/^\?>/.test(php))
                php = php.replace(/^\?>/, '');
            php = php.replace(/\?>\s*$/, '').trim();
            if (!php)
                continue;
            if (/^\/\/|^#|^\*|^\/\*/.test(php))
                continue;
            if (/^(?:function|class|interface|trait|namespace|use|declare)\b/.test(php))
                continue;
            if (php === '}' || php === '{')
                continue;
            if (/^(?:require|require_once|include|include_once)\b/.test(php))
                return true;
            if (/^(?:echo|print|new)\b|^\$[A-Za-z_]/.test(php))
                return true;
            if (/^[A-Za-z_]\w*\s*\(/.test(php))
                return true;
            continue;
        }
        if (language === 'ruby') {
            if (/^#/.test(t))
                continue;
            if (/^(?:def|class|module|end|__END__)\b/.test(t))
                continue;
            if (/^(?:require|require_relative|load)\b/.test(t))
                return true;
            // The idiomatic Ruby entry guard — the direct analogue of Python's
            // `if __name__ == "__main__":`, which this function already special-cases.
            // Without it a genuinely runnable file (`if __FILE__ == $0` + a call) was
            // reported as "no runnable entry point": measured live on two generated
            // Ruby CLI tools that both DO run when invoked with `ruby x.rb`.
            if (/^if\s+__FILE__\s*==/.test(t))
                return true;
            // Any other column-0 control-flow or output statement is executable code
            // (the `^\s` guard above already excluded indented lines, i.e. bodies).
            // `puts "hi"` at top level has no bracket after the method name, so the
            // call/assignment patterns below both miss it.
            if (/^(?:if|unless|while|until|begin|case|loop|puts|print|p|warn|raise)\b/.test(t))
                return true;
            if (/^[A-Za-z_]\w*\s*[.\[(]/.test(t))
                return true; // call / chain
            if (/^[A-Za-z_]\w*\s*=/.test(t))
                return true; // assignment
            continue;
        }
        if (language === 'swift') {
            if (/^\/\//.test(t))
                continue;
            if (/^(?:let|var)\b/.test(t))
                return true; // top-level binding
            if (/^(?:import|func|class|struct|enum|protocol|extension|typealias|actor)\b/.test(t))
                continue;
            if (/^@main\b/.test(t))
                return true;
            // A column-0 control-flow statement IS top-level executable code — the
            // `^\s` guard above already excluded anything inside a block body. Without
            // this, a valid `main.swift` whose entry is `if CommandLine.argc > 1 { ... }`
            // was reported as "no runnable entry point" (measured live on a generated
            // Swift c→f converter that compiles and runs correctly); the model then
            // churned two repair rounds trying to satisfy a gate that was simply wrong.
            if (/^(?:if|guard|while|for|repeat|switch|do|defer)\b/.test(t))
                return true;
            if (/^(?:print|debugPrint|assert|precondition|fatalError)\b/.test(t))
                return true;
            if (/^[A-Za-z_][\w.]*\s*\(/.test(t))
                return true;
            continue;
        }
        if (language === 'csharp') {
            // Top-level statements (C# 9+) are a valid program without a Main method.
            if (/^\/\//.test(t) || /^\*/.test(t))
                continue;
            if (/^(?:using|namespace|public|internal|private|protected|sealed|abstract|static|partial|class|interface|struct|enum|record|delegate)\b/.test(t))
                continue;
            if (t === '{' || t === '}')
                continue;
            if (/^\[/.test(t))
                continue; // attribute line
            return true;
        }
        if (language === 'javascript') {
            // Imports/exports and declarations are wiring, not a program. A JS CLI's
            // entry point is executable top-level code (a call, a control-flow
            // statement, or a top-level `process.argv` read) — measured live on a
            // generated `src/main.js` whose entry was `const args = process.argv...`
            // followed by `if (!filePath) { ... }`.
            if (/^\/\//.test(t) || /^\/\*/.test(t) || /^\*/.test(t))
                continue;
            if (/^(?:import|export)\b/.test(t))
                continue;
            if (/^(?:const|let|var|function|class|async\s+function)\b/.test(t))
                continue;
            return true;
        }
    }
    return false;
}
/** Does a single file declare the program's entry point? */
function fileHasEntryPoint(code, language) {
    const patterns = ENTRY_PATTERNS[language];
    if (patterns?.some((re) => re.test(code)))
        return true;
    if (SCRIPT_ENTRY_LANGS.has(language) && hasExecutableTopLevel(code, language))
        return true;
    return false;
}
/**
 * Whether a file carries a runnable entry point, exposed for the contract gate.
 *
 * A plan that lists `main` as a file's export is describing the ENTRY-POINT
 * convention, not a real callable contract: a Python CLI that runs under
 * `if __name__ == "__main__":`, a Ruby script guarded by `if __FILE__ == $0`,
 * or any other top-level executable statement satisfies it without a function
 * literally named `main`. Measured live: a correct, runnable Python
 * file-renamer was rejected with
 * "src/main.py: planned export 'main' is not implemented".
 */
export function fileDeclaresEntryPoint(code, language, relPath = '') {
    const lang = resolveGateLanguage(language, relPath);
    if (!lang)
        return false;
    return fileHasEntryPoint(code || '', lang);
}
/** Human hint naming the entry point shape a language expects. */
const ENTRY_HINTS = {
    go: 'func main()',
    rust: 'fn main()',
    c: 'int main()',
    cpp: 'int main()',
    java: 'public static void main(String[])',
    csharp: 'static Main() or top-level statements',
    kotlin: 'fun main()',
    swift: '@main or top-level statements',
    python: 'if __name__ == "__main__" or a top-level call',
    php: 'executable top-level statements',
    ruby: 'executable top-level statements',
    javascript: 'a top-level call that runs the program',
};
/**
 * The file an entry-point failure should be ATTRIBUTED to.
 *
 * Every other gate error names the file it came from, and the non-TS repair
 * loop routes failures to a file (`groupGateErrorsByFile`). An entry-point
 * error carries no path of its own, so it was unroutable: the loop found no
 * failing file, broke out at round 0, and the model was never shown the
 * problem — measured live on two Python CLI builds that shipped as bare
 * functions with `repairRounds: 0`. Naming the most likely entry file keeps the
 * error honest AND makes the existing repair loop able to fix it.
 */
function pickEntryCandidate(files, language) {
    const baseOf = (p) => (p || '').replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '').toLowerCase();
    const exact = new Set(['main', 'app', 'cli', 'index', 'run', 'program', 'entry', 'start', 'application']);
    for (const f of files)
        if (exact.has(baseOf(f.relPath)))
            return f;
    const loose = /main|app|cli|index|run|start/;
    for (const f of files)
        if (loose.test(baseOf(f.relPath)))
            return f;
    void language;
    return files[0];
}
/** Entry errors for a language's file set (empty when a runnable entry exists). */
function entryGateErrors(files, language) {
    if (files.some((f) => fileHasEntryPoint(f.code, language)))
        return [];
    const owner = pickEntryCandidate(files, language);
    return [
        `${owner.relPath}: no runnable entry point — this ${language} build compiles but cannot be ` +
            `launched (found no ${ENTRY_HINTS[language]}). VACA builds apps, not libraries: add the entry point.`,
    ];
}
/**
 * The `Main-Class` a jar's manifest declares.
 *
 * `read` is false when the jar could not be parsed at all — callers must treat
 * that as "unknown", never as "no entry point", so an unsupported jar shape can
 * not invent a failure. `mainClass` is null when the manifest was read but
 * declares no `Main-Class`.
 *
 * Needed because `kotlinc <files> -include-runtime -d app.jar` sets the manifest
 * `Main-Class` only when EXACTLY ONE `fun main` is present: two overloads
 * (`main()` in one node, `main(args)` in another) compile with exit 0 and no
 * errors, and the resulting jar then dies at launch with "no main manifest
 * attribute". The compile gate alone therefore reported `clean: true` for a jar
 * that cannot be run — measured live on a generated grade-calculator app.
 */
export function jarManifestInfo(jarPath) {
    try {
        const buf = fs.readFileSync(jarPath);
        // End Of Central Directory record: signature 0x06054b50, scanned from the
        // tail because a trailing comment (up to 64 KiB) may follow it.
        let eocd = -1;
        for (let i = buf.length - 22; i >= 0 && i >= buf.length - 22 - 65535; i--) {
            if (buf.readUInt32LE(i) === 0x06054b50) {
                eocd = i;
                break;
            }
        }
        if (eocd < 0)
            return { read: false, mainClass: null };
        const count = buf.readUInt16LE(eocd + 10);
        let off = buf.readUInt32LE(eocd + 16);
        for (let n = 0; n < count; n++) {
            if (off + 46 > buf.length || buf.readUInt32LE(off) !== 0x02014b50)
                return { read: false, mainClass: null };
            const method = buf.readUInt16LE(off + 10);
            const compSize = buf.readUInt32LE(off + 20);
            const nameLen = buf.readUInt16LE(off + 28);
            const extraLen = buf.readUInt16LE(off + 30);
            const commentLen = buf.readUInt16LE(off + 32);
            const localOff = buf.readUInt32LE(off + 42);
            const name = buf.toString('utf8', off + 46, off + 46 + nameLen);
            if (name === 'META-INF/MANIFEST.MF') {
                // The central directory carries no data offset: follow the local header.
                const lNameLen = buf.readUInt16LE(localOff + 26);
                const lExtraLen = buf.readUInt16LE(localOff + 28);
                const start = localOff + 30 + lNameLen + lExtraLen;
                const data = buf.subarray(start, start + compSize);
                const text = (method === 0 ? data : zlib.inflateRawSync(data)).toString('utf8');
                const m = /^Main-Class:\s*(.+)$/m.exec(text);
                return { read: true, mainClass: m ? m[1].trim() : null };
            }
            off += 46 + nameLen + extraLen + commentLen;
        }
        return { read: false, mainClass: null };
    }
    catch {
        return { read: false, mainClass: null };
    }
}
/**
 * Where a generated Go file must be STAGED so its import path resolves.
 *
 * Go resolves an import by DIRECTORY: `import "<module>/hasher"` only builds if
 * a `hasher/` directory exists. The model decides the package name itself, so a
 * plan node `hasher.go` frequently comes back as `package hasher` while `main.go`
 * imports `<module>/hasher` — and the file is sitting at the project ROOT, so
 * `go build ./...` fails with `package <module>/hasher is not in std` (measured
 * live on 3 consecutive Go builds). Likewise a root `converter.go` written as
 * `package app` collided with `main.go`: "found packages app (converter.go) and
 * main (main.go) in <dir>".
 *
 * Honour the package the model declared: a non-`main` file planned at the root
 * is staged under a directory named after its own package, which is exactly the
 * directory its callers' import path names. `package main` files and files that
 * already live in a subdirectory are left where the plan put them.
 */
export function goStagePath(relPath, code) {
    const norm = (relPath || '').replace(/\\/g, '/').replace(/^\.\//, '').replace(/^\/+/, '');
    const m = /^\s*package\s+([A-Za-z_]\w*)/m.exec(code || '');
    const pkg = m ? m[1] : '';
    const safe = norm || 'main.go';
    if (!pkg || pkg === 'main')
        return safe;
    const parts = safe.split('/');
    const base = parts[parts.length - 1] || 'file.go';
    const dir = parts.slice(0, -1);
    if (dir.length)
        return safe; // already inside a directory — trust the plan
    return `${pkg}/${base}`;
}
/** The package a Go file declares (`''` when it declares none). */
export function goFilePackage(code) {
    const m = /^[ \t]*package[ \t]+([A-Za-z_]\w*)/m.exec(code || '');
    return m ? m[1] : '';
}
/**
 * True when the file declares the program entry point — a TOP-LEVEL
 * `func main()`. Comments are stripped first so a commented-out `func main()`
 * cannot make a library package look runnable.
 */
export function goDeclaresMainFunc(code) {
    return /^func[ \t]+main[ \t]*\(/m.test((code || '').replace(/\/\/[^\n]*/g, ''));
}
/**
 * Every LOCAL import path a Go file references — module-prefixed
 * (`<module>/dir`) or relative (`./dir`, `../dir`). Imports of the standard
 * library or a third-party module are ignored: they never name a directory this
 * project stages.
 *
 * Comments are stripped first so a commented-out import cannot steer staging.
 */
export function goLocalImportPaths(code, moduleName) {
    const src = (code || '').replace(/\/\/[^\n]*/g, '');
    const specs = [];
    const collect = (body) => {
        const re = /"((?:[^"\\]|\\.)*)"/g;
        let q;
        while ((q = re.exec(body)))
            specs.push(q[1]);
    };
    let m;
    const grouped = /import[ \t]*\(([\s\S]*?)\)/g;
    while ((m = grouped.exec(src)))
        collect(m[1]);
    const single = /\bimport[ \t]+(?:(?:[A-Za-z_]\w*|[_.])[ \t]+)?"((?:[^"\\]|\\.)*)"/g;
    while ((m = single.exec(src)))
        specs.push(m[1]);
    const isLocal = (spec) => spec.startsWith('./') || spec.startsWith('../') || spec === moduleName || (!!moduleName && spec.startsWith(`${moduleName}/`));
    return [...new Set(specs.filter(isLocal))];
}
/**
 * Plan the whole-project Go staging layout so every LOCAL import resolves.
 *
 * Go resolves an import by DIRECTORY, and the model routinely writes files that
 * violate that: it puts several packages' files in one shared `src/` dir while
 * importing each as `<module>/src/<pkg>`, and declares them all `package src`.
 * The import path's last segment then names a directory that does not exist, so
 * `go build ./...` fails with `package <module>/src/<pkg> is not in std`
 * (measured live on 3 consecutive Go builds of the SHA-256/file-size/JSON→YAML
 * tools). `goStagePath` cannot see this class — it leaves a file already in a
 * subdirectory untouched and never consults the importers.
 *
 * This planner AUTO-DECIDES per project: it gathers every local import path's
 * directory, then stages each non-`main` package into the directory its own
 * importers name (matching the file's STEM first, then its declared package
 * name), and aligns the `package` clause to that directory's base name so the
 * call-site qualifier (`pkg.Fn`) still matches. Files nothing imports keep the
 * plan's location (root files fall back to `goStagePath`'s own-package dir).
 *
 * The gate then tries this layout FIRST and falls back to the naive
 * `goStagePath` layout if it still does not compile — whichever closes wins.
 */
export function planGoStaging(files, moduleName) {
    const norm = (p) => (p || 'main.go').replace(/\\/g, '/').replace(/^\.\//, '').replace(/^\/+/, '');
    const dirName = (p) => norm(p).split('/').slice(0, -1).join('/');
    const baseName = (p) => norm(p).split('/').pop() || 'file.go';
    const stem = (p) => baseName(p).replace(/\.[^.]+$/, '');
    const lastSeg = (d) => d.split('/').filter(Boolean).pop() || '';
    // 1. Every directory the project's own imports name.
    const wanted = new Set();
    for (const f of files) {
        const fromDir = dirName(f.relPath);
        for (const spec of goLocalImportPaths(f.code, moduleName)) {
            let dir = '';
            if (spec.startsWith('./') || spec.startsWith('../')) {
                dir = path.posix.normalize(path.posix.join(fromDir, spec)).replace(/^\.\//, '');
            }
            else if (moduleName && spec.startsWith(`${moduleName}/`)) {
                dir = spec.slice(moduleName.length + 1);
            }
            dir = dir.replace(/\/+$/, '');
            if (dir && dir !== '.')
                wanted.add(dir);
        }
    }
    // 2. Directories that hold a `package main` file. Go allows exactly ONE
    // package per directory, so a non-main file staged into one of these is a
    // hard build error ("found packages src (files.go) and main (main.go) in
    // src") — measured live on a generated file-size tool whose `src/files.go`
    // declared `package src` next to `src/main.go`.
    const mainDirs = new Set();
    for (const f of files) {
        if (goFilePackage(f.code) === 'main' || goDeclaresMainFunc(f.code))
            mainDirs.add(dirName(f.relPath));
    }
    // 3. Stage each file where its importers expect it; align the package clause.
    const out = [];
    const seen = new Set();
    for (const f of files) {
        const pkg = goFilePackage(f.code);
        const base = baseName(f.relPath);
        const isEntry = goDeclaresMainFunc(f.code);
        if (!pkg || pkg === 'main' || isEntry) {
            const rel = norm(f.relPath);
            // A file carrying the entry point must BE `package main`: any other name
            // compiles as a library, produces no binary and can never run — and the
            // old "root non-main file → its own package dir" rule buried such a file
            // in `app/`, where the compile gate still reported it CLEAN (measured live
            // on the generated SHA-256 CLI). The sanitizer does this too; the planner
            // does it so the layout is right even for unsanitized input.
            const code = isEntry && pkg && pkg !== 'main'
                ? f.code.replace(/^([ \t]*)package[ \t]+\w+/m, '$1package main')
                : f.code;
            if (!seen.has(rel)) {
                seen.add(rel);
                out.push({ relPath: rel, code });
            }
            continue;
        }
        const fileStem = stem(f.relPath);
        const candidates = [...wanted].filter((d) => lastSeg(d) === fileStem || lastSeg(d) === pkg);
        let targetDir = '';
        if (candidates.length) {
            const exact = candidates.filter((d) => lastSeg(d) === fileStem);
            // The importer that named the FILE (its stem) is the strongest signal;
            // otherwise the one that named the PACKAGE. Shortest path wins ties.
            const pool = (exact.length ? exact : candidates).sort((a, b) => a.length - b.length || a.localeCompare(b));
            targetDir = pool[0];
        }
        else {
            targetDir = dirName(f.relPath) || pkg; // no importer: keep the plan (root file → own-package dir)
        }
        let code = f.code;
        const want = lastSeg(targetDir);
        if (want && want !== pkg && /^[ \t]*package[ \t]+\w+/m.test(code)) {
            code = code.replace(/^([ \t]*)package[ \t]+\w+/m, `$1package ${want}`);
        }
        const rel = targetDir ? `${targetDir}/${base}` : base;
        const relDir = rel.includes('/') ? rel.split('/').slice(0, -1).join('/') : '';
        // One package per directory: a non-main file sharing a directory with the
        // entry point must BE `package main` (nothing imports it, or it would have
        // been staged into its importer's directory instead). Folding it keeps the
        // file where the plan put it and makes the directory buildable.
        if (mainDirs.has(relDir) && !wanted.has(relDir)) {
            code = code.replace(/^([ \t]*)package[ \t]+\w+/m, '$1package main');
        }
        if (!seen.has(rel)) {
            seen.add(rel);
            out.push({ relPath: rel, code });
        }
    }
    return out;
}
/**
 * Run whole-project compile gates for every gateable language present.
 * Returns one entry per language that had files; languages with no files are
 * omitted (the caller treats an empty array as "no non-TS gate needed").
 *
 * Every language ALSO gets an entry-point check: a build that compiles but has
 * no runnable entry (a Python file of bare functions, a PHP file with only
 * `function` definitions, a Go set of library packages) is rejected — the
 * compile gates only prove the code parses, not that the app can be run.
 */
export async function runNonTsProjectGates(files, moduleName, opts) {
    const gates = [];
    // Group by canonical language (declared language OR extension).
    const byLang = new Map();
    for (const f of files) {
        const lang = resolveGateLanguage(f.language, f.relPath);
        if (!lang)
            continue;
        const list = byLang.get(lang) || [];
        list.push(f);
        byLang.set(lang, list);
    }
    // `.h` is shared by C and C++, so `resolveGateLanguage` returns null for an
    // unlabelled one, and a planner that labels it `c` in a C++ project sends it
    // to the SEPARATE C staging dir. Either way the C++ files cannot find their
    // own header. Route EVERY `.h` to the gate the project actually uses — C++
    // when it has any C++ file, else C. Measured live: (a) a C to-hex tool whose
    // unlabelled header was dropped from both gates; (b) a C++ string-reverser
    // whose header was labelled `c` and split off, failing `#include
    // "string_reverser.h"`.
    const headerFiles = files.filter((f) => /\.h$/i.test(f.relPath));
    if (headerFiles.length) {
        const target = byLang.get('cpp')?.length ? 'cpp' : 'c';
        for (const lang of ['c', 'cpp']) {
            const bucket = byLang.get(lang);
            if (!bucket)
                continue;
            const rest = bucket.filter((f) => !/\.h$/i.test(f.relPath));
            if (rest.length)
                byLang.set(lang, rest);
            else
                byLang.delete(lang);
        }
        byLang.set(target, [...(byLang.get(target) || []), ...headerFiles]);
    }
    // ── Go: stage a module and build the whole set ─────────────────────────
    const goFiles = byLang.get('go');
    if (goFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-gobuild-'));
        // Auto-decide the staging layout: try the import-resolved layout first, and
        // only fall back to the naive per-file layout if it does not compile.
        // Whichever closes cleanly wins; a build verifies the choice rather than
        // trusting the heuristic.
        const resolved = planGoStaging(goFiles, moduleName);
        const naive = goFiles.map((f) => ({ relPath: goStagePath(f.relPath, f.code), code: f.code }));
        const sameLayout = JSON.stringify(resolved) === JSON.stringify(naive);
        // `go build ./...` writes each main package's binary into the CURRENT
        // directory, named after the package's own directory — so a `package main`
        // staged in `src/` fails with `go: build output "src" already exists and is
        // a directory` (measured live on a generated file-size CLI whose entry sat
        // in `src/`). Sending the binaries to a scratch dir keeps the check honest:
        // every package is still compiled, and nothing collides with the tree (a
        // dot-directory is ignored by `./...`, so the output cannot be re-gated).
        const binDir = path.join(dir, '.bin');
        const attempt = async (layout) => {
            fs.rmSync(dir, { recursive: true, force: true });
            fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(path.join(dir, 'go.mod'), `module ${moduleName}\n\ngo 1.21\n`);
            for (const f of layout)
                stageFile(dir, f.relPath, f.code);
            fs.mkdirSync(binDir, { recursive: true });
            return runTool(toolchainBin('go'), ['build', '-o', `${binDir}/`, './...'], { cwd: dir, timeout: 90000, });
        };
        try {
            let r = await attempt(resolved);
            if (!r.ok && !sameLayout) {
                const fallback = await attempt(naive);
                if (fallback.ok)
                    r = fallback;
            }
            pushGate(gates, 'go', r.ok ? [] : [r.error]);
        }
        catch (err) {
            pushGate(gates, 'go', [`go build staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── Python: py_compile per file ────────────────────────────────────────
    const pyFiles = byLang.get('python');
    if (pyFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-pygate-'));
        try {
            const absFiles = pyFiles.map((f) => stageFile(dir, f.relPath, f.code));
            const failures = await perFileGate(toolchainBin('python'), (abs) => ['-m', 'py_compile', abs], absFiles, dir, 30000);
            pushGate(gates, 'python', failures);
        }
        catch (err) {
            pushGate(gates, 'python', [`py_compile staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── Rust: typecheck the module tree through its entry file ─────────────
    const rustFiles = byLang.get('rust');
    if (rustFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-rustgate-'));
        try {
            for (const f of rustFiles)
                stageFile(dir, f.relPath, f.code);
            // Prefer the file carrying `fn main` (a bin crate's root); else the first
            // file. `--crate-type lib` accepts a stray main fn, and compiling the
            // root resolves `mod x;` siblings staged at their relative paths.
            const entry = rustFiles.find((f) => /\bfn\s+main\s*\(/.test(f.code)) || rustFiles[0];
            const entryAbs = path.join(dir, ...entry.relPath.replace(/^[/\\]+/, '').split(/[/\\]+/));
            const r = await runTool(toolchainBin('rust'), ['--edition', '2021', '--crate-type', 'lib', '--emit=metadata', entryAbs], { cwd: dir, timeout: 90000 });
            pushGate(gates, 'rust', r.ok ? [] : [r.error]);
        }
        catch (err) {
            pushGate(gates, 'rust', [`rustc staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── C / C++: syntax-only per file ──────────────────────────────────────
    const cFiles = byLang.get('c');
    if (cFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-cgate-'));
        try {
            const absFiles = cFiles.map((f) => stageFile(dir, f.relPath, f.code));
            const includes = includeDirsFor(dir, absFiles).flatMap((d) => ['-I', d]);
            const failures = await perFileGate(toolchainBin('c'), (abs) => ['-fsyntax-only', '-std=c11', ...includes, abs], absFiles, dir, 60000);
            pushGate(gates, 'c', failures);
        }
        catch (err) {
            pushGate(gates, 'c', [`gcc staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    const cppFiles = byLang.get('cpp');
    if (cppFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-cppgate-'));
        try {
            const absFiles = cppFiles.map((f) => stageFile(dir, f.relPath, f.code));
            const includes = includeDirsFor(dir, absFiles).flatMap((d) => ['-I', d]);
            const failures = await perFileGate(toolchainBin('cpp'), (abs) => ['-fsyntax-only', '-std=c++17', ...includes, abs], absFiles, dir, 60000);
            pushGate(gates, 'cpp', failures);
        }
        catch (err) {
            pushGate(gates, 'cpp', [`g++ staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── Java: compile the whole set into a classes dir ─────────────────────
    const javaFiles = byLang.get('java');
    if (javaFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-javagate-'));
        try {
            const absFiles = javaFiles.map((f) => stageFile(dir, f.relPath, f.code));
            const classes = path.join(dir, '__classes__');
            fs.mkdirSync(classes, { recursive: true });
            const errors = await wholeSetGate(toolchainBin('java'), ['-d', classes, ...absFiles], dir, 90000);
            pushGate(gates, 'java', errors);
        }
        catch (err) {
            pushGate(gates, 'java', [`javac staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── C#: compile the whole set to a library (csc / Roslyn) ──────────────
    const csFiles = byLang.get('csharp');
    if (csFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-csgate-'));
        try {
            const absFiles = csFiles.map((f) => stageFile(dir, f.relPath, f.code));
            const csBin = toolchainBin('csharp');
            let errors;
            // `toolchainBin` returns an ABSOLUTE path when dotnet is found (the normal
            // case), so compare the basename — a bare-name `=== 'dotnet'` check was
            // always false, so it silently ran `dotnet -nologo -target:library …`
            // instead of `dotnet build`, which fails with "Could not execute because
            // the specified command or file was not found". Every valid C# project
            // with a real dotnet on the machine was reported as broken.
            const csIsDotnet = path.basename(csBin).toLowerCase().replace(/\.exe$/, '') === 'dotnet';
            if (csIsDotnet) {
                // `csc` is not on PATH in a normal .NET SDK install — drive the SDK
                // instead. A project file with default compile items picks up every
                // staged .cs file under the workspace.
                fs.writeFileSync(path.join(dir, 'app.csproj'), '<Project Sdk="Microsoft.NET.Sdk">\n' +
                    '  <PropertyGroup>\n' +
                    '    <OutputType>Library</OutputType>\n' +
                    '    <TargetFramework>net8.0</TargetFramework>\n' +
                    '    <ImplicitUsings>disable</ImplicitUsings>\n' +
                    '    <Nullable>disable</Nullable>\n' +
                    '  </PropertyGroup>\n' +
                    '</Project>\n');
                errors = await wholeSetGate(csBin, ['build', '-nologo', '-v', 'q', path.join(dir, 'app.csproj')], dir, 150000);
            }
            else {
                errors = await wholeSetGate(csBin, ['-nologo', '-target:library', `-out:${path.join(dir, 'out.dll')}`, ...absFiles], dir, 90000);
            }
            pushGate(gates, 'csharp', errors);
        }
        catch (err) {
            pushGate(gates, 'csharp', [`csc staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── Swift: whole-module typecheck ──────────────────────────────────────
    const swiftFiles = byLang.get('swift');
    if (swiftFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-swiftgate-'));
        try {
            const absFiles = swiftFiles.map((f) => stageFile(dir, f.relPath, f.code));
            const errors = await wholeSetGate(toolchainBin('swift'), ['-typecheck', ...absFiles], dir, 120000);
            pushGate(gates, 'swift', errors);
        }
        catch (err) {
            pushGate(gates, 'swift', [`swiftc staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── Kotlin: compile the whole set ──────────────────────────────────────
    const kotlinFiles = byLang.get('kotlin');
    if (kotlinFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-ktgate-'));
        try {
            const absFiles = kotlinFiles.map((f) => stageFile(dir, f.relPath, f.code));
            const errors = await wholeSetGate(toolchainBin('kotlin'), [...absFiles, '-d', path.join(dir, 'out.jar')], dir, 150000);
            if (errors.length === 0) {
                // A jar that compiles but carries no Main-Class cannot be launched.
                const { read, mainClass } = jarManifestInfo(path.join(dir, 'out.jar'));
                if (read && !mainClass) {
                    errors.push(`${pickEntryCandidate(kotlinFiles, 'kotlin').relPath}: kotlinc produced a jar with no Main-Class: ` +
                        'the file set compiles but cannot be launched with `java -jar`. This happens when more ' +
                        'than one `fun main` is present (kotlinc cannot choose). VACA builds apps, not ' +
                        'libraries: leave exactly one `fun main`.');
                }
            }
            pushGate(gates, 'kotlin', errors);
        }
        catch (err) {
            pushGate(gates, 'kotlin', [`kotlinc staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── PHP: lint per file ─────────────────────────────────────────────────
    const phpFiles = byLang.get('php');
    if (phpFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-phpgate-'));
        try {
            const absFiles = phpFiles.filter((f) => !isConfigDotfile(f.relPath)).map((f) => stageFile(dir, f.relPath, f.code));
            const failures = await perFileGate(toolchainBin('php'), (abs) => ['-l', abs], absFiles, dir, 30000);
            pushGate(gates, 'php', failures);
        }
        catch (err) {
            pushGate(gates, 'php', [`php -l staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── Ruby: syntax check per file ────────────────────────────────────────
    const rubyFiles = byLang.get('ruby');
    if (rubyFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-rubygate-'));
        try {
            const absFiles = rubyFiles.filter((f) => !isConfigDotfile(f.relPath)).map((f) => stageFile(dir, f.relPath, f.code));
            const failures = await perFileGate(toolchainBin('ruby'), (abs) => ['-c', abs], absFiles, dir, 30000);
            pushGate(gates, 'ruby', failures);
        }
        catch (err) {
            pushGate(gates, 'ruby', [`ruby -c staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── JavaScript: syntax check per file (node --check) ───────────────────
    // A JS build used to fall through every gate and report the catch-all
    // "no gate applied (unverified)". `node --check` parses the file without
    // executing it, so a real syntax error (unclosed brace, stray token) is
    // caught while Node's own module-type detection accepts both ESM (`import`/
    // `export`) and CommonJS shapes.
    const jsFiles = byLang.get('javascript');
    if (jsFiles?.length) {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vaca-jsgate-'));
        try {
            const absFiles = jsFiles.filter((f) => !isConfigDotfile(f.relPath)).map((f) => stageFile(dir, f.relPath, f.code));
            const failures = await perFileGate(toolchainBin('javascript'), (abs) => ['--check', abs], absFiles, dir, 30000);
            pushGate(gates, 'javascript', failures);
        }
        catch (err) {
            pushGate(gates, 'javascript', [`node --check staging failed: ${err?.message || err}`]);
        }
        finally {
            try {
                fs.rmSync(dir, { recursive: true, force: true });
            }
            catch { /* noop */ }
        }
    }
    // ── Entry-point gate ───────────────────────────────────────────────────
    // A build that compiles but has NO runnable entry point is rejected here.
    // The compile gates above only prove the code parses/links; a library-shaped
    // fragment (a Python file of bare functions, a PHP file of only `function`
    // definitions) passes them and then cannot be run at all. Folded into each
    // language's existing gate so callers see ONE verdict per language.
    const entryFoldSource = opts?.scaffoldSuppliesEntry ? [] : [...byLang];
    for (const [language, files] of entryFoldSource) {
        const entryErrors = entryGateErrors(files, language);
        if (!entryErrors.length)
            continue;
        const existing = gates.find((g) => g.language === language);
        if (existing) {
            existing.clean = false;
            existing.errors = [...entryErrors, ...existing.errors].slice(0, 10);
        }
        else {
            gates.push({ language, clean: false, errors: entryErrors });
        }
        console.warn(`[nonTsGate] ${language} entry-point gate: FAIL — ${entryErrors[0]?.slice(0, 160) || ''}`);
    }
    return gates;
}
