# -*- coding: utf-8 -*-
"""
Code Bible — Category 01: UI components (atomic, single-responsibility).
Convention: every chunk exports ONE component `<Name>(props: <Name>Props)`.
Callbacks are `on<Event>`; values flow in as props, events flow out via callbacks.
"""
CHUNKS = [
    {
        "id": "ui-login-form",
        "name": "Login Form",
        "category": "ui",
        "lang": "typescript",
        "when": "Building an authentication screen that collects email + password and submits credentials",
        "why": "Atomic login UI with built-in validation; emits onSubmit(LoginInput) so auth logic stays in a separate chunk",
        "tags": ["login", "auth", "form", "email", "password", "authentication"],
        "iface": r'''export interface LoginInput { email: string; password: string }
export interface LoginFormProps {
  onSubmit: (input: LoginInput) => void | Promise<void>;
  busy?: boolean;
  error?: string | null;
}''',
        "code": r'''import { useState } from 'react';

export function LoginForm(props: LoginFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.includes('@') || password.length < 6) return;
    void props.onSubmit({ email, password });
  }

  return (
    <form onSubmit={handleSubmit}>
      <input type="email" value={email} placeholder="you@example.com"
        onChange={(e) => setEmail(e.target.value)} aria-label="Email" />
      <input type="password" value={password} placeholder="Password"
        onChange={(e) => setPassword(e.target.value)} aria-label="Password" />
      {props.error && <p className="form-error" role="alert">{props.error}</p>}
      <button type="submit" disabled={props.busy || !email || !password}>
        {props.busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  );
}''',
        "provides": "LoginForm(props: LoginFormProps)",
        "depends": [],
    },
    {
        "id": "ui-signup-form",
        "name": "Sign-Up Form",
        "category": "ui",
        "lang": "typescript",
        "when": "Building a registration screen that validates name/email/password before creating an account",
        "why": "Atomic signup UI with field-level validation; emits onSubmit(SignupInput) and never talks to a backend itself",
        "tags": ["signup", "registration", "form", "validation", "auth"],
        "iface": r'''export interface SignupInput { name: string; email: string; password: string }
export interface SignupFormProps {
  onSubmit: (input: SignupInput) => void | Promise<void>;
  busy?: boolean;
  error?: string | null;
}''',
        "code": r'''import { useState } from 'react';

export function SignupForm(props: SignupFormProps) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const valid =
    name.trim().length >= 2 &&
    email.includes('@') &&
    password.length >= 8;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;
    void props.onSubmit({ name: name.trim(), email, password });
  }

  return (
    <form onSubmit={handleSubmit}>
      <input value={name} placeholder="Full name" onChange={(e) => setName(e.target.value)} aria-label="Name" />
      <input type="email" value={email} placeholder="you@example.com" onChange={(e) => setEmail(e.target.value)} aria-label="Email" />
      <input type="password" value={password} placeholder="Min 8 characters" onChange={(e) => setPassword(e.target.value)} aria-label="Password" />
      {props.error && <p role="alert">{props.error}</p>}
      <button type="submit" disabled={props.busy || !valid}>
        {props.busy ? 'Creating account…' : 'Create account'}
      </button>
    </form>
  );
}''',
        "provides": "SignupForm(props: SignupFormProps)",
        "depends": [],
    },
    {
        "id": "ui-todo-item",
        "name": "Todo Item",
        "category": "ui",
        "lang": "typescript",
        "when": "Rendering one task row in a todo/checklist app with toggle and delete actions",
        "why": "Atomic todo row; emits onToggle/onDelete so list state lives in a separate store chunk",
        "tags": ["todo", "task", "list", "checkbox", "item"],
        "iface": r'''export interface TodoItemData { id: string; title: string; done: boolean }
export interface TodoItemProps {
  item: TodoItemData;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}''',
        "code": r'''export function TodoItem(props: TodoItemProps) {
  const { item } = props;
  return (
    <li className={'todo-item' + (item.done ? ' done' : '')}>
      <input
        type="checkbox"
        checked={item.done}
        onChange={() => props.onToggle(item.id)}
        aria-label={'Mark ' + item.title + (item.done ? ' not done' : ' done')}
      />
      <span className="todo-title">{item.title}</span>
      <button type="button" onClick={() => props.onDelete(item.id)} aria-label={'Delete ' + item.title}>×</button>
    </li>
  );
}''',
        "provides": "TodoItem(props: TodoItemProps)",
        "depends": [],
    },
    {
        "id": "ui-kanban-card",
        "name": "Kanban Card",
        "category": "ui",
        "lang": "typescript",
        "when": "Rendering a draggable card inside a kanban/trello-style board column",
        "why": "Atomic card that renders content and reports drag intent via onDragStart/onDragEnd; board logic stays separate",
        "tags": ["kanban", "board", "card", "drag", "agile"],
        "iface": r'''export interface KanbanCardData { id: string; title: string; tags?: string[] }
export interface KanbanCardProps {
  card: KanbanCardData;
  onDragStart: (cardId: string) => void;
  onDragEnd: () => void;
}''',
        "code": r'''export function KanbanCard(props: KanbanCardProps) {
  const { card } = props;
  return (
    <div
      className="kanban-card"
      draggable
      onDragStart={() => props.onDragStart(card.id)}
      onDragEnd={() => props.onDragEnd()}
    >
      <span className="kanban-card-title">{card.title}</span>
      {card.tags && (
        <div className="kanban-card-tags">
          {card.tags.map((t) => (
            <span className="kanban-tag" key={t}>{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}''',
        "provides": "KanbanCard(props: KanbanCardProps)",
        "depends": [],
    },
    {
        "id": "ui-modal-dialog",
        "name": "Modal Dialog",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing a focused dialog (confirm, settings, form) over the page with a backdrop and Escape-to-close",
        "why": "Atomic overlay; owns focus trap + escape handling and emits onClose, so any content can be a child",
        "tags": ["modal", "dialog", "overlay", "popup", "focus"],
        "iface": r'''export interface ModalDialogProps {
  open: boolean;
  title?: string;
  children: React.ReactNode;
  onClose: () => void;
  width?: number;
}''',
        "code": r'''import { useEffect, useRef } from 'react';

export function ModalDialog(props: ModalDialogProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!props.open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') props.onClose(); };
    document.addEventListener('keydown', onKey);
    ref.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [props.open, props.onClose]);

  if (!props.open) return null;

  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div
        ref={ref}
        className="modal-dialog"
        style={props.width ? { width: props.width } : undefined}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        {props.title && <h2 className="modal-title">{props.title}</h2>}
        <div className="modal-body">{props.children}</div>
        <button className="modal-close" onClick={props.onClose} aria-label="Close">×</button>
      </div>
    </div>
  );
}''',
        "provides": "ModalDialog(props: ModalDialogProps)",
        "depends": [],
    },
    {
        "id": "ui-toast-notification",
        "name": "Toast Notification",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing transient success/error/info messages that auto-dismiss",
        "why": "Atomic toast with auto-dismiss + manual close; emits onDismiss so a parent toast-bus owns the queue",
        "tags": ["toast", "notification", "snackbar", "message"],
        "iface": r'''export interface ToastData { id: string; kind: 'success' | 'error' | 'info'; message: string }
export interface ToastNotificationProps {
  toast: ToastData;
  onDismiss: (id: string) => void;
  durationMs?: number;
}''',
        "code": r'''import { useEffect } from 'react';

export function ToastNotification(props: ToastNotificationProps) {
  const { toast, durationMs = 4000 } = props;

  useEffect(() => {
    const t = setTimeout(() => props.onDismiss(toast.id), durationMs);
    return () => clearTimeout(t);
  }, [toast.id, durationMs, props.onDismiss]);

  return (
    <div className={`toast toast-${toast.kind}`} role="status">
      <span className="toast-message">{toast.message}</span>
      <button type="button" onClick={() => props.onDismiss(toast.id)} aria-label="Dismiss">×</button>
    </div>
  );
}''',
        "provides": "ToastNotification(props: ToastNotificationProps)",
        "depends": [],
    },
    {
        "id": "ui-dropdown-menu",
        "name": "Dropdown Menu",
        "category": "ui",
        "lang": "typescript",
        "when": "Selecting one option from a collapsible list (sort, filter, actions)",
        "why": "Atomic dropdown: options in, onSelect out; owns open/close + outside-click, so data never leaks in",
        "tags": ["dropdown", "select", "menu", "options"],
        "iface": r'''export interface DropdownOption<T extends string = string> { value: T; label: string }
export interface DropdownMenuProps<T extends string> {
  options: DropdownOption<T>[];
  value: T;
  onSelect: (value: T) => void;
  placeholder?: string;
}''',
        "code": r'''import { useEffect, useRef, useState } from 'react';

export function DropdownMenu<T extends string>(props: DropdownMenuProps<T>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const selected = props.options.find((o) => o.value === props.value);

  return (
    <div className="dropdown" ref={ref}>
      <button type="button" className="dropdown-trigger" onClick={() => setOpen((v) => !v)}>
        {selected ? selected.label : (props.placeholder ?? 'Select…')}
      </button>
      {open && (
        <ul className="dropdown-menu" role="listbox">
          {props.options.map((o) => (
            <li key={o.value}>
              <button
                type="button"
                role="option"
                aria-selected={o.value === props.value}
                className={o.value === props.value ? 'active' : ''}
                onClick={() => { props.onSelect(o.value); setOpen(false); }}
              >
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}''',
        "provides": "DropdownMenu<T>(props: DropdownMenuProps<T>)",
        "depends": [],
    },
    {
        "id": "ui-tab-bar",
        "name": "Tab Bar",
        "category": "ui",
        "lang": "typescript",
        "when": "Switching between sibling views (settings, profile, dashboard sections)",
        "why": "Atomic tab strip; active tab in, onSelect out — the panel rendering belongs to the parent",
        "tags": ["tabs", "navigation", "panel", "view"],
        "iface": r'''export interface TabItem { id: string; label: string; icon?: string }
export interface TabBarProps {
  tabs: TabItem[];
  activeId: string;
  onSelect: (id: string) => void;
}''',
        "code": r'''export function TabBar(props: TabBarProps) {
  return (
    <div className="tab-bar" role="tablist">
      {props.tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={t.id === props.activeId}
          className={t.id === props.activeId ? 'tab active' : 'tab'}
          onClick={() => props.onSelect(t.id)}
        >
          {t.icon && <span className="tab-icon">{t.icon}</span>}
          {t.label}
        </button>
      ))}
    </div>
  );
}''',
        "provides": "TabBar(props: TabBarProps)",
        "depends": [],
    },
    {
        "id": "ui-data-table",
        "name": "Data Table",
        "category": "ui",
        "lang": "typescript",
        "when": "Rendering structured rows/columns (logs, users, inventory) with optional sorting",
        "why": "Atomic table: columns + rows in, onSort out; the table owns only layout, never data fetching",
        "tags": ["table", "grid", "rows", "columns", "sort"],
        "iface": r'''export interface TableColumn<K extends string> { key: K; header: string; width?: number }
export interface DataTableProps<T, K extends string = Extract<keyof T, string>> {
  columns: TableColumn<K>[];
  rows: T[];
  sortKey?: K;
  sortDir?: 'asc' | 'desc';
  onSort?: (key: K) => void;
}''',
        "code": r'''export function DataTable<T extends Record<string, unknown>, K extends string = Extract<keyof T, string>>(
  props: DataTableProps<T, K>,
) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          {props.columns.map((c) => (
            <th key={c.key} style={c.width ? { width: c.width } : undefined}>
              {props.onSort ? (
                <button type="button" className="th-sort" onClick={() => props.onSort!(c.key)}>
                  {c.header}
                  {props.sortKey === c.key ? (props.sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </button>
              ) : (
                c.header
              )}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {props.rows.map((row, i) => (
          <tr key={i}>
            {props.columns.map((c) => (
              <td key={c.key}>{String(row[c.key] ?? '')}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}''',
        "provides": "DataTable<T, K>(props: DataTableProps<T, K>)",
        "depends": [],
    },
    {
        "id": "ui-pagination-bar",
        "name": "Pagination Bar",
        "category": "ui",
        "lang": "typescript",
        "when": "Navigating a paged list of results (search, tables, feeds)",
        "why": "Atomic pager; page/pageSize/total in, onPageChange out — the query layer is separate",
        "tags": ["pagination", "pager", "pages", "navigation"],
        "iface": r'''export interface PaginationBarProps {
  page: number;          // 0-based
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}''',
        "code": r'''export function PaginationBar(props: PaginationBarProps) {
  const totalPages = Math.max(1, Math.ceil(props.total / props.pageSize));
  if (totalPages <= 1) return null;

  function btn(p: number, label: string, opts: { disabled?: boolean; active?: boolean } = {}) {
    return (
      <button
        type="button"
        key={label + p}
        disabled={opts.disabled}
        className={opts.active ? 'page active' : 'page'}
        onClick={() => props.onPageChange(p)}
      >
        {label}
      </button>
    );
  }

  const pages: React.ReactNode[] = [];
  for (let p = 0; p < totalPages; p++) {
    if (totalPages > 7 && p > 1 && p < totalPages - 2 && Math.abs(p - props.page) > 1) {
      if (pages[pages.length - 1] !== '…') pages.push('…');
      continue;
    }
    pages.push(btn(p, String(p + 1), { active: p === props.page }));
  }

  return (
    <nav className="pagination" aria-label="Pagination">
      {btn(props.page - 1, '‹', { disabled: props.page === 0 })}
      {pages}
      {btn(props.page + 1, '›', { disabled: props.page >= totalPages - 1 })}
    </nav>
  );
}''',
        "provides": "PaginationBar(props: PaginationBarProps)",
        "depends": [],
    },
    {
        "id": "ui-search-input",
        "name": "Search Input",
        "category": "ui",
        "lang": "typescript",
        "when": "Capturing a free-text search query with debounced change events",
        "why": "Atomic search field: query in, onQueryChange out (debounced by parent or hook); no fetching inside",
        "tags": ["search", "input", "query", "filter"],
        "iface": r'''export interface SearchInputProps {
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  debounceMs?: number;
  autoFocus?: boolean;
}''',
        "code": r'''import { useEffect, useRef, useState } from 'react';

export function SearchInput(props: SearchInputProps) {
  const [text, setText] = useState(props.value);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => setText(props.value), [props.value]);

  function handleChange(v: string) {
    setText(v);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => props.onValueChange(v), props.debounceMs ?? 300);
  }

  return (
    <input
      type="search"
      className="search-input"
      value={text}
      placeholder={props.placeholder ?? 'Search…'}
      autoFocus={props.autoFocus}
      onChange={(e) => handleChange(e.target.value)}
      aria-label="Search"
    />
  );
}''',
        "provides": "SearchInput(props: SearchInputProps)",
        "depends": [],
    },
    {
        "id": "ui-slider-input",
        "name": "Slider Input",
        "category": "ui",
        "lang": "typescript",
        "when": "Choosing a numeric value in a range (volume, speed, zoom)",
        "why": "Atomic slider; min/max/value in, onValueChange out, with a live readout",
        "tags": ["slider", "range", "input", "number"],
        "iface": r'''export interface SliderInputProps {
  value: number;
  min: number;
  max: number;
  step?: number;
  label?: string;
  onValueChange: (value: number) => void;
}''',
        "code": r'''export function SliderInput(props: SliderInputProps) {
  return (
    <label className="slider-input">
      {props.label && <span className="slider-label">{props.label}</span>}
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step ?? 1}
        value={props.value}
        onChange={(e) => props.onValueChange(Number(e.target.value))}
      />
      <output className="slider-value">{props.value}</output>
    </label>
  );
}''',
        "provides": "SliderInput(props: SliderInputProps)",
        "depends": [],
    },
    {
        "id": "ui-toggle-switch",
        "name": "Toggle Switch",
        "category": "ui",
        "lang": "typescript",
        "when": "Binary on/off setting (notifications, dark mode, auto-save)",
        "why": "Atomic switch; checked in, onChange out, accessible via real checkbox semantics",
        "tags": ["toggle", "switch", "checkbox", "boolean", "settings"],
        "iface": r'''export interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
}''',
        "code": r'''export function ToggleSwitch(props: ToggleSwitchProps) {
  return (
    <label className={'toggle-switch' + (props.checked ? ' on' : '')}>
      <input
        type="checkbox"
        checked={props.checked}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
      {props.label && <span className="toggle-label">{props.label}</span>}
    </label>
  );
}''',
        "provides": "ToggleSwitch(props: ToggleSwitchProps)",
        "depends": [],
    },
    {
        "id": "ui-progress-bar",
        "name": "Progress Bar",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing progress of a task (upload, install, generation) as 0-100%",
        "why": "Atomic progress indicator; value in, renders fill + optional label; no async logic inside",
        "tags": ["progress", "percent", "loading", "bar"],
        "iface": r'''export interface ProgressBarProps {
  value: number;         // 0..100
  label?: string;
  indeterminate?: boolean;
  showPercent?: boolean;
}''',
        "code": r'''export function ProgressBar(props: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, props.value));
  return (
    <div className="progress" role="progressbar" aria-valuenow={props.indeterminate ? undefined : clamped}
      aria-valuemin={0} aria-valuemax={100}>
      {props.label && <span className="progress-label">{props.label}</span>}
      <div className="progress-track">
        <div
          className={props.indeterminate ? 'progress-fill indeterminate' : 'progress-fill'}
          style={props.indeterminate ? undefined : { width: `${clamped}%` }}
        />
      </div>
      {props.showPercent && !props.indeterminate && <span className="progress-percent">{Math.round(clamped)}%</span>}
    </div>
  );
}''',
        "provides": "ProgressBar(props: ProgressBarProps)",
        "depends": [],
    },
    {
        "id": "ui-accordion",
        "name": "Accordion",
        "category": "ui",
        "lang": "typescript",
        "when": "Collapsing sections of content (FAQ, settings groups, docs)",
        "why": "Atomic expand/collapse group; one open item at a time, state owned by parent via openId",
        "tags": ["accordion", "collapse", "expand", "faq", "sections"],
        "iface": r'''export interface AccordionSection { id: string; title: string; content: React.ReactNode }
export interface AccordionProps {
  sections: AccordionSection[];
  openId: string | null;
  onToggle: (id: string) => void;
}''',
        "code": r'''export function Accordion(props: AccordionProps) {
  return (
    <div className="accordion">
      {props.sections.map((s) => {
        const open = props.openId === s.id;
        return (
          <div className={'accordion-section' + (open ? ' open' : '')} key={s.id}>
            <button type="button" className="accordion-header" onClick={() => props.onToggle(s.id)}
              aria-expanded={open}>
              <span>{s.title}</span>
              <span className="accordion-chevron">{open ? '▾' : '▸'}</span>
            </button>
            {open && <div className="accordion-body">{s.content}</div>}
          </div>
        );
      })}
    </div>
  );
}''',
        "provides": "Accordion(props: AccordionProps)",
        "depends": [],
    },
    {
        "id": "ui-tooltip",
        "name": "Tooltip",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing a short hint on hover/focus for icons and buttons",
        "why": "Atomic tooltip wrapper; only positions + shows the label, content is a child",
        "tags": ["tooltip", "hover", "hint", "popover"],
        "iface": r'''export interface TooltipProps {
  label: string;
  children: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
}''',
        "code": r'''import { useState } from 'react';

export function Tooltip(props: TooltipProps) {
  const [show, setShow] = useState(false);
  return (
    <span
      className="tooltip-wrap"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      {props.children}
      {show && <span className={`tooltip tooltip-${props.position ?? 'top'}`} role="tooltip">{props.label}</span>}
    </span>
  );
}''',
        "provides": "Tooltip(props: TooltipProps)",
        "depends": [],
    },
    {
        "id": "ui-badge",
        "name": "Badge",
        "category": "ui",
        "lang": "typescript",
        "when": "Labeling status or counts (Unread 3, Beta, Success)",
        "why": "Atomic status pill; text + kind in, zero logic",
        "tags": ["badge", "pill", "tag", "status", "label"],
        "iface": r'''export interface BadgeProps {
  text: string;
  kind?: 'neutral' | 'success' | 'warning' | 'danger' | 'info';
  dot?: boolean;
}''',
        "code": r'''export function Badge(props: BadgeProps) {
  return (
    <span className={`badge badge-${props.kind ?? 'neutral'}`}>
      {props.dot && <span className="badge-dot" aria-hidden="true" />}
      {props.text}
    </span>
  );
}''',
        "provides": "Badge(props: BadgeProps)",
        "depends": [],
    },
    {
        "id": "ui-color-picker",
        "name": "Color Picker",
        "category": "ui",
        "lang": "typescript",
        "when": "Choosing a color for themes, painting tools, or data-viz series",
        "why": "Atomic color input; hex value in, onValueChange out, renders swatch + native picker",
        "tags": ["color", "picker", "palette", "input"],
        "iface": r'''export interface ColorPickerProps {
  value: string;         // hex like #ff8800
  onValueChange: (hex: string) => void;
  label?: string;
}''',
        "code": r'''export function ColorPicker(props: ColorPickerProps) {
  return (
    <label className="color-picker">
      {props.label && <span className="color-label">{props.label}</span>}
      <span className="color-swatch" style={{ background: props.value }}>
        <input
          type="color"
          value={props.value}
          onChange={(e) => props.onValueChange(e.target.value)}
          aria-label={props.label ?? 'Pick color'}
        />
      </span>
      <input
        className="color-hex"
        value={props.value}
        onChange={(e) => props.onValueChange(e.target.value)}
        aria-label="Hex value"
      />
    </label>
  );
}''',
        "provides": "ColorPicker(props: ColorPickerProps)",
        "depends": [],
    },
    {
        "id": "ui-file-dropzone",
        "name": "File Dropzone",
        "category": "ui",
        "lang": "typescript",
        "when": "Accepting drag-and-drop file uploads (images, docs, archives)",
        "why": "Atomic dropzone; emits File[] via onFilesSelected, handles drag state — upload itself is a separate chunk",
        "tags": ["file", "upload", "dropzone", "drag", "dragdrop"],
        "iface": r'''export interface FileDropzoneProps {
  accept?: string;       // mime or ext filter, e.g. "image/*"
  multiple?: boolean;
  onFilesSelected: (files: File[]) => void;
  label?: string;
}''',
        "code": r'''import { useRef, useState } from 'react';

export function FileDropzone(props: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function acceptFiles(list: FileList | null) {
    if (!list) return;
    const files = Array.from(list);
    const picked = props.accept
      ? files.filter((f) => f.type.match(props.accept!) || f.name.match(new RegExp(props.accept!.replace('*', '.*'))))
      : files;
    props.onFilesSelected(props.multiple ? picked : picked.slice(0, 1));
  }

  return (
    <div
      className={'dropzone' + (dragging ? ' dragging' : '')}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); acceptFiles(e.dataTransfer.files); }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click(); }}
    >
      <input ref={inputRef} type="file" hidden accept={props.accept}
        multiple={props.multiple} onChange={(e) => acceptFiles(e.target.files)} />
      <p>{dragging ? 'Drop files here' : (props.label ?? 'Drag & drop files, or click to browse')}</p>
    </div>
  );
}''',
        "provides": "FileDropzone(props: FileDropzoneProps)",
        "depends": [],
    },
    {
        "id": "ui-calendar-grid",
        "name": "Calendar Grid",
        "category": "ui",
        "lang": "typescript",
        "when": "Rendering a month view for date picking or event calendars",
        "why": "Atomic month grid; year/month/selected in, onSelectDate out — scheduling logic stays separate",
        "tags": ["calendar", "date", "month", "grid", "picker"],
        "iface": r'''export interface CalendarGridProps {
  year: number;
  month: number;         // 0-based
  selected?: string;     // ISO yyyy-mm-dd
  onSelectDate: (iso: string) => void;
}''',
        "code": r'''export function CalendarGrid(props: CalendarGridProps) {
  const { year, month } = props;
  const first = new Date(year, month, 1);
  const startPad = (first.getDay() + 6) % 7;          // Monday-first
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const cells: React.ReactNode[] = [];
  for (let p = 0; p < startPad; p++) cells.push(<td key={'pad' + p} />);
  for (let d = 1; d <= daysInMonth; d++) {
    const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push(
      <td key={iso}>
        <button
          type="button"
          className={iso === props.selected ? 'cal-day selected' : 'cal-day'}
          onClick={() => props.onSelectDate(iso)}
        >
          {d}
        </button>
      </td>,
    );
  }
  while (cells.length % 7 !== 0) cells.push(<td key={'pad' + cells.length} />);

  const rows: React.ReactNode[] = [];
  for (let i = 0; i < cells.length; i += 7) rows.push(<tr key={i}>{cells.slice(i, i + 7)}</tr>);

  return (
    <table className="calendar-grid">
      <thead>
        <tr>{['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].map((d) => <th key={d}>{d}</th>)}</tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  );
}''',
        "provides": "CalendarGrid(props: CalendarGridProps)",
        "depends": [],
    },
    {
        "id": "ui-timeline",
        "name": "Timeline",
        "category": "ui",
        "lang": "typescript",
        "when": "Displaying an ordered sequence of events (activity feed, history, build steps)",
        "why": "Atomic vertical timeline; items in, renders markers + content, no time math inside",
        "tags": ["timeline", "history", "events", "feed", "activity"],
        "iface": r'''export interface TimelineItemData { id: string; title: string; time?: string; detail?: string; kind?: 'default' | 'success' | 'danger' }
export interface TimelineProps {
  items: TimelineItemData[];
}''',
        "code": r'''export function Timeline(props: TimelineProps) {
  return (
    <ol className="timeline">
      {props.items.map((it) => (
        <li className="timeline-item" key={it.id}>
          <span className={`timeline-marker timeline-${it.kind ?? 'default'}`} aria-hidden="true" />
          <div className="timeline-content">
            <div className="timeline-head">
              <span className="timeline-title">{it.title}</span>
              {it.time && <span className="timeline-time">{it.time}</span>}
            </div>
            {it.detail && <p className="timeline-detail">{it.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}''',
        "provides": "Timeline(props: TimelineProps)",
        "depends": [],
    },
    {
        "id": "ui-chart-line",
        "name": "Line Chart",
        "category": "ui",
        "lang": "typescript",
        "when": "Plotting a numeric series over time (metrics, prices, progress)",
        "why": "Atomic SVG line chart; points + dimensions in, renders path/grid/axis — no data shaping inside",
        "tags": ["chart", "line", "plot", "graph", "svg", "visualization"],
        "iface": r'''export interface ChartPoint { x: number; y: number }
export interface LineChartProps {
  points: ChartPoint[];
  width?: number;
  height?: number;
  color?: string;
}''',
        "code": r'''export function LineChart(props: LineChartProps) {
  const w = props.width ?? 480;
  const h = props.height ?? 240;
  const { points } = props;

  if (points.length === 0) return <svg className="line-chart" width={w} height={h} />;

  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const pad = 8;
  const sx = (v: number) => pad + ((v - minX) / (maxX - minX || 1)) * (w - pad * 2);
  const sy = (v: number) => h - pad - ((v - minY) / (maxY - minY || 1)) * (h - pad * 2);

  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(' ');

  return (
    <svg className="line-chart" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Line chart">
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#888" />
      <line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke="#888" />
      <path d={d} fill="none" stroke={props.color ?? '#4f8ef7'} strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={3} fill={props.color ?? '#4f8ef7'} />
      ))}
    </svg>
  );
}''',
        "provides": "LineChart(props: LineChartProps)",
        "depends": [],
    },
    {
        "id": "ui-chart-bar",
        "name": "Bar Chart",
        "category": "ui",
        "lang": "typescript",
        "when": "Comparing discrete categories (usage by day, top products)",
        "why": "Atomic SVG bar chart; category/value pairs in, renders bars + baseline",
        "tags": ["chart", "bar", "histogram", "visualization"],
        "iface": r'''export interface BarDatum { label: string; value: number }
export interface BarChartProps {
  data: BarDatum[];
  width?: number;
  height?: number;
  color?: string;
}''',
        "code": r'''export function BarChart(props: BarChartProps) {
  const w = props.width ?? 480;
  const h = props.height ?? 240;
  const max = Math.max(1, ...props.data.map((d) => d.value));
  const bw = w / Math.max(1, props.data.length);

  return (
    <svg className="bar-chart" width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Bar chart">
      <line x1={0} y1={h - 20} x2={w} y2={h - 20} stroke="#888" />
      {props.data.map((d, i) => {
        const bh = ((d.value / max) * (h - 30));
        const x = i * bw + bw * 0.15;
        return (
          <g key={i}>
            <rect x={x} y={h - 20 - bh} width={bw * 0.7} height={bh}
              fill={props.color ?? '#4f8ef7'} rx={2} />
            <text x={i * bw + bw / 2} y={h - 6} textAnchor="middle" fontSize={10} fill="#666">
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}''',
        "provides": "BarChart(props: BarChartProps)",
        "depends": [],
    },
    {
        "id": "ui-chart-pie",
        "name": "Pie / Donut Chart",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing proportion of a whole (budget split, traffic sources)",
        "why": "Atomic SVG pie; slices in, renders arcs + percentage labels",
        "tags": ["chart", "pie", "donut", "proportion", "visualization"],
        "iface": r'''export interface PieSlice { label: string; value: number; color: string }
export interface PieChartProps {
  data: PieSlice[];
  size?: number;
  donut?: boolean;
}''',
        "code": r'''export function PieChart(props: PieChartProps) {
  const size = props.size ?? 200;
  const r = size / 2 - 6;
  const total = props.data.reduce((s, d) => s + d.value, 0) || 1;
  let angle = -Math.PI / 2;

  function arc(cx: number, cy: number, a0: number, a1: number): string {
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    if (props.donut) {
      const ir = r * 0.6;
      const ix0 = cx + ir * Math.cos(a0), iy0 = cy + ir * Math.sin(a0);
      const ix1 = cx + ir * Math.cos(a1), iy1 = cy + ir * Math.sin(a1);
      return `M${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} L${ix1},${iy1} A${ir},${ir} 0 ${large} 0 ${ix0},${iy0} Z`;
    }
    return `M${cx},${cy} L${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} Z`;
  }

  return (
    <svg className="pie-chart" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Pie chart">
      {props.data.map((d, i) => {
        const sweep = (d.value / total) * Math.PI * 2;
        const a1 = angle + sweep;
        const path = arc(size / 2, size / 2, angle, a1);
        angle = a1;
        return <path key={i} d={path} fill={d.color} stroke="#fff" strokeWidth={1} />;
      })}
    </svg>
  );
}''',
        "provides": "PieChart(props: PieChartProps)",
        "depends": [],
    },
    {
        "id": "ui-markdown-renderer",
        "name": "Markdown Renderer",
        "category": "ui",
        "lang": "typescript",
        "when": "Rendering user-generated markdown (docs, notes, chat) as safe HTML",
        "why": "Atomic renderer: markdown in, sanitized HTML out; owns parsing + sanitization only",
        "tags": ["markdown", "renderer", "html", "docs", "content"],
        "iface": r'''export interface MarkdownRendererProps {
  markdown: string;
  className?: string;
}''',
        "code": r'''// Minimal safe renderer: escapes HTML then applies a small inline/heading subset.
export function MarkdownRenderer(props: MarkdownRendererProps) {
  const html = renderSafeMarkdown(props.markdown);
  return <div className={props.className ?? 'markdown-body'} dangerouslySetInnerHTML={{ __html: html }} />;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function renderSafeMarkdown(md: string): string {
  const lines = md.split('\n');
  const out: string[] = [];
  for (const raw of lines) {
    const line = escapeHtml(raw.trim());
    if (line.startsWith('### ')) out.push(`<h3>${line.slice(4)}</h3>`);
    else if (line.startsWith('## ')) out.push(`<h2>${line.slice(3)}</h2>`);
    else if (line.startsWith('# ')) out.push(`<h1>${line.slice(2)}</h1>`);
    else if (line.startsWith('- ')) out.push(`<li>${line.slice(2)}</li>`);
    else if (line.startsWith('`'.repeat(3))) out.push('<pre><code>');
    else if (line === '') out.push('');
    else out.push(`<p>${line.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>')}</p>`);
  }
  return out.join('\n');
}''',
        "provides": "MarkdownRenderer(props), renderSafeMarkdown(md)",
        "depends": [],
    },
    {
        "id": "ui-code-editor",
        "name": "Code Editor Shell",
        "category": "ui",
        "lang": "typescript",
        "when": "Embedding a textarea-based code editor with line numbers and tab handling",
        "why": "Atomic editor shell: value in, onValueChange out, syntax highlighting belongs to a separate chunk",
        "tags": ["editor", "code", "textarea", "monospace"],
        "iface": r'''export interface CodeEditorProps {
  value: string;
  onValueChange: (value: string) => void;
  language?: string;
  readOnly?: boolean;
  rows?: number;
}''',
        "code": r'''export function CodeEditor(props: CodeEditorProps) {
  const lines = props.value.split('\n').length;
  return (
    <div className="code-editor" data-lang={props.language}>
      <div className="code-gutter" aria-hidden="true">
        {Array.from({ length: Math.max(lines, props.rows ?? 10) }, (_, i) => (
          <span key={i}>{i + 1}</span>
        ))}
      </div>
      <textarea
        className="code-input"
        value={props.value}
        readOnly={props.readOnly}
        spellCheck={false}
        rows={props.rows ?? 10}
        onChange={(e) => props.onValueChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Tab') {
            e.preventDefault();
            const el = e.currentTarget;
            const { selectionStart: s, selectionEnd: end, value } = el;
            const next = value.slice(0, s) + '  ' + value.slice(end);
            props.onValueChange(next);
            requestAnimationFrame(() => el.setSelectionRange(s + 2, s + 2));
          }
        }}
      />
    </div>
  );
}''',
        "provides": "CodeEditor(props: CodeEditorProps)",
        "depends": [],
    },
    {
        "id": "ui-avatar",
        "name": "Avatar",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing a user/entity image with initials fallback and size variants",
        "why": "Atomic avatar; name/url/size in, renders image → initials fallback, zero logic",
        "tags": ["avatar", "profile", "image", "user"],
        "iface": r'''export interface AvatarProps {
  name: string;
  src?: string;
  size?: number;
  onClick?: () => void;
}''',
        "code": r'''import { useState } from 'react';

export function Avatar(props: AvatarProps) {
  const [failed, setFailed] = useState(false);
  const size = props.size ?? 40;
  const initials = props.name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase();

  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
      onClick={props.onClick}
      role={props.onClick ? 'button' : undefined}
    >
      {props.src && !failed ? (
        <img src={props.src} alt={props.name} onError={() => setFailed(true)} />
      ) : (
        <span className="avatar-initials">{initials}</span>
      )}
    </span>
  );
}''',
        "provides": "Avatar(props: AvatarProps)",
        "depends": [],
    },
    {
        "id": "ui-drag-drop-list",
        "name": "Drag & Drop Reorder List",
        "category": "ui",
        "lang": "typescript",
        "when": "Reordering items by dragging (playlists, priorities, layers)",
        "why": "Atomic reorder list: items in, onReorder(newOrder) out; uses pointer events + DOM measurement only",
        "tags": ["drag", "drop", "reorder", "list", "sort"],
        "iface": r'''export interface DragDropListProps<T extends { id: string }> {
  items: T[];
  renderItem: (item: T) => React.ReactNode;
  onReorder: (orderedIds: string[]) => void;
}''',
        "code": r'''import { useRef, useState } from 'react';

export function DragDropList<T extends { id: string }>(props: DragDropListProps<T>) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  function move(from: string, to: string) {
    const ids = props.items.map((i) => i.id);
    const fromIdx = ids.indexOf(from);
    const toIdx = ids.indexOf(to);
    if (fromIdx < 0 || toIdx < 0 || fromIdx === toIdx) return;
    ids.splice(fromIdx, 1);
    ids.splice(toIdx, 0, from);
    props.onReorder(ids);
  }

  return (
    <ul className="drag-list">
      {props.items.map((item) => (
        <li
          key={item.id}
          className={'drag-item' + (dragId === item.id ? ' dragging' : '') + (overId === item.id ? ' over' : '')}
          draggable
          onDragStart={() => setDragId(item.id)}
          onDragEnd={() => { setDragId(null); setOverId(null); }}
          onDragOver={(e) => { e.preventDefault(); setOverId(item.id); }}
          onDrop={(e) => { e.preventDefault(); if (dragId) move(dragId, item.id); }}
        >
          {props.renderItem(item)}
        </li>
      ))}
    </ul>
  );
}''',
        "provides": "DragDropList<T>(props: DragDropListProps<T>)",
        "depends": [],
    },
    {
        "id": "ui-infinite-scroll",
        "name": "Infinite Scroll Sentinel",
        "category": "ui",
        "lang": "typescript",
        "when": "Loading more items when the user scrolls near the bottom of a feed",
        "why": "Atomic sentinel: IntersectionObserver in, onReachEnd out — fetching/rendering belong to the parent",
        "tags": ["infinite", "scroll", "feed", "lazy", "intersection"],
        "iface": r'''export interface InfiniteScrollProps {
  onReachEnd: () => void;
  enabled?: boolean;
  rootMargin?: string;
  children: React.ReactNode;
}''',
        "code": r'''import { useEffect, useRef } from 'react';

export function InfiniteScroll(props: InfiniteScrollProps) {
  const sentinel = useRef<HTMLDivElement>(null);
  const cbRef = useRef(props.onReachEnd);
  cbRef.current = props.onReachEnd;

  useEffect(() => {
    const el = sentinel.current;
    if (!el || props.enabled === false) return;
    const obs = new IntersectionObserver(
      (entries) => { if (entries.some((e) => e.isIntersecting)) cbRef.current(); },
      { rootMargin: props.rootMargin ?? '200px' },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [props.enabled, props.rootMargin]);

  return (
    <div className="infinite-scroll">
      {props.children}
      <div ref={sentinel} className="infinite-sentinel" aria-hidden="true" />
    </div>
  );
}''',
        "provides": "InfiniteScroll(props: InfiniteScrollProps)",
        "depends": [],
    },
    {
        "id": "ui-context-menu",
        "name": "Context Menu",
        "category": "ui",
        "lang": "typescript",
        "when": "Right-click actions on items (copy, rename, delete, share)",
        "why": "Atomic context menu; coordinates + items in, onAction out, closes on outside click",
        "tags": ["context", "menu", "rightclick", "actions"],
        "iface": r'''export interface ContextMenuItem { id: string; label: string; danger?: boolean }
export interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onAction: (itemId: string) => void;
  onClose: () => void;
}''',
        "code": r'''import { useEffect } from 'react';

export function ContextMenu(props: ContextMenuProps) {
  useEffect(() => {
    const close = () => props.onClose();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [props.onClose]);

  return (
    <ul className="context-menu" style={{ left: props.x, top: props.y }} role="menu"
      onMouseDown={(e) => e.stopPropagation()}>
      {props.items.map((it) => (
        <li key={it.id} role="none">
          <button type="button" role="menuitem"
            className={it.danger ? 'context-item danger' : 'context-item'}
            onClick={() => { props.onAction(it.id); props.onClose(); }}>
            {it.label}
          </button>
        </li>
      ))}
    </ul>
  );
}''',
        "provides": "ContextMenu(props: ContextMenuProps)",
        "depends": [],
    },
    {
        "id": "ui-carousel",
        "name": "Carousel",
        "category": "ui",
        "lang": "typescript",
        "when": "Cycling through images/cards with arrows, dots, and auto-advance",
        "why": "Atomic carousel; slides in, index controlled by parent via onIndexChange",
        "tags": ["carousel", "slideshow", "gallery", "slider"],
        "iface": r'''export interface CarouselProps {
  slides: React.ReactNode[];
  index: number;
  onIndexChange: (index: number) => void;
  autoAdvanceMs?: number;
}''',
        "code": r'''import { useEffect } from 'react';

export function Carousel(props: CarouselProps) {
  const count = props.slides.length;
  const go = (i: number) => props.onIndexChange(((i % count) + count) % count);

  useEffect(() => {
    if (!props.autoAdvanceMs || count <= 1) return;
    const t = setInterval(() => go(props.index + 1), props.autoAdvanceMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.autoAdvanceMs, props.index, count]);

  if (count === 0) return null;

  return (
    <div className="carousel">
      <div className="carousel-viewport" style={{ transform: `translateX(-${props.index * 100}%)` }}>
        {props.slides.map((s, i) => (
          <div className="carousel-slide" key={i}>{s}</div>
        ))}
      </div>
      <button type="button" className="carousel-prev" onClick={() => go(props.index - 1)} aria-label="Previous">‹</button>
      <button type="button" className="carousel-next" onClick={() => go(props.index + 1)} aria-label="Next">›</button>
      <div className="carousel-dots">
        {props.slides.map((_, i) => (
          <button key={i} type="button" className={i === props.index ? 'dot active' : 'dot'}
            onClick={() => props.onIndexChange(i)} aria-label={`Go to slide ${i + 1}`} />
        ))}
      </div>
    </div>
  );
}''',
        "provides": "Carousel(props: CarouselProps)",
        "depends": [],
    },
    {
        "id": "ui-form-builder",
        "name": "Form Builder",
        "category": "ui",
        "lang": "typescript",
        "when": "Rendering a dynamic form from a declarative field schema",
        "why": "Atomic schema-driven form; field config in, values + validation errors out — submission handled by parent",
        "tags": ["form", "builder", "schema", "fields", "dynamic"],
        "iface": r'''export type FieldKind = 'text' | 'email' | 'number' | 'select' | 'checkbox' | 'textarea';
export interface FieldConfig {
  name: string;
  label: string;
  kind: FieldKind;
  required?: boolean;
  options?: Array<{ value: string; label: string }>;
  placeholder?: string;
}
export interface FormBuilderProps {
  fields: FieldConfig[];
  values: Record<string, string | boolean>;
  onValuesChange: (values: Record<string, string | boolean>) => void;
}''',
        "code": r'''export function FormBuilder(props: FormBuilderProps) {
  function set(name: string, value: string | boolean) {
    props.onValuesChange({ ...props.values, [name]: value });
  }

  return (
    <div className="form-builder">
      {props.fields.map((f) => (
        <label className="field" key={f.name}>
          <span className="field-label">
            {f.label}{f.required ? ' *' : ''}
          </span>
          {f.kind === 'select' ? (
            <select value={String(props.values[f.name] ?? '')} onChange={(e) => set(f.name, e.target.value)}>
              <option value="">—</option>
              {(f.options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          ) : f.kind === 'checkbox' ? (
            <input type="checkbox" checked={Boolean(props.values[f.name])}
              onChange={(e) => set(f.name, e.target.checked)} />
          ) : f.kind === 'textarea' ? (
            <textarea value={String(props.values[f.name] ?? '')}
              placeholder={f.placeholder} onChange={(e) => set(f.name, e.target.value)} />
          ) : (
            <input type={f.kind} value={String(props.values[f.name] ?? '')}
              placeholder={f.placeholder} onChange={(e) => set(f.name, e.target.value)} />
          )}
        </label>
      ))}
    </div>
  );
}''',
        "provides": "FormBuilder(props: FormBuilderProps)",
        "depends": [],
    },
    {
        "id": "ui-breadcrumb",
        "name": "Breadcrumb",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing the current location path in nested navigation",
        "why": "Atomic breadcrumb; path segments in, onNavigate out",
        "tags": ["breadcrumb", "navigation", "path", "trail"],
        "iface": r'''export interface BreadcrumbItem { id: string; label: string }
export interface BreadcrumbProps {
  items: BreadcrumbItem[];
  onNavigate: (id: string) => void;
}''',
        "code": r'''export function Breadcrumb(props: BreadcrumbProps) {
  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      {props.items.map((it, i) => (
        <span className="crumb" key={it.id}>
          {i < props.items.length - 1 ? (
            <button type="button" className="crumb-link" onClick={() => props.onNavigate(it.id)}>
              {it.label}
            </button>
          ) : (
            <span className="crumb-current" aria-current="page">{it.label}</span>
          )}
          {i < props.items.length - 1 && <span className="crumb-sep">/</span>}
        </span>
      ))}
    </nav>
  );
}''',
        "provides": "Breadcrumb(props: BreadcrumbProps)",
        "depends": [],
    },
    {
        "id": "ui-empty-state",
        "name": "Empty State",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing a friendly placeholder when a list/result is empty",
        "why": "Atomic empty-state; icon/text/action in, renders guidance, zero logic",
        "tags": ["empty", "state", "placeholder", "no results"],
        "iface": r'''export interface EmptyStateProps {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: string;
}''',
        "code": r'''export function EmptyState(props: EmptyStateProps) {
  return (
    <div className="empty-state">
      {props.icon && <div className="empty-icon" aria-hidden="true">{props.icon}</div>}
      <h3 className="empty-title">{props.title}</h3>
      {props.description && <p className="empty-desc">{props.description}</p>}
      {props.actionLabel && props.onAction && (
        <button type="button" className="empty-action" onClick={props.onAction}>{props.actionLabel}</button>
      )}
    </div>
  );
}''',
        "provides": "EmptyState(props: EmptyStateProps)",
        "depends": [],
    },
    {
        "id": "ui-loading-spinner",
        "name": "Loading Spinner",
        "category": "ui",
        "lang": "typescript",
        "when": "Indicating in-flight work without blocking layout",
        "why": "Atomic spinner; size/label in, pure CSS animation",
        "tags": ["loading", "spinner", "loader", "skeleton"],
        "iface": r'''export interface LoadingSpinnerProps {
  size?: number;
  label?: string;
}''',
        "code": r'''export function LoadingSpinner(props: LoadingSpinnerProps) {
  const size = props.size ?? 24;
  return (
    <div className="loading" role="status" aria-live="polite">
      <span
        className="spinner"
        style={{ width: size, height: size, borderWidth: Math.max(2, size / 8) }}
        aria-hidden="true"
      />
      {props.label && <span className="loading-label">{props.label}</span>}
    </div>
  );
}''',
        "provides": "LoadingSpinner(props: LoadingSpinnerProps)",
        "depends": [],
    },
    {
        "id": "ui-stat-card",
        "name": "Stat Card",
        "category": "ui",
        "lang": "typescript",
        "when": "Showing a KPI with value, label, and trend in dashboards",
        "why": "Atomic metric tile; value/trend in, renders formatted number + delta arrow",
        "tags": ["stat", "kpi", "metric", "dashboard", "card"],
        "iface": r'''export interface StatCardProps {
  label: string;
  value: number;
  format?: (v: number) => string;
  trendPct?: number;     // + or - percent vs previous
  icon?: string;
}''',
        "code": r'''export function StatCard(props: StatCardProps) {
  const fmt = props.format ?? ((v: number) => v.toLocaleString());
  const trend = props.trendPct;
  return (
    <div className="stat-card">
      <div className="stat-head">
        <span className="stat-label">{props.label}</span>
        {props.icon && <span className="stat-icon" aria-hidden="true">{props.icon}</span>}
      </div>
      <div className="stat-value">{fmt(props.value)}</div>
      {trend !== undefined && (
        <div className={trend >= 0 ? 'stat-trend up' : 'stat-trend down'}>
          {trend >= 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(1)}%
        </div>
      )}
    </div>
  );
}''',
        "provides": "StatCard(props: StatCardProps)",
        "depends": [],
    },
]
