# AI PR Test Generator

This project automatically:
- Polls GitHub Pull Requests with specified labels
- Generates AI-based test cases using GLM 4.7 Flash via opencode
- Processes multiple PRs and generates test case and module test files
- Fetches latest PR diffs from GitHub API
- Tracks processed PRs to avoid duplication
- Creates test files in `generated_tests/` directory

## Requirements

- Python 3.8+
- Git
- Node.js (for opencode installation)
- opencode installed globally

---

## Setup Instructions

### 1. Install OpenCode

Install opencode globally using npm:

```bash
npm install -g opencode-ai
```

Or using the installation script:

```bash
curl -fsSL https://opencode.ai/install | bash
```

Verify installation:

```bash
opencode --version
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Create `.env` File

Create a `.env` file in the root directory:

```bash
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPO=your-username/your-repo
PR_LABEL=ai-test
MODEL_NAME=zai-coding-plan/glm-4.7-flash
```

**Important:**
- Your `GITHUB_TOKEN` must have read and write access to pull requests
- The `MODEL_NAME` can be customized (default: `zai-coding-plan/glm-4.7-flash`)
- Test cases will be generated for any PR with the specified label

---

## How It Works

### 1. `poller.py`
- Fetches open PRs with the specified label from GitHub API
- Downloads the diff file and saves it to `generated_tests/` directory
- Tracks processed PRs in `processed_prs.json` to avoid duplication
- Exits after processing one PR (use `workflow.py` to process multiple)

### 2. `workflow.py`
- Processes all `pr_*.diff` files in `generated_tests/` directory
- For each PR, fetches the latest diff from GitHub API
- Generates comprehensive test cases (`pr_{number}_diff_testcases.md`)
- Generates module-level tests (`pr_{number}_diff_module_tests.md`)
- Skips already processed PRs (based on `processed_prs.json`)
- Supports multiple functions: arithmetic, array handling, string operations, data structures

### 3. `testcase_generator.py`
- Takes C code diff as input
- Uses opencode to generate structured test case tables
- Creates comprehensive test coverage for all functions

### 4. `glm_client.py`
- Wraps opencode subprocess calls
- Configures and sends prompts to the GLM model
- Returns generated test cases

### 5. `processed_prs.json`
- Stores already processed PR numbers
- Prevents duplicate processing across runs

---

## Running the Poller

To fetch and download PR diffs:

```bash
python poller.py
```
---

## Running the Workflow

To process all existing PR diffs and generate test files:

```bash
python workflow.py
```

---
## Troubleshooting

### PR not being processed

Check:
- `processed_prs.json` to see if the PR was already processed
- Your `GITHUB_TOKEN` permissions (needs pull request access)
- Correct `GITHUB_REPO` format (owner/repo)
- The PR has the correct label (`ai-test` by default)

### opencode not found

If you get a "opencode not found" error:

1. Make sure opencode is installed:
```bash
npm install -g opencode-ai
```

2. Verify installation:
```bash
opencode --version
```

3. Check if opencode is in your PATH:
```bash
which opencode  # or where opencode on Windows
```

### opencode subprocess timeout

If opencode times out:
- Reduce the diff size by filtering the PR diff
- Increase timeout in `glm_client.py`
- Check if opencode is running properly

### Test files not generated

- Ensure the diff file exists in `generated_tests/` directory
- Check if the PR number exists in `processed_prs.json`
- Verify the `.env` file is configured correctly

### API rate limits

GitHub API has rate limits:
- Unauthenticated: 60 requests/hour
- Authenticated: 5,000 requests/hour

If you hit rate limits, wait a few minutes or increase the time between requests.

---
## License

MIT License
