#!/usr/bin/env python3
"""
Generate Per-File Generation Training Examples
===============================================
Creates curated {instruction, input, output, source} JSONL examples that teach
the VACA model the per-file generation step: given a blueprint plan entry
(path, summary, language, exports, uses), how to write THAT file so the whole
multi-file program compiles by construction.

The lessons are hand-authored ground truth (never LLM output) and pair a
realistic generation instruction with a complete, VALID file:

  - exports  → the ONLY public API the file may define (all present, nothing extra)
  - uses     → the ONLY imports allowed (dependency direction: ui → services → repo → models)
  - summary  → the file's one responsibility
  - path     → the exact package/module/namespace the file targets

Concrete code examples are NEVER truncated (same rule as the code-lessons and
large-program generators). Prose rules-of-thumb are capped at MAX_OUTPUT_CHARS.

Validation: every concrete sample is (1) syntax-checked via the checkers in
scripts/validate-code-lessons.py (Python py_compile, Go gofmt -e, TypeScript
tsc --strict, SQL sqlite3, C# structural) and (2) contract-checked via
scripts/check-file-generation-contracts.py — the file's actual public API and
imports must match its plan entry's exports/uses exactly. The merge aborts if
any sample fails either check (--skip-validation to opt out).

Output:
  - training/dataset/file-generation-examples.jsonl
  - Merges into training/dataset/{train,val,test}.jsonl: new examples GUARANTEED
    into train, existing pool deduped (new wins), then split 80/10/10. Backs up
    existing splits first.

Usage:
  python3 scripts/generate-file-generation-examples.py [--dry-run]
"""

import json, random, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
DS_DIR = ROOT / "training" / "dataset"
NEW_OUT = DS_DIR / "file-generation-examples.jsonl"

MAX_OUTPUT_CHARS = 4000  # cap applies only to prose rule-of-thumb examples


def make(instruction: str, output: str, source: str):
    return {"instruction": instruction, "input": "", "output": output, "source": source}


# ─── Concrete per-file lessons (hand-authored, NEVER truncated) ──────────────
# Each example is a realistic "generate one file" request whose output is a
# complete file honoring its plan entry: exports present, uses-only imports,
# one responsibility, package derived from path.

def code_lesson(instruction: str, output: str, source: str):
    return make(instruction, output, source)


# ─── Transferable prose rules (capped by MAX_OUTPUT_CHARS) ──────────────────

def rule(title: str, body: str, source: str):
    out = f"""Per-file generation rule: {title}

{body}"""
    return make(f"Explain the per-file generation rule: {title.lower()}.", out[:MAX_OUTPUT_CHARS], source)


