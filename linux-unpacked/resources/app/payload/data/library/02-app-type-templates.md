# 🏗️ App Type Templates

> Ready-to-use architecture templates for common application types.
> Each template includes recommended node structure, languages, and data flow.

---

## Template Quick Reference

| App Type | Nodes | Primary Language | Database | Interface |
|---|---|---|---|---|
| **CLI Tool** | 3-5 | Go / TypeScript | SQLite / None | Terminal |
| **Web App** | 5-8 | TypeScript (full-stack) | SQLite / PostgreSQL | Web Browser |
| **Media Server** | 6-10 | TypeScript + Python | SQLite | Web UI + Native |
| **System Tool** | 4-7 | Go | SQLite | Terminal UI |
| **Desktop App** | 4-6 | TypeScript | SQLite | Native Linux UI |
| **API Server** | 3-5 | TypeScript / Python | PostgreSQL | REST / GraphQL |
| **Data Processor** | 3-4 | Python | SQLite / Files | CLI / Web |
| **Game** | 5-8 | TypeScript / Go | SQLite | Web / Desktop |
| **Auth App** | 5-7 | TypeScript | PostgreSQL | Web Browser |
| **Chat App** | 5-8 | TypeScript | SQLite / PostgreSQL | Web Browser |
| **E-commerce** | 6-8 | TypeScript | PostgreSQL | Web Browser |
| **Dashboard** | 4-6 | TypeScript | SQLite / PostgreSQL | Web Browser |
| **File Sync Tool** | 3-5 | Go / TypeScript | SQLite | CLI / Tray |
| **Booking App** | 5-7 | TypeScript | PostgreSQL | Web Browser |
| **CMS** | 5-7 | TypeScript | SQLite / PostgreSQL | Web Browser |
| **3D App** | 4-8 | TypeScript / JS (browser) | None | Web Browser (WebGL) |

---

## 1. CLI Tool Template

Best for: System utilities, file processors, dev tools

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Input    │────▶│  Logic   │────▶│  Output  │
│  (CLI)   │     │          │     │  (Print) │
└──────────┘     └────┬─────┘     └──────────┘
                      │
               ┌──────▼──────┐
               │  Database   │
               │  (SQLite)   │
               └─────────────┘
```

### Recommended Languages
- **Primary:** Go (single binary, fast startup)
- **Alternative:** TypeScript (Node.js with `commander` or `yargs`)
- **Python:** For data-heavy CLI tools

### Key Libraries
- **Go:** `spf13/cobra`, `spf13/viper`, `charmbracelet/bubbletea`
- **TypeScript:** `commander`, `inquirer`, `chalk`, `ora`
- **Python:** `click`, `rich`, `typer`

### Generated File Structure
```
project/
├── cmd/
│   └── app/
│       └── main.go / main.ts
├── pkg/ or src/
│   ├── input/       # Input handling
│   ├── logic/        # Business logic
│   ├── db/           # Database layer
│   └── output/       # Output formatting
├── config/
│   └── config.yaml
├── Makefile
└── README.md
```

---

## 2. Web App Template

Best for: Dashboards, management tools, collaborative apps

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  API     │────▶│  Logic   │
│  (React) │     │  Router  │     │          │
└──────────┘     └──────────┘     └────┬─────┘
                                       │
                                ┌──────▼──────┐
                                │  Database   │
                                │  (SQLite)   │
                                └─────────────┘
```

### Recommended Languages
- **Frontend:** TypeScript + React
- **Backend:** TypeScript (Express) or Python (FastAPI)

### Key Libraries
- **Frontend:** React, React Router, TanStack Query, Tailwind CSS
- **Backend:** Express, FastAPI, Zod/Pydantic validation
- **Database:** SQLite (`better-sqlite3`), Drizzle ORM / SQLAlchemy

### Generated File Structure
```
project/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   └── App.tsx
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── db/
│   │   └── index.ts
│   └── package.json
└── README.md
```

---

## 3. Media Server Template

Best for: Home streaming, media management, audio/video processing

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Library │────▶│  Scanner │────▶│  Stream  │
│  (DB)    │     │  (Logic) │     │  Server  │
└──────────┘     └──────────┘     └────┬─────┘
      ▲                                 │
      │                          ┌──────▼──────┐
      │                          │  Web UI     │
      └──────────────────────────│  (React)    │
                                 └─────────────┘
