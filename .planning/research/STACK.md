# Stack Research

**Domain:** AI-powered Cantata unit test generator for C code (brownfield improvement)
**Researched:** 2026-04-24
**Confidence:** HIGH (for core stack), MEDIUM (for C validation tooling)

## Executive Summary

This is a brownfield Python CLI tool that generates Cantata-compatible C unit test files from GitHub PR diffs using GLM 4.7 Flash via the opencode CLI. The **primary failure mode** is Stage 2 LLM output — the generated C code drops test data values and produces invalid syntax (`int arr[] = 0;` instead of `int arr[] = {1,2,3,4};`).

The stack strategy is: **keep the existing foundation** (Python, opencode CLI, requests, dotenv), **upgrade Python baseline** to 3.10+ (required by modern parsing libraries), **replace regex-based C/diff parsing** with proper parser libraries, and **add structural validation** so LLM output errors are caught before saving to disk.

> **Critical dependency constraint:** pycparser 3.0, tree-sitter 0.25.x, pydantic v2, and pytest 9.x all require **Python >=3.10**. The project currently states Python 3.8+. You MUST upgrade the Python baseline to 3.10+ to use the recommended stack.

---

## Recommended Stack

### Core Technologies (Keep — Already in Use)

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Python | 3.10+ (upgrade from 3.8) | Runtime | 3.10 is the minimum for pycparser 3.0, tree-sitter 0.25, pydantic v2, pytest 9.x. 3.10 is also the current minimum for most modern Python libraries. Windows MSVC compatibility is not affected. | HIGH |
| opencode-ai (npm global) | v1.14.x (latest) | LLM inference via CLI subprocess | Already integrated. The `opencode run -m <model> --file <path> --format default "prompt"` command is the correct non-interactive invocation. v1.14.22 (Apr 2026) is current. Supports `--format json` for structured parsing if needed later. | HIGH |
| requests | 2.32.x | GitHub REST API calls (PRs, diffs, labels) | Industry standard, already used throughout `poller.py` and `workflow.py`. No reason to change. | HIGH |
| python-dotenv | 1.1.x | .env file loading | Standard pattern, already used. Keep. | HIGH |
| subprocess (stdlib) | — | Invoking opencode CLI | Required for opencode integration. Already in place. | HIGH |
| re (stdlib) | — | Supplementary text cleanup | Still needed for light cleanup in `clean_output()`. But **stop using regex as the primary C code parser** — that's the root cause of signature extraction failures. | HIGH |

