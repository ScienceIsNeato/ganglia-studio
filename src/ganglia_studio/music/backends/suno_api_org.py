"""SunoApi.org implementation for music generation."""

import os
import time
from datetime import datetime
import requests
from ganglia_common.logger import Logger
from ganglia_studio.music.backends.base import MusicBackend
from ganglia_studio.music.backends.suno_interface import SunoInterface
from ganglia_common.utils.file_utils import get_tempdir
from ganglia_common.utils.retry_utils import exponential_backoff

class SunoApiOrgBackend(MusicBackend, SunoInterface):
    """SunoApi.org implementation for music generation."""

    def __init__(self):
        """Initialize the backend with configuration."""
        self.api_base_url = 'https://apibox.erweima.ai/api/v1'
        self.api_key = os.getenv('SUNO_API_ORG_KEY')

        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        self.audio_directory = get_tempdir() + "/music"
        os.makedirs(self.audio_directory, exist_ok=True)

        Logger.print_info("Initialized Suno API backend")

    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make an API request with retries."""
        def _request():
            response = requests.request(method, endpoint, **kwargs)
            if response.status_code == 401:
                Logger.print_warning(f"Authentication failed (401) - will retry in a moment...")
                time.sleep(2)  # Add a minimum delay before retry
                raise Exception("Authentication failed - retrying...")
            return response
        return exponential_backoff(_request, max_retries=5, initial_delay=5.0)

    def start_generation(
            self,
            prompt: str,
            with_lyrics: bool = False,
            title: str = None,
            tags: str = None,
            story_text: str = None,
            wait_audio: bool = False,
            query_dispatcher = None,
            model: str = 'V3_5',
            duration: int = None
        ) -> str:
        """Start the generation process via API."""
        if not self.api_key:
            raise EnvironmentError("Environment variable 'SUNO_API_ORG_KEY' is not set.")
        try:
            # Ensure model is set to a valid value
            if not model or model not in ['V3_5', 'V4']:
                Logger.print_warning(f"Invalid model '{model}', defaulting to 'V3_5'")
                model = 'V3_5'

            # Use appropriate duration based on type
            if with_lyrics:
                actual_duration = duration if duration is not None else self.DEFAULT_CREDITS_DURATION
            else:
                actual_duration = duration if duration is not None else 30

            # Enhance prompt with duration and title context
            enhanced_prompt = f"Create a {actual_duration}-second {prompt}"
            if title:
                enhanced_prompt = f"{enhanced_prompt} titled '{title}'"

            # Determine if we should use custom mode based on parameters
            use_custom_mode = bool(title or tags)

            # Validate custom mode requirements
            if use_custom_mode:
                if not title:
                    Logger.print_error("Title is required in custom mode")
                    return None
                if not tags:
                    Logger.print_error("Style (tags) is required in custom mode")
                    return None
                if not with_lyrics and not prompt:
                    Logger.print_error("Prompt is required in custom mode for instrumental")
                    return None

            # Add lyrics to prompt if provided
            if with_lyrics and story_text:
                if use_custom_mode:
                    # In custom mode, story_text is sent separately
                    data = {
                        "prompt": enhanced_prompt[:3000],  # Limit prompt to 3000 chars
                        "style": tags[:200],  # Limit style to 200 chars
                        "title": title[:80],  # Limit title to 80 chars
                        "lyrics": story_text[:3000],  # Limit lyrics to 3000 chars
                        "instrumental": False,
                        "customMode": True,
                        "callBackUrl": "https://example.com/callback",
                        "model": model  # Add model parameter
                    }
                else:
                    # In non-custom mode, send story_text as lyrics
                    data = {
                        "prompt": enhanced_prompt[:3000],  # Limit prompt to 3000 chars
                        "lyrics": story_text[:3000],  # Limit lyrics to 3000 chars
                        "instrumental": False,
                        "customMode": False,
                        "callBackUrl": "https://example.com/callback",
                        "model": model  # Add model parameter
                    }
            else:
                # Handle instrumental cases
                if use_custom_mode:
                    data = {
                        "prompt": enhanced_prompt[:3000],  # Limit prompt to 3000 chars
                        "style": tags[:200],  # Limit style to 200 chars
                        "title": title[:80],  # Limit title to 80 chars
                        "instrumental": True,
                        "customMode": True,
                        "callBackUrl": "https://example.com/callback",
                        "model": model  # Add model parameter
                    }
                else:
                    data = {
                        "prompt": enhanced_prompt[:400],  # Limit prompt to 400 chars
                        "instrumental": True,
                        "customMode": False,
                        "callBackUrl": "https://example.com/callback",
                        "model": model  # Add model parameter
                    }

            response = self._make_api_request(
                'post',
                f"{self.api_base_url}/generate",
                headers=self.headers,
                json=data,
                timeout=30
            )

            if response.status_code != 200:
                Logger.print_error(f"Failed to start generation: {response.text}")
                return None

            response_data = response.json()
            if response_data.get('code') == 429 and "credits are insufficient" in response_data.get('msg', '').lower():
                warning_msg = """
