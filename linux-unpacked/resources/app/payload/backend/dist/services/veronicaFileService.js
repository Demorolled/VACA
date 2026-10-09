import { AITranslator } from '../ai/translator.js';
import { readFileSync, existsSync, readdirSync, statSync, mkdirSync, writeFileSync, unlinkSync, renameSync } from 'fs';
import { join, resolve, dirname } from 'path';
import { homedir } from 'os';
import { getIO } from '../socket/socketManager.js';
const FORCE_MODIFY_PATTERNS = [
    { ext: '.py', engines: ['python', 'django', 'flask', 'fastapi'] },
    { ext: '.js', engines: ['node', 'react', 'vue'] },
    { ext: '.ts', engines: ['typescript', 'deno'] },
    { ext: '.tsx', engines: ['react', 'typescript'] },
    { ext: '.jsx', engines: ['react'] },
    { ext: '.rs', engines: ['rust'] },
    { ext: '.go', engines: ['golang'] },
    { ext: '.java', engines: ['java', 'spring'] },
];
const EXCLUDE_DIRS = new Set(['node_modules', '.git', '__pycache__', '.venv', 'dist', 'build', '.cache', '.opencode']);
function expandPath(p) {
    if (p.startsWith('~/'))
        return join(homedir(), p.slice(2));
    if (p === '~')
        return homedir();
    return resolve(p);
}
export function scanDirectoryTree(dirPath, maxDepth = 5, currentDepth = 0) {
    if (currentDepth > maxDepth)
        return [];
    const resolved = expandPath(dirPath);
    if (!existsSync(resolved))
        return [];
    try {
        const entries = readdirSync(resolved);
        const results = [];
        for (const name of entries) {
            if (name.startsWith('.'))
                continue;
            const fullPath = join(resolved, name);
            try {
                const stat = statSync(fullPath);
                if (stat.isDirectory()) {
                    if (EXCLUDE_DIRS.has(name))
                        continue;
                    results.push({
                        name,
                        path: fullPath,
                        type: 'directory',
                        children: scanDirectoryTree(fullPath, maxDepth, currentDepth + 1),
                    });
                }
                else if (stat.isFile()) {
                    const sizeMB = stat.size / (1024 * 1024);
                    results.push({
                        name,
                        path: fullPath,
                        type: 'file',
                        size: stat.size,
                    });
                }
            }
            catch {
                continue;
            }
        }
        return results;
    }
    catch {
        return [];
    }
}
export function readDirectoryFiles(entries, maxFiles = 10000) {
    const files = [];
    function walk(list) {
        for (const entry of list) {
            if (files.length >= maxFiles)
                return;
            if (entry.type === 'file' && entry.size && entry.size > 0) {
                const ext = entry.name.split('.').pop()?.toLowerCase() || '';
                const textExts = new Set([
                    'js', 'ts', 'jsx', 'tsx', 'py', 'rs', 'go', 'java', 'c', 'cpp', 'h',
                    'css', 'html', 'json', 'yaml', 'yml', 'toml', 'md', 'txt', 'xml',
                    'sh', 'bash', 'zig', 'swift', 'kt', 'rb', 'php', 'vue', 'svelte',
                    'sql', 'graphql', 'prisma', 'env', 'ini', 'cfg', 'conf',
                ]);
                if (textExts.has(ext) && entry.size && entry.size < 12884901888) {
                    try {
                        const content = readFileSync(entry.path, 'utf-8');
                        files.push({ path: entry.path, content });
                    }
                    catch { }
                }
            }
            if (entry.children)
                walk(entry.children);
        }
    }
    walk(entries);
    return files;
}
const VERONICA_PROCESS_SYSTEM_PROMPT = `You are Veronica, a senior software engineer integrated into the VACA platform. You have FULL read/write access to the user's filesystem.

YOUR CAPABILITIES:
1. READ files — examine any file on the computer
2. WRITE files — create new files or overwrite existing ones
3. EDIT files — find and replace text in files
4. DELETE files — remove files
5. SEARCH files — find text patterns across files
6. LIST directories — see what's in any directory
7. RUN shell commands — execute terminal commands
8. SCAN code — detect bugs, security issues, lint errors
9. REPAIR files — fix issues you find
10. MOVE/RENAME files — reorganize the filesystem
11. BUILD projects — create multi-file applications
12. SPAWN agents — launch sub-agents for background tasks

When given files to process, you should:
1. ANALYZE every file for issues (syntax errors, bugs, security, style, best practices)
2. REPORT what you find with specific file paths and line references
3. FIX issues automatically using write/edit tools
4. SUMMARIZE what was changed

You have these tools available — respond with a JSON tool call:
{"tool": "read", "input": {"path": "~/file.py"}}
{"tool": "write", "input": {"path": "~/file.py", "content": "# code"}}
{"tool": "edit", "input": {"path": "~/file.py", "oldString": "old", "newString": "new"}}
{"tool": "delete", "input": {"path": "~/file.py"}}
{"tool": "shell", "input": {"command": "ls -la"}}
{"tool": "build_project", "input": {"description": "...", "projectName": "...", "nodeCount": 8}}
{"tool": "orchestrate", "input": {"description": "..."}}

IMPORTANT: Actually EXECUTE tools — do not just describe what you would do. Use the write tool to create/modify files, the edit tool to fix issues, the shell tool to scan directories.

When the task involves repairing files, you MUST:
- First read the file to understand its content
- Identify specific issues (syntax, logic, security, style)
- Use edit or write to apply fixes
- Report what you fixed and why`;
export async function processFiles(files, instructions) {
    const translator = new AITranslator();
    const fileContext = files.map(f => {
        const lines = f.content.split('\n');
        const head = lines.slice(0, 100).join('\n');
        const tail = lines.length > 100 ? `\n... (${lines.length - 100} more lines)` : '';
        return `--- ${f.path} ---\n${head}${tail}`;
    }).join('\n\n');
    const userPrompt = `I'm giving you ${files.length} file(s) to process.

Files:
${fileContext}

Instructions: ${instructions || 'Scan these files for issues, fix any problems found, and report what was done.'}

Process each file thoroughly. For each file:
1. Check for bugs, syntax errors, security vulnerabilities, and code quality issues
2. Apply fixes using the write or edit tools
3. Report what you found and what you fixed

After processing all files, provide a clear summary of:
- What files were checked
- What issues were found (with line numbers)
- What fixes were applied
- What (if anything) was skipped and why`;
    const response = await translator.reason(userPrompt, VERONICA_PROCESS_SYSTEM_PROMPT, { maxTokens: 8192 });
    return {
        success: true,
        message: 'Processing complete',
        findings: [],
        repairs: [],
        summary: response,
    };
}
export async function processFilesWithTools(files, instructions) {
    const veronicaTranslator = new AITranslator();
    const systemPrompt = VERONICA_PROCESS_SYSTEM_PROMPT;
    const fileContext = files.map(f => {
        const lines = f.content.split('\n');
        const head = lines.slice(0, 80).join('\n');
        const tail = lines.length > 80 ? `\n... (${lines.length - 80} more lines)` : '';
        return `--- ${f.path} ---\n${head}${tail}`;
    }).join('\n\n');
    const userPrompt = `Process these ${files.length} file(s):

${fileContext}

Instructions: ${instructions || 'Scan for issues and fix them.'}

${files.length > 3 ? 'For efficiency, batch your file operations where possible.' : ''}

You MUST:
1. Read each file to understand its content
2. Check for: syntax errors, bugs, security issues, type errors, undefined variables, missing imports, deprecated APIs
3. Fix ALL issues found using the write or edit tool
4. Report your findings`;
    const JSON_TOOL_REGEX = /\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"input"\s*:\s*(\{.*?\})\s*\}/s;
    const NATIVE_TOOL_REGEX = /<\|tool_call\|?>call:(?:\d+_)?([a-zA-Z_][a-zA-Z0-9_]*)\{([^}]*)\}<\|?tool_call\|>/s;
    function parseToolCall(response) {
        const jsonMatch = response.match(JSON_TOOL_REGEX);
        if (jsonMatch) {
            try {
                return { toolName: jsonMatch[1], toolInput: JSON.parse(jsonMatch[2]), match: jsonMatch[0] };
            }
            catch { }
        }
        const nativeMatch = response.match(NATIVE_TOOL_REGEX);
        if (nativeMatch) {
            const toolName = nativeMatch[1];
            let args = nativeMatch[2].trim().replace(/\\"/g, '"')
                .replace(/([{,]\s*|^)([a-zA-Z_][a-zA-Z0-9_]*)\s*(?=:\s*|":)/g, '$1"$2"');
            if (!args.startsWith('{'))
                args = '{' + args + '}';
            if (!args.endsWith('}'))
                args = args + '}';
            try {
                return { toolName, toolInput: JSON.parse(args), match: nativeMatch[0] };
            }
            catch {
                return null;
            }
        }
        return null;
    }
    function resolveAgentPath(p) {
        if (p.startsWith('~/'))
            return resolve(homedir(), p.slice(2));
        if (p === '~')
            return homedir();
        return resolve(p);
    }
    async function executeTool(parsed) {
        const { tool, input } = parsed;
        try {
            if (tool === 'write') {
                const filePath = resolveAgentPath(input.path || input.file);
                const content = input.content || '';
                mkdirSync(dirname(filePath), { recursive: true });
                writeFileSync(filePath, content, 'utf-8');
                return `File written: ${input.path || input.file}`;
            }
            if (tool === 'edit') {
                const filePath = resolveAgentPath(input.path || input.file);
                let content = readFileSync(filePath, 'utf-8');
                const oldStr = input.oldString || input.find;
                const newStr = input.newString || input.replace;
                if (!oldStr)
                    return 'Error: oldString required';
                if (input.all) {
                    const escaped = oldStr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    content = content.replace(new RegExp(escaped, 'g'), newStr);
                }
                else {
                    const idx = content.indexOf(oldStr);
                    if (idx === -1)
                        return `String not found in ${input.path}`;
                    content = content.slice(0, idx) + newStr + content.slice(idx + oldStr.length);
                }
                writeFileSync(filePath, content, 'utf-8');
                return `File edited: ${input.path || input.file}`;
            }
            if (tool === 'read') {
                const filePath = resolveAgentPath(input.path || input.file);
                const content = readFileSync(filePath, 'utf-8');
                const lines = content.split('\n');
                return `${input.path} (${lines} lines):\n\`\`\`\n${content.slice(0, 4000)}\n\`\`\``;
            }
            if (tool === 'delete') {
                const filePath = resolveAgentPath(input.path || input.file);
                unlinkSync(filePath);
                return `File deleted: ${input.path || input.file}`;
            }
            if (tool === 'shell' || tool === 'execute') {
                const cmd = input.command || input.cmd;
                if (!cmd)
                    return 'Error: command required';
                const { execSync } = await import('child_process');
                const output = execSync(cmd, { encoding: 'utf-8', timeout: (input.timeout || 30000), maxBuffer: 10 * 1024 * 1024 });
                const truncated = output.length > 5000 ? output.slice(0, 5000) + '\n... (truncated)' : output;
                return `Command executed:\n\`\`\`\n${truncated}\n\`\`\``;
            }
            if (tool === 'rename' || tool === 'move') {
                const oldPath = resolveAgentPath(input.oldPath || input.from || input.source);
                const newPath = resolveAgentPath(input.newPath || input.to || input.destination);
                mkdirSync(dirname(newPath), { recursive: true });
                renameSync(oldPath, newPath);
                return `Moved: ${oldPath} → ${newPath}`;
            }
            if (tool === 'list') {
                const dirPath = resolveAgentPath(input.path || input.dir || '.');
                const entries = readdirSync(dirPath);
                return `Contents of ${input.path || '.'}:\n${entries.join('\n')}`;
            }
            if (tool === 'scan' || tool === 'code_scan') {
                const filePath = resolveAgentPath(input.path || input.file);
                const content = readFileSync(filePath, 'utf-8');
                const lines = content.split('\n');
                const issues = [];
                if (content.includes('TODO') || content.includes('FIXME'))
                    issues.push('Contains TODO/FIXME markers');
                if (content.includes('console.log'))
                    issues.push('Contains console.log statements');
                if (content.includes('debugger'))
                    issues.push('Contains debugger statement');
                if (content.includes('eval('))
                    issues.push('Uses eval() — security risk');
                if (content.includes('password') && !content.includes('"password"') && !content.includes("'password'"))
                    issues.push('Hardcoded password detected');
                return `Scan results for ${input.path}:\n${issues.length ? issues.map(i => `  ⚠ ${i}`).join('\n') : '  ✅ No major issues found'}\n${lines.length} lines, ${content.length} characters`;
            }
            if (tool === 'search') {
                const { execSync } = await import('child_process');
                const dirPath = resolveAgentPath(input.path || input.dir || '.');
                const pattern = input.pattern || input.query;
                if (!pattern)
                    return 'Error: pattern required';
                const output = execSync(`grep -rn "${pattern}" "${dirPath}" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" --include="*.py" --include="*.rs" --include="*.go" 2>/dev/null | head -100`, { encoding: 'utf-8', timeout: 15000 });
                return output ? `Search results for "${pattern}":\n${output}` : `No matches found for "${pattern}"`;
            }
            return `Unknown tool: ${tool}`;
        }
        catch (err) {
            return `Tool error: ${err.message}`;
        }
    }
    let finalResponse = '';
    let conversationText = userPrompt;
    const maxIterations = 15;
    const findings = [];
    const repairs = [];
    for (let iteration = 0; iteration < maxIterations; iteration++) {
        const response = await veronicaTranslator.reason(conversationText, systemPrompt, { maxTokens: iteration === 0 ? 4096 : 2048 });
        const parsedCall = parseToolCall(response);
        if (parsedCall) {
            const toolName = parsedCall.toolName;
            const toolInput = parsedCall.toolInput;
            const result = await executeTool({ tool: toolName, input: toolInput });
            if (toolName === 'read' || toolName === 'scan' || toolName === 'code_scan') {
                findings.push({
                    file: toolInput.path || toolInput.file || 'unknown',
                    type: 'info',
                    severity: 'low',
                    message: result.slice(0, 200),
                });
            }
            if (toolName === 'write' || toolName === 'edit' || toolName === 'rename' || toolName === 'move' || toolName === 'delete') {
                repairs.push({
                    file: toolInput.path || toolInput.file || toolInput.oldPath || 'unknown',
                    action: result.startsWith('Error') ? 'error' : 'fixed',
                    issue: `${toolName} operation`,
                    detail: result,
                });
            }
            const cleanResponse = response.replace(parsedCall.match, '').trim();
            conversationText = `${cleanResponse}\n\n[Tool Result: ${toolName}]\n${result}\n\nContinue processing. If there are more files to check or fix, do it now. When done, provide your final summary.`;
            const io = getIO();
            if (io) {
                io.emit('veronica:tool_result', {
                    tool: toolName,
                    result,
                    iteration,
                    timestamp: new Date().toISOString(),
                });
            }
        }
        else {
            finalResponse = response;
            break;
        }
    }
    return {
        success: true,
        message: `Veronica processed ${files.length} file(s) with ${repairs.length} actions`,
        findings,
        repairs,
        summary: finalResponse || 'Processing complete.',
    };
}
export default { scanDirectoryTree, readDirectoryFiles, processFiles, processFilesWithTools };
