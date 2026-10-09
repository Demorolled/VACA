# 🖥️ Desktop Application Architecture

> Reference for building Linux desktop applications — event loops, GUI patterns, packaging, and Linux integration.
> Extracted from The Programming Bible's Desktop Apps level. Apply these when generating desktop app code.

---

## 1. Desktop App Architecture Overview

```
┌─────────────────────────────────────────────┐
│            DESKTOP APPLICATION               │
│                                               │
│  ┌─────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ Window   │  │ Widget   │  │ Event Loop   │ │
│  │ Manager  │  │ Tree     │  │ (Main Loop)  │ │
│  └────┬────┘  └────┬─────┘  └──────┬──────┘ │
│       │            │               │         │
│  ┌────▼────────────▼───────────────▼──────┐  │
│  │           Application Logic             │  │
│  │   (Service Layer / Business Logic)      │  │
│  └────────────┬───────────────────────────┘  │
│               │                              │
│  ┌────────────▼───────────┐                  │
│  │  Data Layer            │                  │
│  │  (SQLite / File I/O)   │                  │
│  └────────────────────────┘                  │
└─────────────────────────────────────────────┘
```

### Architectural Patterns

| Pattern | Description | When to Use |
|---|---|---|
| **MVC** | Model-View-Controller — separates data, UI, input | Classic desktop apps |
| **MVP** | Model-View-Presenter — View is passive, Presenter handles logic | Testable UIs |
| **MVVM** | Model-View-ViewModel — data binding, ViewModel holds state | Complex UIs with two-way binding |
| **Passive View** | View has zero logic — just template binding | Maximum testability |
| **Supervising Controller** | View handles simple bindings, controller handles complex logic | Pragmatic balance |

---

## 2. Event Loop & Windowing

The event loop is the heart of every desktop application. It processes OS events and drives application behavior.

### Wait Strategies

| Strategy | Behavior | Use Case |
|---|---|---|
| **Poll** | Busy-wait, continuously checks for events | ❌ High CPU, only for specialized cases |
| **Wait/Block** | Thread sleeps until next event arrives | ✅ Idle apps, background services |
| **Wait with Timeout** | Sleep until event or timeout | ✅ Recommended — supports animations + background tasks |

### Event Loop Implementation

```typescript
// Cross-platform event loop
interface Event {
  type: string;
  timestamp: number;
  data: Record<string, unknown>;
}

class EventLoop {
  private running = false;
  private eventQueue: Event[] = [];
  private handlers: Map<string, ((event: Event) => void)[]> = new Map();
  private timers: Timer[] = [];
  private frameCallbacks: FrameCallback[] = [];
  private wakeup: () => void = () => {};

  on(eventType: string, handler: (event: Event) => void): void {
    if (!this.handlers.has(eventType)) this.handlers.set(eventType, []);
    this.handlers.get(eventType)!.push(handler);
  }

  postEvent(event: Event): void {
    this.eventQueue.push(event);
    this.wakeup(); // Wake up the event loop
  }

  setInterval(callback: () => void, ms: number): Timer {
    const timer = { callback, interval: ms, nextFire: Date.now() + ms, active: true };
    this.timers.push(timer);
    return timer;
  }

  requestAnimationFrame(callback: (dt: number) => void): void {
    this.frameCallbacks.push({ callback, scheduled: true });
  }

  run(): void {
    this.running = true;
    let lastTime = performance.now();

    while (this.running) {
      // Process pending events
      while (this.eventQueue.length > 0) {
        const event = this.eventQueue.shift()!;
        const handlers = this.handlers.get(event.type) ?? [];
        for (const handler of handlers) {
          handler(event);
        }
      }

      // Process timers
      const now = Date.now();
      for (const timer of this.timers) {
        if (timer.active && now >= timer.nextFire) {
          timer.callback();
          timer.nextFire = now + timer.interval;
        }
      }

      // Animation frames
      const currentTime = performance.now();
      const dt = (currentTime - lastTime) / 1000;
      for (const cb of this.frameCallbacks) {
        if (cb.scheduled) cb.callback(dt);
      }
      lastTime = currentTime;

      // Wait for next event (with timeout for animations)
      this.waitForEvents(this.computeWaitTime());
    }
  }

  private computeWaitTime(): number {
    const nextTimer = Math.min(...this.timers.filter(t => t.active).map(t => t.nextFire - Date.now()));
    const hasFrameCallbacks = this.frameCallbacks.some(f => f.scheduled);
    return hasFrameCallbacks ? 16 : Math.max(0, nextTimer); // ~60fps if animating
  }

  private waitForEvents(timeout: number): void {
    // Platform-specific: select/poll/epoll on Linux, WaitMessage on Windows
    // This is the platform-dependent part
    if (timeout > 0) {
      // Block until event or timeout — uses epoll/select on Linux
    }
  }

  quit(): void {
    this.running = false;
    this.wakeup();
  }
}
```

