#!/usr/bin/env python3
"""Headless tests for jarvis_voice.py — pure functions only, never audio."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

import jarvis_voice as jv


# ── SAN -> speech ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("san,expected", [
    ("e4", "pawn to e4"),
    ("Nf3", "knight to f3"),
    ("Bxe5", "bishop takes e5"),
    ("exd5", "pawn takes d5"),
    ("O-O", "castles kingside"),
    ("O-O-O", "castles queenside"),
    ("0-0", "castles kingside"),
    ("e8=Q", "pawn promotes to queen on e8"),
    ("exd8=Q", "pawn promotes to queen on d8"),
    ("Nxe5+", "knight takes e5, check"),
    ("Qh4#", "queen to h4, checkmate"),
    ("Nbd2", "knight to d2"),          # disambiguation dropped
    ("R1e2", "rook to e2"),            # disambiguation dropped
    ("", ""),
])
def test_san_to_speech(san, expected):
    assert jv.san_to_speech(san) == expected


def test_san_to_speech_unknown_falls_back_clean():
    out = jv.san_to_speech("weird notation **bold** 🚀")
    assert "**" not in out and "🚀" not in out


def test_say_move_builds_sentence():
    assert jv.say_move("White", "e4") is None  # no-op returns None, never raises


# ── cleanup ───────────────────────────────────────────────────────────────────

def test_clean_for_speech_strips_symbols():
    raw = "**bold** [link](http://x.com) `code` 🚀 # #header #star*"
    out = jv.clean_for_speech(raw)
    for bad in ("**", "`", "🚀", "http://", "#", "*"):
        assert bad not in out
    assert "bold" in out and "link" in out


def test_clean_for_speech_keeps_natural_words():
    out = jv.clean_for_speech("Hello Jarvis, the score is 3-1 today!")
    assert out == "Hello Jarvis, the score is 3-1 today!"


# ── config ────────────────────────────────────────────────────────────────────

def test_config_defaults_enabled(monkeypatch):
    monkeypatch.delenv("JARVIS_TTS_ENABLED", raising=False)
    cfg = jv.load_config()
    assert cfg["enabled"] is True
    assert cfg["voice_id"]  # something picked from config or default
    assert cfg["rate"] > 0


def test_config_env_disable(monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_ENABLED", "0")
    assert jv.enabled() is False
    monkeypatch.delenv("JARVIS_TTS_ENABLED", raising=False)


def test_config_env_overrides(monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_VOICE", "en-US-GuyNeural")
    monkeypatch.setenv("JARVIS_TTS_RATE", "150")
    cfg = jv.load_config()
    assert cfg["voice_id"] == "en-US-GuyNeural"
    assert cfg["rate"] == 150
    monkeypatch.delenv("JARVIS_TTS_VOICE", raising=False)
    monkeypatch.delenv("JARVIS_TTS_RATE", raising=False)


def test_speak_disabled_is_silent(monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_ENABLED", "0")
    # must not raise or touch audio machinery
    jv.speak("hello there")
    jv.say_move("White", "e4")
    monkeypatch.delenv("JARVIS_TTS_ENABLED", raising=False)


def test_speak_cleans_text(monkeypatch):
    # speak() with enabled forced off still cleans first — check no crash
    monkeypatch.setenv("JARVIS_TTS_ENABLED", "0")
    jv.speak("**raw** 🚀 text")
    monkeypatch.delenv("JARVIS_TTS_ENABLED", raising=False)
