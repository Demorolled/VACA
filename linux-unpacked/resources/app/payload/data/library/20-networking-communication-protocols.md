# 🌐 Networking & Communication Protocols

> Reference for networking and communication patterns — TCP/IP stack, HTTP, WebRTC, protocol design, and real-time communication.
> Extracted from The Programming Bible's Networking Deep and Protocols levels.

---

## 1. Network Models

### OSI vs TCP/IP Model

```
OSI Model                    TCP/IP Model        Protocol Data Unit
─────────────────────        ─────────────        ─────────────────
7. Application       ┐
6. Presentation      ├──── Application           Data / Message
5. Session           ┘
4. Transport         ──────── Transport          Segment (TCP) / Datagram (UDP)
3. Network           ──────── Internet           Packet
2. Data Link         ──────── Link               Frame
1. Physical          ──────── Physical           Bits
```

### Data Encapsulation

```
[HTTP Request Body]                          ← Application
[TCP Header][HTTP]                            ← Transport
[IP Header][TCP][HTTP]                        ← Network
[Ethernet Header][IP][TCP][HTTP][Ethernet CRC] ← Data Link
```

---

## 2. Transport Layer Protocols

| Protocol | Type | Features | Use Case |
|---|---|---|---|
| **TCP** (RFC 9293) | Connection-oriented | Reliable, ordered, flow control, congestion control | HTTP, SMTP, SSH |
| **UDP** (RFC 768) | Connectionless | Unreliable, unordered, low overhead | DNS, VoIP, gaming |
| **QUIC** (RFC 9000) | UDP-based | 0-RTT, multiplexed, built-in TLS 1.3, connection migration | HTTP/3 |
| **SCTP** (RFC 4960) | Message-oriented | Multihoming, multistreaming, partial reliability | Telephony signaling |
| **WebRTC** | UDP-based | P2P, DTLS/SRTP encryption, ICE/STUN/TURN | Video calls, data channels |

### TCP Connection Lifecycle

```
CLIENT                          SERVER
  │                               │
  │────── SYN (seq=x) ──────────▶│  LISTEN
  │◀───── SYN+ACK (seq=y, ack=x+1)──│  SYN-RCVD
  │────── ACK (seq=x+1, ack=y+1)──▶│  ESTABLISHED
  │                               │
  │◀══════ Data Exchange ═══════▶│
  │                               │
  │────── FIN ──────────────────▶│  CLOSE-WAIT
  │◀───── ACK ───────────────────│
  │◀───── FIN ───────────────────│
  │────── ACK ──────────────────▶│  CLOSED
```

### TCP Congestion Control

| Algorithm | Characteristics |
|---|---|
| **CUBIC** | Default Linux — scales with BDP, fair in high-BW networks |
| **BBR** | Model-based — uses bandwidth/RTT estimation, not loss |
| **NewReno** | Classic — additive increase, multiplicative decrease (AIMD) |
| **DCTCP** | Data center — uses ECN for low-latency |

### TCP Server Pattern (Node.js)

```typescript
import net from 'net';

const server = net.createServer((socket) => {
  const clientAddr = `${socket.remoteAddress}:${socket.remotePort}`;
  console.log(`Client connected: ${clientAddr}`);

  // Buffer for incomplete messages
  let buffer = Buffer.alloc(0);

  socket.on('data', (data: Buffer) => {
    buffer = Buffer.concat([buffer, data]);

    // Process complete messages (length-prefixed protocol)
    while (buffer.length >= 4) {
      const msgLength = buffer.readUInt32BE(0);
      if (buffer.length < 4 + msgLength) break; // Wait for more data

      const message = buffer.slice(4, 4 + msgLength);
      buffer = buffer.slice(4 + msgLength);

      handleMessage(socket, message);
    }
  });

  socket.on('end', () => {
    console.log(`Client disconnected: ${clientAddr}`);
  });

  socket.on('error', (err) => {
    console.error(`Socket error: ${err.message}`);
  });
});

server.listen(8080, () => {
  console.log('TCP server listening on port 8080');
});
```

---

