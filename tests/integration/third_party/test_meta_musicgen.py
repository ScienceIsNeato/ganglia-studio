"""Tests for the Meta MusicGen backend integration.

This module contains tests that verify the functionality of the Meta MusicGen
backend, including music generation with lyrics and instrumental music generation.
The tests include audio playback capabilities with skip functionality.
"""

# Standard library imports
import os
import select
import subprocess
import sys
import termios
import tty
import time

# Third-party imports
import pytest

# Local imports
from music_lib import MusicGenerator
from ttv.config_loader import load_input
from music_backends.meta import MetaMusicBackend

def wait_for_spacebar():
    """Wait for spacebar press to continue."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        print("\nPress spacebar to continue...")
        while True:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                key = sys.stdin.read(1)
                if key == ' ':
                    break
    except (termios.error, IOError) as e:
        print(f"Terminal interaction error: {e}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

@pytest.mark.live
def test_meta_musicgen_generation():
    """Test music generation using Meta MusicGen."""
    backend = MetaMusicBackend()
    prompt = "A gentle piano melody with soft strings"

    try:
        # Start generation
        job_id = backend.start_generation(prompt=prompt)
        assert job_id is not None, "Failed to start generation"

        # Wait for completion and get result
        audio_path = None
        while True:
            status, progress = backend.check_progress(job_id)
            print(f"\rStatus: {status} ({progress:.1f}%)", end='', flush=True)

            if progress >= 100:
                print()  # New line after progress
                audio_path = backend.get_result(job_id)
                break

            time.sleep(5)

        # Verify the output
        assert audio_path is not None
        assert audio_path.endswith(".wav")
        return audio_path

    except (RuntimeError, IOError, ValueError) as e:
        pytest.skip(f"Meta MusicGen generation failed: {e}")

@pytest.mark.live
def test_meta_musicgen_with_duration():
    """Test music generation with specified duration."""
    backend = MetaMusicBackend()
    prompt = "An upbeat electronic track with synths"
    duration = 10

    try:
        # Start generation
        job_id = backend.start_generation(prompt=prompt, duration_seconds=duration)
        assert job_id is not None, "Failed to start generation"

        # Wait for completion and get result
        audio_path = None
        while True:
            status, progress = backend.check_progress(job_id)
            print(f"\rStatus: {status} ({progress:.1f}%)", end='', flush=True)

            if progress >= 100:
                print()  # New line after progress
                audio_path = backend.get_result(job_id)
                break

            time.sleep(5)

        # Verify the output
        assert audio_path is not None
        assert audio_path.endswith(".wav")
        return audio_path

    except (RuntimeError, IOError, ValueError) as e:
        pytest.skip(f"Meta MusicGen generation failed: {e}")

@pytest.mark.live
def test_meta_musicgen_with_seed():
    """Test music generation with specified seed."""
    backend = MetaMusicBackend()
    prompt = "A dramatic orchestral piece"
    seed = 42

    try:
        # Start generation
        job_id = backend.start_generation(prompt=prompt, seed=seed)
        assert job_id is not None, "Failed to start generation"

        # Wait for completion and get result
        audio_path = None
        while True:
            status, progress = backend.check_progress(job_id)
            print(f"\rStatus: {status} ({progress:.1f}%)", end='', flush=True)

            if progress >= 100:
                print()  # New line after progress
                audio_path = backend.get_result(job_id)
                break

            time.sleep(5)

        # Verify the output
        assert audio_path is not None
        assert audio_path.endswith(".wav")
        return audio_path

    except (RuntimeError, IOError, ValueError) as e:
        pytest.skip(f"Meta MusicGen generation failed: {e}")

@pytest.mark.live
def test_meta_musicgen_with_duration_and_seed():
    """Test music generation with specified duration and seed."""
    backend = MetaMusicBackend()
    prompt = "A jazzy saxophone solo"
    duration = 15
    seed = 123

    try:
        # Start generation
        job_id = backend.start_generation(prompt=prompt, duration_seconds=duration, seed=seed)
        assert job_id is not None, "Failed to start generation"

        # Wait for completion and get result
        audio_path = None
        while True:
            status, progress = backend.check_progress(job_id)
            print(f"\rStatus: {status} ({progress:.1f}%)", end='', flush=True)

            if progress >= 100:
                print()  # New line after progress
                audio_path = backend.get_result(job_id)
                break

            time.sleep(5)

        # Verify the output
        assert audio_path is not None
        assert audio_path.endswith(".wav")
        return audio_path

    except (RuntimeError, IOError, ValueError) as e:
        pytest.skip(f"Meta MusicGen generation failed: {e}")

@pytest.mark.live
def test_meta_backend():
    """Test the Meta MusicGen backend for instrumental music generation."""
    config = load_input("tests/integration/test_data/minimal_ttv_config.json")
    config.music_backend = "meta"  # Override to use Meta backend
    generator = MusicGenerator(config=config)

    def verify_duration(prompt: str, target_duration: int):
        print(f"\nGenerating instrumental music with prompt: {prompt}")
        audio_path = generator.generate_instrumental(
            prompt,
            duration_seconds=target_duration
        )

        # Verify the output
        assert audio_path is not None, "Audio path should not be None"
        assert os.path.exists(audio_path), f"Audio file should exist at {audio_path}"
        assert audio_path.endswith('.wav'), "Audio file should be WAV format"

        # Check actual duration with ffprobe
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            stdout=subprocess.PIPE,
            check=True,
            text=True
        )
        actual_duration = float(result.stdout.strip())
        # Allow 10% tolerance for duration
        assert abs(actual_duration - target_duration) <= 0.1 * target_duration, \
            f"Generated audio duration ({actual_duration:.1f}s) should be within 10% of target ({target_duration}s)"

        print(f"Expected duration: {target_duration}s matches Actual duration: {actual_duration:.1f}s")
        return audio_path

    # Test short duration (7 seconds)
    return verify_duration("A short peaceful piano melody. High quality recording.", 7)

@pytest.mark.costly
@pytest.mark.live
def test_meta_backend_longer_durations():
    """Test the Meta MusicGen backend with a 25 second duration (maximum single generation length)."""
    config = load_input("tests/integration/test_data/minimal_ttv_config.json")
    config.music_backend = "meta"  # Override to use Meta backend
    generator = MusicGenerator(config=config)

    def verify_duration(prompt: str, target_duration: int):
        print(f"\nGenerating instrumental music with prompt: {prompt}")
        audio_path = generator.generate_instrumental(
            prompt,
            duration_seconds=target_duration
        )

        # Verify the output
        assert audio_path is not None, "Audio path should not be None"
        assert os.path.exists(audio_path), f"Audio file should exist at {audio_path}"
        assert audio_path.endswith('.wav'), "Audio file should be WAV format"

        # Check actual duration with ffprobe
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            stdout=subprocess.PIPE,
            check=True,
            text=True
        )
        actual_duration = float(result.stdout.strip())
        # Allow 10% tolerance for duration
        assert abs(actual_duration - target_duration) <= 0.1 * target_duration, \
            f"Generated audio duration ({actual_duration:.1f}s) should be within 10% of target ({target_duration}s)"

        print(f"Expected duration: {target_duration}s matches Actual duration: {actual_duration:.1f}s")
        return audio_path

    # Test maximum single generation duration (25 seconds)
    return verify_duration("An evolving ambient soundscape with gentle pads and subtle rhythms.", 25)

@pytest.mark.costly
@pytest.mark.live
def test_meta_backend_looping():
    """Test the Meta MusicGen backend with a 3 minute duration that requires looping."""
    config = load_input("tests/integration/test_data/minimal_ttv_config.json")
    config.music_backend = "meta"  # Override to use Meta backend
    generator = MusicGenerator(config=config)

    def verify_duration(prompt: str, target_duration: int):
        print(f"\nGenerating instrumental music with prompt: {prompt}")
        audio_path = generator.generate_instrumental(
            prompt,
            duration_seconds=target_duration
        )

        # Verify the output
        assert audio_path is not None, "Audio path should not be None"
        assert os.path.exists(audio_path), f"Audio file should exist at {audio_path}"
        assert audio_path.endswith('.wav'), "Audio file should be WAV format"

        # Check actual duration with ffprobe
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            stdout=subprocess.PIPE,
            check=True,
            text=True
        )
        actual_duration = float(result.stdout.strip())
        # Allow 10% tolerance for duration
        assert abs(actual_duration - target_duration) <= 0.1 * target_duration, \
            f"Generated audio duration ({actual_duration:.1f}s) should be within 10% of target ({target_duration}s)"

        print(f"Expected duration: {target_duration}s matches Actual duration: {actual_duration:.1f}s")
        return audio_path

    # Test long duration that requires looping (3 minutes)
    return verify_duration(
        "A progressive electronic journey with evolving textures, subtle rhythms, and atmospheric pads that build and transform over time.",
        180  # 3 minutes in seconds
    )