### Platform-Specific Event Sources

| Platform | Event Wait API | Notes |
|---|---|---|
| **Linux (X11)** | `XNextEvent`, `XPending` | Traditional, network-transparent |
| **Linux (Wayland)** | `wl_display_dispatch_queue` | Modern, per-client buffering |
| **Linux (generic)** | `poll`/`epoll` on FD | Used by toolkits like SDL, GTK |
| **Windows** | `GetMessage`, `PeekMessage` | Win32 native |
| **macOS** | `CFRunLoop`, `NSEvent` | Cocoa native |

---

## 3. Widget Toolkit Architecture

### Widget Tree Structure

```
Application
└── MainWindow
    ├── MenuBar
    │   ├── FileMenu
    │   │   ├── MenuItem("New")
    │   │   └── MenuItem("Quit")
    │   └── EditMenu
    └── Content
        ├── Sidebar
        │   ├── TreeView
        │   └── SearchBox
        └── MainPanel
            ├── Toolbar
            │   ├── Button("Save")
            │   └── Button("Delete")
            └── Canvas/EditorArea
```

### Widget Lifecycle

```
Construct → Mount → [Layout → Draw → Event]×N → Unmount → Destroy
```

### Widget Implementation Pattern

```typescript
// Minimal widget system
interface Widget {
  parent: Widget | null;
  children: Widget[];
  bounds: Rect;
  visible: boolean;

  mount(): void;
  layout(available: Rect): void;
  draw(context: CanvasContext): void;
  handleEvent(event: Event): boolean;
  unmount(): void;
}

abstract class BaseWidget implements Widget {
  parent: Widget | null = null;
  children: Widget[] = [];
  bounds: Rect = { x: 0, y: 0, width: 0, height: 0 };
  visible = true;

  mount(): void {
    for (const child of this.children) {
      child.parent = this;
      child.mount();
    }
  }

  layout(available: Rect): void {
    this.bounds = available;
    for (const child of this.children) {
      child.layout(this.computeChildBounds(child));
    }
  }

  draw(context: CanvasContext): void {
    if (!this.visible) return;
    this.paint(context);
    for (const child of this.children) {
      context.save();
      context.translate(child.bounds.x, child.bounds.y);
      child.draw(context);
      context.restore();
    }
  }

  protected abstract paint(context: CanvasContext): void;

  abstract computeChildBounds(child: Widget): Rect;

  handleEvent(event: Event): boolean {
    // Default: propagate to children
    for (const child of this.children) {
      if (child.handleEvent(event)) return true;
    }
    return false;
  }

  unmount(): void {
    for (const child of this.children) child.unmount();
  }
}
```

---

## 4. Linux Desktop Integration

### FHS Directory Layout

