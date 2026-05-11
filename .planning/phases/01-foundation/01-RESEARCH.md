# Phase 1: Foundation - Research

**Researched:** 2026-04-28
**Status:** Complete

## Standard Stack

### Core Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.10"
pydantic = "^2.0"
pydantic-validation = "^2.0"
tree-sitter = "^0.20"
tree-sitter-c = "^0.20"

[tool.poetry.dev-dependencies]
pytest = "^9.0"
pytest-cov = "^4.0"
```

### Rationale

- **Python 3.10+**: Required for tree-sitter bindings, Pydantic v2 features, and modern type hints
- **Pydantic v2**: Significant performance improvements over v1, better validation, required by Tasks.md specification
- **tree-sitter-c**: Robust C parsing with AST query capabilities, better than regex for extracting function signatures
- **pytest 9.x**: Latest version with modern fixtures and parametrize features

### External Tools

- **cppcheck**: Static analysis for C code (system install, not pip)
- **cl.exe**: MSVC17 compiler for C89 compliance verification (Windows only, at `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\`)

## Architecture Patterns

### Pattern 1: Pydantic v2 Schema Design

**Purpose:** Define data contracts that validate test case structure at load time, catching errors before they reach the LLM pipeline.

**Implementation Pattern:**

```python
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Dict, List, Optional

class TestType(str, Enum):
    """Valid test scenario types."""
    NORMAL = "normal"
    BOUNDARY_MIN = "boundary_min"
    BOUNDARY_MAX = "boundary_max"
    NULL_PTR = "null_ptr"
    NEGATIVE = "negative"
    OVERFLOW = "overflow"
    FAULT_INJECTION = "fault_injection"

class StubConfig(BaseModel):
    """Cantata stub configuration for a single HAL function."""
    return_value: str = Field(..., description="C literal value stub should return")
    expected_call_count: int = Field(default=1, ge=0, description="Expected invocation count")
    output_params: Dict[str, str] = Field(default_factory=dict, description="Output param values set via pointer")

class TestCase(BaseModel):
    """A single test case scenario."""
    scenario_id: str = Field(..., pattern=r"^S\d{3}$", description="Unique scenario ID (S001, S002...)")
    function_name: str = Field(..., description="Function under test")
    scenario: str = Field(..., description="Human-readable scenario description")
    test_type: TestType = Field(..., description="Type of test scenario")
    inputs: Dict[str, str | Dict[str, str]] = Field(..., description="Input parameter values (scalars or struct fields)")
    expected_return: str = Field(..., description="Expected return value as C literal")
    expected_output_params: Dict[str, str] = Field(default_factory=dict, description="Output param values to check")
    stubs: Dict[str, StubConfig] = Field(default_factory=dict, description="Cantata stub configurations")
    asil_level: str = Field(default="ASIL_B", description="ISO 26262 ASIL level")
    requirement_ref: str = Field(default="", description="Requirement this test covers")
    needs_human_review: bool = Field(default=False, description="Requires engineer review")
    human_review_reason: Optional[str] = Field(default=None, description="Why human review is needed")

    @field_validator('expected_return')
    @classmethod
    def reject_vague_expected_return(cls, v: str) -> str:
        """Reject vague expected_return values."""
        vague = {'depends', 'varies', 'unknown', 'tbd', 'n/a'}
        if v.lower().strip() in vague:
            raise ValueError(f"expected_return must be concrete, not '{v}'")
        return v

class FunctionMeta(BaseModel):
    """Metadata for a single function under test."""
    signature: str = Field(..., description="Full C function signature")
    return_type: str = Field(..., description="C return type")
    description: str = Field(..., description="Plain English description of what function does")
    asil_level: str = Field(default="ASIL_B", description="ISO 26262 ASIL level")

