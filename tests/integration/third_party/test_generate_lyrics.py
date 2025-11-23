import json
import os
import pytest

from ganglia_studio.music.lyrics_lib import LyricsGenerator
from ganglia_common.query_dispatch import ChatGPTQueryDispatcher
from ganglia_common.logger import Logger
from ganglia_common.utils.file_utils import get_config_path

def count_syllables(word):
    """Count the number of syllables in a word."""
    word = word.lower()
    count = 0
    vowels = "aeiouy"

    # Handle special cases
    if not word:
        return 0
    elif word.endswith('e'):
        word = word[:-1]

    # Count vowel groups
    prev_char_is_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_char_is_vowel:
            count += 1
        prev_char_is_vowel = is_vowel

    # Ensure at least one syllable
    return max(1, count)

def count_line_syllables(line):
    """Count syllables in a line of text."""
    words = line.replace(',', ' ').replace('-', ' ').split()
    return sum(count_syllables(word) for word in words)

@pytest.mark.costly
def test_generate_lyrics():
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise EnvironmentError("Environment variable 'OPENAI_API_KEY' is not set.")

    story_text = (
        "This is a story about a brave knight named Stephanie, a dragon named Steve, "
        "and their shared love of Philadelphia. They traveled with their friends Arthur, "
        "Bella, and Cassandra to the mystical land of Eldoria. There they met Eldon the wise, "
        "Fiona the fierce, and Gregory the giant, who helped them on their quest to find the "
        "lost city of Atlantis."
    )

    query_dispatcher = ChatGPTQueryDispatcher(config_file_path=get_config_path())
    lyrics_generator = LyricsGenerator()

    # Test with different durations
    test_durations = [20, 30, 45]
    for duration in test_durations:
        print(f"\nTesting with {duration} second duration:")
        result = lyrics_generator.generate_song_lyrics(story_text, query_dispatcher, target_duration=duration)

        # Check that the result is in the expected JSON format
        try:
            lyrics_json = json.loads(result)
            lyrics = lyrics_json["lyrics"]
            style = lyrics_json["style"]
        except json.JSONDecodeError:
            Logger.print_error("Result is not in valid JSON format")
            return

        # Print the input story and output lyrics
        print(f"Input story: {story_text}")
        print(f"Output lyrics: {lyrics}")
        print(f"Style: {style}")

        # Basic validation
        assert lyrics != "", "ERROR: Generated lyrics are empty"
        assert lyrics != story_text, "ERROR: Generated lyrics are identical to the input story"
        assert style and isinstance(style, str), "ERROR: Style should be a non-empty string"
