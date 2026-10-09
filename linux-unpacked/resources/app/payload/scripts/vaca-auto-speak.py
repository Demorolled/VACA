#!/usr/bin/env python3
"""
vaca-auto-speak.py — speak the service assistant's responses automatically.

Tails the Freebuff chat transcript (`.config/manicode/projects/Desktop/
chats/*/chat-messages.json`) and, whenever the assistant finishes a
response, feeds the FINAL response text through VACA's TTS (scripts/
vaca-tts.py) so it plays on the speakers.

What gets spoken:
  - Only text blocks WITHOUT thinking keys (thinkingCollapseState/thinkingId)
    — i.e. the visible final response, not internal reasoning.
  - Agent/tool/ask-user blocks are skipped.
  - On first run, the existing history is seeded as "already spoken" so it
    only speaks NEW responses from that point on.

Controls:
  tmux kill-session -t vaca-speak    # stop
  touch /tmp/vaca-speak.pause        # pause (remove file to resume)
"""

import glob
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS = os.path.join(ROOT, "scripts", "vaca-tts.py")
CHATS_GLOB = os.path.expanduser(
    "~/.config/manicode/projects/*/chats/*/chat-messages.json")
STATE = os.path.join(ROOT, "scripts", ".vaca-speak-seen.json")

VOICE = "en-US-JennyNeural"
RATE = "+20%"
POLL = 2.0
SETTLE = 6.0       # speak only once a message hasn't grown for this long
PAUSE_FILE = "/tmp/vaca-speak.pause"


def newest_transcript() -> str:
    files = glob.glob(CHATS_GLOB)
    if not files:
        return ""
    return max(files, key=os.path.getmtime)


def load_state() -> set:
    try:
        return set(json.load(open(STATE, encoding="utf-8")))
    except Exception:
        return set()


def save_state(seen: set) -> None:
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)
    os.replace(tmp, STATE)


def extract_final_text(msgs: list) -> list:
    """Return the final-response text per AI message, in order.

    The final response is the LAST visible (non-thinking) text block of the
    message. Messages often end with tool/agent blocks after the written
    answer, so we take the last visible text block wherever it sits — never
    the intermediate progress notes ("Let me check X..."), which appear
    earlier in the block list.
    """
    out = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("variant") != "ai":
            continue
        parts = []
        for b in m.get("blocks", []):
            if not isinstance(b, dict) or b.get("type") != "text":
                continue
            if b.get("thinkingCollapseState") is not None \
                    or b.get("thinkingId") is not None:
                continue  # reasoning block, not the visible response
            c = (b.get("content") or "").strip()
            if c:
                parts.append(c)
        if not parts:
            continue
        joined = parts[-1]  # the final written answer
        if "[response interrupted]" in joined or "[error]" in joined:
            continue  # don't speak aborted/failed responses
        out.append((joined, m.get("id", "")))
    return out


def tts_python() -> str:
    """A python interpreter that can import edge_tts (VACA's neural voice).

    The daemons are started by GNOME autostart with `python3`, which on this
    box resolves to /usr/bin/python3.13 — and that interpreter has NO
    edge_tts installed, so vaca-tts.py silently falls back to piper
    (different voice, slower, rate ignored). Prefer the interpreter that
    actually has edge_tts.
    """
    import importlib.util
    for py in [sys.executable,
               "/home/final-flash1/miniconda3/bin/python3",
               "/home/final-flash1/miniconda3/bin/python"]:
        if not py or not os.path.exists(py):
            continue
        try:
            code = ("import importlib.util,sys;"
                    "sys.exit(0 if importlib.util.find_spec('edge_tts')"
                    " else 1)")
            r = subprocess.run([py, "-c", code], capture_output=True,
                               timeout=10)
            if r.returncode == 0:
                return py
        except Exception:
            continue
    return sys.executable


def speak(text: str) -> None:
    cmd = [tts_python(), TTS, "--voice", VOICE, "--rate", RATE]
    subprocess.run(cmd, input=text.encode(), timeout=600)


def main() -> None:
    seen = load_state()
    seeded = False
    # mid -> (block_count, last_changed)  for settle detection
    grow = {}
    print(f"[vaca-speak] watching transcripts {CHATS_GLOB}", flush=True)
    print(f"[vaca-speak] voice {VOICE} rate {RATE} | pause via "
          f"touch {PAUSE_FILE}", flush=True)

    while True:
        try:
            path = newest_transcript()
            if not path:
                time.sleep(POLL)
                continue
            msgs = json.load(open(path, encoding="utf-8"))
        except Exception:
            time.sleep(POLL)
            continue

        if not seeded:
            # Seed ALL existing AI ids so history isn't re-spoken. Any
            # message that was still growing when we started is detected by
            # the block-count tracking below: if it grows after seeding, we
            # un-seed it and speak it once it settles. This handles any
            # number of in-flight responses at startup.
            for m in msgs:
                if isinstance(m, dict) and m.get("variant") == "ai":
                    mid = m.get("id", "")
                    seen.add(mid)
                    grow[mid] = (len(m.get("blocks", [])), time.time())
            save_state(seen)
            seeded = True
            print(f"[vaca-speak] seeded {len(seen)} existing messages — "
                  f"in-flight ones will be spoken once they settle",
                  flush=True)
            time.sleep(POLL)
            continue

        paused = os.path.exists(PAUSE_FILE)
        now = time.time()
        pending = []
        for m in msgs:
            if not isinstance(m, dict) or m.get("variant") != "ai":
                continue
            mid = m.get("id", "")
            nblocks = len(m.get("blocks", []))
            if mid in grow:
                old_n, _ = grow[mid]
                if nblocks != old_n:
                    # Was seeded as seen but is still growing — it was
                    # in-flight at startup, so un-seed it (will speak later).
                    grow[mid] = (nblocks, now)
                    if mid in seen:
                        seen.discard(mid)
                        print(f"[vaca-speak] response {mid[:18]} was "
                              f"in-flight at start — will speak it when done",
                              flush=True)
                    continue
                if mid in seen:
                    continue
                if now - grow[mid][1] < SETTLE:
                    continue  # settled < 6s — hold on
                pending.append((mid, nblocks))
            else:
                # Brand-new message — start tracking it.
                grow[mid] = (nblocks, now)

        for mid, _ in pending:
            found = [m for m in msgs if isinstance(m, dict)
                     and m.get("id") == mid]
            if not found:
                continue
            texts = extract_final_text(found)
            if not texts:
                seen.add(mid)
                continue
            text, _mid = texts[0]
            seen.add(mid)
            grow.pop(mid, None)
            if paused:
                print(f"[vaca-speak] (paused) skipping response {mid[:18]}",
                      flush=True)
                continue
            snippet = text[:60].replace("\n", " ")
            print(f"[vaca-speak] speaking response {mid[:18]}: {snippet}...",
                  flush=True)
            try:
                speak(text)
            except Exception as e:
                print(f"[vaca-speak] ⚠️ speak error: {e}", flush=True)
        save_state(seen)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
