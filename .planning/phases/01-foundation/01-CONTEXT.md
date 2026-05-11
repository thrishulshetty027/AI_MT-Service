# Phase 1: Foundation - Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

## Phase Boundary

Build the data structures and context extraction infrastructure that the entire 13-LLM call pipeline depends on. This phase establishes the foundation that Stages 1-6 will consume. No test generation happens here — only data contracts, validation, and context assembly.

## Implementation Decisions

### Existing Code Strategy
- **D-01:** Archive existing src/ files to src/legacy/ and rebuild from Tasks.md specification
- **D-02:** Do not attempt to adapt or refactor existing Pydantic v1 code — fresh start ensures alignment with 13-call pipeline architecture
- **D-03:** Keep existing files for reference but they are not part of the new pipeline

### Pydantic v2 Schema Structure
- **D-04:** Follow Tasks.md schema exactly — no deviations, no adaptations
- **D-05:** Implement all required models: TestType enum, StubConfig, TestCase, FunctionMeta, TestCaseFile
- **D-06:** Include all validators specified (e.g., reject vague expected_return values)
- **D-07:** Implement validate_internal_consistency() method on TestCaseFile

### Context Assembler Scope
- **D-08:** Extract context from diff only — no external header file scanning
- **D-09:** Struct definitions: extract only if they appear in the diff's AST
- **D-10:** Typedef resolutions: parse typedef statements from diff, build alias map
- **D-11:** Macro constants: extract #define statements from diff
- **D-12:** HAL functions: detect via function calls in diff's AST (prefixes: HAL_, Rte_, Com_)
- **D-13:** Existing patterns: NOT implemented in Phase 1 (deferred to future phase)

### Type Classification System
- **D-14:** Comprehensive type mapping — all C standard types, all AUTOSAR types
- **D-15:** Implement CType enum: UINT8, UINT16, UINT32, INT8, INT16, INT32, FLOAT, DOUBLE, STRUCT, POINTER, ARRAY, BOOL, VOID, UNKNOWN
- **D-16:** Recursively resolve typedef chains (MyType → uint8_t → UINT8)
- **D-17:** Classify parameters as scalar/struct/pointer/array/float/bool
- **D-18:** Determine correct zero value per type (0u for uint, 0.0f for float, FALSE for bool, NULL_PTR for pointers)
- **D-19:** Determine correct null value per type (NULL_PTR for pointers, N/A for scalars)
- **D-20:** Handle const qualifiers, function pointers, and complex types

## Specific Ideas

- "Tasks.md is the source of truth for the entire architecture — follow it exactly"
- "We're building a 13-LLM call pipeline, so the Pydantic schema must match what Call 5A expects"
- "Type resolution needs to handle automotive AUTOSAR codebases with deep typedef hierarchies"
- "Context extraction from diff only keeps Phase 1 self-contained — no external dependencies"

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture Specification
- `C:\Users\uik03287\Downloads\Tasks.md` — Complete 13-LLM call pipeline specification, Pydantic v2 schema, C89 template rules, compile error mapping

### Project Context
- `.planning/PROJECT.md` — Project constraints (Python 3.10+, GLM 4.7 Flash only, MSVC17 target)
- `.planning/REQUIREMENTS.md` — Phase 1 requirements: FOUND-01 through FOUND-05
- `.planning/ROADMAP.md` — Phase 1 details, success criteria, requirements traceability

### Code Reference (Legacy Only)
- `src/legacy/ir_models.py` — Previous Pydantic v1 models (NOT to be used, reference only for understanding what was tried)
- `src/legacy/signature_extractor.py` — Previous tree-sitter extraction (NOT to be used, reference only)
- `src/legacy/type_resolver.py` — Previous type resolution (NOT to be used, reference only)

No external specs — requirements are fully captured in Tasks.md and project docs.

## Existing Code Insights

### Reusable Assets
- None (all existing code archived to legacy/)

### Established Patterns
- None (fresh start per decision D-01)

### Integration Points
- `poller.py` — Existing GitHub PR polling (do not modify, integrate as-is)
- `glm_client.py` — Existing GLM 4.7 Flash integration (do not modify, integrate as-is)
- `processed_prs.json` — Existing PR tracking (do not modify, integrate as-is)

## Deferred Ideas

- **Existing pattern loading** — "Load most similar existing test as style reference" — deferred to future phase (requires test database)
- **Context from external headers** — Header file scanning for typedefs/macros — deferred to future phase if diff-only proves insufficient
- **Struct field validation against project headers** — Currently struct fields extracted from diff only — deferred if C2039 errors become common

## the agent's Discretion

### File Structure
- Exact file names from Tasks.md: `schemas.py`, `diff_validator.py`, `context_assembler.py`, `type_resolver.py`
- Module organization within each file (classes, functions) is at agent's discretion
- Test file naming and organization follows standard pytest conventions

### Implementation Details
- Exact AST query syntax for tree-sitter is at agent's discretion (must work correctly)
- Error message phrasing and format is at agent's discretion (must be clear)
- Type resolution algorithm for recursive typedef chains is at agent's discretion (must be correct)
- Diff chunking strategy for >300 line diffs is at agent's discretion (must be by function boundary)

### Trade-offs
- Performance vs. completeness in type resolution: agent should favor correctness over speed
- Memory usage vs. simplicity in diff validation: agent should favor correctness for large diffs

---
*Phase: 01-foundation*
*Context gathered: 2026-04-28*
