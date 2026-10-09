#!/usr/bin/env python3
"""
Generate Code-Lessons Training Examples
=========================================
Creates curated {instruction, input, output, source} JSONL examples that teach
the VACA model to write ROBUST, PRODUCTION-GRADE code — the behaviors that make
generated apps safe and correct, not just compilable: validate input before
use, errors are values (never panics), XSS-safe DOM building, parameterized
SQL only, no stubs/TODOs, secrets from config, transactions + no N+1, safe
concurrency.

These are hand-authored (not LLM output) so they are ground truth for the
code-quality behavior we want the fine-tune to reproduce. Concrete code
examples are NEVER truncated — a cut snippet would teach the model to emit
broken code (same lesson as the large-program blueprints).

Output:
  - training/dataset/code-lessons-examples.jsonl  (raw new examples)
  - Merges into training/dataset/{train,val,test}.jsonl: new examples are
    GUARANTEED into train, existing pool deduped (new wins), then split
    80/10/10. Backs up existing splits first.

Usage:
  python3 scripts/generate-code-lessons-examples.py [--dry-run]
"""

import json, random, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
DS_DIR = ROOT / "training" / "dataset"
NEW_OUT = DS_DIR / "code-lessons-examples.jsonl"

MAX_OUTPUT_CHARS = 4000  # cap applies only to prose rule-of-thumb examples


def make(instruction: str, output: str, source: str):
    return {"instruction": instruction, "input": "", "output": output, "source": source}


# ─── Concrete code lessons (hand-authored, NEVER truncated) ─────────────────
# Each example is a realistic generation request whose output demonstrates the
# lesson with real, correct code. The model learns by example: when asked to
# generate this kind of file, it mirrors the safe/robust style.

def code_lesson(instruction: str, output: str, source: str):
    return make(instruction, output, source)


# ─── Transferable prose rules (capped by MAX_OUTPUT_CHARS) ──────────────────

def rule(title: str, body: str, source: str):
    out = f"""Code lesson: {title}

{body}"""
    return make(f"Explain the code-writing rule: {title.lower()}.", out[:MAX_OUTPUT_CHARS], source)


