# Calculator

A dependency-free calculator app (HTML + vanilla JS, no build step).

Originally generated as a TypeScript class by VACA (`src/calculator.ts`);
this build wraps that logic in a working UI while keeping the typed class as
the reference implementation.

## Run

```bash
# any static server works — no install needed
python3 -m http.server 8000
# open http://localhost:8000
```

Or open `index.html` directly in a browser.

## What it does

- Full expression evaluation with operator precedence (`2 + 3 × 4 = 14`),
  parentheses, decimals, unary minus, and `%` (percent-of).
- Buttons + full keyboard support (digits, `+ - * / %`, `Enter` = `=`,
  `Backspace` delete, `Esc` clear).
- Division by zero is caught and shown on the display instead of crashing.
- All arithmetic runs through the `Calculator` class methods
  (add/subtract/multiply/divide) — the same API as `src/calculator.ts`.

## Files

| File | Purpose |
|------|---------|
| `index.html` | The UI (dark theme, display + key grid) |
| `calculator.js` | `Calculator` class mirror + expression parser + UI wiring |
| `src/calculator.ts` | VACA-generated typed reference implementation |

## Testing

The parser/class are exported for Node, so:

```bash
node -e "const {evaluate}=require('./calculator.js'); console.log(evaluate('2+3*4'))"  # 14
```
