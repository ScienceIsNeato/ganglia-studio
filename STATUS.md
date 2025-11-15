# GANGLIA Studio - Systematic Linting Cleanup

## Mission
Fix ALL 220 pylint warnings to achieve 10.0/10 rating, then ensure all tests pass and CI is green.

## Current Status
- **Branch**: `ci/fix-dependency-installation`
- **Last Commit**: `504595b` - "refactor: fix 29 pylint issues - Phase 1 quick wins (partial)"
- **Progress**: 29/220 issues resolved (13%)
- **Current Rating**: 9.35/10 (was 9.35/10)

## What's Been Completed

### ✅ Phase 1 - Quick Wins (29/97 issues fixed)

**Files Modified:**
1. `src/ganglia_studio/interface/parse_inputs.py` - removed trailing newline, fixed no-else-return
2. `src/ganglia_studio/interface/__init__.py` - removed trailing newline
3. `src/ganglia_studio/music/music_lib.py` - added `check=False` to subprocess.run
4. `src/ganglia_studio/music/backends/foxai_suno.py`:
   - Added `encoding="utf-8"` to 2 open() calls
   - Fixed bare-except with specific exception types
   - Added `timeout=30` to 5 requests calls
   - Fixed unused variable `status` (prefixed with `_`)
   - Removed 5 unnecessary `pass` statements
5. `src/ganglia_studio/music/backends/suno_api_org.py`:
   - Added default timeout handling to `_make_api_request`
   - Fixed bare-except with specific exception types
   - Fixed 2 unused variables (prefixed with `_`)
6. `src/ganglia_studio/music/backends/suno_interface.py` - removed 5 unnecessary `pass` statements
7. `src/ganglia_studio/music/backends/base.py` - removed 5 unnecessary `pass` statements
8. `src/ganglia_studio/video/audio_generation.py` - added `timeout=30` to requests.post
9. `src/ganglia_studio/video/story_generation.py` - removed unused `prompt` variable
10. `src/ganglia_studio/story/story_generation_driver.py` - fixed unused variable `info_type`

## What Remains

### 🔄 Phase 1 - Quick Wins (Remaining: 68 issues)

#### A. Line Too Long (55 instances - C0301)
**Strategy**: Break long lines at logical points (function calls, string concatenation, list/dict literals)

**Files needing fixes:**
- `music/music_lib.py`: 6 lines
- `music/lyrics_lib.py`: 2 lines
- `music/backends/foxai_suno.py`: 6 lines
- `music/backends/gcui_suno.py`: 3 lines
- `music/backends/base.py`: 2 lines
- `music/backends/meta.py`: 1 line
- `video/config_loader.py`: 1 line
- `video/log_messages.py`: 1 line
- `video/story_generation.py`: 10 lines
- `video/story_processor.py`: 8 lines
- `video/captions.py`: 2 lines
- `video/audio_alignment.py`: 3 lines
- `video/final_video_generation.py`: 3 lines
- `video/image_generation.py`: 4 lines
- `story/story_generation_driver.py`: 3 lines

**Command to find them all:**
```bash
cd /Users/pacey/Documents/SourceCode/ganglia_repos/ganglia-core/ganglia-studio
.venv/bin/pylint src/ganglia_studio/ --disable=C0111,R0903,R0913,C0103,W0212,W0611,C0302,R0801 2>&1 | grep "C0301"
```

#### B. Unused Arguments (2 instances - W0613)
- `music/backends/foxai_suno.py:216` - `prompt` parameter
- `video/image_generation.py:30` - `total_images` parameter

**Fix**: Prefix with underscore or remove if truly unused.

#### C. FIXME Comments (4 instances - W0511)
- `music/music_lib.py:418` - "TODO: Calculate actual duration"
- `video/captions.py:920` - "TODO: Fix bug where long static captions overflow"
- `video/ttv.py:12` - "TODO: remove skip_generation globally"
- `video/final_video_generation.py:331` - "TODO: This shouldn't be specific to test outputs"

**Fix**: Either implement the TODO or convert to GitHub issue and remove from code.

### 📋 Phase 2 - Import Issues (8 instances - C0415)
**Issue**: Imports inside functions instead of at module top.

**Strategy**: Move imports to top of file, except where there's a circular dependency reason.

**Files:**
- `music/music_lib.py`: 4 shutil imports
- `music/backends/suno_api_org.py`: 1 json import
- `video/image_generation.py`: 1 PIL.ImageDraw, PIL.ImageFont import
- `story/story_generation_driver.py`: 1 traceback import

### 📋 Phase 3 - Code Structure (15 instances)
**Issue**: Unnecessary else/elif after return/raise/continue/break

**Pattern to fix:**
```python
# BAD
if condition:
    return value
else:
    do_something()

# GOOD
if condition:
    return value
do_something()
```

**Instances:**
- 12x `no-else-return` (R1705)
- 1x `no-else-raise` (R1720)
- 1x `no-else-continue` (R1724)
- 1x `no-else-break` (R1723)

**Files:**
- `music/music_lib.py`: 2 instances
- `music/backends/foxai_suno.py`: 2 instances
- `music/backends/suno_api_org.py`: 2 instances
- `video/story_generation.py`: 2 instances
- `video/story_processor.py`: 2 instances
- `video/final_video_generation.py`: 2 instances
- Others: scattered

### 📋 Phase 4 - Too Many Positional Arguments (38 instances - R0917)
**Issue**: Functions with >5 positional arguments (hard to read/maintain)

**Strategy**: Convert to keyword-only arguments or create config dataclasses.

