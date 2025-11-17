"""Meta's MusicGen backend implementation for audio generation from text prompts.

This module provides a backend implementation for Meta's MusicGen model, allowing for
text-to-music generation with features like audio looping and progress tracking.
"""

# Standard library imports
import json
import os
import subprocess
import threading
import time
from datetime import datetime

# Third-party imports
import soundfile as sf
import torch

# Local imports
from ganglia_common.logger import Logger
from ganglia_common.utils.file_utils import get_tempdir
from transformers import AutoProcessor, MusicgenForConditionalGeneration

from ganglia_studio.music.backends.base import MusicBackend

# Set environment variables to avoid warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TORCH_WARN_COPY_TENSOR"] = "0"  # Suppress tensor copy warning


class MetaMusicBackend(MusicBackend):
    """Meta's MusicGen implementation for music generation."""

    def __init__(self):
        """Initialize the Meta MusicGen model and processor."""
        self.model = None
        self.processor = None
        self.model_name = "facebook/musicgen-small"
        self.sample_rate = 32000
        self.audio_directory = os.path.join(get_tempdir(), "music")
        self.progress_directory = os.path.join(get_tempdir(), "progress")
        os.makedirs(self.audio_directory, exist_ok=True)
        os.makedirs(self.progress_directory, exist_ok=True)
        self.active_jobs = {}  # job_id -> thread

    def _ensure_model_loaded(self):
        """Ensure the model and processor are loaded."""
        if self.model is None:
            Logger.print_info(f"Loading MusicGen model and processor from {self.model_name}")

            # Set environment variables to avoid warnings
            os.environ["TOKENIZERS_PARALLELISM"] = "false"

            # Initialize model with specific dtype and attention implementation
            self.model = MusicgenForConditionalGeneration.from_pretrained(
                self.model_name,
                attn_implementation="eager",  # Fix for scaled_dot_product_attention warning
                torch_dtype=torch.float32,  # Fix for tensor construction warning
                use_safetensors=True,  # Use safetensors to avoid tensor copy warnings
            )
            self.processor = AutoProcessor.from_pretrained(self.model_name)

            if torch.cuda.is_available():
                Logger.print_info("Moving model to CUDA")
                self.model = self.model.to("cuda")
            else:
                Logger.print_info("CUDA not available, using CPU")

    def start_generation(
        self, prompt: str, with_lyrics: bool = False, title: str = None, tags: str = None, **kwargs
    ) -> str:
        """Start the generation process in a separate thread.

        Args:
            prompt: The text prompt for music generation
            with_lyrics: Whether to generate with lyrics
            title: Title for the generated song (optional)
            tags: Style tags/descriptors for the song (optional)
            **kwargs: Additional parameters including story_text for lyrics

        Returns:
            str: A unique job ID for tracking generation progress
        """
        job_id = f"musicgen_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(prompt)}"
        progress_file = os.path.join(self.progress_directory, f"{job_id}.json")

        # Initialize progress file
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "status": "Starting",
                    "progress": 0,
                    "output_path": None,
                    "error": None,
                    "title": title,
                    "tags": tags,
                },
                f,
            )

        # Start generation thread
        thread = threading.Thread(
            target=self._generation_thread, args=(job_id, prompt), kwargs=kwargs
        )
        thread.start()
        self.active_jobs[job_id] = thread

        return job_id

    def check_progress(self, job_id: str) -> tuple[str, float]:
        """Check the progress of a generation job."""
        progress_file = os.path.join(self.progress_directory, f"{job_id}.json")

        try:
            with open(progress_file, encoding="utf-8") as f:
                data = json.load(f)
                return data["status"], data["progress"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return "Error reading progress", 0

    def get_result(self, job_id: str) -> str:
        """Get the result of a completed generation job."""
        progress_file = os.path.join(self.progress_directory, f"{job_id}.json")

        try:
            with open(progress_file, encoding="utf-8") as f:
                data = json.load(f)
                if data.get("error"):
                    Logger.print_error(f"Generation failed: {data['error']}")
                    return None
                return data.get("output_path")
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _update_progress(
        self,
        job_id: str,
        status: str,
        progress: float,
        *,
        output_path: str | None = None,
        error: str | None = None,
    ):
        """Update the progress file for a job."""
        progress_file = os.path.join(self.progress_directory, f"{job_id}.json")
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "status": status,
                    "progress": progress,
                    "output_path": output_path,
                    "error": error,
                },
                f,
            )

    def _generation_thread(self, job_id: str, prompt: str, **kwargs):
        """Thread function for generating audio."""
        try:
            self._update_progress(job_id, "Loading model", 0)
            self._ensure_model_loaded()

            inputs = self._prepare_model_inputs(prompt)
            duration_seconds = kwargs.get("duration_seconds", 30)
            generation_duration = min(25, duration_seconds)

            audio_data = self._generate_audio_with_progress(
                job_id, inputs, generation_duration, duration_seconds
            )

            temp_clip_path, final_path = self._save_audio_clip(prompt, audio_data)

            if duration_seconds > generation_duration:
                final_path = self._create_looped_audio(
                    temp_clip_path, final_path, duration_seconds, generation_duration
                )
            else:
                os.rename(temp_clip_path, final_path)

            self._update_progress(job_id, "Complete", 100, final_path)

        except Exception as e:
            Logger.print_error(f"Generation failed: {str(e)}")
            self._update_progress(job_id, "Failed", 0, error=str(e))

        finally:
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]

    def _prepare_model_inputs(self, prompt):
        """Prepare model inputs from prompt."""
        self._update_progress("", "Processing prompt", 10)
        inputs = self.processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )

        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}

        return inputs

    def _generate_audio_with_progress(self, job_id, inputs, generation_duration, duration_seconds):
        """Generate audio with progress tracking."""
        self._update_progress(job_id, "Starting generation", 20)
        Logger.print_info(f"Generating {duration_seconds:.1f} seconds of audio")

        max_new_tokens = int(generation_duration * 50)

        generation_complete = threading.Event()
        progress_thread = threading.Thread(
            target=self._progress_updater,
            args=(job_id, generation_complete, generation_duration),
        )
        progress_thread.start()

        audio_values = self.model.generate(
            **inputs, do_sample=True, guidance_scale=3, max_new_tokens=max_new_tokens
        )

        generation_complete.set()
        progress_thread.join()

        self._update_progress(job_id, "Processing audio", 98)
        audio_data = audio_values.cpu().numpy().squeeze()
        if len(audio_data.shape) == 1:
            audio_data = audio_data.reshape(1, -1)

        return audio_data

    def _save_audio_clip(self, prompt, audio_data):
        """Save audio data to temporary clip file."""
        self._update_progress("", "Saving audio", 99)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_prompt = "".join(c if c.isalnum() else "_" for c in prompt)[:50]

        temp_clip_path = os.path.join(
            self.audio_directory, f"musicgen_temp_{sanitized_prompt}_{timestamp}.wav"
        )
        final_path = os.path.join(
            self.audio_directory, f"musicgen_{sanitized_prompt}_{timestamp}.wav"
        )

        sf.write(temp_clip_path, audio_data.T, self.sample_rate)
        return temp_clip_path, final_path

    def _create_looped_audio(self, temp_clip_path, final_path, duration_seconds, generation_duration):
        """Create looped audio with crossfade for extended duration."""
        num_loops = int(duration_seconds / generation_duration) + 1
        crossfade_duration = min(3, generation_duration / 4)

        filter_str = self._build_crossfade_filter(num_loops, crossfade_duration, duration_seconds)
        cmd = self._build_ffmpeg_loop_command(
            temp_clip_path, final_path, num_loops, filter_str
        )

        try:
            subprocess.run(cmd, check=True, capture_output=True)
            os.remove(temp_clip_path)
            return final_path
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode()
            Logger.print_error(f"Failed to create looped audio: {error_msg}")
            return temp_clip_path

    def _build_crossfade_filter(self, num_loops, crossfade_duration, duration_seconds):
        """Build ffmpeg crossfade filter string."""
        filter_complex = []

        for i in range(num_loops - 1):
            if i == 0:
                fade_str = f"[0:a][1:a]acrossfade=d={crossfade_duration}:c1=tri:c2=tri[f1];"
            else:
                fade_str = (
                    f"[f{i}][{i + 1}:a]acrossfade=d={crossfade_duration}:c1=tri:c2=tri[f{i + 1}];"
                )
            filter_complex.append(fade_str)

        filter_str = "".join(filter_complex)
        filter_out = f"[f{num_loops - 1}]atrim=0:{duration_seconds}[out]"
        return filter_str + filter_out

    def _build_ffmpeg_loop_command(self, temp_clip_path, final_path, num_loops, filter_str):
        """Build ffmpeg command for looping audio with crossfade."""
        cmd = ["ffmpeg", "-y"]
        for _ in range(num_loops):
            cmd.extend(["-i", temp_clip_path])

        cmd.extend(["-filter_complex", filter_str, "-map", "[out]", final_path])
        return cmd

    def _progress_updater(
        self, job_id: str, complete_event: threading.Event, target_duration: float
    ):
        """Update progress periodically while generation is running."""
        start_time = time.time()

        # Calculate token generation rate (tokens/second) based on model size
        # Based on measured completion time: 350 tokens in 42.9s ≈ 8.2 tokens/second
        tokens_per_second = 8

        # Total tokens we expect to generate
        total_tokens = int(target_duration * 50)  # 50 tokens per second of audio

        while not complete_event.is_set():
            elapsed = time.time() - start_time
            estimated_tokens = min(total_tokens, int(elapsed * tokens_per_second))
            progress = min(95, (estimated_tokens / total_tokens) * 100)

            self._update_progress(job_id, "Generating audio", progress)

            time.sleep(0.5)  # Update every half second

    def generate_instrumental(self, prompt: str, **kwargs) -> str:
        """Generate instrumental music from a text prompt."""
        return self.start_generation(prompt, **kwargs)

    def generate_with_lyrics(self, prompt: str, story_text: str, **kwargs) -> str:
        """Generate music with consideration for lyrics/story text."""
        return self.start_generation(prompt, story_text=story_text, **kwargs)
