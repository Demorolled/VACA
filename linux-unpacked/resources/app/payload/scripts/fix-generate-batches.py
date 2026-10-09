#!/usr/bin/env python3
"""Generate Batches 3-10: 160 designs for remaining bible categories. Fixed version."""
import json, os, re

DESIGNS_PATH = "data/designs.json"
BIBLE_BASE = "bible-reference/00-app-designs"
NOW = "2026-06-19T14:00:00.000Z"

with open(DESIGNS_PATH) as f:
    existing = json.load(f)

def n(id_, type_, label, desc, lang, x, y):
    return {"id": f"saved_{id_}", "type": type_, "label": label, "description": desc, "language": lang, "position": {"x": x, "y": y}}

def e(src, tgt):
    return {"source": f"node_{src}", "target": f"node_{tgt}"}

def safe(name):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ','-').replace('/',''))).strip('-')[:60]

all_created = []

def add(cat, name, goal, purpose, nodes, edges, tags):
    d = {
        "id": f"design_{cat}_{len(existing)+len(all_created)}",
        "name": name, "goal": goal, "purpose": purpose, "targetOS": "linux",
        "nodes": nodes, "edges": edges,
        "roadmap": f"App: {name}\nTarget: linux\nNodes: {len(nodes)}\nConnections: {len(edges)}",
        "createdAt": NOW, "updatedAt": NOW, "source": "local", "tags": tags
    }
    all_created.append(d)
    # Write bible ref
    bdir = os.path.join(BIBLE_BASE, cat)
    os.makedirs(bdir, exist_ok=True)
    fn = f"{len([f for f in os.listdir(bdir) if f.endswith('.md') and f != '00-index.md']) + 1:02d}-{safe(name)}.md"
    nodes_str = '\n'.join([f"  - **{x['label']}** ({x['type']}): {x['description']}" for x in nodes])
    with open(os.path.join(bdir, fn), 'w') as f:
        f.write(f"# 🏗️ {name}\n\n**ID:** `{d['id']}` | **Category:** {cat} | **Target:** linux\n\n## Goal\n{goal}\n\n## Purpose\n{purpose}\n\n## Nodes ({len(nodes)})\n{nodes_str}\n\n## Tags\n{', '.join(tags)}\n\n---\n*Design generated for Visual AI Architect*\n")

