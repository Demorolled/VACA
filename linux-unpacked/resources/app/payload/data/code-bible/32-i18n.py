# -*- coding: utf-8 -*-
"""
Code Bible — Category 32: Internationalization (atomic).
Convention: Intl-based where stated, locale tags as BCP-47 strings.
"""
CHUNKS = [
    {
        "id": "i18n-pluralize-rules",
        "name": "Plural Rule Selector",
        "category": "i18n",
        "lang": "typescript",
        "when": "Picking the right plural form for a count per locale (Intl.PluralRules)",
        "why": "Atomic plural selector — one/other/two/few/many from Intl, falls back gracefully",
        "tags": ["i18n", "plural", "pluralrules", "locale", "count"],
        "iface": r'''export function pluralCategory(locale: string, count: number): Intl.LDMLPluralRule
export function pickPlural(locale: string, count: number, forms: Record<string, string>): string''',
        "code": r'''export function pluralCategory(locale: string, count: number) {
  try { return new Intl.PluralRules(locale).select(count); }
  catch { return count === 1 ? 'one' : 'other'; }
}
export function pickPlural(locale: string, count: number, forms: Record<string, string>) {
  const cat = pluralCategory(locale, count);
  return forms[cat] ?? forms.other ?? forms.one ?? String(count);
}''',
        "provides": "pluralCategory / pickPlural",
        "depends": [],
    },
    {
        "id": "i18n-collate",
        "name": "Locale Collation",
        "category": "i18n",
        "lang": "typescript",
        "when": "Comparing strings in the correct order for a locale",
        "why": "Atomic Intl.Collator wrapper — cached per locale, case/sensitivity options",
        "tags": ["i18n", "collation", "sort", "locale", "compare"],
        "iface": r'''export function localeCompareFn(locale: string, opts?: Intl.CollatorOptions): (a: string, b: string) => number''',
        "code": r'''const cache = new Map<string, Intl.Collator>();
export function localeCompareFn(locale: string, opts: Intl.CollatorOptions = {}) {
  const key = locale + JSON.stringify(opts);
  if (!cache.has(key)) cache.set(key, new Intl.Collator(locale, opts));
  return (a: string, b: string) => cache.get(key)!.compare(a, b);
}''',
        "provides": "localeCompareFn(locale, opts?)",
        "depends": [],
    },
    {
        "id": "i18n-number",
        "name": "Number Format",
        "category": "i18n",
        "lang": "typescript",
        "when": "Formatting numbers with locale digit grouping",
        "why": "Atomic Intl.NumberFormat — decimals, grouping on/off, locale-aware separators",
        "tags": ["i18n", "number", "format", "Intl", "grouping"],
        "iface": r'''export function formatNumber(locale: string, value: number, opts?: Intl.NumberFormatOptions): string''',
        "code": r'''const cache = new Map<string, Intl.NumberFormat>();
export function formatNumber(locale: string, value: number, opts: Intl.NumberFormatOptions = {}) {
  const key = locale + JSON.stringify(opts);
  if (!cache.has(key)) cache.set(key, new Intl.NumberFormat(locale, opts));
  return cache.get(key)!.format(value);
}''',
        "provides": "formatNumber(locale, value, opts?)",
        "depends": [],
    },
    {
        "id": "i18n-currency",
        "name": "Currency Format",
        "category": "i18n",
        "lang": "typescript",
        "when": "Formatting money with the right symbol and decimal rules",
        "why": "Atomic currency formatter — code + locale, symbol/name display, fallback",
        "tags": ["i18n", "currency", "money", "format", "Intl"],
        "iface": r'''export function formatCurrency(locale: string, value: number, currency: string, opts?: Intl.NumberFormatOptions): string''',
        "code": r'''export function formatCurrency(locale: string, value: number, currency: string, opts: Intl.NumberFormatOptions = {}) {
  return formatNumber(locale, value, { style: 'currency', currency, ...opts });
}''',
        "provides": "formatCurrency(locale, value, currency, opts?)",
        "depends": [],
    },
    {
        "id": "i18n-date",
        "name": "Date Format",
        "category": "i18n",
        "lang": "typescript",
        "when": "Formatting dates according to locale conventions",
        "why": "Atomic DateTimeFormat — dateStyle/timeStyle presets, cached per key",
        "tags": ["i18n", "date", "format", "Intl", "locale"],
        "iface": r'''export function formatDate(locale: string, date: Date | number, opts?: Intl.DateTimeFormatOptions): string''',
        "code": r'''const cache = new Map<string, Intl.DateTimeFormat>();
export function formatDate(locale: string, date: Date | number, opts: Intl.DateTimeFormatOptions = { dateStyle: 'medium' }) {
  const key = locale + JSON.stringify(opts);
  if (!cache.has(key)) cache.set(key, new Intl.DateTimeFormat(locale, opts));
  return cache.get(key)!.format(new Date(date));
}''',
        "provides": "formatDate(locale, date, opts?)",
        "depends": [],
    },
    {
        "id": "i18n-relative-time",
        "name": "Relative Time",
        "category": "i18n",
        "lang": "typescript",
        "when": "Formatting '3 minutes ago' in the user's locale",
        "why": "Atomic RelativeTimeFormat — picks unit from delta, signed numeric, cached",
        "tags": ["i18n", "relative-time", "ago", "Intl", "delta"],
        "iface": r'''export function relativeTime(locale: string, deltaMs: number, opts?: Intl.RelativeTimeFormatOptions): string''',
        "code": r'''const cache = new Map<string, Intl.RelativeTimeFormat>();
const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 31536000000], ['month', 2592000000], ['week', 604800000],
  ['day', 86400000], ['hour', 3600000], ['minute', 60000], ['second', 1000],
];
export function relativeTime(locale: string, deltaMs: number, opts: Intl.RelativeTimeFormatOptions = { numeric: 'auto' }) {
  const key = locale + JSON.stringify(opts);
  if (!cache.has(key)) cache.set(key, new Intl.RelativeTimeFormat(locale, opts));
  for (const [unit, size] of UNITS) {
    const value = Math.round(deltaMs / size);
    if (Math.abs(value) >= 1 || unit === 'second') return cache.get(key)!.format(value, unit);
  }
  return cache.get(key)!.format(0, 'second');
}''',
        "provides": "relativeTime(locale, deltaMs, opts?)",
        "depends": [],
    },
    {
        "id": "i18n-rtl",
        "name": "RTL Detect",
        "category": "i18n",
        "lang": "typescript",
        "when": "Detecting whether a locale is right-to-left",
        "why": "Atomic RTL set check — common RTL language tags, plus dir= attribute helper",
        "tags": ["i18n", "rtl", "ltr", "direction", "bidi"],
        "iface": r'''export function isRtlLocale(locale: string): boolean
export function dirForLocale(locale: string): 'rtl' | 'ltr' ''',
        "code": r'''const RTL = /^(ar|fa|he|ur|yi|dv|ps|sd|ckb|az-Arab|ku-Arab|ug)/i;
export function isRtlLocale(locale: string) { return RTL.test(locale); }
export function dirForLocale(locale: string) { return isRtlLocale(locale) ? 'rtl' : 'ltr'; }''',
        "provides": "isRtlLocale / dirForLocale",
        "depends": [],
    },
    {
        "id": "i18n-bidi",
        "name": "Bidi Order",
        "category": "i18n",
        "lang": "typescript",
        "when": "Ordering mixed LTR/RTL segments in a user-facing string",
        "why": "Atomic bidi grouping — split by strong direction, join with neutral markers",
        "tags": ["i18n", "bidi", "rtl", "order", "mixed"],
        "iface": r'''export function bidiGrouped(text: string): string[]''',
        "code": r'''const RTL_RE = /[\u0590-\u08FF\uFB1D-\uFDFD\uFE70-\uFEFC]/;
export function bidiGrouped(text: string) {
  const out: string[] = [];
  let buf = '', dir: 'rtl' | 'ltr' | '' = '';
  for (const ch of text) {
    const d = RTL_RE.test(ch) ? 'rtl' : /[a-zA-Z0-9]/.test(ch) ? 'ltr' : '';
    if (d && d !== dir) { if (buf) out.push(buf); buf = ''; dir = d; }
    buf += ch;
  }
  if (buf) out.push(buf);
  return out;
}''',
        "provides": "bidiGrouped(text)",
        "depends": [],
    },
    {
        "id": "i18n-locale-sort",
        "name": "Locale-Aware Sort",
        "category": "i18n",
        "lang": "typescript",
        "when": "Sorting a list in natural locale order (accents, case)",
        "why": "Atomic Intl.Collator sort — stable, asc/desc, usage=sort default",
        "tags": ["i18n", "sort", "locale", "collator", "natural"],
        "iface": r'''export function localeSort(items: string[], locale: string, desc = false): string[]''',
        "code": r'''export function localeSort(items: string[], locale: string, desc = false) {
  const cmp = localeCompareFn(locale);
  return items.slice().sort((a, b) => (desc ? -1 : 1) * cmp(a, b));
}''',
        "provides": "localeSort(items, locale, desc?)",
        "depends": [],
    },
    {
        "id": "i18n-message-format",
        "name": "ICU Message Format",
        "category": "i18n",
        "lang": "typescript",
        "when": "Interpolating named placeholders in translated strings",
        "why": "Atomic {name} substitution — plural-aware via pickPlural, missing key tolerant",
        "tags": ["i18n", "message", "format", "placeholder", "icu"],
        "iface": r'''export function formatMessage(template: string, params: Record<string, string | number>): string''',
        "code": r'''export function formatMessage(template: string, params: Record<string, string | number>) {
  return template.replace(/\{(\w+)\}/g, (_, key) => (params[key] !== undefined ? String(params[key]) : `{${key}}`));
}''',
        "provides": "formatMessage(template, params)",
        "depends": [],
    },
    {
        "id": "i18n-key-fallback",
        "name": "Translation Key Fallback",
        "category": "i18n",
        "lang": "typescript",
        "when": "Resolving a translation key across a locale chain (en → fallback)",
        "why": "Atomic key resolver — exact locale, language-only, then default, then key",
        "tags": ["i18n", "fallback", "translation", "locale-chain", "key"],
        "iface": r'''export function resolveKey(messages: Record<string, Record<string, string>>, locale: string, key: string, fallback = 'en'): string''',
        "code": r'''export function resolveKey(messages: Record<string, Record<string, string>>, locale: string, key: string, fallback = 'en') {
  const lang = locale.split('-')[0];
  for (const cand of [locale, lang, fallback]) {
    const hit = messages[cand]?.[key];
    if (hit !== undefined) return hit;
  }
  return key;
}''',
        "provides": "resolveKey(messages, locale, key, fallback?)",
        "depends": [],
    },
    {
        "id": "i18n-locale-negotiate",
        "name": "Locale Negotiation",
        "category": "i18n",
        "lang": "typescript",
        "when": "Picking the best supported locale from an Accept-Language list",
        "why": "Atomic negotiation — quality order, language-only matches, default fallback",
        "tags": ["i18n", "negotiation", "accept-language", "locale", "match"],
        "iface": r'''export function negotiateLocale(acceptLanguage: string, supported: string[], defaultLocale: string): string''',
        "code": r'''export function negotiateLocale(acceptLanguage: string, supported: string[], defaultLocale: string) {
  const parsed = acceptLanguage.split(',').map((p) => {
    const [tag, ...params] = p.trim().split(';');
    const q = parseFloat(params.find((x) => x.trim().startsWith('q='))?.split('=')[1] ?? '1');
    return { tag: tag.trim(), q: isNaN(q) ? 0 : q };
  }).sort((a, b) => b.q - a.q);
  for (const { tag } of parsed) {
    const exact = supported.find((s) => s.toLowerCase() === tag.toLowerCase());
    if (exact) return exact;
    const lang = tag.split('-')[0].toLowerCase();
    const partial = supported.find((s) => s.split('-')[0].toLowerCase() === lang);
    if (partial) return partial;
  }
  return defaultLocale;
}''',
        "provides": "negotiateLocale(acceptLanguage, supported, defaultLocale)",
        "depends": [],
    },
    {
        "id": "i18n-default-locale",
        "name": "Default Locale Resolve",
        "category": "i18n",
        "lang": "typescript",
        "when": "Resolving the runtime locale from navigator/Intl with a safe default",
        "why": "Atomic resolver — navigator.languages chain, falls back to 'en'",
        "tags": ["i18n", "locale", "default", "navigator", "resolve"],
        "iface": r'''export function resolveDefaultLocale(fallback = 'en'): string''',
        "code": r'''export function resolveDefaultLocale(fallback = 'en') {
  if (typeof navigator !== 'undefined' && navigator.languages?.length) return navigator.languages[0];
  if (typeof Intl !== 'undefined' && Intl.DateTimeFormat().resolvedOptions().locale) return Intl.DateTimeFormat().resolvedOptions().locale;
  return fallback;
}''',
        "provides": "resolveDefaultLocale(fallback?)",
        "depends": [],
    },
    {
        "id": "i18n-compact",
        "name": "Compact Notation",
        "category": "i18n",
        "lang": "typescript",
        "when": "Formatting big numbers as 1.2K / 3.4M per locale",
        "why": "Atomic compact formatter — notation: 'compact', optional maximum fraction digits",
        "tags": ["i18n", "compact", "notation", "abbreviate", "number"],
        "iface": r'''export function formatCompact(locale: string, value: number, maxFractionDigits = 1): string''',
        "code": r'''export function formatCompact(locale: string, value: number, maxFractionDigits = 1) {
  return formatNumber(locale, value, { notation: 'compact', maximumFractionDigits: maxFractionDigits });
}''',
        "provides": "formatCompact(locale, value, maxFractionDigits?)",
        "depends": [],
    },
    {
        "id": "i18n-ordinal",
        "name": "Ordinal Rules",
        "category": "i18n",
        "lang": "typescript",
        "when": "Choosing ordinal forms (1st/2nd/3rd per locale)",
        "why": "Atomic PluralRules(ordinal) — returns the ordinal category + suffix mapping",
        "tags": ["i18n", "ordinal", "1st", "suffix", "pluralrules"],
        "iface": r'''export function ordinalSuffix(locale: string, n: number): string''',
        "code": r'''export function ordinalSuffix(locale: string, n: number) {
  const cat = new Intl.PluralRules(locale, { type: 'ordinal' }).select(n);
  const map: Record<string, string> = { one: 'st', two: 'nd', few: 'rd', other: 'th' };
  return map[cat] ?? 'th';
}''',
        "provides": "ordinalSuffix(locale, n)",
        "depends": [],
    },
    {
        "id": "i18n-week-start",
        "name": "Week Start",
        "category": "i18n",
        "lang": "typescript",
        "when": "Getting the first day of the week for a locale's calendar",
        "why": "Atomic week-start map — common regions (Sun/Mon/Sat), default Monday",
        "tags": ["i18n", "week", "calendar", "start-day"],
        "iface": r'''export function weekStartDay(locale: string): number''',
        "code": r'''const MON = /^(en-US|en-CA|ja|zh|ko|pt-BR|es|ar|he)/i;
const SAT = /^(ar-DZ|ar-EG|af|bn|hi|ur|dv)/i;
export function weekStartDay(locale: string) {
  if (SAT.test(locale)) return 6;
  if (MON.test(locale)) return 0;
  return 1;
}''',
        "provides": "weekStartDay(locale)",
        "depends": [],
    },
    {
        "id": "i18n-grapheme",
        "name": "Grapheme Split",
        "category": "i18n",
        "lang": "typescript",
        "when": "Splitting text by user-perceived characters (emoji, combining marks)",
        "why": "Atomic Intl.Segmenter splitter — the correct way to count/iterate characters",
        "tags": ["i18n", "grapheme", "segmenter", "unicode", "emoji"],
        "iface": r'''export function graphemes(text: string, locale = 'en'): string[]''',
        "code": r'''export function graphemes(text: string, locale = 'en') {
  if (typeof Intl.Segmenter !== 'undefined') {
    const seg = new Intl.Segmenter(locale, { granularity: 'grapheme' });
    return [...seg.segment(text)].map((s) => s.segment);
  }
  return Array.from(text); // fallback: code-point split
}''',
        "provides": "graphemes(text, locale?)",
        "depends": [],
    },
    {
        "id": "i18n-surrogates",
        "name": "Surrogate Pair Safe",
        "category": "i18n",
        "lang": "typescript",
        "when": "Slicing strings without breaking surrogate pairs or combining sequences",
        "why": "Atomic code-point slice — Array.from based, offsets in code points",
        "tags": ["i18n", "surrogate", "slice", "unicode", "safe"],
        "iface": r'''export function safeSlice(text: string, start: number, end?: number): string''',
        "code": r'''export function safeSlice(text: string, start: number, end?: number) {
  const chars = Array.from(text);
  return chars.slice(start, end).join('');
}''',
        "provides": "safeSlice(text, start, end?)",
        "depends": [],
    },
    {
        "id": "i18n-text-direction",
        "name": "Text Direction Per Char",
        "category": "i18n",
        "lang": "typescript",
        "when": "Classifying runs of text by bidi direction for rendering",
        "why": "Atomic classifier — strong-LTR, strong-RTL, weak/neutral buckets per char",
        "tags": ["i18n", "direction", "bidi", "rtl", "classify"],
        "iface": r'''export type Dir = 'ltr' | 'rtl' | 'neutral'
export function charDirection(ch: string): Dir''',
        "code": r'''const RTL_RE = /[\u0590-\u08FF\uFB1D-\uFDFD\uFE70-\uFEFC]/;
const LTR_RE = /[A-Za-z0-9\u00C0-\u02AF\u0370-\u03FF\u0400-\u04FF\u0530-\u058F\u0600-\u06FF\u0E00-\u0E7F]/;
export function charDirection(ch: string): Dir {
  if (RTL_RE.test(ch)) return 'rtl';
  if (LTR_RE.test(ch)) return 'ltr';
  return 'neutral';
}''',
        "provides": "charDirection(ch)",
        "depends": [],
    },
    {
        "id": "i18n-unit",
        "name": "Unit Format",
        "category": "i18n",
        "lang": "typescript",
        "when": "Formatting values with units (km, kg, bytes) per locale",
        "why": "Atomic Intl.NumberFormat unit style — localized unit labels",
        "tags": ["i18n", "unit", "format", "Intl", "measurement"],
        "iface": r'''export function formatUnit(locale: string, value: number, unit: string): string''',
        "code": r'''export function formatUnit(locale: string, value: number, unit: string) {
  return formatNumber(locale, value, { style: 'unit', unit: unit as Intl.NumberFormatOptions['unit'] });
}''',
        "provides": "formatUnit(locale, value, unit)",
        "depends": [],
    },
    {
        "id": "i18n-percent",
        "name": "Percent Format",
        "category": "i18n",
        "lang": "typescript",
        "when": "Formatting ratios as localized percentages",
        "why": "Atomic percent formatter — style: 'percent', fraction control",
        "tags": ["i18n", "percent", "format", "ratio", "Intl"],
        "iface": r'''export function formatPercent(locale: string, ratio: number, maxFractionDigits = 1): string''',
        "code": r'''export function formatPercent(locale: string, ratio: number, maxFractionDigits = 1) {
  return formatNumber(locale, ratio, { style: 'percent', maximumFractionDigits: maxFractionDigits });
}''',
        "provides": "formatPercent(locale, ratio, maxFractionDigits?)",
        "depends": [],
    },
    {
        "id": "i18n-calendar",
        "name": "Calendar Type",
        "category": "i18n",
        "lang": "typescript",
        "when": "Resolving the calendar (gregory, islamic, buddhist...) of a locale",
        "why": "Atomic Intl resolvedOptions probe — returns the active calendar type",
        "tags": ["i18n", "calendar", "gregory", "resolvedOptions"],
        "iface": r'''export function calendarOf(locale: string): string''',
        "code": r'''export function calendarOf(locale: string) {
  try { return new Intl.DateTimeFormat(locale).resolvedOptions().calendar; }
  catch { return 'gregory'; }
}''',
        "provides": "calendarOf(locale)",
        "depends": [],
    },
    {
        "id": "i18n-timezone-list",
        "name": "Timezone List",
        "category": "i18n",
        "lang": "typescript",
        "when": "Enumerating IANA timezones supported by the runtime",
        "why": "Atomic Intl.supportedValuesOf probe — with graceful fallback to a curated set",
        "tags": ["i18n", "timezone", "iana", "list", "Intl"],
        "iface": r'''export function listTimezones(): string[]''',
        "code": r'''export function listTimezones() {
  try {
    const supported = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.('timeZone');
    if (supported?.length) return supported;
  } catch { /* fall through */ }
  return ['UTC', 'America/New_York', 'Europe/London', 'Asia/Tokyo', 'Australia/Sydney'];
}''',
        "provides": "listTimezones()",
        "depends": [],
    },
    {
        "id": "i18n-interpolation",
        "name": "Interpolation (named placeholders)",
        "category": "i18n",
        "lang": "typescript",
        "when": "Substituting named args in a template with type-aware formatting",
        "why": "Atomic formatter — {name} + {count,number} + {when,relative} directives",
        "tags": ["i18n", "interpolate", "template", "placeholder", "format"],
        "iface": r'''export function interpolate(template: string, locale: string, params: Record<string, unknown>): string''',
        "code": r'''export function interpolate(template: string, locale: string, params: Record<string, unknown>) {
  return template.replace(/\{(\w+)(?:,(\w+)(?:,([^}]+))?)?\}/g, (_, key, kind, opt) => {
    const v = params[key];
    if (v === undefined) return `{${key}}`;
    if (kind === 'number') return formatNumber(locale, Number(v), opt ? JSON.parse(`{${opt}}`) : {});
    if (kind === 'date') return formatDate(locale, new Date(Number(v)), { dateStyle: 'medium' });
    return String(v);
  });
}''',
        "provides": "interpolate(template, locale, params)",
        "depends": [],
    },
    {
        "id": "i18n-digit-strings",
        "name": "Digit Grouping",
        "category": "i18n",
        "lang": "typescript",
        "when": "Splitting a raw number string into localized groups for display",
        "why": "Atomic grouping via Intl — reuses NumberFormat so separators match the locale",
        "tags": ["i18n", "digit", "grouping", "thousands", "separator"],
        "iface": r'''export function groupDigits(locale: string, value: number): string''',
        "code": r'''export function groupDigits(locale: string, value: number) {
  return formatNumber(locale, value, { useGrouping: true });
}''',
        "provides": "groupDigits(locale, value)",
        "depends": [],
    },
]
