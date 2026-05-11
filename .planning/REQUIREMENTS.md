# Requirements: AI MT-Service (Cantata Test Generator)

**Defined:** 2026-04-28
**Core Value:** Generated Cantata .c test files must compile with zero errors on first attempt 90%+ of the time. The other 10% must compile after the self-healing retry loop.

## v1 Requirements

Requirements for industrial-grade 13-LLM call pipeline with deterministic C code generation.

### Foundation (Phase 1)

- [ ] **FOUND-01**: Pydantic v2 models validate test case data structure (TestCaseFile, TestCase, FunctionMeta, StubConfig)
- [ ] **FOUND-02**: Diff validator rejects empty diffs, non-C diffs, and splits diffs > 300 lines by function boundary
- [ ] **FOUND-03**: Context assembler extracts function signatures, struct definitions, typedefs, macro constants, and HAL functions from headers
- [ ] **FOUND-04**: Type resolver maps C types to CType enum (UINT8, INT32, FLOAT, STRUCT, POINTER, ARRAY, BOOL)
- [ ] **FOUND-05**: Type resolver classifies parameters as scalar/struct/pointer/array/float/bool with correct zero/null values

### LLM Pipeline Infrastructure (Phase 2)

- [ ] **LLMP-01**: `_call_llm_focused()` executes single LLM calls with system prompt, user prompt, max_retries=2
- [ ] **LLMP-02**: LLM calls retry on empty response immediately
- [ ] **LLMP-03**: LLM calls retry on JSON parse error with "your output was not valid JSON, try again"
- [ ] **LLMP-04**: `run_multi_call_pipeline()` orchestrates all 13 calls with Stage 1 parallel, Stages 2-5 sequential
- [ ] **LLMP-05**: All intermediate outputs stored in PipelineState dataclass
- [ ] **LLMP-06**: Deterministic validators run between stages and reject invalid outputs

### Stage 1 Generator (Phase 3)

- [ ] **S1-01**: Call 1A (Code Analyst) describes what each function does in plain English
- [ ] **S1-02**: Call 1B (Type Inspector) builds complete JSON type map from signatures and struct definitions
- [ ] **S1-03**: Call 1C (Complexity Judge) classifies each function as TIER_1/2/3
- [ ] **S1-04**: Call 2A (MC/DC Scenario Planner) plans test scenarios by intent (no values)
- [ ] **S1-05**: Deterministic gap filler adds missing null_ptr and boundary scenarios
- [ ] **S1-06**: Call 2B (Scenario Critic) finds gaps in scenario list (missing branches, null tests, boundaries)
- [ ] **S1-07**: Call 2C (Scenario Finalizer) applies critique fixes and outputs clean final scenario list
- [ ] **S1-08**: Call 3A (Concrete Value Generator) assigns C values to all parameters with correct suffixes
- [ ] **S1-09**: Deterministic value sanitizer fixes suffixes, NULL_PTR, FALSE/TRUE
- [ ] **S1-10**: Call 3B (Value Critic) finds value errors (wrong suffixes, missing struct fields, vague expected_return)
- [ ] **S1-11**: Call 3C (Value Finalizer) applies value fixes and flags NEEDS_HUMAN cases
- [ ] **S1-12**: Call 4A (Stub Analyst) configures Cantata stubs per scenario
- [ ] **S1-13**: Call 4B (Stub Critic) verifies stub completeness and outputs final stub config
- [ ] **S1-14**: Call 5A (JSON Assembler) merges all stages into TestCaseFile JSON
- [ ] **S1-15**: Call 5B (Self-Review Auditor) checks 12-item checklist and fixes issues
- [ ] **S1-16**: `stage1_generator.py` produces testcases.md (human-readable) and testcases.json (Pydantic-validated)

### Jinja2 Templates (Phase 4)

- [ ] **TMPL-01**: All variable declarations appear before any executable statements (C89 requirement)
- [ ] **TMPL-02**: Function prototype style: `void func_name(void)` not `void func_name()`
- [ ] **TMPL-03**: Extern declarations strip everything from `{` onward, add `extern` keyword, end with `;`
- [ ] **TMPL-04**: Boolean values use FALSE and TRUE (never false, true, 0, 1 for BOOL)
- [ ] **TMPL-05**: Null pointers use NULL_PTR (never NULL or 0)
- [ ] **TMPL-06**: OPEN_LOG second arg: FALSE (not false — C89 has no bool)
- [ ] **TMPL-07**: Cantata assertion macros: CHECK_INT(expected, actual), CHECK_DOUBLE, CHECK_N_CALLS, INITIALISE_STUB_RETURN, INITIALISE_STUB_POINTER_PARAM
- [ ] **TMPL-08**: math.h included ONLY when float/double tests are present
- [ ] **TMPL-09**: All comments use `/* */` style only. No `//` comments
- [ ] **TMPL-10**: Struct initialization is field-by-field after declaration, not aggregate init
- [ ] **TMPL-11**: Array test pattern: `uint8 arr[] = {1u, 2u, 3u}; uint16 arr_size = 3u; result = func(arr, arr_size);`
- [ ] **TMPL-12**: All 8 partials work correctly (scalar, struct, pointer, array, float, multi-param, void-return, stub setup)
- [ ] **TMPL-13**: Master templates generate complete Cantata test scripts with main(), coverage rules, OPEN_LOG/START_SCRIPT/END_SCRIPT

### Stage 2 Generator (Phase 5)

