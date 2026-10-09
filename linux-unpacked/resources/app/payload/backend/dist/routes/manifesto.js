/**
 * Design Manifesto API Routes
 * ============================
 *
 * Endpoints for reading and updating the Design Manifesto.
 *
 * GET  /api/manifesto       — Return the manifesto text and context
 * PUT  /api/manifesto       — Update the manifesto with new content
 * POST /api/manifesto/reset — Reset to the original template
 */
import { Router } from 'express';
import { getRawManifesto, saveManifesto, getManifestoContext, hasManifesto, invalidateCache, } from '../ai/manifesto.js';
const router = Router();
// ─── Original template (used for reset) ────────────────────────────────────
const ORIGINAL_TEMPLATE = `# 🎨 Veronica — Design Manifesto

> **Edit this file to teach the app YOUR vision. Every architecture plan and code generation will use this as context.**

---

## 1. 🏗️ Architectural Philosophy

**How do you think about software architecture?**

- [ ] Prefer **monolithic** applications (simpler deployment, single codebase)
- [ ] Prefer **microservices / modular** architecture (independent deployability)
- [ ] Prefer **layered architecture** (UI → Logic → Data)
- [ ] Prefer **event-driven / reactive** architecture
- [ ] Prefer **hexagonal / clean architecture** (ports & adapters)
- [ ] **Other:** _________________________________

**Your architectural principles:**
\`\`\`
Example: "I believe in separation of concerns. Every module should have one responsibility. 
Dependencies should flow inward — UI depends on logic, logic depends on data, never the reverse."
\`\`\`

Write your principles here:





---

## 2. ✍️ Code Style & Conventions

**What does your ideal code look like?**

- [ ] **Functional** style (pure functions, immutability, composition)
- [ ] **Object-Oriented** style (classes, inheritance, polymorphism)
- [ ] **Procedural** style (simple functions, minimal abstractions)
- [ ] **Mixed** (use what fits the problem)

**Naming conventions:**
- Variables: \`camelCase\` / \`snake_case\` / \`PascalCase\`
- Functions: \`verbNoun()\` / \`doSomething()\` / \`compute_result()\`
- Classes: \`PascalCase\` / \`snake_case\`
- Files: \`kebab-case\` / \`snake_case\` / \`camelCase\`

**Other style preferences:**
- [ ] Always include **type annotations** (TypeScript/Python types)
- [ ] Prefer **explicit** over implicit (no magic)
- [ ] Always include **JSDoc / docstrings**
- [ ] Prefer **early returns** over nested if-else
- [ ] Maximum **80 / 100 / 120** characters per line
- [ ] Prefer \`const\` / \`let\` over \`var\` always
- [ ] Always handle **errors explicitly** (no silent failures)

**Your custom style rules:**
\`\`\`
Example: "I always put business logic in service files, never in controllers or 
route handlers. I prefer async/await over raw promises. I use Zod for validation."
\`\`\`





---

## 3. 🛠️ Preferred Technologies

**What's in your toolkit?**

**Languages** (rank by preference):
1. _______________
2. _______________
3. _______________
4. _______________

**Frameworks:**
- Frontend: ___________________
- Backend: ___________________
- Mobile: ___________________
- Testing: ___________________

**Databases:**
- Primary: ___________________
- Cache: ___________________
- Search: ___________________

**Infrastructure:**
- Hosting: ___________________
- CI/CD: ___________________
- Monitoring: ___________________

**Your technology philosophy:**
\`\`\`
Example: "I prefer boring, well-tested technology over the latest trend. 
SQLite for data, Go for backend, TypeScript for frontend. No Kubernetes 
unless absolutely necessary."
\`\`\`





---

## 4. ⚖️ Design Principles

**The rules you live by when building software.**

Check all that apply and add your own:

- [ ] **YAGNI** — You Ain't Gonna Need It (build only what's needed now)
- [ ] **DRY** — Don't Repeat Yourself (extract shared logic)
- [ ] **KISS** — Keep It Simple, Stupid (simplicity over cleverness)
- [ ] **SOLID** principles (Single responsibility, Open-closed, Liskov, Interface segregation, Dependency inversion)
- [ ] **Composition over inheritance**
- [ ] **Convention over configuration**
- [ ] **Fail fast** — validate inputs early, crash on unexpected states
- [ ] **Graceful degradation** — handle errors gracefully, never crash the whole app
- [ ] **Defensive programming** — validate everything, trust nothing
- [ ] **Testable design** — write code that's easy to test (dependency injection, interfaces)

**Your personal design principles:**





---

## 5. 🌟 Quality Standards

**What "good" means to you.**

- [ ] Code must **compile/type-check** on first try (no any/ignore)
- [ ] Every function needs a **unit test**
- [ ] **80%+ test coverage** minimum
- [ ] No **unused imports**, variables, or dead code
- [ ] All **error paths must be handled**
- [ ] Logging on every **entry/exit** point
- [ ] Security: **input validation**, **SQL injection prevention**, **XSS protection**
- [ ] Performance: **no N+1 queries**, **proper indexing**, **caching strategy**
- [ ] Accessibility: **WCAG AA** minimum
- [ ] Documentation: **README**, **API docs**, **architecture decisions**

**Your quality bar:**





---

## 6. 🚫 Anti-Patterns & Pet Peeves

**Things you NEVER want the AI to generate.**

- [ ] No \`any\` types (TypeScript)
- [ ] No \`var\` declarations (JavaScript)
- [ ] No global mutable state
- [ ] No \`try/catch\` swallowing errors silently
- [ ] No massive functions (>50 lines)
- [ ] No deeply nested callbacks or conditionals
- [ ] No magic numbers or strings
- [ ] No circular dependencies
- [ ] No commented-out code
- [ ] No \`TODO\` or \`FIXME\` left in production code

**Your specific anti-patterns:**





---

## 7. 📁 Project Structure Preferences

**How you like your projects organized.**

- [ ] **Feature-based** (group by feature: \`auth/\`, \`payments/\`, \`users/\`)
- [ ] **Type-based** (group by type: \`components/\`, \`services/\`, \`utils/\`)
- [ ] **Layer-based** (group by layer: \`frontend/\`, \`backend/\`, \`shared/\`)
- [ ] **Monorepo** with multiple packages
- [ ] **Flat** structure (minimal nesting)

**Your preferred structure:**

\`\`\`
Example:
src/
  app/          # Application setup, routing
  domain/       # Business logic, entities
  infrastructure/  # External integrations, database
  interfaces/   # UI components, API endpoints
  shared/       # Shared utilities
\`\`\`





---

## 8. 📝 How You Want the AI to Communicate

- [ ] **Concise** — get straight to the point, minimal commentary
- [ ] **Detailed** — explain the reasoning behind every decision
- [ ] **Socratic** — ask me questions rather than assuming
- [ ] **Enthusiastic** — celebrate wins, be encouraging
- [ ] **Professional** — business-like, precise language
- [ ] **Custom:** _________________________________

---

## 9. 🎯 Your Vision Statement

> *In one or two sentences, what kind of software do you want to build, and how should the AI help you build it?*

\`\`\`
Example: "I build pragmatic, production-ready applications that solve real problems 
without over-engineering. Help me ship fast without sacrificing quality. 
Teach me things I don't know, but never get in my way."
\`\`\`



---

## ✅ How This Works

This manifesto is loaded by the backend on every request and injected into the:
- **Architect prompt** — so the AI plans architectures that match your vision
- **Code generation prompts** — so generated code follows your style
- **Blueprint suggestions** — so recommendations align with your preferences

**To edit this manifesto**, either:
1. Edit this file directly (\`data/design-manifesto.md\`)
2. Use the **Manifesto Editor** in the app UI
3. Use the API: \`GET /api/manifesto\` to read, \`PUT /api/manifesto\` to update\n`;
/**
 * GET /api/manifesto
 *
 * Returns the full manifesto document.
 * Query params:
 *   ?format=raw     — return the raw Markdown text
 *   ?format=context — return the compact context for prompt injection
 *   default         — return both as JSON
 */
