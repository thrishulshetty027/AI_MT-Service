# AI MT-Service (Cantata Test Generator)

## Overview

**Core Value:** Generate C unit test files that compile in Cantata v24.04 (MSVC17) without manual fixes from GitHub PR diffs.

This service polls GitHub PRs for C code changes and generates compilable Cantata unit test scripts using GLM 4.7 Flash via opencode CLI. The project is being refactored from a broken LLM-to-C pipeline into a deterministic system with proper type safety and error handling.

**Current Status:** Phase 1 of 3 (IR Pipeline & Parsing) — 50% complete

## Features

- **GitHub PR Polling:** Fetch PR diffs by label and repository
- **LLM Test Generation:** Uses GLM 4.7 Flash to generate structured test case definitions in markdown
- **C Code Generation:** Generates compilable Cantata .c test scripts with complete boilerplate
- **Architecture Foundation:** Built on typed intermediate representation (IR) with C signature extraction
- **Self-Healing:** Detects and auto-fixes common compile-time errors
- **Planning-Driven Development:** Uses GSD methodology for structured project execution

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI MT-Service                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  GitHub PRs ──► Poller ──► Download Diffs                   │
│        │                                                   │
│        ▼                                                   │
│  ┌──────────────────────────────────────┐                  │
│  │       Stage 1: Test Case Design       │◄── GLM 4.7 Flash │
│  │   (Markdown tables with test data)    │                  │
│  └──────────────────────────────────────┘                  │
│        │                                                   │
│        ▼                                                   │
│  ┌──────────────────────────────────────┐                  │
│  │     Stage 2: C Code Generation        │                  │
│  │  (Deterministic templates + IR)       │                  │
│  └──────────────────────────────────────┘                  │
│        │                                                   │
│        ▼                                                   │
│  Generated .c test files (Cantata-compatible)               │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Current Implementation

The project has two implementation paths (old VIO-based being replaced):

**Legacy Pipeline (deprecated):**
- `vio_llm_client.py` — VIO LLM interface
- `cantata_integration.py` — Old Cantata integration

**New GLM Pipeline (current focus):**
- `glm_client.py` — GLM 4.7 Flash via opencode CLI
- `src/ir_models.py` — Pydantic IR models for typed test data
- `src/signature_extractor.py` — tree-sitter C signature extraction
- `src/markdown_parser.py` — Parse LLM markdown → IR
- `src/type_resolver.py` — Infer types from signatures
- `src/code_generator.py` — Jinja2 template-based C generation
- `src/self_healer.py` — Auto-fix common compile errors
- `templates/` — Jinja2 templates for Cantata .c files

## Requirements

- **Python:** 3.10+ (required for tree-sitter, pydantic v2, pytest 9.x)
- **C compiler:** MSVC17 (cl.exe) — Target for Cantata v24.04
- **Git:** For version control
- **Node.js:** 14+ (for opencode CLI)
- **opencode:** Globally installed via npm
- **Cantata:** v24.04 at `C:\LegacyApp\qa_systems\` (compiler target)
- **GitHub:** Personal access token with PR read/write access

## Project Structure

```
.
├── .planning/                 # GSD planning documents
│   ├── PROJECT.md            # Project context
│   ├── ROADMAP.md            # 3-phase execution plan
│   ├── REQUIREMENTS.md       # Requirements (v1/v2/out of scope)
│   ├── STATE.md              # Current project state
│   ├── config.json           # GSD workflow preferences
│   └── phases/
│       └── 01-ir-pipeline-parsing/
│           ├── 01-01-PLAN.md      (✓ Complete)
│           ├── 01-02-PLAN.md      (Ready to execute)
│           └── 01-RESEARCH.md
├── src/                       # New IR pipeline modules
│   ├── ir_models.py          # Pydantic IR schemas
│   ├── signature_extractor.py  # tree-sitter C parser
│   ├── markdown_parser.py     # Markdown → IR
│   ├── type_resolver.py       # Type inference
│   ├── code_generator.py      # C code generation
│   ├── self_healer.py         # Error auto-fixing
│   └── c_validator.py         # C syntax validation
├── templates/                 # Jinja2 templates
│   ├── cantata_header.h.j2    # Header file template
│   └── cantata_test.c.j2      # Test case template
├── generated_tests/           # Output directory
│   ├── pr_diff.txt
│   ├── module_testcases.md
│   └── *.c test files
├── docs/                      # Documentation (not yet added)
├── AGENTS.md                  # GSD workflow instructions
├── README.MD                  # This file
├── cantata_integration.py    # Legacy (being phased out)
├── glm_client.py              # GLM 4.7 Flash client
├── poller.py                  # GitHub PR poller
├── testcase_generator.py     # LLM Stage 1 test case generator
├── workflow.py                # Legacy workflow (monolithic)
├── run.py                     # New unified entry point
├── vio_config.py              # Legacy VIO config
├── vio_llm_client.py          # Legacy VIO client
└── processed_prs.json         # PR processing tracking
```

## Quick Start

### 1. Install Dependencies

```bash
# Install opencode globally
npm install -g opencode-ai

