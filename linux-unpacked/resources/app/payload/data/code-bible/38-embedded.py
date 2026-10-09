# -*- coding: utf-8 -*-
"""
Code Bible — Category 38: Embedded & Systems (atomic).
Convention: bitwise/byte helpers, memory-safe, no deps.
"""
CHUNKS = [
    {
        "id": "embed-bitfield",
        "name": "Bitfield Read/Write",
        "category": "embed",
        "lang": "typescript",
        "when": "Packing and unpacking named bits in a register value",
        "why": "Atomic field ops — mask + shift in, get/set out; no overflow",
        "tags": ["embed", "bitfield", "register", "mask", "bits"],
        "iface": r'''export interface BitField { offset: number; width: number }
export function fieldGet(value: number, field: BitField): number
export function fieldSet(value: number, field: BitField, raw: number): number''',
        "code": r'''export function fieldGet(value: number, field: BitField) {
  const mask = (1 << field.width) - 1;
  return (value >>> field.offset) & mask;
}
export function fieldSet(value: number, field: BitField, raw: number) {
  const mask = (1 << field.width) - 1;
  return (value & ~(mask << field.offset)) | ((raw & mask) << field.offset);
}''',
        "provides": "fieldGet / fieldSet",
        "depends": [],
    },
    {
        "id": "embed-byte-ops",
        "name": "Byte Pack/Unpack",
        "category": "embed",
        "lang": "typescript",
        "when": "Serializing integers into byte arrays (BE/LE)",
        "why": "Atomic pack — number + width + endian in, Uint8Array out; and back",
        "tags": ["embed", "byte", "pack", "endian", "binary"],
        "iface": r'''export function packInt(value: number, width: 1 | 2 | 4, littleEndian = false): Uint8Array
export function unpackInt(bytes: Uint8Array, offset: number, width: 1 | 2 | 4, littleEndian = false): number''',
        "code": r'''export function packInt(value: number, width: 1 | 2 | 4, littleEndian = false) {
  const out = new Uint8Array(width);
  for (let i = 0; i < width; i++) {
    const shift = littleEndian ? i * 8 : (width - 1 - i) * 8;
    out[i] = (value >>> shift) & 0xff;
  }
  return out;
}
export function unpackInt(bytes: Uint8Array, offset: number, width: 1 | 2 | 4, littleEndian = false) {
  let v = 0;
  for (let i = 0; i < width; i++) {
    const b = bytes[offset + (littleEndian ? i : width - 1 - i)];
    v = (v << 8) | b;
  }
  return v;
}''',
        "provides": "packInt / unpackInt",
        "depends": [],
    },
    {
        "id": "embed-crc8",
        "name": "CRC-8 Check",
        "category": "embed",
        "lang": "typescript",
        "when": "Computing a lightweight integrity byte for a packet",
        "why": "Atomic CRC-8 — polynomial 0x07 table-less bit loop, no deps",
        "tags": ["embed", "crc8", "checksum", "integrity", "packet"],
        "iface": r'''export function crc8(data: Uint8Array, poly = 0x07): number''',
        "code": r'''export function crc8(data: Uint8Array, poly = 0x07) {
  let crc = 0;
  for (const b of data) {
    crc ^= b;
    for (let i = 0; i < 8; i++) crc = crc & 0x80 ? ((crc << 1) ^ poly) & 0xff : (crc << 1) & 0xff;
  }
  return crc;
}''',
        "provides": "crc8(data, poly)",
        "depends": [],
    },
    {
        "id": "embed-leb128",
        "name": "LEB128 Encode/Decode",
        "category": "embed",
        "lang": "typescript",
        "when": "Variable-length encoding of integers (protocol/streams)",
        "why": "Atomic LEB128 — unsigned encode + decode, stream-friendly",
        "tags": ["embed", "leb128", "varint", "encode", "stream"],
        "iface": r'''export function encodeLeb128(value: number): number[]
export function decodeLeb128(bytes: number[] | Uint8Array, offset = 0): { value: number; next: number }''',
        "code": r'''export function encodeLeb128(value: number) {
  const out: number[] = [];
  let v = value >>> 0;
  do {
    let b = v & 0x7f;
    v >>>= 7;
    if (v) b |= 0x80;
    out.push(b);
  } while (v);
  return out;
}
export function decodeLeb128(bytes: number[] | Uint8Array, offset = 0) {
  let value = 0, shift = 0, i = offset;
  while (i < bytes.length) {
    const b = bytes[i++];
    value |= (b & 0x7f) << shift;
    if (!(b & 0x80)) break;
    shift += 7;
    if (shift > 28) break;
  }
  return { value: value >>> 0, next: i };
}''',
        "provides": "encodeLeb128 / decodeLeb128",
        "depends": [],
    },
    {
        "id": "embed-ring-buffer",
        "name": "Ring Buffer",
        "category": "embed",
        "lang": "typescript",
        "when": "Bounded FIFO for streaming bytes/samples without GC churn",
        "why": "Atomic ring — fixed capacity, overwrite policy, size + fill access",
        "tags": ["embed", "ring", "buffer", "fifo", "bounded"],
        "iface": r'''export class RingBuffer<T> {
  constructor(capacity: number)
  push(item: T): void
  pop(): T | undefined
  get size(): number
  toArray(): T[]
}''',
        "code": r'''export class RingBuffer<T> {
  private buf: Array<T | undefined>;
  private head = 0; private tail = 0; private count = 0;
  constructor(private capacity: number) { this.buf = new Array(capacity); }
  push(item: T) {
    if (this.count === this.capacity) { this.head = (this.head + 1) % this.capacity; this.count--; }
    this.buf[this.tail] = item;
    this.tail = (this.tail + 1) % this.capacity;
    this.count++;
  }
  pop() {
    if (!this.count) return undefined;
    const v = this.buf[this.head];
    this.head = (this.head + 1) % this.capacity;
    this.count--;
    return v;
  }
  get size() { return this.count; }
  toArray() {
    const out: T[] = [];
    for (let i = 0; i < this.count; i++) out.push(this.buf[(this.head + i) % this.capacity] as T);
    return out;
  }
}''',
        "provides": "RingBuffer",
        "depends": [],
    },
    {
        "id": "embed-debounce",
        "name": "Debounce",
        "category": "embed",
        "lang": "typescript",
        "when": "Collapsing rapid sensor/button events into one trailing call",
        "why": "Atomic debounce — fn + delay in, wrapped fn out; no timers API",
        "tags": ["embed", "debounce", "button", "events", "delay"],
        "iface": r'''export function debounce<T extends unknown[]>(fn: (...args: T) => void, delayMs: number): { (...args: T): void; cancel(): void }''',
        "code": r'''export function debounce<T extends unknown[]>(fn: (...args: T) => void, delayMs: number) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const wrapped = (...args: T) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = null; fn(...args); }, delayMs);
  };
  wrapped.cancel = () => { if (timer) { clearTimeout(timer); timer = null; } };
  return wrapped;
}''',
        "provides": "debounce(fn, delayMs)",
        "depends": [],
    },
    {
        "id": "embed-throttle",
        "name": "Throttle",
        "category": "embed",
        "lang": "typescript",
        "when": "Limiting event handling to at most once per interval",
        "why": "Atomic throttle — leading-edge call, drops the rest, no deps",
        "tags": ["embed", "throttle", "rate", "events", "interval"],
        "iface": r'''export function throttle<T extends unknown[]>(fn: (...args: T) => void, intervalMs: number): (...args: T) => void''',
        "code": r'''export function throttle<T extends unknown[]>(fn: (...args: T) => void, intervalMs: number) {
  let last = 0;
  return (...args: T) => {
    const now = Date.now();
    if (now - last >= intervalMs) { last = now; fn(...args); }
  };
}''',
        "provides": "throttle(fn, intervalMs)",
        "depends": [],
    },
    {
        "id": "embed-avg-filter",
        "name": "Moving Average Filter",
        "category": "embed",
        "lang": "typescript",
        "when": "Smoothing noisy ADC samples in a sliding window",
        "why": "Atomic filter — sample in, windowed mean out; O(1) via running sum",
        "tags": ["embed", "average", "filter", "smooth", "adc"],
        "iface": r'''export class MovingAverage {
  constructor(window: number)
  push(sample: number): number
}''',
        "code": r'''export class MovingAverage {
  private buf: number[] = [];
  private sum = 0;
  constructor(private window: number) {}
  push(sample: number) {
    this.buf.push(sample);
    this.sum += sample;
    if (this.buf.length > this.window) this.sum -= this.buf.shift()!;
    return this.sum / this.buf.length;
  }
}''',
        "provides": "MovingAverage",
        "depends": [],
    },
    {
        "id": "embed-hex-dump",
        "name": "Hex Dump",
        "category": "embed",
        "lang": "typescript",
        "when": "Rendering raw bytes as a debug hex/ascii table",
        "why": "Atomic dump — bytes in, offset | hex | ascii lines out",
        "tags": ["embed", "hex", "dump", "debug", "bytes"],
        "iface": r'''export function hexDump(bytes: Uint8Array, bytesPerLine = 16): string''',
        "code": r'''export function hexDump(bytes: Uint8Array, bytesPerLine = 16) {
  const lines: string[] = [];
  for (let off = 0; off < bytes.length; off += bytesPerLine) {
    const chunk = bytes.slice(off, off + bytesPerLine);
    const hex = [...chunk].map((b) => b.toString(16).padStart(2, '0')).join(' ');
    const ascii = [...chunk].map((b) => (b >= 32 && b < 127 ? String.fromCharCode(b) : '.')).join('');
    lines.push(`${off.toString(16).padStart(8, '0')}  ${hex.padEnd(bytesPerLine * 3 - 1)}  ${ascii}`);
  }
  return lines.join('\n');
}''',
        "provides": "hexDump(bytes, bytesPerLine)",
        "depends": [],
    },
    {
        "id": "embed-uptime",
        "name": "Uptime Formatter",
        "category": "embed",
        "lang": "typescript",
        "when": "Formatting milliseconds since boot as d/h/m/s",
        "why": "Atomic formatter — ms in, compact duration string out",
        "tags": ["embed", "uptime", "duration", "format", "time"],
        "iface": r'''export function formatUptime(ms: number): string''',
        "code": r'''export function formatUptime(ms: number) {
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const parts: string[] = [];
  if (d) parts.push(`${d}d`);
  if (h) parts.push(`${h}h`);
  if (m) parts.push(`${m}m`);
  if (!d) parts.push(`${sec}s`);
  return parts.join(' ') || '0s';
}''',
        "provides": "formatUptime(ms)",
        "depends": [],
    },
    {
        "id": "embed-gpio-sim",
        "name": "GPIO Pin Simulator",
        "category": "embed",
        "lang": "typescript",
        "when": "Simulating pin states with input pullup and edges",
        "why": "Atomic pin — read/write, rising/falling edge detection",
        "tags": ["embed", "gpio", "pin", "simulate", "edge"],
        "iface": r'''export class Pin {
  constructor(private output: boolean)
  write(high: boolean): void
  read(): boolean
  edge(): 'rising' | 'falling' | null
}''',
        "code": r'''export class Pin {
  private value: boolean;
  private last: boolean | null = null;
  constructor(private output: boolean) { this.value = false; }
  write(high: boolean) { this.last = this.value; this.value = high; }
  read() { return this.value; }
  edge() {
    if (this.last === null) { this.last = this.value; return null; }
    const e = this.value && !this.last ? 'rising' : !this.value && this.last ? 'falling' : null;
    this.last = this.value;
    return e;
  }
}''',
        "provides": "Pin",
        "depends": [],
    },
    {
        "id": "embed-state-machine",
        "name": "State Machine",
        "category": "embed",
        "lang": "typescript",
        "when": "Running event-driven device logic as a table-driven FSM",
        "why": "Atomic FSM — transition table + events in, state + handlers out",
        "tags": ["embed", "state", "machine", "fsm", "transition"],
        "iface": r'''export class StateMachine<S extends string, E extends string> {
  constructor(initial: S, transitions: Record<S, Partial<Record<E, S>>>)
  send(event: E): S
  get state(): S
}''',
        "code": r'''export class StateMachine<S extends string, E extends string> {
  private current: S;
  constructor(initial: S, private transitions: Record<S, Partial<Record<E, S>>>) { this.current = initial; }
  send(event: E) {
    const next = this.transitions[this.current]?.[event];
    if (next) this.current = next;
    return this.current;
  }
  get state() { return this.current; }
}''',
        "provides": "StateMachine",
        "depends": [],
    },
    {
        "id": "embed-sample-hold",
        "name": "Sample & Hold",
        "category": "embed",
        "lang": "typescript",
        "when": "Capturing the latest sensor reading between reads",
        "why": "Atomic sampler — write in, last-read value out; read clears dirty flag",
        "tags": ["embed", "sample", "hold", "sensor", "read"],
        "iface": r'''export class SampleHold<T> {
  sample(value: T): void
  read(): { value: T | undefined; fresh: boolean }
}''',
        "code": r'''export class SampleHold<T> {
  private stored: T | undefined;
  private dirty = false;
  sample(value: T) { this.stored = value; this.dirty = true; }
  read() { const fresh = this.dirty; this.dirty = false; return { value: this.stored, fresh }; }
}''',
        "provides": "SampleHold",
        "depends": [],
    },
    {
        "id": "embed-frame-codec",
        "name": "Frame Codec (SOF + len + payload)",
        "category": "embed",
        "lang": "typescript",
        "when": "Framing bytes for serial transport with a start marker",
        "why": "Atomic codec — wrap adds SOF+len, unwrap validates and returns payloads",
        "tags": ["embed", "frame", "codec", "serial", "protocol"],
        "iface": r'''export function frame(payload: Uint8Array, sof = 0xaa): Uint8Array
export function unframe(stream: number[]): { frames: Uint8Array[]; rest: number[] }''',
        "code": r'''export function frame(payload: Uint8Array, sof = 0xaa) {
  const out = new Uint8Array(2 + payload.length);
  out[0] = sof; out[1] = payload.length;
  out.set(payload, 2);
  return out;
}
export function unframe(stream: number[]) {
  const frames: Uint8Array[] = [];
  let i = 0;
  while (i + 1 < stream.length) {
    if (stream[i] === 0xaa) {
      const len = stream[i + 1];
      if (i + 2 + len <= stream.length) {
        frames.push(Uint8Array.from(stream.slice(i + 2, i + 2 + len)));
        i += 2 + len;
        continue;
      }
    }
    i++;
  }
  return { frames, rest: stream.slice(i) };
}''',
        "provides": "frame / unframe",
        "depends": [],
    },
    {
        "id": "embed-timer-wheel",
        "name": "Timer Wheel",
        "category": "embed",
        "lang": "typescript",
        "when": "Scheduling many low-resolution timeouts efficiently",
        "why": "Atomic wheel — tick() advances, expiring callbacks fire in order",
        "tags": ["embed", "timer", "wheel", "schedule", "tick"],
        "iface": r'''export class TimerWheel {
  constructor(slots: number, slotMs: number)
  after(delayMs: number, cb: () => void): void
  tick(): void
}''',
        "code": r'''export class TimerWheel {
  private slots: Array<Array<{ remaining: number; cb: () => void }>>;
  private cursor = 0;
  private elapsed = 0;
  constructor(slots: number, private slotMs: number) { this.slots = Array.from({ length: slots }, () => []); }
  after(delayMs: number, cb: () => void) {
    const ticks = Math.ceil(delayMs / this.slotMs);
    const idx = (this.cursor + ticks) % this.slots.length;
    this.slots[idx].push({ remaining: ticks, cb });
  }
  tick() {
    this.elapsed++;
    const due = this.slots[this.cursor];
    this.slots[this.cursor] = [];
    for (const t of due) t.cb();
    this.cursor = (this.cursor + 1) % this.slots.length;
  }
}''',
        "provides": "TimerWheel",
        "depends": [],
    },
    {
        "id": "embed-pwm",
        "name": "PWM Duty Cycle",
        "category": "embed",
        "lang": "typescript",
        "when": "Computing on/off timing for a PWM signal at a duty %",
        "why": "Atomic math — period + duty in, on/off µs out; clamped 0-100",
        "tags": ["embed", "pwm", "duty", "cycle", "timing"],
        "iface": r'''export function pwmTiming(periodUs: number, dutyPercent: number): { onUs: number; offUs: number }''',
        "code": r'''export function pwmTiming(periodUs: number, dutyPercent: number) {
  const d = Math.max(0, Math.min(100, dutyPercent)) / 100;
  const onUs = periodUs * d;
  return { onUs, offUs: periodUs - onUs };
}''',
        "provides": "pwmTiming(periodUs, dutyPercent)",
        "depends": [],
    },
    {
        "id": "embed-vector-scale",
        "name": "Sensor Vector Scale",
        "category": "embed",
        "lang": "typescript",
        "when": "Scaling raw ADC/IMU counts to engineering units",
        "why": "Atomic scale — raw + gain + offset in, calibrated value out",
        "tags": ["embed", "sensor", "scale", "calibrate", "adc"],
        "iface": r'''export function sensorScale(raw: number, gain: number, offset = 0): number''',
        "code": r'''export function sensorScale(raw: number, gain: number, offset = 0) {
  return raw * gain + offset;
}''',
        "provides": "sensorScale(raw, gain, offset)",
        "depends": [],
    },
    {
        "id": "embed-boot-check",
        "name": "Boot Self-Test",
        "category": "embed",
        "lang": "typescript",
        "when": "Running startup checks and collecting pass/fail flags",
        "why": "Atomic test runner — named checks in, summary with failures out",
        "tags": ["embed", "boot", "self-test", "check", "diagnostic"],
        "iface": "export interface BootResult { checks: Array<{ name: string; ok: boolean }>; ok: boolean }",
        "code": r'''export interface BootCheck { name: string; run: () => boolean }
export function bootSelfTest(checks: BootCheck[]): BootResult {
  const results = checks.map((c) => ({ name: c.name, ok: c.run() }));
  return { checks: results, ok: results.every((r) => r.ok) };
}''',
        "provides": "bootSelfTest(checks)",
        "depends": [],
    },
    {
        "id": "embed-bit-crc16",
        "name": "CRC-16/CCITT",
        "category": "embed",
        "lang": "typescript",
        "when": "Computing a stronger 16-bit frame checksum",
        "why": "Atomic CRC-16 — poly 0x1021, initial 0xffff, no table required",
        "tags": ["embed", "crc16", "ccitt", "checksum", "frame"],
        "iface": r'''export function crc16(data: Uint8Array, poly = 0x1021): number''',
        "code": r'''export function crc16(data: Uint8Array, poly = 0x1021) {
  let crc = 0xffff;
  for (const b of data) {
    crc ^= b << 8;
    for (let i = 0; i < 8; i++) crc = crc & 0x8000 ? ((crc << 1) ^ poly) & 0xffff : (crc << 1) & 0xffff;
  }
  return crc;
}''',
        "provides": "crc16(data, poly)",
        "depends": [],
    },
    {
        "id": "embed-nibble",
        "name": "Nibble Split/Join",
        "category": "embed",
        "lang": "typescript",
        "when": "Encoding a byte as two 4-bit values (e.g. hex digits)",
        "why": "Atomic nibble — byte in, hi/lo out; pair back to byte",
        "tags": ["embed", "nibble", "byte", "split", "hex"],
        "iface": r'''export function splitNibbles(byte: number): [number, number]
export function joinNibbles(hi: number, lo: number): number''',
        "code": r'''export function splitNibbles(byte: number) { return [(byte >> 4) & 0x0f, byte & 0x0f]; }
export function joinNibbles(hi: number, lo: number) { return ((hi & 0x0f) << 4) | (lo & 0x0f); }''',
        "provides": "splitNibbles / joinNibbles",
        "depends": [],
    },
    {
        "id": "embed-reset-causes",
        "name": "Reset Cause Decoder",
        "category": "embed",
        "lang": "typescript",
        "when": "Decoding a device reset-cause bitmask to readable causes",
        "why": "Atomic decoder — bitmask + known flags in, named causes out",
        "tags": ["embed", "reset", "cause", "decode", "flags"],
        "iface": r'''export function resetCauses(mask: number, flags: Record<string, number>): string[]''',
        "code": r'''export function resetCauses(mask: number, flags: Record<string, number>) {
  return Object.entries(flags).filter(([, bit]) => mask & bit).map(([name]) => name);
}''',
        "provides": "resetCauses(mask, flags)",
        "depends": [],
    },
    {
        "id": "embed-queued-worker",
        "name": "Queued Job Worker",
        "category": "embed",
        "lang": "typescript",
        "when": "Processing sensor/IO jobs serially from a queue",
        "why": "Atomic worker — enqueue in, one-at-a-time processing with callback",
        "tags": ["embed", "queue", "worker", "jobs", "serial"],
        "iface": r'''export class JobQueue<T> {
  constructor(process: (job: T) => void)
  enqueue(job: T): void
  get pending(): number
}''',
        "code": r'''export class JobQueue<T> {
  private q: T[] = [];
  private running = false;
  constructor(private process: (job: T) => void) {}
  enqueue(job: T) {
    this.q.push(job);
    if (!this.running) { this.running = true; this.drain(); }
  }
  private drain() {
    const job = this.q.shift();
    if (!job) { this.running = false; return; }
    this.process(job);
    this.drain();
  }
  get pending() { return this.q.length; }
}''',
        "provides": "JobQueue",
        "depends": [],
    },
    {
        "id": "embed-parse-fixed",
        "name": "Fixed-Point Parse/Format",
        "category": "embed",
        "lang": "typescript",
        "when": "Parsing and formatting fixed-point values without floats",
        "why": "Atomic fixed-point — scaled integer in, string out; parse reverse",
        "tags": ["embed", "fixed-point", "parse", "format", "int"],
        "iface": r'''export function fixedFormat(scaled: number, decimals: number): string
export function fixedParse(text: string, decimals: number): number''',
        "code": r'''export function fixedFormat(scaled: number, decimals: number) {
  const neg = scaled < 0;
  const v = Math.abs(scaled);
  const f = Math.pow(10, decimals);
  const int = Math.floor(v / f);
  const frac = String(v % f).padStart(decimals, '0');
  return (neg ? '-' : '') + int + '.' + frac;
}
export function fixedParse(text: string, decimals: number) {
  const neg = text.startsWith('-');
  const clean = text.replace('-', '').replace('.', '');
  const f = Math.pow(10, decimals);
  const v = parseInt(clean || '0', 10);
  const scaled = decimals > 0 ? Math.round(v / (f / 1000)) * (f / 1000) : v;
  return (neg ? -1 : 1) * Math.round(scaled);
}''',
        "provides": "fixedFormat / fixedParse",
        "depends": [],
    },
    {
        "id": "embed-watchdog",
        "name": "Watchdog Kick",
        "category": "embed",
        "lang": "typescript",
        "when": "Tracking loop health and flagging missed heartbeats",
        "why": "Atomic watchdog — kick() + deadline in, tripped boolean + ms left out",
        "tags": ["embed", "watchdog", "heartbeat", "kick", "timeout"],
        "iface": r'''export class Watchdog {
  constructor(timeoutMs: number)
  kick(): void
  status(now: number): { tripped: boolean; remainingMs: number }
}''',
        "code": r'''export class Watchdog {
  private last = Date.now();
  constructor(private timeoutMs: number) {}
  kick() { this.last = Date.now(); }
  status(now: number) {
    const remainingMs = this.last + this.timeoutMs - now;
    return { tripped: remainingMs <= 0, remainingMs: Math.max(0, remainingMs) };
  }
}''',
        "provides": "Watchdog",
        "depends": [],
    },
    {
        "id": "embed-baud-rate",
        "name": "Baud Rate Timing",
        "category": "embed",
        "lang": "typescript",
        "when": "Computing bit time and achievable bytes/sec for a serial link",
        "why": "Atomic math \u2014 baud + data bits in, bit-time and max B/s out",
        "tags": [
            "embed",
            "baud",
            "serial",
            "timing",
            "uart"
        ],
        "iface": "export function baudTiming(baud: number, dataBits = 8, stopBits = 1): { bitUs: number; bytesPerSec: number }",
        "code": "export function baudTiming(baud: number, dataBits = 8, stopBits = 1) {\n  const bitsPerByte = 1 + dataBits + stopBits; // start + data + stop\n  return { bitUs: baud <= 0 ? 0 : 1_000_000 / baud, bytesPerSec: baud / bitsPerByte };\n}",
        "provides": "baudTiming(baud, dataBits, stopBits)",
        "depends": []
    },
]
