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
from dataclasses import dataclass
from typing import Any

# First party imports
from ganglia_common.logger import Logger
from ganglia_common.tts.google_tts import GoogleTTS

from ganglia_studio.music.music_lib import MusicGenerator
from ganglia_studio.utils.ffmpeg_utils import ffmpeg_thread_manager
from ganglia_studio.video.config_loader import TTVConfig

# Local imports
from .audio_alignment import create_word_level_captions
from .captions import CaptionEntry, create_dynamic_captions, create_static_captions
from .image_generation import generate_blank_image, generate_image
from .story_generation import generate_movie_poster
from .video_generation import create_video_segment


@dataclass
class WordTiming:
    """Represents a word with its start and end times from audio."""

    text: str
    start: float
    end: float


@dataclass
class StoryTaskResults:
    """Container for asynchronous story processing task outputs."""

    segments: list[str]
    segment_indices: list[int]
    movie_poster_path: str | None
    background_music_path: str | None
    closing_credits_path: str | None
    closing_credits_lyrics: str | None


def process_sentence(
    i: int,
    sentence: str,
    context: str,
    style: str,
    *,
    total_images: int,
    tts: GoogleTTS,
    skip_generation: bool,
    query_dispatcher: Any | None = None,
    config: TTVConfig | None = None,
    output_dir: str,
):
    """Process a single sentence into a video segment with audio and captions.

    This function handles the complete pipeline for converting a single sentence
    into a video segment:
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
            - video_path (str or None): Path to the generated video segment, or
              None if generation failed
            - index (int): The original sentence index

    Note:
        The function may return (None, index) at various points if any step fails:
        - Image generation/loading fails
        - Audio generation fails
        - Video segment creation fails
        - Caption addition fails (falls back to raw video)
    """
    thread_id = f"[Thread {i + 1}/{total_images}]"
    Logger.print_info(f"{thread_id} Processing sentence: {sentence}")

    filename = _generate_sentence_image(
        i,
        sentence,
        context,
        style,
        total_images=total_images,
        skip_generation=skip_generation,
        query_dispatcher=query_dispatcher,
        config=config,
        output_dir=output_dir,
        thread_id=thread_id,
    )
    if not filename:
        return None, i

    audio_path = _generate_sentence_audio(sentence, tts, thread_id)
    if not audio_path:
        return None, i

    initial_segment_path = _create_initial_video_segment(
        i,
        filename,
        audio_path,
        output_dir,
        thread_id,
    )
    if not initial_segment_path:
        return None, i

    caption_style = getattr(config, "caption_style", "static")
    final_segment_path = os.path.join(output_dir, f"segment_{i}.mp4")

    return _add_captions_to_segment(
        caption_style,
        initial_segment_path,
        final_segment_path,
        audio_path=audio_path,
        sentence=sentence,
        index=i,
        thread_id=thread_id,
    )


def _generate_sentence_image(
    i,
    sentence,
    context,
    style,
    *,
    total_images: int,
    skip_generation: bool,
    query_dispatcher: Any | None,
    config: TTVConfig | None,
    output_dir: str,
    thread_id: str,
):
    """Generate or load image for sentence."""
    if skip_generation:
        return generate_blank_image(sentence, i, thread_id=thread_id, output_dir=output_dir)

    preloaded_images_dir = getattr(config, "preloaded_images_dir", None)
    filename, success = generate_image(
        sentence,
        context,
        style,
        image_index=i,
        total_images=total_images,
        query_dispatcher=query_dispatcher,
        preloaded_images_dir=preloaded_images_dir,
        thread_id=thread_id,
        output_dir=output_dir,
    )
    return filename if success else None


def _generate_sentence_audio(sentence, tts, thread_id):
    """Generate audio for sentence."""
    Logger.print_info(f"{thread_id} Generating audio for sentence.")
    success, audio_path = tts.convert_text_to_speech(sentence, thread_id=thread_id)
    if not success or not audio_path:
        Logger.print_error(f"{thread_id} Failed to generate audio")
        return None
    return audio_path


