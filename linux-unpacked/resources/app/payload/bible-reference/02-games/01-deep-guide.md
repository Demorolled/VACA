# 02 — Games — Deep Technical Guide

> A comprehensive technical guide for building game systems and engines. Covers game loop architecture, physics, AI, graphics rendering, and networking. Use this as a reference when generating game code.

## Overview

> Reference for building game systems and engines. Covers game loop architecture, physics, AI, graphics rendering, and networking.

### Game Loop Architectures

| Architecture | Characteristics | Use Case |
|---|---|---|
| **Fixed Timestep + Variable Render** | Fixed physics step, variable render frame rate | Arcade, simulation |
| **Fixed Timestep + Fixed Render** | Both physics and render at fixed intervals | Real-time strategy |
| **Variable Timestep + Variable Render** | Both physics and render variable | Casual games, visual novels |
| **Physics-First** | Physics updates before rendering | RTS, tactical games |
| **Render-First** | Rendering before physics | 2D top-down, match-3 |

### Game States

| State | Transition | Action |
|---|---|---|
| **Title** | Start game | Reset state |
| **Menu** | New game | Create game state |
| **Game** | Game over | Reset state |
| **Game** | Quit game | Return to menu |
| **Paused** | Resume game | Unpause |
| **Paused** | Main menu | Return to menu |

### Input Handling

```typescript
// Game input system
interface InputEvent {
  type: string;
  timestamp: number;
  keys: Record<string, boolean>;
  mouse: { x: number; y: number; buttons: Record<string, boolean> };
  touch: Array<{ id: number; x: number; y: number; phase: string }>;
}

class InputSystem {
  private events: InputEvent[] = [];
  private pendingEvents: InputEvent[] = [];
  private delta: number = 0;

  handleEvent(event: InputEvent): void {
    this.pendingEvents.push(event);
  }

  update(delta: number): void {
    this.delta = delta;

    // Process pending events
    while (this.pendingEvents.length > 0) {
      const event = this.pendingEvents.shift()!;
      this.events.push(event);

      // Consume input events
      // ...

      // Remove processed events
      this.pendingEvents.shift();
    }

    // Update game state with input
    this.updateState();
  }

  private updateState(): void {
    // Game state updates based on input
    // ...
  }
}
```

### Game State Management

```typescript
// Game state management
class GameState {
  private stateStack: GameState[] = [];
  private currentState: GameState | null = null;

  pushState(state: GameState): void {
    this.stateStack.push(this.currentState);
    this.currentState = state;
    state.initialize();
  }

  popState(): void {
    if (this.currentState?.canPop()) {
      this.currentState = this.stateStack.pop();
      if (this.currentState) {
        this.currentState.update(0);
      }
    }
  }

  update(delta: number): void {
    if (this.currentState) {
      this.currentState.update(delta);
    }
  }

  render(context: CanvasRenderingContext2D): void {
    if (this.currentState) {
      this.currentState.render(context);
    }
  }
}
```

### Physics Engine

```typescript
// Physics engine
class PhysicsEngine {
  private bodies: Map<string, Body> = new Map();
  private constraints: Array<Constraint> = [];

  update(delta: number): void {
    // Update bodies
    for (const body of this.bodies.values()) {
      body.update(delta);
    }

    // Solve constraints
    for (const constraint of this.constraints) {
      constraint.solve(delta);
    }
  }

  applyForce(id: string, force: Vec2, point: Vec2): void {
    const body = this.bodies.get(id);
    if (body) {
      body.applyForce(force, point);
    }
  }

  addBody(body: Body): void {
    this.bodies.set(body.id, body);
  }

  addConstraint(constraint: Constraint): void {
    this.constraints.push(constraint);
  }
}
```

### AI System

```typescript
// AI system
interface AITrait {
  name: string;
  update(entity: Entity, deltaTime: number): void;
}

class AIManager {
  private traits: Map<string, AITrait> = new Map();
  private activeTraits: Map<string, AITrait> = new Map();

  addTrait(name: string, trait: AITrait): void {
    this.traits.set(name, trait);
  }

  activateTrait(entity: Entity, name: string): void {
    const trait = this.traits.get(name);
    if (trait) {
      this.activeTraits.set(entity.id, trait);
    }
  }

  update(deltaTime: number): void {
    for (const [id, trait] of this.activeTraits) {
      const entity = entityManager.getEntity(id);
      if (entity) {
        trait.update(entity, deltaTime);
      }
    }
  }
}
```

