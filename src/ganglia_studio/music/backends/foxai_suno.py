import os
import time
import json
from datetime import datetime
import requests
from ganglia_studio.music.lyrics_lib import LyricsGenerator
from ganglia_common.logger import Logger
from ganglia_studio.music.backends.base import MusicBackend
from ganglia_studio.music.backends.suno_interface import SunoInterface
from utils import get_tempdir
class FoxAISunoBackend(MusicBackend, SunoInterface):
    """FoxAI's Suno API implementation for music generation."""

    def __init__(self):
        self.api_base_url = 'https://api.sunoaiapi.com/api/v1'
        self.api_key = os.getenv('FOXAI_SUNO_API_KEY')
        if not self.api_key:
            raise EnvironmentError("Environment variable 'FOXAI_SUNO_API_KEY' is not set.")
        self.headers = {
            'api-key': self.api_key,
            'Content-Type': 'application/json'
        }
        self.audio_directory = get_tempdir() + "/music"
        os.makedirs(self.audio_directory, exist_ok=True)

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
        """Start the generation process via API.

        Args:
            prompt: Text description of the desired music
            with_lyrics: Whether to generate with lyrics
            title: Title for the generated song
            tags: Style tags/descriptors for the song
            story_text: Story text for lyric generation
            wait_audio: Whether to wait for audio generation
            query_dispatcher: Query dispatcher for lyric generation
            model: Model to use for generation (chirp-v3-5 or chirp-v4)
            duration: Duration in seconds (default: 30 for instrumental, DEFAULT_CREDITS_DURATION for lyrics)

        Returns:
            str: Job ID for tracking progress, or None if generation fails
        """
        if with_lyrics and story_text:
            return self._start_lyrical_song_job(
                prompt=prompt,
                model=model,
                story_text=story_text,
                query_dispatcher=query_dispatcher,
                title=title,
                tags=tags,
                duration=duration
            )
        else:
            return self._start_instrumental_song_job(
                prompt=prompt,
                model=model,
                title=title,
                tags=tags,
                duration=duration
            )

    def check_progress(self, job_id: str) -> tuple[str, float]:
        """Check the progress of a generation job via API."""
        endpoint = f"{self.api_base_url}/gateway/query?ids={job_id}"

        try:
            response = requests.get(endpoint, headers=self.headers)
            if response.status_code != 200:
                return f"Error: HTTP {response.status_code}", 0

            response_data = response.json()
            if not isinstance(response_data, list):
                return "Error: Invalid response format", 0

            song_data = next((item for item in response_data if item.get('id') == job_id), None)
            if not song_data:
                return "Error: Song data not found", 0

            status = song_data.get('status', '')
            meta_data = song_data.get('meta_data', {})

            # Determine if this is background music or closing credits based on the prompt
            prompt = meta_data.get('prompt', '')
            is_closing_credits = 'with lyrics' in prompt.lower() if prompt else False
            file_type = "closing_credits.mp3" if is_closing_credits else "background_music.mp3"

            if status == 'complete':
                return "Complete", 100
            elif status == 'error':
                error_type = meta_data.get('error_type', 'Unknown error')
                error_message = meta_data.get('error_message', '')
                return f"Error: {error_type} - {error_message}", 0
            else:
                # Estimate progress based on typical generation time
                elapsed = time.time() - self._get_start_time(job_id)
                estimated_progress = min(95, (elapsed / 180) * 100)  # 3 minutes typical time
                return f"{status} ({file_type})", estimated_progress

        except Exception as e:
            return f"Error: {str(e)}", 0

    def get_result(self, job_id: str) -> str:
        """Get the result of a completed generation job."""
        endpoint = f"{self.api_base_url}/gateway/query?ids={job_id}"

        try:
            response = requests.get(endpoint, headers=self.headers)
            if response.status_code != 200:
                return None

            response_data = response.json()
            if not isinstance(response_data, list):
                return None

            song_data = next((item for item in response_data if item.get('id') == job_id), None)
            if not song_data or song_data.get('status') != 'complete':
                return None

            audio_url = song_data.get('audio_url')
            if not audio_url:
                return None

            return self._download_audio(audio_url, job_id)

        except Exception as e:
            Logger.print_error(f"Failed to get result: {str(e)}")
            return None

    def _start_instrumental_song_job(
            self,
            prompt: str,
            model: str,
            title: str = None,
            tags: str = None,
            duration: int = 30
        ) -> str:
        """Start a job for instrumental music generation."""
        endpoint = f"{self.api_base_url}/gateway/generate"

        # Use default 30 seconds for instrumentals if none specified
        actual_duration = duration if duration is not None else 30

        # Map user-friendly model names to API format
        model_mapping = {
            'V3_5': 'chirp-v3-5',
            'V4': 'chirp-v4',
            'chirp-v3-5': 'chirp-v3-5',  # Allow direct API format too
            'chirp-v4': 'chirp-v4'
        }
        
        # Ensure model is set to a valid value
        if not model or model not in model_mapping:
            Logger.print_warning(f"Invalid model '{model}', defaulting to 'chirp-v3-5'")
            model = 'chirp-v3-5'
        else:
            model = model_mapping[model]

        # Enhance prompt with duration and title context
        enhanced_prompt = f"Create a {actual_duration}-second {prompt}"
        if title:
            enhanced_prompt = f"{enhanced_prompt} titled '{title}'"

        data = {
            "prompt": enhanced_prompt,
            "make_instrumental": True,
            "model_version": model,
            "title": title or "Generated Instrumental",
            "tags": tags or "instrumental",
            "duration": actual_duration
        }

        logging_headers = self.headers.copy()
        api_key = self.headers['api-key']
        masked_key = f"{api_key[:2]}{'*' * (len(api_key)-4)}{api_key[-2:]}"
        logging_headers['api-key'] = masked_key
        Logger.print_info(f"Sending request to {endpoint} with data: {data} and headers: {logging_headers}")
        response = requests.post(endpoint, headers=self.headers, json=data)
        Logger.print_info(f"Request completed with status code {response.status_code}")

        if response.status_code != 200:
            try:
                error_detail = response.json()
                Logger.print_error(f"Failed to start instrumental music job. Status: {response.status_code}, Response: {error_detail}")
                if 'detail' in error_detail:
                    Logger.print_error(f"Error detail: {error_detail['detail']}")
                if 'message' in error_detail:
                    Logger.print_error(f"Error message: {error_detail['message']}")
            except json.JSONDecodeError:
                Logger.print_error(f"Failed to start instrumental music job. Status: {response.status_code}, Raw response: {response.text}")
            return None

        response_data = response.json()
        if response_data.get('code') != 0:
            return None

        if "data" in response_data and isinstance(response_data["data"], list):
            job_data = response_data["data"]
            if job_data and "song_id" in job_data[0]:
                song_id = job_data[0]["song_id"]
                self._save_start_time(song_id)
                return song_id

        return None

    def _start_lyrical_song_job(
            self,
            prompt: str,
            model: str,
            story_text: str,
            query_dispatcher,
            title: str = None,
            tags: str = None,
            duration: int = None
        ) -> str:
        """Start a job for music generation with lyrics."""
        try:
            # Get lyrics from query dispatcher
            lyrics_data = query_dispatcher.send_query(story_text) if query_dispatcher else story_text

            # Handle both string and dict responses
            if isinstance(lyrics_data, str):
                try:
                    lyrics_data = json.loads(lyrics_data)
                except json.JSONDecodeError:
                    lyrics_data = {"style": "pop", "lyrics": lyrics_data}

            style = lyrics_data.get('style', 'pop')
            lyrics = lyrics_data.get('text', '') or lyrics_data.get('lyrics', '')

            endpoint = f"{self.api_base_url}/gateway/generate"  # Changed endpoint

            # Use default credits duration if none specified
            actual_duration = duration if duration is not None else self.DEFAULT_CREDITS_DURATION

            # Ensure model is set to a valid value
            if not model or model.lower() not in ['chirp-v3-5', 'chirp-v4']:
                Logger.print_warning(f"Invalid model '{model}', defaulting to 'chirp-v3-5'")
                model = 'chirp-v3-5'

            # Enhance prompt with duration, style, and title context
            enhanced_prompt = f"Create a {actual_duration}-second {style} song"
            if title:
                enhanced_prompt = f"{enhanced_prompt} titled '{title}'"
            enhanced_prompt = f"{enhanced_prompt} with these exact lyrics:\n{lyrics}"

            data = {
                "prompt": enhanced_prompt,  # Use prompt directly
                "make_instrumental": False,  # This is a lyrical song
                "model_version": model,  # Changed from mv to model_version
                "title": title or "Generated Song",
                "tags": tags or style,
                "duration": actual_duration,
                "lyrics": lyrics
            }

            logging_headers = self.headers.copy()
            api_key = self.headers['api-key']
            masked_key = f"{api_key[:2]}{'*' * (len(api_key)-4)}{api_key[-2:]}"
            logging_headers['api-key'] = masked_key
            Logger.print_info(f"Generated lyrics: {lyrics_data}")
            Logger.print_info(f"Sending request to {endpoint} with data: {data} and headers: {logging_headers}")

            response = requests.post(endpoint, headers=self.headers, json=data)
            if response.status_code != 200:
                try:
                    error_detail = response.json()
                    Logger.print_error(f"Failed to start lyrical music job. Status: {response.status_code}, Response: {error_detail}")
                    if 'detail' in error_detail:
                        Logger.print_error(f"Error detail: {error_detail['detail']}")
                    if 'message' in error_detail:
                        Logger.print_error(f"Error message: {error_detail['message']}")
                except json.JSONDecodeError:
                    Logger.print_error(f"Failed to start lyrical music job. Status: {response.status_code}, Raw response: {response.text}")
                return None

            response_data = response.json()
            if response_data.get('code') != 0:
                return None

            if "data" in response_data and isinstance(response_data["data"], list):
                job_data = response_data["data"]
                if job_data and "song_id" in job_data[0]:
                    song_id = job_data[0]["song_id"]
                    self._save_start_time(song_id)
                    return song_id

            return None

        except Exception as e:
            Logger.print_error(f"Failed to start lyrical song job: {str(e)}")
            return None

    def _download_audio(self, audio_url, job_id):
        """Download the generated audio file."""
        try:
            response = requests.get(audio_url)
            if response.status_code != 200:
                return None

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            audio_path = os.path.join(self.audio_directory, f"suno_{job_id}_{timestamp}.mp3")

            with open(audio_path, 'wb') as f:
                f.write(response.content)

            return audio_path

        except Exception as e:
            Logger.print_error(f"Failed to download audio: {str(e)}")
            return None

    def _save_start_time(self, job_id):
        """Save the start time of a job for progress estimation."""
        path = os.path.join(self.audio_directory, f"{job_id}_start_time")
        with open(path, 'w') as f:
            f.write(str(time.time()))

    def _get_start_time(self, job_id):
        """Get the start time of a job for progress estimation."""
        try:
            path = os.path.join(self.audio_directory, f"{job_id}_start_time")
            with open(path, 'r') as f:
                return float(f.read().strip())
        except:
            return time.time()

    def generate_instrumental(self, prompt: str, title: str = None, tags: str = None, wait_audio: bool = False, duration: int = 30, model: str = 'V3_5') -> str:
        """Generate instrumental music from a text prompt.

        Args:
            prompt: The text prompt for music generation
            title: Optional title for the generated music
            tags: Optional list of tags
            wait_audio: Whether to wait for audio generation
            duration: Duration in seconds
            model: Model to use for generation (V3_5 or V4)

        Returns:
            str: Path to the generated audio file or None if generation fails
        """
        # Start generation
        job_id = self.start_generation(
            prompt=prompt,
            with_lyrics=False,
            title=title,
            tags=tags,
            wait_audio=wait_audio,
            duration=duration,
            model=model
        )
        if not job_id:
            Logger.print_error("Failed to start generation")
            return None

        # If wait_audio is False, return the job ID
        if not wait_audio:
            return job_id

        # Poll for completion
        while True:
            status, progress = self.check_progress(job_id)
            Logger.print_info(f"Generation progress: {status} ({progress:.1f}%)")

            if progress >= 100:
                break

            time.sleep(5)  # Wait before checking again

        # Get result
        return self.get_result(job_id)

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
        """Generate music with lyrics and return both the audio file path and lyrics.

        Args:
            prompt: The text prompt describing the desired music
            story_text: The story text to generate lyrics from
            title: Title for the generated song
            tags: Style tags/descriptors for the song
            query_dispatcher: Query dispatcher for lyric generation
            wait_audio: Whether to wait for audio generation
            duration: Duration in seconds (default: DEFAULT_CREDITS_DURATION)

        Returns:
            tuple[str, str]: Tuple containing (audio_file_path, lyrics) or (None, None) if generation fails
        """
        job_id = self.start_generation(
            prompt=prompt,
            with_lyrics=True,
            story_text=story_text,
            title=title,
            tags=tags,
            query_dispatcher=query_dispatcher,
            wait_audio=wait_audio,
            duration=duration
        )
        if not job_id:
            return None, None

        # Get the lyrics that were generated for this job
        lyrics = None
        try:
            lyrics_generator = LyricsGenerator()
            lyrics_json = lyrics_generator.generate_song_lyrics(story_text, query_dispatcher)
            lyrics_data = json.loads(lyrics_json)
            lyrics = lyrics_data.get('lyrics', '')
        except Exception as e:
            Logger.print_error(f"Failed to extract lyrics: {str(e)}")
            return None, None

        while True:
            status, progress = self.check_progress(job_id)
            if progress >= 100:
                result = self.get_result(job_id)
                return result, lyrics if result else (None, None)
            time.sleep(5)
