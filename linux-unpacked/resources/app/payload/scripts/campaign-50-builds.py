#!/usr/bin/env python3
"""
VACA 50-Build Campaign Runner
=============================
Runs 50 REAL builds through VACA's live pipeline (per-file scaffold):
  - 10 simple, 15 medium, 25 complex = 50 total
  - Each spec is detailed (goal, purpose, nodes with descriptions)
  - Pipeline: POST /api/projects → PUT nodes/edges → POST /api/export/:id/per-file-scaffold
  - Output: full project directory under backend/exports/campaign50/<slug>/
  - Records results to data/campaign50-manifest.json (resumable, idempotent)

Usage:
  python3 scripts/campaign-50-builds.py --batch simple
  python3 scripts/campaign-50-builds.py --batch medium
  python3 scripts/campaign-50-builds.py --batch complex
  python3 scripts/campaign-50-builds.py --batch all --only N  # resume single build
"""

import json, os, sys, time, re, urllib.request, urllib.error, argparse
from datetime import datetime

ARCHITECT_API = "http://localhost:3001"
MANIFEST = "data/campaign50-manifest.json"
OUT_BASE = "backend/exports/campaign50"

NOW = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

# ─────────────────────────────────────────────────────────────────────────────
# Specs: 10 simple, 15 medium, 25 complex
# Each: name, goal (detailed), purpose, tags, nodes [{label,type,description,language}]
# ─────────────────────────────────────────────────────────────────────────────

def mk(label, type_, desc, lang="typescript"):
    return {"label": label, "type": type_, "description": desc, "language": lang}

SIMPLE = [
    {
        "name": "Countdown Timer",
        "goal": "A countdown timer with presets, pause/resume, and a completion alarm",
        "purpose": "Lets users pick a duration (1/5/10/25 min), start/pause/reset, and plays a beep when time runs out. Shows remaining time big and clear with a progress ring.",
        "tags": ["timer", "utility", "desktop"],
        "nodes": [
            mk("Timer Input", "input", "Duration presets (1m/5m/10m/25m) and custom minutes input"),
            mk("Countdown Engine", "logic", "Tick loop decrementing remaining seconds, pause/resume, reset, zero detection"),
            mk("State Store", "database", "Current duration, remaining time, running flag, last mode"),
            mk("Alarm Handler", "logic", "Web Audio beep sequence + visual flash on completion"),
            mk("Timer UI", "ui", "Big time display, progress ring, start/pause/reset buttons, preset chips"),
        ],
    },
    {
        "name": "Todo List",
        "goal": "A todo list with add, complete, delete, filter, and localStorage persistence",
        "purpose": "Manage daily tasks: add with Enter, toggle done, delete, filter all/active/completed, count remaining. Persists to localStorage.",
        "tags": ["todo", "productivity", "desktop"],
        "nodes": [
            mk("Task Input", "input", "Text field to add a new task with Enter key submit"),
            mk("Task Manager", "logic", "Add/complete/delete operations with id generation and validation"),
            mk("Task Store", "database", "In-memory task array synced to localStorage on every change"),
            mk("Filter Engine", "logic", "all/active/completed filtering with remaining-count computation"),
            mk("Task UI", "ui", "Input row, task list with checkboxes, delete buttons, filter tabs, counter"),
        ],
    },
    {
        "name": "Unit Converter",
        "goal": "Length/temperature/weight converter with live bidirectional conversion",
        "purpose": "Convert between units (m/ft, C/F/K, kg/lb) with instant results as you type, swap button to flip direction, and a units reference table.",
        "tags": ["converter", "utility", "desktop"],
        "nodes": [
            mk("Category Picker", "input", "Choose category (length/temperature/weight) and units"),
            mk("Conversion Engine", "logic", "Formula map per category with precise conversion math"),
            mk("History Store", "database", "Last 10 conversions with timestamps"),
            mk("Swap Handler", "logic", "Swap from/to units and re-run conversion"),
            mk("Converter UI", "ui", "Category tabs, two unit dropdowns, live input/output, swap button, history list"),
        ],
    },
    {
        "name": "Random Quote Generator",
        "goal": "Random quote generator with categories, copy, and tweet buttons",
        "purpose": "Shows a random quote with author from a curated collection, category filter, copy-to-clipboard, tweet intent link, and keyboard shortcut (Space) for new quote.",
        "tags": ["quotes", "inspiration", "desktop"],
        "nodes": [
            mk("Quote Source", "database", "Curated quote array with authors and categories"),
            mk("Picker Engine", "logic", "Random index selection avoiding immediate repeats"),
            mk("Category Filter", "logic", "Filter quote pool by selected category"),
            mk("Share Actions", "logic", "Copy to clipboard and Twitter intent URL builder"),
            mk("Quote UI", "ui", "Quote card, author, category chips, new-quote button, copy/tweet buttons"),
        ],
    },
    {
        "name": "Color Palette Generator",
        "goal": "Generate harmonious color palettes with hex preview and copy",
        "purpose": "Generate 5-color palettes from random or scheme-based seeds (analogous/complementary/triadic), show hex codes, click to copy, regenerate button, dark/light contrast check.",
        "tags": ["color", "design", "desktop"],
        "nodes": [
            mk("Scheme Picker", "input", "Choose scheme (random/analogous/complementary/triadic) and seed hue"),
            mk("Palette Engine", "logic", "HSL math to derive 5 colors from seed per scheme"),
            mk("Palette Store", "database", "Current palette with hex values and labels"),
            mk("Copy Handler", "logic", "Clipboard copy with visual feedback"),
            mk("Palette UI", "ui", "Color swatch cards with hex, copy on click, regenerate, contrast badge"),
        ],
    },
    {
        "name": "Memory Card Game",
        "goal": "Classic memory matching card game with moves counter and timer",
        "purpose": "Flip cards to find pairs. Tracks moves and time, has difficulty levels (4x3/4x4/6x4), win screen with stats, restart, and flip animations.",
        "tags": ["game", "memory", "games"],
        "nodes": [
            mk("Game Setup", "input", "Difficulty selection and new-game trigger"),
            mk("Match Engine", "logic", "Card flip logic, pair matching, game-over detection"),
            mk("Game State", "database", "Card deck, flipped indices, matched pairs, moves, elapsed time"),
            mk("Score Tracker", "logic", "Moves/time tracking and best-score localStorage"),
            mk("Game UI", "ui", "Card grid with CSS flip animation, HUD (moves/time), win modal"),
        ],
    },
    {
        "name": "Stopwatch",
        "goal": "Precision stopwatch with lap times and millisecond display",
        "purpose": "Start/stop/reset stopwatch with 1ms resolution, lap recording with best/worst lap highlight, and elapsed time list.",
        "tags": ["stopwatch", "utility", "desktop"],
        "nodes": [
            mk("Control Buttons", "input", "Start/stop/lap/reset button handling"),
            mk("Time Engine", "logic", "RequestAnimationFrame-based elapsed computation with offset math"),
            mk("Lap Store", "database", "Lap records with timestamps and deltas"),
            mk("Lap Analyzer", "logic", "Best/worst lap detection and formatting"),
            mk("Stopwatch UI", "ui", "Monospace time display, control buttons, lap list with highlights"),
        ],
    },
    {
        "name": "Calculator",
        "goal": "Standard 4-function calculator with keyboard support and expression display",
        "purpose": "Basic calculator (add/sub/mul/div, percent, sign, clear, backspace) with expression preview line, keyboard input, and decimal handling that avoids floating-point display errors.",
        "tags": ["calculator", "utility", "desktop"],
        "nodes": [
            mk("Keypad", "input", "Digit/operator/function button events incl. keyboard mapping"),
            mk("Calc Engine", "logic", "Two-operand math with proper precedence for chain operations"),
            mk("Display State", "database", "Current input, accumulator, pending operator, expression string"),
            mk("Format Handler", "logic", "Number formatting, rounding, comma grouping, overflow guard"),
            mk("Calc UI", "ui", "Expression line, big result display, grid keypad with hover states"),
        ],
    },
    {
        "name": "Word Counter",
        "goal": "Real-time word, character, sentence, and reading-time counter for text",
        "purpose": "Analyze pasted/typed text: words, chars (with/without spaces), sentences, paragraphs, reading time (200wpm), top keywords. Live updates with nice stat cards.",
        "tags": ["writing", "utility", "desktop"],
        "nodes": [
            mk("Text Area", "input", "Multi-line text input with paste handling"),
            mk("Analysis Engine", "logic", "Tokenize into words/sentences/paragraphs, keyword frequency"),
            mk("Stats Store", "database", "Computed metrics object per analysis run"),
            mk("Read Time Calc", "logic", "Reading/speaking time estimates"),
            mk("Stats UI", "ui", "Stat card grid, text area, keyword tags, progress bars"),
        ],
    },
    {
        "name": "Simple Quiz",
        "goal": "Short quiz app with multiple-choice questions, scoring, and results screen",
        "purpose": "Answer 8 general-knowledge MCQs one at a time, immediate feedback (correct/wrong), final score screen with percentage and retry. Progress bar and question counter.",
        "tags": ["quiz", "education", "games"],
        "nodes": [
            mk("Quiz Loader", "input", "Question bank selection and start button"),
            mk("Quiz Engine", "logic", "Question sequencing, answer checking, score tally"),
            mk("Question Store", "database", "Question bank with options and correct index"),
            mk("Result Calc", "logic", "Final percentage, pass/fail threshold, grade label"),
            mk("Quiz UI", "ui", "Question card, option buttons with feedback colors, progress bar, results screen"),
        ],
    },
]

