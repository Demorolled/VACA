# 🚀 Deployment Templates

> Deployment strategies and templates for generated applications.
> Covers Linux-native deployment, self-contained binaries, and web hosting.

---

## 1. Deployment Philosophy

Following the Design Manifesto's principles:
- **Self-contained** — prefer single-binary or minimal-dependency deployments
- **Linux-first** — systemd integration, journal logging, FHS paths
- **Offline-capable** — no mandatory network dependencies
- **Simple** — no container orchestration, no Kubernetes

### Deployment Decision Tree

```
What type of app?
├── CLI / System Tool
│   └── Go binary → Systemd service or standalone executable
├── Web Application
│   └── TypeScript backend → Node.js process + systemd
├── Media Server
│   └── TypeScript + Python → Multiple systemd services
├── Desktop Web App
│   └── Static files (Vite build) + API backend
└── Data Processor
    └── Python script → Cron job or systemd timer
```

---

## 2. Deployment Targets

### 2.1 Single Binary (Go) — Preferred for CLI & System Tools

**Build:**
```makefile
BINARY=app
VERSION=$(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")

build:
	go build -ldflags="-s -w -X main.Version=$(VERSION)" -o bin/$(BINARY) ./cmd/app

build-linux-amd64:
	GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o bin/$(BINARY)-linux-amd64 ./cmd/app

# Install to system
install: build
	install -m 755 bin/$(BINARY) /usr/local/bin/$(BINARY)
	install -d /etc/$(BINARY)
	install -m 644 config/config.yaml /etc/$(BINARY)/config.yaml

clean:
	rm -rf bin/
```

**Systemd Service** (`deploy/systemd/app.service`):
```ini
[Unit]
Description=App Service
Documentation=https://github.com/user/app
After=network.target

[Service]
Type=simple
User=app
Group=app
ExecStart=/usr/local/bin/app
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=APP_CONFIG=/etc/app/config.yaml
Environment=APP_DATA=/var/lib/app
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

**Post-Install Script** (`deploy/postinst`):
```bash
#!/bin/bash
# Called after .deb package installation
set -e

# Create user if not exists
if ! id -u app &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin app
fi

# Create data directory
mkdir -p /var/lib/app
chown app:app /var/lib/app

# Reload systemd
systemctl daemon-reload

# Start service
systemctl enable app
systemctl start app || true
```

### 2.2 TypeScript Backend (Node.js)

**Build:**
```json
{
  "scripts": {
    "build": "tsup src/index.ts --minify --target node20 --out-dir dist",
    "build:linux": "tsup src/index.ts --minify --target node20 --platform node --out-dir dist",
    "build:standalone": "pkg dist/index.js --target node20-linux-x64 --output bin/app"
  }
}
```

**Systemd Service** (`deploy/systemd/app.service`):
```ini
[Unit]
Description=App API Server
After=network.target

[Service]
Type=exec
User=app
WorkingDirectory=/opt/app
ExecStart=/usr/bin/node /opt/app/dist/index.js
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production
Environment=PORT=3000
Environment=DB_PATH=/var/lib/app/data.db