╔════════════════════════════════════════════════════════════════════╗
║                       INSUFFICIENT CREDITS                          ║
║                                                                    ║
║  Your Suno API account has run out of credits.                    ║
║  Please top up your credits to continue generating music.          ║
║  Will retry after delay.                                          ║
║                                                                    ║
║  Error: {msg}                                                      ║
╚════════════════════════════════════════════════════════════════════╝
""".format(msg=response_data.get('msg'))
                Logger.print_warning(warning_msg)
                # Raise an exception to trigger retry
                raise RuntimeError("Insufficient credits - will retry after delay")
            elif response_data.get('code') != 200:  # Check other API response codes
                Logger.print_error(f"API error: {response_data.get('msg')}")
                return None

            job_id = response_data.get('data', {}).get('taskId')  # Updated to use taskId

            if job_id:
                self._save_start_time(job_id)
                return job_id

            Logger.print_error("No job ID in response")
            return None

        except Exception as e:
            Logger.print_error(f"Failed to start generation: {str(e)}")
            return None

    def check_progress(self, job_id: str) -> tuple[str, float]:
        """Check the progress of a generation job via API."""
        try:
            response = self._make_api_request(
                'get',
                f"{self.api_base_url}/generate/record-info",
                params={"taskId": job_id},
                headers=self.headers,
                timeout=10
            )

            # Logger.print_info(f"Progress check response: {response.text}") # DEBUG

            if response.status_code != 200:
                return f"Error: HTTP {response.status_code}", 0

            response_data = response.json()
            if response_data.get('code') != 200:
                return f"Error: {response_data.get('msg')}", 0

            generation_data = response_data.get('data', {})
            status = generation_data.get('status', '').upper()

            # Get title for status message
            param_str = generation_data.get('param', '{}')
            try:
                import json
                params = json.loads(param_str)
                title = params.get('title', 'Untitled')
            except:
                title = 'Untitled'

            # Calculate elapsed time and progress
            elapsed = time.time() - self._get_start_time(job_id)
            expected_duration = 120  # 2 minutes expected duration
            base_progress = min(99.0, (elapsed / expected_duration) * 100)
            time_status = f"[{int(elapsed)}s/{expected_duration}s]"

            # Check for success states first
            if status in ['SUCCESS', 'FIRST_SUCCESS']:
                generation_response = generation_data.get('response') or {}
                suno_data = generation_response.get('sunoData', [])
                if suno_data and suno_data[0].get('streamAudioUrl'):
                    Logger.print_info(f"Found stream audio URL in {status} state")
                    return "complete", 100.0
                Logger.print_info(f"No stream audio URL yet in {status} state")
                return f"{title} - Finalizing {time_status}", 99.0

            # Handle other known states
            if status == 'PENDING':
                return f"{title} - Initializing {time_status}", min(20.0, base_progress)
            elif status == 'TEXT_SUCCESS':
                return f"{title} - Processing lyrics {time_status}", min(99.0, base_progress + 20)
            elif status == 'PROCESSING':
                return f"{title} - Processing {time_status}", base_progress
            elif status == 'CREATE_TASK_FAILED':
                return f"{title} - Error: Task creation failed", 0.0
            elif status == 'GENERATE_AUDIO_FAILED':
                return f"{title} - Error: Audio generation failed", 0.0
            elif status == 'CALLBACK_EXCEPTION':
                return f"{title} - Error: Callback failed", 0.0
            elif status == 'SENSITIVE_WORD_ERROR':
                return f"{title} - Error: Contains sensitive words", 0.0
            else:
                # Log unexpected status
                Logger.print_warning(f"Unexpected status '{status}' received from API")
                return f"{title} - {status.lower()} {time_status}", base_progress

        except Exception as e:
            Logger.print_error(f"Error checking progress: {str(e)}")
            return f"Error: {str(e)}", 0.0

    def get_result(self, job_id: str) -> str:
        """Get the result of a completed generation job."""
        try:
            Logger.print_info(f"Getting result for job {job_id}")
            response = self._make_api_request(
                'get',
                f"{self.api_base_url}/generate/record-info",
                params={"taskId": job_id},
                headers=self.headers,
                timeout=10
            )

            Logger.print_info(f"Result response: {response.text}")

            if response.status_code != 200:
                Logger.print_error(f"Failed to get result: HTTP {response.status_code}")
                return None

            response_data = response.json()
            if response_data.get('code') != 200:
                Logger.print_error(f"API error: {response_data.get('msg')}")
                return None

            generation_data = response_data.get('data', {})
            status = generation_data.get('status', '').upper()

            # Accept both success states
            if status not in ['SUCCESS', 'FIRST_SUCCESS']:
                Logger.print_error(f"Generation not in success state: {status}")
                return None

            # Get the audio URL from sunoData
            suno_data = generation_data.get('response', {}).get('sunoData', [])
            if not suno_data:
                Logger.print_error("No suno data in response")
                return None

            audio_url = suno_data[0].get('streamAudioUrl')
            if not audio_url:
                Logger.print_error("No stream audio URL in response")
                return None

            return self._download_audio(audio_url, job_id)

        except Exception as e:
            Logger.print_error(f"Failed to get result: {str(e)}")
            return None

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
        """Generate music with lyrics (blocking)."""
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

        while True:
            status, progress = self.check_progress(job_id)
            if progress >= 100:
                result = self.get_result(job_id)
                return result, story_text if result else (None, None)
            time.sleep(5)

    def _download_audio(self, audio_url: str, job_id: str) -> str:
        """Download the generated audio file."""
        try:
            response = self._make_api_request(
                'get',
                audio_url,
                stream=True,
                timeout=30
            )

            if response.status_code != 200:
                Logger.print_error(f"Failed to download audio: HTTP {response.status_code}")
                return None

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            audio_path = os.path.join(self.audio_directory, f"suno_{job_id}_{timestamp}.mp3")

            total_size = int(response.headers.get('content-length', 0))
            bytes_written = 0

            with open(audio_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        bytes_written += len(chunk)
                        f.write(chunk)

            Logger.print_info("Successfully added background music")
            return audio_path

        except requests.exceptions.Timeout:
            Logger.print_error(f"Download timed out after 30 seconds")
            Logger.print_error("Failed to add background music")
            return None
        except Exception as e:
            Logger.print_error(f"Failed to download audio: {str(e)}")
            Logger.print_error("Failed to add background music")
            return None

    def _save_start_time(self, job_id: str):
        """Save the start time of a job for progress estimation."""
        path = os.path.join(self.audio_directory, f"{job_id}_start_time")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(str(time.time()))

    def _get_start_time(self, job_id: str) -> float:
        """Get the start time of a job for progress estimation."""
        try:
            path = os.path.join(self.audio_directory, f"{job_id}_start_time")
            with open(path, 'r', encoding='utf-8') as f:
                return float(f.read().strip())
        except (IOError, ValueError) as e:
            Logger.print_error(f"Failed to get start time for job {job_id}: {e}")
            return time.time()
