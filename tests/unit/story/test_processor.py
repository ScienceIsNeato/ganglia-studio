"""Tests for the story processor module.

This module contains tests that verify the functionality of the story processor,
including:
- Story processing with file-based credits
- Image and movie poster generation
- Video segment creation
- Error handling and failure cases
"""

# Standard library imports
import json
import os
import unittest
from unittest.mock import Mock, patch, MagicMock

# Third-party imports
import pytest

# Local imports
from ganglia_common.query_dispatch import ChatGPTQueryDispatcher
from ganglia_studio.video.config_loader import MusicConfig, MusicOptions, TTVConfig
from ganglia_studio.video.story_processor import process_story
from ganglia_common.utils.file_utils import get_tempdir

@pytest.fixture
def tts_mock():
    """Provide a mock TTS instance for testing.

    Returns:
        MagicMock: A mock TTS instance that returns a test audio file path
    """
    mock = MagicMock()
    mock.convert_text_to_speech.return_value = (
        True,
        os.path.join(get_tempdir(), "tts/test_audio.mp3")
    )
    return mock

class TestStoryProcessor(unittest.TestCase):
    """Test suite for the story processor module.

    Tests the end-to-end functionality of the story processor, including:
    - Story processing with file-based credits
    - Image and movie poster generation
    - Video segment creation
    - Error handling and failure cases
    """

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = get_tempdir()  # Use the base temp dir
        os.makedirs(os.path.join(self.temp_dir), exist_ok=True)

    @patch('ganglia_studio.video.story_processor.generate_movie_poster')
    @patch('ganglia_studio.video.story_processor.generate_image')
    @patch('ganglia_studio.video.story_processor.create_video_segment')
    def test_story_processor_with_file_based_credits(
        self, mock_create_video, mock_generate_image, mock_generate_poster
    ):
        """Test story processor with file-based credits.

        Verifies that the story processor correctly handles all aspects of
        video generation when using file-based credits, including:
        - TTS conversion
        - Image generation
        - Movie poster generation
        - Video segment creation
        """
        # Mock dependencies
        mock_tts = Mock()
        mock_tts.convert_text_to_speech.return_value = (
            True,
            os.path.join(self.temp_dir, "test_audio.mp3")
        )
        mock_query_dispatcher = Mock(spec=ChatGPTQueryDispatcher)
        mock_music_gen = Mock()

        # Mock movie poster generation
        mock_generate_poster.return_value = os.path.join(
            self.temp_dir, "movie_poster.png"
        )

        # Mock image generation for each sentence
        mock_generate_image.return_value = (
            os.path.join(self.temp_dir, "test_image.png"),
            True
        )

        # Mock video segment creation
        mock_create_video.return_value = os.path.join(self.temp_dir, "segment_1.mp4")

        # Set up mock responses for content filtering
        mock_query_dispatcher.send_query.return_value = json.dumps({
            "filtered_text": "Test filtered text",
            "is_safe": True
        })

        # Create a test config with file-based closing credits and background music
        test_config = TTVConfig(
            style="test style",
            story=["Test story line 1", "Test story line 2"],
            title="Test Title",
            caption_style="static",
            music=MusicOptions(
                backend="suno",
                background=MusicConfig(prompt="Generate background music"),
                closing=MusicConfig(file=os.path.join(self.temp_dir, "test_credits.mp3")),
            ),
            preloaded_images_dir=None,
        )

        # Mock background music generation
        mock_music_gen.get_background_music.return_value = os.path.join(
            self.temp_dir, "background_music.mp3"
        )

        # Mock closing credits generation
        mock_music_gen.get_closing_credits.return_value = (
            os.path.join(self.temp_dir, "closing_credits.mp3"),
            "Test lyrics"
        )

        # Patch the MusicGenerator to return our mock
        with patch('ganglia_studio.video.story_processor.MusicGenerator', return_value=mock_music_gen):
            # Call the function under test
            segments, background_music, closing_credits, poster, lyrics = process_story(
                tts=mock_tts,
                style=test_config.style,
                story=test_config.story,
                skip_generation=False,
                query_dispatcher=mock_query_dispatcher,
                story_title=test_config.title,
                config=test_config,
                output_dir=self.temp_dir
            )

            # Verify that the function returned the expected values
            self.assertIsNotNone(segments, "Should have video segments")
            self.assertEqual(len(segments), len(test_config.story),
                           "Should have one segment per story line")
            self.assertEqual(background_music, os.path.join(self.temp_dir, "background_music.mp3"),
                           "Should have background music")
            self.assertEqual(closing_credits, os.path.join(self.temp_dir, "closing_credits.mp3"),
                           "Should have closing credits")
            self.assertEqual(poster, os.path.join(self.temp_dir, "movie_poster.png"),
                           "Should have movie poster")
            self.assertEqual(lyrics, "Test lyrics", "Should have lyrics")

            # Verify that the mock functions were called with the expected arguments
            mock_music_gen.get_background_music.assert_called_once()
            mock_music_gen.get_closing_credits.assert_called_once()
            mock_generate_poster.assert_called_once()
            self.assertEqual(mock_generate_image.call_count, len(test_config.story),
                           "Should call generate_image once per story line")
            self.assertEqual(mock_create_video.call_count, len(test_config.story),
                           "Should call create_video_segment once per story line")

    @patch('ganglia_studio.video.story_processor.generate_movie_poster')
    @patch('ganglia_studio.video.story_processor.generate_image')
    @patch('ganglia_studio.video.story_processor.create_video_segment')
    def test_handles_generation_failures(
        self, mock_create_video, mock_generate_image, mock_generate_poster
    ):
        """Test that story processor handles generation failures gracefully."""
        # Mock dependencies
        mock_tts = Mock()
        mock_tts.convert_text_to_speech.return_value = (
            True,
            os.path.join(self.temp_dir, "test_audio.mp3")
        )
        mock_query_dispatcher = Mock(spec=ChatGPTQueryDispatcher)
        mock_music_gen = Mock()

        # Mock movie poster generation failure
        mock_generate_poster.return_value = None

        # Mock image generation failure for the first sentence
        mock_generate_image.side_effect = [
            (None, False),  # First call fails
            (os.path.join(self.temp_dir, "test_image.png"), True)  # Second call succeeds
        ]

        # Mock video segment creation
        mock_create_video.return_value = os.path.join(self.temp_dir, "segment_1.mp4")

        # Set up mock responses for content filtering
        mock_query_dispatcher.send_query.return_value = json.dumps({
            "filtered_text": "Test filtered text",
            "is_safe": True
        })

        # Create a test config with background music
        test_config = TTVConfig(
            style="test style",
            story=["Test story line 1", "Test story line 2"],
            title="Test Title",
            caption_style="static",
            music=MusicOptions(
                backend="suno",
                background=MusicConfig(prompt="Generate background music"),
                closing=MusicConfig(prompt="Generate closing credits"),
            ),
            preloaded_images_dir=None,
        )

        # Mock background music generation
        mock_music_gen.get_background_music.return_value = os.path.join(
            self.temp_dir, "background_music.mp3"
        )

        # Mock closing credits generation
        mock_music_gen.get_closing_credits.return_value = (
            os.path.join(self.temp_dir, "closing_credits.mp3"),
            "Test lyrics"
        )

        # Patch the MusicGenerator to return our mock
        with patch('ganglia_studio.video.story_processor.MusicGenerator', return_value=mock_music_gen):
            # Call the function under test
            segments, background_music, closing_credits, poster, lyrics = process_story(
                tts=mock_tts,
                style=test_config.style,
                story=test_config.story,
                skip_generation=False,
                query_dispatcher=mock_query_dispatcher,
                story_title=test_config.title,
                config=test_config,
                output_dir=self.temp_dir
            )

            # Verify that the function returned the expected values
            self.assertIsNotNone(segments, "Should have video segments")
            self.assertEqual(len(segments), 1, "Should have one segment (the second one)")
            self.assertEqual(background_music, os.path.join(self.temp_dir, "background_music.mp3"),
                           "Should have background music")
            self.assertEqual(closing_credits, os.path.join(self.temp_dir, "closing_credits.mp3"),
                           "Should have closing credits")
            self.assertIsNone(poster, "Should not have movie poster")
            self.assertEqual(lyrics, "Test lyrics", "Should have lyrics")

    @patch('ganglia_studio.video.story_processor.generate_movie_poster')
    @patch('ganglia_studio.video.story_processor.generate_image')
    @patch('ganglia_studio.video.story_processor.create_video_segment')
    def test_story_processor_with_generated_lyrics(
        self, mock_create_video, mock_generate_image, mock_generate_poster
    ):
        """Test that story processor correctly handles generated lyrics in closing credits."""
        # Mock dependencies
        mock_tts = Mock()
        mock_tts.convert_text_to_speech.return_value = (
            True,
            os.path.join(self.temp_dir, "test_audio.mp3")
        )
        mock_query_dispatcher = Mock(spec=ChatGPTQueryDispatcher)
        mock_music_gen = Mock()

        # Mock movie poster generation
        mock_generate_poster.return_value = os.path.join(
            self.temp_dir, "movie_poster.png"
        )

        # Mock image generation
        mock_generate_image.return_value = (
            os.path.join(self.temp_dir, "test_image.png"),
            True
        )

        # Mock video segment creation
        mock_create_video.return_value = os.path.join(self.temp_dir, "segment_1.mp4")

        # Set up mock responses for content filtering
        mock_query_dispatcher.send_query.return_value = json.dumps({
            "filtered_text": "Test filtered text",
            "is_safe": True
        })

        # Mock successful closing credits generation with lyrics
        expected_lyrics = "Test song lyrics\nSecond line of lyrics"
        mock_music_gen.get_closing_credits.return_value = (
            os.path.join(self.temp_dir, "closing_credits.mp3"),
            expected_lyrics
        )

        # Mock background music generation
        mock_music_gen.get_background_music.return_value = os.path.join(
            self.temp_dir, "background_music.mp3"
        )

        # Create a test config with prompt-based closing credits and background music
        test_config = TTVConfig(
            style="test style",
            story=["Test story line 1", "Test story line 2"],
            title="Test Title",
            caption_style="static",
            music=MusicOptions(
                backend="suno",
                background=MusicConfig(prompt="Generate background music"),
                closing=MusicConfig(prompt="Generate closing credits with lyrics"),
            ),
            preloaded_images_dir=None,
        )

        # Patch the MusicGenerator to return our mock
        with patch('ganglia_studio.video.story_processor.MusicGenerator', return_value=mock_music_gen):
            # Call the function under test
            segments, background_music, closing_credits, poster, lyrics = process_story(
                tts=mock_tts,
                style=test_config.style,
                story=test_config.story,
                skip_generation=False,
                query_dispatcher=mock_query_dispatcher,
                story_title=test_config.title,
                config=test_config,
                output_dir=self.temp_dir
            )

            # Verify that the function returned the expected values
            self.assertIsNotNone(segments, "Should have video segments")
            self.assertEqual(len(segments), len(test_config.story),
                           "Should have one segment per story line")
            self.assertEqual(background_music, os.path.join(self.temp_dir, "background_music.mp3"),
                           "Should have background music")
            self.assertEqual(closing_credits, os.path.join(self.temp_dir, "closing_credits.mp3"),
                           "Should have closing credits")
            self.assertEqual(poster, os.path.join(self.temp_dir, "movie_poster.png"),
                           "Should have movie poster")
            self.assertEqual(lyrics, expected_lyrics, "Should have lyrics")

            # Verify that the mock functions were called with the expected arguments
            mock_music_gen.get_background_music.assert_called_once()
            mock_music_gen.get_closing_credits.assert_called_once()

            # Check that the story text is passed (as a newline-joined string)
            story_text_arg = mock_music_gen.get_closing_credits.call_args[1]['story_text']
            self.assertTrue(isinstance(story_text_arg, str), "Story text should be a string")
            # Story text is the newline-joined story lines
            expected_story_text = "\n".join(test_config.story)
            self.assertEqual(story_text_arg, expected_story_text, "Story text should be newline-joined story lines")

if __name__ == '__main__':
    unittest.main()

