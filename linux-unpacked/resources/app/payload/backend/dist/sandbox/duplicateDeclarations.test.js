import { describe, it, expect } from 'vitest';
import { maskCommentsAndStrings, extractTypeDeclarations, declarationCarriesProgramEntry, nodeStemFromPath, nonBenignReferenceCount, renameTypeInContent, resolveCrossFileDuplicates, } from './duplicateDeclarations.js';
const hint = (path, language, summary = '', exports) => ({ path, language, summary, exports });
/** The generated Swift app from the round-3 retest, reduced to the collision. */
const SWIFT_CLI = `import Foundation

class TemperatureLog {
    private var temperatures: [Double] = []

    init() {}

    func averageTemperature() -> Double {
        return 0.0
    }
}

func main() {
    let log = TemperatureLog()
    print(log.averageTemperature())
}
`;
const SWIFT_STATS = `import Foundation

class TemperatureLog {
    private var temperatures: [Double] = []

    init() {}

    func add(_ value: Double) {
        temperatures.append(value)
    }

    func averageTemperature() -> Double {
        return 0.0
    }

    func recordTemperature(_ value: Double) {
        add(value)
    }

    func maxTemperature() -> Double {
        return temperatures.max() ?? 0
    }
}
`;
describe('maskCommentsAndStrings', () => {
    it('blanks comments and literals while preserving every offset', () => {
        const code = [
            '// class Fake {',
            'const char* s = "class AlsoFake {";',
            '/* class BlockFake { */',
            'class Real {',
            '};',
        ].join('\n');
        const mask = maskCommentsAndStrings(code, 'cpp');
        expect(mask.length).toBe(code.length);
        expect(mask).not.toContain('Fake');
        expect(mask).toContain('Real');
        expect(mask.split('\n').length).toBe(code.split('\n').length);
    });
    it('masks Swift multiline strings and C# verbatim strings', () => {
        const swift = 'let a = """\nclass Nope {}\n"""\nclass Yes {}\n';
        expect(maskCommentsAndStrings(swift, 'swift')).not.toContain('Nope');
        const csharp = 'var s = @"line1\nclass Nope {}";\nclass Yes {}\n';
        const cm = maskCommentsAndStrings(csharp, 'csharp');
        expect(cm).not.toContain('Nope');
        expect(cm).toContain('Yes');
    });
});
describe('extractTypeDeclarations', () => {
    it('finds the Swift type and ignores the one inside a comment', () => {
        const decls = extractTypeDeclarations(SWIFT_CLI, 'swift');
        expect(decls.map((d) => d.raw)).toEqual(['TemperatureLog']);
    });
    it('reads a C# body on the next line (Allman braces)', () => {
        const code = [
            'public class BudgetStore',
            '{',
            '    private double balance;',
            '    public double GetBalance() { return balance; }',
            '}',
            '',
            'public class Other { }',
        ].join('\n');
        const decls = extractTypeDeclarations(code, 'csharp');
        expect(decls.map((d) => d.raw)).toEqual(['BudgetStore', 'Other']);
        expect(code.slice(decls[0].start, decls[0].end)).toContain('GetBalance');
        expect(code.slice(decls[0].start, decls[0].end)).not.toContain('Other');
    });
    it('ends a bare declaration at its own line instead of stealing the next body', () => {
        const code = ['class TemperatureLog', 'class Stats {', '  var n = 0', '}', ''].join('\n');
        const decls = extractTypeDeclarations(code, 'swift');
        expect(decls.map((d) => d.raw)).toEqual(['TemperatureLog', 'Stats']);
        expect(code.slice(decls[0].start, decls[0].end)).toBe('class TemperatureLog');
        expect(code.slice(decls[1].start, decls[1].end)).toContain('var n = 0');
    });
    it('covers Kotlin primary-constructor classes and C# positional records', () => {
        expect(extractTypeDeclarations('data class Entry(val amount: Double) { fun show() {} }\n', 'kotlin').map((d) => d.raw))
            .toEqual(['Entry']);
        expect(extractTypeDeclarations('public record BudgetEntry(double Amount);\n', 'csharp').map((d) => d.raw))
            .toEqual(['BudgetEntry']);
        expect(extractTypeDeclarations('enum class Grade { A, B }\n', 'kotlin').map((d) => d.raw)).toEqual(['Grade']);
    });
    it('finds nothing in languages it must not touch', () => {
        expect(extractTypeDeclarations('type Foo struct {}\n', 'go')).toEqual([]);
        expect(extractTypeDeclarations('pub struct Foo {}\n', 'rust')).toEqual([]);
    });
});
describe('declarationCarriesProgramEntry', () => {
    it('detects a C# static Main and a Java main, not a Swift/Kotlin class', () => {
        expect(declarationCarriesProgramEntry('class Program { static void Main() {} }', 'csharp')).toBe(true);
        expect(declarationCarriesProgramEntry('class App { public static void main(String[] a) {} }', 'java')).toBe(true);
        expect(declarationCarriesProgramEntry('class TemperatureLog { func run() {} }', 'swift')).toBe(false);
        expect(declarationCarriesProgramEntry('class Store { fun get() {} }', 'kotlin')).toBe(false);
    });
});
describe('rename safety helpers', () => {
    it('derives the node stem from the scaffold path', () => {
        expect(nodeStemFromPath('src/budget-store/budget-store.cs')).toBe('BudgetStore');
        expect(nodeStemFromPath('src/stats/stats.swift')).toBe('Stats');
        expect(nodeStemFromPath('main.swift')).toBe('Main');
    });
    it('treats a bare type witness as benign and a real use as not', () => {
        expect(nonBenignReferenceCount('_ = Foo.self\n_ = Foo.self\n', 'swift', 'Foo')).toBe(0);
        expect(nonBenignReferenceCount('var f = typeof(Foo);\n', 'csharp', 'Foo')).toBe(0);
        expect(nonBenignReferenceCount('var f = new Foo();\n', 'csharp', 'Foo')).toBe(1);
        expect(nonBenignReferenceCount('Foo.Bar();\n', 'java', 'Foo')).toBe(1);
    });
    it('renames type references but never touches strings or comments', () => {
        const code = 'class Row { }\n// class Row\nlet s = "class Row"\nlet r = Row()\n';
        const out = renameTypeInContent(code, 'swift', 'Row', 'ARow');
        expect(out).toContain('class ARow');
        expect(out).toContain('let r = ARow()');
        expect(out).toContain('// class Row');
        expect(out).toContain('"class Row"');
    });
});
describe('resolveCrossFileDuplicates', () => {
    it('keeps the super-set definition and deletes the redundant Swift copy', () => {
        const files = [
            { path: 'src/cli/cli.swift', content: SWIFT_CLI },
            { path: 'src/stats/stats.swift', content: SWIFT_STATS },
        ];
        const res = resolveCrossFileDuplicates(files, [hint('src/cli/cli.swift', 'swift'), hint('src/stats/stats.swift', 'swift')]);
        expect(res.failures).toEqual([]);
        expect(res.notes).toEqual([
            { symbol: 'TemperatureLog', path: 'src/cli/cli.swift', ownerPath: 'src/stats/stats.swift', action: 'deleted' },
        ]);
        expect(res.changedPaths).toEqual(['src/cli/cli.swift']);
        expect(files[1].content).toContain('class TemperatureLog');
        expect(files[0].content).not.toContain('class TemperatureLog');
        expect(files[0].content).toContain('func main()');
        expect(files[0].content).toContain('TemperatureLog()');
    });
    it('falls back to the node label when the definitions are equivalent', () => {
        const files = [
            { path: 'src/report/report.cs', content: 'class BudgetStore { }\n' },
            { path: 'src/budget-store/budget-store.cs', content: 'class BudgetStore { }\n' },
        ];
        const res = resolveCrossFileDuplicates(files, [hint('src/report/report.cs', 'csharp'), hint('src/budget-store/budget-store.cs', 'csharp')]);
        expect(res.notes).toEqual([
            { symbol: 'BudgetStore', path: 'src/report/report.cs', ownerPath: 'src/budget-store/budget-store.cs', action: 'deleted' },
        ]);
        expect(files[1].content).toContain('class BudgetStore');
        expect(files[0].content).not.toContain('class BudgetStore');
    });
    it('RENAMES a divergent redeclaration and rewrites its own references', () => {
        const files = [
            { path: 'src/a/a.swift', content: 'class Row {\n  let a = 1\n}\n\nlet r = Row()\n' },
            { path: 'src/b/b.swift', content: 'class Row {\n  let b = 2\n}\n' },
        ];
        const res = resolveCrossFileDuplicates(files, [hint('src/a/a.swift', 'swift'), hint('src/b/b.swift', 'swift')]);
        expect(res.failures).toEqual([]);
        const renamed = res.notes.find((n) => n.action === 'renamed');
        expect(renamed).toBeDefined();
        expect(renamed.path).toBe('src/b/b.swift');
        expect(renamed.ownerPath).toBe('src/a/a.swift');
        expect(renamed.newName).toBe('BRow');
        expect(files[1].content).toContain('class BRow');
        expect(files[1].content).not.toMatch(/\bclass Row\b/);
        // The owner keeps the original name, and its own call still resolves.
        expect(files[0].content).toContain('class Row');
        expect(files[0].content).toContain('let r = Row()');
    });
    it('reports (never renames) when another file consumes the API', () => {
        const files = [
            { path: 'src/a/a.swift', content: 'class Row {\n  let a = 1\n}\n' },
            { path: 'src/b/b.swift', content: 'class Row {\n  let b = 2\n}\n' },
            { path: 'src/c/c.swift', content: 'func use() {\n  let r = Row()\n}\n' },
        ];
        const res = resolveCrossFileDuplicates(files, [
            hint('src/a/a.swift', 'swift'), hint('src/b/b.swift', 'swift'), hint('src/c/c.swift', 'swift'),
        ]);
        expect(res.changedPaths).toEqual([]);
        expect(res.notes.every((n) => n.action === 'reported')).toBe(true);
        expect(res.failures[0]).toContain('uses this definition');
        expect(files[1].content).toContain('class Row');
    });
    it('allows a rename when the only outside reference is a bare type witness', () => {
        const files = [
            { path: 'src/a/a.swift', content: 'class Row {\n  let a = 1\n}\n' },
            { path: 'src/b/b.swift', content: 'class Row {\n  let b = 2\n}\n' },
            { path: 'main.swift', content: '_ = Row.self\n' },
        ];
        const res = resolveCrossFileDuplicates(files, [
            hint('src/a/a.swift', 'swift'), hint('src/b/b.swift', 'swift'), hint('main.swift', 'swift'),
        ]);
        expect(res.failures).toEqual([]);
        expect(res.notes.some((n) => n.action === 'renamed')).toBe(true);
    });
    it('keeps the contract exports in step with a delete and a rename', () => {
        const files = [
            { path: 'src/a/a.cs', content: 'public class Row { }\n' },
            { path: 'src/b/b.cs', content: 'public class Row {\n  public int B;\n}\n' },
        ];
        const contracts = [
            hint('src/a/a.cs', 'csharp', '', ['Row']),
            hint('src/b/b.cs', 'csharp', '', ['Row', 'Other']),
        ];
        resolveCrossFileDuplicates(files, contracts);
        // src/b/b.cs is the super-set owner and keeps `Row`; src/a/a.cs lost it.
        expect(contracts[1].exports).toEqual(['Row', 'Other']);
        expect(contracts[0].exports).toEqual([]);
    });
    it('never resolves away a declaration that holds the program entry point', () => {
        const files = [
            { path: 'src/one/one.cs', content: 'class Program { static void Main() { } }\n' },
            { path: 'src/two/two.cs', content: 'class Program { static void Main() { } }\n' },
        ];
        const res = resolveCrossFileDuplicates(files, [hint('src/one/one.cs', 'csharp'), hint('src/two/two.cs', 'csharp')]);
        expect(res.changedPaths).toEqual([]);
        expect(res.notes.every((n) => n.action === 'reported')).toBe(true);
        expect(res.failures[0]).toContain('program entry point');
    });
    it('deletes the second copy inside ONE file too', () => {
        const content = 'class Store {\n  let a = 1\n}\n\nclass Store {\n  let a = 1\n}\n';
        const files = [{ path: 'src/store/store.swift', content }];
        const res = resolveCrossFileDuplicates(files, [hint('src/store/store.swift', 'swift')]);
        expect(res.changedPaths).toEqual(['src/store/store.swift']);
        expect(files[0].content.match(/class Store/g)).toHaveLength(1);
    });
    it('leaves Java files in different packages and C/C++ structs untouched', () => {
        const java = [
            { path: 'src/a/a.java', content: 'package one;\nclass Row { }\n' },
            { path: 'src/b/b.java', content: 'package two;\nclass Row { }\n' },
        ];
        expect(resolveCrossFileDuplicates(java, [hint('src/a/a.java', 'java'), hint('src/b/b.java', 'java')]).changedPaths).toEqual([]);
        expect(java[1].content).toContain('class Row');
        // A struct in two translation units is required by the ODR, not a defect.
        const cpp = [
            { path: 'src/a/a.cpp', content: 'struct Point { int x; };\n' },
            { path: 'src/b/b.cpp', content: 'struct Point { int x; };\n' },
        ];
        const res = resolveCrossFileDuplicates(cpp, [hint('src/a/a.cpp', 'cpp'), hint('src/b/b.cpp', 'cpp')]);
        expect(res.changedPaths).toEqual([]);
        expect(res.failures).toEqual([]);
        expect(cpp[1].content).toContain('struct Point');
    });
    it('only considers files whose contract declares a resolvable language', () => {
        const files = [
            { path: 'src/a/a.swift', content: 'class Row { }\n' },
            { path: 'src/b/b.swift', content: 'class Row { }\n' },
        ];
        expect(resolveCrossFileDuplicates(files, []).changedPaths).toEqual([]);
        expect(files[0].content).toContain('class Row');
    });
    it('is idempotent — a second pass over the resolved set changes nothing', () => {
        const files = [
            { path: 'src/cli/cli.swift', content: SWIFT_CLI },
            { path: 'src/stats/stats.swift', content: SWIFT_STATS },
        ];
        const contracts = [hint('src/cli/cli.swift', 'swift'), hint('src/stats/stats.swift', 'swift')];
        resolveCrossFileDuplicates(files, contracts);
        const snapshot = files.map((f) => f.content);
        const second = resolveCrossFileDuplicates(files, contracts);
        expect(second.changedPaths).toEqual([]);
        expect(second.notes).toEqual([]);
        expect(files.map((f) => f.content)).toEqual(snapshot);
    });
});
/**
 * The REAL round-3 retest sources, verbatim from
 * /tmp/vaca-app-tests5/<app>/... — both apps failed their real toolchain
 * (`make` exit 2, `dotnet build` exit 1) purely on the redeclaration, and both
 * were DIVERGENT (neither definition contained the other), so these pin the
 * rename path rather than the delete path.
 */
