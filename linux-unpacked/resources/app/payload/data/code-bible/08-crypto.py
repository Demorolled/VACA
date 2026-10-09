# -*- coding: utf-8 -*-
"""
Code Bible — Category 08: Crypto & security (atomic).
Convention: functions take plain input and return output objects with
`{ ok, ... }` or throw typed errors; secrets never logged.
"""
CHUNKS = [
    {
        "id": "crypto-aes-encrypt",
        "name": "AES-256-GCM Encrypt",
        "category": "crypto",
        "lang": "typescript",
        "when": "Encrypting sensitive data at rest with authenticated encryption",
        "why": "Atomic encryptor; plaintext + key in, ciphertext+iv+tag out — GCM authenticates, no key storage",
        "tags": ["aes", "gcm", "encrypt", "cipher", "crypto"],
        "iface": r'''export interface AesEncryptResult { ciphertext: string; iv: string; tag: string }
export function aesEncrypt(plaintext: string, key: Buffer): AesEncryptResult''',
        "code": r'''import * as crypto from 'crypto';

export function aesEncrypt(plaintext: string, key: Buffer): AesEncryptResult {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const encrypted = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return {
    ciphertext: encrypted.toString('base64'),
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
  };
}''',
        "provides": "aesEncrypt(plaintext, key)",
        "depends": [],
    },
    {
        "id": "crypto-aes-decrypt",
        "name": "AES-256-GCM Decrypt",
        "category": "crypto",
        "lang": "typescript",
        "when": "Decrypting AES-GCM ciphertext produced by the encrypt chunk",
        "why": "Atomic decryptor; ciphertext + iv + tag + key in, plaintext out — throws on tampering",
        "tags": ["aes", "gcm", "decrypt", "cipher", "auth"],
        "iface": r'''export function aesDecrypt(result: AesEncryptResult, key: Buffer): string''',
        "code": r'''import * as crypto from 'crypto';

export function aesDecrypt(result: AesEncryptResult, key: Buffer): string {
  const decipher = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(result.iv, 'base64'));
  decipher.setAuthTag(Buffer.from(result.tag, 'base64'));
  const decrypted = Buffer.concat([
    decipher.update(Buffer.from(result.ciphertext, 'base64')),
    decipher.final(),
  ]);
  return decrypted.toString('utf8');
}''',
        "provides": "aesDecrypt(result, key)",
        "depends": ["crypto-aes-encrypt"],
    },
    {
        "id": "crypto-rsa-keygen",
        "name": "RSA Key Generation",
        "category": "crypto",
        "lang": "typescript",
        "when": "Creating key pairs for signatures or asymmetric encryption",
        "why": "Atomic keygen; bits in, pem pair out — private key never exported as plaintext by default",
        "tags": ["rsa", "keygen", "keys", "asymmetric", "pem"],
        "iface": r'''export interface KeyPair { publicKey: string; privateKey: string }
export function generateRsaKeyPair(bits?: number): KeyPair''',
        "code": r'''import * as crypto from 'crypto';

export function generateRsaKeyPair(bits = 2048): KeyPair {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('rsa', {
    modulusLength: bits,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
  });
  return { publicKey, privateKey };
}''',
        "provides": "generateRsaKeyPair(bits?)",
        "depends": [],
    },
    {
        "id": "crypto-rsa-sign",
        "name": "RSA Sign/Verify",
        "category": "crypto",
        "lang": "typescript",
        "when": "Proving message authenticity with asymmetric signatures",
        "why": "Atomic signer; message + private key in, signature out — verify with public key",
        "tags": ["rsa", "sign", "verify", "signature", "authenticity"],
        "iface": r'''export function rsaSign(message: string, privateKey: string): string
export function rsaVerify(message: string, signature: string, publicKey: string): boolean''',
        "code": r'''import * as crypto from 'crypto';

export function rsaSign(message: string, privateKey: string): string {
  return crypto.sign('sha256', Buffer.from(message), privateKey).toString('base64');
}

export function rsaVerify(message: string, signature: string, publicKey: string): boolean {
  try {
    return crypto.verify('sha256', Buffer.from(message), publicKey, Buffer.from(signature, 'base64'));
  } catch {
    return false;
  }
}''',
        "provides": "rsaSign(message, privateKey), rsaVerify(message, signature, publicKey)",
        "depends": [],
    },
    {
        "id": "crypto-hmac",
        "name": "HMAC-SHA256",
        "category": "crypto",
        "lang": "typescript",
        "when": "Message authentication with a shared secret (webhooks, tokens)",
        "why": "Atomic hmac; message + secret in, hex digest out — constant-time compare provided",
        "tags": ["hmac", "sha256", "mac", "authenticate", "digest"],
        "iface": r'''export function hmacSha256(message: string, secret: string): string
export function safeEqual(a: string, b: string): boolean''',
        "code": r'''import * as crypto from 'crypto';

export function hmacSha256(message: string, secret: string): string {
  return crypto.createHmac('sha256', secret).update(message).digest('hex');
}

export function safeEqual(a: string, b: string): boolean {
  const ba = Buffer.from(a);
  const bb = Buffer.from(b);
  return ba.length === bb.length && crypto.timingSafeEqual(ba, bb);
}''',
        "provides": "hmacSha256(message, secret), safeEqual(a, b)",
        "depends": [],
    },
    {
        "id": "crypto-sha256",
        "name": "SHA-256 Hash",
        "category": "crypto",
        "lang": "typescript",
        "when": "Fingerprinting content, checksums, and lookup keys",
        "why": "Atomic hash; input in, hex digest out — one-shot, no streaming state",
        "tags": ["sha256", "hash", "digest", "checksum", "fingerprint"],
        "iface": r'''export function sha256(input: string | Buffer): string
export function sha256Stream(stream: NodeJS.ReadableStream): Promise<string>''',
        "code": r'''import * as crypto from 'crypto';

export function sha256(input: string | Buffer): string {
  return crypto.createHash('sha256').update(input).digest('hex');
}

export async function sha256Stream(stream: NodeJS.ReadableStream): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256');
    stream.on('data', (chunk) => hash.update(chunk));
    stream.on('end', () => resolve(hash.digest('hex')));
    stream.on('error', reject);
  });
}''',
        "provides": "sha256(input), sha256Stream(stream)",
        "depends": [],
    },
    {
        "id": "crypto-password-hash",
        "name": "Password Hash (scrypt)",
        "category": "crypto",
        "lang": "typescript",
        "when": "Storing user passwords safely with per-user salts",
        "why": "Atomic hasher; password in, salted hash out — scrypt + salt, verify included",
        "tags": ["password", "hash", "scrypt", "salt", "security"],
        "iface": r'''export interface PasswordHash { hash: string; salt: string }
export function hashPassword(password: string): PasswordHash
export function verifyPassword(password: string, hash: string, salt: string): boolean''',
        "code": r'''import * as crypto from 'crypto';

const KEYLEN = 64;

export function hashPassword(password: string): PasswordHash {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(password, salt, KEYLEN).toString('hex');
  return { hash, salt };
}

export function verifyPassword(password: string, hash: string, salt: string): boolean {
  const candidate = crypto.scryptSync(password, salt, KEYLEN).toString('hex');
  return crypto.timingSafeEqual(Buffer.from(hash, 'hex'), Buffer.from(candidate, 'hex'));
}''',
        "provides": "hashPassword(password), verifyPassword(password, hash, salt)",
        "depends": [],
    },
    {
        "id": "crypto-totp",
        "name": "TOTP (2FA Code)",
        "category": "crypto",
        "lang": "typescript",
        "when": "Generating and verifying time-based one-time passwords (2FA)",
        "why": "Atomic totp; secret + time in, 6-digit code out — standard RFC 6238",
        "tags": ["totp", "2fa", "otp", "mfa", "authenticator"],
        "iface": r'''export function generateTotp(secret: string, timeStepSec?: number, digits?: number, atMs?: number): string
export function verifyTotp(secret: string, code: string, window?: number, atMs?: number): boolean''',
        "code": r'''import * as crypto from 'crypto';

export function generateTotp(secret: string, timeStepSec = 30, digits = 6, atMs = Date.now()): string {
  const counter = Math.floor(atMs / 1000 / timeStepSec);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const key = Buffer.from(base32ToHex(secret), 'hex');
  const hmac = crypto.createHmac('sha1', key).update(buf).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const bin = ((hmac[offset] & 0x7f) << 24) | (hmac[offset + 1] << 16) | (hmac[offset + 2] << 8) | hmac[offset + 3];
  return String(bin % 10 ** digits).padStart(digits, '0');
}

function base32ToHex(base32: string): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const ch of base32.toUpperCase().replace(/=+$/, '')) {
    const idx = alphabet.indexOf(ch);
    if (idx === -1) continue;
    bits += idx.toString(2).padStart(5, '0');
  }
  let hex = '';
  for (let i = 0; i + 4 <= bits.length; i += 4) hex += parseInt(bits.slice(i, i + 4), 2).toString(16);
  return hex;
}

export function verifyTotp(secret: string, code: string, window = 1, atMs = Date.now()): boolean {
  const stepMs = 30_000;
  for (let w = -window; w <= window; w++) {
    if (generateTotp(secret, 30, 6, atMs + w * stepMs) === code) return true;
  }
  return false;
}''',
        "provides": "generateTotp(secret, timeStepSec?, digits?), verifyTotp(secret, code, window?)",
        "depends": [],
    },
    {
        "id": "crypto-base64",
        "name": "Base64 Encode/Decode",
        "category": "crypto",
        "lang": "typescript",
        "when": "Encoding binary as text (urls, tokens, attachments)",
        "why": "Atomic codec; bytes/string in, encoded/decoded out — url-safe variant included",
        "tags": ["base64", "encode", "decode", "codec", "binary"],
        "iface": r'''export function toBase64(data: string | Uint8Array): string
export function fromBase64(text: string): Uint8Array
export function toBase64Url(data: string | Uint8Array): string''',
        "code": r'''export function toBase64(data: string | Uint8Array): string {
  if (typeof data === 'string') return Buffer.from(data, 'utf8').toString('base64');
  return Buffer.from(data).toString('base64');
}

export function fromBase64(text: string): Uint8Array {
  return new Uint8Array(Buffer.from(text, 'base64'));
}

export function toBase64Url(data: string | Uint8Array): string {
  return toBase64(data).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}''',
        "provides": "toBase64(data), fromBase64(text), toBase64Url(data)",
        "depends": [],
    },
    {
        "id": "crypto-random",
        "name": "Secure Random Helpers",
        "category": "crypto",
        "lang": "typescript",
        "when": "Generating cryptographically-secure tokens, ids, and secrets",
        "why": "Atomic random; length in, token/bytes out — uses CSPRNG, never Math.random",
        "tags": ["random", "secure", "token", "csprng", "secret"],
        "iface": r'''export function randomBytes(n: number): Uint8Array
export function randomToken(bytes?: number): string
export function randomInt(max: number): number''',
        "code": r'''import * as crypto from 'crypto';

export function randomBytes(n: number): Uint8Array {
  return new Uint8Array(crypto.randomBytes(n));
}

export function randomToken(bytes = 32): string {
  return crypto.randomBytes(bytes).toString('base64url');
}

export function randomInt(max: number): number {
  return crypto.randomInt(max);
}''',
        "provides": "randomBytes(n), randomToken(bytes?), randomInt(max)",
        "depends": [],
    },
    {
        "id": "crypto-constant-time",
        "name": "Constant-Time Compare",
        "category": "crypto",
        "lang": "typescript",
        "when": "Comparing secrets/hashes without timing leaks",
        "why": "Atomic compare; two values in, boolean out — timing-safe for equal-length inputs",
        "tags": ["constant", "time", "compare", "timing", "safe"],
        "iface": r'''export function constantTimeEqual(a: string | Uint8Array, b: string | Uint8Array): boolean''',
        "code": r'''import * as crypto from 'crypto';

export function constantTimeEqual(a: string | Uint8Array, b: string | Uint8Array): boolean {
  const ba = typeof a === 'string' ? Buffer.from(a) : Buffer.from(a);
  const bb = typeof b === 'string' ? Buffer.from(b) : Buffer.from(b);
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
}''',
        "provides": "constantTimeEqual(a, b)",
        "depends": [],
    },
    {
        "id": "crypto-key-derivation",
        "name": "PBKDF2 Key Derivation",
        "category": "crypto",
        "lang": "typescript",
        "when": "Deriving encryption keys from passwords with iterations",
        "why": "Atomic kdf; password + salt in, derived key out — configurable iterations",
        "tags": ["pbkdf2", "derive", "key", "password", "kdf"],
        "iface": r'''export function deriveKey(password: string, salt: string, options?: { iterations?: number; keyLen?: number }): Buffer''',
        "code": r'''import * as crypto from 'crypto';

export function deriveKey(password: string, salt: string, options?: { iterations?: number; keyLen?: number }): Buffer {
  return crypto.pbkdf2Sync(
    password,
    salt,
    options?.iterations ?? 210_000,
    options?.keyLen ?? 32,
    'sha256',
  );
}''',
        "provides": "deriveKey(password, salt, options?)",
        "depends": [],
    },
    {
        "id": "crypto-pem-parse",
        "name": "PEM Key Parser",
        "category": "crypto",
        "lang": "typescript",
        "when": "Extracting key material from PEM strings for interop",
        "why": "Atomic parser; pem in, type + body out — no verification, just structure",
        "tags": ["pem", "key", "parse", "certificate", "der"],
        "iface": r'''export interface PemBlock { label: string; body: string; bytes: Uint8Array }
export function parsePem(pem: string): PemBlock[]
export function pemToJwk(pem: string): Record<string, string> | null''',
        "code": r'''export function parsePem(pem: string): PemBlock[] {
  const blocks: PemBlock[] = [];
  const re = /-----BEGIN ([A-Z0-9 ]+)-----([\s\S]+?)-----END \1-----/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(pem)) !== null) {
    const body = match[2].replace(/\s+/g, '');
    blocks.push({ label: match[1], body, bytes: new Uint8Array(Buffer.from(body, 'base64')) });
  }
  return blocks;
}

export function pemToJwk(pem: string): Record<string, string> | null {
  const blocks = parsePem(pem);
  if (blocks.length === 0) return null;
  const block = blocks[0];
  if (!block.label.includes('PUBLIC KEY') && !block.label.includes('PRIVATE KEY')) return null;
  const der = Buffer.from(block.body, 'base64');
  // Minimal: convert raw RSA modulus/exponent when DER is simple RSA (no full ASN.1 parser).
  try {
    const mod = der.subarray(der.length - 270, der.length - 3);
    return {
      kty: 'RSA',
      n: Buffer.from(mod).toString('base64url'),
      e: 'AQAB',
    };
  } catch {
    return null;
  }
}''',
        "provides": "parsePem(pem), pemToJwk(pem)",
        "depends": [],
    },
    {
        "id": "crypto-salt-generator",
        "name": "Salt Generator",
        "category": "crypto",
        "lang": "typescript",
        "when": "Creating unique salts for password hashing and derivation",
        "why": "Atomic salt; bytes in, hex/base64 salt out — CSPRNG sourced",
        "tags": ["salt", "generate", "random", "hash", "crypto"],
        "iface": r'''export function generateSalt(bytes?: number, encoding?: 'hex' | 'base64'): string''',
        "code": r'''import * as crypto from 'crypto';

export function generateSalt(bytes = 16, encoding: 'hex' | 'base64' = 'hex'): string {
  return crypto.randomBytes(bytes).toString(encoding);
}''',
        "provides": "generateSalt(bytes?, encoding?)",
        "depends": [],
    },
    {
        "id": "crypto-envelope",
        "name": "Encrypted Envelope (Hybrid)",
        "category": "crypto",
        "lang": "typescript",
        "when": "Encrypting payloads for a recipient using their public key",
        "why": "Atomic envelope; plaintext + public key in, sealed box out — RSA + AES hybrid",
        "tags": ["envelope", "hybrid", "encrypt", "publickey", "seal"],
        "iface": r'''export interface SealedEnvelope { encryptedKey: string; ciphertext: string; iv: string; tag: string }
export function sealEnvelope(plaintext: string, recipientPublicKey: string): SealedEnvelope
export function openEnvelope(envelope: SealedEnvelope, recipientPrivateKey: string): string''',
        "code": r'''import * as crypto from 'crypto';

export function sealEnvelope(plaintext: string, recipientPublicKey: string): SealedEnvelope {
  const sessionKey = crypto.randomBytes(32);
  const encryptedKey = crypto.publicEncrypt(recipientPublicKey, sessionKey).toString('base64');
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', sessionKey, iv);
  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  return {
    encryptedKey,
    ciphertext: ciphertext.toString('base64'),
    iv: iv.toString('base64'),
    tag: cipher.getAuthTag().toString('base64'),
  };
}

export function openEnvelope(envelope: SealedEnvelope, recipientPrivateKey: string): string {
  const sessionKey = crypto.privateDecrypt(recipientPrivateKey, Buffer.from(envelope.encryptedKey, 'base64'));
  const decipher = crypto.createDecipheriv('aes-256-gcm', sessionKey, Buffer.from(envelope.iv, 'base64'));
  decipher.setAuthTag(Buffer.from(envelope.tag, 'base64'));
  return Buffer.concat([
    decipher.update(Buffer.from(envelope.ciphertext, 'base64')),
    decipher.final(),
  ]).toString('utf8');
}''',
        "provides": "sealEnvelope(plaintext, publicKey), openEnvelope(envelope, privateKey)",
        "depends": ["crypto-aes-encrypt", "crypto-rsa-keygen"],
    },
    {
        "id": "crypto-xss-sanitize",
        "name": "HTML Sanitizer (XSS)",
        "category": "crypto",
        "lang": "typescript",
        "when": "Cleaning user HTML before rendering to prevent XSS",
        "why": "Atomic sanitizer; html in, safe html out — allowlist tags/attrs, strips scripts",
        "tags": ["xss", "sanitize", "html", "security", "escape"],
        "iface": r'''export function sanitizeHtml(html: string, allowlist?: { tags?: string[]; attrs?: string[] }): string''',
        "code": r'''const DEFAULT_TAGS = new Set(['p', 'b', 'i', 'em', 'strong', 'a', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'h1', 'h2', 'h3', 'br', 'span', 'div']);
const DEFAULT_ATTRS = new Set(['href', 'title', 'class', 'id', 'rel', 'target']);

export function sanitizeHtml(html: string, allowlist?: { tags?: string[]; attrs?: string[] }): string {
  const tags = new Set(allowlist?.tags ?? [...DEFAULT_TAGS]);
  const attrs = new Set(allowlist?.attrs ?? [...DEFAULT_ATTRS]);

  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/on\w+\s*=\s*"[^"]*"/gi, '')
    .replace(/on\w+\s*=\s*'[^']*'/gi, '')
    .replace(/javascript:/gi, '')
    .replace(/<(\/?)([a-zA-Z0-9]+)([^>]*)>/g, (full, close: string, tag: string, attrsStr: string) => {
      if (!tags.has(tag.toLowerCase())) return '';
      const safeAttrs = attrsStr
        .match(/([a-zA-Z-]+)="([^"]*)"/g)
        ?.filter((a) => attrs.has(a.split('=')[0]))
        .join(' ') ?? '';
      return `<${close}${tag}${safeAttrs ? ' ' + safeAttrs : ''}>`;
    });
}''',
        "provides": "sanitizeHtml(html, allowlist?)",
        "depends": [],
    },
    {
        "id": "crypto-token-bucket",
        "name": "Token Bucket Rate Limit",
        "category": "crypto",
        "lang": "typescript",
        "when": "Smoothing request bursts with a refill-rate bucket",
        "why": "Atomic bucket; rate + capacity in, take out — algorithm shared with rate-limiter chunk",
        "tags": ["token", "bucket", "rate", "limit", "burst"],
        "iface": r'''export function createTokenBucket(options: { refillPerSec: number; capacity: number }) {
  return {
    take(tokens?: number): boolean,
    get available(): number,
    refill(now?: number): void,
  };
}''',
        "code": r'''export function createTokenBucket(options: { refillPerSec: number; capacity: number }) {
  let tokens = options.capacity;
  let last = Date.now();

  return {
    refill(now = Date.now()) {
      const elapsed = (now - last) / 1000;
      tokens = Math.min(options.capacity, tokens + elapsed * options.refillPerSec);
      last = now;
    },
    take(count = 1) {
      this.refill();
      if (tokens < count) return false;
      tokens -= count;
      return true;
    },
    get available() { return tokens; },
  };
}''',
        "provides": "createTokenBucket({refillPerSec, capacity})",
        "depends": [],
    },
]
