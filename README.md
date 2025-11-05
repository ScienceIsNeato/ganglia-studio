# ganglia-studio

Multimedia generation suite for the GANGLIA ecosystem.

## Components

- **video**: Text-to-video generation (captions, audio, image generation, final assembly)
- **music**: Music generation backends (Suno, Meta MusicGen)
- **story**: Story generation and conversational drivers
- **image**: Image generation utilities
- **CLI**: Command-line interface for multimedia generation

## Installation

```bash
pip install -e .
```

## CLI Usage

```bash
# Generate video from config
ganglia-studio video --config path/to/ttv_config.json --output ./output/
```

## Development

```bash
pip install -e .
pip install -r requirements-dev.txt
pytest
```

## Dependencies

Requires `ganglia-common` for shared utilities (logger, query_dispatch, TTS, pubsub).
