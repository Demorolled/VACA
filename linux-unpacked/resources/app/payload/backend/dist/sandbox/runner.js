import { runSandbox, checkSandboxAvailability } from './dockerRunner.js';
import { runErrorCorrection, formatFixReport } from './errorCorrection.js';
export class SandboxRunner {
    /**
     * Run validation in the sandbox (Docker or local).
     * Accepts code and optional language, returns SandboxResult.
     */
    async run(code, os) {
        // Map OSType to language hint
        const language = this.osToLanguage(os || 'linux');
        return runSandbox(code, language);
    }
    /**
     * Run the full error-correction loop: generate → validate → fix → retry.
     * Tries up to 3 times to fix validation errors automatically.
     *
     * @param request - Fix request with code, language, project context
     * @returns SandboxFixResult with final code, attempt history, and report
     */
    async runWithFix(request) {
        const result = await runErrorCorrection(request);
        return {
            success: result.success,
            finalCode: result.finalCode,
            language: result.language,
            fixAttempts: result.attempts.length,
            totalTimeMs: result.totalTimeMs,
            report: formatFixReport(result),
        };
    }
    /**
     * Check what sandbox tools are available on this system.
     */
    getAvailability() {
        return checkSandboxAvailability();
    }
    /**
     * Map an OS name to its default language, or pass through an actual language
     * name untouched. Previously any unrecognized value (e.g. 'go', 'python',
     * 'rust' passed straight from the file generator) fell through to
     * 'typescript' — which made the sandbox compile Go/Python source with tsc
     * and report bogus TS1434 failures on every non-TS file.
     */
    osToLanguage(os) {
        const OS_DEFAULT = {
            linux: 'typescript',
            windows: 'csharp',
            mac: 'swift',
            ios: 'swift',
            android: 'kotlin',
        };
        if (OS_DEFAULT[os])
            return OS_DEFAULT[os];
        return os; // already a language name — pass through
    }
}
