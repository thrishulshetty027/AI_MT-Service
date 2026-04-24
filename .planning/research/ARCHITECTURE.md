# Architecture Research

**Domain:** AI-powered C test code generator (Cantata++ target)
**Researched:** 2026-04-24
**Confidence:** HIGH (based on thorough codebase analysis + domain expertise)

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CLI Entry Point                               │
│                     (run.py / main.py)                               │
├──────────┬───────────────────────────────────────────────────────────┤
│          │                Orchestrator                                │
│          │          (pipeline coordination)                           │
├──────────┴──────┬───────────────────────┬───────────────────────────┤
│  GitHubAdapter  │    DiffAnalyzer      │    [LLM Client]            │
│  (poll + fetch) │  (signature + types)  │  (glm_client.py)          │
├─────────────────┼───────────────────────┼───────────────────────────┤
│                 │   TestCaseDesigner    │                            │
│                 │  (LLM → structured)   │                            │
│                 ├───────────────────────┤                            │
│                 │   TestCaseParser      │                            │
│                 │  (markdown → IR)      │                            │
│                 ├───────────────────────┤                            │
│                 │   CCodeGenerator      │                            │
│                 │  (IR → templates → C) │                            │
│                 ├───────────────────────┤                            │
│                 │   CValidator          │                            │
│                 │  (syntax + sanity)    │                            │
├─────────────────┴───────────────────────┴───────────────────────────┤
│                        File Storage                                  │
│   (generated_tests/)                                                 │
│   ├── pr_{N}.diff                                                    │
│   ├── pr_{N}_testcases.json    ← structured IR (NEW)                │
│   ├── test_module_{N}.c                                              │
│   └── module_{N}.h                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### Why This Architecture

The current system has a fatal flaw: **it asks the LLM to transfer structured data between stages**, and the LLM consistently drops values (arrays become `= 0`, sizes become `0`, struct fields vanish). The fix is architectural, not prompt engineering:

1. **LLM generates test case *definitions*** (Stage 1 — already works)
2. **Python code parses those definitions into structured data** (TestCaseParser — NEW, deterministic)
3. **Python templates emit C code from structured data** (CCodeGenerator — deterministic)
4. **LLM is never trusted with data transfer** — it generates *ideas*, Python handles *execution*

This is the **"LLM as advisor, templates as executor"** pattern. It eliminates the data-loss problem because the LLM never touches the C code generation step.

---

## Component Responsibilities

| Component | Responsibility | Key Files | Depends On |
|-----------|----------------|-----------|------------|
| **CLI Entry Point** | Single command: poll → generate → output | `run.py` (new) | Orchestrator |
| **Orchestrator** | Sequences pipeline stages, error handling, logging | `pipeline.py` (new) | All components |
| **GitHubAdapter** | Poll PRs, download diffs, manage labels, post comments | `poller.py` (refactored) | requests, .env |
| **DiffAnalyzer** | Extract function signatures, struct definitions, type info from C diffs | `diff_analyzer.py` (new) | re (stdlib) |
| **TestCaseDesigner** | Generate test case definitions via LLM (Stage 1) | `testcase_generator.py` (refactored) | LLM Client |
| **TestCaseParser** | Parse LLM markdown output into structured Python dicts | `testcase_parser.py` (new) | re (stdlib) |
| **CCodeGenerator** | Generate compilable Cantata C code from structured test cases using templates | `code_generator.py` (new) | Jinja2 or f-string templates |
| **CValidator** | Validate generated C: array syntax, declarations, type consistency | `c_validator.py` (new) | re (stdlib) |
| **LLM Client** | Abstract LLM calls behind uniform interface | `glm_client.py` (kept) | opencode CLI |
| **File Storage** | Read/write diff files, test cases, C output | Shared across components | os, json (stdlib) |

---

## Recommended Project Structure

```
AI_MT-Service/
├── run.py                      # Single entry point: python run.py
├── pipeline.py                 # Orchestrator: coordinates all stages
├── poller.py                   # GitHubAdapter (refactored from current)
├── diff_analyzer.py            # NEW: C diff parsing, signature extraction
├── testcase_generator.py       # Stage 1: LLM test case design (refactored)
├── testcase_parser.py          # NEW: markdown → structured data (IR)
├── code_generator.py           # NEW: structured data → C code via templates
├── c_validator.py              # NEW: post-generation C code validation
├── glm_client.py               # LLM client (kept, VIO removed)
├── templates/                  # C code templates
│   ├── cantata_test.c.j2       # Main test script template
│   ├── cantata_header.h.j2     # Header file template
│   ├── test_function.c.j2      # Per-function test implementation template
│   └── coverage_rules.c.j2     # Coverage analysis template
├── generated_tests/            # Output directory (existing)
├── .env                        # Configuration
├── processed_prs.json          # State tracking
└── requirements.txt            # Dependencies
```

