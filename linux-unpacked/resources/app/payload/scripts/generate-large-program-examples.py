#!/usr/bin/env python3
"""
Generate Large-Program Training Examples
==========================================
Creates curated {instruction, input, output, source} JSONL examples that teach
the VACA model how to DESIGN large multi-file programs (25–60 files) — the exact
kind of decomposition that makes big builds compilable: one file per
responsibility, vertical feature slices, one-way dependency direction, per-file
export/uses contracts, and the 9 mandatory layers.

These are hand-authored architecture blueprints (not LLM output), so they are
ground truth for the scale behavior we want the fine-tune to reproduce.

Output:
  - training/dataset/large-program-examples.jsonl  (raw new examples)
  - Merges into training/dataset/{train,val,test}.jsonl following the same
    policy as scripts/build-vaca-knowledge-dataset.py: new examples are
    GUARANTEED into train, existing pool is deduped (new wins), then split
    80/10/10. Backs up the existing splits first.

Usage:
  python3 scripts/generate-large-program-examples.py [--dry-run]
"""

import json, random, re, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
DS_DIR = ROOT / "training" / "dataset"
NEW_OUT = DS_DIR / "large-program-examples.jsonl"

MAX_OUTPUT_CHARS = 4000  # cap only applies to prose rule-of-thumb examples


def make(instruction: str, output: str, source: str):
    return {"instruction": instruction, "input": "", "output": output, "source": source}


# ─── Curated large-program architecture blueprints ──────────────────────────
# Each example is a full file plan with per-file exports/uses contracts, in the
# same shape the codePlanner's PLAN_PROMPT asks the model to emit. Teach by
# example: the model mirrors this structure instead of planning 3-file apps.
# These are hand-authored and MUST NOT be truncated — a cut file plan teaches
# the model to emit broken JSON.

def blueprint(goal, intro, files_blocks):
    """Render a full plan JSON with reasoning + file contracts (never truncated)."""
    # Each block is one file entry (a JSON object line). Join with commas so
    # the "files" array is valid JSON.
    files = ",\n".join(b for b in files_blocks)
    out = f'''Design a production-grade {goal}. Think through every file a real {goal} needs — this is a LARGE program, so plan 25+ files.

Reasoning: {intro}

Plan:
{{
  "reasoning": "{intro}",
  "files": [
{files}
  ],
  "questions": []
}}'''
    # Safety: a hand-authored blueprint's JSON block must always parse. Assert
    # instead of silently truncating — a broken example is worse than none.
    match = re.search(r"\{[\s\S]*\}", out)
    if not match or not json.loads(match.group(0)):
        raise ValueError(f"blueprint produced invalid JSON for: {goal}")
    return out


# Example 1 — E-Commerce Platform (Go, ~34 files)
ECOMMERCE = blueprint(
    "e-commerce platform with user accounts, product catalog, cart, checkout, and orders",
    "Multi-tenant storefront: users, products, cart, checkout, orders. Decompose by feature with a shared models/repository/services/handlers layering so imports flow one way (handlers → services → repo → models) and the build compiles in dependency order.",
    [
        '    { "path": "cmd/server/main.go", "summary": "Entry point: loads config, wires repository+services+handlers, starts HTTP server, graceful shutdown", "language": "go", "exports": ["main"], "uses": [{"from": "internal/config", "members": ["Load", "Config"]}, {"from": "internal/handlers", "members": ["NewRouter"]}] }',
        '    { "path": "internal/config/config.go", "summary": "Env-driven config: DB DSN, port, JWT secret, defaults + validation", "language": "go", "exports": ["Load", "Config"], "uses": [] }',
        '    { "path": "internal/models/user.go", "summary": "User entity + role enum", "language": "go", "exports": ["User", "Role"], "uses": [] }',
        '    { "path": "internal/models/product.go", "summary": "Product entity with price and stock", "language": "go", "exports": ["Product"], "uses": [] }',
        '    { "path": "internal/models/cart.go", "summary": "Cart + CartItem entities", "language": "go", "exports": ["Cart", "CartItem"], "uses": [] }',
        '    { "path": "internal/models/order.go", "summary": "Order + OrderItem entities and status enum", "language": "go", "exports": ["Order", "OrderItem", "OrderStatus"], "uses": [] }',
        '    { "path": "internal/repository/user_repo.go", "summary": "User CRUD on SQLite: Create, GetByID, GetByEmail, Update", "language": "go", "exports": ["UserRepo", "NewUserRepo"], "uses": [{"from": "internal/models", "members": ["User", "Role"]}] }',
        '    { "path": "internal/repository/product_repo.go", "summary": "Product CRUD + stock decrement with transaction", "language": "go", "exports": ["ProductRepo", "NewProductRepo"], "uses": [{"from": "internal/models", "members": ["Product"]}] }',
        '    { "path": "internal/repository/cart_repo.go", "summary": "Cart load/save per user", "language": "go", "exports": ["CartRepo", "NewCartRepo"], "uses": [{"from": "internal/models", "members": ["Cart", "CartItem"]}] }',
        '    { "path": "internal/repository/order_repo.go", "summary": "Order create/list per user", "language": "go", "exports": ["OrderRepo", "NewOrderRepo"], "uses": [{"from": "internal/models", "members": ["Order", "OrderItem", "OrderStatus"]}] }',
        '    { "path": "internal/service/user_service.go", "summary": "Registration, login, JWT issue, password hashing", "language": "go", "exports": ["UserService", "NewUserService"], "uses": [{"from": "internal/repository", "members": ["UserRepo"]}, {"from": "internal/models", "members": ["User"]}] }',
        '    { "path": "internal/service/product_service.go", "summary": "Catalog queries, stock validation, price rules", "language": "go", "exports": ["ProductService", "NewProductService"], "uses": [{"from": "internal/repository", "members": ["ProductRepo"]}] }',
        '    { "path": "internal/service/cart_service.go", "summary": "Add/remove/update cart items, totals", "language": "go", "exports": ["CartService", "NewCartService"], "uses": [{"from": "internal/repository", "members": ["CartRepo", "ProductRepo"]}, {"from": "internal/models", "members": ["CartItem"]}] }',
        '    { "path": "internal/service/order_service.go", "summary": "Checkout: validates cart, decrements stock, creates order in one transaction", "language": "go", "exports": ["OrderService", "NewOrderService"], "uses": [{"from": "internal/repository", "members": ["OrderRepo", "CartRepo", "ProductRepo"]}, {"from": "internal/models", "members": ["Order"]}] }',
        '    { "path": "internal/handlers/auth_handlers.go", "summary": "HTTP: register, login, me (thin — delegates to user service)", "language": "go", "exports": ["AuthHandlers", "NewAuthHandlers"], "uses": [{"from": "internal/service", "members": ["UserService"]}, {"from": "internal/models", "members": ["User"]}] }',
        '    { "path": "internal/handlers/product_handlers.go", "summary": "HTTP: list/get products", "language": "go", "exports": ["ProductHandlers"], "uses": [{"from": "internal/service", "members": ["ProductService"]}] }',
        '    { "path": "internal/handlers/cart_handlers.go", "summary": "HTTP: get/add/update cart", "language": "go", "exports": ["CartHandlers"], "uses": [{"from": "internal/service", "members": ["CartService"]}] }',
        '    { "path": "internal/handlers/order_handlers.go", "summary": "HTTP: create order, list my orders", "language": "go", "exports": ["OrderHandlers"], "uses": [{"from": "internal/service", "members": ["OrderService"]}] }',
        '    { "path": "internal/handlers/router.go", "summary": "Wires all handlers + middleware (auth, logging, recover) into a mux", "language": "go", "exports": ["NewRouter"], "uses": [{"from": "internal/handlers", "members": ["AuthHandlers", "ProductHandlers", "CartHandlers", "OrderHandlers"]}] }',
        '    { "path": "internal/service/user_service_test.go", "summary": "Tests registration validation + password hashing + login flow", "language": "go", "exports": [], "uses": [{"from": "internal/service", "members": ["UserService"]}] }',
        '    { "path": "internal/service/order_service_test.go", "summary": "Tests checkout happy path + insufficient stock", "language": "go", "exports": [], "uses": [{"from": "internal/service", "members": ["OrderService"]}] }',
        '    { "path": "internal/handlers/health_handlers.go", "summary": "REST: GET /health + readiness probe", "language": "go", "exports": ["HealthHandlers"], "uses": [] }',
        '    { "path": "internal/handlers/router_test.go", "summary": "Smoke: routes registered, middleware chain applies", "language": "go", "exports": [], "uses": [{"from": "internal/handlers", "members": ["NewRouter"]}] }',
        '    { "path": "go.mod", "summary": "Go module definition", "language": "go", "exports": [], "uses": [] }',
        '    { "path": "README.md", "summary": "Run/build/test instructions + env vars", "language": "markdown", "exports": [], "uses": [] }',
        '    { "path": ".env.example", "summary": "Documented env var template", "language": "dotenv", "exports": [], "uses": [] }',
    ],
)

