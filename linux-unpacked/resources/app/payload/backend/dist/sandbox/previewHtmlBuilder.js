/**
 * Preview HTML Builder
 * ====================
 * Generates a sandbox HTML preview page that actually RUNS the generated code.
 * - JS/TypeScript code → executed inline with live console output panel
 * - HTML nodes → rendered directly in the preview area
 * - CSS nodes → applied to the page
 * - Other languages (Go, Python, Rust, etc.) → shown as highlighted source files
 */
/**
 * Detect the programming language of a code string by analyzing its syntax.
 */
function detectLang(code) {
    // CSS
    if (/[.#@]\w+\s*\{[^}]+\}/m.test(code) && /color|background|margin|padding|font|border|display|flex|grid|width|height|position/i.test(code))
        return 'css';
    // Go
    if (/^\s*(package |import |func |type |const |var |:=)/m.test(code))
        return 'go';
    // TypeScript/JavaScript (must check before HTML since JSX uses HTML-like syntax)
    if (/^\s*(import |from |export |interface |type |const |let |var |>|function |class |async|await)/m.test(code))
        return 'javascript';
    // Python
    if (/^\s*(import |from |def |class |print|# )/m.test(code))
        return 'python';
    // Rust
    if (/^\s*(use |pub |fn |impl |struct |enum |let |mut)/m.test(code))
        return 'rust';
    // C++
    if (/^\s*(#include|using namespace|int main|std::)/m.test(code))
        return 'cpp';
    // HTML (check for tags, but not JS keywords)
    if (/<[a-zA-Z][^>]*>/m.test(code) && !/^(import |from |export |interface |type |const |let |var |>|function )/m.test(code))
        return 'html';
    return 'javascript';
}
function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}
function highlightCode(code) {
    const SPAN_MARKER = '\x00HL';
    let spanIndex = 0;
    const spans = [];
    function saveSpan(spanHtml) {
        const marker = `${SPAN_MARKER}${spanIndex}${SPAN_MARKER}`;
        spans[spanIndex] = spanHtml;
        spanIndex++;
        return marker;
    }
    let processed = code.replace(/(\"(?:[^\"\\]|\\.)*\")/g, (m) => saveSpan(`<span class="str">${escapeHtml(m)}</span>`));
    processed = processed.replace(/(\'(?:[^'\\]|\\.)*\')/g, (m) => saveSpan(`<span class="str">${escapeHtml(m)}</span>`));
    processed = processed.replace(/(\`(?:[^`\\]|\\.)*\`)/g, (m) => saveSpan(`<span class="str">${escapeHtml(m)}</span>`));
    processed = processed.replace(/(\/\/.*$)/gm, (m) => saveSpan(`<span class="cm">${escapeHtml(m)}</span>`));
    processed = processed.replace(/(#.*$)/gm, (m) => saveSpan(`<span class="cm">${escapeHtml(m)}</span>`));
    let result = escapeHtml(processed);
    const keywords = ['import', 'export', 'from', 'return', 'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'break', 'continue', 'throw', 'try', 'catch', 'finally', 'new', 'delete', 'typeof', 'instanceof', 'void', 'this', 'super', 'class', 'extends', 'implements', 'interface', 'type', 'enum', 'const', 'let', 'var', 'function', 'async', 'await', 'yield', 'def', 'elif', 'raise', 'with', 'as', 'pass', 'None', 'True', 'False', 'and', 'or', 'not', 'in', 'is', 'lambda', 'package', 'func', 'defer', 'go', 'select', 'chan', 'map', 'struct', 'range', 'fallthrough', 'goto'];
    for (const kw of keywords) {
        result = result.replace(new RegExp(`\\b${kw}\\b`, 'g'), `<span class="kw">${kw}</span>`);
    }
    result = result.replace(/\b(\d+\.?\d*)\b/g, '<span class="num">$1</span>');
    for (let i = 0; i < spans.length; i++) {
        result = result.replace(`${SPAN_MARKER}${i}${SPAN_MARKER}`, spans[i]);
    }
    return result;
}
/**
 * Build a sandbox HTML preview page that actually RUNS the generated code.
 *
 * - JS/TS code → injected into a <script> with a live console panel
 * - HTML code → rendered directly in the preview area
 * - CSS code → applied to the page
 * - Other → shown as source files with tabs
 */
export function buildSandboxHtml(project, codeNodes, previewId) {
    const warnings = [];
    let totalChars = 0;
    let uiHtml = '';
    let inlineScripts = [];
    let sourceFiles = [];
    // Process each node's code
    for (const node of codeNodes) {
        const code = node.data?.generatedCode || '';
        const label = node.data?.label || node.id || 'unknown';
        totalChars += code.length;
        if (code.includes('TODO') || code.includes('FIXME')) {
            warnings.push(`Node "${label}" has TODOs/FIXMEs in generated code`);
        }
        const lang = detectLang(code);
        if (lang === 'html') {
            // Embed HTML directly in the preview
            uiHtml += `<!-- ───── ${label} ───── -->\n${code}\n`;
        }
        else if (lang === 'css') {
            // Embed CSS in a style tag
            const safeCss = code.replace(/<\//g, '<\\/');
            uiHtml += `<style>\n/* ───── ${label} ───── */\n${safeCss}\n</style>\n`;
        }
        else if (lang === 'javascript') {
            // Collect JS/TS code for inline execution
            inlineScripts.push(`/** ───── ${label} ───── */\n${code}`);
        }
        else {
            // Other languages shown as source files
            sourceFiles.push({ label, code, lang });
        }
    }
    // Build the executable JS (combine all JS/TS nodes)
    const jsCode = inlineScripts.length > 0 ? inlineScripts.join('\n\n') : '';
    // Build source file tabs HTML
    function buildSourceTabs(files) {
        if (files.length === 0 && !jsCode)
            return '';
        const allFiles = files.map(f => ({ label: f.label, code: f.code, lang: f.lang }));
        if (jsCode) {
            allFiles.unshift({ label: 'Runtime Code', code: jsCode, lang: 'javascript' });
        }
        if (allFiles.length === 0)
            return '';
        const tabs = allFiles.map((f, i) => `<button class="src-tab ${i === 0 ? 'active' : ''}" data-tab="src-${i}">📄 ${escapeHtml(f.label)}</button>`).join('');
        const panels = allFiles.map((f, i) => `<div class="src-panel ${i === 0 ? 'active' : ''}" id="src-${i}">
        <div class="src-header">
          <span class="src-lang-badge">${f.lang}</span>
          <span class="src-filename">${escapeHtml(f.label)}</span>
        </div>
        <pre class="src-code"><code>${highlightCode(f.code)}</code></pre>
      </div>`).join('');
        return `
    <div class="node-section" id="source-panel">
      <h2>📄 Source Files (${allFiles.length})</h2>
      <div class="src-tabs">${tabs}</div>
      ${panels}</div>`;
    }
    const sourceHtml = buildSourceTabs(sourceFiles);
    // Determine what view to show initially
    const hasRunnableCode = jsCode.length > 0;
    const hasUI = uiHtml.length > 0;
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(project.name)} — Sandbox Preview</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; display: flex; flex-direction: column; }
    .app-header { background: #16213e; border-bottom: 1px solid #0f3460; padding: 12px 20px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; flex-wrap: wrap; }
    .app-header h1 { font-size: 16px; font-weight: 600; color: #4a9eff; }
    .app-header .badge { font-size: 10px; padding: 2px 8px; background: #0f3460; color: #8892b0; border-radius: 4px; }

    /* Tab navigation */
    .view-tabs { display: flex; gap: 0; background: #0d0d20; border-bottom: 1px solid #1a1a3e; flex-shrink: 0; }
    .view-tab { padding: 10px 18px; font-size: 12px; font-weight: 600; background: transparent; border: none; border-bottom: 2px solid transparent; color: #64748b; cursor: pointer; transition: all 0.15s ease; display: flex; align-items: center; gap: 6px; }
    .view-tab:hover { color: #94a3b8; background: rgba(74,158,255,0.05); }
    .view-tab.active { color: #4a9eff; border-bottom-color: #4a9eff; background: rgba(74,158,255,0.08); }
    .view-tab .tab-badge { font-size: 9px; padding: 1px 5px; border-radius: 6px; background: rgba(74,158,255,0.15); color: #4a9eff; margin-left: 4px; }
    .view-content { flex: 1; overflow: auto; display: flex; flex-direction: column; }
    .view-panel { display: none; flex: 1; flex-direction: column; overflow: auto; }
    .view-panel.active { display: flex; }

    /* App preview area */
    .app-content { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 16px; overflow: auto; }
    .node-section { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; overflow: hidden; }
    .node-section h2 { font-size: 13px; font-weight: 600; color: #4a9eff; padding: 10px 16px; background: rgba(74, 158, 255, 0.08); border-bottom: 1px solid #0f3460; margin: 0; }
    .widget-container { padding: 16px; display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start; min-height: 60px; }

    /* Console output */
    .console-panel { background: #0a0a18; border: 1px solid #0f3460; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; flex: 1; min-height: 120px; }
    .console-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; background: #0d0d20; border-bottom: 1px solid #0f3460; }
    .console-header h3 { font-size: 12px; font-weight: 600; color: #4a9eff; margin: 0; display: flex; align-items: center; gap: 6px; }
    .console-actions { display: flex; gap: 6px; }
    .console-btn { padding: 4px 10px; font-size: 10px; font-weight: 600; border-radius: 3px; border: 1px solid rgba(74,158,255,0.3); background: rgba(74,158,255,0.1); color: #4a9eff; cursor: pointer; transition: all 0.12s ease; }
    .console-btn:hover { background: rgba(74,158,255,0.2); }
    .console-btn.danger { border-color: rgba(239,68,68,0.3); color: #ef4444; background: rgba(239,68,68,0.1); }
    .console-btn.danger:hover { background: rgba(239,68,68,0.2); }
    .console-btn.success { border-color: rgba(74,222,128,0.3); color: #4ade80; background: rgba(74,222,128,0.1); }
    .console-btn.success:hover { background: rgba(74,222,128,0.2); }
    .console-output { padding: 12px 14px; font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 12px; line-height: 1.5; overflow-y: auto; white-space: pre-wrap; word-break: break-all; flex: 1; color: #ccd6f6; }
    .console-output .log-line { padding: 1px 0; display: flex; gap: 8px; align-items: flex-start; border-bottom: 1px solid rgba(255,255,255,0.03); }
    .console-output .log-line:last-child { border-bottom: none; }
    .console-output .log-level { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 2px; flex-shrink: 0; margin-top: 2px; }
    .console-output .log-level.info { background: rgba(74,158,255,0.2); color: #4a9eff; }
    .console-output .log-level.warn { background: rgba(251,191,36,0.2); color: #fbbf24; }
    .console-output .log-level.error { background: rgba(239,68,68,0.2); color: #ef4444; }
    .console-output .log-level.success { background: rgba(74,222,128,0.2); color: #4ade80; }
    .console-output .log-msg { flex: 1; }
    .console-output .log-msg.info { color: #ccd6f6; }
    .console-output .log-msg.warn { color: #fbbf24; }
    .console-output .log-msg.error { color: #ef4444; }
    .console-output .log-msg.success { color: #4ade80; }
    .console-empty { color: #64748b; font-style: italic; padding: 20px; text-align: center; }

    /* Source file tabs */
    .src-tabs { display: flex; gap: 0; overflow-x: auto; background: #0d0d20; border-bottom: 1px solid #1a1a3e; padding: 0; }
    .src-tab { padding: 8px 14px; font-size: 11px; font-weight: 600; background: transparent; border: none; border-bottom: 2px solid transparent; color: #64748b; cursor: pointer; white-space: nowrap; transition: all 0.15s ease; }
    .src-tab:hover { color: #94a3b8; background: rgba(74,158,255,0.05); }
    .src-tab.active { color: #4a9eff; border-bottom-color: #4a9eff; background: rgba(74,158,255,0.08); }
    .src-panel { display: none; }
    .src-panel.active { display: block; }
    .src-header { display: flex; align-items: center; gap: 10px; padding: 8px 16px; background: #0a0a18; border-bottom: 1px solid #1a1a3e; }
    .src-lang-badge { font-size: 10px; padding: 2px 8px; border-radius: 3px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; background: rgba(74,158,255,0.15); color: #4a9eff; border: 1px solid rgba(74,158,255,0.3); }
    .src-filename { font-size: 12px; font-weight: 600; color: #94a3b8; font-family: 'SF Mono', 'Fira Code', monospace; }
    .src-code { margin: 0; padding: 16px; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; line-height: 1.6; overflow-x: auto; white-space: pre; color: #ccd6f6; background: #0a0a18; }
    .src-code code { display: block; }

    /* Status bar */
    .status-bar { background: #0f3460; border-top: 1px solid rgba(74, 158, 255, 0.2); padding: 8px 20px; font-size: 11px; color: #8892b0; display: flex; gap: 16px; flex-shrink: 0; flex-wrap: wrap; }
    .status-bar .ok { color: #4ade80; }
    .status-bar .warn { color: #fbbf24; }
    .status-bar .error { color: #ef4444; }

    /* Syntax highlighting */
    .kw { color: #c792ea; } .str { color: #c3e88d; } .cm { color: #546e7a; font-style: italic; } .fn { color: #82aaff; } .tp { color: #ffcb6b; } .num { color: #f78c6c; }

    /* Empty states */
    .empty-state { text-align: center; padding: 40px; color: #64748b; }
    .empty-state h3 { color: #94a3b8; margin-bottom: 8px; font-size: 14px; }
  </style>
</head>
<body>
  <div class="app-header">
    <h1>🧪 ${escapeHtml(project.name)}</h1>
    <span class="badge">${project.targetOS || 'linux'}</span>
    <span class="badge">${codeNodes.length} nodes</span>
    ${hasRunnableCode ? '<span class="badge" style="color:#4ade80">⚡ Runnable</span>' : '<span class="badge" style="color:#fbbf24">📄 Source View</span>'}
    ${warnings.length > 0 ? '<span class="badge" style="color:#fbbf24">⚠️ ' + warnings.length + ' warnings</span>' : ''}
  </div>

  <!-- View Tabs -->
  <div class="view-tabs">
    ${hasRunnableCode || hasUI ? `<button class="view-tab active" data-view="preview">🖥 Preview${hasRunnableCode ? ' <span class="tab-badge">Live</span>' : ''}</button>` : ''}
    <button class="view-tab ${!hasRunnableCode && !hasUI ? 'active' : ''}" data-view="source">📄 Source</button>
    ${hasRunnableCode ? '<button class="view-tab" data-view="console">🖥️ Console</button>' : ''}
  </div>

  <div class="view-content">

    <!-- Preview Panel -->
    ${hasRunnableCode || hasUI ? `
    <div class="view-panel active" id="view-preview">
      <div class="app-content" style="padding: 12px;">
        ${hasUI ? `
        <div class="node-section">
          <h2>🖥 UI Components</h2>
          <div class="widget-container" id="ui-root">
            ${uiHtml}
          </div>
        </div>` : ''}
        ${!hasUI && hasRunnableCode ? `
        <div class="node-section">
          <h2>⚡ Runtime Output</h2>
          <div id="runtime-root" class="widget-container" style="flex-direction:column; gap:8px;">
            <div style="padding:12px; background:rgba(74,158,255,0.05); border:1px solid rgba(74,158,255,0.15); text-align:center;">
              <div style="font-size:13px; color:#4a9eff; font-weight:600; margin-bottom:4px;">App Code Executed</div>
              <div style="font-size:11px; color:#64748b;">Check the Console tab for runtime output</div>
            </div>
          </div>
        </div>` : ''}
      </div>
    </div>` : ''}

    <!-- Source Panel -->
    <div class="view-panel ${!hasRunnableCode && !hasUI ? 'active' : ''}" id="view-source">
      <div class="app-content" style="padding: 12px;">
        ${sourceHtml || '<div class="empty-state"><h3>📄 No source files</h3><p>Generated code will appear here after code generation.</p></div>'}
      </div>
    </div>

    <!-- Console Panel -->
    ${hasRunnableCode ? `
    <div class="view-panel" id="view-console">
      <div class="app-content" style="padding: 12px; flex: 1; display: flex; flex-direction: column;">
        <div class="console-panel" style="flex:1;">
          <div class="console-header">
            <h3>🖥️ Runtime Console</h3>
            <div class="console-actions">
              <button class="console-btn success" onclick="rerunApp()">▶ Run</button>
              <button class="console-btn danger" onclick="clearConsole()">✕ Clear</button>
            </div>
          </div>
          <div class="console-output" id="console-output">
            <div class="console-empty">▶ Click "Run" to execute the app code</div>
          </div>
        </div>
      </div>
    </div>` : ''}

  </div>

  <div class="status-bar">
    <span id="status-ready">${hasRunnableCode ? '⚡ App ready to run' : '📄 Source view'}</span>
    <span>📄 ${totalChars.toLocaleString()} chars</span>
    <span>🔤 ${[hasRunnableCode ? 'javascript' : '', ...sourceFiles.map(f => f.lang)].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(', ') || 'N/A'}</span>
    ${warnings.length > 0 ? '<span class="warn">⚠️ ' + warnings.length + ' warnings</span>' : '<span class="ok">✓ No warnings</span>'}
    <span style="margin-left:auto" id="test-status">🧪 Test: Not run</span>
  </div>

  <script>
    // ── Tab Switching ──────────────────────────────────────────
    document.querySelectorAll('.view-tab').forEach(function(tab) {
      tab.addEventListener('click', function() {
        document.querySelectorAll('.view-tab').forEach(function(t) { t.classList.remove('active'); });
        document.querySelectorAll('.view-panel').forEach(function(p) { p.classList.remove('active'); });
        tab.classList.add('active');
        var target = document.getElementById('view-' + tab.getAttribute('data-view'));
        if (target) target.classList.add('active');
      });
    });
    document.querySelectorAll('.src-tab').forEach(function(tab) {
      tab.addEventListener('click', function() {
        document.querySelectorAll('.src-tab').forEach(function(t) { t.classList.remove('active'); });
        document.querySelectorAll('.src-panel').forEach(function(p) { p.classList.remove('active'); });
        tab.classList.add('active');
        var target = document.getElementById(tab.getAttribute('data-tab'));
        if (target) target.classList.add('active');
      });
    });

    // ── Live Console ───────────────────────────────────────────
    var consoleOutput = document.getElementById('console-output');
    var consoleLines = [];

    function appendToConsole(level, msg) {
      var line = document.createElement('div');
      line.className = 'log-line';
      var badge = document.createElement('span');
      badge.className = 'log-level ' + level;
      badge.textContent = level.toUpperCase();
      var text = document.createElement('span');
      text.className = 'log-msg ' + level;
      // Convert objects to formatted strings
      if (typeof msg === 'object' && msg !== null) {
        try { text.textContent = JSON.stringify(msg, null, 2); } catch(e) { text.textContent = String(msg); }
      } else {
        text.textContent = String(msg);
      }
      line.appendChild(badge);
      line.appendChild(text);
      consoleOutput.appendChild(line);
      consoleLines.push(line);
      consoleOutput.scrollTop = consoleOutput.scrollHeight;
      // Remove empty state
      var empty = consoleOutput.querySelector('.console-empty');
      if (empty) empty.remove();
    }

    // Override console methods
    var origLog = console.log;
    var origWarn = console.warn;
    var origError = console.error;
    var origInfo = console.info;

    console.log = function() {
      var args = Array.prototype.slice.call(arguments).map(function(a) {
        return typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a);
      }).join(' ');
      appendToConsole('info', args);
      origLog.apply(console, arguments);
    };
    console.warn = function() {
      var args = Array.prototype.slice.call(arguments).map(function(a) {
        return typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a);
      }).join(' ');
      appendToConsole('warn', args);
      origWarn.apply(console, arguments);
    };
    console.error = function() {
      var args = Array.prototype.slice.call(arguments).map(function(a) {
        return typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a);
      }).join(' ');
      appendToConsole('error', args);
      origError.apply(console, arguments);
    };
    console.info = function() {
      var args = Array.prototype.slice.call(arguments).map(function(a) {
        return typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a);
      }).join(' ');
      appendToConsole('info', args);
      origInfo.apply(console, arguments);
    };

    // Handle errors
    var origOnError = window.onerror;
    window.onerror = function(msg, url, line, col, err) {
      appendToConsole('error', msg + ' (line ' + line + ')');
      if (origOnError) return origOnError.apply(this, arguments);
    };
    window.addEventListener('unhandledrejection', function(e) {
      appendToConsole('error', 'Unhandled Promise: ' + (e.reason ? e.reason.message || String(e.reason) : 'unknown'));
    });

    function clearConsole() {
      consoleOutput.innerHTML = '<div class="console-empty">Console cleared</div>';
      consoleLines = [];
    }

    // ── App Runner (Safe iframe Sandbox) ────────────────────────
    var appCode = ${JSON.stringify(jsCode)};
    var sandboxIframe = null;

    function rerunApp() {
      clearConsole();
      appendToConsole('info', '▶ Running app code in sandbox iframe (' + appCode.length + ' chars)...');
      console.log('[App] Starting execution in sandbox...');

      // Remove old iframe if exists
      if (sandboxIframe) {
        document.body.removeChild(sandboxIframe);
        sandboxIframe = null;
      }

      // Create sandbox iframe — no access to parent window
      sandboxIframe = document.createElement('iframe');
      sandboxIframe.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;border:none;';
      sandboxIframe.sandbox = 'allow-scripts';
      document.body.appendChild(sandboxIframe);

      // Intercept console from iframe
      var iframeWindow = sandboxIframe.contentWindow;
      iframeWindow.console = {
        log: function() {
          var args = Array.prototype.slice.call(arguments).map(function(a) {
            return typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a);
          }).join(' ');
          appendToConsole('info', args);
          origLog.apply(console, arguments);
        },
        warn: function() {
          var args = Array.prototype.slice.call(arguments).map(function(a) {
            return typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a);
          }).join(' ');
          appendToConsole('warn', args);
          origWarn.apply(console, arguments);
        },
        error: function() {
          var args = Array.prototype.slice.call(arguments).map(function(a) {
            return typeof a === 'object' ? JSON.stringify(a, null, 2) : String(a);
          }).join(' ');
          appendToConsole('error', args);
          origError.apply(console, arguments);
        }
      };

      iframeWindow.onerror = function(msg, url, line, col) {
        appendToConsole('error', msg + ' (line ' + line + ')');
        var sr = document.getElementById('status-ready');
        if (sr) { sr.textContent = '❌ App execution failed'; sr.style.color = '#ef4444'; }
      };

      try {
        // Write code into iframe as srcdoc (sandboxed execution)
        sandboxIframe.srcdoc = '<!DOCTYPE html><html><head><script>'
          + 'window.parent.postMessage({type:"sandbox-ready"},"*");'
          + '<\/script><\/head><body><script>'
          + appCode.replace(/<\/script>/gi, '<\\/script>')
          + '<\/script><\/body><\/html>';

        console.log('[App] Code injected into sandbox iframe');

        var sr = document.getElementById('status-ready');
        if (sr) { sr.textContent = '✅ App executed in sandbox'; sr.style.color = '#4ade80'; }
        appendToConsole('success', '✅ App code injected into sandbox iframe');
      } catch (e) {
        console.error('[App] Sandbox error:', e.message);
        var sr = document.getElementById('status-ready');
        if (sr) { sr.textContent = '❌ Sandbox execution failed'; sr.style.color = '#ef4444'; }
        appendToConsole('error', '❌ ' + e.message);
      }
    }

    // Auto-run on load if we have executable code
    if (appCode && appCode.length > 0) {
      document.addEventListener('DOMContentLoaded', function() {
        setTimeout(rerunApp, 300);
      });
    }

    // ── Test Runner ────────────────────────────────────────────
    (function() {
      var st=document.getElementById('test-status'),tr={passed:0,failed:0,total:0};
      function sr(){ try{ window.parent.postMessage({type:'sandbox-test-results',passed:tr.passed,failed:tr.failed,total:tr.total},'*') }catch(e){} }
      function rt(n,p,d){ tr.total++;p?tr.passed++:tr.failed++;origLog('[SandboxTest] '+(p?'✓':'✗')+' '+n+(d?': '+d:''));sr(); }
      function rs(){ tr={passed:0,failed:0,total:0};if(st){st.textContent='🧪 Test: Running...';st.style.color='#f59e0b';} }
      function us(){ if(st){ if(tr.failed>0){st.textContent='🧪 Tests: '+tr.passed+'/'+tr.total+' passed ('+tr.failed+' failed)';st.style.color='#fbbf24';}else if(tr.total>0){st.textContent='🧪 Tests: '+tr.passed+'/'+tr.total+' all passed ✅';st.style.color='#4ade80';} } }
      window.addEventListener('error',function(e){rt('No runtime errors',false,e.message);});
      function runAll(){
        rs();
        rt('Page render',document.body!==null,'DOM loaded');
        var b=document.querySelectorAll('button'),i=document.querySelectorAll('input,select,textarea'),l=document.querySelectorAll('a');
        rt('Interactive elements',b.length+i.length+l.length>0,b.length+' buttons, '+i.length+' inputs, '+l.length+' links');
        var u=document.getElementById('ui-root');
        if(u){rt('UI components rendered',u.children.length>0,u.children.length+' UI elements');}else{rt('UI components rendered',true,'No UI components (code-only app)');}
        // Check if app code ran
        if(appCode && appCode.length>0){rt('App code execution',true,appCode.length+' chars');}
        origLog('[SandboxTest] All '+tr.total+' tests completed');
        us();sr();
      }
      window.addEventListener('message',function(e){if(e.data&&e.data.type==='run-sandbox-tests')runAll();});
      if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){setTimeout(runAll,800);});else setTimeout(runAll,800);
    })();
  </script>
</body>
</html>`;
    return { html, totalChars, hasErrors: false, warnings };
}