# ═══════════ BATCH 3: desktop-apps ═══════════
b3 = [
    ("Text Editor Pro","Full-featured text editor with syntax highlighting, find/replace, file management","Desktop text editor with gap buffer, syntax highlighting, find/replace with regex, tabs, file tree",
     [n(0,"input","File Handler","Open/save/create files, file tree, drag-drop","ts",50,50),n(1,"logic","Gap Buffer","Efficient edit with gap buffer, cursor mgmt","ts",250,50),n(2,"logic","Syntax Highlighter","Token-based highlighting, 20+ langs, themes","ts",250,250),n(3,"database","File Store","File cache, recent files, session state","sqlite",50,450),n(4,"ui","Editor Canvas","Editor with line numbers, gutter, minimap","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["text-editor","editor","productivity","desktop"]),
    ("File Explorer","Dual-pane file manager with tree navigation, search, and file operations","Desktop file manager with tree/list view, copy/move/delete/rename, file search, context menu",
     [n(0,"input","Nav Bar","Path bar, breadcrumbs, back/forward, bookmarks","ts",50,50),n(1,"logic","Dir Engine","Dir traversal with lazy loading, sort, filter","ts",250,50),n(2,"logic","File Ops","Copy/move/delete/rename with progress and undo","ts",250,250),n(3,"database","File Index","File metadata cache, dir structure, bookmarks","sqlite",50,450),n(4,"ui","File List View","Dual-pane with icons/details/list modes","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["file-explorer","file-manager","desktop","utility"]),
    ("Markdown Editor","Live markdown editor with split-pane preview and HTML/PDF export","WYSIWYG markdown with GFM tables, code blocks, task lists, live preview, export",
     [n(0,"input","Editor Input","Rich markdown text input with toolbar","ts",50,50),n(1,"logic","Markdown Parser","Markdown-to-HTML, GFM tables, fenced code","ts",250,50),n(2,"logic","Preview Engine","Debounced preview, scroll sync","ts",250,250),n(3,"database","Doc Store","Save/load, history, auto-save drafts","sqlite",50,450),n(4,"ui","Split View","Editor left, Preview right, toolbar top","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["markdown","editor","productivity","documentation"]),
    ("Media Player Desktop","Audio/video player with playlist, equalizer, and subtitle support","Desktop media player MP3/FLAC/MP4/MKV with playlist, EQ, subtitles, speed control",
     [n(0,"input","Media Loader","File open, drag-drop, URL input, folder import","ts",50,50),n(1,"logic","Playback Engine","Audio/video decode, play/pause/seek/volume","ts",250,50),n(2,"logic","Equalizer","10-band EQ with presets: rock, pop, jazz","ts",250,250),n(3,"database","Media Library","Playlist, media metadata, play count cache","sqlite",50,450),n(4,"ui","Player UI","Video canvas, audio viz, playlist, EQ panel","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["media-player","audio","video","entertainment"]),
    ("Image Viewer","Image viewer with basic editing, filters, and format conversion","Desktop image viewer PNG/JPG/GIF/WEBP with crop, resize, rotate, filters, batch convert",
     [n(0,"input","Image Loader","File browser, drag-drop, clipboard, URL","ts",50,50),n(1,"logic","Image Processor","Crop, resize, rotate, flip, color adjust","ts",250,50),n(2,"logic","Filter Engine","Blur, sharpen, edge, sepia, grayscale","ts",250,250),n(3,"database","Image Cache","Thumbnails, edit history, EXIF data","sqlite",50,450),n(4,"ui","Viewer","Image display with zoom/pan, filter preview","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["image-viewer","photo","filters","desktop"]),
    ("PDF Reader","PDF reader with text selection, bookmarks, annotations, and form filling","Desktop PDF reader with page rendering, text search, annotations, form filling, bookmarks",
     [n(0,"input","Doc Input","File open, page nav, bookmark jump, search","ts",50,50),n(1,"logic","PDF Engine","Page render, text extraction, search","ts",250,50),n(2,"logic","Annotation Sys","Highlight, underline, comment, freehand draw","ts",250,250),n(3,"database","Doc Store","Page cache, annotations, bookmarks, position","sqlite",50,450),n(4,"ui","Reader View","Page display, sidebar, toolbar","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["pdf-reader","document","annotations","productivity"]),
    ("Terminal Emulator","GPU-accelerated terminal with tabs, themes, and split panes","GPU-accelerated terminal with multiple profiles, tabs, split panes, 256-color, search",
     [n(0,"input","Keyboard Input","Raw keyboard processing, escape sequences","ts",50,50),n(1,"logic","PTY Manager","PTY management, shell spawn, terminal state","ts",250,50),n(2,"logic","Render Engine","GPU text rendering, ligatures, AA, themes","ts",250,250),n(3,"database","Config Store","Profile settings, session history, themes","sqlite",50,450),n(4,"ui","Terminal View","Scrollback, tab bar, split pane manager","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["terminal","emulator","console","developer-tools"]),
    ("Code IDE","Lightweight IDE with project management, Git, LSP, and debugging","Desktop IDE with project tree, Git status/diff/blame, LSP client, debugger, terminal",
     [n(0,"input","Project Manager","Folder open, file tree with Git status icons","ts",50,50),n(1,"logic","Code Intel","LSP client: autocomplete, go-to-def, hover","ts",250,50),n(2,"logic","Git Integration","Status, diff, blame, commit, branch mgmt","ts",250,250),n(3,"database","Index Store","Symbol index, file cache, Git data, workspace","sqlite",50,450),n(4,"ui","IDE Workspace","Tabbed editor, sidebar, panel","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["ide","code-editor","git","developer-tools","lsp"]),
    ("Notes & Wiki","Personal knowledge base with rich text, tags, backlinks, and full-text search","Desktop notes with WYSIWYG rich text, tag organization, wiki backlinks, full-text search",
     [n(0,"input","Note Editor","Rich text, toolbar, image embed, code blocks","ts",50,50),n(1,"logic","Wiki Engine","Tag indexing, backlink detection, graph view","ts",250,50),n(2,"logic","Search Engine","Full-text search, fuzzy matching, tag filter","ts",250,250),n(3,"database","Note Store","SQLite notes, tags, links, attachments","sqlite",50,450),n(4,"ui","Workspace","Editor pane, sidebar, graph visualization","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["notes","wiki","knowledge-base","productivity"]),
    ("Scientific Calculator","Advanced calculator with graphing, unit conversion, and equation solving","Desktop scientific calculator with expression parser, 2D/3D graphing, unit conversion, solver",
     [n(0,"input","Expression Input","Expression entry with syntax highlighting","ts",50,50),n(1,"logic","Expression Engine","Shunting-yard parser, 200+ functions","ts",250,50),n(2,"logic","Graph Plotter","2D/3D plotting, zoom, pan, trace, overlay","ts",250,250),n(3,"database","History Store","Calc history, saved graphs, constants","sqlite",50,450),n(4,"ui","Calculator UI","Display, graph canvas, unit converter","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["calculator","scientific","graphing","math"]),
    ("Contact Manager","Personal CRM with contact groups, search, and vCard import/export","Desktop contacts with customizable fields, groups, birthday reminders, vCard import/export",
     [n(0,"input","Contact Form","Custom fields, avatar upload, address auto","ts",50,50),n(1,"logic","Contact Engine","Dedup (fuzzy), groups, birthday calc","ts",250,50),n(2,"logic","Import/Export","vCard, CSV, JSON import/export with mapping","ts",250,250),n(3,"database","Contact DB","SQLite contacts, groups, history, tags","sqlite",50,450),n(4,"ui","Contact Browser","Card/list, search/filter, groups sidebar","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["contacts","crm","address-book","productivity"]),
    ("Calendar App","Desktop calendar with events, reminders, recurrence, and iCal sync","Calendar with month/week/day views, event recurrence, reminders, iCal import/export, Google Calendar sync",
     [n(0,"input","Event Creator","Title, date/time, duration, recurrence, notes","ts",50,50),n(1,"logic","Schedule Engine","Recurrence expansion, conflict detection","ts",250,50),n(2,"logic","Reminder System","Popup/sound reminders, snooze, email notify","ts",250,250),n(3,"database","Calendar Store","Events, reminders, calendars, iCal data","sqlite",50,450),n(4,"ui","Calendar View","Month/week/day views, mini-calendar","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["calendar","schedule","events","productivity"]),
    ("Music Organizer","Music library manager with tag editing, duplicate finder, and playlists","Desktop music organizer with ID3 tag editing, fingerprint-based dedup, smart playlists, album art",
     [n(0,"input","Library Import","Scan dirs, watch folders, auto-detect files","ts",50,50),n(1,"logic","Tag Editor","ID3/FLAC/MP4 tag editing, batch ops, art mgmt","ts",250,50),n(2,"logic","Dedup Finder","Audio fingerprint dedup detection","ts",250,250),n(3,"database","Music DB","SQLite with tracks, albums, artists, playlists","sqlite",50,450),n(4,"ui","Library Browser","Album/artist/track grid, search, playlist","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["music","organizer","audio","library"]),
    ("Video Converter","Batch video converter with format profiles, crop, and quality presets","Desktop video converter H.264/H.265/VP9/AV1, batch processing, crop/resize, progress tracking",
     [n(0,"input","File Importer","Add files/folders, drag-drop, thumbnail preview","ts",50,50),n(1,"logic","Conversion Engine","FFmpeg pipeline, HW acceleration (NVENC)","ts",250,50),n(2,"logic","Batch Manager","Queue, parallel convert, priority, actions","ts",250,250),n(3,"database","Job Store","Jobs, presets, profiles, conversion history","sqlite",50,450),n(4,"ui","Converter UI","File list, format presets, quality, progress","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["video","converter","transcoding","batch"]),
    ("Screen Recorder","Desktop screen recorder with audio, annotations, and GIF/MP4 export","Screen capture with region/window, mic audio, mouse highlight, drawing annotations",
     [n(0,"input","Capture Config","Source (screen/region/window), audio, quality","ts",50,50),n(1,"logic","Capture Engine","Frame capture with HW encoding, audio mix","ts",250,50),n(2,"logic","Annotation Tool","Real-time drawing overlay: pen, arrow, rect","ts",250,250),n(3,"database","Recording Store","Video storage, auto-save, export profiles","sqlite",50,450),n(4,"ui","Recorder UI","Preview, record/pause/stop, timeline","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["screen-recorder","capture","video","recording"]),
    ("Clipboard Manager","Clipboard history with snippets, search, and LAN sync","Desktop clipboard manager: text/image/file history, favorites, full-text search, LAN sync",
     [n(0,"input","Clipboard Monitor","System clipboard hook, format detection","ts",50,50),n(1,"logic","History Engine","History mgmt, dedup, expiration, categories","ts",250,50),n(2,"logic","Sync Engine","LAN sync via WebRTC, encrypted transfer","ts",250,250),n(3,"database","Clip Store","SQLite history, favorites, snippets","sqlite",50,450),n(4,"ui","Clipboard Panel","History list, search, favorite sidebar","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["clipboard","manager","productivity","utility"]),
    ("System Monitor","System resource monitor with CPU/RAM/disk/network graphs and process mgmt","Real-time system monitor with CPU/RAM/disk/network graphs, process list, temperature, alerts",
     [n(0,"input","Monitor Config","Refresh rate, alert thresholds, graph colors","ts",50,50),n(1,"logic","System Collector","CPU per core, RAM/swap, disk I/O, network, procs","ts",250,50),n(2,"logic","Alert Engine","Threshold monitoring, alerts, notification","ts",250,250),n(3,"database","Metrics Store","Time-series metrics, alert history","sqlite",50,450),n(4,"ui","Dashboard","Tabbed: CPU/RAM/Disk/Network graphs, proc table","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["system-monitor","performance","metrics","utility"]),
    ("Password Manager","Secure password vault with AES-256 encryption, generator, and auto-fill","Desktop password manager AES-256-GCM vault, password generator, auto-type, CSV import/export",
     [n(0,"input","Vault Unlock","Master password, biometric, key file auth","ts",50,50),n(1,"logic","Crypto Engine","AES-256-GCM, PBKDF2, argon2 hashing","ts",250,50),n(2,"logic","Password Gen","Configurable: length, char sets, pronounceable","ts",250,250),n(3,"database","Vault Store","Encrypted SQLite entries, categories, TOTP","sqlite",50,450),n(4,"ui","Vault Browser","Entry list, detail, generator, auto-type","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["password-manager","security","encryption","vault"]),
    ("App Launcher","Keyboard-driven app launcher with fuzzy search, calculator, and plugins","Desktop launcher like Spotlight/Alfred: fuzzy search, calculations, web search, file search",
     [n(0,"input","Quick Input","Hotkey search bar, fuzzy text, autocomplete","ts",50,50),n(1,"logic","Search Engine","Fuzzy match: apps, files, contacts, plugins","ts",250,50),n(2,"logic","Plugin System","Plugin loader, action dispatcher","ts",250,250),n(3,"database","Index Store","App/file index, plugin registry, usage data","sqlite",50,450),n(4,"ui","Launcher UI","Overlay with results, categories, actions","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["app-launcher","search","productivity","plugin"]),
    ("Backup Tool","File backup with scheduled sync, versioning, dedup, and cloud targets","Desktop backup with full/incremental, scheduled sync, version history, hash-based dedup, cloud targets",
     [n(0,"input","Backup Config","Source/dest, schedule, file filter, encryption","ts",50,50),n(1,"logic","Backup Engine","File scan, change detection, incremental, dedup","ts",250,50),n(2,"logic","Restore Mgr","Version browser, selective/full restore, verify","ts",250,250),n(3,"database","Backup Catalog","File index, version history, checksums, jobs","sqlite",50,450),n(4,"ui","Backup Dashboard","Job status, log, version timeline, restore","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["backup","sync","file-management","utility"])
]
for args in b3:
    add("03-desktop-apps", *args)

# ═══════════ BATCH 4: systems-programming ═══════════
b4 = [
    ("Memory Profiler","Real-time memory profiler with allocation tracking and leak detection","Memory analysis: malloc/free tracking, leak detection, heap fragmentation, allocation hotspot profiling",
     [n(0,"input","Process Select","Attach process, launch new, load core dump","ts",50,50),n(1,"logic","Tracer Engine","malloc/free hook (LD_PRELOAD), stack capture","cpp",250,50),n(2,"logic","Leak Detector","Ref count, cyclic ref, unfreed block report","cpp",250,250),n(3,"database","Profiling DB","Time-series alloc data, call stack index","sqlite",50,450),n(4,"ui","Profiler UI","Flame graph, heap timeline, alloc heatmap","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["memory","profiler","leak-detection","cpp"]),
    ("Thread Debugger","Multi-thread debugger with race condition and deadlock detection","Thread debugging: thread states, lock ownership, wait graphs, deadlock detection, data race detection",
     [n(0,"input","Debug Config","Thread/process attach, breakpoints, watches","ts",50,50),n(1,"logic","Thread Tracker","State machine, context switch log","cpp",250,50),n(2,"logic","Race Detector","Happens-before tracking, lock-set analysis","cpp",250,250),n(3,"database","Debug Data","Thread states, lock owners, memory access log","sqlite",50,450),n(4,"ui","Debugger UI","Thread timeline, lock graph, var inspector","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["threads","debugger","race-detection","concurrency"]),
    ("Compiler Explorer","Educational compiler: lexer, parser, AST, IR, and x86 code generation","Interactive showing each compiler stage: tokens, AST, semantic analysis, IR, assembly output",
     [n(0,"input","Source Editor","Code input with syntax highlighting, examples","ts",50,50),n(1,"logic","Lexer & Parser","Regex DFA lexer, recursive descent parser","py",250,50),n(2,"logic","Semantic Analyzer","Type checking, symbol table, scope resolution","py",250,250),n(3,"database","Compilation Store","Tokens, AST, symbol table, IR, assembly","ts",50,450),n(4,"ui","Pipeline View","Tabbed: tokens/AST/IR/assembly with highlights","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["compiler","lexer","parser","ast","education"]),
    ("Bytecode VM","Stack-based bytecode virtual machine with debugger and memory viewer","Custom VM: fetch-decode-execute, operand stack, locals, debugger, disassembler",
     [n(0,"input","Program Loader","Load .bytecode, ASM-like syntax, examples","ts",50,50),n(1,"logic","Bytecode Engine","FDX loop, operand stack, local vars, control","cpp",250,50),n(2,"logic","Debugger","Single-step, breakpoint, watch, stack trace","ts",250,250),n(3,"database","VM State","Instruction mem, stack, call frames, heap","ts",50,450),n(4,"ui","VM Viewer","Code highlight, stack display, heap view","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["vm","bytecode","interpreter","compiler"]),
    ("Serialization Bench","Serialize format benchmark: protobuf, JSON, MessagePack, CBOR, FlatBuffers","Perf comparison: throughput, size, CPU cycles for protobuf, JSON, MsgPack, CBOR, FlatBuffers",
     [n(0,"input","Bench Config","Select formats, schema complexity, payload sizes","ts",50,50),n(1,"logic","Serialize Engine","Encode/decode for protobuf, JSON, etc.","cpp",250,50),n(2,"logic","Metrics Collector","Throughput, size, CPU cycles, alloc count","cpp",250,250),n(3,"database","Results Store","Bench results per format/size/schema","sqlite",50,450),n(4,"ui","Comparison Charts","Bar/line: size, speed, memory, multi-metric","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["serialization","protobuf","json","benchmark"]),
    ("Perf Analyzer","Statistical profiler with sampling, call graph, and flame graph generation","Perf profiling: timer sampling, trace capture, call graph, hotspot detection, flame graph",
     [n(0,"input","Profiling Target","Select process, mode (sampling/tracing), duration","ts",50,50),n(1,"logic","Sampling Engine","SIGPROF/hw event sampling, stack unwind","cpp",250,50),n(2,"logic","Call Graph Builder","Stack aggregation, call graph, hot paths","cpp",250,250),n(3,"database","Profile Data","Sample stacks, call graph, symbols, source map","sqlite",50,450),n(4,"ui","Flame Graph","Interactive flame graph, call tree, source","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["profiling","performance","flame-graph","optimization"]),
    ("Linker Lab","ELF linker: symbol resolution, relocation, and loading visualization","Educational ELF linker: symbol table resolution, relocation processing, section merging, runtime loading",
     [n(0,"input","Object Files","Load .o/.so, view ELF sections/symbols/relocs","ts",50,50),n(1,"logic","Symbol Resolution","Symbol lookup, strong/weak/global rules","cpp",250,50),n(2,"logic","Relocation Engine","Reloc processing: GOT, PLT, R_X86_64 types","cpp",250,250),n(3,"database","ELF Store","Sections, symbols, relocs, resolved addrs","binary",50,450),n(4,"ui","Linker View","Section diagram, symbol table, mem map","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["linker","elf","loader","binary"]),
    ("Signal Lab","Unix signal handling sandbox: handler install, mask, and delivery flow","Interactive: sigaction, signal masks, handler invocation, signal-safe functions, delivery flow",
     [n(0,"input","Signal Config","Select signal, handler, flags","ts",50,50),n(1,"logic","Signal Manager","sigaction, mask mgmt, pending tracking","cpp",250,50),n(2,"logic","Signal Flow","Signal generation, delivery simulation","cpp",250,250),n(3,"database","Signal Data","Configs, delivery history, pending/blocked","ts",50,450),n(4,"ui","Signal Viewer","Signal table, mask display, timeline","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["signals","unix","interrupts","low-level"]),
    ("FD Explorer","Process file descriptor explorer: files, sockets, pipes, epoll","Explore any process's FDs: regular files, sockets, pipes, epoll fds, seek pos, flags",
     [n(0,"input","Process Picker","Select by name/PID, auto-refresh, FD type filter","ts",50,50),n(1,"logic","ProcFS Parser","Read /proc/[pid]/fd, resolve symlinks","cpp",250,50),n(2,"logic","Socket Inspector","TCP state, peer addr, buffer sizes","cpp",250,250),n(3,"database","FD Cache","Process info, socket data, snapshots","sqlite",50,450),n(4,"ui","FD Browser","FD list by type, tree view, details panel","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["file-descriptor","process","procfs","linux"]),
    ("MCU Simulator","ARM Cortex-M MCU simulator with GPIO, timers, UART, and interrupts","Simulated MCU: ARM Thumb-2, GPIO, timers/PWM, NVIC, UART, SPI, I2C, ADC cycle-level",
     [n(0,"input","Peripheral Config","Pins, timer periods, interrupt priorities","ts",50,50),n(1,"logic","CPU Simulator","ARM Thumb-2 interpreter, registers, pipeline","cpp",250,50),n(2,"logic","Peripheral Models","GPIO, timer, UART, SPI, I2C, ADC models","cpp",250,250),n(3,"database","Sim State","Registers, memory, interrupt state, trace","ts",50,450),n(4,"ui","Debug Dashboard","Registers, peripherals, mem browser, scope","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["embedded","simulator","arm","mcu"]),
    ("IPC Playground","IPC demos: pipes, shared memory, msg queues, sockets with latency metrics","Interactive IPC sandbox: pipe, FIFO, shm, mq, Unix sockets, D-Bus with latency/throughput",
     [n(0,"input","IPC Config","Select type, msg size, mode (1-way/ping/broadcast)","ts",50,50),n(1,"logic","IPC Engine","pipe/fifo/shm/mq/socket create/RW","cpp",250,50),n(2,"logic","Metrics Engine","Latency, throughput, context switch count","cpp",250,250),n(3,"database","Bench Data","Results per type/size/mode, history","sqlite",50,450),n(4,"ui","IPC Dashboard","Results table, latency histogram, throughput","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["ipc","pipes","shared-memory","sockets"]),
    ("Assembly Playground","x86-64 assembly editor with live register display and single-step debug","Interactive ASM editor: syntax highlight, registers, flags, memory, single-step, syscall sim",
     [n(0,"input","ASM Editor","Assembly text editor with highlight, labels","ts",50,50),n(1,"logic","x86-64 Emulator","Instruction decode, register file, flags, mem","cpp",250,50),n(2,"logic","Call Conv Viewer","System V AMD64: reg args, stack frame, red zone","cpp",250,250),n(3,"database","Debug State","Registers, flags, mem pages, exec history","ts",50,450),n(4,"ui","Debug View","Reg/flags panel, mem hex, stack diagram","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["assembly","x86","low-level","education"]),
    ("Netlink Monitor","Linux netlink socket monitor: routing, neighbors, link events","Real-time netlink: RTNETLINK messages, routing changes, neighbor discovery, link state, IP addrs",
     [n(0,"input","Netlink Config","Select groups (route/neigh/link), dump mode","ts",50,50),n(1,"logic","Netlink Engine","NETLINK_ROUTE socket, msg parsing","cpp",250,50),n(2,"logic","Route Parser","Route attr, nexthops, multipath, metrics","cpp",250,250),n(3,"database","Netlink Store","Route table, neigh cache, link states, events","sqlite",50,450),n(4,"ui","Network View","Route table, neigh table, link list, event log","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["netlink","networking","linux","routing"]),
    ("CGroup Explorer","Linux cgroups v2: CPU/memory/IO/PID controllers and pressure monitoring","cgroups v2 explorer: create/delete, set limits, PSI monitoring, process assignment",
     [n(0,"input","CGroup Config","Create/delete cgroups, set limits, attach procs","ts",50,50),n(1,"logic","CGroup Manager","cgroupfs ops, controller tree, limit config","cpp",250,50),n(2,"logic","Pressure Monitor","PSI CPU/memory/IO pressure averages","cpp",250,250),n(3,"database","CGroup Data","Tree, controller stats, pressure history","sqlite",50,450),n(4,"ui","CGroup Dashboard","Tree view, controller stats, pressure graphs","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["cgroups","containers","linux","resource-mgmt"]),
    ("eBPF Sandbox","eBPF program loader with verifier log, maps, and kprobe attachment","eBPF dev sandbox: write/load BPF C programs, verifier log, maps, kprobes, events",
     [n(0,"input","BPF Editor","Write BPF C programs, templates (kprobe/XDP)","ts",50,50),n(1,"logic","BPF Loader","Clang->BPF, bpf() syscall, prog/map create","cpp",250,50),n(2,"logic","Verifier Viewer","Parse verifier log, instruction-level analysis","cpp",250,250),n(3,"database","BPF State","Loaded progs, map contents, event buffers","ts",50,450),n(4,"ui","BPF Dashboard","Program list, map editor, event stream","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["ebpf","bpf","kernel","tracing"]),
    ("DMA Explorer","DMA controller simulator: scatter-gather, descriptor rings, interrupts","DMA simulation: mem-to-mem/device, descriptor rings, scatter-gather, interrupt on completion",
     [n(0,"input","Transfer Config","Src/dst addrs, size, burst, descriptor mode","ts",50,50),n(1,"logic","DMA Controller","Register-level: src/dst/count/control/status","cpp",250,50),n(2,"logic","Scatter-Gather","Descriptor ring, linked-list, completion cb","cpp",250,250),n(3,"database","Transfer Store","Transfer queue, completed, descriptors","ts",50,450),n(4,"ui","DMA Viewer","Registers, descriptor ring, timeline","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["dma","hardware","memory","low-level"]),
    ("Futex Lab","Futex sync lab: wait/wake/requeue/PI, comparison with mutex/spinlock","Futex demo: futex_wait/wake/requeue, PI futexes, robust list, vs mutex/spinlock comparison",
     [n(0,"input","Futex Config","Op (wait/wake/requeue), timeout, PI, robust","ts",50,50),n(1,"logic","Futex Engine","Futex syscall, hash bucket, wait queue ops","cpp",250,50),n(2,"logic","Lock Comparison","Futex vs mutex vs spinlock: latency, fairness","cpp",250,250),n(3,"database","Bench Data","Op latency, wake efficiency, contention","sqlite",50,450),n(4,"ui","Futex Dashboard","Op log, lock comparison charts, wait queue","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["futex","synchronization","locking","linux"]),
    ("ALSA Lab","Linux ALSA PCM capture/playback, MIDI, and audio DSP effects","ALSA audio lab: PCM hw/sw params, mmap, xrun, MIDI I/O, DSP effects, latency measure",
     [n(0,"input","Audio Config","Device, sample rate, buffer size, channels","ts",50,50),n(1,"logic","ALSA Engine","PCM hw/sw params, mmap, period interrupts","cpp",250,50),n(2,"logic","DSP Processor","Volume, EQ, reverb, delay real-time","cpp",250,250),n(3,"database","Audio Store","Recordings, effect presets, device cache","ts",50,450),n(4,"ui","Audio Dashboard","Waveform, spectrum, level meters, effects","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["alsa","audio","linux","sound"]),
    ("Syscall Tracer","strace-like syscall tracer with filter, stats, and timeline view","Syscall tracing via ptrace: all syscalls, args, return values, latency stats, timeline",
     [n(0,"input","Tracer Config","Target, syscall filter, follow forks","ts",50,50),n(1,"logic","Ptrace Engine","PTRACE_SYSCALL, arg extract, ret capture","cpp",250,50),n(2,"logic","Syscall Table","Number->name, arg types, errno translate","cpp",250,250),n(3,"database","Trace Data","Syscall records, aggregated stats","sqlite",50,450),n(4,"ui","Trace Viewer","Timeline, raw list, filtered summary","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["syscall","tracing","ptrace","debugging"]),
    ("Virtual Memory Lab","Virtual memory simulator: page tables, TLB, MMU, paging, swapping","Educational VM sim: multi-level page tables, TLB LRU, page faults, swapping, addr translation",
     [n(0,"input","Memory Config","Page size, address bits, TLB size/assoc","ts",50,50),n(1,"logic","MMU Simulator","Virt->phys translation, page table walk","cpp",250,50),n(2,"logic","Page Fault Handler","Demand paging, swap, replacement (LRU/Clock)","cpp",250,250),n(3,"database","Memory State","Page tables, TLB contents, page frames","ts",50,450),n(4,"ui","Memory Viewer","Addr space map, page walk, TLB hit/miss","ts",450,250)],
     [e(0,1),e(1,2),e(2,3),e(3,4)],["virtual-memory","mmu","paging","tlb"])
]
for args in b4:
    add("05-systems-programming", *args)

# ═══════════ BATCH 5: databases ═══════════
db_names = [
    ("SQL Query Analyzer","Interactive SQL EXPLAIN, indexing advice, optimization recommendations","SQL analysis: execution plans, index suggestions, query rewrite, perf estimates"),
    ("B+Tree Visualizer","Interactive B+Tree insert/delete/search with page split/merge animations","B+Tree visualization: page splits/merges, fanout, height, leaf traversal"),
    ("Redis Playground","Redis data structures: strings, hashes, lists, sets, sorted sets with persistence","In-memory store with Redis data types, RDB/AOF persistence sim"),
    ("SQLite Inspector","SQLite .db file inspector: schema, page layout, B-tree, record format","SQLite file analyzer: schema, page browser, B-tree, WAL journal inspection"),
    ("Query Optimizer","Relational algebra, cost-based optimization, join enumeration, histograms","Query optimizer: join reordering, index selection, cost estimation"),
    ("Index Designer","Index selection advisor: workload analysis, covering indexes, maintenance","Index design: workload analysis, index recommendation, maintenance strategies"),
    ("NoSQL Comparator","Compare document/KV/graph/TS DB CRUD ops and query patterns side by side","Multi-model DB comparison: CRUD, query patterns, performance across NoSQL"),
    ("ACID Lab","Transaction isolation: dirty reads, non-repeatable reads, phantoms simulation","Transaction isolation simulator under different isolation levels"),
    ("MVCC Visualizer","Multi-version concurrency control: version chains, snapshots, vacuum","MVCC internals: version chains, snapshot visibility, compaction, conflicts"),
    ("Data Modeler","ER diagram designer with normalization to 3NF/BCNF and DDL generation","Visual data modeling: ER diagrams, normalization, SQL DDL generation"),
    ("Migration Manager","Schema migration: versioning, rollback, diff, compatibility checking","Schema migrations: versioned up/down scripts, diff, dry-run preview"),
    ("PG Dashboard","PostgreSQL monitor: queries, locks, table stats, index usage, performance","PG dashboard: active queries, lock waits, table/index stats, perf metrics"),
    ("MongoDB Aggregator","Aggregation pipeline builder: $lookup/$unwind/$group stage visualization","Visual aggregation pipeline: stage-by-stage, intermediate results view"),
    ("TSDB Viewer","Time-series DB: metric ingestion, downsampling, retention, continuous queries","TSDB: ingest, downsampling, retention policies, continuous queries, ranges"),
    ("DW Modeler","Star/snowflake schema: fact tables, dimensions, SCD types, cube design","Data warehouse modeler: fact/dim tables, SCD, cube design, OLAP"),
    ("Full-Text Search Lab","PostgreSQL/ES full-text search: tsvector, BM25, fuzzy, relevance tuning","Full-text search: tsvector/tsquery, BM25 ranking, fuzzy match, tuning"),
    ("Partition Manager","Table partitioning: range/list/hash, partition pruning, partition-wise join","Partitioning: create/manage, pruning analysis, partition-wise join planning"),
    ("Replication Monitor","DB replication: WAL position, slots, standby lag, conflict resolution","Replication monitoring: WAL lag, replication slots, conflict events"),
    ("Shard Designer","Distributed sharding: hash/range, consistent hashing, rebalance, query routing","Shard design: hash/range, consistent hashing, rebalancing, query routing"),
    ("Database Benchmark","TPC-C/TPC-H: custom workloads, concurrency scaling, latency/throughput","Benchmarking: TPC-C/TPC-H, custom workloads, concurrency, metrics")]
for n_, g_, p_ in db_names:
    add("06-databases", n_, g_, p_,
        [n(0,"input","Query/Config","SQL queries, schema design, configuration","ts",50,50),n(1,"logic","DB Engine","Query processing, storage engine sim, optimization","ts",250,50),n(2,"logic","Analysis","Perf analysis, index advice, optimization recs","ts",250,250),n(3,"database","Data Store","Schema, query history, benchmark results, config","sqlite",50,450),n(4,"ui","Results Viewer","Query results, visualization, metrics, recommendations","ts",450,250)],
        [e(0,1),e(1,2),e(2,3),e(3,4)],["database","sql","nosql","performance"])

# ═══════════ BATCH 6: math ═══════════
math_names = [
    ("Function Plotter","2D/3D function plotter with calculus derivative visualization","Plotter: parametric, polar, implicit; derivative, normals, intersections"),
    ("Linear Algebra Lab","Matrix operations, LU/QR/SVD decompositions, eigenvalues, vector spaces","LA tool: matrix multiply, LU/QR/SVD, eigenvalues, vector space viz"),
    ("Calculus Explorer","Derivative, integral, limit calculator with step-by-step solutions","Calculus: derivative rules, integration techniques, limits, series expansion"),
    ("Statistics Toolbox","Descriptive stats, distributions, t-tests, ANOVA, regression","Stats: histograms, PDF/CDF, t-tests, ANOVA, linear/logistic regression"),
    ("3D Surface Plotter","Interactive 3D surface/contour plotter with rotation and colormap","3D plots: surface/contour, colormaps, wireframe/solid, equation input"),
    ("Number Theory Lab","Prime testing, factorization, GCD, modular arithmetic explorer","Number theory: Miller-Rabin, AKS, Pollard rho, modular arithmetic"),
    ("Vector Field Viz","2D/3D vector fields: divergence, curl, gradient, flow lines","Vector fields: field lines, div/curl, gradient fields, flow animation"),
    ("Fourier Studio","FFT/IFFT: time/frequency domains, filtering, spectrograms","Fourier: time/freq domains, FFT, low/high/bandpass filtering, spectrogram"),
    ("Probability Sim","Monte Carlo: distributions, random walks, CLT, law of large numbers","Probability: PDF/CDF, random sampling, CLT, LLN, random walks"),
    ("Optimization Viz","Linear programming: simplex, gradient descent, Lagrange multipliers","Optimization: simplex, gradient descent, Lagrange, KKT conditions"),
    ("ODE Solver","ODE: Runge-Kutta, Euler, adaptive step, phase portraits, slope fields","ODE solving: RK4, Euler, adaptive step, phase portraits, slope fields"),
    ("Graph Theory Lab","Graph properties, coloring, max flow, bipartite matching","Graph theory: adjacency matrix, clique, chromatic number, max flow"),
    ("Complex Plotter","Complex functions: domain coloring, conformal mapping, Riemann surfaces","Complex analysis: domain coloring, conformal maps, Riemann surfaces"),
    ("Numerical Methods","Root finding, interpolation, numerical integration, approximation","Numerical: Newton/bisection/secant, Lagrange/spline, numerical integration"),
    ("Financial Calc","NPV, IRR, amortization, compound interest, Black-Scholes","Finance: TVM, amortization, bond pricing, Black-Scholes option pricing"),
    ("Algebra Tutor","Fraction math, equation solving, polynomials, factoring step-by-step","Algebra: fraction ops, equation steps, polynomial ops, factoring"),
    ("Set Theory Viz","Venn diagrams, set ops, cardinality, power sets","Set theory: Venn, union/intersection/complement, cardinality, power sets"),
    ("Geometry Play","Interactive geometry: points, lines, circles, polygons, transforms","Geometry: compass/straightedge, transform (translate/rotate/reflect)"),
    ("Turing Machine","Turing machine: tape, states, rules, execution trace, examples","TM simulator: custom rules, step-by-step, tape viz, example programs"),
    ("Chaos & Fractals","Mandelbrot/Julia, L-systems, Barnsley fern, IFS fractals","Fractals: Mandelbrot/Julia zoom, L-system trees, IFS, color mapping")]
for n_, g_, p_ in math_names:
    add("13-math", n_, g_, p_,
        [n(0,"input","Math Input","Equation/parameter input, data, config","ts",50,50),n(1,"logic","Math Engine","Math computation, algorithms, numerical methods","ts",250,50),n(2,"logic","Analysis","Result analysis, error computation, optimization","ts",250,250),n(3,"database","Data Storage","Computation history, results cache, presets","sqlite",50,450),n(4,"ui","Visualization","Graphs, charts, 3D, results display","ts",450,250)],
        [e(0,1),e(1,2),e(2,3),e(3,4)],["mathematics","visualization","education","science"])

# ═══════════ BATCH 7: specialized-computing ═══════════
spec_names = [
    ("Quantum Gate Sim","Quantum gates: single/qubit, Bell states, Grover's, circuit visualization","Quantum sim: qubit gates, Bell states, Grover's algorithm, circuits"),
    ("DNA Sequence Tool","DNA/RNA: Needleman-Wunsch, Smith-Waterman, BLAST-like, variant calling","Bioinformatics: sequence alignment, BLAST search, mutation detection"),
    ("Molecular Viewer","3D molecular viewer: PDB loading, ball-and-stick, spacefill","Molecular viz: PDB loader, ball-and-stick/spacefill, measurement"),
    ("Weather Modeler","Weather data: GRIB parsing, isobars, temperature maps, fronts","Meteorology: GRIB parsing, contour maps, temperature gradients"),
    ("Optimization Solver","LP/MILP: simplex, branch-and-bound, constraint propagation","OR solver: simplex, B&B, constraint propagation, solution space viz"),
    ("Computational Geometry","Convex hull, Delaunay, Voronoi, mesh generation","CGAL: convex hull (Graham/Quickhull), Delaunay triangulation, Voronoi"),
    ("Protein Folder","Protein BLAST, homology modeling, secondary structure prediction","Bioinformatics: BLAST search, homology modeling, structure prediction"),
    ("Climate Viewer","Climate data: NetCDF/HDF5, temperature/precipitation maps, animation","Climate: NetCDF reader, temperature maps, time-series animation"),
    ("Constraint Solver","CSP: forward checking, AC-3, backjumping, constraint graph","CSP solver: backtracking, AC-3 arc consistency, constraint graphs"),
    ("Fluid Dynamics","Navier-Stokes 2D: velocity/pressure fields, smoke simulation","Fluid sim: stable fluids, velocity field, pressure, vorticity, smoke"),
    ("Circuit Simulator","SPICE-like: RLC, diodes, transistors, op-amps, DC/AC/transient","Circuit sim: RLC, diode, transistor, op-amp, waveform analysis"),
    ("Orbit Simulator","N-body gravity: Keplerian elements, Lagrange points, trajectories","Orbital: N-body gravity, Kepler elements, Lagrange points, trajectory"),
    ("Drug Discovery","Molecular docking: AutoDock-like, binding affinity, interactions","Drug discovery: docking simulation, binding scoring, interaction viz"),
    ("FEM Lab","FEM PDE solver: mesh generation, assembly, solution visualization","FEM: mesh generation, element assembly, PDE solver, field viz"),
    ("Signal Processing","FIR/IIR filters, FFT, wavelets, adaptive filtering, noise reduction","DSP: filter design, spectral analysis, wavelet decomposition, denoising"),
    ("Game Theory Lab","Nash equilibrium, prisoners dilemma, auction theory, payoff matrices","Game theory: Nash (pure/mixed), iterated PD, auction simulations"),
    ("Image Processing","Convolution, morphology, edge detection (Canny/Sobel), segmentation","CV: convolution filters, morphological ops, edge detection, segmentation"),
    ("Neural Net Lab","NN from scratch: forward/backward, gradients, decision boundaries","NN builder: forward/backward pass, gradient descent, activation functions"),
    ("Crypto Lab","AES/ChaCha20, RSA/ECC, SHA-256, TLS handshake, cryptanalysis","Crypto: symmetric/asymmetric, hashing, TLS handshake, attacks"),
    ("Robotics Sim","Robot kinematics: DH params, RRT path planning, sensor noise","Robotics: forward/inverse kinematics, RRT planning, sensor models")]
for n_, g_, p_ in spec_names:
    add("20-specialized-computing", n_, g_, p_,
        [n(0,"input","Domain Input","Domain parameters, data loading, config","ts",50,50),n(1,"logic","Core Algorithm","Domain-specific algorithm","ts,py",250,50),n(2,"logic","Analysis","Analysis, validation, error computation","ts",250,250),n(3,"database","Data Store","Simulation data, results, reference","sqlite",50,450),n(4,"ui","Visualization","3D, plots, maps, animations","ts",450,250)],
        [e(0,1),e(1,2),e(2,3),e(3,4)],["specialized","computation","science","simulation"])

# ═══════════ BATCH 8: data-engineering ═══════════
de_names = [
    ("ETL Pipeline Builder","Visual ETL: extract, transform, load stages with data preview","ETL designer: drag-and-drop stages, transforms, scheduled execution"),
    ("Data Quality Dashboard","Data profiling, validation rules, duplicate/outlier detection, scoring","DQ: column profiling, schema validation, duplicate detection, scoring"),
    ("Stream Processor","Real-time streams: Kafka topics, window ops, watermarks, event time","Stream processing: topic/subscribe, windows, watermarks, event time"),
    ("Data Lineage Explorer","Column-level provenance, transformation graph, impact analysis","Lineage: column provenance, transform graph, data flow, impact analysis"),
    ("Schema Registry","Schema versioning, compatibility (backward/forward/full), evolution","Schema registry: Avro/Protobuf/JSON, compatibility, evolution tracking"),
    ("Data Catalog","Data asset search, business glossary, metadata, usage analytics","Catalog: asset search, business glossary, technical metadata, usage stats"),
    ("Workflow Scheduler","DAG scheduler: task dependencies, retries, monitoring, execution","Scheduler: DAG definition, dependencies, retry logic, execution monitor"),
    ("DW Builder","Automated DW: dimensional model, ETL mapping, index recommendation","DW builder: dimensional model, ETL mapping, index optimization"),
    ("CDC Pipeline","Change data capture: WAL/trigger, event serialization, sink connectors","CDC: WAL/trigger capture, Avro/JSON serialization, sink connectors"),
    ("Data Masking","PII detection: regex/NER, redaction, tokenization, k-anonymity","Privacy: PII detection, masking techniques, k-anonymity, differential privacy"),
    ("Data Lake Explorer","Lake files: Parquet/ORC/Avro inspection, schema inference, SQL query","Data lake: file format viewer, schema inference, partition layout, SQL"),
    ("Batch Processor","Batch processing: chunk-oriented, partitioning, retry, checkpoint","Batch: chunk processing, partitioning, skip/retry, checkpoint/restart"),
    ("Feature Store","ML features: definitions, point-in-time joins, online/offline serving","Feature store: point-in-time correct joins, online/offline serving"),
    ("Pipeline Monitor","Monitoring: task latency, data freshness, SLAs, alerting","Pipeline monitoring: metrics, SLA tracking, alert rules, incidents"),
    ("Data Compaction","Compaction: size/interval strategies, snappy/zstd/gzip, statistics","File compaction: size/interval strategies, compression, statistics"),
    ("Schema Migrator","Migration: schema diff, compatibility, auto-migration, dry-run","Schema migration: diff generation, compatibility, auto-migrate, dry-run"),
    ("Query Federation","Cross-DB federation: pushdown, join across sources, cost-based routing","Query federation: heterogeneous sources, predicate pushdown, join"),
    ("Data Sampling","Sampling: simple random, stratified, reservoir, cluster, bias detection","Sampling: strategies, sample size, bias detection, representativeness"),
    ("Columnar Analytics","Vectorized execution: dict/RLE encoding, SIMD, late materialization","Columnar engine: dictionary/RLE encoding, vectorized eval, late materializaton"),
    ("Data Version Control","Data versioning: git-like commit/diff/branch for datasets, experiments","DVC: dataset versioning, experiment tracking, data registry, lineage")]
for n_, g_, p_ in de_names:
    add("27-data-engineering", n_, g_, p_,
        [n(0,"input","Pipeline Config","Source/target selection, scheduling, config","ts",50,50),n(1,"logic","Data Processor","Transformation, validation, processing","py",250,50),n(2,"logic","Scheduler","Workflow orchestration, dependencies, execution","py",250,250),n(3,"database","Data Store","Pipeline metadata, execution logs, catalog","sqlite",50,450),n(4,"ui","Dashboard","Pipeline DAG, execution status, metrics","ts",450,250)],
        [e(0,1),e(1,2),e(2,3),e(3,4)],["data-engineering","etl","pipeline","data-quality"])

# ═══════════ BATCH 9: devops-sre ═══════════
devops_names = [
    ("CI/CD Builder","Visual CI/CD: stages, parallel steps, matrix builds, deployment","Pipeline designer: pipeline generation, caching, artifacts, deploy"),
    ("Docker Compose Lab","Multi-service compose: network, volumes, health checks, config","Container designer: multi-service, network/volume, health checks"),
    ("K8s Designer","K8s resources: Deployments, Services, ConfigMaps, PVCs, validation","K8s designer: form-based config, YAML generation, validation"),
    ("Monitoring Dash","PromQL query builder, graphs, alert rules, on-call schedule","Monitoring: metric explorer, PromQL builder, graph panels, alerts"),
    ("Log Aggregator","Log collection: parsing (grok/regex), search, anomaly detection","Log aggregation: multi-source, parsing, full-text search, anomalies"),
    ("Terraform Viz","Terraform plan: resource graph, dependency view, plan diff","Terraform viewer: dependency graph, diff viz, resource attributes"),
    ("Alert Manager","Alerting: dedup, grouping, inhibition, silencing, escalation","Alert manager: deduplication, grouping, silencing, escalation policies"),
    ("Incident Response","Incidents: severity, runbooks, timeline, postmortems","Incident management: classification, runbook automation, postmortems"),
    ("Service Mesh","Istio/Linkerd: service graph, traffic metrics, mTLS, circuit breakers","Service mesh: service graph, traffic (HTTP/gRPC), mTLS, retries"),
    ("Chaos Lab","Chaos experiments: fault injection, blast radius, hypothesis testing","Chaos engineering: pod kill, network delay, CPU stress, experiments"),
    ("Cost Explorer","Cloud costs: resource attribution, savings plans, budgets, alerts","Multi-cloud cost: resource attribution, savings recommendations, budgets"),
    ("Secret Manager","Vault: secrets, rotation, policies, access audit","Secret management: encrypted storage, dynamic secrets, rotation, audit"),
    ("SLO Dashboard","SLOs: SLI definition, error budgets, burn rate alerts, scorecards","SLO management: SLI definition, budget calc, burn rate alerts"),
    ("Config Sync","GitOps: drift detection, auto-remediation, sync status","GitOps sync: Git watching, drift detection, auto-remediation"),
    ("Capacity Planner","Capacity: trends, forecasting (linear/exponential), what-if","Capacity planning: utilization trends, growth forecasting, what-if"),
    ("Canary Deployer","Canary: traffic splitting, metrics comparison, auto-rollback","Canary: traffic shifting, metrics compare (latency/errors), rollback"),
    ("Compliance Scanner","CIS benchmarks: custom policies (OPA/Rego), remediation, reports","Compliance: CIS checks, OPA policy engine, remediation suggestions"),
    ("Runbook Automation","Runbooks: step library, approvals, error handling, execution history","Runbook automation: step library, manual gates, error handling"),
    ("Image Scanner","Container vuln scan: CVE, SBOM (SPDX/CycloneDX), policies","Container security: CVE scanning, SBOM generation, policy enforcement"),
    ("Backup & DR","Backup/DR: RTO/RPO, replication, recovery drills, compliance","Backup/DR: RTO/RPO targets, replication, recovery testing, reports")]
for n_, g_, p_ in devops_names:
    add("33-devops-sre-tooling", n_, g_, p_,
        [n(0,"input","Config Input","Infra config, alert settings, pipeline definition","ts",50,50),n(1,"logic","Orchestration","Workflow, deployment logic, monitoring algos","ts",250,50),n(2,"logic","Analysis","Metrics analysis, compliance, cost calc","ts",250,250),n(3,"database","State Store","Infra state, metrics history, config, audit","sqlite",50,450),n(4,"ui","Ops Dashboard","Dashboards, pipeline views, cost charts","ts",450,250)],
        [e(0,1),e(1,2),e(2,3),e(3,4)],["devops","sre","monitoring","ci-cd"])

# ═══════════ BATCH 10: search-recs ═══════════
search_names = [
    ("Search Engine Sim","Mini search: crawling, inverted index, BM25, query expansion","Educational search: web crawl, inverted index, BM25, snippets"),
    ("ES Dashboard","Elasticsearch: cluster health, index mapping, query perf, shards","ES dashboard: cluster health, mapping viewer, query analysis"),
    ("Vector Search Lab","Vector search: embeddings, HNSW/IVF, hybrid BM25+vector, recall","Vector search: HNSW/IVF indexing, hybrid search, recall benchmarking"),
    ("Recommender Studio","Recs: collaborative filtering (ALS/NCF), content-based, hybrid","RS builder: CF, content-based, hybrid, offline evaluation"),
    ("Personalization","Segmentation: multi-armed bandits, contextual, A/B testing","Personalization: user segments, bandit algorithms, experiment analysis"),
    ("Feature Platform","Feature engineering: definitions, transforms, online/offline serving","Feature platform: definitions, transformations, serving, validation"),
    ("Search Relevance","Relevance: NDCG/MAP/MRR, interleaving, pairwise evaluation","Search relevance: judged queries, ranking metrics, interleaving eval"),
    ("Query Understanding","Query parsing, intent classification, NER, spelling correction","Query understanding: tokenization, intent, entity extraction, expansion"),
    ("Learning to Rank","LTR: feature extraction, LambdaMART, GBT, model evaluation","Learning-to-rank: features, LambdaMART, evaluation, online serving"),
    ("Content Categorizer","Classification: hierarchical taxonomy, CNN/BERT, active learning","Doc categorization: taxonomy, text classification, active learning"),
    ("Semantic Search","Semantic: bi-encoder, cross-encoder reranking, ColBERT, dense retrieval","Semantic search: bi-encoder embed, cross-encoder reranking"),
    ("Real-time Persnlzr","Real-time: event stream, user profiles, instant recommendations","Real-time personalization: stream processing, instant feature computation"),
    ("Search Analytics","Analytics: CTR, session analysis, zero-result rate, funnel","Search analytics: click tracking, session analysis, funnel analysis"),
    ("Image Search","CLIP: text-to-image, image-to-image search with vector indexing","Visual search: CLIP embeddings, text/image search, vector indexing"),
    ("Feed Ranking","Feed: candidate gen, CTR prediction, diversity, fatigue penalties","Feed ranking: engagement prediction, diversity mixing, real-time"),
    ("Autocomplete","Autocomplete: trie prefix search, frequency ranking, personalization","Autocomplete: trie, frequency ranking, user personalization, typo tolerance"),
    ("Market Basket","Market basket: Apriori/FP-Growth, association rules, lift/confidence","Market basket: frequent itemset mining, association rules, recommendations"),
    ("Content Similarity","Similarity: TF-IDF cosine, LSA, NMF, document clustering","Content similarity: TF-IDF, LSA topic modeling, document clustering"),
    ("ML Serving","Model serving: REST/gRPC, batch inference, prediction caching","ML serving: model registry, REST/gRPC, batch inference, monitoring"),
    ("Recs Evaluation","Eval: offline metrics, counterfactual estimation, interleaving","RecSys eval: precision/recall/NDCG, counterfactual, interleaving")]
for n_, g_, p_ in search_names:
    add("36-search-recs-personalization", n_, g_, p_,
        [n(0,"input","Search/Recs Config","Query input, config, data source selection","ts",50,50),n(1,"logic","Search Engine","Indexing, retrieval, ranking, personalization","py",250,50),n(2,"logic","Evaluation","Relevance eval, A/B testing, metrics","py",250,250),n(3,"database","Index & Data","Search index, user profiles, interactions","sqlite",50,450),n(4,"ui","Results Display","Search results, recommendations, analytics","ts",450,250)],
        [e(0,1),e(1,2),e(2,3),e(3,4)],["search","recommendations","personalization","ranking"])

# ═══════════ WRITE ALL ═══════════
existing.extend(all_created)
with open(DESIGNS_PATH, 'w') as f:
    json.dump(existing, f, indent=2)

# Write index files for batches that need them
cats = ["03-desktop-apps","05-systems-programming","06-databases","13-math","20-specialized-computing","27-data-engineering","33-devops-sre-tooling","36-search-recs-personalization"]
for c in cats:
    bdir = os.path.join(BIBLE_BASE, c)
    idx = os.path.join(bdir, "00-index.md")
    if not os.path.exists(idx):
        files = sorted([f for f in os.listdir(bdir) if f.endswith('.md') and f != '00-index.md'])
        with open(idx, 'w') as f:
            f.write(f"# 🏗️ Batch Designs: {c}\n\n| # | Name |\n|---|------|\n")
            for i, fn in enumerate(files):
                name = fn[3:-3].replace('-',' ').title()
                f.write(f"| {i+1:2d} | [{name}]({fn}) |\n")

print(f"✅ ALL COMPLETE!")
print(f"   New designs created: {len(all_created)}")
b_count = sum(1 for x in all_created if x['id'].startswith('design_03'))
sys_count = sum(1 for x in all_created if x['id'].startswith('design_05'))
db_count = sum(1 for x in all_created if x['id'].startswith('design_06'))
math_count = sum(1 for x in all_created if x['id'].startswith('design_13'))
spec_count = sum(1 for x in all_created if x['id'].startswith('design_20'))
de_count = sum(1 for x in all_created if x['id'].startswith('design_27'))
devops_count = sum(1 for x in all_created if x['id'].startswith('design_33'))
search_count = sum(1 for x in all_created if x['id'].startswith('design_36'))
print(f"   Batch 3 (desktop-apps): {b_count}")
print(f"   Batch 4 (systems): {sys_count}")
print(f"   Batch 5 (databases): {db_count}")
print(f"   Batch 6 (math): {math_count}")
print(f"   Batch 7 (specialized): {spec_count}")
print(f"   Batch 8 (data-eng): {de_count}")
print(f"   Batch 9 (devops): {devops_count}")
print(f"   Batch 10 (search): {search_count}")
print(f"   Grand total in designs.json: {len(existing)}")
