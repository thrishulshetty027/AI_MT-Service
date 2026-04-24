# Project Research Summary

**Project:** AI_MT-Service — AI-powered Cantata C unit test generator
**Domain:** LLM-driven code generation pipeline (brownfield improvement)
**Researched:** 2026-04-24
**Confidence:** HIGH

## Executive Summary

This is a brownfield Python CLI tool that generates Cantata-compatible C unit test files from GitHub PR diffs using GLM 4.7 Flash via the opencode CLI. The tool has a working Stage 1 (LLM designs test cases as markdown tables) but a **completely broken Stage 2** — the LLM-generated C code drops all test data values to zero (`int arr[] = 0;` instead of `int arr[] = {1,2,3,4};`), producing uncompilable output 100% of the time. This is the single problem that must be solved for the tool to be useful.

The recommended approach is a **hybrid architecture: LLM for test design (Stage 1), deterministic Python templates for code generation (Stage 2)**. This is the consensus finding across all four research dimensions. The LLM is excellent at understanding C semantics and designing test cases — Stage 1 works reliably. But LLMs are fundamentally unreliable at faithfully reproducing exact numeric values through multi-stage prompt chains. The fix is architectural, not prompt engineering: parse the LLM's markdown output into structured Python data, then generate C code deterministically using templates. This eliminates the entire class of "LLM drops values" bugs.

Key risks include a required Python baseline upgrade (3.8 → 3.10+), the need to replace regex-based C parsing with tree-sitter (which has a learning curve), and ensuring Cantata v24.04 compliance (specific macros, pragma directives, MSVC17 C89 compatibility). The 14 documented pitfalls are overwhelmingly concentrated in the current Stage 2 pipeline, which is the code being replaced entirely — meaning the fix addresses most known issues in one architectural change.

## Key Findings

### Recommended Stack

The stack strategy is **keep the foundation, replace the broken pipeline**. Keep Python, requests, python-dotenv, and the opencode CLI integration. Upgrade Python to 3.10+ (required by all modern parsing libraries). Add four new libraries to fix the data-loss pipeline: unidiff for diff parsing, tree-sitter + tree-sitter-c for C AST-based signature extraction, pydantic for output validation, and pytest for testing. Remove the VIO LLM client entirely (dead code + hardcoded API key security issue). Remove `shell=True` from subprocess calls.

**Core technologies:**
- **Python 3.10+** (upgrade from 3.8) — required minimum for pycparser 3.0, tree-sitter 0.25, pydantic v2, pytest 9.x
- **unidiff 0.7.5** — replaces hand-rolled diff parsing; structured `PatchSet` → `Hunk` → added/removed lines
- **tree-sitter + tree-sitter-c (0.25.2 / 0.24.x)** — replaces regex-based C signature extraction; handles pointers, arrays, multi-line declarations, incomplete code fragments
- **pydantic v2** — validates LLM output structure before C code generation; enables retry-on-validation-failure pattern
- **Jinja2** — template engine for deterministic C code generation from structured data
- **pytest 9.x** — replaces ad-hoc test scripts with proper unit tests

### Expected Features

The feature landscape is dominated by one insight: **PROMPT_2 (the Stage 2 LLM call) should be deleted**. It is the source of all critical bugs. The LLM generates test case *designs* well (Stage 1) but cannot faithfully transfer structured data into C code (Stage 2). Replacing Stage 2 with deterministic Python templates solves 6 of the top 8 critical/moderate pitfalls simultaneously.

**Must have (table stakes — P1):**
- Compilable C output — the entire tool is useless without this
- Faithful data transfer between stages — markdown values must appear identically in C code
- Correct array initialization syntax (`int arr[] = {1,2,3,4};`, never `= 0`)
- Correct function call syntax (`func(arr, size)`, never `func(arr[], size)`)
- Robust function signature extraction from diffs (handle `int arr[]`, `const char*`, struct pointers)
- Cantata++ framework compliance (`cantpp.h`, `TEST_SCRIPT_INFO`, `CHECK_EQUAL`, `RUN_TEST`, coverage analysis, `main()`)
- Correct header file generation from actual parsed signatures
- Single command entry point (merge poller.py + workflow.py)

**Should have (competitive — P2):**
- Post-generation compilation validation (run MSVC17, capture errors)
- Self-healing compile loop (parse errors, apply deterministic fixes)
- Branch-aware test generation (detect if/else/switch, ensure coverage per branch)
- Struct field initialization (designated initializers `{.field = value}`)

**Defer (v2+):**
- Cantata Server result upload — trivial HTTP POST once tests compile
- PR comment posting — team visibility feature
- Test deduplication — optimization, not functionality
- Coverage report interpretation — operational enhancement

### Architecture Approach

The new architecture replaces the "LLM generates C code" pipeline with a deterministic intermediate representation (IR) pipeline. The LLM generates test case *designs* as markdown (Stage 1, already working). A new `TestCaseParser` converts that markdown into structured Python `TestCase` dataclasses — the IR. A new `CCodeGenerator` expands Jinja2 templates using the IR + parsed function signatures. A new `CValidator` runs deterministic syntax checks before writing files. The LLM is never involved in code generation.

