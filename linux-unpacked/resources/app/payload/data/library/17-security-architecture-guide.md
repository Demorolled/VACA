# 🔒 Security Architecture Guide

> Reference for building secure applications — threat modeling, secure design principles, authentication, and common protections.
> Extracted from The Programming Bible's Security and Cryptography levels.

---

## 1. Security Mindset

### Core Principles

| Principle | Description |
|---|---|
| **Defense in Depth** | Multiple layers of security — if one fails, others still protect |
| **Least Privilege** | Only grant the minimum permissions needed |
| **Secure by Default** | Default configuration should be secure |
| **Fail Secure** | On failure, deny access (not grant it) |
| **Complete Mediation** | Every access attempt must be checked |
| **Economy of Mechanism** | Keep the design simple — complexity hides flaws |
| **Open Design** | Security shouldn't depend on secrecy of the design |
| **Psychological Acceptability** | Security should be easy for users to follow |

### Threat Modeling Process

```
1. Define Scope
   ├── What are we protecting?
   ├── Who are the attackers?
   └── What's the threat model?

2. Decompose the System
   ├── Identify trust boundaries
   ├── Map data flows (DFD)
   └── Identify entry points

3. Identify Threats (STRIDE)
   ├── Spoofing — Impersonating someone/something
   ├── Tampering — Modifying data or code
   ├── Repudiation — Denying actions
   ├── Information Disclosure — Exposing protected data
   ├── Denial of Service — Making system unavailable
   └── Elevation of Privilege — Gaining unauthorized access

4. Rank Threats (DREAD)
   ├── Damage potential
   ├── Reproducibility
   ├── Exploitability
   ├── Affected users
   └── Discoverability

5. Define Mitigations
   └── For each threat, determine how to prevent/detect/respond

6. Validate Mitigations
   └── Test that mitigations are effective
```

---

## 2. Application Security Controls

### OWASP ASVS Levels

| Level | Description | Required For |
|---|---|---|
| **L1** | Essential security controls | All applications |
| **L2** | Sensitive data protection | Apps handling PII, financial data |
| **L3** | High-security applications | Healthcare, critical infrastructure, defense |

### Standard Security Controls

```typescript
// Application Security Control Template
interface SecurityControl {
  id: string;           // e.g., 'AUTH-01'
  category: string;     // e.g., 'Authentication'
  description: string;
  asvsLevel: 1 | 2 | 3;
  implemented: boolean;
  verified: boolean;
}

const standardControls: SecurityControl[] = [
  // Authentication
  { id: 'AUTH-01', category: 'Authentication', description: 'Password minimum length 8+', asvsLevel: 1, implemented: false, verified: false },
  { id: 'AUTH-02', category: 'Authentication', description: 'Rate-limit login attempts', asvsLevel: 1, implemented: false, verified: false },
  { id: 'AUTH-03', category: 'Authentication', description: 'MFA for high-value accounts', asvsLevel: 2, implemented: false, verified: false },

  // Access Control
  { id: 'AC-01', category: 'Access Control', description: 'Server-side authorization on all endpoints', asvsLevel: 1, implemented: false, verified: false },
  { id: 'AC-02', category: 'Access Control', description: 'Deny by default, whitelist access', asvsLevel: 1, implemented: false, verified: false },

  // Input Validation
  { id: 'VAL-01', category: 'Input Validation', description: 'Validate all input with schema/type checks', asvsLevel: 1, implemented: false, verified: false },
  { id: 'VAL-02', category: 'Input Validation', description: 'Encode output to prevent XSS', asvsLevel: 1, implemented: false, verified: false },
  { id: 'VAL-03', category: 'Input Validation', description: 'Parameterized queries for all SQL', asvsLevel: 1, implemented: false, verified: false },

  // Cryptography
  { id: 'CRYPTO-01', category: 'Cryptography', description: 'Use TLS 1.2+ for transport', asvsLevel: 1, implemented: false, verified: false },
  { id: 'CRYPTO-02', category: 'Cryptography', description: 'Hash passwords with bcrypt/argon2', asvsLevel: 1, implemented: false, verified: false },
  { id: 'CRYPTO-03', category: 'Cryptography', description: 'Use authenticated encryption (AES-GCM)', asvsLevel: 2, implemented: false, verified: false },
  
  // Logging & Monitoring
  { id: 'LOG-01', category: 'Logging', description: 'Log all authentication attempts', asvsLevel: 1, implemented: false, verified: false },
  { id: 'LOG-02', category: 'Logging', description: 'Log access control failures', asvsLevel: 1, implemented: false, verified: false },
  { id: 'LOG-03', category: 'Logging', description: 'Monitor for anomalous activity', asvsLevel: 2, implemented: false, verified: false },
];
```

---

## 3. Authentication & Session Management

### Password Handling

```typescript
// ✅ GOOD: Hash passwords with bcrypt
import bcrypt from 'bcrypt';

const SALT_ROUNDS = 12;

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, SALT_ROUNDS);
}

export async function verifyPassword(password: string, hash: string): Promise<boolean> {
  return bcrypt.compare(password, hash);
}

// ❌ BAD: Never do this
function hashPassword_bad(password: string): string {
  return crypto.createHash('md5').update(password).digest('hex'); // MD5 + no salt!
}
```

### JWT Session Pattern

