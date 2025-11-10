"""Module for handling dynamic video captions and SRT subtitle generation."""

import os
import subprocess
import tempfile
import traceback
import uuid
import random
from dataclasses import dataclass
from typing import List, Tuple, Optional

from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from PIL import ImageFont, Image, ImageDraw
import numpy as np

from ganglia_common.logger import Logger
from ganglia_studio.utils.ffmpeg_utils import run_ffmpeg_command
from .caption_roi import find_roi_in_frame
from .color_utils import get_vibrant_palette

def get_default_font() -> str:
    """Get default font name."""
    # Common paths for DejaVu Sans font
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux/Docker
        "/Library/Fonts/DejaVuSans.ttf",  # macOS
    ]

    for path in font_paths:
        if os.path.exists(path):
            return path

    raise RuntimeError(
        "DejaVu Sans font not found. You have two options:\n"
        "1. Run tests in Docker (recommended)\n"
        "2. Install DejaVu Sans font on your system:\n"
        "   - macOS: curl -L https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2 | tar xj && sudo cp dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf /Library/Fonts/ && rm -rf dejavu-fonts-ttf-2.37\n"
        "   - Linux: sudo apt-get install fonts-dejavu-core\n"
    )

@dataclass
class Word:
    """Represents a single word in a caption with timing and display properties."""
    text: str
    start_time: float
    end_time: float
    line_number: int = 0
    font_size: int = 0
    x_position: int = 0
    width: int = 0
    font_name: str = get_default_font()

    @classmethod
    def from_timed_word(cls, text: str, start_time: float, end_time: float, font_name: str = get_default_font()) -> 'Word':
        """Create a Word instance from pre-timed word (e.g. from Whisper alignment)."""
        return cls(text=text, start_time=start_time, end_time=end_time, font_name=font_name)

    @classmethod
    def from_text(cls, text: str, font_name: str = get_default_font()) -> 'Word':
        """Create a Word instance from text only, timing to be calculated later."""
        return cls(text=text, start_time=0.0, end_time=0.0, font_name=font_name)

    def calculate_width(self, font_size):
        """Calculate exact text width using PIL's ImageFont."""
        try:
            font = ImageFont.truetype(self.font_name, font_size)
        except OSError:
            # Fallback to loading system font by name
            font = ImageFont.load_default()
        self.width = font.getlength(self.text)

@dataclass
class CaptionWindow:
    """Groups words into a display window with shared timing and font size."""
    words: List[Word]
    start_time: float
    end_time: float
    font_size: int

class CaptionEntry:
    """Represents a complete caption with text and timing information."""
    def __init__(self, text: str, start_time: float, end_time: float, timed_words: Optional[List[Tuple[str, float, float]]] = None):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time
        self.timed_words = timed_words

def split_into_words(caption: CaptionEntry, words_per_second: float = 2.0, font_name: str = get_default_font()) -> List[Word]:
    """Split caption text into words with timing.

    If caption.timed_words is provided, uses those timings.
    Otherwise, calculates timing based on words_per_second.
    """
    if caption.timed_words:
        # Use pre-calculated word timings (e.g. from Whisper)
        return [Word.from_timed_word(text, start, end, font_name)
                for text, start, end in caption.timed_words]

    # Fall back to calculating timing based on words_per_second
    words = caption.text.split()
    total_duration = caption.end_time - caption.start_time
    total_words = len(words)
    min_duration_needed = total_words / words_per_second

    if min_duration_needed > total_duration:
        # If we need more time than available, spread words evenly
        word_duration = total_duration / total_words
    else:
        # Otherwise use the requested words_per_second
        word_duration = 1.0 / words_per_second

    result = []
    current_time = caption.start_time
    for i, word in enumerate(words):
        # For the last word, ensure it ends exactly at caption.end_time
        if i == len(words) - 1:
            end_time = caption.end_time
        else:
            end_time = min(current_time + word_duration, caption.end_time)
        result.append(Word(text=word, start_time=current_time, end_time=end_time, font_name=font_name))
        current_time = end_time
    return result

