/**
 * Tool System API Routes — expose the ToolRegistry via HTTP endpoints.
 * Mounted at /api/tools in the main server.
 */
import { Router } from 'express';
import { getRegistry } from '../tools/ToolRegistry.js';
export const toolRoutes = Router();
// ─── Helpers ────────────────────────────────────────────────────────────────
function buildContext(req) {
    return {
        userId: req.userId || req.ip || 'anonymous',
        sessionId: req.headers['x-session-id'] || undefined,
        projectId: req.headers['x-project-id'] || undefined,
        metadata: {
            projectRoot: process.cwd(),
            clientIp: req.ip,
            userAgent: req.headers['user-agent'],
        },
        permissionMode: req.headers['x-permission-mode'] || 'ask_each',
        req,
        res: undefined,
    };
}
function handleError(res, err, status = 500) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(status).json({ success: false, error: msg });
}
// ═════════════════════════════════════════════════════════════════════════
// Permission Manager Endpoints
// (must come before /:name routes to avoid parameter capture)
// ═════════════════════════════════════════════════════════════════════════
// ─── GET /api/tools/permissions/summary — Policy configuration summary ────────
toolRoutes.get('/permissions/summary', (_req, res) => {
    try {
        const summary = getRegistry().permissionManager.getPolicySummary();
        res.json({ success: true, data: summary });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── GET /api/tools/permissions/approvals — Pending approval requests ────────
toolRoutes.get('/permissions/approvals', (_req, res) => {
    try {
        const approvals = getRegistry().permissionManager.getPendingApprovals();
        res.json({ success: true, data: approvals, total: approvals.length });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── POST /api/tools/permissions/approvals/:id/approve — Approve a request ────
toolRoutes.post('/permissions/approvals/:id/approve', (req, res) => {
    try {
        const approved = getRegistry().permissionManager.approve(req.params.id, req.userId);
        if (!approved) {
            res.status(404).json({ success: false, error: 'Approval request not found or already decided', errorCode: 'NOT_FOUND' });
            return;
        }
        res.json({ success: true, data: { message: 'Approval granted', approvalId: req.params.id } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── POST /api/tools/permissions/approvals/:id/deny — Deny a request ──────────
toolRoutes.post('/permissions/approvals/:id/deny', (req, res) => {
    try {
        const denied = getRegistry().permissionManager.deny(req.params.id, req.userId);
        if (!denied) {
            res.status(404).json({ success: false, error: 'Approval request not found or already decided', errorCode: 'NOT_FOUND' });
            return;
        }
        res.json({ success: true, data: { message: 'Approval denied', approvalId: req.params.id } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── GET /api/tools/permissions/audit — Audit trail ───────────────────────────
toolRoutes.get('/permissions/audit', (req, res) => {
    try {
        const limit = req.query.limit ? parseInt(req.query.limit, 10) : undefined;
        const audit = getRegistry().permissionManager.getAuditLog(limit);
        res.json({ success: true, data: audit, total: audit.length });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── DELETE /api/tools/permissions/audit — Clear audit trail ──────────────────
toolRoutes.delete('/permissions/audit', (_req, res) => {
    try {
        getRegistry().permissionManager.clearAuditLog();
        res.json({ success: true, data: { message: 'Audit log cleared' } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── PUT /api/tools/permissions/users/:userId — Set user policy ───────────────
toolRoutes.put('/permissions/users/:userId', (req, res) => {
    try {
        const { mode } = req.body;
        const validModes = ['allow_all', 'auto_approve', 'ask_each', 'deny_all', 'plan_only'];
        if (!mode || !validModes.includes(mode)) {
            res.status(400).json({ success: false, error: `Invalid mode. Valid: ${validModes.join(', ')}`, errorCode: 'VALIDATION_ERROR' });
            return;
        }
        getRegistry().permissionManager.setUserPolicy(req.params.userId, mode);
        res.json({ success: true, data: { userId: req.params.userId, permissionMode: mode } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── DELETE /api/tools/permissions/users/:userId — Clear user policy ───────────
toolRoutes.delete('/permissions/users/:userId', (req, res) => {
    try {
        getRegistry().permissionManager.clearUserPolicy(req.params.userId);
        res.json({ success: true, data: { message: `User policy cleared for ${req.params.userId}` } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── PUT /api/tools/permissions/sessions/:sessionId — Set session policy ───────
toolRoutes.put('/permissions/sessions/:sessionId', (req, res) => {
    try {
        const { mode } = req.body;
        const validModes = ['allow_all', 'auto_approve', 'ask_each', 'deny_all', 'plan_only'];
        if (!mode || !validModes.includes(mode)) {
            res.status(400).json({ success: false, error: `Invalid mode. Valid: ${validModes.join(', ')}`, errorCode: 'VALIDATION_ERROR' });
            return;
        }
        getRegistry().permissionManager.setSessionPolicy(req.params.sessionId, mode);
        res.json({ success: true, data: { sessionId: req.params.sessionId, permissionMode: mode } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── DELETE /api/tools/permissions/sessions/:sessionId — Clear session policy ─
toolRoutes.delete('/permissions/sessions/:sessionId', (req, res) => {
    try {
        getRegistry().permissionManager.clearSessionPolicy(req.params.sessionId);
        res.json({ success: true, data: { message: `Session policy cleared for ${req.params.sessionId}` } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── PUT /api/tools/permissions/risk/:level — Set risk-level policy ───────────
toolRoutes.put('/permissions/risk/:level', (req, res) => {
    try {
        const { mode } = req.body;
        const level = req.params.level;
        const validLevels = ['readonly', 'low', 'medium', 'high', 'critical'];
        const validModes = ['allow_all', 'auto_approve', 'ask_each', 'deny_all', 'plan_only'];
        if (!validLevels.includes(level)) {
            res.status(400).json({ success: false, error: `Invalid risk level. Valid: ${validLevels.join(', ')}`, errorCode: 'VALIDATION_ERROR' });
            return;
        }
        if (!mode || !validModes.includes(mode)) {
            res.status(400).json({ success: false, error: `Invalid mode. Valid: ${validModes.join(', ')}`, errorCode: 'VALIDATION_ERROR' });
            return;
        }
        getRegistry().permissionManager.setRiskLevelPolicy(level, mode);
        res.json({ success: true, data: { riskLevel: level, permissionMode: mode } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── DELETE /api/tools/permissions/risk/:level — Clear risk-level policy ──────
toolRoutes.delete('/permissions/risk/:level', (req, res) => {
    try {
        const level = req.params.level;
        getRegistry().permissionManager.clearRiskLevelPolicy(level);
        res.json({ success: true, data: { message: `Risk-level policy cleared for ${level}` } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ═════════════════════════════════════════════════════════════════════════
// Tool Listing & Execution Endpoints
// ═════════════════════════════════════════════════════════════════════════
// ─── GET /api/tools — List all tools (with optional query params) ───────────
toolRoutes.get('/', (req, res) => {
    try {
        const registry = getRegistry();
        const query = {};
        if (req.query.category)
            query.category = req.query.category;
        if (req.query.riskLevel)
            query.riskLevel = req.query.riskLevel;
        if (req.query.search)
            query.search = req.query.search;
        if (req.query.enabled !== undefined)
            query.enabled = req.query.enabled === 'true';
        const tools = registry.all(Object.keys(query).length > 0 ? query : undefined);
        res.json({ success: true, data: tools, total: tools.length });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── GET /api/tools/manifest — AI function-calling manifest ─────────────────
toolRoutes.get('/manifest', (_req, res) => {
    try {
        const manifest = getRegistry().toToolManifest();
        res.json({ success: true, data: manifest });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── GET /api/tools/grouped — Tools grouped by category ─────────────────────
toolRoutes.get('/grouped', (_req, res) => {
    try {
        const grouped = getRegistry().grouped;
        res.json({ success: true, data: grouped });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── GET /api/tools/executions — Execution history ──────────────────────────
toolRoutes.get('/executions', (req, res) => {
    try {
        const toolName = req.query.toolName;
        const history = getRegistry().getHistory(toolName);
        res.json({ success: true, data: history, total: history.length });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── GET /api/tools/executions/:id — Single execution details ───────────────
toolRoutes.get('/executions/:id', (req, res) => {
    try {
        const execution = getRegistry().getExecution(req.params.id);
        if (!execution) {
            res.status(404).json({ success: false, error: 'Execution not found', errorCode: 'NOT_FOUND' });
            return;
        }
        res.json({ success: true, data: execution });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── POST /api/tools/:name/execute — Execute a tool ─────────────────────────
// NOTE: /:name routes must come AFTER all specific routes above to avoid
// catching "manifest", "grouped", "executions" as tool names.
toolRoutes.post('/:name/execute', async (req, res) => {
    try {
        const { name } = req.params;
        const input = req.body?.input ?? req.body ?? {};
        const context = buildContext(req);
        context.res = res;
        const registry = getRegistry();
        const tool = registry.get(name);
        if (!tool) {
            res.status(404).json({ success: false, error: `Tool not found: ${name}`, errorCode: 'NOT_FOUND' });
            return;
        }
        // Validate input against schema
        const schema = tool.inputSchema;
        if (schema.required) {
            for (const field of schema.required) {
                if (input[field] === undefined || input[field] === null) {
                    res.status(400).json({ success: false, error: `Missing required field: ${field}`, errorCode: 'VALIDATION_ERROR' });
                    return;
                }
            }
        }
        const result = await registry.execute(name, input, context);
        const status = result.success ? 200 : result.errorCode === 'PERMISSION_DENIED' ? 403 : 400;
        res.status(status).json(result);
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── POST /api/tools/:name/interrupt — Interrupt a running execution ────────
toolRoutes.post('/:name/interrupt', async (req, res) => {
    try {
        const executionId = req.body?.executionId;
        if (!executionId) {
            res.status(400).json({ success: false, error: 'executionId is required', errorCode: 'VALIDATION_ERROR' });
            return;
        }
        const interrupted = await getRegistry().interrupt(executionId);
        if (!interrupted) {
            res.status(404).json({ success: false, error: 'Execution not found or already completed', errorCode: 'NOT_FOUND' });
            return;
        }
        res.json({ success: true, data: { message: 'Execution interrupted', executionId } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── PUT /api/tools/:name/permission — Set permission override ──────────────
toolRoutes.put('/:name/permission', (req, res) => {
    try {
        const { name } = req.params;
        const { mode } = req.body;
        const validModes = ['allow_all', 'auto_approve', 'ask_each', 'deny_all', 'plan_only'];
        if (!mode || !validModes.includes(mode)) {
            res.status(400).json({ success: false, error: `Invalid mode. Valid: ${validModes.join(', ')}`, errorCode: 'VALIDATION_ERROR' });
            return;
        }
        const registry = getRegistry();
        if (!registry.has(name)) {
            res.status(404).json({ success: false, error: `Tool not found: ${name}`, errorCode: 'NOT_FOUND' });
            return;
        }
        registry.setPermissionOverride(name, mode);
        res.json({ success: true, data: { tool: name, permissionMode: mode } });
    }
    catch (err) {
        handleError(res, err);
    }
});
// ─── DELETE /api/tools/:name/permission — Clear permission override ─────────
toolRoutes.delete('/:name/permission', (req, res) => {
    try {
        const registry = getRegistry();
        registry.clearPermissionOverride(req.params.name);
        res.json({ success: true, data: { message: `Permission override cleared for ${req.params.name}` } });
    }
    catch (err) {
        handleError(res, err);
    }
});
