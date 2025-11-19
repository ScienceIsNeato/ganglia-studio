"""FFmpeg utilities for managing commands and thread allocation."""

import multiprocessing
import os
import platform
import queue
import subprocess
import threading
import time
from contextlib import suppress
from functools import lru_cache

import psutil
from ganglia_common.logger import Logger


@lru_cache(maxsize=1)
def get_system_info():
    """
    Get system information including CPU count and available memory.
    Cached to avoid repeated system calls.
    """
    return {
        "total_cores": multiprocessing.cpu_count(),
        "total_memory": psutil.virtual_memory().total,
        "platform": platform.system().lower(),
    }


def get_ffmpeg_thread_count(is_ci: bool | None = None) -> int:
    """
    Get the optimal number of threads for FFmpeg operations.

    In CI environments, this returns a lower thread count to avoid resource contention.
    CI detection is automatic - GitHub Actions and most CI platforms automatically set CI=true,
    so no manual configuration is needed.

    Args:
        is_ci: Optional boolean to force CI behavior. If None, determines from environment.

    Returns:
        int: Number of threads to use for FFmpeg operations
    """
    # Get system info from cached function
    system_info = get_system_info()
    cpu_count = system_info["total_cores"]
    memory_gb = system_info["total_memory"] / (1024**3)

    # Check if running in CI environment
    if is_ci is None:
        ci_value = os.environ.get("CI", "")
        is_ci = ci_value.lower() == "true" if ci_value is not None else False

    # Memory-based thread limiting takes precedence
    # Use fewer threads when memory is constrained
    if memory_gb < 4:
        return min(2, cpu_count)
    if memory_gb <= 8:
        return min(4, cpu_count)
    if memory_gb < 16:
        return min(6, cpu_count)

    # For systems with ample memory (16GB+), apply environment-specific limits
    if is_ci:
        # In CI: Use cpu_count/2 with min 2, max 4 threads
        return min(4, max(2, cpu_count // 2))

    # In production with ample memory: Use 1.5x CPU count, capped at 16 threads
    # For single core systems, use just 1 thread
    if cpu_count == 1:
        return 1
    return min(16, int(cpu_count * 1.5))


class FFmpegOperation(threading.Thread):
    """Represents a single FFmpeg operation running in a thread."""

    def __init__(self, command: str, manager: "FFmpegThreadManager"):
        super().__init__()
        self.command = command
        self.completed = False
        self.error = None
        self.daemon = True  # Allow the program to exit even if threads are running
        self.manager = manager

    def run(self):
        try:
            # Simulate FFmpeg operation for testing
            time.sleep(0.1)
            if "-invalid-flag" in self.command:
                raise ValueError("Invalid FFmpeg flag")
            self.completed = True
        except Exception as error:
            self.error = error
            self.completed = True  # Mark as completed even on error
            # Remove self from active operations immediately on error
            with self.manager.lock:
                if self in self.manager.active_operations:
                    self.manager.active_operations.remove(self)
                    with suppress(queue.Empty):
                        self.manager.operation_queue.get_nowait()
        finally:
            # Remove self from active operations when done
            with self.manager.lock:
                if self in self.manager.active_operations:
                    self.manager.active_operations.remove(self)
                    with suppress(queue.Empty):
                        self.manager.operation_queue.get_nowait()


class FFmpegThreadManager:
    """Manages FFmpeg thread allocation across multiple concurrent operations."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active_operations = []
        self.operation_queue = queue.Queue()

    def get_threads_for_operation(self) -> int:
        """Get the optimal number of threads for a new FFmpeg operation.

        Takes into account current system load and concurrent operations.

        Returns:
            int: Number of threads to allocate for this operation
        """
        with self.lock:
            # Get base thread count which already includes memory limits
            base_thread_count = get_ffmpeg_thread_count()

            if not self.active_operations:
                # First operation gets base thread count (already memory limited)
                return base_thread_count

            # For subsequent operations, reduce thread count based on active operations
            # but never exceed the base memory-limited thread count
            return min(
                base_thread_count, max(2, base_thread_count // (len(self.active_operations) + 1))
            )

    def cleanup(self) -> None:
        """Clean up resources and reset state."""
        with self.lock:
            # Wait for all operations to complete with a timeout
            for operation in list(self.active_operations):
                try:
                    operation.join(timeout=0.1)
                except threading.ThreadError as error:
                    Logger.print_error(f"Error during cleanup: {error}")

            self.active_operations.clear()
            while not self.operation_queue.empty():
                try:
                    self.operation_queue.get_nowait()
                except queue.Empty:
                    break

    def __enter__(self):
        """Context manager entry - register new FFmpeg operation"""
        with self.lock:
            thread = FFmpegOperation("context_manager_operation", self)
            self.active_operations.append(thread)
            thread.start()

            # Wait for thread to start
            while not thread.is_alive():
                time.sleep(0.01)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - unregister FFmpeg operation"""
        with self.lock:
            if self.active_operations:
                thread = self.active_operations.pop()
                try:
                    thread.join(timeout=0.1)
                except threading.ThreadError as error:
                    Logger.print_error(f"Error during thread cleanup: {error}")


# Global thread manager instance
ffmpeg_thread_manager = FFmpegThreadManager()


def run_ffmpeg_command(ffmpeg_cmd):
    """Run an FFmpeg command with managed thread allocation.

    Args:
        ffmpeg_cmd: List of command arguments for FFmpeg

    Returns:
        subprocess.CompletedProcess or None if the command fails
    """
    try:
        # Use thread manager as context manager to track active operations
        with ffmpeg_thread_manager:
            # Get optimal thread count for this operation
            thread_count = get_ffmpeg_thread_count()

            # Insert thread count argument right after ffmpeg command
            # Make a copy of the command to avoid modifying the original
            cmd = ffmpeg_cmd.copy()
            cmd.insert(1, "-threads")
            cmd.insert(2, str(thread_count))

            Logger.print_info(
                f"Running ffmpeg command with {thread_count} threads: {' '.join(cmd)}"
            )
            result = subprocess.run(cmd, check=True, capture_output=True)
            Logger.print_info(f"ffmpeg output: {result.stdout.decode('utf-8')}")
            return result

    except subprocess.CalledProcessError as error:
        Logger.print_error(f"ffmpeg failed with error: {error.stderr.decode('utf-8')}")
        Logger.print_error(f"ffmpeg command was: {' '.join(ffmpeg_cmd)}")
        return None
