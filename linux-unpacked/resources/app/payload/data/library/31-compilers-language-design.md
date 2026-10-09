# 🏗️ Compilers & Programming Language Design

> Reference sheet for the design and implementation of programming languages: lexing, parsing, type systems, code generation, runtime design, and optimization passes. Use this when building compilers, interpreters, DSLs, or when analyzing language performance characteristics.

**Source Bible Levels:** 11 — Language Design, 15 — Programming Languages

---

## 📐 The Compilation Pipeline

```
Source Code
    │
    ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐
│   Lexer     │───►│    Parser    │───►│ Type Checker│───►│    IR      │
│ (Tokenizer) │    │ (AST Builder)│    │ (Semantic)  │    │ (Middle-End)│
└─────────────┘    └──────────────┘    └─────────────┘    └─────┬──────┘
                                                                 │
                                                                 ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐
│  Machine    │◄───│   Code Gen   │◄───│   Optimizer │◄───│   IR Gen   │
│  Code       │    │  (Back-End)  │    │  (Opt Pass) │    │  (Middle)  │
└─────────────┘    └──────────────┘    └─────────────┘    └────────────┘
```

### Lexer (Tokenizer)

```typescript
// Token definitions
enum TokenType {
  // Literals
  Number, String, Boolean, Null,
  // Identifiers & Keywords
  Identifier, Let, Const, Function, Return, If, Else, While, For,
  // Operators
  Plus, Minus, Star, Slash, Equals, EqualsEquals, Bang, BangEquals,
  Less, Greater, LessEquals, GreaterEquals,
  // Delimiters
  LeftParen, RightParen, LeftBrace, RightBrace, LeftBracket, RightBracket,
  Semicolon, Comma, Dot, Colon, Arrow,
  // Special
  EOF, Error,
}

interface Token {
  type: TokenType;
  lexeme: string;
  literal: any;
  line: number;
  column: number;
}

class Lexer {
  private source: string;
  private start = 0;
  private current = 0;
  private line = 1;
  private tokens: Token[] = [];

  scanTokens(): Token[] {
    while (!this.isAtEnd()) {
      this.start = this.current;
      this.scanToken();
    }
    this.tokens.push({ type: TokenType.EOF, lexeme: '', literal: null, line: this.line, column: this.current });
    return this.tokens;
  }

  private scanToken(): void {
    const c = this.advance();
    switch (c) {
      case '(': this.addToken(TokenType.LeftParen); break;
      case ')': this.addToken(TokenType.RightParen); break;
      case '{': this.addToken(TokenType.LeftBrace); break;
      case '}': this.addToken(TokenType.RightBrace); break;
      case '+': this.addToken(TokenType.Plus); break;
      case '-':
        this.addToken(this.match('>') ? TokenType.Arrow : TokenType.Minus);
        break;
      case '*': this.addToken(TokenType.Star); break;
      case '!':
        this.addToken(this.match('=') ? TokenType.BangEquals : TokenType.Bang);
        break;
      case '=':
        this.addToken(this.match('=') ? TokenType.EqualsEquals : TokenType.Equals);
        break;
      case '/':
        if (this.match('/')) {
          // Single-line comment: consume until end of line
          while (this.peek() !== '\n' && !this.isAtEnd()) this.advance();
        } else {
          this.addToken(TokenType.Slash);
        }
        break;
      case ' ': case '\r': case '\t':
        // Skip whitespace
        break;
      case '\n':
        this.line++;
        break;
      case '"': this.string(); break;
      default:
        if (this.isDigit(c)) {
          this.number();
        } else if (this.isAlpha(c)) {
          this.identifier();
        } else {
          throw new Error(`Unexpected character '${c}' at line ${this.line}`);
        }
        break;
    }
  }

  // Helper methods: advance(), match(), peek(), addToken(), etc.
  private advance(): string { return this.source[this.current++]; }
  private match(expected: string): boolean {
    if (this.isAtEnd()) return false;
    if (this.source[this.current] !== expected) return false;
    this.current++;
    return true;
  }
  private peek(): string { return this.isAtEnd() ? '\0' : this.source[this.current]; }
  private addToken(type: TokenType, literal: any = null): void {
    this.tokens.push({ type, lexeme: this.source.slice(this.start, this.current), literal, line: this.line, column: this.start });
  }
}
```

### Parser — Recursive Descent

