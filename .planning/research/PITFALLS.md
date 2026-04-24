# Domain Pitfalls: LLM-Generated Cantata C Test Code

**Domain:** AI-powered Cantata unit test generation from C code diffs
**Researched:** 2026-04-24
**Confidence:** HIGH (empirical — every pitfall observed in real generated output across PRs #155–#500)

## Critical Pitfalls

Mistakes that produce uncompilable output or silent test corruption. Every pitfall below is confirmed by examining actual generated `.c` files in `generated_tests/`.

---

### Pitfall 1: LLM Replaces All Test Data With Zeros

**What goes wrong:**
Every generated test function initializes all variables to `0` regardless of what the markdown test cases specify. The markdown says `arr={1,2,3,4}, size=4, expected=10` but the C output is `int arr[] = 0; int size = 0;` for every single test case.

**Why it happens:**
Three compounding root causes:

1. **Parameter type extraction is broken** (`testcase_generator.py:302-306`): The regex `r'(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{'` captures `arr[]` as a single token. The `split(',')` on params then produces `"int arr[]"` which doesn't contain `:`, so the fallback defaults it to `{"name": "int arr[]", "type": "int"}` — losing the array nature entirely.

2. **Function signature passed as Python dict repr** (`testcase_generator.py:322`): The LLM receives `FUNCTION SIGNATURE: {'function_name': 'sumPositive', 'return_type': 'int', 'parameters': [{'name': 'arr', 'type': 'int'}]}` — the `arr` parameter's type is already wrong (`int` instead of `int[]`). The LLM sees "int arr" and generates `int arr[] = 0;` because it knows it's an array from the extern, but has lost the actual values.

3. **ALL test cases sent for every function** (`testcase_generator.py:322`): The LLM receives test cases for `sumPositive`, `countNegative`, and `firstZeroIndex` all at once when generating code for just `sumPositive`. This floods the context window and makes it harder for the LLM to match data to the correct function.

**Consequences:** Every generated test file is 100% broken. No test can pass because the data is wrong. Zero compilation chance since `int arr[] = 0;` is invalid C.

**Prevention:**
- Parse test data from markdown BEFORE sending to LLM, inject parsed values directly into the prompt as explicit C initialization statements
- Filter test cases per function — only send relevant rows
- Fix parameter type extraction: handle `int arr[]`, `int *arr`, `int mat[][10]` properly
- Add a post-generation validation pass that compares markdown values to generated C values

**Warning signs:**
- Generated `.c` file contains `= 0` for every variable initialization
- Test cases in markdown have distinct values but C code doesn't
- Parameter count in LLM prompt shows `'type': 'int'` for array parameters

**Phase to address:** Phase 1 (fix Stage 2 C generation) — this is the single highest-priority bug

---

### Pitfall 2: Invalid C Array Initialization Syntax

**What goes wrong:**
The LLM generates `int arr[] = 0;` instead of `int arr[] = {1,2,3,4};`. Similarly, 2D arrays become `int mat[][10] = 0;`. These are syntax errors — C requires brace-enclosed initializer lists for arrays.

**Why it happens:**
The LLM sees the parameter declared as `int arr[]` in the extern section, recognizes it needs an array, but the prompt provides no concrete initializer. It fills with `0` as a placeholder. This is a model limitation — GLM 4.7 Flash defaults to zero-initialization when it can't resolve the concrete values.

**Consequences:** Compilation failure on every test case. MSVC17 reports error C2078: too many initializers / C2057: expected constant expression.

**Prevention:**
- Never ask the LLM to "use the values from the test cases" — instead, explicitly embed the parsed values as C code fragments in the prompt
- Example prompt structure: "Initialize: int arr[] = {1,2,3,4}; int size = 4;" — give the LLM the exact C code to use
- Add syntax validation: regex-check generated code for patterns like `int \w+\[\]\s*=\s*[^{]` (array init without braces)
- Include few-shot examples in the prompt with correct array initialization

**Warning signs:**
- `int arr[] = 0;` appears in generated output
- `int mat[][10] = 0;` in generated output
- No `{` character following `=` in array declarations

**Phase to address:** Phase 1 (fix Stage 2 C generation)

---

### Pitfall 3: Bracket Syntax in Function Calls

**What goes wrong:**
Generated code calls functions as `sumPositive(arr[], size)` instead of `sumPositive(arr, size)`, and `sumMatrix(mat[][10], rows, cols)` instead of `sumMatrix(mat, rows, cols)`. The `[]` is type notation, not argument syntax.

**Why it happens:**
The LLM sees the extern declaration `extern int sumPositive(int arr[], int size)` and copies the parameter type syntax directly into the function call. This is a classic LLM confusion between declaration syntax and expression syntax.

**Consequences:** Compilation failure. MSVC17 reports error C2059: syntax error '['. Every test function fails.

**Prevention:**
- In the prompt, separate "declaration" from "usage" explicitly: "Declare as: int arr[] = {1,2,3}; Call as: sumPositive(arr, size)"
- Post-generation regex check: scan for `\w+\[\]` or `\w+\[\d+\]` inside function call parentheses
- Add a fixup pass: replace `funcname(varname[], ...)` with `funcname(varname, ...)` using regex

**Warning signs:**
- `\w+\[\]` appears inside function call arguments
- `\w+\[\d+\]` appears inside function call arguments
- Generated function call contains brackets

**Phase to address:** Phase 1 (fix Stage 2 C generation) — can be partially mitigated with post-processing regex fixup

---

### Pitfall 4: Missing Semicolons in Variable Declarations

**What goes wrong:**
Generated code contains `int a = 0` without a trailing semicolon. Observed in `test_module_500_500.c` lines 96-97, 122-123, etc. Multiple consecutive declarations are missing semicolons.

**Why it happens:**
LLM output formatting inconsistency. When generating multiple variable declarations, the model sometimes forgets the semicolon, especially when the values are all `0`. This is a known LLM code generation weakness — models produce syntactically incomplete statements when generating repetitive patterns.

**Consequences:** Compilation failure. MSVC17 reports error C2146/C2061 on the next line.

**Prevention:**
- Post-generation syntax validation: check that every line matching `int \w+ =` ends with `;`
- Automated fixup: append semicolons to declaration lines that are missing them
- Include few-shot examples with correct semicolon usage

**Warning signs:**
- Variable declaration lines not ending with `;`
- `int \w+ = \d+\n` without `;` before newline

**Phase to address:** Phase 1 (fix Stage 2 C generation) — address via post-processing validation

---

### Pitfall 5: Markdown Preamble Corrupts C Files

**What goes wrong:**
The `save_to_markdown()` function in `workflow.py:194-207` wraps every saved file with `# {title}\nGenerated at: ...\n---\n\n`. This means `.c` files start with:
```c
# Cantata Test Script - PR #500
Generated at: 2026-04-24 11:13:42
---
```
which are invalid C tokens. The `#` is treated as a preprocessor directive but `Cantata Test Script...` is not a valid directive.

**Why it happens:**
`workflow.py:346-347` calls `save_to_markdown()` for both `.c` files and `.md` files, even though `save_to_markdown()` is designed for markdown content. The function unconditionally prepends markdown headers.

**Consequences:** Compilation failure. MSVC reports fatal error C1021: invalid preprocessor command. Even if the LLM generates perfect C code, the file is corrupted by the wrapper.

**Prevention:**
- Create a separate `save_c_file()` function that does NOT prepend headers
- Or add a `raw=False` parameter to `save_to_markdown()` that skips the preamble for non-markdown files
- Write the C code directly to file without any wrapping

**Warning signs:**
- `.c` file starts with `# Cantata` or `# Test` or `Generated at:` on first line
- First non-comment line is not a valid C preprocessor directive

**Phase to address:** Phase 1 (fix file output) — trivial fix but critical impact

---

### Pitfall 6: Function Signatures Corrupted in Extern Section

**What goes wrong:**
Instead of proper extern declarations like `extern int calculate_product(int a, int b);`, the LLM generates `int calculate_product(int a, int b) {;` — a function definition body start `{` followed by a semicolon. This creates an incomplete function definition in the extern section.

**Why it happens:**
When the LLM receives the full function signature and is asked to generate test code, it sometimes confuses "declare this function" with "define this function". The `{;` pattern suggests the model started generating a function body and then terminated with `;`.

**Consequences:** Compilation failure. The compiler sees a function definition starting with `{` and then encounters the next declaration, causing parse errors.

**Prevention:**
- Don't ask the LLM to generate extern declarations — use the already-extracted signatures from the diff
- Generate the extern block programmatically from the parsed signatures, not via LLM
- Post-generation validation: check that extern section contains only `extern ... (...)` lines ending with `;`

**Warning signs:**
- Extern section contains `{` characters
- Extern section contains `void func(...){;` or `int func(...){;`
- `extern` keyword missing from function declarations

**Phase to address:** Phase 1 (fix extern generation — make programmatic, not LLM-generated)

---

## Moderate Pitfalls

### Pitfall 7: No `main()` Function in Generated Tests

**What goes wrong:**
The LLM-generated output (from testcase_generator.py Stage 2) does not include a `main()` function. Cantata test scripts require `main()` with `OPEN_LOG()`, `START_SCRIPT()`, `END_SCRIPT()` calls. The old `cantata_integration.py` template (lines 276-296) included these, but the new pipeline relies entirely on the LLM which omits them.

**Prevention:** Generate the `main()` entry point and `run_tests()` control function programmatically as a template, not via LLM. Only ask the LLM to generate individual test case bodies.

**Phase to address:** Phase 1 (Cantata template scaffolding)

---

### Pitfall 8: Missing Cantata Coverage Analysis Section

**What goes wrong:**
The old `cantata_integration.py` template (lines 239-296) generated `rule_set()` with `ANALYSIS_CHECK()` for 100% entry point + statement + call + decision coverage, plus `EXPORT_COVERAGE()`. The new LLM-generated output omits this entirely. Cantata requires these for coverage reporting.

**Prevention:** Include coverage analysis as a static template appended to the generated code. Don't rely on the LLM to know Cantata coverage macros.

**Phase to address:** Phase 1 (Cantata template scaffolding)

---

### Pitfall 9: Void Function Tests Lack State Verification

**What goes wrong:**
For void-return functions like `fill_array()` and `transposeMatrix()`, the generated code calls the function but only logs "PASSED: executed successfully" without verifying any state changes. For `fill_array(arr, 3, 99)`, the test should verify that `arr[0] == 99 && arr[1] == 99 && arr[2] == 99`.

**Why it happens:**
The LLM doesn't know what state to check because the prompt doesn't specify post-conditions. The markdown test cases have `Post-Conditions` columns like "All array elements equal 99" but this text is not translated into C assertions.

**Prevention:**
- For void functions, extract post-conditions from the markdown table
- Generate explicit assertions: `CHECK_EQUAL(arr[0], 99); CHECK_EQUAL(arr[1], 99);`
- Add a void-function-specific prompt section with examples of state verification

**Phase to address:** Phase 2 (improve test quality for void/struct functions)

---

### Pitfall 10: Struct Field Initialization Missing

**What goes wrong:**
When functions take struct parameters (Queue, Stack, Node), the LLM has no guidance on how to initialize struct fields. The prompt mentions struct types but doesn't provide the actual struct definition from the diff. The LLM either generates incomplete struct initialization or skips it entirely.

**Prevention:**
- Extract struct definitions from the diff and include them in the prompt
- Provide a struct initialization template in the prompt with field-by-field initialization
- Add post-generation check for `struct` keyword usage to verify fields are populated

**Phase to address:** Phase 2 (struct-based function support)

---

### Pitfall 11: `function_under_test` Placeholder Remains in Output

**What goes wrong:**
The generated files still contain `extern int function_under_test(int param);` as a leftover generic placeholder, even when actual functions have been detected. PR #167 has `sumPositive`, `countNegative`, `firstZeroIndex` but also includes the generic `function_under_test` extern.

**Prevention:**
- Remove the `function_under_test` fallback entirely
- If no function signatures are found, report an error instead of generating a placeholder
- Post-generation: grep for `function_under_test` and remove/replace

**Phase to address:** Phase 1 (cleanup)

---

## Minor Pitfalls

### Pitfall 12: CHECK_EQUAL vs ASSERT_EQUALS Inconsistency

**What goes wrong:**
PROMPT_2 references `ASSERT_EQUALS(expected, actual)` but the generated code uses Cantata's `CHECK_EQUAL(actual, expected)`. The argument order is also reversed between these macros. Cantata's actual macro is `CHECK_EQUAL(expected, actual)` per the standard API.

**Prevention:** Standardize on `CHECK_EQUAL(expected, actual)` in all prompts and templates. Verify argument order against Cantata v24.04 documentation.

**Phase to address:** Phase 1 (prompt cleanup)

---

### Pitfall 13: `static` Missing on `initialise_global_data()`

**What goes wrong:**
The LLM generates `void initialise_global_data()` without `static`, while the old template used `static void initialise_global_data()`. Cantata expects these helper functions to be file-scoped.

**Prevention:** Generate the global data boilerplate programmatically, not via LLM.

**Phase to address:** Phase 1 (Cantata template scaffolding)

---

### Pitfall 14: Test Case 1 Is a Placeholder

**What goes wrong:**
In PR #500 output, test case 1 contains `-------------` for all values and the function call `-------------()`. This is the `function_under_test` placeholder test from the old `cantata_integration.py` template that creates 3 default test functions when no test cases are parsed correctly.

**Prevention:** Remove the "create default test functions" fallback (lines 140-151 in cantata_integration.py). If no test cases are parsed, fail with an error.

**Phase to address:** Phase 1 (cleanup)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Regex-based C signature extraction | Quick to implement, no C parser dependency | Misses function pointers, typedefs, macros, multi-line declarations; silently produces wrong types for `int arr[]` | Never — this is a root cause of Pitfall 1 |
| Sending ALL test cases to LLM per function | Simpler code — one prompt for all | LLM context pollution; data for wrong functions confuses model; 3x token usage | Never for production — filter per function |
| `save_to_markdown()` for `.c` files | One save function for all output | Corrupts C files with markdown headers; compilation impossible | Never — C and markdown need different writers |
| Letting LLM generate Cantata boilerplate | Less template code to maintain | LLM omits `main()`, coverage, pragma directives; inconsistent between runs | Never — boilerplate should be programmatic template |
| No post-generation validation | Saves development time | Broken code ships silently; every output must be manually inspected | Only during initial prototyping — must add before production |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Cantata v24.04 MSVC17 | Using C99/C11 features not supported by MSVC17 (e.g., variable-length arrays, `for(int i=...)`) | Stick to C89/C90 compatible code; declare all variables at block start |
| Cantata `#include <cantpp.h>` | Not verifying the include path resolves in Cantata environment | Ensure `C:\LegacyApp\qa_systems\cantata\inc` is in the include path |
| Cantata test script structure | Missing `#define TEST_SCRIPT_GENERATOR 2` and `/* pragma ipl cantata++ testscript start */` | Include both in programmatic template — required by Cantata GUI/parser |
| Cantata `RUN_TEST()` macro | Putting test body directly in `run_tests()` instead of separate functions | Each test must be its own function called via `RUN_TEST(func_name)` |
| GLM 4.7 Flash via opencode CLI | `shell=True` in subprocess; temp file prompt passing; 600s timeout may be too short for large diffs | Use `shell=False`, pass command as list; increase timeout for large inputs |
| opencode CLI output parsing | Assuming output is clean C code — it may contain conversational preamble ("Here is the generated code...") | Use `clean_output()` to strip preamble; verify first line is valid C |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Sequential LLM calls per function | 3 functions × 60s each = 3+ minutes per PR | Filter test cases per function; parallelize independent LLM calls | Already slow — any PR with 5+ functions takes 5+ minutes |
| Full diff sent to LLM without chunking | Token limits hit on large PRs; truncated diffs produce incomplete tests | Split diffs by file; only send changed functions | PRs with 10+ changed files |
| No caching of LLM results | Re-running on same PR makes identical API calls | Hash diff content + test cases; cache results by hash | Already an issue — accidental re-runs waste API calls |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Hardcoded API key in `vio_config.py` | Exposed in git history; anyone with repo access has the key | Move to `.env`; rotate the key; add to `.gitignore` |
| `shell=True` in `glm_client.py:39` | Command injection if prompt contains shell metacharacters | Remove `shell=True` — command is already a list |
| No input sanitization on diff content before LLM prompt | Malicious diff could contain prompt injection to manipulate LLM output | Sanitize diff content; limit to valid C code characters; truncate aggressively |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces:

- [ ] **Generated `.c` file exists:** Often contains `arr[] = 0` everywhere — verify actual test data values match markdown
- [ ] **Test functions compile:** Check for missing semicolons, bracket syntax in calls, invalid array init
- [ ] **Extern declarations correct:** Verify no `{;` corruption, all signatures match diff, no `function_under_test` leftover
- [ ] **`main()` function present:** Cantata requires entry point with `OPEN_LOG()`, `START_SCRIPT()`, `END_SCRIPT()`
- [ ] **Coverage analysis present:** `rule_set()` with `ANALYSIS_CHECK()` for entry point + statement + call + decision
- [ ] **`#define TEST_SCRIPT_GENERATOR 2`:** Required by Cantata GUI to recognize the file as a test script
- [ ] **File is valid C (no markdown preamble):** First line should be `/*` comment or `#define`, never `# Cantata Test Script`
- [ ] **Void functions tested with state verification:** Not just "executed successfully" — check actual post-conditions
- [ ] **`static` on helper functions:** `initialise_global_data()` and related must be file-scoped
- [ ] **`#pragma ipl cantata++ testscript start`:** Required for Cantata to parse the test script correctly
- [ ] **Matrix/2D array initialization:** Verify `int mat[][10] = {{1,2,...},{3,4,...}};` not `= 0;`

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| All data replaced with zeros | HIGH — requires re-running entire LLM pipeline with fixed prompts | 1. Fix parameter extraction 2. Fix prompt to embed parsed values 3. Re-run Stage 2 |
| Invalid array syntax `arr[] = 0` | LOW — regex fixup can patch existing files | 1. Parse markdown values 2. Regex-replace `int \w+\[\] = 0;` with correct init 3. Verify compilation |
| Bracket syntax in function calls | LOW — regex fixup: `\w+\[\]` → `\w+` in call contexts | 1. Find function calls with brackets 2. Remove brackets 3. Verify compilation |
| Markdown preamble in `.c` files | LOW — strip first 3 lines if they start with `# Cantata` | 1. Detect non-C preamble 2. Strip lines before `/*` comment block 3. Re-save |
| Missing `main()` / coverage | MEDIUM — can be appended as template | 1. Generate `main()` template 2. Append to file 3. Verify Cantata recognizes |
| Missing semicolons | LOW — automated fixup adds `;` to declaration lines | 1. Regex find `int \w+ = \d+` not ending with `;` 2. Append `;` 3. Verify compilation |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| P1: All data → zeros | Phase 1: Fix Stage 2 | Compare markdown values to C values programmatically; assert non-zero for non-zero test cases |
| P2: Invalid array init syntax | Phase 1: Fix Stage 2 + post-processing | Regex check generated code for `int \w+\[\]\s*=\s*[^{]`; compile test |
| P3: Bracket syntax in calls | Phase 1: Post-processing fixup | Regex check for `\w+\[\]` in function call arguments; compile test |
| P4: Missing semicolons | Phase 1: Post-processing validation | Regex check for declaration lines not ending with `;`; compile test |
| P5: Markdown preamble corruption | Phase 1: Fix file output | Verify `.c` file first line is `/*` or `#define`; never `# [A-Z]` |
| P6: Corrupted extern signatures | Phase 1: Generate programmatically | Verify extern section contains only `extern` lines with `;` endings |
| P7: No `main()` function | Phase 1: Cantata template | Verify `main()` exists with `OPEN_LOG`, `START_SCRIPT`, `END_SCRIPT` |
| P8: Missing coverage analysis | Phase 1: Cantata template | Verify `rule_set()` function exists with 4 `ANALYSIS_CHECK` calls |
| P9: Void function verification | Phase 2: Improve test quality | For void functions, verify state assertions exist (not just log messages) |
| P10: Struct initialization | Phase 2: Struct support | Verify struct fields populated with non-zero values matching test cases |
| P11: `function_under_test` leftover | Phase 1: Cleanup | Grep generated file for `function_under_test`; must not appear |
| P12: CHECK_EQUAL inconsistency | Phase 1: Prompt fix | Grep for `ASSERT_EQUALS`; should not appear in output |
| P13: Missing `static` | Phase 1: Template fix | Verify helper functions have `static` qualifier |
| P14: Placeholder test case | Phase 1: Remove fallback | Verify test case 1 is a real test, not dashes or "-------------" |

## Sources

- Empirical analysis of 23+ generated `.c` files in `generated_tests/` (PRs #151–#502)
- Side-by-side comparison of markdown test cases (`pr_*_testcases.md`) vs generated C code (`test_module_*_*_.c`)
- Code review of `testcase_generator.py` (prompt construction, parameter extraction, Stage 2 pipeline)
- Code review of `workflow.py` (file saving, markdown parsing, orchestration)
- Code review of `cantata_integration.py` (old template with correct Cantata structure)
- Code review of `glm_client.py` (opencode CLI interface)
- Cantata v24.04 template patterns from existing generated output (correct `main()`, coverage, pragma usage)
- `.planning/codebase/CONCERNS.md` — existing tech debt and fragile areas documentation

---
*Pitfalls research for: AI-powered Cantata C test generation*
*Researched: 2026-04-24*
