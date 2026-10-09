#!/usr/bin/env python3
"""Probe retry-prompt variants against the R6 model to break the blueprint-JSON habit."""
import json, urllib.request

DSPARK = "http://127.0.0.1:8000/v1/chat/completions"

USER_MSG = "Can you help me debug my Express server that returns 500 on POST /api/users? What should I check first?"

VARIANTS = {
    "short-force": (
        "You are a helpful assistant. Reply in plain conversational prose. "
        "STRICTLY FORBIDDEN: JSON objects, braces, app_type, target_stack, architecture_checklist, "
        "wiring_graph, markdown code fences. Write 2-4 natural sentences answering the user's question."
    ),
    "no-jargon": (
        "Reply to the user in plain English, like a friendly senior engineer pair-programming with them. "
        "Do not output JSON. Do not output any structured format. Do not use the word app_type. "
        "Just talk to them directly."
    ),
    "chat-role": (
        "You are VACA, a friendly AI assistant chatting with the user. IMPORTANT: the user is just chatting — "
        "they are NOT asking you to build an app or generate a blueprint. Answer their question conversationally. "
        "NEVER output JSON. NEVER output app_type. Never output a blueprint."
    ),
}

def chat(sys_prompt, msg):
    body = json.dumps({
        "model": "default",
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": msg},
        ],
        "max_tokens": 350,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(DSPARK, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["choices"][0]["message"]["content"]

for name, sys_p in VARIANTS.items():
    try:
        out = chat(sys_p, USER_MSG)
        is_json = out.strip().startswith("{") and '"app_type"' in out[:300]
        print("=" * 60)
        print("VARIANT:", name, "| STILL_JSON:", is_json)
        print(out[:300].replace("\n", " "))
        print()
    except Exception as e:
        print("VARIANT:", name, "ERROR:", e)
