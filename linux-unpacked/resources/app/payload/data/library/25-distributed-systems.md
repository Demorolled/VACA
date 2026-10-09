# 🔄 Distributed Systems

> Reference for building distributed systems — consensus algorithms, message queues, stream processing, CAP theorem, and distributed storage.
> Extracted from The Programming Bible's Distributed Systems level.

---

## 1. Distributed System Fundamentals

### Motivations

| Motivation | Description |
|---|---|
| **Scalability** | Horizontal scaling beyond a single machine |
| **Fault Tolerance** | Replication across independent failure domains |
| **Low Latency** | Geo-distributed compute closest to users |
| **Geo-Distribution** | Data residency, DR, regulatory compliance |
| **Cost Efficiency** | Commodity hardware over expensive mainframes |

### Key Challenges

| Challenge | Implication |
|---|---|
| **Partial Failure** | Any component can fail independently — must detect & handle |
| **Network Partitions** | Messages may be lost, delayed, or reordered |
| **Clock Skew** | No guarantee of synchronized clocks across nodes |
| **Coordination** | Consensus is hard — FLP impossibility result |
| **Causality** | Determining order of events across nodes |

### System Models

| Model | Timing | Realism | Algorithm Difficulty |
|---|---|---|---|
| **Synchronous** | Known bounds on time & drift | Unrealistic | Easiest |
| **Asynchronous** | No timing assumptions | Too strict (FLP) | Impossible for consensus |
| **Partially Synchronous** | Eventually synchronous after GST | Most realistic | Standard approach |

---

## 2. The CAP Theorem

```
Consistency (C)              Availability (A)
      ▲                              ▲
       \                            /
        \                          /
         \     CA (impossible)    /
          \                      /
           ─────────────────────
           │     CP or AP      │
           └───────────────────┘
                    │
                    ▼
          Partition Tolerance (P)
```

| Combination | Properties | Examples |
|---|---|---|
| **CP** | Consistent but unavailable during partition | Zookeeper, etcd, MongoDB (default) |
| **AP** | Available but eventually consistent | Cassandra, DynamoDB, Riak |
| **CA** | Cannot exist in distributed systems | — |

**Practical Reality:** You must choose between CP and AP during a network partition. The choice depends on your use case.

---

## 3. Consensus Algorithms

### The Consensus Problem

$N$ processes must agree on a single value, satisfying:

- **Termination** — Every correct process eventually decides
- **Integrity** — No process decides twice
- **Agreement** — No two correct processes decide differently
- **Validity** — If a process decides $v$, then $v$ was proposed by some process

**FLP Impossibility:** In an asynchronous system with one potential crash, no deterministic algorithm can guarantee termination.

**Workaround:** Use failure detectors, randomization, or partial synchrony (GST).

### Paxos (Simplified)

```
Phase 1 (Prepare):
  Proposer → Acceptors: Prepare(N)
  Acceptor → Proposer: Promise(N, lastAcceptedValue)

Phase 2 (Accept):
  Proposer → Acceptors: Accept(N, V)
  Acceptor → Acceptors: Accepted(N, V)

Where N = unique proposal number, V = value
Quorum size = floor(N/2) + 1
```

### Raft Consensus

```
┌────────────────────────────────────────────────┐
│                    Raft Cluster                  │
│                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   │
│  │ Leader   │   │Follower  │   │Follower  │   │
│  │ (active) │──▶│          │──▶│          │   │
│  └──────────┘   └──────────┘   └──────────┘   │
│       │              │              │           │
│   Client         Heartbeats      Heartbeats     │
│   Requests        (AppendEntries)  (AppendEntries)│
└────────────────────────────────────────────────┘
```

### Raft Implementation (Conceptual)

