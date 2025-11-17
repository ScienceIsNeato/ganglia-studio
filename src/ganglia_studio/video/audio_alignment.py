"""Audio alignment module for text-to-video generation.

This module provides functionality for aligning audio with video segments,
including:
- Audio duration calculation
- Segment timing adjustment
- Whisper-based audio transcription
- FFmpeg-based audio processing
"""

# Standard library imports
import os
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from functools import partial

# Third-party imports
import torch
import whisper

# Local imports
from ganglia_common.logger import Logger
from ganglia_common.utils.retry_utils import exponential_backoff

from .captions import CaptionEntry

# Add parent directory to Python path to import logger
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Monkey patch torch.load to always use weights_only=True
torch.load = partial(torch.load, weights_only=True)

whisper_lock = threading.Lock()
_whisper_model = None
_whisper_model_size = None
_model_loading = False
_model_loading_event = threading.Event()


def get_whisper_model(model_size: str = "small") -> whisper.Whisper:
    """Get or load Whisper model, ensuring thread safety and clean state.

    Args:
        model_size: Size of model to load if not already loaded

    Returns:
        whisper.Whisper: The loaded model instance
    """
    global _whisper_model, _whisper_model_size, _model_loading, _model_loading_event

    # Fast path - if model exists and is right size, return it
    if _whisper_model is not None and _whisper_model_size == model_size:
        # Clear model state before returning
        if hasattr(_whisper_model, "decoder") and hasattr(_whisper_model.decoder, "_kv_cache"):
            _whisper_model.decoder._kv_cache = {}
        return _whisper_model

    # If another thread is loading the model, wait for it
    if _model_loading:
        Logger.print_info("Waiting for Whisper model to be loaded by another thread...")
        _model_loading_event.wait()
        # After waiting, check if the model is what we need
        if _whisper_model is not None and _whisper_model_size == model_size:
            # Clear model state before returning
            if hasattr(_whisper_model, "decoder") and hasattr(_whisper_model.decoder, "_kv_cache"):
                _whisper_model.decoder._kv_cache = {}
            return _whisper_model

    # Slow path - need to load model
    with whisper_lock:
        # Double-check pattern
        if _whisper_model is not None and _whisper_model_size == model_size:
            # Clear model state before returning
            if hasattr(_whisper_model, "decoder") and hasattr(_whisper_model.decoder, "_kv_cache"):
                _whisper_model.decoder._kv_cache = {}
            return _whisper_model

        # Mark that we're loading the model and clear any previous event
        _model_loading = True
        _model_loading_event.clear()

        try:
            # Load new model
            _whisper_model = whisper.load_model(
                model_size,
                device="cpu",  # Force CPU usage
                download_root=None,  # Use default download location
                in_memory=True,  # Keep model in memory
            )
            _whisper_model_size = model_size

            # Initialize empty cache
            if hasattr(_whisper_model, "decoder"):
                _whisper_model.decoder._kv_cache = {}

            return _whisper_model
        finally:
            # Always mark loading as complete and notify waiters
            _model_loading = False
            _model_loading_event.set()


@dataclass
class WordTiming:
    """Represents a word with its start and end times from audio."""

    text: str
    start: float
    end: float


def _transcribe_with_whisper(model, audio_path, text):
    """Transcribe audio with Whisper model and return result."""
    with whisper_lock:
        return model.transcribe(
            audio_path,
            word_timestamps=True,
            initial_prompt=text,
            condition_on_previous_text=False,
            language="en",
            temperature=0.0,
            no_speech_threshold=0.3,
            logprob_threshold=-0.7,
            compression_ratio_threshold=2.0,
            best_of=5,
        )


def _extract_word_timings(result):
    """Extract word timings from Whisper result."""
    word_timings = []
    for segment in result["segments"]:
        if "words" not in segment:
            continue
        for word in segment["words"]:
            if not isinstance(word, dict):
                continue
            if not all(k in word for k in ["word", "start", "end"]):
                continue
            word_timings.append(
                WordTiming(text=word["word"].strip(), start=word["start"], end=word["end"])
            )
    return word_timings


def _should_retry(attempt, max_retries, error_msg):
    """Check if we should retry and log appropriate messages."""
    if error_msg:
        Logger.print_error(f"{error_msg} on attempt {attempt + 1}")
    if attempt < max_retries - 1:
        Logger.print_info(f"Retrying whisper alignment (attempt {attempt + 1}/{max_retries})")
        time.sleep(0.5)
        return True
    return False


