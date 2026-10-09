# -*- coding: utf-8 -*-
"""
Code Bible — Category 07: Media (audio/video/image, atomic).
Convention: pure helpers take data in and return transformed data out;
player/managers expose play/pause/seek/state.
"""
CHUNKS = [
    {
        "id": "media-audio-player",
        "name": "Audio Player Controller",
        "category": "media",
        "lang": "typescript",
        "when": "Playing audio files with play/pause/seek/volume in a UI",
        "why": "Atomic audio controller; element or url in, controls + state out — no rendering inside",
        "tags": ["audio", "player", "play", "pause", "seek"],
        "iface": r'''export function createAudioPlayer(src: string) {
  return {
    play(): Promise<void>,
    pause(): void,
    seek(timeSec: number): void,
    setVolume(v: number): void,
    get currentTime(): number,
    get duration(): number,
    get ended(): boolean,
    onEnded(cb: () => void): () => void,
    destroy(): void,
  };
}''',
        "code": r'''export function createAudioPlayer(src: string) {
  const audio = new Audio(src);
  audio.preload = 'metadata';
  const endedCbs: Array<() => void> = [];
  audio.addEventListener('ended', () => endedCbs.forEach((cb) => cb()));

  return {
    play: () => audio.play(),
    pause: () => audio.pause(),
    seek: (t) => { audio.currentTime = Math.max(0, t); },
    setVolume: (v) => { audio.volume = Math.max(0, Math.min(1, v)); },
    get currentTime() { return audio.currentTime; },
    get duration() { return Number.isFinite(audio.duration) ? audio.duration : 0; },
    get ended() { return audio.ended; },
    onEnded(cb) { endedCbs.push(cb); return () => { const i = endedCbs.indexOf(cb); if (i >= 0) endedCbs.splice(i, 1); }; },
    destroy() { audio.pause(); audio.src = ''; endedCbs.length = 0; },
  };
}''',
        "provides": "createAudioPlayer(src)",
        "depends": [],
    },
    {
        "id": "media-video-player",
        "name": "Video Player Controller",
        "category": "media",
        "lang": "typescript",
        "when": "Controlling a <video> element with custom UI",
        "why": "Atomic video controller; video element in, controls + state out — UI chrome separate",
        "tags": ["video", "player", "playback", "controls", "element"],
        "iface": r'''export function createVideoController(video: HTMLVideoElement) {
  return {
    play(): Promise<void>,
    pause(): void,
    toggle(): Promise<void>,
    seek(timeSec: number): void,
    setPlaybackRate(rate: number): void,
    get state(): { playing: boolean; currentTime: number; duration: number; muted: boolean },
    onTimeUpdate(cb: () => void): () => void,
  };
}''',
        "code": r'''export function createVideoController(video: HTMLVideoElement) {
  const timeCbs: Array<() => void> = [];
  video.addEventListener('timeupdate', () => timeCbs.forEach((cb) => cb()));

  return {
    play: () => video.play(),
    pause: () => video.pause(),
    async toggle() {
      if (video.paused) await video.play();
      else video.pause();
    },
    seek: (t) => { video.currentTime = Math.max(0, Math.min(t, video.duration || t)); },
    setPlaybackRate: (rate) => { video.playbackRate = rate; },
    get state() {
      return {
        playing: !video.paused && !video.ended,
        currentTime: video.currentTime,
        duration: Number.isFinite(video.duration) ? video.duration : 0,
        muted: video.muted,
      };
    },
    onTimeUpdate(cb) {
      timeCbs.push(cb);
      return () => { const i = timeCbs.indexOf(cb); if (i >= 0) timeCbs.splice(i, 1); };
    },
  };
}''',
        "provides": "createVideoController(video)",
        "depends": [],
    },
    {
        "id": "media-waveform",
        "name": "Audio Waveform Drawer",
        "category": "media",
        "lang": "typescript",
        "when": "Visualizing audio amplitude as bars (players, editors)",
        "why": "Atomic drawer; samples in, canvas out — peak bucketing only, no decode logic",
        "tags": ["waveform", "audio", "visualize", "canvas", "peaks"],
        "iface": r'''export function drawWaveform(
  ctx: CanvasRenderingContext2D,
  samples: Float32Array,
  width: number,
  height: number,
  color?: string,
): void''',
        "code": r'''export function drawWaveform(
  ctx: CanvasRenderingContext2D,
  samples: Float32Array,
  width: number,
  height: number,
  color = '#4f8ef7',
): void {
  const bucketSize = Math.max(1, Math.floor(samples.length / width));
  const mid = height / 2;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = color;
  ctx.strokeStyle = color;

  for (let x = 0; x < width; x++) {
    const start = x * bucketSize;
    const end = Math.min(samples.length, start + bucketSize);
    let max = 0;
    for (let i = start; i < end; i++) {
      const v = Math.abs(samples[i]);
      if (v > max) max = v;
    }
    const barHeight = Math.max(1, max * height * 0.9);
    ctx.fillRect(x, mid - barHeight / 2, 1, barHeight);
  }
}''',
        "provides": "drawWaveform(ctx, samples, width, height, color?)",
        "depends": [],
    },
    {
        "id": "media-canvas-resize",
        "name": "Canvas/Image Resize",
        "category": "media",
        "lang": "typescript",
        "when": "Resizing images or canvases while preserving aspect ratio",
        "why": "Atomic resize; image source + target dims in, dataURL out — cover/contain modes",
        "tags": ["resize", "image", "canvas", "thumbnail", "scale"],
        "iface": r'''export interface ResizeOptions { maxWidth?: number; maxHeight?: number; mode?: 'cover' | 'contain'; quality?: number; format?: 'image/jpeg' | 'image/png' | 'image/webp' }
export async function resizeImage(source: HTMLImageElement | Blob, options?: ResizeOptions): Promise<string>''',
        "code": r'''export async function resizeImage(source: HTMLImageElement | Blob, options: ResizeOptions = {}): Promise<string> {
  const img = source instanceof Blob
    ? await createImageBitmap(source)
    : source;

  const srcW = 'width' in img ? img.width : 0;
  const srcH = 'height' in img ? img.height : 0;
  const maxW = options.maxWidth ?? srcW;
  const maxH = options.maxHeight ?? srcH;

  let scale = Math.min(maxW / srcW, maxH / srcH);
  if (options.mode === 'cover') scale = Math.max(maxW / srcW, maxH / srcH);
  scale = Math.min(1, scale);   // only downscale by default

  const w = Math.max(1, Math.round(srcW * scale));
  const h = Math.max(1, Math.round(srcH * scale));

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(img as CanvasImageSource, 0, 0, w, h);

  const format = options.format ?? 'image/jpeg';
  return canvas.toDataURL(format, options.quality ?? 0.85);
}''',
        "provides": "resizeImage(source, options?)",
        "depends": [],
    },
    {
        "id": "media-image-filters",
        "name": "Canvas Image Filters",
        "category": "media",
        "lang": "typescript",
        "when": "Applying grayscale/invert/sepia/brightness to images",
        "why": "Atomic filter pipeline; image + filter stack in, dataURL out — pure pixel ops",
        "tags": ["filter", "image", "grayscale", "sepia", "pixel"],
        "iface": r'''export type ImageFilter = { type: 'grayscale' } | { type: 'invert' } | { type: 'sepia' } | { type: 'brightness'; amount: number } | { type: 'contrast'; amount: number };
export function applyFilters(source: CanvasImageSource, filters: ImageFilter[], width: number, height: number): HTMLCanvasElement''',
        "code": r'''export function applyFilters(source: CanvasImageSource, filters: ImageFilter[], width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;
  ctx.drawImage(source, 0, 0, width, height);

  const imageData = ctx.getImageData(0, 0, width, height);
  const d = imageData.data;

  for (let i = 0; i < d.length; i += 4) {
    let r = d[i], g = d[i + 1], b = d[i + 2];
    for (const f of filters) {
      if (f.type === 'grayscale') {
        const gray = 0.299 * r + 0.587 * g + 0.114 * b;
        r = g = b = gray;
      } else if (f.type === 'invert') {
        r = 255 - r; g = 255 - g; b = 255 - b;
      } else if (f.type === 'sepia') {
        const nr = 0.393 * r + 0.769 * g + 0.189 * b;
        const ng = 0.349 * r + 0.686 * g + 0.168 * b;
        const nb = 0.272 * r + 0.534 * g + 0.131 * b;
        r = nr; g = ng; b = nb;
      } else if (f.type === 'brightness') {
        r *= f.amount; g *= f.amount; b *= f.amount;
      } else if (f.type === 'contrast') {
        const f2 = (259 * (f.amount * 100 + 255)) / (255 * (259 - f.amount * 100));
        r = f2 * (r - 128) + 128;
        g = f2 * (g - 128) + 128;
        b = f2 * (b - 128) + 128;
      }
    }
    d[i] = Math.max(0, Math.min(255, r));
    d[i + 1] = Math.max(0, Math.min(255, g));
    d[i + 2] = Math.max(0, Math.min(255, b));
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}''',
        "provides": "applyFilters(source, filters, width, height)",
        "depends": [],
    },
    {
        "id": "media-audio-recorder",
        "name": "Microphone Recorder",
        "category": "media",
        "lang": "typescript",
        "when": "Capturing microphone input to a blob (voice notes, dictation)",
        "why": "Atomic recorder; nothing in, start/stop/result out — MediaRecorder lifecycle owned here",
        "tags": ["record", "microphone", "audio", "media", "capture"],
        "iface": r'''export function createAudioRecorder(options?: { mimeType?: string }) {
  return {
    async start(): Promise<void>,
    async stop(): Promise<{ blob: Blob; url: string }>,
    get state(): 'inactive' | 'recording' | 'paused',
    cancel(): void,
  };
}''',
        "code": r'''export function createAudioRecorder(options?: { mimeType?: string }) {
  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let chunks: BlobPart[] = [];

  return {
    async start() {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream, options?.mimeType ? { mimeType: options.mimeType } : undefined);
      chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.start();
    },
    async stop() {
      if (!recorder) throw new Error('not_recording');
      return new Promise<{ blob: Blob; url: string }>((resolve) => {
        recorder!.onstop = () => {
          stream?.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: recorder!.mimeType || 'audio/webm' });
          resolve({ blob, url: URL.createObjectURL(blob) });
        };
        recorder!.stop();
      });
    },
    get state() { return recorder ? (recorder.state as 'inactive' | 'recording' | 'paused') : 'inactive'; },
    cancel() {
      recorder?.stop();
      stream?.getTracks().forEach((t) => t.stop());
      recorder = null;
      stream = null;
      chunks = [];
    },
  };
}''',
        "provides": "createAudioRecorder(options?)",
        "depends": [],
    },
    {
        "id": "media-audio-visualizer",
        "name": "Frequency Visualizer",
        "category": "media",
        "lang": "typescript",
        "when": "Drawing realtime frequency bars from audio (music apps, EQ)",
        "why": "Atomic analyzer; analyser node + canvas in, loop render out — rAF + FFT inside",
        "tags": ["visualizer", "frequency", "fft", "analyser", "bars"],
        "iface": r'''export function startFrequencyVisualizer(
  analyser: AnalyserNode,
  ctx: CanvasRenderingContext2D,
  options?: { barCount?: number; color?: string; smoothing?: number },
): () => void''',
        "code": r'''export function startFrequencyVisualizer(
  analyser: AnalyserNode,
  ctx: CanvasRenderingContext2D,
  options?: { barCount?: number; color?: string; smoothing?: number },
): () => void {
  analyser.fftSize = 256;
  analyser.smoothingTimeConstant = options?.smoothing ?? 0.8;
  const data = new Uint8Array(analyser.frequencyBinCount);
  const barCount = options?.barCount ?? 48;
  const color = options?.color ?? '#4f8ef7';
  let raf = 0;

  function render() {
    analyser.getByteFrequencyData(data);
    const w = ctx.canvas.width;
    const h = ctx.canvas.height;
    ctx.clearRect(0, 0, w, h);
    const barW = w / barCount;

    for (let i = 0; i < barCount; i++) {
      const value = data[Math.floor((i / barCount) * data.length)] / 255;
      const barH = Math.max(2, value * h);
      ctx.fillStyle = color;
      ctx.fillRect(i * barW + 1, h - barH, Math.max(2, barW - 2), barH);
    }
    raf = requestAnimationFrame(render);
  }

  render();
  return () => cancelAnimationFrame(raf);
}''',
        "provides": "startFrequencyVisualizer(analyser, ctx, options?)",
        "depends": [],
    },
    {
        "id": "media-frame-extractor",
        "name": "Video Frame Extractor",
        "category": "media",
        "lang": "typescript",
        "when": "Grabbing a thumbnail frame from a video at a timestamp",
        "why": "Atomic frame grab; video source + time in, image dataURL out — seeks once, never plays",
        "tags": ["video", "frame", "thumbnail", "extract", "capture"],
        "iface": r'''export async function extractVideoFrame(
  src: string,
  timeSec: number,
  options?: { maxWidth?: number },
): Promise<string>''',
        "code": r'''export async function extractVideoFrame(src: string, timeSec: number, options?: { maxWidth?: number }): Promise<string> {
  const video = document.createElement('video');
  video.src = src;
  video.muted = true;
  video.preload = 'metadata';

  await new Promise<void>((resolve, reject) => {
    video.onloadeddata = () => resolve();
    video.onerror = () => reject(new Error('video_load_failed'));
  });

  video.currentTime = Math.max(0, Math.min(timeSec, video.duration || 0));
  await new Promise<void>((resolve) => { video.onseeked = () => resolve(); });

  const scale = Math.min(1, (options?.maxWidth ?? 640) / video.videoWidth);
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, video.videoWidth * scale);
  canvas.height = Math.max(1, video.videoHeight * scale);
  canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height);

  video.src = '';
  return canvas.toDataURL('image/jpeg', 0.8);
}''',
        "provides": "extractVideoFrame(src, timeSec, options?)",
        "depends": [],
    },
    {
        "id": "media-metadata-reader",
        "name": "Audio Metadata Reader",
        "category": "media",
        "lang": "typescript",
        "when": "Reading duration/artist/title from audio files (music libraries)",
        "why": "Atomic metadata; blob in, tags + duration out — async decode, no player required",
        "tags": ["metadata", "audio", "tags", "duration", "music"],
        "iface": r'''export interface AudioMetadata { duration: number; title?: string; artist?: string; album?: string }
export async function readAudioMetadata(blob: Blob): Promise<AudioMetadata>
export function parseId3Tags(bytes: Uint8Array): { title?: string; artist?: string; album?: string }''',
        "code": r'''export function parseId3Tags(bytes: Uint8Array): { title?: string; artist?: string; album?: string } {
  // Minimal ID3v2.3/v2.4 frame scan: 'TIT2' title, 'TPE1' artist, 'TALB' album.
  if (bytes.length < 10 || String.fromCharCode(bytes[0], bytes[1], bytes[2]) !== 'ID3') return {};
  const major = bytes[3];
  const size = ((bytes[6] & 0x7f) << 21) | ((bytes[7] & 0x7f) << 14) | ((bytes[8] & 0x7f) << 7) | (bytes[9] & 0x7f);
  const out: { title?: string; artist?: string; album?: string } = {};
  let pos = 10;
  const end = Math.min(bytes.length, 10 + size);

  function readFrameSize(b: Uint8Array, i: number): number {
    if (major >= 4) {
      return ((b[i] & 0x7f) << 21) | ((b[i + 1] & 0x7f) << 14) | ((b[i + 2] & 0x7f) << 7) | (b[i + 3] & 0x7f);
    }
    return (b[i] << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3];
  }

  function readFrame(): { id: string; data: string } | null {
    if (pos + 10 > end) return null;
    const id = String.fromCharCode(...bytes.subarray(pos, pos + 4));
    const frameSize = readFrameSize(bytes, pos + 4);
    pos += 10;
    if (pos + frameSize > end) return null;
    const raw = bytes.subarray(pos, pos + frameSize);
    pos += frameSize;
    // Text frames: first byte is encoding, then UTF-16 (BOM) or Latin-1 text.
    let text = '';
    if (raw[0] === 1 && raw.length >= 3) {
      const bom = (raw[1] << 8) | raw[2];
      if (bom === 0xfffe) text = new TextDecoder('utf-16le').decode(raw.subarray(3));
      else if (bom === 0xfeff) text = new TextDecoder('utf-16be').decode(raw.subarray(3));
    } else if (raw[0] === 0) {
      text = new TextDecoder('latin1').decode(raw.subarray(1));
    }
    return { id, data: text.replace(/\0/g, '').trim() };
  }

  let frame = readFrame();
  while (frame) {
    if (frame.id === 'TIT2') out.title = frame.data;
    else if (frame.id === 'TPE1') out.artist = frame.data;
    else if (frame.id === 'TALB') out.album = frame.data;
    frame = readFrame();
  }
  return out;
}

export async function readAudioMetadata(blob: Blob): Promise<AudioMetadata> {
  const ctx = new AudioContext();
  try {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const tags = parseId3Tags(bytes);
    const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    const decoded = await ctx.decodeAudioData(ab);
    return { duration: decoded.duration, ...tags };
  } finally {
    await ctx.close();
  }
}''',
        "provides": "readAudioMetadata(blob)",
        "depends": [],
    },
    {
        "id": "media-slideshow",
        "name": "Slideshow Timer",
        "category": "media",
        "lang": "typescript",
        "when": "Auto-advancing slides/media with manual navigation",
        "why": "Atomic slideshow controller; interval in, next/prev/state out — pure sequencing",
        "tags": ["slideshow", "slide", "timer", "advance", "carousel"],
        "iface": r'''export function createSlideshow(options?: { intervalMs?: number; loop?: boolean }) {
  return {
    index: number,
    next(): void,
    prev(): void,
    goTo(i: number): void,
    start(): void,
    stop(): void,
    onIndexChange(cb: (i: number) => void): () => void,
    get count(): number,
  };
}''',
        "code": r'''export function createSlideshow(options?: { intervalMs?: number; loop?: boolean }) {
  const intervalMs = options?.intervalMs ?? 5000;
  const loop = options?.loop ?? true;
  let index = 0;
  let count = 0;
  let timer: ReturnType<typeof setInterval> | undefined;
  const listeners = new Set<(i: number) => void>();

  function notify() { listeners.forEach((cb) => cb(index)); }

  function schedule() {
    if (timer) clearInterval(timer);
    if (count > 1) timer = setInterval(() => next(), intervalMs);
  }

  function next() {
    index = index + 1 >= count ? (loop ? 0 : count - 1) : index + 1;
    notify();
  }

  return {
    get index() { return index; },
    next,
    prev() {
      index = index - 1 < 0 ? (loop ? count - 1 : 0) : index - 1;
      notify();
    },
    goTo(i) {
      if (i < 0 || i >= count) return;
      index = i;
      notify();
    },
    start() { schedule(); },
    stop() { if (timer) clearInterval(timer); timer = undefined; },
    onIndexChange(cb) { listeners.add(cb); return () => listeners.delete(cb); },
    get count() { return count; },
    _setCount(n: number) { count = n; if (index >= count) index = Math.max(0, count - 1); },
  };
}''',
        "provides": "createSlideshow(options?)",
        "depends": [],
    },
    {
        "id": "media-playlist",
        "name": "Playlist Controller",
        "category": "media",
        "lang": "typescript",
        "when": "Sequencing tracks with repeat/shuffle and auto-advance",
        "why": "Atomic playlist; tracks in, current/next/prev/shuffle out — player itself injected as callback",
        "tags": ["playlist", "queue", "shuffle", "repeat", "music"],
        "iface": r'''export interface Track { id: string; src: string; title: string; [k: string]: unknown }
export function createPlaylist(tracks: Track[], onTrackChange: (track: Track, index: number) => void) {
  return {
    current(): Track | null,
    next(): Track | null,
    prev(): Track | null,
    playAt(i: number): Track,
    toggleShuffle(): void,
    toggleRepeat(): void,
    get index(): number,
    get shuffled(): boolean,
    get repeated(): boolean,
  };
}''',
        "code": r'''export function createPlaylist(tracks: Track[], onTrackChange: (track: Track, index: number) => void) {
  let index = 0;
  let shuffled = false;
  let repeat = false;
  let order: number[] = tracks.map((_, i) => i);

  function ensureOrder() {
    if (shuffled) {
      order = tracks.map((_, i) => i).sort(() => Math.random() - 0.5);
      order = order.filter((i) => i !== index);
      order.unshift(index);
    }
  }

  function currentTrack(): Track | null {
    return tracks[order[index]] ?? null;
  }

  function change(delta: number): Track | null {
    if (tracks.length === 0) return null;
    index += delta;
    if (index < 0 || index >= order.length) {
      if (repeat) index = ((index % order.length) + order.length) % order.length;
      else { index = Math.max(0, Math.min(order.length - 1, index)); return null; }
    }
    const track = currentTrack();
    if (track) onTrackChange(track, order[index]);
    return track;
  }

  return {
    current: currentTrack,
    next: () => change(1),
    prev: () => change(-1),
    playAt(i) {
      const idx = order.indexOf(i);
      if (idx === -1) { order = tracks.map((_, n) => n); index = i; }
      else index = idx;
      const track = currentTrack()!;
      onTrackChange(track, i);
      return track;
    },
    toggleShuffle() { shuffled = !shuffled; ensureOrder(); },
    toggleRepeat() { repeat = !repeat; },
    get index() { return order[index]; },
    get shuffled() { return shuffled; },
    get repeated() { return repeat; },
  };
}''',
        "provides": "createPlaylist(tracks, onTrackChange)",
        "depends": [],
    },
    {
        "id": "media-clip-trim",
        "name": "Media Clip Trimmer",
        "category": "media",
        "lang": "typescript",
        "when": "Marking in/out points to trim audio or video segments",
        "why": "Atomic trim helper; duration in, in/out points out — pure timeline math",
        "tags": ["trim", "clip", "in", "out", "timeline"],
        "iface": r'''export function createClipTrimmer(duration: number) {
  return {
    setIn(t: number): void,
    setOut(t: number): void,
    get inPoint(): number,
    get outPoint(): number,
    get duration(): number,
    clamp(t: number): number,
    toRange(): [number, number],
  };
}''',
        "code": r'''export function createClipTrimmer(duration: number) {
  let inPoint = 0;
  let outPoint = duration;

  function clamp(t: number): number {
    return Math.max(0, Math.min(duration, t));
  }

  return {
    setIn(t) {
      inPoint = clamp(Math.min(t, outPoint));
    },
    setOut(t) {
      outPoint = clamp(Math.max(t, inPoint));
    },
    get inPoint() { return inPoint; },
    get outPoint() { return outPoint; },
    get duration() { return outPoint - inPoint; },
    clamp,
    toRange() { return [inPoint, outPoint]; },
  };
}''',
        "provides": "createClipTrimmer(duration)",
        "depends": [],
    },
    {
        "id": "media-color-quantize",
        "name": "Color Quantizer",
        "category": "media",
        "lang": "typescript",
        "when": "Reducing an image's palette (pixel-art, GIF, thumbnails)",
        "why": "Atomic quantizer; image data + k colors in, palette + remapped pixels out — median cut",
        "tags": ["quantize", "palette", "colors", "pixel", "gif"],
        "iface": r'''export function quantizeColors(
  pixels: Uint8ClampedArray,
  k: number,
): { palette: Array<[number, number, number]>; indexed: Uint8Array }''',
        "code": r'''export function quantizeColors(pixels: Uint8ClampedArray, k: number) {
  const colors: Array<[number, number, number]> = [];
  for (let i = 0; i < pixels.length; i += 4) colors.push([pixels[i], pixels[i + 1], pixels[i + 2]]);

  function medianCut(list: Array<[number, number, number]>, depth: number): Array<[number, number, number]> {
    if (list.length === 0) return [];
    if (depth === 0 || list.length === 1) {
      const avg = list.reduce<[number, number, number]>(
        (acc, c) => [acc[0] + c[0], acc[1] + c[1], acc[2] + c[2]],
        [0, 0, 0],
      );
      const n = list.length;
      return [[Math.round(avg[0] / n), Math.round(avg[1] / n), Math.round(avg[2] / n)]];
    }
    const range = [0, 1, 2].map((ch) => {
      const vals = list.map((c) => c[ch]);
      return Math.max(...vals) - Math.min(...vals);
    });
    const channel = range.indexOf(Math.max(...range));
    list.sort((a, b) => a[channel] - b[channel]);
    const mid = list.length >> 1;
    return [...medianCut(list.slice(0, mid), depth - 1), ...medianCut(list.slice(mid), depth - 1)];
  }

  const palette = medianCut(colors, Math.ceil(Math.log2(k))).slice(0, k);
  const indexed = new Uint8Array(colors.length);
  for (let i = 0; i < colors.length; i++) {
    let best = 0, bestDist = Infinity;
    for (let j = 0; j < palette.length; j++) {
      const d = (colors[i][0] - palette[j][0]) ** 2 + (colors[i][1] - palette[j][1]) ** 2 + (colors[i][2] - palette[j][2]) ** 2;
      if (d < bestDist) { bestDist = d; best = j; }
    }
    indexed[i] = best;
  }
  return { palette, indexed };
}''',
        "provides": "quantizeColors(pixels, k)",
        "depends": [],
    },
    {
        "id": "media-sprite-sheet",
        "name": "Sprite Sheet Animator",
        "category": "media",
        "lang": "typescript",
        "when": "Playing frame-based animations from a sprite sheet",
        "why": "Atomic animator; sheet + frame config in, current frame out — fps + looping handled",
        "tags": ["sprite", "sheet", "animation", "frames", "fps"],
        "iface": r'''export interface SpriteSheetConfig { cols: number; rows: number; frameW: number; frameH: number; fps?: number; loop?: boolean }
export function createSpriteAnimator(config: SpriteSheetConfig) {
  return {
    update(dt: number): void,
    get frame(): { sx: number; sy: number; index: number },
    setFps(fps: number): void,
    restart(): void,
    get finished(): boolean,
  };
}''',
        "code": r'''export function createSpriteAnimator(config: SpriteSheetConfig) {
  const totalFrames = config.cols * config.rows;
  const frameMs = 1000 / (config.fps ?? 12);
  let elapsed = 0;
  let index = 0;
  let finished = false;

  return {
    update(dt) {
      if (finished && !config.loop) return;
      elapsed += dt * 1000;
      while (elapsed >= frameMs) {
        elapsed -= frameMs;
        index++;
        if (index >= totalFrames) {
          if (config.loop) index = 0;
          else { index = totalFrames - 1; finished = true; return; }
        }
      }
    },
    get frame() {
      return {
        sx: (index % config.cols) * config.frameW,
        sy: Math.floor(index / config.cols) * config.frameH,
        index,
      };
    },
    setFps(fps) { config.fps = fps; },
    restart() { index = 0; elapsed = 0; finished = false; },
    get finished() { return finished; },
  };
}''',
        "provides": "createSpriteAnimator(config)",
        "depends": [],
    },
]
