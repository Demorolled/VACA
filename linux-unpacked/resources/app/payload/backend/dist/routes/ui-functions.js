/**
 * UI Functions Route
 * ===================
 *
 * When an app is being designed, this endpoint analyzes the app goal and nodes
 * and generates a list of needed UI buttons, controls, and functions.
 *
 * The LLM reasons about what GUI elements the app needs, and returns a
 * structured list that can be used for visual widget placement.
 *
 * Endpoints:
 *   POST /api/ui-functions/suggest  — Generate button/function list from design
 *   POST /api/ui-functions/finalize  — Take placed buttons and generate connection code
 */
import { Router } from 'express';
import { AITranslator } from '../ai/translator.js';
import { flattenSuggestedWidgets, deriveNodeId } from '../shared/designContract.js';
export const uiFunctionsRoutes = Router();
const translator = new AITranslator();
/**
 * Extract a JSON object from LLM response text using multiple fallback strategies.
 */
function extractJSONObject(text) {
    // Strategy 1: Try direct parse
    try {
        const r = JSON.parse(text);
        if (typeof r === 'object' && !Array.isArray(r))
            return r;
    }
    catch { }
    // Strategy 2: Try extracting from markdown code block
    const codeBlock = text.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
    if (codeBlock) {
        try {
            const r = JSON.parse(codeBlock[1]);
            if (typeof r === 'object' && !Array.isArray(r))
                return r;
        }
        catch { }
    }
    // Strategy 3: Try extracting first { ... } with greedy match
    const objMatch = text.match(/\{[\s\S]*\}/);
    if (objMatch) {
        try {
            const r = JSON.parse(objMatch[0]);
            if (typeof r === 'object' && !Array.isArray(r))
                return r;
        }
        catch { }
    }
    return null;
}
/**
 * Extract a JSON array from LLM response text using multiple fallback strategies.
 */
function extractJSONArray(text) {
    // Strategy 1: Try direct parse
    try {
        const r = JSON.parse(text);
        if (Array.isArray(r))
            return r;
    }
    catch { }
    // Strategy 2: Try extracting JSON array from text (greedy match to last ])
    const match = text.match(/\[[\s\S]*\]/);
    if (match) {
        try {
            const r = JSON.parse(match[0]);
            if (Array.isArray(r))
                return r;
        }
        catch { }
    }
    // Strategy 3: Try extracting from markdown code block
    const codeMatch = text.match(/```(?:json)?\n([\s\S]*?)```/);
    if (codeMatch) {
        try {
            const r = JSON.parse(codeMatch[1]);
            if (Array.isArray(r))
                return r;
        }
        catch { }
        try {
            const r = JSON.parse(codeMatch[1]);
            if (r.functions && Array.isArray(r.functions))
                return r.functions;
        }
        catch { }
    }
    // Strategy 4: Try to find any JSON array wrapped in objects
    try {
        const obj = JSON.parse(text);
        if (obj.functions && Array.isArray(obj.functions))
            return obj.functions;
        if (obj.suggestions && Array.isArray(obj.suggestions))
            return obj.suggestions;
        if (obj.items && Array.isArray(obj.items))
            return obj.items;
    }
    catch { }
    return null;
}
/**
 * Generate default UI function suggestions based on app name/goal.
 * Used as an ultimate fallback when the LLM fails to return valid JSON.
 */
