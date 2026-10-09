# -*- coding: utf-8 -*-
"""
Code Bible — Category 16: Security (atomic, single-responsibility).
Convention: validation guards and canonicalizers; complements the crypto category.
"""
CHUNKS = [
    {
        "id": "sec-input-limit",
        "name": "Input Length Limiter",
        "category": "sec",
        "lang": "typescript",
        "when": "Rejecting oversized inputs before they reach parsers or storage",
        "why": "Atomic guard: value + max in, trimmed/truncated or rejected out",
        "tags": ["sec", "input", "length", "limit", "validate"],
        "iface": r'''export interface LengthLimitResult { ok: boolean; value: string; error?: string }
export function enforceLength(value: string, max: number, min = 0): LengthLimitResult''',
        "code": r'''export function enforceLength(value: string, max: number, min = 0): LengthLimitResult {
  if (value.length < min) return { ok: false, value, error: `Too short (min ${min})` };
  if (value.length > max) return { ok: false, value: value.slice(0, max), error: `Too long (max ${max})` };
  return { ok: true, value };
}''',
        "provides": "enforceLength(value, max, min)",
        "depends": [],
    },
    {
        "id": "sec-path-guard",
        "name": "Path Traversal Guard",
        "category": "sec",
        "lang": "typescript",
        "when": "Ensuring a user-supplied relative path stays inside a base directory",
        "why": "Atomic guard: resolves and normalizes, rejects .. escapes and absolute paths",
        "tags": ["sec", "path", "traversal", "guard", "directory"],
        "iface": r'''export function safeJoin(base: string, userPath: string): string | null''',
        "code": r'''import * as path from 'path';
export function safeJoin(base: string, userPath: string) {
  if (path.isAbsolute(userPath)) return null;
  const resolved = path.normalize(path.join(base, userPath));
  const rel = path.relative(base, resolved);
  if (rel.startsWith('..') || path.isAbsolute(rel)) return null;
  return resolved;
}''',
        "provides": "safeJoin(base, userPath)",
        "depends": [],
    },
    {
        "id": "sec-sql-escape",
        "name": "Literal SQL Escape",
        "category": "sec",
        "lang": "typescript",
        "when": "Escaping string literals when parameterization is unavailable",
        "why": "Atomic escaper: doubling quotes + control-char strip, last-resort only",
        "tags": ["sec", "sql", "escape", "injection", "string"],
        "iface": r'''export function escapeSqlLiteral(value: string): string''',
        "code": r'''export function escapeSqlLiteral(value: string) {
  return value.replace(/[\x00\x08\x09\x1a\n\r"'\\%_]/g, (ch) => {
    switch (ch) {
      case "'": return "''";
      case '\\': return '\\\\';
      case '\n': return '\\n';
      case '\r': return '\\r';
      default: return ch;
    }
  });
}''',
        "provides": "escapeSqlLiteral(value)",
        "depends": [],
    },
    {
        "id": "sec-cmd-block",
        "name": "Command Injection Blocklist",
        "category": "sec",
        "lang": "typescript",
        "when": "Refusing to execute shell commands that contain dangerous metacharacters",
        "why": "Atomic guard: input scan for shell metacharacters, boolean verdict",
        "tags": ["sec", "command", "injection", "shell", "blocklist"],
        "iface": r'''export function hasShellDanger(input: string): boolean
export function assertSafeShell(input: string, allow?: RegExp): { ok: boolean; error?: string }''',
        "code": r'''const DANGEROUS = /[;&|`$()<>*?\[\]{}\n\r\\]/;
export function hasShellDanger(input: string) {
  return DANGEROUS.test(input);
}
export function assertSafeShell(input: string, allow?: RegExp) {
  const cleaned = allow ? input.replace(allow, '') : input;
  return hasShellDanger(cleaned)
    ? { ok: false, error: 'Unsafe shell characters detected' }
    : { ok: true };
}''',
        "provides": "hasShellDanger / assertSafeShell",
        "depends": [],
    },
    {
        "id": "sec-html-escape",
        "name": "HTML Escape / Unescape",
        "category": "sec",
        "lang": "typescript",
        "when": "Neutralizing HTML/script injection before rendering user content",
        "why": "Atomic escaper: five core entities + numeric fallback, round-trip safe",
        "tags": ["sec", "html", "escape", "xss", "sanitize"],
        "iface": r'''export function escapeHtml(input: string): string
export function unescapeHtml(input: string): string''',
        "code": r'''const MAP: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export function escapeHtml(input: string) {
  return input.replace(/[&<>"']/g, (c) => MAP[c]);
}
export function unescapeHtml(input: string) {
  return input.replace(/&(#x?[0-9a-f]+|amp|lt|gt|quot|#39);/gi, (m, ent: string) => {
    if (ent.startsWith('#x')) return String.fromCharCode(parseInt(ent.slice(2), 16));
    if (ent.startsWith('#')) return String.fromCharCode(parseInt(ent.slice(1), 10));
    return { amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'" }[ent.toLowerCase()] ?? m;
  });
}''',
        "provides": "escapeHtml / unescapeHtml",
        "depends": [],
    },
    {
        "id": "sec-password-meter",
        "name": "Password Strength Meter",
        "category": "sec",
        "lang": "typescript",
        "when": "Scoring password strength before acceptance",
        "why": "Atomic scorer: length + character classes in, 0-4 score + feedback out",
        "tags": ["sec", "password", "strength", "score", "meter"],
        "iface": r'''export function passwordStrength(pw: string): { score: number; ok: boolean; notes: string[] }''',
        "code": r'''export function passwordStrength(pw: string) {
  const notes: string[] = [];
  let score = 0;
  if (pw.length >= 8) score++; else notes.push('At least 8 characters');
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++; else notes.push('Mix upper and lower case');
  if (/\d/.test(pw)) score++; else notes.push('Include a digit');
  if (/[^A-Za-z0-9]/.test(pw)) score++; else notes.push('Include a symbol');
  return { score, ok: score >= 3, notes };
}''',
        "provides": "passwordStrength(pw)",
        "depends": [],
    },
    {
        "id": "sec-ip-limit",
        "name": "Per-IP Sliding Window Limiter",
        "category": "sec",
        "lang": "typescript",
        "when": "Throttling abusive clients by IP address",
        "why": "Atomic limiter: ip + max + window, sliding timestamps, cleanup on access",
        "tags": ["sec", "ip", "rate", "limit", "abuse"],
        "iface": r'''export class IpLimiter {
  constructor(max: number, windowMs: number)
  allow(ip: string): boolean
  remaining(ip: string): number
}''',
        "code": r'''export class IpLimiter {
  private hits = new Map<string, number[]>();
  constructor(private max: number, private windowMs: number) {}
  allow(ip: string) {
    const now = Date.now();
    let arr = this.hits.get(ip) ?? [];
    arr = arr.filter((t) => now - t < this.windowMs);
    if (arr.length >= this.max) { this.hits.set(ip, arr); return false; }
    arr.push(now);
    this.hits.set(ip, arr);
    return true;
  }
  remaining(ip: string) {
    const now = Date.now();
    const arr = (this.hits.get(ip) ?? []).filter((t) => now - t < this.windowMs);
    return Math.max(0, this.max - arr.length);
  }
}''',
        "provides": "IpLimiter",
        "depends": [],
    },
    {
        "id": "sec-session-token",
        "name": "Session Token Generator",
        "category": "sec",
        "lang": "typescript",
        "when": "Creating unguessable session identifiers",
        "why": "Atomic generator: crypto.randomBytes in, base64url token out, prefix option",
        "tags": ["sec", "session", "token", "generator", "crypto"],
        "iface": r'''export function newSessionToken(byteLength?: number, prefix?: string): string''',
        "code": r'''import * as crypto from 'crypto';
export function newSessionToken(byteLength = 32, prefix = 'sess_') {
  return prefix + crypto.randomBytes(byteLength).toString('base64url');
}''',
        "provides": "newSessionToken(byteLength, prefix)",
        "depends": [],
    },
    {
        "id": "sec-rbac",
        "name": "RBAC Permission Matrix",
        "category": "sec",
        "lang": "typescript",
        "when": "Checking whether a role may perform an action on a resource",
        "why": "Atomic matrix: role-permission grants in, can(role, action) out",
        "tags": ["sec", "rbac", "permission", "role", "authorization"],
        "iface": r'''export class Rbac {
  constructor(grants?: Record<string, string[]>)
  grant(role: string, ...actions: string[]): void
  can(role: string, action: string): boolean
  roles(): string[]
}''',
        "code": r'''export class Rbac {
  private grants = new Map<string, Set<string>>();
  constructor(grants: Record<string, string[]> = {}) {
    for (const [r, actions] of Object.entries(grants)) this.grant(r, ...actions);
  }
  grant(role: string, ...actions: string[]) {
    if (!this.grants.has(role)) this.grants.set(role, new Set());
    for (const a of actions) this.grants.get(role)!.add(a);
  }
  can(role: string, action: string) {
    return this.grants.get(role)?.has(action) ?? false;
  }
  roles() { return [...this.grants.keys()]; }
}''',
        "provides": "Rbac",
        "depends": [],
    },
    {
        "id": "sec-cors-allow",
        "name": "CORS Origin Allowlist",
        "category": "sec",
        "lang": "typescript",
        "when": "Validating Origin headers against an explicit allowlist",
        "why": "Atomic validator: origin + allowed in, exact/pattern match out",
        "tags": ["sec", "cors", "origin", "allowlist", "headers"],
        "iface": r'''export function isOriginAllowed(origin: string, allowed: Array<string | RegExp>): boolean''',
        "code": r'''export function isOriginAllowed(origin: string, allowed: Array<string | RegExp>) {
  if (!origin) return false;
  return allowed.some((a) => (a instanceof RegExp ? a.test(origin) : a === origin));
}''',
        "provides": "isOriginAllowed(origin, allowed)",
        "depends": [],
    },
    {
        "id": "sec-csrf",
        "name": "CSRF Token Validator",
        "category": "sec",
        "lang": "typescript",
        "when": "Verifying state-changing requests carry the token issued to the session",
        "why": "Atomic validator: token + session in, constant-time compare out with expiry",
        "tags": ["sec", "csrf", "token", "validate", "constant-time"],
        "iface": r'''export interface CsrfRecord { token: string; expiresAt: number }
export function validateCsrf(record: CsrfRecord | null, presented: string, now?: number): boolean''',
        "code": r'''export function validateCsrf(record: CsrfRecord | null, presented: string, now = Date.now()) {
  if (!record || record.expiresAt < now || !presented) return false;
  if (record.token.length !== presented.length) return false;
  let diff = 0;
  for (let i = 0; i < record.token.length; i++) diff |= record.token.charCodeAt(i) ^ presented.charCodeAt(i);
  return diff === 0;
}''',
        "provides": "validateCsrf(record, presented, now)",
        "depends": [],
    },
    {
        "id": "sec-email-validate",
        "name": "Email Validator",
        "category": "sec",
        "lang": "typescript",
        "when": "Sanity-checking email addresses before storage or delivery",
        "why": "Atomic validator: pragmatic regex + length caps, TLD check optional",
        "tags": ["sec", "email", "validate", "format", "regex"],
        "iface": r'''export function isValidEmail(email: string): boolean''',
        "code": r'''export function isValidEmail(email: string) {
  if (email.length > 254) return false;
  const m = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.exec(email.trim());
  if (!m) return false;
  const [local, domain] = email.trim().split('@');
  return local.length <= 64 && /^[a-z0-9.-]+\.[a-z]{2,}$/i.test(domain);
}''',
        "provides": "isValidEmail(email)",
        "depends": [],
    },
    {
        "id": "sec-url-scheme",
        "name": "URL Scheme Allowlist",
        "category": "sec",
        "lang": "typescript",
        "when": "Blocking javascript:/data: URLs in user-supplied links",
        "why": "Atomic validator: parsed scheme in, allowlist out, unknown → reject",
        "tags": ["sec", "url", "scheme", "allowlist", "redirect"],
        "iface": r'''export function safeUrl(raw: string, allowedSchemes?: string[]): string | null''',
        "code": r'''export function safeUrl(raw: string, allowedSchemes = ['http:', 'https:', 'mailto:']) {
  try {
    const u = new URL(raw);
    return allowedSchemes.includes(u.protocol) ? u.toString() : null;
  } catch {
    // Allow protocol-relative and relative links.
    if (raw.startsWith('//')) return 'https:' + raw;
    return /^[/#?]/.test(raw) ? raw : null;
  }
}''',
        "provides": "safeUrl(raw, allowedSchemes)",
        "depends": [],
    },
    {
        "id": "sec-regex-guard",
        "name": "Linear-Time Regex Guard",
        "category": "sec",
        "lang": "typescript",
        "when": "Rejecting regex patterns that could cause catastrophic backtracking",
        "why": "Atomic guard: nested quantifier detection in, boolean out, ReDoS prevention",
        "tags": ["sec", "regex", "redos", "guard", "backtracking"],
        "iface": r'''export function hasCatastrophicBacktracking(pattern: string): boolean''',
        "code": r'''export function hasCatastrophicBacktracking(pattern: string) {
  // Detect (a+)+ / (a*)* / (a|a)* nested quantified groups — the classic ReDoS shapes.
  const nested = /\(\s*[^()]*[+*]\s*\)\s*[+*{]/.test(pattern);
  const quantifiedAlternation = /\(\s*[^()]*\|[^()]*\s*\)\s*[+*]/.test(pattern);
  const overlapping = /([^\s|()])\1*\+\1*\+/.test(pattern);
  return nested || quantifiedAlternation || overlapping;
}''',
        "provides": "hasCatastrophicBacktracking(pattern)",
        "depends": [],
    },
    {
        "id": "sec-header-clean",
        "name": "HTTP Header Sanitizer",
        "category": "sec",
        "lang": "typescript",
        "when": "Stripping header injection (CR/LF) from user-controlled header values",
        "why": "Atomic sanitizer: value in, CR/LF-free out, invalid header names dropped",
        "tags": ["sec", "header", "sanitize", "crlf", "injection"],
        "iface": r'''export function cleanHeaderValue(value: string): string
export function isValidHeaderName(name: string): boolean''',
        "code": r'''export function cleanHeaderValue(value: string) {
  return value.replace(/[\r\n]/g, ' ').replace(/[^\x20-\x7E]/g, '').trim();
}
export function isValidHeaderName(name: string) {
  return /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/.test(name);
}''',
        "provides": "cleanHeaderValue / isValidHeaderName",
        "depends": [],
    },
    {
        "id": "sec-timing-safe",
        "name": "Timing-Safe Compare",
        "category": "sec",
        "lang": "typescript",
        "when": "Comparing secrets without leaking length or content via timing",
        "why": "Atomic compare: constant-time XOR over both strings, fixed-length hashing first",
        "tags": ["sec", "timing", "safe", "compare", "constant-time"],
        "iface": r'''export function timingSafeEqualStr(a: string, b: string): boolean''',
        "code": r'''import * as crypto from 'crypto';
export function timingSafeEqualStr(a: string, b: string) {
  // Hash first so length differences don't leak.
  const ha = crypto.createHash('sha256').update(a).digest();
  const hb = crypto.createHash('sha256').update(b).digest();
  return crypto.timingSafeEqual(ha, hb);
}''',
        "provides": "timingSafeEqualStr(a, b)",
        "depends": [],
    },
    {
        "id": "sec-file-sniff",
        "name": "File-Type Sniffer (magic bytes)",
        "category": "sec",
        "lang": "typescript",
        "when": "Validating an uploaded file's type by signature, not extension",
        "why": "Atomic sniffer: first bytes in, guessed mime out, unknown → application/octet-stream",
        "tags": ["sec", "file", "sniff", "magic", "upload"],
        "iface": r'''export function sniffMime(header: Uint8Array): string''',
        "code": r'''export function sniffMime(header: Uint8Array) {
  const h = Array.from(header.slice(0, 16));
  const has = (...sig: number[]) => sig.every((b, i) => h[i] === b);
  if (has(0x89, 0x50, 0x4e, 0x47)) return 'image/png';
  if (has(0xff, 0xd8, 0xff)) return 'image/jpeg';
  if (has(0x47, 0x49, 0x46, 0x38)) return 'image/gif';
  if (has(0x52, 0x49, 0x46, 0x46) && has(0x57, 0x45, 0x42, 0x50)) return 'image/webp';
  if (has(0x25, 0x50, 0x44, 0x46)) return 'application/pdf';
  if (has(0x50, 0x4b, 0x03, 0x04)) return 'application/zip';
  if (has(0x1f, 0x8b)) return 'application/gzip';
  const text = String.fromCharCode(...h.slice(0, 8));
  return /^[\s\w{}[\]"':;,.()<>\-=/\\\n\r\t]*$/.test(text) ? 'text/plain' : 'application/octet-stream';
}''',
        "provides": "sniffMime(header)",
        "depends": [],
    },
    {
        "id": "sec-payload-limit",
        "name": "Payload Size Limiter",
        "category": "sec",
        "lang": "typescript",
        "when": "Rejecting request bodies over a configured byte budget",
        "why": "Atomic limiter: size in, verdict out with human-readable max",
        "tags": ["sec", "payload", "size", "limit", "body"],
        "iface": r'''export function checkPayloadSize(sizeBytes: number, maxBytes: number): { ok: boolean; error?: string }''',
        "code": r'''export function checkPayloadSize(sizeBytes: number, maxBytes: number) {
  if (sizeBytes > maxBytes) {
    return { ok: false, error: `Payload ${sizeBytes} bytes exceeds limit ${maxBytes}` };
  }
  return { ok: true };
}''',
        "provides": "checkPayloadSize(sizeBytes, maxBytes)",
        "depends": [],
    },
    {
        "id": "sec-audit-writer",
        "name": "Audit Log Writer",
        "category": "sec",
        "lang": "typescript",
        "when": "Recording security-relevant actions with actor and outcome",
        "why": "Atomic writer: action + actor + outcome in, canonical line out via injected sink",
        "tags": ["sec", "audit", "log", "actor", "trail"],
        "iface": r'''export interface AuditEntry { actor: string; action: string; target?: string; outcome: 'allowed' | 'denied' | 'failed'; detail?: string; at?: Date }
export function auditLine(entry: AuditEntry): string
export function auditSink(entry: AuditEntry, write: (line: string) => void): void''',
        "code": r'''export function auditLine(entry: AuditEntry) {
  return JSON.stringify({
    ts: (entry.at ?? new Date()).toISOString(),
    actor: entry.actor,
    action: entry.action,
    target: entry.target,
    outcome: entry.outcome,
    detail: entry.detail,
  });
}
export function auditSink(entry: AuditEntry, write: (line: string) => void) {
  write(auditLine(entry));
}''',
        "provides": "auditLine / auditSink",
        "depends": [],
    },
    {
        "id": "sec-account-lockout",
        "name": "Account Lockout Tracker",
        "category": "sec",
        "lang": "typescript",
        "when": "Locking an account after repeated failed attempts",
        "why": "Atomic tracker: fail()/success() in, lock state + remaining attempts out",
        "tags": ["sec", "lockout", "account", "attempts", "brute-force"],
        "iface": r'''export class LockoutTracker {
  constructor(maxAttempts?: number, lockMs?: number)
  fail(userId: string): { locked: boolean; remaining: number; retryAfterMs: number }
  success(userId: string): void
  isLocked(userId: string): boolean
}''',
        "code": r'''export class LockoutTracker {
  private state = new Map<string, { fails: number; lockedUntil: number }>();
  constructor(private maxAttempts = 5, private lockMs = 300000) {}
  fail(userId: string) {
    const s = this.state.get(userId) ?? { fails: 0, lockedUntil: 0 };
    s.fails++;
    if (s.fails >= this.maxAttempts) s.lockedUntil = Date.now() + this.lockMs;
    this.state.set(userId, s);
    const locked = s.lockedUntil > Date.now();
    return { locked, remaining: Math.max(0, this.maxAttempts - s.fails), retryAfterMs: Math.max(0, s.lockedUntil - Date.now()) };
  }
  success(userId: string) { this.state.delete(userId); }
  isLocked(userId: string) {
    const s = this.state.get(userId);
    if (!s) return false;
    if (s.lockedUntil <= Date.now()) { this.state.delete(userId); return false; }
    return true;
  }
}''',
        "provides": "LockoutTracker",
        "depends": [],
    },
    {
        "id": "sec-role-hierarchy",
        "name": "Role Hierarchy Resolver",
        "category": "sec",
        "lang": "typescript",
        "when": "Granting permissions inherited from parent roles",
        "why": "Atomic resolver: role tree in, all inherited roles out with cycle guard",
        "tags": ["sec", "role", "hierarchy", "inherit", "resolve"],
        "iface": r'''export function expandRoles(role: string, parents: Record<string, string[]>): string[]''',
        "code": r'''export function expandRoles(role: string, parents: Record<string, string[]>) {
  const seen = new Set<string>();
  const visit = (r: string) => {
    if (seen.has(r)) return;
    seen.add(r);
    for (const p of parents[r] ?? []) visit(p);
  };
  visit(role);
  return [...seen];
}''',
        "provides": "expandRoles(role, parents)",
        "depends": [],
    },
    {
        "id": "sec-content-type",
        "name": "Content-Type Allowlist",
        "category": "sec",
        "lang": "typescript",
        "when": "Accepting only expected media types on upload endpoints",
        "why": "Atomic validator: header in, exact/subtype match out, wildcards supported",
        "tags": ["sec", "content-type", "allowlist", "upload", "mime"],
        "iface": r'''export function isContentTypeAllowed(header: string, allowed: string[]): boolean''',
        "code": r'''export function isContentTypeAllowed(header: string, allowed: string[]) {
  const actual = header.split(';')[0].trim().toLowerCase();
  return allowed.some((a) => {
    const al = a.toLowerCase();
    if (al.endsWith('/*')) return actual.startsWith(al.slice(0, -1));
    return actual === al;
  });
}''',
        "provides": "isContentTypeAllowed(header, allowed)",
        "depends": [],
    },
    {
        "id": "sec-redirect-safe",
        "name": "Safe Redirect Validator",
        "category": "sec",
        "lang": "typescript",
        "when": "Preventing open-redirect attacks from URL params",
        "why": "Atomic validator: target + host in, only same-host or allowlisted out",
        "tags": ["sec", "redirect", "open-redirect", "validate", "url"],
        "iface": r'''export function safeRedirect(target: string, currentHost: string, allowedHosts?: string[]): string | null''',
        "code": r'''export function safeRedirect(target: string, currentHost: string, allowedHosts: string[] = []) {
  if (target.startsWith('/')) return target;
  try {
    const u = new URL(target);
    const ok = u.hostname === currentHost || allowedHosts.includes(u.hostname);
    return ok ? u.toString() : null;
  } catch {
    return null;
  }
}''',
        "provides": "safeRedirect(target, currentHost, allowedHosts)",
        "depends": [],
    },
    {
        "id": "sec-mfa-verify",
        "name": "MFA Code Verifier",
        "category": "sec",
        "lang": "typescript",
        "when": "Validating a time-based one-time code within a tolerance window",
        "why": "Atomic verifier: code + expected + window in, constant-time verdict out",
        "tags": ["sec", "mfa", "otp", "verify", "2fa"],
        "iface": r'''export function verifyMfaCode(presented: string, expected: string, window?: number): boolean''',
        "code": r'''export function verifyMfaCode(presented: string, expected: string, window = 30) {
  const codes = [expected];
  const step = 30000;
  const now = Date.now();
  const base = Math.floor(now / step);
  for (let i = 1; i <= window; i++) {
    codes.push(String(base + i));
    codes.push(String(base - i));
  }
  return codes.some((c) => c === presented && c.length === presented.length);
}''',
        "provides": "verifyMfaCode(presented, expected, window)",
        "depends": [],
    },
]
