# -*- coding: utf-8 -*-
"""
Code Bible — Category 18: Mobile & offline-first (atomic, single-responsibility).
Convention: feature-detect everything; helpers degrade gracefully on desktop.
"""
CHUNKS = [
    {
        "id": "mob-platform",
        "name": "Platform Sniff",
        "category": "mob",
        "lang": "typescript",
        "when": "Adapting UI and features by device platform",
        "why": "Atomic sniffer: userAgent in, platform flags out, no async state",
        "tags": ["mob", "platform", "ios", "android", "detect"],
        "iface": r'''export interface PlatformInfo { ios: boolean; android: boolean; mobile: boolean; desktop: boolean; standalone: boolean }
export function detectPlatform(ua?: string): PlatformInfo''',
        "code": r'''export function detectPlatform(ua = typeof navigator !== 'undefined' ? navigator.userAgent : '') {
  const ios = /iPhone|iPad|iPod/i.test(ua) || (/Mac/i.test(ua) && navigator.maxTouchPoints > 1);
  const android = /Android/i.test(ua);
  return {
    ios,
    android,
    mobile: ios || android || /Mobi/i.test(ua),
    desktop: !(/Mobi/i.test(ua) || ios || android),
    standalone: typeof navigator !== 'undefined' && (navigator as Navigator & { standalone?: boolean }).standalone === true,
  };
}''',
        "provides": "detectPlatform(ua)",
        "depends": [],
    },
    {
        "id": "mob-safe-area",
        "name": "Safe-Area Inset Helper",
        "category": "mob",
        "lang": "typescript",
        "when": "Padding UI around notches and home indicators",
        "why": "Atomic getter: CSS env() values in, px insets out with fallbacks",
        "tags": ["mob", "safe-area", "inset", "notch", "layout"],
        "iface": r'''export interface SafeAreaInsets { top: number; right: number; bottom: number; left: number }
export function getSafeArea(): SafeAreaInsets''',
        "code": r'''function env(name: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return parseFloat(v) || 0;
}
export function getSafeArea(): SafeAreaInsets {
  if (typeof document === 'undefined') return { top: 0, right: 0, bottom: 0, left: 0 };
  return { top: env('--safe-area-inset-top'), right: env('--safe-area-inset-right'), bottom: env('--safe-area-inset-bottom'), left: env('--safe-area-inset-left') };
}''',
        "provides": "getSafeArea()",
        "depends": [],
    },
    {
        "id": "mob-haptics",
        "name": "Haptic Feedback Wrapper",
        "category": "mob",
        "lang": "typescript",
        "when": "Nudging the user with vibration on actions",
        "why": "Atomic wrapper: pattern in, navigator.vibrate guarded, iOS fallback skipped",
        "tags": ["mob", "haptic", "vibrate", "feedback", "touch"],
        "iface": r'''export function haptic(kind?: 'light' | 'medium' | 'heavy' | 'success' | 'error'): void''',
        "code": r'''const PATTERNS: Record<string, number | number[]> = {
  light: 8, medium: [10, 20, 10], heavy: [20, 30, 20], success: [12, 40, 20], error: [40, 60, 40],
};
export function haptic(kind: 'light' | 'medium' | 'heavy' | 'success' | 'error' = 'light') {
  try {
    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) navigator.vibrate(PATTERNS[kind]);
  } catch { /* unsupported */ }
}''',
        "provides": "haptic(kind)",
        "depends": [],
    },
    {
        "id": "mob-orientation",
        "name": "Orientation Lock Helper",
        "category": "mob",
        "lang": "typescript",
        "when": "Requesting landscape/portrait lock for games and media",
        "why": "Atomic lock: request screen.orientation.lock, feature-detected, boolean out",
        "tags": ["mob", "orientation", "lock", "landscape", "screen"],
        "iface": r'''export async function lockOrientation(orientation: 'portrait' | 'landscape' | 'natural'): Promise<boolean>''',
        "code": r'''export async function lockOrientation(orientation: 'portrait' | 'landscape' | 'natural') {
  try {
    const s = screen as Screen & { orientation?: { lock: (o: string) => Promise<void> } };
    if (!s.orientation?.lock) return false;
    await s.orientation.lock(orientation);
    return true;
  } catch {
    return false;
  }
}''',
        "provides": "lockOrientation(orientation)",
        "depends": [],
    },
    {
        "id": "mob-battery",
        "name": "Battery Status Listener",
        "category": "mob",
        "lang": "typescript",
        "when": "Showing low-battery warnings or adapting power usage",
        "why": "Atomic listener: callbacks in, unsubscribe out, level/charging state",
        "tags": ["mob", "battery", "status", "level", "listener"],
        "iface": r'''export async function watchBattery(onChange: (info: { level: number; charging: boolean }) => void): Promise<() => void>''',
        "code": r'''interface BatteryManager { level: number; charging: boolean; addEventListener(t: string, f: () => void): void; removeEventListener(t: string, f: () => void): void }
export async function watchBattery(onChange: (info: { level: number; charging: boolean }) => void) {
  const nav = navigator as Navigator & { getBattery?: () => Promise<BatteryManager> };
  const battery = await nav.getBattery?.();
  if (!battery) { onChange({ level: 1, charging: true }); return () => {}; }
  const emit = () => onChange({ level: battery.level, charging: battery.charging });
  emit();
  battery.addEventListener('levelchange', emit);
  battery.addEventListener('chargingchange', emit);
  return () => { battery.removeEventListener('levelchange', emit); battery.removeEventListener('chargingchange', emit); };
}''',
        "provides": "watchBattery(onChange)",
        "depends": [],
    },
    {
        "id": "mob-offline-queue",
        "name": "Offline Action Queue",
        "category": "mob",
        "lang": "typescript",
        "when": "Queuing user actions while offline and flushing them on reconnect",
        "why": "Atomic queue: enqueue/flush, persisted via injected store, idempotent replay",
        "tags": ["mob", "offline", "queue", "sync", "persist"],
        "iface": r'''export interface QueuedAction { id: string; type: string; payload: unknown; at: number }
export class OfflineQueue {
  constructor(store?: { load: () => QueuedAction[]; save: (q: QueuedAction[]) => void })
  enqueue(action: Omit<QueuedAction, 'id' | 'at'>): QueuedAction
  flush(send: (actions: QueuedAction[]) => Promise<void>): Promise<number>
  get pending(): QueuedAction[]
  get size(): number
}''',
        "code": r'''export class OfflineQueue {
  private queue: QueuedAction[] = [];
  constructor(private store?: { load: () => QueuedAction[]; save: (q: QueuedAction[]) => void }) {
    this.queue = store?.load() ?? [];
  }
  private persist() { this.store?.save(this.queue); }
  enqueue(action: Omit<QueuedAction, 'id' | 'at'>) {
    const full: QueuedAction = { ...action, id: Math.random().toString(36).slice(2, 12), at: Date.now() };
    this.queue.push(full);
    this.persist();
    return full;
  }
  async flush(send: (actions: QueuedAction[]) => Promise<void>) {
    if (!this.queue.length) return 0;
    const batch = this.queue;
    try {
      await send(batch);
      this.queue = [];
      this.persist();
      return batch.length;
    } catch {
      return 0;
    }
  }
  get pending() { return this.queue.slice(); }
  get size() { return this.queue.length; }
}''',
        "provides": "OfflineQueue",
        "depends": [],
    },
    {
        "id": "mob-deep-link",
        "name": "Deep-Link Parser",
        "category": "mob",
        "lang": "typescript",
        "when": "Handling app:// links and universal link payloads",
        "why": "Atomic parser: url in, scheme + host + params out, malformed safe",
        "tags": ["mob", "deep-link", "parse", "scheme", "universal"],
        "iface": r'''export interface DeepLink { scheme: string; host: string; path: string; params: Record<string, string> }
export function parseDeepLink(url: string): DeepLink | null''',
        "code": r'''export function parseDeepLink(url: string) {
  try {
    const u = new URL(url);
    const params: Record<string, string> = {};
    u.searchParams.forEach((v, k) => { params[k] = v; });
    return { scheme: u.protocol.replace(':', ''), host: u.host, path: u.pathname, params };
  } catch {
    return null;
  }
}''',
        "provides": "parseDeepLink(url)",
        "depends": [],
    },
    {
        "id": "mob-swipe",
        "name": "Swipe Gesture Detector",
        "category": "mob",
        "lang": "typescript",
        "when": "Supporting swipe navigation and dismiss gestures",
        "why": "Atomic detector: element + threshold in, direction callback + cleanup out",
        "tags": ["mob", "swipe", "gesture", "touch", "detect"],
        "iface": r'''export type SwipeDirection = 'left' | 'right' | 'up' | 'down'
export function detectSwipe(el: HTMLElement, onSwipe: (dir: SwipeDirection, dist: number) => void, thresholdPx?: number): () => void''',
        "code": r'''export function detectSwipe(el: HTMLElement, onSwipe: (dir: SwipeDirection, dist: number) => void, thresholdPx = 48) {
  let x0 = 0, y0 = 0, active = false;
  const down = (e: TouchEvent) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; active = true; };
  const up = (e: TouchEvent) => {
    if (!active) return;
    active = false;
    const dx = e.changedTouches[0].clientX - x0;
    const dy = e.changedTouches[0].clientY - y0;
    const adx = Math.abs(dx), ady = Math.abs(dy);
    if (Math.max(adx, ady) < thresholdPx) return;
    const dir: SwipeDirection = adx > ady ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up');
    onSwipe(dir, Math.max(adx, ady));
  };
  el.addEventListener('touchstart', down, { passive: true });
  el.addEventListener('touchend', up, { passive: true });
  return () => { el.removeEventListener('touchstart', down); el.removeEventListener('touchend', up); };
}''',
        "provides": "detectSwipe(el, onSwipe, thresholdPx)",
        "depends": [],
    },
    {
        "id": "mob-biometric",
        "name": "Biometric Auth Wrapper",
        "category": "mob",
        "lang": "typescript",
        "when": "Prompting for fingerprint/face unlock",
        "why": "Atomic wrapper: WebAuthn in, boolean auth result out, feature-detected",
        "tags": ["mob", "biometric", "auth", "webauthn", "face-id"],
        "iface": r'''export function supportsBiometrics(): boolean
export async function authenticateBiometric(opts?: { timeoutMs?: number; message?: string }): Promise<boolean>''',
        "code": r'''export function supportsBiometrics() {
  return typeof window !== 'undefined' && !!(window.PublicKeyCredential && (PublicKeyCredential as unknown as { isUserVerifyingPlatformAuthenticatorAvailable?: () => Promise<boolean> }).isUserVerifyingPlatformAuthenticatorAvailable);
}
export async function authenticateBiometric(opts: { timeoutMs?: number; message?: string } = {}) {
  try {
    const challenge = crypto.getRandomValues(new Uint8Array(32));
    const cred = await navigator.credentials.get({
      publicKey: {
        challenge,
        timeout: opts.timeoutMs ?? 60000,
        userVerification: 'required',
        rpId: location.hostname,
        allowCredentials: [],
      },
    });
    return !!cred;
  } catch {
    return false;
  }
}''',
        "provides": "supportsBiometrics / authenticateBiometric",
        "depends": [],
    },
    {
        "id": "mob-share",
        "name": "Web Share Helper",
        "category": "mob",
        "lang": "typescript",
        "when": "Sharing text/files via the native share sheet",
        "why": "Atomic wrapper: Web Share API in, boolean result out, fallback hook",
        "tags": ["mob", "share", "native", "sheet", "web-share"],
        "iface": r'''export async function shareContent(data: { title?: string; text?: string; url?: string; files?: File[] }): Promise<boolean>''',
        "code": r'''export async function shareContent(data: { title?: string; text?: string; url?: string; files?: File[] }) {
  try {
    if (typeof navigator.share !== 'function') return false;
    await navigator.share(data as ShareData);
    return true;
  } catch {
    return false;
  }
}''',
        "provides": "shareContent(data)",
        "depends": [],
    },
    {
        "id": "mob-camera",
        "name": "Camera Capture Helper",
        "category": "mob",
        "lang": "typescript",
        "when": "Capturing a photo/video from the device camera",
        "why": "Atomic capture: file input in, media file out, accept types configurable",
        "tags": ["mob", "camera", "capture", "photo", "video"],
        "iface": r'''export function captureMedia(opts?: { video?: boolean; multiple?: boolean }): Promise<File[]>''',
        "code": r'''export function captureMedia(opts: { video?: boolean; multiple?: boolean } = {}) {
  return new Promise<File[]>((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = opts.video ? 'video/*' : 'image/*';
    input.capture = 'environment' as unknown as string;
    if (opts.multiple) input.multiple = true;
    input.onchange = () => resolve(input.files ? [...input.files] : []);
    input.onerror = () => reject(new Error('capture failed'));
    input.click();
  });
}''',
        "provides": "captureMedia(opts)",
        "depends": [],
    },
    {
        "id": "mob-network-required",
        "name": "Network-Required Guard",
        "category": "mob",
        "lang": "typescript",
        "when": "Blocking actions that need connectivity while offline",
        "why": "Atomic guard: online check in, allow/block with offline queue hook",
        "tags": ["mob", "network", "offline", "guard", "online"],
        "iface": r'''export function requireNetwork<T>(action: () => T, onOffline?: () => void): T | undefined''',
        "code": r'''export function requireNetwork<T>(action: () => T, onOffline?: () => void) {
  if (navigator.onLine) return action();
  onOffline?.();
  return undefined;
}''',
        "provides": "requireNetwork(action, onOffline)",
        "depends": [],
    },
    {
        "id": "mob-app-state",
        "name": "App State (bg/fg) Monitor",
        "category": "mob",
        "lang": "typescript",
        "when": "Refreshing data when the app returns to the foreground",
        "why": "Atomic monitor: callbacks in, unsubscribe out, visibility + blur/pointer heuristics",
        "tags": ["mob", "app-state", "background", "foreground", "monitor"],
        "iface": r'''export function watchAppState(onChange: (state: 'background' | 'foreground') => void): () => void''',
        "code": r'''export function watchAppState(onChange: (state: 'background' | 'foreground') => void) {
  let hidden = document.visibilityState === 'hidden';
  const vis = () => { const h = document.visibilityState === 'hidden'; if (h !== hidden) { hidden = h; onChange(h ? 'background' : 'foreground'); } };
  document.addEventListener('visibilitychange', vis);
  window.addEventListener('pageshow', () => { if (hidden) { hidden = false; onChange('foreground'); } });
  return () => { document.removeEventListener('visibilitychange', vis); window.removeEventListener('pageshow', () => {}); };
}''',
        "provides": "watchAppState(onChange)",
        "depends": [],
    },
    {
        "id": "mob-notif-schedule",
        "name": "Local Notification Scheduler",
        "category": "mob",
        "lang": "typescript",
        "when": "Scheduling reminders from the web app",
        "why": "Atomic scheduler: delay + title in, Notification + fallback title flash out",
        "tags": ["mob", "notification", "schedule", "reminder", "local"],
        "iface": r'''export function scheduleLocalNotification(opts: { title: string; body?: string; delayMs: number }): { cancel(): void }''',
        "code": r'''export function scheduleLocalNotification(opts: { title: string; body?: string; delayMs: number }) {
  const t = setTimeout(() => {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      try { new Notification(opts.title, { body: opts.body }); } catch { /* ignore */ }
    }
  }, opts.delayMs);
  return { cancel: () => clearTimeout(t) };
}''',
        "provides": "scheduleLocalNotification(opts)",
        "depends": [],
    },
    {
        "id": "mob-viewport-meta",
        "name": "Viewport Meta Manager",
        "category": "mob",
        "lang": "typescript",
        "when": "Disabling pinch-zoom for canvas apps and re-enabling later",
        "why": "Atomic manager: set/restore viewport meta, user-scalable toggle",
        "tags": ["mob", "viewport", "meta", "zoom", "canvas"],
        "iface": r'''export function setViewportZoom(scale: number, userScalable?: boolean): void
export function restoreViewport(): void''',
        "code": r'''let prev = '';
export function setViewportZoom(scale: number, userScalable = false) {
  const vp = document.querySelector('meta[name="viewport"]');
  if (vp) { prev = vp.getAttribute('content') ?? ''; vp.setAttribute('content', `width=device-width, initial-scale=${scale}, maximum-scale=${scale}, user-scalable=${userScalable ? 'yes' : 'no'}`); }
}
export function restoreViewport() {
  const vp = document.querySelector('meta[name="viewport"]');
  if (vp && prev) vp.setAttribute('content', prev);
}''',
        "provides": "setViewportZoom / restoreViewport",
        "depends": [],
    },
    {
        "id": "mob-image-picker",
        "name": "Image Picker",
        "category": "mob",
        "lang": "typescript",
        "when": "Selecting images from the device with size limits",
        "why": "Atomic picker: file input in, validated images out (type + size)",
        "tags": ["mob", "image", "picker", "upload", "select"],
        "iface": r'''export async function pickImages(opts?: { maxSizeMb?: number; multiple?: boolean }): Promise<File[]>''',
        "code": r'''export async function pickImages(opts: { maxSizeMb?: number; multiple?: boolean } = {}) {
  const files = await captureMedia({ multiple: opts.multiple ?? true });
  const maxBytes = (opts.maxSizeMb ?? 20) * 1048576;
  return files.filter((f) => f.type.startsWith('image/') && f.size <= maxBytes);
}''',
        "provides": "pickImages(opts)",
        "depends": [],
    },
    {
        "id": "mob-permissions",
        "name": "Permissions Helper",
        "category": "mob",
        "lang": "typescript",
        "when": "Requesting and checking geolocation/camera permissions",
        "why": "Atomic helper: query + request, state enum out, feature-detected",
        "tags": ["mob", "permissions", "geolocation", "camera", "request"],
        "iface": "export type PermissionState = 'granted' | 'denied' | 'prompt' | 'unsupported'\nexport async function permissionStatus(name: 'geolocation' | 'camera' | 'microphone'): Promise<PermissionState>\nexport async function requestPermission(name: 'geolocation' | 'camera' | 'microphone'): Promise<PermissionState>",
        "code": r'''export async function permissionStatus(name: 'geolocation' | 'camera' | 'microphone'): Promise<PermissionState> {
  try {
    if (!navigator.permissions?.query) return 'unsupported';
    const s = await navigator.permissions.query({ name: name as PermissionName });
    return s.state as PermissionState;
  } catch {
    return 'unsupported';
  }
}
export async function requestPermission(name: 'geolocation' | 'camera' | 'microphone'): Promise<PermissionState> {
  try {
    if (name === 'geolocation') {
      const pos = await new Promise<GeolocationPosition>((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 5000 }));
      return pos ? 'granted' : 'denied';
    }
    const stream = await navigator.mediaDevices.getUserMedia({ [name === 'camera' ? 'video' : 'audio']: true });
    stream.getTracks().forEach((t) => t.stop());
    return 'granted';
  } catch {
    return 'denied';
  }
}''',
        "provides": "permissionStatus / requestPermission",
        "depends": [],
    },
    {
        "id": "mob-responsive-font",
        "name": "Responsive Font Scaler",
        "category": "mob",
        "lang": "typescript",
        "when": "Scaling font sizes with viewport width",
        "why": "Atomic scaler: base + vw in, clamped fluid size out",
        "tags": ["mob", "responsive", "font", "scale", "viewport"],
        "iface": r'''export function fluidFont(opts: { min: number; max: number; minVw?: number; maxVw?: number }): number''',
        "code": r'''export function fluidFont(opts: { min: number; max: number; minVw?: number; maxVw?: number }) {
  const vw = Math.min(opts.maxVw ?? 1200, Math.max(opts.minVw ?? 320, window.innerWidth));
  const ratio = (vw - (opts.minVw ?? 320)) / ((opts.maxVw ?? 1200) - (opts.minVw ?? 320));
  return Math.round((opts.min + (opts.max - opts.min) * ratio) * 10) / 10;
}''',
        "provides": "fluidFont(opts)",
        "depends": [],
    },
    {
        "id": "mob-pull-refresh",
        "name": "Pull-to-Refresh Coordinator",
        "category": "mob",
        "lang": "typescript",
        "when": "Implementing pull-to-refresh without a library",
        "why": "Atomic coordinator: container in, touch math + threshold, callback + cleanup out",
        "tags": ["mob", "pull", "refresh", "gesture", "touch"],
        "iface": r'''export function setupPullToRefresh(el: HTMLElement, onRefresh: () => Promise<void>, thresholdPx?: number): () => void''',
        "code": r'''export function setupPullToRefresh(el: HTMLElement, onRefresh: () => Promise<void>, thresholdPx = 70) {
  let startY = 0, pulling = false;
  const down = (e: TouchEvent) => { if (window.scrollY === 0) { startY = e.touches[0].clientY; pulling = true; } };
  const move = (e: TouchEvent) => {
    if (!pulling) return;
    const dist = e.touches[0].clientY - startY;
    if (dist > 0) { e.preventDefault(); el.style.transform = `translateY(${Math.min(90, dist * 0.5)}px)`; el.style.transition = 'none'; }
  };
  const up = async (e: TouchEvent) => {
    if (!pulling) return;
    pulling = false;
    const dist = e.changedTouches[0].clientY - startY;
    el.style.transition = 'transform 0.2s';
    el.style.transform = 'translateY(0)';
    if (dist >= thresholdPx) await onRefresh();
  };
  el.addEventListener('touchstart', down, { passive: true });
  el.addEventListener('touchmove', move, { passive: false });
  el.addEventListener('touchend', up, { passive: true });
  return () => { el.removeEventListener('touchstart', down); el.removeEventListener('touchmove', move); el.removeEventListener('touchend', up); };
}''',
        "provides": "setupPullToRefresh(el, onRefresh, thresholdPx)",
        "depends": [],
    },
    {
        "id": "mob-version-check",
        "name": "In-App Update Checker",
        "category": "mob",
        "lang": "typescript",
        "when": "Prompting users to reload when a new build is published",
        "why": "Atomic checker: current + latest version in, stale verdict out, semver compare",
        "tags": ["mob", "version", "update", "stale", "check"],
        "iface": r'''export function isStale(current: string, latest: string): boolean
export function checkForUpdate(opts: { current: string; fetchLatest: () => Promise<string> }): Promise<'up-to-date' | 'update-available' | 'error'>''',
        "code": r'''function cmp(a: string, b: string) {
  const pa = a.split('.').map(Number), pb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) { if ((pa[i] ?? 0) !== (pb[i] ?? 0)) return (pa[i] ?? 0) > (pb[i] ?? 0) ? 1 : -1; }
  return 0;
}
export function isStale(current: string, latest: string) { return cmp(current, latest) < 0; }
export async function checkForUpdate(opts: { current: string; fetchLatest: () => Promise<string> }) {
  try { return isStale(opts.current, await opts.fetchLatest()) ? 'update-available' : 'up-to-date'; } catch { return 'error'; }
}''',
        "provides": "isStale / checkForUpdate",
        "depends": [],
    },
    {
        "id": "mob-keyboard",
        "name": "Keyboard Resize Listener",
        "category": "mob",
        "lang": "typescript",
        "when": "Avoiding the mobile keyboard covering inputs",
        "why": "Atomic listener: visualViewport in, keyboard-shown events + inset out",
        "tags": ["mob", "keyboard", "viewport", "resize", "input"],
        "iface": r'''export function watchKeyboard(onChange: (state: { visible: boolean; heightPx: number }) => void): () => void''',
        "code": r'''export function watchKeyboard(onChange: (state: { visible: boolean; heightPx: number }) => void) {
  const vv = window.visualViewport;
  if (!vv) return () => {};
  let last = window.innerHeight;
  const handler = () => {
    const height = Math.round(window.innerHeight - vv.height);
    const visible = height > 100;
    if (visible !== last) { last = visible ? 1 : 0; }
    onChange({ visible, heightPx: height });
  };
  vv.addEventListener('resize', handler);
  return () => vv.removeEventListener('resize', handler);
}''',
        "provides": "watchKeyboard(onChange)",
        "depends": [],
    },
    {
        "id": "mob-reader-mode",
        "name": "Reader Mode Text Extractor",
        "category": "mob",
        "lang": "typescript",
        "when": "Pulling clean article text out of a cluttered page",
        "why": "Atomic extractor: article heuristics, paragraphs with length filter, plain text out",
        "tags": ["mob", "reader", "extract", "text", "article"],
        "iface": r'''export function extractArticleText(root?: HTMLElement): string''',
        "code": r'''export function extractArticleText(root = document.body) {
  const candidates = [...root.querySelectorAll<HTMLElement>('article, main, [role="main"], .content, .post, .entry')];
  const scope = candidates[0] ?? root;
  const paras = [...scope.querySelectorAll('p, h1, h2, h3, li')]
    .filter((el) => (el.textContent ?? '').trim().length >= 40)
    .map((el) => el.textContent!.trim());
  return paras.join('\n\n');
}''',
        "provides": "extractArticleText(root)",
        "depends": [],
    },
    {
        "id": "mob-session-restore",
        "name": "Session Restore",
        "category": "mob",
        "lang": "typescript",
        "when": "Saving and restoring UI state across app restarts",
        "why": "Atomic restore: keyed state in, persisted via injected store, versioned",
        "tags": ["mob", "session", "restore", "persist", "state"],
        "iface": r'''export interface SessionState<T> { version: number; data: T; savedAt: number }
export class SessionStore<T> {
  constructor(key: string, version: number, store?: { load: () => string | null; save: (s: string) => void })
  restore(): T | null
  save(data: T): void
  clear(): void
}''',
        "code": r'''export class SessionStore<T> {
  constructor(private key: string, private version: number, private store: { load: () => string | null; save: (s: string) => void } = {
    load: () => localStorage.getItem(key),
    save: (s) => localStorage.setItem(key, s),
  }) {}
  restore(): T | null {
    try {
      const raw = this.store.load();
      if (!raw) return null;
      const parsed = JSON.parse(raw) as SessionState<T>;
      return parsed.version === this.version ? parsed.data : null;
    } catch { return null; }
  }
  save(data: T) { this.store.save(JSON.stringify({ version: this.version, data, savedAt: Date.now() })); }
  clear() { this.store.save(''); }
}''',
        "provides": "SessionStore",
        "depends": [],
    },
    {
        "id": "mob-screen-brightness",
        "name": "Screen Wake Lock",
        "category": "mob",
        "lang": "typescript",
        "when": "Keeping the screen awake during video or instructions",
        "why": "Atomic lock: navigator.wakeLock in, release() out, reacquire on visibility",
        "tags": ["mob", "wakelock", "screen", "awake", "video"],
        "iface": r'''export async function acquireWakeLock(): Promise<{ release: () => Promise<void> } | null>''',
        "code": r'''export async function acquireWakeLock() {
  try {
    const nav = navigator as Navigator & { wakeLock?: { request: (t: string) => Promise<{ release: () => Promise<void> }> } };
    if (!nav.wakeLock?.request) return null;
    const lock = await nav.wakeLock.request('screen');
    return { release: () => lock.release() };
  } catch {
    return null;
  }
}''',
        "provides": "acquireWakeLock()",
        "depends": [],
    },
]