function generateDefaultFunctions(appNameOrGoal) {
    const goal = appNameOrGoal.toLowerCase();
    const isMedia = goal.includes('media') || goal.includes('stream') || goal.includes('music') || goal.includes('video') || goal.includes('player');
    const isSocial = goal.includes('chat') || goal.includes('social') || goal.includes('message') || goal.includes('feed');
    const isProductivity = goal.includes('task') || goal.includes('todo') || goal.includes('note') || goal.includes('manage') || goal.includes('calendar');
    const isShopping = goal.includes('shop') || goal.includes('store') || goal.includes('ecom') || goal.includes('cart');
    const isData = goal.includes('dashboard') || goal.includes('analytics') || goal.includes('report') || goal.includes('chart');
    if (isMedia) {
        return [
            { label: 'Play/Pause', type: 'button', description: 'Toggle playback of current media', defaultAction: 'togglePlayback', category: 'media', zone: 'bottom' },
            { label: 'Volume Slider', type: 'slider', description: 'Adjust audio volume level', defaultAction: 'setVolume', category: 'media', zone: 'bottom' },
            { label: 'Skip Next', type: 'button', description: 'Skip to next track/media', defaultAction: 'nextTrack', category: 'media', zone: 'bottom' },
            { label: 'Skip Previous', type: 'button', description: 'Go to previous track', defaultAction: 'previousTrack', category: 'media', zone: 'bottom' },
            { label: 'Media Library', type: 'display', description: 'Browse and search media library', defaultAction: 'openLibrary', category: 'data', zone: 'main' },
            { label: 'Search', type: 'input', description: 'Search through media collection', defaultAction: 'searchMedia', category: 'data', zone: 'topbar' },
            { label: 'Settings', type: 'button', description: 'Open settings and preferences', defaultAction: 'openSettings', category: 'navigation', zone: 'topbar' },
            { label: 'Now Playing', type: 'display', description: 'Shows current track info and progress', defaultAction: 'showNowPlaying', category: 'media', zone: 'main' },
        ];
    }
    if (isProductivity) {
        return [
            { label: 'Add New', type: 'button', description: 'Create a new item', defaultAction: 'createItem', category: 'data', zone: 'topbar' },
            { label: 'Search', type: 'input', description: 'Search through items', defaultAction: 'searchItems', category: 'data', zone: 'topbar' },
            { label: 'Filter', type: 'toggle', description: 'Toggle filter options', defaultAction: 'toggleFilter', category: 'data', zone: 'sidebar' },
            { label: 'Save', type: 'button', description: 'Save current changes', defaultAction: 'saveChanges', category: 'utility', zone: 'topbar' },
            { label: 'Delete', type: 'button', description: 'Delete selected item', defaultAction: 'deleteItem', category: 'utility', zone: 'main' },
            { label: 'List View', type: 'display', description: 'Display items in a list', defaultAction: 'showList', category: 'data', zone: 'main' },
            { label: 'Settings', type: 'button', description: 'Open app settings', defaultAction: 'openSettings', category: 'navigation', zone: 'topbar' },
        ];
    }
    // Generic defaults
    return [
        { label: 'Home', type: 'button', description: 'Go to home screen', defaultAction: 'goHome', category: 'navigation', zone: 'topbar' },
        { label: 'Settings', type: 'button', description: 'Open app settings', defaultAction: 'openSettings', category: 'navigation', zone: 'topbar' },
        { label: 'Search', type: 'input', description: 'Search through content', defaultAction: 'search', category: 'data', zone: 'topbar' },
        { label: 'Submit', type: 'button', description: 'Submit current form', defaultAction: 'submitForm', category: 'utility', zone: 'bottom' },
        { label: 'Status', type: 'display', description: 'Shows current app status', defaultAction: 'showStatus', category: 'data', zone: 'main' },
        { label: 'Refresh', type: 'button', description: 'Refresh current view', defaultAction: 'refresh', category: 'utility', zone: 'topbar' },
        { label: 'Menu', type: 'button', description: 'Open navigation menu', defaultAction: 'toggleMenu', category: 'navigation', zone: 'sidebar' },
    ];
}
// ─── Shared prompt templates ──────────────────────────────────────
/**
 * Build the prompt used by both /suggest and /auto-place.
 * Asks the LLM to reason about the app, then output structured suggestions
 * linked to specific architect nodes with layout zone awareness.
 */
