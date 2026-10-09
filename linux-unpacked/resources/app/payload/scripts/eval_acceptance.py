#!/usr/bin/env python3
"""
eval_acceptance.py — the second gate: does the model produce a file that parses
and exports what the task declared?
=============================================================================
Companion to eval_adapters.py. Same task file, same prompt, same temp 0 / seed 42
generation, but the score is not difflib similarity against gold — it is:

    passed = (0 local TypeScript errors) AND (every declared export present)

Why both gates are needed
-------------------------
The similarity metric has saturated: base 0.3814, and nogrpo / nogrpo2 / curated
all land 0.6659-0.6861 with code_like 7/7. It cannot separate a file that
compiles from one that merely resembles the gold. It is also only 7 tasks, two
of which score identically every run. This gate runs over the whole corpus
(a corpus/tasks file) and asks a question the model is actually for.

Non-code tasks (css/html) are generated but excluded from the denominator, since
"expected exports" is meaningless for them.

Usage:
  python3 scripts/eval_acceptance.py \
      --tasks corpora/vaca/tasks.txt \
      --model nogrpo=vaca-r40-off-nogrpo-adapter:latest \
      --model distill=vaca-r40-off-distill-adapter:latest \
      --baseline distill --out runs/acceptance-x200c.json
"""
import argparse
import concurrent.futures as futures
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

URL = "http://192.168.1.234:11434/api/generate"
PROMPT_PREFIX = "Recreate this file. Output the file content only.\n\n"
CODE_EXTS = {"ts", "tsx", "js", "jsx", "mjs", "cjs"}
ID_RE = re.compile(r"\bid=([A-Za-z0-9_.-]+)")
FILE_RE = re.compile(r"\bfile=(\S+)")
LANG_RE = re.compile(r"\blang=(\S+)")
EXPECT_RE = re.compile(r"expected exports:\s*([^|]+)")
PLAN_RE = re.compile(r"app plan:\s*([^|]+)")
PLAN_FILE_RE = re.compile(
    r"([A-Za-z0-9_./-]+\.(?:tsx?|jsx?|mjs|cjs|html|css|json|ya?ml|md|txt|py|go|rs|sh|vue|svelte))\b")
HERE = Path(__file__).resolve().parent

def parse_task(line: str):
    m = ID_RE.search(line)
    if not m:
        return None
    f = FILE_RE.search(line)
    l = LANG_RE.search(line)
    e = EXPECT_RE.search(line)
    expects = []
    if e:
        v = e.group(1).strip()
        if "none declared" not in v:
            expects = [x.strip() for x in v.split(",") if x.strip()]
    file = f.group(1) if f else ""
    ext = file.rsplit(".", 1)[-1].lower() if "." in file else ""
    plan = PLAN_RE.search(line)
    siblings = sorted({p.split("/")[-1] for p in PLAN_FILE_RE.findall(plan.group(1))}) \
        if plan else []
    return {
        "id": m.group(1),
        "file": file,
        "lang": (l.group(1) if l else ""),
        "expects": expects,
        "ext": ext,
        "siblings": siblings,
        "applicable": ext in CODE_EXTS,
    }