def align_words_with_audio(
    audio_path: str, text: str, model_size: str = "small", max_retries: int = 5
) -> list[WordTiming]:
    """
    Analyze audio file to generate word-level timings.
    Uses Whisper ASR to perform forced alignment between the audio and text.
    Falls back to even distribution if Whisper alignment fails after max_retries.

    Args:
        audio_path: Path to the audio file (should be wav format)
        text: The expected text content of the audio
        model_size: Size of the Whisper model to use ("tiny", "base", "small")
        max_retries: Maximum number of retry attempts for whisper alignment

    Returns:
        List of WordTiming objects containing word-level alignments
    """
    for attempt in range(max_retries):
        try:
            model = get_whisper_model(model_size)

            # Clear any existing cache
            if hasattr(model, "decoder") and hasattr(model.decoder, "_kv_cache"):
                model.decoder._kv_cache = {}

            result = _transcribe_with_whisper(model, audio_path, text)

            if not result or "segments" not in result:
                if _should_retry(attempt, max_retries, "No segments found in result"):
                    continue
                return create_evenly_distributed_timings(audio_path, text)

            word_timings = _extract_word_timings(result)

            if not word_timings:
                if _should_retry(attempt, max_retries, "No word timings found"):
                    continue
                return create_evenly_distributed_timings(audio_path, text)

            if attempt > 0:
                Logger.print_info(f"✓ Whisper alignment succeeded on attempt {attempt + 1}")
            return word_timings

        except Exception as e:
            Logger.print_error(f"Whisper alignment failed on attempt {attempt + 1}: {str(e)}")
            if _should_retry(attempt, max_retries, None):
                continue
            return create_evenly_distributed_timings(audio_path, text)

    # If we get here, all retries failed
    Logger.print_error(
        f"All {max_retries} whisper alignment attempts failed, falling back to even distribution"
    )
    return create_evenly_distributed_timings(audio_path, text)


def create_evenly_distributed_timings(audio_path: str, text: str) -> list[WordTiming]:
    """
    Create evenly distributed word timings when Whisper alignment fails.

    Args:
        audio_path: Path to the audio file
        text: The text to create timings for

    Returns:
        List of WordTiming objects with evenly distributed timings
    """
    try:
        # Get total audio duration using ffprobe
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        total_duration = float(result.stdout)

        # Split text into words
        words = text.split()
        if not words:
            return []

        # Calculate time per word
        time_per_word = total_duration / len(words)

        # Create evenly distributed timings
        word_timings = []
        for i, word in enumerate(words):
            start_time = i * time_per_word
            end_time = (i + 1) * time_per_word
            word_timings.append(WordTiming(text=word, start=start_time, end=end_time))

        Logger.print_info(
            f"Created fallback evenly distributed timings for {len(words)} words over "
            f"{total_duration:.2f}s"
        )
        return word_timings

    except Exception as e:
        Logger.print_error(f"Error creating evenly distributed timings: {str(e)}")
        return []


