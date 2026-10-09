# -*- coding: utf-8 -*-
"""
Code Bible — Category 28: Time & Scheduling (atomic).
Convention: Date-based where stated, pure helpers, ms-based durations.
"""
CHUNKS = [
    {
        "id": "time-iso-week",
        "name": "ISO Week Number",
        "category": "time",
        "lang": "typescript",
        "when": "Computing the ISO 8601 week number and week-year for a date",
        "why": "Atomic ISO week calc — Thursday-anchored year, week 1..53",
        "tags": ["time", "iso", "week", "calendar", "date"],
        "iface": r'''export function isoWeek(date: Date): { week: number; year: number }''',
        "code": r'''export function isoWeek(date: Date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const diff = Math.floor((d.getTime() - firstThursday.getTime()) / 86400000);
  const week = 1 + Math.floor((diff + firstThursday.getUTCDay() + 6) / 7) - Math.floor((dayNum + 7) / 7);
  return { week, year: d.getUTCFullYear() };
}''',
        "provides": "isoWeek(date)",
        "depends": [],
    },
    {
        "id": "time-business-days",
        "name": "Business Day Calculator",
        "category": "time",
        "lang": "typescript",
        "when": "Adding N business days skipping weekends and optional holidays",
        "why": "Atomic business-day math — Mon-Fri + holiday set, returns a Date",
        "tags": ["time", "business", "workday", "calendar", "holiday"],
        "iface": r'''export function addBusinessDays(date: Date, days: number, holidays: Set<string> = new Set()): Date''',
        "code": r'''export function addBusinessDays(date: Date, days: number, holidays: Set<string> = new Set()) {
  const out = new Date(date);
  const key = (d: Date) => d.toISOString().slice(0, 10);
  let remaining = days;
  while (remaining > 0) {
    out.setDate(out.getDate() + 1);
    const dow = out.getDay();
    if (dow === 0 || dow === 6 || holidays.has(key(out))) continue;
    remaining--;
  }
  return out;
}''',
        "provides": "addBusinessDays(date, days, holidays?)",
        "depends": [],
    },
    {
        "id": "time-timezone-convert",
        "name": "Timezone Convert",
        "category": "time",
        "lang": "typescript",
        "when": "Converting a wall-clock time between named timezones (Intl)",
        "why": "Atomic Intl converter — parse in one zone, format in another",
        "tags": ["time", "timezone", "convert", "intl", "wall-clock"],
        "iface": r'''export function convertTime(iso: string, fromZone: string, toZone: string): string''',
        "code": r'''export function convertTime(iso: string, fromZone: string, toZone: string) {
  const dt = new Date(iso);
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: fromZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(dt);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '0';
  const asUTC = Date.UTC(+get('year'), +get('month') - 1, +get('day'), +get('hour') % 24, +get('minute'), +get('second'));
  return new Intl.DateTimeFormat('en-GB', { timeZone: toZone, dateStyle: 'short', timeStyle: 'medium' }).format(new Date(asUTC));
}''',
        "provides": "convertTime(iso, fromZone, toZone)",
        "depends": [],
    },
    {
        "id": "time-rrule",
        "name": "Recurring Event Matcher",
        "category": "time",
        "lang": "typescript",
        "when": "Matching dates against a small RRULE subset (daily/weekly/monthly)",
        "why": "Atomic recurrence test — freq + interval + weekdays, no full RFC 5545 parser",
        "tags": ["time", "recurrence", "rrule", "calendar", "schedule"],
        "iface": r'''export interface RecurRule { freq: 'daily' | 'weekly' | 'monthly'; interval?: number; weekdays?: number[] }
export function matchesRule(date: Date, anchor: Date, rule: RecurRule): boolean''',
        "code": r'''export function matchesRule(date: Date, anchor: Date, rule: RecurRule) {
  const interval = rule.interval ?? 1;
  const dayDiff = Math.round((new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime() - new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate()).getTime()) / 86400000);
  if (dayDiff < 0) return false;
  if (rule.freq === 'daily') return dayDiff % interval === 0;
  if (rule.freq === 'weekly') {
    if (dayDiff % (7 * interval) !== 0) return false;
    return rule.weekdays ? rule.weekdays.includes(date.getDay()) : true;
  }
  if (rule.freq === 'monthly') {
    const monthDiff = (date.getFullYear() - anchor.getFullYear()) * 12 + date.getMonth() - anchor.getMonth();
    return monthDiff % interval === 0 && date.getDate() === anchor.getDate();
  }
  return false;
}''',
        "provides": "matchesRule(date, anchor, rule)",
        "depends": [],
    },
    {
        "id": "time-duration-parse",
        "name": "ISO 8601 Duration Parser",
        "category": "time",
        "lang": "typescript",
        "when": "Parsing 'P1DT2H30M' style durations into milliseconds",
        "why": "Atomic ISO duration reader — P[y][m][d]T[h][m][s] segments in, ms out",
        "tags": ["time", "duration", "iso8601", "parse", "ms"],
        "iface": r'''export function parseIsoDuration(duration: string): number''',
        "code": r'''export function parseIsoDuration(duration: string) {
  const m = /^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$/.exec(duration);
  if (!m) throw new Error(`Invalid ISO 8601 duration: ${duration}`);
  const [y, mo, d, h, mi, s] = m.slice(1).map((x) => Number(x ?? 0));
  return (((((y * 365 + mo * 30 + d) * 24 + h) * 60 + mi) * 60 + s) * 1000);
}''',
        "provides": "parseIsoDuration(duration)",
        "depends": [],
    },
    {
        "id": "time-duration-human",
        "name": "Human Duration",
        "category": "time",
        "lang": "typescript",
        "when": "Formatting ms as '2h 14m 5s' for logs and status displays",
        "why": "Atomic humanizer — largest two units, plural-safe, handles sub-second",
        "tags": ["time", "duration", "human", "format", "ms"],
        "iface": r'''export function humanDuration(ms: number, units = 2): string''',
        "code": r'''export function humanDuration(ms: number, units = 2) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const parts: string[] = [];
  const chunks: Array<[number, string]> = [
    [86400000, 'd'], [3600000, 'h'], [60000, 'm'], [1000, 's'],
  ];
  let rest = ms;
  for (const [size, label] of chunks) {
    if (rest >= size) { parts.push(`${Math.floor(rest / size)}${label}`); rest %= size; }
  }
  return parts.slice(0, units).join(' ') || `${ms}ms`;
}''',
        "provides": "humanDuration(ms, units?)",
        "depends": [],
    },
    {
        "id": "time-date-range",
        "name": "Date Range Iterator",
        "category": "time",
        "lang": "typescript",
        "when": "Iterating day-by-day (or step-by-step) between two dates",
        "why": "Atomic range generator — inclusive, custom step in days, yields Dates",
        "tags": ["time", "range", "iterator", "days", "generate"],
        "iface": r'''export function* eachDay(from: Date, to: Date, stepDays = 1): Generator<Date>''',
        "code": r'''export function* eachDay(from: Date, to: Date, stepDays = 1) {
  const cur = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  const end = new Date(to.getFullYear(), to.getMonth(), to.getDate());
  while (cur <= end) { yield new Date(cur); cur.setDate(cur.getDate() + stepDays); }
}''',
        "provides": "eachDay(from, to, stepDays?)",
        "depends": [],
    },
    {
        "id": "time-dst-safe",
        "name": "DST-Safe Date Math",
        "category": "time",
        "lang": "typescript",
        "when": "Adding calendar days across DST boundaries without drift",
        "why": "Atomic calendar-day arithmetic — date-component based, immune to 23/25h days",
        "tags": ["time", "dst", "date-math", "calendar", "add-days"],
        "iface": r'''export function addCalendarDays(date: Date, days: number): Date''',
        "code": r'''export function addCalendarDays(date: Date, days: number) {
  const out = new Date(date);
  out.setDate(out.getDate() + days);
  return out;
}''',
        "provides": "addCalendarDays(date, days)",
        "depends": [],
    },
    {
        "id": "time-lap-stopwatch",
        "name": "Lap Stopwatch",
        "category": "time",
        "lang": "typescript",
        "when": "Measuring elapsed time with lap splits and total",
        "why": "Atomic stopwatch — start/pause/lap/reset, monotonic performance.now",
        "tags": ["time", "stopwatch", "lap", "timer", "measure"],
        "iface": r'''export class LapStopwatch {
  start(): void
  lap(): number
  pause(): number
  resume(): void
  get elapsedMs(): number
}''',
        "code": r'''export class LapStopwatch {
  private t0 = 0;
  private pausedMs = 0;
  private running = false;
  start() { this.t0 = performance.now(); this.pausedMs = 0; this.running = true; }
  private now() { return this.running ? performance.now() - this.t0 - this.pausedMs : this.pausedMs; }
  lap() { return this.now(); }
  pause() { if (this.running) { this.pausedMs = this.now(); this.running = false; } return this.pausedMs; }
  resume() { if (!this.running) { this.t0 = performance.now() - this.pausedMs; this.running = true; } }
  get elapsedMs() { return this.now(); }
}''',
        "provides": "LapStopwatch",
        "depends": [],
    },
    {
        "id": "time-interval-align",
        "name": "Interval Alignment",
        "category": "time",
        "lang": "typescript",
        "when": "Rounding a timestamp down to a grid (5-min buckets, hourly buckets)",
        "why": "Atomic bucket floor — timestamp + bucket ms in, aligned ts out",
        "tags": ["time", "interval", "align", "bucket", "round"],
        "iface": r'''export function alignToBucket(ts: number, bucketMs: number, offsetMs = 0): number''',
        "code": r'''export function alignToBucket(ts: number, bucketMs: number, offsetMs = 0) {
  if (bucketMs <= 0) return ts;
  return ts - ((ts - offsetMs) % bucketMs + bucketMs) % bucketMs;
}''',
        "provides": "alignToBucket(ts, bucketMs, offsetMs?)",
        "depends": [],
    },
    {
        "id": "time-frac-seconds",
        "name": "Fractional Seconds Format",
        "category": "time",
        "lang": "typescript",
        "when": "Formatting timestamps with sub-second precision for logs",
        "why": "Atomic ms precision formatter — ISO-like with 3-digit fraction",
        "tags": ["time", "fractional", "seconds", "format", "precision"],
        "iface": r'''export function formatWithMs(date: Date): string''',
        "code": r'''export function formatWithMs(date: Date) {
  const p = (n: number, l = 2) => String(n).padStart(l, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}.${p(date.getMilliseconds(), 3)}`;
}''',
        "provides": "formatWithMs(date)",
        "depends": [],
    },
    {
        "id": "time-age",
        "name": "Age Calculator",
        "category": "time",
        "lang": "typescript",
        "when": "Computing someone's age in full years from a birthdate",
        "why": "Atomic age — year diff with birthday-hasn't-passed correction",
        "tags": ["time", "age", "birthday", "years", "date"],
        "iface": r'''export function ageInYears(birthDate: Date, now: Date = new Date()): number''',
        "code": r'''export function ageInYears(birthDate: Date, now: Date = new Date()) {
  let age = now.getFullYear() - birthDate.getFullYear();
  const m = now.getMonth() - birthDate.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < birthDate.getDate())) age--;
  return Math.max(0, age);
}''',
        "provides": "ageInYears(birthDate, now?)",
        "depends": [],
    },
    {
        "id": "time-working-hours",
        "name": "Working Hours",
        "category": "time",
        "lang": "typescript",
        "when": "Checking whether a moment falls inside configured business hours",
        "why": "Atomic shift checker — start/end + weekday mask, DST-agnostic",
        "tags": ["time", "working-hours", "shift", "business", "check"],
        "iface": r'''export interface Shift { startHour: number; endHour: number; days: number[] }
export function inWorkingHours(date: Date, shift: Shift): boolean''',
        "code": r'''export function inWorkingHours(date: Date, shift: Shift) {
  if (!shift.days.includes(date.getDay())) return false;
  const h = date.getHours() + date.getMinutes() / 60;
  return h >= shift.startHour && h < shift.endHour;
}''',
        "provides": "inWorkingHours(date, shift)",
        "depends": [],
    },
    {
        "id": "time-monotonic",
        "name": "Monotonic Clock",
        "category": "time",
        "lang": "typescript",
        "when": "Measuring durations immune to system clock jumps",
        "why": "Atomic performance.now wrapper — epoch-agnostic elapsed-time source",
        "tags": ["time", "monotonic", "clock", "elapsed", "performance"],
        "iface": r'''export class MonotonicClock {
  now(): number
  elapsed(since: number): number
}''',
        "code": r'''export class MonotonicClock {
  now() { return performance.now(); }
  elapsed(since: number) { return this.now() - since; }
}''',
        "provides": "MonotonicClock",
        "depends": [],
    },
    {
        "id": "time-next-birthday",
        "name": "Next Birthday",
        "category": "time",
        "lang": "typescript",
        "when": "Finding the next occurrence of an annual date (handles Feb 29)",
        "why": "Atomic anniversary finder — rolls the year forward, clamps leap-day",
        "tags": ["time", "birthday", "anniversary", "next", "date"],
        "iface": r'''export function nextAnniversary(month: number, day: number, now: Date = new Date()): Date''',
        "code": r'''export function nextAnniversary(month: number, day: number, now: Date = new Date()) {
  let year = now.getFullYear();
  let candidate = new Date(year, month - 1, day);
  if (candidate.getDate() !== day) candidate = new Date(year, month - 1, 28); // Feb 29 -> Feb 28
  if (candidate < new Date(now.getFullYear(), now.getMonth(), now.getDate())) {
    year++;
    candidate = new Date(year, month - 1, day);
    if (candidate.getDate() !== day) candidate = new Date(year, month - 1, 28);
  }
  return candidate;
}''',
        "provides": "nextAnniversary(month, day, now?)",
        "depends": [],
    },
    {
        "id": "time-half-open",
        "name": "Half-Open Interval",
        "category": "time",
        "lang": "typescript",
        "when": "Testing whether a timestamp falls in [start, end) with overlap logic",
        "why": "Atomic interval math — contains, overlaps, merge for half-open ranges",
        "tags": ["time", "interval", "half-open", "overlap", "contains"],
        "iface": r'''export interface TimeSpan { start: number; end: number }
export function spansOverlap(a: TimeSpan, b: TimeSpan): boolean
export function spansContain(a: TimeSpan, ts: number): boolean''',
        "code": r'''export function spansOverlap(a: TimeSpan, b: TimeSpan) {
  return a.start < b.end && b.start < a.end;
}
export function spansContain(a: TimeSpan, ts: number) {
  return ts >= a.start && ts < a.end;
}''',
        "provides": "spansOverlap / spansContain",
        "depends": [],
    },
    {
        "id": "time-epoch",
        "name": "Epoch Converters",
        "category": "time",
        "lang": "typescript",
        "when": "Converting between Unix seconds, milliseconds, and Dates",
        "why": "Atomic unit bridge — sec/ms/date in each direction, no surprises",
        "tags": ["time", "epoch", "unix", "convert", "timestamp"],
        "iface": r'''export function toUnixSeconds(ms: number): number
export function toMs(unixSeconds: number): number
export function dateToUnixSeconds(d: Date): number''',
        "code": r'''export const toUnixSeconds = (ms: number) => Math.floor(ms / 1000);
export const toMs = (unixSeconds: number) => unixSeconds * 1000;
export const dateToUnixSeconds = (d: Date) => toUnixSeconds(d.getTime());''',
        "provides": "toUnixSeconds / toMs / dateToUnixSeconds",
        "depends": [],
    },
    {
        "id": "time-round-time",
        "name": "Round to Interval",
        "category": "time",
        "lang": "typescript",
        "when": "Rounding a time to the nearest 5/15/30-minute boundary",
        "why": "Atomic nearest-round — half up to bucket, returns new Date",
        "tags": ["time", "round", "interval", "minutes", "nearest"],
        "iface": r'''export function roundToNearest(date: Date, minutes: number): Date''',
        "code": r'''export function roundToNearest(date: Date, minutes: number) {
  const ms = minutes * 60000;
  const rounded = new Date(date);
  rounded.setTime(Math.round(date.getTime() / ms) * ms);
  return rounded;
}''',
        "provides": "roundToNearest(date, minutes)",
        "depends": [],
    },
    {
        "id": "time-first-last-day",
        "name": "First/Last Day of Month",
        "category": "time",
        "lang": "typescript",
        "when": "Computing month boundaries for calendar ranges",
        "why": "Atomic month math — first day + last day (with month rollover), zero-offset",
        "tags": ["time", "month", "first", "last", "boundary"],
        "iface": r'''export function firstDayOfMonth(date: Date): Date
export function lastDayOfMonth(date: Date): Date''',
        "code": r'''export function firstDayOfMonth(date: Date) { return new Date(date.getFullYear(), date.getMonth(), 1); }
export function lastDayOfMonth(date: Date) { return new Date(date.getFullYear(), date.getMonth() + 1, 0); }''',
        "provides": "firstDayOfMonth / lastDayOfMonth",
        "depends": [],
    },
    {
        "id": "time-leap-year",
        "name": "Leap Year + Days in Month",
        "category": "time",
        "lang": "typescript",
        "when": "Calendar arithmetic needing days-per-month or leap-year truth",
        "why": "Atomic calendar facts — 400/100/4 rule + month table with leap adjustment",
        "tags": ["time", "leap-year", "days-in-month", "calendar"],
        "iface": r'''export function isLeapYear(year: number): boolean
export function daysInMonth(year: number, month: number): number''',
        "code": r'''export function isLeapYear(year: number) { return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0); }
export function daysInMonth(year: number, month: number) {
  const table = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return table[month];
}''',
        "provides": "isLeapYear / daysInMonth",
        "depends": [],
    },
    {
        "id": "time-countdown-until",
        "name": "Countdown Until",
        "category": "time",
        "lang": "typescript",
        "when": "Computing remaining time to a target, optionally with a callback",
        "why": "Atomic countdown — remaining(ms) pure + ticker with interval and stop",
        "tags": ["time", "countdown", "timer", "remaining", "tick"],
        "iface": r'''export class Countdown {
  constructor(targetMs: number)
  remaining(): number
  start(onTick: (msLeft: number) => void, intervalMs?: number): void
  stop(): void
}''',
        "code": r'''export class Countdown {
  private timer: ReturnType<typeof setInterval> | null = null;
  constructor(private targetMs: number) {}
  remaining() { return Math.max(0, this.targetMs - Date.now()); }
  start(onTick: (msLeft: number) => void, intervalMs = 250) {
    this.stop();
    this.timer = setInterval(() => {
      const left = this.remaining();
      onTick(left);
      if (left <= 0) this.stop();
    }, intervalMs);
  }
  stop() { if (this.timer) { clearInterval(this.timer); this.timer = null; } }
}''',
        "provides": "Countdown",
        "depends": [],
    },
    {
        "id": "time-elapsed-format",
        "name": "Elapsed Format (ms -> human)",
        "category": "time",
        "lang": "typescript",
        "when": "Formatting an elapsed ms value for timers and logs",
        "why": "Atomic elapsed formatter — mm:ss and hh:mm:ss variants",
        "tags": ["time", "elapsed", "format", "mmss", "timer"],
        "iface": r'''export function formatElapsed(ms: number, includeHours = false): string''',
        "code": r'''export function formatElapsed(ms: number, includeHours = false) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const s = total % 60, m = Math.floor(total / 60) % 60, h = Math.floor(total / 3600);
  const p = (n: number) => String(n).padStart(2, '0');
  return includeHours ? `${p(h)}:${p(m)}:${p(s)}` : `${p(m)}:${p(s)}`;
}''',
        "provides": "formatElapsed(ms, includeHours?)",
        "depends": [],
    },
    {
        "id": "time-schedule-next",
        "name": "Next Scheduled Fire",
        "category": "time",
        "lang": "typescript",
        "when": "Computing the next fire time for a daily/weekly schedule from now",
        "why": "Atomic next-fire calc — daily at HH:MM or weekly on weekday, handles same-day-past",
        "tags": ["time", "schedule", "next", "fire", "cron"],
        "iface": r'''export interface Schedule { hour: number; minute: number; weekdays?: number[] }
export function nextFire(schedule: Schedule, now: Date = new Date()): Date''',
        "code": r'''export function nextFire(schedule: Schedule, now: Date = new Date()) {
  const candidate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), schedule.hour, schedule.minute, 0, 0);
  if (candidate.getTime() <= now.getTime()) candidate.setDate(candidate.getDate() + 1);
  const days = schedule.weekdays;
  if (days && days.length) {
    while (!days.includes(candidate.getDay())) candidate.setDate(candidate.getDate() + 1);
  }
  return candidate;
}''',
        "provides": "nextFire(schedule, now?)",
        "depends": [],
    },
    {
        "id": "time-utc-offset",
        "name": "UTC Offset by TZ Name",
        "category": "time",
        "lang": "typescript",
        "when": "Getting the current UTC offset (minutes) for a named timezone",
        "why": "Atomic Intl offset probe — formatToParts trick, DST-aware at a given moment",
        "tags": ["time", "utc", "offset", "timezone", "dst"],
        "iface": r'''export function utcOffsetMinutes(timeZone: string, at: Date = new Date()): number''',
        "code": r'''export function utcOffsetMinutes(timeZone: string, at: Date = new Date()) {
  const dtf = new Intl.DateTimeFormat('en-US', { timeZone, hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const parts = dtf.formatToParts(at);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '0';
  const asUTC = Date.UTC(+get('year'), +get('month') - 1, +get('day'), +get('hour') % 24, +get('minute'), +get('second'));
  return Math.round((asUTC - at.getTime()) / 60000);
}''',
        "provides": "utcOffsetMinutes(timeZone, at?)",
        "depends": [],
    },
    {
        "id": "time-quarter",
        "name": "Fiscal Quarter",
        "category": "time",
        "lang": "typescript",
        "when": "Computing the quarter and year label for a date",
        "why": "Atomic quarter \u2014 date in, 'Q3 2026' style out; fiscal offset option",
        "tags": [
            "time",
            "quarter",
            "fiscal",
            "year",
            "date"
        ],
        "iface": "export function quarterOf(date: Date, fiscalOffsetMonths = 0): { quarter: number; year: number; label: string }",
        "code": "export function quarterOf(date: Date, fiscalOffsetMonths = 0) {\n  const d = new Date(date);\n  d.setMonth(d.getMonth() - fiscalOffsetMonths);\n  const quarter = Math.floor(d.getMonth() / 3) + 1;\n  return { quarter, year: d.getFullYear(), label: `Q${quarter} ${d.getFullYear()}` };\n}",
        "provides": "quarterOf(date, fiscalOffsetMonths)",
        "depends": []
    },
]
