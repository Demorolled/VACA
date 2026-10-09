# -*- coding: utf-8 -*-
"""
Code Bible — Category 27: Filesystem & Storage Helpers (atomic).
Convention: Node-style path strings ('/' separators), pure helpers, no deps.
"""
CHUNKS = [
    {
        "id": "fsys-path-normalize",
        "name": "Path Normalizer",
        "category": "fsys",
        "lang": "typescript",
        "when": "Resolving '.', '..', and duplicate separators in a path string",
        "why": "Atomic path resolver — stack-based segments, handles absolute/relative",
        "tags": ["fsys", "path", "normalize", "resolve", "segments"],
        "iface": r'''export function normalizePath(path: string): string''',
        "code": r'''export function normalizePath(path: string) {
  const absolute = path.startsWith('/');
  const stack: string[] = [];
  for (const seg of path.split('/')) {
    if (!seg || seg === '.') continue;
    if (seg === '..') { if (stack.length && stack[stack.length - 1] !== '..') stack.pop(); else if (!absolute) stack.push('..'); }
    else stack.push(seg);
  }
  return (absolute ? '/' : '') + stack.join('/');
}''',
        "provides": "normalizePath(path)",
        "depends": [],
    },
    {
        "id": "fsys-safe-filename",
        "name": "Safe Filename Sanitizer",
        "category": "fsys",
        "lang": "typescript",
        "when": "Sanitizing user input into a filesystem-safe filename",
        "why": "Atomic sanitizer — strips separators and control chars, caps length, keeps extension",
        "tags": ["fsys", "filename", "sanitize", "safe", "security"],
        "iface": r'''export function safeFilename(name: string, maxLength = 100): string''',
        "code": r'''export function safeFilename(name: string, maxLength = 100) {
  const cleaned = name
    .replace(/[\/\\:*?"<>|\x00-\x1f]/g, '_')
    .replace(/^\.+/, '')
    .replace(/[. ]+$/g, '')
    .slice(0, maxLength)
    .trim();
  return cleaned || 'untitled';
}''',
        "provides": "safeFilename(name, maxLength?)",
        "depends": [],
    },
    {
        "id": "fsys-extension-map",
        "name": "Extension to MIME Map",
        "category": "fsys",
        "lang": "typescript",
        "when": "Looking up a MIME type from a file extension",
        "why": "Atomic extension table — common web/media types, fallback octet-stream",
        "tags": ["fsys", "extension", "mime", "file-type", "lookup"],
        "iface": r'''export function mimeFromExtension(filename: string): string''',
        "code": r'''const MIME: Record<string, string> = {
  html: 'text/html', htm: 'text/html', css: 'text/css', js: 'text/javascript',
  mjs: 'text/javascript', json: 'application/json', jsonl: 'application/x-ndjson',
  md: 'text/markdown', txt: 'text/plain', csv: 'text/csv', xml: 'application/xml',
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif',
  svg: 'image/svg+xml', webp: 'image/webp', ico: 'image/x-icon',
  mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg', mp4: 'video/mp4', webm: 'video/webm',
  pdf: 'application/pdf', zip: 'application/zip', gz: 'application/gzip', tar: 'application/x-tar',
  wasm: 'application/wasm', ts: 'text/x.typescript', py: 'text/x-python',
};
export function mimeFromExtension(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  return MIME[ext] ?? 'application/octet-stream';
}''',
        "provides": "mimeFromExtension(filename)",
        "depends": [],
    },
    {
        "id": "fsys-atomic-rename",
        "name": "Atomic Rename",
        "category": "fsys",
        "lang": "typescript",
        "when": "Replacing a file without a partial-write window (write temp, then rename)",
        "why": "Atomic write-then-rename — caller supplies fs ops so it stays dependency-free",
        "tags": ["fsys", "atomic", "rename", "write", "safe"],
        "iface": r'''export interface FsOps {
  writeFile(path: string, data: string): Promise<void>
  rename(from: string, to: string): Promise<void>
  unlink(path: string): Promise<void>
}
export async function atomicWrite(ops: FsOps, target: string, data: string, tmp = target + '.tmp'): Promise<void>''',
        "code": r'''export async function atomicWrite(ops: FsOps, target: string, data: string, tmp = target + '.tmp') {
  await ops.writeFile(tmp, data);
  try { await ops.rename(tmp, target); }
  catch (err) { await ops.unlink(tmp).catch(() => undefined); throw err; }
}''',
        "provides": "atomicWrite(ops, target, data, tmp?)",
        "depends": [],
    },
    {
        "id": "fsys-dir-tree",
        "name": "Directory Tree Renderer",
        "category": "fsys",
        "lang": "typescript",
        "when": "Rendering a nested file tree as an ASCII/indented listing",
        "why": "Atomic tree formatter — takes a nested map, emits box-drawing or plain lines",
        "tags": ["fsys", "tree", "directory", "render", "ascii"],
        "iface": r'''export interface TreeEntry { name: string; children?: TreeEntry[] }
export function renderTree(entries: TreeEntry[], style: 'plain' | 'box' = 'box'): string''',
        "code": r'''export function renderTree(entries: TreeEntry[], style: 'plain' | 'box' = 'box') {
  const lines: string[] = [];
  const walk = (items: TreeEntry[], prefix: string) => {
    items.forEach((entry, i) => {
      const last = i === items.length - 1;
      const connector = style === 'box' ? (last ? '└── ' : '├── ') : '  ';
      lines.push(prefix + connector + entry.name);
      if (entry.children?.length) walk(entry.children, prefix + (style === 'box' ? (last ? '    ' : '│   ') : '  '));
    });
  };
  walk(entries, '');
  return lines.join('\n');
}''',
        "provides": "renderTree(entries, style?)",
        "depends": [],
    },
    {
        "id": "fsys-file-split",
        "name": "File Splitter/Joiner",
        "category": "fsys",
        "lang": "typescript",
        "when": "Splitting a large payload into numbered parts and rejoining them",
        "why": "Atomic part indexer — chunk sizes in, part map out, reassembly order preserved",
        "tags": ["fsys", "split", "join", "chunk", "parts"],
        "iface": r'''export function splitParts(totalBytes: number, partSize: number): Array<{ index: number; start: number; end: number }>''',
        "code": r'''export function splitParts(totalBytes: number, partSize: number) {
  const parts: Array<{ index: number; start: number; end: number }> = [];
  if (partSize <= 0) throw new Error('partSize must be > 0');
  for (let start = 0; start < totalBytes; start += partSize) {
    parts.push({ index: parts.length, start, end: Math.min(start + partSize, totalBytes) });
  }
  return parts;
}''',
        "provides": "splitParts(totalBytes, partSize)",
        "depends": [],
    },
    {
        "id": "fsys-chunked-reader",
        "name": "Chunked File Reader",
        "category": "fsys",
        "lang": "typescript",
        "when": "Streaming a file in fixed-size chunks for progress or memory limits",
        "why": "Atomic chunk iterator — async generator over offsets, caller controls flow",
        "tags": ["fsys", "chunk", "stream", "reader", "iterator"],
        "iface": r'''export async function* readChunks(read: (offset: number, length: number) => Promise<Uint8Array>, total: number, chunkSize: number): AsyncGenerator<Uint8Array>''',
        "code": r'''export async function* readChunks(read: (offset: number, length: number) => Promise<Uint8Array>, total: number, chunkSize: number) {
  for (let offset = 0; offset < total; offset += chunkSize) {
    yield await read(offset, Math.min(chunkSize, total - offset));
  }
}''',
        "provides": "readChunks(read, total, chunkSize)",
        "depends": [],
    },
    {
        "id": "fsys-buffered-writer",
        "name": "Buffered Writer",
        "category": "fsys",
        "lang": "typescript",
        "when": "Batching many small writes into fewer, larger flushes",
        "why": "Atomic buffer + flush — accumulate until size or explicit flush, then drain",
        "tags": ["fsys", "buffer", "writer", "batch", "flush"],
        "iface": r'''export class BufferedWriter {
  constructor(flush: (chunk: string) => Promise<void>, maxBuffer = 64 * 1024)
  write(text: string): Promise<void>
  flush(): Promise<void>
}''',
        "code": r'''export class BufferedWriter {
  private buffer = '';
  constructor(private flush: (chunk: string) => Promise<void>, private maxBuffer = 64 * 1024) {}
  async write(text: string) {
    this.buffer += text;
    if (this.buffer.length >= this.maxBuffer) await this.flush();
  }
  async flush() {
    if (this.buffer) { await this.flush(this.buffer); this.buffer = ''; }
  }
}''',
        "provides": "BufferedWriter",
        "depends": [],
    },
    {
        "id": "fsys-temp-file",
        "name": "Temp File Allocator",
        "category": "fsys",
        "lang": "typescript",
        "when": "Generating collision-free temporary file names with cleanup tracking",
        "why": "Atomic temp-name generator — counter+time+random, optional cleanup registry",
        "tags": ["fsys", "temp", "temporary", "unique", "cleanup"],
        "iface": r'''export function tempName(prefix = 'tmp', extension = 'tmp', existing: Set<string> = new Set()): string''',
        "code": r'''export function tempName(prefix = 'tmp', extension = 'tmp', existing: Set<string> = new Set()) {
  let name = '';
  do {
    name = `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}.${extension}`;
  } while (existing.has(name));
  existing.add(name);
  return name;
}''',
        "provides": "tempName(prefix?, extension?, existing?)",
        "depends": [],
    },
    {
        "id": "fsys-disk-usage",
        "name": "Disk Usage Aggregator",
        "category": "fsys",
        "lang": "typescript",
        "when": "Summing sizes across a tree and reporting per-directory totals",
        "why": "Atomic size aggregator — walk entries, accumulate, sort biggest first",
        "tags": ["fsys", "disk", "usage", "size", "aggregate"],
        "iface": r'''export interface SizedEntry { name: string; size: number; children?: SizedEntry[] }
export function diskUsage(root: SizedEntry): { total: number; perDir: Array<{ name: string; size: number }> }''',
        "code": r'''export function diskUsage(root: SizedEntry) {
  let total = 0;
  const perDir: Array<{ name: string; size: number }> = [];
  const walk = (e: SizedEntry, path: string) => {
    let size = e.size;
    for (const c of e.children ?? []) size += walk(c, path + '/' + e.name).total;
    total += size;
    if (e.children) perDir.push({ name: path + '/' + e.name, size });
    return { total: size };
  };
  walk(root, '');
  return { total, perDir: perDir.sort((a, b) => b.size - a.size) };
}''',
        "provides": "diskUsage(root)",
        "depends": [],
    },
    {
        "id": "fsys-recursive-delete",
        "name": "Recursive Delete",
        "category": "fsys",
        "lang": "typescript",
        "when": "Deleting a directory tree with safety guards (never root or home)",
        "why": "Atomic guarded deleter — deny-list of dangerous roots, ordered children-first",
        "tags": ["fsys", "delete", "recursive", "guard", "safe"],
        "iface": r'''export async function deleteTree(remove: (path: string) => Promise<void>, isDir: (path: string) => Promise<boolean>, read: (path: string) => Promise<string[]>, root: string): Promise<void>''',
        "code": r'''const DENY = new Set(['/', '', '.', '..', process?.env?.HOME ?? '']);
export async function deleteTree(remove: (p: string) => Promise<void>, isDir: (p: string) => Promise<boolean>, read: (p: string) => Promise<string[]>, root: string) {
  const real = root.replace(/\/+$/, '') || '/';
  if (DENY.has(real)) throw new Error(`Refusing to delete ${real}`);
  if (await isDir(real)) {
    for (const child of await read(real)) await deleteTree(remove, isDir, read, real + '/' + child);
  }
  await remove(real);
}''',
        "provides": "deleteTree(remove, isDir, read, root)",
        "depends": [],
    },
    {
        "id": "fsys-dir-checksum",
        "name": "Directory Checksum",
        "category": "fsys",
        "lang": "typescript",
        "when": "Fingerprinting a directory's contents to detect any change",
        "why": "Atomic content fingerprint — path+hash lines folded into one digest via a pluggable hash",
        "tags": ["fsys", "checksum", "fingerprint", "directory", "change-detect"],
        "iface": r'''export function dirFingerprint(files: Array<{ path: string; hash: string }>, hashFn: (s: string) => string): string''',
        "code": r'''export function dirFingerprint(files: Array<{ path: string; hash: string }>, hashFn: (s: string) => string) {
  const lines = files.map((f) => `${f.path}:${f.hash}`).sort().join('\n');
  return hashFn(lines);
}''',
        "provides": "dirFingerprint(files, hashFn)",
        "depends": [],
    },
    {
        "id": "fsys-offset-reader",
        "name": "Offset File Reader",
        "category": "fsys",
        "lang": "typescript",
        "when": "Reading a byte range of a file without loading the whole thing",
        "why": "Atomic range reader — offset+length in, decoded text out, clamped",
        "tags": ["fsys", "offset", "range", "reader", "partial"],
        "iface": r'''export async function readRange(read: (offset: number, length: number) => Promise<Uint8Array>, total: number, offset: number, length: number, decode: (b: Uint8Array) => string = (b) => new TextDecoder().decode(b)): Promise<string>''',
        "code": r'''export async function readRange(read: (offset: number, length: number) => Promise<Uint8Array>, total: number, offset: number, length: number, decode: (b: Uint8Array) => string = (b) => new TextDecoder().decode(b)) {
  const start = Math.max(0, Math.min(offset, total));
  const end = Math.min(total, start + Math.max(0, length));
  if (start >= end) return '';
  return decode(await read(start, end - start));
}''',
        "provides": "readRange(read, total, offset, length, decode?)",
        "depends": [],
    },
    {
        "id": "fsys-jsonl-stream",
        "name": "JSONL Stream Reader",
        "category": "fsys",
        "lang": "typescript",
        "when": "Parsing a newline-delimited JSON file one record at a time",
        "why": "Atomic JSONL splitter — handles CRLF, skips blanks, tolerant per-line parse",
        "tags": ["fsys", "jsonl", "stream", "parser", "ndjson"],
        "iface": r'''export function parseJsonl(text: string): unknown[]
export function* iterateJsonl(text: string): Generator<unknown>''',
        "code": r'''export function* iterateJsonl(text: string) {
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try { yield JSON.parse(line); } catch { /* skip malformed line */ }
  }
}
export function parseJsonl(text: string) { return [...iterateJsonl(text)]; }''',
        "provides": "parseJsonl / iterateJsonl",
        "depends": [],
    },
    {
        "id": "fsys-binary-header",
        "name": "Binary Header Reader",
        "category": "fsys",
        "lang": "typescript",
        "when": "Reading fixed-width header fields from binary data",
        "why": "Atomic header decoder — offsets into fields, DataView-based, little-endian default",
        "tags": ["fsys", "binary", "header", "parse", "data-view"],
        "iface": r'''export function readHeader(buffer: ArrayBuffer, fields: Array<{ name: string; offset: number; type: 'u8' | 'u16' | 'u32' | 'f32' | 'ascii' | 'utf8'; length?: number }>): Record<string, number | string>''',
        "code": r'''export function readHeader(buffer: ArrayBuffer, fields: Array<{ name: string; offset: number; type: 'u8' | 'u16' | 'u32' | 'f32' | 'ascii' | 'utf8'; length?: number }>) {
  const dv = new DataView(buffer);
  const out: Record<string, number | string> = {};
  for (const f of fields) {
    switch (f.type) {
      case 'u8': out[f.name] = dv.getUint8(f.offset); break;
      case 'u16': out[f.name] = dv.getUint16(f.offset, true); break;
      case 'u32': out[f.name] = dv.getUint32(f.offset, true); break;
      case 'f32': out[f.name] = dv.getFloat32(f.offset, true); break;
      case 'ascii': case 'utf8': {
        const bytes = new Uint8Array(buffer, f.offset, f.length ?? 0);
        out[f.name] = new TextDecoder(f.type === 'utf8' ? 'utf-8' : 'ascii').decode(bytes).replace(/\0+$/, '');
        break;
      }
    }
  }
  return out;
}''',
        "provides": "readHeader(buffer, fields)",
        "depends": [],
    },
    {
        "id": "fsys-home-expand",
        "name": "Home Path Expander",
        "category": "fsys",
        "lang": "typescript",
        "when": "Expanding '~' and environment variables inside a path",
        "why": "Atomic expander — ~ to home, $VAR to env, configurable env map",
        "tags": ["fsys", "home", "tilde", "expand", "env"],
        "iface": r'''export function expandPath(path: string, env: Record<string, string> = process?.env ?? {}): string''',
        "code": r'''export function expandPath(path: string, env: Record<string, string> = (process?.env ?? {}) as Record<string, string>) {
  let out = path;
  if (out.startsWith('~')) out = (env.HOME ?? env.USERPROFILE ?? '') + out.slice(1);
  out = out.replace(/\$(\w+)/g, (_, name) => env[name] ?? '');
  return out;
}''',
        "provides": "expandPath(path, env?)",
        "depends": [],
    },
    {
        "id": "fsys-sort-by-size",
        "name": "Sort Files by Size",
        "category": "fsys",
        "lang": "typescript",
        "when": "Ranking files/directories by size for cleanup or analytics",
        "why": "Atomic sorter — entry list in, size-descending (or asc) ranking out",
        "tags": ["fsys", "sort", "size", "ranking", "cleanup"],
        "iface": r'''export function sortBySize<T>(entries: Array<{ name: string; size: number } & T>, ascending = false): Array<{ name: string; size: number } & T>''',
        "code": r'''export function sortBySize<T>(entries: Array<{ name: string; size: number } & T>, ascending = false) {
  return entries.slice().sort((a, b) => (ascending ? a.size - b.size : b.size - a.size));
}''',
        "provides": "sortBySize(entries, ascending?)",
        "depends": [],
    },
    {
        "id": "fsys-dedupe-hash",
        "name": "Dedupe by Hash",
        "category": "fsys",
        "lang": "typescript",
        "when": "Finding duplicate files or entries by content hash",
        "why": "Atomic dedupe — group by hash, report first-copy vs duplicates",
        "tags": ["fsys", "dedupe", "hash", "duplicate", "group"],
        "iface": r'''export function groupByHash(items: Array<{ path: string; hash: string }>): Array<{ hash: string; copies: string[] }>''',
        "code": r'''export function groupByHash(items: Array<{ path: string; hash: string }>) {
  const groups = new Map<string, string[]>();
  for (const it of items) {
    if (!groups.has(it.hash)) groups.set(it.hash, []);
    groups.get(it.hash)!.push(it.path);
  }
  return [...groups.entries()].map(([hash, copies]) => ({ hash, copies }));
}''',
        "provides": "groupByHash(items)",
        "depends": [],
    },
    {
        "id": "fsys-staging-dir",
        "name": "Staging Directory",
        "category": "fsys",
        "lang": "typescript",
        "when": "Collecting files into a temp staging area, then promoting on success",
        "why": "Atomic stage/commit — stage names, promote all, rollback clears partial state",
        "tags": ["fsys", "staging", "commit", "transaction", "temp"],
        "iface": r'''export class StagingDir {
  stage(name: string): string
  commit(): string[]
  rollback(): void
}''',
        "code": r'''export class StagingDir {
  private staged: string[] = [];
  constructor(private base: string) {}
  stage(name: string) {
    const path = `${this.base}/${name}`;
    this.staged.push(path);
    return path;
  }
  commit() { const out = this.staged.splice(0); return out; }
  rollback() { this.staged = []; }
}''',
        "provides": "StagingDir",
        "depends": [],
    },
    {
        "id": "fsys-copy-tree",
        "name": "Copy Tree",
        "category": "fsys",
        "lang": "typescript",
        "when": "Mirroring a directory tree with optional filtering",
        "why": "Atomic copy plan — source entries in, (destPath, copy) list out, filterable",
        "tags": ["fsys", "copy", "tree", "mirror", "filter"],
        "iface": r'''export function copyPlan(entries: Array<{ path: string; isDir: boolean }>, filter?: (path: string) => boolean): string[]''',
        "code": r'''export function copyPlan(entries: Array<{ path: string; isDir: boolean }>, filter: (path: string) => boolean = () => true) {
  return entries.filter((e) => filter(e.path)).map((e) => e.path);
}''',
        "provides": "copyPlan(entries, filter?)",
        "depends": [],
    },
    {
        "id": "fsys-line-counter",
        "name": "Streaming Line Counter",
        "category": "fsys",
        "lang": "typescript",
        "when": "Counting lines and characters without loading the file into memory",
        "why": "Atomic counter — scan chunks for newlines, tolerate partial final line",
        "tags": ["fsys", "line", "count", "stream", "wc"],
        "iface": r'''export function countLines(chunks: Iterable<string>): { lines: number; chars: number }''',
        "code": r'''export function countLines(chunks: Iterable<string>) {
  let lines = 0, chars = 0;
  for (const c of chunks) {
    chars += c.length;
    lines += (c.match(/\n/g) ?? []).length;
  }
  return { lines, chars };
}''',
        "provides": "countLines(chunks)",
        "depends": [],
    },
    {
        "id": "fsys-tail-reader",
        "name": "Tail Reader (Last N Lines)",
        "category": "fsys",
        "lang": "typescript",
        "when": "Reading the last N lines of a file without scanning from the start",
        "why": "Atomic reverse scan — walk back through the buffer collecting line ends",
        "tags": ["fsys", "tail", "last-lines", "reader", "reverse"],
        "iface": r'''export function tailLines(text: string, n: number): string''',
        "code": r'''export function tailLines(text: string, n: number) {
  if (n <= 0) return '';
  const lines = text.split(/\r?\n/);
  return lines.slice(-n).join('\n');
}''',
        "provides": "tailLines(text, n)",
        "depends": [],
    },
    {
        "id": "fsys-find-dup-names",
        "name": "Duplicate Name Finder",
        "category": "fsys",
        "lang": "typescript",
        "when": "Flagging case-insensitive name collisions across a folder",
        "why": "Atomic collision scan — fold-case map, report groups with origins",
        "tags": ["fsys", "duplicate", "collision", "names", "case"],
        "iface": r'''export function findNameCollisions(names: string[]): Array<{ key: string; names: string[] }>''',
        "code": r'''export function findNameCollisions(names: string[]) {
  const map = new Map<string, string[]>();
  for (const n of names) {
    const key = n.toLowerCase();
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(n);
  }
  return [...map.entries()].filter(([, v]) => v.length > 1).map(([key, names2]) => ({ key, names: names2 }));
}''',
        "provides": "findNameCollisions(names)",
        "depends": [],
    },
    {
        "id": "fsys-path-join",
        "name": "Path Join/Resolve",
        "category": "fsys",
        "lang": "typescript",
        "when": "Joining path segments with clean separator handling",
        "why": "Atomic joiner — one separator, no doubles, '.' and '..' honored via normalize",
        "tags": ["fsys", "path", "join", "resolve", "segments"],
        "iface": r'''export function joinPaths(...segments: string[]): string''',
        "code": r'''export function joinPaths(...segments: string[]) {
  const cleaned = segments.filter((s) => s && s !== '.');
  const out = cleaned.join('/').replace(/\/+/g, '/');
  return out === '' ? '.' : out;
}''',
        "provides": "joinPaths(...segments)",
        "depends": [],
    },
    {
        "id": "fs-recent-files",
        "name": "Recent Files Sorter",
        "category": "fsys",
        "lang": "typescript",
        "when": "Sorting a file list by modified time, newest first",
        "why": "Atomic sorter \u2014 files + optional count in, newest-first slice out",
        "tags": [
            "fsys",
            "recent",
            "sort",
            "modified",
            "files"
        ],
        "iface": "export interface FileMeta { path: string; modifiedMs: number }\nexport function recentFiles(files: FileMeta[], limit?: number): FileMeta[]",
        "code": "export function recentFiles(files: FileMeta[], limit?: number) {\n  const sorted = files.slice().sort((a, b) => b.modifiedMs - a.modifiedMs);\n  return limit === undefined ? sorted : sorted.slice(0, limit);\n}",
        "provides": "recentFiles(files, limit)",
        "depends": []
    },
]
