"""Unit tests for color utilities."""

import pytest
import numpy as np
from ganglia_studio.video.color_utils import (
    get_vibrant_palette,
    get_color_complement,
    mix_colors,
    get_contrasting_color
)


def test_get_vibrant_palette():
    """Test vibrant color palette generation."""
    palette = get_vibrant_palette()
    
    # Should return a list
    assert isinstance(palette, list)
    
    # Should have multiple colors
    assert len(palette) > 0
    
    # Each color should be an RGB tuple
    for color in palette:
        assert isinstance(color, tuple)
        assert len(color) == 3
        # RGB values should be in valid range
        for value in color:
            assert 0 <= value <= 255


def test_get_color_complement():
    """Test color complement calculation."""
    # Test with red
    red = (255, 0, 0)
    complement = get_color_complement(red)
    
    # Complement should be an RGB tuple
    assert isinstance(complement, tuple)
    assert len(complement) == 3
    
    # Values should be in valid range
    for value in complement:
        assert 0 <= value <= 255
    
    # Test with blue
    blue = (0, 0, 255)
    complement = get_color_complement(blue)
    assert isinstance(complement, tuple)


def test_mix_colors():
    """Test color mixing."""
    red = (255, 0, 0)
    blue = (0, 0, 255)
    
    # Mix with 80% red (default ratio)
    mixed = mix_colors(red, blue)
    assert isinstance(mixed, tuple)
    assert len(mixed) == 3
    
    # Result should be closer to red
    assert mixed[0] > mixed[2]
    
    # Mix with 50/50 ratio
    mixed_equal = mix_colors(red, blue, ratio=0.5)
    assert mixed_equal[0] == mixed_equal[2]
    
    # Mix with 20% red
    mixed_blue = mix_colors(red, blue, ratio=0.2)
    assert mixed_blue[2] > mixed_blue[0]


def test_get_contrasting_color_dark_background():
    """Test contrasting color selection for dark backgrounds."""
    # Create a dark frame (black)
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    roi = (10, 10, 50, 50)  # x, y, width, height
    
    text_color, stroke_color = get_contrasting_color(frame, roi)
    
    # Both should be RGB tuples
    assert isinstance(text_color, tuple)
    assert isinstance(stroke_color, tuple)
    assert len(text_color) == 3
    assert len(stroke_color) == 3
    
    # For dark background, text should be light
    text_brightness = sum(text_color) / 3
    assert text_brightness > 127


def test_get_contrasting_color_light_background():
    """Test contrasting color selection for light backgrounds."""
    # Create a light frame (white)
    frame = np.full((100, 100, 3), 255, dtype=np.uint8)
    roi = (10, 10, 50, 50)
    
    text_color, stroke_color = get_contrasting_color(frame, roi)
    
    # For light background, text should be dark
    text_brightness = sum(text_color) / 3
    assert text_brightness < 200


def test_get_contrasting_color_red_background():
    """Test contrasting color selection for red backgrounds."""
    # Create a red frame
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[:, :, 0] = 255  # Red channel
    roi = (10, 10, 50, 50)
    
    text_color, stroke_color = get_contrasting_color(frame, roi)
    
    # Should return valid colors
    assert isinstance(text_color, tuple)
    assert isinstance(stroke_color, tuple)

