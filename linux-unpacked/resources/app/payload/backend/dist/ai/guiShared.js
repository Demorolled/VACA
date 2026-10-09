/**
 * Shared GUI helpers — used by BOTH the chat/CLI build path (codePlanner) and
 * the canvas node-based path (fileGenerator). Kept in a neutral module so a
 * layers/ file can import them without triggering route-module side effects
 * (Router()/AITranslator instantiation).
 *
 *   - isGuiRequest:           intent detection from request text + user answers
 *   - ensureGuiEntryFile:     plan-level guarantee of an index.html entry
 *   - GUI_WIDGET_SECTION:     verbatim HTML widget templates for small models
 *   - inlineExternalScriptRefs: self-containment fix (inline <script>/<link>
 *                             refs) so the srcdoc preview never renders white
 *   - sanitizeInlineScripts:  makes the entry's OWN inline <script> runnable
 *                             (strips raw TS / ES-module syntax)
 *   - stripTypeScript:        .ts→browser-JS conversion for inlined siblings
 */
import ts from 'typescript';
/**
 * Concrete HTML widget templates handed to the writer for GUI entry files.
 * Small models reinvent UI code (and produce invalid elements — e.g. a <div>
 * standing in for <video>) when left on their own. Giving them verbatim,
 * correct snippets raises the floor on every GUI build.
 */
export const GUI_WIDGET_SECTION = `
━━━ HTML WIDGET TEMPLATES (copy these EXACT patterns — do not invent new element types) ━━━

⚠️ HANDLERS MUST RESOLVE. The on* names below are PLACEHOLDERS. Every inline
   handler (onclick/oninput/onchange/…) MUST call a function you actually DEFINE
   in this file's <script>. Copy the button SHAPES, but rename the handler to
   your app's real function and define it. An inline handler that calls an
   undefined function throws "… is not defined" on the very first click, so the
   whole app fails its runtime check.

LAYOUT:
  <div class="row" style="display:flex;gap:10px;align-items:center"> ...children... </div>
  <div class="col" style="display:flex;flex-direction:column;gap:10px"> ...children... </div>
  <div class="grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px"> ...cards... </div>
  Main shell: <div class="app" style="max-width:960px;margin:0 auto;padding:24px"> ... </div>

BUTTON — the onclick name MUST be a function you define in the SAME <script>:
  <button id="playBtn" class="btn" onclick="startGame()">▶ Play</button>
  <button id="saveBtn" class="btn btn-primary" onclick="saveItem()">💾 Save</button>
  <button id="delBtn" class="btn btn-danger" onclick="deleteItem()">✕ Delete</button>
  <script>
    function startGame()  { /* your real logic here — never leave it undefined */ }
    function saveItem()   { /* ... */ }
    function deleteItem() { /* ... */ }
  </script>
  ⚠️ Do NOT emit onclick="play()" / save() / remove() / openItem() / go() unless
     you ALSO define that exact function — those names are placeholders, not
     built-ins. Replace them with your app's real function names.
  Disabled state: <button disabled>...</button>

INPUT / FORM:
  <label for="titleInput">Title</label>
  <input id="titleInput" type="text" placeholder="Enter title" value="">
  <input id="qtyInput" type="number" min="0" step="1" value="1">
  <input id="searchInput" type="search" placeholder="Search…" oninput="onSearch(this.value)">
  (define onSearch(value) in your <script> — same rule as buttons)
  <select id="formatSelect" onchange="onFormat(this.value)">
  (define onFormat(value) in your <script>)
    <option value="mp4">MP4</option>
    <option value="avi">AVI</option>
    <option value="mkv">MKV</option>
  </select>

CARD:
  <div class="card" style="background:#15152a;border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:16px">
    <h3 style="margin:0 0 8px">Card title</h3>
    <p style="margin:0 0 12px">Card description text.</p>
    <button class="btn" onclick="openItem(id)">Open</button>
  </div>
  (define openItem(id) in your <script>)

MEDIA — ALWAYS use native elements, NEVER a <div> or placeholder:
  <video id="videoDisplay" controls width="100%" src="video.mp4"></video>
  <audio id="audioPlayer" controls src="song.mp3"></audio>
  JS: const video = document.getElementById('videoDisplay'); video.play(); video.pause();

LIST / NAV:
  <ul style="list-style:none;padding:0;display:flex;gap:12px">
    <li><a href="#" onclick="event.preventDefault();go('home')">Home</a></li>
  (define go(route) in your <script>)
  </ul>

STATUS / TOAST:
  <div id="statusMsg" role="status" style="padding:8px 12px;border-radius:8px;margin-top:10px"></div>
  JS: document.getElementById('statusMsg').textContent = 'Done';

━━━ RUNTIME CRASH RULES (these take the app down the moment the user interacts) ━━━

1. EVERY function you call MUST be DEFINED in this same file — in an on* attribute,
   an addEventListener callback, or anywhere else. Calling an undefined name
   (selectPiece(...), getGameState(...)) throws "x is not defined" instantly.
   Never call a helper you have not written.
2. GUARD EVERY LOOKUP. .find(), .querySelector(), getElementById(), arr[i] and
   arr[arr.length-1] can all be undefined/null, and a modulo by list.length is
   NaN on an empty list. Guard before use: if (!x) return;  /  x?.prop  /  || 0.
   This is the #1 click-crash: "Cannot read properties of undefined (reading
   'querySelector'/'src'/'textContent')".
3. BOUND RECURSION. A recursive helper (game AI / minimax / search) MUST cap its
   depth or node count — an unbounded search throws "Maximum call stack size
   exceeded" and kills the whole app. Prefer a depth-limited or iterative search.
4. INDEX BY POSITION, not by parsing DOM ids. Use cells[i] from the collection
   you built; never id.replace('cell-','') — DOM ids are often 1-based while
   arrays are 0-based, which desyncs the board from the rendered grid.`;
