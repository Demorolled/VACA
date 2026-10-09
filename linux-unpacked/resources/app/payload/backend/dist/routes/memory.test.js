import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import express from 'express';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
// Point the singleton store at a temp file BEFORE the route module loads it.
const fakeDir = await mkdtemp(join(tmpdir(), 'vaca-memory-test-'));
process.env.VACA_MEMORY_FILE = join(fakeDir, 'session-memory.json');
vi.resetModules();
const { memoryRoutes } = await import('./memory.js');
const app = express();
app.use(express.json());
app.use('/api/memory', memoryRoutes);
let server;
let baseUrl;
async function req(path, method = 'GET', body) {
    const res = await fetch(`${baseUrl}${path}`, {
        method,
        headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let json = null;
    try {
        json = text ? JSON.parse(text) : null;
    }
    catch {
        json = null;
    }
    return { status: res.status, json, text };
}
beforeAll(async () => {
    server = app.listen(0);
    await new Promise((resolve) => server.once('listening', resolve));
    baseUrl = `http://127.0.0.1:${server.address().port}`;
});
afterAll(async () => {
    server?.close();
    delete process.env.VACA_MEMORY_FILE;
    await rm(fakeDir, { recursive: true, force: true });
});
describe('memory routes — note lifecycle', () => {
    it('writes a note, lists it, deletes it by id, and 404s afterwards', async () => {
        const w = await req('/api/memory/write', 'POST', { topic: 'My color', content: 'teal-ish probe note' });
        expect(w.status).toBe(200);
        const id = w.json.note.id;
        expect(typeof id).toBe('string');
        const list = await req('/api/memory/notes');
        expect(list.json.notes.some((n) => n.id === id)).toBe(true);
        const del = await req(`/api/memory/notes/${id}`, 'DELETE');
        expect(del.status).toBe(200);
        expect(del.json.success).toBe(true);
        const gone = await req(`/api/memory/notes/${id}`, 'DELETE');
        expect(gone.status).toBe(404);
    });
    it('restores a snapshot so probe notes never linger', async () => {
        // Real user note first.
        await req('/api/memory/write', 'POST', { topic: 'Real note', content: 'real content' });
        const list = await req('/api/memory/notes');
        const snap = list.json.notes;
        // Probe writes its fact...
        await req('/api/memory/write', 'POST', { topic: 'auditcolor1234', content: 'turquoise probe' });
        const polluted = await req('/api/memory/notes');
        expect(polluted.json.notes.some((n) => n.topic === 'auditcolor1234')).toBe(true);
        // ...then restores the exact prior state.
        const restore = await req('/api/memory/notes/restore', 'POST', { notes: snap });
        expect(restore.status).toBe(200);
        const after = await req('/api/memory/notes');
        expect(after.json.notes.some((n) => n.topic === 'auditcolor1234')).toBe(false);
        expect(after.json.notes.some((n) => n.topic === 'Real note')).toBe(true);
    });
    it('rejects a restore with a non-array body', async () => {
        const r = await req('/api/memory/notes/restore', 'POST', { notes: 'not-an-array' });
        expect(r.status).toBe(400);
    });
    it('wipe-guard: refuses an EMPTY snapshot over a non-empty store', async () => {
        await req('/api/memory/write', 'POST', { topic: 'Keep me', content: 'must survive' });
        const r = await req('/api/memory/notes/restore', 'POST', { notes: [] });
        expect(r.status).toBe(400);
        const list = await req('/api/memory/notes');
        expect(list.json.notes.some((n) => n.topic === 'Keep me')).toBe(true); // not wiped
        // force:true allows a deliberate full clear
        const forced = await req('/api/memory/notes/restore', 'POST', { notes: [], force: true });
        expect(forced.status).toBe(200);
    });
});
