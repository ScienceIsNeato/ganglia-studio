"""Module for loading and validating TTV (text-to-video) configuration files."""

import json
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class MusicConfig:
    """Configuration for background or closing credits music."""

    file: str | None = None
    prompt: str | None = None


@dataclass
class MusicOptions:
    """Group music-related configuration."""

    backend: Literal["suno", "meta"] = "suno"
    background: MusicConfig | None = None
    closing: MusicConfig | None = None


@dataclass
class TTVConfig:
    """Configuration for text-to-video generation."""

    style: str  # Required
    story: list[str]  # Required
    title: str  # Required
    caption_style: Literal["static", "dynamic"] = "static"  # Optional, defaults to static
    music: MusicOptions = field(default_factory=MusicOptions)
    preloaded_images_dir: str | None = None  # Optional, directory containing pre-generated images

    def __iter__(self):
        """Make the config unpackable into (style, story, title)."""
        return iter([self.style, self.story, self.title])

    def get(self, key, default=None):
        """Get a config value by key, with an optional default."""
        if hasattr(self, key):
            return getattr(self, key, default)
        special_keys = {
            "background_music": self.background_music,
            "closing_credits": self.closing_credits,
            "music_backend": self.music_backend,
        }
        return special_keys.get(key, default)

    @property
    def background_music(self) -> MusicConfig | None:
        """Background music configuration accessor."""
        return self.music.background

    @property
    def closing_credits(self) -> MusicConfig | None:
        """Closing credits configuration accessor."""
        return self.music.closing

    @property
    def music_backend(self) -> Literal["suno", "meta"]:
        """Music backend accessor."""
        return self.music.backend


def validate_music_config(config: MusicConfig) -> None:
    """Validate that a music config has either a file or a prompt."""
    if not config.file and not config.prompt:
        raise ValueError("Either file or prompt must be specified")
    if config.file is not None and config.prompt is not None:
        raise ValueError(
            "Cannot specify both file and prompt. "
            f"Current settings: file={config.file}, prompt={config.prompt}"
        )


def validate_caption_style(caption_style: str | None) -> str:
    """Validate and normalize the caption style.

    Args:
        caption_style: The caption style from config, or None

    Returns:
        Normalized caption style ("static" or "dynamic")

    Raises:
        ValueError: If caption style is invalid
    """
    if caption_style is None:
        return "static"
    if caption_style not in ["static", "dynamic"]:
        raise ValueError(f"Invalid caption style: {caption_style}. Must be 'static' or 'dynamic'")
    return caption_style


def load_input(ttv_config: str) -> TTVConfig:
    """Load and validate the TTV config file.

    Args:
        ttv_config: Path to the config JSON file

    Returns:
        TTVConfig object with validated configuration

    Raises:
        KeyError: If required fields are missing
        JSONDecodeError: If JSON is invalid
        FileNotFoundError: If config file doesn't exist
        ValueError: If music configuration is invalid"""
    with open(ttv_config, encoding="utf-8") as json_file:
        data = json.load(json_file)

    # Create music configs if present
    background_music = None
    if "background_music" in data and data["background_music"]:
        background_music = MusicConfig(
            file=data["background_music"].get("file"), prompt=data["background_music"].get("prompt")
        )
        if background_music.file or background_music.prompt:
            validate_music_config(background_music)
        else:
            background_music = None

    closing_credits = None
    if "closing_credits" in data and data["closing_credits"]:
        closing_credits = MusicConfig(
            file=data["closing_credits"].get("file"), prompt=data["closing_credits"].get("prompt")
        )
        if closing_credits.file or closing_credits.prompt:
            validate_music_config(closing_credits)
        else:
            closing_credits = None

    # Validate caption style
    caption_style = validate_caption_style(data.get("caption_style"))

    music_options = MusicOptions(
        backend=data.get("music_backend", "suno"),
        background=background_music,
        closing=closing_credits,
    )

    # Create and validate full config
    config = TTVConfig(
        style=data["style"],
        story=data["story"],
        title=data["title"],
        caption_style=caption_style,
        music=music_options,
        preloaded_images_dir=data.get("preloaded_images_dir"),
    )

    return config
