# Developer Guide

Quick reference for ganglia-studio development.

## Initial Setup

```bash
# Clone and setup
git clone <repo-url>
cd ganglia-studio
./setup.sh

# Activate environment
source .envrc  # or direnv allow
```

## Development Workflow

### Before Making Changes

```bash
# Create a feature branch
git checkout -b feature/my-feature

# Run tests to ensure everything works
pytest tests/unit/ -v
```

### During Development

```bash
# Run relevant tests frequently
pytest tests/unit/test_mymodule.py -v

# Or use watch mode (requires pytest-watch)
ptw tests/unit/ -- -v
```

### Before Committing

```bash
# Run all local checks (same as CI)
pytest tests/unit/ -v
pytest tests/integration/ -v -m "not costly"
ruff check src/
pylint src/ganglia_studio/ --disable=C0111,R0903,R0913,C0103,W0212,W0611

# Auto-fix formatting issues
ruff format src/

# Commit
git add .
git commit -m "feat: describe your change"
```

### Creating a Pull Request

```bash
# Push to your branch
git push origin feature/my-feature

# Create PR on GitHub
# CI will automatically run:
# - Unit tests (all Python versions)
# - Integration tests (skip costly)
# - Linting
# - Coverage
# - Package build
```

## Common Tasks

### Adding a New Feature

```bash
# 1. Create test file
touch tests/unit/test_my_feature.py

# 2. Write tests first (TDD)
# tests/unit/test_my_feature.py
def test_my_feature():
    assert my_function() == expected_result

# 3. Implement feature
# src/ganglia_studio/my_module.py

# 4. Run tests
pytest tests/unit/test_my_feature.py -v

# 5. Add integration test if needed
touch tests/integration/test_my_feature_integration.py
```

### Fixing a Bug

```bash
# 1. Write a test that reproduces the bug
def test_bug_reproduction():
    # This should fail initially
    result = buggy_function()
    assert result == correct_value

# 2. Run test to confirm it fails
pytest tests/unit/test_bug.py::test_bug_reproduction -v

# 3. Fix the bug

# 4. Run test to confirm it passes
pytest tests/unit/test_bug.py::test_bug_reproduction -v

# 5. Run full test suite
pytest tests/unit/ -v
```

### Adding Dependencies

```bash
# 1. Add to setup.py
# Edit: install_requires=[..., "new-package>=1.0.0"]

# 2. Reinstall package
pip install -e .

# 3. Test that it works
pytest tests/unit/ -v

# 4. Commit both setup.py and any code using the new dependency
git add setup.py src/
git commit -m "deps: add new-package for feature X"
```

### Running Costly Tests Locally

```bash
# Ensure API keys are set
source .envrc

# Run costly tests
pytest tests/integration/ -v -m costly

# This will:
# - Make real API calls
# - Consume API credits
# - Take several minutes
# - Generate videos in /tmp/GANGLIA/ttv/
```

### Debugging Test Failures

```bash
# Run with verbose output
pytest tests/unit/test_failing.py -vv

# Run with pdb debugger
pytest tests/unit/test_failing.py --pdb

# Run single test
pytest tests/unit/test_file.py::test_specific_function -v

# See print statements
pytest tests/unit/test_file.py -v -s

# See full tracebacks
pytest tests/unit/test_file.py -v --tb=long
```

## Code Quality

### Linting

```bash
# Fast linting with auto-fix
ruff check src/ --fix

# Comprehensive linting
pylint src/ganglia_studio/

# Check specific file
ruff check src/ganglia_studio/video/ttv.py
```

### Formatting

```bash
# Check formatting
ruff format --check src/

# Auto-format
ruff format src/

# Format specific file
ruff format src/ganglia_studio/video/ttv.py
```

### Type Checking (if using mypy)

```bash
pip install mypy
mypy src/ganglia_studio/
```

## Testing Tips

### Test Markers

