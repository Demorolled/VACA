#!/usr/bin/env python3
"""Test retry variants WITHOUT mentioning forbidden tokens, on two questions."""
import json, urllib.request

BASE = "http://127.0.0.1:3001/api/reason/chat"

QUESTIONS = {
    "debug": "Can you help me debug my Express server that returns 500 on POST /api/users? What should I check first?",
    "knowledge": "What does the knowledge base say about round-6 training or blueprint fidelity targets?",
}

VARIANTS = {
    "chat-role": (
        "You are a friendly AI assistant having a casual conversation with a developer. "
        "Talk to them like a colleague helping with a problem. Answer naturally in plain prose. "
        "Do not output any data structures, machine-readable formats, or bracket notation."
    ),
    "convo-only": (
        "This is a normal conversation. Reply exactly the way you would in an everyday chat: "
        "natural sentences, no formatting tricks, no structured output of any kind."
    ),
    "friend-coder": (
        "You're a senior engineer chatting with a friend over coffee. Answer their question conversationally "
        "in plain sentences. Keep it helpful and human. No machines should be able to parse your reply."
    ),
}

def chat(system, msg, max_tokens=500):
    body = {"messages": [{"role": "user", "content": msg}], "maxTokens": max_tokens, "system": system}
    req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=200) as r:
        return json.load(r).get("response", "")

for qname, q in QUESTIONS.items():
    print("=" * 66)
    print("QUESTION:", qname, "->", q[:60])
    for name, sys_p in VARIANTS.items():
        try:
            out = chat(sys_p, q)
            is_json = out.strip().startswith("{") and "app_type" in out[:300]
            print(f"  {name:14} JSON={is_json} | {out[:110].replace(chr(10),' ')}")
        except Exception as e:
            print(f"  {name:14} ERROR {e}")
    print()
