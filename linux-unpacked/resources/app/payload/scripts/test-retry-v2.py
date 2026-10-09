#!/usr/bin/env python3
"""Test retry variants via the real /chat route (matches guard's call shape)."""
import json, urllib.request

BASE = "http://127.0.0.1:3001/api/reason/chat"
MSG = "Can you help me debug my Express server that returns 500 on POST /api/users? What should I check first?"

def chat(system, max_tokens=600, temperature=None):
    body = {"messages": [{"role": "user", "content": MSG}], "maxTokens": max_tokens, "system": system}
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=200) as r:
        return json.load(r).get("response", "")

VARIANTS = {
    "rule-only-600": (
        "Reply to the user in plain conversational prose, like a friendly engineer pair-programming with them. "
        "STRICTLY FORBIDDEN: JSON objects, braces, app_type, target_stack, architecture_checklist, wiring_graph, "
        "code fences, or any structured output. Answer their question directly and naturally."
    ),
    "rule+mistake-note": (
        "The previous assistant reply was a JSON object with an app_type field — that was a mistake. "
        "The user is just chatting, NOT asking you to build an app or blueprint. "
        "Reply now in plain conversational prose. STRICTLY FORBIDDEN: JSON, app_type, braces, code fences, structured output."
    ),
    "roleplay-chat": (
        "You are having a casual conversation with the user. They are a developer asking for debugging help. "
        "Talk to them like a friend helping with code. Absolutely no JSON, no app_type, no blueprints, no structured formats."
    ),
}

for name, sys_p in VARIANTS.items():
    try:
        out = chat(sys_p)
        is_json = out.strip().startswith("{") and "app_type" in out[:300]
        print("=" * 60)
        print(f"{name}: JSON={is_json}")
        print(out[:250].replace("\n", " "))
    except Exception as e:
        print(f"{name}: ERROR {e}")
    print()
