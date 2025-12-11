"""
Tests for the movie poster generation functionality.
"""

import json
import unittest
from unittest.mock import MagicMock, Mock, patch

from ganglia_studio.video.story_generation import generate_movie_poster


class TestGenerateMoviePoster(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.query_dispatcher = Mock()
        self.style = "cyberpunk"
        self.story_title = "Neon Nights"
        self.output_dir = "/tmp/test_output"

    @patch('ganglia_studio.video.story_generation.get_openai_client')
    @patch('ganglia_studio.video.story_generation.save_image_without_caption')
    def test_generate_movie_poster(self, mock_save, mock_get_client):
        """Test successful movie poster generation."""
        # Setup
        filtered_story = json.dumps({
            "style": "cyberpunk",
            "title": "Neon Nights",
            "story": "A detective navigates a neon-lit city"
        })

        # Mock OpenAI client response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(url='http://example.com/poster.png')]
        mock_client.images.generate.return_value = mock_response
        mock_get_client.return_value = mock_client

        # Execute
        result = generate_movie_poster(
            filtered_story,
            self.style,
            self.story_title,
            query_dispatcher=self.query_dispatcher,
            output_dir=self.output_dir,
        )

        # Assert
        self.assertIsNotNone(result)
        mock_client.images.generate.assert_called_once()
        mock_save.assert_called_once()

    @patch('ganglia_studio.video.story_generation.get_openai_client')
    def test_generate_movie_poster_dalle_failure(self, mock_get_client):
        """Test handling of DALL-E generation failure."""
        # Setup
        filtered_story = json.dumps({
            "style": "cyberpunk",
            "title": "Neon Nights",
            "story": "A detective navigates a neon-lit city"
        })

        # Mock DALL-E failure
        mock_client = MagicMock()
        mock_client.images.generate.side_effect = Exception("DALL-E API error")
        mock_get_client.return_value = mock_client

        # Execute & Assert - function should return None on error, not raise
        result = generate_movie_poster(
            filtered_story,
            self.style,
            self.story_title,
            query_dispatcher=self.query_dispatcher,
            output_dir=self.output_dir,
        )
        self.assertIsNone(result, "Function should return None on DALL-E error")

if __name__ == '__main__':
    unittest.main()

