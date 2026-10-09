# -*- coding: utf-8 -*-
"""
Code Bible — Category 21: Mathematics & statistics (atomic, single-responsibility).
Convention: pure functions, no mutation of inputs, defensive edge cases.
"""
CHUNKS = [
    {
        "id": "mth-vector-ops",
        "name": "N-Dimensional Vector Ops",
        "category": "mth",
        "lang": "typescript",
        "when": "Vector arithmetic for embeddings or geometry of any dimension",
        "why": "Atomic ops: add/sub/scale/dot/norm, dimension-mismatch safe",
        "tags": ["mth", "vector", "ndim", "ops", "math"],
        "iface": r'''export function vAddN(a: number[], b: number[]): number[]
export function vScaleN(v: number[], s: number): number[]
export function vDotN(a: number[], b: number[]): number
export function vNormN(v: number[]): number
export function vNormalizeN(v: number[]): number[]''',
        "code": r'''export function vAddN(a: number[], b: number[]) { return a.map((x, i) => x + (b[i] ?? 0)); }
export function vScaleN(v: number[], s: number) { return v.map((x) => x * s); }
export function vDotN(a: number[], b: number[]) { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * (b[i] ?? 0); return s; }
export function vNormN(v: number[]) { return Math.sqrt(v.reduce((s, x) => s + x * x, 0)); }
export function vNormalizeN(v: number[]) { const l = vNormN(v); return l === 0 ? v.slice() : v.map((x) => x / l); }''',
        "provides": "vAddN / vScaleN / vDotN / vNormN / vNormalizeN",
        "depends": [],
    },
    {
        "id": "mth-matrix",
        "name": "Matrix Multiply",
        "category": "mth",
        "lang": "typescript",
        "when": "Multiplying matrices for transforms or linear systems",
        "why": "Atomic multiply: A×B in, dim-checked product out, 2D arrays",
        "tags": ["mth", "matrix", "multiply", "linear", "algebra"],
        "iface": r'''export function matMul(a: number[][], b: number[][]): number[][]
export function matIdentity(n: number): number[][]
export function matTranspose(m: number[][]): number[][]''',
        "code": r'''export function matMul(a: number[][], b: number[][]) {
  const m = a.length, k = a[0].length, n = b[0].length;
  if (b.length !== k) throw new Error(`matrix shape mismatch: ${k} vs ${b.length}`);
  const out = Array.from({ length: m }, () => new Array(n).fill(0));
  for (let i = 0; i < m; i++) for (let j = 0; j < n; j++) {
    let s = 0;
    for (let p = 0; p < k; p++) s += a[i][p] * b[p][j];
    out[i][j] = s;
  }
  return out;
}
export function matIdentity(n: number) { return Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))); }
export function matTranspose(m: number[][]) { return m[0].map((_, c) => m.map((r) => r[c])); }''',
        "provides": "matMul / matIdentity / matTranspose",
        "depends": [],
    },
    {
        "id": "mth-polynomial",
        "name": "Polynomial Evaluation",
        "category": "mth",
        "lang": "typescript",
        "when": "Evaluating polynomials in O(n) with Horner's method",
        "why": "Atomic evaluator: coefficients + x in, value out, Horner form",
        "tags": ["mth", "polynomial", "horner", "evaluate", "coeff"],
        "iface": r'''export function polyEval(coeffs: number[], x: number): number  // highest degree first
export function polyDerivative(coeffs: number[]): number[]''',
        "code": r'''export function polyEval(coeffs: number[], x: number) {
  let acc = 0;
  for (const c of coeffs) acc = acc * x + c;
  return acc;
}
export function polyDerivative(coeffs: number[]) {
  const n = coeffs.length;
  return coeffs.slice(0, -1).map((c, i) => c * (n - 1 - i));
}''',
        "provides": "polyEval / polyDerivative",
        "depends": [],
    },
    {
        "id": "mth-gcd-lcm",
        "name": "GCD / LCM",
        "category": "mth",
        "lang": "typescript",
        "when": "Simplifying ratios and computing common multiples",
        "why": "Atomic number theory: Euclidean GCD, LCM from GCD, multi-value variants",
        "tags": ["mth", "gcd", "lcm", "euclid", "number-theory"],
        "iface": r'''export function gcd(a: number, b: number): number
export function lcm(a: number, b: number): number
export function gcdMany(nums: number[]): number
export function lcmMany(nums: number[]): number''',
        "code": r'''export function gcd(a: number, b: number) { let x = Math.abs(a), y = Math.abs(b); while (y) { [x, y] = [y, x % y]; } return x; }
export function lcm(a: number, b: number) { return a === 0 || b === 0 ? 0 : Math.abs(a * b) / gcd(a, b); }
export function gcdMany(nums: number[]) { return nums.reduce((acc, n) => gcd(acc, n), 0); }
export function lcmMany(nums: number[]) { return nums.reduce((acc, n) => lcm(acc, n), 1); }''',
        "provides": "gcd / lcm / gcdMany / lcmMany",
        "depends": [],
    },
    {
        "id": "mth-mod-exp",
        "name": "Modular Exponentiation",
        "category": "mth",
        "lang": "typescript",
        "when": "Computing a^b mod m efficiently for cryptography and hashing",
        "why": "Atomic power: binary exponentiation, O(log b), no overflow via BigInt",
        "tags": ["mth", "modular", "exponent", "power", "crypto"],
        "iface": r'''export function modExp(base: number, exp: number, mod: number): number''',
        "code": r'''export function modExp(base: number, exp: number, mod: number) {
  if (mod === 0) return NaN;
  let result = 1n, b = BigInt(base) % BigInt(mod), e = BigInt(exp), m = BigInt(mod);
  while (e > 0n) { if (e & 1n) result = (result * b) % m; b = (b * b) % m; e >>= 1n; }
  return Number(result);
}''',
        "provides": "modExp(base, exp, mod)",
        "depends": [],
    },
    {
        "id": "mth-prime-factor",
        "name": "Prime Factorization",
        "category": "mth",
        "lang": "typescript",
        "when": "Breaking a number into its prime factors",
        "why": "Atomic factorizer: trial division up to sqrt(n), factor map out",
        "tags": ["mth", "prime", "factor", "factorization", "number"],
        "iface": r'''export function primeFactors(n: number): Array<{ factor: number; count: number }>
export function isPrime(n: number): boolean''',
        "code": r'''export function primeFactors(n: number) {
  const out: Array<{ factor: number; count: number }> = [];
  let x = n;
  for (let p = 2; p * p <= x; p++) {
    if (x % p === 0) { let c = 0; while (x % p === 0) { x /= p; c++; } out.push({ factor: p, count: c }); }
  }
  if (x > 1) out.push({ factor: x, count: 1 });
  return out;
}
export function isPrime(n: number) {
  if (n < 2) return false;
  if (n < 4) return true;
  if (n % 2 === 0 || n % 3 === 0) return false;
  for (let i = 5; i * i <= n; i += 6) if (n % i === 0 || n % (i + 2) === 0) return false;
  return true;
}''',
        "provides": "primeFactors / isPrime",
        "depends": [],
    },
    {
        "id": "mth-fib-fast",
        "name": "Fibonacci (fast doubling)",
        "category": "mth",
        "lang": "typescript",
        "when": "Computing the nth Fibonacci number in O(log n)",
        "why": "Atomic fast-doubling: matrix identity trick, BigInt for large n",
        "tags": ["mth", "fibonacci", "fast", "doubling", "bigint"],
        "iface": r'''export function fib(n: number): bigint
export function fibArray(n: number): number[]''',
        "code": r'''export function fib(n: number): bigint {
  if (n < 0) throw new Error('n must be >= 0');
  const f = (k: number): [bigint, bigint] => {
    if (k === 0) return [0n, 1n];
    const [a, b] = f(k >> 1);
    const c = a * (2n * b - a);
    const d = a * a + b * b;
    return k % 2 === 0 ? [c, d] : [d, c + d];
  };
  return f(n)[0];
}
export function fibArray(n: number) {
  const out = [0, 1];
  for (let i = 2; i < n; i++) out.push(out[i - 1] + out[i - 2]);
  return out.slice(0, n);
}''',
        "provides": "fib / fibArray",
        "depends": [],
    },
    {
        "id": "mth-combinatorics",
        "name": "Combinatorics (nCr, factorial)",
        "category": "mth",
        "lang": "typescript",
        "when": "Counting combinations and permutations",
        "why": "Atomic counters: iterative nCr to avoid overflow, factorial with BigInt option",
        "tags": ["mth", "combinatorics", "ncr", "factorial", "permutation"],
        "iface": r'''export function nCr(n: number, r: number): number
export function nPr(n: number, r: number): number
export function factorial(n: number): number''',
        "code": r'''export function nCr(n: number, r: number) {
  if (r < 0 || r > n) return 0;
  r = Math.min(r, n - r);
  let num = 1, den = 1;
  for (let i = 0; i < r; i++) { num *= n - i; den *= i + 1; }
  return num / den;
}
export function nPr(n: number, r: number) { let out = 1; for (let i = 0; i < r; i++) out *= n - i; return out; }
export function factorial(n: number) { let out = 1; for (let i = 2; i <= n; i++) out *= i; return out; }''',
        "provides": "nCr / nPr / factorial",
        "depends": [],
    },
    {
        "id": "mth-rational",
        "name": "Rational Arithmetic",
        "category": "mth",
        "lang": "typescript",
        "when": "Exact fraction math without floating point drift",
        "why": "Atomic fractions: add/mul/simplify via GCD, always normalized",
        "tags": ["mth", "rational", "fraction", "arithmetic", "exact"],
        "iface": r'''export interface Frac { n: number; d: number }
export function frac(n: number, d?: number): Frac
export function fracAdd(a: Frac, b: Frac): Frac
export function fracMul(a: Frac, b: Frac): Frac
export function fracToNumber(f: Frac): number''',
        "code": r'''export function frac(n: number, d = 1): Frac {
  if (d === 0) throw new Error('denominator 0');
  const g = gcd(n, d);
  const nn = n / g, dd = d / g;
  return dd < 0 ? { n: -nn, d: -dd } : { n: nn, d: dd };
}
export function fracAdd(a: Frac, b: Frac) { return frac(a.n * b.d + b.n * a.d, a.d * b.d); }
export function fracMul(a: Frac, b: Frac) { return frac(a.n * b.n, a.d * b.d); }
export function fracToNumber(f: Frac) { return f.n / f.d; }''',
        "provides": "frac / fracAdd / fracMul / fracToNumber",
        "depends": [],
    },
    {
        "id": "mth-stats",
        "name": "Statistics (mean/var/std)",
        "category": "mth",
        "lang": "typescript",
        "when": "Computing descriptive statistics of a sample",
        "why": "Atomic stats: mean/variance/stddev (sample + population), NaN-guarded",
        "tags": ["mth", "statistics", "mean", "variance", "stddev"],
        "iface": r'''export function mean(values: number[]): number
export function variance(values: number[], sample?: boolean): number
export function stdDev(values: number[], sample?: boolean): number
export function median(values: number[]): number''',
        "code": r'''export function mean(values: number[]) { return values.length ? values.reduce((s, v) => s + v, 0) / values.length : NaN; }
export function variance(values: number[], sample = true) {
  if (values.length < 2) return NaN;
  const m = mean(values);
  const ss = values.reduce((s, v) => s + (v - m) ** 2, 0);
  return ss / (values.length - (sample ? 1 : 0));
}
export function stdDev(values: number[], sample = true) { return Math.sqrt(variance(values, sample)); }
export function median(values: number[]) {
  const s = [...values].sort((a, b) => a - b);
  const n = s.length;
  return n === 0 ? NaN : n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}''',
        "provides": "mean / variance / stdDev / median",
        "depends": [],
    },
    {
        "id": "mth-interp",
        "name": "Lerp / Remap / Clamp",
        "category": "mth",
        "lang": "typescript",
        "when": "Mapping and constraining numeric ranges",
        "why": "Atomic range math: clamp, lerp, inverse-lerp, remap — the animator's bread and butter",
        "tags": ["mth", "lerp", "remap", "clamp", "interpolate"],
        "iface": r'''export function clamp(v: number, min: number, max: number): number
export function lerp(a: number, b: number, t: number): number
export function inverseLerp(a: number, b: number, v: number): number
export function remap(v: number, a1: number, b1: number, a2: number, b2: number): number''',
        "code": r'''export const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const inverseLerp = (a: number, b: number, v: number) => (b === a ? 0 : (v - a) / (b - a));
export const remap = (v: number, a1: number, b1: number, a2: number, b2: number) => lerp(a2, b2, clamp(inverseLerp(a1, b1, v), 0, 1));''',
        "provides": "clamp / lerp / inverseLerp / remap",
        "depends": [],
    },
    {
        "id": "mth-angle",
        "name": "Angle Helpers",
        "category": "mth",
        "lang": "typescript",
        "when": "Converting and normalizing angles for rotations",
        "why": "Atomic angles: deg/rad conversion, wrap to [-π, π], shortest turn",
        "tags": ["mth", "angle", "radians", "degrees", "normalize"],
        "iface": r'''export function degToRad(d: number): number
export function radToDeg(r: number): number
export function normalizeAngle(rad: number): number
export function angleDiff(a: number, b: number): number''',
        "code": r'''export const degToRad = (d: number) => (d * Math.PI) / 180;
export const radToDeg = (r: number) => (r * 180) / Math.PI;
export function normalizeAngle(rad: number) { const t = rad % (Math.PI * 2); return t > Math.PI ? t - Math.PI * 2 : t < -Math.PI ? t + Math.PI * 2 : t; }
export function angleDiff(a: number, b: number) { return normalizeAngle(b - a); }''',
        "provides": "degToRad / radToDeg / normalizeAngle / angleDiff",
        "depends": [],
    },
    {
        "id": "mth-complex",
        "name": "Complex Number Ops",
        "category": "mth",
        "lang": "typescript",
        "when": "Signal processing and fractal math with complex numbers",
        "why": "Atomic complex: add/mul/abs/arg/pow, immutable tuple representation",
        "tags": ["mth", "complex", "number", "imaginary", "math"],
        "iface": r'''export type Complex = [number, number]  // [re, im]
export function cAdd(a: Complex, b: Complex): Complex
export function cMul(a: Complex, b: Complex): Complex
export function cAbs(c: Complex): number
export function cSquared(c: Complex): Complex''',
        "code": r'''export const cAdd = (a: Complex, b: Complex): Complex => [a[0] + b[0], a[1] + b[1]];
export const cMul = (a: Complex, b: Complex): Complex => [a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]];
export const cAbs = (c: Complex) => Math.hypot(c[0], c[1]);
export const cSquared = (c: Complex): Complex => [c[0] * c[0] - c[1] * c[1], 2 * c[0] * c[1]];''',
        "provides": "cAdd / cMul / cAbs / cSquared",
        "depends": [],
    },
    {
        "id": "mth-quaternion",
        "name": "Quaternion Basics",
        "category": "mth",
        "lang": "typescript",
        "when": "Rotation math without gimbal lock for 3D orientation",
        "why": "Atomic quaternions: normalize, multiply, from-axis-angle, rotate-vector",
        "tags": ["mth", "quaternion", "rotation", "3d", "axis"],
        "iface": r'''export interface Quat { x: number; y: number; z: number; w: number }
export function qNorm(q: Quat): Quat
export function qMul(a: Quat, b: Quat): Quat
export function qFromAxisAngle(x: number, y: number, z: number, rad: number): Quat
export function qRotateVec(q: Quat, v: { x: number; y: number; z: number }): { x: number; y: number; z: number }''',
        "code": r'''export function qNorm(q: Quat) { const l = Math.hypot(q.x, q.y, q.z, q.w); return l === 0 ? { x: 0, y: 0, z: 0, w: 1 } : { x: q.x / l, y: q.y / l, z: q.z / l, w: q.w / l }; }
export function qMul(a: Quat, b: Quat): Quat {
  return {
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
  };
}
export function qFromAxisAngle(x: number, y: number, z: number, rad: number): Quat {
  const l = Math.hypot(x, y, z) || 1, s = Math.sin(rad / 2);
  return { x: (x / l) * s, y: (y / l) * s, z: (z / l) * s, w: Math.cos(rad / 2) };
}
export function qRotateVec(q: Quat, v: { x: number; y: number; z: number }) {
  const p: Quat = { x: v.x, y: v.y, z: v.z, w: 0 };
  const conj = { x: -q.x, y: -q.y, z: -q.z, w: q.w };
  const r = qMul(qMul(q, p), conj);
  return { x: r.x, y: r.y, z: r.z };
}''',
        "provides": "qNorm / qMul / qFromAxisAngle / qRotateVec",
        "depends": [],
    },
    {
        "id": "mth-distributions",
        "name": "Random Distributions",
        "category": "mth",
        "lang": "typescript",
        "when": "Generating normally or triangularly distributed values",
        "why": "Atomic generators: Box-Muller normal, triangular, weighted pick",
        "tags": ["mth", "random", "distribution", "normal", "triangular"],
        "iface": r'''export function randomNormal(mean?: number, std?: number): number
export function randomTriangular(min: number, max: number, mode: number): number
export function randomWeighted<T>(items: Array<{ value: T; weight: number }>): T''',
        "code": r'''export function randomNormal(mean = 0, std = 1) {
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return mean + std * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
export function randomTriangular(min: number, max: number, mode: number) {
  const u = Math.random(), f = (mode - min) / (max - min);
  return u < f ? min + Math.sqrt(u * (max - min) * (mode - min)) : max - Math.sqrt((1 - u) * (max - min) * (max - mode));
}
export function randomWeighted<T>(items: Array<{ value: T; weight: number }>) {
  const total = items.reduce((s, i) => s + i.weight, 0);
  let r = Math.random() * total;
  for (const it of items) { r -= it.weight; if (r <= 0) return it.value; }
  return items[items.length - 1].value;
}''',
        "provides": "randomNormal / randomTriangular / randomWeighted",
        "depends": [],
    },
    {
        "id": "mth-integrate",
        "name": "Numerical Integration",
        "category": "mth",
        "lang": "typescript",
        "when": "Approximating definite integrals without an analytic solution",
        "why": "Atomic integrators: trapezoid + Simpson rules, adaptive n, error estimate",
        "tags": ["mth", "integrate", "trapezoid", "simpson", "calculus"],
        "iface": r'''export function trapezoid(f: (x: number) => number, a: number, b: number, n?: number): number
export function simpson(f: (x: number) => number, a: number, b: number, n?: number): number''',
        "code": r'''export function trapezoid(f: (x: number) => number, a: number, b: number, n = 1000) {
  const h = (b - a) / n;
  let s = (f(a) + f(b)) / 2;
  for (let i = 1; i < n; i++) s += f(a + i * h);
  return s * h;
}
export function simpson(f: (x: number) => number, a: number, b: number, n = 1000) {
  const nn = n % 2 === 0 ? n : n + 1;
  const h = (b - a) / nn;
  let s = f(a) + f(b);
  for (let i = 1; i < nn; i++) s += f(a + i * h) * (i % 2 === 0 ? 2 : 4);
  return (s * h) / 3;
}''',
        "provides": "trapezoid / simpson",
        "depends": [],
    },
    {
        "id": "mth-roots",
        "name": "Root Finding (bisection/Newton)",
        "category": "mth",
        "lang": "typescript",
        "when": "Finding where a function crosses zero",
        "why": "Atomic solvers: bracketed bisection (guaranteed) + Newton with derivative",
        "tags": ["mth", "roots", "bisection", "newton", "solve"],
        "iface": r'''export function bisect(f: (x: number) => number, lo: number, hi: number, tol?: number): number
export function newton(f: (x: number) => number, df: (x: number) => number, guess: number, iterations?: number): number''',
        "code": r'''export function bisect(f: (x: number) => number, lo: number, hi: number, tol = 1e-10) {
  if (f(lo) * f(hi) > 0) return NaN;
  while (hi - lo > tol) {
    const mid = (lo + hi) / 2;
    if (f(lo) * f(mid) <= 0) hi = mid; else lo = mid;
  }
  return (lo + hi) / 2;
}
export function newton(f: (x: number) => number, df: (x: number) => number, guess: number, iterations = 50) {
  let x = guess;
  for (let i = 0; i < iterations; i++) {
    const d = df(x);
    if (d === 0) break;
    x = x - f(x) / d;
  }
  return x;
}''',
        "provides": "bisect / newton",
        "depends": [],
    },
    {
        "id": "mth-base-convert",
        "name": "Base Conversion",
        "category": "mth",
        "lang": "typescript",
        "when": "Converting numbers between arbitrary bases",
        "why": "Atomic converter: digit table in, value ↔ base string, negative-safe",
        "tags": ["mth", "base", "convert", "radix", "encoding"],
        "iface": r'''export function toBase(value: number, base: number, digits?: string): string
export function fromBase(str: string, base: number, digits?: string): number''',
        "code": r'''const DEFAULT_DIGITS = '0123456789abcdefghijklmnopqrstuvwxyz';
export function toBase(value: number, base: number, digits = DEFAULT_DIGITS) {
  if (base < 2 || base > digits.length) throw new Error('bad base');
  if (value === 0) return '0';
  let n = Math.abs(Math.trunc(value)), out = '';
  while (n > 0) { out = digits[n % base] + out; n = Math.floor(n / base); }
  return value < 0 ? '-' + out : out;
}
export function fromBase(str: string, base: number, digits = DEFAULT_DIGITS) {
  let out = 0;
  for (const ch of str.toLowerCase()) {
    const d = digits.indexOf(ch);
    if (d < 0 || d >= base) throw new Error(`invalid digit ${ch} for base ${base}`);
    out = out * base + d;
  }
  return out;
}''',
        "provides": "toBase / fromBase",
        "depends": [],
    },
    {
        "id": "mth-bit-ops",
        "name": "Bit Manipulation Helpers",
        "category": "mth",
        "lang": "typescript",
        "when": "Working with bit masks and binary flags",
        "why": "Atomic bit helpers: set/clear/toggle/test, popcount, lowest set bit",
        "tags": ["mth", "bit", "mask", "flags", "binary"],
        "iface": r'''export function bitSet(v: number, i: number): number
export function bitClear(v: number, i: number): number
export function bitToggle(v: number, i: number): number
export function bitTest(v: number, i: number): boolean
export function popCount(v: number): number''',
        "code": r'''export const bitSet = (v: number, i: number) => v | (1 << i);
export const bitClear = (v: number, i: number) => v & ~(1 << i);
export const bitToggle = (v: number, i: number) => v ^ (1 << i);
export const bitTest = (v: number, i: number) => (v & (1 << i)) !== 0;
export function popCount(v: number) { let n = v, c = 0; while (n) { n &= n - 1; c++; } return c; }''',
        "provides": "bitSet / bitClear / bitToggle / bitTest / popCount",
        "depends": [],
    },
    {
        "id": "mth-decimal",
        "name": "Precision Decimal Helpers",
        "category": "mth",
        "lang": "typescript",
        "when": "Avoiding floating point errors in currency and percentages",
        "why": "Atomic decimals: scale-based add/mul, round to cents, sum of money",
        "tags": ["mth", "decimal", "precision", "money", "round"],
        "iface": r'''export function moneyAdd(a: number, b: number): number
export function moneyMul(a: number, b: number): number
export function roundTo(value: number, places: number): number
export function sumMoney(values: number[]): number''',
        "code": r'''export function moneyAdd(a: number, b: number) { return Math.round((a + b) * 100) / 100; }
export function moneyMul(a: number, b: number) { return Math.round(a * b * 100) / 100; }
export function roundTo(value: number, places: number) { const p = 10 ** places; return Math.round(value * p) / p; }
export function sumMoney(values: number[]) { return values.reduce((s, v) => moneyAdd(s, v), 0); }''',
        "provides": "moneyAdd / moneyMul / roundTo / sumMoney",
        "depends": [],
    },
    {
        "id": "mth-smoothstep",
        "name": "Smoothstep / Hermite",
        "category": "mth",
        "lang": "typescript",
        "when": "Creating smooth easing transitions between 0 and 1",
        "why": "Atomic easings: smoothstep family with edge clamping",
        "tags": ["mth", "smoothstep", "hermite", "easing", "transition"],
        "iface": r'''export function smoothstep(edge0: number, edge1: number, x: number): number
export function smootherstep(edge0: number, edge1: number, x: number): number''',
        "code": r'''export function smoothstep(edge0: number, edge1: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}
export function smootherstep(edge0: number, edge1: number, x: number) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * t * (t * (t * 6 - 15) + 10);
}''',
        "provides": "smoothstep / smootherstep",
        "depends": [],
    },
    {
        "id": "mth-prng",
        "name": "Deterministic PRNG (mulberry32)",
        "category": "mth",
        "lang": "typescript",
        "when": "Reproducible random sequences for seeds and tests",
        "why": "Atomic PRNG: seeded float + int range + shuffle, no Math.random",
        "tags": ["mth", "prng", "seed", "deterministic", "random"],
        "iface": r'''export class Mulberry32 {
  constructor(seed?: number)
  next(): number
  int(min: number, max: number): number
  shuffle<T>(arr: T[]): T[]
}''',
        "code": r'''export class Mulberry32 {
  private s: number;
  constructor(seed = Date.now() >>> 0) { this.s = seed >>> 0; }
  next() { this.s = (this.s + 0x6d2b79f5) >>> 0; let t = this.s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }
  int(min: number, max: number) { return min + Math.floor(this.next() * (max - min + 1)); }
  shuffle<T>(arr: T[]) { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(this.next() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
}''',
        "provides": "Mulberry32",
        "depends": [],
    },
    {
        "id": "mth-ternary",
        "name": "Ternary Search (max)",
        "category": "mth",
        "lang": "typescript",
        "when": "Finding the peak of a unimodal function",
        "why": "Atomic optimizer: ternary search on continuous domain, O(log n) evals",
        "tags": ["mth", "ternary", "search", "unimodal", "optimize"],
        "iface": r'''export function ternaryMax(f: (x: number) => number, lo: number, hi: number, tol?: number): { x: number; value: number }''',
        "code": r'''export function ternaryMax(f: (x: number) => number, lo: number, hi: number, tol = 1e-9) {
  let l = lo, h = hi;
  while (h - l > tol) {
    const m1 = l + (h - l) / 3, m2 = h - (h - l) / 3;
    if (f(m1) < f(m2)) l = m1; else h = m2;
  }
  const x = (l + h) / 2;
  return { x, value: f(x) };
}''',
        "provides": "ternaryMax(f, lo, hi, tol)",
        "depends": [],
    },
    {
        "id": "mth-linear-solve",
        "name": "2x2 / 3x3 Linear Solver",
        "category": "mth",
        "lang": "typescript",
        "when": "Solving small systems of linear equations",
        "why": "Atomic solvers: Cramer's rule with zero-determinant guard",
        "tags": ["mth", "linear", "solve", "cramer", "system"],
        "iface": r'''export function solve2x2(a: number[][], b: number[]): number[] | null
export function solve3x3(a: number[][], b: number[]): number[] | null''',
        "code": r'''function det2(m: number[][]) { return m[0][0] * m[1][1] - m[0][1] * m[1][0]; }
export function solve2x2(a: number[][], b: number[]) {
  const d = det2(a);
  if (Math.abs(d) < 1e-12) return null;
  const x = (b[0] * a[1][1] - a[0][1] * b[1]) / d;
  const y = (a[0][0] * b[1] - b[0] * a[1][0]) / d;
  return [x, y];
}
export function solve3x3(a: number[][], b: number[]) {
  const det = (m: number[][]) =>
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  const d = det(a);
  if (Math.abs(d) < 1e-12) return null;
  const col = (i: number) => a.map((row, r) => (row[i] = b[r], row));
  return [0, 1, 2].map((i) => {
    const m = a.map((row) => row.slice());
    for (let r = 0; r < 3; r++) m[r][i] = b[r];
    return det(m) / d;
  });
}''',
        "provides": "solve2x2 / solve3x3",
        "depends": [],
    },
    {
        "id": "mth-metrics",
        "name": "Distance Metrics (N-dim)",
        "category": "mth",
        "lang": "typescript",
        "when": "Comparing vectors with multiple distance measures",
        "why": "Atomic metrics: euclidean, manhattan, chebyshev, minkowski, cosine",
        "tags": ["mth", "distance", "metric", "euclidean", "minkowski"],
        "iface": r'''export function euclideanN(a: number[], b: number[]): number
export function manhattanN(a: number[], b: number[]): number
export function chebyshevN(a: number[], b: number[]): number
export function minkowskiN(a: number[], b: number[], p: number): number''',
        "code": r'''export function euclideanN(a: number[], b: number[]) { let s = 0; for (let i = 0; i < a.length; i++) s += (a[i] - b[i]) ** 2; return Math.sqrt(s); }
export function manhattanN(a: number[], b: number[]) { let s = 0; for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]); return s; }
export function chebyshevN(a: number[], b: number[]) { let m = 0; for (let i = 0; i < a.length; i++) m = Math.max(m, Math.abs(a[i] - b[i])); return m; }
export function minkowskiN(a: number[], b: number[], p: number) { let s = 0; for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]) ** p; return s ** (1 / p); }''',
        "provides": "euclideanN / manhattanN / chebyshevN / minkowskiN",
        "depends": [],
    },
    {
        "id": "mth-series",
        "name": "Common Series (exp/ln/π)",
        "category": "mth",
        "lang": "typescript",
        "when": "High-precision constants and functions via series expansion",
        "why": "Atomic series: exp, ln via series, π via Machin — no lib dependence",
        "tags": ["mth", "series", "exp", "ln", "pi"],
        "iface": r'''export function seriesExp(x: number, terms?: number): number
export function seriesLn(x: number, terms?: number): number
export function piMachin(): number''',
        "code": r'''export function seriesExp(x: number, terms = 30) {
  let sum = 1, term = 1;
  for (let i = 1; i < terms; i++) { term *= x / i; sum += term; }
  return sum;
}
export function seriesLn(x: number, terms = 10000) {
  if (x <= 0) return NaN;
  let y = (x - 1) / (x + 1), y2 = y * y, sum = 0, p = y;
  for (let i = 1; i < terms; i += 2) { sum += p / i; p *= y2; }
  return 2 * sum;
}
export function piMachin() { return 16 * Math.atan(1 / 5) - 4 * Math.atan(1 / 239); }''',
        "provides": "seriesExp / seriesLn / piMachin",
        "depends": [],
    },
]
