"""Abstract base class defining the interface for Suno music generation backends."""

from abc import ABC, abstractmethod

class SunoInterface(ABC):
    """Abstract base class for Suno music generation implementations."""

    @abstractmethod
    def start_generation(self, prompt: str, with_lyrics: bool = False, **kwargs) -> str:
        """Start the generation process.

        Args:
            prompt: The text prompt describing the desired music
            with_lyrics: Whether to generate music with lyrics
            **kwargs: Additional arguments like model, duration, etc.

        Returns:
            str: Job ID for tracking the generation progress
        """
        pass

    @abstractmethod
    def check_progress(self, job_id: str) -> tuple[str, float]:
        """Check the progress of a generation job.

        Args:
            job_id: The ID of the job to check

        Returns:
            tuple[str, float]: Status message and progress percentage (0-100)
        """
        pass

    @abstractmethod
    def get_result(self, job_id: str) -> str:
        """Get the result of a completed generation job.

        Args:
            job_id: The ID of the completed job

        Returns:
            str: Path to the downloaded audio file, or None if failed
        """
        pass

    @abstractmethod
    def generate_instrumental(self, prompt: str, **kwargs) -> str:
        """Generate instrumental music (blocking).

        Args:
            prompt: The text prompt describing the desired music
            **kwargs: Additional arguments like model, duration, etc.

        Returns:
            str: Path to the generated audio file, or None if failed
        """
        pass

    @abstractmethod
    def generate_with_lyrics(self, prompt: str, story_text: str, **kwargs) -> tuple[str, str]:
        """Generate music with lyrics (blocking).

        Args:
            prompt: The text prompt describing the desired music
            story_text: The story text to generate lyrics from
            **kwargs: Additional arguments like model, etc.

        Returns:
            tuple[str, str]: Tuple containing (audio_file_path, lyrics) or (None, None) if failed
        """
        pass
