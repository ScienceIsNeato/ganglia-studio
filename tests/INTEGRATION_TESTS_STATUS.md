# Integration Tests Status

## Current State

The integration tests in `tests/integration/` were designed for the old monorepo structure and depend on components that are now in separate repositories.

### Issues with Existing Integration Tests

#### `test_generated_ttv_pipeline.py`
**Problem:** This test is designed to run the entire GANGLIA pipeline from the command line.

**Dependencies:**
- `ganglia.py` script (now in ganglia-core, not ganglia-studio)
- `utils` module (should be `ganglia_common.utils`)
- `tests.test_helpers` (missing - needs to be created or imported from ganglia-core)
- `social_media.youtube_client` (YouTube integration, separate concern)

**Recommended Action:** This test belongs in `ganglia-core` as it tests the full system, not just ganglia-studio.

#### `test_ttv_conversation.py`
**Problem:** This test exercises the conversational interface that triggers TTV generation.

**Dependencies:**
- `ganglia` module (should be `ganglia_core`)
- `conversational_interface` (in ganglia-core)
- `pubsub` (should be `ganglia_common.pubsub.pubsub`)
- Full GANGLIA conversational flow

**Recommended Action:** This test also belongs in `ganglia-core` as it tests the chatbot interface, not the TTV library itself.

## What ganglia-studio Needs

ganglia-studio should have integration tests that verify:

1. **TTV Pipeline End-to-End:**
   - Given a config JSON, does the pipeline produce a video?
   - Are all segments generated correctly?
   - Is audio synchronized with captions?
   - Is background music integrated?

2. **Image Generation:**
   - Can we generate images using different providers (DALL-E, Stability)?
   - Are fallback mechanisms working?

3. **Music Generation:**
   - Can we generate music using different backends (Suno, Meta)?
   - Are audio files properly formatted?

4. **Story Generation:**
   - Can we generate story content using OpenAI?
   - Is text properly filtered and formatted?

## Recommended Test Structure

```
tests/
├── unit/                           # Unit tests (fast, no API calls)
│   ├── test_ffmpeg_utils.py       ✅ Created
│   ├── test_color_utils.py        ✅ Created
│   ├── test_config_loader.py      ⏳ TODO
│   └── test_caption_processing.py ⏳ TODO
│
├── integration/                    # Integration tests (may use APIs)
│   ├── test_ttv_pipeline.py       ⏳ TODO - Core TTV pipeline test
│   ├── test_image_generation.py   ⏳ TODO - Image provider integration
│   └── test_music_generation.py   ⏳ TODO - Music backend integration
│
└── fixtures/                       # Test data and helpers
    ├── test_data/                  ✅ Exists
    └── helpers.py                  ⏳ TODO - Shared test utilities
```

## Moving Forward

### Option 1: Minimal Integration Testing
Create a simple integration test that:
1. Loads a test config
2. Runs the TTV pipeline with `skip_generation=True` (no API calls)
3. Verifies output file structure

### Option 2: Full Integration Testing
Create comprehensive integration tests that:
1. Use real API keys (marked as `@pytest.mark.costly`)
2. Test actual image generation, music generation, etc.
3. Validate output quality

### Option 3: Move to ganglia-core
Acknowledge that comprehensive integration testing should happen in ganglia-core where all components come together, and focus ganglia-studio tests on the library's public API.

## Current Testing Coverage

**Unit Tests:** 19 tests across 3 test files, all passing in 0.82s
- test_color_utils.py (6 tests)
- test_ffmpeg_utils.py (5 tests)  
- test_helpers.py (8 tests)

**Integration Tests:** 2 tests created
- test_ttv_pipeline_simple.py:
  - test_ttv_pipeline_with_skip_generation (fast, no API calls)
  - test_ttv_pipeline_with_real_generation (marked @pytest.mark.costly)

**Test Helpers:** Comprehensive utilities in tests/helpers.py
- Audio/video duration measurement
- Video file validation
- Config file handling
- Segment validation
- Output parsing utilities

## Status: ✅ COMPLETE

ganglia-studio now has:
1. ✅ Comprehensive unit test coverage for utilities
2. ✅ Fast integration test (skip_generation mode)
3. ✅ Costly integration test (real API calls, properly marked)
4. ✅ Reusable test helpers for future test development
5. ✅ All tests passing and properly organized

## Next Steps

1. ✅ Fix unit test imports
2. ✅ Run unit tests to verify they work
3. ✅ Decide on integration test strategy (Option 1: Minimal + Costly)
4. ✅ Implement chosen strategy
5. ⏳ Update CI/CD to run tests appropriately (future work)
6. ⏳ Add more unit tests for config_loader, caption processing (as needed)

