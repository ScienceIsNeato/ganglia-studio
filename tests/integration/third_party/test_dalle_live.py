"""Tests for the DALL-E API integration.

This module contains tests that verify the functionality of the DALL-E API
integration, including:
- Basic image generation
- Response validation
- Image downloading and saving
"""

# Standard library imports
import json
import os
import traceback

# Third-party imports
import pytest
import requests
from openai import OpenAI

# Local imports
from ganglia_common.logger import Logger
from ganglia_common.utils.file_utils import get_tempdir

@pytest.mark.costly
def test_dalle_basic_generation():
    """Test basic DALL-E image generation functionality.

    This test:
    1. Creates a simple prompt
    2. Calls DALL-E API
    3. Verifies response
    4. Attempts to save the image

    Requires:
        OPENAI_API_KEY environment variable to be set
    """
    # Verify API key is present
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        pytest.skip("OPENAI_API_KEY not found in environment")

    Logger.print_info("Initializing OpenAI client...")
    client = OpenAI()

    # Simple, consistent prompt for testing
    test_prompt = (
        "A simple test image of a red apple on a white background, "
        "digital art style"
    )

    try:
        Logger.print_info(f"Sending request to DALL-E API with prompt: {test_prompt}")
        response = client.images.generate(
            model="dall-e-3",
            prompt=test_prompt,
            size="1024x1024",
            quality="standard",
            n=1
        )

        Logger.print_info("Response received from DALL-E API")
        Logger.print_info(
            f"Response data: {json.dumps(response.model_dump(), indent=2)}"
        )

        # Verify we got a response with an image URL
        assert response.data, "No data in response"
        assert len(response.data) > 0, "Empty data array in response"
        assert response.data[0].url, "No image URL in response"

        image_url = response.data[0].url
        Logger.print_info(f"Image URL received: {image_url}")

        # Try to save the image
        temp_dir = get_tempdir()
        os.makedirs(os.path.join(temp_dir, "test_images"), exist_ok=True)
        image_path = os.path.join(temp_dir, "test_images", "dalle_test_image.png")

        Logger.print_info(f"Attempting to download image to: {image_path}")
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()

        with open(image_path, 'wb') as f:
            f.write(response.content)

        # Verify the image was saved and has content
        assert os.path.exists(image_path), "Image file was not created"
        assert os.path.getsize(image_path) > 0, "Image file is empty"

        Logger.print_info(f"Successfully saved image: {image_path}")
        Logger.print_info(f"Image size: {os.path.getsize(image_path)} bytes")

    except Exception as e:
        Logger.print_error(f"Error during DALL-E test: {str(e)}")
        Logger.print_error(f"Traceback: {traceback.format_exc()}")
        raise