# Example 2 — SaaS Analytics Dashboard (TypeScript, ~30 files)
ANALYTICS = blueprint(
    "SaaS analytics dashboard with projects, events, metrics, user management, and API tokens",
    "Event ingestion + analytics: auth, projects, events, metrics computation, API tokens. TypeScript with src/ layering (routes → services → repositories → models), each feature as a vertical slice, tests beside services.",
    [
        '    { "path": "src/main.ts", "summary": "Entry: boots express, wires routes+services+db, listens", "language": "typescript", "exports": ["main"], "uses": [{"from": "src/config", "members": ["loadConfig"]}, {"from": "src/routes", "members": ["buildRouter"]}] }',
        '    { "path": "src/config.ts", "summary": "Env config: db url, jwt secret, port", "language": "typescript", "exports": ["loadConfig", "Config"], "uses": [] }',
        '    { "path": "src/models/user.ts", "summary": "User type + role", "language": "typescript", "exports": ["User", "Role"], "uses": [] }',
        '    { "path": "src/models/project.ts", "summary": "Project type", "language": "typescript", "exports": ["Project"], "uses": [] }',
        '    { "path": "src/models/event.ts", "summary": "Raw event type", "language": "typescript", "exports": ["Event"], "uses": [] }',
        '    { "path": "src/models/metric.ts", "summary": "Computed metric + timeseries point", "language": "typescript", "exports": ["Metric", "MetricPoint"], "uses": [] }',
        '    { "path": "src/models/token.ts", "summary": "API token model", "language": "typescript", "exports": ["ApiToken"], "uses": [] }',
        '    { "path": "src/repositories/userRepo.ts", "summary": "User persistence", "language": "typescript", "exports": ["UserRepo"], "uses": [{"from": "src/models/user", "members": ["User"]}] }',
        '    { "path": "src/repositories/projectRepo.ts", "summary": "Project persistence", "language": "typescript", "exports": ["ProjectRepo"], "uses": [{"from": "src/models/project", "members": ["Project"]}] }',
        '    { "path": "src/repositories/eventRepo.ts", "summary": "Event ingestion + bulk insert", "language": "typescript", "exports": ["EventRepo"], "uses": [{"from": "src/models/event", "members": ["Event"]}] }',
        '    { "path": "src/repositories/metricRepo.ts", "summary": "Metric reads + rollup writes", "language": "typescript", "exports": ["MetricRepo"], "uses": [{"from": "src/models/metric", "members": ["Metric", "MetricPoint"]}] }',
        '    { "path": "src/repositories/tokenRepo.ts", "summary": "API token CRUD", "language": "typescript", "exports": ["TokenRepo"], "uses": [{"from": "src/models/token", "members": ["ApiToken"]}] }',
        '    { "path": "src/services/authService.ts", "summary": "Signup, login, JWT", "language": "typescript", "exports": ["AuthService"], "uses": [{"from": "src/repositories/userRepo", "members": ["UserRepo"]}] }',
        '    { "path": "src/services/ingestService.ts", "summary": "Validates + batches incoming events", "language": "typescript", "exports": ["IngestService"], "uses": [{"from": "src/repositories/eventRepo", "members": ["EventRepo"]}, {"from": "src/models/event", "members": ["Event"]}] }',
        '    { "path": "src/services/metricService.ts", "summary": "Computes rollups from raw events", "language": "typescript", "exports": ["MetricService"], "uses": [{"from": "src/repositories/metricRepo", "members": ["MetricRepo"]}] }',
        '    { "path": "src/services/projectService.ts", "summary": "Project CRUD + membership", "language": "typescript", "exports": ["ProjectService"], "uses": [{"from": "src/repositories/projectRepo", "members": ["ProjectRepo"]}] }',
        '    { "path": "src/routes/authRoutes.ts", "summary": "POST /auth/register, /auth/login", "language": "typescript", "exports": ["authRoutes"], "uses": [{"from": "src/services/authService", "members": ["AuthService"]}] }',
        '    { "path": "src/routes/ingestRoutes.ts", "summary": "POST /ingest (token-gated)", "language": "typescript", "exports": ["ingestRoutes"], "uses": [{"from": "src/services/ingestService", "members": ["IngestService"]}] }',
        '    { "path": "src/routes/metricRoutes.ts", "summary": "GET /projects/:id/metrics", "language": "typescript", "exports": ["metricRoutes"], "uses": [{"from": "src/services/metricService", "members": ["MetricService"]}] }',
        '    { "path": "src/routes/router.ts", "summary": "Combines subrouters + middleware", "language": "typescript", "exports": ["buildRouter"], "uses": [{"from": "src/routes/authRoutes", "members": ["authRoutes"]}, {"from": "src/routes/ingestRoutes", "members": ["ingestRoutes"]}] }',
        '    { "path": "src/services/authService.test.ts", "summary": "Auth unit tests", "language": "typescript", "exports": [], "uses": [{"from": "src/services/authService", "members": ["AuthService"]}] }',
        '    { "path": "src/services/metricService.test.ts", "summary": "Metric rollup tests", "language": "typescript", "exports": [], "uses": [{"from": "src/services/metricService", "members": ["MetricService"]}] }',
        '    { "path": "package.json", "summary": "Deps + scripts", "language": "json", "exports": [], "uses": [] }',
        '    { "path": "tsconfig.json", "summary": "TS compiler config", "language": "json", "exports": [], "uses": [] }',
        '    { "path": "README.md", "summary": "Setup + run docs", "language": "markdown", "exports": [], "uses": [] }',
    ],
)

# Example 3 — Multi-tenant CMS (Python/FastAPI, ~28 files)
CMS = blueprint(
    "multi-tenant CMS with content types, drafts, publishing workflow, media uploads, and roles",
    "Content management: tenants, content types, entries, workflow, media, roles. FastAPI with routers → services → repositories → models; per-feature slices, Alembic migrations, pytest beside services.",
    [
        '    { "path": "app/main.py", "summary": "FastAPI app factory, mounts routers, startup DB init", "language": "python", "exports": ["create_app"], "uses": [{"from": "app.config", "members": ["get_settings"]}, {"from": "app.api.router", "members": ["api_router"]}] }',
        '    { "path": "app/config.py", "summary": "Pydantic settings from env", "language": "python", "exports": ["Settings", "get_settings"], "uses": [] }',
        '    { "path": "app/models/tenant.py", "summary": "Tenant ORM model", "language": "python", "exports": ["Tenant"], "uses": [] }',
        '    { "path": "app/models/user.py", "summary": "User + role", "language": "python", "exports": ["User", "Role"], "uses": [] }',
        '    { "path": "app/models/content_type.py", "summary": "ContentType schema model", "language": "python", "exports": ["ContentType"], "uses": [] }',
        '    { "path": "app/models/entry.py", "summary": "Entry + status", "language": "python", "exports": ["Entry", "EntryStatus"], "uses": [] }',
        '    { "path": "app/models/media.py", "summary": "Media asset model", "language": "python", "exports": ["MediaAsset"], "uses": [] }',
        '    { "path": "app/repositories/tenant_repo.py", "summary": "Tenant scoping helpers", "language": "python", "exports": ["TenantRepo"], "uses": [{"from": "app.models.tenant", "members": ["Tenant"]}] }',
        '    { "path": "app/repositories/user_repo.py", "summary": "User CRUD + role checks", "language": "python", "exports": ["UserRepo"], "uses": [{"from": "app.models.user", "members": ["User"]}] }',
        '    { "path": "app/repositories/content_repo.py", "summary": "ContentType + Entry persistence", "language": "python", "exports": ["ContentRepo"], "uses": [{"from": "app.models.entry", "members": ["Entry"]}] }',
        '    { "path": "app/repositories/media_repo.py", "summary": "Media metadata persistence", "language": "python", "exports": ["MediaRepo"], "uses": [{"from": "app.models.media", "members": ["MediaAsset"]}] }',
        '    { "path": "app/services/workflow_service.py", "summary": "Draft→review→publish state machine", "language": "python", "exports": ["WorkflowService"], "uses": [{"from": "app.repositories.content_repo", "members": ["ContentRepo"]}] }',
        '    { "path": "app/services/tenant_service.py", "summary": "Tenant provisioning + scoping", "language": "python", "exports": ["TenantService"], "uses": [{"from": "app.repositories.tenant_repo", "members": ["TenantRepo"]}] }',
        '    { "path": "app/services/role_service.py", "summary": "Role assignment + permission checks", "language": "python", "exports": ["RoleService"], "uses": [{"from": "app.repositories.user_repo", "members": ["UserRepo"]}] }',
        '    { "path": "app/api/content.py", "summary": "REST endpoints for content types + entries", "language": "python", "exports": ["content_router"], "uses": [{"from": "app.services.workflow_service", "members": ["WorkflowService"]}] }',
        '    { "path": "app/api/media.py", "summary": "Upload + serve media endpoints", "language": "python", "exports": ["media_router"], "uses": [{"from": "app.repositories.media_repo", "members": ["MediaRepo"]}] }',
        '    { "path": "app/api/auth.py", "summary": "Login + me endpoints", "language": "python", "exports": ["auth_router"], "uses": [{"from": "app.services.role_service", "members": ["RoleService"]}] }',
        '    { "path": "app/api/router.py", "summary": "Aggregates sub-routers under /api", "language": "python", "exports": ["api_router"], "uses": [{"from": "app.api.content", "members": ["content_router"]}, {"from": "app.api.auth", "members": ["auth_router"]}] }',
        '    { "path": "tests/test_workflow.py", "summary": "Publish flow tests", "language": "python", "exports": [], "uses": [{"from": "app.services.workflow_service", "members": ["WorkflowService"]}] }',
        '    { "path": "tests/test_roles.py", "summary": "Permission tests", "language": "python", "exports": [], "uses": [{"from": "app.services.role_service", "members": ["RoleService"]}] }',
        '    { "path": "app/services/media_service.py", "summary": "Media validation, storage backend, thumbnails", "language": "python", "exports": ["MediaService"], "uses": [{"from": "app.repositories.media_repo", "members": ["MediaRepo"]}] }',
        '    { "path": "tests/test_media.py", "summary": "Upload validation + storage tests", "language": "python", "exports": [], "uses": [{"from": "app.services.media_service", "members": ["MediaService"]}] }',
        '    { "path": "alembic/versions/0001_initial.py", "summary": "Initial schema migration", "language": "python", "exports": ["upgrade", "downgrade"], "uses": [] }',
        '    { "path": "requirements.txt", "summary": "Python deps", "language": "text", "exports": [], "uses": [] }',
        '    { "path": "README.md", "summary": "Run + config docs", "language": "markdown", "exports": [], "uses": [] }',
    ],
)


