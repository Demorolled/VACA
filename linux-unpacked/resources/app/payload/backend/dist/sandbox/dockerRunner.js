/**
 * Docker Sandbox Runner
 * ======================
 * Executes generated code in a Docker container (or locally as fallback).
 * Supports TypeScript, Python, Go, and other languages via configurable images.
 *
 * Flow:
 *   1. Write generated code to a temp directory
 *   2. Spin up Docker container (or fallback to local exec)
 *   3. Run typecheck / test / build commands
 *   4. Capture stdout, stderr, exit code
 *   5. Cleanup temp directory
 *   6. Return results
 */
import { execSync } from 'child_process';
import { mkdirSync, writeFileSync, rmSync } from 'fs';
import { join, dirname } from 'path';
import { tmpdir } from 'os';
import { randomBytes } from 'crypto';
import { toolchainBin } from './nonTsCompileGate.js';
// ─── Config ────────────────────────────────────────────────────────────────
const DOCKER_ENABLED = process.env.DOCKER_ENABLED === 'true';
const SANDBOX_TIMEOUT = parseInt(process.env.SANDBOX_TIMEOUT || '30000', 10);
const SANDBOX_CONFIGS = {
    typescript: {
        image: 'node:20-alpine',
        checkCmd: ['sh', '-c', 'cd /sandbox && npx --package typescript tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution bundler --esModuleInterop --skipLibCheck --allowImportingTsExtensions index.ts 2>&1'],
        fileExtension: '.ts',
        entrypoint: 'index.ts',
        installCmd: ['sh', '-c', 'cd /sandbox && npm init -y && npm install typescript @types/node 2>&1'],
    },
    javascript: {
        image: 'node:20-alpine',
        checkCmd: ['sh', '-c', 'cd /sandbox && node --check index.js 2>&1'],
        fileExtension: '.js',
        entrypoint: 'index.js',
    },
    python: {
        image: 'python:3.12-alpine',
        checkCmd: ['sh', '-c', 'cd /sandbox && python3 -m py_compile main.py 2>&1'],
        fileExtension: '.py',
        entrypoint: 'main.py',
    },
    go: {
        image: 'golang:1.22-alpine',
        checkCmd: ['sh', '-c', 'cd /sandbox && go vet ./... 2>&1'],
        fileExtension: '.go',
        entrypoint: 'main.go',
        installCmd: ['sh', '-c', 'cd /sandbox && go mod init sandbox 2>&1'],
    },
    rust: {
        image: 'rust:1.78-alpine',
        checkCmd: ['sh', '-c', 'cd /sandbox && cargo check 2>&1'],
        fileExtension: '.rs',
        entrypoint: 'src/main.rs',
        installCmd: ['sh', '-c', 'cd /sandbox && cargo init 2>&1'],
    },
};
// ─── Helpers ───────────────────────────────────────────────────────────────
function generateTempDir() {
    const id = randomBytes(8).toString('hex');
    const dir = join(tmpdir(), 'sandbox', id);
    mkdirSync(dir, { recursive: true });
    return dir;
}
export function detectLanguage(code) {
    const lines = code.split('\n').filter(l => l.trim());
    if (lines.some(l => l.includes('import React') || l.includes('from \'react\'')))
        return 'typescript';
    if (lines.some(l => l.includes('use strict') || l.includes('require(') || l.includes('module.exports')))
        return 'javascript';
    if (lines.some(l => l.includes('def ') || l.includes('import ') && l.includes('as') && !l.includes('{') && !l.includes('from')))
        return 'python';
    if (lines.some(l => l.includes('func main') || l.includes('package main')))
        return 'go';
    if (lines.some(l => l.includes('fn main') || l.includes('fn ') && l.includes('->')))
        return 'rust';
    // Default: check for TypeScript syntax
    if (lines.some(l => l.includes(': string') || l.includes(': number') || l.includes('interface ')))
        return 'typescript';
    if (lines.some(l => l.includes('console.log')))
        return 'javascript';
    return 'typescript';
}
/**
 * The Docker config for a language, or null when no image handles it.
 *
 * This used to fall back to `SANDBOX_CONFIGS.typescript` for EVERY language it
 * did not know, which compiled non-TS source with the TypeScript image (a C
 * file written to `index.ts`). Null means "cannot check", never "check it as
 * TypeScript" — see the `skipped` results below.
 */
