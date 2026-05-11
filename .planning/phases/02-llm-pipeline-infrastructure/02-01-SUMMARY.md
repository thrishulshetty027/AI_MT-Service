# Phase 2: LLM Pipeline Infrastructure - Planning Summary

**Planned:** 2026-04-30
**Status:** Ready to execute

## Planning Overview

Phase 2 planning is complete. Created 1 plan (02-01-PLAN.md) for building the orchestration infrastructure that manages 13 LLM calls with retry logic and parallel execution.

## Plan Details

### Plan 02-01: Multi-call Pipeline Orchestration + Retry Logic

**Objective:** Build the orchestration layer that manages 13 LLM calls with retry logic and parallel execution where possible.

**Type:** execute
**Wave:** 1
**Autonomous:** yes

**Files Modified:**
- `src/multi_call_pipeline.py` — Orchestration layer
- `tests/test_multi_call_pipeline.py` — Comprehensive tests

**Requirements Covered:**
- LLMP-01: `_call_llm_focused()` with system prompt, user prompt, max_retries=2
- LLMP-02: Retry on empty response immediately
- LLMP-03: Retry on JSON parse error with specific message
- LLMP-04: `run_multi_call_pipeline()` orchestrates all 13 calls: Stage 1 (parallel), Stages 2-5 (sequential)
- LLMP-05: All intermediate outputs stored in PipelineState dataclass
- LLMP-06: Deterministic validators run between stages and reject invalid outputs

**Tasks:**
1. Create src/multi_call_pipeline.py with PipelineState dataclass
2. Implement _call_llm_focused() with retry logic
3. Implement run_multi_call_pipeline() with Stage 1 parallel execution
4. Create comprehensive tests for multi_call_pipeline.py

**Key Implementation Decisions:**

1. **PipelineState Dataclass:**
   - Contains all 13 stage outputs (stage1a_output through stage5b_output)
   - Includes input fields (diff_text, pr_number, module_name)
   - Includes final outputs (testcases_json, testcases_md)
   - Uses Python 3.10+ dataclass with type hints

2. **_call_llm_focused() Function:**
   - Wraps existing `call_glm_4_7_flash()` from glm_client.py
   - Combines system and user prompts into single string (required by glm_client.py)
   - Implements retry on empty response (LLMP-02)
   - Implements retry on JSON parse error with specific message (LLMP-03)
   - Includes `_extract_json()` helper to handle markdown code blocks
   - Raises RuntimeError after all retries exhausted
   - Logs warnings for retry attempts

3. **run_multi_call_pipeline() Function:**
   - Stage 1 (1A, 1B, 1C) executes in parallel using ThreadPoolExecutor
   - Stages 2-5 execute sequentially (placeholders in this phase)
   - Collects results dict first, then assigns to state (avoids race conditions)
   - Includes timeout on futures (660s, slightly longer than LLM timeout)
   - Cancels remaining futures if one fails
   - Includes placeholders for deterministic validators (LLMP-06)
   - Accepts context_package parameter from Phase 1

4. **Test Coverage:**
   - Tests for retry logic (empty response, JSON parse error)
   - Tests for RuntimeError after all retries exhausted
   - Tests for Stage 1 parallel execution
   - Tests for PipelineState dataclass
   - Tests for error handling and context_package acceptance
   - Tests for JSON extraction from markdown code blocks

**Integration Points:**
- Uses existing `call_glm_4_7_flash()` from `glm_client.py` (DO NOT MODIFY)
- Uses `TestCaseFile` from `src/schemas.py` (from Phase 1)
- Accepts `ContextPackage` from `src/context_assembler.py` (from Phase 1)

**Research Alignment:**
The plan aligns with the existing Phase 2 RESEARCH.md:
- Uses ThreadPoolExecutor for Stage 1 parallel execution
- Implements stage-level validation hooks (placeholders)
- Handles JSON extraction from markdown code blocks
- Follows the research's integration contract with glm_client.py

**Threat Model:**
- T-02-01: Spoofing — Validate pr_number and module_name
- T-02-02: Tampering — Validate diff_text (already in Phase 1 diff_validator)
- T-02-03: Repudiation — Logging provides audit trail
- T-02-04: Information Disclosure — Validate LLM responses don't leak secrets
- T-02-05: Denial of Service — Max retries=2, timeout on futures
- T-02-06: Elevation of Privilege — Not applicable (CLI tool, no auth)

## Success Criteria

- [ ] src/multi_call_pipeline.py contains PipelineState dataclass with all 13 stage outputs
- [ ] _call_llm_focused() executes single LLM calls with max_retries=2
- [ ] _call_llm_focused() retries on empty response immediately (LLMP-02)
- [ ] _call_llm_focused() retries on JSON parse error with specific message (LLMP-03)
- [ ] run_multi_call_pipeline() orchestrates all 13 calls
- [ ] Stage 1 (1A, 1B, 1C) executes in parallel using ThreadPoolExecutor (LLMP-04)
- [ ] Stages 2-5 execute sequentially (LLMP-04)
- [ ] All intermediate outputs stored in PipelineState (LLMP-05)
- [ ] Deterministic validator placeholders between stages (LLMP-06)
- [ ] Error handling raises RuntimeError on failures
- [ ] Logging of retry attempts and stage progression
- [ ] tests/test_multi_call_pipeline.py created with comprehensive coverage
- [ ] All tests pass (pytest tests/test_multi_call_pipeline.py — 100% pass rate)
- [ ] Coverage > 80% for multi_call_pipeline.py

## Next Steps

Execute Phase 2:
```
/gsd-execute-phase 2
```

After Phase 2 completes, the pipeline infrastructure will be ready. Phase 3 will implement the 13 LLM prompts and deterministic validators for Stage 1 Generator.

---

*Planning complete: 2026-04-30*
*Plan file: .planning/phases/02-llm-pipeline-infrastructure/02-01-PLAN.md*
*Research: .planning/phases/02-llm-pipeline-infrastructure/02-RESEARCH.md*
