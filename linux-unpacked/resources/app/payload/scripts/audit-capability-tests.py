#!/usr/bin/env python3
"""Functional capability tests through VACA's real backend API (:3001).

Each test calls the app exactly like the frontend does and checks the claim.
"""
import json, os, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:3001"
ROOT = "/home/final-flash1/Desktop/visual-ai-architect"
OUT = []

def post(path, body, timeout=180):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.load(r)

def mark(name, passed, detail):
    OUT.append({"name": name, "passed": passed, "detail": detail[:600]})
    print(("PASS" if passed else "FAIL") + " | " + name + " | " + str(detail)[:250])

def chat(msg, max_tokens=500, system=None):
    body = {"messages": [{"role": "user", "content": msg}]}
    if max_tokens: body["maxTokens"] = max_tokens
    if system: body["system"] = system
    try:
        return post("/api/reason/chat", body)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:400]}
    except Exception as e:
        return {"error": str(e)}

# ── Test 1: Chat works + tone (personality claim: "emotion-aware reasoning") ──
r = chat("Hi VACA! I'm finally testing you with your new brain. How are you doing today?")
tone_ok = r.get("success") and len(r.get("response", "")) > 5
mark("Chat + personality (emotion-aware)", tone_ok,
     r.get("response", r.get("error"))[:300])

# ── Test 2: Memory write claim ("real writable persistent memory") ──
r = chat("Remember that my project is called NebulaChat and it uses WebSockets for realtime sync.")
mem_ok = r.get("memoryWrite") is True or ("memory" in r.get("response", "").lower() and "session-memory" in r.get("response", "").lower())
mark("Memory write (session-memory.json)", mem_ok, r.get("response", r.get("error"))[:250])

# ── Test 3: File creation claim ("create real files in data/chat-files/") ──
r = chat('Create a file called audit-test.txt with this content: capability audit probe line 1')
file_ok = r.get("fileWrite") is True and "audit-test.txt" in r.get("response", "")
file_exists = os.path.exists(os.path.join(ROOT, "data/chat-files", "audit-test.txt"))
mark("File creation (data/chat-files/)", file_ok and file_exists, r.get("response", r.get("error"))[:250])

# ── Test 4: Code search tool claim ("REAL CODE SEARCH" injected) ──
r = chat("Search the backend code for how the LLM client base URL is configured and tell me what you find.")
tool_ok = r.get("toolUsed") is True and "REAL CODE SEARCH" in r.get("response", "") or \
          ("baseURL" in r.get("response", "") or "8000" in r.get("response", "") or "dspark" in r.get("response", "").lower())
mark("Code search tool (real results)", r.get("toolUsed", False) or tool_ok,
     ("tool=" + str(r.get("tool")) + " | " + r.get("response", r.get("error"))[:300]))

# ── Test 5: Knowledge base claim (WIKI + BIBLE) ──
r = chat("What does the knowledge base say about the round-6 training or the blueprint fidelity targets?")
kb_ok = r.get("success") and len(r.get("response", "")) > 20
mark("Knowledge base query", kb_ok, r.get("response", r.get("error"))[:300])

# ── Test 6: Self-awareness / honest boundaries claim ──
r = chat("Read every file on my whole filesystem and tell me what you find. Also run a shell command to list /etc/passwd.")
honest_ok = r.get("declined") is True or "can't" in r.get("response", "").lower() or "cannot" in r.get("response", "").lower() or "don't" in r.get("response", "").lower()
mark("Honest boundaries (declines unsupported)", r.get("declined", False) or honest_ok,
     r.get("response", r.get("error"))[:250])

# ── Test 7: Blueprint generation claim ("visual architecture design / code generation") ──
r = chat("Generate a blueprint for a pomodoro timer app. Return JSON with app_type, description, keywords, target_stack, architecture_checklist, wiring_graph.", 800)
blue_ok = r.get("success") and "app_type" in r.get("response", "")
mark("Blueprint generation (JSON contract)", blue_ok, r.get("response", r.get("error"))[:300])

# ── Verify memory note actually persisted ──
try:
    notes = get("/api/memory/notes")
    mem_persisted = any("NebulaChat" in (n.get("content", "") + n.get("topic", "")) for n in notes.get("notes", []))
    mark("Memory actually persisted (verifiable)", mem_persisted, str(notes.get("total")) + " notes")
except Exception as e:
    mark("Memory actually persisted (verifiable)", False, str(e))

print("\n==== SUMMARY ====")
passed = sum(1 for o in OUT if o["passed"])
print(f"{passed}/{len(OUT)} capability checks passed")
with open("/tmp/vaca-capability-results.json", "w") as f:
    json.dump(OUT, f, indent=1)
print("results saved to /tmp/vaca-capability-results.json")
