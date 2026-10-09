# 🔄 Real-Time Collaboration Systems — CRDT, OT, WebSocket & Multiplayer

> Reference sheet for building real-time collaborative applications: operational transformation, conflict-free replicated data types, WebSocket server architecture, multiplayer game servers, WebRTC conferencing, and sync frameworks. Use this when building collaborative editors, real-time messaging, multiplayer games, or live streaming systems.

**Source Bible Level:** 35 — Real-Time Collaboration

---

## 🎯 System Categories & Requirements

| Category | Latency | Consistency | Example | Key Tech |
|---|---|---|---|---|
| **Collaborative Editing** | < 200ms | Eventual (CRDT/OT) | Google Docs, Figma | CRDT, OT, WebSocket |
| **Real-Time Messaging** | < 100ms | Reliable delivery | Slack, Discord | WebSocket, fan-out |
| **Multiplayer Games** | < 50ms | Authoritative | FPS, RTS games | UDP, client prediction |
| **Live Streaming** | < 500ms (HLS) | Ordered segments | Twitch, YouTube | WebRTC, HLS, CMAF |
| **Financial Tick Data** | < 10μs | Total order | Trading feeds | Binary protocols, HW timestamping |
| **IoT Telemetry** | Variable | Best-effort | Sensor networks | MQTT, CoAP |

---

## 🔌 WebSocket Server Architecture

### Connection Lifecycle

```typescript
// WebSocket handshake (upgrade from HTTP)
function handleWebSocketUpgrade(req: IncomingMessage, socket: Duplex): WebSocketConn {
  // 1. Validate key
  const key = req.headers['sec-websocket-key'];
  if (!key) return socket.destroy();

  // 2. Compute accept key (SHA-1 + base64)
  const GUID = '258EAFA5-E914-47DA-95CA-5AB5F5DC26CDB';
  const accept = crypto.createHash('sha1')
    .update(key + GUID)
    .digest('base64');

  // 3. Send upgrade response
  socket.write(
    'HTTP/1.1 101 Switching Protocols\r\n' +
    'Upgrade: websocket\r\n' +
    'Connection: Upgrade\r\n' +
    `Sec-WebSocket-Accept: ${accept}\r\n\r\n`
  );

  return new WebSocketConn(socket);
}

// Frame parsing
class WebSocketFrame {
  fin: boolean;
  opcode: number;  // 1=text, 2=binary, 8=close, 9=ping, 10=pong
  masked: boolean;
  payloadLength: number;
  maskingKey: Buffer;
  payload: Buffer;

  static async read(socket: Duplex): Promise<WebSocketFrame> {
    const firstByte = await readByte(socket);
    const secondByte = await readByte(socket);
    const fin = (firstByte & 0x80) !== 0;
    const opcode = firstByte & 0x0F;
    const masked = (secondByte & 0x80) !== 0;
    let payloadLength = secondByte & 0x7F;

    if (payloadLength === 126) {
      payloadLength = (await readBytes(socket, 2)).readUInt16BE(0);
    } else if (payloadLength === 127) {
      payloadLength = Number((await readBytes(socket, 8)).readBigUInt64BE(0));
    }

    const maskingKey = masked ? await readBytes(socket, 4) : null;
    let payload = await readBytes(socket, payloadLength);

    if (maskingKey) {
      for (let i = 0; i < payload.length; i++) {
        payload[i] ^= maskingKey[i % 4];
      }
    }

    return { fin, opcode, masked, payloadLength, maskingKey, payload };
  }
}
```

### Fan-Out Messaging Server

