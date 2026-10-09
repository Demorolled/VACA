#!/usr/bin/env python3
"""Verify the three fixes against the live backend (:3001)."""
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

def chat(msg, max_tokens=500, system=None):
    body = {"messages": [{"role": "user", "content": msg}]}
    if max_tokens: body["maxTokens"] = max_tokens
    if system: body["system"] = system
    return post("/api/reason/chat", body)

def is_blueprint_json(text):
    t = (text or "").strip()
    if t.startswith("```"): t = t.split("```")[1] if "```" in t[3:] else t
    return t.strip().startswith("{") and '"app_type"' in t[:300]

print("═══ FIX #1: blueprint-JSON hijack guard ═══")
r = chat("Can you help me debug my Express server that returns 500 on POST /api/users? What should I check first?", 400)
resp = r.get("response", r.get("error")) or ""
print("debug Q -> blueprint JSON?", is_blueprint_json(resp))
print("  reply:", resp[:220].replace("\n", " "))
print()

r = chat("What does the knowledge base say about round-6 training or blueprint fidelity targets?", 400)
resp = r.get("response", r.get("error")) or ""
print("knowledge Q -> blueprint JSON?", is_blueprint_json(resp))
print("  reply:", resp[:220].replace("\n", " "))
print()

print("═══ FIX #1 regression: real blueprint requests must keep JSON ═══")
r = chat("Generate a blueprint for a pomodoro timer app. Return JSON with app_type, description, keywords, target_stack, architecture_checklist, wiring_graph.", 700)
resp = r.get("response", r.get("error")) or ""
print("blueprint Q -> has app_type JSON?", is_blueprint_json(resp), "| starts:", resp[:80].replace("\n", " "))
print()

print("═══ FIX #2: tool detector natural phrasing ═══")
r = chat("Search the backend code for how the LLM client base URL is configured", 400)
print("natural search -> tool:", r.get("toolUsed") and r.get("tool"), "| pattern used:", (r.get("toolDisplay") or "")[:60])
print("  reply:", (r.get("response", r.get("error")) or "")[:220].replace("\n", " "))
print()

r = chat("read backend/src/ai/translator.ts", 300)
print("read file -> tool:", r.get("toolUsed") and r.get("tool"))
print()

print("═══ FIX #4: warm soul ═══")
with urllib.request.urlopen(BASE + "/api/soul", timeout=8) as resp:
    soul = json.load(resp)["soul"]
t = soul["personality"]["traits"]
print("traits:", json.dumps({k: t.get(k) for k in ("warmth", "empathy", "sassiness", "verbosity", "formality")}))
print()

r = chat("Hi VACA! I'm exhausted after debugging my chess app all night. Can you help?", 300)
print("warmth probe:", (r.get("response", r.get("error")) or "")[:200].replace("\n", " "))
