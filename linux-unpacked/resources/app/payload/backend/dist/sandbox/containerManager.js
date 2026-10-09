/**
 * Docker Container Manager
 * ========================
 * Manages running generated apps as full Docker services.
 * Handles image building, container lifecycle, port allocation,
 * health checking, and cleanup.
 *
 * Flow:
 *   1. Collect generated code from project nodes
 *   2. Write files to a temp project directory
 *   3. Generate a Dockerfile based on language/type
 *   4. Build Docker image
 *   5. Run container on a dynamic port
 *   6. Health check until ready (or timeout)
 *   7. Return preview URL
 *   8. Auto-cleanup after TTL (default 30 min)
 */
import { execSync, spawn } from 'child_process';
import { mkdirSync, writeFileSync, rmSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { randomUUID } from 'crypto';
import net from 'net';
// ─── Docker Command Wrapper ────────────────────────────────────────────────
// Handles the case where the user is in the docker group but the group
// membership hasn't been applied to the current process. Falls back to
// `sg docker -c` (activates group) then `sudo` as last resort.
export function execDocker(args, opts = {}) {
    const defaultOpts = { timeout: 30000, encoding: 'utf-8', stdio: 'pipe' };
    const options = { ...defaultOpts, ...opts };
    try {
        return String(execSync(`docker ${args}`, options));
    }
    catch (err) {
        try {
            const escaped = args.replace(/"/g, '\\"');
            return String(execSync(`sg docker -c "docker ${escaped}"`, { ...options, timeout: (options.timeout || 30000) + 5000 }));
        }
        catch {
            try {
                return String(execSync(`sudo docker ${args} 2>/dev/null`, { ...options, timeout: (options.timeout || 30000) + 5000 }));
            }
            catch {
                throw err;
            }
        }
    }
}
// ─── Config ───────────────────────────────────────────────────────────────
const CONTAINER_TTL_MS = parseInt(process.env.CONTAINER_TTL || '1800000', 10); // 30 min default
const HEALTH_CHECK_TIMEOUT = parseInt(process.env.HEALTH_CHECK_TIMEOUT || '30000', 10); // 30s
const BUILD_TIMEOUT = parseInt(process.env.DOCKER_BUILD_TIMEOUT || '120000', 10); // 2 min
const IMAGE_PREFIX = 'vaca-app-';
// In-memory registry of running containers
const containers = new Map();
// ─── Docker Availability ──────────────────────────────────────────────────
export function findAvailablePort(min = 40000, max = 50000) {
    return new Promise((resolve, reject) => {
        const tryPort = (port) => {
            if (port > max) {
                reject(new Error('No available ports found in range'));
                return;
            }
            const server = net.createServer();
            server.once('error', () => {
                server.close(() => tryPort(port + 1));
            });
            server.once('listening', () => {
                server.close(() => resolve(port));
            });
            server.listen(port, '0.0.0.0');
        };
        tryPort(min);
    });
}
export function isDockerAvailable() {
    try {
        execDocker('info --format "{{.ServerVersion}}"', { timeout: 5000, stdio: 'pipe' });
        return true;
    }
    catch {
        return false;
    }
}
// ─── Language Detection ───────────────────────────────────────────────────
export function detectLanguage(nodes) {
    // First check if any node explicitly declares a language
    for (const node of nodes) {
        if (node.data?.language) {
            const lang = node.data.language.toLowerCase();
            if (['typescript', 'javascript', 'python', 'go'].includes(lang))
                return lang;
        }
    }
    // Then sniff the code
    const allCode = nodes.map(n => n.data?.generatedCode || '').join('\n');
    const lines = allCode.split('\n').filter(l => l.trim());
    if (lines.some(l => l.includes('import React') || l.includes('from \'react\'') || l.includes(': string') || l.includes('interface ')))
        return 'typescript';
    if (lines.some(l => l.includes('require(') || l.includes('module.exports') || l.includes('express(')))
        return 'javascript';
    if (lines.some(l => l.includes('def ') || l.includes('from ') && l.includes('import') || l.includes('@app.route')))
        return 'python';
    if (lines.some(l => l.includes('package main') || l.includes('func main')))
        return 'go';
    // Check if it's mostly HTML
    if (lines.some(l => l.includes('<html') || l.includes('<!DOCTYPE')))
        return 'html';
    return 'typescript';
}
const DOCKERFILE_TEMPLATES = {
    typescript(appDir, entrypoint) {
        return `FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production 2>/dev/null || npm init -y
COPY . .
RUN apk add --no-cache curl
EXPOSE 3000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \\
  CMD curl -f http://localhost:3000/health || curl -f http://localhost:3000/ || exit 1
CMD ["node", "${entrypoint || 'index.js'}"]`;
    },
    javascript(appDir, entrypoint) {
        return `FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm init -y 2>/dev/null; npm install express 2>/dev/null || true
COPY . .
RUN apk add --no-cache curl
EXPOSE 3000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \\
  CMD curl -f http://localhost:3000/health || curl -f http://localhost:3000/ || exit 1
CMD ["node", "${entrypoint || 'index.js'}"]`;
    },
    python(appDir, entrypoint) {
        return `FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null; \\
    pip install flask 2>/dev/null || true
COPY . .
RUN apk add --no-cache curl
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \\
  CMD curl -f http://localhost:8080/health || curl -f http://localhost:8080/ || exit 1
CMD ["python3", "${entrypoint || 'main.py'}"]`;
    },
    go(appDir, entrypoint) {
        return `FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download 2>/dev/null || true
COPY . .
RUN CGO_ENABLED=0 go build -o /server . && \\
    apk add --no-cache curl
FROM alpine:3.19
RUN apk add --no-cache curl
WORKDIR /app
COPY --from=build /server .
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \\
  CMD curl -f http://localhost:8080/health || curl -f http://localhost:8080/ || exit 1
CMD ["./server"]`;
    },
    html(appDir, _entrypoint) {
        return `FROM nginx:alpine
COPY . /usr/share/nginx/html
RUN apk add --no-cache curl
EXPOSE 80
HEALTHCHECK --interval=5s --timeout=3s --start-period=3s --retries=3 \\
  CMD curl -f http://localhost/ || exit 1`;
    },
};
function getEntrypoint(language, nodes) {
    switch (language) {
        case 'typescript':
        case 'javascript':
            // Look for a node with server code or a main entry
            for (const node of nodes) {
                const code = node.data?.generatedCode || '';
                if (code.includes('app.listen') || code.includes('server.listen') || code.includes('http.createServer')) {
                    return `index.${language === 'typescript' ? 'ts' : 'js'}`;
                }
            }
            return 'index.js';
        case 'python':
            return 'main.py';
        case 'go':
            return 'main.go';
        default:
            return 'index.html';
    }
}
// ─── Project Directory Builder ───────────────────────────────────────────
function buildProjectDir(baseDir, nodes, language, entrypoint) {
    const appDir = join(baseDir, 'app');
    mkdirSync(appDir, { recursive: true });
    // Write each node's code as a separate file
    let hasServerCode = false;
    const nodeFiles = [];
    for (const node of nodes) {
        const code = node.data?.generatedCode || '';
        if (!code.trim())
            continue;
        const label = node.data?.label || node.id || 'unnamed';
        // Determine if this is server code
        if (code.includes('app.listen') || code.includes('server.listen') || code.includes('http.createServer') ||
            code.includes('@app.route') || code.includes('app.run') || code.includes('func main')) {
            hasServerCode = true;
        }
        // Create a clean filename from the label
        const safeName = label.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
        let ext;
        switch (language) {
            case 'typescript':
                ext = '.ts';
                break;
            case 'javascript':
                ext = '.js';
                break;
            case 'python':
                ext = '.py';
                break;
            case 'go':
                ext = '.go';
                break;
            default: ext = '.html';
        }
        const filename = `${safeName}${ext}`;
        nodeFiles.push({ name: filename, code });
    }
    // Write all node files
    for (const nf of nodeFiles) {
        writeFileSync(join(appDir, nf.name), nf.code, 'utf-8');
    }
    // Create an entrypoint if none exists with server code
    if (!hasServerCode) {
        createDefaultEntrypoint(appDir, language, entrypoint, nodes, nodeFiles);
    }
    // Only write concatenated entrypoint if there's no server code (avoid duplication)
    if (!hasServerCode) {
        const entryCode = nodes
            .filter(n => n.data?.generatedCode)
            .map(n => n.data?.generatedCode)
            .join('\n\n');
        writeFileSync(join(appDir, entrypoint), entryCode || '// Generated app entry point', 'utf-8');
    }
    // Generate package.json for Node.js apps
    if (language === 'typescript' || language === 'javascript') {
        writeFileSync(join(appDir, 'package.json'), JSON.stringify({
            name: 'vaca-generated-app',
            version: '1.0.0',
            private: true,
            type: 'module',
            main: entrypoint,
            scripts: {
                start: `node ${entrypoint}`,
                dev: `node --watch ${entrypoint}`,
            },
        }, null, 2), 'utf-8');
    }
    // Generate requirements.txt for Python
    if (language === 'python') {
        writeFileSync(join(appDir, 'requirements.txt'), 'flask\ngunicorn\n', 'utf-8');
    }
    // Generate go.mod for Go
    if (language === 'go') {
        writeFileSync(join(appDir, 'go.mod'), `module vaca-generated-app\n\ngo 1.22\n`, 'utf-8');
    }
    // Generate Dockerfile
    const dockerfileGenerator = DOCKERFILE_TEMPLATES[language] || DOCKERFILE_TEMPLATES.html;
    const dockerfile = dockerfileGenerator(appDir, entrypoint);
    writeFileSync(join(appDir, 'Dockerfile'), dockerfile, 'utf-8');
    // Generate .dockerignore
    writeFileSync(join(appDir, '.dockerignore'), 'node_modules\n.git\n*.md\n', 'utf-8');
    return appDir;
}
function createDefaultEntrypoint(appDir, language, entrypoint, nodes, _nodeFiles) {
    const allCode = nodes.map(n => n.data?.generatedCode || '').join('\n');
    switch (language) {
        case 'typescript':
        case 'javascript': {
            const entryCode = `import http from 'http';

// Generated app entry point
// All node code has been loaded above

const server = http.createServer((req, res) => {
  if (req.url === '/health' || req.url === '/') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      status: 'ok',
      app: '${nodes[0]?.data?.label || 'Generated App'}',
      timestamp: new Date().toISOString(),
    }));
    return;
  }
  res.writeHead(404);
  res.end('Not found');
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log('🚀 Server running on port', PORT);
});
`;
            writeFileSync(join(appDir, entrypoint), entryCode, 'utf-8');
            break;
        }
        case 'python': {
            const entryCode = `from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os

class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/health'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'app': 'Generated App',
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), AppHandler)
    print(f'🚀 Server running on port {port}')
    server.serve_forever()
`;
            writeFileSync(join(appDir, entrypoint), entryCode, 'utf-8');
            break;
        }
        case 'go': {
            const entryCode = `package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "os"
)

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }

    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{
            "status": "ok",
            "app":    "Generated App",
        })
    })

    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
    })

    fmt.Printf("🚀 Server running on port %s\\n", port)
    log.Fatal(http.ListenAndServe(":"+port, nil))
}
`;
            writeFileSync(join(appDir, entrypoint), entryCode, 'utf-8');
            break;
        }
    }
}
// ─── Container Lifecycle ──────────────────────────────────────────────────
/**
 * Start a Docker container for a generated app project.
 * Builds the image, runs the container, and waits for it to become healthy.
 */
export async function startContainer(options) {
    const id = randomUUID().slice(0, 8);
    const imageName = `${IMAGE_PREFIX}${id}`;
    const language = detectLanguage(options.nodes);
    const port = await findAvailablePort();
    const instance = {
        id,
        dockerId: '',
        projectName: options.projectName,
        projectId: options.projectId,
        imageName,
        port,
        hostPort: port,
        status: 'building',
        url: `http://localhost:${port}`,
        language,
        entrypoint: '',
        createdAt: Date.now(),
        lastHealthCheck: 0,
        healthCheckUrl: `http://localhost:${port}/health`,
        logs: [],
    };
    containers.set(id, instance);
    try {
        // 1. Create temp build directory
        const buildDir = join(tmpdir(), 'vaca-docker', id);
        mkdirSync(buildDir, { recursive: true });
        instance.logs.push(`[build] Created temp directory: ${buildDir}`);
        // 2. Write project files
        const entrypoint = getEntrypoint(language, options.nodes);
        instance.entrypoint = entrypoint;
        const appDir = buildProjectDir(buildDir, options.nodes, language, entrypoint);
        instance.logs.push(`[build] Wrote ${options.nodes.length} node files + Dockerfile to ${appDir}`);
        // 3. Build Docker image (async so it doesn't block other requests)
        instance.logs.push(`[build] Building Docker image: ${imageName}`);
        try {
            await new Promise((resolve, reject) => {
                const build = spawn('docker', [
                    'build', '-t', imageName,
                    '-f', join(appDir, 'Dockerfile'),
                    appDir,
                ], { timeout: BUILD_TIMEOUT });
                build.stdout.on('data', (data) => {
                    const text = data.toString();
                    instance.logs.push(...text.split('\n').filter((l) => l.trim()).map((l) => `[build] ${l}`));
                });
                build.stderr.on('data', (_data) => { });
                build.on('close', (code) => {
                    if (code === 0)
                        resolve();
                    else
                        reject(new Error(`Build exited with code ${code}`));
                });
                build.on('error', reject);
            });
        }
        catch (buildErr) {
            const buildLog = buildErr.message || 'Build failed';
            instance.logs.push(`[build] ❌ Build error: ${buildLog.slice(0, 500)}`);
            instance.status = 'error';
            instance.error = `Docker build failed: ${buildLog.slice(0, 500)}`;
            cleanupBuildDir(buildDir);
            return instance;
        }
        // 4. Run container
        instance.status = 'starting';
        instance.logs.push(`[run] Starting container on host port ${port}`);
        try {
            const runResult = execDocker(`run -d --name ${imageName} --restart no -p ${port}:${port} ` +
                `-e PORT=${port} -e NODE_ENV=production ` +
                `${imageName}`, { timeout: 30000 });
            instance.dockerId = runResult.trim();
            instance.logs.push(`[run] Container started: ${instance.dockerId.slice(0, 12)}`);
        }
        catch (runErr) {
            instance.logs.push(`[run] ❌ Run error: ${runErr.message}`);
            instance.status = 'error';
            instance.error = `Docker run failed: ${runErr.message}`;
            cleanupBuildDir(buildDir);
            return instance;
        }
        // 5. Health check loop
        instance.logs.push(`[health] Waiting for service at http://localhost:${port}...`);
        const healthStart = Date.now();
        let healthy = false;
        while (Date.now() - healthStart < HEALTH_CHECK_TIMEOUT) {
            try {
                const response = await fetch(`http://localhost:${port}/health`, { signal: AbortSignal.timeout(3000) });
                if (response.ok) {
                    healthy = true;
                    instance.lastHealthCheck = Date.now();
                    instance.logs.push(`[health] ✅ Service is healthy!`);
                    break;
                }
            }
            catch {
                // Not ready yet
            }
            // Also try root path
            if (!healthy) {
                try {
                    const response = await fetch(`http://localhost:${port}/`, { signal: AbortSignal.timeout(3000) });
                    if (response.ok) {
                        healthy = true;
                        instance.lastHealthCheck = Date.now();
                        instance.logs.push(`[health] ✅ Service responded at root!`);
                        break;
                    }
                }
                catch {
                    // Not ready yet
                }
            }
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
        if (healthy) {
            instance.status = 'running';
            instance.logs.push(`[health] ✅ Service running at ${instance.url}`);
        }
        else {
            instance.status = 'running'; // Still mark as running even if health check didn't pass
            instance.logs.push(`[health] ⚠️ Health check timed out, but container is running`);
        }
        // 6. Set auto-cleanup timer — stops container AND removes from tracking map
        setTimeout(() => {
            stopContainer(id).then(() => containers.delete(id)).catch(() => containers.delete(id));
        }, CONTAINER_TTL_MS);
        // Cleanup build dir
        cleanupBuildDir(buildDir);
    }
    catch (err) {
        instance.status = 'error';
        instance.error = err.message;
        instance.logs.push(`[error] ${err.message}`);
    }
    return instance;
}
/**
 * Stop and remove a running container.
 */
export async function stopContainer(id) {
    const instance = containers.get(id);
    if (!instance)
        return false;
    try {
        instance.logs.push(`[stop] Stopping container ${instance.dockerId.slice(0, 12)}...`);
        // Stop the container
        execDocker(`stop ${instance.imageName} 2>/dev/null`, { timeout: 15000, stdio: 'pipe' });
        execDocker(`rm ${instance.imageName} 2>/dev/null`, { timeout: 15000, stdio: 'pipe' });
        // Remove the image
        execDocker(`rmi ${instance.imageName} 2>/dev/null`, { timeout: 30000, stdio: 'pipe' });
        instance.status = 'stopped';
        instance.logs.push(`[stop] ✅ Container stopped and removed`);
        return true;
    }
    catch (err) {
        instance.logs.push(`[stop] ⚠️ Cleanup error: ${err.message}`);
        instance.status = 'stopped';
        return false;
    }
}
/**
 * Get container logs.
 */
export function getContainerLogs(id) {
    const instance = containers.get(id);
    if (!instance)
        return null;
    // Try to get live docker logs
    try {
        const dockerLogs = execDocker(`logs ${instance.imageName} --tail 50 2>&1`, { timeout: 5000, stdio: 'pipe' });
        const liveLogs = dockerLogs.split('\n').filter(l => l.trim());
        return {
            logs: [...instance.logs, ...liveLogs.map(l => `[app] ${l}`)],
            containerId: instance.dockerId,
            status: instance.status,
        };
    }
    catch {
        // Docker logs unavailable, return cached
        return {
            logs: instance.logs,
            containerId: instance.dockerId,
            status: instance.status,
        };
    }
}
/**
 * Get the status of a specific container.
 */
export function getContainerStatus(id) {
    const instance = containers.get(id);
    if (!instance)
        return null;
    // Check if container is still alive
    if (instance.status === 'running') {
        try {
            const inspect = execDocker(`inspect ${instance.imageName} --format '{{.State.Status}}' 2>/dev/null`, { timeout: 5000 });
            const dockerStatus = inspect.trim();
            if (dockerStatus !== 'running') {
                instance.status = 'stopped';
            }
        }
        catch {
            instance.status = 'stopped';
        }
    }
    return instance;
}
/**
 * List all managed containers.
 */
export function listContainers(status) {
    const all = Array.from(containers.values());
    // Clean up stale entries
    for (const inst of all) {
        if (inst.status === 'running') {
            try {
                execDocker(`inspect ${inst.imageName} 2>/dev/null`, { timeout: 5000, stdio: 'pipe' });
            }
            catch {
                inst.status = 'stopped';
            }
        }
    }
    if (status)
        return all.filter(c => c.status === status);
    return all;
}
/**
 * Clean up all stopped containers.
 */
export function cleanupAllStopped() {
    let count = 0;
    for (const [id, instance] of containers) {
        if (instance.status === 'stopped' || instance.status === 'error') {
            stopContainer(id).catch(() => { });
            containers.delete(id);
            count++;
        }
    }
    return count;
}
/**
 * Clean up containers that have exceeded their TTL.
 */
export function cleanupExpired() {
    const now = Date.now();
    let count = 0;
    for (const [id, instance] of containers) {
        if (now - instance.createdAt > CONTAINER_TTL_MS) {
            stopContainer(id).catch(() => { });
            containers.delete(id);
            count++;
        }
    }
    return count;
}
// ─── Helpers ──────────────────────────────────────────────────────────────
function cleanupBuildDir(dir) {
    try {
        rmSync(join(dir, 'app'), { recursive: true, force: true });
    }
    catch { }
    try {
        rmSync(dir, { recursive: true, force: true });
    }
    catch { }
}
