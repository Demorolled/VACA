/**
 * Error Correction Engine
 * ========================
 * Implements the generate → validate → fix → retry loop.
 *
 * Flow:
 *   1. Take generated code + project context
 *   2. Run sandbox validation (typecheck / syntax check)
 *   3. If validation fails, send errors + code to secondary LLM for fixing
 *   4. Apply fix and retry (max 3 attempts)
 *   5. Track fix history for learning
 */
import { runSandbox, detectLanguage } from './dockerRunner.js';
import { AITranslator } from '../ai/translator.js';
// ─── Fix Prompt Builder ──────────────────────────────────────────────────
function buildFixPrompt(code, errors, projectName, goal, reviewComments, reviewSeverity) {
    const ctx = projectName ? `\nProject: ${projectName}` : '';
    const gl = goal ? `\nGoal: ${goal}` : '';
    // If review comments are provided, include them as targeted guidance
    const reviewSection = reviewComments
        ? `\n\nAdditional Review Findings (must fix these):\n${reviewComments}\n\nThese were flagged by an automated code review as ${reviewSeverity || 'critical'} issues. They MUST be fixed in the corrected code.`
        : '';
    return `You are an expert code debugger. The following generated code has errors that need to be fixed.${reviewSection}

Code:${ctx}${gl}

\`\`\`
${code}
\`\`\`

Error Output:
\`\`\`
${errors.join('\n')}
\`\`\`

TASK:
1. Analyze each error and determine the root cause
2. Fix ALL errors in the code${reviewComments ? '\n3. Also fix the specific issues highlighted in the Review Findings section above\n4. Return ONLY the corrected code — no explanations, no markdown fences\n5. Preserve the original structure and logic of the code' : '\n3. Return ONLY the corrected code — no explanations, no markdown fences\n4. Preserve the original structure and logic of the code'}

Return the complete corrected file.`;
}
// ─── Error Correction Loop ────────────────────────────────────────────────
/**
 * Run the full generate → validate → fix → retry loop.
 * Returns the final fixed code and a history of fix attempts.
 */
export async function runErrorCorrection(req) {
    const startTime = Date.now();
    const maxAttempts = req.maxAttempts || 3;
    const attempts = [];
    const translator = new AITranslator();
    let currentCode = req.code;
    let currentLanguage = req.language || 'typescript';
    let lastResult = null;
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        // Validate current code
        lastResult = await runSandbox(currentCode, currentLanguage);
        if (lastResult.success) {
            // Code is valid — done!
            return {
                success: true,
                finalCode: currentCode,
                language: currentLanguage,
                attempts,
                totalTimeMs: Date.now() - startTime,
            };
        }
        // Code has errors — ask LLM to fix it
        const errorText = lastResult.errors.length > 0
            ? lastResult.errors
            : [lastResult.output || 'Unknown validation error'];
        // Build the fix prompt — include review comments if available
        const fixPrompt = buildFixPrompt(currentCode, errorText, req.projectName, req.goal, req.reviewComments, req.reviewSeverity);
        try {
            // Use the secondary (stronger) model for fixing — better at debugging
            const fixedCode = await translator.reason(fixPrompt, undefined, { maxTokens: 4096 });
            // Clean up the fixed code — remove markdown fences if present
            const cleaned = cleanFixedCode(fixedCode);
            if (cleaned && cleaned.length > 20) {
                currentCode = cleaned;
            }
            // Update language if it changed
            const detectedLang = detectLanguage(cleaned);
            if (detectedLang)
                currentLanguage = detectedLang;
            attempts.push({
                attempt,
                error: errorText.join('\n'),
                fix: cleaned,
                result: lastResult,
            });
            console.log(`[errorCorrection] Attempt ${attempt}/${maxAttempts}: Fixed code (${cleaned.length} chars)`);
        }
        catch (err) {
            // LLM fix failed — push a placeholder and continue
            attempts.push({
                attempt,
                error: errorText.join('\n'),
                fix: currentCode,
                result: lastResult,
            });
            console.error(`[errorCorrection] LLM fix failed on attempt ${attempt}: ${err.message}`);
        }
    }
    // All attempts exhausted
    return {
        success: false,
        finalCode: currentCode,
        language: currentLanguage,
        attempts,
        totalTimeMs: Date.now() - startTime,
    };
}
// ─── Helpers ──────────────────────────────────────────────────────────────
function cleanFixedCode(code) {
    let cleaned = code.trim();
    // Remove markdown code fences
    cleaned = cleaned.replace(/^```[\w]*\n?/gm, '');
    cleaned = cleaned.replace(/\n?```$/gm, '');
    // Remove any leading/trailing explanation text
    // (Keep only if it looks like code — has brackets, parens, etc.)
    const lines = cleaned.split('\n');
    const codeLines = lines.filter(l => l.includes('{') || l.includes('(') || l.includes('=') ||
        l.includes('import') || l.includes('export') || l.includes('function') ||
        l.includes('const ') || l.includes('let ') || l.includes('var '));
    if (codeLines.length >= lines.length * 0.5) {
        return cleaned;
    }
    // Try to extract just the code block if one exists
    const codeBlock = cleaned.match(/```[\w]*\n?([\s\S]*?)```/);
    if (codeBlock) {
        return codeBlock[1].trim();
    }
    return cleaned;
}
/**
 * Format fix history for display / logging.
 */
export function formatFixReport(result) {
    const lines = [];
    lines.push(`╔══════════════════════════════════════════════╗`);
    lines.push(`║      Error Correction Report                ║`);
    lines.push(`╚══════════════════════════════════════════════╝`);
    lines.push(`Status: ${result.success ? '✅ Fixed' : '❌ Failed'}`);
    lines.push(`Attempts: ${result.attempts.length}`);
    lines.push(`Time: ${result.totalTimeMs}ms`);
    lines.push(`Language: ${result.language}`);
    lines.push(`Final code: ${result.finalCode.length} chars`);
    lines.push('');
    for (const a of result.attempts) {
        lines.push(`── Attempt ${a.attempt} ──`);
        lines.push(`Error: ${a.error.slice(0, 200)}`);
        lines.push(`Fix: ${a.fix.length} chars`);
        lines.push('');
    }
    return lines.join('\n');
}
