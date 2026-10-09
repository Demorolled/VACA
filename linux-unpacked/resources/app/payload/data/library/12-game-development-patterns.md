# 🎮 Game Development Patterns

> Reference for game development patterns, architectures, and implementation strategies.
> Extracted from The Programming Bible — apply these when generating game code from node designs.

---

## 1. The Game Loop

The central control structure for every real-time game. Three core pillars: **Input → Update → Render**.

### Loop Strategies

| Strategy | Description | When to Use |
|---|---|---|
| **Naive Loop** | Runs as fast as CPU allows | ❌ Avoid — framerate-dependent physics, high CPU |
| **Fixed Timestep** | Simulation advances by fixed Δt, render is decoupled | ✅ Industry standard for deterministic games |
| **Variable Timestep** | Uses actual time elapsed between frames | ⚠️ Simple but non-deterministic behavior |
| **Semi-Fixed Timestep** | Fixed update steps, variable render rate | ✅ Best compromise for most games |

### Fixed Timestep Pattern

```typescript
// Fixed timestep game loop
const FIXED_DT = 1 / 60; // 60 updates per second
const MAX_FRAME_TIME = 0.25; // Prevent spiral of death

let accumulator = 0;
let previousTime = performance.now();

function gameLoop(currentTime: number): void {
  let frameTime = (currentTime - previousTime) / 1000;
  frameTime = Math.min(frameTime, MAX_FRAME_TIME);
  accumulator += frameTime;

  while (accumulator >= FIXED_DT) {
    update(FIXED_DT); // Fixed-step simulation
    accumulator -= FIXED_DT;
  }

  const alpha = accumulator / FIXED_DT; // Interpolation factor
  render(alpha); // Render with interpolation for smooth visuals

  previousTime = currentTime;
  requestAnimationFrame(gameLoop);
}
```

### Game Loop Components

| Component | Responsibility | Anti-Pattern |
|---|---|---|
| **Input** | Poll or capture events each frame | Blocking on input |
| **Update** | Advance game state by Δt | Variable Δt for physics |
| **Render** | Draw current state (stateless) | Mixing logic with rendering |
| **Physics** | Collision detection, forces, integration | Per-frame physics without substeps |

---

## 2. Entity Component System (ECS)

Data-oriented architecture — composition over inheritance.

### Core Concepts

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Entity     │     │  Component   │     │   System     │
│  (just ID)   │────▶│  (pure data) │────▶│   (logic)    │
└──────────────┘     └──────────────┘     └──────────────┘
      │                     │                     │
      │  Player_42          │  Position{x,y}      │  MovementSystem
      │  Enemy_17           │  Velocity{vx,vy}     │  PhysicsSystem
      │  Bullet_3           │  Health{hp,max}      │  RenderSystem
```

### ECS Implementation

```typescript
// TypeScript ECS Example
type Entity = number;

interface Component {
  type: string;
  data: Record<string, unknown>;
}

// Dense component pool for cache-friendly access
class ComponentPool<T> {
  private sparse: Map<Entity, number> = new Map();
  private dense: T[] = [];
  private entityIds: Entity[] = [];

  add(entity: Entity, component: T): void {
    const idx = this.dense.length;
    this.sparse.set(entity, idx);
    this.dense.push(component);
    this.entityIds.push(entity);
  }

  get(entity: Entity): T | undefined {
    const idx = this.sparse.get(entity);
    if (idx === undefined) return undefined;
    return this.dense[idx];
  }

  remove(entity: Entity): void {
    const idx = this.sparse.get(entity);
    if (idx === undefined) return;
    
    // Swap-with-back O(1) removal
    const lastIdx = this.dense.length - 1;
    if (idx !== lastIdx) {
      this.dense[idx] = this.dense[lastIdx];
      this.entityIds[idx] = this.entityIds[lastIdx];
      this.sparse.set(this.entityIds[idx], idx);
    }
    this.dense.pop();
    this.entityIds.pop();
    this.sparse.delete(entity);
  }

  *entitiesWith(): Generator<[Entity, T]> {
    for (let i = 0; i < this.dense.length; i++) {
      yield [this.entityIds[i], this.dense[i]];
    }
  }
}

