"""Tests for audio alignment functionality."""

import os
import threading

import pytest
import whisper

from ganglia_studio.video.audio_alignment import (
    align_words_with_audio,
    create_word_level_captions,
)
import ganglia_studio.video.audio_alignment
from tests.audio_fixtures import (
    CLOSING_CREDITS_LYRICS,
    generate_dummy_tts_audio,
)


@pytest.mark.slow
def test_word_alignment(tmp_path):
    test_text = "This is a test sentence for word alignment"
    audio_path = generate_dummy_tts_audio(test_text, tmp_path)

    # Test word alignment
    word_timings = align_words_with_audio(audio_path, test_text)
    assert word_timings is not None, "Failed to generate word timings"
    assert len(word_timings) > 0, "No word timings generated"

    # Verify words are in order and have valid timings
    for i in range(len(word_timings) - 1):
        assert word_timings[i].end <= word_timings[i + 1].start, "Word timings are not in order"
        assert word_timings[i].start >= 0, "Invalid start time"
        assert word_timings[i].end > word_timings[i].start, "Invalid timing duration"


@pytest.mark.slow
def test_caption_generation_from_audio(tmp_path):
    test_text = "Testing caption generation from audio file"
    audio_path = generate_dummy_tts_audio(test_text, tmp_path)

    captions = create_word_level_captions(audio_path, test_text)
    assert captions is not None, "Failed to generate captions"
    assert len(captions) > 0, "No captions generated"

    for i in range(len(captions) - 1):
        assert captions[i].end_time <= captions[i + 1].start_time, "Caption timings are not in order"
        assert captions[i].start_time >= 0, "Invalid start time"
        assert captions[i].end_time > captions[i].start_time, "Invalid timing duration"


@pytest.mark.slow
def test_closing_credits_with_music(tmp_path):
    """Test word alignment with an extended set of lyrics."""
    music_path = generate_dummy_tts_audio(CLOSING_CREDITS_LYRICS, tmp_path)

    # Use dummy lyrics to stress-test alignment with >150 words
    transcribed_text = CLOSING_CREDITS_LYRICS
    model = whisper.load_model("tiny", device="cpu")
    # The actual transcription is mocked via DummyWhisperModel but we keep the API call for parity
    model.transcribe(music_path, language="en", word_timestamps=True, fp16=False)

    word_timings = align_words_with_audio(music_path, transcribed_text)
    assert word_timings is not None, "Failed to generate word timings"
    assert len(word_timings) > 150, "Expected at least 150 words in the lyrics sample"

    for i in range(len(word_timings) - 1):
        assert word_timings[i].start >= 0, "Invalid start time"
        assert word_timings[i].end >= word_timings[i].start, "End time before start time"
        assert word_timings[i].end <= word_timings[i + 1].start, "Word timings are not in order"


def _test_alignment_with_model(model_size: str, tmp_path) -> tuple[set[str], set[str]]:
    """Helper function to test word alignment with different Whisper models.

    This function tests alignment on a complex phrase that has been observed
    to cause issues with word identification in production.

    Args:
        model_size: Size of Whisper model to use ('tiny', 'base', 'small', 'medium', 'large')

    Returns:
        tuple[set[str], set[str]]: Sets of (missing_words, extra_words)
    """
    # This text contains adjectives, compound words, and abstract concepts
    # that have been observed to cause issues with word identification
    text = "Ancient dragons soar through crystal skies, their scales shimmering with otherworldly light"

    audio_path = generate_dummy_tts_audio(text, tmp_path)

    captions = create_word_level_captions(audio_path, text, model_name=model_size)
    assert captions is not None, "Failed to create word-level captions"

    text_words = set(word.strip().lower() for word in text.split())
    caption_words = set(word.strip().lower() for caption in captions for word in caption.text.split())

    missing_words = text_words - caption_words
    extra_words = caption_words - text_words

    return missing_words, extra_words


@pytest.mark.slow
def test_complex_phrase_alignment(tmp_path):
    """Test word-level alignment for complex phrases.

    This test verifies Whisper's behavior with specific text patterns that have been
    observed to have incomplete word identification in production, including:
    - Adjective-heavy descriptions
    - Abstract concepts
    - Compound words
    - Poetic/literary language
    """
    # Try with small model first (better accuracy than base, still reasonably fast)
    print("\nTesting with 'small' model:")
    missing_words, extra_words = _test_alignment_with_model('small', tmp_path)

    # If small model fails, try with medium model
    if missing_words or extra_words:
        print("\nSmall model had issues, trying with 'medium' model:")
        missing_words, extra_words = _test_alignment_with_model('medium', tmp_path)

    # Assert that all words were found
    assert not missing_words, f"Words missing from captions: {missing_words}"
    assert not extra_words, f"Extra words in captions: {extra_words}"


@pytest.mark.slow
def test_thread_safe_model_loading(tmp_path):
    """Test that Whisper model is only loaded once when called from multiple threads."""
    test_text = "This is a test sentence for word alignment"
    audio_path = generate_dummy_tts_audio(test_text, tmp_path)

    # Initialize outside try block to avoid UnboundLocalError in finally
    original_load_model = whisper.load_model
    audio_alignment_module = ganglia_studio.video.audio_alignment
    original_whisper_state = audio_alignment_module._whisper_state

    try:
        # Reset shared Whisper model state
        audio_alignment_module._whisper_state = audio_alignment_module.WhisperModelState()

        # Track model loads
        model_load_count = 0

        def mock_load_model(*args, **kwargs):
            nonlocal model_load_count
            model_load_count += 1
            return original_load_model(*args, **kwargs)

        whisper.load_model = mock_load_model

        # Create two threads that will try to load the model simultaneously
        def thread_func():
            create_word_level_captions(audio_path, test_text, thread_id=threading.current_thread().name)

        thread1 = threading.Thread(name="Thread1", target=thread_func)
        thread2 = threading.Thread(name="Thread2", target=thread_func)

        # Start threads
        thread1.start()
        thread2.start()

        # Wait for threads to complete
        thread1.join()
        thread2.join()

        # Verify model was only loaded once
        assert model_load_count == 1, f"Model was loaded {model_load_count} times, expected 1"

    finally:
        whisper.load_model = original_load_model
        audio_alignment_module._whisper_state = original_whisper_state
        if os.path.exists(audio_path):
            os.remove(audio_path)
