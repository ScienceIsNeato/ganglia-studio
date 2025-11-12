"""Test the TTV config loader."""

import unittest
import os

import pytest
from ganglia_studio.video.config_loader import load_input, TTVConfig, MusicConfig
import json

class TestConfigLoader(unittest.TestCase):
    """Test cases for TTV config loading."""


    def test_load_file_based_config(self):
        """Test loading a config that uses file-based resources."""
        config_path = os.path.join("tests", "unit", "ttv", "test_data", "file_based_config.json")
        result = load_input(config_path)

        # Check basic fields
        self.assertIsInstance(result, TTVConfig)
        self.assertEqual(result.style, "digital art")
        self.assertEqual(len(result.story), 3)
        self.assertEqual(result.title, "The Curious Cat")
        self.assertEqual(result.caption_style, "static")

        # Check background music config
        self.assertIsInstance(result.background_music, MusicConfig)
        self.assertEqual(result.background_music.file, "tests/unit/ttv/test_data/background_music.mp3")
        self.assertIsNone(result.background_music.prompt)

        # Check closing credits config
        self.assertIsInstance(result.closing_credits, MusicConfig)
        self.assertEqual(result.closing_credits.file, "tests/unit/ttv/test_data/closing_credits.mp3")
        self.assertIsNone(result.closing_credits.prompt)


    def test_load_prompt_based_config(self):
        """Test loading a config that uses prompt-based resources."""
        config_path = os.path.join("tests", "unit", "ttv", "test_data", "prompt_based_config.json")
        result = load_input(config_path)

        # Check basic fields
        self.assertIsInstance(result, TTVConfig)
        self.assertEqual(result.style, "digital art")
        self.assertEqual(len(result.story), 3)
        self.assertEqual(result.title, "The Curious Cat")
        self.assertEqual(result.caption_style, "dynamic")

        # Check background music config
        self.assertIsInstance(result.background_music, MusicConfig)
        self.assertIsNone(result.background_music.file)
        self.assertEqual(
            result.background_music.prompt,
            "Create ambient electronic music that captures the curiosity of a cat"
        )

        # Check closing credits config
        self.assertIsInstance(result.closing_credits, MusicConfig)
        self.assertIsNone(result.closing_credits.file)
        self.assertEqual(
            result.closing_credits.prompt,
            "Create upbeat celebratory music with cat-themed lyrics"
        )


    def test_background_music_both_null(self):
        """Test loading a config where background_music has both file and prompt as null."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "background_music": {
                "file": None,
                "prompt": None
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIsNone(result.background_music)
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_background_music_both_populated(self):
        """Test loading a config where background_music has both file and prompt populated."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "background_music": {
                "file": "test.mp3",
                "prompt": "test prompt"
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        with self.assertRaises(ValueError) as context:
            load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIn("Cannot specify both file and prompt", str(context.exception))
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_background_music_file_null(self):
        """Test loading a config where background_music has file as null and prompt populated."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "background_music": {
                "file": None,
                "prompt": "test prompt"
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIsInstance(result.background_music, MusicConfig)
        self.assertIsNone(result.background_music.file)
        self.assertEqual(result.background_music.prompt, "test prompt")
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_background_music_prompt_null(self):
        """Test loading a config where background_music has prompt as null and file populated."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "background_music": {
                "file": "test.mp3",
                "prompt": None
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIsInstance(result.background_music, MusicConfig)
        self.assertEqual(result.background_music.file, "test.mp3")
        self.assertIsNone(result.background_music.prompt)
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_closing_credits_both_null(self):
        """Test loading a config where closing_credits has both file and prompt as null."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "closing_credits": {
                "file": None,
                "prompt": None
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIsNone(result.closing_credits)
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_closing_credits_both_populated(self):
        """Test loading a config where closing_credits has both file and prompt populated."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "closing_credits": {
                "file": "test.mp3",
                "prompt": "test prompt"
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        with self.assertRaises(ValueError) as context:
            load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIn("Cannot specify both file and prompt", str(context.exception))
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_closing_credits_file_null(self):
        """Test loading a config where closing_credits has file as null and prompt populated."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "closing_credits": {
                "file": None,
                "prompt": "test prompt"
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIsInstance(result.closing_credits, MusicConfig)
        self.assertIsNone(result.closing_credits.file)
        self.assertEqual(result.closing_credits.prompt, "test prompt")
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_closing_credits_prompt_null(self):
        """Test loading a config where closing_credits has prompt as null and file populated."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "closing_credits": {
                "file": "test.mp3",
                "prompt": None
            }
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIsInstance(result.closing_credits, MusicConfig)
        self.assertEqual(result.closing_credits.file, "test.mp3")
        self.assertIsNone(result.closing_credits.prompt)
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_preloaded_images_dir_present(self):
        """Test loading a config with preloaded_images_dir specified."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title",
            "preloaded_images_dir": "tests/unit/ttv/test_data/images"
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertEqual(result.preloaded_images_dir, "tests/unit/ttv/test_data/images")
        os.remove("tests/unit/ttv/test_data/temp_config.json")


    def test_preloaded_images_dir_absent(self):
        """Test loading a config without preloaded_images_dir."""
        config = {
            "style": "test style",
            "story": ["test story"],
            "title": "test title"
        }
        with open("tests/unit/ttv/test_data/temp_config.json", "w") as f:
            json.dump(config, f)

        result = load_input("tests/unit/ttv/test_data/temp_config.json")
        self.assertIsNone(result.preloaded_images_dir)
        os.remove("tests/unit/ttv/test_data/temp_config.json")

if __name__ == "__main__":
    unittest.main()

