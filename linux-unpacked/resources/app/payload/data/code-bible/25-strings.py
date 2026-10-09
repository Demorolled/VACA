# -*- coding: utf-8 -*-
"""
Code Bible — Category 25: Strings & Text Processing (atomic).
Convention: pure functions, no deps; Unicode-aware where stated.
"""
CHUNKS = [
    {
        "id": "str-slugify",
        "name": "Slugify",
        "category": "str",
        "lang": "typescript",
        "when": "Turning any title into a URL-safe lowercase slug",
        "why": "Atomic slugger — normalize, strip diacritics, replace spaces/dashes, keep [a-z0-9-]",
        "tags": ["str", "slug", "url", "normalize"],
        "iface": r'''export function slugify(text: string): string''',
        "code": r'''export function slugify(text: string) {
  return text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}''',
        "provides": "slugify(text)",
        "depends": [],
    },
    {
        "id": "str-case-converter",
        "name": "Case Converter",
        "category": "str",
        "lang": "typescript",
        "when": "Converting identifiers between camelCase / snake_case / kebab-case / PascalCase",
        "why": "Atomic case transducer — split once on boundaries, join in any convention",
        "tags": ["str", "case", "camel", "snake", "kebab", "pascal"],
        "iface": r'''export function toCamel(s: string): string
export function toSnake(s: string): string
export function toKebab(s: string): string
export function toPascal(s: string): string''',
        "code": r'''function words(s: string) {
  return s
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_\-\s]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
    .map((w) => w.toLowerCase());
}
const cap = (w: string) => w.charAt(0).toUpperCase() + w.slice(1);
export const toCamel = (s: string) => words(s).map((w, i) => (i ? cap(w) : w)).join('');
export const toSnake = (s: string) => words(s).join('_');
export const toKebab = (s: string) => words(s).join('-');
export const toPascal = (s: string) => words(s).map(cap).join('');''',
        "provides": "toCamel / toSnake / toKebab / toPascal",
        "depends": [],
    },
    {
        "id": "str-pluralize",
        "name": "Pluralizer",
        "category": "str",
        "lang": "typescript",
        "when": "Choosing singular/plural forms with common English rules + overrides",
        "why": "Atomic plural rule engine — irregular map first, then suffix rules, then default",
        "tags": ["str", "plural", "singular", "inflection", "english"],
        "iface": r'''export function pluralize(word: string, count?: number): string''',
        "code": r'''const IRREGULAR: Record<string, string> = {
  person: 'people', child: 'children', mouse: 'mice', foot: 'feet',
  tooth: 'teeth', goose: 'geese', ox: 'oxen', man: 'men', woman: 'women',
};
export function pluralize(word: string, count?: number) {
  if (count === 1) return word;
  if (IRREGULAR[word.toLowerCase()]) return IRREGULAR[word.toLowerCase()];
  if (/(s|x|z|ch|sh)$/i.test(word)) return word + 'es';
  if (/[^aeiou]y$/i.test(word)) return word.slice(0, -1) + 'ies';
  if (/fe?$/i.test(word) && !/^[a-z]+fe$/i.test(word)) return word.replace(/fe?$/, 'ves');
  return word + 's';
}''',
        "provides": "pluralize(word, count?)",
        "depends": [],
    },
    {
        "id": "str-truncate",
        "name": "Grapheme-Safe Truncate",
        "category": "str",
        "lang": "typescript",
        "when": "Truncating text without splitting emoji or surrogate pairs",
        "why": "Atomic Array.from truncation — iterates by code point, safe for multi-byte chars",
        "tags": ["str", "truncate", "grapheme", "unicode", "ellipsis"],
        "iface": r'''export function truncate(text: string, max: number, ellipsis = '…'): string''',
        "code": r'''export function truncate(text: string, max: number, ellipsis = '…') {
  if (max <= 0) return '';
  const chars = Array.from(text);
  if (chars.length <= max) return text;
  return chars.slice(0, Math.max(0, max - Array.from(ellipsis).length)).join('') + ellipsis;
}''',
        "provides": "truncate(text, max, ellipsis?)",
        "depends": [],
    },
    {
        "id": "str-pad",
        "name": "Pad String",
        "category": "str",
        "lang": "typescript",
        "when": "Padding to a target length on either side with any fill character",
        "why": "Atomic pad helper — code-point aware, center option, no native-only behavior",
        "tags": ["str", "pad", "align", "format"],
        "iface": r'''export function pad(s: string, length: number, fill = ' ', side: 'start' | 'end' | 'both' = 'start'): string''',
        "code": r'''export function pad(s: string, length: number, fill = ' ', side: 'start' | 'end' | 'both' = 'start') {
  const need = Math.max(0, length - Array.from(s).length);
  if (!need) return s;
  const f = fill.repeat(Math.ceil(need / fill.length)).slice(0, need);
  if (side === 'start') return f + s;
  if (side === 'end') return s + f;
  const half = Math.floor(f.length / 2);
  return f.slice(0, half) + s + f.slice(half);
}''',
        "provides": "pad(s, length, fill?, side?)",
        "depends": [],
    },
    {
        "id": "str-soundex",
        "name": "Soundex",
        "category": "str",
        "lang": "typescript",
        "when": "Encoding a name to its phonetic Soundex code for fuzzy matching",
        "why": "Atomic classic Soundex — consonant code + first letter, 4-char output",
        "tags": ["str", "soundex", "phonetic", "fuzzy", "name"],
        "iface": r'''export function soundex(name: string): string''',
        "code": r'''export function soundex(name: string) {
  const codes: Record<string, string> = {
    b: '1', f: '1', p: '1', v: '1', c: '2', g: '2', j: '2', k: '2', q: '2',
    s: '2', x: '2', z: '2', d: '3', t: '3', l: '4', m: '5', n: '5', r: '6',
  };
  const s = name.toUpperCase().replace(/[^A-Z]/g, '');
  if (!s) return '';
  let out = s[0];
  let prev = codes[s[0].toLowerCase()] ?? '';
  for (let i = 1; i < s.length && out.length < 4; i++) {
    const c = codes[s[i].toLowerCase()];
    if (c && c !== prev) out += c;
    if (s[i] !== 'H' && s[i] !== 'W') prev = c ?? '';
  }
  return (out + '000').slice(0, 4);
}''',
        "provides": "soundex(name)",
        "depends": [],
    },
    {
        "id": "str-metaphone",
        "name": "Metaphone",
        "category": "str",
        "lang": "typescript",
        "when": "Phonetic encoding more accurate than Soundex for English words",
        "why": "Atomic simplified Metaphone — consonant rules for approximate pronunciation matching",
        "tags": ["str", "metaphone", "phonetic", "fuzzy", "english"],
        "iface": r'''export function metaphone(word: string): string''',
        "code": r'''export function metaphone(word: string) {
  let s = word.toUpperCase().replace(/[^A-Z]/g, '');
  s = s.replace(/^KN/, 'N').replace(/^GN/, 'N').replace(/^PN/, 'N').replace(/^WR/, 'R');
  const out: string[] = [];
  for (let i = 0; i < s.length; i++) {
    const c = s[i], n = s[i + 1];
    if (c === n) continue;
    if ('AEIOU'.includes(c) && i === 0) { out.push(c); continue; }
    if (c === 'C') { out.push(n === 'I' || n === 'E' || n === 'Y' ? 'S' : 'K'); continue; }
    if (c === 'G') { out.push(n === 'I' || n === 'E' || n === 'Y' ? 'J' : 'K'); continue; }
    if ('AEIOU'.includes(c)) continue;
    if (c === 'H' && !'AEIOU'.includes(n ?? '')) continue;
    if (c === 'Q') { out.push('K'); continue; }
    if (c === 'X') { out.push('KS'); continue; }
    if (c === 'Y' && i === 0) continue;
    if (c === 'V') { out.push('F'); continue; }
    if (c === 'J') { out.push('J'); continue; }
    if (c === 'S' && n === 'H') { out.push('X'); i++; continue; }
    if (c === 'T' && n === 'H') { out.push('0'); i++; continue; }
    if (c === 'W' || c === 'K' || c === 'P' || c === 'B' || c === 'D' || c === 'F' || c === 'L' || c === 'M' || c === 'N' || c === 'R' || c === 'Z' || c === 'T') out.push(c === 'Z' ? 'S' : c);
  }
  return out.join('');
}''',
        "provides": "metaphone(word)",
        "depends": [],
    },
    {
        "id": "str-glob-match",
        "name": "Glob Matcher",
        "category": "str",
        "lang": "typescript",
        "when": "Matching a path against a glob pattern (*, **, ?)",
        "why": "Atomic glob → RegExp compiler — supports double-star recursion, dependency-free",
        "tags": ["str", "glob", "pattern", "match", "path"],
        "iface": r'''export function globMatch(pattern: string, path: string): boolean''',
        "code": r'''export function globMatch(pattern: string, path: string) {
  const memo = new Map<string, boolean>();
  const match = (p: number, s: number): boolean => {
    const key = p + ':' + s;
    if (memo.has(key)) return memo.get(key)!;
    let res: boolean;
    if (p === pattern.length) res = s === path.length;
    else if (pattern[p] === '*') {
      if (pattern[p + 1] === '*') {
        res = match(p + 2, s) || (s < path.length && match(p, s + 1));
      } else {
        res = match(p + 1, s) || (s < path.length && match(p, s + 1));
      }
    } else if (pattern[p] === '?') res = s < path.length && match(p + 1, s + 1);
    else res = s < path.length && pattern[p] === path[s] && match(p + 1, s + 1);
    memo.set(key, res);
    return res;
  };
  return match(0, 0);
}''',
        "provides": "globMatch(pattern, path)",
        "depends": [],
    },
    {
        "id": "str-wildcard",
        "name": "Wildcard Match",
        "category": "str",
        "lang": "typescript",
        "when": "Matching a string against a simple * and ? wildcard pattern",
        "why": "Atomic two-pointer wildcard match — single string, no path semantics",
        "tags": ["str", "wildcard", "match", "pattern", "search"],
        "iface": r'''export function wildcardMatch(pattern: string, text: string): boolean''',
        "code": r'''export function wildcardMatch(pattern: string, text: string) {
  let p = 0, s = 0, star = -1, mark = 0;
  while (s < text.length) {
    if (p < pattern.length && (pattern[p] === '?' || pattern[p] === text[s])) { p++; s++; }
    else if (p < pattern.length && pattern[p] === '*') { star = p++; mark = s; }
    else if (star !== -1) { p = star + 1; s = ++mark; }
    else return false;
  }
  while (p < pattern.length && pattern[p] === '*') p++;
  return p === pattern.length;
}''',
        "provides": "wildcardMatch(pattern, text)",
        "depends": [],
    },
    {
        "id": "str-levenshtein",
        "name": "Levenshtein Distance",
        "category": "str",
        "lang": "typescript",
        "when": "Edit distance between two strings (insert/delete/substitute) for fuzzy search",
        "why": "Atomic DP with rolling rows — O(n*m) time, O(min(n,m)) space",
        "tags": ["str", "levenshtein", "edit-distance", "fuzzy", "similarity"],
        "iface": r'''export function levenshtein(a: string, b: string): number''',
        "code": r'''export function levenshtein(a: string, b: string) {
  if (a.length < b.length) [a, b] = [b, a];
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(
        prev[j] + 1,
        cur[j - 1] + 1,
        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    prev = cur;
  }
  return prev[b.length];
}''',
        "provides": "levenshtein(a, b)",
        "depends": [],
    },
    {
        "id": "str-roman-numerals",
        "name": "Roman Numerals",
        "category": "str",
        "lang": "typescript",
        "when": "Converting between integers and Roman numeral strings",
        "why": "Atomic bidirectional converter — greedy subtractive pairs both ways",
        "tags": ["str", "roman", "numeral", "convert"],
        "iface": r'''export function toRoman(n: number): string
export function fromRoman(s: string): number''',
        "code": r'''const ROMAN: Array<[number, string]> = [
  [1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
  [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I'],
];
export function toRoman(n: number) {
  if (n <= 0 || n > 3999) throw new Error('Roman numerals support 1..3999');
  let out = '';
  for (const [v, sym] of ROMAN) while (n >= v) { out += sym; n -= v; }
  return out;
}
export function fromRoman(s: string) {
  const val: Record<string, number> = { I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000 };
  let total = 0;
  for (let i = 0; i < s.length; i++) {
    const v = val[s[i]] ?? 0;
    total += i + 1 < s.length && v < (val[s[i + 1]] ?? 0) ? -v : v;
  }
  return total;
}''',
        "provides": "toRoman / fromRoman",
        "depends": [],
    },
    {
        "id": "str-number-words",
        "name": "Number to Words",
        "category": "str",
        "lang": "typescript",
        "when": "Spelling an integer in English (e.g. 1234 -> one thousand two hundred thirty-four)",
        "why": "Atomic number speller — ones/tens/scales tables, handles 0 and negatives",
        "tags": ["str", "number", "words", "spell", "english"],
        "iface": r'''export function numberToWords(n: number): string''',
        "code": r'''const ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'];
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];
const SCALES = ['', 'thousand', 'million', 'billion', 'trillion'];
function three(n: number): string {
  const parts: string[] = [];
  if (n >= 100) { parts.push(ONES[Math.floor(n / 100)] + ' hundred'); n %= 100; }
  if (n >= 20) { parts.push(TENS[Math.floor(n / 10)] + (n % 10 ? '-' + ONES[n % 10] : '')); }
  else if (n > 0) parts.push(ONES[n]);
  return parts.join(' ');
}
export function numberToWords(n: number) {
  if (n === 0) return 'zero';
  const sign = n < 0 ? 'minus ' : '';
  n = Math.abs(n);
  const groups: string[] = [];
  let scale = 0;
  while (n > 0) { groups.push(three(n % 1000)); n = Math.floor(n / 1000); scale++; }
  const parts: string[] = [];
  for (let i = groups.length - 1; i >= 0; i--) {
    if (groups[i]) parts.push(groups[i] + (SCALES[i] ? ' ' + SCALES[i] : ''));
  }
  return sign + parts.join(' ');
}''',
        "provides": "numberToWords(n)",
        "depends": [],
    },
    {
        "id": "str-words-number",
        "name": "Words to Number",
        "category": "str",
        "lang": "typescript",
        "when": "Parsing English number phrases like 'two thousand three hundred'",
        "why": "Atomic phrase parser — handles scales and hyphenation, returns integer",
        "tags": ["str", "words", "number", "parse", "english"],
        "iface": r'''export function wordsToNumber(phrase: string): number | null''',
        "code": r'''const MAP: Record<string, number> = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9,
  ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16,
  seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20, thirty: 30, forty: 40, fifty: 50,
  sixty: 60, seventy: 70, eighty: 80, ninety: 90,
};
const SCALE: Record<string, number> = { hundred: 100, thousand: 1000, million: 1e6, billion: 1e9 };
export function wordsToNumber(phrase: string) {
  const tokens = phrase.toLowerCase().replace(/-/g, ' ').split(/\s+/).filter(Boolean);
  let current = 0, total = 0;
  for (const t of tokens) {
    if (t in MAP) current += MAP[t];
    else if (t in SCALE) {
      current = Math.max(current * SCALE[t], SCALE[t]);
      if (t !== 'hundred') { total += current; current = 0; }
    } else return null;
  }
  return total + current;
}''',
        "provides": "wordsToNumber(phrase)",
        "depends": [],
    },
    {
        "id": "str-natural-sort",
        "name": "Natural Sort",
        "category": "str",
        "lang": "typescript",
        "when": "Sorting strings so numbers sort numerically (file2 before file10)",
        "why": "Atomic digit-aware comparator — split runs into (num | str) parts, compare pairwise",
        "tags": ["str", "sort", "natural", "numeric", "comparator"],
        "iface": r'''export function naturalCompare(a: string, b: string): number
export function naturalSort<T>(items: T[], key?: (t: T) => string): T[]''',
        "code": r'''export function naturalCompare(a: string, b: string) {
  const pa = a.match(/\d+|\D+/g) ?? [a];
  const pb = b.match(/\d+|\D+/g) ?? [b];
  const n = Math.max(pa.length, pb.length);
  for (let i = 0; i < n; i++) {
    const x = pa[i], y = pb[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    const xn = /^\d+$/.test(x), yn = /^\d+$/.test(y);
    if (xn && yn) {
      const diff = x.length - y.length || x.localeCompare(y);
      if (diff) return diff;
    } else {
      const diff = x.localeCompare(y);
      if (diff) return diff;
    }
  }
  return 0;
}
export function naturalSort<T>(items: T[], key: (t: T) => string = (t) => String(t)) {
  return items.slice().sort((a, b) => naturalCompare(key(a), key(b)));
}''',
        "provides": "naturalCompare / naturalSort",
        "depends": [],
    },
    {
        "id": "str-unicode-normalize",
        "name": "Unicode Normalize",
        "category": "str",
        "lang": "typescript",
        "when": "Canonicalizing composed/decomposed Unicode (NFD/NFC/NFKD/NFKC)",
        "why": "Atomic normalize wrapper — NFC for storage, NFKD for search, NFKC for slugs",
        "tags": ["str", "unicode", "normalize", "nfc", "nfkd"],
        "iface": r'''export function normalizeUnicode(s: string, form: 'NFC' | 'NFD' | 'NFKC' | 'NFKD' = 'NFC'): string''',
        "code": r'''export function normalizeUnicode(s: string, form: 'NFC' | 'NFD' | 'NFKC' | 'NFKD' = 'NFC') {
  return s.normalize(form);
}''',
        "provides": "normalizeUnicode(s, form?)",
        "depends": [],
    },
    {
        "id": "str-diacritics",
        "name": "Diacritics Remover",
        "category": "str",
        "lang": "typescript",
        "when": "Stripping accents so 'café' matches 'cafe' in searches",
        "why": "Atomic NFD + combining-mark strip — accent-insensitive comparison base",
        "tags": ["str", "diacritics", "accents", "normalize", "search"],
        "iface": r'''export function removeDiacritics(s: string): string
export function accentFoldEqual(a: string, b: string): boolean''',
        "code": r'''export function removeDiacritics(s: string) {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}
export function accentFoldEqual(a: string, b: string) {
  return removeDiacritics(a).toLowerCase() === removeDiacritics(b).toLowerCase();
}''',
        "provides": "removeDiacritics / accentFoldEqual",
        "depends": [],
    },
    {
        "id": "str-interleave",
        "name": "String Interleave",
        "category": "str",
        "lang": "typescript",
        "when": "Merging strings character-by-character (checksums, obfuscation, columns)",
        "why": "Atomic zip of code points — handles unequal lengths by appending remainder",
        "tags": ["str", "interleave", "merge", "zip"],
        "iface": r'''export function interleave(...strings: string[]): string''',
        "code": r'''export function interleave(...strings: string[]) {
  const cols = strings.map((s) => Array.from(s));
  const max = Math.max(...cols.map((c) => c.length), 0);
  const out: string[] = [];
  for (let i = 0; i < max; i++) for (const col of cols) if (i < col.length) out.push(col[i]);
  return out.join('');
}''',
        "provides": "interleave(...strings)",
        "depends": [],
    },
    {
        "id": "str-indent",
        "name": "Indent Helper",
        "category": "str",
        "lang": "typescript",
        "when": "Indenting every line of a block by a prefix (codegen, logs, quotes)",
        "why": "Atomic line indenter — preserves trailing blank lines, takes any prefix",
        "tags": ["str", "indent", "block", "format"],
        "iface": r'''export function indent(text: string, prefix = '  '): string''',
        "code": r'''export function indent(text: string, prefix = '  ') {
  return text
    .split('\n')
    .map((line) => (line.length ? prefix + line : line))
    .join('\n');
}''',
        "provides": "indent(text, prefix?)",
        "depends": [],
    },
    {
        "id": "str-json-beautify",
        "name": "JSON Beautifier",
        "category": "str",
        "lang": "typescript",
        "when": "Pretty-printing JSON with configurable indent and key sorting",
        "why": "Atomic stable pretty-printer — sort keys option, compact toggle, parse guard",
        "tags": ["str", "json", "beautify", "pretty", "format"],
        "iface": r'''export function beautifyJson(raw: string, indent = 2, sortKeys = false): string''',
        "code": r'''export function beautifyJson(raw: string, indent = 2, sortKeys = false) {
  const parsed = JSON.parse(raw);
  const sort = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(sort);
    if (v && typeof v === 'object') {
      const o = v as Record<string, unknown>;
      return Object.keys(o).sort().reduce<Record<string, unknown>>((acc, k) => { acc[k] = sort(o[k]); return acc; }, {});
    }
    return v;
  };
  return JSON.stringify(sortKeys ? sort(parsed) : parsed, null, indent);
}''',
        "provides": "beautifyJson(raw, indent?, sortKeys?)",
        "depends": [],
    },
    {
        "id": "str-lorem",
        "name": "Lorem Ipsum Generator",
        "category": "str",
        "lang": "typescript",
        "when": "Generating placeholder copy for mockups and fixtures",
        "why": "Atomic seeded word-picker — deterministic with a seed, words/paragraphs API",
        "tags": ["str", "lorem", "placeholder", "generator", "fixture"],
        "iface": r'''export function loremIpsum(words: number, seed?: number): string''',
        "code": r'''const WORDS = 'lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua enim ad minim veniam quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo consequat'.split(' ');
export function loremIpsum(words: number, seed = 42) {
  let s = seed;
  const rand = () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
  const out: string[] = [];
  for (let i = 0; i < words; i++) {
    const w = WORDS[Math.floor(rand() * WORDS.length)];
    out.push(i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w);
  }
  return out.join(' ') + '.';
}''',
        "provides": "loremIpsum(words, seed?)",
        "depends": [],
    },
    {
        "id": "str-email-mask",
        "name": "Email Masquer",
        "category": "str",
        "lang": "typescript",
        "when": "Masking an email address for display/logging (j***@example.com)",
        "why": "Atomic PII masker — keeps domain, hides local part, handles malformed input",
        "tags": ["str", "email", "mask", "pii", "privacy"],
        "iface": r'''export function maskEmail(email: string): string''',
        "code": r'''export function maskEmail(email: string) {
  const at = email.indexOf('@');
  if (at <= 0) return '***';
  const local = email.slice(0, at);
  const domain = email.slice(at + 1);
  const shown = local.charAt(0) + '***';
  return `${shown}@${domain}`;
}''',
        "provides": "maskEmail(email)",
        "depends": [],
    },
    {
        "id": "str-compact-whitespace",
        "name": "Compact Whitespace",
        "category": "str",
        "lang": "typescript",
        "when": "Collapsing runs of whitespace and trimming for clean tokens",
        "why": "Atomic whitespace collapser — normalizes newlines/tabs/spaces to single spaces",
        "tags": ["str", "whitespace", "collapse", "trim", "normalize"],
        "iface": r'''export function compactWhitespace(s: string): string''',
        "code": r'''export function compactWhitespace(s: string) {
  return s.replace(/\s+/g, ' ').trim();
}''',
        "provides": "compactWhitespace(s)",
        "depends": [],
    },
    {
        "id": "str-initials",
        "name": "Initials / Abbreviation",
        "category": "str",
        "lang": "typescript",
        "when": "Deriving avatar initials or acronyms from names and phrases",
        "why": "Atomic initials picker — first letters of up to N significant words, upper-cased",
        "tags": ["str", "initials", "abbreviation", "avatar", "acronym"],
        "iface": r'''export function initials(name: string, max = 2): string''',
        "code": r'''export function initials(name: string, max = 2) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, max)
    .join('')
    .toUpperCase();
}''',
        "provides": "initials(name, max?)",
        "depends": [],
    },
    {
        "id": "str-title-case",
        "name": "Title Case",
        "category": "str",
        "lang": "typescript",
        "when": "Capitalizing significant words of a heading or label",
        "why": "Atomic title-caser — small-word exception list, hyphenated words both capitalized",
        "tags": ["str", "title", "case", "capitalize", "heading"],
        "iface": r'''export function titleCase(s: string): string''',
        "code": r'''const SMALL = new Set(['a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'if', 'in', 'nor', 'of', 'on', 'or', 'per', 'the', 'to', 'vs']);
export function titleCase(s: string) {
  const cap = (w: string) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
  return s
    .split(/\s+/)
    .map((w, i) => {
      if (!w) return w;
      if (i > 0 && SMALL.has(w.toLowerCase())) return w.toLowerCase();
      return w.includes('-') ? w.split('-').map(cap).join('-') : cap(w);
    })
    .join(' ');
}''',
        "provides": "titleCase(s)",
        "depends": [],
    },
    {
        "id": "str-delimiter-join",
        "name": "Delimiter Join / Split",
        "category": "str",
        "lang": "typescript",
        "when": "Joining parts with a delimiter or splitting on one, empty-safe",
        "why": "Atomic join/split pair that filters empties \u2014 no deps, deterministic",
        "tags": [
            "str",
            "join",
            "split",
            "delimiter",
            "concat"
        ],
        "iface": "export function joinNonEmpty(parts: string[], delimiter = ', '): string\nexport function splitKeepTrimmed(text: string, delimiter: string): string[]",
        "code": "export function joinNonEmpty(parts: string[], delimiter = ', ') {\n  return parts.filter((p) => p !== undefined && p !== null && p !== '').join(delimiter);\n}\nexport function splitKeepTrimmed(text: string, delimiter: string) {\n  return text.split(delimiter).map((p) => p.trim()).filter(Boolean);\n}",
        "provides": "joinNonEmpty / splitKeepTrimmed",
        "depends": []
    },
]
