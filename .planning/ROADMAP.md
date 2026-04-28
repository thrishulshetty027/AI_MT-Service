# Roadmap: AI MT-Service (Cantata Test Generator)

## Overview

This roadmap builds a complete industrial-grade Python pipeline that generates 100% compilable Cantata v24.04 C89 test files from GitHub PR diffs. The architecture consists of a 13-call GLM 4.7 Flash pipeline for intelligent test case design (Stage 1), followed by deterministic Jinja2 templates for code generation (Stage 6) with MSVC17 compile validation and self-healing.

## Phases

- [ ] **Phase 1: Foundation** — Pydantic schemas, diff validation, context assembly, type resolution
- [ ] **Phase 2: LLM Pipeline Infrastructure** — Multi-call orchestration with retry logic
- [ ] **Phase 3: Stage 1 Generator** — 13 LLM calls with deterministic validators
- [ ] **Phase 4: Jinja2 Templates** — C89-compliant templates with partials
- [ ] **Phase 5: Stage 2 Generator** — C code generation, cppcheck, compile validator
- [ ] **Phase 6: Integration & Quality Gates** — run.py entry points, traceability, E2E testing

## Phase Details

### Phase 1: Foundation
**Goal**: Build the data structures and context extraction infrastructure that the entire pipeline depends on.
**Depends on**: Nothing (first phase)
**Requirements**: QUAL-09, QUAL-05, INTG-03, INTG-04
**Success Criteria** (what must be TRUE):
  1. Pydantic v2 models validate test case data structure and catch schema violations
  2. Diff validator rejects empty/non-C diffs and splits large diffs by function boundary
  3. Context assembler extracts function signatures, struct definitions, typedefs, macros, and HAL functions from headers
  4. Type resolver maps C types to CType enum and classifies parameters (scalar/struct/pointer/array/float/bool)
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md — Pydantic schemas + diff validator
- [ ] 01-02-PLAN.md — Context assembler + type resolver

### Phase 2: LLM Pipeline Infrastructure
**Goal**: Build the orchestration layer that manages 13 LLM calls with retry logic and parallel execution where possible.
**Depends on**: Phase 1
**Requirements**: LLMP-01, LLMP-02, LLMP-03, LLMP-04, LLMP-05, LLMP-06
**Success Criteria** (what must be TRUE):
  1. `_call_llm_focused()` executes single LLM calls with retry on empty response or JSON parse errors
  2. `run_multi_call_pipeline()` orchestrates all 13 calls: Stage 1 (parallel), Stages 2-5 (sequential)
  3. All intermediate outputs are stored in PipelineState dataclass
  4. Deterministic validators run between stages and reject invalid outputs
**Plans**: 1 plan

Plans:
- [ ] 02-01-PLAN.md — Multi-call pipeline orchestration + retry logic

### Phase 3: Stage 1 Generator
**Goal**: Implement the 13-LLM call pipeline with all prompts, deterministic validators, and markdown/JSON output generation.
**Depends on**: Phase 1, Phase 2
**Requirements**: QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-06, QUAL-07, QUAL-08, QUAL-10, QUAL-11
**Success Criteria** (what must be TRUE):
  1. All 13 LLM prompts are implemented (1A-1C, 2A-2C, 3A-3C, 4A-4B, 5A-5B)
  2. Stage 1 calls (1A, 1B, 1C) execute in parallel using ThreadPoolExecutor
  3. Deterministic validators check: scenario gaps, value suffixes, struct fields, expected returns
  4. `stage1_generator.py` produces testcases.md (human-readable) and testcases.json (Pydantic-validated)
**Plans**: 2 plans

Plans:
- [ ] 03-01-PLAN.md — LLM prompts + deterministic validators (Calls 1A-1C, 2A-2C, 3A-3C)
- [ ] 03-02-PLAN.md — Stub configuration + JSON assembly + self-review (Calls 4A-4B, 5A-5B)

