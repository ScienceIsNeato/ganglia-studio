import json
import random

from ganglia_common.logger import Logger

example_lyrical_styles = [
    "rock",
    "pop",
    "jazz",
    "blues",
    "hip hop",
    "country",
    "classical",
    "reggae",
    "metal",
    "folk",
]


class LyricsGenerator:
    def __init__(self):
        pass

    def generate_song_lyrics(self, story_text, query_dispatcher, target_duration=30):
        """Generate song lyrics based on the story text.

        Args:
            story_text: The story to base the lyrics on
            query_dispatcher: The query dispatcher to use for generation
            target_duration: Target duration in seconds (default: 30)
        """
        prompt = f"""
        Generate lyrics for a {target_duration}-second song based on the following story.
        The lyrics should be:
        - Each line takes 8-12 seconds to sing naturally with proper phrasing
        - Each line should be 8-10 syllables for natural pacing
        - No repetition of lines
        - Focus on the key themes, emotions, and narrative elements
        - Suitable for a trailer or closing credits
        - Must clearly reflect the story's themes and content

        For reference:
        - A 20-second song should have 2-3 lines
        - A 30-second song should have 3-4 lines
        - A 45-second song should have 4-5 lines

        Story:
        {story_text}

        Return the lyrics in JSON format with the following structure:
        {{
            "style": "upbeat pop",  # or another appropriate style
            "lyrics": "the generated lyrics here"
        }}

        The lyrics should capture the essence and themes of the story while being memorable and fitting the time constraint.
        """

        response = query_dispatcher.send_query(prompt)

        # Try to parse the response as JSON
        try:
            json_data = json.loads(response)
            return json.dumps(json_data)  # Return the properly formatted JSON
        except json.JSONDecodeError:
            # If response is not valid JSON, try to extract style and lyrics from text
            lines = response.strip().split("\n")
            style = "upbeat pop"  # Default style
            lyrics = []

            for line in lines:
                line = line.strip()
                if line.startswith('"style":'):
                    style = line.split(":")[1].strip().strip('",')
                elif line.startswith('"lyrics":'):
                    lyrics = [line.split(":")[1].strip().strip('",')]
                elif not line.startswith("{") and not line.startswith("}"):
                    lyrics.append(line.strip().strip('",'))

            # Create a properly formatted JSON response
            formatted_response = {"style": style, "lyrics": "\n".join(lyrics)}

            Logger.print_info(f"Generated lyrics: {formatted_response}")
            return json.dumps(formatted_response)

    def determine_lyrical_style(self, story_text, query_dispatcher):
        Logger.print_info("Determining lyrical style with ChatGPT.")

        prompt = (
            f"Based on the following story, suggest an appropriate lyrical style for a song:\n\n{story_text}\n\n"
            "Possible styles include: " + ", ".join(example_lyrical_styles) + ".\n\n"
            "Return the style as a single word or phrase that best fits the story."
        )

        try:
            response = query_dispatcher.send_query(prompt)
            lyrical_style = response.strip().split("\n")[0]

            if lyrical_style not in example_lyrical_styles:
                lyrical_style = random.choice(example_lyrical_styles)

            Logger.print_info(f"Determined lyrical style: {lyrical_style}")
            return lyrical_style
        except Exception as e:
            Logger.print_error(f"Error determining lyrical style: {e}")
            return random.choice(example_lyrical_styles)