### Structure Rationale

- **`templates/`**: Separates C code templates from Python logic. When Cantata syntax changes, edit templates, not Python. Use Jinja2 for complex conditional logic (struct vs array vs primitive handling).
- **`testcase_parser.py`**: Single responsibility — parse markdown tables into dicts. This is the most critical new component because it eliminates the LLM data transfer problem.
- **`code_generator.py`**: Takes structured data, emits C code. No LLM involvement. Pure deterministic transformation.
- **`c_validator.py`**: Post-generation sanity check. Catches `arr[] = 0` and `func(arr[])` before files are written.
- **`diff_analyzer.py`**: Extracts function signatures with full type information (not just regex matching). Provides the type context that templates need.

---

## Architectural Patterns

### Pattern 1: Deterministic Intermediate Representation (IR)

**What:** Parse LLM output into structured Python data (list of dicts) BEFORE any code generation. The IR is the single source of truth for all downstream steps.

**When to use:** Any pipeline where an LLM generates structured data that must be faithfully reproduced in a different format.

**Trade-offs:** Adds a parsing step but eliminates the "LLM drops data" class of bugs entirely. The parser must be robust against LLM output format variations.

**Example:**
```python
# testcase_parser.py — the critical new component

@dataclass
class TestCase:
    id: str
    function_name: str
    scenario: str
    input_values: Dict[str, str]     # {"arr": "{1,2,3,4}", "size": "4"}
    expected_result: str             # "10"
    test_type: str                   # "boundary"
    pre_conditions: str
    post_conditions: str

def parse_markdown_table(markdown: str) -> List[TestCase]:
    """Parse LLM markdown output into structured TestCase objects."""
    rows = extract_table_rows(markdown)
    test_cases = []
    for row in rows:
        tc = TestCase(
            id=row.get("Test Case ID", ""),
            function_name=row.get("Function Name", ""),
            scenario=row.get("Test Scenario", ""),
            input_values=parse_input_values(row.get("Input Values", "")),
            expected_result=parse_expected(row.get("Expected Result", "")),
            test_type=row.get("Test Type", ""),
            pre_conditions=row.get("Pre-Conditions", ""),
            post_conditions=row.get("Post-Conditions", ""),
        )
        test_cases.append(tc)
    return test_cases

def parse_input_values(raw: str) -> Dict[str, str]:
    """Parse 'arr={1,2,3,4}, size=4' into {'arr': '{1,2,3,4}', 'size': '4'}"""
    # Handle array values: arr={1,2,3,4}
    # Handle simple values: size=4
    # Handle string values: input="hello"
    result = {}
    # Split on commas but not commas inside braces
    parts = re.split(r',\s*(?![^{]*})', raw)
    for part in parts:
        if '=' in part:
            key, val = part.split('=', 1)
            result[key.strip()] = val.strip()
    return result
```

### Pattern 2: Template-Driven Code Generation (No LLM in Stage 2)

**What:** Generate C code from the IR using Jinja2 templates. The LLM is completely removed from the code generation step.

**When to use:** When the output format is well-defined (C code, Cantata test scripts) and the input data is already structured.

**Trade-offs:** Templates must cover all C type patterns (arrays, structs, pointers, etc.). Initial template development is more work than "ask the LLM", but the output is deterministic and debuggable. Template fixes are permanent — prompt fixes are not.

**Example:**
```python
# code_generator.py

from jinja2 import Environment, FileSystemLoader

def generate_c_test(test_cases: List[TestCase], signatures: Dict, pr_number: str) -> str:
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('cantata_test.c.j2')
    
    return template.render(
        test_cases=test_cases,
        signatures=signatures,
        pr_number=pr_number,
        module_name=f"module_{pr_number}",
    )
```