### Network System

```typescript
// Network system
interface NetworkMessage {
  id: string;
  type: string;
  data: Record<string, any>;
}

class NetworkSystem {
  private messages: Array<NetworkMessage> = [];

  send(message: NetworkMessage): void {
    this.messages.push(message);
  }

  receive(data: any): void {
    // Parse incoming data into NetworkMessage
    // ...
  }

  update(delta: number): void {
    // Process network messages
    for (const message of this.messages) {
      // Process message
      // ...
    }
  }
}
```

## Core Concepts

> Fundamental concepts and principles for game development.

### Game Entities and Components

```typescript
// ECS pattern
class Entity {
  id: number;
  components: Map<string, any> = new Map();

  addComponent<T>(key: string, value: T): void {
    this.components.set(key, value);
  }

  getComponent<T>(key: string): T | undefined {
    return this.components.get(key) as T;
  }

  hasComponent(key: string): boolean {
    return this.components.has(key);
  }
}
```

### Game Loop

```typescript
// Game loop architecture
class GameLoop {
  private running: boolean = false;
  private frameRate: number = 60;
  private delta: number = 0;
  private accumulator: number = 0;
  private lastTime: number = 0;

  start(): void {
    this.running = true;
    requestAnimationFrame(this.fixedUpdate.bind(this));
  }

  private fixedUpdate(): void {
    const now = Date.now();
    this.delta = now - this.lastTime;
    this.accumulator += this.delta;

    // Process input
    // ...

    while (this.accumulator >= 16) {
      this.update(16);
      this.accumulator -= 16;
    }

    this.render();

    if (this.running) {
      this.lastTime = now;
      requestAnimationFrame(this.fixedUpdate.bind(this));
    }
  }

  private update(delta: number): void {
    // Update game state
    // ...
  }

  private render(): void {
    // Render game
    // ...
  }
}
```

### Physics Simulation

```typescript
// Physics simulation
class PhysicsEngine {
  private world: World = new World();
  private gravity: Vec2 = new Vec2(0, 1000);
  private fixedStep: number = 1 / 60;

  update(delta: number): void {
    const iterations = Math.max(1, Math.floor(delta / this.fixedStep));
    const step = delta / iterations;

    for (let i = 0; i < iterations; i++) {
      // Apply gravity
      this.world.gravity = this.gravity;

      // Simulate physics
      for (const body of this.world.bodies) {
        body.update(step);
      }

      // Solve constraints
      for (const constraint of this.world.constraints) {
        constraint.solve(step);
      }
    }
  }

  applyForce(bodyId: string, force: Vec2, point: Vec2): void {
    const body = this.world.getBody(bodyId);
    if (body) {
      body.applyForce(force, point);
    }
  }
}
```

### AI Behavior

```typescript
// AI behavior
interface AITrait {
  update(entity: Entity, deltaTime: number): void;
}

class MoveAI implements AITrait {
  private target: Vec2 | null = null;
  private speed: number = 150;

  update(entity: Entity, deltaTime: number): void {
    if (!this.target) {
      return;
    }

    const position = entity.getComponent(Position);
    const direction = Vec2.sub(this.target, position).normalized();
    const velocity = Vec2.scale(direction, this.speed);

    position.add(velocity * deltaTime);
  }
}
```

### Network Message Format

```typescript
// Network message format
interface NetworkMessage {
  id: string;
  sequence: number;
  timestamp: number;
  data: Buffer;
}

class NetworkSystem {
  private messages: Array<NetworkMessage> = [];

  send(message: NetworkMessage): void {
    this.messages.push(message);
  }

  receive(data: Buffer): void {
    const buffer = Buffer.from(data);
    const id = buffer.readUTF8();
    const sequence = buffer.readUInt32BE();
    const timestamp = buffer.readDoubleBE();
    const data = buffer.slice(buffer.offset, buffer.byteLength);

    const existing = this.messages.find(m => m.id === id && m.sequence === sequence);
    if (existing) {
      existing.data = Buffer.concat([existing.data, data]);
      return;
    }

    this.messages.push({ id, sequence, timestamp, data });
  }
}
```

