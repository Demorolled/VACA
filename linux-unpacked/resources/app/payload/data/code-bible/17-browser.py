# -*- coding: utf-8 -*-
"""
Code Bible — Category 17: Browser & DOM (atomic, single-responsibility).
Convention: DOM helpers guard for missing document/window so they are SSR-safe.
"""
CHUNKS = [
    {
        "id": "brw-dom-ready",
        "name": "DOM Ready Helper",
        "category": "brw",
        "lang": "typescript",
        "when": "Running initialization code once the DOM is interactive",
        "why": "Atomic helper: callback in, runs immediately if ready or on DOMContentLoaded once",
        "tags": ["brw", "dom", "ready", "init", "load"],
        "iface": r'''export function onDomReady(fn: () => void): void''',
        "code": r'''export function onDomReady(fn: () => void) {
  if (typeof document === 'undefined') return;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fn, { once: true });
  } else {
    queueMicrotask(fn);
  }
}''',
        "provides": "onDomReady(fn)",
        "depends": [],
    },
    {
        "id": "brw-element-size",
        "name": "Element Size Observer",
        "category": "brw",
        "lang": "typescript",
        "when": "Reacting to an element's size changes (responsive widgets)",
        "why": "Atomic observer: element + callback in, stop() out, ResizeObserver wrapped",
        "tags": ["brw", "resize", "observer", "element", "size"],
        "iface": r'''export function watchElementSize(el: Element, onResize: (size: { width: number; height: number }) => void): () => void''',
        "code": r'''export function watchElementSize(el: Element, onResize: (size: { width: number; height: number }) => void) {
  if (typeof ResizeObserver === 'undefined') return () => {};
  const ro = new ResizeObserver((entries) => {
    for (const e of entries) onResize({ width: e.contentRect.width, height: e.contentRect.height });
  });
  ro.observe(el);
  return () => ro.disconnect();
}''',
        "provides": "watchElementSize(el, onResize)",
        "depends": [],
    },
    {
        "id": "brw-clipboard",
        "name": "Copy-to-Clipboard",
        "category": "brw",
        "lang": "typescript",
        "when": "Copying text to the clipboard with a legacy fallback",
        "why": "Atomic copier: async API first, execCommand fallback, boolean success out",
        "tags": ["brw", "clipboard", "copy", "text", "fallback"],
        "iface": r'''export async function copyText(text: string): Promise<boolean>''',
        "code": r'''export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}''',
        "provides": "copyText(text)",
        "depends": [],
    },
    {
        "id": "brw-download-blob",
        "name": "Download Blob File",
        "category": "brw",
        "lang": "typescript",
        "when": "Triggering a browser download for generated content",
        "why": "Atomic downloader: content + filename in, object URL created and revoked",
        "tags": ["brw", "download", "blob", "file", "save"],
        "iface": r'''export function downloadBlob(content: BlobPart, filename: string, mime = 'application/octet-stream'): void''',
        "code": r'''export function downloadBlob(content: BlobPart, filename: string, mime = 'application/octet-stream') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}''',
        "provides": "downloadBlob(content, filename, mime)",
        "depends": [],
    },
    {
        "id": "brw-url-query",
        "name": "URL Query Parser/Builder",
        "category": "brw",
        "lang": "typescript",
        "when": "Reading and writing ?query=params without a router",
        "why": "Atomic helpers: location-agnostic parse/serialize, encoded safe",
        "tags": ["brw", "url", "query", "params", "parse"],
        "iface": r'''export function parseQuery(search: string): Record<string, string>
export function buildQuery(params: Record<string, string | number | undefined>): string''',
        "code": r'''export function parseQuery(search: string) {
  const out: Record<string, string> = {};
  const q = search.replace(/^\?/, '');
  if (!q) return out;
  for (const pair of q.split('&')) {
    const eq = pair.indexOf('=');
    if (eq < 0) { out[decodeURIComponent(pair)] = ''; continue; }
    out[decodeURIComponent(pair.slice(0, eq))] = decodeURIComponent(pair.slice(eq + 1).replace(/\+/g, ' '));
  }
  return out;
}
export function buildQuery(params: Record<string, string | number | undefined>) {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? '?' + parts.join('&') : '';
}''',
        "provides": "parseQuery / buildQuery",
        "depends": [],
    },
    {
        "id": "brw-cookie",
        "name": "Cookie Get/Set/Delete",
        "category": "brw",
        "lang": "typescript",
        "when": "Managing cookies with encoding and options",
        "why": "Atomic cookie API: get/set/delete, encodeURIComponent safe, defaults to path=/",
        "tags": ["brw", "cookie", "get", "set", "delete"],
        "iface": r'''export function getCookie(name: string): string | null
export function setCookie(name: string, value: string, opts?: { maxAgeSec?: number; path?: string; secure?: boolean; sameSite?: 'Lax' | 'Strict' | 'None' }): void
export function deleteCookie(name: string, path?: string): void''',
        "code": r'''export function getCookie(name: string) {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : null;
}
export function setCookie(name: string, value: string, opts: { maxAgeSec?: number; path?: string; secure?: boolean; sameSite?: 'Lax' | 'Strict' | 'None' } = {}) {
  const parts = [`${encodeURIComponent(name)}=${encodeURIComponent(value)}`];
  if (opts.maxAgeSec !== undefined) parts.push(`Max-Age=${opts.maxAgeSec}`);
  parts.push(`Path=${opts.path ?? '/'}`);
  if (opts.secure) parts.push('Secure');
  if (opts.sameSite) parts.push(`SameSite=${opts.sameSite}`);
  document.cookie = parts.join('; ');
}
export function deleteCookie(name: string, path = '/') {
  document.cookie = `${encodeURIComponent(name)}=; Max-Age=0; Path=${path}`;
}''',
        "provides": "getCookie / setCookie / deleteCookie",
        "depends": [],
    },
    {
        "id": "brw-storage",
        "name": "Typed localStorage Wrapper",
        "category": "brw",
        "lang": "typescript",
        "when": "Persisting typed values with namespace + safe JSON",
        "why": "Atomic wrapper: get/set/remove typed, corrupt entries return null",
        "tags": ["brw", "localstorage", "storage", "typed", "persist"],
        "iface": r'''export class LocalStore<T> {
  constructor(key: string)
  get(): T | null
  set(value: T): void
  remove(): void
}
export function storageAvailable(kind: 'localStorage' | 'sessionStorage'): boolean''',
        "code": r'''export class LocalStore<T> {
  constructor(private key: string) {}
  get(): T | null {
    try { const raw = localStorage.getItem(this.key); return raw ? (JSON.parse(raw) as T) : null; } catch { return null; }
  }
  set(value: T) { try { localStorage.setItem(this.key, JSON.stringify(value)); } catch { /* quota */ } }
  remove() { localStorage.removeItem(this.key); }
}
export function storageAvailable(kind: 'localStorage' | 'sessionStorage') {
  try { const k = '__t__'; window[kind].setItem(k, '1'); window[kind].removeItem(k); return true; } catch { return false; }
}''',
        "provides": "LocalStore / storageAvailable",
        "depends": [],
    },
    {
        "id": "brw-scroll",
        "name": "Scroll Helpers",
        "category": "brw",
        "lang": "typescript",
        "when": "Scrolling to positions or elements with smooth behavior",
        "why": "Atomic scroll API: top/el/position, smooth option, SSR-safe guards",
        "tags": ["brw", "scroll", "smooth", "position", "element"],
        "iface": r'''export function scrollToTop(smooth?: boolean): void
export function scrollToElement(el: Element, opts?: { smooth?: boolean; block?: ScrollLogicalPosition }): void
export function scrollToPosition(x: number, y: number, smooth?: boolean): void''',
        "code": r'''export function scrollToTop(smooth = true) {
  window.scrollTo({ top: 0, behavior: smooth ? 'smooth' : 'auto' });
}
export function scrollToElement(el: Element, opts: { smooth?: boolean; block?: ScrollLogicalPosition } = {}) {
  el.scrollIntoView({ behavior: opts.smooth === false ? 'auto' : 'smooth', block: opts.block ?? 'start' });
}
export function scrollToPosition(x: number, y: number, smooth = true) {
  window.scrollTo({ left: x, top: y, behavior: smooth ? 'smooth' : 'auto' });
}''',
        "provides": "scrollToTop / scrollToElement / scrollToPosition",
        "depends": [],
    },
    {
        "id": "brw-visibility",
        "name": "Visibility Change Tracker",
        "category": "brw",
        "lang": "typescript",
        "when": "Pausing timers or polling when the tab is hidden",
        "why": "Atomic tracker: callback in, unsubscribe out, immediate current state",
        "tags": ["brw", "visibility", "hidden", "tab", "tracker"],
        "iface": r'''export function trackVisibility(onChange: (hidden: boolean) => void): () => void
export function isTabHidden(): boolean''',
        "code": r'''export function trackVisibility(onChange: (hidden: boolean) => void) {
  const handler = () => onChange(document.visibilityState === 'hidden');
  document.addEventListener('visibilitychange', handler);
  return () => document.removeEventListener('visibilitychange', handler);
}
export function isTabHidden() {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}''',
        "provides": "trackVisibility / isTabHidden",
        "depends": [],
    },
    {
        "id": "brw-network-status",
        "name": "Network Status Monitor",
        "category": "brw",
        "lang": "typescript",
        "when": "Showing offline banners and toggling online-only features",
        "why": "Atomic monitor: online/offline events in, status + unsubscribe out",
        "tags": ["brw", "network", "online", "offline", "status"],
        "iface": r'''export function isOnline(): boolean
export function watchNetwork(onChange: (online: boolean) => void): () => void''',
        "code": r'''export function isOnline() {
  return typeof navigator === 'undefined' ? true : navigator.onLine;
}
export function watchNetwork(onChange: (online: boolean) => void) {
  const up = () => onChange(true);
  const down = () => onChange(false);
  window.addEventListener('online', up);
  window.addEventListener('offline', down);
  return () => { window.removeEventListener('online', up); window.removeEventListener('offline', down); };
}''',
        "provides": "isOnline / watchNetwork",
        "depends": [],
    },
    {
        "id": "brw-fullscreen",
        "name": "Fullscreen Toggle",
        "category": "brw",
        "lang": "typescript",
        "when": "Entering/exiting fullscreen for a player or canvas",
        "why": "Atomic toggle: element in, request/exit fullscreen, vendor-prefix free",
        "tags": ["brw", "fullscreen", "toggle", "element", "screen"],
        "iface": r'''export async function toggleFullscreen(el?: Element): Promise<boolean>
export function isFullscreen(): boolean''',
        "code": r'''export async function toggleFullscreen(el?: Element) {
  if (document.fullscreenElement) { await document.exitFullscreen(); return false; }
  await (el ?? document.documentElement).requestFullscreen();
  return true;
}
export function isFullscreen() {
  return !!document.fullscreenElement;
}''',
        "provides": "toggleFullscreen / isFullscreen",
        "depends": [],
    },
    {
        "id": "brw-media-query",
        "name": "Media Query Matcher",
        "category": "brw",
        "lang": "typescript",
        "when": "Reacting to responsive breakpoints in JS",
        "why": "Atomic matcher: query in, matches + change subscription out",
        "tags": ["brw", "media", "query", "responsive", "match"],
        "iface": r'''export function matchMedia(query: string): { matches: boolean; subscribe: (fn: (m: boolean) => void) => () => void }''',
        "code": r'''export function matchMedia(query: string) {
  const mql = window.matchMedia(query);
  return {
    matches: mql.matches,
    subscribe(fn: (m: boolean) => void) {
      const handler = (e: MediaQueryListEvent) => fn(e.matches);
      mql.addEventListener('change', handler);
      return () => mql.removeEventListener('change', handler);
    },
  };
}''',
        "provides": "matchMedia(query)",
        "depends": [],
    },
    {
        "id": "brw-keyboard",
        "name": "Keyboard Shortcut Registry",
        "category": "brw",
        "lang": "typescript",
        "when": "Binding global key combos with modifier support",
        "why": "Atomic registry: shortcuts in, stop() out, modifier matching + ignore inputs option",
        "tags": ["brw", "keyboard", "shortcut", "hotkey", "registry"],
        "iface": r'''export interface ShortcutDef { combo: string; handler: (e: KeyboardEvent) => void; ignoreInInputs?: boolean }
export function registerShortcuts(defs: ShortcutDef[]): () => void''',
        "code": r'''export function registerShortcuts(defs: ShortcutDef[]) {
  const handler = (e: KeyboardEvent) => {
    for (const d of defs) {
      if (d.ignoreInInputs && /^(input|textarea|select)$/i.test((e.target as HTMLElement)?.tagName ?? '')) continue;
      const parts = d.combo.toLowerCase().split('+');
      const key = parts[parts.length - 1];
      const mods = parts.slice(0, -1);
      if (e.key.toLowerCase() !== key) continue;
      if (mods.includes('ctrl') !== e.ctrlKey) continue;
      if (mods.includes('shift') !== e.shiftKey) continue;
      if (mods.includes('alt') !== e.altKey) continue;
      if (mods.includes('meta') !== e.metaKey) continue;
      e.preventDefault();
      d.handler(e);
      return;
    }
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}''',
        "provides": "registerShortcuts(defs)",
        "depends": [],
    },
    {
        "id": "brw-drag-files",
        "name": "File Drag-and-Drop Helper",
        "category": "brw",
        "lang": "typescript",
        "when": "Handling file drops on a dropzone element",
        "why": "Atomic dropzone: element + callbacks in, cleanup out, preventDefault handled",
        "tags": ["brw", "drag", "drop", "files", "upload"],
        "iface": r'''export interface DropHandlers { onFiles: (files: File[]) => void; onDragState?: (active: boolean) => void }
export function setupDropzone(el: HTMLElement, handlers: DropHandlers): () => void''',
        "code": r'''export function setupDropzone(el: HTMLElement, handlers: DropHandlers) {
  const enter = (e: DragEvent) => { e.preventDefault(); handlers.onDragState?.(true); };
  const leave = (e: DragEvent) => { e.preventDefault(); handlers.onDragState?.(false); };
  const over = (e: DragEvent) => e.preventDefault();
  const drop = (e: DragEvent) => {
    e.preventDefault();
    handlers.onDragState?.(false);
    if (e.dataTransfer?.files.length) handlers.onFiles([...e.dataTransfer.files]);
  };
  el.addEventListener('dragenter', enter);
  el.addEventListener('dragleave', leave);
  el.addEventListener('dragover', over);
  el.addEventListener('drop', drop);
  return () => {
    el.removeEventListener('dragenter', enter);
    el.removeEventListener('dragleave', leave);
    el.removeEventListener('dragover', over);
    el.removeEventListener('drop', drop);
  };
}''',
        "provides": "setupDropzone(el, handlers)",
        "depends": [],
    },
    {
        "id": "brw-focus-trap",
        "name": "Focus Trap (modals)",
        "category": "brw",
        "lang": "typescript",
        "when": "Keeping keyboard focus inside an open modal",
        "why": "Atomic trap: container in, tab cycling + restore previous focus out",
        "tags": ["brw", "focus", "trap", "modal", "a11y"],
        "iface": r'''export function trapFocus(container: HTMLElement): () => void''',
        "code": r'''export function trapFocus(container: HTMLElement) {
  const prev = document.activeElement as HTMLElement | null;
  const focusables = () => [...container.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter((el) => !el.hasAttribute('disabled'));
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'Tab') return;
    const list = focusables();
    if (!list.length) return;
    const first = list[0], last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', onKey);
  focusables()[0]?.focus();
  return () => { document.removeEventListener('keydown', onKey); prev?.focus(); };
}''',
        "provides": "trapFocus(container)",
        "depends": [],
    },
    {
        "id": "brw-form-serialize",
        "name": "Form Serializer",
        "category": "brw",
        "lang": "typescript",
        "when": "Converting a form to a plain object for API calls",
        "why": "Atomic serializer: form in, object out, checkbox/multi-value aware",
        "tags": ["brw", "form", "serialize", "formdata", "object"],
        "iface": r'''export function formToObject(form: HTMLFormElement): Record<string, string | string[] | boolean>''',
        "code": r'''export function formToObject(form: HTMLFormElement) {
  const fd = new FormData(form);
  const out: Record<string, string | string[] | boolean> = {};
  for (const [name, value] of fd.entries()) {
    const el = form.elements.namedItem(name) as HTMLInputElement | null;
    if (el?.type === 'checkbox' && !(el as HTMLInputElement).checked) continue;
    if (el?.type === 'checkbox') { out[name] = true; continue; }
    if (name in out) {
      const cur = out[name];
      out[name] = Array.isArray(cur) ? [...cur, String(value)] : [String(cur), String(value)];
    } else {
      out[name] = String(value);
    }
  }
  return out;
}''',
        "provides": "formToObject(form)",
        "depends": [],
    },
    {
        "id": "brw-hash-router",
        "name": "Hash Router",
        "category": "brw",
        "lang": "typescript",
        "when": "Single-page routing without a server using location.hash",
        "why": "Atomic router: routes in, current + navigate + subscribe out",
        "tags": ["brw", "hash", "router", "spa", "route"],
        "iface": r'''export class HashRouter {
  constructor(routes: Array<{ path: string; render: (params: Record<string, string>) => void }>)
  navigate(path: string): void
  start(): void
  get current(): string
}''',
        "code": r'''export class HashRouter {
  private listeners: Array<() => void> = [];
  constructor(private routes: Array<{ path: string; render: (params: Record<string, string>) => void }>) {}
  private parse(hash: string) {
    const clean = hash.replace(/^#/, '') || '/';
    for (const r of this.routes) {
      const keys: string[] = [];
      const re = new RegExp('^' + r.path.replace(/:[a-zA-Z_]+/g, (m) => { keys.push(m.slice(1)); return '([^/]+)'; }) + '$');
      const m = re.exec(clean);
      if (m) { r.render(Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]))); return clean; }
    }
    return clean;
  }
  navigate(path: string) { window.location.hash = path; }
  start() {
    const handler = () => { this.current; this.listeners.forEach((l) => l()); };
    window.addEventListener('hashchange', handler);
    handler();
  }
  get current() { return this.parse(window.location.hash); }
}''',
        "provides": "HashRouter",
        "depends": [],
    },
    {
        "id": "brw-image-preload",
        "name": "Image Preloader",
        "category": "brw",
        "lang": "typescript",
        "when": "Preloading critical images to avoid layout jumps",
        "why": "Atomic preloader: urls in, loaded/failed counts out, parallel via Promise.allSettled",
        "tags": ["brw", "image", "preload", "load", "cache"],
        "iface": r'''export async function preloadImages(urls: string[]): Promise<{ loaded: number; failed: number }>''',
        "code": r'''export async function preloadImages(urls: string[]) {
  const results = await Promise.allSettled(urls.map((url) =>
    new Promise<void>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve();
      img.onerror = () => reject(new Error(url));
      img.src = url;
    })));
  return { loaded: results.filter((r) => r.status === 'fulfilled').length, failed: results.filter((r) => r.status === 'rejected').length };
}''',
        "provides": "preloadImages(urls)",
        "depends": [],
    },
    {
        "id": "brw-audio-unlock",
        "name": "Audio Context Unlock",
        "category": "brw",
        "lang": "typescript",
        "when": "Resuming WebAudio after a user gesture (autoplay policy)",
        "why": "Atomic unlock: context in, resume + one-time gesture listener out",
        "tags": ["brw", "audio", "unlock", "autoplay", "webaudio"],
        "iface": r'''export function unlockAudio(ctx: AudioContext): () => void''',
        "code": r'''export function unlockAudio(ctx: AudioContext) {
  const resume = () => { if (ctx.state === 'suspended') void ctx.resume(); };
  window.addEventListener('pointerdown', resume, { once: true });
  window.addEventListener('keydown', resume, { once: true });
  return () => { window.removeEventListener('pointerdown', resume); window.removeEventListener('keydown', resume); };
}''',
        "provides": "unlockAudio(ctx)",
        "depends": [],
    },
    {
        "id": "brw-open-tab",
        "name": "Safe Open-in-New-Tab",
        "category": "brw",
        "lang": "typescript",
        "when": "Opening links safely without tabnabbing",
        "why": "Atomic opener: url in, rel=noopener enforced, window.open guarded",
        "tags": ["brw", "open", "tab", "noopener", "link"],
        "iface": r'''export function openInNewTab(url: string): void''',
        "code": r'''export function openInNewTab(url: string) {
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  document.body.appendChild(a);
  a.click();
  a.remove();
}''',
        "provides": "openInNewTab(url)",
        "depends": [],
    },
    {
        "id": "brw-quota",
        "name": "Storage Quota Estimator",
        "category": "brw",
        "lang": "typescript",
        "when": "Warn users before persistent storage runs out",
        "why": "Atomic estimator: navigator.storage in, used/available MB out, graceful fallback",
        "tags": ["brw", "storage", "quota", "estimate", "persist"],
        "iface": r'''export async function storageQuota(): Promise<{ usedMb: number; quotaMb: number; usagePct: number } | null>''',
        "code": r'''export async function storageQuota() {
  try {
    if (!navigator.storage?.estimate) return null;
    const est = await navigator.storage.estimate();
    const usedMb = (est.usage ?? 0) / 1048576;
    const quotaMb = (est.quota ?? 0) / 1048576;
    return { usedMb: +usedMb.toFixed(1), quotaMb: +quotaMb.toFixed(1), usagePct: est.quota ? (est.usage ?? 0) / est.quota * 100 : 0 };
  } catch {
    return null;
  }
}''',
        "provides": "storageQuota()",
        "depends": [],
    },
    {
        "id": "brw-title-flash",
        "name": "Tab Title Flash",
        "category": "brw",
        "lang": "typescript",
        "when": "Grabbing attention for notifications when the tab is hidden",
        "why": "Atomic flasher: message in, interval title swap + restore out",
        "tags": ["brw", "title", "flash", "notification", "tab"],
        "iface": r'''export function flashTitle(message: string, originalTitle?: string): () => void''',
        "code": r'''export function flashTitle(message: string, originalTitle = document.title) {
  let shown = false;
  const interval = setInterval(() => {
    document.title = shown ? originalTitle : message;
    shown = !shown;
  }, 1000);
  return () => { clearInterval(interval); document.title = originalTitle; };
}''',
        "provides": "flashTitle(message, originalTitle)",
        "depends": [],
    },
    {
        "id": "brw-position",
        "name": "Element Position Getter",
        "category": "brw",
        "lang": "typescript",
        "when": "Placing tooltips/popovers relative to an anchor element",
        "why": "Atomic getter: element in, viewport-relative rect out, fixed/absolute friendly",
        "tags": ["brw", "position", "rect", "tooltip", "geometry"],
        "iface": r'''export interface ViewportRect { top: number; left: number; width: number; height: number; bottom: number; right: number }
export function getViewportRect(el: Element): ViewportRect''',
        "code": r'''export function getViewportRect(el: Element): ViewportRect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height, bottom: r.bottom, right: r.right };
}''',
        "provides": "getViewportRect(el)",
        "depends": [],
    },
    {
        "id": "brw-raf-loop",
        "name": "requestAnimationFrame Loop",
        "category": "brw",
        "lang": "typescript",
        "when": "Running a per-frame update/render loop",
        "why": "Atomic loop: tick fn in, start/stop out, delta-time normalized",
        "tags": ["brw", "raf", "loop", "frame", "animation"],
        "iface": r'''export class RafLoop {
  constructor(tick: (dt: number, time: number) => void)
  start(): void
  stop(): void
  get running(): boolean
}''',
        "code": r'''export class RafLoop {
  private raf = 0;
  private last = 0;
  private _running = false;
  constructor(private tick: (dt: number, time: number) => void) {}
  private frame = (now: number) => {
    if (!this.last) this.last = now;
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    this.tick(dt, now);
    this.raf = requestAnimationFrame(this.frame);
  };
  start() { if (this._running) return; this._running = true; this.last = 0; this.raf = requestAnimationFrame(this.frame); }
  stop() { if (!this._running) return; cancelAnimationFrame(this.raf); this._running = false; }
  get running() { return this._running; }
}''',
        "provides": "RafLoop",
        "depends": [],
    },
    {
        "id": "brw-debounce-resize",
        "name": "Debounced Resize Handler",
        "category": "brw",
        "lang": "typescript",
        "when": "Reacting to window resizes without jank",
        "why": "Atomic handler: callback in, trailing-debounced subscription out",
        "tags": ["brw", "resize", "debounce", "window", "handler"],
        "iface": r'''export function onResizeDebounced(cb: () => void, delayMs?: number): () => void''',
        "code": r'''export function onResizeDebounced(cb: () => void, delayMs = 150) {
  let t: ReturnType<typeof setTimeout> | null = null;
  const handler = () => {
    if (t) clearTimeout(t);
    t = setTimeout(cb, delayMs);
  };
  window.addEventListener('resize', handler);
  return () => { if (t) clearTimeout(t); window.removeEventListener('resize', handler); };
}''',
        "provides": "onResizeDebounced(cb, delayMs)",
        "depends": [],
    },
    {
        "id": "brw-notify",
        "name": "Notification Wrapper",
        "category": "brw",
        "lang": "typescript",
        "when": "Showing a browser notification with permission flow",
        "why": "Atomic wrapper: request permission, notify, fallback to in-app callback",
        "tags": ["brw", "notification", "permission", "toast", "wrapper"],
        "iface": r'''export async function requestNotifyPermission(): Promise<boolean>
export function notify(title: string, opts?: { body?: string; icon?: string }): void''',
        "code": r'''export async function requestNotifyPermission() {
  if (!('Notification' in window)) return false;
  if (Notification.permission === 'granted') return true;
  if (Notification.permission === 'denied') return false;
  return (await Notification.requestPermission()) === 'granted';
}
export function notify(title: string, opts: { body?: string; icon?: string } = {}) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  try { new Notification(title, opts); } catch { /* unsupported */ }
}''',
        "provides": "requestNotifyPermission / notify",
        "depends": [],
    },
]
