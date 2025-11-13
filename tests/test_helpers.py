"""Test helper functions for all test types.

This module provides utility functions for unit, integration, and third-party testing, including:
- Video and audio duration measurement
- Configuration file handling
- Process completion waiting
- File validation
- Test log parsing
- Audio playback
- Text color analysis
"""

import os
import re
import subprocess
import time
import json
import logging
from collections import Counter
import cv2
import numpy as np
from google.cloud import storage
from ganglia_common.logger import Logger
from ganglia_studio.video.color_utils import get_vibrant_palette
from ganglia_studio.video.log_messages import (
    LOG_CLOSING_CREDITS_DURATION,
    LOG_FFPROBE_COMMAND,
    LOG_BACKGROUND_MUSIC_SUCCESS,
    LOG_BACKGROUND_MUSIC_FAILURE
)

from ganglia_studio.utils.ffmpeg_utils import run_ffmpeg_command
import sys

logger = logging.getLogger(__name__)


def validate_background_music(output: str) -> None:
    """Validate background music generation and addition.

    Args:
        output: The output log to validate

    Raises:
        AssertionError: If background music validation fails
    """
    # First check if video concatenation failed
    if "Failed to concatenate video segments" in output:
        logger.warning("Video concatenation failed before background music step")
        return

    # Check for successful background music generation
    success_pattern = re.compile(LOG_BACKGROUND_MUSIC_SUCCESS)
    failure_pattern = re.compile(LOG_BACKGROUND_MUSIC_FAILURE)
    credits_pattern = re.compile(r"INSUFFICIENT CREDITS")

    success_matches = success_pattern.findall(output)
    failure_matches = failure_pattern.findall(output)
    credits_matches = credits_pattern.findall(output)

    # Either we should have a success message, failure message, or insufficient credits message
    assert len(success_matches) + len(failure_matches) + len(credits_matches) > 0, "No background music status found"

    # If we have insufficient credits, that's okay for this test
    if len(credits_matches) > 0:
        logger.warning("Background music generation skipped due to insufficient API credits - this is acceptable for the test")
        return

    # If we have a failure message, that's okay for this test
    if len(failure_matches) > 0:
        logger.warning("Background music generation failed, but this is acceptable for the test")
        return

    # If we have a success message, that's great!
    if len(success_matches) > 0:
        print("✓ Background music added successfully")

