# ✅ Formal Methods & Program Verification

> Reference for formal methods in software engineering — model checking, theorem proving, SAT/SMT solvers, static analysis, and verification-driven development.
> Extracted from The Programming Bible's Formal Methods & Tools level.

---

## 1. Formal Methods Landscape

### Verification Techniques

| Technique | What It Proves | Automation | Scalability |
|---|---|---|---|
| **Model Checking** | Temporal properties of state machines | Full | Moderate |
| **Theorem Proving** | Mathematical correctness | Interactive | High |
| **SAT/SMT Solving** | Propositional/satisfiability | Full | Very high |
| **Static Analysis** | Code properties (null safety, bounds) | Full | High |
| **Abstract Interpretation** | Program invariants | Full | High |
| **Runtime Verification** | Execution traces | Monitoring | Very high |
| **Symbolic Execution** | Path feasibility | Partial | Low |
| **Fuzzing** | Crash detection | Full | Very high |

### When to Apply Formal Methods

| Criticality Level | When to Use | Methods |
|---|---|---|
| **Safety-critical** (avionics, medical) | Always — certification required | Model checking, theorem proving |
| **Security-critical** (crypto, auth) | High-value components | SMT, symbolic execution, fuzzing |
| **Infrastructure** (databases, kernels) | Core algorithms | Model checking, TLA+ |
| **Business logic** (fintech, contracts) | Complex state machines | TLA+, Alloy, invariants |
| **General code** | API contracts, data types | Type systems, static analysis |

---

## 2. TLA+ & Model Checking

### TLA+ Specification (Raft Leader Election)

```tla
------------------------ MODULE RaftElection ------------------------
EXTENDS Integers, TLC, FiniteSets

CONSTANTS Server, Majority
VARIABLES term, votedFor, leader, state

(* State machine *)
TypeOK ≜
    ∧ term ∈ [Server → Nat]
    ∧ votedFor ∈ [Server → Server ∪ {NONE}]
    ∧ leader ∈ [Server → BOOLEAN]
    ∧ state ∈ [Server → {"follower", "candidate", "leader"}]

Init ≜
    ∧ term = [s ∈ Server ↦ 0]
    ∧ votedFor = [s ∈ Server ↦ NONE]
    ∧ leader = [s ∈ Server ↦ FALSE]
    ∧ state = [s ∈ Server ↦ "follower"]

(* Election timeout — start new election *)
BecomeCandidate(s) ≜
    ∧ state[s] = "follower"
    ∧ term' = [term EXCEPT ![s] = @ + 1]
    ∧ votedFor' = [votedFor EXCEPT ![s] = s]
    ∧ state' = [state EXCEPT ![s] = "candidate"]
    ∧ UNCHANGED leader

(* Vote for candidate *)
VoteFor(s, c) ≜
    ∧ state[s] = "follower"
    ∧ votedFor[s] = NONE
    ∧ term[c] ≥ term[s]
    ∧ votedFor' = [votedFor EXCEPT ![s] = c]
    ∧ UNCHANGED ⟨term, leader, state⟩

(* Win election with majority *)
WinElection(s) ≜
    ∧ state[s] = "candidate"
    ∧ Cardinality({s2 ∈ Server : votedFor[s2] = s}) ≥ Majority
    ∧ leader' = [leader EXCEPT ![s] = TRUE]
    ∧ state' = [state EXCEPT ![s] = "leader"]
    ∧ UNCHANGED ⟨term, votedFor⟩

Next ≜
    ∨ ∃ s ∈ Server : BecomeCandidate(s)
    ∨ ∃ s, c ∈ Server : VoteFor(s, c)
    ∨ ∃ s ∈ Server : WinElection(s)

(* Safety: at most one leader per term *)
Safety ≜ ∀ t ∈ Nat :
    Cardinality({s ∈ Server : leader[s] ∧ term[s] = t}) ≤ 1

Spec ≜ Init ∧ □[Next]_⟨term, votedFor, leader, state⟩
=============================================================================
```

### Model Checking with TLC

```bash
# Run TLC model checker on TLA+ spec
java -cp tla2tools.jar tlc2.TLC RaftElection.tla \
    -workers 4 \
    -deadlock \
    -config RaftElection.cfg \
    -coverage 1

# Expected output:
# Progress: 1,834 states generated, 2,312 distinct states found
# Error: Invariant Safety violated for term 3
# The behavior up to this point is:
# 1: <Initial predicate>
# 2: BecomeCandidate(server1)
# 3: ...
```

---

## 3. SAT & SMT Solvers

### SAT Solving (MiniSat Style)

```typescript
// Simple CDCL SAT solver (conceptual)
interface CNFClause {
    literals: number[];  // Positive = variable, Negative = ¬variable
}

class CDCLSolver {
    private clauses: CNFClause[] = [];
    private assignment: Map<number, boolean> = new Map();
    private implicationGraph: Map<number, number[]> = new Map();

    addClause(literals: number[]): void {
        this.clauses.push({ literals });
    }

    solve(): Map<number, boolean> | null {
        while (true) {
            // 1. Unit propagation
            while (this.hasUnitClause()) {
                const unit = this.findUnitClause();
                this.assign(unit.literal, unit.value);

                // Check for conflict
                if (this.hasConflict()) {
                    const learnt = this.analyzeConflict();
                    if (!learnt) return null; // Unsatisfiable
                    this.backjump(learnt);
                }
            }

            // 2. All variables assigned → satisfiable
            if (this.allAssigned()) return this.assignment;

            // 3. Decide — pick unassigned variable
            const var = this.pickBranchingVariable();
            this.assign(var, true); // Try true first
            this.addDecisionLevel();
        }
    }

    private hasUnitClause(): boolean {
        return this.clauses.some(c => {
            const unassigned = c.literals.filter(l => !this.assignment.has(Math.abs(l)));
            const satisfied = c.literals.some(l =>
                this.assignment.get(Math.abs(l)) === (l > 0)
            );
            return !satisfied && unassigned.length === 1;
        });
    }

    private analyzeConflict(): number | null {
        // 1UIP (First Unique Implication Point) learning
        // Returns the asserting clause or null if conflict at decision level 0
        return null; // Simplified
    }

    private backjump(learntClause: number): void {
        // Backtrack to appropriate decision level
        // Add learned clause to clause database
        // Continue propagation
    }
}
```

