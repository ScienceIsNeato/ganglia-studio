"""Image generation and manipulation module.

This module provides functionality for:
- Generating images using DALL-E and other AI models
- Processing and manipulating images
- Handling image downloads and caching
- Managing image metadata and attributes
"""

import os
import shutil
import textwrap
import time
from datetime import datetime
from io import BytesIO

import openai
import requests
from ganglia_common.logger import Logger
from ganglia_common.query_dispatch import ChatGPTQueryDispatcher
from PIL import Image, ImageDraw, ImageFont

from ganglia_studio.video.story_generation import filter_text


def generate_image(
    sentence: str,
    context: str,
    style: str,
    *,
    image_index: int,
    total_images: int,
    query_dispatcher: ChatGPTQueryDispatcher,
    preloaded_images_dir: str | None = None,
    thread_id: str | None = None,
    output_dir: str | None = None,
) -> tuple[str | None, bool]:
    """Generate an image for a given sentence.

    Args:
        sentence: Text description for image generation
        context: Context for image generation
        style: Style to use for generation
        image_index: Index of the image in sequence
        total_images: Total number of images
        query_dispatcher: Query dispatcher for API calls
        preloaded_images_dir: Optional directory with pre-generated images
        thread_id: Optional thread ID for logging
        output_dir: Optional output directory for generated files

    Returns:
        Tuple[Optional[str], bool]: Path to generated image and success flag
    """
    thread_prefix = f"{thread_id} " if thread_id else ""
    progress = ""
    if total_images:
        progress = f" [{image_index + 1}/{total_images}]"
    Logger.print_info(
        f"{thread_prefix}Generating image for: '{sentence}' using style '{style}'"
        f"{progress}"
    )

    # Check for preloaded image
    if preloaded_images_dir:
        preloaded_path = os.path.join(preloaded_images_dir, f"image_{image_index}.png")
        if os.path.exists(preloaded_path):
            filename = os.path.join(output_dir, f"image_{image_index}.png")
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            save_image_without_caption(preloaded_path, filename, thread_id=thread_id)
            Logger.print_info(f"{thread_prefix}Using preloaded image from {preloaded_path}")
            return filename, True

        Logger.print_warning(
            f"{thread_prefix}Preloaded image not found at {preloaded_path}, "
            "falling back to generation"
        )

    try:
        # Clean up the sentence for better prompts
        filtered_text = filter_text(
            text=sentence,
            context=context,
            style=style,
            query_dispatcher=query_dispatcher,
            thread_id=thread_id,
        )
        if not filtered_text:
            Logger.print_error(
                f"{thread_prefix}No text available for image generation after filtering"
            )
            return None, False

        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(output_dir, f"image_{image_index}_{timestamp}.png")
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        # Generate image with DALL-E
        prompt = (
            f"Create a high-quality, photorealistic image in the style of {style} "
            f"that captures: {filtered_text['text']}"
        )

        result = generate_image_with_dalle(
            prompt=prompt, output_path=filename, size="1024x1024", quality="standard", style="vivid"
        )

        if result:
            Logger.print_info(f"{thread_prefix}Generated image {image_index} at: {filename}")
            return result, True

        Logger.print_error(f"{thread_prefix}Failed to generate image {image_index}")
        blank_image = generate_blank_image(
            sentence, image_index, thread_id=thread_id, output_dir=output_dir
        )
        return blank_image, False

    except OSError as e:
        Logger.print_error(f"{thread_prefix}Error generating image {image_index}: {str(e)}")
        blank_image = generate_blank_image(
            sentence, image_index, thread_id=thread_id, output_dir=output_dir
        )
        return blank_image, False


