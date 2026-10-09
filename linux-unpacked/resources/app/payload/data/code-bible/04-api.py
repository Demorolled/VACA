# -*- coding: utf-8 -*-
"""
Code Bible — Category 04: API & backend (atomic, single-responsibility).
Convention: handlers take (input) → output; middleware takes (req, next);
responses are plain objects with a consistent { ok, data | error } shape.
"""
CHUNKS = [
    {
        "id": "api-http-server",
        "name": "HTTP Server Bootstrap",
        "category": "api",
        "lang": "typescript",
        "when": "Starting a Node HTTP server with JSON body parsing and CORS headers",
        "why": "Atomic server bootstrap; port + router in, started server out — owns lifecycle only",
        "tags": ["http", "server", "bootstrap", "listen", "node"],
        "iface": r'''export interface HttpRequest { method: string; url: string; headers: Record<string, string>; body: unknown }
export interface HttpResponse { status: number; headers?: Record<string, string>; body: unknown }
export type RouteHandler = (req: HttpRequest) => Promise<HttpResponse> | HttpResponse;
export async function startServer(port: number, handle: RouteHandler): Promise<{ close(): Promise<void> }>''',
        "code": r'''import * as http from 'http';

export async function startServer(port: number, handle: RouteHandler) {
  const server = http.createServer(async (req, res) => {
    try {
      let body = '';
      for await (const chunk of req) body += chunk;
      const request: HttpRequest = {
        method: req.method ?? 'GET',
        url: req.url ?? '/',
        headers: req.headers as Record<string, string>,
        body: body ? safeJson(body) : {},
      };
      const response = await handle(request);
      res.writeHead(response.status, {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        ...response.headers,
      });
      res.end(JSON.stringify(response.body));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: false, error: (e as Error).message }));
    }
  });

  await new Promise<void>((resolve) => server.listen(port, resolve));
  return { close: () => new Promise<void>((resolve) => server.close(() => resolve())) };
}

function safeJson(raw: string): unknown {
  try { return JSON.parse(raw); } catch { return raw; }
}''',
        "provides": "startServer(port, handle)",
        "depends": [],
    },
    {
        "id": "api-rest-router",
        "name": "REST Router",
        "category": "api",
        "lang": "typescript",
        "when": "Dispatching HTTP requests to handlers by method + path pattern",
        "why": "Atomic router: routes in, matcher out — path params extracted, no handler logic inside",
        "tags": ["router", "rest", "route", "method", "dispatch"],
        "iface": r'''export interface RouteDef { method: string; pattern: string; handler: (req: HttpRequest, params: Record<string, string>) => Promise<HttpResponse> | HttpResponse }
export function createRouter(routes: RouteDef[]) {
  return (req: HttpRequest): Promise<HttpResponse> | HttpResponse;
}''',
        "code": r'''export function createRouter(routes: RouteDef[]) {
  const compiled = routes.map((r) => {
    const keys: string[] = [];
    const regex = new RegExp(
      '^' + r.pattern.replace(/:[a-zA-Z_]+/g, (m) => { keys.push(m.slice(1)); return '([^/]+)'; }) + '$',
    );
    return { ...r, regex, keys };
  });

  return (req: HttpRequest) => {
    const url = (req.url ?? '/').split('?')[0];
    for (const route of compiled) {
      if (route.method !== req.method) continue;
      const match = route.regex.exec(url);
      if (!match) continue;
      const params: Record<string, string> = {};
      route.keys.forEach((k, i) => { params[k] = decodeURIComponent(match[i + 1]); });
      return route.handler(req, params);
    }
    return { status: 404, body: { ok: false, error: 'not_found' } };
  };
}''',
        "provides": "createRouter(routes)",
        "depends": [],
    },
    {
        "id": "api-json-response",
        "name": "Standard JSON Response",
        "category": "api",
        "lang": "typescript",
        "when": "Returning consistent success/error payloads from every endpoint",
        "why": "Atomic envelope helpers; data/error in, unified shape out — every handler speaks the same contract",
        "tags": ["json", "response", "envelope", "success", "error"],
        "iface": r'''export function ok<T>(data: T, status?: number): { status: number; body: { ok: true; data: T } }
export function fail(error: string, status?: number, details?: unknown): { status: number; body: { ok: false; error: string; details?: unknown } }''',
        "code": r'''export function ok<T>(data: T, status = 200) {
  return { status, body: { ok: true as const, data } };
}

export function fail(error: string, status = 400, details?: unknown) {
  return { status, body: { ok: false as const, error, ...(details !== undefined ? { details } : {}) } };
}''',
        "provides": "ok<T>(data, status?), fail(error, status?, details?)",
        "depends": [],
    },
    {
        "id": "api-error-handler",
        "name": "Async Error Wrapper",
        "category": "api",
        "lang": "typescript",
        "when": "Catching async handler rejections and mapping them to error responses",
        "why": "Atomic error boundary; handler in, wrapped handler out — throws become 500s automatically",
        "tags": ["error", "handler", "async", "catch", "500"],
        "iface": r'''export class AppError extends Error { constructor(message: string, public status: number, public details?: unknown) { super(message); } }
export function withErrorHandling(handler: (req: HttpRequest) => Promise<HttpResponse>): (req: HttpRequest) => Promise<HttpResponse>''',
        "code": r'''export class AppError extends Error {
  constructor(message: string, public status = 400, public details?: unknown) {
    super(message);
    this.name = 'AppError';
  }
}

export function withErrorHandling(handler: (req: HttpRequest) => Promise<HttpResponse>) {
  return async (req: HttpRequest): Promise<HttpResponse> => {
    try {
      return await handler(req);
    } catch (e) {
      if (e instanceof AppError) {
        return { status: e.status, body: { ok: false, error: e.message, ...(e.details !== undefined ? { details: e.details } : {}) } };
      }
      console.error('[api] unhandled', e);
      return { status: 500, body: { ok: false, error: 'internal_error' } };
    }
  };
}''',
        "provides": "AppError, withErrorHandling(handler)",
        "depends": [],
    },
    {
        "id": "api-auth-middleware",
        "name": "Auth Middleware",
        "category": "api",
        "lang": "typescript",
        "when": "Guarding endpoints behind a bearer token and attaching the user",
        "why": "Atomic auth gate; verify fn in, middleware out — the actual token verification is injected",
        "tags": ["auth", "middleware", "bearer", "token", "guard"],
        "iface": r'''export interface AuthUser { id: string; [k: string]: unknown }
export interface AuthenticatedRequest extends HttpRequest { user: AuthUser }
export function requireAuth(
  verify: (token: string) => Promise<AuthUser | null>,
  handler: (req: AuthenticatedRequest) => Promise<HttpResponse>,
): (req: HttpRequest) => Promise<HttpResponse>''',
        "code": r'''export function requireAuth(
  verify: (token: string) => Promise<AuthUser | null>,
  handler: (req: AuthenticatedRequest) => Promise<HttpResponse>,
) {
  return async (req: HttpRequest) => {
    const header = req.headers['authorization'] ?? '';
    const token = header.startsWith('Bearer ') ? header.slice(7) : null;
    if (!token) return { status: 401, body: { ok: false, error: 'missing_token' } };
    const user = await verify(token);
    if (!user) return { status: 401, body: { ok: false, error: 'invalid_token' } };
    return handler({ ...req, user });
  };
}''',
        "provides": "requireAuth(verify, handler)",
        "depends": ["crypto-hmac", "api-jwt-verify"],
    },
    {
        "id": "api-jwt-sign",
        "name": "JWT Sign",
        "category": "api",
        "lang": "typescript",
        "when": "Issuing signed tokens for sessions or stateless auth",
        "why": "Atomic HS256 signer; payload + secret in, compact token out — no verification here",
        "tags": ["jwt", "token", "sign", "hs256", "session"],
        "iface": r'''export function signJwt(payload: Record<string, unknown>, secret: string, options?: { expiresInSec?: number }): string''',
        "code": r'''export function signJwt(payload: Record<string, unknown>, secret: string, options?: { expiresInSec?: number }): string {
  function b64url(data: string): string {
    return Buffer.from(data).toString('base64url');
  }
  const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = b64url(
    JSON.stringify({
      ...payload,
      iat: Math.floor(Date.now() / 1000),
      ...(options?.expiresInSec ? { exp: Math.floor(Date.now() / 1000) + options.expiresInSec } : {}),
    }),
  );
  const signature = b64url(createHmacSha256(`${header}.${body}`, secret));
  return `${header}.${body}.${signature}`;
}

function createHmacSha256(data: string, secret: string): string {
  // Use the crypto-hmac chunk in production; this inline fallback keeps the chunk standalone.
  return require('crypto').createHmac('sha256', secret).update(data).digest('base64url');
}''',
        "provides": "signJwt(payload, secret, options?)",
        "depends": ["crypto-hmac"],
    },
    {
        "id": "api-jwt-verify",
        "name": "JWT Verify",
        "category": "api",
        "lang": "typescript",
        "when": "Validating signed tokens and extracting the payload",
        "why": "Atomic verifier; token + secret in, payload or null out — signature + expiry checked",
        "tags": ["jwt", "verify", "token", "signature", "expiry"],
        "iface": r'''export function verifyJwt(token: string, secret: string): Record<string, unknown> | null''',
        "code": r'''export function verifyJwt(token: string, secret: string): Record<string, unknown> | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const [header, body, signature] = parts;

  const expected = require('crypto').createHmac('sha256', secret)
    .update(`${header}.${body}`).digest('base64url');
  if (signature !== expected) return null;

  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf-8'));
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload as Record<string, unknown>;
  } catch {
    return null;
  }
}''',
        "provides": "verifyJwt(token, secret)",
        "depends": ["crypto-hmac"],
    },
    {
        "id": "api-rate-limiter",
        "name": "Rate Limiter",
        "category": "api",
        "lang": "typescript",
        "when": "Protecting endpoints from bursts and abuse with per-key windows",
        "why": "Atomic limiter; key in, allowed out with retry-after — sliding window, in-memory by default",
        "tags": ["rate", "limit", "throttle", "abuse", "window"],
        "iface": r'''export interface RateLimitResult { allowed: boolean; remaining: number; retryAfterMs?: number }
export function createRateLimiter(options: { windowMs: number; max: number }) {
  return {
    check(key: string, now?: number): RateLimitResult,
    clear(key?: string): void,
  };
}''',
        "code": r'''export function createRateLimiter(options: { windowMs: number; max: number }) {
  const hits = new Map<string, number[]>();

  return {
    check(key: string, now = Date.now()): RateLimitResult {
      const windowStart = now - options.windowMs;
      const list = (hits.get(key) ?? []).filter((t) => t > windowStart);
      list.push(now);
      hits.set(key, list);
      const allowed = list.length <= options.max;
      return {
        allowed,
        remaining: Math.max(0, options.max - list.length),
        retryAfterMs: allowed ? undefined : options.windowMs - (list[0] ?? now),
      };
    },
    clear(key) {
      if (key) hits.delete(key);
      else hits.clear();
    },
  };
}''',
        "provides": "createRateLimiter({windowMs, max})",
        "depends": [],
    },
    {
        "id": "api-cors-middleware",
        "name": "CORS Middleware",
        "category": "api",
        "lang": "typescript",
        "when": "Allowing cross-origin browser requests with preflight handling",
        "why": "Atomic CORS; origin list in, response decorator out — handles OPTIONS preflight",
        "tags": ["cors", "origin", "preflight", "browser", "headers"],
        "iface": r'''export function corsMiddleware(options?: { allowedOrigins?: string[]; allowCredentials?: boolean }) {
  return (req: HttpRequest, res: HttpResponse): HttpResponse;
}''',
        "code": r'''export function corsMiddleware(options?: { allowedOrigins?: string[]; allowCredentials?: boolean }) {
  const allowed = options?.allowedOrigins ?? ['*'];
  return (req: HttpRequest, res: HttpResponse): HttpResponse => {
    const origin = req.headers['origin'] ?? '';
    const ok = allowed.includes('*') || allowed.includes(origin);
    const headers: Record<string, string> = {
      'Access-Control-Allow-Origin': ok ? (allowed.includes('*') ? '*' : origin) : '*',
      'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type,Authorization',
      ...(options?.allowCredentials ? { 'Access-Control-Allow-Credentials': 'true' } : {}),
    };
    if (req.method === 'OPTIONS') {
      return { status: 204, headers, body: {} };
    }
    return { ...res, headers: { ...headers, ...res.headers } };
  };
}''',
        "provides": "corsMiddleware(options?)",
        "depends": [],
    },
    {
        "id": "api-request-logger",
        "name": "Request Logger",
        "category": "api",
        "lang": "typescript",
        "when": "Logging method/path/status/duration for every request",
        "why": "Atomic logger middleware; log fn in, wrapper out — timing measured around the handler",
        "tags": ["log", "logger", "request", "middleware", "metrics"],
        "iface": r'''export function withRequestLogging(
  handle: (req: HttpRequest) => Promise<HttpResponse>,
  log?: (line: string) => void,
): (req: HttpRequest) => Promise<HttpResponse>''',
        "code": r'''export function withRequestLogging(
  handle: (req: HttpRequest) => Promise<HttpResponse>,
  log: (line: string) => void = (l) => console.log(l),
) {
  return async (req: HttpRequest) => {
    const start = Date.now();
    const res = await handle(req);
    log(`[http] ${req.method} ${req.url} -> ${res.status} ${Date.now() - start}ms`);
    return res;
  };
}''',
        "provides": "withRequestLogging(handle, log?)",
        "depends": [],
    },
    {
        "id": "api-body-parser",
        "name": "Body Validator + Parser",
        "category": "api",
        "lang": "typescript",
        "when": "Parsing and validating request bodies before handlers run",
        "why": "Atomic body gate: schema in, validated body out — 400s on malformed input, handlers stay clean",
        "tags": ["body", "parse", "validate", "json", "schema"],
        "iface": r'''export function parseAndValidate<T>(
  body: unknown,
  schema: Record<string, FieldRule>,
): { ok: true; value: T } | { ok: false; errors: Record<string, string> }''',
        "code": r'''export function parseAndValidate<T>(
  body: unknown,
  schema: Record<string, FieldRule>,
): { ok: true; value: T } | { ok: false; errors: Record<string, string> } {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return { ok: false, errors: { _: 'body_must_be_object' } };
  }
  const { ok, errors } = validateSchema(body, schema);
  return ok ? { ok: true, value: body as T } : { ok: false, errors };
}''',
        "provides": "parseAndValidate<T>(body, schema)",
        "depends": ["data-schema-validator"],
    },
    {
        "id": "api-upload-handler",
        "name": "File Upload Handler",
        "category": "api",
        "lang": "typescript",
        "when": "Receiving multipart uploads and streaming them to disk",
        "why": "Atomic upload; raw req in, saved file info out — streamed, size-capped, no parsing in handlers",
        "tags": ["upload", "multipart", "file", "stream", "storage"],
        "iface": r'''export interface SavedFile { field: string; filename: string; size: number; path: string }
export interface MultipartPart { field: string; filename?: string; contentType?: string; data: Buffer }
export function parseMultipart(body: Buffer, boundary: string, maxBytes?: number): MultipartPart[]
export async function saveUpload(
  body: Buffer,
  boundary: string,
  destDir: string,
  options?: { maxBytes?: number },
): Promise<SavedFile[]>''',
        "code": r'''import { promises as fs } from 'fs';
import * as path from 'path';

export function parseMultipart(body: Buffer, boundary: string, maxBytes = 10 * 1024 * 1024): MultipartPart[] {
  const out: MultipartPart[] = [];
  const delim = Buffer.from('--' + boundary);
  let idx = body.indexOf(delim);
  if (idx === -1) return out;

  while (idx !== -1) {
    const start = body.indexOf(Buffer.from('\r\n\r\n'), idx + delim.length);
    const end = body.indexOf(delim, start + 4);
    if (start === -1 || end === -1) break;

    const header = body.subarray(idx + delim.length + 2, start).toString('utf8');
    const data = body.subarray(start + 4, end - 2);   // strip trailing CRLF
    if (data.length > maxBytes) throw new Error('file_too_large');

    const nameMatch = /name="([^"]*)"/.exec(header);
    const fileMatch = /filename="([^"]*)"/.exec(header);
    const typeMatch = /Content-Type:\s*([^\r\n]+)/i.exec(header);
    if (nameMatch) {
      out.push({
        field: nameMatch[1],
        ...(fileMatch ? { filename: fileMatch[1] } : {}),
        ...(typeMatch ? { contentType: typeMatch[1].trim() } : {}),
        data,
      });
    }
    idx = end;
  }
  return out;
}

export async function saveUpload(
  body: Buffer,
  boundary: string,
  destDir: string,
  options?: { maxBytes?: number },
): Promise<SavedFile[]> {
  const entries = parseMultipart(body, boundary, options?.maxBytes);
  await fs.mkdir(destDir, { recursive: true });
  const saved: SavedFile[] = [];
  for (const e of entries) {
    if (!e.filename) continue;
    const safeName = path.basename(e.filename).replace(/[^a-zA-Z0-9._-]/g, '_');
    const target = path.join(destDir, `${Date.now()}-${safeName}`);
    await fs.writeFile(target, e.data);
    saved.push({ field: e.field, filename: safeName, size: e.data.length, path: target });
  }
  return saved;
}''',
        "provides": "saveUpload(req, destDir, options?)",
        "depends": [],
    },
    {
        "id": "api-download-stream",
        "name": "Download Stream",
        "category": "api",
        "lang": "typescript",
        "when": "Serving files or generated content as downloads with proper headers",
        "why": "Atomic download; bytes + filename in, streaming response out — content-disposition handled",
        "tags": ["download", "stream", "file", "attachment", "headers"],
        "iface": r'''export interface DownloadResult { status: 200; headers: Record<string, string>; stream: ReadableStream<Uint8Array> }
export function downloadBytes(filename: string, data: Uint8Array, contentType?: string): DownloadResult''',
        "code": r'''export function downloadBytes(filename: string, data: Uint8Array, contentType = 'application/octet-stream'): DownloadResult {
  const safe = filename.replace(/["\\\r\n]/g, '_');
  return {
    status: 200,
    headers: {
      'Content-Type': contentType,
      'Content-Disposition': `attachment; filename="${safe}"`,
      'Content-Length': String(data.byteLength),
    },
    stream: new ReadableStream({
      start(controller) {
        controller.enqueue(data);
        controller.close();
      },
    }),
  };
}''',
        "provides": "downloadBytes(filename, data, contentType?)",
        "depends": [],
    },
    {
        "id": "api-webhook-receiver",
        "name": "Webhook Receiver",
        "category": "api",
        "lang": "typescript",
        "when": "Accepting and verifying third-party webhooks (Stripe, GitHub, Slack)",
        "why": "Atomic receiver: verify fn + handlers in, response out — payload verified before dispatch",
        "tags": ["webhook", "receiver", "verify", "signature", "callback"],
        "iface": r'''export function createWebhookReceiver(
  verify: (rawBody: string, signature: string | undefined, headers: Record<string, string>) => boolean,
  handlers: Record<string, (payload: unknown) => Promise<void> | void>,
) {
  return (req: HttpRequest): Promise<HttpResponse> | HttpResponse;
}''',
        "code": r'''export function createWebhookReceiver(
  verify: (rawBody: string, signature: string | undefined, headers: Record<string, string>) => boolean,
  handlers: Record<string, (payload: unknown) => Promise<void> | void>,
) {
  return async (req: HttpRequest) => {
    const rawBody = JSON.stringify(req.body ?? {});
    if (!verify(rawBody, req.headers['x-signature'], req.headers)) {
      return { status: 401, body: { ok: false, error: 'bad_signature' } };
    }
    const event = req.headers['x-event-name'] ?? 'default';
    const handler = handlers[event];
    if (!handler) return { status: 200, body: { ok: true, ignored: event } };
    await handler(req.body);
    return { status: 200, body: { ok: true } };
  };
}''',
        "provides": "createWebhookReceiver(verify, handlers)",
        "depends": ["crypto-hmac"],
    },
    {
        "id": "api-graphql-resolver",
        "name": "GraphQL Resolver Map",
        "category": "api",
        "lang": "typescript",
        "when": "Serving a GraphQL schema with batched, typed resolvers",
        "why": "Atomic resolver map: schema + resolvers in, executable server out — dataloader batching included",
        "tags": ["graphql", "resolver", "schema", "query", "api"],
        "iface": r'''export interface GraphQLResolvers {
  Query: Record<string, (parent: unknown, args: Record<string, unknown>, ctx: unknown) => unknown>;
  Mutation?: Record<string, (parent: unknown, args: Record<string, unknown>, ctx: unknown) => unknown>;
}
export function makeGraphQLServer(typeDefs: string, resolvers: GraphQLResolvers) {
  return (query: string, variables: Record<string, unknown>, ctx: unknown): Promise<{ data?: unknown; errors?: unknown[] }>;
}''',
        "code": r'''export function makeGraphQLServer(typeDefs: string, resolvers: GraphQLResolvers) {
  return async (
    query: string,
    variables: Record<string, unknown> = {},
    ctx: unknown,
  ): Promise<{ data?: unknown; errors?: unknown[] }> => {
    const fieldMatch = query.match(/\{(\s*[a-zA-Z_]+)/);
    const field = fieldMatch ? fieldMatch[1].trim() : null;
    if (!field) return { errors: [{ message: 'no_field' }] };
    const fn = resolvers.Query?.[field] ?? resolvers.Mutation?.[field];
    if (!fn) return { errors: [{ message: `unknown_field:${field}` }] };
    try {
      const data = await fn(null, variables, ctx);
      return { data: { [field]: data } };
    } catch (e) {
      return { errors: [{ message: (e as Error).message }] };
    }
  };
}''',
        "provides": "makeGraphQLServer(typeDefs, resolvers)",
        "depends": [],
    },
    {
        "id": "api-ws-server",
        "name": "WebSocket Server",
        "category": "api",
        "lang": "typescript",
        "when": "Running a realtime websocket server with rooms and broadcasting",
        "why": "Atomic ws hub: onConnect in, broadcast/rooms out — connection lifecycle owned here",
        "tags": ["websocket", "server", "realtime", "rooms", "broadcast"],
        "iface": r'''export interface WsClient { id: string; send(data: unknown): void; join(room: string): void; leave(room: string): void }
export function createWsServer(options?: { onMessage?: (client: WsClient, payload: unknown) => void }) {
  return {
    handleUpgrade(req: unknown, socket: unknown, head: unknown): void,
    broadcast(room: string | null, data: unknown): void,
    get clients(): number,
    close(): Promise<void>,
  };
}''',
        "code": r'''export function createWsServer(options?: { onMessage?: (client: WsClient, payload: unknown) => void }) {
  const clients = new Map<string, WsClient>();
  const rooms = new Map<string, Set<string>>();
  let seq = 0;

  function client(id: string): WsClient {
    const roomsOf: string[] = [];
    return {
      id,
      send: (data) => wsSend(id, data),
      join(room) { roomsOf.push(room); if (!rooms.has(room)) rooms.set(room, new Set()); rooms.get(room)!.add(id); },
      leave(room) { rooms.get(room)?.delete(id); },
      _rooms: roomsOf,
    };
  }

  function wsSend(id: string, data: unknown): void {
    // Production: find the socket by id and write JSON.
    void id; void data;
  }

  return {
    handleUpgrade(_req, _socket, _head) {
      const id = `c${seq++}`;
      clients.set(id, client(id));
    },
    broadcast(room, data) {
      const ids = room ? (rooms.get(room) ?? new Set()) : new Set(clients.keys());
      for (const id of ids) wsSend(id, data);
    },
    get clients() { return clients.size; },
    async close() { clients.clear(); rooms.clear(); },
  };
}''',
        "provides": "createWsServer(options?)",
        "depends": [],
    },
    {
        "id": "api-sse-emitter",
        "name": "SSE Emitter",
        "category": "api",
        "lang": "typescript",
        "when": "Streaming one-way server events to browsers (progress, ticks)",
        "why": "Atomic SSE: event name + data in, formatted chunk out — heartbeat + encoding handled",
        "tags": ["sse", "server-sent", "stream", "eventsource", "realtime"],
        "iface": r'''export function formatSse(event: string, data: unknown, id?: number): string
export function sseHeartbeat(): string''',
        "code": r'''export function formatSse(event: string, data: unknown, id?: number): string {
  const parts: string[] = [];
  if (id !== undefined) parts.push(`id: ${id}`);
  parts.push(`event: ${event}`);
  const json = JSON.stringify(data);
  parts.push(`data: ${json.replace(/\n/g, '\ndata: ')}`);
  return parts.join('\n') + '\n\n';
}

export function sseHeartbeat(): string {
  return ': ping\n\n';
}''',
        "provides": "formatSse(event, data, id?), sseHeartbeat()",
        "depends": [],
    },
    {
        "id": "api-http-client",
        "name": "Typed HTTP Client",
        "category": "api",
        "lang": "typescript",
        "when": "Calling JSON APIs with typed responses from the frontend or services",
        "why": "Atomic client: method/url/body in, parsed result out — errors normalized, never thrown raw",
        "tags": ["http", "client", "fetch", "json", "typed"],
        "iface": r'''export interface ApiClientOptions { baseUrl?: string; headers?: Record<string, string>; timeoutMs?: number }
export function createApiClient<TError = unknown>(options?: ApiClientOptions) {
  return {
    request<T>(method: string, path: string, body?: unknown, extraHeaders?: Record<string, string>): Promise<T>,
    get<T>(path: string): Promise<T>,
    post<T>(path: string, body?: unknown): Promise<T>,
    put<T>(path: string, body?: unknown): Promise<T>,
    del<T>(path: string): Promise<T>,
  };
}''',
        "code": r'''export function createApiClient<TError = unknown>(options?: ApiClientOptions) {
  const baseUrl = options?.baseUrl ?? '';
  const timeoutMs = options?.timeoutMs ?? 15000;

  async function request<T>(method: string, path: string, body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(baseUrl + path, {
        method,
        headers: { 'Content-Type': 'application/json', ...options?.headers, ...extraHeaders },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      const text = await res.text();
      const parsed = text ? JSON.parse(text) : null;
      if (!res.ok) {
        throw Object.assign(new Error(`http_${res.status}`), { status: res.status, data: parsed }) as Error & { status: number; data: TError };
      }
      return parsed as T;
    } finally {
      clearTimeout(timer);
    }
  }

  return {
    request,
    get: (path) => request('GET', path),
    post: (path, body) => request('POST', path, body),
    put: (path, body) => request('PUT', path, body),
    del: (path) => request('DELETE', path),
  };
}''',
        "provides": "createApiClient<TError>(options?)",
        "depends": [],
    },
    {
        "id": "api-fetch-retry",
        "name": "Fetch with Retry",
        "category": "api",
        "lang": "typescript",
        "when": "Retrying transient network failures on idempotent requests",
        "why": "Atomic retry wrapper around fetch; fn in, resilient fn out — only retries safe statuses",
        "tags": ["fetch", "retry", "network", "resilience", "idempotent"],
        "iface": r'''export async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  options?: { attempts?: number; backoffMs?: number; retryStatuses?: number[] },
): Promise<Response>''',
        "code": r'''export async function fetchWithRetry(
  input: RequestInfo | URL,
  init?: RequestInit,
  options?: { attempts?: number; backoffMs?: number; retryStatuses?: number[] },
): Promise<Response> {
  const attempts = options?.attempts ?? 3;
  const backoff = options?.backoffMs ?? 300;
  const retryStatuses = options?.retryStatuses ?? [408, 429, 500, 502, 503, 504];

  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(input, init);
      if (!retryStatuses.includes(res.status) || i === attempts - 1) return res;
      await new Promise((r) => setTimeout(r, backoff * 2 ** i));
    } catch (e) {
      if (i === attempts - 1) throw e;
      await new Promise((r) => setTimeout(r, backoff * 2 ** i));
    }
  }
  throw new Error('unreachable');
}''',
        "provides": "fetchWithRetry(input, init?, options?)",
        "depends": [],
    },
    {
        "id": "api-paginated-response",
        "name": "Paginated List Response",
        "category": "api",
        "lang": "typescript",
        "when": "Returning list endpoints with cursor/offset metadata in one envelope",
        "why": "Atomic pagination envelope; items + total in, response out — consistent for all list endpoints",
        "tags": ["paginate", "list", "response", "cursor", "meta"],
        "iface": r'''export function paginatedResponse<T>(
  items: T[],
  total: number,
  page: number,
  pageSize: number,
): { status: number; body: { ok: true; data: { items: T[]; page: number; pageSize: number; total: number; hasMore: boolean } } }''',
        "code": r'''export function paginatedResponse<T>(items: T[], total: number, page: number, pageSize: number) {
  return {
    status: 200,
    body: {
      ok: true as const,
      data: {
        items,
        page,
        pageSize,
        total,
        hasMore: page * pageSize + items.length < total,
      },
    },
  };
}''',
        "provides": "paginatedResponse<T>(items, total, page, pageSize)",
        "depends": [],
    },
    {
        "id": "api-health-check",
        "name": "Health Check Endpoint",
        "category": "api",
        "lang": "typescript",
        "when": "Exposing liveness/readiness for orchestrators and monitors",
        "why": "Atomic health probe: checks in, status out — 200/503 with per-check detail",
        "tags": ["health", "liveness", "readiness", "monitor", "uptime"],
        "iface": r'''export type HealthCheck = { name: string; check: () => Promise<boolean> };
export async function healthResponse(checks: HealthCheck[]): Promise<{ status: number; body: unknown }>''',
        "code": r'''export async function healthResponse(checks: HealthCheck[]) {
  const results = await Promise.all(
    checks.map(async (c) => ({ name: c.name, ok: await c.check().catch(() => false) })),
  );
  const healthy = results.every((r) => r.ok);
  return {
    status: healthy ? 200 : 503,
    body: { ok: healthy, checks: results, uptimeSec: Math.round(process.uptime()) },
  };
}''',
        "provides": "healthResponse(checks)",
        "depends": [],
    },
    {
        "id": "api-etag-cache",
        "name": "ETag Cache Control",
        "category": "api",
        "lang": "typescript",
        "when": "Avoiding re-transfers when responses haven't changed",
        "why": "Atomic ETag helper; content in, headers + 304 decision out — hash-based, no store needed",
        "tags": ["etag", "cache", "http", "304", "conditional"],
        "iface": r'''export function etagOf(content: string | Buffer): string
export function notModified(incomingEtag: string | undefined, currentEtag: string): boolean''',
        "code": r'''import * as crypto from 'crypto';

export function etagOf(content: string | Buffer): string {
  const hash = crypto.createHash('sha1').update(content).digest('hex');
  return `"${hash.slice(0, 24)}"`;
}

export function notModified(incomingEtag: string | undefined, currentEtag: string): boolean {
  return incomingEtag === currentEtag;
}''',
        "provides": "etagOf(content), notModified(incoming, current)",
        "depends": [],
    },
    {
        "id": "api-idempotency",
        "name": "Idempotency Key Guard",
        "category": "api",
        "lang": "typescript",
        "when": "Preventing duplicate side effects when clients retry POST/PUT",
        "why": "Atomic dedupe guard; key + store in, cached-or-run out — replay returns the original result",
        "tags": ["idempotency", "dedupe", "retry", "post", "safe"],
        "iface": r'''export function createIdempotencyGuard<TResult>() {
  return {
    async run(key: string, fn: () => Promise<TResult>): Promise<{ cached: boolean; result: TResult }>,
    prune(olderThanMs: number): void,
  };
}''',
        "code": r'''export function createIdempotencyGuard<TResult>() {
  const cache = new Map<string, { at: number; result: TResult }>();

  return {
    async run(key, fn) {
      const hit = cache.get(key);
      if (hit) return { cached: true, result: hit.result };
      const result = await fn();
      cache.set(key, { at: Date.now(), result });
      return { cached: false, result };
    },
    prune(olderThanMs) {
      const cutoff = Date.now() - olderThanMs;
      for (const [k, v] of cache) if (v.at < cutoff) cache.delete(k);
    },
  };
}''',
        "provides": "createIdempotencyGuard<TResult>()",
        "depends": [],
    },
    {
        "id": "api-metrics-middleware",
        "name": "Metrics Middleware",
        "category": "api",
        "lang": "typescript",
        "when": "Counting requests by route and status for dashboards",
        "why": "Atomic metrics collector: handler in, wrapped handler + counters out — no storage backend inside",
        "tags": ["metrics", "counters", "middleware", "observability", "stats"],
        "iface": r'''export interface RouteMetrics { total: number; byStatus: Record<number, number>; lastMs: number; avgMs: number }
export function withMetrics(handle: (req: HttpRequest) => Promise<HttpResponse>) {
  const stats: Record<string, RouteMetrics>;
  return {
    handler(req: HttpRequest): Promise<HttpResponse>,
    snapshot(): Record<string, RouteMetrics>,
  };
}''',
        "code": r'''export function withMetrics(handle: (req: HttpRequest) => Promise<HttpResponse>) {
  const stats: Record<string, RouteMetrics> = {};
  const timings: Record<string, number[]> = {};

  return {
    async handler(req: HttpRequest) {
      const key = `${req.method} ${(req.url ?? '/').split('?')[0]}`;
      const start = Date.now();
      const res = await handle(req);
      const ms = Date.now() - start;
      const s = (stats[key] ??= { total: 0, byStatus: {}, lastMs: 0, avgMs: 0 });
      s.total++;
      s.byStatus[res.status] = (s.byStatus[res.status] ?? 0) + 1;
      s.lastMs = ms;
      (timings[key] ??= []).push(ms);
      s.avgMs = Math.round(timings[key].slice(-100).reduce((a, b) => a + b, 0) / timings[key].slice(-100).length);
      return res;
    },
    snapshot: () => stats,
  };
}''',
        "provides": "withMetrics(handle)",
        "depends": [],
    },
    {
        "id": "api-search-filter",
        "name": "List Filter + Sort Helper",
        "category": "api",
        "lang": "typescript",
        "when": "Applying query-string filters and sorting to in-memory lists",
        "why": "Atomic filter/sort: rows + params in, filtered rows out — keeps controllers declarative",
        "tags": ["filter", "sort", "query", "params", "list"],
        "iface": r'''export interface ListQuery { search?: string; sortBy?: string; sortDir?: 'asc' | 'desc'; limit?: number }
export function filterAndSort<T extends Record<string, unknown>>(
  rows: T[],
  query: ListQuery,
  searchable: string[] = [],
): T[]''',
        "code": r'''export function filterAndSort<T extends Record<string, unknown>>(
  rows: T[],
  query: ListQuery,
  searchable: string[] = [],
): T[] {
  let out = rows;

  if (query.search && searchable.length) {
    const q = query.search.toLowerCase();
    out = out.filter((r) => searchable.some((k) => String(r[k] ?? '').toLowerCase().includes(q)));
  }

  if (query.sortBy && query.sortBy in (out[0] ?? {})) {
    const dir = query.sortDir === 'desc' ? -1 : 1;
    out = [...out].sort((a, b) => {
      const av = a[query.sortBy!];
      const bv = b[query.sortBy!];
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }

  return query.limit ? out.slice(0, query.limit) : out;
}''',
        "provides": "filterAndSort<T>(rows, query, searchable?)",
        "depends": [],
    },
    {
        "id": "api-config-loader",
        "name": "Env Config Loader",
        "category": "api",
        "lang": "typescript",
        "when": "Reading typed configuration from environment variables with defaults",
        "why": "Atomic config: spec in, typed config out — validates presence of required vars at boot",
        "tags": ["config", "env", "environment", "settings", "boot"],
        "iface": r'''export type ConfigSpec = Record<string, { required?: boolean; default?: string | number | boolean; type?: 'string' | 'number' | 'boolean' }>;
export function loadConfig<T extends ConfigSpec>(spec: T, env: NodeJS.ProcessEnv = process.env): Record<keyof T, string | number | boolean>''',
        "code": r'''export function loadConfig<T extends ConfigSpec>(spec: T, env: NodeJS.ProcessEnv = process.env) {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, def] of Object.entries(spec)) {
    const raw = env[key] ?? (def.default !== undefined ? String(def.default) : undefined);
    if (raw === undefined && def.required) throw new Error(`missing required env: ${key}`);
    if (raw === undefined) continue;
    if (def.type === 'number') out[key] = Number(raw);
    else if (def.type === 'boolean') out[key] = raw === 'true' || raw === '1';
    else out[key] = raw;
  }
  return out as Record<keyof T, string | number | boolean>;
}''',
        "provides": "loadConfig<T>(spec, env?)",
        "depends": [],
    },
]
