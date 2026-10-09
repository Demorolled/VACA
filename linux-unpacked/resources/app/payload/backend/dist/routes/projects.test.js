import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import express from 'express';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ProjectStore } from '../db/projects.js';
import { createProjectRoutes } from './projects.js';
let fakeDir;
let server;
let baseUrl;
async function startServer() {
    const store = new ProjectStore(join(fakeDir, 'projects.json'));
    const app = express();
    app.use(express.json());
    app.use('/api/projects', createProjectRoutes(store));
    const srv = app.listen(0);
    await new Promise((resolve) => srv.once('listening', resolve));
    const port = srv.address().port;
    return { server: srv, baseUrl: `http://127.0.0.1:${port}` };
}
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
    fakeDir = await mkdtemp(join(tmpdir(), 'vaca-projects-test-'));
    const srv = await startServer();
    server = srv.server;
    baseUrl = srv.baseUrl;
});
afterAll(async () => {
    server?.close();
    await rm(fakeDir, { recursive: true, force: true });
});
describe('projects export/import endpoints', () => {
    it('exports a project as JSON with the same id + fields', async () => {
        const created = await req('/api/projects', 'POST', { name: 'Export Me', targetOS: 'linux' });
        expect(created.status).toBe(201);
        const id = created.json.id;
        const exp = await req(`/api/projects/${id}/export`);
        expect(exp.status).toBe(200);
        expect(exp.json.id).toBe(id);
        expect(exp.json.name).toBe('Export Me');
        expect(Array.isArray(exp.json.nodes)).toBe(true);
    });
    it('returns 404 when exporting a missing project', async () => {
        const exp = await req('/api/projects/does-not-exist/export');
        expect(exp.status).toBe(404);
    });
    it('imports exported JSON into a fresh project (new id, preserved fields)', async () => {
        const created = await req('/api/projects', 'POST', { name: 'Source Project', targetOS: 'linux' });
        const srcId = created.json.id;
        const exported = await req(`/api/projects/${srcId}/export`);
        const exportedJson = exported.json;
        const imported = await req('/api/projects/import', 'POST', exportedJson);
        expect(imported.status).toBe(201);
        expect(imported.json.id).not.toBe(srcId);
        expect(imported.json.name).toBe('Source Project');
        expect(imported.json.targetOS).toBe('linux');
        expect(Array.isArray(imported.json.nodes)).toBe(true);
        // The imported project is actually retrievable (saved, not just echoed).
        const fetched = await req(`/api/projects/${imported.json.id}`);
        expect(fetched.status).toBe(200);
        expect(fetched.json.name).toBe('Source Project');
    });
    it('imports a minimal {name, nodes, edges} payload', async () => {
        const imported = await req('/api/projects/import', 'POST', {
            name: 'Minimal Import',
            nodes: [{ id: 'n1', type: 'logic', position: { x: 0, y: 0 }, data: { label: 'Node' } }],
            edges: [],
        });
        expect(imported.status).toBe(201);
        expect(imported.json.name).toBe('Minimal Import');
        expect(imported.json.nodes).toHaveLength(1);
    });
    it('rejects a non-object import body with 400', async () => {
        // `null` is valid JSON that reaches the route's body check (a raw string
        // would be rejected earlier by express.json with an HTML error page).
        const res = await req('/api/projects/import', 'POST', null);
        expect(res.status).toBe(400);
    });
    it('rejects import when nodes is present but not an array', async () => {
        const res = await req('/api/projects/import', 'POST', { name: 'Bad Nodes', nodes: 'not-an-array' });
        expect(res.status).toBe(400);
    });
    it('persists imported projects to disk (survives store reload)', async () => {
        const imported = await req('/api/projects/import', 'POST', { name: 'Persist Me' });
        expect(imported.status).toBe(201);
        const id = imported.json.id;
        // A brand-new store pointing at the same file must still see the project.
        const store2 = new ProjectStore(join(fakeDir, 'projects.json'));
        const reloaded = store2.getById(id);
        expect(reloaded?.name).toBe('Persist Me');
    });
});