MEDIUM = [
    {
        "name": "Expense Tracker",
        "goal": "Expense tracker with categories, monthly totals, charts, and localStorage",
        "purpose": "Add/delete expenses with amount, category, date. Monthly summary, category breakdown bar chart, total balance, filter by month, export CSV. All persisted locally.",
        "tags": ["finance", "tracker", "desktop"],
        "nodes": [
            mk("Expense Form", "input", "Amount, category dropdown, date picker, description"),
            mk("Ledger Engine", "logic", "Add/delete/update expense records with validation"),
            mk("Ledger Store", "database", "Expense array with id, amount, category, date; localStorage sync"),
            mk("Aggregate Engine", "logic", "Monthly totals, category sums, running balance"),
            mk("Chart Renderer", "logic", "SVG bar/line chart generation from aggregates"),
            mk("Expense UI", "ui", "Form row, summary cards, chart, filterable list, CSV export button"),
        ],
    },
    {
        "name": "Habit Tracker",
        "goal": "Habit tracker with streaks, weekly grid, and completion stats",
        "purpose": "Define habits, mark daily completions, see 7/30-day heatmap grids, current streak and best streak per habit, weekly overview, and edit/delete habits.",
        "tags": ["habits", "self-improvement", "desktop"],
        "nodes": [
            mk("Habit Manager", "input", "Add/edit/delete habits with name and target days"),
            mk("Streak Engine", "logic", "Consecutive-day streak computation with gap handling"),
            mk("Habit Store", "database", "Habits + completion dates map, localStorage persistence"),
            mk("Heatmap Builder", "logic", "7/30-day grid generation with intensity coloring"),
            mk("Habit UI", "ui", "Habit rows with check circles, streak badges, heatmap grids"),
        ],
    },
    {
        "name": "Pomodoro Timer",
        "goal": "Pomodoro timer with work/break cycles, session counter, and statistics",
        "purpose": "25/5min work/break cycles with auto-advance toggle, session counter, long-break every 4 sessions, daily session stats, and progress circle visualization.",
        "tags": ["pomodoro", "productivity", "desktop"],
        "nodes": [
            mk("Mode Picker", "input", "Work/break mode selection and custom durations"),
            mk("Pomodoro Engine", "logic", "Cycle state machine: work→break→long break→work"),
            mk("Session Store", "database", "Session history with timestamps and durations"),
            mk("Stats Engine", "logic", "Today counts, week totals, average focus time"),
            mk("Timer UI", "ui", "Progress circle, time display, mode tabs, session counter, stats panel"),
        ],
    },
    {
        "name": "Markdown Previewer",
        "goal": "Live markdown editor with split preview, toolbar, and export",
        "purpose": "Type markdown on the left, see rendered HTML on the right in real time. Supports headings, lists, links, code blocks, tables, blockquotes. Toolbar inserts syntax, export to .md/.html.",
        "tags": ["markdown", "editor", "desktop"],
        "nodes": [
            mk("Editor Input", "input", "Textarea with markdown source + toolbar actions"),
            mk("Markdown Parser", "logic", "Custom line-based markdown→HTML converter (headings, lists, code, tables, links)"),
            mk("Doc Store", "database", "Source text, rendered HTML, autosave draft to localStorage"),
            mk("Export Handler", "logic", "Download .md and .html blob generation"),
            mk("Preview UI", "ui", "Split pane with live preview, toolbar, word count footer"),
        ],
    },
    {
        "name": "Weather Widget",
        "goal": "Weather dashboard with mock city data, 5-day forecast, and unit toggle",
        "purpose": "Pick a city, see current conditions (temp, humidity, wind), 5-day forecast cards, hourly strip, and C/F toggle. Uses bundled sample data (no external API).",
        "tags": ["weather", "dashboard", "desktop"],
        "nodes": [
            mk("City Selector", "input", "City search/filter over bundled sample dataset"),
            mk("Weather Engine", "logic", "Deterministic mock forecast generation from city seed"),
            mk("Weather Store", "database", "Sample city dataset with climate baselines"),
            mk("Unit Converter", "logic", "Celsius/Fahrenheit conversion across all temps"),
            mk("Weather UI", "ui", "Current conditions card, hourly strip, 5-day forecast, unit toggle"),
        ],
    },
    {
        "name": "Typing Speed Test",
        "goal": "Typing test measuring WPM, accuracy, and error highlighting",
        "purpose": "Type a sample passage; live WPM and accuracy tracking, per-word correctness highlighting, 30/60s modes, results screen with chart of WPM over time, retry with new passage.",
        "tags": ["typing", "education", "games"],
        "nodes": [
            mk("Test Config", "input", "Duration mode (30/60s) and passage generation"),
            mk("Input Tracker", "logic", "Keystroke capture, word boundary detection, correctness marking"),
            mk("Metric Engine", "logic", "WPM (gross/net), accuracy %, per-second sampling"),
            mk("Result Store", "database", "Per-test results and best-score history"),
            mk("Typing UI", "ui", "Passage display with live highlighting, caret, live metrics, results overlay"),
        ],
    },
    {
        "name": "Sketch Pad",
        "goal": "Drawing canvas with brushes, colors, undo/redo, and PNG export",
        "purpose": "Draw with mouse/touch on canvas: 5 brush sizes, color palette + custom picker, eraser, undo/redo history, clear, and download as PNG.",
        "tags": ["drawing", "canvas", "desktop"],
        "nodes": [
            mk("Toolbar Input", "input", "Brush size, color, eraser, tool selection events"),
            mk("Stroke Engine", "logic", "Pointer events → smooth canvas stroke drawing with line interpolation"),
            mk("History Store", "database", "Canvas snapshot stack for undo/redo (capped at 30)"),
            mk("Export Handler", "logic", "Canvas.toDataURL PNG download with filename"),
            mk("Canvas UI", "ui", "Full canvas area, floating toolbar, undo/redo/clear/export buttons"),
        ],
    },
    {
        "name": "Password Generator",
        "goal": "Secure password generator with strength meter and options",
        "purpose": "Generate random passwords with toggles (upper/lower/digits/symbols), length slider, real-time strength meter, copy button, and a history of generated passwords with 'time to crack' estimate.",
        "tags": ["security", "password", "utility"],
        "nodes": [
            mk("Options Panel", "input", "Character-set toggles and length slider"),
            mk("Generator Engine", "logic", "Cryptographically random char selection with set guarantees"),
            mk("Strength Analyzer", "logic", "Entropy calc and strength grading with crack-time estimate"),
            mk("History Store", "database", "Recent generated passwords (plaintext, capped list)"),
            mk("Generator UI", "ui", "Live password display, options, strength bar, copy, history list"),
        ],
    },
    {
        "name": "Flashcard Study App",
        "goal": "Flashcard deck builder with spaced-repetition review and stats",
        "purpose": "Create decks and cards (front/back), study mode with self-grading (again/good/easy), spaced-repetition scheduling (SM-2 style), deck progress stats, and import/export JSON.",
        "tags": ["flashcards", "study", "education"],
        "nodes": [
            mk("Deck Builder", "input", "Create/edit decks and add front/back cards"),
            mk("Review Engine", "logic", "SM-2 spaced repetition scheduling on grade"),
            mk("Card Store", "database", "Decks, cards, review state (interval, ease, due), localStorage"),
            mk("Stats Engine", "logic", "Due counts, mastered cards, streak, accuracy"),
            mk("Study UI", "ui", "Card flip view, grade buttons, deck list, progress stats"),
        ],
    },
    {
        "name": "BMI & Health Calculator",
        "goal": "BMI calculator with health category, ideal range, and simple advice",
        "purpose": "Input height/weight (metric/imperial toggle), compute BMI with category (underweight/normal/overweight/obese), show healthy weight range for height, and display simple lifestyle tips.",
        "tags": ["health", "calculator", "desktop"],
        "nodes": [
            mk("Input Form", "input", "Height/weight inputs with unit system toggle"),
            mk("BMI Engine", "logic", "BMI computation with metric/imperial handling"),
            mk("Category Map", "database", "BMI category thresholds and health advice text"),
            mk("Range Calc", "logic", "Healthy weight range for given height"),
            mk("Health UI", "ui", "Result card with category badge, range display, advice panel"),
        ],
    },
    {
        "name": "Sudoku Solver",
        "goal": "Sudoku solver with visual backtracking animation and board input",
        "purpose": "Enter a Sudoku puzzle, solve with visualized backtracking (step/instant modes), validation of entries, and 'new puzzle' button with a sample board.",
        "tags": ["sudoku", "puzzle", "games"],
        "nodes": [
            mk("Board Input", "input", "9x9 grid entry with arrow navigation and validation"),
            mk("Solver Engine", "logic", "Backtracking solver with step generator for animation"),
            mk("Board Store", "database", "Grid state, fixed-cell flags, solution cache"),
            mk("Validator", "logic", "Row/col/box conflict checks on entry"),
            mk("Solver UI", "ui", "9x9 grid, solve/step/reset buttons, status messages"),
        ],
    },
    {
        "name": "Recipe Manager",
        "goal": "Recipe manager with search, categories, and printable view",
        "purpose": "Add recipes (ingredients, steps, time, category), search/filter, view detail with servings scaling, and print-friendly view. localStorage persistence.",
        "tags": ["recipes", "lifestyle", "desktop"],
        "nodes": [
            mk("Recipe Form", "input", "Add/edit recipe: name, ingredients list, steps, time, category"),
            mk("Search Engine", "logic", "Name/ingredient/category search with fuzzy match"),
            mk("Recipe Store", "database", "Recipe collection with localStorage sync"),
            mk("Scaling Engine", "logic", "Ingredient quantity scaling by servings"),
            mk("Recipe UI", "ui", "Card grid, search bar, detail modal with steps and scale controls"),
        ],
    },
    {
        "name": "Connect Four",
        "goal": "Connect Four game vs AI with minimax difficulty levels",
        "purpose": "Drop discs into 7-column board, play vs AI (minimax with alpha-beta, 3 difficulty levels) or 2-player local. Win/draw detection, scoreboard, restart, animated disc drops.",
        "tags": ["game", "connect4", "games"],
        "nodes": [
            mk("Column Input", "input", "Column hover/click detection and legal-move check"),
            mk("Board Engine", "logic", "Disc drop physics (gravity), win/draw detection"),
            mk("AI Opponent", "logic", "Minimax with alpha-beta pruning and depth by difficulty"),
            mk("Match Store", "database", "Board state, current player, win counts"),
            mk("Game UI", "ui", "7x6 board render, hover preview, turn indicator, scoreboard"),
        ],
    },
    {
        "name": "URL Shortener (Local)",
        "goal": "Local URL shortener with code generation and click stats",
        "purpose": "Shorten URLs to short codes, copy result, click-through counter per link, list of all shortened links with delete, and daily click chart. All data in localStorage (no network).",
        "tags": ["url", "utility", "desktop"],
        "nodes": [
            mk("URL Input", "input", "URL paste field with validation"),
            mk("Code Generator", "logic", "Unique short-code generation (base62) with collision check"),
            mk("Link Store", "database", "Short links with original URL, clicks, created date"),
            mk("Stats Engine", "logic", "Click increment and per-day click aggregation for chart"),
            mk("Shortener UI", "ui", "Input row, result with copy button, link list, mini bar chart"),
        ],
    },
    {
        "name": "Music Player",
        "goal": "Music player with playlist, seek bar, and visualizer",
        "purpose": "Play bundled synthesized demo tracks (Web Audio), playlist sidebar, play/pause/next/prev, seek bar, volume, shuffle/repeat, and a canvas frequency visualizer. No external files needed.",
        "tags": ["music", "player", "desktop"],
        "nodes": [
            mk("Transport Controls", "input", "Play/pause/next/prev/shuffle/repeat events"),
            mk("Audio Engine", "logic", "Web Audio scheduling, gain, oscillator-based demo tracks"),
            mk("Playlist Store", "database", "Track metadata and playback state"),
            mk("Visualizer", "logic", "AnalyserNode → canvas bars/line rendering"),
            mk("Player UI", "ui", "Album art placeholder, track title, seek bar, controls, playlist"),
        ],
    },
]

