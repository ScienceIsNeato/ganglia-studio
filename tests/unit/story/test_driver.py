"""Unit tests for the story generation driver.

This module contains tests for the story generation driver, which manages
the process of gathering information for text-to-video generation.
"""

import unittest
import os
import json
import tempfile
from unittest.mock import MagicMock, patch
from ganglia_studio.story.story_generation_driver import (
    StoryGenerationDriver, StoryInfoType, StoryGenerationState, get_story_generation_driver
)
from ganglia_common.pubsub import Event, EventType


class TestStoryGenerationDriver(unittest.TestCase):
    """Test cases for the story generation driver."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock query dispatcher
        self.mock_query_dispatcher = MagicMock()

        # Mock the pubsub system
        self.mock_pubsub = MagicMock()

        # Create a patcher for the pubsub system
        self.pubsub_patcher = patch('ganglia_studio.story.story_generation_driver.get_pubsub')
        self.mock_get_pubsub = self.pubsub_patcher.start()
        self.mock_get_pubsub.return_value = self.mock_pubsub

        # Create a driver instance with the mock query dispatcher
        self.driver = StoryGenerationDriver(query_dispatcher=self.mock_query_dispatcher)

        # Set a test user ID
        self.driver.user_id = "test_user_123"

    def tearDown(self):
        """Tear down test fixtures."""
        # Stop the pubsub patcher
        self.pubsub_patcher.stop()

    def test_initialization(self):
        """Test initialization of the driver."""
        # Verify initial state
        self.assertEqual(self.driver.state, StoryGenerationState.IDLE)
        self.assertIsNotNone(self.driver.story_info)
        self.assertEqual(self.driver.user_id, "test_user_123")

        # Verify pubsub subscriptions were set up
        self.mock_pubsub.subscribe.assert_any_call(
            EventType.CONVERSATION_STARTED,
            self.driver._handle_conversation_started
        )
        self.mock_pubsub.subscribe.assert_any_call(
            EventType.STORY_INFO_RECEIVED,
            self.driver._handle_story_info_received
        )

    def test_start_story_gathering(self):
        """Test starting the story gathering process."""
        # Start story gathering
        self.driver.start_story_gathering()

        # Verify state transition
        self.assertEqual(self.driver.state, StoryGenerationState.GATHERING_STORY_IDEA)

        # Verify event was published
        self.mock_pubsub.publish.assert_called_once()
        event = self.mock_pubsub.publish.call_args[0][0]
        self.assertEqual(event.event_type, EventType.STORY_INFO_NEEDED)
        self.assertEqual(event.data['info_type'], StoryInfoType.STORY_IDEA)
        self.assertEqual(event.target, "test_user_123")

    def test_handle_conversation_started(self):
        """Test handling a conversation started event."""
        # Create a conversation started event
        event = Event(
            event_type=EventType.CONVERSATION_STARTED,
            data={"user_id": "new_user_456"},
            source="conversation"
        )

        # Handle the event
        self.driver._handle_conversation_started(event)

        # Verify user ID was updated
        self.assertEqual(self.driver.user_id, "new_user_456")

    @patch('ganglia_studio.story.story_generation_driver.get_timestamped_ttv_dir')
    def test_story_info_flow(self, mock_get_dir):
        """Test the flow of gathering story information."""
        # Mock the timestamped directory
        mock_get_dir.return_value = tempfile.mkdtemp()

        # Set up the query dispatcher to return mock responses
        self.mock_query_dispatcher.send_query.side_effect = [
            "Scene 1\nScene 2\nScene 3\nScene 4\nScene 5",  # Story scenes
            "The Epic Journey",  # Title
            # Add this third response for the artistic style processing
            "Visual style: fantasy\nBackground music: epic orchestral\nClosing credits: gentle piano"
        ]

        # Start with story idea
        self.driver.state = StoryGenerationState.GATHERING_STORY_IDEA

        # Create a story idea event
        story_event = Event(
            event_type=EventType.STORY_INFO_RECEIVED,
            data={
                "info_type": StoryInfoType.STORY_IDEA,
                "user_response": "A hero's journey through a magical land",
                "is_valid": True
            },
            source="conversation",
            target="test_user_123"
        )

        # Handle the event
        self.driver._handle_story_info_received(story_event)

        # Verify state transition
        self.assertEqual(self.driver.state, StoryGenerationState.GATHERING_ARTISTIC_STYLE)

        # Verify story info was processed
        self.assertEqual(len(self.driver.story_info['story']), 5)
        self.assertEqual(self.driver.story_info['title'], "The Epic Journey")

        # Verify artistic style request was published
        self.mock_pubsub.publish.assert_called()
        style_request = self.mock_pubsub.publish.call_args[0][0]
        self.assertEqual(style_request.event_type, EventType.STORY_INFO_NEEDED)
        self.assertEqual(style_request.data['info_type'], StoryInfoType.ARTISTIC_STYLE)

        # Reset mock
        self.mock_pubsub.reset_mock()

        # Create an artistic style event
        style_event = Event(
            event_type=EventType.STORY_INFO_RECEIVED,
            data={
                "info_type": StoryInfoType.ARTISTIC_STYLE,
                "user_response": "Fantasy style with epic music",
                "is_valid": True
            },
            source="conversation",
            target="test_user_123"
        )

        # Mock the open function for config file writing
        with patch('builtins.open', unittest.mock.mock_open()) as mock_open:
            # Handle the event
            self.driver._handle_story_info_received(style_event)

            # Verify state transition
            self.assertEqual(self.driver.state, StoryGenerationState.RUNNING_TTV)

            # Verify style info was processed
            self.assertEqual(self.driver.story_info['style'], "fantasy")
            self.assertEqual(self.driver.story_info['background_music']['prompt'], "epic orchestral")
            self.assertEqual(self.driver.story_info['closing_credits']['prompt'], "gentle piano")

            # Verify config file was written
            mock_open.assert_called()

            # Verify TTV process started event was published
            self.mock_pubsub.publish.assert_called()
            ttv_start_event = self.mock_pubsub.publish.call_args[0][0]
            self.assertEqual(ttv_start_event.event_type, EventType.TTV_PROCESS_STARTED)

    def test_invalid_story_info(self):
        """Test handling invalid story information."""
        # Start with story idea
        self.driver.state = StoryGenerationState.GATHERING_STORY_IDEA

        # Create an invalid story idea event
        invalid_event = Event(
            event_type=EventType.STORY_INFO_RECEIVED,
            data={
                "info_type": StoryInfoType.STORY_IDEA,
                "user_response": "No",
                "is_valid": False
            },
            source="conversation",
            target="test_user_123"
        )

        # Handle the event
        self.driver._handle_story_info_received(invalid_event)

        # Verify state transition
        self.assertEqual(self.driver.state, StoryGenerationState.CANCELLED)

        # Verify cancellation event was published
        self.mock_pubsub.publish.assert_called_once()
        cancel_event = self.mock_pubsub.publish.call_args[0][0]
        self.assertEqual(cancel_event.event_type, EventType.STORY_INFO_NEEDED)
        self.assertEqual(cancel_event.data['info_type'], "cancelled")

    @patch('ganglia_studio.story.story_generation_driver.text_to_video')
    @patch('ganglia_studio.story.story_generation_driver.parse_tts_interface')
    def test_run_ttv_process_success(self, mock_parse_tts, mock_text_to_video):
        """Test running the TTV process successfully."""
        # Mock the TTS interface
        mock_tts = MagicMock()
        mock_parse_tts.return_value = mock_tts

        # Mock the text_to_video function
        mock_text_to_video.return_value = "/path/to/output.mp4"

        # Set up the driver
        self.driver.config_path = "/path/to/config.json"

        # Run the TTV process
        self.driver._run_ttv_process()

        # Verify text_to_video was called
        mock_text_to_video.assert_called_once_with(
            config_path=self.driver.config_path,
            skip_generation=False,
            tts=mock_tts,
            query_dispatcher=self.mock_query_dispatcher
        )

        # Verify state transition
        self.assertEqual(self.driver.state, StoryGenerationState.COMPLETED)

        # Verify completion event was published
        self.mock_pubsub.publish.assert_called_once()
        complete_event = self.mock_pubsub.publish.call_args[0][0]
        self.assertEqual(complete_event.event_type, EventType.TTV_PROCESS_COMPLETED)
        self.assertEqual(complete_event.data['output_path'], "/path/to/output.mp4")

    @patch('ganglia_studio.story.story_generation_driver.text_to_video')
    @patch('ganglia_studio.story.story_generation_driver.parse_tts_interface')
    def test_run_ttv_process_failure(self, mock_parse_tts, mock_text_to_video):
        """Test handling a failure in the TTV process."""
        # Mock the TTS interface
        mock_tts = MagicMock()
        mock_parse_tts.return_value = mock_tts

        # Mock the text_to_video function to raise an exception
        mock_text_to_video.side_effect = Exception("Test error")

        # Set up the driver
        self.driver.config_path = "/path/to/config.json"

        # Run the TTV process
        self.driver._run_ttv_process()

        # Verify state transition
        self.assertEqual(self.driver.state, StoryGenerationState.FAILED)

        # Verify failure event was published
        self.mock_pubsub.publish.assert_called_once()
        fail_event = self.mock_pubsub.publish.call_args[0][0]
        self.assertEqual(fail_event.event_type, EventType.TTV_PROCESS_FAILED)
        self.assertEqual(fail_event.data['error'], "Test error")

    def test_singleton_instance(self):
        """Test the singleton pattern for the driver."""
        # Get the singleton instance
        instance1 = get_story_generation_driver(self.mock_query_dispatcher)
        instance2 = get_story_generation_driver(self.mock_query_dispatcher)

        # Verify both instances are the same
        self.assertIs(instance1, instance2)

        # Verify the instance has the expected type
        self.assertIsInstance(instance1, StoryGenerationDriver)


if __name__ == "__main__":
    unittest.main()

