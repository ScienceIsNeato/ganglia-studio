"""Unit tests for the SunoApi.org backend implementation."""

import json
from unittest.mock import patch, MagicMock, mock_open
import pytest
from ganglia_studio.music.backends.suno_api_org import SunoApiOrgBackend
import time

@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv('SUNO_API_ORG_KEY', 'test_api_key')
    return monkeypatch

@pytest.fixture
def mock_exponential_backoff(monkeypatch):
    """Mock exponential backoff to eliminate delays in tests."""
    def side_effect(func, max_retries=5, *args, **kwargs):
        """Execute the function with retries but no delays."""
        attempts = 0
        while attempts < max_retries:
            try:
                return func()
            except Exception as e:
                attempts += 1
                if attempts == max_retries:
                    raise e
                # No sleep, just continue to next attempt
                continue

    monkeypatch.setattr('ganglia_studio.music.backends.suno_api_org.exponential_backoff', side_effect)
    return side_effect

@pytest.fixture
def backend(mock_env, tmp_path, mock_exponential_backoff):
    """Create a SunoApiOrgBackend instance with mocked environment."""
    with patch('ganglia_studio.music.backends.suno_api_org.get_tempdir', return_value=str(tmp_path)):
        return SunoApiOrgBackend()

def test_start_generation_instrumental(backend):
    """Test starting instrumental generation."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "PENDING"
        }
    }

    with patch('requests.request', return_value=mock_response) as mock_request:
        job_id = backend.start_generation(
            prompt="test prompt",
            with_lyrics=False,
            title="Test Song",
            tags="rock electronic",
            duration=45
        )

        assert job_id == "test_job_id"
        mock_request.assert_called_once()

        # Verify request data
        call_args = mock_request.call_args
        assert call_args[0][0] == "post"  # First arg is method
        assert call_args[0][1] == "https://apibox.erweima.ai/api/v1/generate"  # Second arg is endpoint
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_api_key"

        sent_data = json.loads(json.dumps(call_args[1]["json"]))
        assert "Create a 45-second test prompt" in sent_data["prompt"]
        assert sent_data["instrumental"] is True
        assert sent_data["customMode"] is True

def test_start_generation_with_lyrics(backend):
    """Test starting generation with lyrics."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "PENDING"
        }
    }

    with patch('requests.request', return_value=mock_response) as mock_request:
        job_id = backend.start_generation(
            prompt="test prompt",
            with_lyrics=True,
            title="Test Song",
            tags="pop vocal",
            story_text="Test story for lyrics",
            duration=60
        )

        assert job_id == "test_job_id"
        mock_request.assert_called_once()

        # Verify request data
        call_args = mock_request.call_args
        assert call_args[0][0] == "post"  # First arg is method
        assert call_args[0][1] == "https://apibox.erweima.ai/api/v1/generate"  # Second arg is endpoint
        assert call_args[1]["headers"]["Authorization"] == "Bearer test_api_key"

        sent_data = json.loads(json.dumps(call_args[1]["json"]))
        assert "Create a 60-second test prompt" in sent_data["prompt"]
        assert sent_data["instrumental"] is False
        assert sent_data["customMode"] is True
        assert sent_data["lyrics"] == "Test story for lyrics"

def test_check_progress(backend):
    """Test checking generation progress."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "TEXT_SUCCESS",
            "param": '{"title": "Test Song"}',
            "response": {
                "taskId": "test_job_id",
                "sunoData": [{
                    "id": "test_song_id",
                    "streamAudioUrl": "https://example.com/test.mp3",
                    "title": "Test Song",
                    "duration": 45
                }]
            }
        }
    }

    with patch('requests.request', return_value=mock_response) as mock_request:
        with patch('time.time', return_value=1000):  # Mock current time
            with patch.object(backend, '_get_start_time', return_value=980):  # Mock start time 20s ago
                status, progress = backend.check_progress("test_job_id")

                assert "Test Song" in status
                assert "Processing lyrics" in status
                assert progress > 0
                mock_request.assert_called_once()

def test_get_result(backend):
    """Test getting generation result."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "FIRST_SUCCESS",
            "response": {
                "taskId": "test_job_id",
                "sunoData": [{
                    "id": "test_song_id",
                    "streamAudioUrl": "https://example.com/test.mp3",
                    "title": "Test Song",
                    "duration": 45
                }]
            }
        }
    }

    mock_download_response = MagicMock()
    mock_download_response.status_code = 200
    mock_download_response.headers = {"content-length": "1000"}
    mock_download_response.iter_content.return_value = [b"test audio data"]
    mock_download_response.ok = True

    with patch('requests.request', side_effect=[mock_response, mock_download_response]) as mock_request:
        with patch('builtins.open', mock_open()) as mock_file:
            result = backend.get_result("test_job_id")

            assert result is not None
            assert mock_request.call_count == 2
            mock_file.assert_called_once()

