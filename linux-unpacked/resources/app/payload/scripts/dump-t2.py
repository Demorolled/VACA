#!/usr/bin/env python3
"""Dump the full turn-2 replies (with the few-shot block live) so continuity
can be judged by eye, not just by keyword gate."""
import json, urllib.request

BASE = "http://127.0.0.1:3001"
W2 = ["sorry", "understand", "awful", "rough", "hard", "help", "breathe", "we'll", "together", "devastat", "frustrat", "let's"]
CONT = ["deadline", "earlier", "mentioned", "on top of", "stress"]

def chat(msgs, mt=250, t=120):
    req = urllib.request.Request(BASE + "/api/reason/chat",
                                 data=json.dumps({"messages": msgs, "maxTokens": mt}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.loads(r.read().decode()).get("response") or ""

import sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
for n in range(N):
    r1 = chat([{"role": "user", "content": "I'm really stressed about my deadline tomorrow, everything is going wrong"}])
    r2 = chat([
        {"role": "user", "content": "I'm really stressed about my deadline tomorrow, everything is going wrong"},
        {"role": "assistant", "content": r1},
        {"role": "user", "content": "and now it got even worse — my laptop just died and I lost my work"},
    ])
    warm2 = any(w in r2.lower() for w in W2)
    cont = any(w in r2.lower() for w in CONT)
    print("=== sample %d: warm2=%s keywordCont=%s" % (n + 1, warm2, cont))
    print(r2.strip()[:350])
    print()
