'use strict';
/**
 * Veronica (VACA) — Electron main process.
 *
 * Runs the app from a WRITABLE per-user copy of the bundled payload.
 *
 * Why a copy: the backend writes next to itself (data/, projects/, users/,
 * scripts/, knowledge/). Inside an installed app those paths are root-owned
 * (/opt/... or /usr/lib/...), so the backend would fail the moment it tried to
 * record a plan or a design. On first run we mirror the payload into the user's
 * data dir and run the backend from there.
 *
 * The backend runs on Electron's OWN bundled Node (ELECTRON_RUN_AS_NODE=1), so
 * the machine does not need Node installed.
 *
 * LLM: shipped pinned to a single Qwen2.5 14B model (see llm-config.qwen14b.json).
 * main.js rewrites runtime/backend/llm-config.json from Settings on every launch.
 */
const { app, BrowserWindow, ipcMain, shell, Menu, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const net = require('node:net');
const http = require('node:http');
const { spawn } = require('node:child_process');

const PAYLOAD_DIR = path.join(__dirname, 'payload');
const USER_DIR = app.getPath('userData');
const RUNTIME_DIR = path.join(USER_DIR, 'runtime');
const LOG_DIR = path.join(USER_DIR, 'logs');
const SETTINGS_FILE = path.join(USER_DIR, 'settings.json');
const BACKEND_LOG = path.join(LOG_DIR, 'backend.log');

/**
 * Bump when stageRuntime()'s behaviour changes (which dirs it seeds, etc.).
 * The payload stamp only covers the payload's own bytes, so without this a
 * change to the STAGING LOGIC would never trigger a re-stage — an existing
 * runtime copy would keep whatever the old logic produced, forever.
 */
const STAGING_VERSION = 3;

const DEFAULTS = {
  mode: 'local',                              // 'local' | 'remote'
  remoteBackendUrl: '',                       // e.g. http://192.168.1.234:3001
  llmBaseUrl: 'http://127.0.0.1:11434/v1',    // Ollama / OpenAI-compatible endpoint
  llmModel: 'qwen2.5-coder:14b',              // the ONLY model this build ships with
  port: 3001,
  devTools: false,
};

let backendProc = null;
let backendPort = null;
let mainWindow = null;
let settingsWindow = null;

// ── settings ────────────────────────────────────────────────────────────────
function readSettings() {
  try {
    const raw = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf8'));
    return { ...DEFAULTS, ...raw };
  } catch {
    return { ...DEFAULTS };
  }
}

function writeSettings(patch) {
  const merged = { ...readSettings(), ...patch };
  fs.mkdirSync(USER_DIR, { recursive: true });
  fs.writeFileSync(SETTINGS_FILE, JSON.stringify(merged, null, 2));
  return merged;
}

function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.join(' ')}`;
  try {
    fs.mkdirSync(LOG_DIR, { recursive: true });
    fs.appendFileSync(path.join(LOG_DIR, 'main.log'), line + '\n');
  } catch { /* logging must never break boot */ }
  console.log(line);
}

// ── payload staging ─────────────────────────────────────────────────────────
function payloadStamp() {
  try {
    return fs.readFileSync(path.join(PAYLOAD_DIR, 'PAYLOAD.json'), 'utf8');
  } catch {
    return null;
  }
}

/**
 * Mirror the read-only payload into the writable runtime dir.
 * Code dirs are refreshed whenever the payload stamp changes; user-data dirs
 * (data/, projects/) are seeded only if absent so upgrades never clobber work.
 */
function stageRuntime() {
  const stamp = `${payloadStamp() || ''}::staging-v${STAGING_VERSION}`;
  const stampFile = path.join(RUNTIME_DIR, '.payload-stamp');
  let current = null;
  try { current = fs.readFileSync(stampFile, 'utf8'); } catch { /* first run */ }

  if (stamp && current === stamp && fs.existsSync(RUNTIME_DIR)) return false;

  fs.mkdirSync(RUNTIME_DIR, { recursive: true });

  // `backend/users/` (per-user roadmaps, code-exports, projects) and
  // `backend/data/` (projects.json) hold state the RUNNING backend writes, but
  // they live under `backend/`, which is wiped and re-copied on every re-stage.
  // A payload or staging-version bump therefore silently destroyed a user's
  // project state on upgrade. Stash them across the copy, then merge them back.
  const stashed = [];
  const stashDir = path.join(RUNTIME_DIR, '.stash-preserved');
  fs.rmSync(stashDir, { recursive: true, force: true });
  fs.mkdirSync(stashDir, { recursive: true });
  for (const rel of ['users', 'data']) {
    const src = path.join(RUNTIME_DIR, 'backend', rel);
    if (!fs.existsSync(src)) continue;
    try {
      fs.renameSync(src, path.join(stashDir, rel));
      stashed.push(rel);
    } catch { /* locked/cross-device — leave it, it is reseeded below */ }
  }

  for (const rel of ['backend', 'frontend']) {
    const dst = path.join(RUNTIME_DIR, rel);
    fs.rmSync(dst, { recursive: true, force: true });
    fs.cpSync(path.join(PAYLOAD_DIR, rel), dst, { recursive: true });
  }

  // Merge (not replace) so freshly-shipped seed files survive while the user's
  // own files win on name collisions.
  for (const rel of stashed) {
    fs.cpSync(path.join(stashDir, rel), path.join(RUNTIME_DIR, 'backend', rel), { recursive: true });
    log('preserved user data across re-stage ->', path.join('backend', rel));
  }
  fs.rmSync(stashDir, { recursive: true, force: true });

  for (const rel of ['node_modules']) {
    const src = path.join(PAYLOAD_DIR, rel);
    if (!fs.existsSync(src)) continue;
    const dst = path.join(RUNTIME_DIR, rel);
    fs.rmSync(dst, { recursive: true, force: true });
    fs.cpSync(src, dst, { recursive: true });
  }

  // `scripts/` is seeded too: backend/src/sandbox/behavioralSmoke.ts runs
  // scripts/smoke-test-html.py as the primary render-smoke gate. Shipping it in
  // the payload without staging it here left the gate reporting a missing-file
  // reason and falling back to the (working) TS Playwright engine.
  for (const rel of ['knowledge', 'projects', 'apps', 'bible-reference', 'data', 'scripts']) {
    const src = path.join(PAYLOAD_DIR, rel);
    const dst = path.join(RUNTIME_DIR, rel);
    if (fs.existsSync(src) && !fs.existsSync(dst)) {
      fs.cpSync(src, dst, { recursive: true });
    }
  }

  for (const f of ['modelVeronice.txt', 'tts-config.json', 'config.yaml']) {
    const src = path.join(PAYLOAD_DIR, f);
    const dst = path.join(RUNTIME_DIR, f);
    if (fs.existsSync(src) && !fs.existsSync(dst)) {
      try { fs.copyFileSync(src, dst); } catch { /* optional seed */ }
    }
  }

  fs.writeFileSync(stampFile, stamp);
  log('payload staged ->', RUNTIME_DIR, stamp ? `(stamp ${stamp.trim().slice(0, 24)})` : '(no stamp)');
  return true;
}

// ── LLM config (pinned to Qwen2.5 14B) ──────────────────────────────────────
function writeLlmConfig(settings) {
  const entry = {
    provider: 'ollama',
    model: settings.llmModel,
    baseUrl: settings.llmBaseUrl.replace(/\/+$/, ''),
    apiKey: 'ollama',
    nCtx: 16384,
  };
  // NOTE: deliberately NO `dspark` key — backend/src/index.ts picks
  // `dspark || ollama || primary`, and translator.ts picks `dspark ? ... : ollama`.
  // Omitting it is what forces every role onto Ollama / Qwen2.5 14B.
  const cfg = {
    provider: 'ollama',
    ollama: { ...entry },
    primary: { ...entry },
    secondary: { ...entry },
    fastChat: { ...entry },
    roles: { reasoning: { ...entry }, coding: { ...entry } },
  };
  const cfgPath = path.join(RUNTIME_DIR, 'backend', 'llm-config.json');
  fs.mkdirSync(path.dirname(cfgPath), { recursive: true });
  fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2));
  return cfgPath;
}

// ── backend process ─────────────────────────────────────────────────────────
/**
 * Find a usable port and return the ACTUAL number bound.
 * Tries `preferred` first; if it is busy, falls back to an OS-assigned port.
 * Returns 0 only if the OS could not assign one either, which the caller
 * treats as a hard failure rather than silently passing 0 to the backend.
 */
function freePort(preferred) {
  const bind = (p) => new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(p, '127.0.0.1', () => {
      const actual = srv.address().port;
      srv.close(() => resolve(actual));
    });
  });

  return (async () => {
    if (preferred) {
      try {
        return await bind(preferred);
      } catch {
        log('preferred port busy, falling back to an OS-assigned port:', preferred);
      }
    }
    try {
      return await bind(0);
    } catch (err) {
      log('could not find a free port:', err.message);
      return 0;
    }
  })();
}

function httpGetOk(url, timeoutMs) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 400);
    });
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

async function waitForHealth(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const url = `http://127.0.0.1:${port}/health`;
  while (Date.now() < deadline) {
    if (await httpGetOk(url, 4000)) return true;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

async function startBackend(settings) {
  const entry = path.join(RUNTIME_DIR, 'backend', 'dist', 'index.js');
  if (!fs.existsSync(entry)) {
    throw new Error(`Bundled backend missing at ${entry}`);
  }
  const port = await freePort(settings.port || 3001);
  if (!port) throw new Error('No free TCP port available for the bundled backend.');
  fs.mkdirSync(LOG_DIR, { recursive: true });
  const stream = fs.createWriteStream(BACKEND_LOG, { flags: 'a' });
  stream.write(`\n===== backend start ${new Date().toISOString()} (port ${port}) =====\n`);

  const llmRoot = settings.llmBaseUrl.replace(/\/v1\/?$/, '');

  backendProc = spawn(process.execPath, [entry], {
    cwd: RUNTIME_DIR,                       // backend resolves ../../data etc. from here
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',            // run Electron's bundled Node as plain node
      NODE_ENV: 'production',
      PORT: String(port),
      BIND_HOST: '127.0.0.1',
      OLLAMA_BASE_URL: llmRoot,
      VACA_STRICT_CORS: '1',
      // The UI is served BY this backend, so its requests carry
      // Origin: http://127.0.0.1:<port>. That origin is not in the backend's
      // built-in allowlist (which only lists the Vite dev ports), and the cors
      // middleware evaluates its origin callback even for same-origin requests —
      // so without this every API call 500s. The backend appends FRONTEND_URL to
      // its allowlist; supply the exact origin, which varies with the port.
      FRONTEND_URL: `http://127.0.0.1:${port}`,
      DSPARK_AUTOSTART: '0',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  backendProc.stdout.pipe(stream);
  backendProc.stderr.pipe(stream);
  backendProc.on('exit', (code, sig) => {
    log(`backend exited code=${code} signal=${sig}`);
    backendProc = null;
  });

  const healthy = await waitForHealth(port, 90000);
  if (!healthy) throw new Error(`Backend did not become healthy on port ${port}. See ${BACKEND_LOG}`);
  backendPort = port;
  log('backend healthy on port', port);
  return port;
}

function stopBackend() {
  if (backendProc) {
    try { backendProc.kill(); } catch { /* already gone */ }
    backendProc = null;
  }
}

// ── windows / menu ──────────────────────────────────────────────────────────
function createMainWindow(settings, port) {
  const useRemote = settings.mode === 'remote' && settings.remoteBackendUrl;
  const target = useRemote ? settings.remoteBackendUrl : `http://127.0.0.1:${port}`;

  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0d0d1a',
    title: 'Veronica — AI Code Architect',
    icon: path.join(__dirname, 'build', 'icon-512.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (settings.devTools) mainWindow.webContents.openDevTools({ mode: 'detach' });

  // keep in-app navigation inside the app; send real external links to the browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://127.0.0.1') || (useRemote && url.startsWith(settings.remoteBackendUrl))) {
      return { action: 'allow' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.loadURL(target);
  mainWindow.on('closed', () => { mainWindow = null; });

  if (settings.devTools) {
    mainWindow.webContents.on('did-fail-load', (_e, code, desc) => {
      log('did-fail-load', code, desc);
    });
  }
  return mainWindow;
}

function openSettingsWindow() {
  if (settingsWindow) { settingsWindow.focus(); return; }
  settingsWindow = new BrowserWindow({
    width: 620,
    height: 640,
    resizable: false,
    title: 'Veronica — Settings',
    backgroundColor: '#0d0d1a',
    parent: mainWindow || undefined,
    modal: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  settingsWindow.setMenuBarVisibility(false);
  settingsWindow.loadFile(path.join(__dirname, 'settings.html'));
  settingsWindow.on('closed', () => { settingsWindow = null; });
}

function buildMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        { label: 'Settings…', accelerator: 'CmdOrCtrl+,', click: openSettingsWindow },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
        { role: 'toggleDevTools' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Open data folder',
          click: () => { shell.openPath(RUNTIME_DIR); },
        },
        {
          label: 'Open logs',
          click: () => { shell.openPath(LOG_DIR); },
        },
        {
          label: 'Show status',
          click: async () => {
            const s = readSettings();
            const healthy = backendPort ? await httpGetOk(`http://127.0.0.1:${backendPort}/health`, 3000) : false;
            dialog.showMessageBox({
              type: 'info',
              title: 'Veronica status',
              message: [
                `Mode: ${s.mode}${s.mode === 'remote' ? ` (${s.remoteBackendUrl})` : ''}`,
                `Local backend port: ${backendPort ?? 'not running'}`,
                `Backend healthy: ${healthy ? 'yes' : 'no'}`,
                `LLM endpoint: ${s.llmBaseUrl}`,
                `LLM model: ${s.llmModel}`,
                '',
                `Runtime: ${RUNTIME_DIR}`,
                `Logs: ${LOG_DIR}`,
                '',
                demoSummary(),
              ].join('\n'),
            });
          },
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ── IPC ─────────────────────────────────────────────────────────────────────
function registerIpc() {
  ipcMain.handle('settings:get', () => readSettings());
  ipcMain.handle('settings:save', (_e, patch) => {
    const merged = writeSettings(patch || {});
    log('settings saved', JSON.stringify(merged));
    // Relaunch so staging + backend + window all restart cleanly.
    app.relaunch();
    app.exit(0);
    return merged;
  });
  ipcMain.handle('status:get', async () => {
    const s = readSettings();
    const healthy = backendPort ? await httpGetOk(`http://127.0.0.1:${backendPort}/health`, 3000) : false;
    return {
      mode: s.mode,
      remoteBackendUrl: s.remoteBackendUrl,
      llmBaseUrl: s.llmBaseUrl,
      llmModel: s.llmModel,
      port: backendPort,
      healthy,
      runtimeDir: RUNTIME_DIR,
      logDir: LOG_DIR,
      version: app.getVersion(),
      demo: DEMO,
      demoExpires: DEMO_EXPIRES,
      demoDaysLeft: DEMO ? demoDaysLeft() : null,
    };
  });
  ipcMain.handle('runtime:open', () => { shell.openPath(RUNTIME_DIR); });
  ipcMain.handle('logs:open', () => { shell.openPath(LOG_DIR); });
  ipcMain.handle('app:relaunch', () => { app.relaunch(); app.exit(0); });
}

// ── demo build ──────────────────────────────────────────────────────────────
/**
 * This is a time-limited DEMO. It behaves exactly like a normal build until
 * DEMO_EXPIRES (inclusive), then refuses to start.
 *
 * The deadline is a fixed calendar date on purpose: there is no stored start
 * date, no activation, no server, and nothing written outside the app's own log
 * — so a copy behaves identically wherever it is installed and whenever it is
 * first run. The trade for that simplicity is that the check trusts the local
 * clock: winding the machine's date back will keep the demo alive. Making that
 * harder needs state (a stored "highest date ever seen"), which is a deliberate
 * decision to make later, not a bug.
 */
const DEMO = true;
const DEMO_EXPIRES = '2026-12-09';

/**
 * Local end-of-day on the last day the demo runs, so 2026-12-09 itself is still
 * a working day. Parsed without a timezone suffix, which makes it local time.
 */
const DEMO_DEADLINE = new Date(`${DEMO_EXPIRES}T23:59:59.999`);

function demoExpired(now = new Date()) {
  return DEMO && now.getTime() > DEMO_DEADLINE.getTime();
}

/** Whole days remaining; 0 on the final day, clamped at 0 once past. */
function demoDaysLeft(now = new Date()) {
  const ms = DEMO_DEADLINE.getTime() - now.getTime();
  return ms <= 0 ? 0 : Math.ceil(ms / 86400000);
}

/** One line for the status dialogs. */
function demoSummary() {
  if (!DEMO) return 'Licensed build';
  return `Demo — runs until ${DEMO_EXPIRES} (${demoDaysLeft()} day(s) left)`;
}

// ── boot ────────────────────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus(); }
  });

  app.whenReady().then(async () => {
    // Before anything else: no runtime staging, no backend, no window. An
    // expired demo does not get a working app behind the dialog.
    if (demoExpired()) {
      log('demo expired on', DEMO_EXPIRES, '— refusing to start');
      dialog.showMessageBoxSync({
        type: 'info',
        title: 'Veronica — demo period ended',
        message: 'This demo copy of Veronica has expired.',
        detail: [
          `This was a two-month demo, and it stopped running after ${DEMO_EXPIRES}.`,
          '',
          'Nothing was deleted. Your saved projects are still on this machine in:',
          `  ${RUNTIME_DIR}`,
          '',
          'A licensed build is required to carry on using it.',
        ].join('\n'),
        buttons: ['Close'],
        noLink: true,
      });
      app.exit(0);
      return;
    }

    const settings = readSettings();
    log('app start', app.getVersion(), 'mode=' + settings.mode, '|', demoSummary());

    try {
      stageRuntime();
      writeLlmConfig(settings);
    } catch (err) {
      dialog.showErrorBox('Veronica — startup error', `Could not prepare the runtime copy:\n${err.message}\n\nRuntime: ${RUNTIME_DIR}`);
    }

    let port = null;
    if (settings.mode !== 'remote' || !settings.remoteBackendUrl) {
      try {
        port = await startBackend(settings);
      } catch (err) {
        log('backend start failed:', err.message);
        dialog.showErrorBox(
          'Veronica — backend failed to start',
          `${err.message}\n\nTry Help ▸ Show status, or open the logs folder.\n\nLogs: ${LOG_DIR}`
        );
      }
    }

    buildMenu();
    registerIpc();
    createMainWindow(settings, port);
  });

  app.on('window-all-closed', () => { app.quit(); });
  app.on('before-quit', stopBackend);
  app.on('will-quit', stopBackend);
}