function getConfig(language) {
    return SANDBOX_CONFIGS[(language || '').toLowerCase()] || null;
}
function writeCodeToTempDir(code, config, dir) {
    const filePath = join(dir, config.entrypoint);
    // Create parent directories if needed (recursive handles nested paths)
    mkdirSync(dirname(filePath), { recursive: true });
    writeFileSync(filePath, code, 'utf-8');
    return filePath;
}
// ─── Docker Execution ──────────────────────────────────────────────────────
async function runInDocker(code, language, timeout) {
    const config = getConfig(language);
    if (!config) {
        return {
            success: false,
            output: '',
            errors: [],
            exitCode: 0,
            skipped: true,
            reason: `Docker sandbox has no image for '${language}' — this file was not validated.`,
        };
    }
    const tempDir = generateTempDir();
    try {
        writeCodeToTempDir(code, config, tempDir);
        // Mount temp dir as /sandbox inside container
        const mountArg = `-v ${tempDir}:/sandbox`;
        const image = config.image;
        // Pull image if not present (first time)
        try {
            execSync(`docker image inspect ${image} 2>/dev/null || docker pull ${image}`, { timeout: 60000, stdio: 'ignore' });
        }
        catch {
            // Image pull failed — fall through to local execution
            return runLocally(code, language, timeout, 'docker');
        }
        // Run install commands if needed
        if (config.installCmd && config.installCmd.length > 0) {
            try {
                const installArgs = ['run', '--rm', mountArg, '-w', '/sandbox', image, ...config.installCmd];
                execSync(`docker ${installArgs.join(' ')}`, { timeout: 60000, stdio: 'pipe' });
            }
            catch (err) {
                // Install failed, but we can still try the check
            }
        }
        // Run the check command
        try {
            const checkArgs = ['run', '--rm', mountArg, '-w', '/sandbox', image, ...config.checkCmd];
            const output = execSync(`docker ${checkArgs.join(' ')}`, {
                timeout,
                encoding: 'utf-8',
                stdio: 'pipe',
            });
            return {
                success: true,
                output: output.trim(),
                errors: [],
                exitCode: 0,
            };
        }
        catch (err) {
            const stderr = err.stderr?.toString() || '';
            const stdout = err.stdout?.toString() || '';
            return {
                success: false,
                output: stdout.trim(),
                errors: [stderr.trim() || stdout.trim() || `Docker check failed with code ${err.status}`],
                exitCode: err.status || 1,
            };
        }
    }
    finally {
        // Cleanup temp directory
        try {
            rmSync(tempDir, { recursive: true, force: true });
        }
        catch { /* noop */ }
    }
}
// ─── Local Execution (Fallback) ────────────────────────────────────────────
// NOTE: no tsconfig.json is written for the local TS check (runLocally) —
// when a config exists and files are also passed on the command line, tsc
// emits TS5112 ("tsconfig.json is present but will not be loaded") and marks
// otherwise-clean generated files as failing. All needed options are passed
// explicitly below (target ES2022 → default lib includes DOM; bundler
// resolution replaces the removed 'node'/'node10' value).
const TSC_ARGS = [
    '--noEmit', '--strict', '--target', 'ES2022', '--module', 'ESNext',
    '--moduleResolution', 'bundler', '--esModuleInterop', '--skipLibCheck',
    '--allowImportingTsExtensions',
];
/** The type a Java file declares — javac requires `Foo` in `Foo.java`. */
function javaEntryFileName(code) {
    const m = /^\s*(?:public\s+)?(?:final\s+|abstract\s+|sealed\s+|non-sealed\s+)*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)/m.exec(code || '');
    return m ? `${m[1]}.java` : 'Main.java';
}
const LOCAL_TOOL_CHECK = {
    typescript: {
        check: 'npx --package typescript tsc --version',
        entrypoint: () => 'index.ts',
        run: (staged) => ['npx', '--package', 'typescript', 'tsc', ...TSC_ARGS, staged],
    },
    javascript: {
        check: 'node --version',
        entrypoint: () => 'index.js',
        run: (staged) => ['node', '--check', staged],
    },
    python: {
        check: 'python3 --version',
        entrypoint: () => 'main.py',
        run: (staged) => ['python3', '-m', 'py_compile', staged],
    },
    go: {
        check: 'go version',
        entrypoint: () => 'main.go',
        run: (staged) => ['go', 'vet', staged],
    },
    rust: {
        // `cargo check` needs a Cargo.toml the sandbox never writes — it failed on
        // every Rust file whenever the staging write got that far. rustc typechecks
        // a single file directly (the same command the Rust project gate uses).
        check: 'rustc --version',
        entrypoint: () => 'main.rs',
        run: (staged) => [toolchainBin('rust'), '--edition', '2021', '--crate-type', 'lib', '--emit=metadata', staged],
    },
    c: {
        check: 'gcc --version',
        entrypoint: () => 'main.c',
        run: (staged) => [toolchainBin('c'), '-fsyntax-only', '-std=c11', staged],
    },
    cpp: {
        check: 'g++ --version',
        entrypoint: () => 'main.cpp',
        run: (staged) => [toolchainBin('cpp'), '-fsyntax-only', '-std=c++17', staged],
    },
    java: {
        check: 'javac -version',
        entrypoint: javaEntryFileName,
        prepare: (dir) => mkdirSync(join(dir, '__classes__'), { recursive: true }),
        run: (staged, dir) => [toolchainBin('java'), '-d', join(dir, '__classes__'), staged],
    },
    php: {
        check: 'php --version',
        entrypoint: () => 'index.php',
        run: (staged) => ['php', '-l', staged],
    },
    ruby: {
        check: 'ruby --version',
        entrypoint: () => 'main.rb',
        run: (staged) => ['ruby', '-c', staged],
    },
    swift: {
        check: 'swiftc --version',
        entrypoint: () => 'main.swift',
        run: (staged) => [toolchainBin('swift'), '-typecheck', staged],
    },
};
async function runLocally(code, language, timeout, fromMethod = 'local') {
    const tempDir = generateTempDir();
    const fallbackReason = fromMethod === 'docker' ? 'Docker' : 'Local';
    const tool = LOCAL_TOOL_CHECK[(language || '').toLowerCase()];
    // No checker for this language: report the file as UNCHECKED, never as broken.
    // (Errors are empty on purpose — a file must not be marked failed because the
    // sandbox could not read it.)
    if (!tool) {
        return {
            success: false,
            output: '',
            errors: [],
            exitCode: 0,
            skipped: true,
            reason: `${fallbackReason} sandbox has no checker for '${language}' — this file was not validated.`,
        };
    }
    try {
        const entryName = tool.entrypoint(code);
        const staged = join(tempDir, entryName);
        // An entry point may live in a subdirectory: the raw write threw ENOENT and
        // surfaced as "Sandbox validation unavailable" on EVERY Rust file.
        mkdirSync(dirname(staged), { recursive: true });
        writeFileSync(staged, code, 'utf-8');
        tool.prepare?.(tempDir);
        // For TypeScript, create a package.json (module context) but NO tsconfig.json:
        // a config in the cwd + explicit file args makes tsc emit TS5112 and mark
        // otherwise-clean code as failing. The tsc options live on the command line.
        if (language === 'typescript') {
            writeFileSync(join(tempDir, 'package.json'), JSON.stringify({ name: 'sandbox', private: true, type: 'module' }), 'utf-8');
        }
        // For Go, create go.mod
        if (language === 'go') {
            try {
                execSync('cd ' + tempDir + ' && go mod init sandbox 2>/dev/null', { timeout: 10000, stdio: 'ignore' });
            }
            catch { }
        }
        // Run the check command locally
        const args = tool.run(staged, tempDir);
        try {
            const output = execSync(args.join(' '), {
                timeout,
                encoding: 'utf-8',
                stdio: 'pipe',
                cwd: tempDir,
            });
            return {
                success: true,
                output: output.trim(),
                errors: [],
                exitCode: 0,
            };
        }
        catch (err) {
            const stderr = err.stderr?.toString() || '';
            const stdout = err.stdout?.toString() || '';
            return {
                success: false,
                output: stdout.trim(),
                errors: [stderr.trim() || stdout.trim() || `Check failed with code ${err.status}`],
                exitCode: err.status || 1,
            };
        }
    }
    finally {
        try {
            rmSync(tempDir, { recursive: true, force: true });
        }
        catch { /* noop */ }
    }
}
// ─── Public API ────────────────────────────────────────────────────────────
/**
 * Run generated code validation in a sandboxed environment.
 * Uses Docker if available, falls back to local execution.
 */
export async function runSandbox(code, language, timeout) {
    const lang = language || detectLanguage(code);
    const t = timeout || SANDBOX_TIMEOUT;
    if (DOCKER_ENABLED) {
        try {
            return await runInDocker(code, lang, t);
        }
        catch (err) {
            // Docker failed — fall back to local
            console.warn(`[sandbox] Docker execution failed: ${err.message}. Falling back to local.`);
            return runLocally(code, lang, t, 'docker');
        }
    }
    return runLocally(code, lang, t);
}
/**
 * Check which sandbox tools are available on this system.
 */
export function checkSandboxAvailability() {
    const docker = DOCKER_ENABLED && (() => {
        try {
            execSync('docker --version', { stdio: 'ignore' });
            return true;
        }
        catch {
            return false;
        }
    })();
    const local = [];
    for (const [lang, tool] of Object.entries(LOCAL_TOOL_CHECK)) {
        try {
            execSync(tool.check, { stdio: 'ignore' });
            local.push(lang);
        }
        catch { /* not available */ }
    }
    return { docker: !!docker, local };
}