```

### Recommended Languages
- **Backend:** TypeScript (Node.js for I/O efficiency)
- **Media Processing:** Python (FFmpeg bindings)
- **UI:** TypeScript + React

### Key Libraries
- **Streaming:** FFmpeg, `fluent-ffmpeg` (Node), HTTP Live Streaming
- **Media:** `music-metadata`, `sharp` (images), `ffmpeg-python`
- **UI:** React, video.js, howler.js

### Generated File Structure
```
project/
├── src/
│   ├── scanner/        # Media file scanner
│   ├── library/        # Media library management
│   ├── transcoder/     # Media conversion (FFmpeg)
│   ├── stream/         # Streaming server
│   ├── api/            # REST API endpoints
│   └── ui/             # React frontend
├── data/               # Media database & config
├── package.json
└── README.md
```

---

## 4. System Tool Template

Best for: Diagnostics, monitoring, system management

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Collector│────▶│  Checks  │────▶│  Report  │
│ (Input)  │     │ (Logic)  │     │ (Output) │
└──────────┘     └────┬─────┘     └──────────┘
                      │
               ┌──────▼──────┐     ┌──────────┐
               │  Database   │────▶│   TUI    │
               │  (SQLite)   │     │  (View)  │
               └─────────────┘     └──────────┘
```

### Recommended Languages
- **Primary:** Go (single binary, system-level access)
- **Alternative:** Python (rich system libraries)

### Key Libraries
- **Go:** `shirou/gopsutil`, `charmbracelet/bubbletea`, `spf13/cobra`
- **Python:** `psutil`, `rich`, `click`

### Generated File Structure
```
project/
├── cmd/
│   └── app/main.go
├── pkg/
│   ├── collector/     # System information gathering
│   ├── checks/        # Health check engine
│   ├── db/            # SQLite database
│   ├── report/        # Report generation
│   └── tui/           # Terminal UI
├── Makefile
└── README.md
```

---

## 5. Desktop App Template (Web-based UI)

Best for: Productivity tools, file managers, media players

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  Logic   │────▶│  Files   │
│  (React) │     │          │     │  (FS)    │
└──────────┘     └────┬─────┘     └──────────┘
                      │
               ┌──────▼──────┐
               │  Database   │
               │  (SQLite)   │
               └─────────────┘
```

### Recommended Languages
- **Frontend:** TypeScript + React (Vite)
- **Backend:** TypeScript (Electron-like or local server)

### Key Libraries
- **UI:** React, Vite, Tailwind CSS
- **Desktop:** Capacitor (for Linux desktop wrapping)
- **Storage:** SQLite, File System Access API

---

## 6. API Server Template

Best for: Microservices, backend-only apps, mobile backends

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Router  │────▶│  Auth    │────▶│  Logic   │
│  (HTTP)  │     │  Middle  │     │          │
└──────────┘     └──────────┘     └────┬─────┘
                                       │
                                ┌──────▼──────┐
                                │  Database   │
                                └─────────────┘
```

### Recommended Languages
- **Primary:** TypeScript (Express or Fastify, fast and typed)
- **Alternative:** Python (FastAPI, async with automatic docs)
- **Also:** Go (Gin or Chi for performance)

---

## 7. Auth App Template

Best for: Login/registration, user accounts, session management, OAuth

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  Auth    │────▶│  Logic  │
│  (Login) │     │ (Logic)  │     │          │
└──────────┘     └────┬─────┘     └────┬─────┘
                      │                │
               ┌──────▼──────┐  ┌──────▼──────┐
               │  Database   │  │  Sessions   │
               │  (Users)    │  │   (Cache)   │
               └─────────────┘  └─────────────┘
