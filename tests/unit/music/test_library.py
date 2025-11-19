import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from ganglia_studio.music.music_lib import MusicGenerator, _exponential_backoff
from ganglia_studio.music.backends.meta import MetaMusicBackend
from ganglia_studio.music.backends.suno_api_org import SunoApiOrgBackend
from ganglia_studio.music.backends.foxai_suno import FoxAISunoBackend
from ganglia_studio.video.config_loader import MusicOptions, TTVConfig
from typing import Union
from ganglia_common.logger import Logger

@pytest.fixture
def temp_output_dir():
    """Fixture to provide a temporary output directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

class MockSunoBackend(SunoApiOrgBackend):
    def __init__(self, should_fail=False, fail_count=None):
        self.should_fail = should_fail
        self.fail_count = fail_count  # Number of times to fail before succeeding
        self.attempts = 0
        self.start_generation_called = False
        self.check_progress_called = False
        self.get_result_called = False

    def start_generation(self, prompt: str, **kwargs) -> str:
        """Mock start_generation that handles retries correctly."""
        self.start_generation_called = True
        self.attempts += 1
        self.with_lyrics = kwargs.get('with_lyrics', False)

        if self.fail_count is not None:
            # Succeed after fail_count failures
            if self.attempts <= self.fail_count:
                Logger.print_info(f"Mock failing attempt {self.attempts}/{self.fail_count}")
                return None
            Logger.print_info(f"Mock succeeding after {self.fail_count} failures")
            return "mock_job_id"

        if self.should_fail:
            return None
        return "mock_job_id"

    def check_progress(self, job_id: str) -> tuple[str, float]:
        self.check_progress_called = True
        if self.should_fail:
            return "Failed", 0
        return "Complete", 100

    def get_result(self, job_id: str) -> Union[str, tuple[str, str]]:
        self.get_result_called = True
        if self.should_fail:
            return None if not self.with_lyrics else (None, None)
        return ("/mock/path/to/audio.mp3", None) if self.with_lyrics else "/mock/path/to/audio.mp3"

class MockMetaBackend(MetaMusicBackend):
    def __init__(self):
        self.start_generation_called = False
        self.check_progress_called = False
        self.get_result_called = False

    def start_generation(self, prompt: str, **kwargs) -> str:
        self.start_generation_called = True
        return "mock_meta_job_id"

    def check_progress(self, job_id: str) -> tuple[str, float]:
        self.check_progress_called = True
        return "Complete", 100

    def get_result(self, job_id: str) -> str:
        self.get_result_called = True
        return "/mock/path/to/meta_audio.wav"

class DurationTestBackend(SunoApiOrgBackend):
    def __init__(self):
        self.last_duration = None
        self.start_generation_called = False
        self.check_progress_called = False
        self.get_result_called = False

    def start_generation(self, prompt: str, **kwargs) -> str:
        self.start_generation_called = True
        self.last_duration = kwargs.get('duration')
        return "mock_job_id"

    def check_progress(self, job_id: str) -> tuple[str, float]:
        self.check_progress_called = True
        return "Complete", 100

    def get_result(self, job_id: str) -> Union[str, tuple[str, str]]:
        self.get_result_called = True
        return "/mock/path/to/audio.mp3"

class ErrorTestBackend(SunoApiOrgBackend):
    def __init__(self, error_type=RuntimeError):
        self.error_type = error_type
        self.start_generation_called = False
        self.check_progress_called = False
        self.get_result_called = False

    def start_generation(self, prompt: str, **kwargs) -> str:
        self.start_generation_called = True
        raise self.error_type("Test error")

    def check_progress(self, job_id: str) -> tuple[str, float]:
        self.check_progress_called = True
        raise self.error_type("Test error")

    def get_result(self, job_id: str) -> Union[str, tuple[str, str]]:
        self.get_result_called = True
        raise self.error_type("Test error")

class ThreadTestBackend(SunoApiOrgBackend):
    def __init__(self):
        self.start_generation_called = False
        self.check_progress_called = False
        self.get_result_called = False

    def start_generation(self, prompt: str, **kwargs) -> str:
        self.start_generation_called = True
        return "mock_job_id"

    def check_progress(self, job_id: str) -> tuple[str, float]:
        self.check_progress_called = True
        return "Complete", 100

    def get_result(self, job_id: str) -> Union[str, tuple[str, str]]:
        self.get_result_called = True
        return "/mock/path/to/audio.mp3"

class RetryTestBackend(SunoApiOrgBackend):
    def __init__(self, error_sequence):
        self.error_sequence = error_sequence
        self.attempts = 0
        self.start_generation_called = False
        self.check_progress_called = False
        self.get_result_called = False

    def start_generation(self, prompt: str, **kwargs) -> str:
        self.start_generation_called = True
        if self.attempts < len(self.error_sequence):
            error = self.error_sequence[self.attempts]
            self.attempts += 1
            raise error
        self.attempts += 1
        return "mock_job_id"

    def check_progress(self, job_id: str) -> tuple[str, float]:
        self.check_progress_called = True
        return "Complete", 100

    def get_result(self, job_id: str) -> Union[str, tuple[str, str]]:
        self.get_result_called = True
        return "/mock/path/to/audio.mp3"

def test_instrumental_generation_with_parameters():
    """Test instrumental generation with all optional parameters."""
    suno_backend = MockSunoBackend(should_fail=False)
    generator = MusicGenerator(backend=suno_backend)

    result = generator.generate_instrumental(
        prompt="test prompt",
        duration=30,
        title="Test Song",
        tags=["test", "music"],
        output_path=os.path.join(tempfile.gettempdir(), "output.mp3")
    )

    assert suno_backend.start_generation_called
    assert result == ("/mock/path/to/audio.mp3", None)

def test_instrumental_generation_no_fallback_needed():
    """Test that Meta fallback is not used when Suno succeeds."""
    suno_backend = MockSunoBackend(should_fail=False)
    meta_backend = MockMetaBackend()

    generator = MusicGenerator(backend=suno_backend)
    generator.fallback_backend = meta_backend

    with patch('time.sleep'):  # Mock sleep to speed up test
        result = generator.generate_instrumental("test prompt")

    # Verify Suno was called
    assert suno_backend.start_generation_called
    assert suno_backend.check_progress_called
    assert suno_backend.get_result_called

    # Verify Meta was not called
    assert not meta_backend.start_generation_called
    assert not meta_backend.check_progress_called
    assert not meta_backend.get_result_called

    assert result == ("/mock/path/to/audio.mp3", None)

def test_lyrics_generation_with_parameters():
    """Test lyrics generation with all optional parameters."""
    suno_backend = MockSunoBackend(should_fail=False)
    generator = MusicGenerator(backend=suno_backend)

    query_dispatcher = Mock()
    result = generator.generate_with_lyrics(
        prompt="test prompt",
        story_text="test story",
        title="Test Song",
        tags=["test", "music"],
        output_path=os.path.join(tempfile.gettempdir(), "output.mp3"),
        query_dispatcher=query_dispatcher
    )

    assert suno_backend.start_generation_called
    # The get_result method returns a tuple for lyrics generation
    assert result[0] == "/mock/path/to/audio.mp3"
    assert result[1] is None

def test_lyrics_generation_no_fallback():
    """Test that Meta fallback is not used for lyrics generation, even if Suno fails."""
    suno_backend = MockSunoBackend(should_fail=True)
    meta_backend = MockMetaBackend()

    generator = MusicGenerator(backend=suno_backend)
    generator.fallback_backend = meta_backend

    result = generator.generate_with_lyrics("test prompt", "test story")

    # Verify Suno was attempted
    assert suno_backend.start_generation_called

    # Verify Meta was not called
    assert not meta_backend.start_generation_called
    assert not meta_backend.check_progress_called
    assert not meta_backend.get_result_called

    assert result == (None, None)  # Should return (None, None) when failing without fallback

def test_parameter_passing_through_retry_chain():
    """Test that parameters are correctly passed through the retry chain."""
    suno_backend = MockSunoBackend(fail_count=1)  # Fail once then succeed
    generator = MusicGenerator(backend=suno_backend)

    with patch('time.sleep'):  # Mock sleep to speed up test
        result = generator.generate_instrumental(
            prompt="test prompt",
            duration=30,
            title="Test Song",
            tags=["test", "music"],
            output_path=os.path.join(tempfile.gettempdir(), "output.mp3")
        )

    assert suno_backend.attempts == 2  # One failure + one success
    assert result == ("/mock/path/to/audio.mp3", None)

def test_exponential_backoff():
    """Test that exponential backoff generates reasonable delays."""
    # Test a few attempts
    max_delay = 5  # Updated to match the actual max delay
    delays = [_exponential_backoff(i, max_delay=max_delay) for i in range(5)]

    # Verify delays increase exponentially until max delay
    for i in range(1, len(delays)):
        if delays[i-1] < max_delay:  # Only check increase if previous delay was below max
            assert delays[i] > delays[i-1], "Delays should increase exponentially until max"
        else:
            # Once we hit max delay, subsequent delays should be at max (with jitter)
            assert abs(delays[i] - max_delay) <= max_delay * 0.1, \
                f"Delay {i} should be close to max_delay (got {delays[i]})"

    # Verify max delay is respected
    large_attempt_delay = _exponential_backoff(10, max_delay=max_delay)
    assert large_attempt_delay <= max_delay * 1.1  # Allow for 10% jitter

    # Verify actual delay sequence is reasonable
    expected_base_delays = [1, 2, 4, 5, 5]  # Last two are capped at max_delay
    for i, delay in enumerate(delays):
        # Allow for 10% jitter in either direction
        assert abs(delay - expected_base_delays[i]) <= expected_base_delays[i] * 0.1, \
            f"Delay {i} should be close to {expected_base_delays[i]} (got {delay})"

def test_instrumental_generation_string_result():
    """Test that string results from generate_instrumental are handled correctly."""
    class StringResultGenerator(MusicGenerator):
        def __init__(self):
            """Override to avoid initializing real backends."""
            self.backend = None
            self.fallback_backend = None

        def generate_instrumental(self, *args, **kwargs) -> str:
            """Override to return a string directly."""
            return "/mock/path/to/audio.mp3"

    generator = StringResultGenerator()

    # This should fail with "too many values to unpack" because we're trying to unpack
    # a string as if it were a tuple
    result = generator.get_background_music_from_prompt(
        prompt="test prompt",
        output_dir=os.path.join(tempfile.gettempdir(), "output"),
        thread_id="test"
    )

    assert result == "/mock/path/to/audio.mp3"

def test_closing_credits_string_result():
    """Test that string results from generate_with_lyrics are handled correctly."""
    class StringResultGenerator(MusicGenerator):
        def __init__(self):
            """Override to avoid initializing real backends."""
            self.backend = None
            self.fallback_backend = None

        def generate_with_lyrics(self, *args, **kwargs) -> str:
            """Override to return a string directly."""
            return "/mock/path/to/credits.mp3"

    generator = StringResultGenerator()

    # Test the closing credits path handling
    result_path, result_lyrics = generator.get_closing_credits_from_prompt(
        prompt="test prompt",
        story_text="test story",
        output_dir=os.path.join(tempfile.gettempdir(), "output"),
        thread_id="test"
    )

    assert result_path == "/mock/path/to/credits.mp3"
    assert result_lyrics is None

def test_output_path_handling():
    """Test that output paths are correctly handled when copying files."""
    class OutputPathGenerator(MusicGenerator):
        def __init__(self):
            self.backend = None
            self.fallback_backend = None

        def generate_instrumental(self, *args, **kwargs) -> tuple[str, None]:
            """Return a tuple with a path and None."""
            return "/mock/source/path.mp3", None

    generator = OutputPathGenerator()

    with patch('shutil.copy2') as mock_copy:
        # Mock copy2 to simulate successful copy
        mock_copy.return_value = None

        result = generator.get_background_music_from_prompt(
            prompt="test prompt",
            output_dir=os.path.join(tempfile.gettempdir(), "output"),
            thread_id="test"
        )

        # Verify the copy was attempted with correct paths
        mock_copy.assert_called_once_with(
            "/mock/source/path.mp3",
            os.path.join(tempfile.gettempdir(), "output", "background_music.mp3")
        )
        # Result should be the output path since copy succeeded
        assert result == os.path.join(tempfile.gettempdir(), "output", "background_music.mp3")

def test_output_path_copy_failure():
    """Test graceful handling of file copy failures."""
    class OutputPathGenerator(MusicGenerator):
        def __init__(self):
            self.backend = None
            self.fallback_backend = None

        def generate_instrumental(self, *args, **kwargs) -> tuple[str, None]:
            """Return a tuple with a path and None."""
            return "/mock/source/path.mp3", None

    generator = OutputPathGenerator()

    with patch('shutil.copy2') as mock_copy:
        # Mock copy2 to simulate failure
        mock_copy.side_effect = IOError("Mock copy failure")

        result = generator.get_background_music_from_prompt(
            prompt="test prompt",
            output_dir=os.path.join(tempfile.gettempdir(), "output"),
            thread_id="test"
        )

        # Verify the copy was attempted
        mock_copy.assert_called_once()
        # Result should fall back to the source path since copy failed
        assert result == "/mock/source/path.mp3"

def test_backend_initialization_from_config(monkeypatch):
    """Test that backends are correctly initialized from config."""
    # Mock API key environment variable for FoxAI backend
    monkeypatch.setenv("FOXAI_SUNO_API_KEY", "test-key")
    
    # Test Meta backend initialization
    config_meta = TTVConfig(
        style="test",
        story=[],
        title="test",
        music=MusicOptions(backend="meta"),
    )
    generator_meta = MusicGenerator(config=config_meta)
    assert isinstance(generator_meta.backend, MetaMusicBackend)
    assert generator_meta.fallback_backend is None

    # Test Suno backend initialization (default)
    config_suno = TTVConfig(
        style="test",
        story=[],
        title="test",
        music=MusicOptions(backend="suno"),
    )
    generator_suno = MusicGenerator(config=config_suno)
    assert isinstance(generator_suno.backend, SunoApiOrgBackend)
    assert isinstance(generator_suno.fallback_backend, FoxAISunoBackend)

    # Test default when no backend specified
    config_default = TTVConfig(
        style="test",
        story=[],
        title="test"
    )
    generator_default = MusicGenerator(config=config_default)
    assert isinstance(generator_default.backend, SunoApiOrgBackend)
    assert isinstance(generator_default.fallback_backend, FoxAISunoBackend)

def test_duration_handling():
    """Test that duration is correctly passed through to backends."""
    backend = DurationTestBackend()
    generator = MusicGenerator(backend=backend)

    # Test default duration
    generator.get_background_music_from_prompt(
        prompt="test prompt",
        output_dir=os.path.join(tempfile.gettempdir(), "output")
    )
    assert backend.last_duration == 30  # Default duration

    # Test custom duration
    generator.generate_instrumental(
        prompt="test prompt",
        duration=45
    )
    assert backend.last_duration == 45  # Custom duration

@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, IOError, TimeoutError])
def test_error_propagation(error_type):
    """Test that errors from backends are properly propagated."""
    generator = MusicGenerator(backend=ErrorTestBackend(error_type))
    with patch('time.sleep'):  # Mock sleep to speed up test
        result = generator.generate_instrumental("test prompt")
    assert result == (None, None)

def test_retry_behavior():
    """Test retry behavior with a simple error sequence."""
    # Test a single retry that succeeds
    generator = MusicGenerator(backend=RetryTestBackend([RuntimeError("Test error")]))
    with patch('time.sleep'):  # Mock sleep to speed up test
        result = generator.generate_instrumental("test prompt")
        assert result == ("/mock/path/to/audio.mp3", None)
        assert generator.backend.attempts == 2  # One failure + one success

def test_retry_exhaustion():
    """Test that retries are exhausted after MAX_RETRIES attempts."""
    # Reduce MAX_RETRIES temporarily for the test
    original_max_retries = MusicGenerator.MAX_RETRIES
    MusicGenerator.MAX_RETRIES = 2
    try:
        generator = MusicGenerator(backend=RetryTestBackend([RuntimeError("Test error")] * 3))
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = generator.generate_instrumental("test prompt")
            assert result == (None, None)
            assert generator.backend.attempts == 2  # Should stop after MAX_RETRIES
    finally:
        MusicGenerator.MAX_RETRIES = original_max_retries

def test_retry_with_fallback():
    """Test that fallback is used after retries are exhausted."""
    # Reduce MAX_RETRIES temporarily for the test
    original_max_retries = MusicGenerator.MAX_RETRIES
    MusicGenerator.MAX_RETRIES = 2
    try:
        suno_backend = MockSunoBackend(should_fail=True)
        meta_backend = MockMetaBackend()
        generator = MusicGenerator(backend=suno_backend)
        generator.fallback_backend = meta_backend

        with patch('time.sleep'):  # Mock sleep to speed up test
            result = generator.generate_instrumental("test prompt")
            assert suno_backend.attempts == 2  # Should stop after MAX_RETRIES
            assert meta_backend.start_generation_called  # Should fall back to meta
            assert result == ("/mock/path/to/meta_audio.wav", None)
    finally:
        MusicGenerator.MAX_RETRIES = original_max_retries

def test_thread_id_propagation():
    """Test that thread IDs are correctly propagated through logging."""
    backend = ThreadTestBackend()
    generator = MusicGenerator(backend=backend)

    with patch('ganglia_common.logger.Logger.print_info') as mock_log:
        generator.get_background_music_from_prompt(
            prompt="test prompt",
            output_dir=os.path.join(tempfile.gettempdir(), "output"),
            thread_id="test_thread"
        )

        # Verify thread ID is included in log messages that should have it
        thread_id_messages = [
            call.args[0] for call in mock_log.call_args_list
            if "Successfully generated" in call.args[0] or
               "Failed to copy" in call.args[0]
        ]
        assert thread_id_messages, "No thread ID messages found"
        for message in thread_id_messages:
            assert "test_thread" in message, f"Thread ID not found in message: {message}"
