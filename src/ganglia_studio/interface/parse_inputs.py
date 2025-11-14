"""Input parsing utilities for GANGLIA Studio.

This module provides functions for parsing and initializing various interfaces
like TTS (Text-to-Speech) based on user preferences or configuration.
"""

from ganglia_common.tts.google_tts import GoogleTTS, TextToSpeech
from ganglia_common.tts.openai_tts import OpenAITTS


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
    if tts_interface.lower() == "google":
        return GoogleTTS(apply_effects=apply_effects)
    elif tts_interface.lower() == "openai":
        return OpenAITTS(voice="onyx")  # Deep voice similar to GANGLIA's personality
    else:
        raise ValueError(
            f"Invalid TTS interface provided: '{tts_interface}'. "
            "Available options: 'google', 'openai'"
        )