// System operates on entities with specific components
class MovementSystem {
  update(positions: ComponentPool<Position>, velocities: ComponentPool<Velocity>, dt: number): void {
    for (const [entity, pos] of positions.entitiesWith()) {
      const vel = velocities.get(entity);
      if (vel) {
        pos.x += vel.vx * dt;
        pos.y += vel.vy * dt;
      }
    }
  }
}
```

### ECS vs OOP

| Aspect | OOP (Inheritance) | ECS (Composition) |
|---|---|---|
| **Memory layout** | AoS — fragmented | SoA/dense pools — cache-friendly |
| **Flexibility** | Rigid hierarchy | Mix & match components |
| **Code reuse** | Base classes | Shared systems |
| **Performance** | Virtual dispatch, cache misses | Contiguous memory, branch-predictable |
| **When to use** | Simple games, small scope | Complex games, many entity types |

---

## 3. Collision Detection

### Broad Phase vs Narrow Phase

```typescript
// Broad phase — fast rejection
interface AABB {
  x: number; y: number;
  width: number; height: number;
}

function aabbOverlap(a: AABB, b: AABB): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x &&
         a.y < b.y + b.height && a.y + a.height > b.y;
}

// Spatial partitioning for broad phase
class Grid {
  private cells: Map<string, Entity[]> = new Map();
  private cellSize: number;

  clear(): void { this.cells.clear(); }

  insert(entity: Entity, x: number, y: number): void {
    const key = `${Math.floor(x / this.cellSize)},${Math.floor(y / this.cellSize)}`;
    if (!this.cells.has(key)) this.cells.set(key, []);
    this.cells.get(key)!.push(entity);
  }

  getNearby(x: number, y: number): Entity[] {
    const results: Entity[] = [];
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const key = `${Math.floor(x / this.cellSize) + dx},${Math.floor(y / this.cellSize) + dy}`;
        results.push(...(this.cells.get(key) ?? []));
      }
    }
    return results;
  }
}
```

### Collision Response Patterns

| Type | Approach | Use Case |
|---|---|---|
| **Circle** | Distance < r1 + r2 | Simple entities, balls |
| **AABB** | Axis-aligned overlap | Tiles, boxes, UI |
| **SAT** | Separating Axis Theorem | Convex polygons, rotated objects |
| **Pixel-perfect** | Bitmask overlap | 2D sprites, precise detection |

---

## 4. State Machine Pattern

```typescript
// Finite State Machine for game entities
interface State {
  name: string;
  enter(entity: Entity): void;
  update(entity: Entity, dt: number): State | null;
  exit(entity: Entity): void;
}

class StateMachine {
  private states: Map<string, State> = new Map();
  private current: State | null = null;
  private entity: Entity;

  add(state: State): void {
    this.states.set(state.name, state);
  }

  transition(name: string): void {
    const next = this.states.get(name);
    if (!next) throw new Error(`Unknown state: ${name}`);
    this.current?.exit(this.entity);
    this.current = next;
    this.current.enter(this.entity);
  }

  update(dt: number): void {
    if (!this.current) return;
    const next = this.current.update(this.entity, dt);
    if (next) this.transition(next.name);
  }
}

// Example: Enemy AI states
const idleState: State = {
  name: 'idle',
  enter: (e: Entity) => { /* start idle animation */ },
  update: (e: Entity, dt: number) => {
    if (detectPlayer(e)) return patrolState; // Transition
    return null;
  },
  exit: (e: Entity) => { /* cleanup */ }
};
```

---

## 5. AI for Games

### Common AI Techniques

| Technique | Used For | Complexity |
|---|---|---|
| **A\* Pathfinding** | Grid-based navigation | O(b^d) |
| **Finite State Machines** | Simple behavior switching | O(1) |
| **Behavior Trees** | Complex decision making | O(n) |
| **NavMesh** | 3D pathfinding | Precomputed |
| **Steering Behaviors** | Flocking, chasing, evading | O(n) per entity |
| **Minimax** | Turn-based strategy | O(b^d) |

### Behavior Tree Pattern

```typescript
// Simplified behavior tree
type Status = 'success' | 'failure' | 'running';

interface Node {
  tick(blackboard: Map<string, unknown>): Status;
}

class Selector implements Node {
  constructor(private children: Node[]) {}
  
  tick(bb: Map<string, unknown>): Status {
    for (const child of this.children) {
      const status = child.tick(bb);
      if (status !== 'failure') return status;
    }
    return 'failure';
  }
}

class Sequence implements Node {
  constructor(private children: Node[]) {}
  