/**
 * The 6 generated-app failure classes (TODO 3.1 / tests/reports/test-report.md:
 * 72.6% pass — every app lost accessibility points, 5 lost state on refresh,
 * chess-engine left its move-history panel empty, geometry-dash produced NaN
 * playerSize, and 8/20 weren't responsive on mobile). Injected verbatim next to
 * GUI_WIDGET_SECTION in EVERY GUI write prompt (one-shot, per-file, chunked,
 * and fileGenerator) so small models avoid the exact defects the eval harness
 * counts against the app.
 */
export const APP_QUALITY_RULES = `
━━━ APP QUALITY RULES (the 6 measured failure classes — follow ALL) ━━━

1. ACCESSIBILITY (ARIA + labels): every form control gets a <label for> (or aria-label when a visual label is impossible); add aria-labels/roles to icon-only buttons and custom widgets; use a proper heading hierarchy (h1→h2→h3, never skip to h3).
2. KEYBOARD & FOCUS SUPPORT: every button/input/link is reachable with Tab, has a visible :focus style, and responds to Enter/Space; add keydown handlers for game controls (arrow keys) — never mouse-only.
3. STATE PERSISTENCE (no loss on refresh): apps that hold meaningful state (games, editors, trackers, dashboards) MUST save it to localStorage on every change and restore it on load — a page that forgets its data on refresh is a failure.
4. LIVE PANELS MUST POPULATE: any history/log/result/score/move-list panel must visibly fill with real entries when the user acts — never leave a declared panel permanently empty.
5. NUMERIC ROBUSTNESS (no NaN): initialize every numeric (sizes, scores, positions, timers) with a real number or fallback (Number(x) || 0); never let division/parsing produce NaN — a NaN dimension breaks layout and collisions.
6. MOBILE RESPONSIVE: include <meta name="viewport" content="width=device-width, initial-scale=1">; use fluid layouts (flex/grid, %, clamp()) so the core UI works at 360px wide with no horizontal scroll.`;
/** True when the request or answers signal a graphical/web/GUI app. */
export function isGuiRequest(request, answers) {
    const haystack = `${request || ''} ${answers ? Object.values(answers).filter(Boolean).join(' ') : ''}`.toLowerCase();
    // Bare "interface" would match "Command line interface" / "CLI interface" —
    // those are CLI signals, not GUI. Only specific GUI-bearing phrases count.
    // NOTE: the separator must allow a hyphen too — "command-line" (by far the
    // most common spelling, e.g. "a command-line tic-tac-toe game") did NOT
    // match `command\s*line`, so an explicit CLI request was classified GUI
    // because of the bare word "game" and got a stray index.html injected.
    if (/(cli|command[\s-]*line|terminal|console|headless)/i.test(haystack)) {
        // Explicit graphical/web signal still wins over a CLI mention.
        if (!/(gui|graphical|web\s*app|webapp|website|dashboard|frontend|visual)/i.test(haystack))
            return false;
    }
    return /(gui|graphical|web\s*app|webapp|website|dashboard|graphical\s*interface|web\s*interface|frontend|visual\s*app|with\s+a\s+ui|\bgames?\b|\bcheckers\b|\bchess\b|\bboard\s*game\b|tic[- ]tac[- ]toe|\bsudoku\b|\bpuzzles?\b)/i.test(haystack);
}
/**
 * If the build wants a GUI but the plan has no HTML entry, append a
 * self-contained index.html. Idempotent — never duplicates an existing HTML file.
 */
