"""Tests for audio alignment functionality."""

import os
import pytest
import whisper
import threading
from ganglia_common.tts.google_tts import GoogleTTS
from ganglia_studio.video.audio_alignment import align_words_with_audio, create_word_level_captions
import ganglia_studio.video.audio_alignment


def test_word_alignment():
    # Create test audio using TTS
    tts = GoogleTTS()
    test_text = "This is a test sentence for word alignment"
    success, audio_path = tts.convert_text_to_speech(test_text)
    assert success and audio_path is not None, "Failed to generate test audio"

    try:
        # Test word alignment
        word_timings = align_words_with_audio(audio_path, test_text)
        assert word_timings is not None, "Failed to generate word timings"
        assert len(word_timings) > 0, "No word timings generated"

        # Verify words are in order and have valid timings
        for i in range(len(word_timings) - 1):
            assert word_timings[i].end <= word_timings[i + 1].start, "Word timings are not in order"
            assert word_timings[i].start >= 0, "Invalid start time"
            assert word_timings[i].end > word_timings[i].start, "Invalid timing duration"
    finally:
        # Cleanup
        if os.path.exists(audio_path):
            os.remove(audio_path)


def test_caption_generation_from_audio():
    # Create test audio using TTS
    tts = GoogleTTS()
    test_text = "Testing caption generation from audio file"
    success, audio_path = tts.convert_text_to_speech(test_text)
    assert success and audio_path is not None, "Failed to generate test audio"

    try:
        # Test caption generation
        captions = create_word_level_captions(audio_path, test_text)
        assert captions is not None, "Failed to generate captions"
        assert len(captions) > 0, "No captions generated"

        # Verify caption timings are in order
        for i in range(len(captions) - 1):
            assert captions[i].end_time <= captions[i + 1].start_time, "Caption timings are not in order"
            assert captions[i].start_time >= 0, "Invalid start time"
            assert captions[i].end_time > captions[i].start_time, "Invalid timing duration"
    finally:
        # Cleanup
        if os.path.exists(audio_path):
            os.remove(audio_path)

@pytest.mark.costly
def test_closing_credits_with_music():
    """Test word alignment with the closing credits song."""
    try:
        print("\nTesting closing credits song transcription:")
        music_path = "tests/unit/ttv/test_data/closing_credits.mp3"

        # Use base model as it provides cleaner transcription
        model = whisper.load_model("base", device="cpu")
        result = model.transcribe(
            music_path,
            language="en",
            word_timestamps=True,
            fp16=False
        )

        assert result and "text" in result, "Failed to transcribe closing credits"
        transcribed_text = result["text"].strip()

        # Validate key aspects of the transcription
        assert transcribed_text.lower().startswith("in the quiet of a shadowed room"), "Unexpected start of lyrics"
        assert "in every flutter eternity" in transcribed_text.lower(), "Missing expected ending lyrics"

        # Get word timings
        word_timings = align_words_with_audio(music_path, transcribed_text)
        assert word_timings is not None, "Failed to generate word timings"
        assert len(word_timings) > 150, "Expected at least 150 words in the song"  # Based on previous runs

        # Verify word timing order and non-negative times
        for i in range(len(word_timings) - 1):
            assert word_timings[i].start >= 0, "Invalid start time"
            assert word_timings[i].end >= word_timings[i].start, "End time before start time"
            assert word_timings[i].end <= word_timings[i + 1].start, "Word timings are not in order"

    except FileNotFoundError:
        print("Test data file not found. Please ensure tests/unit/ttv/test_data/closing_credits.mp3 exists.")
        assert False, "Test data file not found"


def _test_alignment_with_model(model_size: str) -> tuple[set[str], set[str]]:
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

    # First generate audio for this text
    tts = GoogleTTS()
    success, audio_path = tts.convert_text_to_speech(text)
    assert success and audio_path is not None, "Failed to generate test audio"

    try:
        # Get word-level captions using specified model size
        captions = create_word_level_captions(audio_path, text, model_name=model_size)
        assert captions is not None, "Failed to create word-level captions"

        # Print debug info about found words
        print(f"\nFound words in caption (using {model_size} model):")
        for caption in captions:
            print(f"'{caption.text}' ({caption.start_time:.2f}s - {caption.end_time:.2f}s)")

        # Convert text to lowercase for comparison since Whisper might change case
        text_words = set(word.strip().lower() for word in text.split())
        caption_words = set(word.strip().lower() for caption in captions for word in caption.text.split())

        # Check for missing words
        missing_words = text_words - caption_words
        extra_words = caption_words - text_words

        print("\nWord verification:")
        print(f"Expected words: {sorted(text_words)}")
        print(f"Found words: {sorted(caption_words)}")
        if missing_words:
            print(f"Missing words: {sorted(missing_words)}")
        if extra_words:
            print(f"Extra words: {sorted(extra_words)}")

        return missing_words, extra_words

    finally:
        # Clean up
        if os.path.exists(audio_path):
            os.remove(audio_path)


def test_complex_phrase_alignment():
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
    missing_words, extra_words = _test_alignment_with_model('small')

    # If small model fails, try with medium model
    if missing_words or extra_words:
        print("\nSmall model had issues, trying with 'medium' model:")
        missing_words, extra_words = _test_alignment_with_model('medium')

    # Assert that all words were found
    assert not missing_words, f"Words missing from captions: {missing_words}"
    assert not extra_words, f"Extra words in captions: {extra_words}"


def test_thread_safe_model_loading():
    """Test that Whisper model is only loaded once when called from multiple threads."""
    # Create test audio using TTS
    tts = GoogleTTS()
    test_text = "This is a test sentence for word alignment"
    success, audio_path = tts.convert_text_to_speech(test_text)
    assert success and audio_path is not None, "Failed to generate test audio"

    # Initialize outside try block to avoid UnboundLocalError in finally
    original_load_model = whisper.load_model

    try:
        # Reset global variables
        ganglia_studio.video.audio_alignment._whisper_model = None
        ganglia_studio.video.audio_alignment._whisper_model_size = None
        ganglia_studio.video.audio_alignment._model_loading = False
        ganglia_studio.video.audio_alignment._model_loading_event.clear()

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
        # Restore original function
        whisper.load_model = original_load_model
        # Cleanup
        if os.path.exists(audio_path):
            os.remove(audio_path)