  tick(bb: Map<string, unknown>): Status {
    for (const child of this.children) {
      const status = child.tick(bb);
      if (status !== 'success') return status;
    }
    return 'success';
  }
}
```

---

## 6. Network Sync for Games

### Synchronization Strategies

| Strategy | Bandwidth | Deterministic | Rewind | Use Case |
|---|---|---|---|---|
| **Lockstep** | Low | ✅ Required | No | RTS, fighting games |
| **State Sync** | High | No | No | Casual, MMOs |
| **Client-side Prediction** | Medium | No | Optional | FPS, racing |
| **Deterministic Lockstep** | Very low | ✅ Required | Yes | Competitive RTS |

### Client-Side Prediction Pattern

```typescript
// Client predicts state, server authoritatively corrects
class NetworkedEntity {
  public position: Vec2;
  public velocity: Vec2;
  private pendingInputs: Input[] = [];
  private serverState: ServerSnapshot | null = null;

  applyInput(input: Input): void {
    this.pendingInputs.push(input);
    // Predict locally
    this.position.x += this.velocity.x * input.dt;
    this.position.y += this.velocity.y * input.dt;
  }

  receiveServerState(snapshot: ServerSnapshot): void {
    // Server reconciliation
    const serverPos = snapshot.entityPositions.get(this.id);
    if (!serverPos) return;

    // Find how many inputs the server processed
    const processedCount = snapshot.processedInputIndex;
    const unconsumed = this.pendingInputs.slice(processedCount);

    // Reset to server state
    this.position = serverPos;

    // Re-apply unconsumed inputs
    for (const input of unconsumed) {
      this.applyInput(input);
    }
  }
}
```

---

## 7. Game Project Structure

```
game-project/
├── src/
│   ├── main.ts                 # Entry point, game loop init
│   ├── engine/
│   │   ├── loop.ts             # Fixed timestep game loop
│   │   ├── ecs.ts              # Entity-Component-System core
│   │   ├── input.ts            # Input handling
│   │   ├── audio.ts            # Audio system
│   │   └── assets.ts           # Asset loading/caching
│   ├── systems/
│   │   ├── physics.ts          # Physics & collision
│   │   ├── rendering.ts        # Rendering pipeline
│   │   ├── animation.ts        # Animation system
│   │   ├── ai.ts               # AI behavior
│   │   └── network.ts          # Network sync
│   ├── components/
│   │   ├── transform.ts        # Position, rotation, scale
│   │   ├── physics.ts          # Velocity, mass, collision
│   │   ├── renderable.ts       # Sprite, mesh, material
│   │   └── health.ts           # HP, damage, state
│   ├── entities/
│   │   ├── player.ts           # Player entity factory
│   │   ├── enemy.ts            # Enemy entity factory
│   │   └── projectile.ts       # Projectile entity factory
│   └── utils/
│       ├── math.ts             # Vec2, Mat4, random
│       └── pool.ts             # Object pool
├── assets/                     # Sprites, audio, levels
├── package.json
└── README.md
```

---

## 8. Rendering & 3D (Three.js)

> The game loop, AI, and ECS above are engine-agnostic. For the **rendering
> layer** — especially 3D games like chess, mazes, and builders — consult
> `44-threejs-scene-recipes.md` FIRST. Quick pointers:

- **Single-file rule:** the browser preview has no build step. Use Three.js
  r128 UMD via CDN (`three.min.js` global `THREE`) + `examples/js/controls/OrbitControls.js`, both pinned to 0.128.0. NEVER ES module imports.
- **Depth = shadows + lighting:** `renderer.shadowMap.enabled` + PCFSoft +
  `shadow.bias = -0.0005`; key directional light + ambient + cool fill.
- **Chess pieces:** `THREE.LatheGeometry` with Vector2(radius, height)
  profiles — the recipe sheet ships pawn/rook/knight/bishop/queen/king arrays.
- **Motion:** lerp moves inside the render loop (`position.lerpVectors` +
  easeInOut) for smooth, interruption-safe animation.
- **Picking:** Raycaster on pointerdown/pointermove for square selection.
- **Always guard:** `typeof THREE === 'undefined'` → on-screen fallback message.

---

## Quick Reference: Game Dev by Node Type

| Node Type | Game Dev Mapping |
|---|---|
| **Input** | Keyboard/mouse/gamepad polling, touch events |
| **Logic** | Game loop, ECS systems, AI behavior, physics |
| **Database** | Save/load game state, leaderboards, config |
| **UI** | HUD, menus, inventory, minimap, dialogue |
| **API** | Multiplayer networking, leaderboard API, cloud saves |

---

*For deeper game development concepts, see Bible levels `02-games/`, `09-game-engines/`, and `10-collision-detection.md`*
