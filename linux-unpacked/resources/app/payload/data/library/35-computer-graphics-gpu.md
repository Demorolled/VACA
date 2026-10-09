# 🎨 Computer Graphics & GPU Programming

> Reference for graphics programming — rendering pipelines, GPU architecture, shaders, WebGPU, and visualization techniques.
> Extracted from The Programming Bible's Computer Graphics and GPU Architecture levels.

---

## 1. Graphics Pipeline Overview

### Real-Time Rendering Pipeline

```
Vertex Data (3D Model)
    │
    ▼
┌──────────────────────┐
│ Vertex Shader        │  ← Transform vertices to clip space
│ (per-vertex)          │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Primitive Assembly   │  ← Assemble triangles/lines/points
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Rasterization        │  ← Convert triangles to fragments (pixels)
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Fragment Shader      │  ← Compute per-pixel color
│ (per-fragment)        │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Output Merging       │  ← Depth test, stencil, blending
│ (per-pixel)           │
└──────┬───────────────┘
       │
       ▼
    Framebuffer → Display
```

### Coordinate Systems

```
Model Space → World Space → View Space → Clip Space → NDC → Screen
   (local)      (scene)      (camera)     (project)   [-1,1]  (pixels)
```

| Matrix | Purpose | Description |
|---|---|---|
| **Model** | Object → World | Translate, rotate, scale the object |
| **View** | World → Camera | Position the camera in the world |
| **Projection** | Camera → Clip | Perspective or orthographic projection |
| **Viewport** | Clip → Screen | Map [-1,1] to pixel coordinates |

---

## 2. GPU Architecture

### Modern GPU Design

```
┌─────────────────────────────────────────────────────┐
│                    GPU Chip                          │
│                                                      │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                │
│  │ GPC  │ │ GPC  │ │ GPC  │ │ GPC  │  ...           │
│  └──────┘ └──────┘ └──────┘ └──────┘                │
│      │        │        │        │                    │
│  ┌───┴───┐ ┌──┴───┐ ┌──┴───┐ ┌──┴───┐              │
│  │ TPC   │ │ TPC  │ │ TPC  │ │ TPC  │  (Texture     │
│  │ SM    │ │ SM   │ │ SM   │ │ SM   │   Processing  │
│  └───┬───┘ └──┬───┘ └──┬───┘ └──┬───┘   Clusters)   │
│      │        │        │        │                    │
│  ┌───┴───┐ ┌──┴───┐ ┌──┴───┐ ┌──┴───┐              │
│  │ CUDA  │ │CUDA │ │CUDA │ │CUDA │  (Streaming      │
│  │ Cores │ │Cores│ │Cores│ │Cores│   Multiprocessors)│
│  └───────┘ └─────┘ └─────┘ └─────┘                  │
│                                                      │
│  ┌─────────────────────────────────────┐            │
│  │         Memory Hierarchy            │            │
│  │  L1 Cache / Shared Memory (per SM)  │            │
│  │  L2 Cache (shared across GPCs)      │            │
│  │  HBM/VRAM (global memory)           │            │
│  └─────────────────────────────────────┘            │
└─────────────────────────────────────────────────────┘
```

### GPU vs CPU Comparison

| Aspect | CPU | GPU |
|---|---|---|
| **Design Goal** | Low-latency single-thread | High-throughput parallel |
| **Cores** | Few (4-32), complex | Many (1000s), simple |
| **Cache** | Large L1-L3 | Small L1, shared L2 |
| **Memory** | DDR (low bandwidth) | HBM/GDDR (high bandwidth) |
| **SIMT** | SIMD (SSE/AVX) | SIMT (warp/wavefront) |
| **Best for** | Sequential, branching | Data-parallel, throughput |

---

## 3. Shader Programming

### GLSL Shader Example

```glsl
// Vertex shader — transforms 3D vertices to screen space
#version 460 core

layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;

uniform mat4 uModel;
uniform mat4 uView;
uniform mat4 uProjection;

out vec3 vNormal;
out vec2 vTexCoord;
out vec3 vWorldPos;

void main() {
    vec4 worldPos = uModel * vec4(aPosition, 1.0);
    gl_Position = uProjection * uView * worldPos;
    vNormal = mat3(uModel) * aNormal;          // Transform normal
    vTexCoord = aTexCoord;
    vWorldPos = worldPos.xyz;
}
```

