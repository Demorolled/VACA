import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import path from 'path';
const DB_DIR = path.resolve(import.meta.dirname, '..', '..', '..', 'data');
const DESIGNS_FILE = path.join(DB_DIR, 'designs.json');
let designs = [];
function ensureDb() {
    if (!existsSync(DB_DIR))
        mkdirSync(DB_DIR, { recursive: true });
    if (!existsSync(DESIGNS_FILE))
        writeFileSync(DESIGNS_FILE, '[]', 'utf-8');
}
function load() {
    ensureDb();
    try {
        designs = JSON.parse(readFileSync(DESIGNS_FILE, 'utf-8'));
    }
    catch {
        designs = [];
    }
}
function save() {
    ensureDb();
    writeFileSync(DESIGNS_FILE, JSON.stringify(designs, null, 2), 'utf-8');
}
load();
export const designStore = {
    getAll() {
        return designs;
    },
    getById(id) {
        return designs.find(d => d.id === id);
    },
    search(query) {
        const q = query.toLowerCase();
        return designs.filter(d => d.name.toLowerCase().includes(q) ||
            d.goal.toLowerCase().includes(q) ||
            d.purpose.toLowerCase().includes(q) ||
            d.tags.some(t => t.toLowerCase().includes(q)) ||
            d.nodes.some(n => n.label.toLowerCase().includes(q) || n.description.toLowerCase().includes(q)));
    },
    add(design) {
        designs.push(design);
        save();
        return design;
    },
    update(id, updates) {
        const idx = designs.findIndex(d => d.id === id);
        if (idx === -1)
            return undefined;
        designs[idx] = { ...designs[idx], ...updates, updatedAt: new Date().toISOString() };
        save();
        return designs[idx];
    },
    delete(id) {
        const idx = designs.findIndex(d => d.id === id);
        if (idx === -1)
            return false;
        designs.splice(idx, 1);
        save();
        return true;
    },
    count() {
        return designs.length;
    },
};
