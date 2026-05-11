# Phase 1: Foundation - Pattern Map

**Generated:** 2026-04-28
**Purpose:** Extract file patterns from context to guide implementation

## Files to Create

From CONTEXT.md decisions and RESEARCH.md implementation patterns, Phase 1 creates these files:

### Data Models
- **src/schemas.py** — Pydantic v2 models (TestCaseFile, TestCase, FunctionMeta, StubConfig, TestType enum)

### Input Processing
- **src/diff_validator.py** — Diff validation and chunking (DiffValidator class, DiffChunk dataclass)

### Context Extraction
- **src/context_assembler.py** — AST-based context extraction (ContextAssembler class, FunctionSignature, StructDefinition, ContextPackage dataclasses)

### Type System
- **src/type_resolver.py** — C type classification (TypeResolver class, CType enum, ParamClass enum, TypeMetadata dataclass)

## File Classification by Role

| File | Role | Input | Output | Data Flow |
|------|------|-------|--------|-----------|
| `schemas.py` | Data contract definition | None | Pydantic model classes | N/A (defines types) |
| `diff_validator.py` | Input validator | Raw diff text | Validated chunks | Diff → Chunks |
| `context_assembler.py` | Context extractor | Diff text | ContextPackage | Diff → Signatures, Structs, Typedefs, Macros, HAL functions |
| `type_resolver.py` | Type classifier | C type strings, typedef_map | TypeMetadata | Type string → CType + metadata |

## Closest Existing Analogs

**Note:** Per decision D-01, existing code is archived to legacy/ and NOT reused. These analogs are for pattern reference only to understand file organization and structure.

### src/schemas.py → src/legacy/ir_models.py

**Why this analog:** Both define Pydantic models for the pipeline.

**Pattern from ir_models.py:**
```python
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union
from enum import Enum

class IRType(str, Enum):
    """Type classification enum."""
    SCALAR = "scalar"
    STRUCT = "struct"
    POINTER = "pointer"

class IRParameter(BaseModel):
    """Function parameter representation."""
    name: str
    ir_type: IRType
    c_type: str
    is_pointer: bool = False

class IRFunction(BaseModel):
    """Function representation."""
    name: str
    return_type: str
    parameters: List[IRParameter]
```

**Key pattern elements to replicate:**
- Use `str, Enum` for string enums
- Use `Field` for all field descriptions (even if default is omitted)
- Use type hints: `List[IRParameter]`, `Dict[str, str]`, `Optional[str]`
- Default values in Field(): `is_pointer: bool = False`
- Docstrings for each class

**Differences for new schemas.py:**
- Use Pydantic v2 syntax: `@field_validator` instead of `@validator`
- Add `@classmethod` to validators
- More complex models: TestCaseFile has cross-field validation method
- TestType enum has 7 values (not 3)

### src/diff_validator.py → src/legacy/signature_extractor.py

**Why this analog:** Both process input text and extract structured data.

**Pattern from signature_extractor.py:**
```python
import re
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class FunctionInfo:
    """Extracted function information."""
    name: str
    return_type: str
    parameters: Dict[str, str]

class SignatureExtractor:
    """Extracts function signatures from C code."""

    FUNCTION_PATTERN = re.compile(
        r'^(?P<return_type>[\w\s*]+?)\s+'
        r'(?P<name>\w+)\s*\('
        r'(?P<params>[^)]*)\)'
    )

    def __init__(self):
        self.functions: List[FunctionInfo] = []

    def extract(self, code: str) -> List[FunctionInfo]:
        """Extract all function signatures from code."""
        # Implementation...
        pass
```

**Key pattern elements to replicate:**
- Use `@dataclass` for simple data containers (DiffChunk)
- Use compiled regex patterns as class attributes: `PATTERN = re.compile(...)`
- Type hints on all methods and return types
- Class docstring + method docstrings
- List accumulation: `self.functions: List[...] = []`

**Differences for new diff_validator.py:**
- Two classes: `DiffValidator` and `DiffChunk` (dataclass)
- Validation logic: `validate()` raises ValueError
- Chunking logic: `chunk_by_function()` returns List[DiffChunk]
- Multiple regex patterns: diff header, hunk header, function definition

### src/context_assembler.py → src/legacy/signature_extractor.py

**Why this analog:** Both extract structured information from C code.

**Pattern from signature_extractor.py:**
```python
import re
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class FunctionInfo:
    name: str
    return_type: str
    parameters: Dict[str, str]

class SignatureExtractor:
    """Extracts function signatures from C code."""

    def __init__(self):
        self.functions: List[FunctionInfo] = []

    def extract(self, code: str) -> List[FunctionInfo]:
        """Extract all function signatures from code."""
        # Process code, extract functions
        return self.functions
```

