# 🔄 CI/CD Configuration

> Ready-to-use CI/CD pipeline templates for generated applications.
> Covers GitHub Actions, testing, building, and releasing.

---

## 1. CI/CD Principles

For generated applications, CI/CD pipelines should be:

1. **Fast** — run in under 5 minutes for a push
2. **Deterministic** — same code always produces same result
3. **Thorough** — typecheck, lint, test, build, security scan
4. **Triggered** — on push to any branch, on PR, on tag

### Pipeline Stages

```
Push/PR
  │
  ▼
┌──────────────┐
│  1. Lint     │  ← Format check, lint, typecheck
└──────┬───────┘
       ▼
┌──────────────┐
│  2. Test     │  ← Unit + integration tests
└──────┬───────┘
       ▼
┌──────────────┐
│  3. Build    │  ← Compile, bundle, package
└──────┬───────┘
       ▼
┌──────────────┐
│  4. Security │  ← Dependency audit, SAST scan
└──────┬───────┘
       ▼
┌──────────────┐
│  5. Release  │  ← (on tag only) Publish artifacts
└──────────────┘
```

---

## 2. GitHub Actions Workflows

### 2.1 TypeScript Project

**.github/workflows/ci.yml:**
```yaml
name: CI

on:
  push:
    branches: [main, develop]
    paths-ignore:
      - '**.md'
      - '.gitignore'
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality:
    name: Quality Checks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
          cache-dependency-path: '**/package-lock.json'

      - name: Install dependencies
        run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      - name: Lint
        run: npx eslint src/

      - name: Check formatting
        run: npx prettier --check src/

  test:
    name: Tests
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run unit tests
        run: npx vitest run

      - name: Run integration tests
        run: npx vitest run --config vitest.integration.config.ts

      - name: Upload coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: coverage/

  build:
    name: Build
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build

      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: build
          path: dist/

  security:
    name: Security Scan
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Audit dependencies
        run: npx audit-ci --moderate

      - name: SAST scan
        uses: github/codeql-action/analyze@v3
        with:
          languages: javascript-typescript
```

### 2.2 Go Project

**.github/workflows/ci.yml:**
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality:
    name: Quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
          cache: true

      - name: Lint
        uses: golangci/golangci-lint-action@v4
        with:
          version: latest

      - name: Vet
        run: go vet ./...

  test:
    name: Tests
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
          cache: true

      - name: Run unit tests
        run: go test -v -short -count=1 -race ./...

      - name: Run integration tests
        run: go test -v -count=1 -tags=integration ./...

  build:
    name: Build
    needs: test
    strategy:
      matrix:
        goos: [linux, darwin]
        goarch: [amd64, arm64]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'
          cache: true

      - name: Build
        env:
          GOOS: ${{ matrix.goos }}
          GOARCH: ${{ matrix.goarch }}
        run: |
          mkdir -p dist
          go build -ldflags="-s -w" -o dist/app_${{ matrix.goos }}_${{ matrix.goarch }} ./cmd/app

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: build-${{ matrix.goos }}-${{ matrix.goarch }}
          path: dist/
```

### 2.3 Python Project

**.github/workflows/ci.yml:**
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality:
    name: Quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-dev.txt

      - name: Type check
        run: mypy src/

      - name: Lint
        run: ruff check src/

      - name: Format check
        run: ruff format --check src/

  test:
    name: Tests
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

---

## 3. Release Workflow

### 3.1 Semantic Versioning

```
v1.2.3
├── major: breaking changes
│  ├── minor: new features (backward compatible)
│  │  └── patch: bug fixes (backward compatible)
```

**Trigger:** Pushing a tag `v*` triggers the release pipeline.

### 3.2 Release Pipeline

**.github/workflows/release.yml:**
```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  test:
    uses: ./.github/workflows/ci.yml  # Reuse CI

  release:
    name: Create Release
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: '1.22'

      - name: Build all platforms
        run: |
          mkdir -p dist
          for os in linux darwin; do
            for arch in amd64 arm64; do
              GOOS=$os GOARCH=$arch go build -ldflags="-s -w" \
                -o dist/app_${os}_${arch} ./cmd/app
            done
          done

      - name: Build .deb package
        run: make deb VERSION=${GITHUB_REF_NAME#v}

      - name: Generate checksums
        run: |
          cd dist
          sha256sum * > checksums.txt

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          name: Release ${{ github.ref_name }}
          body_path: CHANGELOG.md
          files: |
            dist/*
            build/deb/*.deb
```

---

## 4. Pre-commit Hooks

### .pre-commit-config.yaml

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
      - id: detect-private-key

  # TypeScript
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.56.0
    hooks:
      - id: eslint
        types: [file]
        files: \.(ts|tsx)$
        args: ['--fix']

  # Go
  - repo: https://github.com/TekWizely/pre-commit-golang
    rev: v1.0.0-rc.1
    hooks:
      - id: go-fmt
      - id: go-vet

  # Python
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

---

## 5. CI/CD Configuration Templates

### 5.1 TypeScript Package.json Scripts

```json
{
  "scripts": {
    "lint": "eslint src/",
    "lint:fix": "eslint src/ --fix",
    "format": "prettier --check src/",
    "format:fix": "prettier --write src/",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage",
    "build": "tsup src/index.ts --minify",
    "audit": "npm audit --audit-level=moderate",
    "ci": "npm run typecheck && npm run lint && npm run format && npm run test && npm run build"
  }
}
```

### 5.2 Makefile Targets (for Go projects)

```makefile
.PHONY: all lint vet test build clean ci

all: build

lint:
	golangci-lint run ./...

vet:
	go vet ./...

test:
	go test -v -short -count=1 -race ./...

test-integration:
	go test -v -count=1 -tags=integration ./...

build:
	go build -ldflags="-s -w" -o bin/app ./cmd/app

clean:
	rm -rf bin/ dist/

ci: lint vet test test-integration build
```

### 5.3 Python requirements-dev.txt

```txt
# Development dependencies
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=5.0
mypy>=1.8
ruff>=0.3.0
pre-commit>=3.6
```

---

## 6. CI/CD Checklist

- [ ] CI runs on push to `main` and on PRs
- [ ] Type checking passes (no errors)
- [ ] Linting passes (no warnings)
- [ ] All tests pass (unit + integration)
- [ ] Build succeeds
- [ ] Security audit passes (no critical vulnerabilities)
- [ ] Coverage is uploaded and visible
- [ ] Pre-commit hooks are configured
- [ ] Release workflow creates GitHub releases with artifacts
- [ ] Docker/container build not required (prefer binaries)

---

*For deeper CI/CD concepts, see `bible-reference/12-devops/`, `bible-reference/33-devops-sre-tooling/`, and `bible-reference/30-software-process/`.*