- [ ] **S2-01**: `stage2_generator.py` loads testcases.json and validates schema
- [ ] **S2-02**: Type resolver maps every param to CType enum using type_map from JSON
- [ ] **S2-03**: Template selector chooses correct Jinja2 partial per test case
- [ ] **S2-04**: Jinja2 renderer produces .c and .h files with C89 compliance
- [ ] **S2-05**: cppcheck runs before compiler and catches obvious issues
- [ ] **S2-06**: Compile validator attempts MSVC17 compilation with `/Za /nologo /W3 /c`
- [ ] **S2-07**: Compile validator maps MSVC error codes to IR fixes (C2039, C2065, C2143, C4013, C2440, C2106)
- [ ] **S2-08**: Compile validator regenerates C code from fixed IR and retries up to 3 times
- [ ] **S2-09**: Compile report shows errors resolved, attempts used, and escalates when self-healing fails

### Integration & Quality Gates (Phase 6)

- [ ] **INTG-01**: `run.py --diff path/to/diff.txt --pr 167` executes full pipeline
- [ ] **INTG-02**: `run.py --repo owner/repo --pr 167` fetches diff from GitHub and executes full pipeline
- [ ] **INTG-03**: `run.py --stage2-only generated_tests/pr_167_testcases.json` regenerates .c from existing JSON
- [ ] **INTG-04**: `run.py --stage1-only --diff path/to/diff.txt --pr 167` produces testcases.md + .json, stops before C gen
- [ ] **INTG-05**: REQUIRE_HUMAN_APPROVAL env var pauses after Stage 1 for engineer review
- [ ] **INTG-06**: Quality gates generate ISO 26262 traceability sidecar (trace_PR.json)
- [ ] **INTG-07**: E2E test 1: simple function compiles with zero errors
- [ ] **INTG-08**: E2E test 2: struct function compiles with zero errors (no C2039 errors)
- [ ] **INTG-09**: E2E test 3: stage2-only regenerates .c file after JSON is hand-edited

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Features

- **ADVN-01**: Post-generation MSVC17 compilation validation
- **ADVN-02**: Branch-aware test generation
- **ADVN-03**: Struct designated initializer generation
- **ADVN-04**: Cantata Server result upload
- **ADVN-05**: Automatic PR comment posting

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web UI or REST API | CLI is sufficient for current use case |
| CI/CD integration | Single user, manual trigger |
| Multi-repo support beyond current polling | Not needed yet |
| Cantata Server integration (uploading results) | Deferred to v2 |
| Automatic PR comment posting | Deferred to v2 |
| Test execution | Only test file generation in scope |
| Dynamic code analysis | Static analysis only (cppcheck) |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Pending |
| FOUND-02 | Phase 1 | Pending |
| FOUND-03 | Phase 1 | Pending |
| FOUND-04 | Phase 1 | Pending |
| FOUND-05 | Phase 1 | Pending |
| LLMP-01 | Phase 2 | Pending |
| LLMP-02 | Phase 2 | Pending |
| LLMP-03 | Phase 2 | Pending |
| LLMP-04 | Phase 2 | Pending |
| LLMP-05 | Phase 2 | Pending |
| LLMP-06 | Phase 2 | Pending |
| S1-01 | Phase 3 | Pending |
| S1-02 | Phase 3 | Pending |
| S1-03 | Phase 3 | Pending |
| S1-04 | Phase 3 | Pending |
| S1-05 | Phase 3 | Pending |
| S1-06 | Phase 3 | Pending |
| S1-07 | Phase 3 | Pending |
| S1-08 | Phase 3 | Pending |
| S1-09 | Phase 3 | Pending |
| S1-10 | Phase 3 | Pending |
| S1-11 | Phase 3 | Pending |
| S1-12 | Phase 3 | Pending |
| S1-13 | Phase 3 | Pending |
| S1-14 | Phase 3 | Pending |
| S1-15 | Phase 3 | Pending |
| S1-16 | Phase 3 | Pending |
| TMPL-01 | Phase 4 | Pending |
| TMPL-02 | Phase 4 | Pending |
| TMPL-03 | Phase 4 | Pending |
| TMPL-04 | Phase 4 | Pending |
| TMPL-05 | Phase 4 | Pending |
| TMPL-06 | Phase 4 | Pending |
| TMPL-07 | Phase 4 | Pending |
| TMPL-08 | Phase 4 | Pending |
| TMPL-09 | Phase 4 | Pending |
| TMPL-10 | Phase 4 | Pending |
| TMPL-11 | Phase 4 | Pending |
| TMPL-12 | Phase 4 | Pending |
| TMPL-13 | Phase 4 | Pending |
| S2-01 | Phase 5 | Pending |
| S2-02 | Phase 5 | Pending |
| S2-03 | Phase 5 | Pending |
| S2-04 | Phase 5 | Pending |
| S2-05 | Phase 5 | Pending |
| S2-06 | Phase 5 | Pending |
| S2-07 | Phase 5 | Pending |
| S2-08 | Phase 5 | Pending |
| S2-09 | Phase 5 | Pending |
| INTG-01 | Phase 6 | Pending |
| INTG-02 | Phase 6 | Pending |
| INTG-03 | Phase 6 | Pending |
| INTG-04 | Phase 6 | Pending |
| INTG-05 | Phase 6 | Pending |
| INTG-06 | Phase 6 | Pending |
| INTG-07 | Phase 6 | Pending |
| INTG-08 | Phase 6 | Pending |
| INTG-09 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 57 total
- Mapped to phases: 57
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-28*
*Last updated: 2026-04-28 after rebuild from Tasks.md*
