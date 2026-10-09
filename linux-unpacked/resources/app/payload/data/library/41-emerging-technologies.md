# 🚀 Emerging Technologies

> Reference for building applications with emerging tech — Web3/blockchain, edge computing, digital twins, AR/VR, spatial computing, and sustainable computing.
> Extracted from The Programming Bible's Emerging Technologies level.

---

## 1. Web3 & Blockchain

### Blockchain Architecture

```
┌──────────────────────────────────────────────────────┐
│                    BLOCKCHAIN                          │
│                                                        │
│  Block N-1           Block N           Block N+1      │
│  ┌──────────┐       ┌──────────┐       ┌──────────┐  │
│  │ Prev:    │──────▶│ Prev:    │──────▶│ Prev:    │  │
│  │ 0xABC    │       │ 0xDEF    │       │ 0x123    │  │
│  ├──────────┤       ├──────────┤       ├──────────┤  │
│  │ State:   │       │ State:   │       │ State:   │  │
│  │ Merkle   │       │ Merkle   │       │ Merkle   │  │
│  │ Root     │       │ Root     │       │ Root     │  │
│  ├──────────┤       ├──────────┤       ├──────────┤  │
│  │ Txs:     │       │ Txs:     │       │ Txs:     │  │
│  │ Tx 1     │       │ Tx 4     │       │ Tx 7     │  │
│  │ Tx 2     │       │ Tx 5     │       │ Tx 8     │  │
│  │ Tx 3     │       │ Tx 6     │       │ Tx 9     │  │
│  └──────────┘       └──────────┘       └──────────┘  │
└──────────────────────────────────────────────────────┘
```

### Smart Contract (Solidity)

```solidity
// Simple escrow smart contract
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MarketplaceEscrow {
    address public platform;
    uint256 public feeRate;  // Basis points (e.g., 250 = 2.5%)

    struct Escrow {
        address buyer;
        address seller;
        uint256 amount;
        uint256 fee;
        State state;
        uint256 createdAt;
    }

    enum State { Pending, Funded, Released, Refunded, Disputed }

    mapping(bytes32 => Escrow) public escrows;
    bytes32[] public activeEscrows;

    event EscrowCreated(bytes32 indexed id, address buyer, address seller, uint256 amount);
    event EscrowReleased(bytes32 indexed id);
    event DisputeOpened(bytes32 indexed id);

    modifier onlyPlatform() {
        require(msg.sender == platform, "Only platform");
        _;
    }

    constructor(uint256 _feeRate) {
        platform = msg.sender;
        feeRate = _feeRate;
    }

    function createEscrow(address seller) external payable returns (bytes32) {
        require(msg.value > 0, "Amount must be > 0");
        uint256 fee = msg.value * feeRate / 10000;

        bytes32 id = keccak256(abi.encodePacked(
            msg.sender, seller, block.timestamp
        ));

        escrows[id] = Escrow({
            buyer: msg.sender,
            seller: seller,
            amount: msg.value,
            fee: fee,
            state: State.Funded,
            createdAt: block.timestamp
        });

        activeEscrows.push(id);
        emit EscrowCreated(id, msg.sender, seller, msg.value);
        return id;
    }

    function releaseEscrow(bytes32 id) external {
        Escrow storage escrow = escrows[id];
        require(escrow.state == State.Funded, "Not funded");
        require(
            msg.sender == escrow.buyer || msg.sender == platform,
            "Not authorized"
        );

        escrow.state = State.Released;
        uint256 payout = escrow.amount - escrow.fee;

        (bool sent, ) = escrow.seller.call{value: payout}("");
        require(sent, "Payment failed");

        emit EscrowReleased(id);
    }
}
```

---

## 2. Edge Computing

### Edge vs Cloud Architecture

```
┌────────────────────────────────────────────────────────┐
│                    EDGE ARCHITECTURE                    │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────┐ │
│  │  Device       │    │  Edge Node   │    │  Cloud   │ │
│  │  (Sensor,     │───▶│  (Gateway,   │───▶│  Region  │ │
│  │   Phone, IoT) │    │  5G Base)    │    │  Data    │ │
│  └──────────────┘    └──────────────┘    │  Center  │ │
│         │                  │              └──────────┘ │
│         ▼                  ▼                           │
│    Local inference    Aggregation                     │
│    Real-time        Filtering                         │
│    Offline ops      Caching                           │
└────────────────────────────────────────────────────────┘
```

