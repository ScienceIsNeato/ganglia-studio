"""SunoApi.org implementation for music generation."""

import json
import os
import time
from datetime import datetime

import requests
from ganglia_common.logger import Logger
from ganglia_common.utils.file_utils import get_tempdir
from ganglia_common.utils.retry_utils import exponential_backoff

from ganglia_studio.music.backends.base import MusicBackend
from ganglia_studio.music.backends.suno_interface import SunoInterface


class SunoApiOrgBackend(MusicBackend, SunoInterface):
    """SunoApi.org implementation for music generation."""

    def __init__(self):
        """Initialize the backend with configuration."""
        self.api_base_url = "https://apibox.erweima.ai/api/v1"
        self.api_key = os.getenv("SUNO_API_ORG_KEY")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.audio_directory = get_tempdir() + "/music"
        os.makedirs(self.audio_directory, exist_ok=True)

        Logger.print_info("Initialized Suno API backend")

    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make an API request with retries."""
        timeout = kwargs.pop("timeout", 30)

        def _request():
            response = requests.request(method, endpoint, timeout=timeout, **kwargs)
            if response.status_code == 401:
                Logger.print_warning("Authentication failed (401) - will retry in a moment...")
                time.sleep(2)  # Add a minimum delay before retry
                raise RuntimeError("Authentication failed - retrying...")
            return response

        return exponential_backoff(_request, max_retries=5, initial_delay=5.0)

    def start_generation(
        self,
        prompt: str,
        *,
        with_lyrics: bool = False,
        title: str | None = None,
        tags: str | None = None,
        story_text: str | None = None,
        wait_audio: bool = False,
        query_dispatcher=None,
        model: str = "V3_5",
        duration: int | None = None,
    ) -> str:
        """Start the generation process via API."""
        if not self.api_key:
            raise OSError("Environment variable 'SUNO_API_ORG_KEY' is not set.")
        try:
            model = self._validate_model(model)
            actual_duration = self._get_duration(with_lyrics, duration)
            enhanced_prompt = self._build_enhanced_prompt(prompt, actual_duration, title)
            use_custom_mode = bool(title or tags)

            if use_custom_mode and not self._validate_custom_mode(title, tags, with_lyrics, prompt):
                return None

            data = self._build_request_data(
                enhanced_prompt,
                model=model,
                with_lyrics=with_lyrics,
                story_text=story_text,
                use_custom_mode=use_custom_mode,
                title=title,
                tags=tags,
            )

            return self._submit_generation_request(data)

        except Exception as e:
            Logger.print_error(f"Failed to start generation: {str(e)}")
            return None

    def _validate_model(self, model):
        """Validate and normalize model name."""
        if not model or model not in ["V3_5", "V4"]:
            Logger.print_warning(f"Invalid model '{model}', defaulting to 'V3_5'")
            return "V3_5"
        return model

    def _get_duration(self, with_lyrics, duration):
        """Get appropriate duration based on generation type."""
        if with_lyrics:
            return duration if duration is not None else self.DEFAULT_CREDITS_DURATION
        return duration if duration is not None else 30

    def _build_enhanced_prompt(self, prompt, actual_duration, title):
        """Build enhanced prompt with duration and title."""
        enhanced_prompt = f"Create a {actual_duration}-second {prompt}"
        if title:
            enhanced_prompt = f"{enhanced_prompt} titled '{title}'"
        return enhanced_prompt

    def _validate_custom_mode(self, title, tags, with_lyrics, prompt):
        """Validate custom mode requirements."""
        if not title:
            Logger.print_error("Title is required in custom mode")
            return False
        if not tags:
            Logger.print_error("Style (tags) is required in custom mode")
            return False
        if not with_lyrics and not prompt:
            Logger.print_error("Prompt is required in custom mode for instrumental")
            return False
        return True

    def _build_request_data(
        self,
        enhanced_prompt,
        *,
        model,
        with_lyrics,
        story_text=None,
        use_custom_mode=False,
        title=None,
        tags=None,
    ):
        """Build API request data based on parameters."""
        if with_lyrics and story_text:
            return self._build_lyrical_data(
                enhanced_prompt,
                model=model,
                story_text=story_text,
                use_custom_mode=use_custom_mode,
                title=title,
                tags=tags,
            )
        return self._build_instrumental_data(
            enhanced_prompt,
            model=model,
            use_custom_mode=use_custom_mode,
            title=title,
            tags=tags,
        )

    def _build_lyrical_data(
        self,
        enhanced_prompt,
        *,
        model,
        story_text,
        use_custom_mode=False,
        title=None,
        tags=None,
    ):
        """Build request data for lyrical generation."""
        base_data = {
            "prompt": enhanced_prompt[:3000],
            "lyrics": story_text[:3000],
            "instrumental": False,
            "customMode": use_custom_mode,
            "callBackUrl": "https://example.com/callback",
            "model": model,
        }
        if use_custom_mode:
            base_data["style"] = tags[:200]
            base_data["title"] = title[:80]
        return base_data

    def _build_instrumental_data(
        self,
        enhanced_prompt,
        *,
        model,
        use_custom_mode=False,
        title=None,
        tags=None,
    ):
        """Build request data for instrumental generation."""
        prompt_limit = 3000 if use_custom_mode else 400
        base_data = {
            "prompt": enhanced_prompt[:prompt_limit],
            "instrumental": True,
            "customMode": use_custom_mode,
            "callBackUrl": "https://example.com/callback",
            "model": model,
        }
        if use_custom_mode:
            base_data["style"] = tags[:200]
            base_data["title"] = title[:80]
        return base_data

    def _submit_generation_request(self, data):
        """Submit generation request to API and handle response."""
        response = self._make_api_request(
            "post", f"{self.api_base_url}/generate", headers=self.headers, json=data, timeout=30
        )

        if response.status_code != 200:
            Logger.print_error(f"Failed to start generation: {response.text}")
            return None

        response_data = response.json()
        if (
            response_data.get("code") == 429
            and "credits are insufficient" in response_data.get("msg", "").lower()
        ):
            self._handle_insufficient_credits(response_data)
            raise RuntimeError("Insufficient credits - will retry after delay")

        if response_data.get("code") != 200:
            Logger.print_error(f"API error: {response_data.get('msg')}")
            return None

        job_id = response_data.get("data", {}).get("taskId")
        if job_id:
            self._save_start_time(job_id)
            return job_id

        Logger.print_error("No job ID in response")
        return None

    def _handle_insufficient_credits(self, response_data):
        """Handle insufficient credits error."""
        warning_msg = (
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║                       INSUFFICIENT CREDITS                    ║\n"
            "║                                                              ║\n"
            "║  Your Suno API account is out of credits.                    ║\n"
            "║  Please top up to continue generating music.                 ║\n"
            "║  Will retry after delay.                                     ║\n"
            "║                                                              ║\n"
            f"║  Error: {response_data.get('msg')}                           ║\n"
            "╚══════════════════════════════════════════════════════════════╝"
        )
        Logger.print_warning(warning_msg)

    def check_progress(self, job_id: str) -> tuple[str, float]:
        """Check the progress of a generation job via API."""
        try:
            response = self._make_api_request(
                "get",
                f"{self.api_base_url}/generate/record-info",
                params={"taskId": job_id},
                headers=self.headers,
                timeout=10,
            )

            # Logger.print_info(f"Progress check response: {response.text}") # DEBUG

            if response.status_code != 200:
                return f"Error: HTTP {response.status_code}", 0

            response_data = response.json()
            if response_data.get("code") != 200:
                return f"Error: {response_data.get('msg')}", 0

            generation_data = response_data.get("data", {})
            status = generation_data.get("status", "").upper()
            title = self._extract_title_from_params(generation_data.get("param", "{}"))

            elapsed = time.time() - self._get_start_time(job_id)
            expected_duration = 120
            base_progress = min(99.0, (elapsed / expected_duration) * 100)
            time_status = f"[{int(elapsed)}s/{expected_duration}s]"

            return self._interpret_status(
                status,
                generation_data,
                title=title,
                time_status=time_status,
                base_progress=base_progress,
            )

        except Exception as e:
            Logger.print_error(f"Error checking progress: {str(e)}")
            return f"Error: {str(e)}", 0.0

    def _extract_title_from_params(self, param_str):
        """Extract title from API parameters JSON string."""
        try:
            params = json.loads(param_str)
            return params.get("title", "Untitled")
        except (json.JSONDecodeError, KeyError, TypeError):
            return "Untitled"

    def _interpret_status(self, status, generation_data, *, title, time_status, base_progress):
        """Interpret API status and return progress tuple."""
        status_map = {
            "PENDING": (f"{title} - Initializing {time_status}", min(20.0, base_progress)),
            "TEXT_SUCCESS": (
                f"{title} - Processing lyrics {time_status}",
                min(99.0, base_progress + 20),
            ),
            "PROCESSING": (f"{title} - Processing {time_status}", base_progress),
            "CREATE_TASK_FAILED": (f"{title} - Error: Task creation failed", 0.0),
            "GENERATE_AUDIO_FAILED": (f"{title} - Error: Audio generation failed", 0.0),
            "CALLBACK_EXCEPTION": (f"{title} - Error: Callback failed", 0.0),
            "SENSITIVE_WORD_ERROR": (f"{title} - Error: Contains sensitive words", 0.0),
        }

        if status in ["SUCCESS", "FIRST_SUCCESS"]:
            return self._check_success_state(
                status,
                generation_data,
                title=title,
                time_status=time_status,
            )

        if status in status_map:
            return status_map[status]

        Logger.print_warning(f"Unexpected status '{status}' received from API")
        return f"{title} - {status.lower()} {time_status}", base_progress

    def _check_success_state(self, status, generation_data, *, title, time_status):
        """Check if SUCCESS state has audio URL ready."""
        generation_response = generation_data.get("response") or {}
        suno_data = generation_response.get("sunoData", [])
        if suno_data and suno_data[0].get("streamAudioUrl"):
            Logger.print_info(f"Found stream audio URL in {status} state")
            return "complete", 100.0
        Logger.print_info(f"No stream audio URL yet in {status} state")
        return f"{title} - Finalizing {time_status}", 99.0

    def get_result(self, job_id: str) -> str:
        """Get the result of a completed generation job."""
        try:
            Logger.print_info(f"Getting result for job {job_id}")
            response = self._make_api_request(
                "get",
                f"{self.api_base_url}/generate/record-info",
                params={"taskId": job_id},
                headers=self.headers,
                timeout=10,
            )

            Logger.print_info(f"Result response: {response.text}")

            error_msg = self._validate_result_response(response)
            if error_msg:
                Logger.print_error(error_msg)
                return None

            response_data = response.json()
            audio_url = self._extract_audio_url(response_data)
            if not audio_url:
                return None

            return self._download_audio(audio_url, job_id)

        except Exception as e:
            Logger.print_error(f"Failed to get result: {str(e)}")
            return None

    def _validate_result_response(self, response):
        """Validate response from result API call."""
        if response.status_code != 200:
            return f"Failed to get result: HTTP {response.status_code}"

        response_data = response.json()
        if response_data.get("code") != 200:
            return f"API error: {response_data.get('msg')}"

        return None

    def _extract_audio_url(self, response_data):
        """Extract audio URL from API response data."""
        generation_data = response_data.get("data", {})
        status = generation_data.get("status", "").upper()

        if status not in ["SUCCESS", "FIRST_SUCCESS"]:
            Logger.print_error(f"Generation not in success state: {status}")
            return None

        suno_data = generation_data.get("response", {}).get("sunoData", [])
        if not suno_data:
            Logger.print_error("No suno data in response")
            return None

        audio_url = suno_data[0].get("streamAudioUrl")
        if not audio_url:
            Logger.print_error("No stream audio URL in response")
            return None

        return audio_url

    def generate_instrumental(
        self,
        prompt: str,
        *,
        title: str | None = None,
        tags: str | None = None,
        wait_audio: bool = False,
        duration: int = 30,
        model: str = "V3_5",
    ) -> str:
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
            model=model,
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
        *,
        title: str | None = None,
        tags: str | None = None,
        query_dispatcher=None,
        wait_audio: bool = False,
        duration: int | None = None,
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
            duration=duration,
        )
        if not job_id:
            return None, None

        while True:
            _status, progress = self.check_progress(job_id)
            if progress >= 100:
                result = self.get_result(job_id)
                return result, story_text if result else (None, None)
            time.sleep(5)

    def _download_audio(self, audio_url: str, job_id: str) -> str:
        """Download the generated audio file."""
        try:
            response = self._make_api_request("get", audio_url, stream=True, timeout=30)

            if response.status_code != 200:
                Logger.print_error(f"Failed to download audio: HTTP {response.status_code}")
                return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = os.path.join(self.audio_directory, f"suno_{job_id}_{timestamp}.mp3")

            _total_size = int(response.headers.get("content-length", 0))
            bytes_written = 0

            with open(audio_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        bytes_written += len(chunk)
                        f.write(chunk)

            Logger.print_info("Successfully added background music")
            return audio_path

        except requests.exceptions.Timeout:
            Logger.print_error("Download timed out after 30 seconds")
            Logger.print_error("Failed to add background music")
            return None
        except Exception as e:
            Logger.print_error(f"Failed to download audio: {str(e)}")
            Logger.print_error("Failed to add background music")
            return None

    def _save_start_time(self, job_id: str):
        """Save the start time of a job for progress estimation."""
        path = os.path.join(self.audio_directory, f"{job_id}_start_time")
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(time.time()))

    def _get_start_time(self, job_id: str) -> float:
        """Get the start time of a job for progress estimation."""
        try:
            path = os.path.join(self.audio_directory, f"{job_id}_start_time")
            with open(path, encoding="utf-8") as f:
                return float(f.read().strip())
        except (OSError, ValueError) as e:
            Logger.print_error(f"Failed to get start time for job {job_id}: {e}")
            return time.time()
