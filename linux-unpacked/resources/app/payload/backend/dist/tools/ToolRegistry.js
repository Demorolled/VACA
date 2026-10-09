/**
 * Veronica Tool Registry — central hub for registering, finding,
 * and executing tools with lifecycle management.
 */
import { PermissionManager } from './permissions/PermissionManager.js';
import { v4 as uuid } from 'uuid';
const DEFAULT_CONFIG = {
    defaultPermissionMode: 'allow_all',
    emitEvents: true,
    maxConcurrentExecutions: 50,
    defaultTimeoutMs: 120000,
};
// ─── Registry ───────────────────────────────────────────────────────────────
export class ToolRegistry {
    tools = new Map();
    executions = new Map();
    activeExecutionCount = 0;
    config;
    eventHandlers = new Set();
    permissionManager = new PermissionManager();
    constructor(config) {
        this.config = { ...DEFAULT_CONFIG, ...config };
        if (config?.defaultPermissionMode) {
            this.permissionManager.setDefaultMode(config.defaultPermissionMode);
        }
    }
    // ── Registration ──────────────────────────────────────────────────────────
    /** Register a single tool. Returns false if a tool with the same name exists or is malformed. */
    register(tool) {
        if (!tool.name || !tool.description || !tool.inputSchema || typeof tool.call !== 'function') {
            return false;
        }
        if (this.tools.has(tool.name)) {
            return false;
        }
        this.tools.set(tool.name, tool);
        this.emit({ type: 'tool:registered', toolName: tool.name, timestamp: Date.now() });
        return true;
    }
    /** Register multiple tools at once. Returns count of successfully registered. */
    registerAll(...tools) {
        let count = 0;
        for (const tool of tools) {
            if (this.register(tool))
                count++;
        }
        return count;
    }
    /** Unregister a tool by name. */
    unregister(name) {
        const existed = this.tools.delete(name);
        if (existed) {
            this.emit({ type: 'tool:unregistered', toolName: name, timestamp: Date.now() });
        }
        return existed;
    }
    // ── Lookup ────────────────────────────────────────────────────────────────
    /** Get a tool by name. */
    get(name) {
        return this.tools.get(name);
    }
    /** Check if a tool is registered. */
    has(name) {
        return this.tools.has(name);
    }
    /** Get all registered tool names. */
    get names() {
        return Array.from(this.tools.keys());
    }
    /** Get all registered tools (optionally filtered). */
    all(query) {
        let results = Array.from(this.tools.values());
        if (query) {
            if (query.name) {
                results = results.filter(t => t.name === query.name);
            }
            if (query.category) {
                results = results.filter(t => t.category === query.category);
            }
            if (query.riskLevel) {
                results = results.filter(t => t.riskLevel === query.riskLevel);
            }
            if (query.enabled !== undefined) {
                results = results.filter(t => t.enabled !== false);
            }
            if (query.search) {
                const q = query.search.toLowerCase();
                results = results.filter(t => t.name.toLowerCase().includes(q) ||
                    t.description.toLowerCase().includes(q));
            }
        }
        return results;
    }
    /** Get tools grouped by category. */
    get grouped() {
        const groups = {};
        for (const tool of this.tools.values()) {
            if (!groups[tool.category])
                groups[tool.category] = [];
            groups[tool.category].push(tool);
        }
        return groups;
    }
    /** Total number of registered tools. */
    get size() {
        return this.tools.size;
    }
    // ── Execution ─────────────────────────────────────────────────────────────
    /** Execute a tool by name with the given input and context. */
    async execute(name, input, context) {
        const tool = this.tools.get(name);
        if (!tool) {
            return {
                success: false,
                error: `Tool not found: ${name}`,
                errorCode: 'TOOL_NOT_FOUND',
            };
        }
        if (tool.enabled === false) {
            return {
                success: false,
                error: `Tool is disabled: ${name}`,
                errorCode: 'TOOL_DISABLED',
            };
        }
        if (this.activeExecutionCount >= this.config.maxConcurrentExecutions) {
            return {
                success: false,
                error: 'Max concurrent tool executions reached',
                errorCode: 'EXECUTION_LIMIT',
            };
        }
        const executionId = uuid();
        const startedAt = Date.now();
        const execution = {
            id: executionId,
            toolName: name,
            input,
            status: 'pending',
            startedAt,
        };
        this.executions.set(executionId, execution);
        this.activeExecutionCount++;
        this.emit({ type: 'tool:before_execute', toolName: name, timestamp: startedAt, executionId });
        const timeoutMs = (tool.timeoutMs ?? this.config.defaultTimeoutMs) || undefined;
        const timeoutSignal = timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined;
        const rawSignals = [context.signal, timeoutSignal].filter(Boolean);
        const combinedSignal = rawSignals.length > 0 ? anySignal(rawSignals) : undefined;
        const effectiveMode = this.permissionManager.getEffectivePermission(name, tool, context);
        // ── Permission check via PermissionManager ──
        const permissionCheck = await this.permissionManager.check(tool, input, context);
        if (!permissionCheck.allowed) {
            const result = {
                success: false,
                error: permissionCheck.reason ?? 'Permission denied',
                errorCode: 'PERMISSION_DENIED',
            };
            execution.status = 'failed';
            execution.completedAt = Date.now();
            execution.result = result;
            execution.error = permissionCheck.reason;
            this.activeExecutionCount--;
            this.emit({
                type: 'tool:error',
                toolName: name,
                timestamp: Date.now(),
                executionId,
                error: permissionCheck.reason,
            });
            return result;
        }
        const toolContext = {
            ...context,
            permissionMode: effectiveMode,
            ...(combinedSignal ? { signal: combinedSignal } : {}),
        };
        try {
            // ── Execute ──
            execution.status = 'running';
            const result = await tool.call(input, toolContext);
            // ── Completion ──
            const completedAt = Date.now();
            result.durationMs = completedAt - startedAt;
            execution.status = result.success ? 'completed' : 'failed';
            execution.completedAt = completedAt;
            execution.result = result;
            if (!result.success && result.error) {
                execution.error = result.error;
            }
            this.activeExecutionCount--;
            // ── Post-execution hook ──
            if (tool.onAfterCall) {
                await tool.onAfterCall(input, result, toolContext).catch(() => { });
            }
            this.emit({
                type: result.success ? 'tool:after_execute' : 'tool:error',
                toolName: name,
                timestamp: completedAt,
                executionId,
                error: result.error,
                durationMs: result.durationMs,
            });
            return result;
        }
        catch (err) {
            const completedAt = Date.now();
            execution.status = 'failed';
            execution.completedAt = completedAt;
            execution.error = err instanceof Error ? err.message : String(err);
            this.activeExecutionCount--;
            this.emit({
                type: 'tool:error',
                toolName: name,
                timestamp: completedAt,
                executionId,
                error: execution.error,
                durationMs: completedAt - startedAt,
            });
            return {
                success: false,
                error: execution.error,
                errorCode: 'EXECUTION_ERROR',
            };
        }
    }
    /** Interrupt a running tool execution. */
    async interrupt(executionId) {
        const execution = this.executions.get(executionId);
        if (!execution || execution.status !== 'running')
            return false;
        const tool = this.tools.get(execution.toolName);
        // Respect opt-out
        if (tool?.interruptBehavior === 'none')
            return false;
        execution.status = 'interrupted';
        execution.completedAt = Date.now();
        if (tool?.onInterrupt) {
            await tool.onInterrupt(execution.input, {}).catch(() => { });
        }
        this.emit({
            type: 'tool:interrupted',
            toolName: execution.toolName,
            timestamp: Date.now(),
            executionId,
        });
        return true;
    }
    // ── Execution History ─────────────────────────────────────────────────────
    /** Get execution history for a tool, optionally filtered by status. */
    getHistory(toolName) {
        let results = Array.from(this.executions.values());
        if (toolName) {
            results = results.filter(e => e.toolName === toolName);
        }
        return results.sort((a, b) => b.startedAt - a.startedAt);
    }
    /** Get a specific execution by ID. */
    getExecution(id) {
        return this.executions.get(id);
    }
    /** Clear execution history older than the given timestamp. */
    clearHistory(before = Date.now()) {
        let cleared = 0;
        for (const [id, exec] of this.executions) {
            if (exec.startedAt < before) {
                this.executions.delete(id);
                cleared++;
            }
        }
        return cleared;
    }
    // ── Permission Overrides (delegated to PermissionManager) ─────────────────
    /** Override the permission mode for a specific tool. */
    setPermissionOverride(toolName, mode) {
        this.permissionManager.setToolOverride(toolName, mode);
    }
    /** Remove a permission override. */
    clearPermissionOverride(toolName) {
        this.permissionManager.clearToolOverride(toolName);
    }
    /** Get the effective permission mode for a tool (with optional context). */
    getEffectivePermission(toolName, context) {
        const tool = this.tools.get(toolName);
        return this.permissionManager.getEffectivePermission(toolName, tool, context);
    }
    // ── Events ────────────────────────────────────────────────────────────────
    /** Subscribe to registry events. */
    on(handler) {
        this.eventHandlers.add(handler);
        return () => this.eventHandlers.delete(handler);
    }
    /** Subscribe to a specific event type. */
    onEvent(type, handler) {
        const wrapped = (event) => {
            if (event.type === type)
                handler(event);
        };
        this.eventHandlers.add(wrapped);
        return () => this.eventHandlers.delete(wrapped);
    }
    emit(event) {
        if (!this.config.emitEvents)
            return;
        for (const handler of this.eventHandlers) {
            try {
                handler(event);
            }
            catch { /* handler errors are silent */ }
        }
    }
    // ── Utilities ─────────────────────────────────────────────────────────────
    /** Generate an AI-friendly tool manifest for LLM function calling. */
    toToolManifest() {
        return this.all({ enabled: true }).map(tool => ({
            name: tool.name,
            description: tool.description,
            input_schema: tool.inputSchema,
        }));
    }
    /** Reset the registry to its initial state. */
    reset() {
        this.tools.clear();
        this.executions.clear();
        this.permissionManager.reset();
        this.activeExecutionCount = 0;
    }
}
// ─── Signal Helper ─────────────────────────────────────────────────────────
function anySignal(signals) {
    const controller = new AbortController();
    for (const signal of signals) {
        if (signal.aborted) {
            controller.abort(signal.reason);
            return controller.signal;
        }
        signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true });
    }
    return controller.signal;
}
// ─── Singleton ──────────────────────────────────────────────────────────────
let defaultRegistry = null;
/** Get or create the global default registry instance. */
export function getRegistry(config) {
    if (!defaultRegistry) {
        defaultRegistry = new ToolRegistry(config);
    }
    return defaultRegistry;
}
/** Reset the global registry (useful for testing). */
export function resetRegistry() {
    defaultRegistry = null;
}