## 3. HTTP Protocol Evolution

| Version | Year | Key Innovation | Transport |
|---|---|---|---|
| **HTTP/1.0** | 1996 | Simple request-response | TCP per request |
| **HTTP/1.1** | 1997 | Keep-alive, chunked encoding, caching | TCP persistent |
| **HTTP/2** | 2015 | Binary framing, multiplexing, server push, HPACK | TCP multiplexed |
| **HTTP/3** | 2022 | QUIC-based, 0-RTT, no TCP HOL blocking | QUIC/UDP |

### HTTP/2 Binary Framing

```
Frame Format (9-byte header):
┌──────────────────────────────────────┐
│ Length (24 bits)                      │
├──────────────────┬───────────────────┤
│ Type (8 bits)    │ Flags (8 bits)    │
├──────────────────┴───────────────────┤
│ Stream Identifier (31 bits)           │
├──────────────────────────────────────┤
│ Frame Payload (variable)              │
└──────────────────────────────────────┘

Frame Types: HEADERS, DATA, PRIORITY, SETTINGS, PUSH_PROMISE, PING, GOAWAY
```

### HTTP/3 QUIC Advantages

```typescript
// QUIC (HTTP/3) client using Node.js built-in (Node 21+)
import { fetch } from 'undici'; // or use node:http

async function http3Request(url: string): Promise<void> {
  try {
    const response = await fetch(url, {
      // H3 is negotiated automatically via Alt-Svc or DNS
    });
    console.log(`Status: ${response.status}`);
    console.log(`Protocol: ${response.httpVersion}`); // Should be 'h3'
  } catch (err) {
    console.error(`HTTP/3 request failed: ${err}`);
  }
}
```

### HTTP Client with Retry & Timeout

```typescript
interface HTTPOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
  timeout?: number;
  retries?: number;
  backoff?: number;
}

async function httpFetch(url: string, options: HTTPOptions = {}): Promise<Response> {
  const timeout = options.timeout ?? 10000;
  const retries = options.retries ?? 3;
  const backoff = options.backoff ?? 1000;

  for (let attempt = 1; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        method: options.method ?? 'GET',
        headers: options.headers,
        body: options.body,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) return response;

      // Retry on 5xx server errors
      if (response.status >= 500 && attempt < retries) {
        await sleep(backoff * Math.pow(2, attempt - 1));
        continue;
      }

      return response; // Return 4xx errors immediately
    } catch (err) {
      clearTimeout(timeoutId);
      if (attempt === retries) throw err;
      await sleep(backoff * Math.pow(2, attempt - 1));
    }
  }

  throw new Error('All retries exhausted');
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
```

---

## 4. WebRTC for Real-Time Communication

### WebRTC Architecture

```
Application
    │
├── RTCPeerConnection   ← Session management, ICE, DTLS
├── MediaStream         ← Camera, microphone, screen share
└── RTCDataChannel      ← Peer-to-peer data (SCTP over DTLS)
    │
├── DTLS/SRTP           ← Encryption
├── ICE/STUN/TURN       ← NAT traversal
└── UDP/TCP             ← Transport
```

### WebRTC Signaling & Peer Connection