```python
import pytest

@pytest.mark.unit
def test_fast_unit_test():
    pass

@pytest.mark.integration
def test_integration():
    pass

@pytest.mark.costly
@pytest.mark.integration
def test_with_api_calls():
    pass

@pytest.mark.slow
def test_long_running():
    pass
```

### Run Tests by Marker

```bash
# Default: exclude slow tests (fast feedback, ~1 minute)
pytest tests/unit/  # Uses default from pytest.ini: -m "not slow"

# Run ALL tests including slow caption tests (~4-11 minutes)
pytest tests/unit/ -m ""

# Only slow tests (caption rendering, ~11 minutes)
pytest -m slow

# Only integration (skip costly)
pytest -m "integration and not costly"

# Everything except costly
pytest -m "not costly"
```

**Note:** Slow tests (mainly caption rendering) are excluded by default to save time during development. They're still available when you need them via `-m slow` or `-m ""`. CI also excludes them by default.

### Using Test Helpers

```python
from tests.helpers import (
    create_test_config,
    validate_video_file,
    get_video_duration,
    validate_segment_files
)

def test_my_video_generation():
    config_path = create_test_config(
        "/tmp/test.json",
        story=["Scene 1", "Scene 2"],
        style="digital art"
    )
    
    video_path = text_to_video(config_path, skip_generation=True)
    
    assert validate_video_file(video_path)
    assert get_video_duration(video_path) > 0
```

## Git Workflow

### Commit Message Format

Use conventional commits:

```
feat: add new video transition effect
fix: correct audio alignment timing
docs: update installation instructions
test: add tests for caption generation
refactor: simplify image generation logic
deps: upgrade OpenAI SDK to 1.5.0
ci: add Python 3.13 to test matrix
```

### Branch Naming

```
feature/video-transitions
fix/audio-alignment-bug
docs/api-documentation
refactor/cleanup-imports
```

## CI/CD Integration

### What CI Checks

1. **Unit Tests:** Run on every push/PR
2. **Integration Tests:** Run on every push/PR (skip costly)
3. **Linting:** Run on every push/PR (won't block)
4. **Coverage:** Measured on every push/PR
5. **Package Build:** Verified on every push/PR

### Manually Trigger Costly Tests

1. Go to Actions tab on GitHub
2. Select "Costly Tests (Manual)"
3. Click "Run workflow"
4. Select Python version
5. Run

### Viewing CI Results

- Green checkmark: All checks passed
- Red X: Some checks failed
- Yellow circle: Checks in progress
- Click on the status to see details

## Troubleshooting

### "ModuleNotFoundError: No module named 'ganglia_common'"

```bash
cd ../ganglia-common
pip install -e .
cd ../ganglia-studio
pip install -e .
```

### "OpenAI API key not set"

```bash
# Check .envrc exists
ls -la .envrc

# Source it
source .envrc

# Verify
echo $OPENAI_API_KEY
```

### "FFmpeg not found"

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Verify
ffmpeg -version
```

### Tests pass locally but fail in CI

- Check for hardcoded paths
- Check for environment-specific behavior
- Look at CI logs for detailed error messages
- Try running with `CI=true` locally

## Performance Tips

### Speeding Up Tests

```bash
# Run tests in parallel (requires pytest-xdist)
pip install pytest-xdist
pytest tests/unit/ -n auto

# Only run tests that failed last time
pytest --lf

# Stop at first failure
pytest -x
```

### Reducing API Costs

```bash
# Use skip_generation for integration tests
video_path = text_to_video(config, skip_generation=True)

# Use small test data
story = ["Single short scene"]  # instead of long story

# Mock API calls in unit tests
@pytest.fixture
def mock_openai(monkeypatch):
    monkeypatch.setattr("openai.OpenAI", MockOpenAI)
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Conventional Commits](https://www.conventionalcommits.org/)

## Getting Help

- Check existing issues on GitHub
- Look at test examples in `tests/` directory
- Review CI logs for failure details
- Read inline code documentation
- Ask in team chat/discussion