```c
{# templates/test_function.c.j2 #}
{% for tc in test_cases %}
void test_{{ tc.function_name }}_{{ loop.index }}() {
    TEST_SCRIPT_INFO("Executing test: {{ tc.scenario }}\\n");
    
    {% for var, val in tc.input_values.items() %}
    {% if val.startswith('{') %}
    {# Array initialization #}
    int {{ var }}[] = {{ val }};
    int {{ var }}_size = sizeof({{ var }}) / sizeof({{ var }}[0]);
    {% elif val.startswith('"') %}
    {# String initialization #}
    char {{ var }}[] = {{ val }};
    {% else %}
    {# Scalar initialization #}
    int {{ var }} = {{ val }};
    {% endif %}
    {% endfor %}
    
    {% if signatures[tc.function_name].return_type != 'void' %}
    int result = {{ tc.function_name }}({{ tc.input_values.keys() | join(', ') }});
    if (result != {{ tc.expected_result }}) {
        TEST_SCRIPT_ERROR("FAILED: expected %d, got %d\\n", {{ tc.expected_result }}, result);
    }
    {% else %}
    {{ tc.function_name }}({{ tc.input_values.keys() | join(', ') }});
    {# State validation for void functions #}
    {% endif %}
}
{% endfor %}
```

### Pattern 3: Post-Generation Validation Gate

**What:** After generating C code, run deterministic validation checks before writing files. Catch the exact class of bugs that the current system produces.

**When to use:** When the output must compile on first try and manual inspection isn't practical.

**Trade-offs:** Adds a small delay. Validation rules must be maintained as new edge cases are discovered. But catching `arr[] = 0` automatically is worth any cost.

**Example:**
```python
# c_validator.py

def validate_c_code(c_code: str) -> List[str]:
    """Return list of errors found. Empty list = valid."""
    errors = []
    
    # Check 1: No zero-initialized arrays (the primary bug)
    if re.search(r'\w+\[\]\s*=\s*0\s*;', c_code):
        errors.append("FATAL: Array initialized to 0 (data loss detected)")
    
    # Check 2: No bracket-in-function-call (arr[] in call)
    if re.search(r'\w+\(\s*\w+\[\]\s*,', c_code):
        errors.append("FATAL: Array brackets in function call argument")
    
    # Check 3: All variables declared before use
    declarations = set(re.findall(r'(?:int|char|float|double|void|FILE\*)\s+(\w+)', c_code))
    usages = set(re.findall(r'(?<!\w)([a-zA-Z_]\w*)\s*[=\[]', c_code))
    undeclared = (usages - declarations) - {'main', 'printf', 'TEST_SCRIPT_INFO', ...}
    if undeclared:
        errors.append(f"Undeclared variables: {undeclared}")
    
    # Check 4: No void return assignments
    if re.search(r'int\s+result\s*=\s*\w+\(.*\).*;\s*//\s*void\s+return', c_code):
        errors.append("FATAL: Void function assigned to result variable")
    
    return errors
```

### Pattern 4: Single Entry Point (Merge Poller + Workflow)

**What:** One `run.py` that does everything: poll GitHub → download diff → generate tests → output C files.

**When to use:** When the user runs this manually and wants one command, not two sequential scripts.

**Trade-offs:** Less flexibility for partial re-runs. Mitigated by adding `--stage` flags for debugging.

---

## Data Flow

### Primary Pipeline (Diff → Compilable C)

```
[GitHub PR with 'ai-test' label]
        ↓
[GitHubAdapter] → fetch diff → pr_{N}.diff
        ↓
[DiffAnalyzer] → extract signatures, types, structs → FuncSignature[]
        ↓
[TestCaseDesigner] → LLM(PROMPT_1 + diff) → markdown table
        ↓                              (raw LLM text)
[TestCaseParser] → parse markdown → List[TestCase]  ← IR / SINGLE SOURCE OF TRUTH
        ↓                              (structured Python data)
[CCodeGenerator] → templates + IR → .c file + .h file
        ↓                              (raw C code text)
[CValidator] → syntax checks → validated .c file + .h file
        ↓
[File Storage] → write to generated_tests/
        ↓
[GitHubAdapter] → remove 'ai-test' label from PR
```

### Critical Data Preservation Point

The **TestCaseParser** is the architectural linchpin. It converts:
```
LLM markdown: "arr={1,2,3,4}, size=4, expected=10"
         ↓
Python IR:    {"arr": "{1,2,3,4}", "size": "4", "expected": "10"}
         ↓
Template C:   int arr[] = {1,2,3,4}; int size = 4;
```

Without the parser, the LLM would see the markdown and "interpret" it, losing the actual values. With the parser, values flow deterministically from markdown → Python dict → C template.

### Key Data Flows

1. **Signature extraction flow:** `diff text → DiffAnalyzer → {func_name: {return_type, params: [{name, type}]}}` — This must be accurate because templates use these types to decide variable declarations.

