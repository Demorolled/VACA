#!/usr/bin/env python3
"""jarvis_voice.py — shared voice helper for Jarvis apps.

Lets any app (chess, and future ones) have JARVIS speak to the user, using
the exact same TTS setup as main.py: voice/rate/pitch from
Jarvis2/config.yaml (voice: section) with JARVIS_TTS_* env overrides.

Design:
  - Pure stdlib + optional edge_tts / pyttsx3 — never raises, never blocks
    the game (speech runs in a daemon thread).
  - `clean_for_speech()` strips markdown, emoji and symbols so nothing
    symbol-like is ever read aloud (mirrors voice/speaker.py).
  - `san_to_speech()` humanizes chess SAN ("Nxe5+" -> "knight takes e5,
    check") for natural spoken move announcements.
  - Falls back edge-tts -> pyttsx3 -> silent, so apps work even without
    network or the module.

Apps import it like:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import jarvis_voice
    jarvis_voice.say_move("White", "Nxe5+")
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

# Jarvis2 is a sibling of visual-ai-architect/ (both live in the Desktop root).
_JARVIS_ROOT = Path(__file__).resolve().parents[2] / "Jarvis2"
DEFAULT_CONFIG = _JARVIS_ROOT / "config.yaml"

PIECE_NAMES = {"K": "king", "Q": "queen", "R": "rook", "B": "bishop",
               "N": "knight", "P": "pawn"}

_speak_lock = threading.Lock()
_speaking = False


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Voice settings: Jarvis2/config.yaml `voice:` section, env wins."""
    cfg = {
        "enabled": True,
        "backend": "edge-tts",
        "voice_id": "en-US-BrianNeural",
        "rate": 196,
        "pitch": 1.0,
        "volume": 1.0,
    }
    path = os.environ.get("JARVIS_CONFIG", str(DEFAULT_CONFIG))
    try:
        import yaml  # noqa: PLC0415 — optional, config is a nicety
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        v = (data.get("voice") or {})
        cfg["enabled"] = bool(v.get("tts_enabled", True))
        cfg["backend"] = str(v.get("tts_backend", cfg["backend"]))
        cfg["voice_id"] = str(v.get("tts_voice_id", cfg["voice_id"]))
        cfg["rate"] = int(v.get("tts_rate", cfg["rate"]))
        cfg["pitch"] = float(v.get("tts_pitch", cfg["pitch"]))
        cfg["volume"] = float(v.get("tts_volume", cfg["volume"]))
    except Exception:
        pass  # defaults
    env = os.environ
    if env.get("JARVIS_TTS_ENABLED", "").strip().lower() in ("0", "false", "no", "off"):
        cfg["enabled"] = False
    if env.get("JARVIS_TTS_VOICE", "").strip():
        cfg["voice_id"] = env["JARVIS_TTS_VOICE"].strip()
    if env.get("JARVIS_TTS_RATE", "").strip():
        cfg["rate"] = int(env["JARVIS_TTS_RATE"].strip())
    if env.get("JARVIS_TTS_PITCH", "").strip():
        cfg["pitch"] = float(env["JARVIS_TTS_PITCH"].strip())
    return cfg


def enabled() -> bool:
    return load_config()["enabled"]


# ── Cleanup (mirrors voice/speaker.py clean_for_speech) ──────────────────────

def clean_for_speech(text: str) -> str:
    """Strip markdown, emoji and symbols so TTS speaks clean natural language."""
    if not text:
        return ""
    text = re.sub(r"</?reasonings?>|</?answers?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```[\w+#.-]*\s*[\s\S]*?```", "", text)
    text = re.sub(r"`[^`\n]+`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+|ftp://\S+", "", text)
    text = re.sub(r"\*\*|\*|__|_|~~", "", text)
    text = re.sub(r"(?:^|\n)[ \t]*#{1,6}[ \t]+", "\n", text)
    text = re.sub(r"(?:^|\n)[ \t]*[-*+][ \t]+", "\n", text)
    text = re.sub(r"(?:^|\n)[ \t]*\d+\.[ \t]+", "\n", text)
    text = re.sub(r"(?:^|\n)[ \t]*>[ \t]*", "\n", text)
    text = re.sub(r"\|[-:| ]+\|", "", text)
    text = re.sub(r"\[SKILL:\w+\]", "", text)
    text = re.sub(r"#+", " ", text)  # hashtags/hash marks are never spoken
    emoji = re.compile(
        "[\U0001F000-\U0001FAFF\U0001F1E0-\U0001F1FF\U00002600-\U000027BF"
        "\U0000FE00-\U0000FE0F\U0001F300-\U0001F5FF\U00002190-\U000021FF"
        "\U000025A0-\U000025FF\U00002B00-\U00002BFF\U0001F900-\U0001F9FF"
        "\U00002702-\U000027B0]"
    )
    text = emoji.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Chess SAN -> natural speech ───────────────────────────────────────────────

