import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { runScriptedTicTacToe, looksLikeTicTacToe, ticTacToeWinningInput, parseAnnouncedWinner, parseFirstPlayer, runBehavioralSmokeGates } from './behavioralSmoke.js';
function tmpGame(body) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttt-smoke-'));
    fs.writeFileSync(path.join(dir, 'main.ts'), body, 'utf-8');
    return { dir, files: [{ path: 'main.ts', content: body }] };
}
describe('scripted tic-tac-toe helpers', () => {
    it('detects a tic-tac-toe app from request or source', () => {
        expect(looksLikeTicTacToe('build a tic tac toe game', [])).toBe(true);
        expect(looksLikeTicTacToe('anything', [{ path: 'B.java', content: "char[][] board; boolean checkWin(){return false;} char p='X'; Scanner s;" }])).toBe(true);
        expect(looksLikeTicTacToe('a calculator', [{ path: 'a.py', content: 'print(1)' }])).toBe(false);
    });
    it('builds a winning input for each move encoding', () => {
        expect(ticTacToeWinningInput(false, false)).toBe('0\n3\n1\n4\n2\n');
        expect(ticTacToeWinningInput(true, false)).toBe('1\n4\n2\n5\n3\n');
        expect(ticTacToeWinningInput(false, true)).toBe('0 0\n1 0\n0 1\n1 1\n0 2\n');
    });
    it('parses the announced winner and the first player', () => {
        expect(parseAnnouncedWinner('Player O wins!')).toBe('O');
        expect(parseAnnouncedWinner('X is the winner')).toBe('X');
        expect(parseAnnouncedWinner('no winner here')).toBeNull();
        expect(parseFirstPlayer('Player X, enter your move')).toBe('X');
    });
});
describe('runScriptedTicTacToe (end-to-end via tsx)', () => {
    it('PASSES when the winner is announced correctly', async () => {
        const { dir, files } = tmpGame(`
      import fs from 'fs';
      const nums = fs.readFileSync(0, 'utf8').split(/\\s+/).filter(Boolean);
      console.log('Tic-tac-toe: Player X, enter your move [0-8]:');
      for (const n of nums) console.log('move ' + n);
      console.log('Player X wins!');
    `);
        try {
            const res = await runScriptedTicTacToe(dir, files, { request: 'tic-tac-toe in typescript' });
            expect(res.verdict.status).toBe('passed');
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
    it('caps runaway output without crashing (a game that never consumes input)', async () => {
        const { dir, files } = tmpGame(`
      console.log('Tic-tac-toe: Player X, enter your move [0-8]:');
      const chunk = 'X'.repeat(8192);
      setInterval(() => process.stdout.write(chunk), 1);
    `);
        try {
            const res = await runScriptedTicTacToe(dir, files, { request: 'tic-tac-toe', timeoutMs: 4_000 });
            expect(res.verdict.status).toBe('failed');
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
    it('never downgrades a scripted-game failure to a pass via the generic CLI probe', async () => {
        // The generic cliProbe only understands TS/JS; for a Java game it returns
        // `skipped`. If the repair loop re-ran THAT after a scripted failure, the
        // verdict would clear and a broken game would ship as "success".
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttt-nodowngrade-'));
        fs.writeFileSync(path.join(dir, 'main.ts'), 'console.log(1)', 'utf-8');
        const files = [{ path: 'main.ts', content: 'console.log(1)' }];
        try {
            const res = await runBehavioralSmokeGates({
                request: 'tic-tac-toe',
                files,
                contractFiles: [],
                exportDir: dir,
                timeoutMs: 5_000,
                tag: 'test',
                canRepair: () => true,
                consumeRepair: () => { },
                repairCall: async () => 'console.log(2)',
                renderProbe: async () => ({ status: 'skipped', errors: [], detail: 'no HTML entry file' }),
                cliProbe: async () => ({ status: 'skipped', errors: [], detail: 'no runnable entry file' }),
                gameProbe: async () => ({ verdict: { status: 'failed', errors: ['boom'], detail: 'tic-tac-toe: crashed' }, entryPath: 'main.ts' }),
            });
            expect(res.cliSmoke.status).toBe('failed');
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
    it('FAILS (with a repair target) when a Java game has no main entry point', async () => {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ttt-nomain-'));
        const src = 'src/TicTacToe.java';
        fs.mkdirSync(path.join(dir, 'src'), { recursive: true });
        const content = 'public class TicTacToe { void playGame() { System.out.println("Tic-tac-toe: Player X"); } }';
        fs.writeFileSync(path.join(dir, src), content, 'utf-8');
        const files = [{ path: src, content }];
        try {
            const res = await runScriptedTicTacToe(dir, files, { request: 'command-line tic-tac-toe in java' });
            expect(res.verdict.status).toBe('failed');
            expect(res.verdict.detail).toContain('no main class');
            expect(res.entryPath).toBe(src);
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
    it('FAILS when the wrong winner is announced (the live bug)', async () => {
        const { dir, files } = tmpGame(`
      import fs from 'fs';
      const nums = fs.readFileSync(0, 'utf8').split(/\\s+/).filter(Boolean);
      console.log('Tic-tac-toe: Player X, enter your move [0-8]:');
      for (const n of nums) console.log('move ' + n);
      console.log('Player O wins!');
    `);
        try {
            const res = await runScriptedTicTacToe(dir, files, { request: 'tic-tac-toe in typescript' });
            expect(res.verdict.status).toBe('failed');
            expect(res.verdict.errors.join(' ')).toContain('wrong winner');
        }
        finally {
            fs.rmSync(dir, { recursive: true, force: true });
        }
    });
});
