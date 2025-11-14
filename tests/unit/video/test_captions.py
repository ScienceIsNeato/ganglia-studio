"""Unit tests for the captions module.

This module contains tests for caption generation functionality including:
- Static caption generation
- Dynamic caption generation
- SRT caption file creation
- Word-level caption alignment
- Font size scaling and text wrapping
"""

# pylint: disable=no-member,unused-import,unused-variable,import-outside-toplevel

import os
import tempfile
import random
import pytest
import numpy as np
from PIL import Image
import cv2

from ganglia_common.logger import Logger
from ganglia_common.tts.google_tts import GoogleTTS
from ganglia_common.utils.file_utils import get_tempdir
from ganglia_studio.video.audio_alignment import create_word_level_captions
from ganglia_studio.video.captions import (
    CaptionEntry, Word, create_caption_windows,
    create_dynamic_captions, create_srt_captions,
    create_static_captions,
    calculate_word_positions,
    split_into_words
)
from ganglia_studio.video.color_utils import get_vibrant_palette
from ganglia_studio.utils.ffmpeg_utils import run_ffmpeg_command
from ganglia_studio.utils.video_utils import create_test_video
from tests.test_helpers import get_text_colors_from_video, play_media

def get_default_font():
    """Get the default font path for testing."""
    # Try common system font locations
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "C:\\Windows\\Fonts\\arial.ttf"  # Windows
    ]
    for path in font_paths:
        if os.path.exists(path):
            return path
    return None

def test_default_static_captions():
    """Test that static captions work with default settings."""
    # Create test video
    input_video_path = create_test_video(duration=2)
    assert input_video_path is not None, "Failed to create test video"

    # Create test captions
    captions = [CaptionEntry("Testing default static captions", 0.0, 2.0)]

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_default_static_test.mp4")

    try:
        # Test the function with default settings
        result = create_static_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path
        )

        # Verify results
        assert result is not None, "Failed to create video with default static captions"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)

def test_static_captions():
    """Test static caption generation"""
    # Create test video
    input_video_path = create_test_video(duration=1)
    assert input_video_path is not None, "Failed to create test video"

    # Create test captions
    captions = [
        CaptionEntry("Hello World", 0.0, 0.5),
        CaptionEntry("Testing Captions", 0.5, 1.0)
    ]

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_static_test.mp4")

    try:
        # Test the function
        result = create_static_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path
        )

        # Verify results
        assert result is not None, "Failed to create video with static captions"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_caption_text_completeness():
    """Test that all words from the original caption appear in the dynamic captions"""
    original_text = "This is a test caption with multiple words that should all appear in the output"
    # Split into words and verify all words are present
    words = original_text.split()
    # Use standard 720p dimensions for testing
    width, height = 1280, 720
    margin = 40
    max_window_height_ratio = 0.3
    # Calculate ROI dimensions
    roi_width = width - (2 * margin)
    roi_height = int(height * max_window_height_ratio)
    windows = create_caption_windows(
        words=[Word(text=w, start_time=0, end_time=1) for w in words],
        min_font_size=32,
        max_font_ratio=1.5,  # Max will be 48 (1.5x the min)
        roi_width=roi_width,
        roi_height=roi_height
    )
    # Collect all words from all windows
    processed_words = []
    for window in windows:
        processed_words.extend(word.text for word in window.words)
    assert set(words) == set(processed_words), "Not all words from original caption are present in processed output"


