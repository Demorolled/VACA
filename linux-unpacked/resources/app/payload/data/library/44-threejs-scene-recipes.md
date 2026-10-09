# 🧊 Three.js 3D Scene Recipes

> The rendering layer for generated GUI apps. Use this sheet whenever the user
> asks for a 3D scene, 3D game (chess, maze, builder, visualizer), rotating
> logo/object, particle effect, or anything that needs real perspective depth.
> Pair with `12-game-development-patterns.md` (game loop, AI) and
> `35-computer-graphics-gpu.md` (shaders/WebGPU, for advanced effects).

---

## 0. Which technology to pick (decide FIRST)

| Request | Technology | Why |
|---|---|---|
| True 3D with depth, lights, shadows | **Three.js via CDN (r128 UMD)** | Most-documented browser 3D; no build step; works with the single-file HTML constraint |
| Faux-3D board/scene, no WebGL | **CSS 3D transforms** (`perspective`, `rotateX`) | Zero dependencies, instant load, still looks dimensional |
| Isometric "2.5D" dashboard/game | **Canvas 2D with isometric projection** | Fast, crisp, no WebGL required |
| Real-time VR/AR or custom shaders | WebGPU / raw WebGL | Only for advanced requests; much higher risk of runtime failure |

**Default for "3D": Three.js r128 UMD.** It is the pattern the model has seen
most in training data, needs no build step, and works in the browser preview.

---

## 1. The ONLY CDN import pattern that works in a single-file HTML app

