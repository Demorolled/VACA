import { describe, expect, it } from 'vitest';
import { isDeploymentRequest, ensureDeploymentArtifacts, ensureDockerfileArtifact, isTestRequest, ensureTestFiles, ensureTestArtifact, sanitizeInlineScripts, inlineModuleImports, inlineExternalScriptRefs, defuseUndefinedInlineHandlers, } from './guiShared.js';
// ═══════════════════════════════════════════════════════════════════════════
// isDeploymentRequest — deployment-intent detection
// ═══════════════════════════════════════════════════════════════════════════
describe('isDeploymentRequest (deployment-intent detection)', () => {
    it('detects Dockerfile / docker / deploy / containerize mentions', () => {
        expect(isDeploymentRequest('a full-stack note app with a Dockerfile for deployment')).toBe(true);
        expect(isDeploymentRequest('containerize this app')).toBe(true);
        expect(isDeploymentRequest('build a docker image')).toBe(true);
        expect(isDeploymentRequest('deploy scripts for production')).toBe(true);
        expect(isDeploymentRequest('k8s manifests')).toBe(true);
    });
    it('returns false for plain app requests', () => {
        expect(isDeploymentRequest('a todo list app with due dates')).toBe(false);
        expect(isDeploymentRequest('a pomodoro timer app')).toBe(false);
    });
    it('also scans answers (plan-time refinement answers may carry the intent)', () => {
        expect(isDeploymentRequest('a note-taking app', { q1: 'yes, with a Dockerfile' })).toBe(true);
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// ensureDeploymentArtifacts — plan-level enforcement
// ═══════════════════════════════════════════════════════════════════════════
describe('ensureDeploymentArtifacts (plan-level Dockerfile enforcement)', () => {
    const files = [
        { path: 'src/server.ts', summary: 'core', language: 'typescript', exports: [], uses: [] },
        { path: 'src/app.tsx', summary: 'ui', language: 'typescript', exports: [], uses: [] },
    ];
    it('appends a planned Dockerfile when deployment is requested and none is planned', () => {
        const out = ensureDeploymentArtifacts(files, 'a note app with a Dockerfile for deployment');
        expect(out.length).toBe(3);
        expect(out[2].path).toBe('Dockerfile');
        expect(out[2].language).toBe('dockerfile');
        expect(out[2].summary).toMatch(/multi-stage/i);
    });
    it('is a no-op without a deployment request', () => {
        expect(ensureDeploymentArtifacts(files, 'a todo list app')).toBe(files);
    });
    it('never duplicates an existing deploy artifact', () => {
        const withDocker = [...files, { path: 'Dockerfile', summary: 'x', language: 'dockerfile', exports: [], uses: [] }];
        expect(ensureDeploymentArtifacts(withDocker, 'deploy this with docker')).toBe(withDocker);
        const withCompose = [...files, { path: 'docker-compose.yml', summary: 'x', language: 'yaml', exports: [], uses: [] }];
        expect(ensureDeploymentArtifacts(withCompose, 'deploy this with docker')).toBe(withCompose);
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// ensureDockerfileArtifact — deterministic output-level guarantee
// ═══════════════════════════════════════════════════════════════════════════
describe('ensureDockerfileArtifact (deterministic output-level Dockerfile)', () => {
    it('injects a Node multi-stage Dockerfile when deployment is requested and none exists', () => {
        const files = [
            { path: 'src/server.ts', content: 'export const x = 1;' },
            { path: 'package.json', content: '{}' },
        ];
        const out = ensureDockerfileArtifact(files, 'a full-stack app with a Dockerfile for deployment');
        expect(out.length).toBe(3);
        const docker = out.find(f => f.path === 'Dockerfile');
        expect(docker.content).toContain('FROM node:20-alpine AS build');
        expect(docker.content).toContain('EXPOSE 3000');
    });
    it('is a no-op when the writer already emitted a Dockerfile', () => {
        const files = [
            { path: 'src/server.ts', content: 'export const x = 1;' },
            { path: 'Dockerfile', content: 'FROM python:3.12' },
        ];
        expect(ensureDockerfileArtifact(files, 'deploy this with docker')).toBe(files);
    });
    it('is a no-op without a deployment request', () => {
        const files = [{ path: 'src/server.ts', content: 'export const x = 1;' }];
        expect(ensureDockerfileArtifact(files, 'a todo list app')).toBe(files);
    });
    it('also recognizes docker-compose / deploy scripts as satisfying the guarantee', () => {
        const compose = [{ path: 'src/server.ts', content: 'export const x = 1;' }, { path: 'docker-compose.yml', content: 'x: 1' }];
        expect(ensureDockerfileArtifact(compose, 'deploy this with docker')).toBe(compose);
        const script = [{ path: 'src/server.ts', content: 'export const x = 1;' }, { path: 'deploy.sh', content: '#!/bin/sh' }];
        expect(ensureDockerfileArtifact(script, 'deploy this with docker')).toBe(script);
    });
    it('falls back to a generic Dockerfile when the project has no package.json', () => {
        const files = [{ path: 'src/main.py', content: 'print(1)' }];
        const out = ensureDockerfileArtifact(files, 'deploy this app');
        const docker = out.find(f => f.path === 'Dockerfile');
        expect(docker.content).toContain('CMD ["node", "src/index.js"]');
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// isTestRequest — test-intent detection
// ═══════════════════════════════════════════════════════════════════════════
describe('isTestRequest (test-intent detection)', () => {
    it('detects unit/integration test mentions', () => {
        expect(isTestRequest('a full-stack note app with unit tests')).toBe(true);
        expect(isTestRequest('write integration tests for the API')).toBe(true);
        expect(isTestRequest('a todo app with a test suite')).toBe(true);
        expect(isTestRequest('add vitest coverage')).toBe(true);
        expect(isTestRequest('pytest for the backend')).toBe(true);
    });
    it('returns false for plain app requests without test intent', () => {
        expect(isTestRequest('a todo list app with due dates')).toBe(false);
        expect(isTestRequest('a pomodoro timer app')).toBe(false);
    });
    it('also scans answers (plan-time refinement answers may carry the intent)', () => {
        expect(isTestRequest('a note-taking app', { q1: 'yes, include unit tests' })).toBe(true);
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// ensureTestFiles — plan-level enforcement
// ═══════════════════════════════════════════════════════════════════════════
describe('ensureTestFiles (plan-level test enforcement)', () => {
    const files = [
        { path: 'src/server.ts', summary: 'core', language: 'typescript', exports: [], uses: [] },
        { path: 'src/app.tsx', summary: 'ui', language: 'typescript', exports: [], uses: [] },
    ];
    it('appends a planned test file when tests are requested and none is planned', () => {
        const out = ensureTestFiles(files, 'a note app with unit tests');
        expect(out.length).toBe(3);
        expect(out[2].path).toBe('tests/app.test.ts');
        expect(out[2].language).toBe('typescript');
        expect(out[2].summary).toMatch(/check helper/i);
    });
    it('is a no-op without a test request', () => {
        expect(ensureTestFiles(files, 'a todo list app')).toBe(files);
    });
    it('never duplicates an existing test file', () => {
        const withTest = [...files, { path: 'tests/app.test.ts', summary: 'x', language: 'typescript', exports: [], uses: [] }];
        expect(ensureTestFiles(withTest, 'unit tests please')).toBe(withTest);
        const withSpec = [...files, { path: 'src/app.spec.ts', summary: 'x', language: 'typescript', exports: [], uses: [] }];
        expect(ensureTestFiles(withSpec, 'unit tests please')).toBe(withSpec);
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// ensureTestArtifact — deterministic output-level guarantee
// ═══════════════════════════════════════════════════════════════════════════
describe('ensureTestArtifact (deterministic output-level test file)', () => {
    it('injects a self-contained smoke test when tests are requested and none exists', () => {
        const files = [{ path: 'src/server.ts', content: 'export const x = 1;' }];
        const out = ensureTestArtifact(files, 'a full-stack note app with unit tests');
        expect(out.length).toBe(2);
        const test = out.find(f => f.path === 'tests/smoke.test.ts');
        expect(test.content).toContain('export {}');
        expect(test.content).toContain('function check(name: string, cond: boolean): void');
        expect(test.content).toContain('1 + 1 === 2');
    });
    it('is a no-op when the writer already emitted a test file', () => {
        const files = [
            { path: 'src/server.ts', content: 'export const x = 1;' },
            { path: 'tests/app.test.ts', content: 'export {};' },
        ];
        expect(ensureTestArtifact(files, 'unit tests please')).toBe(files);
    });
    it('is a no-op without a test request', () => {
        const files = [{ path: 'src/server.ts', content: 'export const x = 1;' }];
        expect(ensureTestArtifact(files, 'a todo list app')).toBe(files);
    });
    it('also recognizes __tests__ / .spec. paths as satisfying the guarantee', () => {
        const dir = [{ path: 'src/server.ts', content: 'export const x = 1;' }, { path: '__tests__/server.test.ts', content: 'export {};' }];
        expect(ensureTestArtifact(dir, 'unit tests please')).toBe(dir);
        const spec = [{ path: 'src/server.ts', content: 'export const x = 1;' }, { path: 'src/server.spec.ts', content: 'export {};' }];
        expect(ensureTestArtifact(spec, 'unit tests please')).toBe(spec);
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// sanitizeInlineScripts — the entry's OWN inline <script> must be runnable
// ═══════════════════════════════════════════════════════════════════════════
describe('sanitizeInlineScripts (entry inline scripts must be browser JS)', () => {
    const bodyOf = (html) => {
        const m = /<script[^>]*>([\s\S]*?)<\/script>/i.exec(html);
        return m ? m[1] : '';
    };
    // Same oracle the sanitizer uses: does this parse as a classic browser script?
    const parsesAsClassicJs = (code) => {
        try {
            // eslint-disable-next-line @typescript-eslint/no-implied-eval
            new Function(code);
            return true;
        }
        catch {
            return false;
        }
    };
    it('strips TypeScript annotations written directly into the entry script', () => {
        // Real failure mode: an app shipped `function isGameOver(board: number[]): boolean`
        // inline and the browser died with "Unexpected token ':'".
        const html = `<!doctype html><html><body><script>
      function isGameOver(board: number[]): boolean { return board.length === 9; }
    </script></body></html>`;
        const out = sanitizeInlineScripts(html);
        expect(out).not.toContain('board: number[]');
        expect(out).not.toContain('): boolean');
        expect(parsesAsClassicJs(bodyOf(out))).toBe(true);
    });
    it('strips ES-module import/export from the entry script', () => {
        // Real failure mode: "Cannot use import statement outside a module".
        const html = `<!doctype html><html><body><script>
      import { AI } from './ai.js';
      export class Game { start() { return 1; } }
      new Game().start();
    </script></body></html>`;
        const out = sanitizeInlineScripts(html);
        expect(/\bimport\s/.test(bodyOf(out))).toBe(false);
        expect(/\bexport\s/.test(bodyOf(out))).toBe(false);
        expect(parsesAsClassicJs(bodyOf(out))).toBe(true);
    });
    it('leaves already-valid classic JS byte-for-byte', () => {
        const html = `<!doctype html><html><body><script>\n  const x = 1;\n  document.title = String(x);\n</script></body></html>`;
        expect(sanitizeInlineScripts(html)).toBe(html);
    });
    it('leaves non-JS script types and external scripts untouched', () => {
        const json = `<!doctype html><html><body><script type="application/json">{"a": 1}</script></body></html>`;
        expect(sanitizeInlineScripts(json)).toBe(json);
        const ext = `<!doctype html><html><body><script src="./app.js"></script></body></html>`;
        expect(sanitizeInlineScripts(ext)).toBe(ext);
    });
    it('is applied by inlineExternalScriptRefs so the written entry is runnable', () => {
        const files = [{ path: 'index.html', content: `<!doctype html><html><body><script>\nfunction f(n: number): number { return n; }\n</script></body></html>` }];
        inlineExternalScriptRefs(files);
        expect(files[0].content).not.toContain('n: number');
        expect(parsesAsClassicJs(bodyOf(files[0].content))).toBe(true);
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// inlineModuleImports — sibling ES imports must be bundled into the entry
// ═══════════════════════════════════════════════════════════════════════════
describe('inlineModuleImports (bundle sibling ES imports into the entry)', () => {
    it('inlines a sibling import and drops the import statement', () => {
        const files = [
            { path: 'index.html', content: `<html><body><script>\nimport { AI } from './ai.js';\nconst g = new AI();\ng.move();\n</script></body></html>` },
            { path: 'src/ai.js', content: 'export class AI { move() { return 1; } }' },
        ];
        inlineModuleImports(files);
        expect(files[0].content).not.toMatch(/^\s*import\s/m);
        expect(files[0].content).not.toContain('export class');
        expect(files[0].content).toContain('class AI');
        // The importer's own code must still be present after the dependency.
        expect(files[0].content.indexOf('class AI')).toBeLessThan(files[0].content.indexOf('new AI()'));
    });
    it('resolves an extension mismatch (./ai.js imports a sibling ai.ts) and strips its types', () => {
        const files = [
            { path: 'index.html', content: `<html><body><script>\nimport { AI } from './ai.js';\nnew AI();\n</script></body></html>` },
            { path: 'src/ai.ts', content: 'export class AI { move(n: number): number { return n; } }' },
        ];
        inlineModuleImports(files);
        expect(files[0].content).toContain('class AI');
        expect(files[0].content).not.toContain('n: number');
    });
    it('inlines transitively in dependency order (dependency before its importer)', () => {
        const files = [
            { path: 'index.html', content: `<html><body><script>\nimport { Game } from './game.js';\nnew Game();\n</script></body></html>` },
            { path: 'game.js', content: `import { AI } from './ai.js';\nexport class Game { constructor() { this.ai = new AI(); } }` },
            { path: 'ai.js', content: 'export class AI { move() { return 1; } }' },
        ];
        inlineModuleImports(files);
        const html = files[0].content;
        expect(html).toContain('class AI');
        expect(html).toContain('class Game');
        expect(html.indexOf('class AI')).toBeLessThan(html.indexOf('class Game'));
    });
    it('leaves an unresolvable relative import untouched (never silently drops code)', () => {
        const files = [{ path: 'index.html', content: `<html><body><script>\nimport { X } from './missing.js';\nX();\n</script></body></html>` }];
        inlineModuleImports(files);
        expect(files[0].content).toContain("import { X } from './missing.js'");
    });
    it('leaves bare/package imports untouched', () => {
        const files = [{ path: 'index.html', content: `<html><body><script>\nimport React from 'react';\nReact;\n</script></body></html>` }];
        inlineModuleImports(files);
        expect(files[0].content).toContain("import React from 'react'");
    });
    it('is applied by inlineExternalScriptRefs', () => {
        const files = [
            { path: 'index.html', content: `<html><body><script>\nimport { AI } from './ai.js';\nnew AI();\n</script></body></html>` },
            { path: 'ai.js', content: 'export class AI {}' },
        ];
        inlineExternalScriptRefs(files);
        expect(files[0].content).not.toMatch(/^\s*import\s/m);
        expect(files[0].content).toContain('class AI');
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// defuseUndefinedInlineHandlers — a handler that calls nothing defined
// ═══════════════════════════════════════════════════════════════════════════
describe('defuseUndefinedInlineHandlers (dead inline handlers must not crash)', () => {
    it('defuses a handler calling a function nothing defines', () => {
        const html = `<html><body><button onclick="startGame()">Go</button><script>const x = 1;</script></body></html>`;
        const out = defuseUndefinedInlineHandlers(html);
        expect(out).toContain("typeof startGame === 'function'");
        // Must still be valid JS, and run without throwing when the name is missing.
        const body = /onclick="([^"]*)"/.exec(out)[1];
        // eslint-disable-next-line @typescript-eslint/no-implied-eval
        expect(() => new Function(body)).not.toThrow();
    });
    it('leaves a handler alone when the function is defined', () => {
        const html = `<html><body><button onclick="startGame()">Go</button><script>function startGame(){}</script></body></html>`;
        expect(defuseUndefinedInlineHandlers(html)).toBe(html);
    });
    it('also recognises const/let/var, class and window.* definitions', () => {
        for (const def of ['const go = () => {};', 'let go = function(){};', 'class go {}', 'window.go = () => {};']) {
            const html = `<html><body><a onclick="go()">x</a><script>${def}</script></body></html>`;
            expect(defuseUndefinedInlineHandlers(html)).toBe(html);
        }
    });
    it('never touches browser built-ins', () => {
        const html = `<html><body><button onclick="alert('hi')">Go</button></body></html>`;
        expect(defuseUndefinedInlineHandlers(html)).toBe(html);
    });
    it('defuses only the bare call in a mixed handler, never the method call', () => {
        const html = `<html><body><a href="#" onclick="event.preventDefault();go('home')">H</a><script>const y = 1;</script></body></html>`;
        const out = defuseUndefinedInlineHandlers(html);
        expect(out).toContain('event.preventDefault()');
        expect(out).toContain("typeof go === 'function'");
    });
    it('is idempotent', () => {
        const html = `<html><body><button onclick="startGame()">Go</button><script>const x = 1;</script></body></html>`;
        const once = defuseUndefinedInlineHandlers(html);
        expect(defuseUndefinedInlineHandlers(once)).toBe(once);
    });
    it('skips the document when an external <script src> could define the name', () => {
        const html = `<html><body><button onclick="startGame()">Go</button><script src="./app.js"></script></body></html>`;
        expect(defuseUndefinedInlineHandlers(html)).toBe(html);
    });
    it('is applied by inlineExternalScriptRefs', () => {
        const files = [{ path: 'index.html', content: `<html><body><button onclick="startGame()">Go</button><script>const x=1;</script></body></html>` }];
        inlineExternalScriptRefs(files);
        expect(files[0].content).toContain("typeof startGame === 'function'");
    });
});
