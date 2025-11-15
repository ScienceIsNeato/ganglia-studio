"""Audio generation module for text-to-video conversion.

This module provides functionality for:
- Generating audio from text using text-to-speech
- Processing and manipulating audio files
- Managing audio file operations and cleanup
- Handling audio generation retries and error cases
"""

import os
import subprocess

import requests
from ganglia_common.logger import Logger


def generate_audio(
    text: str,
    output_path: str,
    voice: str = "en-US-Neural2-F",
    language_code: str = "en-US",
    thread_id: str | None = None,
) -> str | None:
    """Generate audio from text using text-to-speech.

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: Voice ID to use for synthesis
        language_code: Language code for synthesis
        thread_id: Optional thread ID for logging

    Returns:
        Optional[str]: Path to generated audio if successful, None otherwise
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        # Create output directory if needed
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Call text-to-speech API
        response = requests.post(
            "https://texttospeech.googleapis.com/v1/text:synthesize",
            json={
                "input": {"text": text},
                "voice": {"languageCode": language_code, "name": voice},
                "audioConfig": {"audioEncoding": "LINEAR16", "pitch": 0, "speakingRate": 1.0},
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise ValueError(f"API request failed with status {response.status_code}")

        # Save audio data
        with open(output_path, "wb") as f:
            f.write(response.content)

        Logger.print_info(f"{thread_prefix}Generated audio saved to: {output_path}")
        return output_path

    except Exception as e:
        Logger.print_error(f"{thread_prefix}Error generating audio: {str(e)}")
        return None


def get_audio_duration(audio_path: str, thread_id: str | None = None) -> float | None:
    """Get the duration of an audio file in seconds.

    Args:
        audio_path: Path to the audio file
        thread_id: Optional thread ID for logging

    Returns:
        Optional[float]: Duration in seconds if successful, None otherwise
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        # Use ffprobe to get duration
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        duration = float(result.stdout.strip())
        Logger.print_debug(f"{thread_prefix}Audio duration: {duration:.2f} seconds")
        return duration

    except (subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(f"{thread_prefix}Error getting audio duration: {str(e)}")
        return None


def mix_audio_tracks(
    tracks: list[str],
    output_path: str,
    volumes: list[float] | None = None,
    thread_id: str | None = None,
) -> str | None:
    """Mix multiple audio tracks with optional volume adjustment.

    Args:
        tracks: List of audio file paths to mix
        output_path: Path to save mixed audio
        volumes: Optional list of volume multipliers for each track
        thread_id: Optional thread ID for logging

    Returns:
        Optional[str]: Path to mixed audio if successful, None otherwise
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        if not tracks:
            raise ValueError("No audio tracks provided")

        # Use default volumes if not provided
        if volumes is None:
            volumes = [1.0] * len(tracks)

        if len(volumes) != len(tracks):
            raise ValueError("Number of volume multipliers must match number of tracks")

        # Build filter complex for mixing
        inputs = []
        for i, track in enumerate(tracks):
            inputs.extend(["-i", track])

        filter_parts = []
        for i, volume in enumerate(volumes):
            filter_parts.append(f"[{i}:a]volume={volume}[a{i}]")

        mix_inputs = "".join(f"[a{i}]" for i in range(len(tracks)))
        filter_parts.append(f"{mix_inputs}amix=inputs={len(tracks)}:duration=longest[out]")

        filter_complex = ";".join(filter_parts)

        # Run ffmpeg command
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex",
                filter_complex,
                "-map",
                "[out]",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

        Logger.print_info(f"{thread_prefix}Mixed audio saved to: {output_path}")
        return output_path

    except (subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(f"{thread_prefix}Error mixing audio tracks: {str(e)}")
        return None
