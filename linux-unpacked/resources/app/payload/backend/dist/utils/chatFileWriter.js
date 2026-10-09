/**
 * Chat file writer — persists files the user asks the chat to create
 * ("create a file called app.py with content ..."). Writes land in
 * data/chat-files/ (env-overridable via VACA_CHAT_FILES_DIR) so the chat
 * can perform REAL writes instead of the LLM hallucinating them.
 *
 * Path safety: the file name is sanitized (no `..`, absolute, drive, or
 * backslash segments) and the resolved destination is verified to stay
 * inside the chat-files root.
 */
import { writeFileSync, mkdirSync, existsSync, readdirSync } from 'fs';
import path from 'path';
import { sanitizeFileName } from './fileWriteDetector.js';
export const CHAT_FILES_DIR = process.env.VACA_CHAT_FILES_DIR ||
    path.resolve(import.meta.dirname, '..', '..', '..', 'data', 'chat-files');
/**
 * Write a file inside the chat-files root. Throws on unsafe names or I/O
 * failures. Sub-paths (e.g. "src/app.ts") are created as needed.
 */
export function writeChatFile(rawName, content) {
    const fileName = sanitizeFileName(rawName);
    if (!fileName) {
        throw new Error(`Unsafe file name: "${String(rawName).slice(0, 80)}"`);
    }
    if (!existsSync(CHAT_FILES_DIR))
        mkdirSync(CHAT_FILES_DIR, { recursive: true });
    const filePath = path.join(CHAT_FILES_DIR, fileName);
    if (!filePath.startsWith(CHAT_FILES_DIR + path.sep)) {
        throw new Error('File path escapes the chat-files directory');
    }
    mkdirSync(path.dirname(filePath), { recursive: true });
    writeFileSync(filePath, content, 'utf-8');
    return { fileName, filePath, bytes: Buffer.byteLength(content, 'utf-8') };
}
/** List saved chat files (relative paths), newest first. */
export function listChatFiles() {
    if (!existsSync(CHAT_FILES_DIR))
        return [];
    const out = [];
    const walk = (dir, prefix) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
            const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
            if (entry.isDirectory())
                walk(path.join(dir, entry.name), rel);
            else
                out.push(rel);
        }
    };
    walk(CHAT_FILES_DIR, '');
    return out.sort();
}
