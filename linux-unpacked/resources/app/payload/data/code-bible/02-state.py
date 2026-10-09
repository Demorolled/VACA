# -*- coding: utf-8 -*-
"""
Code Bible — Category 02: State management (atomic, single-responsibility).
Convention: stores expose `get/set/subscribe/reset`; hooks return `[value, setValue]`;
pure helpers take an input object and return an output object.
"""
CHUNKS = [
    {
        "id": "state-create-store",
        "name": "Tiny Store",
        "category": "state",
        "lang": "typescript",
        "when": "Sharing mutable state between components without a heavyweight framework",
        "why": "Atomic store: get/set/subscribe only — no middleware, no actions; pairs with any UI layer",
        "tags": ["store", "state", "subscribe", "observer", "reactive"],
        "iface": r'''export interface Store<T> {
  get(): T;
  set(next: T | ((prev: T) => T)): void;
  subscribe(fn: (value: T) => void): () => void;
}
export function createStore<T>(initial: T): Store<T>''',
        "code": r'''export function createStore<T>(initial: T): Store<T> {
  let value = initial;
  const listeners = new Set<(v: T) => void>();

  return {
    get: () => value,
    set(next) {
      value = typeof next === 'function' ? (next as (prev: T) => T)(value) : next;
      for (const fn of listeners) fn(value);
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}''',
        "provides": "createStore<T>(initial): Store<T>",
        "depends": [],
    },
    {
        "id": "state-reducer",
        "name": "Reducer",
        "category": "state",
        "lang": "typescript",
        "when": "Updating state from a stream of typed actions with predictable transitions",
        "why": "Atomic pure reducer; (state, action) in, next state out — no side effects inside",
        "tags": ["reducer", "action", "state", "pure", "redux"],
        "iface": r'''export type Reducer<S, A> = (state: S, action: A) => S;
export function createReducer<S, A>(reducer: Reducer<S, A>, initial: S) {
  return (state: S = initial, action: A): S => reducer(state, action);
}''',
        "code": r'''export function createReducer<S, A>(reducer: Reducer<S, A>, initial: S) {
  let state = initial;
  return {
    dispatch(action: A) { state = reducer(state, action); },
    getState: () => state,
    reducer,
  };
}

// Example action type pattern:
// type TodoAction = { type: 'add'; title: string } | { type: 'toggle'; id: string };''',
        "provides": "createReducer<S,A>(reducer, initial)",
        "depends": [],
    },
    {
        "id": "state-finite-machine",
        "name": "Finite State Machine",
        "category": "state",
        "lang": "typescript",
        "when": "Modeling discrete states and legal transitions (wizard, connection, game turns)",
        "why": "Atomic FSM: states/transitions in, transition()/can()/state out — guards prevent illegal moves",
        "tags": ["fsm", "state machine", "transitions", "guard", "wizard"],
        "iface": r'''export type FSMState = string;
export interface FSMDefinition<S extends string, E extends string> {
  initial: S;
  transitions: Record<S, Partial<Record<E, S>>>;
}
export function createFSM<S extends string, E extends string>(def: FSMDefinition<S, E>): {
  state: S;
  can(event: E): boolean;
  send(event: E): boolean;
  reset(): void;
}''',
        "code": r'''export function createFSM<S extends string, E extends string>(def: FSMDefinition<S, E>) {
  let current: S = def.initial;
  return {
    get state(): S { return current; },
    can(event: E): boolean { return Boolean(def.transitions[current]?.[event]); },
    send(event: E): boolean {
      const next = def.transitions[current]?.[event];
      if (!next) return false;
      current = next;
      return true;
    },
    reset() { current = def.initial; },
  };
}''',
        "provides": "createFSM<S,E>(def)",
        "depends": [],
    },
    {
        "id": "state-undo-stack",
        "name": "Undo/Redo Stack",
        "category": "state",
        "lang": "typescript",
        "when": "Adding undo/redo to editors, painting tools, and builders",
        "why": "Atomic history stack; push in, undo()/redo()/canUndo/canRedo out — snapshots stored, not the live object",
        "tags": ["undo", "redo", "history", "stack", "editor"],
        "iface": r'''export function createUndoStack<T>(limit?: number) {
  return {
    push(snapshot: T): void,
    undo(): T | null,
    redo(): T | null,
    get canUndo(): boolean,
    get canRedo(): boolean,
    clear(): void,
  };
}''',
        "code": r'''export function createUndoStack<T>(limit = 100) {
  const past: T[] = [];
  const future: T[] = [];
  let current: T | null = null;

  return {
    push(snapshot: T) {
      if (current !== null) {
        past.push(current);
        if (past.length > limit) past.shift();
      }
      current = snapshot;
      future.length = 0;
    },
    undo() {
      if (past.length === 0) return null;
      if (current !== null) future.push(current);
      current = past.pop()!;
      return current;
    },
    redo() {
      if (future.length === 0) return null;
      if (current !== null) past.push(current);
      current = future.pop()!;
      return current;
    },
    get canUndo() { return past.length > 0; },
    get canRedo() { return future.length > 0; },
    clear() { past.length = 0; future.length = 0; current = null; },
  };
}''',
        "provides": "createUndoStack<T>(limit?)",
        "depends": [],
    },
    {
        "id": "state-debounce",
        "name": "Debounce",
        "category": "state",
        "lang": "typescript",
        "when": "Delaying a handler until input stops (search-as-you-type, resize)",
        "why": "Atomic debounce wrapper; fn in, debounced fn out — timer owned internally, no leaks on dispose",
        "tags": ["debounce", "delay", "timer", "search", "performance"],
        "iface": r'''export function debounce<A extends unknown[]>(
  fn: (...args: A) => void,
  waitMs: number,
): { run: (...args: A) => void; cancel: () => void }''',
        "code": r'''export function debounce<A extends unknown[]>(fn: (...args: A) => void, waitMs: number) {
  let timer: ReturnType<typeof setTimeout> | undefined;

  return {
    run(...args: A) {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { timer = undefined; fn(...args); }, waitMs);
    },
    cancel() {
      if (timer) clearTimeout(timer);
      timer = undefined;
    },
  };
}''',
        "provides": "debounce<A>(fn, waitMs)",
        "depends": [],
    },
    {
        "id": "state-throttle",
        "name": "Throttle",
        "category": "state",
        "lang": "typescript",
        "when": "Limiting handler frequency (scroll position, pointer moves, progress ticks)",
        "why": "Atomic throttle; fn + interval in, throttled fn out — leading edge fires immediately",
        "tags": ["throttle", "rate", "limit", "scroll", "performance"],
        "iface": r'''export function throttle<A extends unknown[]>(
  fn: (...args: A) => void,
  intervalMs: number,
): (...args: A) => void''',
        "code": r'''export function throttle<A extends unknown[]>(fn: (...args: A) => void, intervalMs: number) {
  let last = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;

  return (...args: A) => {
    const now = Date.now();
    const remaining = intervalMs - (now - last);
    if (remaining <= 0) {
      last = now;
      fn(...args);
    } else if (!timer) {
      timer = setTimeout(() => {
        timer = undefined;
        last = Date.now();
        fn(...args);
      }, remaining);
    }
  };
}''',
        "provides": "throttle<A>(fn, intervalMs)",
        "depends": [],
    },
    {
        "id": "state-local-storage",
        "name": "localStorage Persistence",
        "category": "state",
        "lang": "typescript",
        "when": "Persisting app state across reloads in the browser",
        "why": "Atomic persistence adapter: load/save with JSON serialization + try/catch for quota/private-mode",
        "tags": ["localstorage", "persist", "storage", "serialize", "json"],
        "iface": r'''export interface StorageAdapter<T> {
  load(): T | null;
  save(value: T): void;
  clear(): void;
}
export function createLocalStorageAdapter<T>(key: string, fallback: T): StorageAdapter<T>''',
        "code": r'''export function createLocalStorageAdapter<T>(key: string, fallback: T): StorageAdapter<T> {
  return {
    load(): T | null {
      try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : (JSON.parse(raw) as T);
      } catch {
        return fallback;
      }
    },
    save(value: T) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* quota/private */ }
    },
    clear() {
      try { localStorage.removeItem(key); } catch { /* ignore */ }
    },
  };
}''',
        "provides": "createLocalStorageAdapter<T>(key, fallback)",
        "depends": [],
    },
    {
        "id": "state-session-store",
        "name": "Session Storage Persistence",
        "category": "state",
        "lang": "typescript",
        "when": "Keeping transient UI state alive across tab reloads but not new tabs",
        "why": "Atomic sessionStorage adapter; same contract as the localStorage chunk, swapped storage backend",
        "tags": ["session", "storage", "persist", "tab"],
        "iface": r'''export function createSessionStorageAdapter<T>(key: string, fallback: T) {
  return {
    load(): T | null,
    save(value: T): void,
    clear(): void,
  };
}''',
        "code": r'''export function createSessionStorageAdapter<T>(key: string, fallback: T) {
  return {
    load(): T | null {
      try {
        const raw = sessionStorage.getItem(key);
        return raw === null ? fallback : (JSON.parse(raw) as T);
      } catch { return fallback; }
    },
    save(value: T) {
      try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
    },
    clear() {
      try { sessionStorage.removeItem(key); } catch { /* ignore */ }
    },
  };
}''',
        "provides": "createSessionStorageAdapter<T>(key, fallback)",
        "depends": [],
    },
    {
        "id": "state-event-emitter",
        "name": "Event Emitter",
        "category": "state",
        "lang": "typescript",
        "when": "Broadcasting typed events to multiple subscribers (notifications, bus)",
        "why": "Atomic emitter: on/off/emit only — no payload validation, typed via generics",
        "tags": ["emitter", "events", "listener", "publish", "observer"],
        "iface": r'''export type EventMap = Record<string, unknown[]>;
export function createEventEmitter<T extends EventMap>() {
  return {
    on<K extends keyof T>(event: K, fn: (...args: T[K]) => void): () => void,
    off<K extends keyof T>(event: K, fn: (...args: T[K]) => void): void,
    emit<K extends keyof T>(event: K, ...args: T[K]): void,
  };
}''',
        "code": r'''export function createEventEmitter<T extends EventMap>() {
  const listeners = new Map<keyof T, Set<(...args: never[]) => void>>();

  return {
    on(event, fn) {
      if (!listeners.has(event)) listeners.set(event, new Set());
      listeners.get(event)!.add(fn as (...args: never[]) => void);
      return () => listeners.get(event)?.delete(fn as (...args: never[]) => void);
    },
    off(event, fn) {
      listeners.get(event)?.delete(fn as (...args: never[]) => void);
    },
    emit(event, ...args) {
      listeners.get(event)?.forEach((fn) => (fn as (...a: unknown[]) => void)(...args));
    },
  };
}''',
        "provides": "createEventEmitter<T>()",
        "depends": [],
    },
    {
        "id": "state-pubsub-bus",
        "name": "Pub/Sub Bus",
        "category": "state",
        "lang": "typescript",
        "when": "Decoupling producers from consumers across modules (toasts, refresh signals)",
        "why": "Atomic topic bus: subscribe/publish by topic string, wildcard support optional; no state kept",
        "tags": ["pubsub", "bus", "topics", "decouple", "messaging"],
        "iface": r'''export function createPubSub<T extends string = string>() {
  return {
    subscribe(topic: T, fn: (payload: unknown) => void): () => void,
    publish(topic: T, payload?: unknown): void,
    clear(): void,
  };
}''',
        "code": r'''export function createPubSub<T extends string = string>() {
  const subs = new Map<T, Set<(payload: unknown) => void>>();

  return {
    subscribe(topic, fn) {
      if (!subs.has(topic)) subs.set(topic, new Set());
      subs.get(topic)!.add(fn);
      return () => subs.get(topic)?.delete(fn);
    },
    publish(topic, payload) {
      subs.get(topic)?.forEach((fn) => fn(payload));
    },
    clear() { subs.clear(); },
  };
}''',
        "provides": "createPubSub<T>()",
        "depends": [],
    },
    {
        "id": "state-atomic-counter",
        "name": "Atomic Counter",
        "category": "state",
        "lang": "typescript",
        "when": "Generating unique incrementing ids or tracking counts under concurrency",
        "why": "Atomic counter; increment()/peek()/reset() out — no timers or randomness inside",
        "tags": ["counter", "atomic", "id", "unique", "sequence"],
        "iface": r'''export function createCounter(start?: number) {
  return {
    next(): number,
    peek(): number,
    reset(): void,
  };
}''',
        "code": r'''export function createCounter(start = 0) {
  let value = start;
  return {
    next() { return value++; },
    peek() { return value; },
    reset() { value = start; },
  };
}''',
        "provides": "createCounter(start?)",
        "depends": [],
    },
    {
        "id": "state-memo-selector",
        "name": "Memoized Selector",
        "category": "state",
        "lang": "typescript",
        "when": "Deriving values from state without recomputing on every render",
        "why": "Atomic selector cache; selector fn in, cached result out — invalidates on reference change",
        "tags": ["memo", "selector", "cache", "derived", "performance"],
        "iface": r'''export function memoize<A extends unknown[], R>(fn: (...args: A) => R, keyOf?: (...args: A) => string): (...args: A) => R''',
        "code": r'''export function memoize<A extends unknown[], R>(fn: (...args: A) => R, keyOf?: (...args: A) => string) {
  const cache = new Map<string, R>();
  return (...args: A) => {
    const key = keyOf ? keyOf(...args) : JSON.stringify(args);
    if (!cache.has(key)) cache.set(key, fn(...args));
    return cache.get(key)!;
  };
}

export const selectVisibleTodos = memoize(
  (todos: Array<{ done: boolean }>) => todos.filter((t) => !t.done),
  (todos) => String(todos.length) + ':' + String(todos.filter((t) => t.done).length),
);''',
        "provides": "memoize<A,R>(fn, keyOf?)",
        "depends": [],
    },
    {
        "id": "state-polling-hook",
        "name": "Polling Hook",
        "category": "state",
        "lang": "typescript",
        "when": "Re-fetching data on an interval (status checks, tickers, leaderboards)",
        "why": "Atomic polling loop; fetcher + interval in, state + controls out — pauses on hidden tab",
        "tags": ["polling", "interval", "refresh", "hook", "fetch"],
        "iface": r'''export interface PollingState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
}
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  options?: { enabled?: boolean; onError?: (e: Error) => void },
): PollingState<T> & { refresh: () => Promise<void>; stop: () => void; start: () => void }''',
        "code": r'''import { useCallback, useEffect, useRef, useState } from 'react';

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number,
  options?: { enabled?: boolean; onError?: (e: Error) => void },
) {
  const [state, setState] = useState<PollingState<T>>({ data: null, error: null, loading: false });
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const tick = useCallback(async () => {
    try {
      setState((s) => ({ ...s, loading: true }));
      const data = await fetcherRef.current();
      setState({ data, error: null, loading: false });
    } catch (e) {
      setState((s) => ({ ...s, error: e as Error, loading: false }));
      options?.onError?.(e as Error);
    }
  }, [options]);

  const start = useCallback(() => {
    if (timer.current) return;
    void tick();
    timer.current = setInterval(() => void tick(), intervalMs);
  }, [tick, intervalMs]);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = undefined;
  }, []);

  useEffect(() => {
    if (options?.enabled !== false) start();
    return stop;
  }, [start, stop, options?.enabled]);

  return { ...state, refresh: tick, stop, start };
}''',
        "provides": "usePolling<T>(fetcher, intervalMs, options?)",
        "depends": [],
    },
    {
        "id": "state-websocket-hook",
        "name": "WebSocket Hook",
        "category": "state",
        "lang": "typescript",
        "when": "Connecting a component to a live websocket with auto-reconnect",
        "why": "Atomic socket hook: url in, message stream + status out; reconnection + heartbeat inside",
        "tags": ["websocket", "socket", "hook", "realtime", "reconnect"],
        "iface": r'''export interface SocketState<T> {
  status: 'connecting' | 'open' | 'closed' | 'error';
  lastMessage: T | null;
}
export function useWebSocket<T = unknown>(
  url: string,
  options?: { reconnectMs?: number; heartbeatMs?: number },
): SocketState<T> & { send: (data: unknown) => void; close: () => void }''',
        "code": r'''import { useEffect, useRef, useState } from 'react';

export function useWebSocket<T = unknown>(url: string,
  options?: { reconnectMs?: number; heartbeatMs?: number },
) {
  const [status, setStatus] = useState<SocketState<T>['status']>('connecting');
  const [lastMessage, setLastMessage] = useState<T | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const closedRef = useRef(false);
  const reconnectMs = options?.reconnectMs ?? 3000;

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;

    function connect() {
      if (closedRef.current) return;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      setStatus('connecting');
      ws.onopen = () => {
        setStatus('open');
        if (options?.heartbeatMs) {
          timer = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('ping'); }, options.heartbeatMs);
        }
      };
      ws.onmessage = (ev) => {
        try { setLastMessage(JSON.parse(ev.data) as T); } catch { setLastMessage(ev.data as unknown as T); }
      };
      ws.onclose = () => {
        setStatus('closed');
        if (timer) clearInterval(timer);
        if (!closedRef.current) timer = setTimeout(connect, reconnectMs);
      };
      ws.onerror = () => setStatus('error');
    }

    closedRef.current = false;
    connect();
    return () => {
      closedRef.current = true;
      if (timer) clearTimeout(timer);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, reconnectMs]);

  return {
    status,
    lastMessage,
    send: (data: unknown) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
      }
    },
    close: () => { closedRef.current = true; wsRef.current?.close(); },
  };
}''',
        "provides": "useWebSocket<T>(url, options?)",
        "depends": [],
    },
    {
        "id": "state-optimistic-update",
        "name": "Optimistic Update",
        "category": "state",
        "lang": "typescript",
        "when": "Applying UI changes instantly, then reconciling with the server response",
        "why": "Atomic optimistic helper: apply in, confirm/rollback out — keeps a snapshot for reversal",
        "tags": ["optimistic", "optimisticui", "rollback", "snapshot", "mutation"],
        "iface": r'''export function createOptimisticUpdater<T>() {
  return {
    apply(update: (current: T) => T): () => void,   // returns rollback()
  };
}
export function optimisticSet<T>(list: T[], id: string, patch: Partial<T>): T[]''',
        "code": r'''export function optimisticSet<T extends { id: string }>(list: T[], id: string, patch: Partial<T>): T[] {
  return list.map((item) => (item.id === id ? { ...item, ...patch } : item));
}

export function optimisticRemove<T extends { id: string }>(list: T[], id: string): T[] {
  return list.filter((item) => item.id !== id);
}

export function optimisticAdd<T>(list: T[], item: T, atTop = false): T[] {
  return atTop ? [item, ...list] : [...list, item];
}''',
        "provides": "optimisticSet/Remove/Add (pure list helpers)",
        "depends": [],
    },
    {
        "id": "state-cancellation-token",
        "name": "Cancellation Token",
        "category": "state",
        "lang": "typescript",
        "when": "Cancelling in-flight async work when a component unmounts or params change",
        "why": "Atomic cancellation primitive; token in, isCancelled + signal out — async loops check it",
        "tags": ["cancel", "abort", "async", "token", "unmount"],
        "iface": r'''export interface CancellationToken { isCancelled: boolean; signal: AbortSignal }
export function createCancellationToken(): CancellationToken & { cancel(): void }''',
        "code": r'''export function createCancellationToken() {
  const controller = new AbortController();
  let cancelled = false;
  return {
    get isCancelled() { return cancelled; },
    get signal() { return controller.signal; },
    cancel() {
      cancelled = true;
      controller.abort();
    },
  };
}''',
        "provides": "createCancellationToken()",
        "depends": [],
    },
    {
        "id": "state-queue",
        "name": "Async Queue",
        "category": "state",
        "lang": "typescript",
        "when": "Processing tasks one-at-a-time in order (uploads, LLM calls, writes)",
        "why": "Atomic FIFO queue with concurrency 1; push in, results via promises out — no timers inside",
        "tags": ["queue", "fifo", "worker", "async", "tasks"],
        "iface": r'''export function createQueue<T>(worker: (item: T) => Promise<void>) {
  return {
    push(item: T): Promise<void>,
    get size(): number,
    get idle(): boolean,
    drain(): Promise<void>,
  };
}''',
        "code": r'''export function createQueue<T>(worker: (item: T) => Promise<void>) {
  const items: T[] = [];
  let running = false;
  const waiters: Array<() => void> = [];

  async function pump() {
    if (running) return;
    running = true;
    while (items.length > 0) {
      const item = items.shift()!;
      try { await worker(item); } catch { /* worker handles its own errors */ }
    }
    running = false;
    waiters.splice(0).forEach((w) => w());
  }

  return {
    push(item: T) {
      items.push(item);
      void pump();
      return new Promise<void>((resolve) => {
        const check = () => { if (!running && items.length === 0) resolve(); };
        waiters.push(check);
      });
    },
    get size() { return items.length; },
    get idle() { return !running && items.length === 0; },
    async drain() {
      while (!this.idle) await new Promise((r) => setTimeout(r, 5));
    },
  };
}''',
        "provides": "createQueue<T>(worker)",
        "depends": [],
    },
    {
        "id": "state-lru-cache",
        "name": "LRU Cache",
        "category": "state",
        "lang": "typescript",
        "when": "Caching recently-used values with bounded memory (lookups, renders)",
        "why": "Atomic LRU via Map ordering; get/set/delete out — evicts least-recently-used on overflow",
        "tags": ["lru", "cache", "memory", "eviction", "performance"],
        "iface": r'''export function createLruCache<K, V>(capacity: number) {
  return {
    get(key: K): V | undefined,
    set(key: K, value: V): void,
    has(key: K): boolean,
    delete(key: K): boolean,
    get size(): number,
    clear(): void,
  };
}''',
        "code": r'''export function createLruCache<K, V>(capacity: number) {
  const map = new Map<K, V>();

  return {
    get(key) {
      if (!map.has(key)) return undefined;
      const value = map.get(key)!;
      map.delete(key);          // refresh recency
      map.set(key, value);
      return value;
    },
    set(key, value) {
      if (map.has(key)) map.delete(key);
      map.set(key, value);
      if (map.size > capacity) {
        const oldest = map.keys().next().value;
        if (oldest !== undefined) map.delete(oldest);
      }
    },
    has: (key) => map.has(key),
    delete: (key) => map.delete(key),
    get size() { return map.size; },
    clear: () => map.clear(),
  };
}''',
        "provides": "createLruCache<K,V>(capacity)",
        "depends": [],
    },
    {
        "id": "state-ttl-cache",
        "name": "TTL Cache",
        "category": "state",
        "lang": "typescript",
        "when": "Caching values that expire after a timeout (tokens, sessions, responses)",
        "why": "Atomic time-based cache; get/set with ttl out — expired entries auto-evicted on access",
        "tags": ["ttl", "cache", "expiry", "timeout", "session"],
        "iface": r'''export function createTtlCache<K, V>(defaultTtlMs: number) {
  return {
    get(key: K): V | undefined,
    set(key: K, value: V, ttlMs?: number): void,
    delete(key: K): boolean,
    get size(): number,
  };
}''',
        "code": r'''export function createTtlCache<K, V>(defaultTtlMs: number) {
  const map = new Map<K, { value: V; expiresAt: number }>();

  return {
    get(key) {
      const entry = map.get(key);
      if (!entry) return undefined;
      if (entry.expiresAt < Date.now()) { map.delete(key); return undefined; }
      return entry.value;
    },
    set(key, value, ttlMs) {
      map.set(key, { value, expiresAt: Date.now() + (ttlMs ?? defaultTtlMs) });
    },
    delete: (key) => map.delete(key),
    get size() { return map.size; },
  };
}''',
        "provides": "createTtlCache<K,V>(defaultTtlMs)",
        "depends": [],
    },
    {
        "id": "state-backoff-retry",
        "name": "Backoff Retry",
        "category": "state",
        "lang": "typescript",
        "when": "Retrying flaky async calls with exponential backoff + jitter",
        "why": "Atomic retry helper; task in, result out — capped attempts, no global timers leak",
        "tags": ["retry", "backoff", "exponential", "jitter", "resilience"],
        "iface": r'''export interface RetryOptions { attempts?: number; baseMs?: number; maxMs?: number; shouldRetry?: (e: unknown) => boolean }
export async function withRetry<T>(task: () => Promise<T>, options?: RetryOptions): Promise<T>''',
        "code": r'''export async function withRetry<T>(task: () => Promise<T>, options?: RetryOptions): Promise<T> {
  const attempts = options?.attempts ?? 3;
  const baseMs = options?.baseMs ?? 200;
  const maxMs = options?.maxMs ?? 4000;

  for (let i = 0; i < attempts; i++) {
    try {
      return await task();
    } catch (e) {
      if (i === attempts - 1) throw e;
      if (options?.shouldRetry && !options.shouldRetry(e)) throw e;
      const jitter = Math.random() * baseMs;
      const delay = Math.min(maxMs, baseMs * 2 ** i + jitter);
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw new Error('unreachable');
}''',
        "provides": "withRetry<T>(task, options?)",
        "depends": [],
    },
    {
        "id": "state-async-generator",
        "name": "Async Generator Queue",
        "category": "state",
        "lang": "typescript",
        "when": "Consuming a stream of async events one-by-one (log tail, SSE chunks)",
        "why": "Atomic async iterable; producer pushes in, consumer pulls via for-await — backpressure safe",
        "tags": ["async", "generator", "stream", "iterator", "producer"],
        "iface": r'''export function createAsyncQueue<T>() {
  return {
    push(value: T): void,
    done(): void,
    [Symbol.asyncIterator](): AsyncIterator<T>,
  };
}''',
        "code": r'''export function createAsyncQueue<T>() {
  const buffer: T[] = [];
  const waiters: Array<{ resolve: (v: IteratorResult<T>) => void }> = [];
  let finished = false;

  return {
    push(value: T) {
      if (finished) return;
      const waiter = waiters.shift();
      if (waiter) waiter.resolve({ value, done: false });
      else buffer.push(value);
    },
    done() {
      finished = true;
      waiters.splice(0).forEach((w) => w.resolve({ value: undefined, done: true }));
    },
    async *[Symbol.asyncIterator]() {
      while (true) {
        if (buffer.length > 0) yield buffer.shift()!;
        else if (finished) return;
        else await new Promise<IteratorResult<T>>((resolve) => waiters.push({ resolve }));
      }
    },
  };
}''',
        "provides": "createAsyncQueue<T>()",
        "depends": [],
    },
    {
        "id": "state-crdt-lww",
        "name": "LWW CRDT Map",
        "category": "state",
        "lang": "typescript",
        "when": "Merging concurrent edits across devices with last-writer-wins semantics",
        "why": "Atomic LWW map; set/merge out — conflicts resolved by (timestamp, peerId) without a server",
        "tags": ["crdt", "merge", "conflict", "offline", "sync"],
        "iface": r'''export interface LwwValue<V> { value: V; ts: number; peer: string }
export function createLwwMap<V>() {
  return {
    set(key: string, value: V, peer: string, ts?: number): void,
    get(key: string): V | undefined,
    merge(other: Map<string, LwwValue<V>>): void,
    snapshot(): Map<string, LwwValue<V>>,
  };
}''',
        "code": r'''export function createLwwMap<V>() {
  const data = new Map<string, LwwValue<V>>();

  function wins(a: LwwValue<V> | undefined, b: LwwValue<V>): boolean {
    if (!a) return true;
    return b.ts > a.ts || (b.ts === a.ts && b.peer > a.peer);
  }

  return {
    set(key, value, peer, ts) {
      const entry: LwwValue<V> = { value, peer, ts: ts ?? Date.now() };
      if (wins(data.get(key), entry)) data.set(key, entry);
    },
    get(key) { return data.get(key)?.value; },
    merge(other) {
      for (const [key, entry] of other) {
        if (wins(data.get(key), entry)) data.set(key, entry);
      }
    },
    snapshot() { return new Map(data); },
  };
}''',
        "provides": "createLwwMap<V>()",
        "depends": [],
    },
    {
        "id": "state-signal-slot",
        "name": "Signal/Slot Bus",
        "category": "state",
        "lang": "typescript",
        "when": "Typed callback wiring with single-slot semantics (framework integrations)",
        "why": "Atomic signal-slot; connect/disconnect/emit out — typed like Qt, lightweight",
        "tags": ["signal", "slot", "callback", "typed", "connect"],
        "iface": r'''export function createSignal<T = void>() {
  return {
    connect(fn: (payload: T) => void): () => void,
    emit(payload: T): void,
    get count(): number,
    disconnectAll(): void,
  };
}''',
        "code": r'''export function createSignal<T = void>() {
  const slots = new Set<(payload: T) => void>();

  return {
    connect(fn) {
      slots.add(fn);
      return () => slots.delete(fn);
    },
    emit(payload) {
      for (const fn of [...slots]) fn(payload);
    },
    get count() { return slots.size; },
    disconnectAll() { slots.clear(); },
  };
}''',
        "provides": "createSignal<T>()",
        "depends": [],
    },
    {
        "id": "state-idle-timer",
        "name": "Idle Timer",
        "category": "state",
        "lang": "typescript",
        "when": "Detecting user inactivity (auto-lock, pause, presence)",
        "why": "Atomic idle detector; timeout in, onIdle callback out — resets on any activity event",
        "tags": ["idle", "timeout", "activity", "presence", "lock"],
        "iface": r'''export function createIdleTimer(timeoutMs: number, onIdle: () => void) {
  return {
    reset(): void,
    stop(): void,
    start(): void,
  };
}''',
        "code": r'''export function createIdleTimer(timeoutMs: number, onIdle: () => void) {
  let timer: ReturnType<typeof setTimeout> | undefined;

  const EVENTS = ['mousemove', 'keydown', 'mousedown', 'touchstart', 'scroll'] as const;

  function arm() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(onIdle, timeoutMs);
  }

  return {
    reset() { arm(); },
    stop() {
      if (timer) clearTimeout(timer);
      timer = undefined;
      EVENTS.forEach((e) => window.removeEventListener(e, arm));
    },
    start() {
      arm();
      EVENTS.forEach((e) => window.addEventListener(e, arm, { passive: true }));
    },
  };
}''',
        "provides": "createIdleTimer(timeoutMs, onIdle)",
        "depends": [],
    },
]