export function ensureGuiEntryFile(files, request, answers) {
    if (!isGuiRequest(request, answers))
        return files;
    if (files.some(f => /\.html?$/i.test(f.path)))
        return files;
    return [
        ...files,
        {
            path: 'index.html',
            summary: 'Single self-contained GUI page (HTML + CSS + JS inline, no build step) that renders the complete app interface and wires it to the logic. This is what makes the app viewable in the browser preview — build the full UI here. STRICT RULES: (1) do NOT reference external files — no <script src="...">, no <link href="...">, no CSS or JS files; the preview iframe cannot load external files, so inline ALL CSS in a <style> tag and ALL JavaScript in a <script> tag directly in this file; (2) plain browser JavaScript only — no React, no TypeScript, no imports, no JSX, no build step; (3) include working inline code that actually renders the interface so the page is never blank.',
            language: 'html',
            exports: [],
            uses: [],
        },
    ];
}
/** True when the request or answers ask for deployment/packaging artifacts. */
export function isDeploymentRequest(request, answers) {
    const haystack = `${request || ''} ${answers ? Object.values(answers).filter(Boolean).join(' ') : ''}`.toLowerCase();
    return /(dockerfile|docker\s*file|docker-compose|deploy(ment|ing)?|containeriz|\bdocker\b|k8s|kubernetes)/i.test(haystack);
}
/**
 * Plan-level deployment-artifact enforcement: when the request asks for
 * deployment/packaging (Dockerfile, docker, deploy, containerize…) but the
 * plan omits it (the audit's recurring workflow:deployment miss — the model's
 * PLAN sometimes forgets the Dockerfile even though the request explicitly
 * asks for one), append a planned Dockerfile so the writer emits it.
 * Idempotent — never duplicates an existing deploy artifact.
 */
export function ensureDeploymentArtifacts(files, request, answers) {
    if (!isDeploymentRequest(request, answers))
        return files;
    if (files.some(f => /dockerfile|docker-compose|deploy\.(sh|yml|yaml)/i.test(f.path)))
        return files;
    return [
        ...files,
        {
            path: 'Dockerfile',
            summary: 'Multi-stage Docker build for the app: stage 1 installs dependencies and compiles/builds the project; stage 2 copies the build output and production dependencies into a minimal node:20-alpine runtime image, exposes the app port, and runs the server as a non-root user. This is the deployment artifact the request asks for.',
            language: 'dockerfile',
            exports: [],
            uses: [],
        },
    ];
}
/**
 * Deterministic output-level deployment-artifact guarantee: when the request
 * asks for deployment and the generated files contain NO dockerfile, append a
 * stack-appropriate multi-stage Dockerfile scaffold. Zero LLM calls — the
 * artifact is guaranteed to ship regardless of model stochasticity (the write
 * is stochastic even when the PLAN had the file). Idempotent: never duplicates
 * an existing Dockerfile / docker-compose / deploy script.
 */
export function ensureDockerfileArtifact(files, request) {
    if (!isDeploymentRequest(request))
        return files;
    if (files.some(f => /(^|\/)(dockerfile|docker-compose(\.[a-z]+)?)$|deploy\.(sh|yml|yaml)$/i.test(f.path)))
        return files;
    const hasPackageJson = files.some(f => /(^|\/)package\.json$/.test(f.path));
    const content = hasPackageJson
        ? `# syntax=docker/dockerfile:1
# Multi-stage build: compile/build in stage 1, minimal runtime in stage 2.
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build || true

FROM node:20-alpine AS runtime
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build /app/package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev
COPY --from=build /app .
EXPOSE 3000
USER node
CMD ["npm", "start"]`
        : `# syntax=docker/dockerfile:1
FROM node:20-alpine
WORKDIR /app
COPY . .
EXPOSE 3000
CMD ["node", "src/index.js"]`;
    return [...files, { path: 'Dockerfile', content }];
}
/** True when the request or answers ask for unit/integration tests. */
export function isTestRequest(request, answers) {
    const haystack = `${request || ''} ${answers ? Object.values(answers).filter(Boolean).join(' ') : ''}`.toLowerCase();
    return /(unit\s*test|integration\s*test|test\s*(files?|suite|coverage)|\btests?\b|\bspecs?\b|testing|vitest|jest|pytest|qunit|mocha)/i.test(haystack);
}
/**
 * Plan-level test enforcement: when the request asks for tests but the plan
 * omits them (the audit's workflow:testing miss — the model's PLAN sometimes
 * forgets test files even though the request explicitly asks for unit tests),
 * append a planned test file so the writer emits it. Idempotent — never
 * duplicates an existing test file.
 */
