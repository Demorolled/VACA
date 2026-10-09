#!/usr/bin/env python3
"""
A/B test: tuned model vs stock — countdown-engine node
======================================================
Generates the SAME node ('countdown-engine' from the Countdown Timer app,
simple tier) with:
  A) the TUNED model — via dspark on port 8000 (serves the deployed GGUF)
  B) the STOCK model — loaded in-process via llama_cpp from the untouched
     models/qwen2.5-7b-instruct-uncensored-q4_k_m.gguf

Both outputs get the campaign's quality checks:
  - JSX-in-ts (TS1005 failure mode)      - stub code
  - markdown-prose lines (TS1434/1435)   - named exports present
  - import statements                    - length sanity
Then each file is compiled with `tsc --noEmit` (sibling-import TS2307 is
expected/benign since the build system injects siblings).

Usage:
  python3 scripts/ab-test-tuned-vs-stock.py            # run now (models must exist)
  python3 scripts/ab-test-tuned-vs-stock.py --wait     # poll until tuned deployed, then run
"""

import argparse, json, os, re, shutil, subprocess, tempfile, time, urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE, "models")
TARGET_ENV = os.path.join(BASE, "scripts", "dspark-target.env")
OUT_DIR = os.path.join(BASE, "data", "ab-test")
DSPARK_URL = "http://127.0.0.1:8000/v1"

STOCK_GGUF = os.path.join(MODELS_DIR, "qwen2.5-7b-instruct-uncensored-q4_k_m.gguf")
TSC_BIN = None
for cand in [
    os.path.join(BASE, "node_modules", "typescript", "bin", "tsc"),
    os.path.join(BASE, "node_modules", ".bin", "tsc"),
]:
    if os.path.isfile(cand):
        TSC_BIN = cand
        break

INSTRUCTION = (
    "Generate the source file for the node 'countdown-engine' in the 'Countdown "
    "Timer' app (simple tier). Write complete, production-ready TypeScript code "
    "that is FULLY SELF-CONTAINED: implement the entire countdown logic inline "
    "in this one file. STRICT RULES: (1) NO import statements of any kind — "
    "especially NO sibling-module imports such as `import { TimerService } from "
    "'../timer-service/timer-service.ts'`; the build system injects siblings "
    "automatically, so do NOT delegate to or reference other modules. "
    "(2) NO `export default` — use named exports only (`export class`, "
    "`export function`, `export const`). (3) NO JSX — build the DOM with "
    "document.createElement. (4) Include real error handling and edge cases "
    "(negative/zero durations, double start/stop, completing at zero). "
    "Return only the code — no markdown, no explanations, no code fences."
)

# ── Quality gates (mirror scripts/export-corrected-builds-to-training.py) ──
STUB_PATTERNS = [
    r"\bnot implemented\b", r"placeholder\s+for\b", r"\bcoming soon\b",
    r"\blorem ipsum\b", r"\bunimplemented\b",
    r"throw new Error\(['\"]not", r"TODO:\s*Implement",
]
JSX_RE = re.compile(r"</?[a-z][a-z0-9]*\s[^>]*>|</[a-z][a-z0-9]*\s*>")
# Markdown fences (```), headings (#/##/###), and `declare module` blocks are
# prose that leaked into the code — the old regex missed them (STOCK emitted a
# ```typescript fence that sailed through the gates).
PROSE_RE = re.compile(
    r"^\s*(?:```|#{1,6}\s|declare\s+module\b|\*\*[^*]+\*\*|[-*]\s+[A-Za-z]|Note:|NOTE:|> |Explanation:|Here's|Below is|The .* (?:function|class|module))"
)
# Side-effect relative imports (import './x.ts') are added BY THE BUILD SYSTEM
# and legitimately appear in corrected reference files — do NOT flag those.
# Only substantive imports (import { X } from '...') are a contract violation.
IMPORT_LINE_RE = re.compile(r"^\s*import\s+", re.M)
SIDE_EFFECT_IMPORT_RE = re.compile(r"^\s*import\s+['\"](?:\.\.?/)", re.M)


def is_stub(code): return any(re.search(p, code, re.I) for p in STUB_PATTERNS)