```typescript
import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET!; // Must be 256-bit+ random
const ACCESS_TOKEN_TTL = '15m';
const REFRESH_TOKEN_TTL = '7d';

interface TokenPayload {
  userId: number;
  role: 'user' | 'admin';
}

export function generateTokens(payload: TokenPayload): { accessToken: string; refreshToken: string } {
  const accessToken = jwt.sign(payload, JWT_SECRET, { expiresIn: ACCESS_TOKEN_TTL });
  const refreshToken = jwt.sign(
    { ...payload, type: 'refresh' },
    JWT_SECRET,
    { expiresIn: REFRESH_TOKEN_TTL }
  );
  return { accessToken, refreshToken };
}

export function verifyToken(token: string): TokenPayload {
  try {
    return jwt.verify(token, JWT_SECRET) as TokenPayload;
  } catch (err) {
    if (err instanceof jwt.TokenExpiredError) {
      throw new AppError('Token expired', 'ERR_TOKEN_EXPIRED');
    }
    throw new AppError('Invalid token', 'ERR_TOKEN_INVALID');
  }
}
```

### Session Security Checklist

- [ ] Tokens expire after reasonable TTL (15-60 minutes)
- [ ] Refresh tokens are rotated on each use
- [ ] Old refresh tokens are invalidated on password change
- [ ] Sessions are invalidated server-side on logout
- [ ] Rate limit login attempts (5 failed = 15-min lockout)
- [ ] No sensitive data in JWT payload (user IDs are fine, passwords are not)
- [ ] Use `httpOnly`, `secure`, `sameSite=strict` cookies for web apps

---

## 4. Input Validation & Injection Prevention

### SQL Injection Prevention

```typescript
// ✅ GOOD: Parameterized queries
const stmt = db.prepare('SELECT * FROM users WHERE email = ?');
const user = stmt.get(email);

// ✅ GOOD: Named parameters
const stmt = db.prepare('SELECT * FROM users WHERE id = @id AND active = @active');
const user = stmt.get({ id: userId, active: true });

// ❌ BAD: String interpolation
const query = `SELECT * FROM users WHERE email = '${email}'`; // SQL injection!
```

### XSS Prevention

```typescript
// ✅ GOOD: Encode output context
function encodeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ✅ GOOD: Use safe React patterns
function UserProfile({ user }: { user: User }) {
  // React auto-escapes JSX expressions
  return <div>{user.name}</div>; // Safe
  // ❌ Don't: dangerouslySetInnerHTML={{ __html: user.bio }}
}

// ✅ GOOD: Content-Security-Policy header
app.use((req, res, next) => {
  res.setHeader(
    'Content-Security-Policy',
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
  );
  next();
});
```

### Path Traversal Prevention

```typescript
// ✅ GOOD: Sanitize file paths
import path from 'path';
import fs from 'fs';

const ALLOWED_DIR = path.resolve('./uploads');

function safeReadFile(userPath: string): Buffer {
  const resolved = path.resolve(ALLOWED_DIR, userPath);
  
  // Prevent path traversal
  if (!resolved.startsWith(ALLOWED_DIR)) {
    throw new AppError('Invalid path', 'ERR_PATH_TRAVERSAL');
  }
  
  return fs.readFileSync(resolved);
}

// ❌ BAD: Direct user input as path
const content = fs.readFileSync(userPath); // ../../../etc/passwd
```

---

## 5. Common Security Controls Checklist

### API Security

- [ ] Rate limiting on all endpoints (express-rate-limit)
- [ ] CORS configured for specific origins, not `*`
- [ ] Request size limits (body-parser `limit` option)
- [ ] HTTP security headers set (Helmet middleware)
- [ ] API keys/credentials not in source code (environment variables)
- [ ] Logging of all security-relevant events
- [ ] Input validation at every API boundary

### Data Protection

- [ ] All passwords hashed with bcrypt/argon2
- [ ] All PII encrypted at rest (AES-256-GCM)
- [ ] All data encrypted in transit (TLS 1.2+)
- [ ] Backup strategy with encryption
- [ ] Data retention and deletion policies
- [ ] Secrets stored via environment variables or vault

### Infrastructure Security

- [ ] Minimal open ports (only what's needed)
- [ ] Regular dependency updates (`npm audit`, `dependabot`)
- [ ] No debug/development endpoints in production
- [ ] File permissions: 755 for dirs, 644 for files, 600 for secrets
- [ ] Limited user accounts for services (no root)
- [ ] Regular security scanning (SAST, dependency analysis)

---

## Security Quick Reference

| Vulnerability | Prevention | Tools |
|---|---|---|
| **SQL Injection** | Parameterized queries | ESLint plugin, SQL linters |
| **XSS** | Output encoding, CSP headers | DOMPurify, helmet |
| **CSRF** | CSRF tokens, SameSite cookies | csurf middleware |
| **Path Traversal** | Resolve + prefix check | nosanitize |
| **Command Injection** | Don't shell out with user input | shell-quote, execa |
| **Insecure Deserialization** | Validate input schemas | Zod, Pydantic |
| **SSRF** | URL allowlist, no internal URLs | ssrf-agent |
| **Open Redirect** | Validate redirect URLs | Valid URL middleware |

---

*For deeper security concepts, see Bible levels `10-security/`, `14-cryptography-security/`, and `28-trust-security-deep/` — binary exploitation, web security, reverse engineering, malware analysis.*
