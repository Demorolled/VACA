#!/usr/bin/env python3
"""Generate Batch 2: 20 Game designs for visual-ai-architect."""
import json, os, time

DESIGNS_PATH = "data/designs.json"
BIBLE_DIR = "bible-reference/00-app-designs/02-games"
NOW = "2026-06-19T14:00:00.000Z"

existing = []
if os.path.exists(DESIGNS_PATH):
    with open(DESIGNS_PATH) as f:
        existing = json.load(f)

def make_design(name, goal, purpose, nodes, edges, tags):
    return {
        "id": f"design_b2_{int(time.time()*1000)}_{len(existing)+len(globals().get('created', []))}",
        "name": name, "goal": goal, "purpose": purpose, "targetOS": "linux",
        "nodes": nodes, "edges": edges,
        "roadmap": f"App: {name}\nTarget OS: linux\nNodes: {len(nodes)}\nConnections: {len(edges)}",
        "createdAt": NOW, "updatedAt": NOW, "source": "local", "tags": tags
    }

def n(id, type_, label, desc, lang, x, y):
    return {"id": f"saved_{id}", "type": type_, "label": label, "description": desc, "language": lang, "position": {"x": x, "y": y}}

def e(src, tgt):
    return {"source": f"node_{src}", "target": f"node_{tgt}"}

created = []

# 1. Pong Game
created.append(make_design("Pong Game",
    "Classic two-player Pong with paddle physics, ball collision, and score tracking",
    "A complete Pong implementation with paddle movement, ball bouncing physics, collision detection, score tracking, and AI opponent mode",
    [n(0,"input","Paddle Controller","Keyboard input for paddle up/down movement, AI toggle","typescript",50,50),
     n(1,"logic","Physics Engine","Ball velocity, paddle collision response, angle reflection","typescript",250,50),
     n(2,"logic","AI Opponent","Simple paddle AI that tracks ball position with reaction delay","typescript",450,50),
     n(3,"database","Game State Store","Score, paddle positions, ball position/velocity, game mode","typescript",50,250),
     n(4,"ui","Game Renderer","Canvas-based rendering with paddles, ball, score display, center line","typescript",450,250)],
    [e(0,1), e(1,3), e(2,1), e(3,4)], ["pong","game","physics","2d","multiplayer"]))

# 2. Snake Game
created.append(make_design("Snake Game",
    "Classic Snake with grid movement, growing body, collision detection, and progression",
    "Snake implementation with linked-list body representation, directional input, food collision, self-collision detection, scoring, and speed progression",
    [n(0,"input","Snake Controller","Arrow key input handler for direction change with anti-reverse protection","typescript",50,50),
     n(1,"logic","Movement Engine","Grid-based movement, linked-list body update, wrap-around or wall collision","typescript",250,50),
     n(2,"logic","Collision Detector","Food collision (growth trigger) and self-collision (game over) detection","typescript",450,50),
     n(3,"database","Game State","Snake body segments (linked list), food position, score, speed level","typescript",50,250),
     n(4,"ui","Grid Renderer","Renders grid, snake body with gradient coloring, food item, score HUD","typescript",450,250)],
    [e(0,1), e(1,2), e(1,3), e(3,4)], ["snake","game","linked-list","grid","arcade"]))

# 3. Tetris Game
created.append(make_design("Tetris Game",
    "Full Tetris with SRS rotation, bag randomizer, ghost piece, and T-spin detection",
    "Complete Tetris implementation with Super Rotation System, 7-bag randomizer, wall kicks, ghost piece preview, line clearing, T-spin detection, and scoring system",
    [n(0,"input","Tetris Controls","Keyboard input: left/right/down movement, rotate (CW/CCW), hard drop, hold","typescript",50,50),
     n(1,"logic","Piece Engine","7 tetromino types, SRS rotation with wall kick tables, bag randomizer","typescript",250,50),
     n(2,"logic","Collision & Clear","Piece placement collision, line clear detection with animation, T-spin detection","typescript",250,250),
     n(3,"database","Board State","10x20 grid, current piece position/rotation, next queue, hold piece, score","typescript",50,450),
     n(4,"ui","Game Board","Renders board, ghost piece, next piece preview, hold display, score, level","typescript",450,250),
     n(5,"logic","Scoring System","Tetris scoring: lines, combos, T-spins, back-to-back, level progression","typescript",450,50)],
    [e(0,1), e(1,2), e(2,3), e(5,3), e(3,4)], ["tetris","game","rotation","puzzle","arcade"]))