def generate_blank_image(
    text: str, image_index: int, thread_id: str | None = None, output_dir: str | None = None
) -> str | None:
    """Generate a blank image with text overlay.

    Args:
        text: Text to overlay on the image
        image_index: Index of the image in sequence
        thread_id: Optional thread ID for logging
        output_dir: Optional output directory for generated files

    Returns:
        Optional[str]: Path to generated image if successful, None otherwise
    """
    try:
        # Create blank image
        width = 1024
        height = 1024
        background_color = (0, 0, 0)  # Black background
        text_color = (255, 255, 255)  # White text

        image = Image.new("RGB", (width, height), background_color)

        # Add text overlay
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        except OSError:
            font = ImageFont.load_default()

        # Wrap text to fit width
        wrapped_text = textwrap.fill(text, width=40)

        # Calculate text position for center alignment
        text_bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Draw text
        draw.text((x, y), wrapped_text, font=font, fill=text_color)

        # Save image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(output_dir, f"blank_image_{image_index}_{timestamp}.png")

        image.save(filename)
        Logger.print_info(
            f"{thread_id + ' ' if thread_id else ''}Generated blank image {image_index} at: "
            f"{filename}"
        )
        return filename

    except OSError as e:
        Logger.print_error(
            f"{thread_id + ' ' if thread_id else ''}Error generating blank image "
            f"{image_index}: {str(e)}"
        )
        return None


def save_image_with_caption(
    image_url: str,
    filename: str,
    caption: str,
    current_step: int,
    total_steps: int,
    *,
    thread_id: str | None = None,
) -> None:
    """Save an image from URL with a caption overlay.

    Args:
        image_url: URL of the image to download
        filename: Path to save the final image
        caption: Text caption to overlay on the image
        current_step: Current step number in sequence
        total_steps: Total number of steps
        thread_id: Optional thread ID for logging
    """
    start_time = datetime.now()
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        # Download and process image
        image_data = download_image(image_url)
        if not image_data:
            raise ValueError("Failed to download image")

        image = Image.open(BytesIO(image_data))

        # Create caption overlay
        caption_image = create_caption_overlay(caption, current_step, total_steps, image.size[0])

        # Combine image with caption
        final_image = Image.new("RGB", (image.size[0], image.size[1] + caption_image.size[1]))
        final_image.paste(image, (0, 0))
        final_image.paste(caption_image, (0, image.size[1]))

        # Save final image
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        final_image.save(filename)

        end_time = datetime.now()
        Logger.print_info(
            f"{thread_prefix}Total time to save image: "
            f"{(end_time - start_time).total_seconds()} seconds. "
            f"Saved to {filename}"
        )

    except OSError as e:
        Logger.print_error(f"{thread_prefix}Error saving image with caption: {str(e)}")
        raise


def save_image_without_caption(
    image_source: str, filename: str, thread_id: str | None = None
) -> None:
    """Save image without caption from URL or local file.

    Args:
        image_source: URL or local path of source image
        filename: Path to save the image
        thread_id: Optional thread ID for logging
    """
    thread_prefix = f"{thread_id} " if thread_id else ""

    try:
        if image_source.startswith(("http://", "https://")):
            # Download from URL
            image_data = download_image(image_source)
            if not image_data:
                raise ValueError("Failed to download image")
            image = Image.open(BytesIO(image_data))
        else:
            # Load from local file
            image = Image.open(image_source)

        # Save image
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        image.save(filename)
        Logger.print_info(f"{thread_prefix}Saved image without caption to {filename}")

    except OSError as e:
        Logger.print_error(f"{thread_prefix}Error saving image: {str(e)}")
        raise


