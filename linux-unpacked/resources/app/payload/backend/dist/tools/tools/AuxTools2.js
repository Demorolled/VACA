/**
 * AuxTools2 — Batch 2 of additional mini agents and tools.
 *
 * Data Processing (6): yaml_convert, base64_codec, text_transform, regex_test, text_diff, json_format
 * Utility (4):         time_convert, cron_explain, password_gen, color_convert
 * Development (4):     port_check, npm_info, code_metrics, file_ops
 * System (4):          disk_usage, env_list, process_ps, jwt_decode
 * Mini Agents (4):     bug_hunter_mini, api_design_mini, commit_msg_mini, readme_gen_mini
 */
import { execSync } from 'child_process';
import { randomBytes } from 'crypto';
import { existsSync, renameSync, copyFileSync, statSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { createServer } from 'net';
import * as yaml from 'js-yaml';
// ─── Lazy imports ───────────────────────────────────────────────────────────
async function getTranslator() {
    const mod = await import('../../ai/translator.js');
    return mod;
}
// ─── LLM Fallback Helper ────────────────────────────────────────────────────
function isLLMConnectionError(err) {
    const msg = (err instanceof Error ? err.message : String(err)).toLowerCase();
    return /econnrefused|fetch failed|connection error|connect econnrefused|ollama|translator.*error|reasoning.*failed/i.test(msg);
}
function llmFallbackResponse(toolName, hint, primaryField) {
    const data = {
        _fallback: true,
        _notice: `LLM not available — ${toolName} requires a running Ollama server (ollama serve). Showing guidance instead.`,
        guidance: hint,
    };
    if (primaryField) {
        data[primaryField] = hint;
    }
    return { success: true, data };
}
const yamlConvertDef = {
    name: 'yaml_convert',
    description: 'Convert between YAML and JSON formats (supports yaml2json and json2yaml)',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            input: { type: 'string', description: 'Input YAML or JSON text' },
            direction: { type: 'string', description: 'Conversion direction', enum: ['yaml2json', 'json2yaml'], default: 'yaml2json' },
        },
        required: ['input', 'direction'],
    },
    timeoutMs: 10000,
    async call(input, _ctx) {
        try {
            if (input.direction === 'yaml2json') {
                const parsed = yaml.load(input.input);
                const output = JSON.stringify(parsed, null, 2);
                return { success: true, data: { output, format: 'json' } };
            }
            else {
                const parsed = JSON.parse(input.input);
                const output = yaml.dump(parsed, { indent: 2, lineWidth: 120, noRefs: true });
                return { success: true, data: { output, format: 'yaml' } };
            }
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'YAML_CONVERT_ERROR' };
        }
    },
};
const base64CodecDef = {
    name: 'base64_codec',
    description: 'Encode text to base64 or decode base64 back to text',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            text: { type: 'string', description: 'Text (for encode) or base64 string (for decode)' },
            action: { type: 'string', description: 'Action', enum: ['encode', 'decode'], default: 'encode' },
        },
        required: ['text', 'action'],
    },
    async call(input, _ctx) {
        try {
            if (input.action === 'encode') {
                const result = Buffer.from(input.text, 'utf-8').toString('base64');
                return { success: true, data: { result, length: result.length } };
            }
            else {
                const result = Buffer.from(input.text, 'base64').toString('utf-8');
                return { success: true, data: { result, length: result.length } };
            }
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'BASE64_ERROR' };
        }
    },
};
const textTransformDef = {
    name: 'text_transform',
    description: 'Transform text between different naming conventions (camelCase, snake_case, kebab-case, PascalCase, etc.)',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            text: { type: 'string', description: 'Text to transform' },
            to: { type: 'string', description: 'Target case format', enum: ['camelCase', 'snake_case', 'kebab-case', 'PascalCase', 'SCREAMING_SNAKE_CASE', 'lowercase', 'UPPERCASE', 'Title Case', 'dot.case'], default: 'camelCase' },
        },
        required: ['text', 'to'],
    },
    async call(input, _ctx) {
        try {
            // Split input into words: handle camelCase, snake_case, kebab-case, spaces, etc.
            const words = input.text
                .replace(/([A-Z])/g, ' $1') // Insert space before capitals
                .replace(/[-_.]/g, ' ') // Replace separators with space
                .toLowerCase()
                .split(/\s+/)
                .filter(Boolean);
            if (words.length === 0) {
                return { success: true, data: { original: input.text, result: '', transform: input.to } };
            }
            let result;
            switch (input.to) {
                case 'camelCase':
                    result = words[0] + words.slice(1).map(w => w[0].toUpperCase() + w.slice(1)).join('');
                    break;
                case 'snake_case':
                    result = words.join('_');
                    break;
                case 'kebab-case':
                    result = words.join('-');
                    break;
                case 'PascalCase':
                    result = words.map(w => w[0].toUpperCase() + w.slice(1)).join('');
                    break;
                case 'SCREAMING_SNAKE_CASE':
                    result = words.map(w => w.toUpperCase()).join('_');
                    break;
                case 'lowercase':
                    result = words.join(' ');
                    break;
                case 'UPPERCASE':
                    result = words.map(w => w.toUpperCase()).join(' ');
                    break;
                case 'Title Case':
                    result = words.map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
                    break;
                case 'dot.case':
                    result = words.join('.');
                    break;
                default:
                    result = words.join('_');
            }
            return { success: true, data: { original: input.text, result, transform: input.to } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'TEXT_TRANSFORM_ERROR' };
        }
    },
};
const regexTestDef = {
    name: 'regex_test',
    description: 'Test a regex pattern against text and return all matches with positions',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            pattern: { type: 'string', description: 'Regular expression pattern (without delimiters)' },
            text: { type: 'string', description: 'Text to search in' },
            flags: { type: 'string', description: 'Regex flags (e.g., "gi", "g", "i")', default: 'g', required: false },
        },
        required: ['pattern', 'text'],
    },
    async call(input, _ctx) {
        try {
            const flags = input.flags || 'g';
            let regex;
            try {
                regex = new RegExp(input.pattern, flags);
            }
            catch (e) {
                return { success: true, data: { matches: [], count: 0, valid: false, error: `Invalid regex: ${e instanceof Error ? e.message : String(e)}` } };
            }
            const matches = [];
            let m;
            while ((m = regex.exec(input.text)) !== null) {
                matches.push({ match: m[0], index: m.index, length: m[0].length });
                if (m.index === regex.lastIndex)
                    regex.lastIndex++;
                if (matches.length >= 1000)
                    break; // Safety limit
            }
            return { success: true, data: { matches, count: matches.length, valid: true } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'REGEX_ERROR' };
        }
    },
};
const textDiffDef = {
    name: 'text_diff',
    description: 'Compare two texts and show line-by-line differences (additions/removals)',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            textA: { type: 'string', description: 'Original text' },
            textB: { type: 'string', description: 'New text to compare against' },
            context: { type: 'number', description: 'Context lines around changes', default: 2 },
        },
        required: ['textA', 'textB'],
    },
    async call(input, _ctx) {
        try {
            const linesA = input.textA.split('\n');
            const linesB = input.textB.split('\n');
            const context = input.context ?? 2;
            // Simple LCS-based diff (Myers-like simplified)
            const maxLen = linesA.length + linesB.length;
            const dp = Array.from({ length: linesA.length + 1 }, () => Array(linesB.length + 1).fill(0));
            for (let i = 1; i <= linesA.length; i++) {
                for (let j = 1; j <= linesB.length; j++) {
                    if (linesA[i - 1] === linesB[j - 1])
                        dp[i][j] = dp[i - 1][j - 1] + 1;
                    else
                        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
                }
            }
            // Backtrack to find diff
            const hunks = [];
            let i = linesA.length, j = linesB.length;
            const ops = [];
            while (i > 0 || j > 0) {
                if (i > 0 && j > 0 && linesA[i - 1] === linesB[j - 1]) {
                    ops.push({ type: 'equal', line: linesA[i - 1] });
                    i--;
                    j--;
                }
                else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                    ops.push({ type: 'add', line: linesB[j - 1] });
                    j--;
                }
                else if (i > 0) {
                    ops.push({ type: 'remove', line: linesA[i - 1] });
                    i--;
                }
            }
            ops.reverse();
            // Build hunks with context
            let additions = 0, removals = 0;
            let currentHunk = null;
            let contextCounter = 0;
            for (let idx = 0; idx < ops.length; idx++) {
                const op = ops[idx];
                if (op.type === 'equal') {
                    if (currentHunk && currentHunk.type === 'equal') {
                        currentHunk.lines.push(op.line);
                        contextCounter++;
                    }
                    else if (currentHunk) {
                        // Check if we need context lines after a change
                        if (contextCounter < context) {
                            if (!currentHunk) {
                                currentHunk = { type: 'equal', lines: [op.line] };
                                hunks.push(currentHunk);
                            }
                            else {
                                currentHunk.lines.push(op.line);
                            }
                            contextCounter++;
                        }
                        else {
                            currentHunk = null;
                            contextCounter = 0;
                        }
                    }
                }
                else {
                    if (!currentHunk || currentHunk.type === 'equal') {
                        currentHunk = { type: op.type, lines: [op.line] };
                        hunks.push(currentHunk);
                    }
                    else if (currentHunk.type === op.type) {
                        currentHunk.lines.push(op.line);
                    }
                    else {
                        currentHunk = { type: op.type, lines: [op.line] };
                        hunks.push(currentHunk);
                    }
                    contextCounter = 0;
                    if (op.type === 'add')
                        additions++;
                    if (op.type === 'remove')
                        removals++;
                }
            }
            return { success: true, data: { hunks, additions, removals } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'DIFF_ERROR' };
        }
    },
};
const jsonFormatDef = {
    name: 'json_format',
    description: 'Pretty-print or minify JSON strings',
    category: 'data',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            json: { type: 'string', description: 'JSON string to format' },
            action: { type: 'string', description: 'Format action', enum: ['pretty', 'minify'], default: 'pretty' },
        },
        required: ['json'],
    },
    async call(input, _ctx) {
        try {
            const parsed = JSON.parse(input.json);
            const originalLength = input.json.length;
            const result = input.action === 'minify'
                ? JSON.stringify(parsed)
                : JSON.stringify(parsed, null, 2);
            return { success: true, data: { result, originalLength, resultLength: result.length } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'JSON_FORMAT_ERROR' };
        }
    },
};
const timeConvertDef = {
    name: 'time_convert',
    description: 'Convert a timestamp between timezones using IANA timezone names (e.g., "America/New_York", "UTC", "Asia/Tokyo")',
    category: 'utility',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            timestamp: { type: 'string', description: 'Date/time string (ISO 8601 preferred, e.g., "2024-01-15T14:30:00")' },
            fromTimezone: { type: 'string', description: 'Source IANA timezone (e.g., "America/New_York")' },
            toTimezone: { type: 'string', description: 'Target IANA timezone (e.g., "Europe/London")' },
            format: { type: 'string', description: 'Output format (e.g., "iso", "locale", "full")', default: 'iso', required: false },
        },
        required: ['timestamp', 'fromTimezone', 'toTimezone'],
    },
    async call(input, _ctx) {
        try {
            const date = new Date(input.timestamp);
            if (isNaN(date.getTime())) {
                return { success: false, error: `Invalid timestamp: "${input.timestamp}"`, errorCode: 'INVALID_DATE' };
            }
            const originalStr = date.toLocaleString('en-US', { timeZone: input.fromTimezone, timeZoneName: 'short' });
            const convertedStr = date.toLocaleString('en-US', { timeZone: input.toTimezone, timeZoneName: 'short' });
            // Also provide ISO with timezone offset
            const getOffset = (tz) => {
                const now = new Date();
                const utcDate = new Date(now.toLocaleString('en-US', { timeZone: 'UTC' }));
                const tzDate = new Date(now.toLocaleString('en-US', { timeZone: tz }));
                const diffMs = tzDate.getTime() - utcDate.getTime();
                const sign = diffMs >= 0 ? '+' : '-';
                const hours = Math.floor(Math.abs(diffMs) / 3600000);
                const mins = Math.floor((Math.abs(diffMs) % 3600000) / 60000);
                return `${sign}${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
            };
            return {
                success: true,
                data: {
                    original: `${date.toISOString()} (${input.fromTimezone}, UTC${getOffset(input.fromTimezone)})`,
                    converted: `${convertedStr} (${input.toTimezone}, UTC${getOffset(input.toTimezone)})`,
                    from: input.fromTimezone,
                    to: input.toTimezone,
                },
            };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'TIME_CONVERT_ERROR' };
        }
    },
};
const cronExplainDef = {
    name: 'cron_explain',
    description: 'Parse a 5-field cron expression and explain it in plain English with next upcoming run times',
    category: 'utility',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            expression: { type: 'string', description: '5-field cron expression (e.g., "*/15 * * * *" or "0 9 * * 1-5")' },
        },
        required: ['expression'],
    },
    async call(input, _ctx) {
        try {
            const parts = input.expression.trim().split(/\s+/);
            if (parts.length !== 5) {
                return { success: false, error: 'Cron expression must have exactly 5 fields (minute, hour, day-of-month, month, day-of-week)', errorCode: 'INVALID_CRON' };
            }
            const fieldNames = ['minute', 'hour', 'day of month', 'month', 'day of week'];
            const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
            const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
            const describeField = (value, fieldName) => {
                if (value === '*')
                    return `every ${fieldName}`;
                if (value.includes('/')) {
                    const [base, step] = value.split('/');
                    return `every ${step} ${fieldName}(s)` + (base !== '*' ? ` (starting at ${base})` : '');
                }
                if (value.includes(',')) {
                    const items = value.split(',').map(parseCronValue).join(', ');
                    return `${fieldName}s: ${items}`;
                }
                if (value.includes('-')) {
                    const [start, end] = value.split('-');
                    if (fieldName === 'day of week') {
                        return `${dayNames[parseInt(start)]} through ${dayNames[parseInt(end)]}`;
                    }
                    if (fieldName === 'month') {
                        return `${monthNames[parseInt(start) - 1]} through ${monthNames[parseInt(end) - 1]}`;
                    }
                    return `${fieldName}s ${start} through ${end}`;
                }
                return `${fieldName} ${parseCronValue(value)}`;
            };
            const parseCronValue = (val) => {
                const n = parseInt(val, 10);
                if (isNaN(n))
                    return val;
                // Map sunday=0 or 7
                return String(n);
            };
            const descriptions = parts.map((p, i) => describeField(p, fieldNames[i]));
            const explanation = `Runs ${descriptions.join(', ')}.`;
            // Calculate next 5 run times (simple simulation)
            const nextRuns = [];
            const now = new Date();
            const [minField, hourField, domField, monField, dowField] = parts;
            let probe = new Date(now);
            const matches = (date, field, type) => {
                const val = type === 'minute' ? date.getMinutes()
                    : type === 'hour' ? date.getHours()
                        : type === 'dom' ? date.getDate()
                            : type === 'month' ? date.getMonth() + 1
                                : date.getDay();
                if (field === '*')
                    return true;
                if (field.includes(','))
                    return field.split(',').map(Number).includes(val);
                if (field.includes('/')) {
                    const [, step] = field.split('/');
                    return val % parseInt(step) === 0;
                }
                if (field.includes('-')) {
                    const [start, end] = field.split('-').map(Number);
                    return val >= start && val <= end;
                }
                return val === parseInt(field);
            };
            let safety = 0;
            while (nextRuns.length < 5 && safety < 100000) {
                safety++;
                probe = new Date(probe.getTime() + 60000); // Increment by 1 minute
                if (matches(probe, minField, 'minute') &&
                    matches(probe, hourField, 'hour') &&
                    matches(probe, domField, 'dom') &&
                    matches(probe, monField, 'month') &&
                    matches(probe, dowField, 'dow')) {
                    nextRuns.push(probe.toISOString().replace('T', ' ').substring(0, 16));
                }
            }
            return { success: true, data: { expression: input.expression, explanation, nextRuns } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'CRON_ERROR' };
        }
    },
};
const passwordGenDef = {
    name: 'password_gen',
    description: 'Generate cryptographically secure random passwords with configurable character sets',
    category: 'utility',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            length: { type: 'number', description: 'Password length', default: 16 },
            uppercase: { type: 'boolean', description: 'Include uppercase letters', default: true },
            lowercase: { type: 'boolean', description: 'Include lowercase letters', default: true },
            digits: { type: 'boolean', description: 'Include digits', default: true },
            symbols: { type: 'boolean', description: 'Include symbols (!@#$%^&* etc.)', default: false },
            count: { type: 'number', description: 'Number of passwords to generate', default: 1 },
        },
        required: [],
    },
    async call(input, _ctx) {
        const length = Math.min(Math.max(4, input.length || 16), 128);
        const numPasswords = Math.min(Math.max(1, input.count || 1), 20);
        const useUpper = input.uppercase !== false;
        const useLower = input.lowercase !== false;
        const useDigits = input.digits !== false;
        const useSymbols = input.symbols === true;
        let charset = '';
        if (useLower)
            charset += 'abcdefghijklmnopqrstuvwxyz';
        if (useUpper)
            charset += 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        if (useDigits)
            charset += '0123456789';
        if (useSymbols)
            charset += '!@#$%^&*()_+-=[]{}|;:,.<>?';
        if (charset.length === 0)
            charset = 'abcdefghijklmnopqrstuvwxyz';
        const passwords = [];
        for (let n = 0; n < numPasswords; n++) {
            const bytes = randomBytes(length);
            let pwd = '';
            for (let i = 0; i < length; i++) {
                pwd += charset[bytes[i] % charset.length];
            }
            passwords.push(pwd);
        }
        // Calculate entropy
        const entropyBits = Math.log2(charset.length) * length;
        const strength = entropyBits >= 80 ? 'strong' : entropyBits >= 50 ? 'moderate' : 'weak';
        return { success: true, data: { passwords, strength } };
    },
};
const colorConvertDef = {
    name: 'color_convert',
    description: 'Convert colors between hex (#ff00ff), rgb (rgb(255,0,255)), and hsl (hsl(300,100%,50%)) formats',
    category: 'utility',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            color: { type: 'string', description: 'Color value in hex, rgb(), or hsl() format' },
            format: { type: 'string', description: 'Input color format', enum: ['hex', 'rgb', 'hsl'], default: 'hex' },
        },
        required: ['color'],
    },
    async call(input, _ctx) {
        try {
            let r = 0, g = 0, b = 0;
            if (input.format === 'hex') {
                const hex = input.color.replace('#', '');
                if (hex.length === 3) {
                    r = parseInt(hex[0] + hex[0], 16);
                    g = parseInt(hex[1] + hex[1], 16);
                    b = parseInt(hex[2] + hex[2], 16);
                }
                else if (hex.length === 6) {
                    r = parseInt(hex.substring(0, 2), 16);
                    g = parseInt(hex.substring(2, 4), 16);
                    b = parseInt(hex.substring(4, 6), 16);
                }
                else {
                    return { success: false, error: 'Invalid hex color', errorCode: 'INVALID_COLOR' };
                }
            }
            else if (input.format === 'rgb') {
                const match = input.color.match(/rgb\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)/i);
                if (!match)
                    return { success: false, error: 'Invalid rgb() format', errorCode: 'INVALID_COLOR' };
                r = parseInt(match[1]);
                g = parseInt(match[2]);
                b = parseInt(match[3]);
            }
            else if (input.format === 'hsl') {
                const match = input.color.match(/hsl\((\d+)\s*,\s*(\d+)%?\s*,\s*(\d+)%?\)/i);
                if (!match)
                    return { success: false, error: 'Invalid hsl() format', errorCode: 'INVALID_COLOR' };
                const h = parseInt(match[1]) / 360;
                const s = parseInt(match[2]) / 100;
                const l = parseInt(match[3]) / 100;
                [r, g, b] = hslToRgb(h, s, l);
            }
            const hex = `#${[r, g, b].map(c => c.toString(16).padStart(2, '0')).join('')}`;
            const rgb = `rgb(${r}, ${g}, ${b})`;
            const [h, s, l] = rgbToHsl(r, g, b);
            const hsl = `hsl(${Math.round(h * 360)}, ${Math.round(s * 100)}%, ${Math.round(l * 100)}%)`;
            return { success: true, data: { hex, rgb, hsl } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'COLOR_ERROR' };
        }
    },
};
function rgbToHsl(r, g, b) {
    r /= 255;
    g /= 255;
    b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h = 0, s = 0, l = (max + min) / 2;
    if (max !== min) {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
        h /= 6;
    }
    return [h, s, l];
}
function hslToRgb(h, s, l) {
    let r, g, b;
    if (s === 0) {
        r = g = b = l;
    }
    else {
        const hue2rgb = (p, q, t) => {
            if (t < 0)
                t += 1;
            if (t > 1)
                t -= 1;
            if (t < 1 / 6)
                return p + (q - p) * 6 * t;
            if (t < 1 / 2)
                return q;
            if (t < 2 / 3)
                return p + (q - p) * (2 / 3 - t) * 6;
            return p;
        };
        const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        const p = 2 * l - q;
        r = hue2rgb(p, q, h + 1 / 3);
        g = hue2rgb(p, q, h);
        b = hue2rgb(p, q, h - 1 / 3);
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}
const portCheckDef = {
    name: 'port_check',
    description: 'Check if a network port is in use on localhost or a specified host',
    category: 'development',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            port: { type: 'number', description: 'Port number to check (1-65535)' },
            host: { type: 'string', description: 'Host to check (default: 127.0.0.1)', default: '127.0.0.1', required: false },
        },
        required: ['port'],
    },
    timeoutMs: 5000,
    async call(input, _ctx) {
        const port = Math.min(65535, Math.max(1, input.port));
        const host = input.host || '127.0.0.1';
        return new Promise((resolvePromise) => {
            const server = createServer();
            server.once('error', (err) => {
                if (err.code === 'EADDRINUSE') {
                    resolvePromise({ success: true, data: { port, inUse: true, service: 'unknown' } });
                }
                else {
                    resolvePromise({ success: true, data: { port, inUse: true, service: err.message } });
                }
            });
            server.once('listening', () => {
                server.close();
                resolvePromise({ success: true, data: { port, inUse: false } });
            });
            server.listen(port, host);
        });
    },
};
const npmInfoDef = {
    name: 'npm_info',
    description: 'Look up npm package metadata (description, latest version, keywords, license) from the public registry',
    category: 'development',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            package: { type: 'string', description: 'npm package name' },
            version: { type: 'string', description: 'Specific version (default: latest)', required: false },
        },
        required: ['package'],
    },
    timeoutMs: 15000,
    async call(input, _ctx) {
        try {
            const url = input.version
                ? `https://registry.npmjs.org/${encodeURIComponent(input.package)}/${input.version}`
                : `https://registry.npmjs.org/${encodeURIComponent(input.package)}/latest`;
            const response = await fetch(url, { signal: AbortSignal.timeout(10000) });
            if (!response.ok) {
                return { success: false, error: `Package not found: ${input.package} (HTTP ${response.status})`, errorCode: 'NPM_NOT_FOUND' };
            }
            const data = await response.json();
            return {
                success: true,
                data: {
                    name: data.name || input.package,
                    version: data.version || 'unknown',
                    description: data.description || '',
                    keywords: data.keywords || [],
                    license: data.license || 'unknown',
                    repository: data.repository?.url || data.repository || '',
                    homepage: data.homepage || '',
                },
            };
        }
        catch (err) {
            if (err instanceof Error && err.name === 'TimeoutError') {
                return { success: false, error: 'npm registry request timed out', errorCode: 'TIMEOUT' };
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'NPM_ERROR' };
        }
    },
};
const codeMetricsDef = {
    name: 'code_metrics',
    description: 'Analyze source code metrics: physical lines, code lines, comment lines, blank lines, function count, class count, cyclomatic complexity',
    category: 'development',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            source: { type: 'string', description: 'Source code to analyze' },
            language: { type: 'string', description: 'Programming language hint', required: false },
        },
        required: ['source'],
    },
    async call(input, _ctx) {
        try {
            const lines = input.source.split('\n');
            const total = lines.length;
            let code = 0, comments = 0, blanks = 0, functions = 0, classes = 0, complexity = 1;
            let inBlock = false;
            const lang = (input.language || '').toLowerCase();
            for (const rawLine of lines) {
                const trimmed = rawLine.trim();
                if (trimmed === '') {
                    blanks++;
                    continue;
                }
                // Block comment handling
                if (inBlock) {
                    comments++;
                    if (trimmed.includes('*/'))
                        inBlock = false;
                    continue;
                }
                if (trimmed.startsWith('/*')) {
                    comments++;
                    if (!trimmed.includes('*/'))
                        inBlock = true;
                    continue;
                }
                if (trimmed.startsWith('//') || trimmed.startsWith('#') || trimmed.startsWith('--') || trimmed.startsWith('%') || trimmed.startsWith('"""')) {
                    comments++;
                    continue;
                }
                code++;
                // Function detection
                if (/\b(?:function|def |fun |fn |func)\b/.test(trimmed))
                    functions++;
                else if (/=>\s*[{`]/.test(trimmed) || /=>\s*$/.test(trimmed))
                    functions++;
                else if (lang.includes('go') && /^func\s+\w/.test(trimmed))
                    functions++;
                // Method shorthand in objects/classes (intentionally not double-counted here)
                // Class detection
                if (/\bclass\s+\w+/.test(trimmed) && !trimmed.includes('className'))
                    classes++;
                // Complexity
                if (/\b(?:if|else if|while|for|catch|case|&&|\|\|)\b/.test(trimmed))
                    complexity++;
            }
            const label = complexity >= 50 ? 'Very Complex' : complexity >= 30 ? 'Complex' : complexity >= 15 ? 'Moderate' : 'Simple';
            return {
                success: true,
                data: {
                    lines: { total, code, comments, blanks, commentRatio: total > 0 ? `${((comments / total) * 100).toFixed(1)}%` : '0%' },
                    functions,
                    classes,
                    complexity,
                    label,
                },
            };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'METRICS_ERROR' };
        }
    },
};
const fileOpsDef = {
    name: 'file_ops',
    description: 'Perform file operations: copy, move, or rename files on the filesystem',
    category: 'development',
    riskLevel: 'high',
    inputSchema: {
        type: 'object',
        properties: {
            action: { type: 'string', description: 'File operation', enum: ['copy', 'move', 'rename'] },
            source: { type: 'string', description: 'Source file path' },
            destination: { type: 'string', description: 'Destination file path' },
            overwrite: { type: 'boolean', description: 'Overwrite if destination exists', default: false },
        },
        required: ['action', 'source', 'destination'],
    },
    async call(input, _ctx) {
        try {
            const src = resolve(input.source);
            const dst = resolve(input.destination);
            if (!existsSync(src)) {
                return { success: false, error: `Source not found: ${input.source}`, errorCode: 'NOT_FOUND' };
            }
            if (existsSync(dst) && !input.overwrite) {
                return { success: false, error: `Destination exists: ${input.destination}. Set overwrite: true to replace.`, errorCode: 'EXISTS' };
            }
            // Ensure destination directory exists
            const dstDir = dirname(dst);
            if (!existsSync(dstDir)) {
                mkdirSync(dstDir, { recursive: true });
            }
            switch (input.action) {
                case 'copy':
                    copyFileSync(src, dst);
                    break;
                case 'move':
                case 'rename':
                    renameSync(src, dst);
                    break;
            }
            const stats = statSync(dst);
            return { success: true, data: { action: input.action, source: input.source, destination: input.destination, success: true, size: stats.size }, didModify: true };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'FILE_OPS_ERROR' };
        }
    },
};
const diskUsageDef = {
    name: 'disk_usage',
    description: 'Check disk usage information for a given path or all mounted filesystems',
    category: 'monitoring',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            path: { type: 'string', description: 'Path to check (default: current directory)', required: false },
            humanReadable: { type: 'boolean', description: 'Show human-readable sizes', default: true },
        },
        required: [],
    },
    timeoutMs: 5000,
    async call(input, _ctx) {
        try {
            const targetPath = input.path || '.';
            const output = execSync(`df -h "${targetPath}"`, { encoding: 'utf-8', timeout: 4000 });
            const lines = output.trim().split('\n');
            if (lines.length < 2) {
                return { success: false, error: 'No disk info available', errorCode: 'DF_ERROR' };
            }
            const headers = lines[0].split(/\s+/);
            const values = lines[1].split(/\s+/);
            const result = {};
            headers.forEach((h, i) => {
                result[h.toLowerCase()] = values[i] || '';
            });
            return {
                success: true,
                data: {
                    filesystem: result.filesystem || '',
                    size: result.size || '',
                    used: result.used || '',
                    available: result.avail || result.available || '',
                    usagePercent: result['use%'] || result.use || '',
                    mount: result.mounted || result.mountedon || '',
                },
            };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'DISK_ERROR' };
        }
    },
};
// ─── Tool: env_list ─────────────────────────────────────────────────────────
const envListDef = {
    name: 'env_list',
    description: 'List all environment variables and their values (values may be truncated for security)',
    category: 'monitoring',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {},
        required: [],
    },
    async call(_input, _ctx) {
        const safeKeys = ['PATH', 'HOME', 'USER', 'SHELL', 'PWD', 'NODE_ENV', 'PORT', 'LANG', 'TERM', 'DISPLAY', 'EDITOR', 'npm_package_name', 'npm_package_version', 'npm_command', 'npm_lifecycle_event'];
        const variables = [];
        for (const [key, value] of Object.entries(process.env)) {
            if (value === undefined)
                continue;
            // Mask sensitive-looking values
            const isSensitive = /key|secret|token|password|credential|auth|api.?key/i.test(key);
            const displayValue = isSensitive && !safeKeys.includes(key)
                ? value.substring(0, 4) + '...' + value.substring(value.length - 4)
                : value.length > 200 ? value.substring(0, 200) + '...' : value;
            variables.push({ key, value: displayValue });
        }
        variables.sort((a, b) => a.key.localeCompare(b.key));
        return { success: true, data: { variables, count: variables.length } };
    },
};
const processPsDef = {
    name: 'process_ps',
    description: 'List running processes (uses ps aux on Linux/Mac, tasklist on Windows)',
    category: 'monitoring',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            filter: { type: 'string', description: 'Filter by command name (optional)', required: false },
            maxResults: { type: 'number', description: 'Maximum results', default: 30 },
        },
        required: [],
    },
    timeoutMs: 5000,
    async call(input, _ctx) {
        try {
            const maxResults = input.maxResults || 30;
            const isWindows = process.platform === 'win32';
            const cmd = isWindows ? 'tasklist /FO CSV /NH' : 'ps aux --no-headers 2>/dev/null || ps aux';
            const output = execSync(cmd, { encoding: 'utf-8', timeout: 4000, maxBuffer: 1024 * 1024 });
            const lines = output.trim().split('\n').filter(Boolean);
            const processes = lines
                .map(line => {
                if (isWindows) {
                    const parts = line.replace(/"/g, '').split(',');
                    return { pid: parts[1] || '?', cpu: parts[3] || '?', mem: parts[4] || '?', command: parts[0] || '?' };
                }
                const parts = line.trim().split(/\s+/);
                const pid = parts[1] || '?';
                const cpu = parts[2] || '?';
                const mem = parts[3] || '?';
                const command = parts.slice(10).join(' ') || '?';
                return { pid, cpu, mem, command };
            })
                .filter(p => {
                if (input.filter)
                    return p.command.toLowerCase().includes(input.filter.toLowerCase());
                return true;
            })
                .slice(0, maxResults);
            return { success: true, data: { processes, count: processes.length } };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'PS_ERROR' };
        }
    },
};
const jwtDecodeDef = {
    name: 'jwt_decode',
    description: 'Decode and inspect a JWT token (header, payload, signature) without verification',
    category: 'development',
    riskLevel: 'readonly',
    inputSchema: {
        type: 'object',
        properties: {
            token: { type: 'string', description: 'JWT token string (e.g., "eyJhbGciOiJIUzI1NiIs..."}' },
        },
        required: ['token'],
    },
    async call(input, _ctx) {
        try {
            const parts = input.token.trim().split('.');
            if (parts.length !== 3) {
                return { success: false, error: 'Invalid JWT format: expected 3 dot-separated parts (header.payload.signature)', errorCode: 'INVALID_JWT' };
            }
            const decodeBase64Url = (str) => {
                // Convert base64url to base64
                let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
                while (base64.length % 4)
                    base64 += '=';
                return Buffer.from(base64, 'base64').toString('utf-8');
            };
            let header;
            let payload;
            try {
                header = JSON.parse(decodeBase64Url(parts[0]));
                payload = JSON.parse(decodeBase64Url(parts[1]));
            }
            catch {
                return { success: false, error: 'Failed to decode JWT parts (invalid base64 or JSON)', errorCode: 'DECODE_ERROR' };
            }
            // Check expiration
            const now = Math.floor(Date.now() / 1000);
            const expired = payload.exp ? payload.exp < now : undefined;
            const expiresAt = payload.exp ? new Date(payload.exp * 1000).toISOString() : undefined;
            return {
                success: true,
                data: {
                    header,
                    payload: { ...payload, ...(expired !== undefined ? { _expired: expired, _expiresAt: expiresAt } : {}) },
                    signature: parts[2].substring(0, 20) + '...',
                    valid: parts.length === 3,
                },
            };
        }
        catch (err) {
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'JWT_ERROR' };
        }
    },
};
const bugHunterMiniDef = {
    name: 'bug_hunter_mini',
    description: 'Deep AI-powered bug hunting in source code — finds logic errors, edge cases, race conditions, and undefined behavior',
    category: 'testing',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            code: { type: 'string', description: 'Source code to analyze for bugs' },
            language: { type: 'string', description: 'Programming language', required: false },
            depth: { type: 'string', description: 'Analysis depth', enum: ['quick', 'deep'], default: 'deep' },
        },
        required: ['code'],
    },
    timeoutMs: 90000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const lang = input.language || 'source';
            const isDeep = (input.depth || 'deep') === 'deep';
            const depthInstruction = isDeep
                ? 'Perform an exhaustive deep analysis. Check for: null pointer dereferences, race conditions, memory leaks (for systems languages), type confusion, off-by-one errors, infinite loops, unhandled promise rejections, improper error handling, security vulnerabilities, and concurrency issues.'
                : 'Do a quick scan for obvious bugs: syntax errors, type mismatches, undefined variables, and common pitfalls.';
            const result = await translator.reason(`Hunt for bugs in this ${lang} code:\n\n\`\`\`${lang}\n${input.code}\n\`\`\`\n\n${depthInstruction}\n\nFor each bug found, specify: LINE NUMBER, SEVERITY (critical/major/minor), DESCRIPTION, and FIX.`, 'You are an expert bug hunter with 20+ years of experience. You find bugs that other reviewers miss. Be extremely thorough.', { maxTokens: 3072 });
            const critical = (result.match(/critical/gi) || []).length;
            const major = (result.match(/\bmajor\b/gi) || []).length;
            const minor = (result.match(/\bminor\b/gi) || []).length;
            const totalBugs = critical + major + minor;
            const severity = critical > 0 ? 'critical' : major > 0 ? 'major' : minor > 0 ? 'minor' : 'none';
            return { success: true, data: { bugs: result, severity, count: totalBugs } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('bug_hunter_mini', 'To hunt bugs manually:\n' +
                    '  • Check for null/undefined dereferences and type mismatches\n' +
                    '  • Look for off-by-one errors in loops\n' +
                    '  • Verify async error handling (try/catch, .catch())\n' +
                    '  • Check for race conditions in shared state\n' +
                    '  • Test edge cases: empty arrays, null inputs, boundary values\n' +
                    '  • Review security: injection, XSS, hardcoded secrets\n' +
                    'Start Ollama with: ollama serve  (then retry this tool)', 'bugs');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'BUG_HUNTER_ERROR' };
        }
    },
};
const apiDesignMiniDef = {
    name: 'api_design_mini',
    description: 'Design REST, GraphQL, or WebSocket API endpoints from a natural language description using AI',
    category: 'development',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            description: { type: 'string', description: 'Description of the API requirements' },
            style: { type: 'string', description: 'API style', enum: ['rest', 'graphql', 'websocket'], default: 'rest' },
        },
        required: ['description'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const style = input.style || 'rest';
            const styleGuide = style === 'rest'
                ? 'Design RESTful endpoints with: HTTP method, URL path, request body schema, response schema, status codes, and authentication requirements.'
                : style === 'graphql'
                    ? 'Design GraphQL schema with: types, queries, mutations, subscriptions, and resolvers.'
                    : 'Design WebSocket events with: event names, payload schemas, server→client events, client→server events, and connection lifecycle.';
            const result = await translator.reason(`Design a ${style} API for:\n\n${input.description}\n\n${styleGuide}\n\nBe specific with endpoint paths, data types, and example payloads.`, 'You are an expert API designer. Design practical, well-structured APIs following industry best practices.', { maxTokens: 2048 });
            const endpointCount = (result.match(/(?:GET|POST|PUT|DELETE|PATCH|query |mutation |subscription|event:)/gi) || []).length;
            return { success: true, data: { design: result, endpoints: Math.max(endpointCount, 1) } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('api_design_mini', 'To design APIs manually:\n' +
                    '  • REST: Define resources (nouns), HTTP methods, URL paths, request/response schemas\n' +
                    '  • Use proper status codes: 200 OK, 201 Created, 400 Bad Request, 404 Not Found, 500 Server Error\n' +
                    '  • Add authentication (JWT/OAuth) and rate limiting\n' +
                    '  • Document with OpenAPI/Swagger for discoverability\n' +
                    '  • GraphQL: Define types, queries, mutations, and resolvers\n' +
                    '  • WebSocket: Define event names, payloads, and lifecycle\n' +
                    'Start Ollama with: ollama serve  (then retry this tool)', 'design');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'API_DESIGN_ERROR' };
        }
    },
};
const commitMsgMiniDef = {
    name: 'commit_msg_mini',
    description: 'Generate git commit messages from a diff using AI (supports conventional commits, simple, or detailed styles)',
    category: 'development',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            diff: { type: 'string', description: 'Git diff output or summary of changes' },
            style: { type: 'string', description: 'Commit message style', enum: ['conventional', 'simple', 'detailed'], default: 'conventional' },
        },
        required: ['diff'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const style = input.style || 'conventional';
            const styleInstructions = {
                conventional: 'Use Conventional Commits format: type(scope): description (e.g., "feat(auth): add OAuth2 login flow"). Suggest 3 options.',
                simple: 'Use short, one-line messages. Suggest 3 options.',
                detailed: 'Include a subject line, a blank line, then a detailed body explaining what and why. Suggest 2 options.',
            };
            const result = await translator.reason(`Generate git commit messages for this diff:\n\n\`\`\`diff\n${input.diff}\n\`\`\`\n\n${styleInstructions[style]}`, 'You are an expert at writing clear, meaningful git commit messages that explain both WHAT changed and WHY.', { maxTokens: 1536 });
            const messages = result.split('\n')
                .filter(l => l.match(/^\d+[.)]\s/) || l.match(/^\s*[-*]\s+/) || l.match(/^feat[(:]/) || l.match(/^fix[(:]/) || l.match(/^chore[(:]/) || l.match(/^refactor[(:]/) || l.match(/^docs[(:]/) || l.match(/^test[(:]/) || l.match(/^style[(:]/) || l.match(/^perf[(:]/) || l.match(/^ci[(:]/) || l.match(/^build[(:]/))
                .filter(l => l.trim().length < 100)
                .map(l => l.replace(/^\d+[.)]\s*/, '').replace(/^\s*[-*]\s+/, '').trim());
            return { success: true, data: { messages: messages.slice(0, 5) } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                const fb = llmFallbackResponse('commit_msg_mini', 'feat(scope): add new feature\nfix(scope): fix issue\nchore(scope): maintenance' +
                    ' — Start Ollama with: ollama serve');
                fb.data.messages = [fb.data.guidance]; // Wrap in array to match messages: string[]
                return fb;
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'COMMIT_MSG_ERROR' };
        }
    },
};
const readmeGenMiniDef = {
    name: 'readme_gen_mini',
    description: 'Generate a complete README.md from project details using AI (title, description, install, usage, API, contributing)',
    category: 'development',
    riskLevel: 'low',
    inputSchema: {
        type: 'object',
        properties: {
            projectName: { type: 'string', description: 'Project name' },
            description: { type: 'string', description: 'Brief project description' },
            features: { type: 'string', description: 'Key features (comma-separated)', required: false },
            installation: { type: 'string', description: 'Installation instructions or commands', required: false },
            usage: { type: 'string', description: 'Usage examples or CLI commands', required: false },
            techStack: { type: 'string', description: 'Technologies used (comma-separated)', required: false },
        },
        required: ['projectName', 'description'],
    },
    timeoutMs: 60000,
    async call(input, _ctx) {
        try {
            const { AITranslator } = await getTranslator();
            const translator = new AITranslator();
            const context = [
                `Project: ${input.projectName}`,
                `Description: ${input.description}`,
                input.features ? `Features: ${input.features}` : '',
                input.installation ? `Installation: ${input.installation}` : '',
                input.usage ? `Usage: ${input.usage}` : '',
                input.techStack ? `Tech Stack: ${input.techStack}` : '',
            ].filter(Boolean).join('\n');
            const result = await translator.reason(`Generate a complete README.md for this project:\n\n${context}\n\nInclude sections: Title, Description, Features, Installation, Usage, API/Configuration (if applicable), Contributing, License. Use proper Markdown formatting with code blocks, badges (as text), and emojis for visual appeal.`, 'You are a technical writer who creates excellent README files. Make it professional, scannable, and beginner-friendly.', { maxTokens: 2048 });
            return { success: true, data: { readme: result } };
        }
        catch (err) {
            if (isLLMConnectionError(err)) {
                return llmFallbackResponse('readme_gen_mini', '# Project Name\n## Description\nWhat does it do?\n## Installation\n```bash\ngit clone ...\nnpm install\n```\n## Usage\nExamples here.\n## License\nMIT\n\n' +
                    'Start Ollama with: ollama serve  (then retry this tool)', 'readme');
            }
            return { success: false, error: err instanceof Error ? err.message : String(err), errorCode: 'README_GEN_ERROR' };
        }
    },
};
// ═════════════════════════════════════════════════════════════════════════════
// Export all aux2 tools as a single array
// ═════════════════════════════════════════════════════════════════════════════
export const auxTools2 = [
    // Data Processing Tools
    yamlConvertDef,
    base64CodecDef,
    textTransformDef,
    regexTestDef,
    textDiffDef,
    jsonFormatDef,
    // Utility Tools
    timeConvertDef,
    cronExplainDef,
    passwordGenDef,
    colorConvertDef,
    // More Development Tools
    portCheckDef,
    npmInfoDef,
    codeMetricsDef,
    fileOpsDef,
    // System Tools
    diskUsageDef,
    envListDef,
    processPsDef,
    jwtDecodeDef,
    // More Mini Agents (AI-powered)
    bugHunterMiniDef,
    apiDesignMiniDef,
    commitMsgMiniDef,
    readmeGenMiniDef,
];
