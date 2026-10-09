import { describe, it, expect } from 'vitest';
import { buildScanConnections, detectApps } from './scanner.js';
const FILE = (path, content) => ({ path, content });
describe('buildScanConnections', () => {
    it('detects npm packages from bare import specifiers', () => {
        const conns = buildScanConnections([
            FILE('myapp/src/server.ts', "import express from 'express';\nimport { Router } from 'express';\n"),
            FILE('myapp/src/client.ts', "import axios from 'axios';\nconst x = require('lodash');\n"),
        ]);
        const names = conns.filter((c) => c.kind === 'package').map((c) => c.name);
        expect(names).toContain('express');
        expect(names).toContain('axios');
        expect(names).toContain('lodash');
        const express = conns.find((c) => c.name === 'express');
        expect(express.usedBy).toContain('myapp/src/server.ts');
    });
    it('handles scoped packages and subpath imports', () => {
        const conns = buildScanConnections([
            FILE('app/index.tsx', "import { Button } from '@mui/material';\nimport React from 'react-dom/client';\n"),
        ]);
        expect(conns.some((c) => c.kind === 'package' && c.name === '@mui/material')).toBe(true);
        expect(conns.some((c) => c.kind === 'package' && c.name === 'react-dom')).toBe(true);
    });
    it('detects external services from URL calls and /api paths', () => {
        const conns = buildScanConnections([
            FILE('app/api.ts', "fetch('https://api.stripe.com/v1/charges');\naxios.post('https://example.com/webhook');\n"),
            FILE('app/socket.ts', "const ws = new WebSocket('wss://realtime.example.com/feed');\n"),
        ]);
        const services = conns.filter((c) => c.kind === 'service');
        expect(services.some((c) => c.name.includes('api.stripe.com'))).toBe(true);
        expect(services.some((c) => c.name.includes('example.com/webhook'))).toBe(true);
        expect(services.some((c) => c.name.includes('realtime.example.com'))).toBe(true);
    });
    it('detects sibling apps from cross-folder relative imports', () => {
        const conns = buildScanConnections([
            FILE('frontend/src/index.ts', "import { api } from '../../backend/src/api';\n"),
            FILE('frontend/src/util.ts', 'export const x = 1;'),
            FILE('backend/src/api.ts', 'export const api = 1;'),
        ]);
        const app = conns.find((c) => c.kind === 'app');
        expect(app).toBeTruthy();
        expect(app.name).toBe('backend');
        expect(app.usedBy).toContain('frontend/src/index.ts');
    });
    it('reads package.json dependencies', () => {
        const conns = buildScanConnections([
            FILE('app/package.json', JSON.stringify({ dependencies: { express: '^4.0.0' }, devDependencies: { vitest: '^4.0.0' } })),
        ]);
        expect(conns.some((c) => c.kind === 'package' && c.name === 'express')).toBe(true);
        expect(conns.some((c) => c.kind === 'package' && c.name === 'vitest')).toBe(true);
    });
    it('does not treat relative or node-builtin imports as packages', () => {
        const conns = buildScanConnections([
            FILE('app/main.ts', "import { x } from './util';\nimport path from 'path';\nimport fs from 'node:fs';\n"),
        ]);
        expect(conns.filter((c) => c.kind === 'package')).toHaveLength(0);
    });
    it('dedupes by kind+name and merges usedBy, sorted by usage', () => {
        const conns = buildScanConnections([
            FILE('app/a.ts', "import x from 'express';\n"),
            FILE('app/b.ts', "import y from 'express';\nimport z from 'axios';\n"),
        ]);
        const express = conns.find((c) => c.name === 'express');
        expect(express.usedBy).toHaveLength(2);
        expect(conns[0].name).toBe('express'); // most-used first
    });
});
describe('detectApps', () => {
    it('returns a single root for one app', () => {
        expect(detectApps([FILE('myapp/src/index.ts', ''), FILE('myapp/src/util.ts', '')])).toEqual(['myapp']);
    });
    it('returns multiple roots when several apps are dropped', () => {
        const roots = detectApps([
            FILE('frontend/src/index.ts', ''),
            FILE('backend/src/api.ts', ''),
            FILE('shared/lib.ts', ''),
        ]);
        expect(roots).toEqual(['frontend', 'backend', 'shared']);
    });
});