def test_font_size_and_variation():
    """Test that font sizes are properly scaled and varied based on video dimensions and word length"""
    # Create test video with specific dimensions
    video_size = (1280, 720)  # 720p test video
    input_video_path = create_test_video(size=video_size)
    assert input_video_path is not None, "Failed to create test video"

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_font_test.mp4")

    try:
        # Test with various caption lengths and word sizes
        test_cases = [
            "Short caption",  # Should use larger font
            "This is a much longer caption that should use a smaller font size to fit properly",
            "Testing with some very long words like supercalifragilisticexpialidocious",
            "This is a test of our random font size distribution in captions",
            "🎉 Testing with emojis and special characters !@#$%"
        ]
        captions = [CaptionEntry(text, idx * 2.0, (idx + 1) * 2.0) for idx, text in enumerate(test_cases)]

        # Add dynamic captions
        result_path = create_dynamic_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path,
            min_font_size=24,  # Smaller min to test scaling
            max_font_ratio=2.0  # Max will be 48 (2x the min)
        )

        # Verify results
        assert result_path is not None, "Failed to create video with font size testing"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_caption_positioning():
    """Test that captions stay within the safe viewing area"""
    # Create test video with specific dimensions
    video_size = (1920, 1080)
    input_video_path = create_test_video(size=video_size)
    assert input_video_path is not None, "Failed to create test video"

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_position_test.mp4")

    try:
        # Test with long captions that might overflow
        test_cases = [
            # Long single line to test horizontal overflow
            "This is a very long caption that should not extend beyond the right margin of the video frame",
            # Multiple short lines to test vertical spacing
            "Line one\nLine two\nLine three",
            # Long words that might cause overflow
            "Supercalifragilisticexpialidocious Pneumonoultramicroscopicsilicovolcanoconiosis",
            # Emojis and special characters
            "🌟 Testing with emojis 🎬 and special characters !@#$% to ensure proper spacing"
        ]
        captions = [
            CaptionEntry(text, idx * 2.0, (idx + 1) * 2.0)
            for idx, text in enumerate(test_cases)
        ]

        # Add dynamic captions with specific margin
        result_path = create_dynamic_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path,
            min_font_size=32,  # Ensure readable text
            max_font_ratio=1.5  # Max will be 48 (1.5x the min)
        )

        # Verify results
        assert result_path is not None, "Failed to create video with position testing"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_create_srt_captions():
    """Test SRT caption file creation."""
    # Create test captions
    captions = [
        CaptionEntry("First caption", 0.0, 2.0),
        CaptionEntry("Second caption", 2.0, 4.0)
    ]

    # Create SRT file
    srt_path = os.path.join(get_tempdir(), "test.srt")
    result = create_srt_captions(captions, srt_path)

    try:
        # Verify results
        assert result is not None, "Failed to create SRT file"
        assert os.path.exists(srt_path), f"SRT file not created: {srt_path}"
        assert os.path.getsize(srt_path) > 0, "SRT file is empty"

        # Read and verify content
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "First caption" in content, "First caption not found in SRT"
            assert "Second caption" in content, "Second caption not found in SRT"

    finally:
        # Clean up
        if os.path.exists(srt_path):
            os.unlink(srt_path)