### Edge Worker Pattern

```typescript
// Edge computing worker (Cloudflare Workers style)
interface EdgeRequest {
    url: URL;
    method: string;
    headers: Headers;
    body?: string;
}

interface EdgeResponse {
    status: number;
    headers: Record<string, string>;
    body: string;
}

// Edge function — runs at CDN edge location
export default {
    async fetch(request: EdgeRequest): Promise<EdgeResponse> {
        const url = request.url;
        const cache = caches.default;

        // 1. Check edge cache
        const cached = await cache.match(request);
        if (cached) {
            return {
                status: 200,
                headers: { 'Content-Type': 'application/json', 'X-Cache': 'HIT' },
                body: await cached.text(),
            };
        }

        // 2. Process at edge (geo-aware routing)
        const country = request.headers.get('CF-IPCountry');
        const region = request.headers.get('CF-Region');

        // 3. Route based on location
        const originUrl = this.selectOrigin(url, country);
        const response = await fetch(originUrl, {
            method: request.method,
            headers: request.headers,
            body: request.body,
        });

        // 4. Cache at edge
        if (response.status === 200) {
            const cloned = new Response(response.body, response);
            cloned.headers.set('Cache-Control', 'public, max-age=300');
            ctx.waitUntil(cache.put(request, cloned));
        }

        return {
            status: response.status,
            headers: Object.fromEntries(response.headers),
            body: await response.text(),
        };
    },

    selectOrigin(url: URL, country: string): string {
        // Route to nearest region
        const regions: Record<string, string> = {
            US: 'us-east.api.example.com',
            DE: 'eu-central.api.example.com',
            JP: 'ap-northeast.api.example.com',
            BR: 'sa-east.api.example.com',
            AU: 'ap-southeast.api.example.com',
        };
        const region = regions[country] || 'us-east.api.example.com';
        return `https://${region}${url.pathname}`;
    },
};
```

---

## 3. Digital Twins

### Digital Twin Architecture

```
Physical Asset                    Digital Twin
┌────────────┐                  ┌────────────────────┐
│ Sensor 1   │──┐              │  ┌──────────────┐  │
└────────────┘  │              │  │ 3D Model     │  │
┌────────────┐  │  IoT Hub     │  │ (glTF/USD)   │  │
│ Sensor 2   │──┤──MQTT/HTTP──▶│  └──────────────┘  │
└────────────┘  │              │  ┌──────────────┐  │
┌────────────┐  │              │  │ State        │  │
│ Actuator   │◄─┘              │  │ (real-time)  │  │
└────────────┘                 │  └──────────────┘  │
                               │  ┌──────────────┐  │
                               │  │ Simulation   │  │
                               │  │ Engine       │  │
                               │  └──────────────┘  │
                               │  ┌──────────────┐  │
                               │  │ Analytics    │  │
                               │  │ (anomaly,    │  │
                               │  │  prediction) │  │
                               │  └──────────────┘  │
                               └────────────────────┘
```

### Digital Twin Service

```typescript
// Digital twin service for IoT device modeling
interface TwinState {
    deviceId: string;
    timestamp: Date;
    properties: Record<string, number | string | boolean>;
    desired: Record<string, number | string | boolean>; // Desired state
    reported: Record<string, number | string | boolean>; // Reported state
    tags: Record<string, string>;
}

class DigitalTwinService {
    private twins = new Map<string, TwinState>();
    private simulationModels = new Map<string, SimulationModel>();

    async updateReported(deviceId: string, reported: Record<string, unknown>): Promise<void> {
        const twin = this.getOrCreateTwin(deviceId);
        twin.reported = { ...twin.reported, ...reported };
        twin.timestamp = new Date();

        // Detect anomalies
        const anomalies = this.detectAnomalies(twin);
        if (anomalies.length > 0) {
            await this.alertService.send({
                deviceId,
                type: 'anomaly',
                anomalies,
            });
        }

        // Run simulation step
        await this.runSimulation(twin);
    }

