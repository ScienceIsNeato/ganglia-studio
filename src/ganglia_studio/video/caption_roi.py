"""Module for determining optimal Region of Interest (ROI) for video captions.

The ROI should be:
1. Located in a low-activity area of the frame
2. Taller than it is wide (portrait orientation)
3. Approximately 1/5th to 1/10th of the frame size
4. Positioned to minimize interference with main video content

Note: Current implementation analyzes only the first frame.
TODO: Expand to analyze multiple frames for true video content.
"""

from typing import Optional, Tuple
import numpy as np
from moviepy.video.io.VideoFileClip import VideoFileClip

def calculate_activity_map(frame: np.ndarray, block_size: int = 32) -> np.ndarray:
    """Calculate activity level for each block in the frame.

    Uses standard deviation of pixel values as a simple measure of activity.
    Lower values indicate less activity/movement.

    Args:
        frame: Image/video frame as numpy array (height, width, channels)
        block_size: Size of blocks to analyze

    Returns:
        2D numpy array of activity levels
    """
    height, width = frame.shape[:2]
    gray = np.mean(frame, axis=2)  # Convert to grayscale

    # Calculate number of blocks in each dimension
    blocks_h = height // block_size
    blocks_w = width // block_size

    # Initialize activity map
    activity_map = np.zeros((blocks_h, blocks_w))

    # Calculate standard deviation for each block
    for i in range(blocks_h):
        for j in range(blocks_w):
            h_start = i * block_size
            h_end = (i + 1) * block_size
            w_start = j * block_size
            w_end = (j + 1) * block_size

            block = gray[h_start:h_end, w_start:w_end]
            activity_map[i, j] = np.std(block)

    return activity_map

def find_roi_in_frame(frame, block_size=32):
    """Find optimal ROI in a single frame."""
    height, width = frame.shape[:2]

    # Calculate 5% buffer size
    buffer_x = int(width * 0.05)
    buffer_y = int(height * 0.05)

    # Create a new frame with the buffer cut off
    cropped_frame = frame[buffer_y:height-buffer_y, buffer_x:width-buffer_x]

    # Calculate 10% border size
    border_x = int(cropped_frame.shape[1] * 0.1)
    border_y = int(cropped_frame.shape[0] * 0.1)

    # Calculate target ROI area (aim for 1/7th of frame area as a middle ground)
    target_area = ((cropped_frame.shape[1] - 2 * border_x) * (cropped_frame.shape[0] - 2 * border_y)) / 7

    # Calculate ROI dimensions to achieve target area while being taller than wide
    # Make height 1.5 times the width to ensure portrait orientation
    roi_width = int(np.sqrt(target_area / 1.5))
    roi_height = int(roi_width * 1.5)

    # Ensure dimensions don't exceed frame
    roi_width = min(roi_width, cropped_frame.shape[1] - 2 * border_x)
    roi_height = min(roi_height, cropped_frame.shape[0] - 2 * border_y)

    # Calculate activity map
    activity_map = calculate_activity_map(cropped_frame, block_size)

    # Find position with minimum activity
    valid_y = cropped_frame.shape[0] - roi_height - 2 * border_y
    valid_x = cropped_frame.shape[1] - roi_width - 2 * border_x

    min_activity = float('inf')
    best_x = border_x
    best_y = border_y

    # Convert block coordinates to pixel coordinates
    blocks_h = cropped_frame.shape[0] // block_size
    blocks_w = cropped_frame.shape[1] // block_size

    for y in range(border_y, valid_y + 1, block_size):
        for x in range(border_x, valid_x + 1, block_size):
            # Convert pixel coordinates to block coordinates
            block_y = y // block_size
            block_x = x // block_size

            # Ensure we don't exceed activity map bounds
            if block_y + (roi_height // block_size) > blocks_h or block_x + (roi_width // block_size) > blocks_w:
                continue

            # Get activity for this region
            region = activity_map[block_y:block_y+(roi_height // block_size),
                                block_x:block_x+(roi_width // block_size)]
            activity = np.mean(region)  # Use mean instead of sum for better scaling

            if activity < min_activity:
                min_activity = activity
                best_x = x
                best_y = y

    # Adjust best_x and best_y to account for the initial buffer
    best_x += buffer_x
    best_y += buffer_y

    return (best_x, best_y, roi_width, roi_height)

def find_optimal_roi(
    video_path: str,
    block_size: int = 32
) -> Optional[Tuple[int, int, int, int]]:
    """Find optimal ROI for captions in a video.

    Currently only analyzes the first frame.
    TODO: Expand to analyze multiple frames for true video content.

    Args:
        video_path: Path to video file
        block_size: Size of blocks for activity analysis

    Returns:
        Tuple of (x, y, width, height) defining the ROI rectangle,
        or None if analysis fails
    """
    try:
        video = VideoFileClip(video_path)
        first_frame = video.get_frame(0)
        video.close()

        return find_roi_in_frame(
            frame=first_frame,
            block_size=block_size
        )

    except Exception as e:
        print(f"Error finding optimal ROI: {str(e)}")
        return None