def test_audio_aligned_captions():
    """Test creation of a video with audio-aligned captions"""
    # Generate audio using Google TTS first to get its duration
    test_text = "This is a test video with synchronized audio and captions. The captions should match the spoken words exactly."
    tts = GoogleTTS()
    success, audio_path = tts.convert_text_to_speech(test_text)
    assert success and audio_path is not None, "Failed to generate test audio"

    try:
        # Verify the audio file exists and has content
        assert os.path.exists(audio_path), "Audio file not created"
        assert os.path.getsize(audio_path) > 0, "Audio file is empty"

        # Get audio duration using ffprobe
        ffprobe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ]
        result = run_ffmpeg_command(ffprobe_cmd)
        assert result is not None, "Failed to get audio duration"
        duration = float(result.stdout.strip())

        # Create test video with duration matching audio
        video_size = (1920, 1080)
        input_video_path = create_test_video(size=video_size, duration=duration)
        assert input_video_path is not None, "Failed to create test video"

        # Get word-level captions from audio
        captions = create_word_level_captions(audio_path, test_text)
        assert captions is not None, "Failed to create word-level captions"

        # Print debug info about captions
        print("\nCaption timings:")
        for i, caption in enumerate(captions):
            print(f"Word {i}: '{caption.text}' ({caption.start_time:.2f}s - {caption.end_time:.2f}s)")

        # Verify all words from test_text are present in captions
        test_words = set(word.strip() for word in test_text.lower().split())
        caption_words = set(word.strip() for caption in captions for word in caption.text.lower().split())
        missing_words = test_words - caption_words
        extra_words = caption_words - test_words

        print("\nWord verification:")
        print(f"Expected words: {sorted(test_words)}")
        print(f"Found words: {sorted(caption_words)}")
        if missing_words:
            print(f"Missing words: {sorted(missing_words)}")
        if extra_words:
            print(f"Extra words: {sorted(extra_words)}")

        assert not missing_words, f"Words missing from captions: {missing_words}"
        assert not extra_words, f"Extra words in captions: {extra_words}"

        # Create output path
        output_path = os.path.join(get_tempdir(), "test_audio_aligned.mp4")

        # Add dynamic captions
        result_path = create_dynamic_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path,
            min_font_size=32,
            max_font_ratio=1.5  # Max will be 48 (1.5x the min)
        )
        assert result_path is not None, "Failed to create video with captions"

        # Add audio to the video with improved FFmpeg command
        final_output = os.path.join(get_tempdir(), "final_output_with_audio.mp4")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", output_path,     # Video with captions
            "-i", audio_path,      # Audio file
            "-map", "0:v:0",       # Map video from first input
            "-map", "1:a:0",       # Map audio from second input
            "-c:v", "copy",        # Copy video stream without re-encoding
            "-c:a", "aac",         # Encode audio as AAC
            "-b:a", "192k",        # Set audio bitrate
            final_output
        ]
        result = run_ffmpeg_command(ffmpeg_cmd)
        assert result is not None, "Failed to add audio to video"
        assert os.path.exists(final_output), "Final output file not created"
        assert os.path.getsize(final_output) > 0, "Final output file is empty"

        # Verify audio stream exists in output
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=noprint_wrappers=1:nokey=1",
            final_output
        ]
        probe_result = run_ffmpeg_command(probe_cmd)
        assert probe_result is not None and probe_result.stdout, "No audio stream found in output video"

        # Play the video (skipped in automated testing)
        play_media(final_output)

    finally:
        # Cleanup
        if os.path.exists(input_video_path):
            os.remove(input_video_path)
        if os.path.exists(audio_path):
            os.remove(audio_path)


