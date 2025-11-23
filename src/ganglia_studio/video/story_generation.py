import json
import os
import time
from functools import lru_cache
from typing import Any

import requests
from ganglia_common.logger import Logger
from openai import OpenAI


@lru_cache(maxsize=1)
def get_openai_client():
    """Get or create the OpenAI client instance."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable must be set. "
            "Please add it to your .envrc file."
        )
    return OpenAI(api_key=api_key)


def generate_filtered_story(context, style, story_title, query_dispatcher):
    """
    Generates a filtered story based on the provided context and style using ChatGPT.

    Args:
        context (str): The context for the story.
        style (str): The style of the story.
        story_title (str): The title of the story.
        query_dispatcher: An instance of the query dispatcher to send the query to ChatGPT.

    Returns:
        str: Generated filtered story in JSON format.
    """
    Logger.print_info("Generating filtered story with ChatGPT.")

    try:
        # First filter the content using the base DALL-E filter
        success, filtered_content = query_dispatcher.filter_content_for_dalle(context)
        if not success:
            Logger.print_error("Failed to filter story content")
            return json.dumps({"style": style, "title": story_title, "story": "No story generated"})

        # Then format it into the required JSON structure
        response = query_dispatcher.send_query(
            "Format this filtered story into a JSON object with the style "
            f"'{style}' and title '{story_title}':\n\n"
            f"{filtered_content}\n\n"
            "IMPORTANT: Return ONLY a JSON object in this exact format "
            "with no other text before or after:\n"
            "{\n"
            '  "style": "<insert style here>",\n'
            '  "title": "<insert title here>",\n'
            '  "story": "<insert filtered story here>"\n'
            "}"
        )

        # Parse the response to extract the filtered story
        response_json = json.loads(response)

        filtered_style = response_json["style"]
        filtered_title = response_json["title"]
        filtered_story = response_json["story"]

        if filtered_story == "No story generated":
            Logger.print_error(
                "Failed to generate filtered story - error in response format. Response: "
                + response
            )

        Logger.print_info(f"Generated filtered story: {filtered_story}")
        return json.dumps(
            {"style": filtered_style, "title": filtered_title, "story": filtered_story}
        )
    except Exception as e:
        Logger.print_error(f"Error generating filtered story: {e}")
        return json.dumps({"style": style, "title": story_title, "story": "No story generated"})


def _parse_story_context(filtered_story_json, thread_prefix):
    """Parse and validate story context from JSON."""
    try:
        filtered_story = json.loads(filtered_story_json)
    except json.JSONDecodeError:
        Logger.print_error(f"{thread_prefix}Filtered story is not in valid JSON format")
        return None

    filtered_context = filtered_story.get("story", "")
    if not filtered_context:
        Logger.print_error(f"{thread_prefix}Filtered story does not contain a story")
        return None

    return filtered_context


def _build_poster_prompt(story_title, style, filtered_context):
    """Build DALL-E prompt for movie poster."""
    return (
        f"Create a movie poster for the story titled '{story_title}' "
        f"with the style of {style} and context: {filtered_context}."
    )


def _generate_poster_image(client, prompt, output_dir, thread_id, thread_prefix):
    """Generate and save poster image."""
    response = client.images.generate(
        model="dall-e-3", prompt=prompt, size="1024x1024", quality="standard", n=1
    )
    if not response.data:
        Logger.print_error(f"{thread_prefix}No image was returned for the movie poster.")
        return None

    image_url = response.data[0].url
    filename = os.path.join(output_dir, "movie_poster.png")
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    save_image_without_caption(image_url, filename, thread_id=thread_id)
    return filename


def _handle_poster_generation_error(e, attempt, retries, wait_time, thread_prefix):
    """Handle errors during poster generation and return action."""
    if "Rate limit exceeded" in str(e):
        Logger.print_warning(
            f"{thread_prefix}Rate limit exceeded. Retrying in {wait_time} seconds... "
            f"(Attempt {attempt + 1} of {retries})"
        )
        time.sleep(wait_time)
        return "retry"

    if "safety system" in str(e).lower():
        return "safety"

    Logger.print_error(f"{thread_prefix}An error occurred while generating the movie poster: {e}")
    return "error"


def generate_movie_poster(
    filtered_story_json: str,
    style: str,
    story_title: str,
    *,
    query_dispatcher: Any,
    retries: int = 5,
    wait_time: float = 60,
    thread_id: str = "[MoviePoster]",
    output_dir: str | None = None,
) -> str | None:
    thread_prefix = f"{thread_id} " if thread_id else ""

    filtered_context = _parse_story_context(filtered_story_json, thread_prefix)
    if not filtered_context:
        return None

    prompt = _build_poster_prompt(story_title, style, filtered_context)
    safety_retries = 3

    for safety_attempt in range(safety_retries):
        for attempt in range(retries):
            try:
                client = get_openai_client()
                return _generate_poster_image(client, prompt, output_dir, thread_id, thread_prefix)

            except Exception as e:
                action = _handle_poster_generation_error(
                    e, attempt, retries, wait_time, thread_prefix
                )

                if action == "retry":
                    continue
                if action == "safety":
                    Logger.print_warning(
                        f"{thread_prefix}Safety system rejection. Attempting to filter content "
                        f"(Attempt {safety_attempt + 1} of {safety_retries})"
                    )
                    success, filtered_context = query_dispatcher.filter_content_for_dalle(
                        filtered_context
                    )
                    if success:
                        prompt = _build_poster_prompt(story_title, style, filtered_context)
                        break
                    Logger.print_error(f"{thread_prefix}Failed to filter content")
                    return None
                return None
        else:
            continue
        continue

    Logger.print_error(
        f"{thread_prefix}Failed to generate movie poster after {safety_retries} "
        "safety filtering attempts."
    )
    return None


def filter_text(
    text: str,
    *,
    context: str | None = None,
    style: str | None = None,
    query_dispatcher: Any | None = None,
    retries: int = 5,
    wait_time: float = 60.0,
    thread_id: str | None = None,
) -> dict[str, str]:
    """Filter and process text for better story generation.

    Args:
        text: Input text to filter
        context: Optional context for filtering
        style: Optional style to apply
        query_dispatcher: Optional query dispatcher
        retries: Number of retry attempts
        wait_time: Wait time between retries in seconds
        thread_id: Optional thread ID for logging

    Returns:
        Dict[str, str]: Dictionary containing filtered text and metadata
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    if not query_dispatcher:
        Logger.print_warning(
            f"{thread_prefix}No query dispatcher provided, returning original text"
        )
        return {"text": text}

    # Build the prompt for filtering
    prompt = (
        f"Given the context: {context}, "
        f"and style: {style}, "
        f"filter this text: {text}\n\n"
        "Return only the filtered text with no additional explanation or formatting."
    )

    for attempt in range(retries):
        try:
            response = query_dispatcher.send_query(prompt)
            filtered_text = response.strip()
            Logger.print_info(f"{thread_prefix}Successfully filtered text: {filtered_text}")
            return {"text": filtered_text}

        except Exception as e:
            if attempt < retries - 1:
                retry_wait = wait_time * (2**attempt)  # Exponential backoff
                Logger.print_warning(
                    f"{thread_prefix}Error filtering text: {str(e)}. "
                    f"Retrying in {retry_wait} seconds... "
                    f"(Attempt {attempt + 1} of {retries})"
                )
                time.sleep(retry_wait)
            else:
                Logger.print_error(
                    f"{thread_prefix}Failed to filter text after {retries} attempts: {str(e)}"
                )
                return {"text": text}  # Return original text on failure

    return {"text": text}


def save_image_without_caption(image_url, filename, thread_id=None):
    """Save an image from URL without caption.

    Args:
        image_url: URL of the image to save
        filename: Path to save the image
        thread_id: Optional thread ID for logging
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    response = requests.get(image_url, timeout=30)  # 30 second timeout
    if response.status_code == 200:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "wb") as file:
            file.write(response.content)
    Logger.print_info(f"{thread_prefix}Movie poster saved to {filename}")
