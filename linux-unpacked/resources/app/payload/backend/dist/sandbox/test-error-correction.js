/**
 * Error-Correction Loop Test
 * ===========================
 * Tests the generate → validate → fix → retry pipeline
 * with intentionally broken code snippets.
 *
 * Usage:
 *   cd backend && npx tsx src/sandbox/test-error-correction.ts
 *
 * Requires:
 *   - Node.js with `npx tsc` available (for TypeScript validation)
 *   - Or Python, Go, Rust toolchains for those languages
 */
import { runSandbox, checkSandboxAvailability } from './dockerRunner.js';
import { runErrorCorrection, formatFixReport } from './errorCorrection.js';
// ─── Test Case 1: TypeScript — Wrong type assignment ──────────────────────
const BROKEN_TS_1 = `function greet(name: string): string {
  return "Hello, " + name;
}

const user: string = 42;
console.log(greet(user));
`;
// ─── Test Case 2: TypeScript — Missing imports ──────────────────────────
const BROKEN_TS_2 = `const fs = require('fs');

interface Config {
  port: number;
  host: string;
}

const config: Config = {
  port: "3000",  // type mismatch
  host: "localhost",
};

const server = http.createServer();  // http not imported
server.listen(config.port);
`;
// ─── Test Case 3: Python — Syntax + type errors ─────────────────────────
const BROKEN_PY_1 = `def calculate_total(prices: list) -> float
    total = 0
    for price in prices
        total += price
    return sum

items = [10, 20, "30", 40]
result = calculate_total(items
print(f"Total: {result}")
`;
// ─── Test Case 4: JavaScript — Logic error + syntax ─────────────────────
const BROKEN_JS_1 = `function fibonacci(n) {
  if (n <= 1) return n;
  return fibonacci(n - 1 + fibonacci(n - 2);  // missing paren
}

console.log(fibonacci("10"));
`;
// ─── Test Case 5: Go — Multiple errors ───────────────────────────────────
const BROKEN_GO_1 = `package main

import "fmt"

func main() {
    var name string = 123
    fmt.Println("Hello, " + name)
    undefinedFunction()
}

func add(a int, b int) int {
    return a + b
`;
const TEST_CASES = [
    { name: 'TypeScript — type mismatch', code: BROKEN_TS_1, language: 'typescript', expectedToFail: true },
    { name: 'TypeScript — missing import + type', code: BROKEN_TS_2, language: 'typescript', expectedToFail: true },
    { name: 'Python — syntax errors', code: BROKEN_PY_1, language: 'python', expectedToFail: true },
    { name: 'JavaScript — syntax + type', code: BROKEN_JS_1, language: 'javascript', expectedToFail: true },
    { name: 'Go — type + syntax errors', code: BROKEN_GO_1, language: 'go', expectedToFail: true },
];
async function testSandbox() {
    console.log('\n═══════════════════════════════════════════════════');
    console.log('  ERROR-CORRECTION LOOP — TEST SUITE');
    console.log('═══════════════════════════════════════════════════\n');
    // 1. Check available tools
    console.log('🔍 Checking available sandbox tools...');
    const availability = checkSandboxAvailability();
    console.log(`   Docker: ${availability.docker ? '✅' : '❌'} (${availability.docker ? 'enabled' : 'not available'})`);
    console.log(`   Local tools: ${availability.local.length > 0 ? availability.local.join(', ') : 'none'}`);
    console.log('');
    if (availability.local.length === 0) {
        console.log('⚠️  No local tools available. Install at least Node.js to run TypeScript tests.');
        console.log('');
    }
    // 2. Test each broken code snippet through the sandbox
    for (const tc of TEST_CASES) {
        const toolAvailable = availability.local.includes(tc.language);
        console.log(`┌──────────────────────────────────────────────────┐`);
        console.log(`  Test: ${tc.name}`);
        console.log(`  Language: ${tc.language}`);
        console.log(`  Tool available: ${toolAvailable ? '✅' : '❌'}`);
        console.log(`└──────────────────────────────────────────────────┘`);
        console.log('');
        if (!toolAvailable && tc.language !== 'typescript' && tc.language !== 'javascript') {
            console.log(`   ⏭  Skipping — ${tc.language} tool not installed\n`);
            continue;
        }
        // Step 1: Show the broken code
        console.log(`  📄 Input code (${tc.code.length} chars):`);
        console.log(`  ─────────────────────────────────────`);
        tc.code.split('\n').slice(0, 8).forEach(line => console.log(`  │ ${line}`));
        if (tc.code.split('\n').length > 8)
            console.log('  │ ...');
        console.log('');
        // Step 2: Run sandbox validation
        console.log(`  🔍 Running sandbox validation...`);
        let sandboxResult = null;
        try {
            sandboxResult = await runSandbox(tc.code, tc.language, 15000);
            console.log(`  Result: ${sandboxResult.success ? '✅ PASSED' : '❌ FAILED'}`);
            if (sandboxResult.errors.length > 0) {
                console.log(`  Errors:`);
                sandboxResult.errors.slice(0, 3).forEach((e) => {
                    console.log(`    ${e.split('\n').slice(0, 4).join('\n    ')}`);
                    if (e.split('\n').length > 4)
                        console.log('    ...');
                });
            }
            if (sandboxResult.output) {
                console.log(`  Output: ${sandboxResult.output.slice(0, 200)}`);
            }
            console.log('');
        }
        catch (err) {
            console.log(`  💥 Sandbox crashed: ${err.message}`);
            console.log('');
            continue;
        }
        // Step 3: Run error-correction loop (only if LLM is configured)
        const llmConfigured = process.env.OPENAI_API_KEY || process.env.SECONDARY_OPENAI_API_KEY;
        if (llmConfigured && sandboxResult && !sandboxResult.success) {
            console.log(`  🤖 LLM configured — running error-correction loop...`);
            try {
                const fixResult = await runErrorCorrection({
                    code: tc.code,
                    language: tc.language,
                    projectName: 'Test Project',
                    goal: 'Test the error-correction loop',
                    maxAttempts: 3,
                });
                console.log(`  Fix loop: ${fixResult.success ? '✅ FIXED' : '❌ STILL BROKEN'}`);
                console.log(`  Attempts: ${fixResult.attempts.length}`);
                console.log(`  Time: ${fixResult.totalTimeMs}ms`);
                console.log(`  Final code: ${fixResult.finalCode.length} chars`);
                console.log('');
                console.log(`  📋 Report:`);
                console.log(`  ${formatFixReport(fixResult).split('\n').slice(0, 8).join('\n  ')}`);
                console.log('');
            }
            catch (err) {
                console.log(`  💥 Fix loop crashed: ${err.message}`);
                console.log('');
            }
        }
        else if (!llmConfigured) {
            console.log(`  ⏭  Skipping fix loop — no LLM API key configured.`);
            console.log(`  Set OPENAI_API_KEY or SECONDARY_OPENAI_API_KEY in .env to enable fixing.\n`);
        }
    }
    // 3. Summary
    console.log('═══════════════════════════════════════════════════');
    console.log('  TEST SUMMARY');
    console.log('═══════════════════════════════════════════════════\n');
    console.log(`  Tools available: ${availability.local.join(', ') || 'none'}`);
    console.log(`  Docker: ${availability.docker ? 'yes' : 'no'}`);
    console.log(`  LLM configured: ${!!(process.env.OPENAI_API_KEY || process.env.SECONDARY_OPENAI_API_KEY)}`);
    console.log(`  ${TEST_CASES.length} test cases defined`);
    console.log('');
    if (availability.local.length === 0) {
        console.log('  💡 Tip: Install Node.js to run TypeScript/JS tests:');
        console.log('     sudo apt install nodejs npm');
        console.log('     npx tsc --version');
        console.log('');
    }
    if (!(process.env.OPENAI_API_KEY || process.env.SECONDARY_OPENAI_API_KEY)) {
        console.log('  💡 Tip: Set an LLM API key in backend/.env to test the full');
        console.log('     fix loop (validate → LLM fixes → retry):');
        console.log('     SECONDARY_OPENAI_API_KEY=sk-your-key');
        console.log('');
    }
    console.log('═══════════════════════════════════════════════════\n');
}
testSandbox().catch(err => {
    console.error('Test suite failed:', err);
    process.exit(1);
});
