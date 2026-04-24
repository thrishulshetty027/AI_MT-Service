# AI MT-Service (Cantata Test Generator)

## What This Is

A Python service that polls GitHub PRs for C code diffs and generates compilable Cantata unit test scripts using GLM 4.7 Flash via opencode CLI. Currently, the generated .c files fail to compile because the LLM-to-C code pipeline drops test data values and produces invalid syntax.

## Core Value

Generated Cantata .c test files must compile and execute in Cantata v24.04 (MSVC17) without manual fixes.

## Requirements

### Validated

- ✓ Poll GitHub PRs with labeled diffs — existing (poller.py)
- ✓ Download and store PR diffs — existing (poller.py)
- ✓ Generate test case definitions in markdown tables — existing (testcase_generator.py Stage 1)
- ✓ Support GLM 4.7 Flash via opencode CLI — existing (glm_client.py)
- ✓ Track processed PRs to avoid duplication — existing (processed_prs.json)

### Active

- [ ] Generated .c files compile without errors in Cantata v24.04 with MSVC17
- [ ] Array initializations use correct C syntax: `int arr[] = {1,2,3,4};` not `int arr[] = 0;`
- [ ] Function calls use correct syntax: `sumPositive(arr, size)` not `sumPositive(arr[], size)`
- [ ] Test data from markdown Stage 1 is faithfully transferred to C code Stage 2
- [ ] All variables declared before use with correct types matching diff signatures
- [ ] Struct-based functions handled with proper field initialization
- [ ] Void return functions validated via state checks, not assigned to variables
- [ ] Remove VIO LLM option — GLM 4.7 Flash via opencode only
- [ ] Cantata coverage rules (100% entry point + statement + call + decision) generated correctly
- [ ] Generated header files match actual function signatures from diff

### Out of Scope

- Web UI or REST API — manual CLI workflow is fine for now
- CI/CD integration — single user, manual trigger
- Multi-repo support beyond current polling — not needed yet
- Cantata Server integration (uploading results) — deferred
- Automatic PR comment posting — deferred

## Context

- Cantata v24.04 installed at `C:\LegacyApp\qa_systems\` with MSVC17 as default compiler
- Cantata Server running on WildFly at `localhost:8085` (available but not integrated)
- Floating license via `ls-cantata-lm-ww-1.int.automotive-wan.com`
- The service processes diffs from a C code project — functions like array operations, string handling, data structures
- Generated files follow naming: `test_module_{pr}_{pr}.c`, output log `.ctr`, coverage `.cov`
- Two-stage pipeline: Stage 1 (markdown test cases) works well; Stage 2 (C code generation) is broken — drops all test data values, produces `arr[] = 0` everywhere
- Example of the gap: PR #167 test cases markdown correctly says `arr={1,2,3,4}, size=4, expected=10` but generated C has `int arr[] = 0; int size = 0;` for every test

## Constraints

- **LLM**: GLM 4.7 Flash via opencode CLI only — no other models
- **Runtime**: opencode CLI subprocess calls, 600s timeout
- **Compiler target**: MSVC17 (cl.exe / link.exe), x86-Win32
- **Language**: Python 3.8+ for the service, C11/C++ for generated tests
- **Cantata headers**: `#include <cantpp.h>` resolves via `C:\LegacyApp\qa_systems\cantata\inc`
- **No Cantata GUI output**: `DCANTPP_OUTPUT_FOR_GUI` removed from config

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Fix Stage 2 C code generation first | Stage 1 markdown is correct; the breakdown is in converting to C | — Pending |
| GLM 4.7 Flash only | User requirement; no VIO LLM | — Pending |
| Keep manual CLI workflow | Single user, quality over process automation | — Pending |
| Target MSVC17 compiler | Matches Cantata config at `C:\LegacyApp\qa_systems\` | — Pending |

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
*Last updated: 2026-04-24 after initialization*
