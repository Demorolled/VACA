#!/usr/bin/env python3
"""
=============================================================================
  ROUND-8 CODE DISTILLATION DATASET — qwen3.6:27b → Qwen2.5-7B
  =====================================================================
  Teacher : qwen3.6:27b-q4_K_M (17 GB Q4_K_M, spans both RTX 3060s) via Ollama
  Student : Qwen2.5-7B-Instruct-Uncensored (VACA's tuned LLM on dspark :8000)

  Distills TIGHT code question→answer pairs — codegen, algorithms, debugging,
  code review, refactoring, explanations, architecture, API usage, SQL, shell,
  regex, and web tasks — as {instruction, input, output} JSONL rows for the
  VACA training pipeline (Qwen chat template, assistant-only masking).

  EVERY answer is tight by construction: the teacher is instructed to reply
  with a ```lang code block plus at most 1-2 short sentences, zero preamble,
  zero meta-commentary; a Python gate then rejects fluff, echoes, reasoning
  dumps, and turn labels, and code-required registers must contain a fence.

  Usage:
    python3 scripts/build-round8-code-dataset.py --seed-rows 30        # validate
    python3 scripts/build-round8-code-dataset.py --max-bytes 10000000  # ~10 MB target
    python3 scripts/build-round8-code-dataset.py --max-bytes 10000000 --samples 4 \
        --concurrency 2 --registers codegen,algo,sql

  Resume: safe to re-run — prompt hashes are checkpointed and skipped; rows
  are appended incrementally so progress survives crashes / reboots.
=============================================================================
"""
import argparse
import hashlib
import json
import os
import random
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'training', 'dataset', 'round8-code.jsonl')
STATS = os.path.join(ROOT, 'training', 'dataset', 'round8-stats.json')
CHECKPOINT = os.path.join(ROOT, 'training', 'dataset', 'round8-done-hashes.json')
DEFAULT_TEACHER = 'qwen3.6:27b-q4_K_M'
DEFAULT_BASE = 'http://127.0.0.1:11434'

random.seed(2026)


# ─── Teacher call — qwen3.6 is a REASONING model: think MUST be false ──────
# (Verified: /v1/chat/completions ignores think:false and returns empty
#  content; native /api/chat with think:false returns clean tight answers.)