describe('real round-3 failures (Swift + C#)', () => {
    it('removes the Swift TemperatureLog collision without orphaning cli.swift', () => {
        const cli = `import Foundation

class TemperatureLog {
    private var temperatures: [Double] = []

    func recordTemperature(_ temperature: Double) {
        temperatures.append(temperature)
    }

    func averageTemperature() -> Double? {
        guard !temperatures.isEmpty else { return nil }
        return temperatures.reduce(0, +) / Double(temperatures.count)
    }
}

func main() {
    let log = TemperatureLog()
    print("Temperature Log")
}
`;
        const stats = `import Foundation

class TemperatureLog {
    private var temperatures: [Double] = []

    func record(_ temp: Double) {
        temperatures.append(temp)
    }

    func average() -> Double? {
        guard !temperatures.isEmpty else { return nil }
        let sum = temperatures.reduce(0, +)
        return sum / Double(temperatures.count)
    }
}
`;
        const store = `import Foundation

class TemperatureStore {
    private var temperatures: [Double] = []
}
`;
        const entry = `import Foundation

print("starting...")

_ = TemperatureLog.self
main()
_ = TemperatureStore.self
_ = TemperatureLog.self`;
        const files = [
            { path: 'src/cli/cli.swift', content: cli },
            { path: 'src/stats/stats.swift', content: stats },
            { path: 'src/temp-store/temp-store.swift', content: store },
            { path: 'main.swift', content: entry },
        ];
        const res = resolveCrossFileDuplicates(files, [
            hint('src/cli/cli.swift', 'swift', 'Record temperatures from the command line and report the average'),
            hint('src/stats/stats.swift', 'swift', 'Record temperatures from the command line and report the average'),
            hint('src/temp-store/temp-store.swift', 'swift', 'Record temperatures from the command line and report the average'),
            hint('main.swift', 'swift'),
        ]);
        expect(res.failures).toEqual([]);
        const all = files.map((f) => f.content).join('\n');
        // Exactly ONE declaration keeps the contested name...
        expect((all.match(/\bclass TemperatureLog\b/g) || []).length).toBe(1);
        // ...and the other one survives under a node-qualified name.
        expect(all).toMatch(/\bclass (?:Cli|Stats)TemperatureLog\b/);
        // The renamed file's own constructor call was rewritten with it.
        const renamedFile = files.find((f) => /\bclass (?:Cli|Stats)TemperatureLog\b/.test(f.content));
        expect(renamedFile.content).toMatch(/= (?:Cli|Stats)TemperatureLog\(\)/);
        // The entry file was not touched: a bare `Type.self` resolves to the owner.
        expect(files[3].content).toBe(entry);
    });
    it('resolves the C# BudgetStore and BudgetEntry collisions by rename', () => {
        const budgetStore = `using System.Collections.Generic;

public class BudgetStore {
    private List<BudgetEntry> entries = new List<BudgetEntry>();

    public void AddEntry(BudgetEntry entry) {
        entries.Add(entry);
    }

    public double GetBalance() {
        double balance = 0;
        foreach (var entry in entries) {
            balance += entry.Amount;
        }
        return balance;
    }

    public List<BudgetEntry> GetEntries() {
        return entries;
    }
}

public class BudgetEntry {
    public string Description { get; set; }
    public double Amount { get; set; }

    public BudgetEntry(string description, double amount) {
        Description = description;
        Amount = amount;
    }
}`;
        const report = `public class BudgetStore
{
    private List<Entry> entries;

    public BudgetStore()
    {
        entries = new List<Entry>();
    }

    public decimal GetBalance()
    {
        decimal balance = 0;
        return balance;
    }

    public List<Entry> GetAllEntries()
    {
        return new List<Entry>();
    }
}

public class Entry
{
    public string Description { get; }
    public decimal Amount { get; }
}`;
        const cli = `using System;
using System.Collections.Generic;

class Program
{
    static void Main(string[] args)
    {
        var budgetEntries = new List<BudgetEntry>();
        var entry = new BudgetEntry { Category = "food", Amount = 10m };
        budgetEntries.Add(entry);
    }
}

class BudgetEntry
{
    public string Category { get; set; }
    public decimal Amount { get; set; }
}`;
        const files = [
            { path: 'src/budget-store/budget-store.cs', content: budgetStore },
            { path: 'src/report/report.cs', content: report },
            { path: 'src/cli/cli.cs', content: cli },
        ];
        const contracts = [
            hint('src/budget-store/budget-store.cs', 'csharp', '', ['BudgetStore', 'BudgetEntry']),
            hint('src/report/report.cs', 'csharp', '', ['BudgetStore', 'Entry']),
            hint('src/cli/cli.cs', 'csharp', '', ['Program', 'BudgetEntry', 'ReportGenerator']),
        ];
        const res = resolveCrossFileDuplicates(files, contracts);
        expect(res.failures).toEqual([]);
        const all = files.map((f) => f.content).join('\n');
        expect((all.match(/\bclass BudgetStore\b/g) || []).length).toBe(1);
        expect((all.match(/\bclass BudgetEntry\b/g) || []).length).toBe(1);
        // report.cs is not the store's owner (its dir does not derive the name), so
        // its copy is renamed; cli.cs's BudgetEntry is renamed for the same reason.
        expect(files[1].content).toContain('class ReportBudgetStore');
        expect(files[1].content).toContain('public ReportBudgetStore()');
        expect(files[2].content).toContain('class CliBudgetEntry');
        // Every use in the renamed files moved with the declaration...
        expect(files[2].content).toContain('new CliBudgetEntry');
        expect(files[2].content).not.toMatch(/\bBudgetEntry\b/);
        // ...and the exports metadata followed, so the stub gate stays quiet.
        expect(contracts[1].exports).toEqual(['ReportBudgetStore', 'Entry']);
        expect(contracts[2].exports).toEqual(['Program', 'CliBudgetEntry', 'ReportGenerator']);
        // The owner file is untouched.
        expect(files[0].content).toBe(budgetStore);
    });
});