def _create_initial_video_segment(i, filename, audio_path, output_dir, thread_id):
    """Create initial video segment from image and audio."""
    Logger.print_info(f"{thread_id} Creating initial video segment.")
    initial_segment_path = os.path.join(output_dir, f"segment_{i}_initial.mp4")
    with ffmpeg_thread_manager:
        if not create_video_segment(filename, audio_path, initial_segment_path):
            Logger.print_error(f"{thread_id} Failed to create video segment")
            return None
    return initial_segment_path


def _add_captions_to_segment(
    caption_style,
    initial_segment_path,
    final_segment_path,
    *,
    audio_path,
    sentence,
    index,
    thread_id,
):
    """Add captions to video segment based on style."""
    if caption_style == "dynamic":
        return _add_dynamic_captions(
            initial_segment_path,
            final_segment_path,
            audio_path=audio_path,
            sentence=sentence,
            index=index,
            thread_id=thread_id,
        )
    return _add_static_captions(
        initial_segment_path,
        final_segment_path,
        sentence=sentence,
        index=index,
        thread_id=thread_id,
    )


def _add_dynamic_captions(
    initial_segment_path,
    final_segment_path,
    *,
    audio_path,
    sentence,
    index,
    thread_id,
):
    """Add dynamic word-level captions to video."""
    Logger.print_info(f"{thread_id} Adding dynamic captions to video segment.")
    try:
        captions = create_word_level_captions(audio_path, sentence)
        if not captions:
            Logger.print_error(f"{thread_id} Failed to create word-level captions")
            return None, index
    except Exception as e:
        Logger.print_error(f"{thread_id} Error creating word-level captions: {e}")
        return None, index

    with ffmpeg_thread_manager:
        captioned_path = create_dynamic_captions(
            input_video=initial_segment_path,
            captions=captions,
            output_path=final_segment_path,
            min_font_size=32,
            max_font_ratio=1.5,
        )

    if captioned_path:
        Logger.print_info(f"{thread_id} Successfully added dynamic captions")
        return captioned_path, index
    Logger.print_error(
        f"{thread_id} Failed to add captions, using raw video"
    )
    return initial_segment_path, index


def _add_static_captions(
    initial_segment_path,
    final_segment_path,
    *,
    sentence,
    index,
    thread_id,
):
    """Add static captions to video."""
    Logger.print_info(f"{thread_id} Adding static captions to video segment.")
    captions = [CaptionEntry(sentence, 0.0, float("inf"))]
    with ffmpeg_thread_manager:
        captioned_path = create_static_captions(
            input_video=initial_segment_path,
            captions=captions,
            output_path=final_segment_path,
            font_size=40,
        )

    if captioned_path:
        Logger.print_info(f"{thread_id} Successfully added static captions")
        return captioned_path, index
    Logger.print_error(f"{thread_id} Failed to add captions, using raw video")
    return initial_segment_path, index


def _needs_music(config) -> bool:
    """Check whether any music generation is configured."""
    return bool(
        getattr(config, "background_music", None)
        or getattr(config, "closing_credits", None)
    )


def _submit_parallel_tasks(
    executor,
    story,
    *,
    total_segments,
    style,
    tts,
    config,
    skip_generation,
    query_dispatcher,
    story_title,
    output_dir,
    thread_id,
    music_generator,
):
    """Submit all parallel tasks and return futures."""
    futures = []

    # Movie poster task
    _submit_movie_poster_task(
        executor,
        skip_generation=skip_generation,
        story_title=story_title,
        query_dispatcher=query_dispatcher,
        story=story,
        style=style,
        output_dir=output_dir,
        futures=futures,
    )

    # Background music task
    _submit_background_music_task(
        executor,
        music_generator=music_generator,
        config=config,
        output_dir=output_dir,
        skip_generation=skip_generation,
        thread_id=thread_id,
        futures=futures,
    )

    # Closing credits task
    _submit_closing_credits_task(
        executor,
        music_generator=music_generator,
        config=config,
        story=story,
        output_dir=output_dir,
        skip_generation=skip_generation,
        query_dispatcher=query_dispatcher,
        thread_id=thread_id,
        futures=futures,
    )

    # Video segment tasks
    _submit_segment_tasks(
        executor,
        story,
        total_segments=total_segments,
        style=style,
        tts=tts,
        config=config,
        skip_generation=skip_generation,
        query_dispatcher=query_dispatcher,
        output_dir=output_dir,
        futures=futures,
    )

    return futures


