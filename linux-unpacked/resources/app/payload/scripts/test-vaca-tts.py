#!/usr/bin/env python3
"""Smoke tests for vaca-tts.py: normalizer behavior + real synthesis."""
import asyncio
import os
import sys
import tempfile

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "vaca_tts", os.path.join(os.path.dirname(__file__), "vaca-tts.py"))
vt = importlib.util.module_from_spec(_spec)
sys.modules["vaca_tts"] = vt
_spec.loader.exec_module(vt)  # noqa: E402

print("=== 1. normalizer: code fences silenced ===")
out = vt.normalize_for_speech("Here is the plan:\n```js\nconst x = 1;\n```\nDone.")
assert "const" not in out and "x = 1" not in out, out
print("  OK ->", repr(out))

print("=== 2. normalizer: emoji expansion ===")
out = vt.normalize_for_speech("Great work! 🚀 ✅")
assert "rocket" in out and "check mark" in out, out
print("  OK ->", repr(out))

print("=== 3. normalizer: code-to-words reads code ===")
out = vt.normalize_for_speech("```python\nprint('hi')\n```", code_to_words=True)
assert "print" in out, out
print("  OK ->", repr(out))

print("=== 4. normalizer: operators become words ===")
out = vt.normalize_for_speech("if (a === b) return x => y")
assert "equals" in out and "becomes" in out, out
print("  OK ->", repr(out))

print("=== 5. real synthesis (edge-tts) ===")
fd, tmp = tempfile.mkstemp(suffix=".mp3")
os.close(fd)
ok = asyncio.run(vt.synth_edge("Hello from VACA, speaking through the terminal.",
                               "en-US-JennyNeural", "+0%", "+0%", "+0Hz", tmp))
size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
print(f"  synth ok={ok} size={size} bytes")
assert ok and size > 1024
os.unlink(tmp)

print("=== 6. piper fallback (writes wav sibling) ===")
fd, tmp2 = tempfile.mkstemp(suffix=".mp3")
os.close(fd)
ok2 = vt.synth_piper("Offline voice check.", tmp2)
wav2 = tmp2.rsplit(".", 1)[0] + ".wav"
size2 = os.path.getsize(wav2) if os.path.exists(wav2) else 0
print(f"  piper ok={ok2} wav_size={size2} bytes")
assert ok2 and size2 > 1024
for p in (tmp2, wav2):
    if os.path.exists(p):
        os.unlink(p)

print("\nALL TESTS PASSED")
