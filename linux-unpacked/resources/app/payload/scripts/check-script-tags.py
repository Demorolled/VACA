#!/usr/bin/env python3
"""Check whether the DOM-ready wrap in repair-gui.py drops closing </script> tags."""
import re
import sys
from pathlib import Path

root = Path("/home/final-flash1/Desktop/visual-ai-architect/probes/r15-gui")
if len(sys.argv) > 1:
    targets = [Path(sys.argv[1])]
else:
    targets = sorted(root.glob("*-repaired.html"))

for p in targets:
    raw_p = p.with_name(p.name.replace("-repaired", ""))
    if not raw_p.exists():
        continue
    raw = raw_p.read_text(encoding="utf-8")
    rep = p.read_text(encoding="utf-8")

    def count_close(html):
        # count real </script> closers (not ones inside JS strings — approximate)
        return len(re.findall(r"</script>", html, re.IGNORECASE))

    def count_open(html):
        return len(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.IGNORECASE)) + \
               len(re.findall(r"<script\b[^>]*\bsrc=[^>]*>", html, re.IGNORECASE))

    rc, ro = count_close(raw), count_open(raw)
    dc, do = count_close(rep), count_open(rep)
    status = "OK" if (do == dc and dc >= ro) else "❌ UNBALANCED"
    print(f"{p.name:42s} raw open={ro} close={rc} | rep open={do} close={dc}  {status}")
