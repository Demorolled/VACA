#!/usr/bin/env python3
"""
vaca-tts.py — VACA's TTS system, wired into the terminal.

A faithful port of VACA's backend TTS (backend/src/routes/tts.ts +
ttsSpeakerService.ts): the same Microsoft neural voices (edge-tts), the same
speech normalizer (code fences silenced, emojis expanded, symbols spoken
naturally). Two additions make it a terminal tool:

  1. SPEAK ANY TEXT FROM THE TERMINAL:
       python3 scripts/vaca-tts.py "Hello, this is Veronica speaking."
       echo "Build me a chess game" | python3 scripts/vaca-tts.py
       python3 scripts/vaca-tts.py --file response.txt --voice en-US-GuyNeural

  2. SPEAK THE LLM'S GENERATED RESPONSE (dspark / VACA model):
       python3 scripts/vaca-tts.py --dspark "Build a 3D chess game"
     --dspark asks the local dspark server (:8000) and speaks the reply.

Fallback chain if the network is down:
  edge-tts (neural, 12 voices, same as VACA) -> piper (local .onnx voices)
  -> espeak-ng (last resort). Playback: ffplay -> paplay -> aplay.

Options:
  --voice ID        edge-tts voice (default en-US-JennyNeural; see --voices)
  --rate PCT        speech rate percent, e.g. +20 or -10 (default +20)
  --volume PCT      volume percent (default +0)
  --pitch HZ        pitch in Hz, e.g. +30 (default +0)
  --file PATH       read text from a file instead of argv/stdin
  --dspark PROMPT   ask the dspark LLM, then speak its response
  --dspark-url URL  override dspark endpoint (default http://127.0.0.1:8000)
  --save OUT        also save the audio to a file (mp3)
  --voices          list available edge-tts voices and exit
  --code-to-words   read code blocks aloud instead of silencing them
  --no-play         synthesize but do not play (with --save, useful to just
                    generate an mp3)
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

# ─── Voices — the same set VACA exposes on /api/tts/voices ─────────────────
AVAILABLE_VOICES = [
    "en-US-JennyNeural", "en-US-AriaNeural", "en-US-AndrewNeural",
    "en-US-BrianNeural", "en-US-ChristopherNeural", "en-US-EricNeural",
    "en-US-GuyNeural", "en-US-RogerNeural", "en-US-AngelaNeural",
    "en-US-SaraNeural", "en-GB-SoniaNeural", "en-GB-RyanNeural",
]

# ─── Emoji → spoken-word expansion (ported 1:1 from backend/src/routes/tts.ts) ─
EMOJI_MAP = {
    "😀": " grinning face ", "😂": " face with tears of joy ",
    "🤣": " rolling on the floor laughing ", "😊": " smiling face ",
    "😍": " smiling face with heart eyes ", "🥰": " smiling face with hearts ",
    "🤔": " thinking face ", "😏": " smirking face ", "😢": " crying face ",
    "😭": " loudly crying face ", "😡": " enraged face ", "🤖": " robot face ",
    "👍": " thumbs up ", "👎": " thumbs down ", "👏": " clapping hands ",
    "🙌": " raising hands ", "🤝": " handshake ", "🙏": " folded hands ",
    "💪": " flexed biceps ", "🎉": " party popper ", "🎊": " confetti ball ",
    "🚀": " rocket ", "💡": " light bulb ", "✨": " sparkles ", "🔥": " fire ",
    "⭐": " star ", "❤️": " red heart ", "💔": " broken heart ",
    "✅": " check mark ", "❌": " cross mark ", "❓": " question mark ",
    "❗": " exclamation mark ", "⚠️": " warning ", "🔧": " wrench ",
    "🔒": " locked lock ", "🔓": " unlocked lock ", "💻": " laptop ",
    "📱": " mobile phone ", "☕": " hot beverage ", "🍕": " pizza ",
    "🍔": " hamburger ", "🎯": " bullseye ", "🎮": " video game ",
    "🎵": " musical note ", "🔊": " speaker ", "🎨": " artist palette ",
    "📝": " memo ", "📚": " books ", "💯": " hundred points ", "👑": " crown ",
    "🏆": " trophy ", "🌈": " rainbow ", "☀️": " sun ", "🌙": " moon ",
    "🚨": " alert ", "♻️": " recycling ", "™️": " trademark ",
    "©️": " copyright ", "®️": " registered ",
}


def normalize_for_speech(text: str, code_to_words: bool = False) -> str:
    """Port of VACA's normalizeForSpeech — make LLM output sound natural."""
    result = text
    if code_to_words:
        result = re.sub(r"```[a-zA-Z0-9_-]*\s*", " ", result)
        result = result.replace("```", " ")
    else:
        # Default: never read code aloud — silence complete fences and any
        # unclosed fence opener along with the rest of the text.
        result = re.sub(r"```[\s\S]*?```", " ", result)
        result = re.sub(r"```[a-zA-Z0-9_-]*[\s\S]*$", " ", result)
    # Inline code backticks: keep inner text
    result = re.sub(r"`([^`]+)`", r" \1 ", result)
    # Markdown bold/italic
    result = re.sub(r"\*\*([^*]+)\*\*", r" \1 ", result)
    result = re.sub(r"\*([^*]+)\*", r" \1 ", result)
    result = re.sub(r"__([^_]+)__", r" \1 ", result)
    result = re.sub(r"_([^_]+)_", r" \1 ", result)
    # Code operators → words
    result = re.sub(r"\s*=>\s*", " becomes ", result)
    result = re.sub(r"\s*===\s*", " equals ", result)
    result = re.sub(r"\s*==\s*", " equals ", result)
    result = re.sub(r"\s*!==\s*", " does not equal ", result)
    result = re.sub(r"\s*!=\s*", " does not equal ", result)
    result = re.sub(r"\s*>=\s*", " greater than or equal ", result)
    result = re.sub(r"\s*<=\s*", " less than or equal ", result)
    result = re.sub(r"\s*&&\s*", " and ", result)
    result = re.sub(r"\s*\|\|\s*", " or ", result)
    # Package paths: a/b → a slash b
    result = re.sub(
        r"([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)",
        lambda m: m.group(0).replace("/", " slash "), result)
    # File extensions: file.ts → file dot ts
    result = re.sub(r"\.([a-zA-Z]{2,4})(?=\s|$)", r" dot \1 ", result)
    # Standalone symbols that are annoying in speech
    # (JS used (?<=^|[\s(]) — Python lookbehind needs fixed width, so
    # capture the boundary instead and re-emit it)
    result = re.sub(
        r"(^|[\s(])[*#@$%^&~`|\\_{}\[\]<>](?=[\s)]|$)",
        r"\1 ", result)
    # Emoji expansion
    for emoji, replacement in EMOJI_MAP.items():
        result = result.replace(emoji, replacement)
    # Strip remaining unmapped emojis
    result = re.sub(
        r"[\U0001F000-\U0001FFFF]|[\u2700-\u27BF]|[\u2600-\u26FF]"
        r"|[\uFE00-\uFE0F]|[\u200D]", "", result)
    # Collapse whitespace
    return re.sub(r"\s+", " ", result).strip()


