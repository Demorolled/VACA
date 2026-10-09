# 🎬 Media, Entertainment & Social Platforms

> Reference for building media and social platforms — video streaming, social feeds, content moderation, messaging, and creator economy.
> Extracted from The Programming Bible's Media, Entertainment & Social level.

---

## 1. Media Platform Architecture

### Video Streaming Stack

```
┌──────────────────────────────────────────────────┐
│                 CLIENT (Player)                    │
│  HLS.js / Shaka Player / ExoPlayer / AVPlayer     │
│  Adaptive Bitrate (ABR) — quality ladder           │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│            CONTENT DELIVERY (CDN)                │
│  CloudFront / Cloudflare / Fastly / Akamai       │
│  Edge caching, regional POPs                     │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              ORIGIN / PACKAGER                   │
│  Unified Origin / Nimble Streamer / Wowza       │
│  HLS (m3u8) + DASH (mpd) packaging              │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              ENCODING / TRANSCODER               │
│  FFmpeg / AWS Elemental / Bitmovin               │
│  ABR ladder: 144p → 4K, codec: H.264/HEVC/AV1   │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│                 SOURCE / STORAGE                 │
│  S3 / GCS / local NAS — original master files    │
└──────────────────────────────────────────────────┘
```

### Adaptive Bitrate Ladder

| Label | Resolution | Bitrate (video) | Bitrate (audio) | Codec |
|---|---|---|---|---|
| 144p | 256×144 | 150 Kbps | 64 Kbps | H.264 |
| 360p | 640×360 | 800 Kbps | 96 Kbps | H.264 |
| 720p | 1280×720 | 2.5 Mbps | 128 Kbps | H.264 |
| 1080p | 1920×1080 | 5 Mbps | 192 Kbps | H.264/HEVC |
| 4K | 3840×2160 | 15 Mbps | 192 Kbps | HEVC/AV1 |

---

## 2. Social Feed Architecture

### Feed Generation Patterns

| Pattern | Latency | Write Cost | Read Cost | Example |
|---|---|---|---|---|
| **Fan-out-on-write** | Low read | High write | Low | Twitter (pre-2016) |
| **Fan-out-on-read** | High read | Low write | High | Reddit, Hacker News |
| **Hybrid fan-out** | Medium | Medium | Medium | Instagram, modern Twitter |
| **Pull-based** | High | None | Highest | RSS readers |

### Timeline Service

```typescript
// Hybrid feed — fan-out to active followers, pull for inactive
interface FeedItem {
    id: string;
    authorId: string;
    type: 'post' | 'share' | 'like' | 'comment';
    content: string;
    timestamp: number;
    metadata: Record<string, unknown>;
}

class TimelineService {
    private readonly ACTIVE_THRESHOLD = 7 * 24 * 60 * 60 * 1000; // 7 days
    private readonly FEED_SIZE = 500;

    constructor(
        private redis: RedisClient,
        private db: Database,
    ) {}

    async publishPost(authorId: string, post: FeedItem): Promise<void> {
        // Get active followers (logged in within 7 days)
        const activeFollowers = await this.db.findActiveFollowers(
            authorId, this.ACTIVE_THRESHOLD
        );

        // Fan-out to active followers' timelines
        const pipeline = this.redis.pipeline();
        for (const followerId of activeFollowers) {
            pipeline.lpush(`feed:${followerId}`, JSON.stringify(post));
            pipeline.ltrim(`feed:${followerId}`, 0, this.FEED_SIZE);
        }
        await pipeline.exec();

        // Store in author's timeline for pull-based readers
        await this.redis.lpush(`author:${authorId}`, JSON.stringify(post));
        await this.redis.ltrim(`author:${authorId}`, 0, this.FEED_SIZE);
    }

    async getTimeline(
        userId: string,
        cursor?: string,
        limit: number = 20,
    ): Promise<{ items: FeedItem[]; nextCursor?: string }> {
        // Try cache first
        const cached = await this.redis.lrange(`feed:${userId}`, 0, limit);
        if (cached.length > 0) {
            return {
                items: cached.map(c => JSON.parse(c)),
                nextCursor: cached.length >= limit ? 'more' : undefined,
            };
        }

        // Cache miss — pull from followed authors
        const followed = await this.db.findFollowed(userId);
        const posts = await this.db.findRecentPosts(followed, limit);

        // Warm cache
        await this.redis.lpush(
            `feed:${userId}`,
            ...posts.map(p => JSON.stringify(p))
        );

        return { items: posts };
    }
}
```

---

## 3. Content Moderation

### Moderation Pipeline

```
User Generated Content
    │
    ▼
┌────────────────────┐
│ Automated Filters   │  ← Regex, blocklist, pattern matching
└──────┬─────────────┘
       │
       ▼
┌────────────────────┐
│ ML Classifiers     │  ← NSFW, toxicity, spam detection
└──────┬─────────────┘
       │
       ▼
┌────────────────────┐
│ Hash Matching      │  ← PhotoDNA, CSAM hash database
└──────┬─────────────┘
       │
       ▼
┌────────────────────┐
│ Human Review Queue │  ← Escalated items for manual review
└──────┬─────────────┘
       │
       ▼
┌────────────────────┐
│ Action Taken       │  ← Allow, flag, remove, suspend, ban
└────────────────────┘
```

### Moderation Service