# Example 4 — Social Network (TypeScript, ~27 files)
SOCIAL = blueprint(
    "social network with user profiles, posts, comments, likes, follows, a personalized feed, and notifications",
    "Timeline platform: auth, profiles, posts, comments, likes, follows, feed assembly, notifications. TypeScript with src/ layering (routes → services → repositories → models), feed as an aggregation service over post+follow repos.",
    [
        '    { "path": "src/main.ts", "summary": "Entry: boots express, wires routes+services+db, listens", "language": "typescript", "exports": ["main"], "uses": [{"from": "src/config", "members": ["loadConfig"]}, {"from": "src/routes", "members": ["buildRouter"]}] }',
        '    { "path": "src/config.ts", "summary": "Env config: db url, jwt secret, port", "language": "typescript", "exports": ["loadConfig", "Config"], "uses": [] }',
        '    { "path": "src/models/user.ts", "summary": "User profile + privacy settings", "language": "typescript", "exports": ["User", "PrivacyLevel"], "uses": [] }',
        '    { "path": "src/models/post.ts", "summary": "Post + visibility", "language": "typescript", "exports": ["Post"], "uses": [] }',
        '    { "path": "src/models/comment.ts", "summary": "Comment on a post", "language": "typescript", "exports": ["Comment"], "uses": [] }',
        '    { "path": "src/models/follow.ts", "summary": "Follow relationship between users", "language": "typescript", "exports": ["Follow"], "uses": [] }',
        '    { "path": "src/models/like.ts", "summary": "Like on a post", "language": "typescript", "exports": ["Like"], "uses": [] }',
        '    { "path": "src/models/notification.ts", "summary": "Notification + type", "language": "typescript", "exports": ["Notification", "NotificationType"], "uses": [] }',
        '    { "path": "src/repositories/userRepo.ts", "summary": "Profile persistence", "language": "typescript", "exports": ["UserRepo"], "uses": [{"from": "src/models/user", "members": ["User"]}] }',
        '    { "path": "src/repositories/postRepo.ts", "summary": "Post + like persistence", "language": "typescript", "exports": ["PostRepo"], "uses": [{"from": "src/models/post", "members": ["Post"]}, {"from": "src/models/like", "members": ["Like"]}] }',
        '    { "path": "src/repositories/commentRepo.ts", "summary": "Comment persistence", "language": "typescript", "exports": ["CommentRepo"], "uses": [{"from": "src/models/comment", "members": ["Comment"]}] }',
        '    { "path": "src/repositories/followRepo.ts", "summary": "Follow graph: who follows whom", "language": "typescript", "exports": ["FollowRepo"], "uses": [{"from": "src/models/follow", "members": ["Follow"]}] }',
        '    { "path": "src/repositories/notificationRepo.ts", "summary": "Notification persistence", "language": "typescript", "exports": ["NotificationRepo"], "uses": [{"from": "src/models/notification", "members": ["Notification"]}] }',
        '    { "path": "src/services/authService.ts", "summary": "Signup, login, JWT", "language": "typescript", "exports": ["AuthService"], "uses": [{"from": "src/repositories/userRepo", "members": ["UserRepo"]}] }',
        '    { "path": "src/services/postService.ts", "summary": "Create/delete posts, like/unlike, comment, visibility checks", "language": "typescript", "exports": ["PostService"], "uses": [{"from": "src/repositories/postRepo", "members": ["PostRepo"]}, {"from": "src/repositories/commentRepo", "members": ["CommentRepo"]}] }',
        '    { "path": "src/services/feedService.ts", "summary": "Assembles timeline: follow list + recent posts, privacy filtered", "language": "typescript", "exports": ["FeedService"], "uses": [{"from": "src/repositories/followRepo", "members": ["FollowRepo"]}, {"from": "src/repositories/postRepo", "members": ["PostRepo"]}] }',
        '    { "path": "src/services/notifyService.ts", "summary": "Creates + lists notifications on follow/like/comment", "language": "typescript", "exports": ["NotifyService"], "uses": [{"from": "src/repositories/notificationRepo", "members": ["NotificationRepo"]}] }',
        '    { "path": "src/services/profileService.ts", "summary": "View/update profile + follow/unfollow users", "language": "typescript", "exports": ["ProfileService"], "uses": [{"from": "src/repositories/userRepo", "members": ["UserRepo"]}, {"from": "src/repositories/followRepo", "members": ["FollowRepo"]}] }',
        '    { "path": "src/routes/authRoutes.ts", "summary": "POST /auth/register, /auth/login", "language": "typescript", "exports": ["authRoutes"], "uses": [{"from": "src/services/authService", "members": ["AuthService"]}] }',
        '    { "path": "src/routes/postRoutes.ts", "summary": "POST/GET/DELETE posts, likes, comments", "language": "typescript", "exports": ["postRoutes"], "uses": [{"from": "src/services/postService", "members": ["PostService"]}] }',
        '    { "path": "src/routes/feedRoutes.ts", "summary": "GET /feed (paginated timeline)", "language": "typescript", "exports": ["feedRoutes"], "uses": [{"from": "src/services/feedService", "members": ["FeedService"]}] }',
        '    { "path": "src/routes/notifyRoutes.ts", "summary": "GET /notifications", "language": "typescript", "exports": ["notifyRoutes"], "uses": [{"from": "src/services/notifyService", "members": ["NotifyService"]}] }',
        '    { "path": "src/routes/router.ts", "summary": "Combines subrouters + auth middleware", "language": "typescript", "exports": ["buildRouter"], "uses": [{"from": "src/routes/authRoutes", "members": ["authRoutes"]}, {"from": "src/routes/postRoutes", "members": ["postRoutes"]}, {"from": "src/routes/feedRoutes", "members": ["feedRoutes"]}] }',
        '    { "path": "src/services/feedService.test.ts", "summary": "Feed privacy + ordering tests", "language": "typescript", "exports": [], "uses": [{"from": "src/services/feedService", "members": ["FeedService"]}] }',
        '    { "path": "src/services/postService.test.ts", "summary": "Post visibility + like tests", "language": "typescript", "exports": [], "uses": [{"from": "src/services/postService", "members": ["PostService"]}] }',
        '    { "path": "package.json", "summary": "Deps + scripts", "language": "json", "exports": [], "uses": [] }',
        '    { "path": "tsconfig.json", "summary": "TS compiler config", "language": "json", "exports": [], "uses": [] }',
        '    { "path": "README.md", "summary": "Setup + run docs", "language": "markdown", "exports": [], "uses": [] }',
        '    { "path": ".env.example", "summary": "Documented env var template", "language": "dotenv", "exports": [], "uses": [] }',
    ],
)

# Example 5 — Banking Core (C#, ~27 files)
BANKING = blueprint(
    "banking backend with accounts, transfers, a double-entry ledger, statements, and audit logging",
    "Financial core: accounts, double-entry ledger, transfers (with funds check + idempotency), statements, audit log. C# with .NET solution layering (Api → Application → Domain → Infrastructure), each layer one project, repositories behind interfaces so the ledger stays pure.",
    [
        '    { "path": "src/Bank.Api/Program.cs", "summary": "Entry: ASP.NET host, DI wiring, middleware, controllers", "language": "csharp", "exports": ["Main"], "uses": [{"from": "src/Bank.Api/Controllers", "members": ["AccountsController", "TransfersController"]}] }',
        '    { "path": "src/Bank.Api/appsettings.json", "summary": "Connection strings + limits config", "language": "json", "exports": [], "uses": [] }',
        '    { "path": "src/Bank.Domain/Accounts/Account.cs", "summary": "Account entity: number, owner, balance", "language": "csharp", "exports": ["Account"], "uses": [] }',
        '    { "path": "src/Bank.Domain/Accounts/AccountType.cs", "summary": "Enum: checking, savings, credit", "language": "csharp", "exports": ["AccountType"], "uses": [] }',
        '    { "path": "src/Bank.Domain/Ledger/LedgerEntry.cs", "summary": "Double-entry row: debit/credit, amount, reference", "language": "csharp", "exports": ["LedgerEntry"], "uses": [] }',
        '    { "path": "src/Bank.Domain/Transfers/TransferRequest.cs", "summary": "DTO: from/to accounts, amount, memo", "language": "csharp", "exports": ["TransferRequest"], "uses": [] }',
        '    { "path": "src/Bank.Domain/Transfers/TransferResult.cs", "summary": "Outcome: success/failure reason, new balances", "language": "csharp", "exports": ["TransferResult"], "uses": [] }',
        '    { "path": "src/Bank.Domain/Audit/AuditEvent.cs", "summary": "Immutable audit trail record", "language": "csharp", "exports": ["AuditEvent"], "uses": [] }',
        '    { "path": "src/Bank.Infrastructure/Repositories/AccountRepository.cs", "summary": "Account persistence + optimistic concurrency on balance", "language": "csharp", "exports": ["AccountRepository"], "uses": [{"from": "src/Bank.Domain/Accounts", "members": ["Account", "AccountType"]}] }',
        '    { "path": "src/Bank.Infrastructure/Repositories/LedgerRepository.cs", "summary": "Ledger rows in one transaction per operation", "language": "csharp", "exports": ["LedgerRepository"], "uses": [{"from": "src/Bank.Domain/Ledger", "members": ["LedgerEntry"]}] }',
        '    { "path": "src/Bank.Infrastructure/Repositories/AuditRepository.cs", "summary": "Append-only audit writes", "language": "csharp", "exports": ["AuditRepository"], "uses": [{"from": "src/Bank.Domain/Audit", "members": ["AuditEvent"]}] }',
        '    { "path": "src/Bank.Application/Services/AccountService.cs", "summary": "Open/close accounts, balance queries, statement generation", "language": "csharp", "exports": ["AccountService"], "uses": [{"from": "src/Bank.Infrastructure/Repositories", "members": ["AccountRepository", "LedgerRepository"]}] }',
        '    { "path": "src/Bank.Application/Services/TransferService.cs", "summary": "Validates funds, double-entry post, idempotency key, audit event — single transaction", "language": "csharp", "exports": ["TransferService"], "uses": [{"from": "src/Bank.Infrastructure/Repositories", "members": ["AccountRepository", "LedgerRepository", "AuditRepository"]}, {"from": "src/Bank.Domain/Transfers", "members": ["TransferRequest", "TransferResult"]}] }',
        '    { "path": "src/Bank.Application/Services/StatementService.cs", "summary": "Builds monthly statement from ledger rows", "language": "csharp", "exports": ["StatementService"], "uses": [{"from": "src/Bank.Infrastructure/Repositories", "members": ["LedgerRepository"]}] }',
        '    { "path": "src/Bank.Api/Controllers/AccountsController.cs", "summary": "GET/POST /accounts, GET /accounts/{id}/statement", "language": "csharp", "exports": ["AccountsController"], "uses": [{"from": "src/Bank.Application/Services", "members": ["AccountService", "StatementService"]}] }',
        '    { "path": "src/Bank.Api/Controllers/TransfersController.cs", "summary": "POST /transfers (idempotency-key header)", "language": "csharp", "exports": ["TransfersController"], "uses": [{"from": "src/Bank.Application/Services", "members": ["TransferService"]}] }',
        '    { "path": "src/Bank.Api/Controllers/Controllers.csproj", "summary": "Controllers project file", "language": "xml", "exports": [], "uses": [] }',
        '    { "path": "tests/Bank.Tests/TransferServiceTests.cs", "summary": "Tests insufficient funds + idempotent retry", "language": "csharp", "exports": ["TransferServiceTests"], "uses": [{"from": "src/Bank.Application/Services", "members": ["TransferService"]}] }',
        '    { "path": "tests/Bank.Tests/LedgerBalancesTests.cs", "summary": "Tests ledger debits equal credits", "language": "csharp", "exports": ["LedgerBalancesTests"], "uses": [{"from": "src/Bank.Application/Services", "members": ["AccountService"]}] }',
        '    { "path": "Bank.sln", "summary": "Solution wiring all projects", "language": "text", "exports": [], "uses": [] }',
        '    { "path": "src/Bank.Domain/Bank.Domain.csproj", "summary": "Domain project (no external deps)", "language": "xml", "exports": [], "uses": [] }',
        '    { "path": "src/Bank.Infrastructure/Bank.Infrastructure.csproj", "summary": "Infrastructure project", "language": "xml", "exports": [], "uses": [] }',
        '    { "path": "src/Bank.Application/Bank.Application.csproj", "summary": "Application project", "language": "xml", "exports": [], "uses": [] }',
        '    { "path": "src/Bank.Api/Bank.Api.csproj", "summary": "Web API project", "language": "xml", "exports": [], "uses": [] }',
        '    { "path": "README.md", "summary": "Run, config, test docs", "language": "markdown", "exports": [], "uses": [] }',
        '    { "path": ".env.example", "summary": "Documented env var template", "language": "dotenv", "exports": [], "uses": [] }',
    ],
)