_SAN_RE = re.compile(r"^([KQRBN])?([a-h])?([1-8])?(x)?([a-h][1-8])(=?[QRBN])?([+#])?$")


def san_to_speech(san: str) -> str:
    """Humanize a chess SAN move into a spoken sentence (no side prefix)."""
    if not san:
        return ""
    san = san.strip()
    if san in ("O-O", "O-O-O", "0-0", "0-0-0"):
        return "castles kingside" if san in ("O-O", "0-0") else "castles queenside"
    m = _SAN_RE.match(san)
    if not m:
        # Unknown notation — speak it plainly, cleaned
        return clean_for_speech(san)
    piece, _file, _rank, capture, square, promo, suffix = m.groups()
    piece_name = PIECE_NAMES.get(piece, "pawn")
    if promo:
        words = [piece_name, "promotes to", PIECE_NAMES[promo[1]], "on", square]
    else:
        words = [piece_name, "takes" if capture else "to", square]
    out = " ".join(words)
    if suffix == "+":
        out += ", check"
    elif suffix == "#":
        out += ", checkmate"
    return out


def say_move(side: str, san: str) -> None:
    """Speak a move like 'White, knight takes e5, check'."""
    if not enabled():
        return
    speech = san_to_speech(san)
    if not speech:
        return
    text = f"{side} {speech}." if side else f"{speech}."
    speak(text)


# ── TTS backends ──────────────────────────────────────────────────────────────

def _edge_tts_say(text: str, cfg: dict) -> bool:
    """Generate via edge-tts and play it. Returns True if played."""
    try:
        import edge_tts
        import asyncio
    except ImportError:
        return False
    voice = cfg["voice_id"]
    rate = int(cfg["rate"])
    rate_str = f"+{rate - 180}%" if rate >= 180 else f"-{180 - rate}%"
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    try:
        asyncio.run(edge_tts.Communicate(text, voice=voice, rate=rate_str).save(mp3_path))
        if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
            return False
        return _play_mp3(mp3_path)
    except Exception:
        return False
    finally:
        try:
            os.unlink(mp3_path)
        except OSError:
            pass


def _play_mp3(mp3_path: str) -> bool:
    """Play an mp3 via ffplay -> ffmpeg|paplay -> ffmpeg|aplay."""
    methods = [
        [["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path]],
        [["ffmpeg", "-loglevel", "quiet", "-i", mp3_path, "-f", "wav", "pipe:1"],
         ["paplay"]],
        [["ffmpeg", "-loglevel", "quiet", "-i", mp3_path, "-f", "wav", "pipe:1"],
         ["aplay", "-q"]],
    ]
    for method in methods:
        try:
            if len(method) == 1:
                return subprocess.run(method[0], timeout=60,
                                      stderr=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL).returncode == 0
            decode = subprocess.Popen(method[0], stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL)
            play = subprocess.run(method[1], stdin=decode.stdout, timeout=60,
                                  stderr=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL)
            decode.wait()
            if play.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _pyttsx3_say(text: str, cfg: dict) -> bool:
    try:
        import pyttsx3  # noqa: PLC0415 — optional fallback backend
        engine = pyttsx3.init()
        engine.setProperty("rate", int(cfg["rate"]))
        engine.setProperty("volume", float(cfg["volume"]))
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception:
        return False


def speak(text: str, wait: bool = False) -> None:
    """Have Jarvis speak `text`. Non-blocking by default; drops new speech
    while something is already being spoken (sparse events like chess moves).
    Never raises."""
    if not enabled():
        return
    clean = clean_for_speech(text)
    if not clean:
        return
    cfg = load_config()

    def _do():
        global _speaking
        with _speak_lock:
            if _speaking:
                return
            _speaking = True
        try:
            backend = cfg["backend"].lower()
            if backend == "edge-tts" and _edge_tts_say(clean, cfg):
                return
            if backend == "pyttsx3" or not backend:
                _pyttsx3_say(clean, cfg)
            elif backend == "edge-tts":
                _pyttsx3_say(clean, cfg)  # edge failed (offline?) -> fallback
            else:
                _pyttsx3_say(clean, cfg)  # unknown backend -> try pyttsx3
        finally:
            with _speak_lock:
                _speaking = False

    if wait:
        _do()
    else:
        threading.Thread(target=_do, daemon=True).start()
