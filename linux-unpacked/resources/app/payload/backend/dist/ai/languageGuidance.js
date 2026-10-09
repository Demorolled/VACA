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
            'Standard library ONLY. No third-party modules and no guessed import paths: NEVER write `github.com/...`, `gopkg.in/...`, `example.com/...`, or a `yourusername` placeholder — nothing is downloadable (`go get` fails offline), so any such import makes `go build` fail.',
            'There is NO YAML package anywhere in the Go standard library. `gopkg.in/yaml.v2`, `gopkg.in/yaml.v3`, `yaml`, `encoding/yaml`, `os/yaml` and `io/yaml` ALL do not exist — importing any of them fails with `package ... is not in std`. When YAML output is requested, WRITE a minimal YAML emitter by hand with `fmt.Fprintf`/`strings.Builder` (2-space indent, `key: value`, `- item`), or emit JSON instead.',
            'The file that declares `func main()` MUST be `package main`, and it is the ONLY file allowed to be `package main`. Every other file in the project is a SEPARATE package named after the DIRECTORY it lives in (e.g. `conversion/converter.go` → `package conversion`). Never give a non-entry file `package main` and never give the entry file the directory name.',
            'PREFER keeping everything in ONE `package main` spread over several files (same package, no imports between them). Only split into a sibling package when the plan explicitly asks for it.',
            'A file the plan places at the project ROOT (e.g. `hasher.go`, `utils.go`) is part of `package main`: declare NO package of its own and NEVER import it — call its functions directly. Only a file inside a SUBDIRECTORY (e.g. `fileutil/file.go`) may have its own package, named after that subdirectory, and it is imported as `<module>/fileutil`.',
            'If (and only if) the plan splits code into a sibling package, import it via the go.mod module path (`module <name>` is declared in your guidance) — e.g. `import "<module>/conversion"`. NEVER import a bare relative path such as `app/conversion`, `conversion`, `./conversion`, or `src/foo`: `go build` treats those as standard-library paths and fails with `package app/conversion is not in std`.',
            'Imports in parentheses: `import ("fmt"; "os"; "bufio"; "strings")`. EVERY import must be used or `go build` fails.',
            'Input: `bufio.NewScanner(os.Stdin)`. Output: `fmt.Println` / `fmt.Printf`. Command-line args: `os.Args` (>= 2) or the `flag` package.',
            'Handle errors explicitly (`if err != nil { ... }`) — no ignored returns. `ioutil` is deprecated; use `os.ReadFile` / `os.WriteFile`.',
        ],
    },
    swift: {
        name: 'Swift 5 (single module, swiftc)',
        lines: [
            'Standard library ONLY — no SPM dependencies (no Vapor, Alamofire, swift-argument-parser). The whole set is type-checked by `swiftc` alone.',
            'Entry point: put TOP-LEVEL statements in a file named `main.swift`. The `@main` attribute is FORBIDDEN in `main.swift` — the compiler rejects it with "\'main\' attribute cannot be used in a module that contains top-level code". Use `@main` ONLY in a file NOT named `main.swift`, and at most once in the whole set.',
            'NEVER mix the two: if you wrote `@main`, the file must not be `main.swift` and must contain no top-level statements; if the file is `main.swift`, use plain top-level code and no `@main`.',
            'All files in the set compile as ONE module: every type, function and global must be declared EXACTLY ONCE across all files. Do not repeat a declaration that a sibling file already makes.',
            '`String.characters` was REMOVED from Swift — `input.characters` fails with "\'characters\' is unavailable". Iterate the String directly (`for ch in input.lowercased()`) or use `input.count` / `input.filter { ... }.count`.',
            '`CommandLine.arguments` is `[String]`; `CommandLine.argc` is `Int32`. Convert before arithmetic/comparison (`Int(CommandLine.argc)`) — mixing `Int32` and `Int` is a compile error.',
            'Input: `CommandLine.arguments` or `readLine()`. Output: `print(...)`.',
            'Indent with 4 spaces; no markdown fences, no explanatory prose in the file.',
        ],
    },
    kotlin: {
        name: 'Kotlin/JVM (kotlinc)',
        lines: [
            'Standard library ONLY — no external dependencies (no kotlinx.*, ktor, Gradle-only artifacts). The set is compiled by `kotlinc` alone.',
            'Entry point: `fun main(args: Array<String>)` (or `fun main()`) declared EXACTLY ONCE in the WHOLE project. A second `fun main` in another file is a compile error.',
            'All files compile as ONE module: every top-level function, class and property is a single global. Declare each name EXACTLY ONCE across every file — re-declaring a function with the same signature (e.g. two `fun factorial(n: Int): Long`) fails with `conflicting overloads`. Put a shared helper in ONE file and CALL it from the others.',
            'The file named `main.kt` contains ONLY `fun main(args: Array<String>)` plus the code it calls — do NOT copy a helper into `main.kt` that the plan already assigns to another file. If a helper is planned in BOTH the entry file and a sibling, implement it in the sibling and call it; a second identical definition in `main.kt` is the `conflicting overloads` error above.',
            'Kotlin has NO `isDigitsOnly`/`isNumeric` helper: use `s.all { it.isDigit() }` or `s.matches(Regex("\\d+"))`.',
            'Input: `args` (check `args.isNotEmpty()`) or `readln()`. Output: `println(...)`. Use `explicit` integer types — prefer `Long` for factorial/fibonacci-style accumulation and convert with `.toLong()`.',
            'Return ONLY the raw `.kt` source: no ``` fences, no trailing "Note:"/explanation text after the code — any non-code text is a syntax error.',
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
    kt: 'kotlin', kts: 'kotlin',
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
