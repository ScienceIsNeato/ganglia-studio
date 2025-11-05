from abc import ABC, abstractmethod
import time

class MusicBackend(ABC):
    """Base class for music generation backends."""

    # Default duration for credits music in seconds
    DEFAULT_CREDITS_DURATION = 60

    @abstractmethod
    def generate_instrumental(self, prompt: str, title: str = None, tags: str = None, wait_audio: bool = False, duration: int = 30) -> str:
        """Generate instrumental music from a text prompt.

        Args:
            prompt: Text description of the desired music
            title: Title for the generated song
            tags: Style tags/descriptors for the song
            wait_audio: Whether to wait for audio generation
            duration: Duration in seconds (default: 30)

        Returns:
            str: Path to the generated audio file.
        """
        pass

    @abstractmethod
    def generate_with_lyrics(
            self,
            prompt: str,
            story_text: str,
            title: str = None,
            tags: str = None,
            query_dispatcher = None,
            wait_audio: bool = False,
            duration: int = None
        ) -> tuple[str, str]:
        """Generate music with lyrics from a text prompt and story.

        Args:
            prompt: Text description of the desired music style
            story_text: Story text to generate lyrics from
            title: Title for the generated song
            tags: Style tags/descriptors for the song
            query_dispatcher: Query dispatcher for lyric generation
            wait_audio: Whether to wait for audio generation
            duration: Duration in seconds (default: DEFAULT_CREDITS_DURATION)

        Returns:
            tuple[str, str]: Tuple containing (audio_file_path, lyrics) or (None, None) if generation fails
        """
        pass

    @abstractmethod
    def start_generation(
            self,
            prompt: str,
            with_lyrics: bool = False,
            title: str = None,
            tags: str = None,
            story_text: str = None,
            wait_audio: bool = False,
            query_dispatcher = None,
            model: str = 'chirp-v3-5',
            duration: int = None
        ) -> str:
        """Start the generation process and return a job ID or identifier.

        Args:
            prompt: Text description of the desired music
            with_lyrics: Whether to generate with lyrics
            title: Title for the generated song
            tags: Style tags/descriptors for the song
            story_text: Story text for lyric generation
            wait_audio: Whether to wait for audio generation
            query_dispatcher: Query dispatcher for lyric generation
            model: Model to use for generation (default: chirp-v3-5)
            duration: Duration in seconds (default: 30 for instrumental, DEFAULT_CREDITS_DURATION for lyrics)

        Returns:
            str: Job ID for tracking progress, or None if generation fails
        """
        pass

    @abstractmethod
    def check_progress(self, job_id: str) -> tuple[str, float]:
        """Check the progress of a generation job.

        Args:
            job_id: The job ID to check progress for

        Returns:
            tuple[str, float]: Status message and progress percentage (0-100)
        """
        pass

    @abstractmethod
    def get_result(self, job_id: str) -> str:
        """Get the result of a completed generation job.

        Args:
            job_id: The job ID to get results for

        Returns:
            str: Path to the generated audio file, or None if failed
        """
        pass

    def wait_for_completion(self, job_id: str, timeout: int = 300, interval: int = 5) -> str:
        """Wait for a generation job to complete.

        Args:
            job_id: Job ID from start_generation
            timeout: Maximum time to wait in seconds
            interval: Time between status checks in seconds

        Returns:
            Path to the generated audio file, or None if generation failed/timed out
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            status, progress = self.check_progress(job_id)
            print(f"\nStatus: {status}")
            print(f"Progress: {progress:.1f}%")

            if status == 'complete':
                return self.get_result(job_id)

            time.sleep(interval)

        return None
