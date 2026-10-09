# -*- coding: utf-8 -*-
"""
Code Bible — Category 30: HTTP & Web Platform (atomic).
Convention: header names case-insensitive strings, pure helpers, no deps.
"""
CHUNKS = [
    {
        "id": "http-status-text",
        "name": "Status Code Helper",
        "category": "http",
        "lang": "typescript",
        "when": "Mapping an HTTP status code to its canonical reason phrase",
        "why": "Atomic status table — common codes + fallback, groups (2xx/3xx/4xx/5xx)",
        "tags": ["http", "status", "code", "reason", "phrase"],
        "iface": r'''export function statusText(code: number): string
export function statusClass(code: number): '1xx' | '2xx' | '3xx' | '4xx' | '5xx' | 'other' ''',
        "code": r'''const REASONS: Record<number, string> = {
  200: 'OK', 201: 'Created', 202: 'Accepted', 204: 'No Content', 206: 'Partial Content',
  301: 'Moved Permanently', 302: 'Found', 304: 'Not Modified', 307: 'Temporary Redirect', 308: 'Permanent Redirect',
  400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed',
  408: 'Request Timeout', 409: 'Conflict', 410: 'Gone', 413: 'Payload Too Large', 415: 'Unsupported Media Type',
  422: 'Unprocessable Entity', 429: 'Too Many Requests',
  500: 'Internal Server Error', 501: 'Not Implemented', 502: 'Bad Gateway', 503: 'Service Unavailable', 504: 'Gateway Timeout',
};
export function statusText(code: number) { return REASONS[code] ?? 'Unknown'; }
export function statusClass(code: number) {
  const c = Math.floor(code / 100);
  return (c >= 1 && c <= 5 ? c + 'xx' : 'other') as '1xx' | '2xx' | '3xx' | '4xx' | '5xx' | 'other';
}''',
        "provides": "statusText / statusClass",
        "depends": [],
    },
    {
        "id": "http-date-header",
        "name": "HTTP Date Header",
        "category": "http",
        "lang": "typescript",
        "when": "Formatting/parsing RFC 7231 (IMF-fixdate) HTTP dates",
        "why": "Atomic IMF-fixdate codec — the exact format Date/Last-Modified headers require",
        "tags": ["http", "date", "header", "rfc7231", "imf-fixdate"],
        "iface": r'''export function toHttpDate(date: Date): string
export function fromHttpDate(value: string): Date | null''',
        "code": r'''export function toHttpDate(date: Date) {
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const p = (n: number) => String(n).padStart(2, '0');
  return `${days[date.getUTCDay()]}, ${p(date.getUTCDate())} ${months[date.getUTCMonth()]} ${date.getUTCFullYear()} ${p(date.getUTCHours())}:${p(date.getUTCMinutes())}:${p(date.getUTCSeconds())} GMT`;
}
export function fromHttpDate(value: string) {
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}''',
        "provides": "toHttpDate / fromHttpDate",
        "depends": [],
    },
    {
        "id": "http-accept-parse",
        "name": "Accept Header Parser",
        "category": "http",
        "lang": "typescript",
        "when": "Parsing Accept / Accept-Language q-value negotiation lists",
        "why": "Atomic q-value parser — media types with weights, sorted best-first",
        "tags": ["http", "accept", "parser", "q-value", "negotiation"],
        "iface": r'''export function parseAccept(header: string): Array<{ value: string; q: number }>''',
        "code": r'''export function parseAccept(header: string) {
  return header.split(',').map((part) => {
    const [value, ...params] = part.trim().split(';');
    const q = parseFloat(params.find((p) => p.trim().startsWith('q='))?.split('=')[1] ?? '1');
    return { value: value.trim(), q: isNaN(q) ? 0 : q };
  }).sort((a, b) => b.q - a.q);
}''',
        "provides": "parseAccept(header)",
        "depends": [],
    },
    {
        "id": "http-content-negotiation",
        "name": "Content Negotiation",
        "category": "http",
        "lang": "typescript",
        "when": "Choosing the best response format from the client's Accept header",
        "why": "Atomic picker — intersection of accepted and offered types by q-value",
        "tags": ["http", "negotiation", "content-type", "accept", "pick"],
        "iface": r'''export function negotiate(acceptHeader: string, offered: string[]): string | null''',
        "code": r'''export function negotiate(acceptHeader: string, offered: string[]) {
  const accepted = parseAccept(acceptHeader);
  for (const a of accepted) {
    const [type, sub] = a.value.toLowerCase().split('/');
    for (const o of offered) {
      const [ot, os] = o.toLowerCase().split('/');
      if ((type === '*' || type === ot) && (sub === '*' || sub === os)) return o;
    }
  }
  return null;
}
function parseAccept(header: string) {
  return header.split(',').map((part) => {
    const [value, ...params] = part.trim().split(';');
    const q = parseFloat(params.find((p) => p.trim().startsWith('q='))?.split('=')[1] ?? '1');
    return { value: value.trim(), q: isNaN(q) ? 0 : q };
  }).sort((a, b) => b.q - a.q);
}''',
        "provides": "negotiate(acceptHeader, offered)",
        "depends": [],
    },
    {
        "id": "http-range-respond",
        "name": "Range Request Responder",
        "category": "http",
        "lang": "typescript",
        "when": "Computing the byte range slice for a Range header request",
        "why": "Atomic range math — bytes=start-end / bytes=start- / suffix, returns status + slice",
        "tags": ["http", "range", "bytes", "partial", "206"],
        "iface": r'''export function resolveRange(header: string | undefined, size: number): { status: 200 | 206 | 416; start: number; end: number }''',
        "code": r'''export function resolveRange(header: string | undefined, size: number) {
  if (!header || !header.startsWith('bytes=')) return { status: 200, start: 0, end: size - 1 };
  const spec = header.slice(6).trim();
  const m = /^(\d*)-(\d*)$/.exec(spec);
  if (!m || size === 0) return { status: 416, start: 0, end: -1 };
  let start = m[1] === '' ? 0 : parseInt(m[1], 10);
  let end = m[2] === '' ? size - 1 : parseInt(m[2], 10);
  if (m[1] === '' && m[2] !== '') { start = Math.max(0, size - parseInt(m[2], 10)); end = size - 1; }
  if (start >= size || start > end) return { status: 416, start: 0, end: -1 };
  end = Math.min(end, size - 1);
  return { status: 206, start, end };
}''',
        "provides": "resolveRange(header, size)",
        "depends": [],
    },
    {
        "id": "http-chunked-decode",
        "name": "Chunked Transfer Decoder",
        "category": "http",
        "lang": "typescript",
        "when": "Decoding HTTP/1.1 chunked transfer-encoding bodies",
        "why": "Atomic chunk decoder — hex sizes, extensions, CRLF framing, terminator",
        "tags": ["http", "chunked", "transfer-encoding", "decode"],
        "iface": r'''export function decodeChunked(body: string): string''',
        "code": r'''export function decodeChunked(body: string) {
  const out: string[] = [];
  let i = 0;
  while (i < body.length) {
    const lineEnd = body.indexOf('\r\n', i);
    if (lineEnd === -1) break;
    const sizeHex = body.slice(i, lineEnd).split(';')[0].trim();
    const size = parseInt(sizeHex, 16);
    i = lineEnd + 2;
    if (size === 0) break;
    out.push(body.slice(i, i + size));
    i += size + 2; // skip chunk data + trailing CRLF
  }
  return out.join('');
}''',
        "provides": "decodeChunked(body)",
        "depends": [],
    },
    {
        "id": "http-multipart-parse",
        "name": "Multipart/Form-Data Parser",
        "category": "http",
        "lang": "typescript",
        "when": "Parsing a multipart/form-data body into fields and files",
        "why": "Atomic boundary splitter — headers + body per part, name/filename extraction",
        "tags": ["http", "multipart", "form-data", "parser", "boundary"],
        "iface": r'''export interface MultipartPart { name: string; filename?: string; contentType?: string; body: string }
export function parseMultipart(contentType: string, body: string): MultipartPart[]''',
        "code": r'''export function parseMultipart(contentType: string, body: string) {
  const m = /boundary=(?:"([^"]+)"|([^;]+))/.exec(contentType);
  const boundary = m ? (m[1] ?? m[2]).trim() : '';
  if (!boundary) return [];
  const parts: MultipartPart[] = [];
  const delim = '--' + boundary;
  for (const raw of body.split(delim)) {
    if (!raw.trim() || raw.startsWith('--')) continue;
    const headerEnd = raw.indexOf('\r\n\r\n');
    if (headerEnd === -1) continue;
    const headers = raw.slice(0, headerEnd);
    const content = raw.slice(headerEnd + 4).replace(/\r\n$/, '');
    const name = /name="([^"]*)"/.exec(headers)?.[1] ?? '';
    const filename = /filename="([^"]*)"/.exec(headers)?.[1];
    const ct = /content-type:\s*([^\r\n]+)/i.exec(headers)?.[1]?.trim();
    parts.push({ name, filename, contentType: ct, body: content });
  }
  return parts;
}''',
        "provides": "parseMultipart(contentType, body)",
        "depends": [],
    },
    {
        "id": "http-redirect-chain",
        "name": "Redirect Chain Resolver",
        "category": "http",
        "lang": "typescript",
        "when": "Resolving a series of redirects to the final URL with a hop cap",
        "why": "Atomic redirect walker — follow 3xx with Location, detect loops, cap hops",
        "tags": ["http", "redirect", "chain", "follow", "loop"],
        "iface": r'''export function resolveRedirects(get: (url: string) => { status: number; location?: string }, start: string, maxHops = 5): { final: string; hops: string[] }''',
        "code": r'''export function resolveRedirects(get: (url: string) => { status: number; location?: string }, start: string, maxHops = 5) {
  let url = start;
  const hops = [url];
  const seen = new Set([url]);
  for (let i = 0; i < maxHops; i++) {
    const res = get(url);
    if (res.status < 300 || res.status >= 400 || !res.location) break;
    const next = new URL(res.location, url).toString();
    if (seen.has(next)) throw new Error(`Redirect loop at ${next}`);
    seen.add(next);
    url = next;
    hops.push(url);
  }
  return { final: url, hops };
}''',
        "provides": "resolveRedirects(get, start, maxHops?)",
        "depends": [],
    },
    {
        "id": "http-retry-after",
        "name": "Retry-After Parser",
        "category": "http",
        "lang": "typescript",
        "when": "Reading Retry-After as either seconds or an HTTP date",
        "why": "Atomic parser — delta-seconds or IMF-fixdate, returns ms wait",
        "tags": ["http", "retry-after", "429", "503", "parser"],
        "iface": r'''export function parseRetryAfter(header: string, now = new Date()): number''',
        "code": r'''export function parseRetryAfter(header: string, now = new Date()) {
  const trimmed = header.trim();
  if (/^\d+$/.test(trimmed)) return parseInt(trimmed, 10) * 1000;
  const date = new Date(trimmed);
  if (!isNaN(date.getTime())) return Math.max(0, date.getTime() - now.getTime());
  return 0;
}''',
        "provides": "parseRetryAfter(header, now?)",
        "depends": [],
    },
    {
        "id": "http-rate-header",
        "name": "Rate-Limit Header Formatter",
        "category": "http",
        "lang": "typescript",
        "when": "Emitting X-RateLimit-* style headers from a token bucket state",
        "why": "Atomic header builder — limit/remaining/reset from counters, RFC-ish fields",
        "tags": ["http", "rate-limit", "header", "429", "remaining"],
        "iface": r'''export function rateLimitHeaders(limit: number, remaining: number, resetAtMs: number): Record<string, string>''',
        "code": r'''export function rateLimitHeaders(limit: number, remaining: number, resetAtMs: number) {
  return {
    'X-RateLimit-Limit': String(limit),
    'X-RateLimit-Remaining': String(Math.max(0, remaining)),
    'X-RateLimit-Reset': String(Math.ceil(resetAtMs / 1000)),
  };
}''',
        "provides": "rateLimitHeaders(limit, remaining, resetAtMs)",
        "depends": [],
    },
    {
        "id": "http-conditional",
        "name": "Conditional Request Handler",
        "category": "http",
        "lang": "typescript",
        "when": "Evaluating If-None-Match / If-Modified-Since for 304 responses",
        "why": "Atomic revalidation — compare etags/mtimes, decide 304 vs fresh body",
        "tags": ["http", "conditional", "if-none-match", "304", "etag"],
        "iface": r'''export function evaluateConditional(etag: string | undefined, lastModifiedMs: number | undefined, headers: Record<string, string>): boolean''',
        "code": r'''export function evaluateConditional(etag: string | undefined, lastModifiedMs: number | undefined, headers: Record<string, string>) {
  const inm = headers['if-none-match'];
  if (inm !== undefined && etag !== undefined) {
    const tags = inm.split(',').map((t) => t.trim().replace(/^W\//, ''));
    if (tags.includes('*') || tags.includes(etag.replace(/^W\//, ''))) return true;
  }
  const ims = headers['if-modified-since'];
  if (ims !== undefined && lastModifiedMs !== undefined) {
    const since = Date.parse(ims);
    if (!isNaN(since) && lastModifiedMs <= since) return true;
  }
  return false;
}''',
        "provides": "evaluateConditional(etag, lastModifiedMs, headers)",
        "depends": [],
    },
    {
        "id": "http-cache-revalidate",
        "name": "Cache Revalidation",
        "category": "http",
        "lang": "typescript",
        "when": "Deciding whether a cached entry is fresh from Cache-Control directives",
        "why": "Atomic freshness calc — max-age/s-maxage vs age, no-store/no-cache short-circuit",
        "tags": ["http", "cache", "revalidate", "max-age", "freshness"],
        "iface": r'''export function cacheFresh(cacheControl: string | undefined, ageSec: number): 'fresh' | 'stale' | 'revalidate' | 'no-store' ''',
        "code": r'''export function cacheFresh(cacheControl: string | undefined, ageSec: number) {
  if (!cacheControl) return 'fresh';
  const dirs = new Map(cacheControl.split(',').map((d) => d.trim().split('=')).map(([k, v]) => [k.toLowerCase(), v]));
  if (dirs.has('no-store')) return 'no-store';
  const maxAge = parseInt(dirs.get('max-age') ?? dirs.get('s-maxage') ?? '', 10);
  if (isNaN(maxAge)) return 'revalidate';
  return ageSec <= maxAge ? 'fresh' : 'revalidate';
}''',
        "provides": "cacheFresh(cacheControl, ageSec)",
        "depends": [],
    },
    {
        "id": "http-oauth-refresh",
        "name": "OAuth2 Token Refresh",
        "category": "http",
        "lang": "typescript",
        "when": "Proactively refreshing an expiring access token with a refresh token",
        "why": "Atomic refresh manager — expiry-aware get, single-flight refresh, callback injectable",
        "tags": ["http", "oauth", "refresh", "token", "expiry"],
        "iface": r'''export class OAuthTokenManager {
  constructor(get: () => { token: string; expiresAtMs: number }, refresh: () => Promise<{ token: string; expiresAtMs: number }>, clock?: () => number)
  async token(): Promise<string>
}''',
        "code": r'''export class OAuthTokenManager {
  private refreshing: Promise<string> | null = null;
  constructor(private get: () => { token: string; expiresAtMs: number }, private refresh: () => Promise<{ token: string; expiresAtMs: number }>, private clock: () => number = Date.now) {}
  async token() {
    const cur = this.get();
    if (this.clock() < cur.expiresAtMs - 60_000) return cur.token;
    if (!this.refreshing) {
      this.refreshing = this.refresh().then((r) => r.token).finally(() => { this.refreshing = null; });
    }
    return this.refreshing;
  }
}''',
        "provides": "OAuthTokenManager",
        "depends": [],
    },
    {
        "id": "http-basic-auth",
        "name": "Basic Auth Parser",
        "category": "http",
        "lang": "typescript",
        "when": "Decoding/encoding HTTP Basic authorization headers",
        "why": "Atomic codec — 'Basic base64(user:pass)' both directions with validation",
        "tags": ["http", "basic-auth", "authorization", "base64"],
        "iface": r'''export function decodeBasic(header: string): { username: string; password: string } | null
export function encodeBasic(username: string, password: string): string''',
        "code": r'''export function decodeBasic(header: string) {
  if (!header.startsWith('Basic ')) return null;
  try {
    const [username, ...rest] = atob(header.slice(6)).split(':');
    return { username, password: rest.join(':') };
  } catch { return null; }
}
export function encodeBasic(username: string, password: string) {
  return 'Basic ' + btoa(`${username}:${password}`);
}''',
        "provides": "decodeBasic / encodeBasic",
        "depends": [],
    },
    {
        "id": "http-bearer-token",
        "name": "Bearer Token Extractor",
        "category": "http",
        "lang": "typescript",
        "when": "Pulling the token out of an Authorization: Bearer header",
        "why": "Atomic extractor — case-insensitive scheme, rejects malformed",
        "tags": ["http", "bearer", "token", "authorization", "extract"],
        "iface": r'''export function extractBearer(header: string | undefined): string | null''',
        "code": r'''export function extractBearer(header: string | undefined) {
  if (!header) return null;
  const m = /^Bearer\s+(\S+)$/i.exec(header.trim());
  return m ? m[1] : null;
}''',
        "provides": "extractBearer(header)",
        "depends": [],
    },
    {
        "id": "http-url-signer",
        "name": "URL Signer",
        "category": "http",
        "lang": "typescript",
        "when": "Signing a URL with HMAC so it can't be tampered with",
        "why": "Atomic signature — url + key + expiry in, signed url out, verify checks",
        "tags": ["http", "url", "sign", "hmac", "expiry"],
        "iface": r'''export function signUrl(url: string, key: string, expiresAtMs: number, hash: (s: string) => string): string
export function verifySignedUrl(signed: string, key: string, hash: (s: string) => string, now?: number): boolean''',
        "code": r'''export function signUrl(url: string, key: string, expiresAtMs: number, hash: (s: string) => string) {
  const base = url.split('?')[0];
  const sep = url.includes('?') ? '&' : '?';
  const sig = hash(`${base}|${expiresAtMs}|${key}`);
  return `${url}${sep}expires=${expiresAtMs}&sig=${sig}`;
}
export function verifySignedUrl(signed: string, key: string, hash: (s: string) => string, now = Date.now()) {
  const u = new URL(signed);
  const expires = Number(u.searchParams.get('expires') ?? NaN);
  if (!expires || expires < now) return false;
  const stripped = signed.split('?')[0];
  const sig = hash(`${stripped}|${expires}|${key}`);
  return u.searchParams.get('sig') === sig;
}''',
        "provides": "signUrl / verifySignedUrl",
        "depends": [],
    },
    {
        "id": "http-webhook-signature",
        "name": "Webhook Signature Verify",
        "category": "http",
        "lang": "typescript",
        "when": "Verifying an HMAC signature on an incoming webhook payload",
        "why": "Atomic verifier — constant-time compare, header 'sha256=<hex>' convention",
        "tags": ["http", "webhook", "signature", "hmac", "verify"],
        "iface": r'''export function verifyWebhookSignature(payload: string, signatureHeader: string, secret: string, hash: (s: string) => string): boolean''',
        "code": r'''function timingSafe(a: string, b: string) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
export function verifyWebhookSignature(payload: string, signatureHeader: string, secret: string, hash: (s: string) => string) {
  const m = /^sha256=([0-9a-f]+)$/i.exec(signatureHeader.trim());
  if (!m) return false;
  return timingSafe(m[1].toLowerCase(), hash(payload + secret).toLowerCase());
}''',
        "provides": "verifyWebhookSignature(payload, signatureHeader, secret, hash)",
        "depends": [],
    },
    {
        "id": "http-sse-client",
        "name": "SSE Client",
        "category": "http",
        "lang": "typescript",
        "when": "Parsing a Server-Sent Events stream into named events",
        "why": "Atomic SSE parser — event:/data:/id:/retry: fields, multi-line data, comments",
        "tags": ["http", "sse", "eventsource", "stream", "parser"],
        "iface": r'''export interface SseMessage { event: string; data: string; id?: string }
export function parseSse(chunk: string, lastEvent = 'message'): SseMessage[]''',
        "code": r'''export function parseSse(chunk: string, lastEvent = 'message') {
  const out: SseMessage[] = [];
  let event = lastEvent, data: string[] = [], id: string | undefined;
  const flush = () => {
    if (data.length) out.push({ event, data: data.join('\n'), id });
    data = []; id = undefined;
  };
  for (const rawLine of chunk.split('\n')) {
    const line = rawLine.startsWith('\r') ? rawLine.slice(1) : rawLine;
    if (line.startsWith(':')) continue;
    if (line === '') { flush(); event = lastEvent; continue; }
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (field === 'event') event = value;
    else if (field === 'data') data.push(value);
    else if (field === 'id') id = value;
  }
  return out;
}''',
        "provides": "parseSse(chunk, lastEvent?)",
        "depends": [],
    },
    {
        "id": "http-longpoll",
        "name": "Long-Poll Helper",
        "category": "http",
        "lang": "typescript",
        "when": "Holding a request open until data arrives or a timeout hits",
        "why": "Atomic long-poll race — resolves on first data, rejects after timeout",
        "tags": ["http", "long-poll", "comet", "timeout", "wait"],
        "iface": r'''export function longPoll<T>(waitForData: (resolve: (v: T) => void) => void, timeoutMs: number): Promise<T>''',
        "code": r'''export function longPoll<T>(waitForData: (resolve: (v: T) => void) => void, timeoutMs: number) {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Long-poll timeout')), timeoutMs);
    waitForData((v) => { clearTimeout(timer); resolve(v); });
  });
}''',
        "provides": "longPoll(waitForData, timeoutMs)",
        "depends": [],
    },
    {
        "id": "http-reverse-proxy",
        "name": "Reverse Proxy Handler",
        "category": "http",
        "lang": "typescript",
        "when": "Forwarding a request to a backend and returning its response",
        "why": "Atomic forwarder — path prefix rewrite, header passthrough, error mapping",
        "tags": ["http", "proxy", "reverse", "forward", "backend"],
        "iface": r'''export class ReverseProxy {
  constructor(forward: (req: { url: string; headers: Record<string, string>; body?: unknown }) => Promise<{ status: number; body: unknown }>)
  async handle(path: string, headers: Record<string, string>, body?: unknown): Promise<{ status: number; body: unknown }>
}''',
        "code": r'''export class ReverseProxy {
  constructor(private forward: (req: { url: string; headers: Record<string, string>; body?: unknown }) => Promise<{ status: number; body: unknown }>) {}
  async handle(path: string, headers: Record<string, string>, body?: unknown) {
    try { return await this.forward({ url: path, headers, body }); }
    catch { return { status: 502, body: { error: 'Bad gateway' } }; }
  }
}''',
        "provides": "ReverseProxy",
        "depends": [],
    },
    {
        "id": "http-request-id",
        "name": "Request ID Generator",
        "category": "http",
        "lang": "typescript",
        "when": "Issuing traceable request ids for correlation across services",
        "why": "Atomic id mint — timestamp + counter + random, collision-safe per process",
        "tags": ["http", "request-id", "trace", "correlation", "id"],
        "iface": r'''export class RequestIdGenerator {
  next(): string
}''',
        "code": r'''export class RequestIdGenerator {
  private counter = 0;
  next() {
    return `${Date.now().toString(36)}-${(this.counter++).toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }
}''',
        "provides": "RequestIdGenerator",
        "depends": [],
    },
    {
        "id": "http-method-allow",
        "name": "Method Allowlist",
        "category": "http",
        "lang": "typescript",
        "when": "Enforcing allowed HTTP methods and emitting Allow headers",
        "why": "Atomic gate — method check + Allow header + 405 response shape",
        "tags": ["http", "method", "allow", "405", "allowlist"],
        "iface": r'''export function methodAllowed(method: string, allowed: string[]): boolean
export function allowHeader(allowed: string[]): string''',
        "code": r'''export function methodAllowed(method: string, allowed: string[]) {
  return allowed.includes(method.toUpperCase());
}
export function allowHeader(allowed: string[]) { return [...new Set(allowed.map((m) => m.toUpperCase()))].join(', '); }''',
        "provides": "methodAllowed / allowHeader",
        "depends": [],
    },
    {
        "id": "http-link-header",
        "name": "Link Header Parser",
        "category": "http",
        "lang": "typescript",
        "when": "Parsing Link headers (rel=next/prev pagination) into URLs",
        "why": "Atomic link parser — '<url>; rel='next'' format, multiple rels per link",
        "tags": ["http", "link", "header", "pagination", "rel"],
        "iface": r'''export function parseLinkHeader(header: string | undefined): Record<string, string>''',
        "code": r'''export function parseLinkHeader(header: string | undefined) {
  const out: Record<string, string> = {};
  if (!header) return out;
  for (const part of header.split(',')) {
    const m = /<([^>]+)>\s*;\s*(.*)/.exec(part.trim());
    if (!m) continue;
    const url = m[1];
    for (const param of m[2].split(';')) {
      const rel = /rel="?([^";]+)"?/.exec(param.trim());
      if (rel) out[rel[1]] = url;
    }
  }
  return out;
}''',
        "provides": "parseLinkHeader(header)",
        "depends": [],
    },
    {
        "id": "http-cookie-jar",
        "name": "Cookie Jar",
        "category": "http",
        "lang": "typescript",
        "when": "Storing and sending cookies per domain with expiry",
        "why": "Atomic jar — set/expire/domain scoping, emits a Cookie header for a url",
        "tags": ["http", "cookie", "jar", "session", "domain"],
        "iface": r'''export class CookieJar {
  set(name: string, value: string, opts?: { domain?: string; expiresAtMs?: number }): void
  headerFor(url: string): string
}''',
        "code": r'''export class CookieJar {
  private cookies = new Map<string, { value: string; domain?: string; expiresAtMs?: number }>();
  set(name: string, value: string, opts: { domain?: string; expiresAtMs?: number } = {}) {
    this.cookies.set(name, { value, ...opts });
  }
  headerFor(url: string) {
    const host = new URL(url).hostname;
    const now = Date.now();
    const parts: string[] = [];
    for (const [name, c] of this.cookies) {
      if (c.expiresAtMs && c.expiresAtMs < now) continue;
      if (c.domain && !host.endsWith(c.domain)) continue;
      parts.push(`${name}=${c.value}`);
    }
    return parts.join('; ');
  }
}''',
        "provides": "CookieJar",
        "depends": [],
    },
    {
        "id": "http-form-urlencode",
        "name": "URL-Encode Form Builder",
        "category": "http",
        "lang": "typescript",
        "when": "Building application/x-www-form-urlencoded bodies and parsing them",
        "why": "Atomic codec — encodeURIComponent pairs, tolerant decode, arrays supported",
        "tags": ["http", "form", "urlencoded", "encode", "parse"],
        "iface": r'''export function encodeForm(data: Record<string, string | number | boolean | string[]>): string
export function decodeForm(body: string): Record<string, string>''',
        "code": r'''export function encodeForm(data: Record<string, string | number | boolean | string[]>) {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(data)) {
    if (Array.isArray(v)) for (const item of v) parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(item))}`);
    else parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.join('&');
}
export function decodeForm(body: string) {
  const out: Record<string, string> = {};
  for (const pair of body.split('&')) {
    if (!pair) continue;
    const [k, v] = pair.split('=');
    out[decodeURIComponent(k)] = decodeURIComponent(v ?? '');
  }
  return out;
}''',
        "provides": "encodeForm / decodeForm",
        "depends": [],
    },
]
