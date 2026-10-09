import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import path from 'path';
const DB_DIR = path.resolve(import.meta.dirname, '..', '..', '..', 'data');
const NODES_FILE = path.join(DB_DIR, 'node-designs.json');
const builtInDesigns = [
    { id: 'builtin-input', type: 'input', label: 'User Input', description: 'Captures and validates user input from forms, buttons, or voice', language: 'typescript', category: 'input', tags: ['form', 'validation', 'input'], code: '', source: 'built-in', usageCount: 0, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() },
    { id: 'builtin-output', type: 'output', label: 'Display Output', description: 'Renders results and feedback to the user', language: 'typescript', category: 'output', tags: ['display', 'render', 'output'], code: '', source: 'built-in', usageCount: 0, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() },
    { id: 'builtin-logic', type: 'logic', label: 'Core Logic', description: 'Core application logic, state management, and business rules', language: 'typescript', category: 'logic', tags: ['logic', 'state', 'business'], code: '', source: 'built-in', usageCount: 0, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() },
    { id: 'builtin-api', type: 'api', label: 'API Integration', description: 'Connects to external services and APIs', language: 'typescript', category: 'api', tags: ['api', 'integration', 'network'], code: '', source: 'built-in', usageCount: 0, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() },
    { id: 'builtin-database', type: 'database', label: 'Data Storage', description: 'Persists and retrieves application data', language: 'typescript', category: 'database', tags: ['database', 'storage', 'crud'], code: '', source: 'built-in', usageCount: 0, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() },
    { id: 'builtin-ui', type: 'ui', label: 'User Interface', description: 'Renders the application user interface', language: 'typescript', category: 'ui', tags: ['ui', 'interface', 'component'], code: '', source: 'built-in', usageCount: 0, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() },
];
let customDesigns = [];
function ensureDb() {
    if (!existsSync(DB_DIR))
        mkdirSync(DB_DIR, { recursive: true });
    if (!existsSync(NODES_FILE))
        writeFileSync(NODES_FILE, '[]', 'utf-8');
}
function load() {
    ensureDb();
    try {
        customDesigns = JSON.parse(readFileSync(NODES_FILE, 'utf-8'));
    }
    catch {
        customDesigns = [];
    }
}
function save() {
    ensureDb();
    writeFileSync(NODES_FILE, JSON.stringify(customDesigns, null, 2), 'utf-8');
}
load();
export const nodeStore = {
    getAll() {
        return [...builtInDesigns, ...customDesigns];
    },
    getById(id) {
        return [...builtInDesigns, ...customDesigns].find(n => n.id === id);
    },
    searchByType(type) {
        return [...builtInDesigns, ...customDesigns].filter(n => n.type === type);
    },
    search(query) {
        const q = query.toLowerCase();
        return [...builtInDesigns, ...customDesigns].filter(n => n.label.toLowerCase().includes(q) ||
            n.description.toLowerCase().includes(q) ||
            n.tags.some(t => t.toLowerCase().includes(q)));
    },
    add(design) {
        customDesigns.push(design);
        save();
        return design;
    },
    learnFromNode(node) {
        const existing = customDesigns.find(n => n.type === node.type && n.label.toLowerCase() === (node.label || '').toLowerCase());
        if (existing) {
            existing.usageCount++;
            existing.updatedAt = new Date().toISOString();
            if (node.description && !existing.description.includes(node.description)) {
                existing.description = node.description;
            }
            save();
            return existing;
        }
        const newDesign = {
            id: `learned_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            type: node.type,
            label: node.label,
            description: node.description,
            language: node.language || 'typescript',
            category: node.type,
            tags: [node.type, node.label.toLowerCase().replace(/\s+/g, '-')],
            code: node.generatedCode || '',
            source: 'learned',
            usageCount: 1,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
        };
        customDesigns.push(newDesign);
        save();
        return newDesign;
    },
    update(id, updates) {
        const idx = customDesigns.findIndex(n => n.id === id);
        if (idx === -1)
            return undefined;
        customDesigns[idx] = { ...customDesigns[idx], ...updates, updatedAt: new Date().toISOString() };
        save();
        return customDesigns[idx];
    },
    delete(id) {
        const idx = customDesigns.findIndex(n => n.id === id);
        if (idx === -1)
            return false;
        customDesigns.splice(idx, 1);
        save();
        return true;
    },
    count() {
        return builtInDesigns.length + customDesigns.length;
    },
    customCount() {
        return customDesigns.length;
    },
};