def assign_word_sizes(words: List[Word], min_font_size: int, max_font_ratio: float) -> None:
    """
    Assign font sizes to words using a uniform distribution.

    Args:
        words: List of Word objects to assign sizes to
        min_font_size: Minimum font size in pixels
        max_font_ratio: Ratio to determine max font size (max = min * ratio)
    """
    max_font_size = int(min_font_size * max_font_ratio)
    size_range = max_font_size - min_font_size

    # Calculate number of distinct sizes we want (about 1 size per 2-3 words)
    num_sizes = max(5, len(words) // 2)
    step = size_range / (num_sizes - 1)

    # Create a list of available sizes
    available_sizes = [int(min_font_size + (i * step)) for i in range(num_sizes)]
    if available_sizes[-1] > max_font_size:
        available_sizes[-1] = max_font_size

    # First, ensure each size is used at least once (if we have enough words)
    shuffled_words = list(words)
    random.shuffle(shuffled_words)

    for i, word in enumerate(shuffled_words):
        if i < len(available_sizes):
            # Assign one of each size first
            word.font_size = available_sizes[i]
        else:
            # Then randomly assign remaining words
            word.font_size = random.choice(available_sizes)
        word.calculate_width(word.font_size)

def calculate_word_position(
    word: Word,
    cursor_x: int,
    cursor_y: int,
    line_height: int,
    roi_width: int,
    roi_height: int,
    previous_word: Optional[Word] = None
) -> Tuple[int, int, int, int, bool]:
    """Calculate position for a word in the caption window."""
    # Calculate buffer pixels based on font size
    buffer_pixels = max(int(word.font_size * 0.4), 8)  # Reduced from 0.5 to 0.4

    # Calculate word position
    if previous_word is None:
        # First word in window
        word_x = 0
        word_y = cursor_y
        new_cursor_x = int(word.width + buffer_pixels)
        new_cursor_y = cursor_y
        return new_cursor_x, new_cursor_y, word_x, word_y, False

    # Check if word fits on current line
    # Use 90% of ROI width to force wrapping sooner
    effective_width = int(roi_width * 0.9)
    if cursor_x + word.width + buffer_pixels <= effective_width:
        # Word fits on current line
        word_x = int(cursor_x + buffer_pixels)  # Add buffer after previous word
        word_y = cursor_y
        new_cursor_x = int(word_x + word.width)
        new_cursor_y = int(cursor_y)
        return new_cursor_x, new_cursor_y, word_x, word_y, False

    # Word doesn't fit - check if we have room for a new line
    # Add extra vertical buffer between lines
    vertical_buffer = max(int(line_height * 0.4), 8)  # Reduced from 0.5 to 0.4
    if cursor_y + (2 * line_height) + vertical_buffer <= roi_height:
        # Start new line
        word_x = 0
        word_y = int(cursor_y + line_height + vertical_buffer)
        new_cursor_x = int(word.width + buffer_pixels)
        new_cursor_y = word_y
        return new_cursor_x, new_cursor_y, word_x, word_y, False

    # No room for new line - need new window
    return 0, 0, 0, 0, True

def create_caption_windows(
    words: List[Word],
    min_font_size: int,
    max_font_ratio: float,
    roi_width: int,
    roi_height: int,
) -> List[CaptionWindow]:
    """Group words into caption windows with appropriate line breaks."""
    # First, assign random sizes to all words
    assign_word_sizes(words, min_font_size, max_font_ratio)

    windows = []
    current_window_words = []
    cursor_x = 0
    cursor_y = 0
    line_number = 0

    i = 0
    while i < len(words):
        word = words[i]
        previous_word = current_window_words[-1] if current_window_words else None

        new_cursor_x, new_cursor_y, word_x, word_y, needs_new_window = calculate_word_position(
            word=word,
            cursor_x=int(cursor_x),
            cursor_y=int(cursor_y),
            line_height=int(word.font_size * 1.2),
            roi_width=int(roi_width),
            roi_height=int(roi_height),
            previous_word=previous_word
        )

        if needs_new_window:
            # Create window with current words and start a new one
            if current_window_words:
                window = CaptionWindow(
                    words=current_window_words,
                    start_time=current_window_words[0].start_time,
                    end_time=current_window_words[-1].end_time,
                    font_size=min_font_size  # This is now just a baseline for spacing
                )
                windows.append(window)

            # Reset for new window
            current_window_words = []
            cursor_x = 0
            cursor_y = 0
            line_number = 0
            continue

        # Update word position and line number
        word.x_position = word_x
        # Calculate line number based on y position, accounting for line height and vertical buffer
        vertical_buffer = max(int(word.font_size * 1.2 * 0.4), 8)  # Same as in calculate_word_position
        line_spacing = word.font_size * 1.2 + vertical_buffer
        word.line_number = int(word_y / line_spacing)
        current_window_words.append(word)
        cursor_x = new_cursor_x
        cursor_y = new_cursor_y
        if cursor_y > line_number * line_spacing:
            line_number += 1
        i += 1

    # Add any remaining words as the last window
    if current_window_words:
        window = CaptionWindow(
            words=current_window_words,
            start_time=current_window_words[0].start_time,
            end_time=current_window_words[-1].end_time,
            font_size=min_font_size  # This is now just a baseline for spacing
        )
        windows.append(window)

    return windows

def calculate_word_positions(
    window: CaptionWindow,
    video_height: int,
    margin: int,
) -> List[Tuple[float, float]]:
    """
    Calculate the (x, y) positions for each word in a caption window.
    Returns a list of (x, y) coordinates in the same order as window.words.
    """
    positions = []
    line_height = int(window.font_size * 1.2)  # Add some spacing between lines
    total_lines = max(w.line_number for w in window.words) + 1
    window_height = total_lines * line_height
    window_top = video_height - margin - window_height  # Start position of window

    # Calculate positions for each word
    for word in window.words:
        # Calculate y position
        y_position = window_top + (word.line_number * line_height)  # Lines flow downward

        # Adjust y position for larger font sizes to align baselines
        if word.font_size > window.font_size:
            baseline_offset = word.font_size - window.font_size
            y_position -= baseline_offset

        # X position is already calculated in try_fit_words and stored in word.x_position
        # Just add the left margin
        x_position = margin + word.x_position

        positions.append((x_position, y_position))

    return positions

def calculate_text_size(text, font_size, font_path=None):
    """Calculate the size of text when rendered with the given font size."""
    # Create a PIL Image to measure text size
    img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(img)

    # Load font
    if font_path and os.path.exists(font_path):
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = ImageFont.truetype(get_default_font(), font_size)
    else:
        font = ImageFont.truetype(get_default_font(), font_size)

    # Get text size
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    text_width = width
    text_height = height

    # Add buffer pixels around text
    buffer_pixels = max(int(font_size * 0.75), 16)  # Significantly increased buffer
    return width + buffer_pixels * 2, height + buffer_pixels * 2, text_width, text_height

def _create_text_clip(
    word: Word,
    position: Tuple[int, int],
    text_color: Tuple[int, int, int],
    stroke_color: Tuple[int, int, int],
    clip_dimensions: Tuple[int, int],
    margins: Tuple[int, int, int, int],
    border_thickness: int,
    duration: float,
    start_time: float
) -> TextClip:
    """Create a text clip with the given parameters."""
    return TextClip(
        text=word.text,
        font=word.font_name,
        method='caption',
        color=text_color,
        stroke_color=stroke_color,
        stroke_width=border_thickness,
        font_size=word.font_size,
        size=clip_dimensions,
        margin=margins,
        text_align='left',
        duration=duration
    ).with_position(position).with_start(start_time)

def _create_shadow_clip(
    word: Word,
    position: Tuple[int, int],
    clip_dimensions: Tuple[int, int],
    margins: Tuple[int, int, int, int],
    border_thickness: int,
    duration: float,
    start_time: float,
    opacity: float
) -> TextClip:
    """Create a shadow clip with the given parameters."""
    return TextClip(
        text=word.text,
        font=word.font_name,
        method='caption',
        color=(0, 0, 0),  # Black shadow
        stroke_color=(0, 0, 0),
        stroke_width=border_thickness,
        font_size=word.font_size,
        size=clip_dimensions,
        margin=margins,
        text_align='left',
        duration=duration
    ).with_position(position).with_start(start_time).with_opacity(opacity)

def _calculate_clip_dimensions(
    word: Word,
    border_thickness: int,
    shadow_offset: Tuple[int, int]
) -> Tuple[Tuple[int, int], Tuple[int, int, int, int]]:
    """Calculate clip dimensions and margins."""
    # Calculate padding to account for stroke and shadow
    # Use border thickness for stroke and shadow offset for shadow
    horizontal_padding = (border_thickness + shadow_offset[0]) * 2
    clip_width = int(word.width + horizontal_padding)
    clip_height = int(word.font_size * 1.5)  # Keep original height ratio

    # Center the text in the clip by using equal margins
    margin_left = horizontal_padding // 2
    margin_bottom = int(word.font_size * 0.2)  # Keep original bottom margin

    return (clip_width, clip_height), (margin_left, 0, 0, margin_bottom)

def _create_word_clips(
    word: Word,
    window: CaptionWindow,
    roi_x: int,
    roi_y: int,
    roi_width: int,
    roi_height: int,
    text_color: Tuple[int, int, int],
    stroke_color: Tuple[int, int, int],
    border_thickness: int,
    shadow_offset: Tuple[int, int],
    max_font_size: int,
    cursor_pos: Tuple[int, int],
    previous_word: Optional[Word]
) -> Tuple[List[TextClip], Tuple[int, int]]:
    """Create all clips (text and shadows) for a single word."""
    clip_dimensions, margins = _calculate_clip_dimensions(word, border_thickness, shadow_offset)

    # Calculate baseline offset for vertical alignment
    baseline_offset = max_font_size - word.font_size

    # Calculate word position
    new_cursor_x, new_cursor_y, x_position, y_position, _ = calculate_word_position(
        word=word,
        cursor_x=int(cursor_pos[0]),
        cursor_y=int(cursor_pos[1]),
        line_height=int(word.font_size * 1.2),
        roi_width=int(roi_width),
        roi_height=int(roi_height),
        previous_word=previous_word
    )

    # Calculate base position adjustments
    margin_left = margins[0]
    base_x = int(roi_x + x_position - margin_left)
    base_y = int(roi_y + y_position + baseline_offset)

    # Create outer shadow
    outer_shadow = _create_shadow_clip(
        word=word,
        position=(base_x + int(shadow_offset[0] * 1.5), base_y + int(shadow_offset[1] * 1.5)),
        clip_dimensions=clip_dimensions,
        margins=margins,
        border_thickness=border_thickness,
        duration=window.end_time - word.start_time,
        start_time=word.start_time,
        opacity=0.4
    )

    # Create inner shadow
    inner_shadow = _create_shadow_clip(
        word=word,
        position=(base_x + shadow_offset[0], base_y + shadow_offset[1]),
        clip_dimensions=clip_dimensions,
        margins=margins,
        border_thickness=border_thickness,
        duration=window.end_time - word.start_time,
        start_time=word.start_time,
        opacity=0.7
    )

    # Create main text clip
    text_clip = _create_text_clip(
        word=word,
        position=(base_x, base_y),
        text_color=text_color,
        stroke_color=stroke_color,
        clip_dimensions=clip_dimensions,
        margins=margins,
        border_thickness=border_thickness,
        duration=window.end_time - word.start_time,
        start_time=word.start_time
    )

    return [outer_shadow, inner_shadow, text_clip], (new_cursor_x, new_cursor_y)

def _process_caption_window(
    window: CaptionWindow,
    roi_x: int,
    roi_y: int,
    roi_width: int,
    roi_height: int,
    first_frame: np.ndarray,
    min_font_size: int,
    max_font_ratio: float,
    border_thickness: int,
    shadow_offset: Tuple[int, int]
) -> List[TextClip]:
    """Process a single caption window and create all necessary clips."""
    # Get background color from ROI for this window's position
    window_roi = first_frame[roi_y:roi_y+roi_height, roi_x:roi_x+roi_width]
    avg_bg_color = tuple(map(int, np.mean(window_roi, axis=(0, 1))))

    # Calculate complement of background color
    complement = tuple(255 - c for c in avg_bg_color)

    # Find palette color closest to background complement
    palette = get_vibrant_palette()
    color_diffs = [sum(abs(c1 - c2) for c1, c2 in zip(complement, palette_color)) for palette_color in palette]
    color_idx = color_diffs.index(min(color_diffs))
    text_color = palette[color_idx]

    # Make stroke color exactly 1/3 intensity of text color
    stroke_color = tuple(c // 3 for c in text_color)

    Logger.print_info(f"Using color {text_color} for window (background: {avg_bg_color}, complement: {complement})")

    # Process all words in the window
    text_clips = []
    cursor_x, cursor_y = 0, 0
    previous_word = None
    max_font_size = int(min_font_size * max_font_ratio)

    for word in window.words:
        clips, (cursor_x, cursor_y) = _create_word_clips(
            word=word,
            window=window,
            roi_x=roi_x,
            roi_y=roi_y,
            roi_width=roi_width,
            roi_height=roi_height,
            text_color=text_color,
            stroke_color=stroke_color,
            border_thickness=border_thickness,
            shadow_offset=shadow_offset,
            max_font_size=max_font_size,
            cursor_pos=(cursor_x, cursor_y),
            previous_word=previous_word
        )
        text_clips.extend(clips)
        previous_word = word

    return text_clips

def create_dynamic_captions(
    input_video: str,
    captions: List[CaptionEntry],
    output_path: str,
    min_font_size: int = 32,
    max_font_ratio: float = 1.5,
    font_name: str = get_default_font(),
    words_per_second: float = 2.0,
    shadow_offset: Tuple[int, int] = (8, 8),
    border_thickness: int = 5,
) -> Optional[str]:
    """Add Instagram-style dynamic captions to a video using MoviePy."""
    temp_files = []  # Keep track of temp files for cleanup
    try:
        # Load the video and get its duration
        video = VideoFileClip(input_video)
        video_duration = video.duration

        # Get first frame for ROI detection
        first_frame = video.get_frame(0)
        roi = find_roi_in_frame(first_frame)
        if roi is None:
            Logger.print_error("Failed to find ROI for captions")
            return None

        # Extract ROI dimensions
        roi_x, roi_y, roi_width, roi_height = roi

        # Process all captions into words
        all_words = []
        for caption in captions:
            # Ensure caption timing doesn't exceed video duration
            if caption.start_time >= video_duration:
                continue
            caption.end_time = min(caption.end_time, video_duration)

            words = split_into_words(caption, words_per_second, font_name)
            if words:
                # Ensure word timings don't exceed video duration
                for word in words:
                    word.end_time = min(word.end_time, video_duration)
                all_words.extend(words)

        if not all_words:
            Logger.print_error("No words to display in captions")
            return None

        # Create caption windows using ROI dimensions
        windows = create_caption_windows(
            words=all_words,
            min_font_size=min_font_size,
            max_font_ratio=max_font_ratio,
            roi_width=roi_width,
            roi_height=roi_height
        )

        # Process each window and collect all text clips
        text_clips = []
        for window in windows:
            window_clips = _process_caption_window(
                window=window,
                roi_x=roi_x,
                roi_y=roi_y,
                roi_width=roi_width,
                roi_height=roi_height,
                first_frame=first_frame,
                min_font_size=min_font_size,
                max_font_ratio=max_font_ratio,
                border_thickness=border_thickness,
                shadow_offset=shadow_offset
            )
            text_clips.extend(window_clips)

        # Combine video with text overlays
        final_video = CompositeVideoClip([video] + text_clips)

        # Generate unique filenames for temporary files
        temp_audio = os.path.join(os.path.dirname(output_path), f"temp_audio_{uuid.uuid4()}.m4a")
        temp_files.append(temp_audio)

        # Extract audio from input video
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vn",  # No video
            "-acodec", "copy",  # Copy audio codec
            temp_audio
        ]
        result = run_ffmpeg_command(ffmpeg_cmd)
        if not result:
            Logger.print_error("Failed to extract audio")
            return None

        # Write video without audio first
        temp_video = os.path.join(os.path.dirname(output_path), f"temp_video_{uuid.uuid4()}.mp4")
        temp_files.append(temp_video)

        final_video.write_videofile(
            temp_video,
            codec='libx264',
            audio=False,  # No audio in this step
            preset='ultrafast',
            threads=4
        )

        # Combine video with original audio
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", temp_video,     # Video with captions
            "-i", temp_audio,     # Original audio
            "-map", "0:v:0",      # Map video from first input
            "-map", "1:a:0",      # Map audio from second input
            "-c:v", "copy",       # Copy video stream without re-encoding
            "-c:a", "aac",        # Encode audio as AAC
            "-b:a", "192k",       # Set audio bitrate
            output_path
        ]
        result = run_ffmpeg_command(ffmpeg_cmd)
        if not result:
            Logger.print_error("Failed to combine video with audio")
            return None

        # Clean up
        video.close()
        final_video.close()
        for clip in text_clips:
            clip.close()

        Logger.print_info(f"Successfully added dynamic captions to video: {output_path}")
        return output_path

    except Exception as exception:
        Logger.print_error(f"Error adding dynamic captions: {str(exception)}")
        Logger.print_error(f"Traceback: {traceback.format_exc()}")
        return None
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as exception:
                Logger.print_error(f"Error cleaning up temporary file {temp_file}: {exception}")

