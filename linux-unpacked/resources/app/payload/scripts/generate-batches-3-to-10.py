#!/usr/bin/env python3
"""Generate Batches 3-10: 160 designs for remaining bible categories."""
import json, os, time, re

DESIGNS_PATH = "data/designs.json"
NOW = "2026-06-19T14:00:00.000Z"

existing = []
if os.path.exists(DESIGNS_PATH):
    with open(DESIGNS_PATH) as f:
        existing = json.load(f)

def make_design(name, goal, purpose, nodes, edges, tags):
    ts = int(time.time() * 1000) + len(existing) + len(globals().get('all_created', []))
    return {
        "id": f"design_{ts}", "name": name, "goal": goal, "purpose": purpose,
        "targetOS": "linux", "nodes": nodes, "edges": edges,
        "roadmap": f"App: {name}\nTarget OS: linux\nNodes: {len(nodes)}\nConnections: {len(edges)}",
        "createdAt": NOW, "updatedAt": NOW, "source": "local", "tags": tags
    }

def n(id, type_, label, desc, lang, x, y):
    return {"id": f"saved_{id}", "type": type_, "label": label, "description": desc, "language": lang, "position": {"x": x, "y": y}}

def e(src, tgt):
    return {"source": f"node_{src}", "target": f"node_{tgt}"}

