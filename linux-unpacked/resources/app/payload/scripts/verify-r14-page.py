#!/usr/bin/env python3
"""Verify probes/r14-3d/index.html DATA matches results.json, then check serving."""
import json
import re
import subprocess

ROOT = "visual-ai-architect" if __import__("os").path.isdir("visual-ai-architect") else "."

res = {r["name"]: r for r in json.load(open(f"{ROOT}/probes/r14-3d/results.json"))}
html = open(f"{ROOT}/probes/r14-3d/index.html").read()

names_in_page = re.findall(r'"name":"([a-z-]+)"', html)
print("page entries:", len(names_in_page), "| json apps:", len(res))

mismatch = []
for n in names_in_page:
    if n not in res:
        mismatch.append(f"{n}: not in results.json")
for n, r in res.items():
    if n not in names_in_page:
        mismatch.append(f"{n}: missing from page")
    else:
        raw_ok = "true" if r["raw_pass"] else "false"
        rep_ok = "true" if r["repaired_pass"] else "false"
        if f'"raw":{raw_ok}' not in html or f'"rep":{rep_ok}' not in html:
            mismatch.append(f"{n}: gate flags wrong (raw={raw_ok} rep={rep_ok})")

if mismatch:
    print("❌ MISMATCHES:")
    for m in mismatch:
        print("  ", m)
else:
    print("✅ page DATA matches results.json")

# serve check
r = subprocess.run(
    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:8124/index.html"],
    capture_output=True, text=True, timeout=10)
print("HTTP", r.stdout, "for http://127.0.0.1:8124/index.html")