function getSuggestPrompt(goal, purpose, targetOS, nodeList) {
    return `I'm designing a "${goal || 'Untitled App'}"${purpose ? ` (${purpose})` : ''} for ${targetOS || 'linux'}.

The app has these architecture nodes/components:
${nodeList || '(none yet - just starting the design)'}

First, REASON step by step about what UI controls this app needs on its main screen.
Think about:
- What actions does the user need to perform? (navigation, CRUD, playback, settings, etc.)
- What data needs to be displayed? (status, lists, readouts, etc.)
- Which architecture node does each control connect to?
- What layout zone does each control belong to?

Then respond with a JSON object containing TWO fields:
1. "reasoning": a short paragraph explaining your design thinking
2. "functions": an array of UI control objects

Each control object has:
{
  "label": "short button label (e.g., Play/Pause)",
  "type": "button|slider|toggle|display|input|knob|label",
  "description": "what this control does in one sentence",
  "defaultAction": "the action it performs (e.g., togglePlayback)",
  "category": "navigation|media|data|settings|utility|auth|social",
  "linkedNodeLabel": "the exact node label this control connects to from the list above",
  "zone": "topbar|main|sidebar|bottom",
  "reasoning": "brief justification — why this control is needed"
}

Provide 6-15 specific, well-justified controls.

IMPORTANT: Respond with ONLY a JSON object — no markdown, no code fences, no explanations outside the JSON. The object must have "reasoning" (string) and "functions" (array) keys.`;
}
/**
 * Build the prompt for /auto-place which combines suggestion + positioning.
 * The LLM outputs a single JSON with reasoning, functions, AND layout.
 */
function getAutoPlacePrompt(goal, purpose, targetOS, nodeList) {
    return `I'm designing a "${goal || 'Untitled App'}"${purpose ? ` (${purpose})` : ''} for ${targetOS || 'linux'}.

The app has these architecture nodes/components:
${nodeList || '(none yet - just starting the design)'}

Step 1 — REASON about the UI controls needed.
Think about:
- Navigation (top bar: back, home, settings)
- Main content area (displays, lists, search)
- Bottom bar (playback controls, action buttons)
- Which architecture node each control connects to

Step 2 — POSITION each control on an 800×600 canvas.
Design a logical layout:
- TOP BAR (y: 8–60): navigation buttons, search input
- MAIN AREA (y: 70–480): displays, lists, status readouts
- BOTTOM BAR (y: 490–560): playback controls, primary action buttons
- SIDEBAR (x: 610–760): secondary settings, filters

Each control needs:
- Reasonable width/height for its type (buttons: 90–140×32–44, sliders: 160–280×28, displays: 180–400×60–200, inputs: 160–300×32, toggles: 44–64×28, knobs: 44–64×44, labels: 80–160×20–28)
- Non-overlapping placement with at least 8px gap between elements
- x constrained to 0–720, y constrained to 0–550
- x + width ≤ 800, y + height ≤ 600

Respond with ONLY a JSON object:
{
  "reasoning": "paragraph explaining your design",
  "functions": [
    {
      "label": "short button label",
      "type": "button|slider|toggle|display|input|knob|label",
      "description": "what this control does",
      "defaultAction": "the action",
      "category": "navigation|media|data|settings|utility|auth|social",
      "linkedNodeLabel": "exact node label from the list above",
      "zone": "topbar|main|sidebar|bottom",
      "reasoning": "why this control is needed",
      "x": number (0-720),
      "y": number (0-550),
      "width": number (40-400),
      "height": number (20-200)
    }
  ]
}

Provide 6-15 specific, well-positioned controls. Make positions reasonable and collision-free.`;
}
// ─── Zone-based fallback layout ──────────────────────────────────
/** Zones with y-range and description */
const LAYOUT_ZONES = {
    topbar: { yStart: 8, yEnd: 56, label: 'Top Navigation' },
    main: { yStart: 68, yEnd: 480, label: 'Main Content' },
    sidebar: { yStart: 68, yEnd: 480, label: 'Side Panel' },
    bottom: { yStart: 500, yEnd: 560, label: 'Bottom Controls' },
};
/** Preferred width for each widget type */
function getPreferredWidth(type) {
    switch (type) {
        case 'button': return 120;
        case 'slider': return 220;
        case 'toggle': return 56;
        case 'knob': return 52;
        case 'display': return 280;
        case 'input': return 220;
        case 'label': return 120;
        default: return 120;
    }
}
function getPreferredHeight(type) {
    switch (type) {
        case 'button': return 36;
        case 'slider': return 28;
        case 'toggle': return 28;
        case 'knob': return 52;
        case 'display': return 100;
        case 'input': return 32;
        case 'label': return 24;
        default: return 36;
    }
}
/**
 * Layout widgets on an 800×600 canvas grouped by zone.
 * Each zone uses columns, with collision avoidance.
 */
