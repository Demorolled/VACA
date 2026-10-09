#!/usr/bin/env python3
"""
vaca-hear.py — select-to-speak daemon for VACA's TTS.

Highlight (or copy) any text on screen — including this assistant's
responses in the terminal — and VACA's voice reads it aloud.

Modes:
  --selection   watch the PRIMARY selection (highlight-to-speak, default)
  --clipboard   watch the clipboard (copy-to-speak, Ctrl+Shift+C)

The daemon debounces fast partial selections (speaks only once the text has
been stable for DEBOUNCE seconds) and ignores trivial noise (< MIN_CHARS).

Run it once in the background (tmux):
  tmux new-session -d -s vaca-hear 'python3 scripts/vaca-hear.py'
  tmux kill-session -t vaca-hear          # stop it
  tmux a -t vaca-hear                     # watch its log

Test:  printf 'hello' | xclip -selection primary   -> should speak
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS = os.path.join(ROOT, "scripts", "vaca-tts.py")

POLL = 0.4            # seconds between clipboard reads
DEBOUNCE = 0.8        # text must be stable this long before speaking
MIN_CHARS = 12        # ignore selections shorter than this
MAX_CHARS = 6000      # don't speak gigantic pastes
RATE = "+20%"
VOICE = "en-US-JennyNeural"


def read_selection(clipboard: bool) -> str:
    """Read PRIMARY selection or CLIPBOARD; return '' if unavailable."""
    sel = "clipboard" if clipboard else "primary"
    if shutil.which("xclip"):
        try:
            out = subprocess.run(
                ["xclip", "-selection", sel, "-o", "-rmlastnl"],
                capture_output=True, timeout=3)
            if out.returncode == 0:
                return out.stdout.decode("utf-8", "replace")
        except Exception:
            pass
    if shutil.which("wl-paste"):
        try:
            out = subprocess.run(["wl-paste", "-n"], capture_output=True,
                                 timeout=3)
            if out.returncode == 0:
                return out.stdout.decode("utf-8", "replace")
        except Exception:
            pass
    return ""


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
    subprocess.run(cmd, input=text.encode(), timeout=300)


def main() -> None:
    global VOICE, RATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection", action="store_true",
                    help="watch PRIMARY selection (default)")
    ap.add_argument("--clipboard", action="store_true",
                    help="watch clipboard instead")
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--rate", default=RATE)
    args = ap.parse_args()
    clipboard = args.clipboard
    VOICE, RATE = args.voice, args.rate

    print(f"[vaca-hear] listening on {'CLIPBOARD' if clipboard else 'SELECTION'} "
          f"(voice {VOICE}, rate {RATE}) — select/copy text to hear it.",
          flush=True)
    last = ""
    stable_since = 0.0
    last_spoken = ""

    while True:
        try:
            txt = read_selection(clipboard).strip()
        except Exception:
            txt = ""
        now = time.time()

        if txt != last:
            last = txt
            stable_since = now
        elif txt and now - stable_since >= DEBOUNCE and txt != last_spoken:
            if MIN_CHARS <= len(txt) <= MAX_CHARS:
                # Ignore things that are mostly symbols (code smoke tests,
                # path strings, random terminal output the user brushes).
                alpha = sum(c.isalpha() for c in txt)
                if alpha >= 6:
                    print(f"[vaca-hear] speaking {len(txt)} chars: "
                          f"{txt[:70]}{'...' if len(txt) > 70 else ''}",
                          flush=True)
                    try:
                        speak(txt)
                        last_spoken = txt
                    except Exception as e:
                        print(f"[vaca-hear] ⚠️ speak error: {e}", flush=True)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
