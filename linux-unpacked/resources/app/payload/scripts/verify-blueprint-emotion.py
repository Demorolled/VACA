#!/usr/bin/env python3
"""Live verification of the two remaining improvements:
(1) blueprint edge referential integrity (no dangling edges)
(2) emotion continuity (turn 2 warm AND references turn 1)
"""
import json, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:3001"

def api(method, path, body=None, timeout=180):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode()[:200]}
    except Exception as e:
        return -1, {"error": str(e)[:200]}

def chat(q, mt=400, t=120):
    _, d = api("POST", "/api/reason/chat",
               {"messages": [{"role": "user", "content": q}], "maxTokens": mt}, timeout=t)
    return (d.get("response") or "") if isinstance(d, dict) else ""

print("=" * 70)
print("LIVE VERIFY — blueprint integrity + emotion continuity")
print("=" * 70)

# ── 1. Blueprint referential integrity (real /api/blueprint/build pipeline) ──
print("\n[1] Blueprint — wiring_graph resolves into checklist; edges reference real node ids")
st, d = api("POST", "/api/blueprint/build",
            {"goal": "a fitness tracker app with workouts and goals"}, timeout=180)
if isinstance(d, dict) and d.get("blueprint") and d.get("project"):
    bp, proj = d["blueprint"], d["project"]
    known = set(str(m).strip() for m in (bp.get("architecture_checklist") or []))
    wg = bp.get("wiring_graph") or []
    node_ids = set(n.get("id") for n in (proj.get("nodes") or []))
    proj_edges = proj.get("edges") or []
    dangle_mod = [w for w in wg
                  if str(w.get("source_module") or "").strip() not in known
                  or str(w.get("destination_module") or "").strip() not in known]
    dangle_edge = [ed for ed in proj_edges
                   if ed.get("source") not in node_ids or ed.get("target") not in node_ids]
    ok = len(known) >= 3 and len(wg) >= 2 and not dangle_mod and not dangle_edge
    print(f"  checklist={len(known)} wiring={len(wg)} dangleMod={len(dangle_mod)} "
          f"nodes={len(node_ids)} edges={len(proj_edges)} dangleEdge={len(dangle_edge)}")
    print(f"  {'PASS — no dangling edges' if ok else 'FAIL — dangling edges found'}")
else:
    print("  FAIL — /api/blueprint/build error:", (d or {}).get("error", str(d)[:120]))

# (3) soul.json emotional_state freshness — the /chat route must record each
# reading (analyzeEmotion → recordEmotionHistory). A moved last_updated proves
# the emotion machinery runs inside the chat path, not just on /api/emotion/*.
def read_emotion_state():
    try:
        with open("data/soul.json") as f:
            s = json.load(f).get("emotional_state", {})
        h = s.get("history") or []
        return s.get("last_updated", ""), (h[-1].get("trigger", "") if h else "")
    except Exception:
        return "", ""

lu_before, tr_before = read_emotion_state()

# ── 2. Emotion continuity ──
# Realistic multi-turn chat: the frontend sends the FULL history (user1,
# assistant1, user2) in one /chat call, so the model sees turn 1. The probe
# must do the same — two independent single-message calls could never show
# continuity even if the backend carried the context.
print("\n[2] Emotion — turn 1 warm AND turn 2 warm + references turn 1 (multi-turn)")
_, d1 = api("POST", "/api/reason/chat",
            {"messages": [{"role": "user", "content": "I'm really stressed about my deadline tomorrow, everything is going wrong"}],
             "maxTokens": 250})
r1 = (d1.get("response") or "") if isinstance(d1, dict) else ""
w1 = any(w in r1.lower() for w in ["sorry", "understand", "breath", "stuck", "help", "one thing at a time", "we'll", "together", "awful", "rough", "here for", "stress", "tackle", "one by one", "support", "empath"])
_, d2 = api("POST", "/api/reason/chat",
            {"messages": [
                {"role": "user", "content": "I'm really stressed about my deadline tomorrow, everything is going wrong"},
                {"role": "assistant", "content": r1},
                {"role": "user", "content": "and now it got even worse — my laptop just died and I lost my work"},
            ], "maxTokens": 250})
r2 = (d2.get("response") or "") if isinstance(d2, dict) else ""
w2 = any(w in r2.lower() for w in ["sorry", "understand", "awful", "rough", "hard", "help", "breathe", "we'll", "together", "devastat", "frustrat", "let's"])
# Continuity = the model references turn 1's OWN fact ("deadline") or uses a
# genuine connector showing it remembers prior context (earlier/mentioned/
# on top). Deliberately NOT "laptop"/"work" (the user's own turn-2 words),
# NOT filler ("that's"/"still"), and NOT generic words that appear in any
# advice reply ("first" in "Backup First", "already"/"before" in tips).
# "stress" matches both "stressed" (turn 1's own state) and "stressful" —
# the model echoing the stress emotion IS a turn-1 tie-back. "on top of"
# (with "of") avoids advice phrasings like "get back on top".
cont = any(w in r2.lower() for w in ["deadline", "earlier", "mentioned", "on top of", "stress"])
print(f"  turn1 warm={w1} | turn2 warm={w2} | continuity={cont}")
print(f"  {'PASS — continuity holds' if (w1 and w2 and cont) else 'partial'}")
print(f"  turn2[:200]: {r2[:200]}")

# (3) freshness verdict: the /chat calls above must have moved soul.json's
# emotional_state.last_updated (throttled to dominant-change or 10s gap).
lu_after, tr_after = read_emotion_state()
fresh = bool(lu_after) and lu_after != lu_before
# Stronger than a bare mtime: the last recorded trigger should be one of THIS
# probe's own chat messages — proving an emotion write, not just any write.
probe_trigger = ("stressed about my deadline" in tr_after
                 or "my laptop just died" in tr_after)
print(f"  soul freshness: last_updated {lu_before or 'none'} → {lu_after or 'none'} | last trigger: {tr_after[:60]!r}")
print(f"  {'PASS — emotion recorded in chat path' if (fresh and probe_trigger) else 'FAIL — soul.json did not move (recordEmotionHistory not running?)'}")

print("\nDONE")