def build_examples() -> list:
    examples = []

    # 1. Go model file — imports NOTHING, exports exactly Order + OrderStatus.
    examples.append(code_lesson(
        "Generate the Go file for the node \"order_model\" whose plan entry is: "
        "path internal/models/order.go, summary 'Order entity + status types', "
        "exports [Order, OrderStatus], uses []. The build system adds imports.",
        """package order_model

// Plan: internal/models/order.go — Order entity + status types.
// Exports: Order, OrderStatus. Uses: none — models import nothing.
// The build system adds any imports needed; this file is dependency-free.
// Note: only the two planned exports are public — the status constants and
// the line-item type are private (lowercase), exactly as the contract demands.

type OrderStatus string

const (
	statusPending   OrderStatus = "pending"
	statusPaid      OrderStatus = "paid"
	statusShipped   OrderStatus = "shipped"
	statusCancelled OrderStatus = "cancelled"
)

type Order struct {
	ID         string
	CustomerID string
	Items      []orderItem
	TotalCents int64
	Status     OrderStatus
}

type orderItem struct {
	ProductID string
	Quantity  int
	UnitCents int64
}
""",
        "file-generation → order_model.go (Go)",
    ))

    # 2. Go repository file — uses ONLY internal/models Order.
    examples.append(code_lesson(
        "Generate the Go file for the node \"order_repo\" whose plan entry is: "
        "path internal/repository/order_repo.go, summary 'Order persistence: CRUD + status updates', "
        "exports [OrderRepo, NewOrderRepo], uses [{from internal/models, members [Order]}]. "
        "The build system adds imports from uses.",
        """package order_repo

// Plan: internal/repository/order_repo.go — Order persistence.
// Exports: OrderRepo, NewOrderRepo. Uses: internal/models → Order only.
// Import statements are added by the build system from the uses contract.

type OrderRepo struct {
	store map[string]*Order
}

func NewOrderRepo() *OrderRepo {
	return &OrderRepo{store: make(map[string]*Order)}
}

func (r *OrderRepo) Save(o *Order) error {
	r.store[o.ID] = o
	return nil
}

func (r *OrderRepo) ByID(id string) (*Order, error) {
	if o, ok := r.store[id]; ok {
		return o, nil
	}
	return nil, errNotFound
}

// errNotFound is private: only OrderRepo and NewOrderRepo are in exports.
type notFoundError struct{}

func (e *notFoundError) Error() string { return "order not found" }

var errNotFound = &notFoundError{}
""",
        "file-generation → order_repo.go (Go)",
    ))

    # 3. Go service file — uses repo + models, exports exactly the service pair.
    examples.append(code_lesson(
        "Generate the Go file for the node \"order_service\" whose plan entry is: "
        "path internal/service/order_service.go, summary 'Order business rules: creation, totals, status flow', "
        "exports [OrderService, NewOrderService], uses [{from internal/repository, members [OrderRepo]}, "
        "{from internal/models, members [Order, OrderStatus]}]. The build system adds imports from uses.",
        """package order_service

// Plan: internal/service/order_service.go — order business rules.
// Exports: OrderService, NewOrderService. Uses: repository → OrderRepo;
// models → Order, OrderStatus. Handlers may never import the repo directly.
// Note: only the two planned exports are public — the error type below is
// private (lowercase), exactly as the contract demands.

type OrderService struct {
	repo *OrderRepo
}

func NewOrderService(repo *OrderRepo) *OrderService {
	return &OrderService{repo: repo}
}

func (s *OrderService) Create(o *Order) error {
	if len(o.Items) == 0 {
		return errEmptyOrder
	}
	return s.repo.Save(o)
}

func (s *OrderService) MarkPaid(id string) error {
	o, err := s.repo.ByID(id)
	if err != nil {
		return err
	}
	o.Status = OrderStatus("paid")
	return s.repo.Save(o)
}

// errEmptyOrder is private: it is NOT in the planned exports list.
type emptyOrderError struct{}

func (e *emptyOrderError) Error() string { return "order has no items" }

var errEmptyOrder = &emptyOrderError{}
""",
        "file-generation → order_service.go (Go)",
    ))

    # 4. TypeScript model file — export interface + type guard, no deps.
    examples.append(code_lesson(
        "Generate the TypeScript file for the node \"user_model\" whose plan entry is: "
        "path src/models/user.ts, summary 'User entity + type guard', exports [User, isUser], uses []. "
        "No JSX, no imports — models depend on nothing.",
        """// Plan: src/models/user.ts — User entity + type guard.
// Exports: User, isUser. Uses: none — models import nothing.

export interface User {
  id: string;
  email: string;
  displayName: string;
  role: 'user' | 'admin';
}

export function isUser(v: unknown): v is User {
  if (typeof v !== 'object' || v === null) return false;
  const u = v as Record<string, unknown>;
  return typeof u.id === 'string' &&
    typeof u.email === 'string' &&
    typeof u.displayName === 'string' &&
    (u.role === 'user' || u.role === 'admin');
}
""",
        "file-generation → user_model.ts (TypeScript)",
    ))

    # 5. TypeScript service file — uses the repo per contract (typed via the
    #    uses member; import statements are stripped by the build).
    examples.append(code_lesson(
        "Generate the TypeScript file for the node \"user_service\" whose plan entry is: "
        "path src/services/user_service.ts, summary 'User business rules: register, profile, lookup', "
        "exports [UserService], uses [{from src/repositories/user_repo, members [UserRepo]}, "
        "{from src/models/user, members [User]}]. The build system strips import statements but keeps export declarations.",
        """// Plan: src/services/user_service.ts — user business rules.
// Exports: UserService. Uses: src/repositories/user_repo → UserRepo;
// src/models/user → User. Services never import handlers; handlers may never
// import repositories directly. Import statements are added by the build;
// the declarations below are stand-ins so this sample type-checks alone.

// import { UserRepo } from '../repositories/user_repo'; // added by build
// import type { User } from '../models/user';            // added by build

type UserRepo = {
  create(input: { email: string; displayName: string }): Promise<User>;
  findById(id: string): Promise<User | null>;
};

type User = {
  id: string;
  email: string;
  displayName: string;
};

export class UserService {
  constructor(private readonly repo: UserRepo) {}

  async register(email: string, displayName: string): Promise<User> {
    if (!email.includes('@')) {
      throw new Error('invalid email');
    }
    return this.repo.create({ email, displayName });
  }

  async getProfile(id: string): Promise<User | null> {
    return this.repo.findById(id);
  }
}
""",
        "file-generation → user_service.ts (TypeScript)",
    ))

    # 6. Python model file — dataclass, no imports.
    examples.append(code_lesson(
        "Generate the Python file for the node \"order_model\" whose plan entry is: "
        "path app/models/order.py, summary 'Order dataclass + status enum', exports [Order, OrderStatus, NewOrderStatus], uses []. "
        "Module path app.models.order. No top-level docstrings, no __main__.",
        """# Plan: app/models/order.py — Order dataclass + status enum.
# Exports: Order, OrderStatus, NewOrderStatus. Uses: none — models import nothing.
# The build system adds imports (dataclass, Enum) automatically.

class OrderStatus(Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: list = field(default_factory=list)
    total_cents: int = 0
    status: OrderStatus = OrderStatus.PENDING


def NewOrderStatus(value: str) -> OrderStatus:
    # Parse a status string, raising on unknown values.
    try:
        return OrderStatus(value)
    except ValueError as exc:
        raise ValueError(f"unknown order status: {value}") from exc
""",
        "file-generation → order_model.py (Python)",
    ))

    # 7. Python service file — imports via module paths per uses.
    examples.append(code_lesson(
        "Generate the Python file for the node \"order_service\" whose plan entry is: "
        "path app/services/order_service.py, summary 'Order business rules: creation, totals, status flow', "
        "exports [OrderService], uses [{from app.repositories.order_repo, members [OrderRepo]}, "
        "{from app.models.order, members [Order, OrderStatus]}]. Module path app.services.order_service.",
        """# Plan: app/services/order_service.py — order business rules.
# Exports: OrderService. Uses: app.repositories.order_repo → OrderRepo;
# app.models.order → Order. Import statements are added by the build system
# (Python modules must NOT write their own imports); names below resolve to
# the uses members at assembly time.

class OrderService:
    # Order business rules. Handlers call this; it never imports handlers.

    def __init__(self, repo: OrderRepo):
        self._repo = repo

    def create(self, order: Order) -> None:
        if not order.items:
            raise ValueError("order has no items")
        self._repo.save(order)

    def mark_paid(self, order_id: str) -> None:
        order = self._repo.by_id(order_id)
        order.status = OrderStatus.PAID
        self._repo.save(order)
""",
        "file-generation → order_service.py (Python)",
    ))

    # 8. C# service file — namespace from path, DI, thin API.
    examples.append(code_lesson(
        "Generate the C# file for the node \"order_service\" whose plan entry is: "
        "path src/App.Application/Orders/OrderService.cs, summary 'Order business rules: creation, totals, status flow', "
        "exports [OrderService], uses [{from App.Domain.Orders, members [Order]}, "
        "{from App.Infrastructure.Data, members [IOrderRepository]}]. Never generate Program.cs or Main in a node file.",
        """namespace App.Application.Orders;

using App.Domain.Orders;
using App.Infrastructure.Data;

/// <summary>Order business rules. API layer depends on this, never on the repository directly.</summary>
public sealed class OrderService
{
    private readonly IOrderRepository _repo;

    public OrderService(IOrderRepository repo)
    {
        _repo = repo;
    }

    public async Task<Order> CreateAsync(CreateOrderCommand cmd, CancellationToken ct)
    {
        if (cmd.Items.Count == 0)
        {
            throw new ArgumentException("order has no items", nameof(cmd));
        }
        var order = Order.Create(cmd.CustomerId, cmd.Items);
        await _repo.SaveAsync(order, ct);
        return order;
    }
}

/// <summary>Command DTOs used by the API layer. Internal (not public) so this
/// file's only public export stays OrderService — exactly as the contract lists.</summary>
internal sealed record CreateOrderCommand(string CustomerId, IReadOnlyList<OrderItemInput> Items);

internal sealed record OrderItemInput(string ProductId, int Quantity, long UnitCents);
""",
        "file-generation → order_service.cs (C#)",
    ))

    # 9. SQL schema file — DDL honoring the plan entry.
    examples.append(code_lesson(
        "Generate the SQL file for the node \"schema\" whose plan entry is: "
        "path db/schema.sql, summary 'Initial schema: users, orders, order_items with constraints and indexes', "
        "exports [upgrade], uses []. DDL only — the migration runner executes it.",
        """-- Plan: db/schema.sql — initial schema for users, orders, order_items.
-- Exports: upgrade. Uses: none. Executed as DDL by the migration runner.

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin'))
);

CREATE TABLE IF NOT EXISTS orders (
    id            TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES users(id),
    total_cents   INTEGER NOT NULL DEFAULT 0 CHECK (total_cents >= 0),
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id      TEXT NOT NULL REFERENCES orders(id),
    product_id    TEXT NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_cents    INTEGER NOT NULL CHECK (unit_cents >= 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
""",
        "file-generation → schema.sql (SQL)",
    ))

    # ─── Transferable prose rules (4) ─────────────────────────────────────────
    examples.append(rule(
        "Generate files in dependency order, never forward-referencing",
        "When generating the files of a blueprint plan, always follow the uses graph: "
        "models (import nothing) → repositories (import models) → services (import "
        "repositories + models) → handlers/routes/API (import services) → entry point "
        "(wires everything). A file may only import from modules whose files come "
        "EARLIER in this order. Never generate a file that references a member from a "
        "file that hasn't been planned yet — generate the dependency first. If two "
        "files import each other, the plan is broken: merge them or move the shared "
        "type into models.",
        "file-generation → rule-dependency-order",
    ))
    examples.append(rule(
        "Export exactly what the plan declares, nothing more",
        "The plan entry lists the file's exports — the ONLY public API it may define. "
        "Every listed member must exist in the generated file, and anything not listed "
        "must be private (lowercase in Go, not exported in TS, no __all__ entry in "
        "Python, private/internal in C#). Never invent extra public exports: other "
        "files' uses entries were written against this exact surface, so an unplanned "
        "export is dead weight that can only confuse the build.",
        "file-generation → rule-exports-exact",
    ))
    examples.append(rule(
        "Import only what uses lists — never guess or add dependencies",
        "The uses contract lists the modules (and the members within them) this file "
        "is allowed to import. Importing anything else — a module not in uses, a "
        "member the target doesn't export, or a convenience package — breaks the "
        "program even if the file compiles alone. Common violations: handlers importing "
        "repositories directly, services importing other services' internals, models "
        "importing anything at all. If the file genuinely needs a dependency that isn't "
        "in uses, the PLAN is wrong — fix the plan entry first, then generate.",
        "file-generation → rule-uses-only",
    ))
    examples.append(rule(
        "One file, one responsibility — honor the summary",
        "The plan entry's summary describes the file's single responsibility, and the "
        "path tells you which layer it lives in. Write exactly that and stop: a model "
        "file defines types and nothing else; a repository does persistence; a service "
        "holds business rules; a handler maps HTTP to services. If your draft starts "
        "doing two jobs (a service that also writes SQL, a handler that also computes "
        "totals), split it into another planned file rather than bloating this one. "
        "Per-file discipline is what keeps a 30-file program readable and compilable.",
        "file-generation → rule-one-responsibility",
    ))
    examples.append(rule(
        "Generate a whole blueprint round by round in dependency order",
        "Given a 20–40 file blueprint plan, never write all files at once — "
        "generate them in DEPENDENCY-ORDERED ROUNDS of 3–6 files, so the "
        "accumulated set compiles after every round. The invariant: a file is "
        "written only when every module in its uses list already has a written "
        "file. The standard round schedule for a Go/TS/Python/C# backend is: "
        "Round 1 models (import nothing); Round 2 config + repositories (import "
        "models); Round 3 services (import repositories + models); Round 4 "
        "service tests + health handler (import their service); Round 5 feature "
        "handlers + middleware (import services); Round 6 router + entry point "
        "+ build files (import all handlers + middleware + config). Concrete "
        "example — the 33-file filebox-go blueprint (5 features × 5 files): "
        "round 1 writes internal/models/{users,files,folders,shares,activity}.go; "
        "round 2 writes internal/config/config.go and the five repository files; "
        "round 3 writes the five services; round 4 writes the five service "
        "tests + health_handlers.go; round 5 writes the five feature handlers + "
        "internal/middleware/auth.go; round 6 writes internal/handlers/router.go, "
        "cmd/server/main.go, go.mod, README.md, .env.example. Each file still "
        "honors its own exports/uses contract (see the per-file generation "
        "lesson). After each round, compile-check the accumulated set; a repair "
        "round only touches ITS files — never re-emit earlier files, never "
        "reference a file not yet written. Never dump a 33-file program in one "
        "pass: output truncates and the error surface explodes. Six rounds, each "
        "compilable, is how a large generated program compiles the first time.",
        "file-generation → rule-blueprint-to-files",
    ))
    examples.append(rule(
        "Generate a TypeScript blueprint round by round in dependency order",
        "Given a 20–40 file TypeScript blueprint, generate it in "
        "DEPENDENCY-ORDERED ROUNDS of 3–6 files so the accumulated set "
        "typechecks after every round. The invariant: a file is written only "
        "when every module in its uses list already has a written file. The TS "
        "round schedule uses src/ layering (routes instead of Go handlers): "
        "Round 1 src/models (import nothing); Round 2 src/config.ts + "
        "src/repositories (import models); Round 3 src/services (import "
        "repositories + models); Round 4 src/services/*.test.ts (import their "
        "service); Round 5 src/routes + src/middleware (import services); "
        "Round 6 src/routes/router.ts + src/main.ts + build files (package.json, "
        "tsconfig.json, README.md, .env.example). Concrete example — the "
        "33-file kanban-ts blueprint (5 features × 5 files): round 1 writes "
        "src/models/{projects,boards,tasks,comments,activity}.ts; round 2 writes "
        "src/config.ts and the five *Repo.ts files; round 3 writes the five "
        "*Service.ts files; round 4 writes the five *.test.ts files; round 5 "
        "writes the five *Routes.ts files + src/middleware/auth.ts (requireAuth); "
        "round 6 writes src/routes/router.ts (buildRouter wiring all routes "
        "behind requireAuth), src/main.ts, package.json, tsconfig.json, "
        "README.md, .env.example. Each file honors its exports/uses contract: "
        "exports = export declarations only, and the build strips import "
        "statements but keeps export declarations, so files reference uses "
        "members by name. Never dump a 33-file program in one pass — output "
        "truncates and the type-error surface explodes. Six rounds, each "
        "typechecking, is how a large generated TS program compiles first time.",
        "file-generation → rule-blueprint-to-files-ts",
    ))
    examples.append(rule(
        "Repair a failed round by fixing only the failing files",
        "After a generation round, the accumulated set may fail to compile. "
        "Run a REPAIR round: feed the compiler errors back and regenerate ONLY "
        "the failing files — never re-emit files that already pass, and never "
        "touch earlier rounds that already compiled. The #1 rule: KEEP THE SAME "
        "exported symbol names and signatures (other files import them — a "
        "rename breaks every importer with TS2304/undefined). Fix the body, "
        "keep the API. The loop mirrors the generator: run tsc --noEmit (or go "
        "build/gofmt), collect errorsByLabel, regenerate each failing file with "
        "its exact errors as feedback, then re-check — capped at maxRounds (2), "
        "then flag any remaining file for the next round instead of degrading "
        "its contract. Common fixes: TS2304 Cannot find name = you referenced a "
        "member the target doesn't export or the build won't import — use only "
        "uses members; TS2307 Cannot find module = the dependency isn't written "
        "or isn't in uses — write it first (dependency order); TS2554 wrong "
        "arity = call the injected constructor/service the way it's actually "
        "defined; gofmt expected '}' = truncated file — re-emit THIS file "
        "complete. Anti-patterns: rewriting a passing file while you're at it, "
        "renaming exports during repair, adding imports not in the plan to fix "
        "a missing name, fixing round-2 code during a round-5 repair. If an "
        "earlier file genuinely needs change, treat it as a NEW round: update "
        "the plan, edit that one file, re-check the whole set.",
        "file-generation → rule-repair-rounds",
    ))

    return examples