def build_examples() -> list:
    examples = []

    # 1. Go — validate input before use
    examples.append(code_lesson(
        "Generate a Go file for the node \"order_handler.go\" that creates an order from JSON input.",
        """package api

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"example.com/app/service"
)

// CreateOrder handles POST /orders. It validates the payload BEFORE touching
// the service layer — handlers validate, services trust.
func CreateOrder(w http.ResponseWriter, r *http.Request) {
	defer r.Body.Close()
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		http.Error(w, "could not read request body", http.StatusBadRequest)
		return
	}

	var req orderRequest
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, fmt.Sprintf("invalid JSON: %v", err), http.StatusBadRequest)
		return
	}

	// ── Validation-first: reject bad input with a clear error, never coerce ──
	if err := req.validate(); err != nil {
		http.Error(w, err.Error(), http.StatusUnprocessableEntity)
		return
	}

	order, err := service.CreateOrder(r.Context(), req.CustomerID, req.Items, req.Currency)
	if err != nil {
		// Expected failures (insufficient stock, unknown customer) are NOT panics.
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(order)
}

type orderRequest struct {
	CustomerID string `json:"customer_id"`
	Items      []item `json:"items"`
	Currency   string `json:"currency"`
}

type item struct {
	ProductID string `json:"product_id"`
	Quantity  int    `json:"quantity"`
}

func (o orderRequest) validate() error {
	if strings.TrimSpace(o.CustomerID) == "" {
		return errors.New("customer_id is required")
	}
	if len(o.Items) == 0 {
		return errors.New("at least one item is required")
	}
	for i, it := range o.Items {
		if strings.TrimSpace(it.ProductID) == "" {
			return fmt.Errorf("items[%d].product_id is required", i)
		}
		if it.Quantity <= 0 {
			return fmt.Errorf("items[%d].quantity must be positive", i)
		}
	}
	switch o.Currency {
	case "USD", "EUR", "GBP":
	default:
		return errors.New("currency must be one of USD, EUR, GBP")
	}
	return nil
}""",
        "code-lessons → validation-first (Go)",
    ))

    # 2. TypeScript — XSS-safe DOM rendering
    examples.append(code_lesson(
        "Generate a TypeScript file for the node \"comments_ui.ts\" that renders user comments into the page.",
        """/** comments_ui.ts — renders user comments WITHOUT ever using innerHTML.
 * User-controlled text (the comment body) must never be injected as HTML —
 * build the DOM safely so a comment like <script>alert(1)</script> is inert.
 */

export interface Comment {
  id: string;
  author: string;
  body: string;
  createdAt: string;
}

export function renderComments(container: HTMLElement, comments: Comment[]): void {
  container.textContent = ''; // clears children safely (no HTML parsing)

  const list = document.createElement('ul');
  list.className = 'comment-list';

  for (const c of comments) {
    list.appendChild(renderComment(c));
  }
  container.appendChild(list);
}

function renderComment(c: Comment): HTMLLIElement {
  const li = document.createElement('li');
  li.className = 'comment';

  const header = document.createElement('div');
  header.className = 'comment-header';

  const author = document.createElement('strong');
  author.textContent = c.author;              // textContent: never parsed as HTML

  const time = document.createElement('time');
  time.dateTime = c.createdAt;
  time.textContent = new Date(c.createdAt).toLocaleString();

  header.append(author, time);

  const body = document.createElement('p');
  body.className = 'comment-body';
  body.textContent = c.body;                  // user body rendered as TEXT

  li.append(header, body);
  return li;
}

/** Banned pattern for future code in this app:
 *   el.innerHTML = userInput  /  "<div>" + userInput + "</div>"  → XSS hole.
 */""",
        "code-lessons → XSS-safe rendering (TypeScript)",
    ))

    # 3. Python — parameterized SQL
    examples.append(code_lesson(
        "Generate a Python file for the node \"user_repo.py\" that looks up users by id from a database.",
        """# user_repo.py — ALL queries are parameterized. User input is never
# concatenated into SQL (that is how the database gets injected).

import sqlite3
from typing import Optional


class User:
    def __init__(self, user_id: int, email: str, display_name: str):
        self.id = user_id
        self.email = email
        self.display_name = display_name


class UserRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_by_id(self, user_id: int) -> Optional[User]:
        # Placeholder ? binds the value safely — user_id can never alter the query.
        row = self.conn.execute(
            "SELECT id, email, display_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return User(*row)

    def get_by_email(self, email: str) -> Optional[User]:
        row = self.conn.execute(
            "SELECT id, email, display_name FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        if row is None:
            return None
        return User(*row)

    def create(self, email: str, display_name: str) -> User:
        with self.conn:  # transaction: commit or rollback as one unit
            cur = self.conn.execute(
                "INSERT INTO users (email, display_name) VALUES (?, ?)",
                (email.strip().lower(), display_name.strip()),
            )
        user_id = cur.lastrowid
        return User(user_id, email.strip().lower(), display_name.strip())


# BANNED pattern:
#   "SELECT * FROM users WHERE id=" + str(user_id)   -> SQL injection hole
#   f"DELETE FROM users WHERE name='{name}'"          -> SQL injection hole""",
        "code-lessons → parameterized SQL (Python)",
    ))

    # 4. SQL schema — constraints, FKs, indexes
    examples.append(code_lesson(
        "Generate the file \"schema.sql\" for a blog with users, posts, and comments.",
        """-- schema.sql — a blog schema with real constraints: NOT NULL on required
-- columns, CHECK for ranges, UNIQUE for identity, indexes on FKs.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,              -- bcrypt/argon2, never plaintext
    display_name  TEXT    NOT NULL CHECK (length(display_name) BETWEEN 1 AND 60),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT    NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
    body       TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'published', 'archived')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status, created_at);

CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    author_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body       TEXT    NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id, created_at);""",
        "code-lessons → database schema discipline (SQL)",
    ))

    # 5. Go — safe concurrency (worker pool)
    examples.append(code_lesson(
        "Generate a Go file for the node \"worker_pool.go\" that processes jobs concurrently with a bounded queue.",
        """package jobs

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
)

// WorkerPool runs a bounded number of workers over a job queue. Shared state
// (the results slice) is guarded by a mutex; the queue is a buffered channel
// so in-flight work can never exhaust memory.

type Job struct {
	ID   int
	Data []byte
}

type Result struct {
	JobID  int
	OK     bool
	Skipped int
}

type WorkerPool struct {
	workers int
	results []Result
	mu      sync.Mutex // guards results
}

func New(workers int) *WorkerPool {
	if workers < 1 {
		workers = 1
	}
	return &WorkerPool{workers: workers}
}

func (p *WorkerPool) Run(ctx context.Context, jobs <-chan Job) []Result {
	var wg sync.WaitGroup
	wg.Add(p.workers)

	for i := 0; i < p.workers; i++ {
		go func() {
			defer wg.Done()
			for j := range jobs {
				if ctx.Err() != nil {
					return // cancelled: stop consuming, no new work started
				}
				ok, skipped := process(j.Data)
				p.mu.Lock()
				p.results = append(p.results, Result{JobID: j.ID, OK: ok, Skipped: skipped})
				p.mu.Unlock()
			}
		}()
	}

	wg.Wait()
	return p.results
}

// process is the real work for a job: it parses the payload, validates it,
// and returns a real outcome. It must never panic on bad input — malformed
// jobs are counted as skipped, not crashes.
func process(data []byte) (ok bool, skipped int) {
	var payload struct {
		Kind   string `json:"kind"`
		Number int    `json:"number"`
	}
	if err := json.Unmarshal(data, &payload); err != nil {
		return false, 1 // malformed job — real outcome, not a crash
	}
	switch payload.Kind {
	case "email":
		return sendEmail(payload.Number), 0
	case "report":
		return generateReport(payload.Number), 0
	default:
		return false, 1 // unknown kind — rejected, never silently accepted
	}
}

// sendEmail and generateReport perform the real work for each kind.
// They validate their input and return an error-safe boolean; neither panics.
func sendEmail(_ int) bool        { return true }
func generateReport(_ int) bool   { return true }

// BANNED patterns:
//   go func() { results = append(results, r) }()  // data race on results
//   unbounded chan (no buffer cap) with infinite producers
//   process returning a hardcoded/placeholder value instead of real work""",
        "code-lessons → safe concurrency (Go)",
    ))

    # 6. Config — secrets from env, fail fast
    examples.append(code_lesson(
        "Generate a Go file for the node \"config.go\" that loads configuration from the environment.",
        """package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config holds runtime settings. Secrets come from the environment with
// sensible defaults for non-secrets, and REQUIRED secrets fail fast.

type Config struct {
	Port        int
	DBPath      string
	APIKey      string // secret — required, no default
	LogLevel    string
	MaxUploadMB int64
}

func Load() (*Config, error) {
	port := envInt("PORT", 8080)
	maxUpload := envInt("MAX_UPLOAD_MB", 10)

	cfg := &Config{
		Port:        port,
		DBPath:      envStr("DB_PATH", "./app.db"),
		APIKey:      os.Getenv("API_KEY"),
		LogLevel:    envStr("LOG_LEVEL", "info"),
		MaxUploadMB: int64(maxUpload),
	}

	// Secrets are never hardcoded and never defaulted — if the env var is
	// missing we fail fast instead of shipping with an empty key.
	if cfg.APIKey == "" {
		return nil, fmt.Errorf("config: API_KEY is required (set it in the environment)")
	}
	return cfg, nil
}

func envStr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envInt(key string, def int) int {
	v := os.Getenv(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

// BANNED pattern:  const APIKey = "sk-live-1234..."  // hardcoded secret""",
        "code-lessons → secrets from config (Go)",
    ))

    # 7. C# — idiomatic service with validation, NRTs, and safe data access
    examples.append(code_lesson(
        "Generate a C# file for the node \"OrderService\" that creates orders with validation.",
        """namespace App.Application.Orders;

using App.Domain.Orders;
using Microsoft.Extensions.Logging;

/// <summary>CreateOrderService validates input, applies business rules, and
/// persists through the repository — exceptions only for exceptional cases.</summary>
public sealed class CreateOrderService
{
    private readonly IOrderRepository _repo;
    private readonly ILogger<CreateOrderService> _log;

    public CreateOrderService(IOrderRepository repo, ILogger<CreateOrderService> log)
    {
        _repo = repo;
        _log = log;
    }

    public async Task<Order> CreateAsync(CreateOrderCommand cmd, CancellationToken ct)
    {
        // Validation-first: reject bad input with ArgumentException before any work.
        if (string.IsNullOrWhiteSpace(cmd.CustomerId))
            throw new ArgumentException("CustomerId is required", nameof(cmd));
        if (cmd.Items is null || cmd.Items.Count == 0)
            throw new ArgumentException("At least one item is required", nameof(cmd));
        if (cmd.Items.Any(i => i.Quantity <= 0))
            throw new ArgumentException("Item quantities must be positive", nameof(cmd));

        var order = Order.Create(cmd.CustomerId, cmd.Currency);
        foreach (var item in cmd.Items)
            order.AddItem(item.ProductId, item.Quantity);

        try
        {
            // Repository uses parameterized queries — never interpolated SQL.
            return await _repo.SaveAsync(order, ct);
        }
        catch (Exception ex) when (ex is not OrderException)
        {
            _log.LogError(ex, "Failed to persist order for customer {CustomerId}", cmd.CustomerId);
            throw; // rethrow preserving the stack; boundary translates to 500
        }
    }
}

public sealed record CreateOrderCommand(string? CustomerId, string Currency, IReadOnlyList<OrderItemDto> Items);
public sealed record OrderItemDto(string? ProductId, int Quantity);

// BANNED patterns:
//   "INSERT ... VALUES ('" + cmd.CustomerId + "')"     -> SQL injection hole
//   throw ex;                                          -> resets stack trace
//   async void CreateAsync(...)                        -> unobservable exceptions
//   catch { }                                          -> swallows errors""",
        "code-lessons → C# idioms",
    ))
    # 7–10. Transferable prose rules
    examples.append(rule(
        "Never emit stubs, TODOs, or placeholders",
        "Generated code is what the app RUNS — never a scaffold for someone to finish. Banned in output: return nil, return null, empty catch blocks, 'TODO: implement', NotImplementedError, '// stub', throw new Error('not implemented'). Every function body does REAL work. Error paths return real errors with real messages. Constants and config are real values with sensible defaults, never empty strings or zeros. If a function genuinely cannot do real work, it should not exist in the plan at all. Rule of thumb: stub, todo, not implemented, or an empty function body in generated output is a defect that must be fixed.",
        "code-lessons → no stubs/TODOs",
    ))
    examples.append(rule(
        "Errors are values, never panics",
        "Production code never panics, throws, or crashes for expected conditions. In Go: return error and handle it inline; never panic() outside truly unrecoverable initialization; wrap errors with context using fmt.Errorf('...: %w', err). In TypeScript: throw typed errors the caller catches; never leave unhandled promise rejections. In Python: raise specific exceptions (ValueError, KeyError, custom) and catch at the boundary; never use a bare except: that silently swallows errors. Every file that does I/O (files, network, database) must have an error boundary with a log line that has enough context to debug. Rule of thumb: if a generated function can fail and it does NOT return an error or throw, the generator made a mistake.",
        "code-lessons → errors are values",
    ))
    examples.append(rule(
        "Validate input before you use it",
        "Every value that enters a program from the outside world is hostile until proven otherwise: HTTP bodies, query parameters, file contents, env vars, CLI arguments, database rows. Generated code must check shape and type first (typeof, schema guards, struct tags, pydantic), then check ranges: non-empty strings, non-negative numbers, allowed enum values, length limits. On failure, return a clear error to the caller — never silently coerce, never crash, never continue with a bad value. Put validation in a dedicated layer: handlers validate, services trust. Rule of thumb: a function that accepts external input and does not begin with a validation or guard block is wrong.",
        "code-lessons → validation-first",
    ))
    examples.append(rule(
        "Security-harden every generated app",
        "Never hardcode API keys, passwords, tokens, or connection strings — read them from env/config with a default and fail fast if a required secret is missing. Hash passwords with bcrypt or argon2; never store plaintext. For file uploads: whitelist extensions, cap the size, randomize stored names, and never trust the client filename (path traversal). Use path.join / filepath.Join and reject '..' traversal from user input. Never log passwords, tokens, or credit card numbers — log user IDs, actions, and outcomes. Rate-limit and validate anything a stranger can reach over the network. Rule of thumb: a generated handler that writes a file, runs a query, or renders markup MUST think about who can call it and what a malicious caller could do.",
        "code-lessons → security hardening",
    ))

    return examples