2. **Test case flow:** `diff text → LLM → markdown → TestCaseParser → List[TestCase]` — The IR preserves every value exactly as the LLM specified.

3. **Code generation flow:** `List[TestCase] + FuncSignatures → CCodeGenerator → C code` — Pure template expansion, zero LLM involvement.

4. **Validation flow:** `C code → CValidator → errors[]` — If errors found, the pipeline either retries (re-prompt LLM for Stage 1) or reports for manual fix.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| GitHub API | REST via `requests` library | Token auth via `.env`. Rate limits: 5000/hr authenticated |
| GLM 4.7 Flash | Subprocess → `opencode` CLI | 600s timeout. Prompt via temp file, response via stdout |
| Cantata v24.04 | File-based (generate .c files it can compile) | MSVC17 compiler, `cantpp.h` headers, 100% coverage rules |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| GitHubAdapter ↔ Orchestrator | Function calls, return diff text | Adapter handles all GitHub API details |
| DiffAnalyzer ↔ Orchestrator | Function calls, return signature dicts | Pure computation, no I/O |
| TestCaseDesigner ↔ LLM Client | Function call, string in/string out | Only component that calls LLM |
| TestCaseParser ↔ Orchestrator | Function call, markdown in/List[TestCase] out | Critical boundary — no LLM beyond this point |
| CCodeGenerator ↔ Templates | Jinja2 render | Templates are data files, not Python code |
| CValidator ↔ Orchestrator | Function call, C code in/errors out | Returns empty list on success |

---

## Anti-Patterns

### Anti-Pattern 1: LLM-as-Code-Generator (CURRENT BUG)

**What people do:** Ask the LLM to convert structured data (markdown table) into C code in one shot.
**Why it's wrong:** LLMs are pattern completers, not compilers. They "summarize" array values into `0`, drop struct field initializations, and invent syntax. GLM 4.7 Flash specifically struggles with maintaining exact numeric values across a long context window.
**Do this instead:** LLM generates *definitions* (human-readable intent), Python code *compiles* those definitions into C (deterministic templates). The LLM never sees C syntax.

### Anti-Pattern 2: Regex-Based Value Extraction from Freeform Text

**What people do:** Use regex like `r'==\s*([-\d.]+)'` to extract expected values from natural language descriptions like "CHECK: return value equals 5".
**Why it's wrong:** The LLM might say "result should be 10", "returns ten", "expected: 10", or a dozen other phrasings. Regex can't handle this reliably.
**Do this instead:** The LLM output format must be constrained to machine-parseable columns. The `PROMPT_1` already specifies markdown table format — the parser must be built to handle that specific format, not free-form text.

### Anti-Pattern 3: Competing Implementations

**What people do:** Have `testcase_generator.py` AND `cantata_integration.py` both trying to generate C code, with `workflow.py` importing both and choosing dynamically.
**Why it's wrong:** Two implementations = two sets of bugs. `cantata_integration.py` has regex-based value extraction that defaults to `'0'`. `testcase_generator.py` has LLM-based code gen that also loses values. Neither works.
**Do this instead:** One code generation path: `testcase_parser.py` → `code_generator.py` → `c_validator.py`. Remove the dead `cantata_integration.py` path entirely.

### Anti-Pattern 4: Side Effects on Import

**What people do:** Every module calls `load_dotenv()` and `print()` at module level.
**Why it's wrong:** Makes unit testing impossible. Importing `testcase_generator.py` to test the parser would trigger LLM client initialization and print statements.
**Do this instead:** Move `load_dotenv()` to `run.py` entry point only. Use dependency injection or lazy initialization for LLM clients.

---

## Build Order (Dependencies Between Components)

This ordering reflects what must exist before other things can work:

```
Phase 1: Foundation (no dependencies)
  ├── testcase_parser.py     # Pure markdown→IR parsing. Test with sample markdown.
  ├── diff_analyzer.py       # Pure C diff→signatures parsing. Test with sample diffs.
  └── c_validator.py         # Pure C code validation. Test with known-bad C code.

Phase 2: Code Generation (depends on Phase 1 IR format)
  ├── templates/             # Jinja2 templates, driven by IR shape from Phase 1
  └── code_generator.py      # Template renderer, depends on IR + templates

Phase 3: Integration (depends on Phase 1 + 2)
  ├── pipeline.py            # Orchestrates all stages. Depends on every component.
  └── run.py                 # CLI entry point. Depends on pipeline.py.

Phase 4: Cleanup (depends on Phase 3 working)
  ├── Remove cantata_integration.py  # Dead code removal
  ├── Remove vio_llm_client.py       # Dead code removal
  ├── Remove vio_config.py           # Dead code removal
  └── Refactor poller.py             # Side-effect cleanup
```

