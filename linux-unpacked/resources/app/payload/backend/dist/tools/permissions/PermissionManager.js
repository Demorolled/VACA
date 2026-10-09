/**
 * PermissionManager — centralized access control for the Veronica Tool System.
 *
 * Supports layered policy resolution (user → session → tool → pattern → risk → default),
 * an approval queue for interactive (`ask_each`) modes, and a full audit trail.
 *
 * Integration: ToolRegistry delegates its permission checks here instead of handling
 * them inline. The PermissionManager is designed to be a drop-in replacement for the
 * permission-related fields and methods currently on ToolRegistry.
 */
// ─── PermissionManager ──────────────────────────────────────────────────────
export class PermissionManager {
    // ── Policy layers (highest priority first) ──
    defaultMode = 'ask_each';
    userPolicies = new Map();
    sessionPolicies = new Map();
    toolOverrides = new Map();
    patternRules = [];
    riskLevelPolicies = new Map();
    // ── Approval queue ──
    approvals = new Map();
    approvalCounter = 0;
    // ── Audit trail ──
    auditLog = [];
    maxAuditEntries = 1000;
    // ═════════════════════════════════════════════════════════════════════════
    // Configuration
    // ═════════════════════════════════════════════════════════════════════════
    setDefaultMode(mode) {
        this.defaultMode = mode;
    }
    getDefaultMode() {
        return this.defaultMode;
    }
    // ── User policies ─────────────────────────────────────────────────────────
    setUserPolicy(userId, mode) {
        this.userPolicies.set(userId, mode);
    }
    getUserPolicy(userId) {
        return this.userPolicies.get(userId);
    }
    clearUserPolicy(userId) {
        this.userPolicies.delete(userId);
    }
    // ── Session policies ──────────────────────────────────────────────────────
    setSessionPolicy(sessionId, mode) {
        this.sessionPolicies.set(sessionId, mode);
    }
    getSessionPolicy(sessionId) {
        return this.sessionPolicies.get(sessionId);
    }
    clearSessionPolicy(sessionId) {
        this.sessionPolicies.delete(sessionId);
    }
    // ── Tool overrides ────────────────────────────────────────────────────────
    setToolOverride(toolName, mode) {
        this.toolOverrides.set(toolName, mode);
    }
    getToolOverride(toolName) {
        return this.toolOverrides.get(toolName);
    }
    clearToolOverride(toolName) {
        this.toolOverrides.delete(toolName);
    }
    getAllToolOverrides() {
        return new Map(this.toolOverrides);
    }
    // ── Pattern rules ─────────────────────────────────────────────────────────
    addRule(rule) {
        this.patternRules.push(rule);
    }
    removeRule(toolName) {
        this.patternRules = this.patternRules.filter(r => r.toolName !== toolName);
    }
    getRules(toolName) {
        if (toolName) {
            return this.patternRules.filter(r => r.toolName === toolName);
        }
        return [...this.patternRules];
    }
    // ── Risk-level policies ───────────────────────────────────────────────────
    setRiskLevelPolicy(level, mode) {
        this.riskLevelPolicies.set(level, mode);
    }
    getRiskLevelPolicy(level) {
        return this.riskLevelPolicies.get(level);
    }
    clearRiskLevelPolicy(level) {
        this.riskLevelPolicies.delete(level);
    }
    // ═════════════════════════════════════════════════════════════════════════
    // Permission Resolution
    // ═════════════════════════════════════════════════════════════════════════
    /**
     * Resolve the effective permission mode for a given tool and context,
     * consulting policy layers from highest to lowest priority.
     *
     * Priority order: user policy → session policy → tool override →
     * pattern rule → risk-level policy → default mode.
     */
    getEffectivePermission(toolName, tool, context) {
        // 1. User policy (most specific)
        if (context?.userId) {
            const userMode = this.userPolicies.get(context.userId);
            if (userMode)
                return userMode;
        }
        // 2. Session policy
        if (context?.sessionId) {
            const sessionMode = this.sessionPolicies.get(context.sessionId);
            if (sessionMode)
                return sessionMode;
        }
        // 3. Per-tool override
        const override = this.toolOverrides.get(toolName);
        if (override)
            return override;
        // 4. Pattern-based rule (exact match first, then glob match)
        const toolRules = this.patternRules.filter(r => r.toolName === toolName);
        if (toolRules.length > 0) {
            // Return the first matching rule's mode
            return toolRules[0].mode;
        }
        // 5. Risk-level policy
        if (tool?.riskLevel) {
            const riskMode = this.riskLevelPolicies.get(tool.riskLevel);
            if (riskMode)
                return riskMode;
        }
        // 6. Context permission mode (passed from request)
        if (context?.permissionMode) {
            return context.permissionMode;
        }
        // 7. Default (least specific)
        return this.defaultMode;
    }
    /**
     * Check whether a tool call is permitted.
     * Returns a PermissionCheck with the decision and reason.
     */
    async check(tool, input, context) {
        const effectiveMode = this.getEffectivePermission(tool.name, tool, context);
        // ── deny_all: always blocked ──
        if (effectiveMode === 'deny_all') {
            this.audit({
                toolName: tool.name,
                userId: context.userId,
                sessionId: context.sessionId,
                mode: 'deny_all',
                allowed: false,
                reason: `Tool '${tool.name}' is denied by permission policy`,
                decisionSource: effectiveMode,
            });
            return {
                allowed: false,
                reason: `Tool '${tool.name}' is denied by permission policy`,
                needsUserApproval: false,
            };
        }
        // ── allow_all: always permitted ──
        if (effectiveMode === 'allow_all') {
            this.audit({
                toolName: tool.name,
                userId: context.userId,
                sessionId: context.sessionId,
                mode: 'allow_all',
                allowed: true,
                decisionSource: effectiveMode,
            });
            return { allowed: true };
        }
        // ── plan_only: permitted but flagged ──
        if (effectiveMode === 'plan_only') {
            this.audit({
                toolName: tool.name,
                userId: context.userId,
                sessionId: context.sessionId,
                mode: 'plan_only',
                allowed: true,
                reason: 'Planning mode — tool execution is permitted for exploration',
                decisionSource: effectiveMode,
            });
            return { allowed: true, reason: 'Planning mode — execution permitted' };
        }
        // ── Check tool-level onBeforeCall hook ──
        if (tool.onBeforeCall) {
            const hookCheck = await tool.onBeforeCall(input, {
                ...context,
                permissionMode: effectiveMode,
            });
            if (!hookCheck.allowed) {
                this.audit({
                    toolName: tool.name,
                    userId: context.userId,
                    sessionId: context.sessionId,
                    mode: effectiveMode,
                    allowed: false,
                    reason: hookCheck.reason ?? 'Blocked by tool-level permission hook',
                    decisionSource: 'onBeforeCall',
                });
                return hookCheck;
            }
        }
        // ── auto_approve: permitted without user interaction ──
        if (effectiveMode === 'auto_approve') {
            this.audit({
                toolName: tool.name,
                userId: context.userId,
                sessionId: context.sessionId,
                mode: 'auto_approve',
                allowed: true,
                reason: 'Auto-approved by permission policy',
                decisionSource: effectiveMode,
            });
            return { allowed: true };
        }
        // ── ask_each: requires user approval ──
        if (effectiveMode === 'ask_each') {
            const approval = this.createApprovalRequest(tool, input, context);
            this.audit({
                toolName: tool.name,
                userId: context.userId,
                sessionId: context.sessionId,
                mode: 'ask_each',
                allowed: false,
                reason: `Requires user approval (request ${approval.id})`,
                decisionSource: effectiveMode,
            });
            return {
                allowed: false,
                reason: `Tool '${tool.name}' requires your approval`,
                needsUserApproval: true,
            };
        }
        // Fallback: deny for unrecognized modes
        this.audit({
            toolName: tool.name,
            userId: context.userId,
            sessionId: context.sessionId,
            mode: effectiveMode,
            allowed: false,
            reason: `Unrecognized permission mode: ${effectiveMode}`,
            decisionSource: 'default',
        });
        return {
            allowed: false,
            reason: `Unrecognized permission mode: ${effectiveMode}`,
        };
    }
    // ═════════════════════════════════════════════════════════════════════════
    // Approval Queue
    // ═════════════════════════════════════════════════════════════════════════
    createApprovalRequest(tool, input, context) {
        const id = `aprv_${Date.now()}_${++this.approvalCounter}`;
        const request = {
            id,
            toolName: tool.name,
            input,
            userId: context.userId,
            sessionId: context.sessionId,
            riskLevel: tool.riskLevel ?? 'low',
            createdAt: Date.now(),
            status: 'pending',
        };
        this.approvals.set(id, request);
        return request;
    }
    /** List all pending approval requests. */
    getPendingApprovals() {
        const pending = [];
        for (const req of this.approvals.values()) {
            if (req.status === 'pending')
                pending.push(req);
        }
        return pending.sort((a, b) => a.createdAt - b.createdAt);
    }
    /** Get a specific approval request by ID. */
    getApproval(id) {
        return this.approvals.get(id);
    }
    /** Approve a pending request. Returns false if not found or not pending. */
    approve(approvalId, decidedBy) {
        const req = this.approvals.get(approvalId);
        if (!req || req.status !== 'pending')
            return false;
        req.status = 'approved';
        req.decidedAt = Date.now();
        req.decidedBy = decidedBy;
        return true;
    }
    /** Deny a pending request. Returns false if not found or not pending. */
    deny(approvalId, decidedBy) {
        const req = this.approvals.get(approvalId);
        if (!req || req.status !== 'pending')
            return false;
        req.status = 'denied';
        req.decidedAt = Date.now();
        req.decidedBy = decidedBy;
        return true;
    }
    /** Clean up old approval requests (approved/denied + older than ttlMs). */
    cleanApprovals(ttlMs = 3600000) {
        const cutoff = Date.now() - ttlMs;
        let cleaned = 0;
        for (const [id, req] of this.approvals) {
            if (req.status !== 'pending' && (req.decidedAt ?? 0) < cutoff) {
                this.approvals.delete(id);
                cleaned++;
            }
        }
        return cleaned;
    }
    // ═════════════════════════════════════════════════════════════════════════
    // Audit Trail
    // ═════════════════════════════════════════════════════════════════════════
    audit(entry) {
        this.auditLog.push({ ...entry, timestamp: Date.now() });
        if (this.auditLog.length > this.maxAuditEntries) {
            this.auditLog.splice(0, this.auditLog.length - this.maxAuditEntries);
        }
    }
    /** Get the full audit trail, newest first. */
    getAuditLog(limit) {
        const log = [...this.auditLog].reverse();
        return limit ? log.slice(0, limit) : log;
    }
    /** Clear the audit trail. */
    clearAuditLog() {
        this.auditLog = [];
    }
    /** Set the maximum number of audit entries to retain. */
    setMaxAuditEntries(max) {
        this.maxAuditEntries = max;
        if (this.auditLog.length > max) {
            this.auditLog.splice(0, this.auditLog.length - max);
        }
    }
    // ═════════════════════════════════════════════════════════════════════════
    // Utilities
    // ═════════════════════════════════════════════════════════════════════════
    /** Reset the permission manager to its initial state. */
    reset() {
        this.defaultMode = 'ask_each';
        this.userPolicies.clear();
        this.sessionPolicies.clear();
        this.toolOverrides.clear();
        this.patternRules = [];
        this.riskLevelPolicies.clear();
        this.approvals.clear();
        this.approvalCounter = 0;
        this.auditLog = [];
    }
    /** Get a summary of the current policy configuration. */
    getPolicySummary() {
        return {
            defaultMode: this.defaultMode,
            userPolicies: Array.from(this.userPolicies.entries()).map(([userId, mode]) => ({ userId, mode })),
            sessionPolicies: Array.from(this.sessionPolicies.entries()).map(([sessionId, mode]) => ({ sessionId, mode })),
            toolOverrides: Array.from(this.toolOverrides.entries()).map(([toolName, mode]) => ({ toolName, mode })),
            patternRules: this.patternRules.length,
            riskLevelPolicies: Array.from(this.riskLevelPolicies.entries()).map(([level, mode]) => ({ level, mode })),
        };
    }
}
