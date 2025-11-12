"""Tests for the FoxAI Suno backend integration.

This module contains tests that verify the functionality of the FoxAI Suno
backend, including music generation with lyrics and instrumental music generation.
The tests include audio playback capabilities with skip functionality.
"""

import os
import time
import pytest
import requests
from music_backends.foxai_suno import FoxAISunoBackend
from tests.test_helpers import play_media

class MockQueryDispatcher:
    def send_query(self, query):
        return {
            "text": "Generated lyrics for testing",
            "style": "folk"
        }

def check_service_available():
    """Check if the FoxAI Suno service is available."""
    try:
        backend = FoxAISunoBackend()
        response = requests.get(f"{backend.api_base_url}/gateway/query?ids=test", headers=backend.headers)
        return response.status_code != 404
    except:
        return False

@pytest.mark.live
def test_generate_instrumental():
    """Test generating an instrumental song."""
    if not check_service_available():
        pytest.skip("FoxAI Suno service is currently unavailable (404)")

    # Initialize the backend
    backend = FoxAISunoBackend()

    # Set up test parameters
    prompt = "A peaceful piano melody with gentle strings in the background"

    # Start generation
    job_id = backend.start_generation(
        prompt=prompt,
        title="Peaceful Piano",
        tags="piano peaceful instrumental",
        with_lyrics=False
    )
    assert job_id is not None, "Failed to start generation"

    # Wait for completion and get result
    audio_path = None
    while True:
        status, progress = backend.check_progress(job_id)
        print(f"\rStatus: {status} ({progress:.1f}%)", end='', flush=True)

        if status.lower() == "complete":  # Case-insensitive check
            print()  # New line after progress
            audio_path = backend.get_result(job_id)
            break

        if status.lower().startswith("error"):  # Case-insensitive check
            print()  # New line after progress
            raise RuntimeError(f"Generation failed: {status}")

        time.sleep(5)

    # Verify the song was generated
    assert audio_path is not None, "Song generation timed out or failed"
    assert os.path.exists(audio_path), "Song file does not exist"
    assert os.path.getsize(audio_path) > 0, "Song file is empty"
    assert audio_path.endswith('.mp3'), "Song file is not an mp3"

    print(f"\nGenerated instrumental file: {audio_path}")

    play_media(audio_path)

    return audio_path

@pytest.mark.live
def test_generate_with_lyrics():
    """Test generating a song with lyrics."""
    if not check_service_available():
        pytest.skip("FoxAI Suno service is currently unavailable (404)")

    # Initialize the backend
    backend = FoxAISunoBackend()

    # Set up test parameters
    prompt = "A gentle folk song with acoustic guitar"
    story_text = (
        "Life is beautiful, every day brings something new\n"
        "The sun is shining, and the sky is so blue\n"
        "Birds are singing their sweet melodies\n"
        "Nature's symphony, carried by the breeze"
    )

    # Create mock query dispatcher
    query_dispatcher = MockQueryDispatcher()

    # Start generation
    job_id = backend.start_generation(
        prompt=prompt,
        title="Nature's Song",
        tags="folk acoustic",
        with_lyrics=True,
        story_text=story_text,
        query_dispatcher=query_dispatcher
    )
    assert job_id is not None, "Failed to start generation"

    # Wait for completion and get result
    audio_path = None
    while True:
        status, progress = backend.check_progress(job_id)
        print(f"\rStatus: {status} ({progress:.1f}%)", end='', flush=True)

        if status.lower() == "complete":  # Case-insensitive check
            print()  # New line after progress
            audio_path = backend.get_result(job_id)
            break

        if status.lower().startswith("error"):  # Case-insensitive check
            print()  # New line after progress
            raise RuntimeError(f"Generation failed: {status}")

        time.sleep(5)

    # Verify the song was generated
    assert audio_path is not None, "Song generation timed out or failed"
    assert os.path.exists(audio_path), "Song file does not exist"
    assert os.path.getsize(audio_path) > 0, "Song file is empty"
    assert audio_path.endswith('.mp3'), "Song file is not an mp3"

    print(f"\nGenerated lyrical song file: {audio_path}")

    play_media(audio_path)
    return audio_path
