/**
 * Design Manifesto Service
 * ========================
 *
 * Loads the user's Design Manifesto from disk, caches it in memory,
 * and provides methods to inject it into AI prompts so that every
 * architecture plan, code generation, and suggestion is aligned with
 * the user's personal vision.
 *
 * The manifesto is a Markdown file (data/design-manifesto.md) that the user
 * edits directly or through the Manifesto Editor UI.
 */
import * as fs from 'fs';
import * as path from 'path';
// ─── Paths ────────────────────────────────────────────────────────────────
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const MANIFESTO_PATH = path.join(PROJECT_ROOT, 'data', 'design-manifesto.md');
// ─── Cache ────────────────────────────────────────────────────────────────
let cachedManifesto = null;
let lastLoadTime = 0;
const CACHE_TTL_MS = 10_000; // Re-read from disk every 10s at most
// ─── Helpers ──────────────────────────────────────────────────────────────
/**
 * Load the full manifesto text from disk (with caching).
 */
export function loadManifesto() {
    const now = Date.now();
    // Use cache if fresh
    if (cachedManifesto !== null && (now - lastLoadTime) < CACHE_TTL_MS) {
        return cachedManifesto;
    }
    try {
        if (fs.existsSync(MANIFESTO_PATH)) {
            cachedManifesto = fs.readFileSync(MANIFESTO_PATH, 'utf-8');
            lastLoadTime = now;
            return cachedManifesto;
        }
    }
    catch (err) {
        console.warn('[manifesto] Failed to read manifesto file:', err);
    }
    // Fallback: return an empty string if no manifesto exists
    return '';
}
/**
 * Check whether a manifesto has been defined (i.e. the file exists
 * and the user has filled in at least some content beyond the template).
 */
export function hasManifesto() {
    const text = loadManifesto();
    if (!text)
        return false;
    // Ignore the template comments and check for actual user content
    const lines = text.split('\n').filter(l => {
        const trimmed = l.trim();
        // Skip template structure, headings, checkboxes, dashes, and blank lines
        if (trimmed.startsWith('#') || trimmed.startsWith('- [ ]') ||
            trimmed.startsWith('>') || trimmed.startsWith('---') ||
            trimmed.startsWith('```') || trimmed.startsWith('*') ||
            trimmed.startsWith('|') || !trimmed)
            return false;
        return true;
    });
    // If we have at least a few non-trivial lines, consider it "filled in"
    const substantive = lines.filter(l => l.trim().length > 10);
    return substantive.length >= 3;
}
/**
 * Save new manifesto content to disk (overwrites the file).
 */
export function saveManifesto(content) {
    try {
        const dir = path.dirname(MANIFESTO_PATH);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        fs.writeFileSync(MANIFESTO_PATH, content, 'utf-8');
        // Invalidate cache so next load picks up the new content
        cachedManifesto = null;
        lastLoadTime = 0;
        return true;
    }
    catch (err) {
        console.error('[manifesto] Failed to save manifesto:', err);
        return false;
    }
}
// ─── Prompt Injection ─────────────────────────────────────────────────────
/**
 * Extract the key sections from the manifesto as a compact context string
 * suitable for injection into LLM system prompts.
 *
 * We look for the numbered sections and extract user-written content
 * (excluding template boilerplate like empty checkboxes and placeholder lines).
 */
export function getManifestoContext() {
    const text = loadManifesto();
    if (!text || !hasManifesto())
        return '';
    const lines = text.split('\n');
    const sections = [];
    let currentSection = null;
    for (const line of lines) {
        const trimmed = line.trim();
        // Detect section headings (## 1. Title)
        if (trimmed.startsWith('## ')) {
            if (currentSection && currentSection.content.length > 0) {
                sections.push(currentSection);
            }
            currentSection = {
                title: trimmed.replace(/^##\s+\d+\.\s*/, '').trim(),
                content: [],
            };
            continue;
        }
        if (!currentSection)
            continue;
        // Collect non-empty, non-template lines
        if (trimmed &&
            !trimmed.startsWith('- [ ]') && // unchecked checkbox only
            !trimmed.startsWith('>') && // blockquote/template
            !trimmed.startsWith('---') && // horizontal rule
            !trimmed.startsWith('```') && // code fence
            !trimmed.startsWith('|') && // table (template)
            !trimmed.startsWith('*') && // list markers in template
            !trimmed.match(/^\d+\.\s*_{3,}$/) && // "2. _______________" fill-ins
            trimmed.length > 5 // too short = boilerplate
        ) {
            // Skip template example blocks wrapped in ```
            if (trimmed.startsWith('Example:') || trimmed.startsWith('```') ||
                trimmed.startsWith('Write your') || trimmed.startsWith('Your custom') ||
                trimmed.startsWith('Your personal') || trimmed.startsWith('Your preferred') ||
                trimmed.startsWith('Check all') || trimmed.startsWith('Rank by') ||
                trimmed.startsWith('Your technology') || trimmed.startsWith('Your quality') ||
                trimmed.startsWith('Your specific')) {
                // Check if there's actual content after the label
                const afterLabel = line.substring(line.indexOf(':') + 1).trim();
                if (afterLabel.length > 10) {
                    currentSection.content.push(afterLabel);
                }
                continue;
            }
            currentSection.content.push(trimmed);
        }
    }
    // Don't forget the last section
    if (currentSection && currentSection.content.length > 0) {
        sections.push(currentSection);
    }
    if (sections.length === 0)
        return '';
    // Build a compact context string
    const parts = [
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
        '🎨 USER DESIGN MANIFESTO — The user\'s architectural vision, style preferences, and design principles.',
        'Read this carefully. Consider these preferences when designing.',
        '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
    ];
    for (const section of sections) {
        parts.push(`\n[${section.title}]`);
        for (const line of section.content) {
            if (line.startsWith('-')) {
                // Clean up checkbox markers for checked items
                const cleaned = line.replace(/^- \[x\]\s*/, '✅ ').replace(/^- /, '');
                parts.push(`  ${cleaned}`);
            }
            else {
                parts.push(`  ${line}`);
            }
        }
    }
    parts.push('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    parts.push('✅ Consider these preferences as guidance, but the user\'s direct request always takes priority.\n');
    return parts.join('\n');
}
/**
 * Get the raw manifesto text (for the API to serve).
 */
export function getRawManifesto() {
    return loadManifesto();
}
/**
 * Invalidate the cache forcing a re-read from disk on next load.
 */
export function invalidateCache() {
    cachedManifesto = null;
    lastLoadTime = 0;
}
