# 🎬 Media & Multimedia Processing

> Reference for building media processing applications — audio/video codecs, streaming, digital content creation, and media pipelines.
> Extracted from The Programming Bible's Digital Content Media level.

---

## 1. Media Types Overview

### Core Media Formats

| Media Type | Data Model | Common Formats | Key Libraries |
|---|---|---|---|
| **Raster Graphics** | Pixel arrays (RGBA) | PNG, JPEG, WebP, AVIF, OpenEXR | `sharp` (Node), `PIL` (Python) |
| **Vector Graphics** | Paths & curves (Bezier) | SVG, EPS, PDF | `svg.js`, `Paper.js` |
| **3D Geometry** | Vertices + faces + materials | glTF, OBJ, FBX, USD | `three.js`, `blender` |
| **Audio** | PCM samples (time-domain) | WAV, MP3, FLAC, AAC, Opus | `ffmpeg`, `audioworklet` |
| **Video** | Frame sequences + codec | H.264, HEVC, AV1, VP9 | `ffmpeg`, `gstreamer` |
| **Animation** | Keyframes + interpolation | JSON (custom), Lottie, Rive | `framer-motion` |
| **Compositing** | Layer/node graph operations | EXR sequences, OpenColorIO | `nuke`, `blender` |

### Color Space & Bit Depth

```typescript
// Color space management
enum ColorSpace {
  sRGB = 'sRGB',           // Web standard, 8-bit
  Rec709 = 'Rec.709',      // HDTV broadcast
  Rec2020 = 'Rec.2020',    // UHD/HDR wide gamut
  ACES2065 = 'ACES2065-1', // Film industry interchange
  Linear = 'Linear',       // Rendering/compositing
}

interface ImageMetadata {
  width: number;
  height: number;
  bitDepth: 8 | 10 | 12 | 16 | 32;
  colorSpace: ColorSpace;
  alpha: boolean;
  compression: 'lossless' | 'lossy' | 'uncompressed';
}
```

---

## 2. Audio Processing

### Audio Pipeline

```
Source → Decode → Process → Mix → Encode → Output
              │                 │
              ▼                 ▼
         Sample Buffer      Volume/Pan/Effect
```

### Audio Processing Pattern

```typescript
// Audio sample manipulation
interface AudioBuffer {
  sampleRate: number;     // 44100, 48000, 96000
  channels: number;        // 1 (mono), 2 (stereo), 5.1, 7.1
  samples: Float32Array[]; // Per-channel sample data
  duration: number;        // In seconds
}

// Resample audio to match sample rates
function resample(
  input: Float32Array,
  inputRate: number,
  outputRate: number
): Float32Array {
  const ratio = inputRate / outputRate;
  const outputLength = Math.round(input.length / ratio);
  const output = new Float32Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    const srcIdx = i * ratio;
    const lo = Math.floor(srcIdx);
    const hi = Math.min(lo + 1, input.length - 1);
    const frac = srcIdx - lo;
    // Linear interpolation
    output[i] = input[lo] * (1 - frac) + input[hi] * frac;
  }

  return output;
}

// Simple audio effects
function applyGain(buffer: Float32Array, gain: number): Float32Array {
  const output = new Float32Array(buffer.length);
  for (let i = 0; i < buffer.length; i++) {
    output[i] = buffer[i] * gain;
  }
  return output;
}

function applyLowPass(
  buffer: Float32Array,
  cutoff: number,
  sampleRate: number
): Float32Array {
  // Simple single-pole IIR filter
  const rc = 1 / (cutoff * 2 * Math.PI);
  const dt = 1 / sampleRate;
  const alpha = dt / (rc + dt);
  
  const output = new Float32Array(buffer.length);
  output[0] = buffer[0];
  for (let i = 1; i < buffer.length; i++) {
    output[i] = output[i - 1] + alpha * (buffer[i] - output[i - 1]);
  }
  return output;
}
```

### FFmpeg Integration

