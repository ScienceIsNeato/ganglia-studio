"""Integration tests for the TTV pipeline.

This module contains tests that verify the end-to-end functionality of the
text-to-video pipeline, including video generation, audio synchronization,
and output validation.
"""

# Standard library imports
import logging
import subprocess
import sys
import os

# Third-party imports
import pytest

# Local application imports
from utils import get_tempdir
from tests.integration.test_data.config_generator import generate_config
from tests.test_helpers import (
    validate_audio_video_durations,
    validate_final_video_path,
    validate_total_duration,
    validate_closing_credits_duration,
    validate_segment_count,
    validate_background_music,
    validate_gcs_upload,
    validate_caption_accuracy,
    get_output_dir_from_logs
)
from social_media.youtube_client import YouTubeClient

logger = logging.getLogger(__name__)

@pytest.mark.costly
def test_generated_pipeline_execution():
    """Test execution of TTV pipeline with generated content (music, images).

    This test verifies:
    1. DALL-E generated images
    2. Audio generation and synchronization
    3. Background music integration
    4. Closing credits generation and assembly
    5. Final video compilation and validation
    6. GCS upload validation
    7. Caption accuracy validation
    """
    # Skip if GCS credentials are not configured
    bucket_name = os.getenv('GCP_BUCKET_NAME')
    project_name = os.getenv('GCP_PROJECT_NAME')
    if not (bucket_name and project_name):
        pytest.skip("GCS credentials not configured")

    print("\n=== Starting Generated Pipeline Integration Test ===")

    # Generate a config file
    config_path = os.path.join(get_tempdir(), "generated_pipeline_config.json")
    generate_config(config_path)

    # Run the TTV command and capture output
    command = f"PYTHONUNBUFFERED=1 python ganglia.py --text-to-video --ttv-config {config_path}"
    output = ""  # Initialize output here
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in iter(process.stdout.readline, b''):
        decoded_line = line.decode('utf-8')
        print(decoded_line, end='')  # Print to console
        sys.stdout.flush()  # Ensure immediate output
        output += decoded_line
    process.stdout.close()
    process.wait()

    # Save output to a file for debugging
    with open(get_tempdir() + "/test_output.log", "w", encoding='utf-8') as f:
        f.write(output)

    # Get output directory from logs
    output_dir = get_output_dir_from_logs(output)
    print(f"Using TTV directory: {output_dir}")

    # Validate all segments are present
    validate_segment_count(output, config_path)

    # Validate segment durations
    total_video_duration = validate_audio_video_durations(
        config_path, output
    )

    # Validate background music was added successfully
    validate_background_music(output)

    # Add closing credits duration to total video duration
    closing_credits_duration = validate_closing_credits_duration(output)
    total_video_duration += closing_credits_duration

    # Validate final video
    final_video_path = validate_final_video_path(output_dir)
    validate_total_duration(final_video_path, total_video_duration)

    # Validate caption accuracy
    validate_caption_accuracy(output, config_path)

    # Validate GCS upload
    validate_gcs_upload(bucket_name, project_name)

    print("\n=== Test Complete ===\n")

    # Upload test results to YouTube if enabled
    if os.getenv('UPLOAD_INTEGRATION_TESTS_TO_YOUTUBE', 'false').lower() == 'true':
        # Restore stdout/stderr
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        # Post results to YouTube if we have a final video
        if final_video_path and os.path.exists(final_video_path):
            try:
                client = YouTubeClient()
                video_url = client.create_video_post(
                    title="GANGLIA Integration Test: TTV Pipeline (Generated)",
                    video_path=final_video_path,
                    additional_info={
                        "python_version": sys.version,
                        "platform": sys.platform,
                        "environment": "local",
                        "test_type": "integration"
                    },
                    config_path=config_path
                )
                print(f"\nIntegration test results uploaded to YouTube: {video_url}")
            except Exception as e:
                print(f"Failed to upload integration test results to YouTube: {e}")
    else:
        print("YouTube upload disabled")
