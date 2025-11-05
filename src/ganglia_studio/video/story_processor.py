"""Story processor module for text-to-video conversion.

This module provides functionality for:
- Processing and managing story generation workflow
- Handling audio and video segment generation
- Managing file operations and temporary storage
- Coordinating between different components of the system
"""

# Standard library imports
import concurrent.futures
import json
import os
import subprocess
import time
from typing import Dict, List, Optional, Tuple, Any


# First party imports
from ganglia_common.logger import Logger
from ganglia_studio.music.music_lib import MusicGenerator
from ganglia_studio.video.config_loader import TTVConfig
from ganglia_common.tts.google_tts import GoogleTTS
from utils import ffmpeg_thread_manager

# Local imports
from .audio_alignment import create_word_level_captions
from .captions import CaptionEntry, create_dynamic_captions, create_static_captions
from .image_generation import generate_image, generate_blank_image
from .story_generation import generate_movie_poster
from .video_generation import create_video_segment

def process_sentence(i, sentence, context, style, total_images, tts, skip_generation, query_dispatcher, config, output_dir):
    """Process a single sentence into a video segment with audio and captions.

    This function handles the complete pipeline for converting a single sentence into a video segment:
    1. Generates or loads an image based on the sentence
    2. Generates audio narration for the sentence
    3. Creates a video segment combining the image and audio
    4. Adds captions to the video segment (either static or dynamic based on config)

    Args:
        i (int): Index of the sentence in the story sequence
        sentence (str): The sentence text to process
        context (str): Additional context to help with image generation
        style (str): The visual style to use for image generation
        total_images (int): Total number of images/sentences in the story
        tts (GoogleTTS): Text-to-speech interface for audio generation
        skip_generation (bool): If True, generates blank images instead of using DALL-E
        query_dispatcher (QueryDispatcher): Interface for making API calls
        config (Config): Configuration object containing settings for image/caption generation
        output_dir (str): Directory for output files (should be timestamped)

    Returns:
        tuple: A tuple containing (video_path, index) where:
            - video_path (str or None): Path to the generated video segment, or None if generation failed
            - index (int): The original sentence index

    Note:
        The function may return (None, index) at various points if any step fails:
        - Image generation/loading fails
        - Audio generation fails
        - Video segment creation fails
        - Caption addition fails (falls back to raw video)
    """
    thread_id = f"[Thread {i+1}/{total_images}]"
    Logger.print_info(f"{thread_id} Processing sentence: {sentence}")

    # Get preloaded images directory from config
    preloaded_images_dir = getattr(config, 'preloaded_images_dir', None)

    # Generate image for this sentence
    filename = None
    if skip_generation:
        filename = generate_blank_image(sentence, i, thread_id=thread_id, output_dir=output_dir)
    else:
        filename, success = generate_image(
            sentence,
            context,
            style,
            i,
            total_images,
            query_dispatcher,
            preloaded_images_dir=preloaded_images_dir,
            thread_id=thread_id,
            output_dir=output_dir
        )
        if not success:
            return None, i
    if not filename:
        return None, i

    # Generate audio for this sentence
    Logger.print_info(f"{thread_id} Generating audio for sentence.")
    success, audio_path = tts.convert_text_to_speech(sentence, thread_id=thread_id)
    if not success or not audio_path:
        Logger.print_error(f"{thread_id} Failed to generate audio")
        return None, i

    # Create initial video segment using ffmpeg_thread_manager
    Logger.print_info(f"{thread_id} Creating initial video segment.")
    initial_segment_path = os.path.join(output_dir, f"segment_{i}_initial.mp4")
    with ffmpeg_thread_manager:
        if not create_video_segment(filename, audio_path, initial_segment_path):
            Logger.print_error(f"{thread_id} Failed to create video segment")
            return None, i

    # Get caption style from config
    caption_style = getattr(config, 'caption_style', 'static')

    if caption_style == "dynamic":
        # Add dynamic captions using word-level alignment
        Logger.print_info(f"{thread_id} Adding dynamic captions to video segment.")
        try:
            captions = create_word_level_captions(audio_path, sentence)
            if not captions:
                Logger.print_error(f"{thread_id} Failed to create word-level captions")
                return None, i
        except Exception as e:
            Logger.print_error(f"{thread_id} Error creating word-level captions: {e}")
            return None, i

        final_segment_path = os.path.join(output_dir, f"segment_{i}.mp4")
        with ffmpeg_thread_manager:
            captioned_path = create_dynamic_captions(
                input_video=initial_segment_path,
                captions=captions,
                output_path=final_segment_path,
                min_font_size=32,
                max_font_ratio=1.5  # Max will be 48 (1.5x the min)
            )

        if captioned_path:
            Logger.print_info(f"{thread_id} Successfully added dynamic captions")
            return captioned_path, i
        else:
            Logger.print_error(f"{thread_id} Failed to add captions, using raw video")
            return initial_segment_path, i
    else:
        # Add static captions
        Logger.print_info(f"{thread_id} Adding static captions to video segment.")
        final_segment_path = os.path.join(output_dir, f"segment_{i}.mp4")
        captions = [CaptionEntry(sentence, 0.0, float('inf'))]  # Show for entire duration
        with ffmpeg_thread_manager:
            captioned_path = create_static_captions(
                input_video=initial_segment_path,
                captions=captions,
                output_path=final_segment_path,
                font_size=40
            )

        if captioned_path:
            Logger.print_info(f"{thread_id} Successfully added static captions")
            return captioned_path, i
        else:
            Logger.print_error(f"{thread_id} Failed to add captions, using raw video")
            return initial_segment_path, i

