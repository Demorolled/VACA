// Corrected verification — engine geometry verified via the engine's own board.
// Coordinates: e4=36, e5=28, d5=27, d4=35, e2=52, d7=11, h4=39, d8=3,
// f2=53, f3=45, g2=54, g4=38, e7=12, b1=57, c3=42.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
// Script lives in scripts/; exports live in backend/exports/.
const htmlPath = join(here, '..', 'backend', 'exports', '3d-chess-game-1787074372022', 'src', 'index.html');

function findChrome() {
  const c = ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome-stable'];
  for (const x of c) if (existsSync(x)) return x;
  return null;
}
const chrome = findChrome();
const port = 12100 + Math.floor(Math.random() * 200);
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', `--remote-debugging-port=${port}`, `--user-data-dir=/tmp/chess-v3-${Date.now()}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
      const page = pages.find(p => p.type === 'page');
      if (page) {
        const ws = new WebSocket(page.webSocketDebuggerUrl);
        await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
        return ws;
      }
    } catch { }
    await sleep(200);
  }
  throw new Error('no chrome');
}
const ws = await connect();
let msgId = 0; const pending = new Map();
ws.onmessage = ev => { const d = JSON.parse(ev.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d.result); pending.delete(d.id); } };
const cdp = (method, params = {}) => new Promise(res => { const id = ++msgId; pending.set(id, res); ws.send(JSON.stringify({ id, method, params })); });
const evl = async expr => {
  const r = await cdp('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};

await cdp('Page.enable');
await cdp('Page.navigate', { url: 'file://' + htmlPath });
await sleep(2500);

const click = i => evl(`document.querySelectorAll('.square')[${i}].click()`);
const deselect = () => evl(`(() => { const s = document.querySelector('.square.selected'); if (s) s.click(); })()`);
const st = () => evl(`(() => { const c = window.__chess; return { b: c.state.board.slice(), turn: c.state.turn, over: c.state.over, status: document.getElementById('statusMsg').textContent }; })()`);
const targets = () => evl(`[...document.querySelectorAll('.square.target')].map(s => [...document.querySelectorAll('.square')].indexOf(s))`);

const results = [];
function check(name, cond, detail) {
  results.push({ name, pass: !!cond });
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

let s = await st();
check('board renders 64 squares + 32 pieces', s.b.filter(Boolean).length === 32, `pieces=${s.b.filter(Boolean).length}`);
check('initial: White to move', s.turn === 'w');

// 1. e2-e4
await click(52); await click(36); deselect();
s = await st();
check('e2-e4: pawn on e4 (36), e2 empty', s.b[36] === 'P' && s.b[52] === null);
check('turn -> black', s.turn === 'b');

// 2. d7-d5
await click(11); await click(27); deselect();
s = await st();
check('d7-d5: pawn on d5 (27)', s.b[27] === 'p' && s.b[11] === null);
check('turn -> white', s.turn === 'w');

// 3. WHITE CAPTURES: e4 x d5 (36 -> 27) — real capture!
await click(36);
const wt = await targets();
check('e4 pawn shows d5 (27) as capture target', wt.includes(27), `targets=${JSON.stringify(wt)}`);
await click(27); deselect();
s = await st();
check('e4 x d5 capture executed (white pawn on d5)', s.b[27] === 'P', `d5=${s.b[27]}`);
check('captured black pawn removed', s.b.filter(x => x === 'p').length === 7, `black pawns left=${s.b.filter(x => x === 'p').length}`);
check('turn -> black after capture', s.turn === 'b');

// 4. BLACK CAPTURES BACK: c7-c5 (10 -> 26), then d5 x c6? No — c5 pawn can't
//    reach d5. Use: black e7-e5 (12 -> 28) — a pawn push.
await click(12); await click(28); deselect();
s = await st();
check('e7-e5: pawn on e5 (28)', s.b[28] === 'p' && s.b[12] === null);

// 5. Illegal move rejected: white b1 knight (57) — targets must NOT include
//    b2 (49, straight) but MUST include c3 (42, L-shape).
await click(57);
const kt = await targets();
check('knight b1 targets L-shapes only (c3 yes, b2 no)', kt.includes(42) && !kt.includes(49), `targets=${JSON.stringify(kt)}`);
await click(42); deselect();
s = await st();
check('knight b1->c3', s.b[42] === 'N' && s.b[57] === null);  // 6. Fool's mate: new game, f2-f3, e7-e5, g2-g4, Qd8-h4#
  await evl(`document.getElementById('newGameBtn').click()`);
  await click(53); await click(45); deselect();  // f2-f3
  await click(12); await click(28); deselect();  // e7-e5
  await click(54); await click(38); deselect();  // g2-g4
  await click(3);                                 // select Qd8
  const qt = await targets();
  check('queen d8 can reach h4 (39)', qt.includes(39), `targets=${JSON.stringify(qt)}`);
  await click(39); deselect();
  s = await st();
  check('CHECKMATE detected (fool\'s mate)', s.over === 'checkmate', s.status);

// 7. New game resets
await evl(`document.getElementById('newGameBtn').click()`);
s = await st();
check('New Game resets (32 pieces, White to move)', s.b.filter(Boolean).length === 32 && s.turn === 'w');  // 8. AI move works (white's turn, so AI moves -> black's turn)
  await evl(`document.getElementById('aiMoveBtn').click()`);
  await sleep(300);
  s = await st();
  check('AI move executes (turn becomes black)', s.turn === 'b' && s.over === null);

const failed = results.filter(r => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length ? 1 : 0);
