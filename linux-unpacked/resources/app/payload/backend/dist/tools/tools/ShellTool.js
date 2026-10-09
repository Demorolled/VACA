import { execSync, spawn } from 'child_process';
import { access } from 'fs/promises';
import { resolve } from 'path';
function truncateOutput(text, max) {
    if (text.length <= max)
        return { value: text, truncated: false };
    return { value: text.slice(0, max) + `\n... (truncated ${text.length - max} more chars)`, truncated: true };
}
function isExecError(err) {
    return err instanceof Error && 'status' in err;
}
const shellToolDef = {
    name: 'shell',
    description: 'Execute a shell command and return its output',
    category: 'execution',
    riskLevel: 'critical',
    inputSchema: {
        type: 'object',
        properties: {
            command: { type: 'string', description: 'Shell command to execute' },
            cwd: { type: 'string', description: 'Working directory', required: false },
            timeout: { type: 'number', description: 'Timeout in ms', default: 30000 },
            maxOutput: { type: 'number', description: 'Max output chars', default: 100000 },
            env: { type: 'object', description: 'Environment variables', required: false },
            background: { type: 'boolean', description: 'Run in background', default: false },
        },
        required: ['command'],
    },
    interruptBehavior: 'graceful',
    timeoutMs: 60000,
    async call(input, _context) {
        const startTime = Date.now();
        try {
            const workDir = input.cwd ? resolve(input.cwd) : process.cwd();
            await access(workDir);
            const timeout = input.timeout ?? 60000;
            const maxOutput = input.maxOutput ?? 100000;
            if (input.background) {
                return runBackground(input.command, workDir, input.env);
            }
            return runForeground(input, workDir, timeout, maxOutput, startTime);
        }
        catch (err) {
            const elapsed = Date.now() - startTime;
            if (isExecError(err)) {
                return handleExecError(err, input, elapsed, input.maxOutput ?? 100000);
            }
            const isTimeout = err instanceof Error && (err.message.includes('timed out') || err.message.includes('ETIMEDOUT'));
            const msg = err instanceof Error ? err.message : String(err);
            return {
                success: false,
                error: isTimeout ? 'Command timed out' : msg,
                errorCode: isTimeout ? 'TIMEOUT' : 'EXECUTION_ERROR',
                data: { command: input.command, stdout: '', stderr: msg, exitCode: -1, cwd: '', timedOut: isTimeout, truncated: false },
                durationMs: elapsed,
            };
        }
    },
    async onInterrupt(_input, _context) {
    },
};
function runBackground(command, cwd, env) {
    const opts = {
        cwd,
        shell: true,
        stdio: 'ignore',
        detached: true,
        env: { ...process.env, ...(env || {}) },
    };
    const child = spawn(command, [], opts);
    child.unref();
    return {
        success: true,
        data: { command, stdout: `Background process started (PID: ${child.pid})`, stderr: '', exitCode: null, cwd, timedOut: false, truncated: false },
    };
}
function runForeground(input, cwd, timeout, maxOutput, startTime) {
    const opts = {
        cwd,
        encoding: 'utf-8',
        timeout,
        maxBuffer: 10 * 1024 * 1024,
        env: { ...process.env, ...(input.env || {}) },
        windowsHide: true,
    };
    const output = execSync(input.command, opts);
    const elapsed = Date.now() - startTime;
    const { value: stdout, truncated } = truncateOutput((output || '').toString(), maxOutput);
    return {
        success: true,
        data: { command: input.command, stdout, stderr: '', exitCode: 0, cwd, timedOut: false, truncated },
        durationMs: elapsed,
    };
}
function handleExecError(err, input, elapsed, maxOutput) {
    const stderr = (err.stderr || '');
    const stdout = (err.stdout || '');
    const { value: truncatedStderr } = truncateOutput(stderr, maxOutput);
    const isTimeout = err.message.includes('timed out') || err.message.includes('ETIMEDOUT');
    return {
        success: err.status === 0,
        data: {
            command: input.command,
            stdout: stdout.toString(),
            stderr: truncatedStderr,
            exitCode: err.status ?? -1,
            cwd: input.cwd || '',
            timedOut: isTimeout,
            truncated: stderr.length > maxOutput,
        },
        durationMs: elapsed,
        error: isTimeout ? 'Command timed out' : `Exit code ${err.status}`,
        errorCode: isTimeout ? 'TIMEOUT' : 'NONZERO_EXIT',
    };
}
export const shellTools = [shellToolDef];