```typescript
class RealtimeMessagingServer {
  rooms: Map<string, Set<WebSocketConn>> = new Map();
  userSessions: Map<string, WebSocketConn> = new Map();

  onConnect(conn: WebSocketConn, userId: string): void {
    this.userSessions.set(userId, conn);

    conn.on('message', (data) => {
      const msg = JSON.parse(data.toString());

      switch (msg.type) {
        case 'join_room':
          this.joinRoom(conn, msg.roomId);
          break;
        case 'send_message':
          this.broadcastToRoom(msg.roomId, msg.payload, { exclude: conn.id });
          break;
        case 'typing_indicator':
          this.broadcastToRoom(msg.roomId, {
            type: 'typing',
            userId,
            isTyping: msg.isTyping,
          }, { exclude: conn.id });
          break;
      }
    });

    conn.on('close', () => {
      this.userSessions.delete(userId);
      for (const [roomId, members] of this.rooms) {
        members.delete(conn);
        if (members.size === 0) this.rooms.delete(roomId);
      }
    });
  }

  private broadcastToRoom(roomId: string, payload: any, options?: { exclude?: string }): void {
    const members = this.rooms.get(roomId);
    if (!members) return;

    const message = JSON.stringify(payload);
    for (const conn of members) {
      if (options?.exclude && conn.id === options.exclude) continue;
      try {
        conn.send(message);
      } catch {
        members.delete(conn);
      }
    }
  }

  // Horizontal scaling via Redis pub/sub
  private redisClient = new Redis();
  private redisSubscriber = new Redis();

  initializeRedisScale(): void {
    this.redisSubscriber.subscribe('global:events', (err, count) => {
      // Subscribe to cross-node events
    });

    this.redisSubscriber.on('message', (channel, message) => {
      const event = JSON.parse(message);
      // Only broadcast to local connections not already served by origin node
      this.broadcastToRoom(event.roomId, event.payload, { exclude: event.originNodeId });
    });
  }

  private publishToCluster(roomId: string, payload: any): void {
    this.redisClient.publish('global:events', JSON.stringify({
      roomId, payload, originNodeId: this.nodeId,
    }));
  }
}
```

---

## 📝 CRDTs — Conflict-Free Replicated Data Types

CRDTs allow independent replicas to update concurrently and automatically converge without coordination.

### State-Based CRDTs (CvRDT)

```typescript
// G-Counter (Grow-Only Counter)
class GCounter {
  // One entry per replica
  private counts: Map<string, number> = new Map();

  increment(replicaId: string): void {
    const current = this.counts.get(replicaId) ?? 0;
    this.counts.set(replicaId, current + 1);
  }

  value(): number {
    return Array.from(this.counts.values()).reduce((a, b) => a + b, 0);
  }

  // Merge: take max for each replica
  merge(other: GCounter): void {
    for (const [replicaId, count] of other.counts) {
      const current = this.counts.get(replicaId) ?? 0;
      this.counts.set(replicaId, Math.max(current, count));
    }
  }
}

// PN-Counter (Positive-Negative Counter)
class PNCounter {
  private positive: GCounter = new GCounter();
  private negative: GCounter = new GCounter();

  increment(replicaId: string): void { this.positive.increment(replicaId); }
  decrement(replicaId: string): void { this.negative.increment(replicaId); }
  value(): number { return this.positive.value() - this.negative.value(); }

  merge(other: PNCounter): void {
    this.positive.merge(other.positive);
    this.negative.merge(other.negative);
  }
}

// OR-Set (Observed-Remove Set)
class ORSet<T> {
  // Each element tagged with unique add-identifier
  private elements: Map<T, Set<string>> = new Map();  // element → set of tags
  private tombstones: Set<string> = new Set();         // removed tags (for convergence)

  add(element: T, tag: string): void {
    if (!this.elements.has(element)) {
      this.elements.set(element, new Set());
    }
    this.elements.get(element)!.add(tag);
    this.tombstones.delete(tag); // Re-add is possible
  }

  remove(element: T): void {
    const tags = this.elements.get(element);
    if (tags) {
      for (const tag of tags) {
        this.tombstones.add(tag);
      }
      this.elements.delete(element);
    }
  }

  value(): Set<T> {
    const result = new Set<T>();
    for (const [element, tags] of this.elements) {
      const activeTags = new Set(
        Array.from(tags).filter(t => !this.tombstones.has(t))
      );
      if (activeTags.size > 0) {
        result.add(element);
      }
    }
    return result;
  }

  merge(other: ORSet<T>): void {
    for (const [element, tags] of other.elements) {
      if (!this.elements.has(element)) {
        this.elements.set(element, new Set());
      }
      for (const tag of tags) {
        if (!other.tombstones.has(tag)) {
          this.elements.get(element)!.add(tag);
        }
      }
    }
    for (const tombstone of other.tombstones) {
      this.tombstones.add(tombstone);
    }
  }
}

// LWW-Register (Last-Writer-Wins Register)
class LWWRegister<T> {
  private value: T;
  private timestamp: number;  // Wall clock or Lamport timestamp

  assign(newValue: T, ts?: number): void {
    this.value = newValue;
    this.timestamp = ts ?? Date.now();
  }

  merge(other: LWWRegister<T>): void {
    if (other.timestamp > this.timestamp) {
      this.value = other.value;
      this.timestamp = other.timestamp;
    } else if (other.timestamp === this.timestamp) {
      // Tie-break by replica ID or value
      if (JSON.stringify(other.value) > JSON.stringify(this.value)) {
        this.value = other.value;
      }
    }
  }
}
```

