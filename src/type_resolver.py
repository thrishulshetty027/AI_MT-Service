"""
Type classification and typedef resolution.

Maps C types to CType enum, resolves typedef chains, and provides
helpers for zero/null value determination and type classification.
"""

from enum import Enum
from typing import Dict, Tuple, Optional


class CType(str, Enum):
    """Comprehensive C type classification."""
    # Unsigned integers
    UINT8 = "UINT8"
    UINT16 = "UINT16"
    UINT32 = "UINT32"
    UINT64 = "UINT64"

    # Signed integers
    INT8 = "INT8"
    INT16 = "INT16"
    INT32 = "INT32"
    INT64 = "INT64"

    # Floating point
    FLOAT = "FLOAT"
    DOUBLE = "DOUBLE"

    # Complex types
    STRUCT = "STRUCT"
    POINTER = "POINTER"
    ARRAY = "ARRAY"

    # Boolean and void
    BOOL = "BOOL"
    VOID = "VOID"
    UNKNOWN = "UNKNOWN"


# Comprehensive type mapping
C_TYPE_TO_CTYPE = {
    # Standard C unsigned
    "uint8_t": CType.UINT8, "uint16_t": CType.UINT16, "uint32_t": CType.UINT32, "uint64_t": CType.UINT64,
    "unsigned char": CType.UINT8, "unsigned short": CType.UINT16, "unsigned int": CType.UINT32, "unsigned long": CType.UINT64,
    "unsigned long long": CType.UINT64,

    # Standard C signed
    "int8_t": CType.INT8, "int16_t": CType.INT16, "int32_t": CType.INT32, "int64_t": CType.INT64,
    "char": CType.INT8, "short": CType.INT16, "int": CType.INT32, "long": CType.INT64, "long long": CType.INT64,
    "signed char": CType.INT8, "signed short": CType.INT16, "signed int": CType.INT32, "signed long": CType.INT64,

    # Floating point
    "float": CType.FLOAT, "double": CType.DOUBLE,
    "float32": CType.FLOAT, "float64": CType.DOUBLE,
    "float32_t": CType.FLOAT, "float64_t": CType.DOUBLE,
    "long double": CType.DOUBLE,

    # Boolean
    "bool": CType.BOOL, "_Bool": CType.BOOL, "boolean": CType.BOOL,

    # Void
    "void": CType.VOID,
}


def resolve_typedef_chain(type_name: str, typedef_map: Dict[str, str], max_depth: int = 10, visited: Optional[set] = None) -> str:
    """
    Recursively resolve typedef chains.

    Args:
        type_name: The type name to resolve
        typedef_map: Dictionary mapping aliases to base types
        max_depth: Maximum recursion depth to prevent infinite loops
        visited: Set of visited types for cycle detection (internal use)

    Returns:
        Resolved base type name

    Examples:
        >>> typedef_map = {"MyType": "uint8", "uint8": "uint8_t"}
        >>> resolve_typedef_chain("MyType", typedef_map)
        "uint8_t"
    """
    if visited is None:
        visited = set()

    # Check for cycles
    if type_name in visited or max_depth <= 0:
        return type_name

    # If type is not in typedef map, return as-is
    if type_name not in typedef_map:
        return type_name

    # Add current type to visited set
    visited.add(type_name)

    # Recursively resolve
    base_type = typedef_map[type_name]
    resolved = resolve_typedef_chain(base_type, typedef_map, max_depth - 1, visited)

    return resolved


