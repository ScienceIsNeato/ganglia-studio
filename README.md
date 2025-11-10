# ganglia-studio

Multimedia generation suite for the GANGLIA ecosystem.

## Overview

`ganglia-studio` is both a **library** and **CLI tool** for text-to-video (TTV) generation. It provides:
- Image generation (DALL-E 3)
- Audio generation and synchronization (Google TTS, Whisper alignment)
- Music generation backends (Suno, Meta MusicGen)
- Story generation and filtering
- Video assembly with dynamic/static captions
- Movie poster generation
- Final video assembly with credits

## Components

- **video**: Text-to-video generation (captions, audio, image generation, final assembly)
- **music**: Music generation backends (Suno, Meta MusicGen)
- **story**: Story generation and conversational drivers
- **image**: Image generation utilities
- **CLI**: Command-line interface for multimedia generation

## Installation

```bash
./setup.sh
```

This script will:
1. Create a `.envrc` file from `.envrc.template` (if it doesn't exist). **You must fill in your API keys in `.envrc` and run `direnv allow`**.
2. Install all Python dependencies, including development tools.
3. Copy `config/ttv_config.template.json` to `config/ttv_config.json` (if it doesn't exist).

### Manual Installation

If you prefer to set up manually:

```bash
# 1. Install dependencies
pip install -e .
pip install -r requirements-dev.txt

# 2. Configure environment
cp .envrc.template .envrc
# Edit .envrc with your API keys
direnv allow

# 3. Configure TTV settings
cp config/ttv_config.template.json config/ttv_config.json
# Edit config/ttv_config.json as needed
```

## Configuration

### Environment Variables (.envrc)

**Required:**
- `OPENAI_API_KEY`: For image and story generation

**Optional:**
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to Google Cloud credentials JSON (for TTS)
- `SUNO_API_KEY`: For Suno music generation
- `META_MUSICGEN_API_KEY`: For Meta MusicGen
- `GANGLIA_TEMP_DIR`: Custom temp directory (defaults to system temp + /GANGLIA)
- `GANGLIA_LOG_DIR`: Custom log directory

### TTV Config (config/ttv_config.json)

The config file defines parameters for video generation:

```json
{
  "style": "digital art, cinematic",
  "story": [
    "First scene description",
    "Second scene description",
    "Third scene description"
  ],
  "title": "My Video Title",
  "caption_style": "dynamic",
  "background_music": {
    "file": null,
    "prompt": "upbeat electronic music"
  },
  "closing_credits": {
    "file": null,
    "prompt": "calm ambient music"
  }
}
```

See `config/ttv_config.template.json` for full schema.

## CLI Usage

```bash
# Generate video from config
ganglia-studio video --config path/to/ttv_config.json --output ./output/

# Use skip_generation mode (blank images, no API calls)
ganglia-studio video --config path/to/ttv_config.json --skip-generation
```

## Library Usage

```python
from ganglia_studio.video.ttv import text_to_video

# Generate video from config
video_path = text_to_video("path/to/ttv_config.json")

# With skip_generation (for testing)
video_path = text_to_video("path/to/ttv_config.json", skip_generation=True)
```

## Development

### Running Tests

```bash
# All unit tests (fast, no API calls)
pytest tests/unit/ -v

# All tests including integration
pytest tests/ -v

# Skip costly tests (those that make real API calls)
pytest tests/ -v -m "not costly"

# Only run costly tests
pytest tests/ -v -m costly
```

### Test Structure

```
tests/
├── helpers.py              # Shared test utilities
├── unit/                   # Fast tests, no external dependencies
│   ├── test_color_utils.py
│   ├── test_ffmpeg_utils.py
│   └── test_helpers.py
└── integration/            # Tests that exercise multiple components
    └── test_ttv_pipeline_simple.py
```

**Test Markers:**
- `@pytest.mark.unit`: Unit tests (fast)
- `@pytest.mark.integration`: Integration tests (slower)
- `@pytest.mark.costly`: Tests that make real API calls
- `@pytest.mark.slow`: Tests that take a long time

### Adding Tests

Use the helpers in `tests/helpers.py`:

```python
from tests.helpers import (
    create_test_config,
    validate_video_file,
    get_video_duration
)

def test_my_feature():
    config_path = create_test_config(
        "/tmp/test.json",
        story=["Scene 1", "Scene 2"],
        style="test style"
    )
    
    video_path = text_to_video(config_path, skip_generation=True)
    assert validate_video_file(video_path)
```

## Dependencies

Requires `ganglia-common` for shared utilities:
- Logger
- Query dispatch
- Text-to-speech (Google TTS)
- PubSub messaging
- File utilities
- Retry utilities

## Architecture

`ganglia-studio` is designed to work as:
1. **Standalone library**: Can be used by `ganglia-core` or other projects
2. **CLI tool**: Can be run directly for one-off video generation
3. **Service component**: Can be integrated into larger workflows

The library is agnostic to where it's called from and focuses on the core TTV pipeline functionality.

## Troubleshooting

### "OPENAI_API_KEY not set"
Make sure your `.envrc` file has `export OPENAI_API_KEY="your-key-here"` and you've run `direnv allow`.

### "ModuleNotFoundError: No module named 'ganglia_common'"
Run `pip install -e .` from the `ganglia-common` directory first, then reinstall `ganglia-studio`.

### Tests fail to collect
If you see import errors during test collection, make sure you've installed the package in development mode:
```bash
pip install -e .
```

### FFmpeg errors
Make sure FFmpeg is installed:
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## License

See main GANGLIA repository for license information.