# Example 6 — Realtime Chat (Go, ~26 files)
CHAT = blueprint(
    "realtime chat platform with WebSocket connections, rooms, direct messages, presence, and history",
    "Realtime messaging: WebSocket hub (goroutines + channels), rooms, DMs, presence, history. Go with cmd/internal layout; hub owns all connections, services own business rules, handlers bridge HTTP/WS to the hub.",
    [
        '    { "path": "cmd/server/main.go", "summary": "Entry: loads config, starts hub, wires services+handlers, HTTP + WS server", "language": "go", "exports": ["main"], "uses": [{"from": "internal/config", "members": ["Load", "Config"]}, {"from": "internal/handlers", "members": ["NewRouter"]}] }',
        '    { "path": "internal/config/config.go", "summary": "Env config: db dsn, port, jwt secret", "language": "go", "exports": ["Load", "Config"], "uses": [] }',
        '    { "path": "internal/models/user.go", "summary": "User entity", "language": "go", "exports": ["User"], "uses": [] }',
        '    { "path": "internal/models/message.go", "summary": "Message: room, sender, body, timestamp", "language": "go", "exports": ["Message"], "uses": [] }',
        '    { "path": "internal/models/room.go", "summary": "Room + membership", "language": "go", "exports": ["Room", "Membership"], "uses": [] }',
        '    { "path": "internal/repository/user_repo.go", "summary": "User persistence + presence flags", "language": "go", "exports": ["UserRepo"], "uses": [{"from": "internal/models", "members": ["User"]}] }',
        '    { "path": "internal/repository/message_repo.go", "summary": "Message insert + history pagination", "language": "go", "exports": ["MessageRepo"], "uses": [{"from": "internal/models", "members": ["Message"]}] }',
        '    { "path": "internal/repository/room_repo.go", "summary": "Room CRUD + membership", "language": "go", "exports": ["RoomRepo"], "uses": [{"from": "internal/models", "members": ["Room", "Membership"]}] }',
        '    { "path": "internal/hub/hub.go", "summary": "Owns all live connections; register/unregister, broadcast to room, fan-out", "language": "go", "exports": ["Hub", "NewHub", "Register", "Unregister", "Broadcast"], "uses": [] }',
        '    { "path": "internal/hub/client.go", "summary": "Per-connection reader/writer goroutines", "language": "go", "exports": ["Client", "NewClient"], "uses": [{"from": "internal/hub", "members": ["Hub"]}] }',
        '    { "path": "internal/service/message_service.go", "summary": "Persists messages, routes to hub broadcast", "language": "go", "exports": ["MessageService"], "uses": [{"from": "internal/repository", "members": ["MessageRepo"]}, {"from": "internal/hub", "members": ["Hub"]}] }',
        '    { "path": "internal/service/room_service.go", "summary": "Room create/join/leave + membership checks", "language": "go", "exports": ["RoomService"], "uses": [{"from": "internal/repository", "members": ["RoomRepo"]}] }',
        '    { "path": "internal/service/auth_service.go", "summary": "Login, JWT, token→user resolution for WS handshake", "language": "go", "exports": ["AuthService"], "uses": [{"from": "internal/repository", "members": ["UserRepo"]}] }',
        '    { "path": "internal/service/presence_service.go", "summary": "Tracks online status via hub register/unregister events", "language": "go", "exports": ["PresenceService"], "uses": [{"from": "internal/hub", "members": ["Hub"]}, {"from": "internal/repository", "members": ["UserRepo"]}] }',
        '    { "path": "internal/service/dm_service.go", "summary": "1:1 direct messages: resolves peer, persists, routes to hub", "language": "go", "exports": ["DmService"], "uses": [{"from": "internal/repository", "members": ["MessageRepo", "UserRepo"]}, {"from": "internal/hub", "members": ["Hub"]}] }',
        '    { "path": "internal/handlers/ws_handlers.go", "summary": "WebSocket upgrade, auth handshake, routes frames to hub/client", "language": "go", "exports": ["WsHandler"], "uses": [{"from": "internal/service", "members": ["AuthService", "MessageService"]}] }',
        '    { "path": "internal/handlers/room_handlers.go", "summary": "REST: create/join rooms, list members", "language": "go", "exports": ["RoomHandlers"], "uses": [{"from": "internal/service", "members": ["RoomService"]}] }',
        '    { "path": "internal/handlers/history_handlers.go", "summary": "REST: GET /rooms/{id}/messages?before=ts", "language": "go", "exports": ["HistoryHandlers"], "uses": [{"from": "internal/service", "members": ["MessageService"]}] }',
        '    { "path": "internal/handlers/presence_handlers.go", "summary": "REST: GET /users/online (presence snapshot)", "language": "go", "exports": ["PresenceHandlers"], "uses": [{"from": "internal/service", "members": ["PresenceService"]}] }',
        '    { "path": "internal/handlers/router.go", "summary": "Mux: REST routes + /ws upgrade endpoint + auth middleware", "language": "go", "exports": ["NewRouter"], "uses": [{"from": "internal/handlers", "members": ["WsHandler", "RoomHandlers", "HistoryHandlers", "PresenceHandlers"]}] }',
        '    { "path": "internal/hub/hub_test.go", "summary": "Tests broadcast fan-out to room subscribers", "language": "go", "exports": [], "uses": [{"from": "internal/hub", "members": ["Hub", "NewHub"]}] }',
        '    { "path": "internal/service/message_service_test.go", "summary": "Tests message persistence + ordering", "language": "go", "exports": [], "uses": [{"from": "internal/service", "members": ["MessageService"]}] }',
        '    { "path": "internal/service/dm_service_test.go", "summary": "Tests 1:1 DM routing + peer resolution", "language": "go", "exports": [], "uses": [{"from": "internal/service", "members": ["DmService"]}] }',
        '    { "path": "go.mod", "summary": "Go module definition", "language": "go", "exports": [], "uses": [] }',
        '    { "path": "README.md", "summary": "Run, connect, test docs", "language": "markdown", "exports": [], "uses": [] }',
        '    { "path": ".env.example", "summary": "Documented env var template", "language": "dotenv", "exports": [], "uses": [] }',
    ],
)

