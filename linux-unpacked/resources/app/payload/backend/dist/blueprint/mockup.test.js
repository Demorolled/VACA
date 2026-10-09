import { describe, it, expect } from 'vitest';
import { buildGuiMockupHtml, moduleNodeType, compareModulesToFiles } from './mockup.js';
const SAMPLE_BLUEPRINT = {
    app_type: 'pomodoro_timer_3',
    description: 'A pomodoro timer with session history and stats',
    keywords: ['timer', 'pomodoro'],
    target_stack: { frontend: 'react', backend: 'node', database: 'sqlite' },
    architecture_checklist: ['ui_screens', 'core_engine', 'input_handler', 'data_store'],
    wiring_graph: [
        { source_module: 'core_engine', destination_module: 'ui_screens', data_passed: 'tick' },
        { source_module: 'data_store', destination_module: 'core_engine', data_passed: 'state' },
    ],
};
describe('compareModulesToFiles (blueprint drift)', () => {
    it('reports clean when every promised module produced a file', () => {
        const report = compareModulesToFiles(['ui_screens', 'core_engine'], [
            { nodeId: 'mod_0', nodeLabel: 'ui_screens' },
            { nodeId: 'mod_1', nodeLabel: 'core_engine' },
        ]);
        expect(report.clean).toBe(true);
        expect(report.missing).toEqual([]);
        expect(report.matched).toHaveLength(2);
    });
    it('flags promised modules that never generated a file', () => {
        const report = compareModulesToFiles(['ui_screens', 'core_engine', 'data_store'], [
            { nodeId: 'mod_0', nodeLabel: 'ui_screens' },
            { nodeId: 'mod_1', nodeLabel: 'core_engine' },
        ]);
        expect(report.clean).toBe(false);
        expect(report.missing).toEqual(['data_store']);
    });
    it('flags files that match no promised module', () => {
        const report = compareModulesToFiles(['ui_screens'], [
            { nodeId: 'mod_0', nodeLabel: 'ui_screens' },
            { nodeId: 'mod_9', nodeLabel: 'mystery_module' },
        ]);
        expect(report.clean).toBe(false);
        expect(report.unexpected).toEqual(['mystery_module']);
    });
    it('ignores the auto preview wrapper (not a promised module)', () => {
        const report = compareModulesToFiles(['ui_screens'], [
            { nodeId: 'mod_0', nodeLabel: 'ui_screens' },
            { nodeId: 'preview_gui_wrapper', nodeLabel: 'App Preview (Auto-generated)' },
        ]);
        expect(report.clean).toBe(true);
        expect(report.unexpected).toEqual([]);
    });
    it('matches case-insensitively so label drift does not false-positive', () => {
        const report = compareModulesToFiles(['UI_Screens'], [{ nodeId: 'mod_0', nodeLabel: 'ui_screens' }]);
        expect(report.clean).toBe(true);
    });
    it('handles empty inputs without crashing', () => {
        const report = compareModulesToFiles([], []);
        expect(report.clean).toBe(true);
        expect(report.matched).toEqual([]);
        expect(report.missing).toEqual([]);
    });
});
describe('moduleNodeType', () => {
    it('classifies UI-ish modules as ui', () => {
        expect(moduleNodeType('ui_screens')).toBe('ui');
        expect(moduleNodeType('widget renderer')).toBe('ui');
    });
    it('classifies storage modules as database', () => {
        expect(moduleNodeType('data_store')).toBe('database');
    });
    it('defaults to logic', () => {
        expect(moduleNodeType('core_engine')).toBe('logic');
    });
});
describe('buildGuiMockupHtml', () => {
    it('is deterministic — same input yields identical output', () => {
        const a = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { purpose: 'stay focused' });
        const b = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { purpose: 'stay focused' });
        expect(a).toBe(b);
    });
    it('renders every architecture module into the sidebar and card grid', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer');
        for (const mod of SAMPLE_BLUEPRINT.architecture_checklist) {
            expect(html).toContain(mod);
        }
        // Sidebar nav items + card titles both reference the modules.
        expect(html.split('nav-item').length - 1).toBeGreaterThanOrEqual(4);
        expect(html.split('class="card"').length - 1).toBeGreaterThanOrEqual(4);
    });
    it('renders the wiring graph as a data-flow strip', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer');
        expect(html).toContain('Data Flow');
        expect(html).toContain('core_engine');
        expect(html).toContain('ui_screens');
        expect(html).toContain('flow-arrow');
    });
    it('embeds the goal as the app name and purpose in the hero', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'My Pomodoro', { purpose: 'Focus sessions' });
        expect(html).toContain('My Pomodoro');
        expect(html).toContain('Focus sessions');
    });
    it('escapes HTML in goal/purpose so nothing can inject markup', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, '<script>alert(1)</script>', { purpose: '"><img src=x>' });
        expect(html).not.toContain('<script>alert(1)</script>');
        expect(html).toContain('&lt;script&gt;');
        expect(html).not.toContain('<img src=x>');
    });
    it('emits a self-contained page with inline CSS (works in an iframe)', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer');
        expect(html).toContain('<!DOCTYPE html>');
        expect(html).toContain('<style>');
        expect(html).toContain('</style>');
        // No external file references — the preview iframe has no filesystem.
        expect(html).not.toMatch(/<script[^>]*src=/);
        expect(html).not.toMatch(/<link[^>]*href=/);
    });
    it('handles a blueprint with empty wiring (no data-flow section)', () => {
        const bare = {
            ...SAMPLE_BLUEPRINT,
            wiring_graph: [],
        };
        const html = buildGuiMockupHtml(bare, 'pomodoro timer');
        expect(html).not.toContain('Data Flow');
        // The flow SECTION (with its node/arrow markup) is omitted entirely;
        // only the shared CSS rules (.flow, .flow-node) remain in the stylesheet.
        expect(html).not.toContain('<div class="flow">');
    });
    it('handles an empty checklist gracefully', () => {
        const bare = {
            ...SAMPLE_BLUEPRINT,
            architecture_checklist: [],
        };
        const html = buildGuiMockupHtml(bare, 'pomodoro timer');
        expect(html).toContain('<!DOCTYPE html>');
    });
    it('applies a requested theme color', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { theme: 'rose' });
        expect(html).toContain('#f472b6'); // rose accent
        // The default deterministic palette for this blueprint differs from rose.
        const def = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer');
        expect(def).not.toContain('#f472b6');
    });
    it('falls back to a deterministic palette for an unknown theme id', () => {
        const a = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { theme: 'nope' });
        const b = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { theme: 'nope' });
        expect(a).toBe(b);
    });
    it('renders the dashboard layout with stat cards', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { layout: 'dashboard' });
        expect(html).toContain('stat-card');
        expect(html).toContain('Overview');
        expect(html).toContain('Dashboard');
    });
    it('renders the topnav layout with horizontal navigation', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { layout: 'topnav' });
        expect(html).toContain('topnav-brand');
        expect(html).toContain('topnav-item');
        // No left sidebar in topnav mode.
        expect(html).not.toContain('class="sidebar"');
    });
    it('defaults to the sidebar layout for an unknown layout id', () => {
        const html = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { layout: 'bogus' });
        expect(html).toContain('class="sidebar"');
    });
    it('is deterministic per (theme, layout) combination', () => {
        const a = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { theme: 'emerald', layout: 'dashboard' });
        const b = buildGuiMockupHtml(SAMPLE_BLUEPRINT, 'pomodoro timer', { theme: 'emerald', layout: 'dashboard' });
        expect(a).toBe(b);
    });
});
