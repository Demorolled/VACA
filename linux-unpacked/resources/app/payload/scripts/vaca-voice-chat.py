#!/usr/bin/env python3
"""
vaca-voice-chat.py — one-click VACA voice chat.

Interactive loop: you type a prompt, dspark (the VACA LLM, currently R15)
generates a response, and VACA's TTS speaks it aloud through the terminal.

  • If dspark is not running, this script starts it automatically (waits for
    health) — so the desktop icon is truly one-click.
  • Speak is streamed through scripts/vaca-tts.py (edge-tts neural voice,
    piper/espeak fallback offline).

In-chat commands:
  /voice NAME     switch voice (try: Guy, Andrew, Aria, Sonia...)
  /voices         list voices
  /code           toggle reading code blocks aloud (default: silenced)
  /rate +N        speaking speed percent
  /quit  |  /exit | Ctrl+C

Run:  python3 scripts/vaca-voice-chat.py
"""
import glob
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS = os.path.join(ROOT, "scripts", "vaca-tts.py")
DSPARK = "http://127.0.0.1:8000"
DSPARK_SERVER = os.path.join(ROOT, "scripts", "dspark_server.py")


def resolve_model() -> str:
    """The currently deployed GGUF — read from dspark-target.env (source of
    truth), falling back to the newest Qwen2.5-7B GGUF in models/ so the
    one-click launcher never breaks after a round deploy."""
    env_path = os.path.join(ROOT, "scripts", "dspark-target.env")
    try:
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("DSPARK_TARGET="):
                p = line.split("=", 1)[1].strip()
                if os.path.exists(p):
                    return p
    except OSError:
        pass
    models_dir = os.path.join(ROOT, "models")
    gguifs = sorted(glob.glob(os.path.join(models_dir, "*.gguf")),
                    key=os.path.getmtime, reverse=True)
    return gguifs[0] if gguifs else ""

VOICES = [
    "en-US-JennyNeural", "en-US-AriaNeural", "en-US-AndrewNeural",
    "en-US-BrianNeural", "en-US-ChristopherNeural", "en-US-EricNeural",
    "en-US-GuyNeural", "en-US-RogerNeural", "en-US-AngelaNeural",
    "en-US-SaraNeural", "en-GB-SoniaNeural", "en-GB-RyanNeural",
]

SYSTEM = (
    "You are Veronica, the VACA assistant speaking through the terminal. "
    "You help the user build software: GUIs, 3D apps, games, tools. "
    "Answer conversationally and concisely (under 150 words). "
    "When asked to build something, describe the plan briefly in plain "
    "language — do not dump full code unless asked."
)


def chat_print(msg: str) -> None:
    print(msg, flush=True)


def dspark_ok() -> bool:
    try:
        with urllib.request.urlopen(DSPARK + "/v1/health", timeout=5) as r:
            return json.loads(r.read()).get("status") == "ok"
    except Exception:
        return False


def start_dspark() -> bool:
    """Start dspark in tmux and wait for health (up to ~5 min)."""
    model = resolve_model()
    print("[voice] dspark not running — starting it (first load takes ~1-2 min)...",
          flush=True)
    if not model:
        print("[voice] ❌ no GGUF model found in models/", flush=True)
        return False
    print(f"[voice] loading {os.path.basename(model)}", flush=True)
    cmd = (f"cd {ROOT} && tmux kill-session -t dspark 2>/dev/null; "
           f"tmux new-session -d -s dspark "
           f"'python3 {DSPARK_SERVER} --target {model} --draft qwen2.5-coder:0.5b "
           f"--port 8000 --n-ctx 16384 --n-gpu-layers -1 --draft-mode none "
           f"> {ROOT}/scripts/dspark.log 2>&1'")
    subprocess.run(cmd, shell=True)
    for _ in range(60):
        if dspark_ok():
            print("[voice] ✅ dspark is up.", flush=True)
            return True
        time.sleep(5)
    print("[voice] ❌ dspark did not become healthy in time — check "
          f"{ROOT}/scripts/dspark.log", flush=True)
    return False


def ask(prompt: str) -> str:
    payload = {
        "model": "x",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1500,
        "stream": False,
    }
    req = urllib.request.Request(
        DSPARK + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"]


def tts_python() -> str:
    """A python interpreter that can import edge_tts (VACA's neural voice).

    If started with the system python (/usr/bin/python3.13) edge_tts is
    missing, so vaca-tts.py silently falls back to piper (different voice,
    slower, rate ignored). Prefer the interpreter that has edge_tts.
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


def speak(text: str, voice: str, rate: str, code_to_words: bool) -> None:
    cmd = [tts_python(), TTS, "--voice", voice, "--rate", rate]
    if code_to_words:
        cmd.append("--code-to-words")
    # Synthesize + play in ONE pass; stream text via stdin so long responses
    # don't hit argv limits.
    subprocess.run(cmd, input=text.encode(), timeout=300)


def main() -> None:
    voice = "en-US-JennyNeural"
    rate = "+20%"
    code_to_words = False

    if not dspark_ok() and not start_dspark():
        sys.exit(1)

    print("=" * 60, flush=True)
    print("  VACA Voice Chat — type a prompt, hear Veronica answer.", flush=True)
    print("  /voice NAME · /voices · /code · /rate +N · /quit", flush=True)
    print("=" * 60, flush=True)

    while True:
        try:
            user = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[voice] bye!", flush=True)
            break
        if not user:
            continue
        low = user.lower()
        if low in ("/quit", "/exit", "quit", "exit"):
            print("[voice] bye!", flush=True)
            break
        if low == "/voices":
            print("\n" + "\n".join(f"  {v}" for v in VOICES), flush=True)
            continue
        if low.startswith("/voice"):
            parts = user.split()
            if len(parts) > 1:
                want = parts[1]
                matches = [v for v in VOICES
                           if want.lower() in v.lower().replace("en-", "")]
                if matches:
                    voice = matches[0]
                    print(f"[voice] → {voice}", flush=True)
                else:
                    print(f"[voice] no voice matches '{want}' — see /voices", flush=True)
            else:
                print(f"[voice] current: {voice}", flush=True)
            continue
        if low == "/code":
            code_to_words = not code_to_words
            print(f"[voice] code-to-words: {'ON (code will be read)' if code_to_words else 'OFF (code silenced)'}", flush=True)
            continue
        if low.startswith("/rate"):
            parts = user.split()
            if len(parts) > 1:
                rate = parts[1] if parts[1].endswith("%") else parts[1] + "%"
                print(f"[voice] rate {rate}", flush=True)
            continue

        print("[voice] thinking...", flush=True)
        try:
            answer = ask(user)
        except Exception as e:
            print(f"[voice] ❌ dspark error: {e}", flush=True)
            continue
        print(f"\nVeronica > {answer}", flush=True)
        try:
            speak(answer, voice, rate, code_to_words)
        except Exception as e:
            print(f"[voice] ⚠️  speak error: {e}", flush=True)


if __name__ == "__main__":
    main()