```typescript
// FFmpeg-based media processing (Node.js)
import { execa } from 'execa';

interface TranscodeOptions {
  input: string;
  output: string;
  videoCodec?: string;   // 'libx264', 'libx265', 'libaom-av1'
  audioCodec?: string;   // 'aac', 'libmp3lame', 'libopus'
  videoBitrate?: string; // '2M', '5M'
  audioBitrate?: string; // '128k', '192k'
  resolution?: string;   // '1920x1080', '1280x720'
  fps?: number;          // 24, 30, 60
}

async function transcodeMedia(opts: TranscodeOptions): Promise<void> {
  const args = [
    '-i', opts.input,
    '-c:v', opts.videoCodec ?? 'libx264',
    '-b:v', opts.videoBitrate ?? '5M',
    '-c:a', opts.audioCodec ?? 'aac',
    '-b:a', opts.audioBitrate ?? '192k',
  ];

  if (opts.resolution) {
    args.push('-vf', `scale=${opts.resolution}`);
  }
  if (opts.fps) {
    args.push('-r', String(opts.fps));
  }

  args.push('-y', opts.output); // Overwrite output

  try {
    await execa('ffmpeg', args, { stdio: 'inherit' });
  } catch (err) {
    throw new AppError(`Transcoding failed: ${(err as Error).message}`, 'ERR_TRANSCODE');
  }
}

// Extract audio from video
async function extractAudio(videoPath: string, audioPath: string): Promise<void> {
  await execa('ffmpeg', [
    '-i', videoPath,
    '-vn',               // No video
    '-acodec', 'libmp3lame',
    '-ab', '192k',
    '-y', audioPath,
  ]);
}

// Generate video thumbnail
async function generateThumbnail(
  videoPath: string,
  outputPath: string,
  timeSeconds = 10
): Promise<void> {
  await execa('ffmpeg', [
    '-i', videoPath,
    '-ss', String(timeSeconds),
    '-vframes', '1',
    '-vf', 'scale=480:-1',
    '-y', outputPath,
  ]);
}
```

---

## 3. Video Streaming

### Streaming Protocols

| Protocol | Latency | Use Case | Notes |
|---|---|---|---|
| **HLS** (HTTP Live Streaming) | ~6-30s | On-demand, live broadcast | Apple standard, most compatible |
| **DASH** (MPEG-DASH) | ~6-30s | On-demand, live broadcast | Open standard |
| **RTMP** (Real-Time Messaging) | ~1-3s | Live streaming ingest | Adobe, being phased out |
| **WebRTC** | <500ms | Real-time communication | Peer-to-peer, conferencing |
| **SRT** (Secure Reliable Transport) | ~1-5s | Professional live contribution | Error-resilient over internet |

### HLS Streaming Setup

```typescript
// Generate HLS segments from video file
async function generateHLS(inputPath: string, outputDir: string): Promise<void> {
  await execa('ffmpeg', [
    '-i', inputPath,
    '-codec:v', 'libx264',
    '-codec:a', 'aac',
    '-hls_time', '6',              // 6-second segments
    '-hls_list_size', '0',         // Keep all segments in playlist
    '-hls_segment_filename', `${outputDir}/segment_%03d.ts`,
    '-hls_playlist_type', 'vod',   // Video on demand
    `${outputDir}/index.m3u8`,
  ]);
}

// Adaptive bitrate HLS (multiple renditions)
async function generateAdaptiveHLS(inputPath: string, outputDir: string): Promise<void> {
  const renditions = [
    { name: '1080p', resolution: '1920x1080', bitrate: '5M' },
    { name: '720p',  resolution: '1280x720',  bitrate: '3M' },
    { name: '480p',  resolution: '854x480',   bitrate: '1.5M' },
    { name: '360p',  resolution: '640x360',   bitrate: '800k' },
  ];

  for (const rendition of renditions) {
    await transcodeMedia({
      input: inputPath,
      output: `${outputDir}/${rendition.name}/index.m3u8`,
      videoCodec: 'libx264',
      videoBitrate: rendition.bitrate,
      resolution: rendition.resolution,
      audioCodec: 'aac',
      audioBitrate: '128k',
    });
  }

  // Generate master playlist
  const masterPlaylist = renditions.map(r =>
    `#EXT-X-STREAM-INF:BANDWIDTH=${parseInt(r.bitrate) * 1000},RESOLUTION=${r.resolution}\n${r.name}/index.m3u8`
  ).join('\n');

  await fs.writeFile(
    `${outputDir}/master.m3u8`,
    `#EXTM3U\n${masterPlaylist}`
  );
}
```

### Video Streaming Server (Simple)

```typescript
// Node.js streaming server with range request support
import express from 'express';
import fs from 'fs';
import path from 'path';

const app = express();
const MEDIA_DIR = '/path/to/media';

app.get('/video/:filename', (req, res) => {
  const filePath = path.join(MEDIA_DIR, req.params.filename);
  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const range = req.headers.range;

  if (range) {
    const parts = range.replace(/bytes=/, '').split('-');
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
    const chunksize = end - start + 1;

    const stream = fs.createReadStream(filePath, { start, end });
    res.writeHead(206, {
      'Content-Range': `bytes ${start}-${end}/${fileSize}`,
      'Content-Length': chunksize,
      'Content-Type': 'video/mp4',
      'Accept-Ranges': 'bytes',
    });
    stream.pipe(res);
  } else {
    res.writeHead(200, {
      'Content-Length': fileSize,
      'Content-Type': 'video/mp4',
      'Accept-Ranges': 'bytes',
    });
    fs.createReadStream(filePath).pipe(res);
  }
});
```

---

## 4. Digital Content Creation (DCC) Architecture

### DCC Application Patterns

| Pattern | Description | Example Tools |
|---|---|---|
| **Plugin System** | C/C++ SDK + Python API for extensions | Maya, Blender, Nuke |
| **Scene Graph (DAG)** | Hierarchical transform tree | 3D modeling tools |
| **Node Graph** | Directed acyclic graph of processing nodes | Compositing, VFX |
| **Timeline** | Track-based media sequencing | Video editing |
| **Layered Composition** | Stacked layers with blending modes | Image editing |

### Media Pipeline Architecture

```
Input Sources
    │
    ▼