### New Additions — Fix the Broken Pipeline

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| **unidiff** | 0.7.5 | Parse unified diff format into structured objects | **Replaces the hand-rolled `extract_new_changes()` in workflow.py.** The current implementation manually iterates diff lines with string prefix checks. unidiff gives `PatchSet` → `PatchedFile` → `Hunk` → added/removed lines as structured objects. This eliminates off-by-one errors in diff parsing. Pure Python, no dependencies, works on Windows. MIT license. Last updated Mar 2023 but stable (unified diff format doesn't change). | HIGH |
| **pydantic** | 2.11.x | Validate LLM output structure at both stages | **This is the critical missing piece.** Stage 1 produces markdown tables that get parsed manually with fragile `split('|')` logic. Stage 2 produces C code that goes straight to disk without any syntax validation. Pydantic models enforce: (1) every test case has required fields with non-zero values, (2) function signatures have valid types, (3) generated C code passes basic structural checks before being saved. This is the primary mechanism to prevent the `arr[] = 0` problem — validate BEFORE writing to disk, and retry the LLM call if validation fails. | HIGH |
| **tree-sitter** + **tree-sitter-c** | 0.25.2 + 0.24.x | Parse C code into AST for signature extraction and output validation | **Replaces the regex-based `extract_function_signatures_from_diff()` in cantata_integration.py.** The current regex pattern `r'(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{'` fails on: pointer returns (`int*`), struct returns, `FILE*` params, array params (`int arr[]`), multi-line signatures, and `#ifdef`-guarded code. Tree-sitter produces a proper AST that handles all C syntax correctly. **Key advantage over pycparser:** tree-sitter can parse incomplete code fragments (which is what LLMs generate) without needing a C preprocessor. No external dependencies (cpp/gcc) required. Pre-compiled wheels available for Windows x64. | HIGH |
| **pytest** | 9.0.x | Unit testing for the Python service itself | The current "tests" (`test_Vio_llm.py`, `test_format.py`) are ad-hoc manual scripts, not real unit tests. pytest 9.x provides: parametrized tests for C syntax validation, fixtures for diff samples, monkeypatching for LLM calls. Essential for preventing regressions as the pipeline is refactored. | HIGH |

### Supporting Libraries (Situational)

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| pycparser | 3.0 | Full C99 AST parsing | Use **only** if you need to validate that generated C code is semantically correct (e.g., all variables declared, types match). **Overkill for this project** because: (1) requires C preprocessor (cpp) installed, (2) requires complete, compilable C code, (3) the fake libc headers need manual setup on Windows. tree-sitter is better for this use case. Consider only if Cantata compilation errors persist after tree-sitter validation. | MEDIUM |
| logging (stdlib) | — | Replace print() statements with structured logging | The entire codebase uses `print("[INFO]...")` and `print("[ERROR]...")`. Standard library `logging` gives: log levels, file output, formatting. Low effort, high value for debugging LLM pipeline issues. Use when refactoring `glm_client.py` and `testcase_generator.py`. | HIGH |

---

## Installation

```bash
# Create virtual environment (Python 3.10+)
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux/Mac

# Core (keep — already installed)
pip install requests python-dotenv

# New — pipeline fix dependencies
pip install unidiff==0.7.5
pip install pydantic>=2.11
pip install tree-sitter>=0.25.2
pip install tree-sitter-c>=0.24

# Development
pip install -D pytest>=9.0

# opencode CLI (Node.js, global)
npm install -g opencode-ai@latest

# Create requirements.txt
pip freeze > requirements.txt
```

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| tree-sitter-c | pycparser | pycparser 3.0 requires C preprocessor (cpp), needs complete compilable C code, and requires fake libc headers on Windows. tree-sitter parses incomplete fragments natively. pycparser is better for static analysis of complete programs, not for validating LLM-generated snippets. |
| unidiff | Manual diff parsing (current) | Current `extract_new_changes()` is 35 lines of hand-rolled string iteration that fails on edge cases (binary diffs, rename patches, mode changes). unidiff handles all unified diff variants with a tested library. |
| pydantic | Manual dict parsing (current) | Current `parse_test_cases_from_markdown()` uses fragile `split('\|')` logic with fallback regex. pydantic enforces type constraints, required fields, and value ranges at the model level. The retry-on-validation-failure pattern is the key mechanism to fix the `arr[] = 0` problem. |
| opencode CLI (subprocess) | OpenAI SDK direct API | The project constraint is GLM 4.7 Flash via opencode only. The opencode CLI is the correct integration point. The `run` command with `--file` and `--format` flags is the right non-interactive API. |
| pytest | unittest (stdlib) | unittest would work but pytest offers: parametrized tests (essential for testing multiple C syntax patterns), better assertions, fixture system for mock LLM responses. No downside vs unittest. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **regex for C parsing** | The current `re.findall(signature_pattern, diff_content)` in `testcase_generator.py:294` and `cantata_integration.py:44-47` is the root cause of missed function signatures. Regex cannot handle nested parens, pointer types, multi-line declarations, or preprocessor conditionals. | tree-sitter-c for AST-based parsing |
| **raw `dict` for LLM output** | The current pipeline stores LLM output as raw strings/dicts with no validation. This is why `arr[] = 0` silently passes through. | pydantic models with field validators |
| **print() for diagnostics** | Every module uses `print("[INFO]...")`. This makes it impossible to: filter by severity, log to file, or debug LLM retry loops. | stdlib `logging` module |
| **VIO LLM client** (`vio_llm_client.py`, `vio_config.py`) | Project decision: "Remove VIO LLM option — GLM 4.7 Flash via opencode only" (PROJECT.md). The VIO client also has a hardcoded API key in `vio_config.py` (security issue). | Delete these files. GLM via opencode only. |
| **`shell=True` in subprocess** | `glm_client.py:39` passes `shell=True` to `subprocess.run()`. On Windows, this invokes `cmd.exe` which can cause path escaping issues. The opencode command is a known binary — no shell needed. | `subprocess.run(cmd, shell=False, ...)` |
| **pycparser for this use case** | pycparser requires preprocessed C code (needs cpp/gcc on PATH). On the Windows/MSVC17 target, this means requiring a separate C compiler installation just for Python validation. tree-sitter-c has zero external dependencies and parses fragments. | tree-sitter-c |

---

## Stack Patterns by Variant

### For the C Signature Extraction Problem (Current: Broken)

**Use:** tree-sitter-c
**Why:** The current regex `r'(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{'` in `cantata_integration.py:44` fails on:
- `int* func(int* arr, int size)` — pointer return type (`\w+` doesn't match `int*`)
- `void enqueue(Queue* q, int item)` — struct pointer params
- `int (*func_ptr)(int, int)` — function pointer syntax

Tree-sitter query to extract all function definitions:
```python
import tree_sitter_c as tsc
from tree_sitter import Language, Parser, Query

C_LANGUAGE = Language(tsc.language())
parser = Parser(C_LANGUAGE)

tree = parser.parse(bytes(c_code, "utf8"))
query = Query(C_LANGUAGE, """
(function_definition
  type: (_) @return_type
  declarator: (function_declarator
    declarator: (identifier) @func_name
    parameters: (parameter_list) @params))
""")
# Extract all function signatures with correct types
```

### For the "LLM Drops Test Values" Problem (Current: Broken)

**Use:** pydantic + retry loop
**Why:** The current pipeline does:
1. LLM generates C code → `clean_output()` removes markdown → save to disk
2. No validation that array values survived, function calls are correct, etc.

New pipeline should be:
1. LLM generates C code → tree-sitter validates syntax → pydantic validates test data values match Stage 1 → if validation fails, retry LLM with error feedback → save to disk
2. The pydantic model checks: `arr_values != [0, 0, 0, 0]`, `func_call_args match signature`, etc.

### For the Diff Parsing Problem (Current: Fragile)

**Use:** unidiff
**Why:** Current `extract_new_changes()` in `workflow.py:154-192` manually iterates lines checking prefixes. unidiff gives structured access:
```python
from unidiff import PatchSet
patch = PatchSet.from_filename("pr_167.diff", encoding="utf-8")
for file in patch:
    for hunk in file:
        added_lines = [line.value for line in hunk if line.is_added]
```

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pycparser 3.0 | Python >=3.10 | Dropped Python 3.8/3.9 support in v3.0 (Jan 2026) |
| tree-sitter 0.25.x | Python >=3.10 | Pre-compiled wheels for Windows x64 |
| tree-sitter-c 0.24.x | tree-sitter >=0.24 | Separate package since tree-sitter 0.22 |
| pydantic v2 | Python >=3.10 | v1 works on 3.8 but v2 is much faster and better |
| pytest 9.x | Python >=3.10 | v8.x is the last to support 3.8 |
| unidiff 0.7.5 | Python >=3.7 | Widest compatibility, no external deps |
| opencode-ai v1.14.x | Node.js 18+ | npm global install, used as subprocess |
| requests 2.32.x | Python >=3.8 | No compatibility issues |

---

## Architecture Impact

The stack choices drive one critical architecture decision:

```
CURRENT PIPELINE (broken):
  diff → regex extraction → LLM prompt → raw string output → save to disk

PROPOSED PIPELINE:
  diff → unidiff parse → tree-sitter signature extraction
    → LLM prompt (with structured context)
    → tree-sitter syntax validation
    → pydantic data validation
    → retry on validation failure (max 3 attempts)
    → save validated C code to disk
```

The validation-retry loop is the key architectural change. Without it, LLM errors silently propagate to Cantata compilation failures.

---

## Sources

- [opencode-ai GitHub](https://github.com/anomalyco/opencode) — CLI `run` command docs, `--file` and `--format` flags verified (HIGH)
- [opencode.ai/docs/cli](https://opencode.ai/docs/cli/) — CLI command reference, `run` subcommand flags (HIGH)
- [pycparser 3.0 on PyPI](https://pypi.org/project/pycparser/) — v3.0 requires Python >=3.10, needs C preprocessor (HIGH)
- [tree-sitter 0.25.2 on PyPI](https://pypi.org/project/tree-sitter/) — Python bindings, Python >=3.10, Windows x64 wheels (HIGH)
- [unidiff 0.7.5 on PyPI](https://pypi.org/project/unidiff/) — PatchSet API, hunk/line access (HIGH)
- [pytest 9.0.3 on PyPI](https://pypi.org/project/pytest/) — Python >=3.10 (HIGH)
- [pydantic on PyPI](https://pypi.org/project/pydantic/) — v2 validation patterns (HIGH)
- [tree-sitter-c on GitHub](https://github.com/tree-sitter/tree-sitter-c) — C grammar for tree-sitter (MEDIUM — couldn't fetch PyPI page due to client challenge)
- Current codebase analysis: `glm_client.py`, `testcase_generator.py`, `workflow.py`, `cantata_integration.py`, `poller.py` (HIGH)

---
*Stack research for: AI-powered Cantata test generator from C code diffs*
*Researched: 2026-04-24*
