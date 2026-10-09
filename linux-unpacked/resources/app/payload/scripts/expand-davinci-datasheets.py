#!/usr/bin/env python3
"""Expand the small davinci datasheets with rich training entries."""

import json
import time
from pathlib import Path

TRAINER_DIR = Path("/media/final-flash1/a47f2c6e-f5fa-4e60-bcea-95767738c074/MindSpace/trainer")
if not TRAINER_DIR.is_dir():
    print(f"ERROR: Trainer directory not found: {TRAINER_DIR}")
    raise SystemExit(1)

TS = time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def e(text, title, language, tags, nodeType="knowledge", source="davinci-integration-expanded", category="davinci"):
    """Build a training entry dict with all required schema fields."""
    return {
        "text": text,
        "title": title,
        "language": language,
        "tags": tags,
        "nodeType": nodeType,
        "source": source,
        "category": category,
        "timestamp": TS,
    }

DAVINCI_INTEGRATION = [
    # ── Bridge API / Protocol ──
    e("The Davinci Bridge API uses POST /api/bridge/nodes to receive architect node definitions. The payload includes node id, label, type, description, and position. Nodes are stored in the engine's node registry and can be referenced by widgets through archBindings. Response returns received:true and the assigned node count.",
      "Bridge Node Receiving Protocol", "python",
      ["davinci", "bridge", "nodes", "api", "integration"]),

    e("POST /api/bridge/nodes response format: {received: bool, nodeCount: int}. On failure: {received: false, error: string}. The bridge validates each node for required fields (id, label, type). Nodes with missing fields are rejected and counted in a separate rejectedNodes array in the response. The bridge also checks for duplicate node IDs and updates existing nodes instead of creating new ones.",
      "Bridge Node Receive Response Format", "python",
      ["davinci", "bridge", "nodes", "response", "validation"]),

    e("The bridge API node pulling endpoint GET /api/bridge/nodes returns all currently registered architect nodes as a JSON array. Each node includes: id, label, type, description, language, position {x,y}. This is used by the Davinci frontend to display connected nodes and by the autoPlace system to generate appropriate widget suggestions. The endpoint supports ?since=timestamp for incremental sync.",
      "Bridge Node Pull Endpoint", "python",
      ["davinci", "bridge", "nodes", "api", "pull"]),

    # ── Widget Placement / Layout ──
    e("Widget placement in Davinci follows layout zones: topbar (y: 8), main (y: 68, x: 8-600), sidebar (x: 610, y: 68-480), and bottom (y: 500). Each zone has defined boundaries. Widgets auto-arrange in columns of 3 within their zone. The performAutoPlace function reads the design goal and uses LLM to suggest widget types, labels, and placements.",
      "Widget Auto-Placement Strategy", "python",
      ["davinci", "widgets", "layout", "ui", "auto-place"]),

    e("The layoutZonePositions function assigns each widget a position within its zone. Topbar widgets are arranged horizontally (x: 8 + col*130, y: 8). Main zone widgets use a 3-column grid with column width 190px and row height 80px. Sidebar widgets stack vertically with 4px spacing. Bottom widgets stretch full width. Positions include a 4px margin for visual separation and collision avoidance.",
      "Layout Zone Position Calculation", "python",
      ["davinci", "layout", "positions", "zones", "calculation"]),

    e("The LLM autoPlace system prompt instructs the AI to: (1) Analyze the design goal and architect nodes. (2) Select widget types appropriate for the design (buttons for actions, displays for output, sliders for adjustments, toggles for binary settings, inputs for text entry). (3) Place widgets in logical zones. (4) Return a JSON array with type, label, zone, and optional action/displayInput. The system prompt includes the layout zone boundaries and available widget types.",
      "AutoPlace LLM System Prompt", "python",
      ["davinci", "autoplace", "llm", "prompt", "widgets"]),

    # ── Build Lifecycle ──
    e("Build management in the Davinci Bridge follows a lifecycle: (1) POST /api/bridge/builds creates a build with placedWidgets, architectNodes, and UI functions. (2) The build sits in pending state. (3) POST /api/bridge/builds/{id}/apply activates it - widgets are rendered on the canvas, architect bindings are wired. (4) POST /api/bridge/builds/clear resets for the next design. Each build tracks widget_count, arch_binding_count, and node_count metadata.",
      "Build Lifecycle Management", "python",
      ["davinci", "builds", "lifecycle", "bridge", "widgets"]),

    e("The build POST payload schema: {appName: string, goal: string, architectNodes: [{id, label, type, description}], placedWidgets: [{type, label, zone, action?}], uiFunctions: [{type, title, code, language}], archBindings: [{widgetId, nodeId, binding, handler}], targetOS: string}. The bridge validates the payload, assigns build IDs in format build_{timestamp}, and stores to architect_builds.json.",
      "Build Payload Schema", "python",
      ["davinci", "builds", "payload", "schema", "validation"]),

    e("Build status transitions: pending (initial state after POST) -> applied (after POST /apply) -> dismissed (after POST /dismiss). Each transition is logged with a timestamp. Applied builds can be reverted by applying a previous build (which snapshots current state). Dismissed builds are soft-deleted (kept in history but filtered from active list). Builds can be permanently deleted via DELETE /api/bridge/builds/{id} which removes the entry from the build file.",
      "Build Status Transitions", "python",
      ["davinci", "builds", "status", "transitions", "lifecycle"]),

    # ── WebSocket Protocol ──
    e("Architect-to-Davinci WebSocket integration uses ws://localhost:8000/ws/architect. Message types include: push_nodes (sync architect node positions to Davinci canvas), push_ui_functions (trigger autoPlace suggestions), push_build (send a complete build with widgets), push_full_design (full project sync including goal, purpose, nodes, widgets, and UI functions). Each message has a type field and optional payload with designId and projectId.",
      "WebSocket Real-time Protocol", "python",
      ["davinci", "websocket", "realtime", "protocol", "sync"]),

    e("WebSocket message format: {type: string, payload: {designId: string, projectId?: string, data: object}, timestamp: ISO string}. The server validates the type field against known types and returns an acknowledgement: {type: 'ack', payload: {received: true, messageId: string}}. If the type is unknown, it returns {type: 'error', payload: {error: 'unknown message type', receivedType: string}}. The WebSocket connection uses keep-alive pings every 30 seconds.",
      "WebSocket Message Format", "python",
      ["davinci", "websocket", "messages", "format", "protocol"]),

    e("WebSocket reconnection strategy: On disconnect, the client retries with exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s. On reconnect, the client sends a handshake with the last known build ID to recover state. The server replays any missed messages from its buffer (up to 100 messages). If the buffer is exhausted, the client requests a full state sync via GET /api/bridge/state.",
      "WebSocket Reconnection Strategy", "python",
      ["davinci", "websocket", "reconnection", "backoff", "sync"]),

    # ── Persistence / Storage ──
    e("The architect_builds.json file stores all pushed builds from the Visual AI Architect. The format is a JSON list where each entry has: id (auto-generated build_timestamp), appName, goal, nodeCount, widgetCount, status (pending/applied/dismissed), architectNodes array with id/label/type, placedWidgets array, uiFunctions array, archBindings array, and timestamps for created and applied. The engine reads this file on startup and on every push.",
      "Build Persistence Format", "json",
      ["davinci", "builds", "persistence", "storage", "json"]),

    e("Build file write strategy: The architect_builds.json file uses atomic writes (write to .tmp, then rename). File locking prevents concurrent write conflicts. On read failure (corrupted JSON), a backup is restored from architect_builds.json.bak. If no backup exists, an empty builds array is returned. The file is flushed to disk after every write with os.fsync for crash safety.",
      "Build File Atomic Write Strategy", "python",
      ["davinci", "builds", "file", "atomic", "persistence"]),

    e("Build history pruning: To prevent the builds file from growing unbounded, old builds are pruned when the file exceeds 100 entries. The pruning strategy keeps: all pending builds (highest priority), last 10 applied builds (for rollback), no dismissed builds older than 7 days. Pruned builds are archived to architect_builds.archive.json with a timestamp. The archive can be restored via POST /api/bridge/builds/restore-archive.",
      "Build History Pruning Strategy", "python",
      ["davinci", "builds", "pruning", "archive", "history"]),

    # ── Widget Library ──
    e("The Davinci Widget Library provides preset widget configurations organized by category. Each preset includes: id, name, type (button, display, slider, toggle, input), default dimensions, styleId (bs1-bs8 for color variants), icon, category label, tags, and default props. The library is loaded at startup via GET /api/library/widgets and individual presets via GET /api/library/widgets/{preset_id}. Style presets control background, border, text color, and hover effects.",
      "Widget Library Preset System", "python",
      ["davinci", "widgets", "library", "presets", "styles"]),

    e("Widget library search: GET /api/library/widgets/search?q=keyword&type=button&category=input returns filtered presets. Search matches against name, tags, and category fields. Results are ranked by relevance (exact name match > tag match > category match). Results include preset metadata and a preview thumbnail URL. The endpoint supports pagination with ?page=1&perPage=20. Total result count is returned in the X-Total-Count header.",
      "Widget Library Search Endpoint", "python",
      ["davinci", "widgets", "library", "search", "api"]),

    e("Widget library style definition format: {styleId: string, name: string, background: hex, textColor: hex, borderColor: hex, borderRadius: px, hoverDarken: percent, activeScale: percent, boxShadow: string}. Each style can optionally specify dark mode overrides. Styles are defined in widget_library.py and exposed via GET /api/library/styles. Custom styles can be registered at runtime via POST /api/library/styles.",
      "Widget Style Definition Format", "json",
      ["davinci", "styles", "widgets", "definition", "format"]),

    # ── Error Handling ──
    e("Error handling in the Davinci Bridge follows consistent patterns: push failures return {received: false, error: message}. Build apply errors return {ok: false, widgets_applied: 0, error: description}. Missing build IDs return 404. The architect frontend handles these by showing status indicators: spinner during push, green check on success, red X on failure. Timed-out operations (30s) are treated as failures with appropriate user feedback.",
      "Bridge Error Handling Patterns", "typescript",
      ["davinci", "bridge", "errors", "handling", "patterns"]),

    e("Bridge error categories: VALIDATION (invalid payload, missing fields, wrong types), STATE (build not found, build already applied, build already dismissed), RESOURCE (file system error, memory limit, disk full), NETWORK (timeout, connection refused, DNS failure), INTERNAL (unhandled exception, assertion failed, unexpected null). Each error includes a type, message, and HTTP status code. Validation errors include a details array with per-field error descriptions.",
      "Bridge Error Categories", "typescript",
      ["davinci", "errors", "categories", "bridge", "types"]),

    e("Frontend error display: Errors from the bridge are displayed in a toast notification system. Validation errors show inline next to the relevant field. Network errors show a persistent banner with retry button. Internal errors show a generic 'Something went wrong' message with a copy-details button. All errors are logged to the browser console with stack traces for debugging. Error analytics are sent to the backend for monitoring.",
      "Frontend Error Display", "typescript",
      ["davinci", "errors", "frontend", "display", "toast"]),

    # ── AutoPlace Algorithm ──
    e("The performAutoPlace function algorithm: (1) Receives goal string, purpose, targetOS, and node array. (2) Calls LLM with a system prompt instructing it to suggest 5-8 UI widgets for the design. (3) LLM returns JSON with widgets array containing type, label, zone, action. (4) Each widget is positioned within its zone using layoutZonePositions which handles collision avoidance. (5) Widgets are returned with id, type, label, x, y, width, height, archBindings, and styleId.",
      "AutoPlace Algorithm Deep Dive", "python",
      ["davinci", "autoplace", "algorithm", "llm", "layout"]),

    e("AutoPlace widget template generation: Each widget type has a template with default dimensions and style. Buttons default to 120x36px with style bs2 (blue). Displays default to 260x80px with style bs1 (dark). Sliders default to 200x28px with style bs7 (teal). Toggles default to 56x28px with style bs6 (purple). Inputs default to 200x32px with style bs3 (green). Templates are customizable via the widget library API.",
      "AutoPlace Widget Templates", "python",
      ["davinci", "autoplace", "templates", "widgets", "defaults"]),

    e("AutoPlace fallback strategy: If the LLM call fails (timeout, network error, malformed response), the system falls back to a rule-based widget placement. The fallback analyzes node types: 'action' nodes get buttons, 'display' nodes get display widgets, 'input' nodes get input fields, 'toggle' nodes get toggles, 'adjust' nodes get sliders. Each node without a matching type gets a default display widget. The fallback generates 1 widget per node and places them in the main zone.",
      "AutoPlace Fallback Strategy", "python",
      ["davinci", "autoplace", "fallback", "rules", "placement"]),

    # ── Project Format ──
    e("Davinci projects are self-contained directories with a project.json manifest. The manifest includes: project name, version, created/applied timestamps, widget list with positions and styles, image layer references, audio track references, connection data for widget linking, and export history. Projects can be loaded via the file menu, auto-saved on changes, and exported as standalone HTML/CSS/JS applications with all widgets rendered inline.",
      "Project File Format and Export", "json",
      ["davinci", "projects", "export", "format", "serialization"]),

    e("Project auto-save behavior: The engine auto-saves the project 2 seconds after the last change (debounced). Auto-save is triggered by: widget add/remove/move/resize, connection add/remove, layer add/remove, track add/remove, build apply/dismiss. During auto-save, a saving indicator is shown in the status bar. If the save fails, the indicator turns red and the error is logged. The project file includes a lastAutoSave timestamp field.",
      "Project Auto-Save Behavior", "typescript",
      ["davinci", "projects", "autosave", "persistence", "state"]),

    e("Project migration system: When loading a project with an older version number, the engine runs migration scripts. Each migration is a function that transforms the project data structure from one version to the next. Migrations are stored in a migrations/ directory with filenames like 001_add_bindings.py, 002_add_snapshots.py. The project version is checked on load and migrations are applied in sequence. The original data is backed up before migration.",
      "Project Version Migration System", "python",
      ["davinci", "migration", "version", "upgrade", "project"]),

    # ── ArchBindings ──
    e("The bridge's ArchBindings system links canvas widgets to architect nodes. Each widget can have: linkedNodeId (references saved_N in the design), archBindings.onClick (action when button clicked), archBindings.onChange (action for input/toggle/slider changes), archBindings.displayInput (data source for display widgets), and archBindings.valueInput (bindings expression). When a build is applied, the bridge resolves these bindings and wires the widget to the node's data flow.",
      "ArchBindings Wiring System", "typescript",
      ["davinci", "archbindings", "wiring", "nodes", "widgets"]),

    e("ArchBinding expression syntax: {type: 'nodeRef', nodeId: 'saved_1'} for referencing a node's output. {type: 'literal', value: 'hello'} for static values. {type: 'expression', code: 'node.saved_1.value + 1'} for computed values. {type: 'event', event: 'click', nodeId: 'saved_1'} for event triggers. {type: 'state', key: 'counter'} for widget-local state. Expressions are evaluated in a sandboxed JavaScript context with access to node outputs and widget state.",
      "ArchBinding Expression Syntax", "typescript",
      ["davinci", "archbindings", "expressions", "syntax", "bindings"]),

    e("ArchBinding resolution order: When a build is applied, bindings are resolved in dependency order. First, literal and state bindings (no dependencies). Second, nodeRef bindings (depend on nodes). Third, expression bindings (depend on resolved nodeRefs). Fourth, event bindings (wired to DOM events). Circular dependencies are detected and reported as validation errors. Unresolvable bindings are reported as warnings but don't block the build apply.",
      "ArchBinding Resolution Order", "typescript",
      ["davinci", "archbindings", "resolution", "order", "dependencies"]),

    # ── Canvas Snapshots ──
    e("Canvas snapshot and restore: Before applying a new build, the Davinci engine snapshots the current canvas state. The snapshot includes all widget positions, styles, and connections. If the user dismisses a build, the snapshot is restored. Snapshots are stored in memory and in the project file. The /api/bridge/builds/{id}/dismiss endpoint triggers restore. Up to 5 undo levels are maintained for rapid back-and-forth between design iterations.",
      "Canvas Snapshot and Undo System", "python",
      ["davinci", "canvas", "snapshot", "undo", "restore"]),

    e("Snapshot storage format: {id: string, timestamp: ISO string, widgets: [{id, type, label, x, y, width, height, styleId, archBindings}], connections: [{id, sourceWidgetId, targetWidgetId, sourceHandle, targetHandle, style}], buildId: string (that triggered this snapshot)}. Snapshots are stored in a ring buffer of 5 entries. The oldest snapshot is evicted when the buffer is full. Snapshots are serialized to the project file on save for crash recovery.",
      "Snapshot Storage Format", "json",
      ["davinci", "snapshots", "format", "storage", "buffer"]),

    e("Undo/redo system: Ctrl+Z triggers undo - restores the previous snapshot. Ctrl+Shift+Z triggers redo - advances to the next snapshot. Undo/redo operations are animated (300ms transition) for visual continuity. The undo stack is cleared after a new build apply (since the state fundamentally changes). The frontend shows an undo/redo indicator in the toolbar with the snapshot description.",
      "Undo/Redo Keyboard Controls", "typescript",
      ["davinci", "undo", "redo", "keyboard", "controls"]),

    # ── TTS Integration ──
    e("The TTS (text-to-speech) integration in Davinci provides voice feedback for the architect workflow. Endpoints: POST /api/tts/load loads a voice model file, POST /api/tts/generate accepts text and returns audio data, POST /api/tts/voices/upload adds custom voices, GET /api/tts/status reports model state. The TTS engine uses the MindSpace inference server for generation. Voice feedback plays when builds are applied or when the user completes design steps.",
      "TTS Integration for Voice Feedback", "python",
      ["davinci", "tts", "voice", "feedback", "audio"]),

    e("TTS voice model management: POST /api/tts/voices/upload accepts a .pt or .pth voice model file (up to 200MB). POST /api/tts/voices/list returns all loaded voices with name, language, gender, duration. PATCH /api/tts/voices/{name}/default sets a voice as default for all generation. DELETE /api/tts/voices/{name} removes a voice. Voices are cached in data/voices/ and loaded into GPU memory on demand. The TTS engine can hot-swap voices between generations.",
      "TTS Voice Management API", "python",
      ["davinci", "tts", "voices", "api", "management"]),

    e("TTS generation queue: POST /api/tts/generate accepts {text: string, voice?: string, speed?: 0.5-2.0, pitch?: -12 to +12 semitones}. Generation is queued if the engine is busy. The response includes a jobId for polling: GET /api/tts/jobs/{jobId} returns {status: queued/processing/done/error, audioUrl?: string}. Audio is returned as WAV data URL or served from data/tts_output/. The frontend plays audio using the Web Audio API with audio context management.",
      "TTS Generation Queue", "python",
      ["davinci", "tts", "queue", "generation", "audio"]),

    # ── Image Layers ──
    e("The Davinci image layer system supports compositing: POST /api/layers uploads an image file (PNG, JPG, SVG, WebP) and returns a layer_id. Layers can be stacked via POST /api/layers/{id}/filter (apply CSS/Canvas filters like blur, brightness, contrast), POST /api/layers/{id}/resize (scale, crop, rotate), POST /api/layers/blend (composite multiple layers with blend modes: multiply, screen, overlay, difference). Each layer tracks opacity, blendMode, filters, and z-index.",
      "Image Layer Compositing System", "python",
      ["davinci", "layers", "images", "compositing", "blend"]),

    e("Image filter pipeline: Filters are applied in order: brightness -> contrast -> saturation -> blur -> sepia -> hue-rotate. Each filter has a value range (brightness: 0-200%, contrast: 0-200%, saturation: 0-200%, blur: 0-20px, sepia: 0-100%, hue-rotate: 0-360deg). Filters are stored as an array in the layer manifest: [{type: 'brightness', value: 110}, {type: 'blur', value: 2}]. Filters can be reordered via PUT /api/layers/{id}/filters/reorder. Performance: filters are applied server-side using Pillow and cached.",
      "Image Filter Pipeline", "python",
      ["davinci", "images", "filters", "pipeline", "effects"]),

    e("Image blend modes reference: multiply (darkens, good for shadows), screen (lightens, good for highlights), overlay (increases contrast), difference (inverts where overlapping), addition (brightens), subtract (darkens), divide (lightens dark areas), exclusion (similar to difference but lower contrast), hard-light (intense overlay), soft-light (gentle overlay). Each blend mode is implemented as a pixel-level operation using numpy arrays. Blend operations support per-layer opacity for fine control.",
      "Image Blend Modes Reference", "python",
      ["davinci", "blend", "modes", "images", "reference"]),

    # ── Audio Tracks ──
    e("The Davinci audio track system manages multi-track audio: POST /api/tracks uploads audio files (MP3, WAV, OGG, FLAC) returning a track_id. Tracks support volume, pan, start/end trim, and loop mode. GET /api/tracks lists all loaded tracks. PATCH /api/tracks/{id} adjusts volume/pan/trim. DELETE /api/tracks/{id} removes a track. Audio playback is synchronized with image layer animations for timed presentations.",
      "Multi-Track Audio Management", "python",
      ["davinci", "audio", "tracks", "sound", "multimedia"]),

    e("Audio track waveform generation: After upload, the backend generates a waveform preview using ffmpeg/ffprobe. The waveform is a PNG image showing amplitude over time. Waveform dimensions: 800x120px with a dark background and blue waveform line. The waveform is cached alongside the audio file and served via GET /api/tracks/{id}/waveform. Generation happens asynchronously after upload to not block the upload response. The waveform is regenerated when trim points change.",
      "Audio Waveform Generation", "python",
      ["davinci", "audio", "waveform", "generation", "preview"]),

    e("Audio playback synchronization: Tracks can be synchronized to start at specific timestamps relative to a presentation timeline. Sync points are defined as: {trackId: string, startTime: seconds, endTime?: seconds, fadeIn: seconds, fadeOut: seconds}. The playback engine uses the Web Audio API's AudioContext clock for precision timing. Crossfade between tracks uses equal-power fading for smooth transitions. The timeline is managed by the engine with play/pause/seek controls.",
      "Audio Playback Synchronization", "typescript",
      ["davinci", "audio", "synchronization", "timeline", "playback"]),

    # ── Full Workflow ──
    e("The complete Architect-to-Davinci integration workflow: (1) User designs nodes in the Visual AI Architect canvas. (2) User clicks Scaffold & Run which calls the export scaffold endpoint. (3) The scaffold generates code layers and calls performAutoPlace for widget suggestions. (4) The result is pushed to Davinci via the bridge builds endpoint. (5) Davinci applies the build, rendering widgets on its canvas. (6) The user can then refine widgets in Davinci directly.",
      "Full Integration Workflow", "typescript",
      ["davinci", "workflow", "integration", "scaffold", "pipeline"]),

    e("The iterative design loop: After a build is applied to Davinci, the user can (a) drag widgets to reposition, (b) resize widgets, (c) change widget styles via the properties panel, (d) add widgets from the library. When the user is satisfied, they can push the modified layout back to the Architect as a Pull Request template. The Architect then updates its node data to reflect the Davinci layout, enabling a closed design loop between the two systems.",
      "Iterative Design Loop", "typescript",
      ["davinci", "iterative", "design", "loop", "feedback"]),

    e("Multi-app support: Davinci can manage multiple apps simultaneously, each with its own set of widgets, nodes, and build history. App switching is done via the AppLauncher. Each app has an isolated namespace: data/apps/{appName}/. The bridge APIs accept an appName query parameter to target specific apps. Cross-app widget copying is supported via clipboard (copy from App A, paste into App B). Builds are app-scoped and don't interfere across apps.",
      "Multi-App Architecture", "typescript",
      ["davinci", "apps", "multi-app", "architecture", "isolation"]),
]

