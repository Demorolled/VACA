import { describe, it, expect } from 'vitest';
import { ROSETTA_TARGETS, parseSections, extractCodeBlocks, extractRosettaCode, htmlUnescape, stripWikiMarkup, stripOutputComments, isSubstantive, buildRosettaPatterns, rosettaTitle, } from './rosettaCode.js';
const target = (language) => ROSETTA_TARGETS.find((t) => t.language === language);
/** Mirrors real Rosetta wikitext, including its common quirks. */
const WIKITEXT = `
=={{header|Go}}==
<syntaxhighlight lang="go">
package main

import "fmt"

func main() {
	fmt.Println("hi")
}
</syntaxhighlight>

=={{header|Kotlin}}==
<syntaxhighlight lang="scala">
fun main() {
    println("hi")
}
</syntaxhighlight>
<syntaxhighlight lang="text">
hi
</syntaxhighlight>

=={{header|C sharp|C#}}==
<source lang="csharp">
using System;
class Program {
    static void Main() {
        Console.WriteLine("hi");
    }
}
</source>

=={{header|Python}}==
<syntaxhighlight lang="python">
>>> print("hi")
>>> print("again")
>>> print("third")
</syntaxhighlight>

=={{header|Ruby}}==
<syntaxhighlight lang="ruby">
puts "hi"
</syntaxhighlight>

=={{header|C++}}==
<syntaxhighlight lang="cpp">
#include &lt;iostream&gt;
int main() {
    std::cout &lt;&lt; "hi" &lt;&lt; std::endl;
    return 0;
}
</syntaxhighlight>
`;
describe('rosetta wikitext parsing', () => {
    it('splits sections on {{header}} markers, including piped aliases', () => {
        const sections = parseSections(WIKITEXT);
        const allAliases = sections.flatMap((s) => s.aliases);
        expect(allAliases).toContain('Go');
        expect(allAliases).toContain('C sharp');
        expect(allAliases).toContain('C#');
    });
    it('reads both <syntaxhighlight> and <source> blocks', () => {
        const wrap = parseSections(WIKITEXT);
        const csharp = wrap.find((s) => s.aliases.includes('C sharp'));
        const blocks = extractCodeBlocks(csharp.body);
        expect(blocks).toHaveLength(1);
        expect(blocks[0].lang).toBe('csharp');
        expect(blocks[0].code).toContain('using System;');
    });
    it('extracts a clean block for a normal section', () => {
        const code = extractRosettaCode(WIKITEXT, target('go'));
        expect(code).toContain('package main');
        expect(code).toContain('func main()');
    });
    it('falls back to the section header when lang= is wrong (Kotlin labelled scala)', () => {
        const code = extractRosettaCode(WIKITEXT, target('kotlin'));
        expect(code).toContain('fun main()');
        expect(code).not.toContain('lang=');
    });
    it('matches a piped C# header and unescapes HTML entities', () => {
        expect(extractRosettaCode(WIKITEXT, target('csharp'))).toContain('Console.WriteLine');
        const cpp = extractRosettaCode(WIKITEXT, target('cpp'));
        expect(cpp).toContain('#include <iostream>');
        expect(cpp).toContain('std::cout << "hi"');
    });
    it('returns null for a language the page does not contain', () => {
        expect(extractRosettaCode(WIKITEXT, target('rust'))).toBeNull();
    });
});
describe('snippet hygiene', () => {
    it('unescapes the HTML entities Rosetta serves for code', () => {
        expect(htmlUnescape('a &lt; b &amp;&amp; c &gt; d')).toBe('a < b && c > d');
    });
    it('strips wiki links and templates', () => {
        expect(stripWikiMarkup('see [[Rosetta Code|the wiki]] and {{works with|x}}')).toBe('see the wiki and ');
    });
    it('drops a trailing output comment block', () => {
        const code = 'print(1)\nprint(2)\n/* Output:\n1\n2\n*/';
        expect(stripOutputComments(code)).toBe('print(1)\nprint(2)');
    });
    it('rejects one-line idioms as non-substantive', () => {
        expect(isSubstantive('input()[::-1]')).toBe(false);
        expect(isSubstantive('width = 8  # plenty long enough to clear the length gate')).toBe(false);
    });
    it('rejects Python REPL transcripts but not Java unsigned-shift lines', () => {
        const repl = '>>> a = 1\n>>> b = 2\n>>> print(a + b)';
        expect(isSubstantive(repl, 'python')).toBe(false);
        // `>>>` mid-line is a valid Java/Kotlin unsigned shift, not a prompt.
        const java = 'int guess = (lo + hi) >>> 1;\nreturn guess;\n}';
        expect(isSubstantive(java, 'java')).toBe(true);
    });
    it('accepts real multi-line code', () => {
        expect(isSubstantive('package main\n\nfunc main() {\n\tprintln("hi")\n}', 'go')).toBe(true);
    });
    it('rejects residual wiki markup that leaked out of extraction', () => {
        expect(isSubstantive('a\nb\n{{not stripped}}')).toBe(false);
    });
});
describe('buildRosettaPatterns', () => {
    const report = buildRosettaPatterns([{ task: 'Demo', wikitext: WIKITEXT }]);
    const langs = new Set(report.patterns.map((p) => p.language));
    it('keeps languages with clean, substantive snippets', () => {
        expect(langs.has('go')).toBe(true);
        expect(langs.has('kotlin')).toBe(true);
        expect(langs.has('csharp')).toBe(true);
        expect(langs.has('cpp')).toBe(true);
    });
    it('drops the Python REPL transcript and the Ruby one-liner', () => {
        expect(langs.has('python')).toBe(false);
        expect(langs.has('ruby')).toBe(false);
        const reasons = report.rejected.map((r) => `${r.language}:${r.reason}`);
        expect(reasons).toContain('python:not-substantive');
        expect(reasons).toContain('ruby:not-substantive');
    });
    it('orders output by ROSETTA_TASKS, not by the order pages arrive', () => {
        // The MediaWiki titles= response is not in request order, so the corpus
        // must be re-ordered — otherwise which tasks the seed budget picks drifts.
        const page = (task, body) => ({
            task,
            wikitext: `=={{header|Go}}==\n<syntaxhighlight lang="go">\n${body}\n</syntaxhighlight>\n`,
        });
        const factorial = page('Factorial', 'package main\n\nfunc main() {\n\tprintln(1)\n}');
        const fizzbuzz = page('FizzBuzz', 'package main\n\nfunc main() {\n\tprintln(2)\n}');
        // Factorial is later in ROSETTA_TASKS than FizzBuzz, but passed first.
        const { patterns } = buildRosettaPatterns([factorial, fizzbuzz]);
        expect(patterns.map((p) => p.title)).toEqual([
            'rosetta — FizzBuzz (go)',
            'rosetta — Factorial (go)',
        ]);
    });
    it('tags every pattern for the store and records its source', () => {
        const go = report.patterns.find((p) => p.language === 'go');
        expect(go.title).toBe(rosettaTitle('Demo', 'go'));
        expect(go.tags).toContain('go');
        expect(go.tags).toContain('rosetta');
        expect(go.projectId).toBe('rosetta');
        expect(go.category).toBe('code_pattern');
        expect(go.qualityScore).toBeLessThan(8); // curated patterns must still outrank these
        expect(go.description).toContain('rosettacode.org');
    });
});