```typescript
// Signaling (must use WebSocket or similar)
interface SignalingMessage {
  type: 'offer' | 'answer' | 'ice-candidate';
  data: unknown;
}

class WebRTCClient {
  private pc: RTCPeerConnection;
  private signaling: WebSocket;
  private dataChannel: RTCDataChannel | null = null;

  constructor(signalingUrl: string, stunServers: string[] = ['stun:stun.l.google.com:19302']) {
    this.pc = new RTCPeerConnection({
      iceServers: [{ urls: stunServers }],
    });

    this.signaling = new WebSocket(signalingUrl);
    this.setupSignaling();
    this.setupPeerConnection();
  }

  private setupPeerConnection(): void {
    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        this.signaling.send(JSON.stringify({
          type: 'ice-candidate',
          data: event.candidate.toJSON(),
        }));
      }
    };

    this.pc.ontrack = (event) => {
      const video = document.createElement('video');
      video.srcObject = event.streams[0];
      video.autoplay = true;
      document.body.appendChild(video);
    };
  }

  private setupSignaling(): void {
    this.signaling.onmessage = async (event) => {
      const msg: SignalingMessage = JSON.parse(event.data);

      switch (msg.type) {
        case 'offer':
          await this.pc.setRemoteDescription(new RTCSessionDescription(msg.data as any));
          const answer = await this.pc.createAnswer();
          await this.pc.setLocalDescription(answer);
          this.signaling.send(JSON.stringify({ type: 'answer', data: answer }));
          break;

        case 'answer':
          await this.pc.setRemoteDescription(new RTCSessionDescription(msg.data as any));
          break;

        case 'ice-candidate':
          await this.pc.addIceCandidate(new RTCIceCandidate(msg.data as any));
          break;
      }
    };
  }

  async createAndSendOffer(): Promise<void> {
    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);
    this.signaling.send(JSON.stringify({ type: 'offer', data: offer }));
  }

  createDataChannel(label: string): RTCDataChannel {
    this.dataChannel = this.pc.createDataChannel(label);
    return this.dataChannel;
  }

  async addLocalStream(stream: MediaStream): Promise<void> {
    for (const track of stream.getTracks()) {
      this.pc.addTrack(track, stream);
    }
  }
}
```

---

## 5. DNS & Name Resolution

### DNS Record Types

| Record | Value | Purpose |
|---|---|---|
| **A** | IPv4 address | Host → IP |
| **AAAA** | IPv6 address | Host → IPv6 |
| **CNAME** | Canonical name | Alias → real hostname |
| **MX** | Mail server + priority | Email delivery routing |
| **TXT** | Text data | SPF, DKIM, verification |
| **NS** | Nameserver | Delegation |
| **SRV** | Service location | Service discovery |

### DNS Resolution Pattern

```typescript
import dns from 'dns/promises';

async function resolveWithFallback(hostname: string): Promise<string> {
  try {
    // Try IPv6 first
    const addresses = await dns.resolve6(hostname);
    return addresses[0];
  } catch {
    // Fall back to IPv4
    const addresses = await dns.resolve4(hostname);
    return addresses[0];
  }
}

// DNS-over-HTTPS (DoH) for secure resolution
async function resolveDoH(hostname: string): Promise<string[]> {
  const response = await fetch(`https://cloudflare-dns.com/dns-query?name=${hostname}&type=A`, {
    headers: { 'Accept': 'application/dns-json' },
  });
  const data = await response.json();
  return data.Answer?.map((a: any) => a.data) ?? [];
}
```

---

## 6. WebSocket Pattern

```typescript
// WebSocket server with reconnection handling
class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private handlers: Map<string, ((data: unknown) => void)[]> = new Map();

  constructor(url: string) {
    this.url = url;
    this.connect();
  }

  private connect(): void {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000; // Reset on successful connection
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        const handlers = this.handlers.get(msg.type) ?? [];
        for (const handler of handlers) handler(msg.data);
      } catch { /* ignore malformed messages */ }
    };

    this.ws.onclose = () => {
      setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
    };

    this.ws.onerror = () => {
      this.ws?.close(); // Trigger reconnect
    };
  }

  on(type: string, handler: (data: unknown) => void): void {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type)!.push(handler);
  }

  send(type: string, data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    }
  }
}
```

---

## Quick Reference: Networking by Node Type

| Node Type | Networking Mapping |
|---|---|
| **Input** | HTTP request parsing, WebSocket message handling, DNS lookup |
| **Logic** | Protocol implementation, message routing, connection state machine |
| **Database** | Connection pooling, query over network, RPC calls |
| **UI** | WebSocket updates, streaming responses, real-time indicators |
| **API** | REST/GraphQL endpoints, gRPC services, WebRTC signaling |

---

*For deeper networking concepts, see Bible levels `13-networking-deep/`, `14-protocols/`, and `04-web-apps/` — TCP/IP internals, HTTP/3, WebRTC, BGP, DNS, and secure protocols.*
