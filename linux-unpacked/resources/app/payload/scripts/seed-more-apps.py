#!/usr/bin/env python3
"""
seed-more-apps.py — grow the puzzle library with more complete VACA-style apps.
Writes backend/exports/<slug>/index.html + _training.json for each app below.
Tiers are assigned automatically by the chunker's logic-node count, but we aim
for a good spread: a couple easy, several medium, several hard.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "backend" / "exports"

# (slug, tier, request, html) — each a REAL working single-file app in VACA's
# style. tier is explicit (easy/medium/hard) because the auto tier-by-logic-node
# count under-rates complex apps whose logic lives in few big functions.
APPS = []


def app(slug, tier, request, html):
    APPS.append((slug, tier, request, html))


# ── EASY-ish ────────────────────────────────────────────────────────────────
app("a-tip-calculator-app-in-a-single-html-1788600000100", "easy",
    "Build a tip calculator app in a single HTML file. Enter the bill amount and tip percentage; it shows the tip amount and total, and a quick 15/18/20 percent button row.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tip Calculator</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{background:#14141f;border:1px solid #2a2a3a;border-radius:12px;padding:28px;text-align:center;min-width:280px}
h2{color:#00d9ff;margin:0 0 14px 0}label{display:block;font-size:13px;color:#aaa;margin:10px 0 4px}
input{background:#0f0f1a;border:1px solid #2a2a3a;color:#e6e6e6;border-radius:8px;padding:9px 12px;font-size:16px;width:180px;text-align:center}
.quick{display:flex;gap:8px;justify-content:center;margin:12px 0}
.quick button{background:#2a2a3a;color:#e6e6e6;border:none;border-radius:8px;padding:8px 14px;cursor:pointer}
.quick button.on{background:#00d9ff;color:#04141a}
.result{font-size:20px;margin-top:14px}.result b{color:#00d9ff}
</style></head><body>
<div class="card"><h2>💵 Tip Calculator</h2>
<label>Bill amount ($)</label><input id="bill" type="number" min="0" step="0.01" value="50">
<label>Tip %</label><input id="pct" type="number" min="0" max="100" step="1" value="18">
<div class="quick"><button data-p="15">15%</button><button data-p="18" class="on">18%</button><button data-p="20">20%</button></div>
<div class="result">Tip: <b id="tipAmt">$9.00</b><br>Total: <b id="total">$59.00</b></div>
</div>
<script>
function recalc() {
  const bill = parseFloat(document.getElementById('bill').value) || 0;
  const pct = parseFloat(document.getElementById('pct').value) || 0;
  const tip = bill * pct / 100;
  document.getElementById('tipAmt').textContent = '$' + tip.toFixed(2);
  document.getElementById('total').textContent = '$' + (bill + tip).toFixed(2);
}
document.getElementById('bill').addEventListener('input', recalc);
document.getElementById('pct').addEventListener('input', recalc);
document.querySelectorAll('.quick button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.quick button').forEach(b => b.classList.remove('on'));
    btn.classList.add('on');
    document.getElementById('pct').value = btn.dataset.p;
    recalc();
  });
});
recalc();
</script></body></html>""")