def main():
    dry_run = "--dry-run" in sys.argv
    new = build_examples()

    DS_DIR.mkdir(parents=True, exist_ok=True)
    NEW_OUT.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in new) + "\n",
        encoding="utf-8")
    print(f"  Wrote {NEW_OUT.relative_to(ROOT)}")

    # Validate every concrete code sample before merging (reuses the code-lessons
    # checkers; source tags carry the language hints).
    if "--skip-validation" not in sys.argv:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_code_lessons", ROOT / "scripts" / "validate-code-lessons.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print("  Validating per-file generation samples...")
        code = mod.validate(NEW_OUT, quiet=False)
        if code != 0:
            raise SystemExit(
                "FATAL: per-file generation samples failed validation — fix "
                "scripts/generate-file-generation-examples.py before merging.")

        # Contract check: every sample's actual public API + imports must match
        # its plan entry's exports/uses. Broken ground truth (invented exports,
        # forbidden imports, missing members) would teach contract violations.
        print("  Checking exports/uses contracts...")
        spec2 = importlib.util.spec_from_file_location(
            "check_file_generation_contracts",
            ROOT / "scripts" / "check-file-generation-contracts.py")
        mod2 = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(mod2)
        code2 = mod2.check_contracts(NEW_OUT, quiet=False)
        if code2 != 0:
            raise SystemExit(
                "FATAL: per-file generation samples violate their exports/uses "
                "contracts — fix scripts/generate-file-generation-examples.py "
                "before merging.")

    if dry_run:
        print("  (dry run — no merge)")
        return

    # ─── Merge into train/val/test (same policy as the other generators) ───
    existing = []
    for name in ("train", "val", "test"):
        f = DS_DIR / f"{name}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    existing.append(json.loads(line))
    print(f"  Existing pool: {len(existing)} examples")

    # Single source of truth for 'file-generation →' rows: purge stale versions so
    # a corrected lesson fully replaces the old one instead of lingering in val/test.
    stale = [e for e in existing if str(e.get("source", "")).startswith("file-generation →")]
    if stale:
        existing = [e for e in existing if e not in stale]
        print(f"  Purged {len(stale)} stale file-generation rows (regenerated this run)")

    def key(r):
        return (r.get("instruction", ""), r.get("input", ""), r.get("output", ""))

    new_keys = {key(e) for e in new}
    existing = [e for e in existing if key(e) not in new_keys]
    print(f"  After dedupe vs new: {len(existing)} existing retained")

    rng = random.Random(20260804)
    rng.shuffle(existing)

    total = len(new) + len(existing)
    train_target = int(total * 0.8)
    train = list(new) + existing[: max(0, train_target - len(new))]
    rest = existing[max(0, train_target - len(new)):]
    half = len(rest) // 2
    val, test = rest[:half], rest[half:]
    print(f"  train={len(train)} val={len(val)} test={len(test)}")

    ts = time.strftime("%Y%m%d-%H%M%S")
    backup = DS_DIR / f"backup-{ts}"
    backup.mkdir(parents=True, exist_ok=True)
    for name in ("train", "val", "test"):
        f = DS_DIR / f"{name}.jsonl"
        if f.exists():
            shutil.copy2(f, backup / f"{name}.jsonl")
    print(f"  Backed up to {backup.relative_to(ROOT)}")

    for name, rows in (("train", train), ("val", val), ("test", test)):
        (DS_DIR / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    print("=== DONE ===")


if __name__ == "__main__":
    main()
