# Phase 1: Foundation - Discussion Log

**Date:** 2026-04-28
**Mode:** Default (interactive)
**Areas Discussed:** 4

---

## Area 1: Existing Code Strategy

**Question:** How should we handle the existing Pydantic v1 code?

**Options Presented:**
1. Archive and rebuild fresh — Move to `src/legacy/`, build from Tasks.md spec (cleanest, but discards working code)
2. Adapt and extend — Refactor Pydantic v1 → v2, keep tree-sitter, extend for 13-call pipeline (faster, more complex)
3. Hybrid approach — Keep signature_extractor.py (it's solid), rebuild IR models as Pydantic v2 (balanced)

**User Selection:** Option 1

**Decision:** Archive and rebuild fresh. Moving existing files to `src/legacy/` and building from Tasks.md spec.

**Rationale:** Cleanest approach, guarantees alignment with 13-LLM call pipeline architecture specified in Tasks.md

---

## Area 2: Pydantic v2 Schema Structure

**Question:** Should we follow Tasks.md schema exactly, or adapt based on learnings from existing code?

**Options Presented:**
1. Follow Tasks.md exactly — Build all models as specified (guarantees alignment with 13-call pipeline)
2. Adapt with improvements — Keep the structure, add fields the existing code used (e.g., `declarations` in TestCase)
3. Minimal adaptation — Follow exact schema, add only if critical for Stage 2 generation

**User Selection:** Option 1

**Decision:** Follow Tasks.md exactly. Build all Pydantic v2 models as specified to guarantee alignment with the 13-LLM call pipeline.

**Rationale:** Tasks.md is the source of truth for the 13-call pipeline — Pydantic schema must match what Call 5A expects

---

## Area 3: Context Assembler Scope

**Question:** What's the source for struct/typedef/macro/HAL extractions?

**Options Presented:**
1. From diff only — Extract everything visible in the PR diff itself (simple, but misses typedefs/macros defined in headers)
2. From diff + headers — Parse the diff, then scan referenced header files for structs/typedefs/HAL (more complete, requires header file access)
3. From diff + headers + codebase — Scan full project headers for all referenced types (most comprehensive, but could be slow)

**User Selection:** Option 1

**Decision:** From diff only. Extract everything visible in the PR diff itself.

**Rationale:** Keeps Phase 1 self-contained with no external dependencies. If header scanning becomes necessary, can be added in future phase.

**Implications:**
- Struct definitions only if they appear in the diff
- Typedefs only if they appear in the diff
- Macros only if #define appears in the diff
- HAL functions detected via function calls in the diff's AST

---

## Area 4: Type Classification System

**Question:** How comprehensive should the type mapping be?

**Options Presented:**
1. Essential types only — Map common automotive types (uint8_t, uint16_t, uint32_t, int32_t, float, bool, pointers, arrays, structs)
2. Project-specific types — Map AUTOSAR types found in this codebase + essential types (parse typedef from diff dynamically)
3. Comprehensive mapping — Map all C standard types, all AUTOSAR types, handle aliases recursively

**User Selection:** Option 3

**Decision:** Comprehensive mapping. Map all C standard types, all AUTOSAR types, handle aliases recursively.

**Rationale:** Automotive AUTOSAR codebases have complex type hierarchies — need to handle full C standard types and recursively resolve typedef chains

**Implications:**
- Full C standard types (char, short, long, long long, etc.)
- Recursively resolve typedef chains (MyType → uint8_t → UINT8)
- Handle complex types like function pointers, const qualifiers

---

## Deferred Ideas

| Idea | Reason Deferred | Suggested Phase |
|------|-----------------|-----------------|
| Existing pattern loading | Requires test database infrastructure | Future phase |
| Context from external headers | Diff-only approach tried first; add if insufficient | Phase 2+ if needed |
| Struct field validation against headers | C2039 errors will reveal if needed | Phase 5 (compile validator) |

---

## Session Notes

- User chose "all" to discuss all 4 areas
- All decisions favor alignment with Tasks.md specification
- Conservative approach: start with diff-only, add complexity if needed
- Comprehensive type resolution is important for automotive codebases

---

**Discussion Completed:** 2026-04-28
**Next Step:** `/gsd-plan-phase 1` — Create executable plans for Phase 1
