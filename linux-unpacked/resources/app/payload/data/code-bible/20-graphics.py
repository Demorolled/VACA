# -*- coding: utf-8 -*-
"""
Code Bible — Category 20: Graphics & visualization (atomic, single-responsibility).
Convention: pure math + canvas-2d helpers; no WebGL dependency required.
"""
CHUNKS = [
    {
        "id": "gfx-color",
        "name": "Color Helpers",
        "category": "gfx",
        "lang": "typescript",
        "when": "Converting between hex, rgb and hsl, with alpha",
        "why": "Atomic palette: parse + format, no libs, clamping built in",
        "tags": ["gfx", "color", "hex", "rgb", "hsl"],
        "iface": r'''export interface Rgb { r: number; g: number; b: number; a?: number }
export interface Hsl { h: number; s: number; l: number }
export function hexToRgb(hex: string): Rgb | null
export function rgbToHex(rgb: Rgb): string
export function rgbToHsl(rgb: Rgb): Hsl
export function hslToRgb(hsl: Hsl): Rgb''',
        "code": r'''export function hexToRgb(hex: string): Rgb | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}
export function rgbToHex(rgb: Rgb) {
  const c = (v: number) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0');
  return `#${c(rgb.r)}${c(rgb.g)}${c(rgb.b)}`;
}
export function rgbToHsl(rgb: Rgb): Hsl {
  const r = rgb.r / 255, g = rgb.g / 255, b = rgb.b / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l: l * 100 };
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return { h: h * 60, s: s * 100, l: l * 100 };
}
export function hslToRgb(hsl: Hsl): Rgb {
  const h = hsl.h / 360, s = hsl.s / 100, l = hsl.l / 100;
  if (s === 0) { const v = l * 255; return { r: v, g: v, b: v }; }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const hue = (t: number) => {
    let tt = t; if (tt < 0) tt += 1; if (tt > 1) tt -= 1;
    if (tt < 1 / 6) return p + (q - p) * 6 * tt;
    if (tt < 1 / 2) return q;
    if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
    return p;
  };
  return { r: hue(h + 1 / 3) * 255, g: hue(h) * 255, b: hue(h - 1 / 3) * 255 };
}''',
        "provides": "hexToRgb / rgbToHex / rgbToHsl / hslToRgb",
        "depends": [],
    },
    {
        "id": "gfx-vec2",
        "name": "2D Vector Math",
        "category": "gfx",
        "lang": "typescript",
        "when": "Vector arithmetic for positions and velocities",
        "why": "Atomic vec2: add/sub/scale/len/norm/dot, immutable, zero allocation",
        "tags": ["gfx", "vector", "vec2", "math", "2d"],
        "iface": r'''export type Vec2 = { x: number; y: number }
export function vAdd(a: Vec2, b: Vec2): Vec2
export function vSub(a: Vec2, b: Vec2): Vec2
export function vScale(v: Vec2, s: number): Vec2
export function vLen(v: Vec2): number
export function vNorm(v: Vec2): Vec2
export function vDot(a: Vec2, b: Vec2): number
export function vDist(a: Vec2, b: Vec2): number''',
        "code": r'''export const vAdd = (a: Vec2, b: Vec2): Vec2 => ({ x: a.x + b.x, y: a.y + b.y });
export const vSub = (a: Vec2, b: Vec2): Vec2 => ({ x: a.x - b.x, y: a.y - b.y });
export const vScale = (v: Vec2, s: number): Vec2 => ({ x: v.x * s, y: v.y * s });
export const vLen = (v: Vec2) => Math.hypot(v.x, v.y);
export const vNorm = (v: Vec2): Vec2 => { const l = vLen(v); return l === 0 ? { x: 0, y: 0 } : { x: v.x / l, y: v.y / l }; };
export const vDot = (a: Vec2, b: Vec2) => a.x * b.x + a.y * b.y;
export const vDist = (a: Vec2, b: Vec2) => vLen(vSub(a, b));''',
        "provides": "vAdd / vSub / vScale / vLen / vNorm / vDot / vDist",
        "depends": [],
    },
    {
        "id": "gfx-matrix2d",
        "name": "2D Affine Matrix",
        "category": "gfx",
        "lang": "typescript",
        "when": "Composing translate/rotate/scale transforms",
        "why": "Atomic 3x3: multiply/apply/identity, canvas-compatible ordering",
        "tags": ["gfx", "matrix", "affine", "transform", "2d"],
        "iface": r'''export type Mat2 = [number, number, number, number, number, number]  // a b c d e f
export function m2Identity(): Mat2
export function m2Multiply(a: Mat2, b: Mat2): Mat2
export function m2Translate(tx: number, ty: number): Mat2
export function m2Rotate(rad: number): Mat2
export function m2Scale(sx: number, sy: number): Mat2
export function m2Apply(m: Mat2, x: number, y: number): { x: number; y: number }''',
        "code": r'''export const m2Identity = (): Mat2 => [1, 0, 0, 1, 0, 0];
export function m2Multiply(a: Mat2, b: Mat2): Mat2 {
  return [
    a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
    a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
    a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5],
  ];
}
export const m2Translate = (tx: number, ty: number): Mat2 => [1, 0, 0, 1, tx, ty];
export const m2Rotate = (rad: number): Mat2 => [Math.cos(rad), Math.sin(rad), -Math.sin(rad), Math.cos(rad), 0, 0];
export const m2Scale = (sx: number, sy: number): Mat2 => [sx, 0, 0, sy, 0, 0];
export function m2Apply(m: Mat2, x: number, y: number) {
  return { x: m[0] * x + m[2] * y + m[4], y: m[1] * x + m[3] * y + m[5] };
}''',
        "provides": "Mat2 helpers",
        "depends": [],
    },
    {
        "id": "gfx-bezier",
        "name": "Bézier Curve Sampler",
        "category": "gfx",
        "lang": "typescript",
        "when": "Sampling points along quadratic/cubic curves",
        "why": "Atomic sampler: control points in, t in [0,1] → point out, de Casteljau",
        "tags": ["gfx", "bezier", "curve", "sample", "de-casteljau"],
        "iface": r'''export function bezierQuad(p0: Vec2, p1: Vec2, p2: Vec2, t: number): Vec2
export function bezierCubic(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: number): Vec2
export function bezierPoints(pts: Vec2[], steps?: number): Vec2[]''',
        "code": r'''export function bezierQuad(p0: Vec2, p1: Vec2, p2: Vec2, t: number): Vec2 {
  const mt = 1 - t;
  return {
    x: mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x,
    y: mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y,
  };
}
export function bezierCubic(p0: Vec2, p1: Vec2, p2: Vec2, p3: Vec2, t: number): Vec2 {
  const mt = 1 - t;
  return {
    x: mt ** 3 * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t ** 3 * p3.x,
    y: mt ** 3 * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t ** 3 * p3.y,
  };
}
export function bezierPoints(pts: Vec2[], steps = 20) {
  const out: Vec2[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    out.push(pts.length === 3 ? bezierQuad(pts[0], pts[1], pts[2], t) : bezierCubic(pts[0], pts[1], pts[2], pts[3], t));
  }
  return out;
}''',
        "provides": "bezierQuad / bezierCubic / bezierPoints",
        "depends": [],
    },
    {
        "id": "gfx-noise",
        "name": "Perlin Noise 2D",
        "category": "gfx",
        "lang": "typescript",
        "when": "Generating smooth organic textures and terrain",
        "why": "Atomic noise: value-noise with smooth interpolation + fbm octaves, seeded",
        "tags": ["gfx", "perlin", "noise", "fbm", "texture"],
        "iface": r'''export class Noise2D {
  constructor(seed?: number)
  value(x: number, y: number): number
  fbm(x: number, y: number, octaves?: number): number
}''',
        "code": r'''export class Noise2D {
  private perm: number[] = [];
  constructor(seed = 1337) {
    let s = seed;
    const rand = () => { s |= 0; s = (s + 0x6d2b79f5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    this.perm = Array.from({ length: 512 }, (_, i) => (i % 256));
    for (let i = 255; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [this.perm[i], this.perm[j]] = [this.perm[j], this.perm[i]]; }
    for (let i = 0; i < 256; i++) this.perm[256 + i] = this.perm[i];
  }
  private hash(x: number, y: number) { return this.perm[(this.perm[x & 255] + y) & 255]; }
  private smooth(t: number) { return t * t * (3 - 2 * t); }
  value(x: number, y: number) {
    const xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    const u = this.smooth(xf), v = this.smooth(yf);
    const a = this.hash(xi, yi), b = this.hash(xi + 1, yi), c = this.hash(xi, yi + 1), d = this.hash(xi + 1, yi + 1);
    return (a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v) / 255;
  }
  fbm(x: number, y: number, octaves = 4) {
    let sum = 0, amp = 1, freq = 1, norm = 0;
    for (let i = 0; i < octaves; i++) { sum += this.value(x * freq, y * freq) * amp; norm += amp; amp *= 0.5; freq *= 2; }
    return sum / norm;
  }
}''',
        "provides": "Noise2D",
        "depends": [],
    },
    {
        "id": "gfx-aspect-fit",
        "name": "Aspect-Fit Image Draw",
        "category": "gfx",
        "lang": "typescript",
        "when": "Drawing images scaled to fit a box without distortion",
        "why": "Atomic layout: source + target in, contain/cover rect out",
        "tags": ["gfx", "image", "aspect", "fit", "cover"],
        "iface": r'''export interface FitRect { x: number; y: number; w: number; h: number }
export function fitContain(imgW: number, imgH: number, boxW: number, boxH: number): FitRect
export function fitCover(imgW: number, imgH: number, boxW: number, boxH: number): FitRect''',
        "code": r'''export function fitContain(imgW: number, imgH: number, boxW: number, boxH: number): FitRect {
  const scale = Math.min(boxW / imgW, boxH / imgH);
  const w = imgW * scale, h = imgH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h };
}
export function fitCover(imgW: number, imgH: number, boxW: number, boxH: number): FitRect {
  const scale = Math.max(boxW / imgW, boxH / imgH);
  const w = imgW * scale, h = imgH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h };
}''',
        "provides": "fitContain / fitCover",
        "depends": [],
    },
    {
        "id": "gfx-text-wrap",
        "name": "Canvas Text Wrap",
        "category": "gfx",
        "lang": "typescript",
        "when": "Wrapping text to a max width inside a canvas",
        "why": "Atomic wrapper: ctx + text + maxWidth in, wrapped lines out via measureText",
        "tags": ["gfx", "text", "wrap", "canvas", "measure"],
        "iface": r'''export function wrapCanvasText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[]''',
        "code": r'''export function wrapCanvasText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number) {
  const lines: string[] = [];
  let line = '';
  for (const word of text.split(/\s+/)) {
    const test = line ? line + ' ' + word : word;
    if (ctx.measureText(test).width <= maxWidth) { line = test; }
    else { if (line) lines.push(line); line = word; }
  }
  if (line) lines.push(line);
  return lines;
}''',
        "provides": "wrapCanvasText(ctx, text, maxWidth)",
        "depends": [],
    },
    {
        "id": "gfx-pixels",
        "name": "Pixel Buffer Get/Set",
        "category": "gfx",
        "lang": "typescript",
        "when": "Reading and writing individual pixels of an ImageData",
        "why": "Atomic pixel ops: get/set indexed by x,y, RGBA clamp, no allocations",
        "tags": ["gfx", "pixel", "imagedata", "rgba", "buffer"],
        "iface": r'''export function getPixel(data: ImageData, x: number, y: number): [number, number, number, number]
export function setPixel(data: ImageData, x: number, y: number, rgba: [number, number, number, number]): void''',
        "code": r'''export function getPixel(data: ImageData, x: number, y: number): [number, number, number, number] {
  const i = (y * data.width + x) * 4;
  return [data.data[i], data.data[i + 1], data.data[i + 2], data.data[i + 3]];
}
export function setPixel(data: ImageData, x: number, y: number, rgba: [number, number, number, number]) {
  const i = (y * data.width + x) * 4;
  data.data[i] = rgba[0]; data.data[i + 1] = rgba[1]; data.data[i + 2] = rgba[2]; data.data[i + 3] = rgba[3];
}''',
        "provides": "getPixel / setPixel",
        "depends": [],
    },
    {
        "id": "gfx-particle",
        "name": "Particle Emitter (2D)",
        "category": "gfx",
        "lang": "typescript",
        "when": "Confetti, sparks and explosion effects",
        "why": "Atomic emitter: spawn/update/draw loop, gravity + friction, pool-less",
        "tags": ["gfx", "particle", "emitter", "effect", "confetti"],
        "iface": r'''export interface Particle { x: number; y: number; vx: number; vy: number; life: number; maxLife: number; size: number; color: string }
export class ParticleEmitter {
  constructor(opts?: { gravity?: number; friction?: number })
  spawn(opts: { x: number; y: number; count?: number; speed?: number; colors?: string[]; life?: number }): void
  update(dt: number): void
  draw(ctx: CanvasRenderingContext2D): void
  get particles(): Particle[]
}''',
        "code": r'''export class ParticleEmitter {
  private items: Particle[] = [];
  constructor(private opts: { gravity?: number; friction?: number } = {}) {}
  spawn(o: { x: number; y: number; count?: number; speed?: number; colors?: string[]; life?: number }) {
    const colors = o.colors ?? ['#f59e0b', '#ef4444', '#3b82f6', '#22c55e'];
    for (let i = 0; i < (o.count ?? 20); i++) {
      const angle = Math.random() * Math.PI * 2;
      const speed = (o.speed ?? 150) * (0.4 + Math.random() * 0.6);
      this.items.push({
        x: o.x, y: o.y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        life: o.life ?? 1, maxLife: o.life ?? 1, size: 2 + Math.random() * 4,
        color: colors[Math.floor(Math.random() * colors.length)],
      });
    }
  }
  update(dt: number) {
    const g = this.opts.gravity ?? 300, f = this.opts.friction ?? 0.99;
    for (const p of this.items) {
      p.vy += g * dt;
      p.vx *= f; p.vy *= f;
      p.x += p.vx * dt; p.y += p.vy * dt;
      p.life -= dt;
    }
    this.items = this.items.filter((p) => p.life > 0);
  }
  draw(ctx: CanvasRenderingContext2D) {
    for (const p of this.items) {
      ctx.globalAlpha = Math.max(0, p.life / p.maxLife);
      ctx.fillStyle = p.color;
      ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
    }
    ctx.globalAlpha = 1;
  }
  get particles() { return this.items; }
}''',
        "provides": "ParticleEmitter",
        "depends": [],
    },
    {
        "id": "gfx-collision",
        "name": "2D Collision Tests",
        "category": "gfx",
        "lang": "typescript",
        "when": "Hit-testing circles, rects and points",
        "why": "Atomic tests: AABB, circle, point-in, overlap — no physics engine",
        "tags": ["gfx", "collision", "aabb", "circle", "hit-test"],
        "iface": r'''export interface Rect { x: number; y: number; w: number; h: number }
export interface Circle { x: number; y: number; r: number }
export function aabbOverlap(a: Rect, b: Rect): boolean
export function circleOverlap(a: Circle, b: Circle): boolean
export function pointInRect(p: { x: number; y: number }, r: Rect): boolean
export function circleRect(c: Circle, r: Rect): boolean''',
        "code": r'''export function aabbOverlap(a: Rect, b: Rect) { return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y; }
export function circleOverlap(a: Circle, b: Circle) { const dx = a.x - b.x, dy = a.y - b.y; return dx * dx + dy * dy <= (a.r + b.r) ** 2; }
export function pointInRect(p: { x: number; y: number }, r: Rect) { return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h; }
export function circleRect(c: Circle, r: Rect) {
  const cx = Math.max(r.x, Math.min(c.x, r.x + r.w));
  const cy = Math.max(r.y, Math.min(c.y, r.y + r.h));
  const dx = c.x - cx, dy = c.y - cy;
  return dx * dx + dy * dy <= c.r * c.r;
}''',
        "provides": "aabbOverlap / circleOverlap / pointInRect / circleRect",
        "depends": [],
    },
    {
        "id": "gfx-camera",
        "name": "2D Camera (pan/zoom)",
        "category": "gfx",
        "lang": "typescript",
        "when": "Following a target with zoom in a canvas world",
        "why": "Atomic camera: world↔screen transforms, follow with lerp, zoom clamp",
        "tags": ["gfx", "camera", "zoom", "pan", "world"],
        "iface": r'''export class Camera2D {
  constructor(opts?: { zoom?: number; minZoom?: number; maxZoom?: number; lerp?: number })
  follow(target: { x: number; y: number }, dt?: number): void
  screenToWorld(sx: number, sy: number, viewW: number, viewH: number): { x: number; y: number }
  get x(): number
  get y(): number
  get zoom(): number
  setZoom(z: number): void
}''',
        "code": r'''export class Camera2D {
  private _x = 0; private _y = 0;
  private _zoom: number;
  constructor(private opts: { zoom?: number; minZoom?: number; maxZoom?: number; lerp?: number } = {}) { this._zoom = opts.zoom ?? 1; }
  follow(target: { x: number; y: number }, dt = 1 / 60) {
    const k = this.opts.lerp ?? 6;
    const a = 1 - Math.exp(-k * dt);
    this._x += (target.x - this._x) * a;
    this._y += (target.y - this._y) * a;
  }
  screenToWorld(sx: number, sy: number, viewW: number, viewH: number) {
    return { x: this._x + (sx - viewW / 2) / this._zoom, y: this._y + (sy - viewH / 2) / this._zoom };
  }
  get x() { return this._x; }
  get y() { return this._y; }
  get zoom() { return this._zoom; }
  setZoom(z: number) { this._zoom = Math.min(this.opts.maxZoom ?? 4, Math.max(this.opts.minZoom ?? 0.2, z)); }
}''',
        "provides": "Camera2D",
        "depends": [],
    },
    {
        "id": "gfx-svg-path",
        "name": "SVG Path Builder",
        "category": "gfx",
        "lang": "typescript",
        "when": "Composing SVG path data strings for charts and icons",
        "why": "Atomic builder: move/line/curve appends, d-string out, numeric rounding",
        "tags": ["gfx", "svg", "path", "builder", "d"],
        "iface": r'''export class SvgPath {
  moveTo(x: number, y: number): this
  lineTo(x: number, y: number): this
  curveTo(cx: number, cy: number, x: number, y: number): this
  close(): this
  toString(): string
}''',
        "code": r'''export class SvgPath {
  private parts: string[] = [];
  private r2 = (n: number) => Math.round(n * 100) / 100;
  moveTo(x: number, y: number) { this.parts.push(`M${this.r2(x)} ${this.r2(y)}`); return this; }
  lineTo(x: number, y: number) { this.parts.push(`L${this.r2(x)} ${this.r2(y)}`); return this; }
  curveTo(cx: number, cy: number, x: number, y: number) { this.parts.push(`Q${this.r2(cx)} ${this.r2(cy)} ${this.r2(x)} ${this.r2(y)}`); return this; }
  close() { this.parts.push('Z'); return this; }
  toString() { return this.parts.join(' '); }
}''',
        "provides": "SvgPath",
        "depends": [],
    },
    {
        "id": "gfx-palette",
        "name": "HSL Palette Generator",
        "category": "gfx",
        "lang": "typescript",
        "when": "Generating harmonious color ramps for charts",
        "why": "Atomic generator: base hue + count in, evenly spaced palette out",
        "tags": ["gfx", "palette", "hsl", "generate", "chart"],
        "iface": r'''export function generatePalette(count: number, opts?: { hue?: number; saturation?: number; lightness?: number; spread?: number }): string[]''',
        "code": r'''export function generatePalette(count: number, opts: { hue?: number; saturation?: number; lightness?: number; spread?: number } = {}) {
  const hue = opts.hue ?? 210, sat = opts.saturation ?? 70, light = opts.lightness ?? 55;
  const spread = opts.spread ?? 300;
  return Array.from({ length: count }, (_, i) => `hsl(${Math.round(hue + (spread * i) / Math.max(1, count))} ${sat}% ${light}%)`);
}''',
        "provides": "generatePalette(count, opts)",
        "depends": [],
    },
    {
        "id": "gfx-blur",
        "name": "Gaussian Blur Kernel",
        "category": "gfx",
        "lang": "typescript",
        "when": "Applying a box-blur approximation to ImageData",
        "why": "Atomic blur: separable two-pass box blur, radius in, in-place ImageData out",
        "tags": ["gfx", "blur", "gaussian", "kernel", "image"],
        "iface": r'''export function blurImageData(data: ImageData, radius: number): ImageData''',
        "code": r'''function pass(src: Uint8ClampedArray, w: number, h: number, radius: number, horiz: boolean) {
  const dst = new Uint8ClampedArray(src.length);
  const n = horiz ? w : h;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let r = 0, g = 0, b = 0, a = 0, count = 0;
    for (let k = -radius; k <= radius; k++) {
      const idx = horiz ? x + k : y + k;
      if (idx < 0 || idx >= n) continue;
      const o = (horiz ? y * w + idx : idx * w + x) * 4;
      r += src[o]; g += src[o + 1]; b += src[o + 2]; a += src[o + 3]; count++;
    }
    const o = (y * w + x) * 4;
    dst[o] = r / count; dst[o + 1] = g / count; dst[o + 2] = b / count; dst[o + 3] = a / count;
  }
  return dst;
}
export function blurImageData(data: ImageData, radius: number) {
  const { width: w, height: h, data: src } = data;
  const once = pass(src, w, h, radius, true);
  const twice = pass(once, w, h, radius, false);
  return new ImageData(twice, w, h);
}''',
        "provides": "blurImageData(data, radius)",
        "depends": [],
    },
    {
        "id": "gfx-easing",
        "name": "Easing Functions",
        "category": "gfx",
        "lang": "typescript",
        "when": "Animating with smooth acceleration and deceleration",
        "why": "Atomic easings: in/out/inOut for linear, quad, cubic, elastic, bounce",
        "tags": ["gfx", "easing", "animation", "tween", "interpolate"],
        "iface": r'''export type Easing = (t: number) => number
export const easings: Record<'linear' | 'quadIn' | 'quadOut' | 'quadInOut' | 'cubicIn' | 'cubicOut' | 'cubicInOut' | 'elasticOut' | 'bounceOut', Easing>
export function animate(from: number, to: number, t: number, easing?: Easing): number''',
        "code": r'''const clamp = (t: number) => Math.min(1, Math.max(0, t));
export const easings = {
  linear: (t: number) => clamp(t),
  quadIn: (t: number) => { t = clamp(t); return t * t; },
  quadOut: (t: number) => { t = clamp(t); return t * (2 - t); },
  quadInOut: (t: number) => { t = clamp(t); return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; },
  cubicIn: (t: number) => { t = clamp(t); return t * t * t; },
  cubicOut: (t: number) => { const u = clamp(t) - 1; return u * u * u + 1; },
  cubicInOut: (t: number) => { t = clamp(t); return t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1; },
  elasticOut: (t: number) => { t = clamp(t); if (t === 0 || t === 1) return t; return Math.pow(2, -10 * t) * Math.sin((t - 0.1) * 5 * Math.PI) + 1; },
  bounceOut: (t: number) => { t = clamp(t); const n1 = 7.5625, d1 = 2.75; if (t < 1 / d1) return n1 * t * t; if (t < 2 / d1) return n1 * (t -= 1.5 / d1) * t + 0.75; if (t < 2.5 / d1) return n1 * (t -= 2.25 / d1) * t + 0.9375; return n1 * (t -= 2.625 / d1) * t + 0.984375; },
};
export function animate(from: number, to: number, t: number, easing: Easing = easings.linear) {
  return from + (to - from) * easing(t);
}''',
        "provides": "easings / animate",
        "depends": [],
    },
    {
        "id": "gfx-grid-layout",
        "name": "Grid Cell Layout",
        "category": "gfx",
        "lang": "typescript",
        "when": "Laying out tiles evenly in a fixed area",
        "why": "Atomic layout: area + cols in, cell rect out, gap-aware",
        "tags": ["gfx", "grid", "layout", "tiles", "cells"],
        "iface": r'''export function gridLayout(opts: { width: number; height: number; cols: number; gap?: number; margin?: number }): Array<{ x: number; y: number; w: number; h: number }>''',
        "code": r'''export function gridLayout(opts: { width: number; height: number; cols: number; gap?: number; margin?: number }) {
  const gap = opts.gap ?? 4, margin = opts.margin ?? 0;
  const innerW = opts.width - margin * 2, innerH = opts.height - margin * 2;
  const rows = Math.max(1, Math.ceil((innerH + gap) / (innerW / opts.cols + gap)));
  const cellW = (innerW - gap * (opts.cols - 1)) / opts.cols;
  const cellH = (innerH - gap * (rows - 1)) / rows;
  const out = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < opts.cols; c++) {
    out.push({ x: margin + c * (cellW + gap), y: margin + r * (cellH + gap), w: cellW, h: cellH });
  }
  return out;
}''',
        "provides": "gridLayout(opts)",
        "depends": [],
    },
    {
        "id": "gfx-round-rect",
        "name": "Rounded Rect Path",
        "category": "gfx",
        "lang": "typescript",
        "when": "Drawing rounded rectangles on canvas (badges, cards)",
        "why": "Atomic path: ctx + rect + radius in, arcTo corners, no allocations",
        "tags": ["gfx", "round", "rect", "canvas", "path"],
        "iface": r'''export function roundedRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void''',
        "code": r'''export function roundedRectPath(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}''',
        "provides": "roundedRectPath(ctx, x, y, w, h, r)",
        "depends": [],
    },
    {
        "id": "gfx-arc",
        "name": "Arc/Dial Helper",
        "category": "gfx",
        "lang": "typescript",
        "when": "Drawing progress rings and gauge dials",
        "why": "Atomic arc: start/end angles from progress, center/radius math out",
        "tags": ["gfx", "arc", "dial", "progress", "ring"],
        "iface": r'''export function arcAngles(progress: number, startAngle?: number): { start: number; end: number }
export function polarPoint(cx: number, cy: number, r: number, angle: number): { x: number; y: number }''',
        "code": r'''export function arcAngles(progress: number, startAngle = -Math.PI / 2) {
  const p = Math.min(1, Math.max(0, progress));
  return { start: startAngle, end: startAngle + p * Math.PI * 2 };
}
export function polarPoint(cx: number, cy: number, r: number, angle: number) {
  return { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
}''',
        "provides": "arcAngles / polarPoint",
        "depends": [],
    },
    {
        "id": "gfx-gradient",
        "name": "Canvas Gradient Factory",
        "category": "gfx",
        "lang": "typescript",
        "when": "Creating linear and radial gradients with stops",
        "why": "Atomic factory: type + colors in, canvas gradient out, stop helper",
        "tags": ["gfx", "gradient", "canvas", "linear", "radial"],
        "iface": r'''export function makeLinearGradient(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number, stops: Array<[number, string]>): CanvasGradient
export function makeRadialGradient(ctx: CanvasRenderingContext2D, x: number, y: number, r0: number, r1: number, stops: Array<[number, string]>): CanvasGradient''',
        "code": r'''export function makeLinearGradient(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number, stops: Array<[number, string]>) {
  const g = ctx.createLinearGradient(x0, y0, x1, y1);
  for (const [o, c] of stops) g.addColorStop(o, c);
  return g;
}
export function makeRadialGradient(ctx: CanvasRenderingContext2D, x: number, y: number, r0: number, r1: number, stops: Array<[number, string]>) {
  const g = ctx.createRadialGradient(x, y, r0, x, y, r1);
  for (const [o, c] of stops) g.addColorStop(o, c);
  return g;
}''',
        "provides": "makeLinearGradient / makeRadialGradient",
        "depends": [],
    },
    {
        "id": "gfx-shadow",
        "name": "Canvas Shadow Utility",
        "category": "gfx",
        "lang": "typescript",
        "when": "Applying and restoring canvas shadow settings",
        "why": "Atomic util: set shadow + restore previous, option defaults",
        "tags": ["gfx", "shadow", "canvas", "blur", "style"],
        "iface": r'''export function withShadow(ctx: CanvasRenderingContext2D, opts: { blur: number; offsetX?: number; offsetY?: number; color?: string }, draw: () => void): void''',
        "code": r'''export function withShadow(ctx: CanvasRenderingContext2D, opts: { blur: number; offsetX?: number; offsetY?: number; color?: string }, draw: () => void) {
  const prev = { blur: ctx.shadowBlur, x: ctx.shadowOffsetX, y: ctx.shadowOffsetY, color: ctx.shadowColor };
  ctx.shadowBlur = opts.blur;
  ctx.shadowOffsetX = opts.offsetX ?? 0;
  ctx.shadowOffsetY = opts.offsetY ?? 0;
  ctx.shadowColor = opts.color ?? 'rgba(0,0,0,0.4)';
  try { draw(); } finally { ctx.shadowBlur = prev.blur; ctx.shadowOffsetX = prev.x; ctx.shadowOffsetY = prev.y; ctx.shadowColor = prev.color; }
}''',
        "provides": "withShadow(ctx, opts, draw)",
        "depends": [],
    },
    {
        "id": "gfx-offscreen",
        "name": "Offscreen Canvas Cache",
        "category": "gfx",
        "lang": "typescript",
        "when": "Caching expensive renders for fast redraws",
        "why": "Atomic cache: key + renderer in, cached canvas out, LRU + resize invalidation",
        "tags": ["gfx", "offscreen", "canvas", "cache", "render"],
        "iface": r'''export class CanvasCache {
  constructor(capacity?: number)
  get(key: string, w: number, h: number, render: (ctx: CanvasRenderingContext2D) => void): HTMLCanvasElement
  invalidate(key?: string): void
}''',
        "code": r'''export class CanvasCache {
  private store = new Map<string, HTMLCanvasElement>();
  constructor(private capacity = 50) {}
  get(key: string, w: number, h: number, render: (ctx: CanvasRenderingContext2D) => void) {
    const hit = this.store.get(key);
    if (hit && hit.width === w && hit.height === h) { this.store.delete(key); this.store.set(key, hit); return hit; }
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d')!;
    render(ctx);
    this.store.set(key, canvas);
    if (this.store.size > this.capacity) this.store.delete(this.store.keys().next().value!);
    return canvas;
  }
  invalidate(key?: string) { if (key) this.store.delete(key); else this.store.clear(); }
}''',
        "provides": "CanvasCache",
        "depends": [],
    },
    {
        "id": "gfx-sprite-frame",
        "name": "Sprite Frame Clock",
        "category": "gfx",
        "lang": "typescript",
        "when": "Advancing sprite animation frames by time",
        "why": "Atomic clock: fps + frames in, current frame index out, looping",
        "tags": ["gfx", "sprite", "frame", "animation", "clock"],
        "iface": r'''export class SpriteClock {
  constructor(fps?: number)
  update(dt: number): void
  reset(): void
  get frame(): number
  set fps(fps: number)
}''',
        "code": r'''export class SpriteClock {
  private acc = 0;
  private _frame = 0;
  private _fps: number;
  constructor(fps = 12) { this._fps = fps; }
  update(dt: number) {
    this.acc += dt;
    const frameMs = 1 / this._fps;
    while (this.acc >= frameMs) { this.acc -= frameMs; this._frame++; }
  }
  reset() { this.acc = 0; this._frame = 0; }
  get frame() { return this._frame; }
  set fps(fps: number) { this._fps = Math.max(1, fps); }
}''',
        "provides": "SpriteClock",
        "depends": [],
    },
    {
        "id": "gfx-canvas-size",
        "name": "Canvas HiDPI Setup",
        "category": "gfx",
        "lang": "typescript",
        "when": "Making canvas crisp on retina displays",
        "why": "Atomic setup: canvas in, devicePixelRatio scaling + ctx transform out",
        "tags": ["gfx", "canvas", "hidpi", "retina", "dpr"],
        "iface": r'''export function setupHiDpi(canvas: HTMLCanvasElement, w: number, h: number, dpr?: number): CanvasRenderingContext2D''',
        "code": r'''export function setupHiDpi(canvas: HTMLCanvasElement, w: number, h: number, dpr = window.devicePixelRatio || 1) {
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  const ctx = canvas.getContext('2d')!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}''',
        "provides": "setupHiDpi(canvas, w, h, dpr)",
        "depends": [],
    },
    {
        "id": "gfx-lerp-color",
        "name": "Color Lerp",
        "category": "gfx",
        "lang": "typescript",
        "when": "Interpolating between two colors for gradients in time",
        "why": "Atomic lerp: rgb in/out, t clamped, no allocation churn",
        "tags": ["gfx", "lerp", "color", "interpolate", "rgb"],
        "iface": r'''export function lerpColor(a: Rgb, b: Rgb, t: number): Rgb
export function mixColors(colors: Rgb[], t: number): Rgb''',
        "code": r'''export function lerpColor(a: Rgb, b: Rgb, t: number): Rgb {
  const tt = Math.min(1, Math.max(0, t));
  return { r: a.r + (b.r - a.r) * tt, g: a.g + (b.g - a.g) * tt, b: a.b + (b.b - a.b) * tt };
}
export function mixColors(colors: Rgb[], t: number): Rgb {
  if (!colors.length) return { r: 0, g: 0, b: 0 };
  if (colors.length === 1) return colors[0];
  const tt = Math.min(0.999, Math.max(0, t)) * (colors.length - 1);
  const i = Math.floor(tt);
  return lerpColor(colors[i], colors[Math.min(colors.length - 1, i + 1)], tt - i);
}''',
        "provides": "lerpColor / mixColors",
        "depends": [],
    },
    {
        "id": "gfx-voronoi",
        "name": "Voronoi Cell Partition",
        "category": "gfx",
        "lang": "typescript",
        "when": "Assigning points to the nearest seed (art styles, territories)",
        "why": "Atomic partition: seeds + points in, per-point seed index out, brute force",
        "tags": ["gfx", "voronoi", "partition", "nearest", "seeds"],
        "iface": r'''export function voronoiAssign(seeds: Array<{ x: number; y: number }>, points: Array<{ x: number; y: number }>): number[]''',
        "code": r'''export function voronoiAssign(seeds: Array<{ x: number; y: number }>, points: Array<{ x: number; y: number }>) {
  return points.map((p) => {
    let best = 0, bd = Infinity;
    seeds.forEach((s, i) => {
      const d = (p.x - s.x) ** 2 + (p.y - s.y) ** 2;
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  });
}''',
        "provides": "voronoiAssign(seeds, points)",
        "depends": [],
    },
]