# ─── dspark — speak the LLM's generated response ───────────────────────────
def ask_dspark(prompt: str, url: str, max_tokens: int = 1500) -> str:
    payload = {
        "model": "x",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"]


# ─── Synthesis: edge-tts -> piper -> espeak-ng ─────────────────────────────
async def synth_edge(text: str, voice: str, rate: str, volume: str,
                     pitch: str, out_path: str) -> bool:
    try:
        import edge_tts
    except ImportError:
        return False
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate,
                                           volume=volume, pitch=pitch)
        await communicate.save(out_path)
        return os.path.getsize(out_path) > 1024
    except Exception as e:
        print(f"  [edge-tts failed: {e}]", file=sys.stderr)
        return False


def synth_piper(text: str, out_path: str) -> bool:
    piper = "/home/final-flash1/miniconda3/bin/piper"
    if not os.path.exists(piper):
        return False
    voice_dir = os.path.expanduser("~/.local/share/piper/voices")
    models = sorted(f for f in os.listdir(voice_dir)
                    if f.endswith(".onnx")) if os.path.isdir(voice_dir) else []
    if not models:
        return False
    model = os.path.join(voice_dir, models[0])
    wav = out_path.rsplit(".", 1)[0] + ".wav"
    try:
        r = subprocess.run(
            [piper, "--model", model, "--output_file", wav],
            input=text.encode(), capture_output=True, timeout=120)
        if r.returncode == 0 and os.path.getsize(wav) > 1024:
            return True
    except Exception:
        pass
    return False


