import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import pytest
from ganglia_studio.video.story_generation import generate_filtered_story, generate_movie_poster, filter_text, save_image_without_caption
from ganglia_common.utils.file_utils import get_timestamped_ttv_dir

class TestStoryGeneration(unittest.TestCase):
    def setUp(self):
        self.query_dispatcher = Mock()
        self.context = "A story about a friendly robot"
        self.style = "science fiction"
        self.story_title = "Robot Dreams"
        self.output_dir = get_timestamped_ttv_dir()

    def test_generate_filtered_story_success(self):
        # Mock successful content filtering
        self.query_dispatcher.filter_content_for_dalle.return_value = (True, "A friendly robot learns about human emotions")

        # Mock response from query dispatcher
        mock_response = json.dumps({
            "style": "science fiction",
            "title": "Robot Dreams",
            "story": "A heartwarming tale about an AI learning about friendship"
        })
        self.query_dispatcher.send_query.return_value = mock_response

        result = generate_filtered_story(self.context, self.style, self.story_title, self.query_dispatcher)
        result_json = json.loads(result)

        self.assertIn("style", result_json)
        self.assertIn("title", result_json)
        self.assertIn("story", result_json)
        self.query_dispatcher.filter_content_for_dalle.assert_called_once_with(self.context)
        self.query_dispatcher.send_query.assert_called_once()

    def test_generate_filtered_story_failure(self):
        # Mock a failure in content filtering
        self.query_dispatcher.filter_content_for_dalle.return_value = (False, None)

        result = generate_filtered_story(self.context, self.style, self.story_title, self.query_dispatcher)
        result_json = json.loads(result)

        self.assertEqual(result_json["story"], "No story generated")
        self.assertEqual(result_json["style"], self.style)
        self.assertEqual(result_json["title"], self.story_title)
        self.query_dispatcher.filter_content_for_dalle.assert_called_once_with(self.context)
        self.query_dispatcher.send_query.assert_not_called()

    @patch('ganglia_studio.video.story_generation.get_openai_client')
    def test_generate_movie_poster_success(self, mock_get_client):
        # Mock successful image generation
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(url='http://example.com/image.png')]
        mock_client.images.generate.return_value = mock_response
        mock_get_client.return_value = mock_client

        filtered_story = json.dumps({
            "style": "science fiction",
            "title": "Robot Dreams",
            "story": "A heartwarming tale about an AI"
        })

        with patch('ganglia_studio.video.story_generation.save_image_without_caption') as mock_save:
            result = generate_movie_poster(
                filtered_story,
                self.style,
                self.story_title,
                query_dispatcher=self.query_dispatcher,
                output_dir=self.output_dir,
            )

            self.assertIsNotNone(result)
            mock_client.images.generate.assert_called_once_with(
                model="dall-e-3",
                prompt=f"Create a movie poster for the story titled '{self.story_title}' with the style of {self.style} and context: A heartwarming tale about an AI.",
                size="1024x1024",
                quality="standard",
                n=1
            )
            mock_save.assert_called_once()

    def test_filter_text_success(self):
        mock_response = '{"text": "A friendly robot learns about human emotions"}'
        self.query_dispatcher.send_query.return_value = mock_response

        result = filter_text(
            "A robot learns about emotions",
            context=self.context,
            style=self.style,
            query_dispatcher=self.query_dispatcher,
        )

        self.assertIn("text", result)
        self.query_dispatcher.send_query.assert_called_once()

    @patch('requests.get')
    def test_save_image_without_caption(self, mock_get):
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake image content"
        mock_get.return_value = mock_response

        test_filename = "/tmp/test_image.png"

        with patch('builtins.open', unittest.mock.mock_open()) as mock_file:
            save_image_without_caption("http://example.com/image.png", test_filename)
            mock_get.assert_called_once_with("http://example.com/image.png", timeout=30)
            mock_file.assert_any_call(test_filename, 'wb')
            mock_file().write.assert_any_call(b"fake image content")

if __name__ == '__main__':
    unittest.main()