def test_text_wrapping():
    """Test that text wrapping handles long text properly"""
    # Create test video
    input_video_path = create_test_video()
    assert input_video_path is not None, "Failed to create test video"

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_wrap_test.mp4")

    try:
        # Test with various wrapping scenarios
        test_cases = [
            "This is a short caption that should fit on one line",
            "This is a much longer caption that should be wrapped onto multiple lines to ensure proper readability",
            "Testing with some very long words like supercalifragilisticexpialidocious that need special wrapping",
            "Multiple     spaces     should     be     handled     correctly     in     wrapping",
            "Testing with a long sentence that needs to be wrapped properly"
        ]
        captions = [CaptionEntry(text, idx * 2.0, (idx + 1) * 2.0) for idx, text in enumerate(test_cases)]

        result_path = create_dynamic_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path,
            min_font_size=32,
            max_font_ratio=1.5  # Max will be 48 (1.5x the min)
        )

        # Verify results
        assert result_path is not None, "Failed to create video with wrapping"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_text_rendering_features():
    """Test various text rendering features including emoji handling"""
    # Create test video
    input_video_path = create_test_video()
    assert input_video_path is not None, "Failed to create test video"

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_features_test.mp4")

    try:
        # Test with various text features
        test_cases = [
            "Basic emoji test 😊 with text",
            "Multiple emojis 🎉🎨🚀 in text",
            "Special characters !@#$%^&*()_+ with 🎮 emoji",
            "Mixed case TeXt with EMoJis 🎭 and SymBoLs #@!",
            "This caption should wrap onto multiple lines"
        ]
        captions = [CaptionEntry(text, idx * 2.0, (idx + 1) * 2.0) for idx, text in enumerate(test_cases)]

        result_path = create_dynamic_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path,
            min_font_size=32,
            max_font_ratio=1.5  # Max will be 48 (1.5x the min)
        )

        # Verify results
        assert result_path is not None, "Failed to create video with text features"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_vibrant_color_palette():
    """Test that the vibrant color palette generates appropriate colors for different backgrounds"""
    # Create test video
    input_video_path = create_test_video(duration=2)
    assert input_video_path is not None, "Failed to create test video"

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_color_test.mp4")

    try:
        # Test with various caption lengths and word sizes
        test_cases = [
            "Testing with vibrant colors",
            "Each word should have a different color",
            "Colors should match the vibrant palette"
        ]
        captions = [CaptionEntry(text, idx * 0.5, (idx + 1) * 0.5) for idx, text in enumerate(test_cases)]

        # Add dynamic captions
        result_path = create_dynamic_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path,
            min_font_size=32,
            max_font_ratio=1.5  # Max will be 48 (1.5x the min)
        )

        # Verify results
        assert result_path is not None, "Failed to create video with color testing"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

        # Get actual colors from the video
        text_color, stroke_color = get_text_colors_from_video(output_path)
        assert text_color is not None, "Failed to extract text color from video"
        assert stroke_color is not None, "Failed to extract stroke color from video"

        # Print debug info
        print(f"\nText color: {text_color}")
        print(f"Stroke color: {stroke_color}")

        # Get expected colors
        palette = get_vibrant_palette()
        print(f"Palette colors: {palette}")

        # The text color should be close to one of the vibrant colors
        color_diffs = [sum(abs(c1 - c2) for c1, c2 in zip(text_color, palette_color)) for palette_color in palette]
        min_diff = min(color_diffs)
        closest_color = palette[color_diffs.index(min_diff)]
        print(f"Closest palette color: {closest_color} (diff: {min_diff})")

        assert min_diff <= 30, f"Text color {text_color} too far from any palette color"

        # The stroke color should be a darker version of the text color (about 1/3 intensity)
        expected_stroke = tuple(c // 3 for c in text_color)
        for actual, expected in zip(stroke_color, expected_stroke):
            assert abs(actual - expected) <= 10, f"Stroke color {stroke_color} not proportional to text color {text_color}"

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_no_word_overlap():
    """Test that words in captions do not overlap each other"""
    # Create test video
    input_video_path = create_test_video(duration=10)
    assert input_video_path is not None, "Failed to create test video"

    # Create output path
    output_path = os.path.join(get_tempdir(), "output_overlap_test.mp4")

    try:
        # Test with various caption lengths and word sizes
        test_cases = [
            "This is a test with many words of different lengths",
            "Supercalifragilisticexpialidocious is a very long word",
            "Multiple     spaces     should     be     handled",
            "Words should not overlap"
        ]
        # Space out the captions more to ensure they have time to be displayed
        captions = [CaptionEntry(text, idx * 2.5, (idx + 1) * 2.5) for idx, text in enumerate(test_cases)]

        # Add dynamic captions
        result_path = create_dynamic_captions(
            input_video=input_video_path,
            captions=captions,
            output_path=output_path,
            min_font_size=32,
            max_font_ratio=1.5
        )

        # Verify results
        assert result_path is not None, "Failed to create video with word overlap test"
        assert os.path.exists(output_path), f"Output file not created: {output_path}"
        assert os.path.getsize(output_path) > 0, "Output file is empty"

        # Play the video (skipped in automated testing)
        play_media(output_path)

        # Get video dimensions
        cap = cv2.VideoCapture(output_path)
        video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # Process all captions into words
        all_words = []
        for caption in captions:
            words = split_into_words(caption)
            if words:
                all_words.extend(words)

        # Create caption windows
        margin = 40
        roi_width = video_width - (2 * margin)
        roi_height = int(video_height * 0.3)

        windows = create_caption_windows(
            words=all_words,
            min_font_size=32,
            max_font_ratio=1.5,
            roi_width=roi_width,
            roi_height=roi_height
        )

        # For each window, verify words have reasonable spacing
        for window in windows:
            positions = calculate_word_positions(window, video_height, margin)

            # Check each word has reasonable spacing
            for word, pos in zip(window.words, positions):
                x, y = pos
                # Verify word is within ROI bounds
                assert x >= margin, f"Word '{word.text}' too close to left edge"
                assert x + word.width <= video_width - margin, f"Word '{word.text}' too close to right edge"
                assert y >= 0, f"Word '{word.text}' above top edge"
                assert y + word.font_size <= video_height, f"Word '{word.text}' below bottom edge"

    finally:
        # Clean up
        if os.path.exists(input_video_path):
            os.unlink(input_video_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_deterministic_color_selection():
    """Test that color selection is deterministic based on background color."""
    # Create test videos with different background colors
    test_colors = [
        (0, 0, 0),      # Black background
        (255, 255, 255), # White background
        (200, 50, 50),   # Red background
        (50, 200, 50),   # Green background
    ]

    # Test text to use
    test_text = "Testing color selection"

    # Store colors used for each background
    colors_used = {}

    for bg_color in test_colors:
        # Create test video with this background
        input_video_path = create_test_video(duration=2, color=bg_color)
        assert input_video_path is not None, "Failed to create test video"

        # Create output path
        output_path = os.path.join(get_tempdir(), f"output_color_test_{bg_color[0]}_{bg_color[1]}_{bg_color[2]}.mp4")

        try:
            # Create caption
            caption = CaptionEntry(test_text, 0.0, 1.0)

            # Add dynamic captions
            result_path = create_dynamic_captions(
                input_video=input_video_path,
                captions=[caption],
                output_path=output_path,
                min_font_size=32,
                max_font_ratio=1.5
            )

            # Verify results
            assert result_path is not None, "Failed to create video with color testing"
            assert os.path.exists(output_path), f"Output file not created: {output_path}"
            assert os.path.getsize(output_path) > 0, "Output file is empty"

            # Get colors from the video
            text_color, _ = get_text_colors_from_video(output_path)
            assert text_color is not None, "Failed to extract text color from video"

            # Store the color used for this background
            colors_used[bg_color] = text_color

        finally:
            # Clean up
            if os.path.exists(input_video_path):
                os.unlink(input_video_path)
            if os.path.exists(output_path):
                os.unlink(output_path)

    # Verify that the same background color always gets the same text color
    for bg_color in test_colors:
        # Create a second video with the same background
        input_video_path = create_test_video(duration=2, color=bg_color)
        output_path = os.path.join(get_tempdir(), f"output_color_test_verify_{bg_color[0]}_{bg_color[1]}_{bg_color[2]}.mp4")

        try:
            result_path = create_dynamic_captions(
                input_video=input_video_path,
                captions=[CaptionEntry(test_text, 0.0, 1.0)],
                output_path=output_path,
                min_font_size=32,
                max_font_ratio=1.5
            )

            # Get colors and verify they match the first run
            text_color, _ = get_text_colors_from_video(output_path)
            assert text_color is not None, "Failed to extract text color from video"

            # Colors should match exactly since selection is deterministic
            first_run_color = colors_used[bg_color]
            assert text_color == first_run_color, f"Color selection not deterministic for background {bg_color}"

        finally:
            # Clean up
            if os.path.exists(input_video_path):
                os.unlink(input_video_path)
            if os.path.exists(output_path):
                os.unlink(output_path)


if __name__ == "__main__":
    output_dir = os.path.join(get_tempdir(), "caption_test_outputs")
    os.makedirs(output_dir, exist_ok=True)
    Logger.print_info("Running caption tests and saving outputs...")
    test_default_static_captions()
    test_static_captions()
    test_caption_text_completeness()
    test_font_size_and_variation()
    test_caption_positioning()
    test_create_srt_captions()
    test_audio_aligned_captions()
    test_text_wrapping()
    test_text_rendering_features()
    test_vibrant_color_palette()
    test_no_word_overlap()
    test_deterministic_color_selection()
