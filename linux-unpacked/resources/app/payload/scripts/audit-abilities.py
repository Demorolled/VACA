#!/usr/bin/env python3
"""Snapshot VACA's stated abilities for the capability audit."""
import json, os

root = "/home/final-flash1/Desktop/visual-ai-architect"
print("=" * 60)
print("STATED ABILITIES — soul.json identity")
print("=" * 60)
soul = json.load(open(os.path.join(root, "data/soul.json")))
ident = soul.get("identity", {})
print("name:", ident.get("name"))
print("role:", ident.get("role"))
print("description:", ident.get("description", "")[:500])
print("purpose:", ident.get("purpose"))
caps = ident.get("capabilities") or []
print("\nCAPABILITIES (%d):" % len(caps))
for c in caps:
    print("  -", c)
langs = ident.get("languages") or []
print("\nLANGUAGES:", langs)

print("\n" + "=" * 60)
print("WIKI — modelVeronice.txt (first 80 lines)")
print("=" * 60)
try:
    with open(os.path.join(root, "modelVeronice.txt")) as f:
        print("\n".join(f.readlines()[:80]))
except Exception as e:
    print("ERR", e)

print("\n" + "=" * 60)
print("README.md (first 120 lines)")
print("=" * 60)
try:
    with open(os.path.join(root, "README.md")) as f:
        print("\n".join(f.readlines()[:120]))
except Exception as e:
    print("ERR", e)
