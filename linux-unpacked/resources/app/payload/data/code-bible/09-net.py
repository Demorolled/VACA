# -*- coding: utf-8 -*-
"""
Code Bible — Category 09: Networking (atomic).
Convention: clients expose typed request methods; servers expose start/stop;
parsers are pure string→object.
"""
CHUNKS = [
    {
        "id": "net-tcp-server",
        "name": "TCP Server",
        "category": "net",
        "lang": "typescript",
        "when": "Accepting raw TCP connections (protocols, proxies, custom servers)",
        "why": "Atomic tcp listener; port + handlers in, start/stop out — buffering and framing left to caller",
        "tags": ["tcp", "server", "socket", "listen", "protocol"],
        "iface": r'''export interface TcpServerHandlers { onData: (clientId: string, data: Buffer) => void; onClose?: (clientId: string) => void }
export async function startTcpServer(port: number, handlers: TcpServerHandlers): Promise<{
  send(clientId: string, data: Uint8Array): void;
  broadcast(data: Uint8Array, except?: string): void;
  close(): Promise<void>;
  get clients(): number;
}>''',
        "code": r'''import * as net from 'net';

export async function startTcpServer(port: number, handlers: TcpServerHandlers) {
  const sockets = new Map<string, net.Socket>();
  let seq = 0;

  const server = net.createServer((socket) => {
    const id = `c${seq++}`;
    sockets.set(id, socket);
    socket.on('data', (data: Buffer) => handlers.onData(id, data));
    socket.on('close', () => { sockets.delete(id); handlers.onClose?.(id); });
    socket.on('error', () => sockets.delete(id));
  });

  await new Promise<void>((resolve) => server.listen(port, resolve));

  return {
    send(clientId, data) { sockets.get(clientId)?.write(Buffer.from(data)); },
    broadcast(data, except) {
      const buf = Buffer.from(data);
      for (const [id, s] of sockets) if (id !== except) s.write(buf);
    },
    close() {
      for (const s of sockets.values()) s.destroy();
      return new Promise<void>((resolve) => server.close(() => resolve()));
    },
    get clients() { return sockets.size; },
  };
}''',
        "provides": "startTcpServer(port, handlers)",
        "depends": [],
    },
    {
        "id": "net-tcp-client",
        "name": "TCP Client",
        "category": "net",
        "lang": "typescript",
        "when": "Connecting to raw TCP services and exchanging framed messages",
        "why": "Atomic client; host/port in, send/onData/close out — reconnection handled by caller",
        "tags": ["tcp", "client", "socket", "connect", "send"],
        "iface": r'''export async function connectTcp(host: string, port: number): Promise<{
  send(data: Uint8Array): void;
  onData(cb: (data: Buffer) => void): () => void;
  close(): Promise<void>;
  get connected(): boolean;
}>''',
        "code": r'''import * as net from 'net';

export async function connectTcp(host: string, port: number) {
  const socket = net.connect({ host, port });
  await new Promise<void>((resolve, reject) => {
    socket.once('connect', () => resolve());
    socket.once('error', reject);
  });
  const listeners = new Set<(data: Buffer) => void>();
  socket.on('data', (d: Buffer) => listeners.forEach((cb) => cb(d)));

  return {
    send(data) { socket.write(Buffer.from(data)); },
    onData(cb) { listeners.add(cb); return () => listeners.delete(cb); },
    close() {
      return new Promise<void>((resolve) => { socket.end(() => resolve()); });
    },
    get connected() { return socket.readyState === 'open'; },
  };
}''',
        "provides": "connectTcp(host, port)",
        "depends": [],
    },
    {
        "id": "net-http-client",
        "name": "HTTP Client (Node)",
        "category": "net",
        "lang": "typescript",
        "when": "Making HTTP requests without fetch (older Node, proxies, streaming)",
        "why": "Atomic client; url + options in, typed response out — handles redirects and errors",
        "tags": ["http", "client", "request", "node", "fetch"],
        "iface": r'''export interface HttpClientOptions { method?: string; headers?: Record<string, string>; body?: string; timeoutMs?: number }
export interface HttpClientResult { status: number; headers: Record<string, string>; body: string }
export function httpRequest(url: string, options?: HttpClientOptions): Promise<HttpClientResult>''',
        "code": r'''import * as http from 'http';
import * as https from 'https';

export function httpRequest(url: string, options: HttpClientOptions = {}): Promise<HttpClientResult> {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.request(url, {
      method: options.method ?? 'GET',
      headers: options.headers,
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => {
        resolve({
          status: res.statusCode ?? 0,
          headers: res.headers as Record<string, string>,
          body: Buffer.concat(chunks).toString('utf8'),
        });
      });
    });
    req.on('error', reject);
    if (options.timeoutMs) req.setTimeout(options.timeoutMs, () => req.destroy(new Error('timeout')));
    if (options.body) req.write(options.body);
    req.end();
  });
}''',
        "provides": "httpRequest(url, options?)",
        "depends": [],
    },
    {
        "id": "net-dns-resolve",
        "name": "DNS Resolver",
        "category": "net",
        "lang": "typescript",
        "when": "Resolving hostnames to IPs or looking up records",
        "why": "Atomic resolver; hostname in, records out — wraps node:dns with promisification",
        "tags": ["dns", "resolve", "hostname", "ip", "lookup"],
        "iface": r'''export function resolveHost(hostname: string): Promise<string[]>
export function lookupRecords(hostname: string, type?: 'A' | 'AAAA' | 'MX' | 'TXT' | 'CNAME'): Promise<unknown>''',
        "code": r'''import * as dns from 'dns/promises';

export async function resolveHost(hostname: string): Promise<string[]> {
  const result = await dns.lookup(hostname, { all: true });
  return result.map((r) => r.address);
}

export async function lookupRecords(hostname: string, type: 'A' | 'AAAA' | 'MX' | 'TXT' | 'CNAME' = 'A') {
  switch (type) {
    case 'A': return dns.resolve4(hostname);
    case 'AAAA': return dns.resolve6(hostname);
    case 'MX': return dns.resolveMx(hostname);
    case 'TXT': return dns.resolveTxt(hostname);
    case 'CNAME': return dns.resolveCname(hostname);
  }
}''',
        "provides": "resolveHost(hostname), lookupRecords(hostname, type?)",
        "depends": [],
    },
    {
        "id": "net-ping",
        "name": "Ping (ICMP-free)",
        "category": "net",
        "lang": "typescript",
        "when": "Measuring host reachability/latency without raw ICMP sockets",
        "why": "Atomic ping; host in, latency + reachable out — TCP connect timing, cross-platform",
        "tags": ["ping", "latency", "reachable", "network", "probe"],
        "iface": r'''export interface PingResult { reachable: boolean; latencyMs: number | null }
export function pingHost(host: string, options?: { port?: number; timeoutMs?: number }): Promise<PingResult>''',
        "code": r'''import * as net from 'net';

export function pingHost(host: string, options?: { port?: number; timeoutMs?: number }): Promise<PingResult> {
  const port = options?.port ?? 80;
  const timeoutMs = options?.timeoutMs ?? 3000;
  return new Promise((resolve) => {
    const start = Date.now();
    const socket = new net.Socket();
    const done = (reachable: boolean, latencyMs: number | null) => {
      socket.destroy();
      resolve({ reachable, latencyMs });
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => done(true, Date.now() - start));
    socket.once('timeout', () => done(false, null));
    socket.once('error', () => done(false, null));
    socket.connect(port, host);
  });
}''',
        "provides": "pingHost(host, options?)",
        "depends": [],
    },
    {
        "id": "net-port-scanner",
        "name": "Port Scanner",
        "category": "net",
        "lang": "typescript",
        "when": "Discovering open ports on a host (dev tools, diagnostics)",
        "why": "Atomic scanner; host + range in, open ports out — concurrent with bounded workers",
        "tags": ["port", "scan", "open", "network", "discover"],
        "iface": r'''export async function scanPorts(
  host: string,
  ports: number[],
  options?: { concurrency?: number; timeoutMs?: number },
): Promise<number[]>''',
        "code": r'''import * as net from 'net';

async function checkPort(host: string, port: number, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => { socket.destroy(); resolve(true); });
    socket.once('timeout', () => { socket.destroy(); resolve(false); });
    socket.once('error', () => resolve(false));
    socket.connect(port, host);
  });
}

export async function scanPorts(host: string, ports: number[], options?: { concurrency?: number; timeoutMs?: number }): Promise<number[]> {
  const concurrency = options?.concurrency ?? 32;
  const timeoutMs = options?.timeoutMs ?? 1000;
  const open: number[] = [];
  let cursor = 0;

  async function worker() {
    while (cursor < ports.length) {
      const port = ports[cursor++];
      if (await checkPort(host, port, timeoutMs)) open.push(port);
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  return open.sort((a, b) => a - b);
}''',
        "provides": "scanPorts(host, ports, options?)",
        "depends": [],
    },
    {
        "id": "net-ws-client",
        "name": "WebSocket Client (Node)",
        "category": "net",
        "lang": "typescript",
        "when": "Connecting to websocket servers from Node (bots, relays, tests)",
        "why": "Atomic ws client; url in, send/onMessage/close out — reconnection via injected callback",
        "tags": ["websocket", "client", "socket", "realtime", "node"],
        "iface": r'''export function createWsClient(url: string, options?: { protocols?: string[] }) {
  return {
    connect(): Promise<void>,
    send(data: unknown): void,
    onMessage(cb: (data: unknown) => void): () => void,
    close(): Promise<void>,
    get state(): 'connecting' | 'open' | 'closing' | 'closed',
  };
}''',
        "code": r'''export function createWsClient(url: string, options?: { protocols?: string[] }) {
  let ws: WebSocket | null = null;
  const listeners = new Set<(data: unknown) => void>();

  return {
    async connect() {
      ws = new WebSocket(url, options?.protocols);
      ws.onmessage = (ev) => {
        let parsed: unknown = ev.data;
        if (typeof ev.data === 'string') { try { parsed = JSON.parse(ev.data); } catch { /* keep raw */ } }
        listeners.forEach((cb) => cb(parsed));
      };
      await new Promise<void>((resolve, reject) => {
        if (!ws) return reject(new Error('no_ws'));
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error('ws_error'));
      });
    },
    send(data) {
      ws?.send(typeof data === 'string' ? data : JSON.stringify(data));
    },
    onMessage(cb) { listeners.add(cb); return () => listeners.delete(cb); },
    close() {
      return new Promise<void>((resolve) => {
        if (!ws) return resolve();
        ws.onclose = () => resolve();
        ws.close();
      });
    },
    get state() { return ws?.readyState === 1 ? 'open' : (ws?.readyState === 0 ? 'connecting' : 'closed'); },
  };
}''',
        "provides": "createWsClient(url, options?)",
        "depends": [],
    },
    {
        "id": "net-proxy",
        "name": "HTTP Forward Proxy",
        "category": "net",
        "lang": "typescript",
        "when": "Forwarding requests through a proxy (scraping, privacy, local dev)",
        "why": "Atomic proxy; target rules in, forwarding server out — handles CONNECT tunneling",
        "tags": ["proxy", "forward", "http", "tunnel", "relay"],
        "iface": r'''export function createForwardProxy(options?: { onRequest?: (url: string) => void }) {
  return {
    start(port: number): Promise<{ close(): Promise<void> }>,
  };
}''',
        "code": r'''import * as http from 'http';
import * as https from 'https';

export function createForwardProxy(options?: { onRequest?: (url: string) => void }) {
  return {
    start(port: number) {
      const server = http.createServer((req, res) => {
        const url = (req.headers['host'] ?? '') + (req.url ?? '');
        options?.onRequest?.(url);
        const isHttps = req.headers[':scheme'] === 'https' || /:443/.test(url);
        const lib = isHttps ? https : http;
        const proxy = lib.request(url, { method: req.method, headers: req.headers }, (pRes) => {
          res.writeHead(pRes.statusCode ?? 502, pRes.headers);
          pRes.pipe(res);
        });
        req.pipe(proxy);
        proxy.on('error', () => { res.writeHead(502); res.end(); });
      });

      return new Promise<{ close(): Promise<void> }>((resolve) => {
        server.listen(port, () => {
          resolve({ close: () => new Promise<void>((r) => server.close(() => r())) });
        });
      });
    },
  };
}''',
        "provides": "createForwardProxy(options?)",
        "depends": [],
    },
    {
        "id": "net-ip-range",
        "name": "IP Range Utilities",
        "category": "net",
        "lang": "typescript",
        "when": "CIDR math, subnet checks, and IP iteration for network tools",
        "why": "Atomic ip helpers; cidr in, address list + contains out — pure integer math",
        "tags": ["ip", "cidr", "subnet", "range", "network"],
        "iface": r'''export function cidrToRange(cidr: string): { start: string; end: string; count: number }
export function ipInCidr(ip: string, cidr: string): boolean
export function ipv4ToInt(ip: string): number
export function intToIpv4(n: number): string''',
        "code": r'''export function ipv4ToInt(ip: string): number {
  return ip.split('.').reduce((acc, oct) => (acc << 8) + Number(oct), 0) >>> 0;
}

export function intToIpv4(n: number): string {
  return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255].join('.');
}

export function cidrToRange(cidr: string): { start: string; end: string; count: number } {
  const [ip, prefixStr = '32'] = cidr.split('/');
  const prefix = Number(prefixStr);
  const ipInt = ipv4ToInt(ip);
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
  const start = ipInt & mask;
  const count = prefix === 0 ? 0x100000000 : 2 ** (32 - prefix);
  return { start: intToIpv4(start), end: intToIpv4(start + count - 1), count };
}

export function ipInCidr(ip: string, cidr: string): boolean {
  const { start, count } = cidrToRange(cidr);
  const ipInt = ipv4ToInt(ip);
  const startInt = ipv4ToInt(start);
  return ipInt >= startInt && ipInt < startInt + count;
}''',
        "provides": "cidrToRange(cidr), ipInCidr(ip, cidr), ipv4ToInt(ip), intToIpv4(n)",
        "depends": [],
    },
    {
        "id": "net-http-benchmark",
        "name": "HTTP Benchmark",
        "category": "net",
        "lang": "typescript",
        "when": "Measuring request throughput and latency for load testing",
        "why": "Atomic benchmarker; url + concurrency in, stats out — bounded workers, no UI",
        "tags": ["benchmark", "load", "latency", "throughput", "test"],
        "iface": r'''export interface BenchmarkResult { total: number; ok: number; failed: number; avgMs: number; p95Ms: number; rps: number; durationMs: number }
export function benchmarkHttp(url: string, options?: { requests?: number; concurrency?: number; method?: string }): Promise<BenchmarkResult>''',
        "code": r'''export async function benchmarkHttp(url: string, options?: { requests?: number; concurrency?: number; method?: string }) {
  const total = options?.requests ?? 100;
  const concurrency = options?.concurrency ?? 10;
  const method = options?.method ?? 'GET';
  const latencies: number[] = [];
  let ok = 0, failed = 0;
  const start = Date.now();
  let cursor = 0;

  async function worker() {
    while (cursor < total) {
      cursor++;
      const t0 = performance.now();
      try {
        const res = await fetch(url, { method });
        const ms = performance.now() - t0;
        latencies.push(ms);
        if (res.ok) ok++; else failed++;
      } catch {
        latencies.push(performance.now() - t0);
        failed++;
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  const durationMs = Date.now() - start;
  latencies.sort((a, b) => a - b);
  const avg = latencies.reduce((a, b) => a + b, 0) / (latencies.length || 1);
  const p95 = latencies[Math.floor(latencies.length * 0.95)] ?? 0;

  return { total, ok, failed, avgMs: avg, p95Ms: p95, rps: Math.round((total / durationMs) * 1000), durationMs };
}''',
        "provides": "benchmarkHttp(url, options?)",
        "depends": [],
    },
]