[Install]
WantedBy=multi-user.target
```

**Nginx Reverse Proxy** (`deploy/nginx/app.conf`):
```nginx
server {
    listen 80;
    server_name app.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
    }

    location /ws {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 2.3 Static Web Frontend (Vite/React)

**Build:**
```json
{
  "scripts": {
    "build": "vite build",
    "preview": "vite preview"
  }
}
```

**Deploy as static files:**
```bash
# Build
npm run build

# Copy to web server
cp -r dist/* /var/www/app/

# Or serve via systemd with a simple static server
```

**Simple Static Server** (`deploy/static-server.ts`):
```typescript
import express from 'express';
import path from 'path';

const app = express();
const PORT = process.env.PORT ?? 8080;
const DIST = path.join(process.cwd(), 'dist');

app.use(express.static(DIST));
app.get('*', (_req, res) => res.sendFile(path.join(DIST, 'index.html')));

app.listen(PORT, () => console.log(`Static server on :${PORT}`));
```

### 2.4 Python Backend

**Build:**
```bash
# Install dependencies
pip install -r requirements.txt

# Option A: Direct execution
python src/main.py

# Option B: Single executable
pip install pyinstaller
pyinstaller --onefile --name app src/main.py
# Outputs: dist/app
```

**Systemd Service:**
```ini
[Unit]
Description=App Python Service
After=network.target

[Service]
Type=simple
User=app
WorkingDirectory=/opt/app
ExecStart=/usr/bin/python /opt/app/src/main.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

## 3. Linux Filesystem Hierarchy (FHS) Layout

For installed applications, follow FHS:

```
/usr/local/bin/app        ← Executable
/etc/app/config.yaml      ← Configuration (readable by app user)
/var/lib/app/data.db      ← Data (writable by app user)
/var/log/app/app.log      ← Logs (if not using journald)
/usr/share/app/           ← Static assets (read-only)
```

### Install Script Template

```bash
#!/bin/bash
# install.sh — Install application to system
set -euo pipefail

APP_NAME="myapp"
APP_USER="app"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/$APP_NAME"
DATA_DIR="/var/lib/$APP_NAME"

echo "Installing $APP_NAME..."

# Create user
if ! id -u "$APP_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
fi

# Create directories
install -d -m 755 "$CONFIG_DIR"
install -d -m 755 "$DATA_DIR"
install -d -m 755 /var/log/$APP_NAME

# Install binary
install -m 755 "bin/$APP_NAME" "$INSTALL_DIR/$APP_NAME"

# Install config
install -m 644 config.yaml "$CONFIG_DIR/config.yaml"

# Install systemd service
install -m 644 deploy/systemd/$APP_NAME.service /etc/systemd/system/
systemctl daemon-reload

# Set permissions
chown -R "$APP_USER:$APP_USER" "$DATA_DIR" "/var/log/$APP_NAME"

echo "✓ Installation complete"
echo "  Start: systemctl start $APP_NAME"
echo "  Enable: systemctl enable $APP_NAME"
echo "  Status: systemctl status $APP_NAME"
```

---

## 4. .deb Package Building

For system tools distributed to Ubuntu/Debian systems:

```makefile
# Build .deb package
VERSION ?= 1.0.0
APP=myapp

deb: build
	mkdir -p build/deb/$(APP)_$(VERSION)_amd64/DEBIAN
	mkdir -p build/deb/$(APP)_$(VERSION)_amd64/usr/local/bin
	mkdir -p build/deb/$(APP)_$(VERSION)_amd64/etc/$(APP)
	mkdir -p build/deb/$(APP)_$(VERSION)_amd64/lib/systemd/system

	install -m 755 bin/$(APP)-linux-amd64 \
		build/deb/$(APP)_$(VERSION)_amd64/usr/local/bin/$(APP)
	install -m 644 config/config.yaml \
		build/deb/$(APP)_$(VERSION)_amd64/etc/$(APP)/config.yaml
	install -m 644 deploy/systemd/$(APP).service \
		build/deb/$(APP)_$(VERSION)_amd64/lib/systemd/system/$(APP).service

	cat > build/deb/$(APP)_$(VERSION)_amd64/DEBIAN/control << EOF
Package: $(APP)
Version: $(VERSION)
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Your Name <email@example.com>
Description: Application description
 Built from Visual AI Architect.
EOF

	cp deploy/postinst build/deb/$(APP)_$(VERSION)_amd64/DEBIAN/postinst
	chmod 755 build/deb/$(APP)_$(VERSION)_amd64/DEBIAN/postinst

	dpkg-deb --build build/deb/$(APP)_$(VERSION)_amd64
	@echo "Package: build/deb/$(APP)_$(VERSION)_amd64.deb"
```

---

## 5. Environment-Specific Configuration

### 5.1 Config Loading with Environment Overrides

```typescript
// config.ts
import fs from 'fs';
import path from 'path';

/** Configuration — values come from: env vars > config file > defaults */
export interface AppConfig {
  port: number;
  host: string;
  dbPath: string;
  logLevel: string;
}

export function loadConfig(): AppConfig {
  // 1. Defaults
  const defaults: AppConfig = {
    port: 3000,
    host: 'localhost',
    dbPath: './data/app.db',
    logLevel: 'info',
  };

  // 2. Config file override
  const configPath = process.env.APP_CONFIG ?? '/etc/app/config.yaml';
  let fileConfig: Partial<AppConfig> = {};
  try {
    if (fs.existsSync(configPath)) {
      fileConfig = YAML.parse(fs.readFileSync(configPath, 'utf-8'));
    }
  } catch { /* Use defaults if config file is missing */ }

  // 3. Environment variable override (highest priority)
  return {
    ...defaults,
    ...fileConfig,
    ...(process.env.PORT ? { port: parseInt(process.env.PORT) } : {}),
    ...(process.env.HOST ? { host: process.env.HOST } : {}),
    ...(process.env.DB_PATH ? { dbPath: process.env.DB_PATH } : {}),
    ...(process.env.LOG_LEVEL ? { logLevel: process.env.LOG_LEVEL } : {}),
  };
}
```

### 5.2 Config File Template

```yaml
# /etc/app/config.yaml
port: 3000
host: "0.0.0.0"
db_path: "/var/lib/app/data.db"
log_level: "info"

# App-specific settings
max_upload_size: 104857600
allowed_origins:
  - "http://localhost:5173"
  - "https://app.example.com"
```

---

## 6. Deployment Checklist

Before any deployment:

- [ ] Binary is compiled for the target architecture (`linux/amd64`)
- [ ] Binary is stripped of debug symbols (`-ldflags="-s -w"`)
- [ ] Config file is installed to `/etc/app/`
- [ ] Data directory is created with proper permissions
- [ ] Systemd service file is installed and enabled
- [ ] Log rotation is configured (logrotate or journald)
- [ ] Backup strategy is documented
- [ ] Health endpoint returns 200 on `/health`
- [ ] Port is not already in use
- [ ] Firewall allows only necessary ports
- [ ] SSL certificate is valid (for web apps)
- [ ] Database is initialized (migrations run)
- [ ] Service starts successfully (`systemctl start app`)

---

*For deeper deployment concepts, see `bible-reference/12-devops/` and `bible-reference/32-cloud-native-infra/`.*
