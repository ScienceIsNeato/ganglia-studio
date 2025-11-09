from .config_loader import load_input
from .story_processor import process_story
from .final_video_generation import assemble_final_video
from ganglia_common.tts.google_tts import GoogleTTS
from ganglia_common.logger import Logger
from ganglia_common.utils.file_utils import get_timestamped_ttv_dir
import traceback

# TODO: remove skip_generation globally, make query_dispatcher required
def text_to_video(config_path, skip_generation=False, tts=None, query_dispatcher=None):
    """
    Convert text to video using the provided configuration.

    Args:
        config_path: Path to the TTV configuration file
        skip_generation: Whether to skip generation of images and audio
        tts: Text-to-speech engine to use (will create one if not provided)
        query_dispatcher: Query dispatcher for AI-assisted generation

    Returns:
        Path to the final video file, or None if generation failed
    """
    try:
        # Create timestamped directory for this run
        ttv_dir = get_timestamped_ttv_dir()

        # Load configuration
        config = load_input(config_path)
        if not config:
            Logger.print_error("Failed to load configuration")
            return None

        # Log loaded config
        Logger.print_info(f"Loaded config: {config}")

        # Log query dispatcher availability
        if query_dispatcher:
            Logger.print_info("Query dispatcher provided: ChatGPTQueryDispatcher")

        # Use provided TTS or initialize a new one
        if not tts:
            Logger.print_info("Initializing GoogleTTS...")
            tts = GoogleTTS()

        # Process story and generate video segments
        video_segments, background_music_path, closing_credits_path, movie_poster_path, closing_credits_lyrics = process_story(
            tts=tts,
            style=config.style,
            story=config.story,
            skip_generation=skip_generation,
            query_dispatcher=query_dispatcher,
            story_title=config.title,
            config=config,
            output_dir=ttv_dir
        )

        # Check for errors (i.e. no video segments)
        if not video_segments:
            Logger.print_error("No video segments generated")
            return None

        # Log paths for debugging
        Logger.print_info(f"Background music path: {background_music_path}")
        Logger.print_info(f"Closing credits path: {closing_credits_path}")
        Logger.print_info(f"Movie poster path: {movie_poster_path}")

        # Assemble final video
        return assemble_final_video(
            video_segments=video_segments,
            output_dir=ttv_dir,
            music_path=background_music_path,
            song_with_lyrics_path=closing_credits_path,
            movie_poster_path=movie_poster_path,
            config=config,
            closing_credits_lyrics=closing_credits_lyrics
        )

    except Exception as e:
        Logger.print_error(f"Error in text_to_video: {str(e)}")
        Logger.print_error(f"Traceback: {traceback.format_exc()}")
        return None