def synth_espeak(text: str, out_path: str) -> bool:
    wav = out_path.rsplit(".", 1)[0] + ".wav"
    exe = "espeak-ng" if _which("espeak-ng") else "espeak"
    if not _which(exe):
        return False
    try:
        r = subprocess.run(
            [exe, "-w", wav, text], capture_output=True, timeout=120)
        return r.returncode == 0 and os.path.getsize(wav) > 1024
    except Exception:
        return False


# ─── Playback: ffplay -> paplay -> aplay ───────────────────────────────────
def _which(name: str) -> str | None:
    for p in os.environ.get("PATH", "").split(":"):
        c = os.path.join(p, name)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def play(path: str) -> bool:
    if not os.path.exists(path):
        return False
    if _which("ffplay"):
        subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel",
                          "quiet", path]).wait()
        return True
    if _which("paplay"):
        subprocess.Popen(["paplay", path]).wait()
        return True
    if _which("aplay"):
        subprocess.Popen(["aplay", "-q", path]).wait()
        return True
    print("  ⚠️  no audio player found (ffplay/paplay/aplay)", file=sys.stderr)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="VACA TTS in the terminal")
    ap.add_argument("text", nargs="*", help="text to speak (or use --dspark)")
    ap.add_argument("--voice", default="en-US-JennyNeural")
    ap.add_argument("--rate", default="+20%")
    ap.add_argument("--volume", default="+0%")
    ap.add_argument("--pitch", default="+0Hz")
    ap.add_argument("--file")
    ap.add_argument("--dspark")
    ap.add_argument("--dspark-url", default="http://127.0.0.1:8000")
    ap.add_argument("--save")
    ap.add_argument("--voices", action="store_true")
    ap.add_argument("--code-to-words", action="store_true")
    ap.add_argument("--no-play", action="store_true")
    args = ap.parse_args()

    # edge-tts needs explicit units: rate/volume are percentages, pitch Hz.
    def _unit(val: str, suffix: str) -> str:
        v = val.strip()
        return v if v.endswith(("%", "Hz", "hz")) else v + suffix

    rate = _unit(args.rate, "%")
    volume = _unit(args.volume, "%")
    pitch = _unit(args.pitch, "Hz")

    if args.voices:
        for v in AVAILABLE_VOICES:
            print(v)
        return

    # Gather text: --dspark > --file > argv > stdin
    if args.dspark:
        print(f"[vaca-tts] asking dspark: {args.dspark}")
        text = ask_dspark(args.dspark, args.dspark_url)
        print(f"[vaca-tts] response ({len(text)} chars):\n{text}\n")
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = " ".join(args.text)
    else:
        text = sys.stdin.read()

    text = text.strip()
    if not text:
        print("⚠️  no text to speak", file=sys.stderr)
        sys.exit(1)

    spoken = normalize_for_speech(text, args.code_to_words)
    print(f"[vaca-tts] speaking {len(spoken)} chars with voice {args.voice}")

    fd, tmp = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    ok = asyncio.run(synth_edge(spoken, args.voice, rate, volume, pitch, tmp))
    engine = "edge-tts"
    real_out = tmp  # edge-tts writes the mp3 we asked for
    if not ok:
        ok = synth_piper(spoken, tmp)
        engine = "piper (offline)"
        real_out = tmp.rsplit(".", 1)[0] + ".wav"  # piper writes wav
    if not ok:
        ok = synth_espeak(spoken, tmp)
        engine = "espeak-ng (offline)"
        real_out = tmp.rsplit(".", 1)[0] + ".wav"  # espeak writes wav
    if not ok:
        print("❌ all TTS engines failed", file=sys.stderr)
        sys.exit(1)

    print(f"[vaca-tts] synthesized with {engine}")
    if args.save:
        dst = args.save
        ext = ".wav" if engine in ("piper (offline)", "espeak-ng (offline)") else ".mp3"
        if not dst.lower().endswith((".mp3", ".wav")):
            dst += ext
        os.replace(real_out, dst)
        print(f"[vaca-tts] saved: {dst}")
    elif not args.no_play:
        play(real_out)
    for leftover in (tmp, tmp.rsplit(".", 1)[0] + ".wav"):
        if os.path.exists(leftover):
            os.unlink(leftover)


if __name__ == "__main__":
    main()