```typescript
// Expression AST nodes
type Expr =
  | { kind: 'Binary'; left: Expr; operator: Token; right: Expr }
  | { kind: 'Unary'; operator: Token; right: Expr }
  | { kind: 'Literal'; value: any }
  | { kind: 'Variable'; name: Token }
  | { kind: 'Assign'; name: Token; value: Expr }
  | { kind: 'Call'; callee: Expr; args: Expr[] }
  | { kind: 'Grouping'; expr: Expr }
  | { kind: 'Function'; params: Token[]; body: Stmt[] }
  | { kind: 'If'; condition: Expr; thenBranch: Stmt; elseBranch: Stmt | null };

type Stmt =
  | { kind: 'Expression'; expr: Expr }
  | { kind: 'Let'; name: Token; initializer: Expr | null }
  | { kind: 'Return'; value: Expr | null }
  | { kind: 'Block'; statements: Stmt[] }
  | { kind: 'FunctionDecl'; name: Token; function: Expr }
  | { kind: 'While'; condition: Expr; body: Stmt };

// Pratt parser for expressions with precedence climbing
enum Precedence {
  None, Assignment, Or, And, Equality, Comparison, Term, Factor, Unary, Call, Primary,
}

function parseExpression(precedence: Precedence = Precedence.None): Expr {
  let left = parsePrefix();  // Handles literals, variables, grouping, unary

  while (precedence <= getPrecedence(current().type)) {
    left = parseInfix(left);  // Handles binary operators, calls
  }

  return left;
}

// Example: parsing a simple arithmetic expression
function parseBinary(left: Expr): Expr {
  const operator = previous();
  const right = parseExpression(getPrecedence(operator.type) + 1);
  return { kind: 'Binary', left, operator, right };
}
```

---

## 🔤 Type Systems

### Core Type Theory Concepts

| Concept | Description | Example Language |
|---|---|---|
| **Simply Typed Lambda Calculus (STLC)** | Foundation for typed functional languages | Core ML |
| **Hindley-Milner Type Inference** | Algorithm W — unification + let-polymorphism | Haskell, OCaml |
| **Parametric Polymorphism** | Generics — type parameters, System F | Java, TypeScript |
| **Subtyping** | Structural vs nominal, variance (covariant/contravariant) | TypeScript, Scala |
| **Dependent Types** | Types parameterized by values (Π types, Σ types) | Idris, Coq |
| **Linear/Affine Types** | Resource-aware typing — each value used exactly once | Rust, ATS |
| **Gradual Typing** | Mix static and dynamic typing in same program | TypeScript, Typed Racket |

### Hindley-Milner Type Inference (Algorithm W)

```typescript
// Unification for HM type inference
type Type =
  | { kind: 'Var'; id: number }
  | { kind: 'Prim'; name: string }  // Int, Bool, String
  | { kind: 'Fn'; param: Type; return: Type }
  | { kind: 'App'; left: Type; right: Type };  // Type application

interface Substitution {
  apply(t: Type): Type;
  compose(other: Substitution): Substitution;
}

function unify(a: Type, b: Type): Substitution | null {
  if (a.kind === 'Var') return bindVariable(a.id, b);
  if (b.kind === 'Var') return bindVariable(b.id, a);
  if (a.kind === 'Prim' && b.kind === 'Prim' && a.name === b.name) return emptySubst();
  if (a.kind === 'Fn' && b.kind === 'Fn') {
    const s1 = unify(a.param, b.param);
    const s2 = unify(s1.apply(a.return), s1.apply(b.return));
    return s2.compose(s1);
  }
  throw new TypeError(`Cannot unify ${a} with ${b}`);
}

function inferType(expr: Expr, env: Map<string, Type>): { type: Type; subst: Substitution } {
  switch (expr.kind) {
    case 'Literal':
      return { type: typeofExpr(expr.value), subst: emptySubst() };
    case 'Variable': {
      const type = env.get(expr.name.lexeme);
      if (!type) throw new Error(`Undefined variable: ${expr.name.lexeme}`);
      // Create fresh type variables for let-polymorphism
      return { type: instantiate(type), subst: emptySubst() };
    }
    case 'Binary': {
      const left = inferType(expr.left, env);
      const right = inferType(expr.right, env);
      const s1 = unify(left.type, typeNumber());  // Both operands must be numbers
      const s2 = s1.compose(unify(s1.apply(right.type), typeNumber()));
      return { type: s2.apply(typeNumber()), subst: s2.compose(s1) };
    }
    case 'Function': {
      const paramTypes = expr.params.map(() => freshVar());
      const newEnv = new Map(env);
      for (let i = 0; i < expr.params.length; i++) {
        newEnv.set(expr.params[i].lexeme, paramTypes[i]);
      }
      const body = inferType(expr.body, newEnv);
      const fnType = paramTypes.reduceRight(
        (ret, param) => ({ kind: 'Fn', param, return: ret } as Type),
        body.type
      );
      return { type: fnType, subst: body.subst };
    }
    // ... other expression types
  }
}
```

### Subtyping System (Structural)