```

### Recommended Languages
- **Primary:** TypeScript (full-stack, typed sessions and payloads)
- **Alternative:** Python (FastAPI) backend

### Key Libraries
- **Auth:** `argon2` / `bcrypt`, `jsonwebtoken`, `lucia` or `passport`
- **Backend:** Express or Fastify, Zod (schema validation)
- **Frontend:** React, React Router, TanStack Query
- **Database:** PostgreSQL (`pg`), Drizzle ORM

### Generated File Structure
```
project/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Register.tsx
│   │   │   └── Profile.tsx
│   │   ├── components/
│   │   ├── api/
│   │   └── App.tsx
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   │   ├── auth.ts
│   │   │   └── users.ts
│   │   ├── services/
│   │   │   ├── password.ts
│   │   │   └── session.ts
│   │   ├── db/
│   │   │   ├── schema.ts
│   │   │   └── repository.ts
│   │   └── index.ts
│   └── package.json
└── README.md
```

---

## 8. Chat App Template

Best for: Real-time messaging, rooms, support widgets

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  Chat    │────▶│  Logic  │
│  (Web)   │     │  (Room)  │     │          │
└──────────┘     └────┬─────┘     └────┬─────┘
                      │                │
               ┌──────▼──────┐  ┌──────▼──────┐
               │  Database   │  │  Realtime   │
               │  (History)  │  │    (WS)     │
               └─────────────┘  └─────────────┘
```

### Recommended Languages
- **Primary:** TypeScript (full-stack, shared message types)
- **Realtime:** Node.js (WebSockets via `socket.io`)

### Key Libraries
- **Realtime:** `socket.io` or `ws`
- **Backend:** Express, Zod
- **Frontend:** React, React Router
- **Database:** SQLite (`better-sqlite3`) or PostgreSQL

### Generated File Structure
```
project/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageInput.tsx
│   │   │   └── RoomList.tsx
│   │   ├── hooks/
│   │   │   └── useSocket.ts
│   │   ├── api/
│   │   └── App.tsx
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   │   └── rooms.ts
│   │   ├── sockets/
│   │   │   └── chat.ts
│   │   ├── services/
│   │   │   └── messageStore.ts
│   │   ├── db/
│   │   └── index.ts
│   └── package.json
└── README.md
```

---

## 9. E-commerce Template

Best for: Online stores, product catalogs, checkout, orders

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  Cart    │────▶│  Logic  │
│  (Shop)  │     │  (Order) │     │          │
└──────────┘     └────┬─────┘     └────┬─────┘
                      │                │
               ┌──────▼──────┐  ┌──────▼──────┐
               │  Database   │  │  Payments   │
               │  (Products) │  │    (API)    │
               └─────────────┘  └─────────────┘
```

### Recommended Languages
- **Primary:** TypeScript (full-stack)
- **Alternative:** Python (FastAPI) backend

### Key Libraries
- **Payments:** `stripe`, `paypal-rest-sdk`
- **Backend:** Express or Fastify, Zod
- **Frontend:** React, React Router, TanStack Query
- **Database:** PostgreSQL (`pg`), Drizzle ORM

### Generated File Structure
```
project/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ProductList.tsx
│   │   │   ├── ProductDetail.tsx
│   │   │   └── Checkout.tsx
│   │   ├── components/
│   │   │   └── Cart.tsx
│   │   ├── api/
│   │   └── App.tsx
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   │   ├── products.ts
│   │   │   ├── cart.ts
│   │   │   └── orders.ts
│   │   ├── services/
│   │   │   ├── inventory.ts
│   │   │   └── payment.ts
│   │   ├── db/
│   │   │   ├── schema.ts
│   │   │   └── seed.ts
│   │   └── index.ts
│   └── package.json
└── README.md
```

---

## 10. Dashboard Template

Best for: Analytics, metrics monitoring, admin panels

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  Widgets │────▶│  Logic  │
│ (Panels) │     │ (Charts) │     │          │
└──────────┘     └────┬─────┘     └────┬─────┘
                      │                │
               ┌──────▼──────┐  ┌──────▼──────┐
               │  Database   │  │  Data API   │
               │  (Metrics)  │  │  (Source)   │
               └─────────────┘  └─────────────┘
```

### Recommended Languages
- **Primary:** TypeScript (React + Express)
- **Alternative:** Python (FastAPI) + Plotly

### Key Libraries
- **Charts:** `recharts`, `chart.js`, `d3`
- **Backend:** Express or FastAPI
- **Frontend:** React, TanStack Query, Tailwind CSS
- **Database:** SQLite (`better-sqlite3`) or PostgreSQL