**Key pattern elements to replicate:**
- Multiple dataclasses: FunctionSignature, StructDefinition, ContextPackage
- Main class with `assemble()` method returning dataclass
- Helper methods prefixed with `_`: `_extract_functions()`, `_extract_structs()`
- Type hints for complex return types: `Dict[str, FunctionSignature]`

**Differences for new context_assembler.py:**
- Uses tree-sitter-c instead of regex for AST parsing
- tree-sitter query syntax: `(node_type child: (child_type) @capture_name)`
- Multiple query results processed into dicts
- HAL function detection via prefix matching: `HAL_`, `Rte_`, `Com_`
- Macro extraction via regex (tree-sitter doesn't handle preprocessor)

### src/type_resolver.py → src/legacy/type_resolver.py

**Why this analog:** Both resolve and classify C types.

**Pattern from type_resolver.py:**
```python
from enum import Enum
from typing import Dict, Optional

class IRType(str, Enum):
    SCALAR = "scalar"
    STRUCT = "struct"
    POINTER = "pointer"

class TypeResolver:
    """Resolves and classifies C types."""

    AUTOSAR_TYPES = {
        'uint8': IRType.SCALAR,
        'uint16': IRType.SCALAR,
        'float': IRType.SCALAR,
    }

    def __init__(self, typedef_map: Dict[str, str]):
        self.typedef_map = typedef_map

    def resolve(self, c_type: str) -> IRType:
        """Resolve C type to IRType."""
        # Implementation...
        pass
```

**Key pattern elements to replicate:**
- Enum for classification: `CType`, `ParamClass`
- Dict for type lookup: `AUTOSAR_TYPES = {...}`
- Class attributes for constant values: `ZERO_VALUES = {...}`, `NULL_VALUES = {...}`
- Typedef chain resolution: recursive method with visited set
- Zero/null value lookup by type

**Differences for new type_resolver.py:**
- Two enums: `CType` (14 values) and `ParamClass` (6 values)
- More complex type metadata: `TypeMetadata` dataclass with 5 fields
- Recursive typedef resolution with loop detection
- Zero values differ by type (0u, 0.0f, FALSE, NULL_PTR, "")
- ParamClass classification: scalar, struct, pointer, array, float, bool
- Handling const qualifiers, pointers, arrays separately

## Code Excerpts for Reference

### Pydantic v2 Validator Pattern (for schemas.py)

```python
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Dict, List, Optional

class TestType(str, Enum):
    NORMAL = "normal"
    BOUNDARY_MIN = "boundary_min"
    # ... other values

class TestCase(BaseModel):
    scenario_id: str = Field(..., pattern=r"^S\d{3}$")
    expected_return: str

    @field_validator('expected_return')
    @classmethod
    def reject_vague(cls, v: str) -> str:
        vague = {'depends', 'varies', 'unknown', 'tbd'}
        if v.lower().strip() in vague:
            raise ValueError(f"expected_return must be concrete, not '{v}'")
        return v
```

### tree-sitter Query Pattern (for context_assembler.py)

```python
from tree_sitter import Language, Parser
import tree_sitter_c

class ContextAssembler:
    def __init__(self):
        self.language = Language(tree_sitter_c.language())
        self.parser = Parser(self.language)

    def _extract_functions(self, tree):
        query = self.language.query("""
            (function_definition
                type: (type_identifier) @return_type
                declarator: (function_declarator
                    declarator: (identifier) @name
                    parameters: (parameter_list) @params
                )
            ) @func
        """)
        captures = query.captures(tree.root_node)
        # Process captures into dict...
```

### Recursive Typedef Resolution (for type_resolver.py)

```python
def _resolve_typedef(self, type_str: str) -> str:
    """Recursively resolve typedef chain with loop detection."""
    current = type_str
    visited = set()

    while current in self.typedef_map and current not in visited:
        visited.add(current)
        current = self.typedef_map[current]

    return current  # Returns original if loop detected
```

### Regex Pattern Compilation (for diff_validator.py)

```python
class DiffValidator:
    # Compile patterns once at class level
    DIFF_HEADER_RE = re.compile(r'^diff --git a/(.+) b/(.+)$')
    HUNK_HEADER_RE = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
    FUNCTION_DEF_RE = re.compile(r'^(?P<return_type>\w[\w\s*]+?)\s+(?P<name>\w+)\s*\(')

    def validate(self, diff_text: str) -> None:
        if not self.DIFF_HEADER_RE.search(diff_text):
            raise ValueError("Not a unified diff")
```

## Module Organization

### schemas.py

```python
"""
Pydantic v2 models for test case data structure.

Defines all data contracts used throughout the pipeline.
"""

from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Dict, List, Optional

# Enums
class TestType(str, Enum): ...

# Data models (leaf nodes first)
class StubConfig(BaseModel): ...
class FunctionMeta(BaseModel): ...

# Composite models
class TestCase(BaseModel): ...

# Root model
class TestCaseFile(BaseModel): ...
    def validate_internal_consistency(self) -> List[str]: ...
```

### diff_validator.py

```python
"""
Diff validation and chunking.

Validates GitHub PR unified diffs and splits large diffs by function boundary.
"""

import re
from dataclasses import dataclass
from typing import List

@dataclass
class DiffChunk: ...

class DiffValidator:
    # Compiled patterns
    DIFF_HEADER_RE = ...
    HUNK_HEADER_RE = ...
    FUNCTION_DEF_RE = ...

    def __init__(self, max_lines: int = 300): ...

    def validate(self, diff_text: str) -> None: ...

    def chunk_by_function(self, diff_text: str) -> List[DiffChunk]: ...
```

### context_assembler.py

```python
"""
Context extraction from C diff using tree-sitter AST.

Extracts function signatures, struct definitions, typedefs, macros, and HAL functions.
"""

from tree_sitter import Language, Parser
import tree_sitter_c
from dataclasses import dataclass
from typing import Dict, List, Set, Optional

@dataclass
class FunctionSignature: ...
@dataclass
class StructDefinition: ...
@dataclass
class ContextPackage: ...

class ContextAssembler:
    HAL_PREFIXES = {'HAL_', 'Rte_', 'Com_'}

    def __init__(self): ...

    def assemble(self, diff_text: str) -> ContextPackage: ...

    def _extract_functions(self, tree) -> Dict[str, FunctionSignature]: ...
    def _extract_structs(self, tree) -> Dict[str, StructDefinition]: ...
    def _extract_typedefs(self, tree) -> Dict[str, str]: ...
    def _extract_macros(self, tree) -> Dict[str, str]: ...
    def _detect_hal_functions(self, tree) -> Set[str]: ...
```

### type_resolver.py

```python
"""
C type resolution and classification.

Maps C types to CType enum, resolves typedef chains, classifies parameters,
and determines correct zero/null values.
"""

from enum import Enum
from typing import Dict, Optional

class CType(Enum): ...
class ParamClass(Enum): ...

@dataclass
class TypeMetadata: ...

class TypeResolver:
    AUTOSAR_TYPES = {...}
    ZERO_VALUES = {...}
    NULL_VALUES = {...}

    def __init__(self, typedef_map: Dict[str, str]): ...

    def resolve(self, c_type_str: str) -> TypeMetadata: ...

    def _resolve_typedef(self, type_str: str) -> str: ...
    def _classify_string(self, type_str: str) -> CType: ...
    def _classify_param_class(self, c_type: CType) -> ParamClass: ...
```

## Integration Points

### Existing Code to Integrate (Do Not Modify)

From CONTEXT.md "Integration Points":
- `poller.py` — GitHub PR polling (used later, not in Phase 1)
- `glm_client.py` — GLM 4.7 Flash integration (used later, not in Phase 1)
- `processed_prs.json` — PR tracking (used later, not in Phase 1)

**Phase 1 does not integrate with these** — they're used in later phases.

### Dependencies Between Phase 1 Files

```
type_resolver.py depends on:
  - schemas.py (CType enum, TypeMetadata dataclass)

context_assembler.py depends on:
  - schemas.py (for type definitions, if needed)

diff_validator.py is independent.

schemas.py is independent (base foundation).
```

## Testing Patterns

### Test File Organization

```
tests/
  test_schemas.py         — Pydantic model tests
  test_diff_validator.py  — Diff validation/chunking tests
  test_context_assembler.py — AST extraction tests
  test_type_resolver.py   — Type resolution tests
```

### Test Pattern from Legacy Code

```python
import pytest

class TestTypeResolver:
    def test_resolve_uint8(self):
        resolver = TypeResolver({})
        metadata = resolver.resolve("uint8")
        assert metadata.c_type == CType.UINT8
        assert metadata.zero_value == "0u"

    def test_resolve_pointer(self):
        resolver = TypeResolver({})
        metadata = resolver.resolve("uint8*")
        assert metadata.c_type == CType.POINTER
        assert metadata.null_value == "NULL_PTR"

    def test_typedef_chain(self):
        typedef_map = {"MyType": "uint8", "RealType": "MyType"}
        resolver = TypeResolver(typedef_map)
        metadata = resolver.resolve("RealType")
        assert metadata.c_type == CType.UINT8
```

---

*Pattern map generated: 2026-04-28*
*All analogs extracted from legacy codebase for reference*
*New implementation will follow these patterns but use fresh code per decision D-01*
