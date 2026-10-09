/**
 * languageGuidance — per-language code knowledge injected into the file-write
 * prompt.
 *
 * The knowledge store is TypeScript/JavaScript-centric (the learned patterns
 * are all TS/JS), so for every other language the model gets only `Language:
 * rust` and is free to invent members, import third-party crates, or use an API
 * that does not exist. That produced exactly the observed failures: a Java game
 * calling `System.console().readLine()` (null when stdin is piped), invented
 * Go/Java members, and third-party imports that are never installed.
 *
 * This module is the cheap, deterministic counterweight: a compact per-language
 * standard-library / idiom primer added to the generation prompt. It is NOT a
 * knowledge-store replacement — it is the "what this toolchain actually
 * supports" half of VACA's scaffolding contract ("VACA builds the scaffold; the
 * LLM fills in the code VACA asks for").
 */
const GUIDANCE = {
    rust: {
        name: 'Rust (2021 edition)',
        lines: [
            'Standard library ONLY — no external crates (no serde, rand, clap, tokio). Everything must compile with `rustc` alone.',
            'Entry point is `fn main()`. Keep the program a single binary crate; do not rely on Cargo features.',
            'Input: `std::io::stdin().read_line(&mut s)` (handle the `Result`). Output: `println!` / `print!`.',
            'Use `std` types: `String`/`&str`, `Vec`, `Option`, `Result`, `HashMap`, `std::collections`, `std::io`.',
            'Do not use `async`/`await` or the `?` operator in `main` unless `main` returns `Result<(), Box<dyn Error>>`.',
            'Randomness without `rand`: implement a tiny LCG/PRNG with `u64` arithmetic from `std::time` if needed.',
        ],
    },
    cpp: {
        name: 'C++17',
        lines: [
            'Standard library ONLY — no third-party headers. Include only real headers (`<iostream>`, `<vector>`, `<string>`, `<algorithm>`, `<sstream>`, `<random>`, `<chrono>`).',
            'Entry point is `int main()` (or `int main(int argc, char** argv)`).',
            'Use the `std::` namespace explicitly; never `#include <bits/stdc++.h>` (GCC-only and not portable).',
            'Input: `std::cin >> x` or `std::getline(std::cin, s)`. Output: `std::cout << ... << std::endl` (or `\\n`).',
            'Prefer `std::vector` / `std::string` / `std::unordered_map` over raw arrays and `new`/`delete`.',
        ],
    },
    c: {
        name: 'C11',
        lines: [
            'Standard library ONLY. Include only real headers (`<stdio.h>`, `<stdlib.h>`, `<string.h>`, `<math.h>`, `<time.h>`, `<stdbool.h>`).',
            'Entry point is `int main(void)` (or `int main(int argc, char** argv)`); `return 0;` at the end.',
            'Input: `fgets`/`scanf`; output: `printf`. Declare functions before use (prototype or define first).',
            'No C++ constructs — no `std::`, no `//`-only assumptions, no `<iostream>`; compile as C11.',
        ],
    },
    go: {
        name: 'Go 1.21',
        lines: [
            'Standard library ONLY — no external modules (no gin, cobra, etc.).',
            '`package main` + `func main()`. Every file in the set shares one package (or the declared import path).',
            'Imports in parentheses: `import ("fmt"; "os"; "bufio"; "strings")`. EVERY import must be used or `go build` fails.',
            'Input: `bufio.NewScanner(os.Stdin)`. Output: `fmt.Println` / `fmt.Printf`.',
            'Handle errors explicitly (`if err != nil { ... }`) — no ignored returns.',
        ],
    },
    java: {
        name: 'Java 17',
        lines: [
            'Standard library ONLY — `java.util`, `java.io`, `java.nio`, `java.lang`. No third-party jars.',
            'The public class name MUST match its file name (`Main.java` → `public class Main`).',
            'Entry point: `public static void main(String[] args)`.',
            'Input: use `new java.util.Scanner(System.in)` or `BufferedReader(new InputStreamReader(System.in))`. NEVER use `System.console()` — it returns null when stdin is piped/non-interactive and throws NullPointerException.',
            'Output: `System.out.println`. Use `Scanner.nextInt()`/`hasNextInt()` (or `nextLine()`) rather than reading raw bytes.',
            'Keep prefix/package-less classes in the default package; sibling classes resolve when compiled together.',
        ],
    },
    csharp: {
        name: 'C# (.NET 8)',
        lines: [
            'Standard library ONLY — `System`, `System.Collections.Generic`, `System.Linq`, `System.IO`. No NuGet packages.',
            'Entry point: `class Program { static void Main(string[] args) { ... } }`.',
            'Input: `Console.ReadLine()`; output: `Console.WriteLine(...)`.',
            'One top-level class per file; keep program files in the project root so `dotnet build` picks them up.',
        ],
    },
    python: {
        name: 'Python 3.10+',
        lines: [
            'Standard library ONLY — no `pip install` (no requests, numpy, pandas).',
            'Input: `input()` or `sys.stdin`. Output: `print(...)`.',
            'Guard the entry: `if __name__ == "__main__": main()`.',
            'Use f-strings, `dataclasses`, `pathlib`, `json`, `argparse` from the stdlib where useful.',
        ],
    },
    php: {
        name: 'PHP 8',
        lines: [
            'Standard library ONLY — no Composer packages.',
            'Every file starts with `<?php` (no closing `?>` needed at EOF).',
            'Input: `fgets(STDIN)` / `trim(fgets(STDIN))`; output: `echo` / `print`.',
            'Functions must be defined before use OR declared in a file that is `require_once`d first.',
        ],
    },
    ruby: {
        name: 'Ruby 3',
        lines: [
            'Standard library ONLY — no external gems.',
            'Input: `$stdin.gets` / `gets.chomp`; output: `puts` / `print`.',
            'Use `require_relative` for sibling files. Guard the entry with `if __FILE__ == $0`.',
            'Prefer `attr_reader`, blocks, and `Enumerable` methods over manual loops.',
        ],
    },
    typescript: {
        name: 'TypeScript (Node, ESM)',
        lines: [
            'Node built-in modules ONLY — no npm packages (the sandbox installs nothing).',
            'For a CLI: read `process.stdin` / use `readline`; write with `console.log`.',
            'For a script entry, define `main()` and actually CALL it.',
        ],
    },
    javascript: {
        name: 'JavaScript (Node, ESM)',
        lines: [
            'Node built-in modules ONLY — no npm packages (the sandbox installs nothing).',
            'For a CLI: read `process.stdin` / use `readline`; write with `console.log`.',
            'Define and actually CALL the entry function.',
        ],
    },
};
/**
 * The prompt block for a language, or '' when the language has no guidance.
 * Aliases are normalized so `c++`, `c#`, `py`, `kt`-style names still resolve.
 */
