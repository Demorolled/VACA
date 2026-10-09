#!/usr/bin/env python3
"""probe-tuneup.py — ask the LLM to optimize a node, print the RAW reply."""
import sys, json, urllib.request
sys.path.insert(0, "scripts" if "scripts" not in sys.path[0] else sys.path[0])
import puzzle_trainer as pt

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8002/v1/chat/completions"
lib = pt.Library(pt.EXPORTS_DIR)
app = next(iter(lib.apps))
node = [n for n in lib.apps[app]["nodes"] if n["purpose"] == "state" or True][0]
puzzle = lib.make_puzzle(app, node, __import__("random").Random(3))
msgs = pt.build_tuneup_messages(puzzle)
reply = pt.llm_chat(url, "qwen2.5-coder-14b-uncensored-dspark", msgs,
                    max_tokens=700, temperature=0.5)
print("=== RAW REPLY ===")
print(reply)
print("=== PARSED ===", pt.parse_tuneup(reply))