/**
 * report-toolchains — print which language compile-gate toolchains are
 * available on THIS machine, and how to install the missing ones.
 *
 * VACA's non-TS gate treats an unavailable toolchain as a FAILED gate
 * ("unverified is never clean"), so this is the preflight the user should run
 * before asking VACA to build in a language other than TypeScript.
 *
 *   cd backend && npm run toolchains:report
 */
import * as path from 'path';
import { detectToolchains, GATE_LANGUAGES } from '../sandbox/nonTsCompileGate.js';
const ORDER = [...GATE_LANGUAGES];
const statuses = await detectToolchains();
const byLang = new Map(statuses.map((s) => [s.language, s]));
const width = Math.max(...ORDER.map((l) => l.length));
console.log('\nVACA toolchain report — the compile gate for each language\n');
let missing = 0;
for (const lang of ORDER) {
    const s = byLang.get(lang);
    const mark = s.available ? '✓' : '✗';
    const detail = s.available ? s.version : `unavailable — install: ${installHint(s.install)}`;
    if (!s.available)
        missing += 1;
    const binName = path.basename(s.bin).padEnd(8);
    console.log(`  ${mark} ${lang.padEnd(width)}  ${binName} ${detail}`);
}
console.log(missing === 0
    ? '\nAll gate toolchains available.\n'
    : `\n${missing} toolchain(s) missing — those languages cannot be compile-verified until installed.\n` +
        '  Linux/macOS:  scripts/install-toolchains.sh\n' +
        '  Windows:      powershell -ExecutionPolicy Bypass -File scripts\\install-toolchains.ps1\n');
function installHint(install) {
    if (process.platform === 'win32')
        return install.windows;
    if (process.platform === 'darwin' && install.macos)
        return install.macos;
    return install.linux;
}
