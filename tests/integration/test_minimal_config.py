"""Test the TTV pipeline with a minimal configuration file."""
# Standard library imports
import logging
import os
import subprocess
import pytest

# Local application imports
from ganglia_studio.video.ttv import text_to_video
from tests.test_helpers import validate_gcs_upload

logger = logging.getLogger(__name__)

# Path to the test config files
GENERATED_PIPELINE_CONFIG = "tests/integration/test_data/generated_pipeline_config.json"
SERVICE_ACCOUNT_PATH = "/Users/pacey/Downloads/halloween2023-0a131e14c55e.json"

@pytest.mark.skip(reason="Minimal test covered by generated_pipeline_config.json")
def test_minimal_ttv_config(tmp_path):
    """Test the TTV pipeline with a minimal configuration file."""
    # Skip if GCS credentials are not configured
    bucket_name = os.getenv('GCP_BUCKET_NAME')
    project_name = os.getenv('GCP_PROJECT_NAME')
    if not (bucket_name and project_name):
        pytest.skip("GCS credentials not configured")

    # Create test audio files
    test_audio_dir = tmp_path / "test_audio"
    test_audio_dir.mkdir(parents=True)

    # Create a simple audio file for testing
    background_music_path = test_audio_dir / "background_music.mp3"
    closing_credits_path = test_audio_dir / "closing_credits.mp3"

    # Create dummy audio files using ffmpeg
    for audio_path in [background_music_path, closing_credits_path]:
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "5", "-q:a", "9", "-acodec", "libmp3lame", str(audio_path)
        ], check=True, capture_output=True)

    # Create a test config file
    config_path = tmp_path / "test_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(f"""
        {{
            "style": "test style",
            "story": ["Test story line 1", "Test story line 2"],
            "title": "Test Title",
            "caption_style": "static",
            "background_music": {{
                "file": "{str(background_music_path)}",
                "prompt": null
            }},
            "closing_credits": {{
                "file": "{str(closing_credits_path)}",
                "prompt": null
            }}
        }}
        """)

    # Run the pipeline
    result = text_to_video(str(config_path))

    # Verify the result
    assert result is not None, "Pipeline execution failed"
    assert os.path.exists(result), f"Final video file does not exist at {result}"

    # Verify the file was uploaded to GCS
    validate_gcs_upload(bucket_name, project_name)


    # Clean up the uploaded file
    # uploaded_file.delete()