### Z3 SMT Solver (Python)

```python
# Z3 SMT solver example — program verification
from z3 import *

# Symbolic variables
x = Int('x')
y = Int('y')
z = Int('z')

# Create solver
s = Solver()

# Add constraints (the program)
s.add(x > 0)
s.add(y > 0)
s.add(z == x + y)

# Property to verify: z > 0
s.add(Not(z > 0))

# If unsat, property holds
result = s.check()
if result == unsat:
    print("✅ Property verified: z is always > 0")
elif result == sat:
    print(f"❌ Counterexample: x={s.model()[x]}, y={s.model()[y]}, z={s.model()[z]}")
else:
    print("Unknown")

# More complex: array bounds checking
arr = Array('arr', IntSort(), IntSort())
idx = Int('idx')
solver = Solver()
solver.add(idx >= 0, idx < 10)

# Property: arr[idx] is always safe
solver.add(Not(And(idx >= 0, idx < 10)))
print(solver.check())  # unsat = safe
```

---

## 4. Static Analysis

### Abstract Interpretation Framework

```typescript
// Simple interval abstract domain
type Interval = { low: number; high: number } | 'bottom';

function join(a: Interval, b: Interval): Interval {
    if (a === 'bottom') return b;
    if (b === 'bottom') return a;
    return {
        low: Math.min(a.low, b.low),
        high: Math.max(a.high, b.high),
    };
}

function meet(a: Interval, b: Interval): Interval {
    if (a === 'bottom' || b === 'bottom') return 'bottom';
    const result = {
        low: Math.max(a.low, b.low),
        high: Math.min(a.high, b.high),
    };
    return result.low <= result.high ? result : 'bottom';
}

// ZeroDivision analysis
class DivisionAnalyzer {
    analyze(numerator: Interval, denominator: Interval): Interval | 'error' {
        if (denominator === 'bottom') return 'error';
        if (denominator.low <= 0 && denominator.high >= 0) {
            return 'error'; // Potential division by zero
        }

        // Safe division
        const posDenom = denominator.low > 0 ? denominator : { low: 1, high: denominator.high };
        const negDenom = denominator.high < 0 ? denominator : { low: denominator.low, high: -1 };

        return join(
            { low: numerator.low / posDenom.high, high: numerator.high / posDenom.low },
            { low: numerator.high / negDenom.low, high: numerator.low / negDenom.high }
        );
    }
}
```

---

## 5. Verification-Driven Development

### Design by Contract

```typescript
// Contract-based design — preconditions, postconditions, invariants
class BankAccount {
    private balance: number = 0;

    // Invariant
    private checkInvariant(): void {
        if (this.balance < 0) {
            throw new Error('Invariant violation: balance cannot be negative');
        }
    }

    // Precondition: amount > 0
    // Postcondition: balance increases by amount
    deposit(amount: number): void {
        // Precondition check
        if (amount <= 0) throw new Error('Precondition: amount must be positive');

        const oldBalance = this.balance;
        this.balance += amount;

        // Postcondition check
        if (this.balance !== oldBalance + amount) {
            throw new Error('Postcondition violation');
        }

        this.checkInvariant();
    }

    // Precondition: amount > 0 AND amount <= balance
    // Postcondition: balance decreases by amount
    withdraw(amount: number): void {
        if (amount <= 0) throw new Error('Amount must be positive');
        if (amount > this.balance) throw new Error('Insufficient funds');

        const oldBalance = this.balance;
        this.balance -= amount;

        if (this.balance !== oldBalance - amount) {
            throw new Error('Postcondition violation');
        }

        this.checkInvariant();
    }
}
```

### Property-Based Testing

```typescript
// Property-based testing with fast-check
import * as fc from 'fast-check';

describe('Array operations', () => {
    it('reverse(reverse(arr)) === arr (involution)', () => {
        fc.assert(
            fc.property(fc.array(fc.anything()), (arr) => {
                const reversed = arr.slice().reverse();
                const doubleReversed = reversed.slice().reverse();
                expect(doubleReversed).toEqual(arr);
            })
        );
    });

    it('sort(sort(arr)) === sort(arr) (idempotent)', () => {
        fc.assert(
            fc.property(fc.array(fc.integer()), (arr) => {
                const sorted = arr.slice().sort((a, b) => a - b);
                const doubleSorted = sorted.slice().sort((a, b) => a - b);
                expect(doubleSorted).toEqual(sorted);
            })
        );
    });
});
```

---

## Quick Reference: Formal Methods by Node Type

| Node Type | Formal Methods Mapping |
|---|---|
| **Input** | Input validation (preconditions), schema verification, sanitization proof |
| **Logic** | Invariant checking, contract enforcement, state machine verification, SAT solving |
| **Database** | Integrity constraint verification, transaction isolation proof |
| **UI** | State consistency verification, form validation contracts |
| **API** | API contract verification (OpenAPI), rate limiting, authorization proof |

---

*For deeper formal methods, see Bible levels `19-formal-methods-tools/`, `15-programming-languages/` (program verification), and `14-cryptography-security/` (formal verification of crypto).*
