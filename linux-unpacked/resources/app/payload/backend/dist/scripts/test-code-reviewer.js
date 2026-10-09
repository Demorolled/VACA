/**
 * CodeReviewer E2E Test — validates that the code review add-on catches
 * intentionally injected errors across 4 different categories.
 *
 * Each test scenario:
 *   1. Takes a valid code snippet (simulating freshly generated code)
 *   2. Injects a specific error
 *   3. Runs the CodeReviewer on the error-injected code
 *   4. Reports whether the error was caught and at what severity
 *
 * Run: npx tsx backend/src/scripts/test-code-reviewer.ts
 */
import { codeReviewer, toReviewableFiles } from '../review/CodeReviewer.js';
// ── Colors for terminal output ──
const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const YELLOW = '\x1b[33m';
const CYAN = '\x1b[36m';
const BOLD = '\x1b[1m';
const NC = '\x1b[0m';
// ═══════════════════════════════════════════════════════════════════════════
// TEST 1: Security — Hardcoded API key / credential leak
// ═══════════════════════════════════════════════════════════════════════════
const test1 = {
    name: '🔒 Security — Credential Leak',
    fileName: 'weather-service.ts',
    description: 'Hardcoded API key in source code (credentials in plaintext)',
    code: `/**
 * Weather service that fetches forecast data from OpenWeatherMap.
 */
import axios from 'axios';

// BUG INTENTIONALLY INJECTED: Hardcoded API key
const API_KEY = 'sk-live-7f8a2b3c4d5e6f7a8b9c0d1e2f3a4b5c';
const BASE_URL = 'https://api.openweathermap.org/data/2.5';

interface ForecastResponse {
  temperature: number;
  humidity: number;
  description: string;
}

export async function getForecast(city: string): Promise<ForecastResponse> {
  const url = \`\${BASE_URL}/weather?q=\${city}&appid=\${API_KEY}&units=metric\`;
  
  const response = await axios.get(url);
  const data = response.data;
  
  return {
    temperature: data.main.temp,
    humidity: data.main.humidity,
    description: data.weather[0].description,
  };
}

export async function getForecastBatch(cities: string[]): Promise<ForecastResponse[]> {
  return Promise.all(cities.map(city => getForecast(city)));
}
`,
    expectedCategory: 'security',
    expectedMinSeverity: 'high',
    expectedKeywords: ['api', 'key', 'credential', 'secret', 'token', 'hardcoded', 'security', 'leak'],
};
// ═══════════════════════════════════════════════════════════════════════════
// TEST 2: Bug — Null pointer / undefined access
// ═══════════════════════════════════════════════════════════════════════════
const test2 = {
    name: '🐛 Bug — Null Pointer Dereference',
    fileName: 'user-service.ts',
    description: 'Accessing property on potentially null/undefined object',
    code: `/**
 * User profile service.
 */
interface User {
  id: number;
  name: string;
  email: string;
  address?: {
    street: string;
    city: string;
    zip: string;
  };
}

const userCache = new Map<number, User>();

export function getUser(id: number): User | undefined {
  return userCache.get(id);
}

// BUG INTENTIONALLY INJECTED: No null check before accessing nested property
export function getUserCity(id: number): string {
  const user = getUser(id);
  // BUG: user could be undefined, address could be undefined
  return user.address.city;
}

export function formatUserEmail(id: number): string {
  const user = getUser(id);
  if (!user) return 'Unknown User';
  return user.email.toLowerCase();
}

export function updateUserName(id: number, name: string): boolean {
  const user = userCache.get(id);
  if (!user) return false;
  user.name = name;
  return true;
}
`,
    expectedCategory: 'bug',
    expectedMinSeverity: 'high',
    expectedKeywords: ['null', 'undefined', 'optional', 'crash', 'access', 'property', 'type error', 'runtime'],
};
// ═══════════════════════════════════════════════════════════════════════════
// TEST 3: Performance — Unnecessary nested loops (O(n²) when O(n) works)
// ═══════════════════════════════════════════════════════════════════════════
const test3 = {
    name: '⚡ Performance — Inefficient Nested Loops',
    fileName: 'order-matcher.ts',
    description: 'O(n²) nested loops when a Map lookup would be O(n)',
    code: `/**
 * Order matching engine — matches buy and sell orders.
 */
interface Order {
  id: string;
  symbol: string;
  price: number;
  quantity: number;
}

// BUG INTENTIONALLY INJECTED: Nested loops instead of using a Map
export function matchOrders(buys: Order[], sells: Order[]): Array<{ buy: Order; sell: Order }> {
  const matches: Array<{ buy: Order; sell: Order }> = [];
  
  for (const buy of buys) {
    for (const sell of sells) {
      // Inefficient: O(n²) instead of O(n) with a Map lookup
      if (sell.symbol === buy.symbol && sell.price <= buy.price) {
        matches.push({ buy, sell });
      }
    }
  }
  
  return matches;
}

// BUG INTENTIONALLY INJECTED: Same pattern — redundant nested loop
export function findDuplicates(orders: Order[]): Order[] {
  const duplicates: Order[] = [];
  
  for (let i = 0; i < orders.length; i++) {
    for (let j = 0; j < orders.length; j++) {
      // O(n²) comparison — should use a Set
      if (i !== j && orders[i].id === orders[j].id) {
        duplicates.push(orders[i]);
      }
    }
  }
  
  return duplicates;
}

export function getTotalVolume(orders: Order[]): number {
  return orders.reduce((sum, o) => sum + o.quantity, 0);
}
`,
    expectedCategory: 'performance',
    expectedMinSeverity: 'medium',
    expectedKeywords: ['performance', 'nested', 'loop', 'O(n²)', 'complexity', 'inefficient', 'map', 'lookup'],
};
// ═══════════════════════════════════════════════════════════════════════════
// TEST 4: Maintainability — Console.log left in production + dead code
// ═══════════════════════════════════════════════════════════════════════════
const test4 = {
    name: '🧹 Maintainability — Console.log + Dead Code',
    fileName: 'payment-processor.ts',
    description: 'Console debug logs left in production code + commented-out dead code',
    code: `/**
 * Payment processing service.
 */

// BUG INTENTIONALLY INJECTED: Debug logging left in production
export function processPayment(
  userId: number,
  amount: number,
  currency: string
): { success: boolean; transactionId?: string } {
  console.log('DEBUG: processPayment called with:', { userId, amount, currency });
  
  if (amount <= 0) {
    console.log('DEBUG: Invalid amount detected');
    return { success: false };
  }
  
  const result = chargePayment(userId, amount, currency);
  
  console.log('DEBUG: Payment result:', JSON.stringify(result));
  
  // BUG INTENTIONALLY INJECTED: This was for debugging — should be removed
  // console.trace('Payment stack trace for debugging');
  
  return result;
}

// BUG INTENTIONALLY INJECTED: Dead code — unused function (was for a feature that was dropped)
function validateCurrency(currency: string): boolean {
  const validCurrencies = ['USD', 'EUR', 'GBP', 'JPY'];
  // This function is never called anywhere
  if (!validCurrencies.includes(currency.toUpperCase())) {
    console.warn('Unknown currency:', currency);
    return false;
  }
  return true;
}

function chargePayment(userId: number, amount: number, currency: string): { success: boolean; transactionId?: string } {
  // Simulated payment processing
  const transactionId = \`txn_\${Date.now()}_\${userId}\`;
  return { success: true, transactionId };
}
`,
    expectedCategory: 'maintainability',
    expectedMinSeverity: 'low',
    expectedKeywords: ['console.log', 'debug', 'dead code', 'unused', 'maintainability', 'remove'],
};
async function runTest(test) {
    console.log(`\n${BOLD}${CYAN}════════════════════════════════════════════════════════${NC}`);
    console.log(`${BOLD}${test.name}${NC}`);
    console.log(`${CYAN}  ${test.description}${NC}`);
    console.log(`${CYAN}  File: ${test.fileName}${NC}`);
    console.log(`${CYAN}════════════════════════════════════════════════════════${NC}\n`);
    const reviewable = toReviewableFiles([{
            fileName: test.fileName,
            code: test.code,
            nodeId: 'test-node-001',
            nodeLabel: test.name,
            language: 'typescript',
        }]);
    console.log(`  Reviewing ${reviewable.length} file(s)...\n`);
    const result = await codeReviewer.reviewAll(reviewable, {
        projectName: 'CodeReviewer E2E Test',
        appGoal: 'Validate that intentional errors are caught',
        targetOS: 'linux',
    });
    // Analyze results
    const allComments = result.comments || [];
    const matchedKeywords = [];
    let caughtAt = 'not-caught';
    let bestSeverity = 'none';
    for (const comment of allComments) {
        const commentLower = comment.content.toLowerCase();
        for (const keyword of test.expectedKeywords) {
            if (commentLower.includes(keyword.toLowerCase())) {
                if (!matchedKeywords.includes(keyword)) {
                    matchedKeywords.push(keyword);
                }
            }
        }
        // Track the best severity match
        const severityOrder = ['critical', 'high', 'medium', 'low', 'info', 'none'];
        const commentIdx = severityOrder.indexOf(comment.severity);
        const bestIdx = severityOrder.indexOf(bestSeverity);
        if (commentIdx >= 0 && (bestIdx < 0 || commentIdx < bestIdx)) {
            bestSeverity = comment.severity;
        }
    }
    // Check if error was detected by keyword matching
    const keywordMatchRatio = matchedKeywords.length / test.expectedKeywords.length;
    const passed = keywordMatchRatio >= 0.2 && allComments.length > 0; // At least 20% keyword match
    // Determine at what severity it was caught
    const severityOrder = ['critical', 'high', 'medium', 'low', 'info'];
    if (passed) {
        const minIdx = severityOrder.indexOf(test.expectedMinSeverity);
        const actualIdx = severityOrder.indexOf(bestSeverity);
        if (actualIdx >= 0 && actualIdx <= minIdx) {
            caughtAt = bestSeverity;
        }
        else if (actualIdx >= 0) {
            caughtAt = `${bestSeverity} (expected ${test.expectedMinSeverity}+)`;
        }
        else {
            caughtAt = bestSeverity;
        }
    }
    // Print results
    console.log(`  ${BOLD}Results:${NC}`);
    console.log(`  Total comments: ${allComments.length}`);
    console.log(`  Matched keywords: ${matchedKeywords.length}/${test.expectedKeywords.length}`);
    console.log(`  Best severity caught at: ${bestSeverity}`);
    console.log(`  Status: ${passed ? `${GREEN}✅ CAUGHT${NC}` : `${RED}❌ MISSED${NC}`}`);
    if (allComments.length > 0) {
        console.log(`\n  ${BOLD}Review Comments:${NC}`);
        for (const c of allComments.slice(0, 5)) {
            const severityColor = c.severity === 'critical' || c.severity === 'high' ? RED :
                c.severity === 'medium' ? YELLOW :
                    GREEN;
            const lineInfo = c.startLine > 0 ? `:${c.startLine}${c.endLine > c.startLine ? `-${c.endLine}` : ''}` : '';
            console.log(`    [${severityColor}${c.severity}${NC}]${BOLD} ${c.path}${lineInfo}${NC}`);
            console.log(`    ${c.content.substring(0, 200)}${c.content.length > 200 ? '...' : ''}`);
            if (c.suggestionCode) {
                console.log(`    ${YELLOW}Suggestion:${NC} ${c.suggestionCode.substring(0, 100)}...`);
            }
            console.log('');
        }
        if (allComments.length > 5) {
            console.log(`    ... and ${allComments.length - 5} more comment(s)`);
        }
    }
    return {
        scenario: test.name,
        fileName: test.fileName,
        passed,
        caughtAt,
        matchedKeywords,
        commentCount: allComments.length,
        severity: bestSeverity,
        allComments: allComments.map(c => ({
            content: c.content.substring(0, 100),
            severity: c.severity,
            category: c.category,
        })),
    };
}
// ═══════════════════════════════════════════════════════════════════════════
// Main Runner
// ═══════════════════════════════════════════════════════════════════════════
async function main() {
    console.log(`\n${BOLD}${CYAN}╔════════════════════════════════════════════════════════╗${NC}`);
    console.log(`${BOLD}${CYAN}║   CodeReviewer E2E Test Suite — 4 Intentional Errors    ║${NC}`);
    console.log(`${BOLD}${CYAN}╚════════════════════════════════════════════════════════╝${NC}\n`);
    console.log(`Starting tests at ${new Date().toISOString()}`);
    console.log(`Testing CodeReviewer with 4 intentionally injected errors...\n`);
    const scenarios = [test1, test2, test3, test4];
    const results = [];
    for (const test of scenarios) {
        try {
            const result = await runTest(test);
            results.push(result);
        }
        catch (err) {
            console.error(`${RED}Test failed with error:${NC}`, err);
            results.push({
                scenario: test.name,
                fileName: test.fileName,
                passed: false,
                caughtAt: 'error',
                matchedKeywords: [],
                commentCount: 0,
                severity: 'error',
                allComments: [],
            });
        }
    }
    // ── Summary Report ──
    console.log(`\n${BOLD}${CYAN}╔════════════════════════════════════════════════════════╗${NC}`);
    console.log(`${BOLD}${CYAN}║                    SUMMARY REPORT                      ║${NC}`);
    console.log(`${BOLD}${CYAN}╚════════════════════════════════════════════════════════╝${NC}\n`);
    const passed = results.filter(r => r.passed).length;
    const failed = results.filter(r => !r.passed).length;
    for (const r of results) {
        const icon = r.passed ? '✅' : '❌';
        const color = r.passed ? GREEN : RED;
        console.log(`  ${icon} ${color}${r.scenario}${NC}`);
        console.log(`     File: ${r.fileName}`);
        console.log(`     Caught at: ${r.caughtAt}`);
        console.log(`     Comments: ${r.commentCount}`);
        console.log(`     Keywords matched: ${r.matchedKeywords.length}`);
        console.log('');
    }
    console.log(`${BOLD}────────────────────────────────────────────────────${NC}`);
    console.log(`${BOLD}Result: ${passed}/4 passed, ${failed}/4 failed${NC}`);
    if (failed > 0) {
        console.log(`\n${YELLOW}⚠️  Failed tests:${NC}`);
        for (const r of results) {
            if (!r.passed) {
                console.log(`  ${RED}- ${r.scenario}${NC}`);
                console.log(`    Comments returned: ${r.commentCount}`);
                if (r.allComments.length > 0) {
                    console.log(`    Sample: "${r.allComments[0].content}"`);
                    console.log(`    Severity: ${r.allComments[0].severity}, Category: ${r.allComments[0].category}`);
                }
            }
        }
    }
    const hasCriticalComments = results.some(r => r.allComments.some(c => c.severity === 'critical'));
    const hasHighComments = results.some(r => r.allComments.some(c => c.severity === 'high'));
    console.log(`\n${BOLD}CodeReviewer Detection Strength:${NC}`);
    console.log(`  Critical issues detected: ${hasCriticalComments ? '✅ Yes' : '❌ No'}`);
    console.log(`  High severity detected:   ${hasHighComments ? '✅ Yes' : '❌ No'}`);
    console.log(`  Average comments/test:    ${(results.reduce((s, r) => s + r.commentCount, 0) / results.length).toFixed(1)}`);
    console.log(`  Pass rate:                ${(passed / results.length * 100).toFixed(0)}%\n`);
    process.exit(passed === results.length ? 0 : 1);
}
main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