```typescript
// Content moderation service
interface ModerationResult {
    approved: boolean;
    score: number;
    labels: string[];
    reviewedBy: 'auto' | 'human';
    action: 'allow' | 'flag' | 'remove';
}

class ContentModerator {
    constructor(
        private toxicityClassifier: MLModel,
        private imageAnalyzer: ImageAnalysis,
        private blocklist: Set<string>,
    ) {}

    async moderate(text?: string, imageUrl?: string): Promise<ModerationResult> {
        const labels: string[] = [];
        let maxScore = 0;

        // 1. Check blocklist
        if (text) {
            for (const blocked of this.blocklist) {
                if (text.toLowerCase().includes(blocked)) {
                    return {
                        approved: false,
                        score: 1.0,
                        labels: ['blocklist_match'],
                        reviewedBy: 'auto',
                        action: 'remove',
                    };
                }
            }
        }

        // 2. Run ML classifiers
        if (text) {
            const toxicity = await this.toxicityClassifier.predict(text);
            if (toxicity.score > 0.8) {
                labels.push('toxic');
                maxScore = Math.max(maxScore, toxicity.score);
            }
            if (toxicity.labels.includes('spam') && toxicity.score > 0.6) {
                labels.push('spam');
                maxScore = Math.max(maxScore, toxicity.score);
            }
        }

        // 3. Image analysis
        if (imageUrl) {
            const imageResult = await this.imageAnalyzer.analyze(imageUrl);
            for (const label of imageResult.labels) {
                if (label.confidence > 0.9) {
                    labels.push(label.name);
                    maxScore = Math.max(maxScore, label.confidence);
                }
            }
        }

        // 4. Determine action
        if (maxScore > 0.95) {
            return { approved: false, score: maxScore, labels,
                     reviewedBy: 'auto', action: 'remove' };
        }
        if (maxScore > 0.7) {
            return { approved: false, score: maxScore, labels,
                     reviewedBy: 'auto', action: 'flag' };
        }

        return { approved: true, score: maxScore, labels,
                 reviewedBy: 'auto', action: 'allow' };
    }
}
```

---

## 4. Messaging & Chat Architecture

### Chat System Design

```
┌─────────────────────────────────────────────┐
│               API Gateway                    │
├─────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ WebSocket│  │  REST    │  │ Webhook  │ │
│  │ Gateway  │  │  API     │  │ Outgoing │ │
│  └────┬─────┘  └────┬─────┘  └──────────┘ │
└───────┼─────────────┼──────────────────────┘
        │             │
┌───────▼─────────────▼──────────────────────┐
│              Message Service               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ Send     │  │ Receive  │  │ History  │ │
│  │ Message  │  │ Message  │  │ Query    │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
└───────┼─────────────┼──────────────┼───────┘
        │             │              │
┌───────▼─────────────▼──────────────▼───────┐
│           Data Layer                       │
│  Redis (presence, typing)                  │
│  Cassandra (message store)                 │
│  Postgres (user metadata, sync tokens)     │
└────────────────────────────────────────────┘
```

### Real-Time Messaging

```typescript
// WebSocket-based messaging
import WebSocket from 'ws';

class ChatServer {
    private connections = new Map<string, WebSocket[]>();
    private readonly MAX_MESSAGE_LENGTH = 4096;

    handleConnection(ws: WebSocket, userId: string): void {
        const conns = this.connections.get(userId) || [];
        conns.push(ws);
        this.connections.set(userId, conns);

        ws.on('message', async (data) => {
            try {
                const message = JSON.parse(data.toString());

                // Validate message
                if (!message.content || message.content.length > this.MAX_MESSAGE_LENGTH) {
                    ws.send(JSON.stringify({ error: 'Invalid message' }));
                    return;
                }

                const enriched = {
                    id: crypto.randomUUID(),
                    from: userId,
                    content: message.content,
                    timestamp: new Date().toISOString(),
                    type: message.type || 'text',
                };

                // Store in database
                await this.storeMessage(enriched);

                // Deliver to recipient(s)
                if (message.to) {
                    this.deliverToUser(message.to, enriched);
                }

                // Confirm delivery to sender
                ws.send(JSON.stringify({ type: 'ack', id: enriched.id }));
            } catch (err) {
                ws.send(JSON.stringify({ error: 'Invalid message format' }));
            }
        });

        ws.on('close', () => {
            const filtered = this.connections.get(userId)?.filter(c => c !== ws);
            if (filtered?.length === 0) {
                this.connections.delete(userId);
                this.broadcastPresence(userId, 'offline');
            } else if (filtered) {
                this.connections.set(userId, filtered);
            }
        });

        // Send presence
        this.broadcastPresence(userId, 'online');
    }
}
```

---

## 5. Creator Economy Platform

### Platform Models

| Model | Description | Revenue | Example |
|---|---|---|---|
| **Subscriptions** | Monthly/yearly recurring | 70-80% creator split | Patreon, Substack |
| **Ad Revenue Share** | Pre-roll, mid-roll, display ads | 55% creator (YouTube) | YouTube, Twitch |
| **Tips/Digital Goods** | One-time payments, virtual gifts | Variable | Twitch Bits, TikTok |
| **Pay-Per-View** | One-time access to content | 80% creator | Vimeo OTT |
| **Affiliate** | Commission on sales | 5-30% commission | Amazon Associates |

---

## Quick Reference: Media & Social by Node Type

| Node Type | Media/Social Mapping |
|---|---|
| **Input** | Media upload, user content submission, WebSocket connection, webhook receiver |
| **Logic** | Feed ranking algorithm, moderation pipeline, transcoding orchestration, recommendation |
| **Database** | Message store (Cassandra), media metadata (Postgres), feed cache (Redis), blob storage |
| **UI** | Video player, feed viewer, chat interface, moderation dashboard |
| **API** | Content ingestion API, streaming manifest endpoint, GraphQL feed query, webhook delivery |

---

*For deeper media concepts, see Bible levels `40-media-entertainment-social/`, `21-digital-content-media/`, `09-game-engines/`, and `35-realtime-collaboration/`.*