# Or using the installation script
curl -fsSL https://opencode.ai/install | bash

# Verify installation
opencode --version

# Install Python dependencies (requires Python 3.10+)
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the root directory:

```bash
# GitHub configuration
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_REPO=your-username/your-repo
PR_LABEL=ai-test

# LLM configuration
MODEL_NAME=zai-coding-plan/glm-4.7-flash
USE_LLM_TYPE=glm          # Set to "glm" or "vio" (glm is recommended)

# Cantata configuration
CANTATA_PATH=C:\LegacyApp\qa_systems
INTEGRATE_CANTATA=true
```

### 3. Run the Service

**Poll GitHub and process one PR:**

```bash
python run.py --repo owner/repo --label ai-test
```

**Process a specific PR:**

```bash
python run.py --pr 167 --diff generated_tests/pr_diff.txt
```

**Interactive mode:**

```bash
python run.py --interactive
```

**Run legacy workflow (deprecated):**

```bash
python workflow.py
```

### 4. Generate and Compile Tests

```bash
# Generate C test files
python run.py --repo owner/repo --label ai-test

# Check generated files
ls generated_tests/

# Verify with Cantata compiler
# The .c files should compile with MSVC17 without errors
```

## How It Works

### Pipeline Stages

**Stage 1: Poll and Fetch**
- `poller.py` — Fetches PR diffs from GitHub API
- `run.py` — Unified entry point (replaces separate poller/workflow)
- Tracks processed PRs in `processed_prs.json`

**Stage 2: Test Case Generation (LLM)**
- `glm_client.py` — Calls GLM 4.7 Flash via opencode CLI
- `testcase_generator.py` (Stage 1) — Generates markdown test case tables
- Output: `module_testcases.md` with structured test data

**Stage 3: IR Conversion (new)**
- `src/markdown_parser.py` — Parses markdown → IR models
- `src/signature_extractor.py` — Extracts C function signatures via tree-sitter
- `src/type_resolver.py` — Infers types from signatures
- Ensures all test data values are preserved

**Stage 4: C Code Generation**
- `src/code_generator.py` — Jinja2 templates for Cantata .c files
- `templates/` — Template files (header, test functions)
- Output: Compilable Cantata test scripts

**Stage 5: Self-Healing**
- `src/self_healer.py` — Detects and fixes common errors:
  - Array syntax (`arr[] = 0` → `arr[] = {1,2,3}`)
  - Function call syntax (`func(arr[])` → `func(arr, size)`)
  - Missing semicolons, undeclared variables
- Generates fix report

### Current Implementation Paths

**Deprecated (to be removed):**
- `vio_llm_client.py` — Old VIO LLM interface
- `cantata_integration.py` — Legacy integration
- Configure `USE_LLM_TYPE=vio` in `.env`

**Current (recommended):**
- `glm_client.py` — GLM 4.7 Flash via opencode
- Configure `USE_LLM_TYPE=glm` in `.env`

## Development Roadmap

The project follows GSD (Get-Shit-Done) planning methodology:

