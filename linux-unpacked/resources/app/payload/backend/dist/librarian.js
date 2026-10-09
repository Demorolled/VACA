#!/usr/bin/env tsx
/**
 * 📚 Librarian — Reference Library TUI Search Tool
 * =================================================
 *
 * A zero-dependency terminal user interface for searching and browsing
 * the VACA reference library (data/library/).
 *
 * Usage:
 *   npx tsx backend/src/librarian.ts              → Interactive TUI mode
 *   npx tsx backend/src/librarian.ts search <q>    → One-shot search
 *   npx tsx backend/src/librarian.ts list          → List all files
 *   npx tsx backend/src/librarian.ts read <file>   → View full file content
 *   npx tsx backend/src/librarian.ts help          → Show help
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as readline from 'node:readline';
import { fileURLToPath } from 'node:url';
// ─── Paths ────────────────────────────────────────────────────────────────
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const LIBRARY_DIR = path.join(PROJECT_ROOT, 'data', 'library');
// ─── ANSI escape codes (zero dependencies) ──────────────────────────────
const ANSI = {
    reset: '\x1b[0m',
    bold: '\x1b[1m',
    dim: '\x1b[2m',
    italic: '\x1b[3m',
    underline: '\x1b[4m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m',
    white: '\x1b[37m',
    bgBlue: '\x1b[44m',
    bgCyan: '\x1b[46m',
    bgGreen: '\x1b[42m',
    bgYellow: '\x1b[43m',
    clearScreen: '\x1b[2J\x1b[H',
    clearLine: '\x1b[2K\r',
    hideCursor: '\x1b[?25l',
    showCursor: '\x1b[?25h',
};
// ─── File loading ────────────────────────────────────────────────────────
function getFileTopics() {
    try {
        const indexContent = fs.readFileSync(path.join(LIBRARY_DIR, '00-reference-index.md'), 'utf-8');
        const topics = {};
        const lines = indexContent.split('\n');
        let currentFile = '';
        for (const line of lines) {
            // Extract file names from the library structure listing
            const fileMatch = line.match(/├──\s+(\d+-[\w-]+)\.md/);
            if (fileMatch) {
                currentFile = `${fileMatch[1]}.md`;
                topics[currentFile] = [];
                continue;
            }
            // Extract topic descriptions from the quick-use guide table
            const topicMatch = line.match(/\*\*(.+?)\*\*/);
            if (topicMatch && currentFile && line.includes('|')) {
                topics[currentFile].push(topicMatch[1].toLowerCase());
            }
        }
        return topics;
    }
    catch {
        return {};
    }
}
function loadLibraryFiles() {
    const files = [];
    const fileTopics = getFileTopics();
    try {
        if (!fs.existsSync(LIBRARY_DIR)) {
            console.error(`${ANSI.red}✗ Library directory not found: ${LIBRARY_DIR}${ANSI.reset}`);
            process.exit(1);
        }
        const entries = fs.readdirSync(LIBRARY_DIR).sort();
        for (const entry of entries) {
            if (!entry.endsWith('.md'))
                continue;
            const filePath = path.join(LIBRARY_DIR, entry);
            const content = fs.readFileSync(filePath, 'utf-8');
            // Extract headings for topic indexing
            const headings = [];
            for (const line of content.split('\n')) {
                const hMatch = line.match(/^(#{1,4})\s+(.+)/);
                if (hMatch) {
                    headings.push(hMatch[2].trim());
                }
            }
            // Build display name (remove number prefix, replace hyphens)
            const display = entry
                .replace(/\.md$/, '')
                .replace(/^\d+-/, '')
                .replace(/-/g, ' ')
                .replace(/\b\w/g, (c) => c.toUpperCase());
            files.push({
                name: entry,
                display,
                path: filePath,
                content,
                headings,
                topics: fileTopics[entry] || [],
            });
        }
    }
    catch (err) {
        console.error(`${ANSI.red}✗ Failed to load library files: ${err.message}${ANSI.reset}`);
        process.exit(1);
    }
    return files;
}
// ─── Search engine ──────────────────────────────────────────────────────
function highlightText(text, query) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    let result = text;
    for (const word of words) {
        const regex = new RegExp(`(${escapeRegex(word)})`, 'gi');
        result = result.replace(regex, `${ANSI.yellow}${ANSI.bold}$1${ANSI.reset}`);
    }
    return result;
}
function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
function scoreFile(file, words, lowerContent) {
    let score = 0;
    for (const word of words) {
        if (word.length < 2)
            continue;
        // Regex to count matches
        const regex = new RegExp(escapeRegex(word), 'gi');
        const matches = lowerContent.match(regex);
        const count = matches ? matches.length : 0;
        if (count > 0) {
            // Base score from match count (capped)
            score += Math.min(count, 20) * 5;
            // Position bonus: matches near the top are more relevant
            const firstIndex = lowerContent.indexOf(word);
            if (firstIndex >= 0) {
                score += Math.max(0, 50 - Math.floor(firstIndex / 100));
            }
            // Exact heading match bonus
            for (const heading of file.headings) {
                if (heading.toLowerCase().includes(word)) {
                    score += 30;
                }
            }
            // Topic keyword bonus
            for (const topic of file.topics) {
                if (topic.includes(word) || word.includes(topic)) {
                    score += 20;
                }
            }
            // File name match bonus
            if (file.display.toLowerCase().includes(word)) {
                score += 25;
            }
        }
    }
    return score;
}
function extractSnippets(content, query, maxSnippets = 3) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const snippets = [];
    const lines = content.split('\n');
    let foundIndices = new Set();
    for (let i = 0; i < lines.length && snippets.length < maxSnippets; i++) {
        const lowerLine = lines[i].toLowerCase();
        const hasMatch = words.some((w) => lowerLine.includes(w));
        if (hasMatch && !foundIndices.has(i)) {
            // Collect surrounding context (2 lines before, 2 after)
            const start = Math.max(0, i - 2);
            const end = Math.min(lines.length, i + 3);
            let snippetLines = [];
            for (let j = start; j < end; j++) {
                const prefix = j === i ? `${ANSI.bold}>${ANSI.reset} ` : '  ';
                snippetLines.push(`${prefix}${lines[j]}`);
                foundIndices.add(j);
            }
            snippets.push(snippetLines.slice(0, 5).join('\n').trim());
        }
    }
    return snippets.length > 0
        ? snippets
        : [`  ${ANSI.dim}(no matching snippet found)${ANSI.reset}`];
}
function search(files, query) {
    const lowerQuery = query.toLowerCase();
    const words = lowerQuery.split(/\s+/).filter((w) => w.length > 1);
    if (words.length === 0)
        return [];
    const results = [];
    for (const file of files) {
        const lowerContent = file.content.toLowerCase();
        const score = scoreFile(file, words, lowerContent);
        if (score > 0) {
            const snippets = extractSnippets(file.content, query);
            const matchCount = words.reduce((sum, w) => {
                const regex = new RegExp(escapeRegex(w), 'gi');
                return sum + (file.content.match(regex) || []).length;
            }, 0);
            results.push({ file, score, snippets, matchCount });
        }
    }
    results.sort((a, b) => b.score - a.score);
    return results;
}
// ─── Display helpers ────────────────────────────────────────────────────
function truncate(str, maxLen) {
    if (str.length <= maxLen)
        return str;
    return str.slice(0, maxLen - 3) + '...';
}
function formatScoreBar(score, maxScore) {
    const barLen = 10;
    const ratio = maxScore > 0 ? score / maxScore : 0;
    const filled = Math.round(ratio * barLen);
    const empty = barLen - filled;
    const color = ratio > 0.7 ? ANSI.green : ratio > 0.3 ? ANSI.yellow : ANSI.red;
    const bar = color +
        '█'.repeat(filled) +
        ANSI.dim +
        '░'.repeat(Math.max(0, empty)) +
        ANSI.reset;
    return `${bar} ${Math.round(ratio * 100)}%`;
}
function showResults(results, query, page, pageSize) {
    const totalPages = Math.ceil(results.length / pageSize);
    const start = page * pageSize;
    const end = Math.min(start + pageSize, results.length);
    const pageResults = results.slice(start, end);
    const maxScore = results[0]?.score || 1;
    console.log(`${ANSI.cyan}${ANSI.bold}━━━ Results for "${query}" ━━━${ANSI.reset}`);
    console.log(`${ANSI.dim}${results.length} file(s) matched | Page ${page + 1}/${totalPages}${ANSI.reset}\n`);
    for (let i = 0; i < pageResults.length; i++) {
        const r = pageResults[i];
        const idx = start + i + 1;
        console.log(`${ANSI.bold}${ANSI.blue}[${idx}]${ANSI.reset} ${ANSI.bold}${r.file.display}${ANSI.reset}  ${ANSI.dim}(${r.file.name})${ANSI.reset}`);
        console.log(`     Relevance: ${formatScoreBar(r.score, maxScore)}  ${ANSI.dim}| ${r.matchCount} match(es)${ANSI.reset}`);
        // Show topics if available
        if (r.file.topics.length > 0) {
            const tags = r.file.topics.slice(0, 5).map((t) => `${ANSI.bgCyan}${ANSI.white} ${t} ${ANSI.reset}`);
            console.log(`     Tags: ${tags.join(' ')}`);
        }
        // Show headings as quick nav
        if (r.file.headings.length > 0) {
            const hShown = r.file.headings.slice(0, 4).map((h) => `${ANSI.dim}→${ANSI.reset} ${h}`);
            console.log(`     ${hShown.join('  ')}`);
        }
        // Show snippets
        if (r.snippets.length > 0 && r.snippets[0] !== `  ${ANSI.dim}(no matching snippet found)${ANSI.reset}`) {
            console.log(`     ${ANSI.underline}Snippet:${ANSI.reset}`);
            for (const snippet of r.snippets.slice(0, 1)) {
                const highlighted = highlightText(snippet, query);
                console.log(`     ${highlighted.replace(/\n/g, '\n     ')}`);
            }
        }
        console.log('');
    }
}
function showFileContent(file) {
    return new Promise((resolve) => {
        console.log(`${ANSI.clearScreen}${ANSI.hideCursor}`);
        const lines = file.content.split('\n');
        const totalLines = lines.length;
        const pageSize = process.stdout.rows ? process.stdout.rows - 3 : 20;
        let currentPage = 0;
        const totalPages = Math.ceil(totalLines / pageSize);
        function renderPage() {
            const start = currentPage * pageSize;
            const end = Math.min(start + pageSize, totalLines);
            const pageLines = lines.slice(start, end);
            // Header
            console.log(`${ANSI.bold}${ANSI.bgBlue}${ANSI.white}  📖 ${file.display} (${file.name})  ${ANSI.reset}`);
            console.log(`${ANSI.dim}Page ${currentPage + 1}/${totalPages} • ${totalLines} lines • Press ← → to navigate, 'q' to return${ANSI.reset}`);
            console.log('');
            // Content with line numbers
            for (let i = 0; i < pageLines.length; i++) {
                const lineNum = start + i + 1;
                const isCodeBlock = pageLines[i].trimStart().startsWith('```');
                const isHeading = pageLines[i].startsWith('#');
                let formattedLine = pageLines[i];
                if (isCodeBlock) {
                    formattedLine = `${ANSI.dim}${pageLines[i]}${ANSI.reset}`;
                }
                else if (isHeading) {
                    formattedLine = `${ANSI.bold}${ANSI.cyan}${pageLines[i]}${ANSI.reset}`;
                }
                const linePrefix = `${ANSI.dim}${String(lineNum).padStart(4, ' ')}${ANSI.reset}`;
                console.log(`${linePrefix} ${formattedLine}`);
            }
            console.log(`\n${ANSI.dim}[${currentPage + 1}/${totalPages}] n=next p=prev q=quit${ANSI.reset}`);
        }
        renderPage();
        // Use raw mode for single-key navigation
        const stdin = process.stdin;
        const wasRaw = stdin.isRaw;
        stdin.setRawMode(true);
        stdin.resume();
        function handleKey(key) {
            const keyStr = key.toString();
            if (keyStr === 'q' || keyStr === '\u0003') {
                stdin.removeListener('data', handleKey);
                stdin.setRawMode(wasRaw ?? false);
                stdin.pause();
                console.log(`${ANSI.showCursor}`);
                resolve();
                return;
            }
            if ((keyStr === 'n' || keyStr === '\u001b[C') && currentPage < totalPages - 1) {
                currentPage++;
                renderPage();
            }
            if ((keyStr === 'p' || keyStr === '\u001b[D') && currentPage > 0) {
                currentPage--;
                renderPage();
            }
        }
        stdin.on('data', handleKey);
    });
}
// ─── Interactive TUI mode ──────────────────────────────────────────────
async function interactiveTUI(files) {
    console.log(`${ANSI.clearScreen}${ANSI.hideCursor}`);
    // Welcome banner
    console.log(`
${ANSI.bold}${ANSI.cyan}  ╔══════════════════════════════════════════════════╗${ANSI.reset}
${ANSI.bold}${ANSI.cyan}  ║     📚  Librarian — Reference Library Search     ║${ANSI.reset}
${ANSI.bold}${ANSI.cyan}  ╚══════════════════════════════════════════════════╝${ANSI.reset}
${ANSI.dim}  Indexed ${files.length} library files • Type a query to search, or use commands:${ANSI.reset}
  ${ANSI.bold}list${ANSI.reset} — Show all files  |  ${ANSI.bold}read <n>${ANSI.reset} — View file by number
  ${ANSI.bold}help${ANSI.reset} — Show help       |  ${ANSI.bold}q${ANSI.reset} / ${ANSI.bold}exit${ANSI.reset} — Quit
`);
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
        prompt: `${ANSI.cyan}${ANSI.bold}librarian>${ANSI.reset} `,
        terminal: true,
    });
    rl.prompt();
    for await (const line of rl) {
        const input = line.trim();
        const lower = input.toLowerCase();
        if (lower === 'q' || lower === 'quit' || lower === 'exit') {
            break;
        }
        if (lower === 'help') {
            console.log(`
${ANSI.bold}Commands:${ANSI.reset}
  ${ANSI.cyan}<query>${ANSI.reset}     — Search all library files for the given terms
  ${ANSI.cyan}list${ANSI.reset}        — List all 30 library files with descriptions
  ${ANSI.cyan}read <n>${ANSI.reset}    — Read file #<n> from the last search results
  ${ANSI.cyan}read <name>${ANSI.reset} — Read a specific file by name or partial name
  ${ANSI.cyan}help${ANSI.reset}        — Show this help message
  ${ANSI.cyan}q${ANSI.reset}           — Quit Librarian

${ANSI.bold}Tips:${ANSI.reset}
  • Search is case-insensitive and matches across headings, code, and descriptions
  • Results are ranked by relevance (match frequency + position + heading bonus)
  • Use multi-word queries for more precise results (e.g. "kubernetes deployment")
  • After searching, type ${ANSI.cyan}read 1${ANSI.reset} to view the top result in detail
`);
            rl.prompt();
            continue;
        }
        if (lower === 'list') {
            console.log(`\n${ANSI.bold}${ANSI.cyan}━━━ All ${files.length} Library Files ━━━${ANSI.reset}\n`);
            for (let i = 0; i < files.length; i++) {
                const f = files[i];
                const num = `${i + 1}`.padStart(2, ' ');
                console.log(`  ${ANSI.blue}[${num}]${ANSI.reset} ${ANSI.bold}${f.display}${ANSI.reset}`);
                console.log(`       ${ANSI.dim}${f.name}${ANSI.reset}`);
                if (f.headings.length > 0) {
                    const firstH = f.headings[0];
                    console.log(`       ${ANSI.italic}${firstH}${ANSI.reset}`);
                }
                console.log('');
            }
            rl.prompt();
            continue;
        }
        if (lower.startsWith('read ')) {
            const arg = input.slice(5).trim();
            let targetFile;
            // Try numeric index
            const num = parseInt(arg, 10);
            if (!isNaN(num) && num >= 1 && num <= files.length) {
                targetFile = files[num - 1];
            }
            else {
                // Try name match
                const lowerArg = arg.toLowerCase();
                targetFile = files.find((f) => f.name.toLowerCase().includes(lowerArg) ||
                    f.display.toLowerCase().includes(lowerArg));
            }
            if (targetFile) {
                console.log(`${ANSI.showCursor}`);
                await showFileContent(targetFile);
                console.log(`${ANSI.hideCursor}${ANSI.clearScreen}`);
                // Re-show results if they exist
                rl.prompt();
            }
            else {
                console.log(`${ANSI.red}✗ File not found. Use 'list' to see available files.${ANSI.reset}`);
                rl.prompt();
            }
            continue;
        }
        // It's a search query
        if (input.length > 0) {
            const results = search(files, input);
            if (results.length === 0) {
                console.log(`\n${ANSI.yellow}No matches found for "${input}". Try different terms.${ANSI.reset}\n`);
            }
            else {
                showResults(results, input, 0, 5);
            }
        }
        rl.prompt();
    }
    console.log(`${ANSI.showCursor}`);
    rl.close();
    console.log(`\n${ANSI.green}📚 Happy researching!${ANSI.reset}\n`);
}
// ─── One-shot commands ──────────────────────────────────────────────────
function cmdSearch(files, query) {
    const results = search(files, query);
    if (results.length === 0) {
        console.log(`\n${ANSI.yellow}No matches found for "${query}".${ANSI.reset}\n`);
        return;
    }
    showResults(results, query, 0, results.length);
}
function cmdList(files) {
    console.log(`\n${ANSI.bold}${ANSI.cyan}━━━ All ${files.length} Library Files ━━━${ANSI.reset}\n`);
    for (const f of files) {
        const idx = files.indexOf(f) + 1;
        const num = `${idx}`.padStart(2, ' ');
        console.log(`  ${ANSI.blue}[${num}]${ANSI.reset} ${ANSI.bold}${f.display}${ANSI.reset}`);
        console.log(`       ${ANSI.dim}${f.name}${ANSI.reset}`);
        if (f.topics.length > 0) {
            const tags = f.topics.slice(0, 4).join(', ');
            console.log(`       ${ANSI.dim}Topics: ${tags}${ANSI.reset}`);
        }
        console.log('');
    }
    console.log(`\n${ANSI.dim}Use: npx tsx backend/src/librarian.ts read <name> to view a file${ANSI.reset}\n`);
}
function cmdRead(files, query) {
    const lowerQuery = query.toLowerCase();
    const file = files.find((f) => f.name.toLowerCase().includes(lowerQuery) ||
        f.display.toLowerCase().includes(lowerQuery) ||
        f.name.replace(/\.md$/, '') === lowerQuery);
    if (!file) {
        console.log(`${ANSI.red}✗ File not found matching "${query}".${ANSI.reset}`);
        console.log(`${ANSI.dim}Use 'list' to see available files, or try a partial name.${ANSI.reset}`);
        process.exit(1);
    }
    // Print full content as a pager
    const lines = file.content.split('\n');
    console.log(`${ANSI.bold}${ANSI.bgBlue}${ANSI.white}  📖 ${file.display} (${file.name})  ${ANSI.reset}\n`);
    for (const line of lines) {
        if (line.startsWith('#')) {
            const level = line.match(/^#+/)?.[0].length || 1;
            const title = line.replace(/^#+\s*/, '');
            if (level === 1) {
                console.log(`\n${ANSI.bold}${ANSI.cyan}${title}${ANSI.reset}\n`);
            }
            else if (level === 2) {
                console.log(`\n${ANSI.bold}${ANSI.blue}${title}${ANSI.reset}\n`);
            }
            else if (level === 3) {
                console.log(`\n${ANSI.bold}${title}${ANSI.reset}`);
            }
        }
        else if (line.startsWith('|')) {
            // Table rows
            console.log(`${ANSI.dim}${line}${ANSI.reset}`);
        }
        else if (line.startsWith('```')) {
            console.log(`${ANSI.dim}${line}${ANSI.reset}`);
        }
        else if (line.trim().startsWith('>')) {
            console.log(`${ANSI.italic}${ANSI.green}${line}${ANSI.reset}`);
        }
        else {
            console.log(line);
        }
    }
}
// ─── Help ──────────────────────────────────────────────────────────────
function cmdHelp() {
    console.log(`
${ANSI.bold}${ANSI.cyan}📚  Librarian — Reference Library TUI Search Tool${ANSI.reset}

${ANSI.bold}Usage:${ANSI.reset}
  ${ANSI.green}npx tsx backend/src/librarian.ts${ANSI.reset}              Interactive TUI (default)
  ${ANSI.green}npx tsx backend/src/librarian.ts search <query>${ANSI.reset}  One-shot search
  ${ANSI.green}npx tsx backend/src/librarian.ts list${ANSI.reset}            List all files
  ${ANSI.green}npx tsx backend/src/librarian.ts read <name>${ANSI.reset}     View a file
  ${ANSI.green}npx tsx backend/src/librarian.ts help${ANSI.reset}            Show this help

${ANSI.bold}Interactive mode commands:${ANSI.reset}
  ${ANSI.cyan}<query>${ANSI.reset}     — Search the library (e.g. "kubernetes deployment")
  ${ANSI.cyan}list${ANSI.reset}        — Show all available files
  ${ANSI.cyan}read <n>${ANSI.reset}    — Read file # (from search results or list)
  ${ANSI.cyan}help${ANSI.reset}        — Show this help
  ${ANSI.cyan}q${ANSI.reset}           — Quit

${ANSI.bold}Examples:${ANSI.reset}
  npx tsx backend/src/librarian.ts search "database indexing"
  npx tsx backend/src/librarian.ts search "kubernetes pod deployment"
  npx tsx backend/src/librarian.ts read database-design-patterns
  npx tsx backend/src/librarian.ts list
`);
}
// ─── Entry point ───────────────────────────────────────────────────────
async function main() {
    const args = process.argv.slice(2);
    const command = args[0]?.toLowerCase() || 'tui';
    const files = loadLibraryFiles();
    switch (command) {
        case 'tui':
        case undefined:
        case '':
            await interactiveTUI(files);
            break;
        case 'search':
            if (!args[1]) {
                console.error(`${ANSI.red}✗ Usage: librarian search <query>${ANSI.reset}`);
                process.exit(1);
            }
            cmdSearch(files, args.slice(1).join(' '));
            break;
        case 'list':
        case 'ls':
            cmdList(files);
            break;
        case 'read':
        case 'view':
            if (!args[1]) {
                console.error(`${ANSI.red}✗ Usage: librarian read <file-name>${ANSI.reset}`);
                process.exit(1);
            }
            cmdRead(files, args.slice(1).join(' '));
            break;
        case 'help':
        case '--help':
        case '-h':
            cmdHelp();
            break;
        default:
            // If it doesn't match a command, treat it as a search query
            cmdSearch(files, args.join(' '));
            break;
    }
}
main().catch((err) => {
    console.error(`${ANSI.red}✗ Fatal error: ${err.message}${ANSI.reset}`);
    process.exit(1);
});
