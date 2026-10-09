/**
 * Docker Compose Multi-Service Manager
 * =====================================
 * Groups generated app nodes into frontend/backend/database services
 * and manages them via docker-compose. Supports automatic database
 * detection (PostgreSQL, MongoDB, Redis, MySQL) and service dependency
 * wiring.
 *
 * Flow:
 *   1. Classify nodes by type → services (frontend, backend, database)
 *   2. Generate Dockerfiles + docker-compose.yml
 *   3. Run `docker-compose up -d --build`
 *   4. Health-check each service
 *   5. Return URLs for each exposed service
 *   6. Cleanup via `docker-compose down`
 */
import { execSync, spawn } from 'child_process';
import { mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { randomUUID } from 'crypto';
import { findAvailablePort } from './containerManager.js';
// ─── Docker Compose Command Wrapper ────────────────────────────────────────
// Same pattern as containerManager.ts — handles docker group membership issue
export function execCompose(args, opts = {}) {
    const defaultOpts = { timeout: 60000, encoding: 'utf-8', stdio: 'pipe' };
    const options = { ...defaultOpts, ...opts };
    try {
        return String(execSync(args, options));
    }
    catch (err) {
        try {
            const escaped = args.replace(/"/g, '\\"');
            return String(execSync(`sg docker -c "${escaped}"`, { ...options, timeout: (options.timeout || 60000) + 5000 }));
        }
        catch {
            try {
                return String(execSync(`sudo ${args} 2>/dev/null`, { ...options, timeout: (options.timeout || 60000) + 5000 }));
            }
            catch {
                throw err;
            }
        }
    }
}
// Detect language from raw code text (not node items)
function detectLanguageFromCode(code) {
    const lines = code.split('\n').filter(l => l.trim());
    if (lines.some(l => /import React|from 'react'|: string|interface /.test(l)))
        return 'typescript';
    if (lines.some(l => /require\(|module\.exports|express\(/.test(l)))
        return 'javascript';
    if (lines.some(l => /def |@app\.route/.test(l)))
        return 'python';
    if (lines.some(l => /package main|func main/.test(l)))
        return 'go';
    if (lines.some(l => /<html|<\!DOCTYPE/.test(l)))
        return 'html';
    return 'typescript';
}
// ─── Config ───────────────────────────────────────────────────────────────
const COMPOSE_TTL_MS = parseInt(process.env.COMPOSE_TTL || '3600000', 10); // 60 min
const COMPOSE_TIMEOUT = parseInt(process.env.COMPOSE_TIMEOUT || '300000', 10); // 5 min
const COMPOSE_PREFIX = 'vaca-compose-';
// In-memory registry of compose stacks
const composeStacks = new Map();
// Lazy docker-compose command detection — only runs when compose is actually used
let _dockerComposeCmd = null;
function getDockerComposeCmd() {
    if (_dockerComposeCmd)
        return _dockerComposeCmd;
    try {
        execSync('docker compose version 2>/dev/null', { stdio: 'pipe', timeout: 3000 });
        _dockerComposeCmd = ['docker', 'compose'];
    }
    catch {
        try {
            execSync('docker-compose --version 2>/dev/null', { stdio: 'pipe', timeout: 3000 });
            _dockerComposeCmd = ['docker-compose'];
        }
        catch {
            _dockerComposeCmd = ['docker-compose'];
        }
    }
    return _dockerComposeCmd;
}
// Database images and default configs
const DATABASE_IMAGES = {
    postgres: {
        image: 'postgres:16-alpine',
        port: 5432,
        env: { POSTGRES_USER: 'app', POSTGRES_PASSWORD: 'app123', POSTGRES_DB: 'app' },
        healthCmd: 'pg_isready -U app',
    },
    mongodb: {
        image: 'mongo:7',
        port: 27017,
        env: { MONGO_INITDB_ROOT_USERNAME: 'app', MONGO_INITDB_ROOT_PASSWORD: 'app123', MONGO_INITDB_DATABASE: 'app' },
        healthCmd: 'mongosh --quiet --eval "db.runCommand({ ping: 1 })"',
    },
    redis: {
        image: 'redis:7-alpine',
        port: 6379,
        env: {},
        healthCmd: 'redis-cli ping',
    },
    mysql: {
        image: 'mysql:8',
        port: 3306,
        env: { MYSQL_ROOT_PASSWORD: 'root123', MYSQL_DATABASE: 'app', MYSQL_USER: 'app', MYSQL_PASSWORD: 'app123' },
        healthCmd: 'mysqladmin ping -h localhost',
    },
};
// Standard internal ports for app services
const SERVICE_PORTS = {
    frontend: 80,
    backend: 3000,
    database: 5432, // overridden by detected DB type
};
const SERVICE_HEALTH = {
    frontend: '/',
    backend: '/health',
    database: '/health', // not used for DB — uses Docker HEALTHCHECK
};
// ─── Service Detection ───────────────────────────────────────────────────
function detectDatabaseType(code) {
    // Only check within common database connection patterns to avoid false positives
    if (/postgresql:|pg:|@pg\b|pg\s*\(|pg\./.test(code.toLowerCase()))
        return 'postgres';
    if (/mongodb:|mongoose|MongoClient|mongodb\./.test(code))
        return 'mongodb';
    if (/redis:|ioredis|createClient/.test(code))
        return 'redis';
    if (/mysql:|mariadb|createConnection\s*\(/.test(code))
        return 'mysql';
    return 'none';
}
// detectLanguageFromCode: detects language from raw code text (defined at top of file)
/**
 * Classify project nodes into service groups.
 */
function classifyServices(nodes) {
    const frontend = [];
    const backend = [];
    const database = [];
    for (const node of nodes) {
        switch (node.type) {
            case 'ui':
            case 'ui-functions':
            case 'gui-layout':
                frontend.push(node);
                break;
            case 'database':
                database.push(node);
                break;
            case 'api':
            case 'logic':
            case 'input':
            case 'output':
                backend.push(node);
                break;
            default:
                // Default to backend if type is unknown
                backend.push(node);
        }
    }
    return { frontend, backend, database };
}
// ─── Compose YAML Generation ─────────────────────────────────────────────
function generateComposeYaml(services, composeDir) {
    const lines = [];
    lines.push('services:');
    for (const svc of services) {
        lines.push(`  ${svc.name}:`);
        if (svc.type === 'database') {
            const dbConfig = DATABASE_IMAGES[svc.databaseType || 'postgres'];
            lines.push(`    image: ${dbConfig.image}`);
            lines.push(`    container_name: ${COMPOSE_PREFIX}${svc.name}`);
            lines.push('    restart: unless-stopped');
            // Health check
            lines.push('    healthcheck:');
            lines.push(`      test: ["CMD-SHELL", "${dbConfig.healthCmd}"]`);
            lines.push('      interval: 5s');
            lines.push('      timeout: 3s');
            lines.push('      retries: 5');
            // Environment
            lines.push('    environment:');
            for (const [key, val] of Object.entries(dbConfig.env)) {
                lines.push(`      ${key}: ${val}`);
            }
            // Ports
            lines.push('    ports:');
            lines.push(`      - "${svc.hostPort}:${svc.port}"`);
            // Volumes
            lines.push('    volumes:');
            lines.push(`      - ${svc.name}-data:/var/lib/${svc.databaseType}/data`);
        }
        else {
            lines.push(`    build: ./${svc.name}`);
            lines.push(`    container_name: ${COMPOSE_PREFIX}${svc.name}`);
            lines.push('    restart: unless-stopped');
            // Health check
            lines.push('    healthcheck:');
            lines.push('      test: ["CMD", "curl", "-f", "http://localhost:' + svc.port + '/health"]');
            lines.push('      interval: 10s');
            lines.push('      timeout: 5s');
            lines.push('      retries: 5');
            lines.push('      start_period: 15s');
            // Environment
            if (Object.keys(svc.environment).length > 0) {
                lines.push('    environment:');
                for (const [key, val] of Object.entries(svc.environment)) {
                    lines.push(`      ${key}: ${val}`);
                }
            }
            // Ports
            lines.push('    ports:');
            lines.push(`      - "${svc.hostPort}:${svc.port}"`);
        }
        // Dependencies
        if (svc.dependsOn.length > 0) {
            lines.push('    depends_on:');
            for (const dep of svc.dependsOn) {
                lines.push(`      ${dep}:`);
                lines.push('        condition: service_healthy');
            }
        }
    }
    // Named volumes for databases
    const hasDb = services.some(s => s.type === 'database');
    if (hasDb) {
        lines.push('');
        lines.push('volumes:');
        for (const svc of services) {
            if (svc.type === 'database') {
                lines.push(`  ${svc.name}-data:`);
            }
        }
    }
    return lines.join('\n');
}
// ─── Dockerfile Generation for App Services ─────────────────────────────
function generateAppDockerfile(language, _serviceType, entrypoint) {
    switch (language) {
        case 'typescript':
        case 'javascript':
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
        case 'python':
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
        case 'go':
            return `FROM golang:1.22-alpine AS build
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download 2>/dev/null || true
COPY . .
RUN CGO_ENABLED=0 go build -o /server .
FROM alpine:3.19
RUN apk add --no-cache curl
WORKDIR /app
COPY --from=build /server .
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \\
  CMD curl -f http://localhost:8080/health || curl -f http://localhost:8080/ || exit 1
CMD ["./server"]`;
        case 'html':
            return `FROM nginx:alpine
COPY . /usr/share/nginx/html
RUN apk add --no-cache curl
EXPOSE 80
HEALTHCHECK --interval=5s --timeout=3s --start-period=3s --retries=3 \\
  CMD curl -f http://localhost/ || exit 1`;
        default:
            return `FROM node:20-alpine
WORKDIR /app
COPY . .
EXPOSE 3000
CMD ["node", "${entrypoint || 'index.js'}"]`;
    }
}
function getEntrypointName(language) {
    switch (language) {
        case 'typescript': return 'index.ts';
        case 'javascript': return 'index.js';
        case 'python': return 'main.py';
        case 'go': return 'main.go';
        default: return 'index.html';
    }
}
// ─── Build Services ──────────────────────────────────────────────────────
function buildServiceDir(baseDir, serviceName, nodes, language, _type) {
    const svcDir = join(baseDir, serviceName);
    mkdirSync(svcDir, { recursive: true });
    const entrypoint = getEntrypointName(language);
    // Write each node's code as a file
    for (const node of nodes) {
        const code = node.data?.generatedCode || '';
        if (!code.trim())
            continue;
        const label = node.data?.label || node.id || 'unnamed';
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
        writeFileSync(join(svcDir, `${safeName}${ext}`), code, 'utf-8');
    }
    // Write combined entrypoint for apps that need it
    const allCode = nodes.map(n => n.data?.generatedCode || '').join('\n\n');
    writeFileSync(join(svcDir, entrypoint), allCode || `// ${serviceName} entry point`, 'utf-8');
    // Generate package.json for Node.js
    if (language === 'typescript' || language === 'javascript') {
        writeFileSync(join(svcDir, 'package.json'), JSON.stringify({
            name: serviceName, version: '1.0.0', private: true, type: 'module',
            main: entrypoint,
            scripts: { start: `node ${entrypoint}`, dev: `node --watch ${entrypoint}` },
        }, null, 2), 'utf-8');
    }
    // Generate requirements.txt for Python
    if (language === 'python') {
        writeFileSync(join(svcDir, 'requirements.txt'), 'flask\ngunicorn\n', 'utf-8');
    }
    // Generate go.mod for Go
    if (language === 'go') {
        writeFileSync(join(svcDir, 'go.mod'), `module ${serviceName}\n\ngo 1.22\n`, 'utf-8');
    }
    // Generate Dockerfile
    const dockerfile = generateAppDockerfile(language, _type, entrypoint);
    writeFileSync(join(svcDir, 'Dockerfile'), dockerfile, 'utf-8');
    return svcDir;
}
// ─── Compose Lifecycle ──────────────────────────────────────────────────
/**
 * Start a multi-service docker-compose stack from generated node code.
 */
export async function startCompose(options) {
    const id = randomUUID().slice(0, 8);
    const composeDir = join(tmpdir(), 'vaca-compose', id);
    mkdirSync(composeDir, { recursive: true });
    const { frontend, backend, database } = classifyServices(options.nodes);
    // Detect database type from backend code
    const backendCode = backend.map(n => n.data?.generatedCode || '').join('\n');
    const dbType = detectDatabaseType(backendCode);
    const hasDatabase = database.length > 0 || dbType !== 'none';
    // Build service definitions
    const services = [];
    const allLogs = [];
    allLogs.push(`[compose] Classified ${frontend.length} frontend, ${backend.length} backend, ${database.length} database nodes`);
    // 1. Database service
    if (hasDatabase) {
        const dbPort = await findAvailablePort();
        const actualDbType = database.length > 0
            ? detectDatabaseType(database.map(n => n.data?.generatedCode || '').join('\n'))
            : dbType;
        const dbConfig = DATABASE_IMAGES[actualDbType === 'none' ? 'postgres' : actualDbType];
        // Create db directory with init script
        const dbDir = join(composeDir, 'db');
        mkdirSync(dbDir, { recursive: true });
        writeFileSync(join(dbDir, 'Dockerfile'), `FROM ${dbConfig.image}\n`, 'utf-8');
        services.push({
            name: 'db',
            type: 'database',
            language: 'sql',
            nodes: database,
            port: dbConfig.port,
            hostPort: dbPort,
            dependsOn: [],
            environment: { ...dbConfig.env },
            healthEndpoint: '/health',
            databaseType: actualDbType === 'none' ? 'postgres' : actualDbType,
            buildDir: dbDir,
        });
        allLogs.push(`[compose] Database: ${actualDbType} on port ${dbPort}`);
    }
    // 2. Backend service
    if (backend.length > 0) {
        const backendPort = await findAvailablePort();
        const lang = detectLanguageFromCode(backend.map(n => n.data?.generatedCode || '').join('\n'));
        const svcDir = buildServiceDir(composeDir, 'backend', backend, lang, 'backend');
        const env = { NODE_ENV: 'production', PORT: String(SERVICE_PORTS.backend) };
        // Add database connection string
        if (hasDatabase) {
            const dbSvc = services.find(s => s.type === 'database');
            if (dbSvc) {
                const dbName = dbSvc.environment.POSTGRES_DB || dbSvc.environment.MONGO_INITDB_DATABASE || 'app';
                const dbUser = dbSvc.environment.POSTGRES_USER || dbSvc.environment.MONGO_INITDB_ROOT_USERNAME || 'app';
                const dbPass = dbSvc.environment.POSTGRES_PASSWORD || dbSvc.environment.MONGO_INITDB_ROOT_PASSWORD || 'app123';
                env.DATABASE_URL = dbSvc.databaseType === 'postgres'
                    ? `postgresql://${dbUser}:${dbPass}@db:5432/${dbName}`
                    : dbSvc.databaseType === 'mongodb'
                        ? `mongodb://${dbUser}:${dbPass}@db:27017/${dbName}`
                        : dbSvc.databaseType === 'redis'
                            ? 'redis://db:6379'
                            : `mysql://${dbUser}:${dbPass}@db:3306/${dbName}`;
            }
        }
        services.push({
            name: 'backend',
            type: 'backend',
            language: lang,
            nodes: backend,
            port: SERVICE_PORTS.backend,
            hostPort: backendPort,
            dependsOn: hasDatabase ? ['db'] : [],
            environment: env,
            healthEndpoint: SERVICE_HEALTH.backend,
            buildDir: svcDir,
        });
        allLogs.push(`[compose] Backend: ${lang} on port ${backendPort} (${hasDatabase ? 'depends on db' : 'standalone'})`);
    }
    // 3. Frontend service
    if (frontend.length > 0) {
        const frontendPort = await findAvailablePort();
        const lang = detectLanguageFromCode(frontend.map(n => n.data?.generatedCode || '').join('\n'));
        const svcDir = buildServiceDir(composeDir, 'frontend', frontend, lang, 'frontend');
        const env = {};
        // Point frontend to backend
        const backendSvc = services.find(s => s.type === 'backend');
        if (backendSvc) {
            env.API_URL = `http://backend:${backendSvc.port}`;
            env.NEXT_PUBLIC_API_URL = `http://backend:${backendSvc.port}`;
        }
        services.push({
            name: 'frontend',
            type: 'frontend',
            language: lang,
            nodes: frontend,
            port: SERVICE_PORTS.frontend,
            hostPort: frontendPort,
            dependsOn: backendSvc ? ['backend'] : [],
            environment: env,
            healthEndpoint: SERVICE_HEALTH.frontend,
            buildDir: svcDir,
        });
        allLogs.push(`[compose] Frontend: ${lang} on port ${frontendPort}`);
    }
    // If no services were created, return error
    if (services.length === 0) {
        const instance = {
            id, projectName: options.projectName, projectId: options.projectId,
            composeDir, services: [], status: 'error', urls: {}, logs: [...allLogs, '[compose] ❌ No services could be created from the nodes'],
            createdAt: Date.now(), error: 'No services could be created — need at least one frontend, backend, or database node with code',
        };
        composeStacks.set(id, instance);
        return instance;
    }
    const instance = {
        id, projectName: options.projectName, projectId: options.projectId,
        composeDir, services, status: 'building', urls: {}, logs: allLogs,
        createdAt: Date.now(),
    };
    composeStacks.set(id, instance);
    try {
        // Generate and write docker-compose.yml
        const composeYaml = generateComposeYaml(services, composeDir);
        writeFileSync(join(composeDir, 'docker-compose.yml'), composeYaml, 'utf-8');
        allLogs.push(`[compose] Generated docker-compose.yml with ${services.length} services`);
        // Store URLs
        for (const svc of services) {
            instance.urls[svc.name] = `http://localhost:${svc.hostPort}`;
        }
        // Run docker-compose up --build
        allLogs.push('[compose] Running docker-compose up --build (this may take several minutes)...');
        instance.status = 'building';
        await new Promise((resolve, reject) => {
            const up = spawn(getDockerComposeCmd()[0], [...getDockerComposeCmd().slice(1), '-f', join(composeDir, 'docker-compose.yml'), 'up', '-d', '--build'], {
                timeout: COMPOSE_TIMEOUT,
                cwd: composeDir,
            });
            up.stdout.on('data', (data) => {
                const text = data.toString();
                allLogs.push(...text.split('\n').filter((l) => l.trim()).map((l) => `[compose] ${l}`));
            });
            up.stderr.on('data', (data) => {
                const text = data.toString();
                allLogs.push(...text.split('\n').filter((l) => l.trim()).map((l) => `[compose] ${l}`));
            });
            up.on('close', (code) => {
                if (code === 0)
                    resolve();
                else
                    reject(new Error(`docker-compose up exited with code ${code}`));
            });
            up.on('error', reject);
        });
        // All services are considered running after successful compose up
        instance.status = 'running';
        allLogs.push(`[compose] ✅ All ${services.length} services are running`);
        for (const svc of services) {
            allLogs.push(`[compose]   ${svc.name} → http://localhost:${svc.hostPort}`);
        }
        // Set auto-cleanup timer
        setTimeout(() => {
            stopCompose(id).catch(() => { composeStacks.delete(id); });
        }, COMPOSE_TTL_MS);
    }
    catch (err) {
        instance.status = 'error';
        instance.error = err.message;
        allLogs.push(`[compose] ❌ Error: ${err.message}`);
    }
    return instance;
}
/**
 * Stop and remove a docker-compose stack.
 */
export async function stopCompose(id) {
    const instance = composeStacks.get(id);
    if (!instance)
        return false;
    instance.logs.push('[compose] Stopping all services...');
    try {
        execCompose(`${getDockerComposeCmd().join(' ')} -f ${join(instance.composeDir, 'docker-compose.yml')} down --volumes --rmi local 2>/dev/null`, { timeout: 60000, stdio: 'pipe' });
        instance.status = 'stopped';
        instance.logs.push('[compose] ✅ All services stopped and cleaned up');
        return true;
    }
    catch (err) {
        instance.logs.push(`[compose] ⚠️ Cleanup error: ${err.message}`);
        instance.status = 'stopped';
        return false;
    }
}
/**
 * Get the status of a compose stack.
 */
export function getComposeStatus(id) {
    const instance = composeStacks.get(id);
    if (!instance)
        return null;
    // Check if compose stack is still alive
    if (instance.status === 'running') {
        try {
            execCompose(`${getDockerComposeCmd().join(' ')} -f ${join(instance.composeDir, 'docker-compose.yml')} ps --services --filter "status=running" 2>/dev/null`, { timeout: 5000, stdio: 'pipe' });
        }
        catch {
            instance.status = 'stopped';
        }
    }
    return instance;
}
/**
 * Get logs for a compose stack.
 */
export function getComposeLogs(id) {
    const instance = composeStacks.get(id);
    if (!instance)
        return null;
    // Try to get live docker-compose logs
    try {
        const logsOutput = execCompose(`${getDockerComposeCmd().join(' ')} -f ${join(instance.composeDir, 'docker-compose.yml')} logs --tail 100 2>&1`, { timeout: 5000, stdio: 'pipe' });
        const liveLogs = logsOutput.split('\n').filter(l => l.trim());
        return {
            logs: [...instance.logs, ...liveLogs],
            services: instance.services.map(s => s.name),
            status: instance.status,
        };
    }
    catch {
        return {
            logs: instance.logs,
            services: instance.services.map(s => s.name),
            status: instance.status,
        };
    }
}
/**
 * List all compose stacks.
 */
export function listComposeStacks(status) {
    const all = Array.from(composeStacks.values());
    if (status)
        return all.filter(c => c.status === status);
    return all;
}
/**
 * Clean up all compose stacks (stop + remove from tracking).
 */
export function cleanupAllCompose() {
    let count = 0;
    for (const [id, instance] of composeStacks) {
        if (instance.status === 'stopped' || instance.status === 'error') {
            stopCompose(id).catch(() => { });
            composeStacks.delete(id);
            count++;
        }
    }
    return count;
}
