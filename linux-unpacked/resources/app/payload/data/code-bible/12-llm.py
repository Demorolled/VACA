# -*- coding: utf-8 -*-
"""
Code Bible — Category 12: LLM & RAG (atomic, single-responsibility).
Convention: pure helpers for prompt assembly, retrieval, and output parsing.
"""
CHUNKS = [
    {
        "id": "llm-chat-memory",
        "name": "Chat Memory Ring Buffer",
        "category": "llm",
        "lang": "typescript",
        "when": "Keeping only the most recent N turns of a conversation for the model",
        "why": "Atomic bounded history: push in, auto-evict oldest, ready-to-send array out",
        "tags": ["llm", "memory", "ring", "buffer", "history", "context"],
        "iface": r'''export interface ChatTurn { role: 'user' | 'assistant' | 'system'; content: string }
export class ChatMemory {
  constructor(capacity?: number)
  add(turn: ChatTurn): void
  clear(): void
  get messages(): ChatTurn[]
}''',
        "code": r'''export class ChatMemory {
  private turns: ChatTurn[] = [];
  constructor(private capacity = 20) {}
  add(turn: ChatTurn) {
    this.turns.push(turn);
    if (this.turns.length > this.capacity) this.turns.splice(0, this.turns.length - this.capacity);
  }
  clear() { this.turns = []; }
  get messages() { return this.turns.slice(); }
}''',
        "provides": "ChatMemory",
        "depends": [],
    },
    {
        "id": "llm-prompt-template",
        "name": "Prompt Template Renderer",
        "category": "llm",
        "lang": "typescript",
        "when": "Filling {placeholders} in a prompt string with values",
        "why": "Atomic template engine: {{var}} interpolation with safe-to-miss semantics",
        "tags": ["llm", "prompt", "template", "render", "placeholder"],
        "iface": r'''export function renderPrompt(template: string, vars: Record<string, string | number>): string''',
        "code": r'''export function renderPrompt(template: string, vars: Record<string, string | number>) {
  return template.replace(/\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g, (_, key: string) =>
    key in vars ? String(vars[key]) : '');
}''',
        "provides": "renderPrompt(template, vars)",
        "depends": [],
    },
    {
        "id": "llm-token-estimate",
        "name": "Token Estimate (chars→tokens)",
        "category": "llm",
        "lang": "typescript",
        "when": "Budgeting prompts before a call without running a real tokenizer",
        "why": "Atomic heuristic: ~4 chars/token for English text, plus explicit word-based floor",
        "tags": ["llm", "token", "estimate", "budget", "count"],
        "iface": r'''export function estimateTokens(text: string): number
export function truncateToTokens(text: string, maxTokens: number, suffix?: string): string''',
        "code": r'''export function estimateTokens(text: string) {
  const chars = text.length;
  return Math.max(Math.ceil(chars / 4), (text.trim().match(/\S+/g) ?? []).length);
}
export function truncateToTokens(text: string, maxTokens: number, suffix = '…') {
  const budget = maxTokens * 4;
  return text.length <= budget ? text : text.slice(0, budget - suffix.length) + suffix;
}''',
        "provides": "estimateTokens / truncateToTokens",
        "depends": [],
    },
    {
        "id": "llm-rag-retriever",
        "name": "RAG Top-K Retriever",
        "category": "llm",
        "lang": "typescript",
        "when": "Pulling the most relevant document chunks for a query by embedding distance",
        "why": "Atomic retriever: query + chunks + scorer in, top-k with scores out",
        "tags": ["llm", "rag", "retriever", "topk", "embedding", "search"],
        "iface": r'''export interface RetrieverDoc { id: string; text: string; vector: number[] }
export function retrieveTopK(query: number[], docs: RetrieverDoc[], k = 3): Array<{ doc: RetrieverDoc; score: number }>''',
        "code": r'''function cosine(a: number[], b: number[]) {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  return dot / (Math.sqrt(na) * Math.sqrt(nb) || 1);
}
export function retrieveTopK(query: number[], docs: RetrieverDoc[], k = 3) {
  return docs
    .map((doc) => ({ doc, score: cosine(query, doc.vector) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}''',
        "provides": "retrieveTopK(query, docs, k)",
        "depends": [],
    },
    {
        "id": "llm-doc-chunker",
        "name": "Document Chunker (overlap)",
        "category": "llm",
        "lang": "typescript",
        "when": "Splitting long documents into embeddable chunks with context overlap",
        "why": "Atomic splitter: token budget + overlap, keeps whole lines, emits chunk metadata",
        "tags": ["llm", "chunk", "split", "overlap", "embedding", "rag"],
        "iface": r'''export interface Chunk { text: string; index: number; start: number }
export function chunkDocument(text: string, maxTokens = 500, overlapTokens = 50): Chunk[]''',
        "code": r'''export function chunkDocument(text: string, maxTokens = 500, overlapTokens = 50) {
  const lines = text.split('\n');
  const chunks: Chunk[] = [];
  let buf: string[] = []; let len = 0; let start = 0;
  for (const line of lines) {
    const lineLen = Math.max(1, Math.ceil(line.length / 4));
    if (len + lineLen > maxTokens && buf.length) {
      chunks.push({ text: buf.join('\n'), index: chunks.length, start });
      const overlapLines = buf.slice(-Math.max(1, Math.ceil(overlapTokens * 4 / 8)));
      buf = overlapLines; len = overlapLines.reduce((s, l) => s + Math.ceil(l.length / 4), 0);
      start += buf.length;
    }
    buf.push(line); len += lineLen;
  }
  if (buf.length) chunks.push({ text: buf.join('\n'), index: chunks.length, start });
  return chunks;
}''',
        "provides": "chunkDocument(text, maxTokens, overlapTokens)",
        "depends": [],
    },
    {
        "id": "llm-embedding-cache",
        "name": "Embedding Cache (LRU by hash)",
        "category": "llm",
        "lang": "typescript",
        "when": "Avoiding recomputation when the same text is embedded repeatedly",
        "why": "Atomic cache: content-hash key, LRU eviction, sync get-or-compute",
        "tags": ["llm", "embedding", "cache", "lru", "hash"],
        "iface": r'''export class EmbeddingCache {
  constructor(capacity?: number)
  getOrCompute(text: string, compute: (t: string) => number[]): number[]
  size(): number
}''',
        "code": r'''export class EmbeddingCache {
  private map = new Map<string, number[]>();
  constructor(private capacity = 1000) {}
  private key(text: string) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0).toString(16);
  }
  getOrCompute(text: string, compute: (t: string) => number[]) {
    const k = this.key(text);
    const hit = this.map.get(k);
    if (hit) { this.map.delete(k); this.map.set(k, hit); return hit; }
    const vec = compute(text);
    this.map.set(k, vec);
    if (this.map.size > this.capacity) this.map.delete(this.map.keys().next().value!);
    return vec;
  }
  size() { return this.map.size; }
}''',
        "provides": "EmbeddingCache",
        "depends": [],
    },
    {
        "id": "llm-json-extractor",
        "name": "JSON Mode Extractor",
        "category": "llm",
        "lang": "typescript",
        "when": "Extracting a valid JSON object from a model response that may include fences or prose",
        "why": "Atomic parser: strips code fences and leading prose, finds the balanced JSON object",
        "tags": ["llm", "json", "parse", "extract", "fence"],
        "iface": r'''export function extractJson<T = unknown>(raw: string): T | null''',
        "code": r'''const FENCE = '`'.repeat(3);
export function extractJson<T = unknown>(raw: string): T | null {
  const fenced = raw.match(new RegExp(`${FENCE}(?:json)?\\s*([\\s\\S]*?)${FENCE}`));
  const candidate = fenced ? fenced[1] : raw;
  const start = candidate.indexOf('{');
  if (start < 0) return null;
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < candidate.length; i++) {
    const ch = candidate[i];
    if (esc) { esc = false; continue; }
    if (ch === '\\' && inStr) { esc = true; continue; }
    if (ch === '"') inStr = !inStr;
    if (inStr) continue;
    if (ch === '{') depth++;
    else if (ch === '}') { depth--; if (depth === 0) {
      try { return JSON.parse(candidate.slice(start, i + 1)) as T; } catch { return null; }
    } }
  }
  return null;
}''',
        "provides": "extractJson(raw)",
        "depends": [],
    },
    {
        "id": "llm-tool-call-parser",
        "name": "Tool-Call Parser",
        "category": "llm",
        "lang": "typescript",
        "when": "Parsing a model's emitted function-call into name + arguments",
        "why": "Atomic parser: handles both JSON-shaped calls and name(args) textual calls",
        "tags": ["llm", "tool", "function", "call", "parse"],
        "iface": r'''export interface ToolCall { name: string; args: Record<string, unknown> }
export function parseToolCall(text: string): ToolCall | null''',
        "code": r'''export function parseToolCall(text: string): ToolCall | null {
  const json = text.match(/\{\s*"name"\s*:\s*"([^"]+)"[\s\S]*?"arguments"\s*:\s*(\{[\s\S]*?\})\s*\}/);
  if (json) {
    try { return { name: json[1], args: JSON.parse(json[2]) }; } catch { /* fall through */ }
  }
  const call = text.match(/([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*(\{[\s\S]*?\})\s*\)/);
  if (call) {
    try { return { name: call[1], args: JSON.parse(call[2]) }; } catch { /* fall through */ }
  }
  return null;
}''',
        "provides": "parseToolCall(text)",
        "depends": [],
    },
    {
        "id": "llm-stream-accumulator",
        "name": "Streaming Token Accumulator",
        "category": "llm",
        "lang": "typescript",
        "when": "Aggregating streaming chunks into a full response with deltas",
        "why": "Atomic accumulator: chunks in, joined text + last delta out, no async state",
        "tags": ["llm", "stream", "accumulator", "chunk", "delta"],
        "iface": r'''export class StreamAccumulator {
  push(delta: string): void
  get text(): string
  get lastDelta(): string
  reset(): void
}''',
        "code": r'''export class StreamAccumulator {
  private parts: string[] = [];
  private last = '';
  push(delta: string) { this.last = delta; this.parts.push(delta); }
  get text() { return this.parts.join(''); }
  get lastDelta() { return this.last; }
  reset() { this.parts = []; this.last = ''; }
}''',
        "provides": "StreamAccumulator",
        "depends": [],
    },
    {
        "id": "llm-stop-detector",
        "name": "Stop-Sequence Detector",
        "category": "llm",
        "lang": "typescript",
        "when": "Ending streaming early when the model emits a stop token like </s> or END",
        "why": "Atomic detector: buffer tail scan against stop strings, returns matched stop",
        "tags": ["llm", "stop", "sequence", "stream", "detector"],
        "iface": r'''export function detectStop(buffer: string, stops: string[]): { matched: string; index: number } | null''',
        "code": r'''export function detectStop(buffer: string, stops: string[]) {
  for (const stop of stops) {
    const idx = buffer.indexOf(stop);
    if (idx >= 0) return { matched: stop, index: idx };
  }
  return null;
}''',
        "provides": "detectStop(buffer, stops)",
        "depends": [],
    },
    {
        "id": "llm-context-assembler",
        "name": "Context Assembler (system+history+rag)",
        "category": "llm",
        "lang": "typescript",
        "when": "Building the final message array with budget enforcement",
        "why": "Atomic assembler: system, retrieved chunks, history in; fitted message list out",
        "tags": ["llm", "context", "assemble", "messages", "budget"],
        "iface": r'''export interface AssemblerInput {
  system: string; userQuery: string; retrieved?: string[]; history?: Array<{ role: 'user' | 'assistant'; content: string }>; maxTokens?: number
}
export function assembleMessages(input: AssemblerInput): Array<{ role: string; content: string }>''',
        "code": r'''export function assembleMessages(input: AssemblerInput) {
  const sysTokens = Math.ceil(input.system.length / 4);
  const queryTokens = Math.ceil(input.userQuery.length / 4);
  let budget = (input.maxTokens ?? 2048) - sysTokens - queryTokens;
  const messages: Array<{ role: string; content: string }> = [
    { role: 'system', content: input.system },
  ];
  const rag: string[] = [];
  for (const chunk of input.retrieved ?? []) {
    const t = Math.ceil(chunk.length / 4);
    if (t > budget) break;
    rag.push(chunk); budget -= t;
  }
  if (rag.length) messages.push({ role: 'user', content: 'CONTEXT:\n' + rag.join('\n---\n') });
  for (const turn of input.history ?? []) {
    const t = Math.ceil(turn.content.length / 4);
    if (t > budget) break;
    messages.push(turn); budget -= t;
  }
  messages.push({ role: 'user', content: input.userQuery });
  return messages;
}''',
        "provides": "assembleMessages(input)",
        "depends": [],
    },
    {
        "id": "llm-dedupe",
        "name": "Semantic Dedupe",
        "category": "llm",
        "lang": "typescript",
        "when": "Filtering near-identical retrieved chunks or answers",
        "why": "Atomic deduper: similarity threshold on normalized text, first-wins order kept",
        "tags": ["llm", "dedupe", "similarity", "filter", "duplicate"],
        "iface": r'''export function dedupeBySimilarity(items: string[], threshold = 0.85): string[]''',
        "code": r'''function jaccard(a: Set<string>, b: Set<string>) {
  let inter = 0;
  for (const x of a) if (b.has(x)) inter++;
  return inter / (a.size + b.size - inter || 1);
}
function shingles(text: string) {
  const t = text.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').trim();
  const words = t.split(/\s+/).filter(Boolean);
  const out = new Set<string>();
  for (let i = 0; i + 2 <= words.length; i++) out.add(words[i] + ' ' + words[i + 1]);
  return out;
}
export function dedupeBySimilarity(items: string[], threshold = 0.85) {
  const kept: string[] = [];
  for (const item of items) {
    const s = shingles(item);
    const dup = kept.some((k) => jaccard(s, shingles(k)) >= threshold);
    if (!dup) kept.push(item);
  }
  return kept;
}''',
        "provides": "dedupeBySimilarity(items, threshold)",
        "depends": [],
    },
    {
        "id": "llm-rerank-fusion",
        "name": "Rerank Score Fusion",
        "category": "llm",
        "lang": "typescript",
        "when": "Combining vector and lexical scores into one ranking",
        "why": "Atomic fusion: reciprocal-rank or weighted sum, single ranked list out",
        "tags": ["llm", "rerank", "fusion", "score", "ranking"],
        "iface": r'''export interface ScoredDoc { id: string; scores: Record<string, number>; weights?: Record<string, number> }
export function fusedRank(docs: ScoredDoc[]): Array<{ id: string; score: number }>''',
        "code": r'''export function fusedRank(docs: ScoredDoc[]) {
  const names = new Set<string>();
  for (const d of docs) for (const k of Object.keys(d.scores)) names.add(k);
  return docs
    .map((d) => {
      let score = 0;
      for (const k of names) score += (d.weights?.[k] ?? 1) * (d.scores[k] ?? 0);
      return { id: d.id, score };
    })
    .sort((a, b) => b.score - a.score);
}''',
        "provides": "fusedRank(docs)",
        "depends": [],
    },
    {
        "id": "llm-prompt-trimmer",
        "name": "Prompt Budget Trimmer",
        "category": "llm",
        "lang": "typescript",
        "when": "Fitting an oversized prompt under max_tokens by dropping the least important parts",
        "why": "Atomic trimmer: system/context/query priority, truncates context first",
        "tags": ["llm", "trim", "budget", "context", "max-tokens"],
        "iface": r'''export function trimPrompt(system: string, context: string[], query: string, maxTokens: number): { system: string; context: string[]; query: string }''',
        "code": r'''export function trimPrompt(system: string, context: string[], query: string, maxTokens: number) {
  const len = (s: string) => Math.ceil(s.length / 4);
  let budget = maxTokens - len(system) - len(query);
  const kept: string[] = [];
  for (const c of context) { if (len(c) > budget) break; kept.push(c); budget -= len(c); }
  return { system, context: kept, query };
}''',
        "provides": "trimPrompt(system, context, query, maxTokens)",
        "depends": [],
    },
    {
        "id": "llm-tool-dispatcher",
        "name": "Tool-Call Dispatcher",
        "category": "llm",
        "lang": "typescript",
        "when": "Routing a parsed tool name to its registered handler",
        "why": "Atomic registry: name + args in, handler result out, unknown names rejected",
        "tags": ["llm", "tool", "dispatch", "registry", "handler"],
        "iface": r'''export type ToolHandler = (args: Record<string, unknown>) => Promise<unknown> | unknown
export class ToolDispatcher {
  register(name: string, handler: ToolHandler): void
  dispatch(name: string, args: Record<string, unknown>): Promise<unknown>
  get names(): string[]
}''',
        "code": r'''export class ToolDispatcher {
  private handlers = new Map<string, ToolHandler>();
  register(name: string, handler: ToolHandler) { this.handlers.set(name, handler); }
  async dispatch(name: string, args: Record<string, unknown>) {
    const h = this.handlers.get(name);
    if (!h) throw new Error(`Unknown tool: ${name}`);
    return h(args);
  }
  get names() { return [...this.handlers.keys()]; }
}''',
        "provides": "ToolDispatcher",
        "depends": [],
    },
    {
        "id": "llm-reflection-loop",
        "name": "Reflection Loop (generate→critique→revise)",
        "category": "llm",
        "lang": "typescript",
        "when": "Improving a model's answer by critiquing and revising it in rounds",
        "why": "Atomic orchestrator: generate/critique/revise callbacks, max rounds, keeps best",
        "tags": ["llm", "reflection", "critique", "revise", "loop"],
        "iface": r'''export interface ReflectionCbs {
  generate(prompt: string): Promise<string>
  critique(answer: string): Promise<string>
  revise(prompt: string, answer: string, critique: string): Promise<string>
  score(answer: string): Promise<number>
}
export async function reflectionLoop(prompt: string, cbs: ReflectionCbs, maxRounds = 2): Promise<{ answer: string; rounds: number }>''',
        "code": r'''export async function reflectionLoop(prompt: string, cbs: ReflectionCbs, maxRounds = 2) {
  let answer = await cbs.generate(prompt);
  let best = answer, bestScore = await cbs.score(answer);
  for (let r = 0; r < maxRounds; r++) {
    const critique = await cbs.critique(answer);
    const revised = await cbs.revise(prompt, answer, critique);
    const s = await cbs.score(revised);
    if (s > bestScore) { bestScore = s; best = revised; }
    answer = revised;
  }
  return { answer: best, rounds: maxRounds + 1 };
}''',
        "provides": "reflectionLoop(prompt, cbs, maxRounds)",
        "depends": [],
    },
    {
        "id": "llm-vector-ranker",
        "name": "Embedding Cosine Ranker",
        "category": "llm",
        "lang": "typescript",
        "when": "Ordering candidates strictly by cosine similarity to a query vector",
        "why": "Atomic ranker: scores computed once, sorted desc, ties broken by index",
        "tags": ["llm", "vector", "ranker", "cosine", "similarity"],
        "iface": r'''export function rankByCosine(query: number[], candidates: Array<{ id: string; vector: number[] }>, k?: number): Array<{ id: string; score: number }>''',
        "code": r'''export function rankByCosine(query: number[], candidates: Array<{ id: string; vector: number[] }>, k?: number) {
  const scored = candidates.map((c) => {
    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < query.length; i++) { dot += query[i] * c.vector[i]; na += query[i] ** 2; nb += c.vector[i] ** 2; }
    return { id: c.id, score: dot / (Math.sqrt(na) * Math.sqrt(nb) || 1) };
  }).sort((a, b) => b.score - a.score);
  return k ? scored.slice(0, k) : scored;
}''',
        "provides": "rankByCosine(query, candidates, k)",
        "depends": [],
    },
    {
        "id": "llm-history-window",
        "name": "Sliding History Window",
        "category": "llm",
        "lang": "typescript",
        "when": "Keeping the most relevant recent turns plus any pinned first turn",
        "why": "Atomic window: user-specified head keep, tail cap, system/user separation preserved",
        "tags": ["llm", "history", "window", "slide", "turns"],
        "iface": r'''export function windowHistory(turns: Array<{ role: string; content: string }>, maxTurns: number, keepFirst = 1): Array<{ role: string; content: string }>''',
        "code": r'''export function windowHistory(turns: Array<{ role: string; content: string }>, maxTurns: number, keepFirst = 1) {
  if (turns.length <= maxTurns) return turns;
  const head = turns.slice(0, keepFirst);
  const tail = turns.slice(Math.max(keepFirst, turns.length - (maxTurns - keepFirst)));
  return [...head, ...tail];
}''',
        "provides": "windowHistory(turns, maxTurns, keepFirst)",
        "depends": [],
    },
    {
        "id": "llm-fence-checker",
        "name": "Instruction Adherence Checker",
        "category": "llm",
        "lang": "typescript",
        "when": "Validating a model's output obeys format rules like 'no code fences'",
        "why": "Atomic linter: rule predicates in, violations out, ready for retry prompts",
        "tags": ["llm", "adherence", "fence", "validate", "format"],
        "iface": r'''export interface AdherenceRule { name: string; test: (out: string) => boolean; hint: string }
export function checkAdherence(output: string, rules: AdherenceRule[]): Array<{ name: string; hint: string }>''',
        "code": r'''export function checkAdherence(output: string, rules: AdherenceRule[]) {
  return rules.filter((r) => !r.test(output)).map((r) => ({ name: r.name, hint: r.hint }));
}''',
        "provides": "checkAdherence(output, rules)",
        "depends": [],
    },
    {
        "id": "llm-batch-collector",
        "name": "Latency-Aware Batch Collector",
        "category": "llm",
        "lang": "typescript",
        "when": "Grouping queued prompts into a batch within a time budget",
        "why": "Atomic collector: push + flush timer, drains on size or timeout",
        "tags": ["llm", "batch", "collect", "queue", "latency"],
        "iface": r'''export class BatchCollector<T> {
  constructor(opts: { maxSize: number; flushMs: number; onFlush: (items: T[]) => void })
  push(item: T): void
  flush(): void
  get size(): number
}''',
        "code": r'''export class BatchCollector<T> {
  private items: T[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  constructor(private opts: { maxSize: number; flushMs: number; onFlush: (items: T[]) => void }) {}
  push(item: T) {
    this.items.push(item);
    if (this.items.length >= this.opts.maxSize) return this.flush();
    if (!this.timer) this.timer = setTimeout(() => this.flush(), this.opts.flushMs);
  }
  flush() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
    if (!this.items.length) return;
    const batch = this.items; this.items = [];
    this.opts.onFlush(batch);
  }
  get size() { return this.items.length; }
}''',
        "provides": "BatchCollector",
        "depends": [],
    },
    {
        "id": "llm-sources-formatter",
        "name": "Answer-with-Sources Formatter",
        "category": "llm",
        "lang": "typescript",
        "when": "Rendering an answer with numbered citations from retrieved docs",
        "why": "Atomic formatter: answer + cited ids in, markdown-ready output out",
        "tags": ["llm", "sources", "format", "citation", "answer"],
        "iface": r'''export interface Source { id: string; title: string; url?: string }
export function formatWithSources(answer: string, cited: string[], sources: Source[]): string''',
        "code": r'''export function formatWithSources(answer: string, cited: string[], sources: Source[]) {
  const byId = new Map(sources.map((s) => [s.id, s]));
  const lines = [answer, ''];
  const used = cited.map((id) => byId.get(id)).filter(Boolean) as Source[];
  if (used.length) {
    lines.push('Sources:');
    used.forEach((s, i) => lines.push(`${i + 1}. ${s.title}${s.url ? ` — ${s.url}` : ''}`));
  }
  return lines.join('\n');
}''',
        "provides": "formatWithSources(answer, cited, sources)",
        "depends": [],
    },
    {
        "id": "llm-hybrid-fusion",
        "name": "RAG Hybrid Fusion (BM25 + vector)",
        "category": "llm",
        "lang": "typescript",
        "when": "Combining keyword and semantic retrieval for more robust RAG",
        "why": "Atomic hybrid: BM25 + cosine scores normalized and summed, top-k out",
        "tags": ["llm", "hybrid", "bm25", "vector", "fusion", "rag"],
        "iface": r'''export interface HybridDoc { id: string; text: string; vector: number[] }
export function hybridRetrieve(query: string, queryVec: number[], docs: HybridDoc[], k = 3): Array<{ id: string; score: number }>''',
        "code": r'''function bm25(query: string, text: string) {
  const q = new Set(query.toLowerCase().match(/[a-z0-9]+/g) ?? []);
  const t = text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  const tf = new Map<string, number>();
  for (const w of t) tf.set(w, (tf.get(w) ?? 0) + 1);
  let score = 0;
  for (const w of q) score += Math.log(1 + (tf.get(w) ?? 0));
  return score;
}
export function hybridRetrieve(query: string, queryVec: number[], docs: HybridDoc[], k = 3) {
  let maxB = 0, maxC = 0;
  const scored = docs.map((d) => {
    let dot = 0, na = 0, nb = 0;
    for (let i = 0; i < queryVec.length; i++) { dot += queryVec[i] * d.vector[i]; na += queryVec[i] ** 2; nb += d.vector[i] ** 2; }
    const cosine = dot / (Math.sqrt(na) * Math.sqrt(nb) || 1);
    const lexical = bm25(query, d.text);
    maxB = Math.max(maxB, lexical); maxC = Math.max(maxC, cosine);
    return { id: d.id, lexical, cosine };
  });
  return scored
    .map((s) => ({ id: s.id, score: (s.cosine / (maxC || 1)) + (s.lexical / (maxB || 1)) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}''',
        "provides": "hybridRetrieve(query, queryVec, docs, k)",
        "depends": [],
    },
    {
        "id": "llm-sampling-config",
        "name": "Sampling Config (top-p / temperature)",
        "category": "llm",
        "lang": "typescript",
        "when": "Safely computing a sampling config from user-specified parameters",
        "why": "Atomic configurer: clamps temperature and top-p into valid ranges with defaults",
        "tags": ["llm", "sampling", "temperature", "topp", "config"],
        "iface": r'''export interface SamplingConfig { temperature: number; topP: number; maxTokens: number }
export function samplingConfig(opts?: Partial<SamplingConfig>): SamplingConfig''',
        "code": r'''export function samplingConfig(opts?: Partial<SamplingConfig>): SamplingConfig {
  const temp = Math.min(2, Math.max(0, opts?.temperature ?? 0.7));
  return {
    temperature: temp,
    topP: Math.min(1, Math.max(0.01, opts?.topP ?? 0.95)),
    maxTokens: Math.min(8192, Math.max(1, Math.round(opts?.maxTokens ?? 512))),
  };
}''',
        "provides": "samplingConfig(opts)",
        "depends": [],
    },
    {
        "id": "llm-usage-tracker",
        "name": "Token Usage Tracker",
        "category": "llm",
        "lang": "typescript",
        "when": "Budgeting per-session tokens across many model calls",
        "why": "Atomic counter: add usage, check remaining budget, rolling totals out",
        "tags": ["llm", "usage", "token", "budget", "tracker"],
        "iface": r'''export class UsageTracker {
  constructor(budget?: number)
  add(promptTokens: number, completionTokens: number): void
  get remaining(): number
  get total(): number
}''',
        "code": r'''export class UsageTracker {
  private used = 0;
  constructor(private budget = 100000) {}
  add(promptTokens: number, completionTokens: number) { this.used += promptTokens + completionTokens; }
  get remaining() { return Math.max(0, this.budget - this.used); }
  get total() { return this.used; }
}''',
        "provides": "UsageTracker",
        "depends": [],
    },
    {
        "id": "llm-conversation-summarizer",
        "name": "Conversation Summarizer Driver",
        "category": "llm",
        "lang": "typescript",
        "when": "Condensing long chat history so it fits the context window",
        "why": "Atomic summarizer: history + threshold in, summary + retained tail out",
        "tags": ["llm", "summary", "history", "condense", "context"],
        "iface": r'''export interface SummaryResult { summary: string; retainedTurns: Array<{ role: string; content: string }>; summarizedCount: number }
export async function summarizeHistory(opts: {
  turns: Array<{ role: string; content: string }>; maxTurns: number; summarize: (text: string) => Promise<string>
}): Promise<SummaryResult>''',
        "code": r'''export async function summarizeHistory(opts: {
  turns: Array<{ role: string; content: string }>; maxTurns: number; summarize: (text: string) => Promise<string>
}) {
  if (opts.turns.length <= opts.maxTurns) {
    return { summary: '', retainedTurns: opts.turns, summarizedCount: 0 };
  }
  const keep = opts.maxTurns - 1;
  const old = opts.turns.slice(0, opts.turns.length - keep);
  const retained = opts.turns.slice(opts.turns.length - keep);
  const condensed = old.map((t) => `${t.role}: ${t.content}`).join('\n');
  const summary = await opts.summarize(condensed);
  return { summary, retainedTurns: retained, summarizedCount: old.length };
}''',
        "provides": "summarizeHistory(opts)",
        "depends": [],
    },
]