### Operational Transformation (OT)

```typescript
// OT for collaborative text editing
type Operation =
  | { type: 'insert'; position: number; chars: string }
  | { type: 'delete'; position: number; length: number }
  | { type: 'retain'; length: number };  // For composing

// Transform function: given two concurrent operations, transform one against the other
function transform(a: Operation, b: Operation): [Operation, Operation] {
  if (a.type === 'insert' && b.type === 'insert') {
    if (a.position < b.position || (a.position === b.position && a.chars < b.chars)) {
      return [a, { ...b, position: b.position + a.chars.length }];
    }
    return [{ ...a, position: a.position + b.chars.length }, b];
  }

  if (a.type === 'insert' && b.type === 'delete') {
    if (a.position <= b.position) {
      return [a, { ...b, position: b.position + a.chars.length }];
    }
    return [
      { ...a, position: a.position - Math.min(a.position - b.position, b.length) },
      b,
    ];
  }

  if (a.type === 'delete' && b.type === 'insert') {
    // Symmetric to above
    const [tb, ta] = transform(b, a);
    return [ta, tb];
  }

  if (a.type === 'delete' && b.type === 'delete') {
    const overlapStart = Math.max(a.position, b.position);
    const overlapEnd = Math.min(a.position + a.length, b.position + b.length);
    const overlap = Math.max(0, overlapEnd - overlapStart);

    return [
      { ...a, length: a.length - overlap, position: a.position + (a.position > b.position ? overlap : 0) },
      { ...b, length: b.length - overlap, position: b.position + (b.position > a.position ? overlap : 0) },
    ];
  }

  return [a, b];
}

// OT Client — connects to server with history buffer
class OTClient {
  document: string = '';
  revision: number = 0;
  pendingOperations: Operation[] = [];  // Unsent operations
  sentOperations: Operation[] = [];     // Sent but unacknowledged
  serverRevision: number = 0;

  localInsert(position: number, chars: string): void {
    const op: Operation = { type: 'insert', position, chars };

    // Apply locally with pending ops transformed
    const transformed = this.pendingOperations.reduce(
      (currentOp, pending) => transform(currentOp, pending)[0],
      op
    );
    this.applyToDocument(transformed);
    this.pendingOperations.push(op);
    this.sendToServer(op);
  }

  onServerAck(op: Operation): void {
    this.sentOperations = this.sentOperations.filter(o => o !== op);
    this.serverRevision++;
  }

  onServerOperation(op: Operation): void {
    // Transform server op against local pending/sent ops
    for (const localOp of [...this.pendingOperations, ...this.sentOperations]) {
      op = transform(op, localOp)[0];
    }
    this.applyToDocument(op);
  }

  private applyToDocument(op: Operation): void {
    switch (op.type) {
      case 'insert':
        this.document = this.document.slice(0, op.position) + op.chars + this.document.slice(op.position);
        break;
      case 'delete':
        this.document = this.document.slice(0, op.position) + this.document.slice(op.position + op.length);
        break;
    }
  }
}
```

---

