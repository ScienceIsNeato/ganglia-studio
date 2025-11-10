"""Unit tests for FFmpeg utilities."""

import pytest
from ganglia_studio.utils.ffmpeg_utils import (
    get_system_info,
    get_ffmpeg_thread_count,
    FFmpegThreadManager
)


def test_get_system_info():
    """Test system info retrieval."""
    info = get_system_info()
    
    assert 'total_cores' in info
    assert 'total_memory' in info
    assert 'platform' in info
    
    assert info['total_cores'] > 0
    assert info['total_memory'] > 0
    assert info['platform'] in ['darwin', 'linux', 'windows']


def test_get_ffmpeg_thread_count():
    """Test FFmpeg thread count calculation."""
    # Test with CI flag
    ci_threads = get_ffmpeg_thread_count(is_ci=True)
    assert ci_threads >= 2
    assert ci_threads <= 4
    
    # Test with local flag
    local_threads = get_ffmpeg_thread_count(is_ci=False)
    assert local_threads >= 1
    assert local_threads <= 16
    
    # Local should generally have more threads than CI
    # (unless on a very constrained system)
    system_info = get_system_info()
    if system_info['total_memory'] / (1024**3) >= 16:
        assert local_threads >= ci_threads


def test_ffmpeg_thread_manager_context():
    """Test FFmpegThreadManager context manager."""
    manager = FFmpegThreadManager()
    
    # Initially no active operations
    assert len(manager.active_operations) == 0
    
    # Enter context
    with manager:
        # Should have one active operation
        assert len(manager.active_operations) == 1
    
    # After context exit, should be cleaned up
    assert len(manager.active_operations) == 0


def test_ffmpeg_thread_manager_get_threads():
    """Test thread allocation logic."""
    manager = FFmpegThreadManager()
    
    # First operation gets full thread count
    base_threads = get_ffmpeg_thread_count()
    first_op_threads = manager.get_threads_for_operation()
    assert first_op_threads == base_threads
    
    # Simulate an active operation
    with manager:
        # Second operation should get reduced threads
        second_op_threads = manager.get_threads_for_operation()
        assert second_op_threads <= first_op_threads
        assert second_op_threads >= 2


def test_ffmpeg_thread_manager_cleanup():
    """Test cleanup functionality."""
    manager = FFmpegThreadManager()
    
    # Enter and exit context to create operations
    with manager:
        pass
    
    # Cleanup should remove all operations
    manager.cleanup()
    assert len(manager.active_operations) == 0
    assert manager.operation_queue.empty()

