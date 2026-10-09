# -*- coding: utf-8 -*-
"""
Code Bible — Category 06: Game engine patterns (atomic).
Convention: loops expose start/stop; entities are plain data + update(dt);
systems are pure functions over entity lists.
"""
CHUNKS = [
    {
        "id": "game-loop",
        "name": "Game Loop",
        "category": "game",
        "lang": "typescript",
        "when": "Driving continuous rendering + logic updates in a game",
        "why": "Atomic loop; update/render fns in, start/stop/state out — rAF-based, delta-time computed",
        "tags": ["game", "loop", "raf", "delta", "update"],
        "iface": r'''export interface GameLoopCallbacks { update(dt: number): void; render(now: number): void }
export function createGameLoop(callbacks: GameLoopCallbacks, targetFps?: number) {
  return {
    start(): void,
    stop(): void,
    get running(): boolean,
    get fps(): number,
  };
}''',
        "code": r'''export function createGameLoop(callbacks: GameLoopCallbacks, targetFps?: number) {
  let rafId: number | null = null;
  let last = 0;
  let frames = 0;
  let lastFpsTime = 0;
  let currentFps = 0;
  const frameMs = targetFps ? 1000 / targetFps : 0;

  function tick(now: number) {
    if (!last) last = now;
    let dt = (now - last) / 1000;
    last = now;
    if (frameMs) {
      if (dt < frameMs / 1000) { rafId = requestAnimationFrame(tick); return; }
      dt = Math.min(dt, frameMs / 1000);   // cap large stalls
    }
    callbacks.update(Math.min(dt, 0.1));
    callbacks.render(now);
    frames++;
    if (now - lastFpsTime >= 1000) { currentFps = frames; frames = 0; lastFpsTime = now; }
    rafId = requestAnimationFrame(tick);
  }

  return {
    start() { if (rafId === null) { last = 0; rafId = requestAnimationFrame(tick); } },
    stop() { if (rafId !== null) cancelAnimationFrame(rafId); rafId = null; },
    get running() { return rafId !== null; },
    get fps() { return currentFps; },
  };
}''',
        "provides": "createGameLoop(callbacks, targetFps?)",
        "depends": [],
    },
    {
        "id": "game-fixed-timestep",
        "name": "Fixed Timestep Accumulator",
        "category": "game",
        "lang": "typescript",
        "when": "Stable physics/simulation independent of frame rate",
        "why": "Atomic fixed-step; step fn + rate in, accumulator out — deterministic updates",
        "tags": ["timestep", "fixed", "physics", "deterministic", "accumulator"],
        "iface": r'''export function createFixedTimestep(stepMs: number) {
  return {
    advance(realMs: number): number,   // returns number of steps to run
    reset(): void,
    get accumulated(): number,
  };
}''',
        "code": r'''export function createFixedTimestep(stepMs: number) {
  let accumulator = 0;
  const maxFrame = 250;   // avoid spiral of death

  return {
    advance(realMs: number): number {
      accumulator += Math.min(realMs, maxFrame);
      let steps = 0;
      while (accumulator >= stepMs) { accumulator -= stepMs; steps++; }
      return steps;
    },
    reset() { accumulator = 0; },
    get accumulated() { return accumulator; },
  };
}''',
        "provides": "createFixedTimestep(stepMs)",
        "depends": [],
    },
    {
        "id": "game-ecs",
        "name": "Entity-Component System",
        "category": "game",
        "lang": "typescript",
        "when": "Organizing game objects as data + systems instead of deep class trees",
        "why": "Atomic ECS; entity/component/system registration out — composition over inheritance",
        "tags": ["ecs", "entity", "component", "system", "game"],
        "iface": r'''export interface Entity { id: number; components: Map<string, unknown> }
export function createEcs() {
  return {
    createEntity(): number,
    removeEntity(id: number): void,
    addComponent<T>(id: number, name: string, data: T): void,
    getComponent<T>(id: number, name: string): T | undefined,
    query(components: string[]): Entity[],
  };
}''',
        "code": r'''export function createEcs() {
  const entities = new Map<number, Entity>();
  let nextId = 0;

  return {
    createEntity() {
      const id = nextId++;
      entities.set(id, { id, components: new Map() });
      return id;
    },
    removeEntity(id) { entities.delete(id); },
    addComponent(id, name, data) {
      entities.get(id)?.components.set(name, data);
    },
    getComponent(id, name) {
      return entities.get(id)?.components.get(name) as unknown;
    },
    query(components) {
      const out: Entity[] = [];
      for (const entity of entities.values()) {
        if (components.every((c) => entity.components.has(c))) out.push(entity);
      }
      return out;
    },
  };
}''',
        "provides": "createEcs()",
        "depends": [],
    },
    {
        "id": "game-sprite-renderer",
        "name": "Canvas Sprite Renderer",
        "category": "game",
        "lang": "typescript",
        "when": "Drawing sprites/images to a canvas with scale and rotation",
        "why": "Atomic renderer; context + sprite in, draw call out — transform math only, no game logic",
        "tags": ["sprite", "canvas", "render", "draw", "image"],
        "iface": r'''export interface DrawSpriteOptions { scaleX?: number; scaleY?: number; rotation?: number; alpha?: number; anchorX?: number; anchorY?: number }
export function drawSprite(
  ctx: CanvasRenderingContext2D,
  image: CanvasImageSource,
  x: number, y: number,
  options?: DrawSpriteOptions,
): void''',
        "code": r'''export function drawSprite(
  ctx: CanvasRenderingContext2D,
  image: CanvasImageSource,
  x: number, y: number,
  options: DrawSpriteOptions = {},
) {
  const sw = typeof image === 'object' && 'width' in image ? (image as HTMLImageElement).width : 0;
  const sh = typeof image === 'object' && 'height' in image ? (image as HTMLImageElement).height : 0;
  const ax = options.anchorX ?? 0.5;
  const ay = options.anchorY ?? 0.5;
  const scaleX = options.scaleX ?? 1;
  const scaleY = options.scaleY ?? 1;

  ctx.save();
  ctx.translate(x, y);
  if (options.rotation) ctx.rotate(options.rotation);
  if (options.alpha !== undefined) ctx.globalAlpha = options.alpha;
  ctx.scale(scaleX, scaleY);
  ctx.drawImage(image, -sw * ax, -sh * ay, sw, sh);
  ctx.restore();
}''',
        "provides": "drawSprite(ctx, image, x, y, options?)",
        "depends": [],
    },
    {
        "id": "game-tilemap",
        "name": "Tilemap Renderer",
        "category": "game",
        "lang": "typescript",
        "when": "Rendering grid-based levels (platformers, roguelikes, strategy)",
        "why": "Atomic tilemap; grid + tileset + camera in, drawn out — culling and batching included",
        "tags": ["tilemap", "tiles", "grid", "render", "level"],
        "iface": r'''export function renderTilemap(
  ctx: CanvasRenderingContext2D,
  map: number[][],
  tileset: Record<number, { image: CanvasImageSource; sx: number; sy: number; size: number }>,
  camera: { x: number; y: number; scale?: number },
  tileSize: number,
): void''',
        "code": r'''export function renderTilemap(
  ctx: CanvasRenderingContext2D,
  map: number[][],
  tileset: Record<number, { image: CanvasImageSource; sx: number; sy: number; size: number }>,
  camera: { x: number; y: number; scale?: number },
  tileSize: number,
): void {
  const scale = camera.scale ?? 1;
  const viewW = ctx.canvas.width / scale;
  const viewH = ctx.canvas.height / scale;

  ctx.save();
  ctx.scale(scale, scale);
  ctx.translate(-camera.x, -camera.y);

  const startCol = Math.max(0, Math.floor(camera.x / tileSize));
  const endCol = Math.min(map[0]?.length ?? 0, Math.ceil((camera.x + viewW) / tileSize));
  const startRow = Math.max(0, Math.floor(camera.y / tileSize));
  const endRow = Math.min(map.length, Math.ceil((camera.y + viewH) / tileSize));

  for (let r = startRow; r < endRow; r++) {
    for (let c = startCol; c < endCol; c++) {
      const tile = map[r][c];
      const def = tileset[tile];
      if (!def) continue;
      ctx.drawImage(def.image, def.sx, def.sy, def.size, def.size, c * tileSize, r * tileSize, tileSize, tileSize);
    }
  }
  ctx.restore();
}''',
        "provides": "renderTilemap(ctx, map, tileset, camera, tileSize)",
        "depends": [],
    },
    {
        "id": "game-camera",
        "name": "Camera (Follow + Transform)",
        "category": "game",
        "lang": "typescript",
        "when": "Scrolling a world view that follows a target (player)",
        "why": "Atomic camera; target + viewport in, transform out — lerp smoothing + clamping",
        "tags": ["camera", "follow", "scroll", "viewport", "transform"],
        "iface": r'''export function createCamera(options?: { width?: number; height?: number; lerp?: number }) {
  return {
    x: number; y: number;
    follow(target: { x: number; y: number }, bounds?: { minX: number; minY: number; maxX: number; maxY: number }): void,
    worldToScreen(wx: number, wy: number): [number, number],
    screenToWorld(sx: number, sy: number): [number, number],
  };
}''',
        "code": r'''export function createCamera(options?: { width?: number; height?: number; lerp?: number }) {
  const width = options?.width ?? 800;
  const height = options?.height ?? 600;
  const lerp = options?.lerp ?? 0.12;
  const cam = { x: 0, y: 0 };

  return {
    get x() { return cam.x; },
    get y() { return cam.y; },
    follow(target, bounds) {
      const desiredX = target.x - width / 2;
      const desiredY = target.y - height / 2;
      cam.x += (desiredX - cam.x) * lerp;
      cam.y += (desiredY - cam.y) * lerp;
      if (bounds) {
        cam.x = Math.max(bounds.minX, Math.min(bounds.maxX - width, cam.x));
        cam.y = Math.max(bounds.minY, Math.min(bounds.maxY - height, cam.y));
      }
    },
    worldToScreen(wx, wy) { return [wx - cam.x, wy - cam.y]; },
    screenToWorld(sx, sy) { return [sx + cam.x, sy + cam.y]; },
  };
}''',
        "provides": "createCamera(options?)",
        "depends": [],
    },
    {
        "id": "game-input-manager",
        "name": "Keyboard/Mouse Input Manager",
        "category": "game",
        "lang": "typescript",
        "when": "Tracking held keys and mouse state for gameplay controls",
        "why": "Atomic input; nothing in, isDown/justPressed/position out — listeners wired internally",
        "tags": ["input", "keyboard", "mouse", "controls", "keys"],
        "iface": r'''export function createInputManager() {
  return {
    isDown(key: string): boolean,
    justPressed(key: string): boolean,
    get mouse(): { x: number; y: number; down: boolean },
    update(): void,
    destroy(): void,
  };
}''',
        "code": r'''export function createInputManager() {
  const held = new Set<string>();
  const pressed = new Set<string>();
  const mouse = { x: 0, y: 0, down: false };
  let mousePressed = false;

  function onKeyDown(e: KeyboardEvent) {
    if (!held.has(e.key)) pressed.add(e.key);
    held.add(e.key);
  }
  function onKeyUp(e: KeyboardEvent) { held.delete(e.key); }
  function onMouseMove(e: MouseEvent) { mouse.x = e.clientX; mouse.y = e.clientY; }
  function onMouseDown(e: MouseEvent) { mouse.down = true; mousePressed = true; }
  function onMouseUp() { mouse.down = false; }

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mousedown', onMouseDown);
  window.addEventListener('mouseup', onMouseUp);

  return {
    isDown: (key) => held.has(key),
    justPressed: (key) => pressed.has(key),
    get mouse() { return mouse; },
    update() {
      pressed.clear();
      mousePressed = false;
    },
    destroy() {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
    },
  };
}''',
        "provides": "createInputManager()",
        "depends": [],
    },
    {
        "id": "game-audio-manager",
        "name": "WebAudio Sound Manager",
        "category": "game",
        "lang": "typescript",
        "when": "Playing sound effects with volume control and pooling",
        "why": "Atomic audio; nothing in, play/volume/stop out — single AudioContext, reusable buffers",
        "tags": ["audio", "sound", "webaudio", "sfx", "volume"],
        "iface": r'''export function createSoundManager() {
  return {
    load(key: string, url: string): Promise<void>,
    play(key: string, options?: { volume?: number; loop?: boolean }): void,
    stopAll(): void,
    setMasterVolume(v: number): void,
    get context(): AudioContext | null,
  };
}''',
        "code": r'''export function createSoundManager() {
  const buffers = new Map<string, AudioBuffer>();
  let ctx: AudioContext | null = null;
  let master: GainNode | null = null;
  let volume = 1;

  function ensureCtx(): AudioContext {
    if (!ctx) {
      ctx = new AudioContext();
      master = ctx.createGain();
      master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') void ctx.resume();
    return ctx;
  }

  return {
    async load(key, url) {
      const c = ensureCtx();
      const res = await fetch(url);
      const data = await res.arrayBuffer();
      buffers.set(key, await c.decodeAudioData(data));
    },
    play(key, options) {
      const buffer = buffers.get(key);
      if (!buffer || !ctx || !master) return;
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      const gain = ctx.createGain();
      gain.gain.value = (options?.volume ?? 1) * volume;
      src.connect(gain);
      gain.connect(master);
      if (options?.loop) src.loop = true;
      src.start();
    },
    stopAll() {
      ctx?.close();
      ctx = null;
      master = null;
    },
    setMasterVolume(v) {
      volume = Math.max(0, Math.min(1, v));
      if (master) master.gain.value = volume;
    },
    get context() { return ctx; },
  };
}''',
        "provides": "createSoundManager()",
        "depends": [],
    },
    {
        "id": "game-particles",
        "name": "Particle System",
        "category": "game",
        "lang": "typescript",
        "when": "Explosions, confetti, sparks, and ambient effects",
        "why": "Atomic emitter; spawn config in, update/render out — physics + culling inside",
        "tags": ["particles", "effects", "explosion", "confetti", "emitter"],
        "iface": r'''export interface Particle { x: number; y: number; vx: number; vy: number; life: number; maxLife: number; size: number; color: string }
export interface ParticleEmitterConfig { rate: number; count: number; speed: number; life: number; size: number; colors: string[]; gravity?: number; spread?: number }
export function createParticleSystem() {
  return {
    emit(x: number, y: number, config: ParticleEmitterConfig): void,
    update(dt: number): void,
    render(ctx: CanvasRenderingContext2D): void,
    get count(): number,
    clear(): void,
  };
}''',
        "code": r'''export function createParticleSystem() {
  const particles: Particle[] = [];

  return {
    emit(x, y, config) {
      for (let i = 0; i < config.count; i++) {
        const angle = Math.random() * Math.PI * 2 * (config.spread ?? 1);
        const speed = Math.random() * config.speed;
        particles.push({
          x, y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          life: 0,
          maxLife: config.life * (0.6 + Math.random() * 0.8),
          size: config.size * (0.5 + Math.random()),
          color: config.colors[Math.floor(Math.random() * config.colors.length)],
        });
      }
    },
    update(dt) {
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.life += dt;
        if (p.life >= p.maxLife) { particles.splice(i, 1); continue; }
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        if (p.gravity !== undefined) p.vy += p.gravity * dt;
        p.vx *= 0.99;
        p.vy *= 0.99;
      }
    },
    render(ctx) {
      for (const p of particles) {
        const t = 1 - p.life / p.maxLife;
        ctx.globalAlpha = t;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(0.5, p.size * t), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    },
    get count() { return particles.length; },
    clear() { particles.length = 0; },
  };
}''',
        "provides": "createParticleSystem()",
        "depends": [],
    },
    {
        "id": "game-score-system",
        "name": "Score/Combo System",
        "category": "game",
        "lang": "typescript",
        "when": "Tracking score, level, lives, and combo multipliers",
        "why": "Atomic scorekeeper; nothing in, add/level/state out — pure counter logic, UI separate",
        "tags": ["score", "combo", "level", "lives", "points"],
        "iface": r'''export function createScoreSystem(options?: { comboWindowMs?: number }) {
  return {
    add(points: number, now?: number): number,
    get score(): number,
    get combo(): number,
    get level(): number,
    setLevel(n: number): void,
    get highScore(): number,
    reset(): void,
  };
}''',
        "code": r'''export function createScoreSystem(options?: { comboWindowMs?: number }) {
  const comboWindow = options?.comboWindowMs ?? 2000;
  let score = 0;
  let combo = 0;
  let level = 1;
  let highScore = 0;
  let lastHit = 0;

  return {
    add(points, now = Date.now()) {
      combo = now - lastHit <= comboWindow ? combo + 1 : 1;
      lastHit = now;
      const gained = Math.round(points * (1 + (combo - 1) * 0.1));
      score += gained;
      highScore = Math.max(highScore, score);
      return gained;
    },
    get score() { return score; },
    get combo() { return combo; },
    get level() { return level; },
    setLevel(n) { level = n; },
    get highScore() { return highScore; },
    reset() { score = 0; combo = 0; level = 1; lastHit = 0; },
  };
}''',
        "provides": "createScoreSystem(options?)",
        "depends": [],
    },
    {
        "id": "game-save-load",
        "name": "Game Save/Load",
        "category": "game",
        "lang": "typescript",
        "when": "Persisting game state and restoring it on launch",
        "why": "Atomic save system; serialize/deserialize in, save/load/delete out — versioned payload",
        "tags": ["save", "load", "persist", "checkpoint", "game"],
        "iface": r'''export interface SavePayload { version: number; state: unknown; savedAt: number }
export function createGameSave(storage: StorageAdapter<SavePayload>) {
  return {
    save(state: unknown): void,
    load(): unknown | null,
    hasSave(): boolean,
    delete(): void,
  };
}''',
        "code": r'''export function createGameSave(storage: StorageAdapter<SavePayload>) {
  const VERSION = 1;
  return {
    save(state) {
      storage.save({ version: VERSION, state, savedAt: Date.now() });
    },
    load() {
      const payload = storage.load();
      if (!payload || payload.version > VERSION) return null;
      return payload.state;
    },
    hasSave() {
      return storage.load() !== null;
    },
    delete() { storage.clear(); },
  };
}''',
        "provides": "createGameSave(storage)",
        "depends": ["state-local-storage"],
    },
    {
        "id": "game-level-loader",
        "name": "Level Loader",
        "category": "game",
        "lang": "typescript",
        "when": "Loading level definitions from ASCII or JSON maps",
        "why": "Atomic loader; raw level in, typed Level out — ASCII-to-grid translation only",
        "tags": ["level", "loader", "map", "ascii", "tiles"],
        "iface": r'''export interface LoadedLevel { width: number; height: number; grid: string[][]; playerStart?: [number, number]; entities: Array<{ type: string; x: number; y: number }> }
export function loadAsciiLevel(ascii: string, legend: Record<string, string>): LoadedLevel''',
        "code": r'''export function loadAsciiLevel(ascii: string, legend: Record<string, string>): LoadedLevel {
  const lines = ascii.trim().split('\n').map((l) => l.trim()).filter(Boolean);
  const grid = lines.map((line) => [...line].map((ch) => legend[ch] ?? 'empty'));
  const height = grid.length;
  const width = grid[0]?.length ?? 0;

  const entities: LoadedLevel['entities'] = [];
  let playerStart: [number, number] | undefined;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const ch = lines[y][x];
      if (ch === 'P') playerStart = [x, y];
      if (ch !== '.' && ch !== '#' && ch !== 'P') entities.push({ type: ch, x, y });
    }
  }

  return { width, height, grid, playerStart, entities };
}''',
        "provides": "loadAsciiLevel(ascii, legend)",
        "depends": [],
    },
    {
        "id": "game-achievement",
        "name": "Achievement Tracker",
        "category": "game",
        "lang": "typescript",
        "when": "Unlocking and notifying achievements/badges",
        "why": "Atomic achievement engine; defs in, unlock/onUnlock out — persists via injected store",
        "tags": ["achievement", "badge", "unlock", "progress", "gamification"],
        "iface": r'''export interface AchievementDef { id: string; name: string; description: string; condition: (stats: Record<string, number>) => boolean }
export function createAchievementTracker(defs: AchievementDef[], onUnlock?: (id: string) => void) {
  return {
    updateStats(stats: Record<string, number>): string[],
    unlock(id: string): boolean,
    get unlocked(): Set<string>,
    get progress(): Array<{ id: string; unlocked: boolean; condition: string }>,
  };
}''',
        "code": r'''export function createAchievementTracker(defs: AchievementDef[], onUnlock?: (id: string) => void) {
  const unlocked = new Set<string>();
  let stats: Record<string, number> = {};

  return {
    updateStats(next: Record<string, number>) {
      stats = { ...stats, ...next };
      const fresh: string[] = [];
      for (const def of defs) {
        if (!unlocked.has(def.id) && def.condition(stats)) {
          unlocked.add(def.id);
          fresh.push(def.id);
          onUnlock?.(def.id);
        }
      }
      return fresh;
    },
    unlock(id) {
      if (unlocked.has(id)) return false;
      if (!defs.some((d) => d.id === id)) return false;
      unlocked.add(id);
      onUnlock?.(id);
      return true;
    },
    get unlocked() { return new Set(unlocked); },
    get progress() {
      return defs.map((d) => ({ id: d.id, unlocked: unlocked.has(d.id), condition: d.description }));
    },
  };
}''',
        "provides": "createAchievementTracker(defs, onUnlock?)",
        "depends": [],
    },
    {
        "id": "game-aabb-collision",
        "name": "AABB Collision",
        "category": "game",
        "lang": "typescript",
        "when": "Detecting rectangle overlaps for platforms, bullets, pickups",
        "why": "Atomic collision; two boxes in, overlap + resolution out — pure math, no game state",
        "tags": ["collision", "aabb", "rect", "overlap", "physics"],
        "iface": r'''export interface Rect { x: number; y: number; w: number; h: number }
export function aabbOverlap(a: Rect, b: Rect): boolean
export function resolveAabb(a: Rect, b: Rect, velocity: { vx: number; vy: number }): { x: number; y: number; vx: number; vy: number; hit: 'x' | 'y' | 'none' }''',
        "code": r'''export function aabbOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

export function resolveAabb(a: Rect, b: Rect, velocity: { vx: number; vy: number }) {
  // Move then resolve on the axis of least penetration.
  const overlapX = Math.min(a.x + a.w - b.x, b.x + b.w - a.x);
  const overlapY = Math.min(a.y + a.h - b.y, b.y + b.h - a.y);

  if (overlapX < overlapY) {
    const x = velocity.vx > 0 ? b.x - a.w : b.x + b.w;
    return { x, y: a.y, vx: 0, vy: velocity.vy, hit: 'x' as const };
  }
  const y = velocity.vy > 0 ? b.y - a.h : b.y + b.h;
  return { x: a.x, y, vx: velocity.vx, vy: 0, hit: 'y' as const };
}''',
        "provides": "aabbOverlap(a, b), resolveAabb(a, b, velocity)",
        "depends": [],
    },
    {
        "id": "game-highscore-table",
        "name": "High-Score Table",
        "category": "game",
        "lang": "typescript",
        "when": "Ranking player scores with name entry and top-N retention",
        "why": "Atomic leaderboard; score in, sorted table out — top-N only, injected storage",
        "tags": ["highscore", "leaderboard", "rank", "score", "table"],
        "iface": r'''export interface ScoreEntry { name: string; score: number; date: string }
export function createHighScoreTable(limit?: number) {
  return {
    add(name: string, score: number): number,   // returns rank (1-based)
    get top(): ScoreEntry[],
    qualifies(score: number): boolean,
    load(entries: ScoreEntry[]): void,
    export(): ScoreEntry[],
  };
}''',
        "code": r'''export function createHighScoreTable(limit = 10) {
  let entries: ScoreEntry[] = [];

  return {
    add(name, score) {
      const entry: ScoreEntry = { name: name.slice(0, 16), score, date: new Date().toISOString() };
      entries.push(entry);
      entries.sort((a, b) => b.score - a.score);
      entries = entries.slice(0, limit);
      return entries.indexOf(entry) + 1;
    },
    get top() { return [...entries]; },
    qualifies(score) {
      return entries.length < limit || score > entries[entries.length - 1].score;
    },
    load(loaded) { entries = [...loaded].sort((a, b) => b.score - a.score).slice(0, limit); },
    export() { return [...entries]; },
  };
}''',
        "provides": "createHighScoreTable(limit?)",
        "depends": ["state-local-storage"],
    },
]
