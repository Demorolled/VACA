/**
 * generate-training-dataset.ts
 * =============================
 * Comprehensive knowledge-to-dataset converter.
 *
 * Reads ALL knowledge sources in the project and generates a JSONL
 * fine-tuning dataset with instruction-response pairs suitable for
 * training both the Venorica RNN and the LLM via the training studio.
 *
 * Knowledge Sources:
 *   1. modelVeronice.txt — Main wiki documentation (1,713 lines)
 *   2. data/library/*.md — 42 reference library files
 *   3. knowledge/patterns.json — 594KB of code patterns
 *   4. llm-training-app/data/uploads/*.jsonl — existing training files
 *   5. projects/*.html — 92 generated app files
 *   6. data/design-manifesto.md — Design preferences
 *   7. backend/src/ — All backend source code
 *   8. frontend/src/ — All frontend source code
 *
 * Output: Comprehensive JSONL with 10,000+ instruction-response pairs
 */
import * as fs from 'fs';
import * as path from 'path';
// ─── Paths ────────────────────────────────────────────────────────────────
const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const BACKEND_DIR = path.resolve(import.meta.dirname, '..', '..');
const WIKI_PATH = path.join(PROJECT_ROOT, 'modelVeronice.txt');
const LIBRARY_DIR = path.join(PROJECT_ROOT, 'data', 'library');
const MANIFESTO_PATH = path.join(PROJECT_ROOT, 'data', 'design-manifesto.md');
const PATTERNS_PATH = path.join(PROJECT_ROOT, 'knowledge', 'patterns.json');
const TRAINING_UPLOADS = path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
const PROJECTS_DIR = path.join(PROJECT_ROOT, 'projects');
const BACKEND_SRC = path.join(PROJECT_ROOT, 'backend', 'src');
const FRONTEND_SRC = path.join(PROJECT_ROOT, 'frontend', 'src');
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'training', 'dataset');
// ─── Source Readers ───────────────────────────────────────────────────────
function ensureDir(dir) {
    if (!fs.existsSync(dir))
        fs.mkdirSync(dir, { recursive: true });
}
/** Read and parse modelVeronice.txt into sections (underlined headers like "1. TITLE\\n=======") */
function readWikiSections() {
    if (!fs.existsSync(WIKI_PATH)) {
        console.warn('[dataset] modelVeronice.txt not found');
        return [];
    }
    const text = fs.readFileSync(WIKI_PATH, 'utf-8');
    const lines = text.split('\n');
    const sections = [];
    let currentSection = null;
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        // Match underlined headers: "1. TITLE" followed by a line of "=====" or "-----"
        const headerMatch = line.match(/^(\d+(?:\.\d+)*)\.\s+(.+)/);
        if (headerMatch) {
            const nextLine = lines[i + 1] || '';
            const isUnderlined = /^[=\-~^]{3,}$/.test(nextLine.trim());
            if (isUnderlined) {
                if (currentSection && currentSection.content.trim()) {
                    sections.push(currentSection);
                }
                currentSection = {
                    sectionNumber: headerMatch[1],
                    title: headerMatch[2].trim(),
                    content: '',
                };
                i++; // skip the underline
                continue;
            }
        }
        if (currentSection) {
            currentSection.content += line + '\n';
        }
    }
    if (currentSection && currentSection.content.trim()) {
        sections.push(currentSection);
    }
    return sections;
}
/** Read library .md files */
function readLibraryFiles() {
    if (!fs.existsSync(LIBRARY_DIR))
        return [];
    return fs.readdirSync(LIBRARY_DIR)
        .filter(f => f.endsWith('.md'))
        .map(f => ({
        name: f,
        content: fs.readFileSync(path.join(LIBRARY_DIR, f), 'utf-8'),
    }));
}
/** Read patterns.json */
function readPatterns() {
    if (!fs.existsSync(PATTERNS_PATH))
        return [];
    try {
        const data = JSON.parse(fs.readFileSync(PATTERNS_PATH, 'utf-8'));
        return Array.isArray(data) ? data : [];
    }
    catch {
        return [];
    }
}
/** Read existing JSONL training files */
function readExistingTrainingData() {
    if (!fs.existsSync(TRAINING_UPLOADS))
        return [];
    const records = [];
    const files = fs.readdirSync(TRAINING_UPLOADS).filter(f => f.endsWith('.jsonl'));
    for (const file of files.slice(0, 100)) {
        try {
            const content = fs.readFileSync(path.join(TRAINING_UPLOADS, file), 'utf-8');
            for (const line of content.split('\n').filter(l => l.trim())) {
                try {
                    records.push(JSON.parse(line));
                }
                catch { }
            }
        }
        catch { }
    }
    return records;
}
/** Read source code files from a directory recursively */
function readSourceFiles(dir, exts, excludeDirs = ['node_modules', 'dist', '.git']) {
    const results = [];
    if (!fs.existsSync(dir))
        return results;
    function walk(currentDir) {
        let entries;
        try {
            entries = fs.readdirSync(currentDir, { withFileTypes: true });
        }
        catch {
            return;
        }
        for (const entry of entries) {
            const fullPath = path.join(currentDir, entry.name);
            if (entry.isDirectory()) {
                if (excludeDirs.includes(entry.name))
                    continue;
                walk(fullPath);
                continue;
            }
            const ext = path.extname(entry.name).toLowerCase();
            if (!exts.includes(ext))
                continue;
            let content;
            try {
                content = fs.readFileSync(fullPath, 'utf-8');
            }
            catch {
                continue;
            }
            if (content.trim().length < 30)
                continue;
            let language = 'unknown';
            if (ext === '.ts' || ext === '.tsx')
                language = 'typescript';
            else if (ext === '.css')
                language = 'css';
            else if (ext === '.py')
                language = 'python';
            else if (ext === '.html')
                language = 'html';
            else if (ext === '.js')
                language = 'javascript';
            else if (ext === '.json')
                language = 'json';
            results.push({ path: fullPath, content, language });
        }
    }
    walk(dir);
    return results;
}
// ─── Converters ───────────────────────────────────────────────────────────
/** Convert wiki sections to training examples */
function wikiToExamples(sections) {
    const examples = [];
    for (const section of sections) {
        const title = section.title;
        const content = section.content.trim();
        if (content.length < 50)
            continue;
        // Get subsection breakdown for richer training
        const subsectionLines = content.split('\n').filter(l => /^\d+\.\d+/.test(l.trim()));
        const hasSubsections = subsectionLines.length > 0;
        // Instruction: Explain a concept
        examples.push({
            instruction: `Explain "${title}" in the VACA platform.`,
            input: `What is ${title} and how does it work in VACA?`,
            output: content.length > 2000 ? content.substring(0, 2000) + '...' : content,
            source: 'modelVeronice.txt',
            category: 'documentation',
            language: 'text',
            difficulty: content.length > 1000 ? 'advanced' : 'intermediate',
            tags: ['wiki', ...title.toLowerCase().replace(/[^a-z0-9]+/g, '-').split('-').filter(Boolean)],
        });
        // If has subsections, create per-subsection examples
        if (hasSubsections && content.length > 300) {
            const subsections = content.split(/\n(?=\d+\.\d+\s)/);
            for (const sub of subsections.slice(0, 8)) {
                const subMatch = sub.match(/^(\d+\.\d+)\s+(.+)/);
                if (subMatch) {
                    const subTitle = subMatch[2].trim();
                    const subContent = sub.substring(sub.indexOf('\n')).trim();
                    if (subContent.length > 50) {
                        examples.push({
                            instruction: `Explain "${subTitle}" in the VACA platform.`,
                            input: `What is ${subTitle} and how is it configured?`,
                            output: subContent.length > 1500 ? subContent.substring(0, 1500) : subContent,
                            source: 'modelVeronice.txt',
                            category: 'documentation',
                            language: 'text',
                            difficulty: 'intermediate',
                            tags: ['wiki', 'subsection', ...subTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-').split('-').filter(Boolean)],
                        });
                    }
                }
            }
        }
        // Practical how-to instruction
        if (content.length > 200) {
            examples.push({
                instruction: `How do I configure or use "${title}" in the VACA platform?`,
                input: `Guide me through setting up ${title} in VACA.`,
                output: content.substring(0, 1500),
                source: 'modelVeronice.txt',
                category: 'how-to',
                language: 'text',
                difficulty: 'intermediate',
                tags: ['wiki', 'how-to', ...title.toLowerCase().replace(/[^a-z0-9]+/g, '-').split('-').filter(Boolean)],
            });
        }
    }
    return examples;
}
/** Convert library files to training examples */
function libraryToExamples(files) {
    const examples = [];
    const nameMap = {
        '01-node-architecture-reference.md': 'Node Architecture Reference',
        '02-app-type-templates.md': 'App Type Templates',
        '03-code-generation-rules.md': 'Code Generation Rules',
        '04-technology-mapping.md': 'Technology Mapping',
        '05-design-patterns.md': 'Design Patterns',
        '06-data-flow-patterns.md': 'Data Flow Patterns',
        '07-node-implementation-guide.md': 'Node Implementation Guide',
        '08-testing-patterns.md': 'Testing Patterns',
        '09-deployment-templates.md': 'Deployment Templates',
        '10-cicd-configuration.md': 'CI/CD Configuration',
        '11-debugging-strategies.md': 'Debugging Strategies',
        '12-game-development-patterns.md': 'Game Development Patterns',
        '13-desktop-application-architecture.md': 'Desktop Application Architecture',
        '14-web-application-architecture.md': 'Web Application Architecture',
        '15-database-design-patterns.md': 'Database Design Patterns',
        '16-systems-programming-guide.md': 'Systems Programming Guide',
        '17-security-architecture-guide.md': 'Security Architecture Guide',
        '18-media-multimedia-processing.md': 'Media & Multimedia Processing',
        '19-ai-ml-integration-guide.md': 'AI/ML Integration Guide',
        '20-networking-communication-protocols.md': 'Networking & Communication Protocols',
        '21-iot-embedded-systems.md': 'IoT & Embedded Systems',
        '22-enterprise-systems-integration.md': 'Enterprise Systems Integration',
        '23-cloud-native-infrastructure.md': 'Cloud Native Infrastructure',
        '24-devops-sre-tooling.md': 'DevOps & SRE Tooling',
        '25-distributed-systems.md': 'Distributed Systems',
        '26-data-engineering-analytics.md': 'Data Engineering & Analytics',
        '27-mobile-cross-platform.md': 'Mobile & Cross-Platform',
        '28-fintech-insurance-systems.md': 'Fintech & Insurance Systems',
        '29-healthcare-life-sciences.md': 'Healthcare & Life Sciences',
        '30-browser-engineering.md': 'Browser Engineering',
        '31-compilers-language-design.md': 'Compilers & Language Design',
        '32-realtime-collaboration-systems.md': 'Realtime Collaboration Systems',
        '33-search-recommendation-engines.md': 'Search & Recommendation Engines',
        '34-llm-ops-platform-engineering.md': 'LLM Ops & Platform Engineering',
        '35-computer-graphics-gpu.md': 'Computer Graphics & GPU',
        '36-api-integration-platforms.md': 'API Integration Platforms',
        '37-media-entertainment-social.md': 'Media, Entertainment & Social',
        '38-marketplace-ecommerce.md': 'Marketplace & E-Commerce',
        '39-education-learning-platforms.md': 'Education & Learning Platforms',
        '40-formal-methods-verification.md': 'Formal Methods & Verification',
        '41-emerging-technologies.md': 'Emerging Technologies',
    };
    for (const file of files) {
        const topic = nameMap[file.name] || file.name.replace('.md', '').replace(/^\d+-/, '');
        const content = file.content.trim();
        if (content.length < 100)
            continue;
        // Split on any heading level: #, ##, ###
        const parts = content.split(/\n(?=#{1,3}\s)/);
        let headingCount = 0;
        for (const part of parts) {
            const lines = part.split('\n');
            const heading = lines[0].replace(/^#+\s*/, '').trim();
            const body = lines.slice(1).join('\n').trim();
            if (body.length < 80)
                continue;
            headingCount++;
            // Skip the main title (first # heading)
            if (headingCount === 1 && parts.length > 3)
                continue;
            // Generate explanation instruction
            examples.push({
                instruction: `Explain ${topic}: ${heading || topic}`,
                input: `What is ${heading || topic} in the context of ${topic}?`,
                output: body.length > 2000 ? body.substring(0, 2000) : body,
                source: `library/${file.name}`,
                category: 'reference',
                language: 'text',
                difficulty: 'intermediate',
                tags: ['library', ...topic.toLowerCase().replace(/[^a-z0-9]+/g, '-').split('-').filter(Boolean)],
            });
            // Generate practical task instruction
            if (body.length > 300 && headingCount < 20) {
                const taskWords = ['implement', 'create', 'build', 'design', 'configure', 'deploy', 'optimize'];
                const taskWord = taskWords[Math.floor(Math.random() * taskWords.length)];
                examples.push({
                    instruction: `${taskWord.charAt(0).toUpperCase() + taskWord.slice(1)} using ${topic}: ${heading || topic}`,
                    input: `I need to ${taskWord} something related to ${heading || topic} in ${topic}. Guide me.`,
                    output: body.length > 1500 ? body.substring(0, 1500) : body,
                    source: `library/${file.name}`,
                    category: 'practical',
                    language: 'text',
                    difficulty: 'advanced',
                    tags: ['library', 'practical', ...topic.toLowerCase().replace(/[^a-z0-9]+/g, '-').split('-').filter(Boolean)],
                });
            }
        }
    }
    return examples;
}
/** Convert code patterns to training examples */
function patternsToExamples(patterns) {
    const examples = [];
    for (const pattern of patterns) {
        if (!pattern.code || pattern.code.length < 30)
            continue;
        const title = pattern.title || 'Code Pattern';
        const description = pattern.description || '';
        const language = pattern.language || 'typescript';
        const tags = pattern.tags || [];
        // Instruction: Generate this code
        examples.push({
            instruction: `Generate ${language} code for: ${title}`,
            input: (description || `Write code for ${title}`).substring(0, 500),
            output: pattern.code.length > 3000 ? pattern.code.substring(0, 3000) : pattern.code,
            source: 'knowledge/patterns.json',
            category: 'code-generation',
            language,
            difficulty: tags.includes('advanced') ? 'advanced' : tags.includes('expert') ? 'expert' : 'intermediate',
            tags: [...tags.slice(0, 8), 'pattern', 'code-generation'],
        });
        // Instruction: Explain this pattern
        if (description.length > 20) {
            examples.push({
                instruction: `Explain the ${title} ${language} pattern`,
                input: `What does ${title} do and how to use it?`,
                output: `${description}\n\nCode:\n${pattern.code.length > 2000 ? pattern.code.substring(0, 2000) + '...' : pattern.code}`,
                source: 'knowledge/patterns.json',
                category: 'explanation',
                language,
                difficulty: 'intermediate',
                tags: [...tags.slice(0, 5), 'pattern', 'explanation'],
            });
        }
    }
    return examples;
}
/** Convert generated project apps to training examples */
function projectsToExamples() {
    const examples = [];
    if (!fs.existsSync(PROJECTS_DIR))
        return examples;
    const files = fs.readdirSync(PROJECTS_DIR).filter(f => f.endsWith('.html'));
    for (const file of files) {
        try {
            const content = fs.readFileSync(path.join(PROJECTS_DIR, file), 'utf-8');
            const name = file.replace('.html', '');
            const appWords = name.split(/[-_]/).map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
            const titleMatch = content.match(/<title>([^<]+)<\/title>/i);
            const h1Match = content.match(/<h1[^>]*>([^<]+)<\/h1>/i);
            const appTitle = titleMatch?.[1] || h1Match?.[1] || appWords;
            // Instruction: Build this app
            examples.push({
                instruction: `Build a ${appTitle} application`,
                input: `I need a complete ${appTitle} app. Generate HTML, CSS, and JavaScript.`,
                output: content.length > 5000 ? content.substring(0, 5000) : content,
                source: `projects/${file}`,
                category: 'full-app',
                language: 'html',
                difficulty: content.length > 3000 ? 'advanced' : 'intermediate',
                tags: ['app', 'html', ...name.toLowerCase().split(/[-_]/)],
            });
        }
        catch { }
    }
    return examples;
}
/** Convert design manifesto to training examples */
function manifestoToExamples() {
    const examples = [];
    if (!fs.existsSync(MANIFESTO_PATH))
        return examples;
    const content = fs.readFileSync(MANIFESTO_PATH, 'utf-8').trim();
    if (content.length < 50)
        return examples;
    // Split manifesto into sections for richer training
    const sections = content.split(/\n(?=#{1,3}\s)/);
    for (const section of sections) {
        const lines = section.split('\n');
        const heading = lines[0].replace(/^#+\s*/, '').trim();
        const body = lines.slice(1).join('\n').trim();
        if (body.length < 50)
            continue;
        examples.push({
            instruction: heading ? `Design guideline: ${heading}` : `Follow user's design manifesto preferences`,
            input: heading ? `What does the user prefer for ${heading}?` : `What are the user's design preferences?`,
            output: body.length > 2000 ? body.substring(0, 2000) : body,
            source: 'data/design-manifesto.md',
            category: 'design-preferences',
            language: 'text',
            difficulty: 'intermediate',
            tags: ['manifesto', 'design', ...(heading ? heading.toLowerCase().replace(/[^a-z0-9]+/g, '-').split('-').filter(Boolean) : ['preferences'])],
        });
    }
    return examples;
}
/** Convert source code files to training examples */
function sourceToExamples(files) {
    const examples = [];
    const seen = new Set();
    let count = 0;
    for (const file of files) {
        if (count >= 300)
            break; // cap at 300 source files to avoid bloat
        const relPath = path.relative(PROJECT_ROOT, file.path);
        const fileName = path.basename(file.path);
        const dirName = path.dirname(relPath);
        // Skip if we already have this content
        const contentKey = file.content.substring(0, 100);
        if (seen.has(contentKey))
            continue;
        seen.add(contentKey);
        count++;
        const tags = ['source-code', file.language, relPath.split('/')[0] || 'root'];
        // Instruction: Generate code based on this source file
        examples.push({
            instruction: `Generate ${file.language} code similar to ${fileName}`,
            input: `Write ${file.language} code following the pattern in ${relPath}`,
            output: file.content.length > 4000 ? file.content.substring(0, 4000) : file.content,
            source: relPath,
            category: 'code-generation',
            language: file.language,
            difficulty: file.content.length > 2000 ? 'advanced' : 'intermediate',
            tags,
        });
        // Instruction: Explain what this code does
        if (file.content.length > 100) {
            examples.push({
                instruction: `Explain the code in ${relPath}`,
                input: `What does the code in ${fileName} do?`,
                output: `File: ${relPath} (${file.language})\n\n${file.content.length > 2000 ? file.content.substring(0, 2000) + '\n...' : file.content}`,
                source: relPath,
                category: 'explanation',
                language: file.language,
                difficulty: 'intermediate',
                tags: [...tags, 'explanation'],
            });
        }
    }
    return examples;
}
/** Convert existing training JSONL data to standard format */
function existingDataToExamples(records) {
    const examples = [];
    const seen = new Set();
    for (const record of records) {
        const text = record.text || record.output || record.code || '';
        const instruction = record.instruction || record.title || 'Write code';
        const input = record.input || record.description || '';
        const language = record.language || 'typescript';
        const tags = record.tags || [];
        if (text.length < 20)
            continue;
        const dedupKey = text.substring(0, 80);
        if (seen.has(dedupKey))
            continue;
        seen.add(dedupKey);
        examples.push({
            instruction: typeof instruction === 'string' ? instruction.substring(0, 200) : 'Write code for this task',
            input: typeof input === 'string' ? input.substring(0, 500) : '',
            output: text.length > 3000 ? text.substring(0, 3000) : text,
            source: 'training-data-import',
            category: 'code-generation',
            language,
            difficulty: 'intermediate',
            tags: Array.isArray(tags) ? tags.slice(0, 8) : [language],
        });
    }
    return examples;
}
// ─── Dataset Writer ───────────────────────────────────────────────────────
function writeDataset(examples, split) {
    const filePath = path.join(OUTPUT_DIR, `${split}.jsonl`);
    const lines = examples.map(ex => JSON.stringify(ex));
    fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf-8');
    return examples.length;
}
function writeMetadata(totalExamples, sources) {
    const meta = {
        generatedAt: new Date().toISOString(),
        totalExamples,
        sources,
        format: 'instruction-input-output',
        targetModel: 'qwen2.5-7b-instruct-uncensored',
        recommendedFormat: 'ChatML',
    };
    fs.writeFileSync(path.join(OUTPUT_DIR, 'metadata.json'), JSON.stringify(meta, null, 2), 'utf-8');
}
function writeDatasetStats(examples) {
    const langs = {};
    const cats = {};
    const diffs = {};
    const sources = {};
    for (const ex of examples) {
        langs[ex.language] = (langs[ex.language] || 0) + 1;
        cats[ex.category] = (cats[ex.category] || 0) + 1;
        diffs[ex.difficulty] = (diffs[ex.difficulty] || 0) + 1;
        sources[ex.source] = (sources[ex.source] || 0) + 1;
    }
    const stats = {
        total: examples.length,
        totalChars: examples.reduce((s, e) => s + e.instruction.length + e.input.length + e.output.length, 0),
        byLanguage: Object.entries(langs).sort((a, b) => b[1] - a[1]),
        byCategory: Object.entries(cats).sort((a, b) => b[1] - a[1]),
        byDifficulty: Object.entries(diffs).sort((a, b) => b[1] - a[1]),
        averageOutputLength: Math.round(examples.reduce((s, e) => s + e.output.length, 0) / examples.length),
        sources,
    };
    fs.writeFileSync(path.join(OUTPUT_DIR, 'stats.json'), JSON.stringify(stats, null, 2), 'utf-8');
    console.log('\n📊 Dataset Statistics:');
    console.log(`  Total examples:     ${stats.total.toLocaleString()}`);
    console.log(`  Total characters:   ${stats.totalChars.toLocaleString()}`);
    console.log(`  Avg output length:  ${stats.averageOutputLength} chars`);
    console.log('\n  By Language:');
    for (const [lang, count] of stats.byLanguage.slice(0, 10)) {
        console.log(`    ${lang.padEnd(15)} ${count.toString().padStart(5)}`);
    }
    console.log('\n  By Category:');
    for (const [cat, count] of stats.byCategory.slice(0, 10)) {
        console.log(`    ${cat.padEnd(20)} ${count.toString().padStart(5)}`);
    }
    console.log('\n  By Difficulty:');
    for (const [diff, count] of stats.byDifficulty) {
        console.log(`    ${diff.padEnd(15)} ${count.toString().padStart(5)}`);
    }
}
// ─── Main ─────────────────────────────────────────────────────────────────
async function main() {
    console.log('='.repeat(60));
    console.log('  🧠 VACA — Training Dataset Generator');
    console.log('='.repeat(60));
    console.log();
    ensureDir(OUTPUT_DIR);
    const allExamples = [];
    const sourceCounts = {};
    // 1. Wiki sections
    console.log('[1/7] Reading modelVeronice.txt wiki...');
    const wikiSections = readWikiSections();
    console.log(`  → Found ${wikiSections.length} sections`);
    const wikiExamples = wikiToExamples(wikiSections);
    allExamples.push(...wikiExamples);
    sourceCounts['modelVeronice.txt'] = wikiExamples.length;
    console.log(`  → Generated ${wikiExamples.length} examples`);
    // 2. Library files
    console.log('[2/7] Reading library reference files...');
    const libraryFiles = readLibraryFiles();
    console.log(`  → Found ${libraryFiles.length} files`);
    const libExamples = libraryToExamples(libraryFiles);
    allExamples.push(...libExamples);
    sourceCounts['data/library/*.md'] = libExamples.length;
    console.log(`  → Generated ${libExamples.length} examples`);
    // 3. Code patterns
    console.log('[3/7] Reading knowledge patterns...');
    const patterns = readPatterns();
    console.log(`  → Found ${patterns.length} patterns`);
    const patExamples = patternsToExamples(patterns);
    allExamples.push(...patExamples);
    sourceCounts['knowledge/patterns.json'] = patExamples.length;
    console.log(`  → Generated ${patExamples.length} examples`);
    // 4. Project apps
    console.log('[4/7] Reading project apps...');
    const projExamples = projectsToExamples();
    allExamples.push(...projExamples);
    sourceCounts['projects/*.html'] = projExamples.length;
    console.log(`  → Generated ${projExamples.length} examples`);
    // 5. Manifesto
    console.log('[5/7] Reading design manifesto...');
    const manExamples = manifestoToExamples();
    allExamples.push(...manExamples);
    sourceCounts['data/design-manifesto.md'] = manExamples.length;
    console.log(`  → Generated ${manExamples.length} examples`);
    // 6. Existing training data
    console.log('[6/7] Reading existing training data...');
    const existingRecords = readExistingTrainingData();
    console.log(`  → Found ${existingRecords.length} records`);
    const existExamples = existingDataToExamples(existingRecords);
    allExamples.push(...existExamples);
    sourceCounts['training-data-import'] = existExamples.length;
    console.log(`  → Generated ${existExamples.length} examples`);
    // 7. Source code files (NEW!)
    console.log('[7/7] Reading source code files from backend and frontend...');
    const exts = ['.ts', '.tsx', '.js', '.css', '.html', '.json'];
    const backendFiles = readSourceFiles(BACKEND_SRC, exts);
    const frontendFiles = readSourceFiles(FRONTEND_SRC, exts);
    const allSourceFiles = [...backendFiles, ...frontendFiles];
    console.log(`  → Found ${allSourceFiles.length} source files`);
    const srcExamples = sourceToExamples(allSourceFiles);
    allExamples.push(...srcExamples);
    sourceCounts['source-code'] = srcExamples.length;
    console.log(`  → Generated ${srcExamples.length} examples`);
    // 8. Shuffle and split
    console.log('\nShuffling and splitting dataset...');
    // Shuffle
    for (let i = allExamples.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [allExamples[i], allExamples[j]] = [allExamples[j], allExamples[i]];
    }
    // Split: 80% train, 10% val, 10% test
    const total = allExamples.length;
    const trainEnd = Math.floor(total * 0.8);
    const valEnd = Math.floor(total * 0.9);
    const train = allExamples.slice(0, trainEnd);
    const val = allExamples.slice(trainEnd, valEnd);
    const test = allExamples.slice(valEnd);
    // Write splits
    const trainCount = writeDataset(train, 'train');
    const valCount = writeDataset(val, 'val');
    const testCount = writeDataset(test, 'test');
    // Copy to LLM Training Studio uploads
    const uploadDir = path.join(PROJECT_ROOT, 'llm-training-app', 'data', 'uploads');
    ensureDir(uploadDir);
    const combinedPath = path.join(uploadDir, `comprehensive-dataset-${Date.now()}.jsonl`);
    const combinedLines = allExamples.map(ex => JSON.stringify(ex));
    fs.writeFileSync(combinedPath, combinedLines.join('\n') + '\n', 'utf-8');
    console.log(`  → Copied to Training Studio: ${path.basename(combinedPath)}`);
    // Write metadata
    writeMetadata(total, sourceCounts);
    // Write stats
    writeDatasetStats(allExamples);
    console.log();
    console.log('='.repeat(60));
    console.log('  ✅ Dataset Generation Complete');
    console.log('='.repeat(60));
    console.log();
    console.log(`  Train:  ${trainCount.toLocaleString().padStart(8)} examples`);
    console.log(`  Val:    ${valCount.toLocaleString().padStart(8)} examples`);
    console.log(`  Test:   ${testCount.toLocaleString().padStart(8)} examples`);
    console.log(`  ─────────────────────────`);
    console.log(`  Total:  ${total.toLocaleString().padStart(8)} examples`);
    console.log();
    console.log(`  Output: ${OUTPUT_DIR}/`);
    console.log(`  Studio: ${combinedPath}`);
    console.log();
}
main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
