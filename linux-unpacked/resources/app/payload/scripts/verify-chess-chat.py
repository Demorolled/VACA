#!/usr/bin/env python3
"""Replay the user's exact chess conversation against /api/reason/chat."""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:3001"
MSG1 = ("buikd me a chess game board and chess pieces. The chess game needs to be "
        "a stand alone not a web browser based build. Make the board and pieces "
        "look like there made of crystal")
MSG2 = "build it"


def chat(messages, label):
    req = urllib.request.Request(
        BASE + "/api/reason/chat",
        data=json.dumps({"messages": messages, "maxTokens": 2048}).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=240) as r:
        data = json.loads(r.read().decode())
    print("=== %s (%.1fs) ===" % (label, time.time() - t0))
    print(data.get("response", "")[:1500])
    print()
    return data.get("response", "")


if __name__ == "__main__":
    msgs = [{"role": "user", "content": MSG1}]
    r1 = chat(msgs, "msg1: build the chess game")
    msgs.append({"role": "assistant", "content": r1})
    msgs.append({"role": "user", "content": MSG2})
    r2 = chat(msgs, "msg2: build it")

    # Verdicts
    leaks = '{"' in r2 and 'app_type' in r2
    print("VERDICT truncated-JSON leak:", "YES (BAD)" if leaks else "no")
    native = any(k in r2.lower() for k in ("python", "pygame", "tkinter", "go", "rust", "electron", "native", "desktop"))
    webonly = ("react" in r2.lower() or "node" in r2.lower()) and not native
    print("VERDICT native stack steered:", "yes" if native else ("NO - web stack only" if webonly else "unclear"))
    sys.exit(1 if (leaks or webonly) else 0)