def create_srt_captions(
    captions: List[CaptionEntry],
    output_path: Optional[str] = None
) -> Optional[str]:
    """Create an SRT subtitle file from caption entries."""
    try:
        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix='.srt', mode='w', delete=False) as srt_file:
                output_path = srt_file.name
        def format_time(seconds: float) -> str:
            """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            seconds = seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace('.', ',')
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, caption in enumerate(captions, 1):
                f.write(f"{i}\n")
                f.write(f"{format_time(caption.start_time)} --> {format_time(caption.end_time)}\n")
                f.write(f"{caption.text}\n\n")
        return output_path
    except (OSError, IOError) as exception:
        Logger.print_error(f"Error creating SRT file: {exception}")
        return None

def create_static_captions(
    input_video: str,
    captions: List[CaptionEntry],
    output_path: str,
    font_size: int = 40,
    font_name: str = get_default_font(),
    box_color: str = "black@0.5",  # Semi-transparent background
    position: str = "bottom",
    margin: int = 40
) -> Optional[str]:
    """
    Add simple static captions to a video.

    Args:
        input_video: Path to input video file
        captions: List of CaptionEntry objects
        output_path: Path where the output video will be saved
        font_size: Font size for captions
        font_name: Name of the font to use
        box_color: Color and opacity of the background box
        position: Vertical position of captions ('bottom' or 'center')
        margin: Margin from screen edges in pixels
    """
    temp_files = []  # Keep track of temp files for cleanup
    try:
        # Get video dimensions
        ffprobe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            input_video
        ]
        dimensions = run_ffmpeg_command(ffprobe_cmd)
        if not dimensions:
            raise ValueError("Could not determine video dimensions")


        # Build drawtext filters for each caption
        drawtext_filters = []
        for caption in captions:
            # Calculate y position
            if position == "bottom":
                y_position = f"h-{margin}-th"  # Position from bottom with margin
            else:
                y_position = "(h-th)/2"  # Center vertically

            # Escape special characters in text
            escaped_text = caption.text.replace("'", "\\'")

            filter_text = (
                f"drawtext=text='{escaped_text}'"
                f":font={font_name}"
                f":fontsize={font_size}"
                f":fontcolor=white"
                f":x=(w-text_w)/2"  # Center horizontally
                f":y={y_position}"
                f":enable=between(t\\,{caption.start_time}\\,{caption.end_time})"
                f":box=1"
                f":boxcolor={box_color}"
            )
            drawtext_filters.append(filter_text)

        # Combine all filters
        complete_filter = ",".join(drawtext_filters)

        # Generate unique filenames for temporary files
        temp_audio = os.path.join(os.path.dirname(output_path), f"temp_audio_{uuid.uuid4()}.m4a")
        temp_files.append(temp_audio)

        # Extract audio from input video
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vn",  # No video
            "-acodec", "copy",  # Copy audio codec
            temp_audio
        ]
        result = run_ffmpeg_command(ffmpeg_cmd)
        if not result:
            Logger.print_error("Failed to extract audio")
            return None

        # Create video with captions
        temp_video = os.path.join(os.path.dirname(output_path), f"temp_video_{uuid.uuid4()}.mp4")
        temp_files.append(temp_video)

        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", complete_filter,
            "-an",  # No audio in this step
            temp_video
        ]
        result = run_ffmpeg_command(ffmpeg_cmd)
        if not result:
            Logger.print_error("Failed to add static captions to video")
            return None

        # Combine video with original audio
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", temp_video,     # Video with captions
            "-i", temp_audio,     # Original audio
            "-map", "0:v:0",      # Map video from first input
            "-map", "1:a:0",      # Map audio from second input
            "-c:v", "copy",       # Copy video stream without re-encoding
            "-c:a", "aac",        # Encode audio as AAC
            "-b:a", "192k",       # Set audio bitrate
            output_path
        ]
        result = run_ffmpeg_command(ffmpeg_cmd)
        if not result:
            Logger.print_error("Failed to combine video with audio")
            return None

        Logger.print_info(f"Successfully added static captions to video: {output_path}")
        return output_path

    except (ValueError, OSError, subprocess.CalledProcessError) as exception:
        Logger.print_error(f"Error adding static captions: {exception}")
        return None
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as exception:
                Logger.print_error(f"Error cleaning up temporary file {temp_file}: {exception}")

    # TODO: Fix bug where long static captions overflow the screen width.
    #       Need to implement text wrapping for static captions similar to dynamic captions
    #       to ensure text stays within safe viewing area.
