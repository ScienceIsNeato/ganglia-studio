"""Module for generating random TTV config values for integration tests using AI."""

import json
import os
from typing import Dict, Any
from query_dispatch import ChatGPTQueryDispatcher
from logger import Logger

def extract_json_from_response(response: str) -> str:
    """Extract JSON content from a potentially markdown-formatted response."""
    # If response is wrapped in code block, extract just the JSON
    if "```json" in response:
        start = response.find("{")
        end = response.rfind("}") + 1
        return response[start:end]
    # If response has any other markdown, just take the content between first { and last }
    if "{" in response and "}" in response:
        start = response.find("{")
        end = response.rfind("}") + 1
        return response[start:end]
    return response

def generate_config(output_path: str) -> str:
    """Generate a random TTV config using AI and save it to the specified path.

    Args:
        output_path: Path where the config file should be saved

    Returns:
        str: Path to the generated config file
    """
    # Initialize query dispatcher
    query_dispatcher = ChatGPTQueryDispatcher()

    # Generate all content in a single query
    content_prompt = """
    Generate a complete configuration for a text-to-video story generation. Include:
    1. A unique artistic style combining multiple influences (2-4 words)
    2. A cohesive 12-segment story in that style (each segment one sentence)
    3. A background music description matching the style (one sentence)
    4. A closing credits music description providing closure (one sentence)

    IMPORTANT: The title MUST start with "The " followed by title-cased words.

    Return ONLY a JSON object with this exact structure (no markdown, no extra text):
    {
        "style": "<generated>",
        "music_backend": "suno",
        "story": [
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>",
            "<generated>"
        ],
        "title": "The <generated>",
        "caption_style": "dynamic",
        "background_music": {
            "file": null,
            "prompt": "<generated>"
        },
        "closing_credits": {
            "file": null,
            "prompt": "<generated>"
        }
    }
    """

    response = query_dispatcher.send_query(content_prompt)
    content = json.loads(extract_json_from_response(response))

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write config to file with pretty formatting
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, indent=4)

    # Print the file contents
    Logger.print_info("\nGenerated TTV Config:")
    os.system(f"cat {output_path}")
    Logger.print_info("")

    return output_path
