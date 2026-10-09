/**
 * calculator.js — browser build of the Calculator app.
 *
 * The typed reference implementation lives in src/calculator.ts (VACA-built).
 * This file mirrors that class 1:1 so the app runs with zero build tooling,
 * then adds the expression parser + UI wiring.
 *
 * Works in the browser (window.Calculator) and in Node (module.exports)
 * so the logic is unit-testable without a DOM.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.CalculatorApp = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ── Mirror of src/calculator.ts ────────────────────────────────
  class Calculator {
    add(a, b) {
      return a + b;
    }
    subtract(a, b) {
      return a - b;
    }
    multiply(a, b) {
      return a * b;
    }
    divide(a, b) {
      if (b === 0) throw new Error("Division by zero!");
      return a / b;
    }
  }

  // ── Expression evaluator (recursive descent, all ops via Calculator) ──
  function tokenize(expr) {
    const tokens = [];
    const re = /\s*(?:(\d+\.?\d*|\.\d+)|([+\-*/%()]))/g;
    let m;
    while ((m = re.exec(expr)) !== null) {
      if (m[1] !== undefined) tokens.push({ type: "num", value: parseFloat(m[1]) });
      else tokens.push({ type: "op", value: m[2] });
    }
    return tokens;
  }

  class Parser {
    constructor(tokens, calc) {
      this.tokens = tokens;
      this.pos = 0;
      this.calc = calc;
    }
    peek() {
      return this.tokens[this.pos] || null;
    }
    next() {
      return this.tokens[this.pos++] || null;
    }
    parse() {
      const v = this.expr();
      if (this.peek() !== null) throw new Error("Unexpected input");
      return v;
    }
    // expr := term (('+' | '-') term)*
    expr() {
      let v = this.term();
      let t;
      while ((t = this.peek()) && t.type === "op" && (t.value === "+" || t.value === "-")) {
        this.next();
        const r = this.term();
        v = t.value === "+" ? this.calc.add(v, r) : this.calc.subtract(v, r);
      }
      return v;
    }
    // term := factor (('*' | '/' | '%') factor)*
    term() {
      let v = this.factor();
      let t;
      while ((t = this.peek()) && t.type === "op" && (t.value === "*" || t.value === "/" || t.value === "%")) {
        this.next();
        const r = this.factor();
        if (t.value === "*") v = this.calc.multiply(v, r);
        else if (t.value === "/") v = this.calc.divide(v, r);
        else v = this.calc.multiply(v, this.calc.divide(r, 100));
      }
      return v;
    }
    // factor := number | '-' factor | '(' expr ')'
    factor() {
      const t = this.next();
      if (!t) throw new Error("Incomplete expression");
      if (t.type === "num") return t.value;
      if (t.type === "op" && t.value === "-") return this.calc.subtract(0, this.factor());
      if (t.type === "op" && t.value === "(") {
        const v = this.expr();
        const close = this.next();
        if (!close || close.type !== "op" || close.value !== ")") throw new Error("Missing closing parenthesis");
        return v;
      }
      throw new Error("Unexpected input");
    }
  }

  function evaluate(expr, calc) {
    if (!expr || !expr.trim()) return null;
    const value = new Parser(tokenize(expr), calc || new Calculator()).parse();
    // Round away float noise (0.1 + 0.2 → 0.3).
    return Math.round(value * 1e10) / 1e10;
  }

  // ── UI wiring (browser only) ───────────────────────────────────
  function initUI() {
    const calc = new Calculator();
    const exprEl = document.getElementById("expr");
    const resultEl = document.getElementById("result");
    let expression = "";
    let error = null;

    function render() {
      exprEl.textContent = expression || "0";
      resultEl.textContent = error ? error : expression ? "= " + String(evaluate(expression, calc)) : "\u00a0";
    }

    function showError(msg) {
      error = msg;
      resultEl.textContent = msg;
      exprEl.textContent = expression || "0";
    }

    function handleKey(key) {
      if (error && key !== "C" && key !== "Backspace") {
        expression = "";
        error = null;
      }
      if (/\d|\./.test(key)) {
        expression += key;
      } else if (key === "+" || key === "-" || key === "*" || key === "/" || key === "%") {
        if (expression === "") {
          if (key === "-") expression = "-";
          return;
        }
        expression += key;
      } else if (key === "C") {
        expression = "";
        error = null;
      } else if (key === "Backspace") {
        expression = expression.slice(0, -1);
      } else if (key === "=" || key === "Enter") {
        if (!expression) return;
        try {
          const v = evaluate(expression, calc);
          expression = String(v);
          error = null;
        } catch (e) {
          showError(e.message);
          return;
        }
      } else if (key === "±") {
        expression = expression.startsWith("-") ? expression.slice(1) : "-" + expression;
      }
      error = null;
      render();
    }

    const keys = "789/456*123-0.=+C%±";
    const grid = document.getElementById("keys");
    if (grid) {
      for (const k of keys) {
        const btn = document.createElement("button");
        btn.textContent = k;
        btn.className = /[0-9.]/.test(k) ? "digit" : k === "C" ? "danger" : "op";
        btn.addEventListener("click", () => handleKey(k === "=" ? "=" : k));
        grid.appendChild(btn);
      }
      // '=' separate wide button
      const eq = document.createElement("button");
      eq.textContent = "=";
      eq.className = "equals";
      eq.addEventListener("click", () => handleKey("="));
      grid.appendChild(eq);
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" || e.key === "Enter" || e.key === "Escape") {
        e.preventDefault();
        handleKey(e.key === "Escape" ? "C" : e.key);
      } else if (/^[0-9+\-*/.%]$/.test(e.key)) {
        handleKey(e.key);
      }
    });

    render();
  }

  if (typeof document !== "undefined" && document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initUI);
  } else if (typeof document !== "undefined") {
    initUI();
  }

  return { Calculator, evaluate };
});