    async setDesired(deviceId: string, desired: Record<string, unknown>): Promise<void> {
        const twin = this.getOrCreateTwin(deviceId);
        twin.desired = { ...twin.desired, ...desired };

        // Push command to physical device
        await this.iotHub.sendCommand(deviceId, {
            type: 'update_desired',
            properties: desired,
        });
    }

    async predictFailure(deviceId: string): Promise<{
        probability: number;
        estimatedTime: Date;
        failureMode: string;
    }> {
        const twin = this.twins.get(deviceId);
        if (!twin) throw new Error('Device not found');

        // Use ML model to predict failure based on twin state
        const prediction = await this.failurePredictor.predict({
            recentProperties: this.getRecentHistory(deviceId, 100),
            currentState: twin,
            modelType: this.getModelType(deviceId),
        });

        return {
            probability: prediction.probability,
            estimatedTime: prediction.timeToFailure,
            failureMode: prediction.mode,
        };
    }
}
```

---

## 4. AR/VR & Spatial Computing

### AR/VR Application Architecture

```
┌──────────────────────────────────────────────────┐
│               AR/VR APPLICATION                   │
│                                                    │
│  ┌─────────────────┐  ┌──────────────────────┐   │
│  │ Rendering Engine │  │ Interaction System   │   │
│  │                  │  │                      │   │
│  │ • Scene graph    │  │ • Hand tracking      │   │
│  │ • PBR materials  │  │ • Eye tracking       │   │
│  │ • Lighting       │  │ • Controller input   │   │
│  │ • Post-processing│  │ • Gesture detection  │   │
│  └────────┬────────┘  └──────────┬───────────┘   │
│           │                      │                │
│  ┌────────▼──────────────────────▼───────────┐   │
│  │          SPATIAL ANCHOR SYSTEM            │   │
│  │  • World-locked anchors                   │   │
│  │  • Plane detection                        │   │
│  │  • Image tracking                         │   │
│  │  • Mesh reconstruction                    │   │
│  └───────────────────────────────────────────┘   │
│                                                    │
│  ┌──────────────────────────────────────────────┐ │
│  │      CROSS-PLATFORM RUNTIME                   │ │
│  │  WebXR  │  ARKit  │  ARCore  │  OpenXR       │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### WebXR AR Application

```typescript
// WebXR — Augmented Reality web application
async function startARSession(canvas: HTMLCanvasElement) {
    // 1. Check WebXR support
    if (!navigator.xr) {
        throw new Error('WebXR not supported');
    }

    // 2. Check for AR support
    const supported = await navigator.xr.isSessionSupported('immersive-ar');
    if (!supported) {
        throw new Error('AR not supported on this device');
    }

    // 3. Request AR session
    const session = await navigator.xr.requestSession('immersive-ar', {
        requiredFeatures: ['local', 'hit-test', 'plane-detection'],
        optionalFeatures: ['anchors', 'dom-overlay', 'light-estimation'],
    });

    // 4. Setup WebGL rendering
    const gl = canvas.getContext('webgl', {
        xrCompatible: true,
        alpha: true,
    });

    // 5. Configure session
    session.updateRenderState({
        baseLayer: new XRWebGLLayer(session, gl),
    });

    // 6. Reference space for world-locked content
    const referenceSpace = await session.requestReferenceSpace('local');

    // 7. Request hit test source (for placing objects)
    const hitTestSource = await session.requestHitTestSource({
        space: referenceSpace,
    });

    // 8. Animation loop
    function onXRFrame(time: DOMHighResTimeStamp, frame: XRFrame) {
        const session = frame.session;

        // Get pose
        const pose = frame.getViewerPose(referenceSpace);
        if (pose) {
            const views = pose.views;
            // Render for each eye (stereoscopic)
            for (const view of views) {
                // Set up viewport and projection
                gl.viewport(
                    view.recommendedViewportOffset?.x || 0,
                    view.recommendedViewportOffset?.y || 0,
                    view.recommendedViewportWidth || canvas.width,
                    view.recommendedViewportHeight || canvas.height
                );
                // Render scene...
            }
        }

        // Hit test for placing objects
        const hitResults = frame.getHitTestResults(hitTestSource);
        if (hitResults.length > 0) {
            const pose = hitResults[0].getPose(referenceSpace);
            // Place object at pose.transform.position
        }

        // Handle plane detection
        const detectedPlanes = frame.detectedPlanes;
        for (const plane of detectedPlanes) {
            // Use plane.pose and plane.polygon for occlusion/placement
        }

        session.requestAnimationFrame(onXRFrame);
    }

    session.requestAnimationFrame(onXRFrame);
}
```

