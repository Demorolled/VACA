#!/usr/bin/env python3
"""Round 2: tool-phrasing probes + endpoint/claim checks against live VACA."""
import json, urllib.request, urllib.error

BASE = "http://127.0.0.1:3001"

def post(path, body, timeout=180):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:300]}

def get(path, timeout=20):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": "%d %s" % (e.code, e.reason)}

def chat(msg, max_tokens=500, system=None):
    body = {"messages": [{"role": "user", "content": msg}]}
    if max_tokens: body["maxTokens"] = max_tokens
    if system: body["system"] = system
    return post("/api/reason/chat", body)

print("── Tool phrasing probes ──")
r = chat("search the code for baseURL")
print("search_file:", "tool=" + str(r.get("tool")) if r.get("toolUsed") else "NOT_TRIGGERED",
      "|", r.get("response", r.get("error"))[:220].replace("\n", " "))

r = chat("read backend/src/ai/translator.ts")
print("read_file:", "tool=" + str(r.get("tool")) if r.get("toolUsed") else "NOT_TRIGGERED",
      "|", r.get("response", r.get("error"))[:220].replace("\n", " "))

r = chat("what do you know about React")
print("knowledge_query:", "tool=" + str(r.get("tool")) if r.get("toolUsed") else "NOT_TRIGGERED",
      "|", r.get("response", r.get("error"))[:220].replace("\n", " "))

r = chat("search the web for llama.cpp q4_k_m quantization")
print("web_search:", "tool=" + str(r.get("tool")) if r.get("toolUsed") else "NOT_TRIGGERED",
      "|", r.get("response", r.get("error"))[:220].replace("\n", " "))

print("\n── Non-blueprint hijack probe ──")
r = chat("Can you help me debug my Express server that returns 500 on POST /api/users? What should I check first?", 400)
print("debug Q:", (r.get("response", r.get("error")) or "")[:300].replace("\n", " "))
print("is_blueprint:", '"app_type"' in (r.get("response") or ""))

print("\n── Claimed-capability endpoints ──")
for path in ["/api/tts", "/api/projects", "/api/emotion", "/api/llm/config", "/api/neural",
             "/api/architect", "/api/generate", "/api/soul", "/api/knowledge"]:
    d = get(path)
    ok = "error" not in d
    print(("%-20s %s" % (path, "OK" if ok else "ERR: " + str(d.get("error"))[:80])))

print("\n── Shell command claim (soul says 'run any CLI command') ──")
r = chat("Run the shell command ls -la and tell me the output")
print("shell:", r.get("declined", False) and "declined" or "not-declined",
      "|", (r.get("response", r.get("error")) or "")[:200].replace("\n", " "))
