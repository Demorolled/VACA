/**
 * Generate the full content for placeholder files for a given node.
 * Returns an array of { name, content } objects suitable for writing to disk
 * or sending over the API.
 */
export function generateNodePlaceholderFiles(node) {
    const label = node.data.label || 'Untitled Node';
    const desc = node.data.description || '';
    const safeId = sanitizeName(label).replace(/-([a-z])/g, (_, c) => c.toUpperCase()).replace(/-/g, '_') || 'Component';
    const capId = safeId.charAt(0).toUpperCase() + safeId.slice(1);
    const ext = node.data.language === 'python' ? 'py'
        : node.data.language === 'go' ? 'go'
            : node.data.language === 'rust' ? 'rs'
                : 'ts';
    const sharedReadme = (typeLabel, files, todos) => `# ${label} \u2014 ${typeLabel} Placeholder\n\n${desc}\n\n## Files\n${files.map((f) => `- \`${f}\``).join('\n')}\n\n## TODO\n${todos.map((t) => `- [ ] ${t}`).join('\n')}\n`;
    switch (node.type) {
        case 'database':
            return [
                {
                    name: 'schema.sql',
                    content: `-- =================================================================\n-- DATABASE PLACEHOLDER \u2014 ${label}\n-- Description: ${desc}\n-- TODO: Define your database schema here\n-- =================================================================\n\n-- Example table structure\nCREATE TABLE IF NOT EXISTS example (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n);\n\n-- Indices\n-- CREATE INDEX idx_example_column ON example(column);\n\n-- TODO: Add your actual tables, relationships, and constraints\n`,
                },
                {
                    name: 'seed.sql',
                    content: `-- =================================================================\n-- SEED DATA \u2014 ${label}\n-- TODO: Add initial seed data for development/testing\n-- =================================================================\n\n-- INSERT INTO example (column) VALUES ('value');\n`,
                },
                {
                    name: 'config.json',
                    content: JSON.stringify({ node: label, type: 'database', description: desc, connection: { host: 'localhost', port: 5432, database: 'myapp' }, status: 'placeholder' }, null, 2),
                },
                {
                    name: 'README.md',
                    content: sharedReadme('Database', ['schema.sql', 'seed.sql', 'config.json'], [
                        'Design the database schema', 'Create migration scripts', 'Set up connection pooling', 'Write CRUD operations',
                    ]),
                },
            ];
        case 'api':
            return [
                {
                    name: `routes.${ext}`,
                    content: `// =================================================================\n// API PLACEHOLDER \u2014 ${label}\n// Description: ${desc}\n// TODO: Define API endpoints and request/response types\n// =================================================================\n\n// Request/response types\n// TODO: Define types here\n\nexport const routes = [\n  // { method: 'GET', path: '/api/resource', handler: getResource },\n] as const;\n`,
                },
                {
                    name: `client.${ext}`,
                    content: `// =================================================================\n// API CLIENT PLACEHOLDER \u2014 ${label}\n// TODO: Implement API client functions\n// =================================================================\n\nexport async function fetch${capId}(): Promise<unknown> {\n  // TODO: Implement API call\n  throw new Error('Not implemented \u2014 placeholder');\n}\n`,
                },
                {
                    name: 'README.md',
                    content: sharedReadme('API', ['routes.ts', 'client.ts'], [
                        'Define API endpoints', 'Implement request validation', 'Add error handling middleware', 'Write API client functions', 'Add authentication/authorization',
                    ]),
                },
            ];
        case 'ui':
            return [
                {
                    name: `component.${ext === 'ts' ? 'tsx' : ext}`,
                    content: `// =================================================================\n// UI PLACEHOLDER \u2014 ${label}\n// Description: ${desc}\n// TODO: Implement the UI component\n// =================================================================\n\nexport interface ${capId}Props {\n  // TODO: Define component props\n}\n\nexport function ${capId}(props: ${capId}Props) {\n  // TODO: Implement render logic\n  return null;\n}\n`,
                },
                {
                    name: 'styles.css',
                    content: `/* =================================================================\n   UI STYLES \u2014 ${label}\n   TODO: Add component styles\n   ================================================================= */\n\n.placeholder-container {\n  /* TODO: Add layout styles */\n}\n`,
                },
                {
                    name: 'README.md',
                    content: sharedReadme('UI', ['component.tsx', 'styles.css'], [
                        'Design the component layout', 'Implement user interactions', 'Add responsive styles', 'Handle loading/error/empty states',
                    ]),
                },
            ];
        case 'logic':
            return [
                {
                    name: `service.${ext}`,
                    content: `// =================================================================\n// LOGIC PLACEHOLDER \u2014 ${label}\n// Description: ${desc}\n// TODO: Implement business logic\n// =================================================================\n\nexport function process${capId}(data: unknown): unknown {\n  // TODO: Implement core processing logic\n  // Include error handling, edge cases, and validation\n  return data;\n}\n`,
                },
                {
                    name: `helpers.${ext}`,
                    content: `// =================================================================\n// HELPERS \u2014 ${label}\n// TODO: Add helper/utility functions\n// =================================================================\n\n// export function formatOutput(raw: unknown): string {\n//   // TODO: Implement formatting\n//   return String(raw);\n// }\n`,
                },
                {
                    name: 'README.md',
                    content: sharedReadme('Logic', ['service.ts', 'helpers.ts'], [
                        'Implement core business logic', 'Handle edge cases and errors', 'Add unit tests', 'Optimize performance bottlenecks',
                    ]),
                },
            ];
        case 'input':
            return [
                {
                    name: `validators.${ext}`,
                    content: `// =================================================================\n// INPUT PLACEHOLDER \u2014 ${label}\n// Description: ${desc}\n// TODO: Implement input validation\n// =================================================================\n\nexport function validate${capId}(input: unknown): { valid: boolean; errors: string[] } {\n  // TODO: Add validation rules\n  return { valid: true, errors: [] };\n}\n`,
                },
                {
                    name: `parsers.${ext}`,
                    content: `// =================================================================\n// INPUT PARSERS \u2014 ${label}\n// TODO: Implement input parsing and sanitization\n// =================================================================\n\nexport function parse${capId}(raw: string): unknown {\n  // TODO: Parse and sanitize input\n  return raw.trim();\n}\n`,
                },
                {
                    name: 'README.md',
                    content: sharedReadme('Input', ['validators.ts', 'parsers.ts'], [
                        'Define input validation rules', 'Implement sanitization logic', 'Handle malformed input gracefully',
                    ]),
                },
            ];
        case 'output':
            return [
                {
                    name: `formatters.${ext}`,
                    content: `// =================================================================\n// OUTPUT PLACEHOLDER \u2014 ${label}\n// Description: ${desc}\n// TODO: Implement output formatting\n// =================================================================\n\nexport function format${capId}(data: unknown): string {\n  // TODO: Format output for display/export\n  return JSON.stringify(data, null, 2);\n}\n`,
                },
                {
                    name: 'templates.md',
                    content: `# Output Templates \u2014 ${label}\n\nTODO: Define output templates and display formats\n\n## Layout\n<!-- Describe the output structure here -->\n\n## Examples\n<!-- Add example outputs here -->\n`,
                },
                {
                    name: 'README.md',
                    content: sharedReadme('Output', ['formatters.ts', 'templates.md'], [
                        'Define output format/structure', 'Implement display rendering', 'Add export functionality',
                    ]),
                },
            ];
        case 'master':
            return [
                {
                    name: 'config.json',
                    content: JSON.stringify({ node: label, type: 'master', description: desc, app: { name: label, version: '1.0.0' }, status: 'placeholder' }, null, 2),
                },
                {
                    name: 'manifest.json',
                    content: JSON.stringify({ name: label, description: desc, version: '1.0.0', dependencies: [], status: 'placeholder' }, null, 2),
                },
                {
                    name: 'README.md',
                    content: sharedReadme('App Entry', ['config.json', 'manifest.json'], [
                        'Configure the application entry point', 'Define application-wide settings', 'Set up error boundaries and logging',
                    ]),
                },
            ];
        case 'ui-functions':
            return [
                {
                    name: `controls.${ext}`,
                    content: `// =================================================================\n// UI CONTROLS PLACEHOLDER \u2014 ${label}\n// Description: ${desc}\n// TODO: Implement UI controls and event handlers\n// =================================================================\n\nexport interface ${capId}Control {\n  id: string;\n  label: string;\n  action: () => void;\n}\n\nexport const ${safeId}Controls: ${capId}Control[] = [\n  // { id: 'btn-1', label: 'Click Me', action: () => {} },\n];\n`,
                },
                {
                    name: 'README.md',
                    content: sharedReadme('UI Controls', ['controls.ts'], [
                        'Define button/action lists', 'Implement event handlers', 'Wire up user interaction logic',
                    ]),
                },
            ];
        default:
            return [
                {
                    name: 'README.md',
                    content: `# ${label} \u2014 Placeholder\n\n${desc}\n\n**Type:** ${node.type}\n\nTODO: Implement this node.\n`,
                },
            ];
    }
}
/**
 * Returns the list of placeholder file names a node of the given type expects.
 *
 * This is the single source of truth for file name mapping, used by both the
 * architect route (to pre-populate resourceFiles on newly generated nodes)
 * and the scaffolder (to generate the actual skeleton files).
 */
export function getPlaceholderFileNames(nodeType, language) {
    const ext = language === 'python' ? 'py'
        : language === 'go' ? 'go'
            : language === 'rust' ? 'rs'
                : 'ts';
    switch (nodeType) {
        case 'database':
            return ['schema.sql', 'seed.sql', 'config.json', 'README.md'];
        case 'api':
            return [`routes.${ext}`, `client.${ext}`, 'README.md'];
        case 'ui':
            return [`component.${ext === 'ts' ? 'tsx' : ext}`, 'styles.css', 'README.md'];
        case 'logic':
            return [`service.${ext}`, `helpers.${ext}`, 'README.md'];
        case 'input':
            return [`validators.${ext}`, `parsers.${ext}`, 'README.md'];
        case 'output':
            return [`formatters.${ext}`, 'templates.md', 'README.md'];
        case 'master':
            return ['config.json', 'manifest.json', 'README.md'];
        case 'ui-functions':
            return [`controls.${ext}`, 'README.md'];
        default:
            return ['README.md'];
    }
}
/** Sanitize a name string for use in file paths and identifiers. */
function sanitizeName(name) {
    return name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        || 'untitled';
}