```typescript
type NodeState = 'follower' | 'candidate' | 'leader';

interface LogEntry {
  term: number;
  index: number;
  command: string;
}

interface RaftNode {
  // Persistent state
  currentTerm: number;
  votedFor: string | null;
  log: LogEntry[];

  // Volatile state
  commitIndex: number;
  lastApplied: number;

  // Leader state
  nextIndex: Map<string, number>;
  matchIndex: Map<string, number>;
}

// AppendEntries RPC (heartbeat + log replication)
function handleAppendEntries(
  node: RaftNode,
  leaderTerm: number,
  prevLogIndex: number,
  prevLogTerm: number,
  entries: LogEntry[],
  leaderCommit: number,
): { term: number; success: boolean } {
  // 1. Reply false if term < currentTerm
  if (leaderTerm < node.currentTerm) {
    return { term: node.currentTerm, success: false };
  }

  // 2. If log doesn't contain matching entry at prevLogIndex, reply false
  if (node.log[prevLogIndex]?.term !== prevLogTerm) {
    return { term: node.currentTerm, success: false };
  }

  // 3. Append new entries (delete conflicting entries first)
  for (const entry of entries) {
    if (entry.index < node.log.length) {
      if (node.log[entry.index].term !== entry.term) {
        node.log = node.log.slice(0, entry.index); // Delete conflicts
        node.log.push(entry);
      }
    } else {
      node.log.push(entry);
    }
  }

  // 4. Update commitIndex
  if (leaderCommit > node.commitIndex) {
    node.commitIndex = Math.min(leaderCommit, node.log.length - 1);
  }

  return { term: node.currentTerm, success: true };
}

// Election timeout (150-300ms random)
function startElection(node: RaftNode, nodeId: string, peers: string[]): void {
  node.currentTerm++;
  node.votedFor = nodeId;
  let votesReceived = 1; // Vote for self

  // Request votes from all peers
  for (const peer of peers) {
    const granted = requestVote(peer, {
      term: node.currentTerm,
      candidateId: nodeId,
      lastLogIndex: node.log.length - 1,
      lastLogTerm: node.log[node.log.length - 1]?.term ?? 0,
    });

    if (granted) votesReceived++;
  }

  // Majority check
  if (votesReceived > Math.floor((peers.length + 1) / 2)) {
    becomeLeader(node, nodeId); // This node is now the leader
  }
}
```

---

## 4. Message Queues & Event Streaming

### Communication Models

| Model | Delivery | Use Case |
|---|---|---|
| **Push** | Broker pushes to consumers | Low latency (risks consumer overload) |
| **Pull** | Consumers pull from broker | Consumer-controlled rate |
| **Pub/Sub** | One message, many subscribers | Event broadcasting |
| **Point-to-Point** | One message, one consumer | Work queues |
| **Routing** | Message → specific queue based on key | Topic-based filtering |

### RabbitMQ Pattern

```typescript
// RabbitMQ producer (AMQP)
interface AMQPConnection {
  channel: Channel;
  exchange: string;
}

async function setupRabbitMQ(connectionString: string): Promise<AMQPConnection> {
  const connection = await amqp.connect(connectionString);
  const channel = await connection.createChannel();

  // Declare exchange and queue
  const exchange = 'app.events';
  const queue = 'task.processing';
  const routingKey = 'task.created';

  await channel.assertExchange(exchange, 'topic', { durable: true });
  await channel.assertQueue(queue, { durable: true });
  await channel.bindQueue(queue, exchange, routingKey);

  return { channel, exchange };
}

// Publish with publisher confirmations
async function publishEvent(
  conn: AMQPConnection,
  routingKey: string,
  event: unknown,
): Promise<void> {
  const { channel, exchange } = conn;
  const published = channel.publish(
    exchange,
    routingKey,
    Buffer.from(JSON.stringify(event)),
    { persistent: true, contentType: 'application/json' },
  );

  if (!published) {
    // Channel buffer full — implement backpressure handling
    await new Promise(resolve => channel.once('drain', resolve));
  }
}

// Consume with manual acknowledgment
async function startConsumer(connectionString: string): Promise<void> {
  const connection = await amqp.connect(connectionString);
  const channel = await connection.createChannel();

  await channel.prefetch(5); // Process 5 at a time

  await channel.consume('task.processing', async (msg) => {
    if (!msg) return;

    try {
      const event = JSON.parse(msg.content.toString());
      await processEvent(event);

      channel.ack(msg); // Acknowledge success
    } catch (err) {
      if (isRetryable(err)) {
        channel.nack(msg, false, true); // Requeue for retry
      } else {
        channel.nack(msg, false, false); // Send to DLQ
      }
    }
  });
}
```

### Kafka Pattern