```glsl
// Fragment shader — computes per-pixel color with PBR
#version 460 core

in vec3 vNormal;
in vec2 vTexCoord;
in vec3 vWorldPos;

uniform vec3 uLightPos;
uniform vec3 uLightColor;
uniform vec3 uCameraPos;
uniform sampler2D uAlbedo;
uniform sampler2D uMetallicRoughness;

out vec4 fragColor;

void main() {
    vec3 albedo = texture(uAlbedo, vTexCoord).rgb;
    float metallic = texture(uMetallicRoughness, vTexCoord).r;
    float roughness = texture(uMetallicRoughness, vTexCoord).g;

    vec3 N = normalize(vNormal);
    vec3 V = normalize(uCameraPos - vWorldPos);
    vec3 L = normalize(uLightPos - vWorldPos);
    vec3 H = normalize(V + L);

    // Cook-Torrance BRDF
    float NDF = distributionGGX(N, H, roughness);
    float G = geometrySmith(N, V, L, roughness);
    vec3 F = fresnelSchlick(H, V, mix(vec3(0.04), albedo, metallic));

    vec3 kS = F;
    vec3 kD = (1.0 - kS) * (1.0 - metallic);

    vec3 numerator = NDF * G * F;
    float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
    vec3 specular = numerator / denominator;

    vec3 radiance = uLightColor * max(dot(N, L), 0.0);
    fragColor = vec4((kD * albedo / PI + specular) * radiance, 1.0);
}
```

### Compute Shader (GPGPU)

```glsl
// Compute shader — general-purpose GPU computation
#version 460 core
layout(local_size_x = 256) in;

layout(std430, binding = 0) buffer Data {
    float inputData[];
    float outputData[];
};

shared float sharedData[256];

void main() {
    uint id = gl_GlobalInvocationID.x;
    uint lid = gl_LocalInvocationID.x;

    // Load into shared memory
    sharedData[lid] = inputData[id];
    barrier();

    // Parallel prefix sum (scan)
    for (uint offset = 1; offset < 256; offset *= 2) {
        float val = 0.0;
        if (lid >= offset) {
            val = sharedData[lid - offset];
        }
        barrier();
        sharedData[lid] += val;
        barrier();
    }

    outputData[id] = sharedData[lid];
}
```

---

## 4. WebGPU (Modern Web Graphics)

### WebGPU Setup

```typescript
// WebGPU initialization and render loop
async function initWebGPU(canvas: HTMLCanvasElement) {
    // 1. Get adapter and device
    const adapter = await navigator.gpu.requestAdapter({
        powerPreference: "high-performance",
    });
    if (!adapter) throw new Error("WebGPU not supported");

    const device = await adapter.requestDevice();

    // 2. Configure swap chain
    const context = canvas.getContext("webgpu")!;
    const format = navigator.gpu.getPreferredCanvasFormat();
    context.configure({
        device,
        format,
        alphaMode: "premultiplied",
    });

    // 3. Create shader module
    const shaderModule = device.createShaderModule({
        code: `
            @vertex
            fn vertexMain(@location(0) pos: vec3f) -> @builtin(position) vec4f {
                return vec4f(pos, 1.0);
            }

            @fragment
            fn fragmentMain() -> @location(0) vec4f {
                return vec4f(0.3, 0.6, 1.0, 1.0);
            }
        `,
    });

    // 4. Create render pipeline
    const pipeline = device.createRenderPipeline({
        layout: "auto",
        vertex: {
            module: shaderModule,
            entryPoint: "vertexMain",
            buffers: [{
                attributes: [
                    { shaderLocation: 0, offset: 0, format: "float32x3" },
                ],
                arrayStride: 12,
            }],
        },
        fragment: {
            module: shaderModule,
            entryPoint: "fragmentMain",
            targets: [{ format }],
        },
        primitive: { topology: "triangle-list" },
    });

    // 5. Render loop
    function frame() {
        const commandEncoder = device.createCommandEncoder();
        const passEncoder = commandEncoder.beginRenderPass({
            colorAttachments: [{
                view: context.getCurrentTexture().createView(),
                loadOp: "clear",
                storeOp: "store",
                clearValue: { r: 0.1, g: 0.1, b: 0.2, a: 1.0 },
            }],
        });

        passEncoder.setPipeline(pipeline);
        passEncoder.draw(3); // 3 vertices = 1 triangle
        passEncoder.end();

        device.queue.submit([commandEncoder.finish()]);
        requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);
    return { device, context, pipeline };
}
```

