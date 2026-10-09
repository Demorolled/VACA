#!/usr/bin/env python3
"""Deep quality probe for the claims the shallow audit scores at 8/10.
Each test is harder than the audit's: it measures QUALITY, not just existence.
"""
import json, sys, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:3001"

def api(method, path, body=None, timeout=120):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return time.time() - t0, r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return time.time() - t0, e.code, {"error": e.read().decode()[:200]}
    except Exception as e:
        return time.time() - t0, -1, {"error": str(e)[:200]}

def chat(q, mt=400, t=120):
    _, st, d = api("POST", "/api/reason/chat",
                   {"messages": [{"role": "user", "content": q}], "maxTokens": mt},
                   timeout=t)
    resp = (d.get("response") or "") if isinstance(d, dict) else ""
    return st, resp

print("=" * 70)
print("QUALITY PROBE ROUND 6 — beyond the shallow audit")
print("=" * 70)

# ── 1. Memory recall QUALITY: write 3 distinct facts, then ask for all 3 ──
print("\n[1] Memory recall — write 3 facts, ask to list all")
chat("remember that my favorite color is teal", mt=120)
chat("remember that my dog's name is Biscuit", mt=120)
chat("remember that I prefer dark mode", mt=120)
time.sleep(1)
_, r = chat("List ALL the things you remember about me (color, dog, mode). "
            "Answer with each one on its own line.", mt=300)
recalled = sum(1 for w in ["teal", "biscuit", "dark"] if w.lower() in r.lower())
print(f"  recalled {recalled}/3 facts | resp[:300]: {r[:300]}")

# ── 2. Codegen QUALITY: does the chat write real, compilable code? ──
print("\n[2] Codegen quality — chat-level fibonacci with memoization")
_, r2 = chat("write a complete Python function fibonacci with memoization, "
             "including a dictionary cache and a test call", mt=500)
has_def = "def fibonacci" in r2
has_cache = ("cache" in r2 or "memo" in r2)
has_recursion = "fibonacci" in r2 and ("n-1" in r2 or "n - 1" in r2 or "n - 2" in r2)
print(f"  def={has_def} cache={has_cache} recursion={has_recursion}")
print(f"  resp[:250]: {r2[:250]}")

# ── 3. Blueprint QUALITY: JSON parse + node/edge sanity ──
print("\n[3] Blueprint quality — todo app blueprint must be valid + complete")
_, r3 = chat("generate a blueprint for a todo list app as JSON with "
             "app_type, nodes, and edges fields", mt=700)
bp_ok = False
bp_detail = ""
try:
    start = r3.index("{")
    end = r3.rindex("}") + 1
    bp = json.loads(r3[start:end])
    nodes = bp.get("nodes") or []
    edges = bp.get("edges") or []
    bp_ok = bp.get("app_type") and len(nodes) >= 3 and len(edges) >= 2
    bp_detail = f"app_type={bp.get('app_type')} nodes={len(nodes)} edges={len(edges)}"
except Exception as e:
    bp_detail = f"parse error: {str(e)[:100]}"
print(f"  valid+complete={bp_ok} | {bp_detail}")

# ── 4. Emotion depth: multi-turn empathy + follow-up ──
print("\n[4] Emotion depth — stressed message then 'it got worse'")
_, r4 = chat("I'm really stressed about my deadline tomorrow, everything is going wrong", mt=250)
warm1 = any(w in r4.lower() for w in ["sorry", "understand", "breath", "stuck", "help", "one thing at a time"])
_, r5 = chat("and now it got even worse, my laptop died", mt=250)
warm2 = any(w in r5.lower() for w in ["sorry", "understand", "awful", "that's hard", "help", "breathe", "we'll", "together"])
print(f"  first reply warm={warm1} | follow-up warm={warm2}")
print(f"  follow-up resp[:200]: {r5[:200]}")

# ── 5. Self-analysis: read + summarize own code (not just echo) ──
print("\n[5] Self-analysis — read soulService and explain the WHAT/WHY")
_, r6 = chat("read backend/src/services/soulService.ts and explain what "
             "getSoulPromptModifier does and WHY it matters", mt=400)
analysis = any(w in r6.lower() for w in ["personality", "trait", "warmth", "modifier", "prompt"])
print(f"  explains purpose={analysis} | resp[:250]: {r6[:250]}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  1. memory recall: {recalled}/3")
print(f"  2. codegen: def={has_def} cache={has_cache} recursion={has_recursion}")
print(f"  3. blueprint: {'OK' if bp_ok else 'WEAK'} ({bp_detail})")
print(f"  4. emotion: first={warm1} followup={warm2}")
print(f"  5. self-analysis: {'OK' if analysis else 'WEAK'}")
with open("data/quality-probe-round6.json", "w") as f:
    json.dump({"recalled": recalled, "codegen": {"def": has_def, "cache": has_cache,
               "recursion": has_recursion}, "blueprint_ok": bp_ok,
               "blueprint_detail": bp_detail, "emotion": {"first": warm1, "followup": warm2},
               "self_analysis_ok": analysis, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}, f, indent=1)
print("saved: data/quality-probe-round6.json")