```typescript
// Kafka producer
import { Kafka, Producer, Consumer, EachMessagePayload } from 'kafkajs';

const kafka = new Kafka({
  clientId: 'app-service',
  brokers: ['kafka-1:9092', 'kafka-2:9092', 'kafka-3:9092'],
});

const producer: Producer = kafka.producer();

async function sendKafkaEvent(topic: string, key: string, value: unknown): Promise<void> {
  await producer.send({
    topic,
    messages: [{ key, value: JSON.stringify(value) }],
  });
}

// Kafka consumer with consumer groups
const consumer: Consumer = kafka.consumer({ groupId: 'task-processors' });

async function startKafkaConsumer(): Promise<void> {
  await consumer.connect();
  await consumer.subscribe({ topic: 'app-events', fromBeginning: false });

  await consumer.run({
    autoCommit: true,
    eachBatchAutoResolve: true,
    eachBatch: async ({ batch, resolveOffset, heartbeat }) => {
      for (const message of batch.messages) {
        try {
          const event = JSON.parse(message.value!.toString());
          await processEvent(event);
          resolveOffset(message.offset);
        } catch (err) {
          console.error('Processing failed:', err);
          // In production: send to DLQ
        }
        await heartbeat(); // Keep consumer group membership
      }
    },
  });
}
```

---

## 5. Distributed Storage

### Storage Patterns

| Pattern | Description | Examples |
|---|---|---|
| **Primary-Backup** | One primary handles writes, syncs to backup | Postgres replication |
| **Multi-Primary** | Multiple nodes accept writes | Cassandra, DynamoDB |
| **Quorum-based** | W + R > N for consistency | Cassandra, Riak |
| **Leaderless** | All nodes equal, read-repair | Dynamo-style |
| **Sharding** | Partition data across nodes | Consistent hashing |

### Consistent Hashing

```typescript
// Consistent hashing for distributed storage
import crypto from 'crypto';

class ConsistentHashRing {
  private ring: Map<number, string> = new Map();
  private sortedKeys: number[] = [];
  private virtualNodes: number;

  constructor(private nodes: string[], virtualNodes: number = 100) {
    this.virtualNodes = virtualNodes;
    for (const node of nodes) {
      this.addNode(node);
    }
  }

  private hash(key: string): number {
    const hash = crypto.createHash('md5').update(key).digest();
    return hash.readUInt32BE(0);
  }

  addNode(node: string): void {
    for (let i = 0; i < this.virtualNodes; i++) {
      const hashKey = this.hash(`${node}:${i}`);
      this.ring.set(hashKey, node);
    }
    this.sortedKeys = Array.from(this.ring.keys()).sort((a, b) => a - b);
  }

  removeNode(node: string): void {
    for (let i = 0; i < this.virtualNodes; i++) {
      const hashKey = this.hash(`${node}:${i}`);
      this.ring.delete(hashKey);
    }
    this.sortedKeys = Array.from(this.ring.keys()).sort((a, b) => a - b);
  }

  getNode(key: string): string {
    if (this.sortedKeys.length === 0) throw new Error('No nodes available');

    const hash = this.hash(key);
    // Find first node with hash >= key hash (circular)
    const idx = this.sortedKeys.findIndex(h => h >= hash);
    const nodeHash = idx >= 0 ? this.sortedKeys[idx] : this.sortedKeys[0];
    return this.ring.get(nodeHash)!;
  }

  getReplicationNodes(key: string, replicationFactor: number): string[] {
    const nodes: string[] = [];
    const startHash = this.hash(key);

    for (const ringHash of this.sortedKeys) {
      if (ringHash >= startHash && !nodes.includes(this.ring.get(ringHash)!)) {
        nodes.push(this.ring.get(ringHash)!);
        if (nodes.length >= replicationFactor) break;
      }
    }

    // Wrap around if not enough nodes
    if (nodes.length < replicationFactor) {
      for (const ringHash of this.sortedKeys) {
        if (!nodes.includes(this.ring.get(ringHash)!)) {
          nodes.push(this.ring.get(ringHash)!);
          if (nodes.length >= replicationFactor) break;
        }
      }
    }

    return nodes;
  }
}
```

---

## Quick Reference: Distributed Systems by Node Type

| Node Type | Distributed Systems Mapping |
|---|---|
| **Input** | Load-balanced ingress, request routing, partition detection |
| **Logic** | Consensus algorithm, conflict resolution, idempotency handling |
| **Database** | Distributed store, replication, sharding, quorum reads/writes |
| **UI** | Cluster dashboard, node health display, real-time status |
| **API** | gRPC/RPC between services, event bus producer/consumer, distributed tracing |

---

*For deeper distributed systems concepts, see Bible level `12-distributed-systems/` — consensus, stream processing, storage, message queues, observability, and distributed computing.*
