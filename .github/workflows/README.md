# GitHub Actions CI/CD Documentation

This directory contains the GitHub Actions workflows for `ganglia-studio`.

## Workflows

### 1. CI (`ci.yml`)

**Trigger:** Push to `main`/`develop` branches, Pull Requests

**Jobs:**

#### Test Job
- **Matrix:** Python 3.10-3.13, Ubuntu + macOS
- **Steps:**
  1. Install system dependencies (FFmpeg)
  2. Install Python dependencies
  3. Run unit tests
  4. Run integration tests (skip costly)
  5. Upload test results as artifacts

#### Lint Job
- Run `ruff` (fast linter and formatter)
- Run `pylint` (comprehensive linting)
- Continues on error (won't block PR)

#### Coverage Job
- Run unit tests with coverage
- Generate HTML and XML reports
- Upload coverage artifacts
- Display coverage summary

#### Package Job
- Build Python package (wheel + sdist)
- Verify package with `twine check`
- Upload dist artifacts

**Cost:** ~5-10 minutes per run, free on GitHub's free tier

---

### 2. Costly Tests (`costly-tests.yml`)

**Trigger:** Manual dispatch only (`workflow_dispatch`)

**Purpose:** Run integration tests that make real API calls

**Requirements:**
- Repository secrets must be configured:
  - `OPENAI_API_KEY` (required)
  - `GOOGLE_APPLICATION_CREDENTIALS` (optional)
  - `SUNO_API_KEY` (optional)
  - `META_MUSICGEN_API_KEY` (optional)

**Steps:**
1. Verify API keys are configured
2. Run tests marked with `@pytest.mark.costly`
3. Upload test results
4. Upload generated videos (if any)

**Cost:** Consumes API credits + GitHub Actions minutes

**How to run:**
1. Go to Actions tab in GitHub
2. Select "Costly Tests (Manual)"
3. Click "Run workflow"
4. Choose Python version
5. Click "Run workflow"

---

### 3. Dependency Check (`dependency-check.yml`)

**Trigger:** 
- Weekly schedule (Mondays at 9 AM UTC)
- Manual dispatch

**Purpose:** Security and dependency management

**Steps:**
1. Run `pip-audit` to check for known vulnerabilities
2. Run `safety check` for additional security scanning
3. List outdated dependencies
4. Upload security reports as artifacts

**Cost:** ~2 minutes per run

---

### 4. Dependabot (`dependabot.yml`)

**Purpose:** Automated dependency updates

**Configuration:**
- **Python dependencies:** Weekly on Monday at 9 AM
- **GitHub Actions:** Monthly
- Auto-assigns to `pacey`
- Labels PRs with `dependencies`

**Benefits:**
- Keeps dependencies up-to-date
- Security patches applied automatically
- Version compatibility issues caught early

---

## CI/CD Best Practices

### Running Tests Locally Before Push

Always run tests locally to save CI minutes:

```bash
# Run all checks that CI will run
pytest tests/unit/ -v
pytest tests/integration/ -v -m "not costly"
ruff check src/
pylint src/ganglia_studio/
```

### Test Markers

- `@pytest.mark.unit`: Unit tests (always run in CI)
- `@pytest.mark.integration`: Integration tests (run in CI, skip costly)
- `@pytest.mark.costly`: Tests that use real API keys (manual only)
- `@pytest.mark.slow`: Long-running tests

### Cost Optimization

1. **Matrix Strategy:** Limited combinations to reduce CI minutes
   - Ubuntu: All Python versions
   - macOS: Only Python 3.12, 3.13 (most recent)

2. **Fail Fast:** Disabled to see all failures even if one fails

3. **Caching:** Pip cache enabled to speed up dependency installation

4. **Conditional Steps:** Some steps only run on specific OS

---

## Setting Up CI/CD for a New Repository

### Step 1: Enable GitHub Actions

1. Go to repository Settings → Actions → General
2. Set "Actions permissions" to "Allow all actions and reusable workflows"
3. Set "Workflow permissions" to "Read and write permissions"

### Step 2: Configure Secrets (for Costly Tests)

1. Go to Settings → Secrets and variables → Actions
2. Add repository secrets:
   - `OPENAI_API_KEY`
   - `GOOGLE_APPLICATION_CREDENTIALS` (if needed)
   - Other API keys as needed

### Step 3: Enable Dependabot

1. Go to Settings → Security → Dependabot
2. Enable "Dependabot alerts"
3. Enable "Dependabot security updates"
4. Dependabot version updates are already configured via `dependabot.yml`

### Step 4: Configure Branch Protection (Recommended)

1. Go to Settings → Branches
2. Add rule for `main` branch:
   - Require pull request reviews
   - Require status checks to pass:
     - `test (ubuntu-latest, 3.12)`
     - `lint`
     - `coverage`
   - Require branches to be up to date before merging

---

## Monitoring CI/CD

### Viewing Workflow Runs

1. Go to the "Actions" tab in GitHub
2. Select a workflow to see run history
3. Click on a run to see job details
4. Click on a job to see step logs

### Artifacts

After each run, artifacts are available for download:
- Test results (JUnit XML)
- Coverage reports (HTML + XML)
- Built packages (wheel + sdist)
- Security reports
- Generated videos (from costly tests)

### Badges

Add badges to README.md:

```markdown
![CI](https://github.com/OWNER/ganglia-studio/actions/workflows/ci.yml/badge.svg)
![Dependency Check](https://github.com/OWNER/ganglia-studio/actions/workflows/dependency-check.yml/badge.svg)
```

---

## Troubleshooting

### "FFmpeg not found" errors
- Check that system dependencies step ran successfully
- FFmpeg should be installed in both Ubuntu and macOS jobs

### Dependency installation failures
- Check pip cache is working
- Verify `setup.py` and `requirements.txt` are in sync
- Check for platform-specific dependency issues

### Test failures only in CI
- Could be environment differences (CI=true is set)
- Check for hardcoded paths or assumptions about file locations
- Use `$TMPDIR` or `tempfile` for temp files

### Secrets not available
- Secrets are only available in repository where they're defined
- Forks don't have access to secrets (security feature)
- Costly tests will fail if secrets aren't configured

---

## Future Enhancements

Potential additions to CI/CD:

1. **Code Coverage Tracking:**
   - Upload to Codecov or Coveralls
   - Enforce minimum coverage thresholds
   - Comment coverage changes on PRs

2. **Performance Benchmarks:**
   - Track video generation performance over time
   - Alert on significant regressions

3. **Docker Image Builds:**
   - Build and push Docker images
   - Run tests in containerized environment

4. **Release Automation:**
   - Auto-publish to PyPI on tag
   - Generate release notes from commits
   - Create GitHub releases with artifacts

5. **Documentation Builds:**
   - Build and deploy Sphinx docs
   - API documentation generation
   - Deploy to GitHub Pages

