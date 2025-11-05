"""Video generation module for text-to-video conversion.

This module provides functionality for:
- Creating video segments from images and audio
- Adding fade effects to still images
- Concatenating multiple video segments
- Managing subprocess operations safely with locks
"""

import os
import subprocess
import threading
from typing import List, Optional

from ganglia_common.logger import Logger
from utils import ffmpeg_thread_manager
from .audio_generation import get_audio_duration

# Lock for subprocess operations to avoid gRPC fork handler issues
subprocess_lock = threading.Lock()

def create_video_segment(image_path, audio_path, output_path, thread_id=None):
    """Create a video segment from an image and audio file.

    Args:
        image_path: Path to the image file
        audio_path: Path to the audio file
        output_path: Path to save the output video
        thread_id: Optional thread ID for logging

    Returns:
        str: Path to the output video if successful, None otherwise
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    try:
        # Get audio duration
        duration = get_audio_duration(audio_path)
        if duration is None:
            Logger.print_error(f"{thread_prefix}Failed to get audio duration")
            return None
        Logger.print_info(f"{thread_prefix}Got audio duration: {duration}s for {audio_path}")

        # Create video segment using thread manager
        with ffmpeg_thread_manager:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", image_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-t", str(duration),  # Explicit duration is sufficient
                output_path
            ]
            with subprocess_lock:  # Protect subprocess.run from gRPC fork issues
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True
                )

        if result.returncode != 0:
            Logger.print_error(f"{thread_prefix}Failed to create video segment: {result.stderr.decode()}")
            return None

        Logger.print_info(f"{thread_prefix}Successfully created video segment at {output_path}")
        return output_path

    except (subprocess.CalledProcessError, OSError) as e:
        Logger.print_error(f"{thread_prefix}Error creating video segment: {str(e)}")
        return None

def create_still_video_with_fade(image_path, audio_path, output_path, thread_id=None):
    """Create a still video with fade effects.

    Args:
        image_path: Path to the image file
        audio_path: Path to the audio file
        output_path: Path to save the output video
        thread_id: Optional thread ID for logging

    Returns:
        str: Path to the output video if successful, None otherwise
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    try:
        # Get audio duration
        duration = get_audio_duration(audio_path)
        if duration is None:
            Logger.print_error(f"{thread_prefix}Failed to get audio duration")
            return None

        # Create video with fade using thread manager
        with ffmpeg_thread_manager:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", image_path,
                "-i", audio_path,
                "-vf", "fade=t=out:st=25:d=5",
                "-af", f"adelay=3000|3000,afade=t=in:ss=0:d=3,afade=t=out:st={duration}:d=5",
                "-t", str(duration + 4),  # Add 4 seconds for fade effects
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                output_path
            ]
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True
            )

        if result.returncode != 0:
            Logger.print_error(f"{thread_prefix}Failed to create video with fade: {result.stderr.decode()}")
            return None

        Logger.print_info(f"{thread_prefix}Successfully created video with fade at {output_path}")
        return output_path

    except (subprocess.CalledProcessError, OSError) as e:
        Logger.print_error(f"{thread_prefix}Error creating video with fade: {str(e)}")
        return None

def append_video_segments(
    video_segments: List[str],
    thread_id: Optional[str] = None,
    output_dir: str = None,
    force_reencode: bool = False
) -> Optional[str]:
    """Append multiple video segments together.

    Args:
        video_segments: List of video segment paths
        thread_id: Optional thread ID for logging
        output_dir: Optional directory for output files
        force_reencode: Whether to force re-encoding of streams (needed for closing credits)

    Returns:
        str: Path to the output video if successful, None otherwise
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    try:
        # Create output path
        output_path = os.path.join(output_dir, "concatenated_video.mp4")

        # Create concat file with absolute paths
        concat_list_path = os.path.join(output_dir, "concat_list.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for segment in video_segments:
                abs_path = os.path.abspath(segment)
                f.write(f"file '{abs_path}'\n")

        # Concatenate segments using thread manager
        with ffmpeg_thread_manager:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path
            ]

            if force_reencode:
                # Re-encode both video and audio streams
                cmd.extend([
                    "-c:v", "libx264",  # Re-encode video
                    "-c:a", "aac",      # Re-encode audio
                    "-b:a", "192k"      # Set audio bitrate
                ])
            else:
                # Just copy streams without re-encoding
                cmd.extend(["-c", "copy"])

            cmd.append(output_path)

            with subprocess_lock:  # Protect subprocess.run from gRPC fork issues
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True
                )

        if result.returncode != 0:
            Logger.print_error(f"{thread_prefix}Failed to concatenate segments: {result.stderr.decode()}")
            return None

        Logger.print_info(f"{thread_prefix}Successfully appended video segments to {output_path}")
        return output_path

    except (subprocess.CalledProcessError, OSError) as e:
        Logger.print_error(f"{thread_prefix}Error appending video segments: {str(e)}")
        return None
    finally:
        # Cleanup temporary files
        try:
            if os.path.exists(concat_list_path):
                os.remove(concat_list_path)
        except (OSError, UnboundLocalError):
            pass