| Path | Purpose | Permissions |
|---|---|---|
| `/usr/local/bin/app` | Executable | 755 |
| `/etc/app/config.yaml` | Configuration | 644 (root:app) |
| `/var/lib/app/data.db` | Application data | 644 (app:app) |
| `/var/log/app/app.log` | Logs | 644 (app:app) |
| `/usr/share/app/` | Static assets | 755 (root:root) |
| `~/.config/app/` | User config | 700 |
| `~/.local/share/app/` | User data | 700 |

### Systemd Integration

```ini
[Unit]
Description=Desktop Application
After=graphical-session.target
BindsTo=graphical-session.target

[Service]
Type=exec
User=%i
Environment=DISPLAY=:0
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/%U/bus
ExecStart=/usr/local/bin/app
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

### Desktop Entry File

```ini
# ~/.local/share/applications/myapp.desktop
[Desktop Entry]
Type=Application
Name=My Application
Comment=A Linux desktop application
Exec=/usr/local/bin/app
Icon=myapp
Terminal=false
Categories=Utility;Development;
Keywords=app;tool;
```

---

## 5. Application Patterns by Type

### Text Editor

```
┌─────────────────────────────────────────┐
│              Text Editor                  │
│                                           │
│  File I/O ◀── Buffer/Gap Buffer          │
│                    │                      │
│  Input Events ───▶ Cursor Movement        │
│                    │                      │
│  Syntax Highlight ─▶ Rendering (Line-based)│
│                    │                      │
│  Undo/Redo ─────── Command Stack          │
└─────────────────────────────────────────┘
```

### File Explorer

```
┌─────────────────────────────────────────┐
│              File Explorer               │
│                                           │
│  File System ───▶ Tree Model              │
│  (inotify)        │                       │
│                   ▼                       │
│  Selection ───▶ View (List/Grid/Icon)    │
│                   │                       │
│  Operations ────▶ Copy/Move/Delete        │
│  (async)          │ (with undo)           │
│                   ▼                       │
│  Preview ────── Quick Look / Thumbnail   │
└─────────────────────────────────────────┘
```

### Media Player

```
┌─────────────────────────────────────────┐
│              Media Player                │
│                                           │
│  Playlist ──▶ Playback Engine             │
│                 │                        │
│  Audio ────────▶ Decoder → Output        │
│  Video ────────▶ Decoder → Render        │
│                 │                        │
│  Controls ───── Play/Pause/Seek/Volume   │
│                                           │
│  Visualizer ──▶ Spectrum Analyzer        │
└─────────────────────────────────────────┘
```

---

## 6. Desktop App Testing

```typescript
// Testing UI components without a real display
describe('Widget', () => {
  it('should layout children correctly', () => {
    const parent = new Panel();
    const child = new Button('Click me');
    parent.add(child);
    
    parent.layout({ x: 0, y: 0, width: 800, height: 600 });
    
    expect(child.bounds.width).toBeGreaterThan(0);
    expect(child.bounds.height).toBeGreaterThan(0);
    expect(child.bounds.x).toBeGreaterThanOrEqual(0);
  });

  it('should handle click events', () => {
    let clicked = false;
    const button = new Button('Click');
    button.onClick(() => { clicked = true; });
    
    button.handleEvent({
      type: 'mouseDown',
      timestamp: Date.now(),
      data: { button: 0, x: 10, y: 10 }
    });
    
    expect(clicked).toBe(true);
  });
});
```

---

## Quick Reference: Desktop App by Node Type

| Node Type | Desktop App Mapping |
|---|---|
| **Input** | Keyboard/mouse events, file drops, clipboard |
| **Logic** | Application services, state management |
| **Database** | SQLite for local storage, file-based config |
| **UI** | Widget tree, canvas rendering, menus/dialogs |
| **API** | System integration (D-Bus, notifications), network services |

---

*For deeper desktop development concepts, see Bible level `03-desktop-apps/` — widget toolkit design, event loop internals, multimedia apps, and packaging.*
