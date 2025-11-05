"""FFmpeg encoding constants for consistent video/audio settings.

This module defines standard encoding parameters used across all FFmpeg operations
to ensure consistent output quality and format compatibility.
"""

# Video settings
VIDEO_CODEC = "libx264"
VIDEO_TUNE = "stillimage"  # For image-based videos
VIDEO_PIXEL_FORMAT = "yuv420p"
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080

# Audio settings
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"
AUDIO_SAMPLE_RATE = "48000"  # 48kHz
AUDIO_CHANNELS = "2"  # Stereo

# Common FFmpeg arguments that can be extended() into command lists
VIDEO_ENCODING_ARGS = [
    "-c:v", VIDEO_CODEC,
    "-pix_fmt", VIDEO_PIXEL_FORMAT
]

AUDIO_ENCODING_ARGS = [
    "-c:a", AUDIO_CODEC,
    "-b:a", AUDIO_BITRATE,
    "-ar", AUDIO_SAMPLE_RATE,
    "-ac", AUDIO_CHANNELS
]

# For image-based videos (like our segments)
SLIDESHOW_VIDEO_ARGS = [
    "-c:v", VIDEO_CODEC,
    "-tune", VIDEO_TUNE,
    "-pix_fmt", VIDEO_PIXEL_FORMAT
]