### Generated File Structure
```
project/
├── frontend/
│   ├── src/
│   │   ├── widgets/
│   │   │   ├── ChartWidget.tsx
│   │   │   ├── StatWidget.tsx
│   │   │   └── TableWidget.tsx
│   │   ├── layouts/
│   │   │   └── GridLayout.tsx
│   │   ├── api/
│   │   └── App.tsx
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   │   └── metrics.ts
│   │   ├── services/
│   │   │   ├── aggregator.ts
│   │   │   └── exporter.ts
│   │   ├── db/
│   │   └── index.ts
│   └── package.json
└── README.md
```

---

## 11. File Sync Tool Template

Best for: Folder mirroring, backup tools, cloud sync clients

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Watcher │────▶│  Sync    │────▶│  Index   │
│  (Input) │     │ (Logic)  │     │ (SQLite) │
└──────────┘     └────┬─────┘     └──────────┘
                      │
               ┌──────▼──────┐
               │  Remote     │
               │    (API)    │
               └─────────────┘
```

### Recommended Languages
- **Primary:** Go (single binary, cross-platform)
- **Alternative:** TypeScript (Node.js) for a tray or web client

### Key Libraries
- **Go:** `fsnotify`, `rclone` (sync engine), `spf13/cobra`
- **TypeScript:** `chokidar`, `commander`
- **Storage:** SQLite (`modernc.org/sqlite` or `better-sqlite3`)

### Generated File Structure
```
project/
├── cmd/
│   └── app/
│       └── main.go / main.ts
├── pkg/ or src/
│   ├── watcher/        # File system watcher
│   ├── sync/           # Sync engine (diff + transfer)
│   ├── index/          # File index (SQLite)
│   └── remote/         # Remote storage client
├── config/
│   └── config.yaml
├── Makefile
└── README.md
```

---

## 12. Booking App Template

Best for: Reservations, appointment scheduling, capacity management

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  Booking │────▶│  Logic   │
│  (Cal)   │     │  (Logic) │     │  (Rules) │
└──────────┘     └────┬─────┘     └────┬─────┘
                      │                │
               ┌──────▼──────┐  ┌──────▼──────┐
               │  Database   │  │  Payments   │
               │  (Slots)    │  │    (API)    │
               └─────────────┘  └─────────────┘
```

### Recommended Languages
- **Primary:** TypeScript (full-stack)
- **Alternative:** Python (FastAPI) backend

### Key Libraries
- **Backend:** Express or Fastify, Zod
- **Scheduling:** `node-cron`, `date-fns`
- **Frontend:** React, TanStack Query
- **Payments:** `stripe`
- **Database:** PostgreSQL (`pg`), Drizzle ORM

### Generated File Structure
```
project/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Availability.tsx
│   │   │   ├── BookingForm.tsx
│   │   │   └── Confirmation.tsx
│   │   ├── components/
│   │   │   └── Calendar.tsx
│   │   ├── api/
│   │   └── App.tsx
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   │   ├── availability.ts
│   │   │   ├── bookings.ts
│   │   │   └── payments.ts
│   │   ├── services/
│   │   │   ├── scheduler.ts
│   │   │   └── capacity.ts
│   │   ├── db/
│   │   │   ├── schema.ts
│   │   │   └── repository.ts
│   │   └── index.ts
│   └── package.json
└── README.md
```

---

## 13. CMS Template

Best for: Blogs, content publishing, admin editing

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  UI      │────▶│  Content │────▶│  Logic   │
│  (Admin) │     │ (Editor) │     │          │
└──────────┘     └────┬─────┘     └────┬─────┘
                      │                │
               ┌──────▼──────┐  ┌──────▼──────┐
               │  Database   │  │  Publish    │
               │  (Posts)    │  │    (API)    │
               └─────────────┘  └─────────────┘
