import { describe, it, expect } from 'vitest';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
// Same PROJECT_ROOT resolution as semanticRetrieval.ts
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const PROJECT_ROOT = path.resolve(BACKEND_DIR, '..');
const MANIFEST_JSON = path.join(PROJECT_ROOT, 'data', 'component-manifest.json');
const MANIFEST_MD = path.join(PROJECT_ROOT, 'data', 'library', '43-component-manifest.md');
function readManifest() {
    return JSON.parse(readFileSync(MANIFEST_JSON, 'utf-8'));
}
function byType(appTypes, type) {
    const rec = appTypes.find(a => a.appType === type);
    expect(rec, `manifest must contain app type "${type}"`).toBeDefined();
    return rec;
}
// ── Expected component records for the 4 templates added in CHANGE 47 ──
// (from data/library/02-app-type-templates.md §7-10; update deliberately
// when a template legitimately changes — this test guards silent regressions)
const EXPECTED = {
    'Auth App': {
        nodeCount: '5-7',
        nodes: [
            { name: 'UI', type: 'ui' }, { name: 'Auth', type: 'logic' },
            { name: 'Logic', type: 'logic' }, { name: 'Database', type: 'database' },
            { name: 'Sessions', type: 'database' },
        ],
        files: [
            'frontend/', 'frontend/src/', 'frontend/src/pages/',
            'frontend/src/pages/Login.tsx', 'frontend/src/pages/Register.tsx',
            'frontend/src/pages/Profile.tsx', 'frontend/src/components/',
            'frontend/src/api/', 'frontend/src/App.tsx', 'frontend/index.html',
            'frontend/vite.config.ts', 'backend/', 'backend/src/', 'backend/src/routes/',
            'backend/src/routes/auth.ts', 'backend/src/routes/users.ts',
            'backend/src/services/', 'backend/src/services/password.ts',
            'backend/src/services/session.ts', 'backend/src/db/',
            'backend/src/db/schema.ts', 'backend/src/db/repository.ts',
            'backend/src/index.ts', 'backend/package.json', 'README.md',
        ],
        languages: ['TypeScript', 'Python'],
        database: 'PostgreSQL',
        interface: 'Web Browser',
        selectionKeywords: ['log in users', 'authenticate users', 'user accounts'],
    },
    'Chat App': {
        nodeCount: '5-8',
        nodes: [
            { name: 'UI', type: 'ui' }, { name: 'Chat', type: 'logic' },
            { name: 'Logic', type: 'logic' }, { name: 'Database', type: 'database' },
            { name: 'Realtime', type: 'api' },
        ],
        files: [
            'frontend/', 'frontend/src/', 'frontend/src/components/',
            'frontend/src/components/MessageList.tsx',
            'frontend/src/components/MessageInput.tsx',
            'frontend/src/components/RoomList.tsx', 'frontend/src/hooks/',
            'frontend/src/hooks/useSocket.ts', 'frontend/src/api/',
            'frontend/src/App.tsx', 'frontend/index.html', 'frontend/vite.config.ts',
            'backend/', 'backend/src/', 'backend/src/routes/',
            'backend/src/routes/rooms.ts', 'backend/src/sockets/',
            'backend/src/sockets/chat.ts', 'backend/src/services/',
            'backend/src/services/messageStore.ts', 'backend/src/db/',
            'backend/src/index.ts', 'backend/package.json', 'README.md',
        ],
        languages: ['TypeScript', 'Node.js'],
        database: 'SQLite / PostgreSQL',
        interface: 'Web Browser',
        selectionKeywords: ['build a chat', 'real-time messaging'],
    },
    'E-commerce': {
        nodeCount: '6-8',
        nodes: [
            { name: 'UI', type: 'ui' }, { name: 'Cart', type: 'logic' },
            { name: 'Logic', type: 'logic' }, { name: 'Database', type: 'database' },
            { name: 'Payments', type: 'api' },
        ],
        files: [
            'frontend/', 'frontend/src/', 'frontend/src/pages/',
            'frontend/src/pages/ProductList.tsx',
            'frontend/src/pages/ProductDetail.tsx',
            'frontend/src/pages/Checkout.tsx', 'frontend/src/components/',
            'frontend/src/components/Cart.tsx', 'frontend/src/api/',
            'frontend/src/App.tsx', 'frontend/index.html', 'frontend/vite.config.ts',
            'backend/', 'backend/src/', 'backend/src/routes/',
            'backend/src/routes/products.ts', 'backend/src/routes/cart.ts',
            'backend/src/routes/orders.ts', 'backend/src/services/',
            'backend/src/services/inventory.ts', 'backend/src/services/payment.ts',
            'backend/src/db/', 'backend/src/db/schema.ts', 'backend/src/db/seed.ts',
            'backend/src/index.ts', 'backend/package.json', 'README.md',
        ],
        languages: ['TypeScript', 'Python'],
        database: 'PostgreSQL',
        interface: 'Web Browser',
        selectionKeywords: ['online store', 'shopping cart', 'sell products'],
    },
    'Dashboard': {
        nodeCount: '4-6',
        nodes: [
            { name: 'UI', type: 'ui' }, { name: 'Widgets', type: 'ui' },
            { name: 'Logic', type: 'logic' }, { name: 'Database', type: 'database' },
            { name: 'Data API', type: 'api' },
        ],
        files: [
            'frontend/', 'frontend/src/', 'frontend/src/widgets/',
            'frontend/src/widgets/ChartWidget.tsx',
            'frontend/src/widgets/StatWidget.tsx',
            'frontend/src/widgets/TableWidget.tsx', 'frontend/src/layouts/',
            'frontend/src/layouts/GridLayout.tsx', 'frontend/src/api/',
            'frontend/src/App.tsx', 'frontend/index.html', 'frontend/vite.config.ts',
            'backend/', 'backend/src/', 'backend/src/routes/',
            'backend/src/routes/metrics.ts', 'backend/src/services/',
            'backend/src/services/aggregator.ts', 'backend/src/services/exporter.ts',
            'backend/src/db/', 'backend/src/index.ts', 'backend/package.json',
            'README.md',
        ],
        languages: ['TypeScript', 'Python'],
        database: 'SQLite / PostgreSQL',
        interface: 'Web Browser',
        selectionKeywords: ['analytics dashboard', 'monitor metrics', 'admin panel'],
    },
    'File Sync Tool': {
        nodeCount: '3-5',
        nodes: [
            { name: 'Watcher', type: 'input' }, { name: 'Sync', type: 'logic' },
            { name: 'Index', type: 'database' }, { name: 'Remote', type: 'api' },
        ],
        files: [
            'cmd/', 'cmd/app/', 'cmd/app/main.go', 'cmd/app/main.ts',
            'pkg/', 'src/', 'src/watcher/', 'src/sync/', 'src/index/',
            'src/remote/', 'config/', 'config/config.yaml', 'Makefile', 'README.md',
        ],
        languages: ['Go', 'TypeScript'],
        database: 'SQLite',
        interface: 'CLI / Tray',
        selectionKeywords: ['sync files', 'backup folders', 'mirror directories'],
    },
    'Booking App': {
        nodeCount: '5-7',
        nodes: [
            { name: 'UI', type: 'ui' }, { name: 'Booking', type: 'logic' },
            { name: 'Logic', type: 'logic' }, { name: 'Database', type: 'database' },
            { name: 'Payments', type: 'api' },
        ],
        files: [
            'frontend/', 'frontend/src/', 'frontend/src/pages/',
            'frontend/src/pages/Availability.tsx',
            'frontend/src/pages/BookingForm.tsx',
            'frontend/src/pages/Confirmation.tsx', 'frontend/src/components/',
            'frontend/src/components/Calendar.tsx', 'frontend/src/api/',
            'frontend/src/App.tsx', 'frontend/index.html', 'frontend/vite.config.ts',
            'backend/', 'backend/src/', 'backend/src/routes/',
            'backend/src/routes/availability.ts', 'backend/src/routes/bookings.ts',
            'backend/src/routes/payments.ts', 'backend/src/services/',
            'backend/src/services/scheduler.ts', 'backend/src/services/capacity.ts',
            'backend/src/db/', 'backend/src/db/schema.ts',
            'backend/src/db/repository.ts', 'backend/src/index.ts',
            'backend/package.json', 'README.md',
        ],
        languages: ['TypeScript', 'Python'],
        database: 'PostgreSQL',
        interface: 'Web Browser',
        selectionKeywords: ['book a reservation', 'scheduling app', 'appointment booking'],
    },
    'CMS': {
        nodeCount: '5-7',
        nodes: [
            { name: 'UI', type: 'ui' }, { name: 'Content', type: 'logic' },
            { name: 'Logic', type: 'logic' }, { name: 'Database', type: 'database' },
            { name: 'Publish', type: 'api' },
        ],
        files: [
            'frontend/', 'frontend/src/', 'frontend/src/pages/',
            'frontend/src/pages/Admin.tsx', 'frontend/src/pages/PostView.tsx',
            'frontend/src/components/', 'frontend/src/components/Editor.tsx',
            'frontend/src/api/', 'frontend/src/App.tsx', 'frontend/index.html',
            'frontend/vite.config.ts', 'backend/', 'backend/src/',
            'backend/src/routes/', 'backend/src/routes/posts.ts',
            'backend/src/routes/media.ts', 'backend/src/services/',
            'backend/src/services/content.ts', 'backend/src/services/publish.ts',
            'backend/src/db/', 'backend/src/db/schema.ts',
            'backend/src/db/repository.ts', 'backend/src/index.ts',
            'backend/package.json', 'README.md',
        ],
        languages: ['TypeScript', 'Python'],
        database: 'SQLite / PostgreSQL',
        interface: 'Web Browser',
        selectionKeywords: ['content management', 'blog platform', 'publish articles'],
    },
};
describe('component manifest — new app-type templates (CHANGE 47)', () => {
    const manifest = readManifest();
    it('contains all 4 new app types plus the original set (12 total, +1 = 3D App)', () => {
        const names = manifest.appTypes.map(a => a.appType);
        for (const t of Object.keys(EXPECTED))
            expect(names).toContain(t);
        for (const legacy of ['CLI Tool', 'Web App', 'Media Server', 'System Tool',
            'Desktop App', 'API Server', 'Data Processor', 'Game']) {
            expect(names).toContain(legacy);
        }
        expect(names).toContain('3D App');
        expect(manifest.appTypes.length).toBe(16);
    });
    it.each(Object.keys(EXPECTED))('%s — node graph and node count are pinned', (type) => {
        const rec = byType(manifest.appTypes, type);
        const want = EXPECTED[type];
        expect(rec.nodeCount).toBe(want.nodeCount);
        expect(rec.nodes).toEqual(want.nodes);
    });
    it.each(Object.keys(EXPECTED))('%s — full component file list is pinned', (type) => {
        const rec = byType(manifest.appTypes, type);
        const want = EXPECTED[type];
        expect(rec.files).toEqual(want.files);
        // sanity: every file is non-empty and the tree is rooted
        expect(rec.files.length).toBe(want.files.length);
        expect(rec.files.every(f => f.length > 0)).toBe(true);
    });
    it.each(Object.keys(EXPECTED))('%s — languages, database, interface, keywords', (type) => {
        const rec = byType(manifest.appTypes, type);
        const want = EXPECTED[type];
        expect(rec.languages).toEqual(want.languages);
        expect(rec.database).toBe(want.database);
        expect(rec.interface).toBe(want.interface);
        expect(rec.selectionKeywords).toEqual(want.selectionKeywords);
    });
    it('lists the new hybrids (incl. the hyphenated Chat + E-commerce combo)', () => {
        expect(manifest.hybrids).toContain('Auth App + Web App = Members Only Web App');
        expect(manifest.hybrids).toContain('Chat App + E-commerce = Live Shopping with Chat Support');
        expect(manifest.hybrids).toContain('Dashboard + API Server = Metrics Dashboard over Microservices');
        expect(manifest.hybrids).toContain('File Sync Tool + Web App = Cloud Sync Dashboard');
        expect(manifest.hybrids).toContain('Booking App + Chat App = Appointment Chat Reminders');
        expect(manifest.hybrids).toContain('CMS + E-commerce = Store with Content Management');
    });
});
describe('manifest ↔ library-sheet sync', () => {
    it('regeneration from the sheets is a no-op (committed manifest is current)', () => {
        const beforeJson = readFileSync(MANIFEST_JSON, 'utf-8');
        const beforeMd = readFileSync(MANIFEST_MD, 'utf-8');
        let afterJson = beforeJson;
        let afterMd = beforeMd;
        let regenerated = false;
        try {
            execFileSync('python3', ['scripts/build-component-manifest.py'], {
                cwd: PROJECT_ROOT,
                stdio: 'pipe',
                timeout: 60_000,
            });
            regenerated = true;
            afterJson = readFileSync(MANIFEST_JSON, 'utf-8');
            afterMd = readFileSync(MANIFEST_MD, 'utf-8');
        }
        finally {
            // a test must never modify repo files — restore even on failure
            writeFileSync(MANIFEST_JSON, beforeJson);
            writeFileSync(MANIFEST_MD, beforeMd);
        }
        // a thrown/skipped generator run must fail loudly, not trivially pass
        expect(regenerated).toBe(true);
        // generatedAt changes every run — compare everything else exactly
        const strip = (s) => {
            const parsed = JSON.parse(s);
            delete parsed.generatedAt;
            return parsed;
        };
        expect(strip(afterJson)).toEqual(strip(beforeJson));
        expect(afterMd).toBe(beforeMd);
    });
});
