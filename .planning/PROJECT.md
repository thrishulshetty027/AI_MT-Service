# AI MT-Service (Cantata Test Generator)

## What This Is

A Python service that generates 100% compilable Cantata v24.04 C89 test files from GitHub PR diffs containing automotive C code. Uses a 13-call GLM 4.7 Flash pipeline for intelligent test case design, followed by deterministic Jinja2 templates for code generation with MSVC17 compile validation and self-healing.

## Core Value

Generated Cantata .c test files must compile with zero errors on first attempt 90%+ of the time. The other 10% must compile after the self-healing retry loop.

## Requirements

### Validated

- ✓ Poll GitHub PRs with labeled diffs — existing (poller.py)
- ✓ GLM 4.7 Flash via opencode CLI integration — existing (glm_client.py)
- ✓ Track processed PRs to avoid duplication — existing (processed_prs.json)

### Active

- [ ] Complete 13-LLM call pipeline for intelligent test case design (Stage 1)
- [ ] Deterministic C code generation via Jinja2 templates (Stage 6)
- [ ] Pydantic v2 schema validation for all test case data
- [ ] tree-sitter-based C function signature extraction
- [ ] MSVC17 compile validation with error-to-IR fix mapping
- [ ] cppcheck static analysis integration
- [ ] ISO 26262 traceability sidecar generation
- [ ] Multiple entry points: full pipeline, Stage 1 only, Stage 2 only
- [ ] Human approval workflow (REQUIRE_HUMAN_APPROVAL env var)
- [ ] Comprehensive output: testcases.md, testcases.json, .c, .h, compile_report.json, trace.json
- [ ] C89 compliance in all generated code (all declarations before statements, FALSE/TRUE, NULL_PTR)
- [ ] Stub configuration for HAL/RTE functions with Cantata syntax
- [ ] MC/DC coverage planning for ASIL-B compliance
- [ ] Self-healing compile retry loop (up to 3 attempts)

### Out of Scope

- Web UI or REST API — CLI only
- CI/CD integration — single user, manual trigger
- Multi-repo support beyond current polling
- Cantata Server integration (uploading results)
- Automatic PR comment posting
- Test execution — only test file generation
- Dynamic code analysis — static analysis only

## Context

- **Target Compiler**: MSVC17 (cl.exe) with /Za flag for strict C89 compliance
- **Cantata Version**: v24.04 installed at `C:\LegacyApp\qa_systems\`
- **Language**: Python 3.10+ required (tree-sitter, pydantic v2, pytest 9.x)
- **LLM Backend**: GLM 4.7 Flash via opencode CLI only
- **Standard**: ISO 26262 ASIL-B automotive safety-critical software
- **Generated Files**: Follow naming `test_module_{PR}_{PR}.c`, `module_{PR}.h`, `pr_{PR}_testcases.json`, `pr_{PR}_testcases.md`

## Constraints

- **LLM**: GLM 4.7 Flash via opencode CLI only — no other models
- **Runtime**: Python 3.10+, subprocess calls for external tools (cl.exe, cppcheck)
- **Compiler Target**: MSVC17 (cl.exe / link.exe), x86-Win32, strict C89
- **Generated Code**: C89 only — no C++ features, no // comments, all declarations first
- **Cantata Headers**: `#include <cantpp.h>` resolves via `C:\LegacyApp\qa_systems\cantata\inc`
- **Dependencies**: pydantic>=2.0, jinja2>=3.1, tree-sitter>=0.20, tree-sitter-c>=0.20, cppcheck
- **Architecture**: 13-LLM call pipeline (Stage 1) + deterministic generation (Stage 6)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 13-LLM call pipeline | Each call has ONE focused job — improves quality and debuggability | — Pending |
| Deterministic Stage 6 | Zero LLM for code gen eliminates syntax errors, enables self-healing | — Pending |
| Pydantic v2 schemas | Strict type validation catches data errors before C generation | — Pending |
| Jinja2 partials | Reusable templates for scalar, struct, pointer, array, float tests | — Pending |
| MSVC17 error mapping | Compile errors → IR fixes → regenerate → retry up to 3 times | — Pending |
| Human approval workflow | Engineer reviews testcases.md before C generation (opt-in) | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-28 after rebuild from Tasks.md specification*
