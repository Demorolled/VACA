/**
 * testGlobals.ts — ambient TypeScript declarations for test-runner globals.
 *
 * The write prompts forbid third-party packages (rule 11: "Use ONLY built-in
 * language/platform APIs and the standard library. NO third-party packages"),
 * yet the model still legitimately emits vitest/jest-style test files that
 * reference bare globals (`test`, `it`, `expect`, `describe`, `beforeEach`,
 * `afterEach`, ...). Neither sandbox tsc gate installs @types/jest /
 * @types/vitest, so every generated test file failed the compile gate with
 * TS2304 ("Cannot find name 'expect'") / TS2593 ("Cannot find name 'test'")
 * — the dominant error class in the R9 audit's full-stack write (33 tsc
 * errors, 12 files, repair loop gave up). That is a harness artifact, not a
 * code error: the SAME class as the node globals already declared for CLI
 * files (process/require/__dirname). Declaring the test globals keeps the
 * gate honest — it reports STRUCTURAL errors, not missing-type-install noise.
 *
 * The declarations are intentionally loose (`any`-typed) because the goal is
 * to let the MODEL's test files typecheck against a plausible runner surface,
 * not to enforce a specific testing framework. The behavioral gate (smoke
 * tests) remains the authority on whether tests actually run.
 */
export const TEST_GLOBALS_DTS = `// Ambient test-runner globals (declared by the platform — see testGlobals.ts).
// Generated test files reference these bare globals; @types/jest / @types/vitest
// are never installed in the sandbox (third-party packages are banned), so this
// declaration lets them typecheck without inventing imports.
declare const describe: (name: string, fn: () => void) => void;
declare const it: (name: string, fn: () => void) => void;
declare const test: (name: string, fn: () => void) => void;
declare const expect: (actual: any) => any;
declare function beforeEach(fn: () => void): void;
declare function afterEach(fn: () => void): void;
declare function beforeAll(fn: () => void): void;
declare function afterAll(fn: () => void): void;
declare const vi: any;
declare const jest: any;
declare namespace jest {
  const fn: any;
  const mock: any;
}
declare namespace vi {
  const fn: any;
  const mock: any;
}
`;