def teacher_reply(messages, model, base_url, temperature=0.7, max_tokens=800,
                  timeout=240):
    body = json.dumps({
        'model': model,
        'messages': messages,
        'think': False,
        'stream': False,
        'options': {
            'temperature': temperature,
            'num_predict': max_tokens,
            # num_ctx 8192 wedges llama-server on the dual-RTX3060 rig
            # (runner pegs CPU, never responds — verified twice). 4096 is
            # plenty for these tight Q&A prompts.
            'num_ctx': 4096,
        },
    }).encode()
    req = urllib.request.Request(
        base_url + '/api/chat', data=body,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return (data.get('message', {}).get('content') or '').strip()


# ─── Gates — tightness + safety ────────────────────────────────────────────

FLUFF_OPENERS = [
    r"^(sure|certainly|absolutely|of course|no problem|here'?s|here is|"
    r"here you go|i'?d be happy to|let me|ok(?:ay)?[,!.:\s]+|yes[,!.:\s]+|"
    r"great question|good question|sounds good|my pleasure|happy to)[,!\s:]",
    r"^(as an ai|as a language model)", r"^i cannot ", r"^i'?m sorry",
    r"^here is (the|your|a) (code|function|answer)", r"^this (code|snippet|"
    r"function) (does|is|will)", r"^the (code|answer|function)",
]
FLUFF_ANYWHERE = [
    r"i see you'?re typing", r"static file", r"\[REASONING",
    r"chain-?of-?thought", r"^Bot\s*:", r"^User\s*:", r"^Assistant\s*:",
    r"assistant'?s reply", r"training data", r"as a large language model",
    r"\[think\]", r"\[/think\]", r"<thinking>", r"</thinking>",
]
CODE_FENCE = re.compile(r"```[a-zA-Z0-9+#.-]*\s*\n")


def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def clean_and_validate(instruction, reply, register, require_code):
    """Return the cleaned output or None if the row fails any gate."""
    t = (reply or '').strip()
    if len(t) < 12:
        return None
    if any(re.search(p, t, re.I) for p in FLUFF_ANYWHERE):
        return None
    if any(re.match(p, t, re.I) for p in FLUFF_OPENERS):
        return None
    # code-required registers must contain a fenced code block
    if require_code and not CODE_FENCE.search(t):
        return None
    # verbatim echo of the instruction
    tn = norm(t)
    i = norm(instruction)
    if i and (tn == i or tn.startswith(i[:30]) or i.startswith(tn[:30])):
        return None
    if len(t) > 1800:
        # Only truncate at a fence-safe boundary — never split an open ```
        head = t[:1800].rsplit(' ', 1)[0]
        if head.count('```') % 2 == 1:  # an open fence got cut
            head = head.rsplit('```', 1)[0] + '```'
        t = head
    return t


# ─── Teacher prompt ─────────────────────────────────────────────────────────

TEACHER_SYSTEM = (
    "You are a world-class senior software engineer producing training data "
    "for a code-focused fine-tune of a small assistant. You will be given a "
    "user question about code. Write ONE tight, correct answer:\n"
    "- If code is requested, give the complete code in a single ```lang code "
    "block (no placeholder comments, no ellipses).\n"
    "- At most 1-2 short sentences of explanation; prefer none when the code "
    "is self-explanatory.\n"
    "- ZERO preamble: never open with 'Sure!', 'Here's how', 'Of course', "
    "'Let me', 'Good question', or any filler. Answer starts with the code or "
    "the answer itself.\n"
    "- Never echo or restate the user's question. Never add meta-commentary, "
    "'As an AI', or analysis headers.\n"
    "- Be idiomatic for the language, use modern best practices, keep it SHORT."
)

PLANNING_SYSTEM = (
    "You are a world-class senior software architect producing training data "
    "for a fine-tune that must LEARN HOW TO PLAN an app build from scratch. "
    "You will be given an app idea. Write ONE tight, concrete start-to-end "
    "build walkthrough:\n"
    "- Structure it in short labeled stages: 1) Scope, 2) Architecture, "
    "3) File structure (a compact fenced tree), 4) Build order, 5) Verify.\n"
    "- Be specific, not generic: name the actual modules, files, and the order "
    "you would implement and test them. No fluff, no filler sentences.\n"
    "- ZERO preamble: never open with 'Sure!', 'Here's how', or similar. Start "
    "directly with the plan.\n"
    "- Never echo the user's question. Never add meta-commentary, 'As an AI', "
    "or analysis headers.\n"
    "- The whole plan must be SHORT and scannable — this trains planning skill, "
    "not essay-writing."
)


def build_teacher_messages(question, register, lang):
    ctx = ''
    if lang:
        ctx = f' (language: {lang})'
    system = PLANNING_SYSTEM if register == 'planning' else TEACHER_SYSTEM
    return [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': f'[{register}{ctx}]\n{question}'},
    ]


# ─── Scenario catalog — tight code Q&A across 12 registers ─────────────────

LANGS = ['python', 'javascript', 'typescript', 'go', 'java', 'bash', 'ruby', 'rust',
         'c', 'cpp', 'csharp', 'php', 'swift', 'kotlin']

CODEGEN_TASKS = [
    "parse a JSON string and return an object",
    "read a file line by line and print lines containing a substring",
    "capitalize the first letter of every word in a sentence",
    "find all unique elements of a list while preserving order",
    "retry an async operation with exponential backoff and max attempts",
    "debounce a function so it fires only after a quiet period",
    "throttle a function to at most one call per interval",
    "deep-merge two objects without mutating the inputs",
    "flatten a nested list one level deep",
    "chunk a list into groups of size n",
    "convert a snake_case string to camelCase",
    "compute a running average over a stream of numbers",
    "validate an email address with a simple regex",
    "generate a random password of a given length",
    "memoize an expensive pure function",
    "implement a minimal LRU cache with get and put",
    "return the intersection of two lists",
    "group a list of objects by a given key",
    "implement a minimal event emitter with on/emit/off",
    "deep-clone an object without using JSON serialization",
    "paginate a large list into pages of size n",
    "rate-limit async calls to at most n per second",
    "sort a list of objects by a nested key",
    "download a file with retries and a timeout",
    "map an array to an object keyed by id",
    "split a string on commas, trimming whitespace and skipping empties",
    "find the first duplicate in a list, or None",
    "implement a simple pub/sub that supports wildcard topics",
    "convert bytes to a human-readable size string (KB/MB/GB)",
    "round a number to 2 decimals without string tricks",
    "extract all URLs from a text block with a regex",
    "implement a tiny template renderer that replaces {placeholders}",
    "queue async tasks so at most n run concurrently",
    "detect if a string is a valid IPv4 address",
    "build a frequency counter and return the top k items",
    "implement a simple state machine with allowed transitions",
    "rebalance-independently reverse a linked list",
    "implement a ring buffer with fixed capacity",
    "generate all permutations of a small list",
    "fuzzy-match two strings using Levenshtein distance",
]

ALGO_TASKS = [
    "binary search over a sorted array",
    "merge sort",
    "quicksort with in-place partitioning",
    "breadth-first search on a graph",
    "depth-first search on a graph",
    "Dijkstra's shortest path",
    "two-sum (find indices of two numbers adding to a target)",
    "longest common subsequence of two strings",
    "edit distance between two strings",
    "iterative Fibonacci",
    "iterative factorial",
    "sieve of Eratosthenes for primes up to n",
    "check if a string is a palindrome (ignore case and spaces)",
    "reverse a singly linked list iteratively",
    "in-order traversal of a binary tree",
    "Kadane's algorithm for maximum subarray sum",
    "topological sort of a DAG",
    "union-find with path compression and union by rank",
    "0/1 knapsack",
    "binary tree level-order traversal",
    "validate a binary search tree",
    "find the kth largest element with a heap",
]

EXPLAIN_CONCEPTS = [
    "closures", "hoisting", "promises", "async/await", "generators",
    "recursion", "memoization", "time complexity", "Big-O notation",
    "hash maps vs arrays", "linked lists", "stack vs queue",
    "binary search trees", "database indexes", "transactions and ACID",
    "SQL joins", "pass by reference vs pass by value", "immutability",
    "pure functions", "the event loop", "garbage collection", "deadlocks",
    "race conditions", "idempotency", "REST vs RPC", "callbacks",
    "dependency injection", "the observer pattern", "the factory pattern",
    "content negotiation", "connection pooling", "lazy loading",
]

ARCH_TASKS = [
    "a REST API for a todo app",
    "a realtime chat backend",
    "an e-commerce checkout flow",
    "a URL shortener service",
    "a rate limiter service",
    "an image upload service",
    "a job queue for background work",
    "a notification system (email + push)",
    "a search autocomplete endpoint",
    "a multi-tenant SaaS database schema",
    "an offline-first mobile sync layer",
    "a websocket game server",
    "a cron-driven ETL pipeline",
    "a feature-flag system",
    "JWT vs session-based auth",
    "a structured logging pipeline",
    "an event-driven microservice",
    "a file storage abstraction",
    "a caching layer in front of a database",
    "a webhook handler for payments",
    "a realtime leaderboard",
    "a pub/sub fan-out for analytics events",
    "a config service with env overrides",
    "a health-check and metrics endpoint",
    "a background email sender with retries",
]

API_TASKS = [
    "make an HTTP GET request and parse the JSON response",
    "POST JSON to an endpoint with headers",
    "read a file and handle a missing-file error",
    "write a file atomically",
    "set a timer that runs a callback after 1 second",
    "read an environment variable with a default",
    "list files in a directory recursively",
    "copy a file",
    "create a temporary directory",
    "spawn a child process and capture its output",
    "hash a password securely",
    "generate a UUID",
    "connect to SQLite and run a parameterized query",
    "stream a large file without loading it into memory",
    "handle SIGINT gracefully and clean up",
    "read stdin line by line",
    "log with levels and structured fields",
    "compress a string with gzip",
    "base64-encode and decode a string",
    "escape HTML from user input",
    "detect the operating system",
    "get the current timestamp in ISO 8601",
    "retry a flaky function with backoff",
    "parse command-line flags",
    "watch a file for changes",
    "implement a simple HTTP server that returns JSON",
    "run an async task with a timeout that cancels it",
    "interpolate variables into a string safely",
    "compare two timestamps and compute a duration",
    "paginate through an API that uses a cursor",
]

SQL_TASKS = [
    "find duplicate emails in a users table",
    "get the top 3 most recent orders per customer",
    "join orders and customers, showing all customers even without orders",
    "count rows per category and filter to categories with more than 5",
    "find the second-highest salary without LIMIT 1 OFFSET 1",
    "delete duplicate rows keeping the one with the smallest id",
    "select rows created in the last 7 days",
    "compute a rolling 7-day average of daily sales",
    "find employees who earn more than their manager (self join)",
    "rank products by sales within each category (window function)",
    "get customers with no orders (anti-join)",
    "pivot monthly revenue from rows to columns",
    "return the difference between two dates in days",
    "use a CTE to compute a cumulative sum",
    "upsert a row (insert or update on conflict)",
    "paginate a large table with keyset (where id > ?) pagination",
    "extract a nested value from a JSON column",
    "concatenate a group of strings with a separator",
    "find the longest-running sessions using a window function",
    "use EXISTS instead of IN for a correlated subquery",
    "escape a LIKE pattern that contains user-supplied % characters",
    "lock a row for update inside a transaction",
    "find overlapping time ranges for bookings",
    "compute median without a MEDIAN function",
    "select the most common value per group",
    "join three tables to produce a report",
    "check for orphaned rows and clean them up",
    "find rows that appear in one table but not another",
    "optimize a slow query with an index hint",
    "normalize a denormalized table into related tables",
]

SHELL_TASKS = [
    "find the 10 largest files in a directory tree",
    "kill the process listening on port 3000",
    "rename all .txt files to .md",
    "extract a tar.gz archive to a directory",
    "sync a directory with rsync over ssh",
    "show disk usage per top-level directory, sorted",
    "search command history for a command",
    "undo the last git commit but keep the changes",
    "squash the last 3 git commits into one",
    "show a diff of only staged files",
    "make all .sh files executable recursively",
    "replace 'foo' with 'bar' in all files under a dir (sed)",
    "print the second column of a CSV with awk",
    "count unique occurrences of a word in a file",
    "check if a port is open on a host",
    "run a command in the background and log to a file (nohup)",
    "loop over all .json files and print their sizes",
    "parse a JSON API response with jq",
    "make a curl request with a header and save the body",
    "resume an interrupted download with curl",
    "create a symlink",
    "tail -f a log and filter for ERROR lines",
    "find and delete files older than 30 days",
    "run a command every 2 seconds and watch the output",
    "tar a directory excluding node_modules",
    "open an ssh tunnel to a remote database",
    "copy a directory over ssh with scp",
    "add a cron job that runs a script daily at 3am",
    "git log one-line summaries with author and date",
    "show what changed in the last commit, stats only",
]

REGEX_TASKS = [
    "match email addresses",
    "match http(s) URLs",
    "match hex color codes (#fff or #ffffff)",
    "match ISO 8601 dates",
    "match US phone numbers in several formats",
    "match IPv4 addresses",
    "match valid usernames (alphanumeric + underscore, 3-16 chars)",
    "match a strong password (8+, upper, lower, digit, symbol)",
    "convert text to a URL-safe slug",
    "extract a YouTube video id from a URL",
    "match Twitter handles",
    "match hashtags in text",
    "match prices like $12.50",
    "match 24-hour times HH:MM",
    "match US zip codes",
    "match HTML tags",
    "match a UUID",
    "match semantic version strings",
    "match a file extension at the end of a filename",
    "find trailing whitespace at line ends",
    "find duplicate consecutive words",
    "extract all numbers (int and float) from text",
    "match a quoted string allowing escaped quotes",
    "match a markdown link [text](url)",
    "match credit-card-like numbers",
    "split a camelCase identifier into words",
]

WEB_TASKS = [
    "center a div both horizontally and vertically",
    "make a sticky header that stays on top",
    "build a responsive grid that collapses on mobile",
    "implement a dark-mode toggle that persists",
    "build an accessible modal dialog with focus trap",
    "build an accordion with smooth expand/collapse",
    "build tabs with keyboard navigation",
    "show a toast notification",
    "make a CSS-only spinner",
    "validate a form and show inline errors",
    "build a debounced live-search input",
    "implement infinite scroll",
    "implement drag-and-drop reordering",
    "build a simple image carousel",
    "make a progress bar that fills on scroll",
    "build a tooltip on hover with pure CSS",
    "make a hamburger menu for mobile",
    "implement a countdown timer",
    "show a typing indicator while waiting",
    "lazy-load images as they scroll into view",
    "make a video autoplay muted with a play overlay",
    "respect prefers-reduced-motion",
    "use CSS custom properties for a theme",
    "build breadcrumbs",
    "make a badge component",
    "build a skeleton loader",
    "make a card that lifts on hover",
    "build a two-column layout with sidebar",
    "implement a color picker input",
    "make text truncate with an ellipsis",
]

DEBUG_TASKS = [
    ("why does this throw? ", "for i in range(len(lst)):\n    print(lst[i+1])"),
    ("why does this always return True? ", "def is_even(n):\n    return n % 2 == 1"),
    ("why does this hang? ", "def recurse():\n    return recurse()"),
    ("why is this never cached? ", "import random\ndef get():\n    if 'x' in cache:\n        return cache['x']\n    cache['x'] = random.random()\n    return cache['x']"),
    ("why does this leak? ", "const el = document.getElementById('a');\nel.addEventListener('click', () => console.log(el));"),
    ("why does this fail with EADDRINUSE? ", "http.createServer(h).listen(3000);\nhttp.createServer(h).listen(3000);"),
    ("why does this print NaN? ", "console.log('5' + 3 - 2);"),
    ("why is this an infinite loop? ", "let i = 0;\nwhile (i < 10) {\n  console.log(i);\n}"),
    ("why does this return the same object? ", "function make() {\n  const obj = {};\n  return obj;\n}\nconst a = make();\na.x = 1;\nconst b = make();\nconsole.log(b.x);"),
    ("why does this race? ", "fetch(url).then(r => r.json()).then(d => render(d));\nfetch(url2).then(r => r.json()).then(d => render(d));"),
    ("why does this not await? ", "async function main() {\n  fetchData();\n  console.log('done');\n}"),
    ("why does this segfault? ", "char *p = malloc(10);\nfree(p);\nfree(p);"),
    ("why does this mutate the default? ", "def add(item, items=[]):\n    items.append(item)\n    return items"),
    ("why is this slow? ", "for i in range(len(users)):\n    for j in range(len(orders)):\n        if users[i].id == orders[j].user_id: ..."),
    ("why does this return 0.30000000000000004? ", "console.log(0.1 + 0.2);"),
    ("why does this throw ReferenceError? ", "console.log(x);\nlet x = 5;"),
    ("why does this not update? ", "function set() {\n  let count = 0;\n  const inc = () => { count += 1; };\n  inc();\n  return count;\n}"),
    ("why does this give wrong day? ", "const d = new Date('2026-08-08');\nconsole.log(d.getDate());"),
    ("why is this unbounded? ", "db.get('users', (err, users) => {\n  users.forEach(u => db.update(u, () => {}));\n});"),
    ("why does this throw on the second call? ", "const fs = require('fs');\nconst s = fs.createReadStream('a.txt');\ns.on('end', () => console.log('done'));\ns.close();\ns.resume();"),
]

REVIEW_TASKS = [
    ("what's wrong with this? ", "const SECRET = 'sk-live-1234567890abcdef';\nfunction pay(amount) {\n  return fetch('/api/pay', { body: JSON.stringify({ secret: SECRET, amount }) });\n}"),
    ("what's wrong with this? ", "const users = await db.query('SELECT * FROM users WHERE name = \"' + name + '\"');"),
    ("what's wrong with this? ", "function process(items) {\n  items.forEach(item => fs.writeFileSync(item.file, item.data));\n}"),
    ("what's wrong with this? ", "app.get('/user/:id', (req, res) => {\n  const id = parseInt(req.params.id);\n  const user = users.find(u => u.id === id);\n  res.json(user);\n});"),
    ("what's wrong with this? ", "function val(x) { return eval('(' + x + ')'); }"),
    ("what's wrong with this? ", "function render(html) {\n  document.body.innerHTML = html;\n}"),
    ("what's wrong with this? ", "let count = 0;\nfunction inc() { count += 1; }\nexports.inc = inc;\nexports.get = () => count;"),
    ("what's wrong with this? ", "if (user.role == 'admin' || user.role == 'owner') grantAccess();"),
    ("what's wrong with this? ", "router.get('/x', async (req, res) => {\n  const data = await fetchData(req.query.id);\n  res.json(data);\n});\n// no try/catch anywhere"),
    ("what's wrong with this? ", "const price = { value: 19.99, currency: 'USD' };\nmodule.exports = price;"),
    ("what's wrong with this? ", "function wait(ms) { return new Promise(r => setTimeout(r, ms)); }\nwait(1000).then(() => console.log('a'));\nwait(1000).then(() => console.log('b'));"),
    ("what's wrong with this? ", "exports.handler = async () => {\n  const conn = await pool.getConnection();\n  await conn.query('UPDATE ...');\n  conn.release();\n};"),
]

REFACTOR_TASKS = [
    ("refactor this to be cleaner: ", "function f(a, b, c) {\n  if (a) {\n    if (b) return c ? 1 : 2;\n    return 3;\n  }\n  return 4;\n}"),
    ("refactor this to remove duplication: ", "function morning() { alert('Hello'); log('greeted'); }\nfunction evening() { alert('Hello'); log('greeted'); }"),
    ("refactor this with guard clauses: ", "function calc(x) {\n  if (x !== null) {\n    if (x > 0) {\n      return x * 2;\n    }\n    return 0;\n  }\n  return 0;\n}"),
    ("refactor this to use built-ins: ", "function unique(arr) {\n  const out = [];\n  for (let i = 0; i < arr.length; i++) {\n    if (out.indexOf(arr[i]) === -1) out.push(arr[i]);\n  }\n  return out;\n}"),
    ("refactor this to remove magic numbers: ", "if (status === 404) render('nf'); else if (status === 500) render('err');"),
    ("refactor this to inject the dependency: ", "class Mailer {\n  send(msg) { return transport.send(msg); }\n}"),
    ("refactor this into small functions: ", "function run() {\n  const rows = db.fetch('all');\n  const valid = rows.filter(r => r.age >= 18);\n  const names = valid.map(r => r.name);\n  names.forEach(n => console.log(n));\n}"),
    ("refactor this async code to avoid nesting: ", "getUser(id).then(user => {\n  getPosts(user).then(posts => {\n    getComments(posts[0]).then(c => console.log(c));\n  });\n});"),
    ("refactor this switch to an object map: ", "function cmd(k) {\n  switch (k) {\n    case 'add': return add();\n    case 'del': return del();\n    default: return noop();\n  }\n}"),
    ("refactor this to add types: ", "function greet(name) { return 'Hello ' + name.toUpperCase(); }"),
    ("refactor this to avoid mutation: ", "let items = [1, 2, 3];\nitems.push(4);\nitems.sort();\nreturn items;"),
    ("refactor this to extract a helper: ", "function report(users) {\n  let total = 0;\n  for (const u of users) total += u.salary;\n  const avg = total / users.length;\n  console.log('avg', avg);\n}"),
]


# ─── Catalog expansion — extra tasks + 6 new registers ────────────────────

EXTRA_CODEGEN = [
    "convert a list of pairs to a dictionary",
    "count words in a string, case-insensitive",
    "shuffle a list deterministically with a seed",
    "compute the median of a list without sorting it in place",
    "parse a CSV line handling quoted fields",
    "generate all subsets of a list",
    "check whether two strings are anagrams",
    "implement a simple regex-like glob matcher",
    "serialize an object to a compact JSON string",
    "format a number with thousands separators",
    "zip two lists into a dict, dropping extras",
    "interleave two lists element-wise",
    "find the index of the first vowel in a string",
    "rotate a matrix 90 degrees",
    "compute the mode of a list of numbers",
    "build a frequency map and sort it by count",
    "extract the domain from a URL",
    "truncate a string to n chars and add an ellipsis",
    "convert a unix timestamp to a readable date",
    "implement a sliding-window max function",
    "flatten a dict of nested dicts into dotted keys",
    "find pairs in a list that sum to a target",
    "remove falsy values from an array",
    "merge two sorted lists into one sorted list",
    "implement a function that returns a random element, weighted",
    "check if a list is strictly increasing",
    "convert a number to words (0-999)",
    "compute the GCD of two numbers iteratively",
    "find the longest word in a sentence",
    "implement a FIFO queue with two stacks",
    "count islands in a binary grid (DFS flood fill)",
    "validate parentheses balance in a string",
    "implement atoi without built-in parsing",
    "find the longest substring without repeating characters",
    "compute the dot product of two vectors",
]

EXTRA_ALGO = [
    "merge k sorted lists with a heap",
    "find the diameter of a binary tree",
    "implement a trie with insert/search/prefix",
    "sort a nearly-sorted array efficiently",
    "find all connected components in a graph",
    "implement min-heap operations from scratch",
    "compute the number of ways to climb stairs (DP)",
    "find the longest palindromic substring",
    "implement Rabin-Karp string matching",
    "detect a cycle in a linked list (Floyd's)",
    "compute matrix exponentiation for fast Fibonacci",
    "implement a segment tree for range sums",
]

EXTRA_EXPLAIN = [
    "tail recursion", "memoization vs caching", "the SOLID principles",
    "shallow vs deep copy", "synchronous vs asynchronous I/O",
    "strong vs weak typing", "the factory method pattern", "the proxy pattern",
    "the singleton pattern and its problems", "microservices vs monoliths",
    "horizontal vs vertical scaling", "ACID vs BASE", "SQL vs NoSQL",
    "indexed vs sequential scan", "the CAP theorem", "event sourcing",
    "webhooks vs polling", "HTTPS and TLS handshake", "DNS resolution",
    "CDNs and caching layers", "the Observer pattern", "the Strategy pattern",
    "the Adapter pattern", "the Decorator pattern", "the Command pattern",
    "the State pattern", "the Builder pattern", "the Template Method pattern",
    "the Visitor pattern", "the Iterator pattern", "the Composite pattern",
    "the Facade pattern", "the Flyweight pattern", "the Bridge pattern",
    "the Mediator pattern", "the Memento pattern", "the Prototype pattern",
    "the Interpreter pattern", "the Chain of Responsibility pattern",
    "the Null Object pattern", "the Specification pattern",
    "the Repository pattern", "the Unit of Work pattern",
    "dependency injection vs service locator", "immutability in functional code",
    "pure vs impure functions", "monads in simple terms",
    "lazy evaluation", "higher-order functions", "currying",
    "function composition", "recursion vs iteration tradeoffs",
    "tail call optimization", "symbolic vs dynamic linking",
    "AOT vs JIT compilation", "interpreters vs compilers",
    "garbage collection strategies", "reference counting vs tracing GC",
    "memory leaks in JS", "the call stack", "the heap vs the stack",
]

EXTRA_API = [
    "get the length of a string",
    "split a string into an array of characters",
    "join an array into a string with a separator",
    "sort an array descending",
    "reverse a string",
    "check if a string contains a substring (case-insensitive)",
    "get the last element of an array without mutating it",
    "remove duplicates from an array",
    "check if a key exists in a dictionary",
    "iterate over an object's entries",
    "read a JSON config file",
    "write a JSON file with pretty-printing",
    "get the current working directory",
    "sleep for 500 milliseconds",
    "parse a date string into a Date object",
    "format a date as YYYY-MM-DD",
    "generate a random integer in a range",
    "round a float to the nearest integer",
    "truncate a float to an int",
    "get the type of a variable",
    "check if a number is NaN",
    "convert a string to lowercase",
    "replace all occurrences of a substring",
    "split a path into directory and filename",
    "append text to a file",
    "check if a file exists",
    "list the environment variables",
    "set a timeout that fires once",
    "set an interval that fires repeatedly",
    "clear an interval by handle",
    "convert an object to a query string",
    "parse a query string into an object",
    "encode a URI component",
    "decode a URI component",
    "get a random element from an array",
    "compare two floats with an epsilon",
]

EXTRA_ARCH = [
    "a library (book) catalog API",
    "a fitness-tracking app backend",
    "a multiplayer Tic-Tac-Toe game server",
    "a blog platform with comments",
    "an inventory management system",
    "a ride-hailing dispatcher",
    "a food delivery ordering pipeline",
    "a music streaming playlist service",
    "a stock price ingestion pipeline",
    "a customer support ticketing system",
    "a chat moderation pipeline",
    "a document versioning system",
    "a file sync service like Dropbox-lite",
    "a recommendation feed service",
    "an analytics event pipeline",
    "a multi-currency payment ledger",
    "a booking system with availability checks",
    "a geolocation search (nearby places) service",
    "a notification digester that batches messages",
    "a web scraping scheduler",
]

EXTRA_SQL = [
    "get the row with the max value per group",
    "convert a column of strings to a comma-joined list",
    "count sessions per user per day",
    "find the most recent status per order",
    "calculate month-over-month growth of revenue",
    "select rows where a JSON field has a certain key",
    "find gaps in an auto-increment id sequence",
    "join a table to itself to pair consecutive rows",
    "find duplicated entries in a non-normalized table",
    "get the average order value per customer with at least 3 orders",
    "split a comma-separated column into rows",
    "return rows where a datetime column is in the current month",
    "find customers whose lifetime spend exceeds 1000",
    "update a table from a staging table with a join",
    "delete rows older than a year in batches",
    "select distinct combinations of two columns",
    "compute a running total per partition",
    "find the busiest hour of the day from a logs table",
    "retrieve a tree (category hierarchy) with a recursive CTE",
    "list tables and their row counts in a schema",
    "convert UTC timestamps to local time in a query",
    "find rows where a nullable column is set",
    "add a column with a default value (DDL)",
    "create an index for a slow query",
    "find overlapping subscriptions in a range",
    "compute the percentage share per category",
    "get the first row per group ordered by date",
    "find users with repeated failed logins",
    "compare today's sales vs yesterday's per store",
    "return the top contributor per project",
]

EXTRA_SHELL = [
    "count lines in a file",
    "print lines 10 through 20 of a file",
    "remove blank lines from a file",
    "sort lines by the second column numerically",
    "merge two files line-by-line",
    "find files containing a string and list them",
    "copy only new files with rsync",
    "monitor CPU and memory usage live",
    "show the top processes by memory",
    "find which process holds a file open (lsof)",
    "compress a folder into a zip",
    "unzip a zip file to a directory",
    "download a file with a user agent and retries",
    "extract the title of a webpage with curl+grep",
    "show listening ports with their processes",
    "change file extensions in bulk",
    "split a large file into 100 MB chunks",
    "compare two directories for missing files",
    "back up a database with pg_dump",
    "restore a database from a dump",
    "run a python script at login with cron",
    "git fetch + reset to origin for a branch",
    "git stash and re-apply with a message",
    "git cherry-pick a commit from another branch",
    "git log with a grep filter",
    "generate an SSH key without prompts",
    "test SSH connection to a host",
    "forward a remote port to localhost",
    "show IP addresses of all interfaces",
    "flush DNS cache",
]

EXTRA_REGEX = [
    "match a date in MM/DD/YYYY",
    "match a floating-point number with optional sign",
    "match a word boundary issue with hyphenated words",
    "match an IPv6 address",
    "match a MAC address",
    "extract the first sentence of text",
    "match a snake_case identifier",
    "match a kebab-case identifier",
    "match an alphanumeric string with spaces",
    "match a currency amount with commas",
    "match a timezone offset like +05:30",
    "match a filename with a specific prefix",
    "remove all punctuation from text",
    "match a newline-delimited list of emails",
    "match a hexadecimal number (0x...)",
    "match a single-quoted string",
    "match a backtick-quoted string",
    "match comments in code (// ...)",
    "match a SQL identifier with underscores",
    "match a domain name with TLD",
]

EXTRA_WEB = [
    "build a search bar with a clear button",
    "make an image that scales with its container",
    "build a sticky sidebar that doesn't overlap content",
    "implement a checkbox that shows/hides a password field",
    "build a star-rating widget",
    "make a button that copies text to clipboard",
    "build an auto-growing textarea",
    "implement a simple slider (range input with live value)",
    "build a responsive table that scrolls horizontally",
    "make a footer that sticks to the bottom",
    "build a print-friendly stylesheet toggle",
    "implement keyboard shortcuts for a modal (Esc closes)",
    "build a drag-to-resize split pane",
    "make a hover effect with a smooth transform",
    "build a notification badge on an icon",
    "implement a lightbox for images",
    "build a typewriter effect",
    "make a grid of cards that equalizes heights",
    "build a navbar that shrinks on scroll",
    "implement a custom select dropdown",
]

EXTRA_DEBUG = [
    ("why does this crash? ", "const x = null;\nconsole.log(x.name);"),
    ("why does this print twice? ", "btn.addEventListener('click', onClick);\nbtn.addEventListener('click', onClick);"),
    ("why does this return undefined? ", "function f() {\n  let x = 1;\n}\nconsole.log(f());"),
    ("why is this a memory leak? ", "setInterval(() => {\n  data.push(fetchChunk());\n}, 100);"),
    ("why does this throw OOM? ", "const arr = [];\nwhile (true) arr.push('x'.repeat(1e6));"),
    ("why does this not update the UI? ", "function inc() {\n  count += 1;\n  render();\n}\nrender = () => console.log(count);"),
    ("why does this give a wrong sum? ", "let sum = 0;\n[1, 2, 3].forEach(x => {\n  sum = +x;\n});\nconsole.log(sum);"),
    ("why does this time out? ", "app.get('/api', (req, res) => {\n  const big = heavyWork();\n  res.json(big);\n});"),
    ("why does this lose data? ", "const obj = {};\nfor (const k of keys) {\n  obj[k] = obj[k] + 1;\n}\n// keys contains duplicates"),
    ("why does this throw on empty input? ", "const first = items[0].name;\n// items is []"),
    ("why does this not match? ", "const re = /\\bword\\b/;\nre.test('word-word');"),
    ("why does this return false? ", "'2' === 2"),
    ("why does this corrupt the file? ", "fs.writeFileSync(path, data, 'utf8');\nfs.writeFileSync(path, more, 'utf8');"),
    ("why does this deadlock? ", "lock.acquire();\nwaitFor(lock2.acquire());\n// other thread waits for lock1"),
]

EXTRA_REVIEW = [
    ("what's wrong with this? ", "router.get('/items', (req, res) => {\n  const limit = req.query.limit;\n  return db.query('SELECT * FROM items LIMIT ' + limit);\n});"),
    ("what's wrong with this? ", "function save(user) {\n  localStorage.setItem('user', JSON.stringify(user));\n  sendToAnalytics(user.email);\n}"),
    ("what's wrong with this? ", "function upload(file) {\n  return fetch('/upload', { body: file });\n}"),
    ("what's wrong with this? ", "const secret = process.env.API_KEY;\nconsole.log('key:', secret);"),
    ("what's wrong with this? ", "async function run() {\n  await Promise.all(items.map(i => save(i)));\n  return 'done';\n}"),
    ("what's wrong with this? ", "function fmt(n) {\n  return n.toFixed(2);\n}\n// called with strings sometimes"),
    ("what's wrong with this? ", "while (true) {\n  const batch = readBatch();\n  if (!batch.length) break;\n}\n// no progress marker"),
    ("what's wrong with this? ", "exports.router = express.Router();\nrouter.use(cors());\nrouter.use(helmet());"),
    ("what's wrong with this? ", "function auth(req, res) {\n  const token = req.headers.authorization;\n  if (token) next();\n  else res.send(401);\n}"),
    ("what's wrong with this? ", "const data = JSON.parse(body);\n// body could be malformed"),
    ("what's wrong with this? ", "app.listen(3000, () => {});\n// process exits immediately in some environments"),
    ("what's wrong with this? ", "function hash(pw) {\n  return md5(pw + salt);\n}"),
    ("what's wrong with this? ", "const x = Math.random() * 100;\nif (x === 42) doThing();"),
]

EXTRA_REFACTOR = [
    ("refactor this to use a map: ", "function isEven(n) {\n  if (n % 2 === 0) return true;\n  return false;\n}"),
    ("refactor this to remove the flag param: ", "function run(flag) {\n  if (flag) fastPath();\n  else slowPath();\n}"),
    ("refactor this to use optional chaining: ", "const name = user && user.profile && user.profile.name;\nconsole.log(name);"),
    ("refactor this to avoid the temp: ", "const t = getPrice(item);\nreturn t > 100 ? t * 0.9 : t;"),
    ("refactor this with early returns: ", "function f(x) {\n  let r = 0;\n  if (x > 0) {\n    if (x < 10) {\n      r = x * 2;\n    } else {\n      r = 20;\n    }\n  }\n  return r;\n}"),
    ("refactor this to remove dead code: ", "function f() {\n  const a = 1;\n  const b = a + 2;\n  return a;\n}"),
    ("refactor this to use a constant: ", "if (status === 200) ok();\nif (status === 200) log();"),
    ("refactor this to reduce nesting: ", "items.forEach(i => {\n  if (i.active) {\n    if (i.valid) {\n      process(i);\n    }\n  }\n});"),
    ("refactor this with a helper: ", "const a = fmt(users[0]);\nconst b = fmt(users[1]);\nconst c = fmt(users[2]);"),
    ("refactor this to be testable: ", "function start() {\n  const port = process.env.PORT || 3000;\n  server.listen(port);\n}"),
    ("refactor this to avoid the boolean trap: ", "sendEmail(user, false);\nsendEmail(user, true);"),
    ("refactor this to use async/await: ", "getUser().then(u => getPosts(u).then(p => render(p)));"),
    ("refactor this to extract a pure function: ", "function process(data) {\n  const cleaned = data.map(x => x.trim().toLowerCase());\n  const sorted = [...cleaned].sort();\n  db.save(sorted);\n  return sorted;\n}"),
]

GIT_TASKS = [
    "undo the last commit but keep the changes staged",
    "amend the last commit message",
    "reset a file to its state in the last commit",
    "create a branch and switch to it in one command",
    "merge a branch while keeping history linear (rebase)",
    "abort a conflicted merge and start over",
    "list all branches with their last commit date",
    "delete a local branch and its remote",
    "stash only one file's changes",
    "show the diff of a specific commit",
    "search the commit history for a message",
    "find which commit introduced a line (git blame)",
    "revert a commit without rewriting history",
    "squash all commits in a feature branch into one",
    "fetch and rebase without checkout",
    "list changed files between two commits",
    "show files changed in the last commit",
    "remove a file from git tracking but keep it on disk",
    "rename a branch",
    "set the upstream branch for a new branch",
    "compare a branch to main for ahead/behind counts",
    "undo a git add",
    "see the full diff including untracked files",
    "clone a repo at a specific tag",
    "push a tag to remote",
    "list all tags sorted by version",
    "create a patch file from a commit",
    "apply a patch file",
    "checkout a file from another branch",
    "find large files bloating the repo history",
]

DOCKER_TASKS = [
    "build an image from a Dockerfile in the current dir",
    "run a container with a name and remove it on exit",
    "run a container with an env var and a port mapping",
    "mount a host directory as a volume",
    "list running containers",
    "list all containers including stopped ones",
    "stop and remove a container",
    "remove all stopped containers and dangling images",
    "exec a shell inside a running container",
    "copy a file out of a container",
    "view container logs and follow them",
    "inspect a container's environment",
    "tag an image for a registry",
    "push an image to a registry",
    "pull an image by digest",
    "run a one-off command with docker run --rm",
    "run a container with a healthcheck",
    "limit a container's memory and CPU",
    "build a multi-stage Dockerfile pattern",
    "use a named volume across containers",
    "create a custom docker network and attach containers",
    "run a postgres container with a database and user",
    "docker compose: start services in the background",
    "docker compose: rebuild one service and restart it",
    "docker compose: view logs for a single service",
    "docker compose: scale a service",
    "docker compose: stop and remove everything",
    "write a .dockerignore that excludes node_modules",
    "run a container in the host network",
    "clean up unused images and volumes (prune)",
]

TEST_TASKS = [
    "write a unit test for a function that adds two numbers",
    "write a unit test for a debounce function",
    "write a unit test for a function that parses CSV",
    "write a unit test for a retry-with-backoff helper",
    "write a test for an HTTP endpoint returning JSON",
    "write a test that mocks an external API call",
    "write a parameterized test for a formatter",
    "write a test for a class's edge cases (empty input, null)",
    "write a test for an LRU cache's eviction order",
    "write a test for a state machine's invalid transitions",
    "write a property-based test for a sort function",
    "write a test for a rate limiter under concurrency",
    "write a test for a function that handles timezones",
    "write a test for a file reader with a temp fixture",
    "write a test for a reducer/pure state update",
    "write a snapshot test for a render function",
    "write a test for graceful failure when a DB is down",
    "write a test that verifies no sensitive data is logged",
    "write a test for pagination edge cases",
    "write a test for a websocket message handler",
    "write a test for a rate-limited API client",
    "write a test for a function with floating-point rounding",
    "write a test for an auth middleware (valid/invalid token)",
    "write a test for a queue's ordering under load",
    "write a test for a config parser with missing keys",
    "write a test for a cache that expires entries",
    "write a test for a circular-dependency-free module loader",
    "write a test for idempotent retries (same result twice)",
    "write a test for a search function with unicode input",
    "write a test for a session store's expiry behavior",
]

SECURITY_TASKS = [
    "hash and verify a password safely",
    "sanitize user input to prevent SQL injection",
    "escape output to prevent XSS in HTML",
    "implement rate limiting on a login endpoint",
    "validate and normalize a file upload (type/size)",
    "protect an API route with an auth middleware",
    "sign and verify a JWT with an expiry",
    "store secrets in environment variables, not code",
    "implement CSRF protection for a form endpoint",
    "set secure HTTP headers (CSP, HSTS, X-Frame-Options)",
    "implement password strength rules",
    "use parameterized queries in a DB driver",
    "implement constant-time string comparison",
    "sanitize a URL before redirecting a user",
    "protect against path traversal in file downloads",
    "implement a simple allowlist validator for IPs",
    "encrypt data at rest with a proper cipher",
    "generate and validate a CSRF token",
    "avoid logging sensitive data",
    "implement an account lockout after failed logins",
    "validate JSON schema of an incoming payload",
    "implement content-type sniffing protections",
    "prevent clickjacking with frame ancestors",
    "securely compare hashes for password reset tokens",
    "implement a basic OAuth2 authorization-code flow",
    "set cookie flags (HttpOnly, Secure, SameSite)",
    "implement request signing for an API",
    "detect and block a simple brute-force pattern",
    "redact sensitive fields in logs",
    "validate redirect URLs against an allowlist",
]

DATA_TASKS = [
    "implement a singly linked list with push/pop/find",
    "implement a doubly linked list",
    "implement a binary search tree with insert/search/delete",
    "implement a stack with push/pop/peek",
    "implement a queue with enqueue/dequeue",
    "implement a priority queue using a heap",
    "implement a hash map with collision handling (chaining)",
    "implement a set with add/has/remove",
    "implement a deque with push/pop at both ends",
    "implement a circular linked list",
    "implement an adjacency list graph",
    "implement an adjacency matrix graph",
    "implement a weighted graph with Dijkstra",
    "implement a skip list",
    "implement a B-tree node structure",
    "implement an AVL tree with rotations",
    "implement a red-black tree invariants check",
    "implement a bloom filter",
    "implement a disjoint set (union-find)",
    "implement a trie for autocomplete",
    "implement a suffix array",
    "implement a Fenwick tree (BIT)",
    "implement a segment tree with lazy propagation",
    "implement a min-max heap (double-ended)",
    "implement a LRU cache with O(1) ops",
    "implement an LFU cache",
    "implement a linked-list-based stack",
    "implement a dynamic array with amortized growth",
    "implement a sparse table for range min queries",
    "implement a persistent (immutable) list",
]

HTTP_TASKS = [
    "explain the difference between GET and POST",
    "explain idempotency for PUT vs PATCH",
    "explain HTTP status codes 2xx/4xx/5xx with examples",
    "explain how a cookie is set and sent back",
    "explain CORS and how to fix a CORS error",
    "explain the request/response cycle with headers",
    "explain caching headers (Cache-Control, ETag)",
    "explain when to use 301 vs 302 vs 307 redirects",
    "explain content negotiation with Accept headers",
    "explain how to design a RESTful resource with nested routes",
    "explain the difference between JSON and form encoding",
    "explain a webhook and how to secure its endpoint",
    "explain HTTP/2 multiplexing in one sentence",
    "explain keep-alive connections",
    "explain how sessions work over HTTP (cookie+server store)",
    "explain the OPTIONS preflight request",
    "explain how to paginate a REST API with cursors",
    "explain error response conventions in REST APIs",
    "explain idempotency keys for payments",
    "explain how to version a REST API",
]

CODEGEN_TASKS += EXTRA_CODEGEN
ALGO_TASKS += EXTRA_ALGO
EXPLAIN_CONCEPTS += EXTRA_EXPLAIN
API_TASKS += EXTRA_API
ARCH_TASKS += EXTRA_ARCH
SQL_TASKS += EXTRA_SQL
SHELL_TASKS += EXTRA_SHELL
REGEX_TASKS += EXTRA_REGEX
WEB_TASKS += EXTRA_WEB
DEBUG_TASKS += EXTRA_DEBUG
REVIEW_TASKS += EXTRA_REVIEW
REFACTOR_TASKS += EXTRA_REFACTOR


PLANNING_APPS = [
    "desktop media player",
    "note-taking app with sync",
    "real-time chat application",
    "e-commerce storefront",
    "URL shortener service",
    "photo gallery web app",
    "task manager with reminders",
    "markdown blog engine",
    "file upload service with previews",
    "chess game against an AI",
    "music streaming backend",
    "expense tracker with charts",
    "multiplayer quiz game",
    "weather dashboard",
    "inventory management system",
    "code snippet manager",
    "habit tracker with streaks",
    "video editing tool (web)",
    "kanban board app",
    "calorie counter app",
    "terminal file manager (TUI)",
    "screenshot sharing service",
    "RSS reader",
    "password manager",
    "job board with search filters",
    "flashcard study app",
    "restaurant table reservation system",
    "real-time collaborative whiteboard",
    "package delivery tracker",
    "team meeting scheduler",
    "podcast player with transcripts",
    "crypto price alert bot",
    "form builder (drag-and-drop)",
    "API rate limiter service",
    "log viewer with filtering",
    "image compression service",
    "personal finance dashboard",
    "book library with recommendations",
    "web scraping pipeline with a UI",
    "offline-first todo app",
]


def scenario_rows():
    """Yield (register, question, lang, require_code) tuples."""
    for lang in LANGS:
        for task in CODEGEN_TASKS:
            yield ('codegen', f'Write a {lang} function that {task}.',
                   lang, True)
        for task in ALGO_TASKS:
            yield ('algo', f'Implement {task} in {lang}.', lang, True)
        for c in EXPLAIN_CONCEPTS:
            yield ('explain', f'Explain {c} in {lang} with a tiny example.',
                   lang, False)
        for task in API_TASKS:
            yield ('api', f'How do I {task} in {lang}?', lang, True)
    for app in ARCH_TASKS:
        yield ('arch', f'How would you structure {app}? Describe briefly.', '', False)
    for task in SQL_TASKS:
        yield ('sql', f'Write an SQL query to {task}.', 'sql', True)
    for task in SHELL_TASKS:
        yield ('shell', f'Give me a bash one-liner to {task}.', 'bash', True)
    for task in REGEX_TASKS:
        yield ('regex', f'Write a regex to {task}.', 'regex', True)
    for task in WEB_TASKS:
        yield ('web', f'Write the HTML/CSS/JS to {task}.', '', True)
    for prompt, snippet in DEBUG_TASKS:
        q = f'In code, {prompt}\n```\n{snippet}\n```'
        yield ('debug', q, '', False)
    for prompt, snippet in REVIEW_TASKS:
        q = f'Review this code: {prompt}\n```\n{snippet}\n```'
        yield ('review', q, '', False)
    for prompt, snippet in REFACTOR_TASKS:
        q = f'Refactor this: {prompt}\n```\n{snippet}\n```'
        yield ('refactor', q, '', False)
    for task in GIT_TASKS:
        yield ('git', f'Show the git commands to {task}.', 'bash', True)
    for task in DOCKER_TASKS:
        yield ('docker', f'Show the docker commands to {task}.', 'bash', True)
    for task in TEST_TASKS:
        yield ('test', f'Write a unit test: {task}. Pick a sensible language and framework.', '', True)
    for task in SECURITY_TASKS:
        yield ('security', f'Write code to {task}.', '', True)
    for task in DATA_TASKS:
        yield ('data', f'Implement a {task} with clean, tight code.', '', True)
    for task in HTTP_TASKS:
        yield ('http', f'{task}. Answer in 1-3 tight sentences.', '', False)
    for app in PLANNING_APPS:
        yield ('planning',
               f'Walk through building a {app} start to end: planning, '
               f'architecture, file structure, build order, and what you '
               f'verify at each step. Tight and concrete.',
               '', False)


# ─── Runner with resume + incremental append ───────────────────────────────

def prompt_hash(register, question, sample_idx):
    blob = register + '|' + str(sample_idx) + '|' + question
    return hashlib.sha1(blob.encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description='Round-8 code distillation dataset')
    ap.add_argument('--max-bytes', type=int, default=10_000_000,
                    help='stop when output file reaches this size (default 10 MB)')
    ap.add_argument('--max-rows', type=int, default=0, help='hard row cap (0 = none)')
    ap.add_argument('--seed-rows', type=int, default=0,
                    help='quick validation run (first N rows, writes to a temp file)')
    ap.add_argument('--samples', type=int, default=3, help='teacher samples per prompt')
    ap.add_argument('--teacher', default=DEFAULT_TEACHER)
    ap.add_argument('--base-url', default=DEFAULT_BASE)
    ap.add_argument('--concurrency', type=int, default=2)
    ap.add_argument('--registers', default=None, help='comma list, e.g. codegen,algo')
    args = ap.parse_args()

    allowed = set(args.registers.split(',')) if args.registers else None
    out_file = OUT
    if args.seed_rows:
        out_file = os.path.join(ROOT, 'training', 'dataset',
                                'round8-code-SEED.jsonl')
        for f in (out_file,):
            if os.path.exists(f):
                os.remove(f)

    scenarios = [s for s in scenario_rows() if not allowed or s[0] in allowed]
    print(f'catalog scenarios: {len(scenarios)} '
          f'(registers: {sorted(set(s[0] for s in scenarios))})')

    tasks = []
    for register, question, lang, require_code in scenarios:
        for sample_idx in range(args.samples):
            tasks.append((register, question, lang, require_code, sample_idx))
    random.shuffle(tasks)

    limit = args.seed_rows or args.max_rows or len(tasks)
    tasks = tasks[:limit]
    print(f'tasks: {len(tasks)} (samples={args.samples})')

    done = set()
    if os.path.exists(CHECKPOINT):
        try:
            done = set(json.load(open(CHECKPOINT)))
        except Exception:
            done = set()

    lock = threading.Lock()
    stats = {'by_register': {}, 'failed': 0, 'started': time.time(),
             'bytes': 0, 'target_bytes': args.max_bytes}
    rows_written = 0

    # Trim a partial trailing line left by a crash mid-append, so downstream
    # training loaders never choke on it (resume hygiene).
    if os.path.exists(out_file):
        try:
            with open(out_file, 'rb+') as f:
                f.seek(0, 2)
                size = f.tell()
                if size:
                    f.seek(-1, 2)
                    if f.read(1) != b'\n':
                        while size > 0:
                            size -= 1
                            f.seek(size, 0)
                            if f.read(1) == b'\n':
                                f.seek(size + 1, 0)
                                f.truncate()
                                print('   (trimmed partial trailing line from resume)')
                                break
        except Exception:
            pass

    def write_checkpoint():
        # Atomic write: never leave a truncated checkpoint that would make a
        # resume regenerate the whole dataset.
        tmp = CHECKPOINT + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(sorted(done), f)
        os.replace(tmp, CHECKPOINT)

    def produce(task):
        register, question, lang, require_code, sample_idx = task
        ph = prompt_hash(register, question, sample_idx)
        if ph in done:
            return None
        try:
            msgs = build_teacher_messages(question, register, lang)
            temperature = round(0.6 + 0.15 * (sample_idx % 4), 2)
            reply = teacher_reply(msgs, args.teacher, args.base_url,
                                  temperature=temperature)
            out = clean_and_validate(question, reply, register, require_code)
            if out is None:
                return {'ph': ph, 'ok': False, 'why': 'filtered'}
            row = {
                'instruction': question,
                'input': '',
                'output': out,
                'source': f'distill:{register}:qwen3.6',
            }
            return {'ph': ph, 'ok': True, 'row': row, 'register': register}
        except Exception as e:
            return {'ph': ph, 'ok': False, 'why': f'error:{type(e).__name__}:{str(e)[:80]}'}

    def flush_new(new_rows, new_done, new_fails):
        nonlocal rows_written
        with lock:
            for r in new_rows:
                line = json.dumps(r, ensure_ascii=False) + '\n'
                with open(out_file, 'a', encoding='utf-8') as f:
                    f.write(line)
                rows_written += 1
                stats['bytes'] = os.path.getsize(out_file)
                reg = r.get('source', '').split(':')[1]
                stats['by_register'][reg] = stats['by_register'].get(reg, 0) + 1
            done.update(new_done)
            stats['failed'] += new_fails
            write_checkpoint()
            el = time.time() - stats['started']
            bps = stats['bytes'] / el if el > 0 else 0
            eta = (args.max_bytes - stats['bytes']) / bps / 3600 if bps > 0 else 0
            print(f'\r  rows={rows_written} bytes={stats["bytes"]/1e6:.2f}MB '
                  f'failed={stats["failed"]} elapsed={int(el)}s '
                  f'eta={eta:.1f}h ', flush=True)

    # batch of futures (bounded so we can stop at byte cap)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        batch = []
        batch_done = []
        batch_fails = 0
        idx = 0
        while idx < len(tasks):
            if stats['bytes'] >= args.max_bytes:
                print(f'\n✅ target {args.max_bytes/1e6:.1f} MB reached — stopping.')
                break
            window = tasks[idx:idx + args.concurrency]
            idx += len(window)
            futs = [ex.submit(produce, t) for t in window]
            for fut in futs:
                res = fut.result()
                if res is None:
                    continue
                if res['ok']:
                    batch.append(res['row'])
                    batch_done.append(res['ph'])
                elif res['why'].startswith('filtered'):
                    # Filtered = prompt consumed; checkpoint so we don't retry it.
                    batch_done.append(res['ph'])
                    batch_fails += 1
                else:
                    # Transient error (timeout/network): do NOT checkpoint — a
                    # resume retries this prompt instead of silently dropping it.
                    batch_fails += 1
                if len(batch_done) >= 10:
                    flush_new(batch, batch_done, batch_fails)
                    batch, batch_done, batch_fails = [], [], 0
        flush_new(batch, batch_done, batch_fails)

    stats.update({'total_rows': rows_written,
                  'completed': time.time() - stats['started']})
    json.dump(stats, open(STATS, 'w'), indent=2)
    print(f'\n✅ wrote {out_file}: {rows_written} rows, '
          f'{stats["bytes"]/1e6:.2f} MB')
    print(f'   by_register: {stats["by_register"]}')
    print(f'   failed/filtered: {stats["failed"]}')
    if args.seed_rows:
        print('   (SEED file — validate quality, then run the full build)')


if __name__ == '__main__':
    main()