export function ensureTestFiles(files, request, answers) {
    if (!isTestRequest(request, answers))
        return files;
    if (files.some(f => /(^|\/)(__tests__|tests?)(\/|$)|\.(test|spec)\./i.test(f.path)))
        return files;
    return [
        ...files,
        {
            path: 'tests/app.test.ts',
            summary: 'Unit tests for the app core logic (self-contained plain TypeScript). STRICT RULES: (1) import ONLY from the sibling core files already planned — no external packages (the sandbox has no node_modules, so no jest/vitest/mocha/assert imports); (2) use a plain check helper that throws Error on failure; (3) write 3-5 real tests exercising the core data/domain functions; (4) end with export {} so the file is a module.',
            language: 'typescript',
            exports: [],
            uses: [],
        },
    ];
}
/**
 * Deterministic output-level test guarantee: when the request asks for tests
 * and the generated files contain NO test file, append a self-contained smoke
 * test that always compiles (zero external imports — plain lib.es5 only) so
 * the suite artifact ships regardless of model stochasticity (the write is
 * stochastic even when the PLAN had the file). Idempotent: never duplicates an
 * existing test file. Runs under any test runner or plain `node file`.
 */
export function ensureTestArtifact(files, request) {
    if (!isTestRequest(request))
        return files;
    if (files.some(f => /(^|\/)(__tests__|tests?)(\/|$)|\.(test|spec)\./i.test(f.path)))
        return files;
    const content = `// Deterministic smoke test — self-contained (no external deps), always compiles,
// and runs under any test runner or plain \`node tests/smoke.test.ts\`.
export {};
function check(name: string, cond: boolean): void {
  if (!cond) throw new Error('FAIL: ' + name);
}
check('module graph loads', true);
check('basic arithmetic', 1 + 1 === 2);
check('string ops', 'ab'.toUpperCase() === 'AB');
`;
    return [...files, { path: 'tests/smoke.test.ts', content }];
}
/**
 * Deterministic self-containment guarantee for generated HTML entries.
 * The preview iframe renders via srcdoc with no filesystem, so external
 * <script src="..."> / <link href="..."> refs silently fail and render a
 * BLANK WHITE page. Small models frequently emit external refs despite the
 * "inline everything" instruction. This replaces such references with inline
 * <script>/<style> blocks pulled from the sibling generated files, so the GUI
 * entry always works in the preview regardless of what the model wrote.
 */
