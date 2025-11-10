"""Test helper functions for ganglia-studio tests.

This module provides utility functions for validating TTV pipeline outputs,
including video/audio duration checks, file validation, and output parsing.
"""

import os
import re
import subprocess
import json
from typing import Dict, Optional
from ganglia_common.logger import Logger


def get_audio_duration(audio_file_path: str) -> Optional[float]:
    """Get the duration of an audio file using ffprobe.
    
    Args:
        audio_file_path: Path to the audio file
        
    Returns:
        Duration in seconds, or None if the file is invalid
    """
    if not os.path.exists(audio_file_path):
        Logger.print_error(f"Audio file not found: {audio_file_path}")
        return None
    
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


def get_video_duration(video_file_path: str) -> Optional[float]:
    """Get the duration of a video file using ffprobe.
    
    Args:
        video_file_path: Path to the video file
        
    Returns:
        Duration in seconds, or None if the file is invalid
    """
    if not os.path.exists(video_file_path):
        Logger.print_error(f"Video file not found: {video_file_path}")
        return None
    
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=duration', '-of',
        'default=noprint_wrappers=1:nokey=1', video_file_path
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        if output:
            return float(output)
        # Fallback to format duration
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_file_path
        ]
        output = subprocess.check_output(cmd).decode().strip()
        return float(output)
    except (subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(f"Failed to get video duration: {e}")
        return None


def validate_video_file(video_path: str) -> bool:
    """Validate that a video file exists and is valid.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        True if valid, False otherwise
    """
    if not os.path.exists(video_path):
        Logger.print_error(f"Video file not found: {video_path}")
        return False
    
    # Check file size
    file_size = os.path.getsize(video_path)
    if file_size == 0:
        Logger.print_error(f"Video file is empty: {video_path}")
        return False
    
    # Check if ffprobe can read it
    duration = get_video_duration(video_path)
    if duration is None:
        Logger.print_error(f"Video file is not valid: {video_path}")
        return False
    
    Logger.print_info(f"✓ Valid video file: {video_path} ({duration:.2f}s, {file_size/1024/1024:.2f}MB)")
    return True


def load_config(config_path: str) -> Optional[Dict]:
    """Load a TTV config file.
    
    Args:
        config_path: Path to the config JSON file
        
    Returns:
        Config dictionary, or None if loading fails
    """
    if not os.path.exists(config_path):
        Logger.print_error(f"Config file not found: {config_path}")
        return None
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        Logger.print_error(f"Failed to load config: {e}")
        return None


def count_segments_in_directory(output_dir: str) -> int:
    """Count the number of video segments in a directory.
    
    Args:
        output_dir: Directory to search for segments
        
    Returns:
        Number of segment_*.mp4 files found
    """
    if not os.path.exists(output_dir):
        return 0
    
    segment_files = [f for f in os.listdir(output_dir) 
                    if f.startswith('segment_') and f.endswith('.mp4')]
    return len(segment_files)


def find_final_video(output_dir: str) -> Optional[str]:
    """Find the final video file in a TTV output directory.
    
    Args:
        output_dir: TTV output directory
        
    Returns:
        Path to final video, or None if not found
    """
    if not os.path.exists(output_dir):
        return None
    
    # Look for common final video names
    candidates = [
        'final_video_with_credits.mp4',
        'final_video.mp4',
        'output.mp4'
    ]
    
    for candidate in candidates:
        video_path = os.path.join(output_dir, candidate)
        if os.path.exists(video_path):
            return video_path
    
    return None


def validate_segment_files(output_dir: str, expected_count: int) -> bool:
    """Validate that all expected segment files exist and are valid.
    
    Args:
        output_dir: Directory containing segments
        expected_count: Expected number of segments
        
    Returns:
        True if all segments are valid, False otherwise
    """
    actual_count = count_segments_in_directory(output_dir)
    
    if actual_count != expected_count:
        Logger.print_error(
            f"Expected {expected_count} segments, found {actual_count}"
        )
        return False
    
    # Validate each segment
    for i in range(expected_count):
        segment_path = os.path.join(output_dir, f"segment_{i}.mp4")
        if not validate_video_file(segment_path):
            return False
    
    Logger.print_info(f"✓ All {expected_count} segments are valid")
    return True


def parse_ttv_output_for_dir(output_log: str) -> Optional[str]:
    """Parse TTV output log to extract the output directory.
    
    Args:
        output_log: The TTV command output/log
        
    Returns:
        Path to TTV output directory, or None if not found
    """
    # Look for directory creation messages
    patterns = [
        r"TTV directory created: (.+)",
        r"📁 TTV directory created: (.+)",
        r"Output directory: (.+)",
        r"Saving.*to: (.+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, output_log)
        if match:
            return match.group(1).strip()
    
    return None


def create_test_config(output_path: str, story_sentences: list, 
                       style: str = "digital art",
                       include_music: bool = True) -> str:
    """Create a test TTV config file.
    
    Args:
        output_path: Where to save the config
        story_sentences: List of story sentences
        style: Visual style for image generation
        include_music: Whether to include background music config
        
    Returns:
        Path to the created config file
    """
    config = {
        "style": style,
        "story": story_sentences,
        "title": "Test Video",
        "caption_style": "dynamic",
        "closing_credits": {
            "file": None,
            "prompt": None
        }
    }
    
    if include_music:
        config["background_music"] = {
            "file": None,
            "prompt": "upbeat electronic music"
        }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    return output_path

