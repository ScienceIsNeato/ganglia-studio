"""
Helper utilities for generating offline audio assets and mocking Whisper.

These helpers allow the test suite to run without network access or third-party
APIs by generating deterministic synthetic audio and providing a lightweight
Whisper stub that returns consistent word-level timestamps based solely on the
provided text prompt.
"""

from __future__ import annotations

import math
import os
import struct
import wave
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Synthetic audio helpers
# ---------------------------------------------------------------------------

def generate_dummy_tts_audio(
    text: str,
    output_directory: os.PathLike[str] | str,
    *,
    sample_rate: int = 16_000,
    base_frequency: float = 220.0,
    duration_per_word: float = 0.25,
) -> str:
    """
    Generate a deterministic sine-wave audio file for the provided text.

    The content of the audio file is not spoken text—instead, it is a simple
    waveform whose duration scales with the number of words.  This is sufficient
    for tests that only need a real audio file on disk (e.g., to feed ffprobe or
    to ensure that downstream FFmpeg commands succeed) without depending on
    external TTS services.
    """

    words = max(1, len(text.split()))
    duration_seconds = max(0.5, words * duration_per_word)
    total_samples = int(duration_seconds * sample_rate)

    output_dir = Path(output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"dummy_tts_{abs(hash(text)) & 0xFFFF_FFFF:x}.wav"

    amplitude = 12_000
    with wave.open(str(file_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)

        frames: Iterable[bytes] = (
            struct.pack(
                "<h",
                int(
                    amplitude
                    * math.sin(2 * math.pi * base_frequency * sample_index / sample_rate)
                ),
            )
            for sample_index in range(total_samples)
        )
        wav_file.writeframes(b"".join(frames))

    return str(file_path)


# ---------------------------------------------------------------------------
# Whisper mocking utilities
# ---------------------------------------------------------------------------

class _DummyDecoder:
    """Minimal decoder stub to satisfy code that clears `_kv_cache`."""

    def __init__(self) -> None:
        self._kv_cache: dict[str, float] = {}


class DummyWhisperModel:
    """
    Lightweight Whisper model stub used in tests.

    The model ignores the audio input entirely and synthesizes word timings from
    the provided `initial_prompt` so that higher-level alignment logic can be
    exercised deterministically.
    """

    def __init__(self) -> None:
        self.decoder = _DummyDecoder()

    @staticmethod
    def _build_segments_from_prompt(prompt: str) -> list[dict[str, object]]:
        words = [word for word in prompt.strip().split() if word]
        segments: list[dict[str, object]] = []

        if not words:
            return segments

        time_cursor = 0.0
        segment_words = []
        for word in words:
            entry = {
                "word": word,
                "text": word,
                "start": time_cursor,
                "end": time_cursor + 0.35,
            }
            segment_words.append(entry)
            time_cursor += 0.4

        segments.append({"text": prompt, "words": segment_words})
        return segments

    def transcribe(self, _audio_path: str, **kwargs) -> dict[str, object]:
        prompt = kwargs.get("initial_prompt") or ""
        segments = self._build_segments_from_prompt(prompt)
        return {"text": prompt, "segments": segments}


def setup_dummy_whisper(monkeypatch) -> DummyWhisperModel:
    """
    Install the dummy Whisper model into the audio_alignment module.

    Returns:
        DummyWhisperModel: The shared stub instance being used.
    """

    from ganglia_studio.video import audio_alignment as audio_alignment_module

    dummy_model = DummyWhisperModel()

    def load_model_stub(*_args, **_kwargs):
        return dummy_model

    monkeypatch.setattr(audio_alignment_module.whisper, "load_model", load_model_stub)
    monkeypatch.setattr(audio_alignment_module, "_whisper_model", dummy_model)
    monkeypatch.setattr(audio_alignment_module, "_whisper_model_size", "small")
    monkeypatch.setattr(audio_alignment_module, "_model_loading", False)
    audio_alignment_module._model_loading_event.clear()  # pylint: disable=protected-access

    return dummy_model


# ---------------------------------------------------------------------------
# High-word-count text snippets used by tests
# ---------------------------------------------------------------------------

CLOSING_CREDITS_LYRICS = (
    "In the quiet of a shadowed room when all the lights have dimmed away, "
    "We gather up the whispered dreams that made it through another day. "
    "Soft echoes of the stories told now drift across the silver screen, "
    "And every note of hope we played still sparkles in the in-betweens. "
    "Here at the end we take a bow, our hearts alight with embered gleam, "
    "For every soul who shared this path and trusted in the fragile dream. "
    "So linger here a moment more, let gratitude become the light, "
    "Because we only came this far by holding one another tight."
) * 5  # Repeat to ensure we have well over 150 words for stress tests.