def _submit_movie_poster_task(
    executor,
    *,
    skip_generation,
    story_title,
    query_dispatcher,
    story,
    style,
    output_dir,
    futures,
):
    """Submit movie poster generation task."""
    if not skip_generation and story_title and query_dispatcher:
        story_json = json.dumps({"style": style, "title": story_title, "story": story})
        future = executor.submit(
            generate_movie_poster,
            story_json,
            style,
            story_title,
            query_dispatcher=query_dispatcher,
            output_dir=output_dir,
        )
        futures.append(("movie_poster", future))
        return future
    return None


def _submit_background_music_task(
    executor,
    *,
    music_generator,
    config,
    output_dir,
    skip_generation,
    thread_id,
    futures,
):
    """Submit background music generation task."""
    if music_generator and hasattr(config, "background_music") and config.background_music:
        future = executor.submit(
            music_generator.get_background_music,
            config=config,
            output_dir=output_dir,
            skip_generation=skip_generation,
            thread_id=f"{thread_id}_background" if thread_id else "background",
        )
        futures.append(("background_music", future))
        return future
    return None


def _submit_closing_credits_task(
    executor,
    *,
    music_generator,
    config,
    story,
    output_dir,
    skip_generation,
    query_dispatcher,
    thread_id,
    futures,
):
    """Submit closing credits generation task."""
    if music_generator and hasattr(config, "closing_credits") and config.closing_credits:
        future = executor.submit(
            music_generator.get_closing_credits,
            config=config,
            story_text="\n".join(story),
            output_dir=output_dir,
            skip_generation=skip_generation,
            query_dispatcher=query_dispatcher,
            thread_id=f"{thread_id}_credits" if thread_id else "credits",
        )
        futures.append(("closing_credits", future))
        return future
    if hasattr(config, "closing_credits"):
        thread_prefix = f"{thread_id} " if thread_id else ""
        Logger.print_warning(
            f"{thread_prefix}Closing credits configured but no file or prompt provided"
        )
    return None


def _submit_segment_tasks(
    executor,
    story,
    *,
    total_segments,
    style,
    tts,
    config,
    skip_generation,
    query_dispatcher,
    output_dir,
    futures,
):
    """Submit video segment processing tasks."""
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
            output_dir=output_dir,
        )
        segment_futures.append((i, future))
        futures.append(("segment", (i, future)))
    return segment_futures


def _collect_task_results(futures, thread_prefix):
    """Collect and process results from all futures."""
    movie_poster_path = None
    background_music_path = None
    closing_credits_path = None
    closing_credits_lyrics = None
    segments = []
    segment_indices = []

    for task_type, future in futures:
        try:
            if task_type == "movie_poster":
                movie_poster_path = future.result()
                if movie_poster_path is None:
                    Logger.print_warning(
                        f"{thread_prefix}Failed to generate movie poster, "
                        "closing credits may be affected"
                    )

            elif task_type == "background_music":
                background_music_path = future.result()
                if background_music_path is None:
                    Logger.print_warning(
                        f"{thread_prefix}Background music generation failed - "
                        "continuing without background music"
                    )

            elif task_type == "closing_credits":
                closing_credits_path, closing_credits_lyrics = future.result()
                if closing_credits_path is None:
                    Logger.print_error(f"{thread_prefix}Closing credits generation failed")

            elif task_type == "segment":
                segment_index, segment_future = future
                segment = segment_future.result()
                if segment and segment[0]:
                    segments.append(segment[0])
                    segment_indices.append(segment[1])
                else:
                    failed_index = segment[1] if segment else segment_index
                    Logger.print_error(f"{thread_prefix}Failed to process segment {failed_index}")

        except Exception as e:
            Logger.print_error(f"{thread_prefix}Error processing task: {str(e)}")
            if task_type == "background_music":
                Logger.print_warning(
                    f"{thread_prefix}Background music generation failed with error - "
                    "continuing without background music"
                )
                background_music_path = None

    return StoryTaskResults(
        segments=segments,
        segment_indices=segment_indices,
        movie_poster_path=movie_poster_path,
        background_music_path=background_music_path,
        closing_credits_path=closing_credits_path,
        closing_credits_lyrics=closing_credits_lyrics,
    )