# 4. Platformer Engine
created.append(make_design("Platformer Engine",
    "2D platformer with tilemap physics, character controller, parallax scrolling, and enemies",
    "2D platformer engine with tile-based level loading, gravity/jump physics, collision response, animated character sprites, parallax backgrounds, and enemy AI",
    [n(0,"input","Player Input","Keyboard/mouse: movement (A/D), jump (W/space), action (E)","typescript",50,50),
     n(1,"logic","Character Controller","Gravity, acceleration, friction, jump physics, coyote time, variable jump height","typescript",250,50),
     n(2,"logic","Tile Collision","AABB collision against tilemap, slope handling, one-way platforms","typescript",250,250),
     n(3,"database","Level Store","Tilemap data, entity positions, spawn points, collectibles, enemy data","typescript",50,450),
     n(4,"logic","Enemy AI","Patrol, chase, and attack behavior with state machine and line-of-sight","typescript",450,50),
     n(5,"ui","Camera & Renderer","Parallax scrolling camera, sprite batching, animated tiles, HUD overlay","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4), e(3,5), e(4,5)], ["platformer","2d","physics","tilemap","game"]))

# 5. Chess Game
created.append(make_design("Chess Game",
    "Complete chess with move generation, check/checkmate detection, and minimax AI",
    "Full chess implementation with FEN/PGN parsing, all legal move generation (including castling, en passant, promotion), check/checkmate/stalemate detection, and minimax with alpha-beta pruning AI",
    [n(0,"input","Chess Input","Click-to-select/move pieces, drag-and-drop, FEN/PGN import, undo/redo","typescript",50,50),
     n(1,"logic","Move Generator","Generates all legal moves for each piece type with pin/check filtering","typescript",250,50),
     n(2,"logic","Game Rules Engine","Check/checkmate/stalemate detection, castling rights, en passant, 50-move rule","typescript",250,250),
     n(3,"database","Board State","8x8 board with piece positions, move history (algebraic notation), captured pieces","typescript",50,450),
     n(4,"logic","AI Engine","Minimax with alpha-beta pruning, iterative deepening, transposition table","typescript",450,50),
     n(5,"ui","Board Renderer","Renders board with piece sprites, highlights legal moves, last move, check","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(4,3), e(3,5)], ["chess","game","ai","minimax","board-game"]))

# 6. Minesweeper
created.append(make_design("Minesweeper",
    "Classic Minesweeper with flood-fill, flagging, timer, and first-click safety",
    "Minesweeper with randomized mine placement (first click safe), flood-fill reveal, flag marking, chord click, timer, and difficulty levels",
    [n(0,"input","Game Controls","Click to reveal, right-click to flag, chord click (both buttons), restart","typescript",50,50),
     n(1,"logic","Mine Engine","Mine placement (reservoir sampling), flood-fill reveal, mine count calculation","typescript",250,50),
     n(2,"logic","Game Logic","Win/loss detection, flag counting, timer management, difficulty config","typescript",250,250),
     n(3,"database","Board Data","Grid cells with mine/flag/revealed state, adjacent mine counts","typescript",50,450),
     n(4,"ui","Board Renderer","Renders grid with numbers, flags, mines, face button, mine counter, timer","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4)], ["minesweeper","game","puzzle","flood-fill","classic"]))

# 7. Connect 4
created.append(make_design("Connect 4",
    "Two-player Connect 4 with gravity physics, win detection, and AI opponent",
    "Connect 4 with column drop animation, horizontal/vertical/diagonal win detection, board-full detection, and minimax AI opponent with configurable depth",
    [n(0,"input","Column Selector","Click to select column, hover preview showing drop position","typescript",50,50),
     n(1,"logic","Gravity Engine","Token drop simulation with column stacking, piece placement animation","typescript",250,50),
     n(2,"logic","Win Detector","Horizontal, vertical, and both diagonal win conditions check after each move","typescript",250,250),
     n(3,"database","Board State","7x6 grid, current player turn, move history, win state","typescript",50,450),
     n(4,"logic","AI Opponent","Minimax with alpha-beta pruning and board evaluation heuristic","typescript",450,50),
     n(5,"ui","Board Renderer","Renders column grid with animated token drops, win highlight, turn indicator","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(4,3), e(3,5)], ["connect4","game","ai","minimax","two-player"]))

# 8. Tic-Tac-Toe
created.append(make_design("Tic-Tac-Toe",
    "Tic-Tac-Toe with unbeatable minimax AI, 3x3 grid, and score tracking",
    "Simple Tic-Tac-Toe with perfect AI opponent (minimax), win/draw detection, score tracking across rounds, and player/computer turn management",
    [n(0,"input","Grid Input","Click on cell to place X or O, highlights available cells","typescript",50,100),
     n(1,"logic","Minimax AI","Recursive minimax with alpha-beta pruning, evaluates all possible game states","typescript",250,100),
     n(2,"logic","Win/Tie Check","Row, column, and diagonal win detection with draw (board full, no winner)","typescript",250,300),
     n(3,"database","Game State","3x3 board array, current player, scores, game over flag","typescript",50,500),
     n(4,"ui","Board & Score","Renders 3x3 grid with X/O marks, score display, reset button","typescript",450,250)],
    [e(0,1), e(1,3), e(2,3), e(3,4)], ["tictactoe","game","ai","minimax","classic"]))

# 9. Card Game (War)
created.append(make_design("Card Game — War",
    "Classic War card game with deck building, shuffle, and battle animations",
    "War card game implementation with Fisher-Yates deck shuffle, card comparison, tie/war resolution, deck tracking, and animated card dealing/battling",
    [n(0,"input","Game Controls","Deal cards, play round, auto-play, restart game","typescript",50,50),
     n(1,"logic","Deck Engine","Fisher-Yates shuffle, deck splitting, card dealing (26 cards each)","typescript",250,50),
     n(2,"logic","Battle Engine","Card comparison, war resolution (3 face-down + 1 face-up), win detection","typescript",250,250),
     n(3,"database","Game State","Player 1/2 decks (queues), discard piles, round count, war depth","typescript",50,450),
     n(4,"ui","Card Renderer","Renders card back/front, battle field, deck counts, score, war animation","typescript",450,250)],
    [e(0,1), e(1,3), e(2,3), e(3,4)], ["card-game","war","shuffle","game","classic"]))

# 10. Blackjack
created.append(make_design("Blackjack",
    "Casino Blackjack with hit/stand/double/split, dealer AI, and chip management",
    "Full Blackjack game with card dealing, hand values (aces as 1/11), hit/stand/double-down/split, dealer AI (hit until 17), blackjack payout, and chip-based betting",
    [n(0,"input","Player Actions","Hit, Stand, Double Down, Split buttons with context-sensitive availability","typescript",50,50),
     n(1,"logic","Hand Engine","Card values, ace counting (soft/hard), hand total calculation, bust detection","typescript",250,50),
     n(2,"logic","Dealer AI","Dealer strategy (hit on 16 or below, stand on 17+), hole card handling","typescript",450,50),
     n(3,"database","Game State","Player/dealer hands, bet amount, chips, deck (shoe), game phase","typescript",50,250),
     n(4,"ui","Table Renderer","Renders felt table, cards with animations, chip stack, bet area, result display","typescript",450,250)],
    [e(0,1), e(1,3), e(2,3), e(3,4)], ["blackjack","card-game","casino","game","probability"]))

# 11. Memory Match
created.append(make_design("Memory Match",
    "Card matching memory game with flip animation, timer, and score tracking",
    "Match pairs of cards from a shuffled deck with face-down/face-up flip animation, card matching logic, move counting, timer, and score tracking",
    [n(0,"input","Card Grid Input","Click cards to flip, grid size selector (4x4, 4x6, 6x6)","typescript",50,100),
     n(1,"logic","Match Engine","Flip state management, pair matching comparison, match/mismatch handling","typescript",250,100),
     n(2,"database","Game State","Card grid with face-down/up/matched states, moves, matches found, timer","typescript",250,300),
     n(3,"ui","Memory Board","Renders card grid with flip animations, card back/front, match highlight","typescript",450,100),
     n(4,"ui","Score HUD","Move count, matches found, elapsed time, completion message","typescript",450,300)],
    [e(0,1), e(1,2), e(2,3), e(2,4)], ["memory","game","matching","puzzle","classic"]))

# 12. Hangman
created.append(make_design("Hangman",
    "Word guessing game with category selection, letter tracking, and visual hangman",
    "Hangman with word bank by category, letter-by-letter guessing, correct/incorrect tracking, visual hangman progression, and win/loss detection",
    [n(0,"input","Letter Input","On-screen keyboard or physical keyboard, category selector, hint button","typescript",50,50),
     n(1,"logic","Word Engine","Word selection from category, letter matching, partial word reveal","typescript",250,50),
     n(2,"logic","Game Logic","Correct/incorrect tracking, hangman stage progression, win/loss detection","typescript",250,250),
     n(3,"database","Game State","Target word, guessed letters (correct/incorrect), remaining attempts, hint status","typescript",50,450),
     n(4,"ui","Hangman Renderer","Renders gallows and stick figure stages, word blanks, keyboard, category display","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4)], ["hangman","word-game","game","classic","educational"]))

# 13. Sudoku Solver
created.append(make_design("Sudoku Solver",
    "Sudoku puzzle with backtracking solver, pencil marks, and difficulty levels",
    "Complete Sudoku application with puzzle generation (easy/medium/hard), backtracking solver with constraint propagation, pencil mark mode, and validation",
    [n(0,"input","Sudoku Input","Cell selection, number input, pencil mark toggle, difficulty select","typescript",50,50),
     n(1,"logic","Backtracking Solver","Constraint propagation, naked singles, hidden singles, backtracking with MRV heuristic","typescript",250,50),
     n(2,"logic","Puzzle Generator","Clue removal with unique solution verification, difficulty grading","typescript",250,250),
     n(3,"database","Puzzle State","81-cell grid with value/pencil marks/fixed status, solution, difficulty","typescript",50,450),
     n(4,"ui","Board Renderer","9x9 grid with 3x3 boxes, pencil marks, highlighting (same number/cell/box)","typescript",450,250)],
    [e(0,1), e(1,3), e(2,3), e(3,4)], ["sudoku","game","puzzle","backtracking","solver"]))

# 14. Space Shooter
created.append(make_design("Space Shooter",
    "Asteroids-style space shooter with ship physics, projectile combat, and waves",
    "Top-down space shooter with ship thrust/rotation physics, asteroid splitting, projectile collision, wave progression, score tracking, and particle explosions",
    [n(0,"input","Ship Controls","Thrust (W), rotate (A/D), shoot (space), hyperspace (H)","typescript",50,50),
     n(1,"logic","Ship Physics","Thrust acceleration, friction, rotation, wrap-around edges, momentum","typescript",250,50),
     n(2,"logic","Combat Engine","Projectile spawning, hit detection (bullet vs asteroid), asteroid splitting","typescript",250,250),
     n(3,"database","World State","Ship, asteroid, and projectile entity lists, score, wave number, lives","typescript",50,450),
     n(4,"ui","Game Renderer","Vector-style canvas rendering, score HUD, lives display, particle effects","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4)], ["space-shooter","game","asteroids","physics","arcade"]))

# 15. Breakout
created.append(make_design("Breakout",
    "Classic Breakout with paddle physics, brick types, power-ups, and level progression",
    "Breakout implementation with paddle reflection physics, multiple brick types (normal/hard/unbreakable), power-up drops (multi-ball, wide paddle), and level progression",
    [n(0,"input","Paddle Input","Mouse or keyboard (A/D) paddle movement, launch ball on click","typescript",50,50),
     n(1,"logic","Ball Physics","Ball movement, paddle/brick/wall collision response, angle reflection","typescript",250,50),
     n(2,"logic","Brick Engine","Brick types with health, power-up drops, level loading, score calculation","typescript",250,250),
     n(3,"database","Game State","Paddle/ball position, brick grid, power-up status, score, lives, level","typescript",50,450),
     n(4,"ui","Game View","Renders paddle, ball, brick grid, particle effects, score, lives, power-up icons","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4)], ["breakout","game","physics","brick-breaker","arcade"]))

# 16. Maze Generator & Solver
created.append(make_design("Maze Generator & Solver",
    "Procedural maze generation (DFS, Kruskal, Prim) with pathfinding solver visualization",
    "Generates mazes using multiple algorithms (recursive backtracking, Kruskal, Prim, Wilson), solves them with BFS/DFS/A*, and shows step-by-step generation/solving animations",
    [n(0,"input","Maze Config","Select generation algorithm, size, solving algorithm, animation speed","typescript",50,50),
     n(1,"logic","Generation Engine","DFS backtracking, Kruskal (union-find), Prim, Wilson's algorithm maze generation","typescript",250,50),
     n(2,"logic","Solving Engine","BFS shortest path, DFS explorer, A* heuristic pathfinding, dead-end filling","typescript",250,250),
     n(3,"database","Maze Data","Grid cells with wall states, visited flags, parent pointers for path","typescript",50,450),
     n(4,"ui","Maze Canvas","Renders maze generation/solving step-by-step with color-coded cells and path","typescript",450,250)],
    [e(0,1), e(1,3), e(2,3), e(3,4)], ["maze","game","procedural","pathfinding","algorithms"]))

# 17. RPG Character Builder
created.append(make_design("RPG Character Builder",
    "Character creation tool with stats, classes, skills, inventory, and equipment",
    "RPG character creator with class selection (warrior/mage/rogue), stat allocation, skill trees, inventory management, equipment system with modifiers, and character sheet export",
    [n(0,"input","Character Creator","Name input, class selection, stat point allocation, appearance choices","typescript",50,50),
     n(1,"logic","Stats Engine","Base stats (STR/DEX/INT/CON/WIS/CHA) with derived values (HP, MP, damage, defense)","typescript",250,50),
     n(2,"logic","Skill Tree","Skill point distribution, prerequisite checking, tier unlocking, active/passive skills","typescript",250,250),
     n(3,"database","Character Data","Character stats, skills, inventory items, equipment slots, progression level","typescript",50,450),
     n(4,"logic","Combat Simulator","Turn-based combat simulation for build testing with damage formulas","typescript",450,50),
     n(5,"ui","Character Sheet","Renders complete character sheet with stats, skills, equipment, inventory","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(4,3), e(3,5)], ["rpg","character-builder","game","stats","skills"]))

# 18. Tower Defense
created.append(make_design("Tower Defense",
    "Tower defense game with path-based enemies, tower placement, upgrades, and waves",
    "Tower defense with grid-based tower placement, predefined enemy paths, multiple tower types (arrow/cannon/magic/sniper), upgrade system, wave management, and resource economy",
    [n(0,"input","Tower Placement","Click to build/upgrade/sell towers on valid grid positions, wave start button","typescript",50,50),
     n(1,"logic","Enemy AI","Path following with waypoints, speed variation, health scaling per wave","typescript",250,50),
     n(2,"logic","Tower Engine","Target acquisition (first/strongest/fastest), projectile spawning, damage calculation","typescript",250,250),
     n(3,"database","Game State","Grid with towers, enemy list, wave config, gold, lives, score","typescript",50,450),
     n(4,"ui","Field Renderer","Renders grid, towers with range indicators, enemies with health bars, waves, HUD","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4)], ["tower-defense","game","strategy","pathfinding","wave"]))

# 19. Clicker / Idle Game
created.append(make_design("Clicker / Idle Game",
    "Incremental idle game with resource generation, upgrades, and prestige mechanics",
    "Idle clicker with resource clicking, automatic generation, building purchases (multipliers), upgrades, achievement system, and prestige/ascension reset mechanic",
    [n(0,"input","Click Input","Main resource click, upgrade purchases, building buys, prestige button","typescript",50,50),
     n(1,"logic","Resource Engine","Click value calculation, passive generation per second, building production chains","typescript",250,50),
     n(2,"logic","Economy Manager","Upgrade costs (exponential scaling), building prices, prestige point calculation","typescript",250,250),
     n(3,"database","Save State","Resource count, buildings/upgrades owned, prestige level, achievements","typescript",50,450),
     n(4,"ui","Idle Dashboard","Resource counter, building list, upgrade tree, prestige info, achievement popups","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4)], ["idle-game","clicker","incremental","game","economy"]))

# 20. Simon Says
created.append(make_design("Simon Says",
    "Memory sequence game with pattern generation, sound/light feedback, and difficulty scaling",
    "Simon Says memory game with random pattern generation (color+audio), sequence playback animation, player input matching, pattern length progression, and score tracking",
    [n(0,"input","Color Pad","4 colored buttons (red, green, blue, yellow) with click/touch input","typescript",50,100),
     n(1,"logic","Pattern Generator","Random color sequence generation with increasing length, strict mode, speed scaling","typescript",250,100),
     n(2,"logic","Match Checker","Player input sequence vs generated pattern comparison with position tracking","typescript",250,300),
     n(3,"database","Game Data","Current pattern array, player input array, round number, high score, speed level","typescript",50,500),
     n(4,"ui","Game Display","Renders color pad with light/sound feedback, round counter, score, sequence replay","typescript",450,250)],
    [e(0,1), e(1,2), e(2,3), e(3,4)], ["simon","game","memory","sequence","pattern"]))

# Write all to designs.json
existing.extend(created)
with open(DESIGNS_PATH, 'w') as f:
    json.dump(existing, f, indent=2)

print(f"✅ Wrote {len(created)} game designs to {DESIGNS_PATH}")
print(f"   Total designs now: {len(existing)}")

# Generate bible reference files
for i, d in enumerate(created):
    name_short = d['name'].lower().replace(' ', '-').replace('—','').replace('--','-').replace(',','').replace('...','')
    name_short = '-'.join([w for w in name_short.split('-') if w])
    bfile = os.path.join(BIBLE_DIR, f"{i+1:02d}-{name_short}.md")
    tags_str = ', '.join(d['tags'])
    nodes_str = '\n'.join([f"  - **{n['label']}** ({n['type']}): {n['description']}" for n in d['nodes']])
    content = f"""# 🏗️ {d['name']}

> **Design ID:** `{d['id']}`
> **Category:** 02-games
> **Tags:** {tags_str}
> **Target OS:** {d['targetOS']}

## Goal

{d['goal']}

## Purpose

{d['purpose']}

## Nodes ({len(d['nodes'])}

{nodes_str}

## Bible Reference

This design teaches concepts from **bible-reference/02-games/**
Related topics: {tags_str}

---

*Design generated for the Visual AI Architect system*
"""
    with open(bfile, 'w') as f:
        f.write(content)

print(f"✅ Batch 2 complete: {len(created)} game designs with bible reference files")