# Example 7 — Gaming Platform (TypeScript, ~29 files)
GAMING = blueprint(
    "gaming platform with user profiles, matchmaking, ranked matches, leaderboards, and tournaments",
    "Competitive gaming: profiles, matchmaking queue, match lifecycle, ELO/rank updates, leaderboards, tournaments. TypeScript event-driven: services publish match results, leaderboard/tournament services consume them; single src/ layering keeps the graph acyclic.",
    [
        '    { "path": "src/main.ts", "summary": "Entry: boots express + ws, wires services, starts matchmaking loop", "language": "typescript", "exports": ["main"], "uses": [{"from": "src/config", "members": ["loadConfig"]}, {"from": "src/routes", "members": ["buildRouter"]}] }',
        '    { "path": "src/config.ts", "summary": "Env config: db url, jwt secret, queue sizes", "language": "typescript", "exports": ["loadConfig", "Config"], "uses": [] }',
        '    { "path": "src/models/user.ts", "summary": "Player profile + rank", "language": "typescript", "exports": ["Player", "Rank"], "uses": [] }',
        '    { "path": "src/models/match.ts", "summary": "Match: players, result, rating delta", "language": "typescript", "exports": ["Match"], "uses": [] }',
        '    { "path": "src/models/queue.ts", "summary": "Matchmaking queue entry", "language": "typescript", "exports": ["QueueEntry"], "uses": [] }',
        '    { "path": "src/models/tournament.ts", "summary": "Tournament + bracket node", "language": "typescript", "exports": ["Tournament", "BracketNode"], "uses": [] }',
        '    { "path": "src/models/leaderboard.ts", "summary": "Ranked leaderboard row", "language": "typescript", "exports": ["LeaderboardRow"], "uses": [] }',
        '    { "path": "src/repositories/playerRepo.ts", "summary": "Player profile + rating persistence", "language": "typescript", "exports": ["PlayerRepo"], "uses": [{"from": "src/models/user", "members": ["Player", "Rank"]}] }',
        '    { "path": "src/repositories/matchRepo.ts", "summary": "Match persistence + history", "language": "typescript", "exports": ["MatchRepo"], "uses": [{"from": "src/models/match", "members": ["Match"]}] }',
        '    { "path": "src/repositories/tournamentRepo.ts", "summary": "Tournament + bracket persistence", "language": "typescript", "exports": ["TournamentRepo"], "uses": [{"from": "src/models/tournament", "members": ["Tournament", "BracketNode"]}] }',
        '    { "path": "src/repositories/leaderboardRepo.ts", "summary": "Ranked row persistence + top-N queries", "language": "typescript", "exports": ["LeaderboardRepo"], "uses": [{"from": "src/models/leaderboard", "members": ["LeaderboardRow"]}] }',
        '    { "path": "src/services/authService.ts", "summary": "Login, JWT, profile fetch", "language": "typescript", "exports": ["AuthService"], "uses": [{"from": "src/repositories/playerRepo", "members": ["PlayerRepo"]}] }',
        '    { "path": "src/services/matchmakingService.ts", "summary": "Queue players by rating band, emit matched pair event", "language": "typescript", "exports": ["MatchmakingService"], "uses": [{"from": "src/repositories/playerRepo", "members": ["PlayerRepo"]}, {"from": "src/models/queue", "members": ["QueueEntry"]}] }',
        '    { "path": "src/services/matchService.ts", "summary": "Records result, computes ELO delta, saves match, emits MatchCompleted event", "language": "typescript", "exports": ["MatchService"], "uses": [{"from": "src/repositories/matchRepo", "members": ["MatchRepo"]}, {"from": "src/repositories/playerRepo", "members": ["PlayerRepo"]}] }',
        '    { "path": "src/services/ratingService.ts", "summary": "Pure ELO math: expected score, delta, floor", "language": "typescript", "exports": ["RatingService", "computeElo"], "uses": [] }',
        '    { "path": "src/services/leaderboardService.ts", "summary": "Consumes MatchCompleted, upserts ranked rows", "language": "typescript", "exports": ["LeaderboardService"], "uses": [{"from": "src/repositories/leaderboardRepo", "members": ["LeaderboardRepo"]}, {"from": "src/repositories/playerRepo", "members": ["PlayerRepo"]}] }',
        '    { "path": "src/services/tournamentService.ts", "summary": "Creates brackets, advances winners on match completion", "language": "typescript", "exports": ["TournamentService"], "uses": [{"from": "src/repositories/tournamentRepo", "members": ["TournamentRepo"]}, {"from": "src/models/tournament", "members": ["BracketNode"]}] }',
        '    { "path": "src/routes/authRoutes.ts", "summary": "POST /auth/login", "language": "typescript", "exports": ["authRoutes"], "uses": [{"from": "src/services/authService", "members": ["AuthService"]}] }',
        '    { "path": "src/routes/matchRoutes.ts", "summary": "POST /matches (submit result), GET /players/{id}/matches", "language": "typescript", "exports": ["matchRoutes"], "uses": [{"from": "src/services/matchService", "members": ["MatchService"]}] }',
        '    { "path": "src/routes/queueRoutes.ts", "summary": "POST /queue (join/leave matchmaking)", "language": "typescript", "exports": ["queueRoutes"], "uses": [{"from": "src/services/matchmakingService", "members": ["MatchmakingService"]}] }',
        '    { "path": "src/routes/leaderboardRoutes.ts", "summary": "GET /leaderboard?top=50", "language": "typescript", "exports": ["leaderboardRoutes"], "uses": [{"from": "src/services/leaderboardService", "members": ["LeaderboardService"]}] }',
        '    { "path": "src/routes/tournamentRoutes.ts", "summary": "POST /tournaments, POST /tournaments/{id}/start", "language": "typescript", "exports": ["tournamentRoutes"], "uses": [{"from": "src/services/tournamentService", "members": ["TournamentService"]}] }',
        '    { "path": "src/routes/router.ts", "summary": "Combines subrouters + auth middleware", "language": "typescript", "exports": ["buildRouter"], "uses": [{"from": "src/routes/authRoutes", "members": ["authRoutes"]}, {"from": "src/routes/matchRoutes", "members": ["matchRoutes"]}, {"from": "src/routes/queueRoutes", "members": ["queueRoutes"]}] }',
        '    { "path": "src/services/ratingService.test.ts", "summary": "ELO math edge cases (draw, upset, floor)", "language": "typescript", "exports": [], "uses": [{"from": "src/services/ratingService", "members": ["computeElo"]}] }',
        '    { "path": "src/services/matchmakingService.test.ts", "summary": "Queue pairing by rating band", "language": "typescript", "exports": [], "uses": [{"from": "src/services/matchmakingService", "members": ["MatchmakingService"]}] }',
        '    { "path": "src/services/tournamentService.test.ts", "summary": "Bracket advancement tests", "language": "typescript", "exports": [], "uses": [{"from": "src/services/tournamentService", "members": ["TournamentService"]}] }',
        '    { "path": "package.json", "summary": "Deps + scripts", "language": "json", "exports": [], "uses": [] }',
        '    { "path": "tsconfig.json", "summary": "TS compiler config", "language": "json", "exports": [], "uses": [] }',
        '    { "path": "README.md", "summary": "Setup + run docs", "language": "markdown", "exports": [], "uses": [] }',
    ],
)


# ─── Spec-driven blueprint builder (valid by construction) ──────────────────
# The 7 blueprints above are fully hand-authored. The blueprints below are
# generated from compact specs so we can ship MANY more app types cheaply while
# keeping every per-file contract consistent: each feature becomes a vertical
# slice (models → repo → service → handlers/routes → test) whose exports/uses
# naming is derived programmatically, so the plan is valid JSON with coherent
# dependencies by construction (still asserted at build time by blueprint()).

def fp(path, summary, language, exports, uses):
    """Render one file entry line as compact JSON (same shape as the hand-
    authored blueprints: path, summary, language, exports, uses[].from/members)."""
    obj = {
        "path": path,
        "summary": summary,
        "language": language,
        "exports": list(exports),
        "uses": [{"from": frm, "members": list(members)} for frm, members in uses],
    }
    return "    " + json.dumps(obj, ensure_ascii=False)


def go_slice(feature, entity, blurb):
    e = entity
    return [
        fp(f"internal/models/{feature}.go", f"{e} entity + related types", "go", [e], []),
        fp(f"internal/repository/{feature}_repo.go", f"{e} persistence: CRUD + {blurb}", "go", [f"{e}Repo", f"New{e}Repo"], [("internal/models", [e])]),
        fp(f"internal/service/{feature}_service.go", f"{e} business rules: {blurb}", "go", [f"{e}Service", f"New{e}Service"], [("internal/repository", [f"{e}Repo"]), ("internal/models", [e])]),
        fp(f"internal/handlers/{feature}_handlers.go", f"HTTP endpoints for {e}", "go", [f"{e}Handlers"], [("internal/service", [f"{e}Service"])]),
        fp(f"internal/service/{feature}_service_test.go", f"Tests {e} service happy + error paths", "go", [], [("internal/service", [f"{e}Service"])]),
    ]


def go_shared(features):
    handlers = [f"{e}Handlers" for _, e, _ in features]
    return [
        fp("cmd/server/main.go", "Entry: loads config, wires repository+services+handlers, starts HTTP server, graceful shutdown", "go", ["main"], [("internal/config", ["Load", "Config"]), ("internal/handlers", ["NewRouter"])]),
        fp("internal/config/config.go", "Env-driven config: DB DSN, port, JWT secret, defaults + validation", "go", ["Load", "Config"], []),
        fp("internal/middleware/auth.go", "Auth (JWT verify), logging, recover middleware chain", "go", ["AuthMiddleware", "LoggingMiddleware", "RecoverMiddleware"], []),
        fp("internal/handlers/router.go", "Wires all handlers + middleware into a mux", "go", ["NewRouter"], [("internal/handlers", handlers), ("internal/middleware", ["AuthMiddleware", "LoggingMiddleware", "RecoverMiddleware"])]),
        fp("internal/handlers/health_handlers.go", "REST: GET /health + readiness probe", "go", ["HealthHandlers"], []),
        fp("go.mod", "Go module definition", "go", [], []),
        fp("README.md", "Run/build/test instructions + env vars", "markdown", [], []),
        fp(".env.example", "Documented env var template", "dotenv", [], []),
    ]


