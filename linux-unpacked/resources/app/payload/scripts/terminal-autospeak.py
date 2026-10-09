#!/usr/bin/env python3
"""
terminal-autospeak.py — speak THIS terminal's assistant responses automatically.

PERFORMANCE NOTE: the transcript for a long session can reach 20-40 MB. This
daemon used to `json.load()` the whole file every POLL (2 s), which is a full
parse of tens of megabytes several times a second — enough to make the desktop
feel frozen and the client unresponsive. It now stats the file (cheap) and only
parses once the file has STOPPED changing for SETTLE seconds, i.e. roughly once
per finished response instead of continuously.

Terminal-dedicated copy of scripts/vaca-auto-speak.py. It tails the Freebuff
chat transcript (`.config/manicode/projects/*/chats/*/chat-messages.json`) and,
whenever the assistant finishes a response, feeds the FINAL response text
through the app's TTS (scripts/terminal-tts.py) so it plays on the speakers.

Voice/rate are pinned to the VACA app's selected voice — see
backend/tts-config.json: voice `en-US-JennyNeural`, speed 1.1.

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
TTS = os.path.join(ROOT, "scripts", "terminal-tts.py")
CHATS_GLOB = os.path.expanduser(
    "~/.config/manicode/projects/*/chats/*/chat-messages.json")
STATE = os.path.join(ROOT, "scripts", ".terminal-speak-seen.json")

# Pinned to the VACA app's selected voice (backend/tts-config.json).
VOICE = "en-US-JennyNeural"
RATE = "+20%"  # VACA app speed 1.1
POLL = 2.0
SETTLE = 6.0       # speak only once a message hasn't grown for this long
PAUSE_FILE = "/tmp/vaca-speak.pause"
# A message already spoken is re-spoken only if its text grows by more than
# this much — long turns get caught mid-stream and yield only an opening line.
REPEAT_FACTOR = 1.5
REPEAT_MIN_GROWTH = 40


def newest_transcript() -> str:
    files = glob.glob(CHATS_GLOB)
    if not files:
        return ""
    return max(files, key=os.path.getmtime)


def load_state() -> dict:
    """id -> number of characters spoken for that message.

    The length matters: a response caught mid-stream yields only a fragment,
    and storing just "seen" would mean the real answer is never spoken. With
    the length we can speak the fragment and then replace it when the full
    text arrives.
    """
    try:
        raw = json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(raw, dict):
        out = {}
        for k, v in raw.items():
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                out[k] = -1
        return out
    # Legacy format: a plain list of ids, no lengths known. -1 means "spoken,
    # length unknown" and is never re-spoken.
    return {str(k): -1 for k in raw}


def save_state(seen: dict) -> None:
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(seen, f, sort_keys=True)
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


def select_pending(msgs: list, seen: dict) -> list:
    """Messages that should be spoken now, as (id, text).

    Returns a message when it has visible text and either was never spoken or
    has since grown well past what was spoken (a fragment caught mid-stream).

    Critically, a message with NO visible text is skipped and left unseen. An
    earlier version marked it seen at this point and silently muted the daemon:
    turns are long, and the transcript settles for more than SETTLE seconds in
    the gaps between tool calls, so the daemon would catch each response as an
    empty shell, mark it, and never speak it. Every one of 13 responses was
    marked spoken here while only one actually was.
    """
    out = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("variant") != "ai":
            continue
        mid = m.get("id", "")
        found = extract_final_text([m])
        if not found:
            continue                      # nothing speakable yet — try later
        text = found[0][0]
        prev = seen.get(mid)
        if prev is None:
            out.append((mid, text))       # never spoken
        elif prev >= 0 and len(text) > prev * REPEAT_FACTOR + REPEAT_MIN_GROWTH:
            out.append((mid, text))       # spoken, but only a fragment
    return out


def self_test() -> int:
    """Regression test for the mark-seen-without-text mute."""
    def msg(mid, blocks):
        return {"variant": "ai", "id": mid, "blocks": blocks}

    def text(t):
        return {"type": "text", "content": t}

    thinking = {"type": "text", "content": "hmm", "thinkingId": "x"}
    tool = {"type": "tool", "content": "..."}
    fails = []

    # The exact bug: mid-turn a response holds only a thinking block and tool
    # calls. It must not be selectable, and the caller must not record it —
    # `seen` is only written after speak() succeeds.
    shell = [msg("a", [thinking, tool])]
    if select_pending(shell, {}) != []:
        fails.append("empty shell was selected for speaking")

    # A new message with text gets spoken.
    done = [msg("b", [text("hello there friend")])]
    if [p[0] for p in select_pending(done, {})] != ["b"]:
        fails.append("new answered message was not selected")

    # Already spoken and unchanged -> silence.
    if select_pending(done, {"b": len("hello there friend")}) != []:
        fails.append("unchanged spoken message was re-selected")

    # Spoken as a fragment, then the real answer arrives -> speak it fully.
    full = [msg("c", [text("x" * 400)])]
    if [p[0] for p in select_pending(full, {"c": 60})] != ["c"]:
        fails.append("grown fragment was not re-selected")

    # A legacy -1 entry means "spoken, length unknown" and must not repeat.
    if select_pending(done, {"b": -1}) != []:
        fails.append("legacy entry was re-selected")

    # Non-AI variants are ignored entirely.
    human = [{"variant": "human", "id": "h", "blocks": [text("hi")]}]
    if select_pending(human, {}) != []:
        fails.append("human message was selected")

    if fails:
        print("self-test FAILED:")
        for c in fails:
            print("  -", c)
        return 1
    print("self-test OK — an empty shell is never treated as spoken, new "
          "responses are spoken, unchanged ones are not, and a fragment is "
          "replaced by the full text")
    return 0


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
    last_sig = None            # (mtime_ns, size) of the file as last seen
    last_change = 0.0          # when the file last changed
    print(f"[vaca-speak] watching transcripts {CHATS_GLOB}", flush=True)
    print(f"[vaca-speak] voice {VOICE} rate {RATE} | pause via "
          f"touch {PAUSE_FILE}", flush=True)

    while True:
        # Cheap stat first. The expensive json.load() below only runs once the
        # file has gone quiet, so a 20-40 MB transcript is parsed about once
        # per finished response instead of every POLL tick.
        try:
            path = newest_transcript()
            if not path:
                time.sleep(POLL)
                continue
            st = os.stat(path)
        except Exception:
            time.sleep(POLL)
            continue

        sig = (st.st_mtime_ns, st.st_size)
        if sig != last_sig:
            last_sig, last_change = sig, time.time()
            time.sleep(POLL)
            continue                      # still being written — don't parse

        if seeded and (time.time() - last_change) < SETTLE:
            time.sleep(POLL)
            continue                      # quiet, but not long enough yet

        try:
            msgs = json.load(open(path, encoding="utf-8"))
        except Exception:
            time.sleep(POLL)
            continue

        if not seeded:
            # Seed only messages that already have visible text, so completed
            # history isn't re-spoken. A message still streaming has no text
            # yet and is deliberately left unseen — it gets spoken when it
            # finishes, which is the whole point of starting the daemon
            # mid-conversation.
            for m in msgs:
                if not isinstance(m, dict) or m.get("variant") != "ai":
                    continue
                found = extract_final_text([m])
                if found:
                    seen.setdefault(m.get("id", ""), len(found[0][0]))
            save_state(seen)
            seeded = True
            print(f"[vaca-speak] seeded {len(seen)} completed messages — "
                  f"speaking new responses only", flush=True)
            time.sleep(POLL)
            continue

        paused = os.path.exists(PAUSE_FILE)
        pending = []
        for mid, text in select_pending(msgs, seen):
            prev = seen.get(mid)
            if prev is not None and prev >= 0:
                print(f"[vaca-speak] response {mid[:18]} grew "
                      f"{prev}→{len(text)} chars — speaking the full text",
                      flush=True)
            pending.append((mid, text))

        for mid, text in pending:
            if paused:
                print(f"[vaca-speak] (paused) holding response {mid[:18]}",
                      flush=True)
                continue
            snippet = text[:60].replace("\n", " ")
            print(f"[vaca-speak] speaking response {mid[:18]}: {snippet}...",
                  flush=True)
            try:
                speak(text)
            except Exception as e:
                print(f"[vaca-speak] ⚠️ speak error: {e}", flush=True)
                continue          # leave it unseen so it is retried
            seen[mid] = len(text)
        save_state(seen)
        time.sleep(POLL)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    main()
