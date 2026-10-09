/**
 * Map an OSType to its recommended native language for code generation.
 */
export function getNativeLanguage(os, linuxDistro) {
    switch (os) {
        case 'linux': return 'go';
        case 'windows': return 'csharp';
        case 'mac': return 'swift';
        case 'ios': return 'swift';
        case 'android': return 'kotlin';
    }
}
/**
 * Canonical list of FILE node types a plan/scan may assign to a generated
 * file. Excludes the project-root `master` node (not a file). Single source of
 * truth for the planner (`routes/architect.ts`) and the scanner
 * (`routes/scanner.ts`) — previously each redeclared its own list and drifted
 * (scanner silently dropped `gui-layout`).
 */
export const PLAN_NODE_TYPES = ['input', 'output', 'logic', 'api', 'database', 'ui', 'ui-functions', 'gui-layout'];