### Graphics API Comparison

| API | Platform | Language | Control | Learning Curve |
|---|---|---|---|---|
| **OpenGL 4.x** | Cross-platform | GLSL | Medium | Moderate |
| **Vulkan** | Cross-platform | SPIR-V/GLSL | Maximum | Steep |
| **DirectX 12** | Windows/Xbox | HLSL | Maximum | Steep |
| **Metal** | Apple devices | MSL | High | Moderate |
| **WebGPU** | Web/Native | WGSL | Medium | Moderate |
| **WebGL 2.0** | Web | GLSL ES | Low | Easy |

---

## 5. Visualization Techniques

### Data Visualization Patterns

| Technique | Use Case | Tools/Libraries |
|---|---|---|
| **Bar/Line/Scatter** | General data viz | D3.js, Chart.js, Plotly |
| **Heatmap** | 2D density, correlation | Matplotlib, Seaborn |
| **3D Surface** | Scientific visualization | Three.js, VTK, ParaView |
| **Network Graph** | Relationships, topology | D3 force, Cytoscape |
| **Volume Rendering** | Medical/scientific 3D data | VTK, WebGL volume |
| **Geospatial** | Maps, GIS | Mapbox, Leaflet, Cesium |

### CPU-Based Rendering (Software Rasterizer)

```typescript
// Minimal software rasterizer
interface Vertex { x: number; y: number; z: number; }
interface Color { r: number; g: number; b: number; a: number; }

class SoftwareRenderer {
    private framebuffer: ImageData;

    constructor(private width: number, private height: number) {
        this.framebuffer = new ImageData(width, height);
    }

    clear(color: Color = { r: 0, g: 0, b: 0, a: 255 }): void {
        for (let i = 0; i < this.framebuffer.data.length; i += 4) {
            this.framebuffer.data[i] = color.r;
            this.framebuffer.data[i + 1] = color.g;
            this.framebuffer.data[i + 2] = color.b;
            this.framebuffer.data[i + 3] = color.a;
        }
    }

    drawTriangle(v0: Vertex, v1: Vertex, v2: Vertex, color: Color): void {
        // Bounding box
        const minX = Math.max(0, Math.floor(Math.min(v0.x, v1.x, v2.x)));
        const minY = Math.max(0, Math.floor(Math.min(v0.y, v1.y, v2.y)));
        const maxX = Math.min(this.width - 1, Math.ceil(Math.max(v0.x, v1.x, v2.x)));
        const maxY = Math.min(this.height - 1, Math.ceil(Math.max(v0.y, v1.y, v2.y)));

        // Edge function
        const edge = (a: Vertex, b: Vertex, c: Vertex) =>
            (c.x - a.x) * (b.y - a.y) - (c.y - a.y) * (b.x - a.x);

        const area = edge(v0, v1, v2);
        if (area === 0) return;

        // Rasterize
        for (let y = minY; y <= maxY; y++) {
            for (let x = minX; x <= maxX; x++) {
                const p = { x, y, z: 0 };
                const w0 = edge(v1, v2, p);
                const w1 = edge(v2, v0, p);
                const w2 = edge(v0, v1, p);

                // Barycentric check
                if (w0 >= 0 && w1 >= 0 && w2 >= 0) {
                    const idx = (y * this.width + x) * 4;
                    this.framebuffer.data[idx] = color.r;
                    this.framebuffer.data[idx + 1] = color.g;
                    this.framebuffer.data[idx + 2] = color.b;
                    this.framebuffer.data[idx + 3] = color.a;
                }
            }
        }
    }

    getBuffer(): ImageData { return this.framebuffer; }
}
```

---

## Quick Reference: Graphics by Node Type

| Node Type | Graphics Mapping |
|---|---|
| **Input** | User input handling (click, drag, keyboard, touch, gamepad) |
| **Logic** | Transformation math, physics simulation, animation curves, LOD selection |
| **Database** | Texture storage, mesh data, scene graph persistence |
| **UI** | Rendering context, display loop, HUD overlay, interaction layer |
| **API** | Scene description format (glTF/USD), remote rendering protocol |

---

*For deeper graphics concepts, see Bible levels `08-computer-graphics/`, `08-graphics/`, `16-computer-architecture/` (GPU section), and `22-browser-engineering/` (rendering engine).*
