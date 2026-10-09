/**
 * File-write intent detection.
 *
 * Detects when the user asks VACA to create/write/save a file ("create a file
 * called app.py", "write this to notes.txt", "save this as config.yaml"). The
 * chat LLM previously hallucinated these writes (claiming "done!" with no file
 * on disk). Now the platform detects the intent, extracts the filename and
 * content, performs the write itself, and returns a deterministic
 * confirmation — the model never fakes a file write again.
 */
// Never intercept questions ABOUT the capability itself.
const QUESTION_RE = /^(how|what|why|where|when|who|can you|do you|are you|will you|is it|does it|tell me|explain|show me|is there|have you)\b/i;
/** Trimmed file names that are clearly not real files. */
const BAD_NAMES = new Set(['file', 'the', 'this', 'that', 'it', 'a', 'an']);
/**
 * Sanitize an extracted filename: strip leading slashes, collapse the path,
 * and reject anything that escapes via `..` or absolute paths. Returns a safe
 * relative path (forward slashes) or null.
 */
export function sanitizeFileName(raw) {
    if (typeof raw !== 'string')
        return null;
    let p = raw.replace(/\\/g, '/').replace(/^[a-zA-Z]:/, '');
    p = p.replace(/^\/+/, '').replace(/\/+$/, '');
    if (!p || BAD_NAMES.has(p.toLowerCase()))
        return null;
    const segments = p.split('/');
    for (const seg of segments) {
        if (seg === '' || seg === '.' || seg === '..' || seg === '/' || seg.includes('\0'))
            return null;
    }
    if (!/\./.test(p))
        return null; // must have an extension
    return segments.join('/');
}
/**
 * Detect a request to create/write/save a file. Returns null when the message
 * is a question, too long, or not a file-write request.
 */
export function detectFileWriteRequest(text) {
    const t = (text || '').trim();
    if (!t || t.length > 4000)
        return null;
    if (QUESTION_RE.test(t))
        return null;
    // Verb-driven forms:
    //   1) "create/make/generate a file called X[: content]"
    //   2) "write/save/put this (to|into|in|as) X[: content]"
    //   3) "write/save X: content"
    const createMatch = t.match(/\b(?:create|make|generate|write|save|put|add)\s+(?:a\s+|an\s+|the\s+|new\s+)?file\s+(?:called|named|as)?\s*:?\s*([a-zA-Z0-9.][a-zA-Z0-9._/-]*\.[a-zA-Z0-9]{1,8})\b/i);
    const toMatch = !createMatch && t.match(/\b(?:write|save|put|add)\s+(?:this|that|it|the\s+following|these|those)\s+(?:to|into|in|as)\s+([a-zA-Z0-9.][a-zA-Z0-9._/-]*\.[a-zA-Z0-9]{1,8})\b/i);
    const directMatch = !createMatch && !toMatch && t.match(/\b(?:write|save|create|put)\s+([a-zA-Z0-9.][a-zA-Z0-9._/-]*\.[a-zA-Z0-9]{1,8})\s*:/i);
    // Bare form: "create main.py with this content: ..." / "make script.js"
    // (verb directly before a filename with an extension — the extension
    // requirement keeps "create a nice user interface" from matching).
    const bareMatch = !createMatch && !toMatch && !directMatch && t.match(/\b(?:create|make|generate)\s+([a-zA-Z0-9.][a-zA-Z0-9._/-]*\.[a-zA-Z0-9]{1,8})\b/i);
    const matched = createMatch || toMatch || directMatch || bareMatch;
    if (!matched)
        return null;
    // Keep the raw name (trimmed) — the writer sanitizes and rejects unsafe
    // paths, so traversal attempts still reach the route and get a clean error
    // instead of being silently ignored (which let the LLM hallucinate a write).
    const fileName = matched[1].trim();
    // Content extraction:
    //   - After a colon following the filename ("...app.py: <content>")
    //   - Inside a fenced code block (```lang\n...\n```)
    //   - After "with this content:" / "with the content:"
    const afterFile = t.slice(matched.index + matched[0].length).trim();
    // Colon-delimited inline content: "app.py: print('hi')"
    let hasInline = false;
    let inlineContent;
    if (/^[:：]\s*/.test(afterFile)) {
        const body = afterFile.replace(/^[:：]\s*/, '');
        if (body.length > 0) {
            hasInline = true;
            inlineContent = body;
        }
    }
    // "with this content:" / "with the following content:"
    if (!hasInline) {
        const contentMatch = t.match(/\bwith\s+(?:this|the|the\s+following)\s+content\s*:?\s*([\s\S]+)$/i);
        if (contentMatch && contentMatch[1].trim().length > 0) {
            hasInline = true;
            inlineContent = contentMatch[1].trim();
        }
    }
    // Fenced code block: ```lang\n...\n```
    if (!hasInline) {
        const fence = t.match(/```[a-zA-Z0-9_-]*\s*\n([\s\S]*?)```/);
        if (fence && fence[1].trim().length > 0) {
            hasInline = true;
            inlineContent = fence[1].trim();
        }
    }
    return { fileName, hasInlineContent: hasInline, inlineContent };
}
/**
 * Build the content to persist from a single-prompt request. Uses inline
 * content when present; otherwise strips the trailing instruction line and
 * saves the remainder (single-prompt requests may embed history).
 */
export function buildFileContentFromPrompt(req, prompt) {
    if (req.hasInlineContent && req.inlineContent)
        return req.inlineContent;
    const lines = (prompt || '').trim().split('\n');
    lines.pop(); // drop the instruction line itself
    const rest = lines.join('\n').trim();
    // No content anywhere → return '' so the route asks the user what to write
    // instead of accidentally writing the instruction itself as file content.
    return rest.length > 0 ? rest : '';
}
/**
 * Build the content to persist from a chat message array. Uses inline content
 * when present; otherwise serializes all prior messages.
 */
export function buildFileContentFromMessages(req, messages) {
    if (req.hasInlineContent && req.inlineContent)
        return req.inlineContent;
    const prior = messages.slice(0, -1);
    if (prior.length === 0)
        return '';
    const serialized = prior
        .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
        .join('\n\n');
    const MAX = 6000;
    return serialized.length > MAX ? serialized.slice(0, MAX) + '\n[...truncated]' : serialized;
}