```

### Recommended Languages
- **Primary:** TypeScript (full-stack)
- **Alternative:** Python (Django or FastAPI)

### Key Libraries
- **Editor:** TipTap or Lexical, `marked` (markdown)
- **Backend:** Express or Fastify, Zod
- **Frontend:** React, React Router
- **Database:** SQLite (`better-sqlite3`) or PostgreSQL

### Generated File Structure
```
project/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Admin.tsx
│   │   │   └── PostView.tsx
│   │   ├── components/
│   │   │   └── Editor.tsx
│   │   ├── api/
│   │   └── App.tsx
│   ├── index.html
│   └── vite.config.ts
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   │   ├── posts.ts
│   │   │   └── media.ts
│   │   ├── services/
│   │   │   ├── content.ts
│   │   │   └── publish.ts
│   │   ├── db/
│   │   │   ├── schema.ts
│   │   │   └── repository.ts
│   │   └── index.ts
│   └── package.json
└── README.md
```

---

## 14. 3D App Template

> For 3D scenes, 3D games (chess, maze, builder, visualizer), rotating logos,
> particle effects, and anything needing real perspective depth.
> **Rendering recipe: `44-threejs-scene-recipes.md` (read it before coding).**

| Aspect | Recommendation |
|---|---|
| **Entry** | Single self-contained `index.html` — inline CSS + JS, NO build step. Use Three.js r128 UMD via CDN (global `THREE`), never ES module imports. |
| **Nodes** | `ui` (canvas fills viewport + HTML overlay HUD) · `logic` (game/rules state in plain JS, kept separate from rendering) · `input` (Raycaster for click/hover picking) · optional `api`/`database` (persistence behind the scene) |
| **Rendering** | WebGLRenderer + antialias + shadowMap (PCFSoft) + ACESFilmicToneMapping; ambient + key directional light with shadows; MeshStandardMaterial metalness/roughness |
| **Animation** | requestAnimationFrame loop; lerp-based move easing; intro camera sweep; capture fly+fade |
| **Controls** | THREE.OrbitControls (examples/js, pinned to the SAME three version) with damping |
| **Failure safety** | `typeof THREE` guard + on-screen fallback message; resize handler; never blank canvas |
| **Fallback tech** | CSS 3D transforms (no WebGL) or Canvas-2D isometric for low-risk "2.5D" requests |

```
3D Game = ui (index.html w/ Three.js) + logic (rules + AI) + input (Raycaster)
3D Viewer = ui (index.html) + logic (object load/animate) + input (OrbitControls)
3D Dashboard = ui (index.html + HUD overlay) + logic (data → mesh transforms)
```

---

## Template Selection Guide

When a user requests an app, match their request to the closest template:

| User Says | Use Template |
|---|---|
| "scan my system" | System Tool |
| "stream media" | Media Server |
| "manage tasks" | Web App |
| "convert files" | CLI Tool |
| "build a player" | Desktop App |
| "create an API" | API Server |
| "analyze data" | Data Processor / CLI Tool |
| "make a game" | Game Template |
| "log in users" | Auth App |
| "authenticate users" | Auth App |
| "user accounts" | Auth App |
| "build a chat" | Chat App |
| "real-time messaging" | Chat App |
| "online store" | E-commerce |
| "shopping cart" | E-commerce / Web App |
| "sell products" | E-commerce |
| "analytics dashboard" | Dashboard |
| "monitor metrics" | Dashboard / Web App |
| "admin panel" | Dashboard / Web App |
| "sync files" | File Sync Tool |
| "backup folders" | File Sync Tool |
| "mirror directories" | File Sync Tool |
| "book a reservation" | Booking App |
| "3d chess" / "3d game" / "3d scene" | 3D App |
| "rotating logo" / "webgl" / "perspective" | 3D App |
| "scheduling app" | Booking App |
| "appointment booking" | Booking App / Web App |
| "content management" | CMS |
| "blog platform" | CMS |
| "publish articles" | CMS |

### Hybrid Templates

For complex requests, combine templates:

```
Media Server + Desktop App = Media Player with Web Remote
System Tool + Web App = System Dashboard
CLI Tool + Web App = CLI with Web GUI
Auth App + Web App = Members Only Web App
Chat App + E-commerce = Live Shopping with Chat Support
Dashboard + API Server = Metrics Dashboard over Microservices
File Sync Tool + Web App = Cloud Sync Dashboard
Booking App + Chat App = Appointment Chat Reminders
CMS + E-commerce = Store with Content Management
```

---

*For deep technical implementation of each app type's components, see `bible-reference/` via MASTER-INDEX.txt*
