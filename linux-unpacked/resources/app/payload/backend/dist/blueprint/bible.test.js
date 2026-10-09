import { describe, it, expect } from 'vitest';
import { sanitizeWiring, blueprintToProject, matchBlueprint, lexicalHitCount, validateEdgesReferentialIntegrity, deriveModuleContracts, buildContractStub, findBlueprintFile, loadBlueprints } from './bible.js';
describe('findBlueprintFile (locates the live blueprint a scaffold promotion overwrites)', () => {
    it('finds the source file for a curated app_type', () => {
        const bp = loadBlueprints()[0];
        const file = findBlueprintFile(bp.app_type);
        expect(file).toBeTruthy();
        expect(file.endsWith('.json')).toBe(true);
    });
    it('returns null for an unknown app_type', () => {
        expect(findBlueprintFile('no_such_app_type_xyz')).toBeNull();
    });
});
describe('validateEdgesReferentialIntegrity', () => {
    it('flags edges whose source or target is not a known module (dangling)', () => {
        const wiring = [
            { source_module: 'core_engine', destination_module: 'data_store', data_passed: 'x' },
            { source_module: 'ghost_module', destination_module: 'data_store', data_passed: 'x' },
            { source_module: 'core_engine', destination_module: 'nope_missing', data_passed: 'x' },
        ];
        const known = ['ui_screens', 'core_engine', 'data_store'];
        const report = validateEdgesReferentialIntegrity(wiring, known);
        expect(report.dangling.length).toBe(2);
        expect(report.dangling[0].source_module).toBe('ghost_module');
        expect(report.dangling[1].destination_module).toBe('nope_missing');
        expect(report.kept.length).toBe(1);
        expect(report.kept[0].source_module).toBe('core_engine');
    });
    it('keeps every edge intact when all endpoints resolve', () => {
        const wiring = [
            { source_module: 'ui_screens', destination_module: 'core_engine', data_passed: 'r' },
            { source_module: 'core_engine', destination_module: 'data_store', data_passed: 's' },
        ];
        const report = validateEdgesReferentialIntegrity(wiring, ['ui_screens', 'core_engine', 'data_store']);
        expect(report.dangling.length).toBe(0);
        expect(report.kept.length).toBe(2);
    });
    it('treats empty/whitespace endpoints as dangling', () => {
        const report = validateEdgesReferentialIntegrity([{ source_module: '', destination_module: 'data_store', data_passed: 'x' }], ['data_store']);
        expect(report.dangling.length).toBe(1);
        expect(report.kept.length).toBe(0);
    });
});
describe('sanitizeWiring', () => {
    it('reverses UI-backwards edges (UI consumes from logic/data, never the reverse)', () => {
        const out = sanitizeWiring([
            { source_module: 'ui_screens', destination_module: 'core_engine', data_passed: 'requests' },
            { source_module: 'core_engine', destination_module: 'input_handler', data_passed: 'results' },
        ], 'test_app');
        // ui_screens → core_engine becomes core_engine → ui_screens (ui depends on engine)
        expect(out[0]).toEqual({ source_module: 'core_engine', destination_module: 'ui_screens', data_passed: 'requests' });
        // non-UI edges pass through untouched
        expect(out[1]).toEqual({ source_module: 'core_engine', destination_module: 'input_handler', data_passed: 'results' });
    });
    it('drops edges that would create a cycle', () => {
        const out = sanitizeWiring([
            { source_module: 'engine', destination_module: 'screens', data_passed: 'x' },
            { source_module: 'screens', destination_module: 'engine', data_passed: 'y' },
        ], 'test_app');
        expect(out).toHaveLength(1);
    });
    it('leaves a correct data→logic→ui flow untouched', () => {
        const out = sanitizeWiring([
            { source_module: 'data_store', destination_module: 'timer_core', data_passed: 'data' },
            { source_module: 'timer_core', destination_module: 'ui_screens', data_passed: 'ticks' },
        ], 'test_app');
        expect(out).toHaveLength(2);
        expect(out[0].source_module).toBe('data_store');
        expect(out[1].destination_module).toBe('ui_screens');
    });
});
describe('lexicalHitCount', () => {
    it('prefix-matches plural forms (recipes ≈ recipe)', () => {
        const bp = {
            app_type: 'recipe_manager',
            description: '',
            keywords: ['recipe', 'manager'],
            target_stack: { frontend: 'react', backend: 'node', database: 'sqlite' },
            architecture_checklist: ['ui'],
            wiring_graph: [],
        };
        expect(lexicalHitCount('organize and search my cooking recipes', bp)).toBeGreaterThanOrEqual(1);
    });
    it('ignores short common tokens like app', () => {
        const bp = {
            app_type: 'generic_fullstack_app',
            description: '',
            keywords: ['app'],
            target_stack: { frontend: 'react', backend: 'node', database: 'sqlite' },
            architecture_checklist: ['ui'],
            wiring_graph: [],
        };
        expect(lexicalHitCount('a simple todo app', bp)).toBe(0);
    });
});
describe('matchBlueprint (lexical-boosted, real bible data)', () => {
    it('routes a cooking/recipe goal to a cooking-domain app, not code_playground', () => {
        const goal = 'organize and search my cooking recipes with ingredients and ratings';
        const cands = matchBlueprint(goal, 5, 0.30);
        expect(cands.length).toBeGreaterThan(0);
        // Before the fix the winner was code_playground (~0.27) and the recipe
        // blueprints never entered the top-6. Now a cooking/recipe blueprint must
        // win and the unrelated playground must be gone entirely.
        expect(cands[0].blueprint.app_type).toMatch(/recipe|cooking/);
        expect(cands.some(c => c.blueprint.app_type === 'code_playground')).toBe(false);
    });
    it('prefers recipe_manager outright when the goal names it (recipe manager)', () => {
        const goal = 'a recipe manager app with ingredients and ratings';
        const cands = matchBlueprint(goal, 5, 0.30);
        expect(cands[0].blueprint.app_type).toMatch(/recipe/);
    });
    it('keeps strong semantic matches on top (pomodoro)', () => {
        const cands = matchBlueprint('a pomodoro timer with session history and stats', 3, 0.30);
        expect(cands[0].blueprint.app_type).toContain('pomodoro');
    });
    it('returns nothing below a high floor (pure weak matches fall back in the route)', () => {
        const cands = matchBlueprint('organize and search my cooking recipes with ingredients and ratings', 5, 0.9);
        expect(cands).toHaveLength(0);
    });
    it('routes a space-shooter arcade title to the shooter family, not a memory card game', () => {
        const cands = matchBlueprint('classic arcade game void raider', 5, 0.30);
        expect(cands.length).toBeGreaterThan(0);
        expect(cands[0].blueprint.app_type).toBe('void_raider');
        expect(cands.some(c => c.blueprint.app_type === 'memory_card_game_2')).toBe(false);
    });
    it('routes the bare title "void raider" DIRECTLY to the dedicated void_raider blueprint', () => {
        const cands = matchBlueprint('void raider', 5, 0.30);
        expect(cands.length).toBeGreaterThan(0);
        expect(cands[0].blueprint.app_type).toBe('void_raider');
    });
    it('the dedicated void_raider blueprint has its own wave/enemy-AI module list', () => {
        const cands = matchBlueprint('void raider', 5, 0.30);
        const bp = cands.find((c) => c.blueprint.app_type === 'void_raider').blueprint;
        expect(bp.architecture_checklist).toEqual([
            'Ship Controls',
            'Wave Manager',
            'Enemy AI',
            'Combat Engine',
            'Game Renderer',
        ]);
        // Acyclic wiring: the sanitized project must yield a buildable DAG.
        const project = blueprintToProject(bp, { goal: 'void raider' });
        expect(project.nodes).toHaveLength(bp.architecture_checklist.length + 1);
        expect(project.edges).toHaveLength(4);
    });
    it('does not route a plain "classic game" to a memory card game via the generic descriptor', () => {
        // "classic" is a generic descriptor, not a domain — a memory card game
        // must not win solely because its keywords contain the word "classic".
        const cands = matchBlueprint('classic game', 5, 0.30);
        expect(cands[0].blueprint.app_type).not.toBe('memory_card_game_2');
    });
});
describe('blueprintToProject', () => {
    const bp = {
        app_type: 'pomodoro_timer_3',
        description: 'pomodoro timer',
        keywords: ['timer'],
        target_stack: { frontend: 'react', backend: 'node', database: 'sqlite' },
        architecture_checklist: ['ui_screens', 'core_engine', 'input_handler', 'data_store', 'timer_core'],
        wiring_graph: [
            { source_module: 'ui_screens', destination_module: 'core_engine', data_passed: 'requests' },
            { source_module: 'core_engine', destination_module: 'input_handler', data_passed: 'results' },
            { source_module: 'input_handler', destination_module: 'data_store', data_passed: 'state_and_events' },
            { source_module: 'data_store', destination_module: 'timer_core', data_passed: 'data' },
        ],
    };
    it('builds a DAG where the UI node depends on the engine (edge engine → ui)', () => {
        const project = blueprintToProject(bp, { goal: 'pomodoro timer' });
        const uiNode = project.nodes.find(n => n.data.label === 'ui_screens');
        const engineNode = project.nodes.find(n => n.data.label === 'core_engine');
        // edge source_module → destination_module means destination depends on source,
        // so after sanitization the edge must be engine → ui (ui depends on engine).
        const edge = project.edges.find(e => e.source === engineNode.id && e.target === uiNode.id);
        expect(edge).toBeTruthy();
    });
    it('bakes the sanitized wiring into the fused blueprint context', () => {
        const project = blueprintToProject(bp, { goal: 'pomodoro timer' });
        const master = project.nodes.find(n => n.type === 'master');
        const ctx = master.data.blueprintContext;
        expect(ctx).toContain('core_engine → ui_screens');
        expect(ctx).not.toContain('ui_screens → core_engine');
    });
    it('creates one node per checklist module plus the master', () => {
        const project = blueprintToProject(bp, { goal: 'pomodoro timer' });
        expect(project.nodes).toHaveLength(bp.architecture_checklist.length + 1);
    });
    it('injects researchContext into the master blueprint context (fused into every module prompt)', () => {
        const research = '📋 Reference designs found from the web, GitHub, and open source alternatives:\n  • Void Raiders — arcade space shooter with escalating waves';
        const project = blueprintToProject(bp, { goal: 'pomodoro timer', researchContext: research });
        const master = project.nodes.find(n => n.type === 'master');
        const ctx = master.data.blueprintContext;
        expect(ctx).toContain('DESIGN RESEARCH (live web search');
        expect(ctx).toContain('Void Raiders — arcade space shooter');
    });
    it('leaves blueprint context untouched when no research is provided', () => {
        const plain = blueprintToProject(bp, { goal: 'pomodoro timer' });
        const withResearch = blueprintToProject(bp, { goal: 'pomodoro timer', researchContext: 'some research' });
        const plainCtx = plain.nodes.find(n => n.type === 'master').data.blueprintContext;
        const researchCtx = withResearch.nodes.find(n => n.type === 'master').data.blueprintContext;
        expect(plainCtx).not.toContain('DESIGN RESEARCH');
        expect(researchCtx).toContain('some research');
    });
    it('injects internalKnowledgeContext into the master blueprint context alongside research', () => {
        const project = blueprintToProject(bp, {
            goal: 'pomodoro timer',
            researchContext: 'web refs',
            internalKnowledgeContext: '🧠 pattern: pomodoro 5-module | 📗 wiki: section 9',
        });
        const master = project.nodes.find(n => n.type === 'master');
        const ctx = master.data.blueprintContext;
        expect(ctx).toContain('VACA INTERNAL KNOWLEDGE (patterns + wiki');
        expect(ctx).toContain('🧠 pattern: pomodoro 5-module');
        expect(ctx).toContain('DESIGN RESEARCH');
        expect(ctx).toContain('web refs');
    });
    it('omits the internal-knowledge section when no internal context is provided', () => {
        const project = blueprintToProject(bp, { goal: 'pomodoro timer' });
        const ctx = project.nodes.find(n => n.type === 'master').data.blueprintContext;
        expect(ctx).not.toContain('VACA INTERNAL KNOWLEDGE');
    });
});
describe('deriveModuleContracts (contract stubs)', () => {
    const wiring = [
        { source_module: 'ui_screens', destination_module: 'core_engine', data_passed: 'requests' },
        { source_module: 'core_engine', destination_module: 'input_handler', data_passed: 'results' },
        { source_module: 'input_handler', destination_module: 'data_store', data_passed: 'state_and_events' },
        { source_module: 'data_store', destination_module: 'timer_core', data_passed: 'data' },
    ];
    it('derives importers (who imports FROM the module) from edges where it is the source', () => {
        // edge core_engine → input_handler means input_handler imports FROM core_engine
        const c = deriveModuleContracts(wiring, 'core_engine');
        expect(c.importers.map(i => i.module)).toContain('input_handler');
        expect(c.importers.find(i => i.module === 'input_handler')?.data).toBe('results');
        expect(c.dependencies.map(d => d.module)).toContain('ui_screens');
        expect(c.dependencies.find(d => d.module === 'ui_screens')?.data).toBe('requests');
    });
    it('leaf modules have no importers; entry modules have no dependencies', () => {
        const leaf = deriveModuleContracts(wiring, 'timer_core');
        expect(leaf.importers).toHaveLength(0);
        expect(leaf.dependencies.map(d => d.module)).toEqual(['data_store']);
        const entry = deriveModuleContracts(wiring, 'ui_screens');
        expect(entry.dependencies).toHaveLength(0);
        expect(entry.importers.map(i => i.module)).toEqual(['core_engine']);
    });
    it('handles modules absent from the wiring graph (empty contract)', () => {
        const c = deriveModuleContracts(wiring, 'ghost_module');
        expect(c.importers).toHaveLength(0);
        expect(c.dependencies).toHaveLength(0);
    });
    it('buildContractStub names the importers and the anti-global rules', () => {
        const stub = buildContractStub(deriveModuleContracts(wiring, 'core_engine'));
        expect(stub).toContain('core_engine');
        expect(stub).toContain('input_handler');
        expect(stub).toContain('You MUST export the functions/classes these modules call');
        expect(stub).toContain('NEVER reference a variable/function/DOM element');
        expect(stub).toContain('ALL state must be function parameters and return values');
        expect(stub).toContain('non-UI module must NEVER touch the DOM');
    });
    it('assigns SHARED-TYPE OWNERSHIP: a source module owns the types it passes to importers', () => {
        // data_store → timer_core : data — data_store owns the `data` contract type.
        const owner = buildContractStub(deriveModuleContracts(wiring, 'data_store'));
        expect(owner).toContain('SHARED-TYPE OWNERSHIP');
        expect(owner).toContain('you own the data types you pass to timer_core');
        expect(owner).toContain('define each such type/interface in THIS file and export it');
        // A module with only dependencies must NOT claim ownership; it must USE the
        // dependency's exported types instead.
        const consumer = buildContractStub(deriveModuleContracts(wiring, 'timer_core'));
        expect(consumer).not.toContain('SHARED-TYPE OWNERSHIP');
        expect(consumer).toContain('The data types of those contracts are OWNED by the modules listed above');
    });
    it('a module that both imports and exports gets both shared-type directions', () => {
        // input_handler → data_store : state_and_events (owner side) AND
        // core_engine → input_handler : results (consumer side).
        const both = buildContractStub(deriveModuleContracts(wiring, 'input_handler'));
        expect(both).toContain('SHARED-TYPE OWNERSHIP');
        expect(both).toContain('you own the data types you pass to data_store');
        expect(both).toContain('The data types of those contracts are OWNED by the modules listed above');
        expect(both).toContain('TS2304');
    });
});
describe('blueprintToProject contract stubs', () => {
    const bp = {
        app_type: 'pomodoro_timer_3',
        description: 'pomodoro timer',
        keywords: ['timer'],
        target_stack: { frontend: 'react', backend: 'node', database: 'sqlite' },
        architecture_checklist: ['ui_screens', 'core_engine', 'input_handler', 'data_store', 'timer_core'],
        wiring_graph: [
            { source_module: 'ui_screens', destination_module: 'core_engine', data_passed: 'requests' },
            { source_module: 'core_engine', destination_module: 'input_handler', data_passed: 'results' },
            { source_module: 'input_handler', destination_module: 'data_store', data_passed: 'state_and_events' },
            { source_module: 'data_store', destination_module: 'timer_core', data_passed: 'data' },
        ],
    };
    it('stamps a contractContext on every module node', () => {
        const project = blueprintToProject(bp, { goal: 'pomodoro timer' });
        for (const mod of bp.architecture_checklist) {
            const node = project.nodes.find(n => n.data.label === mod);
            expect(node.data.contractContext).toBeTruthy();
            expect(node.data.contractContext).toContain(`MODULE CONTRACT for "${mod}"`);
        }
    });
    it('engine node contract names its real importer (input_handler) and dependency (ui_screens)', () => {
        const project = blueprintToProject(bp, { goal: 'pomodoro timer' });
        const engine = project.nodes.find(n => n.data.label === 'core_engine');
        expect(engine.data.contractContext).toContain('input_handler (results)');
        expect(engine.data.contractContext).toContain('ui_screens (requests)');
    });
});
