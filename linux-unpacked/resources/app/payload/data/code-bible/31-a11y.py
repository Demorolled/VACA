# -*- coding: utf-8 -*-
"""
Code Bible — Category 31: Accessibility (atomic).
Convention: DOM-safe helpers, no frameworks, WCAG-aware where stated.
"""
CHUNKS = [
    {
        "id": "acc-live-region",
        "name": "ARIA Live Region",
        "category": "acc",
        "lang": "typescript",
        "when": "Announcing dynamic updates to screen readers without focus moves",
        "why": "Atomic live region — creates aria-live element, polite/assertive, queued",
        "tags": ["acc", "aria", "live-region", "screen-reader", "announce"],
        "iface": r'''export class LiveRegion {
  constructor(container?: HTMLElement)
  announce(text: string, mode?: 'polite' | 'assertive'): void
}''',
        "code": r'''export class LiveRegion {
  private el: HTMLElement;
  constructor(container: HTMLElement = document.body) {
    this.el = document.createElement('div');
    this.el.setAttribute('aria-live', 'polite');
    this.el.setAttribute('role', 'status');
    this.el.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);';
    container.appendChild(this.el);
  }
  announce(text: string, mode: 'polite' | 'assertive' = 'polite') {
    this.el.setAttribute('aria-live', mode);
    this.el.textContent = '';
    requestAnimationFrame(() => { this.el.textContent = text; });
  }
}''',
        "provides": "LiveRegion",
        "depends": [],
    },
    {
        "id": "acc-focus-manager",
        "name": "Focus Manager",
        "category": "acc",
        "lang": "typescript",
        "when": "Moving focus safely between focusable elements",
        "why": "Atomic focus helpers — query focusables, move next/prev, set with fallback",
        "tags": ["acc", "focus", "keyboard", "navigation", "manager"],
        "iface": r'''export class FocusManager {
  constructor(scope: HTMLElement)
  focusNext(): void
  focusPrev(): void
  first(): void
}''',
        "code": r'''const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
export class FocusManager {
  private els: HTMLElement[];
  constructor(scope: HTMLElement) { this.els = [...scope.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((e) => e.offsetParent !== null); }
  private focus(i: number) {
    if (this.els.length) this.els[(i + this.els.length) % this.els.length].focus();
  }
  focusNext() {
    const cur = document.activeElement;
    this.focus(this.els.indexOf(cur as HTMLElement) + 1);
  }
  focusPrev() {
    const cur = document.activeElement;
    this.focus(this.els.indexOf(cur as HTMLElement) - 1);
  }
  first() { this.focus(0); }
}''',
        "provides": "FocusManager",
        "depends": [],
    },
    {
        "id": "acc-skip-link",
        "name": "Skip Link",
        "category": "acc",
        "lang": "typescript",
        "when": "Letting keyboard users jump straight to the main content",
        "why": "Atomic skip target — inject link on first Tab press, target focus + scroll",
        "tags": ["acc", "skip-link", "keyboard", "navigation"],
        "iface": r'''export function installSkipLink(targetId: string, label = 'Skip to main content'): void''',
        "code": r'''export function installSkipLink(targetId: string, label = 'Skip to main content') {
  const target = document.getElementById(targetId);
  if (!target) return;
  const link = document.createElement('a');
  link.href = '#' + targetId;
  link.textContent = label;
  link.className = 'skip-link';
  link.style.cssText = 'position:absolute;left:-9999px;top:0;z-index:10000;';
  link.addEventListener('focus', () => { link.style.left = '0'; });
  link.addEventListener('blur', () => { link.style.left = '-9999px'; });
  link.addEventListener('click', () => { target.setAttribute('tabindex', '-1'); target.focus(); });
  document.body.prepend(link);
}''',
        "provides": "installSkipLink(targetId, label?)",
        "depends": [],
    },
    {
        "id": "acc-kbd-grid",
        "name": "Keyboard Grid Navigation",
        "category": "acc",
        "lang": "typescript",
        "when": "Arrow-key navigation across a grid of focusable cells",
        "why": "Atomic grid cursor — roving tabindex, arrows move by columns/rows, Home/End",
        "tags": ["acc", "keyboard", "grid", "navigation", "arrows"],
        "iface": r'''export class KeyboardGrid {
  constructor(scope: HTMLElement, cols: number)
  attach(): void
}''',
        "code": r'''export class KeyboardGrid {
  constructor(private scope: HTMLElement, private cols: number) {}
  attach() {
    const cells = [...this.scope.querySelectorAll<HTMLElement>('[role="gridcell"], [role="option"]')];
    if (!cells.length) return;
    cells[0].setAttribute('tabindex', '0');
    const move = (from: number, dc: number, dr: number) => {
      const r = Math.floor(from / this.cols), c = from % this.cols;
      const nr = r + dr, nc = c + dc;
      if (nr < 0 || nc < 0 || nc >= this.cols) return;
      const idx = nr * this.cols + nc;
      if (idx >= cells.length) return;
      cells.forEach((el, i) => el.setAttribute('tabindex', i === idx ? '0' : '-1'));
      cells[idx].focus();
    };
    this.scope.addEventListener('keydown', (e) => {
      const idx = cells.indexOf(document.activeElement as HTMLElement);
      if (idx === -1) return;
      const step = e.key === 'ArrowRight' ? () => move(idx, 1, 0) : e.key === 'ArrowLeft' ? () => move(idx, -1, 0)
        : e.key === 'ArrowDown' ? () => move(idx, 0, 1) : e.key === 'ArrowUp' ? () => move(idx, 0, -1)
        : e.key === 'Home' ? () => { cells[0].focus(); } : e.key === 'End' ? () => { cells[cells.length - 1].focus(); } : null;
      if (step) { e.preventDefault(); step(); }
    });
  }
}''',
        "provides": "KeyboardGrid",
        "depends": [],
    },
    {
        "id": "acc-sr-only",
        "name": "Screen-Reader-Only Text",
        "category": "acc",
        "lang": "typescript",
        "when": "Hiding a label visually while keeping it for screen readers",
        "why": "Atomic sr-only — injects the clipped class + helper to create such elements",
        "tags": ["acc", "sr-only", "screen-reader", "visually-hidden"],
        "iface": r'''export const SR_ONLY_CSS = string
export function srOnly(text: string): HTMLElement''',
        "code": r'''export const SR_ONLY_CSS = '.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}';
export function srOnly(text: string) {
  const el = document.createElement('span');
  el.className = 'sr-only';
  el.textContent = text;
  return el;
}''',
        "provides": "SR_ONLY_CSS / srOnly(text)",
        "depends": [],
    },
    {
        "id": "acc-reduced-motion",
        "name": "Reduced Motion Gate",
        "category": "acc",
        "lang": "typescript",
        "when": "Disabling animations for users who prefer reduced motion",
        "why": "Atomic media-query gate — prefers-reduced-motion check + change listener",
        "tags": ["acc", "reduced-motion", "animation", "media-query"],
        "iface": r'''export function prefersReducedMotion(): boolean
export function onReducedMotionChange(h: (reduced: boolean) => void): () => void''',
        "code": r'''const MQ = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
export function prefersReducedMotion() { return MQ ? MQ.matches : false; }
export function onReducedMotionChange(h: (reduced: boolean) => void) {
  const cb = (e: MediaQueryListEvent) => h(e.matches);
  MQ?.addEventListener('change', cb);
  return () => MQ?.removeEventListener('change', cb);
}''',
        "provides": "prefersReducedMotion / onReducedMotionChange",
        "depends": [],
    },
    {
        "id": "acc-contrast",
        "name": "WCAG Contrast Checker",
        "category": "acc",
        "lang": "typescript",
        "when": "Verifying text/background contrast ratios meet WCAG levels",
        "why": "Atomic ratio math — relative luminance, AA/AAA thresholds for normal/large text",
        "tags": ["acc", "contrast", "wcag", "luminance", "aa"],
        "iface": r'''export function contrastRatio(fg: string, bg: string): number
export function contrastPass(ratio: number, largeText: boolean, level: 'AA' | 'AAA' = 'AA'): boolean''',
        "code": r'''function lum(hex: string) {
  const c = hex.replace('#', '');
  const rgb = [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16) / 255);
  const lin = rgb.map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}
export function contrastRatio(fg: string, bg: string) {
  const l1 = lum(fg), l2 = lum(bg);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}
export function contrastPass(ratio: number, largeText: boolean, level: 'AA' | 'AAA' = 'AA') {
  const target = level === 'AAA' ? (largeText ? 4.5 : 7) : (largeText ? 3 : 4.5);
  return ratio >= target;
}''',
        "provides": "contrastRatio / contrastPass",
        "depends": [],
    },
    {
        "id": "acc-focus-visible",
        "name": "Focus Visible Class",
        "category": "acc",
        "lang": "typescript",
        "when": "Showing focus rings only for keyboard users, not mouse clicks",
        "why": "Atomic focus-visible toggle — adds class on keyboard focus, removes on pointer",
        "tags": ["acc", "focus-visible", "keyboard", "focus-ring"],
        "iface": r'''export function initFocusVisible(className = 'focus-visible'): void''',
        "code": r'''export function initFocusVisible(className = 'focus-visible') {
  document.addEventListener('pointerdown', () => document.body.classList.remove(className), { capture: true });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' || e.key.startsWith('Arrow')) document.body.classList.add(className);
  }, { capture: true });
}''',
        "provides": "initFocusVisible(className?)",
        "depends": [],
    },
    {
        "id": "acc-aria-expanded",
        "name": "ARIA Expanded Toggle",
        "category": "acc",
        "lang": "typescript",
        "when": "Wiring aria-expanded on a disclosure button to its region",
        "why": "Atomic disclosure wiring — button toggles aria-expanded + region hidden state",
        "tags": ["acc", "aria-expanded", "disclosure", "toggle"],
        "iface": r'''export function wireDisclosure(button: HTMLElement, region: HTMLElement): () => void''',
        "code": r'''export function wireDisclosure(button: HTMLElement, region: HTMLElement) {
  const sync = () => {
    const open = button.getAttribute('aria-expanded') === 'true';
    region.hidden = !open;
  };
  button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-controls', region.id);
  sync();
  const onClick = () => {
    button.setAttribute('aria-expanded', button.getAttribute('aria-expanded') === 'true' ? 'false' : 'true');
    sync();
  };
  button.addEventListener('click', onClick);
  return () => button.removeEventListener('click', onClick);
}''',
        "provides": "wireDisclosure(button, region)",
        "depends": [],
    },
    {
        "id": "acc-label-link",
        "name": "Label Association",
        "category": "acc",
        "lang": "typescript",
        "when": "Associating a visible label with a form control by id",
        "why": "Atomic labeler — for/id wiring with auto-unique fallback ids",
        "tags": ["acc", "label", "form", "association", "for"],
        "iface": r'''export function associateLabel(label: HTMLElement, control: HTMLElement): void''',
        "code": r'''export function associateLabel(label: HTMLElement, control: HTMLElement) {
  if (!control.id) control.id = 'ctl-' + Math.random().toString(36).slice(2, 8);
  label.setAttribute('for', control.id);
}''',
        "provides": "associateLabel(label, control)",
        "depends": [],
    },
    {
        "id": "acc-form-announce",
        "name": "Form Error Announcer",
        "category": "acc",
        "lang": "typescript",
        "when": "Announcing validation errors to screen readers and wiring aria-invalid",
        "why": "Atomic error wiring — aria-invalid + describedby + assertive live announce",
        "tags": ["acc", "form", "error", "aria-invalid", "announce"],
        "iface": r'''export function announceError(control: HTMLElement, message: string, announce: (t: string) => void): void''',
        "code": r'''export function announceError(control: HTMLElement, message: string, announce: (t: string) => void) {
  control.setAttribute('aria-invalid', 'true');
  control.setAttribute('aria-describedby', control.getAttribute('aria-describedby') ?? '');
  announce(message);
}''',
        "provides": "announceError(control, message, announce)",
        "depends": [],
    },
    {
        "id": "acc-table-semantics",
        "name": "Table Semantics",
        "category": "acc",
        "lang": "typescript",
        "when": "Adding proper scope/headers semantics to data tables",
        "why": "Atomic table enhancer — scope=col on th, caption id, summary wiring",
        "tags": ["acc", "table", "semantics", "th", "scope"],
        "iface": r'''export function enhanceTable(table: HTMLTableElement): void''',
        "code": r'''export function enhanceTable(table: HTMLTableElement) {
  for (const th of table.querySelectorAll('thead th')) {
    if (!th.hasAttribute('scope')) th.setAttribute('scope', 'col');
  }
  if (!table.querySelector('caption')) {
    const cap = document.createElement('caption');
    cap.className = 'sr-only';
    cap.textContent = table.getAttribute('aria-label') ?? 'Data table';
    table.prepend(cap);
  }
}''',
        "provides": "enhanceTable(table)",
        "depends": [],
    },
    {
        "id": "acc-dialog-wiring",
        "name": "Dialog ARIA Wiring",
        "category": "acc",
        "lang": "typescript",
        "when": "Wiring role=dialog, aria-modal, and labelledby on a custom modal",
        "why": "Atomic dialog semantics — role/modal/labelledby, open state sync",
        "tags": ["acc", "dialog", "aria-modal", "modal", "labelledby"],
        "iface": r'''export function wireDialog(dialog: HTMLElement, titleId?: string, open = false): void''',
        "code": r'''export function wireDialog(dialog: HTMLElement, titleId?: string, open = false) {
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  if (titleId) dialog.setAttribute('aria-labelledby', titleId);
  dialog.hidden = !open;
  dialog.setAttribute('aria-hidden', String(!open));
}''',
        "provides": "wireDialog(dialog, titleId?, open?)",
        "depends": [],
    },
    {
        "id": "acc-icon-button",
        "name": "Accessible Icon Button",
        "category": "acc",
        "lang": "typescript",
        "when": "Giving an icon-only button an accessible name",
        "why": "Atomic naming — aria-label + sr-only fallback span, title for hover",
        "tags": ["acc", "icon", "button", "aria-label", "name"],
        "iface": r'''export function nameIconButton(button: HTMLButtonElement, label: string): void''',
        "code": r'''export function nameIconButton(button: HTMLButtonElement, label: string) {
  button.setAttribute('aria-label', label);
  button.setAttribute('title', label);
  if (!button.textContent?.trim()) button.append(srOnly(label));
}''',
        "provides": "nameIconButton(button, label)",
        "depends": [],
    },
    {
        "id": "acc-status-timer",
        "name": "Status Role Timer",
        "category": "acc",
        "lang": "typescript",
        "when": "Announcing time-limited status updates politely at intervals",
        "why": "Atomic role=status refresher — throttled updates, avoids announcement spam",
        "tags": ["acc", "status", "timer", "announce", "role"],
        "iface": r'''export class StatusAnnouncer {
  constructor(minIntervalMs?: number)
  announce(text: string): void
}''',
        "code": r'''export class StatusAnnouncer {
  private last = 0;
  private el: HTMLElement;
  constructor(private minIntervalMs = 1000, container: HTMLElement = document.body) {
    this.el = document.createElement('div');
    this.el.setAttribute('role', 'status');
    this.el.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;';
    container.appendChild(this.el);
  }
  announce(text: string) {
    const now = Date.now();
    if (now - this.last < this.minIntervalMs) return;
    this.last = now;
    this.el.textContent = text;
  }
}''',
        "provides": "StatusAnnouncer",
        "depends": [],
    },
    {
        "id": "acc-live-queue",
        "name": "Live Region Queue",
        "category": "acc",
        "lang": "typescript",
        "when": "Queueing multiple announcements so none are swallowed",
        "why": "Atomic FIFO announcer — each message announced after the previous one",
        "tags": ["acc", "live-region", "queue", "announce", "order"],
        "iface": r'''export class LiveRegionQueue {
  constructor(announce: (t: string) => void, gapMs?: number)
  enqueue(text: string): void
}''',
        "code": r'''export class LiveRegionQueue {
  private queue: string[] = [];
  private running = false;
  constructor(private announce: (t: string) => void, private gapMs = 150) {}
  enqueue(text: string) {
    this.queue.push(text);
    this.drain();
  }
  private drain() {
    if (this.running || !this.queue.length) return;
    this.running = true;
    const next = this.queue.shift()!;
    this.announce(next);
    setTimeout(() => { this.running = false; this.drain(); }, this.gapMs);
  }
}''',
        "provides": "LiveRegionQueue",
        "depends": [],
    },
    {
        "id": "acc-target-size",
        "name": "Target Size Checker",
        "category": "acc",
        "lang": "typescript",
        "when": "Verifying interactive elements meet minimum touch target sizes",
        "why": "Atomic audit — width/height vs WCAG 2.5.8 min (24px, AA 44px recommended)",
        "tags": ["acc", "target-size", "touch", "wcag", "audit"],
        "iface": r'''export function targetSize(el: HTMLElement): { w: number; h: number; pass: boolean; min: number }''',
        "code": r'''export function targetSize(el: HTMLElement) {
  const r = el.getBoundingClientRect();
  const min = 44; // WCAG 2.5.8 recommendation
  return { w: r.width, h: r.height, pass: r.width >= min && r.height >= min, min };
}''',
        "provides": "targetSize(el)",
        "depends": [],
    },
    {
        "id": "acc-heading-order",
        "name": "Heading Order Validator",
        "category": "acc",
        "lang": "typescript",
        "when": "Finding skipped heading levels in a document outline",
        "why": "Atomic audit — walk h1-h6 sequence, report jumps (h1→h3 etc.)",
        "tags": ["acc", "heading", "outline", "audit", "h1"],
        "iface": r'''export function headingSkips(root: ParentNode = document): Array<{ tag: string; text: string }>''',
        "code": r'''export function headingSkips(root: ParentNode = document) {
  const heads = [...root.querySelectorAll('h1,h2,h3,h4,h5,h6')];
  const out: Array<{ tag: string; text: string }> = [];
  let last = 0;
  for (const h of heads) {
    const level = parseInt(h.tagName[1], 10);
    if (last && level > last + 1) out.push({ tag: h.tagName, text: h.textContent?.slice(0, 60) ?? '' });
    last = level;
  }
  return out;
}''',
        "provides": "headingSkips(root?)",
        "depends": [],
    },
    {
        "id": "acc-landmark",
        "name": "Landmark Helper",
        "category": "acc",
        "lang": "typescript",
        "when": "Ensuring navigation landmarks exist with accessible names",
        "why": "Atomic landmark audit — nav/main/header/footer presence + aria-label check",
        "tags": ["acc", "landmark", "navigation", "main", "audit"],
        "iface": r'''export function landmarkAudit(root: ParentNode = document): Array<{ role: string; ok: boolean; note: string }>''',
        "code": r'''export function landmarkAudit(root: ParentNode = document) {
  const check = (role: string) => {
    const els = [...root.querySelectorAll(`[role="${role}"], ${role === 'navigation' ? 'nav' : role === 'main' ? 'main' : ''}`)];
    return els.length ? { role, ok: true, note: `${els.length} found` } : { role, ok: false, note: 'missing' };
  };
  return ['navigation', 'main'].map(check);
}''',
        "provides": "landmarkAudit(root?)",
        "depends": [],
    },
    {
        "id": "acc-reduced-data",
        "name": "Reduced Data Gate",
        "category": "acc",
        "lang": "typescript",
        "when": "Serving lighter content to users who opt out of heavy data",
        "why": "Atomic prefers-reduced-data gate — returns whether to skip media",
        "tags": ["acc", "reduced-data", "media", "save-data"],
        "iface": r'''export function prefersReducedData(): boolean''',
        "code": r'''export function prefersReducedData() {
  return typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-data: reduce)').matches : false;
}''',
        "provides": "prefersReducedData()",
        "depends": [],
    },
    {
        "id": "acc-touch-audit",
        "name": "Touch Target Audit",
        "category": "acc",
        "lang": "typescript",
        "when": "Scanning a page for interactive elements smaller than the touch minimum",
        "why": "Atomic page audit — all buttons/links/inputs, flag sub-44px, dedupe",
        "tags": ["acc", "touch", "audit", "target", "mobile"],
        "iface": r'''export function touchTargetAudit(root: ParentNode = document): Array<{ selector: string; w: number; h: number }>''',
        "code": r'''export function touchTargetAudit(root: ParentNode = document) {
  const out: Array<{ selector: string; w: number; h: number }> = [];
  for (const el of root.querySelectorAll<HTMLElement>('button, a, input, select, textarea, [role="button"]')) {
    const r = el.getBoundingClientRect();
    if (r.width && r.width < 44 && r.height < 44) {
      const cls = el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : el.tagName.toLowerCase();
      out.push({ selector: cls, w: r.width, h: r.height });
    }
  }
  return out;
}''',
        "provides": "touchTargetAudit(root?)",
        "depends": [],
    },
    {
        "id": "acc-focus-restore",
        "name": "Focus Restore",
        "category": "acc",
        "lang": "typescript",
        "when": "Remembering and restoring focus when a layer closes",
        "why": "Atomic restore — captures activeElement on open, refocuses on close",
        "tags": ["acc", "focus", "restore", "modal", "close"],
        "iface": r'''export class FocusRestore {
  constructor(scope: HTMLElement)
  capture(): void
  restore(): void
}''',
        "code": r'''export class FocusRestore {
  private previous: HTMLElement | null = null;
  constructor(private scope: HTMLElement) {}
  capture() { this.previous = document.activeElement as HTMLElement | null; }
  restore() { if (this.previous?.isConnected) this.previous.focus(); else this.scope.focus(); }
}''',
        "provides": "FocusRestore",
        "depends": [],
    },
    {
        "id": "acc-assist-label",
        "name": "Label from Text",
        "category": "acc",
        "lang": "typescript",
        "when": "Deriving an accessible name from an element's own text content",
        "why": "Atomic naming — first 120 chars of text, trims, control-safe",
        "tags": ["acc", "label", "accessible-name", "text"],
        "iface": r'''export function labelFromText(el: HTMLElement, max = 120): string''',
        "code": r'''export function labelFromText(el: HTMLElement, max = 120) {
  return (el.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, max);
}''',
        "provides": "labelFromText(el, max?)",
        "depends": [],
    },
    {
        "id": "acc-inert",
        "name": "Inert Toggle",
        "category": "acc",
        "lang": "typescript",
        "when": "Removing background content from the tab order and AT tree",
        "why": "Atomic inert wrapper — inert property with a fallback for older engines",
        "tags": ["acc", "inert", "modal", "background", "tab-order"],
        "iface": r'''export function setInert(el: HTMLElement, inert: boolean): void''',
        "code": r'''export function setInert(el: HTMLElement, inert: boolean) {
  if ('inert' in el) (el as HTMLElement & { inert: boolean }).inert = inert;
  else {
    if (inert) el.setAttribute('aria-hidden', 'true');
    else el.removeAttribute('aria-hidden');
  }
}''',
        "provides": "setInert(el, inert)",
        "depends": [],
    },
    {
        "id": "acc-announce",
        "name": "Announce Wrapper",
        "category": "acc",
        "lang": "typescript",
        "when": "Announcing a message with mode selection and cleanup",
        "why": "Atomic announce — one function creating/reusing a live region, auto-cleanup",
        "tags": ["acc", "announce", "live-region", "polite", "assertive"],
        "iface": r'''export function announce(text: string, mode: 'polite' | 'assertive' = 'polite'): void''',
        "code": r'''let region: HTMLElement | null = null;
export function announce(text: string, mode: 'polite' | 'assertive' = 'polite') {
  if (!region) {
    region = document.createElement('div');
    region.setAttribute('role', 'status');
    region.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);';
    document.body.appendChild(region);
  }
  region.setAttribute('aria-live', mode);
  region.textContent = '';
  requestAnimationFrame(() => { region!.textContent = text; });
}''',
        "provides": "announce(text, mode?)",
        "depends": [],
    },
]