def process_story(
    tts: GoogleTTS,
    style: str,
    story: List[str],
    output_dir: str,
    config: TTVConfig,
    skip_generation: bool = False,
    query_dispatcher: Optional[Any] = None,
    story_title: Optional[str] = None,
    thread_id: Optional[str] = None
) -> Tuple[List[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Process a complete story into segments.

    Args:
        tts: Text-to-speech engine instance
        style: Style to apply to generation
        story: List of story sentences to process
        output_dir: Directory for output files
        config: Configuration object containing settings for generation
        skip_generation: Whether to skip image generation
        query_dispatcher: Optional query dispatcher for API calls
        story_title: Optional title of the story
        thread_id: Optional thread ID for logging

    Returns:
        Tuple containing:
        - List[str]: List of video segment paths
        - Optional[str]: Background music path
        - Optional[str]: Closing credits path
        - Optional[str]: Movie poster path
        - Optional[str]: Closing credits lyrics

    Raises:
        ValueError: If story is empty or required configuration is missing
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        if not story:
            raise ValueError("No story provided")

        total_segments = len(story)
        Logger.print_info(
            f"{thread_prefix}Processing {total_segments} story segments"
        )

        # Initialize return values and futures
        movie_poster_path = None
        background_music_path = None
        closing_credits_path = None
        closing_credits_lyrics = None

        # Create music generator
        music_generator = MusicGenerator(config=config)

        # Calculate max workers needed (segments + background music + closing credits)
        max_workers = total_segments + 2

        # Process all tasks in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            # Submit movie poster task if configured
            movie_poster_future = None
            if not skip_generation and story_title and query_dispatcher:
                story_json = json.dumps({
                    "style": style,
                    "title": story_title,
                    "story": story
                })
                movie_poster_future = executor.submit(
                    generate_movie_poster,
                    story_json,
                    style,
                    story_title,
                    query_dispatcher,
                    output_dir=output_dir
                )
                futures.append(('movie_poster', movie_poster_future))

            # Submit background music task if configured
            background_music_future = None
            if hasattr(config, 'background_music') and config.background_music:
                background_music_future = executor.submit(
                    music_generator.get_background_music,
                    config=config,
                    output_dir=output_dir,
                    skip_generation=skip_generation,
                    thread_id=f"{thread_id}_background" if thread_id else "background"
                )
                futures.append(('background_music', background_music_future))

            # Submit closing credits task if configured
            closing_credits_future = None
            if hasattr(config, 'closing_credits') and config.closing_credits:
                closing_credits_future = executor.submit(
                    music_generator.get_closing_credits,
                    config=config,
                    story_text="\n".join(story),
                    output_dir=output_dir,
                    skip_generation=skip_generation,
                    query_dispatcher=query_dispatcher,
                    thread_id=f"{thread_id}_credits" if thread_id else "credits"
                )
                futures.append(('closing_credits', closing_credits_future))
            elif hasattr(config, 'closing_credits'):
                Logger.print_warning(f"{thread_prefix}Closing credits configured but no file or prompt provided")

            # Submit video segment tasks
            segment_futures = []
            for i, sentence in enumerate(story):
                future = executor.submit(
                    process_sentence,
                    i=i,
                    sentence=sentence,
                    context="",
                    style=style,
                    total_images=total_segments,
                    tts=tts,
                    skip_generation=skip_generation,
                    query_dispatcher=query_dispatcher,
                    config=config,
                    output_dir=output_dir
                )
                segment_futures.append((i, future))
                futures.append(('segment', (i, future)))

            # Process results as they complete
            segments = []
            segment_indices = []

            for task_type, future in futures:
                try:
                    if task_type == 'movie_poster':
                        movie_poster_path = future.result()
                        if movie_poster_path is None:
                            Logger.print_warning(f"{thread_prefix}Failed to generate movie poster, closing credits may be affected")

                    elif task_type == 'background_music':
                        background_music_path = future.result()
                        if background_music_path is None:
                            Logger.print_warning(f"{thread_prefix}Background music generation failed - continuing without background music")
                            # Don't return None for everything, just continue without background music

                    elif task_type == 'closing_credits':
                        closing_credits_path, closing_credits_lyrics = future.result()
                        if closing_credits_path is None:
                            Logger.print_error(f"{thread_prefix}Closing credits generation failed")
                            # Don't return None for everything, just continue without credits

                    elif task_type == 'segment':
                        i, segment_future = future
                        segment = segment_future.result()
                        if segment and segment[0]:  # If segment was generated successfully
                            segments.append(segment[0])
                            segment_indices.append(segment[1])
                        else:
                            Logger.print_error(f"{thread_prefix}Failed to process segment {segment[1] if segment else 'unknown'}")

                except Exception as e:
                    Logger.print_error(f"{thread_prefix}Error processing task: {str(e)}")
                    if task_type == 'background_music':  # Background music failure is not critical
                        Logger.print_warning(f"{thread_prefix}Background music generation failed with error - continuing without background music")
                        background_music_path = None
                    continue

            if not segments:
                Logger.print_error(f"{thread_prefix}All segments failed to process")
                return None, None, None, None, None

            # Sort segments by their index to maintain order
            segments_with_indices = list(zip(segments, segment_indices))
            segments_with_indices.sort(key=lambda x: x[1])
            segments = [s[0] for s in segments_with_indices]

            Logger.print_info(f"{thread_prefix}Successfully processed {len(segments)}/{total_segments} segments")

        return segments, background_music_path, closing_credits_path, movie_poster_path, closing_credits_lyrics

    except Exception as e:
        Logger.print_error(
            f"{thread_prefix}Error processing story: {str(e)}"
        )
        return None, None, None, None, None


def retry_on_rate_limit(func, *args, retries=5, wait_time=60, **kwargs):
    """Retry a function call when rate limits are hit.

    Args:
        func: The function to call
        *args: Positional arguments to pass to the function
        retries: Number of times to retry (default: 5)
        wait_time: Seconds to wait between retries (default: 60)
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function call

    Raises:
        Exception: If all retries fail due to rate limiting
    """
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if 'Rate limit exceeded' in str(e):
                Logger.print_error(f"Rate limit exceeded. Retrying in {wait_time} seconds... (Attempt {attempt + 1} of {retries})")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception(f"Failed to complete {func.__name__} after {retries} attempts due to rate limiting.")

def process_story_segment(
    sentence: str,
    segment_index: int,
    total_segments: int,
    tts_engine: GoogleTTS,
    style: str,
    query_dispatcher: Optional[Any] = None,
    context: str = "",
    thread_id: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Process a single story segment.

    Args:
        sentence: Text of the story segment
        segment_index: Index of current segment
        total_segments: Total number of segments
        tts_engine: Text-to-speech engine instance
        style: Style to apply to generation
        query_dispatcher: Optional query dispatcher for API calls
        context: Optional context for image generation
        thread_id: Optional thread ID for logging
        output_dir: Optional directory for output files

    Returns:
        Optional[Dict[str, str]]: Dictionary with paths to generated files
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    Logger.print_info(
        f"{thread_prefix}Processing segment {segment_index + 1} "
        f"of {total_segments}"
    )

    try:
        # Generate image for segment
        image_path = generate_image(
            sentence=sentence,
            context=context,
            style=style,
            image_index=segment_index,
            total_images=total_segments,
            query_dispatcher=query_dispatcher,
            thread_id=thread_id,
            output_dir=output_dir
        )[0]  # get just the path from the tuple
        if not image_path:
            Logger.print_error(
                f"{thread_prefix}Failed to generate image for segment "
                f"{segment_index + 1}"
            )
            return None

        # Generate audio for segment
        success, audio_path = tts_engine.convert_text_to_speech(
            text=sentence,
            thread_id=thread_id
        )
        if not success or not audio_path:
            Logger.print_error(
                f"{thread_prefix}Failed to generate audio for segment "
                f"{segment_index + 1}"
            )
            return None

        return {
            "image": image_path,
            "audio": audio_path,
            "text": sentence
        }

    except Exception as e:
        Logger.print_error(
            f"{thread_prefix}Error processing segment "
            f"{segment_index + 1}: {str(e)}"
        )
        return None

def create_video_with_captions(
    segments: List[Dict[str, str]],
    output_path: str,
    output_dir: str,
    thread_id: Optional[str] = None
) -> Optional[str]:
    """Create a video with captions from segments.

    Args:
        segments: List of segment dictionaries with paths
        output_path: Path to save final video
        thread_id: Optional thread ID for logging

    Returns:
        Optional[str]: Path to final video if successful
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        # Create video segments
        video_segments = []
        futures = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for i, segment in enumerate(segments):
                try:
                    # First create initial video segment without captions
                    initial_segment_path = os.path.join(output_dir, f"segment_{i}_initial.mp4")
                    future = executor.submit(
                        create_video_segment,
                        image_path=segment["image"],
                        audio_path=segment["audio"],
                        output_path=initial_segment_path,
                        thread_id=f"{thread_id}_{i}" if thread_id else None
                    )
                    futures.append((future, i, segment, initial_segment_path))
                except Exception as e:
                    Logger.print_error(
                        f"{thread_prefix}Error submitting segment {i + 1}: {str(e)}"
                    )
                    continue

            # Process results as they complete
            for future, i, segment, initial_segment_path in futures:
                try:
                    video_path = future.result()
                    if not video_path:
                        raise ValueError(
                            f"Failed to create initial video for segment {i + 1}"
                        )

                    # Generate word-level captions
                    captions = create_word_level_captions(
                        segment["audio"],
                        segment["text"],
                        thread_id=f"{thread_id}_{i}" if thread_id else None
                    )
                    if not captions:
                        raise ValueError(
                            f"Failed to generate captions for segment {i + 1}"
                        )

                    # Add dynamic captions to the video segment
                    final_segment_path = os.path.join(output_dir, f"segment_{i}.mp4")
                    captioned_path = create_dynamic_captions(
                        input_video=video_path,
                        captions=captions,
                        output_path=final_segment_path,
                        min_font_size=32,
                        max_font_ratio=1.5  # Max will be 48 (1.5x the min)
                    )

                    if not captioned_path:
                        raise ValueError(
                            f"Failed to add captions to segment {i + 1}"
                        )

                    video_segments.append(captioned_path)

                except (OSError, ValueError) as e:
                    Logger.print_error(
                        f"{thread_prefix}Error processing segment {i + 1}: {str(e)}"
                    )
                    continue

        # Combine segments
        if not video_segments:
            raise ValueError("No video segments were created successfully")

        # Create list file for concatenation
        list_file = os.path.join(output_dir, "segments.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for segment in video_segments:
                f.write(f"file '{segment}'\n")

        # Concatenate segments using thread manager
        with ffmpeg_thread_manager:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-c", "copy",
                output_path
            ]
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True
            )

        if result.returncode != 0:
            raise ValueError(f"Failed to concatenate segments: {result.stderr.decode()}")

        Logger.print_info(
            f"{thread_prefix}Successfully created video at {output_path}"
        )
        return output_path

    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(
            f"{thread_prefix}Error creating video: {str(e)}"
        )
        return None
    finally:
        # Cleanup temporary files
        try:
            if os.path.exists(list_file):
                os.remove(list_file)
            for segment in video_segments:
                if os.path.exists(segment):
                    os.remove(segment)
        except (OSError, UnboundLocalError) as e:
            Logger.print_warning(
                f"{thread_prefix}Error cleaning up temporary files: {str(e)}"
            )

def add_background_music(
    video_path: str,
    output_path: str,
    music_generator: MusicGenerator,
    thread_id: Optional[str] = None
) -> Optional[str]:
    """Add background music to a video.

    Args:
        video_path: Path to input video
        output_path: Path to save output video
        music_generator: Music generator instance
        thread_id: Optional thread ID for logging

    Returns:
        Optional[str]: Path to output video if successful
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    output_dir = os.path.dirname(output_path)

    try:
        # Get video duration
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            Logger.print_info(f"{thread_prefix}Video duration: {duration:.2f}s")
        except (subprocess.CalledProcessError, ValueError) as e:
            Logger.print_error(f"{thread_prefix}Failed to get video duration: {e}")
            duration = 30  # Fallback to default duration

        # Generate background music
        music_path = music_generator.generate_background_music(
            duration=duration,
            output_path=os.path.join(output_dir, "background.wav"),
            thread_id=thread_id
        )
        if not music_path:
            raise ValueError("Failed to generate background music")

        # Mix audio streams
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", music_path,
                "-filter_complex",
                "[1:a]volume=0.3[music];[0:a][music]amix=duration=longest",
                "-c:v", "copy",
                output_path
            ],
            check=True,
            capture_output=True
        )

        Logger.print_info(
            f"{thread_prefix}Successfully added background music to video"
        )
        return output_path

    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(
            f"{thread_prefix}Error adding background music: {str(e)}"
        )
        return None
    finally:
        # Cleanup temporary files
        try:
            if os.path.exists(music_path):
                os.remove(music_path)
        except (OSError, UnboundLocalError):
            pass