COMPLEX = [
    {
        "name": "Kanban Board",
        "goal": "Kanban board with drag-and-drop, tags, priorities, search, and local persistence",
        "purpose": "Full project board: columns (To Do/In Progress/Done), cards with title/desc/tags/priority/due date, HTML5 drag-and-drop between columns, card search/filter, column WIP limits, and complete localStorage persistence with import/export JSON.",
        "tags": ["kanban", "productivity", "project-management"],
        "nodes": [
            mk("Board Actions", "input", "Add/edit/delete columns and cards, search input"),
            mk("Drag Engine", "logic", "HTML5 drag/drop with hover indicators and reordering"),
            mk("Board Store", "database", "Columns, cards, positions, tags; localStorage sync"),
            mk("Filter Engine", "logic", "Search by text/tag/priority, column WIP limit enforcement"),
            mk("Card Sorter", "logic", "Priority/time-based sorting within columns"),
            mk("Kanban UI", "ui", "Multi-column board, draggable cards, modals for edit, search bar"),
        ],
    },
    {
        "name": "Chat Simulator",
        "goal": "Simulated chat app with bot responses, typing indicator, and rooms",
        "purpose": "Chat with a scripted local bot across multiple rooms; message bubbles with timestamps, typing indicator, quick-reply chips, unread badges, and a command system (/help /clear /theme). Bot uses keyword-matching logic.",
        "tags": ["chat", "simulation", "desktop"],
        "nodes": [
            mk("Message Input", "input", "Message composer with Enter/Shift-Enter and commands"),
            mk("Bot Engine", "logic", "Keyword-matching reply generator with delays and personality"),
            mk("Chat Store", "database", "Messages per room, users, unread counts"),
            mk("Command Parser", "logic", "/help /clear /theme /roll command handling"),
            mk("Chat UI", "ui", "Room sidebar, message list with bubbles, typing indicator, composer"),
        ],
    },
    {
        "name": "Finance Dashboard",
        "goal": "Finance dashboard with income/expense charts, budgets, and account balances",
        "purpose": "Full finance overview: account cards with balances, income vs expense line chart (6 months), category donut chart, monthly budget bars with over-budget warnings, and transaction feed with search. Mock data + localStorage edits.",
        "tags": ["finance", "dashboard", "analytics"],
        "nodes": [
            mk("Transaction Feed", "input", "Add transaction (type, category, amount, date) with validation"),
            mk("Aggregation Engine", "logic", "Monthly income/expense totals, category sums, balances"),
            mk("Ledger Store", "database", "Accounts, transactions, budgets; localStorage"),
            mk("Budget Monitor", "logic", "Budget vs spend comparison with alert thresholds"),
            mk("Chart Builder", "logic", "SVG line/donut/bar chart generation from aggregates"),
            mk("Dashboard UI", "ui", "Account cards, KPI row, chart grid, budget list, transaction table"),
        ],
    },
    {
        "name": "Text Adventure Engine",
        "goal": "Text adventure engine with branching story, inventory, and save system",
        "purpose": "A playable branching story (15+ scenes) with choices, inventory items, health/score, death/respawn, and localStorage save/load. Includes a scene-graph data structure and parser for rich text formatting.",
        "tags": ["game", "text-adventure", "games"],
        "nodes": [
            mk("Command Input", "input", "Choice buttons and free-text verb parsing (look/take/use)"),
            mk("Scene Engine", "logic", "Scene-graph traversal, condition/flag evaluation"),
            mk("World Store", "database", "Scene definitions, player state (hp, score, inventory, flags)"),
            mk("Parser", "logic", "Free-text command tokenization and verb matching"),
            mk("Adventure UI", "ui", "Story text pane with typing effect, choices, inventory bar, status HUD"),
        ],
    },
    {
        "name": "Data Visualization Studio",
        "goal": "Chart studio supporting line/bar/pie with CSV import and styling",
        "purpose": "Import CSV (paste or file), choose chart type, map columns to axes, style colors/labels, and export SVG/PNG. Includes sample datasets and multi-series support with legend and tooltips.",
        "tags": ["charts", "visualization", "data-engineering"],
        "nodes": [
            mk("Data Import", "input", "CSV paste/file with parse and column detection"),
            mk("Chart Engine", "logic", "SVG renderers for line/bar/pie with scales and axes"),
            mk("Dataset Store", "database", "Parsed rows, column metadata, sample datasets"),
            mk("Style Mapper", "logic", "Color scheme, labels, axis config mapping"),
            mk("Export Handler", "logic", "SVG string + PNG download"),
            mk("Studio UI", "ui", "Data panel, chart canvas, type tabs, style controls, export buttons"),
        ],
    },
    {
        "name": "Task Automation Builder",
        "goal": "Visual IF-THEN automation builder with trigger/action steps and simulator",
        "purpose": "Build automation rules with a step editor (triggers: time/schedule/condition; actions: notify/transform/run), visual rule list, enable/disable toggles, and a simulator that executes rules against sample events with a log view.",
        "tags": ["automation", "builder", "utility"],
        "nodes": [
            mk("Rule Editor", "input", "Add steps with type (trigger/condition/action) and config"),
            mk("Rule Engine", "logic", "Rule evaluation over events, chained actions, loops guard"),
            mk("Rule Store", "database", "Rules, steps, enabled flags; localStorage"),
            mk("Simulator", "logic", "Sample event generator + execution trace logger"),
            mk("Automation UI", "ui", "Rule cards with step lists, toggle switches, simulator console"),
        ],
    },
    {
        "name": "Interactive Map Explorer",
        "goal": "SVG world map explorer with regions, search, and data overlays",
        "purpose": "Interactive simplified SVG map with clickable regions, region info panel (population, capital), search that flies to a region, overlay toggles (population/density heat coloring), and a quiz mode.",
        "tags": ["map", "explorer", "education"],
        "nodes": [
            mk("Map Interactions", "input", "Region click, hover, search box events"),
            mk("Region Engine", "logic", "Region selection, focus/zoom math, heat coloring"),
            mk("Region Store", "database", "Region geometries + metadata (pop, capital, area)"),
            mk("Quiz Engine", "logic", "Capital/flag-style quiz with scoring"),
            mk("Map UI", "ui", "SVG map, info panel, search, overlay toggles, quiz card"),
        ],
    },
    {
        "name": "Music Synth Workstation",
        "goal": "Web Audio synthesizer with oscillators, envelopes, and sequence recorder",
        "purpose": "Mini synth: 3 oscillators with waveform selection, ADSR envelope, keyboard (QWERTY) + on-screen keys, effects (delay/filter), and a step sequencer/recorder that plays back your performance. Save patches to localStorage.",
        "tags": ["synth", "audio", "specialized"],
        "nodes": [
            mk("Keyboard Input", "input", "QWERTY + on-screen key events with velocity"),
            mk("Synth Engine", "logic", "Web Audio oscillators, ADSR, gain routing, effects chain"),
            mk("Patch Store", "database", "Oscillator/env/fx settings presets (localStorage)"),
            mk("Sequencer", "logic", "16-step pattern recorder/player with tempo"),
            mk("Synth UI", "ui", "Keys, waveform/env sliders, fx knobs, sequencer grid, preset list"),
        ],
    },
    {
        "name": "Inventory Manager",
        "goal": "Inventory manager with barcode-style IDs, low-stock alerts, and reports",
        "purpose": "Manage inventory items (name, SKU, qty, price, category, reorder point). Live stock value calculation, low-stock alert list, search/sort, category summary report, and CSV export.",
        "tags": ["inventory", "manager", "desktop"],
        "nodes": [
            mk("Item Form", "input", "Add/edit item with SKU, qty, price, category, reorder point"),
            mk("Stock Engine", "logic", "In/out adjustments, value calc, low-stock detection"),
            mk("Inventory Store", "database", "Item records with localStorage sync"),
            mk("Report Builder", "logic", "Category totals, stock value, movement summary"),
            mk("Inventory UI", "ui", "Item table with sort/filter, alert banner, KPI cards, export"),
        ],
    },
    {
        "name": "Workout Tracker",
        "goal": "Workout tracker with exercise library, sets/reps logging, and progress charts",
        "purpose": "Log workouts (exercises, sets, reps, weight), built-in exercise library with muscle-group tags, per-exercise progress line charts, weekly volume totals, bodyweight tracking, and streak calendar.",
        "tags": ["fitness", "tracker", "health"],
        "nodes": [
            mk("Workout Logger", "input", "Add sets with exercise, reps, weight; exercise library browse"),
            mk("Volume Engine", "logic", "Set volume (reps*weight) aggregation and PR detection"),
            mk("Workout Store", "database", "Workouts, exercises, bodyweight entries; localStorage"),
            mk("Progress Builder", "logic", "Per-exercise series extraction for charts, weekly totals"),
            mk("Workout UI", "ui", "Log form, exercise list, chart panel, stats cards, calendar"),
        ],
    },
    {
        "name": "PDF & Text Toolkit",
        "goal": "Text toolkit: case converter, diff viewer, lorem generator, and hash calculator",
        "purpose": "Multi-tool workbench: case conversion (camel/snake/kebab/title), side-by-side diff with highlighted changes, lorem ipsum generator, SHA/MD5 hash calculator, and character/word stats. Tabbed interface.",
        "tags": ["text", "toolkit", "utility"],
        "nodes": [
            mk("Tool Tabs", "input", "Tool selection and per-tool input fields"),
            mk("Text Engine", "logic", "Case conversion, diff (LCS), lorem generation, hashing (SHA-256 via SubtleCrypto)"),
            mk("Tool State", "database", "Per-tool input/output state"),
            mk("Diff Renderer", "logic", "LCS diff → highlighted line/char output"),
            mk("Toolkit UI", "ui", "Tab bar, input/output panels, copy buttons, char/word stats bar"),
        ],
    },
    {
        "name": "Pathfinding Visualizer",
        "goal": "Pathfinding visualizer with A*/Dijkstra/BFS on draggable obstacle grids",
        "purpose": "Set start/end nodes, draw walls on a grid, run A*, Dijkstra, BFS, or DFS with animated search (visited frontier + final path), step counter, path length, and maze generation (recursive division).",
        "tags": ["pathfinding", "algorithms", "education"],
        "nodes": [
            mk("Grid Controls", "input", "Start/end/wall drawing modes, algorithm picker, speed slider"),
            mk("Search Engine", "logic", "A*/Dijkstra/BFS/DFS with priority queue and step capture"),
            mk("Grid Store", "database", "Grid cells, wall set, start/end, visited order, path"),
            mk("Maze Generator", "logic", "Recursive division maze on grid"),
            mk("Visualizer UI", "ui", "Grid canvas with color states, legend, stats bar, run/clear"),
        ],
    },
    {
        "name": "Budget Planner",
        "goal": "Monthly budget planner with envelope-style categories and rollover",
        "purpose": "Set monthly income and envelope budgets per category, log spending against envelopes, rollover unused funds, projected savings, alerts on over-budget, and month navigation with persistence.",
        "tags": ["budget", "finance", "planner"],
        "nodes": [
            mk("Budget Setup", "input", "Income + per-category envelope amounts"),
            mk("Envelope Engine", "logic", "Spending allocation, rollover calc, over-budget detection"),
            mk("Budget Store", "database", "Monthly budgets, transactions, rollovers; localStorage"),
            mk("Forecast Engine", "logic", "Projected savings and burn-rate analysis"),
            mk("Budget UI", "ui", "Envelope progress bars, transaction log, month nav, summary cards"),
        ],
    },
    {
        "name": "Image Editor Lite",
        "goal": "Canvas image editor: filters, crop, rotate, and export",
        "purpose": "Open/paste an image, apply filters (grayscale, sepia, invert, blur, brightness/contrast sliders), rotate/flip, crop with drag handles, zoom/pan, and download the result. Undo stack for filter operations.",
        "tags": ["image", "editor", "specialized"],
        "nodes": [
            mk("Image Loader", "input", "File input + paste + sample image"),
            mk("Filter Engine", "logic", "Pixel manipulation filters with preview apply/undo"),
            mk("Edit State", "database", "Canvas buffers, transform state, undo stack"),
            mk("Crop Tool", "logic", "Drag-rectangle crop with aspect lock"),
            mk("Editor UI", "ui", "Canvas with overlay handles, filter sidebar, toolbar, export"),
        ],
    },
    {
        "name": "Task Scheduler",
        "goal": "Task scheduler with calendar view, priorities, and notifications",
        "purpose": "Schedule tasks with date/time, priority, and duration; week calendar view with drag-to-move, timeline conflict detection, upcoming reminders list, recurring tasks (daily/weekly), and localStorage persistence.",
        "tags": ["scheduler", "calendar", "productivity"],
        "nodes": [
            mk("Task Form", "input", "Create/edit task: title, datetime, duration, priority, recurrence"),
            mk("Schedule Engine", "logic", "Time-slot allocation, conflict detection, reminders computation"),
            mk("Schedule Store", "database", "Tasks with recurrence expansion; localStorage"),
            mk("Conflict Analyzer", "logic", "Overlapping task detection and warning generation"),
            mk("Scheduler UI", "ui", "Week grid with task blocks, form modal, reminder list, priority colors"),
        ],
    },
    {
        "name": "Escape Room Puzzle",
        "goal": "Escape room game with interconnected puzzles, inventory, and timer",
        "purpose": "Multi-room escape game: clickable environment with items, 5 chained puzzles (code lock, pattern match, color sequence, math, key lock), inventory to combine items, 10-min timer, hints system, and win/lose screens.",
        "tags": ["game", "escape-room", "games"],
        "nodes": [
            mk("Room Interactions", "input", "Clickable hotspots, item pickup, puzzle trigger detection"),
            mk("Puzzle Engine", "logic", "Five puzzle solvers with validation and unlock chaining"),
            mk("Game State", "database", "Inventory, solved flags, room graph, timer"),
            mk("Hint System", "logic", "Progressive hint generation per puzzle"),
            mk("Game UI", "ui", "Room scene (CSS), inventory bar, puzzle overlays, timer HUD, hints"),
        ],
    },
    {
        "name": "Network Speed Test (Local)",
        "goal": "Local throughput test with latency/ping, jitter, and result history",
        "purpose": "Simulated speed test: ping/latency, jitter, download/upload throughput computed from synthetic benchmark tasks with progress UI, gauge dials, result history chart, and test server selector. All local computation.",
        "tags": ["network", "benchmark", "systems"],
        "nodes": [
            mk("Test Controls", "input", "Start test, server label, test duration selector"),
            mk("Benchmark Engine", "logic", "Synthetic latency/jitter/throughput computation with sampling"),
            mk("Result Store", "database", "Test results history with timestamps"),
            mk("Chart Builder", "logic", "History line chart + gauge rendering"),
            mk("Speed Test UI", "ui", "Gauge dials, live progress, history chart, result cards"),
        ],
    },
    {
        "name": "Documentation Site Builder",
        "goal": "Static documentation site builder with sidebar nav and search",
        "purpose": "Author docs in a tree of pages (markdown), live preview, auto-generated sidebar navigation, full-text search with highlighting, themes (light/dark), and export the whole site as a single HTML bundle.",
        "tags": ["docs", "builder", "desktop"],
        "nodes": [
            mk("Page Editor", "input", "Markdown editor for selected page + tree management"),
            mk("Render Engine", "logic", "Markdown→HTML + TOC generation + syntax highlight"),
            mk("Doc Store", "database", "Page tree, content, theme; localStorage"),
            mk("Search Engine", "logic", "Full-text index with substring scoring and highlight"),
            mk("Site UI", "ui", "Sidebar tree, content pane, search overlay, theme toggle, export"),
        ],
    },
    {
        "name": "Language Learning App",
        "goal": "Language learning app with vocabulary decks, exercises, and progress",
        "purpose": "Learn vocab across decks (ES/FR/DE), 4 exercise types (multiple choice, typing, listening with TTS, matching), spaced review, XP/level system with streak, pronunciation playback via SpeechSynthesis, and progress dashboard.",
        "tags": ["language", "learning", "education"],
        "nodes": [
            mk("Exercise Input", "input", "Answer capture for 4 exercise types"),
            mk("Lesson Engine", "logic", "Exercise sequencing, answer checking, XP awarding"),
            mk("Vocab Store", "database", "Decks, words, review scheduling, XP/level"),
            mk("TTS Handler", "logic", "SpeechSynthesis pronunciation with language selection"),
            mk("Learning UI", "ui", "Lesson screen, exercise cards, progress dashboard, streak display"),
        ],
    },
    {
        "name": "Smart Home Dashboard",
        "goal": "Smart home control dashboard with rooms, devices, scenes, and scheduling",
        "purpose": "Control mock devices (lights, thermostat, locks, cameras) per room, toggle devices with live state, scenes (movie/night/away) that set multiple devices, device schedules with time triggers, and energy usage estimation chart.",
        "tags": ["smart-home", "dashboard", "iot"],
        "nodes": [
            mk("Device Controls", "input", "Toggle/slider events per device type"),
            mk("Device Engine", "logic", "State management, scene application, schedule evaluation"),
            mk("Home Store", "database", "Rooms, devices, scenes, schedules; localStorage"),
            mk("Energy Estimator", "logic", "Wattage × on-time energy calc and aggregation"),
            mk("Home UI", "ui", "Room tabs, device cards, scene buttons, schedule list, energy chart"),
        ],
    },
    {
        "name": "Code Snippet Manager",
        "goal": "Code snippet manager with syntax highlighting, tags, and search",
        "purpose": "Save code snippets with language, title, tags, description; syntax highlighting via custom tokenizer (JS/PY/HTML/CSS), tag filtering, full-text search, copy button, and export all as JSON.",
        "tags": ["snippets", "developer-tools", "desktop"],
        "nodes": [
            mk("Snippet Editor", "input", "Title/language/tags/description + code textarea"),
            mk("Highlight Engine", "logic", "Custom tokenizer → HTML highlighting per language"),
            mk("Snippet Store", "database", "Snippets with metadata; localStorage"),
            mk("Search Engine", "logic", "Title/tag/content search with ranking"),
            mk("Snippet UI", "ui", "Editor form, snippet list with highlighted preview, filter chips"),
        ],
    },
    {
        "name": "Survey Builder & Analyzer",
        "goal": "Survey builder with 4 question types, preview, and results analytics",
        "purpose": "Build surveys (multiple choice, checkboxes, rating, text), preview as respondents see it, simulate responses, and view analytics: response counts, rating averages, bar charts per question, and export results CSV.",
        "tags": ["survey", "analytics", "data-engineering"],
        "nodes": [
            mk("Survey Builder", "input", "Add/edit questions with type-specific options"),
            mk("Response Engine", "logic", "Answer capture, validation, response recording"),
            mk("Survey Store", "database", "Survey definition + responses"),
            mk("Analytics Engine", "logic", "Aggregations: counts, averages, distributions"),
            mk("Survey UI", "ui", "Builder view, preview/simulate mode, results charts, export"),
        ],
    },
    {
        "name": "AI Chat Client",
        "goal": "Chat client for the local LLM server with streaming, history, and personas",
        "purpose": "Talk to the local LLM (DSpark/Ollama) via the app backend proxy with streaming token display, conversation history sidebar, system-prompt persona presets, markdown-rendered responses, token/usage stats, and session export.",
        "tags": ["ai", "chat", "llm"],
        "nodes": [
            mk("Message Composer", "input", "Prompt input, persona selector, streaming toggle"),
            mk("Chat Engine", "logic", "Messages → LLM proxy call with stream parsing"),
            mk("Conversation Store", "database", "Message history per session, personas"),
            mk("Markdown Renderer", "logic", "Response markdown→HTML rendering with code blocks"),
            mk("Chat UI", "ui", "Message list with streaming cursor, sidebar sessions, usage footer"),
        ],
    },
    {
        "name": "Traffic Simulation",
        "goal": "Traffic flow simulation with cars, lights, and congestion heatmaps",
        "purpose": "Animated grid traffic sim: car agents follow lane logic with acceleration/following rules, traffic lights with timed phases, spawn/despawn points, live stats (avg speed, wait time, throughput), congestion heatmap, and scenario presets.",
        "tags": ["simulation", "traffic", "specialized"],
        "nodes": [
            mk("Sim Controls", "input", "Play/pause/speed, car density, light cycle, scenario presets"),
            mk("Agent Engine", "logic", "Car movement: follow/accelerate/brake, intersection handling"),
            mk("Sim State", "database", "Car list, light states, road graph, counters"),
            mk("Metrics Engine", "logic", "Avg speed, queue lengths, throughput sampling, heatmap values"),
            mk("Sim UI", "ui", "Canvas road grid with animated cars and lights, stats panel, heatmap"),
        ],
    },
    {
        "name": "Project Planner",
        "goal": "Project planner with Gantt-style timeline, milestones, and resource allocation",
        "purpose": "Plan projects: tasks with start/end dates and dependencies, Gantt-style timeline rendering, milestone markers, per-person resource loading, critical-path highlighting, and progress tracking with localStorage persistence.",
        "tags": ["project-management", "planner", "gantt"],
        "nodes": [
            mk("Task Editor", "input", "Add/edit tasks: name, dates, assignee, dependency selection"),
            mk("Timeline Engine", "logic", "Date math, overlap/conflict detection, Gantt bar geometry"),
            mk("Plan Store", "database", "Tasks, milestones, assignees, dependencies; localStorage"),
            mk("Critical Path", "logic", "Dependency-graph longest-path computation and progress totals"),
            mk("Planner UI", "ui", "Gantt chart canvas, task list, milestone markers, resource bars"),
        ],
    },
]