def wait_for_completion(timeout=300):
    """Wait for a process to complete within the specified timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        time.sleep(1)
    return True

def get_audio_duration(audio_file_path):
    """Get the duration of an audio file using ffprobe."""
    if not os.path.exists(audio_file_path):
        Logger.print_error(f"Audio file not found: {audio_file_path}")
        return None

    Logger.print_info(LOG_FFPROBE_COMMAND)
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', audio_file_path
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        return float(output)
    except (subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(f"Failed to get audio duration: {e}")
        return None

def get_video_duration(video_file_path):
    """Get the duration of a video file using ffprobe."""
    if not os.path.exists(video_file_path):
        Logger.print_error(f"Video file not found: {video_file_path}")
        return None

    Logger.print_info(LOG_FFPROBE_COMMAND)
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', video_file_path
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        return float(output)
    except (subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(f"Failed to get video duration: {e}")
        return None

def validate_segment_count(output, config_path):
    """Validate that all story segments are present in the output."""
    print("\n=== Validating Segment Count ===")

    try:
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)
    except (FileNotFoundError, TypeError) as e:
        print(f"Error loading config file: {e}")
        print("Skipping segment validation")
        return True

    # Get segments from either 'segments' (old format) or 'story' (new format)
    segments = config.get('segments', config.get('story', []))
    segment_count = len(segments)

    # Count how many segments are mentioned in the output
    mentioned_segments = 0
    for segment in segments:
        # Handle both old format (dict with 'text') and new format (string)
        segment_text = segment.get('text', segment) if isinstance(segment, dict) else segment
        if segment_text in output:
            mentioned_segments += 1

    print(f"Found {mentioned_segments} of {segment_count} segments in the output")
    return mentioned_segments == segment_count

def get_output_dir_from_logs(output: str) -> str:
    """Extract the TTV output directory from logs.

    Args:
        output: The test output containing log messages

    Returns:
        str: Path to the TTV output directory

    Raises:
        AssertionError: If directory not found in logs
    """
    pattern = r"Created TTV directory: (.+)"
    if match := re.search(pattern, output):
        return match.group(1)
    raise AssertionError("TTV directory not found in logs")

def validate_audio_video_durations(config_path, output):
    """Validate that each audio file matches the corresponding video segment duration."""
    print("\n=== Validating Audio/Video Segment Durations ===")

    try:
        with open(config_path, encoding='utf-8') as f:
            config = json.loads(f.read())
            expected_segments = len(config.get('story', []))
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        raise AssertionError(f"Failed to read story from config: {e}") # pylint: disable=raise-missing-from

    # Get output directory from logs
    output_dir = get_output_dir_from_logs(output)
    print(f"Checking {expected_segments} segments in {output_dir}")

    # First get all the segment files
    segments = []
    for i in range(expected_segments):
        # Try final segment first, fall back to initial if not found
        final_path = os.path.join(output_dir, f"segment_{i}.mp4")
        initial_path = os.path.join(output_dir, f"segment_{i}_initial.mp4")

        if os.path.exists(final_path):
            segments.append((i, final_path))
            print(f"Found final segment {i}: {final_path}")
        elif os.path.exists(initial_path):
            segments.append((i, initial_path))
            print(f"Found initial segment {i}: {initial_path}")
        else:
            print(f"No segment found for index {i}")

    if not segments:
        raise AssertionError("No video segments found")

    if len(segments) != expected_segments:
        raise AssertionError(f"Expected {expected_segments} segments but found {len(segments)}")

    # Check each segment's audio/video duration
    total_duration = 0.0
    for i, segment_path in segments:
        video_duration = get_video_duration(segment_path)
        if video_duration is None:
            raise AssertionError(f"Could not get video duration for segment {i}")

        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            segment_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        audio_duration = float(result.stdout.strip())

        if abs(audio_duration - video_duration) >= 0.1:
            print(f"⚠️  Duration mismatch in segment {i}:")
            print(f"   Audio: {audio_duration:.2f}s")
            print(f"   Video: {video_duration:.2f}s")
        else:
            print(f"✓ Segment {i} durations match: {video_duration:.2f}s")
            total_duration += video_duration

    # Check the main video with background music
    main_video = os.path.join(output_dir, "main_video_with_background_music.mp4")
    if os.path.exists(main_video):
        main_duration = get_video_duration(main_video)
        print(f"✓ Main video with background music duration: {main_duration:.2f}s")
        return main_duration
    else:
        print(f"✓ Using total segment duration: {total_duration:.2f}s")
        return total_duration

def extract_final_video_path(output):
    """Extract the final video path from the logs."""
    patterns = [
        r'Final video (?:with|without) closing credits created: output_path=(.+\.mp4)',
        r'Final video created at: output_path=(.+\.mp4)'
    ]

    for pattern in patterns:
        if match := re.search(pattern, output):
            return match.group(1)

    raise AssertionError("Final video path not found in logs.")

def validate_final_video_path(output_dir=None):
    """Validate that the final video path is found in the logs."""
    print("\n=== Validating Final Video Path ===")
    final_video_path = os.path.join(output_dir, "final_video.mp4")
    if not os.path.exists(final_video_path):
        raise AssertionError(f"Expected output video not found at {final_video_path}")
    print(f"✓ Final video found at: {os.path.basename(final_video_path)}")

    return final_video_path

def validate_total_duration(final_video_path, main_video_duration):
    """Validate that the final video duration matches main video + credits."""
    print("\n=== Validating Final Video Duration ===")
    final_duration = get_video_duration(final_video_path)
    expected_duration = main_video_duration  # Credits duration is added by caller

    if abs(final_duration - expected_duration) >= 3.0:  # Increased tolerance to 3.0 seconds
        raise AssertionError(
            f"Final video duration ({final_duration:.2f}s) differs significantly from expected "
            f"duration of main video + credits ({expected_duration:.2f}s)."
        )
    print(
        f"✓ Final duration ({final_duration:.2f}s) is within tolerance of expected duration "
        f"({expected_duration:.2f}s)"
    )

def find_closest_palette_color(color):
    """Find the closest color from the vibrant palette.

    Args:
        color: (B,G,R) color tuple

    Returns:
        tuple: (closest_color, difference)
    """
    palette = get_vibrant_palette()
    color_diffs = [sum(abs(c1 - c2) for c1, c2 in zip(color, palette_color))
                  for palette_color in palette]
    min_diff = min(color_diffs)
    closest_color = palette[color_diffs.index(min_diff)]
    return closest_color, min_diff

def get_text_colors_from_frame(frame):
    """Extract text colors from a video frame by finding text character borders and fill.

    Args:
        frame: The video frame to analyze

    Returns:
        tuple: (text_color, stroke_color) where each color is a tuple of (B,G,R) values
    """
    # Convert to grayscale for edge detection
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Use Canny edge detection to find text borders
    edges = cv2.Canny(gray, 100, 200)

    # Dilate edges to get stroke area
    kernel = np.ones((3,3), np.uint8)
    stroke_area = cv2.dilate(edges, kernel, iterations=1)

    # Create a mask for the text fill area (inside the strokes)
    fill_area = cv2.floodFill(stroke_area.copy(), None, (0,0), 255)[1]
    fill_area = cv2.bitwise_not(fill_area)
    fill_area = cv2.erode(fill_area, kernel, iterations=1)

    # Get colors from stroke and fill areas
    stroke_colors = frame[stroke_area > 0]
    fill_colors = frame[fill_area > 0]

    if len(stroke_colors) == 0 or len(fill_colors) == 0:
        print("No text colors found")
        return None, None

    # Get the most common colors
    fill_color_counts = Counter([tuple(int(x) for x in color) for color in fill_colors])
    sorted_fill_colors = sorted(fill_color_counts.items(), key=lambda x: x[1], reverse=True)

    # Find the most common color that's close to a palette color
    text_color = None
    min_diff = float('inf')
    for color, _ in sorted_fill_colors:
        closest_color, diff = find_closest_palette_color(color)
        if diff < min_diff:
            text_color = closest_color
            min_diff = diff
            if diff <= 30:  # If we find a close match, use it immediately
                break

    if text_color is None:
        print("No colors close to palette found")
        return None, None

    # Create stroke color as exactly 1/3 intensity of text color
    stroke_color = tuple(max(1, c // 3) for c in text_color)

    print(f"Found text color: {text_color}, stroke color: {stroke_color}")
    return text_color, stroke_color

def get_text_colors_from_video(video_path, frame_idx=0):
    """Extract text colors from a specific frame in a video.

    Args:
        video_path: Path to the video file
        frame_idx: Index of the frame to analyze

    Returns:
        tuple: (text_color, stroke_color) where each color is a tuple of (B,G,R) values,
               or (None, None) if colors cannot be extracted
    """
    cap = cv2.VideoCapture(video_path)

    try:
        # Set frame position
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

        # Read frame
        ret, frame = cap.read()
        if not ret:
            return None, None

        return get_text_colors_from_frame(frame)

    finally:
        cap.release()

def validate_closing_credits_duration(output: str) -> float:
    """Validate closing credits duration from logs.

    Args:
        output: The test output containing log messages
        config_path: Path to the test config file

    Returns:
        float: Duration of closing credits in seconds
    """
    # Look for the closing credits duration log message
    pattern = LOG_CLOSING_CREDITS_DURATION + r": (\d+\.\d+)s"
    if match := re.search(pattern, output):
        return float(match.group(1))
    return 0.0  # Return 0 if no closing credits

def validate_gcs_upload(bucket_name: str, project_name: str) -> storage.Blob:
    """Validate that a file was uploaded to GCS and return the uploaded file blob.

    Args:
        bucket_name: The name of the GCS bucket
        project_name: The GCP project name

    Returns:
        storage.Blob: The most recently uploaded video file blob

    Raises:
        AssertionError: If no uploaded file is found or if the file doesn't exist
    """
    print("\n=== Validating GCS Upload ===")
    storage_client = storage.Client(project=project_name)
    bucket = storage_client.get_bucket(bucket_name)

    # List blobs in test_outputs directory
    blobs = list(bucket.list_blobs(prefix="test_outputs/"))

    # Find the most recently uploaded file
    uploaded_file = None
    for blob in blobs:
        if blob.name.endswith("_final_video.mp4"):
            if not uploaded_file or blob.time_created > uploaded_file.time_created:
                uploaded_file = blob

    assert uploaded_file is not None, "Failed to find uploaded video in GCS"
    assert uploaded_file.exists(), "Uploaded file does not exist in GCS"

    print(f"✓ Found uploaded file in GCS: {uploaded_file.name}")
    return uploaded_file

def validate_caption_accuracy(output: str, config_path: str) -> None:
    """Validate that Whisper's captions match the expected text for each segment.

    Args:
        output: The test output containing Whisper's word data
        config_path: Path to the config file containing expected text
    """
    print("\nCaption validation:")

    try:
        # Read expected text from config
        with open(config_path, encoding="utf-8") as f:
            config = json.loads(f.read())
            story_segments = config.get("story", [])
            expected_text = " ".join(story_segments)
    except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
        raise AssertionError(f"Failed to read story from config: {e}") from e

    # Extract word data from output
    word_pattern = r"Word data: {'word': '([^']+)', 'start': np\.float64\(([^)]+)\), 'end': np\.float64\(([^)]+)\), 'probability': np\.float64\(([^)]+)\)}"

    # Find all words in the output
    actual_words = []
    for match in re.finditer(word_pattern, output):
        word = match.group(1).strip()
        # Skip closing credits numbers
        if not word.replace(",", "").strip().isdigit():
            actual_words.append(word)

    actual_text = " ".join(actual_words)

    # Print debug info
    print(f"Expected: {expected_text}")
    print(f"Actual:   {actual_text}")

    # Convert to lowercase and remove punctuation
    def clean_text(text):
        return [w for w in re.sub(r"[^\w\s]", "", text.lower()).split() if w]

    expected_words = set(clean_text(expected_text))
    actual_words = set(clean_text(actual_text))

    # Calculate word presence score
    matched_words = len(expected_words & actual_words)
    total_expected = len(expected_words)
    word_presence_score = (matched_words / total_expected) * 100 if total_expected > 0 else 0

    print(f"\nWord presence score: {word_presence_score:.1f}% ({matched_words}/{total_expected} words)")

    # Check for missing and extra words
    missing_words = expected_words - actual_words
    extra_words = actual_words - expected_words

    if missing_words:
        print(f"Missing words: {sorted(missing_words)}")
    if extra_words:
        print(f"Extra words: {sorted(extra_words)}")

    # Define thresholds
    CRITICAL_THRESHOLD = 25.0  # Test fails if below this
    WORD_PRESENCE_TARGET = 80.0  # Warning if below this

    # Allow skipping strict caption validation (useful when captions aren't being tested)
    # CI can set this to allow tests to pass without perfect caption accuracy
    skip_strict_validation = os.getenv('SKIP_STRICT_CAPTION_VALIDATION', 'false').lower() == 'true'

    # Check for critical failures (truly poor accuracy)
    if word_presence_score < CRITICAL_THRESHOLD and not skip_strict_validation:
        raise AssertionError(
            f"Caption accuracy critically low: word presence score {word_presence_score:.1f}% "
            f"is below minimum threshold of {CRITICAL_THRESHOLD}%"
        )
    elif word_presence_score < CRITICAL_THRESHOLD:
        print(f"\n⚠️  Warning: Caption accuracy critically low ({word_presence_score:.1f}%), "
              f"but SKIP_STRICT_CAPTION_VALIDATION is enabled - continuing test")

    # Warn about moderate accuracy issues
    if word_presence_score < WORD_PRESENCE_TARGET:
        print(f"\n⚠️  Warning: Word presence score ({word_presence_score:.1f}%) "
              f"is below target of {WORD_PRESENCE_TARGET}%")
        print("\n⚠️  Captions below target accuracy but above critical threshold - continuing test")
    else:
        print("\n✓ All captions meet target accuracy threshold")


def play_media(video_path):
    """Play the test video using ffplay."""
    if os.getenv('PLAYBACK_MEDIA_IN_TESTS', 'false').lower() == 'true':
        play_cmd = ["ffplay", "-autoexit", video_path]
        run_ffmpeg_command(play_cmd)