### Phase 4: Jinja2 Templates
**Goal**: Create C89-compliant Jinja2 templates that generate compilable Cantata test scripts.
**Depends on**: Phase 1 (for CType classification)
**Requirements**: QUAL-01, QUAL-02, QUAL-03, QUAL-06, QUAL-07, QUAL-08
**Success Criteria** (what must be TRUE):
  1. All variable declarations appear before any executable statements (C89 requirement)
  2. Boolean values use FALSE/TRUE, null pointers use NULL_PTR
  3. Struct initialization is field-by-field (not aggregate)
  4. All 8 partials work correctly: scalar, struct, pointer, array, float, multi-param, void-return, stub setup
  5. Master templates generate complete Cantata test scripts with main(), coverage rules, OPEN_LOG/START_SCRIPT/END_SCRIPT
**Plans**: 1 plan

Plans:
- [ ] 04-01-PLAN.md — All Jinja2 templates (master + partials)

### Phase 5: Stage 2 Generator
**Goal**: Implement deterministic C code generation, cppcheck static analysis, and MSVC17 compile validation with self-healing.
**Depends on**: Phase 1, Phase 4
**Requirements**: QUAL-10, QUAL-11, HEAL-02, HEAL-03
**Success Criteria** (what must be TRUE):
  1. `stage2_generator.py` loads testcases.json, validates schema, resolves types, selects templates, renders .c and .h
  2. cppcheck runs before compiler and catches obvious issues (undeclared vars, wrong types)
  3. Compile validator attempts MSVC17 compilation, maps error codes to IR fixes, regenerates, retries up to 3 times
  4. Compile report shows errors resolved, attempts used, and escalates when self-healing fails
**Plans**: 2 plans

Plans:
- [ ] 05-01-PLAN.md — Stage 2 generator (JSON → C code via templates)
- [ ] 05-02-PLAN.md — cppcheck integration + compile validator with error-to-IR fix mapping

### Phase 6: Integration & Quality Gates
**Goal**: Create unified entry points, ISO 26262 traceability, and end-to-end testing.
**Depends on**: Phase 2, Phase 3, Phase 5
**Requirements**: INTG-01, INTG-02
**Success Criteria** (what must be TRUE):
  1. `run.py` provides 4 entry points: full pipeline, --repo/--pr, --stage2-only, --stage1-only
  2. REQUIRE_HUMAN_APPROVAL env var pauses after Stage 1 for engineer review
  3. Quality gates generate ISO 26262 traceability sidecar (trace_PR.json)
  4. E2E tests verify: simple function compiles, struct function compiles, stage2-only regenerates correctly
**Plans**: 2 plans

Plans:
- [ ] 06-01-PLAN.md — run.py entry points + human approval workflow
- [ ] 06-02-PLAN.md — Quality gates + traceability + E2E testing

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/2 | Ready to plan | - |
| 2. LLM Pipeline Infrastructure | 0/1 | Ready to execute | - |
| 3. Stage 1 Generator | 0/2 | Not started | - |
| 4. Jinja2 Templates | 0/1 | Not started | - |
| 5. Stage 2 Generator | 0/2 | Not started | - |
| 6. Integration & Quality Gates | 0/2 | Not started | - |

## Requirements Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| QUAL-01: Pydantic schema validation | Phase 1 | Pending |
| QUAL-02: C89 compliance in generated code | Phase 4 | Pending |
| QUAL-03: Correct C literal suffixes (u, f) | Phase 4 | Pending |
| QUAL-04: FALSE/TRUE not false/true | Phase 4 | Pending |
| QUAL-05: NULL_PTR not NULL | Phase 4 | Pending |
| QUAL-06: Struct field-by-field initialization | Phase 4 | Pending |
| QUAL-07: All declarations before statements | Phase 4 | Pending |
| QUAL-08: Cantata macros used correctly | Phase 4 | Pending |
| QUAL-09: Function signatures extracted correctly | Phase 1 | Pending |
| QUAL-10: cppcheck static analysis | Phase 5 | Pending |
| QUAL-11: MSVC17 compile validation | Phase 5 | Pending |
| INTG-01: Unified entry point (run.py) | Phase 6 | Pending |
| INTG-02: Multiple entry points (full, stage1-only, stage2-only) | Phase 6 | Pending |
| INTG-03: Context assembly from headers | Phase 1 | Pending |
| INTG-04: Type resolution and classification | Phase 1 | Pending |
| HEAL-01: LLM retry logic on failures | Phase 2 | Pending |
| HEAL-02: Compile error → IR fix mapping | Phase 5 | Pending |
| HEAL-03: Self-healing compile retry loop (3 attempts) | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓
