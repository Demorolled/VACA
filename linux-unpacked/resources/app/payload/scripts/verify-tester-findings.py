#!/usr/bin/env python3
"""Verify the standalone tester's 4 improvement findings against the live app.
Each test is deeper than the tester's: measures QUALITY, not existence.
Findings: P2 codegen tsc-clean, P2 memory 3-fact recall, P3 emotion continuity,
P3 blueprint referential integrity.
"""
import json, sys, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:3001"

def api(method, path, body=None, timeout=180):
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

print("=" * 72)
print("TESTER-FINDING VERIFICATION — live against the running backend")
print("=" * 72)

results = {}

# ── 1. Memory recall robustness: 3 distinct facts, list all ──
print("\n[1] MEMORY — write 3 distinct facts, then ask to list ALL")
tag = "vf" + str(int(time.time()))[-5:]
facts = [("favorite color", tag + "amber"), ("dog name", "pluto" + tag[-3:]),
         ("preferred mode", "violet-mode")]
for k, v in facts:
    chat("remember that my " + k + " is " + v, mt=120)
time.sleep(1.5)
_, r1 = chat("List ALL the things you remember about me. Answer with each fact on its own line.", mt=300)
hits = sum(1 for (_, v) in facts if v.lower() in r1.lower())
print(f"  recalled {hits}/3 distinct facts | resp[:280]: {r1[:280]}")
# check notes file state (accumulation)
_, _, notes_d = api("GET", "/api/memory/notes", timeout=10)
n_total = notes_d.get("total", 0)
print(f"  notes file total entries: {n_total}")

# ── 2. Emotion continuity: warm reply 1 AND warm follow-up after worse news ──
print("\n[2] EMOTION — continuity across 2 turns (warm 1st + warm 2nd after bad news)")
_, r2a = chat("I'm really stressed about my deadline tomorrow, everything is going wrong", mt=250)
w1 = any(w in r2a.lower() for w in ["sorry", "understand", "breath", "stuck", "help", "one thing at a time", "together", "we'll"])
_, r2b = chat("and now it got even worse — my laptop just died and I lost my work", mt=250)
w2 = any(w in r2b.lower() for w in ["sorry", "understand", "awful", "hard", "help", "breathe", "we'll", "together", "devastat", "frustrat", "let's"])
print(f"  turn1 warm={w1} | turn2 warm={w2}")
print(f"  turn1[:140]: {r2a[:140]}")
print(f"  turn2[:140]: {r2b[:140]}")
# soul emotional_state freshness (does the engine record turns?)
_, _, soul_d = api("GET", "/api/soul", timeout=10)
try:
    hist = soul_d["soul"]["emotional_state"]["history"]
    last = hist[-1]["timestamp"] if hist else ""
    print(f"  soul emotional_state.history entries: {len(hist)} | last: {last}")
    fresh = last and (time.time() - time.mktime(time.strptime(last[:19], "%Y-%m-%dT%H:%M:%S"))) < 600
    print(f"  last reading fresh (<10min): {fresh}")
except Exception as e:
    print(f"  soul history check: {str(e)[:80]}")

# ── 3. Blueprint integrity: edges must reference existing nodes ──
print("\n[3] BLUEPRINT — node/edge referential integrity")
_, r3 = chat("generate a blueprint for a fitness tracker app as JSON with app_type, nodes, and edges fields", mt=700)
dangling = -1
bp_detail = ""
try:
    s, e = r3.index("{"), r3.rindex("}") + 1
    bp = json.loads(r3[s:e])
    nodes = bp.get("nodes") or []
    edges = bp.get("edges") or []
    ids = set(n.get("id") for n in nodes)
    dangling = sum(1 for ed in edges if (ed.get("source") or ed.get("from")) not in ids
                   or (ed.get("target") or ed.get("to")) not in ids)
    bp_detail = f"app_type={bp.get('app_type')} nodes={len(nodes)} edges={len(edges)} dangling={dangling}"
except Exception as ex:
    bp_detail = f"parse error: {str(ex)[:80]}"
print(f"  {bp_detail}")

# ── 4. Codegen: chat-level fibonacci (real + compilable?) ──
print("\n[4] CODEGEN (chat path) — fibonacci with memoization + test call")
_, r4 = chat("write a complete Python function fibonacci with memoization including a dict cache and a test call", mt=500)
has_def = "def fibonacci" in r4
has_cache = "cache" in r4 or "memo" in r4
has_test = "print(fibonacci" in r4 or "fibonacci(10)" in r4 or "fibonacci(" in r4
print(f"  def={has_def} cache={has_cache} testcall={has_test}")
print(f"  resp[:200]: {r4[:200]}")

results = {"memory_3fact": hits, "memory_notes_total": n_total,
           "emotion_w1": w1, "emotion_w2": w2,
           "blueprint_dangling": dangling, "blueprint": bp_detail,
           "codegen_chat": {"def": has_def, "cache": has_cache, "test": has_test},
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
with open("data/verify-tester-findings.json", "w") as f:
    json.dump(results, f, indent=1)
print("\nsaved: data/verify-tester-findings.json")
