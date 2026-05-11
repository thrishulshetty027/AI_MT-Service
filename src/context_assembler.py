"""
Context assembly from diffs.

Extracts function signatures, struct definitions, typedefs, macros, and HAL functions
from diff content using tree-sitter AST parsing.
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass
from pydantic import BaseModel

import tree_sitter_c as tsc
from tree_sitter import Language, Parser


@dataclass
class ContextPackage:
    """Package of extracted context from a diff."""
    diff_text: str
    function_signatures: List[Dict]
    struct_definitions: Dict[str, List[str]]
    typedef_map: Dict[str, str]
    macro_constants: Dict[str, str]
    hal_functions: List[str]
    existing_pattern: Optional[str] = None


def _strip_diff_markers(diff_content: str) -> str:
    """
    Remove diff markers and extract clean C code.

    Args:
        diff_content: Raw diff content

    Returns:
        Clean C code with diff markers removed
    """
    lines = []
    for line in diff_content.split('\n'):
        stripped = line.strip()

        # Skip diff headers
        if stripped.startswith('diff --git') or stripped.startswith('---') or stripped.startswith('+++'):
            continue

        # Skip hunk headers
        if stripped.startswith('@@'):
            continue

        # Skip removals
        if stripped.startswith('-') and not stripped.startswith('--'):
            continue

        # Keep added lines (strip the + prefix)
        if stripped.startswith('+'):
            lines.append(stripped[1:])
        # Keep context lines
        elif stripped:
            lines.append(line)

    return '\n'.join(lines)


def _extract_function_signatures(node, code: str) -> List[Dict]:
    """
    Extract function signatures from AST.

    Args:
        node: Tree-sitter AST node
        code: Clean C code string

    Returns:
        List of function signature dicts with name, return_type, parameters,
        and full_signature (exact original C signature string)
    """
    functions = []

    def _get_type_str(n):
        if n.type in ('primitive_type', 'type_identifier', 'sized_type_specifier'):
            return code[n.start_byte:n.end_byte]
        if n.type == 'struct_specifier':
            parts = []
            for child in n.children:
                if child.type == 'struct':
                    parts.append('struct')
                elif child.type == 'type_identifier':
                    parts.append(code[child.start_byte:child.end_byte])
            return ' '.join(parts) if parts else None
        return None

    def traverse(n):
        if n.type == 'function_definition':
            func_name = None
            return_type = None
            parameters = []
            is_pointer_return = False

            for child in n.children:
                type_str = _get_type_str(child)
                if type_str:
                    return_type = type_str
                elif child.type == 'pointer_declarator':
                    for subchild in child.children:
                        if subchild.type == '*':
                            is_pointer_return = True
                        elif subchild.type == 'function_declarator':
                            for sub2 in subchild.children:
                                if sub2.type == 'identifier':
                                    func_name = code[sub2.start_byte:sub2.end_byte]
                                elif sub2.type == 'parameter_list':
                                    for param in sub2.children:
                                        if param.type == 'parameter_declaration':
                                            param_info = _extract_parameter(param, code)
                                            if param_info:
                                                parameters.append(param_info)
                elif child.type == 'function_declarator':
                    for subchild in child.children:
                        if subchild.type == 'identifier':
                            func_name = code[subchild.start_byte:subchild.end_byte]
                        elif subchild.type == 'parameter_list':
                            for param in subchild.children:
                                if param.type == 'parameter_declaration':
                                    param_info = _extract_parameter(param, code)
                                    if param_info:
                                        parameters.append(param_info)

            if func_name:
                full_ret = return_type or 'void'
                if is_pointer_return:
                    full_ret = full_ret + '*'

                param_strs = []
                for p in parameters:
                    t = p.get('full_type', p['type'])
                    param_strs.append(f"{t} {p['name']}")

                full_sig = f"{full_ret} {func_name}({', '.join(param_strs) if param_strs else 'void'})"

                functions.append({
                    'name': func_name,
                    'return_type': full_ret,
                    'parameters': parameters,
                    'full_signature': full_sig,
                })

        for child in n.children:
            traverse(child)

    traverse(node)
    return functions


def _extract_parameter(node, code: str) -> Optional[Dict]:
    """Extract parameter information from a parameter_declaration node."""
    param_name = None
    param_type = None
    is_pointer = False

    def _get_type_str(n):
        if n.type in ('primitive_type', 'type_identifier', 'sized_type_specifier'):
            return code[n.start_byte:n.end_byte]
        if n.type == 'struct_specifier':
            parts = []
            for child in n.children:
                if child.type == 'struct':
                    parts.append('struct')
                elif child.type == 'type_identifier':
                    parts.append(code[child.start_byte:child.end_byte])
            return ' '.join(parts) if parts else None
        return None

    for child in node.children:
        if child.type == 'identifier':
            param_name = code[child.start_byte:child.end_byte]
        ts = _get_type_str(child)
        if ts and not param_type:
            param_type = ts
        elif child.type == 'pointer_declarator':
            is_pointer = True
            for subchild in child.children:
                if subchild.type == 'identifier':
                    param_name = code[subchild.start_byte:subchild.end_byte]
                st = _get_type_str(subchild)
                if st and not param_type:
                    param_type = st

    if param_name:
        full_type = param_type or 'void'
        if is_pointer:
            full_type = full_type + '*'
        return {
            'name': param_name,
            'type': param_type or 'void',
            'full_type': full_type,
            'is_pointer': is_pointer,
        }
    return None


def _extract_struct_definitions(node, code: str) -> Dict[str, List[str]]:
    """
    Extract struct definitions from AST.

    Args:
        node: Tree-sitter AST node
        code: Clean C code string

    Returns:
        Dict mapping struct names to list of field names
    """
    structs = {}

    def _find_field_identifier(n):
        for child in n.children:
            if child.type == 'field_identifier':
                return code[child.start_byte:child.end_byte]
            if child.type == 'pointer_declarator':
                for sub in child.children:
                    if sub.type == 'field_identifier':
                        return code[sub.start_byte:sub.end_byte]
        return None

    def traverse(n):
        if n.type == 'struct_specifier':
            struct_name = None
            fields = []

            for child in n.children:
                if child.type == 'type_identifier':
                    struct_name = code[child.start_byte:child.end_byte]
                elif child.type == 'field_declaration_list':
                    for field_decl in child.children:
                        if field_decl.type == 'field_declaration':
                            field_name = _find_field_identifier(field_decl)
                            if field_name:
                                fields.append(field_name)

            if struct_name and fields:
                structs[struct_name] = fields

        elif n.type == 'type_definition':
            typedef_name = None
            struct_specifier_node = None

            for child in n.children:
                if child.type == 'type_identifier':
                    typedef_name = code[child.start_byte:child.end_byte]
                elif child.type == 'struct_specifier':
                    struct_specifier_node = child

            if typedef_name and struct_specifier_node:
                fields = []
                for child in struct_specifier_node.children:
                    if child.type == 'field_declaration_list':
                        for field_decl in child.children:
                            if field_decl.type == 'field_declaration':
                                field_name = _find_field_identifier(field_decl)
                                if field_name:
                                    fields.append(field_name)
                if fields:
                    structs[typedef_name] = fields

        for child in n.children:
            traverse(child)

    traverse(node)
    return structs


def _extract_typedefs(node, code: str) -> Dict[str, str]:
    """
    Extract typedef statements from AST.

    Args:
        node: Tree-sitter AST node
        code: Clean C code string

    Returns:
        Dict mapping alias names to base types
    """
    typedefs = {}

    def traverse(n):
        if n.type == 'type_definition':
            # Extract typedef: typedef <base_type> <alias>;
            alias = None
            base_type = None
            is_pointer = False
            struct_name = None

            for child in n.children:
                if child.type == 'type_identifier':
                    alias = code[child.start_byte:child.end_byte]
                elif child.type == 'primitive_type':
                    base_type = code[child.start_byte:child.end_byte]
                elif child.type == 'struct_specifier':
                    # For struct typedefs, check if it has a name
                    for subchild in child.children:
                        if subchild.type == 'type_identifier':
                            struct_name = code[subchild.start_byte:subchild.end_byte]
                    if struct_name:
                        base_type = 'struct ' + struct_name
                    else:
                        # Anonymous struct, use the typedef name
                        base_type = 'struct'
                elif child.type == 'pointer_declarator':
                    # Pointer typedef - alias is inside pointer_declarator
                    is_pointer = True
                    for subchild in child.children:
                        if subchild.type == 'type_identifier':
                            alias = code[subchild.start_byte:subchild.end_byte]

            if alias and base_type:
                if is_pointer:
                    typedefs[alias] = base_type + '*'
                else:
                    typedefs[alias] = base_type

        for child in n.children:
            traverse(child)

    traverse(node)
    return typedefs


def _extract_macros(diff_content: str) -> Dict[str, str]:
    """
    Extract #define macros using regex.

    Args:
        diff_content: Raw diff content

    Returns:
        Dict mapping macro names to their values
    """
    macros = {}

    # Pattern to match #define NAME value (including lines with + prefix)
    # Matches both simple defines and function-like macros with complex expressions
    # Uses a greedy match to capture everything after the macro name
    pattern = re.compile(r'^\+?\s*#define\s+(\w+)(?:\([^)]*\))?\s+(.+)\s*$')

    for line in diff_content.split('\n'):
        match = pattern.match(line)
        if match:
            name = match.group(1)
            value = match.group(2).strip()
            macros[name] = value

    return macros


def _detect_hal_functions(node, code: str) -> List[str]:
    """
    Detect HAL function calls from AST.

    Args:
        node: Tree-sitter AST node
        code: Clean C code string

    Returns:
        List of detected HAL function names (with HAL_, Rte_, Com_ prefixes)
    """
    hal_prefixes = ('HAL_', 'Rte_', 'Com_')
    hal_functions = set()

    def traverse(n):
        if n.type == 'call_expression':
            # Find function name
            for child in n.children:
                if child.type == 'identifier':
                    func_name = code[child.start_byte:child.end_byte]
                    if func_name.startswith(hal_prefixes):
                        hal_functions.add(func_name)
                    break

        for child in n.children:
            traverse(child)

    traverse(node)
    return sorted(list(hal_functions))


def extract_context_from_diff(diff_content: str) -> ContextPackage:
    """
    Extract complete context from a diff.

    Uses tree-sitter to parse the C code and extract:
    - Function signatures
    - Struct definitions
    - Typedefs
    - Macros
    - HAL function calls

    Args:
        diff_content: Raw diff content

    Returns:
        ContextPackage with all extracted information
    """
    # Strip diff markers to get clean C code
    clean_code = _strip_diff_markers(diff_content)

    # Initialize tree-sitter parser for C
    parser = Parser()
    parser.language = Language(tsc.language())

    # Parse the clean code
    tree = parser.parse(bytes(clean_code, 'utf8'))
    root_node = tree.root_node

    # Extract all context components
    function_signatures = _extract_function_signatures(root_node, clean_code)
    struct_definitions = _extract_struct_definitions(root_node, clean_code)
    typedef_map = _extract_typedefs(root_node, clean_code)
    macro_constants = _extract_macros(diff_content)
    hal_functions = _detect_hal_functions(root_node, clean_code)

    return ContextPackage(
        diff_text=diff_content,
        function_signatures=function_signatures,
        struct_definitions=struct_definitions,
        typedef_map=typedef_map,
        macro_constants=macro_constants,
        hal_functions=hal_functions
    )