```typescript
// Structural subtyping with variance
type Variance = 'covariant' | 'contravariant' | 'invariant';

interface TypeRelation {
  isSubtype(sub: Type, sup: Type): boolean;
}

class StructuralTyping {
  isSubtype(sub: Type, sup: Type): boolean {
    // Reflexive
    if (sub === sup) return true;

    // Primitive widening (Int <: Float)
    if (sub.kind === 'Prim' && sup.kind === 'Prim') {
      return primWidening[sub.name] === sup.name;
    }

    // Function types: contravariant in parameter, covariant in return
    if (sub.kind === 'Fn' && sup.kind === 'Fn') {
      return (
        this.isSubtype(sup.param, sub.param) &&  // contravariant
        this.isSubtype(sub.return, sup.return)    // covariant
      );
    }

    // Record types: structural width + depth subtyping
    if (sub.kind === 'Record' && sup.kind === 'Record') {
      for (const [field, supType] of sup.fields) {
        const subType = sub.fields.get(field);
        if (!subType) return false;  // Missing field
        if (!this.isSubtype(subType, supType)) return false;
      }
      return true;
    }

    // Array types: covariant (mutable — unsound but common in TypeScript)
    if (sub.kind === 'Array' && sup.kind === 'Array') {
      return this.isSubtype(sub.element, sup.element);
    }

    return false;
  }
}
```

---

## ⚙️ Runtime Design

### Stack-Based Virtual Machine

```typescript
class VM {
  stack: Value[] = [];
  globals: Map<string, Value> = new Map();
  ip = 0;  // Instruction pointer
  code: OpCode[] = [];

  run(): void {
    while (this.ip < this.code.length) {
      const op = this.code[this.ip++];
      switch (op) {
        case OpCode.Constant: {
          const value = this.readConstant();
          this.stack.push(value);
          break;
        }
        case OpCode.Add: {
          const b = this.stack.pop() as number;
          const a = this.stack.pop() as number;
          this.stack.push(a + b);
          break;
        }
        case OpCode.Subtract: {
          const b = this.stack.pop() as number;
          const a = this.stack.pop() as number;
          this.stack.push(a - b);
          break;
        }
        case OpCode.Multiply: {
          const b = this.stack.pop() as number;
          const a = this.stack.pop() as number;
          this.stack.push(a * b);
          break;
        }
        case OpCode.Divide: {
          const b = this.stack.pop() as number;
          const a = this.stack.pop() as number;
          if (b === 0) throw new RuntimeError('Division by zero');
          this.stack.push(a / b);
          break;
        }
        case OpCode.Call: {
          const argCount = this.readByte();
          const callee = this.stack[this.stack.length - 1 - argCount];
          if (typeof callee === 'function') {
            const args = this.stack.splice(this.stack.length - argCount, argCount);
            this.stack.pop(); // Remove callee
            const result = callee(...args);
            this.stack.push(result);
          } else {
            throw new RuntimeError('Can only call functions');
          }
          break;
        }
        case OpCode.Return: {
          return;  // Exit VM
        }
      }
    }
  }

  private readByte(): number { return this.code[this.ip++] as number; }
  private readConstant(): Value {
    const index = this.readByte();
    return this.constants[index];
  }
}
```

### Garbage Collection — Mark-Sweep

```typescript
interface GCObject {
  marked: boolean;
  next: GCObject | null;
  // Object-specific data
}

class GC {
  objects: GCObject | null = null;  // Linked list of all objects
  roots: Value[] = [];

  allocate(size: number): GCObject {
    const obj: GCObject = { marked: false, next: this.objects };
    this.objects = obj;
    return obj;
  }

  collect(): void {
    // Mark phase — trace from roots
    this.markRoots();

    // Sweep phase — free unmarked objects
    let obj = this.objects;
    let prev: GCObject | null = null;

    while (obj !== null) {
      if (!obj.marked) {
        // Free this object
        if (prev === null) {
          this.objects = obj.next;
        } else {
          prev.next = obj.next;
        }
        const toFree = obj;
        obj = obj.next;
        freeObject(toFree);
      } else {
        obj.marked = false;  // Reset for next GC
        prev = obj;
        obj = obj.next;
      }
    }
  }

  private markRoots(): void {
    for (const root of this.roots) {
      this.markValue(root);
    }
  }

  private markValue(value: Value): void {
    if (!isObject(value)) return;
    const obj = value.asObject;
    if (obj.marked) return;
    obj.marked = true;

    // Mark all references from this object
    for (const ref of getReferences(obj)) {
      this.markValue(ref);
    }
  }
}
```

---

## 🔄 Intermediate Representations & Optimization

### SSA Form (Static Single Assignment)

