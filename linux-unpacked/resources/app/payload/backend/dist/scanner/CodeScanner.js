import * as fs from 'fs';
import * as path from 'path';
export class CodeScanner {
    scanFile(filePath, content) {
        const absPath = path.resolve(filePath);
        const source = content || fs.readFileSync(absPath, 'utf-8');
        const lines = source.split('\n');
        const issues = [];
        const metrics = this.analyzeMetrics(lines, source);
        issues.push(...this.syntaxChecks(lines, filePath));
        issues.push(...this.styleChecks(lines, filePath));
        issues.push(...this.complexityChecks(lines, filePath));
        issues.push(...this.bestPracticeChecks(lines, filePath));
        issues.push(...this.securityPatternChecks(source, filePath));
        const errors = issues.filter(i => i.severity === 'error').length;
        const warnings = issues.filter(i => i.severity === 'warning').length;
        const infos = issues.filter(i => i.severity === 'info').length;
        const result = {
            filePath: absPath,
            issues,
            summary: { errors, warnings, infos },
            metrics,
        };
        return result;
    }
    scanDirectory(dirPath, pattern = /\.(ts|tsx|js|jsx|py|rs|go|java|kt|swift|cpp|c|h)$/) {
        const absPath = path.resolve(dirPath);
        const results = [];
        function walk(dir) {
            const entries = fs.readdirSync(dir, { withFileTypes: true });
            for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
                    walk(fullPath);
                }
                else if (entry.isFile() && pattern.test(entry.name)) {
                    try {
                        const scanner = new CodeScanner();
                        results.push(scanner.scanFile(fullPath));
                    }
                    catch { /* skip unreadable */ }
                }
            }
        }
        walk(absPath);
        return results;
    }
    securityScan(filePath, content) {
        const absPath = path.resolve(filePath);
        const source = content || fs.readFileSync(absPath, 'utf-8');
        const lines = source.split('\n');
        const vulnerabilities = [];
        const patterns = [
            { regex: /eval\s*\(/g, type: 'eval_usage', severity: 'high', description: 'Use of eval() can lead to code injection attacks', remediation: 'Avoid eval(). Use JSON.parse() for JSON, or Function constructor as last resort', cwe: 'CWE-95' },
            { regex: /process\.env\./g, type: 'env_exposure', severity: 'medium', description: 'Environment variables referenced in code may leak secrets', remediation: 'Ensure .env files are in .gitignore. Use a secrets manager for production', cwe: 'CWE-200' },
            { regex: /\.innerHTML\s*=/g, type: 'xss_vulnerability', severity: 'high', description: 'Setting innerHTML can lead to XSS attacks', remediation: 'Use textContent or DOM APIs instead. Sanitize user input', cwe: 'CWE-79' },
            { regex: /(SELECT|INSERT|UPDATE|DELETE).*\+.*['"]/gi, type: 'sql_injection', severity: 'critical', description: 'String concatenation in SQL query - possible SQL injection', remediation: 'Use parameterized queries or prepared statements', cwe: 'CWE-89' },
            { regex: /exec\s*\(/g, type: 'command_injection', severity: 'critical', description: 'Possible command injection via exec()', remediation: 'Use execFile() with arguments array, or validate/sanitize input', cwe: 'CWE-78' },
            { regex: /child_process\./g, type: 'child_process', severity: 'medium', description: 'Child process usage - ensure input is sanitized', remediation: 'Validate all inputs passed to child processes', cwe: 'CWE-78' },
            { regex: /(apiKey|apikey|API_KEY|secret|SECRET|password|PASSWORD|token|TOKEN)\s*[:=]\s*['"][^'"]+['"]/g, type: 'hardcoded_secret', severity: 'critical', description: 'Hardcoded secret/API key detected', remediation: 'Move secrets to environment variables or a secrets manager', cwe: 'CWE-798' },
            { regex: /http:\/\//g, type: 'insecure_http', severity: 'medium', description: 'Insecure HTTP connection detected', remediation: 'Use HTTPS instead of HTTP for all communications', cwe: 'CWE-319' },
            { regex: /new\s+Function\s*\(/g, type: 'dynamic_code', severity: 'high', description: 'Dynamic code execution via Function constructor', remediation: 'Avoid dynamic code generation. Use safer alternatives', cwe: 'CWE-94' },
            { regex: /\.cookie\s*=/g, type: 'cookie_set', severity: 'low', description: 'Setting cookies - ensure Secure and HttpOnly flags are set', remediation: 'Set Secure, HttpOnly, and SameSite flags on all cookies', cwe: 'CWE-614' },
            { regex: /localStorage\./g, type: 'local_storage', severity: 'low', description: 'Sensitive data in localStorage persists and is accessible to JS', remediation: 'Avoid storing sensitive data in localStorage. Use httpOnly cookies for auth', cwe: 'CWE-312' },
            { regex: /Math\.random\s*\(\)/g, type: 'weak_random', severity: 'medium', description: 'Math.random() is not cryptographically secure', remediation: 'Use crypto.randomBytes() or Web Crypto API for security-sensitive randomness', cwe: 'CWE-338' },
            { regex: /debugger\b/g, type: 'debugger_statement', severity: 'low', description: 'Debugger statement left in code', remediation: 'Remove debugger statements before production deployment', cwe: 'CWE-489' },
            { regex: /console\.log\s*\(/g, type: 'console_log', severity: 'low', description: 'Console.log left in production code', remediation: 'Remove or replace with proper logging framework', cwe: '' },
        ];
        for (const pattern of patterns) {
            let match;
            const regex = new RegExp(pattern.regex.source, pattern.regex.flags.includes('g') ? pattern.regex.flags : pattern.regex.flags + 'g');
            while ((match = regex.exec(source)) !== null) {
                const lineNum = source.substring(0, match.index).split('\n').length;
                vulnerabilities.push({
                    type: pattern.type,
                    severity: pattern.severity,
                    line: lineNum,
                    snippet: match[0].substring(0, 100),
                    description: pattern.description,
                    remediation: pattern.remediation,
                    cwe: pattern.cwe,
                });
            }
        }
        const summary = {
            critical: vulnerabilities.filter(v => v.severity === 'critical').length,
            high: vulnerabilities.filter(v => v.severity === 'high').length,
            medium: vulnerabilities.filter(v => v.severity === 'medium').length,
            low: vulnerabilities.filter(v => v.severity === 'low').length,
        };
        return { filePath: absPath, vulnerabilities, summary };
    }
    analyzeMetrics(lines, source) {
        const total = lines.length;
        let code = 0;
        let comments = 0;
        let blanks = 0;
        let complexity = 1;
        let functions = 0;
        const inBlockComment = { value: false };
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed === '') {
                blanks++;
                continue;
            }
            if (inBlockComment.value) {
                comments++;
                if (trimmed.includes('*/'))
                    inBlockComment.value = false;
                continue;
            }
            if (trimmed.startsWith('/*')) {
                comments++;
                if (!trimmed.includes('*/'))
                    inBlockComment.value = true;
                continue;
            }
            if (trimmed.startsWith('//') || trimmed.startsWith('#')) {
                comments++;
                continue;
            }
            code++;
            if (/\b(if|else if|while|for|catch|case)\b/.test(trimmed))
                complexity++;
            if (trimmed.includes('&&') || trimmed.includes('||'))
                complexity++;
            if (/\b(function|def |fun |func |fn )\b/.test(trimmed))
                functions++;
            if (/=>\s*{/.test(trimmed))
                functions++;
            if (/\b(class|struct|trait|interface)\b/.test(trimmed))
                functions++;
        }
        return {
            lines: total,
            codeLines: code,
            commentLines: comments,
            blankLines: blanks,
            complexity,
            functionCount: functions,
        };
    }
    syntaxChecks(lines, _filePath) {
        const issues = [];
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line.trim();
            const unmatchedOpen = (line.match(/\{/g) || []).length;
            const unmatchedClose = (line.match(/\}/g) || []).length;
            if (!trimmed.startsWith('//') && !trimmed.startsWith('*') && unmatchedOpen !== unmatchedClose) {
                const inMultilineComment = lines.slice(0, i).some(l => l.includes('/*')) && !lines.slice(0, i).some(l => l.includes('*/'));
                if (!inMultilineComment) {
                    // Might be multi-line opening/closing, skip
                }
            }
            if (/\(\)\s*=>\s*{/.test(trimmed) && !trimmed.includes('function') && !trimmed.includes('const') && !trimmed.includes('let') && !trimmed.includes('var')) {
                // Arrow function without assignment - likely error
                if (!/^\s*(export\s+)?(default\s+)?\(/.test(trimmed)) {
                    issues.push({
                        line: i + 1, column: trimmed.indexOf('=>') + 1,
                        severity: 'warning',
                        message: 'Arrow function without assignment or declaration',
                        ruleId: 'SYNTAX-ARROW',
                        source: 'CodeScanner',
                        suggestion: 'Assign the arrow function to a const/let/var or use a regular function declaration',
                    });
                }
            }
            if (/\bawait\b/.test(trimmed) && !/async/.test(lines.slice(Math.max(0, i - 5), i + 1).join('\n'))) {
                issues.push({
                    line: i + 1, column: trimmed.indexOf('await') + 1,
                    severity: 'error',
                    message: 'await used outside of async function',
                    ruleId: 'SYNTAX-AWAIT',
                    source: 'CodeScanner',
                    suggestion: 'Wrap in an async function: async function() { ... }',
                });
            }
        }
        return issues;
    }
    styleChecks(lines, _filePath) {
        const issues = [];
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line;
            if (trimmed.trim().length > 120) {
                issues.push({
                    line: i + 1, column: 120,
                    severity: 'warning',
                    message: `Line exceeds 120 characters (${trimmed.length})`,
                    ruleId: 'STYLE-LINE-LENGTH',
                    source: 'CodeScanner',
                    suggestion: 'Break the line into multiple lines for readability',
                });
            }
            if (trimmed !== trimmed.trimEnd()) {
                issues.push({
                    line: i + 1, column: trimmed.trimEnd().length,
                    severity: 'info',
                    message: 'Trailing whitespace detected',
                    ruleId: 'STYLE-TRAILING-WS',
                    source: 'CodeScanner',
                    suggestion: 'Remove trailing whitespace',
                });
            }
            if (/\t/.test(trimmed)) {
                issues.push({
                    line: i + 1, column: trimmed.indexOf('\t') + 1,
                    severity: 'info',
                    message: 'Tab character detected - consider using spaces',
                    ruleId: 'STYLE-TABS',
                    source: 'CodeScanner',
                    suggestion: 'Configure editor to use spaces instead of tabs',
                });
            }
            if (/;\s*$/.test(trimmed.trim()) && !trimmed.trim().startsWith('//')) {
                if (!/for\s*\(|while\s*\(/.test(trimmed)) {
                    // Semicolons in JS/TS are optional - just note it
                }
            }
        }
        // Check for missing trailing newline
        if (lines.length > 0 && lines[lines.length - 1] !== '') {
            issues.push({
                line: lines.length, column: 1,
                severity: 'info',
                message: 'File does not end with a newline',
                ruleId: 'STYLE-NO-NEWLINE-EOF',
                source: 'CodeScanner',
                suggestion: 'Add a trailing newline at the end of the file',
            });
        }
        return issues;
    }
    complexityChecks(lines, _filePath) {
        const issues = [];
        // Find functions and check their complexity
        let currentFunction = '';
        let functionStartLine = 0;
        let depth = 0;
        let branchCount = 0;
        let nestingDepth = 0;
        let maxNesting = 0;
        for (let i = 0; i < lines.length; i++) {
            const trimmed = lines[i].trim();
            const funcMatch = trimmed.match(/(?:function|def |fun |fn )\s*(\w+)?\s*\(/);
            if (funcMatch) {
                if (currentFunction && branchCount > 10) {
                    issues.push({
                        line: functionStartLine, column: 1,
                        severity: 'warning',
                        message: `Function '${currentFunction}' has high cyclomatic complexity (${branchCount})`,
                        ruleId: 'COMPLEXITY-HIGH',
                        source: 'CodeScanner',
                        suggestion: 'Break the function into smaller functions. Consider extracting logic into helper functions.',
                    });
                }
                currentFunction = funcMatch[1] || 'anonymous';
                functionStartLine = i + 1;
                branchCount = 0;
                nestingDepth = 0;
                maxNesting = 0;
            }
            if (/\b(if|else if|while|for|catch|case|&&|\|\|)\b/.test(trimmed)) {
                branchCount++;
            }
            if (trimmed.includes('{'))
                depth++;
            if (trimmed.includes('}'))
                depth--;
            nestingDepth = Math.max(0, depth);
            if (currentFunction && nestingDepth > maxNesting) {
                maxNesting = nestingDepth;
            }
            // Check deep nesting
            if (nestingDepth > 5) {
                issues.push({
                    line: i + 1, column: 1,
                    severity: 'warning',
                    message: `Deep nesting detected (depth ${nestingDepth})`,
                    ruleId: 'COMPLEXITY-NESTING',
                    source: 'CodeScanner',
                    suggestion: 'Extract nested logic into separate functions to improve readability',
                });
                nestingDepth = 0; // Only warn once per function
            }
        }
        // Check final function
        if (currentFunction && branchCount > 10) {
            issues.push({
                line: functionStartLine, column: 1,
                severity: 'warning',
                message: `Function '${currentFunction}' has high cyclomatic complexity (${branchCount})`,
                ruleId: 'COMPLEXITY-HIGH',
                source: 'CodeScanner',
                suggestion: 'Break the function into smaller functions.',
            });
        }
        // Check for long functions (> 100 lines)
        let funcStart = -1;
        for (let i = 0; i < lines.length; i++) {
            const trimmed = lines[i].trim();
            const funcMatch = trimmed.match(/(?:function|def |fun |fn |=>)\s*(\w+)?\s*\(/);
            if (funcMatch && funcStart === -1) {
                funcStart = i;
            }
            if (funcStart >= 0 && (trimmed.startsWith('}') || trimmed.match(/^\s*end\b/))) {
                const funcLen = i - funcStart;
                if (funcLen > 100) {
                    const funcName = funcMatch?.[1] || 'anonymous';
                    issues.push({
                        line: funcStart + 1, column: 1,
                        severity: 'warning',
                        message: `Function '${funcName}' is ${funcLen} lines long`,
                        ruleId: 'COMPLEXITY-LONG-FUNC',
                        source: 'CodeScanner',
                        suggestion: 'Consider breaking this function into smaller, focused functions.',
                    });
                }
                funcStart = -1;
            }
        }
        return issues;
    }
    bestPracticeChecks(lines, _filePath) {
        const issues = [];
        const vars = new Map();
        for (let i = 0; i < lines.length; i++) {
            const trimmed = lines[i].trim();
            if (trimmed.startsWith('//') || trimmed.startsWith('#') || trimmed.startsWith('*'))
                continue;
            const varMatch = trimmed.match(/(?:const|let|var)\s+(\w+)\s*=/);
            if (varMatch) {
                vars.set(varMatch[1], { line: i + 1, used: false });
            }
            for (const [name, info] of vars) {
                if (!info.used && trimmed.includes(name) && !trimmed.match(new RegExp(`(?:const|let|var)\\s+${name}\\s*=`))) {
                    info.used = true;
                }
            }
            if (trimmed.match(/catch\s*\(.*\)\s*\{\s*$/) || trimmed.match(/catch\s*\(.*\)\s*\{/)) {
                const catchContent = trimmed;
                if (catchContent.includes('console.error') || catchContent.includes('console.log')) {
                    // Has error logging - good
                }
                else {
                    // Check next lines if catch opens on this line
                    if (trimmed.endsWith('{')) {
                        let j = i + 1;
                        let catchBody = '';
                        while (j < lines.length && !lines[j].trim().startsWith('}')) {
                            catchBody += lines[j];
                            j++;
                        }
                        if (!catchBody.trim()) {
                            issues.push({
                                line: i + 1, column: 1,
                                severity: 'warning',
                                message: 'Empty catch block - error is silently ignored',
                                ruleId: 'BEST-EMPTY-CATCH',
                                source: 'CodeScanner',
                                suggestion: 'Add error handling or at minimum log the error',
                            });
                        }
                    }
                }
            }
            if (/==\s*(true|false|null|undefined)/.test(trimmed)) {
                issues.push({
                    line: i + 1, column: trimmed.indexOf('==') + 1,
                    severity: 'info',
                    message: 'Unnecessary equality check with boolean/null/undefined',
                    ruleId: 'BEST-UNNECESSARY-CHECK',
                    source: 'CodeScanner',
                    suggestion: 'Use truthy/falsy check: if (value) instead of if (value === true)',
                });
            }
            if (/\bvar\s+/.test(trimmed)) {
                issues.push({
                    line: i + 1, column: trimmed.indexOf('var') + 1,
                    severity: 'warning',
                    message: 'Use of var - prefer const or let for block scoping',
                    ruleId: 'BEST-NO-VAR',
                    source: 'CodeScanner',
                    suggestion: 'Replace var with const (if not reassigned) or let',
                });
            }
        }
        // Report unused variables
        for (const [name, info] of vars) {
            if (!info.used) {
                issues.push({
                    line: info.line, column: 1,
                    severity: 'warning',
                    message: `Unused variable: ${name}`,
                    ruleId: 'BEST-UNUSED-VAR',
                    source: 'CodeScanner',
                    suggestion: `Remove '${name}' if it is not needed`,
                });
            }
        }
        return issues;
    }
    securityPatternChecks(source, _filePath) {
        const issues = [];
        const secPatterns = [
            { regex: /eval\s*\(/g, message: 'Use of eval() poses security risk', severity: 'error', id: 'SEC-EVAL', suggestion: 'Use JSON.parse() or safer alternatives' },
            { regex: /\.innerHTML\s*=/g, message: 'innerHTML assignment can lead to XSS', severity: 'error', id: 'SEC-XSS', suggestion: 'Use textContent or DOMPurify' },
            { regex: /new\s+Function\s*\(/g, message: 'Dynamic function creation is dangerous', severity: 'warning', id: 'SEC-DYNAMIC-FN', suggestion: 'Avoid dynamic code execution' },
            { regex: /process\.env\./g, message: 'Environment variable reference - ensure not leaking secrets', severity: 'info', id: 'SEC-ENV', suggestion: 'Validate .env is in .gitignore' },
            { regex: /(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['"][^'"]+/gi, message: 'Possible hardcoded credential', severity: 'error', id: 'SEC-CRED', suggestion: 'Move to environment variables' },
        ];
        for (const pattern of secPatterns) {
            let match;
            while ((match = pattern.regex.exec(source)) !== null) {
                const lineNum = source.substring(0, match.index).split('\n').length;
                issues.push({
                    line: lineNum,
                    column: source.substring(0, match.index).split('\n').pop().length + 1,
                    severity: pattern.severity,
                    message: pattern.message,
                    ruleId: pattern.id,
                    source: 'CodeScanner',
                    suggestion: pattern.suggestion,
                });
            }
        }
        return issues;
    }
    debugInjectLogs(filePath, expression) {
        const absPath = path.resolve(filePath);
        let source = fs.readFileSync(absPath, 'utf-8');
        const lines = source.split('\n');
        const injected = [];
        for (let i = 0; i < lines.length; i++) {
            const trimmed = lines[i].trim();
            if (expression && !trimmed.includes(expression))
                continue;
            // Inject after assignments and function calls
            if (trimmed.match(/^\s*(const|let|var)\s+\w+\s*=/) || trimmed.match(/^\s*\w+\s*=\s*.+[^;]$/) || trimmed.match(/\.\w+\s*\(.*\)\s*$/)) {
                const indent = lines[i].match(/^\s*/)?.[0] || '';
                const varName = trimmed.match(/(?:const|let|var)\s+(\w+)/)?.[1];
                if (varName && expression === undefined) {
                    const logLine = `${indent}console.log('[debug] ${varName} =', ${varName});`;
                    injected.push(logLine);
                    lines.splice(i + 1, 0, logLine);
                    i++;
                }
                else if (expression || trimmed.includes('return')) {
                    const logLine = `${indent}console.log('[debug] line ${i + 1}:', ${JSON.stringify(trimmed.substring(0, 50))});`;
                    injected.push(logLine);
                    lines.splice(i + 1, 0, logLine);
                    i++;
                }
            }
            // Add log before return statements
            if (trimmed.startsWith('return ') && !trimmed.includes('console.log')) {
                const indent = lines[i].match(/^\s*/)?.[0] || '';
                const returnValue = trimmed.substring(7);
                const logLine = `${indent}console.log('[debug] return:', ${returnValue});`;
                injected.push(logLine);
                lines.splice(i, 0, logLine);
                i++;
            }
        }
        const newSource = lines.join('\n');
        fs.writeFileSync(absPath, newSource, 'utf-8');
        return newSource;
    }
    debugRemoveLogs(filePath) {
        const absPath = path.resolve(filePath);
        let source = fs.readFileSync(absPath, 'utf-8');
        const lines = source.split('\n');
        let removed = 0;
        const filtered = lines.filter(line => {
            const trimmed = line.trim();
            if (trimmed.includes("console.log('[debug]") || trimmed.includes("// DEBUG_INJECTED")) {
                removed++;
                return false;
            }
            return true;
        });
        const newSource = filtered.join('\n');
        fs.writeFileSync(absPath, newSource, 'utf-8');
        return { removed, source: newSource };
    }
    analyzeComplexity(source) {
        const lines = source.split('\n');
        const details = [];
        let score = 0;
        const lineCount = lines.length;
        if (lineCount > 1000) {
            score += 20;
            details.push(`Large file: ${lineCount} lines (+20)`);
        }
        else if (lineCount > 500) {
            score += 10;
            details.push(`Moderate file: ${lineCount} lines (+10)`);
        }
        let branches = 0;
        for (const line of lines) {
            if (/\b(if|else if|while|for|catch|case)\b/.test(line))
                branches++;
        }
        if (branches > 20) {
            score += 20;
            details.push(`High branch count: ${branches} (+20)`);
        }
        else if (branches > 10) {
            score += 10;
            details.push(`Moderate branch count: ${branches} (+10)`);
        }
        let depth = 0;
        let maxDepth = 0;
        for (const line of lines) {
            if (line.includes('{'))
                depth++;
            if (line.includes('}'))
                depth--;
            maxDepth = Math.max(maxDepth, depth);
        }
        if (maxDepth > 6) {
            score += 20;
            details.push(`Deep nesting: depth ${maxDepth} (+20)`);
        }
        else if (maxDepth > 4) {
            score += 10;
            details.push(`Moderate nesting: depth ${maxDepth} (+10)`);
        }
        let funcCount = 0;
        for (const line of lines) {
            if (/\b(function|def |fun |fn )\b/.test(line))
                funcCount++;
        }
        if (funcCount > 15) {
            score += 10;
            details.push(`Many functions: ${funcCount} (+10)`);
        }
        const label = score >= 50 ? 'Very Complex' : score >= 30 ? 'Complex' : score >= 15 ? 'Moderate' : 'Simple';
        return { score, label, details };
    }
}
export const codeScanner = new CodeScanner();