## Key Patterns & Architectures

> Common patterns and architectures for game development.

### Entity-Component-System (ECS)

```typescript
// ECS pattern
class Entity {
  id: number;
  components: Map<string, any> = new Map();

  addComponent<T>(key: string, value: T): void {
    this.components.set(key, value);
  }

  getComponent<T>(key: string): T | undefined {
    return this.components.get(key) as T;
  }

  hasComponent(key: string): boolean {
    return this.components.has(key);
  }
}

class System {
  update(delta: number): void {
    // Process components
    // ...
  }
}

class GameLoop {
  private systems: Array<{ update: (delta: number) => void }> = [];
  private entities: Map<number, Entity> = new Map();

  addSystem(system: { update: (delta: number) => void }): void {
    this.systems.push(system);
  }

  start(): void {
    const frameRate = 60;
    const interval = 1000 / frameRate;
    let lastTime = performance.now();
    let accumulator = 0;

    function fixedUpdate(): void {
      const now = performance.now();
      const delta = now - lastTime;
      lastTime = now;
      accumulator += delta;

      while (accumulator >= interval) {
        for (const system of this.systems) {
          system.update(interval);
        }
        accumulator -= interval;
      }

      if (accumulator > 0) {
        requestAnimationFrame(fixedUpdate.bind(this));
      }
    }

    fixedUpdate();
  }
}
```

### State Machine

```typescript
// State machine pattern
enum GameState {
  Title,
  Menu,
  Game,
  GameOver
}

interface StateContext {
  game: Game;
  state: GameState;
}

class StateMachine {
  private context: StateContext = { game: new Game(), state: GameState.Title };

  transition(state: GameState): void {
    const nextState = this.context.game.getState(state);
    if (nextState) {
      this.context.state = state;
      nextState.enter(this.context);
    }
  }

  update(delta: number): void {
    const state = this.context.state;
    const stateMachine = this.context.game.getStateMachine();
    stateMachine.update(state, delta);
  }

  render(context: CanvasRenderingContext2D): void {
    const state = this.context.state;
    const stateMachine = this.context.game.getStateMachine();
    stateMachine.render(state, context);
  }
}
```

### Finite State Machine (FSM)

```typescript
// FSM pattern
interface State {
  name: string;
  onEnter(context: any): void;
  onUpdate(context: any, deltaTime: number): void;
  onRender(context: any, deltaTime: number): void;
  onExit(context: any): void;
}

class StateMachine {
  private states: Map<string, State> = new Map();
  private currentState: State | null = null;

  addState(state: State): void {
    this.states.set(state.name, state);
  }

  transition(stateName: string): void {
    const nextState = this.states.get(stateName);
    if (nextState) {
      if (this.currentState) {
        this.currentState.onExit(this.context);
      }
      this.currentState = nextState;
      this.currentState.onEnter(this.context);
    }
  }

  update(deltaTime: number): void {
    if (this.currentState) {
      this.currentState onUpdate(this.context, deltaTime);
    }
  }

  render(deltaTime: number): void {
    if (this.currentState) {
      this.currentState.onRender(this.context, deltaTime);
    }
  }
}
```

### Event-Driven Architecture

```typescript
// Event-driven architecture
interface Event {
  type: string;
  timestamp: number;
  data: Record<string, any>;
}

class EventBus {
  private handlers: Map<string, Array<(event: Event) => void>> = new Map();
  private events: Array<Event> = [];

  subscribe(type: string, handler: (event: Event) => void): void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, []);
    }
    this.handlers.get(type)!.push(handler);
  }

  publish(event: Event): void {
    this.events.push(event);

    const handlers = this.handlers.get(event.type) || [];
    for (const handler of handlers) {
      handler(event);
    }
  }

  update(delta: number): void {
    // Process events
    for (const event of this.events) {
      // Process event
      // ...
    }
  }
}
```

## Implementation Guidance

> Practical advice for implementing game systems and engines.

### Game Loop

