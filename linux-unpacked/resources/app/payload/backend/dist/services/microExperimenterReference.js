/**
 * Micro-App Build Reference — 10 curated "before → after" worked examples
 * =======================================================================
 *
 * Each example shows the SAME micro-app written plainly (baseline) and then
 * improved to be SMALLER (fewer bytes/lines), FASTER, and MORE UNIVERSAL (a
 * generic, reusable shape). The `lesson` distills the design pattern so the
 * LLM can generalize it to new apps — not just copy the code.
 *
 * These are injected into the experimenter's rewrite/design prompts as the
 * teaching reference ("emulate this style"), and are the seed cases for the
 * full catalog of micro-apps the experimenter builds during idle time.
 */
export const MICRO_BUILD_REFERENCES = [
    {
        id: 'password-checker',
        title: 'password strength checker',
        nodeType: 'logic',
        language: 'typescript',
        baseline: `const readline = require('readline');
function checkStrength(pw) {
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[a-z]/.test(pw)) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score >= 4) return 'strong';
  if (score >= 2) return 'medium';
  return 'weak';
}
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
rl.question('Enter password: ', (pw) => { console.log('Strength: ' + checkStrength(pw)); rl.close(); });`,
        improved: `const rl = require('readline').createInterface({ input: process.stdin, output: process.stdout });
const checks = [/.{8}/, /\\d/, /[a-z]/, /[A-Z]/, /[^A-Za-z0-9]/];
const rate = pw => ['weak','medium','strong'][Math.min(2, Math.floor(checks.filter(c => c.test(pw)).length / 2))];
rl.question('Enter password: ', pw => { console.log('Strength: ' + rate(pw)); rl.close(); });`,
        lesson: 'Express the scoring rules as a data-driven array of regex tests and map the count to a label with one arithmetic expression. Fewer branches, trivial to extend, and the "checklist → category" shape generalizes to any validator.',
    },
    {
        id: 'mini-server',
        title: 'mini http server',
        nodeType: 'api',
        language: 'javascript',
        baseline: `const http = require('http');
const server = http.createServer((req, res) => {
  let body = '<h1>Hello</h1>';
  if (req.url === '/about') body = '<h1>About</h1>';
  if (req.url === '/api') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end(body);
});
server.listen(3000, () => console.log('listening on 3000'));`,
        improved: `const http = require('http');
const routes = {
  '/': '<h1>Home</h1>',
  '/about': '<h1>About</h1>',
  '/api': JSON.stringify({ ok: true }),
};
http.createServer((req, res) => {
  const api = req.url === '/api';
  res.writeHead(200, { 'Content-Type': api ? 'application/json' : 'text/html' });
  res.end(routes[req.url] ?? routes['/']);
}).listen(3000, () => console.log('listening on 3000'));`,
        lesson: 'Model routes as a lookup object (path → response) instead of an if/else chain. Adding a route is one line, the unmatched case shares one fallback, and object-dispatch is a universal pattern for any state machine or lookup table.',
    },
    {
        id: 'simple-media-player',
        title: 'simple media player',
        nodeType: 'ui',
        language: 'html',
        baseline: `<!doctype html><title>Player</title>
<audio id="a" src="song.mp3"></audio>
<div>
  <button onclick="document.getElementById('a').play()">Play</button>
  <button onclick="document.getElementById('a').pause()">Pause</button>
</div>`,
        improved: `<!doctype html><title>Player</title>
<audio id="a" src="song.mp3" controls autoplay></audio>`,
        lesson: 'Use the native <audio controls> element instead of hand-wiring Play/Pause buttons — the browser provides play/pause/seek/volume for free, works across browsers, and removes all application logic.',
    },
    {
        id: 'todo-cli',
        title: 'todo list cli',
        nodeType: 'logic',
        language: 'typescript',
        baseline: `const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const todos = [];
const add = t => todos.push({ text: t, done: false });
const list = () => todos.forEach((t, i) => console.log((t.done ? '[x]' : '[ ]') + ' ' + i + ' ' + t.text));
const done = i => { if (todos[i]) todos[i].done = true; };
function prompt() {
  rl.question('> ', (line) => {
    const parts = line.trim().split(' ');
    const cmd = parts[0];
    const arg = parts.slice(1).join(' ');
    if (cmd === 'add') add(arg);
    else if (cmd === 'done') done(parseInt(arg));
    else if (cmd === 'list') list();
    list();
    prompt();
  });
}
prompt();`,
        improved: `const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
let todos = [];
const cmds = {
  add: t => todos = [...todos, { text: t, done: false }],
  list: () => todos.forEach((t, i) => console.log(\`\${t.done ? '[x]' : '[ ]'} \${i} \${t.text}\`)),
  done: n => { todos[n].done = true; },
};
const arg = a => isNaN(+a[0]) ? a.join(' ') : +a[0];
const repl = () => rl.question('> ', l => {
  const [c, ...rest] = l.trim().split(' ');
  (cmds[c] ?? (() => {}))(arg(rest));
  cmds.list();
  repl();
});
repl();`,
        lesson: 'Drive the whole REPL through a command table with one arg-coercion rule (number when numeric, string otherwise). A command map is a universal dispatcher — the same shape powers any CLI, event system, or menu.',
    },
    {
        id: 'markdown-to-html',
        title: 'markdown to html converter',
        nodeType: 'logic',
        language: 'typescript',
        baseline: `const fs = require('fs');
const input = fs.readFileSync(process.argv[2] || 'input.md', 'utf8');
const html = input.split('\\n').map(line => {
  if (line.startsWith('# ')) return '<h1>' + line.slice(2) + '</h1>';
  if (line.startsWith('## ')) return '<h2>' + line.slice(3) + '</h2>';
  if (line.startsWith('- ')) return '<li>' + line.slice(2) + '</li>';
  return line ? '<p>' + line + '</p>' : '';
}).join('\\n');
console.log(html);`,
        improved: `const fs = require('fs');
const rules = [[/^# (.*)$/, '<h1>$1</h1>'], [/^## (.*)$/, '<h2>$1</h2>'], [/^- (.*)$/, '<li>$1</li>']];
const convert = l => { for (const [re, out] of rules) if (re.test(l)) return l.replace(re, out); return l ? \`<p>\${l}</p>\` : ''; };
console.log(fs.readFileSync(process.argv[2] || 'input.md', 'utf8').split('\\n').map(convert).join('\\n'));`,
        lesson: 'Encode the converter as an ordered table of (test, transform) rules — each rule is one line and the loop is shared. A rules table is a universal transform engine; adding a markdown element is a single table entry.',
    },
    {
        id: 'temp-converter',
        title: 'temperature converter',
        nodeType: 'ui',
        language: 'html',
        baseline: `<!doctype html><title>Temp</title>
<input id="c" placeholder="Celsius"><button onclick="conv()">To F</button>
<div id="out"></div>
<script>
function conv() {
  const c = document.getElementById('c').value;
  const f = parseFloat(c) * 9 / 5 + 32;
  document.getElementById('out').textContent = f;
}
</script>`,
        improved: `<!doctype html><title>Temp</title>
<input id="c"><span>°C → <output id="out"></output>°F</span>
<script>
const toF = c => c * 9 / 5 + 32;
c.oninput = () => out.textContent = isNaN(c.value) ? '' : toF(parseFloat(c.value)).toFixed(1);
</script>`,
        lesson: 'Recalculate from the input event rather than a button click, and isolate the math in one tiny pure function. The "map one magnitude through a pure transform" shape is universal — swap toF and the same UI does km/miles, any unit pair, or any linear mapping.',
    },
    {
        id: 'stopwatch',
        title: 'simple stopwatch',
        nodeType: 'ui',
        language: 'html',
        baseline: `<!doctype html><title>Timer</title>
<div id="d">0:00</div>
<button onclick="tog()">Start/Stop</button>
<script>
let ms = 0, id = null;
function tog() {
  if (id) { clearInterval(id); id = null; }
  else id = setInterval(() => { ms += 100; d.textContent = (ms / 1000).toFixed(1) + 's'; }, 100);
}
</script>`,
        improved: `<!doctype html><title>Timer</title>
<div id="d">0:00</div><button id="b">▶</button>
<script>
let on = false, acc = 0, t;
b.onclick = () => { on = !on; b.textContent = on ? '⏸' : '▶'; t = performance.now(); if (on) tick(); };
function tick() {
  d.textContent = ((acc + (on ? performance.now() - t : 0)) / 1000).toFixed(1) + 's';
  if (on) requestAnimationFrame(tick);
}
</script>`,
        lesson: 'Measure against an absolute clock (performance.now()) and diff, never accumulate a tick counter — that removes drift and timer throttling entirely. The absolute-now diff pattern also powers countdowns, FPS meters, and progress bars.',
    },
    {
        id: 'word-counter',
        title: 'character and word counter',
        nodeType: 'logic',
        language: 'typescript',
        baseline: `const fs = require('fs');
const text = fs.readFileSync(process.argv[2] || '', 'utf8');
const words = text.trim().split(/\\s+/).filter(w => w.length > 0);
const letters = text.replace(/\\s/g, '').length;
console.log('Words: ' + words.length);
console.log('Chars: ' + letters);`,
        improved: `const t = require('fs').readFileSync(process.argv[2] || '', 'utf8').trim();
console.log('Words: ' + t.split(/\\s+/).filter(Boolean).length + ' | Chars: ' + t.replace(/\\s/g, '').length);`,
        lesson: 'Collapse to a single statement and use filter(Boolean) to drop empties. Small count helpers like "count non-whitespace tokens" are reusable across logs, diffs, and search indexing.',
    },
    {
        id: 'notes-app',
        title: 'notes app with add/list/delete',
        nodeType: 'ui',
        language: 'html',
        baseline: `<!doctype html><title>Notes</title>
<input id="n"><button onclick="add()">Add</button>
<ul id="l"></ul>
<script>
const notes = [];
function add() {
  const t = document.getElementById('n').value;
  if (!t) return;
  notes.push(t);
  document.getElementById('n').value = '';
  render();
}
function render() {
  const ul = document.getElementById('l');
  ul.innerHTML = '';
  notes.forEach((n, i) => {
    const li = document.createElement('li');
    li.textContent = i + ': ' + n;
    ul.appendChild(li);
  });
}
</script>`,
        improved: `<!doctype html><title>Notes</title>
<input id="n"><button id="b">Add</button><ul id="l"></ul>
<script>
let notes = [];
const render = () => l.innerHTML = notes.map((t, i) => \`<li>\${i}: \${t}</li>\`).join('');
b.onclick = () => { const v = n.value.trim(); if (v) { notes.push(v); n.value = ''; render(); } };
</script>`,
        lesson: 'Keep state in one plain array and re-render the whole list from it on every change — never hand-manipulate the DOM. Deriving the view from state is the universal pattern behind component frameworks and keeps single-file apps small and bug-free.',
    },
    {
        id: 'quiz-app',
        title: 'quiz app with hardcoded questions',
        nodeType: 'ui',
        language: 'html',
        baseline: `<!doctype html><title>Quiz</title>
<div id="q"></div><div id="r"></div>
<script>
const quiz = [
  { q: '2+2?', opts: ['3', '4', '5'], a: 1 },
  { q: 'Capital of France?', opts: ['Berlin', 'Paris', 'Rome'], a: 1 },
];
let i = 0, score = 0;
function render() {
  if (i >= quiz.length) { r.textContent = 'Score: ' + score + '/' + quiz.length; return; }
  const item = quiz[i];
  q.innerHTML = item.q + '<br>' + item.opts.map((o, k) => '<button onclick="ans(' + k + ')">' + o + '</button>').join('');
}
function ans(k) { if (k === quiz[i].a) score++; i++; render(); }
render();
</script>`,
        improved: `<!doctype html><title>Quiz</title>
<div id="q"></div>
<script>
const quiz = [{ q: '2+2?', o: ['3', '4', '5'], a: 1 }, { q: 'Capital of France?', o: ['Berlin', 'Paris', 'Rome'], a: 1 }];
let i = 0, s = 0;
const ask = () => q.innerHTML = quiz[i].q + quiz[i].o.map((o, k) => \`<button onclick="ans(\${k})">\${o}</button>\`).join('');
const ans = k => { if (k === quiz[i].a) s++; if (++i < quiz.length) ask(); else q.innerHTML = \`Score \${s}/\${quiz.length}\`; };
ask();
</script>`,
        lesson: 'Run the quiz as a tiny state machine: one advance step mutates the shared index/score and re-renders, branching on the terminal condition. That shape is reusable for slideshows, carousels, and wizards.',
    },
    {
        id: 'rust-word-counter',
        title: 'word counter in rust',
        nodeType: 'logic',
        language: 'rust',
        baseline: `use std::io::{self, BufRead};

fn main() {
    let stdin = io::stdin();
    let mut words = 0usize;
    let mut chars = 0usize;
    for line in stdin.lock().lines() {
        let line = line.unwrap();
        words += line.split_whitespace().count();
        chars += line.chars().count();
    }
    println!("Words: {}", words);
    println!("Characters: {}", chars);
}`,
        improved: `use std::io::{self, Read};

fn main() {
    let mut text = String::new();
    io::stdin().read_to_string(&mut text).unwrap();
    let words = text.split_whitespace().count();
    println!("Words: {words}\nCharacters: {}", text.chars().count());
}`,
        lesson: 'Collapse per-line accumulation into a single `read_to_string`, then derive both counts with iterator adapters over the whole buffer. One pass, no manual loop, and the "reduce a stream to summary stats" shape generalizes to any text metric. Standard library only — no crates.',
    },
    {
        id: 'cpp-guessing-game',
        title: 'number guessing game in c++',
        nodeType: 'logic',
        language: 'cpp',
        baseline: `#include <iostream>
#include <cstdlib>
#include <ctime>

int main() {
    std::srand(std::time(nullptr));
    int secret = std::rand() % 100 + 1;
    int guess = 0;
    while (guess != secret) {
        std::cout << "Guess (1-100): ";
        std::cin >> guess;
        if (guess < secret) std::cout << "Higher\n";
        else if (guess > secret) std::cout << "Lower\n";
    }
    std::cout << "Correct!\n";
    return 0;
}`,
        improved: `#include <iostream>
#include <random>
#include <chrono>

int main() {
    unsigned seed = static_cast<unsigned>(
        std::chrono::steady_clock::now().time_since_epoch().count());
    std::mt19937 rng(seed);
    int secret = static_cast<int>(rng() % 100) + 1;
    for (int guess; std::cin >> guess;) {
        if (guess == secret) { std::cout << "Correct!\n"; return 0; }
        std::cout << (guess < secret ? "Higher\n" : "Lower\n");
    }
    return 0;
}`,
        lesson: 'Replace C `rand()`/`srand()` with the `<random>` engine seeded from a `<chrono>` clock, and fold the read/compare/print loop into one `for (int guess; std::cin >> guess;)`. The "read-until-EOF" idiom is reusable for any interactive CLI; standard library only, compiled with `-std=c++17`.',
    },
    {
        id: 'go-word-frequency',
        title: 'word frequency counter in go',
        nodeType: 'logic',
        language: 'go',
        baseline: `package main

import (
	"bufio"
	"fmt"
	"os"
)

func main() {
	counts := make(map[string]int)
	scanner := bufio.NewScanner(os.Stdin)
	for scanner.Scan() {
		word := scanner.Text()
		counts[word]++
	}
	for w, n := range counts {
		fmt.Println(w, n)
	}
}`,
        improved: `package main

import (
	"bufio"
	"fmt"
	"os"
	"sort"
	"strings"
)

func main() {
	counts := map[string]int{}
	sc := bufio.NewScanner(os.Stdin)
	for sc.Scan() {
		for _, w := range strings.Fields(sc.Text()) {
			counts[w]++
		}
	}
	words := make([]string, 0, len(counts))
	for w := range counts {
		words = append(words, w)
	}
	sort.Slice(words, func(i, j int) bool { return counts[words[i]] > counts[words[j]] })
	for _, w := range words {
		fmt.Println(w, counts[w])
	}
}`,
        lesson: 'Tokenize each line with strings.Fields into a map accumulator, then order the keys once at the end. The "count into a map, then sort its keys" shape is the universal frequency/grouping pattern — standard library only.',
    },
    {
        id: 'python-palindrome',
        title: 'palindrome checker in python',
        nodeType: 'logic',
        language: 'python',
        baseline: `def is_palindrome(s):
    rev = ''
    for ch in s:
        rev = ch + rev
    if rev == s:
        return True
    else:
        return False

word = input('Word: ')
if is_palindrome(word):
    print('yes')
else:
    print('no')`,
        improved: `import re

def is_palindrome(s):
    t = re.sub(r'[^a-z0-9]', '', s.lower())
    return t == t[::-1]

word = input('Word: ')
print('yes' if is_palindrome(word) else 'no')`,
        lesson: 'Normalize once with one regex and compare the string to its slice-reverse. The "normalize, then compare to reversed" shape is the universal palindrome/anagram test — no manual loop.',
    },
    {
        id: 'c-dice-roller',
        title: 'dice roller in c',
        nodeType: 'logic',
        language: 'c',
        baseline: `#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int total = 0;
    int i;
    srand(1);
    for (i = 0; i < 5; i++) {
        total += rand() % 6 + 1;
    }
    printf("Total: %d", total);
    return 0;
}`,
        improved: `#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 5;
    int total = 0;
    srand((unsigned)time(NULL));
    while (n-- > 0) total += rand() % 6 + 1;
    printf("Total: %d", total);
    return 0;
}`,
        lesson: 'Seed once from time(NULL), take the dice count as an argument, and accumulate in one loop instead of hardcoding the count. "Parameterize, then fold into one expression" is the reusable CLI shape; standard library only.',
    },
    {
        id: 'java-bank-account',
        title: 'bank account in java',
        nodeType: 'logic',
        language: 'java',
        baseline: `import java.util.HashMap;
import java.util.Map;

public class Bank {
    static Map<String, Integer> balances = new HashMap<>();

    public static void main(String[] args) {
        balances.put("alice", 100);
        balances.put("bob", 50);
        System.out.println("alice: " + balances.get("alice"));
        System.out.println("bob: " + balances.get("bob"));
    }
}`,
        improved: `import java.util.HashMap;
import java.util.Map;

public class Bank {
    public static void main(String[] args) {
        Map<String, Integer> balances = new HashMap<>(Map.of("alice", 100, "bob", 50));
        balances.forEach((name, cents) -> System.out.println(name + ": " + cents));
    }
}`,
        lesson: 'Build the state with Map.of(...) and emit it with forEach instead of one print per entry. "Declare the data, then iterate" removes duplicated lines and is the universal reporting shape. Read stdin with Scanner — never System.console().',
    },
    {
        id: 'csharp-todo',
        title: 'todo list in c#',
        nodeType: 'logic',
        language: 'csharp',
        baseline: `using System;
using System.Collections.Generic;

class Program
{
    static void Main()
    {
        var todos = new List<string>();
        todos.Add("buy milk");
        todos.Add("walk dog");
        foreach (var t in todos)
        {
            Console.WriteLine(t);
        }
    }
}`,
        improved: `using System;
using System.Linq;

class Program
{
    static void Main(string[] args)
    {
        var todos = args.Length > 0 ? args : new[] { "buy milk", "walk dog" };
        Console.WriteLine(string.Join(", ", todos.Select((t, i) => (i + 1) + ". " + t)));
    }
}`,
        lesson: 'Seed the list from args with a sample fallback, then format the whole collection in one LINQ projection plus string.Join. "Project, then join" replaces a manual print loop and works for any list rendering.',
    },
    {
        id: 'kotlin-temp-stats',
        title: 'temperature stats in kotlin',
        nodeType: 'logic',
        language: 'kotlin',
        baseline: `fun main() {
    val temps = listOf(20.0, 21.5, 19.0)
    var sum = 0.0
    for (t in temps) {
        sum += t
    }
    println("Average: " + (sum / temps.size))
}`,
        improved: `fun main() {
    val temps = listOf(20.0, 21.5, 19.0)
    println("Average: " + "%.2f".format(temps.average()) + " min=" + temps.min() + " max=" + temps.max())
}`,
        lesson: 'Use the collection aggregates (average/min/max) instead of a hand-rolled accumulator. The standard-library statistical operators are the universal reduce shape and remove the loop and the manual divide.',
    },
    {
        id: 'swift-word-reverser',
        title: 'word reverser in swift',
        nodeType: 'logic',
        language: 'swift',
        baseline: `let words = ["alpha", "beta", "gamma"]
var out: [String] = []
for w in words {
    var rev = ""
    for ch in w {
        rev = String(ch) + rev
    }
    out.append(rev)
}
for r in out {
    print(r)
}`,
        improved: `let words = ["alpha", "beta", "gamma"]
words.map { String($0.reversed()) }.forEach { print($0) }`,
        lesson: 'Map the transform over the collection and print in one pass — String.reversed() handles the reverse loop, and "map then forEach" is the universal transform-and-emit idiom.',
    },
    {
        id: 'php-csv',
        title: 'csv parser in php',
        nodeType: 'logic',
        language: 'php',
        baseline: `<?php
$lines = file('data.csv');
foreach ($lines as $line) {
    $fields = explode(',', $line);
    foreach ($fields as $f) {
        echo trim($f) . "|";
    }
    echo PHP_EOL;
}`,
        improved: `<?php
foreach (file('data.csv', FILE_IGNORE_NEW_LINES) as $line) {
    echo implode('|', array_map('trim', str_getcsv($line))), PHP_EOL;
}`,
        lesson: 'str_getcsv plus array_map(trim) plus implode turns each row into one expression. The "split, map, join" pipeline replaces nested loops and is the universal delimited-data shape.',
    },
    {
        id: 'ruby-anagram',
        title: 'anagram grouper in ruby',
        nodeType: 'logic',
        language: 'ruby',
        baseline: `words = %w[listen silent enlist google gooegl]
groups = []
words.each do |w|
  key = w.chars.sort.join
  found = groups.find { |g| g[:key] == key }
  if found
    found[:words] << w
  else
    groups << { key: key, words: [w] }
  end
end
groups.each { |g| puts g[:words].join(' ') }`,
        improved: `words = %w[listen silent enlist google gooegl]
words.group_by { |w| w.chars.sort.join }.each_value { |g| puts g.join(' ') }`,
        lesson: 'group_by(chars.sort.join) collapses the manual key lookup into one call. The "derive a canonical key, then group" shape is the universal bucketing pattern (anagrams, dedupe, clustering).',
    },
];
// ─── Matching + prompt building ───────────────────────────────────────────
/** Normalize for fuzzy matching: lowercase, hyphens/underscores → spaces, collapse gaps. */
function normForMatch(s) {
    return (s || '').toLowerCase().replace(/[-_]/g, ' ').replace(/\s+/g, ' ').trim();
}
/** Match a purpose string to the closest reference (by substring, then node type). */
export function matchReference(purpose, nodeType) {
    const p = normForMatch(purpose);
    if (p) {
        const byText = MICRO_BUILD_REFERENCES.find(r => p.includes(normForMatch(r.title)));
        if (byText)
            return byText;
    }
    if (nodeType) {
        const byType = MICRO_BUILD_REFERENCES.find(r => r.nodeType === nodeType);
        if (byType)
            return byType;
    }
    return MICRO_BUILD_REFERENCES[0] || null;
}
/** Build a compact, injection-ready reference section for a purpose. */
export function buildReferenceSection(purpose, nodeType) {
    const ref = matchReference(purpose, nodeType);
    if (!ref)
        return '';
    return ('━━━ REFERENCE — EMULATE THIS STYLE ━━━\n' +
        'A similar micro-app was built plainly, then improved to be smaller, faster, and more universal. The winning version and the reusable pattern it demonstrates are below. Apply the LESSON to your rewrite — do not merely copy the code if your app differs.\n\n' +
        `LESSON: ${ref.lesson}\n` +
        `IMPROVED VERSION (${ref.id}):\n\`\`\`\n${ref.improved}\n\`\`\``);
}
export const MICRO_CATALOG = [
    { purpose: 'a simple password strength checker CLI program in typescript', nodeType: 'logic', language: 'typescript', refId: 'password-checker' },
    { purpose: 'a mini http server using only node built-ins in javascript', nodeType: 'api', language: 'javascript', refId: 'mini-server' },
    { purpose: 'a simple media player as a single-file browser app (index.html)', nodeType: 'ui', language: 'html', refId: 'simple-media-player' },
    { purpose: 'a minimal todo list CLI app in typescript', nodeType: 'logic', language: 'typescript', refId: 'todo-cli' },
    { purpose: 'a small markdown-to-html converter command line tool in typescript', nodeType: 'logic', language: 'typescript', refId: 'markdown-to-html' },
    { purpose: 'a temperature converter between celsius and fahrenheit as a single-file browser app (index.html)', nodeType: 'ui', language: 'html', refId: 'temp-converter' },
    { purpose: 'a simple stopwatch app as a single-file browser app (index.html)', nodeType: 'ui', language: 'html', refId: 'stopwatch' },
    { purpose: 'a character and word counter CLI program in typescript', nodeType: 'logic', language: 'typescript', refId: 'word-counter' },
    { purpose: 'a tiny in-memory notes app with add/list/delete as a single-file browser app (index.html)', nodeType: 'ui', language: 'html', refId: 'notes-app' },
    { purpose: 'a small quiz app with hardcoded questions as a single-file browser app (index.html)', nodeType: 'ui', language: 'html', refId: 'quiz-app' },
    { purpose: 'a word counter in rust CLI program', nodeType: 'logic', language: 'rust', refId: 'rust-word-counter' },
    { purpose: 'a number guessing game in c++ CLI program', nodeType: 'logic', language: 'cpp', refId: 'cpp-guessing-game' },
    { purpose: 'a word frequency counter in go CLI program', nodeType: 'logic', language: 'go', refId: 'go-word-frequency' },
    { purpose: 'a palindrome checker in python CLI program', nodeType: 'logic', language: 'python', refId: 'python-palindrome' },
    { purpose: 'a dice roller in c CLI program', nodeType: 'logic', language: 'c', refId: 'c-dice-roller' },
    { purpose: 'a bank account in java CLI program', nodeType: 'logic', language: 'java', refId: 'java-bank-account' },
    { purpose: 'a todo list in c# CLI program', nodeType: 'logic', language: 'csharp', refId: 'csharp-todo' },
    { purpose: 'a temperature stats in kotlin CLI program', nodeType: 'logic', language: 'kotlin', refId: 'kotlin-temp-stats' },
    { purpose: 'a word reverser in swift CLI program', nodeType: 'logic', language: 'swift', refId: 'swift-word-reverser' },
    { purpose: 'a csv parser in php CLI program', nodeType: 'logic', language: 'php', refId: 'php-csv' },
    { purpose: 'an anagram grouper in ruby CLI program', nodeType: 'logic', language: 'ruby', refId: 'ruby-anagram' },
];