def test_generate_instrumental_success(backend):
    """Test successful instrumental generation flow."""
    # Mock the API responses for the full generation flow
    mock_start_response = MagicMock()
    mock_start_response.status_code = 200
    mock_start_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "PENDING"
        }
    }

    mock_check_response = MagicMock()
    mock_check_response.status_code = 200
    mock_check_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "FIRST_SUCCESS",
            "param": '{"title": "Test Instrumental"}',
            "response": {
                "taskId": "test_job_id",
                "sunoData": [{
                    "id": "test_song_id",
                    "streamAudioUrl": "https://example.com/test.mp3",
                    "title": "Test Instrumental",
                    "duration": 45
                }]
            }
        }
    }

    mock_result_response = MagicMock()
    mock_result_response.status_code = 200
    mock_result_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "FIRST_SUCCESS",
            "response": {
                "taskId": "test_job_id",
                "sunoData": [{
                    "id": "test_song_id",
                    "streamAudioUrl": "https://example.com/test.mp3",
                    "title": "Test Instrumental",
                    "duration": 45
                }]
            }
        }
    }

    mock_download_response = MagicMock()
    mock_download_response.status_code = 200
    mock_download_response.headers = {"content-length": "1000"}
    mock_download_response.iter_content.return_value = [b"test audio data"]
    mock_download_response.ok = True

    with patch('requests.request', side_effect=[mock_start_response, mock_check_response, mock_result_response, mock_download_response]) as mock_request:
        with patch('builtins.open', mock_open()) as mock_file:
            with patch.object(backend, '_get_start_time', return_value=980):  # Mock start time
                with patch('time.sleep'):  # Mock sleep to skip waiting
                    # Start the generation
                    job_id = backend.generate_instrumental(
                        prompt="test instrumental",
                        title="Test Instrumental",
                        tags="electronic"
                    )

                    assert job_id == "test_job_id"

                    # Wait for completion by polling
                    max_wait = 30  # Maximum wait time in seconds
                    start_time = time.time()
                    while True:
                        status, progress = backend.check_progress(job_id)
                        if progress >= 100:
                            break
                        if time.time() - start_time > max_wait:
                            pytest.fail("Generation timed out")
                        time.sleep(1)

                    # Get the final result
                    result = backend.get_result(job_id)
                    assert result is not None
                    assert mock_request.call_count == 4
                    mock_file.assert_called()

def test_generate_with_lyrics_success(backend):
    """Test successful generation with lyrics flow."""
    # Mock the API responses for the full generation flow
    mock_start_response = MagicMock()
    mock_start_response.status_code = 200
    mock_start_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "PENDING"
        }
    }

    mock_check_response = MagicMock()
    mock_check_response.status_code = 200
    mock_check_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "FIRST_SUCCESS",
            "param": '{"title": "Test Song"}',
            "response": {
                "taskId": "test_job_id",
                "sunoData": [{
                    "id": "test_song_id",
                    "streamAudioUrl": "https://example.com/test.mp3",
                    "title": "Test Song",
                    "duration": 45,
                    "lyrics": "Test lyrics"
                }]
            }
        }
    }

    mock_result_response = MagicMock()
    mock_result_response.status_code = 200
    mock_result_response.json.return_value = {
        "code": 200,
        "msg": "success",
        "data": {
            "taskId": "test_job_id",
            "status": "FIRST_SUCCESS",
            "response": {
                "taskId": "test_job_id",
                "sunoData": [{
                    "id": "test_song_id",
                    "streamAudioUrl": "https://example.com/test.mp3",
                    "title": "Test Song",
                    "duration": 45,
                    "lyrics": "Test lyrics"
                }]
            }
        }
    }

    mock_download_response = MagicMock()
    mock_download_response.status_code = 200
    mock_download_response.headers = {"content-length": "1000"}
    mock_download_response.iter_content.return_value = [b"test audio data"]
    mock_download_response.ok = True

    with patch('requests.request', side_effect=[mock_start_response, mock_check_response, mock_result_response, mock_download_response]) as mock_request:
        with patch('builtins.open', mock_open()) as mock_file:
            with patch.object(backend, '_get_start_time', return_value=980):  # Mock start time
                with patch('time.sleep'):  # Mock sleep to skip waiting
                    # Start the generation
                    result_path, story_text = backend.generate_with_lyrics(
                        prompt="test song",
                        story_text="Test story for lyrics",
                        title="Test Song",
                        tags="pop"
                    )

                    # generate_with_lyrics returns (file_path, story_text), not (job_id, story_text)
                    # It's a blocking call that handles polling internally
                    assert result_path is not None
                    assert result_path.endswith('.mp3')
                    assert 'test_job_id' in result_path  # Job ID is part of the filename
                    assert story_text == "Test story for lyrics"
                    
                    # Verify the expected number of API calls were made
                    assert mock_request.call_count == 4  # start + check + result + download
                    mock_file.assert_called()  # Verify file was written

def test_exponential_backoff_retries(backend, mock_exponential_backoff):
    """Test that exponential backoff retries work correctly without delays."""
    mock_response_success = MagicMock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"code": 200, "msg": "success", "data": {"taskId": "test_job_id"}}

    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 401

    # Mock requests to fail twice then succeed
    responses = [mock_response_fail, mock_response_fail, mock_response_success]

    with patch('requests.request', side_effect=responses) as mock_request:
        job_id = backend.start_generation(
            prompt="test prompt",
            with_lyrics=False,
            title="Test Song",
            tags="cinematic"
        )

        assert job_id == "test_job_id"
        assert mock_request.call_count == 3  # Should have tried 3 times

        # Verify all calls were made with the same parameters
        for call in mock_request.call_args_list:
            assert call[0][0] == "post"  # Method
            assert call[0][1] == "https://apibox.erweima.ai/api/v1/generate"  # Endpoint
