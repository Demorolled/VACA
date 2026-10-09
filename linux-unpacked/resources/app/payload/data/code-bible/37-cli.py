# -*- coding: utf-8 -*-
"""
Code Bible — Category 37: CLI & Terminal (atomic).
Convention: ANSI-free pure helpers; colors optional, no process deps.
"""
CHUNKS = [
    {
        "id": "cli-parse-args",
        "name": "CLI Arg Parser (short/long)",
        "category": "cli",
        "lang": "typescript",
        "when": "Parsing -a, --alpha, --key=value CLI args with aliases",
        "why": "Atomic parser — short+long flags, value pairs, positionals, no deps",
        "tags": ["cli", "args", "parse", "flags", "terminal"],
        "iface": r'''export interface ParsedArgs { flags: Record<string, string | boolean>; positionals: string[] }
export function cliArgs(argv: string[], aliases?: Record<string, string>): ParsedArgs''',
        "code": r'''export function cliArgs(argv: string[], aliases: Record<string, string> = {}) {
  const flags: Record<string, string | boolean> = {};
  const positionals: string[] = [];
  for (const a of argv) {
    if (a === '--') { positionals.push(...argv.slice(argv.indexOf(a) + 1)); break; }
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      const name = eq >= 0 ? a.slice(2, eq) : a.slice(2);
      flags[aliases[name] ?? name] = eq >= 0 ? a.slice(eq + 1) : true;
    } else if (a.startsWith('-') && a.length === 2) {
      const name = aliases[a[1]] ?? a[1];
      flags[name] = true;
    } else positionals.push(a);
  }
  return { flags, positionals };
}''',
        "provides": "cliArgs(argv, aliases)",
        "depends": [],
    },
    {
        "id": "cli-table",
        "name": "ASCII Table Renderer",
        "category": "cli",
        "lang": "typescript",
        "when": "Rendering tabular data as aligned text for terminals",
        "why": "Atomic table — headers + rows in, padded + bordered output out",
        "tags": ["cli", "table", "ascii", "render", "terminal"],
        "iface": r'''export function renderTable(headers: string[], rows: string[][]): string''',
        "code": r'''export function renderTable(headers: string[], rows: string[][]) {
  const widths = headers.map((h, i) => Math.max(h.length, ...rows.map((r) => (r[i] ?? '').length)));
  const fmt = (cells: string[]) => cells.map((c, i) => c.padEnd(widths[i])).join(' | ');
  const sep = headers.map((w) => '-'.repeat(w)).join('-+-');
  return [fmt(headers), sep, ...rows.map(fmt)].join('\n');
}''',
        "provides": "renderTable(headers, rows)",
        "depends": [],
    },
    {
        "id": "cli-progress",
        "name": "Progress Line Formatter",
        "category": "cli",
        "lang": "typescript",
        "when": "Formatting a single-line progress display with percent + ETA",
        "why": "Atomic formatter — done/total + elapsed in, \r-ready string out",
        "tags": ["cli", "progress", "eta", "percent", "format"],
        "iface": r'''export function progressLine(done: number, total: number, elapsedMs: number): string''',
        "code": r'''export function progressLine(done: number, total: number, elapsedMs: number) {
  const pct = total <= 0 ? 100 : Math.min(100, (done / total) * 100);
  const per = done === 0 ? 0 : elapsedMs / done;
  const etaMs = per * Math.max(0, total - done);
  const fmt = (ms: number) => {
    const s = Math.round(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  };
  return `[${'#'.repeat(Math.round(pct / 5))}${'-'.repeat(20 - Math.round(pct / 5))}] ${pct.toFixed(0)}% ETA ${fmt(etaMs)}`;
}''',
        "provides": "progressLine(done, total, elapsedMs)",
        "depends": [],
    },
    {
        "id": "cli-spinner-frames",
        "name": "Spinner Frame Sequence",
        "category": "cli",
        "lang": "typescript",
        "when": "Animating a spinner from an elapsed tick",
        "why": "Atomic frames — tick in, frame char out; cycle-safe",
        "tags": ["cli", "spinner", "frames", "animate", "tick"],
        "iface": r'''export function spinnerFrame(tick: number, frames = ['|', '/', '-', '\\\\']): string''',
        "code": r'''export function spinnerFrame(tick: number, frames = ['|', '/', '-', '\\\\']) {
  return frames[Math.abs(tick) % frames.length];
}''',
        "provides": "spinnerFrame(tick, frames)",
        "depends": [],
    },
    {
        "id": "cli-truncate",
        "name": "Truncate with Ellipsis",
        "category": "cli",
        "lang": "typescript",
        "when": "Clipping long strings to a terminal width with ellipsis",
        "why": "Atomic truncation — max length in, safe cut at char boundary",
        "tags": ["cli", "truncate", "ellipsis", "width", "string"],
        "iface": r'''export function truncate(text: string, max: number, ellipsis = '...'): string''',
        "code": r'''export function truncate(text: string, max: number, ellipsis = '...') {
  if (text.length <= max) return text;
  if (max <= ellipsis.length) return ellipsis.slice(0, max);
  return text.slice(0, max - ellipsis.length) + ellipsis;
}''',
        "provides": "truncate(text, max, ellipsis)",
        "depends": [],
    },
    {
        "id": "cli-confirm-parse",
        "name": "Yes/No Confirmation Parser",
        "category": "cli",
        "lang": "typescript",
        "when": "Interpreting interactive y/n input with defaults",
        "why": "Atomic parser — raw input in, boolean with default out; y/n/yes/no",
        "tags": ["cli", "confirm", "yes", "no", "parse"],
        "iface": r'''export function parseConfirm(input: string | undefined, def = false): boolean''',
        "code": r'''export function parseConfirm(input: string | undefined, def = false) {
  if (!input) return def;
  const v = input.trim().toLowerCase();
  if (['y', 'yes', 'true', '1'].includes(v)) return true;
  if (['n', 'no', 'false', '0'].includes(v)) return false;
  return def;
}''',
        "provides": "parseConfirm(input, def)",
        "depends": [],
    },
    {
        "id": "cli-colorize",
        "name": "ANSI Colorizer",
        "category": "cli",
        "lang": "typescript",
        "when": "Wrapping text in ANSI color codes (with auto-disable)",
        "why": "Atomic color — name + text in, ANSI-wrapped out; off when disabled",
        "tags": ["cli", "ansi", "color", "style", "terminal"],
        "iface": r'''export class Ansi {
  constructor(enabled?: boolean)
  paint(color: string, text: string): string
}''',
        "code": r'''const CODES: Record<string, number> = { red: 31, green: 32, yellow: 33, blue: 34, magenta: 35, cyan: 36, white: 37, gray: 90, bold: 1, dim: 2 };
export class Ansi {
  constructor(private enabled = true) {}
  paint(color: string, text: string) {
    const code = CODES[color];
    if (!this.enabled || code === undefined) return text;
    return `\u001b[${code}m${text}\u001b[0m`;
  }
}''',
        "provides": "Ansi",
        "depends": [],
    },
    {
        "id": "cli-command-router",
        "name": "Command Router",
        "category": "cli",
        "lang": "typescript",
        "when": "Dispatching a CLI command string to registered handlers",
        "why": "Atomic router — name + args in, handler out; unknown → default",
        "tags": ["cli", "command", "router", "dispatch", "handler"],
        "iface": r'''export class CommandRouter {
  register(name: string, handler: (args: string[]) => void): void
  route(input: string): boolean
}''',
        "code": r'''export class CommandRouter {
  private handlers = new Map<string, (args: string[]) => void>();
  register(name: string, handler: (args: string[]) => void) { this.handlers.set(name, handler); }
  route(input: string) {
    const [name, ...rest] = input.trim().split(/\s+/);
    const h = this.handlers.get(name ?? '');
    if (!h) return false;
    h(rest);
    return true;
  }
}''',
        "provides": "CommandRouter",
        "depends": [],
    },
    {
        "id": "cli-help-screen",
        "name": "Help Screen Generator",
        "category": "cli",
        "lang": "typescript",
        "when": "Formatting command usage + options into a help screen",
        "why": "Atomic help — usage + option rows in, aligned text out",
        "tags": ["cli", "help", "usage", "options", "screen"],
        "iface": r'''export function helpScreen(usage: string, options: Array<[string, string]>): string''',
        "code": r'''export function helpScreen(usage: string, options: Array<[string, string]>) {
  const w = Math.max(...options.map(([o]) => o.length));
  const body = options.map(([flag, desc]) => `  ${flag.padEnd(w)}  ${desc}`).join('\n');
  return `Usage: ${usage}\n\nOptions:\n${body}`;
}''',
        "provides": "helpScreen(usage, options)",
        "depends": [],
    },
    {
        "id": "cli-path-resolve",
        "name": "Path Resolver",
        "category": "cli",
        "lang": "typescript",
        "when": "Resolving . and .. segments in a path string",
        "why": "Atomic resolver — path in, normalized absolute-ish path out; no fs",
        "tags": ["cli", "path", "resolve", "normalize", "segments"],
        "iface": r'''export function resolvePath(path: string): string''',
        "code": r'''export function resolvePath(path: string) {
  const isAbs = path.startsWith('/');
  const parts = path.split('/').filter((p) => p && p !== '.');
  const out: string[] = [];
  for (const p of parts) {
    if (p === '..') out.pop();
    else out.push(p);
  }
  return (isAbs ? '/' : '') + out.join('/');
}''',
        "provides": "resolvePath(path)",
        "depends": [],
    },
    {
        "id": "cli-glob-match",
        "name": "Simple Glob Matcher",
        "category": "cli",
        "lang": "typescript",
        "when": "Matching file paths against * and ** patterns",
        "why": "Atomic matcher — pattern + path in, boolean out; ** crosses slashes",
        "tags": ["cli", "glob", "match", "pattern", "files"],
        "iface": r'''export function globMatch(pattern: string, path: string): boolean''',
        "code": r'''function seg(re: string) { return re.replace(/\*\*/g, '\u0000').replace(/\*/g, '[^/]*').replace(/\u0000/g, '.*'); }
export function globMatch(pattern: string, path: string) {
  const re = '^' + seg(pattern.split('/').map((p) => p.replace(/[.+^${}()|[\]\\]/g, '\\$&')).join('/')) + '$';
  return new RegExp(re).test(path);
}''',
        "provides": "globMatch(pattern, path)",
        "depends": [],
    },
    {
        "id": "cli-key-value-parse",
        "name": "Key=Value Parser",
        "category": "cli",
        "lang": "typescript",
        "when": "Parsing 'key=value' tokens from the command line",
        "why": "Atomic parser — tokens in, map out; repeated keys keep last",
        "tags": ["cli", "key-value", "parse", "tokens", "env"],
        "iface": r'''export function keyValueParse(tokens: string[]): Record<string, string>''',
        "code": r'''export function keyValueParse(tokens: string[]) {
  const out: Record<string, string> = {};
  for (const t of tokens) {
    const eq = t.indexOf('=');
    if (eq > 0) out[t.slice(0, eq)] = t.slice(eq + 1);
  }
  return out;
}''',
        "provides": "keyValueParse(tokens)",
        "depends": [],
    },
    {
        "id": "cli-quote-shell",
        "name": "Shell-Safe Quoting",
        "category": "cli",
        "lang": "typescript",
        "when": "Quoting an argument so shell injection can't break out",
        "why": "Atomic quoting — single-quote wrap with escape, always safe",
        "tags": ["cli", "shell", "quote", "escape", "security"],
        "iface": r'''export function shellQuote(arg: string): string''',
        "code": r'''export function shellQuote(arg: string) {
  return `'${arg.replace(/'/g, `'\\''`)}'`;
}''',
        "provides": "shellQuote(arg)",
        "depends": [],
    },
    {
        "id": "cli-exit-codes",
        "name": "Exit Code Mapper",
        "category": "cli",
        "lang": "typescript",
        "when": "Mapping app conditions to conventional exit codes",
        "why": "Atomic map — condition key in, numeric code out; 0 ok / 1 error / 2 usage",
        "tags": ["cli", "exit", "code", "status", "error"],
        "iface": r'''export function exitCode(kind: 'ok' | 'error' | 'usage' | 'not-found' | 'interrupted'): number''',
        "code": r'''export function exitCode(kind: 'ok' | 'error' | 'usage' | 'not-found' | 'interrupted') {
  return { ok: 0, error: 1, usage: 2, 'not-found': 1, interrupted: 130 }[kind];
}''',
        "provides": "exitCode(kind)",
        "depends": [],
    },
    {
        "id": "cli-paginate",
        "name": "Paginated List Window",
        "category": "cli",
        "lang": "typescript",
        "when": "Slicing a long list into pages for terminal paging",
        "why": "Atomic pager — items + page size + page number in, window + meta out",
        "tags": ["cli", "page", "paginate", "window", "list"],
        "iface": r'''export function paginate<T>(items: T[], page: number, size: number): { items: T[]; page: number; pages: number; total: number }''',
        "code": r'''export function paginate<T>(items: T[], page: number, size: number) {
  const pages = Math.max(1, Math.ceil(items.length / Math.max(1, size)));
  const p = Math.max(1, Math.min(page, pages));
  return { items: items.slice((p - 1) * size, p * size), page: p, pages, total: items.length };
}''',
        "provides": "paginate(items, page, size)",
        "depends": [],
    },
    {
        "id": "cli-word-wrap",
        "name": "Word Wrap",
        "category": "cli",
        "lang": "typescript",
        "when": "Wrapping text to a terminal width at word boundaries",
        "why": "Atomic wrap — text + width in, lines out; long words hard-broken",
        "tags": ["cli", "wrap", "width", "text", "terminal"],
        "iface": r'''export function wordWrap(text: string, width: number): string[]''',
        "code": r'''export function wordWrap(text: string, width: number) {
  const lines: string[] = [];
  for (const para of text.split('\n')) {
    let line = '';
    for (const word of para.split(/\s+/)) {
      if (!word) continue;
      if (line && line.length + 1 + word.length > width) { lines.push(line); line = word; }
      else if (line) line += ' ' + word;
      else line = word;
      while (line.length > width) { lines.push(line.slice(0, width)); line = line.slice(width); }
    }
    if (line) lines.push(line);
  }
  return lines;
}''',
        "provides": "wordWrap(text, width)",
        "depends": [],
    },
    {
        "id": "cli-banner",
        "name": "ASCII Banner Generator",
        "category": "cli",
        "lang": "typescript",
        "when": "Centering a title with dashes for section separators",
        "why": "Atomic banner — title + width in, framed line out",
        "tags": ["cli", "banner", "ascii", "title", "separator"],
        "iface": r'''export function banner(title: string, width = 60): string''',
        "code": r'''export function banner(title: string, width = 60) {
  const inner = ` ${title} `;
  if (inner.length >= width) return title;
  const pad = width - inner.length;
  const left = Math.floor(pad / 2), right = pad - left;
  return '='.repeat(left) + inner + '='.repeat(right);
}''',
        "provides": "banner(title, width)",
        "depends": [],
    },
    {
        "id": "cli-human-size",
        "name": "Human-Readable Bytes",
        "category": "cli",
        "lang": "typescript",
        "when": "Formatting byte counts as KB/MB/GB for CLI output",
        "why": "Atomic formatter — bytes in, '4.2 MB' out; decimal units",
        "tags": ["cli", "bytes", "format", "size", "human"],
        "iface": r'''export function humanBytes(bytes: number, decimals = 1): string''',
        "code": r'''export function humanBytes(bytes: number, decimals = 1) {
  if (!Number.isFinite(bytes)) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let u = 0, v = bytes;
  while (Math.abs(v) >= 1000 && u < units.length - 1) { v /= 1000; u++; }
  return `${v.toFixed(u === 0 ? 0 : decimals)} ${units[u]}`;
}''',
        "provides": "humanBytes(bytes, decimals)",
        "depends": [],
    },
    {
        "id": "cli-rate-limit",
        "name": "Token Bucket (Rate Limit)",
        "category": "cli",
        "lang": "typescript",
        "when": "Throttling CLI/API calls to N per second",
        "why": "Atomic bucket — capacity + refill in, allow() boolean out",
        "tags": ["cli", "rate", "limit", "throttle", "bucket"],
        "iface": r'''export class TokenBucket {
  constructor(ratePerSec: number, capacity: number)
  allow(tokens = 1): boolean
}''',
        "code": r'''export class TokenBucket {
  private tokens: number;
  private last = Date.now();
  constructor(private ratePerSec: number, private capacity: number) { this.tokens = capacity; }
  allow(tokens = 1) {
    const now = Date.now();
    this.tokens = Math.min(this.capacity, this.tokens + ((now - this.last) / 1000) * this.ratePerSec);
    this.last = now;
    if (this.tokens < tokens) return false;
    this.tokens -= tokens;
    return true;
  }
}''',
        "provides": "TokenBucket",
        "depends": [],
    },
    {
        "id": "cli-prompt-menu",
        "name": "Menu Builder",
        "category": "cli",
        "lang": "typescript",
        "when": "Numbering menu options for interactive prompts",
        "why": "Atomic menu — options in, numbered lines out with selection parse helper",
        "tags": ["cli", "menu", "prompt", "interactive", "options"],
        "iface": r'''export function menuLines(options: string[]): string[]
export function menuSelect(input: string, count: number): number | null''',
        "code": r'''export function menuLines(options: string[]) {
  return options.map((o, i) => `  ${i + 1}. ${o}`);
}
export function menuSelect(input: string, count: number) {
  const n = parseInt(input, 10);
  return Number.isFinite(n) && n >= 1 && n <= count ? n - 1 : null;
}''',
        "provides": "menuLines / menuSelect",
        "depends": [],
    },
    {
        "id": "cli-indent-block",
        "name": "Indent Block (cli)",
        "category": "cli",
        "lang": "typescript",
        "when": "Indenting multi-line CLI output blocks",
        "why": "Atomic indent — text + prefix in, every non-empty line prefixed",
        "tags": ["cli", "indent", "block", "prefix", "format"],
        "iface": r'''export function indentBlock(text: string, prefix = '  '): string''',
        "code": r'''export function indentBlock(text: string, prefix = '  ') {
  return text.split('\n').map((l) => (l.trim() ? prefix + l : l)).join('\n');
}''',
        "provides": "indentBlock(text, prefix)",
        "depends": [],
    },
    {
        "id": "cli-csv-quote",
        "name": "CSV Field Quoter",
        "category": "cli",
        "lang": "typescript",
        "when": "Escaping CSV fields containing commas, quotes, or newlines",
        "why": "Atomic quoting — RFC-4180 double-quote escaping, no deps",
        "tags": ["cli", "csv", "quote", "escape", "field"],
        "iface": r'''export function csvQuote(field: string): string''',
        "code": r'''export function csvQuote(field: string) {
  return /[",\n\r]/.test(field) ? `"${field.replace(/"/g, '""')}"` : field;
}''',
        "provides": "csvQuote(field)",
        "depends": [],
    },
    {
        "id": "cli-json-out",
        "name": "JSON Pretty Printer",
        "category": "cli",
        "lang": "typescript",
        "when": "Pretty-printing JSON for CLI inspection",
        "why": "Atomic printer — value + indent in, stable 2-space output",
        "tags": ["cli", "json", "pretty", "print", "format"],
        "iface": r'''export function prettyJson(value: unknown, indent = 2): string''',
        "code": r'''export function prettyJson(value: unknown, indent = 2) {
  return JSON.stringify(value, null, indent);
}''',
        "provides": "prettyJson(value, indent)",
        "depends": [],
    },
    {
        "id": "cli-timeout-wrap",
        "name": "Timeout Wrapper",
        "category": "cli",
        "lang": "typescript",
        "when": "Rejecting a slow promise after a timeout",
        "why": "Atomic race — promise + ms in, result or TimeoutError out",
        "tags": ["cli", "timeout", "promise", "async", "wrapper"],
        "iface": r'''export function withTimeout<T>(p: Promise<T>, ms: number, message = 'Operation timed out'): Promise<T>''',
        "code": r'''export function withTimeout<T>(p: Promise<T>, ms: number, message = 'Operation timed out') {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(message)), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}''',
        "provides": "withTimeout(p, ms, message)",
        "depends": [],
    },
    {
        "id": "cli-search-filter",
        "name": "List Filter (fuzzy prefix)",
        "category": "cli",
        "lang": "typescript",
        "when": "Filtering interactive list choices by typed prefix",
        "why": "Atomic filter \u2014 query + items in, case-insensitive prefix matches out",
        "tags": [
            "cli",
            "filter",
            "search",
            "prefix",
            "list"
        ],
        "iface": "export function filterList<T>(items: T[], query: string, label: (t: T) => string): T[]",
        "code": "export function filterList<T>(items: T[], query: string, label: (t: T) => string) {\n  const q = query.trim().toLowerCase();\n  if (!q) return items;\n  return items.filter((t) => label(t).toLowerCase().includes(q));\n}",
        "provides": "filterList(items, query, label)",
        "depends": []
    },
]