---

## 5. Sustainable & Green Computing

### Green Software Principles

| Principle | Practice | Impact |
|---|---|---|
| **Carbon-aware scheduling** | Run batch jobs when grid is cleanest | 30-70% lower carbon |
| **Efficient algorithms** | O(n) over O(n²) for large data | Orders of magnitude |
| **Lazy loading** | Only load what's needed | 40-60% less data transfer |
| **Compression** | zstd, brotli, AVIF images | 30-80% smaller payloads |
| **Caching** | Multi-level (CDN, memory, disk) | 90%+ fewer requests |
| **Idle detection** | Throttle non-critical work when idle | 20-50% background savings |
| **Resource right-sizing** | Match compute to demand | 30-60% infrastructure savings |
| **Hardware longevity** | Support older devices, progressive enhancement | Reduced e-waste |

### Carbon-Aware Scheduling

```typescript
// Carbon-aware job scheduler
interface GridCarbonIntensity {
    timestamp: Date;
    intensity: number;         // gCO2eq/kWh
    forecast: Array<{ timestamp: Date; intensity: number }>;
}

class CarbonAwareScheduler {
    constructor(private carbonApi: CarbonIntensityAPI) {}

    async scheduleJob(
        job: { id: string; duration: number; priority: 'low' | 'medium' | 'high' },
    ): Promise<Date> {
        if (job.priority === 'high') {
            return new Date(); // Run now
        }

        // Get carbon forecast
        const forecast = await this.carbonApi.getForecast();

        if (job.priority === 'low') {
            // Find the greenest window in the next 24 hours
            const bestWindow = this.findGreenestWindow(forecast, job.duration);
            return bestWindow.start;
        }

        // Medium priority — run within next 4 hours
        const next4h = forecast.filter(f =>
            f.timestamp <= new Date(Date.now() + 4 * 3600000)
        );
        if (this.isBelowThreshold(next4h[0]?.intensity)) {
            return new Date(); // Green enough now
        }

        const mediumWindow = this.findGreenestWindow(next4h, job.duration);
        return mediumWindow.start;
    }

    private findGreenestWindow(
        forecast: GridCarbonIntensity[],
        durationMinutes: number,
    ): { start: Date; intensity: number } {
        let best = { start: new Date(), intensity: Infinity };

        for (let i = 0; i < forecast.length; i++) {
            const window = forecast.slice(i, i + Math.ceil(durationMinutes / 60));
            if (window.length < Math.ceil(durationMinutes / 60)) break;

            const avg = window.reduce((s, f) => s + f.intensity, 0) / window.length;
            if (avg < best.intensity) {
                best = { start: forecast[i].timestamp, intensity: avg };
            }
        }

        return best;
    }
}
```

---

## Quick Reference: Emerging Tech by Node Type

| Node Type | Emerging Tech Mapping |
|---|---|
| **Input** | IoT sensor data ingestion, WebXR input events, blockchain transaction submission |
| **Logic** | Smart contract logic, digital twin simulation, carbon-aware scheduling, AR hit-testing |
| **Database** | Blockchain state, digital twin history, edge cache, IPFS/Arweave storage |
| **UI** | WebXR/AR/VR rendering, 3D scene viewer, blockchain explorer, carbon dashboard |
| **API** | Web3 RPC provider, IoT Hub MQTT bridge, edge function CDN, spatial anchor sync |

---

*For deeper emerging tech concepts, see Bible levels `29-emerging-tech/`, `24-autonomous-adas/`, `25-industrial-manufacturing/` (digital twins), and `23-iot-embedded-deep/`.*