def ts_slice(feature, entity, blurb):
    e = entity
    return [
        fp(f"src/models/{feature}.ts", f"{e} type + related types", "typescript", [e], []),
        fp(f"src/repositories/{feature}Repo.ts", f"{e} persistence", "typescript", [f"{e}Repo"], [(f"src/models/{feature}", [e])]),
        fp(f"src/services/{feature}Service.ts", f"{e} business rules: {blurb}", "typescript", [f"{e}Service"], [(f"src/repositories/{feature}Repo", [f"{e}Repo"]), (f"src/models/{feature}", [e])]),
        fp(f"src/routes/{feature}Routes.ts", f"HTTP routes for {e}", "typescript", [f"{feature}Routes"], [(f"src/services/{feature}Service", [f"{e}Service"])]),
        fp(f"src/services/{feature}Service.test.ts", f"{e} service unit tests", "typescript", [], [(f"src/services/{feature}Service", [f"{e}Service"])]),
    ]


def ts_shared(features):
    routes = [f"{f}Routes" for f, _, _ in features]
    return [
        fp("src/main.ts", "Entry: boots express, wires routes+services+db, listens", "typescript", ["main"], [("src/config", ["loadConfig"]), ("src/routes", ["buildRouter"])]),
        fp("src/config.ts", "Env config: db url, jwt secret, port", "typescript", ["loadConfig", "Config"], []),
        fp("src/middleware/auth.ts", "JWT auth middleware for protected routes", "typescript", ["requireAuth"], []),
        fp("src/routes/router.ts", "Combines subrouters + auth middleware", "typescript", ["buildRouter"], [("src/routes", routes), ("src/middleware", ["requireAuth"])]),
        fp("package.json", "Deps + scripts", "json", [], []),
        fp("tsconfig.json", "TS compiler config", "json", [], []),
        fp("README.md", "Setup + run docs", "markdown", [], []),
        fp(".env.example", "Documented env var template", "dotenv", [], []),
    ]


def py_slice(feature, entity, blurb):
    e = entity
    return [
        fp(f"app/models/{feature}.py", f"{e} model", "python", [e], []),
        fp(f"app/repositories/{feature}_repo.py", f"{e} persistence", "python", [f"{e}Repo"], [(f"app.models.{feature}", [e])]),
        fp(f"app/services/{feature}_service.py", f"{e} business rules: {blurb}", "python", [f"{e}Service"], [(f"app.repositories.{feature}_repo", [f"{e}Repo"]), (f"app.models.{feature}", [e])]),
        fp(f"app/api/{feature}.py", f"REST endpoints for {e}", "python", [f"{feature}_router"], [(f"app.services.{feature}_service", [f"{e}Service"])]),
        fp(f"tests/test_{feature}.py", f"{e} service tests", "python", [], [(f"app.services.{feature}_service", [f"{e}Service"])]),
    ]


def py_shared(features):
    routers = [f"{f}_router" for f, _, _ in features]
    return [
        fp("app/main.py", "FastAPI app factory, mounts routers, startup DB init", "python", ["create_app"], [("app.config", ["get_settings"]), ("app.api.router", ["api_router"])]),
        fp("app/config.py", "Pydantic settings from env", "python", ["Settings", "get_settings"], []),
        fp("app/db.py", "Database session + engine setup", "python", ["get_db", "engine"], []),
        fp("app/api/router.py", "Aggregates sub-routers under /api", "python", ["api_router"], [("app.api", routers)]),
        fp("alembic/versions/0001_initial.py", "Initial schema migration", "python", ["upgrade", "downgrade"], []),
        fp("requirements.txt", "Python deps", "text", [], []),
        fp("README.md", "Run + config docs", "markdown", [], []),
        fp(".env.example", "Documented env var template", "dotenv", [], []),
    ]


def cs_slice(feature, entity, blurb):
    e = entity
    return [
        fp(f"src/App.Domain/{e}/{e}.cs", f"{e} entity", "csharp", [e], []),
        fp(f"src/App.Infrastructure/Repositories/{e}Repository.cs", f"{e} persistence", "csharp", [f"{e}Repository"], [(f"src/App.Domain/{e}", [e])]),
        fp(f"src/App.Application/Services/{e}Service.cs", f"{e} business rules: {blurb}", "csharp", [f"{e}Service"], [(f"src/App.Infrastructure/Repositories", [f"{e}Repository"]), (f"src/App.Domain/{e}", [e])]),
        fp(f"src/App.Api/Controllers/{e}Controller.cs", f"REST endpoints for {e}", "csharp", [f"{e}Controller"], [(f"src/App.Application/Services", [f"{e}Service"])]),
        fp(f"tests/App.Tests/{e}ServiceTests.cs", f"{e} service unit tests", "csharp", [f"{e}ServiceTests"], [(f"src/App.Application/Services", [f"{e}Service"])]),
    ]


def cs_shared(features):
    controllers = [f"{e}Controller" for _, e, _ in features]
    return [
        fp("src/App.Api/Program.cs", "Entry: ASP.NET host, DI wiring, middleware, controllers", "csharp", ["Main"], [("src/App.Api/Controllers", controllers)]),
        fp("src/App.Api/appsettings.json", "Connection strings + limits config", "json", [], []),
        fp("App.sln", "Solution wiring all projects", "text", [], []),
        fp("src/App.Domain/App.Domain.csproj", "Domain project (no external deps)", "xml", [], []),
        fp("src/App.Infrastructure/App.Infrastructure.csproj", "Infrastructure project", "xml", [], []),
        fp("src/App.Application/App.Application.csproj", "Application project", "xml", [], []),
        fp("src/App.Api/App.Api.csproj", "Web API project", "xml", [], []),
        fp("README.md", "Run, config, test docs", "markdown", [], []),
        fp(".env.example", "Documented env var template", "dotenv", [], []),
    ]


SLICES = {"go": go_slice, "typescript": ts_slice, "python": py_slice, "csharp": cs_slice}
SHARED = {"go": go_shared, "typescript": ts_shared, "python": py_shared, "csharp": cs_shared}


def build_blueprint(spec):
    """Render a complete plan for one spec: 5-feature vertical slices + the
    language's shared layers (entry, config, middleware/db, router, health,
    tests, build files). Contracts are derived consistently, so the plan is
    valid by construction; blueprint() still asserts the JSON parses."""
    lang = spec["language"]
    files = []
    for feature, entity, blurb in spec["features"]:
        files += SLICES[lang](feature, entity, blurb)
    files += SHARED[lang](spec["features"])
    return blueprint(spec["goal"], spec["intro"], files)


