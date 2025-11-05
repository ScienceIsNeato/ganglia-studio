"""Color utilities for video caption generation.

This module provides functionality for:
1. Generating vibrant color palettes
2. Calculating complementary colors
3. Mixing colors
4. Finding optimal text colors for contrast
"""

from colorsys import rgb_to_hsv, hsv_to_rgb
from typing import Tuple, List

import numpy as np

def get_vibrant_palette() -> List[Tuple[int, int, int]]:
    """Get a list of vibrant colors for captions.

    Returns:
        List[Tuple[int, int, int]]: List of RGB color tuples
    """
    return [
        (240, 46, 230),   # Hot Pink
        (157, 245, 157),  # Lime Green
        (52, 235, 222),   # Cyan
        (247, 158, 69),   # Bright Orange
        (247, 247, 17),   # Hot Yellow
        (167, 96, 247)    # Royal Purple
    ]

def get_color_complement(color: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """
    Calculate the complement of a color using HSV color space for better results.

    Args:
        color: RGB color tuple

    Returns:
        RGB color tuple of the complement
    """
    # Convert RGB to HSV
    r, g, b = [x/255.0 for x in color]
    h, s, v = rgb_to_hsv(r, g, b)

    # Calculate complement by shifting hue by 180 degrees
    h = (h + 0.5) % 1.0

    # Convert back to RGB
    r, g, b = hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

def mix_colors(color1: Tuple[int, int, int], color2: Tuple[int, int, int], ratio: float = 0.8) -> Tuple[int, int, int]:
    """
    Mix two colors with a given ratio.

    Args:
        color1: First RGB color tuple (primary color)
        color2: Second RGB color tuple (secondary color)
        ratio: Weight of the first color (0.0 to 1.0)

    Returns:
        RGB color tuple of the mixed color
    """
    r = int(color1[0] * ratio + color2[0] * (1 - ratio))
    g = int(color1[1] * ratio + color2[1] * (1 - ratio))
    b = int(color1[2] * ratio + color2[2] * (1 - ratio))
    return (r, g, b)

def get_contrasting_color(frame: np.ndarray, roi: Tuple[int, int, int, int]) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """
    Determine contrasting text color and stroke color based on ROI background.
    For dark backgrounds, returns light colors and vice versa.

    Args:
        frame: Video frame as numpy array
        roi: Tuple of (x, y, width, height) defining the ROI

    Returns:
        Tuple of (text_color, stroke_color) as RGB tuples
    """
    x, y, width, height = roi
    roi_region = frame[y:y+height, x:x+width]

    # Calculate average color in ROI
    avg_color = tuple(map(int, np.mean(roi_region, axis=(0, 1))))

    # For red-dominant regions, use a modified brightness calculation
    if avg_color[0] > avg_color[1] and avg_color[0] > avg_color[2]:
        # For red regions, if red component is high enough, treat as light
        if avg_color[0] > 200:  # High red value indicates light region
            text_color = (205, 255, 255)  # Light cyan for light red
            stroke_color = (68, 85, 85)   # Dark cyan
        else:
            text_color = (231, 255, 255)  # Light cyan for dark red
            stroke_color = (77, 85, 85)   # Dark cyan
    else:
        # Calculate perceived brightness using standard coefficients
        brightness = (0.299 * avg_color[0] + 0.587 * avg_color[1] + 0.114 * avg_color[2])

        # For dark backgrounds, use light colors
        if brightness < 128:
            # For dark green, use light magenta
            if avg_color[1] > avg_color[0] and avg_color[1] > avg_color[2]:
                text_color = (255, 205, 255)  # Light magenta
                stroke_color = (85, 68, 85)   # Dark magenta
            # For dark blue or black, use white
            else:
                text_color = (255, 255, 255)  # White
                stroke_color = (85, 85, 85)   # Dark gray
        # For light backgrounds, use dark colors
        else:
            # For light green, use light magenta
            if avg_color[1] > avg_color[0] and avg_color[1] > avg_color[2]:
                text_color = (255, 205, 255)  # Light magenta
                stroke_color = (85, 68, 85)   # Dark magenta
            # For light blue or white, use black
            else:
                text_color = (0, 0, 0)        # Black
                stroke_color = (255, 255, 255) # White

    return text_color, stroke_color
