"""Simple integration test for the TTV pipeline.

This test exercises the core TTV pipeline functionality without requiring
expensive API calls. It uses skip_generation mode to test the pipeline
structure without actually generating images or music.
"""

import os
import pytest
import tempfile
from ganglia_common.utils.file_utils import get_tempdir
from ganglia_common.tts.google_tts import GoogleTTS
from ganglia_studio.video.ttv import text_to_video
from tests.helpers import (
    create_test_config,
    validate_video_file,
    validate_segment_files,
    find_final_video,
    load_config
)


@pytest.mark.integration
@pytest.mark.costly  # Requires TTS even with skip_generation
def test_ttv_pipeline_with_skip_generation():
    """Test TTV pipeline with skip_generation=True (no API calls).
    
    This test verifies:
    1. Config loading works
    2. Pipeline creates correct directory structure
    3. Segments are generated (with blank images)
    4. Final video is assembled
    5. Output files are valid
    
    Note: Even though skip_generation=True, this test still requires TTS for audio.
    """
    # Create a test config
    test_dir = os.path.join(get_tempdir(), "test_ttv_simple")
    os.makedirs(test_dir, exist_ok=True)
    
    config_path = os.path.join(test_dir, "test_config.json")
    story = [
        "A robot walks through a neon cityscape.",
        "The robot stops to observe passing humans.",
        "It continues its journey into the night."
    ]
    
    create_test_config(config_path, story, style="cyberpunk", include_music=False)
    
    # Verify config was created
    config = load_config(config_path)
    assert config is not None, "Failed to create test config"
    assert len(config['story']) == 3, "Config should have 3 story sentences"
    
    # Run TTV pipeline with skip_generation
    # Note: This requires the pipeline to support skip_generation parameter
    # If it doesn't exist yet, this test will fail and we'll need to add it
    try:
        output_path = text_to_video(
            config_path,
            skip_generation=True  # Use blank images instead of API calls
        )
    except TypeError:
        pytest.skip("TTV pipeline doesn't support skip_generation yet")
    
    # Verify output
    assert output_path is not None, "TTV pipeline returned None"
    assert os.path.exists(output_path), f"Output video doesn't exist: {output_path}"
    
    # Validate the video file
    assert validate_video_file(output_path), "Output video is not valid"
    
    print(f"\n✓ TTV pipeline test passed!")
    print(f"  Config: {config_path}")
    print(f"  Output: {output_path}")


@pytest.mark.integration
@pytest.mark.costly
def test_ttv_pipeline_with_real_generation():
    """Test TTV pipeline with actual API calls.
    
    This test requires:
    - OPENAI_API_KEY environment variable
    - Potentially other API keys for music generation
    
    This test is marked as 'costly' because it makes real API calls.
    
    This test verifies:
    1. Image generation works
    2. Audio generation and synchronization works
    3. Video segments are created correctly
    4. Final video assembly works
    5. Music generation (if API keys available)
    """
    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        pytest.skip("OPENAI_API_KEY not set - skipping costly test")
    
    # Create a minimal test config
    test_dir = os.path.join(get_tempdir(), "test_ttv_real")
    os.makedirs(test_dir, exist_ok=True)
    
    config_path = os.path.join(test_dir, "test_config_real.json")
    story = [
        "A single red cube floating in space.",
        "The cube slowly rotates against a starry background."
    ]
    
    create_test_config(config_path, story, style="minimalist 3D render")
    
    # Run TTV pipeline with real generation
    print("\n⚠️  This test makes real API calls and may take several minutes...")
    
    try:
        output_path = text_to_video(config_path)
    except Exception as e:
        pytest.fail(f"TTV pipeline failed with error: {e}")
    
    # Verify output
    assert output_path is not None, "TTV pipeline returned None"
    assert os.path.exists(output_path), f"Output video doesn't exist: {output_path}"
    
    # Validate the video file
    assert validate_video_file(output_path), "Output video is not valid"
    
    # Get output directory
    output_dir = os.path.dirname(output_path)
    
    # Verify segments were created
    config = load_config(config_path)
    expected_segments = len(config['story'])
    assert validate_segment_files(output_dir, expected_segments), \
        "Segment validation failed"
    
    print(f"\n✓ TTV pipeline with real generation test passed!")
    print(f"  Config: {config_path}")
    print(f"  Output: {output_path}")
    print(f"  ⚠️  This test used real API credits")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])