def gen(model: str, prompt: str, num_predict: int, num_ctx: int,
        system: str | None = None, url: str = URL) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "seed": 42,
                    "num_predict": num_predict, "num_ctx": num_ctx},
        "keep_alive": "10m",
    }
    if system:
        payload["system"] = system
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read())["response"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(HERE.parent / "corpora" / "vaca" / "tasks.txt"))
    ap.add_argument("--model", action="append", required=True, metavar="NAME=TAG")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--num-predict", type=int, default=1200)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--max-tasks", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--api", default=URL)
    ap.add_argument("--ts-dir", default=str(HERE.parent / "node_modules" / "typescript"))
    ap.add_argument("--exports-dir", default=str(HERE.parent / "backend" / "exports"),
                    help="app role: gold export dirs the generated file is staged into")
    ap.add_argument("--recheck", action="store_true",
                    help="score the SAVED batch-<name>.json in --workdir with the current "
                         "checker instead of regenerating — use after a checker change so a "
                         "gate fix costs seconds, not a 12-minute run")
    ap.add_argument("--workdir", default=None, help="where to stage generated text")
    ap.add_argument("--role", choices=["completion", "app", "adherence"], default="completion",
                    help="completion = does the file parse + export in isolation (default); "
                         "app = stage the file into its real gold export dir and typecheck the "
                         "whole app (the only mode that can see cross-file consistency); "
                         "adherence = does the file RESPECT VACA's scaffold contract "
                         "(named exports, self-contained, imports only from the app plan, "
                         "no phantom packages / prose / JSX-in-ts / stubs)")
    args = ap.parse_args()

    tasks = [parse_task(l) for l in Path(args.tasks).expanduser().read_text().splitlines() if l.strip()]
    tasks = [t for t in tasks if t]
    if args.max_tasks:
        tasks = tasks[:args.max_tasks]
    lines = [l for l in Path(args.tasks).expanduser().read_text().splitlines() if l.strip()][:len(tasks)]

    models = []
    for m in args.model:
        if "=" not in m:
            print(f"[acc] ABORT: --model needs NAME=TAG, got {m!r}")
            return 1
        models.append(tuple(m.split("=", 1)))
    names = [n for n, _ in models]
    if args.baseline and args.baseline not in names:
        print(f"[acc] ABORT: --baseline {args.baseline!r} not in {names}")
        return 1

    workdir = Path(args.workdir).expanduser() if args.workdir else Path("/tmp/vaca-acceptance")
    workdir.mkdir(parents=True, exist_ok=True)
    n_app = sum(1 for t in tasks if t["applicable"])
    print(f"[acc] role={args.role} tasks={len(tasks)} ({n_app} applicable, "
          f"{len(tasks) - n_app} n/a) models={[f'{n}={t}' for n, t in models]}")
    print(f"[acc] num_predict={args.num_predict} num_ctx={args.num_ctx} temp=0 seed=42 workers={args.workers}")

    summary: dict[str, dict] = {}
    per_task: dict[str, dict] = {}
    checker_mode = "app" if args.role == "app" else ("adherence" if args.role == "adherence" else "code")

    def generate_batch(name: str, tag: str) -> list[dict]:
        batch = []

        def run(i_t):
            i, t = i_t
            prompt, sysmsg = PROMPT_PREFIX + lines[i][:3000], None
            try:
                return i, t, gen(tag, prompt, args.num_predict, args.num_ctx, sysmsg, args.api), None
            except Exception as e:  # noqa: BLE001
                return i, t, "", f"{type(e).__name__}: {e}"

        with futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            for i, t, text, err in ex.map(run, list(enumerate(tasks))):
                if err:
                    print(f"[acc] {name} {t['id']}: generate failed ({err})")
                batch.append({"id": t["id"], "file": t["file"], "lang": t["lang"],
                              "expects": t["expects"], "siblings": t.get("siblings", []),
                              # app mode stages the file into its real export dir, so the
                              # checker needs the slug (the id's prefix) to find it.
                              "slug": t["id"].split("__", 1)[0], "text": text})
                print(f"[acc] {name:>10} {t['id']:<16} {t['file'][:40]:<42} len={len(text)}")
        return batch

    def score_batch(name: str, tag: str, batch: list[dict], elapsed: float) -> None:
        bpath = workdir / f"batch-{name}.json"
        rpath = workdir / f"results-{name}.json"
        if not args.recheck:
            bpath.write_text(json.dumps(batch))
        cmd = ["node", str(HERE / "acceptance_check.mjs"),
               "--in", str(bpath), "--out", str(rpath),
               "--ts-dir", args.ts_dir, "--mode", checker_mode]
        if args.role == "app":
            cmd += ["--exports-dir", str(args.exports_dir)]
        rc = subprocess.run(cmd, capture_output=True, text=True)
        if rc.returncode != 0:
            raise RuntimeError(f"node checker rc={rc.returncode}: {rc.stderr.strip()[:400]}")
        print(rc.stdout.strip())
        res = json.loads(rpath.read_text())["results"]

        # ── adherence role: a graded score + a per-check failure mix ──
        # The pass/fail gate answers "compiles + exports"; this answers "did the
        # model follow the harness". Reported as a mean 0-1 score over the seven
        # contract checks, plus the count of fully-adherent files and the most
        # common failures — the mix is what tells you which part of the contract
        # the model ignores.
        if args.role == "adherence":
            scores, full, check_fail = [], 0, {}
            for t in tasks:
                r = res.get(t["id"], {})
                checks = r.get("checks", {}) or {}
                entry = {
                    "score": r.get("score"), "adherent": bool(r.get("harness_adherent")),
                    "checks": checks, "applicable": t["applicable"],
                    "missing": r.get("exports_missing", []),
                    "phantom": r.get("phantom_imports", []),
                    "bad_imports": r.get("bad_relative_imports", []),
                }
                per_task.setdefault(name, {})[t["id"]] = entry
                if not t["applicable"]:
                    continue
                if isinstance(r.get("score"), (int, float)):
                    scores.append(r["score"])
                if r.get("harness_adherent"):
                    full += 1
                for k, v in checks.items():
                    if not v:
                        check_fail[k] = check_fail.get(k, 0) + 1
            mean = round(sum(scores) / len(scores), 4) if scores else None
            summary[name] = {
                "tag": tag, "role": args.role, "n_applicable": n_app,
                "mean_score": mean, "fully_adherent": full,
                "pass_rate": mean,  # comparable field for the summary/delta print
                "check_failures": dict(sorted(check_fail.items(), key=lambda kv: -kv[1])),
                "elapsed_s": round(elapsed, 1),
            }
            print(f"[acc] {name}: adherence mean={mean}  fully_adherent={full}/{n_app}"
                  f"  worst_checks={list(summary[name]['check_failures'])[:3]}")
            return

        n_pass = n_parse = n_exp = 0
        for t in tasks:
            r = res.get(t["id"], {})
            entry = {
                "passed": bool(r.get("passed")), "applicable": t["applicable"],
                "n_errors": r.get("n_errors"), "missing": r.get("exports_missing", []),
                "errors": r.get("errors", [])[:2],
            }
            per_task.setdefault(name, {})[t["id"]] = entry
            if not t["applicable"]:
                continue
            n_parse += 1 if r.get("n_errors") == 0 else 0
            n_exp += 1 if r.get("ok_exports") else 0
            n_pass += 1 if r.get("passed") else 0

        summary[name] = {
            "tag": tag, "role": args.role, "n_applicable": n_app, "passed": n_pass,
            "parse_ok": n_parse, "exports_ok": n_exp,
            "pass_rate": round(n_pass / n_app, 4) if n_app else None,
            "elapsed_s": round(elapsed, 1),
        }
        print(f"[acc] {name}: passed {n_pass}/{n_app}  parse_ok {n_parse}/{n_app}  exports_ok {n_exp}/{n_app}")

    for name, tag in models:
        t0 = time.time()
        if args.recheck:
            bpath = workdir / f"batch-{name}.json"
            if not bpath.exists():
                print(f"[acc] ABORT: --recheck needs a saved batch at {bpath}")
                return 1
            batch = json.loads(bpath.read_text())
            if len(batch) != len(tasks):
                print(f"[acc] ABORT: {bpath.name} holds {len(batch)} items "
                      f"but this task list has {len(tasks)}")
                return 1
            print(f"[acc] --recheck: scoring {bpath.name} with the CURRENT checker "
                  f"(no generation)")
        else:
            batch = generate_batch(name, tag)
        try:
            score_batch(name, tag, batch, time.time() - t0)
        except RuntimeError as e:
            print(f"[acc] FATAL {e}")
            return 1

    print("\n[acc] ================ SUMMARY ================")
    base_rate = summary[args.baseline]["pass_rate"] if args.baseline else None
    for name in names:
        s = summary[name]
        d = "" if base_rate is None else f"  delta_vs_{args.baseline}={s['pass_rate'] - base_rate:+.4f}"
        if args.role == "adherence":
            print(f"[acc] {name:<12} adherence={s['mean_score']} "
                  f"({s['fully_adherent']}/{s['n_applicable']} fully adherent)"
                  f"  ({s['elapsed_s']}s){d}")
            for k, v in list(s.get("check_failures", {}).items())[:7]:
                print(f"[acc]     ✗ {k:<22} failed on {v}/{s['n_applicable']}")
            continue
        print(f"[acc] {name:<12} pass_rate={s['pass_rate']:.4f} ({s['passed']}/{s['n_applicable']})"
              f"  parse_ok={s['parse_ok']}/{s['n_applicable']}"
              f"  exports_ok={s['exports_ok']}/{s['n_applicable']}"
              f"  ({s['elapsed_s']}s){d}")

    if args.out:
        outp = Path(args.out).expanduser()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps({
            "tasks_file": str(args.tasks), "n_tasks": len(tasks), "role": args.role,
            "n_applicable": n_app, "baseline": args.baseline,
            "num_predict": args.num_predict, "num_ctx": args.num_ctx,
            "summary": summary, "per_task": per_task,
        }, indent=2) + "\n")
        print(f"[acc] wrote {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