function layoutWidgetsByZone(functions) {
    // Assign zones if not provided — infer from category
    const zonedFuncs = functions.map(f => {
        let zone = f.zone || '';
        if (!zone || !(zone in LAYOUT_ZONES)) {
            // Infer zone from category
            if (f.category === 'navigation' || f.category === 'auth')
                zone = 'topbar';
            else if (f.category === 'media')
                zone = 'bottom';
            else if (f.category === 'data')
                zone = 'main';
            else if (f.type === 'display')
                zone = 'main';
            else if (f.type === 'slider' || f.type === 'knob')
                zone = 'bottom';
            else
                zone = 'main';
        }
        return { ...f, zone: zone };
    });
    // Determine how many columns per zone
    const zoneColumns = {
        topbar: 4,
        main: 2,
        sidebar: 1,
        bottom: 3,
    };
    // Track occupied rectangles for collision avoidance
    const occupied = [];
    function checkCollision(x, y, w, h) {
        const margin = 8; // minimum gap
        return occupied.some(r => x < r.x + r.w + margin &&
            x + w + margin > r.x &&
            y < r.y + r.h + margin &&
            y + h + margin > r.y);
    }
    function findFreeSlot(zone, w, h, col, totalCols) {
        const z = LAYOUT_ZONES[zone];
        const zoneWidth = zone === 'sidebar' ? 190 : 780;
        const colWidth = (zoneWidth - 16) / totalCols;
        const baseX = zone === 'sidebar' ? 610 : 8;
        let x = baseX + col * colWidth + 4;
        let y = z.yStart;
        // Try a few y positions to avoid collision
        for (let attempt = 0; attempt < 50; attempt++) {
            if (!checkCollision(x, y, w, h) && y + h <= z.yEnd) {
                break;
            }
            y += 4; // slide down
        }
        // Clamp y so it doesn't exceed the zone
        if (y + h > z.yEnd) {
            y = z.yStart;
            x += colWidth / 2; // shift right
        }
        occupied.push({ x, y, w, h });
        return { x, y };
    }
    return zonedFuncs.map((f, i) => {
        const zone = f.zone;
        const cols = zoneColumns[zone] || 3;
        // Spread items across columns based on their index
        const col = i % cols;
        const w = getPreferredWidth(f.type);
        const h = getPreferredHeight(f.type);
        // For main zone items, make displays wider
        const finalW = (f.type === 'display' && zone === 'main') ? Math.max(w, (780 / cols) - 16) : w;
        const { x, y } = findFreeSlot(zone, finalW, h, col, cols);
        return { label: f.label, x, y, width: finalW, height: h, type: f.type };
    });
}
/**
 * performAutoPlace
 * ================
 * Shared async function that runs suggest + auto-place logic.
 * Can be called directly by other routes
 * to generate UI functions and placed widgets without an HTTP round-trip.
 *
 * BEHAVIOR: If the nodes already have `suggestedWidgets` (from the new
 * architect LLM prompt), those are used directly — no extra LLM call.
 * Only falls back to the LLM auto-place call when nodes don't have
 * suggestedWidgets defined.
 *
 * Returns functions array, placedWidgets array, and summary metadata.
 */
