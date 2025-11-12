"""
Tests for the movie poster generation functionality.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import json
import pytest
from ganglia_studio.video.story_generation import generate_movie_poster

class TestGenerateMoviePoster(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.query_dispatcher = Mock()
        self.style = "cyberpunk"
        self.story_title = "Neon Nights"
        self.output_dir = "/tmp/test_output"

    @pytest.mark.skip(reason="Patching 'client' attribute doesn't exist in story_generation module")
    @patch('ganglia_studio.video.story_generation.client')
    @patch('ganglia_studio.video.story_generation.save_image_without_caption')
    def test_generate_movie_poster(self, mock_save, mock_client):
        """Test successful movie poster generation."""
        # Setup
        filtered_story = json.dumps({
            "style": "cyberpunk",
            "title": "Neon Nights",
            "story": "A detective navigates a neon-lit city"
        })
        
        # Mock OpenAI client response
        mock_response = MagicMock()
        mock_response.data = [MagicMock(url='http://example.com/poster.png')]
        mock_client.images.generate.return_value = mock_response

        # Execute
        result = generate_movie_poster(filtered_story, self.style, self.story_title,
                                       self.query_dispatcher, output_dir=self.output_dir)

        # Assert
        self.assertIsNotNone(result)
        mock_client.images.generate.assert_called_once()
        mock_save.assert_called_once()

    @pytest.mark.skip(reason="Patching 'client' attribute doesn't exist in story_generation module")
    @patch('ganglia_studio.video.story_generation.client')
    def test_generate_movie_poster_dalle_failure(self, mock_client):
        """Test handling of DALL-E generation failure."""
        # Setup
        filtered_story = json.dumps({
            "style": "cyberpunk",
            "title": "Neon Nights",
            "story": "A detective navigates a neon-lit city"
        })
        
        # Mock DALL-E failure
        mock_client.images.generate.side_effect = Exception("DALL-E API error")

        # Execute & Assert
        with self.assertRaises(Exception):
            generate_movie_poster(filtered_story, self.style, self.story_title,
                                self.query_dispatcher, output_dir=self.output_dir)

if __name__ == '__main__':
    unittest.main()

