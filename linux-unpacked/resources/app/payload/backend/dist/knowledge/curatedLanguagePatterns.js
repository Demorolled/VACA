/**
 * curatedLanguagePatterns — a small, hand-written seed of non-TS patterns for
 * the knowledge store.
 *
 * The learned store is TypeScript/JavaScript-only (every captured pattern comes
 * from a TS/JS build), so a Rust/C++/Go/Java request retrieves NOTHING from the
 * library-context step. These patterns are the base layer: real, compilable,
 * standard-library-only idioms the retrieval step can match on, and that the
 * model can copy the shape of. They are seeded idempotently (by title) — see
 * `scripts/seed-knowledge.ts` / `npm run seed:knowledge`.
 */
export const CURATED_LANGUAGE_PATTERNS = [
    {
        category: 'code_pattern',
        title: 'rust — read all stdin and summarize',
        description: 'Read the whole of stdin into a String and derive statistics with iterator adapters. Standard library only; handles EOF cleanly.',
        language: 'rust',
        nodeType: 'logic',
        tags: ['rust', 'cli', 'stdin', 'iterator'],
        projectId: 'curated',
        targetOS: 'linux',
        success: true,
        qualityScore: 8,
        code: `use std::io::{self, Read};

fn main() {
    let mut text = String::new();
    io::stdin().read_to_string(&mut text).unwrap();
    let words = text.split_whitespace().count();
    let lines = text.lines().count();
    println!("Lines: {lines}\\nWords: {words}\\nChars: {}", text.chars().count());
}`,
    },
    {
        category: 'code_pattern',
        title: 'rust — struct with Result-returning constructor',
        description: 'A validated domain type: fields private, a `new` constructor returning Result, and &mut methods that borrow. No external crates.',
        language: 'rust',
        nodeType: 'logic',
        tags: ['rust', 'struct', 'impl', 'result', 'error-handling'],
        projectId: 'curated',
        targetOS: 'linux',
        success: true,
        qualityScore: 8,
        code: `#[derive(Debug)]
pub struct Grid {
    cells: Vec<char>,
    size: usize,
}

impl Grid {
    pub fn new(size: usize) -> Result<Self, String> {
        if size == 0 {
            return Err("size must be positive".to_string());
        }
        Ok(Self { cells: vec!['-'; size * size], size })
    }

    pub fn set(&mut self, row: usize, col: usize, mark: char) -> bool {
        if row >= self.size || col >= self.size {
            return false;
        }
        let idx = row * self.size + col;
        if self.cells[idx] != '-' {
            return false;
        }
        self.cells[idx] = mark;
        true
    }

    pub fn get(&self, row: usize, col: usize) -> Option<char> {
        if row >= self.size || col >= self.size {
            return None;
        }
        Some(self.cells[row * self.size + col])
    }
}`,
    },
    {
        category: 'code_pattern',
        title: 'c++ — interactive loop with <random> and read-until-EOF',
        description: 'A game/CLI loop using the <random> engine seeded from <chrono>, and `for (int x; std::cin >> x;)` to read input until EOF. No third-party headers.',
        language: 'cpp',
        nodeType: 'logic',
        tags: ['cpp', 'cli', 'random', 'loop', 'c++17'],
        projectId: 'curated',
        targetOS: 'linux',
        success: true,
        qualityScore: 8,
        code: `#include <iostream>
#include <random>
#include <chrono>

int main() {
    unsigned seed = static_cast<unsigned>(
        std::chrono::steady_clock::now().time_since_epoch().count());
    std::mt19937 rng(seed);
    int secret = static_cast<int>(rng() % 100) + 1;

    std::cout << "Guess the number (1-100):\\n";
    for (int guess; std::cin >> guess;) {
        if (guess == secret) {
            std::cout << "Correct!\\n";
            return 0;
        }
        std::cout << (guess < secret ? "Higher\\n" : "Lower\\n");
    }
    return 0;
}`,
    },
    {
        category: 'code_pattern',
        title: 'c++ — small class with std::vector and range-for',
        description: 'A self-contained class holding a std::vector, with const-correct accessors and range-based iteration. Header-safe (no main).',
        language: 'cpp',
        nodeType: 'logic',
        tags: ['cpp', 'class', 'vector', 'oop', 'c++17'],
        projectId: 'curated',
        targetOS: 'linux',
        success: true,
        qualityScore: 8,
        code: `#include <string>
#include <vector>

class Inventory {
public:
    void add(const std::string& item) { items_.push_back(item); }

    bool has(const std::string& item) const {
        for (const auto& it : items_) {
            if (it == item) return true;
        }
        return false;
    }

    std::size_t size() const { return items_.size(); }

private:
    std::vector<std::string> items_;
};`,
    },
    {
        category: 'code_pattern',
        title: 'go — bufio scanner input loop',
        description: 'Read lines from stdin with a bufio.Scanner, trimming and skipping blanks, and printing results. Standard library only.',
        language: 'go',
        nodeType: 'logic',
        tags: ['go', 'cli', 'stdin', 'bufio'],
        projectId: 'curated',
        targetOS: 'linux',
        success: true,
        qualityScore: 8,
        code: `package main

import (
	"bufio"
	"fmt"
	"os"
	"strings"
)

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	count := 0
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		count++
		fmt.Printf("%d: %s\\n", count, line)
	}
	if err := scanner.Err(); err != nil {
		fmt.Fprintln(os.Stderr, "read error:", err)
	}
}`,
    },
    {
        category: 'code_pattern',
        title: 'java — Scanner-based interactive loop (never System.console())',
        description: 'A CLI game loop reading moves with java.util.Scanner. Uses System.in (Scanner), NOT System.console(), which is null under piped stdin.',
        language: 'java',
        nodeType: 'logic',
        tags: ['java', 'cli', 'scanner', 'stdin', 'loop'],
        projectId: 'curated',
        targetOS: 'linux',
        success: true,
        qualityScore: 8,
        code: `import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        System.out.println("Enter numbers (blank line to stop):");
        java.util.List<Integer> nums = new java.util.ArrayList<>();
        while (scanner.hasNextLine()) {
            String line = scanner.nextLine().trim();
            if (line.isEmpty()) break;
            if (line.matches("-?\\\\d+")) {
                nums.add(Integer.parseInt(line));
            } else {
                System.out.println("Not a number: " + line);
            }
        }
        System.out.println("Read " + nums.size() + " number(s).");
        scanner.close();
    }
}`,
    },
];
/**
 * Add the curated patterns the store does not already have (matched by title).
 * Idempotent: re-running adds nothing. Returns the titles added and the count
 * skipped. Never throws on a rejected pattern (the quality gate may decline).
 */
export function seedCuratedLanguagePatterns(opts) {
    const existing = new Set(opts.store.getAll().map((p) => p.title));
    const added = [];
    let skipped = 0;
    for (const pattern of CURATED_LANGUAGE_PATTERNS) {
        if (existing.has(pattern.title)) {
            skipped += 1;
            continue;
        }
        const stored = opts.store.addPattern(pattern);
        if (stored) {
            added.push(pattern.title);
            existing.add(pattern.title);
        }
        else {
            skipped += 1;
        }
    }
    return { added, skipped };
}