export function languageGuidanceBlock(language, opts) {
    const g = resolveGuidance(language);
    if (!g)
        return '';
    const lines = [...g.lines];
    const moduleName = opts?.goModuleName;
    if (resolveKey(language) === 'go' && moduleName) {
        lines.push(`The project's go.mod declares \`module ${moduleName}\`. Any import of a sibling package ` +
            `MUST use that module path — e.g. \`import "${moduleName}/internal/foo"\`. ` +
            'Never import a bare sibling path like "src/foo" or "internal/foo" (go build rejects it). ' +
            'When unsure, keep everything in ONE `package main` file using only the standard library.');
    }
    return (`\n━━━ LANGUAGE GUIDANCE (${g.name}) ━━━\n` +
        'VACA supplies the scaffold and the toolchain; you must write code this toolchain can compile and run:\n' +
        lines.map((l) => `  • ${l}`).join('\n') +
        '\n');
}
const ALIASES = {
    'c++': 'cpp', cxx: 'cpp', cplusplus: 'cpp',
    'c#': 'csharp', cs: 'csharp', dotnet: 'csharp',
    ts: 'typescript', js: 'javascript',
    py: 'python', golang: 'go', rs: 'rust', rb: 'ruby',
};
function resolveKey(language) {
    if (!language)
        return null;
    const raw = language.trim().toLowerCase();
    return ALIASES[raw] || raw;
}
function resolveGuidance(language) {
    const key = resolveKey(language);
    return key ? GUIDANCE[key] || null : null;
}