DAVINCI_CORE = [
    # ── System Architecture ──
    e("Davinci Studio Architecture Overview: The system uses a FastAPI Python backend on port 8000 with a React+Vite TypeScript frontend. The backend provides REST APIs for widget management, image layers, audio tracks, project management, and bridge integration with the Visual AI Architect. The frontend renders a canvas-based UI for visual design. The engine manages project state, widget positions, connections, and multimedia assets. Data is stored as JSON files in the data/ directory with project manifests and build history.",
      "Davinci System Architecture Overview", "python",
      ["davinci", "architecture", "overview", "system", "design"]),

    e("Davinci startup sequence: (1) Load config from backend/config.json with env overrides. (2) Initialize FastAPI app with CORS middleware (allow localhost:3001, localhost:5173). (3) Load widget library presets from widget_library.py. (4) Load existing projects from data/projects/. (5) Initialize TTS engine if model file found. (6) Load architect_nodes.json bridge file. (7) Start background workers (auto-save, build poller). (8) Mount static frontend build. (9) Listen on 0.0.0.0:8000.",
      "Davinci Startup Sequence", "python",
      ["davinci", "startup", "initialization", "sequence", "config"]),

    e("Davinci dependency tree: Python backend requires fastapi, uvicorn, pydantic, pillow, numpy, ffmpeg-python, httpx, sse-starlette. Frontend requires react, react-dom, vite, typescript, @vitejs/plugin-react. All dependencies are listed in backend/requirements.txt and frontend/package.json. The launch-web.sh script installs dependencies (pip install -r requirements.txt, npm install) and starts both backend and frontend concurrently.",
      "Davinci Dependency Tree", "text",
      ["davinci", "dependencies", "stack", "requirements", "setup"]),

    # ── Engine Core Methods ──
    e("DavinciEngine core methods: load_project(project_name) reads and deserializes a project from disk. create_widget(widget_data) adds a widget to the current project's widget registry with position validation. remove_widget(widget_id) deletes a widget and its connections. update_widget_position(wid, x, y) updates position with bounds checking. get_project_summary() returns a JSON summary with widget count, layer count, track count, and project metadata. save_project() serializes the current state to disk.",
      "DavinciEngine Core Methods", "python",
      ["davinci", "engine", "methods", "api", "core"]),

    e("Engine project lifecycle: init_project(name) creates a new project directory with default manifest. load_project(name) reads manifest and restores state. save_project() writes current state to disk. close_project() flushes state and releases resources. delete_project(name) removes the project directory after confirmation. The engine maintains a cursor to the currently active project. Only one project can be active at a time. Switching projects triggers an auto-save of the current one.",
      "Engine Project Lifecycle", "python",
      ["davinci", "engine", "lifecycle", "projects", "management"]),

    e("Engine widget registry: The registry is a dict keyed by widget ID. Each entry contains the full widget definition plus runtime state (position, visibility, enabled). The registry supports: get(id), add(widget), update(id, changes), remove(id), list(), count(), filter_by_type(type), filter_by_zone(zone). The registry emits events on changes (widget:added, widget:removed, widget:moved) which the frontend subscribes to for real-time updates.",
      "Engine Widget Registry", "python",
      ["davinci", "registry", "widgets", "engine", "events"]),

    # ── Widget Rendering ──
    e("Widget rendering in the Davinci frontend: Each widget type maps to a React component. ButtonWidget renders a styled button with click handler that fires the archBinding.onClick action. DisplayWidget shows content text or dynamic data, supports HTML rendering, auto-updates from archBinding.displayInput. SliderWidget renders a range input with configurable min/max/step, fires onChange on value change. ToggleWidget renders a switch with on/off labels. InputWidget renders a text input with placeholder, fires onChange on blur. All widgets support rotation via CSS transform and opacity via style.opacity.",
      "Widget Rendering Components", "typescript",
      ["davinci", "rendering", "widgets", "react", "components"]),

    e("ButtonWidget rendering details: Renders a <button> element with CSS classes for style variant. The button has hover (brightness 110%), active (scale 0.97), and focus (ring outline) states. The onClick handler checks for archBinding.onClick and executes it (calls the linked node's action). If no binding, the click is a no-op. Buttons show a ripple effect on click. Disabled buttons have reduced opacity (50%) and no hover effect. The label text is rendered inside a <span> with text truncation for long labels.",
      "ButtonWidget Rendering Details", "typescript",
      ["davinci", "button", "rendering", "details", "component"]),

    e("DisplayWidget rendering details: Renders a <div> with contenteditable=false. Content is set via innerHTML (sanitized to prevent XSS). If archBinding.displayInput is set, the content updates reactively whenever the bound node's output changes. Display supports scrolling for overflow content (max-height: 200px). The display has a subtle border and semi-transparent background. Static displays (no binding) show the text property directly. Dynamic displays show a loading indicator while the binding resolves.",
      "DisplayWidget Rendering Details", "typescript",
      ["davinci", "display", "rendering", "details", "component"]),

    # ── Image Pipeline ──
    e("Image layer processing pipeline in Davinci: (1) Upload via POST /api/layers accepts multipart form with image file. (2) File is validated for type (PNG, JPG, SVG, WebP), max size (10MB), and dimensions. (3) Original is saved to data/images/{filename} and a thumbnail (200px wide) is generated. (4) EXIF metadata is extracted (orientation, date, camera info). (5) The layer is added to the engine's layer list with z-index ordering. (6) GET /api/images/{filename} serves the full image with caching headers. (7) Filters and blend modes are applied in sequence during rendering.",
      "Image Layer Processing Pipeline", "python",
      ["davinci", "images", "layers", "pipeline", "processing"]),

    e("Image upload validation: File type is checked by extension and MIME type (image/png, image/jpeg, image/svg+xml, image/webp). Max file size is 10MB (configurable via DAVINCI_MAX_IMAGE_SIZE env var). Max dimensions are 4096x4096px. Images are scanned for EXIF orientation and auto-rotated. SVG files are sanitized to remove script tags. Animated WebP is allowed. Duplicate filenames get a timestamp suffix. On validation failure, a 422 response with details is returned.",
      "Image Upload Validation Rules", "python",
      ["davinci", "images", "validation", "upload", "rules"]),

    e("Image serving with caching: GET /api/images/{filename} serves images with Cache-Control: public, max-age=3600 headers. Thumbnails are served via GET /api/images/{filename}/thumb with max-age=7200. ETag headers enable conditional requests (304 Not Modified). Images are served using FileResponse with streaming for large files. The content-type is inferred from the file extension. A default image is served for missing files (404 instead of generic error).",
      "Image Serving and Caching", "python",
      ["davinci", "images", "caching", "serving", "headers"]),

    # ── Audio Pipeline ──
    e("Audio track processing in Davinci: (1) Upload via POST /api/tracks accepts MP3, WAV, OGG, FLAC up to 50MB. (2) File is validated and saved to data/audio/{filename}. (3) Duration, sample rate, and channels are extracted using ffprobe. (4) A waveform preview image is generated. (5) The track is added to the engine with configurable volume (0-100), pan (-100 to 100), trim_start/trim_end (in seconds), and loop_mode (none/one/all). (6) Playback uses Web Audio API with crossfade support. (7) Tracks are listed via GET /api/tracks and removed via DELETE /api/tracks/{id}.",
      "Audio Track Processing System", "python",
      ["davinci", "audio", "tracks", "processing", "waveform"]),

    e("Audio format conversion: Uploaded audio files are converted to WAV (16-bit, 44100Hz, mono) for consistent playback. The conversion is done using ffmpeg with a background subprocess. Conversion happens asynchronously; the upload response returns immediately with metadata, and a conversion complete event is sent via WebSocket. The original file is preserved alongside the converted version. Failed conversions set the track status to 'error' with details.",
      "Audio Format Conversion", "python",
      ["davinci", "audio", "conversion", "ffmpeg", "format"]),

    e("Audio track volume envelope: Tracks support volume envelopes for advanced mixing. Envelope points are: [{time: 0, volume: 0}, {time: 1, volume: 100}, {time: 10, volume: 80}, {time: 12, volume: 0} for fade in, hold, and fade out. Envelopes are applied during playback by the Web Audio API using gain nodes. Multiple points create complex volume curves. Envelopes are stored as part of the track metadata and can be edited via PATCH /api/tracks/{id}/envelope.",
      "Audio Volume Envelope System", "typescript",
      ["davinci", "audio", "envelope", "volume", "mixing"]),

    # ── Starter Apps ──
    e("Davinci starter apps manifest defines 5 built-in applications: Notepad (text editing with save/load), Color Picker (HSL/RGB/Hex color selection), Calculator (basic arithmetic with history), Timer (countdown with alarm), and Weather Widget (mock weather display). Each starter app is defined in manifest.json with: name, icon, description, default_widgets array with predefined widget configurations, default_layout with position presets, and category tag. Starter apps load on first startup and can be reset via POST /api/apps/{id}/reset.",
      "Starter Apps Manifest System", "json",
      ["davinci", "apps", "starter", "manifest", "templates"]),

    e("Notepad starter app details: Widgets include a textarea for content, save/load buttons, a filename input, and a character/word count display. The notepad saves content to data/apps/notepad/notes.json. Auto-save triggers every 30 seconds. The app supports multiple documents via a tab bar. Documents can be renamed and deleted. The notepad has a dark theme optimized for long-form text editing with a monospace font option.",
      "Notepad App Details", "typescript",
      ["davinci", "notepad", "app", "details", "features"]),

    e("Color Picker starter app details: Widgets include a color swatch display, HSL sliders (hue 0-360, saturation 0-100, lightness 0-100), RGB number inputs (0-255 each), hex input field, and a palette grid of recent colors. The picker updates in real-time as sliders move. Colors can be copied to clipboard as hex, RGB, or HSL. The palette persists 20 recent colors in local storage. The app supports eyedropper (Capture) button using the EyeDropper API.",
      "Color Picker App Details", "typescript",
      ["davinci", "color", "picker", "app", "details"]),

    # ── Bridge File Format ──
    e("Davinci's architect_nodes.json bridge file: When the Visual AI Architect pushes a design, the node definitions are written to data/architect_nodes.json. The format: array of {id, label, type, description, language, position: {x,y}}. This file is read by the Davinci bridge on startup and every 30 seconds for changes. The bridge uses these nodes to create archBindings for widgets. Nodes can be referenced across multiple builds, allowing iterative design refinement without losing node context.",
      "Architect Nodes Bridge File", "json",
      ["davinci", "nodes", "bridge", "file", "architect"]),

    e("Bridge file watch mechanism: A FileSystemWatcher thread monitors data/architect_nodes.json for changes using file modification timestamp. When the file changes (new write from Architect), the watcher emits a 'nodes:updated' event. The bridge then re-reads the file and checks for new nodes. New nodes are added to the registry. Removed nodes are flagged as stale (not deleted, to preserve existing bindings). The watcher uses a 5-second debounce to avoid rapid reloads.",
      "Bridge File Watch Mechanism", "python",
      ["davinci", "file", "watch", "monitor", "bridge"]),

    e("Bridge file conflict resolution: If the architect writes to the nodes file while the bridge is reading it, a partial read could occur. The bridge handles this by: (1) Reading the file content atomically. (2) Attempting JSON parse. (3) On failure, retrying up to 3 times with 100ms delay. (4) On persistent failure, falling back to the last known good state. The last known good state is cached in memory and serialized to data/architect_nodes.cache.json.",
      "Bridge File Conflict Resolution", "python",
      ["davinci", "bridge", "conflict", "resolution", "file"]),

    # ── Canvas Features ──
    e("The Davinci frontend canvas component (Canvas.tsx): Implements a drag-and-drop design surface using absolute positioning. Features include: zoom (50-200% via scroll wheel), pan (middle-click drag), grid overlay (10px/20px/50px toggle), snap-to-grid, multi-select (click+drag or Ctrl+click), alignment guides (visual indicators when widgets align horizontally or vertically), and context menu (right-click for copy/paste/delete/duplicate). The canvas uses CSS transforms for zoom/pan and React state for widget management.",
      "Canvas Component Features", "typescript",
      ["davinci", "canvas", "frontend", "features", "interaction"]),

    e("Canvas zoom implementation: Zoom is applied via CSS transform: scale(Z) on the canvas container. The zoom origin is the mouse cursor position (pinch-zoom behavior). Zoom levels snap to presets: 50%, 75%, 100%, 125%, 150%, 200%. Ctrl+scroll wheel changes zoom. The current zoom level is displayed in the toolbar. Pan is implemented by translating the canvas container via CSS transform: translate(dx, dy). Pan boundaries prevent the canvas from being moved off-screen. Zoom and pan state is persisted in the project.",
      "Canvas Zoom and Pan Implementation", "typescript",
      ["davinci", "canvas", "zoom", "pan", "implementation"]),

    e("Canvas alignment guides: When dragging a widget near another widget's edge (within 5px), a guide line appears. Guide colors: red for horizontal alignment, blue for vertical alignment, green for both. Guides also appear for center alignment (when widget center aligns with canvas center or another widget center). Guides disappear when the widget is dropped or moved more than 5px away. Multiple guides can be active simultaneously for complex alignments.",
      "Canvas Alignment Guide System", "typescript",
      ["davinci", "canvas", "alignment", "guides", "ux"]),

    # ── Batch / Bulk ──
    e("Davinci's batch widget operations: PUT /api/widgets/batch accepts {widgets: [...]} to replace all widgets on the canvas atomically. This is used during build application. Each widget in the batch is validated for: unique id, valid type, positive dimensions, position within canvas bounds (0-800 x, 0-600 y). On success, all previous widgets are removed and the new batch is rendered. The response includes count of widgets applied and any validation warnings. This endpoint also supports clearing the canvas by sending an empty widgets array.",
      "Batch Widget Operations", "typescript",
      ["davinci", "widgets", "batch", "operations", "api"]),

    e("Batch validation algorithm: (1) Check payload structure (must have widgets array). (2) Iterate widgets and validate each: id is non-empty string, type is one of [button, display, slider, toggle, input], label is non-empty string, x >= 0, y >= 0, width > 0, height > 0, styleId is valid. (3) Check for duplicate IDs - reject batch if found. (4) Check total widget count <= 50 (configurable limit). (5) On partial failure (some widgets valid, some invalid), the batch is rejected entirely (atomic).",
      "Batch Validation Algorithm", "typescript",
      ["davinci", "batch", "validation", "algorithm", "atomic"]),

    e("Batch performance optimization: Widget batch operations use a single render pass. The frontend collects all widget state changes, batches them into one setState call, and applies them in a single React reconciliation. This prevents intermediate flickering and improves perceived performance. For batches larger than 20 widgets, the frontend uses a requestAnimationFrame-based progressive render that shows a loading indicator.",
      "Batch Performance Optimization", "typescript",
      ["davinci", "batch", "performance", "rendering", "optimization"]),

    # ── Export Format ──
    e("Davinci export format for standalone apps: index.html includes inline CSS and JavaScript. The CSS defines: CSS custom properties for theming (--bg-primary, --bg-secondary, --text-primary, --accent), widget styles with transitions and hover effects, responsive grid layout, dark mode support, and animation keyframes. The JS includes: state management (simple store with subscribers), widget renderers for each type, event handling, local storage persistence, and export metadata. The exported app is a single self-contained HTML file.",
      "Standalone App Export Format", "html",
      ["davinci", "export", "format", "standalone", "html"]),

    e("Export CSS theming variables: :root { --bg-primary: #1a1a2e; --bg-secondary: #16213e; --surface: #0f3460; --text-primary: #e8e8e8; --text-secondary: #a0a0b0; --accent: #e94560; --success: #2ecc71; --warning: #f39c12; --error: #e74c3c; --info: #3498db; --border: #2a2a4a; --shadow: rgba(0,0,0,0.3); }. Dark mode is default. Light mode can be enabled by setting the data-theme='light' attribute on the root element, which swaps all variable values.",
      "Export CSS Theme Variables", "css",
      ["davinci", "export", "css", "themes", "variables"]),

    e("Export JavaScript state management: The exported app includes a lightweight store implementation. The store supports: getState(), setState(partial), subscribe(listener), and unsubscribe(listener). Widget state is stored as a flat object keyed by widget ID. State changes trigger reactive re-renders via the subscriber pattern. The store persists to localStorage under key 'davinci_export_{appName}'. Persistence is debounced (500ms) and can be disabled via data-no-persist attribute on the root element.",
      "Export State Management", "javascript",
      ["davinci", "export", "state", "management", "store"]),

    # ── Project Management ──
    e("Davinci project reset and cleanup: POST /api/apps/{id}/reset removes all widgets, layers, tracks, and connections for a project. It preserves the project manifest metadata. The reset also clears the build history and associated architect_nodes references. POST /api/bridge/builds/clear removes all pending and applied builds from the system. The clear operation is logged for debugging. After clear, new builds can be pushed fresh without interference from previous designs.",
      "Project Reset and Cleanup", "typescript",
      ["davinci", "reset", "cleanup", "projects", "management"]),

    e("Project duplicate and rename: POST /api/apps/{id}/duplicate creates a copy of the project with a new name (appended ' (Copy)'). All widgets, layers, tracks, connections, and build history are copied. The copy is independent of the original. PUT /api/apps/{id}/rename accepts {name: string} and renames the project. The project directory is also renamed on disk. Renaming preserves all internal IDs and references. Both operations return the updated project summary.",
      "Project Duplicate and Rename", "typescript",
      ["davinci", "projects", "duplicate", "rename", "management"]),

    e("Project import and export: POST /api/apps/import accepts a .json file with full project data. The system validates the structure and imports as a new project. GET /api/apps/{id}/export downloads the project as a .json file with all widget/layer/track data. Exported files include a schema version field for future compatibility. Imported projects are sanitized (paths normalized, IDs rewritten to avoid conflicts). Both operations support a dry-run mode for validation without side effects.",
      "Project Import and Export", "typescript",
      ["davinci", "import", "export", "projects", "serialization"]),

    # ── Events System ──
    e("Davinci widget interaction events: Each widget emits events that can be captured by the archBindings system. Button events: onClick (with widget id and label), onDoubleClick (for special actions). Slider events: onChange (with value 0-100), onDragStart, onDragEnd. Toggle events: onChange (with on/off state). Input events: onChange (with current text value), onFocus, onBlur, onSubmit (Enter key). Display events: onDataUpdate (when connected node pushes new data). All events propagate through the binding system to the architect node.",
      "Widget Interaction Events", "typescript",
      ["davinci", "events", "interaction", "bindings", "widgets"]),

    e("Event propagation model: Events flow through three layers: (1) DOM event -> (2) Widget component handler -> (3) ArchBinding resolver -> (4) Target node action. At each layer, the event can be intercepted and modified. The ArchBinding resolver maps event types to actions: onClick -> call linked node's execute action, onChange -> update linked node's state, onFocus -> highlight linked node in architect canvas. Event propagation is synchronous within the frontend but async when crossing to the backend via API.",
      "Event Propagation Model", "typescript",
      ["davinci", "events", "propagation", "model", "architecture"]),

    e("Custom event system for cross-widget communication: Widgets can emit custom events via a pub/sub event bus. Events include: 'widget:valueChanged' {widgetId, value}, 'widget:clicked' {widgetId}, 'widget:focused' {widgetId}, 'app:saved', 'app:exported', 'build:applied', 'build:dismissed'. Widgets can subscribe to events using the EventBus.subscribe(eventType, handler) method. The event bus supports wildcard subscriptions ('widget:*') and one-time listeners (subscribeOnce). Events are delivered synchronously in subscription order.",
      "Custom Event Bus System", "typescript",
      ["davinci", "events", "bus", "communication", "pubsub"]),

    # ── Directory Structure ──
    e("Davinci file organization and directory structure: data/ contains audio/ (uploaded audio files), images/ (uploaded images and thumbnails), exports/ (exported standalone apps), projects/ (project.json files), and architect_nodes.json (bridge node cache). backend/ contains main.py (FastAPI app), engine.py (core logic), constants.py (styling constants), widget_library.py (preset definitions), and requirements.txt (Python dependencies). frontend/ contains src/ with React components organized by feature.",
      "Davinci Directory Structure", "text",
      ["davinci", "structure", "files", "organization", "reference"]),

    e("Data directory organization: data/audio/<uuid>.<ext> for uploaded audio with metadata stored in data/audio_index.json. data/images/<uuid>.<ext> for uploaded images with metadata in data/images_index.json. data/exports/<app_name>/index.html for standalone exports. data/projects/<app_name>/project.json for project manifests. data/architect_nodes.json for bridge node cache. Each index file maps UUIDs to original filenames, upload timestamps, and associated metadata.",
      "Data Directory Organization", "text",
      ["davinci", "data", "organization", "directories", "storage"]),

    e("Logs directory: data/logs/ contains application logs. Log files are rotated daily with naming: app-YYYY-MM-DD.log. Logs are kept for 30 days. Each log entry includes: timestamp, level (DEBUG/INFO/WARNING/ERROR), module, message, and optional context JSON. The logging system uses Python's RotatingFileHandler with a max size of 10MB per file. Old logs are compressed (gzip) and archived. A symlink app.log points to the current day's log file.",
      "Logs Directory and Rotation", "text",
      ["davinci", "logs", "rotation", "directory", "logging"]),

    # ── Build Algorithm ──
    e("Davinci build apply algorithm: (1) Validate build_id exists and has pending status. (2) Snapshot current canvas state (widgets, positions, connections). (3) Clear existing widgets from canvas. (4) Iterate through placedWidgets array: for each widget, validate type, calculate position, apply styleId, wire archBindings to referenced nodes. (5) Add each widget to the engine's widget registry. (6) Update build status to 'applied' with applied timestamp. (7) Return {ok: true, widgets_applied: count}. (8) If any step fails, restore from snapshot and return error details.",
      "Build Apply Algorithm", "python",
      ["davinci", "apply", "algorithm", "widgets", "pipeline"]),

    e("Build validation before apply: The system validates: (1) build_id exists in architect_builds.json. (2) build status is 'pending' (cannot re-apply or apply dismissed). (3) placedWidgets is a non-empty array. (4) Each widget has required fields (type, label). (5) Widget dimensions are positive. (6) styleId references a valid style preset. (7) archBindings reference valid node IDs. (8) Total widget count <= 50. If validation fails, the response includes a details object with per-field errors.",
      "Build Validation Before Apply", "python",
      ["davinci", "build", "validation", "apply", "checks"]),

    e("Build apply rollback: If a build apply fails mid-way (e.g., widget 10 of 20 fails), the system rolls back to the pre-apply snapshot. Rollback restores: all widget positions, all connections, all archBindings, the build status (back to pending), and the auto-save state. The rollback is logged with the failure reason. The frontend shows a 'Build apply failed - rolled back' notification with a details expander showing which widget failed and why.",
      "Build Apply Rollback Strategy", "typescript",
      ["davinci", "build", "rollback", "failure", "recovery"]),

    # ── Bridge Status ──
    e("Davinci bridge status reporting: GET /api/bridge/status returns {connected: bool, lastPush: timestamp, activeBuild: build_id/null, widgetCount: int, nodeCount: int}. The frontend displays this in a status bar at the bottom of the canvas. Connection status is checked every 10 seconds. If the bridge disconnects, a warning banner appears with a Reconnect button. The bridge reconnection uses exponential backoff (1s, 2s, 4s, 8s, max 30s) and automatically retries failed operations.",
      "Bridge Status Monitoring", "typescript",
      ["davinci", "bridge", "status", "monitoring", "connection"]),

    e("Bridge health check: GET /api/bridge/health returns {status: 'ok', uptime: seconds, version: string, memory_mb: number, datasheet_count: int}. Health checks are used by the orchestrator to verify bridge availability. The health endpoint bypasses all middleware and runs minimal checks (file system access, database if connected, GPU if applicable). If health check fails twice consecutively, the system auto-restarts the bridge process via the daemon supervisor.",
      "Bridge Health Check", "python",
      ["davinci", "bridge", "health", "monitoring", "uptime"]),

    e("Bridge connection status UI: The status bar shows: green dot with 'Connected' text when bridge is active, yellow dot with 'Reconnecting...' when reconnecting, red dot with 'Disconnected' when connection lost. Clicking the status bar expands a detail panel showing: last push time, active build count, total widget count, total node count, connection latency (ms), and WebSocket state. The detail panel auto-collapses after 10 seconds of inactivity.",
      "Bridge Connection Status UI", "typescript",
      ["davinci", "bridge", "ui", "status", "connection"]),

    # ── Accessibility ──
    e("Davinci accessibility features: All interactive widgets are keyboard accessible (Tab navigation, Enter/Space to activate, Arrow keys for sliders). High contrast mode can be enabled via config. Focus indicators are visible on all focusable elements. ARIA labels are automatically generated from widget labels. Screen reader announcements play via the TTS system on build apply and state changes. Color contrast ratios meet WCAG AA standards for all style variants.",
      "Accessibility Features", "typescript",
      ["davinci", "accessibility", "a11y", "keyboard", "contrast"]),

    e("Keyboard navigation map: Tab - cycle through widgets in z-order. Shift+Tab - reverse cycle. Enter/Space - activate focused widget. Arrow keys - move selected widget (10px per press). Shift+Arrow - move 1px (fine positioning). Delete/Backspace - remove selected widget. Ctrl+C/V - copy/paste widget. Ctrl+D - duplicate widget. Ctrl+A - select all widgets. Escape - deselect all. Ctrl+Z/Y - undo/redo. Ctrl+S - save project. F2 - rename selected widget.",
      "Keyboard Navigation Map", "text",
      ["davinci", "keyboard", "navigation", "shortcuts", "accessibility"]),

    e("Screen reader support: Widgets have auto-generated aria-labels: 'Button: {label}', 'Display: {label}', 'Slider: {label} {value}', 'Toggle: {label} {on/off}', 'Input: {label}'. aria-roledescription provides widget type context. aria-live='polite' regions announce state changes (build applied, widget moved, value changed). The canvas container has role='application' and aria-label='Design canvas'. Focus management follows a roving tabindex pattern for arrow-key navigation between widgets.",
      "Screen Reader Support", "typescript",
      ["davinci", "screenreader", "aria", "accessibility", "labels"]),

    # ── Theme System ──
    e("Davinci theme system: Themes are defined in constants.py with color palettes. Each theme has: background (canvas background), surface (widget background), primary (accent color for buttons), text (primary text color), textSecondary (muted text), border (widget borders), success/error/warning/info (semantic colors). Themes can be switched at runtime via the settings panel. Custom themes can be created by extending constants.py. The active theme is stored in the project manifest and persisted across sessions.",
      "Theme System and Customization", "python",
      ["davinci", "themes", "colors", "customization", "ui"]),

    e("Built-in theme colors: Dark theme: {bg: '#1a1a2e', surface: '#16213e', surface2: '#0f3460', primary: '#e94560', text: '#e8e8e8', textSec: '#a0a0b0', border: '#2a2a4a', success: '#2ecc71', warning: '#f39c12', error: '#e74c3c', info: '#3498db'}. Light theme: {bg: '#f5f6fa', surface: '#ffffff', surface2: '#e8e8e8', primary: '#0984e3', text: '#2d3436', textSec: '#636e72', border: '#dfe6e9', success: '#00b894', warning: '#fdcb6e', error: '#d63031', info: '#74b9ff'}. High contrast theme uses maximum contrast ratios.",
      "Built-in Theme Color Palettes", "css",
      ["davinci", "themes", "colors", "palettes", "builtin"]),

    e("Theme hot-swapping: When a user changes themes, the frontend applies the new theme by updating CSS custom properties on the :root element. The transition is animated (200ms ease-in-out color transition). Theme preference is saved to localStorage and restored on page load. The backend also applies theme to exported apps (the theme is baked into the static HTML at export time). Custom themes can be imported via JSON file or defined in the settings UI with a live preview.",
      "Theme Hot-Swapping Mechanism", "typescript",
      ["davinci", "themes", "hotswap", "mechanism", "animation"]),

    # ── Logging ──
    e("Davinci logging and debugging: The backend uses Python's logging module with levels: DEBUG (widget positioning details), INFO (build lifecycle events), WARNING (validation issues), ERROR (operation failures). Logs are written to stdout and optionally to a file. The frontend logs Redux actions and API calls to the browser console. Debug mode (config.debug=true) enables verbose logging, widget outlines, performance metrics overlay, and simulated operations for testing.",
      "Logging and Debugging System", "python",
      ["davinci", "logging", "debug", "monitoring", "diagnostics"]),

    e("Debug mode features: When debug=true in config: (1) Widgets show bounding box outlines with dimensions. (2) A performance overlay shows FPS, memory usage, and render times. (3) All API calls are logged with request/response bodies. (4) A virtual grid overlay shows zone boundaries and snap points. (5) Simulated operations can be triggered for testing (simulate push, simulate apply, simulate error). (6) Network tab shows real-time API monitoring. Debug mode is disabled by default and requires a backend restart to enable.",
      "Debug Mode Features", "typescript",
      ["davinci", "debug", "mode", "features", "development"]),

    e("Error logging format: Backend errors are logged with: timestamp (ISO 8601), level (ERROR), module (e.g., engine.py), line number, function name, error type, error message, traceback (full stack), context (request parameters, widget IDs, build IDs if available), and user_agent. The log format is structured JSON for machine parsing. Frontend errors (console.error) are sent to the backend via POST /api/log/frontend-error with the same structured format.",
      "Error Logging Format", "python",
      ["davinci", "logging", "errors", "format", "structured"]),
]