# ─── 16 additional app-type specs (4 per language) ───────────────────────────
BLUEPRINT_SPECS = [
    # Go
    {"id": "filebox-go", "language": "go",
     "goal": "file sharing service with user accounts, file uploads, folders, shares, and an activity log",
     "intro": "Secure file storage: validated uploads, folder hierarchy, share links with expiry, append-only activity log. Go cmd/internal layering; handlers → services → repository → models.",
     "features": [("users", "User", "auth + quota limits"), ("files", "File", "upload validation + metadata"), ("folders", "Folder", "hierarchy + move rules"), ("shares", "Share", "expiring share links"), ("activity", "ActivityLog", "append-only audit trail")]},
    {"id": "shortlink-go", "language": "go",
     "goal": "URL shortener with links, click analytics, user accounts, and campaign tracking",
     "intro": "Link shortening at scale: collision-safe keys, per-click analytics, per-user link management, campaign attribution. Go cmd/internal layering, handlers → services → repository → models.",
     "features": [("users", "User", "accounts + API keys"), ("links", "Link", "key generation + expiry"), ("clicks", "ClickEvent", "per-click tracking"), ("campaigns", "Campaign", "attribution + tag filtering")]},
    {"id": "jobboard-go", "language": "go",
     "goal": "job board with companies, job listings, candidates, applications, and matching",
     "intro": "Recruitment platform: company profiles, job listings, candidate resumes, applications with status flow, skill-based matching. Go cmd/internal layering.",
     "features": [("companies", "Company", "profiles + verification"), ("jobs", "Job", "listings + status flow"), ("candidates", "Candidate", "resume + skills"), ("applications", "Application", "apply + status transitions"), ("matches", "Match", "skill-based scoring")]},
    {"id": "kitchen-go", "language": "go",
     "goal": "restaurant ordering system with menus, tables, orders, a kitchen queue, and payments",
     "intro": "Point-of-sale: menu management, table state, order lifecycle, kitchen ticket queue, payment reconciliation. Go cmd/internal layering with feature slices.",
     "features": [("menus", "Menu", "items + availability"), ("tables", "Table", "seat state + assignment"), ("orders", "Order", "order lifecycle"), ("kitchen", "KitchenQueue", "ticket queue + completion"), ("payments", "Payment", "charge + reconcile")]},
    # TypeScript
    {"id": "fitness-ts", "language": "typescript",
     "goal": "fitness tracker with users, workouts, exercises, goals, and progress analytics",
     "intro": "Health tracking: workout logging, exercise library, goal setting, progress analytics over time. TypeScript src/ layering, routes → services → repositories → models.",
     "features": [("users", "User", "profiles + auth"), ("workouts", "Workout", "session logging"), ("exercises", "Exercise", "library + muscles"), ("goals", "Goal", "targets + tracking"), ("progress", "ProgressPoint", "analytics rollups")]},
    {"id": "kanban-ts", "language": "typescript",
     "goal": "project management tool with projects, boards, tasks, comments, and activity",
     "intro": "Kanban workspace: project/board hierarchy, task lifecycle across columns, comments, activity feed. TypeScript src/ layering with feature slices.",
     "features": [("projects", "Project", "workspace + members"), ("boards", "Board", "columns + ordering"), ("tasks", "Task", "cards + status flow"), ("comments", "Comment", "task discussion"), ("activity", "Activity", "change feed")]},
    {"id": "stream-ts", "language": "typescript",
     "goal": "music streaming platform with artists, albums, tracks, playlists, and playback history",
     "intro": "Streaming catalog: artist/album/track hierarchy, user playlists, playback history for recommendations. TypeScript src/ layering.",
     "features": [("artists", "Artist", "profiles + releases"), ("albums", "Album", "release grouping"), ("tracks", "Track", "metadata + audio refs"), ("playlists", "Playlist", "curation + ordering"), ("history", "PlaybackEvent", "listening log")]},
    {"id": "news-ts", "language": "typescript",
     "goal": "news aggregator with feeds, articles, users, bookmarks, and alerts",
     "intro": "RSS-style aggregation: feed subscriptions, deduped article ingestion, user bookmarks, keyword alerts. TypeScript src/ layering.",
     "features": [("feeds", "Feed", "subscriptions + fetching"), ("articles", "Article", "ingest + dedupe"), ("users", "User", "accounts + preferences"), ("bookmarks", "Bookmark", "saved articles"), ("alerts", "Alert", "keyword notifications")]},
    # Python
    {"id": "forum-python", "language": "python",
     "goal": "community forum with users, threads, posts, votes, and moderation",
     "intro": "Discussion platform: threads with posts, vote scoring, moderation queue. FastAPI with routers → services → repositories → models.",
     "features": [("users", "User", "accounts + reputation"), ("threads", "Thread", "topics + tags"), ("posts", "Post", "replies + pagination"), ("votes", "Vote", "score calculation"), ("moderation", "Report", "review queue")]},
    {"id": "academy-python", "language": "python",
     "goal": "e-learning platform with courses, lessons, enrollments, quizzes, and progress",
     "intro": "Course platform: course/lesson hierarchy, enrollment, quiz grading, progress tracking. FastAPI with routers → services → repositories → models.",
     "features": [("courses", "Course", "catalog + instructors"), ("lessons", "Lesson", "content + ordering"), ("enrollments", "Enrollment", "access + completion"), ("quizzes", "Quiz", "questions + grading"), ("progress", "ProgressRecord", "per-course tracking")]},
    {"id": "helpdesk-python", "language": "python",
     "goal": "help desk with tickets, agents, responses, SLAs, and reports",
     "intro": "Support platform: ticket lifecycle, agent assignment, response threads, SLA policies, report queries. FastAPI with routers → services → repositories → models.",
     "features": [("tickets", "Ticket", "lifecycle + priority"), ("agents", "Agent", "roster + assignment"), ("responses", "Response", "thread + timestamps"), ("slas", "SlaPolicy", "deadline rules"), ("reports", "Report", "aggregate queries")]},
    {"id": "estate-python", "language": "python",
     "goal": "real estate platform with listings, agents, saved searches, tour bookings, and favorites",
     "intro": "Property platform: listing lifecycle, agent profiles, saved search alerts, tour scheduling, favorites. FastAPI with routers → services → repositories → models.",
     "features": [("listings", "Listing", "lifecycle + photos"), ("agents", "Agent", "profiles + listings"), ("searches", "SavedSearch", "filters + alerts"), ("tours", "TourBooking", "scheduling + confirm"), ("favorites", "Favorite", "user shortlists")]},
    # C#
    {"id": "expense-csharp", "language": "csharp",
     "goal": "personal finance app with accounts, transactions, budgets, categories, and reports",
     "intro": "Finance manager: account tracking, categorized transactions, budget envelopes, report queries. .NET solution layering (Api → Application → Domain → Infrastructure).",
     "features": [("accounts", "Account", "balances + types"), ("transactions", "Transaction", "categorized entries"), ("budgets", "Budget", "envelopes + limits"), ("categories", "Category", "taxonomy + rules"), ("reports", "Report", "aggregate queries")]},
    {"id": "hr-csharp", "language": "csharp",
     "goal": "HR management with employees, departments, time-off requests, reviews, and payroll",
     "intro": "Workforce platform: employee records, department org chart, time-off workflow, performance reviews, payroll runs. .NET solution layering.",
     "features": [("employees", "Employee", "records + status"), ("departments", "Department", "org hierarchy"), ("timeoffs", "TimeOffRequest", "request workflow"), ("reviews", "PerformanceReview", "cycles + scores"), ("payroll", "PayrollRun", "runs + payslips")]},
    {"id": "crm-csharp", "language": "csharp",
     "goal": "CRM with contacts, companies, deals, activities, and pipelines",
     "intro": "Sales CRM: contact/company records, deal stages in pipelines, activity logging. .NET solution layering (Api → Application → Domain → Infrastructure).",
     "features": [("contacts", "Contact", "records + tags"), ("companies", "Company", "accounts + hierarchy"), ("deals", "Deal", "stages + amounts"), ("activities", "Activity", "interaction log"), ("pipelines", "Pipeline", "stage definitions + order")]},
    {"id": "clinic-csharp", "language": "csharp",
     "goal": "clinic management with patients, appointments, doctors, prescriptions, and billing",
     "intro": "Medical practice: patient records, appointment scheduling, doctor roster, prescriptions, invoice billing. .NET solution layering.",
     "features": [("patients", "Patient", "records + history"), ("appointments", "Appointment", "scheduling + status"), ("doctors", "Doctor", "roster + specialties"), ("prescriptions", "Prescription", "medication + refills"), ("billing", "Invoice", "charges + payments")]},
    {"id": "fleet-go", "language": "go",
     "goal": "fleet management system with vehicles, drivers, routes, shipments, and telemetry",
     "intro": "Fleet tracking: vehicle registry, driver assignment, route planning, shipment status, GPS telemetry ingestion. Go cmd/internal layering, handlers → services → repository → models.",
     "features": [("vehicles", "Vehicle", "registry + status"), ("drivers", "Driver", "assignments + hours"), ("routes", "Route", "planning + stops"), ("shipments", "Shipment", "status + tracking"), ("telemetry", "TelemetryReading", "GPS ingestion + alerts")]},
    {"id": "paygate-go", "language": "go",
     "goal": "payment gateway with merchants, payments, payouts, webhooks, and reconciliation",
     "intro": "Payment processing: merchant onboarding, payment capture with idempotency, payout scheduling, webhook delivery, end-of-day reconciliation. Go cmd/internal layering with event-driven services.",
     "features": [("merchants", "Merchant", "onboarding + credentials"), ("payments", "Payment", "capture + idempotency"), ("payouts", "Payout", "scheduling + transfer"), ("webhooks", "WebhookDelivery", "retry + signatures"), ("reconciliation", "ReconciliationRun", "settlement matching")]},
    {"id": "teamchat-go", "language": "go",
     "goal": "team chat application with channels, members, messages, threads, and reactions",
     "intro": "Slack-style workspace chat: channel membership, threaded messages, reactions, presence. Go cmd/internal layering with a WebSocket hub for realtime delivery.",
     "features": [("channels", "Channel", "workspace + membership"), ("members", "Membership", "roles + invites"), ("messages", "Message", "post + edit history"), ("threads", "Thread", "replies + ordering"), ("reactions", "Reaction", "emoji + counts")]},
    {"id": "subbilling-go", "language": "go",
     "goal": "subscription billing system with plans, customers, subscriptions, invoices, and usage metering",
     "intro": "SaaS billing: plan catalog, customer lifecycle, subscription states, prorated invoicing, usage metering. Go cmd/internal layering, handlers → services → repository → models.",
     "features": [("plans", "Plan", "catalog + pricing"), ("customers", "Customer", "accounts + tax info"), ("subscriptions", "Subscription", "lifecycle + renewal"), ("invoices", "Invoice", "billing + payment"), ("usage", "UsageRecord", "metering + quotas")]},
    {"id": "iot-ts", "language": "typescript",
     "goal": "IoT dashboard with devices, telemetry streams, alerts, dashboards, and user accounts",
     "intro": "Device monitoring: device registry, time-series telemetry, threshold alerts, configurable dashboards. TypeScript src/ layering with an ingestion pipeline.",
     "features": [("devices", "Device", "registry + provisioning"), ("telemetry", "TelemetryPoint", "time-series ingestion"), ("alerts", "Alert", "threshold rules + firing"), ("dashboards", "Dashboard", "widgets + layout"), ("users", "User", "accounts + scopes")]},
    {"id": "hotel-ts", "language": "typescript",
     "goal": "hotel booking platform with hotels, rooms, reservations, guests, and availability",
     "intro": "Hospitality booking: property catalog, room inventory, reservation lifecycle with date-range availability, guest profiles. TypeScript src/ layering, routes → services → repositories → models.",
     "features": [("hotels", "Hotel", "properties + amenities"), ("rooms", "Room", "inventory + rates"), ("reservations", "Reservation", "booking + status flow"), ("guests", "Guest", "profiles + history"), ("availability", "Availability", "date-range checks")]},
    {"id": "courier-ts", "language": "typescript",
     "goal": "courier delivery service with couriers, packages, pickups, deliveries, and live tracking",
     "intro": "Last-mile logistics: courier roster, package registration, pickup scheduling, delivery status, live location tracking. TypeScript src/ layering with realtime updates.",
     "features": [("couriers", "Courier", "roster + availability"), ("packages", "Package", "registration + labels"), ("pickups", "Pickup", "scheduling + confirm"), ("deliveries", "Delivery", "status + proof"), ("tracking", "TrackingEvent", "live location log")]},
    {"id": "wallet-ts", "language": "typescript",
     "goal": "digital wallet with wallets, transactions, transfers, cards, and statements",
     "intro": "Fintech wallet: balance tracking, categorized transactions, peer transfers with idempotency, virtual cards, monthly statements. TypeScript src/ layering.",
     "features": [("wallets", "Wallet", "balances + currencies"), ("transactions", "Transaction", "ledger + categories"), ("transfers", "Transfer", "peer + idempotency"), ("cards", "Card", "virtual + limits"), ("statements", "Statement", "monthly export")]},
    {"id": "subsaas-python", "language": "python",
     "goal": "subscription platform with customers, plans, subscriptions, payments, and dunning",
     "intro": "SaaS subscriptions: customer lifecycle, plan changes, recurring billing, failed-payment dunning workflow. FastAPI with routers → services → repositories → models.",
     "features": [("customers", "Customer", "accounts + contact"), ("plans", "Plan", "tiers + prices"), ("subscriptions", "Subscription", "states + upgrades"), ("payments", "Payment", "recurring + retries"), ("dunning", "DunningCycle", "failed-payment recovery")]},
    {"id": "eventbook-python", "language": "python",
     "goal": "event booking platform with events, tickets, orders, attendees, and seat maps",
     "intro": "Ticketing: event catalog, ticket types, order checkout with seat selection, attendee check-in. FastAPI with routers → services → repositories → models.",
     "features": [("events", "Event", "catalog + schedules"), ("tickets", "TicketType", "pricing + inventory"), ("orders", "Order", "checkout + status"), ("attendees", "Attendee", "registrations + check-in"), ("seats", "SeatMap", "sections + holds")]},
    {"id": "smarthome-python", "language": "python",
     "goal": "smart home hub with devices, rooms, scenes, automations, and event logs",
     "intro": "Home automation: device registry per protocol, room grouping, scene activation, rule-based automations, event audit log. FastAPI with routers → services → repositories → models.",
     "features": [("devices", "Device", "registry + state"), ("rooms", "Room", "grouping + layout"), ("scenes", "Scene", "one-tap presets"), ("automations", "Automation", "trigger + actions"), ("logs", "EventLog", "audit trail")]},
    {"id": "fieldservice-python", "language": "python",
     "goal": "field service dispatch with technicians, work orders, schedules, inventory, and invoices",
     "intro": "Service dispatch: technician roster, work-order lifecycle, schedule assignment, parts inventory, invoicing after completion. FastAPI with routers → services → repositories → models.",
     "features": [("technicians", "Technician", "roster + skills"), ("workorders", "WorkOrder", "lifecycle + priority"), ("schedules", "Schedule", "assignment + conflicts"), ("inventory", "InventoryItem", "parts + stock"), ("invoices", "Invoice", "billing after service")]},
    {"id": "payment-csharp", "language": "csharp",
     "goal": "payment processing system with accounts, payments, settlements, disputes, and reporting",
     "intro": "Fintech core: merchant accounts, payment lifecycle, settlement batches, dispute handling, regulatory reporting. .NET solution layering (Api → Application → Domain → Infrastructure).",
     "features": [("accounts", "MerchantAccount", "onboarding + balances"), ("payments", "Payment", "auth + capture"), ("settlements", "SettlementBatch", "batch + transfer"), ("disputes", "Dispute", "case + evidence"), ("reports", "Report", "regulatory queries")]},
    {"id": "teams-msg-csharp", "language": "csharp",
     "goal": "enterprise messaging with teams, channels, messages, mentions, and search",
     "intro": "Workplace messaging: team/channel hierarchy, message history, @mentions with notifications, full-text search. .NET solution layering.",
     "features": [("teams", "Team", "org + membership"), ("channels", "Channel", "topics + posts"), ("messages", "Message", "send + edit + delete"), ("mentions", "Mention", "notifications + digests"), ("search", "SearchIndex", "full-text queries")]},
    {"id": "membership-csharp", "language": "csharp",
     "goal": "membership management with members, plans, renewals, benefits, and billing",
     "intro": "Gym/club membership: member records, tiered plans, renewal cycles, benefit entitlements, billing runs. .NET solution layering (Api → Application → Domain → Infrastructure).",
     "features": [("members", "Member", "records + status"), ("plans", "Plan", "tiers + pricing"), ("renewals", "Renewal", "cycles + reminders"), ("benefits", "Benefit", "entitlements + usage"), ("billing", "BillingRun", "charges + receipts")]},
    {"id": "iot-csharp", "language": "csharp",
     "goal": "industrial IoT monitoring with sensors, readings, thresholds, alerts, and dashboards",
     "intro": "Industrial telemetry: sensor registry, high-frequency readings, threshold rules, alert dispatch, live dashboards. .NET solution layering with an ingestion service.",
     "features": [("sensors", "Sensor", "registry + calibration"), ("readings", "Reading", "high-freq ingestion"), ("thresholds", "ThresholdRule", "limits + windows"), ("alerts", "Alert", "dispatch + ack"), ("dashboards", "Dashboard", "charts + widgets")]},
]