export async function performAutoPlace(options) {
    const { goal, purpose, targetOS, nodes } = options;
    const validNodes = nodes || [];
    // ── Check if nodes have suggestedWidgets from the new architect prompt ──
    const contractNodes = validNodes
        .filter((n) => n.suggestedWidgets && Array.isArray(n.suggestedWidgets) && n.suggestedWidgets.length > 0)
        .map((n) => ({
        label: n.label || n.id || 'Node',
        description: n.description || '',
        type: n.type || 'logic',
        language: n.language || 'typescript',
        position: n.position || { x: 250, y: 250 },
        uiPorts: n.uiPorts,
        suggestedWidgets: n.suggestedWidgets,
    }));
    if (contractNodes.length > 0) {
        // Use the suggested widgets from the design contract — NO LLM CALL NEEDED
        console.log('[ui-functions] Auto-place: using', contractNodes.length, 'nodes with pre-defined suggestedWidgets');
        const placedWidgets = flattenSuggestedWidgets(contractNodes);
        const functions = placedWidgets.map((w, i) => ({
            id: w.id,
            label: w.label,
            type: w.type,
            description: w.description || '',
            defaultAction: w.archBindings?.onClick || w.archBindings?.onChange || '',
            category: w.category || 'utility',
            linkedNodeLabel: contractNodes.find(n => deriveNodeId(n.label) === w.nodeId)?.label || '',
            zone: w.zone || 'main',
            reasoning: w.archBindings?.onClick ? `Fires ${w.archBindings.onClick}` :
                w.archBindings?.displayInput ? `Displays ${w.archBindings.displayInput}` : '',
        }));
        return {
            functions,
            placedWidgets: placedWidgets.map(w => ({
                ...w,
                linkedNodeId: w.nodeId,
            })),
            appName: goal || 'Untitled',
            nodeCount: validNodes.length,
            widgetCount: placedWidgets.length,
        };
    }
    // ── Fallback: LLM-based auto-place (old flow, for nodes without suggestedWidgets) ──
    const nodeList = validNodes
        .map((n) => `- ${n.label || n.id} (${n.type}): ${n.description || 'No description'}`)
        .join('\n');
    // Single LLM call that does suggestion + positioning in one pass
    const autoPrompt = getAutoPlacePrompt(goal, purpose || '', targetOS || 'linux', nodeList);
    const autoResponse = await translator.reason(autoPrompt, undefined, { maxTokens: 3072 });
    // Parse combined JSON response
    let parsed = null;
    try {
        parsed = extractJSONObject(autoResponse);
    }
    catch { }
    if (!parsed) {
        const codeBlock = autoResponse.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
        if (codeBlock) {
            try {
                parsed = JSON.parse(codeBlock[1]);
            }
            catch { }
        }
    }
    if (!parsed) {
        const arr = extractJSONArray(autoResponse);
        if (arr) {
            parsed = { functions: arr };
        }
    }
    let functions = [];
    if (parsed?.functions && Array.isArray(parsed.functions) && parsed.functions.length > 0) {
        functions = parsed.functions;
        console.log('[ui-functions] Auto-place: parsed', functions.length, 'functions with positions from LLM');
    }
    // Validate and assign IDs
    const validatedFunctions = functions
        .filter((f) => f.label && f.type)
        .map((f, i) => ({
        label: f.label,
        type: ['button', 'slider', 'toggle', 'display', 'input', 'knob', 'label'].includes(f.type) ? f.type : 'button',
        description: f.description || '',
        defaultAction: f.defaultAction || '',
        category: f.category || 'utility',
        linkedNodeLabel: f.linkedNodeLabel || '',
        zone: f.zone || 'main',
        reasoning: f.reasoning || '',
        x: typeof f.x === 'number' ? f.x : -1,
        y: typeof f.y === 'number' ? f.y : -1,
        width: typeof f.width === 'number' ? f.width : getPreferredWidth(f.type || 'button'),
        height: typeof f.height === 'number' ? f.height : getPreferredHeight(f.type || 'button'),
    }));
    // If LLM returned functions with valid positions, use them directly
    let placements = [];
    if (validatedFunctions.length > 0 && validatedFunctions.every((f) => f.x >= 0 && f.y >= 0)) {
        placements = validatedFunctions.map((f) => ({
            label: f.label,
            x: f.x,
            y: f.y,
            width: f.width,
            height: f.height,
            type: f.type,
        }));
    }
    // Fallback: if LLM didn't give positions, use zone-based layout
    if (placements.length === 0) {
        if (validatedFunctions.length === 0) {
            console.log('[ui-functions] Auto-place: using default functions + zone layout fallback');
            const defaults = generateDefaultFunctions(goal || 'App');
            validatedFunctions.push(...defaults.map((f) => ({
                ...f,
                linkedNodeLabel: '',
                reasoning: '',
                x: -1, y: -1, width: 0, height: 0,
            })));
        }
        placements = layoutWidgetsByZone(validatedFunctions);
        console.log('[ui-functions] Auto-place: using zone-based layout for', placements.length, 'widgets');
    }
    // Assign persistent IDs
    const timestamp = Date.now();
    const finalFunctions = validatedFunctions.map((f, i) => ({
        label: f.label,
        type: f.type,
        description: f.description,
        defaultAction: f.defaultAction,
        category: f.category,
        linkedNodeLabel: f.linkedNodeLabel || '',
        zone: f.zone || 'main',
        reasoning: f.reasoning || '',
        id: `uifn_${timestamp}_${i}`,
    }));
    // Merge functions with placements
    const placedWidgets = finalFunctions.map((f, i) => {
        const pl = placements.find((p) => p.label === f.label) || placements[i] || {};
        return {
            id: f.id,
            label: f.label,
            type: f.type,
            description: f.description,
            defaultAction: f.defaultAction,
            category: f.category,
            x: pl.x || 30,
            y: pl.y || 40,
            width: pl.width || getPreferredWidth(f.type),
            height: pl.height || getPreferredHeight(f.type),
            linkedNodeId: f.linkedNodeLabel
                ? f.linkedNodeLabel.toLowerCase().replace(/\s+/g, '-')
                : f.id,
        };
    });
    return {
        functions: finalFunctions,
        placedWidgets,
        appName: goal || 'Untitled',
        nodeCount: (nodes || []).length,
        widgetCount: placedWidgets.length,
    };
}
/**
 * POST /api/ui-functions/suggest
 *
 * Takes an app design (goal, purpose, nodes) and uses the LLM to suggest
 * what UI buttons and controls the app needs.
 */