def write_entries(filename, entries):
    path = TRAINER_DIR / filename
    existing_lines = []
    existing_texts = set()
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_lines.append(line)
                    try:
                        existing_texts.add(json.loads(line).get("text", ""))
                    except json.JSONDecodeError:
                        pass

    new_entries = [e for e in entries if e["text"] not in existing_texts]

    with open(path, "w") as f:
        for line in existing_lines:
            f.write(line + "\n")
        for e in new_entries:
            f.write(json.dumps(e) + "\n")

    skipped = len(entries) - len(new_entries)
    total = len(existing_lines) + len(new_entries)
    print(f"  {filename}: {len(existing_lines)} existing + {len(new_entries)} new ({skipped} skipped) = {total} total lines")
    return len(new_entries)


print("Expanding Davinci datasheets...\n")

t1 = write_entries("datasheet-davinci-integration.jsonl", DAVINCI_INTEGRATION)
t2 = write_entries("datasheet-davinci.jsonl", DAVINCI_CORE)

print(f"\nTotal new entries: {t1 + t2}\n")

for fn in ["datasheet-davinci-integration.jsonl", "datasheet-davinci.jsonl"]:
    p = TRAINER_DIR / fn
    if p.exists():
        print(f"  {fn}: {sum(1 for _ in open(p) if _.strip())} lines")