ALL_SPECS = [("simple", s) for s in SIMPLE] + [("medium", m) for m in MEDIUM] + [("complex", c) for c in COMPLEX]
assert len(ALL_SPECS) == 50, f"expected 50 specs, got {len(ALL_SPECS)}"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline helpers
# ─────────────────────────────────────────────────────────────────────────────

def api(method, url, payload=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)[:200]}


def slugify(name):
    s = name.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def build_project_payload(spec):
    """Convert a spec into the VACA project payload (React-Flow style nodes/edges)."""
    nodes = []
    edges = []
    n = len(spec["nodes"])
    for i, nd in enumerate(spec["nodes"]):
        col = i % 3
        row = i // 3
        nodes.append({
            "id": f"node_{i}",
            "type": nd["type"],
            "position": {"x": 250 + col * 220, "y": 200 + row * 180},
            "data": {
                "label": nd["label"],
                "description": nd["description"],
                "type": nd["type"],
                "language": nd["language"],
                "status": "pending",
            },
        })
        if i > 0:
            edges.append({"source": f"node_{i-1}", "target": f"node_{i}"})
    # Add a couple of cross-edges for complex graphs
    if n >= 6:
        edges.append({"source": "node_1", "target": f"node_{n-1}"})
    if n >= 7:
        edges.append({"source": "node_2", "target": f"node_{n-2}"})
    return {
        "id": f"campaign_{slugify(spec['name'])}",
        "name": spec["name"],
        "goal": spec["goal"],
        "purpose": spec["purpose"],
        "targetOS": "linux",
        "nodes": nodes,
        "edges": edges,
        "createdAt": NOW,
        "updatedAt": NOW,
        "source": "campaign-50",
        "tags": spec["tags"],
    }