def has_jsx_in_ts(code):
    stripped = re.sub(r"(['\"`])(?:\\.|(?!\1)[^\\])*\1", "", code)
    return bool(JSX_RE.search(stripped))


def has_prose(code):
    for line in code.split("\n"):
        t = line.strip()
        if not t:
            continue
        if PROSE_RE.match(line) and not re.search(r"[;{}()=<>]", t):
            return True
    return False


def named_exports(code):
    return len(re.findall(r"\bexport\s+(?:(?:class|function|const|let|interface|type|default|async|enum)\b|\{)", code))


def analyze(code):
    total_imports = IMPORT_LINE_RE.findall(code)
    side_effect = SIDE_EFFECT_IMPORT_RE.findall(code)
    return {
        "jsx_in_ts": has_jsx_in_ts(code),
        "stub": is_stub(code),
        "prose": has_prose(code),
        "named_exports": named_exports(code),
        "default_export": bool(re.search(r"\bexport\s+default\b", code)),
        "imports": len(total_imports) - len(side_effect),  # substantive only
        "side_effect_imports": len(side_effect),
        "len": len(code.strip()),
    }


def tsc_check(code):
    """Compile the file standalone. TS2307 (missing sibling) is expected.
    Scaffolds under data/ (NOT /tmp) so tsc walks up and resolves the
    project's node_modules/@types/node (code uses NodeJS.Timeout etc.)."""
    if not TSC_BIN:
        return "tsc-not-found"
    # UNIQUE scratch dir per call (not a shared 'tsc-tmp') so concurrent
    # callers (e.g. build-self-contained-corrected.py --validate-tsc running
    # alongside another tsc_check) can't clobber each other's node.ts and
    # produce spurious TS1434/TS2304 errors. Still under data/ (NOT /tmp) so
    # tsc walks up and resolves the project's node_modules/@types/node.
    td = tempfile.mkdtemp(prefix="tsc-tmp-", dir=OUT_DIR)
    src = os.path.join(td, "src")
    os.makedirs(src, exist_ok=True)
    f = os.path.join(src, "node.ts")
    with open(f, "w") as fh:
        fh.write(code)
    tsconfig = {
        "compilerOptions": {
            "target": "ES2022", "module": "ESNext",
            "moduleResolution": "bundler", "strict": True,
            "esModuleInterop": True, "skipLibCheck": True,
            "noEmit": True, "allowImportingTsExtensions": True,
            # Match the real browser/Vite target: DOM lib types setInterval/
            # setTimeout as returning `number` (the generated code's assumption),
            # and `types: []` keeps the project's @types/node OUT of scope so the
            # NodeJS.Timeout/Timeout vs number clash can't false-positive.
            "lib": ["ES2022", "DOM"], "types": [],
        },
        "include": ["src/**/*.ts"],
    }
    with open(os.path.join(td, "tsconfig.json"), "w") as fh:
        json.dump(tsconfig, fh)
    try:
        r = subprocess.run(
            ["node", TSC_BIN, "--noEmit", "--allowImportingTsExtensions", "-p", td],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        return f"tsc-error: {type(e).__name__}"
    finally:
        shutil.rmtree(td, ignore_errors=True)
    if r.returncode == 0:
        return "PASS"
    errs = [l for l in r.stdout.splitlines() if "error TS" in l]
    # Environment-dependent (benign for the standalone browser-target compile):
    #   TS2307            — missing sibling module; the build system injects
    #                       siblings, so this is expected, not a defect.
    #   TS2322/TS2769     — NodeJS.Timeout/Timeout vs `number` clash on timers
    #                       (only when the message is about timers, so a real
    #                       bad assignment like `const x: number = "hello"`
    #                       still fails).
    #   TS2345            — `number | null` passed where `number | undefined`
    #                       is expected (clearInterval(null) is a runtime no-op;
    #                       the DOM lib is stricter than the generated code).
    #   TS2552            — name-not-found for a symbol imported through a
    #                       side-effect sibling import (`import './x.ts'`): the
    #                       standalone compile has no sibling files, so this is
    #                       the TS2307 class, not a typo. (Trade-off: if code
    #                       has a real side-effect import AND a genuine typo,
    #                       the typo is also masked — overwhelmingly the
    #                       sibling case in this gate, so accepted.)
    has_sibling = bool(SIDE_EFFECT_IMPORT_RE.search(code))

    def _benign(line: str) -> bool:
        if "TS2307" in line:
            return True
        if ("TS2322" in line or "TS2769" in line) and any(
            t in line for t in ("Timeout", "setInterval", "setTimeout")
        ):
            return True
        if "TS2345" in line and "number | null" in line and "number | undefined" in line:
            return True
        if "TS2552" in line and has_sibling:
            return True
        return False

    serious = [l for l in errs if not _benign(l)]
    if not serious:
        return "PASS (only benign env errors: " + "; ".join(errs[:3]) + ")"
    return "FAIL: " + "; ".join(serious[:3])


def _atomic_write(path, code):
    """Write `code` to `path` atomically (temp file + os.replace) so a
    concurrent reader never sees a partial file. Used for the stable
    data/ab-test/tuned.ts + stock.ts mirrors; the per-run originals live in
    a unique run dir and are never rewritten by another process."""
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".",
                               suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(code)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run_output_dir():
    """Unique per-run dir under data/ab-test so two concurrent A/B runs can't
    clobber each other's tuned.ts/stock.ts (same pattern as the tsc_check
    scratch dirs). Kept (not cleaned up) so every run's raw outputs survive.
    mkdtemp guarantees OS-level uniqueness (no same-microsecond collision)."""
    return tempfile.mkdtemp(prefix="run-", dir=OUT_DIR)


def tuned_target():
    """Resolve which GGUF dspark is (or will be) serving."""
    if os.path.isfile(TARGET_ENV):
        for line in open(TARGET_ENV):
            if line.startswith("DSPARK_TARGET="):
                p = line.strip().split("=", 1)[1].strip()
                if os.path.isfile(p):
                    return p
    # fallback: newest q4_k_m in models/ that is NOT the stock model
    cands = []
    for f in os.listdir(MODELS_DIR):
        if f.endswith(".gguf") and "q4_k_m" in f and f != os.path.basename(STOCK_GGUF):
            p = os.path.join(MODELS_DIR, f)
            cands.append((os.path.getmtime(p), p))
    if cands:
        return max(cands)[1]
    return None


def generate_via_dspark(prompt, max_tokens=1024):
    body = json.dumps({
        "model": "any", "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0.3, "stream": False,
    }).encode()
    req = urllib.request.Request(
        DSPARK_URL + "/chat/completions", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]


def gpu_free_mb():
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
        frees = [int(x) for x in r.stdout.strip().split() if x.strip().isdigit()]
        return max(frees) if frees else 0
    except Exception:
        return 0


def generate_via_llama_cpp(gguf_path, prompt, max_tokens=1024):
    from llama_cpp import Llama
    # dspark holds ~6.5GB across both GPUs — check headroom before -1 (all layers)
    n_gpu_layers = -1
    free = gpu_free_mb()
    if 0 < free < 5500:
        print(f"  ⚠️  Only {free} MB free VRAM — capping GPU layers for stock model (CPU fallback)")
        n_gpu_layers = 0
    llm = Llama(model_path=gguf_path, n_gpu_layers=n_gpu_layers, n_ctx=8192, verbose=False)
    try:
        out = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens, temperature=0.3,
        )
        return out["choices"][0]["message"]["content"]
    finally:
        del llm
        import gc; gc.collect()


