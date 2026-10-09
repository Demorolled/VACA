/**
 * RicoPatternStore — loads, indexes, and queries the Rico Semantics dataset.
 *
 * The Rico Semantics dataset (Google Research) contains ~500k human-verified
 * UI element annotations from ~66k Android app screens. Each element has:
 *   - Normalized coordinates [0,1]: xmin, ymin, xmax, ymax
 *   - Semantic label: e.g. "ICON_THREE_DOTS:MORE", "TEXT_INPUT", "BUTTON"
 *
 * This store indexes those patterns so the gui_builder tool can reference
 * real-world UI widget placement patterns in its generated designs.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const RICO_DIR = path.join(PROJECT_ROOT, 'data', 'rico', 'rico_semantics', 'data');
// ─── Label → Category mapping ──────────────────────────────────────────────
const LABEL_CATEGORY_MAP = {
    ICON: 'icon',
    BUTTON: 'action',
    TEXT_INPUT: 'input',
    LABEL: 'display',
    SWITCH: 'toggle',
    SLIDER: 'slider',
    IMAGE: 'display',
    CARD: 'display',
    LIST_ITEM: 'display',
    TOOLBAR: 'navigation',
    TAB: 'navigation',
    MENU_ITEM: 'navigation',
    CHECKBOX: 'toggle',
    RADIO: 'toggle',
    SPINNER: 'input',
    DROPDOWN: 'input',
    SEARCH: 'input',
    NAVIGATION: 'navigation',
    GROUP: 'container',
    BACKGROUND: 'container',
    DIVIDER: 'utility',
    PROGRESS: 'display',
    RATING: 'input',
    CHIP: 'action',
    AVATAR: 'display',
};
function classifyLabel(label) {
    // Extract type before colon (e.g. "ICON_THREE_DOTS:MORE" → "ICON")
    const colonIdx = label.indexOf(':');
    const rawType = colonIdx > 0 ? label.substring(0, colonIdx) : label;
    // Extract the base type (e.g. "ICON_THREE_DOTS" → "ICON")
    const underscoreIdx = rawType.indexOf('_');
    const baseType = underscoreIdx > 0 ? rawType.substring(0, underscoreIdx) : rawType;
    const category = LABEL_CATEGORY_MAP[baseType] || 'other';
    return { type: baseType, category };
}
/** Determine which zone a widget belongs to based on its normalized y-center */
function classifyZone(ymin, ymax) {
    const yCenter = (ymin + ymax) / 2;
    if (yCenter < 0.1)
        return 'topbar';
    if (yCenter > 0.85)
        return 'bottom';
    const xCenter = 0; // We don't check x here since zone classification for Rico is approximate
    return 'main';
}
// ─── Pattern Store ──────────────────────────────────────────────────────────
export class RicoPatternStore {
    screens = [];
    loaded = false;
    loadError = null;
    /** Stats indexed by base type */
    typeStats = new Map();
    /** Screens indexed by dominant type categories */
    screensByCategory = new Map();
    // ─── Loading ────────────────────────────────────────────────────────────
    /** Load all Rico Semantics JSON files from disk. Call once at startup. */
    load() {
        if (this.loaded)
            return;
        const categories = ['semantics', 'iconnet', 'grouping'];
        const splits = ['train.json', 'val.json', 'test.json'];
        let totalScreens = 0;
        let totalElements = 0;
        for (const category of categories) {
            for (const split of splits) {
                const filePath = path.join(RICO_DIR, category, split);
                if (!fs.existsSync(filePath)) {
                    console.warn(`[RicoPatternStore] File not found: ${filePath}`);
                    continue;
                }
                try {
                    const raw = fs.readFileSync(filePath, 'utf-8');
                    const screens = JSON.parse(raw);
                    if (!Array.isArray(screens)) {
                        console.warn(`[RicoPatternStore] Expected array in ${filePath}, got ${typeof screens}`);
                        continue;
                    }
                    for (const screen of screens) {
                        if (!screen.screen_elements || !Array.isArray(screen.screen_elements))
                            continue;
                        // Filter to only screens with valid elements
                        const validElements = screen.screen_elements.filter(e => typeof e.xmin === 'number' && typeof e.label === 'string');
                        if (validElements.length === 0)
                            continue;
                        this.screens.push({
                            screen_id: screen.screen_id,
                            screen_elements: validElements,
                        });
                        totalScreens++;
                        totalElements += validElements.length;
                    }
                }
                catch (err) {
                    console.warn(`[RicoPatternStore] Error loading ${filePath}: ${err}`);
                }
            }
        }
        console.log(`[RicoPatternStore] Loaded ${totalScreens} screens with ${totalElements} elements from ${categories.length} categories`);
        this.loaded = true;
        this.buildIndex();
    }
    // ─── Indexing ───────────────────────────────────────────────────────────
    buildIndex() {
        // Build type stats
        const typeBuckets = new Map();
        for (const screen of this.screens) {
            for (const el of screen.screen_elements) {
                const { type, category } = classifyLabel(el.label);
                const width = el.xmax - el.xmin;
                const height = el.ymax - el.ymin;
                const xCenter = (el.xmin + el.xmax) / 2;
                const yCenter = (el.ymin + el.ymax) / 2;
                const zone = classifyZone(el.ymin, el.ymax);
                if (!typeBuckets.has(type)) {
                    typeBuckets.set(type, {
                        widths: [],
                        heights: [],
                        centers: [],
                        zoneCounts: new Map(),
                    });
                }
                const bucket = typeBuckets.get(type);
                bucket.widths.push(width);
                bucket.heights.push(height);
                bucket.centers.push({ x: xCenter, y: yCenter });
                bucket.zoneCounts.set(zone, (bucket.zoneCounts.get(zone) || 0) + 1);
            }
        }
        const MIN_SAMPLES = 10;
        for (const [type, bucket] of typeBuckets) {
            if (bucket.widths.length < MIN_SAMPLES)
                continue;
            const total = bucket.widths.length;
            const avgWidth = bucket.widths.reduce((a, b) => a + b, 0) / total;
            const avgHeight = bucket.heights.reduce((a, b) => a + b, 0) / total;
            const avgXCenter = bucket.centers.reduce((a, c) => a + c.x, 0) / total;
            const avgYCenter = bucket.centers.reduce((a, c) => a + c.y, 0) / total;
            const zoneDistribution = {};
            for (const [zone, count] of bucket.zoneCounts) {
                zoneDistribution[zone] = count / total;
            }
            const { category } = classifyLabel(type);
            this.typeStats.set(type, {
                type,
                category,
                count: total,
                avgWidth,
                avgHeight,
                avgXCenter,
                avgYCenter,
                zoneDistribution,
            });
        }
        // Index screens by category (for sampling)
        this.screensByCategory = new Map();
        for (const screen of this.screens) {
            const categories = new Set();
            for (const el of screen.screen_elements) {
                const { category } = classifyLabel(el.label);
                categories.add(category);
            }
            for (const cat of categories) {
                if (!this.screensByCategory.has(cat)) {
                    this.screensByCategory.set(cat, []);
                }
                this.screensByCategory.get(cat).push(screen);
            }
        }
        console.log(`[RicoPatternStore] Indexed ${this.typeStats.size} widget types across ${this.screensByCategory.size} categories`);
    }
    // ─── Querying ──────────────────────────────────────────────────────────
    /** Get top N most common widget types with their stats */
    getTopWidgetTypes(limit = 15) {
        if (!this.loaded)
            this.load();
        return Array.from(this.typeStats.values())
            .sort((a, b) => b.count - a.count)
            .slice(0, limit);
    }
    /** Sample N random screens, optionally filtered by category relevance */
    getSampleScreens(count = 3, relevantTypes) {
        if (!this.loaded)
            this.load();
        if (this.screens.length === 0)
            return [];
        // If relevant types provided, try to find screens containing those types
        let pool = this.screens;
        if (relevantTypes && relevantTypes.length > 0) {
            const relevantScreens = this.screens.filter(screen => screen.screen_elements.some(el => {
                const { type } = classifyLabel(el.label);
                return relevantTypes.some(rt => type.includes(rt));
            }));
            if (relevantScreens.length > 0) {
                pool = relevantScreens;
            }
        }
        // Fisher-Yates shuffle and pick
        const shuffled = [...pool];
        for (let i = shuffled.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
        return shuffled.slice(0, count);
    }
    /** Get a formatted context block for LLM prompt injection */
    getContextForGoal(goal, deep = false) {
        if (!this.loaded)
            this.load();
        const topTypes = this.getTopWidgetTypes(deep ? 25 : 15);
        // Determine relevant types from the goal (simple keyword matching)
        const goalLower = goal.toLowerCase();
        const keywordTypeMap = {
            search: ['SEARCH', 'TEXT_INPUT'],
            filter: ['TEXT_INPUT', 'DROPDOWN'],
            player: ['BUTTON', 'SLIDER', 'TOOLBAR'],
            form: ['TEXT_INPUT', 'BUTTON', 'CHECKBOX', 'DROPDOWN'],
            chat: ['TEXT_INPUT', 'BUTTON', 'LABEL'],
            settings: ['SWITCH', 'SLIDER', 'DROPDOWN', 'CHECKBOX'],
            list: ['LIST_ITEM', 'LABEL', 'CARD'],
            media: ['IMAGE', 'BUTTON', 'SLIDER', 'PROGRESS'],
            nav: ['TAB', 'MENU_ITEM', 'NAVIGATION', 'TOOLBAR'],
            game: ['BUTTON', 'IMAGE', 'LABEL'],
            auth: ['TEXT_INPUT', 'BUTTON', 'LABEL'],
        };
        const relevantTypes = [];
        for (const [keyword, types] of Object.entries(keywordTypeMap)) {
            if (goalLower.includes(keyword)) {
                relevantTypes.push(...types);
            }
        }
        const sampleScreens = this.getSampleScreens(deep ? 5 : 2, relevantTypes.length > 0 ? relevantTypes : undefined);
        // Build zone examples
        const zoneExamples = [
            {
                zone: 'topbar (top 10%)',
                commonTypes: ['ICON', 'SEARCH', 'TAB', 'TOOLBAR', 'MENU_ITEM'],
                exampleLayout: 'Typically contains search bars (~80% width), navigation icons (~10% each), and app title',
            },
            {
                zone: 'main (middle 75%)',
                commonTypes: ['TEXT_INPUT', 'BUTTON', 'LABEL', 'IMAGE', 'CARD', 'LIST_ITEM'],
                exampleLayout: 'Primary content area with forms, lists, cards, and input fields',
            },
            {
                zone: 'bottom (bottom 15%)',
                commonTypes: ['BUTTON', 'TAB', 'NAVIGATION', 'PROGRESS'],
                exampleLayout: 'Action buttons, bottom navigation, progress bars, and controls',
            },
        ];
        const rawSampleScreens = sampleScreens.map(screen => ({
            screenId: screen.screen_id,
            elements: screen.screen_elements.slice(0, 15), // Limit to 15 elements per screen for context
        }));
        return {
            totalScreens: this.screens.length,
            totalElements: this.screens.reduce((sum, s) => sum + s.screen_elements.length, 0),
            topWidgetTypes: topTypes,
            zoneExamples,
            rawSampleScreens,
        };
    }
    /** Format the context as a readable text block for LLM prompt injection */
    formatContextForPrompt(context) {
        const parts = ['📱 RICO DATASET — REAL-WORLD UI PATTERNS'];
        parts.push('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
        parts.push(`Source: ${context.totalScreens.toLocaleString()} Android app screens`);
        parts.push(`Total UI elements indexed: ${context.totalElements.toLocaleString()}\n`);
        if (context.totalScreens > 30000)
            parts.push('🔬 DEEP RESEARCH — full dataset analyzed\n');
        parts.push('── Most Common Widget Types (by frequency) ──');
        const topN = context.topWidgetTypes.length > 15 ? 20 : 10;
        for (const stat of context.topWidgetTypes.slice(0, topN)) {
            const zoneStr = Object.entries(stat.zoneDistribution)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 2)
                .map(([z, p]) => `${z} ${(p * 100).toFixed(0)}%`)
                .join(', ');
            parts.push(`  ${stat.type.padEnd(18)} ${String(stat.count).padStart(6)} occurrences` +
                `  | avg ${(stat.avgWidth * 100).toFixed(1)}%×${(stat.avgHeight * 100).toFixed(1)}% of screen` +
                `  | zones: ${zoneStr}`);
        }
        parts.push('\n── Widget Placement by Zone ──');
        for (const zone of context.zoneExamples) {
            parts.push(`  ${zone.zone}:`);
            parts.push(`    Common: ${zone.commonTypes.join(', ')}`);
            parts.push(`    ${zone.exampleLayout}`);
        }
        if (context.rawSampleScreens.length > 0) {
            parts.push('\n── Sample Screen Layouts ──');
            for (const screen of context.rawSampleScreens) {
                parts.push(`  Screen ${screen.screenId} (${screen.elements.length} elements):`);
                // Group by zone for cleaner presentation
                const byZone = {};
                for (const el of screen.elements) {
                    const zone = classifyZone(el.ymin, el.ymax);
                    if (!byZone[zone])
                        byZone[zone] = [];
                    const xCenter = ((el.xmin + el.xmax) / 2 * 100).toFixed(0);
                    const yCenter = ((el.ymin + el.ymax) / 2 * 100).toFixed(0);
                    byZone[zone].push(`    ${el.label.padEnd(30)} pos(${xCenter}%, ${yCenter}%)  size(${((el.xmax - el.xmin) * 100).toFixed(1)}% × ${((el.ymax - el.ymin) * 100).toFixed(1)}%)`);
                }
                for (const [zone, items] of Object.entries(byZone)) {
                    parts.push(`    [${zone}]:`);
                    parts.push(...items.slice(0, 5)); // Limit to 5 per zone
                    if (items.length > 5) {
                        parts.push(`    ... and ${items.length - 5} more elements in this zone`);
                    }
                }
            }
        }
        parts.push('\n── Design Guidance from Rico Patterns ──');
        parts.push('  • Most screens use a topbar (icons/search) + main content + optional bottom action bar');
        parts.push('  • Buttons are typically placed in the bottom zone or centered in the main zone');
        parts.push('  • Text inputs and forms occupy the upper-main zone');
        parts.push('  • Lists and cards occupy the lower-main to mid-main zone');
        parts.push('  • Navigation controls (tabs, menu items) sit in topbar or bottom zone');
        parts.push('  • Toggles and switches are usually right-aligned with their labels');
        return parts.join('\n');
    }
    /** Check if the Rico dataset is available */
    isAvailable() {
        if (this.loaded)
            return true;
        // Quick check without full load
        const semanticsPath = path.join(RICO_DIR, 'semantics', 'train.json');
        return fs.existsSync(semanticsPath);
    }
}
// ─── Singleton ──────────────────────────────────────────────────────────────
let _instance = null;
export function getRicoPatternStore() {
    if (!_instance) {
        _instance = new RicoPatternStore();
        // Load on first access
        try {
            _instance.load();
        }
        catch (err) {
            console.warn('[RicoPatternStore] Failed to load on init:', err);
        }
    }
    return _instance;
}
