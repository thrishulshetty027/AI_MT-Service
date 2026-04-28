# AI MT-Service — Project Guide

## Project

Industrial-grade Python pipeline that generates 100% compilable Cantata v24.04 C89 test files from GitHub PR diffs containing automotive C code. Uses a 13-call GLM 4.7 Flash pipeline for intelligent test case design, followed by deterministic Jinja2 templates for code generation with MSVC17 compile validation and self-healing.

## Core Value

Generated Cantata .c test files must compile with zero errors on first attempt 90%+ of the time. The other 10% must compile after the self-healing retry loop.

## Current State

- **Phase**: Ready to start Phase 1 (Foundation)
- **Status**: Project rebuilt from Tasks.md specification (2026-04-28)
- **Key files**: `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`

## Architecture Decision

The system uses a 13-LLM call pipeline (Stage 1) for intelligent test case design, followed by deterministic Jinja2 templates (Stage 6) for code generation. Each LLM call has ONE focused job to improve quality and debuggability. C code generation is zero-LLM to eliminate syntax errors and enable self-healing via compile error-to-IR fix mapping.

## Constraints

- **LLM**: GLM 4.7 Flash via opencode CLI only
- **Target compiler**: MSVC17 (cl.exe / link.exe) with /Za flag for strict C89
- **Python**: 3.10+ required (tree-sitter, pydantic v2, pytest 9.x)
- **Cantata v24.04**: at `C:\LegacyApp\qa_systems\`
- **Standard**: ISO 26262 ASIL-B automotive safety-critical software

## Commands

- `/gsd-plan-phase 1` — Plan Phase 1 (Foundation)
- `/gsd-plan-phase 2` — Plan Phase 2 (LLM Pipeline Infrastructure)
- `/gsd-plan-phase 3` — Plan Phase 3 (Stage 1 Generator)
- `/gsd-plan-phase 4` — Plan Phase 4 (Jinja2 Templates)
- `/gsd-plan-phase 5` — Plan Phase 5 (Stage 2 Generator)
- `/gsd-plan-phase 6` — Plan Phase 6 (Integration & Quality Gates)
- `/gsd-settings` — Update project preferences
- `/gsd-progress` — View current status

## File Structure (To Be Built)

```
src/
  schemas.py              — Pydantic v2 models for TestCaseFile
  diff_validator.py       — Diff validation and chunking
  context_assembler.py    — Header/struct/typedef/HAL context assembly
  stage1_generator.py     — 13-call LLM pipeline → testcases.md + .json
  stage2_generator.py     — testcases.json → .c + .h (zero LLM)
  multi_call_pipeline.py  — All 13 LLM calls with retry logic
  type_resolver.py        — Deterministic C type classification
  compile_validator.py    — MSVC17 compile + error-to-IR fix loop
  quality_gates.py        — cppcheck, traceability sidecar
  scenario_validator.py   — Deterministic scenario gap checker
  value_sanitizer.py      — Deterministic value suffix fixer

templates/
  cantata_test.c.j2       — Master test script template
  cantata_header.h.j2     — Header file template
  partials/
    _scalar_test.c.j2
    _struct_test.c.j2
    _pointer_test.c.j2
    _array_test.c.j2
    _float_test.c.j2
    _multi_param_test.c.j2
    _void_return_test.c.j2
    _stub_setup.c.j2
    _coverage_rules.c.j2
    _main.c.j2

run.py                    — Unified entry point

generated_tests/
  pr_{N}_testcases.md         Engineer-readable test case document
  pr_{N}_testcases.json       Machine-readable validated TestCaseFile
  test_module_{N}_{N}.c       Cantata test script (C89 compilable)
  module_{N}.h                Header with extern declarations
  compile_report_{N}.json     Compile result, errors, attempts used
  trace_{N}.json              ISO 26262 traceability sidecar
  human_review_{N}.md         Only written if NEEDS_HUMAN cases exist
```

## Build Order (Per Tasks.md)

1. **src/schemas.py** — Pydantic v2 models
2. **src/diff_validator.py** — Diff validation and chunking
3. **src/context_assembler.py** — Header/struct/typedef/HAL context assembly
4. **src/type_resolver.py** — Deterministic C type classification
5. **src/multi_call_pipeline.py** — LLM calls with retry logic
6. **src/scenario_validator.py + src/value_sanitizer.py** — Deterministic validators
7. **src/stage1_generator.py** — 13 LLM calls with markdown/JSON output
8. **templates/** — All Jinja2 templates (master + partials)
9. **src/stage2_generator.py** — C code generation via templates
10. **src/compile_validator.py** — MSVC17 compile with self-healing
11. **src/quality_gates.py** — cppcheck, traceability
12. **run.py** — Unified entry points

## Success Criteria

The pipeline is complete when:
1. `python run.py --diff tests/sample_add.diff --pr TEST01` produces compilable test_module_TEST01_TEST01.c
2. `python run.py --diff tests/sample_struct.diff --pr TEST02` produces compilable .c with no C2039 errors
3. `python run.py --stage2-only generated_tests/pr_TEST01_testcases.json` regenerates .c after hand-edited JSON
4. testcases.md is human-readable, accurate, and includes engineer review checklist

## Existing Files (Do Not Modify)

- `poller.py` — GitHub PR polling
- `glm_client.py` — GLM 4.7 Flash integration
- `processed_prs.json` — Tracks processed PRs

Integrate with these as-is; do not modify them.