def create_caption_overlay(
    caption: str,
    current_step: int,
    total_steps: int,
    width: int,
    *,
    height: int | None = None,
    background_color: tuple[int, int, int] = (255, 255, 255),
    text_color: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Create an image with caption text overlay.

    Args:
        caption: Text to display
        current_step: Current step number
        total_steps: Total number of steps
        width: Width of the overlay
        height: Optional height (calculated if not provided)
        background_color: RGB tuple for background color
        text_color: RGB tuple for text color

    Returns:
        PIL.Image: Caption overlay image
    """
    try:
        # Set default height if not provided
        if not height:
            height = width // 4

        # Create base image
        caption_image = Image.new("RGB", (width, height), background_color)
        draw = ImageDraw.Draw(caption_image)

        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", height // 4
            )
        except OSError:
            font = ImageFont.load_default()

        # Format caption text
        caption_text = f"Step {current_step} of {total_steps}\n{textwrap.fill(caption, width=50)}"

        # Calculate text position for center alignment
        text_bbox = draw.textbbox((0, 0), caption_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Draw text
        draw.text((x, y), caption_text, font=font, fill=text_color)
        return caption_image

    except OSError as e:
        Logger.print_error(f"Error creating caption overlay: {str(e)}")
        raise


def generate_image_with_dalle(
    prompt: str,
    output_path: str,
    *,
    size: str = "1024x1024",
    quality: str = "standard",
    style: str = "vivid",
    retries: int = 5,
    retry_delay: float = 60.0,  # Increased default delay for rate limits
) -> str | None:
    """Generate an image using DALL-E.

    Args:
        prompt: Text prompt for image generation
        output_path: Path to save the generated image
        size: Image size (e.g. "1024x1024")
        quality: Image quality ("standard" or "hd")
        style: Image style ("vivid" or "natural")
        retries: Number of retries on failure
        retry_delay: Delay between retries in seconds

    Returns:
        Optional[str]: Path to generated image if successful
    """
    for attempt in range(retries):
        try:
            # Create image with DALL-E
            response = openai.images.generate(
                model="dall-e-3", prompt=prompt, size=size, quality=quality, style=style, n=1
            )

            # Get image URL from response
            image_url = response.data[0].url

            # Download and save image
            image_data = download_image(image_url)
            if not image_data:
                raise ValueError("Failed to download generated image")

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(image_data)

            return output_path

        except Exception as e:
            if attempt < retries - 1:
                if "Rate limit exceeded" in str(e):
                    Logger.print_warning(
                        f"Rate limit exceeded. Retrying in {retry_delay} seconds... "
                        f"(Attempt {attempt + 1} of {retries})"
                    )
                else:
                    Logger.print_warning(
                        f"Image generation failed. Retrying in {retry_delay / 10} seconds... "
                        f"(Attempt {attempt + 1} of {retries})"
                    )
                    retry_delay = retry_delay / 10  # Use shorter delay for non-rate-limit errors
                time.sleep(retry_delay)
                continue
            Logger.print_error(f"Failed to generate image: {str(e)}")
            return None


def download_image(url: str, timeout: float = 10.0) -> bytes | None:
    """Download an image from a URL.

    Args:
        url: URL of the image to download
        timeout: Request timeout in seconds (default: 10.0)

    Returns:
        Optional[bytes]: Image data if successful, None otherwise
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        Logger.print_error(f"Failed to download image: {str(e)}")
        return None


def resize_image(image_path: str, output_path: str, target_size: tuple[int, int]) -> str | None:
    """Resize an image to target dimensions.

    Args:
        image_path: Path to input image
        output_path: Path to save resized image
        target_size: Target width and height in pixels

    Returns:
        Optional[str]: Path to resized image if successful, None otherwise
    """
    try:
        with Image.open(image_path) as img:
            resized = img.resize(target_size, Image.Resampling.LANCZOS)
            resized.save(output_path)
            return output_path
    except OSError as e:
        Logger.print_error(f"Error resizing image: {str(e)}")
        return None


def process_image_batch(
    image_paths: list[str], output_dir: str, target_size: tuple[int, int] | None = None
) -> list[str]:
    """Process a batch of images with optional resizing.

    Args:
        image_paths: List of input image paths
        output_dir: Directory to save processed images
        target_size: Optional target size for resizing

    Returns:
        List[str]: List of paths to processed images
    """
    processed_paths = []

    for image_path in image_paths:
        try:
            # Generate output path
            filename = os.path.basename(image_path)
            output_path = os.path.join(output_dir, filename)

            if target_size:
                # Resize the image
                result = resize_image(image_path, output_path, target_size)
                if result:
                    processed_paths.append(result)
            else:
                # Just copy the image
                shutil.copy2(image_path, output_path)
                processed_paths.append(output_path)

        except OSError as e:
            Logger.print_error(f"Error processing image {image_path}: {str(e)}")
            continue

    return processed_paths