def classify_parameter(c_type: str, typedef_map: Dict[str, str] = None) -> Tuple[CType, str]:
    """
    Classify a C parameter type into CType enum.

    Handles:
    - Pointer types (suffix *)
    - Array types (suffix [])
    - Struct types (struct keyword or known struct)
    - Typedef resolution
    - Scalar types

    Args:
        c_type: The C type string
        typedef_map: Optional typedef map for resolution

    Returns:
        Tuple of (CType, resolved_base_type)

    Examples:
        >>> classify_parameter("uint8_t", {})
        (CType.UINT8, "uint8_t")

        >>> classify_parameter("uint8_t*", {})
        (CType.POINTER, "uint8_t")
    """
    if typedef_map is None:
        typedef_map = {}

    # Check for pointer type FIRST (before typedef resolution)
    is_pointer = '*' in c_type or c_type.endswith('*')
    is_array = '[]' in c_type or '[0]' in c_type

    # Extract base type for pointers/arrays
    base_type_for_resolution = c_type
    if is_pointer:
        base_type_for_resolution = c_type.replace('*', '').strip()
    elif is_array:
        # Handle cases like "int arr[]" and "uint8_t[]"
        # Remove the array brackets
        temp = c_type.replace('[]', '').replace('[0]', '').strip()

        # If there's a space, the type is likely the first word (or first two for "unsigned int")
        # Try to extract just the type part
        import re
        # Match: type_name [optional variable name]
        # We want to extract only the type keywords
        type_keywords = ['unsigned', 'signed', 'long', 'short', 'char', 'int', 'float', 'double', 'void', 'bool', '_Bool', 'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t', 'int8_t', 'int16_t', 'int32_t', 'int64_t', 'float32_t', 'float64_t']

        words = temp.split()
        if not words:
            base_type_for_resolution = temp
        elif len(words) == 1:
            base_type_for_resolution = words[0]
        else:
            # Multiple words - try to find where the type ends and variable name begins
            type_parts = []
            for word in words:
                if word in type_keywords or (len(type_parts) == 1 and type_parts[0] in ['unsigned', 'signed', 'long', 'short']):
                    type_parts.append(word)
                else:
                    # This is likely the variable name
                    break
            if type_parts:
                base_type_for_resolution = ' '.join(type_parts)
            else:
                # Fallback: just use the first word
                base_type_for_resolution = words[0]

    # Resolve typedef chain on the base type
    resolved_type = resolve_typedef_chain(base_type_for_resolution, typedef_map)

    # Now classify based on original and resolved type
    if is_pointer:
        return (CType.POINTER, resolved_type)

    if is_array:
        return (CType.ARRAY, resolved_type)

    # Check for struct type
    if resolved_type.startswith('struct ') or resolved_type.startswith('struct\t'):
        base_type = resolved_type.replace('struct', '').strip()
        return (CType.STRUCT, base_type)

    # Check in type mapping
    if resolved_type in C_TYPE_TO_CTYPE:
        return (C_TYPE_TO_CTYPE[resolved_type], resolved_type)

    # Unknown type
    return (CType.UNKNOWN, resolved_type)


def get_zero_value(c_type: CType) -> str:
    """
    Get the zero value literal for a CType.

    Args:
        c_type: The CType enum value

    Returns:
        Zero value as a string

    Examples:
        >>> get_zero_value(CType.UINT8)
        "0u"

        >>> get_zero_value(CType.FLOAT)
        "0.0f"
    """
    if c_type in (CType.UINT8, CType.UINT16, CType.UINT32, CType.UINT64):
        return "0u"
    elif c_type in (CType.INT8, CType.INT16, CType.INT32, CType.INT64):
        return "0"
    elif c_type == CType.FLOAT:
        return "0.0f"
    elif c_type == CType.DOUBLE:
        return "0.0"
    elif c_type == CType.BOOL:
        return "FALSE"
    elif c_type in (CType.POINTER, CType.ARRAY, CType.STRUCT):
        return "NULL_PTR"
    elif c_type == CType.VOID:
        return ""
    else:  # UNKNOWN
        return "0"


def get_null_value(c_type: CType) -> Optional[str]:
    """
    Get the null value for a CType.

    Only pointer-like types (POINTER, ARRAY, STRUCT) have meaningful null values.

    Args:
        c_type: The CType enum value

    Returns:
        Null value as string, or None if not applicable

    Examples:
        >>> get_null_value(CType.POINTER)
        "NULL_PTR"

        >>> get_null_value(CType.INT32)
        None
    """
    if c_type in (CType.POINTER, CType.ARRAY, CType.STRUCT):
        return "NULL_PTR"
    else:
        return None


def is_scalar(c_type: CType) -> bool:
    """
    Check if a CType is a scalar type.

    Scalar types: UINT8-INT64, FLOAT, DOUBLE, BOOL

    Args:
        c_type: The CType enum value

    Returns:
        True if scalar, False otherwise
    """
    return c_type in (
        CType.UINT8, CType.UINT16, CType.UINT32, CType.UINT64,
        CType.INT8, CType.INT16, CType.INT32, CType.INT64,
        CType.FLOAT, CType.DOUBLE,
        CType.BOOL
    )


def is_pointer_like(c_type: CType) -> bool:
    """
    Check if a CType is pointer-like.

    Pointer-like types can be NULL_PTR: POINTER, ARRAY, STRUCT

    Args:
        c_type: The CType enum value

    Returns:
        True if pointer-like, False otherwise
    """
    return c_type in (CType.POINTER, CType.ARRAY, CType.STRUCT)