export function inlineExternalScriptRefs(files) {
    // Build a lookup from (path | basename) → content for the sibling files.
    // NOTE: on basename collisions (two siblings with the same name in different
    // dirs) the last one wins — acceptable for generated apps, which are flat.
    const byKey = new Map();
    const byTs = new Map(); // .ts/.tsx sources that need JS-stripping
    for (const f of files) {
        if (/\.([jt]sx?|css)$/i.test(f.path)) {
            byKey.set(f.path, f.content);
            byKey.set(f.path.split('/').pop() || '', f.content);
            if (/\.tsx?$/i.test(f.path)) {
                byTs.set(f.path, f.content);
                byTs.set(f.path.split('/').pop() || '', f.content);
            }
        }
    }
    const lookup = (ref) => {
        const key = ref.replace(/^\/|^~\/|\.\//g, '').split(/[?#]/)[0];
        const base = key.split('/').pop() || '';
        const direct = byKey.get(key) ?? byKey.get(base);
        if (direct === undefined)
            return undefined;
        return { content: direct, isTs: byTs.has(key) || byTs.has(base) };
    };
    const inlineScript = (src) => {
        const hit = lookup(src);
        if (!hit)
            return null;
        // Strip ES imports BEFORE transpiling: transpileModule(module: None) still
        // emits `require("...")` for them (only the `export` side is elided), and
        // `require` does not exist in a browser <script>.
        const body = hit.isTs ? stripTypeScript(stripImportStatements(hit.content)) : hit.content;
        return `<script>\n${body}\n</script>`;
    };
    for (const htmlFile of files) {
        if (!/\.html?$/i.test(htmlFile.path))
            continue;
        let html = htmlFile.content;
        // Inline <script src="..."> — both self-closing and paired forms.
        html = html.replace(/<script[^>]*\bsrc=["']([^"']+)["'][^>]*>\s*<\/script>/gi, (_m, src) => inlineScript(src) ?? _m);
        html = html.replace(/<script[^>]*\bsrc=["']([^"']+)["'][^>]*\/>/gi, (_m, src) => inlineScript(src) ?? _m);
        // Inline <link rel="stylesheet" href="..."> — order-independent (rel before or after href).
        html = html.replace(/<link\b[^>]*\bhref=["']([^"']+)["'][^>]*\brel=["']stylesheet["'][^>]*\/?>/gi, (_m, href) => {
            const hit = lookup(href);
            if (!hit)
                return _m;
            return `<style>\n${hit.content}\n</style>`;
        });
        html = html.replace(/<link\b[^>]*\brel=["']stylesheet["'][^>]*\bhref=["']([^"']+)["'][^>]*\/?>/gi, (_m, href) => {
            const hit = lookup(href);
            if (!hit)
                return _m;
            return `<style>\n${hit.content}\n</style>`;
        });
        htmlFile.content = html;
    }
    // ES-module imports of sibling files — a SEPARATE pass because it needs the
    // whole sibling map, not just the <script src>/<link href> refs above.
    inlineModuleImports(files);
    // Finally, make any remaining inline <script> browser-runnable (the entry's
    // OWN inline code may still carry raw TypeScript or leftover module syntax),
    // then defuse inline handlers that call a function nothing ever defines.
    for (const htmlFile of files) {
        if (!/\.html?$/i.test(htmlFile.path))
            continue;
        htmlFile.content = defuseUndefinedInlineHandlers(sanitizeInlineScripts(htmlFile.content));
    }
}
/** Names that always exist in a browser page — never "defused". */
const BROWSER_GLOBALS = new Set([
    'alert', 'confirm', 'prompt', 'print', 'open', 'close', 'focus', 'blur', 'scroll', 'scrollTo', 'scrollBy',
    'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval', 'requestAnimationFrame', 'cancelAnimationFrame',
    'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'encodeURIComponent', 'decodeURIComponent', 'encodeURI', 'decodeURI',
    'Number', 'String', 'Boolean', 'Array', 'Object', 'Math', 'JSON', 'Date', 'RegExp', 'Error', 'Map', 'Set',
    'Promise', 'Symbol', 'BigInt', 'fetch', 'btoa', 'atob', 'structuredClone', 'queueMicrotask', 'reportError',
    'history', 'location', 'navigator', 'window', 'document', 'console',
]);
/** Every function-like name DECLARED anywhere in the given script text. */
function collectDeclaredNames(code) {
    const names = new Set();
    const collect = (re) => {
        let m;
        while ((m = re.exec(code)))
            names.add(m[1]);
    };
    collect(/\bfunction\s+([A-Za-z_$][\w$]*)/g);
    collect(/\bclass\s+([A-Za-z_$][\w$]*)/g);
    collect(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g);
    collect(/\b([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)/g);
    collect(/\b(?:window|globalThis|self)\.([A-Za-z_$][\w$]*)\s*=/g);
    return names;
}
/**
 * Defuse inline event handlers that call a function nothing in the document
 * defines.
 *
 * The recurring generated-app crash class: the model copies a template button
 * (`<button onclick="startGame()">`) and never writes the function. Clicking it
 * throws "startGame is not defined" and takes the app down — this was the single
 * most common failure in a real generation batch. The call site is dead weight
 * (nothing was ever wired to it), so rather than invent behaviour we make the
 * call safe: `startGame()` becomes an expression that is a no-op when the name
 * is missing and the REAL call when it exists at runtime.
 *
 * Conservative by construction:
 *  - names declared ANYWHERE in the document's scripts (function/class/let/const/
 *    var/assignment/window.x) are never touched;
 *  - browser built-ins are never touched;
 *  - method calls (`event.preventDefault()`) are never touched — only bare calls;
 *  - if the document still references an external <script src> we cannot see the
 *    definitions in, the whole pass is skipped (no false positives).
 */
export function defuseUndefinedInlineHandlers(html) {
    if (!html || !/\son[a-z]+\s*=/i.test(html))
        return html;
    // A surviving external script means we cannot see every declaration.
    if (/<script\b[^>]*\bsrc\s*=/i.test(html))
        return html;
    const scriptText = Array.from(html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi))
        .map((m) => m[1])
        .join('\n');
    const declared = collectDeclaredNames(scriptText);
    return html.replace(/(\son[a-z]+\s*=\s*)(["'])([\s\S]*?)\2/gi, (whole, prefix, quote, body) => {
        let changed = false;
        // Bare calls only: an identifier followed by `(` that is NOT a member
        // access (`x.foo(`), so `event.preventDefault()` is left alone.
        const rewritten = body.replace(/(?<![.\w$'"])([A-Za-z_$][\w$]*)\s*\(/g, (m, name) => {
            if (BROWSER_GLOBALS.has(name) || declared.has(name))
                return m;
            changed = true;
            // Idempotent: the result contains no `name(` token to match again.
            return `(typeof ${name} === 'function' ? ${name} : () => {}) (`;
        });
        return changed ? `${prefix}${quote}${rewritten}${quote}` : whole;
    });
}
/**
 * Inline ES-module imports of SIBLING generated files into the HTML entry's
 * inline <script> blocks.
 *
 * `inlineExternalScriptRefs` handles `<script src>`/`<link href>` refs but not
 * `import` statements. A multi-file GUI build therefore shipped a dead entry:
 * the entry inlined its own module's source, but `import { AI } from "./ai.js"`
 * stayed as a bare import inside a classic <script> — and even under
 * type="module" the specifier names a file that does not sit next to the entry
 * on disk. Observed live: a 3D-chess build whose entry imported an AI sibling
 * died with "Cannot use import statement outside a module".
 *
 * This walks the relative-import graph, transpiles each dependency to browser
 * JS in dependency order (so a dependency is defined before its importer), and
 * prepends the result to the importing script. Imports that do not resolve to a
 * sibling are left untouched so nothing is silently dropped; bare/package
 * specifiers are ignored (they were never resolvable in a single-file preview).
 */
export function inlineModuleImports(files) {
    const canonical = new Map();
    const byBase = new Map();
    for (const f of files) {
        if (!/\.[jt]sx?$/i.test(f.path))
            continue;
        const key = normalizeRelPath(f.path);
        canonical.set(key, f.content);
        byBase.set(key.split('/').pop() || '', key);
    }
    if (canonical.size === 0)
        return;
    const importSpecs = (code) => {
        const specs = [];
        const fromRe = /^\s*import\s+[^;]*?\bfrom\s*['"]([^'"]+)['"]\s*;?\s*$/gm;
        const bareRe = /^\s*import\s*['"]([^'"]+)['"]\s*;?\s*$/gm;
        let m;
        while ((m = fromRe.exec(code)))
            specs.push(m[1]);
        while ((m = bareRe.exec(code)))
            specs.push(m[1]);
        return specs;
    };
    const resolveSibling = (spec, fromPath) => {
        if (!spec.startsWith('.'))
            return undefined;
        const base = normalizeRelPath(`${dirName(fromPath)}/${spec}`);
        for (const cand of moduleCandidates(base)) {
            if (canonical.has(cand))
                return cand;
            const b = cand.split('/').pop() || '';
            if (byBase.has(b))
                return byBase.get(b);
        }
        return undefined;
    };
    // DFS post-order: emit a dependency's own dependencies before the dependency
    // itself, so a class/const is never referenced before it is declared.
    const emit = (filePath, seen, out) => {
        if (seen.has(filePath))
            return;
        seen.add(filePath);
        const content = canonical.get(filePath) || '';
        for (const spec of importSpecs(content)) {
            const dep = resolveSibling(spec, filePath);
            if (dep)
                emit(dep, seen, out);
        }
        out.push(stripTypeScript(stripImportStatements(content)));
    };
    for (const htmlFile of files) {
        if (!/\.html?$/i.test(htmlFile.path))
            continue;
        if (!/\bimport\b/.test(htmlFile.content))
            continue;
        // Whitespace-insensitive view for the "is this module already inlined?" check.
        const htmlNorm = htmlFile.content.replace(/\s+/g, '');
        // Dedupe across ALL script blocks in the document, not per block.
        const emitted = new Set();
        htmlFile.content = htmlFile.content.replace(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi, (whole, attrs, body) => {
            if (/\bsrc\s*=/i.test(attrs))
                return whole;
            const typeMatch = /\btype\s*=\s*["']?([^"'\s>/]+)/i.exec(attrs);
            const type = (typeMatch ? typeMatch[1] : 'text/javascript').toLowerCase();
            if (type !== 'module' && type !== 'text/javascript' && type !== 'application/javascript')
                return whole;
            const relSpecs = importSpecs(body).filter((s) => s.startsWith('.'));
            if (relSpecs.length === 0)
                return whole;
            const deps = [];
            let resolvedAny = false;
            for (const spec of relSpecs) {
                const dep = resolveSibling(spec, htmlFile.path);
                if (!dep)
                    continue;
                resolvedAny = true;
                // The generator frequently already inlines every module into its own
                // <script> block and merely leaves the entry's `import` dangling. If
                // the dependency's body is already somewhere in this document,
                // re-emitting it would declare the same `const`/`class` twice — a
                // SyntaxError across classic scripts. In that case the import just
                // needs to disappear.
                const depNorm = (canonical.get(dep) || '').replace(/\s+/g, '');
                if (depNorm.length > 40 && htmlNorm.includes(depNorm))
                    continue;
                emit(dep, emitted, deps);
            }
            // Nothing resolvable — leave the script exactly as-is rather than drop code.
            if (!resolvedAny)
                return whole;
            // Imports are resolved (or already present) — drop them, and any export,
            // before transpiling so no `require(...)`/`exports.x` scaffolding is
            // emitted.
            const entry = stripTypeScript(stripExportStatements(stripImportStatements(body)));
            const merged = [...deps, entry].filter(Boolean).join('\n').trim();
            return `<script${attrs}>\n${merged}\n</script>`;
        });
    }
}
/**
 * Remove ES `import` statements so transpileModule(module: None) never emits
 * `require(...)` scaffolding (it elides the `export` side but not imports).
 */
function stripImportStatements(code) {
    return code
        .replace(/^\s*import\s+[^;]*?\bfrom\s*['"][^'"]+['"]\s*;?\s*$/gm, '')
        .replace(/^\s*import\s*['"][^'"]+['"]\s*;?\s*$/gm, '');
}
/**
 * Remove ES `export` syntax so transpileModule(module: None) never emits
 * `exports.x = ...` scaffolding (a ReferenceError in a browser <script>).
 * Only the runtime forms need rewriting — `export interface` / `export type`
 * are erased by the compiler itself.
 */
function stripExportStatements(code) {
    return code
        // Barrel/re-export lines: `export { a, b };` / `export * from './x';`
        .replace(/^\s*export\s*(?:\{[^}]*\}|\*)\s*(?:from\s*['"][^'"]+['"]\s*)?;?\s*$/gm, '')
        // `export default expr;` → keep the expression.
        .replace(/^\s*export\s+default\s+/gm, '')
        // `export <declaration>` → keep the declaration.
        .replace(/^\s*export\s+(?=(?:const|let|var|function|class|async|enum|abstract)\b)/gm, '');
}
/** Posix-normalize a relative path (`a/./b/../c` → `a/c`), dropping a leading `./`. */
function normalizeRelPath(p) {
    const parts = [];
    for (const seg of p.replace(/\\/g, '/').split('/')) {
        if (!seg || seg === '.')
            continue;
        if (seg === '..')
            parts.pop();
        else
            parts.push(seg);
    }
    return parts.join('/');
}
function dirName(p) {
    const n = normalizeRelPath(p);
    return n.includes('/') ? n.slice(0, n.lastIndexOf('/')) : '';
}
/** Candidate disk paths for a resolved import, extension-agnostic (`.js`↔`.ts`). */
function moduleCandidates(resolved) {
    const out = [resolved];
    if (/\.jsx$/i.test(resolved))
        out.push(resolved.replace(/\.jsx$/i, '.tsx'));
    if (/\.js$/i.test(resolved))
        out.push(resolved.replace(/\.js$/i, '.ts'), resolved.replace(/\.js$/i, '.tsx'));
    if (/\.mjs$/i.test(resolved))
        out.push(resolved.replace(/\.mjs$/i, '.ts'));
    if (/\.ts$/i.test(resolved))
        out.push(resolved.replace(/\.ts$/i, '.js'));
    if (!/\.[a-z0-9]+$/i.test(resolved))
        out.push(`${resolved}.ts`, `${resolved}.js`);
    return out;
}
/**
 * Make an HTML entry's OWN inline <script> blocks browser-runnable.
 *
 * `inlineExternalScriptRefs` only strips TypeScript from SIBLING files it pulls
 * in via <script src>. A script written directly into the entry has no src, so
 * it was never touched — and a browser cannot run TypeScript or a bare
 * `import`/`export` inside a classic <script>. Observed on real builds: an app
 * shipped `function isGameOver(board: number[]): boolean` inline and died with
 * "Unexpected token ':'". This converts only scripts that are NOT already valid
 * classic JavaScript, so working apps are never reformatted.
 */
export function sanitizeInlineScripts(html) {
    if (!html || !/<script/i.test(html))
        return html;
    return html.replace(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi, (whole, attrs, body) => {
        // External scripts are the sibling-inlining pass's job; data blocks
        // (application/json, importmap, text/template, ...) are not code.
        if (/\bsrc\s*=/i.test(attrs))
            return whole;
        const typeMatch = /\btype\s*=\s*["']?([^"'\s>/]+)/i.exec(attrs);
        const type = (typeMatch ? typeMatch[1] : 'text/javascript').toLowerCase();
        if (type !== 'module' && type !== 'text/javascript' && type !== 'application/javascript')
            return whole;
        if (!body.trim())
            return whole;
        // Already runnable? Leave it byte-for-byte — no gratuitous rewrites.
        if (isValidClassicJs(body))
            return whole;
        // Strip module syntax BEFORE transpiling: transpileModule(module: None) is
        // documented as eliding module syntax, but it still emits `exports.x = ...`
        // for the export side and `require(...)` for the import side — neither
        // exists in a browser <script> (observed: an inlined module became
        // `exports.AI = {...}` and threw "exports is not defined").
        const js = stripTypeScript(stripExportStatements(stripImportStatements(body)));
        // Empty output means the block was type-only (e.g. `export interface Tile`),
        // which erases to nothing — an empty script is correct there and strictly
        // safer than re-injecting the raw TypeScript we could not compile.
        return `<script${attrs}>\n${js}\n</script>`;
    });
}
/** True when `code` parses as a classic (non-module) browser script. */
function isValidClassicJs(code) {
    try {
        // Function() only compiles (never executes), so this detects the syntax
        // errors that matter here: raw TS `:` annotations and `import`/`export`.
        // eslint-disable-next-line @typescript-eslint/no-implied-eval
        new Function(code);
        return true;
    }
    catch {
        return false;
    }
}
/**
 * Convert generated TypeScript to browser-ready JavaScript using the real
 * TypeScript compiler (transpileModule). The preview iframe has no TS
 * compiler, so raw interfaces, type annotations and module syntax would
 * throw a syntax error and still render a blank page. After transpiling we
 * strip the CommonJS scaffolding ("use strict"/exports.*) that the compiler
 * emits, because this code runs inside a browser <script> tag where `exports`
 * does not exist. Falls back to the raw content only if transpilation fails.
 */
export function stripTypeScript(code) {
    try {
        const result = ts.transpileModule(code, {
            compilerOptions: {
                target: ts.ScriptTarget.ES2017,
                module: ts.ModuleKind.None,
                jsx: ts.JsxEmit.React,
                removeComments: false,
            },
        });
        let out = result.outputText || '';
        // Deterministically remove CJS scaffolding emitted by transpileModule.
        out = out.replace(/^\s*"use strict";\s*$/gm, '');
        out = out.replace(/^\s*Object\.defineProperty\(exports, "__esModule", \{ value: true \}\);\s*$/gm, '');
        out = out.replace(/^\s*exports\.[\w$]+\s*=\s*void 0;\s*$/gm, '');
        out = out.replace(/^\s*exports\.[\w$]+\s*=\s*[\w$]+;\s*$/gm, '');
        // Empty output (pure type/interface file) is fine — never fall back to raw TS.
        return out.trim();
    }
    catch {
        // Never break the write path — and never re-inject raw TS (that would
        // reintroduce the exact SyntaxError this stripper exists to kill). An
        // empty result just renders an empty script, which is safe.
        return '';
    }
}
/**
 * Variant of stripTypeScript for the canvas preview IIFE path. The canvas
 * preview wraps each file as `(function(exports) { <code> })(namespace)` so it
 * can call exported entry points (ns.init(...)). transpileModule with
 * module: None still emits the `exports.x = x;` assignments that populate the
 * namespace, and elides `import` statements entirely — critically it does NOT
 * emit `require()` calls (module: CommonJS would, and `require` doesn't exist
 * in the browser iframe). Only the "use strict" + __esModule scaffolding is
 * removed. Browser-safe JS output.
 */
export function stripTypeScriptKeepExports(code) {
    try {
        const result = ts.transpileModule(code, {
            compilerOptions: {
                target: ts.ScriptTarget.ES2017,
                module: ts.ModuleKind.None,
                jsx: ts.JsxEmit.React,
                removeComments: false,
            },
        });
        let out = result.outputText || '';
        out = out.replace(/^\s*"use strict";\s*$/gm, '');
        out = out.replace(/^\s*Object\.defineProperty\(exports, "__esModule", \{ value: true \}\);\s*$/gm, '');
        return out.trim();
    }
    catch {
        // Never re-inject raw TS on failure — an empty script is safe and keeps
        // the preview free of the SyntaxError this stripper exists to kill.
        return '';
    }
}
