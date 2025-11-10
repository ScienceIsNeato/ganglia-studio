# ganglia-studio

Multimedia generation suite for the GANGLIA ecosystem. ganglia-studio is both a **Python library** and a **command-line tool** for generating videos, music, and stories using AI models.

## What is ganglia-studio?

**ganglia-studio serves two purposes:**

1. **Python Library**: Provides multimedia generation capabilities that can be imported and used by other GANGLIA components (primarily `ganglia-core`)
2. **CLI Binary**: Standalone command-line tool for generating text-to-video (TTV) content

## Components

- **video**: Text-to-video generation pipeline
  - Caption rendering with dynamic positioning
  - Audio generation and alignment
  - Image generation (DALL-E, Stable Diffusion)
  - Final video assembly with FFmpeg
- **music**: Music generation backends
  - Suno API integration (multiple backend options)
  - Meta MusicGen local generation
- **story**: Story generation and conversational drivers
  - OpenAI-powered narrative generation
  - Story processing and structuring
- **image**: Image generation utilities
  - Multi-provider support (OpenAI, Stability AI)
- **CLI**: Command-line interface for multimedia generation

## Quick Start

### 1. Run Setup Script

```bash
./setup.sh
```

This will:
- Create a Python virtual environment
- Install all dependencies from `setup.py`
- Copy `.envrc.template` → `.envrc`
- Copy `config/ttv_config.template.json` → `config/ttv_config.json`
- Create output directories

### 2. Configure Environment Variables

Edit `.envrc` with your API keys:

```bash
# Required
export OPENAI_API_KEY="sk-..."

# Optional (depending on features used)
export STABILITY_API_KEY="sk-..."
export SUNO_API_KEY="..."
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

Then load the environment:

```bash
source .envrc
```

### 3. Customize Your Video Config

Edit `config/ttv_config.json`:

```json
{
  "style": "cinematic digital art",
  "story": [
    "Your story sentence 1",
    "Your story sentence 2",
    "Your story sentence 3"
  ],
  "title": "My Video Title",
  "caption_style": "dynamic",
  "background_music": {
    "file": null,
    "prompt": "upbeat electronic music"
  }
}
```

### 4. Generate Video

```bash
ganglia-studio video --config config/ttv_config.json --output ./generated_videos/
```

## Installation (Manual)

If you prefer manual setup:

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install as editable package (includes all dependencies from setup.py)
pip install -e .

# For development (adds pytest, coverage tools)
pip install -r requirements-dev.txt
```

## CLI Usage

### Basic Video Generation

```bash
ganglia-studio video --config path/to/ttv_config.json
```

### Specify Output Directory

```bash
ganglia-studio video --config path/to/ttv_config.json --output ./my_videos/
```

## Library Usage

```python
from ganglia_studio.video.ttv import text_to_video

# Generate video programmatically
text_to_video(
    config_path="config/ttv_config.json",
    output_dir="./output/"
)
```

```python
from ganglia_studio.music.music_lib import generate_music

# Generate music
audio_file = generate_music(
    prompt="upbeat electronic music",
    duration=30,
    backend="suno"
)
```

## Configuration

### TTV Config Format

```json
{
  "style": "art style for image generation",
  "music_backend": "suno|meta",
  "story": [
    "Array of story sentences",
    "Each becomes a scene in the video"
  ],
  "title": "Video title (used in metadata)",
  "caption_style": "dynamic|static",
  "background_music": {
    "file": "path/to/music.mp3",
    "prompt": "music generation prompt (if file is null)"
  },
  "closing_credits": {
    "file": "path/to/credits.mp3",
    "prompt": "credits music prompt (if file is null)"
  }
}
```

### Required Environment Variables

**Minimum (for basic TTV):**
- `OPENAI_API_KEY` - For image generation and story processing

**Optional (enables additional features):**
- `STABILITY_API_KEY` - Use Stable Diffusion for images
- `SUNO_API_KEY` - Generate background music
- `GOOGLE_APPLICATION_CREDENTIALS` - Google Cloud TTS (via ganglia-common)
- `GCS_BUCKET_NAME` - Google Cloud Storage integration
- `IMAGE_MODEL` - Override default image model (`dall-e-3`)
- `MUSIC_BACKEND` - Override default music backend (`suno`)

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=ganglia_studio --cov-report=html

# Run specific test file
pytest tests/unit/test_video_generation.py
```

### Project Structure

```
ganglia-studio/
├── src/ganglia_studio/
│   ├── cli.py              # Command-line interface
│   ├── video/              # Text-to-video pipeline
│   ├── music/              # Music generation
│   ├── story/              # Story generation
│   └── image/              # Image generation
├── tests/
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests (requires API keys)
├── config/
│   ├── ttv_config.template.json  # Template (committed)
│   └── ttv_config.json           # Your config (gitignored)
├── setup.py                # Package definition and dependencies
├── setup.sh                # Quick setup script
├── .envrc.template         # Environment variable template
└── README.md               # This file
```

## Dependencies

**Core Dependencies** (managed in `setup.py`):
- `ganglia-common>=0.1.0` - Shared GANGLIA utilities (logger, TTS, query_dispatch)
- `torch>=2.0.0` - PyTorch for ML models
- `transformers>=4.30.0` - Hugging Face transformers
- `diffusers>=0.18.0` - Stable Diffusion support
- `opencv-python>=4.8.0` - Video processing
- `moviepy>=1.0.3` - Video editing and assembly
- `pillow>=10.0.0` - Image processing
- `numpy>=1.24.0` - Numerical operations
- `requests>=2.31.0` - HTTP requests

**Development Dependencies** (managed in `requirements-dev.txt`):
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `pytest-timeout` - Test timeout management
- `pytest-cov` - Coverage reporting

## Integration with GANGLIA Ecosystem

ganglia-studio is designed to work as both:
1. **Standalone tool** - Use the CLI to generate videos independently
2. **Library for ganglia-core** - The conversational interface can trigger video generation

When used as a library by `ganglia-core`, it provides multimedia generation capabilities triggered by user commands.

## Troubleshooting

### "No module named 'ganglia_common'"

```bash
# Install ganglia-common first
cd ../ganglia-common && pip install -e .
```

### "OPENAI_API_KEY not found"

```bash
# Make sure you've sourced .envrc
source .envrc

# Verify it's set
echo $OPENAI_API_KEY
```

### "FFmpeg not found"

ganglia-studio requires FFmpeg for video processing:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Verify installation
ffmpeg -version
```

### Integration tests failing

Integration tests require real API keys and can be expensive to run. They're primarily for CI/CD validation. Run unit tests for local development:

```bash
pytest tests/unit/
```

## License

Part of the GANGLIA project. See main repository for license information.

## Contributing

This is a personal project, but issues and suggestions are welcome. Please ensure all tests pass and maintain the existing code style.