### Phase 1: IR Pipeline & Parsing (50% Complete)
- [x] IR model schemas + tree-sitter C signature extractor
- [ ] Markdown parser + type resolver connecting signatures to test cases
- **Goal:** Structured data pipeline from LLM markdown to typed IR

### Phase 2: Code Generation & Cantata Compliance
- [ ] Jinja2 templates producing compilable Cantata .c scripts
- [ ] Complete Cantata boilerplate (main(), coverage rules, includes)
- [ ] Struct field-by-field initialization
- **Goal:** Deterministic code generation with 100% compatibility

### Phase 3: Integration & Self-Healing
- [ ] Single-command pipeline (poll + generate)
- [ ] Auto-fix common compile-time errors
- [ ] Remove VIO LLM code completely
- [ ] Dead code removal
- **Goal:** `python run.py` produces validated .c files with zero manual fixes

See `.planning/ROADMAP.md` for detailed phase planning.

## Key Decisions

- **Hybrid Architecture:** LLM for test case design (Stage 1 works well), deterministic Python templates for code generation (Stage 2 replacement)
- **Type Safety:** IR models ensure data flows faithfully; eliminates data loss class of bugs
- **Single LLM Backend:** GLM 4.7 Flash via opencode CLI only
- **Target Compiler:** MSVC17 (cl.exe) for Cantata v24.04 compatibility
- **Methodology:** GSD planning-driven development for structured execution

## Troubleshooting

### Python Version Issues

The project requires Python 3.10+ for tree-sitter, pydantic v2, and pytest 9.x. If you see import errors:

```bash
# Check Python version
python --version

# If < 3.10, upgrade:
# Windows: Download Python 3.10+ from python.org
# Linux: sudo apt install python3.10 python3.10-venv
```

### opencode Not Found

```bash
# Reinstall opencode
npm install -g opencode-ai

# Verify installation
opencode --version

# If still failing, check Node.js version (need 14+)
node --version
```

### Cantata Compilation Errors

Common issues and fixes:

**Issue:** Arrays initialized to 0 instead of `{1,2,3}`
- **Fix:** Generated by IR pipeline; check type inference and signature extraction

**Issue:** Function calls use wrong syntax (`func(arr[])`)
- **Fix:** Self-healing module catches and repairs this

**Issue:** Missing Cantata boilerplate
- **Fix:** Jinja2 templates ensure completeness

Run self-healing: `python run.py --auto-fix` (when implemented)

### GitHub API Rate Limits

- Unauthenticated: 60 requests/hour
- Authenticated (with token): 5,000 requests/hour

If you hit limits, wait a few minutes or increase polling interval.

### Test Files Not Generated

1. Verify `.env` configuration
2. Check `processed_prs.json` for duplicates
3. Ensure PR has correct label
4. Confirm token has PR read/write access

## Usage Examples

### Process Multiple PRs Sequentially

```bash
python run.py --repo owner/repo --label ai-test
# Continues until no more PRs with label found
```

### Process Specific PR

```bash
python run.py --pr 167
# Uses cached diff from file
```

### Generate from File (no GitHub)

```bash
python run.py --diff path/to/pr_diff.txt
```

### Legacy Mode (deprecated)

```bash
USE_LLM_TYPE=vio python workflow.py
```

## Contributing

This project uses GSD methodology. For contributions:

1. Review current phase in `.planning/ROADMAP.md`
2. Check requirements in `.planning/REQUIREMENTS.md`
3. Create discussion with `/gsd-discuss-phase N`
4. Plan with `/gsd-plan-phase N`
5. Execute with `/gsd-execute-phase N`
6. Verify with `/gsd-verify-work N`

## License

MIT License

## References

- Cantata v24.04: `C:\LegacyApp\qa_systems\`
- GSD Methodology: [Get-Shit-Done](https://github.com/anomalyco/get-shit-done)
- OpenCode CLI: [opencode.ai](https://opencode.ai)

---

**Last Updated:** April 27, 2026
**Project Phase:** 1 of 3 — IR Pipeline & Parsing (50% complete)