def _order_segments(segments, indices):
    """Order segments using their original indices."""
    segments_with_indices = sorted(zip(segments, indices), key=lambda x: x[1])
    return [segment for segment, _ in segments_with_indices]


def process_story(
    tts: GoogleTTS,
    style: str,
    story: list[str],
    output_dir: str,
    config: TTVConfig,
    *,
    skip_generation: bool = False,
    query_dispatcher: Any | None = None,
    story_title: str | None = None,
    thread_id: str | None = None,
) -> tuple[list[str], str | None, str | None, str | None, str | None]:
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
        Logger.print_info(f"{thread_prefix}Processing {total_segments} story segments")

        music_generator = MusicGenerator(config=config) if _needs_music(config) else None

        with concurrent.futures.ThreadPoolExecutor(max_workers=total_segments + 2) as executor:
            futures = _submit_parallel_tasks(
                executor,
                story,
                total_segments=total_segments,
                style=style,
                tts=tts,
                config=config,
                skip_generation=skip_generation,
                query_dispatcher=query_dispatcher,
                story_title=story_title,
                output_dir=output_dir,
                thread_id=thread_id,
                music_generator=music_generator,
            )

            task_results = _collect_task_results(
                futures,
                thread_prefix,
            )

            if not task_results.segments:
                Logger.print_error(f"{thread_prefix}All segments failed to process")
                return None, None, None, None, None

            ordered_segments = _order_segments(
                task_results.segments, task_results.segment_indices
            )

            Logger.print_info(
                f"{thread_prefix}Successfully processed "
                f"{len(ordered_segments)}/{total_segments} segments"
            )

        return (
            ordered_segments,
            task_results.background_music_path,
            task_results.closing_credits_path,
            task_results.movie_poster_path,
            task_results.closing_credits_lyrics,
        )

    except Exception as e:
        Logger.print_error(f"{thread_prefix}Error processing story: {str(e)}")
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
            if "Rate limit exceeded" in str(e):
                Logger.print_error(
                    f"Rate limit exceeded. Retrying in {wait_time} seconds... "
                    f"(Attempt {attempt + 1} of {retries})"
                )
                time.sleep(wait_time)
            else:
                raise e
    raise RuntimeError(
        f"Failed to complete {func.__name__} after {retries} attempts due to rate limiting."
    )


def process_story_segment(
    sentence: str,
    segment_index: int,
    total_segments: int,
    tts_engine: GoogleTTS,
    style: str,
    *,
    query_dispatcher: Any | None = None,
    context: str = "",
    thread_id: str | None = None,
    output_dir: str | None = None,
) -> dict[str, str] | None:
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
    Logger.print_info(f"{thread_prefix}Processing segment {segment_index + 1} of {total_segments}")

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
            output_dir=output_dir,
        )[0]  # get just the path from the tuple
        if not image_path:
            Logger.print_error(
                f"{thread_prefix}Failed to generate image for segment {segment_index + 1}"
            )
            return None

        # Generate audio for segment
        success, audio_path = tts_engine.convert_text_to_speech(text=sentence, thread_id=thread_id)
        if not success or not audio_path:
            Logger.print_error(
                f"{thread_prefix}Failed to generate audio for segment {segment_index + 1}"
            )
            return None

        return {"image": image_path, "audio": audio_path, "text": sentence}

    except Exception as e:
        Logger.print_error(f"{thread_prefix}Error processing segment {segment_index + 1}: {str(e)}")
        return None