```typescript
// Game loop architecture
class GameLoop {
  private running: boolean = false;
  private frameRate: number = 60;
  private delta: number = 0;
  private accumulator: number = 0;
  private lastTime: number = 0;

  start(): void {
    this.running = true;
    requestAnimationFrame(this.fixedUpdate.bind(this));
  }

  private fixedUpdate(): void {
    const now = Date.now();
    this.delta = now - this.lastTime;
    this.accumulator += this.delta;

    // Process input
    // ...

    while (this.accumulator >= 16) {
      this.update(16);
      this.accumulator -= 16;
    }

    this.render();

    if (this.running) {
      this.lastTime = now;
      requestAnimationFrame(this.fixedUpdate.bind(this));
    }
  }

  private update(delta: number): void {
    // Update game state
    // ...
  }

  private render(): void {
    // Render game
    // ...
  }
}
```

### Physics Engine

```typescript
// Physics engine
class PhysicsEngine {
  private world: World = new World();
  private gravity: Vec2 = new Vec2(0, 1000);
  private fixedStep: number = 1 / 60;

  update(delta: number): void {
    const iterations = Math.max(1, Math.floor(delta / this.fixedStep));
    const step = delta / iterations;

    for (let i = 0; i < iterations; i++) {
      // Apply gravity
      this.world.gravity = this.gravity;

      // Simulate physics
      for (const body of this.world.bodies) {
        body.update(step);
      }

      // Solve constraints
      for (const constraint of this.world.constraints) {
        constraint.solve(step);
      }
    }
  }

  applyForce(bodyId: string, force: Vec2, point: Vec2): void {
    const body = this.world.getBody(bodyId);
    if (body) {
      body.applyForce(force, point);
    }
  }
}
```

### AI Behavior

```typescript
// AI behavior
interface AITrait {
  update(entity: Entity, deltaTime: number): void;
}

class MoveAI implements AITrait {
  private target: Vec2 | null = null;
  private speed: number = 150;

  update(entity: Entity, deltaTime: number): void {
    if (!this.target) {
      return;
    }

    const position = entity.getComponent(Position);
    const direction = Vec2.sub(this.target, position).normalized();
    const velocity = Vec2.scale(direction, this.speed);

    position.add(velocity * deltaTime);
  }
}
```

### Network System

```typescript
// Network system
interface NetworkMessage {
  id: string;
  sequence: number;
  timestamp: number;
  data: Buffer;
}

class NetworkSystem {
  private messages: Array<NetworkMessage> = [];

  send(message: NetworkMessage): void {
    this.messages.push(message);
  }

  receive(data: Buffer): void {
    const buffer = Buffer.from(data);
    const id = buffer.readUTF8();
    const sequence = buffer.readUInt32BE();
    const timestamp = buffer.readDoubleBE();
    const data = buffer.slice(buffer.offset, buffer.byteLength);

    const existing = this.messages.find(m => m.id === id && m.sequence === sequence);
    if (existing) {
      existing.data = Buffer.concat([existing.data, data]);
      return;
    }

    this.messages.push({ id, sequence, timestamp, data });
  }
}
```

## Common Pitfalls

> Common issues and pitfalls to avoid in game development.

### Fixed vs Variable Timestep

```typescript
// Fixed timestep architecture
class GameLoop {
  private fixedStep: number = 1 / 60;
  private accumulator: number = 0;
  private lastTime: number = 0;

  start(): void {
    requestAnimationFrame(this.fixedUpdate.bind(this));
  }

  private fixedUpdate(): void {
    const now = performance.now();
    this.accumulator += now - this.lastTime;
    this.lastTime = now;

    while (this.accumulator >= this.fixedStep) {
      this.update(this.fixedStep);
      this.accumulator -= this.fixedStep;
    }

    this.render();
    if (this.running) {
      requestAnimationFrame(this.fixedUpdate.bind(this));
    }
  }

  private update(delta: number): void {
    // Update game state
    // ...
  }

  private render(): void {
    // Render game
    // ...
  }
}
```

### Input Handling

```typescript
// Input system
class InputSystem {
  private keyDown: Set<string> = new Set();
  private keyUp: Set<string> = new Set();
  private keyState: Record<string, boolean> = {};

  handleKeyPress(event: KeyboardEvent): void {
    const key =