def safe_filename(name):
    s = name.lower().replace(' ','-').replace('/','-').replace('\\','-').replace(':','')
    s = re.sub(r'[^a-z0-9-]', '', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s[:60]

def write_bible_refs(category, designs, bible_dir):
    for i, d in enumerate(designs):
        fn = f"{i+1:02d}-{safe_filename(d['name'])}.md"
        path = os.path.join(bible_dir, fn)
        nodes_str = '\n'.join([f"  - **{n['label']}** ({n['type']}): {n['description']}" for n in d['nodes']])
        edges_str = '\n'.join([f"  - `{e['source']}` → `{e['target']}`" for e in d['edges']])
        content = f"""# 🏗️ {d['name']}

**Design ID:** `{d['id']}` | **Category:** {category} | **Target OS:** linux

## Goal
{d['goal']}

## Purpose
{d['purpose']}

## Nodes ({len(d['nodes'])}
{nodes_str}

## Edges ({len(d['edges'])}
{edges_str}

## Tags
{', '.join(d['tags'])}

---
*Design generated for Visual AI Architect*
"""
        with open(path, 'w') as f:
            f.write(content)
    print(f"   📄 Created {len(designs)} bible refs in {bible_dir}")

all_created = []

# ═══════════════════════════════════════════════════════════════
# BATCH 3: 03-desktop-apps
# ═══════════════════════════════════════════════════════════════
b3 = []
b3.append(make_design("Text Editor Pro", "A full-featured text editor with syntax highlighting, find/replace, and file management", "Desktop text editor with gap buffer, syntax highlighting for 20+ languages, find/replace with regex, multiple tabs, and file tree sidebar",
    [n(0,"input","File Handler","Open, save, create files; file tree navigation; drag-drop support","typescript",50,50),
     n(1,"logic","Gap Buffer Engine","Efficient insert/delete using gap buffer data structure with cursor management","typescript",250,50),
     n(2,"logic","Syntax Highlighter","Token-based highlighting for 20+ languages with theme support","typescript",250,250),
     n(3,"database","File Store","File content cache, recent files list, session state persistence","typescript",50,450),
     n(4,"ui","Editor Canvas","Rendered editor with line numbers, gutter, cursor, selection, minimap","typescript",450,250),
     n(5,"ui","Search Panel","Find/replace bar with regex toggle, match highlighting, results count","typescript",650,150)],
    ["text-editor","desktop","editor","syntax-highlighting","productivity"]))
b3.append(make_design("File Explorer", "Dual-pane file manager with directory traversal, search, and file operations", "Desktop file explorer with tree/list view, copy/move/delete/rename operations, file search, directory size calculation, and context menu",
    [n(0,"input","Navigation Bar","Path bar with breadcrumbs, back/forward history, quick jump to bookmarks","typescript",50,50),
     n(1,"logic","Directory Engine","Directory traversal with lazy loading, sorting, filter for files/folders","typescript",250,50),
     n(2,"logic","File Operations","Copy, move, delete, rename with progress tracking and undo support","typescript",250,250),
     n(3,"database","File Index","File metadata cache, directory structure, bookmark store, operation history","typescript",50,450),
     n(4,"ui","File List View","Dual-pane view with icons, details, list modes; context menu; drag-drop","typescript",450,250)],
    ["file-explorer","desktop","file-manager","navigation","utility"]))
b3.append(make_design("Markdown Viewer & Editor", "Live markdown editor with split-pane preview, export to HTML/PDF", "WYSIWYG markdown editor with live preview, GitHub-flavored markdown, table editing, image embedding, and HTML/PDF export",
    [n(0,"input","Editor Input","Rich markdown text input with toolbar buttons (bold, italic, headers, lists, code)","typescript",50,50),
     n(1,"logic","Markdown Parser","Markdown-to-HTML conversion with GFM tables, fenced code blocks, task lists","typescript",250,50),
     n(2,"logic","Live Preview Engine","Debounced preview update, scroll sync between editor and preview","typescript",250,250),
     n(3,"database","Document Store","Document save/load, history, auto-save drafts, export templates","typescript",50,450),
     n(4,"ui","Split View","Left: editor with line numbers; Right: rendered preview with styling","typescript",450,250)],
    ["markdown","editor","preview","documentation","productivity"]))
b3.append(make_design("Media Player", "Audio/video player with playlist management, equalizer, and subtitle support", "Desktop media player supporting MP3/FLAC/WAV/MP4/MKV with playlist, 10-band equalizer, subtitle rendering, and playback speed control",
    [n(0,"input","Media Loader","File open dialog, drag-drop files, URL stream input, folder import","typescript",50,50),
     n(1,"logic","Playback Engine","Audio/video decoding pipeline, playback controls (play/pause/seek/volume)","typescript",250,50),
     n(2,"logic","Equalizer","10-band graphic equalizer with presets (rock, pop, jazz, classical, custom)","typescript",250,250),
     n(3,"database","Media Library","Playlist management, media metadata cache, play count, last position","sqlite",50,450),
     n(4,"ui","Player Interface","Video canvas, audio visualization, playlist panel, EQ controls, subtitles","typescript",450,250)],
    ["media-player","audio","video","entertainment","desktop"]))
b3.append(make_design("Image Viewer & Editor", "Image viewer with basic editing tools, filters, and format conversion", "Desktop image viewer supporting PNG/JPG/GIF/BMP/WEBP with crop, resize, rotate, color adjustment, filter effects, and batch conversion",
    [n(0,"input","Image Loader","File browser, drag-drop, clipboard paste, URL loading","typescript",50,50),
     n(1,"logic","Image Processor","Crop, resize, rotate, flip, color balance, brightness/contrast adjustments","typescript",250,50),
     n(2,"logic","Filter Engine","Blur, sharpen, edge detection, sepia, grayscale, pixelate, emboss filters","typescript",250,250),
     n(3,"database","Image Cache","Thumbnail cache, edit history (undo/redo stack), EXIF data store","typescript",50,450),
     n(4,"ui","Viewer & Toolbar","Image display with zoom/pan, filter preview, side-by-side comparison","typescript",450,250)],
    ["image-viewer","editor","photo","filters","desktop"]))
b3.append(make_design("PDF Reader & Annotator", "PDF viewer with text selection, bookmarks, annotations, and form filling", "Desktop PDF reader with page rendering, text selection/search, bookmark manager, highlight/underline/comment annotations, and PDF form filling",
    [n(0,"input","Document Input","File open, page navigation (thumbnails, search results), bookmark jump","typescript",50,50),
     n(1,"logic","PDF Engine","Page rendering, text extraction, search engine, form field detection","typescript",250,50),
     n(2,"logic","Annotation System","Highlight, underline, strikeout, note, freehand drawing on pages","typescript",250,250),
     n(3,"database","Document Store","Page cache, annotation data, bookmarks, reading position, form data","sqlite",50,450),
     n(4,"ui","Reader View","Page display with zoom, sidebar (thumbnails/outline/annotations), toolbar","typescript",450,250)],
    ["pdf-reader","document","annotations","desktop","productivity"]))
b3.append(make_design("Terminal Emulator", "GPU-accelerated terminal emulator with tabs, themes, and split panes", "Desktop terminal with GPU-accelerated rendering, multiple profiles, tabbed interface, split panes, search, 256-color support, and customization",
    [n(0,"input","Keyboard Input","Raw keyboard input processing, escape sequence generation, clipboard integration","typescript",50,50),
     n(1,"logic","PTY Manager","Pseudo-terminal management, shell spawning, terminal state tracking","typescript",250,50),
     n(2,"logic","Render Engine","GPU-accelerated text rendering, font ligatures, anti-aliasing, color themes","typescript",250,250),
     n(3,"database","Session Config","Profile settings (font, colors, shell), session history, theme store","typescript",50,450),
     n(4,"ui","Terminal View","Scrollback buffer, tab bar, split pane manager, search overlay","typescript",450,250)],
    ["terminal","emulator","console","desktop","developer-tools"]))
b3.append(make_design("Code Editor IDE", "Lightweight IDE with project management, Git integration, and debugging", "Desktop code editor with project tree, Git status/blame/diff, integrated terminal, debugger frontend, and plugin system",
    [n(0,"input","Project Manager","Folder/project open, file tree with Git status icons, recent projects","typescript",50,50),
     n(1,"logic","Code Intelligence","LSP client for autocomplete, go-to-definition, hover info, diagnostics","typescript",250,50),
     n(2,"logic","Git Integration","Status, diff, blame, commit, branch management, conflict resolver","typescript",250,250),
     n(3,"database","Index Store","Symbol index, file cache, Git data, debug configurations, workspace state","sqlite",50,450),
     n(4,"ui","IDE Workspace","Tabbed editor, sidebar (file tree/Git/outline), panel (terminal/problems/output)","typescript",450,250)],
    ["ide","code-editor","git","developer-tools","lsp"]))
b3.append(make_design("Notes & Wiki", "Personal knowledge base with rich text, tags, backlinks, and search", "Desktop notes app with WYSIWYG rich text editing, tag-based organization, wiki-style backlinks, full-text search, and markdown export",
    [n(0,"input","Note Editor","Rich text input with formatting toolbar, image embed, code blocks, tables","typescript",50,50),
     n(1,"logic","Wiki Engine","Tag indexing, backlink detection, graph view of note connections","typescript",250,50),
     n(2,"logic","Search Engine","Full-text search with fuzzy matching, tag filter, recent notes ranking","typescript",250,250),
     n(3,"database","Note Store","SQLite storage for notes, tags, links, attachments with version history","sqlite",50,450),
     n(4,"ui","Workspace View","Editor pane, sidebar (tags/backlinks/outline), graph visualization","typescript",450,250)],
    ["notes","wiki","knowledge-base","productivity","rich-text"]))
b3.append(make_design("Scientific Calculator", "Advanced calculator with graphing, unit conversion, and equation solving", "Desktop scientific calculator with expression parser, 2D/3D graphing, unit conversion, equation solver, and history log",
    [n(0,"input","Expression Input","Math expression entry with syntax highlighting, auto-complete functions","typescript",50,50),
     n(1,"logic","Expression Engine","Shunting-yard parser, variable-precision arithmetic, 200+ built-in functions","typescript",250,50),
     n(2,"logic","Graph Plotter","2D/3D function plotting with zoom, pan, trace, multiple function overlay","typescript",250,250),
     n(3,"database","History Store","Calculation history, saved graphs, constants, user-defined functions","sqlite",50,450),
     n(4,"ui","Calculator UI","Display with history, graph canvas, unit converter panel, equation solver","typescript",450,250)],
    ["calculator","scientific","graphing","math","desktop"]))
b3.append(make_design("Contact Manager CRM", "Personal contact management with groups, search, and import/export", "Desktop CRM for contacts with field customization, group tagging, birthday reminders, vCard import/export, and duplicate detection",
    [n(0,"input","Contact Form","Contact entry form with customizable fields, avatar upload, address autocomplete","typescript",50,50),
     n(1,"logic","Contact Engine","Duplicate detection (fuzzy matching), group management, birthday calculation","typescript",250,50),
     n(2,"logic","Import/Export","vCard, CSV, JSON import/export with field mapping and validation","typescript",250,250),
     n(3,"database","Contact DB","SQLite storage for contacts, groups, interaction history, tags","sqlite",50,450),
     n(4,"ui","Contact Browser","Card/list view, search/filter, group sidebar, interaction timeline","typescript",450,250)],
    ["contacts","crm","address-book","desktop","productivity"]))
b3.append(make_design("Calendar & Schedule", "Desktop calendar with event management, reminders, and iCal sync", "Calendar application with month/week/day views, event creation with recurrence, reminders, iCal import/export, and Google Calendar sync",
    [n(0,"input","Event Creator","Event form with title, date/time, duration, recurrence, location, notes","typescript",50,50),
     n(1,"logic","Schedule Engine","Recurrence expansion (daily/weekly/monthly/yearly), conflict detection","typescript",250,50),
     n(2,"logic","Reminder System","Popup and sound reminders, snooze, email notification integration","typescript",250,250),
     n(3,"database","Calendar Store","Events, reminders, calendars (multiple), iCal data with CRUD operations","sqlite",50,450),
     n(4,"ui","Calendar View","Month/week/day views with drag-create/edit, mini-calendar, agenda list","typescript",450,250)],
    ["calendar","schedule","events","productivity","desktop"]))
b3.append(make_design("Music Organizer", "Music library manager with tag editing, duplicate finder, and playlist management", "Desktop music organizer with ID3 tag editing, duplicate detection (by audio fingerprint), smart playlists, album art downloader, and file renaming",
    [n(0,"input","Library Import","Scan directories for music files, watch folders for new files, CD ripping","typescript",50,50),
     n(1,"logic","Tag Editor","ID3/FLAC/MP4 tag editing, batch tag operations, album art management","typescript",250,50),
     n(2,"logic","Duplicate Finder","Audio fingerprint (acoustic fingerprint) based duplicate detection","typescript",250,250),
     n(3,"database","Music Database","SQLite with tracks, albums, artists, playlists, play counts, ratings","sqlite",50,450),
     n(4,"ui","Library Browser","Album/artist/track grid/list, search, playlist panel, tag editor","typescript",450,250)],
    ["music","organizer","audio","library","desktop"]))
b3.append(make_design("Video Converter", "Batch video converter with format profiles, crop, and quality presets", "Desktop video converter supporting H.264/H.265/VP9/AV1 encoding, batch processing, crop/resize, quality presets, and progress tracking",
    [n(0,"input","File Importer","Add files/folders, drag-drop, preview thumbnails, format detection","typescript",50,50),
     n(1,"logic","Conversion Engine","FFmpeg-based encoding pipeline with hardware acceleration (NVENC/VAAPI)","typescript",250,50),
     n(2,"logic","Batch Manager","Queue management, parallel conversion, priority settings, completion actions","typescript",250,250),
     n(3,"database","Job Store","Conversion jobs, presets, profile settings, conversion history","sqlite",50,450),
     n(4,"ui","Converter UI","File list with status icons, format presets, quality sliders, progress bars","typescript",450,250)],
    ["video","converter","transcoding","batch","desktop"]))
b3.append(make_design("Screen Recorder", "Desktop screen/region recorder with audio, annotations, and export presets", "Screen recording tool with full-screen/region/window capture, microphone audio, mouse highlighting, drawing annotations, and GIF/MP4 export",
    [n(0,"input","Capture Config","Source selection (screen/region/window), audio source, quality settings","typescript",50,50),
     n(1,"logic","Capture Engine","Frame capture with hardware encoding (NVENC/QuickSync), audio mixing","typescript",250,50),
     n(2,"logic","Annotation Tool","Real-time drawing (pen, arrow, rectangle, text) overlay on recording","typescript",250,250),
     n(3,"database","Recording Store","Recorded video storage, auto-save drafts, export profile presets","typescript",50,450),
     n(4,"ui","Recorder UI","Preview window, recording controls (record/pause/stop), timeline, annotations","typescript",450,250)],
    ["screen-recorder","capture","video","recording","desktop"]))
b3.append(make_design("Clipboard Manager", "Clipboard history manager with snippets, search, and sync across devices", "Desktop clipboard manager storing text/image/file history, favorites/snippets, full-text search, and LAN sync between computers",
    [n(0,"input","Clipboard Monitor","System clipboard hook, format detection (text/image/file), paste simulation","typescript",50,50),
     n(1,"logic","History Engine","Clip history management, deduplication, expiration/archival, categorization","typescript",250,50),
     n(2,"logic","Sync Engine","LAN sync via WebRTC, encrypted transfer, conflict resolution","typescript",250,250),
     n(3,"database","Clip Store","SQLite with history, favorites, snippets, categories, sync status","sqlite",50,450),
     n(4,"ui","Clipboard Panel","History list with search, favorite/snippet sidebar, paste-by-click","typescript",450,250)],
    ["clipboard","manager","productivity","utility","desktop"]))
b3.append(make_design("System Monitor", "System resource monitor with CPU/RAM/disk/network graphs and process management", "Desktop system monitor with real-time CPU/RAM/disk/network graphs, process list with kill/priority, temperature monitoring, and alert thresholds",
    [n(0,"input","Monitor Config","Refresh rate, alert thresholds, graph color scheme, process filter settings","typescript",50,50),
     n(1,"logic","System Collector","CPU usage per core, RAM/Swap, disk I/O, network traffic, process list","typescript",250,50),
     n(2,"logic","Alert Engine","Threshold monitoring, alert triggers, notification dispatch, log events","typescript",250,250),
     n(3,"database","Metrics Store","Time-series metrics buffer, alert history, baseline comparison data","sqlite",50,450),
     n(4,"ui","Dashboard UI","Tabbed view: CPU/RAM/Disk/Network graphs, process table, alert log","typescript",450,250)],
    ["system-monitor","performance","metrics","desktop","utility"]))
b3.append(make_design("Password Manager", "Secure local password vault with encryption, generator, and auto-fill", "Desktop password manager with AES-256-GCM encrypted vault, password generator, auto-type/fill, import/export (CSV), and master password recovery",
    [n(0,"input","Vault Unlock","Master password input, biometric auth, key file authentication","typescript",50,50),
     n(1,"logic","Crypto Engine","AES-256-GCM encryption/decryption, PBKDF2 key derivation, argon2 hashing","typescript",250,50),
     n(2,"logic","Password Generator","Configurable password generation: length, character sets, pronounceable, PIN","typescript",250,250),
     n(3,"database","Vault Store","Encrypted SQLite with entries, categories, attachments, history, TOTP seeds","sqlite",50,450),
     n(4,"ui","Vault Browser","Entry list with search/filter, entry detail, generator, auto-type button","typescript",450,250)],
    ["password-manager","security","encryption","vault","utility"]))
b3.append(make_design("App Launcher", "Keyboard-driven application launcher with plugins and quick actions", "Desktop app launcher similar to Spotlight/Alfred with fuzzy search, calculator, web search, file search, clipboard history, and plugin system",
    [n(0,"input","Quick Input","Hotkey-activated search bar with fuzzy text input and autocomplete","typescript",50,50),
     n(1,"logic","Search Engine","Fuzzy matching across apps, files, contacts, web bookmarks, plugins","typescript",250,50),
     n(2,"logic","Plugin System","Plugin loader, action dispatcher, result formatter for extensions","typescript",250,250),
     n(3,"database","Index Store","App index, file index, plugin registry, usage frequency data, settings","sqlite",50,450),
     n(4,"ui","Launcher UI","Overlay window with search results, categories, inline preview, actions","typescript",450,250)],
    ["app-launcher","productivity","search","plugin","desktop"]))
b3.append(make_design("Backup & Sync Tool", "File backup tool with scheduled sync, versioning, and cloud targets", "Desktop backup utility with full/incremental backup, scheduled sync, version history, deduplication, and support for local/external/cloud destinations",
    [n(0,"input","Backup Config","Source/destination selection, schedule config, file filter, encryption settings","typescript",50,50),
     n(1,"logic","Backup Engine","File scanning, change detection, incremental backup, deduplication (hash-based)","typescript",250,50),
     n(2,"logic","Restore Manager","File version browser, selective restore, full restore, integrity verification","typescript",250,250),
     n(3,"database","Backup Catalog","File index, version history, checksums, schedule config, job logs","sqlite",50,450),
     n(4,"ui","Backup Dashboard","Job status, log viewer, version timeline, restore file browser","typescript",450,250)],
    ["backup","sync","file-management","utility","desktop"]))
b3_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 03-desktop-apps/00-overview.md |" for i,d in enumerate(b3)])
all_created.extend(b3)

# ═══════════════════════════════════════════════════════════════
# BATCH 4: 05-systems-programming
# ═══════════════════════════════════════════════════════════════
b4 = []
b4.append(make_design("Memory Profiler", "Real-time memory profiling tool with allocation tracking and leak detection", "Memory analysis tool that tracks malloc/free, detects leaks via reference counting, visualizes heap fragmentation, and profiles allocation hotspots",
    [n(0,"input","Process Selector","Attach to running process, launch new process, load core dump","typescript",50,50),
     n(1,"logic","Tracer Engine","malloc/free hooking via LD_PRELOAD, call stack capture, allocation tracking","cpp",250,50),
     n(2,"logic","Leak Detector","Reference count analysis, cyclic reference detection, unfreed block reporting","cpp",250,250),
     n(3,"database","Profiling DB","Time-series allocation data, call stack index, snapshot store","sqlite",50,450),
     n(4,"ui","Profiler UI","Flame graph, heap timeline, allocation heatmap, top allocators table","typescript",450,250)],
    ["memory","profiler","leak-detection","cpp","systems"]))
b4.append(make_design("Thread Debugger", "Multi-threaded application debugger with race condition detection", "Thread debugging tool showing thread states, lock ownership, wait graphs, deadlock detection, and data race detection using happens-before tracking",
    [n(0,"input","Debug Config","Thread/process attach, breakpoint management, watch expressions","typescript",50,50),
     n(1,"logic","Thread Tracker","Thread state machine (running/blocked/runnable), context switch logging","cpp",250,50),
     n(2,"logic","Race Detector","Happens-before tracking, lock-set analysis, shared memory access logging","cpp",250,250),
     n(3,"database","Debug Data","Thread states, lock ownership, memory access log, breakpoints, watch data","sqlite",50,450),
     n(4,"ui","Debugger UI","Thread timeline, lock graph, variable inspector, call stack panels","typescript",450,250)],
    ["threads","debugger","race-detection","concurrency","systems"]))
b4.append(make_design("Compiler Explorer", "Educational compiler with lexer, parser, AST, and code generation visualization", "Interactive compiler showing each stage: lexing (token stream), parsing (AST), semantic analysis, IR generation, and x86 assembly output",
    [n(0,"input","Source Editor","Code input area with syntax highlighting, file load, example programs","typescript",50,50),
     n(1,"logic","Lexer & Parser","Lexical analysis with regex DFAs, recursive-descent parser, AST builder","python",250,50),
     n(2,"logic","Semantic Analyzer","Type checking, symbol table management, scope resolution, error reporting","python",250,250),
     n(3,"database","Compilation Store","Token stream, AST nodes, symbol table, IR instructions, assembly output","typescript",50,450),
     n(4,"ui","Pipeline View","Tabbed view: tokens/AST/IR/assembly with syntax highlighting and arrows","typescript",450,250)],
    ["compiler","lexer","parser","ast","education"]))
b4.append(make_design("Bytecode VM", "Stack-based bytecode virtual machine with disassembler and debugger", "Custom stack-based VM with bytecode instruction set, disassembler, single-step debugger, memory viewer, and performance profiler",
    [n(0,"input","Program Loader","Load .bytecode files, write programs in assembly-like syntax, example programs","typescript",50,50),
     n(1,"logic","Bytecode Engine","Fetch-decode-execute loop, operand stack, local variables, control flow","cpp",250,50),
     n(2,"logic","Debugger","Single-step, breakpoint, watch variables, stack trace, memory dump","typescript",250,250),
     n(3,"database","VM State","Instruction memory, operand stack, call frames, heap, symbol table","typescript",50,450),
     n(4,"ui","VM Viewer","Code with current instruction highlighted, stack display, heap view, registers","typescript",450,250)],
    ["vm","bytecode","interpreter","compiler","systems"]))
b4.append(make_design("Serialization Bench", "Serialization format benchmarker comparing protobuf, JSON, XML, and binary", "Performance comparison of serialization formats with throughput, size, and CPU metrics for protobuf, flatbuffers, JSON, MessagePack, CBOR, and custom binary",
    [n(0,"input","Bench Config","Select formats, data schema complexity, payload sizes, iteration count","typescript",50,50),
     n(1,"logic","Serialization Engine","Protobuf, JSON, MessagePack, CBOR, FlatBuffers, custom binary encode/decode","cpp",250,50),
     n(2,"logic","Metrics Collector","Throughput (ops/sec), serialized size, CPU cycles, allocation count tracking","cpp",250,250),
     n(3,"database","Results Store","Benchmark results per format/size/schema, historical comparison data","sqlite",50,450),
     n(4,"ui","Comparison Charts","Bar/line charts for size, speed, memory; sorted multi-metric table","typescript",450,250)],
    ["serialization","protobuf","json","performance","benchmark"]))
b4.append(make_design("Perf Analyzer", "Performance profiling tool with sampling, tracing, and hotspot detection", "Statistical profiler using timer-based sampling, tracepoint capture, call graph construction, and hotspot detection with source line attribution",
    [n(0,"input","Profiling Target","Select process, profiling mode (sampling/tracing), duration, event types","typescript",50,50),
     n(1,"logic","Sampling Engine","Timer-based (SIGPROF) and hardware event (perf_events) sampling, stack unwinding","cpp",250,50),
     n(2,"logic","Call Graph Builder","Stack trace aggregation, call graph construction, hot path detection","cpp",250,250),
     n(3,"database","Profile Data","Sample stacks, call graph edges, symbol table, source mapping","sqlite",50,450),
     n(4,"ui","Flame Graph","Interactive flame graph, call tree view, hot method table, source view","typescript",450,250)],
    ["profiling","performance","flame-graph","optimization","systems"]))
b4.append(make_design("Linker & Loader Lab", "Educational ELF linker showing symbol resolution, relocation, and loading", "Interactive ELF linker/loader showing symbol table resolution, relocation entry processing, section merging, and runtime loading with memory mapping",
    [n(0,"input","Object Files","Load .o/.so files, view ELF structure (sections, symbols, relocations)","typescript",50,50),
     n(1,"logic","Symbol Resolution","Symbol lookup across object files, strong/weak/global resolution rules","cpp",250,50),
     n(2,"logic","Relocation Engine","Relocation processing per type (R_X86_64_JUMP_SLOT, GOT, PLT)","cpp",250,250),
     n(3,"database","ELF Store","Sections, symbols, relocations, resolved addresses, memory layout","binary",50,450),
     n(4,"ui","Linker View","Section layout diagram, symbol table, relocation list, memory map viewer","typescript",450,250)],
    ["linker","elf","loader","binary","systems"]))
b4.append(make_design("Signal Handler Lab", "Unix signal handling sandbox with handler installation and signal flow", "Interactive signal handling laboratory showing signal delivery, handler installation, blocked signals, sigaction flags, and signal-safe function usage",
    [n(0,"input","Signal Config","Select signal, handler type (default/ignore/custom), flags (SA_RESTART/SA_SIGINFO)","typescript",50,50),
     n(1,"logic","Signal Manager","sigaction installation, signal mask management, pending signal tracking","cpp",250,50),
     n(2,"logic","Signal Flow Engine","Signal generation, kernel delivery simulation, handler invocation flow","cpp",250,250),
     n(3,"database","Signal Data","Signal configurations, delivery history, pending/blocked sets, handler stats","typescript",50,450),
     n(4,"ui","Signal Viewer","Signal table, mask display, delivery timeline, handler code viewer","typescript",450,250)],
    ["signals","unix","interrupts","systems","low-level"]))
b4.append(make_design("File Descriptor Explorer", "Process file descriptor explorer showing open files, sockets, and pipes", "Explore open file descriptors of any process: regular files, pipes, sockets, epoll fds, with seek position, flags, and kernel buffer info",
    [n(0,"input","Process Picker","Select process by name or PID, auto-refresh, filter by FD type","typescript",50,50),
     n(1,"logic","ProcFS Parser","Read /proc/[pid]/fd, /proc/[pid]/fdinfo, /proc/[pid]/maps, resolve symlinks","cpp",250,50),
     n(2,"logic","Socket Inspector","Socket state (TCP established/listen), peer address, buffer sizes, options","cpp",250,250),
     n(3,"database","FD Cache","Cached process info, socket/proc data, historical snapshots","sqlite",50,450),
     n(4,"ui","FD Browser","FD list with type icons, tree view by directory, socket details panel","typescript",450,250)],
    ["file-descriptor","process","procfs","linux","systems"]))
b4.append(make_design("Embedded Simulator", "Embedded system simulator with GPIO, timers, interrupts, and UART", "Simulated embedded MCU with ARM Cortex-M peripheral set: GPIO, timers/PWM, interrupts/NVIC, UART, SPI, I2C, ADC with cycle-level timing",
    [n(0,"input","Peripheral Config","Configure GPIO pins, timer periods, interrupt priorities, peripheral clock","typescript",50,50),
     n(1,"logic","CPU Simulator","ARM Thumb-2 instruction interpreter, register file, pipeline stages","cpp",250,50),
     n(2,"logic","Peripheral Models","GPIO, timer, UART, SPI, I2C, ADC functional models with timing accuracy","cpp",250,250),
     n(3,"database","Sim State","CPU registers, memory (flash/RAM/peripherals), interrupt state, trace log","typescript",50,450),
     n(4,"ui","Debug Dashboard","Register view, peripheral panel, memory browser, scope/timing diagram","typescript",450,250)],
    ["embedded","simulator","arm","mcu","systems"]))
b4.append(make_design("IPC Playground", "Inter-process communication demo with pipes, shared memory, message queues, sockets", "Interactive IPC sandbox demonstrating pipe, FIFO, SysV shared memory, POSIX message queues, Unix domain sockets, and D-Bus with latency/throughput measurement",
    [n(0,"input","IPC Config","Select IPC type, message size, transfer mode (1-way/ping-pong/broadcast)","typescript",50,50),
     n(1,"logic","IPC Engine","Pipe/fifo create R/W, shmget/mmap, mq_send/receive, socket pair/bind","cpp",250,50),
     n(2,"logic","Metrics Engine","Latency (min/avg/max), throughput (bytes/sec), context switch count","cpp",250,250),
     n(3,"database","Bench Data","IPC benchmark results per type/size/mode, comparison history","sqlite",50,450),
     n(4,"ui","IPC Dashboard","Results table, latency histogram, throughput chart, code snippet view","typescript",450,250)],
    ["ipc","pipes","shared-memory","sockets","systems"]))
b4.append(make_design("Assembly Playground", "Interactive x86-64 assembly editor with live register display and single-step", "Assembly code editor with live register/memory/flag display, single-step execution, breakpoints, and calling convention visualization",
    [n(0,"input","Assembly Editor","x86-64 assembly text editor with syntax highlighting, labels, comments","typescript",50,50),
     n(1,"logic","x86-64 Emulator","Instruction decoder, register file, flags, memory, syscall emulation","cpp",250,50),
     n(2,"logic","Calling Conv Viewer","System V AMD64 ABI visualization: register args, stack frame, red zone","cpp",250,250),
     n(3,"database","Debug State","Registers, flags, memory pages, execution history, breakpoints","typescript",50,450),
     n(4,"ui","Debug View","Register/flags panel, memory hex viewer, stack diagram, console output","typescript",450,250)],
    ["assembly","x86","low-level","education","systems"]))
b4.append(make_design("Netlink Monitor", "Linux netlink socket monitor for routing, neighbors, and link events", "Real-time netlink monitor showing RTNETLINK messages: routing table changes, neighbor discovery, link state, IP address assignments, and QoS settings",
    [n(0,"input","Netlink Config","Select netlink groups (route/neigh/link/firewall), dump mode, filter","typescript",50,50),
     n(1,"logic","Netlink Engine","NETLINK_ROUTE socket, message parsing (rtattr, nlmsghdr), event subscription","cpp",250,50),
     n(2,"logic","Route Table Parser","Route attributes, nexthops, multipath, metrics, cache info decoding","cpp",250,250),
     n(3,"database","Netlink Store","Routing table, neighbor cache, link states, event history","sqlite",50,450),
     n(4,"ui","Network View","Route table, neighbor table, link list, event log with timestamps","typescript",450,250)],
    ["netlink","networking","linux","routing","systems"]))
b4.append(make_design("CGroup Explorer", "Linux cgroups v2 resource controller explorer and monitor", "Explore and configure cgroups v2 controllers: CPU shares/quotas, memory limits, IO throttling, PID limits, and freezer with real-time pressure monitoring",
    [n(0,"input","CGroup Config","Create/delete cgroups, set controller limits, attach processes","typescript",50,50),
     n(1,"logic","CGroup Manager","cgroupfs operations, controller tree management, limit configuration","cpp",250,50),
     n(2,"logic","Pressure Monitor","PSI (pressure stall information) monitoring: CPU/memory/IO averages","cpp",250,250),
     n(3,"database","CGroup Data","CGroup tree, controller stats, pressure history, process assignments","sqlite",50,450),
     n(4,"ui","CGroup Dashboard","CGroup tree view, controller stats, pressure graphs, process table","typescript",450,250)],
    ["cgroups","containers","linux","resource-management","systems"]))
b4.append(make_design("eBPF Sandbox", "Educational eBPF program loader with verifier and map visualization", "eBPF development sandbox: write/load BPF programs, view verifier log, inspect maps, attach to kprobes/tracepoints, and see kernel event data",
    [n(0,"input","BPF Editor","Write BPF C programs, example templates (kprobe, tracepoint, XDP)","typescript",50,50),
     n(1,"logic","BPF Loader","Clang/LLVM compilation to BPF, bpf() syscall, program/map creation","cpp",250,50),
     n(2,"logic","Verifier Viewer","Parse and display verifier log with instruction-level analysis","cpp",250,250),
     n(3,"database","BPF State","Loaded programs, map contents, event perf buffers, verifier logs","typescript",50,450),
     n(4,"ui","BPF Dashboard","Program list, map editor, event stream, verifier log viewer","typescript",450,250)],
    ["ebpf","bpf","kernel","tracing","systems"]))
b4.append(make_design("DMA Explorer", "Direct Memory Access controller simulator with scatter-gather and descriptors", "DMA controller simulator showing memory-to-memory, memory-to-device transfers with descriptor rings, scatter-gather lists, interrupt on completion",
    [n(0,"input","Transfer Config","Source/destination addresses, transfer size, burst size, descriptor mode","typescript",50,50),
     n(1,"logic","DMA Controller","Register-level DMA engine: source/dest addr, count, control, status registers","cpp",250,50),
     n(2,"logic","Scatter-Gather","Descriptor ring management, linked-list descriptors, completion callbacks","cpp",250,250),
     n(3,"database","Transfer Store","Transfer queue, completed transfers, buffer descriptors, register state","typescript",50,450),
     n(4,"ui","DMA Viewer","Register view, descriptor ring diagram, transfer timeline, buffer viewer","typescript",450,250)],
    ["dma","hardware","memory","low-level","systems"]))
b4.append(make_design("Futex Laboratory", "Fast userspace mutex (futex) synchronization lab with wait/wake operations", "Interactive futex demonstration: futex_wait/wake/requeue, PI futexes, robust list, and comparison with other synchronization primitives",
    [n(0,"input","Futex Config","Select operation (wait/wake/requeue/cmp_requeue), timeout, PI, robust","typescript",50,50),
     n(1,"logic","Futex Engine","Futex syscall wrapper, hash bucket management, wait queue operations","cpp",250,50),
     n(2,"logic","Lock Comparison","Compare futex vs mutex vs spinlock vs rwlock: latency, scalability, fairness","cpp",250,250),
     n(3,"database","Bench Data","Operation latency, wake efficiency, contention metrics, lock profiling","sqlite",50,450),
     n(4,"ui","Futex Dashboard","Operation log, lock comparison charts, wait queue visualization","typescript",450,250)],
    ["futex","synchronization","locking","linux","systems"]))
b4.append(make_design("ALSA Audio Lab", "Linux audio programming sandbox with ALSA PCM/capture and MIDI", "ALSA audio lab: PCM playback/capture, sample rate conversion, channel mapping, MIDI I/O, latency measurement, and audio effect processing",
    [n(0,"input","Audio Config","Device selection, sample rate, buffer size, channels, format (S16_LE/S32_LE/float)","typescript",50,50),
     n(1,"logic","ALSA Engine","PCM hw/sw params, mmap vs RW access, period interrupts, xrun handling","cpp",250,50),
     n(2,"logic","DSP Processor","Volume, EQ, reverb, delay audio effects in real-time on PCM stream","cpp",250,250),
     n(3,"database","Audio Store","Recorded samples, effect presets, device capabilities cache","typescript",50,450),
     n(4,"ui","Audio Dashboard","Waveform display, spectrum analyzer, level meters, effect controls","typescript",450,250)],
    ["alsa","audio","linux","sound","systems"]))
b4.append(make_design("Syscall Tracer", "System call tracer (strace-like) with filtering, statistics, and timeline", "System call tracer using ptrace, showing all syscalls with arguments, return values, error codes, with filtering, latency stats, and timeline view",
    [n(0,"input","Tracer Config","Target process, syscall filter (whitelist/blacklist), follow forks, output mode","typescript",50,50),
     n(1,"logic","Ptrace Engine","PTRACE_SYSCALL tracing, argument extraction from registers, return value capture","cpp",250,50),
     n(2,"logic","Syscall Table","Syscall number to name mapping, argument types, errno translation","cpp",250,250),
     n(3,"database","Trace Data","Syscall records with args/retval/timestamp/pid, aggregated stats","sqlite",50,450),
     n(4,"ui","Trace Viewer","Timeline view, raw syscall list, filtered summary, latency histogram","typescript",450,250)],
    ["syscall","tracing","ptrace","debugging","systems"]))
b4.append(make_design("Virtual Memory Lab", "Virtual memory simulator with page tables, TLB, and MMU emulation", "Educational virtual memory simulation: multi-level page tables, TLB with LRU, page fault handling, swapping, and address translation visualization",
    [n(0,"input","Memory Config","Page size (4KB/2MB/1GB), address space bits, TLB size/associativity","typescript",50,50),
     n(1,"logic","MMU Simulator","Virtual-to-physical translation, multi-level page table walk, TLB lookup","cpp",250,50),
     n(2,"logic","Page Fault Handler","Demand paging, swap in/out, page replacement (LRU/Clock/FIFO/Second Chance)","cpp",250,250),
     n(3,"database","Memory State","Page tables, TLB contents, page frame database, swap store","typescript",50,450),
     n(4,"ui","Memory Viewer","Address space map, page table walk diagram, TLB hit/miss visualization","typescript",450,250)],
    ["virtual-memory","mmu","paging","tlb","systems"]))
b4_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 05-systems-programming/00-overview.md |" for i,d in enumerate(b4)])
all_created.extend(b4)

# ═══════════════════════════════════════════════════════════════
# BATCH 5: 06-databases
# ═══════════════════════════════════════════════════════════════
b5 = []
db_designs = [
    ("SQL Query Analyzer", "Interactive SQL query analyzer with EXPLAIN, indexing advice, and optimization", "SQL query analysis tool showing execution plans, index suggestions, query rewrite recommendations, and performance estimates"),
    ("B+Tree Visualizer", "Interactive B+Tree data structure visualizer with insert/delete/search animations", "Educational B+Tree visualization showing page splits/merges, fanout, height balancing, and leaf node traversal"),
    ("Redis Playground", "Redis data structure playground with key operations and persistence simulation", "Interactive Redis-like in-memory store with strings, hashes, lists, sets, sorted sets, and RDB/AOF persistence simulation"),
    ("SQLite Inspector", "SQLite database file inspector with page browsing and query analysis", "SQLite .db file analyzer showing schema, page layout, B-tree structure, record format, and WAL journal inspection"),
    ("Query Optimizer", "SQL query optimizer with join reordering, index selection, and cost estimation", "Query optimizer demonstrating relational algebra, cost-based optimization, histogram statistics, and join enumeration"),
    ("Index Designer", "Database index design advisor with workload analysis and index recommendation", "Index selection tool analyzing query workload to recommend indexes, covering indexes, and index maintenance strategies"),
    ("NoSQL Comparator", "Compare document, key-value, graph, and time-series DB operations side by side", "Multi-model database comparison showing CRUD operations, query patterns, and performance characteristics across NoSQL paradigms"),
    ("ACID Transaction Lab", "Interactive demonstration of atomicity, consistency, isolation, durability", "Transaction isolation simulator showing dirty reads, non-repeatable reads, phantoms under different isolation levels"),
    ("MVCC Visualizer", "Multi-version concurrency control visualization with snapshot isolation", "MVCC internals showing version chains, snapshot visibility, vacuum/compaction, and transaction conflict detection"),
    ("Data Modeling Studio", "Database schema designer with ER diagrams, normalization, and DDL generation", "Visual data modeling tool with entity-relationship diagrams, normalization to 3NF/BCNF, and SQL DDL generation"),
    ("Migration Manager", "Database schema migration tool with versioning, rollback, and diff", "Schema migration manager with version-controlled migrations, up/down scripts, schema diff, and dry-run preview"),
    ("PostgreSQL Dashboard", "PostgreSQL instance monitor with query statistics, locks, and performance", "PG monitoring dashboard showing active queries, lock waits, table statistics, index usage, and query performance"),
    ("MongoDB Aggregator", "MongoDB aggregation pipeline builder and visualizer", "Visual aggregation pipeline builder with stage-by-stage execution, $lookup/$unwind/$group results visualization"),
    ("Time Series DB Viewer", "Time-series database explorer with downsampling, retention, and continuous queries", "TSDB viewer with metric ingestion, downsampling, retention policies, continuous queries, and time-range aggregation"),
    ("Data Warehouse Modeler", "Star/snowflake schema designer with fact tables, dimensions, and SCD", "Data warehouse modeling tool with fact/dimension table design, slowly changing dimension types, and cube design"),
    ("Full-Text Search Lab", "PostgreSQL/Elasticsearch full-text search playground with ranking", "Full-text search sandbox with tsvector/tsquery, BM25 ranking, fuzzy matching, and search relevance tuning"),
    ("Partition Manager", "Database table partition manager with range/list/hash strategies", "Table partitioning tool for creating/managing partitions, partition pruning analysis, and partition-wise join planning"),
    ("Replication Monitor", "Database replication monitoring with lag, slots, and conflict resolution", "Replication monitoring showing WAL position, replication slots, standby lag, and conflict resolution events"),
    ("Shard Designer", "Distributed database shard design tool with key distribution and rebalancing", "Shard design tool with hash/range partitioning, consistent hashing, rebalancing simulation, and query routing"),
    ("Database Benchmarker", "Database performance benchmarker with customizable workloads and metrics", "Database benchmarking tool supporting TPC-C/TPC-H, custom workloads, concurrency scaling, and latency/throughput analysis")
]
for db_name, db_goal, db_purpose in db_designs:
    b5.append(make_design(db_name, db_goal, db_purpose,
        [n(0,"input","Query/Config Input","User input for queries, schema design, or configuration parameters","typescript",50,50),
         n(1,"logic","Database Engine","Core database logic: query processing, storage engine simulation, optimization","typescript",250,50),
         n(2,"logic","Analysis Engine","Performance analysis, index advice, optimization recommendations","typescript",250,250),
         n(3,"database","Data Store","Stores schema metadata, query history, benchmark results, configuration","sqlite",50,450),
         n(4,"ui","Results Viewer","Query results, visualization, performance metrics, and recommendations display","typescript",450,250)],
        ["database","sql","nosql","performance","tools"]))

b5_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 06-databases/00-index.md |" for i,d in enumerate(b5)])
all_created.extend(b5)

# ═══════════════════════════════════════════════════════════════
# BATCH 6: 13-math
# ═══════════════════════════════════════════════════════════════
b6 = []
math_designs = [
    ("Function Graph Plotter", "2D/3D math function plotter with calculus derivative visualization", "Advanced function plotter with parametric, polar, implicit plots; derivative/normal display, and intersection finding"),
    ("Linear Algebra Lab", "Matrix operations, decompositions, and vector space visualizer", "Interactive linear algebra tool with matrix multiply, LU/QR/SVD decomposition, eigenvalue computation, and vector space visualization"),
    ("Calculus Explorer", "Derivative, integral, and limit calculator with step-by-step solutions", "Symbolic calculus tool showing derivative rules, integration techniques, limit evaluation, and series expansion"),
    ("Statistics Toolbox", "Descriptive statistics, distributions, hypothesis testing, and regression", "Statistical analysis suite with histograms, PDF/CDF, t-tests, ANOVA, linear/logistic regression, and correlation analysis"),
    ("3D Surface Plotter", "Interactive 3D surface plotting with rotation, zoom, and color mapping", "3D surface and contour plotter with customizable colormaps, wireframe/solid rendering, and equation input"),
    ("Number Theory Lab", "Prime number testing, factorization, GCD, modular arithmetic explorer", "Number theory toolbox with primality tests (Miller-Rabin, AKS), factorization (Pollard rho, trial division), modular arithmetic"),
    ("Vector Field Visualizer", "2D/3D vector field visualization with divergence, curl, and flow lines", "Vector field plotter showing field lines, divergence/curl computation, gradient fields, and flow animation"),
    ("Fourier Transform Studio", "FFT/IFFT visualization with signal processing and filtering demos", "Fourier analysis tool showing time/frequency domains, FFT of audio/signals, low/high/bandpass filtering, and spectrograms"),
    ("Probability Simulator", "Monte Carlo simulation with probability distributions and random walks", "Probability simulation with PDF/CDF plots, random sampling, law of large numbers, central limit theorem demos, and random walks"),
    ("Convex Optimization", "Linear programming, gradient descent, and convex optimization visualizer", "Optimization tool with simplex method, gradient descent visualization, Lagrange multipliers, and KKT conditions explorer"),
    ("Differential Eq Solver", "ODE solver with Runge-Kutta, Euler methods, and phase plane plots", "ODE solving with Euler, RK4, adaptive step methods; phase portraits, slope fields, and system of ODEs visualization"),
    ("Graph Theory Lab", "Graph properties, coloring, matching, and network flow visualizer", "Graph theory sandbox with adjacency matrix, graph properties (clique, chromatic number), max flow, bipartite matching"),
    ("Complex Function Plotter", "Complex number and function visualization with domain coloring", "Complex analysis tool with domain coloring, conformal mapping, complex function plots, and Riemann surface visualization"),
    ("Numerical Methods Lab", "Root finding, interpolation, numerical integration, and approximation", "Numerical methods toolkit with Newton/bisection/secant root finding, Lagrange/spline interpolation, numerical integration"),
    ("Financial Calculator", "NPV, IRR, amortization, compound interest, and option pricing", "Financial math tool with time value of money, loan amortization schedules, bond pricing, Black-Scholes option pricing"),
    ("Fraction & Algebra Tutor", "Interactive fraction math, equation solving, and algebra step-by-step", "Educational algebra tool with fraction operations, equation solving steps, polynomial operations, and factoring"),
    ("Set Theory Explorer", "Venn diagrams, set operations, cardinality, and power sets", "Set theory visualizer with Venn diagrams, union/intersection/complement, Cartesian products, and cardinality comparisons"),
    ("Geometry Playground", "Interactive geometry with points, lines, circles, polygons, and transformations", "Geometry construction tool with compass/straightedge simulation, transformations (translate/rotate/reflect), and measurement"),
    ("Turing Machine Simulator", "Turing machine with tape, states, transition rules, and execution trace", "Turing machine simulator with custom rule tables, step-by-step execution, tape visualization, and example programs"),
    ("Chaos & Fractals Lab", "Mandelbrot/Julia sets, L-systems, and fractal generation explorer", "Fractal generation with Mandelbrot/Julia zoom explorer, L-system trees, Barnsley fern, IFS fractals, and color mapping")]
for m_name, m_goal, m_purpose in math_designs:
    b6.append(make_design(m_name, m_goal, m_purpose,
        [n(0,"input","Math Input","Equation/parameter input, data entry, configuration settings","typescript",50,50),
         n(1,"logic","Math Engine","Mathematical computation, algorithm implementation, numerical methods","typescript",250,50),
         n(2,"logic","Analysis Module","Result analysis, error computation, validation, optimization","typescript",250,250),
         n(3,"database","Data Storage","Computation history, results cache, configuration presets","sqlite",50,450),
         n(4,"ui","Visualization","Graphs, charts, 3D visualization, and result display","typescript",450,250)],
        ["mathematics","visualization","education","computation","science"]))

b6_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 13-math/00-index.md |" for i,d in enumerate(b6)])
all_created.extend(b6)

# ═══════════════════════════════════════════════════════════════
# BATCH 7: 20-specialized-computing
# ═══════════════════════════════════════════════════════════════
b7 = []
spec_designs = [
    ("Quantum Gate Sim", "Quantum computing gate simulator with qubit visualization and circuits", "Educational quantum computing simulator with single/qubit gates, Bell states, Grover's algorithm, and circuit visualization"),
    ("DNA Sequence Tool", "DNA/RNA sequence analysis with alignment, BLAST, and mutation detection", "Bioinformatics toolkit with sequence alignment (Needleman-Wunsch, Smith-Waterman), BLAST-like search, and variant calling"),
    ("Molecular Viewer", "3D molecular structure viewer with PDB loading and rotation", "Molecular visualization with PDB file loading, ball-and-stick/spacefill rendering, rotation/zoom, and measurement tools"),
    ("Weather Modeler", "Weather data visualization with isobars, temperature maps, and forecasting", "Meteorological data viewer with GRIB file parsing, isobar/contour maps, temperature gradients, and weather front detection"),
    ("Optimization Solver", "Linear/MILP/NLP solver with branch-and-bound and simplex visualization", "Operations research solver with simplex method, branch-and-bound, constraint propagation, and solution space visualization"),
    ("Computational Geometry", "CGAL algorithms: convex hull, Delaunay, Voronoi, and mesh generation", "Computational geometry toolkit with convex hull (Graham scan, Quickhull), Delaunay triangulation, Voronoi diagrams"),
    ("Protein Folder", "Protein structure prediction using homology modeling and visualization", "Bioinformatics tool for protein BLAST search, homology modeling, secondary structure prediction, and 3D structure viewing"),
    ("Climate Data Viewer", "Climate model output visualization with NetCDF/HDF5 and map overlays", "Climate data analysis with NetCDF/HDF5 readers, temperature/precipitation maps, time-series animation, and anomaly detection"),
    ("Constraint Solver", "Constraint satisfaction problem solver with backtracking and propagation", "CSP solver with forward checking, AC-3 arc consistency, backjumping, and visualization of constraint graphs"),
    ("Fluid Dynamics Lab", "Navier-Stokes fluid simulation with velocity and pressure fields", "2D fluid simulation (stable fluids method) showing velocity field, pressure, vorticity confinement, and smoke/buoyancy effects"),
    ("Circuit Simulator", "Electronic circuit simulator with SPICE-like component modeling", "Circuit simulation with RLC components, diodes, transistors, op-amps; DC/AC/transient analysis; waveform display"),
    ("Orbit Simulator", "Celestial body orbit simulation with N-body gravity and visualization", "Orbital mechanics simulator with N-body gravity, Keplerian elements, Lagrange points, trajectory plotting, and animation"),
    ("Drug Discovery Tool", "Molecular docking simulation with ligand-receptor binding analysis", "Computational drug discovery with molecular docking (AutoDock-like), binding affinity scoring, and molecular interaction visualization"),
    ("Finite Element Lab", "FEM PDE solver with mesh generation and solution visualization", "Finite element method solver for PDEs with mesh generation, element assembly, solver, and solution field visualization"),
    ("Signal Processing Lab", "Digital signal processing with filters, FFT, wavelets, and noise reduction", "DSP toolkit with FIR/IIR filter design, FFT/spectral analysis, wavelet decomposition, adaptive filtering, and noise reduction"),
    ("Game Theory Lab", "Game theory solvers: Nash equilibrium, prisoners dilemma, auction theory", "Game theory analysis with payoff matrices, Nash equilibrium (pure/mixed), iterated prisoner's dilemma, auction simulations"),
    ("Image Processing Engine", "Image processing with convolution, morphology, edge detection, segmentation", "Computer vision toolkit with convolution filters, morphological ops, edge detection (Canny/Sobel), segmentation (watershed/mean-shift)"),
    ("Neural Network Lab", "Neural network from scratch with backpropagation and visualization", "Educational neural network builder with forward/backward pass, gradient descent, activation functions, and decision boundary plots"),
    ("Cryptography Lab", "Symmetric/asymmetric encryption, hashing, and protocol simulation", "Cryptography toolkit with AES/ChaCha20, RSA/ECC, SHA-256, digital signatures, TLS handshake simulation, and cryptanalysis demos"),
    ("Robotics Simulator", "Robot kinematics, path planning, and sensor simulation", "Robotics simulator with forward/inverse kinematics (DH parameters), RRT path planning, sensor noise models, and visualization")]
for s_name, s_goal, s_purpose in spec_designs:
    b7.append(make_design(s_name, s_goal, s_purpose,
        [n(0,"input","Domain Input","Domain-specific input parameters, data loading, configuration","typescript",50,50),
         n(1,"logic","Core Algorithm","Specialized algorithm implementation for the domain","typescript, python",250,50),
         n(2,"logic","Analysis Engine","Result analysis, validation, error computation, statistics","typescript",250,250),
         n(3,"database","Data Store","Simulation data, results, parameters, reference data","sqlite",50,450),
         n(4,"ui","Visualization","Domain-specific visualization: 3D, plots, maps, animations","typescript",450,250)],
        ["specialized","computation","science","simulation","visualization"]))

b7_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 20-specialized-computing/00-overview.md |" for i,d in enumerate(b7)])
all_created.extend(b7)

# ═══════════════════════════════════════════════════════════════
# BATCH 8: 27-data-engineering
# ═══════════════════════════════════════════════════════════════
b8 = []
de_designs = [
    ("ETL Pipeline Builder", "Visual ETL pipeline builder with extract, transform, load stages", "Visual ETL designer with drag-and-drop stages, data preview, transformation functions, and scheduled execution"),
    ("Data Quality Dashboard", "Data quality monitoring with profiling, validation, and anomaly detection", "Data quality tool with column profiling, schema validation, duplicate detection, outlier detection, and quality scoring"),
    ("Stream Processor", "Real-time stream processing with Kafka-like topics and window operations", "Stream processing engine with topic/subscribe model, window operations (tumbling/sliding), watermark tracking, and event time processing"),
    ("Data Lineage Explorer", "End-to-end data lineage tracking and column-level provenance visualization", "Data lineage tool showing column-level provenance, transformation graph, data flow diagrams, and impact analysis"),
    ("Schema Registry", "Schema management with versioning, compatibility checks, and evolution", "Schema registry with Avro/Protobuf/JSON Schema, compatibility checking (backward/forward/full), and schema evolution tracking"),
    ("Data Catalog Browser", "Data asset catalog with search, tags, metadata, and usage analytics", "Enterprise data catalog with asset search, business glossary, technical metadata, usage stats, and certification badges"),
    ("Workflow Scheduler", "DAG-based workflow scheduler with dependencies, retries, and monitoring", "Workflow scheduler (Airflow-like) with DAG definition, task dependencies, retry logic, scheduler, and execution monitoring"),
    ("Data Warehouse Builder", "Automated data warehouse builder with schema generation and indexing", "DW builder with dimensional model generation, ETL mapping, index recommendation, and storage optimization"),
    ("Change Data Capture", "CDC pipeline for database change tracking with debezium-like architecture", "CDC tool with WAL/trigger-based capture, event serialization (Avro/JSON), sink connectors, and schema evolution"),
    ("Data Masking Tool", "PII detection and data masking with anonymization and tokenization", "Data privacy tool with PII detection (regex/NER), masking techniques (redaction, tokenization, k-anonymity, differential privacy)"),
    ("Data Lake Explorer", "Data lake file browser with Parquet/ORC/Avro inspection and query", "Data lake explorer showing file formats, schema inference, partition layout, statistics, and SQL query on files"),
    ("Batch Processor", "Batch data processing framework with partitioning, retry, and checkpointing", "Batch processing framework with chunk-oriented processing, partitioning, skip/retry policies, checkpoint/restart, and metrics"),
    ("Feature Store", "ML feature management with point-in-time joins and serving", "Feature store with feature definitions, point-in-time correct joins, online/offline serving, feature validation, and monitoring"),
    ("Data Pipeline Monitor", "Pipeline monitoring dashboard with metrics, alerts, and SLAs", "Pipeline monitoring with task latency, data freshness metrics, SLA tracking, alerting rules, and incident management"),
    ("Data Compaction Tool", "Data compaction and compression tool for Parquet/ORC with multiple codecs", "File compaction tool with size-based/interval-based strategies, compression (snappy/zstd/gzip), and statistics optimization"),
    ("Schema Migrator", "Schema migration tool with diff, compatibility check, and auto-migration", "Schema migration with schema diff generation, compatibility validation, auto-migration scripts, and dry-run execution"),
    ("Query Federation Engine", "Cross-database query federation engine with pushdown optimization", "Query federation with heterogeneous source access, predicate pushdown, join across sources, cost-based routing"),
    ("Data Sampling Studio", "Statistical data sampling tool with stratified, reservoir, and cluster sampling", "Data sampling with various strategies (simple random, stratified, reservoir, cluster), sample size calculation, and bias detection"),
    ("Columnar Analytics", "Columnar query engine with vectorized execution and SIMD optimization", "Columnar analytics engine with dictionary encoding, run-length encoding, vectorized expression evaluation, and late materialization"),
    ("Data Version Control", "Data versioning tool with git-like operations for datasets and experiments", "Data version control with commit/diff/branch of datasets, experiment tracking, data registry, and lineage tracking")]
for de_name, de_goal, de_purpose in de_designs:
    b8.append(make_design(de_name, de_goal, de_purpose,
        [n(0,"input","Pipeline Config","Pipeline/data configuration, source/target selection, scheduling","typescript",50,50),
         n(1,"logic","Data Processor","Data transformation, validation, processing logic","python",250,50),
         n(2,"logic","Scheduler/Orch","Workflow orchestration, dependency management, execution control","python",250,250),
         n(3,"database","Data Store","Pipeline metadata, execution logs, data catalogs, quality metrics","sqlite",50,450),
         n(4,"ui","Pipeline Dashboard","Pipeline DAG view, execution status, metrics, data preview","typescript",450,250)],
        ["data-engineering","etl","pipeline","data-quality","analytics"]))

b8_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 27-data-engineering/00-overview.md |" for i,d in enumerate(b8)])
all_created.extend(b8)

# ═══════════════════════════════════════════════════════════════
# BATCH 9: 33-devops-sre-tooling
# ═══════════════════════════════════════════════════════════════
b9 = []
devops_designs = [
    ("CI/CD Pipeline Builder", "Visual CI/CD pipeline builder with stages, parallel steps, and deployment", "CI/CD designer with pipeline as code generation, matrix builds, caching, artifact management, and deployment stages"),
    ("Docker Compose Lab", "Docker Compose visual editor with service config and networking", "Container orchestration designer with multi-service config, network/volume setup, health checks, and docker-compose generation"),
    ("K8s Resource Designer", "Kubernetes resource YAML visual designer with validation", "K8s resource designer: Deployments, Services, ConfigMaps, PVCs with form-based configuration and validation"),
    ("Monitoring Dashboard", "Time-series monitoring dashboard with PromQL queries and alert rules", "Monitoring dashboard with metric explorer, PromQL query builder, graph panels, alert rule editor, and on-call schedule"),
    ("Log Aggregator", "Centralized log aggregation with parsing, search, and pattern detection", "Log aggregation with multi-source collection, log parsing (grok/regex), full-text search, and anomaly pattern detection"),
    ("Terraform Visualizer", "Terraform plan visualization with resource graph and dependency view", "Terraform state viewer showing resource dependency graph, plan diff visualization, resource attributes, and module structure"),
    ("Alert Manager", "Alert management with deduplication, silencing, and escalation", "Alert manager with deduplication, grouping, inhibition rules, silence management, escalation policies, and notification routing"),
    ("Incident Response Tool", "Incident management with severity, runbooks, timelines, and postmortems", "Incident response platform with severity classification, runbook automation, timeline tracking, communication channels, postmortem generation"),
    ("Service Mesh Explorer", "Istio/Linkerd service mesh visualization with traffic and telemetry", "Service mesh explorer showing service graph, traffic metrics (HTTP/gRPC), circuit breakers, retries, and mTLS status"),
    ("Chaos Engineering Lab", "Chaos experiment designer with fault injection and steady-state validation", "Chaos engineering with fault types (pod kill, network delay, CPU stress), experiments, blast radius control, and hypothesis testing"),
    ("Cost Explorer", "Cloud cost analysis with resource mapping, savings recommendations, and budgets", "Multi-cloud cost analysis with resource cost attribution, savings plans, reserved instance recommendations, and budget alerts"),
    ("Secret Manager", "Vault-based secret management with rotation, access audit, and policies", "Secret management with encrypted storage, dynamic secrets, access policies, secret rotation, and audit logging"),
    ("SLO Dashboard", "Service level objective tracker with burn rate alerts and error budgets", "SLO management with SLI definition, SLO targets, error budget calculation, burn rate alerts, and reliability scorecards"),
    ("Config Sync Tool", "GitOps configuration sync with drift detection and auto-remediation", "GitOps sync tool with Git repository watching, config drift detection, auto-remediation, and sync status dashboard"),
    ("Capacity Planner", "Infrastructure capacity planning with trends, forecasting, and what-if", "Capacity planning with resource utilization trends, growth forecasting (linear/exponential), what-if scenarios, and recommendations"),
    ("Canary Deployer", "Canary deployment manager with traffic splitting and metrics comparison", "Canary deployment with traffic shifting, metrics comparison (latency/errors), auto-rollback, and deployment analysis"),
    ("Compliance Scanner", "Infrastructure compliance scanning with CIS benchmarks and policies", "Compliance scanning with CIS benchmark checks, custom policy engine (OPA/Rego), remediation suggestions, and compliance reporting"),
    ("Runbook Automation", "Automated runbook engine with manual steps, approvals, and error handling", "Runbook automation with step library, manual approval gates, error handling, output collection, and execution history"),
    ("Image Scanner", "Container image vulnerability scanner with SBOM generation and policies", "Container security scanner with CVE database, vulnerability severity scoring, SBOM generation (SPDX/CycloneDX), and policy enforcement"),
    ("Backup & Disaster Recovery", "Backup/DR planner with RTO/RPO, replication, and recovery testing", "Backup/DR planning with RTO/RPO targets, replication configuration, backup scheduling, recovery drills, and compliance reporting")]
for d_name, d_goal, d_purpose in devops_designs:
    b9.append(make_design(d_name, d_goal, d_purpose,
        [n(0,"input","Config Input","Infrastructure configuration, alert settings, pipeline definition","typescript",50,50),
         n(1,"logic","Orchestration","Workflow orchestration, deployment logic, monitoring algorithms","typescript",250,50),
         n(2,"logic","Analysis Engine","Metrics analysis, compliance checking, cost calculation","typescript",250,250),
         n(3,"database","State Store","Infrastructure state, metrics history, config data, audit logs","sqlite",50,450),
         n(4,"ui","Operations Dashboard","Dashboards, pipeline views, alert panels, cost charts","typescript",450,250)],
        ["devops","sre","monitoring","ci-cd","infrastructure"]))

b9_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 33-devops-sre-tooling/00-overview.md |" for i,d in enumerate(b9)])
all_created.extend(b9)

# ═══════════════════════════════════════════════════════════════
# BATCH 10: 36-search-recs-personalization
# ═══════════════════════════════════════════════════════════════
b10 = []
search_designs = [
    ("Search Engine Sim", "Mini search engine with crawling, indexing, BM25 ranking, and query", "Educational search engine with web crawling, inverted index, BM25 ranking, query expansion, and result snippets"),
    ("Elasticsearch Dashboard", "ES cluster monitor with index stats, query analysis, and mapping viewer", "Elasticsearch admin dashboard with cluster health, index mapping, query performance, shard distribution, and search analysis"),
    ("Vector Search Lab", "Vector embedding search with HNSW/IVF indexing and hybrid search", "Vector similarity search with embeddings, HNSW/IVF index builders, hybrid (BM25+vector) search, and recall benchmarking"),
    ("Recommender Studio", "Collaborative + content-based recommendation engine with evaluation", "Recommendation system builder with collaborative filtering (ALS, NCF), content-based, hybrid approaches, and offline evaluation"),
    ("Personalization Engine", "User segmentation with bandit algorithms and A/B experimentation", "Personalization engine with user segmentation, multi-armed bandits, contextual bandits, and A/B test result analysis"),
    ("Feature Platform", "Feature engineering and serving platform for ML models", "Feature platform with feature definitions, transformation functions, online/offline serving, feature validation, and monitoring"),
    ("Search Relevance Lab", "Search relevance tuning with NDCG/MAP/MRR metrics and pairwise evaluation", "Search relevance toolkit with judged queries, ranking metrics (NDCG, MAP, MRR), interleaving experiments, and pairwise evaluation"),
    ("Query Understanding", "Query parsing, intent classification, entity extraction, and spelling correction", "Search query understanding with tokenization, intent classification, named entity recognition, spelling correction, and query expansion"),
    ("Learning to Rank", "LTR model training with LambdaMART and feature engineering pipeline", "Learning-to-rank with feature extraction, LambdaMART/Gradient Boosted Trees training, model evaluation, and online serving"),
    ("Content Categorizer", "Document classifier with taxonomy management and active learning", "Document categorization with hierarchical taxonomy, text classification (CNN/BERT), active learning, and label suggestion"),
    ("Semantic Search Lab", "BERT/Transformer-based semantic search with cross-encoder reranking", "Semantic search with bi-encoder embedding, cross-encoder reranking, ColBERT late interaction, and dense retrieval evaluation"),
    ("Real-time Personalizer", "Real-time user behavior tracking and instant personalization", "Real-time personalization with event stream processing, user profile updates, real-time feature computation, and instant recommendations"),
    ("Search Analytics", "Search log analytics with click-through rate, session analysis, and funnel", "Search analytics with click-through rate tracking, search session analysis, zero-result rate, funnel analysis, and query trends"),
    ("Image Search Engine", "CLIP-based image similarity search with text-to-image retrieval", "Visual search engine using CLIP embeddings for text-to-image and image-to-image search with vector indexing"),
    ("Feed Ranking Engine", "Social media feed ranking with engagement prediction and diversity", "Feed ranking with candidate generation, engagement prediction (CTR), diversity mixing, fatigue penalties, and real-time serving"),
    ("Autocomplete Service", "Prefix-based autocomplete with frequency ranking and personalization", "Autocomplete engine with trie-backed prefix search, frequency ranking, user-specific personalization, and typo tolerance"),
    ("Market Basket Analysis", "Frequent itemset mining with Apriori/FP-Growth and association rules", "Market basket analysis with frequent itemset mining, association rule generation, lift/confidence metrics, and recommendation"),
    ("Content Similarity Search", "Document similarity using TF-IDF, LSA, and topic modeling visualization", "Content-based similarity with TF-IDF cosine similarity, LSA topic modeling (SVD), NMF topic extraction, and document clustering"),
    ("ML Model Serving", "Model serving platform with REST/gRPC endpoints and batch inference", "ML model serving with model registry, REST/gRPC endpoints, batch inference, prediction caching, and performance monitoring"),
    ("Recommendation Eval", "Offline/online recommendation evaluation with counterfactual estimation", "RecSys evaluation framework with offline metrics (precision/recall/NDCG), counterfactual estimation, interleaving, and replay")]
for s_name, s_goal, s_purpose in search_designs:
    b10.append(make_design(s_name, s_goal, s_purpose,
        [n(0,"input","Search/Recs Config","Query input, configuration parameters, data source selection","typescript",50,50),
         n(1,"logic","Search Engine","Indexing, retrieval, ranking, personalization algorithms","python",250,50),
         n(2,"logic","Evaluation","Relevance evaluation, A/B testing, performance metrics","python",250,250),
         n(3,"database","Index & Data","Search index, user profiles, interaction logs, model artifacts","sqlite",50,450),
         n(4,"ui","Results Display","Search results, recommendations, analytics dashboards","typescript",450,250)],
        ["search","recommendations","personalization","ranking","ml"]))

b10_index = "\n".join([f"| {i+1:2d} | {d['name']:30s} | 36-search-recs-personalization/00-overview.md |" for i,d in enumerate(b10)])
all_created.extend(b10)

# ═══════════════════════════════════════════════════════════════
# WRITE ALL TO DESIGNS.JSON
# ═══════════════════════════════════════════════════════════════
existing.extend(all_created)
with open(DESIGNS_PATH, 'w') as f:
    json.dump(existing, f, indent=2)

print(f"✅ Wrote {len(all_created)} new designs to {DESIGNS_PATH}")
print(f"   Total designs now: {len(existing)}")

# Write bible reference files per batch
batches = [
    ("03-desktop-apps", b3),
    ("05-systems-programming", b4),
    ("06-databases", b5),
    ("13-math", b6),
    ("20-specialized-computing", b7),
    ("27-data-engineering", b8),
    ("33-devops-sre-tooling", b9),
    ("36-search-recs-personalization", b10)
]

for cat, designs in batches:
    bible_dir = f"bible-reference/00-app-designs/{cat}"
    os.makedirs(bible_dir, exist_ok=True)
    write_bible_refs(cat, designs, bible_dir)
    # Write index if not exists
    idx = os.path.join(bible_dir, "00-index.md")
    if not os.path.exists(idx):
        with open(idx, 'w') as f:
            f.write(f"# 🏗️ Batch Designs: {cat}\n\n| # | Name |\n|---|------|\n")
            for i, d in enumerate(designs):
                fn = f"{i+1:02d}-{safe_filename(d['name'])}.md"
                f.write(f"| {i+1:2d} | [{d['name']}]({fn}) |\n")

print("\n✅ ALL BATCHES COMPLETE!")
print(f"   Total: {len(all_created)} new designs across 8 batches")
print(f"   Grand total in designs.json: {len(existing)}")