def create_word_level_captions(
    audio_file: str, text: str, model_name: str = "small", thread_id: str = None
) -> list[CaptionEntry]:
    """Create word-level captions by aligning text with audio using Whisper.

    Args:
        audio_file: Path to the audio file
        text: Text to align with audio
        model_name: Whisper model name to use (default: "small")
        thread_id: Optional thread ID for logging

    Returns:
        List[CaptionEntry]: List of caption entries with word-level timings
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        Logger.print_info(f"{thread_prefix}Creating word-level captions for: {audio_file}")

        # Load model and process with retries using exponential backoff
        def load_and_process_model():
            model = get_whisper_model(model_name)

            # Clear any existing cache
            if hasattr(model, "decoder") and hasattr(model.decoder, "_kv_cache"):
                model.decoder._kv_cache = {}

            # Process audio with lock
            with whisper_lock:
                result = model.transcribe(
                    audio_file,
                    word_timestamps=True,
                    initial_prompt=text,  # Add text as initial prompt to guide transcription
                    condition_on_previous_text=False,  # Don't condition on previous text
                    language="en",  # Pass language in decode_options
                    temperature=0.0,  # Use greedy decoding for more consistent results
                    no_speech_threshold=0.3,  # Lower threshold since we know we have speech
                    logprob_threshold=-0.7,  # More strict about word confidence
                    compression_ratio_threshold=2.0,  # Help detect hallucinations
                    best_of=5,  # Try multiple candidates and take the best one
                )
            return model, result

        # Use exponential backoff for model loading and processing
        _, result = exponential_backoff(
            load_and_process_model, max_retries=5, initial_delay=1.0, thread_id=thread_id
        )

        # Extract word timings
        words = []
        for segment in result["segments"]:
            for word in segment.get("words", []):
                # Debug log the word structure
                Logger.print_debug(f"{thread_prefix}Word data: {word}")

                # Get word text with fallback to empty string
                word_text = word.get("text", word.get("word", ""))
                if not word_text:
                    Logger.print_warning(f"{thread_prefix}Empty word text in segment")
                    continue

                # Clean up word text by removing only extra whitespace
                word_text = word_text.strip()
                if not word_text:
                    continue

                words.append(
                    {"text": word_text, "start": word.get("start", 0), "end": word.get("end", 0)}
                )

        # If no words were found, fall back to evenly distributed
        if not words:
            Logger.print_warning(
                f"{thread_prefix}No words found in Whisper output, "
                "falling back to even distribution"
            )
            return create_evenly_distributed_captions(audio_file, text, thread_id)

        # Create caption entries
        captions = []
        for _, word in enumerate(words):
            caption = CaptionEntry(
                text=word["text"], start_time=word["start"], end_time=word["end"]
            )
            captions.append(caption)

        return captions

    except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
        Logger.print_error(f"{thread_prefix}Error creating word-level captions: {str(e)}")
        Logger.print_error(f"{thread_prefix}Full traceback: {traceback.format_exc()}")
        Logger.print_info(f"{thread_prefix}Falling back to evenly distributed captions")
        return create_evenly_distributed_captions(audio_file, text, thread_id)
    except OSError as e:
        Logger.print_error(f"{thread_prefix}Error reading audio file: {str(e)}")
        Logger.print_error(f"Traceback: {traceback.format_exc()}")
        Logger.print_info(f"{thread_prefix}Falling back to evenly distributed captions")
        return create_evenly_distributed_captions(audio_file, text, thread_id)
    except Exception as e:
        Logger.print_error(
            f"{thread_prefix}Unexpected error in create_word_level_captions: {str(e)}"
        )
        Logger.print_error(f"Traceback: {traceback.format_exc()}")
        Logger.print_info(f"{thread_prefix}Falling back to evenly distributed captions")
        return create_evenly_distributed_captions(audio_file, text, thread_id)


def create_evenly_distributed_captions(
    audio_file: str, text: str, thread_id: str | None = None
) -> list[CaptionEntry]:
    """Create evenly distributed captions when Whisper alignment fails.

    Args:
        audio_file: Path to the audio file
        text: Text to create captions for
        thread_id: Optional thread ID for logging

    Returns:
        List[CaptionEntry]: List of caption entries with evenly distributed timings
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    try:
        # Get total audio duration using ffprobe
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_file,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        total_duration = float(result.stdout)

        # Split text into words
        words = text.split()
        if not words:
            return []

        # Calculate time per word
        time_per_word = total_duration / len(words)

        # Create evenly distributed captions
        captions = []
        for i, word in enumerate(words):
            start_time = i * time_per_word
            end_time = (i + 1) * time_per_word
            captions.append(CaptionEntry(text=word, start_time=start_time, end_time=end_time))

        Logger.print_info(
            f"{thread_prefix}Created evenly distributed captions for {len(words)} words over "
            f"{total_duration:.2f}s"
        )
        return captions

    except Exception as e:
        Logger.print_error(f"{thread_prefix}Error creating evenly distributed captions: {str(e)}")
        return []


def get_audio_duration(audio_file: str, thread_id: str = None) -> float:
    """Get the duration of an audio file in seconds.

    Args:
        audio_file: Path to the audio file
        thread_id: Optional thread ID for logging

    Returns:
        float: Duration in seconds
    """
    try:
        thread_prefix = f"{thread_id} " if thread_id else ""
        Logger.print_info(f"{thread_prefix}Getting duration for audio file: {audio_file}")

        # Use ffprobe to get duration
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_file,
        ]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True
        )
        duration = float(result.stdout.strip())

        Logger.print_info(f"{thread_prefix}Audio duration: {duration:.2f} seconds")
        return duration

    except subprocess.CalledProcessError as e:
        Logger.print_error(f"{thread_prefix}FFprobe error: {e.stderr.decode()}")
        raise
    except (ValueError, OSError) as e:
        Logger.print_error(f"{thread_prefix}Error getting audio duration: {str(e)}")
        raise