```
// Original:
x = a + b
x = x * c
y = x + d

// SSA Form (with Φ-functions at join points):
x1 = a + b
x2 = x1 * c
y1 = x2 + d
```

### Optimization Passes

```typescript
class Optimizer {
  optimize(ir: IRFunction): IRFunction {
    let changed = true;
    while (changed) {
      changed = false;
      changed ||= this.constantFolding(ir);
      changed ||= this.deadCodeElimination(ir);
      changed ||= this.commonSubexpressionElimination(ir);
      changed ||= this.copyPropagation(ir);
      changed ||= this.loopInvariantHoisting(ir);
      changed ||= this.inlineSmallFunctions(ir);
    }
    return ir;
  }

  // Constant Folding
  constantFolding(ir: IRFunction): boolean {
    let changed = false;
    for (const block of ir.blocks) {
      for (const instr of block.instructions) {
        if (isAdd(instr) && isConst(instr.left) && isConst(instr.right)) {
          instr.replaceWith(constInstr(instr.left.value + instr.right.value));
          changed = true;
        }
        // Similar for sub, mul, div, etc.
      }
    }
    return changed;
  }

  // Dead Code Elimination
  deadCodeElimination(ir: IRFunction): boolean {
    // Mark all instructions that have side effects (store, call, return, branch)
    // Any unmarked instruction whose result is never used is dead
    let changed = false;
    for (const block of ir.blocks) {
      block.instructions = block.instructions.filter(instr => {
        if (instr.hasSideEffect) return true;
        if (instr.users.size > 0) return true;
        changed = true;
        return false;  // Remove dead instruction
      });
    }
    return changed;
  }

  // Loop Invariant Code Motion
  loopInvariantHoisting(ir: IRFunction): boolean {
    for (const loop of ir.naturalLoops) {
      for (const block of loop.body) {
        for (const instr of block.instructions) {
          if (isInvariant(instr, loop)) {
            // Hoist to pre-header block
            loop.preHeader.instructions.push(instr);
            block.instructions.delete(instr);
          }
        }
      }
    }
    return true;
  }
}
```

---

## 🧩 DSL Design Patterns

```typescript
// Internal DSL (embedded in host language)
class QueryBuilder {
  private conditions: string[] = [];
  private orderField: string | null = null;
  private limitCount: number | null = null;

  select(fields: string[]): this {
    this.fields = fields;
    return this;
  }

  from(table: string): this {
    this.table = table;
    return this;
  }

  where(condition: string): this {
    this.conditions.push(condition);
    return this;
  }

  orderBy(field: string, dir: 'asc' | 'desc' = 'asc'): this {
    this.orderField = `${field} ${dir}`;
    return this;
  }

  limit(n: number): this {
    this.limitCount = n;
    return this;
  }

  build(): string {
    let sql = `SELECT ${this.fields.join(', ')} FROM ${this.table}`;
    if (this.conditions.length > 0) {
      sql += ` WHERE ${this.conditions.join(' AND ')}`;
    }
    if (this.orderField) sql += ` ORDER BY ${this.orderField}`;
    if (this.limitCount) sql += ` LIMIT ${this.limitCount}`;
    return sql;
  }
}

// Usage: new QueryBuilder().select(['name', 'age']).from('users').where('age > 21').build()

// External DSL — PEG parser (using Ohm/Lark style)
// grammar Calculator {
//   Expr     = AddExpr;
//   AddExpr  = MulExpr (("+" | "-") MulExpr)*;
//   MulExpr  = Prim   (("*" | "/") Prim)*;
//   Prim     = Number | "(" Expr ")";
//   Number   = digit+;
// }
```

---

## 📊 Quick Reference: Compilers & Language Design by Node Type

| Node Type | Relevant Concepts | Implementation Notes |
|---|---|---|
| **Input** | Lexer/tokenizer, parser combinators | Use character-by-character state machines for tokenization; implement Pratt parsing for expressions |
| **Logic** | Type inference, SSA construction, optimization passes | Implement Hindley-Milner inference for implicit typing; use SSA form for optimization-friendly IR |
| **Database** | Symbol table, scope chains, environment maps | Use persistent data structures for scoped symbol tables; implement lexical scoping with linked environments |
| **UI** | Syntax highlighting, error messages, autocomplete | Use incremental parsing for responsive editors; implement linter rules via AST visitors |
| **API** | Language server protocol (LSP), bytecode serialization | Implement LSP protocol for IDE integration; use binary format for bytecode serialization |
| **Output** | Code generation (assembly, bytecode, source), runtime VM | Emit platform-specific machine code via JIT; implement stack-based VM for portability |

---

*For deeper technical details on any compiler or language design concept, see Bible Levels 11 — Language Design and 15 — Programming Languages, including formal semantics, parser theory, and advanced type systems.*