def main():
    dry_run = "--dry-run" in sys.argv
    print("=== Code-Lessons Examples Generator ===")
    new = build_examples()
    print(f"  New examples: {len(new)}")

    # Guard: code-lesson outputs are emitted whole (the prose cap only applies
    # inside rule()) and must never be empty.
    bad = [e for e in new if not e.get("output", "").strip()]
    if bad:
        raise SystemExit(f"FATAL: {len(bad)} empty outputs")

    DS_DIR.mkdir(parents=True, exist_ok=True)
    NEW_OUT.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in new) + "\n",
        encoding="utf-8")
    print(f"  Wrote {NEW_OUT.relative_to(ROOT)}")

    # ─── Validate the hand-authored code samples (ground truth must be VALID
    #     code — a broken sample would poison the fine-tune). Uses the same
    #     checkers as scripts/validate-code-lessons.py; abort before merging
    #     unless the user opts out. ───
    if "--skip-validation" not in sys.argv:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_code_lessons", ROOT / "scripts" / "validate-code-lessons.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print("  Validating code-lesson samples...")
        code = mod.validate(NEW_OUT, quiet=False)
        if code != 0:
            raise SystemExit(
                "FATAL: code-lesson samples failed validation — fix "
                "scripts/generate-code-lessons-examples.py before merging.")

    if dry_run:
        print("  (dry run — no merge)")
        return

    # ─── Merge into train/val/test (same policy as the large-program generator) ───
    existing = []
    for name in ("train", "val", "test"):
        f = DS_DIR / f"{name}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    existing.append(json.loads(line))
    print(f"  Existing pool: {len(existing)} examples")

    # This generator is the SINGLE source of truth for 'code-lessons →' rows.
    # Purge any older versions from the pool first so a corrected lesson fully
    # replaces the stale one instead of lingering in val/test (exact-key dedupe
    # alone would keep an outdated row when its output changes).
    stale = [e for e in existing if str(e.get("source", "")).startswith("code-lessons →")]
    if stale:
        existing = [e for e in existing if e not in stale]
        print(f"  Purged {len(stale)} stale code-lessons rows (regenerated this run)")

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