### Build Order Rationale

1. **TestCaseParser first** because it defines the IR shape that everything else depends on. Get the data model right before building templates.
2. **DiffAnalyzer and CValidator in parallel** because they're independent. DiffAnalyzer provides the type information that templates need. CValidator provides the safety net.
3. **Templates + CodeGenerator** depend on the IR format being finalized. Build after TestCaseParser is tested.
4. **Pipeline + run.py** last because they wire everything together.

### Critical Interface: TestCase IR

The most important design decision is the shape of the TestCase dataclass. Everything else flows from this:

```python
@dataclass
class ParameterInit:
    """How a single parameter is initialized in C code."""
    c_type: str          # "int", "int[]", "char[]", "struct Queue", "FILE*"
    name: str            # "arr", "size", "queue_var"
    init_expression: str # "{1,2,3,4}", "4", '{"hello"}', etc.
    
@dataclass 
class FuncSignature:
    """A C function signature extracted from diff."""
    return_type: str     # "int", "void", "float"
    name: str            # "sumPositive"
    params: List[Tuple[str, str]]  # [(type, name), ...]
    raw_signature: str   # "int sumPositive(int arr[], int size)"

@dataclass
class TestCase:
    """A single test case parsed from LLM markdown output."""
    id: str                              # "TC_001"
    function_name: str                   # "sumPositive"
    scenario: str                        # "Normal case with positive numbers"
    params: List[ParameterInit]          # Parsed input values with types
    expected_result: str                 # "10" 
    assertion_type: str                  # "return_value", "state_check", "pointer_null"
    test_type: str                       # "normal", "edge", "boundary", "negative"
```

---

## Scaling Considerations

This is a single-user CLI tool. Scaling concerns are not about users but about **diff complexity**:

| Diff Complexity | Architecture Adjustments |
|-----------------|--------------------------|
| Simple functions (1-3 params, primitives) | Current architecture handles this fine |
| Array functions (5+ element arrays) | **This is where the current system breaks**. Templates must handle array initialization correctly |
| Struct-based functions | Templates need struct field initialization. DiffAnalyzer must extract struct definitions from diff context |
| Multi-file PRs (10+ functions) | Pipeline processes functions sequentially. No change needed — LLM calls are the bottleneck, not template rendering |
| Large diffs (1000+ lines) | DiffAnalyzer should split into per-function chunks. Each function gets its own test generation cycle |

### Scaling Priorities

1. **First bottleneck:** LLM timeout on large diffs (600s limit). Fix: truncate diffs to changed functions only.
2. **Second bottleneck:** Template coverage — new C types not handled by templates. Fix: add templates incrementally as new types are encountered.

---

## Migration Path from Current Architecture

### What to Keep
- `glm_client.py` — LLM client works fine (after removing VIO code)
- `poller.py` GitHub polling logic — rename GitHubAdapter, clean side effects
- `testcase_generator.py` PROMPT_1 — the Stage 1 prompt produces good results
- `.env` configuration pattern
- `generated_tests/` directory structure

### What to Replace
- `cantata_integration.py` → `code_generator.py` + `templates/` (template-based, deterministic)
- `testcase_generator.py` Stage 2 → `testcase_parser.py` + `code_generator.py` (parser + templates)
- `workflow.py` → `pipeline.py` (orchestrator, single-responsibility)
- Two entry points (`poller.py` + `workflow.py`) → `run.py` (single command)

### What to Delete
- `vio_llm_client.py` — VIO LLM is removed per requirements
- `vio_config.py` — VIO configuration
- `test_Vio_llm.py` — VIO connectivity test
- `test_format.py` — replaced by `c_validator.py`

---

## Sources

- Codebase analysis of all 9 Python files (2026-04-24)
- Cantata v24.04 infrastructure map at `C:\LegacyApp\qa_systems\`
- PR #167 test case demonstrating the data loss: markdown shows `arr={1,2,3,4}` but generated C has `int arr[] = 0`
- Python `dataclasses` module for IR definition (stdlib, no new dependency)
- Jinja2 templating engine for C code generation (single new dependency)

---
*Architecture research for: AI-powered Cantata C test generator*
*Researched: 2026-04-24*