## 🎮 Multiplayer Game Server Architecture

### Client-Side Prediction & Server Reconciliation

```typescript
interface GameState {
  players: Map<string, PlayerState>;
  entities: Map<string, EntityState>;
  timestamp: number;
}

interface PlayerInput {
  seq: number;
  moveX: number;
  moveY: number;
  jump: boolean;
  shoot: boolean;
  aim: { x: number; y: number };
}

class GameClient {
  predictedState: GameState;
  pendingInputs: PlayerInput[] = [];
  inputSeq = 0;
  serverState: GameState | null = null;

  // Send input every frame
  sendInput(input: PlayerInput): void {
    input.seq = this.inputSeq++;
    this.pendingInputs.push(input);

    // Predictively apply locally
    this.predictedState = this.applyInput(this.predictedState, input);

    // Send to server via UDP
    this.udpSocket.send(encodeInput(input));
  }

  // Receive authoritative state from server
  onServerState(state: GameState): void {
    this.serverState = state;

    // Remove acknowledged inputs
    this.pendingInputs = this.pendingInputs.filter(i => i.seq > state.lastProcessedInput);

    // Start from server state and re-apply unacknowledged inputs
    this.predictedState = state;
    for (const input of this.pendingInputs) {
      this.predictedState = this.applyInput(this.predictedState, input);
    }
  }

  // Interpolation for other players (smooth movement)
  private interpolateEntity(entity: EntityState, renderTimestamp: number): { x: number; y: number } {
    const renderDelay = renderTimestamp - entity.lastUpdate;
    const t = renderDelay / 50;  // Assume 50ms between state updates

    return {
      x: entity.x + entity.velocityX * t * 50,
      y: entity.y + entity.velocityY * t * 50,
    };
  }
}

class GameServer {
  worldState: GameState;
  tickRate = 20;  // 50ms between ticks

  gameLoop(): void {
    setInterval(() => {
      this.processInputs();
      this.updatePhysics();
      this.broadcastState();
    }, 1000 / this.tickRate);
  }

  processInputs(): void {
    for (const [playerId, inputs] of this.inputQueue) {
      for (const input of inputs) {
        this.worldState = this.applyInputAuthoritative(this.worldState, playerId, input);
      }
      this.inputQueue.set(playerId, []);
    }
  }

  broadcastState(): void {
    // Delta-encode state: only send changed entities
    const snapshot = this.createDeltaSnapshot();
    const encoded = encodeSnapshot(snapshot);

    for (const [playerId, conn] of this.connections) {
      // Customize snapshot for each player (fog of war, relevancy)
      conn.send(encoded, { compress: true });
    }
  }
}
```

---

## 📊 Quick Reference: Real-Time Collaboration by Node Type

| Node Type | Relevant Concepts | Implementation Notes |
|---|---|---|
| **Input** | WebSocket frame parsing, OT/CRDT operations, UDP packet handling | Use zero-copy buffer parsing for game inputs; implement frame masking/unmasking per websocket spec |
| **Logic** | CRDT merge logic, OT transform function, state reconciliation | CRDTs for eventual consistency; OT for linear collaborative documents; authoritative server for games |
| **Database** | CRDT database (Automerge, Yjs), Redis pub/sub, fan-out tables | Automerge/Yjs for document sync; Redis for cross-node pub/sub; Cassandra for chat history |
| **UI** | Optimistic updates, ghost cursors, presence indicators, undo/redo | Apply changes optimistically; render foreign cursors with interpolation; implement undo via OT/CRDT history |
| **API** | WebSocket upgrade, room management, presence signaling, WebRTC | Handle upgrade from HTTP; manage room membership with heartbeat; implement STUN/TURN for NAT traversal |
| **Output** | Delta snapshots, binary encoding, video/audio frames via WebRTC | Encode deltas for bandwidth; use VarInt + bitpacking for game state; RTP for media streams |

---

*For deeper technical details on any real-time collaboration concept, see Bible Level 35 — Real-Time Collaboration, including CRDT database internals, WebRTC media server architecture, and multiplayer game networking.*