uiFunctionsRoutes.post('/suggest', async (req, res) => {
    try {
        const { goal, purpose, targetOS, nodes } = req.body;
        if (!goal && (!nodes || nodes.length === 0)) {
            res.status(400).json({ error: 'App goal or nodes are required' });
            return;
        }
        const nodeList = (nodes || [])
            .map((n) => `- ${n.label || n.id} (${n.type}): ${n.description || 'No description'}`)
            .join('\n');
        const prompt = getSuggestPrompt(goal, purpose, targetOS, nodeList);
        const response = await translator.reason(prompt, undefined, { maxTokens: 2048 });
        console.log('[ui-functions] Raw LLM response length:', response.length, 'First 300 chars:', response.substring(0, 300));
        // Parse enriched JSON response with reasoning + functions
        let reasoning = '';
        let rawFunctions = [];
        // Remove any common LLM preamble text before the JSON
        let cleanResponse = response.trim();
        // Try to find JSON object by scanning for { and matching }
        const firstBrace = cleanResponse.indexOf('{');
        const lastBrace = cleanResponse.lastIndexOf('}');
        if (firstBrace !== -1 && lastBrace > firstBrace) {
            cleanResponse = cleanResponse.substring(firstBrace, lastBrace + 1);
        }
        try {
            const parsed = extractJSONObject(cleanResponse);
            if (parsed) {
                reasoning = parsed.reasoning || '';
                rawFunctions = parsed.functions || parsed.items || parsed.suggestions || [];
                console.log('[ui-functions] Found', rawFunctions.length, 'functions via object parse');
            }
        }
        catch { }
        // Fallback: try extracting just an array
        if (!Array.isArray(rawFunctions) || rawFunctions.length === 0) {
            const arr = extractJSONArray(cleanResponse);
            if (arr) {
                rawFunctions = arr;
                console.log('[ui-functions] Found', rawFunctions.length, 'functions via array fallback');
            }
        }
        // Ultimate fallback: generate defaults
        if (!Array.isArray(rawFunctions) || rawFunctions.length === 0) {
            console.log('[ui-functions] Using generateDefaultFunctions fallback');
            const defaultFuncs = generateDefaultFunctions(goal || 'App');
            rawFunctions = defaultFuncs;
        }
        // Assign IDs and validate
        const validated = rawFunctions
            .filter(f => f.label && f.type)
            .map((f, i) => ({
            ...f,
            id: f.id || `uifn_${Date.now()}_${i}`,
            type: ['button', 'slider', 'toggle', 'display', 'input', 'knob', 'label'].includes(f.type)
                ? f.type
                : 'button',
            category: f.category || 'utility',
            linkedNodeLabel: f.linkedNodeLabel || f.linkedNode || '',
            zone: f.zone || '',
            reasoning: f.reasoning || '',
        }));
        res.json({
            success: true,
            reasoning,
            functions: validated,
            appName: goal || 'Untitled',
            nodeCount: (nodes || []).length,
        });
    }
    catch (err) {
        console.error('[ui-functions] Suggest error:', err);
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/ui-functions/finalize
 *
 * Takes the user's placed button/widget layout and generates the
 * connection code that wires the buttons to the node functions.
 */
uiFunctionsRoutes.post('/finalize', async (req, res) => {
    try {
        const { goal, purpose, targetOS, nodes, placedWidgets, connections } = req.body;
        if (!placedWidgets || placedWidgets.length === 0) {
            res.status(400).json({ error: 'Placed widgets are required' });
            return;
        }
        const widgetList = placedWidgets
            .map((w) => `- ${w.label} (${w.type}) at (${Math.round(w.x)}, ${Math.round(w.y)}): ${w.description || 'No description'}${w.linkedNodeId ? ` → linked to node: ${w.linkedNodeId}` : ''}`)
            .join('\n');
        const nodeList = (nodes || [])
            .map((n) => `- ${n.label || n.id} (${n.type}): ${n.description || ''}`)
            .join('\n');
        const connectionList = (connections || [])
            .map((c) => `- ${c.from || c.source} → ${c.to || c.target}`)
            .join('\n');
        const prompt = `I'm finalizing the UI for "${goal || 'My App'}"${purpose ? ` (${purpose})` : ''} on ${targetOS || 'linux'}.

NODE ARCHITECTURE:
${nodeList || '(no nodes defined)'}

PLACED UI WIDGETS/BUTTONS:
${widgetList}

CONNECTIONS:
${connectionList || '(none defined)'}

Generate the glue code that connects each UI widget to its corresponding node function.
For each widget-button, write the onClick/onChange handler that calls the right function.
For each display widget, write the update logic.
For sliders/toggles/knobs, write the value-change handlers.

Keep it practical. Use JavaScript/TypeScript syntax.
Respond with code ONLY — no markdown, no explanations.`;
        const response = await translator.reason(prompt, undefined, { maxTokens: 2048 });
        res.json({
            success: true,
            code: response,
            widgetCount: placedWidgets.length,
            nodeCount: (nodes || []).length,
        });
    }
    catch (err) {
        console.error('[ui-functions] Finalize error:', err);
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/ui-functions/auto-place
 *
 * Takes an app design, generates UI suggestions via LLM, then uses the LLM
 * to auto-position widgets on a canvas. Returns both suggestions and placed widgets
 * so they can be placed on the GUI canvas.
 */
uiFunctionsRoutes.post('/auto-place', async (req, res) => {
    try {
        const { goal, purpose, targetOS, nodes } = req.body;
        if (!goal && (!nodes || nodes.length === 0)) {
            res.status(400).json({ error: 'App goal or nodes are required' });
            return;
        }
        const result = await performAutoPlace({ goal, purpose, targetOS, nodes });
        res.json({
            success: true,
            functions: result.functions,
            placedWidgets: result.placedWidgets,
            appName: result.appName,
            nodeCount: result.nodeCount,
            widgetCount: result.widgetCount,
        });
    }
    catch (err) {
        console.error('[ui-functions] Auto-place error:', err);
        res.status(500).json({ error: err.message });
    }
});
/**
 * POST /api/ui-functions/connected-status
 *
 * Check which architect nodes have been connected to widgets.
 */
uiFunctionsRoutes.post('/connected-status', async (req, res) => {
    try {
        const { architectNodes, placedWidgets } = req.body;
        const status = (architectNodes || []).map((node) => {
            const nodeIdTag = String(node.id || node.label || '').toLowerCase().replace(/\s+/g, '-');
            const linkedWidget = (placedWidgets || []).find((w) => w.linkedNodeId === nodeIdTag);
            return {
                nodeId: node.id,
                nodeLabel: node.label,
                nodeType: node.type,
                connected: !!linkedWidget,
                linkedWidget: linkedWidget ? linkedWidget.label : null,
                widgetType: linkedWidget ? linkedWidget.type : null,
            };
        });
        res.json({
            success: true,
            connections: status,
            totalNodes: architectNodes?.length || 0,
            connectedCount: status.filter((s) => s.connected).length,
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message });
    }
});
