"""Input parsing utilities for GANGLIA Studio.

This module provides functions for parsing and initializing various interfaces
like TTS (Text-to-Speech) based on user preferences or configuration.
"""

from ganglia_common.tts.google_tts import GoogleTTS, TextToSpeech
from ganglia_common.tts.openai_tts import OpenAITTS

from ganglia_studio.interface.constants import (
    GOOGLE_TTS_SERVICE,
    OPENAI_DEFAULT_VOICE,
    OPENAI_TTS_SERVICE,
    SUPPORTED_TTS_SERVICES,
)


def parse_tts_interface(tts_interface: str, apply_effects: bool = False) -> TextToSpeech:
    """Parse TTS interface string and return appropriate TTS implementation.

    Args:
        tts_interface: String identifier for TTS service ("google" or "openai")
        apply_effects: Whether to apply audio effects (pitch, reverb, etc.) to Google TTS

    Returns:
        TextToSpeech: Initialized TTS implementation

    Raises:
        ValueError: If an invalid TTS interface is provided

    Examples:
        >>> tts = parse_tts_interface("google")
        >>> tts = parse_tts_interface("openai")
        >>> tts = parse_tts_interface("google", apply_effects=True)
    """
    normalized = tts_interface.lower()
    if normalized == GOOGLE_TTS_SERVICE:
        return GoogleTTS(apply_effects=apply_effects)
    if normalized == OPENAI_TTS_SERVICE:
        return OpenAITTS(voice=OPENAI_DEFAULT_VOICE)
    raise ValueError(
        f"Invalid TTS interface provided: '{tts_interface}'. "
        f"Available options: {', '.join(SUPPORTED_TTS_SERVICES)}"
    )