def _submit_video_segment_jobs(executor, segments, output_dir, thread_id):
    """Submit video segment creation jobs."""
    futures = []
    for i, segment in enumerate(segments):
        try:
            initial_segment_path = os.path.join(output_dir, f"segment_{i}_initial.mp4")
            future = executor.submit(
                create_video_segment,
                image_path=segment["image"],
                audio_path=segment["audio"],
                output_path=initial_segment_path,
                thread_id=f"{thread_id}_{i}" if thread_id else None,
            )
            futures.append((future, i, segment, initial_segment_path))
        except Exception as e:
            thread_prefix = f"{thread_id} " if thread_id else ""
            Logger.print_error(f"{thread_prefix}Error submitting segment {i + 1}: {str(e)}")
    return futures


def _process_segment_with_captions(future, i, segment, output_dir, thread_id):
    """Process a single segment by adding captions."""
    video_path = future.result()
    if not video_path:
        raise ValueError(f"Failed to create initial video for segment {i + 1}")

    captions = create_word_level_captions(
        segment["audio"],
        segment["text"],
        thread_id=f"{thread_id}_{i}" if thread_id else None,
    )
    if not captions:
        raise ValueError(f"Failed to generate captions for segment {i + 1}")

    final_segment_path = os.path.join(output_dir, f"segment_{i}.mp4")
    captioned_path = create_dynamic_captions(
        input_video=video_path,
        captions=captions,
        output_path=final_segment_path,
        min_font_size=32,
        max_font_ratio=1.5,
    )

    if not captioned_path:
        raise ValueError(f"Failed to add captions to segment {i + 1}")

    return captioned_path


def _concatenate_video_segments(video_segments, output_dir, output_path):
    """Concatenate video segments into final video."""
    list_file = os.path.join(output_dir, "segments.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for segment in video_segments:
            f.write(f"file '{segment}'\n")

    with ffmpeg_thread_manager:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_path,
        ]
        result = subprocess.run(cmd, check=True, capture_output=True)

    if result.returncode != 0:
        raise ValueError(f"Failed to concatenate segments: {result.stderr.decode()}")

    return list_file


def create_video_with_captions(
    segments: list[dict[str, str]], output_path: str, output_dir: str, thread_id: str | None = None
) -> str | None:
    """Create a video with captions from segments.

    Args:
        segments: List of segment dictionaries with paths
        output_path: Path to save final video
        thread_id: Optional thread ID for logging

    Returns:
        Optional[str]: Path to final video if successful
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    video_segments = []
    list_file = None

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = _submit_video_segment_jobs(executor, segments, output_dir, thread_id)

            for future, i, segment, _ in futures:
                try:
                    captioned_path = _process_segment_with_captions(
                        future, i, segment, output_dir, thread_id
                    )
                    video_segments.append(captioned_path)
                except (OSError, ValueError) as e:
                    Logger.print_error(f"{thread_prefix}Error processing segment {i + 1}: {str(e)}")

        if not video_segments:
            raise ValueError("No video segments were created successfully")

        list_file = _concatenate_video_segments(video_segments, output_dir, output_path)

        Logger.print_info(f"{thread_prefix}Successfully created video at {output_path}")
        return output_path

    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(f"{thread_prefix}Error creating video: {str(e)}")
        return None
    finally:
        try:
            if list_file and os.path.exists(list_file):
                os.remove(list_file)
            for segment in video_segments:
                if os.path.exists(segment):
                    os.remove(segment)
        except OSError as e:
            Logger.print_warning(f"{thread_prefix}Error cleaning up temporary files: {str(e)}")


def add_background_music(
    video_path: str, output_path: str, music_generator: MusicGenerator, thread_id: str | None = None
) -> str | None:
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
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
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
            thread_id=thread_id,
        )
        if not music_path:
            raise ValueError("Failed to generate background music")

        # Mix audio streams
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-i",
                music_path,
                "-filter_complex",
                "[1:a]volume=0.3[music];[0:a][music]amix=duration=longest",
                "-c:v",
                "copy",
                output_path,
            ],
            check=True,
            capture_output=True,
        )

        Logger.print_info(f"{thread_prefix}Successfully added background music to video")
        return output_path

    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        Logger.print_error(f"{thread_prefix}Error adding background music: {str(e)}")
        return None
    finally:
        # Cleanup temporary files
        try:
            if os.path.exists(music_path):
                os.remove(music_path)
        except (OSError, UnboundLocalError):
            pass