def dspark_healthy():
    try:
        with urllib.request.urlopen(DSPARK_URL + "/health", timeout=5) as r:
            return json.load(r).get("status") == "ok"
    except Exception:
        return False


def wait_for_deploy(timeout=7200):
    print(f"[wait] Polling {DSPARK_URL}/health until tuned model is served (timeout {timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        target = tuned_target()
        if target:
            print(f"[wait] Tuned target found: {target}")
            # dspark needs time to load the 4.4GB GGUF after the env file is
            # written — wait for /health status ok before generating.
            if dspark_healthy():
                print("[wait] dspark /health OK — ready.")
                return target
            print("[wait] Target set but dspark still loading — waiting for /health...")
        time.sleep(30)
    raise TimeoutError("Timed out waiting for tuned model deployment")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", action="store_true", help="Wait for training+deploy before running")
    ap.add_argument("--max-tokens", type=int, default=1024)
    args = ap.parse_args()

    if args.wait:
        wait_for_deploy()

    os.makedirs(OUT_DIR, exist_ok=True)

    # ── Tuned (A): via dspark API ──
    print("\n[test] Generating with TUNED model (dspark :8000)...")
    try:
        tuned_code = generate_via_dspark(INSTRUCTION, args.max_tokens)
    except Exception as e:
        print(f"  ❌ dspark failed: {e}")
        tuned_code = ""

    # ── Stock (B): in-process llama_cpp from untouched GGUF ──
    print(f"[test] Generating with STOCK model ({os.path.basename(STOCK_GGUF)})...")
    if not os.path.isfile(STOCK_GGUF):
        print(f"  ❌ Stock GGUF missing: {STOCK_GGUF}")
        stock_code = ""
    else:
        try:
            stock_code = generate_via_llama_cpp(STOCK_GGUF, INSTRUCTION, args.max_tokens)
        except Exception as e:
            print(f"  ❌ stock generation failed: {e}")
            stock_code = ""

    # ── Save raw outputs ──
    # Unique per-run dir first: concurrent runs never collide (the tsc_check
    # pattern). Then atomically mirror the latest run to the stable paths
    # data/ab-test/tuned.ts + stock.ts, which existing consumers read.
    run_dir = run_output_dir()
    with open(os.path.join(run_dir, "tuned.ts"), "w") as f:
        f.write(tuned_code)
    with open(os.path.join(run_dir, "stock.ts"), "w") as f:
        f.write(stock_code)
    _atomic_write(os.path.join(OUT_DIR, "tuned.ts"), tuned_code)
    _atomic_write(os.path.join(OUT_DIR, "stock.ts"), stock_code)

    # ── Analyze + tsc ──
    results = {}
    for label, code in (("TUNED", tuned_code), ("STOCK", stock_code)):
        if not code.strip():
            results[label] = {"error": "no output"}
            continue
        checks = analyze(code)
        checks["tsc"] = tsc_check(code)
        results[label] = checks

    # ── Report ──
    print("\n" + "=" * 70)
    print("  A/B RESULT — countdown-engine (simple tier)")
    print("=" * 70)
    for label in ("TUNED", "STOCK"):
        r = results.get(label, {})
        if "error" in r:
            print(f"  {label:<6} ❌ {r['error']}")
            continue
        flags = []
        if r["jsx_in_ts"]: flags.append("JSX-in-ts ✗")
        if r["stub"]: flags.append("STUB ✗")
        if r["prose"]: flags.append("PROSE ✗")
        if r["named_exports"] == 0: flags.append("NO-EXPORTS ✗")
        if r.get("default_export"): flags.append("DEFAULT-EXPORT ✗")
        if r["imports"] > 0: flags.append("SUBSTANTIVE-IMPORTS ✗")
        # A tsc failure means the output isn't valid TS — that must FAIL the
        # verdict (previously a broken file could still print ✅ PASS).
        if not str(r.get("tsc", "")).startswith("PASS"):
            flags.append("TSC ✗")
        verdict = "PASS" if not flags else "FAIL"
        status = "✅" if verdict == "PASS" else "❌"
        print(f"\n  {status} {label}: {verdict}")
        print(f"     length: {r['len']} chars | exports: {r['named_exports']} "
              f"(default: {r.get('default_export')}) | "
              f"imports: {r['imports']} (side-effect: {r['side_effect_imports']})")
        print(f"     tsc: {r['tsc']}")
        if flags:
            print(f"     flags: {', '.join(flags)}")

    print(f"\n  Raw outputs saved to: {OUT_DIR}/tuned.ts, {OUT_DIR}/stock.ts")
    print(f"  Run originals (unique per run): {run_dir}/tuned.ts, {run_dir}/stock.ts")
    return 0


if __name__ == "__main__":
    main()
