"""Module for determining optimal Region of Interest (ROI) for video captions.

The ROI should be:
1. Located in a low-activity area of the frame
2. Taller than it is wide (portrait orientation)
3. Approximately 1/5th to 1/10th of the frame size
4. Positioned to minimize interference with main video content

Note: Current implementation analyzes only the first frame.
TODO: Expand to analyze multiple frames for true video content.
"""

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


def _crop_frame_with_buffer(frame: np.ndarray, buffer_ratio: float = 0.05):
    """Crop frame by buffer ratio and return cropped frame with buffers."""
    height, width = frame.shape[:2]
    buffer_x = int(width * buffer_ratio)
    buffer_y = int(height * buffer_ratio)
    cropped_frame = frame[buffer_y : height - buffer_y, buffer_x : width - buffer_x]
    return cropped_frame, buffer_x, buffer_y


def _compute_borders(cropped_frame: np.ndarray, border_ratio: float = 0.1) -> tuple[int, int]:
    """Compute border offsets for cropped frame."""
    border_x = int(cropped_frame.shape[1] * border_ratio)
    border_y = int(cropped_frame.shape[0] * border_ratio)
    return border_x, border_y


def _calculate_roi_dimensions(cropped_frame, border_x, border_y):
    """Calculate ROI width/height ensuring portrait orientation."""
    available_width = cropped_frame.shape[1] - 2 * border_x
    available_height = cropped_frame.shape[0] - 2 * border_y
    target_area = (available_width * available_height) / 7
    roi_width = int(np.sqrt(target_area / 1.5))
    roi_height = int(roi_width * 1.5)
    return min(roi_width, available_width), min(roi_height, available_height)


def _locate_roi_position(cropped_frame, border_x, border_y, roi_width, roi_height, block_size):
    """Locate ROI position based on activity map."""
    activity_map = calculate_activity_map(cropped_frame, block_size)
    blocks_h = cropped_frame.shape[0] // block_size
    blocks_w = cropped_frame.shape[1] // block_size
    is_uniform = np.std(activity_map) < 0.01

    if is_uniform:
        return (
            (cropped_frame.shape[1] - roi_width) // 2,
            (cropped_frame.shape[0] - roi_height) // 2,
        )

    valid_y = cropped_frame.shape[0] - roi_height - 2 * border_y
    valid_x = cropped_frame.shape[1] - roi_width - 2 * border_x
    min_activity = float("inf")
    best_x = border_x
    best_y = border_y

    for y in range(border_y, valid_y + 1, block_size):
        for x in range(border_x, valid_x + 1, block_size):
            block_y = y // block_size
            block_x = x // block_size
            if (
                block_y + (roi_height // block_size) > blocks_h
                or block_x + (roi_width // block_size) > blocks_w
            ):
                continue

            activity = np.mean(
                activity_map[
                    block_y : block_y + (roi_height // block_size),
                    block_x : block_x + (roi_width // block_size),
                ]
            )
            if activity < min_activity:
                min_activity = activity
                best_x = x
                best_y = y

    return best_x, best_y


def find_roi_in_frame(frame, block_size=32):
    """Find optimal ROI in a single frame."""
    cropped_frame, buffer_x, buffer_y = _crop_frame_with_buffer(frame)
    border_x, border_y = _compute_borders(cropped_frame)
    roi_width, roi_height = _calculate_roi_dimensions(cropped_frame, border_x, border_y)
    best_x, best_y = _locate_roi_position(
        cropped_frame, border_x, border_y, roi_width, roi_height, block_size
    )
    return (best_x + buffer_x, best_y + buffer_y, roi_width, roi_height)


def find_optimal_roi(video_path: str, block_size: int = 32) -> tuple[int, int, int, int] | None:
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

        return find_roi_in_frame(frame=first_frame, block_size=block_size)

    except Exception as e:
        print(f"Error finding optimal ROI: {str(e)}")
        return None