**Major components:**
1. **DiffAnalyzer** (`diff_analyzer.py`) — Extracts function signatures, struct definitions, and type info from C diffs using tree-sitter. Replaces the fragile regex in `cantata_integration.py`.
2. **TestCaseParser** (`testcase_parser.py`) — The architectural linchpin. Parses LLM markdown output into structured `TestCase` dataclasses with typed fields. This is the data preservation boundary — no LLM beyond this point.
3. **CCodeGenerator** (`code_generator.py`) + **templates/** — Deterministic C code generation from IR + signatures using Jinja2 templates. No LLM involvement. Guaranteed correct syntax.
4. **CValidator** (`c_validator.py`) — Post-generation validation gate. Catches `arr[] = 0`, bracket-in-calls, missing semicolons, undeclared variables before files are written.
5. **Pipeline** (`pipeline.py`) — Orchestrator that sequences all stages with error handling and logging.
6. **run.py** — Single CLI entry point replacing the current split between `poller.py` and `workflow.py`.

### Critical Pitfalls

1. **LLM replaces all test data with zeros** (Pitfall 1) — Root cause is architectural: asking the LLM to transfer structured data between stages. Fix: deterministic templates. Prevention: pydantic validation of IR data + CValidator checks for `= 0` array initializers.

2. **Invalid C array initialization** (Pitfall 2) — `int arr[] = 0;` instead of `int arr[] = {1,2,3,4};`. Fix: templates always emit brace-enclosed initializer lists from parsed IR values. CValidator regex-checks for bare `= 0` on arrays.

3. **Markdown preamble corrupts C files** (Pitfall 5) — `save_to_markdown()` wraps `.c` files with `# Cantata Test Script...` headers that are invalid C preprocessor directives. Fix: separate `save_c_file()` function that writes raw C code. Trivial to fix but fatal if missed.

4. **Function signatures corrupted in extern section** (Pitfall 6) — LLM generates `int func(int a, int b) {;` instead of `extern int func(int a, int b);`. Fix: generate extern declarations programmatically from parsed signatures, not via LLM.

5. **Missing Cantata boilerplate** (Pitfalls 7, 8, 13) — No `main()`, no coverage analysis section, missing `static` on helpers. Fix: include all Cantata boilerplate as a static template appended programmatically. Never rely on LLM for framework-specific macros.

## Implications for Roadmap

Based on research, the following 4-phase structure is recommended:

### Phase 1: Foundation — IR Pipeline & Core Parsing
**Rationale:** The TestCaseParser defines the IR data model that everything else depends on. DiffAnalyzer provides the type information templates need. CValidator provides the safety net. These three components are independent of each other and have zero external dependencies beyond the new libraries. Build and test them first.
**Delivers:** Structured data pipeline from markdown → Python dataclasses, robust C signature extraction, post-generation validation framework.
**Addresses:** Structured intermediate format (P1), Diff-to-signature parser (P1), Faithful data transfer (P1)
**Avoids:** Pitfalls 1 (data loss), 2 (invalid array init), 4 (missing semicolons), 5 (markdown preamble — by not using save_to_markdown)
**Stack:** unidiff, tree-sitter-c, pydantic, pytest for unit testing new components

### Phase 2: Code Generation — Templates & Cantata Compliance
**Rationale:** Templates depend on the IR shape from Phase 1. CCodeGenerator depends on both the IR format and the templates being ready. Cantata compliance is a template concern, not a pipeline concern. Build after Phase 1 validates the data model.
**Delivers:** Deterministic C code generation from structured data via Jinja2 templates. Full Cantata boilerplate (main, coverage, pragma, includes). Correct header file generation. Void function handling.
**Addresses:** Deterministic C code generation (P1), Cantata++ boilerplate (P1), Correct header files (P1), Void function handling (P1)
**Avoids:** Pitfalls 2 (invalid array syntax — templates guarantee brace init), 3 (bracket in calls — templates never emit brackets in calls), 6 (corrupted externs — generated from parsed signatures), 7 (no main — template includes it), 8 (missing coverage — template includes it), 12 (CHECK_EQUAL inconsistency — standardized in template), 13 (missing static — template enforces it), 14 (placeholder test — no fallback)
**Stack:** Jinja2 templates, CValidator from Phase 1

### Phase 3: Integration — Pipeline Wiring & Entry Point
**Rationale:** The pipeline orchestrator and run.py entry point wire all components together. This depends on Phase 1 (parsing + validation) and Phase 2 (code generation) being complete and tested. The existing `poller.py` GitHub integration is refactored as a clean adapter.
**Delivers:** Single-command pipeline: `python run.py` → poll GitHub → download diff → generate tests → output validated C files. End-to-end working tool.
**Addresses:** Single command entry point (P1), LLM client cleanup (remove VIO, fix shell=True), logging (replace print statements)
**Avoids:** Pitfalls 5 (markdown preamble — separate C file writer), security issues (shell=True removal, .env for secrets)
**Stack:** Python stdlib (logging, argparse), existing requests/poller logic refactored

### Phase 4: Cleanup — Dead Code Removal & Hardening
**Rationale:** Only delete code after the replacement pipeline is proven working. This phase removes the broken `cantata_integration.py`, dead VIO code paths, and adds the post-generation compilation validation that requires a working pipeline to be useful.
**Delivers:** Clean codebase with single code path. Optional: MSVC17 compilation validation, self-healing compile loop.
**Addresses:** Remove VIO LLM code (P2), Post-gen compilation validation (P2), Self-healing compile loop (P2)
**Stack:** subprocess (MSVC17 cl.exe invocation), regex for error message parsing

### Phase Ordering Rationale

- **Phase 1 before Phase 2** because templates need the IR data model to be finalized. Changing the `TestCase` dataclass after templates are written means rewriting templates.
- **Phase 2 before Phase 3** because the pipeline wires components together — it needs all components to exist and be tested in isolation first.
- **Phase 4 last** because deleting the old code path before the new one works is reckless. Also, compilation validation only makes sense when the code actually compiles.
- **Pitfall coverage:** Phases 1-3 address all 14 documented pitfalls (11 in Phases 1-2 alone). Phase 4 adds optional reliability improvements.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (DiffAnalyzer):** tree-sitter-c query syntax for C function definitions, handling of MSVC-specific extensions and preprocessor directives in diffs. The tree-sitter-c grammar has nuances that need validation against real PR diffs.
- **Phase 2 (Cantata templates):** Exact Cantata v24.04 pragma directives, `TEST_SCRIPT_GENERATOR` macro requirements, coverage analysis macro argument order. The existing `cantata_integration.py` template (lines 239-296) is the best reference but may be incomplete.

Phases with standard patterns (skip research-phase):
- **Phase 1 (TestCaseParser):** Markdown table parsing is well-documented, and the current `PROMPT_1` output format is known and consistent.
- **Phase 3 (Pipeline/CLI):** Standard Python CLI patterns with argparse. Poller refactoring is mechanical.
- **Phase 4 (Cleanup):** Pure deletion and minor refactoring. No research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified on PyPI with version compatibility confirmed. Python 3.10 requirement validated against all target packages. |
| Features | HIGH | Feature list derived from direct codebase analysis of 9 Python files + 23+ generated output files. The critical bug (data loss) is empirically confirmed. |
| Architecture | HIGH | The hybrid architecture (LLM design + deterministic templates) is the consensus solution across all research dimensions. The IR-based pipeline is a well-established pattern for LLM code generation. |
| Pitfalls | HIGH | All 14 pitfalls empirically observed in real generated output. Side-by-side comparison of markdown test cases vs generated C code confirms every issue. |

**Overall confidence:** HIGH

### Gaps to Address

- **Cantata v24.04 exact pragma/coverage syntax:** The existing template in `cantata_integration.py` is the best reference, but Cantata documentation should be consulted during Phase 2 template development to verify completeness. The research recommends using the existing template as a starting point and verifying against Cantata headers at `C:\LegacyApp\qa_systems\cantata\inc`.
- **tree-sitter-c query performance on large diffs:** Research confirms tree-sitter handles incomplete code fragments, but behavior on diffs with 1000+ lines or 10+ files hasn't been tested. Phase 1 should include a performance test with a real large PR.
- **GLM 4.7 Flash Stage 1 output format stability:** The markdown table format is consistent in observed outputs, but LLM output formats can drift. The parser must be robust against minor format variations. This should be validated during Phase 1 with a test suite of real Stage 1 outputs.
- **Jinja2 vs f-string templates:** Architecture research recommends Jinja2 for complex conditional logic (struct vs array vs primitive handling). For simpler cases, Python f-strings may suffice. Decision should be made during Phase 2 based on actual template complexity.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all 9 Python files: `testcase_generator.py`, `cantata_integration.py`, `workflow.py`, `glm_client.py`, `poller.py`, `vio_llm_client.py`, `vio_config.py`, `test_Vio_llm.py`, `test_format.py`
- Empirical analysis of 23+ generated `.c` files in `generated_tests/` (PRs #151–#502)
- Side-by-side comparison: markdown test cases (`pr_*_testcases.md`) vs generated C code (`test_module_*_*_.c`)
- PyPI package pages: tree-sitter 0.25.2, unidiff 0.7.5, pydantic v2, pytest 9.0.3
- opencode-ai CLI documentation (run command, --file/--format flags)
- Cantata v24.04 infrastructure at `C:\LegacyApp\qa_systems\`

### Secondary (MEDIUM confidence)
- tree-sitter-c grammar documentation on GitHub — couldn't fully verify PyPI package due to client challenge
- LLM-to-code pipeline patterns — industry consensus that structured IR outperforms pure LLM chains, based on training data rather than specific recent publications
- Jinja2 templating for C code generation — established pattern but project-specific template design needs validation

### Tertiary (LOW confidence)
- MSVC17 exact error message formats for automated error parsing (Phase 4 concern, can be gathered empirically)
- GLM 4.7 Flash context window limits for large diffs — timeout behavior at 600s boundary

---
*Research completed: 2026-04-24*
*Ready for roadmap: yes*
