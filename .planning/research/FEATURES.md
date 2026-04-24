# Feature Research

**Domain:** AI-powered Cantata C unit test generation from GitHub PR diffs
**Researched:** 2026-04-24
**Confidence:** HIGH (based on direct codebase analysis + domain expertise)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels broken or useless.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Compilable C output** | If generated `.c` files don't compile, the entire tool is useless. This is the core value prop. | HIGH | Current code produces `int arr[] = 0;` — invalid C. Requires structured intermediate format between Stage 1 and Stage 2 to guarantee correct syntax. |
| **Correct array initialization syntax** | Array params are the most common pattern in C functions. `int arr[] = {1,2,3};` not `int arr[] = 0;` | MEDIUM | Root cause: LLM drops array values from markdown. Fix by parsing `{1,2,3}` into Python list, then emitting deterministic C syntax. Never trust LLM to generate array initializer syntax. |
| **Correct function call syntax** | `func(arr, size)` not `func(arr[], size)`. The `[]` in parameter declaration ≠ in function call. | LOW | Trivial syntactic rule. Must be enforced in deterministic code generation, not left to LLM. |
| **Faithful data transfer between stages** | Test data from Stage 1 markdown (arr={1,2,3,4}, size=4) MUST appear identically in Stage 2 C code. | HIGH | **THE critical bug.** Currently Stage 2 drops all values to 0. Requires parsing markdown into structured data (JSON/dict), then generating C code from that data deterministically. |
| **Variables declared before use with correct types** | C requires declarations. Mismatched types cause compile errors. | MEDIUM | Function signatures must be parsed from diff accurately. Variable types must match parameter types in the signature. |
| **Function signature matching from diff** | Tests must call the actual functions from the PR diff, with correct parameter types and counts. | MEDIUM | Current regex `(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{` is fragile. Must handle `int arr[]`, `const char*`, `struct Foo*`, multi-line signatures. |
| **Cantata++ framework compliance** | Output must use `#include <cantpp.h>`, `TEST_SCRIPT_INFO()`, `CHECK_EQUAL()`, `RUN_TEST()`, coverage analysis rules. | MEDIUM | Template already exists in `cantata_integration.py`. Needs fixing but structure is correct. |
| **Void return function handling** | Void functions must be called without assignment; validate via state checks. | LOW | Simple rule: if return type is `void`, don't assign result. Current code handles this in `cantata_integration.py`. |
| **Struct field initialization** | Struct-based functions need proper `{.field1 = val1, .field2 = val2}` initialization. | MEDIUM | Requires recognizing struct types from diff and generating correct C designated initializer syntax. |
| **Single command entry point** | User runs one command: poll GitHub → generate tests → output files. | LOW | Currently split across `poller.py` and `workflow.py`. Merge into single `main.py`. |
| **Correct header file generation** | Generated `.h` must match actual function signatures, not `extern int func(int param)` for everything. | MEDIUM | Current `generate_header_file()` hardcodes `int func(int param)` for all functions. Must use actual parsed signatures. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required for v1, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Deterministic code generation (template-based)** | Eliminates entire class of LLM syntax errors. LLM designs tests; Python writes C code. | MEDIUM | **Most impactful differentiator.** Use LLM for Stage 1 (test design — it's good at this) and deterministic Python templates for Stage 2 (C code — LLM is unreliable). This is the key architectural insight. |
| **Post-generation compilation validation** | Catch compile errors immediately. Feed errors back for automatic correction. | HIGH | Run MSVC17 compile attempt after generation. If errors, either re-prompt LLM with error messages or fix via deterministic rules. Saves manual debugging. |
| **Structured intermediate format (JSON)** | Explicit, verifiable data contract between stages. No "LLM hope-based" data transfer. | MEDIUM | Parse Stage 1 markdown into JSON with typed fields: `{"arrays": [{"name": "arr", "values": [1,2,3,4], "type": "int"}], "expected": 10}`. Stage 2 reads JSON, not raw markdown. Enables validation, debugging, and deterministic generation. |
| **Branch-aware test generation** | Detect if/else/switch from diff and generate tests covering each branch. | MEDIUM | LLM in Stage 1 can identify branches. Stage 2 ensures at least one test per branch. Current PROMPT_1 mentions coverage but doesn't enforce branch-specific tests. |
| **Diff-to-signature parser (robust)** | Handle complex C signatures: function pointers, `const` qualifiers, multi-line declarations, typedefs. | MEDIUM | Current regex is fragile. Proper C signature parsing handles the 20% of edge cases that cause 80% of failures. |
| **Self-healing compile loop** | If compile fails, automatically fix common errors (missing `;`, wrong types, undeclared vars) without re-calling LLM. | MEDIUM | Parse MSVC error messages, apply deterministic fixes (add semicolons, fix types). Only re-call LLM for unfixable errors. Faster and more reliable than full regeneration. |
| **Test deduplication** | Avoid generating duplicate test cases that test the same scenario. | LOW | Simple heuristic: group by (function, input signature) and skip duplicates. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for this specific project.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Full C AST parsing** | "Why not parse the full C code into an AST?" | Massively over-engineered for diff-based test generation. Requires clang/libtooling, build system integration, header resolution. The diff IS the input — we don't have the full project. | Parse only function signatures from diff with targeted regex. Sufficient for 95% of cases. |
| **LLM fine-tuning on Cantata tests** | "Train a model specifically for Cantata output" | Requires hundreds of example test files, training infrastructure, ongoing maintenance. Single user, single project — ROI is negative. | Better prompts + deterministic post-processing. Achieve same reliability without ML ops. |
| **Web UI / REST API** | "Wouldn't a dashboard be nice?" | Out of scope. Single user, CLI-driven workflow. UI adds 3-5x development time with zero value for current use case. | CLI with clear `print()` output. Add API later if multi-user demand emerges. |
| **CI/CD pipeline integration** | "Auto-generate tests on every PR" | Premature. Generated tests don't compile yet. Adding CI integration before reliability is achieved creates noise, not value. | Fix compilation first. Add CI trigger as Phase 2 once tests are reliable. |
| **Multi-language support** | "Support C++, Java, Python tests too" | Each language has different syntax rules, test frameworks, compilation pipelines. Expanding scope before C works is scope creep at its worst. | Master C + Cantata first. Language-specific generators can be added as separate modules later. |
| **Pure LLM generation (no templates)** | "Just improve the prompt, the LLM should handle it" | Empirically proven false by this project. PROMPT_2 already has extensive rules (lines 151-237) and the LLM still produces `arr[] = 0`. LLMs are unreliable for exact syntax reproduction over multi-stage pipelines. | Hybrid approach: LLM for design, deterministic Python for code generation. |
| **Cantata Server integration** | "Upload results to Cantata Server automatically" | Server is available (localhost:8085) but integration adds complexity without addressing the core problem (tests don't compile). | Fix compilation first. Server upload is a trivial HTTP POST once tests work. |
| **Concurrent PR processing** | "Process multiple PRs in parallel" | Single-user tool, single GLM endpoint, 600s timeout per call. Parallelism adds complexity (file locking, state management) with minimal throughput gain. | Sequential processing is fine. Optimize per-PR reliability, not throughput. |
| **Generic "AI test framework"** | "Abstract it so it works with any test framework" | Cantata has specific macros, coverage rules, and conventions. Abstracting across frameworks dilutes Cantata-specific correctness. | Be opinionated about Cantata. If framework swap is needed later, it's a rewrite of the code generation layer, not an API surface. |

## Feature Dependencies

```
[Diff-to-Signature Parser]
    └──enables──> [Faithful Data Transfer]
                      └──enables──> [Deterministic Code Generation]
                                        └──enables──> [Compilable C Output]
                                                          └──enables──> [Post-Gen Compilation Validation]
                                                                            └──enables──> [Self-Healing Compile Loop]

[Structured Intermediate Format (JSON)]
    └──enables──> [Faithful Data Transfer]
    └──enables──> [Deterministic Code Generation]
    └──enables──> [Post-Gen Compilation Validation] (provides structured error context)

[Cantata++ Framework Compliance]
    └──requires──> [Compilable C Output]
    └──requires──> [Correct Header File Generation]

[Branch-Aware Test Generation]
    └──requires──> [Diff-to-Signature Parser] (to detect return types and branches)

[Single Command Entry Point]
    └──requires──> [Compilable C Output] (no point in automating if output is broken)
    └──conflicts with──> [Pure LLM Generation] (merging modules means choosing one approach)

[Pure LLM Generation]
    └──conflicts with──> [Deterministic Code Generation] (mutually exclusive architectures)
    └──conflicts with──> [Structured Intermediate Format] (LLM-to-LLM vs LLM-to-data-to-code)
```

### Dependency Notes

- **Diff-to-Signature Parser enables everything:** If we can't parse function signatures correctly from the diff, no downstream feature works. Must be fixed first.
- **Structured Intermediate Format enables Deterministic Code Generation:** The key architectural insight. Without structured data between stages, we're asking the LLM to both understand test design AND write perfect C syntax — it fails at the latter.
- **Compilable C Output enables Post-Gen Validation:** You can't validate compilation if the code never compiles. Fix generation first, then add validation.
- **Pure LLM Generation conflicts with Deterministic Code Generation:** These are mutually exclusive approaches. The current code tries to do Pure LLM (PROMPT_2 → raw C code). Switching to Deterministic means PROMPT_2 becomes unnecessary — Python generates C code from structured data.
- **Single Command Entry Point requires Compilable Output:** Merging poller + workflow is pointless if the output is broken. Fix the core pipeline first, then merge entry points.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to make the tool actually useful.

- [x] ~~Poll GitHub PRs with labeled diffs~~ — Already working
- [x] ~~Stage 1: Generate test case markdown~~ — Already working
- [ ] **Structured intermediate format** — Parse Stage 1 markdown into JSON with typed fields. This is the foundation that makes everything else possible.
- [ ] **Diff-to-signature parser (robust)** — Parse function signatures from diff with proper handling of `int arr[]`, `const char*`, multi-param functions. Replace the fragile regex.
- [ ] **Deterministic C code generation** — Python generates C test code from JSON data + parsed signatures. No LLM call for Stage 2. Array init: `int arr[] = {1,2,3,4};`. Function calls: `sumPositive(arr, 4);`. Guaranteed correct syntax.
- [ ] **Cantata++ boilerplate template** — Generate the complete Cantata test file structure (includes, extern declarations, `run_tests()`, coverage rules, `main()`) deterministically.
- [ ] **Correct header file from signatures** — Generate `.h` with actual function signatures, not `int func(int param)`.
- [ ] **Void function handling** — Don't assign return value for void functions. Use state checks instead.
- [ ] **Single command entry point** — Merge `poller.py` + `workflow.py` into one `main.py`.

### Add After Validation (v1.x)

Features to add once core generation is reliable.

- [ ] **Post-generation compilation validation** — Run `cl.exe` on generated `.c` file, capture errors. Trigger: when first generated file compiles successfully.
- [ ] **Self-healing compile loop** — Parse MSVC errors, apply deterministic fixes, retry. Trigger: when compilation validation reveals recurring fixable errors.
- [ ] **Branch-aware test generation** — Detect if/else/switch in diff and ensure coverage. Trigger: when basic test generation is reliable.
- [ ] **Struct field initialization** — Handle `struct` parameters with designated initializers `{.field = value}`. Trigger: when diff contains struct-based functions.
- [ ] **Remove VIO LLM code path** — Delete `vio_llm_client.py`, `vio_config.py`, all `USE_LLM_TYPE` branching. Single LLM: GLM via opencode.

### Future Consideration (v2+)

Features to defer until the tool is proven reliable for its core use case.

- [ ] **Cantata Server result upload** — POST `.ctr` and `.cov` files to localhost:8085. Low effort once tests compile and run.
- [ ] **PR comment posting** — Post generated test summary back to GitHub PR. Useful for team visibility.
- [ ] **Test deduplication** — Avoid testing the same scenario twice across multiple runs.
- [ ] **Coverage report interpretation** — Parse `.cov` output and flag functions below 100% coverage.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Structured intermediate format (JSON) | HIGH | MEDIUM | P1 |
| Deterministic C code generation | HIGH | MEDIUM | P1 |
| Diff-to-signature parser (robust) | HIGH | MEDIUM | P1 |
| Correct header file generation | HIGH | LOW | P1 |
| Cantata++ boilerplate template | HIGH | LOW | P1 |
| Faithful data transfer (parse → emit) | HIGH | LOW | P1 |
| Single command entry point | MEDIUM | LOW | P1 |
| Void function handling | MEDIUM | LOW | P1 |
| Post-gen compilation validation | HIGH | HIGH | P2 |
| Self-healing compile loop | MEDIUM | HIGH | P2 |
| Branch-aware test generation | MEDIUM | MEDIUM | P2 |
| Struct field initialization | MEDIUM | MEDIUM | P2 |
| Remove VIO LLM code path | LOW | LOW | P2 |
| Cantata Server upload | LOW | LOW | P3 |
| PR comment posting | LOW | MEDIUM | P3 |
| Test deduplication | LOW | LOW | P3 |
| Coverage report interpretation | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch — these fix the core bug and make the tool functional
- P2: Should have, add when possible — reliability and robustness improvements
- P3: Nice to have, future consideration — operational enhancements

## The Critical Architectural Insight

### Current Architecture (Broken)

```
Diff → LLM (PROMPT_1) → Markdown table → LLM (PROMPT_2) → C code (broken)
                                                      ↑
                                              LLM drops all values
                                              Produces arr[] = 0
```

### Recommended Architecture (Reliable)

```
Diff → LLM (PROMPT_1) → Markdown table → Python Parser → JSON (structured data)
                                                                    ↓
                                               Python Code Generator → C code (correct)
                                                       ↑
                                              Uses parsed signatures
                                              from diff + JSON test data
                                              Deterministic, no LLM
```

**Why this works:**
- LLM is excellent at understanding C code semantics and designing test cases (Stage 1 works!)
- LLM is terrible at faithfully reproducing exact values through a multi-stage prompt chain (Stage 2 fails!)
- Python is excellent at string formatting with exact values (deterministic code generation never drops values)
- The JSON intermediate format makes data transfer explicit and debuggable

**What changes in the codebase:**
1. `testcase_generator.py`: Keep `PROMPT_1` and `generate_testcases()` as-is
2. NEW: `test_parser.py` — Parse markdown table into structured JSON (arrays, scalars, expected values)
3. NEW: `code_generator.py` — Deterministic C code generation from JSON + parsed signatures
4. `cantata_integration.py`: Simplify to template-based generation (already partially there)
5. `testcase_generator.py`: Delete `PROMPT_2` and `generate_module_test_code()` (no longer needed)
6. `workflow.py`: Wire new pipeline: LLM → parse → generate

## Competitor Feature Analysis

| Feature | Copilot/ChatGPT Code Gen | Traditional Test Frameworks | Our Approach |
|---------|--------------------------|----------------------------|--------------|
| Test design intelligence | LLM-based (good) | Manual (slow) | LLM-based (good) |
| C syntax correctness | Often wrong (same problem we have) | Perfect (human-written) | Deterministic Python (guaranteed) |
| Cantata++ compliance | Doesn't know Cantata | Manual compliance | Template-based (guaranteed) |
| Data fidelity | Often drops values | Perfect (human-written) | Structured format (guaranteed) |
| Speed | Seconds | Hours/days | Seconds (LLM) + milliseconds (code gen) |
| Branch coverage | Cannot verify | Manual verification | Structured test data enables verification |

**Key insight:** No existing AI tool reliably generates Cantata-compatible C test code. The gap is always in the "last mile" — getting from AI-designed tests to compilable C. Our competitive advantage is the hybrid architecture: LLM for design, deterministic code for syntax.

## Root Cause Analysis of Current Bugs

Based on direct code reading, the specific bugs are:

1. **`testcase_generator.py` line 322:** Passes `func` (a Python dict) as function signature to the LLM. The LLM sees `{'function_name': 'sumPositive', ...}` instead of `int sumPositive(int arr[], int size)`.

2. **`testcase_generator.py` line 322:** Passes full markdown table as `TEST CASES` to LLM. The LLM must parse the markdown table AND generate correct C code in one shot — it fails at both simultaneously.

3. **`cantata_integration.py` `extract_input_values()`:** Only handles `key=value` pairs. Cannot parse `arr={1,2,3,4}` (the `{` breaks its split logic). Returns empty dict, defaults to `0`.

4. **`workflow.py` line 339:** Calls `new_generate_cantata_tests()` which re-runs Stage 1 (calling LLM again) even though test cases already exist in the markdown file. Wastes API calls and introduces inconsistency.

5. **Two competing code paths:** `testcase_generator.generate_cantata_tests()` vs `cantata_integration.generate_cantata_tests()` — both generate C code, both broken in different ways. `workflow.py` imports both.

## Sources

- Direct codebase analysis: `testcase_generator.py`, `cantata_integration.py`, `workflow.py`, `glm_client.py`
- Sample outputs: `generated_tests/pr_167_testcases.md` (correct Stage 1), `generated_tests/test_module_167_167.c` (broken Stage 2)
- Project context: `.planning/PROJECT.md`
- Architecture analysis: `.planning/codebase/ARCHITECTURE.md`
- Domain knowledge: Cantata v24.04 documentation (QA Systems), MSVC17 C compiler conventions
- LLM-to-code pipeline patterns: Industry consensus that structured intermediate formats outperform pure LLM chains for code generation (MEDIUM confidence — based on training data, not specific recent source)

---
*Feature research for: AI-powered Cantata C test generation*
*Researched: 2026-04-24*
