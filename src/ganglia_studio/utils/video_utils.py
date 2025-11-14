"""Video generation and manipulation utilities."""

# pylint: disable=no-member
import os
import random
import tempfile
import cv2
import numpy as np
from PIL import Image
from ganglia_studio.utils.ffmpeg_utils import run_ffmpeg_command

def create_test_video(duration=5, size=(1920, 1080), color=None):
    """Create a simple colored background video with a silent audio track"""
    # Generate random color if none provided
    if color is None:
        # Generate vibrant colors by ensuring at least one channel is high
        channels = [random.randint(0, 255) for _ in range(3)]
        max_channel = max(channels)
        if max_channel < 128:  # If all channels are too dark
            boost_channel = random.randint(0, 2)  # Choose a random channel to boost
            channels[boost_channel] = random.randint(128, 255)  # Make it brighter
        color = tuple(channels)

    # Create a colored image using PIL
    image = Image.new('RGB', size, color)
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as img_file:
        image.save(img_file.name)

        # First create video with silent audio
        video_path = img_file.name.replace('.png', '.mp4')

        # Create video with silent audio track
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img_file.name,
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-c:v", "libx264", "-t", str(duration),
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", video_path
        ]
        result = run_ffmpeg_command(ffmpeg_cmd)
        if result is None:
            return None

        # Clean up temporary files
        os.unlink(img_file.name)
        return video_path

def create_moving_rectangle_video(output_path: str, duration_seconds: int = 5):
    """Create a test video with a moving white rectangle on black background.

    Args:
        output_path: Path where the video should be saved
        duration_seconds: Duration of the video in seconds
    """
    # Video settings
    fps = 30
    frame_width = 640
    frame_height = 480

    # Create video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height))

    try:
        # Create frames
        for i in range(fps * duration_seconds):
            # Create a black frame
            frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

            # Draw a moving white rectangle
            x = int((i / (fps * duration_seconds)) * (frame_width - 100))
            cv2.rectangle(frame, (x, 190), (x + 100, 290), (255, 255, 255), -1)

            # Add frame number text
            cv2.putText(
                frame,
                f'Frame {i}/{fps * duration_seconds}',
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 255),
                2
            )

            out.write(frame)
    finally:
        out.release()
