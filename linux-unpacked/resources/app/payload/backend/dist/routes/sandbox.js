/**
 * Sandbox Routes
 * ==============
 * Preview & Docker container management for generated apps.
 *
 * Static Preview:
 *   POST /api/sandbox/preview      — Generate preview HTML from node code
 *   GET  /api/sandbox/preview/:id  — Serve generated preview HTML
 *
 * Docker Service:
 *   POST /api/sandbox/run           — Build & start Docker container
 *   GET  /api/sandbox/running       — List managed containers
 *   GET  /api/sandbox/run/:id       — Container status
 *   POST /api/sandbox/run/:id/stop  — Stop container
 *   GET  /api/sandbox/run/:id/logs  — Container logs
 *   POST /api/sandbox/cleanup       — Cleanup stopped containers
 */
import { Router } from 'express';
import { projects } from '../db/projects.js';
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { randomUUID } from 'crypto';
import { tmpdir } from 'os';
import { startContainer, stopContainer, getContainerStatus, getContainerLogs, listContainers, cleanupAllStopped, isDockerAvailable, execDocker, } from '../sandbox/containerManager.js';
import { startCompose, stopCompose, getComposeStatus, getComposeLogs, cleanupAllCompose, } from '../sandbox/composeManager.js';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PREVIEWS_DIR = path.join(tmpdir(), 'vaca-sandbox-previews');
try {
    fs.mkdirSync(PREVIEWS_DIR, { recursive: true });
}
catch { /* exists */ }
export const sandboxRoutes = Router();
// ═══════════════════════════════════════════════════════════════════════════
// Docker & Sandbox Status
// ═══════════════════════════════════════════════════════════════════════════
/** GET /api/sandbox/status — Check sandbox/Docker availability */
sandboxRoutes.get('/status', (_req, res) => {
    const dockerAvailable = isDockerAvailable();
    const dockerVersion = (() => {
        try {
            return execDocker('--version', { timeout: 3000 }).trim();
        }
        catch {
            return null;
        }
    })();
    // Check if user is IN the docker group (membership, not capability).
    // Does NOT use execDocker's sudo fallback — we want to know if the
    // user is actually in the group, not just whether Docker can run via sudo.
    const inDockerGroup = (() => {
        // Try sg docker -c 'groups' which activates group membership and checks
        try {
            const result = execSync('sg docker -c "groups" 2>/dev/null', {
                encoding: 'utf-8', stdio: 'pipe', timeout: 5000,
            }).trim();
            if (result.includes('docker'))
                return true;
        }
        catch { /* sg failed — user may not be in docker group */ }
        // Fallback: check the current process's groups (no group activation)
        try {
            const groups = execSync('groups', {
                encoding: 'utf-8', stdio: 'pipe', timeout: 3000,
            }).trim();
            return groups.includes('docker');
        }
        catch {
            return false;
        }
    })();
    // Check if Docker daemon is actually accessible (uses execDocker which
    // tries direct → sg docker -c → sudo as fallbacks)
    const daemonAccessible = (() => {
        try {
            execDocker('info --format "{{.ServerVersion}}"', { timeout: 5000 });
            return true;
        }
        catch {
            return false;
        }
    })();
    // Determine the most helpful hint message
    let hint;
    if (!dockerAvailable) {
        hint = 'Docker is not installed or the daemon is not running. Install Docker Desktop or run: `sudo apt install docker.io` and start the daemon.';
    }
    else if (!inDockerGroup && !daemonAccessible) {
        hint = 'Docker CLI is installed but your user is not in the docker group. Run: `sudo usermod -aG docker $USER && newgrp docker`';
    }
    else if (inDockerGroup && !daemonAccessible) {
        hint = 'Docker CLI and group membership detected, but the daemon is not accessible. Is Docker Desktop running? Try: `sudo systemctl start docker`';
    }
    else if (!inDockerGroup && daemonAccessible) {
        hint = 'Docker daemon is accessible (via sudo), but your user is not in the docker group. For better security, add your user: `sudo usermod -aG docker $USER && newgrp docker`';
    }
    res.json({
        success: true,
        docker: {
            available: dockerAvailable,
            version: dockerVersion,
            inDockerGroup,
            daemonAccessible,
            cliInstalled: !!dockerVersion,
        },
        local: {
            node: (() => { try {
                execSync('node --version', { stdio: 'pipe', timeout: 3000 });
                return true;
            }
            catch {
                return false;
            } })(),
            python: (() => { try {
                execSync('python3 --version', { stdio: 'pipe', timeout: 3000 });
                return true;
            }
            catch {
                return false;
            } })(),
        },
        hint,
    });
});
// ═══════════════════════════════════════════════════════════════════════════
// Docker Container Management
// ═══════════════════════════════════════════════════════════════════════════
/** POST /api/sandbox/run — Start a Docker container from project code */
sandboxRoutes.post('/run', async (req, res) => {
    try {
        const { projectId, nodes: inlineNodes, projectName: fallbackName } = req.body;
        if (!projectId)
            return void res.status(400).json({ error: 'projectId is required' });
        if (!isDockerAvailable()) {
            return void res.status(503).json({
                error: 'Docker is not available on this system.',
                hint: 'Install Docker and ensure the daemon is running.',
            });
        }
        // Try to find project in backend store first
        let project = projects.getById(projectId);
        let codeNodes = [];
        if (project) {
            // Get code nodes from stored project
            codeNodes = project.nodes.filter((n) => n.type !== 'master' && n.data?.generatedCode);
        }
        else if (inlineNodes && Array.isArray(inlineNodes)) {
            // Fallback: use nodes sent directly in the request body
            codeNodes = inlineNodes.filter((n) => n.type !== 'master' && n.data?.generatedCode);
            project = {
                name: fallbackName || 'Untitled',
                targetOS: 'linux',
            };
        }
        else {
            return void res.status(404).json({
                error: 'Project not found',
                hint: 'Make sure the project is saved to the backend, or send nodes in the request body.',
            });
        }
        if (codeNodes.length === 0) {
            return void res.status(400).json({
                error: 'No generated code found. Generate code first.',
                hint: 'Run code generation before starting the Docker service.',
            });
        }
        const instance = await startContainer({
            projectName: project.name || 'Untitled',
            projectId,
            nodes: codeNodes,
        });
        res.json({
            success: instance.status !== 'error',
            containerId: instance.id,
            status: instance.status,
            url: instance.url,
            language: instance.language,
            projectName: instance.projectName,
            error: instance.error || undefined,
        });
    }
    catch (err) {
        console.error('[sandbox] Container start failed:', err);
        res.status(500).json({ error: err.message || 'Failed to start container' });
    }
});
/** GET /api/sandbox/running — List all managed containers */
sandboxRoutes.get('/running', (_req, res) => {
    const all = listContainers();
    res.json({
        success: true,
        containers: all.map(c => ({
            id: c.id,
            projectName: c.projectName,
            status: c.status,
            url: c.url,
            language: c.language,
            createdAt: c.createdAt,
        })),
        count: all.length,
    });
});
/** GET /api/sandbox/run/:id — Status of a specific container */
sandboxRoutes.get('/run/:id', (req, res) => {
    const { id } = req.params;
    const instance = getContainerStatus(id);
    if (!instance)
        return void res.status(404).json({ error: 'Container not found' });
    res.json({
        success: true,
        container: {
            id: instance.id,
            dockerId: instance.dockerId,
            projectName: instance.projectName,
            status: instance.status,
            url: instance.url,
            port: instance.hostPort,
            language: instance.language,
            entrypoint: instance.entrypoint,
            createdAt: instance.createdAt,
            error: instance.error,
        },
    });
});
/** POST /api/sandbox/run/:id/stop — Stop and remove a container */
sandboxRoutes.post('/run/:id/stop', async (req, res) => {
    try {
        const { id } = req.params;
        const result = await stopContainer(id);
        res.json({
            success: result,
            message: result ? 'Container stopped and removed' : 'Container not found',
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message || 'Failed to stop container' });
    }
});
/** GET /api/sandbox/run/:id/logs — Container logs */
sandboxRoutes.get('/run/:id/logs', (req, res) => {
    const { id } = req.params;
    const logs = getContainerLogs(id);
    if (!logs)
        return void res.status(404).json({ error: 'Container not found' });
    res.json({
        success: true,
        logs: logs.logs,
        containerStatus: logs.status,
    });
});
/** POST /api/sandbox/cleanup — Clean up all stopped containers */
sandboxRoutes.post('/cleanup', (_req, res) => {
    const count = cleanupAllStopped();
    res.json({ success: true, cleaned: count, message: `Cleaned up ${count} container(s)` });
});
// ═══════════════════════════════════════════════════════════════════════════
// Docker Compose Multi-Service
// ═══════════════════════════════════════════════════════════════════════════
/** POST /api/sandbox/compose — Start a multi-service docker-compose stack */
sandboxRoutes.post('/compose', async (req, res) => {
    try {
        const { projectId } = req.body;
        if (!projectId)
            return void res.status(400).json({ error: 'projectId is required' });
        if (!isDockerAvailable()) {
            return void res.status(503).json({
                error: 'Docker is not available on this system.',
                hint: 'Install Docker and ensure the daemon is running.',
            });
        }
        const project = (await import('../db/projects.js')).projects.getById(projectId);
        if (!project)
            return void res.status(404).json({ error: 'Project not found' });
        const codeNodes = project.nodes.filter((n) => n.type !== 'master' && n.data?.generatedCode);
        if (codeNodes.length === 0) {
            return void res.status(400).json({
                error: 'No generated code found. Generate code first.',
                hint: 'Run code generation before starting compose services.',
            });
        }
        const instance = await startCompose({
            projectName: project.name || 'Untitled',
            projectId,
            nodes: codeNodes,
        });
        res.json({
            success: instance.status !== 'error',
            composeId: instance.id,
            status: instance.status,
            urls: instance.urls,
            services: instance.services.map(s => ({
                name: s.name,
                type: s.type,
                url: instance.urls[s.name],
                language: s.language,
            })),
            projectName: instance.projectName,
            error: instance.error || undefined,
        });
    }
    catch (err) {
        console.error('[sandbox] Compose start failed:', err);
        res.status(500).json({ error: err.message || 'Failed to start compose services' });
    }
});
/** GET /api/sandbox/compose/:id — Get compose stack status */
sandboxRoutes.get('/compose/:id', (req, res) => {
    const { id } = req.params;
    const instance = getComposeStatus(id);
    if (!instance)
        return void res.status(404).json({ error: 'Compose stack not found' });
    res.json({
        success: true,
        compose: {
            id: instance.id,
            projectName: instance.projectName,
            status: instance.status,
            urls: instance.urls,
            services: instance.services.map(s => ({
                name: s.name,
                type: s.type,
                port: s.hostPort,
                language: s.language,
                dependsOn: s.dependsOn,
            })),
            createdAt: instance.createdAt,
            error: instance.error,
        },
    });
});
/** POST /api/sandbox/compose/:id/stop — Stop and remove a compose stack */
sandboxRoutes.post('/compose/:id/stop', async (req, res) => {
    try {
        const { id } = req.params;
        const result = await stopCompose(id);
        res.json({
            success: result,
            message: result ? 'Compose stack stopped and removed' : 'Compose stack not found',
        });
    }
    catch (err) {
        res.status(500).json({ error: err.message || 'Failed to stop compose stack' });
    }
});
/** GET /api/sandbox/compose/:id/logs — Get compose stack logs */
sandboxRoutes.get('/compose/:id/logs', (req, res) => {
    const { id } = req.params;
    const logs = getComposeLogs(id);
    if (!logs)
        return void res.status(404).json({ error: 'Compose stack not found' });
    res.json({
        success: true,
        logs: logs.logs,
        services: logs.services,
        status: logs.status,
    });
});
/** POST /api/sandbox/compose/cleanup — Clean up all compose stacks */
sandboxRoutes.post('/compose/cleanup', (_req, res) => {
    const count = cleanupAllCompose();
    res.json({ success: true, cleaned: count, message: `Cleaned up ${count} compose stack(s)` });
});
// ═══════════════════════════════════════════════════════════════════════════
// Static HTML Preview
// ═══════════════════════════════════════════════════════════════════════════
/** POST /api/sandbox/preview — Generate a sandbox HTML preview */
sandboxRoutes.post('/preview', async (req, res) => {
    try {
        const { projectId, nodes: inlineNodes, projectName: fallbackName } = req.body;
        // Try to find project in backend store first
        let project = projectId ? projects.getById(projectId) : undefined;
        let codeNodes = [];
        if (project) {
            // Get code nodes from stored project
            codeNodes = project.nodes.filter((n) => n.type !== 'master' && n.data?.generatedCode);
        }
        else if (inlineNodes && Array.isArray(inlineNodes)) {
            // Fallback: use nodes sent directly in the request body
            codeNodes = inlineNodes.filter((n) => n.type !== 'master' && n.data?.generatedCode);
            // Create a minimal project object for the HTML builder
            project = {
                name: fallbackName || 'Untitled',
                targetOS: 'linux',
            };
        }
        else {
            return void res.status(400).json({
                error: 'No code found to preview.',
                hint: 'Generate code first, or provide nodes in the request body.',
            });
        }
        if (codeNodes.length === 0) {
            return void res.status(400).json({
                error: 'No generated code found. Generate code first.',
                hint: 'Run code generation before previewing.',
            });
        }
        const previewId = randomUUID().slice(0, 8);
        const preview = buildSandboxHtml(project, codeNodes, previewId);
        const previewPath = path.join(PREVIEWS_DIR, `${previewId}.html`);
        fs.writeFileSync(previewPath, preview.html, 'utf-8');
        res.json({
            success: true,
            previewId,
            previewUrl: `/api/sandbox/preview/${previewId}`,
            nodeCount: codeNodes.length,
            totalCodeChars: preview.totalChars,
            hasErrors: preview.hasErrors,
            warnings: preview.warnings,
        });
    }
    catch (err) {
        console.error('[sandbox] Preview generation failed:', err);
        res.status(500).json({ error: err.message || 'Preview generation failed' });
    }
});
/** GET /api/sandbox/preview/:id — Serve a previously generated preview */
sandboxRoutes.get('/preview/:id', (req, res) => {
    const { id } = req.params;
    const previewPath = path.join(PREVIEWS_DIR, `${id}.html`);
    if (!fs.existsSync(previewPath))
        return void res.status(404).json({ error: 'Preview not found or expired' });
    const html = fs.readFileSync(previewPath, 'utf-8');
    res.setHeader('Content-Security-Policy', "default-src 'self' 'unsafe-inline' 'unsafe-eval'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:;");
    res.setHeader('X-Frame-Options', 'SAMEORIGIN');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.send(html);
});
// ═══════════════════════════════════════════════════════════════════════════
// Preview HTML Builder — imported from separate module
// ═══════════════════════════════════════════════════════════════════════════
import { buildSandboxHtml } from '../sandbox/previewHtmlBuilder.js';