Three.js ships two module styles. The browser preview has **no build step**, so
you MUST use the classic UMD build (global `THREE`) — NOT `import ... from
'three'` (needs bundler) and NOT `three.module.js` (needs `<script type=module>`).

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
```

- `three.min.js` → global `THREE` object.
- `OrbitControls.js` (examples/js) → adds `THREE.OrbitControls`. It must come
  AFTER three.min.js and from the SAME pinned version (0.128.0) or the control
  fails to attach.
- Load both in `<head>` (or top of body) before any scene code.
- **Always** guard with a fallback message: if `typeof THREE === 'undefined'`
  (CDN blocked/offline), show a readable error on the page instead of a blank
  screen. This is a hard rule — a silent black canvas is a failed app.

```js
function showFallback(msg) {
  document.body.innerHTML = '<div style="font-family:sans-serif;color:#fff;background:#111;padding:24px">3D unavailable: ' + msg + '</div>';
}
```

---

## 2. Scene skeleton (the 15 lines everything hangs off)

```js
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);
scene.fog = new THREE.Fog(0x0d1117, 30, 80);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(10, 8, 12);
camera.lookAt(0, 1, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;                 // ← shadows ON = instant depth
renderer.shadowMap.type = THREE.PCFSoftShadowMap;  // ← soft shadows
renderer.toneMapping = THREE.ACESFilmicToneMapping; // ← filmic look
renderer.outputEncoding = THREE.sRGBEncoding;       // r128: correct color
document.body.appendChild(renderer.domElement);     // ← MUST append or nothing shows

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;      // smooth inertia
controls.target.set(0, 1, 0);

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
```

Rules: canvas must fill the viewport via CSS (`html,body{margin:0;height:100%}`
and `#canvas`/body background), `requestAnimationFrame` must run the loop, and
`resize` must update both camera and renderer or the scene distorts.

---

## 3. Lighting recipe that makes scenes look "rendered" not flat

```js
const ambient = new THREE.AmbientLight(0xffffff, 0.35);
scene.add(ambient);

const key = new THREE.DirectionalLight(0xffeedd, 1.0);   // warm key
key.position.set(8, 12, 6);
key.castShadow = true;
key.shadow.mapSize.set(1024, 1024);
key.shadow.camera.left = -10; key.shadow.camera.right = 10;
key.shadow.camera.top = 10;  key.shadow.camera.bottom = -10;
key.shadow.camera.near = 0.5; key.shadow.camera.far = 40;
key.shadow.bias = -0.0005;                                // ← kills shadow acne
scene.add(key);

const fill = new THREE.DirectionalLight(0x4466ff, 0.3);   // cool fill
fill.position.set(-6, 4, -8);
scene.add(fill);
```

Rule of thumb: ambient (fill in the blacks) + one bright key with shadows +
optional cool rim/fill = "dazzling" with 3 lights and no shaders.

---

## 4. Materials & the "premium" look

```js
// Standard PBR-ish material (metalness/roughness = cheap realism)
const gold = new THREE.MeshStandardMaterial({
  color: 0xd4af37, metalness: 0.85, roughness: 0.35,
});
const wood = new THREE.MeshStandardMaterial({ color: 0x8b5a2b, roughness: 0.6 });
const glass = new THREE.MeshStandardMaterial({ color: 0x88ccff, metalness: 0.1, roughness: 0.15, transparent: true, opacity: 0.85 });

// If the scene must run on weak machines, MeshPhongMaterial is the cheap twin:
const phong = new THREE.MeshPhongMaterial({ color: 0xd4af37, shininess: 80 });
```

- **MeshStandardMaterial + metalness/roughness** reads as "3D render".
- Set `castShadow = true` on objects, `receiveShadow = true` on the floor.
- A dark background + strong key light + metal material = the whole "stunning" effect.

---

## 5. Chess piece geometry (LatheGeometry profiles)

Chess pieces are rotationally symmetric — `THREE.LatheGeometry` is the exact
tool. Profile points are Vector2(radius, height) from bottom to top; the lathe
spins them 360° around the Y axis. These profiles produce recognizable pieces
(simplified, clean, no poly explosions):

```js
function lathePiece(profile, material) {
  const geo = new THREE.LatheGeometry(profile, 32);
  const mesh = new THREE.Mesh(geo, material);
  mesh.castShadow = true;
  return mesh;
}

// PAWN
const pawnProfile = [
  new THREE.Vector2(0.00, 0.00), new THREE.Vector2(0.30, 0.00),
  new THREE.Vector2(0.34, 0.06), new THREE.Vector2(0.22, 0.28),
  new THREE.Vector2(0.16, 0.50), new THREE.Vector2(0.13, 0.72),
  new THREE.Vector2(0.09, 0.86), new THREE.Vector2(0.16, 0.94),
  new THREE.Vector2(0.18, 1.00), new THREE.Vector2(0.12, 1.00),
  new THREE.Vector2(0.12, 0.94), new THREE.Vector2(0.00, 0.94),
];

// ROOK (cylinder body + crenellated top)
const rookProfile = [
  new THREE.Vector2(0.00, 0.00), new THREE.Vector2(0.34, 0.00),
  new THREE.Vector2(0.34, 0.72), new THREE.Vector2(0.28, 0.72),
  new THREE.Vector2(0.28, 0.80), new THREE.Vector2(0.30, 0.80),
  new THREE.Vector2(0.30, 0.88), new THREE.Vector2(0.26, 0.88),
  new THREE.Vector2(0.26, 0.96), new THREE.Vector2(0.30, 0.96),
  new THREE.Vector2(0.30, 1.00), new THREE.Vector2(0.24, 1.00),
  new THREE.Vector2(0.24, 0.94), new THREE.Vector2(0.20, 0.94),
  new THREE.Vector2(0.20, 1.00), new THREE.Vector2(0.14, 1.00),
  new THREE.Vector2(0.14, 0.94), new THREE.Vector2(0.10, 0.94),
  new THREE.Vector2(0.10, 1.00), new THREE.Vector2(0.00, 1.00),
];

// KNIGHT (base + tapered neck; the horse head reads from the silhouette)
const knightProfile = [
  new THREE.Vector2(0.00, 0.00), new THREE.Vector2(0.32, 0.00),
  new THREE.Vector2(0.32, 0.10), new THREE.Vector2(0.24, 0.34),
  new THREE.Vector2(0.18, 0.56), new THREE.Vector2(0.16, 0.78),
  new THREE.Vector2(0.18, 0.90), new THREE.Vector2(0.26, 1.00),
  new THREE.Vector2(0.20, 1.00), new THREE.Vector2(0.00, 1.00),
];

// BISHOP (tall body + mitre + the small ball on top)
const bishopProfile = [
  new THREE.Vector2(0.00, 0.00), new THREE.Vector2(0.30, 0.00),
  new THREE.Vector2(0.32, 0.08), new THREE.Vector2(0.20, 0.30),
  new THREE.Vector2(0.14, 0.60), new THREE.Vector2(0.11, 0.82),
  new THREE.Vector2(0.08, 0.92), new THREE.Vector2(0.16, 0.96),
  new THREE.Vector2(0.14, 1.00), new THREE.Vector2(0.08, 1.00),
  new THREE.Vector2(0.08, 0.94), new THREE.Vector2(0.00, 0.94),
];

// QUEEN (wide base, rings, crown)
const queenProfile = [
  new THREE.Vector2(0.00, 0.00), new THREE.Vector2(0.36, 0.00),
  new THREE.Vector2(0.36, 0.06), new THREE.Vector2(0.26, 0.18),
  new THREE.Vector2(0.20, 0.46), new THREE.Vector2(0.15, 0.74),
  new THREE.Vector2(0.12, 0.90), new THREE.Vector2(0.20, 0.98),
  new THREE.Vector2(0.20, 1.00), new THREE.Vector2(0.12, 1.00),
  new THREE.Vector2(0.12, 0.92), new THREE.Vector2(0.00, 0.92),
];

// KING (like queen but taller + cross on top)
const kingProfile = [
  new THREE.Vector2(0.00, 0.00), new THREE.Vector2(0.36, 0.00),
  new THREE.Vector2(0.36, 0.06), new THREE.Vector2(0.26, 0.16),
  new THREE.Vector2(0.20, 0.42), new THREE.Vector2(0.15, 0.70),
  new THREE.Vector2(0.12, 0.86), new THREE.Vector2(0.18, 0.94),
  new THREE.Vector2(0.18, 1.04), new THREE.Vector2(0.22, 1.08),
  new THREE.Vector2(0.22, 1.12), new THREE.Vector2(0.00, 1.12),
];

// Cross on the king: two small boxes at the top
function kingCross(material) {
  const g = new THREE.Group();
  const v = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.22, 0.08), material);
  const h = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.07, 0.07), material);
  v.position.y = 1.24; h.position.y = 1.30; h.position.z = 0.02;
  g.add(v, h); g.traverse(o => o.castShadow = true); return g;
}
```

The knight's horse-head is hard to lathe convincingly — the standard trick is
the tapered-neck profile plus rotating the piece slightly; it reads fine at
game scale. For hero pieces, swap in a Box/Sphere composite.

---

## 6. Board / floor with a checkerboard texture

```js
function checkerTexture(size = 8, c1 = 0xf0d9b5, c2 = 0xb58863) {
  const cv = document.createElement('canvas');
  cv.width = cv.height = size * 64;
  const ctx = cv.getContext('2d');
  for (let r = 0; r < size; r++) for (let c = 0; c < size; c++) {
    ctx.fillStyle = ((r + c) % 2 === 0) ? '#' + c1.toString(16).padStart(6, '0')
                                        : '#' + c2.toString(16).padStart(6, '0');
    ctx.fillRect(c * 64, r * 64, 64, 64);
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.anisotropy = 4;
  return tex;
}

const board = new THREE.Mesh(
  new THREE.BoxGeometry(size, 0.15, size),           // slab with thickness
  new THREE.MeshStandardMaterial({ map: checkerTexture() })
);
board.position.y = -0.075; board.receiveShadow = true;
scene.add(board);
```

Squares land at integer (x, z) grid positions — `(col - 3.5, row - 3.5)` maps
file/rank to world coordinates. Keep the board receiving shadows and pieces
casting them.

---

## 7. Movement animation (the "alive" factor)

Lerp in the render loop — simple, smooth, interruption-safe:

```js
const MOVES = []; // {mesh, from, to, t}
function animateMove(mesh, from, to, duration = 500) {
  MOVES.push({ mesh, from, to, t: 0, dur: duration });
}
function easeInOut(k) { return k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; }

// inside animate(): step moves
for (let i = MOVES.length - 1; i >= 0; i--) {
  const m = MOVES[i];
  m.t += 16.67 / m.dur;                      // per-frame at 60fps
  const k = easeInOut(Math.min(m.t, 1));
  m.mesh.position.lerpVectors(m.from, m.to, k);
  if (m.t >= 1) MOVES.splice(i, 1);
}
```

Capture animation: animate the captured piece up + fade (transparent material)
while the mover lerps onto the square — two parallel entries in MOVES.

Intro sweep: animate `camera.position` from a high wide shot to the play
position over ~1.5s with the same lerp machinery.

---

## 8. Particles (cheap sparkle/atmosphere)

```js
function starfield(n = 800, spread = 60) {
  const pos = new Float32Array(n * 3);
  for (let i = 0; i < n * 3; i++) pos[i] = (Math.random() - 0.5) * spread * 2;
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.15, transparent: true, opacity: 0.8 });
  const pts = new THREE.Points(geo, mat);
  pts.position.y = 12;
  return pts;
}
```

---

## 9. CSS 3D fallback (no WebGL — still looks dimensional)

```html
<style>
  .stage { perspective: 900px; }
  .board { transform: rotateX(55deg) rotateZ(45deg);
           transform-style: preserve-3d; }
  .piece { transform: translateZ(calc(var(--h) * 1px)); }
</style>
```

Good for faux-3D menus, cards, and simple boards; does NOT do shadows/reflections.

---

## 10. Failure modes — check these before calling the app done

| Symptom | Cause → Fix |
|---|---|
| Blank black canvas | Renderer never appended, or `THREE` undefined (CDN blocked) → guard + append |
| Page shows but no 3D | CDN URL typo / version mismatch between three.min.js and OrbitControls.js → pin BOTH to 0.128.0 |
| `THREE.OrbitControls is not a constructor` | examples/js control missing or wrong version → load after three.min.js, same version |
| Everything flat, no shadows | `renderer.shadowMap.enabled` false, or objects lack `castShadow`, floor lacks `receiveShadow` |
| Shadow acne / wavy lines | `shadow.bias = -0.0005` missing on the light |
| Z-fighting stripes on board | Two coplanar surfaces → add `polygonOffset` or nudge by 0.001 |
| Scene stretched | Missing resize handler → update camera aspect + renderer size |
| Very dark scene | Tone mapping without enough light → raise light intensity (1.5–2 with ACES) |
| WebGL context lost | Too many large textures → cap pixelRatio at 2, reuse materials |
| `requestAnimationFrame` never starts | Loop not launched after renderer append → call `animate()` |

**Final checklist:** single self-contained HTML · both CDN scripts pinned to
0.128.0 · `typeof THREE` guard with on-screen fallback · renderer appended ·
shadows on · resize handler · animation loop running · canvas fills viewport.

---

## Quick Reference by Node Type

| Node | 3D recipe |
|---|---|
| **ui / output** | Canvas fills viewport; HUD as HTML overlay (absolute-positioned div) |
| **logic** | Game rules in plain JS (board state, legal moves) — keep 3D code separate |
| **input** | Raycaster click on board plane to pick squares; hover via `pointermove` |
| **api / database** | Not 3D — fetch/save behind the scene; never block the render loop |

**Bible cross-reference:** `35-computer-graphics-gpu.md` (pipeline, shaders,
WebGPU) · `30-browser-engineering.md` (canvas/rendering internals) ·
`12-game-development-patterns.md` (game loop, AI, ECS).