class TestCaseFile(BaseModel):
    """Complete test case file containing all functions and test cases."""
    version: str = Field(default="1.0", description="Schema version")
    pr_number: str = Field(..., description="GitHub PR number")
    module_name: str = Field(..., description="Module name being tested")
    generated_at: str = Field(..., description="ISO 8601 timestamp")
    functions: Dict[str, FunctionMeta] = Field(..., description="All functions under test")
    test_cases: List[TestCase] = Field(..., description="All test cases")
    hal_stubs: List[str] = Field(default_factory=list, description="All HAL functions that need stubs")

    def validate_internal_consistency(self) -> List[str]:
        """Cross-field validation: ensure test cases reference valid functions and stubs."""
        errors = []

        # Check: every test function_name exists in functions dict
        for tc in self.test_cases:
            if tc.function_name not in self.functions:
                errors.append(f"Test {tc.scenario_id}: function '{tc.function_name}' not in functions dict")

        # Check: every stub in hal_stubs is actually used
        used_stubs = set()
        for tc in self.test_cases:
            used_stubs.update(tc.stubs.keys())
        unused_stubs = set(self.hal_stubs) - used_stubs
        if unused_stubs:
            errors.append(f"hal_stubs contains unused functions: {unused_stubs}")

        # Check: no duplicate scenario_ids
        scenario_ids = [tc.scenario_id for tc in self.test_cases]
        duplicates = [sid for sid in set(scenario_ids) if scenario_ids.count(sid) > 1]
        if duplicates:
            errors.append(f"Duplicate scenario_ids: {duplicates}")

        return errors

    @field_validator('test_cases')
    @classmethod
    def unique_scenario_ids(cls, v: List[TestCase]) -> List[TestCase]:
        """Ensure scenario_ids are unique."""
        ids = [tc.scenario_id for tc in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate scenario_ids detected")
        return v
```

**Key Points:**
- Use `field_validator` (Pydantic v2) instead of `validator` (Pydantic v1)
- Use `Field` for all field descriptions and constraints
- Enum for constrained string values (TestType)
- `validate_internal_consistency()` is a method, not a validator, because it needs access to multiple fields

### Pattern 2: Diff Validation

**Purpose:** Reject invalid diffs early and split large diffs by function boundary to keep LLM context manageable.

**Implementation Pattern:**

```python
import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DiffChunk:
    """A chunk of diff text split by function boundary."""
    chunk_id: int
    start_line: int
    end_line: int
    content: str
    function_names: List[str]

class DiffValidator:
    """Validates and chunks GitHub PR unified diffs."""

    # Patterns for unified diff format
    DIFF_HEADER_RE = re.compile(r'^diff --git a/(.+) b/(.+)$')
    HUNK_HEADER_RE = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
    FUNCTION_DEF_RE = re.compile(r'^(?P<return_type>\w[\w\s*]+?)\s+(?P<name>\w+)\s*\(')

    def __init__(self, max_lines: int = 300):
        self.max_lines = max_lines

    def validate(self, diff_text: str) -> None:
        """Validate diff format and reject empty/non-C diffs."""
        if not diff_text or not diff_text.strip():
            raise ValueError("Diff is empty")

        # Check for unified diff markers
        if not re.search(r'^diff --git', diff_text, re.MULTILINE):
            raise ValueError("Not a unified diff (missing 'diff --git' header)")

        if not re.search(r'^@@', diff_text, re.MULTILINE):
            raise ValueError("Not a unified diff (missing '@@' hunk headers)")

        # Heuristic: check for C code indicators
        c_indicators = [r'\.c\b', r'\.h\b', r'#include', r'int\s+\w+', r'void\s+\w+\(']
        has_c = any(re.search(pattern, diff_text, re.IGNORECASE) for pattern in c_indicators)
        if not has_c:
            raise ValueError("Diff does not appear to contain C code")

    def chunk_by_function(self, diff_text: str) -> List[DiffChunk]:
        """Split diff > max_lines by function boundary."""
        lines = diff_text.split('\n')

        if len(lines) <= self.max_lines:
            return [DiffChunk(0, 1, len(lines), diff_text, [])]

        chunks = []
        current_chunk_lines = []
        current_functions = []
        chunk_id = 0
        start_line = 1

        for i, line in enumerate(lines, 1):
            current_chunk_lines.append(line)

            # Detect function definition (simplified)
            func_match = self.FUNCTION_DEF_RE.match(line.lstrip('+-'))
            if func_match:
                func_name = func_match.group('name')
                current_functions.append(func_name)

                # Check if we should split here
                if len(current_chunk_lines) >= self.max_lines:
                    chunk = DiffChunk(
                        chunk_id=chunk_id,
                        start_line=start_line,
                        end_line=i,
                        content='\n'.join(current_chunk_lines),
                        function_names=current_functions.copy()
                    )
                    chunks.append(chunk)

                    # Reset for next chunk
                    chunk_id += 1
                    start_line = i + 1
                    current_chunk_lines = []
                    current_functions = []

        # Add final chunk if any remaining lines
        if current_chunk_lines:
            chunk = DiffChunk(
                chunk_id=chunk_id,
                start_line=start_line,
                end_line=len(lines),
                content='\n'.join(current_chunk_lines),
                function_names=current_functions
            )
            chunks.append(chunk)

        return chunks
```

**Key Points:**
- Use regex to validate unified diff format (diff --git, @@ hunk headers)
- Heuristic check for C code (.c/.h files, #include, function signatures)
- Function boundary detection is simplified — use tree-sitter in context_assembler for accuracy
- Split by function definition to keep LLM context under 300 lines

### Pattern 3: Context Assembly

**Purpose:** Extract function signatures, struct definitions, typedefs, macros, and HAL functions from diff using tree-sitter AST.

**Implementation Pattern:**

```python
from tree_sitter import Language, Parser
import tree_sitter_c
from dataclasses import dataclass
from typing import Dict, List, Set, Optional

@dataclass
class FunctionSignature:
    """Extracted C function signature."""
    name: str
    return_type: str
    parameters: List[Dict[str, str]]
    signature_string: str

@dataclass
class StructDefinition:
    """Extracted C struct definition."""
    name: str
    fields: Dict[str, str]

@dataclass
class ContextPackage:
    """Complete context extracted from diff."""
    diff_text: str
    function_signatures: Dict[str, FunctionSignature]
    struct_definitions: Dict[str, StructDefinition]
    typedef_map: Dict[str, str]  # alias -> base type
    macro_constants: Dict[str, str]  # name -> value
    hal_functions: Set[str]  # function names needing stubs

class ContextAssembler:
    """Extracts context from C diff using tree-sitter."""

    # HAL/RTE/Com function prefixes
    HAL_PREFIXES = {'HAL_', 'Rte_', 'Com_'}

    def __init__(self):
        # Initialize tree-sitter parser for C
        self.language = Language(tree_sitter_c.language())
        self.parser = Parser(self.language)

    def assemble(self, diff_text: str) -> ContextPackage:
        """Extract all context from diff."""
        # Parse diff as C code (tree-sitter can handle partial C)
        tree = self.parser.parse(diff_text.encode())

        function_signatures = self._extract_functions(tree)
        struct_definitions = self._extract_structs(tree)
        typedef_map = self._extract_typedefs(tree)
        macro_constants = self._extract_macros(tree)
        hal_functions = self._detect_hal_functions(tree)

        return ContextPackage(
            diff_text=diff_text,
            function_signatures=function_signatures,
            struct_definitions=struct_definitions,
            typedef_map=typedef_map,
            macro_constants=macro_constants,
            hal_functions=hal_functions
        )

    def _extract_functions(self, tree) -> Dict[str, FunctionSignature]:
        """Extract all function signatures from AST."""
        functions = {}

        # Query: function_definition nodes
        query = self.language.query("""
            (function_definition
                type: (type_identifier) @return_type
                declarator: (function_declarator
                    declarator: (identifier) @name
                    parameters: (parameter_list
                        (parameter_declaration
                            type: (type_identifier) @param_type
                            declarator: (identifier) @param_name
                        )*
                    ) @params
                )
            ) @func
        """)

        captures = query.captures(tree.root_node)

        # Group by function
        current_func = None
        for node, tag in captures:
            if tag == 'name':
                current_func = node.text.decode()
            elif tag == 'return_type':
                if current_func:
                    return_type = node.text.decode()
            elif tag == 'param_type':
                # Accumulate parameters...
                pass

        # Simplified: return dict with function names
        # Full implementation would build complete FunctionSignature objects
        return {}

    def _extract_structs(self, tree) -> Dict[str, StructDefinition]:
        """Extract struct definitions from AST."""
        structs = {}

        query = self.language.query("""
            (struct_specifier
                name: (type_identifier) @name
                body: (field_declaration_list
                    (field_declaration
                        type: (type_identifier) @field_type
                        declarator: (field_identifier) @field_name
                    )*
                )
            ) @struct
        """)

        # Process captures...
        return {}

    def _extract_typedefs(self, tree) -> Dict[str, str]:
        """Extract typedef statements."""
        typedefs = {}

        query = self.language.query("""
            (type_definition
                type: (type_identifier) @alias
                declarator: (type_identifier) @base_type
            )
        """)

        # Process captures...
        return {}

    def _extract_macros(self, tree) -> Dict[str, str]:
        """Extract #define constants."""
        # tree-sitter doesn't parse preprocessor directives well
        # Use regex as fallback
        macros = {}

        macro_re = re.compile(r'^#define\s+(\w+)\s+(.+)$', re.MULTILINE)
        for match in macro_re.finditer(self.diff_text):
            name, value = match.groups()
            macros[name] = value.strip()

        return macros

    def _detect_hal_functions(self, tree) -> Set[str]:
        """Detect calls to HAL/RTE/Com functions."""
        hal_functions = set()

        query = self.language.query("""
            (call_expression
                function: (identifier) @func_name
            )
        """)

        captures = query.captures(tree.root_node)
        for node, tag in captures:
            if tag == 'func_name':
                name = node.text.decode()
                if any(name.startswith(prefix) for prefix in self.HAL_PREFIXES):
                    hal_functions.add(name)

        return hal_functions
```

**Key Points:**
- tree-sitter-c provides AST for accurate parsing (vs fragile regex)
- Query syntax: `(node_type child: (child_type) @capture_name)` to extract nodes
- Preprocessor directives (#define) not well-supported by tree-sitter — use regex fallback
- HAL function detection: look for calls with HAL_/Rte_/Com_ prefixes

### Pattern 4: Type Resolution

**Purpose:** Map C types to CType enum, resolve typedef chains, classify parameters, determine zero/null values.

**Implementation Pattern:**

```python
from enum import Enum
from typing import Dict, Optional, Tuple

class CType(Enum):
    """C type classification."""
    UINT8 = "UINT8"
    UINT16 = "UINT16"
    UINT32 = "UINT32"
    INT8 = "INT8"
    INT16 = "INT16"
    INT32 = "INT32"
    FLOAT = "FLOAT"
    DOUBLE = "DOUBLE"
    STRUCT = "STRUCT"
    POINTER = "POINTER"
    ARRAY = "ARRAY"
    BOOL = "BOOL"
    VOID = "VOID"
    UNKNOWN = "UNKNOWN"

class ParamClass(Enum):
    """Parameter classification for test generation."""
    SCALAR = "scalar"
    STRUCT = "struct"
    POINTER = "pointer"
    ARRAY = "array"
    FLOAT = "float"
    BOOL = "bool"

@dataclass
class TypeMetadata:
    """Metadata for a resolved C type."""
    c_type: CType
    param_class: ParamClass
    zero_value: str  # C literal for zero (e.g., "0u", "0.0f", "FALSE")
    null_value: Optional[str]  # C literal for null (e.g., "NULL_PTR") or None
    base_type: Optional[str]  # Resolved base type after typedef chain

class TypeResolver:
    """Resolves and classifies C types."""

    # AUTOSAR standard types
    AUTOSAR_TYPES = {
        'uint8': CType.UINT8, 'uint8_t': CType.UINT8,
        'uint16': CType.UINT16, 'uint16_t': CType.UINT16,
        'uint32': CType.UINT32, 'uint32_t': CType.UINT32,
        'int8': CType.INT8, 'int8_t': CType.INT8,
        'int16': CType.INT16, 'int16_t': CType.INT16,
        'int32': CType.INT32, 'int32_t': CType.INT32,
        'float32': CType.FLOAT, 'float': CType.FLOAT,
        'float64': CType.DOUBLE, 'double': CType.DOUBLE,
        'boolean': CType.BOOL, 'bool': CType.BOOL,
    }

    # Zero values per type (C89 compliant)
    ZERO_VALUES = {
        CType.UINT8: "0u", CType.UINT16: "0u", CType.UINT32: "0u",
        CType.INT8: "0", CType.INT16: "0", CType.INT32: "0",
        CType.FLOAT: "0.0f", CType.DOUBLE: "0.0",
        CType.BOOL: "FALSE",
        CType.POINTER: "NULL_PTR",
        CType.STRUCT: "",  # Structs require field-by-field init
        CType.ARRAY: "",  # Arrays require element-by-element init
        CType.VOID: "",
        CType.UNKNOWN: "0",
    }

    # Null values per type
    NULL_VALUES = {
        CType.POINTER: "NULL_PTR",
        # Other types don't have null values
    }

    def __init__(self, typedef_map: Dict[str, str]):
        self.typedef_map = typedef_map

    def resolve(self, c_type_str: str) -> TypeMetadata:
        """Resolve C type string to TypeMetadata."""
        # Normalize: remove const, handle pointers, resolve typedef
        normalized = c_type_str.strip()
        is_const = 'const' in normalized.lower()
        normalized = normalized.replace('const', '').strip()

        # Check for pointer
        if '*' in normalized:
            base = normalized.replace('*', '').strip()
            resolved_base = self._resolve_typedef(base)
            c_type = self._classify_string(resolved_base)
            if c_type == CType.STRUCT:
                return TypeMetadata(
                    c_type=CType.POINTER,
                    param_class=ParamClass.POINTER,
                    zero_value="NULL_PTR",
                    null_value="NULL_PTR",
                    base_type=resolved_base
                )
            else:
                return TypeMetadata(
                    c_type=CType.POINTER,
                    param_class=ParamClass.POINTER,
                    zero_value="NULL_PTR",
                    null_value="NULL_PTR",
                    base_type=resolved_base
                )

        # Check for array
        if '[' in normalized:
            base = normalized.split('[')[0].strip()
            resolved_base = self._resolve_typedef(base)
            c_type = self._classify_string(resolved_base)
            return TypeMetadata(
                c_type=CType.ARRAY,
                param_class=ParamClass.ARRAY,
                zero_value=self.ZERO_VALUES.get(c_type, ""),
                null_value=None,
                base_type=resolved_base
            )

        # Resolve typedef chain
        resolved = self._resolve_typedef(normalized)
        c_type = self._classify_string(resolved)

        # Classify parameter
        param_class = self._classify_param_class(c_type)

        return TypeMetadata(
            c_type=c_type,
            param_class=param_class,
            zero_value=self.ZERO_VALUES.get(c_type, "0"),
            null_value=self.NULL_VALUES.get(c_type),
            base_type=resolved,
        )

    def _resolve_typedef(self, type_str: str) -> str:
        """Recursively resolve typedef chain."""
        current = type_str
        visited = set()

        while current in self.typedef_map and current not in visited:
            visited.add(current)
            current = self.typedef_map[current]

        return current

    def _classify_string(self, type_str: str) -> CType:
        """Classify type string to CType enum."""
        return self.AUTOSAR_TYPES.get(type_str, CType.UNKNOWN)

    def _classify_param_class(self, c_type: CType) -> ParamClass:
        """Map CType to ParamClass."""
        if c_type in (CType.UINT8, CType.UINT16, CType.UINT32,
                      CType.INT8, CType.INT16, CType.INT32):
            return ParamClass.SCALAR
        elif c_type == CType.BOOL:
            return ParamClass.BOOL
        elif c_type in (CType.FLOAT, CType.DOUBLE):
            return ParamClass.FLOAT
        elif c_type == CType.STRUCT:
            return ParamClass.STRUCT
        elif c_type in (CType.POINTER, CType.ARRAY):
            return ParamClass.POINTER
        else:
            return ParamClass.SCALAR  # Default
```

**Key Points:**
- Resolve typedef chains recursively (MyType → uint8 → UINT8)
- Handle const qualifiers, pointers, arrays separately
- Zero values differ by type (0u for uint, 0.0f for float, FALSE for bool, NULL_PTR for pointers)
- Null values only apply to pointer types

## Don't Hand Roll

### Use These Libraries Instead

| Task | Use This | Don't Build |
|------|----------|-------------|
| AST parsing | tree-sitter-c | Custom regex parsers |
| Data validation | Pydantic v2 validators | Manual validation code |
| Type hints | Python 3.10+ typing module | Custom type checking |
| Testing | pytest fixtures/parametrize | Custom test framework |

### Why Not Hand-Roll?

- **tree-sitter-c**: Well-tested C parser, handles edge cases (nested structs, function pointers)
- **Pydantic v2**: Battle-tested validation, performance optimized, clear error messages
- **pytest 9.x**: Rich ecosystem, parallel execution, coverage integration

## Common Pitfalls

### Pitfall 1: Python Version Mismatch

**Problem:** Project requires Python 3.10+ but existing environment is 3.8.

**Detection:**
```bash
python --version  # Should be 3.10 or higher
```

**Fix:**
- Use pyenv or conda to create Python 3.10+ environment
- Update `.python-version` file if using pyenv
- Update `pyproject.toml` with `python = "^3.10"`

**Impact:** tree-sitter and Pydantic v2 will fail to install on Python < 3.10.

---

### Pitfall 2: tree-sitter Query Syntax Errors

**Problem:** Incorrect query syntax causes AST extraction to return no results.

**Example Bad Query:**
```
(function_definition (identifier) @name)  # Too generic
```

**Example Good Query:**
```
(function_definition
    type: (type_identifier) @return_type
    declarator: (function_declarator
        declarator: (identifier) @name
        parameters: (parameter_list) @params
    )
)
```

**Fix:**
- Test queries in tree-sitter playground: https://tree-sitter.github.io/tree-sitter/playground
- Use specific node types and capture names
- Group captures with `@capture_name`

---

### Pitfall 3: Typedef Chain Infinite Loop

**Problem:** Circular typedef definitions cause infinite loop.

**Example:**
```c
typedef MyType MyType;  // Self-referential
```

**Fix:**
- Track visited types in `_resolve_typedef()`
- Stop recursion when type revisited
- Return original type if loop detected

**Code:**
```python
def _resolve_typedef(self, type_str: str) -> str:
    current = type_str
    visited = set()

    while current in self.typedef_map and current not in visited:
        visited.add(current)
        current = self.typedef_map[current]

    return current  # Returns original if loop detected
```

---

### Pitfall 4: Missing Zero Value for Struct

**Problem:** Trying to use a single zero value for struct initialization.

**Wrong:**
```python
zero_value = "0"  # Won't work for structs
```

**Right:**
```python
# Structs require field-by-field initialization
# The zero_value is empty string; templates handle it
if c_type == CType.STRUCT:
    zero_value = ""  # Template will initialize each field
```

**Reason:** C89 requires field-by-field init for test code clarity.

---

### Pitfall 5: Diff Splitting Breaks Context

**Problem:** Splitting diff mid-function loses context for LLM.

**Wrong:**
```python
# Split by line count only
if len(lines) >= self.max_lines:
    split_here()
```

**Right:**
```python
# Split at function boundaries
if len(current_chunk_lines) >= self.max_lines:
    # Find next function definition and split there
    if self.FUNCTION_DEF_RE.match(next_line):
        split_here()
```

**Reason:** LLM needs complete function context for accurate test generation.

---

### Pitfall 6: Pydantic v1 vs v2 Syntax

**Problem:** Using Pydantic v1 syntax causes failures in v2.

**Wrong (v1):**
```python
from pydantic import BaseModel, validator

class TestCase(BaseModel):
    expected_return: str

    @validator('expected_return')
    def reject_vague(cls, v):
        if v.lower() in {'depends', 'varies'}:
            raise ValueError('Must be concrete')
        return v
```

**Right (v2):**
```python
from pydantic import BaseModel, field_validator

class TestCase(BaseModel):
    expected_return: str

    @field_validator('expected_return')
    @classmethod
    def reject_vague(cls, v: str) -> str:
        if v.lower() in {'depends', 'varies'}:
            raise ValueError('Must be concrete')
        return v
```

**Changes:**
- `@validator` → `@field_validator`
- Add `@classmethod`
- Add type hints to parameters and return

---

### Pitfall 7: Missing Struct Fields in Type Map

**Problem:** LLM generates struct inputs with fields not in actual struct definition → C2039 compile errors.

**Wrong:**
```python
# LLM generates inputs with any field
inputs = {
    "brake_actuator": {
        "pressure": "15000u",  # Not in actual struct!
        "is_engaged": "TRUE"
    }
}
```

**Right:**
```python
# Type map from struct_definition enforces valid fields
type_map = {
    "functions": {
        "apply_brake": {
            "params": {
                "actuator": {
                    "struct_fields": {
                        "is_engaged": "boolean",
                        "request_count": "uint16"
                        # NO "pressure" field
                    }
                }
            }
        }
    }
}
```

**Fix:** Context assembler must extract EXACT struct field names from AST, not guess.

---

### Pitfall 8: Wrong C Literal Suffixes

**Problem:** Missing 'u' suffix on uint or 'f' suffix on float causes C compiler warnings/errors.

**Wrong:**
```python
value = "15000"  # Missing 'u'
float_val = "3.14"  # Missing 'f'
```

**Right:**
```python
value = "15000u"  # Correct
float_val = "3.14f"  # Correct
```

**Fix:** Type resolver must return correct zero_value per type, and LLM prompts must enforce suffixes.

---

### Pitfall 9: NULL vs NULL_PTR

**Problem:** Using `NULL` instead of `NULL_PTR` breaks C89 compliance.

**Wrong:**
```python
null_value = "NULL"
```

**Right:**
```python
null_value = "NULL_PTR"  # Project-specific macro
```

**Reason:** Project uses `NULL_PTR` macro (likely defined in Cantata headers), not standard `NULL`.

---

### Pitfall 10: Pydantic Validation Happens Too Late

**Problem:** Running full LLM pipeline before validating schema wastes tokens on invalid data.

**Wrong:**
```
LLM Stage 1 → Stage 2 → ... → Stage 5 → Pydantic validate → FAIL
```

**Right:**
```
LLM Stage 1 → Validate → Stage 2 → Validate → ... → Stage 5 → Pydantic validate
```

**Fix:** Insert Pydantic validation after each stage in `multi_call_pipeline.py` (Phase 2).

## Architectural Responsibility Map

| Component | Owner | Depends On |
|-----------|-------|------------|
| `schemas.py` | Phase 1 | None (base foundation) |
| `diff_validator.py` | Phase 1 | None |
| `context_assembler.py` | Phase 1 | tree-sitter-c, schemas.py (for types) |
| `type_resolver.py` | Phase 1 | schemas.py (CType enum), context_assembler (typedef_map) |
| `multi_call_pipeline.py` | Phase 2 | schemas.py, context_assembler.py, type_resolver.py |

## Validation Architecture

### Dimension 1: Schema Validation

- **What:** Pydantic v2 validates TestCaseFile structure
- **Where:** After Stage 5 assembly, before Stage 6
- **How:** `TestCaseFile.model_validate_json(json_string)`
- **Pass Criteria:** No ValidationError, `validate_internal_consistency()` returns empty list

### Dimension 2: Diff Validation

- **What:** Diff format and content checks
- **Where:** Before LLM pipeline starts
- **How:** `DiffValidator.validate(diff_text)`
- **Pass Criteria:** No ValueError, diff recognized as C code

### Dimension 3: Type Consistency

- **What:** All struct fields in inputs exist in type_map
- **Where:** After Stage 3 (value assignment)
- **How:** Deterministic validator in `scenario_validator.py`
- **Pass Criteria:** No unknown struct fields

### Dimension 4: Boundary Value Validation

- **What:** Boundary scenarios use actual type boundaries
- **Where:** After Stage 3 (value assignment)
- **How:** Check against type_map valid_min/valid_max
- **Pass Criteria:** boundary_min ≤ valid_min, boundary_max ≥ valid_max

### Dimension 5: HAL Stub Completeness

- **What:** Every HAL function called by SUT is stubbed
- **Where:** After Stage 4 (stub configuration)
- **How:** Check hal_functions set vs stub_configs keys
- **Pass Criteria:** All HAL functions have stub configs

### Dimension 6: C89 Literal Compliance

- **What:** All C literals use correct suffixes
- **Where:** After Stage 3 (value assignment)
- **How:** Deterministic sanitizer in `value_sanitizer.py`
- **Pass Criteria:** uint has 'u', float has 'f', bool is FALSE/TRUE, ptr is NULL_PTR

### Dimension 7: Scenario Coverage

- **What:** Every function has at least one normal scenario
- **Where:** After Stage 2 (scenario design)
- **How:** Deterministic gap filler in `scenario_validator.py`
- **Pass Criteria:** Each function has test_type="normal" scenario

### Dimension 8: Internal Consistency

- **What:** Cross-field validation (function names, stub references)
- **Where:** After Stage 5 assembly
- **How:** `TestCaseFile.validate_internal_consistency()`
- **Pass Criteria:** Returns empty list

---

*Research complete: 2026-04-28*
*All patterns validated against Tasks.md specification*