router.get('/', (req, res) => {
    try {
        const format = req.query.format;
        if (format === 'raw') {
            res.setHeader('Content-Type', 'text/markdown; charset=utf-8');
            res.send(getRawManifesto());
            return;
        }
        if (format === 'context') {
            res.setHeader('Content-Type', 'text/plain; charset=utf-8');
            res.send(getManifestoContext());
            return;
        }
        res.json({
            success: true,
            manifesto: getRawManifesto(),
            context: getManifestoContext(),
            hasContent: hasManifesto(),
        });
    }
    catch (err) {
        console.error('[manifesto] GET error:', err.message);
        res.status(500).json({ error: 'Failed to read manifesto.' });
    }
});
/**
 * PUT /api/manifesto
 *
 * Save new manifesto content. Overwrites the file entirely.
 * Body: { content: "full markdown content" }
 */
router.put('/', (req, res) => {
    try {
        const { content } = req.body;
        if (typeof content !== 'string') {
            res.status(400).json({ error: 'Content must be a string.' });
            return;
        }
        if (content.trim().length === 0) {
            res.status(400).json({ error: 'Content cannot be empty.' });
            return;
        }
        const saved = saveManifesto(content);
        if (!saved) {
            res.status(500).json({ error: 'Failed to save manifesto.' });
            return;
        }
        console.log(`[manifesto] Updated (${content.length} chars)`);
        res.json({
            success: true,
            message: 'Manifesto updated successfully.',
            length: content.length,
            hasContent: hasManifesto(),
            context: getManifestoContext(),
        });
    }
    catch (err) {
        console.error('[manifesto] PUT error:', err.message);
        res.status(500).json({ error: 'Failed to save manifesto.' });
    }
});
/**
 * POST /api/manifesto/reset
 *
 * Reset to the original Design Manifesto template.
 */
router.post('/reset', (_req, res) => {
    try {
        const saved = saveManifesto(ORIGINAL_TEMPLATE);
        if (!saved) {
            res.status(500).json({ error: 'Failed to reset manifesto.' });
            return;
        }
        invalidateCache();
        res.json({
            success: true,
            message: 'Manifesto reset to original template.',
        });
    }
    catch (err) {
        console.error('[manifesto] Reset error:', err.message);
        res.status(500).json({ error: 'Failed to reset manifesto.' });
    }
});
export { router as manifestoRoutes };