# Render all specs at module load so a broken spec fails loudly at import time.
GENERATED_BLUEPRINTS = [build_blueprint(spec) for spec in BLUEPRINT_SPECS]


def build_examples():
    out = []
    out.append(make(
        "Design the complete file architecture for an e-commerce platform with user accounts, product catalog, cart, checkout, and orders. Plan every file with exports and uses contracts.",
        ECOMMERCE,
        "large-program-examples → ecommerce-go",
    ))
    out.append(make(
        "Design the complete file architecture for a SaaS analytics dashboard with projects, event ingestion, metrics, user management, and API tokens. Plan every file with exports and uses contracts.",
        ANALYTICS,
        "large-program-examples → analytics-ts",
    ))
    out.append(make(
        "Design the complete file architecture for a multi-tenant CMS with content types, drafts, publishing workflow, media uploads, and roles. Plan every file with exports and uses contracts.",
        CMS,
        "large-program-examples → cms-python",
    ))
    out.append(make(
        "Design the complete file architecture for a social network with user profiles, posts, comments, likes, follows, a personalized feed, and notifications. Plan every file with exports and uses contracts.",
        SOCIAL,
        "large-program-examples → social-ts",
    ))
    out.append(make(
        "Design the complete file architecture for a banking backend with accounts, transfers, a double-entry ledger, statements, and audit logging. Plan every file with exports and uses contracts.",
        BANKING,
        "large-program-examples → banking-csharp",
    ))
    out.append(make(
        "Design the complete file architecture for a realtime chat platform with WebSocket connections, rooms, direct messages, presence, and history. Plan every file with exports and uses contracts.",
        CHAT,
        "large-program-examples → chat-go",
    ))
    out.append(make(
        "Design the complete file architecture for a gaming platform with user profiles, matchmaking, ranked matches, leaderboards, and tournaments. Plan every file with exports and uses contracts.",
        GAMING,
        "large-program-examples → gaming-ts",
    ))
    # ── 16 spec-driven blueprints (4 per language, valid by construction) ──
    for i, spec in enumerate(BLUEPRINT_SPECS):
        out.append(make(
            f"Design the complete file architecture for the {spec['goal']}. Plan every file with exports and uses contracts.",
            GENERATED_BLUEPRINTS[i],
            f"large-program-examples → {spec['id']}",
        ))
    # Compact rules-of-thumb examples that transfer the scale mindset. These are
    # prose (no JSON), so the small cap is fine — they never approach it.
    out.append(make(
        "When should a program be planned as 25+ files instead of 8?",
        "A program is LARGE (25+ files) when it has 3+ distinct features (accounts, catalog, checkout), multi-user access, persistence with multiple entities, or any payments/realtime/uploads. Large programs decompose by FEATURE: each feature gets models + repository + service (+ handlers) + test files, plus shared layers (entry, config, models, middleware, UI, README, build config). One file = one responsibility. Never plan a 1500-line monolith file.",
        "large-program-examples → scale-decision",
    ))
    out.append(make(
        "How should dependencies flow in a large multi-file program so it compiles?",
        "Dependencies flow ONE way: ui/handlers → services → repository → models/types. Config is imported by everything and imports nothing app-specific. Handlers never import repository directly. Models import nothing. Never create import cycles — if A imports B and B imports A, merge the files or move the shared type into models. This ordering lets the generator write files in dependency order (models first, main last) so every import target exists when the importer is written.",
        "large-program-examples → dependency-direction",
    ))
    out.append(make(
        "What per-file contracts keep a 40-file generated program compiling?",
        "Every planned file declares its public API surface: exports (every function/class/type/constant the file defines) and uses (which members it imports from which OTHER planned file). Generated code must honor the contracts — never reference a member the target file doesn't export. This is the #1 compile failure in large builds. Rule of thumb: 3–10 exports and 0–8 uses per file; if a file needs 15+ uses it is doing too much — split it.",
        "large-program-examples → file-contracts",
    ))
    out.append(make(
        "How should a 40-file program be generated so it never truncates?",
        "Generate in dependency-ordered chunks: order files so imports come first (models → repository → services → handlers → main), write 3–6 files per chunk, compile-check the accumulated set, feed errors back as a repair round, and repeat. Each round only writes ITS files — never re-emit earlier files, never reference a file not yet written. A 40-file program is written in 8–12 rounds.",
        "large-program-examples → chunked-generation",
    ))
    return out


def main():
    dry_run = "--dry-run" in sys.argv
    new = build_examples()

    # Dedupe
    seen, deduped = set(), []
    for ex in new:
        key = (ex["instruction"], ex["output"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ex)
    new = deduped

    print("=== Large-Program Training Examples ===")
    print(f"  New examples: {len(new)}")
    for ex in new:
        print(f"    {ex['source']}: {ex['instruction'][:70]}")

    DS_DIR.mkdir(parents=True, exist_ok=True)
    NEW_OUT.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in new) + "\n", encoding="utf-8")
    print(f"  Wrote {NEW_OUT.relative_to(ROOT)}")

    if dry_run:
        print("  (dry run — no merge)")
        return

    # ─── Merge into train/val/test (same policy as build-vaca-knowledge-dataset.py) ───
    existing = []
    for name in ("train", "val", "test"):
        f = DS_DIR / f"{name}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip():
                    existing.append(json.loads(line))
    print(f"  Existing pool: {len(existing)} examples")

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

    # Backup
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