def load_manifest():
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST) as f:
                return json.load(f)
        except Exception:
            pass
    return {"builds": [], "startedAt": NOW, "completedAt": None}


def save_manifest(m):
    with open(MANIFEST, "w") as f:
        json.dump(m, f, indent=2)


def build_one(spec, tier, skip_validation=True):
    """Run one spec through VACA's pipeline, return result dict."""
    name = spec["name"]
    slug = slugify(name)
    out_dir = os.path.join(OUT_BASE, slug)
    st, proj = api("POST", f"{ARCHITECT_API}/api/projects", {"name": name, "targetOS": "linux"}, timeout=15)
    if st not in (200, 201):
        return {"name": name, "tier": tier, "slug": slug, "status": "error",
                "error": f"create failed: {proj.get('error','')} ({st})"}
    pid = proj.get("id")

    # Push the full design (nodes/edges) onto the project
    payload = build_project_payload(spec)
    st2, upd = api("PUT", f"{ARCHITECT_API}/api/projects/{pid}", {
        "name": name,
        "goal": spec["goal"],
        "purpose": spec["purpose"],
        "targetOS": "linux",
        "nodes": payload["nodes"],
        "edges": payload["edges"],
        "tags": spec["tags"],
    }, timeout=20)
    if st2 not in (200, 201):
        return {"name": name, "tier": tier, "slug": slug, "status": "error",
                "error": f"update failed: {upd.get('error','')} ({st2})", "projectId": pid}

    # Run the real per-file scaffold (LLM generates every node file)
    st3, scaf = api("POST", f"{ARCHITECT_API}/api/export/{pid}/per-file-scaffold", {
        "skipValidation": skip_validation,
        "outputDir": os.path.abspath(out_dir),
        "projectName": name,
    }, timeout=600)
    if st3 not in (200, 201) or not scaf.get("success"):
        return {"name": name, "tier": tier, "slug": slug, "status": "error",
                "error": scaf.get("error", f"scaffold failed ({st3})")[:300],
                "projectId": pid, "outputDir": out_dir}

    gen = scaf.get("generationSummary", {})
    sec = scaf.get("securityScan", {}).get("summary", {})
    result = {
        "name": name,
        "tier": tier,
        "slug": slug,
        "status": "built",
        "projectId": pid,
        "outputDir": scaf.get("outputPath", out_dir),
        "files": scaf.get("files", []),
        "totalFiles": gen.get("totalFiles", 0),
        "totalChars": gen.get("totalChars", 0),
        "validatedCount": gen.get("validatedCount", 0),
        "failedCount": gen.get("failedCount", 0),
        "security": {
            "total": sec.get("totalVulnerabilities", 0),
            "critical": sec.get("critical", 0),
            "high": sec.get("high", 0),
            "medium": sec.get("medium", 0),
            "low": sec.get("low", 0),
            "isSecure": sec.get("isSecure", True),
        },
        "builtAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    return result


def run_batch(tier, only=None, resume=True, skip_validation=True):
    m = load_manifest()
    done = {b["slug"]: b for b in m["builds"]}
    specs = {"simple": SIMPLE, "medium": MEDIUM, "complex": COMPLEX}[tier]
    print(f"\n=== Campaign batch: {tier.upper()} ({len(specs)} builds) ===")
    for spec in specs:
        slug = slugify(spec["name"])
        if resume and slug in done and done[slug]["status"] in ("built", "error"):
            print(f"  ⏭️  skip (already recorded): {spec['name']}")
            continue
        if only is not None and slug != only:
            continue
        print(f"  🔨 building: {spec['name']} ...", flush=True)
        t0 = time.time()
        r = build_one(spec, tier, skip_validation=skip_validation)
        dt = time.time() - t0
        st = "✅" if r["status"] == "built" else "❌"
        print(f"  {st} {r['name']} ({dt:.0f}s) files={r.get('totalFiles','-')} valid={r.get('validatedCount','-')} err={r.get('failedCount','-')} {r.get('error','')}")
        done[slug] = r
        # Persist the FULL updated build list on every save so a mid-run
        # crash doesn't lose completed builds (true resumability).
        m["builds"] = list(done.values())
        save_manifest(m)
    m["builds"] = list(done.values())
    m["completedAt"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    save_manifest(m)
    summary = {"simple": 0, "medium": 0, "complex": 0}
    for b in m["builds"]:
        if b["status"] == "built":
            summary[b["tier"]] = summary.get(b["tier"], 0) + 1
    print(f"\n=== Manifest now has {len(m['builds'])} builds: {summary} ===")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--batch", choices=["simple", "medium", "complex", "all"], default="all")
    p.add_argument("--only", type=str, default=None, help="slug to build only")
    p.add_argument("--no-resume", action="store_true", help="rebuild even if recorded")
    p.add_argument("--validate", action="store_true",
                   help="enable per-file sandbox validation (default: skipped — static scan is the verification layer)")
    args = p.parse_args()
    tiers = ["simple", "medium", "complex"] if args.batch == "all" else [args.batch]
    for t in tiers:
        run_batch(t, only=args.only, resume=not args.no_resume, skip_validation=not args.validate)
    print("\n🏁 Campaign batch run complete. See data/campaign50-manifest.json")
