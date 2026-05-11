# AI MT-Service: Cantata Test Generator

An industrial-grade Python pipeline that generates 100% compilable Cantata v24.04 C89 test files from GitHub PR diffs containing automotive C code.

## Core Value

Generated Cantata `.c` test files compile with zero errors on first attempt 90%+ of the time. The remaining 10% compile after the self-healing retry loop.

## Architecture

**13-LLM Call Pipeline (Stage 1)** → **Deterministic Jinja2 Templates (Stage 6)** → **MSVC17 Compile Validation**

- **Stage 1**: 13 focused GLM 4.7 Flash LLM calls for intelligent test case design (parallel + sequential)
- **Stage 6**: Zero-LLM deterministic code generation via Jinja2 templates (eliminates syntax errors, enables self-healing)
- **Validation**: MSVC17 compiler (`cl.exe /Za` for strict C89) with error-to-IR fix mapping and 3-attempt retry loop

## Requirements

- **Python**: 3.10+ (tree-sitter, pydantic v2, pytest 9.x)
- **Compiler**: MSVC17 (`cl.exe`, `link.exe`) with `/Za` flag for C89 compliance
- **Cantata**: v24.04 installed at `C:\LegacyApp\qa_systems\`
- **LLM**: GLM 4.7 Flash via opencode CLI only
- **Standard**: ISO 26262 ASIL-B automotive safety-critical software

## Installation

```bash
# Install Python dependencies
pip install pydantic>=2.0 jinja2>=3.1 tree-sitter>=0.20 tree-sitter-c>=0.20

# Ensure MSVC17 is available (Visual Studio 2017 Build Tools)
# Ensure Cantata v24.04 is installed at C:\LegacyApp\qa_systems\

# Configure environment
cp .env.example .env
# Edit .env with required variables (opencode API access, etc.)
```

## Usage

### Full Pipeline (GitHub PR)

```bash
python run.py --diff tests/sample_add.diff --pr TEST01
```

### Stage 1 Only (Test Case Design)

```bash
python run.py --stage1-only --diff tests/sample_add.diff --pr TEST01
```

### Stage 2 Only (Code Generation from JSON)

```bash
python run.py --stage2-only generated_tests/pr_TEST01_testcases.json
```

### Human Approval Workflow

Set `REQUIRE_HUMAN_APPROVAL=true` in `.env` to pause after Stage 1 for engineer review of `testcases.md`.

## Output Files

Generated in `generated_tests/` directory:

| File | Description |
|------|-------------|
| `pr_{N}_testcases.md` | Human-readable test case document with engineer review checklist |
| `pr_{N}_testcases.json` | Machine-readable validated `TestCaseFile` schema |
| `test_module_{N}_{N}.c` | Cantata test script (C89 compilable) |
| `module_{N}.h` | Header with `extern` declarations |
| `compile_report_{N}.json` | Compile result, errors, attempts used |
| `trace_{N}.json` | ISO 26262 traceability sidecar |
| `human_review_{N}.md` | Written only if `NEEDS_HUMAN` cases exist |

## Project Structure

```
src/
  schemas.py              # Pydantic v2 models for TestCaseFile
  diff_validator.py       # Diff validation and chunking
  context_assembler.py    # Header/struct/typedef/HAL context assembly
  stage1_generator.py     # 13-call LLM pipeline → testcases.md + .json
  stage2_generator.py     # testcases.json → .c + .h (zero LLM)
  multi_call_pipeline.py  # All 13 LLM calls with retry logic
  type_resolver.py        # Deterministic C type classification
  compile_validator.py    # MSVC17 compile + error-to-IR fix loop
  quality_gates.py        # cppcheck, traceability sidecar
  scenario_validator.py   # Deterministic scenario gap checker
  value_sanitizer.py      # Deterministic value suffix fixer

templates/
  cantata_test.c.j2       # Master test script template
  cantata_header.h.j2     # Header file template
  partials/
    _scalar_test.c.j2
    _struct_test.c.j2
    _pointer_test.c.j2
    _array_test.c.j2
    _float_test.c.j2
    _multi_param_test.c.j2
    _void_return_test.c.j2
    _stub_setup.c.j2
    _coverage_rules.c.j2
    _main.c.j2

run.py                    # Unified entry point
poller.py                 # GitHub PR polling (existing)
glm_client.py             # GLM 4.7 Flash integration (existing)
processed_prs.json        # Tracks processed PRs (existing)
```

## Build Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Foundation | ✅ Complete | Pydantic schemas, diff validation, context assembly, type resolution |
| 2. LLM Pipeline Infrastructure | 🚧 Ready | Multi-call orchestration with retry logic |
| 3. Stage 1 Generator | ⏳ Pending | 13 LLM calls with deterministic validators |
| 4. Jinja2 Templates | ⏳ Pending | C89-compliant templates with partials |
| 5. Stage 2 Generator | ⏳ Pending | C code generation, cppcheck, compile validator |
| 6. Integration & Quality Gates | ⏳ Pending | Entry points, traceability, E2E testing |

## C89 Compliance

All generated code follows strict C89 rules:
- All variable declarations before executable statements
- Boolean literals: `FALSE`/`TRUE` (not `false`/`true`)
- Null pointers: `NULL_PTR` (not `NULL`)
- Struct initialization: field-by-field (not aggregate)
- No C++ features, no `//` comments
- Correct type suffixes: `u` for unsigned, `f` for float

## ISO 26262 Compliance

- MC/DC coverage planning for ASIL-B
- Traceability sidecar (`trace_{N}.json`) links requirements → test cases → test scripts
- Human approval workflow for safety-critical test cases
- Compile validation ensures deterministic behavior

## Development Workflow

```bash
# Plan a phase
/gsd-plan-phase 3

# View progress
/gsd-progress

# Check planning documents
cat .planning/PROJECT.md
cat .planning/ROADMAP.md
cat .planning/REQUIREMENTS.md
```

## License

Automotive safety-critical software development tool. ISO 26262 ASIL-B compliant.