**Options:**
1. Add `*,` to force keyword-only args after position 5
2. Create config objects (e.g., `MusicGenConfig`, `CaptionConfig`)
3. Use `**kwargs` with validation

**Most affected files:**
- `music/music_lib.py`: 5 functions
- `music/backends/`: Multiple backends (7/5, 8/5, 10/5 violations)
- `video/captions.py`: 7 functions
- `video/story_generation.py`: 2 functions
- `video/story_processor.py`: 2 functions

### 📋 Phase 5 - Function Complexity (27 instances)
**Issue**: Functions are too complex

**Categories:**
- 14x `too-many-locals` (R0914) - >20 local variables
- 7x `too-many-return-statements` (R0911) - >6 returns
- 4x `too-many-branches` (R0912) - >15 branches
- 1x `too-many-statements` (R0915) - >60 statements
- 1x `too-many-nested-blocks` (R1702) - >5 nested levels

**Strategy**: Extract helper functions, use early returns, simplify logic.

### 📋 Phase 6 - Too Many Instance Attributes (3 instances - R0902)
**Issue**: Classes with >7 instance attributes

**Files:**
- `video/config_loader.py:17` - TTVConfig (8/7)
- `video/captions.py:46` - CaptionGenerator (8/7)

**Fix**: Consider breaking into smaller classes or accept the complexity for config objects.

### 📋 Phase 7 - Arguments Differ (3 instances - W0221)
**Issue**: Overriding methods with different signatures than base class

**Files:**
- `music/backends/meta.py`: 3 methods differ from MusicBackend base

**Fix**: Make signatures compatible or use `*args, **kwargs`.

### 📋 Phase 8 - Misc Cleanup (8 instances)
- 2x `global-statement` (W0603)
- 2x `broad-exception-raised` (W0719) - raising `Exception` instead of specific type
- 2x `reimported` (W0404)
- 2x `redefined-outer-name` (W0621)
- 1x `global-variable-not-assigned` (W0602)
- 1x `consider-using-f-string` (C0209)

### 📋 Phase 9 - Remove CI Bypasses
**Critical**: Remove `continue-on-error: true` from CI workflows

**Files to fix:**
1. `.github/workflows/ci.yml`:
   - Line 84: ruff check
   - Line 89: pylint
2. `.github/workflows/dependency-check.yml`:
   - Line 42: pip-audit
   - Line 46 + 50: safety check (double bypass)

**After removing bypasses, CI will ACTUALLY fail on linting issues (as it should).**

### 📋 Phase 10 - Final Verification
1. Run full pylint: `cd /Users/pacey/Documents/SourceCode/ganglia_repos/ganglia-core/ganglia-studio && .venv/bin/pylint src/ganglia_studio/ --disable=C0111,R0903,R0913,C0103,W0212,W0611,C0302,R0801`
2. Target: 10.0/10 rating, exit code 0
3. Run all tests: `.venv/bin/pytest tests/unit/ -v`
4. Ensure 81 tests pass (17 deselected as slow)
5. Commit all fixes
6. Push to PR
7. Watch CI pass

## Commands Reference

### Check Current Pylint Status
```bash
cd /Users/pacey/Documents/SourceCode/ganglia_repos/ganglia-core/ganglia-studio
.venv/bin/pylint src/ganglia_studio/ --disable=C0111,R0903,R0913,C0103,W0212,W0611,C0302,R0801
```

### Get Issue Counts
```bash
.venv/bin/pylint src/ganglia_studio/ --disable=C0111,R0903,R0913,C0103,W0212,W0611,C0302,R0801 --output-format=parseable 2>&1 | sed -n 's/.*\[\([A-Z0-9]*\)(.*/\1/p' | sort | uniq -c | sort -rn
```

### Run Tests
```bash
cd /Users/pacey/Documents/SourceCode/ganglia_repos/ganglia-core/ganglia-studio
source .envrc
.venv/bin/pytest tests/unit/ -v --tb=short
# Should see: 81 passed, 17 deselected
```

### Commit Template
```bash
git add -A
git commit -m "refactor: fix [N] pylint issues - Phase [X] [description]

[detailed list of changes]

Progress: [X]/220 issues resolved"
```

## Key Principles

1. **No shortcuts**: Fix the root cause, not the symptom
2. **Test after each phase**: Ensure tests still pass
3. **Commit frequently**: After each logical phase (every 20-30 fixes)
4. **Follow patterns**: Look at existing code for style consistency
5. **Preserve functionality**: Don't change behavior, only improve code quality

## Expected Timeline

- Phase 1 remaining: ~45 minutes (55 line-too-long + misc)
- Phase 2: ~15 minutes (8 imports)
- Phase 3: ~20 minutes (15 else-after-return patterns)
- Phase 4: ~90 minutes (38 function signatures)
- Phase 5: ~120 minutes (27 function decompositions)
- Phase 6-8: ~30 minutes (misc cleanup)
- Phase 9: ~5 minutes (CI config)
- Phase 10: ~15 minutes (verification)

**Total**: ~5-6 hours of focused work

## Notes for Next Model

- The user expects you to complete ALL phases without asking for permission
- Don't get distracted by the CI bypasses - fix the linting first, then remove bypasses
- Tests are already passing (81/81), don't break them
- The goal is 10.0/10 pylint rating with zero warnings
- Work systematically through phases - don't jump around
- Commit after each phase for checkpoints
- When done with linting, remove CI bypasses and verify everything passes

## Current Git State

```
Branch: ci/fix-dependency-installation
Last commit: 504595b
Status: 11 files changed (Phase 1 partial complete)
Ready for: Phase 1 completion (line-too-long fixes)
```

Good luck! The user won't interrupt you - just keep working until CI is green. 🚀

