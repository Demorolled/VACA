# -*- coding: utf-8 -*-
"""
Code Bible — Category 35: Code Generation & Tooling (atomic).
Convention: helpers for scaffolding, templates, naming, diffs; no deps.
"""
CHUNKS = [
    {
        "id": "gen-camel-case",
        "name": "Camel Case Converter",
        "category": "gen",
        "lang": "typescript",
        "when": "Converting arbitrary strings to camelCase identifiers",
        "why": "Atomic identifier normalizer — splits on separators, lowercases, caps segments",
        "tags": ["gen", "camel", "case", "identifier", "naming"],
        "iface": r'''export function toCamelCase(input: string): string''',
        "code": r'''export function toCamelCase(input: string) {
  const parts = input.split(/[^a-z0-9]+/i).filter(Boolean);
  return parts.map((p, i) => (i === 0 ? p.toLowerCase() : p[0].toUpperCase() + p.slice(1).toLowerCase())).join('');
}''',
        "provides": "toCamelCase(input)",
        "depends": [],
    },
    {
        "id": "gen-kebab-case",
        "name": "Kebab Case Converter",
        "category": "gen",
        "lang": "typescript",
        "when": "Converting strings to kebab-case slugs for filenames and URLs",
        "why": "Atomic slugger — separators and case boundaries to hyphens, safe charset",
        "tags": ["gen", "kebab", "slug", "case", "filename"],
        "iface": r'''export function toKebabCase(input: string): string''',
        "code": r'''export function toKebabCase(input: string) {
  return input
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[^a-z0-9]+/gi, '-')
    .toLowerCase()
    .replace(/^-+|-+$/g, '');
}''',
        "provides": "toKebabCase(input)",
        "depends": [],
    },
    {
        "id": "gen-pascal-case",
        "name": "Pascal Case Converter",
        "category": "gen",
        "lang": "typescript",
        "when": "Converting strings to PascalCase for class and component names",
        "why": "Atomic namer — camelCase then capitalize first letter",
        "tags": ["gen", "pascal", "case", "class", "component"],
        "iface": r'''export function toPascalCase(input: string): string''',
        "code": r'''export function toPascalCase(input: string) {
  const camel = input.split(/[^a-z0-9]+/i).filter(Boolean)
    .map((p) => p[0].toUpperCase() + p.slice(1).toLowerCase()).join('');
  return camel ? camel[0].toUpperCase() + camel.slice(1) : camel;
}''',
        "provides": "toPascalCase(input)",
        "depends": [],
    },
    {
        "id": "gen-snake-case",
        "name": "Snake Case Converter",
        "category": "gen",
        "lang": "typescript",
        "when": "Converting strings to snake_case for constants and DB columns",
        "why": "Atomic converter — boundaries to underscores, lowercase, trimmed",
        "tags": ["gen", "snake", "case", "underscore", "constant"],
        "iface": r'''export function toSnakeCase(input: string): string''',
        "code": r'''export function toSnakeCase(input: string) {
  return input
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[^a-z0-9]+/gi, '_')
    .toLowerCase()
    .replace(/^_+|_+$/g, '');
}''',
        "provides": "toSnakeCase(input)",
        "depends": [],
    },
    {
        "id": "gen-pluralize",
        "name": "Pluralizer",
        "category": "gen",
        "lang": "typescript",
        "when": "Pluralizing English nouns for labels and endpoints",
        "why": "Atomic pluralizer — common rules + irregulars + uncountables",
        "tags": ["gen", "plural", "singular", "english", "word"],
        "iface": r'''export function pluralize(word: string): string''',
        "code": r'''const IRREGULAR: Record<string, string> = { person: 'people', child: 'children', mouse: 'mice', foot: 'feet', tooth: 'teeth', goose: 'geese', man: 'men', woman: 'women' };
export function pluralize(word: string) {
  if (IRREGULAR[word.toLowerCase()]) return IRREGULAR[word.toLowerCase()];
  if (/(s|x|z|ch|sh)$/i.test(word)) return word + 'es';
  if (/[^aeiou]y$/i.test(word)) return word.slice(0, -1) + 'ies';
  if (/(f|fe)$/i.test(word)) return word.replace(/f{1,2}e?$/i, 'ves');
  return word + 's';
}''',
        "provides": "pluralize(word)",
        "depends": [],
    },
    {
        "id": "gen-unique-name",
        "name": "Unique Name Generator",
        "category": "gen",
        "lang": "typescript",
        "when": "Generating a name not already used in a collection",
        "why": "Atomic dedupe — base + suffix counter, collision-safe",
        "tags": ["gen", "unique", "name", "dedupe", "generate"],
        "iface": r'''export function uniqueName(base: string, existing: Set<string>): string''',
        "code": r'''export function uniqueName(base: string, existing: Set<string>) {
  if (!existing.has(base)) return base;
  let i = 2;
  while (existing.has(`${base} ${i}`)) i++;
  return `${base} ${i}`;
}''',
        "provides": "uniqueName(base, existing)",
        "depends": [],
    },
    {
        "id": "gen-indent",
        "name": "Indent / Dedent",
        "category": "gen",
        "lang": "typescript",
        "when": "Indenting every line of generated source by N spaces",
        "why": "Atomic formatter — string + level in, indented output out; keeps blank lines bare",
        "tags": ["gen", "indent", "format", "source", "whitespace"],
        "iface": r'''export function indent(text: string, spaces = 2): string''',
        "code": r'''export function indent(text: string, spaces = 2) {
  const pad = ' '.repeat(spaces);
  return text.split('\n').map((l) => (l.trim() ? pad + l : l)).join('\n');
}''',
        "provides": "indent(text, spaces)",
        "depends": [],
    },
    {
        "id": "gen-template-render",
        "name": "Template Renderer ({{var}})",
        "category": "gen",
        "lang": "typescript",
        "when": "Rendering placeholder templates with a values object",
        "why": "Atomic renderer — {{key}} placeholders, missing keys become empty string",
        "tags": ["gen", "template", "render", "placeholder", "string"],
        "iface": r'''export function renderTemplate(template: string, values: Record<string, string>): string''',
        "code": r'''export function renderTemplate(template: string, values: Record<string, string>) {
  return template.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key: string) => values[key] ?? '');
}''',
        "provides": "renderTemplate(template, values)",
        "depends": [],
    },
    {
        "id": "gen-import-sort",
        "name": "Import Sorter",
        "category": "gen",
        "lang": "typescript",
        "when": "Sorting import statements deterministically",
        "why": "Atomic sorter — parses 'from' paths, groups by source, stable output",
        "tags": ["gen", "import", "sort", "module", "statement"],
        "iface": r'''export function sortImports(imports: string[]): string[]''',
        "code": r'''export function sortImports(imports: string[]) {
  return imports.slice().sort((a, b) => {
    const pa = /from\s+['"]([^'"]+)['"]/.exec(a)?.[1] ?? a;
    const pb = /from\s+['"]([^'"]+)['"]/.exec(b)?.[1] ?? b;
    return pa.localeCompare(pb);
  });
}''',
        "provides": "sortImports(imports)",
        "depends": [],
    },
    {
        "id": "gen-type-interface",
        "name": "Interface Generator",
        "category": "gen",
        "lang": "typescript",
        "when": "Generating a TypeScript interface from a sample object",
        "why": "Atomic shape → interface — infers string/number/boolean/array types",
        "tags": ["gen", "interface", "typescript", "types", "infer"],
        "iface": r'''export function inferInterface(name: string, sample: Record<string, unknown>): string''',
        "code": r'''function tsType(v: unknown): string {
  if (Array.isArray(v)) return v.length ? `${tsType(v[0])}[]` : 'unknown[]';
  if (v === null || v === undefined) return 'unknown';
  if (typeof v === 'string') return 'string';
  if (typeof v === 'number') return 'number';
  if (typeof v === 'boolean') return 'boolean';
  if (typeof v === 'object') return '{ [key: string]: unknown }';
  return 'unknown';
}
export function inferInterface(name: string, sample: Record<string, unknown>) {
  const fields = Object.entries(sample).map(([k, v]) => `  ${k}: ${tsType(v)};`);
  return `export interface ${name} {\n${fields.join('\n')}\n}`;
}''',
        "provides": "inferInterface(name, sample)",
        "depends": [],
    },
    {
        "id": "gen-stub-func",
        "name": "Function Stub Generator",
        "category": "gen",
        "lang": "typescript",
        "when": "Scaffolding a typed function signature with a TODO body",
        "why": "Atomic stub — name + params in, throw-not-implemented body out",
        "tags": ["gen", "stub", "function", "scaffold", "todo"],
        "iface": r'''export function stubFunction(name: string, params: Array<{ name: string; type: string }>, ret = 'void'): string''',
        "code": r'''export function stubFunction(name: string, params: Array<{ name: string; type: string }>, ret = 'void') {
  const sig = params.map((p) => `${p.name}: ${p.type}`).join(', ');
  return `export function ${name}(${sig}): ${ret} {\n  throw new Error('Not implemented');\n}`;
}''',
        "provides": "stubFunction(name, params, ret)",
        "depends": [],
    },
    {
        "id": "gen-doc-comment",
        "name": "JSDoc Comment Generator",
        "category": "gen",
        "lang": "typescript",
        "when": "Wrapping a function with a JSDoc block from a one-line summary",
        "why": "Atomic doc — summary + optional params/returns in, formatted block out",
        "tags": ["gen", "jsdoc", "comment", "doc", "documentation"],
        "iface": r'''export function jsdoc(summary: string, params: Array<{ name: string; desc: string }> = [], returns?: string): string''',
        "code": r'''export function jsdoc(summary: string, params: Array<{ name: string; desc: string }> = [], returns?: string) {
  const lines = ['/**', ` * ${summary}`];
  for (const p of params) lines.push(` * @param ${p.name} ${p.desc}`);
  if (returns) lines.push(` * @returns ${returns}`);
  lines.push(' */');
  return lines.join('\n');
}''',
        "provides": "jsdoc(summary, params, returns)",
        "depends": [],
    },
    {
        "id": "gen-lint-config",
        "name": "Config Merger (defaults + overrides)",
        "category": "gen",
        "lang": "typescript",
        "when": "Merging tool configs with defaults and one-level deep overrides",
        "why": "Atomic merge — recursive shallow merge, arrays replaced not concatenated",
        "tags": ["gen", "config", "merge", "defaults", "overrides"],
        "iface": r'''export function mergeConfig<T extends Record<string, unknown>>(defaults: T, overrides: Partial<T>): T''',
        "code": r'''export function mergeConfig<T extends Record<string, unknown>>(defaults: T, overrides: Partial<T>): T {
  const out: Record<string, unknown> = { ...defaults };
  for (const [k, v] of Object.entries(overrides)) {
    if (v && typeof v === 'object' && !Array.isArray(v) && typeof out[k] === 'object' && !Array.isArray(out[k])) {
      out[k] = mergeConfig(out[k] as Record<string, unknown>, v as Record<string, unknown>);
    } else out[k] = v;
  }
  return out as T;
}''',
        "provides": "mergeConfig(defaults, overrides)",
        "depends": [],
    },
    {
        "id": "gen-line-diff",
        "name": "Line Diff (LCS-ish)",
        "category": "gen",
        "lang": "typescript",
        "when": "Highlighting added/removed lines between two source texts",
        "why": "Atomic differ — simple LCS on lines, +/- markers out, stable order",
        "tags": ["gen", "diff", "lines", "lcs", "compare"],
        "iface": r'''export function lineDiff(a: string, b: string): Array<{ type: '+' | '-' | ' '; line: string }>''',
        "code": r'''export function lineDiff(a: string, b: string) {
  const A = a.split('\n'), B = b.split('\n');
  const m = A.length, n = B.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--)
    dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: Array<{ type: '+' | '-' | ' '; line: string }> = [];
  let i = 0, j = 0;
  while (i < m && j < n) {
    if (A[i] === B[j]) { out.push({ type: ' ', line: A[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: '-', line: A[i] }); i++; }
    else { out.push({ type: '+', line: B[j] }); j++; }
  }
  while (i < m) out.push({ type: '-', line: A[i++] });
  while (j < n) out.push({ type: '+', line: B[j++] });
  return out;
}''',
        "provides": "lineDiff(a, b)",
        "depends": [],
    },
    {
        "id": "gen-export-walk",
        "name": "Export Walker",
        "category": "gen",
        "lang": "typescript",
        "when": "Listing all top-level exports in a source file",
        "why": "Atomic parser — regexes export function/class/const, returns names",
        "tags": ["gen", "export", "walk", "parse", "symbols"],
        "iface": r'''export function listExports(source: string): string[]''',
        "code": r'''export function listExports(source: string) {
  const out: string[] = [];
  const re = /export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source))) out.push(m[1]);
  return out;
}''',
        "provides": "listExports(source)",
        "depends": [],
    },
    {
        "id": "gen-arg-parser",
        "name": "CLI Arg Parser",
        "category": "gen",
        "lang": "typescript",
        "when": "Parsing --flag and --key=value style CLI arguments",
        "why": "Atomic parser — argv in, flags + positionals out; boolean flag default true",
        "tags": ["gen", "cli", "args", "parse", "flags"],
        "iface": r'''export function parseArgs(argv: string[]): { flags: Record<string, string | boolean>; positionals: string[] }''',
        "code": r'''export function parseArgs(argv: string[]) {
  const flags: Record<string, string | boolean> = {};
  const positionals: string[] = [];
  for (const a of argv) {
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq >= 0) flags[a.slice(2, eq)] = a.slice(eq + 1);
      else flags[a.slice(2)] = true;
    } else if (a.startsWith('-') && a.length > 1) flags[a.slice(1)] = true;
    else positionals.push(a);
  }
  return { flags, positionals };
}''',
        "provides": "parseArgs(argv)",
        "depends": [],
    },
    {
        "id": "gen-version-bump",
        "name": "Semver Bump",
        "category": "gen",
        "lang": "typescript",
        "when": "Bumping a semantic version string by release type",
        "why": "Atomic bump — '1.2.3' + major|minor|patch in, next version string out",
        "tags": ["gen", "semver", "version", "bump", "release"],
        "iface": r'''export function bumpVersion(version: string, part: 'major' | 'minor' | 'patch'): string''',
        "code": r'''export function bumpVersion(version: string, part: 'major' | 'minor' | 'patch') {
  const [maj, min, patch] = version.split('.').map((n) => parseInt(n, 10) || 0);
  if (part === 'major') return `${maj + 1}.0.0`;
  if (part === 'minor') return `${maj}.${min + 1}.0`;
  return `${maj}.${min}.${patch + 1}`;
}''',
        "provides": "bumpVersion(version, part)",
        "depends": [],
    },
    {
        "id": "gen-env-default",
        "name": "Env Var Reader with Default",
        "category": "gen",
        "lang": "typescript",
        "when": "Reading config from env with typed defaults and validation",
        "why": "Atomic reader — name + default in, value out; number/boolean coercion",
        "tags": ["gen", "env", "config", "default", "reader"],
        "iface": r'''export function envOr(env: Record<string, string | undefined>, name: string, def: string): string
export function envInt(env: Record<string, string | undefined>, name: string, def: number): number
export function envBool(env: Record<string, string | undefined>, name: string, def: boolean): boolean''',
        "code": r'''export function envOr(env: Record<string, string | undefined>, name: string, def: string) { return env[name] ?? def; }
export function envInt(env: Record<string, string | undefined>, name: string, def: number) {
  const v = env[name]; return v === undefined || v === '' ? def : Number(v);
}
export function envBool(env: Record<string, string | undefined>, name: string, def: boolean) {
  const v = env[name]; if (v === undefined || v === '') return def;
  return v === '1' || v.toLowerCase() === 'true';
}''',
        "provides": "envOr / envInt / envBool",
        "depends": [],
    },
    {
        "id": "gen-ts-compile-error",
        "name": "TSC Error Normalizer",
        "category": "gen",
        "lang": "typescript",
        "when": "Parsing tsc output into structured file/line/code errors",
        "why": "Atomic parser — 'file.ts(12,3): error TS1234: msg' into objects",
        "tags": ["gen", "tsc", "error", "parse", "typescript"],
        "iface": r'''export interface TsError { file: string; line: number; col: number; code: string; message: string }
export function parseTscErrors(output: string): TsError[]''',
        "code": r'''export function parseTscErrors(output: string) {
  const out: TsError[] = [];
  const re = /^(.+?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.*)$/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(output))) out.push({ file: m[1], line: Number(m[2]), col: Number(m[3]), code: m[4], message: m[5] });
  return out;
}''',
        "provides": "parseTscErrors(output)",
        "depends": [],
    },
    {
        "id": "gen-hex-color",
        "name": "Hex Color Generator",
        "category": "gen",
        "lang": "typescript",
        "when": "Generating distinct hex colors for generated charts and components",
        "why": "Atomic palette — golden-angle hue stepping, deterministic, HSL→hex",
        "tags": ["gen", "color", "hex", "palette", "generate"],
        "iface": r'''export function colorForIndex(i: number, saturation = 65, lightness = 55): string''',
        "code": r'''function hslToHex(h: number, s: number, l: number) {
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const a = s * Math.min(l, 1 - l);
    return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, Math.min(9 - k, 1)))));
  };
  return `#${[f(0), f(8), f(4)].map((c) => c.toString(16).padStart(2, '0')).join('')}`;
}
export function colorForIndex(i: number, saturation = 65, lightness = 55) {
  return hslToHex((i * 137.508) % 360, saturation / 100, lightness / 100);
}''',
        "provides": "colorForIndex(i, saturation, lightness)",
        "depends": [],
    },
    {
        "id": "gen-progress-bar",
        "name": "ASCII Progress Bar",
        "category": "gen",
        "lang": "typescript",
        "when": "Rendering a text progress bar for generated-build output",
        "why": "Atomic renderer — pct + width in, framed bar string out",
        "tags": ["gen", "progress", "bar", "ascii", "render"],
        "iface": r'''export function progressBar(percent: number, width = 20): string''',
        "code": r'''export function progressBar(percent: number, width = 20) {
  const p = Math.max(0, Math.min(100, percent));
  const filled = Math.round((p / 100) * width);
  return '[' + '#'.repeat(filled) + '-'.repeat(width - filled) + `] ${p.toFixed(0)}%`;
}''',
        "provides": "progressBar(percent, width)",
        "depends": [],
    },
    {
        "id": "gen-file-tree",
        "name": "File Tree Renderer",
        "category": "gen",
        "lang": "typescript",
        "when": "Rendering a nested file list as an ASCII tree",
        "why": "Atomic renderer — paths in, '|- ' tree with sorted siblings out",
        "tags": ["gen", "tree", "files", "render", "ascii"],
        "iface": r'''export function renderTree(paths: string[]): string''',
        "code": r'''export function renderTree(paths: string[]) {
  const root: Record<string, unknown> = {};
  for (const p of paths) {
    let node = root;
    for (const part of p.split('/')) {
      if (part === '') continue;
      if (typeof node[part] !== 'object' || node[part] === null) node[part] = {};
      node = node[part] as Record<string, unknown>;
    }
  }
  const lines: string[] = [];
  const walk = (node: Record<string, unknown>, prefix: string, isRoot: boolean) => {
    const keys = Object.keys(node).sort();
    keys.forEach((k, i) => {
      const last = i === keys.length - 1;
      lines.push(prefix + (last ? '`- ' : '|- ') + k);
      walk(node[k] as Record<string, unknown>, prefix + (last ? '   ' : '|  '), false);
    });
  };
  walk(root, '', true);
  return lines.join('\n');
}''',
        "provides": "renderTree(paths)",
        "depends": [],
    },
    {
        "id": "gen-random-id",
        "name": "Random ID Generator",
        "category": "gen",
        "lang": "typescript",
        "when": "Generating collision-resistant string ids for generated entities",
        "why": "Atomic id — prefix + timestamp base36 + random suffix, no crypto required",
        "tags": ["gen", "random", "id", "unique", "generate"],
        "iface": r'''export function randomId(prefix = 'id'): string''',
        "code": r'''export function randomId(prefix = 'id') {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now().toString(36)}_${rand}`;
}''',
        "provides": "randomId(prefix)",
        "depends": [],
    },
    {
        "id": "gen-num-format",
        "name": "Number Formatter (SI suffix)",
        "category": "gen",
        "lang": "typescript",
        "when": "Formatting large generated metrics as 1.2K / 3.4M / 5.6B",
        "why": "Atomic formatter — value in, compact string with SI suffix out",
        "tags": ["gen", "number", "format", "si", "compact"],
        "iface": r'''export function formatCompact(value: number, decimals = 1): string''',
        "code": r'''export function formatCompact(value: number, decimals = 1) {
  const abs = Math.abs(value);
  const units = ['', 'K', 'M', 'B', 'T'];
  let u = 0;
  while (abs >= 1000 && u < units.length - 1) { value /= 1000; u++; }
  return `${value.toFixed(value >= 100 || u === 0 ? 0 : decimals)}${units[u]}`;
}''',
        "provides": "formatCompact(value, decimals)",
        "depends": [],
    },
    {
        "id": "gen-string-builder",
        "name": "String Builder",
        "category": "gen",
        "lang": "typescript",
        "when": "Accumulating generated code lines efficiently",
        "why": "Atomic builder \u2014 append/line/toString, join-once; no array concat churn",
        "tags": [
            "gen",
            "string",
            "builder",
            "accumulate",
            "lines"
        ],
        "iface": "export class StringBuilder {\n  line(text?: string): void\n  append(text: string): void\n  toString(): string\n  get length(): number\n}",
        "code": "export class StringBuilder {\n  private parts: string[] = [];\n  line(text = '') { this.parts.push(text + '\\n'); }\n  append(text: string) { this.parts.push(text); }\n  toString() { return this.parts.join(''); }\n  get length() { return this.parts.reduce((s, p) => s + p.length, 0); }\n}",
        "provides": "StringBuilder",
        "depends": []
    },
]
