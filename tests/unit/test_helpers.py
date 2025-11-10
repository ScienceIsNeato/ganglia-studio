"""Unit tests for test helper functions."""

import os
import pytest
import tempfile
import json
from tests.helpers import (
    create_test_config,
    load_config,
    validate_video_file,
    count_segments_in_directory,
    parse_ttv_output_for_dir
)


def test_create_test_config():
    """Test config file creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "test_config.json")
        story = ["Sentence 1", "Sentence 2", "Sentence 3"]
        
        result_path = create_test_config(config_path, story, style="test style")
        
        assert result_path == config_path
        assert os.path.exists(config_path)
        
        # Load and verify contents
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        assert config['style'] == "test style"
        assert config['story'] == story
        assert config['title'] == "Test Video"
        assert 'background_music' in config
        assert 'closing_credits' in config


def test_load_config():
    """Test config loading."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "test.json")
        
        # Create a config
        test_config = {"test": "value", "number": 42}
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(test_config, f)
        
        # Load it
        loaded = load_config(config_path)
        
        assert loaded is not None
        assert loaded == test_config


def test_load_config_nonexistent():
    """Test loading nonexistent config."""
    result = load_config("/nonexistent/path.json")
    assert result is None


def test_load_config_invalid_json():
    """Test loading invalid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "bad.json")
        
        # Create invalid JSON
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write("{ invalid json }")
        
        result = load_config(config_path)
        assert result is None


def test_validate_video_file_nonexistent():
    """Test validating nonexistent video."""
    result = validate_video_file("/nonexistent/video.mp4")
    assert result is False


def test_count_segments_in_directory():
    """Test segment counting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some dummy segment files
        for i in range(3):
            segment_path = os.path.join(tmpdir, f"segment_{i}.mp4")
            with open(segment_path, 'w') as f:
                f.write("dummy")
        
        # Create a non-segment file
        other_path = os.path.join(tmpdir, "other.mp4")
        with open(other_path, 'w') as f:
            f.write("dummy")
        
        count = count_segments_in_directory(tmpdir)
        assert count == 3


def test_count_segments_nonexistent_dir():
    """Test counting segments in nonexistent directory."""
    count = count_segments_in_directory("/nonexistent/dir")
    assert count == 0


def test_parse_ttv_output_for_dir():
    """Test parsing TTV output for directory path."""
    # Test with standard message
    output1 = "Some output\n📁 TTV directory created: /tmp/test/dir\nMore output"
    result1 = parse_ttv_output_for_dir(output1)
    assert result1 == "/tmp/test/dir"
    
    # Test with alternative message
    output2 = "TTV directory created: /path/to/output"
    result2 = parse_ttv_output_for_dir(output2)
    assert result2 == "/path/to/output"
    
    # Test with no match
    output3 = "No directory information here"
    result3 = parse_ttv_output_for_dir(output3)
    assert result3 is None

