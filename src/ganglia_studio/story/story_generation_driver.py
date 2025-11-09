"""
Story generation driver module for GANGLIA.

This module provides functionality for gathering information from the user
to build a TTV configuration file, and then triggering the TTV process.
"""

import os
import time
import threading
import json
from typing import Dict, Any, Optional, List
import uuid

from ganglia_common.pubsub import get_pubsub, Event, EventType
from ganglia_studio.video.ttv import text_to_video
from ganglia_studio.video.config_loader import load_input
from ganglia_core.interface.parse_inputs import parse_tts_interface
from ganglia_common.logger import Logger
from ganglia_common.utils.file_utils import get_timestamped_ttv_dir, get_config_path
from ganglia_common.query_dispatch import ChatGPTQueryDispatcher


class StoryInfoType:
    """Types of story information that can be requested from the user."""
    STORY_IDEA = "story_idea"
    ARTISTIC_STYLE = "artistic_style"
    MUSIC_STYLE = "music_style"


class StoryGenerationState:
    """States for the story generation process."""
    IDLE = "idle"
    GATHERING_STORY_IDEA = "gathering_story_idea"
    GATHERING_ARTISTIC_STYLE = "gathering_artistic_style"
    GENERATING_CONFIG = "generating_config"
    RUNNING_TTV = "running_ttv"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StoryGenerationDriver:
    """
    Driver for gathering story information from the user and generating a TTV config.

    This class manages the process of collecting information needed for text-to-video
    generation through a conversational interface, without directly controlling the
    conversation flow.
    """

    def __init__(self, query_dispatcher: Optional[ChatGPTQueryDispatcher] = None):
        """
        Initialize the story generation driver.

        Args:
            query_dispatcher: Optional query dispatcher for AI-assisted content generation
        """
        self.pubsub = get_pubsub()
        self.query_dispatcher = query_dispatcher
        self.user_id = None
        self.state = StoryGenerationState.IDLE
        self.story_info = {
            'title': None,
            'style': None,
            'story': [],
            'music_backend': 'suno',
            'background_music': {
                'prompt': None,
                'file': None
            },
            'closing_credits': {
                'prompt': None,
                'file': None
            },
            'caption_style': 'dynamic'
        }
        self.config_path = None
        self._setup_pubsub_subscribers()
        Logger.print_debug("Story generation driver initialized")

    def _setup_pubsub_subscribers(self):
        """Set up the PubSub subscribers for the story generation driver."""
        # Subscribe to conversation started events
        self.pubsub.subscribe(
            EventType.CONVERSATION_STARTED,
            self._handle_conversation_started
        )

        # Subscribe to story information received events
        self.pubsub.subscribe(
            EventType.STORY_INFO_RECEIVED,
            self._handle_story_info_received
        )

    def _handle_conversation_started(self, event: Event):
        """
        Handle a conversation started event.

        Args:
            event: The event to handle
        """
        # Store the user ID for targeting events
        self.user_id = event.data.get('user_id')
        Logger.print_debug(f"Story generation driver registered user: {self.user_id}")

    def start_story_gathering(self):
        """Start the process of gathering story information."""
        if not self.user_id:
            Logger.print_error("Cannot start story gathering without a user ID")
            return

        # Reset story information
        self.story_info = {
            'title': "User's Story",
            'style': "cinematic",
            'story': [],
            'music_backend': 'suno',
            'background_music': {
                'prompt': None,
                'file': None
            },
            'closing_credits': {
                'prompt': None,
                'file': None
            },
            'caption_style': 'dynamic'
        }

        # Update state and request story idea
        self.state = StoryGenerationState.GATHERING_STORY_IDEA
        self._request_story_idea()

    def _request_story_idea(self):
        """Request the story idea from the user."""
        self.pubsub.publish(Event(
            event_type=EventType.STORY_INFO_NEEDED,
            data={
                'info_type': StoryInfoType.STORY_IDEA,
                'prompt': "If you tell me an interesting story, I can try to make a video. Give me some broad strokes and I can fill in the details. What do you have in mind for the protagonist? The conflict? The resolution?",
                'current_state': self.state
            },
            source='story_generation_driver',
            target=self.user_id
        ))

    def _request_artistic_style(self):
        """Request the artistic style from the user."""
        self.pubsub.publish(Event(
            event_type=EventType.STORY_INFO_NEEDED,
            data={
                'info_type': StoryInfoType.ARTISTIC_STYLE,
                'prompt': "What artistic style are you thinking for the visual components? What about music styles for the background music and closing credits?",
                'current_state': self.state
            },
            source='story_generation_driver',
            target=self.user_id
        ))

    def _handle_story_info_received(self, event: Event):
        """
        Handle story information received from the user.

        Args:
            event: The event containing the story information
        """
        if event.target != self.user_id:
            return

        info_type = event.data.get('info_type')
        user_response = event.data.get('user_response', '')
        is_valid = event.data.get('is_valid', False)

        if not is_valid:
            # User declined or provided invalid information
            self.state = StoryGenerationState.CANCELLED
            self.pubsub.publish(Event(
                event_type=EventType.STORY_INFO_NEEDED,
                data={
                    'info_type': 'cancelled',
                    'prompt': "No problem! Let me know if you change your mind and want to create a video later.",
                    'current_state': self.state
                },
                source='story_generation_driver',
                target=self.user_id
            ))
            return

        # Process the information based on the current state
        if self.state == StoryGenerationState.GATHERING_STORY_IDEA:
            # Process story idea
            self._process_story_idea(user_response)
            # Move to next state
            self.state = StoryGenerationState.GATHERING_ARTISTIC_STYLE
            # Request artistic style
            self._request_artistic_style()

        elif self.state == StoryGenerationState.GATHERING_ARTISTIC_STYLE:
            # Process artistic style
            self._process_artistic_style(user_response)
            # Move to generating config state
            self.state = StoryGenerationState.GENERATING_CONFIG
            # Generate the config file
            self._generate_config_file()
            # Start the TTV process
            self._start_ttv_process()

        else:
            Logger.print_error(f"Received story info in unexpected state: {self.state}")

    def _process_story_idea(self, user_response: str):
        """
        Process the story idea from the user.

        Args:
            user_response: The user's response containing the story idea
        """
        # Use query dispatcher to generate a story from the user's input
        if self.query_dispatcher:
            prompt = f"""
            Based on the following user input, create a short story with 5 scenes.
            Each scene should be a single sentence describing a visual moment.
            Format the output as a list of 5 sentences, each on a new line.

            User input: {user_response}
            """

            story_response = self.query_dispatcher.send_query(prompt)

            # Extract the story scenes
            scenes = [line.strip() for line in story_response.split('\n') if line.strip()]
            # Take up to 5 scenes
            scenes = scenes[:5]

            # Generate a title
            title_prompt = f"Generate a short, catchy title for this story: {' '.join(scenes)}"
            title = self.query_dispatcher.send_query(title_prompt).strip()

            # Update story info
            self.story_info['story'] = scenes
            self.story_info['title'] = title
        else:
            # Fallback if no query dispatcher
            self.story_info['story'] = [
                "A character embarks on an adventure",
                "They encounter a challenge along the way",
                "They struggle to overcome the obstacle",
                "With determination, they find a solution",
                "They return home changed by the experience"
            ]
            self.story_info['title'] = "The Journey"

    def _process_artistic_style(self, user_response: str):
        """
        Process the artistic style from the user.

        Args:
            user_response: The user's response containing the artistic style
        """
        # Use query dispatcher to extract style information
        if self.query_dispatcher:
            prompt = f"""
            Based on the following user input, extract:
            1. A visual style for images (e.g., "cinematic dark fantasy", "anime", "photorealistic")
            2. A music style for background music
            3. A music style for closing credits

            Format your response as:
            Visual style: [style]
            Background music: [style]
            Closing credits: [style]

            User input: {user_response}
            """

            style_response = self.query_dispatcher.send_query(prompt)

            # Parse the response
            visual_style = None
            background_music = None
            closing_credits = None

            for line in style_response.split('\n'):
                line = line.strip()
                if line.startswith("Visual style:"):
                    visual_style = line.replace("Visual style:", "").strip()
                elif line.startswith("Background music:"):
                    background_music = line.replace("Background music:", "").strip()
                elif line.startswith("Closing credits:"):
                    closing_credits = line.replace("Closing credits:", "").strip()

            # Update story info
            if visual_style:
                self.story_info['style'] = visual_style
            if background_music:
                self.story_info['background_music']['prompt'] = background_music
            if closing_credits:
                self.story_info['closing_credits']['prompt'] = closing_credits
        else:
            # Fallback if no query dispatcher
            self.story_info['style'] = "cinematic"
            self.story_info['background_music']['prompt'] = "epic orchestral"
            self.story_info['closing_credits']['prompt'] = "gentle piano"

    def _generate_config_file(self):
        """Generate the TTV config file."""
        # Create a timestamped directory for this run
        ttv_dir = get_timestamped_ttv_dir()

        # Create the config file path
        self.config_path = os.path.join(ttv_dir, "ttv_config.json")

        # Write the config file
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.story_info, f, indent=4)

        Logger.print_info(f"Generated TTV config file: {self.config_path}")

    def _start_ttv_process(self):
        """Start the TTV process."""
        # Update state
        self.state = StoryGenerationState.RUNNING_TTV

        # Notify that the TTV process is starting
        self.pubsub.publish(Event(
            event_type=EventType.TTV_PROCESS_STARTED,
            data={
                'config_path': self.config_path,
                'timestamp': time.time(),
                'estimated_duration': "7 minutes"
            },
            source='story_generation_driver',
            target=self.user_id
        ))

        # Start the TTV process in a separate thread
        thread = threading.Thread(target=self._run_ttv_process)
        thread.daemon = True
        thread.start()

    def _run_ttv_process(self):
        """Run the TTV process and handle events."""
        try:
            # Initialize TTS
            tts = parse_tts_interface('google')

            # Run the TTV process
            output_path = text_to_video(
                config_path=self.config_path,
                skip_generation=False,
                tts=tts,
                query_dispatcher=self.query_dispatcher
            )

            # Update state
            self.state = StoryGenerationState.COMPLETED

            # Publish a TTV process completed event
            self.pubsub.publish(Event(
                event_type=EventType.TTV_PROCESS_COMPLETED,
                data={
                    'output_path': output_path,
                    'timestamp': time.time()
                },
                source='story_generation_driver',
                target=self.user_id
            ))
        except Exception as e:
            # Update state
            self.state = StoryGenerationState.FAILED

            # Publish a TTV process failed event
            self.pubsub.publish(Event(
                event_type=EventType.TTV_PROCESS_FAILED,
                data={
                    'error': str(e),
                    'timestamp': time.time()
                },
                source='story_generation_driver',
                target=self.user_id
            ))

            Logger.print_error(f"Error in TTV process: {e}")
            import traceback
            Logger.print_error(f"Traceback: {traceback.format_exc()}")


# Singleton instance
_instance = None

def get_story_generation_driver(query_dispatcher=None):
    """Get the singleton StoryGenerationDriver instance."""
    global _instance
    if _instance is None:
        _instance = StoryGenerationDriver(query_dispatcher)
    return _instance