┌──────────────┐
│  Decoder     │  Raw → decoded frames/samples
└──────┬───────┘
       ▼
┌──────────────┐
│  Filter      │  Color correction, resize, denoise
└──────┬───────┘
       ▼
┌──────────────┐
│  Process     │  Effects, transitions, compositing
└──────┬───────┘
       ▼
┌──────────────┐
│  Encode      │  Processed → compressed output
└──────┬───────┘
       ▼
    Storage / Stream
```

### Image Processing Pipeline

```typescript
// Node.js image processing with Sharp
import sharp from 'sharp';

interface ProcessingOptions {
  resize?: { width: number; height: number; fit?: 'cover' | 'contain' | 'fill' };
  format?: 'jpeg' | 'png' | 'webp' | 'avif';
  quality?: number;      // 1-100
  rotate?: number;       // Degrees
  grayscale?: boolean;
  blur?: number;
  sharpen?: boolean;
}

async function processImage(
  inputPath: string,
  outputPath: string,
  options: ProcessingOptions
): Promise<void> {
  let pipeline = sharp(inputPath);

  if (options.resize) {
    pipeline = pipeline.resize(options.resize.width, options.resize.height, {
      fit: options.resize.fit ?? 'cover',
      withoutEnlargement: true,
    });
  }

  if (options.rotate) pipeline = pipeline.rotate(options.rotate);
  if (options.grayscale) pipeline = pipeline.grayscale();
  if (options.blur) pipeline = pipeline.blur(options.blur);
  if (options.sharpen) pipeline = pipeline.sharpen();

  const format = options.format ?? 'jpeg';
  const quality = options.quality ?? 80;

  switch (format) {
    case 'jpeg': pipeline = pipeline.jpeg({ quality }); break;
    case 'png': pipeline = pipeline.png({ quality }); break;
    case 'webp': pipeline = pipeline.webp({ quality }); break;
    case 'avif': pipeline = pipeline.avif({ quality }); break;
  }

  await pipeline.toFile(outputPath);
}

// Batch resize images
async function batchResize(inputDir: string, outputDir: string, width: number): Promise<void> {
  const files = await fs.readdir(inputDir);
  const imageFiles = files.filter(f => /\.(jpg|jpeg|png|webp)$/i.test(f));

  await Promise.all(imageFiles.map(async (file) => {
    await processImage(
      path.join(inputDir, file),
      path.join(outputDir, file),
      { resize: { width }, format: 'webp', quality: 80 }
    );
  }));
}
```

---

## 5. Media Library Management

### Media Metadata Extraction

```typescript
// Music metadata
interface MusicMetadata {
  title: string;
  artist: string;
  album: string;
  year: number;
  track: number;
  duration: number; // seconds
  bitrate: number;  // kbps
  format: string;   // 'mp3', 'flac', 'aac'
  sampleRate: number;
  channels: number;
}

// Video metadata
interface VideoMetadata {
  title: string;
  duration: number;
  width: number;
  height: number;
  fps: number;
  codec: string;       // 'h264', 'hevc', 'av1'
  bitrate: number;
  audioCodec: string;
  audioChannels: number;
  aspectRatio: string;
}

// Media library schema (SQLite)
const mediaLibrarySchema = `
  CREATE TABLE IF NOT EXISTS media_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK(type IN ('image', 'audio', 'video', 'document')),
    title TEXT,
    artist TEXT,
    album TEXT,
    duration REAL,
    width INTEGER,
    height INTEGER,
    format TEXT,
    codec TEXT,
    bitrate INTEGER,
    file_size INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE INDEX IF NOT EXISTS idx_media_type ON media_items(type);
  CREATE INDEX IF NOT EXISTS idx_media_path ON media_items(path);
  CREATE INDEX IF NOT EXISTS idx_media_title ON media_items(title);
`;
```

---

## Quick Reference: Media by Node Type

| Node Type | Media Processing Mapping |
|---|---|
| **Input** | File scanner, camera/capture device, import pipeline |
| **Logic** | Transcode engine, filter graph, effect processor |
| **Database** | Media library (SQLite), asset cache, metadata store |
| **UI** | Media player, timeline, waveform display, thumbnail grid |
| **API** | Streaming server, download manager, CDN integration |

---

*For deeper media processing concepts, see Bible level `21-digital-content-media/` — color science, video compositing, font engineering, 3D modeling.*