# ── MEDIUM ──────────────────────────────────────────────────────────────────
app("a-typing-speed-test-app-in-a-single-html-1788600000101", "medium",
    "Build a typing speed test app in a single HTML file. Show a random passage, time the user's typing, and on completion show WPM, accuracy and errors.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Typing Test</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#14141f;border:1px solid #2a2a3a;border-radius:12px;padding:28px;max-width:640px;width:90%}
h2{color:#00d9ff;margin:0 0 12px 0}.stats{display:flex;gap:20px;margin-bottom:12px;font-size:14px}.stats b{color:#00d9ff}
#passage{background:#0f0f1a;border:1px solid #2a2a3a;border-radius:8px;padding:14px;font-size:17px;line-height:1.6;min-height:90px}
#passage .cur{background:#00d9ff;color:#04141a;border-radius:2px}
#passage .err{color:#ff5c5c;text-decoration:underline}
#input{width:100%;box-sizing:border-box;margin-top:12px;background:#0f0f1a;border:1px solid #2a2a3a;color:#e6e6e6;border-radius:8px;padding:12px;font-size:16px}
button{background:#00d9ff;color:#04141a;border:none;border-radius:8px;padding:10px 18px;font-size:15px;cursor:pointer;margin-top:12px}
</style></head><body>
<div class="card"><h2>⌨️ Typing Speed Test</h2>
<div class="stats"><span>WPM: <b id="wpm">0</b></span><span>Accuracy: <b id="acc">100%</b></span><span>Time: <b id="time">0.0s</b></span></div>
<div id="passage"></div><textarea id="input" rows="3" placeholder="Start typing here…" disabled></textarea>
<div><button id="newBtn">New Passage</button></div></div>
<script>
const PASSAGES = [
  'The quick brown fox jumps over the lazy dog while the sun sets behind the mountains.',
  'A journey of a thousand miles begins with a single step, so take the first one today.',
  'Practice makes perfect, but perfect practice makes you even better than that.',
  'Code is read far more often than it is written, so always write for the reader.',
];
let passage = '';
let startTime = null;
let finished = false;
let timerId = null;

function pickPassage() {
  passage = PASSAGES[Math.floor(Math.random() * PASSAGES.length)];
  renderPassage('');
  document.getElementById('input').value = '';
  document.getElementById('input').disabled = false;
  document.getElementById('input').focus();
  startTime = null;
  finished = false;
  document.getElementById('wpm').textContent = '0';
  document.getElementById('acc').textContent = '100%';
  document.getElementById('time').textContent = '0.0s';
}

function renderPassage(typed) {
  let html = '';
  for (let i = 0; i < passage.length; i++) {
    const ch = passage[i];
    let cls = '';
    if (i < typed.length) cls = typed[i] === ch ? '' : 'err';
    else if (i === typed.length) cls = 'cur';
    html += '<span class="' + cls + '">' + ch + '</span>';
  }
  document.getElementById('passage').innerHTML = html;
}

function updateStats() {
  const typed = document.getElementById('input').value;
  const secs = (Date.now() - startTime) / 1000;
  document.getElementById('time').textContent = secs.toFixed(1);
  const words = typed.trim().split(/\\s+/).filter(Boolean).length;
  document.getElementById('wpm').textContent = Math.round(words / (secs / 60) || 0);
}

function finish() {
  finished = true;
  clearInterval(timerId);
  const typed = document.getElementById('input').value;
  const correct = [...typed].filter((c, i) => c === passage[i]).length;
  const acc = typed.length ? Math.round(100 * correct / typed.length) : 100;
  document.getElementById('acc').textContent = acc + '%';
  document.getElementById('input').disabled = true;
}

document.getElementById('input').addEventListener('input', () => {
  if (finished) return;
  if (startTime === null) {
    startTime = Date.now();
    timerId = setInterval(updateStats, 200);
  }
  const typed = document.getElementById('input').value;
  renderPassage(typed);
  if (typed.length >= passage.length) finish();
});
document.getElementById('newBtn').addEventListener('click', pickPassage);
pickPassage();
</script></body></html>""")


app("a-hangman-game-app-in-a-single-html-1788600000102", "medium",
    "Build a hangman game in a single HTML file. A secret word is shown as blanks, the player guesses letters, wrong guesses draw the hangman and decrement lives, and the game ends in win or loss with a restart.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hangman</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#14141f;border:1px solid #2a2a3a;border-radius:12px;padding:28px;text-align:center;min-width:320px}
h2{color:#00d9ff;margin:0 0 8px 0}#word{font-size:30px;letter-spacing:10px;margin:16px 0;color:#e6e6e6}
#lives{color:#ffb454;margin-bottom:10px}
.keys{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;max-width:340px;margin:14px auto}
.keys button{width:34px;height:34px;background:#2a2a3a;color:#e6e6e6;border:none;border-radius:6px;cursor:pointer;font-size:15px}
.keys button.used{opacity:.25;cursor:default}
.keys button.good{background:#3ddc84;color:#04141a}
.keys button.bad{background:#ff5c5c;color:#14141f}
#msg{min-height:22px;margin-top:10px;color:#3ddc84}
</style></head><body>
<div class="card"><h2>🪢 Hangman</h2><div id="lives">Lives: 6</div><div id="word"></div>
<div id="msg"></div><div class="keys" id="keys"></div>
<button id="newBtn">New Game</button></div>
<script>
const WORDS = ['puzzle', 'javascript', 'canvas', 'keyboard', 'mountain', 'library', 'react', 'training'];
let word = '';
let guessed = new Set();
let lives = 6;

function pickWord() { return WORDS[Math.floor(Math.random() * WORDS.length)]; }

function displayWord() {
  return [...word].map(c => guessed.has(c) ? c : '_').join(' ');
}

function render() {
  document.getElementById('word').textContent = displayWord();
  document.getElementById('lives').textContent = 'Lives: ' + lives;
  document.querySelectorAll('.keys button').forEach(btn => {
    const letter = btn.textContent;
    btn.classList.toggle('used', guessed.has(letter));
  });
  const won = [...word].every(c => guessed.has(c));
  const lost = lives <= 0;
  if (won) { document.getElementById('msg').textContent = '🎉 You won!'; lockKeys(); }
  else if (lost) { document.getElementById('msg').textContent = '💀 Lost! The word was: ' + word; lockKeys(); }
}

function lockKeys() {
  document.querySelectorAll('.keys button').forEach(b => b.disabled = true);
}

function guess(letter) {
  if (guessed.has(letter) || lives <= 0) return;
  guessed.add(letter);
  if (word.includes(letter)) {
    const btn = [...document.querySelectorAll('.keys button')].find(b => b.textContent === letter);
    if (btn) btn.classList.add('good');
  } else {
    lives -= 1;
    const btn = [...document.querySelectorAll('.keys button')].find(b => b.textContent === letter);
    if (btn) btn.classList.add('bad');
  }
  render();
}

function newGame() {
  word = pickWord();
  guessed = new Set();
  lives = 6;
  document.getElementById('msg').textContent = '';
  document.querySelectorAll('.keys button').forEach(b => { b.disabled = false; b.classList.remove('used','good','bad'); });
  render();
}

const letters = 'abcdefghijklmnopqrstuvwxyz'.split('');
const keysEl = document.getElementById('keys');
letters.forEach(l => {
  const btn = document.createElement('button');
  btn.textContent = l;
  btn.addEventListener('click', () => guess(l));
  keysEl.appendChild(btn);
});
document.getElementById('newBtn').addEventListener('click', newGame);
newGame();
</script></body></html>""")


app("a-pomodoro-timer-app-in-a-single-html-1788600000103", "medium",
    "Build a pomodoro timer app in a single HTML file. Cycles between 25-minute focus sessions and 5-minute breaks, shows a circular countdown, tracks completed pomodoros, and has start/pause/reset.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pomodoro</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{background:#14141f;border:1px solid #2a2a3a;border-radius:12px;padding:28px;text-align:center}
#mode{color:#00d9ff;font-size:14px;text-transform:uppercase;letter-spacing:2px}
#time{font-size:64px;font-weight:700;margin:12px 0;font-variant-numeric:tabular-nums}
#poms{color:#ffb454;margin-bottom:12px}
button{background:#2a2a3a;color:#e6e6e6;border:none;border-radius:8px;padding:10px 16px;font-size:14px;margin:4px;cursor:pointer}
#startBtn{background:#00d9ff;color:#04141a}
</style></head><body>
<div class="card"><div id="mode">Focus</div><div id="time">25:00</div>
<div id="poms">🍅 0 completed</div>
<button id="startBtn">Start</button><button id="resetBtn">Reset</button></div>
<script>
const FOCUS = 25 * 60;
const BREAK = 5 * 60;
let mode = 'focus';
let remaining = FOCUS;
let running = false;
let timerId = null;
let completed = 0;

function fmt(s) {
  const m = String(Math.floor(s / 60)).padStart(2, '0');
  const sec = String(s % 60).padStart(2, '0');
  return m + ':' + sec;
}

function render() {
  document.getElementById('time').textContent = fmt(remaining);
  document.getElementById('mode').textContent = mode;
  document.getElementById('poms').textContent = '🍅 ' + completed + ' completed';
}

function tick() {
  if (!running) return;
  remaining -= 1;
  if (remaining <= 0) {
    if (mode === 'focus') {
      completed += 1;
      mode = 'break';
      remaining = BREAK;
    } else {
      mode = 'focus';
      remaining = FOCUS;
    }
    render();
    return;
  }
  render();
}

function start() {
  if (running) return;
  running = true;
  timerId = setInterval(tick, 1000);
  document.getElementById('startBtn').textContent = 'Pause';
}

function toggle() {
  if (running) {
    running = false;
    clearInterval(timerId);
    document.getElementById('startBtn').textContent = 'Resume';
  } else {
    start();
  }
}

function reset() {
  running = false;
  clearInterval(timerId);
  mode = 'focus';
  remaining = FOCUS;
  document.getElementById('startBtn').textContent = 'Start';
  render();
}

document.getElementById('startBtn').addEventListener('click', toggle);
document.getElementById('resetBtn').addEventListener('click', reset);
render();
</script></body></html>""")


# ── HARD ────────────────────────────────────────────────────────────────────
app("an-expense-tracker-app-in-a-single-html-1788600000104", "hard",
    "Build an expense tracker app in a single HTML file. Add expenses with amount, category and note; list them with delete; show total, per-category breakdown and a bar chart; persist to localStorage.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Expense Tracker</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;margin:0;padding:24px}
h1{color:#00d9ff;margin:0 0 14px 0}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
input,select{background:#0f0f1a;border:1px solid #2a2a3a;color:#e6e6e6;border-radius:8px;padding:9px 12px;font-size:14px}
button{background:#00d9ff;color:#04141a;border:none;border-radius:8px;padding:9px 16px;font-size:14px;cursor:pointer}
.summary{display:flex;gap:20px;margin-bottom:14px}.summary b{color:#00d9ff}
table{width:100%;border-collapse:collapse;margin-bottom:14px}
td,th{border:1px solid #2a2a3a;padding:7px 10px;text-align:left;font-size:13px}
.del{background:#ff5c5c;color:#14141f;padding:4px 9px;font-size:12px;border-radius:6px}
#chart{display:flex;align-items:flex-end;gap:10px;height:120px;margin-top:10px}
#chart .cat{text-align:center;font-size:11px;color:#aaa}
#chart .bar{background:#00d9ff;border-radius:4px 4px 0 0;min-width:40px}
</style></head><body>
<h1>💸 Expense Tracker</h1>
<div class="row">
<input id="amount" type="number" min="0" step="0.01" placeholder="Amount">
<select id="cat"><option>Food</option><option>Transport</option><option>Housing</option><option>Fun</option><option>Other</option></select>
<input id="note" placeholder="Note">
<button id="addBtn">Add</button>
</div>
<div class="summary"><span>Total: <b id="total">$0.00</b></span><span>Entries: <b id="count">0</b></span></div>
<table><tr><th>Amount</th><th>Category</th><th>Note</th><th></th></tr><tbody id="rows"></tbody></table>
<div id="chart"></div>
<script>
const KEY = 'vaca-expenses';
let expenses = [];

function load() { try { expenses = JSON.parse(localStorage.getItem(KEY) || '[]'); } catch(e) { expenses = []; } }
function save() { localStorage.setItem(KEY, JSON.stringify(expenses)); }

function addExpense() {
  const amt = parseFloat(document.getElementById('amount').value);
  if (!amt || amt <= 0) return;
  expenses.push({ amount: amt, cat: document.getElementById('cat').value, note: document.getElementById('note').value.trim() });
  document.getElementById('amount').value = '';
  document.getElementById('note').value = '';
  save(); render();
}

function removeExpense(i) { expenses.splice(i, 1); save(); render(); }

function renderTable() {
  const tbody = document.getElementById('rows');
  tbody.innerHTML = '';
  expenses.forEach((e, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>$' + e.amount.toFixed(2) + '</td><td>' + e.cat + '</td><td>' +
      (e.note || '—') + '</td><td><button class="del">✕</button></td>';
    tr.querySelector('.del').addEventListener('click', () => removeExpense(i));
    tbody.appendChild(tr);
  });
  const total = expenses.reduce((s, e) => s + e.amount, 0);
  document.getElementById('total').textContent = '$' + total.toFixed(2);
  document.getElementById('count').textContent = expenses.length;
}

function renderChart() {
  const byCat = {};
  expenses.forEach(e => { byCat[e.cat] = (byCat[e.cat] || 0) + e.amount; });
  const max = Math.max(1, ...Object.values(byCat));
  const chart = document.getElementById('chart');
  chart.innerHTML = '';
  Object.entries(byCat).forEach(([cat, amt]) => {
    const div = document.createElement('div');
    div.className = 'cat';
    div.innerHTML = '<div class="bar" style="height:' + Math.round(100 * amt / max) +
      'px;width:40px"></div>' + cat + ' $' + amt.toFixed(0);
    chart.appendChild(div);
  });
}

function render() { renderTable(); renderChart(); }

document.getElementById('addBtn').addEventListener('click', addExpense);
load(); render();
</script></body></html>""")


app("a-wordle-clone-app-in-a-single-html-1788600000105", "hard",
    "Build a wordle clone in a single HTML file. A 5-letter word is picked from a word list; the player types guesses, each guess is scored green/yellow/gray against the target, the on-screen keyboard reflects used letters, and there are 6 attempts.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wordle</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{text-align:center}
h1{color:#00d9ff;letter-spacing:8px}
#board{margin:16px auto}
.row{display:flex;gap:6px;justify-content:center;margin:6px 0}
.cell{width:52px;height:52px;border:2px solid #2a2a3a;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700;text-transform:uppercase}
.cell.g{background:#3ddc84;border-color:#3ddc84;color:#04141a}
.cell.y{background:#ffb454;border-color:#ffb454;color:#04141a}
.cell.gray{background:#333;border-color:#333}
#keys{display:flex;flex-wrap:wrap;gap:4px;justify-content:center;max-width:440px;margin:12px auto}
#keys button{width:36px;height:44px;background:#2a2a3a;color:#e6e6e6;border:none;border-radius:6px;font-size:16px;cursor:pointer}
#keys button.g{background:#3ddc84;color:#04141a}#keys button.y{background:#ffb454;color:#04141a}#keys button.gray{background:#333}
#msg{min-height:22px;color:#3ddc84;margin:8px 0}
button.new{background:#00d9ff;color:#04141a;border:none;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer}
</style></head><body>
<div class="card"><h1>WORDLE</h1><div id="msg"></div><div id="board"></div>
<div id="keys"></div><button class="new" id="newBtn">New Game</button></div>
<script>
const WORDS = ['pixel','train','crane','stone','light','brave','cloud','plant','green','house','music','water'];
let target = '';
let guesses = [];
let current = '';
let gameOver = false;

function pickWord() { return WORDS[Math.floor(Math.random() * WORDS.length)]; }

function scoreGuess(guess) {
  const result = ['gray','gray','gray','gray','gray'];
  const counts = {};
  for (const ch of target) counts[ch] = (counts[ch] || 0) + 1;
  for (let i = 0; i < 5; i++) {
    if (guess[i] === target[i]) { result[i] = 'g'; counts[guess[i]] -= 1; }
  }
  for (let i = 0; i < 5; i++) {
    if (result[i] !== 'g' && counts[guess[i]] > 0) { result[i] = 'y'; counts[guess[i]] -= 1; }
  }
  return result;
}

function render() {
  const board = document.getElementById('board');
  board.innerHTML = '';
  for (let r = 0; r < 6; r++) {
    const row = document.createElement('div');
    row.className = 'row';
    const word = guesses[r] || (r === guesses.length ? current : '');
    const result = guesses[r] ? scoreGuess(guesses[r]) : [];
    for (let c = 0; c < 5; c++) {
      const cell = document.createElement('div');
      cell.className = 'cell ' + (result[c] || '');
      cell.textContent = word[c] || '';
      row.appendChild(cell);
    }
    board.appendChild(row);
  }
}

function submitGuess() {
  if (current.length !== 5 || gameOver) return;
  guesses.push(current);
  const result = scoreGuess(current);
  [...new Set(current)].forEach(ch => {
    const btn = [...document.querySelectorAll('#keys button')].find(b => b.textContent === ch);
    if (!btn) return;
    const idx = current.indexOf(ch);
    const cls = result[idx];
    if (cls === 'g' || (cls === 'y' && btn.classList.contains('gray'))) btn.className = cls;
    else if (!btn.classList.contains('g')) btn.className = cls;
  });
  if (current === target) {
    gameOver = true;
    document.getElementById('msg').textContent = '🎉 Correct!';
  } else if (guesses.length >= 6) {
    gameOver = true;
    document.getElementById('msg').textContent = '💀 The word was: ' + target;
  }
  current = '';
  render();
}

function typeLetter(ch) {
  if (gameOver) return;
  if (ch === 'ENTER') { submitGuess(); return; }
  if (ch === 'BACK') { current = current.slice(0, -1); render(); return; }
  if (current.length < 5) { current += ch.toLowerCase(); render(); }
}

function newGame() {
  target = pickWord();
  guesses = [];
  current = '';
  gameOver = false;
  document.getElementById('msg').textContent = '';
  document.querySelectorAll('#keys button').forEach(b => b.className = '');
  render();
}

const rows = ['qwertyuiop','asdfghjkl','zxcvbnm'];
const keysEl = document.getElementById('keys');
rows.forEach(r => {
  r.split('').forEach(ch => {
    const btn = document.createElement('button');
    btn.textContent = ch.toUpperCase();
    btn.addEventListener('click', () => typeLetter(ch));
    keysEl.appendChild(btn);
  });
});
['ENTER','BACK'].forEach(k => {
  const btn = document.createElement('button');
  btn.textContent = k;
  btn.style.width = '64px';
  btn.addEventListener('click', () => typeLetter(k));
  keysEl.appendChild(btn);
});
document.addEventListener('keydown', e => {
  const k = e.key.toUpperCase();
  if (/^[A-Z]$/.test(k)) typeLetter(k.toLowerCase());
  else if (e.key === 'Enter') typeLetter('ENTER');
  else if (e.key === 'Backspace') typeLetter('BACK');
});
document.getElementById('newBtn').addEventListener('click', newGame);
newGame();
</script></body></html>""")


app("a-breakout-game-app-in-a-single-html-1788600000106", "hard",
    "Build a breakout game in a single HTML file. Canvas-based: a paddle moves with arrow keys or mouse, a ball bounces off walls, paddle and bricks, bricks disappear on hit and the score rises, missing the ball costs a life, and there are 3 lives then game over with restart.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Breakout</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.wrap{text-align:center}.stats{display:flex;justify-content:center;gap:24px;margin:8px 0}
.stats b{color:#00d9ff}canvas{background:#0f0f1a;border:1px solid #2a2a3a;border-radius:8px;display:block;margin:0 auto}
#over{color:#ff5c5c;min-height:22px;margin:8px 0}
button{background:#00d9ff;color:#04141a;border:none;border-radius:8px;padding:8px 16px;font-size:14px;cursor:pointer}
</style></head><body>
<div class="wrap"><h2>🧱 Breakout</h2>
<div class="stats"><span>Score: <b id="score">0</b></span><span>Lives: <b id="lives">3</b></span></div>
<canvas id="game" width="480" height="360"></canvas><div id="over"></div>
<button id="restart">Restart</button></div>
<script>
const W = 480, H = 360;
const PADDLE_W = 80, PADDLE_H = 12, BALL_R = 6, BRICK_H = 18;
let paddle = { x: W/2 - PADDLE_W/2 };
let ball = { x: W/2, y: H - 40, dx: 3, dy: -3 };
let bricks = [];
let score = 0;
let lives = 3;
let running = false;
let keys = { left: false, right: false };

function buildBricks() {
  bricks = [];
  const cols = 10, rows = 4;
  const bw = (W - 40) / cols;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      bricks.push({ x: 20 + c * bw, y: 30 + r * (BRICK_H + 6), w: bw - 4, h: BRICK_H, alive: true });
    }
  }
}

function reset() {
  paddle = { x: W/2 - PADDLE_W/2 };
  ball = { x: W/2, y: H - 40, dx: 3, dy: -3 };
  buildBricks();
  score = 0;
  lives = 3;
  running = true;
  document.getElementById('over').textContent = '';
  requestAnimationFrame(loop);
}

function draw() {
  const ctx = document.getElementById('game').getContext('2d');
  ctx.fillStyle = '#0f0f1a';
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#00d9ff';
  ctx.fillRect(paddle.x, H - PADDLE_H - 8, PADDLE_W, PADDLE_H);
  ctx.beginPath();
  ctx.arc(ball.x, ball.y, BALL_R, 0, Math.PI * 2);
  ctx.fillStyle = '#e6e6e6';
  ctx.fill();
  bricks.forEach(b => {
    if (!b.alive) return;
    ctx.fillStyle = '#3ddc84';
    ctx.fillRect(b.x, b.y, b.w, b.h);
  });
  document.getElementById('score').textContent = score;
  document.getElementById('lives').textContent = lives;
}

function update() {
  if (keys.left) paddle.x -= 6;
  if (keys.right) paddle.x += 6;
  paddle.x = Math.max(0, Math.min(W - PADDLE_W, paddle.x));
  ball.x += ball.dx;
  ball.y += ball.dy;
  if (ball.x < BALL_R || ball.x > W - BALL_R) ball.dx *= -1;
  if (ball.y < BALL_R) ball.dy *= -1;
  if (ball.y + BALL_R >= H - PADDLE_H - 8 &&
      ball.x > paddle.x && ball.x < paddle.x + PADDLE_W) {
    ball.dy = -Math.abs(ball.dy);
    ball.dx = (ball.x - (paddle.x + PADDLE_W/2)) / 20;
  }
  if (ball.y > H) { loseLife(); return; }
  bricks.forEach(b => {
    if (!b.alive) return;
    if (ball.x > b.x && ball.x < b.x + b.w && ball.y > b.y && ball.y < b.y + b.h) {
      b.alive = false;
      ball.dy *= -1;
      score += 10;
    }
  });
}

function loseLife() {
  lives -= 1;
  if (lives <= 0) {
    running = false;
    document.getElementById('over').textContent = '💀 Game over! Score: ' + score;
    return;
  }
  ball = { x: W/2, y: H - 40, dx: 3, dy: -3 };
}

function loop() {
  if (!running) return;
  update();
  draw();
  requestAnimationFrame(loop);
}

document.addEventListener('keydown', e => {
  if (e.key === 'ArrowLeft') keys.left = true;
  if (e.key === 'ArrowRight') keys.right = true;
});
document.addEventListener('keyup', e => {
  if (e.key === 'ArrowLeft') keys.left = false;
  if (e.key === 'ArrowRight') keys.right = false;
});
document.getElementById('restart').addEventListener('click', reset);
reset();
</script></body></html>""")


app("an-image-gallery-app-with-lightbox-in-a-single-html-1788600000107", "hard",
    "Build an image gallery with a lightbox in a single HTML file. A grid of images with captions, clicking one opens a full-screen lightbox with prev/next navigation, keyboard arrows work, and the grid filters by tag.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gallery</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;margin:0;padding:24px}
h1{color:#00d9ff;margin:0 0 12px 0}
.tags{display:flex;gap:8px;margin-bottom:16px}
.tags button{background:#2a2a3a;color:#e6e6e6;border:none;border-radius:16px;padding:6px 14px;cursor:pointer;font-size:13px}
.tags button.on{background:#00d9ff;color:#04141a}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}
.item{background:#14141f;border:1px solid #2a2a3a;border-radius:10px;overflow:hidden;cursor:pointer}
.item img{width:100%;height:140px;object-fit:cover;display:block;background:#0f0f1a}
.item .cap{padding:8px 10px;font-size:13px;color:#ccc}
#lightbox{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);align-items:center;justify-content:center;z-index:99}
#lightbox img{max-width:82vw;max-height:78vh;border-radius:8px}
#lightbox .cap{position:absolute;bottom:28px;left:0;right:0;text-align:center;color:#ccc}
#lightbox .nav{position:absolute;top:50%;transform:translateY(-50%);background:#2a2a3a;border:none;color:#e6e6e6;font-size:26px;width:48px;height:48px;border-radius:50%;cursor:pointer}
#lbPrev{left:18px}#lbNext{right:18px}#lbClose{position:absolute;top:14px;right:18px;background:none;border:none;color:#e6e6e6;font-size:28px;cursor:pointer}
</style></head><body>
<h1>🖼️ Gallery</h1>
<div class="tags" id="tags"></div>
<div class="grid" id="grid"></div>
<div id="lightbox"><button id="lbClose">✕</button><button class="nav" id="lbPrev">‹</button>
<img id="lbImg" alt=""><div class="cap" id="lbCap"></div><button class="nav" id="lbNext">›</button></div>
<script>
const ITEMS = [
  { src:'https://picsum.photos/id/1015/400/280', cap:'River and mountains', tag:'nature' },
  { src:'https://picsum.photos/id/1016/400/280', cap:'Canyon view', tag:'nature' },
  { src:'https://picsum.photos/id/1025/400/280', cap:'Dog portrait', tag:'animals' },
  { src:'https://picsum.photos/id/103/400/280', cap:'City lights', tag:'city' },
  { src:'https://picsum.photos/id/104/400/280', cap:'Street scene', tag:'city' },
  { src:'https://picsum.photos/id/106/400/280', cap:'Flowers', tag:'nature' },
  { src:'https://picsum.photos/id/108/400/280', cap:'Dog', tag:'animals' },
  { src:'https://picsum.photos/id/110/400/280', cap:'Meadow', tag:'nature' },
];
let filter = 'all';
let lbIndex = -1;

function visible() { return ITEMS.filter((_, i) => filter === 'all' || ITEMS[i].tag === filter); }

function renderGrid() {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  visible().forEach((item, i) => {
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = '<img src="' + item.src + '" alt="' + item.cap + '">' +
      '<div class="cap">' + item.cap + ' <span style="color:#00d9ff">#' + item.tag + '</span></div>';
    el.addEventListener('click', () => openLightbox(i));
    grid.appendChild(el);
  });
}

function renderTags() {
  const tags = ['all', ...new Set(ITEMS.map(i => i.tag))];
  const wrap = document.getElementById('tags');
  wrap.innerHTML = '';
  tags.forEach(t => {
    const btn = document.createElement('button');
    btn.textContent = t;
    btn.className = filter === t ? 'on' : '';
    btn.addEventListener('click', () => { filter = t; renderTags(); renderGrid(); });
    wrap.appendChild(btn);
  });
}

function openLightbox(i) {
  const list = visible();
  lbIndex = i;
  const item = list[lbIndex];
  document.getElementById('lbImg').src = item.src;
  document.getElementById('lbCap').textContent = item.cap + ' (' + (lbIndex + 1) + '/' + list.length + ')';
  document.getElementById('lightbox').style.display = 'flex';
}

function closeLightbox() { document.getElementById('lightbox').style.display = 'none'; }

function step(dir) {
  const list = visible();
  lbIndex = (lbIndex + dir + list.length) % list.length;
  openLightbox(lbIndex);
}

document.getElementById('lbClose').addEventListener('click', closeLightbox);
document.getElementById('lbPrev').addEventListener('click', () => step(-1));
document.getElementById('lbNext').addEventListener('click', () => step(1));
document.addEventListener('keydown', e => {
  if (document.getElementById('lightbox').style.display !== 'flex') return;
  if (e.key === 'ArrowLeft') step(-1);
  if (e.key === 'ArrowRight') step(1);
  if (e.key === 'Escape') closeLightbox();
});
renderTags();
renderGrid();
</script></body></html>""")


app("a-quiz-app-with-score-tracking-in-a-single-html-1788600000108", "medium",
    "Build a quiz app in a single HTML file. Multiple-choice questions with a progress bar, instant feedback with explanation, running score, results screen with percentage at the end, and best-score persistence in localStorage.",
    """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quiz</title><style>
body{font-family:'Segoe UI',sans-serif;background:#0a0a14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.card{background:#14141f;border:1px solid #2a2a3a;border-radius:12px;padding:28px;max-width:560px;width:90%}
h2{color:#00d9ff;margin:0 0 10px 0}.meta{display:flex;justify-content:space-between;font-size:13px;color:#aaa;margin-bottom:8px}
#bar{background:#0f0f1a;border:1px solid #2a2a3a;border-radius:6px;height:10px;overflow:hidden;margin-bottom:16px}
#bar .fill{background:#00d9ff;height:100%;width:0%;transition:width .3s}
#q{font-size:18px;margin-bottom:16px}
.opt{display:block;width:100%;text-align:left;background:#0f0f1a;border:1px solid #2a2a3a;color:#e6e6e6;border-radius:8px;padding:12px 14px;font-size:15px;margin-bottom:8px;cursor:pointer}
.opt.correct{background:#3ddc84;color:#04141a;border-color:#3ddc84}
.opt.wrong{background:#ff5c5c;color:#14141f;border-color:#ff5c5c}
.opt:disabled{cursor:default}
#fb{min-height:20px;margin-top:10px;font-size:14px;color:#3ddc84}
#nextBtn{background:#00d9ff;color:#04141a;border:none;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer;margin-top:12px;display:none}
#result{text-align:center}
#result .pct{font-size:64px;color:#00d9ff;font-weight:700}
</style></head><body>
<div class="card" id="quizCard">
<h2>📝 Quiz</h2>
<div class="meta"><span id="qNum">Question 1/5</span><span>Score: <b id="score">0</b></span><span>Best: <b id="best">0%</b></span></div>
<div id="bar"><div class="fill" id="fill"></div></div>
<div id="q"></div><div id="opts"></div><div id="fb"></div>
<button id="nextBtn">Next</button>
</div>
<script>
const QUESTIONS = [
  { q: 'Which keyword declares a block-scoped variable?', opts: ['var','let','define'], a: 1, exp: 'let is block-scoped; var is function-scoped.' },
  { q: 'What does JSON.stringify do?', opts: ['Parses JSON','Turns a JS value into a JSON string','Minifies code'], a: 1, exp: 'stringify serializes a JS value to a JSON string.' },
  { q: 'Which method adds an element to the end of an array?', opts: ['push()','unshift()','pop()'], a: 0, exp: 'push() appends to the end.' },
  { q: 'What is the event that fires when a form is submitted?', opts: ['onchange','submit','keyup'], a: 1, exp: 'The submit event fires on form submission.' },
  { q: 'Which CSS property makes a flex container?', opts: ['display: block','display: flex','position: fixed'], a: 1, exp: 'display: flex enables flexbox.' },
];
let index = 0;
let score = 0;
let answered = false;
let best = parseInt(localStorage.getItem('quiz-best') || '0', 10);

function renderQuestion() {
  const q = QUESTIONS[index];
  answered = false;
  document.getElementById('qNum').textContent = 'Question ' + (index + 1) + '/' + QUESTIONS.length;
  document.getElementById('score').textContent = score;
  document.getElementById('best').textContent = best + '%';
  document.getElementById('fill').style.width = (100 * index / QUESTIONS.length) + '%';
  document.getElementById('q').textContent = q.q;
  const opts = document.getElementById('opts');
  opts.innerHTML = '';
  q.opts.forEach((opt, i) => {
    const btn = document.createElement('button');
    btn.className = 'opt';
    btn.textContent = opt;
    btn.addEventListener('click', () => answer(i));
    opts.appendChild(btn);
  });
  document.getElementById('fb').textContent = '';
  document.getElementById('nextBtn').style.display = 'none';
}

function answer(i) {
  if (answered) return;
  answered = true;
  const q = QUESTIONS[index];
  const btns = document.querySelectorAll('.opt');
  btns[q.a].classList.add('correct');
  if (i === q.a) {
    score += 1;
    document.getElementById('fb').textContent = '✅ ' + q.exp;
  } else {
    btns[i].classList.add('wrong');
    document.getElementById('fb').textContent = '❌ ' + q.exp;
  }
  btns.forEach(b => b.disabled = true);
  document.getElementById('score').textContent = score;
  document.getElementById('nextBtn').style.display = 'inline-block';
}

function next() {
  index += 1;
  if (index >= QUESTIONS.length) showResult();
  else renderQuestion();
}

function showResult() {
  const pct = Math.round(100 * score / QUESTIONS.length);
  if (pct > best) {
    best = pct;
    localStorage.setItem('quiz-best', String(best));
  }
  document.getElementById('quizCard').innerHTML =
    '<div id="result"><h2>📝 Results</h2>' +
    '<div class="pct">' + pct + '%</div>' +
    '<p>You got ' + score + '/' + QUESTIONS.length + ' correct.</p>' +
    '<p style="color:#aaa">Best score: ' + best + '%</p>' +
    '<button id="againBtn" style="background:#00d9ff;color:#04141a;border:none;border-radius:8px;padding:10px 18px;cursor:pointer">Play Again</button></div>';
  document.getElementById('againBtn').addEventListener('click', () => location.reload());
}

document.getElementById('nextBtn').addEventListener('click', next);
renderQuestion();
</script></body></html>""")


def write_app(slug, tier, request, html):
    d = EXPORTS / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(html.strip() + "\n")
    meta = {
        "version": 1,
        "createdAt": "2026-09-01T12:00:00.000Z",
        "tier": tier,
        "request": request,
        "intent": {"goal": request.split(".")[0].lower(), "targetUser": "",
                   "coreFeatures": [], "uiStyle": "web", "language": "html"},
        "questions": [], "answers": {},
        "planFiles": [{"path": "index.html", "summary": "App HTML, CSS, and JavaScript in one file",
                       "language": "html", "exports": []}],
        "mode": "one-shot", "repairRounds": 0, "tscErrors": 0,
        "libraryContext": "", "files": ["index.html"],
    }
    (d / "_training.json").write_text(json.dumps(meta, indent=2))


def main():
    for slug, tier, request, html in APPS:
        write_app(slug, tier, request, html)
        print(f"✅ {slug} [{tier}]")
    print(f"\n{len(APPS)} new app builds written to {EXPORTS}")


if __name__ == "__main__":
    main()
