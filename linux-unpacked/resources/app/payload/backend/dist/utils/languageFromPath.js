/**
 * languageFromPath — deterministic file-path → language.
 *
 * The ONE mapping shared by:
 *   - the learning engine (which pattern language a captured file belongs to)
 *   - the scaffold self-improvement loop's adherence scorer (which checks apply
 *     to a generated file — the harness checks are TypeScript-shaped, so scoring
 *     a Go/Rust/C#/… scaffold needs to know the file is not TS)
 *
 * Kept dependency-free (no disk, no config) so importing it can never make the
 * pure scorer side-effectful or create an import cycle.
 */
export function languageFromPath(p) {
    const base = (p.split('/').pop() || p).toLowerCase();
    if (base === 'dockerfile')
        return 'dockerfile';
    const ext = (p.split('.').pop() || '').toLowerCase();
    switch (ext) {
        case 'ts':
        case 'tsx': return 'typescript';
        case 'js':
        case 'jsx': return 'javascript';
        case 'py': return 'python';
        case 'go': return 'go';
        case 'rs': return 'rust';
        case 'java': return 'java';
        case 'c':
        case 'h': return 'c';
        case 'cpp':
        case 'cc':
        case 'cxx':
        case 'hpp':
        case 'hh': return 'cpp';
        case 'cs': return 'csharp';
        case 'kt':
        case 'kts': return 'kotlin';
        case 'swift': return 'swift';
        case 'php': return 'php';
        case 'rb': return 'ruby';
        case 'html': return 'html';
        case 'css': return 'css';
        case 'json': return 'json';
        case 'md': return 'markdown';
        case 'sh': return 'bash';
        case 'sql': return 'sql';
        default: return 'typescript';
    }
}
