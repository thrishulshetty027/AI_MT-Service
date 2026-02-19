# AI PR Test Generator

This project automatically:

- Polls GitHub Pull Requests
- Generates AI-based test suggestions
- Saves PR diff files`
- Tracks processed PRs to avoid duplication
- Works with a locally running Ollama model

## Requirements

- Python 3.8+
- Git
- Ollama installed locally

---

## Setup Instructions

## Install Ollama

Pull your model:
ollama pull qwen2.5-coder:7b

Start Ollama:
ollama serve
---

## Install Python Dependencies

pip install -r requirements.txt
---

## Create `.env` File

Create a `.env` file in the root directory:

```
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPO=your-username/your-repo
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_BASE_URL=""
```

---

## How It Works

1. `poller.py`
   - Fetches open PRs from GitHub
   - Downloads PR diffs
   - Saves them inside `generated_tests/`
   - Calls the test generator

2. `testcase_generator.py`
   - Sends PR diff to Ollama
   - Generates suggested test cases

3. `workflow.py`
   - Can be used to orchestrate execution manually

4. `processed_prs.json`
   - Stores already processed PR numbers
   - Prevents duplicate processing

---

## Running the Poller

From project root:

```bash
python poller.py
```

If a new PR is detected:

- A file like `generated_tests/pr_12.diff` will be created
- Test suggestions will be generated

---

## Troubleshooting

## Ollama connection refused

Make sure this is running:

```bash
ollama serve
```

---

## PR not being processed

Check:
- `processed_prs.json`
- Your `GITHUB_TOKEN`
- Correct `GITHUB_REPO` format

---
