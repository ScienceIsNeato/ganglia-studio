# GANGLIA Studio - Systematic Linting Cleanup

## Mission
Fix ALL 220 pylint warnings to achieve 10.0/10 rating, then ensure all tests pass and CI is green.

## Current Status
- **Branch**: `ci/fix-dependency-installation`
- **Last Commit**: `f13a822` - "refactor: fix 8 pylint issues - Phase 2 import hygiene"
- **Progress**: 220/220 issues resolved (100%)
- **Current Rating**: 10.0/10 across the full pylint suite (`--disable=C0111,R0903,R0913,C0103,W0212,W0611,C0302,R0801`)

## What's Been Completed

### ✅ Phase 1 - Quick Wins (90/97 issues fixed)

**Files Modified (latest updates):**
1. 47x `C0301` fixes across `music/backends/*.py`, `video/*`, and `story/story_generation_driver.py`.
2. `tests/integration/third_party/test_gcui_suno_live.py` - restored real API coverage (no local mocks).
3. `tests/unit/music/backends/test_gcui_suno.py` - new mocked/offline coverage for gcui flows.
4. `.github/workflows/ci.yml` / `.github/workflows/dependency-check.yml` - removed `continue-on-error` / `|| true`.
5. `tests/test_helpers.py` - missing Google Cloud deps now raise a friendly error immediately.
6. `src/ganglia_studio/music/music_lib.py` - split long logging/doc lines (6x `C0301`).
7. `src/ganglia_studio/music/lyrics_lib.py` - split doc/prompt strings (2x `C0301`).

**Files Modified (earlier Sonnet pass):**
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

### ✅ Phase 2 - Import Hygiene (8/8 issues fixed)

- `music/music_lib.py`: added top-level `shutil` import and cleaned four copy helpers.
- `music/backends/suno_api_org.py`: promoted `json` import and reused globally.
- `video/image_generation.py`: top-level `PIL.ImageDraw/ImageFont` and `shutil` imports for overlay + batch helpers.
- `story/story_generation_driver.py`: top-level `traceback` import for failure logging.

Result: `pylint --enable=C0415` now exits cleanly (10.00/10 for that rule set).

### ✅ Phase 3 - Code Structure (13/13 issues fixed)

- Eliminated `no-else-return`, `no-else-raise`, `no-else-continue`, and `no-else-break` patterns across `music/music_lib.py`, `music/backends/{foxai_suno,suno_api_org}.py`, `video/{story_generation,story_processor,final_video_generation}.py`, and `utils/ffmpeg_utils.py`.
- Converted control flow to early returns / sequential checks; no behavior changes, only structural clarity.
- Targeted check: `pylint --disable=all --enable=R1705,R1720,R1723,R1724` now passes at 10.00/10.

### ✅ Phase 4 - Positional Argument Hygiene (38/38 issues fixed)

- All music backends + `MusicGenerator` now require optional parameters via keywords (no more 7-10 positional args).
- Video layer refactored: movie poster generator, final-video assembler, and caption stack (`captions.py`) expose keyword-only knobs, and every call site/test updated accordingly.
- `pylint --disable=all --enable=R0917` returns 0 findings (10.00/10).

## What Remains

### 🔄 Phase 1 - Quick Wins (Remaining: 0 issues)

All quick-win items are closed. Line-length, unused-argument, and FIXME cleanups are complete.

### 📋 Phase 2 - Import Issues ✅
Completed; all dynamic imports are now hoisted to module scope.

### 📋 Phase 3 - Code Structure ✅
Structural cleanups complete; onward to Phase 4 (function signatures).

### 📋 Phase 4 - Too Many Positional Arguments ✅
Completed (all `R0917` cleared); proceed to Phase 5 complexity refactors.

### 📋 Phase 5 - Function Complexity ✅
- Refactored `music/music_lib.py`, music backends, and `video/story_processor.py`.
- Simplified ROI detection, final video assembly, and all dynamic/static captions helpers.
- `pylint --disable=all --enable=R0914,R0911,R0912,R0915,R1702` now passes cleanly.

### 📋 Phase 6 - Too Many Instance Attributes ✅
- Introduced `MusicOptions` wrapper + properties in `TTVConfig`.
- Refined `Word` into `WordLayout` container and added layout helper dataclasses.
- Simplified `FFmpegOperation` to rely on manager state instead of duplicating queues.

### ✅ Phase 7 - Interface Consistency
- Signature mismatches resolved across music backends; `pylint --enable=W0221` clean.

### ✅ Phase 8 - Misc Cleanup
- Replaced lingering `global` usage with cached/holder patterns.
- Converted broad `Exception` raises to `RuntimeError` and updated warning strings to f-strings.
- Cleaned unused locals and ensured ROI destructuring only stores needed values.
- Targeted check (`pylint --disable=all --enable=W0511,W0612,W0613,W0603,W0602,W0719,W0404,W0621,C0209`) now passes at 10.00/10.

### 🚀 Latest Progress (Codex pass)
- Eliminated the final `R0917` regressions by making every helper keyword-only:
  `music/music_lib.py`, `music/backends/{suno_api_org,foxai_suno,gcui_suno,meta}.py`,
  `video/{story_processor,caption_roi,final_video_generation,captions}.py`.
- Fixed new runtime regressions surfaced during cleanup (`gcui_suno` quota log, Suno timeout handling,
  `story_processor` keyword plumbing, caption filters, FFmpeg compose helpers).
- Resolved remaining `C0301`/`C0305` stragglers and tightened crossfade helpers.
- Full-suite pylint command now returns 10.00/10 with zero findings:
  ```bash
  activate && cd ${AGENT_HOME}/ganglia-core/ganglia-studio && \
  pylint src/ganglia_studio/ --disable=C0111,R0903,R0913,C0103,W0212,W0611,C0302,R0801
  ```

### 📋 Phase 9 - CI bypass removal ✅
All `continue-on-error` / `|| true` gates have been removed from `ci.yml` and `dependency-check.yml`. Expect lint + security jobs to fail loudly until the remaining issues are fixed.

### 📋 Phase 10 - Final Verification
1. ✅ Full pylint run (command above) — 10.00/10, no findings.
2. ✅ Targeted regressions: `pytest tests/unit/video/test_captions.py tests/unit/video/test_caption_roi.py tests/unit/story/test_processor.py -q` → 20 passed.
3. ✅ Full sweep: `pytest tests/unit -v` → 101 passed (0 failed).
4. ⏳ Stage + commit all lint + test fixes.
5. Push branch, then `python cursor-rules/scripts/pr_status.py --watch <PR#>`.

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
Status: 11 files staged locally (music backends + video pipeline + STATUS.md) awaiting test run
Ready for: Phase 10 test pass + commit/push
```

Good luck! The user won't interrupt you - just keep working until CI is green. 🚀

